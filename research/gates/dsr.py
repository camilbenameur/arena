"""Deflated Sharpe ratio of Bailey & López de Prado (2014), research-v1.

Formulas of the lab's reference implementation, copied without the lab journal. Everything in DAILY
units: sr_day = mean / standard deviation of the net daily returns (not annualized), T = number of days,
skew, kurt = NON-excess kurtosis (3 for the normal distribution).

    SR* = sqrt(V) * ((1-g) * Phi^-1(1-1/N) + g * Phi^-1(1-1/(N*e)))      g = 0,5772156649
    DSR = Phi( (SR - SR*) * sqrt(T-1) / sqrt(1 - skew*SR + (kurt-1)/4 * SR^2) )
    V   = max(1/(T-1), family-weighted mean of the within-family variances,
              variance of all the class's sr_day)                          (PROTOCOL §5, hardened)

The published numerical example (annualized SR 2.5, T=1250, skewness -3, kurtosis 10, N=100, annualized
variance of the Sharpe ratios 0.5, 250 days per year) gives DSR = 0.9004 in the paper; it is reproduced in the tests.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from scipy.optimize import brentq
from scipy.stats import norm

GAMMA = 0.5772156649  # Euler-Mascheroni, value from criteria.yaml
N_MINIMUM = 2
DAYS_PER_YEAR = 365


def sr_star(V: float, N: int) -> float:
    """Expected daily Sharpe of the best of N trials without a real edge (V = daily variance)."""
    if N < N_MINIMUM:
        raise ValueError(f"N={N} refused: the DSR requires N >= {N_MINIMUM}")
    if not (V > 0 and math.isfinite(V)):
        raise ValueError(f"V must be > 0 and finite (got {V})")
    return math.sqrt(V) * (
        (1 - GAMMA) * norm.ppf(1 - 1.0 / N) + GAMMA * norm.ppf(1 - 1.0 / (N * math.e))
    )


def dsr_prob(sr_day: float, T: int, skew: float, kurt: float, N: int, V: float) -> float:
    """Probability that the Sharpe is real (daily units, non-excess kurtosis)."""
    if T < 2:
        raise ValueError("T must be >= 2")
    if not math.isfinite(sr_day):
        raise ValueError("sr_day not finite: DSR impossible")
    sr0 = sr_star(V, N)
    denom = 1 - skew * sr_day + (kurt - 1) / 4.0 * sr_day**2
    if not denom > 0:
        raise ValueError(f"non-positive denominator ({denom}): inconsistent skew/kurt")
    z = (sr_day - sr0) * math.sqrt(T - 1) / math.sqrt(denom)
    return float(norm.cdf(z))


def variance_floor(T: int) -> float:
    """Floor of V: 1/(T-1)."""
    return 1.0 / (T - 1)


def class_variance(sr_per_family: dict[str, Iterable[float]], T: int) -> float:
    """V of a class: max(1/(T-1), family-weighted mean of the within-family variances, variance of all the
    class's sr_day).

    `sr_per_family`: family -> sr_day of ALL the research trials of this class, all waves, resumptions
    included (lab excluded). Weight = number of trials of the family; a family with fewer than 2 trials
    has no within-family variance but its sr_day still count in the overall variance.

    The third term (added by the review) protects against dilution: the mean of the within-family
    variances drops if dummy families whose variants are almost identical (ignored parameters) are
    added, whereas the dispersion of the whole set cannot be masked that way.
    """
    num = 0.0
    weight = 0
    pooled: list[float] = []
    for srs in sr_per_family.values():
        v = [float(x) for x in srs if x is not None and math.isfinite(float(x))]
        pooled.extend(v)
        if len(v) < 2:
            continue
        m = sum(v) / len(v)
        var = sum((x - m) ** 2 for x in v) / (len(v) - 1)
        num += len(v) * var
        weight += len(v)
    terms = [variance_floor(T)]
    if weight:
        terms.append(num / weight)
    if len(pooled) >= 2:
        m = sum(pooled) / len(pooled)
        terms.append(sum((x - m) ** 2 for x in pooled) / (len(pooled) - 1))
    return max(terms)


def v_from_annual_std(sharpe_annualized_std: float) -> float:
    """Daily variance equivalent to an annualized Sharpe standard deviation (columns 0.5 / 0.7 of §5)."""
    return sharpe_annualized_std**2 / DAYS_PER_YEAR


def required_sharpe(
    N: int,
    T: int,
    V: float | None = None,
    skew: float = 0.0,
    kurt: float = 3.0,
    target: float = 0.95,
    annualized: bool = True,
) -> float:
    """Net Sharpe required for DSR >= target. V = None: floor 1/(T-1).

    Returns the annualized Sharpe (x sqrt(365)) if `annualized`, else the sr_day. DSR is strictly increasing
    in sr_day (derivative of the numerator over a constant-sign denominator), so the root is unique.
    """
    v = variance_floor(T) if V is None else V
    sr0 = sr_star(v, N)

    def f(sr: float) -> float:
        return dsr_prob(sr, T, skew, kurt, N, v) - target

    sr = float(brentq(f, sr0, max(1.0, 10 * sr0), xtol=1e-14))
    return sr * math.sqrt(DAYS_PER_YEAR) if annualized else sr
