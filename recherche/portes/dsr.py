"""Sharpe déflaté de Bailey & López de Prado (2014), recherche-v1.

Formules du labo (`~/dev/labo-trading/outils/dsr.py`), recopiées sans le journal du labo. Tout en unités
JOURNALIÈRES : sr_jour = moyenne / écart-type des rendements quotidiens nets (non annualisé), T = nombre
de jours, skew, kurt = kurtosis NON excès (3 pour la loi normale).

    SR* = sqrt(V) * ((1-g) * Phi^-1(1-1/N) + g * Phi^-1(1-1/(N*e)))      g = 0,5772156649
    DSR = Phi( (SR - SR*) * sqrt(T-1) / sqrt(1 - skew*SR + (kurt-1)/4 * SR^2) )
    V   = max(variance des sr_jour de la classe, 1/(T-1))                 (PROTOCOLE §5)

L'exemple numérique publié (SR annualisé 2,5, T=1250, asymétrie -3, kurtosis 10, N=100, variance annualisée
des Sharpe 0,5, 250 jours par an) donne DSR = 0,9004 dans l'article ; il est reproduit dans les tests.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from scipy.optimize import brentq
from scipy.stats import norm

GAMMA = 0.5772156649  # Euler-Mascheroni, valeur de criteres.yaml
N_MINIMUM = 2
JOURS_AN = 365


def sr_etoile(V: float, N: int) -> float:
    """Sharpe journalier attendu du meilleur de N essais sans avantage réel (V = variance journalière)."""
    if N < N_MINIMUM:
        raise ValueError(f"N={N} refusé : le DSR exige N >= {N_MINIMUM}")
    if not (V > 0 and math.isfinite(V)):
        raise ValueError(f"V doit être > 0 et fini (reçu {V})")
    return math.sqrt(V) * (
        (1 - GAMMA) * norm.ppf(1 - 1.0 / N) + GAMMA * norm.ppf(1 - 1.0 / (N * math.e))
    )


def dsr_proba(sr_jour: float, T: int, skew: float, kurt: float, N: int, V: float) -> float:
    """Probabilité que le Sharpe soit réel (unités journalières, kurtosis non excès)."""
    if T < 2:
        raise ValueError("T doit être >= 2")
    if not math.isfinite(sr_jour):
        raise ValueError("sr_jour non fini : DSR impossible")
    sr0 = sr_etoile(V, N)
    denom = 1 - skew * sr_jour + (kurt - 1) / 4.0 * sr_jour**2
    if not denom > 0:
        raise ValueError(f"dénominateur non positif ({denom}) : skew/kurt incohérents")
    z = (sr_jour - sr0) * math.sqrt(T - 1) / math.sqrt(denom)
    return float(norm.cdf(z))


def plancher_variance(T: int) -> float:
    """Plancher de V : 1/(T-1)."""
    return 1.0 / (T - 1)


def variance_classe(sr_par_famille: dict[str, Iterable[float]], T: int) -> float:
    """V d'une classe : max(moyenne pondérée par famille des variances des sr_jour, 1/(T-1)).

    `sr_par_famille` : famille -> sr_jour des essais de recherche de cette classe (labo exclu). Une famille
    à moins de 2 essais n'a pas de variance : elle est ignorée. Poids = nombre d'essais de la famille.
    """
    num = 0.0
    poids = 0
    for srs in sr_par_famille.values():
        v = [float(x) for x in srs if x is not None and math.isfinite(float(x))]
        if len(v) < 2:
            continue
        m = sum(v) / len(v)
        var = sum((x - m) ** 2 for x in v) / (len(v) - 1)
        num += len(v) * var
        poids += len(v)
    plancher = plancher_variance(T)
    if poids == 0:
        return plancher
    return max(num / poids, plancher)


def v_depuis_ecart_type_annuel(ecart_type_sharpe_annualise: float) -> float:
    """Variance journalière équivalente à un écart-type de Sharpe annualisé (colonnes 0,5 / 0,7 du §5)."""
    return ecart_type_sharpe_annualise**2 / JOURS_AN


def sharpe_requis(
    N: int,
    T: int,
    V: float | None = None,
    skew: float = 0.0,
    kurt: float = 3.0,
    cible: float = 0.95,
    annualise: bool = True,
) -> float:
    """Sharpe net requis pour DSR >= cible. V = None : plancher 1/(T-1).

    Renvoie le Sharpe annualisé (x sqrt(365)) si `annualise`, sinon le sr_jour. DSR est strictement croissant
    en sr_jour (dérivée du numérateur sur dénominateur de signe constant), la racine est donc unique.
    """
    v = plancher_variance(T) if V is None else V
    sr0 = sr_etoile(v, N)

    def f(sr: float) -> float:
        return dsr_proba(sr, T, skew, kurt, N, v) - cible

    sr = float(brentq(f, sr0, max(1.0, 10 * sr0), xtol=1e-14))
    return sr * math.sqrt(JOURS_AN) if annualise else sr
