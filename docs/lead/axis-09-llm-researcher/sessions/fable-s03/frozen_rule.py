"""frozen_rule.py -- cross-sectional 7-day momentum, overlapping-tranche (J = K = 7 days), market neutral.
STATUS: NO ROBUST EDGE FOUND on the design period. Handed back as the pre-committed, most defensible simple rule.
Causal: row t uses only bars with ts <= t (backward shifts and backward cumulative sums only)."""
import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
LOOKBACK = 42   # bars = 7 days: formation window J
HOLD = 42       # bars = 7 days: holding window K (average of the last 7 daily snapshots)
N_SIDE = 2      # long the 2 strongest, short the 2 weakest
SIZE = 1.0      # weight units per full position (max gross = 4/6 of equity)


def targets(df):
    d = df[["ts", "ticker", "close"]].copy()
    d["ts"] = pd.to_datetime(d["ts"])
    close = d.pivot_table(index="ts", columns="ticker", values="close", aggfunc="last")
    close = close.reindex(columns=TICKERS).sort_index().astype(float)
    close = close.where(close > 0).ffill()                      # causal fill of any missing bar

    lc = np.log(close)
    mom = lc - lc.shift(LOOKBACK)                               # trailing 7-day log return
    valid = mom.notna().all(axis=1)

    rk_lo = mom.rank(axis=1, method="first", ascending=True)    # 1 = weakest
    rk_hi = mom.rank(axis=1, method="first", ascending=False)   # 1 = strongest
    snap = pd.DataFrame(0.0, index=close.index, columns=TICKERS)
    snap = snap.mask(rk_hi <= N_SIDE, 1.0).mask(rk_lo <= N_SIDE, -1.0)
    snap = snap.where(valid, 0.0)

    # one snapshot per day, taken at the bar that opens at 00:00 UTC, carried forward until the next one
    is_reb = pd.Series(close.index.hour == 0, index=close.index)
    held = snap.where(is_reb, np.nan).ffill().fillna(0.0)

    # overlapping tranches: mean of the held snapshot over the last HOLD bars (exact: sums of -1/0/+1)
    cs = held.cumsum()
    roll = (cs - cs.shift(HOLD).fillna(0.0)) / float(HOLD)

    w = (SIZE * roll).clip(-2.0, 2.0).fillna(0.0)
    w.index.name = "ts"
    w.columns.name = None
    return w[TICKERS]
