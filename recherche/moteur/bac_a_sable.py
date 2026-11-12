"""Bac à sable d'exécution des stratégies : contrôle AST, worker sous `bwrap`, dialogue par tubes.

Défense en profondeur, du plus faible au plus fort :
1. contrôle AST du texte exact exécuté (liste blanche d'imports, noms et attributs interdits) ;
2. builtins restreints dans le worker (pas d'`open`, d'`exec`, d'`__import__` libre) ;
3. `bwrap --unshare-all` : ni réseau, ni `$HOME`, ni dépôt ; `/usr` et la bibliothèque numpy en lecture
   seule, un tmpfs pour `/tmp`, `--die-with-parent`, aucune capacité ;
4. délai dur (chien de garde) et limites de ressources dans le worker.
Le parent ne désérialise jamais (pickle) ce que le worker écrit.
"""

from __future__ import annotations

import ast
import builtins
import dataclasses
import json
import os
import pickle
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Self

import numpy as np

from recherche.moteur import contrat
from recherche.moteur.contrat import (
    DelaiDepasse,
    ErreurEssai,
    FormePoids,
    SourceRefusee,
)

_DIR = Path(__file__).resolve().parent
IMPORTS_PERMIS = frozenset({"math", "statistics", "numpy", "collections", "itertools", "functools", "heapq",
                            "bisect"})
NOMS_INTERDITS = frozenset({
    "open", "exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr", "globals", "locals",
    "vars", "input", "breakpoint", "memoryview", "exit", "quit", "help", "time", "datetime", "random", "os",
    "sys", "socket", "subprocess", "pathlib", "importlib", "builtins", "ctypes"})
ATTRS_INTERDITS = frozenset({
    "open", "exec", "eval", "compile", "load", "save", "savez", "savez_compressed", "savetxt", "loadtxt",
    "genfromtxt", "fromfile", "tofile", "fromregex", "memmap", "DataSource", "ctypeslib", "f2py", "testing",
    "system", "popen", "random", "os", "sys", "subprocess", "socket", "time", "datetime", "pathlib",
    "importlib", "ctypes", "builtins", "lib", "core", "_core", "fromstring"})
#: Préfixes d'attributs interdits : internes de générateurs/coroutines/cadres/traces/code (gi_frame, cr_frame,
#: ag_frame, f_back, f_locals, f_globals, tb_frame, co_code...) qui permettent de sortir des builtins restreints.
PREFIXES_ATTRS_INTERDITS = ("read_", "__", "gi_", "cr_", "ag_", "f_", "tb_", "co_")
#: Noms explicitement interdits en attribut (couverts aussi par le préfixe `__`, listés pour mémoire).
DUNDERS_INTERDITS = frozenset({"__traceback__", "__code__", "__globals__", "__closure__", "__subclasses__",
                               "__mro__", "__bases__", "__class__", "__dict__", "__getattribute__"})
#: Anti-mémoire : pas de grande table de constantes dans une stratégie (elle embarquerait une mémoire du futur).
MAX_LITTERAUX_NUMERIQUES = 32
MAX_ELEMENTS_LITTERAL = 16
MAX_LONGUEUR_CHAINE = 64
LIMITE_MEMOIRE = 6 * 2**30
EXCEPTIONS_STANDARD = frozenset(
    k for k, v in vars(builtins).items() if isinstance(v, type) and issubclass(v, BaseException))


# ----------------------------------------------------------------------------------------------------
# Contrôle AST
# ----------------------------------------------------------------------------------------------------


def verifier_source(texte: str, nom: str = "strategie.py") -> None:
    """Lève `SourceRefusee` si le texte viole la liste blanche. Contrôle le texte exact qui sera exécuté."""
    try:
        arbre = ast.parse(texte, filename=nom)
    except (SyntaxError, ValueError) as e:
        raise SourceRefusee(f"{nom} : syntaxe : {e}") from None

    def refus(n, raison):
        raise SourceRefusee(f"{nom} ligne {getattr(n, 'lineno', '?')} : {raison}")

    docstrings = set()
    for n in ast.walk(arbre):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body \
                and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant) \
                and isinstance(n.body[0].value.value, str):
            docstrings.add(id(n.body[0].value))
    n_numeriques = 0
    classes = {n.name for n in arbre.body if isinstance(n, ast.ClassDef)}
    if "Strategie" not in classes:
        raise SourceRefusee(f"{nom} : classe `Strategie` absente")
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name not in IMPORTS_PERMIS:
                    refus(n, f"import {a.name!r} interdit")
                if a.asname and (a.asname in NOMS_INTERDITS or a.asname.startswith("__")):
                    refus(n, f"alias {a.asname!r} interdit")
        elif isinstance(n, ast.ImportFrom):
            if n.level or (n.module or "") not in IMPORTS_PERMIS:
                refus(n, f"import depuis {n.module!r} interdit")
            for a in n.names:
                if a.name == "*" or a.name in ATTRS_INTERDITS or a.name in NOMS_INTERDITS \
                        or a.name.startswith("__") or a.name.startswith("read_"):
                    refus(n, f"import du nom {a.name!r} interdit")
                if a.asname and (a.asname in NOMS_INTERDITS or a.asname.startswith("__")):
                    refus(n, f"alias {a.asname!r} interdit")
        elif isinstance(n, ast.Name):
            if n.id in NOMS_INTERDITS or (n.id.startswith("__") and n.id.endswith("__")):
                refus(n, f"nom {n.id!r} interdit")
        elif isinstance(n, ast.Attribute):
            a = n.attr
            if a in ATTRS_INTERDITS or a in NOMS_INTERDITS or a in DUNDERS_INTERDITS \
                    or a.startswith(PREFIXES_ATTRS_INTERDITS):
                refus(n, f"attribut .{a} interdit")
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if n.name in NOMS_INTERDITS or (n.name.startswith("__") and n.name.endswith("__")
                                            and not isinstance(n, ast.ClassDef)
                                            and n.name not in {"__init__", "__call__", "__repr__"}):
                refus(n, f"définition {n.name!r} interdite")
        elif isinstance(n, ast.arg):
            if n.arg in NOMS_INTERDITS:
                refus(n, f"argument {n.arg!r} interdit")
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            continue
        elif isinstance(n, ast.Constant):
            v = n.value
            if isinstance(v, str) and v.startswith("__") and v.endswith("__"):
                refus(n, "chaîne de type dunder interdite")
            if isinstance(v, (int, float, complex)) and not isinstance(v, bool):
                n_numeriques += 1
            elif isinstance(v, (str, bytes)) and len(v) > MAX_LONGUEUR_CHAINE and id(n) not in docstrings:
                refus(n, f"chaîne littérale de plus de {MAX_LONGUEUR_CHAINE} caractères (table de constantes)")
        elif isinstance(n, (ast.List, ast.Tuple, ast.Set)) and len(n.elts) > MAX_ELEMENTS_LITTERAL:
            refus(n, f"littéral de plus de {MAX_ELEMENTS_LITTERAL} éléments (table de constantes)")
        elif isinstance(n, ast.Dict) and len(n.keys) > MAX_ELEMENTS_LITTERAL:
            refus(n, f"dict littéral de plus de {MAX_ELEMENTS_LITTERAL} éléments (table de constantes)")
    if n_numeriques > MAX_LITTERAUX_NUMERIQUES:
        raise SourceRefusee(f"{nom} : {n_numeriques} littéraux numériques (> {MAX_LITTERAUX_NUMERIQUES}) : "
                            "table de constantes interdite")


# ----------------------------------------------------------------------------------------------------
# bwrap
# ----------------------------------------------------------------------------------------------------


def bwrap_disponible() -> bool:
    return shutil.which("bwrap") is not None


def _site_packages() -> str:
    return str(Path(np.__file__).resolve().parent.parent)


def _commande(job: str, script: str, args: list[str]) -> list[str]:
    exe = os.path.realpath(sys.executable)
    cmd = [
        "bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL", "--clearenv",
        "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
        "--symlink", "usr/bin", "/bin", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
    ]
    prefixe = os.path.realpath(sys.base_prefix)
    if not exe.startswith("/usr/") and not (prefixe + "/").startswith("/usr/"):
        cmd += ["--ro-bind", prefixe, prefixe]  # interpréteur hors /usr (python géré par uv)
    cmd += [
        "--ro-bind", _site_packages(), "/venv", "--ro-bind", job, "/job", "--chdir", "/tmp",
        "--setenv", "PATH", "/usr/bin", "--setenv", "LANG", "C.UTF-8", "--setenv", "PYTHONHASHSEED", "0",
        "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--setenv", "OMP_NUM_THREADS", "1",
        "--setenv", "OPENBLAS_NUM_THREADS", "1", "--setenv", "MKL_NUM_THREADS", "1",
        exe, "-I", "-B", f"/job/{script}", *args,
    ]
    return cmd


def _preparer_job(source: bytes | None, script: str, script_texte: str | None = None) -> str:
    job = tempfile.mkdtemp(prefix="recherche-bac-")
    os.chmod(job, 0o700)
    shutil.copy(_DIR / "contrat.py", Path(job) / "contrat.py")
    if script_texte is None:
        shutil.copy(_DIR / script, Path(job) / script)
    else:
        (Path(job) / script).write_text(script_texte, encoding="utf-8")
    if source is not None:
        (Path(job) / "strategie.py").write_bytes(source)
    for p in Path(job).iterdir():
        p.chmod(0o444)
    return job


# ----------------------------------------------------------------------------------------------------
# Worker
# ----------------------------------------------------------------------------------------------------


class Worker:
    """Un processus worker sous bwrap. Usage : `with Worker(source, n, params, timeout) as w: w.pas(...)`."""

    def __init__(self, source: bytes, n_paires: int, params: dict, timeout_s: float):
        if not bwrap_disponible():
            raise ErreurEssai("bwrap introuvable : exécution refusée")
        self.n = n_paires
        self.params = params
        self.timeout_s = timeout_s
        self.source = source
        self.job: str | None = None
        self.proc: subprocess.Popen | None = None
        self.delai = False
        self._timer: threading.Timer | None = None

    def __enter__(self) -> Self:
        self.job = _preparer_job(self.source, "_worker.py")
        self.proc = subprocess.Popen(
            _commande(self.job, "_worker.py", ["/job", "/venv", "/job", str(LIMITE_MEMOIRE)]),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
            bufsize=0)
        self._timer = threading.Timer(self.timeout_s, self._tuer)
        self._timer.daemon = True
        self._timer.start()
        self._envoyer(("init", self.n, self.params))
        statut, charge = self._recevoir()
        if statut != 2:
            self._echec(statut, charge)
        return self

    def __exit__(self, *exc) -> None:
        if self._timer:
            self._timer.cancel()
        if self.proc is not None:
            try:
                if self.proc.poll() is None:
                    try:
                        self._envoyer(("fin",))
                    except ErreurEssai:
                        pass
                    try:
                        self.proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self._tuer()
                        self.proc.wait()
            finally:
                for f in (self.proc.stdin, self.proc.stdout):
                    try:
                        f.close()
                    except OSError:
                        pass
        if self.job:
            for p in Path(self.job).iterdir():
                p.chmod(0o644)
            shutil.rmtree(self.job, ignore_errors=True)

    def _tuer(self) -> None:
        self.delai = True
        try:
            os.killpg(self.proc.pid, 9)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            self.proc.kill()
        except ProcessLookupError:
            pass

    def _envoyer(self, obj) -> None:
        octets = pickle.dumps(obj, protocol=5)
        try:
            self.proc.stdin.write(struct.pack("<I", len(octets)) + octets)
        except (BrokenPipeError, OSError):
            self._mort()

    def _lire(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            morceau = self.proc.stdout.read(n - len(buf))
            if not morceau:
                self._mort()
            buf += morceau
        return bytes(buf)

    def _mort(self):
        if self.delai:
            raise DelaiDepasse(f"délai de {self.timeout_s:.0f} s dépassé")
        code = self.proc.poll()
        raise ErreurEssai(f"worker mort (code {code})")

    def _recevoir(self) -> tuple[int, bytes]:
        (taille,) = struct.unpack("<I", self._lire(4))
        if taille < 1 or taille > 16 * 2**20:
            raise ErreurEssai(f"trame de {taille} octets refusée")
        corps = self._lire(taille)
        return corps[0], corps[1:]

    def _echec(self, statut: int, charge: bytes):
        """Aucun texte venant de la stratégie ne passe : seulement le type d'exception, et seulement s'il
        s'agit d'une exception standard (un nom de classe choisi par la stratégie serait un canal)."""
        nom = charge.decode("utf-8", "replace")
        if nom not in EXCEPTIONS_STANDARD:
            nom = "exception_non_standard"
        if statut == 3:
            raise FormePoids(f"sortie mal formée ({nom})")
        raise ErreurEssai(f"erreur de la stratégie ({nom})")

    def pas(self, jour) -> tuple[np.ndarray, np.ndarray]:
        self._envoyer(("jour", jour.i, jour.spot_1d, jour.spot_1h, jour.perp_1h, jour.funding,
                       jour.eligibles, jour.eligibles_perp))
        statut, charge = self._recevoir()
        if statut != 0:
            self._echec(statut, charge)
        if len(charge) != 16 * self.n:
            raise ErreurEssai(f"charge de {len(charge)} octets, {16 * self.n} attendus")
        v = np.frombuffer(charge, dtype="<f8")
        return v[: self.n].copy(), v[self.n:].copy()


DECALAGE_MIN = 10_000


def tirer_decalage() -> int:
    """Décalage entier aléatoire (os.urandom) ajouté à `Jour.i` : >= 10 000, tiré par essai."""
    return DECALAGE_MIN + int.from_bytes(os.urandom(4), "big") % (1 << 24)


def executer_flux(source: bytes, params: dict, panneau, validateur, timeout_s: float,
                  verifier_ast: bool = True, jusqu_a_erreur: int | None = None,
                  decalage: int | None = None) -> tuple[np.ndarray, np.ndarray, int]:
    """Envoie les jours du panneau (dans l'ordre) à la stratégie ; `validateur(i, ws, wp)` est appelé pour
    chaque jour et lève `FormePoids` si la forme est violée. Renvoie (poids_spot, poids_perp, n_jours_ok)
    avec des tableaux (T, N). Si `jusqu_a_erreur` est donné, une erreur (hors délai) n'est tolérée qu'à
    partir de ce jour (les jours suivants restent à 0 et `n_jours_ok` dit où elle s'est produite) ; sinon
    toute erreur est levée.

    Ce que voit la stratégie : le panneau REBASÉ (`Panneau.rebaser` : prix ÷ premier close de la paire,
    volumes ÷ volume moyen des 30 premiers jours cotés, causal) et un index de jour `Jour.i = décalage + k`
    où `décalage` (>= 10 000) est tiré par appel : elle peut compter les jours, pas en déduire la date.
    Le moteur calcule les rendements sur les prix réels (`portefeuille.simuler`), jamais sur ce panneau.
    Le détail des erreurs ne contient aucun texte de la stratégie : le type d'exception standard et le jour."""
    if verifier_ast:
        verifier_source(source.decode("utf-8", "replace"))
    T, N = panneau.n_jours, panneau.n_paires
    if decalage is None:
        decalage = tirer_decalage()
    vue = panneau.rebaser()
    ws = np.zeros((T, N))
    wp = np.zeros((T, N))
    n_ok = 0
    with Worker(source, N, params, timeout_s) as w:
        for i in range(T):
            try:
                a, b = w.pas(dataclasses.replace(vue.jour(i), i=decalage + i))
                validateur(i, a, b)
            except ErreurEssai as e:
                if "jour" not in e.detail:
                    e.detail = f"{e.detail} (jour {i})"
                if isinstance(e, DelaiDepasse) or jusqu_a_erreur is None or i < jusqu_a_erreur:
                    raise
                break
            ws[i], wp[i] = a, b
            n_ok = i + 1
    return ws, wp, n_ok


# ----------------------------------------------------------------------------------------------------
# Canari
# ----------------------------------------------------------------------------------------------------

_CANARI_SCRIPT = r'''
import json, os, sys, socket
sys.path.insert(0, "/venv")
cfg = json.loads(sys.argv[1])
sortie = {}

def essayer(nom, f):
    try:
        f()
        sortie[nom] = True      # l'action interdite a REUSSI
    except BaseException as e:
        sortie[nom] = False

def connexion():
    s = socket.socket(); s.settimeout(2); s.connect(("127.0.0.1", cfg["port"])); s.close()
def connexion_externe():
    s = socket.socket(); s.settimeout(2); s.connect(("1.1.1.1", 53)); s.close()
def lire_home():
    open(cfg["home_fichier"], "rb").read()
def lire_decoy():
    open(cfg["decoy_lecture"], "rb").read()
def ecrire_depot():
    open(cfg["depot_ecriture"], "w").write("x")
def ecrire_usr():
    open("/usr/canari-x", "w").write("x")
def ecrire_job():
    open("/job/canari-x", "w").write("x")
def lister_home():
    if os.path.exists(cfg["home"]) and os.listdir(cfg["home"]):
        return
    raise OSError
def lister_depot():
    if os.path.exists(cfg["depot"]) and os.listdir(cfg["depot"]):
        return
    raise OSError
for nom, f in [("connect_loopback", connexion), ("connect_externe", connexion_externe),
               ("lecture_bashrc", lire_home), ("lecture_hors_liste", lire_decoy),
               ("ecriture_depot", ecrire_depot), ("ecriture_usr", ecrire_usr), ("ecriture_job", ecrire_job),
               ("listage_home", lister_home), ("listage_depot", lister_depot)]:
    essayer(nom, f)
temoins = {}
try:
    open("/tmp/ok", "w").write("ok"); temoins["tmp_ecriture"] = open("/tmp/ok").read() == "ok"
except BaseException:
    temoins["tmp_ecriture"] = False
try:
    import numpy as np; temoins["numpy"] = float(np.arange(4).sum()) == 6.0
except BaseException:
    temoins["numpy"] = False
os.write(1, (json.dumps({"interdit_reussi": sortie, "temoins": temoins}) + "\n").encode())
'''

_canari_ok = False
_canari_verrou = threading.Lock()


class CanariError(Exception):
    """Le bac à sable laisse passer une action interdite (ou ne fonctionne pas) : le moteur refuse de démarrer."""


def canari(force: bool = False, *, depot: Path | None = None) -> None:
    """Lance un worker de test qui tente connect(), lectures hors liste blanche et écritures hors tmpfs.
    Lève `CanariError` si l'une de ces actions réussit, ou si les témoins (écriture dans /tmp, numpy) échouent."""
    global _canari_ok
    with _canari_verrou:
        if _canari_ok and not force:
            return
        if not bwrap_disponible():
            raise CanariError("bwrap introuvable")
        depot = depot or _DIR.parents[1]
        home = Path.home()
        decoy_dir = Path(tempfile.mkdtemp(prefix="recherche-canari-"))
        (decoy_dir / "secret.txt").write_text("secret du canari")
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(4)
        port = srv.getsockname()[1]
        ecriture = depot / "var" / "canari-ne-doit-pas-exister"
        job = _preparer_job(None, "_canari.py", _CANARI_SCRIPT)
        try:
            cfg = {"port": port, "home_fichier": str(home / ".bashrc"), "home": str(home),
                   "depot": str(depot), "decoy_lecture": str(decoy_dir / "secret.txt"),
                   "depot_ecriture": str(ecriture)}
            try:
                r = subprocess.run(_commande(job, "_canari.py", [json.dumps(cfg)]), capture_output=True, check=False,
                                   timeout=60, start_new_session=True)
            except subprocess.TimeoutExpired:
                raise CanariError("canari : délai dépassé") from None
            if r.returncode != 0:
                raise CanariError(f"canari : bwrap/python a échoué ({r.returncode}) : "
                                  f"{r.stderr.decode('utf-8', 'replace')[-400:]}")
            try:
                res = json.loads(r.stdout.decode().strip().splitlines()[-1])
            except (ValueError, IndexError):
                raise CanariError(f"canari : sortie illisible : {r.stdout[-200:]!r}") from None
            if ecriture.exists():
                ecriture.unlink()
                raise CanariError("canari : écriture dans le dépôt réussie")
            srv.settimeout(0.01)
            try:
                srv.accept()
                raise CanariError("canari : le serveur de test a reçu une connexion")
            except (TimeoutError, BlockingIOError):
                pass
            reussies = [k for k, v in res["interdit_reussi"].items() if v]
            if reussies:
                raise CanariError(f"canari : actions interdites réussies : {sorted(reussies)}")
            manquants = [k for k, v in res["temoins"].items() if not v]
            if manquants:
                raise CanariError(f"canari : témoins en échec : {sorted(manquants)}")
        finally:
            srv.close()
            shutil.rmtree(job, ignore_errors=True)
            shutil.rmtree(decoy_dir, ignore_errors=True)
        _canari_ok = True


__all__ = [
    "CanariError",
    "Worker",
    "bwrap_disponible",
    "canari",
    "contrat",
    "executer_flux",
    "verifier_source",
]
