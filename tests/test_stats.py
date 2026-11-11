"""Tests de arene/stats.py sur des séries à résultat connu."""

from __future__ import annotations

import math
import random

import pytest

from arene import stats
from arene.stats import (
    Distinction,
    distinguishable,
    max_drawdown,
    rank_in_distribution,
    returns,
    sharpe,
    sharpe_ci,
    total_return,
)

M = 1_000_000


def test_serie_constante():
    eq = [1000 * M] * 50
    assert returns(eq) == [0.0] * 49
    assert total_return(eq) == 0.0
    assert max_drawdown(eq) == 0.0
    assert sharpe(returns(eq)) == 0.0
    assert sharpe_ci(returns(eq)) == (0.0, 0.0)


def test_rendements_et_rendement_total():
    eq = [1000 * M, 1100 * M, 990 * M, 1089 * M]
    assert returns(eq) == pytest.approx([0.10, -0.10, 0.10])
    assert total_return(eq) == pytest.approx(0.089)
    assert returns([5]) == [] and total_return([5]) == 0.0
    with pytest.raises(ValueError):
        returns([0, 10])


def test_drawdown_connu():
    eq = [100, 120, 90, 110, 60, 130, 117]
    assert max_drawdown(eq) == pytest.approx(0.5)  # 120 -> 60
    assert max_drawdown([100, 110, 121]) == 0.0
    assert max_drawdown([100, 80]) == pytest.approx(0.2)


def test_sharpe_serie_construite():
    # rendements alternés +1 % / -0.5 % : moyenne 0.25 %, écart type d'échantillon connu
    rets = [0.01, -0.005] * 50
    mean = 0.0025
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / 99)
    assert sharpe(rets) == pytest.approx(mean / sd * math.sqrt(2190))
    assert stats.PERIODS_PER_YEAR == 6 * 365
    assert sharpe(rets, periods_per_year=1) == pytest.approx(mean / sd)
    assert sharpe([0.01]) == 0.0
    assert sharpe([-x for x in rets]) == pytest.approx(-sharpe(rets))


def test_sharpe_ci_encadre_et_est_reproductible():
    rng = random.Random(1)
    rets = [rng.gauss(0.001, 0.01) for _ in range(300)]
    lo, hi = sharpe_ci(rets)
    assert lo < sharpe(rets) < hi
    assert (lo, hi) == sharpe_ci(rets)  # graine fixe
    assert (lo, hi) != sharpe_ci(rets, seed=1)
    # plus de données : intervalle plus étroit
    more = [rng.gauss(0.001, 0.01) for _ in range(3000)]
    lo2, hi2 = sharpe_ci(more)
    assert hi2 - lo2 < hi - lo


def test_sharpe_ci_bloc_plus_grand_que_la_serie():
    lo, hi = sharpe_ci([0.01, -0.01, 0.02], block=6, n_boot=50)
    assert lo <= hi


def test_rank_in_distribution():
    d = list(range(1, 101))  # 1..100
    assert rank_in_distribution(1000, d) == 100.0
    assert rank_in_distribution(-5, d) == 0.0
    assert rank_in_distribution(50.5, d) == 50.0
    assert rank_in_distribution(50, d) == pytest.approx(49.5)  # 49 en dessous + la moitié de l'égalité
    assert rank_in_distribution(3, [3, 3, 3, 3]) == 50.0
    with pytest.raises(ValueError):
        rank_in_distribution(1.0, [])


def test_distinguishable_ecart_net():
    rng = random.Random(3)
    base = [rng.gauss(0.0, 0.01) for _ in range(360)]
    better = [b + 0.002 + rng.gauss(0, 0.0005) for b in base]  # +0.2 % par cycle, très régulier
    res = distinguishable(better, base)
    assert isinstance(res, Distinction) and res.significant and bool(res)
    assert res.ci_low > 0 and res.mean_diff == pytest.approx(0.002, abs=2e-4)
    assert distinguishable(base, better).significant  # symétrique : sous le panier aussi


def test_distinguishable_non_distinguable_du_hasard():
    rng = random.Random(4)
    base = [rng.gauss(0.0, 0.01) for _ in range(360)]
    same = list(base)
    res = distinguishable(same, base)
    assert not res.significant and res.ci_low == res.ci_high == 0.0
    noisy = [b + rng.gauss(0, 0.01) for b in base]  # bruit centré, aucun effet
    res = distinguishable(noisy, base)
    assert not res.significant and res.ci_low < 0 < res.ci_high
    assert distinguishable(noisy, base) == res  # graine fixe
    with pytest.raises(ValueError):
        distinguishable([0.1, 0.2], [0.1])
    assert not distinguishable([0.1], [0.0]).significant
