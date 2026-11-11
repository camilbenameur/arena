"""Dépend du niveau absolu des prix : viole l'invariance d'échelle (C9)."""
import numpy as np


class Strategie:
    def __init__(self, n_paires):
        self.n = n_paires

    def pas(self, jour):
        c = np.where(jour.eligibles, jour.spot_1d[:, 3], -1.0)
        w = np.zeros(self.n)
        w[int(np.argmax(c))] = 1.0
        return w, np.zeros(self.n)
