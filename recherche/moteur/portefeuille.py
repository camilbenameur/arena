"""Simulation du portefeuille en quantités (protocole §3) à partir des poids cibles quotidiens.

Chronologie (identique au labo) : les poids décidés à la clôture du jour i s'appliquent au rendement du
jour i+1 ; les coûts de la rotation décidée en i sont imputés au rendement du jour i+1. Tous les tableaux
de sortie sont indexés par le jour du rendement (`jours[j]` = jour dont la clôture termine le rendement).

Rotation (convention `derive`, celle du protocole) : rotation_i = Σ |w_cible_i − w_dérivé_i| avec
w_dérivé_i = w_{i-1} (1 + r_i) / (1 + r_p,i) par jambe (r_p = rendement brut du portefeuille, funding compris).
Convention `cible` (reproduction du labo, E0065) : rotation_i = Σ |w_cible_i − w_cible_{i-1}|.

Classes : `directionnel` (spot seul, w ∈ [0,1], Σw ≤ 1) et `couvert` (short perp ≤ long spot par paire,
capital immobilisé Σ w_spot + marge · Σ w_perp ≤ 1). Toute violation lève `FormePoids` ; jamais de rognage.
Les rendements sont des P&L rapportés au capital total (1) ; `rendements_nets_immobilise` les rapporte au
capital immobilisé du jour (marge perp comprise ; diviseur max(expo_j, expo_{j-1}), voir `diviseur_immobilise`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from recherche.moteur.contrat import TOL_POIDS, FormePoids
from recherche.moteur.panneau import Panneau

CLASSES = ("directionnel", "couvert")


#: Part minimale du long spot qui doit être couverte par le short perp, par paire et par jour (classe couvert).
#: 0,9 dans `recherche-moteur-v1` ; 0 depuis `recherche-moteur-v2` (erratum 5, décision du propriétaire du 12/11/2026) :
#: la couverture partielle est permise, la discipline vient des portes C6 (drawdown <= 20 %) et C8 (|bêta| <= 0,3).
COUVERTURE_MIN = 0.0


def valider_poids(classe: str, i: int, ws: np.ndarray, wp: np.ndarray, deja_cotee: np.ndarray,
                  eligibles_perp: np.ndarray | None, marge: float) -> None:
    """Validation stricte des bornes pour un jour. `deja_cotee` : paire cotée à ce jour ou avant.

    Classe `couvert` : interprétation STRICTE de la définition du protocole §3 (« long spot et short perp sur
    la même paire, avec short perp <= long spot ») : sur chaque paire et chaque jour,
    `COUVERTURE_MIN * poids_spot <= poids_perp <= poids_spot`. Depuis `recherche-moteur-v2`, COUVERTURE_MIN = 0 :
    toute couverture partielle est permise, jamais un short perp supérieur au long spot ; `FORME_POIDS` sinon,
    jamais de rognage.

    Les messages d'erreur ne contiennent aucune valeur issue de la stratégie (canal de sortie) : le jour et la
    règle violée seulement."""
    if classe not in CLASSES:
        raise FormePoids(f"classe inconnue {classe!r}")
    if not (np.isfinite(ws).all() and np.isfinite(wp).all()):
        raise FormePoids(f"jour {i} : poids non finis")
    if ws.min(initial=0.0) < -TOL_POIDS or wp.min(initial=0.0) < -TOL_POIDS:
        raise FormePoids(f"jour {i} : poids négatif")
    if (ws[~deja_cotee] > TOL_POIDS).any():
        raise FormePoids(f"jour {i} : poids sur une paire non cotée")
    if classe == "directionnel":
        if wp.max(initial=0.0) > TOL_POIDS:
            raise FormePoids(f"jour {i} : jambe perp interdite en classe directionnel")
        if ws.sum() > 1.0 + TOL_POIDS:
            raise FormePoids(f"jour {i} : somme des poids > 1")
        return
    if (wp > ws + TOL_POIDS).any():
        raise FormePoids(f"jour {i} : short perp supérieur au long spot")
    if (wp < COUVERTURE_MIN * ws - TOL_POIDS).any():
        raise FormePoids(f"jour {i} : short perp inférieur à la couverture minimale du long spot")
    if eligibles_perp is None:
        if wp.max(initial=0.0) > TOL_POIDS:
            raise FormePoids(f"jour {i} : poids perp sans donnée perp")
    elif (wp[~eligibles_perp] > TOL_POIDS).any():
        raise FormePoids(f"jour {i} : poids perp sur un perpétuel absent")
    if ws.sum() + marge * wp.sum() > 1.0 + TOL_POIDS:
        raise FormePoids(f"jour {i} : capital immobilisé > 1")


def diviseur_immobilise(exposition: np.ndarray) -> np.ndarray:
    """Capital de référence du jour pour les séries « sur capital immobilisé » : max(expo_j, expo_{j-1}).
    Les coûts du jour j sont ceux de la rotation décidée en j-1 (de w_{j-2} vers w_{j-1}) ; diviser par la seule
    exposition du jour effacerait le coût d'une sortie complète (exposition 0 le jour de la sortie)."""
    prec = np.concatenate([[0.0], exposition[:-1]])
    return np.maximum(exposition, prec)


def rapporter(valeurs: np.ndarray, exposition: np.ndarray) -> np.ndarray:
    """`valeurs` (P&L rapportés au capital total) rapportés au capital immobilisé de référence ; 0 si nul."""
    d = diviseur_immobilise(exposition)
    return np.where(d > 1e-12, valeurs / np.where(d > 1e-12, d, 1.0), 0.0)


@dataclass(frozen=True)
class SerieMoteur:
    """Résultat complet d'un essai (réservé à l'orchestrateur et aux portes ; jamais rendu à un agent)."""

    classe: str
    jours: np.ndarray  # (T,) secondes UTC du jour du rendement
    rendements_nets: np.ndarray
    rendements_nets_stresses: np.ndarray
    rendements_bruts: np.ndarray
    rotation: np.ndarray  # rotation totale (spot + perp) imputée au jour
    rotation_spot: np.ndarray
    rotation_perp: np.ndarray
    couts: np.ndarray  # coûts normaux imputés au jour
    exposition: np.ndarray  # capital immobilisé du jour (Σ w_spot + marge Σ w_perp)
    rendements_nets_immobilise: np.ndarray
    funding: np.ndarray  # funding net reçu dans le jour (part du brut)
    eligible: np.ndarray  # (T,) bool : au moins une paire éligible ce jour
    masque_eval: np.ndarray  # (T,) bool : jours de la fenêtre d'évaluation où la stratégie est mesurable
    poids_spot: np.ndarray  # (T, N) poids décidés à la clôture du jour (ordre des colonnes d'origine)
    poids_perp: np.ndarray
    symboles: tuple[str, ...]

    def evaluation(self, champ: str = "rendements_nets") -> np.ndarray:
        return getattr(self, champ)[self.masque_eval]


def _ts_jour(iso: str) -> int:
    return int(pd.Timestamp(iso, tz="UTC").timestamp())


def masque_evaluation(panneau: Panneau, classe: str, criteres) -> tuple[np.ndarray, np.ndarray]:
    """(éligible, masque_eval) : jours de la fenêtre où au moins une paire est éligible (protocole §3) ;
    pour `couvert`, spot ET perp, et la fenêtre se termine à `fin_fenetre_perp`."""
    T = panneau.n_jours
    debut = _ts_jour(criteres.donnees.fenetre_evaluation.debut)
    fin = _ts_jour(criteres.donnees.fenetre_evaluation.fin)
    if classe == "couvert" and panneau.eligibles_perp is not None:
        elig = (panneau.eligibles & panneau.eligibles_perp).any(axis=1)
        fin = min(fin, _ts_jour(criteres.donnees.fin_fenetre_perp))
    elif classe == "couvert":
        elig = np.zeros(T, dtype=bool)
    else:
        elig = panneau.eligibles.any(axis=1)
    masque = (panneau.jours >= debut) & (panneau.jours <= fin) & elig
    masque[0] = False
    return elig, masque


def simuler(
    panneau: Panneau, poids_spot: np.ndarray, poids_perp: np.ndarray, classe: str, criteres,
    *, convention_rotation: str = "derive", cout_spot_bp: int | None = None, cout_perp_bp: int | None = None,
) -> SerieMoteur:
    """Simule le portefeuille. `poids_*` : (T, N), un vecteur de poids cibles par jour de décision."""
    if convention_rotation not in ("derive", "cible"):
        raise ValueError(convention_rotation)
    T, N = panneau.n_jours, panneau.n_paires
    cs = (criteres.cout_spot_bp if cout_spot_bp is None else cout_spot_bp) / 1e4
    cp = (criteres.cout_perp_bp if cout_perp_bp is None else cout_perp_bp) / 1e4
    stress = criteres.stress_multiplicateur
    marge = criteres.marge_perp_part
    r_s = panneau.rendements_spot()
    r_p = panneau.rendements_perp()
    fund = panneau.funding_par_jour()

    brut = np.zeros(T)
    fund_j = np.zeros(T)
    rot_s = np.zeros(T)
    rot_p = np.zeros(T)
    couts = np.zeros(T)
    expo = np.zeros(T)
    prev_s = np.zeros(N)
    prev_p = np.zeros(N)
    cout_prec = 0.0
    for j in range(T):
        # rendement du jour j avec les poids décidés en j-1 ; coûts de la rotation décidée en j-1
        if j > 0:
            gain_s = float(prev_s @ r_s[j])
            gain_p = float(prev_p @ (fund[j] - r_p[j]))
            brut[j] = gain_s + gain_p
            fund_j[j] = float(prev_p @ fund[j])
            couts[j] = cout_prec
            expo[j] = prev_s.sum() + marge * prev_p.sum()
        # décision du jour j
        cs_j, cp_j = poids_spot[j], poids_perp[j]
        if convention_rotation == "derive" and j > 0:
            denom = 1.0 + brut[j]
            der_s = prev_s * (1.0 + r_s[j]) / denom
            der_p = prev_p * (1.0 + r_p[j]) / denom
        else:
            der_s, der_p = prev_s, prev_p
        a = float(np.abs(cs_j - der_s).sum())
        b = float(np.abs(cp_j - der_p).sum())
        rot_s[j], rot_p[j] = a, b  # imputées au jour j+1 : décalées plus bas
        cout_prec = cs * a + cp * b
        prev_s, prev_p = cs_j, cp_j
    # la rotation décidée en j est payée le jour j+1
    rot_s = np.concatenate([[0.0], rot_s[:-1]])
    rot_p = np.concatenate([[0.0], rot_p[:-1]])
    net = brut - couts
    net2 = brut - stress * couts
    immobilise = rapporter(net, expo)

    elig, masque = masque_evaluation(panneau, classe, criteres)
    return SerieMoteur(
        classe=classe, jours=panneau.jours.copy(), rendements_nets=net, rendements_nets_stresses=net2,
        rendements_bruts=brut, rotation=rot_s + rot_p, rotation_spot=rot_s, rotation_perp=rot_p, couts=couts,
        exposition=expo, rendements_nets_immobilise=immobilise, funding=fund_j, eligible=elig,
        masque_eval=masque, poids_spot=poids_spot, poids_perp=poids_perp, symboles=panneau.symboles)


def panier_equipondere(panneau: Panneau, criteres, *, jours_rebalancement: str = "mensuel",
                       eligibles: np.ndarray | None = None) -> SerieMoteur:
    """Panier équipondéré des paires éligibles, rebalancé le 1er de chaque mois, mêmes coûts (classe
    directionnel). Les poids décidés au dernier jour du mois (clôture) sont 1/n_éligibles ; entre deux
    rebalancements les poids dérivent. Sert de référence à C8 et au test d'acceptation 1/15."""
    T, N = panneau.n_jours, panneau.n_paires
    elig = panneau.eligibles if eligibles is None else eligibles
    r_s = panneau.rendements_spot()
    cs = criteres.cout_spot_bp / 1e4
    dates = pd.to_datetime(panneau.jours, unit="s")
    # le rebalancement se décide à la clôture du dernier jour du mois = ouverture du 1er
    premier_du_mois = np.zeros(T, dtype=bool)
    premier_du_mois[:-1] = dates[1:].day == 1
    w = np.zeros(N)
    brut = np.zeros(T)
    couts = np.zeros(T)
    expo = np.zeros(T)
    poids = np.zeros((T, N))
    cout_prec = 0.0
    for j in range(T):
        if j > 0:
            brut[j] = float(w @ r_s[j])
            couts[j] = cout_prec
            expo[j] = w.sum()
            w = w * (1.0 + r_s[j]) / (1.0 + brut[j])  # dérive
        if j == 0 or premier_du_mois[j] or w.sum() == 0.0:
            n = int(elig[j].sum())
            cible = np.where(elig[j], 1.0 / n, 0.0) if n else np.zeros(N)
        else:
            cible = w
        cout_prec = cs * float(np.abs(cible - w).sum())
        w = cible
        poids[j] = w
    net = brut - couts
    return SerieMoteur(
        classe="directionnel", jours=panneau.jours.copy(), rendements_nets=net,
        rendements_nets_stresses=brut - 2 * couts, rendements_bruts=brut, rotation=np.zeros(T),
        rotation_spot=np.zeros(T), rotation_perp=np.zeros(T), couts=couts, exposition=expo,
        rendements_nets_immobilise=net, funding=np.zeros(T), eligible=elig.any(axis=1),
        masque_eval=masque_evaluation(panneau, "directionnel", criteres)[1], poids_spot=poids, poids_perp=np.zeros((T, N)),
        symboles=panneau.symboles)
