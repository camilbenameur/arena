"""Constant 1/n weights on all pairs, the reference basket."""
import numpy as np


class Strategy:
    def __init__(self, n_pairs, part=1.0):
        self.n = n_pairs
        self.part = part

    def step(self, day):
        w = np.full(self.n, self.part / self.n)
        return w, np.zeros(self.n)
