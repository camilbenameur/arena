import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
SPEEDS = ((15, 60), (20, 80), (30, 120))  # (fast, slow) EMA spans in 4-hour bars; equal-weight ensemble, no speed is picked
VOL_SPAN = 60        # 10 days of 4-hour bars for the volatility estimate
TARGET_BAR_VOL = 0.01  # per-contract risk target: 1% per 4-hour bar at full conviction
MAX_W = 2.0


def _wide(df, col):
    w = df.pivot_table(index="ts", columns="ticker", values=col, aggfunc="last").sort_index()
    return w.reindex(columns=TICKERS)


def targets(df):
    """Slow time-series trend, three-speed ensemble, volatility-scaled, long/short.
    Row t uses only bars with ts <= t (recursive EMAs started at the first row, no look-ahead)."""
    close = _wide(df, "close").ffill()
    ret = close.pct_change()
    vol = ret.ewm(span=VOL_SPAN, adjust=False, min_periods=VOL_SPAN // 2).std()
    size = (TARGET_BAR_VOL / vol).clip(lower=0.0, upper=MAX_W)

    direction = pd.DataFrame(0.0, index=close.index, columns=TICKERS)
    for fast, slow in SPEEDS:
        ef = close.ewm(span=fast, adjust=False).mean()
        es = close.ewm(span=slow, adjust=False).mean()
        d = np.sign(ef - es)
        d.iloc[:slow] = 0.0  # warm-up of this speed
        direction = direction + d.fillna(0.0)
    direction = direction / float(len(SPEEDS))

    w = (direction * size).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    w = w.clip(lower=-MAX_W, upper=MAX_W).astype(float)
    w.index.name = "ts"
    w.columns.name = None
    return w[TICKERS]
