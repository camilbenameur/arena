"""Offline random price paths (docs/SPEC-MVP.md §10): 1,000 replays of the random agent.

Each path replays `benchmark:random` on the SAME cycles and the SAME quotes as the arena, with
ITS OWN seeds (path number 1..n), goes through `riskd.evaluate` (counters recomputed in the
simulation, not read from the real journal) and through `market_fill`; stops (`stop_fill`), the maximum
holding time, the freeze and the halt (drawdown) are replayed as in the real cycle. Integers only.

Each cycle's market (MarketView: quotes, latest closes, median spreads, marks) is computed
ONCE and shared by all paths.
"""

from __future__ import annotations

import warnings
from bisect import bisect_right
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from arena.ledger import month_start_ts
from arena.risk.policy import Policy
from arena.risk.riskd import BP, Counters, MarketView, evaluate, freeze_or_halt
from arena.sim.fills import market_fill, stop_fill, stop_price
from arena.benchmarks import BenchmarkContext, random_trader
from arena.types import (
    Bar,
    Instrument,
    PortfolioState,
    Position,
    Quote,
    Side,
    ceil_div,
    notional_ueur,
)

DAY_S = 86_400
MINUTE_S = 60
SPREAD_WINDOW = 20


@dataclass(frozen=True)
class CycleData:
    """What the journal kept of a past cycle.

    ts          : ts of the decision cycle.
    quotes      : journaled quotes per symbol.
    marks       : valuation prices per symbol (in practice the quote's mid).
    last_closes : latest 4 h close per symbol (PRICE_SANITY); defaults to the quote's mid.
    bars        : 4 h bars closed since the previous cycle, per symbol (for the stops). If no cycle
                  provides any, the stops are not simulated (a warning is issued).
    """

    ts: int
    quotes: Mapping[str, Quote]
    marks: Mapping[str, int]
    last_closes: Mapping[str, int] = field(default_factory=dict)
    bars: Mapping[str, Sequence[Bar]] = field(default_factory=dict)


@dataclass(frozen=True)
class _Prepared:
    ts: int
    market: MarketView
    bars: Mapping[str, Sequence[Bar]]
    month_start: int


def _prepare(cycles: Sequence[CycleData]) -> list[_Prepared]:
    spreads: dict[str, deque[int]] = {}
    out = []
    for c in cycles:
        medians: dict[str, int] = {}
        closes: dict[str, int] = {}
        for sym, q in c.quotes.items():
            win = spreads.setdefault(sym, deque(maxlen=SPREAD_WINDOW))
            win.append(q.ask - q.bid)
            medians[sym] = sorted(win)[len(win) // 2]
            closes[sym] = c.last_closes.get(sym, (q.bid + q.ask) // 2)
        out.append(
            _Prepared(
                ts=c.ts,
                market=MarketView(c.quotes, closes, medians, c.marks),
                bars=c.bars,
                month_start=month_start_ts(c.ts),
            )
        )
    return out


def _fee(qty: int, price: int, fee_bp: int) -> int:
    return ceil_div(notional_ueur(qty, price, round_up=True) * fee_bp, BP)


def _apply(state: PortfolioState, sym: str, side: Side, qty: int, price: int, fee: int, ts: int) -> bool:
    """Apply a fill like `ledger.replay`. False (changing nothing) if cash or position is insufficient."""
    pos = state.positions.get(sym)
    if side == Side.BUY:
        total = notional_ueur(qty, price, round_up=True) + fee
        if qty <= 0 or total > state.cash_ueur:
            return False
        state.cash_ueur -= total
        if pos is None:
            state.positions[sym] = Position(sym, qty, total, ts)
        else:
            pos.qty += qty
            pos.cost_ueur += total
    else:
        if pos is None or qty <= 0 or qty > pos.qty:
            return False
        gross = notional_ueur(qty, price, round_up=False)
        removed = pos.cost_ueur if qty == pos.qty else ceil_div(pos.cost_ueur * qty, pos.qty)
        pos.qty -= qty
        pos.cost_ueur -= removed
        if pos.qty == 0:
            del state.positions[sym]
        state.cash_ueur += gross - fee
    state.fees_paid_ueur += fee
    return True


def _sell_all(
    state: PortfolioState, fees: list[tuple[int, int]], sym: str, price: int, fee: int, ts: int
) -> None:
    if _apply(state, sym, Side.SELL, state.positions[sym].qty, price, fee, ts):
        fees.append((ts, fee))


def _counters(base: tuple[int, int, int, int, int], orders: int, last: int | None, eq_now: int) -> Counters:
    trades, fees_month, eq_month, eq_24h, peak = base
    return Counters(
        trades_24h=trades,
        orders_last_minute=orders,
        last_symbol_intent_ts=last,
        fees_month_ueur=fees_month,
        equity_month_start_ueur=eq_month,
        equity_24h_ago_ueur=eq_24h,
        equity_peak_ueur=peak,
        equity_now_ueur=eq_now,
    )


def _equity(state: PortfolioState, marks: Mapping[str, int]) -> int:
    return state.cash_ueur + sum(
        notional_ueur(p.qty, marks[s], round_up=False) for s, p in state.positions.items()
    )


def _simulate(
    prepared: Sequence[_Prepared],
    price_path: int,
    policy: Policy,
    instruments: Mapping[str, Instrument],
    fee_bp: int,
    slippage_bp: int,
    capital_ueur: int,
) -> list[int]:
    """Equity after each cycle for price path `price_path`."""
    state = PortfolioState(random_trader.PORTFOLIO, capital_ueur)
    context = BenchmarkContext(symbols=tuple(instruments), price_path=price_path)
    eq_ts: list[int] = []
    eq_val: list[int] = []
    peak = capital_ueur
    intent_fills: deque[int] = deque()  # ts of the fills coming from an intent (24 h window)
    fees: list[tuple[int, int]] = []  # (ts, fees) of the current month
    last_buy_intent: dict[str, int] = {}

    for cyc in prepared:
        ts, market = cyc.ts, cyc.market
        marks = market.marks
        quotes = market.quotes

        # 4. Stops (bars closed since the last cycle), then maximum holding time.
        for sym in list(state.positions):
            pos = state.positions[sym]
            inst = instruments[sym]
            if pos.stop_ueur is not None:
                for bar in cyc.bars.get(sym, ()):
                    px = stop_fill(pos.stop_ueur, bar, inst, slippage_bp)
                    if px is not None:
                        _sell_all(state, fees, sym, px, _fee(pos.qty, px, fee_bp), ts)
                        break
            if sym in state.positions and ts - pos.opened_ts >= policy.max_holding_s and sym in quotes:
                px, fee = market_fill(Side.SELL, pos.qty, quotes[sym], inst, fee_bp, slippage_bp)
                _sell_all(state, fees, sym, px, fee, ts)

        # Rolling windows, reference equity.
        while intent_fills and intent_fills[0] <= ts - DAY_S:
            intent_fills.popleft()
        fees[:] = [(t, f) for t, f in fees if t >= cyc.month_start]
        i24 = bisect_right(eq_ts, ts - DAY_S)
        eq_24h = eq_val[i24 - 1] if i24 else capital_ueur
        im = bisect_right(eq_ts, cyc.month_start - 1)
        eq_month = eq_val[im - 1] if im else capital_ueur
        eq_now = _equity(state, marks)
        fees_month = sum(f for _, f in fees)

        base = (len(intent_fills), fees_month, eq_month, eq_24h, peak)

        # 5. Freeze / halt.
        code, until = freeze_or_halt(state, _counters(base, 0, None, eq_now), policy, ts)
        if code == "HALTED" and not state.halted:
            state.halted = True
            for sym in list(state.positions):
                if sym in quotes:
                    pos = state.positions[sym]
                    px, fee = market_fill(Side.SELL, pos.qty, quotes[sym], instruments[sym], fee_bp, slippage_bp)
                    _sell_all(state, fees, sym, px, fee, ts)
            eq_now = _equity(state, marks)
        elif code == "FROZEN":
            state.frozen_until_ts = max(state.frozen_until_ts, until)

        # 6. Decisions, riskd, execution.
        if not state.halted:
            orders = 0
            for intent in random_trader.decide(ts, state, marks, context):
                last = last_buy_intent.get(intent.symbol)
                verdict = evaluate(
                    intent, state, market, policy, _counters(base, orders, last, eq_now), ts,
                    instruments, fee_bp, slippage_bp, False,
                )  # fmt: skip
                if not verdict.approved or intent.symbol not in quotes:
                    continue  # symbol without a quote: not tradable (like NO_QUOTE in the engine), never KeyError
                orders += 1
                if intent.side == Side.BUY:
                    last_buy_intent[intent.symbol] = ts
                inst = instruments[intent.symbol]
                px, fee = market_fill(intent.side, verdict.qty, quotes[intent.symbol], inst, fee_bp, slippage_bp)
                if _apply(state, intent.symbol, intent.side, verdict.qty, px, fee, ts):
                    intent_fills.append(ts)
                    fees.append((ts, fee))
                    if intent.side == Side.BUY and intent.stop_bp is not None:
                        state.positions[intent.symbol].stop_ueur = stop_price(px, intent.stop_bp, inst)

        eq_end = _equity(state, marks)
        eq_ts.append(ts)
        eq_val.append(eq_end)
        peak = max(peak, eq_end)
    return eq_val


def _normalize(instruments: Mapping[str, Instrument] | Iterable[Instrument]) -> dict[str, Instrument]:
    if isinstance(instruments, Mapping):
        return dict(instruments)
    return {i.symbol: i for i in instruments}


def simulate_trajectory(
    cycles: Sequence[CycleData],
    price_path: int,
    *,
    policy: Policy,
    instruments: Mapping[str, Instrument] | Iterable[Instrument],
    fee_bp: int,
    slippage_bp: int,
    capital_ueur: int,
) -> list[int]:
    """One path: equity (µEUR) after each cycle."""
    return _simulate(
        _prepare(cycles), price_path, policy, _normalize(instruments), fee_bp, slippage_bp, capital_ueur
    )


def simulate_random_trajectories(
    cycles: Sequence[CycleData],
    n: int = 1000,
    *,
    policy: Policy,
    instruments: Mapping[str, Instrument] | Iterable[Instrument],
    fee_bp: int,
    slippage_bp: int,
    capital_ueur: int,
) -> list[int]:
    """Final equity (µEUR) of each of the `n` random paths (numbers 1..n), deterministic."""
    if cycles and not any(c.bars for c in cycles):
        warnings.warn("no 4 h bar provided: the stops are not simulated", RuntimeWarning, stacklevel=2)
    prepared = _prepare(cycles)
    inst = _normalize(instruments)
    if not prepared:
        return [capital_ueur] * n
    return [
        _simulate(prepared, t, policy, inst, fee_bp, slippage_bp, capital_ueur)[-1] for t in range(1, n + 1)
    ]
