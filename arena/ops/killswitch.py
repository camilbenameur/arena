"""Kill switch: sentinel file `var/KILL` or `~/.config/arena/KILL` (docs/SPEC-MVP.md §7, §12).

Takes effect by the next cycle at the latest; `arena kill --now` also triggers an immediate flatten.
"""

from __future__ import annotations

from pathlib import Path

from arena.paths import Paths


def _files(paths: Paths) -> list[Path]:
    return [paths.kill, paths.user_kill]


def active_sources(paths: Paths) -> list[str]:
    """Sentinels present (paths as text). Empty list: kill switch inactive."""
    return [str(p) for p in _files(paths) if p.exists()]


def is_active(paths: Paths) -> bool:
    return bool(active_sources(paths))


def activate(paths: Paths) -> Path:
    paths.kill.parent.mkdir(parents=True, exist_ok=True)
    paths.kill.touch()
    return paths.kill


def deactivate(paths: Paths) -> list[Path]:
    """Delete the sentinels. Returns the ones that were deleted."""
    removed = []
    for p in _files(paths):
        try:
            p.unlink()
            removed.append(p)
        except FileNotFoundError:
            pass
    return removed
