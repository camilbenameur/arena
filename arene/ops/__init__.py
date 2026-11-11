"""Exploitation : heartbeat externe, notifications ntfy, coupe-circuit, dormance (docs/SPEC-MVP.md §12)."""

from __future__ import annotations

import os
from pathlib import Path

from arene.paths import Paths


def read_secret(secrets_dir: Path | str, name: str) -> str | None:
    """Lit un secret facultatif au moment de l'usage. None si absent ou vide. Jamais journalisé ni affiché."""
    try:
        text = (Path(secrets_dir) / name).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def anthropic_key(paths: Paths) -> str | None:
    """Clé API : `$CREDENTIALS_DIRECTORY/anthropic_api_key`, sinon `<secrets>/anthropic_api_key`."""
    cred = os.environ.get("CREDENTIALS_DIRECTORY")
    if cred:
        key = read_secret(cred, "anthropic_api_key")
        if key:
            return key
    return read_secret(paths.secrets, "anthropic_api_key")
