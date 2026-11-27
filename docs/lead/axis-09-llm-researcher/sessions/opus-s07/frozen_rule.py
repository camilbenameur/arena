"""Frozen rule: equal-weight long basket at 1x.
NO ROBUST EDGE FOUND in the design period. This is the simplest risk-premium baseline, not an alpha claim."""
import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
WEIGHT = 1.0  # multiple of equity/6 per contract


def targets(df):
    ts = pd.Index(sorted(pd.to_datetime(df["ts"]).unique()), name="ts")
    W = pd.DataFrame(WEIGHT, index=ts, columns=TICKERS, dtype=float)
    # a ticker with no bar yet at time t is held flat (uses only rows with ts <= t)
    present = df.assign(ts=pd.to_datetime(df["ts"])).pivot_table(
        index="ts", columns="ticker", values="close", aggfunc="last")
    present = present.reindex(index=ts, columns=TICKERS).notna().cummax()
    W = W.where(present, 0.0)
    return W.clip(-2, 2).fillna(0.0)
