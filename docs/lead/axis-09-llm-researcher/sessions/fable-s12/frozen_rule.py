import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]

# Parameters fixed before testing, from the economics (not searched):
ENTRY_BARS = 60      # 10 days of 4h bars: breakout window (new 10-day closing high/low opens a position)
EXIT_BARS = 30       # 5 days: opposite half-length extreme closes the position (go flat)
VOL_BARS = 60        # 10 days: realised-volatility window
TARGET_VOL = 0.25    # annualised volatility targeted per contract (half size: no demonstrated edge)
BARS_PER_YEAR = 2190.0
MAX_W = 2.0


def targets(df):
    d = df[["ts", "ticker", "close"]].copy()
    d["ts"] = pd.to_datetime(d["ts"])
    close = d.pivot_table(index="ts", columns="ticker", values="close", aggfunc="last").sort_index()
    close = close.reindex(columns=TICKERS).ffill()          # causal fill of any gap
    ret = close.pct_change()
    prev = close.shift(1)                                    # channels exclude the current bar
    hi_in = prev.rolling(ENTRY_BARS).max()
    lo_in = prev.rolling(ENTRY_BARS).min()
    hi_out = prev.rolling(EXIT_BARS).max()
    lo_out = prev.rolling(EXIT_BARS).min()
    vol = ret.rolling(VOL_BARS).std() * np.sqrt(BARS_PER_YEAR)
    size = (TARGET_VOL / vol.where(vol > 0)).clip(lower=0.0, upper=MAX_W).fillna(0.0)

    n = len(close)
    W = pd.DataFrame(0.0, index=close.index, columns=TICKERS)
    for j in TICKERS:
        c = close[j].to_numpy(float)
        h, l = hi_in[j].to_numpy(float), lo_in[j].to_numpy(float)
        xh, xl = hi_out[j].to_numpy(float), lo_out[j].to_numpy(float)
        out = np.zeros(n)
        state = 0
        for i in range(n):
            if np.isnan(h[i]) or np.isnan(c[i]):
                out[i] = state if not np.isnan(c[i]) else 0.0
                continue
            if state == 1 and c[i] <= xl[i]:
                state = 0
            if state == -1 and c[i] >= xh[i]:
                state = 0
            if c[i] >= h[i]:
                state = 1
            elif c[i] <= l[i]:
                state = -1
            out[i] = state
        W[j] = out * size[j].to_numpy(float)
    W = W.replace([np.inf, -np.inf], 0.0).fillna(0.0).clip(lower=-MAX_W, upper=MAX_W)
    W.index.name = "ts"
    return W
