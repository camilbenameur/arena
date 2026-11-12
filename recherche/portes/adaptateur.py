"""Adaptateur moteur -> portes : `ResultatEssai` (moteur) vers `Essai` et `RapportCausalite` (portes).

Aucun calcul de performance ici : on découpe les séries du moteur sur la fenêtre d'évaluation
(`masque_eval`) et, pour la classe `couvert` seulement, on les rapporte au capital immobilisé de référence
(PROTOCOLE §3 : « capital immobilisé = notionnel spot + marge perp ») : max(expo_j, expo_{j-1}), pour que le
coût d'une sortie complète (exposition 0 le jour du coût) ne disparaisse pas. Pour `directionnel`, les séries sont
celles du moteur, telles quelles (capital total = 1, le cash rend zéro).
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from recherche.moteur.portefeuille import rapporter
from recherche.portes.evaluer import Essai, RapportCausalite


def _serie(valeurs: np.ndarray, jours: np.ndarray, masque: np.ndarray, exposition: np.ndarray | None) -> pd.Series:
    """Série datée sur la fenêtre d'évaluation ; `exposition` non None : rapportée au capital immobilisé de
    référence max(expo_j, expo_{j-1}) (le diviseur est calculé sur TOUTE la série avant d'appliquer le masque)."""
    v = valeurs if exposition is None else rapporter(valeurs, exposition)
    return pd.Series(v[masque].astype(float), index=pd.to_datetime(jours[masque], unit="s"))


def vers_essai(resultat, *, famille: str, classe: str, params: Mapping[str, float]) -> Essai:
    """`resultat` : `ResultatEssai` du moteur avec `serie` (code OK). Lève ValueError sinon."""
    s = resultat.serie
    if s is None:
        raise ValueError(f"essai {resultat.id} sans série (code {resultat.code})")
    m = s.masque_eval
    div = s.exposition if classe == "couvert" else None

    def ser(x):
        return _serie(x, s.jours, m, div)

    return Essai(
        id=resultat.id, famille=famille, classe=classe, params=dict(params),
        net=ser(s.rendements_nets), net_stress=ser(s.rendements_nets_stresses), brut=ser(s.rendements_bruts),
        rotation=_serie(s.rotation, s.jours, m, None), couts=ser(s.couts), univers=resultat.univers)


def vers_rapport_causalite(causalite: dict | None, criteres) -> RapportCausalite | None:
    """Résumé C9 depuis `ResultatEssai.causalite` (dict de `verifier_causalite`). None si absent ou si le
    test n'a pas pu aller au bout (clé `erreur`)."""
    if not causalite or "ecart_coupures" not in causalite:
        return None
    n_fixes = int(criteres.portes.C9_causalite.coupures_fixes)
    n = int(causalite["n_coupures"])
    ecart = max(causalite["ecart_coupures"], causalite["ecart_permutation"], causalite["ecart_echelle"])
    tol = 1e-9
    return RapportCausalite(
        n_aleatoires=n - n_fixes, n_fixes=n_fixes,
        part_heure_non_pleine=causalite["coupures_heure_non_pleine"] / n if n else 0.0,
        ecart_max=float(ecart),
        invariances_ok=bool(causalite.get("deterministe", False) and causalite["ecart_permutation"] <= tol
                            and causalite["ecart_echelle"] <= tol
                            # poids constants sur toute la série synthétique : rien ne prouve la causalité
                            and causalite.get("evaluable", False)
                            # second contrôle, sur les données réelles de l'essai (permutation + échelles)
                            and causalite.get("reel_ok", False)))


def vers_serie_panier(panier_serie) -> pd.Series:
    """Rendements nets du panier du moteur sur sa fenêtre d'évaluation, en `pd.Series` datée."""
    m = panier_serie.masque_eval
    return pd.Series(panier_serie.rendements_nets[m].astype(float),
                     index=pd.to_datetime(panier_serie.jours[m], unit="s"))
