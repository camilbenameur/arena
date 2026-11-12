"""Statistiques des portes (recherche-v1). Fonctions pures sur des rendements QUOTIDIENS (pd.Series à index
de dates, ou ndarray pour les fonctions sans calendrier). Annualisation en √365 (crypto, 7 j sur 7).

Aucune de ces fonctions ne lit de donnée de marché : le moteur fournit les séries.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, skew

JOURS_AN = 365


def _arr(x) -> np.ndarray:
    return np.asarray(x, dtype=float)


def sr_jour(r) -> float:
    """Sharpe journalier (non annualisé), écart-type ddof=1. NaN si variance nulle ou < 2 points."""
    x = _arr(r)
    if len(x) < 2:
        return float("nan")
    sd = x.std(ddof=1)
    return float(x.mean() / sd) if sd > 0 else float("nan")


def sharpe(r) -> float:
    """Sharpe annualisé (x √365)."""
    return sr_jour(r) * math.sqrt(JOURS_AN)


def moments(r) -> tuple[float, float]:
    """(asymétrie, kurtosis non excès), biaisés comme au labo."""
    x = _arr(r)
    return float(skew(x, bias=True)), float(kurtosis(x, fisher=False, bias=True))


def t_newey_west(r, retards: int = 20) -> float:
    """t de la moyenne, variance de long terme de Newey-West (poids de Bartlett), comme au labo."""
    x = _arr(r)
    n = len(x)
    m = x.mean()
    c = x - m
    lrv = float(c @ c) / n
    for k in range(1, retards + 1):
        lrv += 2.0 * (1.0 - k / (retards + 1)) * float(c[k:] @ c[:-k]) / n
    return float(m / math.sqrt(lrv / n)) if lrv > 0 else float("nan")


def drawdown(r) -> float:
    """Drawdown maximal de la valeur liquidative composée en clôtures quotidiennes (départ à 1)."""
    nav = np.concatenate([[1.0], np.cumprod(1.0 + _arr(r))])
    pic = np.maximum.accumulate(nav)
    return float((1.0 - nav / pic).max())


def rendement_annualise(r) -> float:
    """Rendement annualisé géométrique : (prod(1+r))^(365/n) - 1."""
    x = _arr(r)
    if len(x) == 0:
        return float("nan")
    nav = float(np.prod(1.0 + x))
    if nav <= 0:
        return -1.0
    return nav ** (JOURS_AN / len(x)) - 1.0


def rotation_annuelle(rotation) -> float:
    """Rotation annuelle = somme des rotations quotidiennes / (n / 365)."""
    x = _arr(rotation)
    return float(x.sum() / (len(x) / JOURS_AN))


def bootstrap_blocs(
    x, longueur: int = 20, replications: int = 5000, graine: int = 12345, lot: int = 500
) -> dict:
    """Bootstrap par blocs circulaires de `longueur` jours. H0 : moyenne <= 0.

    La série est centrée (moyenne nulle), rééchantillonnée par blocs ; p unilatéral = (1 + nb de moyennes
    rééchantillonnées >= moyenne observée) / (replications + 1). Même algorithme que le labo (C10).
    """
    v = _arr(x)
    T = len(v)
    obs = float(v.mean())
    c = v - obs
    rng = np.random.default_rng(graine)
    nb = math.ceil(T / longueur)
    deltas = np.arange(longueur)
    ge = 0
    vus = 0
    while vus < replications:
        k = min(lot, replications - vus)
        debuts = rng.integers(0, T, size=(k, nb))
        idx = ((debuts[:, :, None] + deltas) % T).reshape(k, -1)[:, :T]
        ge += int((c[idx].mean(axis=1) >= obs).sum())
        vus += k
    return {"p": (ge + 1) / (replications + 1), "moyenne": obs, "T": T}


def bootstrap_apparie(a, b, longueur: int = 20, replications: int = 5000, graine: int = 12345) -> dict:
    """Bootstrap apparié par blocs sur la différence a - b (séries alignées par index si pd.Series)."""
    if isinstance(a, pd.Series) and isinstance(b, pd.Series):
        a, b = a.align(b, join="inner")
    d = _arr(a) - _arr(b)
    if len(d) < 2:
        raise ValueError("séries trop courtes pour un bootstrap apparié")
    return bootstrap_blocs(d, longueur, replications, graine)


def regression_alpha_beta(y, x, retards: int = 20) -> dict:
    """MCO y = alpha + beta x + u, variance HAC de Newey-West (Bartlett), sans correction de petit échantillon.

    Renvoie alpha_jour, alpha_annuel (x365), beta, t_alpha, t_beta. Séries alignées par index si pd.Series.
    """
    if isinstance(y, pd.Series) and isinstance(x, pd.Series):
        y, x = y.align(x, join="inner")
    yv = _arr(y)
    xv = _arr(x)
    n = len(yv)
    X = np.column_stack([np.ones(n), xv])
    xtx_inv = np.linalg.inv(X.T @ X)
    coef = xtx_inv @ X.T @ yv
    u = yv - X @ coef
    Xu = X * u[:, None]
    S = Xu.T @ Xu
    for k in range(1, retards + 1):
        g = Xu[k:].T @ Xu[:-k]
        S += (1.0 - k / (retards + 1)) * (g + g.T)
    cov = xtx_inv @ S @ xtx_inv
    se = np.sqrt(np.diag(cov))
    return {
        "alpha_jour": float(coef[0]),
        "alpha_annuel": float(coef[0] * JOURS_AN),
        "beta": float(coef[1]),
        "t_alpha": float(coef[0] / se[0]) if se[0] > 0 else float("nan"),
        "t_beta": float(coef[1] / se[1]) if se[1] > 0 else float("nan"),
    }


def retirer_meilleurs_jours(r, part: float):
    """Retire les ceil(part x n) meilleurs jours (supprimés, pas mis à zéro). Renvoie (série, nb retirés)."""
    n = len(r)
    k = math.ceil(part * n - 1e-12)
    if k <= 0:
        return r, 0
    if isinstance(r, pd.Series):
        sortie = r.drop(r.nlargest(k).index) if r.index.is_unique else r.sort_values().iloc[:-k]
        return sortie.sort_index() if r.index.is_unique else sortie, k
    v = _arr(r)
    return np.sort(v)[:-k], k


def _plat(x) -> bool:
    """Au moins 2 points, tous exactement nuls (stratégie à plat : écart-type nul, Sharpe NaN)."""
    v = _arr(x)
    return len(v) >= 2 and bool(np.all(v == 0.0))


def sharpe_par_annee(r: pd.Series, annees: Sequence[int], *, plat_vaut_zero: bool = False) -> dict[int, float]:
    """Sharpe annualisé par année civile ; NaN si l'année est absente.

    Une année à rendement exactement nul (stratégie à plat toute l'année) a un écart-type nul, donc un
    Sharpe NaN. Avec `plat_vaut_zero`, elle vaut 0,0 : « non positive et non sous −1 » pour C5.
    """
    out = {}
    for a in annees:
        sel = r[r.index.year == a]
        if plat_vaut_zero and _plat(sel):
            out[int(a)] = 0.0
        else:
            out[int(a)] = sharpe(sel) if len(sel) >= 2 else float("nan")
    return out


def sharpe_moities(r) -> tuple[float, float]:
    """Sharpe de chaque moitié de la fenêtre (première moitié = n // 2 premiers jours).

    Une moitié entièrement à plat (rendements tous nuls) a un Sharpe de 0,0 (et non NaN) : C13 exige
    > 0 dans chaque moitié, donc une moitié à plat fait échouer C13.
    """
    x = _arr(r)
    h = len(x) // 2
    moities = (x[:h], x[h:])
    return tuple(0.0 if _plat(m) else sharpe(m) for m in moities)  # type: ignore[return-value]
