"""Frozen rule: slow Donchian trend (20-day breakout entry, 10-day opposite-extreme exit), long/short/flat per contract,
inverse-volatility size fixed at entry.  STATUS: no robust edge found on the design period; this is the most defensible
low-turnover fallback (trial 9 of the log), not a validated finding.  Causal: row t uses only bars with ts <= t."""
import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
N_ENTRY = 120      # 20 days of 4h bars: breakout lookback (multi-week trend horizon)
N_EXIT = 60        # 10 days: exit when close crosses the opposite 10-day extreme (hysteresis, limits whipsaw)
VOL_WIN = 120      # 20 days: trailing volatility of 4h log returns
TARGET_VOL = 0.01  # per-bar volatility at which a position has weight 1.0
W_MIN, W_MAX = 0.5, 2.0


def targets(df):
    d = df[["ts", "ticker", "close"]].copy()
    d["ts"] = pd.to_datetime(d["ts"])
    close = d.pivot_table(index="ts", columns="ticker", values="close", aggfunc="last").sort_index()
    close = close.reindex(columns=TICKERS).ffill()          # forward fill only: causal
    logret = np.log(close).diff()
    vol = logret.rolling(VOL_WIN).std()
    prev = close.shift(1)                                   # channels exclude the current bar
    hi_n, lo_n = prev.rolling(N_ENTRY).max(), prev.rolling(N_ENTRY).min()
    hi_x, lo_x = prev.rolling(N_EXIT).max(), prev.rolling(N_EXIT).min()
    out = pd.DataFrame(0.0, index=close.index, columns=TICKERS)
    for tk in TICKERS:
        c = close[tk].to_numpy(float)
        a, b = hi_n[tk].to_numpy(float), lo_n[tk].to_numpy(float)
        hx, lx = hi_x[tk].to_numpy(float), lo_x[tk].to_numpy(float)
        v = vol[tk].to_numpy(float)
        pos, col = 0.0, np.zeros(len(c))
        for i in range(len(c)):
            if not (np.isnan(c[i]) or np.isnan(a[i]) or np.isnan(b[i]) or np.isnan(v[i]) or v[i] <= 0):
                if pos > 0 and c[i] < lx[i]:
                    pos = 0.0
                if pos < 0 and c[i] > hx[i]:
                    pos = 0.0
                size = float(np.clip(TARGET_VOL / v[i], W_MIN, W_MAX))
                if c[i] > a[i] and pos <= 0:
                    pos = size
                elif c[i] < b[i] and pos >= 0:
                    pos = -size
            col[i] = pos
        out[tk] = col
    out = out.fillna(0.0).clip(-2.0, 2.0).astype(float)
    out.index.name = "ts"
    return out
