"""Statistics of the gates (research-v1). Pure functions on DAILY returns (pd.Series with a date index, or
ndarray for the functions without a calendar). Annualization with √365 (crypto, 7 days a week).

None of these functions reads market data: the engine supplies the series.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, skew

DAYS_PER_YEAR = 365


def _arr(x) -> np.ndarray:
    return np.asarray(x, dtype=float)


def sr_day(r) -> float:
    """Daily Sharpe (not annualized), standard deviation with ddof=1. NaN if variance is zero or fewer than 2 points."""
    x = _arr(r)
    if len(x) < 2:
        return float("nan")
    sd = x.std(ddof=1)
    return float(x.mean() / sd) if sd > 0 else float("nan")


def sharpe(r) -> float:
    """Annualized Sharpe (x √365)."""
    return sr_day(r) * math.sqrt(DAYS_PER_YEAR)


def moments(r) -> tuple[float, float]:
    """(skewness, non-excess kurtosis), biased as in the lab."""
    x = _arr(r)
    return float(skew(x, bias=True)), float(kurtosis(x, fisher=False, bias=True))


def t_newey_west(r, lags: int = 20) -> float:
    """t-statistic of the mean, Newey-West long-run variance (Bartlett weights), as in the lab."""
    x = _arr(r)
    n = len(x)
    m = x.mean()
    c = x - m
    lrv = float(c @ c) / n
    for k in range(1, lags + 1):
        lrv += 2.0 * (1.0 - k / (lags + 1)) * float(c[k:] @ c[:-k]) / n
    return float(m / math.sqrt(lrv / n)) if lrv > 0 else float("nan")


def drawdown(r) -> float:
    """Maximum drawdown of the compounded net asset value at daily closes (starting at 1)."""
    nav = np.concatenate([[1.0], np.cumprod(1.0 + _arr(r))])
    peak = np.maximum.accumulate(nav)
    return float((1.0 - nav / peak).max())


def annualized_return(r) -> float:
    """Geometric annualized return: (prod(1+r))^(365/n) - 1."""
    x = _arr(r)
    if len(x) == 0:
        return float("nan")
    nav = float(np.prod(1.0 + x))
    if nav <= 0:
        return -1.0
    return nav ** (DAYS_PER_YEAR / len(x)) - 1.0


def annual_turnover(rotation) -> float:
    """Annual turnover = sum of the daily turnovers / (n / 365)."""
    x = _arr(rotation)
    return float(x.sum() / (len(x) / DAYS_PER_YEAR))


def bootstrap_blocks(
    x, length: int = 20, replications: int = 5000, seed: int = 12345, batch: int = 500
) -> dict:
    """Circular block bootstrap with blocks of `length` days. H0: mean <= 0.

    The series is centered (zero mean) and resampled by blocks; one-sided p = (1 + number of resampled
    means >= observed mean) / (replications + 1). Same algorithm as the lab (C10).
    """
    v = _arr(x)
    T = len(v)
    obs = float(v.mean())
    c = v - obs
    rng = np.random.default_rng(seed)
    n_blocks = math.ceil(T / length)
    offsets = np.arange(length)
    ge = 0
    seen = 0
    while seen < replications:
        k = min(batch, replications - seen)
        starts = rng.integers(0, T, size=(k, n_blocks))
        idx = ((starts[:, :, None] + offsets) % T).reshape(k, -1)[:, :T]
        ge += int((c[idx].mean(axis=1) >= obs).sum())
        seen += k
    return {"p": (ge + 1) / (replications + 1), "mean": obs, "T": T}


def bootstrap_paired(a, b, length: int = 20, replications: int = 5000, seed: int = 12345) -> dict:
    """Paired block bootstrap on the difference a - b (series aligned by index if pd.Series)."""
    if isinstance(a, pd.Series) and isinstance(b, pd.Series):
        a, b = a.align(b, join="inner")
    d = _arr(a) - _arr(b)
    if len(d) < 2:
        raise ValueError("series too short for a paired bootstrap")
    return bootstrap_blocks(d, length, replications, seed)


def regression_alpha_beta(y, x, lags: int = 20) -> dict:
    """OLS y = alpha + beta x + u, Newey-West HAC variance (Bartlett), without small-sample correction.

    Returns alpha_day, alpha_annual (x365), beta, t_alpha, t_beta. Series aligned by index if pd.Series.
    """
    if isinstance(y, pd.Series) and isinstance(x, pd.Series):
        y, x = y.align(x, join="inner")
    yv = _arr(y)
    xv = _arr(x)
    n = len(yv)
    X = np.column_stack([np.ones(n), xv])
    xtx_inv = np.linalg.inv(X.T @ X)
    coef = xtx_inv @ X.T @ yv
    u = yv - X @ coef
    Xu = X * u[:, None]
    S = Xu.T @ Xu
    for k in range(1, lags + 1):
        g = Xu[k:].T @ Xu[:-k]
        S += (1.0 - k / (lags + 1)) * (g + g.T)
    cov = xtx_inv @ S @ xtx_inv
    se = np.sqrt(np.diag(cov))
    return {
        "alpha_day": float(coef[0]),
        "alpha_annual": float(coef[0] * DAYS_PER_YEAR),
        "beta": float(coef[1]),
        "t_alpha": float(coef[0] / se[0]) if se[0] > 0 else float("nan"),
        "t_beta": float(coef[1] / se[1]) if se[1] > 0 else float("nan"),
    }


def remove_best_days(r, share: float):
    """Remove the ceil(share x n) best days (dropped, not set to zero). Returns (series, number removed)."""
    n = len(r)
    k = math.ceil(share * n - 1e-12)
    if k <= 0:
        return r, 0
    if isinstance(r, pd.Series):
        kept = r.drop(r.nlargest(k).index) if r.index.is_unique else r.sort_values().iloc[:-k]
        return kept.sort_index() if r.index.is_unique else kept, k
    v = _arr(r)
    return np.sort(v)[:-k], k


def _flat(x) -> bool:
    """At least 2 points, all exactly zero (flat strategy: zero standard deviation, NaN Sharpe)."""
    v = _arr(x)
    return len(v) >= 2 and bool(np.all(v == 0.0))


def sharpe_per_year(r: pd.Series, years: Sequence[int], *, flat_is_zero: bool = False) -> dict[int, float]:
    """Annualized Sharpe per calendar year; NaN if the year is absent.

    A year with exactly zero returns (strategy flat all year) has a zero standard deviation, hence a
    NaN Sharpe. With `flat_is_zero`, it is 0.0: "not positive and not below −1" for C5.
    """
    out = {}
    for a in years:
        sel = r[r.index.year == a]
        if flat_is_zero and _flat(sel):
            out[int(a)] = 0.0
        else:
            out[int(a)] = sharpe(sel) if len(sel) >= 2 else float("nan")
    return out


def sharpe_halves(r) -> tuple[float, float]:
    """Sharpe of each half of the window (first half = first n // 2 days).

    A half entirely flat (all returns zero) has a Sharpe of 0.0 (not NaN): C13 requires
    > 0 in each half, so a flat half fails C13.
    """
    x = _arr(r)
    h = len(x) // 2
    halves = (x[:h], x[h:])
    return tuple(0.0 if _flat(m) else sharpe(m) for m in halves)  # type: ignore[return-value]
