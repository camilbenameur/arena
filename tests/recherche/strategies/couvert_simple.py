"""Classe couvert : long spot et short perp (même notionnel) sur les `k` premières colonnes cotées."""
import numpy as np


class Strategie:
    def __init__(self, n_paires, taille=0.25, k=2):
        self.n = n_paires
        self.taille = taille
        self.k = k

    def pas(self, jour):
        ok = jour.eligibles & jour.eligibles_perp
        ws = np.zeros(self.n)
        pris = 0
        for j in range(self.n):
            if ok[j] and pris < self.k:
                ws[j] = self.taille
                pris += 1
        return ws, ws.copy()
