"""Saison gelée (docs/RUNBOOK.md « Saison 1 ») : fonctions pures sur les événements du journal.

Une saison commence par `saison_debut` (au premier cycle dont l'instant de décision est >= debut_ts - cycle_delay_s)
et finit par `saison_fin`. Entre les deux, la config (hors table [saison]), la politique de risque et la consigne
système sont gelées : si l'un de leurs hashes diffère de celui du `saison_debut`, le cycle et les réveils refusent
de tourner. La seule échappatoire est un fichier `var/SAISON_DEROGATION` contenant une raison écrite : le cycle
journalise alors `saison_derogation`. L'état se lit uniquement dans le journal (pas dans la config).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from arene.paths import Paths

HASHES = ("config_sha256", "policy_sha256", "prompt_sha256")
NOMS = {"config_sha256": "config", "policy_sha256": "politique de risque", "prompt_sha256": "consigne système"}


def lire_derogation(paths: Paths) -> str:
    """Raison écrite dans `var/SAISON_DEROGATION` (vide : pas de dérogation)."""
    try:
        return (paths.var / "SAISON_DEROGATION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def saison_ouverte(events: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Payload du dernier `saison_debut` dont la saison n'a pas de `saison_fin`, sinon None."""
    fins = {e["payload"]["numero"] for e in events if e["type"] == "saison_fin"}
    ouvertes = [e["payload"] for e in events if e["type"] == "saison_debut" and e["payload"]["numero"] not in fins]
    return ouvertes[-1] if ouvertes else None


@dataclass(frozen=True)
class Gel:
    statut: str  # libre | derogation | gele
    numero: int | None = None
    avant: Mapping[str, str] | None = None  # hashes de référence (début, ou dernière dérogation)
    apres: Mapping[str, str] | None = None
    diff: tuple[str, ...] = ()

    @property
    def message(self) -> str:
        noms = ", ".join(NOMS[k] for k in self.diff)
        return (
            f"saison {self.numero} gelée : {noms} modifié(e) depuis le début ({', '.join(self.diff)}) ; "
            "pour déroger, écrire une raison dans var/SAISON_DEROGATION"
        )


def verifier_gel(
    events: Sequence[Mapping[str, Any]], hashes: Mapping[str, str], t: int, raison: str
) -> Gel:
    """Gel de la saison ouverte à l'instant `t` (cycle ou réveil). Libre si aucune saison n'est ouverte ou si
    `t >= fin_prevue_cycle` (le cycle de fin ne subit plus le gel)."""
    debut = saison_ouverte(events)
    if debut is None or t >= debut["fin_prevue_cycle"]:
        return Gel("libre")
    ref = {k: debut[k] for k in HASHES}
    for e in events:
        if e["type"] == "saison_derogation" and e["payload"]["numero"] == debut["numero"]:
            ref = dict(e["payload"]["hashes_apres"])
    diff = tuple(k for k in HASHES if hashes[k] != ref[k])
    if not diff:
        return Gel("libre", debut["numero"], ref, dict(hashes))
    return Gel("derogation" if raison else "gele", debut["numero"], ref, dict(hashes), diff)
