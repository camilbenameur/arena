import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
LOOKBACKS = (60, 120, 180)   # 10, 20, 30 days of 4h bars
VOL_WIN = 42                 # 7 days of 4h bars
TARGET_DAILY_VOL = 0.02      # per-contract risk budget (2% daily vol per 1/6 slot)
DECISION_HOUR = 20           # bar opening 20:00 UTC closes 00:00 UTC -> one decision per day


def targets(df):
    close = df.pivot(index="ts", columns="ticker", values="close").sort_index()
    close = close.reindex(columns=TICKERS)
    logp = np.log(close)
    # multi-horizon time-series trend: average of signs of 10d/20d/30d log returns (trailing only)
    sig = sum(np.sign(logp - logp.shift(L)) for L in LOOKBACKS) / len(LOOKBACKS)
    # inverse-volatility sizing from trailing 7-day realised vol, capped at 1
    vol = close.pct_change().rolling(VOL_WIN).std() * np.sqrt(6)
    size = (TARGET_DAILY_VOL / vol).clip(upper=1.0)
    w = sig * size
    # decide once per day (close of the 20:00 UTC bar), hold in between: keeps turnover low
    is_dec = pd.Series(w.index.hour == DECISION_HOUR, index=w.index)
    w = w.where(is_dec, np.nan).ffill().fillna(0.0)
    w = w.clip(-2.0, 2.0).astype(float)
    w.index.name = "ts"
    return w[TICKERS]
