"""Données de marché publiques (Kraken, Binance) et cache local.

Conversions texte -> entiers : toujours via Decimal, jamais float.

Arrondi (DONNÉES de marché uniquement, pas des montants de portefeuille) : une valeur de marché
dont la précision dépasse l'unité entière (rare) est arrondie avec ROUND_HALF_EVEN. Les montants
de portefeuille (frais, coûts, produits) suivent, eux, les arrondis défavorables de `arene.types`.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

import httpx

from arene.types import MICRO, QTY_SCALE

TIMEOUT_S = 10.0
MAX_ATTEMPTS = 3
MIN_INTERVAL_S = 1.0  # 1 requête par seconde et par hôte
BACKOFF_BASE_S = 1.0


class DataError(Exception):
    """Erreur de récupération ou de lecture de données de marché."""


class TransientDataError(DataError):
    """Erreur qui justifie une nouvelle tentative (5xx, 429, réseau, erreur Kraken passagère)."""


class RateLimitedError(TransientDataError):
    """HTTP 429 : `retry_after` = secondes demandées par l'en-tête Retry-After (None s'il est absent ou illisible)."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def to_scaled(text: str | int, scale: int) -> int:
    """Convertit un décimal texte en entier `valeur * scale` sans float (ROUND_HALF_EVEN, données de marché)."""
    try:
        d = Decimal(str(text))
    except InvalidOperation as exc:
        raise DataError(f"nombre illisible: {text!r}") from exc
    if not d.is_finite():
        raise DataError(f"nombre non fini: {text!r}")
    return int((d * scale).to_integral_value(rounding=ROUND_HALF_EVEN))


def to_ueur(text: str | int) -> int:
    """Prix texte -> µEUR (ou µUSDT). Ex. "56622.4" -> 56_622_400_000."""
    return to_scaled(text, MICRO)


def to_qty(text: str | int) -> int:
    """Quantité texte -> unités 1e-8. Ex. "130.20355035" -> 13_020_355_035."""
    return to_scaled(text, QTY_SCALE)


def to_exact_scaled(text: str, scale: int) -> int:
    """Comme `to_scaled` mais refuse toute valeur non entière après mise à l'échelle (paramètres de paire)."""
    d = Decimal(str(text)) * scale
    if d != d.to_integral_value():
        raise DataError(f"valeur non représentable exactement: {text!r}")
    return int(d)


class RateLimitedHttp:
    """Client GET JSON : 1 requête/s par hôte, 3 tentatives, backoff exponentiel, timeout 10 s.

    `client`, `sleep` et `clock` sont injectables (tests : transport httpx mocké, pas d'attente réelle).
    """

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client or httpx.Client(timeout=TIMEOUT_S)
        self._sleep = sleep
        self._clock = clock
        self._last: dict[str, float] = {}

    def _throttle(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            wait = MIN_INTERVAL_S - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last[host] = self._clock()

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        retry_if: Callable[[Any], None] | None = None,
        parse_float: Callable[[str], Any] | None = None,
    ) -> Any:
        """GET et décodage JSON. `retry_if(payload)` peut lever TransientDataError/DataError sur le contenu.

        `parse_float` (e.g. `Decimal`) decodes JSON decimal numbers without going through float.
        """
        host = httpx.URL(url).host
        last_exc: DataError | None = None
        for attempt in range(MAX_ATTEMPTS):
            if attempt:
                self._sleep(BACKOFF_BASE_S * 2 ** (attempt - 1))
            self._throttle(host)
            try:
                resp = self._client.get(url, params=params, timeout=TIMEOUT_S)
                if resp.status_code == 429:
                    ra = resp.headers.get("Retry-After", "")
                    raise RateLimitedError(f"HTTP 429 sur {host}", int(ra) if ra.strip().isdigit() else None)
                if resp.status_code >= 500:
                    raise TransientDataError(f"HTTP {resp.status_code} sur {host}")
                if resp.status_code >= 400:
                    raise DataError(f"HTTP {resp.status_code} sur {host}")
                payload = resp.json() if parse_float is None else json.loads(resp.text, parse_float=parse_float)
                if retry_if is not None:
                    retry_if(payload)
                return payload
            except TransientDataError as exc:
                last_exc = exc
            except httpx.TransportError as exc:  # timeout, connexion, DNS...
                last_exc = TransientDataError(f"réseau: {exc!r}")
            except ValueError as exc:  # JSON invalide
                raise DataError(f"réponse non JSON de {host}") from exc
        assert last_exc is not None
        raise last_exc
