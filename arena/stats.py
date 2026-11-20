"""Statistics on equity series (docs/SPEC-MVP.md §10 and §13).

Input: INTEGER equity series (µEUR), one value per cycle. Floats are allowed here (statistics and display,
never the money path). Pure Python, no dependency. All random draws use a fixed seed: same series, same
intervals.
"""

from __future__ import annotations

import itertools
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

CYCLES_PER_DAY = 6
DAYS_PER_YEAR = 365
PERIODS_PER_YEAR = CYCLES_PER_DAY * DAYS_PER_YEAR  # 2,190
BLOCK = 6  # one day of cycles
N_BOOT = 2_000
SEED = 20_261_111
ALPHA = 0.05


def returns(equity: Sequence[int]) -> list[float]:
    """Simple returns per cycle: e[i] / e[i-1] - 1. A series of fewer than 2 points gives []."""
    out = []
    for prev, cur in itertools.pairwise(equity):
        if prev <= 0:
            raise ValueError("equity <= 0: return undefined")
        out.append(cur / prev - 1.0)
    return out


def total_return(equity: Sequence[int]) -> float:
    """Total return e[-1] / e[0] - 1 (0.0 if fewer than 2 points)."""
    if len(equity) < 2:
        return 0.0
    if equity[0] <= 0:
        raise ValueError("equity initiale <= 0")
    return equity[-1] / equity[0] - 1.0


def max_drawdown(equity: Sequence[int]) -> float:
    """Maximum drawdown as a positive fraction of the peak (0.2 = -20%). 0.0 if the series never falls."""
    peak = 0
    worst = 0.0
    for e in equity:
        peak = max(peak, e)
        if peak > 0:
            worst = max(worst, (peak - e) / peak)
    return worst


def sharpe(rets: Sequence[float], periods_per_year: int = PERIODS_PER_YEAR) -> float:
    """Annualised Sharpe: mean / standard deviation (ddof = 1) × sqrt(periods_per_year), zero risk-free rate.

    Returns 0.0 if the standard deviation is zero (constant series) or there are fewer than 2 returns.
    """
    n = len(rets)
    if n < 2:
        return 0.0
    mean = math.fsum(rets) / n
    var = math.fsum((r - mean) ** 2 for r in rets) / (n - 1)
    if var <= 1e-30:  # constant series, up to rounding noise
        return 0.0
    return mean / math.sqrt(var) * math.sqrt(periods_per_year)


def _resample(rets: Sequence[float], block: int, rng: random.Random) -> list[float]:
    """A series resampled with moving blocks of length `block`, of the same length as `rets`."""
    n = len(rets)
    b = max(1, min(block, n))
    out: list[float] = []
    while len(out) < n:
        start = rng.randrange(n - b + 1)
        out.extend(rets[start : start + b])
    return out[:n]


def _percentiles(values: list[float], alpha: float) -> tuple[float, float]:
    values.sort()
    n = len(values)
    lo = values[min(n - 1, math.floor(alpha / 2 * n))]
    hi = values[min(n - 1, math.ceil((1 - alpha / 2) * n) - 1)]
    return lo, hi


def sharpe_ci(
    rets: Sequence[float],
    *,
    n_boot: int = N_BOOT,
    block: int = BLOCK,
    seed: int = SEED,
    alpha: float = ALPHA,
    periods_per_year: int = PERIODS_PER_YEAR,
) -> tuple[float, float]:
    """(1 - alpha) confidence interval of the Sharpe ratio by moving-block bootstrap (percentiles).

    Fewer than 2 returns: (0.0, 0.0).
    """
    if len(rets) < 2:
        return 0.0, 0.0
    rng = random.Random(seed)
    stats = [sharpe(_resample(rets, block, rng), periods_per_year) for _ in range(n_boot)]
    return _percentiles(stats, alpha)


def rank_in_distribution(value: float, distribution: Sequence[float]) -> float:
    """Percentile of `value` in `distribution`, in [0, 100]: share of values strictly below
    plus half of the ties. Empty distribution: ValueError."""
    n = len(distribution)
    if n == 0:
        raise ValueError("empty distribution")
    below = sum(1 for d in distribution if d < value)
    equal = sum(1 for d in distribution if d == value)
    return 100.0 * (below + equal / 2) / n


@dataclass(frozen=True)
class Distinction:
    """Result of `distinguishable`. `bool(result)` equals `significant`."""

    significant: bool
    mean_diff: float  # mean return difference per cycle (portfolio - reference)
    ci_low: float
    ci_high: float

    def __bool__(self) -> bool:
        return self.significant


def distinguishable(
    rets: Sequence[float],
    baseline_rets: Sequence[float],
    *,
    n_boot: int = N_BOOT,
    block: int = BLOCK,
    seed: int = SEED,
    alpha: float = ALPHA,
) -> Distinction:
    """Is the portfolio's return gap to the basket significant?

    PAIRED block bootstrap: the series of per-cycle differences is resampled (same blocks for both
    portfolios) and the mean is kept; the gap is significant if the 95% interval (percentiles) excludes 0.
    Otherwise the site shows "indistinguishable from chance".
    """
    if len(rets) != len(baseline_rets):
        raise ValueError("series of different lengths")
    diff = [a - b for a, b in zip(rets, baseline_rets, strict=True)]
    n = len(diff)
    if n < 2:
        return Distinction(False, 0.0, 0.0, 0.0)
    rng = random.Random(seed)
    means = [math.fsum(_resample(diff, block, rng)) / n for _ in range(n_boot)]
    lo, hi = _percentiles(means, alpha)
    mean = math.fsum(diff) / n
    return Distinction(lo > 0 or hi < 0, mean, lo, hi)
