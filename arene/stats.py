"""Statistiques des séries d'equity (docs/SPEC-MVP.md §10 et §13).

Entrée : séries d'equity ENTIÈRES (µEUR), une valeur par cycle. Les floats sont permis ici (statistiques
et affichage, jamais le chemin de l'argent). Python pur, sans dépendance. Tout tirage aléatoire utilise
une graine fixe : mêmes séries, mêmes intervalles.
"""

from __future__ import annotations

import itertools
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

CYCLES_PER_DAY = 6
DAYS_PER_YEAR = 365
PERIODS_PER_YEAR = CYCLES_PER_DAY * DAYS_PER_YEAR  # 2 190
BLOCK = 6  # un jour de cycles
N_BOOT = 2_000
SEED = 20_261_111
ALPHA = 0.05


def returns(equity: Sequence[int]) -> list[float]:
    """Rendements simples par cycle : e[i] / e[i-1] - 1. Une série de moins de 2 points donne []."""
    out = []
    for prev, cur in itertools.pairwise(equity):
        if prev <= 0:
            raise ValueError("equity <= 0 : rendement indéfini")
        out.append(cur / prev - 1.0)
    return out


def total_return(equity: Sequence[int]) -> float:
    """Rendement total e[-1] / e[0] - 1 (0.0 si moins de 2 points)."""
    if len(equity) < 2:
        return 0.0
    if equity[0] <= 0:
        raise ValueError("equity initiale <= 0")
    return equity[-1] / equity[0] - 1.0


def max_drawdown(equity: Sequence[int]) -> float:
    """Drawdown maximal en fraction positive du plus haut (0.2 = -20 %). 0.0 si la série ne baisse jamais."""
    peak = 0
    worst = 0.0
    for e in equity:
        peak = max(peak, e)
        if peak > 0:
            worst = max(worst, (peak - e) / peak)
    return worst


def sharpe(rets: Sequence[float], periods_per_year: int = PERIODS_PER_YEAR) -> float:
    """Sharpe annualisé : moyenne / écart type (ddof = 1) × sqrt(periods_per_year), taux sans risque nul.

    Renvoie 0.0 si l'écart type est nul (série constante) ou s'il y a moins de 2 rendements.
    """
    n = len(rets)
    if n < 2:
        return 0.0
    mean = math.fsum(rets) / n
    var = math.fsum((r - mean) ** 2 for r in rets) / (n - 1)
    if var <= 1e-30:  # série constante, au bruit d'arrondi près
        return 0.0
    return mean / math.sqrt(var) * math.sqrt(periods_per_year)


def _resample(rets: Sequence[float], block: int, rng: random.Random) -> list[float]:
    """Une série rééchantillonnée par blocs glissants de longueur `block`, de la même longueur que `rets`."""
    n = len(rets)
    b = max(1, min(block, n))
    out: list[float] = []
    while len(out) < n:
        start = rng.randrange(n - b + 1)
        out.extend(rets[start : start + b])
    return out[:n]


def _percentiles(values: list[float], alpha: float) -> tuple[float, float]:
    values.sort()
    n = len(values)
    lo = values[min(n - 1, math.floor(alpha / 2 * n))]
    hi = values[min(n - 1, math.ceil((1 - alpha / 2) * n) - 1)]
    return lo, hi


def sharpe_ci(
    rets: Sequence[float],
    *,
    n_boot: int = N_BOOT,
    block: int = BLOCK,
    seed: int = SEED,
    alpha: float = ALPHA,
    periods_per_year: int = PERIODS_PER_YEAR,
) -> tuple[float, float]:
    """Intervalle de confiance (1 - alpha) du Sharpe par bootstrap par blocs glissants (percentiles).

    Moins de 2 rendements : (0.0, 0.0).
    """
    if len(rets) < 2:
        return 0.0, 0.0
    rng = random.Random(seed)
    stats = [sharpe(_resample(rets, block, rng), periods_per_year) for _ in range(n_boot)]
    return _percentiles(stats, alpha)


def rank_in_distribution(value: float, distribution: Sequence[float]) -> float:
    """Percentile de `value` dans `distribution`, en [0, 100] : part des valeurs strictement inférieures
    plus la moitié des égalités. Distribution vide : ValueError."""
    n = len(distribution)
    if n == 0:
        raise ValueError("distribution vide")
    below = sum(1 for d in distribution if d < value)
    equal = sum(1 for d in distribution if d == value)
    return 100.0 * (below + equal / 2) / n


@dataclass(frozen=True)
class Distinction:
    """Résultat de `distinguishable`. `bool(résultat)` vaut `significant`."""

    significant: bool
    mean_diff: float  # écart moyen de rendement par cycle (portefeuille - référence)
    ci_low: float
    ci_high: float

    def __bool__(self) -> bool:
        return self.significant


def distinguishable(
    rets: Sequence[float],
    baseline_rets: Sequence[float],
    *,
    n_boot: int = N_BOOT,
    block: int = BLOCK,
    seed: int = SEED,
    alpha: float = ALPHA,
) -> Distinction:
    """L'écart de rendement du portefeuille au panier est-il significatif ?

    Bootstrap APPARIÉ par blocs : on rééchantillonne la série des différences cycle par cycle (mêmes
    blocs pour les deux portefeuilles), on garde la moyenne ; l'écart est significatif si l'intervalle
    à 95 % (percentiles) exclut 0. Sinon le site affiche « non distinguable du hasard ».
    """
    if len(rets) != len(baseline_rets):
        raise ValueError("séries de longueurs différentes")
    diff = [a - b for a, b in zip(rets, baseline_rets, strict=True)]
    n = len(diff)
    if n < 2:
        return Distinction(False, 0.0, 0.0, 0.0)
    rng = random.Random(seed)
    means = [math.fsum(_resample(diff, block, rng)) / n for _ in range(n_boot)]
    lo, hi = _percentiles(means, alpha)
    mean = math.fsum(diff) / n
    return Distinction(lo > 0 or hi < 0, mean, lo, hi)
