"""Processus worker : exécute UNE stratégie, un jour à la fois, dans le bac à sable `bwrap`.

Lancé par `bac_a_sable.py` en `python -I -B /job/_worker.py` (cwd /tmp, aucune variable d'environnement
héritée). Dialogue par stdin/stdout, trames `uint32 longueur + charge utile`.

    parent -> worker : pickle de ("init", n_paires, params) | ("jour", i, spot_1d, spot_1h, perp_1h,
                       funding, eligibles, eligibles_perp) | ("fin",)
    worker -> parent : 1 octet de statut puis, selon le statut :
                       0 = poids : 2 x n_paires float64 (spot puis perp), 2 = prêt (vide),
                       1 = erreur de la stratégie (texte), 3 = sortie mal formée (texte)

Le parent ne désérialise JAMAIS (pickle) ce que le worker écrit : seuls des octets bruts et du texte.
Ce fichier n'importe ni le dépôt ni `arene`. Il est copié tel quel dans le bac à sable.
"""

import builtins
import os
import pickle
import resource
import struct
import sys
import traceback

IMPORTS_PERMIS = frozenset({"math", "statistics", "numpy", "collections", "itertools", "functools", "heapq",
                            "bisect"})
BANNIS = frozenset({"open", "exec", "eval", "compile", "getattr", "setattr", "delattr", "globals", "locals",
                    "vars", "input", "breakpoint", "memoryview", "exit", "quit", "help", "license",
                    "credits", "copyright"})
INTERDITS_RUNTIME = frozenset({"os", "sys", "socket", "_socket", "subprocess", "ctypes", "_ctypes", "importlib",
                               "pathlib", "shutil", "tempfile", "builtins", "posix", "pickle", "marshal",
                               "urllib", "http", "multiprocessing", "asyncio", "signal", "select", "mmap",
                               "fcntl", "pty", "resource", "time", "datetime", "random", "io"})
ST_POIDS, ST_ERREUR, ST_PRET, ST_FORME = 0, 1, 2, 3


class _Sortie:
    def __init__(self, fd):
        self.f = os.fdopen(fd, "wb", buffering=0)

    def trame(self, statut, charge=b""):
        corps = bytes([statut]) + charge
        self.f.write(struct.pack("<I", len(corps)) + corps)


def _lire_exact(f, n):
    b = f.read(n)
    if b is None or len(b) < n:
        raise EOFError
    return b


def main():
    modules_dir, venv_dir, job_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    lim_as = int(sys.argv[4])
    resource.setrlimit(resource.RLIMIT_AS, (lim_as, lim_as))
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 2**20, 32 * 2**20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # stdin/stdout du processus deviennent privés ; fd 0/1 sont rebranchés sur /dev/null pour la stratégie.
    entree = os.fdopen(os.dup(0), "rb", buffering=1 << 20)
    sortie = _Sortie(os.dup(1))
    nul = os.open(os.devnull, os.O_RDWR)
    os.dup2(nul, 0)
    os.dup2(nul, 1)
    sys.stdout = sys.stderr = open(os.devnull, "w")  # noqa: SIM115
    sys.path.insert(0, venv_dir)
    sys.path.insert(0, modules_dir)
    import numpy as np

    vrai_import = builtins.__import__

    def import_restreint(name, globals=None, locals=None, fromlist=(), level=0):
        # Imports écrits dans strategie.py : liste blanche (le contrôle AST l'impose déjà). Imports internes
        # de numpy, faits depuis du code C avec les globals de la stratégie : tout sauf les modules dangereux.
        haut = name.split(".")[0]
        if level or haut in INTERDITS_RUNTIME or (globals is not None and globals.get("__name__") == "strategie"
                                                  and name not in IMPORTS_PERMIS and haut != "numpy"):
            raise ImportError(f"import {name!r} interdit")
        return vrai_import(name, globals, locals, fromlist, level)

    surs = {k: v for k, v in vars(builtins).items() if k not in BANNIS}
    surs["__import__"] = import_restreint
    from contrat import Jour  # copié dans /job

    with builtins.open(os.path.join(job_dir, "strategie.py"), encoding="utf-8") as f:
        source = f.read()
    ns = {"__builtins__": surs, "__name__": "strategie"}
    strategie = None
    n = 0
    try:
        code = builtins.compile(source, "strategie.py", "exec")
        builtins.exec(code, ns)  # noqa: S102
    except BaseException:  # noqa: BLE001
        sortie.trame(ST_ERREUR, traceback.format_exc()[-1500:].encode("utf-8", "replace"))
        return 0
    while True:
        try:
            (taille,) = struct.unpack("<I", _lire_exact(entree, 4))
            msg = pickle.loads(_lire_exact(entree, taille))
        except EOFError:
            return 0
        genre = msg[0]
        if genre == "fin":
            return 0
        try:
            if genre == "init":
                n, params = msg[1], msg[2]
                strategie = ns["Strategie"](n, **params)
                sortie.trame(ST_PRET)
                continue
            _, i, s1d, s1h, p1h, funding, elig, elp = msg
            res = strategie.pas(Jour(i=i, spot_1d=s1d, spot_1h=s1h, perp_1h=p1h, funding=funding,
                                     eligibles=elig, eligibles_perp=elp))
        except BaseException:  # noqa: BLE001
            sortie.trame(ST_ERREUR, traceback.format_exc()[-1500:].encode("utf-8", "replace"))
            return 0
        try:
            if isinstance(res, tuple) and len(res) == 2:
                ws, wp = np.array(res[0], dtype=np.float64), np.array(res[1], dtype=np.float64)
            else:
                ws, wp = np.array(res, dtype=np.float64), np.zeros(n)
            if ws.shape != (n,) or wp.shape != (n,):
                raise ValueError(f"formes {ws.shape} {wp.shape}, ({n},) attendu")
        except BaseException as e:  # noqa: BLE001
            sortie.trame(ST_FORME, f"{type(e).__name__}: {e}"[:500].encode("utf-8", "replace"))
            return 0
        sortie.trame(ST_POIDS, ws.tobytes() + wp.tobytes())


if __name__ == "__main__":
    try:
        code_sortie = main()
    except BaseException:  # noqa: BLE001
        code_sortie = 70
    os._exit(code_sortie)
