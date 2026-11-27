import numpy as np
import pandas as pd

# Cross-sectional 7-day momentum, market neutral, daily rebalance.
# Status: NO ROBUST EDGE FOUND -- this is the most defensible simple (pre-registered, un-tuned) rule, not a validated edge.

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
LOOKBACK = 42  # bars = 7 days of 4h bars


def targets(df):
    d = df[["ts", "ticker", "close"]].copy()
    d["ts"] = pd.to_datetime(d["ts"])
    c = d.pivot_table(index="ts", columns="ticker", values="close", aggfunc="last")
    c = c.reindex(columns=TICKERS).sort_index()
    mom = c / c.shift(LOOKBACK) - 1.0                      # trailing 7-day return, causal
    rk = mom.rank(axis=1, method="first", ascending=False)  # 1 = strongest, per-bar cross-section only
    W = pd.DataFrame(0.0, index=c.index, columns=TICKERS)
    W[rk <= 2] = 1.0     # long two strongest
    W[rk >= 5] = -1.0    # short two weakest
    W[mom.isna().any(axis=1)] = 0.0  # warm-up / missing data -> flat
    idx = c.index
    decide = idx.hour == 20  # decide once a day, at the close of the 20:00 UTC bar (00:00 UTC)
    W = W.where(pd.Series(decide, index=idx), np.nan, axis=0).ffill().fillna(0.0)
    return W.clip(-2, 2).astype(float)
