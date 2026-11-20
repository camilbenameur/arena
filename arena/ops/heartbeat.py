"""External heartbeat (Healthchecks.io or equivalent): URL in `<secrets>/healthcheck_url`.

Success: GET on the URL. Failure: GET on the URL + "/fail". URL missing: nothing is sent, one informational
message is journaled once. A network error never makes the cycle fail.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from arena.ops import read_secret
from arena.ops.notify import Notifier

log = logging.getLogger("arena.heartbeat")


class Heartbeat:
    def __init__(self, secrets_dir: Path | str, notifier: Notifier) -> None:
        self.secrets_dir = Path(secrets_dir)
        self.notifier = notifier

    def ping(self, ok: bool, ts: int) -> bool:
        """True if the ping was sent and accepted; False otherwise (missing, refused or network error)."""
        url = read_secret(self.secrets_dir, "healthcheck_url")
        if url is None:
            self.notifier.alert_once(
                "info", "heartbeat_absent", "healthcheck_url missing: no external heartbeat is sent", ts
            )
            return False
        target = url.rstrip("/") + ("" if ok else "/fail")
        try:
            return self.notifier.http.get(target, timeout=10.0).is_success
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("heartbeat: ping failed (%s)", type(exc).__name__)
            return False
