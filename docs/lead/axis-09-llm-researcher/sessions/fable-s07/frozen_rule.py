"""Frozen rule: capitulation rebound, long only, episodic.  Label: NO ROBUST EDGE FOUND (see trial log).

After a 4-hour bar that closes down by more than Z trailing standard deviations on more than VMULT times the
trailing median volume (a forced-selling / liquidation signature), hold that contract long at weight SIZE for
HOLD bars (2 days), otherwise stay flat. All statistics are trailing and exclude the current bar.
"""
import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
LOOKBACK = 42   # bars (7 days) for the trailing volatility and volume baselines
Z = 2.0         # down-move threshold in trailing standard deviations of 4h log returns
VMULT = 2.0     # volume threshold as a multiple of the trailing median bar volume
HOLD = 12       # bars to hold after a trigger (2 days)
SIZE = 1.0      # weight per triggered contract (units of equity/6); at most 1x equity gross if all six fire


def _wide(df, col):
    w = df.pivot_table(index="ts", columns="ticker", values=col, aggfunc="last").sort_index()
    return w.reindex(columns=TICKERS).astype(float)


def targets(df):
    close = _wide(df, "close")
    volume = _wide(df, "volume")
    ret = np.log(close).diff()
    sd = ret.shift(1).rolling(LOOKBACK).std()          # trailing, excludes the current bar
    med = volume.shift(1).rolling(LOOKBACK).median()   # trailing, excludes the current bar
    trig = ((ret < -Z * sd) & (volume > VMULT * med)).astype(float)   # NaN comparisons are False -> 0
    w = trig.rolling(HOLD, min_periods=1).max() * SIZE
    w = w.replace([np.inf, -np.inf], 0.0).fillna(0.0).clip(-2.0, 2.0)
    w.index.name = "ts"
    w.columns.name = None
    return w[TICKERS]
