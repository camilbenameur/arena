"""Cross-venue funding spread: perp vs perp (no spot). Short the perp on the venue paying more,
long on the other. Price PnL of the two legs cancels (same underlying; the small cross-venue
perp price gap is NOT modelled -- stated omission); PnL = spread x notional - fees.
Legs: 1x notional per venue => equity/2 per venue."""
import numpy as np
import pandas as pd
import carry
from strategies import ANN

PERP_FEE, SLIP = 0.0005, 0.0005
N_of = {}

def spread_frame(fa, fb, coins):
    """fa - fb on common 8h grid; positive => venue A pays more."""
    idx = fa.index.union(fb.index)
    A, B = fa.reindex(idx), fb.reindex(idx)
    return (A[coins] - B[coins])

def simulate(spread, start, end, w, enter, exit_, k, equity0=1000.0, fee=PERP_FEE, slip=SLIP):
    N_of.clear()
    sp = spread[(spread.index <= end)]
    tr = sp.rolling(w, min_periods=max(2, w // 2)).mean() * ANN
    a_tr, a_sp = tr.values, sp.values
    idx = sp.index
    dirn = np.zeros(a_tr.shape[1])  # +1: short A / long B ; -1 opposite
    E = equity0; eq, times = [], []
    held = {}; ntr = 0; ftot = 0.0; ctot = 0.0
    cost_side = 2 * (fee + slip)   # two perp legs
    pos = np.where((idx >= start) & (idx <= end))[0]
    for i in pos:
        # decision for the interval ending at idx[i] was taken from row i-2 (execute at start of interval i-1->i)
        if i < 2: continue
        row = a_tr[i - 2]
        ok = ~np.isnan(row)
        for j in list(held):
            if (not ok[j]) or (held[j] * row[j] < exit_):
                del held[j]; E -= cost_side * N_of[j]; ctot += cost_side * N_of[j]; ntr += 1
        order = np.argsort(-np.abs(np.where(ok, row, 0)))
        newj = []
        for j in order:
            if len(held) + len(newj) >= k: break
            if j in held or not ok[j]: continue
            if abs(row[j]) > enter:
                newj.append(j)
        for j in newj:
            N = E / (2 * k)
            N_of[j] = N; held[j] = np.sign(row[j]); E -= cost_side * N; ctot += cost_side * N; ntr += 1
        for j, s_ in held.items():
            v = a_sp[i, j]
            if not np.isnan(v):
                g = s_ * v * N_of[j]; E += g; ftot += g
        eq.append(E); times.append(idx[i])
    s = pd.Series(eq, index=times)
    yrs = max((times[-1] - times[0]).days / 365.25, 1e-9) if times else 1
    return s, dict(entries_exits=ntr, per_year=ntr / yrs, funding=ftot, costs=ctot)

