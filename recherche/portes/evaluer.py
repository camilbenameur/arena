"""Évaluation des portes C1-C16 d'un candidat (PROTOCOLE §6, seuils de criteres.yaml).

Aucun LLM, aucun calcul de performance ailleurs que dans le moteur : ce module reçoit les SÉRIES
QUOTIDIENNES produites par le moteur (net, net stressé, brut, rotation, coûts) et leur applique les
critères. Une porte non évaluable (donnée absente, NaN) ÉCHOUE ; rien n'est jamais arrondi en faveur du
candidat.

`criteres` : objet `recherche.config.Criteres` ou dict de la racine du YAML (accès par clé uniquement).

Entrée d'un essai : tout objet ayant les attributs de `Essai` (le moteur peut fournir le sien).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from recherche.portes import dsr as dsr_mod
from recherche.portes import stats

Porte = tuple[bool, Any, Any]  # (réussie, valeur mesurée, seuil)


@dataclass(frozen=True)
class Essai:
    """Séries quotidiennes (index = dates UTC de la fenêtre d'évaluation) d'un essai.

    net, net_stress, brut : rendements quotidiens sur le capital immobilisé (marge perp comprise) ;
    rotation : somme quotidienne des |Δw| (chaque jambe comptée) ; couts : coût quotidien payé en part du
    capital (net = brut - couts, hors funding qui est dans brut). `net_stress` : coûts x2.
    """

    id: str
    famille: str
    classe: str  # "directionnel" | "couvert"
    params: Mapping[str, float]
    net: pd.Series
    net_stress: pd.Series
    brut: pd.Series
    rotation: pd.Series
    couts: pd.Series
    univers: str = "principal"


@dataclass(frozen=True)
class RapportCausalite:
    """Résumé du test C9 sur données synthétiques (produit par le moteur).

    ecart_max : plus grand écart absolu entre la sortie tronquée à la coupure et la sortie complète sur
    les jours antérieurs, toutes coupures confondues ; part_heure_non_pleine : part des coupures dont
    l'instant n'est pas une heure pleine UTC.
    """

    n_aleatoires: int
    n_fixes: int
    part_heure_non_pleine: float
    ecart_max: float
    invariances_ok: bool = True  # permutation de colonnes, échelle prix/volume (§3)


@dataclass(frozen=True)
class Verdict:
    portes: dict[str, Porte]
    coherence: dict[str, Porte]
    passe: bool
    details: dict[str, Any] = field(default_factory=dict)

    def echecs(self) -> list[str]:
        return [k for k, (ok, _, _) in {**self.portes, **self.coherence}.items() if not ok]


# ----------------------------------------------------------------------------- utilitaires
def section(criteres: Any, nom: str):
    """Section `nom` de `criteres` : dict du YAML (accès par clé) ou objet `Criteres` (accès par attribut)."""
    if isinstance(criteres, Mapping):
        return criteres[nom]
    return getattr(criteres, nom)


def _finite(x) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _ok_ge(valeur, seuil) -> bool:
    return _finite(valeur) and valeur >= seuil


def _ok_gt(valeur, seuil) -> bool:
    return _finite(valeur) and valeur > seuil


def _ok_le(valeur, seuil) -> bool:
    return _finite(valeur) and valeur <= seuil


# ----------------------------------------------------------------------------- C1
def variance_de_classe(classe: str, tous: Sequence[Any], T: int,
                       sr_jours_recherche: Mapping[str, Mapping[str, Sequence[float]]] | None = None) -> float:
    """V de la classe (PROTOCOLE §5 durci) : max(1/(T-1), variance intra-famille moyenne pondérée, variance
    de l'ensemble des sr_jour de la classe).

    `sr_jours_recherche` : classe -> famille -> sr_jour de TOUS les essais de recherche (univers principal)
    du journal, toutes vagues et reprises comprises (`vague.sr_jours_du_journal`). Sans lui (tests, usage
    isolé), on prend les essais de `tous` de la classe, univers principal."""
    if sr_jours_recherche is not None:
        return dsr_mod.variance_classe(dict(sr_jours_recherche.get(classe, {})), T)
    par_famille: dict[str, list[float]] = {}
    for r in tous:
        if r.classe != classe or getattr(r, "univers", "principal") != "principal":
            continue
        s = stats.sr_jour(r.net)
        if _finite(s):
            par_famille.setdefault(r.famille, []).append(s)
    return dsr_mod.variance_classe(par_famille, T)


def porte_c1(net, N: int, V: float, seuil: float) -> tuple[Porte, dict]:
    T = len(net)
    s = stats.sr_jour(net)
    sk, ku = stats.moments(net)
    try:
        d = dsr_mod.dsr_proba(s, T, sk, ku, N, V)
    except ValueError:
        d = float("nan")
    return (_ok_ge(d, seuil), d, seuil), {"N": N, "V": V, "T": T, "sr_jour": s, "skew": sk, "kurt": ku,
                                           "sr_etoile": dsr_mod.sr_etoile(V, N)}


# ----------------------------------------------------------------------------- C5
def porte_c5(net: pd.Series, cfg) -> Porte:
    """Années civiles : aucune sous `sharpe_min_par_annee`, au moins `annees_positives_min` positives.

    Une année à rendement exactement nul (stratégie à plat toute l'année : écart-type nul, Sharpe NaN) est
    traitée comme « non positive et non sous −1 » (Sharpe 0,0) : elle ne fait pas échouer C5 à elle seule mais
    ne compte pas parmi les années positives. Une année absente (moins de 2 jours) reste un échec."""
    annees = list(cfg["annees"])
    sh = stats.sharpe_par_annee(net, annees, plat_vaut_zero=True)
    vals = [sh[a] for a in annees]
    if not all(_finite(v) for v in vals):
        return (False, sh, dict(cfg))
    ok = all(v >= cfg["sharpe_min_par_annee"] for v in vals) and (
        sum(1 for v in vals if v > 0) >= cfg["annees_positives_min"]
    )
    return (ok, sh, {"sharpe_min": cfg["sharpe_min_par_annee"], "positives_min": cfg["annees_positives_min"]})


# ----------------------------------------------------------------------------- C6
def porte_c6(net, classe: str, cfg) -> Porte:
    dd = stats.drawdown(net)
    seuil = cfg[classe]
    return (_ok_le(dd, seuil), dd, seuil)


# ----------------------------------------------------------------------------- C7
def grille_valide(grille: Mapping[str, Sequence[float]], cfg_essais) -> tuple[bool, str]:
    """Au moins 3 valeurs par paramètre, rapport >= 1,25 entre valeurs voisines (grille géométrique)."""
    gmin = cfg_essais["grille"]["valeurs_min_par_parametre"]
    rmin = cfg_essais["grille"]["rapport_min_entre_voisines"]
    if not grille:
        return False, "grille vide"
    for p, vals in grille.items():
        v = list(vals)
        if len(v) < gmin:
            return False, f"{p} : {len(v)} valeurs < {gmin}"
        if any(not _finite(x) or x <= 0 for x in v):
            return False, f"{p} : valeurs non strictement positives"
        v = sorted(v)
        for a, b in itertools.pairwise(v):
            if b / a < rmin - 1e-12:
                return False, f"{p} : rapport {b / a:.4f} < {rmin}"
    return True, ""


def _meme_point(p: Mapping[str, float], q: Mapping[str, float]) -> bool:
    return set(p) == set(q) and all(math.isclose(float(p[k]), float(q[k]), rel_tol=1e-9, abs_tol=1e-12) for k in p)


#: Un voisin dont la série nette est corrélée à plus de CORR_VOISIN_IDENTIQUE avec celle du candidat ET dont
#: la rotation est identique à TOL_ROTATION_IDENTIQUE près est le même comportement (paramètre ignoré).
CORR_VOISIN_IDENTIQUE = 0.999
TOL_ROTATION_IDENTIQUE = 1e-9
#: C7 exige au moins ce nombre de voisins distincts.
VOISINS_DISTINCTS_MIN = 2


def _voisin_identique(candidat: Any, voisin: Any) -> bool:
    """Vrai si `voisin` ne se distingue pas de `candidat` : corrélation des rendements nets > 0,999 et
    rotation égale à 1e-9 près (alignement par date). Série constante : identique si les valeurs sont égales."""
    a, b = candidat.net.align(voisin.net, join="inner")
    ra, rb = candidat.rotation.align(voisin.rotation, join="inner")
    if len(a) < 2 or len(ra) < 1:
        return False
    if float(np.abs(ra.to_numpy(dtype=float) - rb.to_numpy(dtype=float)).max()) > TOL_ROTATION_IDENTIQUE:
        return False
    va, vb = a.to_numpy(dtype=float), b.to_numpy(dtype=float)
    if va.std() == 0.0 or vb.std() == 0.0:
        return bool(np.allclose(va, vb, rtol=0.0, atol=1e-15))
    return float(np.corrcoef(va, vb)[0, 1]) > CORR_VOISIN_IDENTIQUE


def porte_c7(
    candidat: Any,
    tous: Sequence[Any],
    grille: Mapping[str, Sequence[float]] | None,
    cfg,
    cfg_essais,
) -> tuple[Porte, dict]:
    seuil = {"part_voisins_min": cfg["part_voisins_min"], "ratio": cfg["ratio_sharpe_voisin_min"],
             "sharpe_voisin_min": cfg["sharpe_voisin_min"]}
    if not grille:
        return (False, None, seuil), {"raison": "grille non déclarée"}
    ok_grille, raison = grille_valide(grille, cfg_essais)
    if not ok_grille:
        return (False, None, seuil), {"raison": f"grille invalide : {raison}"}
    axes = {p: sorted(float(x) for x in v) for p, v in grille.items()}
    pt = dict(candidat.params)
    pos = {}
    for p, vals in axes.items():
        if p not in pt:
            return (False, None, seuil), {"raison": f"paramètre {p} absent du candidat"}
        idx = [i for i, x in enumerate(vals) if math.isclose(x, float(pt[p]), rel_tol=1e-9, abs_tol=1e-12)]
        if not idx:
            return (False, None, seuil), {"raison": f"{p}={pt[p]} hors grille"}
        if idx[0] in (0, len(vals) - 1):
            return (False, None, seuil), {"raison": f"{p} au bord de la grille"}
        pos[p] = idx[0]
    s_cand = stats.sharpe(candidat.net)
    seuil_voisin = max(cfg["ratio_sharpe_voisin_min"] * s_cand, cfg["sharpe_voisin_min"])
    voisins, bons, identiques = [], 0, []
    pool = [r for r in tous if r.famille == candidat.famille and getattr(r, "univers", "principal") == "principal"]
    for p, vals in axes.items():
        for d in (-1, 1):
            q = dict(pt)
            q[p] = vals[pos[p] + d]
            trouve = next((r for r in pool if _meme_point(r.params, q)), None)
            if trouve is None:
                return (False, None, seuil), {"raison": f"voisin non évalué : {q}"}
            s = stats.sharpe(trouve.net)
            if not _finite(s):
                return (False, None, seuil), {"raison": f"voisin non évaluable : {q}"}
            if _voisin_identique(candidat, trouve):
                identiques.append(q)  # paramètre sans effet : ce n'est pas un voisin distinct
                continue
            voisins.append((q, s))
            bons += s >= seuil_voisin
    det = {"voisins": voisins, "voisins_identiques": identiques, "seuil_sharpe_voisin": seuil_voisin}
    if len(voisins) < VOISINS_DISTINCTS_MIN:
        det["raison"] = f"{len(voisins)} voisin(s) distinct(s) < {VOISINS_DISTINCTS_MIN} (paramètres sans effet ?)"
        return (False, None, seuil), det
    part = bons / len(voisins)
    ok = _finite(s_cand) and part >= cfg["part_voisins_min"]
    return (ok, part, seuil), det


# ----------------------------------------------------------------------------- C8
def porte_c8_directionnel(net: pd.Series, panier: pd.Series | None, cfg) -> Porte:
    seuil = cfg["p_unilateral_max"]
    if panier is None:
        return (False, None, seuil)
    a, b = net.align(panier, join="inner")
    if len(a) < 2 * cfg["bootstrap_apparie_blocs_jours"]:
        return (False, None, seuil)
    p = stats.bootstrap_apparie(
        a, b, cfg["bootstrap_apparie_blocs_jours"], cfg["replications"], cfg["graine"]
    )["p"]
    return (_ok_le(p, seuil), p, seuil)


def porte_c8_couvert(net: pd.Series, panier: pd.Series | None, cfg) -> Porte:
    seuil = (cfg["alpha_t_newey_west_min"], cfg["beta_abs_max"])
    if panier is None:
        return (False, None, seuil)
    a, b = net.align(panier, join="inner")
    if len(a) < 3 * cfg["retards"]:
        return (False, None, seuil)
    reg = stats.regression_alpha_beta(a, b, cfg["retards"])
    ok = _ok_ge(reg["t_alpha"], seuil[0]) and _finite(reg["beta"]) and abs(reg["beta"]) <= seuil[1]
    return (ok, (reg["t_alpha"], reg["beta"]), seuil)


# ----------------------------------------------------------------------------- C9
def porte_c9(rapport: RapportCausalite | None, cfg) -> Porte:
    seuil = {"aleatoires": cfg["coupures_aleatoires"], "fixes": cfg["coupures_fixes"],
             "part_non_pleine_min": cfg["part_heure_non_pleine_min"], "tolerance": cfg["tolerance"]}
    if rapport is None:
        return (False, None, seuil)
    ok = (
        rapport.n_aleatoires >= cfg["coupures_aleatoires"]
        and rapport.n_fixes >= cfg["coupures_fixes"]
        and _ok_ge(rapport.part_heure_non_pleine, cfg["part_heure_non_pleine_min"])
        and _ok_le(rapport.ecart_max, cfg["tolerance"])
        and bool(rapport.invariances_ok)
    )
    return (ok, rapport.ecart_max, seuil)


# ----------------------------------------------------------------------------- C11
def porte_c11(net: pd.Series, cfg) -> Porte:
    s0 = stats.sharpe(net)
    r1, _ = stats.retirer_meilleurs_jours(net, cfg["retrait_part_1"])
    r2, _ = stats.retirer_meilleurs_jours(net, cfg["retrait_part_2"])
    s1, s2 = stats.sharpe(r1), stats.sharpe(r2)
    min1 = max(0.5, 0.5 * s0) if _finite(s0) else float("nan")
    ok = _ok_ge(s1, min1) and _ok_gt(s2, cfg["sharpe_min_apres_2"])
    return (ok, (s1, s2), (min1, cfg["sharpe_min_apres_2"]))


# ----------------------------------------------------------------------------- C12
def porte_c12(brut: pd.Series, couts: pd.Series, rotation: pd.Series, classe: str, cfg, cfg_classes) -> Porte:
    cout_an = float(couts.sum() / (len(couts) / stats.JOURS_AN))
    brut_an = float(brut.sum() / (len(brut) / stats.JOURS_AN))
    rot = stats.rotation_annuelle(rotation)
    rot_max = cfg_classes[classe]["rotation_annuelle_max"]
    ratio = cout_an / brut_an if brut_an > 0 else float("inf")
    ok = _ok_le(ratio, cfg["cout_sur_rendement_brut_max"]) and _ok_le(rot, rot_max)
    return (ok, (ratio, rot), (cfg["cout_sur_rendement_brut_max"], rot_max))


# ----------------------------------------------------------------------------- C13
def porte_c13(net: pd.Series, cfg) -> Porte:
    a, b = stats.sharpe_moities(net)
    seuil = cfg["sharpe_min_chaque_moitie"]
    return (_ok_gt(a, seuil) and _ok_gt(b, seuil), (a, b), seuil)


# ----------------------------------------------------------------------------- C14
def porte_c14(net: pd.Series, cfg) -> Porte:
    r = stats.rendement_annualise(net)
    seuil = cfg["rendement_annualise_net_min"]
    return (_ok_ge(r, seuil), r, seuil)


# ----------------------------------------------------------------------------- C15
def _sharpe_dd(res: Any) -> tuple[float, float]:
    """Sharpe et drawdown d'un résultat : objet à `.net` (Essai) ou à `.rendements` (replay_arene)."""
    serie = getattr(res, "net", None)
    if serie is None:
        serie = getattr(res, "rendements", None)
    if serie is None:
        return float("nan"), float("nan")
    return stats.sharpe(serie), stats.drawdown(serie)


def porte_c15(res_arene: Any | None, classe: str, cfg, cfg_c6) -> Porte:
    seuil = (cfg["sharpe_min"], cfg["drawdown_max_facteur_C6"] * cfg_c6[classe])
    if res_arene is None:
        return (False, None, seuil)
    s, dd = _sharpe_dd(res_arene)
    return (_ok_gt(s, seuil[0]) and _ok_le(dd, seuil[1]), (s, dd), seuil)


# ----------------------------------------------------------------------------- C16
#: Marque, dans `res_controle`, un symbole dont la donnée requise par la fiche manque (couvert : perp ;
#: signaux_perp : funding). Il ne compte ni au numérateur ni dans le minimum d'évaluables, mais le dénominateur
#: de C16 reste la taille de l'univers de contrôle.
NON_EVALUABLE = "non_evaluable"
EVALUABLES_MIN_C16 = 10


def porte_c16(res_controle: Mapping[str, Any] | None, cfg, taille_univers: int = 20) -> Porte:
    """C16 : part des symboles de contrôle au Sharpe net > 0 >= `part_symboles_sharpe_positif_min`.

    - Dénominateur FIXE = `taille_univers` (20, `criteres.donnees.univers_controle.taille`), jamais le
      nombre de symboles qui ont tourné.
    - Un symbole absent de `res_controle`, `None` (essai non OK : ERREUR, TIMEOUT, ...) ou de Sharpe NaN
      est un échec (il reste au dénominateur).
    - `NON_EVALUABLE` : donnée requise absente ; ne compte ni au numérateur ni dans le minimum de
      `EVALUABLES_MIN_C16` symboles évaluables (sinon C16 échoue) ; le rapport l'indique.
    Valeur rendue : (part, positifs, evaluables, non_evaluables, taille_univers)."""
    seuil = cfg["part_symboles_sharpe_positif_min"]
    if not res_controle:
        return (False, None, seuil)
    positifs = non_eval = 0
    for res in res_controle.values():
        if isinstance(res, str) and res == NON_EVALUABLE:
            non_eval += 1
            continue
        if res is None:
            continue
        s, _ = _sharpe_dd(res)
        if _finite(s) and s > 0:
            positifs += 1
    evaluables = taille_univers - non_eval
    part = positifs / taille_univers
    valeur = (part, positifs, evaluables, non_eval, taille_univers)
    return (evaluables >= EVALUABLES_MIN_C16 and part >= seuil, valeur, seuil)


# ----------------------------------------------------------------------------- orchestration
def evaluer_candidat(
    resultat: Any,
    tous_les_resultats: Sequence[Any],
    criteres: Any,
    grille_fiche: Mapping[str, Sequence[float]] | None,
    panier: pd.Series | None,
    resultats_arene: Any | None,
    resultats_controle: Mapping[str, Any] | None,
    causalite: RapportCausalite | None = None,
    sr_jours_recherche: Mapping[str, Mapping[str, Sequence[float]]] | None = None,
) -> Verdict:
    """Applique C1-C16 (+ cohérence C2, C3, C4, C10) à `resultat`.

    tous_les_resultats : tous les essais de recherche (V par classe ; voisins C7), `resultat` compris.
    panier : rendements quotidiens du panier équipondéré de l'univers du candidat (fourni par le moteur).
    causalite : sinon `resultat.causalite` ; absent = C9 échoue.
    sr_jours_recherche : sr_jour de tous les essais de recherche du journal (V par classe) ; voir
    `variance_de_classe`. resultats_controle : voir `porte_c16` (dénominateur = taille de l'univers de contrôle).
    """
    c_portes, c_coh = section(criteres, "portes"), section(criteres, "coherence")
    c_essais, c_classes = section(criteres, "essais"), section(criteres, "classes")
    classe = resultat.classe
    if classe not in ("directionnel", "couvert"):
        raise ValueError(f"classe inconnue : {classe!r}")
    net = resultat.net
    T = len(net)

    N = int(c_essais["N_dsr"])
    V = variance_de_classe(classe, tous_les_resultats, T, sr_jours_recherche)
    p1, d1 = porte_c1(net, N, V, c_portes["C1_dsr_min"])
    try:
        d1["dsr_V_commun"] = dsr_mod.dsr_proba(
            d1["sr_jour"], T, d1["skew"], d1["kurt"], N,
            _v_commun(tous_les_resultats, T, sr_jours_recherche),
        )
    except ValueError:
        d1["dsr_V_commun"] = float("nan")

    cc8 = c_portes["C8_directionnel"] if classe == "directionnel" else c_portes["C8_couvert"]
    p8 = (
        porte_c8_directionnel(net, panier, cc8)
        if classe == "directionnel"
        else porte_c8_couvert(net, panier, cc8)
    )
    p7, d7 = porte_c7(resultat, tous_les_resultats, grille_fiche, c_portes["C7_voisinage"], c_essais)
    rapport = causalite if causalite is not None else getattr(resultat, "causalite", None)

    portes: dict[str, Porte] = {
        "C1": p1,
        "C5": porte_c5(net, c_portes["C5_annees"]),
        "C6": porte_c6(net, classe, c_portes["C6_drawdown_max"]),
        "C7": p7,
        "C8": p8,
        "C9": porte_c9(rapport, c_portes["C9_causalite"]),
        "C11": porte_c11(net, c_portes["C11_extremes"]),
        "C12": porte_c12(resultat.brut, resultat.couts, resultat.rotation, classe, c_portes["C12_couts"], c_classes),
        "C13": porte_c13(net, c_portes["C13_moities"]),
        "C14": porte_c14(net, c_portes["C14_materialite"]),
        "C15": porte_c15(resultats_arene, classe, c_portes["C15_arene"], c_portes["C6_drawdown_max"]),
        "C16": porte_c16(resultats_controle, c_portes["C16_hors_univers"],
                         int(section(criteres, "donnees")["univers_controle"]["taille"])),
    }

    s_net = stats.sharpe(net)
    t_nw = stats.t_newey_west(net, 20)
    s_stress = stats.sharpe(resultat.net_stress)
    c10 = c_coh["C10_bootstrap"]
    p10 = stats.bootstrap_blocs(net, c10["blocs_jours"], c10["replications"], c10["graine"])["p"]
    coherence: dict[str, Porte] = {
        "C2": (_ok_ge(s_net, c_coh["C2_sharpe_net_min"]), s_net, c_coh["C2_sharpe_net_min"]),
        "C3": (_ok_ge(t_nw, c_coh["C3_t_newey_west_min"]), t_nw, c_coh["C3_t_newey_west_min"]),
        "C4": (_ok_gt(s_stress, c_coh["C4_sharpe_stress_min"]), s_stress, c_coh["C4_sharpe_stress_min"]),
        "C10": (_ok_le(p10, c10["p_unilateral_max"]), p10, c10["p_unilateral_max"]),
    }
    details = {"C1": d1, "C7": d7, "sharpe_net": s_net, "T": T}
    passe = all(ok for ok, _, _ in portes.values()) and all(ok for ok, _, _ in coherence.values())
    return Verdict(portes=portes, coherence=coherence, passe=passe, details=details)


def _v_commun(tous: Sequence[Any], T: int,
              sr_jours_recherche: Mapping[str, Mapping[str, Sequence[float]]] | None = None) -> float:
    """V toutes classes confondues (information seulement, PROTOCOLE §5)."""
    par_famille: dict[str, list[float]] = {}
    if sr_jours_recherche is not None:
        for fams in sr_jours_recherche.values():
            for fam, srs in fams.items():
                par_famille.setdefault(fam, []).extend(srs)
        return dsr_mod.variance_classe(par_famille, T)
    for r in tous:
        if getattr(r, "univers", "principal") != "principal":
            continue
        s = stats.sr_jour(r.net)
        if _finite(s):
            par_famille.setdefault(r.famille, []).append(s)
    return dsr_mod.variance_classe(par_famille, T)
