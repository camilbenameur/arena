"""F1 du labo (pression d'achat taker persistante) réécrite au contrat du flux.

r = taker_buy_base / volume (barre 1 j), moyenne simple sur L jours ; la paire n'est classable que si les L
derniers jours sont tous valides (cotée, volume > 0). Tous les H jours (numéro d'ordre du flux, sans date),
les k paires de r lissé le plus haut reçoivent 1/k ; poids conservés entre deux reconstitutions.
Le rang du jour est compté par la stratégie (`Jour.i` est décalé d'un entier aléatoire par le moteur). Égalités :
ordre d'index (le labo : ordre alphabétique ; indiscernable hors égalité exacte, que les colonnes anonymes
ne permettent pas de définir autrement).
"""
import numpy as np


class Strategie:
    def __init__(self, n_paires, L=20, k=3, H=10):
        self.n = n_paires
        self.L = L
        self.k = k
        self.H = H
        self.hist = np.full((L, n_paires), np.nan)
        self.poids = np.zeros(n_paires)
        self.rang = -1

    def pas(self, jour):
        v = jour.spot_1d[:, 4]
        tb = jour.spot_1d[:, 5]
        valide = jour.eligibles & (v > 0)
        r = np.where(valide, tb / np.where(v > 0, v, 1.0), np.nan)
        self.hist = np.vstack([self.hist[1:], r[None, :]])
        self.rang += 1
        if self.rang % self.H == 0:
            rbar = self.hist.mean(axis=0)  # NaN si un des L jours est invalide
            ok = np.isfinite(rbar)
            ordre = np.lexsort((np.arange(self.n), -np.where(ok, rbar, 0.0)))
            self.poids = np.zeros(self.n)
            n_pris = 0
            for j in ordre:
                if ok[j] and n_pris < self.k:
                    self.poids[j] = 1.0 / self.k
                    n_pris += 1
        return self.poids.copy(), np.zeros(self.n)
