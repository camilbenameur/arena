"""Frozen rule: volume-weighted time-series momentum with hysteresis, volatility-scaled.
Label: NO ROBUST EDGE FOUND on the design period; this is the most defensible simple fallback.
Causal: every statistic is a trailing rolling / exponentially weighted quantity or a forward-running state machine.
"""
import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]

L_MOM = 42        # 7 days of 4h bars: momentum lookback
L_VOLUME = 126    # 21 days: baseline for relative volume
SPAN_VOL = 60     # 10 days: EWM span of the volatility estimate
BAND = 0.5        # hysteresis: flip only when the move exceeds 0.5 sigma of a 7-day move
TARGET_VOL = 0.30 # annualised volatility target per contract
BARS_PER_YEAR = 6 * 365


def _wide(df, col):
    d = df.drop_duplicates(subset=["ts", "ticker"], keep="last")
    w = d.pivot(index="ts", columns="ticker", values=col).sort_index()
    return w.reindex(columns=TICKERS).astype(float)


def _hysteresis(z, band):
    out = np.zeros(z.shape)
    for j in range(z.shape[1]):
        s = 0.0
        col = z[:, j]
        for i in range(col.shape[0]):
            v = col[i]
            if v == v:  # not NaN
                if v > band:
                    s = 1.0
                elif v < -band:
                    s = -1.0
            out[i, j] = s
    return out


def targets(df):
    close = _wide(df, "close")
    volume = _wide(df, "volume")
    lr = np.log(close.where(close > 0)).diff()
    vol_bar = lr.ewm(span=SPAN_VOL, min_periods=30).std()
    base = volume.rolling(L_VOLUME).mean()
    relvol = (volume / base.where(base > 0)).replace([np.inf, -np.inf], np.nan)
    x = lr * relvol
    z = x.rolling(L_MOM).sum() / (vol_bar.where(vol_bar > 0) * np.sqrt(L_MOM))
    z = z.replace([np.inf, -np.inf], np.nan)
    state = pd.DataFrame(_hysteresis(z.to_numpy(float), BAND), index=close.index, columns=TICKERS)
    scale = (TARGET_VOL / (vol_bar.where(vol_bar > 0) * np.sqrt(BARS_PER_YEAR))).clip(upper=2.0)
    w = (state * scale).replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(-2.0, 2.0)
    w.index.name = "ts"
    return w[TICKERS]
