"""Execution of a trial: `start` -> synthetic causality -> real stream in the sandbox -> simulation -> `end`.

The calling agent receives only the closed code (`TrialResult.for_agent()`). The complete series and metrics
stay in `TrialResult.track` / `.metrics`, for the orchestrator and the gates.

Output channels (a strategy is hostile code that sees the result of its own trials):
- text: `detail` and the technical journal contain NO text coming from the strategy (no exception
  message, no trace): the closed code, the standard exception type and the stream's day number;
- time: the timestamps of `start`/`end` are rounded to the minute (`ResearchJournal._ts`);
- residual bit: the closed code itself (6 values) remains readable by the agent, and the strategy chooses whether it
  is OK, ERROR, TIMEOUT or WEIGHT_SHAPE (and, through the error's day number, one day among T in the
  technical journal, which the agent does not read). At most log2(6) ~ 2.6 bits per trial exposed to the agent, hence
  at most ~1,600 bits over all of research-v1 (N <= 600): the trial cap bounds the channel, it does not close it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
import os
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from research.engine import sandbox, contract
from research.engine.contract import (
    ERROR,
    OK,
    TrialError,
    WeightShape,
    SourceRefused,
)
from research.engine.journal import AnchorError, ResearchJournal, decimal12, canonical_params
from research.engine.panel import DAY_S, Panel, panel_from_data, varied_synthetic
from research.engine.portfolio import CLASSES, EngineSeries, relative_to, simulate, validate_weight

ENGINE_VERSION = "research-engine-v2"


class CapError(Exception):
    """The total trial cap (criteria.trials.total_cap) is reached: no further trial."""


@dataclass(frozen=True)
class TrialSheet:
    """What the engine keeps from a sheet: family, class (declared before any trial), file sha256."""

    family: str
    class_: str
    sheet_sha256: str
    perp_signals: bool = False  # directional: receives perp bars and funding as SIGNALS (perp leg zero)


@dataclass
class TrialResult:
    id: str
    code: str
    universe: str
    track: EngineSeries | None = None
    metrics: dict = field(default_factory=dict)
    detail: str = ""  # technical: orchestrator only
    causality: dict | None = None

    def for_agent(self) -> str:
        """The only return meant for an agent: a closed code."""
        return self.code


# ----------------------------------------------------------------------------------------------------
# Metrics (strictly what the journal needs; the gates recompute the rest with their own code)
# ----------------------------------------------------------------------------------------------------


def _sharpe(r: np.ndarray) -> float:
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    return float(r.mean() / sd * math.sqrt(365)) if sd > 0 else float("nan")


def _drawdown(r: np.ndarray) -> float:
    nav = np.concatenate([[1.0], np.cumprod(1.0 + r)])
    return float((1.0 - nav / np.maximum.accumulate(nav)).max())


def _t_nw(r: np.ndarray, lags: int = 20) -> float:
    x = r - r.mean()
    n = len(x)
    lrv = float(x @ x) / n
    for k in range(1, lags + 1):
        lrv += 2.0 * (1.0 - k / (lags + 1)) * float(x[k:] @ x[:-k]) / n
    return float(r.mean() / math.sqrt(lrv / n)) if lrv > 0 else float("nan")


def _annualized(r: np.ndarray) -> float:
    n = len(r)
    nav = float(np.prod(1.0 + r))
    return nav ** (365.0 / n) - 1.0 if n and nav > 0 else float("nan")


def compute_metrics(track: EngineSeries) -> dict:
    """Journal metrics over the days of the evaluation window (eval_mask)."""
    m = track.eval_mask
    net, net2, gross = track.net_returns[m], track.stressed_net_returns[m], track.gross_returns[m]
    n = len(net)
    if n < 3:
        return {"T": n}
    sd = net.std(ddof=1)
    c = net - net.mean()
    s2 = float((c**2).mean())
    years = {}
    year_arr = np.asarray((track.days[m].astype("datetime64[s]").astype("datetime64[Y]").astype(int)) + 1970)
    for a in range(2020, 2026):
        ra = net[year_arr == a]
        years[str(a)] = _sharpe(ra) if len(ra) > 2 else float("nan")
    return {
        "T": n,
        "sharpe_net": _sharpe(net),
        "sr_day": float(net.mean() / sd) if sd > 0 else float("nan"),
        "skew": float((c**3).mean() / s2**1.5) if s2 > 0 else float("nan"),
        "kurt": float((c**4).mean() / s2**2) if s2 > 0 else float("nan"),
        "drawdown": _drawdown(net),
        "annual_turnover": float(track.rotation[m].sum() / (n / 365.0)),
        "t_nw20": _t_nw(net),
        "sharpe_net_costs_x2": _sharpe(net2),
        "net_annualized_return": _annualized(net),
        "gross_annualized_return": _annualized(gross),
        "annualized_total_cost": float(track.costs[m].sum() / (n / 365.0)),
        "avg_immobilized_capital": float(track.exposure[m].mean()),
        "sharpe_per_year": years,
        "series_sha256": hashlib.sha256(np.ascontiguousarray(net).tobytes()).hexdigest(),
    }


def gate_series(track: EngineSeries) -> EngineSeries:
    """The series as the gates see it: for `hedged`, relative to the reference immobilized capital
    max(expo_j, expo_{j-1}) (same transformation as `gates.adapter`); `directional`: unchanged."""
    if track.class_ != "hedged":
        return track
    def r(x):
        return relative_to(x, track.exposure)
    return dataclasses.replace(
        track, net_returns=r(track.net_returns), stressed_net_returns=r(track.stressed_net_returns),
        gross_returns=r(track.gross_returns), costs=r(track.costs))


def compute_gate_metrics(track: EngineSeries) -> dict:
    """Same metrics as `compute_metrics`, on the gates' series (immobilized capital), prefixed
    `gates_` so they are not confused with those on total capital."""
    return {f"gates_{k}": v for k, v in compute_metrics(gate_series(track)).items() if k != "T"}


# ----------------------------------------------------------------------------------------------------
# Causality (C9) on synthetic data
# ----------------------------------------------------------------------------------------------------

_CAUSALITY_CACHE: dict = {}
_CAUSALITY_TOL = 1e-9
_SYNTH_DAYS = 1300
CAUSALITY_VERSION = "c9-v2"  # in the cache key: changing the test invalidates the cached results


def _run(source: bytes, params: dict, panel: Panel, class_: str, margin: float, timeout: float,
            strict: bool, until: int | None = None, days_withdrawn: int = 0):
    listed = np.maximum.accumulate(panel.eligibles, axis=0)

    def validate(i, ws, wp):
        if strict:
            validate_weight(class_, i, ws, wp, listed[i], None if panel.eligibles_perp is None
                          else panel.eligibles_perp[i], margin)

    return sandbox.run_stream(source, params, panel, validate, timeout, until_error=until,
                                     days_withdrawn=days_withdrawn)


def verify_causality(source: bytes, params: dict, criteria, *, class_: str = "directional",
                       n_pairs: int = 15, with_1h: bool = True, with_perp: bool = False,
                       data_seed: int | None = None, rng: np.random.Generator | None = None,
                       threads: int = 4, days_withdrawn: int | None = None) -> dict:
    """C9 on synthetic data (never real). Compares, inside the sandbox:
    - determinism: two identical complete runs;
    - `random_cutoffs` + `fixed_cutoffs` cutoffs on `known_at`: all data known after the cutoff
      is replaced by noise, the weights of the days closed before the cutoff are unchanged
      (at least `min_non_full_hour_share` of the cutoffs fall on a non-full hour);
    - column permutation: the weights follow the permutation;
    - scale: prices x factor in [0.1, 10], volumes / factor: weights unchanged.
    Tolerance 1e-9. Returns a dict with `ok` and the details of the checks.

    The data is `varied_synthetic`: at least 1,300 days, varied regimes (trends, crashes, sustained high
    positive or negative funding, negative basis, pairs entering listing) and a seed drawn from
    `os.urandom` ON EACH CALL (`data_seed` is given only by tests): a strategy cannot
    recognize the test set. If the weights are constant over the whole series, the report carries
    `evaluable: False` (nothing then proves causality: `adapter.to_causality_report` makes C9 fail).
    `days_withdrawn`: number of warm-up days removed from the stream (None: drawn per call, a single draw
    for all replays; tests pass 0)."""
    cfg = criteria.gates.C9_causality
    rng = rng or np.random.default_rng(int.from_bytes(os.urandom(16), "big"))
    if data_seed is None:
        data_seed = int.from_bytes(os.urandom(8), "big")  # never in a cache key
    panel = varied_synthetic(_SYNTH_DAYS, n_pairs, data_seed, with_1h=with_1h, with_perp=with_perp)
    T = panel.n_days
    margin = criteria.perp_share_margin
    timeout = 180.0
    # cutoffs: instants in UTC seconds
    n_random, n_fixed = int(cfg.random_cutoffs), int(cfg.fixed_cutoffs)
    min_day = 40
    cutoffs = []
    for f in (0.3, 0.55, 0.9)[:n_fixed]:
        cutoffs.append(int(panel.days[int(T * f)]) + 12 * 3600)  # exactly 12:00
    drawn_days = rng.choice(np.arange(min_day, T - 1), size=n_random, replace=False)
    n_not_full = math.ceil(float(cfg.min_non_full_hour_share) * (n_random + n_fixed))
    for k, j in enumerate(drawn_days):
        h = int(rng.integers(0, 24))
        if k < n_not_full:
            cutoffs.append(int(panel.days[j]) + h * 3600 + int(rng.integers(1, 3600)))
        else:
            cutoffs.append(int(panel.days[j]) + h * 3600)
    not_full = sum(1 for c in cutoffs if c % 3600 != 0)
    perm = _permutation_without_fixed_point(rng, n_pairs)
    factors = np.exp(rng.uniform(math.log(0.1), math.log(10.0), n_pairs))
    # k warm-up days removed: ONE single draw for all replays of this check (otherwise two replays
    # of a strategy that counts days would not be comparable).
    k_withdrawn = sandbox.draw_days_withdrawn(panel, criteria) if days_withdrawn is None else int(days_withdrawn)

    def base(_):
        return _run(source, params, panel, class_, margin, timeout, True, days_withdrawn=k_withdrawn)

    def cut_run(c):
        corrupted = panel.corrupt_after(c, rng_local(c))
        ws, wp, n_ok = _run(source, params, corrupted, class_, margin, timeout, False, until=1, days_withdrawn=k_withdrawn)
        return c, ws, wp, n_ok

    def rng_local(c):
        return np.random.default_rng([int(c), int.from_bytes(os.urandom(4), "big")])

    def permuted_run(_):
        p = panel.swap(perm)
        ws, wp, _n = _run(source, params, p, class_, margin, timeout, True, days_withdrawn=k_withdrawn)
        o_s, o_p = np.empty_like(ws), np.empty_like(wp)
        o_s[:, perm], o_p[:, perm] = ws, wp
        return o_s, o_p

    def scale(_):
        ws, wp, _n = _run(source, params, panel.rescale(factors), class_, margin, timeout, True,
                             days_withdrawn=k_withdrawn)
        return ws, wp

    res = {"ok": False, "n_cutoffs": len(cutoffs), "non_full_hour_cutoffs": not_full}
    try:
        with ThreadPoolExecutor(max_workers=threads) as ex:
            f_base = [ex.submit(base, k) for k in (0, 1)]
            f_cut = [ex.submit(cut_run, c) for c in cutoffs]
            f_perm = ex.submit(permuted_run, 0)
            f_scale = ex.submit(scale, 0)
            (w1s, w1p, _), (w2s, w2p, _) = (f.result() for f in f_base)
            cuts = [f.result() for f in f_cut]
            p_s, p_p = f_perm.result()
            e_s, e_p = f_scale.result()
    except TrialError as e:
        res["error"] = f"{e.code}: {e.detail}"[:500]
        res["code"] = e.code
        return res
    res["deterministic"] = bool(max(np.abs(w1s - w2s).max(), np.abs(w1p - w2p).max()) <= _CAUSALITY_TOL)
    res["evaluable"] = bool(np.ptp(w1s, axis=0).max() > _CAUSALITY_TOL or np.ptp(w1p, axis=0).max() > _CAUSALITY_TOL)
    res["n_days"] = int(T)
    cut_gap = 0.0
    for c, ws, wp, n_ok in cuts:
        closed = int(np.sum(panel.days + DAY_S <= c))  # days whose close <= cutoff
        k = min(closed, n_ok)
        if k < closed:
            cut_gap = float("inf")  # the strategy failed before the cutoff on clean data
            continue
        cut_gap = max(cut_gap, float(np.abs(ws[:closed] - w1s[:closed]).max()),
                        float(np.abs(wp[:closed] - w1p[:closed]).max()))
    res["cutoffs_gap"] = cut_gap
    res["permutation_gap"] = float(max(np.abs(p_s - w1s).max(), np.abs(p_p - w1p).max()))
    res["scale_gap"] = float(max(np.abs(e_s - w1s).max(), np.abs(e_p - w1p).max()))
    res["ok"] = bool(res["deterministic"] and cut_gap <= _CAUSALITY_TOL
                     and res["permutation_gap"] <= _CAUSALITY_TOL and res["scale_gap"] <= _CAUSALITY_TOL
                     and not_full >= float(cfg.min_non_full_hour_share) * len(cutoffs) - 1e-9)
    return res


# ----------------------------------------------------------------------------------------------------
# Trial
# ----------------------------------------------------------------------------------------------------

_PANELS: list = []


def _field(sheet, name):
    return sheet[name] if isinstance(sheet, Mapping) else getattr(sheet, name)


def _perp_signals(sheet, class_: str) -> bool:
    """A hedged sheet always receives perp and funding; a directional sheet only if it declares it
    (`perp_signals: true`), and then as signals: `validate_weight` always enforces a zero perp leg."""
    if class_ == "hedged":
        return True
    v = sheet.get("perp_signals", False) if isinstance(sheet, Mapping) else getattr(sheet, "perp_signals", False)
    return bool(v)


def _panel(data, universe: str, class_: str, criteria, with_perp: bool | None = None) -> Panel:
    if with_perp is None:
        with_perp = class_ == "hedged"
    if isinstance(data, Panel):
        panel = data
        if universe.startswith("control:"):
            panel = panel.sub_universe([universe.split(":", 1)[1]])
        elif universe == "arena":
            panel = panel.sub_universe(list(criteria.arena_universe))
        elif universe != "main":
            raise ValueError(f"unknown universe: {universe!r}")
    else:
        for d, u, c, p in _PANELS:
            if d is data and u == universe and c == with_perp:
                return p
        panel = panel_from_data(data, universe, with_perp=with_perp,
                                     arena_symbols=tuple(criteria.arena_universe))
        _PANELS.append((data, universe, with_perp, panel))
        del _PANELS[:-4]
        return panel
    return panel


def _without_perp(panel: Panel) -> Panel:
    z = tuple(a[:0] for a in panel.funding_idx)
    return Panel(panel.symbols, panel.days, panel.spot_1d, panel.spot_1h, None, panel.eligibles, None, z,
                   tuple(a[:0] for a in panel.funding_rate), tuple(a[:0] for a in panel.funding_ts))


def _permutation_without_fixed_point(rng: np.random.Generator, n: int) -> np.ndarray:
    """Permutation that moves every column (otherwise the permutation test might test nothing)."""
    while True:
        perm = rng.permutation(n)
        if n < 2 or (perm != np.arange(n)).all():
            return perm


def _derangement(rng: np.random.Generator, ref: np.ndarray) -> np.ndarray:
    """Permutation `p` with `p[k] != ref[k]` for every k: no column of the replay carries the same pair as
    in the reference run (otherwise a strategy that leaks the column index would not be detected
    on those columns). Impossible for n = 1 (a single pair): returns `ref` then."""
    n = len(ref)
    if n < 2:
        return np.asarray(ref).copy()
    while True:
        p = rng.permutation(n)
        if (p != ref).all():
            return p


def _real_control(source: bytes, params: dict, panel: Panel, class_: str, margin: float, timeout: float,
                   ws_o: np.ndarray, wp_o: np.ndarray, perm_ref: np.ndarray | None = None,
                   days_withdrawn: int = 0) -> float:
    """Second causality/invariance check, on the REAL data of the trial: replays the strategy with another
    permutation and other per-pair scale factors (drawn per call, `os.urandom`); returns the maximum gap
    of the weights, in the frame of the real pairs, against those of the main run.
    `perm_ref`: permutation of the main run; the replay draws a relative derangement from it (every column
    changes pair between the two runs). `days_withdrawn`: the same k as the main run."""
    rng = np.random.default_rng(int.from_bytes(os.urandom(16), "big"))
    n = panel.n_pairs
    perm = _permutation_without_fixed_point(rng, n) if perm_ref is None else _derangement(rng, np.asarray(perm_ref))
    factors = np.exp(rng.uniform(math.log(0.1), math.log(10.0), n))
    p2 = panel.rescale(factors).swap(perm)
    ws, wp, _ = _run(source, params, p2, class_, margin, timeout, True, days_withdrawn=days_withdrawn)
    o_s, o_p = np.empty_like(ws), np.empty_like(wp)
    o_s[:, perm], o_p[:, perm] = ws, wp
    return float(max(np.abs(o_s - ws_o).max(), np.abs(o_p - wp_o).max()))


def run_trial(sheet, code_path: str | Path, params: dict, data, journal: ResearchJournal, criteria,
                   universe: str = "main", *, arena_journal: str | Path | None = None,
                   convention_rotation: str = "drifted", permutation: np.ndarray | None = None,
                   causality: bool = True, timeout_s: float | None = None,
                   spot_cost_bp: int | None = None, perp_cost_bp: int | None = None,
                   test: bool = False, days_withdrawn: int | None = None,
                   draw_k: int | None = None) -> TrialResult:
    """A complete trial. `data`: loader `Data` or `Panel`. Raises `CapError` (total cap),
    `CanaryError` (failing sandbox), `AnchorError` (inconsistent journal, or `arena_journal` missing without
    `test=True`): these are not trials. Any other failure is a trial: `start` and `end` are written
    and the closed code is returned.

    `arena_journal` is REQUIRED (external anchoring, protocol §4) unless `test=True` (tests only).
    The anchor is written right after `start` AND right after `end`. `start` records all the overrides
    (causality, spot_cost_bp, perp_cost_bp, convention_rotation, timeout_s, forced permutation, test).
    `convention_rotation="target"` and `spot_cost_bp=15` reproduce the lab engine (acceptance E0065).

    If `causality`, two checks: C9 on synthetic data (`verify_causality`, seed drawn per call) then,
    on the real data of the trial, a replay with another permutation and other per-pair scale factors
    (identical weights to within 1e-9); a gap gives the CAUSALITY code.

    `days_withdrawn`: number k of warm-up days removed at the START of the stream sent to the strategy. None:
    drawn once per trial (`os.urandom`, in [0, 365), remaining warm-up >= 365 days, evaluation
    window intact), the same for the main run and its replay on real data. The acceptance tests
    for exact reproduction of the lab (E0065, basket) pass `days_withdrawn=0`: the lab
    started its series on the first day of the data and the rebalancing phase (H = 10 days) depends on it."""
    class_ = _field(sheet, "class_")
    if class_ not in CLASSES:
        raise ValueError(f"unknown class {class_!r}")
    if arena_journal is None and not test:
        raise AnchorError("arena_journal required (external anchoring); test=True is reserved for tests")
    sandbox.canary()
    journal.initialize()
    journal.verify_anchor(arena_journal)
    if journal.n_ids() >= criteria.total_cap:
        raise CapError(f"{journal.n_ids()} trials already started, cap {criteria.total_cap}")
    source = Path(code_path).read_bytes()  # read ONCE: this text is hashed, checked and executed
    eid = journal.next_id()
    journal.start({
        "id": eid, "family": _field(sheet, "family"), "class_": class_,
        "sheet_sha256": _field(sheet, "sheet_sha256"), "code_sha256": hashlib.sha256(source).hexdigest(),
        "params": canonical_params(params), "universe": universe, "criteria_sha256": criteria.sha256,
        "engine": ENGINE_VERSION,
        "overrides": {"causality": bool(causality), "spot_cost_bp": spot_cost_bp, "perp_cost_bp": perp_cost_bp,
                       "convention_rotation": convention_rotation, "timeout_s": timeout_s,
                       "forced_permutation": permutation is not None, "test": bool(test),
                       "days_withdrawn": days_withdrawn}})
    journal.anchor(arena_journal)
    res = TrialResult(id=eid, code=ERROR, universe=universe)
    k_withdrawn = None
    try:
        sandbox.verify_source(source.decode("utf-8", "replace"), Path(code_path).name)
        signals = _perp_signals(sheet, class_)
        panel = _panel(data, universe, class_, criteria, with_perp=signals)
        if not signals and panel.perp_1h is not None:
            panel = _without_perp(panel)
        k_withdrawn = (sandbox.draw_days_withdrawn(panel, criteria, draw=draw_k) if days_withdrawn is None
                 else int(days_withdrawn))
        if causality:
            key = (hashlib.sha256(source).hexdigest(), canonical_params(params), criteria.sha256, panel.n_pairs,
                   panel.spot_1h is not None, panel.perp_1h is not None, class_, _SYNTH_DAYS, CAUSALITY_VERSION)
            if key not in _CAUSALITY_CACHE:
                _CAUSALITY_CACHE[key] = verify_causality(
                    source, params, criteria, class_=class_, n_pairs=panel.n_pairs,
                    with_1h=panel.spot_1h is not None, with_perp=panel.perp_1h is not None)
            res.causality = dict(_CAUSALITY_CACHE[key])
            if not res.causality["ok"]:
                res.code = res.causality.get("code", contract.CAUSALITY)
                # no value or text coming from the strategy: only the names of the failed checks
                failures = [k for k in ("deterministic",) if not res.causality.get(k, True)]
                failures += [k for k in ("cutoffs_gap", "permutation_gap", "scale_gap")
                           if res.causality.get(k, 0.0) > _CAUSALITY_TOL]
                res.detail = f"synthetic causality failed: {failures or res.causality.get('error', '?')}"
                return res
        perm = (np.random.default_rng(int.from_bytes(os.urandom(16), "big")).permutation(panel.n_pairs)
                if permutation is None else np.asarray(permutation))
        permuted_panel = panel.swap(perm)
        timeout = timeout_s or float(criteria.trial_timeout_s)
        ws, wp, _ = _run(source, params, permuted_panel, class_, criteria.perp_share_margin, timeout, True,
                            days_withdrawn=k_withdrawn)
        ws_o, wp_o = np.empty_like(ws), np.empty_like(wp)
        ws_o[:, perm], wp_o[:, perm] = ws, wp
        if causality:
            gap = _real_control(source, params, panel, class_, criteria.perp_share_margin, timeout, ws_o, wp_o,
                                   perm_ref=perm, days_withdrawn=k_withdrawn)
            res.causality["real_gap"] = gap
            res.causality["real_ok"] = bool(gap <= _CAUSALITY_TOL)
            if not res.causality["real_ok"]:
                res.code = contract.CAUSALITY
                res.detail = "causality on real data failed (different permutation and scales)"
                return res
        res.track = simulate(panel, ws_o, wp_o, class_, criteria, convention_rotation=convention_rotation,
                            spot_cost_bp=spot_cost_bp, perp_cost_bp=perp_cost_bp)
        res.metrics = {**compute_metrics(res.track), **compute_gate_metrics(res.track)}
        res.code = OK
    except TrialError as e:
        res.code, res.detail = e.code, e.detail
    except Exception as e:  # noqa: BLE001
        res.code, res.detail = ERROR, type(e).__name__  # never the message (output channel)
    finally:
        end = {"id": eid, "status": res.code}
        if k_withdrawn is not None:
            end["days_withdrawn"] = int(k_withdrawn)  # k drawn for this trial (reproducibility)
        if res.code == OK:
            for k, v in res.metrics.items():
                end[k] = {a: decimal12(x) for a, x in v.items()} if isinstance(v, dict) else \
                    (v if isinstance(v, str) else decimal12(v))
        journal.end(end)
        if res.detail:
            journal.technical_detail(eid, res.detail)
        journal.anchor(arena_journal)
    return res


__all__ = [
    "TrialSheet",
    "WeightShape",
    "CapError",
    "TrialResult",
    "SourceRefused",
    "compute_metrics",
    "compute_gate_metrics",
    "run_trial",
    "verify_causality",
]
