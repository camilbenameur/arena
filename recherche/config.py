"""Chargement des critères chiffrés (`criteres.yaml`) et constantes du pare-feu.

`criteres.yaml` fait foi. L'objet `Criteres` est gelé : ses sections sont des vues en lecture seule,
accessibles par clé (`c.couts_bp["spot_par_rotation"]`) ou par attribut (`c.couts_bp.spot_par_rotation`).
Les coûts sont des entiers en points de base ; tout flottant à leur place est refusé.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
CRITERES_PATH = REPO / "recherche" / "criteres.yaml"
ARENE_TOML = REPO / "config" / "arene.toml"

#: 2026-07-01T00:00:00Z. Rien d'égal ou postérieur n'entre dans la recherche ; `connue_a` > COUPURE_TS est refusé.
COUPURE_TS = 1_782_864_000
#: Dernier mois (année, mois) autorisé au téléchargement.
DERNIER_MOIS = (2026, 6)


class CoupureError(Exception):
    """Une donnée postérieure à la coupure (2026-07-01T00:00:00Z) a été demandée ou rencontrée."""


class CriteresError(Exception):
    """`criteres.yaml` est invalide ou incohérent."""


class Section(Mapping):
    """Vue en lecture seule d'une section du YAML : clés ET attributs, récursive."""

    __slots__ = ("_d",)

    def __init__(self, d: Mapping[str, Any]):
        object.__setattr__(self, "_d", {k: _geler(v) for k, v in d.items()})

    def __getitem__(self, k):
        return self._d[k]

    def __iter__(self):
        return iter(self._d)

    def __len__(self):
        return len(self._d)

    def __getattr__(self, k):
        try:
            return self._d[k]
        except KeyError:
            raise AttributeError(k) from None

    def __setattr__(self, k, v):
        raise AttributeError("Section en lecture seule")

    def __repr__(self):
        return f"Section({self._d!r})"

    def vers_dict(self) -> dict:
        return {k: (v.vers_dict() if isinstance(v, Section) else list(v) if isinstance(v, tuple) else v)
                for k, v in self._d.items()}


def _geler(v):
    if isinstance(v, Mapping):
        return Section(v)
    if isinstance(v, list):
        return tuple(_geler(x) for x in v)
    return v


def _entier_bp(nom: str, v) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise CriteresError(f"{nom} doit être un entier en points de base, reçu {v!r}")
    if v < 0:
        raise CriteresError(f"{nom} doit être >= 0")
    return v


def _ts(iso: str) -> int:
    return int(datetime.fromisoformat(iso).astimezone(UTC).timestamp())


@dataclass(frozen=True)
class Criteres:
    sha256: str
    version: str
    coupure_ts: int
    univers: tuple[str, ...]
    univers_arene: tuple[str, ...]
    controle_taille: int
    cout_spot_bp: int
    cout_perp_bp: int
    stress_multiplicateur: int
    marge_perp_part: float
    n_dsr: int
    plafond_total: int
    plafond_vague_1: int
    timeout_essai_s: int
    donnees: Section
    couts_bp: Section
    classes: Section
    essais: Section
    dsr: Section
    portes: Section
    coherence: Section
    selection: Section
    paper: Section
    execution: Section

    def cout_bp(self, jambe: str, stress: bool = False) -> int:
        """Coût par unité de rotation, en pb entiers (`jambe` : "spot" ou "perp")."""
        base = {"spot": self.cout_spot_bp, "perp": self.cout_perp_bp}[jambe]
        return base * (self.stress_multiplicateur if stress else 1)


def charger_criteres(path: Path | str = CRITERES_PATH) -> Criteres:
    octets = Path(path).read_bytes()
    brut = yaml.safe_load(octets)
    if not isinstance(brut, dict):
        raise CriteresError("criteres.yaml : mapping attendu à la racine")
    try:
        don, couts, ess = brut["donnees"], brut["couts_bp"], brut["essais"]
        coupure = _ts(don["coupure_exclue"])
        if coupure != COUPURE_TS:
            raise CriteresError(f"coupure_exclue ({coupure}) différente de COUPURE_TS ({COUPURE_TS})")
        univers = tuple(don["univers"])
        arene = tuple(don["univers_arene"])
        if len(set(univers)) != len(univers) or not set(arene) <= set(univers):
            raise CriteresError("univers : doublons ou univers_arene hors univers")
        spot = _entier_bp("couts_bp.spot_par_rotation", couts["spot_par_rotation"])
        perp = _entier_bp("couts_bp.perp_par_rotation", couts["perp_par_rotation"])
        stress = _entier_bp("couts_bp.stress_multiplicateur", couts["stress_multiplicateur"])
        return Criteres(
            sha256=hashlib.sha256(octets).hexdigest(),
            version=str(brut["version"]),
            coupure_ts=coupure,
            univers=univers,
            univers_arene=arene,
            controle_taille=int(don["univers_controle"]["taille"]),
            cout_spot_bp=spot,
            cout_perp_bp=perp,
            stress_multiplicateur=stress,
            marge_perp_part=float(couts["marge_perp_part"]),
            n_dsr=int(ess["N_dsr"]),
            plafond_total=int(ess["plafond_total"]),
            plafond_vague_1=int(ess["plafond_vague_1"]),
            timeout_essai_s=int(brut["execution"]["timeout_essai_s"]),
            donnees=Section(don),
            couts_bp=Section(couts),
            classes=Section(brut["classes"]),
            essais=Section(ess),
            dsr=Section(brut["dsr"]),
            portes=Section(brut["portes"]),
            coherence=Section(brut["coherence"]),
            selection=Section(brut["selection"]),
            paper=Section(brut["paper"]),
            execution=Section(brut["execution"]),
        )
    except KeyError as e:
        raise CriteresError(f"criteres.yaml : clé manquante {e}") from None
