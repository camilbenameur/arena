"""Depends on the column order: violates permutation invariance (C9)."""
import numpy as np


class Strategy:
    def __init__(self, n_pairs):
        self.n = n_pairs

    def step(self, day):
        w = np.zeros(self.n)
        w[0] = 0.5 if day.eligibles[0] and day.spot_1d[0, 3] > 1.0 else 0.0
        return w, np.zeros(self.n)
