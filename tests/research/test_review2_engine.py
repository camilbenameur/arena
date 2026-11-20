"""Regression tests for the 2nd adversarial review of the engine: control universe without 1 h/perp/funding,
funding order revealing the permutation, escape through `collections._sys`, constant tables (integers,
strings), date through day counting, causality replay without derangement. 100% synthetic data.

Each test fails on the pre-fix code.
"""

from __future__ import annotations

import ast
import sys
import types
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.engine import sandbox, trial
from research.engine.sandbox import run_stream, verify_source
from research.engine.contract import SourceRefused
from research.engine.trial import TrialSheet, run_trial
from research.engine.panel import panel_from_data, synthetic, varied_synthetic
from tests.research.test_data import payload, dummy_root
from tests.research.test_engine_fixes import SYNTH_WAVE
from tests.research.test_engine import _canary, crit, write, journal, dummy_lab  # noqa: F401

STRAT = Path(__file__).parent / "strategies"


def ok(*_):
    return None


# --------------------------------------------------------------------------------------------------
# 1. Control universe: 1 h, perp and funding wired in
# --------------------------------------------------------------------------------------------------

SRC_HEDGED_PERP = b'''
import numpy as np
class Strategy:
    def __init__(self, n, **p):
        self.n = n
    def step(self, day):
        w = np.zeros(self.n)
        if day.perp_1h is not None and day.eligibles_perp is not None and day.eligibles_perp[0] \\
                and day.eligibles[0]:
            w[0] = 0.25
        return w, w.copy()
'''


def test_control_branch_1h_perp_and_funding(tmp_path):
    d = payload(tmp_path, dummy_root(tmp_path))
    panel = panel_from_data(d, "control:CTLUSDT")
    assert panel.symbols == ("CTLUSDT",)
    assert panel.spot_1h is not None and panel.perp_1h is not None and panel.eligibles_perp is not None
    assert panel.eligibles_perp.any() and sum(len(a) for a in panel.funding_idx) == 3  # 06-29; 06-30 outside the 1 d grid
    # same values as the loader tables (columns and known_at identical to the main universe)
    h = d.control_1h["CTLUSDT"][["open", "high", "low", "close", "volume", "taker_buy_base"]].to_numpy()
    assert np.array_equal(panel.spot_1h[-1, 0], h[:24])  # last day of the 1 d grid = 2026-06-29
    pf = d.control_perp_1h["CTLUSDT"][["open", "high", "low", "close", "volume", "taker_buy_base"]].to_numpy()
    assert np.array_equal(panel.perp_1h[-1, 0], pf[:24])
    # without 1 h / perp: None, as before
    d2 = payload(tmp_path / "b", dummy_root(tmp_path / "b", ctl_perp=False, ctl_1h=False))
    p2 = panel_from_data(d2, "control:CTLUSDT")
    assert p2.spot_1h is None and p2.perp_1h is None and p2.eligibles_perp is None


def test_hedged_control_and_perp_signals_receive_their_data(tmp_path, crit):  # noqa: F811
    d = payload(tmp_path, dummy_root(tmp_path))
    pc = trial._panel(d, "control:CTLUSDT", "hedged", crit)
    assert pc.perp_1h is not None and pc.eligibles_perp is not None
    ps = trial._panel(d, "control:CTLUSDT", "directional", crit, with_perp=True)  # perp_signals
    assert ps.perp_1h is not None and ps.eligibles_perp is not None
    for panel in (pc, ps):
        ws, wp, _ = run_stream(SRC_HEDGED_PERP, {}, panel, ok, 60)
        assert ws.any() and wp.any(), "the strategy never received perp on the control universe"
    # a directional sheet without perp_signals receives nothing from perp
    assert trial._panel(d, "control:CTLUSDT", "directional", crit).perp_1h is None
    assert TrialSheet("S", "directional", "c" * 64, perp_signals=True).perp_signals


# --------------------------------------------------------------------------------------------------
# 2. The funding order does not reveal the permutation
# --------------------------------------------------------------------------------------------------


def test_funding_order_independent_of_permutation():
    panel = varied_synthetic(200, 15, 3, with_perp=True)
    for seed in range(3):
        perm = np.random.default_rng(seed).permutation(15)
        pp = panel.swap(perm)
        for i in (120, 150, 199):
            msgs = pp.day(i).funding
            idx = [k for k, _ in msgs]
            assert idx == sorted(idx), "the settlements must be sorted by permuted column"
            # within the same column, chronological order (rates follow the timestamps)
            ts = pp.funding_ts[i]
            order = np.lexsort((ts, pp.funding_idx[i]))
            assert [t for _, t in msgs] == pp.funding_rate[i][order].tolist()


SRC_FIRST_FUNDING = b'''
import numpy as np
class Strategy:
    def __init__(self, n, **p): self.n = n
    def step(self, j):
        w = np.zeros(self.n)
        if j.funding:
            w[j.funding[0][0]] = 0.5
        return w, np.zeros(self.n)
'''


def test_flow_does_not_depend_on_permutation_via_funding():
    panel = varied_synthetic(120, 15, 5, with_perp=True)
    outputs = []
    for seed in (1, 2):
        perm = np.random.default_rng(seed).permutation(15)
        ws, _wp, _ = run_stream(SRC_FIRST_FUNDING, {}, panel.swap(perm), ok, 60)
        outputs.append(ws)
    # in the frame of the stream's COLUMNS, the strategy sees the same thing whatever the permutation
    assert np.array_equal(outputs[0], outputs[1])


# --------------------------------------------------------------------------------------------------
# 3. Escape from the AST check
# --------------------------------------------------------------------------------------------------

TEMPLATE = ("import collections, numpy as np\nclass Strategy:\n    def __init__(self, n, **p):\n        self.n = n\n"
       "    def step(self, day):\n{body}\n        return np.zeros(self.n), np.zeros(self.n)\n")


def _src(body: str) -> str:
    return TEMPLATE.format(body="\n".join("        " + line for line in body.splitlines()))


REFUSED = {
    "collections._sys": "m = collections._sys.modules",
    "private_alias": "import collections as _c",
    "private_from_import": "from collections import _sys",
    "private_kw": "f = dict(_x=1)",
    "private_name": "_s = 1",
    "np_ma_inspect": "m = np.ma.extras.ma.operator",
    "np_char_inspect": "m = np.char.overrides.inspect",
    "from_numpy_ma": "from numpy import ma",
    "type": "t = type(self)",
    "dir": "t = dir(self)",
    "getattr": "t = getattr(self, 'n')",
    "vars": "t = vars(self)",
    "setattr": "setattr(self, 'n', 1)",
    "delattr": "delattr(self, 'n')",
    "ndarray_dump": "np.zeros(3).dump('/tmp/x')",
    "np_load": "np.load('/tmp/x')",
    "np_lib": "np.lib.npyio",
    "np_ctypeslib": "np.ctypeslib",
    "np_testing": "np.testing",
    "np_f2py": "np.f2py",
    "np_memmap": "np.memmap('/tmp/x')",
    "np_tofile": "np.zeros(3).tofile('/tmp/x')",
    "statistics_sys": "import statistics\nstatistics.sys",
    "bounced_self": "self = collections",
    "bounced_self_for": "for self in [collections]:\n    pass",
    "bounced_self_import": "import collections as self",
    "unbound_local_class": "Strategy.step(collections, None)",
    "int_literal": "x = int('1010', 2)",
    "float_literal": "x = float('1.5')",
    "bytes_literal": "x = bytes('ab', 'ascii')",
    "bytearray_literal": "x = bytearray('ab', 'ascii')",
    "ord_literal": "x = ord('a')",
    "fromhex": "x = bytes.fromhex('ab')",
    "int_fstring": "x = int(f'{1}0')",
    "integer_65_bits": f"x = {1 << 64}",
    "negative_integer_65_bits": f"x = -{1 << 64}",
    "total_strings": "\n".join(f"s{i} = '{'a' * 60}'" for i in range(9)),
}


@pytest.mark.parametrize("name", REFUSED)
def test_source_refused(name):
    body = REFUSED[name]
    text = _src(body)
    if name == "unbound_local_class":
        text = (TEMPLATE.format(body="        return np.zeros(self.n), np.zeros(self.n)")
                 + "def helper(self):\n    return self._sys\nStrategy.helper(collections)\n")
    with pytest.raises(SourceRefused):
        verify_source(text)


def test_function_outside_class_with_self_is_refused():
    text = TEMPLATE.format(body="        pass") + "\ndef helper(self):\n    return self._sys\n"
    with pytest.raises(SourceRefused):
        verify_source(text)


ACCEPTED = {
    "private_self_attribute": "self._x = 1\nself._y = self._x + 1",
    "throwaway_name": "a = [0 for _ in range(3)]",
    "integer_64_bits": f"x = {(1 << 64) - 1}",
    "short_strings": "\n".join(f"s{i} = '{'a' * 60}'" for i in range(2)),
    "float_on_variable": "x = float(self.n)",
}


@pytest.mark.parametrize("name", ACCEPTED)
def test_source_accepted(name):
    verify_source(_src(ACCEPTED[name]))


def test_long_docstrings_excluded_from_the_total():
    long_one = "x" * 2000
    src = (f'"""{long_one}"""\nimport numpy as np\nclass Strategy:\n    """{long_one}"""\n'
           f'    def __init__(self, n):\n        """{long_one}"""\n        self.n = n\n'
           "    def step(self, day):\n        return np.zeros(self.n), np.zeros(self.n)\n")
    verify_source(src)
    # a long string that is NOT a docstring is counted
    src2 = src.replace("        self.n = n\n", f"        self.n = n\n        '{'y' * 60}'\n        s = '{'z' * 500}'\n")
    with pytest.raises(SourceRefused):
        verify_source(src2)


def test_synthetic_wave_strategies_pass_the_control():
    assert len(SYNTH_WAVE) == 5
    for name, (_c, _s, source, _p) in sorted(SYNTH_WAVE.items()):
        verify_source(source, f"{name}.py")


def test_no_attribute_path_to_a_module_outside_the_whitelist():
    """Walks the public attributes (except those the check refuses) of the allowlisted modules:
    no module outside numpy / the allowlist must remain reachable (regression guard on upgrades)."""
    safe = set(sandbox.IMPORTS_ALLOWED)
    roots = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import bisect
        import collections
        import functools
        import heapq
        import itertools
        import math
        import statistics

        import numpy as np
        roots = {"numpy": np, "collections": collections, "statistics": statistics, "math": math,
                   "itertools": itertools, "functools": functools, "heapq": heapq, "bisect": bisect}
        seen, outputs = set(), {}

        def internal(m):
            t = m.__name__.split(".")[0]
            return t == "numpy" or t in safe

        def walk(m, path):
            if id(m) in seen:
                return
            seen.add(id(m))
            for a in dir(m):
                if sandbox.forbidden_attribute(a):
                    continue
                try:
                    v = getattr(m, a)
                except Exception:  # noqa: BLE001, S112
                    continue
                if isinstance(v, types.ModuleType):
                    if internal(v):
                        walk(v, f"{path}.{a}")
                    else:
                        outputs[f"{path}.{a}"] = v.__name__

        for n, m in roots.items():
            walk(m, n)
    assert outputs == {}, outputs
    assert sys.modules  # the traversal imported nothing dangerous in this process


def test_ast_tree_cites_no_private_path_in_synthetic_wave_strategies():
    for name, (_c, _s, source, _p) in sorted(SYNTH_WAVE.items()):
        for n in ast.walk(ast.parse(source)):
            if isinstance(n, ast.Attribute) and n.attr.startswith("_"):
                assert isinstance(n.value, ast.Name) and n.value.id == "self", (name, n.attr)


# --------------------------------------------------------------------------------------------------
# 5. Date through a day counter: k warm-up days removed from the stream
# --------------------------------------------------------------------------------------------------

SRC_COUNTER = (b"import numpy as np\nclass Strategy:\n    def __init__(self, n, **p):\n        self.n = n; self.c = 0\n"
                b"    def step(self, j):\n        self.c += 1\n        w = np.zeros(self.n); w[0] = self.c / 1000.0\n"
                b"        return w, np.zeros(self.n)\n")


def test_removed_days_are_not_sent():
    panel = synthetic(30, 3, 0, with_1h=False, late_quotes=False)
    calls = []

    def validate(i, a, b):
        calls.append(i)

    ws, _wp, n_ok = run_stream(SRC_COUNTER, {}, panel, validate, 60, days_withdrawn=7, offset=20_000)
    assert calls == list(range(7, 30)) and n_ok == 30
    assert (ws[:7] == 0).all()
    assert ws[7, 0] == pytest.approx(1 / 1000) and ws[-1, 0] == pytest.approx(23 / 1000)
    ws0, _wp0, _ = run_stream(SRC_COUNTER, {}, panel, ok, 60)
    assert ws0[0, 0] == pytest.approx(1 / 1000)  # k = 0: behaviour unchanged
    with pytest.raises(ValueError):
        run_stream(SRC_COUNTER, {}, panel, ok, 60, days_withdrawn=30)


def test_draw_bounded_and_evaluation_intact(crit):  # noqa: F811
    deb2020 = int(pd.Timestamp("2020-01-01", tz="UTC").timestamp())
    large = synthetic(1000, 3, 0, with_1h=False)  # 2018-01-01: 730 warm-up days
    ks = {sandbox.draw_days_withdrawn(large, crit) for _ in range(300)}
    assert min(ks) >= 0 and max(ks) < 365 and len(ks) > 50
    assert all(730 - k >= 365 for k in ks)  # remaining warm-up >= 365 days
    short = synthetic(1000, 3, 0, with_1h=False, day_start=deb2020 - 380 * 86400)
    assert {sandbox.draw_days_withdrawn(short, crit) for _ in range(100)} <= set(range(16))  # 380 - k >= 365
    without = synthetic(100, 3, 0, with_1h=False, day_start=deb2020)
    assert {sandbox.draw_days_withdrawn(without, crit) for _ in range(50)} == {0}


def test_same_k_for_main_run_and_real_replay(tmp_path, journal, crit):  # noqa: F811
    panel = synthetic(700, 4, 1, with_1h=False, late_quotes=False)
    code = write(tmp_path, "import numpy as np\nclass Strategy:\n    def __init__(self, n, **p):\n        self.n = n\n"
                  "    def step(self, j):\n        e = j.eligibles.astype(float)\n"
                  "        return e / max(e.sum(), 1.0), np.zeros(self.n)\n")
    seen = []
    true = sandbox.run_stream

    def spy(source, params, panel, validator, timeout_s, **kw):
        seen.append((panel.n_days, kw.get("days_withdrawn")))
        return true(source, params, panel, validator, timeout_s, **kw)

    mp = pytest.MonkeyPatch()
    mp.setattr(sandbox, "run_stream", spy)
    try:
        r = run_trial(TrialSheet("F1", "directional", "a" * 64), code, {}, panel, journal, crit,
                           causality=True, test=True)
    finally:
        mp.undo()
    assert r.code == "OK", r.detail
    real_values = [k for n, k in seen if n == 700]
    assert len(real_values) == 2 and real_values[0] == real_values[1] and 0 <= real_values[0] < 336  # 700 - 365 + 1
    synth = {k for n, k in seen if n == 1300}
    assert len(synth) == 1  # a single draw for all synthetic replays


# --------------------------------------------------------------------------------------------------
# 6. Real causality: replay with a derangement relative to the main permutation
# --------------------------------------------------------------------------------------------------


def test_relative_disturbance():
    rng = np.random.default_rng(0)
    for n in (2, 3, 6, 15):
        for _ in range(50):
            ref = rng.permutation(n)
            p = trial._derangement(rng, ref)
            assert sorted(p.tolist()) == list(range(n)) and (p != ref).all()
    assert trial._derangement(rng, np.array([0])).tolist() == [0]


def test_real_control_always_detects_the_column_leak():
    src = (STRAT / "column_leak.py").read_bytes()
    panel = synthetic(60, 6, 4, with_1h=False, late_quotes=False)
    rng = np.random.default_rng(0)
    detections = 0
    for _ in range(20):
        perm = rng.permutation(6)
        ws, wp, _ = trial._run(src, {}, panel.swap(perm), "directional", 0.5, 60, True)
        ws_o, wp_o = np.empty_like(ws), np.empty_like(wp)
        ws_o[:, perm], wp_o[:, perm] = ws, wp
        detections += trial._real_control(src, {}, panel, "directional", 0.5, 60, ws_o, wp_o,
                                           perm_ref=perm) > 1e-9
    assert detections == 20


# --------------------------------------------------------------------------------------------------
# 7. Bounded sandbox tmpfs
# --------------------------------------------------------------------------------------------------


def test_tmpfs_bounded():
    cmd = sandbox._bwrap_command("/job", "_worker.py", [])
    i = cmd.index("--tmpfs")
    assert cmd[i - 2:i] == ["--size", str(256 * 2**20)] and cmd[i + 1] == "/tmp"


def test_literal_bit_budget_closes_the_bytes_channel_and_the_cumulative():
    """Review 2b: a bytes literal read by index, or 32 64-bit integers + 512 characters, encoded
    up to 6,144 bits of calendar; the total budget is 1,024 bits (frozen strategies: 908 at most)."""
    from research.engine.sandbox import SourceRefused, verify_source
    head = "import numpy as np\n\n\nclass Strategy:\n    def __init__(self, n, **p):\n        self.n = n\n"
    step = "    def step(self, j):\n        return np.zeros(self.n), np.zeros(self.n)\n"
    with pytest.raises(SourceRefused, match="bytes"):
        verify_source(head + "        self.c = b'abc'\n" + step)
    with pytest.raises(SourceRefused, match="ASCII"):
        verify_source(head + "        self.c = 'é'\n" + step)
    ints = "".join(f"        self.v{i} = {(1 << 63) + i}\n" for i in range(20))  # 20 x 64 bits = 1,280 bits
    with pytest.raises(SourceRefused, match="bits of literals"):
        verify_source(head + ints + step)
    for name, (_c, _s, source, _p) in sorted(SYNTH_WAVE.items()):
        verify_source(source, f"{name}.py")
