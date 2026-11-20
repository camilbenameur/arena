"""Dormancy: if the operator has not confirmed their presence (`arena ack`) for 7 days, no new entries;
at 9 days, everything is flattened (docs/SPEC-MVP.md §12).

Reference = modification time of `var/ack`; without an ack, the first journal event (startup).
"""

from __future__ import annotations

import os

from arena.paths import Paths

DAY_S = 86_400
NO_ENTRY_S = 7 * DAY_S
FLATTEN_S = 9 * DAY_S

OK, NO_ENTRIES, FLATTEN = "ok", "no_entries", "flatten"


def write_ack(paths: Paths, now_ts: int) -> None:
    paths.ack.parent.mkdir(parents=True, exist_ok=True)
    paths.ack.touch()
    os.utime(paths.ack, (now_ts, now_ts))


def ack_ts(paths: Paths) -> int | None:
    try:
        return int(paths.ack.stat().st_mtime)
    except FileNotFoundError:
        return None


def age_s(paths: Paths, now_ts: int, since_ts: int) -> int:
    """Seconds elapsed since the last ack (or since `since_ts` if there has never been one)."""
    ref = ack_ts(paths)
    if ref is None:
        ref = since_ts
    return max(0, now_ts - ref)


def level(age: int) -> str:
    if age >= FLATTEN_S:
        return FLATTEN
    if age >= NO_ENTRY_S:
        return NO_ENTRIES
    return OK
