import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
LOOKBACK = 84           # 14 days of 4h bars: horizon of the market-momentum signal
Z_ON, Z_OFF = 0.5, -0.5  # hysteresis thresholds on the z-scored 14d basket return
VOL_SPAN = 42           # 7 days EWMA for volatility
TARGET_VOL = 0.50       # annualised volatility target per contract (about 1x basket when ON)
BARS_PER_YEAR = 2190.0  # 6 bars per day * 365


def targets(df):
    """Long/flat market-trend rule with volatility targeting. NO ROBUST EDGE FOUND: this is risk-managed beta.

    Row t uses only bars with ts <= t (backward rolling/EWM windows and a forward-running state machine).
    """
    d = df.drop_duplicates(["ts", "ticker"], keep="last")
    close = d.pivot(index="ts", columns="ticker", values="close").sort_index()
    close = close.reindex(columns=TICKERS).ffill()
    r = np.log(close).diff()

    # Market factor: equal-weight mean of the contracts' 4h log returns
    mkt = r.mean(axis=1, skipna=True).fillna(0.0)
    mom = mkt.rolling(LOOKBACK, min_periods=LOOKBACK).sum()
    sig = mkt.ewm(span=VOL_SPAN, adjust=False, min_periods=VOL_SPAN).std() * np.sqrt(LOOKBACK)
    z = (mom / sig).to_numpy(float)

    # Hysteresis state: ON above +0.5 sigma, OFF below -0.5 sigma, otherwise keep the previous state
    state = np.zeros(len(z))
    on = 0.0
    for i in range(len(z)):
        if np.isfinite(z[i]):
            if z[i] > Z_ON:
                on = 1.0
            elif z[i] < Z_OFF:
                on = 0.0
        state[i] = on

    # Per-contract volatility targeting (causal EWMA), weights capped to [0, 2]
    vol = r.ewm(span=VOL_SPAN, adjust=False, min_periods=VOL_SPAN).std() * np.sqrt(BARS_PER_YEAR)
    unit = (TARGET_VOL / vol).replace([np.inf, -np.inf], np.nan).clip(lower=0.0, upper=2.0).fillna(0.0)

    W = unit.mul(pd.Series(state, index=close.index), axis=0)
    W = W.fillna(0.0).clip(-2.0, 2.0)
    W.index.name = "ts"
    return W[TICKERS]
