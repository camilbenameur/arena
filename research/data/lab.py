"""Copy of the lab in-sample candles (read-only on the lab side), verified against its MANIFEST.json."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

LAB_IN_SAMPLE = Path("var") / "lab" / "data" / "in-sample"


class LabError(Exception):
    pass


def _file_sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def copy_in_sample(src: Path | str = LAB_IN_SAMPLE, dest: Path | str = Path("var/research/data/lab")
                     ) -> list[Path]:
    """Verify the sha256 of each `src` file listed in `MANIFEST.json`, then copy it to `dest`.

    Nothing is copied if any source file does not match. Resumable: a file already present in `dest`
    with the right sha256 is skipped. The lab `MANIFEST.json` is copied too. Returns the `dest` paths.
    """
    src, dest = Path(src), Path(dest)
    manifest_bytes = (src / "MANIFEST.json").read_bytes()
    entries = json.loads(manifest_bytes)["files"]
    if not entries:
        raise LabError("lab MANIFEST.json lists no file")
    for e in entries:
        f = src / e["file"]
        if not f.is_file():
            raise LabError(f"{e['file']} missing from {src}")
        if _file_sha(f) != e["sha256"]:
            raise LabError(f"{e['file']} : sha256 differs from the lab MANIFEST.json")
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for e in entries:
        target = dest / e["file"]
        if not (target.is_file() and _file_sha(target) == e["sha256"]):
            tmp = target.with_name(target.name + ".part")
            shutil.copyfile(src / e["file"], tmp)
            tmp.replace(target)
        out.append(target)
    (dest / "MANIFEST.json").write_bytes(manifest_bytes)
    return out
