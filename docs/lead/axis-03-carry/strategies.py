"""Trial specs and signal builders. A spec is a plain dict, logged as-is to trials.jsonl."""
import numpy as np
import pandas as pd
import carry

ANN = 3 * 365  # settlements per year (8h)

def sig_always(coins):
    def f(d):
        s = pd.DataFrame(False, index=d.idx, columns=d.coins)
        for c in coins:
            if c in s: s[c] = True
        return s
    return f

def sig_threshold(coins, w, enter, exit_, k):
    """Hysteresis: on when trailing mean funding (annualised) > enter, off when < exit_.
    Several coins: at most k on at once, best trailing funding first."""
    def f(d):
        tr = carry.trailing(d.fund[[c for c in coins if c in d.fund]], w) * ANN
        a = tr.values
        out = np.zeros(a.shape, dtype=bool)
        on = np.zeros(a.shape[1], dtype=bool)
        for i in range(a.shape[0]):
            row = a[i]
            ok = ~np.isnan(row)
            on = on & ok & (row > exit_)
            cand = np.where(ok & (row > enter) & ~on)[0]
            cand = cand[np.argsort(-row[cand])]
            for j in cand:
                if on.sum() < k: on[j] = True
            out[i] = on
        res = pd.DataFrame(False, index=d.idx, columns=d.coins)
        res[tr.columns] = out
        return res
    return f

def sig_rotate(coins, w, enter, k):
    """Top-k coins by trailing funding, must exceed `enter`; a held coin is kept while it stays
    above enter/2 and inside the top 2k (limits churn)."""
    def f(d):
        cs = [c for c in coins if c in d.fund]
        tr = carry.trailing(d.fund[cs], w) * ANN
        a = tr.values
        out = np.zeros(a.shape, dtype=bool)
        held = np.zeros(a.shape[1], dtype=bool)
        for i in range(a.shape[0]):
            row = a[i]; ok = ~np.isnan(row)
            r = np.where(ok, row, -9.0)
            order = np.argsort(-r)
            rank = np.empty_like(order); rank[order] = np.arange(len(order))
            held = held & ok & (row > enter / 2) & (rank < 2 * k)
            for j in order:
                if held.sum() >= k: break
                if ok[j] and row[j] > enter and not held[j]: held[j] = True
            out[i] = held
        res = pd.DataFrame(False, index=d.idx, columns=d.coins)
        res[tr.columns] = out
        return res
    return f

def build(spec):
    t = spec["type"]
    if t == "always": return sig_always(spec["coins"])
    if t == "thr": return sig_threshold(spec["coins"], spec["w"], spec["enter"], spec["exit"], spec["k"])
    if t == "rot": return sig_rotate(spec["coins"], spec["w"], spec["enter"], spec["k"])
    raise ValueError(t)

ALL = carry.COINS
DESIGN_TRIALS = [
 dict(id=1, type="always", coins=["BTC"], k=1),
 dict(id=2, type="always", coins=["ETH"], k=1),
 dict(id=3, type="always", coins=["BTC","ETH"], k=2),
 dict(id=4, type="thr", coins=["BTC"], w=21, enter=0.10, exit=0.05, k=1),
 dict(id=5, type="thr", coins=["BTC"], w=63, enter=0.10, exit=0.05, k=1),
 dict(id=6, type="thr", coins=["BTC"], w=9, enter=0.15, exit=0.05, k=1),
 dict(id=7, type="thr", coins=["BTC"], w=21, enter=0.20, exit=0.08, k=1),
 dict(id=8, type="thr", coins=["ETH"], w=21, enter=0.10, exit=0.05, k=1),
 dict(id=9, type="thr", coins=["BTC","ETH"], w=21, enter=0.10, exit=0.05, k=2),
 dict(id=10, type="rot", coins=ALL, w=21, enter=0.15, k=1),
 dict(id=11, type="rot", coins=ALL, w=21, enter=0.15, k=3),
 dict(id=12, type="rot", coins=ALL, w=21, enter=0.15, k=5),
 dict(id=13, type="rot", coins=ALL, w=63, enter=0.15, k=3),
 dict(id=14, type="rot", coins=ALL, w=21, enter=0.25, k=3),
 dict(id=15, type="rot", coins=ALL, w=21, enter=0.10, k=3),
 dict(id=16, type="rot", coins=ALL, w=63, enter=0.10, k=5),
# follow-up trials after the first 20 (always-on beats gating; try a kill-switch and slower rotation)
 dict(id=21, type="thr", coins=["BTC","ETH"], w=63, enter=0.03, exit=0.0, k=2),
 dict(id=22, type="thr", coins=["ETH"], w=63, enter=0.03, exit=0.0, k=1),
 dict(id=23, type="rot", coins=ALL, w=126, enter=0.08, k=3),
 dict(id=24, type="rot", coins=ALL, w=126, enter=0.08, k=5),
]
# cross-venue (perp vs perp, Bybit minus Binance funding): handled in xvenue.py
XV_TRIALS = [
 dict(id=17, type="xv", coins=["BTC"], w=21, enter=0.05, exit=0.02, k=1),
 dict(id=18, type="xv", coins=["ETH"], w=21, enter=0.05, exit=0.02, k=1),
 dict(id=19, type="xv", coins=["BTC","ETH","SOL","XRP","DOGE","LTC","LINK","ADA"], w=21, enter=0.05, exit=0.02, k=3),
 dict(id=20, type="xv", coins=["BTC"], w=63, enter=0.03, exit=0.01, k=1),
]
