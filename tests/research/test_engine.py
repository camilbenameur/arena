"""Tests of the research engine: sandbox, stream, portfolio, trial, journal. 100% synthetic data."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from arena.journal import Journal
from research.config import load_criteria
from research.engine import sandbox, contract
from research.engine.sandbox import CanaryError, run_stream, verify_source
from research.engine.contract import DelayExceeded, TrialError, WeightShape, SourceRefused
from research.engine.trial import (
    TrialSheet,
    CapError,
    compute_metrics,
    run_trial,
    verify_causality,
)
from research.engine.journal import AnchorError, ResearchJournal, decimal12
from research.engine.panel import panel_from_tables, synthetic
from research.engine.portfolio import evaluation_mask, equal_weighted_basket, simulate, validate_weight

STRAT = Path(__file__).parent / "strategies"
START_2019_09 = int(pd.Timestamp("2019-09-01", tz="UTC").timestamp())
START_2018 = int(pd.Timestamp("2018-01-01", tz="UTC").timestamp())


@pytest.fixture(scope="module")
def crit():
    return load_criteria()


@pytest.fixture(scope="module", autouse=True)
def _canary():
    sandbox.canary()


@pytest.fixture
def dummy_lab(tmp_path):
    """Fake lab repository with the final-freeze tag (never the real lab journal)."""
    d = tmp_path / "lab"
    d.mkdir()
    lines = [json.dumps({"id": f"E{i:04d}", "prev_hash": "x"}) for i in range(1, 8)]
    (d / "trials.jsonl").write_text("\n".join(lines) + "\n")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    for cmd in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "x"], ["tag", "final-freeze"]):
        subprocess.run(["git", "-C", str(d), *cmd], check=True, env=env, capture_output=True)
    return d, lines


@pytest.fixture
def journal(tmp_path, dummy_lab):
    return ResearchJournal(tmp_path / "trials.jsonl", lab_repo=dummy_lab[0], clock=lambda: 1_700_000_000)


SHEET = TrialSheet("F1", "directional", "a" * 64)


def write(tmp_path, text, name="strategy.py"):
    p = tmp_path / name
    p.write_text(text)
    return p


def sharpe(r):
    return float(r.mean() / r.std(ddof=1) * math.sqrt(365))


# --------------------------------------------------------------------------------------------------
# Contrat
# --------------------------------------------------------------------------------------------------


def test_day_fields_and_anonymity():
    fields = [f.name for f in dataclasses.fields(contract.Day)]
    assert tuple(fields) == contract.DAY_FIELDS
    assert not {"date", "ts", "symbol", "symbols", "name"} & set(fields)
    assert contract.CODES == ("OK", "CAUSALITY", "TIMEOUT", "SOURCE_REFUSED", "WEIGHT_SHAPE", "ERROR")


def test_codes_aligned_with_criteria(crit):
    assert tuple(crit.execution.return_codes) == contract.CODES


def test_day_message_shape():
    panel = synthetic(30, 4, 1, with_perp=True)
    j = panel.day(3)
    assert j.i == 3 and j.spot_1d.shape == (4, 6) and j.spot_1h.shape == (4, 24, 6)
    assert j.perp_1h.shape == (4, 24, 6) and j.eligibles.dtype == bool
    assert all(isinstance(a, int) and isinstance(b, float) for a, b in j.funding)
    assert len(j.funding) == 3 * int(panel.eligibles_perp[3].sum())


# --------------------------------------------------------------------------------------------------
# AST check
# --------------------------------------------------------------------------------------------------

TEMPLATE = "import numpy as np\n\nclass Strategy:\n    def __init__(self, n_pairs):\n        self.n = n_pairs\n\n    def step(self, day):\n{body}\n        return np.zeros(self.n), np.zeros(self.n)\n"

HOSTILES = {
    "open": "        open('/etc/passwd').read()",
    "open_home": "        open('/root/.bashrc').read()",
    "import_os": "        import os",
    "import_socket": "        import socket",
    "import_subprocess": "        import subprocess",
    "import_time": "        import time",
    "import_random": "        import random",
    "import_pathlib": "        import pathlib",
    "from_os": "        from os import system",
    "dunder_import": "        __import__('os')",
    "eval": "        eval('1+1')",
    "exec": "        exec('x=1')",
    "compile": "        compile('1', 'a', 'eval')",
    "getattr": "        getattr(np, 'load')",
    "globals": "        globals()",
    "dunder_attr": "        np.__dict__",
    "dunder_class": "        ().__class__.__bases__",
    "np_load": "        np.load('x.npy')",
    "np_fromfile": "        np.fromfile('x')",
    "np_random": "        np.random.rand(3)",
    "np_savetxt": "        np.savetxt('x', np.zeros(3))",
    "np_ctypeslib": "        np.ctypeslib",
    "memoryview": "        memoryview(b'x')",
}


@pytest.mark.parametrize("name", sorted(HOSTILES))
def test_ast_refuses_hostile_sources(name):
    with pytest.raises(SourceRefused):
        verify_source(TEMPLATE.format(body=HOSTILES[name]))


def test_ast_refuses_missing_class_and_bad_syntax():
    with pytest.raises(SourceRefused):
        verify_source("import numpy as np\nx = 1\n")
    with pytest.raises(SourceRefused):
        verify_source("class Strategy(:\n")


def test_ast_accepts_repo_strategies():
    for f in ("f1_lab", "constant", "simple_hedged", "side_memory", "scale_leak", "column_leak"):
        verify_source((STRAT / f"{f}.py").read_text())


@pytest.mark.parametrize("name", ["open", "open_home", "import_socket", "import_subprocess", "np_load",
                                 "dunder_import"])
def test_hostile_trial_never_yields_a_result(tmp_path, journal, crit, name):
    p = write(tmp_path, TEMPLATE.format(body=HOSTILES[name]))
    r = run_trial(SHEET, p, {}, synthetic(40, 3, 0), journal, crit, causality=False, test=True)
    assert r.code == "SOURCE_REFUSED" and r.track is None and r.metrics == {}
    assert r.for_agent() == "SOURCE_REFUSED"


@pytest.mark.parametrize("body", [
    "        open('/etc/passwd').read()",
    "        open('/root/.bashrc').read()",
    "        s = __import__('socket')",
    "        s = __import__('os')",
    "        import socket as s",
])
def test_sandbox_belt_without_ast(tmp_path, body):
    """Even if the AST check were bypassed, the worker (restricted builtins + bwrap) produces nothing."""
    src = TEMPLATE.format(body=body).encode()
    with pytest.raises(TrialError):
        run_stream(src, {}, synthetic(5, 3, 0), lambda *a: None, 30, verify_ast=False)


# --------------------------------------------------------------------------------------------------
# bwrap sandbox (real)
# --------------------------------------------------------------------------------------------------


def test_canary_passes():
    sandbox.canary(force=True)


def test_canary_detects_a_leaky_sandbox(monkeypatch):
    """Mutants: without network isolation, then with the host's /tmp visible, the canary must raise."""
    true = sandbox._bwrap_command

    def without_network(job, script, args):
        cmd = true(job, script, args)
        cmd[cmd.index("--unshare-all")] = "--unshare-pid"
        return cmd

    def tmp_host(job, script, args):
        cmd = true(job, script, args)
        i = cmd.index("--tmpfs")
        cmd[i:i + 2] = ["--bind", "/tmp", "/tmp"]
        return cmd

    for mutant in (without_network, tmp_host):
        monkeypatch.setattr(sandbox, "_bwrap_command", mutant)
        with pytest.raises(CanaryError):
            sandbox.canary(force=True)
    monkeypatch.setattr(sandbox, "_bwrap_command", true)
    sandbox.canary(force=True)


def test_canary_checks_the_benchmarks(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda _: None)
    with pytest.raises(CanaryError):
        sandbox.canary(force=True)


def test_timeout_infinite_loop(tmp_path, journal, crit):
    p = write(tmp_path, TEMPLATE.format(body="        while True:\n            pass"))
    t0 = time.time()
    r = run_trial(SHEET, p, {}, synthetic(20, 3, 0), journal, crit, causality=False, timeout_s=2, test=True)
    assert r.code == "TIMEOUT" and time.time() - t0 < 15
    with pytest.raises(DelayExceeded):
        run_stream(p.read_bytes(), {}, synthetic(5, 3, 0), lambda *a: None, 1)


def test_no_error_or_trace_for_the_agent(tmp_path, journal, crit):
    p = write(tmp_path, TEMPLATE.format(body="        raise ValueError('secret 12345')"))
    r = run_trial(SHEET, p, {}, synthetic(20, 3, 0), journal, crit, causality=False, test=True)
    assert r.for_agent() == "ERROR" and r.code in contract.CODES
    # the detail (orchestrator) contains only the standard exception type and the day, never the message
    assert "secret" not in r.detail and "12345" not in r.detail and "ValueError" in r.detail
    assert "day 0" in r.detail
    text = journal.path.read_text()
    assert "secret" not in text and "Traceback" not in text
    assert "secret" not in journal.technical_path.read_text()


# --------------------------------------------------------------------------------------------------
# Weight shape
# --------------------------------------------------------------------------------------------------


def _trial_weight(tmp_path, journal, crit, body, class_="directional", with_perp=False, params=None):
    p = write(tmp_path, TEMPLATE.format(body=body).replace(
        "return np.zeros(self.n), np.zeros(self.n)", ""))
    panel = synthetic(30, 4, 0, with_perp=with_perp, late_quotes=False)
    sheet = TrialSheet("X", class_, "b" * 64)
    return run_trial(sheet, p, params or {}, panel, journal, crit, causality=False, test=True)


@pytest.mark.parametrize("returns,class_,code", [
    ("np.full(self.n, 0.3), np.zeros(self.n)", "directional", "WEIGHT_SHAPE"),        # sum 1.2
    ("np.full(self.n, 0.25 + 1e-6), np.zeros(self.n)", "directional", "WEIGHT_SHAPE"),  # 1.000004: no clipping
    ("np.array([-0.1, 0.1, 0.1, 0.1]), np.zeros(self.n)", "directional", "WEIGHT_SHAPE"),
    ("np.full(self.n, np.nan), np.zeros(self.n)", "directional", "WEIGHT_SHAPE"),
    ("np.zeros(self.n), np.full(self.n, 0.1)", "directional", "WEIGHT_SHAPE"),           # perp in directional
    ("np.zeros(3), np.zeros(self.n)", "directional", "WEIGHT_SHAPE"),                    # wrong shape
    ("np.full(self.n, 0.1), np.full(self.n, 0.2)", "hedged", "WEIGHT_SHAPE"),            # short > long
    ("np.full(self.n, 0.5), np.full(self.n, 0.5)", "hedged", "WEIGHT_SHAPE"),            # capital 0.5*4 + 0.25*4 > 1
    ("np.full(self.n, 0.2), np.full(self.n, 0.2)", "hedged", "OK"),                     # 0.8 + 0.4 = 1.2? -> see below
    ("np.full(self.n, 0.25), np.zeros(self.n)", "directional", "OK"),
    ("np.full(self.n, 0.25), np.zeros(self.n)", "hedged", "OK"),                     # naked spot long: allowed (engine v2)
])
def test_weight_shape(tmp_path, journal, crit, returns, class_, code):
    if class_ == "hedged" and code == "OK" and "0.2), np.full(self.n, 0.2)" in returns:
        code = "WEIGHT_SHAPE"  # 4 x 0.2 + 0.5 x 4 x 0.2 = 1.2 > 1
    r = _trial_weight(tmp_path, journal, crit, f"        return {returns}", class_=class_, with_perp=class_ == "hedged")
    assert r.code == code, r.detail


def test_weight_shape_no_clipping_of_bounds():
    listed = np.ones(3, dtype=bool)
    validate_weight("directional", 0, np.array([1 / 3] * 3), np.zeros(3), listed, None, 0.5)  # sum = 1 to within 1 ulp
    with pytest.raises(WeightShape):
        validate_weight("directional", 0, np.array([0.5, 0.5, 1e-6]), np.zeros(3), listed, None, 0.5)
    with pytest.raises(WeightShape):
        validate_weight("directional", 0, np.array([0.5, 0.0, 0.0]), np.zeros(3), np.array([0, 1, 1], bool), None, 0.5)


def test_weight_on_unlisted_pair_is_refused(tmp_path, journal, crit):
    p = write(tmp_path, TEMPLATE.format(body="        return np.full(self.n, 0.1), np.zeros(self.n)").replace(
        "\n        return np.zeros(self.n), np.zeros(self.n)\n", "\n"))
    panel = synthetic(60, 6, 3, late_quotes=True)
    assert not panel.eligibles.all()
    r = run_trial(SHEET, p, {}, panel, journal, crit, causality=False, test=True)
    assert r.code == "WEIGHT_SHAPE"


# --------------------------------------------------------------------------------------------------
# Portfolio: arithmetic
# --------------------------------------------------------------------------------------------------


def _mini_panel(closes):
    """1 d-only panel from a (T, N) matrix of closes."""
    closes = np.asarray(closes, dtype=float)
    T, N = closes.shape
    panel = synthetic(T, N, 0, with_1h=False, late_quotes=False, day_start=START_2018)
    s1d = panel.spot_1d.copy()
    s1d[..., 3] = closes
    return dataclasses.replace(panel, spot_1d=s1d)


def test_rotation_derived_by_hand(crit):
    panel = _mini_panel([[100, 100], [110, 100], [110, 100]])
    ws = np.array([[0.5, 0.5], [0.5, 0.5], [0.5, 0.5]])
    s = simulate(panel, ws, np.zeros((3, 2)), "directional", crit)
    r_p = 0.5 * 0.10
    assert s.gross_returns[1] == pytest.approx(r_p)
    # day 1: drifted = (0.5*1.1/1.05; 0.5/1.05) -> rotation = 2*|0.5-0.5238095|
    last = 0.5 * 1.1 / 1.05
    rot1 = abs(0.5 - last) + abs(0.5 - 0.5 / 1.05)
    # rotation decided on day 0 (initial purchase: 1.0) paid on day 1; that of day 1 paid on day 2
    assert s.rotation[1] == pytest.approx(1.0) and s.rotation[2] == pytest.approx(rot1)
    assert s.costs[1] == pytest.approx(0.006) and s.costs[2] == pytest.approx(0.006 * rot1)
    assert s.net_returns[1] == pytest.approx(r_p - 0.006)
    assert s.stressed_net_returns[2] == pytest.approx(0.0 - 2 * 0.006 * rot1)
    target = simulate(panel, ws, np.zeros((3, 2)), "directional", crit, convention_rotation="target")
    assert target.rotation[1] == pytest.approx(1.0) and target.rotation[2] == pytest.approx(0.0)


def test_double_stress_cost_and_perp_cost(crit):
    panel = synthetic(40, 3, 5, with_perp=True, late_quotes=False)
    ws = np.zeros((40, 3))
    wp = np.zeros((40, 3))
    ws[5:, 0] = 0.4
    wp[5:, 0] = 0.4
    s = simulate(panel, ws, wp, "hedged", crit)
    assert s.rotation_spot[6] == pytest.approx(0.4) and s.rotation_perp[6] == pytest.approx(0.4)
    assert s.costs[6] == pytest.approx(0.4 * 0.0060 + 0.4 * 0.0010)
    assert np.allclose(s.gross_returns - s.stressed_net_returns, 2 * s.costs)
    assert s.exposure[10] == pytest.approx(0.4 + 0.5 * 0.4)


def test_funding_paid_by_the_position_decided_before(crit):
    """A settlement of day j is paid by the weights decided at the close of j-1 (<= fundingTime)."""
    panel = synthetic(12, 2, 1, with_perp=True, late_quotes=False)
    z = np.zeros(0)
    fi = [z.astype(np.int64)] * 12
    ft = [z] * 12
    fs = [z.astype(np.int64)] * 12
    fi[6], ft[6], fs[6] = np.array([0], dtype=np.int64), np.array([0.01]), np.array([int(panel.days[6])], dtype=np.int64)
    panel = dataclasses.replace(panel, funding_idx=tuple(fi), funding_rate=tuple(ft), funding_ts=tuple(fs),
                              eligibles_perp=np.ones((12, 2), bool))
    before = np.zeros((12, 2)); before[5:, 0] = 0.5   # decided at the close of day 5 -> pays on day 6
    after = np.zeros((12, 2)); after[6:, 0] = 0.5   # decided at the close of day 6 -> does not pay on day 6
    s_before = simulate(panel, before, before, "hedged", crit)
    s_after = simulate(panel, after, after, "hedged", crit)
    assert s_before.funding[6] == pytest.approx(0.005) and s_after.funding[6] == 0.0
    # gross P&L = spot - perp + funding
    rs, rp = panel.spot_returns()[6, 0], panel.perp_returns()[6, 0]
    assert s_before.gross_returns[6] == pytest.approx(0.5 * rs - 0.5 * rp + 0.005)
    # funding received by a short when the rate is positive; paid when it is negative
    ft2 = list(ft); ft2[6] = np.array([-0.01])
    s_neg = simulate(dataclasses.replace(panel, funding_rate=tuple(ft2)), before, before, "hedged", crit)
    assert s_neg.funding[6] == pytest.approx(-0.005)


def test_evaluation_mask(crit):
    panel = synthetic(2600, 4, 2, with_1h=False, late_quotes=True, day_start=START_2018)
    el, m = evaluation_mask(panel, "directional", crit)
    j = pd.to_datetime(panel.days, unit="s")
    assert m[(j >= "2020-01-01") & el].all() and not m[j < "2020-01-01"].any() and not m[0]
    # perp window: ends on 2026-06-29 (out of reach here) and spot+perp required for hedged
    pan2 = synthetic(60, 3, 2, with_perp=True)
    assert not evaluation_mask(pan2, "hedged", crit)[1].any()  # 2018: outside the evaluation window


# --------------------------------------------------------------------------------------------------
# Acceptance 1: constant 1/15 weights, independent recomputation in quantities
# --------------------------------------------------------------------------------------------------


def test_acceptance_basket_one_fifteenth(tmp_path, journal, crit):
    N = 15
    panel = synthetic(650, N, 11, with_1h=False, late_quotes=False, day_start=START_2019_09)
    r = run_trial(SHEET, STRAT / "constant.py", {}, panel, journal, crit, causality=False, test=True)
    assert r.code == "OK", r.detail
    # independent recomputation: holdings in units, value, drift, rotation
    p = panel.spot_1d[:, :, 3]
    c = 0.0060
    q = (1 / N) * 1.0 / p[0]
    v = 1.0
    prev_rot = 1.0  # initial purchase
    net, rot = np.zeros(len(p)), np.zeros(len(p))
    for t in range(1, len(p)):
        v_new = float(q @ p[t])
        net[t] = (v_new / v - 1.0) - c * prev_rot
        rot[t] = prev_rot
        w_last = q * p[t] / v_new
        prev_rot = float(np.abs(1 / N - w_last).sum())
        q = v_new / N / p[t]
        v = v_new
    s = r.track
    assert np.allclose(s.net_returns, net, atol=1e-12, rtol=0)
    assert np.allclose(s.rotation, rot, atol=1e-12, rtol=0)
    m = s.eval_mask
    assert m.sum() > 400
    assert float(r.metrics["sharpe_net"]) == pytest.approx(sharpe(net[m]), abs=1e-12)
    # the engine's basket (rebalanced monthly) has the same structure: same days, lower rotation
    b = equal_weighted_basket(panel, crit)
    assert b.gross_returns[1:30].shape == (29,)
    assert b.costs.sum() < s.costs.sum()


def test_result_journaled_as_strings(tmp_path, journal, crit):
    panel = synthetic(650, 6, 12, with_1h=False, late_quotes=False, day_start=START_2019_09)
    r = run_trial(SHEET, STRAT / "constant.py", {"part": 1.0}, panel, journal, crit, causality=False, test=True)
    e = journal.trials()[r.id]
    assert e["end"]["status"] == "OK" and e["end"]["sharpe_net"] == decimal12(r.metrics["sharpe_net"])
    assert len(e["end"]["sharpe_net"].replace(".", "").replace("-", "").replace("e", "")) <= 16
    assert Journal(journal.path).verify().ok
    assert "." not in json.dumps(e["end"]["T"])  # integer
    assert e["start"]["code_sha256"] == hashlib.sha256((STRAT / "constant.py").read_bytes()).hexdigest()
    assert e["start"]["params"] == '{"part":1.0}' and e["start"]["criteria_sha256"] == crit.sha256


# --------------------------------------------------------------------------------------------------
# Acceptance 2: lab F1 under the stream contract = vectorized reference implementation
# --------------------------------------------------------------------------------------------------


def f1_reference(panel, L, k, H, cost=0.0015):
    """Lab version (pandas, vectorized except the ranking), weights of bar t on the return of t+1."""
    T, N = panel.n_days, panel.n_pairs
    cols = [f"P{j:02d}" for j in range(N)]
    vol = pd.DataFrame(panel.spot_1d[:, :, 4], columns=cols).where(panel.eligibles)
    tak = pd.DataFrame(panel.spot_1d[:, :, 5], columns=cols).where(panel.eligibles)
    ratio = (tak / vol).where(vol > 0)
    rbar = ratio.rolling(window=L, min_periods=L).mean().to_numpy()
    weight = np.zeros((T, N))
    current = np.zeros(N)
    for t in range(T):
        if t % H == 0:
            current = np.zeros(N)
            line = rbar[t]
            el = [i for i in range(N) if np.isfinite(line[i])]
            el.sort(key=lambda i: (-line[i], i))
            for i in el[:k]:
                current[i] = 1.0 / k
        weight[t] = current
    close = pd.DataFrame(panel.spot_1d[:, :, 3], columns=cols).where(panel.eligibles)
    r = close.pct_change(fill_method=None)
    ws = pd.DataFrame(weight, columns=cols).shift(1).fillna(0.0)
    ws = ws.where(r.notna(), 0.0)
    gross = (ws * r.fillna(0.0)).sum(axis=1)
    rot = ws.diff().abs().sum(axis=1)
    rot.iloc[0] = ws.iloc[0].abs().sum()
    return (gross - cost * rot).to_numpy(), rot.to_numpy()


@pytest.mark.parametrize("L,k,H", [(20, 3, 10), (5, 5, 5), (40, 7, 10)])
def test_acceptance_f1_flow_against_vectorized_reference(tmp_path, journal, crit, L, k, H):
    panel = synthetic(700, 15, 21, with_1h=False, late_quotes=True, day_start=START_2019_09)
    ref_net, ref_rot = f1_reference(panel, L, k, H)
    r = run_trial(SHEET, STRAT / "f1_lab.py", {"L": L, "k": k, "H": H}, panel, journal, crit,
                       convention_rotation="target", spot_cost_bp=15, causality=False, test=True)
    assert r.code == "OK", r.detail
    s = r.track
    assert np.allclose(s.net_returns, ref_net, atol=1e-12, rtol=0)
    assert np.allclose(s.rotation, ref_rot, atol=1e-12, rtol=0)
    m = s.eval_mask
    assert m.sum() > 500
    assert float(r.metrics["sharpe_net"]) == pytest.approx(sharpe(ref_net[m]), abs=1e-9)


def test_f1_invariant_to_column_permutation(tmp_path, journal, crit):
    panel = synthetic(300, 15, 5, with_1h=False, day_start=START_2019_09)
    rng = np.random.default_rng(0)
    series = []
    for _ in range(3):
        r = run_trial(SHEET, STRAT / "f1_lab.py", {}, panel, journal, crit, causality=False,
                           permutation=rng.permutation(15), test=True)
        assert r.code == "OK"
        series.append(r.track.net_returns)
    assert np.allclose(series[0], series[1], atol=1e-12) and np.allclose(series[0], series[2], atol=1e-12)


# --------------------------------------------------------------------------------------------------
# Causality and invariances (C9), on synthetic data
# --------------------------------------------------------------------------------------------------


def test_causality_f1_passes(crit):
    res = verify_causality((STRAT / "f1_lab.py").read_bytes(), {"L": 10, "k": 3, "H": 5}, crit)
    assert res["ok"], res
    assert res["n_cutoffs"] == 23 and res["non_full_hour_cutoffs"] >= math.ceil(0.4 * 23)
    assert res["cutoffs_gap"] <= 1e-9 and res["permutation_gap"] <= 1e-9 and res["scale_gap"] <= 1e-9


def test_causality_stateful_passes(crit):
    assert verify_causality((STRAT / "side_memory.py").read_bytes(), {}, crit)["ok"]


def test_causality_detects_column_and_rebasing_neutralizes_scale(crit):
    # the absolute price level is no longer passed (rebasing): scale_leak can no longer read the level
    a = verify_causality((STRAT / "scale_leak.py").read_bytes(), {}, crit)
    assert a["scale_gap"] <= 1e-9
    b = verify_causality((STRAT / "column_leak.py").read_bytes(), {}, crit)
    assert not b["ok"] and b["permutation_gap"] > 1e-9


def test_trial_causality_code(tmp_path, journal, crit):
    r = run_trial(SHEET, STRAT / "column_leak.py", {}, synthetic(80, 5, 4), journal, crit, test=True)
    assert r.code == "CAUSALITY" and r.track is None
    assert journal.trials()[r.id]["end"]["status"] == "CAUSALITY"


def test_truncation_identical_weights_on_the_prefix():
    src = (STRAT / "side_memory.py").read_bytes()
    panel = synthetic(120, 8, 9)
    ok = lambda *a: None
    ws, _wp, _ = run_stream(src, {}, panel, ok, 60)
    for n in (30, 77, 119):
        w2, _, _ = run_stream(src, {}, panel.truncate(n), ok, 60)
        assert np.abs(w2 - ws[:n]).max() == 0.0


def test_corrupting_the_future_does_not_change_the_past():
    src = (STRAT / "f1_lab.py").read_bytes()
    panel = synthetic(150, 8, 10)
    ok = lambda *a: None
    ws, _, _ = run_stream(src, {"L": 5, "k": 3, "H": 3}, panel, ok, 60)
    cut = int(panel.days[90]) + 5 * 3600 + 17 * 60  # 05:17 of day 90
    corr = panel.corrupt_after(cut, np.random.default_rng(0))
    assert not np.array_equal(corr.spot_1d[91], panel.spot_1d[91])
    assert np.array_equal(corr.spot_1d[89], panel.spot_1d[89]) and np.array_equal(corr.spot_1h[89], panel.spot_1h[89])
    w2, _, _ = run_stream(src, {"L": 5, "k": 3, "H": 3}, corr, ok, 60, until_error=1)
    assert np.abs(w2[:90] - ws[:90]).max() == 0.0  # days 0..89 closed before the cutoff


def test_panel_permute_and_scale():
    panel = synthetic(20, 5, 3, with_perp=True)
    perm = np.array([3, 0, 4, 1, 2])
    p = panel.swap(perm)
    assert p.symbols == tuple(panel.symbols[i] for i in perm)
    assert np.array_equal(p.spot_1d[:, 0], panel.spot_1d[:, 3])
    for i in range(20):  # funding follows the column
        a = {(panel.symbols[k], t) for k, t in zip(panel.funding_idx[i], panel.funding_rate[i], strict=True)}
        b = {(p.symbols[k], t) for k, t in zip(p.funding_idx[i], p.funding_rate[i], strict=True)}
        assert a == b
    f = np.array([0.1, 10, 1, 2, 5.0])
    e = panel.rescale(f)
    assert np.allclose(e.spot_1d[..., 3], panel.spot_1d[..., 3] * f)
    assert np.allclose(e.spot_1d[..., 4] * e.spot_1d[..., 3], panel.spot_1d[..., 4] * panel.spot_1d[..., 3])
    with np.errstate(invalid="ignore"):
        assert np.allclose(e.spot_1d[..., 5] / e.spot_1d[..., 4], panel.spot_1d[..., 5] / panel.spot_1d[..., 4], equal_nan=True)


def test_synthetic_is_consistent():
    panel = synthetic(30, 4, 1, late_quotes=False)
    h = panel.spot_1h
    assert np.allclose(panel.spot_1d[..., 3], h[:, :, -1, 3]) and np.allclose(panel.spot_1d[..., 0], h[:, :, 0, 0])
    assert np.allclose(panel.spot_1d[..., 4], h[..., 4].sum(axis=2))
    assert (panel.spot_1d[..., 1] >= panel.spot_1d[..., 3]).all() and (panel.spot_1d[..., 2] <= panel.spot_1d[..., 0]).all()


def test_panel_from_tables_alignment():
    idx = pd.date_range("2019-12-30", periods=5, freq="D")
    cols = ["open", "high", "low", "close", "volume", "taker_buy_base"]
    a = pd.DataFrame(np.arange(30, dtype=float).reshape(5, 6) + 1, index=idx, columns=cols)
    b = a.iloc[2:].copy()
    p = panel_from_tables(["AAA", "BBB"], {"AAA": a, "BBB": b})
    assert p.n_days == 5 and p.eligibles[:, 0].all() and list(p.eligibles[:, 1]) == [False, False, True, True, True]
    assert (p.spot_1d[:2, 1] == 0).all() and p.days[0] == int(pd.Timestamp("2019-12-30", tz="UTC").timestamp())
    s = p.sub_universe(["BBB"])
    assert s.n_days == 3 and s.eligibles.all()


# --------------------------------------------------------------------------------------------------
# Hedged class
# --------------------------------------------------------------------------------------------------


def test_hedged_trial(tmp_path, journal, crit):
    panel = synthetic(650, 6, 33, with_1h=False, with_perp=True, late_quotes=False, day_start=START_2019_09)
    sheet = TrialSheet("carry", "hedged", "c" * 64)
    r = run_trial(sheet, STRAT / "simple_hedged.py", {"size": 0.25, "k": 2}, panel, journal, crit,
                       causality=False, test=True)
    assert r.code == "OK", r.detail
    s = r.track
    ws, wp = s.spot_weight, s.perp_weight
    assert np.allclose(ws, wp) and np.allclose(ws.sum(axis=1)[100:], 0.5)
    # recomputed P&L: 0.25 per leg on the first two perp-listed columns
    rs, rp, fd = panel.spot_returns(), panel.perp_returns(), panel.funding_per_day()
    gross = np.zeros(panel.n_days)
    gross[1:] = (ws[:-1] * (rs[1:] - rp[1:] + fd[1:])).sum(axis=1)
    assert np.allclose(s.gross_returns, gross, atol=1e-12)
    assert np.allclose(s.exposure[100], 0.5 + 0.5 * 0.5) and abs(s.funding.sum()) > 0
    assert (s.immobilized_net_returns[100] * s.exposure[100]) == pytest.approx(s.net_returns[100])
    assert r.metrics["T"] > 100


def test_perp_not_provided_in_directional(tmp_path, journal, crit):
    """A directional sheet receives neither perp bars nor funding: a strategy that requires them fails."""
    panel = synthetic(40, 4, 1, with_perp=True, late_quotes=False)
    r = run_trial(SHEET, STRAT / "simple_hedged.py", {}, panel, journal, crit, causality=False, test=True)
    assert r.code == "ERROR"


# --------------------------------------------------------------------------------------------------
# Journal, anchoring, cap
# --------------------------------------------------------------------------------------------------


def test_lab_genesis(dummy_lab, journal):
    _d, lines = dummy_lab
    ev = journal.lab_genesis()
    assert ev["seq"] == 0 and ev["type"] == "lab_genesis"
    assert ev["payload"]["n_lines"] == 7 and ev["payload"]["head"] == hashlib.sha256(lines[-1].encode()).hexdigest()
    with pytest.raises(Exception, match="first line"):
        journal.lab_genesis()


def test_start_before_end_and_order(tmp_path, journal, crit, monkeypatch):
    seen = {}
    true = sandbox.run_stream

    def spy(*a, **k):
        seen["types"] = [e["type"] for e in journal.events()]
        return true(*a, **k)

    monkeypatch.setattr(sandbox, "run_stream", spy)
    panel = synthetic(30, 4, 1, with_1h=False)
    r = run_trial(SHEET, STRAT / "constant.py", {}, panel, journal, crit, causality=False, test=True)
    assert seen["types"] == ["lab_genesis", "start"]  # `start` is already written before the computation
    assert [e["type"] for e in journal.events()] == ["lab_genesis", "start", "end"]
    assert journal.n_ids() == 1 and r.id == "R0001"
    assert journal.next_id() == "R0002"


def test_failed_trial_counts_and_closes(tmp_path, journal, crit):
    p = write(tmp_path, "import numpy as np\nclass Strategy:\n    def __init__(self, n):\n        pass\n    def step(self, day):\n        return 1 / 0\n")
    run_trial(SHEET, p, {}, synthetic(20, 3, 0), journal, crit, causality=False, test=True)
    ev = journal.trials()
    assert list(ev) == ["R0001"] and ev["R0001"]["end"]["status"] == "ERROR"


def test_no_float_in_the_journal(tmp_path, journal, crit):
    panel = synthetic(650, 6, 12, with_1h=False, late_quotes=False, day_start=START_2019_09)
    run_trial(SHEET, STRAT / "constant.py", {"part": 0.5}, panel, journal, crit, causality=False, test=True)
    assert Journal(journal.path).verify().ok  # verify flags any float
    assert "float_present" not in Journal(journal.path).verify().codes()


def test_total_cap(tmp_path, journal, crit):
    small = dataclasses.replace(crit, total_cap=2)
    panel = synthetic(30, 4, 1, with_1h=False)
    for _ in range(2):
        run_trial(SHEET, STRAT / "constant.py", {}, panel, journal, small, causality=False, test=True)
    with pytest.raises(CapError):
        run_trial(SHEET, STRAT / "constant.py", {}, panel, journal, small, causality=False, test=True)
    assert journal.n_ids() == 2


def test_anchoring_and_verification(tmp_path, journal, crit):
    arena = tmp_path / "arena-journal.jsonl"
    panel = synthetic(30, 4, 1, with_1h=False)
    for _ in range(2):
        run_trial(SHEET, STRAT / "constant.py", {}, panel, journal, crit, causality=False, arena_journal=arena)
    ev = [e for e in Journal(arena).iter_events()]
    assert [e["type"] for e in ev] == ["research_anchor"] * 4  # after each start AND each end
    assert ev[-1]["payload"] == {"head": journal.head(), "n_lines": journal.n_lines(), "journal": "trials.jsonl",
                                 "genesis": journal.genesis_hash()}
    journal.verify_anchor(arena)
    # truncated journal (history rewrite) -> refused
    saved = journal.path.read_bytes()
    lines = saved.split(b"\n")
    journal.path.write_bytes(b"\n".join(lines[:-3]) + b"\n")
    with pytest.raises(AnchorError, match="latest anchor"):
        journal.verify_anchor(arena)
    # same length, same genesis, history rewritten (one line replaced, chain recomputed) -> head absent
    journal.path.write_bytes(saved)
    alt = ResearchJournal(tmp_path / "alt.jsonl", lab_repo=journal.lab_repo, clock=lambda: 1_700_000_000)
    alt.initialize()
    assert alt.genesis_hash() == journal.genesis_hash()
    for k in range(journal.n_lines() - 1):
        alt.journal.append("start", {"id": f"R{k:04d}"}, 5)
    journal.path.write_bytes(alt.path.read_bytes())
    with pytest.raises(AnchorError, match="anchored head"):
        journal.verify_anchor(arena)
    # journal recreated with another genesis -> refused
    alt2 = ResearchJournal(tmp_path / "alt2.jsonl", lab_repo=journal.lab_repo, clock=lambda: 5)
    alt2.journal.append("lab_genesis", {"tag": "x", "n_lines": 1, "head": "0" * 64}, 5)
    for k in range(journal.n_lines() - 1):
        alt2.journal.append("start", {"id": f"R{k:04d}"}, 5)
    journal.path.write_bytes(alt2.path.read_bytes())
    with pytest.raises(AnchorError, match="genesis"):
        journal.verify_anchor(arena)
    # a trial refuses to start if the anchoring is not respected
    with pytest.raises(AnchorError):
        run_trial(SHEET, STRAT / "constant.py", {}, panel, journal, crit, causality=False, arena_journal=arena)


def test_no_anchoring_without_path(tmp_path, journal):
    journal.initialize()
    assert journal.anchor(None) is None
    assert list(tmp_path.glob("*arena*")) == []


def test_start_requires_genesis_on_the_first_line(tmp_path, dummy_lab):
    j = ResearchJournal(tmp_path / "x.jsonl", lab_repo=dummy_lab[0])
    j.journal.append("start", {"id": "R0001"}, 1)
    with pytest.raises(Exception, match="first line"):
        j.initialize()


def test_decimal12():
    assert decimal12(1.2449864426425823) == "1.24498644264"
    assert decimal12(float("nan")) == "nan" and decimal12(3) == "3" and decimal12(1e-20) == "1e-20"


def test_short_metrics(crit):
    panel = synthetic(10, 3, 0, with_1h=False)
    s = simulate(panel, np.zeros((10, 3)), np.zeros((10, 3)), "directional", crit)
    assert compute_metrics(s) == {"T": 0}


# --------------------------------------------------------------------------------------------------
# Performance
# --------------------------------------------------------------------------------------------------


def test_performance_real_size(tmp_path, journal, crit):
    """~3,830 days (warm-up included) x 15 pairs with the 1 h bars: well under 60 s."""
    panel = synthetic(3830, 15, 77, with_1h=True, day_start=START_2018)
    t0 = time.time()
    r = run_trial(SHEET, STRAT / "f1_lab.py", {"L": 20, "k": 3, "H": 10}, panel, journal, crit, test=True)
    dt = time.time() - t0
    assert r.code == "OK", r.detail
    assert r.metrics["T"] == 2373 - 0 or r.metrics["T"] > 2000
    assert r.causality["ok"]
    assert dt < 60, dt


# --------------------------------------------------------------------------------------------------
# Data adapter (loader format) -> Panel
# --------------------------------------------------------------------------------------------------


def _data_from_panel(panel, control=None):
    from research.data.loader import Data

    cols = ["open", "high", "low", "close", "volume", "taker_buy_base"]
    spot_1d, spot_1h, perp_1h, funding = {}, {}, {}, {}
    for k, s in enumerate(panel.symbols):
        ok = panel.eligibles[:, k]
        spot_1d[s] = pd.DataFrame(panel.spot_1d[ok, k], columns=cols,
                                  index=pd.to_datetime(panel.days[ok], unit="s").as_unit("ns"))
        hs = (panel.days[ok][:, None] + np.arange(24)[None, :] * 3600).reshape(-1)
        spot_1h[s] = pd.DataFrame(panel.spot_1h[ok, k].reshape(-1, 6), columns=cols,
                                  index=pd.to_datetime(hs, unit="s").as_unit("ns"))
        okp = panel.eligibles_perp[:, k]
        hp = (panel.days[okp][:, None] + np.arange(24)[None, :] * 3600).reshape(-1)
        perp_1h[s] = pd.DataFrame(panel.perp_1h[okp, k].reshape(-1, 6), columns=cols,
                                  index=pd.to_datetime(hp, unit="s").as_unit("ns"))
        ts, tx = [], []
        for i in range(panel.n_days):
            m = panel.funding_idx[i] == k
            ts += list(panel.funding_ts[i][m])
            tx += list(panel.funding_rate[i][m])
        funding[s] = pd.DataFrame({"rate": tx, "known_at": np.array(ts) + 1},
                                  index=pd.to_datetime(ts, unit="s").as_unit("ns"))
    return Data(root_path=Path("."), manifest_sha256="0" * 64, universe=panel.symbols, control=(),
                   spot_1d=spot_1d, spot_1h=spot_1h, perp_1h=perp_1h, funding=funding, control_1d=control or {},
                   control_1h={}, control_perp_1h={}, control_funding={})


def test_panel_from_data_round_trip():
    from research.engine.panel import panel_from_data

    panel = synthetic(40, 5, 8, with_perp=True, late_quotes=True, day_start=START_2019_09)
    d = _data_from_panel(panel)
    p2 = panel_from_data(d, "main")
    assert p2.symbols == panel.symbols and np.array_equal(p2.days, panel.days)
    for a in ("spot_1d", "spot_1h", "perp_1h", "eligibles", "eligibles_perp"):
        assert np.array_equal(getattr(p2, a), getattr(panel, a)), a
    for i in range(panel.n_days):
        o1, o2 = np.lexsort((panel.funding_ts[i], panel.funding_idx[i])), np.lexsort((p2.funding_ts[i], p2.funding_idx[i]))
        assert np.array_equal(panel.funding_idx[i][o1], p2.funding_idx[i][o2])
        assert np.array_equal(panel.funding_rate[i][o1], p2.funding_rate[i][o2])
    without = panel_from_data(d, "main", with_perp=False, with_1h=False)
    assert without.perp_1h is None and without.spot_1h is None
    ar = panel_from_data(d, "arena", arena_symbols=("S01", "S03"))
    assert ar.symbols == ("S01", "S03")
    ctl = panel_from_data(dataclasses.replace(d, control_1d={"ZZZ": d.spot_1d["S00"]}), "control:ZZZ")
    assert ctl.symbols == ("ZZZ",) and ctl.spot_1h is None and ctl.n_pairs == 1


def test_trial_arena_and_control_universe(tmp_path, journal, crit):
    panel = synthetic(650, 15, 4, with_1h=False, late_quotes=False, day_start=START_2019_09)
    arena = tuple(crit.arena_universe)
    panel = dataclasses.replace(panel, symbols=tuple(crit.universe))
    r = run_trial(SHEET, STRAT / "constant.py", {}, panel, journal, crit, universe="arena", causality=False, test=True)
    assert r.code == "OK" and r.track.symbols == arena
    r2 = run_trial(SHEET, STRAT / "constant.py", {}, panel, journal, crit, universe="control:BTCUSDT",
                        causality=False, test=True)
    assert r2.code == "OK" and r2.track.symbols == ("BTCUSDT",) and r2.track.spot_weight.shape[1] == 1
    assert [e["universe"] for e in (v["start"] for v in journal.trials().values())] == ["arena", "control:BTCUSDT"]
