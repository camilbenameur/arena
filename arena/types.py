"""Shared contracts of the arena. All modules rely on these types.

Unit rules (non-negotiable, see docs/SPEC-MVP.md §2):
- Cash and prices in EUR, stored as integer micro-euros (1 EUR = 1_000_000 µEUR).
- Base-asset quantities as integer minimal units: 1 unit = 10**-8 of the asset (QTY_SCALE).
- No float anywhere in the money path. Floats are used only for statistics and display.
- Rounding is always adverse to the portfolio: fees rounded up, sale proceeds rounded down,
  purchase cost rounded up.
- Timestamps: integers in Unix UTC seconds (ts); ISO 8601 strings are used for display only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

MICRO = 1_000_000  # µEUR per EUR
QTY_SCALE = 100_000_000  # minimal units per unit of the base asset

VenueMode = Literal["live", "paper", "backtest", "synthetic"]


def ceil_div(a: int, b: int) -> int:
    """Integer division rounded up (b > 0)."""
    return -((-a) // b)


def notional_ueur(qty: int, price_ueur: int, *, round_up: bool) -> int:
    """Value in µEUR of `qty` minimal units at price `price_ueur` (µEUR per whole unit of the asset)."""
    num = qty * price_ueur
    return ceil_div(num, QTY_SCALE) if round_up else num // QTY_SCALE


@dataclass(frozen=True)
class Instrument:
    symbol: str  # canonical form "BTC/EUR"
    kraken_pair: str  # e.g. "XBTEUR" (Kraken altname)
    binance_symbol: str  # e.g. "BTCUSDT", used only for the E0065 benchmark signal
    tick_ueur: int  # price step in µEUR
    lot_min_qty: int  # minimum order quantity (minimal units)
    cost_min_ueur: int  # minimum order notional (µEUR)


@dataclass(frozen=True)
class Bar:
    """Closed OHLCV bar. ts = bar start (UTC, seconds). Prices in µEUR, volume in minimal units."""

    symbol: str
    interval_s: int
    ts: int
    open: int
    high: int
    low: int
    close: int
    volume: int


@dataclass(frozen=True)
class Quote:
    """Best price at the time of the simulated execution."""

    symbol: str
    ts: int
    bid: int
    ask: int


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Intent:
    """Intent emitted by a decider (model or benchmark). Never an order: riskd validates it first.

    size_bp: size in basis points (1/10,000) of the portfolio equity for a buy,
             or of the held position for a sell (10_000 = sell everything).
    stop_bp: distance of the stop below the entry price, in basis points (buys only).
    """

    intent_id: str  # sha256 hex of the canonical form (portfolio, cycle, index, content)
    portfolio: str  # e.g. "llm:claude-sonnet-5-5", "benchmark:basket"
    cycle: int  # ts of the decision cycle
    symbol: str
    side: Side
    size_bp: int
    stop_bp: int | None = None
    horizon_h: int | None = None
    expected_move_bp: int | None = None
    confidence_pct: int | None = None


class OrderState(StrEnum):
    INTENT = "INTENT"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    SUBMITTING = "SUBMITTING"
    ACKED = "ACKED"
    UNKNOWN = "UNKNOWN"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELED = "CANCELED"


@dataclass(frozen=True)
class Verdict:
    intent_id: str
    approved: bool
    reasons: tuple[str, ...]  # stable rule codes, e.g. "MAX_ORDER_SIZE", "DAILY_TRADES"
    qty: int = 0  # approved quantity (minimal units), 0 if rejected
    reserved_ueur: int = 0  # reserved notional (buy) or expected notional (sell)
    policy_sha256: str = ""


@dataclass(frozen=True)
class Fill:
    order_id: str  # = intent_id for an entry; "stop:<intent_id>" or "exit:<...>" for an exit
    portfolio: str
    symbol: str
    side: Side
    qty: int
    price_ueur: int
    fee_ueur: int
    ts: int
    venue_mode: VenueMode
    fill_model_version: str
    reason: str = "intent"  # "intent" | "stop" | "max_holding" | "kill_switch"


@dataclass
class Position:
    symbol: str
    qty: int
    cost_ueur: int  # total acquisition cost including fees (weighted average cost)
    opened_ts: int
    stop_ueur: int | None = None


@dataclass
class PortfolioState:
    portfolio: str
    cash_ueur: int
    positions: dict[str, Position] = field(default_factory=dict)
    fees_paid_ueur: int = 0
    realized_pnl_ueur: int = 0
    frozen_until_ts: int = 0
    halted: bool = False  # halted (drawdown): human review required
