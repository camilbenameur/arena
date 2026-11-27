import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
LOOKBACK = 180      # bars (30 days) for beta estimation
MIN_OBS = 90        # bars (15 days) before trading
REBAL = 42          # bars (7 days) between rebalances
N_SIDE = 2          # names per side


def targets(df):
    close = df.pivot(index="ts", columns="ticker", values="close").sort_index()
    close = close.reindex(columns=TICKERS)
    r = close.pct_change()
    m = r.mean(axis=1)
    beta = r.rolling(LOOKBACK, min_periods=MIN_OBS).cov(m).div(
        m.rolling(LOOKBACK, min_periods=MIN_OBS).var(), axis=0)
    W = pd.DataFrame(np.nan, index=close.index, columns=TICKERS)
    n = len(close)
    b = beta.to_numpy(float)
    out = np.full((n, len(TICKERS)), np.nan)
    for t in range(0, n, REBAL):          # weekly decision grid anchored at the first bar
        row = b[t]
        if np.isnan(row).any():
            out[t] = 0.0
            continue
        order = np.argsort(row, kind="mergesort")
        lo, hi = order[:N_SIDE], order[-N_SIDE:]
        w = np.zeros(len(TICKERS))
        bl, bh = row[lo].mean(), row[hi].mean()
        if bl <= 0 or bh <= 0:
            out[t] = 0.0
            continue
        w[lo] = min(1.0 / bl, 2.0)       # long low-beta names, levered to ~beta 1
        w[hi] = max(-1.0 / bh, -2.0)     # short high-beta names, delevered to ~beta 1
        out[t] = w
    W[:] = out
    W = W.ffill().fillna(0.0).clip(-2.0, 2.0)
    W.index.name = "ts"
    return W
