"""Journal JSONL chaîné (source de vérité, voir docs/SPEC-MVP.md §4).

Une ligne par événement : {seq, ts, type, payload, prev_hash, hash}.
`hash = sha256(canonical(record sans "hash"))`. Aucun float n'est admis, ni à l'écriture ni à la lecture.
Une ligne tronquée en fin de fichier est signalée (verify) ou refusée (append), jamais réparée en silence.
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

from arene.types import Bar, Fill, Intent, Quote, Side, Verdict

GENESIS_HASH = "0" * 64
_TAIL_CHUNK = 65536


class JournalError(Exception):
    """Erreur générique du journal."""


class FloatInPayloadError(JournalError, TypeError):
    """Un float a été trouvé dans un événement (interdit : entiers, chaînes, booléens, null, listes, objets)."""


class JournalCorruptError(JournalError):
    """Le fichier est corrompu (ligne tronquée, JSON invalide, hash cassé) : on refuse d'écrire dessus."""


# ---------------------------------------------------------------------------
# Forme canonique et hachage
# ---------------------------------------------------------------------------


def canonical(obj: Any) -> bytes:
    """Forme canonique UTF-8 d'un objet JSON (clés triées, sans espaces, non ASCII conservé)."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record_hash(record: dict[str, Any]) -> str:
    """Hash d'un enregistrement : sha256 de sa forme canonique sans le champ "hash"."""
    return sha256_hex(canonical({k: v for k, v in record.items() if k != "hash"}))


def find_float(obj: Any, path: str = "$") -> str | None:
    """Chemin du premier float trouvé dans `obj`, ou None."""
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
    """Lève FloatInPayloadError si `obj` contient un float."""
    where = find_float(obj)
    if where:
        raise FloatInPayloadError(f"float interdit dans le journal (en {where})")


# ---------------------------------------------------------------------------
# Sérialisation des contrats de types.py
# ---------------------------------------------------------------------------


def to_payload(obj: Any) -> Any:
    """Convertit récursivement dataclasses, enums et tuples en objets JSON simples (enums -> str)."""
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
    """Champs du payload connus de la dataclass (les champs ajoutés par un module sont ignorés)."""
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
# Vérification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifyError:
    code: str  # hash_mismatch, prev_hash_mismatch, seq_gap, float_present, truncated_tail, bad_json, ...
    line: int  # numéro de ligne (à partir de 1)
    seq: int | None  # seq lu dans la ligne, ou attendu quand la ligne est illisible
    message: str


@dataclass(frozen=True)
class VerifyReport:
    ok: bool
    n_records: int
    head_seq: int | None
    head_hash: str  # tête de chaîne (GENESIS_HASH si journal vide)
    errors: tuple[VerifyError, ...] = ()

    def codes(self) -> list[str]:
        return [e.code for e in self.errors]


def _no_const(name: str) -> Any:
    raise ValueError(f"constante JSON interdite : {name}")


def _loads(raw: bytes) -> Any:
    # parse_float renvoie un float : find_float le détecte ensuite (1.0 et 1e3 sont aussi des floats).
    return json.loads(raw.decode("utf-8"), parse_constant=_no_const)


def verify(path: str | Path) -> VerifyReport:
    """Vérifie chaîne de hash, continuité des seq, absence de float et de ligne tronquée."""
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
        lines.pop()  # dernier élément vide après le "\n" final
    for i, raw in enumerate(lines, start=1):
        is_last = i == len(lines)
        if is_last and not ends_with_newline:
            errors.append(
                VerifyError("truncated_tail", i, expected_seq, "dernière ligne sans fin de ligne : écriture interrompue")
            )
            break
        if not raw.strip():
            errors.append(VerifyError("blank_line", i, expected_seq, "ligne vide"))
            continue
        try:
            rec = _loads(raw)
        except ValueError as exc:  # JSONDecodeError et UnicodeDecodeError en dérivent
            errors.append(VerifyError("bad_json", i, expected_seq, f"JSON illisible : {exc}"))
            continue
        need = {"seq", "ts", "type", "payload", "prev_hash", "hash"}
        if not isinstance(rec, dict) or not need <= rec.keys():
            errors.append(VerifyError("bad_record", i, expected_seq, "champs obligatoires manquants"))
            continue
        seq = rec["seq"]
        if isinstance(seq, bool) or not isinstance(seq, int):
            errors.append(VerifyError("bad_record", i, expected_seq, "seq n'est pas un entier"))
            continue
        if seq != expected_seq:
            errors.append(VerifyError("seq_gap", i, seq, f"seq attendu {expected_seq}, lu {seq}"))
        if rec["prev_hash"] != prev_hash:
            errors.append(VerifyError("prev_hash_mismatch", i, seq, "prev_hash ne correspond pas à la ligne précédente"))
        if rec["hash"] != record_hash(rec):
            errors.append(VerifyError("hash_mismatch", i, seq, "hash recalculé différent du hash stocké"))
        where = find_float(rec)
        if where:
            errors.append(VerifyError("float_present", i, seq, f"float présent en {where}"))
        prev_hash = rec["hash"] if isinstance(rec["hash"], str) else prev_hash
        expected_seq = seq + 1
        head_seq = seq
        n += 1
    return VerifyReport(not errors, n, head_seq, prev_hash, tuple(errors))


# ---------------------------------------------------------------------------
# Lecture de la dernière ligne
# ---------------------------------------------------------------------------


def _tail_record(path: Path) -> dict[str, Any] | None:
    """Dernier enregistrement du fichier (lecture depuis la fin). Lève JournalCorruptError si illisible."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    with open(path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        f.seek(size - 1)
        if f.read(1) != b"\n":
            raise JournalCorruptError(f"{path} : dernière ligne tronquée (pas de fin de ligne)")
        buf = b""
        pos = size - 1  # on exclut le "\n" final
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
        raise JournalCorruptError(f"{path} : dernière ligne illisible ou hash invalide")
    return rec


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------


class Journal:
    """Journal append-only. Plusieurs processus peuvent écrire (verrou flock exclusif sur `<path>.lock`)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    def append(self, type: str, payload: Any, ts: int) -> dict[str, Any]:
        """Ajoute un événement et renvoie l'enregistrement complet. `payload` : dict ou dataclasse de types.py."""
        if not isinstance(type, str) or not type:
            raise JournalError("type d'événement invalide")
        if isinstance(ts, float):
            raise FloatInPayloadError("ts doit être un entier (secondes UTC), pas un float")
        if isinstance(ts, bool) or not isinstance(ts, int):
            raise JournalError("ts doit être un entier (secondes UTC)")
        body = to_payload(payload)
        if not isinstance(body, dict):
            raise JournalError("le payload doit être un objet")
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
        """Itère sur les enregistrements. Ne vérifie pas les hash (voir verify).

        strict=True : une ligne tronquée en fin ou un JSON illisible lève JournalCorruptError.
        strict=False : une dernière ligne sans fin de ligne est ignorée (lecteur concurrent d'une écriture).
        """
        if not self.path.exists():
            return
        with open(self.path, "rb") as f:
            for lineno, raw in enumerate(f, start=1):
                if not raw.endswith(b"\n"):
                    if strict:
                        raise JournalCorruptError(f"{self.path} ligne {lineno} : tronquée")
                    return
                try:
                    yield _loads(raw)
                except ValueError as exc:
                    raise JournalCorruptError(f"{self.path} ligne {lineno} : JSON illisible ({exc})") from exc

    def events(self) -> list[dict[str, Any]]:
        return list(self.iter_events())

    def last(self) -> dict[str, Any] | None:
        """Dernier enregistrement, ou None si le journal est vide."""
        return _tail_record(self.path)

    def verify(self) -> VerifyReport:
        return verify(self.path)
