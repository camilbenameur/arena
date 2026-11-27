import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
BETA_BARS = 90      # 15 days of 4-hour bars for the trailing beta estimate
BETA_FLOOR = 0.3    # floor on beta before inverting, keeps weights bounded


def _wide(df, col):
    w = df.pivot_table(index="ts", columns="ticker", values=col, aggfunc="last")
    return w.reindex(columns=TICKERS).sort_index()


def targets(df):
    """Betting-against-beta, beta-neutral by construction, rebalanced weekly.

    Trailing beta of each contract to the equal-weight basket (last 90 bars).
    Long the three lowest-beta contracts, short the three highest-beta ones,
    each sized 1/beta. Decisions are refreshed only on the Monday 00:00 UTC
    bar and held in between. Uses only rows with ts <= t.
    """
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"])
    close = _wide(df, "close").ffill()
    r = np.log(close).diff()
    m = r.mean(axis=1)
    beta = r.rolling(BETA_BARS).cov(m).div(m.rolling(BETA_BARS).var(), axis=0)
    rk = beta.rank(axis=1, method="first")
    side = (rk <= 3).astype(float) - (rk > 3).astype(float)
    W = side / beta.clip(lower=BETA_FLOOR)
    W[beta.isna().any(axis=1)] = 0.0
    W = W.clip(-2.0, 2.0)
    monday = pd.Series((W.index.hour == 0) & (W.index.dayofweek == 0), index=W.index)
    W = W.where(monday, np.nan).ffill().fillna(0.0)
    W = W.replace([np.inf, -np.inf], 0.0).clip(-2.0, 2.0)
    W.index.name = "ts"
    W.columns.name = None
    return W[TICKERS].astype(float)
