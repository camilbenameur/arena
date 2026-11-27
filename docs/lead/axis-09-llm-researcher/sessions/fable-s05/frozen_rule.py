import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
FAST, SLOW = 30, 120      # 5 days / 20 days of 4-hour bars
WEIGHT = 1.0              # equity/6 per contract when the trend is up, else flat


def targets(df):
    d = df[["ts", "ticker", "close"]].copy()
    d["ts"] = pd.to_datetime(d["ts"])
    close = d.pivot_table(index="ts", columns="ticker", values="close", aggfunc="last").sort_index()
    close = close.reindex(columns=TICKERS).ffill()
    fast = close.ewm(span=FAST, adjust=False, min_periods=SLOW).mean()
    slow = close.ewm(span=SLOW, adjust=False, min_periods=SLOW).mean()
    w = (fast > slow).astype(float) * WEIGHT          # NaN during warm-up compares False -> 0
    w = w.where(close.notna(), 0.0).fillna(0.0).clip(-2.0, 2.0)
    w.index.name = "ts"
    w.columns.name = None
    return w[TICKERS]
