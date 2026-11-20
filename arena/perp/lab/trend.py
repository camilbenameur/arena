"""The trend engine of the council v4 (docs/SPEC-TREND-COUNCIL.md), frozen on 17/11/2026 before the holdout
was read: an EMA crossover on 4-hour bars, symmetric long/short per contract, sized by volatility targeting.

- bars: the close of each 4-hour block of minutes;
- signal: z = ((EMA_fast - EMA_slow) / EMA_slow) / (hourly_sd * sqrt(slow * hours)); long when z > band, short
  when z < -band, back to flat when z crosses 0 (hysteresis);
- size: sign * target_daily_vol / daily_sd, capped per contract; the daily sd (hourly sd over 5 days * sqrt(24))
  is re-estimated once a day (low turnover);
- `scale` multiplies the weights (the council runs it at 2x).

`targets(data)` gives the (N, K) matrix of the bench (row = minute where a bar closes); `latest(data)` the target
of the last closed bar, for the live council.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from arena.perp.lab.backtest import Data


@dataclass(frozen=True)
class TrendParams:
    bar_hours: int = 4
    fast: int = 12  # bars (2 days)
    slow: int = 36  # bars (6 days)
    band: float = 0.3
    target_daily_vol: float = 0.006
    cap: float = 2.0  # per contract, before `scale`
    vol_window_h: int = 120
    scale: float = 1.0


FROZEN = TrendParams()


def _ewm(x: np.ndarray, span: int) -> np.ndarray:
    return pd.DataFrame(x).ewm(span=span, adjust=False).mean().values


def _hourly_sd(close_min: np.ndarray, win: int) -> np.ndarray:
    n, k = close_min.shape
    count = n // 60
    c1 = close_min[: count * 60].reshape(count, 60, k)[:, -1]
    r = np.diff(np.log(c1), axis=0, prepend=np.nan)
    return pd.DataFrame(r).rolling(win, min_periods=win // 2).std().values


def bar_weights(data: Data, p: TrendParams = FROZEN) -> tuple[np.ndarray, np.ndarray]:
    """(bar_end_index (nb,), weights (nb, K)): the target decided at the close of each bar."""
    n, k = data.close.shape
    h = p.bar_hours
    m = 60 * h
    count = n // m
    c = data.close[: count * m].reshape(count, m, k)[:, -1]
    sd1 = _hourly_sd(data.close, p.vol_window_h)[np.arange(count) * h + h - 1]
    ef, es = _ewm(c, p.fast), _ewm(c, p.slow)
    z = np.nan_to_num(((ef - es) / es) / (sd1 * np.sqrt(p.slow * h)))
    state = np.zeros((count, k))
    cur = np.zeros(k)
    for b in range(count):
        for j in range(k):
            if (cur[j] > 0 and z[b, j] < 0) or (cur[j] < 0 and z[b, j] > 0):
                cur[j] = 0
            if cur[j] == 0:
                if z[b, j] > p.band:
                    cur[j] = 1
                elif z[b, j] < -p.band:
                    cur[j] = -1
        state[b] = cur
    per_day = 24 // h
    idx = (np.arange(count) // per_day) * per_day
    sig_day = (sd1 * np.sqrt(24))[idx]
    safe = np.where(np.isnan(sig_day) | (sig_day == 0), np.inf, sig_day)
    w = np.nan_to_num(state * np.clip(p.target_daily_vol / safe, 0, p.cap)) * p.scale
    return np.arange(count) * m + m - 1, w


def targets(data: Data, p: TrendParams = FROZEN) -> np.ndarray:
    rows, w = bar_weights(data, p)
    t = np.full(data.close.shape, np.nan)
    t[rows] = w
    return t


def latest(data: Data, p: TrendParams = FROZEN) -> tuple[int, np.ndarray]:
    """(ts of the minute closing the last complete bar, its weights). `data` must start on a bar boundary of the
    live clock (see `arena.perp.trend_council`), with at least 30 days of history for the EMAs to settle."""
    rows, w = bar_weights(data, p)
    return int(data.ts[rows[-1]]), w[-1]
