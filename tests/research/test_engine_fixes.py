"""Regression tests for the engine fixes (adversarial review). 100% synthetic data.

Each test fails on the pre-fix code: date leaking through `Day.i`, absolute price level,
recognizable C9, diluted hedged class, escape through generator frames, journal without anchor or
genesis, output channels (text, time).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from arena.journal import Journal
from research.config import load_criteria
from research.engine import sandbox, trial
from research.engine.sandbox import OFFSET_MIN, run_stream, verify_source
from research.engine.contract import WeightShape, SourceRefused
from research.engine.trial import (
    TrialSheet,
    compute_gate_metrics,
    run_trial,
    verify_causality,
)
from research.engine.journal import AnchorError, ResearchJournal
from research.engine.panel import DAY_S, synthetic, varied_synthetic
from research.engine.portfolio import immobilized_divisor, simulate, validate_weight
from research.gates.adapter import to_trial, to_causality_report

STRAT = Path(__file__).parent / "strategies"
START_2020 = int(pd.Timestamp("2020-01-01", tz="UTC").timestamp())
SHEET = TrialSheet("F1", "directional", "a" * 64)
SHEET_C = TrialSheet("C1", "hedged", "b" * 64)

TEMPLATE = ("import numpy as np\n\nclass Strategy:\n    def __init__(self, n_pairs, **p):\n        self.n = n_pairs\n\n"
           "    def step(self, day):\n{body}\n")


_HEAD = "import numpy as np\n\n\nclass Strategy:\n"

# Synthetic stand-ins for wave-1 strategies: (class, receives perp signals, source, params).
# They exercise the same inputs (daily bars, funding settlements, perp eligibility) with non-trivial weights.
SYNTH_WAVE = {
    "m-semivar": ("directional", False, _HEAD + """    def __init__(self, n_pairs, L=20, k=3):
        self.n, self.L, self.k = n_pairs, L, k
        self.prev = np.full(n_pairs, np.nan)
        self.r = []

    def step(self, day):
        c = np.where(day.eligibles, day.spot_1d[:, 3], np.nan)
        self.r.append(c / self.prev - 1.0)
        self.prev = c
        w = np.zeros(self.n)
        if len(self.r) > self.L:
            h = np.array(self.r[-self.L:])
            ok = np.isfinite(h).all(axis=0)
            neg = np.minimum(np.where(np.isfinite(h), h, 0.0), 0.0)
            semi = np.where(ok, (neg ** 2).mean(axis=0), np.inf)
            for j in np.argsort(semi)[: self.k]:
                if np.isfinite(semi[j]):
                    w[j] = 1.0 / self.k
        return w, np.zeros(self.n)
""", {}),
    "r-crowded-funding": ("directional", True, _HEAD + """    def __init__(self, n_pairs, k=3, a=0.1):
        self.n, self.k, self.a = n_pairs, k, a
        self.ema = np.zeros(n_pairs)

    def step(self, day):
        f = np.zeros(self.n)
        for j, x in day.funding:
            f[j] += x
        self.ema = (1.0 - self.a) * self.ema + self.a * f
        ok = day.eligibles & day.eligibles_perp
        w = np.zeros(self.n)
        score = np.where(ok, self.ema, np.inf)
        for j in np.argsort(score)[: self.k]:
            if ok[j]:
                w[j] = 1.0 / self.k
        return w, np.zeros(self.n)
""", {}),
    "c-rank-carry": ("hedged", False, _HEAD + """    def __init__(self, n_pairs, k=3, size=0.2, a=0.1):
        self.n, self.k, self.size, self.a = n_pairs, k, size, a
        self.ema = np.zeros(n_pairs)

    def step(self, day):
        f = np.zeros(self.n)
        for j, x in day.funding:
            f[j] += x
        self.ema = (1.0 - self.a) * self.ema + self.a * f
        ok = day.eligibles & day.eligibles_perp
        w = np.zeros(self.n)
        score = np.where(ok, -self.ema, np.inf)
        for j in np.argsort(score)[: self.k]:
            if ok[j] and self.ema[j] > 0.0:
                w[j] = self.size
        return w, w.copy()
""", {}),
    "c-persistent-carry": ("hedged", False, _HEAD + """    def __init__(self, n_pairs, L=10, size=0.2, k=3):
        self.n, self.L, self.size, self.k = n_pairs, L, size, k
        self.h = []

    def step(self, day):
        f = np.zeros(self.n)
        for j, x in day.funding:
            f[j] += x
        self.h.append(f)
        ok = day.eligibles & day.eligibles_perp
        w = np.zeros(self.n)
        if len(self.h) >= self.L:
            m = np.array(self.h[-self.L:])
            pos = (m > 0.0).all(axis=0) & ok
            avg = np.where(pos, m.mean(axis=0), -np.inf)
            for j in np.argsort(-avg)[: self.k]:
                if pos[j]:
                    w[j] = self.size
        return w, w.copy()
""", {}),
    "c-carry-regime": ("hedged", False, _HEAD + """    def __init__(self, n_pairs, size=0.2, a=0.05, thr=0.0002):
        self.n, self.size, self.a, self.thr = n_pairs, size, a, thr
        self.market = 0.0
        self.ema = np.zeros(n_pairs)

    def step(self, day):
        ok = day.eligibles & day.eligibles_perp
        f = np.zeros(self.n)
        for j, x in day.funding:
            f[j] += x
        mean = float(f[ok].mean()) if ok.any() else 0.0
        self.market = (1.0 - self.a) * self.market + self.a * mean
        self.ema = (1.0 - self.a) * self.ema + self.a * f
        w = np.zeros(self.n)
        if self.market > self.thr:
            for j in np.argsort(np.where(ok, -self.ema, np.inf))[:3]:
                if ok[j]:
                    w[j] = self.size
        return w, w.copy()
""", {}),
}


@pytest.fixture(scope="module")
def crit():
    return load_criteria()


@pytest.fixture(scope="module", autouse=True)
def _canary():
    sandbox.canary()


@pytest.fixture
def journal(tmp_path):
    import subprocess

    d = tmp_path / "lab"
    d.mkdir()
    (d / "trials.jsonl").write_text(json.dumps({"id": "E0001"}) + "\n")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    for cmd in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "x"], ["tag", "final-freeze"]):
        subprocess.run(["git", "-C", str(d), *cmd], check=True, env=env, capture_output=True)
    return ResearchJournal(tmp_path / "trials.jsonl", lab_repo=d, clock=lambda: 1_700_000_031)


def write(tmp_path, body, name="strategy.py"):
    p = tmp_path / name
    p.write_text(TEMPLATE.format(body=body))
    return p


def ok(*_):
    return None


# --------------------------------------------------------------------------------------------------
# 1. The date no longer leaks: shifted index, rebased prices and volumes
# --------------------------------------------------------------------------------------------------


def test_day_i_shifted_randomly_per_trial():
    src = TEMPLATE.format(body="        w = np.zeros(self.n)\n        w[0] = day.i / 1e8\n        return w, np.zeros(self.n)").encode()
    panel = synthetic(12, 3, 0, with_1h=False, late_quotes=False)
    starts = []
    for _ in range(3):
        ws, _wp, _ = run_stream(src, {}, panel, ok, 60)
        i = np.rint(ws[:, 0] * 1e8).astype(int)
        assert (np.diff(i) == 1).all()  # days can be counted...
        starts.append(int(i[0]))
    assert min(starts) >= OFFSET_MIN  # ... but i is no longer the rank since 2018-01-01
    assert len(set(starts)) == 3
    ws, _wp, _ = run_stream(src, {}, panel, ok, 60, offset=123_456)
    assert round(ws[0, 0] * 1e8) == 123_456


def test_rebasing_price_and_volumes_causal():
    panel = synthetic(80, 5, 3, with_1h=True, with_perp=True, late_quotes=True)
    view = panel.rebase()
    for k in range(panel.n_pairs):
        idx = np.flatnonzero(panel.eligibles[:, k])
        # prices: divided by the pair's first close
        assert view.spot_1d[idx[0], k, 3] == pytest.approx(1.0)
        assert np.allclose(view.spot_1d[idx, k, 3], panel.spot_1d[idx, k, 3] / panel.spot_1d[idx[0], k, 3])
        # perp: same divisor (the perp/spot basis is preserved)
        assert np.allclose(view.perp_1h[idx, k, :, 3] / view.spot_1h[idx, k, :, 3],
                           panel.perp_1h[idx, k, :, 3] / panel.spot_1h[idx, k, :, 3])
        # volumes: running mean, then mean of the first 30 listed days
        v = panel.spot_1d[idx, k, 4]
        for n in (0, 5, 28, 29, 40):
            if n < len(idx):
                m = v[: min(n + 1, 30)].mean()
                assert view.spot_1d[idx[n], k, 4] == pytest.approx(v[n] / m)
        assert np.all(view.spot_1d[~panel.eligibles[:, k], k] == 0.0)


def test_rebasing_depends_only_on_the_past():
    panel = synthetic(90, 4, 5, late_quotes=True)
    future = panel.corrupt_after(int(panel.days[50]) + 5 * 3600, np.random.default_rng(0))
    a, b = panel.rebase(), future.rebase()
    before = slice(0, 50)  # days entirely closed before the cutoff
    assert np.array_equal(a.spot_1d[before], b.spot_1d[before])
    assert np.array_equal(a.spot_1h[before], b.spot_1h[before])


def test_strategy_no_longer_sees_the_absolute_level(tmp_path):
    # weight = 0.1 x the day's close: with rebasing, 0.1 on the first day for all pairs
    src = TEMPLATE.format(body="        return np.where(day.eligibles, 0.1 * day.spot_1d[:, 3], 0.0), np.zeros(self.n)").encode()
    panel = synthetic(5, 6, 1, with_1h=False, late_quotes=False)
    assert panel.spot_1d[0, :, 3].max() / panel.spot_1d[0, :, 3].min() > 5  # very different real levels
    ws, _wp, _ = run_stream(src, {}, panel, ok, 60)
    assert np.allclose(ws[0], 0.1)


def test_returns_computed_on_real_prices(tmp_path, journal, crit):
    panel = synthetic(40, 4, 2, with_1h=False, late_quotes=False, day_start=START_2020)
    r = run_trial(SHEET, STRAT / "constant.py", {}, panel, journal, crit, causality=False, test=True)
    gross = r.track.gross_returns
    expected = panel.spot_returns()[1:].mean(axis=1)
    assert np.allclose(gross[1:], expected)


def test_ast_refuses_large_constant_tables():
    def src(body):
        return TEMPLATE.format(body="        " + body + "\n        return np.zeros(self.n), np.zeros(self.n)")

    verify_source(src("x = [" + ",".join(["1"] * 16) + "]"))  # 16 elements: allowed
    for table in ("[" + ",".join(["1"] * 17) + "]", "(" + ",".join(["1"] * 17) + ")",
                  "{" + ",".join(f"'{i}'" for i in range(17)) + "}",
                  "{" + ",".join(f"{i}:0" for i in range(17)) + "}"):
        with pytest.raises(SourceRefused):
            verify_source(src("x = " + table))
    verify_source(src("; ".join(f"x{i} = {i + 2}" for i in range(31))))  # 31 + 0 other numeric literals
    with pytest.raises(SourceRefused, match="numeric literals"):
        verify_source(src("; ".join(f"x{i} = {i + 2}" for i in range(33))))
    with pytest.raises(SourceRefused):  # table inside a string
        verify_source(src("x = '" + "01" * 100 + "'"))
    verify_source('"""' + "very long docstring " * 20 + '"""\n' + src("x = 1"))  # docstring: allowed


@pytest.mark.parametrize("p", [p for p in sorted(STRAT.glob("*.py")) if p.name != "__init__.py"],
                         ids=lambda p: p.name)
def test_ast_accepts_legitimate_strategies(p):
    verify_source(p.read_text(), p.name)


@pytest.mark.parametrize("name", sorted(SYNTH_WAVE))
def test_ast_accepts_synthetic_wave_strategies(name):
    verify_source(SYNTH_WAVE[name][2], f"{name}.py")


# --------------------------------------------------------------------------------------------------
# 2. C9: varied data with a seed drawn per call, evaluable, second check on the real data
# --------------------------------------------------------------------------------------------------


def test_causality_seed_per_call_and_long_dataset(crit, monkeypatch):
    seen = []
    real = trial.varied_synthetic

    def spy(n_days, n_pairs, seed=None, **kw):
        seen.append((n_days, seed))
        return real(n_days, n_pairs, seed, **kw)

    monkeypatch.setattr(trial, "varied_synthetic", spy)
    src = (STRAT / "side_memory.py").read_bytes()
    r1 = verify_causality(src, {}, crit, n_pairs=6)
    r2 = verify_causality(src, {}, crit, n_pairs=6)
    assert r1["ok"] and r2["ok"]
    assert all(n >= 1300 for n, _ in seen) and r1["n_days"] >= 1300
    assert seen[0][1] != seen[1][1]  # seed: os.urandom, different on every call (None -> drawn inside the generator)


def test_synthetic_varies_random_seed_and_regimes():
    a, b = varied_synthetic(1300, 6), varied_synthetic(1300, 6)
    assert not np.array_equal(a.spot_1d, b.spot_1d)
    assert np.array_equal(varied_synthetic(1300, 6, 7).spot_1d, varied_synthetic(1300, 6, 7).spot_1d)
    a = varied_synthetic(1300, 6, 1)  # fixed seed for the regime assertions (random draws can miss a crash)
    r = a.spot_returns()[:, :].mean(axis=1)
    assert r.min() < -0.05  # at least one crash
    ann = np.array([t.mean() * 1095 for t in a.funding_rate if len(t)])
    assert ann.max() > 0.5 and ann.min() < 0.0  # sustained high and negative funding
    base = a.perp_1h[:, :, -1, 3] / a.spot_1h[:, :, -1, 3] - 1.0
    assert base[a.eligibles_perp].min() < -0.005  # negative basis
    assert (~a.eligibles[:, 5]).any()  # pairs that enter listing


@pytest.mark.parametrize("name", sorted(SYNTH_WAVE))
def test_synthetic_wave_strategies_have_nontrivial_weights_in_causality(crit, name):
    class_, signals, source, params = SYNTH_WAVE[name]
    r = verify_causality(source.encode(), params, crit, class_=class_, n_pairs=15,
                         with_perp=class_ == "hedged" or signals)
    assert r["ok"] and r["evaluable"], r


def test_constant_weights_make_the_report_not_evaluable(crit):
    zero = TEMPLATE.format(body="        return np.zeros(self.n), np.zeros(self.n)").encode()
    r = verify_causality(zero, {}, crit, n_pairs=4, with_1h=False)
    assert r["evaluable"] is False
    assert to_causality_report(r, crit).invariances_ok is False
    r2 = verify_causality((STRAT / "side_memory.py").read_bytes(), {}, crit, n_pairs=6, with_1h=False)
    assert r2["evaluable"] is True and to_causality_report(r2, crit).invariances_ok is False  # without real_ok
    r2["real_ok"] = True  # the replay on real data is added by run_trial
    assert to_causality_report(r2, crit).invariances_ok is True


def test_real_control_detects_a_leak_the_synthetic_misses(tmp_path, journal, crit, monkeypatch):
    # the synthetic check is neutralized: only the replay on the trial's data can catch the leak
    monkeypatch.setattr(trial, "verify_causality", lambda *a, **k: {
        "ok": True, "evaluable": True, "n_cutoffs": 23, "non_full_hour_cutoffs": 10, "deterministic": True,
        "cutoffs_gap": 0.0, "permutation_gap": 0.0, "scale_gap": 0.0})
    trial._CAUSALITY_CACHE.clear()
    panel = synthetic(60, 6, 4, with_1h=False, late_quotes=False)
    r = run_trial(SHEET, STRAT / "column_leak.py", {}, panel, journal, crit, test=True)
    assert r.code == "CAUSALITY" and r.track is None and "real data" in r.detail
    r2 = run_trial(SHEET, STRAT / "side_memory.py", {}, panel, journal, crit, test=True)
    assert r2.code == "OK" and r2.causality["real_ok"] and r2.causality["real_gap"] <= 1e-9
    trial._CAUSALITY_CACHE.clear()


def test_causality_cache_never_serves_other_code_or_parameters(tmp_path, journal, crit, monkeypatch):
    calls = []

    def fake(source, params, criteria, **k):
        calls.append((source, dict(params)))
        return {"ok": True, "evaluable": True, "n_cutoffs": 23, "non_full_hour_cutoffs": 10,
                "deterministic": True, "cutoffs_gap": 0.0, "permutation_gap": 0.0, "scale_gap": 0.0}

    monkeypatch.setattr(trial, "verify_causality", fake)
    trial._CAUSALITY_CACHE.clear()
    panel = synthetic(30, 4, 1, with_1h=False, late_quotes=False)
    src = (STRAT / "side_memory.py").read_text()
    a = tmp_path / "a.py"
    a.write_text(src)
    b = tmp_path / "b.py"
    b.write_text(src + "\n# other code\n")

    def go(p, params):
        run_trial(SHEET, p, params, panel, journal, crit, test=True)

    go(a, {})
    go(a, {})
    assert len(calls) == 1  # same code, same parameters: cache
    go(a, {"k": 2})
    assert len(calls) == 2  # other parameters
    go(b, {})
    assert len(calls) == 3  # other code
    trial._CAUSALITY_CACHE.clear()


# --------------------------------------------------------------------------------------------------
# 3-4. Hedged class: costs of a full exit, strict hedge
# --------------------------------------------------------------------------------------------------


class _Res:
    def __init__(self, track):
        self.track, self.id, self.code, self.universe = track, "R0001", "OK", "main"


def test_hedged_keeps_the_full_exit_cost(crit):
    T = 100
    panel = synthetic(T, 3, 1, with_1h=False, with_perp=True, late_quotes=False, day_start=START_2020)
    ws, wp = np.zeros((T, 3)), np.zeros((T, 3))
    for j in range(T):
        if (j // 10) % 2 == 1 and j >= 20:  # 10 days invested, 10 days flat
            ws[j, 0] = wp[j, 0] = 0.4
    s = simulate(panel, ws, wp, "hedged", crit)
    expo_inv = 0.4 + crit.perp_share_margin * 0.4
    e = to_trial(_Res(s), family="C1", class_="hedged", params={})
    m = s.eval_mask
    assert s.costs[m].sum() > 0
    # total costs of the gates' series = real costs (invested at constant exposure)
    assert e.costs.sum() * expo_inv == pytest.approx(s.costs[m].sum(), rel=1e-12)
    # the day of a full exit (day exposure 0) keeps its cost
    output = np.flatnonzero((s.exposure == 0) & (np.concatenate([[0.0], s.exposure[:-1]]) > 0) & (s.costs > 0))
    assert len(output) >= 2
    assert (immobilized_divisor(s.exposure)[output] == pytest.approx(expo_inv))
    assert np.allclose(s.immobilized_net_returns[output], (s.gross_returns - s.costs)[output] / expo_inv)


def test_gate_metrics_differ_from_total_capital_metrics(tmp_path, journal, crit):
    panel = synthetic(150, 4, 3, with_1h=False, with_perp=True, late_quotes=False, day_start=START_2020)
    r = run_trial(SHEET_C, STRAT / "simple_hedged.py", {"size": 0.3, "k": 2}, panel, journal, crit,
                       causality=False, test=True)
    assert r.code == "OK", r.detail
    end = journal.trials()[r.id]["end"]
    assert "sharpe_net" in end and "gates_sharpe_net" in end and "gates_drawdown" in end
    assert end["net_annualized_return"] != end["gates_net_annualized_return"]
    p = compute_gate_metrics(r.track)
    assert p["gates_sharpe_net"] == r.metrics["gates_sharpe_net"]
    e = to_trial(r, family="C1", class_="hedged", params={})
    assert float(end["gates_sharpe_net"]) == pytest.approx(
        float(e.net.mean() / e.net.std(ddof=1) * math.sqrt(365)), rel=1e-9)


def test_hedged_partial_hedge_allowed_engine_v2():
    from research.engine.trial import ENGINE_VERSION
    from research.engine.portfolio import HEDGED_MIN
    assert HEDGED_MIN == 0.0 and ENGINE_VERSION == "research-engine-v2"  # erratum 5
    cot = np.ones(3, dtype=bool)
    el = np.ones(3, dtype=bool)
    ws = np.array([0.1, 0.1, 0.0])
    for wp in ([0.09, 0.1, 0.0], [0.089, 0.1, 0.0], [0.0, 0.0, 0.0], [0.03, 0.07, 0.0]):  # partial: allowed
        validate_weight("hedged", 0, ws, np.array(wp), cot, el, 0.5)
    validate_weight("hedged", 0, ws, ws.copy(), cot, el, 0.5)
    for wp in ([0.1, 0.1, 0.05], [0.11, 0.1, 0.0], [-0.01, 0.1, 0.0]):  # short > long, perp without spot, negative
        with pytest.raises(WeightShape):
            validate_weight("hedged", 0, ws, np.array(wp), cot, el, 0.5)


# --------------------------------------------------------------------------------------------------
# 5. AST: escape through generator frames
# --------------------------------------------------------------------------------------------------

FRAME_ESCAPE = '''
import numpy as np

class Strategy:
    def __init__(self, n_pairs, **p):
        self.n = n_pairs
        def g():
            yield me.gi_frame.f_back
        me = g()
        f = next(me)
        while f.f_back is not None and "true_import" not in f.f_locals:
            f = f.f_back
        raise RuntimeError(repr(f.f_globals["os"].listdir("/")))
    def step(self, day):
        return np.zeros(self.n), np.zeros(self.n)
'''


def test_frame_escape_refused_by_ast_and_never_run():
    with pytest.raises(SourceRefused, match="forbidden"):
        verify_source(FRAME_ESCAPE)
    with pytest.raises(SourceRefused):
        run_stream(FRAME_ESCAPE.encode(), {}, synthetic(5, 3, 1), ok, 30.0)


@pytest.mark.parametrize("attr", [
    "gi_frame", "gi_code", "cr_frame", "cr_await", "ag_frame", "ag_code", "f_back", "f_locals", "f_globals",
    "f_builtins", "tb_frame", "tb_next", "co_code", "co_consts", "__traceback__", "__code__", "__globals__",
    "__closure__", "__subclasses__", "__mro__", "__bases__", "__class__", "__dict__", "__getattribute__"])
def test_ast_refuses_introspection_attributes(attr):
    with pytest.raises(SourceRefused):
        verify_source(TEMPLATE.format(body=f"        x = day.{attr}\n        return np.zeros(self.n), np.zeros(self.n)"))


# --------------------------------------------------------------------------------------------------
# 6. Journal: anchors after start and end, genesis, arena_journal required, overrides recorded
# --------------------------------------------------------------------------------------------------


def test_anchor_after_start_and_after_end(tmp_path, journal, crit):
    arena = tmp_path / "arena.jsonl"
    panel = synthetic(30, 4, 1, with_1h=False)
    run_trial(SHEET, STRAT / "constant.py", {}, panel, journal, crit, causality=False, arena_journal=arena)
    anchors = [e["payload"] for e in Journal(arena).iter_events()]
    assert [a["n_lines"] for a in anchors] == [2, 3]  # genesis + start; genesis + start + end
    assert all(a["genesis"] == journal.genesis_hash() for a in anchors)
    assert [e["type"] for e in journal.events()] == ["lab_genesis", "start", "end"]


def test_renamed_or_recreated_journal_is_refused(tmp_path, journal, crit):
    arena = tmp_path / "arena.jsonl"
    panel = synthetic(30, 4, 1, with_1h=False)
    run_trial(SHEET, STRAT / "constant.py", {}, panel, journal, crit, causality=False, arena_journal=arena)
    renamed = ResearchJournal(tmp_path / "other.jsonl", lab_repo=journal.lab_repo, clock=lambda: 1_700_000_031)
    renamed.path.write_bytes(journal.path.read_bytes())
    with pytest.raises(AnchorError, match="renam"):
        renamed.verify_anchor(arena)
    # recreated (same name, genesis written at another time, different chain): refused
    journal.path.unlink()
    fresh = ResearchJournal(journal.path, lab_repo=journal.lab_repo, clock=lambda: 1_800_000_000)
    fresh.initialize()
    with pytest.raises(AnchorError, match="genesis"):
        fresh.verify_anchor(arena)
    with pytest.raises(AnchorError):
        run_trial(SHEET, STRAT / "constant.py", {}, panel, fresh, crit, causality=False, arena_journal=arena)
    # recreated with an identical genesis (same clock) but shorter than the latest anchor: refused
    journal.path.unlink()
    short = ResearchJournal(journal.path, lab_repo=journal.lab_repo, clock=lambda: 1_700_000_031)
    short.initialize()
    with pytest.raises(AnchorError, match="latest anchor"):
        short.verify_anchor(arena)


def test_arena_journal_required_outside_tests(tmp_path, journal, crit):
    panel = synthetic(30, 4, 1, with_1h=False, late_quotes=False)
    with pytest.raises(AnchorError, match="arena_journal"):
        run_trial(SHEET, STRAT / "constant.py", {}, panel, journal, crit, causality=False)
    assert journal.n_ids() == 0 and not journal.path.exists()
    r = run_trial(SHEET, STRAT / "constant.py", {}, panel, journal, crit, causality=False, test=True)
    assert r.code == "OK"


def test_start_records_all_overrides(tmp_path, journal, crit):
    panel = synthetic(30, 4, 1, with_1h=False)
    run_trial(SHEET, STRAT / "constant.py", {}, panel, journal, crit, causality=False, test=True,
                   spot_cost_bp=15, perp_cost_bp=3, convention_rotation="target", timeout_s=77)
    s = journal.events("start")[0]["payload"]["overrides"]
    assert s["causality"] is False and s["spot_cost_bp"] == 15 and s["perp_cost_bp"] == 3
    assert s["convention_rotation"] == "target" and str(s["timeout_s"]) == "77"  # never a float in the journal
    assert s["test"] is True


# --------------------------------------------------------------------------------------------------
# 7. Output channels: text and time
# --------------------------------------------------------------------------------------------------


def test_no_strategy_text_in_detail_or_journal(tmp_path, journal, crit):
    panel = synthetic(20, 3, 0, with_1h=False, late_quotes=False)
    case_ = {
        "message": "        raise ValueError('SECRET-42')",
        "custom_class": "        class SecretXYZ(Exception):\n            pass\n        raise SecretXYZ('SECRET-42')",
        "shape": "        return np.zeros(2), np.zeros(self.n)",
        "weight": "        return np.full(self.n, 0.512345678), np.zeros(self.n)",
    }
    for name, body in case_.items():
        p = write(tmp_path, body, name + ".py")
        r = run_trial(SHEET, p, {}, panel, journal, crit, causality=False, test=True)
        assert r.code in ("ERROR", "WEIGHT_SHAPE"), name
        for banned in ("SECRET", "XYZ", "0.5123", "(2,)", "Traceback"):
            assert banned not in r.detail, (name, r.detail)
        assert "day" in r.detail
    assert "ValueError" in journal.technical_path.read_text()
    assert "non_standard_exception" in journal.technical_path.read_text()
    whole = journal.path.read_text() + journal.technical_path.read_text()
    for banned in ("SECRET", "SecretXYZ", "0.5123", "Traceback"):
        assert banned not in whole


def test_timestamps_rounded_to_the_minute(tmp_path, journal, crit):
    arena = tmp_path / "arena.jsonl"
    panel = synthetic(20, 3, 0, with_1h=False, late_quotes=False)
    p = write(tmp_path, "        raise ValueError('x')")
    run_trial(SHEET, p, {}, panel, journal, crit, causality=False, arena_journal=arena)
    expected = 1_700_000_031 - 1_700_000_031 % 60
    assert expected != 1_700_000_031
    assert {e["ts"] for e in journal.journal.iter_events()} == {expected}
    assert json.loads(journal.technical_path.read_text().splitlines()[0])["ts"] == expected
    assert {e["ts"] for e in Journal(arena).iter_events()} == {expected}


def test_n_synthetic_days_and_day_without_date():
    assert trial._SYNTH_DAYS >= 1300
    assert DAY_S == 86400
