"""Local bar cache: var/data/<source>/<symbol>_<interval>.jsonl, deduplicated by ts.

`load` returns only bars CLOSED before `until_ts` (no look-ahead leak). The root is a
parameter (tests use tmp_path).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path

from arena.data import DataError
from arena.data.binance import DayBar
from arena.types import Bar

_CODECS: dict[str, type] = {"kraken": Bar, "binance": DayBar}


def interval_label(interval_s: int) -> str:
    if interval_s % 86400 == 0:
        return f"{interval_s // 86400}d"
    if interval_s % 3600 == 0:
        return f"{interval_s // 3600}h"
    return f"{interval_s}s"


class BarStore:
    """Cache for one source ("kraken" -> Bar, "binance" -> DayBar)."""

    def __init__(self, root: Path | str, source: str) -> None:
        if source not in _CODECS:
            raise ValueError(f"unknown source: {source!r}")
        self.root = Path(root)
        self.source = source
        self._cls = _CODECS[source]

    def path(self, symbol: str, interval_s: int) -> Path:
        safe = symbol.replace("/", "-")
        return self.root / self.source / f"{safe}_{interval_label(interval_s)}.jsonl"

    def _read(self, symbol: str, interval_s: int) -> dict[int, Bar | DayBar]:
        p = self.path(symbol, interval_s)
        out: dict[int, Bar | DayBar] = {}
        if not p.exists():
            return out
        with p.open(encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    bar = self._cls(**json.loads(line))
                except (ValueError, TypeError) as exc:
                    raise DataError(f"{p}:{n}: unreadable line") from exc
                out.setdefault(bar.ts, bar)  # first occurrence kept: a closed bar is immutable
        return out

    def _write(self, symbol: str, interval_s: int, bars: dict[int, Bar | DayBar]) -> None:
        p = self.path(symbol, interval_s)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for ts in sorted(bars):
                f.write(json.dumps(asdict(bars[ts]), sort_keys=True, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)

    def add(self, symbol: str, interval_s: int, new: Sequence[Bar | DayBar]) -> int:
        """Merge bars (dedup by ts, the existing one wins). Returns the number of bars added."""
        have = self._read(symbol, interval_s)
        added = 0
        for b in new:
            if b.ts not in have:
                have[b.ts] = b
                added += 1
        if added:
            self._write(symbol, interval_s, have)
        return added

    def last_ts(self, symbol: str, interval_s: int) -> int | None:
        have = self._read(symbol, interval_s)
        return max(have) if have else None

    def update(
        self,
        symbol: str,
        interval_s: int,
        fetch: Callable[[int | None], Sequence[Bar | DayBar]],
    ) -> int:
        """Incremental update: calls `fetch(since)` (since = last stored ts, None if the cache is empty)."""
        since = self.last_ts(symbol, interval_s)
        return self.add(symbol, interval_s, fetch(since))

    def load(self, symbol: str, interval_s: int, until_ts: int) -> list[Bar | DayBar]:
        """Bars closed before `until_ts` (ts + interval_s <= until_ts), sorted. Never a bar >= until_ts."""
        have = self._read(symbol, interval_s)
        return [have[ts] for ts in sorted(have) if ts + interval_s <= until_ts]

    def gaps(self, symbol: str, interval_s: int, until_ts: int, from_ts: int | None = None) -> list[int]:
        """ts of the missing bars from `from_ts` (default: first cached bar) up to the bars closed before `until_ts`.

        Note: Kraken emits no bar without a trade; a gap can be legitimate on an illiquid pair.
        """
        have = self._read(symbol, interval_s)
        if from_ts is None:
            if not have:
                return []
            from_ts = min(have)
        last_closed = (until_ts // interval_s) * interval_s - interval_s
        return [ts for ts in range(from_ts, last_closed + 1, interval_s) if ts not in have]
