"""Local cache of perpetual market data, sharded by day or month, deduplicated by `ts`.

Layout under `<root>` (default `var-perp/data/kraken_futures/`):

    candles/<kind>/<kraken_symbol>/<interval>/<YYYY-MM-DD>.jsonl
    funding/<kraken_symbol>/<YYYY-MM>.jsonl
    open_interest/<kraken_symbol>/<interval>/<YYYY-MM>.jsonl
    books/<kraken_symbol>/<YYYY-MM-DD>.jsonl
    tickers/<YYYY-MM-DD>.jsonl          one snapshot per collection run (all tickers + EUR/USD)

A record already stored is never overwritten (first write wins: a closed candle is immutable). New records
are APPENDED to their shard (then fsync). A shard holding an unreadable line (for instance a line torn by a
crash during an append) is quarantined as `<shard>.jsonl.corrupt-<n>`, rebuilt from its readable lines,
and reported in `PerpDataStore.warnings`: one bad line never blocks a series.

No look-ahead: the collector only stores candles that are closed, and `PerpDataStore.closed_candles`
filters again on `ts + interval_s <= until_ts`. `Series.load` itself only filters on `ts`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from arena.perp.types import (
    BookSnapshot,
    Candle,
    FundingRate,
    FxQuote,
    OpenInterest,
    PerpTicker,
)


class _Record(Protocol):
    ts: int

    def to_dict(self) -> dict[str, Any]: ...


def _fsync_dir(d: Path) -> None:
    """Makes a file creation or rename durable (POSIX)."""
    fd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _day(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")


def _month(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m")


def interval_label(interval_s: int) -> str:
    if interval_s % 86400 == 0:
        return f"{interval_s // 86400}d"
    if interval_s % 3600 == 0:
        return f"{interval_s // 3600}h"
    if interval_s % 60 == 0:
        return f"{interval_s // 60}m"
    return f"{interval_s}s"


class Series[R: _Record]:
    """One time series of records keyed by `ts`, stored in shard files named by `shard_of(ts)`."""

    def __init__(
        self,
        directory: Path,
        decode: Callable[[dict[str, Any]], R],
        shard_of: Callable[[int], str],
        warnings: list[str] | None = None,
    ):
        self.dir = directory
        self._decode = decode
        self._shard_of = shard_of
        self.warnings = warnings if warnings is not None else []

    def _path(self, shard: str) -> Path:
        return self.dir / f"{shard}.jsonl"

    def _shards(self) -> list[str]:
        if not self.dir.exists():
            return []
        return sorted(p.stem for p in self.dir.glob("*.jsonl"))

    def _read(self, shard: str) -> dict[int, R]:
        p = self._path(shard)
        out: dict[int, R] = {}
        if not p.exists():
            return out
        bad: list[int] = []
        with p.open(encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f, 1):
                if not line.strip():
                    continue
                if not line.endswith("\n"):
                    break  # the last line is being appended by another process: not corruption, ignore it
                try:
                    rec = self._decode(json.loads(line))
                except (ValueError, TypeError, KeyError):
                    bad.append(n)
                    continue
                out.setdefault(rec.ts, rec)
        if bad:
            self._quarantine(shard, out, bad)
        return out

    def _quarantine(self, shard: str, good: dict[int, R], bad: list[int]) -> None:
        p = self._path(shard)
        n = 1
        while (dest := p.with_name(f"{p.name}.corrupt-{n}")).exists():
            n += 1
        os.replace(p, dest)
        self._rewrite(shard, good)
        self.warnings.append(
            f"{p}: {len(bad)} unreadable line(s) {bad[:5]}, kept in {dest.name}, shard rebuilt"
        )

    @staticmethod
    def _line(rec: _Record) -> str:
        return json.dumps(rec.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"

    def _rewrite(self, shard: str, records: dict[int, R]) -> None:
        p = self._path(shard)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for ts in sorted(records):
                f.write(self._line(records[ts]))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
        _fsync_dir(p.parent)

    def add(self, records: Iterable[R]) -> int:
        """Append the records not stored yet (dedup by ts, existing wins). Returns how many were added."""
        by_shard: dict[str, dict[int, R]] = {}
        for r in records:
            by_shard.setdefault(self._shard_of(r.ts), {}).setdefault(r.ts, r)
        added = 0
        for shard, new in sorted(by_shard.items()):
            have = self._read(shard)
            fresh = [new[ts] for ts in sorted(new) if ts not in have]
            if not fresh:
                continue
            p = self._path(shard)
            created = not p.exists()
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                for r in fresh:
                    f.write(self._line(r))
                f.flush()
                os.fsync(f.fileno())
            if created:
                _fsync_dir(p.parent)
            added += len(fresh)
        return added

    def last_ts(self) -> int | None:
        for shard in reversed(self._shards()):
            have = self._read(shard)
            if have:
                return max(have)
        return None

    def first_ts(self) -> int | None:
        for shard in self._shards():
            have = self._read(shard)
            if have:
                return min(have)
        return None

    def load(self, from_ts: int, until_ts: int) -> list[R]:
        """Records with from_ts <= ts < until_ts, sorted. Callers add their own closure rule."""
        if until_ts <= from_ts:
            return []
        lo, hi = self._shard_of(from_ts), self._shard_of(until_ts - 1)
        out: list[R] = []
        for shard in self._shards():
            if lo <= shard <= hi:
                out.extend(r for r in self._read(shard).values() if from_ts <= r.ts < until_ts)
        out.sort(key=lambda r: r.ts)
        return out


@dataclass(frozen=True)
class TickerSnapshot:
    """What one collection run saw: the tickers of every instrument and the EUR/USD quote."""

    ts: int
    tickers: tuple[PerpTicker, ...]
    fx: FxQuote | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "tickers": [t.to_dict() for t in self.tickers],
            "fx": self.fx.to_dict() if self.fx else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TickerSnapshot:
        return cls(
            ts=d["ts"],
            tickers=tuple(PerpTicker.from_dict(t) for t in d["tickers"]),
            fx=FxQuote.from_dict(d["fx"]) if d.get("fx") else None,
        )


class PerpDataStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.warnings: list[str] = []  # quarantined shards, collected by the run report

    def candles(self, kind: str, kraken_symbol: str, interval_s: int) -> Series[Candle]:
        d = self.root / "candles" / kind / kraken_symbol / interval_label(interval_s)
        return Series(d, Candle.from_dict, _day, self.warnings)

    def funding(self, kraken_symbol: str) -> Series[FundingRate]:
        return Series(self.root / "funding" / kraken_symbol, FundingRate.from_dict, _month, self.warnings)

    def open_interest(self, kraken_symbol: str, interval_s: int) -> Series[OpenInterest]:
        d = self.root / "open_interest" / kraken_symbol / interval_label(interval_s)
        return Series(d, OpenInterest.from_dict, _month, self.warnings)

    def books(self, kraken_symbol: str) -> Series[BookSnapshot]:
        return Series(self.root / "books" / kraken_symbol, BookSnapshot.from_dict, _day, self.warnings)

    def tickers(self) -> Series[TickerSnapshot]:
        return Series(self.root / "tickers", TickerSnapshot.from_dict, _day, self.warnings)

    def closed_candles(
        self, kind: str, kraken_symbol: str, interval_s: int, from_ts: int, until_ts: int
    ) -> list[Candle]:
        """Candles CLOSED at `until_ts` (ts + interval_s <= until_ts), from `from_ts`. No look-ahead."""
        series = self.candles(kind, kraken_symbol, interval_s)
        return [c for c in series.load(from_ts, until_ts) if c.ts + interval_s <= until_ts]


def missing_steps(present: Sequence[int], step_s: int, from_ts: int, until_ts: int) -> list[int]:
    """Timestamps on the `step_s` grid in [from_ts, until_ts) absent from `present`."""
    start = -(-from_ts // step_s) * step_s
    have = set(present)
    return [ts for ts in range(start, until_ts, step_s) if ts not in have]
