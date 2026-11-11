"""Téléchargement des archives mensuelles publiques de data.binance.vision, mois <= 2026-06 seulement.

Pare-feu : `telecharger_mois` lève `CoupureError` pour tout (annee, mois) >= (2026, 7) AVANT toute
requête réseau. Chaque zip est vérifié contre le `.CHECKSUM` publié. Une requête par seconde au plus.
Reprenable : un zip déjà présent dont le sha256 égale celui du `.CHECKSUM` conservé à côté est sauté
sans réseau.
"""

from __future__ import annotations

import hashlib
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from recherche.config import DERNIER_MOIS, CoupureError

BASE = "https://data.binance.vision/data"
LISTE = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
PAUSE_S = 1.0  # une requête par seconde
SOURCES = ("perp_funding", "perp_klines_1h", "spot_klines_1d")


class TelechargementError(Exception):
    """Échec réseau ou checksum non conforme."""


class DonneeAbsente(TelechargementError):
    """L'archive n'existe pas (HTTP 404)."""


_dernier = [0.0]


def _limiter() -> None:
    attente = _dernier[0] + PAUSE_S - time.monotonic()
    if attente > 0:
        time.sleep(attente)
    _dernier[0] = time.monotonic()


def _chemin(source: str, symbole: str) -> str:
    if source == "perp_funding":
        return f"futures/um/monthly/fundingRate/{symbole}"
    if source == "perp_klines_1h":
        return f"futures/um/monthly/klines/{symbole}/1h"
    if source == "spot_klines_1d":
        return f"spot/monthly/klines/{symbole}/1d"
    raise ValueError(f"source inconnue : {source!r} (attendu : {SOURCES})")


def nom_fichier(source: str, symbole: str, annee: int, mois: int) -> str:
    mm = f"{annee:04d}-{mois:02d}"
    return {
        "perp_funding": f"{symbole}-fundingRate-{mm}.zip",
        "perp_klines_1h": f"{symbole}-1h-{mm}.zip",
        "spot_klines_1d": f"{symbole}-1d-{mm}.zip",
    }[source]


def url_mois(source: str, symbole: str, annee: int, mois: int) -> str:
    return f"{BASE}/{_chemin(source, symbole)}/{nom_fichier(source, symbole, annee, mois)}"


def chemin_local(dest: Path | str, source: str, symbole: str, annee: int, mois: int) -> Path:
    return Path(dest) / source / symbole / nom_fichier(source, symbole, annee, mois)


def verifier_mois(annee: int, mois: int) -> None:
    if not (1 <= mois <= 12):
        raise ValueError(f"mois invalide : {mois}")
    if (annee, mois) > DERNIER_MOIS:
        raise CoupureError(
            f"mois {annee:04d}-{mois:02d} postérieur à {DERNIER_MOIS[0]:04d}-{DERNIER_MOIS[1]:02d} : refusé"
        )


def _get(client: httpx.Client, url: str, essais: int = 4) -> httpx.Response:
    derniere: Exception | None = None
    for k in range(essais):
        _limiter()
        try:
            r = client.get(url, timeout=60.0)
        except httpx.TransportError as e:
            derniere = e
        else:
            if r.status_code == 404:
                raise DonneeAbsente(url)
            if r.status_code < 400:
                return r
            derniere = TelechargementError(f"HTTP {r.status_code} sur {url}")
            if r.status_code < 500 and r.status_code != 429:
                raise derniere
        if k < essais - 1:
            time.sleep(min(30.0, 2.0 ** (k + 1)) if PAUSE_S else 0)
    raise TelechargementError(f"échec après {essais} essais : {url} ({derniere})")


def _sha_texte(texte: str) -> str:
    m = re.search(r"\b([0-9a-fA-F]{64})\b", texte)
    if not m:
        raise TelechargementError(f"CHECKSUM illisible : {texte[:80]!r}")
    return m.group(1).lower()


def telecharger_mois(source: str, symbole: str, annee: int, mois: int, dest: Path | str,
                     client: httpx.Client | None = None) -> Path:
    """Télécharge (ou retrouve) l'archive du mois sous `dest/<source>/<symbole>/`. Renvoie son chemin.

    `CoupureError` si (annee, mois) >= (2026, 7), avant tout accès réseau. `DonneeAbsente` si 404.
    """
    verifier_mois(annee, mois)
    url = url_mois(source, symbole, annee, mois)  # valide aussi `source`
    cible = chemin_local(dest, source, symbole, annee, mois)
    lateral = cible.with_name(cible.name + ".CHECKSUM")
    if cible.exists() and lateral.exists():
        if hashlib.sha256(cible.read_bytes()).hexdigest() == _sha_texte(lateral.read_text()):
            return cible
        cible.unlink()
    cible.parent.mkdir(parents=True, exist_ok=True)
    propre = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        publie = _get(client, url + ".CHECKSUM").text
        attendu = _sha_texte(publie)
        octets = _get(client, url).content
    finally:
        if propre:
            client.close()
    obtenu = hashlib.sha256(octets).hexdigest()
    if obtenu != attendu:
        raise TelechargementError(f"checksum différent pour {url} : attendu {attendu}, obtenu {obtenu}")
    tmp = cible.with_name(cible.name + ".part")
    tmp.write_bytes(octets)
    tmp.replace(cible)
    lateral.write_text(publie if publie.endswith("\n") else publie + "\n")
    return cible


def _liste(client: httpx.Client, prefixe: str, delimiteur: bool) -> tuple[list[str], list[str]]:
    """Listing S3 paginé : (clés, préfixes communs)."""
    cles: list[str] = []
    prefs: list[str] = []
    marqueur = ""
    while True:
        params = {"prefix": prefixe, "max-keys": "1000"}
        if delimiteur:
            params["delimiter"] = "/"
        if marqueur:
            params["marker"] = marqueur
        _limiter()
        r = client.get(LISTE, params=params, timeout=60.0)
        if r.status_code >= 400:
            raise TelechargementError(f"listing HTTP {r.status_code} ({prefixe})")
        racine = ET.fromstring(r.content)
        ns = racine.tag.split("}")[0] + "}" if racine.tag.startswith("{") else ""
        cles += [e.findtext(f"{ns}Key") or "" for e in racine.findall(f"{ns}Contents")]
        prefs += [e.findtext(f"{ns}Prefix") or "" for e in racine.findall(f"{ns}CommonPrefixes")]
        if (racine.findtext(f"{ns}IsTruncated") or "").lower() != "true":
            return cles, prefs
        marqueur = racine.findtext(f"{ns}NextMarker") or (cles[-1] if cles else prefs[-1])


def lister_mois(source: str, symbole: str, client: httpx.Client | None = None) -> list[tuple[int, int]]:
    """Mois publiés (<= 2026-06 seulement) pour une source et un symbole, d'après le listing public."""
    prefixe = f"data/{_chemin(source, symbole)}/"
    propre = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        cles, _ = _liste(client, prefixe, delimiteur=False)
    finally:
        if propre:
            client.close()
    out = []
    for c in cles:
        m = re.search(r"-(\d{4})-(\d{2})\.zip$", c)
        if m and c.startswith(prefixe) and (int(m[1]), int(m[2])) <= DERNIER_MOIS:
            out.append((int(m[1]), int(m[2])))
    return sorted(set(out))


def lister_symboles_spot(client: httpx.Client | None = None) -> list[str]:
    """Tous les symboles spot ayant des archives mensuelles de bougies (délistés compris)."""
    propre = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        _, prefs = _liste(client, "data/spot/monthly/klines/", delimiteur=True)
    finally:
        if propre:
            client.close()
    return sorted(p.rstrip("/").rsplit("/", 1)[-1] for p in prefs)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
