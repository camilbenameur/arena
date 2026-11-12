"""Construction complète et reprenable de `var/recherche/donnees/`."""

from __future__ import annotations

from pathlib import Path

import httpx

from recherche.config import REPO, charger_criteres
from recherche.donnees.controle import UNIVERS_CONTROLE_PATH, choisir_univers_controle
from recherche.donnees.labo import LABO_IN_SAMPLE, copier_in_sample
from recherche.donnees.manifeste import construire_manifeste
from recherche.donnees.telecharger import lister_mois, log, telecharger_mois

RACINE_DEFAUT = REPO / "var" / "recherche" / "donnees"


def construire_donnees(racine: Path | str = RACINE_DEFAUT, *, labo_src: Path | str = LABO_IN_SAMPLE,
                       univers_controle_path: Path | str = UNIVERS_CONTROLE_PATH,
                       client: httpx.Client | None = None) -> dict:
    """Copie du labo, choix de l'univers de contrôle, téléchargements (mois <= 2026-06), manifeste.

    Reprenable : tout fichier déjà présent et vérifié est sauté sans réseau ; la progression va sur stderr.
    Renvoie le manifeste. Durée : plusieurs heures à 1 requête/s (environ 8 000 archives avec l'univers de contrôle).
    """
    racine = Path(racine)
    racine.mkdir(parents=True, exist_ok=True)
    crit = charger_criteres()
    log(f"[1/4] copie des bougies in-sample du labo -> {racine / 'labo'}")
    copier_in_sample(labo_src, racine / "labo")
    propre = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        log("[2/4] univers de contrôle")
        controle = choisir_univers_controle(univers_controle_path, cache=racine / "brut", client=client)
        plan: list[tuple[str, str, int, int]] = []
        log("[3/4] plan des téléchargements (listings publics)")
        demandes = [(src, s) for s in crit.univers for src in ("perp_funding", "perp_klines_1h")]
        demandes += [("spot_klines_1d", s) for s in controle]
        # Univers de contrôle (C16) : mêmes sources que l'univers principal ; un symbole sans perp n'a
        # simplement aucun mois listé (normal).
        demandes += [(src, s) for s in controle
                     for src in ("spot_klines_1h", "perp_klines_1h", "perp_funding")]
        for src, s in demandes:
            plan += [(src, s, a, m) for a, m in lister_mois(src, s, client)]
        log(f"[4/4] {len(plan)} archives à vérifier/télécharger")
        for k, (src, s, a, m) in enumerate(plan, 1):
            telecharger_mois(src, s, a, m, racine / "brut", client)
            if k % 25 == 0 or k == len(plan):
                log(f"  {k}/{len(plan)} (dernier : {src} {s} {a}-{m:02d})")
    finally:
        if propre:
            client.close()
    doc = construire_manifeste(racine, univers_controle_path)
    log(f"manifeste écrit : {len(doc['fichiers'])} fichiers")
    return doc
