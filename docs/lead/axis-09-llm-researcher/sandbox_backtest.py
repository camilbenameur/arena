"""Fast bar-level approximation of the evaluation bench, for use inside the sandbox on the design CSV.

Usage:  from sandbox_backtest import simulate;  r = simulate(df, W)
  df: the CSV as read by pd.read_csv(path, parse_dates=["ts"]);  W: DataFrame indexed by ts (one row per bar), columns
  BTC ETH SOL XRP LTC LINK, the target weight decided at the CLOSE of that bar (units of equity/6, in [-2, 2]).
Model: the target of bar t is filled at the close of bar t (the real bench fills at the next minute open, a close
approximation), then held through bar t+1. A contract trades only when its position moves by more than 5% of equity
(0.3 weight units) from the target, or when the target is exactly 0 and a position is open. Each side costs 12 bp
(7 bp fee + 5 bp slippage) of the traded notional. Funding of bar t+1 (column `funding`, paid by longs, received by
shorts) is applied to the position held through it. Equity compounds. Returned `turnover_x` is traded notional divided
by starting equity, as in the bench. This is an approximation: the final judge is a minute-level simulator you do not have.
"""

import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
COST = 12e-4
BAND = 0.05  # of equity


def _wide(df, col):
    return df.pivot(index="ts", columns="ticker", values=col)[TICKERS]


def simulate(df, W):
    close, fund = _wide(df, "close"), _wide(df, "funding")
    W = W.reindex(close.index)[TICKERS].fillna(0.0).to_numpy(float) / 6.0  # equity fractions
    ret = (close.shift(-1) / close - 1).to_numpy(float)
    f = fund.shift(-1).to_numpy(float)
    n, k = W.shape
    pos, eq, turn, curve = np.zeros(k), 1.0, 0.0, []
    for t in range(n - 1):
        for j in range(k):
            if abs(W[t, j] - pos[j]) > BAND or (W[t, j] == 0 and pos[j] != 0):
                d = abs(W[t, j] - pos[j])
                eq -= d * eq * COST
                turn += d * eq
                pos[j] = W[t, j]
        eq *= 1 + float(np.nansum(pos * (ret[t] - f[t])))
        curve.append(eq)
    c = np.array(curve) if curve else np.array([1.0])
    dd = float((c / np.maximum.accumulate(c) - 1).min())
    daily = c[5::6]
    d = np.diff(np.concatenate([[1.0], daily])) / np.concatenate([[1.0], daily[:-1]]) if len(daily) else np.array([0.0])
    sharpe = float(d.mean() / d.std() * np.sqrt(365)) if d.std() > 0 else 0.0
    return {"return_pct": round(100 * (c[-1] - 1), 2), "max_dd_pct": round(100 * dd, 2), "sharpe": round(sharpe, 2),
            "turnover_x": round(turn, 1)}
