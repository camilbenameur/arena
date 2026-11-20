"""Public market data (Kraken, Binance) and local cache.

Text -> integer conversions always go through Decimal, never float.

Rounding (market DATA only, not portfolio amounts): a market value whose precision exceeds the
integer unit (rare) is rounded with ROUND_HALF_EVEN. Portfolio amounts (fees, costs, proceeds)
follow the adverse rounding rules of `arena.types` instead.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

import httpx

from arena.types import MICRO, QTY_SCALE

TIMEOUT_S = 10.0
MAX_ATTEMPTS = 3
MIN_INTERVAL_S = 1.0  # 1 request per second per host
BACKOFF_BASE_S = 1.0


class DataError(Exception):
    """Error while fetching or reading market data."""


class TransientDataError(DataError):
    """Error worth retrying (5xx, 429, network, transient Kraken error)."""


class RateLimitedError(TransientDataError):
    """HTTP 429: `retry_after` = seconds requested by the Retry-After header (None if absent or unreadable)."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def to_scaled(text: str | int, scale: int) -> int:
    """Convert a decimal text to the integer `value * scale` without float (ROUND_HALF_EVEN, market data)."""
    try:
        d = Decimal(str(text))
    except InvalidOperation as exc:
        raise DataError(f"unreadable number: {text!r}") from exc
    if not d.is_finite():
        raise DataError(f"non-finite number: {text!r}")
    return int((d * scale).to_integral_value(rounding=ROUND_HALF_EVEN))


def to_ueur(text: str | int) -> int:
    """Price text -> µEUR (or µUSDT). E.g. "56622.4" -> 56_622_400_000."""
    return to_scaled(text, MICRO)


def to_qty(text: str | int) -> int:
    """Quantity text -> 1e-8 units. E.g. "130.20355035" -> 13_020_355_035."""
    return to_scaled(text, QTY_SCALE)


def to_exact_scaled(text: str, scale: int) -> int:
    """Like `to_scaled` but refuses any value that is not an integer after scaling (pair parameters)."""
    d = Decimal(str(text)) * scale
    if d != d.to_integral_value():
        raise DataError(f"value not exactly representable: {text!r}")
    return int(d)


class RateLimitedHttp:
    """JSON GET client: 1 request/s per host, 3 attempts, exponential backoff, 10 s timeout.

    `client`, `sleep` and `clock` are injectable (tests: mocked httpx transport, no real waiting).
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
        """GET and decode JSON. `retry_if(payload)` may raise TransientDataError/DataError based on the content.

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
                    raise RateLimitedError(f"HTTP 429 from {host}", int(ra) if ra.strip().isdigit() else None)
                if resp.status_code >= 500:
                    raise TransientDataError(f"HTTP {resp.status_code} from {host}")
                if resp.status_code >= 400:
                    raise DataError(f"HTTP {resp.status_code} from {host}")
                payload = resp.json() if parse_float is None else json.loads(resp.text, parse_float=parse_float)
                if retry_if is not None:
                    retry_if(payload)
                return payload
            except TransientDataError as exc:
                last_exc = exc
            except httpx.TransportError as exc:  # timeout, connection, DNS...
                last_exc = TransientDataError(f"network: {exc!r}")
            except ValueError as exc:  # invalid JSON
                raise DataError(f"non-JSON response from {host}") from exc
        assert last_exc is not None
        raise last_exc
