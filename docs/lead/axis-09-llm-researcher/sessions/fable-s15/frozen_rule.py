import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]

EMA_SPAN = 60      # 10 days of 4h bars: trend reference
VOL_SPAN = 90      # 15 days of 4h bars: volatility estimate
VOL_MINP = 30
BAND_K = 0.5       # hysteresis half-width, in daily sigmas, around the EMA
TARGET_BAR_VOL = 0.01   # per-contract 4h volatility target at weight 1
MAX_W = 2.0


def targets(df):
    """Long-only trend filter with hysteresis, inverse-volatility sized.

    Per contract: go long when the close is more than BAND_K daily sigmas above
    its 60-bar EMA, go flat when it is more than BAND_K daily sigmas below it,
    otherwise keep the previous state. Size = TARGET_BAR_VOL / trailing vol,
    capped at 2. Only data with ts <= t is used for row t.
    """
    d = df[["ts", "ticker", "close"]].copy()
    d["ts"] = pd.to_datetime(d["ts"])
    close = d.pivot_table(index="ts", columns="ticker", values="close", aggfunc="last").sort_index()
    close = close.reindex(columns=TICKERS)

    ret = close / close.shift(1) - 1.0
    vol = ret.ewm(span=VOL_SPAN, min_periods=VOL_MINP).std()
    ema = close.ewm(span=EMA_SPAN, min_periods=EMA_SPAN).mean()
    day_vol = vol * np.sqrt(6.0)
    upper = ema * (1.0 + BAND_K * day_vol)
    lower = ema * (1.0 - BAND_K * day_vol)

    state = pd.DataFrame(0.0, index=close.index, columns=TICKERS)
    for tk in TICKERS:
        s = 0.0
        out = np.zeros(len(close))
        cv, uv, lv = close[tk].to_numpy(float), upper[tk].to_numpy(float), lower[tk].to_numpy(float)
        for i in range(len(cv)):
            if not (np.isnan(cv[i]) or np.isnan(uv[i]) or np.isnan(lv[i])):
                if cv[i] > uv[i]:
                    s = 1.0
                elif cv[i] < lv[i]:
                    s = 0.0
            out[i] = s
        state[tk] = out

    scale = (TARGET_BAR_VOL / vol).clip(upper=MAX_W)
    w = (state * scale).replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(0.0, MAX_W)
    w.index.name = "ts"
    w.columns.name = None
    return w[TICKERS].astype(float)
