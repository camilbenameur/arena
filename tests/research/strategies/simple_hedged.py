"""Hedged class: long spot and short perp (same notional) on the first `k` listed columns."""
import numpy as np


class Strategy:
    def __init__(self, n_pairs, size=0.25, k=2):
        self.n = n_pairs
        self.size = size
        self.k = k

    def step(self, day):
        ok = day.eligibles & day.eligibles_perp
        ws = np.zeros(self.n)
        taken = 0
        for j in range(self.n):
            if ok[j] and taken < self.k:
                ws[j] = self.size
                taken += 1
        return ws, ws.copy()
