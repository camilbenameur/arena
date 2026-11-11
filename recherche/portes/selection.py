"""Sélection finale (PROTOCOLE §6 « Sélection ») : classement par DSR, corrélation des excès, 3 au plus.

Ne choisit que parmi les essais qui ont passé toutes les portes (le filtre est fait par l'appelant avec
`Verdict.passe`). Aucun jugement : tri par DSR décroissant puis règle gloutonne.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

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


# Probabilité qu'UN candidat sans avantage réel soit « non réfuté » au paper. Le protocole (§6) donne
# « environ 85 % pour 3 » : 1 - (1 - p)^3 = 0,85  =>  p = 1 - 0,15^(1/3) = 0,4686. Valeur calibrée sur ce
# chiffre, pas dérivée : elle dépend du drawdown du backtest contraint (C15) et du rythme des regards.
P_NON_REFUTE_H0_DEFAUT = 1.0 - 0.15 ** (1.0 / 3.0)


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
