"""Contrat de flux entre le moteur et une stratégie (protocole §3).

Ce module est copié tel quel dans le bac à sable : il ne dépend que de la bibliothèque standard et de numpy.

Un fichier `strategie.py` définit :

    class Strategie:
        def __init__(self, n_paires: int, **params): ...
        def pas(self, jour: Jour) -> tuple[ndarray, ndarray]: ...   # (poids_spot, poids_perp), chacun (n_paires,)

`pas` est appelée une fois par jour, dans l'ordre, avec les données connues à la clôture de 00:00 UTC qui
termine ce jour (barre journalière complète, ses 24 barres de 1 h, les échéances de funding du jour).
La stratégie ne reçoit ni date ni nom de paire : l'ordre des colonnes est permuté à chaque essai.
`poids_perp[j]` est un notionnel court en fraction du capital (>= 0).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Colonnes de `spot_1d` et des barres 1 h : open, high, low, close, volume (base), taker_buy_base.
COL_O, COL_H, COL_L, COL_C, COL_V, COL_TB = range(6)
N_COLONNES = 6
HEURES = 24

#: Codes fermés rendus aux agents (criteres.yaml : execution.codes_retour).
OK = "OK"
CAUSALITE = "CAUSALITE"
TIMEOUT = "TIMEOUT"
SOURCE_REFUSEE = "SOURCE_REFUSEE"
FORME_POIDS = "FORME_POIDS"
ERREUR = "ERREUR"
CODES = (OK, CAUSALITE, TIMEOUT, SOURCE_REFUSEE, FORME_POIDS, ERREUR)

#: Tolérance de comparaison des bornes de poids (jamais utilisée pour rogner).
TOL_POIDS = 1e-9


class ErreurEssai(Exception):
    """Échec d'un essai avec un code fermé ; `detail` ne va qu'au journal technique, jamais à un agent."""

    code = ERREUR

    def __init__(self, detail: str = ""):
        super().__init__(detail)
        self.detail = detail


class SourceRefusee(ErreurEssai):
    code = SOURCE_REFUSEE


class FormePoids(ErreurEssai):
    code = FORME_POIDS


class DelaiDepasse(ErreurEssai):
    code = TIMEOUT


class Causalite(ErreurEssai):
    code = CAUSALITE


@dataclass(frozen=True, slots=True)
class Jour:
    """Message du jour `i` (0 = premier jour de la fenêtre complète, échauffement compris)."""

    i: int
    spot_1d: np.ndarray  # (n_paires, 6) o,h,l,c,v,taker_buy_base ; zéros tant que la paire n'est pas cotée
    spot_1h: np.ndarray | None  # (n_paires, 24, 6)
    perp_1h: np.ndarray | None  # (n_paires, 24, 6)
    funding: list  # [(paire_idx, taux)] des échéances dont connue_a <= clôture du jour
    eligibles: np.ndarray  # (n_paires,) bool : la paire est cotée (spot) ce jour
    eligibles_perp: np.ndarray | None  # (n_paires,) bool : le perpétuel existe ce jour


CHAMPS_JOUR = ("i", "spot_1d", "spot_1h", "perp_1h", "funding", "eligibles", "eligibles_perp")
