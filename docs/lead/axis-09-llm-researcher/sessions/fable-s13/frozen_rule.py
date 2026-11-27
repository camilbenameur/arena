import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]

# Parameters (set from the economics, not searched):
SPAN = 120        # EMA span in 4h bars = 20 days: slow trend, few decisions
BAND = 0.03       # hysteresis around the EMA, about one daily sigma of an alt: a flip must pay for 24 bp
VOL_WIN = 120     # 20 days of 4h returns for the volatility estimate
VOL_TGT = 0.30    # annualised volatility target per contract (deliberately small: no confirmed edge)
W_MIN, W_MAX = 0.20, 2.0   # floor keeps a sign flip (2*w) above the 0.3 re-trade threshold
BARS_PER_YEAR = 6 * 365


def _wide(df, col):
    d = df.drop_duplicates(["ts", "ticker"], keep="last")
    w = d.pivot(index="ts", columns="ticker", values=col).sort_index()
    return w.reindex(columns=TICKERS)


def targets(df):
    """Slow trend with hysteresis, inverse-volatility sized, long/short. Strictly causal:
    row t uses only bars with ts <= t (recursive EMA, trailing windows, forward-filled state)."""
    close = _wide(df, "close").astype(float).ffill()
    ema = close.ewm(span=SPAN, adjust=False).mean()

    up = close > ema * (1.0 + BAND)
    dn = close < ema * (1.0 - BAND)
    state = pd.DataFrame(np.where(up, 1.0, np.where(dn, -1.0, np.nan)),
                         index=close.index, columns=TICKERS)
    # warm-up: need SPAN valid closes per ticker before the EMA is trusted
    n_obs = close.notna().cumsum()
    state = state.where(n_obs > SPAN)
    state = state.ffill().fillna(0.0)          # inside the band: keep the previous side

    vol = np.log(close).diff().rolling(VOL_WIN, min_periods=VOL_WIN).std() * np.sqrt(BARS_PER_YEAR)
    size = (VOL_TGT / vol).clip(lower=W_MIN, upper=W_MAX)
    size = size.where(vol > 0).fillna(0.0)     # no volatility estimate yet -> flat

    w = (state * size).clip(-2.0, 2.0).fillna(0.0)
    w.index.name = "ts"
    return w[TICKERS]
