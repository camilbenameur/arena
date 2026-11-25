"""Pauses of a league for absence (dormancy), drawn as a band on the curves.

With no presence confirmation (`arena ack`) for 7 days, no new entries; at 9 days, the deciding portfolios are
flattened (arena/ops/dormancy.py). The curves keep being recorded meanwhile, flat: the band tells the reader why.

A pause runs from the reference + 7 days (entries blocked) to the next confirmation. The reference is the league's
start, then each confirmation. The confirmations come from the `operator_ack` events of the spot journal (written
by `arena ack`) and from the modification time of `var/ack`, which also covers the confirmations made before
that event existed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from arena.ops.dormancy import NO_ENTRY_S


def ack_times(events: Iterable[Mapping[str, Any]], ack_file: Path | None) -> list[int]:
    acks: set[int] = set()
    for e in events:
        if e.get("type") == "operator_ack":
            ts = e.get("payload", {}).get("ack_ts")
            if isinstance(ts, int) and not isinstance(ts, bool):
                acks.add(ts)
    if ack_file is not None:
        try:
            acks.add(int(ack_file.stat().st_mtime))
        except OSError:
            pass
    return sorted(acks)


def dormancy_pauses(acks: Iterable[int], start_ts: int | None, now_ts: int) -> list[list[int]]:
    """[[from, to], ...] in order; an ongoing pause ends at `now_ts`."""
    if start_ts is None:
        return []
    out: list[list[int]] = []
    ref = start_ts
    for ack in sorted(a for a in acks if a > start_ts):
        if ack - ref >= NO_ENTRY_S:
            out.append([ref + NO_ENTRY_S, ack])
        ref = ack
    if now_ts - ref >= NO_ENTRY_S:
        out.append([ref + NO_ENTRY_S, now_ts])
    return out


def clip(pauses: list[list[int]], xs: list[int]) -> list[list[int]]:
    """The pauses that overlap the chart's time range, clipped to it."""
    if len(xs) < 2:
        return []
    lo, hi = xs[0], xs[-1]
    return [[max(a, lo), min(b, hi)] for a, b in pauses if b > lo and a < hi]
