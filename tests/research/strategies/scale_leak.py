"""Depends on the absolute price level: violates scale invariance (C9)."""
import numpy as np


class Strategy:
    def __init__(self, n_pairs):
        self.n = n_pairs

    def step(self, day):
        c = np.where(day.eligibles, day.spot_1d[:, 3], -1.0)
        w = np.zeros(self.n)
        w[int(np.argmax(c))] = 1.0
        return w, np.zeros(self.n)
