"""Market data types for the perpetual futures league. Integers only, no float.

Units:
- prices of USD-quoted contracts: micro-USD (µUSD, `MICRO` per USD), suffix `_uusd`;
- quantities, volumes and open interest: 1e-8 of the base asset (`QTY_SCALE`), suffix `_qty`;
- absolute funding: nano-USD per unit of base asset per hour (`NANO` per USD), suffix `_nusd`
  (µUSD is too coarse: XRP funding is a few µUSD per unit);
- relative funding: fraction per hour scaled by 1e12 (`E12`), suffix `_e12`;
- margin rates: parts per million of notional (`PPM`), suffix `_ppm`;
- EUR/USD quotes: µUSD per EUR, suffix `_uusd_per_eur`;
- timestamps: integer seconds UTC. A candle's `ts` is its start.

Market data is rounded half-to-even when the source has more precision than the unit; portfolio
amounts (later steps) use the unfavourable roundings of `arena.types`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

NANO = 1_000_000_000
E12 = 1_000_000_000_000
PPM = 1_000_000

CandleKind = Literal["mark", "trade", "spot"]
CANDLE_KINDS: tuple[str, ...] = ("mark", "trade", "spot")


@dataclass(frozen=True)
class PerpInstrument:
    """An instrument of the league, as configured in config/perp.toml."""

    symbol: str  # league name, e.g. "BTC-PERP"
    kraken_symbol: str  # Kraken Futures symbol, e.g. "PF_XBTUSD"
    spot_symbol: str  # matching spot pair of the spot league, e.g. "BTC/EUR"


@dataclass(frozen=True)
class MarginLevel:
    """One margin tier: applies from `threshold_uusd` of position notional upwards."""

    threshold_uusd: int
    initial_ppm: int
    maintenance_ppm: int


@dataclass(frozen=True)
class InstrumentSpec:
    """Contract parameters from /derivatives/api/v3/instruments (GLOBAL catalogue, not the EEA one)."""

    kraken_symbol: str
    tradeable: bool
    tick_uusd: int
    contract_size_qty: int
    max_position_qty: int | None
    margin_levels: tuple[MarginLevel, ...]
    max_relative_funding_e12: int | None
    lot_step_qty: int | None = None  # smallest tradeable quantity step (contractValueTradePrecision)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> InstrumentSpec:
        levels = tuple(MarginLevel(**lv) for lv in d["margin_levels"])
        return cls(**{**d, "margin_levels": levels})


@dataclass(frozen=True)
class Candle:
    """A CLOSED candle. `kind`: "mark" (mark price), "trade" (traded price), "spot" (index)."""

    kraken_symbol: str
    kind: str
    interval_s: int
    ts: int
    open: int
    high: int
    low: int
    close: int
    volume_qty: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Candle:
        return cls(**d)


@dataclass(frozen=True)
class PerpTicker:
    """Ticker of a perpetual at request time `ts` (local clock)."""

    kraken_symbol: str
    ts: int
    bid_uusd: int
    ask_uusd: int
    mark_uusd: int
    index_uusd: int | None
    last_uusd: int | None
    funding_nusd: int | None
    funding_prediction_nusd: int | None
    relative_funding_e12: int | None
    relative_funding_prediction_e12: int | None
    open_interest_qty: int | None
    suspended: bool
    post_only: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PerpTicker:
        return cls(**d)


@dataclass(frozen=True)
class FundingRate:
    """Hourly funding published by Kraken.

    `ts` is Kraken's stamp, which is the END of the hour paid for: the rate stamped H is computed over
    [H - 1 h, H) and published at H. `funding_nusd` is paid by longs to shorts (received if negative) per
    unit of base asset for that hour; `relative_funding_e12` is the same as a fraction of the mark price.
    """

    kraken_symbol: str
    ts: int
    funding_nusd: int
    relative_funding_e12: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FundingRate:
        return cls(**d)


@dataclass(frozen=True)
class OpenInterest:
    """Open interest candle (in units of base asset), CLOSED."""

    kraken_symbol: str
    interval_s: int
    ts: int
    open_qty: int
    high_qty: int
    low_qty: int
    close_qty: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OpenInterest:
        return cls(**d)


@dataclass(frozen=True)
class BookSnapshot:
    """Top of the L2 order book at request time `ts`. Levels are (price_uusd, qty), best first."""

    kraken_symbol: str
    ts: int
    bids: tuple[tuple[int, int], ...]
    asks: tuple[tuple[int, int], ...]
    crossed: bool  # best bid >= best ask (transient on the venue, or bad data): recorded, not hidden

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "bids": [list(x) for x in self.bids], "asks": [list(x) for x in self.asks]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BookSnapshot:
        return cls(
            kraken_symbol=d["kraken_symbol"],
            ts=d["ts"],
            bids=tuple((int(p), int(q)) for p, q in d["bids"]),
            asks=tuple((int(p), int(q)) for p, q in d["asks"]),
            crossed=d["crossed"],
        )


@dataclass(frozen=True)
class FxQuote:
    """EUR/USD quote from Kraken spot at request time `ts`: µUSD per EUR."""

    ts: int
    bid_uusd_per_eur: int
    ask_uusd_per_eur: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FxQuote:
        return cls(**d)
