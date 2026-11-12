"""Saison gelée (docs/RUNBOOK.md « Saison 1 ») : fonctions pures sur les événements du journal.

Une saison commence par `saison_debut` (au premier cycle dont l'instant de décision est >= debut_ts - cycle_delay_s)
et finit par `saison_fin`. Entre les deux, la config (hors table [saison]), la politique de risque et la consigne
système sont gelées : si l'un de leurs hashes diffère de celui du `saison_debut`, le cycle et les réveils refusent
de tourner. La seule échappatoire est un fichier `var/SAISON_DEROGATION` contenant une raison écrite : le cycle
journalise alors `saison_derogation`. L'état se lit uniquement dans le journal (pas dans la config).
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from arene.paths import Paths

HASHES = ("config_sha256", "policy_sha256", "prompt_sha256", "code_sha256")
NOMS = {
    "config_sha256": "config",
    "policy_sha256": "politique de risque",
    "prompt_sha256": "consigne système",
    "code_sha256": "code",
}
#: Code gelé : liste blanche des modules qui font tourner le cycle, la veille et les réveils (lus SUR LE DISQUE,
#: sans dépendre de git). Hors gel : `arene/site/` (dashboard), `arene/cli.py`, `arene/perp/` (ligue dérivés,
#: développée pendant la saison), `arene/stats.py`, et `uv.lock` (réécrit par `uv run` en développement).
CODE_GELE_FICHIERS = (
    "arene/__init__.py", "arene/config.py", "arene/cycle.py", "arene/veille.py", "arene/journal.py",
    "arene/ledger.py", "arene/types.py", "arene/paths.py", "arene/saison.py",
    "arene/ops/dormance.py", "arene/ops/killswitch.py", "config/policy.toml",
)
CODE_GELE_DOSSIERS = ("arene/data", "arene/deciders", "arene/risk", "arene/sim", "arene/temoins")
CODE_SUFFIXES = (".py", ".md", ".toml", ".json", ".txt")


def _fichiers_code(repo: Path) -> list[str]:
    """Chemins gelés (voir CODE_GELE_*), lus sur le disque : les fichiers des dossiers gelés dont le suffixe est dans
    CODE_SUFFIXES, hors `__pycache__`. Aucun appel à git : le hash ne bascule pas selon que git répond ou non."""
    files = [f for f in CODE_GELE_FICHIERS if (repo / f).is_file()]
    for d in CODE_GELE_DOSSIERS:
        base = repo / d
        if base.is_dir():
            files += [
                str(f.relative_to(repo)) for f in base.rglob("*")
                if f.is_file() and "__pycache__" not in f.parts and f.suffix in CODE_SUFFIXES
            ]  # fmt: skip
    return sorted(set(files))


def code_sha256(repo: Path) -> str:
    """sha256 du code gelé : pour chaque chemin dans l'ordre trié (voir `_fichiers_code`), le chemin, un octet nul,
    la longueur du contenu (8 octets) puis les octets lus SUR LE DISQUE (un fichier supprimé compte comme absent)."""
    h = hashlib.sha256()
    for f in _fichiers_code(repo):
        try:
            data = (repo / f).read_bytes()
        except OSError:
            continue
        h.update(f.encode("utf-8") + b"\0" + len(data).to_bytes(8, "big") + data)
    return h.hexdigest()


def claude_cli_version() -> str | None:
    """Sortie de `claude --version`, ou None (CLI absente, délai, échec). Non gelée : un changement est alerté."""
    from arene.deciders import llm  # import tardif (les tests remplacent `_claude_bin`)

    try:
        out = subprocess.run([llm._claude_bin(), "--version"], capture_output=True, text=True, timeout=20, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()[:100] or None


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
    ref = {k: debut[k] for k in HASHES if k in debut}
    for e in events:
        if e["type"] == "saison_derogation" and e["payload"]["numero"] == debut["numero"]:
            ref = dict(e["payload"]["hashes_apres"])
    diff = tuple(k for k in HASHES if k in ref and hashes[k] != ref[k])
    if not diff:
        return Gel("libre", debut["numero"], ref, dict(hashes))
    return Gel("derogation" if raison else "gele", debut["numero"], ref, dict(hashes), diff)
