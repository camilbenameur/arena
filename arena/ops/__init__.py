"""Operations: external heartbeat, ntfy notifications, kill switch, dormancy (docs/SPEC-MVP.md §12)."""

from __future__ import annotations

import os
from pathlib import Path

from arena.paths import Paths


def read_secret(secrets_dir: Path | str, name: str) -> str | None:
    """Read an optional secret at the time of use. None if absent or empty. Never journaled or displayed."""
    try:
        text = (Path(secrets_dir) / name).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def anthropic_key(paths: Paths) -> str | None:
    """API key: `$CREDENTIALS_DIRECTORY/anthropic_api_key`, otherwise `<secrets>/anthropic_api_key`."""
    cred = os.environ.get("CREDENTIALS_DIRECTORY")
    if cred:
        key = read_secret(cred, "anthropic_api_key")
        if key:
            return key
    return read_secret(paths.secrets, "anthropic_api_key")
