"""riskd: the risk guard (docs/SPEC-MVP.md §7). PURE FUNCTION, no I/O, no float.

`evaluate()` receives everything it needs as arguments (state, market, journal-derived counters,
policy) and returns a `Verdict`: approved with a quantity, or rejected with ALL the violated codes.
All amounts are integers (µEUR, 1e-8 units); rounding is adverse:
approved quantity rounded down, estimated cost and exposure rounded up, equity rounded down.

Principle: when in doubt (missing data, absurd value), the entry is REFUSED (fail closed).
A sale reduces risk: it is subject only to NOT_WHITELISTED, NO_SHORT, ORDER_RATE and
ORDER_TOO_SMALL (except a complete flatten), and remains allowed if the portfolio is frozen, halted
or the kill switch is active.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from arena.risk.policy import Policy
from arena.types import (
    QTY_SCALE,
    Instrument,
    Intent,
    PortfolioState,
    Quote,
    Side,
    Verdict,
    ceil_div,
    notional_ueur,
)

BP = 10_000  # 1 = 100% in basis points

# --- Rule codes of spec §7 ---
NOT_WHITELISTED = "NOT_WHITELISTED"
MAX_ORDER_SIZE = "MAX_ORDER_SIZE"
MAX_POSITION = "MAX_POSITION"
MAX_EXPOSURE = "MAX_EXPOSURE"
INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
DAILY_TRADES = "DAILY_TRADES"
ORDER_RATE = "ORDER_RATE"
TOO_SOON = "TOO_SOON"
STOP_REQUIRED = "STOP_REQUIRED"
STOP_RANGE = "STOP_RANGE"
EDGE_TOO_SMALL = "EDGE_TOO_SMALL"
FROZEN = "FROZEN"
HALTED = "HALTED"
FEE_BUDGET = "FEE_BUDGET"
PRICE_SANITY = "PRICE_SANITY"
SPREAD_ANOMALY = "SPREAD_ANOMALY"
ORDER_TOO_SMALL = "ORDER_TOO_SMALL"
NO_SHORT = "NO_SHORT"
KILL_SWITCH = "KILL_SWITCH"
# --- Technical codes (missing or absurd input: refuse) ---
BAD_SIDE = "BAD_SIDE"  # side is neither buy nor sell
BAD_SIZE = "BAD_SIZE"  # size_bp missing, not an integer or <= 0
BAD_PARAMS = "BAD_PARAMS"  # fee_bp / slippage_bp / now_ts negative or not integers
NO_QUOTE = "NO_QUOTE"  # quote missing or inconsistent (bid <= 0, ask < bid)
NO_MARK = "NO_MARK"  # a held position has no mark > 0: equity cannot be valued
NO_EQUITY = "NO_EQUITY"  # equity <= 0
UNKNOWN_INSTRUMENT = "UNKNOWN_INSTRUMENT"  # symbol missing from `instruments`
INTERNAL_ERROR = "INTERNAL_ERROR"  # bug: exception caught, refuse for safety

ALL_CODES: tuple[str, ...] = tuple(
    sorted(
        (
            NOT_WHITELISTED, MAX_ORDER_SIZE, MAX_POSITION, MAX_EXPOSURE, INSUFFICIENT_CASH, DAILY_TRADES,
            ORDER_RATE, TOO_SOON, STOP_REQUIRED, STOP_RANGE, EDGE_TOO_SMALL, FROZEN, HALTED, FEE_BUDGET,
            PRICE_SANITY, SPREAD_ANOMALY, ORDER_TOO_SMALL, NO_SHORT, KILL_SWITCH, BAD_SIDE, BAD_SIZE,
            BAD_PARAMS, NO_QUOTE, NO_MARK, NO_EQUITY, UNKNOWN_INSTRUMENT, INTERNAL_ERROR,
        )
    )
)  # fmt: skip


@dataclass(frozen=True)
class MarketView:
    """Market at decision time, per symbol (prices in µEUR).

    quotes            : current quote (bid/ask).
    last_closes       : last 4h close (closed bar); used by the PRICE_SANITY check.
    median_spreads_ueur : median of (ask - bid) over the symbol's last 20 quotes. If the history
                        is empty, the caller supplies the current spread (otherwise SPREAD_ANOMALY, fail closed).
    marks             : valuation price of each held position (in practice the quote mid).
    """

    quotes: Mapping[str, Quote] = field(default_factory=dict)
    last_closes: Mapping[str, int] = field(default_factory=dict)
    median_spreads_ueur: Mapping[str, int] = field(default_factory=dict)
    marks: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Counters:
    """Counters computed from the journal (nowhere else) and passed as arguments.

    trades_24h              : fills (buys and sells) of the portfolio over the sliding 24 h.
    orders_last_minute      : orders, all portfolios combined, over the last minute.
    last_symbol_intent_ts   : ts of this portfolio's last approved BUY intent on the evaluated
                              symbol (None if none). A rejected intent does not block.
    fees_month_ueur         : fees paid by the portfolio in the current calendar month.
    equity_month_start_ueur : portfolio equity at the start of the calendar month (capital if opened during the month).
    equity_24h_ago_ueur     : portfolio equity 24 h ago.
    equity_peak_ueur        : portfolio equity peak.
    equity_now_ueur         : current equity (last `equity` event), used by freeze_or_halt.
    """

    trades_24h: int = 0
    orders_last_minute: int = 0
    last_symbol_intent_ts: int | None = None
    fees_month_ueur: int = 0
    equity_month_start_ueur: int = 0
    equity_24h_ago_ueur: int = 0
    equity_peak_ueur: int = 0
    equity_now_ueur: int = 0


def _is_int(value: object) -> bool:
    return type(value) is int  # excludes bool and float


def _quote_ok(q: Quote | None) -> bool:
    return q is not None and _is_int(q.bid) and _is_int(q.ask) and q.bid > 0 and q.ask >= q.bid


def _freeze_halt(
    equity_now: int, state: PortfolioState, counters: Counters, policy: Policy, now_ts: int
) -> tuple[str | None, int]:
    """Shared core of freeze_or_halt and the evaluation check. Halt takes priority."""
    peak = counters.equity_peak_ueur
    if state.halted:
        return HALTED, 0
    # Drawdown >= threshold from the peak: (peak - eq) / peak >= bp / 10000.
    if peak > 0 and (peak - equity_now) * BP >= policy.drawdown_halt_bp * peak:
        return HALTED, 0
    ago = counters.equity_24h_ago_ueur
    # Loss >= threshold over 24 h: (ago - eq) / ago >= bp / 10000.
    if ago > 0 and (ago - equity_now) * BP >= policy.daily_loss_freeze_bp * ago:
        return FROZEN, now_ts + policy.freeze_duration_s
    return None, 0


def freeze_or_halt(
    state: PortfolioState, counters: Counters, policy: Policy, now_ts: int
) -> tuple[str | None, int]:
    """Say whether the portfolio must be halted, frozen, or neither.

    Returns (HALTED, 0) if drawdown >= drawdown_halt_bp (or already halted), (FROZEN, now_ts + duration) if the
    24 h loss >= daily_loss_freeze_bp, otherwise (None, 0). Current equity = counters.equity_now_ueur.
    """
    return _freeze_halt(counters.equity_now_ueur, state, counters, policy, now_ts)


def _positions_value(state: PortfolioState, marks: Mapping[str, int], *, round_up: bool) -> int | None:
    """Value of the positions at the marks; None if a held position has no mark > 0."""
    total = 0
    for symbol, pos in state.positions.items():
        if pos.qty <= 0:
            continue
        mark = marks.get(symbol)
        if not _is_int(mark) or mark <= 0:
            return None
        total += notional_ueur(pos.qty, mark, round_up=round_up)
    return total


def _reject(intent_id: str, reasons: set[str], policy: Policy) -> Verdict:
    return Verdict(
        intent_id=intent_id,
        approved=False,
        reasons=tuple(sorted(reasons)),
        qty=0,
        reserved_ueur=0,
        policy_sha256=policy.sha256,
    )


def _exec_price(ask: int, slippage_bp: int, tick: int) -> int:
    """Pessimistic buy price: ask plus slippage, rounded up, then up to the next tick."""
    px = ceil_div(ask * (BP + slippage_bp), BP)
    if tick > 0:
        px = ceil_div(px, tick) * tick
    return px


def _buy_total(qty: int, px: int, fee_bp: int) -> tuple[int, int]:
    """(cost, cost + fees) of a buy, both rounded up."""
    cost = notional_ueur(qty, px, round_up=True)
    return cost, cost + ceil_div(cost * fee_bp, BP)


def _buy_qty(budget: int, px: int, fee_bp: int) -> int:
    """Largest quantity whose cost + fees (rounded up) fits in `budget` (µEUR)."""
    if budget <= 0:
        return 0
    qty = budget * BP * QTY_SCALE // (px * (BP + fee_bp))
    while qty > 0:
        _, total = _buy_total(qty, px, fee_bp)
        if total <= budget:
            break
        # A step of ceil(excess * QTY_SCALE / px) removes at least `excess` µEUR of cost: one iteration is enough.
        qty -= max(1, ceil_div((total - budget) * QTY_SCALE, px))
    return max(qty, 0)


def _evaluate_buy(
    intent: Intent,
    state: PortfolioState,
    market: MarketView,
    policy: Policy,
    counters: Counters,
    now_ts: int,
    instruments: Mapping[str, Instrument],
    fee_bp: int,
    slippage_bp: int,
    kill_switch: bool,
) -> Verdict:
    sym = intent.symbol
    r: set[str] = set()

    if kill_switch:
        r.add(KILL_SWITCH)
    if sym not in policy.symbols:
        r.add(NOT_WHITELISTED)
    instrument = instruments.get(sym)
    if instrument is None:
        r.add(UNKNOWN_INSTRUMENT)

    # Equity (rounded down): cash + positions at the marks.
    pos_floor = _positions_value(state, market.marks, round_up=False)
    equity: int | None = None
    if pos_floor is None:
        r.add(NO_MARK)
    else:
        equity = state.cash_ueur + pos_floor
        if equity <= 0:
            r.add(NO_EQUITY)

    # Freeze / halt: state flags, and an independent recomputation from the equity valued at the marks.
    if state.frozen_until_ts > now_ts:
        r.add(FROZEN)
    if state.halted:
        r.add(HALTED)
    if equity is not None:
        code, _ = _freeze_halt(equity, state, counters, policy, now_ts)
        if code is not None:
            r.add(code)

    # Monthly fee budget: fees >= bp * start-of-month equity (start <= 0: refuse).
    start = counters.equity_month_start_ueur
    if start <= 0 or counters.fees_month_ueur * BP >= policy.monthly_fee_budget_bp * start:
        r.add(FEE_BUDGET)

    # Frequency.
    if counters.trades_24h >= policy.max_trades_per_day:
        r.add(DAILY_TRADES)
    if counters.orders_last_minute >= policy.max_orders_per_minute:
        r.add(ORDER_RATE)
    last = counters.last_symbol_intent_ts
    if last is not None and now_ts - last < policy.min_interval_same_symbol_s:
        r.add(TOO_SOON)

    # Stop is mandatory and bounded.
    stop = intent.stop_bp
    if stop is None:
        r.add(STOP_REQUIRED)
    elif not _is_int(stop) or not (policy.stop_bp_min <= stop <= policy.stop_bp_max):
        r.add(STOP_RANGE)

    # Market: quote, price consistency, spread, cost / gain.
    quote = market.quotes.get(sym)
    quote_ok = _quote_ok(quote)
    expected = intent.expected_move_bp
    if not _is_int(expected) or expected <= 0:
        r.add(EDGE_TOO_SMALL)
    if not quote_ok or quote is None:
        r.add(NO_QUOTE)
    else:
        bid, ask = quote.bid, quote.ask
        close = market.last_closes.get(sym)
        # |mid - close| / close > dev  <=>  |bid + ask - 2 close| * 10000 > dev * 2 * close
        if (
            not _is_int(close)
            or close <= 0
            or abs(bid + ask - 2 * close) * BP > policy.max_quote_deviation_bp * 2 * close
        ):
            r.add(PRICE_SANITY)
        spread = ask - bid
        median = market.median_spreads_ueur.get(sym)
        if not _is_int(median) or median < 0 or spread > policy.max_spread_multiple * median:
            r.add(SPREAD_ANOMALY)
        if _is_int(expected) and expected > 0:
            spread_bp = ceil_div(spread * 2 * BP, bid + ask)  # spread / mid, in bp, rounded up
            cost_rt_bp = 2 * (fee_bp + slippage_bp) + spread_bp
            if cost_rt_bp * 100 > policy.max_cost_to_expected_move_pct * expected:
                r.add(EDGE_TOO_SMALL)

    # Size.
    size = intent.size_bp
    size_ok = _is_int(size) and size > 0
    if not size_ok:
        r.add(BAD_SIZE)
    elif size > policy.max_order_bp:
        r.add(MAX_ORDER_SIZE)

    # Quantity and the rules that depend on it (position, exposure, cash, minimum size).
    qty = 0
    reserved = 0
    if (
        instrument is not None
        and quote is not None
        and quote_ok
        and equity is not None
        and equity > 0
        and size_ok
        and pos_floor is not None
    ):
        px = _exec_price(quote.ask, slippage_bp, instrument.tick_ueur)
        budget = equity * size // BP  # rounded down
        qty = _buy_qty(budget, px, fee_bp)
        cost, total = _buy_total(qty, px, fee_bp)
        reserved = total

        pos_ceil = _positions_value(state, market.marks, round_up=True)
        held = state.positions.get(sym)
        held_ceil = 0
        if held is not None and held.qty > 0:
            held_ceil = notional_ueur(held.qty, market.marks[sym], round_up=True)
        assert pos_ceil is not None  # the marks exist: pos_floor is not None
        if (held_ceil + cost) * BP > policy.max_position_bp * equity:
            r.add(MAX_POSITION)
        if (pos_ceil + cost) * BP > policy.max_exposure_bp * equity:
            r.add(MAX_EXPOSURE)
        if state.cash_ueur - total < 0:
            r.add(INSUFFICIENT_CASH)
        floor_value = notional_ueur(qty, px, round_up=False)
        if (
            qty <= 0
            or qty < instrument.lot_min_qty
            or floor_value < max(policy.min_order_ueur, instrument.cost_min_ueur)
        ):
            r.add(ORDER_TOO_SMALL)

    if r:
        return _reject(intent.intent_id, r, policy)
    return Verdict(
        intent_id=intent.intent_id,
        approved=True,
        reasons=(),
        qty=qty,
        reserved_ueur=reserved,
        policy_sha256=policy.sha256,
    )


def _evaluate_sell(
    intent: Intent,
    state: PortfolioState,
    market: MarketView,
    policy: Policy,
    counters: Counters,
    instruments: Mapping[str, Instrument],
) -> Verdict:
    sym = intent.symbol
    r: set[str] = set()

    if sym not in policy.symbols:
        r.add(NOT_WHITELISTED)
    if counters.orders_last_minute >= policy.max_orders_per_minute:
        r.add(ORDER_RATE)

    size = intent.size_bp
    held = state.positions.get(sym)
    held_qty = held.qty if held is not None else 0
    qty = 0
    if not _is_int(size) or size <= 0:
        r.add(BAD_SIZE)
    elif held_qty <= 0 or size > BP:
        r.add(NO_SHORT)  # nothing to sell, or more than the position
    else:
        qty = held_qty if size == BP else held_qty * size // BP  # rounded down
        if qty == 0:
            r.add(ORDER_TOO_SMALL)  # the requested fraction rounds to zero: never approve at qty 0
    full_exit = qty > 0 and qty == held_qty

    # Price used to value the sale (bid, otherwise the mark): used for ORDER_TOO_SMALL and the expected amount.
    quote = market.quotes.get(sym)
    price: int | None = None
    if _quote_ok(quote) and quote is not None:
        price = quote.bid
    else:
        mark = market.marks.get(sym)
        if _is_int(mark) and mark > 0:
            price = mark
    value = notional_ueur(qty, price, round_up=False) if price is not None else 0

    # Minimum size: except for a complete flatten (a full sale must always be able to go through).
    if qty > 0 and not full_exit:
        instrument = instruments.get(sym)
        if instrument is None:
            r.add(UNKNOWN_INSTRUMENT)
        elif price is None:
            r.add(NO_QUOTE)
        elif qty < instrument.lot_min_qty or value < max(policy.min_order_ueur, instrument.cost_min_ueur):
            r.add(ORDER_TOO_SMALL)

    if r:
        return _reject(intent.intent_id, r, policy)
    return Verdict(
        intent_id=intent.intent_id,
        approved=True,
        reasons=(),
        qty=qty,
        reserved_ueur=value,
        policy_sha256=policy.sha256,
    )


def evaluate(
    intent: Intent,
    state: PortfolioState,
    market: MarketView,
    policy: Policy,
    counters: Counters,
    now_ts: int,
    instruments: dict[str, Instrument],
    fee_bp: int,
    slippage_bp: int,
    kill_switch: bool,
) -> Verdict:
    """Validate an intent. Pure: same inputs, same verdict. Returns ALL the violated codes, sorted.

    Buy: quantity = floor(equity x size_bp / 10000 / execution price), fees included in the budget.
    The execution price is ask x (1 + slippage), rounded up then to the tick. Cost, fees and
    exposure are rounded up, equity down. Position and exposure are measured
    against the equity before the order. Any unexpected exception becomes an INTERNAL_ERROR rejection.
    """
    try:
        if (
            not _is_int(fee_bp)
            or not _is_int(slippage_bp)
            or not _is_int(now_ts)
            or fee_bp < 0
            or slippage_bp < 0
        ):
            return _reject(intent.intent_id, {BAD_PARAMS}, policy)
        if intent.side == Side.BUY:
            return _evaluate_buy(
                intent, state, market, policy, counters, now_ts, instruments, fee_bp, slippage_bp, kill_switch
            )
        if intent.side == Side.SELL:
            return _evaluate_sell(intent, state, market, policy, counters, instruments)
        return _reject(intent.intent_id, {BAD_SIDE}, policy)
    except Exception:  # noqa: BLE001 - fail closed: a bug must never produce an approval
        return _reject(intent.intent_id, {INTERNAL_ERROR}, policy)
