"""Frozen rule: per-coin slow trend filter, long or flat, decided once a day.

Label: NO ROBUST EDGE FOUND. This is a low-turnover, long-or-flat risk filter, not an alpha.
For each contract: hold +1.0 (equity/6, i.e. unlevered) when the last close is above the simple
average of the last 120 four-hour closes (20 days), otherwise 0. The decision is refreshed only
at the bar that closes at 00:00 UTC (bar open time 20:00) and held in between.
Causal: row t uses only bars with ts <= t (trailing windows, no full-sample statistics).
"""
import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
LOOKBACK = 120      # 4-hour bars = 20 days
DECISION_HOUR = 20  # bar opening 20:00 UTC closes at 00:00 UTC
SIZE = 1.0          # weight when in trend (multiple of equity/6)


def targets(df):
    d = df[["ts", "ticker", "close"]].copy()
    d["ts"] = pd.to_datetime(d["ts"])
    close = d.pivot_table(index="ts", columns="ticker", values="close", aggfunc="last")
    close = close.sort_index().reindex(columns=TICKERS)
    sma = close.rolling(LOOKBACK, min_periods=LOOKBACK).mean()
    signal = (close > sma).astype(float) * SIZE          # NaN comparisons are False -> 0 in warm-up
    is_decision = pd.Series(close.index.hour == DECISION_HOUR, index=close.index)
    w = signal.where(is_decision, axis=0).ffill().fillna(0.0)
    w = w.clip(-2.0, 2.0).astype(float)
    w.index.name = "ts"
    w.columns.name = None
    return w
