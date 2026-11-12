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
    "dir", "type", "open", "exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr", "globals", "locals",
    "vars", "input", "breakpoint", "memoryview", "exit", "quit", "help", "time", "datetime", "random", "os",
    "sys", "socket", "subprocess", "pathlib", "importlib", "builtins", "ctypes"})
ATTRS_INTERDITS = frozenset({
    "open", "exec", "eval", "compile", "load", "save", "savez", "savez_compressed", "savetxt", "loadtxt",
    "genfromtxt", "fromfile", "tofile", "fromregex", "memmap", "DataSource", "ctypeslib", "f2py", "testing",
    "system", "popen", "random", "os", "sys", "subprocess", "socket", "time", "datetime", "pathlib",
    "importlib", "ctypes", "builtins", "lib", "core", "_core", "fromstring",
    # E/S fichier restantes de numpy / ndarray (revue 2) : écriture d'un fichier par `arr.dump(chemin)`, etc.
    "dump", "dumps", "loads", "test", "show_config", "show_runtime", "info", "source", "get_include",
    "distutils", "compat", "array_api",
    # Sous-modules numpy qui exposent des modules hors liste blanche (`np.char.overrides.inspect.os`,
    # `np.ma.extras.ma.operator`...) : trouvés par parcours (`test_revue2_moteur::test_aucun_chemin_...`).
    "ma", "char", "rec", "overrides", "extras", "mrecords", "matlib", "matrixlib",
    "inspect", "operator", "re", "textwrap", "warnings", "numbers", "dt", "types", "typing"})
#: Préfixes d'attributs interdits : internes de générateurs/coroutines/cadres/traces/code (gi_frame, cr_frame,
#: ag_frame, f_back, f_locals, f_globals, tb_frame, co_code...) qui permettent de sortir des builtins restreints.
PREFIXES_ATTRS_INTERDITS = ("read_", "__", "gi_", "cr_", "ag_", "f_", "tb_", "co_")
#: Tout attribut, nom, alias d'import ou mot-clé commençant par `_` est refusé (`collections._sys` donnait
#: `sys.modules` donc `os` et `builtins`). Deux exceptions, étroites : `self._x` (attribut privé d'une méthode
#: de la stratégie : `self` doit être le premier paramètre d'une méthode et n'être jamais rebondi) et le nom
#: `_` seul (variable jetable).
NOM_JETABLE = "_"
#: Noms explicitement interdits en attribut (couverts aussi par le préfixe `__`, listés pour mémoire).
DUNDERS_INTERDITS = frozenset({"__traceback__", "__code__", "__globals__", "__closure__", "__subclasses__",
                               "__mro__", "__bases__", "__class__", "__dict__", "__getattribute__"})
#: Anti-mémoire : pas de grande table de constantes dans une stratégie (elle embarquerait une mémoire du futur).
MAX_LITTERAUX_NUMERIQUES = 32
MAX_ELEMENTS_LITTERAL = 16
MAX_LONGUEUR_CHAINE = 64
#: Anti-mémoire (revue 2) : un entier littéral de 3 103 bits portait un calendrier de jours ; une centaine de
#: chaînes de 64 caractères une table. Plafonds : bits d'un littéral entier, caractères de TOUS les littéraux
#: chaîne/bytes du fichier (docstrings de module/classe/fonction exclues : elles ne sont lisibles ni par
#: `__doc__` ni par `help`, interdits, et ne sont pas des expressions utilisées).
MAX_BITS_ENTIER = 64
MAX_CARACTERES_CHAINES = 512
# Budget d'information des littéraux (hors docstrings), tous canaux confondus : bits des entiers, 64 par flottant
# ou complexe, 7 par caractère de chaîne (ASCII imposé). Les stratégies gelées de la vague 1 en utilisent au plus
# 908 ; une table (calendrier codé) en voudrait des milliers.
MAX_BITS_LITTERAUX = 1024
#: Conversions texte -> nombre interdites sur un littéral chaîne/bytes (décodage d'une table).
CONVERSIONS_INTERDITES = frozenset({"int", "float", "complex", "bytes", "bytearray", "ord"})
ATTRS_CONVERSION_INTERDITS = frozenset({"fromhex", "from_bytes", "frombuffer", "fromstring"})
LIMITE_MEMOIRE = 6 * 2**30
#: Taille du tmpfs /tmp du bac à sable (bwrap >= 0.5 connaît `--size`, avant le `--tmpfs` qu'il concerne).
TAILLE_TMPFS = 256 * 2**20
EXCEPTIONS_STANDARD = frozenset(
    k for k, v in vars(builtins).items() if isinstance(v, type) and issubclass(v, BaseException))


# ----------------------------------------------------------------------------------------------------
# Contrôle AST
# ----------------------------------------------------------------------------------------------------


def attribut_interdit(a: str) -> bool:
    """Vrai si l'attribut `a` est refusé quel que soit l'objet (l'exception `self._x` est traitée à part)."""
    return (a in ATTRS_INTERDITS or a in NOMS_INTERDITS or a in DUNDERS_INTERDITS
            or a.startswith(PREFIXES_ATTRS_INTERDITS) or a.startswith("_"))


def _nom_prive_interdit(nom: str) -> bool:
    return nom.startswith("_") and nom != NOM_JETABLE


def _est_litteral_texte(n: ast.AST) -> bool:
    return isinstance(n, ast.JoinedStr) or (isinstance(n, ast.Constant) and isinstance(n.value, (str, bytes)))


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
    # `self` autorisé : premier paramètre d'une fonction définie directement dans le corps d'une classe.
    self_permis = set()
    appels_nom = set()  # Name utilisés comme `f(...)`
    bases = set()
    classes_locales = {n.name for n in ast.walk(arbre) if isinstance(n, ast.ClassDef)}
    for n in ast.walk(arbre):
        if isinstance(n, ast.ClassDef):
            for b in n.bases:
                bases.add(id(b))
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.args.args \
                        and m.args.args[0].arg == "self" and not m.args.posonlyargs:
                    self_permis.add(id(m.args.args[0]))
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            appels_nom.add(id(n.func))
    n_numeriques = 0
    n_caracteres = 0
    n_bits = 0
    classes = {n.name for n in arbre.body if isinstance(n, ast.ClassDef)}
    if "Strategie" not in classes:
        raise SourceRefusee(f"{nom} : classe `Strategie` absente")

    def alias_ok(n, a):
        if a.asname and (a.asname in NOMS_INTERDITS or _nom_prive_interdit(a.asname) or a.asname == "self"):
            refus(n, f"alias {a.asname!r} interdit")

    def nom_ok(n, x):
        if x in NOMS_INTERDITS or _nom_prive_interdit(x) or x == "self":
            refus(n, f"nom {x!r} interdit")

    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name not in IMPORTS_PERMIS:
                    refus(n, f"import {a.name!r} interdit")
                alias_ok(n, a)
        elif isinstance(n, ast.ImportFrom):
            if n.level or (n.module or "") not in IMPORTS_PERMIS:
                refus(n, f"import depuis {n.module!r} interdit")
            for a in n.names:
                if a.name == "*" or a.name in ATTRS_INTERDITS or a.name in NOMS_INTERDITS \
                        or a.name.startswith("_") or a.name.startswith("read_"):
                    refus(n, f"import du nom {a.name!r} interdit")
                alias_ok(n, a)
        elif isinstance(n, ast.Name):
            if n.id in NOMS_INTERDITS or _nom_prive_interdit(n.id):
                refus(n, f"nom {n.id!r} interdit")
            if n.id == "self" and not isinstance(n.ctx, ast.Load):
                refus(n, "`self` ne peut pas être rebondi")
            if n.id in classes_locales and isinstance(n.ctx, ast.Load) and id(n) not in appels_nom \
                    and id(n) not in bases:
                refus(n, f"classe locale {n.id!r} utilisée autrement qu'en l'instanciant (méthode non liée)")
        elif isinstance(n, ast.Attribute):
            a = n.attr
            privee_self = (a.startswith("_") and not a.startswith("__") and isinstance(n.value, ast.Name)
                           and n.value.id == "self")
            if not privee_self and attribut_interdit(a):
                refus(n, f"attribut .{a} interdit")
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if n.name in NOMS_INTERDITS or n.name == "self" \
                    or (n.name.startswith("__") and n.name.endswith("__") and not isinstance(n, ast.ClassDef)
                        and n.name not in {"__init__", "__call__", "__repr__"}):
                refus(n, f"définition {n.name!r} interdite")
        elif isinstance(n, ast.arg):
            if n.arg in NOMS_INTERDITS or _nom_prive_interdit(n.arg) or (n.arg == "self" and id(n) not in self_permis):
                refus(n, f"argument {n.arg!r} interdit")
        elif isinstance(n, ast.keyword):
            if n.arg is not None and (n.arg.startswith("_") or n.arg in NOMS_INTERDITS):
                refus(n, f"mot-clé {n.arg!r} interdit")
        elif isinstance(n, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
            if n.name:
                nom_ok(n, n.name)
        elif isinstance(n, ast.MatchMapping):
            if n.rest:
                nom_ok(n, n.rest)
        elif isinstance(n, ast.MatchClass):
            for k in n.kwd_attrs:
                if attribut_interdit(k):
                    refus(n, f"attribut {k!r} interdit (motif de classe)")
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            for g in n.names:
                nom_ok(n, g)
        elif isinstance(n, ast.Constant):
            v = n.value
            if isinstance(v, str) and v.startswith("__") and v.endswith("__"):
                refus(n, "chaîne de type dunder interdite")
            if isinstance(v, bytes):
                refus(n, "littéral bytes interdit (table de constantes)")
            elif isinstance(v, str) and id(n) not in docstrings and not v.isascii():
                refus(n, "chaîne littérale non ASCII interdite (table de constantes)")
            if isinstance(v, int) and not isinstance(v, bool):
                n_bits += max(1, abs(v).bit_length())
                n_numeriques += 1
                if abs(v).bit_length() > MAX_BITS_ENTIER:
                    refus(n, f"entier littéral de plus de {MAX_BITS_ENTIER} bits (table de constantes)")
            elif isinstance(v, (float, complex)):
                n_bits += 64
                n_numeriques += 1
            elif isinstance(v, (str, bytes)) and id(n) not in docstrings:
                n_bits += 7 * len(v)
                n_caracteres += len(v)
                if len(v) > MAX_LONGUEUR_CHAINE:
                    refus(n, f"chaîne littérale de plus de {MAX_LONGUEUR_CHAINE} caractères (table de constantes)")
        elif isinstance(n, (ast.List, ast.Tuple, ast.Set)) and len(n.elts) > MAX_ELEMENTS_LITTERAL:
            refus(n, f"littéral de plus de {MAX_ELEMENTS_LITTERAL} éléments (table de constantes)")
        elif isinstance(n, ast.Dict) and len(n.keys) > MAX_ELEMENTS_LITTERAL:
            refus(n, f"dict littéral de plus de {MAX_ELEMENTS_LITTERAL} éléments (table de constantes)")
        if isinstance(n, ast.Call):
            f = n.func
            args = [*n.args, *(k.value for k in n.keywords)]
            if any(_est_litteral_texte(x) for x in args):
                if isinstance(f, ast.Name) and f.id in CONVERSIONS_INTERDITES:
                    refus(n, f"{f.id}() appliqué à un littéral chaîne (décodage d'une table)")
                if isinstance(f, ast.Attribute) and f.attr in ATTRS_CONVERSION_INTERDITS:
                    refus(n, f".{f.attr}() appliqué à un littéral chaîne (décodage d'une table)")
    if n_bits > MAX_BITS_LITTERAUX:
        raise SourceRefusee(f"{nom} : {n_bits} bits de littéraux (> {MAX_BITS_LITTERAUX}) : table de constantes "
                            "interdite")
    if n_numeriques > MAX_LITTERAUX_NUMERIQUES:
        raise SourceRefusee(f"{nom} : {n_numeriques} littéraux numériques (> {MAX_LITTERAUX_NUMERIQUES}) : "
                            "table de constantes interdite")
    if n_caracteres > MAX_CARACTERES_CHAINES:
        raise SourceRefusee(f"{nom} : {n_caracteres} caractères de littéraux chaîne (> {MAX_CARACTERES_CHAINES}) : "
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
        "--symlink", "usr/bin", "/bin", "--proc", "/proc", "--dev", "/dev",
        "--size", str(TAILLE_TMPFS), "--tmpfs", "/tmp",
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
#: Échauffement minimal conservé : la plus longue mémoire déclarée par une fiche est de 365 jours (funding).
#: `criteres.yaml` ne fixe aucun minimum (l'échauffement 2018-2019 « ne sert qu'à l'échauffement ») ;
#: ce plancher est celui de la plus longue fenêtre des fiches ; le retrait k ne peut donc pas descendre
#: l'échauffement sous 365 jours, et ne touche jamais la fenêtre d'évaluation.
ECHAUFFEMENT_MIN_JOURS = 365
RETRAIT_MAX_JOURS = 365  # k est tiré dans [0, 365)


def tirer_jours_retires(panneau, criteres, tirage: int | None = None) -> int:
    """Nombre k de jours retirés au début du flux, tiré par essai (`os.urandom`), dans [0, 365). Borné pour que
    l'échauffement restant (jours avant `fenetre_evaluation.debut`, à partir de la première cotation du
    panneau) reste >= `ECHAUFFEMENT_MIN_JOURS` : 0 si le panneau n'a pas assez d'échauffement. Les jours de la
    fenêtre d'évaluation ne sont jamais retirés."""
    import pandas as pd

    debut = int(pd.Timestamp(criteres.donnees.fenetre_evaluation.debut, tz="UTC").timestamp())
    n_echauffement = int(np.sum(panneau.jours < debut))
    borne = min(RETRAIT_MAX_JOURS, max(1, n_echauffement - ECHAUFFEMENT_MIN_JOURS + 1))
    # `tirage` : entier tiré une fois par famille au début de la vague (journal chaîné) ; sinon tiré ici.
    v = int.from_bytes(os.urandom(4), "big") if tirage is None else int(tirage)
    return v % borne


def tirer_decalage() -> int:
    """Décalage entier aléatoire (os.urandom) ajouté à `Jour.i` : >= 10 000, tiré par essai."""
    return DECALAGE_MIN + int.from_bytes(os.urandom(4), "big") % (1 << 24)


def executer_flux(source: bytes, params: dict, panneau, validateur, timeout_s: float,
                  verifier_ast: bool = True, jusqu_a_erreur: int | None = None,
                  decalage: int | None = None, jours_retires: int = 0) -> tuple[np.ndarray, np.ndarray, int]:
    """Envoie les jours du panneau (dans l'ordre) à la stratégie ; `validateur(i, ws, wp)` est appelé pour
    chaque jour et lève `FormePoids` si la forme est violée. Renvoie (poids_spot, poids_perp, n_jours_ok)
    avec des tableaux (T, N). Si `jusqu_a_erreur` est donné, une erreur (hors délai) n'est tolérée qu'à
    partir de ce jour (les jours suivants restent à 0 et `n_jours_ok` dit où elle s'est produite) ; sinon
    toute erreur est levée.

    Ce que voit la stratégie : le panneau REBASÉ (`Panneau.rebaser` : prix ÷ premier close de la paire,
    volumes ÷ volume moyen des 30 premiers jours cotés, causal) et un index de jour `Jour.i = décalage + k`
    où `décalage` (>= 10 000) est tiré par appel : elle peut compter les jours, pas en déduire la date.
    Le moteur calcule les rendements sur les prix réels (`portefeuille.simuler`), jamais sur ce panneau.
    `jours_retires` (k >= 0) : les k premiers jours du panneau (échauffement) ne sont PAS envoyés à la
    stratégie ; leurs poids valent 0 et `validateur`/`n_jours_ok`/`jusqu_a_erreur` gardent les indices du
    panneau complet. Le moteur tire k par essai (`tirer_jours_retires`) : sans cela, `Jour.i - Jour.i_0` donne
    la date par simple compte de jours depuis le début des données, publiques.
    Le détail des erreurs ne contient aucun texte de la stratégie : le type d'exception standard et le jour."""
    if verifier_ast:
        verifier_source(source.decode("utf-8", "replace"))
    T, N = panneau.n_jours, panneau.n_paires
    if decalage is None:
        decalage = tirer_decalage()
    k = int(jours_retires)
    if not 0 <= k < T:
        raise ValueError(f"jours_retires={k} hors de [0, {T})")
    vue = panneau.retirer_debut(k).rebaser()
    ws = np.zeros((T, N))
    wp = np.zeros((T, N))
    n_ok = k
    with Worker(source, N, params, timeout_s) as w:
        for i in range(k, T):
            try:
                a, b = w.pas(dataclasses.replace(vue.jour(i - k), i=decalage + i - k))
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
