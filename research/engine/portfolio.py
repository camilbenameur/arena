"""Simulation of the portfolio in quantities (protocol §3) from the daily target weights.

Timeline (same as the lab): the weights decided at the close of day i apply to the return of day i+1;
the costs of the rotation decided at i are charged to the return of day i+1. All output arrays are
indexed by the return day (`days[j]` = day whose close ends the return).

Rotation (`drifted` convention, the protocol's): rotation_i = Σ |w_target_i − w_drifted_i| with
w_drifted_i = w_{i-1} (1 + r_i) / (1 + r_p,i) per leg (r_p = gross portfolio return, funding included).
`target` convention (reproduction of the lab, E0065): rotation_i = Σ |w_target_i − w_target_{i-1}|.

Classes: `directional` (spot only, w ∈ [0,1], Σw ≤ 1) and `hedged` (perp short ≤ spot long per pair,
immobilized capital Σ w_spot + margin · Σ w_perp ≤ 1). Any violation raises `WeightShape`; never clipping.
Returns are P&L relative to total capital (1); `immobilized_net_returns` relates them to the day's
immobilized capital (perp margin included; divisor max(expo_j, expo_{j-1}), see `immobilized_divisor`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from research.engine.contract import WEIGHT_TOL, WeightShape
from research.engine.panel import Panel

CLASSES = ("directional", "hedged")


#: Minimum share of the spot long that must be covered by the perp short, per pair and per day (hedged class).
#: 0.9 in `research-engine-v1`; 0 since `research-engine-v2` (erratum 5): partial hedging is allowed, the
#: discipline comes from gates C6 (drawdown <= 20%) and C8 (|beta| <= 0.3).
HEDGED_MIN = 0.0


def validate_weight(class_: str, i: int, ws: np.ndarray, wp: np.ndarray, already_listed: np.ndarray,
                  eligibles_perp: np.ndarray | None, margin: float) -> None:
    """Strict validation of the bounds for one day. `already_listed`: pair listed on or before that day.

    `hedged` class: STRICT reading of the protocol §3 definition ("spot long and perp short on the same
    pair, with perp short <= spot long"): on every pair and every day,
    `HEDGED_MIN * spot_weight <= perp_weight <= spot_weight`. Since `research-engine-v2`, HEDGED_MIN = 0:
    any partial hedge is allowed, never a perp short larger than the spot long; `WEIGHT_SHAPE` otherwise,
    never clipping.

    Error messages contain no value coming from the strategy (output channel): only the day and the
    rule violated."""
    if class_ not in CLASSES:
        raise WeightShape(f"unknown class {class_!r}")
    if not (np.isfinite(ws).all() and np.isfinite(wp).all()):
        raise WeightShape(f"day {i}: non-finite weights")
    if ws.min(initial=0.0) < -WEIGHT_TOL or wp.min(initial=0.0) < -WEIGHT_TOL:
        raise WeightShape(f"day {i}: negative weight")
    if (ws[~already_listed] > WEIGHT_TOL).any():
        raise WeightShape(f"day {i}: weight on an unlisted pair")
    if class_ == "directional":
        if wp.max(initial=0.0) > WEIGHT_TOL:
            raise WeightShape(f"day {i}: perp leg forbidden in the directional class")
        if ws.sum() > 1.0 + WEIGHT_TOL:
            raise WeightShape(f"day {i}: sum of weights > 1")
        return
    if (wp > ws + WEIGHT_TOL).any():
        raise WeightShape(f"day {i}: perp short larger than the spot long")
    if (wp < HEDGED_MIN * ws - WEIGHT_TOL).any():
        raise WeightShape(f"day {i}: perp short below the minimum hedge of the spot long")
    if eligibles_perp is None:
        if wp.max(initial=0.0) > WEIGHT_TOL:
            raise WeightShape(f"day {i}: perp weight without perp data")
    elif (wp[~eligibles_perp] > WEIGHT_TOL).any():
        raise WeightShape(f"day {i}: perp weight on an absent perpetual")
    if ws.sum() + margin * wp.sum() > 1.0 + WEIGHT_TOL:
        raise WeightShape(f"day {i}: immobilized capital > 1")


def immobilized_divisor(exposure: np.ndarray) -> np.ndarray:
    """Reference capital of the day for the "on immobilized capital" series: max(expo_j, expo_{j-1}).
    The costs of day j are those of the rotation decided at j-1 (from w_{j-2} to w_{j-1}); dividing by the
    day's exposure alone would erase the cost of a full exit (exposure 0 on the exit day)."""
    prev = np.concatenate([[0.0], exposure[:-1]])
    return np.maximum(exposure, prev)


def relative_to(values: np.ndarray, exposure: np.ndarray) -> np.ndarray:
    """`values` (P&L relative to total capital) relative to the reference immobilized capital; 0 if zero."""
    d = immobilized_divisor(exposure)
    return np.where(d > 1e-12, values / np.where(d > 1e-12, d, 1.0), 0.0)


@dataclass(frozen=True)
class EngineSeries:
    """Complete result of a trial (reserved for the orchestrator and the gates; never returned to an agent)."""

    class_: str
    days: np.ndarray  # (T,) UTC seconds of the return day
    net_returns: np.ndarray
    stressed_net_returns: np.ndarray
    gross_returns: np.ndarray
    rotation: np.ndarray  # total rotation (spot + perp) charged to the day
    rotation_spot: np.ndarray
    rotation_perp: np.ndarray
    costs: np.ndarray  # normal costs charged to the day
    exposure: np.ndarray  # immobilized capital of the day (Σ w_spot + margin Σ w_perp)
    immobilized_net_returns: np.ndarray
    funding: np.ndarray  # net funding received during the day (part of the gross)
    eligible: np.ndarray  # (T,) bool: at least one eligible pair that day
    eval_mask: np.ndarray  # (T,) bool: days of the evaluation window where the strategy is measurable
    spot_weight: np.ndarray  # (T, N) weights decided at the close of the day (original column order)
    perp_weight: np.ndarray
    symbols: tuple[str, ...]

    def evaluation(self, field: str = "net_returns") -> np.ndarray:
        return getattr(self, field)[self.eval_mask]


def _ts_day(iso: str) -> int:
    return int(pd.Timestamp(iso, tz="UTC").timestamp())


def evaluation_mask(panel: Panel, class_: str, criteria) -> tuple[np.ndarray, np.ndarray]:
    """(eligible, eval_mask): days of the window where at least one pair is eligible (protocol §3);
    for `hedged`, spot AND perp, and the window ends at `perp_window_end`."""
    T = panel.n_days
    start = _ts_day(criteria.data.evaluation_window.start)
    end = _ts_day(criteria.data.evaluation_window.end)
    if class_ == "hedged" and panel.eligibles_perp is not None:
        elig = (panel.eligibles & panel.eligibles_perp).any(axis=1)
        end = min(end, _ts_day(criteria.data.perp_window_end))
    elif class_ == "hedged":
        elig = np.zeros(T, dtype=bool)
    else:
        elig = panel.eligibles.any(axis=1)
    mask = (panel.days >= start) & (panel.days <= end) & elig
    mask[0] = False
    return elig, mask


def simulate(
    panel: Panel, spot_weight: np.ndarray, perp_weight: np.ndarray, class_: str, criteria,
    *, convention_rotation: str = "drifted", spot_cost_bp: int | None = None, perp_cost_bp: int | None = None,
) -> EngineSeries:
    """Simulates the portfolio. `*_weight`: (T, N), one vector of target weights per decision day."""
    if convention_rotation not in ("drifted", "target"):
        raise ValueError(convention_rotation)
    T, N = panel.n_days, panel.n_pairs
    cs = (criteria.spot_cost_bp if spot_cost_bp is None else spot_cost_bp) / 1e4
    cp = (criteria.perp_cost_bp if perp_cost_bp is None else perp_cost_bp) / 1e4
    stress = criteria.stress_multiplier
    margin = criteria.perp_share_margin
    r_s = panel.spot_returns()
    r_p = panel.perp_returns()
    fund = panel.funding_per_day()

    gross = np.zeros(T)
    fund_j = np.zeros(T)
    rot_s = np.zeros(T)
    rot_p = np.zeros(T)
    costs = np.zeros(T)
    expo = np.zeros(T)
    prev_s = np.zeros(N)
    prev_p = np.zeros(N)
    prev_cost = 0.0
    for j in range(T):
        # return of day j with the weights decided at j-1; costs of the rotation decided at j-1
        if j > 0:
            gain_s = float(prev_s @ r_s[j])
            gain_p = float(prev_p @ (fund[j] - r_p[j]))
            gross[j] = gain_s + gain_p
            fund_j[j] = float(prev_p @ fund[j])
            costs[j] = prev_cost
            expo[j] = prev_s.sum() + margin * prev_p.sum()
        # decision of day j
        cs_j, cp_j = spot_weight[j], perp_weight[j]
        if convention_rotation == "drifted" and j > 0:
            denom = 1.0 + gross[j]
            last_s = prev_s * (1.0 + r_s[j]) / denom
            last_p = prev_p * (1.0 + r_p[j]) / denom
        else:
            last_s, last_p = prev_s, prev_p
        a = float(np.abs(cs_j - last_s).sum())
        b = float(np.abs(cp_j - last_p).sum())
        rot_s[j], rot_p[j] = a, b  # charged to day j+1: shifted below
        prev_cost = cs * a + cp * b
        prev_s, prev_p = cs_j, cp_j
    # the rotation decided at j is paid on day j+1
    rot_s = np.concatenate([[0.0], rot_s[:-1]])
    rot_p = np.concatenate([[0.0], rot_p[:-1]])
    net = gross - costs
    net2 = gross - stress * costs
    immobilized = relative_to(net, expo)

    elig, mask = evaluation_mask(panel, class_, criteria)
    return EngineSeries(
        class_=class_, days=panel.days.copy(), net_returns=net, stressed_net_returns=net2,
        gross_returns=gross, rotation=rot_s + rot_p, rotation_spot=rot_s, rotation_perp=rot_p, costs=costs,
        exposure=expo, immobilized_net_returns=immobilized, funding=fund_j, eligible=elig,
        eval_mask=mask, spot_weight=spot_weight, perp_weight=perp_weight, symbols=panel.symbols)


def equal_weighted_basket(panel: Panel, criteria, *, rebalancing_days: str = "monthly",
                       eligibles: np.ndarray | None = None) -> EngineSeries:
    """Equal-weighted basket of the eligible pairs, rebalanced on the 1st of each month, same costs (directional
    class). The weights decided on the last day of the month (close) are 1/n_eligible; between two
    rebalancings the weights drift. Serves as the reference for C8 and for the acceptance test 1/15."""
    T, N = panel.n_days, panel.n_pairs
    elig = panel.eligibles if eligibles is None else eligibles
    r_s = panel.spot_returns()
    cs = criteria.spot_cost_bp / 1e4
    dates = pd.to_datetime(panel.days, unit="s")
    # the rebalancing is decided at the close of the last day of the month = open of the 1st
    first_of_month = np.zeros(T, dtype=bool)
    first_of_month[:-1] = dates[1:].day == 1
    w = np.zeros(N)
    gross = np.zeros(T)
    costs = np.zeros(T)
    expo = np.zeros(T)
    weight = np.zeros((T, N))
    prev_cost = 0.0
    for j in range(T):
        if j > 0:
            gross[j] = float(w @ r_s[j])
            costs[j] = prev_cost
            expo[j] = w.sum()
            w = w * (1.0 + r_s[j]) / (1.0 + gross[j])  # drift
        if j == 0 or first_of_month[j] or w.sum() == 0.0:
            n = int(elig[j].sum())
            target = np.where(elig[j], 1.0 / n, 0.0) if n else np.zeros(N)
        else:
            target = w
        prev_cost = cs * float(np.abs(target - w).sum())
        w = target
        weight[j] = w
    net = gross - costs
    return EngineSeries(
        class_="directional", days=panel.days.copy(), net_returns=net,
        stressed_net_returns=gross - 2 * costs, gross_returns=gross, rotation=np.zeros(T),
        rotation_spot=np.zeros(T), rotation_perp=np.zeros(T), costs=costs, exposure=expo,
        immobilized_net_returns=net, funding=np.zeros(T), eligible=elig.any(axis=1),
        eval_mask=evaluation_mask(panel, "directional", criteria)[1], spot_weight=weight, perp_weight=np.zeros((T, N)),
        symbols=panel.symbols)
