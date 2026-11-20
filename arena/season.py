"""Frozen season (docs/RUNBOOK.md "Season 1"): pure functions over the journal events.

A season starts with `season_started` (at the first cycle whose decision time is >= start_ts - cycle_delay_s)
and ends with `season_ended`. In between, the config (outside the [season] table), the risk policy and the system
prompt are frozen: if any of their hashes differs from the one in `season_started`, the cycle and the wake-ups refuse
to run. The only escape hatch is a `var/SEASON_WAIVER` file containing a written reason: the cycle then journals
`season_waiver`. The state is read from the journal only (not from the config).
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from arena.paths import Paths

HASHES = ("config_sha256", "policy_sha256", "prompt_sha256", "code_sha256")
NAMES = {
    "config_sha256": "config",
    "policy_sha256": "risk policy",
    "prompt_sha256": "system prompt",
    "code_sha256": "code",
}
#: Frozen code: allow-list of the modules that run the cycle, the watch and the wake-ups (read FROM DISK,
#: without depending on git). Outside the freeze: `arena/site/` (dashboard), `arena/cli.py`, `arena/perp/` (derivatives
#: league, developed during the season), `arena/stats.py`, and `uv.lock` (rewritten by `uv run` during development).
FROZEN_CODE_FILES = (
    "arena/__init__.py", "arena/config.py", "arena/cycle.py", "arena/watch.py", "arena/journal.py",
    "arena/ledger.py", "arena/types.py", "arena/paths.py", "arena/season.py",
    "arena/ops/dormancy.py", "arena/ops/killswitch.py", "config/policy.toml",
)
FROZEN_CODE_DIRS = ("arena/data", "arena/deciders", "arena/risk", "arena/sim", "arena/benchmarks")
CODE_SUFFIXES = (".py", ".md", ".toml", ".json", ".txt")


def _code_files(repo: Path) -> list[str]:
    """Frozen paths (see FROZEN_CODE_*), read from disk: the files of the frozen directories whose suffix is in
    CODE_SUFFIXES, excluding `__pycache__`. No git call: the hash does not change depending on whether git answers."""
    files = [f for f in FROZEN_CODE_FILES if (repo / f).is_file()]
    for d in FROZEN_CODE_DIRS:
        base = repo / d
        if base.is_dir():
            files += [
                str(f.relative_to(repo)) for f in base.rglob("*")
                if f.is_file() and "__pycache__" not in f.parts and f.suffix in CODE_SUFFIXES
            ]  # fmt: skip
    return sorted(set(files))


def code_sha256(repo: Path) -> str:
    """sha256 of the frozen code: for each path in sorted order (see `_code_files`), the path, a null byte,
    the content length (8 bytes) then the bytes read FROM DISK (a deleted file counts as absent)."""
    h = hashlib.sha256()
    for f in _code_files(repo):
        try:
            data = (repo / f).read_bytes()
        except OSError:
            continue
        h.update(f.encode("utf-8") + b"\0" + len(data).to_bytes(8, "big") + data)
    return h.hexdigest()


def claude_cli_version() -> str | None:
    """Output of `claude --version`, or None (CLI missing, timeout, failure). Not frozen: a change raises an alert."""
    from arena.deciders import llm  # late import (tests replace `_claude_bin`)

    try:
        out = subprocess.run([llm._claude_bin(), "--version"], capture_output=True, text=True, timeout=20, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()[:100] or None


def read_waiver(paths: Paths) -> str:
    """Reason written in `var/SEASON_WAIVER` (empty: no waiver)."""
    try:
        return (paths.var / "SEASON_WAIVER").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def season_open(events: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Payload of the last `season_started` whose season has no `season_ended`, else None."""
    ends = {e["payload"]["number"] for e in events if e["type"] == "season_ended"}
    opened = [e["payload"] for e in events if e["type"] == "season_started" and e["payload"]["number"] not in ends]
    return opened[-1] if opened else None


@dataclass(frozen=True)
class Freeze:
    status: str  # free | waiver | frozen
    number: int | None = None
    before: Mapping[str, str] | None = None  # reference hashes (start, or last waiver)
    after: Mapping[str, str] | None = None
    diff: tuple[str, ...] = ()

    @property
    def message(self) -> str:
        names = ", ".join(NAMES[k] for k in self.diff)
        return (
            f"season {self.number} frozen: {names} changed since the start ({', '.join(self.diff)}); "
            "to waive, write a reason in var/SEASON_WAIVER"
        )


def verify_freeze(
    events: Sequence[Mapping[str, Any]], hashes: Mapping[str, str], t: int, reason: str
) -> Freeze:
    """Freeze state of the open season at time `t` (cycle or wake-up). Free if no season is open or if
    `t >= planned_cycle_end` (the end cycle is no longer subject to the freeze)."""
    start = season_open(events)
    if start is None or t >= start["planned_cycle_end"]:
        return Freeze("free")
    ref = {k: start[k] for k in HASHES if k in start}
    for e in events:
        if e["type"] == "season_waiver" and e["payload"]["number"] == start["number"]:
            ref = dict(e["payload"]["hashes_after"])
    diff = tuple(k for k in HASHES if k in ref and hashes[k] != ref[k])
    if not diff:
        return Freeze("free", start["number"], ref, dict(hashes))
    return Freeze("waiver" if reason else "frozen", start["number"], ref, dict(hashes), diff)
