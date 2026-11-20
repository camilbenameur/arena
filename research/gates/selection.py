"""Final selection (PROTOCOL §6 "Selection"): ranking by DSR, correlation of the excess returns, at most 3.

Chooses only among the trials that passed every gate (the caller filters with `Verdict.passed`).
No judgment: sort by decreasing DSR, then a greedy rule.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from research.gates.evaluate import section

#: Numerical tolerance of the comparison rho > max_basket_excess_correlation.
TOLERANCE_CORRELATION = 1e-12


@dataclass(frozen=True)
class Candidate:
    id: str
    dsr: float
    excess: pd.Series  # net return of the candidate minus return of the basket, daily


@dataclass(frozen=True)
class Selection:
    retained: tuple[str, ...]
    discarded: dict[str, str]  # id -> reason
    correlations: dict[tuple[str, str], float] = field(default_factory=dict)
    p_at_least_one_not_refuted: float = 0.0


def simulate_p_not_refuted(
    sigma_ann: float = 0.30, drawdown_backtest: float = 0.30, n_days: int = 56, n_sim: int = 400_000,
    seed: int = 20261111, look_step: int = 7, with_drawdown: bool = True,
) -> float:
    """P(not refuted | H0) by simulating the refutation rule of §9.

    H0: i.i.d. Gaussian daily return with ZERO mean, volatility = that of the backtest
    (`sigma_ann`, annualized with the square root of 365). The paper trading lasts `n_days` (56 or 84), with one
    look per week. Refuted if, at the end, the compounded cumulative return <= -0.5 x sigma_ann (56 d) or
    -0.6 x sigma_ann (84 d), or if, at any weekly look, the paper drawdown exceeds
    1.3 x `drawdown_backtest` (drawdown of the C15-constrained backtest). No alpha spending is simulated at
    the intermediate looks: the protocol sets a return threshold only at 56 and 84 days.
    This is NOT a calibration: the value obtained is reported, whatever it is.
    """
    factor = {56: -0.5, 84: -0.6}.get(n_days)
    if factor is None:
        raise ValueError("n_days must be 56 or 84 (criteria.yaml paper.refutation)")
    rng = np.random.default_rng(seed)
    sd = sigma_ann / math.sqrt(365.0)
    nav_end = np.empty(n_sim)
    dd_max = np.zeros(n_sim)
    looks = np.arange(look_step, n_days + 1, look_step)  # days 7, 14, ... (number of elapsed days)
    for start in range(0, n_sim, 100_000):
        k = min(100_000, n_sim - start)
        nav = np.cumprod(1.0 + rng.normal(0.0, sd, (k, n_days)), axis=1)
        nav_end[start:start + k] = nav[:, -1]
        nv = np.concatenate([np.ones((k, 1)), nav], axis=1)
        dd = 1.0 - nv / np.maximum.accumulate(nv, axis=1)
        dd_max[start:start + k] = dd[:, looks].max(axis=1)
    refuted = (nav_end - 1.0) <= factor * sigma_ann
    if with_drawdown:
        refuted |= dd_max > 1.3 * drawdown_backtest
    return float(1.0 - refuted.mean())


# P(not refuted | H0) of a candidate with 30% volatility and 30% backtest drawdown (56 days), SIMULATED
# value (fixed seed, 400,000 paths, standard error ~ 5e-4), not calibrated to a wanted result: it is
# close to 0.91, i.e. paper trading almost never refutes a candidate without an edge. A test reruns the
# simulation and checks this constant. The protocol §6 figure of "about 85% for 3" is therefore wrong:
# 1 - (1 - 0.907)^3 = 0.999.
P_NOT_REFUTED_H0_DEFAULT = 0.9068475


def prob_at_least_one_not_refuted(n_candidates: int, p_not_refuted_h0: float = P_NOT_REFUTED_H0_DEFAULT) -> float:
    """P(at least one not refuted | H0) = 1 - (1 - p)^n, candidates assumed independent (upper bound)."""
    if n_candidates <= 0:
        return 0.0
    return 1.0 - (1.0 - p_not_refuted_h0) ** n_candidates


def select_candidates(
    candidates: Sequence[Candidate],
    criteria,
    p_not_refuted_h0: float = P_NOT_REFUTED_H0_DEFAULT,
) -> Selection:
    """Rank by decreasing DSR; keep a candidate if its (Pearson, daily) excess-return correlation with each
    candidate already retained is <= max_basket_excess_correlation (compared with a tolerance of
    1e-12: discarded if rho > 0.7 + 1e-12); at most 3.

    Only STRONGLY POSITIVE correlations discard: a negative correlation (even -0.99) triggers no
    discard, as the protocol says ("correlated above 0.7")."""
    sel = section(criteria, "selection")
    cmax = sel["max_basket_excess_correlation"]
    nmax = int(sel["max_candidates"])
    ranked = sorted(candidates, key=lambda c: (-c.dsr, c.id))  # DSR tie: order by id, deterministic
    retained: list[Candidate] = []
    discarded: dict[str, str] = {}
    corr: dict[tuple[str, str], float] = {}
    for c in ranked:
        if len(retained) >= nmax:
            discarded[c.id] = f"beyond {nmax} candidates"
            continue
        reason = None
        for r in retained:
            a, b = c.excess.align(r.excess, join="inner")
            rho = float(a.corr(b)) if len(a) > 2 else float("nan")
            corr[(r.id, c.id)] = rho
            if math.isnan(rho) or rho > cmax + TOLERANCE_CORRELATION:  # NaN: cannot be checked, discard
                reason = f"excess correlation with {r.id} : {rho:.3f} > {cmax}"
                break
        if reason:
            discarded[c.id] = reason
        else:
            retained.append(c)
    return Selection(
        retained=tuple(c.id for c in retained),
        discarded=discarded,
        correlations=corr,
        p_at_least_one_not_refuted=prob_at_least_one_not_refuted(len(retained), p_not_refuted_h0),
    )
