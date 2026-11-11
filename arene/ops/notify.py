"""Alertes : écrites dans le journal (toujours) et envoyées à ntfy si l'URL est configurée.

Secrets lus à l'usage dans le dossier de secrets : `ntfy_url` (obligatoire pour envoyer), `ntfy_token`
(facultatif, jeton Bearer). Niveaux : info -> priorité 2, action -> 3, panique -> 5 (seul niveau prioritaire).
Une erreur d'envoi ne fait jamais échouer l'appelant : l'alerte reste dans le journal.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from arene.journal import Journal
from arene.ops import read_secret

log = logging.getLogger("arene.notify")

PRIORITY = {"info": 2, "action": 3, "panique": 5}
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
        self.journal_enabled = journal is not None  # False si le journal est cassé : on n'y écrit plus

    @property
    def http(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=TIMEOUT_S)
        return self._http

    def send(self, level: str, code: str, message: str) -> bool:
        """Envoie à ntfy. False si non configuré ou en échec (jamais d'exception)."""
        url = read_secret(self.secrets_dir, "ntfy_url")
        if url is None:
            return False
        headers = {"Title": f"arene {code}", "Priority": str(PRIORITY[level]), "Tags": level}
        token = read_secret(self.secrets_dir, "ntfy_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            resp = self.http.post(url, content=message[:MAX_MESSAGE].encode("utf-8"), headers=headers)
            return resp.is_success
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("ntfy : envoi impossible (%s)", type(exc).__name__)
            return False

    def alert(self, level: str, code: str, message: str, ts: int) -> dict | None:
        """Journalise l'alerte (si le journal est utilisable) puis tente l'envoi. Renvoie l'enregistrement."""
        if level not in PRIORITY:
            raise ValueError(f"niveau d'alerte inconnu : {level!r}")
        rec = None
        if self.journal is not None and self.journal_enabled:
            try:
                rec = self.journal.append(
                    "alert", {"level": level, "code": code, "message": message[:MAX_MESSAGE]}, ts
                )
            except Exception as exc:  # noqa: BLE001 - on ne perd jamais l'envoi externe pour une panne de disque
                log.error("alerte non journalisée (%s)", type(exc).__name__)
        self.send(level, code, message)
        return rec

    def alert_once(self, level: str, code: str, message: str, ts: int) -> bool:
        """Comme `alert`, mais seulement si aucune alerte de ce code n'est déjà dans le journal."""
        if self.journal is not None and self.journal_enabled:
            try:
                if any(e["type"] == "alert" and e["payload"].get("code") == code for e in self.journal.iter_events()):
                    return False
            except Exception:  # noqa: BLE001
                return False
        self.alert(level, code, message, ts)
        return True
