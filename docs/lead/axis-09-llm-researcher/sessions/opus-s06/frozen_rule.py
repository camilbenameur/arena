import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
SMA_BARS = 120          # 20 days of 4-hour bars
DECISION_HOUR = 20      # the bar that opens at 20:00 UTC closes at 00:00 UTC: one decision per day


def targets(df):
    """Long/flat trend filter per contract: hold 1.0 (equity/6) when the 4h close is above its
    trailing 20-day simple mean, else 0. Re-evaluated once per day (bar close at 00:00 UTC),
    held in between. Fully causal: trailing rolling mean + forward fill only."""
    d = df[["ts", "ticker", "close"]].copy()
    d["ts"] = pd.to_datetime(d["ts"])
    close = d.pivot_table(index="ts", columns="ticker", values="close", aggfunc="last").sort_index()
    close = close.reindex(columns=TICKERS)
    sma = close.rolling(SMA_BARS, min_periods=SMA_BARS).mean()
    sig = (close > sma).astype(float)
    sig[sma.isna() | close.isna()] = 0.0
    is_decision = pd.Series(close.index.hour == DECISION_HOUR, index=close.index)
    W = sig.where(is_decision, np.nan).ffill().fillna(0.0)
    W = W.clip(-2.0, 2.0).astype(float)
    W.index.name = "ts"
    return W[TICKERS]
