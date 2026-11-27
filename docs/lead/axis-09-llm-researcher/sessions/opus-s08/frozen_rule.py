import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
WEIGHT = 1.0  # constant long exposure per contract (units of equity/6): equal-weight basket at 1x


def targets(df):
    """NO ROBUST EDGE FOUND. Fallback: hold the equal-weight long basket at 1x.
    This is plain market beta, not alpha. Causal by construction because it uses no data values."""
    ts = pd.Index(sorted(pd.unique(df["ts"])), name="ts")
    W = pd.DataFrame(WEIGHT, index=ts, columns=TICKERS, dtype=float)
    return W.clip(-2.0, 2.0).fillna(0.0)
