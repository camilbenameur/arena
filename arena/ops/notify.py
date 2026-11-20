"""Alerts: always written to the journal and sent to ntfy if the URL is configured.

Secrets are read at use time from the secrets directory: `ntfy_url` (required to send), `ntfy_token`
(optional, Bearer token). Levels: info -> priority 2, action -> 3, panic -> 5 (the only high-priority level).
A send error never makes the caller fail: the alert stays in the journal.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from arena.journal import Journal
from arena.ops import read_secret

log = logging.getLogger("arena.notify")

PRIORITY = {"info": 2, "action": 3, "panic": 5}
LEVELS = tuple(PRIORITY)
TIMEOUT_S = 10.0
MAX_MESSAGE = 1000


class Notifier:
    def __init__(
        self, journal: Journal | None, secrets_dir: Path | str, http: httpx.Client | None = None
    ) -> None:
        self.journal = journal
        self.secrets_dir = Path(secrets_dir)
        self._http = http
        self.journal_enabled = journal is not None  # False if the journal is broken: nothing is written to it any more

    @property
    def http(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=TIMEOUT_S)
        return self._http

    def send(self, level: str, code: str, message: str) -> bool:
        """Send to ntfy. False if not configured or failed (never raises)."""
        url = read_secret(self.secrets_dir, "ntfy_url")
        if url is None:
            return False
        headers = {"Title": f"arena {code}", "Priority": str(PRIORITY[level]), "Tags": level}
        token = read_secret(self.secrets_dir, "ntfy_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            resp = self.http.post(url, content=message[:MAX_MESSAGE].encode("utf-8"), headers=headers)
            return resp.is_success
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("ntfy: send failed (%s)", type(exc).__name__)
            return False

    def alert(self, level: str, code: str, message: str, ts: int) -> dict | None:
        """Journal the alert (if the journal is usable) then try to send it. Returns the record."""
        if level not in PRIORITY:
            raise ValueError(f"unknown alert level: {level!r}")
        rec = None
        if self.journal is not None and self.journal_enabled:
            try:
                rec = self.journal.append(
                    "alert", {"level": level, "code": code, "message": message[:MAX_MESSAGE]}, ts
                )
            except Exception as exc:  # noqa: BLE001 - the external send is never lost because of a disk failure
                log.error("alert not journaled (%s)", type(exc).__name__)
        self.send(level, code, message)
        return rec

    def alert_once(self, level: str, code: str, message: str, ts: int) -> bool:
        """Like `alert`, but only if no alert with this code is already in the journal."""
        if self.journal is not None and self.journal_enabled:
            try:
                if any(e["type"] == "alert" and e["payload"].get("code") == code for e in self.journal.iter_events()):
                    return False
            except Exception:  # noqa: BLE001
                return False
        self.alert(level, code, message, ts)
        return True
