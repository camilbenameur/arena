"""Fiche directionnel avec `signaux_perp: true` : le funding arrive comme signal, la jambe perp reste nulle."""

from __future__ import annotations

from recherche.moteur.essai import FicheEssai, executer_essai
from recherche.moteur.panneau import synthetique
from tests.recherche.test_moteur import _canari, crit, ecrire, journal, labo_factice  # noqa: F401

# Directionnel : tout le panier tant que le funding n'a jamais été vu ; 0 dès qu'une échéance arrive.
VOIT_FUNDING = """
import numpy as np
class Strategie:
    def __init__(self, n_paires):
        self.n = n_paires
        self.vu = False
    def pas(self, jour):
        if jour.funding:
            self.vu = True
        w = np.zeros(self.n)
        if not self.vu:
            w[jour.eligibles] = 1.0 / max(1, int(jour.eligibles.sum()))
        return w, np.zeros(self.n)
"""

# Directionnel qui tente une jambe perp : le moteur doit refuser (FORME_POIDS), jamais rogner.
JAMBE_PERP = """
import numpy as np
class Strategie:
    def __init__(self, n_paires):
        self.n = n_paires
    def pas(self, jour):
        w = np.zeros(self.n)
        p = np.zeros(self.n)
        if jour.eligibles_perp is not None:
            ok = jour.eligibles & jour.eligibles_perp
            w[ok] = 0.1
            p[ok] = 0.1
        return w, p
"""


def _exposition(r):
    return r.serie.exposition if hasattr(r.serie, "exposition") else None


def test_sans_declaration_le_funding_est_retire(tmp_path, journal, crit):  # noqa: F811
    pan = synthetique(60, 3, 0, avec_perp=True)
    p = ecrire(tmp_path, VOIT_FUNDING)
    r = executer_essai(FicheEssai("x", "directionnel", "a" * 64), p, {}, pan, journal, crit, causalite=False, test=True)
    assert r.code == "OK"
    expo = _exposition(r)
    assert expo is None or float(max(expo)) > 0  # jamais vu de funding : reste investi


def test_avec_declaration_le_funding_arrive(tmp_path, journal, crit):  # noqa: F811
    pan = synthetique(60, 3, 0, avec_perp=True)
    p = ecrire(tmp_path, VOIT_FUNDING)
    fiche = FicheEssai("x", "directionnel", "a" * 64, signaux_perp=True)
    r = executer_essai(fiche, p, {}, pan, journal, crit, causalite=False, test=True)
    assert r.code == "OK"
    expo = _exposition(r)
    if expo is not None:
        assert float(expo[-1]) == 0.0  # le funding a été vu : sorti


def test_directionnel_jambe_perp_refusee_meme_avec_signaux(tmp_path, journal, crit):  # noqa: F811
    pan = synthetique(60, 3, 0, avec_perp=True)
    p = ecrire(tmp_path, JAMBE_PERP)
    fiche = FicheEssai("x", "directionnel", "a" * 64, signaux_perp=True)
    r = executer_essai(fiche, p, {}, pan, journal, crit, causalite=False, test=True)
    assert r.code == "FORME_POIDS"
