import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
LOOKBACKS = (60, 120, 180)   # 10, 20, 30 days of 4-hour bars; equal-weight ensemble, not tuned
DECISION_HOUR = 20           # re-decide once per day, on the bar opening 20:00 UTC (closes 00:00 UTC)


def targets(df):
    d = df.copy()
    d["ts"] = pd.to_datetime(d["ts"])
    close = d.pivot_table(index="ts", columns="ticker", values="close", aggfunc="last")
    close = close.reindex(columns=TICKERS).sort_index()
    sig = None
    for n in LOOKBACKS:
        s = np.sign(close / close.shift(n) - 1.0).fillna(0.0)
        sig = s if sig is None else sig + s
    sig = sig / float(len(LOOKBACKS))
    is_dec = pd.Series(sig.index.hour == DECISION_HOUR, index=sig.index)
    W = sig.where(is_dec, np.nan).ffill().fillna(0.0)
    W = W.clip(-2.0, 2.0).astype(float)
    W.index.name = "ts"
    return W[TICKERS]
