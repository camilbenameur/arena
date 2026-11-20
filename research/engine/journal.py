"""Hash-chained journal of research trials (wrapper around `arena.journal.Journal`) and external anchoring.

Event types: `lab_genesis` (first line), `start` (before the computation), `end` (after). No float:
metrics are decimal strings with 12 significant digits (`decimal12`). The technical detail of a
failure never goes into this journal but into `<journal>.technical_detail.jsonl`, read by the orchestrator; it
contains no text coming from a strategy (closed code, standard exception type, day number).

Timing channel: all written timestamps (journal, technical journal, anchors) are rounded to the minute.

Anchoring: each `research_anchor` event of the arena journal carries the head, the number of lines, the journal
name AND the hash of the `lab_genesis` line (first line). `verify_anchor` compares the latest anchor
(whatever name it was written under) with the journal: name, genesis, length, head. A renamed, recreated or
rewritten journal is refused.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from arena.journal import Journal, JournalError

LAB_REPO = Path(__file__).resolve().parents[2]  # repository holding the frozen-lab tag; override via lab_repo
LAB_TAG = "final-freeze"
GENESIS_TYPE, START_TYPE, END_TYPE, ANCHOR_TYPE = "lab_genesis", "start", "end", "research_anchor"


class AnchorError(JournalError):
    """The research journal is shorter than the latest anchor, or the anchored head is not in it."""


def decimal12(x: Any) -> str:
    """Decimal string with 12 significant digits (explicit `nan`, `inf`); never a float."""
    if isinstance(x, bool):
        return str(x).lower()
    if isinstance(x, int):
        return str(x)
    x = float(x)
    if math.isnan(x):
        return "nan"
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return format(x, ".12g")


def _without_float(obj: Any) -> Any:
    if isinstance(obj, float):
        return decimal12(obj)
    if isinstance(obj, dict):
        return {str(k): _without_float(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_without_float(v) for v in obj]
    return obj


def canonical_params(params: dict) -> str:
    return json.dumps(params, sort_keys=True, separators=(",", ":"), allow_nan=False)


class ResearchJournal:
    def __init__(self, path: str | Path, *, lab_repo: Path | str = LAB_REPO, lab_tag: str = LAB_TAG,
                 clock: Callable[[], int] | None = None):
        self.path = Path(path)
        self.journal = Journal(self.path)
        self.lab_repo = Path(lab_repo)
        self.lab_tag = lab_tag
        self._clock = clock or (lambda: int(time.time()))  # rounded to the minute by `_ts`
        self.technical_path = self.path.with_name(self.path.name + ".technical_detail.jsonl")

    # --- writing --------------------------------------------------------------------------------
    def _ts(self) -> int:
        """Timestamp rounded to the minute (the timing channel of a strategy that slows down or speeds up is
        thus reduced to a 60 s step)."""
        h = int(self._clock())
        return h - h % 60

    def _add(self, type_: str, payload: dict) -> dict:
        return self.journal.append(type_, _without_float(payload), self._ts())

    def lab_genesis(self) -> dict:
        """First line: head (sha256 of the last line) and number of lines of the lab journal at tag
        `final-freeze`, read as is with `git show`. Refuses if the journal is not empty."""
        if self.journal.last() is not None:
            raise JournalError("lab_genesis must be the first line of an empty journal")
        r = subprocess.run(["git", "-C", str(self.lab_repo), "show", f"{self.lab_tag}:trials.jsonl"],
                           capture_output=True, check=False, timeout=60)
        if r.returncode != 0:
            raise JournalError(f"git show {self.lab_tag}:trials.jsonl failed : {r.stderr.decode()[-200:]}")
        lines = [line for line in r.stdout.split(b"\n") if line]
        return self._add(GENESIS_TYPE, {
            "tag": self.lab_tag, "n_lines": len(lines),
            "head": hashlib.sha256(lines[-1]).hexdigest() if lines else "0" * 64,
            "file_sha256": hashlib.sha256(r.stdout).hexdigest()})

    def initialize(self) -> None:
        """Writes the genesis if the journal is empty; otherwise checks that it is the first line."""
        if self.journal.last() is None:
            self.lab_genesis()
            return
        first = next(self.journal.iter_events())
        if first["type"] != GENESIS_TYPE:
            raise JournalError("the first line of the journal is not lab_genesis")

    def start(self, payload: dict) -> dict:
        return self._add(START_TYPE, payload)

    def end(self, payload: dict) -> dict:
        return self._add(END_TYPE, payload)

    def technical_detail(self, trial_id: str, detail: str) -> None:
        """Detail of a failure, for the orchestrator only (unchained file)."""
        line = json.dumps({"ts": self._ts(), "id": trial_id, "detail": detail[-4000:]},
                           ensure_ascii=False)
        with open(self.technical_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    # --- reading ---------------------------------------------------------------------------------
    def events(self, type_: str | None = None) -> list[dict]:
        return [e for e in self.journal.iter_events() if type_ is None or e["type"] == type_]

    def n_ids(self) -> int:
        """Number of trials started (a trial without `end` counts)."""
        return len(self.events(START_TYPE))

    def next_id(self) -> str:
        return f"R{self.n_ids() + 1:04d}"

    def trials(self) -> dict[str, dict]:
        """{id: {"start": payload, "end": payload|None}} re-read from the file."""
        out: dict[str, dict] = {}
        for e in self.journal.iter_events():
            if e["type"] == START_TYPE:
                out[e["payload"]["id"]] = {"start": e["payload"], "end": None}
            elif e["type"] == END_TYPE:
                out[e["payload"]["id"]]["end"] = e["payload"]
        return out

    def n_lines(self) -> int:
        last = self.journal.last()
        return 0 if last is None else last["seq"] + 1

    def head(self) -> str:
        last = self.journal.last()
        return "0" * 64 if last is None else last["hash"]

    def verify(self) -> None:
        report = self.journal.verify()
        if not report.ok:
            raise JournalError(f"research journal corrupted : {report.codes()}")

    # --- anchoring ---------------------------------------------------------------------------------
    def genesis_hash(self) -> str | None:
        """Hash of the first line (`lab_genesis`); None if the journal is empty."""
        first = next(iter(self.journal.iter_events()), None)
        return None if first is None else first["hash"]

    def anchor(self, arena_journal_path: str | Path | None) -> dict | None:
        """Writes `research_anchor {head, n_lines, journal, genesis}` into the arena journal, only if
        a path is given. Returns the record written (or None)."""
        if arena_journal_path is None:
            return None
        return Journal(arena_journal_path).append(
            ANCHOR_TYPE, {"head": self.head(), "n_lines": self.n_lines(), "journal": self.path.name,
                         "genesis": self.genesis_hash()}, self._ts())

    def verify_anchor(self, arena_journal_path: str | Path | None) -> None:
        """Refuses a journal whose name or genesis does not match the latest anchor, that is shorter than
        it, or whose anchored head is missing. With no anchor in the arena journal: nothing to verify."""
        self.verify()
        if arena_journal_path is None:
            return
        anchors = [e for e in Journal(arena_journal_path).iter_events() if e["type"] == ANCHOR_TYPE]
        if not anchors:
            return
        latest = anchors[-1]["payload"]
        if latest.get("journal") != self.path.name:
            raise AnchorError("journal renamed or another journal: the name does not match the latest anchor")
        if latest.get("genesis") != self.genesis_hash():
            raise AnchorError("the journal genesis does not match the latest anchor (journal recreated)")
        n = latest["n_lines"]
        if self.n_lines() < n:
            raise AnchorError(f"journal of {self.n_lines()} lines, latest anchor at {n}")
        for e in self.journal.iter_events():
            if e["seq"] == n - 1:
                if e["hash"] != latest["head"]:
                    raise AnchorError("the anchored head is not in the journal (history rewritten)")
                return
        raise AnchorError("anchored line not found")
