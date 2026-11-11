"""Sélection finale (PROTOCOLE §6 « Sélection ») : classement par DSR, corrélation des excès, 3 au plus.

Ne choisit que parmi les essais qui ont passé toutes les portes (le filtre est fait par l'appelant avec
`Verdict.passe`). Aucun jugement : tri par DSR décroissant puis règle gloutonne.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from recherche.portes.evaluer import section


@dataclass(frozen=True)
class Candidat:
    id: str
    dsr: float
    exces: pd.Series  # rendement net du candidat moins rendement du panier, quotidien


@dataclass(frozen=True)
class Selection:
    retenus: tuple[str, ...]
    ecartes: dict[str, str]  # id -> raison
    correlations: dict[tuple[str, str], float] = field(default_factory=dict)
    p_au_moins_un_non_refute: float = 0.0


def simuler_p_non_refute(
    sigma_ann: float = 0.30, drawdown_backtest: float = 0.30, n_jours: int = 56, n_sim: int = 400_000,
    graine: int = 20261111, regard_s: int = 7, avec_drawdown: bool = True,
) -> float:
    """P(non réfuté | H0) par simulation de la règle de réfutation du §9.

    H0 : rendement journalier i.i.d. gaussien de moyenne NULLE, volatilité = celle du backtest
    (`sigma_ann`, annualisée en racine de 365). Le paper dure `n_jours` (56 ou 84), avec un regard par
    semaine. Réfuté si, à la fin, le rendement cumulé composé <= -0,5 x sigma_ann (56 j) ou
    -0,6 x sigma_ann (84 j), ou si, à l'un des regards hebdomadaires, le drawdown du paper dépasse
    1,3 x `drawdown_backtest` (drawdown du backtest contraint C15). Aucune dépense d'alpha n'est simulée aux
    regards intermédiaires : le protocole ne fixe de seuil de rendement qu'à 56 et 84 jours.
    Ce n'est PAS une calibration : on rapporte la valeur obtenue, quelle qu'elle soit.
    """
    facteur = {56: -0.5, 84: -0.6}.get(n_jours)
    if facteur is None:
        raise ValueError("n_jours doit être 56 ou 84 (criteres.yaml paper.refutation)")
    rng = np.random.default_rng(graine)
    sd = sigma_ann / math.sqrt(365.0)
    nav_fin = np.empty(n_sim)
    dd_max = np.zeros(n_sim)
    regards = np.arange(regard_s, n_jours + 1, regard_s)  # jours 7, 14, ... (nombre de jours écoulés)
    for debut in range(0, n_sim, 100_000):
        k = min(100_000, n_sim - debut)
        nav = np.cumprod(1.0 + rng.normal(0.0, sd, (k, n_jours)), axis=1)
        nav_fin[debut:debut + k] = nav[:, -1]
        nv = np.concatenate([np.ones((k, 1)), nav], axis=1)
        dd = 1.0 - nv / np.maximum.accumulate(nv, axis=1)
        dd_max[debut:debut + k] = dd[:, regards].max(axis=1)
    refute = (nav_fin - 1.0) <= facteur * sigma_ann
    if avec_drawdown:
        refute |= dd_max > 1.3 * drawdown_backtest
    return float(1.0 - refute.mean())


# P(non réfuté | H0) d'un candidat de volatilité 30 % et de drawdown de backtest 30 % (56 jours), valeur
# SIMULÉE (graine fixe, 400 000 trajectoires, erreur type ~ 5e-4), pas calibrée sur un résultat voulu :
# elle est proche de 0,91, c'est-à-dire que le paper ne réfute presque jamais un candidat sans avantage.
# Un test relance la simulation et vérifie cette constante. Le « environ 85 % pour 3 » du protocole §6 est
# donc faux : 1 - (1 - 0,907)^3 = 0,999.
P_NON_REFUTE_H0_DEFAUT = 0.9068475


def proba_au_moins_un_non_refute(n_candidats: int, p_non_refute_h0: float = P_NON_REFUTE_H0_DEFAUT) -> float:
    """P(au moins un non réfuté | H0) = 1 - (1 - p)^n, candidats supposés indépendants (borne haute)."""
    if n_candidats <= 0:
        return 0.0
    return 1.0 - (1.0 - p_non_refute_h0) ** n_candidats


def selectionner(
    candidats: Sequence[Candidat],
    criteres,
    p_non_refute_h0: float = P_NON_REFUTE_H0_DEFAUT,
) -> Selection:
    """Classe par DSR décroissant ; garde un candidat si sa corrélation (Pearson, quotidienne) des excès
    avec chaque candidat déjà retenu est <= correlation_exces_panier_max ; 3 au plus."""
    sel = section(criteres, "selection")
    cmax = sel["correlation_exces_panier_max"]
    nmax = int(sel["candidats_max"])
    classes = sorted(candidats, key=lambda c: (-c.dsr, c.id))  # égalité de DSR : ordre de l'id, déterministe
    retenus: list[Candidat] = []
    ecartes: dict[str, str] = {}
    corr: dict[tuple[str, str], float] = {}
    for c in classes:
        if len(retenus) >= nmax:
            ecartes[c.id] = f"au-delà de {nmax} candidats"
            continue
        motif = None
        for r in retenus:
            a, b = c.exces.align(r.exces, join="inner")
            rho = float(a.corr(b)) if len(a) > 2 else float("nan")
            corr[(r.id, c.id)] = rho
            if math.isnan(rho) or rho > cmax:  # NaN : non vérifiable, on écarte
                motif = f"corrélation des excès avec {r.id} : {rho:.3f} > {cmax}"
                break
        if motif:
            ecartes[c.id] = motif
        else:
            retenus.append(c)
    return Selection(
        retenus=tuple(c.id for c in retenus),
        ecartes=ecartes,
        correlations=corr,
        p_au_moins_un_non_refute=proba_au_moins_un_non_refute(len(retenus), p_non_refute_h0),
    )
