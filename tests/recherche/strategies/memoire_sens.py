"""Stratégie causale légitime à état (momentum 5 jours, rééquilibrage chaque jour) pour les tests de troncature."""
import numpy as np


class Strategie:
    def __init__(self, n_paires, L=5, k=3):
        self.n = n_paires
        self.L = L
        self.k = k
        self.cl = []

    def pas(self, jour):
        c = np.where(jour.eligibles, jour.spot_1d[:, 3], np.nan)
        self.cl.append(c)
        w = np.zeros(self.n)
        if len(self.cl) > self.L:
            mom = c / self.cl[-1 - self.L] - 1.0
            mom = np.where(np.isfinite(mom), mom, -np.inf)
            for j in np.argsort(-mom)[: self.k]:
                if np.isfinite(mom[j]):
                    w[j] = 1.0 / self.k
        return w, np.zeros(self.n)
