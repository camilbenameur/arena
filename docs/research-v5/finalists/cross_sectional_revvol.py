"""cross-sectional: reversal 240h (daily rebalance) + low-vol-minus-high-vol 168h (weekly), market-neutral, gross 2x each leg set,
emits every hour; relies on the bench's 0.05 rebalance band. WEAK / fragile: see report."""
import numpy as np
import pandas as pd
from arena.perp.lab.backtest import Data  # noqa: F401

STOP_PCT = None
LEV, REV_WIN, REV_HOLD, VOL_WIN, VOL_HOLD, DEAD = 2.0, 240, 24, 168, 168, 0.0


def _sched(sig, hold):
    H, k = sig.shape
    w = np.zeros((H, k)); cur = np.zeros(k)
    for h in range(H):
        if h % hold == 0 and not np.isnan(sig[h]).any():
            s = sig[h] - sig[h].mean(); g = np.abs(s).sum()
            cur = s / g if g > 0 else np.zeros(k)
        w[h] = cur
    return w


def targets(d):
    n, k = d.close.shape; H = n // 60
    c = d.close[:H * 60].reshape(H, 60, k)[:, -1]
    lc = np.log(c); lr = np.diff(lc, axis=0, prepend=np.nan)
    tot = _sched(-pd.DataFrame(lc).diff(REV_WIN).values, REV_HOLD) + _sched(-pd.DataFrame(lr).rolling(VOL_WIN).std().values, VOL_HOLD)
    tot = tot * LEV
    t = np.full((n, k), np.nan); last = np.zeros(k)
    for h in range(H):
        ch = np.abs(tot[h] - last) >= 0
        if ch.any():
            row = np.full(k, np.nan); row[ch] = tot[h][ch]; last = np.where(ch, tot[h], last)
            t[h * 60 + 59] = row
    return t
