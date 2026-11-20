"""Hash-chained JSONL journal (source of truth, see docs/SPEC-MVP.md §4).

One line per event: {seq, ts, type, payload, prev_hash, hash}.
`hash = sha256(canonical(record without "hash"))`. No float is accepted, neither on write nor on read.
A truncated line at the end of the file is reported (verify) or refused (append), never silently repaired.
"""

from __future__ import annotations

import dataclasses
import fcntl
import hashlib
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from arena.types import Bar, Fill, Intent, Quote, Side, Verdict

GENESIS_HASH = "0" * 64
_TAIL_CHUNK = 65536


class JournalError(Exception):
    """Generic journal error."""


class FloatInPayloadError(JournalError, TypeError):
    """A float was found in an event (forbidden: use integers, strings, booleans, null, lists, objects)."""


class JournalCorruptError(JournalError):
    """The file is corrupt (truncated line, invalid JSON, broken hash): writing to it is refused."""


# ---------------------------------------------------------------------------
# Canonical form and hashing
# ---------------------------------------------------------------------------


def canonical(obj: Any) -> bytes:
    """UTF-8 canonical form of a JSON object (sorted keys, no spaces, non-ASCII preserved)."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record_hash(record: dict[str, Any]) -> str:
    """Hash of a record: sha256 of its canonical form without the "hash" field."""
    return sha256_hex(canonical({k: v for k, v in record.items() if k != "hash"}))


def find_float(obj: Any, path: str = "$") -> str | None:
    """Path of the first float found in `obj`, or None."""
    if isinstance(obj, float):
        return path
    if isinstance(obj, dict):
        for k, v in obj.items():
            found = find_float(v, f"{path}.{k}")
            if found:
                return found
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            found = find_float(v, f"{path}[{i}]")
            if found:
                return found
    return None


def check_no_float(obj: Any) -> None:
    """Raise FloatInPayloadError if `obj` contains a float."""
    where = find_float(obj)
    if where:
        raise FloatInPayloadError(f"float forbidden in the journal (at {where})")


# ---------------------------------------------------------------------------
# Serialization of the types.py contracts
# ---------------------------------------------------------------------------


def to_payload(obj: Any) -> Any:
    """Recursively convert dataclasses, enums and tuples to plain JSON objects (enums -> str)."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_payload(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Enum):
        return to_payload(obj.value)
    if isinstance(obj, dict):
        return {str(k): to_payload(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_payload(v) for v in obj]
    return obj


def _fields(cls: type, payload: dict[str, Any]) -> dict[str, Any]:
    """Payload fields known to the dataclass (fields added by a module are ignored)."""
    names = {f.name for f in dataclasses.fields(cls)}
    return {k: v for k, v in payload.items() if k in names}


def intent_from_payload(payload: dict[str, Any]) -> Intent:
    d = _fields(Intent, payload)
    d["side"] = Side(d["side"])
    return Intent(**d)


def verdict_from_payload(payload: dict[str, Any]) -> Verdict:
    d = _fields(Verdict, payload)
    d["reasons"] = tuple(d.get("reasons", ()))
    return Verdict(**d)


def fill_from_payload(payload: dict[str, Any]) -> Fill:
    d = _fields(Fill, payload)
    d["side"] = Side(d["side"])
    return Fill(**d)


def bar_from_payload(payload: dict[str, Any]) -> Bar:
    return Bar(**_fields(Bar, payload))


def quote_from_payload(payload: dict[str, Any]) -> Quote:
    return Quote(**_fields(Quote, payload))


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifyError:
    code: str  # hash_mismatch, prev_hash_mismatch, seq_gap, float_present, truncated_tail, bad_json, ...
    line: int  # line number (1-based)
    seq: int | None  # seq read from the line, or expected when the line is unreadable
    message: str


@dataclass(frozen=True)
class VerifyReport:
    ok: bool
    n_records: int
    head_seq: int | None
    head_hash: str  # chain head (GENESIS_HASH if the journal is empty)
    errors: tuple[VerifyError, ...] = ()

    def codes(self) -> list[str]:
        return [e.code for e in self.errors]


def _no_const(name: str) -> Any:
    raise ValueError(f"forbidden JSON constant: {name}")


def _loads(raw: bytes) -> Any:
    # parse_float returns a float: find_float detects it afterwards (1.0 and 1e3 are floats too).
    return json.loads(raw.decode("utf-8"), parse_constant=_no_const)


def verify(path: str | Path) -> VerifyReport:
    """Check the hash chain, seq continuity, and absence of floats and of a truncated line."""
    p = Path(path)
    errors: list[VerifyError] = []
    if not p.exists():
        return VerifyReport(True, 0, None, GENESIS_HASH)
    expected_seq = 0
    prev_hash = GENESIS_HASH
    head_seq: int | None = None
    n = 0
    data = p.read_bytes()
    lines = data.split(b"\n")
    ends_with_newline = data.endswith(b"\n") or not data
    if ends_with_newline and lines:
        lines.pop()  # last element is empty after the final "\n"
    for i, raw in enumerate(lines, start=1):
        is_last = i == len(lines)
        if is_last and not ends_with_newline:
            errors.append(
                VerifyError("truncated_tail", i, expected_seq, "last line has no line ending: write interrupted")
            )
            break
        if not raw.strip():
            errors.append(VerifyError("blank_line", i, expected_seq, "blank line"))
            continue
        try:
            rec = _loads(raw)
        except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError derive from it
            errors.append(VerifyError("bad_json", i, expected_seq, f"unreadable JSON: {exc}"))
            continue
        need = {"seq", "ts", "type", "payload", "prev_hash", "hash"}
        if not isinstance(rec, dict) or not need <= rec.keys():
            errors.append(VerifyError("bad_record", i, expected_seq, "required fields missing"))
            continue
        seq = rec["seq"]
        if isinstance(seq, bool) or not isinstance(seq, int):
            errors.append(VerifyError("bad_record", i, expected_seq, "seq is not an integer"))
            continue
        if seq != expected_seq:
            errors.append(VerifyError("seq_gap", i, seq, f"expected seq {expected_seq}, read {seq}"))
        if rec["prev_hash"] != prev_hash:
            errors.append(VerifyError("prev_hash_mismatch", i, seq, "prev_hash does not match the previous line"))
        if rec["hash"] != record_hash(rec):
            errors.append(VerifyError("hash_mismatch", i, seq, "recomputed hash differs from the stored hash"))
        where = find_float(rec)
        if where:
            errors.append(VerifyError("float_present", i, seq, f"float present at {where}"))
        prev_hash = rec["hash"] if isinstance(rec["hash"], str) else prev_hash
        expected_seq = seq + 1
        head_seq = seq
        n += 1
    return VerifyReport(not errors, n, head_seq, prev_hash, tuple(errors))


# ---------------------------------------------------------------------------
# Reading the last line
# ---------------------------------------------------------------------------


def _tail_record(path: Path) -> dict[str, Any] | None:
    """Last record of the file (read from the end). Raises JournalCorruptError if unreadable."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    with open(path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        f.seek(size - 1)
        if f.read(1) != b"\n":
            raise JournalCorruptError(f"{path}: last line truncated (no line ending)")
        buf = b""
        pos = size - 1  # exclude the final "\n"
        while True:
            start = max(0, pos - _TAIL_CHUNK)
            f.seek(start)
            buf = f.read(pos - start) + buf
            pos = start
            idx = buf.rfind(b"\n")
            if idx != -1 or pos == 0:
                line = buf[idx + 1 :]
                break
    try:
        rec = _loads(line)
        ok = isinstance(rec, dict) and isinstance(rec.get("seq"), int) and rec.get("hash") == record_hash(rec)
    except ValueError:
        ok = False
    if not ok:
        raise JournalCorruptError(f"{path}: last line unreadable or invalid hash")
    return rec


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------


class Journal:
    """Append-only journal. Several processes may write (exclusive flock on `<path>.lock`)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    def append(self, type: str, payload: Any, ts: int) -> dict[str, Any]:
        """Append an event and return the full record. `payload`: dict or dataclass from types.py."""
        if not isinstance(type, str) or not type:
            raise JournalError("invalid event type")
        if isinstance(ts, float):
            raise FloatInPayloadError("ts must be an integer (UTC seconds), not a float")
        if isinstance(ts, bool) or not isinstance(ts, int):
            raise JournalError("ts must be an integer (UTC seconds)")
        body = to_payload(payload)
        if not isinstance(body, dict):
            raise JournalError("the payload must be an object")
        check_no_float(body)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists()
        with open(self.lock_path, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                last = _tail_record(self.path)
                seq = 0 if last is None else last["seq"] + 1
                prev = GENESIS_HASH if last is None else last["hash"]
                rec: dict[str, Any] = {"seq": seq, "ts": ts, "type": type, "payload": body, "prev_hash": prev}
                rec["hash"] = record_hash(rec)
                line = canonical(rec) + b"\n"
                with open(self.path, "ab") as f:
                    f.write(line)
                    f.flush()
                    os.fsync(f.fileno())
                if not existed:
                    dfd = os.open(self.path.parent, os.O_RDONLY)
                    try:
                        os.fsync(dfd)
                    finally:
                        os.close(dfd)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
        return rec

    def iter_events(self, *, strict: bool = True) -> Iterator[dict[str, Any]]:
        """Iterate over the records. Does not check the hashes (see verify).

        strict=True: a truncated trailing line or unreadable JSON raises JournalCorruptError.
        strict=False: a last line without a line ending is ignored (reader concurrent with a write).
        """
        if not self.path.exists():
            return
        with open(self.path, "rb") as f:
            for lineno, raw in enumerate(f, start=1):
                if not raw.endswith(b"\n"):
                    if strict:
                        raise JournalCorruptError(f"{self.path} line {lineno}: truncated")
                    return
                try:
                    yield _loads(raw)
                except ValueError as exc:
                    raise JournalCorruptError(f"{self.path} line {lineno}: unreadable JSON ({exc})") from exc

    def events(self) -> list[dict[str, Any]]:
        return list(self.iter_events())

    def last(self) -> dict[str, Any] | None:
        """Last record, or None if the journal is empty."""
        return _tail_record(self.path)

    def verify(self) -> VerifyReport:
        return verify(self.path)
