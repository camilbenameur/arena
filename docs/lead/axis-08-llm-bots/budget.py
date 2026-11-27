"""Hard spend ledger (JSONL, append-only) for the LLM-bot backtests.

Cost of a response = usage x list price (batch: -50%, applied to every token class). Before anything is submitted the
projected worst case (input estimate + max_tokens output for every request) is RESERVED; submission is refused when
settled spend + open reservations + this projection would exceed the cap given on the command line (itself never above
HARD_TOTAL_CAP). Reservations are settled with the real usage when the results arrive.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

HARD_TOTAL_CAP = 160.0
LEDGER = Path.home() / "dev" / "_arena-data" / "axis-08" / "spend.jsonl"


@dataclass(frozen=True)
class Price:
    inp: float  # USD per MTok
    out: float
    cache_read: float
    cache_write: float  # 5-minute write = 1.25 x input


# list prices; cache reads as documented for Sonnet 5.5 / Opus 5.5 / Fable 5.2; Haiku 5.5 assumed at 0.1 x input
PRICES = {
    "claude-haiku-5-5": Price(0.10, 0.50, 0.01, 0.125),
    "claude-sonnet-5-5": Price(2.00, 10.00, 0.10, 2.50),
    "claude-opus-5-5": Price(4.00, 20.00, 0.20, 5.00),
    "claude-fable-5-2": Price(8.00, 40.00, 0.20, 10.00),
}


class BudgetExceeded(RuntimeError):
    pass


def usage_cost(model: str, usage: dict, batch: bool) -> float:
    p = PRICES[model]
    usd = (
        usage.get("input_tokens", 0) * p.inp
        + usage.get("output_tokens", 0) * p.out
        + usage.get("cache_read_input_tokens", 0) * p.cache_read
        + usage.get("cache_creation_input_tokens", 0) * p.cache_write
    ) / 1e6
    return usd * (0.5 if batch else 1.0)


def projected_cost(model: str, input_tokens: int, max_output_tokens: int, n: int, batch: bool) -> float:
    """Worst case: nothing cached, every request writes max_tokens."""
    return usage_cost(model, {"input_tokens": input_tokens * n, "output_tokens": max_output_tokens * n}, batch)


class Ledger:
    """Append-only JSONL. Every read-modify-write (reserve, release, deduplicated actual) holds an exclusive flock on a
    sidecar lock file for its whole duration, so two processes can never both pass the cap check on the same totals."""

    def __init__(self, path: Path = LEDGER):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = path.with_name(path.name + ".lock")

    @contextmanager
    def _locked(self):
        with self.lock_path.open("a") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)

    def _events(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for x in self.path.read_text().splitlines():
            try:
                out.append(json.loads(x))
            except ValueError:  # a torn last line can only be seen by a reader outside the lock
                continue
        return out

    @staticmethod
    def _open_reservations(events: list[dict]) -> dict[str, dict]:
        res: dict[str, dict] = {}
        for e in events:
            if e["kind"] == "reserve":
                res[e["key"]] = e
            elif e["kind"] in ("settle", "release"):
                res.pop(e["key"], None)
        return res

    @classmethod
    def _totals(cls, events: list[dict]) -> dict:
        settled = sum(e["usd"] for e in events if e["kind"] == "actual")
        open_res = sum(e["usd"] for e in cls._open_reservations(events).values())
        return {"settled": settled, "reserved": open_res, "total": settled + open_res}

    def totals(self) -> dict:
        return self._totals(self._events())

    def open_reservations(self) -> list[dict]:
        return list(self._open_reservations(self._events()).values())

    def _append(self, ev: dict) -> None:
        """Caller holds the lock."""
        with self.path.open("a") as f:
            f.write(json.dumps({"ts": int(time.time()), **ev}) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def reserve(self, key: str, usd: float, cap: float, note: str = "") -> str:
        """Atomic: read totals, check the cap and append, all under one lock. Returns the reservation id, unique per call
        (key + random suffix): a second submission with the same key never overwrites the first."""
        if cap > HARD_TOTAL_CAP:
            raise BudgetExceeded(f"cap {cap} above the hard total {HARD_TOTAL_CAP}")
        with self._locked():
            t = self._totals(self._events())
            if t["total"] + usd > cap + 1e-9:
                raise BudgetExceeded(
                    f"refused: settled {t['settled']:.2f} + reserved {t['reserved']:.2f} + this {usd:.2f} > cap {cap:.2f} USD"
                )
            rid = f"{key}#{uuid.uuid4().hex[:8]}"
            self._append({"kind": "reserve", "key": rid, "usd": round(usd, 6), "note": note})
        return rid

    def actual(self, rid: str, model: str, usage: dict, batch: bool, custom_id: str = "", dedupe: str | None = None) -> float:
        """Settles one response. With `dedupe` (batch id + custom_id for batches) the same actual is never appended twice:
        a repeated --collect returns the amount already booked."""
        usd = round(usage_cost(model, usage, batch), 6)
        with self._locked():
            if dedupe is not None:
                for e in self._events():
                    if e["kind"] == "actual" and e.get("dedupe") == dedupe:
                        return e["usd"]
            self._append({"kind": "actual", "key": rid, "custom_id": custom_id, "dedupe": dedupe, "model": model,
                          "batch": batch, "usage": usage, "usd": usd})
        return usd

    def release(self, rid: str) -> bool:
        """Closes an open reservation; idempotent (False when it was not open)."""
        with self._locked():
            if rid not in self._open_reservations(self._events()):
                return False
            self._append({"kind": "release", "key": rid})
            return True

    def release_stale(self, older_than_s: float, now: float | None = None) -> list[str]:
        """Releases every open reservation older than `older_than_s`. Use only after checking in the console that the
        corresponding batch or call did not run (or was collected), otherwise real spend would go uncounted."""
        now = time.time() if now is None else now
        out = []
        for e in self.open_reservations():
            if now - e["ts"] >= older_than_s and self.release(e["key"]):
                out.append(e["key"])
        return out
