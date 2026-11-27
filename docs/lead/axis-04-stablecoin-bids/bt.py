"""Axis 04 backtest engine (tick tape, conservative fill model). See PREREGISTRATION.md."""
import json, collections
from pathlib import Path
import numpy as np

D = Path("~/dev/_arena-data/axis-04/raw").expanduser()
PAIR = "USDGUSD"
SIZE_EUR, MAKER, TAKER, SLIP = 250.0, 0.0, 0.0001, 0.0001
WICK, HARD, SELL_BP = 0.952, 0.97, 5
DESIGN_END = 1775001600.0  # 2026-04-01T00:00:00Z

def load():
    T = []
    for line in (D / f"trades_{PAIR}.jsonl").read_text().splitlines():
        T += json.loads(line)["t"]
    a = np.array(T); a = a[np.argsort(a[:, 2], kind="stable")]
    # drop duplicates from overlapping pages
    k = np.unique(a[:, [0, 1, 2]], axis=0); k = k[np.argsort(k[:, 2], kind="stable")]
    return k[:, 2], k[:, 0], k[:, 1]  # t, price, volume

def eurusd():
    rows = json.loads((D / "ohlc1440_EURUSD.json").read_text())
    return np.array([r[0] for r in rows], float), np.array([float(r[4]) for r in rows])

def find_fill(t, p, v, i0, t_from, mask, size, win=3600.0):
    """First index >= i0 (trades at time >= t_from, mask True) where a 1 h window of masked trades holds
    >= 3x size volume, >= 3 prints, no print > 50% of the cumulative. Returns index or None."""
    idx = np.nonzero(mask[i0:])[0] + i0
    idx = idx[t[idx] >= t_from]
    dq = collections.deque(); cum = 0.0
    for j in idx:
        dq.append(j); cum += v[j]
        while t[j] - t[dq[0]] > win: cum -= v[dq.popleft()]
        if cum >= 3 * size and len(dq) >= 3 and max(v[k] for k in dq) <= 0.5 * cum: return j
    return None

def hard_exit(t, p, i0, i1):
    """First index in [i0,i1) starting a >=1 h stretch where all trades are < HARD; returns index of last trade of the stretch."""
    low = np.nonzero(p[i0:i1] < HARD)[0] + i0
    for a in low:
        j = np.searchsorted(t, t[a] + 3600.0)
        if j > a + 0 and np.all(p[a:j] < HARD) and (j < len(t) or t[-1] >= t[a] + 3600.0):
            return j - 1
    return None

def run(t, p, v, level_bp, cap_days, start, end, ez, ed, mvw):
    bid = 1.0 - level_bp / 1e4; ask = 1.0 - SELL_BP / 1e4
    fills, cur = [], start
    okp = p > WICK
    while True:
        i0 = int(np.searchsorted(t, cur))
        if i0 >= len(t) or t[i0] >= end: break
        px = np.interp(cur, ez, ed); size = SIZE_EUR * px
        ie = find_fill(t, p, v, i0, cur + 1.0, (p <= bid) & okp, size)
        if ie is None or t[ie] >= end: break
        te = t[ie] + 1.0; cap_t = te + cap_days * 86400.0
        j0 = int(np.searchsorted(t, te)); j1 = int(np.searchsorted(t, cap_t))
        isz = SIZE_EUR * np.interp(te, ez, ed)
        # sell limit (mirrored model); consider only trades inside the holding window
        sub = np.zeros(len(t), bool); sub[j0:j1] = (p[j0:j1] >= ask) & okp[j0:j1]
        is_ = find_fill(t, p, v, j0, te + 1.0, sub, isz)
        ih = hard_exit(t, p, j0, j1)
        cand = []
        if is_ is not None: cand.append((t[is_], "target", ask, MAKER))
        if ih is not None: cand.append((t[ih], "hard", p[ih] - SLIP, TAKER))
        if cand and min(cand)[0] < cap_t: tx, why, xp, fee = min(cand)
        else:
            k = min(j1, len(t) - 1); tx, why, xp, fee = t[k], "cap", p[k] - SLIP, TAKER
        # a position still open at 'end' is closed at the cap rule anyway (mark at last tick before end)
        qty = isz / bid
        net_usd = qty * xp * (1 - fee) - isz * (1 + MAKER)
        net_eur = net_usd / np.interp(tx, ez, ed)
        a, b = int(np.searchsorted(mvw[0], te)), int(np.searchsorted(mvw[0], te + 10 * 86400.0))
        rec = bool(np.any(mvw[1][a:b] >= 0.999))
        fills.append(dict(t_fill=float(te), t_exit=float(tx), exit=why, entry=bid, exit_px=float(xp),
                          net_eur=float(net_eur), recovered=rec, worst_low=float(p[ie:np.searchsorted(t, tx)].min())))
        cur = tx + 1.0
    return fills

def minute_vwap(t, p, v):
    m = (t // 60).astype(np.int64); u, inv = np.unique(m, return_inverse=True)
    pv = np.bincount(inv, p * v); vv = np.bincount(inv, v)
    return u * 60.0 + 30.0, pv / vv

def summarize(f):
    n = len(f); net = [x["net_eur"] for x in f]
    gains = [x for x in net if x > 0]
    return dict(fills=n, net_eur=round(sum(net), 4), recovered_pct=round(100 * np.mean([x["recovered"] for x in f]), 1) if n else None,
                worst_eur=round(min(net), 4) if n else None, avg_gain_eur=round(float(np.mean(gains)), 4) if gains else None,
                exits={k: sum(1 for x in f if x["exit"] == k) for k in ("target", "cap", "hard")})
