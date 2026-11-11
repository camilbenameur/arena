"""Manifeste des données de recherche : sha256 de chaque fichier de `racine` (hors le manifeste lui-même)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from recherche.config import REPO
from recherche.donnees.labo import _sha_fichier

NOM = "MANIFESTE.json"
VERSION = "recherche-donnees-v1"
UNIVERS_CONTROLE_PATH = REPO / "recherche" / "univers_controle.json"


class ManifesteError(Exception):
    """Un fichier manque, a changé, ou n'est pas listé : les données ne sont pas celles qui ont été figées."""


def _fichiers(racine: Path) -> list[Path]:
    return sorted(p for p in racine.rglob("*")
                  if p.is_file() and p.name != NOM and not p.name.endswith(".part"))


def construire_manifeste(racine: Path | str, univers_controle: Path | str | None = UNIVERS_CONTROLE_PATH
                         ) -> dict:
    """Hache tous les fichiers de `racine`, écrit `racine/MANIFESTE.json` et renvoie son contenu.

    Si `univers_controle` existe, son sha256 est consigné aussi (la liste figée fait partie des données).
    """
    racine = Path(racine)
    fichiers = {p.relative_to(racine).as_posix(): {"sha256": _sha_fichier(p), "octets": p.stat().st_size}
                for p in _fichiers(racine)}
    doc = {"version": VERSION, "coupure": "2026-07-01T00:00:00Z", "fichiers": fichiers}
    if univers_controle is not None and Path(univers_controle).is_file():
        doc["univers_controle_sha256"] = _sha_fichier(Path(univers_controle))
    tmp = racine / (NOM + ".part")
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    tmp.replace(racine / NOM)
    return doc


def lire_manifeste(racine: Path | str) -> dict:
    p = Path(racine) / NOM
    if not p.is_file():
        raise ManifesteError(f"{p} absent : lancer construire_donnees")
    return json.loads(p.read_text())


def verifier_manifeste(racine: Path | str, univers_controle: Path | str | None = UNIVERS_CONTROLE_PATH
                       ) -> dict:
    """Vérifie fichier par fichier (présence, taille, sha256, aucun fichier en trop). Renvoie le manifeste."""
    racine = Path(racine)
    doc = lire_manifeste(racine)
    attendus = doc["fichiers"]
    presents = {p.relative_to(racine).as_posix(): p for p in _fichiers(racine)}
    manquants = sorted(set(attendus) - set(presents))
    en_trop = sorted(set(presents) - set(attendus))
    if manquants or en_trop:
        raise ManifesteError(f"fichiers manquants {manquants[:5]} ({len(manquants)}), "
                             f"fichiers non listés {en_trop[:5]} ({len(en_trop)})")
    for nom, e in attendus.items():
        p = presents[nom]
        if p.stat().st_size != e["octets"] or _sha_fichier(p) != e["sha256"]:
            raise ManifesteError(f"{nom} : contenu différent du manifeste")
    if "univers_controle_sha256" in doc:
        if univers_controle is None or not Path(univers_controle).is_file():
            raise ManifesteError("univers_controle.json absent alors que le manifeste le consigne")
        if _sha_fichier(Path(univers_controle)) != doc["univers_controle_sha256"]:
            raise ManifesteError("univers_controle.json modifié depuis la construction du manifeste")
    return doc


def sha256_manifeste(racine: Path | str) -> str:
    return hashlib.sha256((Path(racine) / NOM).read_bytes()).hexdigest()
