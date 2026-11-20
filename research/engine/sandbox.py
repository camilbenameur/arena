"""Strategy execution sandbox: AST check, worker under `bwrap`, pipe-based dialogue.

Defense in depth, from weakest to strongest:
1. AST check of the exact text executed (import allowlist, forbidden names and attributes);
2. restricted builtins in the worker (no `open`, `exec`, free `__import__`);
3. `bwrap --unshare-all`: no network, no `$HOME`, no repository; `/usr` and the numpy library read-only,
   a tmpfs for `/tmp`, `--die-with-parent`, no capability;
4. hard timeout (watchdog) and resource limits in the worker.
The parent never deserializes (pickle) what the worker writes.
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

from research.engine import contract
from research.engine.contract import (
    DelayExceeded,
    TrialError,
    WeightShape,
    SourceRefused,
)

_DIR = Path(__file__).resolve().parent
IMPORTS_ALLOWED = frozenset({"math", "statistics", "numpy", "collections", "itertools", "functools", "heapq",
                            "bisect"})
FORBIDDEN_NAMES = frozenset({
    "dir", "type", "open", "exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr", "globals", "locals",
    "vars", "input", "breakpoint", "memoryview", "exit", "quit", "help", "time", "datetime", "random", "os",
    "sys", "socket", "subprocess", "pathlib", "importlib", "builtins", "ctypes"})
FORBIDDEN_ATTRS = frozenset({
    "open", "exec", "eval", "compile", "load", "save", "savez", "savez_compressed", "savetxt", "loadtxt",
    "genfromtxt", "fromfile", "tofile", "fromregex", "memmap", "DataSource", "ctypeslib", "f2py", "testing",
    "system", "popen", "random", "os", "sys", "subprocess", "socket", "time", "datetime", "pathlib",
    "importlib", "ctypes", "builtins", "lib", "core", "_core", "fromstring",
    # Remaining file I/O of numpy / ndarray (review 2): writing a file with `arr.dump(path)`, etc.
    "dump", "dumps", "loads", "test", "show_config", "show_runtime", "info", "source", "get_include",
    "distutils", "compat", "array_api",
    # numpy submodules that expose modules outside the allowlist (`np.char.overrides.inspect.os`,
    # `np.ma.extras.ma.operator`...): found by traversal (`test_review2_engine::test_no_attribute_path_to_a_module_outside_the_whitelist`).
    "ma", "char", "rec", "overrides", "extras", "mrecords", "matlib", "matrixlib",
    "inspect", "operator", "re", "textwrap", "warnings", "numbers", "dt", "types", "typing"})
#: Forbidden attribute prefixes: internals of generators/coroutines/frames/tracebacks/code (gi_frame, cr_frame,
#: ag_frame, f_back, f_locals, f_globals, tb_frame, co_code...) that allow escaping the restricted builtins.
FORBIDDEN_ATTR_PREFIXES = ("read_", "__", "gi_", "cr_", "ag_", "f_", "tb_", "co_")
#: Any attribute, name, import alias or keyword starting with `_` is refused (`collections._sys` gave
#: `sys.modules` hence `os` and `builtins`). Two narrow exceptions: `self._x` (private attribute of a method
#: of the strategy: `self` must be the first parameter of a method and never rebound) and the bare name
#: `_` (throwaway variable).
THROWAWAY_NAME = "_"
#: Names explicitly forbidden as attributes (also covered by the `__` prefix, listed for the record).
FORBIDDEN_DUNDERS = frozenset({"__traceback__", "__code__", "__globals__", "__closure__", "__subclasses__",
                               "__mro__", "__bases__", "__class__", "__dict__", "__getattribute__"})
#: Anti-memorization: no large constant table in a strategy (it would embed a memory of the future).
MAX_NUMERIC_LITERALS = 32
MAX_LITERAL_ELEMENTS = 16
MAX_STRING_LENGTH = 64
#: Anti-memorization (review 2): an integer literal of 3,103 bits carried a calendar of days; a hundred
#: 64-character strings a table. Caps: bits of an integer literal, characters of ALL string/bytes literals
#: of the file (module/class/function docstrings excluded: they are readable neither through
#: `__doc__` nor `help`, both forbidden, and are not used expressions).
MAX_INTEGER_BITS = 64
MAX_STRING_CHARS = 512
# Information budget of the literals (docstrings excluded), all channels combined: bits of integers, 64 per float
# or complex, 7 per string character (ASCII enforced). The frozen wave-1 strategies use at most
# 908; a table (encoded calendar) would need thousands.
MAX_LITERAL_BITS = 1024
#: Text -> number conversions forbidden on a string/bytes literal (decoding a table).
FORBIDDEN_CONVERSIONS = frozenset({"int", "float", "complex", "bytes", "bytearray", "ord"})
FORBIDDEN_CONVERSION_ATTRS = frozenset({"fromhex", "from_bytes", "frombuffer", "fromstring"})
MEMORY_LIMIT = 6 * 2**30
#: Size of the sandbox's /tmp tmpfs (bwrap >= 0.5 knows `--size`, placed before the `--tmpfs` it applies to).
TMPFS_SIZE = 256 * 2**20
EXCEPTIONS_STANDARD = frozenset(
    k for k, v in vars(builtins).items() if isinstance(v, type) and issubclass(v, BaseException))


# ----------------------------------------------------------------------------------------------------
# AST check
# ----------------------------------------------------------------------------------------------------


def forbidden_attribute(a: str) -> bool:
    """True if attribute `a` is refused whatever the object (the `self._x` exception is handled separately)."""
    return (a in FORBIDDEN_ATTRS or a in FORBIDDEN_NAMES or a in FORBIDDEN_DUNDERS
            or a.startswith(FORBIDDEN_ATTR_PREFIXES) or a.startswith("_"))


def _forbidden_private_name(name: str) -> bool:
    return name.startswith("_") and name != THROWAWAY_NAME


def _is_text_literal(n: ast.AST) -> bool:
    return isinstance(n, ast.JoinedStr) or (isinstance(n, ast.Constant) and isinstance(n.value, (str, bytes)))


def verify_source(text: str, name: str = "strategy.py") -> None:
    """Raises `SourceRefused` if the text violates the allowlist. Checks the exact text that will be executed."""
    try:
        tree = ast.parse(text, filename=name)
    except (SyntaxError, ValueError) as e:
        raise SourceRefused(f"{name}: syntax: {e}") from None

    def refused(n, reason):
        raise SourceRefused(f"{name} line {getattr(n, 'lineno', '?')}: {reason}")

    docstrings = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body \
                and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant) \
                and isinstance(n.body[0].value.value, str):
            docstrings.add(id(n.body[0].value))
    # `self` allowed: first parameter of a function defined directly in a class body.
    self_allowed = set()
    name_calls = set()  # Names used as `f(...)`
    bases = set()
    local_classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef):
            for b in n.bases:
                bases.add(id(b))
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.args.args \
                        and m.args.args[0].arg == "self" and not m.args.posonlyargs:
                    self_allowed.add(id(m.args.args[0]))
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            name_calls.add(id(n.func))
    n_numeric = 0
    n_characters = 0
    n_bits = 0
    classes = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
    if "Strategy" not in classes:
        raise SourceRefused(f"{name}: class `Strategy` missing")

    def alias_ok(n, a):
        if a.asname and (a.asname in FORBIDDEN_NAMES or _forbidden_private_name(a.asname) or a.asname == "self"):
            refused(n, f"alias {a.asname!r} forbidden")

    def name_ok(n, x):
        if x in FORBIDDEN_NAMES or _forbidden_private_name(x) or x == "self":
            refused(n, f"name {x!r} forbidden")

    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name not in IMPORTS_ALLOWED:
                    refused(n, f"import {a.name!r} forbidden")
                alias_ok(n, a)
        elif isinstance(n, ast.ImportFrom):
            if n.level or (n.module or "") not in IMPORTS_ALLOWED:
                refused(n, f"import from {n.module!r} forbidden")
            for a in n.names:
                if a.name == "*" or a.name in FORBIDDEN_ATTRS or a.name in FORBIDDEN_NAMES \
                        or a.name.startswith("_") or a.name.startswith("read_"):
                    refused(n, f"import of name {a.name!r} forbidden")
                alias_ok(n, a)
        elif isinstance(n, ast.Name):
            if n.id in FORBIDDEN_NAMES or _forbidden_private_name(n.id):
                refused(n, f"name {n.id!r} forbidden")
            if n.id == "self" and not isinstance(n.ctx, ast.Load):
                refused(n, "`self` cannot be rebound")
            if n.id in local_classes and isinstance(n.ctx, ast.Load) and id(n) not in name_calls \
                    and id(n) not in bases:
                refused(n, f"local class {n.id!r} used other than by instantiating it (unbound method)")
        elif isinstance(n, ast.Attribute):
            a = n.attr
            self_private = (a.startswith("_") and not a.startswith("__") and isinstance(n.value, ast.Name)
                           and n.value.id == "self")
            if not self_private and forbidden_attribute(a):
                refused(n, f"attribute .{a} forbidden")
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if n.name in FORBIDDEN_NAMES or n.name == "self" \
                    or (n.name.startswith("__") and n.name.endswith("__") and not isinstance(n, ast.ClassDef)
                        and n.name not in {"__init__", "__call__", "__repr__"}):
                refused(n, f"definition {n.name!r} forbidden")
        elif isinstance(n, ast.arg):
            if n.arg in FORBIDDEN_NAMES or _forbidden_private_name(n.arg) or (n.arg == "self" and id(n) not in self_allowed):
                refused(n, f"argument {n.arg!r} forbidden")
        elif isinstance(n, ast.keyword):
            if n.arg is not None and (n.arg.startswith("_") or n.arg in FORBIDDEN_NAMES):
                refused(n, f"keyword {n.arg!r} forbidden")
        elif isinstance(n, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
            if n.name:
                name_ok(n, n.name)
        elif isinstance(n, ast.MatchMapping):
            if n.rest:
                name_ok(n, n.rest)
        elif isinstance(n, ast.MatchClass):
            for k in n.kwd_attrs:
                if forbidden_attribute(k):
                    refused(n, f"attribute {k!r} forbidden (class pattern)")
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            for g in n.names:
                name_ok(n, g)
        elif isinstance(n, ast.Constant):
            v = n.value
            if isinstance(v, str) and v.startswith("__") and v.endswith("__"):
                refused(n, "dunder-style string forbidden")
            if isinstance(v, bytes):
                refused(n, "bytes literal forbidden (constant table)")
            elif isinstance(v, str) and id(n) not in docstrings and not v.isascii():
                refused(n, "non-ASCII string literal forbidden (constant table)")
            if isinstance(v, int) and not isinstance(v, bool):
                n_bits += max(1, abs(v).bit_length())
                n_numeric += 1
                if abs(v).bit_length() > MAX_INTEGER_BITS:
                    refused(n, f"integer literal of more than {MAX_INTEGER_BITS} bits (constant table)")
            elif isinstance(v, (float, complex)):
                n_bits += 64
                n_numeric += 1
            elif isinstance(v, (str, bytes)) and id(n) not in docstrings:
                n_bits += 7 * len(v)
                n_characters += len(v)
                if len(v) > MAX_STRING_LENGTH:
                    refused(n, f"string literal of more than {MAX_STRING_LENGTH} characters (constant table)")
        elif isinstance(n, (ast.List, ast.Tuple, ast.Set)) and len(n.elts) > MAX_LITERAL_ELEMENTS:
            refused(n, f"literal of more than {MAX_LITERAL_ELEMENTS} elements (constant table)")
        elif isinstance(n, ast.Dict) and len(n.keys) > MAX_LITERAL_ELEMENTS:
            refused(n, f"dict literal of more than {MAX_LITERAL_ELEMENTS} elements (constant table)")
        if isinstance(n, ast.Call):
            f = n.func
            args = [*n.args, *(k.value for k in n.keywords)]
            if any(_is_text_literal(x) for x in args):
                if isinstance(f, ast.Name) and f.id in FORBIDDEN_CONVERSIONS:
                    refused(n, f"{f.id}() applied to a string literal (table decoding)")
                if isinstance(f, ast.Attribute) and f.attr in FORBIDDEN_CONVERSION_ATTRS:
                    refused(n, f".{f.attr}() applied to a string literal (table decoding)")
    if n_bits > MAX_LITERAL_BITS:
        raise SourceRefused(f"{name}: {n_bits} bits of literals (> {MAX_LITERAL_BITS}): constant table "
                            "forbidden")
    if n_numeric > MAX_NUMERIC_LITERALS:
        raise SourceRefused(f"{name}: {n_numeric} numeric literals (> {MAX_NUMERIC_LITERALS}): "
                            "constant table forbidden")
    if n_characters > MAX_STRING_CHARS:
        raise SourceRefused(f"{name}: {n_characters} characters of string literals (> {MAX_STRING_CHARS}): "
                            "constant table forbidden")


# ----------------------------------------------------------------------------------------------------
# bwrap
# ----------------------------------------------------------------------------------------------------


def bwrap_available() -> bool:
    return shutil.which("bwrap") is not None


def _site_packages() -> str:
    return str(Path(np.__file__).resolve().parent.parent)


def _bwrap_command(job: str, script: str, args: list[str]) -> list[str]:
    exe = os.path.realpath(sys.executable)
    cmd = [
        "bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL", "--clearenv",
        "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
        "--symlink", "usr/bin", "/bin", "--proc", "/proc", "--dev", "/dev",
        "--size", str(TMPFS_SIZE), "--tmpfs", "/tmp",
    ]
    prefix = os.path.realpath(sys.base_prefix)
    if not exe.startswith("/usr/") and not (prefix + "/").startswith("/usr/"):
        cmd += ["--ro-bind", prefix, prefix]  # interpreter outside /usr (python managed by uv)
    cmd += [
        "--ro-bind", _site_packages(), "/venv", "--ro-bind", job, "/job", "--chdir", "/tmp",
        "--setenv", "PATH", "/usr/bin", "--setenv", "LANG", "C.UTF-8", "--setenv", "PYTHONHASHSEED", "0",
        "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--setenv", "OMP_NUM_THREADS", "1",
        "--setenv", "OPENBLAS_NUM_THREADS", "1", "--setenv", "MKL_NUM_THREADS", "1",
        exe, "-I", "-B", f"/job/{script}", *args,
    ]
    return cmd


def _prepare_job(source: bytes | None, script: str, script_text: str | None = None) -> str:
    job = tempfile.mkdtemp(prefix="research-bin-")
    os.chmod(job, 0o700)
    shutil.copy(_DIR / "contract.py", Path(job) / "contract.py")
    if script_text is None:
        shutil.copy(_DIR / script, Path(job) / script)
    else:
        (Path(job) / script).write_text(script_text, encoding="utf-8")
    if source is not None:
        (Path(job) / "strategy.py").write_bytes(source)
    for p in Path(job).iterdir():
        p.chmod(0o444)
    return job


# ----------------------------------------------------------------------------------------------------
# Worker
# ----------------------------------------------------------------------------------------------------


class Worker:
    """A worker process under bwrap. Usage: `with Worker(source, n, params, timeout) as w: w.step(...)`."""

    def __init__(self, source: bytes, n_pairs: int, params: dict, timeout_s: float):
        if not bwrap_available():
            raise TrialError("bwrap not found: execution refused")
        self.n = n_pairs
        self.params = params
        self.timeout_s = timeout_s
        self.source = source
        self.job: str | None = None
        self.proc: subprocess.Popen | None = None
        self.timed_out = False
        self._timer: threading.Timer | None = None

    def __enter__(self) -> Self:
        self.job = _prepare_job(self.source, "_worker.py")
        self.proc = subprocess.Popen(
            _bwrap_command(self.job, "_worker.py", ["/job", "/venv", "/job", str(MEMORY_LIMIT)]),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
            bufsize=0)
        self._timer = threading.Timer(self.timeout_s, self._kill)
        self._timer.daemon = True
        self._timer.start()
        self._send(("init", self.n, self.params))
        status, payload = self._receive()
        if status != 2:
            self._failure(status, payload)
        return self

    def __exit__(self, *exc) -> None:
        if self._timer:
            self._timer.cancel()
        if self.proc is not None:
            try:
                if self.proc.poll() is None:
                    try:
                        self._send(("end",))
                    except TrialError:
                        pass
                    try:
                        self.proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self._kill()
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

    def _kill(self) -> None:
        self.timed_out = True
        try:
            os.killpg(self.proc.pid, 9)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            self.proc.kill()
        except ProcessLookupError:
            pass

    def _send(self, obj) -> None:
        data = pickle.dumps(obj, protocol=5)
        try:
            self.proc.stdin.write(struct.pack("<I", len(data)) + data)
        except (BrokenPipeError, OSError):
            self._dead()

    def _read(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self.proc.stdout.read(n - len(buf))
            if not chunk:
                self._dead()
            buf += chunk
        return bytes(buf)

    def _dead(self):
        if self.timed_out:
            raise DelayExceeded(f"timeout of {self.timeout_s:.0f} s exceeded")
        code = self.proc.poll()
        raise TrialError(f"worker dead (code {code})")

    def _receive(self) -> tuple[int, bytes]:
        (size,) = struct.unpack("<I", self._read(4))
        if size < 1 or size > 16 * 2**20:
            raise TrialError(f"frame of {size} bytes refused")
        body = self._read(size)
        return body[0], body[1:]

    def _failure(self, status: int, payload: bytes):
        """No text coming from the strategy gets through: only the exception type, and only if it is
        a standard exception (a class name chosen by the strategy would be a channel)."""
        name = payload.decode("utf-8", "replace")
        if name not in EXCEPTIONS_STANDARD:
            name = "non_standard_exception"
        if status == 3:
            raise WeightShape(f"malformed output ({name})")
        raise TrialError(f"strategy error ({name})")

    def step(self, day) -> tuple[np.ndarray, np.ndarray]:
        self._send(("day", day.i, day.spot_1d, day.spot_1h, day.perp_1h, day.funding,
                       day.eligibles, day.eligibles_perp))
        status, payload = self._receive()
        if status != 0:
            self._failure(status, payload)
        if len(payload) != 16 * self.n:
            raise TrialError(f"payload of {len(payload)} bytes, {16 * self.n} expected")
        v = np.frombuffer(payload, dtype="<f8")
        return v[: self.n].copy(), v[self.n:].copy()


OFFSET_MIN = 10_000
#: Minimum warm-up kept: the longest memory declared by a sheet is 365 days (funding).
#: `criteria.yaml` sets no minimum (the 2018-2019 warm-up "only serves as warm-up");
#: this floor is that of the longest window among the sheets; the withdrawal k therefore cannot bring
#: the warm-up below 365 days, and never touches the evaluation window.
WARMUP_MIN_DAYS = 365
WITHDRAWAL_MAX_DAYS = 365  # k is drawn in [0, 365)


def draw_days_withdrawn(panel, criteria, draw: int | None = None) -> int:
    """Number k of days withdrawn at the start of the stream, drawn per trial (`os.urandom`), in [0, 365). Bounded so that
    the remaining warm-up (days before `evaluation_window.start`, counted from the first listing of the
    panel) stays >= `WARMUP_MIN_DAYS`: 0 if the panel does not have enough warm-up. The days of the
    evaluation window are never withdrawn."""
    import pandas as pd

    start = int(pd.Timestamp(criteria.data.evaluation_window.start, tz="UTC").timestamp())
    n_warmup = int(np.sum(panel.days < start))
    bound = min(WITHDRAWAL_MAX_DAYS, max(1, n_warmup - WARMUP_MIN_DAYS + 1))
    # `draw`: integer drawn once per family at the start of the wave (hash-chained journal); otherwise drawn here.
    v = int.from_bytes(os.urandom(4), "big") if draw is None else int(draw)
    return v % bound


def draw_offset() -> int:
    """Random integer offset (os.urandom) added to `Day.i`: >= 10,000, drawn per trial."""
    return OFFSET_MIN + int.from_bytes(os.urandom(4), "big") % (1 << 24)


def run_stream(source: bytes, params: dict, panel, validator, timeout_s: float,
                  verify_ast: bool = True, until_error: int | None = None,
                  offset: int | None = None, days_withdrawn: int = 0) -> tuple[np.ndarray, np.ndarray, int]:
    """Sends the days of the panel (in order) to the strategy; `validator(i, ws, wp)` is called for
    each day and raises `WeightShape` if the shape is violated. Returns (spot_weights, perp_weights, n_ok_days)
    as (T, N) arrays. If `until_error` is given, an error (other than a timeout) is tolerated only from
    that day on (the following days stay at 0 and `n_ok_days` says where it occurred); otherwise
    every error is raised.

    What the strategy sees: the REBASED panel (`Panel.rebase`: price / the pair's first close,
    volume / mean volume of the first 30 listed days, causal) and a day index `Day.i = offset + k`
    where `offset` (>= 10,000) is drawn per call: it can count days, not deduce the date from them.
    The engine computes returns on the real prices (`portfolio.simulate`), never on this panel.
    `days_withdrawn` (k >= 0): the first k days of the panel (warm-up) are NOT sent to the
    strategy; their weights are 0 and `validator`/`n_ok_days`/`until_error` keep the indices of the
    full panel. The engine draws k per trial (`draw_days_withdrawn`): without it, `Day.i - Day.i_0` gives
    the date by simply counting days from the start of the (public) data.
    Error details contain no text from the strategy: only the standard exception type and the day."""
    if verify_ast:
        verify_source(source.decode("utf-8", "replace"))
    T, N = panel.n_days, panel.n_pairs
    if offset is None:
        offset = draw_offset()
    k = int(days_withdrawn)
    if not 0 <= k < T:
        raise ValueError(f"days_withdrawn={k} outside [0, {T})")
    view = panel.trim_start(k).rebase()
    ws = np.zeros((T, N))
    wp = np.zeros((T, N))
    n_ok = k
    with Worker(source, N, params, timeout_s) as w:
        for i in range(k, T):
            try:
                a, b = w.step(dataclasses.replace(view.day(i - k), i=offset + i - k))
                validator(i, a, b)
            except TrialError as e:
                if "day" not in e.detail:
                    e.detail = f"{e.detail} (day {i})"
                if isinstance(e, DelayExceeded) or until_error is None or i < until_error:
                    raise
                break
            ws[i], wp[i] = a, b
            n_ok = i + 1
    return ws, wp, n_ok


# ----------------------------------------------------------------------------------------------------
# Canary
# ----------------------------------------------------------------------------------------------------

_CANARY_SCRIPT = r'''
import json, os, sys, socket
sys.path.insert(0, "/venv")
cfg = json.loads(sys.argv[1])
output = {}

def attempt(name, f):
    try:
        f()
        output[name] = True      # the forbidden action SUCCEEDED
    except BaseException as e:
        output[name] = False

def connect_loopback():
    s = socket.socket(); s.settimeout(2); s.connect(("127.0.0.1", cfg["port"])); s.close()
def connect_external():
    s = socket.socket(); s.settimeout(2); s.connect(("1.1.1.1", 53)); s.close()
def read_home():
    open(cfg["home_file"], "rb").read()
def read_decoy():
    open(cfg["decoy_read"], "rb").read()
def write_repo():
    open(cfg["repo_write"], "w").write("x")
def write_usr():
    open("/usr/canary-x", "w").write("x")
def write_job():
    open("/job/canary-x", "w").write("x")
def list_home():
    if os.path.exists(cfg["home"]) and os.listdir(cfg["home"]):
        return
    raise OSError
def list_repo():
    if os.path.exists(cfg["repo"]) and os.listdir(cfg["repo"]):
        return
    raise OSError
for name, f in [("connect_loopback", connect_loopback), ("connect_external", connect_external),
               ("read_bashrc", read_home), ("read_outside_allowlist", read_decoy),
               ("write_repo", write_repo), ("write_usr", write_usr), ("write_job", write_job),
               ("list_home", list_home), ("list_repo", list_repo)]:
    attempt(name, f)
benchmarks = {}
try:
    open("/tmp/ok", "w").write("ok"); benchmarks["tmp_write"] = open("/tmp/ok").read() == "ok"
except BaseException:
    benchmarks["tmp_write"] = False
try:
    import numpy as np; benchmarks["numpy"] = float(np.arange(4).sum()) == 6.0
except BaseException:
    benchmarks["numpy"] = False
os.write(1, (json.dumps({"forbidden_succeeded": output, "benchmarks": benchmarks}) + "\n").encode())
'''

_canary_ok = False
_canary_lock = threading.Lock()


class CanaryError(Exception):
    """The sandbox lets a forbidden action through (or does not work): the engine refuses to start."""


def canary(force: bool = False, *, repo: Path | None = None) -> None:
    """Launches a test worker that attempts connect(), reads outside the allowlist and writes outside the tmpfs.
    Raises `CanaryError` if any of these actions succeeds, or if the control checks (write to /tmp, numpy) fail."""
    global _canary_ok
    with _canary_lock:
        if _canary_ok and not force:
            return
        if not bwrap_available():
            raise CanaryError("bwrap not found")
        repo = repo or _DIR.parents[1]
        home = Path.home()
        decoy_dir = Path(tempfile.mkdtemp(prefix="research-canary-"))
        (decoy_dir / "secret.txt").write_text("canary secret")
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(4)
        port = srv.getsockname()[1]
        write = repo / "var" / "canary-must-not-exist"
        job = _prepare_job(None, "_canary.py", _CANARY_SCRIPT)
        try:
            cfg = {"port": port, "home_file": str(home / ".bashrc"), "home": str(home),
                   "repo": str(repo), "decoy_read": str(decoy_dir / "secret.txt"),
                   "repo_write": str(write)}
            try:
                r = subprocess.run(_bwrap_command(job, "_canary.py", [json.dumps(cfg)]), capture_output=True, check=False,
                                   timeout=60, start_new_session=True)
            except subprocess.TimeoutExpired:
                raise CanaryError("canary: timeout exceeded") from None
            if r.returncode != 0:
                raise CanaryError(f"canary: bwrap/python failed ({r.returncode}): "
                                  f"{r.stderr.decode('utf-8', 'replace')[-400:]}")
            try:
                res = json.loads(r.stdout.decode().strip().splitlines()[-1])
            except (ValueError, IndexError):
                raise CanaryError(f"canary: unreadable output: {r.stdout[-200:]!r}") from None
            if write.exists():
                write.unlink()
                raise CanaryError("canary: write to the repository succeeded")
            srv.settimeout(0.01)
            try:
                srv.accept()
                raise CanaryError("canary: the test server received a connection")
            except (TimeoutError, BlockingIOError):
                pass
            succeeded = [k for k, v in res["forbidden_succeeded"].items() if v]
            if succeeded:
                raise CanaryError(f"canary: forbidden actions succeeded: {sorted(succeeded)}")
            missing = [k for k, v in res["benchmarks"].items() if not v]
            if missing:
                raise CanaryError(f"canary: control checks failed: {sorted(missing)}")
        finally:
            srv.close()
            shutil.rmtree(job, ignore_errors=True)
            shutil.rmtree(decoy_dir, ignore_errors=True)
        _canary_ok = True


__all__ = [
    "CanaryError",
    "Worker",
    "bwrap_available",
    "canary",
    "contract",
    "run_stream",
    "verify_source",
]
