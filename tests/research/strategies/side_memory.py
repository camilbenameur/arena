"""Legitimate stateful causal strategy (5-day momentum, rebalanced every day) for the truncation tests."""
import numpy as np


class Strategy:
    def __init__(self, n_pairs, L=5, k=3):
        self.n = n_pairs
        self.L = L
        self.k = k
        self.cl = []

    def step(self, day):
        c = np.where(day.eligibles, day.spot_1d[:, 3], np.nan)
        self.cl.append(c)
        w = np.zeros(self.n)
        if len(self.cl) > self.L:
            mom = c / self.cl[-1 - self.L] - 1.0
            mom = np.where(np.isfinite(mom), mom, -np.inf)
            for j in np.argsort(-mom)[: self.k]:
                if np.isfinite(mom[j]):
                    w[j] = 1.0 / self.k
        return w, np.zeros(self.n)
