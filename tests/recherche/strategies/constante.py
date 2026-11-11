"""Poids constants 1/n sur toutes les paires éligibles du jour (panier de référence)."""
import numpy as np


class Strategie:
    def __init__(self, n_paires, part=1.0):
        self.n = n_paires
        self.part = part

    def pas(self, jour):
        w = np.full(self.n, self.part / self.n)
        return w, np.zeros(self.n)
