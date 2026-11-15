"""Public Kraken Futures API (no account, no key) and the EUR/USD quote from Kraken spot.

Every JSON number is decoded as `Decimal` (never float), then converted to integers (see
`arene.perp.types`). Endpoints, all checked live on 12/11/2026:

- GET /derivatives/api/v3/tickers
- GET /derivatives/api/v3/instruments
- GET /derivatives/api/v3/historical-funding-rates?symbol=...   (whole hourly history, about one year)
- GET /derivatives/api/v3/orderbook?symbol=...
- GET /api/charts/v1/{mark|trade|spot}/{symbol}/{resolution}?from=&to=   (pages of 2000 candles)
- GET /api/charts/v1/analytics/{symbol}/open-interest?interval=&since=

The catalogue is Kraken's GLOBAL one. Whether EEA clients trade the same contracts (same mark, same
funding, same margins) is not established: the EEA margin schedule (10 % / 5 %) differs from the global
one returned here.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from arene.data import DataError, RateLimitedHttp, to_scaled
from arene.data.kraken import KrakenClient
from arene.perp.types import (
    E12,
    NANO,
    PPM,
    BookSnapshot,
    Candle,
    FundingRate,
    FxQuote,
    InstrumentSpec,
    MarginLevel,
    OpenInterest,
    PerpTicker,
)
from arene.types import MICRO, QTY_SCALE

BASE_URL = "https://futures.kraken.com"
RESOLUTIONS: dict[int, str] = {
    60: "1m",
    300: "5m",
    900: "15m",
    1800: "30m",
    3600: "1h",
    14400: "4h",
    43200: "12h",
    86400: "1d",
    604800: "1w",
}
MAX_PAGES = 400  # guard against a pagination loop: 400 pages of 2000 one-minute candles = 555 days
# A candle is accepted as closed only `CLOSE_GRACE_S` after its end by the local clock: the charts API
# also returns the candle being formed, and a stored candle is never corrected.
CLOSE_GRACE_S = 15


def _uusd(x: Any) -> int:
    return to_scaled(str(x), MICRO)


def _qty(x: Any) -> int:
    return to_scaled(str(x), QTY_SCALE)


def _opt(conv: Callable[[Any], int], x: Any) -> int | None:
    return None if x is None else conv(x)


def _iso_ts(text: str) -> int:
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DataError(f"unreadable timestamp: {text!r}") from exc
    if dt.tzinfo is None:
        raise DataError(f"timestamp without time zone: {text!r}")
    return int(dt.timestamp())


@contextmanager
def _parsing(what: str) -> Iterator[None]:
    """Turns any malformed-payload error into DataError, so a bad row never aborts a whole run."""
    try:
        yield
    except DataError:
        raise
    except (KeyError, IndexError, ValueError, TypeError, ArithmeticError, InvalidOperation) as exc:
        raise DataError(f"{what}: malformed payload ({type(exc).__name__}: {exc})") from exc


def _strict_bool(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    if x is None:
        return False
    raise DataError(f"expected a JSON boolean, got {x!r}")


def _check_success(payload: Any) -> None:
    if not isinstance(payload, dict) or payload.get("result") != "success":
        err = payload.get("error") if isinstance(payload, dict) else None
        raise DataError(f"Kraken Futures: unsuccessful response ({err!r})")


class KrakenFuturesClient:
    def __init__(
        self,
        http: RateLimitedHttp | None = None,
        *,
        base_url: str = BASE_URL,
        now: Callable[[], float] = time.time,
        spot: KrakenClient | None = None,
    ) -> None:
        self._http = http or RateLimitedHttp()
        self._base = base_url.rstrip("/")
        self._now = now
        self._spot = spot or KrakenClient(self._http, now=now)
        self.misaligned_rows = 0  # candles / open-interest rows off the interval grid, dropped (counted)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._http.get_json(f"{self._base}{path}", params, parse_float=Decimal)

    def get_url_json(self, url: str) -> Any:
        """A public JSON page outside the market data (Kraken's announcements, `arene.perp.news`), through the
        same rate-limited client; numbers stay floats (only booleans, integers and texts are kept)."""
        return self._http.get_json(url)

    # ------------------------------------------------------------------ snapshots

    def tickers(self, kraken_symbols: Iterable[str]) -> tuple[dict[str, PerpTicker], dict[str, str]]:
        """(tickers that could be read, {symbol: problem} for the others). One bad contract never hides
        the healthy ones."""
        wanted = set(kraken_symbols)
        payload = self._get("/derivatives/api/v3/tickers")
        _check_success(payload)
        ts = int(self._now())
        out: dict[str, PerpTicker] = {}
        problems: dict[str, str] = {}
        rows = payload.get("tickers")
        if not isinstance(rows, list):
            raise DataError("Kraken Futures tickers: no tickers list")
        for t in rows:
            sym = t.get("symbol") if isinstance(t, dict) else None
            if sym not in wanted:
                continue
            try:
                with _parsing(f"ticker {sym}"):
                    out[sym] = PerpTicker(
                        kraken_symbol=sym,
                        ts=ts,
                        bid_uusd=_uusd(t["bid"]),
                        ask_uusd=_uusd(t["ask"]),
                        mark_uusd=_uusd(t["markPrice"]),
                        index_uusd=_opt(_uusd, t.get("indexPrice")),
                        last_uusd=_opt(_uusd, t.get("last")),
                        funding_nusd=_opt(lambda x: to_scaled(str(x), NANO), t.get("fundingRate")),
                        funding_prediction_nusd=_opt(
                            lambda x: to_scaled(str(x), NANO), t.get("fundingRatePrediction")
                        ),
                        relative_funding_e12=_opt(
                            lambda x: to_scaled(str(x), E12), t.get("relativeFundingRate")
                        ),
                        relative_funding_prediction_e12=_opt(
                            lambda x: to_scaled(str(x), E12), t.get("relativeFundingRatePrediction")
                        ),
                        open_interest_qty=_opt(_qty, t.get("openInterest")),
                        suspended=_strict_bool(t.get("suspended")),
                        post_only=_strict_bool(t.get("postOnly")),
                    )
            except DataError as exc:
                problems[sym] = str(exc)
        for sym in sorted(wanted - set(out) - set(problems)):
            problems[sym] = "absent from the tickers response"
        return out, problems

    def instruments(self, kraken_symbols: Iterable[str]) -> dict[str, InstrumentSpec]:
        wanted = set(kraken_symbols)
        payload = self._get("/derivatives/api/v3/instruments")
        _check_success(payload)
        out: dict[str, InstrumentSpec] = {}
        for i in payload.get("instruments", []):
            sym = i.get("symbol")
            if sym not in wanted:
                continue
            with _parsing(f"instrument {sym}"):
                out[sym] = self._instrument(sym, i)
        missing = wanted - set(out)
        if missing:
            raise DataError(f"Kraken Futures instruments: missing {sorted(missing)}")
        return out

    @staticmethod
    def _instrument(sym: str, i: dict[str, Any]) -> InstrumentSpec:
        levels = tuple(
            MarginLevel(
                threshold_uusd=_uusd(lv.get("numNonContractUnits", 0)),
                initial_ppm=to_scaled(str(lv["initialMargin"]), PPM),
                maintenance_ppm=to_scaled(str(lv["maintenanceMargin"]), PPM),
            )
            for lv in i.get("marginLevels", [])
        )
        max_rel = i.get("maxRelativeFundingRate")
        max_pos = i.get("maxPositionSize")
        prec = i.get("contractValueTradePrecision")
        lot = None
        if prec is not None:
            if type(prec) is not int or not -8 <= prec <= 8:
                raise DataError(f"instrument {sym}: bad contractValueTradePrecision {prec!r}")
            lot = 10 ** (8 - prec)
        return InstrumentSpec(
            kraken_symbol=sym,
            tradeable=_strict_bool(i.get("tradeable")),
            tick_uusd=_uusd(i["tickSize"]),
            contract_size_qty=_qty(i.get("contractSize", 1)),
            max_position_qty=_opt(_qty, max_pos),
            margin_levels=tuple(sorted(levels, key=lambda lv: lv.threshold_uusd)),
            max_relative_funding_e12=_opt(lambda x: to_scaled(str(x), E12), max_rel),
            lot_step_qty=lot,
        )

    def order_book(self, kraken_symbol: str, depth: int) -> BookSnapshot:
        if depth <= 0:
            raise ValueError("depth must be > 0")
        payload = self._get("/derivatives/api/v3/orderbook", {"symbol": kraken_symbol})
        _check_success(payload)
        ts = int(self._now())
        book = payload.get("orderBook") or {}

        def levels(rows: Any, best_first_desc: bool) -> tuple[tuple[int, int], ...]:
            parsed = [(_uusd(p), _qty(q)) for p, q in rows or []]
            parsed = [(p, q) for p, q in parsed if p > 0 and q > 0]
            parsed.sort(key=lambda r: -r[0] if best_first_desc else r[0])
            return tuple(parsed[:depth])

        with _parsing(f"order book {kraken_symbol}"):
            bids = levels(book.get("bids"), True)
            asks = levels(book.get("asks"), False)
        if not bids or not asks:
            raise DataError(f"Kraken Futures order book {kraken_symbol}: empty side")
        return BookSnapshot(kraken_symbol, ts, bids, asks, crossed=bids[0][0] >= asks[0][0])

    def eurusd(self, pair: str = "EURUSD") -> FxQuote:
        """EUR/USD from Kraken spot (USD per EUR): µUSD per EUR."""
        q = self._spot.ticker("EUR/USD", pair)
        if q.bid <= 0 or q.ask < q.bid:
            raise DataError(f"EUR/USD quote is incoherent (bid={q.bid}, ask={q.ask})")
        return FxQuote(ts=q.ts, bid_uusd_per_eur=q.bid, ask_uusd_per_eur=q.ask)

    # ------------------------------------------------------------------ histories

    def funding_history(self, kraken_symbol: str) -> list[FundingRate]:
        """The whole hourly funding history Kraken returns (about one year), sorted by ts.

        Kraken stamps each rate with the END of the hour it pays for: the entry stamped H is computed over
        [H - 1 h, H) and published at H (checked live on 12/11/2026). The history itself has holes.
        """
        payload = self._get("/derivatives/api/v3/historical-funding-rates", {"symbol": kraken_symbol})
        _check_success(payload)
        with _parsing(f"funding {kraken_symbol}"):
            out = [
                FundingRate(
                    kraken_symbol=kraken_symbol,
                    ts=_iso_ts(r["timestamp"]),
                    funding_nusd=to_scaled(str(r["fundingRate"]), NANO),
                    relative_funding_e12=to_scaled(str(r["relativeFundingRate"]), E12),
                )
                for r in payload.get("rates", [])
            ]
        out.sort(key=lambda r: r.ts)
        return out

    def candles(
        self, kind: str, kraken_symbol: str, interval_s: int, from_ts: int, to_ts: int
    ) -> list[Candle]:
        """CLOSED candles with from_ts <= ts and ts + interval_s <= min(to_ts, now - CLOSE_GRACE_S),
        sorted, paged. Kraken's `from` rounds up to the next candle and `to` is inclusive."""
        if kind not in ("mark", "trade", "spot"):
            raise ValueError(f"unknown candle kind: {kind!r}")
        res = RESOLUTIONS.get(interval_s)
        if res is None:
            raise ValueError(f"unsupported interval: {interval_s}")
        horizon = min(to_ts, int(self._now()) - CLOSE_GRACE_S)
        out: dict[int, Candle] = {}
        cursor = from_ts
        for _ in range(MAX_PAGES):
            if cursor + interval_s > horizon:
                break
            payload = self._get(
                f"/api/charts/v1/{kind}/{kraken_symbol}/{res}", {"from": cursor, "to": horizon}
            )
            rows = payload.get("candles") if isinstance(payload, dict) else None
            if rows is None:
                raise DataError(f"Kraken Futures charts {kind} {kraken_symbol}: no candles field")
            last = None
            with _parsing(f"charts {kind} {kraken_symbol}"):
                for c in rows:
                    last = self._candle_row(c, kind, kraken_symbol, interval_s, from_ts, horizon, out, last)
            if not payload.get("more_candles") or last is None:
                break
            if last + interval_s <= cursor:
                raise DataError(f"Kraken Futures charts {kind} {kraken_symbol}: pagination does not advance")
            cursor = last + interval_s
        else:
            raise DataError(f"Kraken Futures charts {kind} {kraken_symbol}: more than {MAX_PAGES} pages")
        return [out[ts] for ts in sorted(out)]

    def _candle_row(
        self,
        c: Any,
        kind: str,
        kraken_symbol: str,
        interval_s: int,
        from_ts: int,
        horizon: int,
        out: dict[int, Candle],
        last: int | None,
    ) -> int:
        ms = int(c["time"])
        if ms % 1000:
            raise DataError(f"candle time not on a second: {ms}")
        ts = ms // 1000
        last = ts if last is None else max(last, ts)
        if ts % interval_s:
            self.misaligned_rows += 1
            return last
        if ts < from_ts or ts + interval_s > horizon:
            return last  # outside the window, or not closed yet
        out.setdefault(
            ts,
            Candle(
                kraken_symbol=kraken_symbol,
                kind=kind,
                interval_s=interval_s,
                ts=ts,
                open=_uusd(c["open"]),
                high=_uusd(c["high"]),
                low=_uusd(c["low"]),
                close=_uusd(c["close"]),
                volume_qty=_qty(c.get("volume", "0")),
            ),
        )
        return last

    def open_interest(self, kraken_symbol: str, interval_s: int, since_ts: int) -> list[OpenInterest]:
        """CLOSED open-interest candles with ts >= since_ts, sorted, paged."""
        horizon = int(self._now()) - CLOSE_GRACE_S
        out: dict[int, OpenInterest] = {}
        cursor = since_ts
        for _ in range(MAX_PAGES):
            payload = self._get(
                f"/api/charts/v1/analytics/{kraken_symbol}/open-interest",
                {"interval": interval_s, "since": cursor},
            )
            if not isinstance(payload, dict) or payload.get("errors"):
                raise DataError(f"Kraken Futures open interest {kraken_symbol}: {payload!r:.200}")
            result = payload.get("result") or {}
            stamps, data = result.get("timestamp") or [], result.get("data") or []
            if len(stamps) != len(data):
                raise DataError(f"Kraken Futures open interest {kraken_symbol}: misaligned arrays")
            with _parsing(f"open interest {kraken_symbol}"):
                for ts, row in zip(stamps, data, strict=True):
                    ts = int(ts)
                    if ts % interval_s:
                        self.misaligned_rows += 1
                        continue
                    if ts < since_ts or ts + interval_s > horizon:
                        continue
                    o, h, lo, c = (_qty(x) for x in row)
                    out.setdefault(ts, OpenInterest(kraken_symbol, interval_s, ts, o, h, lo, c))
            if not result.get("more") or not stamps:
                break
            nxt = int(max(stamps)) + interval_s
            if nxt <= cursor:
                raise DataError(f"Kraken Futures open interest {kraken_symbol}: pagination does not advance")
            cursor = nxt
        else:
            raise DataError(f"Kraken Futures open interest {kraken_symbol}: more than {MAX_PAGES} pages")
        return [out[ts] for ts in sorted(out)]
