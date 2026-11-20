"""Random trajectories behind the "rank against chance", replayed over the cycles AND the completed wake-ups.

The engine's simulator (`arena.benchmarks.price_paths`, frozen during the season) only knows cycles: each round
has a quote for every symbol, bar-based stops and a maximum holding. A wake-up differs
(docs/WATCH.md §2): only the symbols quoted at the wake-up are tradable (the others get NO_QUOTE), there is
neither a bar-based stop nor a maximum holding, the median of the spreads stays that of the cycle quotes, PRICE_SANITY
compares against the 1-minute close, and no equity is journaled (the 24 h, month and peak references stay those of
the cycles). This module therefore replays the same agent, with the same engine building blocks (riskd, fills,
`random_trader.decide`), following those differences. Without a wake-up, it returns exactly the same numbers as the
engine's simulator (checked by tests/test_site.py).
"""

from __future__ import annotations

from bisect import bisect_right
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from arena.ledger import month_start_ts
from arena.risk.policy import Policy
from arena.risk.riskd import MarketView, evaluate, freeze_or_halt
from arena.sim.fills import market_fill, stop_fill, stop_price
from arena.benchmarks import BenchmarkContext, random_trader
from arena.benchmarks.price_paths import (
    DAY_S,
    SPREAD_WINDOW,
    CycleData,
    _apply,
    _counters,
    _equity,
    _fee,
    _sell_all,
)
from arena.types import Instrument, PortfolioState, Side


@dataclass(frozen=True)
class Round:
    """A 4 h cycle (`wakeup=False`) or a completed wake-up (`wakeup=True`, quotes of the quoted symbols only)."""

    data: CycleData
    wakeup: bool = False


@dataclass(frozen=True)
class _Prepared:
    ts: int
    wakeup: bool
    market: MarketView
    bars: Mapping[str, Sequence]
    month_start: int


def _prepare(rounds: Sequence[Round]) -> list[_Prepared]:
    spreads: dict[str, deque[int]] = {}
    medians: dict[str, int] = {}  # current median, updated at cycles only (like the engine's `_view`)
    out = []
    for r in rounds:
        c = r.data
        closes: dict[str, int] = {}
        if not r.wakeup:
            for sym, q in c.quotes.items():
                win = spreads.setdefault(sym, deque(maxlen=SPREAD_WINDOW))
                win.append(q.ask - q.bid)
                medians[sym] = sorted(win)[len(win) // 2]
        med = {}
        for sym, q in c.quotes.items():
            # Without cycle history, the current spread (MarketView rule: otherwise SPREAD_ANOMALY).
            med[sym] = medians.get(sym, q.ask - q.bid)
            closes[sym] = c.last_closes.get(sym, (q.bid + q.ask) // 2)
        out.append(_Prepared(c.ts, r.wakeup, MarketView(c.quotes, closes, med, c.marks), c.bars, month_start_ts(c.ts)))
    return out


def _simulate(
    prepared: Sequence[_Prepared], price_path: int, policy: Policy, instruments: Mapping[str, Instrument],
    fee_bp: int, slippage_bp: int, capital_ueur: int, since: int | None = None,
) -> tuple[int, int]:  # fmt: skip
    """(equity at the start of round `since`, before any action; final equity) of trajectory `price_path`.
    Same flow as `price_paths._simulate` at the cycles. Without `since`, the first value is the capital."""
    state = PortfolioState(random_trader.PORTFOLIO, capital_ueur)
    context = BenchmarkContext(symbols=tuple(instruments), price_path=price_path)
    eq_ts: list[int] = []
    eq_val: list[int] = []
    peak = capital_ueur
    intent_fills: deque[int] = deque()
    fees: list[tuple[int, int]] = []
    last_buy_intent: dict[str, int] = {}
    eq_end = capital_ueur
    eq_start = capital_ueur

    for cyc in prepared:
        ts, market = cyc.ts, cyc.market
        marks, quotes = market.marks, market.quotes
        if since is not None and ts == since:
            eq_start = _equity(state, marks)  # like season_reference: before the round's decisions

        # Bar-based stops and maximum holding: at cycles only (a wake-up has none).
        if not cyc.wakeup:
            for sym in list(state.positions):
                pos = state.positions[sym]
                inst = instruments[sym]
                if pos.stop_ueur is not None:
                    for bar in cyc.bars.get(sym, ()):
                        if bar.ts < pos.opened_ts:
                            continue  # bar started before the entry (SimExecutor guard; relevant as soon as positions are opened at a wake-up)
                        px = stop_fill(pos.stop_ueur, bar, inst, slippage_bp)
                        if px is not None:
                            _sell_all(state, fees, sym, px, _fee(pos.qty, px, fee_bp), ts)
                            break
                if sym in state.positions and ts - pos.opened_ts >= policy.max_holding_s and sym in quotes:
                    px, fee = market_fill(Side.SELL, pos.qty, quotes[sym], inst, fee_bp, slippage_bp)
                    _sell_all(state, fees, sym, px, fee, ts)

        while intent_fills and intent_fills[0] <= ts - DAY_S:
            intent_fills.popleft()
        fees[:] = [(t, f) for t, f in fees if t >= cyc.month_start]
        i24 = bisect_right(eq_ts, ts - DAY_S)
        eq_24h = eq_val[i24 - 1] if i24 else capital_ueur
        im = bisect_right(eq_ts, cyc.month_start - 1)
        eq_month = eq_val[im - 1] if im else capital_ueur
        eq_now = _equity(state, marks)
        base = (len(intent_fills), sum(f for _, f in fees), eq_month, eq_24h, peak)

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

        if not state.halted:
            orders = 0
            for intent in random_trader.decide(ts, state, marks, context):
                if intent.symbol not in quotes:
                    continue  # symbol not quoted at this wake-up: NO_QUOTE, like the engine
                last = last_buy_intent.get(intent.symbol)
                verdict = evaluate(
                    intent, state, market, policy, _counters(base, orders, last, eq_now), ts,
                    instruments, fee_bp, slippage_bp, False,  # type: ignore[arg-type]
                )  # fmt: skip
                if not verdict.approved:
                    continue
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
        if not cyc.wakeup:  # no equity journaled at a wake-up: 24 h, month and peak references come from the cycles
            eq_ts.append(ts)
            eq_val.append(eq_end)
            peak = max(peak, eq_end)
    return eq_start, eq_end


def price_paths(
    rounds: Sequence[Round], n: int, *, policy: Policy, instruments: Mapping[str, Instrument], fee_bp: int,
    slippage_bp: int, capital_ueur: int,
) -> list[int]:  # fmt: skip
    """Final equity (µEUR) of trajectories 1..n, deterministic."""
    return [f for _d, f in price_paths_since(
        rounds, n, policy=policy, instruments=instruments, fee_bp=fee_bp, slippage_bp=slippage_bp,
        capital_ueur=capital_ueur,
    )]  # fmt: skip


def price_paths_since(
    rounds: Sequence[Round], n: int, *, policy: Policy, instruments: Mapping[str, Instrument], fee_bp: int,
    slippage_bp: int, capital_ueur: int, since: int | None = None,
) -> list[tuple[int, int]]:  # fmt: skip
    """(equity at the start of round `since`, final equity) of trajectories 1..n. All rounds are replayed
    (the burn-in seeds the spread median, the peak and the 24 h and month references), measurement starts at `since`."""
    prepared = _prepare(rounds)
    if not prepared:
        return [(capital_ueur, capital_ueur)] * n
    return [
        _simulate(prepared, t, policy, instruments, fee_bp, slippage_bp, capital_ueur, since) for t in range(1, n + 1)
    ]
