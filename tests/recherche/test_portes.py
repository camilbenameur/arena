"""Tests de recherche/portes/ : DSR (exemple publié, table du §5), statistiques, chaque porte C1-C16 « juste
au-dessus / juste en dessous » sur séries SYNTHÉTIQUES, sélection et replay arène (vrai riskd).

Aucune donnée de marché réelle. Les critères sont lus dans recherche/criteres.yaml.
"""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import yaml

from recherche.portes import dsr, evaluer, selection, stats
from recherche.portes.evaluer import Essai, RapportCausalite
from recherche.portes.replay_arene import POLICY_PATH, rejouer, symbole_arene

REPO = Path(__file__).resolve().parents[2]
CRIT = yaml.safe_load((REPO / "recherche" / "criteres.yaml").read_text(encoding="utf-8"))
P = CRIT["portes"]
T_PROTOCOLE = 2373


# ----------------------------------------------------------------------------- outils de test
def serie(sharpe_annuel: float, n: int = 400, graine: int = 0, std: float = 0.01, index=None) -> pd.Series:
    """Série de rendements dont le Sharpe annualisé est EXACTEMENT `sharpe_annuel` (standardisée)."""
    z = np.random.default_rng(graine).normal(size=n)
    z = (z - z.mean()) / z.std(ddof=1)
    x = z * std + sharpe_annuel / math.sqrt(365) * std
    idx = index if index is not None else pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.Series(x, index=idx)


def bascule(f, lo: float, hi: float, n: int = 60) -> float:
    """Frontière d'un prédicat monotone : f(lo) != f(hi) ; renvoie le point de bascule."""
    flo = f(lo)
    assert f(hi) != flo
    for _ in range(n):
        mid = (lo + hi) / 2
        if f(mid) == flo:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ----------------------------------------------------------------------------- DSR
def test_exemple_publie_bailey_lopez_de_prado():
    # Article (2014) : SR annualisé 2,5, T=1250 (250 j/an), asymétrie -3, kurtosis 10, N=100, V annualisée 0,5.
    V = 0.5 / 250
    sr = 2.5 / math.sqrt(250)
    assert dsr.sr_etoile(V, 100) * math.sqrt(250) == pytest.approx(1.7894, abs=1e-3)
    assert dsr.dsr_proba(sr, 1250, -3.0, 10.0, 100, V) == pytest.approx(0.9004, abs=5e-4)


@pytest.mark.parametrize(
    ("N", "plancher", "sd05", "sd07"),
    [(326, 1.79, 2.2, 2.69), (726, 1.89, 2.3, 2.86)],
)
def test_table_du_protocole_section_5(N, plancher, sd05, sd07):
    assert dsr.sharpe_requis(N, T_PROTOCOLE) == pytest.approx(plancher, abs=0.02)
    assert dsr.sharpe_requis(N, T_PROTOCOLE, dsr.v_depuis_ecart_type_annuel(0.7)) == pytest.approx(sd07, abs=0.02)
    # colonne « ≈ » du protocole : à 0,15 près (valeurs calculées 2,11 et 2,23)
    assert dsr.sharpe_requis(N, T_PROTOCOLE, dsr.v_depuis_ecart_type_annuel(0.5)) == pytest.approx(sd05, abs=0.15)


def test_sharpe_requis_est_la_racine_du_dsr():
    for N in (326, 726):
        req = dsr.sharpe_requis(N, T_PROTOCOLE, annualise=False)
        V = dsr.plancher_variance(T_PROTOCOLE)
        assert dsr.dsr_proba(req, T_PROTOCOLE, 0.0, 3.0, N, V) == pytest.approx(0.95, abs=1e-9)
        assert dsr.dsr_proba(req * 1.001, T_PROTOCOLE, 0.0, 3.0, N, V) > 0.95
        assert dsr.dsr_proba(req * 0.999, T_PROTOCOLE, 0.0, 3.0, N, V) < 0.95


def test_dsr_garde_fous():
    with pytest.raises(ValueError, match="N=1"):
        dsr.sr_etoile(1.0, 1)
    with pytest.raises(ValueError):
        dsr.sr_etoile(0.0, 100)
    with pytest.raises(ValueError):
        dsr.dsr_proba(float("nan"), 100, 0, 3, 10, 1e-3)
    assert dsr.dsr_proba(0.1, 500, -1.0, 10.0, 100, 1e-3) < dsr.dsr_proba(0.1, 500, 0.0, 3.0, 100, 1e-3)


def test_variance_par_classe_ponderee_par_famille_et_plancher():
    # famille A : 3 essais de variance 4e-4 ; famille B : 2 essais de variance 1e-4 ; poids 3 et 2
    a = [0.0, 0.02, -0.02]  # var = 4e-4
    b = [0.0, math.sqrt(2) * 0.01]  # var = 1e-4
    v = dsr.variance_classe({"A": a, "B": b, "seule": [0.5]}, T=10_000)
    assert v == pytest.approx((3 * 4e-4 + 2 * 1e-4) / 5)
    # sous le plancher 1/(T-1) : le plancher s'applique ; sans famille exploitable aussi
    assert dsr.variance_classe({"A": [0.0, 1e-6]}, T=100) == pytest.approx(1 / 99)
    assert dsr.variance_classe({}, T=100) == pytest.approx(1 / 99)


# ----------------------------------------------------------------------------- statistiques
def test_sharpe_et_rendement_annualise():
    r = serie(1.5, n=500)
    assert stats.sharpe(r) == pytest.approx(1.5)
    assert stats.sr_jour(r) == pytest.approx(1.5 / math.sqrt(365))
    g = 1.04 ** (1 / 365) - 1
    assert stats.rendement_annualise(np.full(730, g)) == pytest.approx(0.04)
    assert stats.rendement_annualise([-1.0, 0.5]) == -1.0


def test_drawdown_valeur_liquidative_composee():
    r = np.array([0.1, -0.2, 0.05, -0.1, 0.3])
    nav = np.cumprod(1 + r)
    attendu = 1 - 1.1 * 0.8 * 1.05 * 0.9 / (1.1)  # creux après le 4e jour, pic 1,1
    assert stats.drawdown(r) == pytest.approx(attendu)
    assert stats.drawdown(np.zeros(5)) == 0.0
    assert nav[-1] > 0


def test_t_newey_west_sans_retard_et_avec_autocorrelation():
    r = serie(1.0, n=1000, graine=3)
    n = len(r)
    t0 = stats.t_newey_west(r, 0)
    assert t0 == pytest.approx(r.mean() / (r.std(ddof=0) / math.sqrt(n)))
    # une série positivement autocorrélée voit son t baisser avec les retards
    rng = np.random.default_rng(5)
    e = rng.normal(size=3000)
    x = np.zeros(3000)
    for i in range(1, 3000):
        x[i] = 0.7 * x[i - 1] + e[i]
    x += 0.05
    assert stats.t_newey_west(x, 20) < stats.t_newey_west(x, 0)


def test_bootstrap_blocs_reproductible_et_calibre():
    forte = serie(3.0, n=1000)
    nulle = serie(0.0, n=1000)
    a = stats.bootstrap_blocs(forte)
    assert a == stats.bootstrap_blocs(forte)  # graine 12345 fixe
    assert a["p"] < 0.01
    assert stats.bootstrap_blocs(nulle)["p"] > 0.4
    assert stats.bootstrap_blocs(-serie(3.0, n=1000))["p"] > 0.95
    assert stats.bootstrap_blocs(forte, replications=100)["p"] >= 1 / 101


def test_bootstrap_apparie_est_un_bootstrap_de_la_difference():
    a, b = serie(2.0, graine=1), serie(0.5, graine=2)
    assert stats.bootstrap_apparie(a, b) == stats.bootstrap_blocs(a - b)
    # alignement par index : un décalage de dates réduit à l'intersection
    p1 = stats.bootstrap_apparie(a, b.iloc[50:])
    p2 = stats.bootstrap_blocs((a - b).iloc[50:])
    assert p1 == p2


def test_regression_alpha_beta_retrouve_les_parametres():
    rng = np.random.default_rng(11)
    x = pd.Series(rng.normal(0, 0.02, 3000), index=pd.date_range("2018-01-01", periods=3000))
    y = 0.001 + 0.25 * x + pd.Series(rng.normal(0, 0.003, 3000), index=x.index)
    reg = stats.regression_alpha_beta(y, x, 20)
    assert reg["beta"] == pytest.approx(0.25, abs=0.02)
    assert reg["alpha_jour"] == pytest.approx(0.001, abs=3e-4)
    assert reg["alpha_annuel"] == pytest.approx(reg["alpha_jour"] * 365)
    assert reg["t_alpha"] > 5
    # sans alpha : t petit
    y0 = 0.25 * x + pd.Series(rng.normal(0, 0.003, 3000), index=x.index)
    assert abs(stats.regression_alpha_beta(y0, x, 20)["t_alpha"]) < 3


def test_retrait_des_meilleurs_jours():
    idx = pd.date_range("2020-01-01", periods=T_PROTOCOLE)
    r = pd.Series(np.random.default_rng(0).normal(size=T_PROTOCOLE), index=idx)
    r1, k1 = stats.retirer_meilleurs_jours(r, 0.01)
    _, k2 = stats.retirer_meilleurs_jours(r, 0.02)
    assert (k1, len(r1)) == (24, T_PROTOCOLE - 24)  # « 1 % meilleurs jours (24 jours) » du protocole
    assert k2 == 48
    assert r1.max() < r.nlargest(24).min() + 1e-15
    assert r1.index.is_monotonic_increasing


def test_sharpe_par_annee_et_moities():
    idx = pd.date_range("2020-01-01", "2025-12-31")
    r = pd.Series(np.random.default_rng(0).normal(0.001, 0.01, len(idx)), index=idx)
    sh = stats.sharpe_par_annee(r, [2019, 2020, 2025])
    assert math.isnan(sh[2019])
    assert sh[2020] == pytest.approx(stats.sharpe(r[r.index.year == 2020]))
    a, b = stats.sharpe_moities(r)
    h = len(r) // 2
    assert (a, b) == (stats.sharpe(r.iloc[:h]), stats.sharpe(r.iloc[h:]))


# ----------------------------------------------------------------------------- portes, une par une
def test_c1_juste_au_dessus_et_en_dessous():
    n = T_PROTOCOLE
    base = serie(0.0, n=n, graine=7)
    sk, ku = stats.moments(base)
    N = CRIT["essais"]["N_dsr"]
    V = dsr.plancher_variance(n)
    req = dsr.sharpe_requis(N, n, skew=sk, kurt=ku, annualise=True)
    haut = serie(req + 0.002, n=n, graine=7)
    bas = serie(req - 0.002, n=n, graine=7)
    (ok_h, d_h, s_h), _ = evaluer.porte_c1(haut, N, V, P["C1_dsr_min"])
    (ok_b, d_b, _), _ = evaluer.porte_c1(bas, N, V, P["C1_dsr_min"])
    assert ok_h and not ok_b
    assert d_h >= s_h == 0.95 > d_b
    # la variance de classe plus grande que le plancher durcit la porte
    (ok_v, _, _), _ = evaluer.porte_c1(haut, N, 100 * V, P["C1_dsr_min"])
    assert not ok_v


def _annees(sharpes: dict[int, float]) -> pd.Series:
    parts = []
    for a, s in sharpes.items():
        idx = pd.date_range(f"{a}-01-01", f"{a}-12-31")
        parts.append(serie(s, n=len(idx), graine=a, index=idx))
    return pd.concat(parts)


def test_c5_annees():
    cfg = P["C5_annees"]
    ok = {a: 0.5 for a in range(2020, 2026)}
    assert evaluer.porte_c5(_annees(ok), cfg)[0]
    # une année juste sous -1 : échec ; juste au-dessus : réussite
    assert not evaluer.porte_c5(_annees({**ok, 2022: -1.001}), cfg)[0]
    assert evaluer.porte_c5(_annees({**ok, 2022: -0.999}), cfg)[0]
    # 4 positives exactement : réussite (2 négatives mais > -1) ; 3 positives : échec
    assert evaluer.porte_c5(_annees({**ok, 2021: -0.5, 2022: -0.5}), cfg)[0]
    assert not evaluer.porte_c5(_annees({**ok, 2021: -0.5, 2022: -0.5, 2023: -0.5}), cfg)[0]
    # année manquante : échec
    assert not evaluer.porte_c5(_annees({a: 0.5 for a in range(2020, 2025)}), cfg)[0]


@pytest.mark.parametrize("classe", ["directionnel", "couvert"])
def test_c6_drawdown(classe):
    lim = P["C6_drawdown_max"][classe]
    n = 200

    def avec_chute(d: float) -> pd.Series:
        r = np.zeros(n)
        r[50] = -d
        return pd.Series(r, index=pd.date_range("2020-01-01", periods=n))

    assert evaluer.porte_c6(avec_chute(lim - 0.001), classe, P["C6_drawdown_max"])[0]
    assert evaluer.porte_c6(avec_chute(lim), classe, P["C6_drawdown_max"])[0]  # ≤ inclusif
    assert not evaluer.porte_c6(avec_chute(lim + 0.001), classe, P["C6_drawdown_max"])[0]


GRILLE = {"a": [4.0, 6.0, 9.0], "b": [10.0, 15.0, 22.5]}


def _essai(params, sharpe, graine, famille="F", classe="directionnel", n=400) -> Essai:
    net = serie(sharpe, n=n, graine=graine)
    z = pd.Series(0.0, index=net.index)
    return Essai(f"{params}", famille, classe, params, net, net, net, z, z)


def _voisinage(sh_voisins: list[float], s_cand=2.0, params=None):
    params = params or {"a": 6.0, "b": 15.0}
    cand = _essai(params, s_cand, 0)
    voisins = [
        _essai({"a": 4.0, "b": 15.0}, sh_voisins[0], 1),
        _essai({"a": 9.0, "b": 15.0}, sh_voisins[1], 2),
        _essai({"a": 6.0, "b": 10.0}, sh_voisins[2], 3),
        _essai({"a": 6.0, "b": 22.5}, sh_voisins[3], 4),
    ]
    return cand, [cand, *voisins]


def test_c7_voisinage():
    cfg = P["C7_voisinage"]
    # seuil voisin = max(0,6 x 2,0 ; 0,5) = 1,2 ; 3 voisins sur 4 = 75 % : réussite
    cand, tous = _voisinage([1.21, 1.21, 1.21, 0.0])
    (ok, part, _), _ = evaluer.porte_c7(cand, tous, GRILLE, cfg, CRIT["essais"])
    assert ok and part == 0.75
    # juste en dessous du seuil de Sharpe voisin : 2 sur 4 -> échec
    cand, tous = _voisinage([1.19, 1.21, 1.21, 0.0])
    (ok, part, _), _ = evaluer.porte_c7(cand, tous, GRILLE, cfg, CRIT["essais"])
    assert not ok and part == 0.5
    # plancher absolu 0,5 : candidat à 0,6 -> seuil 0,5 (et non 0,36)
    cand, tous = _voisinage([0.51, 0.51, 0.51, 0.49], s_cand=0.6)
    assert evaluer.porte_c7(cand, tous, GRILLE, cfg, CRIT["essais"])[0][0]
    cand, tous = _voisinage([0.49, 0.51, 0.51, 0.49], s_cand=0.6)
    assert not evaluer.porte_c7(cand, tous, GRILLE, cfg, CRIT["essais"])[0][0]


def test_c7_echecs_structurels():
    cfg = P["C7_voisinage"]
    bons = [3.0, 3.0, 3.0, 3.0]
    # bord de grille
    cand, tous = _voisinage(bons, params={"a": 4.0, "b": 15.0})
    assert not evaluer.porte_c7(cand, tous, GRILLE, cfg, CRIT["essais"])[0][0]
    # voisin non évalué
    cand, tous = _voisinage(bons)
    assert not evaluer.porte_c7(cand, tous[:-1], GRILLE, cfg, CRIT["essais"])[0][0]
    # grille non déclarée, trop courte, ou rapport < 1,25
    assert not evaluer.porte_c7(cand, tous, None, cfg, CRIT["essais"])[0][0]
    assert not evaluer.porte_c7(cand, tous, {"a": [4.0, 6.0], "b": [10.0, 15.0]}, cfg, CRIT["essais"])[0][0]
    ok, _ = evaluer.grille_valide({"a": [1.0, 1.25, 1.5625]}, CRIT["essais"])
    assert ok
    ok, _ = evaluer.grille_valide({"a": [1.0, 1.24, 1.54]}, CRIT["essais"])
    assert not ok
    # un voisin d'une AUTRE famille ne compte pas
    cand, tous = _voisinage(bons)
    autre = [Essai(**{**t.__dict__, "famille": "G"}) if i == 1 else t for i, t in enumerate(tous)]
    assert not evaluer.porte_c7(cand, autre, GRILLE, cfg, CRIT["essais"])[0][0]


def test_c8_directionnel_bascule_sur_p():
    cfg = P["C8_directionnel"]
    panier = serie(0.0, n=1500, graine=21, std=0.02)
    bruit = serie(0.0, n=1500, graine=22, std=0.01)

    def reussit(delta: float) -> bool:
        return evaluer.porte_c8_directionnel(panier + bruit + delta, panier, cfg)[0]

    assert not reussit(0.0)
    d = bascule(reussit, 0.0, 0.003, n=25)
    assert reussit(d * 1.02) and not reussit(d * 0.98)
    _, p, seuil = evaluer.porte_c8_directionnel(panier + bruit + d * 1.02, panier, cfg)
    assert seuil == 0.05 and p <= 0.05 + 1e-9
    assert not evaluer.porte_c8_directionnel(panier, None, cfg)[0]  # panier absent : échec


def test_c8_couvert_alpha_et_beta():
    cfg = P["C8_couvert"]
    rng = np.random.default_rng(3)
    idx = pd.date_range("2020-01-01", periods=2000)
    x = pd.Series(rng.normal(0, 0.02, 2000), index=idx)
    u = pd.Series(rng.normal(0, 0.003, 2000), index=idx)

    def t_ok(alpha: float) -> bool:
        return evaluer.porte_c8_couvert(alpha + 0.1 * x + u, x, cfg)[0]

    assert not t_ok(0.0)
    a = bascule(t_ok, 0.0, 0.002, n=30)
    assert t_ok(a * 1.01) and not t_ok(a * 0.99)
    # bêta : alpha confortable, |bêta| juste sous / au-dessus de 0,3 (positif et négatif)
    for signe in (1, -1):
        assert evaluer.porte_c8_couvert(0.003 + signe * 0.29 * x + u, x, cfg)[0]
        assert not evaluer.porte_c8_couvert(0.003 + signe * 0.31 * x + u, x, cfg)[0]


def test_c9_causalite():
    cfg = P["C9_causalite"]
    ok = RapportCausalite(20, 3, 0.4, 1e-9)
    assert evaluer.porte_c9(ok, cfg)[0]
    assert not evaluer.porte_c9(RapportCausalite(20, 3, 0.4, 1.0001e-9), cfg)[0]  # tolérance 1e-9
    assert not evaluer.porte_c9(RapportCausalite(20, 3, 0.39, 0.0), cfg)[0]  # 40 % d'heures non pleines
    assert not evaluer.porte_c9(RapportCausalite(19, 3, 0.5, 0.0), cfg)[0]
    assert not evaluer.porte_c9(RapportCausalite(20, 2, 0.5, 0.0), cfg)[0]
    assert not evaluer.porte_c9(RapportCausalite(20, 3, 0.5, 0.0, invariances_ok=False), cfg)[0]
    assert not evaluer.porte_c9(RapportCausalite(20, 3, 0.5, float("nan")), cfg)[0]
    assert not evaluer.porte_c9(None, cfg)[0]


def test_c11_extremes_bascule():
    cfg = P["C11_extremes"]
    n = T_PROTOCOLE

    def porte(sharpe_base: float):
        return evaluer.porte_c11(serie(sharpe_base, n=n, graine=9), cfg)

    # le retrait des 24 meilleurs jours coûte environ 0,5 de Sharpe : la porte bascule autour de 1,0
    assert not porte(0.8)[0]
    assert porte(2.0)[0]
    b = bascule(lambda x: porte(x)[0], 0.8, 2.0, n=40)
    assert porte(b * 1.01)[0] and not porte(b * 0.99)[0]
    # seuil du premier palier : max(0,5 ; 0,5 x Sharpe complet)
    assert porte(0.8)[2][0] == pytest.approx(0.5)
    assert porte(5.0)[2][0] == pytest.approx(2.5)
    # second palier : sous 0 après retrait de 2 %, même si le premier palier passe
    nulle = serie(0.0, n=n, graine=9)
    r = nulle.copy()
    r.iloc[np.arange(40) * 50 + 3] += 0.05  # 40 jours (> 1 % mais < 2 %), 24 retirés laissent un Sharpe positif
    ok, (_, s2), _ = evaluer.porte_c11(r, cfg)
    assert s2 < 0.5 * stats.sharpe(r) and not ok


def test_c12_cout_et_rotation():
    cfg = P["C12_couts"]
    n = 365 * 4
    idx = pd.date_range("2020-01-01", periods=n)
    brut = pd.Series(0.001, index=idx)

    def porte(cout_jour: float, rot_annuelle: float, classe="directionnel"):
        return evaluer.porte_c12(
            brut, pd.Series(cout_jour, index=idx), pd.Series(rot_annuelle / 365, index=idx), classe, cfg, CRIT["classes"]
        )

    assert porte(0.00049, 10)[0] and porte(0.0005, 10)[0]
    assert not porte(0.00051, 10)[0]
    assert porte(0.0001, 15)[0] and not porte(0.0001, 15.01)[0]
    assert porte(0.0001, 40, "couvert")[0] and not porte(0.0001, 40.01, "couvert")[0]
    # rendement brut nul ou négatif : échec
    z = pd.Series(0.0, index=idx)
    assert not evaluer.porte_c12(z, z, z, "directionnel", cfg, CRIT["classes"])[0]


def test_c13_moities():
    cfg = P["C13_moities"]
    n = 400

    def deux(m1: float, m2: float) -> pd.Series:
        a = serie(0.0, n=n // 2, graine=1, std=0.01) + m1
        b = serie(0.0, n=n // 2, graine=2, std=0.01) + m2
        return pd.concat([a, b]).set_axis(pd.date_range("2020-01-01", periods=n))

    assert evaluer.porte_c13(deux(1e-5, 1e-5), cfg)[0]
    assert not evaluer.porte_c13(deux(1e-5, -1e-5), cfg)[0]
    assert not evaluer.porte_c13(deux(-1e-5, 1e-5), cfg)[0]
    assert not evaluer.porte_c13(deux(-1e-5, -1e-5), cfg)[0]


def test_c14_materialite():
    cfg = P["C14_materialite"]
    idx = pd.date_range("2020-01-01", periods=730)
    assert evaluer.porte_c14(pd.Series(1.0401 ** (1 / 365) - 1, index=idx), cfg)[0]
    assert not evaluer.porte_c14(pd.Series(1.0399 ** (1 / 365) - 1, index=idx), cfg)[0]


def test_c15_sharpe_strictement_positif():
    cfg, c6 = P["C15_arene"], P["C6_drawdown_max"]
    pos = SimpleNamespace(rendements=serie(0.01, n=300))
    neg = SimpleNamespace(rendements=serie(-0.01, n=300))
    nul = SimpleNamespace(rendements=pd.Series(0.0, index=pd.date_range('2020-01-01', periods=300)))
    assert evaluer.porte_c15(pos, "directionnel", cfg, c6)[0]
    assert not evaluer.porte_c15(neg, "directionnel", cfg, c6)[0]
    assert not evaluer.porte_c15(nul, "directionnel", cfg, c6)[0]
    assert not evaluer.porte_c15(None, "directionnel", cfg, c6)[0]


@pytest.mark.parametrize(("classe", "lim"), [("directionnel", 0.585), ("couvert", 0.26)])
def test_c15_drawdown_juste_sous_et_sur_la_limite(classe, lim):
    cfg, c6 = P["C15_arene"], P["C6_drawdown_max"]
    base = pd.Series(0.002, index=pd.date_range("2020-01-01", periods=3000))

    def porte(dd: float):
        s = base.copy()
        s.iloc[100] = -dd
        return evaluer.porte_c15(SimpleNamespace(rendements=s), classe, cfg, c6)

    ok, (sh, _), seuil = porte(lim - 0.002)
    assert sh > 0 and ok and seuil[1] == pytest.approx(lim)
    assert not porte(lim + 0.002)[0]


def test_c16_hors_univers():
    cfg = P["C16_hors_univers"]

    def d(n_pos: int, n_neg: int, n_none: int = 0):
        out = {f"P{i}": SimpleNamespace(net=serie(1.0, graine=i)) for i in range(n_pos)}
        out.update({f"N{i}": SimpleNamespace(net=serie(-1.0, graine=i)) for i in range(n_neg)})
        out.update({f"X{i}": None for i in range(n_none)})
        return out

    assert evaluer.porte_c16(d(6, 4), cfg)[0]  # 60 % exactement
    assert not evaluer.porte_c16(d(5, 4), cfg)[0]  # 55,6 %
    assert evaluer.porte_c16(d(3, 2, n_none=15), cfg)[0]  # non applicable : hors du dénominateur
    assert not evaluer.porte_c16(d(0, 0, n_none=20), cfg)[0]
    assert not evaluer.porte_c16({}, cfg)[0] and not evaluer.porte_c16(None, cfg)[0]
    assert evaluer.porte_c16(d(6, 4), cfg)[1][1:] == (10, 10)


# ----------------------------------------------------------------------------- évaluateur complet
IDX = pd.date_range("2020-01-01", "2026-06-30")


def _candidat_parfait(classe: str = "directionnel"):
    n = len(IDX)

    def un(params, graine, sharpe=2.9):
        net = serie(sharpe, n=n, graine=graine, std=0.01, index=IDX)
        rot = pd.Series(10.0 / 365, index=IDX)
        couts = rot * 0.006
        return Essai(f"{params}", "F", classe, params, net, net - 0.00005, net + couts, rot, couts)

    cand = un({"a": 6.0, "b": 15.0}, 100)
    voisins = [
        un({"a": 4.0, "b": 15.0}, 101),
        un({"a": 9.0, "b": 15.0}, 102),
        un({"a": 6.0, "b": 10.0}, 103),
        un({"a": 6.0, "b": 22.5}, 104),
    ]
    kw = {
        "tous_les_resultats": [cand, *voisins],
        "criteres": CRIT,
        "grille_fiche": GRILLE,
        "panier": serie(0.0, n=n, graine=200, std=0.02, index=IDX),
        "resultats_arene": SimpleNamespace(rendements=serie(1.0, n=n, graine=201, index=IDX)),
        "resultats_controle": {f"S{i}": SimpleNamespace(net=serie(0.8, n=n, graine=300 + i, index=IDX)) for i in range(10)},
        "causalite": RapportCausalite(20, 3, 0.45, 0.0),
    }
    return cand, kw


def test_candidat_parfait_passe_tout():
    cand, kw = _candidat_parfait()
    v = evaluer.evaluer_candidat(cand, **kw)
    assert set(v.portes) == {"C1", "C5", "C6", "C7", "C8", "C9", "C11", "C12", "C13", "C14", "C15", "C16"}
    assert set(v.coherence) == {"C2", "C3", "C4", "C10"}
    assert v.passe, v.echecs()
    assert v.details["C1"]["N"] == 726  # N fixé, jamais le N courant
    assert v.details["C1"]["V"] >= 1 / (v.details["T"] - 1)


def test_candidat_couvert_utilise_la_branche_alpha_beta():
    cand, kw = _candidat_parfait("couvert")
    # le candidat de test est décorrélé du panier avec un Sharpe élevé : alpha t élevé, bêta ~ 0
    v = evaluer.evaluer_candidat(cand, **kw)
    t, beta = v.portes["C8"][1]
    assert t > 2 and abs(beta) < 0.3 and v.portes["C8"][0]
    assert v.portes["C6"][2] == 0.20


def test_chaque_porte_peut_echouer_seule():
    cand, kw = _candidat_parfait()
    n = len(IDX)
    assert evaluer.evaluer_candidat(cand, **{**kw, "causalite": None}).echecs() == ["C9"]
    assert evaluer.evaluer_candidat(cand, **{**kw, "panier": None}).echecs() == ["C8"]
    assert evaluer.evaluer_candidat(cand, **{**kw, "resultats_arene": None}).echecs() == ["C15"]
    assert evaluer.evaluer_candidat(cand, **{**kw, "resultats_controle": None}).echecs() == ["C16"]
    assert evaluer.evaluer_candidat(cand, **{**kw, "grille_fiche": None}).echecs() == ["C7"]
    # classe couvert avec le même candidat : seule la rotation (40) et le drawdown (20 %) changent le verdict
    mauvais = Essai(**{**cand.__dict__, "rotation": pd.Series(16.0 / 365, index=IDX)})
    assert evaluer.evaluer_candidat(mauvais, **{**kw, "tous_les_resultats": [mauvais, *kw["tous_les_resultats"][1:]]}).echecs() == ["C12"]
    # série nette dégradée : le Sharpe passe sous C2 et le DSR sous C1
    faible = serie(0.4, n=n, graine=100, index=IDX)
    c = Essai(**{**cand.__dict__, "net": faible, "net_stress": faible})
    ech = evaluer.evaluer_candidat(c, **{**kw, "tous_les_resultats": [c, *kw["tous_les_resultats"][1:]]}).echecs()
    assert "C1" in ech and "C2" in ech and "C3" in ech


def test_stress_et_bootstrap_de_coherence():
    cand, kw = _candidat_parfait()
    pire = serie(-0.1, n=len(IDX), graine=100, index=IDX)
    c = Essai(**{**cand.__dict__, "net_stress": pire})
    v = evaluer.evaluer_candidat(c, **{**kw, "tous_les_resultats": [c, *kw["tous_les_resultats"][1:]]})
    assert v.echecs() == ["C4"] and not v.passe


def test_classe_inconnue_refusee():
    cand, kw = _candidat_parfait()
    mauvais = Essai(**{**cand.__dict__, "classe": "neutre"})
    with pytest.raises(ValueError):
        evaluer.evaluer_candidat(mauvais, **kw)


def test_accepte_l_objet_criteres_du_projet():
    config = pytest.importorskip("recherche.config")
    crit = config.charger_criteres()
    cand, kw = _candidat_parfait()
    assert evaluer.evaluer_candidat(cand, **{**kw, "criteres": crit}).passe


# ----------------------------------------------------------------------------- sélection
def _paire_correlee(rho: float, n: int = 500):
    rng = np.random.default_rng(4)
    z1, z2 = rng.normal(size=n), rng.normal(size=n)
    z1 = (z1 - z1.mean()) / z1.std()
    z2 = z2 - z2.mean()
    z2 -= (z2 @ z1) / (z1 @ z1) * z1
    z2 /= z2.std()
    idx = pd.date_range("2020-01-01", periods=n)
    return pd.Series(z1, index=idx), pd.Series(rho * z1 + math.sqrt(1 - rho**2) * z2, index=idx)


def test_selection_correlation_juste_sous_et_au_dessus():
    for rho, garde in ((0.69, True), (0.71, False)):
        a, b = _paire_correlee(rho)
        s = selection.selectionner([selection.Candidat("b", 0.96, b), selection.Candidat("a", 0.99, a)], CRIT)
        assert s.retenus == (("a", "b") if garde else ("a",))
        assert s.correlations[("a", "b")] == pytest.approx(rho, abs=1e-9)
        if not garde:
            assert "b" in s.ecartes and "corrélation" in s.ecartes["b"]


def test_selection_trois_au_plus_classes_par_dsr():
    rng = np.random.default_rng(8)
    idx = pd.date_range("2020-01-01", periods=600)
    cs = [selection.Candidat(f"c{i}", 0.951 + 0.001 * i, pd.Series(rng.normal(size=600), index=idx)) for i in range(5)]
    s = selection.selectionner(cs, CRIT)
    assert s.retenus == ("c4", "c3", "c2")
    assert set(s.ecartes) == {"c1", "c0"}
    assert s.p_au_moins_un_non_refute == pytest.approx(1 - (1 - selection.P_NON_REFUTE_H0_DEFAUT) ** 3)
    assert selection.selectionner([], CRIT).retenus == ()
    assert selection.proba_au_moins_un_non_refute(0) == 0.0


# ----------------------------------------------------------------------------- replay arène
PAIRES = CRIT["donnees"]["univers_arene"]


def _marche(n=250, graine=1):
    rng = np.random.default_rng(graine)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    px = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.02, (n, 6)), 0)), index=idx, columns=PAIRES)
    return px


def test_politique_strategie_passe_validate_policy():
    from arene.risk.policy import load_policy, validate_policy

    pol = load_policy(POLICY_PATH)
    validate_policy(pol)
    assert len(pol.sha256) == 64
    assert set(pol.symbols) == {symbole_arene(s) for s in PAIRES}
    assert (pol.max_order_bp, pol.max_position_bp, pol.max_exposure_bp) == (10000, 10000, 10000)
    assert pol.max_trades_per_day == 12


def test_replay_poids_constants_retrouve_la_comptabilite_independante():
    px = _marche()
    w = pd.DataFrame(1 / 6, index=px.index, columns=PAIRES)
    res = rejouer(w, px)
    assert res.rejets == {} and res.n_ordres == res.n_fills > 0
    # comptabilité indépendante : rendement brut du panier rééquilibré chaque jour, coût 60 pb x rotation
    r = px.pct_change().fillna(0.0).to_numpy()
    wa = np.full(6, 1 / 6)
    att = []
    w_der = np.zeros(6)
    for t in range(len(px)):
        rb = float(w_der @ r[t])
        rot = float(np.abs(wa - w_der).sum())
        net = (1 + rb) * (1 - 0.006 * rot) / 1 - 1 if t else -0.006 * rot
        att.append(net)
        w_der = wa * (1 + r[t]) / (1 + float(wa @ r[t]))
    # le jour 0 achète 100 % ; ensuite la dérive est ré-équilibrée : rotation indépendante ci-dessus (Δw jour t
    # = poids cible - poids dérivé à la veille, appliqué après le rendement du jour t)
    ecart = (res.rendements.to_numpy() - np.array(att))
    assert abs(ecart.mean()) < 2e-5 and np.abs(ecart).max() < 1e-3


def test_replay_cout_d_un_aller_retour_vaut_60_bp_par_rotation():
    px = _marche(n=4, graine=2)
    px.iloc[:] = 100.0  # prix constants : seul le coût agit
    w = pd.DataFrame(0.0, index=px.index, columns=PAIRES)
    w.iloc[0, 0] = 1.0  # achat 100 % le jour 0 ; revente totale le jour 2
    w.iloc[1, 0] = 1.0
    res = rejouer(w, px)
    assert res.rendements.iloc[0] == pytest.approx(-0.0060, abs=2e-4)  # achat : 60 pb
    assert res.rendements.iloc[1] == pytest.approx(0.0, abs=1e-6)
    assert res.rendements.iloc[2] == pytest.approx(-0.0060, abs=2e-4)  # vente : 60 pb
    assert res.rendements.iloc[3] == 0.0


def test_replay_passe_vraiment_par_riskd():
    px = _marche(n=30)
    w = pd.DataFrame(0.0, index=px.index, columns=PAIRES)
    w[PAIRES[0]] = 1.0  # 100 % sur une paire
    assert rejouer(w, px).rejets == {}
    # politique resserrée (copie temporaire) : riskd REJETTE, le replay compte et n'exécute pas
    texte = POLICY_PATH.read_text(encoding="utf-8").replace("max_position_bp = 10000", "max_position_bp = 5000")
    texte = texte.replace("max_order_bp    = 10000", "max_order_bp    = 5000")
    tmp = Path(__file__).parent / "_policy_tmp.toml"
    try:
        tmp.write_text(texte, encoding="utf-8")
        res = rejouer(w, px, policy_path=tmp)
    finally:
        tmp.unlink(missing_ok=True)
    assert res.rejets.get("MAX_ORDER_SIZE", 0) > 0
    assert (res.rendements == 0.0).all() and res.n_fills == 0
    assert all(len(c) > 0 for _, _, c in res.ordres_rejetes)


def test_replay_refuse_les_poids_invalides_et_les_index_differents():
    px = _marche(n=10)
    w = pd.DataFrame(0.2, index=px.index, columns=PAIRES)  # somme 1,2
    with pytest.raises(ValueError, match="poids hors bornes"):
        rejouer(w, px)
    w2 = pd.DataFrame(0.1, index=px.index, columns=PAIRES)
    with pytest.raises(ValueError, match="index"):
        rejouer(w2, px.iloc[1:])
    with pytest.raises(ValueError, match="USDT"):
        symbole_arene("BTCEUR")
    assert symbole_arene("LINKUSDT") == "LINK/EUR"


def test_replay_paire_sans_prix_est_ignoree():
    px = _marche(n=20)
    px.iloc[:5, 0] = np.nan  # BTC pas encore cotée
    w = pd.DataFrame(1 / 6, index=px.index, columns=PAIRES)
    res = rejouer(w, px)
    assert res.rejets == {} and np.isfinite(res.rendements).all()
