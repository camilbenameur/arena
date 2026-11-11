"""Dépend de l'ordre des colonnes : viole l'invariance par permutation (C9)."""
import numpy as np


class Strategie:
    def __init__(self, n_paires):
        self.n = n_paires

    def pas(self, jour):
        w = np.zeros(self.n)
        w[0] = 0.5 if jour.eligibles[0] else 0.0
        return w, np.zeros(self.n)
