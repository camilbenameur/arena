"""F1 (persistent taker buying pressure) written to the stream contract.

r = taker_buy_base / volume (1-day bar), simple mean over L days; a pair is rankable only if its last L
days are all valid (listed, volume > 0). Every H days (stream sequence number, no date),
the k pairs with the highest smoothed r get 1/k; weights are kept between two rebuilds.
The day rank is counted by the strategy (`Day.i` is shifted by a random integer by the engine). Ties are broken
by index order (alphabetical order in the original; indistinguishable except on exact ties, which
anonymous columns cannot define any other way).
"""
import numpy as np


class Strategy:
    def __init__(self, n_pairs, L=20, k=3, H=10):
        self.n = n_pairs
        self.L = L
        self.k = k
        self.H = H
        self.hist = np.full((L, n_pairs), np.nan)
        self.weight = np.zeros(n_pairs)
        self.rank = -1

    def step(self, day):
        v = day.spot_1d[:, 4]
        tb = day.spot_1d[:, 5]
        valid = day.eligibles & (v > 0)
        r = np.where(valid, tb / np.where(v > 0, v, 1.0), np.nan)
        self.hist = np.vstack([self.hist[1:], r[None, :]])
        self.rank += 1
        if self.rank % self.H == 0:
            rbar = self.hist.mean(axis=0)  # NaN if any of the L days is invalid
            ok = np.isfinite(rbar)
            order = np.lexsort((np.arange(self.n), -np.where(ok, rbar, 0.0)))
            self.weight = np.zeros(self.n)
            n_taken = 0
            for j in order:
                if ok[j] and n_taken < self.k:
                    self.weight[j] = 1.0 / self.k
                    n_taken += 1
        return self.weight.copy(), np.zeros(self.n)
