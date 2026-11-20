"""Manifest of the research data: sha256 of every file under `root_path` (the manifest itself excluded)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from research.config import REPO
from research.data.lab import _file_sha

NAME = "MANIFEST.json"
VERSION = "research-data-v1"
CONTROL_UNIVERSE_PATH = REPO / "research" / "control_universe.json"


class ManifestError(Exception):
    """A file is missing, changed or unlisted: the data is not the data that was frozen."""


def _files(root_path: Path) -> list[Path]:
    return sorted(p for p in root_path.rglob("*")
                  if p.is_file() and p.name != NAME and not p.name.endswith(".part"))


def build_manifest(root_path: Path | str, control_universe: Path | str | None = CONTROL_UNIVERSE_PATH
                         ) -> dict:
    """Hash every file under `root_path`, write `root_path/MANIFEST.json` and return its content.

    If `control_universe` exists, its sha256 is recorded too (the frozen list is part of the data).
    """
    root_path = Path(root_path)
    files = {p.relative_to(root_path).as_posix(): {"sha256": _file_sha(p), "byte_count": p.stat().st_size}
                for p in _files(root_path)}
    doc = {"version": VERSION, "cutoff": "2026-07-01T00:00:00Z", "files": files}
    if control_universe is not None and Path(control_universe).is_file():
        doc["control_universe_sha256"] = _file_sha(Path(control_universe))
    tmp = root_path / (NAME + ".part")
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    tmp.replace(root_path / NAME)
    return doc


def read_manifest(root_path: Path | str) -> dict:
    p = Path(root_path) / NAME
    if not p.is_file():
        raise ManifestError(f"{p} missing: run build_data")
    return json.loads(p.read_text())


def verify_manifest(root_path: Path | str, control_universe: Path | str | None = CONTROL_UNIVERSE_PATH
                       ) -> dict:
    """Check file by file (presence, size, sha256, no extra file). Returns the manifest."""
    root_path = Path(root_path)
    doc = read_manifest(root_path)
    expected = doc["files"]
    present = {p.relative_to(root_path).as_posix(): p for p in _files(root_path)}
    missing = sorted(set(expected) - set(present))
    extra = sorted(set(present) - set(expected))
    if missing or extra:
        raise ManifestError(f"missing files {missing[:5]} ({len(missing)}), "
                             f"unlisted files {extra[:5]} ({len(extra)})")
    for name, e in expected.items():
        p = present[name]
        if p.stat().st_size != e["byte_count"] or _file_sha(p) != e["sha256"]:
            raise ManifestError(f"{name} : content differs from the manifest")
    if "control_universe_sha256" in doc:
        if control_universe is None or not Path(control_universe).is_file():
            raise ManifestError("control_universe.json missing although the manifest records it")
        if _file_sha(Path(control_universe)) != doc["control_universe_sha256"]:
            raise ManifestError("control_universe.json modified since the manifest was built")
    return doc


def sha256_manifest(root_path: Path | str) -> str:
    return hashlib.sha256((Path(root_path) / NAME).read_bytes()).hexdigest()
