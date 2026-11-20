"""Worker process: runs ONE strategy, one day at a time, inside the `bwrap` sandbox.

Launched by `sandbox.py` as `python -I -B /job/_worker.py` (cwd /tmp, no inherited environment variable).
Talks over stdin/stdout with frames `uint32 length + payload`.

    parent -> worker : pickle of ("init", n_pairs, params) | ("day", i, spot_1d, spot_1h, perp_1h,
                       funding, eligibles, eligibles_perp) | ("end",)
    worker -> parent : 1 status byte, then, depending on the status:
                       0 = weights: 2 x n_pairs float64 (spot then perp), 2 = ready (empty),
                       1 = strategy error, 3 = malformed output: the payload is the NAME of the exception
                       type only (never a message or a trace: output channel)

The parent NEVER deserializes (pickle) what the worker writes: only raw bytes and text.
This file imports neither the repository nor `arena`. It is copied as is into the sandbox.
"""

import builtins
import os
import pickle
import resource
import struct
import sys

IMPORTS_ALLOWED = frozenset({"math", "statistics", "numpy", "collections", "itertools", "functools", "heapq",
                            "bisect"})
BANNED = frozenset({"open", "exec", "eval", "compile", "getattr", "setattr", "delattr", "globals", "locals",
                    "vars", "input", "breakpoint", "memoryview", "exit", "quit", "help", "license",
                    "credits", "copyright"})
FORBIDDEN_RUNTIME = frozenset({"os", "sys", "socket", "_socket", "subprocess", "ctypes", "_ctypes", "importlib",
                               "pathlib", "shutil", "tempfile", "builtins", "posix", "pickle", "marshal",
                               "urllib", "http", "multiprocessing", "asyncio", "signal", "select", "mmap",
                               "fcntl", "pty", "resource", "time", "datetime", "random", "io"})
ST_WEIGHT, ST_ERROR, ST_READY, ST_SHAPE = 0, 1, 2, 3


class _Output:
    def __init__(self, fd):
        self.f = os.fdopen(fd, "wb", buffering=0)

    def frame(self, status, payload=b""):
        body = bytes([status]) + payload
        self.f.write(struct.pack("<I", len(body)) + body)


def _read_exact(f, n):
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
    # The process's stdin/stdout become private; fd 0/1 are redirected to /dev/null for the strategy.
    stdin_pipe = os.fdopen(os.dup(0), "rb", buffering=1 << 20)
    output = _Output(os.dup(1))
    devnull_fd = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull_fd, 0)
    os.dup2(devnull_fd, 1)
    sys.stdout = sys.stderr = open(os.devnull, "w")  # noqa: SIM115
    sys.path.insert(0, venv_dir)
    sys.path.insert(0, modules_dir)
    import numpy as np

    true_import = builtins.__import__

    def restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
        # Imports written in strategy.py: allowlist (the AST check already enforces it). Internal numpy
        # imports, made from C code with the strategy's globals: everything except the dangerous modules.
        top = name.split(".")[0]
        if level or top in FORBIDDEN_RUNTIME or (globals is not None and globals.get("__name__") == "strategy"
                                                  and name not in IMPORTS_ALLOWED and top != "numpy"):
            raise ImportError(f"import {name!r} forbidden")
        return true_import(name, globals, locals, fromlist, level)

    safe = {k: v for k, v in vars(builtins).items() if k not in BANNED}
    safe["__import__"] = restricted_import
    from contract import Day  # copied into /job

    with builtins.open(os.path.join(job_dir, "strategy.py"), encoding="utf-8") as f:
        source = f.read()
    ns = {"__builtins__": safe, "__name__": "strategy"}
    strategy = None
    n = 0
    try:
        code = builtins.compile(source, "strategy.py", "exec")
        builtins.exec(code, ns)  # noqa: S102
    except BaseException as e:  # noqa: BLE001
        output.frame(ST_ERROR, type(e).__name__[:64].encode("utf-8", "replace"))
        return 0
    while True:
        try:
            (size,) = struct.unpack("<I", _read_exact(stdin_pipe, 4))
            msg = pickle.loads(_read_exact(stdin_pipe, size))
        except EOFError:
            return 0
        category = msg[0]
        if category == "end":
            return 0
        try:
            if category == "init":
                n, params = msg[1], msg[2]
                strategy = ns["Strategy"](n, **params)
                output.frame(ST_READY)
                continue
            _, i, s1d, s1h, p1h, funding, elig, elp = msg
            res = strategy.step(Day(i=i, spot_1d=s1d, spot_1h=s1h, perp_1h=p1h, funding=funding,
                                     eligibles=elig, eligibles_perp=elp))
        except BaseException as e:  # noqa: BLE001
            output.frame(ST_ERROR, type(e).__name__[:64].encode("utf-8", "replace"))
            return 0
        try:
            if isinstance(res, tuple) and len(res) == 2:
                ws, wp = np.array(res[0], dtype=np.float64), np.array(res[1], dtype=np.float64)
            else:
                ws, wp = np.array(res, dtype=np.float64), np.zeros(n)
            if ws.shape != (n,) or wp.shape != (n,):
                raise ValueError(f"shapes {ws.shape} {wp.shape}, ({n},) expected")
        except BaseException as e:  # noqa: BLE001
            output.frame(ST_SHAPE, type(e).__name__[:64].encode("utf-8", "replace"))
            return 0
        output.frame(ST_WEIGHT, ws.tobytes() + wp.tobytes())


if __name__ == "__main__":
    try:
        exit_code = main()
    except BaseException:  # noqa: BLE001
        exit_code = 70
    os._exit(exit_code)
