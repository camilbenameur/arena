"""Choix mécanique de l'univers de contrôle (C16), figé dans `recherche/univers_controle.json`.

Règle (criteres.yaml) : les `taille` plus gros volumes en quote de janvier 2020 parmi les symboles spot
USDT de data.binance.vision, hors univers, délistés compris ; stablecoins, monnaies fiat et jetons à
levier exclus ; tout symbole dont les données de 2020-01 manquent (archive absente ou moins de 31 barres
journalières) est écarté. Le volume est la somme des `quote_volume` des 31 barres 1 j de 2020-01
(l'archive mensuelle 1 j contient exactement les barres des archives quotidiennes).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx

from recherche.config import REPO, charger_criteres
from recherche.donnees.lecture import lire_barres_zip
from recherche.donnees.telecharger import DonneeAbsente, lister_symboles_spot, log, telecharger_mois

UNIVERS_CONTROLE_PATH = REPO / "recherche" / "univers_controle.json"
STABLES = frozenset({
    "USDC", "BUSD", "TUSD", "USDP", "DAI", "FDUSD", "PAX", "USDS", "USDSB", "SUSD", "UST", "USTC",
    "USDD", "GUSD", "HUSD", "LUSD", "EURI", "AEUR", "EUR", "GBP", "AUD", "TRY", "BRL", "RUB", "UAH",
    "NGN", "ZAR", "IDRT", "BIDR", "BVND", "VAI", "XUSD", "USD1", "PYUSD",
})
_LEVIER = re.compile(r"^[A-Z0-9]{2,}(UP|DOWN|BULL|BEAR)$")
REGLE = ("plus gros volumes en quote de janvier 2020 sur data.binance.vision (spot USDT, archive mensuelle 1 j "
         "complète de 31 barres), hors univers, délistés compris, stablecoins, monnaies fiat et jetons à levier "
         "exclus ; figé avant la vague 1")


def candidat_admissible(symbole: str, univers: set[str] | frozenset[str]) -> bool:
    if not symbole.endswith("USDT") or symbole in univers:
        return False
    base = symbole[: -len("USDT")]
    return bool(base) and base not in STABLES and not _LEVIER.match(base)


def choisir_univers_controle(sortie: Path | str = UNIVERS_CONTROLE_PATH, cache: Path | str | None = None,
                             client: httpx.Client | None = None, date: str | None = None,
                             force: bool = False, candidats: list[str] | None = None) -> list[str]:
    """Renvoie la liste figée ; la calcule (réseau) seulement si `sortie` n'existe pas (ou `force`).

    `cache` : dossier des zips bruts (même arborescence que le téléchargement ; défaut
    `var/recherche/donnees/brut`). `candidats` : liste de symboles à évaluer (défaut : listing public).
    """
    sortie = Path(sortie)
    crit = charger_criteres()
    if sortie.exists() and not force:
        doc = json.loads(sortie.read_text())
        if len(doc["symboles"]) != crit.controle_taille:
            raise ValueError(f"{sortie} : {len(doc['symboles'])} symboles, {crit.controle_taille} attendus")
        return list(doc["symboles"])
    cache = Path(cache) if cache else REPO / "var" / "recherche" / "donnees" / "brut"
    univers = frozenset(crit.univers)
    propre = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        liste = candidats if candidats is not None else lister_symboles_spot(client)
        cand = sorted(s for s in liste if candidat_admissible(s, univers))
        log(f"controle : {len(cand)} candidats USDT à évaluer sur 2020-01")
        absents_f = cache / "controle_absents_2020-01.txt"
        cache.mkdir(parents=True, exist_ok=True)
        absents = set(absents_f.read_text().split()) if absents_f.exists() else set()
        volumes: dict[str, float] = {}
        for i, s in enumerate(cand, 1):
            if s in absents:
                continue
            try:
                zp = telecharger_mois("spot_klines_1d", s, 2020, 1, cache, client)
            except DonneeAbsente:
                absents.add(s)
                with absents_f.open("a") as f:
                    f.write(s + "\n")
                continue
            df = lire_barres_zip(zp.read_bytes(), zp.name)
            if len(df) == 31:
                volumes[s] = float(df["quote_volume"].sum())
            if i % 25 == 0:
                log(f"controle : {i}/{len(cand)} évalués, {len(volumes)} avec 2020-01 complet")
    finally:
        if propre:
            client.close()
    classes = sorted(volumes, key=lambda s: (-volumes[s], s))
    if len(classes) < crit.controle_taille:
        raise ValueError(f"seulement {len(classes)} symboles admissibles, {crit.controle_taille} attendus")
    choisis = classes[: crit.controle_taille]
    doc = {
        "regle": REGLE,
        "source": "https://data.binance.vision/data/spot/monthly/klines/<SYM>/1d/<SYM>-1d-2020-01.zip",
        "date": date or datetime.now(UTC).date().isoformat(),
        "taille": crit.controle_taille,
        "n_candidats_avec_2020_01_complet": len(volumes),
        "symboles": choisis,
        "volume_quote_2020_01": {s: volumes[s] for s in choisis},
    }
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    return choisis
