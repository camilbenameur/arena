"""Arena benchmarks (docs/SPEC-MVP.md §10): basket, 60/40, adapted E0065, random trader.

Each benchmark exposes `decide(cycle_ts, state, marks, context) -> list[Intent]`. Intents are expressed
like the LLMs' ones: `size_bp` in basis points of equity for a buy, of the position for a sell.

`basket`, `6040` and `e0065` are REFERENCES: they do not go through riskd's size caps.
Their quantity is computed by `reference_qty` (rounded down, fees included, never negative cash).
`random_trader` goes through riskd exactly like an LLM (the cycle calls it).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from arena.config import E0065Params
from arena.data.binance import DayBar
from arena.deciders.llm import UNIVERSE, make_intent_id
from arena.ledger import equity_ueur
from arena.sim.fills import market_fill
from arena.types import (
    QTY_SCALE,
    Bar,
    Instrument,
    Intent,
    PortfolioState,
    Quote,
    Side,
    notional_ueur,
)

BP = 10_000
DAY_S = 86_400


@dataclass(frozen=True)
class BenchmarkContext:
    """What the cycle provides to the benchmarks in addition to the state and marks.

    cycle_index   : cycle number since the start of the arena (0 = first).
    prev_cycle_ts : ts of the previous cycle (None on the very first).
    interval_s    : duration of a cycle (4 h).
    symbols       : universe, in canonical order.
    bars_4h       : closed 4 h bars per symbol (informational; no benchmark needs them to decide).
    day_bars      : Binance 1-day candles per CANONICAL symbol ("BTC/EUR"), for E0065. Only bars
                    closed at `cycle_ts` are read, whatever the list contains (leak guard).
    e0065         : parameters L, k, H.
    day0_ts       : first common day (00:00 UTC), used to number E0065's days. To be frozen once
                    and for all by the caller; if None, computed as the latest of the first available
                    days (fragile if the cache is truncated at the top).
    price_path    : price path number of the random trader (0 = the live path).
    min_trade_ueur: below this notional, a reference adjustment is ignored (dust).
    """

    cycle_index: int = 0
    prev_cycle_ts: int | None = None
    interval_s: int = 14_400
    symbols: tuple[str, ...] = UNIVERSE
    bars_4h: Mapping[str, Sequence[Bar]] = field(default_factory=dict)
    day_bars: Mapping[str, Sequence[DayBar]] = field(default_factory=dict)
    e0065: E0065Params = field(default_factory=lambda: E0065Params(L=20, k=3, H=10))
    day0_ts: int | None = None
    price_path: int = 0
    min_trade_ueur: int = 5_000_000


def never_traded(state: PortfolioState) -> bool:
    """True while the portfolio has no position and has paid no fees (no buy has happened yet)."""
    return not state.positions and state.fees_paid_ueur == 0


def make_intent(
    portfolio: str,
    cycle: int,
    index: int,
    symbol: str,
    side: Side,
    size_bp: int,
    *,
    stop_bp: int | None = None,
    horizon_h: int | None = None,
    expected_move_bp: int | None = None,
    confidence_pct: int | None = None,
) -> Intent:
    """Intent with an `intent_id` built like the LLMs' ones (`make_intent_id`)."""
    content = {
        "symbol": symbol,
        "side": side.value,
        "size_bp": size_bp,
        "stop_bp": stop_bp,
        "horizon_h": horizon_h,
        "expected_move_bp": expected_move_bp,
        "confidence_pct": confidence_pct,
    }
    return Intent(
        intent_id=make_intent_id(portfolio, cycle, index, content),
        portfolio=portfolio,
        cycle=cycle,
        symbol=symbol,
        side=side,
        size_bp=size_bp,
        stop_bp=stop_bp,
        horizon_h=horizon_h,
        expected_move_bp=expected_move_bp,
        confidence_pct=confidence_pct,
    )


def rebalance_intents(
    portfolio: str,
    cycle_ts: int,
    state: PortfolioState,
    marks: Mapping[str, int],
    targets_bp: Mapping[str, int],
    symbols: Sequence[str],
    min_trade_ueur: int,
) -> list[Intent]:
    """Intents that bring each symbol of `symbols` back to its target weight (bp of equity).

    Sells come first (they free the cash for the buys). A held symbol with no target is sold in full.
    A value gap below `min_trade_ueur` is ignored. A buy is expressed in bp of equity, a sell in bp of
    the position (rounded down, so never too large).
    """
    equity = equity_ueur(state, marks)
    if equity <= 0:
        return []
    sells: list[tuple[str, int]] = []
    buys: list[tuple[str, int]] = []
    for sym in symbols:
        pos = state.positions.get(sym)
        held = notional_ueur(pos.qty, marks[sym], round_up=False) if pos and pos.qty > 0 else 0
        target = equity * targets_bp.get(sym, 0) // BP
        gap = target - held
        if abs(gap) < min_trade_ueur and not (target == 0 and held > 0):
            continue
        if gap < 0:
            frac = BP if target == 0 else (-gap) * BP // held
            if frac > 0:
                sells.append((sym, min(frac, BP)))
        elif gap > 0:
            size = gap * BP // equity
            if size > 0:
                buys.append((sym, size))
    out: list[Intent] = []
    for sym, size in sells:
        out.append(make_intent(portfolio, cycle_ts, len(out), sym, Side.SELL, size))
    for sym, size in buys:
        out.append(make_intent(portfolio, cycle_ts, len(out), sym, Side.BUY, size))
    return out


def reference_qty(
    intent: Intent,
    state: PortfolioState,
    marks: Mapping[str, int],
    quote: Quote,
    instrument: Instrument,
    fee_bp: int,
    slippage_bp: int,
) -> int:
    """Quantity (1e-8) to execute for a reference intent; 0 = execute nothing.

    Buy: budget = equity × size_bp / 10 000, capped at cash; largest quantity whose cost
    (rounded up) + fees fits in the budget (rounded down, never negative cash).
    Sell: position × size_bp / 10 000 rounded down (the whole position if size_bp >= 10 000).
    Below the instrument's minimum lot or minimum cost: 0.
    """
    if intent.size_bp <= 0:
        return 0
    if intent.side == Side.SELL:
        pos = state.positions.get(intent.symbol)
        if pos is None or pos.qty <= 0:
            return 0
        if intent.size_bp >= BP:
            return pos.qty  # going flat: always allowed
        qty = pos.qty * intent.size_bp // BP
        if qty <= 0:
            return 0
        price, _ = market_fill(Side.SELL, qty, quote, instrument, fee_bp, slippage_bp)
        if qty < instrument.lot_min_qty or notional_ueur(qty, price, round_up=False) < instrument.cost_min_ueur:
            return 0
        return qty

    equity = equity_ueur(state, marks)
    budget = min(equity * intent.size_bp // BP, state.cash_ueur)
    if budget <= 0:
        return 0
    price, _ = market_fill(Side.BUY, QTY_SCALE, quote, instrument, fee_bp, slippage_bp)  # the price does not depend on qty
    if price <= 0:
        return 0
    qty = budget * BP * QTY_SCALE // (price * (BP + fee_bp))
    while qty > 0:
        _, fee = market_fill(Side.BUY, qty, quote, instrument, fee_bp, slippage_bp)
        total = notional_ueur(qty, price, round_up=True) + fee
        if total <= budget:
            break
        qty -= max(1, (total - budget) * QTY_SCALE // price)
    if qty <= 0 or qty < instrument.lot_min_qty:
        return 0
    if notional_ueur(qty, price, round_up=False) < instrument.cost_min_ueur:
        return 0
    return qty
