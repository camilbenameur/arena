"""Heartbeat externe (Healthchecks.io ou équivalent) : URL dans `<secrets>/healthcheck_url`.

Succès : GET sur l'URL. Échec : GET sur l'URL + "/fail". URL absente : rien n'est envoyé, un message
d'information est journalisé une seule fois. Une erreur réseau ne fait jamais échouer le cycle.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from arene.ops import read_secret
from arene.ops.notify import Notifier

log = logging.getLogger("arene.heartbeat")


class Heartbeat:
    def __init__(self, secrets_dir: Path | str, notifier: Notifier) -> None:
        self.secrets_dir = Path(secrets_dir)
        self.notifier = notifier

    def ping(self, ok: bool, ts: int) -> bool:
        """True si le ping est parti et accepté ; False sinon (absent, refusé ou erreur réseau)."""
        url = read_secret(self.secrets_dir, "healthcheck_url")
        if url is None:
            self.notifier.alert_once(
                "info", "heartbeat_absent", "healthcheck_url absent : aucun heartbeat externe n'est envoyé", ts
            )
            return False
        target = url.rstrip("/") + ("" if ok else "/fail")
        try:
            return self.notifier.http.get(target, timeout=10.0).is_success
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("heartbeat : ping impossible (%s)", type(exc).__name__)
            return False
