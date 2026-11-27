import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]

# Parameters fixed a priori from the economics, not searched:
N_BREAKOUT = 42      # 7 days of 4-hour bars: breakout look-back
VOL_SPAN = 60        # 10 days of 4-hour bars: EWMA span of the volatility estimate
VOL_MIN = 30         # bars needed before a volatility estimate is trusted
TARGET_DVOL = 0.025  # target daily volatility per contract (weight 1 ~ a contract with 2.5%/day vol)
W_MAX = 2.0


def targets(df):
    """Long/flat 7-day breakout per contract, volatility-scaled. Strictly causal:
    only trailing rolling windows, recursive EWMAs and forward-fills are used."""
    d = df[["ts", "ticker", "close"]].copy()
    d["ts"] = pd.to_datetime(d["ts"])
    c = d.pivot_table(index="ts", columns="ticker", values="close", aggfunc="last").sort_index()
    c = c.reindex(columns=TICKERS).astype(float)

    # trailing channel of the previous N closes (current bar excluded)
    hi = c.shift(1).rolling(N_BREAKOUT).max()
    lo = c.shift(1).rolling(N_BREAKOUT).min()
    raw = pd.DataFrame(np.where(c > hi, 1.0, np.where(c < lo, -1.0, np.nan)),
                       index=c.index, columns=c.columns)
    state = raw.ffill()                 # hold the last breakout direction; NaN before the first one
    long_state = state.clip(lower=0.0)  # +1 after an up-breakout, 0 after a down-breakout (flat, never short)

    # trailing EWMA daily volatility of 4-hour log returns (6 bars per day)
    r = np.log(c).diff()
    dvol = np.sqrt((r ** 2).ewm(span=VOL_SPAN, min_periods=VOL_MIN, adjust=False).mean()) * np.sqrt(6.0)
    scale = (TARGET_DVOL / dvol).clip(upper=W_MAX)

    w = (long_state * scale).replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(0.0, W_MAX)
    w.index.name = "ts"
    w.columns.name = None
    return w
