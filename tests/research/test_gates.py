"""Tests of research/gates/: DSR (published example, table of §5), statistics, each gate C1-C16 "just
above / just below" on SYNTHETIC series, selection and arena replay (real riskd).

No real market data. The criteria are read from research/criteria.yaml.
"""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import yaml

from research.gates import dsr, evaluate, selection, stats
from research.gates.evaluate import Trial, CausalityReport
from research.gates.arena_replay import POLICY_PATH, replay, symbol_arena

REPO = Path(__file__).resolve().parents[2]
CRIT = yaml.safe_load((REPO / "research" / "criteria.yaml").read_text(encoding="utf-8"))
P = CRIT["gates"]
T_PROTOCOL = 2373


# ----------------------------------------------------------------------------- test tools
def sharpe_series(annual_sharpe: float, n: int = 400, seed: int = 0, std: float = 0.01, index=None) -> pd.Series:
    """Return series whose annualized Sharpe is EXACTLY `annual_sharpe` (standardized)."""
    z = np.random.default_rng(seed).normal(size=n)
    z = (z - z.mean()) / z.std(ddof=1)
    x = z * std + annual_sharpe / math.sqrt(365) * std
    idx = index if index is not None else pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.Series(x, index=idx)


def crossover(f, lo: float, hi: float, n: int = 60) -> float:
    """Boundary of a monotone predicate: f(lo) != f(hi); returns the switching point."""
    flo = f(lo)
    assert f(hi) != flo
    for _ in range(n):
        mid = (lo + hi) / 2
        if f(mid) == flo:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ----------------------------------------------------------------------------- DSR
def test_published_example_bailey_lopez_de_prado():
    # Paper (2014): annualized SR 2.5, T=1250 (250 d/year), skewness -3, kurtosis 10, N=100, annualized V 0.5.
    V = 0.5 / 250
    sr = 2.5 / math.sqrt(250)
    assert dsr.sr_star(V, 100) * math.sqrt(250) == pytest.approx(1.7894, abs=1e-3)
    assert dsr.dsr_prob(sr, 1250, -3.0, 10.0, 100, V) == pytest.approx(0.9004, abs=5e-4)


@pytest.mark.parametrize(
    ("N", "floor", "sd05", "sd07"),
    [(326, 1.79, 2.2, 2.69), (726, 1.89, 2.3, 2.86)],
)
def test_protocol_table_section_5(N, floor, sd05, sd07):
    assert dsr.required_sharpe(N, T_PROTOCOL) == pytest.approx(floor, abs=0.02)
    assert dsr.required_sharpe(N, T_PROTOCOL, dsr.v_from_annual_std(0.7)) == pytest.approx(sd07, abs=0.02)
    # "≈" column of the protocol: within 0.15 (computed values 2.11 and 2.23)
    assert dsr.required_sharpe(N, T_PROTOCOL, dsr.v_from_annual_std(0.5)) == pytest.approx(sd05, abs=0.15)


def test_required_sharpe_is_the_root_of_the_dsr():
    for N in (326, 726):
        req = dsr.required_sharpe(N, T_PROTOCOL, annualized=False)
        V = dsr.variance_floor(T_PROTOCOL)
        assert dsr.dsr_prob(req, T_PROTOCOL, 0.0, 3.0, N, V) == pytest.approx(0.95, abs=1e-9)
        assert dsr.dsr_prob(req * 1.001, T_PROTOCOL, 0.0, 3.0, N, V) > 0.95
        assert dsr.dsr_prob(req * 0.999, T_PROTOCOL, 0.0, 3.0, N, V) < 0.95


def test_dsr_guardrails():
    with pytest.raises(ValueError, match="N=1"):
        dsr.sr_star(1.0, 1)
    with pytest.raises(ValueError):
        dsr.sr_star(0.0, 100)
    with pytest.raises(ValueError):
        dsr.dsr_prob(float("nan"), 100, 0, 3, 10, 1e-3)
    assert dsr.dsr_prob(0.1, 500, -1.0, 10.0, 100, 1e-3) < dsr.dsr_prob(0.1, 500, 0.0, 3.0, 100, 1e-3)


def test_variance_per_class_weighted_by_family_and_floor():
    # family A: 3 trials of variance 4e-4; family B: 2 trials of variance 1e-4; weights 3 and 2
    a = [0.0, 0.02, -0.02]  # var = 4e-4
    b = [0.0, math.sqrt(2) * 0.01]  # var = 1e-4
    v = dsr.class_variance({"A": a, "B": b}, T=10_000)
    assert v == pytest.approx((3 * 4e-4 + 2 * 1e-4) / 5)
    # a family with a single trial has no within-family variance but counts in the overall variance
    assert dsr.class_variance({"A": a, "B": b, "single": [0.5]}, T=10_000) > 3e-2
    # below the 1/(T-1) floor: the floor applies; also with no usable family
    assert dsr.class_variance({"A": [0.0, 1e-6]}, T=100) == pytest.approx(1 / 99)
    assert dsr.class_variance({}, T=100) == pytest.approx(1 / 99)


# ----------------------------------------------------------------------------- statistiques
def test_sharpe_and_annualized_return():
    r = sharpe_series(1.5, n=500)
    assert stats.sharpe(r) == pytest.approx(1.5)
    assert stats.sr_day(r) == pytest.approx(1.5 / math.sqrt(365))
    g = 1.04 ** (1 / 365) - 1
    assert stats.annualized_return(np.full(730, g)) == pytest.approx(0.04)
    assert stats.annualized_return([-1.0, 0.5]) == -1.0


def test_drawdown_compounded_net_asset_value():
    r = np.array([0.1, -0.2, 0.05, -0.1, 0.3])
    nav = np.cumprod(1 + r)
    expected = 1 - 1.1 * 0.8 * 1.05 * 0.9 / (1.1)  # trough after day 4, peak 1.1
    assert stats.drawdown(r) == pytest.approx(expected)
    assert stats.drawdown(np.zeros(5)) == 0.0
    assert nav[-1] > 0


def test_t_newey_west_without_lag_and_with_autocorrelation():
    r = sharpe_series(1.0, n=1000, seed=3)
    n = len(r)
    t0 = stats.t_newey_west(r, 0)
    assert t0 == pytest.approx(r.mean() / (r.std(ddof=0) / math.sqrt(n)))
    # a positively autocorrelated series sees its t drop as lags increase
    rng = np.random.default_rng(5)
    e = rng.normal(size=3000)
    x = np.zeros(3000)
    for i in range(1, 3000):
        x[i] = 0.7 * x[i - 1] + e[i]
    x += 0.05
    assert stats.t_newey_west(x, 20) < stats.t_newey_west(x, 0)


def test_block_bootstrap_reproducible_and_calibrated():
    strong = sharpe_series(3.0, n=1000)
    zero = sharpe_series(0.0, n=1000)
    a = stats.bootstrap_blocks(strong)
    assert a == stats.bootstrap_blocks(strong)  # fixed seed 12345
    assert a["p"] < 0.01
    assert stats.bootstrap_blocks(zero)["p"] > 0.4
    assert stats.bootstrap_blocks(-sharpe_series(3.0, n=1000))["p"] > 0.95
    assert stats.bootstrap_blocks(strong, replications=100)["p"] >= 1 / 101


def test_paired_bootstrap_is_a_bootstrap_of_the_difference():
    a, b = sharpe_series(2.0, seed=1), sharpe_series(0.5, seed=2)
    assert stats.bootstrap_paired(a, b) == stats.bootstrap_blocks(a - b)
    # alignment by index: a date offset reduces to the intersection
    p1 = stats.bootstrap_paired(a, b.iloc[50:])
    p2 = stats.bootstrap_blocks((a - b).iloc[50:])
    assert p1 == p2


def test_alpha_beta_regression_recovers_the_parameters():
    rng = np.random.default_rng(11)
    x = pd.Series(rng.normal(0, 0.02, 3000), index=pd.date_range("2018-01-01", periods=3000))
    y = 0.001 + 0.25 * x + pd.Series(rng.normal(0, 0.003, 3000), index=x.index)
    reg = stats.regression_alpha_beta(y, x, 20)
    assert reg["beta"] == pytest.approx(0.25, abs=0.02)
    assert reg["alpha_day"] == pytest.approx(0.001, abs=3e-4)
    assert reg["alpha_annual"] == pytest.approx(reg["alpha_day"] * 365)
    assert reg["t_alpha"] > 5
    # no alpha: small t
    y0 = 0.25 * x + pd.Series(rng.normal(0, 0.003, 3000), index=x.index)
    assert abs(stats.regression_alpha_beta(y0, x, 20)["t_alpha"]) < 3


def test_removal_of_the_best_days():
    idx = pd.date_range("2020-01-01", periods=T_PROTOCOL)
    r = pd.Series(np.random.default_rng(0).normal(size=T_PROTOCOL), index=idx)
    r1, k1 = stats.remove_best_days(r, 0.01)
    _, k2 = stats.remove_best_days(r, 0.02)
    assert (k1, len(r1)) == (24, T_PROTOCOL - 24)  # protocol's "1% best days (24 days)"
    assert k2 == 48
    assert r1.max() < r.nlargest(24).min() + 1e-15
    assert r1.index.is_monotonic_increasing


def test_sharpe_per_year_and_halves():
    idx = pd.date_range("2020-01-01", "2025-12-31")
    r = pd.Series(np.random.default_rng(0).normal(0.001, 0.01, len(idx)), index=idx)
    sh = stats.sharpe_per_year(r, [2019, 2020, 2025])
    assert math.isnan(sh[2019])
    assert sh[2020] == pytest.approx(stats.sharpe(r[r.index.year == 2020]))
    a, b = stats.sharpe_halves(r)
    h = len(r) // 2
    assert (a, b) == (stats.sharpe(r.iloc[:h]), stats.sharpe(r.iloc[h:]))


# ----------------------------------------------------------------------------- gates, one by one
def test_c1_just_above_and_below():
    n = T_PROTOCOL
    base = sharpe_series(0.0, n=n, seed=7)
    sk, ku = stats.moments(base)
    N = CRIT["trials"]["N_dsr"]
    V = dsr.variance_floor(n)
    req = dsr.required_sharpe(N, n, skew=sk, kurt=ku, annualized=True)
    top = sharpe_series(req + 0.002, n=n, seed=7)
    low = sharpe_series(req - 0.002, n=n, seed=7)
    (ok_h, d_h, s_h), _ = evaluate.gate_c1(top, N, V, P["C1_dsr_min"])
    (ok_b, d_b, _), _ = evaluate.gate_c1(low, N, V, P["C1_dsr_min"])
    assert ok_h and not ok_b
    assert d_h >= s_h == 0.95 > d_b
    # a class variance above the floor hardens the gate
    (ok_v, _, _), _ = evaluate.gate_c1(top, N, 100 * V, P["C1_dsr_min"])
    assert not ok_v


def _years(sharpes: dict[int, float]) -> pd.Series:
    parts = []
    for a, s in sharpes.items():
        idx = pd.date_range(f"{a}-01-01", f"{a}-12-31")
        parts.append(sharpe_series(s, n=len(idx), seed=a, index=idx))
    return pd.concat(parts)


def test_c5_years():
    cfg = P["C5_years"]
    ok = {a: 0.5 for a in range(2020, 2026)}
    assert evaluate.gate_c5(_years(ok), cfg)[0]
    # a year just below -1: failure; just above: pass
    assert not evaluate.gate_c5(_years({**ok, 2022: -1.001}), cfg)[0]
    assert evaluate.gate_c5(_years({**ok, 2022: -0.999}), cfg)[0]
    # exactly 4 positive: pass (2 negative but > -1); 3 positive: failure
    assert evaluate.gate_c5(_years({**ok, 2021: -0.5, 2022: -0.5}), cfg)[0]
    assert not evaluate.gate_c5(_years({**ok, 2021: -0.5, 2022: -0.5, 2023: -0.5}), cfg)[0]
    # missing year: failure
    assert not evaluate.gate_c5(_years({a: 0.5 for a in range(2020, 2025)}), cfg)[0]


@pytest.mark.parametrize("class_", ["directional", "hedged"])
def test_c6_drawdown(class_):
    lim = P["C6_drawdown_max"][class_]
    n = 200

    def with_drop(d: float) -> pd.Series:
        r = np.zeros(n)
        r[50] = -d
        return pd.Series(r, index=pd.date_range("2020-01-01", periods=n))

    assert evaluate.gate_c6(with_drop(lim - 0.001), class_, P["C6_drawdown_max"])[0]
    assert evaluate.gate_c6(with_drop(lim), class_, P["C6_drawdown_max"])[0]  # ≤ inclusive
    assert not evaluate.gate_c6(with_drop(lim + 0.001), class_, P["C6_drawdown_max"])[0]


GRID = {"a": [4.0, 6.0, 9.0], "b": [10.0, 15.0, 22.5]}


def _trial(params, sharpe, seed, family="F", class_="directional", n=400) -> Trial:
    net = sharpe_series(sharpe, n=n, seed=seed)
    z = pd.Series(0.0, index=net.index)
    return Trial(f"{params}", family, class_, params, net, net, net, z, z)


def _neighborhood(sh_neighbors: list[float], s_cand=2.0, params=None):
    params = params or {"a": 6.0, "b": 15.0}
    cand = _trial(params, s_cand, 0)
    neighbors = [
        _trial({"a": 4.0, "b": 15.0}, sh_neighbors[0], 1),
        _trial({"a": 9.0, "b": 15.0}, sh_neighbors[1], 2),
        _trial({"a": 6.0, "b": 10.0}, sh_neighbors[2], 3),
        _trial({"a": 6.0, "b": 22.5}, sh_neighbors[3], 4),
    ]
    return cand, [cand, *neighbors]


def test_c7_neighborhood():
    cfg = P["C7_neighborhood"]
    # neighbor threshold = max(0.6 x 2.0; 0.5) = 1.2; 3 neighbors out of 4 = 75%: pass
    cand, all_results = _neighborhood([1.21, 1.21, 1.21, 0.0])
    (ok, part, _), _ = evaluate.gate_c7(cand, all_results, GRID, cfg, CRIT["trials"])
    assert ok and part == 0.75
    # just below the neighbor Sharpe threshold: 2 out of 4 -> failure
    cand, all_results = _neighborhood([1.19, 1.21, 1.21, 0.0])
    (ok, part, _), _ = evaluate.gate_c7(cand, all_results, GRID, cfg, CRIT["trials"])
    assert not ok and part == 0.5
    # absolute floor 0.5: candidate at 0.6 -> threshold 0.5 (not 0.36)
    cand, all_results = _neighborhood([0.51, 0.51, 0.51, 0.49], s_cand=0.6)
    assert evaluate.gate_c7(cand, all_results, GRID, cfg, CRIT["trials"])[0][0]
    cand, all_results = _neighborhood([0.49, 0.51, 0.51, 0.49], s_cand=0.6)
    assert not evaluate.gate_c7(cand, all_results, GRID, cfg, CRIT["trials"])[0][0]


def test_c7_structural_failures():
    cfg = P["C7_neighborhood"]
    good_count = [3.0, 3.0, 3.0, 3.0]
    # grid edge
    cand, all_results = _neighborhood(good_count, params={"a": 4.0, "b": 15.0})
    assert not evaluate.gate_c7(cand, all_results, GRID, cfg, CRIT["trials"])[0][0]
    # neighbor not evaluated
    cand, all_results = _neighborhood(good_count)
    assert not evaluate.gate_c7(cand, all_results[:-1], GRID, cfg, CRIT["trials"])[0][0]
    # grid not declared, too short, or ratio < 1.25
    assert not evaluate.gate_c7(cand, all_results, None, cfg, CRIT["trials"])[0][0]
    assert not evaluate.gate_c7(cand, all_results, {"a": [4.0, 6.0], "b": [10.0, 15.0]}, cfg, CRIT["trials"])[0][0]
    ok, _ = evaluate.grid_valid({"a": [1.0, 1.25, 1.5625]}, CRIT["trials"])
    assert ok
    ok, _ = evaluate.grid_valid({"a": [1.0, 1.24, 1.54]}, CRIT["trials"])
    assert not ok
    # a neighbor from ANOTHER family does not count
    cand, all_results = _neighborhood(good_count)
    other = [Trial(**{**t.__dict__, "family": "G"}) if i == 1 else t for i, t in enumerate(all_results)]
    assert not evaluate.gate_c7(cand, other, GRID, cfg, CRIT["trials"])[0][0]


def test_c8_directional_switches_on_p():
    cfg = P["C8_directional"]
    basket = sharpe_series(0.0, n=1500, seed=21, std=0.02)
    noise = sharpe_series(0.0, n=1500, seed=22, std=0.01)

    def succeeds(delta: float) -> bool:
        return evaluate.gate_c8_directional(basket + noise + delta, basket, cfg)[0]

    assert not succeeds(0.0)
    d = crossover(succeeds, 0.0, 0.003, n=25)
    assert succeeds(d * 1.02) and not succeeds(d * 0.98)
    _, p, threshold = evaluate.gate_c8_directional(basket + noise + d * 1.02, basket, cfg)
    assert threshold == 0.05 and p <= 0.05 + 1e-9
    assert not evaluate.gate_c8_directional(basket, None, cfg)[0]  # basket absent: failure


def test_c8_hedged_alpha_and_beta():
    cfg = P["C8_hedged"]
    rng = np.random.default_rng(3)
    idx = pd.date_range("2020-01-01", periods=2000)
    x = pd.Series(rng.normal(0, 0.02, 2000), index=idx)
    u = pd.Series(rng.normal(0, 0.003, 2000), index=idx)

    def t_ok(alpha: float) -> bool:
        return evaluate.gate_c8_hedged(alpha + 0.1 * x + u, x, cfg)[0]

    assert not t_ok(0.0)
    a = crossover(t_ok, 0.0, 0.002, n=30)
    assert t_ok(a * 1.01) and not t_ok(a * 0.99)
    # beta: comfortable alpha, |beta| just below / above 0.3 (positive and negative)
    for sign in (1, -1):
        assert evaluate.gate_c8_hedged(0.003 + sign * 0.29 * x + u, x, cfg)[0]
        assert not evaluate.gate_c8_hedged(0.003 + sign * 0.31 * x + u, x, cfg)[0]


def test_c9_causality():
    cfg = P["C9_causality"]
    ok = CausalityReport(20, 3, 0.4, 1e-9)
    assert evaluate.gate_c9(ok, cfg)[0]
    assert not evaluate.gate_c9(CausalityReport(20, 3, 0.4, 1.0001e-9), cfg)[0]  # tolerance 1e-9
    assert not evaluate.gate_c9(CausalityReport(20, 3, 0.39, 0.0), cfg)[0]  # 40 % of hours not full
    assert not evaluate.gate_c9(CausalityReport(19, 3, 0.5, 0.0), cfg)[0]
    assert not evaluate.gate_c9(CausalityReport(20, 2, 0.5, 0.0), cfg)[0]
    assert not evaluate.gate_c9(CausalityReport(20, 3, 0.5, 0.0, invariances_ok=False), cfg)[0]
    assert not evaluate.gate_c9(CausalityReport(20, 3, 0.5, float("nan")), cfg)[0]
    assert not evaluate.gate_c9(None, cfg)[0]


def test_c11_extremes_crossover():
    cfg = P["C11_extremes"]
    n = T_PROTOCOL

    def gate(sharpe_base: float):
        return evaluate.gate_c11(sharpe_series(sharpe_base, n=n, seed=9), cfg)

    # removing the 24 best days costs about 0.5 of Sharpe: the gate flips around 1.0
    assert not gate(0.8)[0]
    assert gate(2.0)[0]
    b = crossover(lambda x: gate(x)[0], 0.8, 2.0, n=40)
    assert gate(b * 1.01)[0] and not gate(b * 0.99)[0]
    # first-tier threshold: max(0.5; 0.5 x full Sharpe)
    assert gate(0.8)[2][0] == pytest.approx(0.5)
    assert gate(5.0)[2][0] == pytest.approx(2.5)
    # second tier: below 0 after removing 2%, even if the first tier passes
    zero = sharpe_series(0.0, n=n, seed=9)
    r = zero.copy()
    r.iloc[np.arange(40) * 50 + 3] += 0.05  # 40 days (> 1% but < 2%), 24 removed leave a positive Sharpe
    ok, (_, s2), _ = evaluate.gate_c11(r, cfg)
    assert s2 < 0.5 * stats.sharpe(r) and not ok


def test_c12_cost_and_rotation():
    cfg = P["C12_costs"]
    n = 365 * 4
    idx = pd.date_range("2020-01-01", periods=n)
    gross = pd.Series(0.001, index=idx)

    def gate(day_cost: float, annual_rot: float, class_="directional"):
        return evaluate.gate_c12(
            gross, pd.Series(day_cost, index=idx), pd.Series(annual_rot / 365, index=idx), class_, cfg, CRIT["classes"]
        )

    assert gate(0.00049, 10)[0] and gate(0.0005, 10)[0]
    assert not gate(0.00051, 10)[0]
    assert gate(0.0001, 15)[0] and not gate(0.0001, 15.01)[0]
    assert gate(0.0001, 40, "hedged")[0] and not gate(0.0001, 40.01, "hedged")[0]
    # zero or negative gross return: failure
    z = pd.Series(0.0, index=idx)
    assert not evaluate.gate_c12(z, z, z, "directional", cfg, CRIT["classes"])[0]


def test_c13_halves():
    cfg = P["C13_halves"]
    n = 400

    def two(m1: float, m2: float) -> pd.Series:
        a = sharpe_series(0.0, n=n // 2, seed=1, std=0.01) + m1
        b = sharpe_series(0.0, n=n // 2, seed=2, std=0.01) + m2
        return pd.concat([a, b]).set_axis(pd.date_range("2020-01-01", periods=n))

    assert evaluate.gate_c13(two(1e-5, 1e-5), cfg)[0]
    assert not evaluate.gate_c13(two(1e-5, -1e-5), cfg)[0]
    assert not evaluate.gate_c13(two(-1e-5, 1e-5), cfg)[0]
    assert not evaluate.gate_c13(two(-1e-5, -1e-5), cfg)[0]


def test_c14_materiality():
    cfg = P["C14_materiality"]
    idx = pd.date_range("2020-01-01", periods=730)
    assert evaluate.gate_c14(pd.Series(1.0401 ** (1 / 365) - 1, index=idx), cfg)[0]
    assert not evaluate.gate_c14(pd.Series(1.0399 ** (1 / 365) - 1, index=idx), cfg)[0]


def test_c15_sharpe_strictly_positive():
    cfg, c6 = P["C15_arena"], P["C6_drawdown_max"]
    pos = SimpleNamespace(returns=sharpe_series(0.01, n=300))
    neg = SimpleNamespace(returns=sharpe_series(-0.01, n=300))
    devnull_fd = SimpleNamespace(returns=pd.Series(0.0, index=pd.date_range('2020-01-01', periods=300)))
    assert evaluate.gate_c15(pos, "directional", cfg, c6)[0]
    assert not evaluate.gate_c15(neg, "directional", cfg, c6)[0]
    assert not evaluate.gate_c15(devnull_fd, "directional", cfg, c6)[0]
    assert not evaluate.gate_c15(None, "directional", cfg, c6)[0]


@pytest.mark.parametrize(("class_", "lim"), [("directional", 0.585), ("hedged", 0.26)])
def test_c15_drawdown_just_under_and_on_the_limit(class_, lim):
    cfg, c6 = P["C15_arena"], P["C6_drawdown_max"]
    base = pd.Series(0.002, index=pd.date_range("2020-01-01", periods=3000))

    def gate(dd: float):
        s = base.copy()
        s.iloc[100] = -dd
        return evaluate.gate_c15(SimpleNamespace(returns=s), class_, cfg, c6)

    ok, (sh, _), threshold = gate(lim - 0.002)
    assert sh > 0 and ok and threshold[1] == pytest.approx(lim)
    assert not gate(lim + 0.002)[0]


def test_c16_outside_universe():
    cfg = P["C16_outside_universe"]
    size = CRIT["data"]["control_universe"]["size"]
    assert size == 20

    def d(n_pos: int, n_neg: int, n_none: int = 0, n_not_evaluable: int = 0):
        out = {f"P{i}": SimpleNamespace(net=sharpe_series(1.0, seed=i)) for i in range(n_pos)}
        out.update({f"N{i}": SimpleNamespace(net=sharpe_series(-1.0, seed=i)) for i in range(n_neg)})
        out.update({f"X{i}": None for i in range(n_none)})
        out.update({f"E{i}": evaluate.NOT_EVALUABLE for i in range(n_not_evaluable)})
        return out

    # fixed denominator 20: 12 positives out of 20 = exactly 60%
    assert evaluate.gate_c16(d(12, 8), cfg, size)[0]
    assert not evaluate.gate_c16(d(11, 9), cfg, size)[0]
    # 6 positives out of only 10 symbols is no longer 60%: the denominator stays 20
    assert not evaluate.gate_c16(d(6, 4), cfg, size)[0]
    # a failed symbol (None) counts as a failure in the denominator
    assert not evaluate.gate_c16(d(11, 0, n_none=9), cfg, size)[0]
    assert evaluate.gate_c16(d(12, 0, n_none=8), cfg, size)[0]
    # not evaluable: not in the numerator, not in the minimum of 10, denominator unchanged
    assert evaluate.gate_c16(d(12, 0, n_not_evaluable=8), cfg, size)[0]
    assert not evaluate.gate_c16(d(9, 0, n_not_evaluable=11), cfg, size)[0]  # 9 evaluable < 10
    assert not evaluate.gate_c16(d(10, 0, n_not_evaluable=10), cfg, size)[0]  # 10 evaluable, 50% < 60%
    val = evaluate.gate_c16(d(12, 0, n_not_evaluable=8), cfg, size)[1]
    assert val == (0.6, 12, 12, 8, 20)
    assert not evaluate.gate_c16({}, cfg, size)[0] and not evaluate.gate_c16(None, cfg, size)[0]
    # NaN Sharpe (flat series) = failure
    flat = SimpleNamespace(net=pd.Series(0.0, index=pd.date_range("2020-01-01", periods=300)))
    without = {**d(12, 0), "Z": flat}
    assert evaluate.gate_c16(without, cfg, size)[1][1] == 12


# ----------------------------------------------------------------------------- full evaluator
IDX = pd.date_range("2020-01-01", "2026-06-30")


def _perfect_candidate(class_: str = "directional"):
    n = len(IDX)

    def one(params, seed, sharpe=2.9):
        net = sharpe_series(sharpe, n=n, seed=seed, std=0.01, index=IDX)
        rot = pd.Series(10.0 / 365, index=IDX)
        costs = rot * 0.006
        return Trial(f"{params}", "F", class_, params, net, net - 0.00005, net + costs, rot, costs)

    cand = one({"a": 6.0, "b": 15.0}, 100)
    neighbors = [
        one({"a": 4.0, "b": 15.0}, 101),
        one({"a": 9.0, "b": 15.0}, 102),
        one({"a": 6.0, "b": 10.0}, 103),
        one({"a": 6.0, "b": 22.5}, 104),
    ]
    kw = {
        "all_results": [cand, *neighbors],
        "criteria": CRIT,
        "sheet_grid": GRID,
        "basket": sharpe_series(0.0, n=n, seed=200, std=0.02, index=IDX),
        "results_arena": SimpleNamespace(returns=sharpe_series(1.0, n=n, seed=201, index=IDX)),
        "results_control": {f"S{i}": SimpleNamespace(net=sharpe_series(0.8, n=n, seed=300 + i, index=IDX)) for i in range(20)},
        "causality": CausalityReport(20, 3, 0.45, 0.0),
    }
    return cand, kw


def test_perfect_candidate_passes_everything():
    cand, kw = _perfect_candidate()
    v = evaluate.evaluate_candidate(cand, **kw)
    assert set(v.gates) == {"C1", "C5", "C6", "C7", "C8", "C9", "C11", "C12", "C13", "C14", "C15", "C16"}
    assert set(v.consistency) == {"C2", "C3", "C4", "C10"}
    assert v.passed, v.failures()
    assert v.details["C1"]["N"] == 726  # fixed N, never the current N
    assert v.details["C1"]["V"] >= 1 / (v.details["T"] - 1)


def test_hedged_candidate_uses_the_alpha_beta_branch():
    cand, kw = _perfect_candidate("hedged")
    # the test candidate is uncorrelated with the basket with a high Sharpe: high alpha t, beta ~ 0
    v = evaluate.evaluate_candidate(cand, **kw)
    t, beta = v.gates["C8"][1]
    assert t > 2 and abs(beta) < 0.3 and v.gates["C8"][0]
    assert v.gates["C6"][2] == 0.20


def test_each_gate_can_fail_alone():
    cand, kw = _perfect_candidate()
    n = len(IDX)
    assert evaluate.evaluate_candidate(cand, **{**kw, "causality": None}).failures() == ["C9"]
    assert evaluate.evaluate_candidate(cand, **{**kw, "basket": None}).failures() == ["C8"]
    assert evaluate.evaluate_candidate(cand, **{**kw, "results_arena": None}).failures() == ["C15"]
    assert evaluate.evaluate_candidate(cand, **{**kw, "results_control": None}).failures() == ["C16"]
    assert evaluate.evaluate_candidate(cand, **{**kw, "sheet_grid": None}).failures() == ["C7"]
    # hedged class with the same candidate: only the turnover (40) and the drawdown (20%) change the verdict
    bad = Trial(**{**cand.__dict__, "rotation": pd.Series(16.0 / 365, index=IDX)})
    assert evaluate.evaluate_candidate(bad, **{**kw, "all_results": [bad, *kw["all_results"][1:]]}).failures() == ["C12"]
    # degraded net series: the Sharpe falls below C2 and the DSR below C1
    weak = sharpe_series(0.4, n=n, seed=100, index=IDX)
    c = Trial(**{**cand.__dict__, "net": weak, "net_stress": weak})
    scale_array = evaluate.evaluate_candidate(c, **{**kw, "all_results": [c, *kw["all_results"][1:]]}).failures()
    assert "C1" in scale_array and "C2" in scale_array and "C3" in scale_array


def test_stress_and_bootstrap_consistency():
    cand, kw = _perfect_candidate()
    worst = sharpe_series(-0.1, n=len(IDX), seed=100, index=IDX)
    c = Trial(**{**cand.__dict__, "net_stress": worst})
    v = evaluate.evaluate_candidate(c, **{**kw, "all_results": [c, *kw["all_results"][1:]]})
    assert v.failures() == ["C4"] and not v.passed


def test_unknown_class_is_refused():
    cand, kw = _perfect_candidate()
    bad = Trial(**{**cand.__dict__, "class_": "neutral"})
    with pytest.raises(ValueError):
        evaluate.evaluate_candidate(bad, **kw)


def test_accepts_the_project_criteria_object():
    config = pytest.importorskip("research.config")
    crit = config.load_criteria()
    cand, kw = _perfect_candidate()
    assert evaluate.evaluate_candidate(cand, **{**kw, "criteria": crit}).passed


# ----------------------------------------------------------------------------- selection
def _correlated_pair(rho: float, n: int = 500):
    rng = np.random.default_rng(4)
    z1, z2 = rng.normal(size=n), rng.normal(size=n)
    z1 = (z1 - z1.mean()) / z1.std()
    z2 = z2 - z2.mean()
    z2 -= (z2 @ z1) / (z1 @ z1) * z1
    z2 /= z2.std()
    idx = pd.date_range("2020-01-01", periods=n)
    return pd.Series(z1, index=idx), pd.Series(rho * z1 + math.sqrt(1 - rho**2) * z2, index=idx)


def test_selection_correlation_just_under_and_above():
    for rho, guard in ((0.69, True), (0.71, False)):
        a, b = _correlated_pair(rho)
        s = selection.select_candidates([selection.Candidate("b", 0.96, b), selection.Candidate("a", 0.99, a)], CRIT)
        assert s.retained == (("a", "b") if guard else ("a",))
        assert s.correlations[("a", "b")] == pytest.approx(rho, abs=1e-9)
        if not guard:
            assert "b" in s.discarded and "correlation" in s.discarded["b"]


def test_selection_at_most_three_ranked_by_dsr():
    rng = np.random.default_rng(8)
    idx = pd.date_range("2020-01-01", periods=600)
    cs = [selection.Candidate(f"c{i}", 0.951 + 0.001 * i, pd.Series(rng.normal(size=600), index=idx)) for i in range(5)]
    s = selection.select_candidates(cs, CRIT)
    assert s.retained == ("c4", "c3", "c2")
    assert set(s.discarded) == {"c1", "c0"}
    assert s.p_at_least_one_not_refuted == pytest.approx(1 - (1 - selection.P_NOT_REFUTED_H0_DEFAULT) ** 3)
    assert selection.select_candidates([], CRIT).retained == ()
    assert selection.prob_at_least_one_not_refuted(0) == 0.0


# ----------------------------------------------------------------------------- arena replay
PAIRS = CRIT["data"]["arena_universe"]


def _market(n=250, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    px = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.02, (n, 6)), 0)), index=idx, columns=PAIRS)
    return px


def test_strategy_policy_passes_validate_policy():
    from arena.risk.policy import load_policy, validate_policy

    pol = load_policy(POLICY_PATH)
    validate_policy(pol)
    assert len(pol.sha256) == 64
    assert set(pol.symbols) == {symbol_arena(s) for s in PAIRS}
    assert (pol.max_order_bp, pol.max_position_bp, pol.max_exposure_bp) == (10000, 10000, 10000)
    assert pol.max_trades_per_day == 12


def test_replay_constant_weights_match_the_independent_accounting():
    px = _market()
    w = pd.DataFrame(1 / 6, index=px.index, columns=PAIRS)
    res = replay(w, px)
    assert res.rejected == {} and res.n_orders == res.n_fills > 0
    # independent accounting: gross return of the basket rebalanced every day, cost 60 bp x turnover
    r = px.pct_change().fillna(0.0).to_numpy()
    wa = np.full(6, 1 / 6)
    att = []
    w_last = np.zeros(6)
    for t in range(len(px)):
        rb = float(w_last @ r[t])
        rot = float(np.abs(wa - w_last).sum())
        net = (1 + rb) * (1 - 0.006 * rot) / 1 - 1 if t else -0.006 * rot
        att.append(net)
        w_last = wa * (1 + r[t]) / (1 + float(wa @ r[t]))
    # day 0 buys 100%; then the drift is rebalanced: independent turnover above (Δw on day t
    # = target weight - drifted weight of the previous day, applied after the day t return)
    gap = (res.returns.to_numpy() - np.array(att))
    assert abs(gap.mean()) < 2e-5 and np.abs(gap).max() < 1e-3


def test_replay_round_trip_cost_is_60_bp_per_rotation():
    px = _market(n=4, seed=2)
    px.iloc[:] = 100.0  # constant prices: only the cost acts
    w = pd.DataFrame(0.0, index=px.index, columns=PAIRS)
    w.iloc[0, 0] = 1.0  # buy 100% on day 0; full sale on day 2
    w.iloc[1, 0] = 1.0
    res = replay(w, px)
    assert res.returns.iloc[0] == pytest.approx(-0.0060, abs=2e-4)  # buy: 60 pb
    assert res.returns.iloc[1] == pytest.approx(0.0, abs=1e-6)
    assert res.returns.iloc[2] == pytest.approx(-0.0060, abs=2e-4)  # sell: 60 pb
    assert res.returns.iloc[3] == 0.0


def test_replay_really_goes_through_riskd():
    px = _market(n=30)
    w = pd.DataFrame(0.0, index=px.index, columns=PAIRS)
    w[PAIRS[0]] = 1.0  # 100% on one pair
    assert replay(w, px).rejected == {}
    # tightened policy (temporary copy): riskd REJECTS, the replay counts and does not execute
    text = POLICY_PATH.read_text(encoding="utf-8").replace("max_position_bp = 10000", "max_position_bp = 5000")
    text = text.replace("max_order_bp    = 10000", "max_order_bp    = 5000")
    tmp = Path(__file__).parent / "_policy_tmp.toml"
    try:
        tmp.write_text(text, encoding="utf-8")
        res = replay(w, px, policy_path=tmp)
    finally:
        tmp.unlink(missing_ok=True)
    assert res.rejected.get("MAX_ORDER_SIZE", 0) > 0
    assert (res.returns == 0.0).all() and res.n_fills == 0
    assert all(len(c) > 0 for _, _, c in res.orders_rejected)


def test_replay_refuses_invalid_weights_and_different_indexes():
    px = _market(n=10)
    w = pd.DataFrame(0.2, index=px.index, columns=PAIRS)  # sum 1.2
    with pytest.raises(ValueError, match="weights out of bounds"):
        replay(w, px)
    w2 = pd.DataFrame(0.1, index=px.index, columns=PAIRS)
    with pytest.raises(ValueError, match="index"):
        replay(w2, px.iloc[1:])
    with pytest.raises(ValueError, match="USDT"):
        symbol_arena("BTCEUR")
    assert symbol_arena("LINKUSDT") == "LINK/EUR"


def test_replay_pair_without_price_is_ignored():
    px = _market(n=20)
    px.iloc[:5, 0] = np.nan  # BTC not yet listed
    w = pd.DataFrame(1 / 6, index=px.index, columns=PAIRS)
    res = replay(w, px)
    assert res.rejected == {} and np.isfinite(res.returns).all()
