import numpy as np
import pandas as pd

# Cross-sectional "funding momentum": long the 2 contracts with the highest trailing 3-day mean funding,
# short the 2 with the lowest, flat the middle 2. Rebalanced once per day (close of the 20:00 UTC bar).
# LABEL: NO ROBUST EDGE FOUND -- this is the most defensible simple rule from a failed search, see log.

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
LOOKBACK = 18      # bars = 3 days of funding
N_SIDE = 2         # long top-2, short bottom-2
REBAL_HOUR = 20    # rebalance once a day, at the close of the 20:00 UTC bar


def targets(df):
    f = df.pivot(index="ts", columns="ticker", values="funding").sort_index()
    f = f.reindex(columns=TICKERS)
    score = f.rolling(LOOKBACK, min_periods=LOOKBACK).mean()
    rank = score.rank(axis=1, method="first")
    W = pd.DataFrame(0.0, index=score.index, columns=TICKERS)
    W[rank > len(TICKERS) - N_SIDE] = 1.0
    W[rank <= N_SIDE] = -1.0
    W[score.isna().any(axis=1)] = 0.0
    is_rebal = pd.Series(score.index.hour == REBAL_HOUR, index=score.index)
    W = W.where(is_rebal, np.nan).ffill().fillna(0.0)
    return W.clip(-2, 2).astype(float)
