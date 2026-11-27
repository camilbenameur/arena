import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
SMA_BARS = 120  # 20 days of 4-hour bars; set a priori (standard slow trend horizon), not optimised


def targets(df):
    """Long/flat slow time-series trend filter, per contract.
    Hold weight 1.0 (equity/6) in a contract while its 4h close is above its trailing 20-day simple
    moving average of closes; otherwise flat (0). Uses only rows with ts <= t. No shorting."""
    d = df.sort_values(["ts", "ticker"])
    close = d.pivot_table(index="ts", columns="ticker", values="close", aggfunc="last")
    close = close.reindex(columns=TICKERS).sort_index()
    sma = close.rolling(SMA_BARS, min_periods=SMA_BARS).mean()
    w = (close > sma).astype(float)
    w = w.where(sma.notna() & close.notna(), 0.0)
    w = w.fillna(0.0).clip(-2.0, 2.0)
    w.index.name = "ts"
    return w[TICKERS]
