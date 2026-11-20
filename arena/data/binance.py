"""Public Binance 1d klines, used only for the E0065 benchmark signal (never for an amount).

Prices in micro-USDT, quantities in 1e-8, via `Decimal` (ROUND_HALF_EVEN: market data).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from arena.data import DataError, RateLimitedHttp, to_qty, to_ueur

BASE_URL = "https://api.binance.com"
DAY_S = 86400


@dataclass(frozen=True)
class DayBar:
    """Closed Binance 1d bar. ts = open (UTC s); close in micro-USDT; volumes in 1e-8."""

    symbol: str  # e.g. "BTCUSDT"
    ts: int
    close: int
    volume: int
    taker_buy_base: int
    interval_s: int = DAY_S


class BinanceClient:
    def __init__(
        self,
        http: RateLimitedHttp | None = None,
        *,
        base_url: str = BASE_URL,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._http = http or RateLimitedHttp()
        self._base = base_url.rstrip("/")
        self._now = now

    def klines_1d(self, binance_symbol: str, since: int | None = None, limit: int = 1000) -> list[DayBar]:
        """Closed 1d bars (the current day's bar, close_time >= now, is excluded)."""
        params: dict[str, str | int] = {"symbol": binance_symbol, "interval": "1d", "limit": limit}
        if since is not None:
            params["startTime"] = since * 1000
        payload = self._http.get_json(f"{self._base}/api/v3/klines", params)
        if not isinstance(payload, list):
            raise DataError(f"Binance klines: unexpected response {str(payload)[:100]}")
        now_ms = int(self._now() * 1000)
        bars = [
            DayBar(
                symbol=binance_symbol,
                ts=int(r[0]) // 1000,
                close=to_ueur(r[4]),
                volume=to_qty(r[5]),
                taker_buy_base=to_qty(r[9]),
            )
            for r in payload
            if int(r[6]) < now_ms
        ]
        bars.sort(key=lambda b: b.ts)
        return bars
