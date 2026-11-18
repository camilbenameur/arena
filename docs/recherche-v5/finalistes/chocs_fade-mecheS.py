"""Famille chocs : retour apres une meche extreme (liquidation en cascade). Frozen."""
import numpy as np

THR = 0.045      # mouvement log > 4,5 % sur 5, 15 ou 30 minutes
HOLD = 60        # minutes
WEIGHT = 2.0     # levier par contrat
LOCK = 60        # minutes sans reentree apres la sortie
STOP_PCT = 0.05


def targets(d):
    close = d.close
    n, k = close.shape
    ev = np.zeros((n, k), dtype=int)
    for w in (5, 15, 30):
        r = np.full((n, k), np.nan)
        r[w:] = np.log(close[w:] / close[:-w])
        ev = np.where(r < -THR, 1, np.where(r > THR, -1, ev))   # on achete la chute, on vend la hausse
    until = np.full(k, -1)
    lock = np.full(k, -1)
    out = np.full((n, k), np.nan)
    cur = np.zeros(k)
    for i in range(n):
        new = cur.copy()
        for j in range(k):
            if cur[j] != 0 and i >= until[j]:
                new[j] = 0.0
            if new[j] == 0 and ev[i, j] != 0 and i >= lock[j]:
                new[j] = ev[i, j] * WEIGHT
                until[j] = i + HOLD
                lock[j] = i + HOLD + LOCK
        if not np.array_equal(new, cur):
            out[i] = new
            cur = new
    return out
