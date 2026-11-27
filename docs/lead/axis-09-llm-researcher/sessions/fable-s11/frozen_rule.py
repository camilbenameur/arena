"""Frozen rule: slow time-series trend, EMA(18) vs EMA(90) on 4-hour closes, long/short per contract,
inverse-volatility sized. Labelled "no robust edge found" in the trial log: see the log for caveats.
Causal: uses only recursive exponential averages of past and current closes; no full-sample statistics."""
import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
FAST = 18        # 3 days of 4-hour bars
SLOW = 90        # 15 days of 4-hour bars
VOL_REF = 0.01   # a contract with 1% volatility per 4-hour bar gets weight 1
W_MAX = 2.0


def targets(df):
    d = df[["ts", "ticker", "close"]].copy()
    d["ts"] = pd.to_datetime(d["ts"])
    close = d.pivot_table(index="ts", columns="ticker", values="close", aggfunc="last").sort_index()
    close = close.reindex(columns=TICKERS).astype(float).ffill()

    fast = close.ewm(span=FAST, adjust=False).mean()
    slow = close.ewm(span=SLOW, adjust=False).mean()
    sign = np.sign(fast - slow)

    ret = close.pct_change()
    vol = ret.ewm(span=SLOW, adjust=False).std()
    size = (VOL_REF / vol).clip(upper=W_MAX)

    w = sign * size
    w = w.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    w.iloc[:SLOW] = 0.0                      # warm-up: flat for the first SLOW bars
    w = w.clip(lower=-W_MAX, upper=W_MAX)
    w.columns.name = None
    return w[TICKERS]
