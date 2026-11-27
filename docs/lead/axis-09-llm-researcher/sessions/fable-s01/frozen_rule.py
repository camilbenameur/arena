import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
VOL_BARS = 84      # 14 days of 4-hour bars: trailing window for realised volatility
N_SIDE = 2         # long the 2 least volatile contracts, short the 2 most volatile
W_CAP = 2.0        # weight cap (units of equity/6)


def _trailing_std(x, n):
    """Trailing sample std over exactly n observations, computed window by window
    (no running sums), so the value at row t depends only on rows t-n+1..t."""
    out = np.full(x.shape, np.nan)
    for i in range(n - 1, x.shape[0]):
        w = x[i - n + 1:i + 1]
        if np.isfinite(w).all():
            out[i] = w.std(ddof=1)
    return out


def targets(df):
    d = df[["ts", "ticker", "close"]].copy()
    d["ts"] = pd.to_datetime(d["ts"])
    close = d.pivot_table(index="ts", columns="ticker", values="close", aggfunc="last")
    close = close.reindex(columns=TICKERS).sort_index()
    idx = close.index
    ret = close.to_numpy(float)
    ret = np.vstack([np.full((1, len(TICKERS)), np.nan), ret[1:] / ret[:-1] - 1.0])

    vol = np.column_stack([_trailing_std(ret[:, j], VOL_BARS) for j in range(len(TICKERS))])

    # weekly decision bar: the bar that closes at Monday 00:00 UTC (opens Sunday 20:00)
    rebalance = (idx.hour == 20) & (idx.dayofweek == 6)

    W = np.zeros((len(idx), len(TICKERS)))
    cur = np.zeros(len(TICKERS))
    for i in range(len(idx)):
        v = vol[i]
        if rebalance[i] and np.isfinite(v).all() and (v > 0).all():
            order = np.argsort(v, kind="stable")           # ascending volatility
            size = np.minimum(np.median(v) / v, W_CAP)     # risk-weighted legs
            new = np.zeros(len(TICKERS))
            new[order[:N_SIDE]] = size[order[:N_SIDE]]     # long low volatility
            new[order[-N_SIDE:]] = -size[order[-N_SIDE:]]  # short high volatility
            cur = new
        W[i] = cur
    out = pd.DataFrame(W, index=idx, columns=TICKERS).fillna(0.0).clip(-W_CAP, W_CAP)
    out.index.name = "ts"
    return out
