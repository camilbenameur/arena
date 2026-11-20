"""Evaluation of a candidate's gates C1-C16 (PROTOCOL §6, thresholds from criteria.yaml).

No LLM, no performance computation anywhere but in the engine: this module receives the DAILY SERIES
produced by the engine (net, stressed net, gross, turnover, costs) and applies the criteria to them. A gate
that cannot be evaluated (missing data, NaN) FAILS; nothing is ever rounded in the candidate's favor.

`criteria`: `research.config.Criteria` object or dict of the YAML root (access by key only).

Trial input: any object with the attributes of `Trial` (the engine may supply its own).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from research.gates import dsr as dsr_mod
from research.gates import stats

Gate = tuple[bool, Any, Any]  # (passed, measured value, threshold)


@dataclass(frozen=True)
class Trial:
    """Daily series (index = UTC dates of the evaluation window) of a trial.

    net, net_stress, gross: daily returns on the tied-up capital (perp margin included);
    rotation: daily sum of |Δw| (each leg counted); costs: daily cost paid as a share of the
    capital (net = gross - costs, funding excluded, it is in gross). `net_stress`: costs x2.
    """

    id: str
    family: str
    class_: str  # "directional" | "hedged"
    params: Mapping[str, float]
    net: pd.Series
    net_stress: pd.Series
    gross: pd.Series
    rotation: pd.Series
    costs: pd.Series
    universe: str = "main"


@dataclass(frozen=True)
class CausalityReport:
    """Summary of the C9 test on synthetic data (produced by the engine).

    max_gap: largest absolute difference between the output truncated at the cutoff and the full output on
    the earlier days, over all cutoffs; not_full_hour_share: share of the cutoffs whose
    instant is not a full UTC hour.
    """

    n_random_cuts: int
    n_fixed: int
    not_full_hour_share: float
    max_gap: float
    invariances_ok: bool = True  # column permutation, price/volume scale (§3)


@dataclass(frozen=True)
class Verdict:
    gates: dict[str, Gate]
    consistency: dict[str, Gate]
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)

    def failures(self) -> list[str]:
        return [k for k, (ok, _, _) in {**self.gates, **self.consistency}.items() if not ok]


# ----------------------------------------------------------------------------- utilities
def section(criteria: Any, name: str):
    """Section `name` of `criteria`: YAML dict (access by key) or `Criteria` object (access by attribute)."""
    if isinstance(criteria, Mapping):
        return criteria[name]
    return getattr(criteria, name)


def _finite(x) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _ok_ge(value, threshold) -> bool:
    return _finite(value) and value >= threshold


def _ok_gt(value, threshold) -> bool:
    return _finite(value) and value > threshold


def _ok_le(value, threshold) -> bool:
    return _finite(value) and value <= threshold


# ----------------------------------------------------------------------------- C1
def variance_of_class(class_: str, all_results: Sequence[Any], T: int,
                       research_sr_days: Mapping[str, Mapping[str, Sequence[float]]] | None = None) -> float:
    """V of the class (PROTOCOL §5 hardened): max(1/(T-1), weighted mean within-family variance, variance
    of all the class's sr_day).

    `research_sr_days`: class -> family -> sr_day of ALL the research trials (main universe) of the
    journal, all waves and resumptions included (`wave.journal_sr_days`). Without it (tests, isolated
    use), the trials of `all_results` of the class are used, main universe."""
    if research_sr_days is not None:
        return dsr_mod.class_variance(dict(research_sr_days.get(class_, {})), T)
    per_family: dict[str, list[float]] = {}
    for r in all_results:
        if r.class_ != class_ or getattr(r, "universe", "main") != "main":
            continue
        s = stats.sr_day(r.net)
        if _finite(s):
            per_family.setdefault(r.family, []).append(s)
    return dsr_mod.class_variance(per_family, T)


def gate_c1(net, N: int, V: float, threshold: float) -> tuple[Gate, dict]:
    T = len(net)
    s = stats.sr_day(net)
    sk, ku = stats.moments(net)
    try:
        d = dsr_mod.dsr_prob(s, T, sk, ku, N, V)
    except ValueError:
        d = float("nan")
    return (_ok_ge(d, threshold), d, threshold), {"N": N, "V": V, "T": T, "sr_day": s, "skew": sk, "kurt": ku,
                                           "sr_star": dsr_mod.sr_star(V, N)}


# ----------------------------------------------------------------------------- C5
def gate_c5(net: pd.Series, cfg) -> Gate:
    """Calendar years: none below `min_sharpe_per_year`, at least `min_positive_years` positive.

    A year with exactly zero returns (strategy flat all year: zero standard deviation, NaN Sharpe) is
    treated as "not positive and not below −1" (Sharpe 0.0): it does not fail C5 by itself but
    does not count among the positive years. A missing year (fewer than 2 days) remains a failure."""
    years = list(cfg["years"])
    sh = stats.sharpe_per_year(net, years, flat_is_zero=True)
    vals = [sh[a] for a in years]
    if not all(_finite(v) for v in vals):
        return (False, sh, dict(cfg))
    ok = all(v >= cfg["min_sharpe_per_year"] for v in vals) and (
        sum(1 for v in vals if v > 0) >= cfg["min_positive_years"]
    )
    return (ok, sh, {"sharpe_min": cfg["min_sharpe_per_year"], "positives_min": cfg["min_positive_years"]})


# ----------------------------------------------------------------------------- C6
def gate_c6(net, class_: str, cfg) -> Gate:
    dd = stats.drawdown(net)
    threshold = cfg[class_]
    return (_ok_le(dd, threshold), dd, threshold)


# ----------------------------------------------------------------------------- C7
def grid_valid(grid: Mapping[str, Sequence[float]], cfg_trials) -> tuple[bool, str]:
    """At least 3 values per parameter, ratio >= 1.25 between neighboring values (geometric grid)."""
    gmin = cfg_trials["grid"]["min_values_per_parameter"]
    rmin = cfg_trials["grid"]["min_ratio_between_neighbors"]
    if not grid:
        return False, "empty grid"
    for p, vals in grid.items():
        v = list(vals)
        if len(v) < gmin:
            return False, f"{p}: {len(v)} values < {gmin}"
        if any(not _finite(x) or x <= 0 for x in v):
            return False, f"{p}: values not strictly positive"
        v = sorted(v)
        for a, b in itertools.pairwise(v):
            if b / a < rmin - 1e-12:
                return False, f"{p}: ratio {b / a:.4f} < {rmin}"
    return True, ""


def _same_point(p: Mapping[str, float], q: Mapping[str, float]) -> bool:
    return set(p) == set(q) and all(math.isclose(float(p[k]), float(q[k]), rel_tol=1e-9, abs_tol=1e-12) for k in p)


#: A neighbor whose net series is correlated above IDENTICAL_NEIGHBOR_CORR with the candidate's AND whose
#: turnover is identical to within IDENTICAL_TURNOVER_TOL is the same behavior (parameter ignored).
IDENTICAL_NEIGHBOR_CORR = 0.999
IDENTICAL_TURNOVER_TOL = 1e-9
#: C7 requires at least this number of distinct neighbors.
DISTINCT_NEIGHBORS_MIN = 2


def _identical_neighbor(candidate: Any, neighbor: Any) -> bool:
    """True if `neighbor` is indistinguishable from `candidate`: net-return correlation > 0.999 and
    turnover equal to within 1e-9 (aligned by date). Constant series: identical if the values are equal."""
    a, b = candidate.net.align(neighbor.net, join="inner")
    ra, rb = candidate.rotation.align(neighbor.rotation, join="inner")
    if len(a) < 2 or len(ra) < 1:
        return False
    if float(np.abs(ra.to_numpy(dtype=float) - rb.to_numpy(dtype=float)).max()) > IDENTICAL_TURNOVER_TOL:
        return False
    va, vb = a.to_numpy(dtype=float), b.to_numpy(dtype=float)
    if va.std() == 0.0 or vb.std() == 0.0:
        return bool(np.allclose(va, vb, rtol=0.0, atol=1e-15))
    return float(np.corrcoef(va, vb)[0, 1]) > IDENTICAL_NEIGHBOR_CORR


def gate_c7(
    candidate: Any,
    all_results: Sequence[Any],
    grid: Mapping[str, Sequence[float]] | None,
    cfg,
    cfg_trials,
) -> tuple[Gate, dict]:
    threshold = {"min_neighbors_share": cfg["min_neighbors_share"], "ratio": cfg["min_neighbor_sharpe_ratio"],
             "min_neighbor_sharpe": cfg["min_neighbor_sharpe"]}
    if not grid:
        return (False, None, threshold), {"reason": "grid not declared"}
    ok_grid, reason = grid_valid(grid, cfg_trials)
    if not ok_grid:
        return (False, None, threshold), {"reason": f"invalid grid: {reason}"}
    axes = {p: sorted(float(x) for x in v) for p, v in grid.items()}
    pt = dict(candidate.params)
    pos = {}
    for p, vals in axes.items():
        if p not in pt:
            return (False, None, threshold), {"reason": f"parameter {p} absent from the candidate"}
        idx = [i for i, x in enumerate(vals) if math.isclose(x, float(pt[p]), rel_tol=1e-9, abs_tol=1e-12)]
        if not idx:
            return (False, None, threshold), {"reason": f"{p}={pt[p]} outside the grid"}
        if idx[0] in (0, len(vals) - 1):
            return (False, None, threshold), {"reason": f"{p} at the edge of the grid"}
        pos[p] = idx[0]
    s_cand = stats.sharpe(candidate.net)
    neighbor_threshold = max(cfg["min_neighbor_sharpe_ratio"] * s_cand, cfg["min_neighbor_sharpe"])
    neighbors, good_count, identical = [], 0, []
    pool = [r for r in all_results if r.family == candidate.family and getattr(r, "universe", "main") == "main"]
    for p, vals in axes.items():
        for d in (-1, 1):
            q = dict(pt)
            q[p] = vals[pos[p] + d]
            found = next((r for r in pool if _same_point(r.params, q)), None)
            if found is None:
                return (False, None, threshold), {"reason": f"neighbor not evaluated: {q}"}
            s = stats.sharpe(found.net)
            if not _finite(s):
                return (False, None, threshold), {"reason": f"neighbor not evaluable: {q}"}
            if _identical_neighbor(candidate, found):
                identical.append(q)  # parameter without effect: not a distinct neighbor
                continue
            neighbors.append((q, s))
            good_count += s >= neighbor_threshold
    det = {"neighbors": neighbors, "neighbors_identical": identical, "neighbor_sharpe_threshold": neighbor_threshold}
    if len(neighbors) < DISTINCT_NEIGHBORS_MIN:
        det["reason"] = f"{len(neighbors)} distinct neighbor(s) < {DISTINCT_NEIGHBORS_MIN} (parameters without effect?)"
        return (False, None, threshold), det
    share = good_count / len(neighbors)
    ok = _finite(s_cand) and share >= cfg["min_neighbors_share"]
    return (ok, share, threshold), det


# ----------------------------------------------------------------------------- C8
def gate_c8_directional(net: pd.Series, basket: pd.Series | None, cfg) -> Gate:
    threshold = cfg["p_unilateral_max"]
    if basket is None:
        return (False, None, threshold)
    a, b = net.align(basket, join="inner")
    if len(a) < 2 * cfg["paired_bootstrap_block_days"]:
        return (False, None, threshold)
    p = stats.bootstrap_paired(
        a, b, cfg["paired_bootstrap_block_days"], cfg["replications"], cfg["seed"]
    )["p"]
    return (_ok_le(p, threshold), p, threshold)


def gate_c8_hedged(net: pd.Series, basket: pd.Series | None, cfg) -> Gate:
    threshold = (cfg["alpha_t_newey_west_min"], cfg["beta_abs_max"])
    if basket is None:
        return (False, None, threshold)
    a, b = net.align(basket, join="inner")
    if len(a) < 3 * cfg["delays"]:
        return (False, None, threshold)
    reg = stats.regression_alpha_beta(a, b, cfg["delays"])
    ok = _ok_ge(reg["t_alpha"], threshold[0]) and _finite(reg["beta"]) and abs(reg["beta"]) <= threshold[1]
    return (ok, (reg["t_alpha"], reg["beta"]), threshold)


# ----------------------------------------------------------------------------- C9
def gate_c9(report: CausalityReport | None, cfg) -> Gate:
    threshold = {"random_cuts": cfg["random_cutoffs"], "fixed_cuts": cfg["fixed_cutoffs"],
             "not_full_share_min": cfg["min_non_full_hour_share"], "tolerance": cfg["tolerance"]}
    if report is None:
        return (False, None, threshold)
    ok = (
        report.n_random_cuts >= cfg["random_cutoffs"]
        and report.n_fixed >= cfg["fixed_cutoffs"]
        and _ok_ge(report.not_full_hour_share, cfg["min_non_full_hour_share"])
        and _ok_le(report.max_gap, cfg["tolerance"])
        and bool(report.invariances_ok)
    )
    return (ok, report.max_gap, threshold)


# ----------------------------------------------------------------------------- C11
def gate_c11(net: pd.Series, cfg) -> Gate:
    s0 = stats.sharpe(net)
    r1, _ = stats.remove_best_days(net, cfg["withdrawal_share_1"])
    r2, _ = stats.remove_best_days(net, cfg["withdrawal_share_2"])
    s1, s2 = stats.sharpe(r1), stats.sharpe(r2)
    min1 = max(0.5, 0.5 * s0) if _finite(s0) else float("nan")
    ok = _ok_ge(s1, min1) and _ok_gt(s2, cfg["min_sharpe_after_2"])
    return (ok, (s1, s2), (min1, cfg["min_sharpe_after_2"]))


# ----------------------------------------------------------------------------- C12
def gate_c12(gross: pd.Series, costs: pd.Series, rotation: pd.Series, class_: str, cfg, cfg_classes) -> Gate:
    cost_year = float(costs.sum() / (len(costs) / stats.DAYS_PER_YEAR))
    gross_year = float(gross.sum() / (len(gross) / stats.DAYS_PER_YEAR))
    rot = stats.annual_turnover(rotation)
    rot_max = cfg_classes[class_]["max_annual_turnover"]
    ratio = cost_year / gross_year if gross_year > 0 else float("inf")
    ok = _ok_le(ratio, cfg["max_cost_on_gross_return"]) and _ok_le(rot, rot_max)
    return (ok, (ratio, rot), (cfg["max_cost_on_gross_return"], rot_max))


# ----------------------------------------------------------------------------- C13
def gate_c13(net: pd.Series, cfg) -> Gate:
    a, b = stats.sharpe_halves(net)
    threshold = cfg["min_sharpe_each_half"]
    return (_ok_gt(a, threshold) and _ok_gt(b, threshold), (a, b), threshold)


# ----------------------------------------------------------------------------- C14
def gate_c14(net: pd.Series, cfg) -> Gate:
    r = stats.annualized_return(net)
    threshold = cfg["min_net_annualized_return"]
    return (_ok_ge(r, threshold), r, threshold)


# ----------------------------------------------------------------------------- C15
def _sharpe_dd(res: Any) -> tuple[float, float]:
    """Sharpe and drawdown of a result: object with `.net` (Trial) or `.returns` (arena replay)."""
    series = getattr(res, "net", None)
    if series is None:
        series = getattr(res, "returns", None)
    if series is None:
        return float("nan"), float("nan")
    return stats.sharpe(series), stats.drawdown(series)


def gate_c15(res_arena: Any | None, class_: str, cfg, cfg_c6) -> Gate:
    threshold = (cfg["sharpe_min"], cfg["max_drawdown_factor_C6"] * cfg_c6[class_])
    if res_arena is None:
        return (False, None, threshold)
    s, dd = _sharpe_dd(res_arena)
    return (_ok_gt(s, threshold[0]) and _ok_le(dd, threshold[1]), (s, dd), threshold)


# ----------------------------------------------------------------------------- C16
#: Marks, in `res_control`, a symbol whose data required by the sheet is missing (hedged: perp;
#: perp_signals: funding). It counts neither in the numerator nor in the minimum of evaluable symbols, but the
#: denominator of C16 remains the size of the control universe.
NOT_EVALUABLE = "not_evaluable"
EVALUABLE_MIN_C16 = 10


def gate_c16(res_control: Mapping[str, Any] | None, cfg, universe_size: int = 20) -> Gate:
    """C16: share of the control symbols with net Sharpe > 0 >= `min_positive_sharpe_symbols_share`.

    - FIXED denominator = `universe_size` (20, `criteria.data.control_universe.size`), never the
      number of symbols that ran.
    - A symbol absent from `res_control`, `None` (non-OK trial: ERROR, TIMEOUT, ...) or with a NaN Sharpe
      is a failure (it stays in the denominator).
    - `NOT_EVALUABLE`: required data missing; counts neither in the numerator nor in the minimum of
      `EVALUABLE_MIN_C16` evaluable symbols (otherwise C16 fails); the report says so.
    Returned value: (share, positives, evaluable, not_evaluable, universe_size)."""
    threshold = cfg["min_positive_sharpe_symbols_share"]
    if not res_control:
        return (False, None, threshold)
    positive = not_eval = 0
    for res in res_control.values():
        if isinstance(res, str) and res == NOT_EVALUABLE:
            not_eval += 1
            continue
        if res is None:
            continue
        s, _ = _sharpe_dd(res)
        if _finite(s) and s > 0:
            positive += 1
    evaluable = universe_size - not_eval
    share = positive / universe_size
    value = (share, positive, evaluable, not_eval, universe_size)
    return (evaluable >= EVALUABLE_MIN_C16 and share >= threshold, value, threshold)


# ----------------------------------------------------------------------------- orchestration
def evaluate_candidate(
    result: Any,
    all_results: Sequence[Any],
    criteria: Any,
    sheet_grid: Mapping[str, Sequence[float]] | None,
    basket: pd.Series | None,
    results_arena: Any | None,
    results_control: Mapping[str, Any] | None,
    causality: CausalityReport | None = None,
    research_sr_days: Mapping[str, Mapping[str, Sequence[float]]] | None = None,
) -> Verdict:
    """Apply C1-C16 (+ consistency C2, C3, C4, C10) to `result`.

    all_results: all the research trials (V per class; C7 neighbors), `result` included.
    basket: daily returns of the equal-weighted basket of the candidate's universe (supplied by the engine).
    causality: otherwise `result.causality`; absent = C9 fails.
    research_sr_days: sr_day of all the journal's research trials (V per class); see
    `variance_of_class`. results_control: see `gate_c16` (denominator = size of the control universe).
    """
    c_gates, c_coh = section(criteria, "gates"), section(criteria, "consistency")
    c_trials, c_classes = section(criteria, "trials"), section(criteria, "classes")
    class_ = result.class_
    if class_ not in ("directional", "hedged"):
        raise ValueError(f"unknown class: {class_!r}")
    net = result.net
    T = len(net)

    N = int(c_trials["N_dsr"])
    V = variance_of_class(class_, all_results, T, research_sr_days)
    p1, d1 = gate_c1(net, N, V, c_gates["C1_dsr_min"])
    try:
        d1["dsr_V_common"] = dsr_mod.dsr_prob(
            d1["sr_day"], T, d1["skew"], d1["kurt"], N,
            _common_v(all_results, T, research_sr_days),
        )
    except ValueError:
        d1["dsr_V_common"] = float("nan")

    cc8 = c_gates["C8_directional"] if class_ == "directional" else c_gates["C8_hedged"]
    p8 = (
        gate_c8_directional(net, basket, cc8)
        if class_ == "directional"
        else gate_c8_hedged(net, basket, cc8)
    )
    p7, d7 = gate_c7(result, all_results, sheet_grid, c_gates["C7_neighborhood"], c_trials)
    report = causality if causality is not None else getattr(result, "causality", None)

    gates: dict[str, Gate] = {
        "C1": p1,
        "C5": gate_c5(net, c_gates["C5_years"]),
        "C6": gate_c6(net, class_, c_gates["C6_drawdown_max"]),
        "C7": p7,
        "C8": p8,
        "C9": gate_c9(report, c_gates["C9_causality"]),
        "C11": gate_c11(net, c_gates["C11_extremes"]),
        "C12": gate_c12(result.gross, result.costs, result.rotation, class_, c_gates["C12_costs"], c_classes),
        "C13": gate_c13(net, c_gates["C13_halves"]),
        "C14": gate_c14(net, c_gates["C14_materiality"]),
        "C15": gate_c15(results_arena, class_, c_gates["C15_arena"], c_gates["C6_drawdown_max"]),
        "C16": gate_c16(results_control, c_gates["C16_outside_universe"],
                         int(section(criteria, "data")["control_universe"]["size"])),
    }

    s_net = stats.sharpe(net)
    t_nw = stats.t_newey_west(net, 20)
    s_stress = stats.sharpe(result.net_stress)
    c10 = c_coh["C10_bootstrap"]
    p10 = stats.bootstrap_blocks(net, c10["block_days"], c10["replications"], c10["seed"])["p"]
    consistency: dict[str, Gate] = {
        "C2": (_ok_ge(s_net, c_coh["C2_sharpe_net_min"]), s_net, c_coh["C2_sharpe_net_min"]),
        "C3": (_ok_ge(t_nw, c_coh["C3_t_newey_west_min"]), t_nw, c_coh["C3_t_newey_west_min"]),
        "C4": (_ok_gt(s_stress, c_coh["C4_sharpe_stress_min"]), s_stress, c_coh["C4_sharpe_stress_min"]),
        "C10": (_ok_le(p10, c10["p_unilateral_max"]), p10, c10["p_unilateral_max"]),
    }
    details = {"C1": d1, "C7": d7, "sharpe_net": s_net, "T": T}
    passed = all(ok for ok, _, _ in gates.values()) and all(ok for ok, _, _ in consistency.values())
    return Verdict(gates=gates, consistency=consistency, passed=passed, details=details)


def _common_v(all_results: Sequence[Any], T: int,
              research_sr_days: Mapping[str, Mapping[str, Sequence[float]]] | None = None) -> float:
    """V over all classes pooled (information only, PROTOCOL §5)."""
    per_family: dict[str, list[float]] = {}
    if research_sr_days is not None:
        for fams in research_sr_days.values():
            for fam, srs in fams.items():
                per_family.setdefault(fam, []).extend(srs)
        return dsr_mod.class_variance(per_family, T)
    for r in all_results:
        if getattr(r, "universe", "main") != "main":
            continue
        s = stats.sr_day(r.net)
        if _finite(s):
            per_family.setdefault(r.family, []).append(s)
    return dsr_mod.class_variance(per_family, T)
