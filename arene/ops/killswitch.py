"""Coupe-circuit : fichier sentinelle `var/KILL` ou `~/.config/arene/KILL` (docs/SPEC-MVP.md §7, §12).

Effet au plus tard au cycle suivant ; `arene kill --now` lance en plus une mise à plat immédiate.
"""

from __future__ import annotations

from pathlib import Path

from arene.paths import Paths


def _files(paths: Paths) -> list[Path]:
    return [paths.kill, paths.user_kill]


def active_sources(paths: Paths) -> list[str]:
    """Sentinelles présentes (chemins en texte). Liste vide : coupe-circuit inactif."""
    return [str(p) for p in _files(paths) if p.exists()]


def is_active(paths: Paths) -> bool:
    return bool(active_sources(paths))


def activate(paths: Paths) -> Path:
    paths.kill.parent.mkdir(parents=True, exist_ok=True)
    paths.kill.touch()
    return paths.kill


def deactivate(paths: Paths) -> list[Path]:
    """Supprime les sentinelles. Renvoie celles qui ont été supprimées."""
    removed = []
    for p in _files(paths):
        try:
            p.unlink()
            removed.append(p)
        except FileNotFoundError:
            pass
    return removed
