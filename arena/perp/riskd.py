"""riskd of the perp league: `evaluate_perp`, a PURE function (no I/O, no float, no clock).

Rules: docs/ETUDE-AGENTS-TRADERS.md §4 and config/policy-perp.toml. Every intent gets a verdict listing ALL
the rules it violates; any missing, stale or absurd input refuses an entry (fail closed); any unexpected
exception becomes INTERNAL_ERROR (its class name is kept in `verdict.error`).

Reductions and closes reduce risk. They only need the target instrument's quote and EUR/USD, and are only
subject to NO_POSITION, ORDER_RATE, NO_QUOTE and ORDER_TOO_SMALL (except a full close): they pass when the
portfolio is frozen or halted, under the kill switch, with stale data on other instruments, and even on an
instrument removed from the whitelist since the position was opened.

The quantity, the expected fill, the fees and the post-trade state are computed with the simulator's own
functions (same slippage, ticks, fees, unfavourable conversions), so an approved entry is one the simulator
accepts. The same function serves the agents' `simulate_order` tool.

Loss at a stop (MAX_TRADE_LOSS, MAX_OPEN_RISK) is the equity lost if the stop fills NOW: from the current
mark (not the entry, so an unrealized gain given back counts), to a fill `stop_gap_bp` beyond the stop plus
the simulator's slippage, plus the exit fee.

The aggressive profile (the Haiku council, docs/SPEC-PERP-COUNCIL-HAIKU.md §5) changes three things only: the
initial margin is Kraken's own schedule (`arena/perp/margin.py`) instead of the AMF 50 %; every stop must be
reached before the liquidation (LIQUIDATION_BEFORE_STOP: the equity left at the stops, each alone and all
together, covers Kraken's maintenance margin at those prices); a daily freeze or a fee budget set to 0 is off.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field

from arena.perp.ledger import (
    BP,
    MarginAccount,
    PerpLedgerError,
    apply_fill,
    cost_eur,
    equity_ueur,
    gross_exposure_ueur,
    notional_up,
)
from arena.perp.margin import INITIAL, MAINTENANCE, margin_ueur
from arena.perp.policy import AGGRESSIVE, PerpPolicy
from arena.perp.sim import SimParams, buy_price, fee_ueur, sell_price, tick_down, tick_up
from arena.perp.types import InstrumentSpec
from arena.types import MICRO, QTY_SCALE, ceil_div

ACTIONS = ("open_long", "open_short", "reduce", "close")
E12 = 1_000_000_000_000
FUTURE_TOLERANCE_S = 5  # a timestamp more than 5 s ahead of now is treated as bad data

# --- rule codes ---
NOT_WHITELISTED = "NOT_WHITELISTED"
NOT_TRADEABLE = "NOT_TRADEABLE"
UNKNOWN_INSTRUMENT = "UNKNOWN_INSTRUMENT"
BAD_ACTION = "BAD_ACTION"
BAD_PORTFOLIO = "BAD_PORTFOLIO"
INTENT_STALE = "INTENT_STALE"
BAD_SIZE = "BAD_SIZE"
BAD_HORIZON = "BAD_HORIZON"
BAD_TAKE_PROFIT = "BAD_TAKE_PROFIT"
BAD_EXPECTED_MOVE = "BAD_EXPECTED_MOVE"
NO_QUOTE = "NO_QUOTE"
NO_MARK = "NO_MARK"
NO_FX = "NO_FX"
NO_EQUITY = "NO_EQUITY"
NO_POSITION = "NO_POSITION"
NO_FLIP = "NO_FLIP"
KILL_SWITCH = "KILL_SWITCH"
HALTED = "HALTED"
FROZEN = "FROZEN"
COUNTERS_MISSING = "COUNTERS_MISSING"
FEE_BUDGET = "FEE_BUDGET"
DAILY_TRADES = "DAILY_TRADES"
ORDER_RATE = "ORDER_RATE"
TOO_SOON = "TOO_SOON"
DATA_STALE = "DATA_STALE"
MARK_SANITY = "MARK_SANITY"
SPREAD_ANOMALY = "SPREAD_ANOMALY"
FUNDING_EXTREME = "FUNDING_EXTREME"
MAX_ORDER_SIZE = "MAX_ORDER_SIZE"
STOP_REQUIRED = "STOP_REQUIRED"
STOP_RANGE = "STOP_RANGE"
EDGE_TOO_SMALL = "EDGE_TOO_SMALL"
ORDER_TOO_SMALL = "ORDER_TOO_SMALL"
MAX_CONTRACT_POSITION = "MAX_CONTRACT_POSITION"
MAX_POSITION = "MAX_POSITION"
MAX_LEVERAGE = "MAX_LEVERAGE"
INITIAL_MARGIN = "INITIAL_MARGIN"
MAX_TRADE_LOSS = "MAX_TRADE_LOSS"
MAX_OPEN_RISK = "MAX_OPEN_RISK"
LIQUIDATION_BEFORE_STOP = "LIQUIDATION_BEFORE_STOP"
INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class PerpIntent:
    """A decision of an agent (or a benchmark), before riskd.

    open_long / open_short: `size_bp` = notional in bp of the equity; `stop_bp` = stop distance from the
    expected fill (required); `take_profit_bp` = optional target distance; `horizon_h` (<= 168), and
    `expected_move_bp` (the declared move, capped by the policy). reduce: `size_bp` = part of the position
    in bp (10000 = all). close: the whole position.
    """

    intent_id: str
    portfolio: str
    ts: int
    instrument: str
    action: str
    size_bp: int | None = None
    stop_bp: int | None = None
    take_profit_bp: int | None = None
    horizon_h: int | None = None
    expected_move_bp: int | None = None
    confidence_pct: int | None = None


@dataclass(frozen=True)
class InstrumentMarket:
    """What riskd knows of one instrument at decision time (µUSD; relative funding per hour x 1e12).
    Every value carries the timestamp of its observation."""

    bid_uusd: int
    ask_uusd: int
    quote_ts: int
    mark_uusd: int
    mark_ts: int
    index_uusd: int | None
    index_ts: int | None
    relative_funding_e12: int | None
    funding_ts: int | None
    median_spread_uusd: int | None


@dataclass(frozen=True)
class PerpMarketView:
    instruments: Mapping[str, InstrumentMarket]
    fx_bid: int
    fx_ask: int
    fx_ts: int


@dataclass(frozen=True)
class PerpCounters:
    """Counters computed from the league journal only, passed in (riskd stays pure). The equity
    references have NO default: a caller that cannot compute them must say so (0 refuses entries)."""

    equity_month_start_ueur: int
    equity_24h_ago_ueur: int
    equity_peak_ueur: int
    opens_24h: int = 0
    orders_last_minute: int = 0
    last_open_ts: Mapping[str, int] = field(default_factory=dict)
    fees_month_ueur: int = 0


@dataclass(frozen=True)
class PerpVerdict:
    intent_id: str
    approved: bool
    reasons: tuple[str, ...]
    qty: int = 0  # signed quantity to fill (1e-8 units); 0 if rejected
    est_price_uusd: int = 0
    stop_uusd: int | None = None  # stop of the WHOLE position after the order
    take_profit_uusd: int | None = None
    policy_sha256: str = ""
    metrics: Mapping[str, int] = field(default_factory=dict)
    error: str | None = None  # class name of an unexpected exception (INTERNAL_ERROR)


def _is_int(v: object) -> bool:
    return type(v) is int


def _reject(
    intent: PerpIntent,
    reasons: set[str],
    policy: PerpPolicy,
    metrics: dict[str, int] | None = None,
    error: str | None = None,
) -> PerpVerdict:
    return PerpVerdict(
        intent.intent_id,
        False,
        tuple(sorted(reasons)),
        policy_sha256=policy.sha256,
        metrics=metrics or {},
        error=error,
    )


def _fresh(ts: object, now_ts: int, max_age_s: int) -> bool:
    return _is_int(ts) and -FUTURE_TOLERANCE_S <= now_ts - ts <= max_age_s  # type: ignore[operator]


def stop_exit_price(qty: int, stop_uusd: int, tick: int, gap_bp: int, params: SimParams) -> int:
    """Pessimistic fill of a stop: `gap_bp` beyond the stop, then the simulator's slippage and tick."""
    if qty > 0:
        return max(sell_price(stop_uusd * (BP - gap_bp) // BP, params.slippage_bp, tick), tick)
    return buy_price(ceil_div(stop_uusd * (BP + gap_bp), BP), params.slippage_bp, tick)


def loss_at_stop_ueur(
    qty: int,
    stop_uusd: int | None,
    mark_uusd: int,
    tick: int,
    gap_bp: int,
    params: SimParams,
    fx: tuple[int, int],
) -> int:
    """Equity lost (>= 0, µEUR) if the position's stop filled now: from the MARK to the pessimistic stop
    fill, plus the exit fee. A position without a stop counts for its whole notional at the mark."""
    if stop_uusd is None:
        return cost_eur(notional_up(qty, mark_uusd), *fx)
    exit_px = stop_exit_price(qty, stop_uusd, tick, gap_bp, params)
    move = (mark_uusd - exit_px) if qty > 0 else (exit_px - mark_uusd)
    loss_uusd = max(0, ceil_div(move * abs(qty), QTY_SCALE))
    return cost_eur(loss_uusd, *fx) + fee_ueur(qty, exit_px, params.taker_fee_bp, *fx)


def _freeze_halt(
    acc: MarginAccount, equity: int, c: PerpCounters, policy: PerpPolicy, now_ts: int
) -> set[str]:
    r: set[str] = set()
    if acc.halted:
        r.add(HALTED)
    if acc.frozen_until_ts > now_ts:
        r.add(FROZEN)
    if not (_is_int(c.equity_peak_ueur) and _is_int(c.equity_24h_ago_ueur)) or c.equity_24h_ago_ueur <= 0:
        r.add(COUNTERS_MISSING)
        return r
    peak = max(c.equity_peak_ueur, acc.capital_ueur, equity)
    if (peak - equity) * BP >= policy.drawdown_halt_bp * peak:
        r.add(HALTED)
    ago = c.equity_24h_ago_ueur
    if policy.daily_loss_freeze_bp and (ago - equity) * BP >= policy.daily_loss_freeze_bp * ago:
        r.add(FROZEN)
    return r


def _kraken_margins(
    after: MarginAccount,
    marks: Mapping[str, int],
    specs: Mapping[str, InstrumentSpec],
    policy: PerpPolicy,
    params: SimParams,
    fx: tuple[int, int],
    eq_after: int,
    risks: Mapping[str, int],
    inst: str,
) -> set[str]:
    """Kraken's initial margin after the order, and the liquidation never reached before the stops: the
    equity left when the traded position's stop fills (the others at the mark), and when every stop fills
    at once, covers the maintenance margin with the positions valued at those stop prices."""
    r: set[str] = set()
    levels = {i: specs[i].margin_levels for i in after.positions}
    at_mark = {i: notional_up(p.qty, marks[i]) for i, p in after.positions.items()}
    if eq_after < margin_ueur(at_mark, levels, INITIAL, *fx):
        r.add(INITIAL_MARGIN)
    at_stop = {}
    for i, p in after.positions.items():
        exit_px = (
            marks[i]
            if p.stop_uusd is None
            else stop_exit_price(p.qty, p.stop_uusd, specs[i].tick_uusd, policy.stop_gap_bp, params)
        )
        at_stop[i] = notional_up(p.qty, exit_px)
    alone = {**at_mark, inst: at_stop[inst]}
    if eq_after - risks[inst] < margin_ueur(alone, levels, MAINTENANCE, *fx):
        r.add(LIQUIDATION_BEFORE_STOP)
    if eq_after - sum(risks.values()) < margin_ueur(at_stop, levels, MAINTENANCE, *fx):
        r.add(LIQUIDATION_BEFORE_STOP)
    return r


def evaluate_perp(
    intent: PerpIntent,
    acc: MarginAccount,
    market: PerpMarketView,
    specs: Mapping[str, InstrumentSpec],
    counters: PerpCounters,
    policy: PerpPolicy,
    params: SimParams,
    now_ts: int,
    kill_switch: bool,
) -> PerpVerdict:
    """Pure: same inputs, same verdict. See the module docstring."""
    try:
        if intent.action in ("reduce", "close"):
            return _evaluate_reduce(intent, acc, market, specs, counters, policy, params, now_ts)
        return _evaluate_entry(intent, acc, market, specs, counters, policy, params, now_ts, kill_switch)
    except Exception as exc:  # noqa: BLE001 - fail closed: a bug must never produce an approval
        return _reject(intent, {INTERNAL_ERROR}, policy, error=type(exc).__name__)


def _common(
    intent: PerpIntent, acc: MarginAccount, counters: PerpCounters, policy: PerpPolicy, now_ts: int
) -> set[str]:
    r: set[str] = set()
    if intent.portfolio != acc.portfolio:
        r.add(BAD_PORTFOLIO)
    if not _fresh(intent.ts, now_ts, policy.max_data_age_s):
        r.add(INTENT_STALE)
    if (
        not _is_int(counters.orders_last_minute)
        or counters.orders_last_minute >= policy.max_orders_per_minute
    ):
        r.add(ORDER_RATE)
    return r


def _quote_ok(m: InstrumentMarket | None) -> bool:
    return m is not None and _is_int(m.bid_uusd) and _is_int(m.ask_uusd) and 0 < m.bid_uusd <= m.ask_uusd


def _evaluate_reduce(
    intent: PerpIntent,
    acc: MarginAccount,
    market: PerpMarketView,
    specs: Mapping[str, InstrumentSpec],
    counters: PerpCounters,
    policy: PerpPolicy,
    params: SimParams,
    now_ts: int,
) -> PerpVerdict:
    inst = intent.instrument
    r = _common(intent, acc, counters, policy, now_ts)
    pos = acc.positions.get(inst)
    if pos is None:
        r.add(NO_POSITION)
        return _reject(intent, r, policy)
    spec = specs.get(inst)
    m = market.instruments.get(inst)
    fx = (market.fx_bid, market.fx_ask)
    if spec is None or not _is_int(spec.tick_uusd) or spec.tick_uusd <= 0:
        r.add(UNKNOWN_INSTRUMENT)
    if not (_is_int(fx[0]) and _is_int(fx[1]) and 0 < fx[0] <= fx[1]):
        r.add(NO_FX)
    if not _quote_ok(m):
        r.add(NO_QUOTE)
    if r & {UNKNOWN_INSTRUMENT, NO_FX, NO_QUOTE}:
        return _reject(intent, r, policy)
    assert spec is not None and m is not None
    tick, lot = spec.tick_uusd, spec.lot_step_qty or 1
    if intent.action == "close":
        q = abs(pos.qty)
    else:
        size = intent.size_bp
        if not _is_int(size) or not 0 < size <= BP:
            r.add(BAD_SIZE)
            return _reject(intent, r, policy)
        q = abs(pos.qty) * size // BP // lot * lot
    full = q == abs(pos.qty)
    if pos.qty > 0:
        price = sell_price(m.bid_uusd, params.slippage_bp, tick)
    else:
        price = buy_price(m.ask_uusd, params.slippage_bp, tick)
    if price <= 0:
        r.add(NO_QUOTE)
    elif not full and (q <= 0 or cost_eur(notional_up(q, price), *fx) < policy.min_order_ueur):
        r.add(ORDER_TOO_SMALL)
    if r:
        return _reject(intent, r, policy)
    return PerpVerdict(
        intent.intent_id,
        True,
        (),
        qty=-q if pos.qty > 0 else q,
        est_price_uusd=price,
        stop_uusd=None if full else pos.stop_uusd,
        take_profit_uusd=None if full else pos.take_profit_uusd,
        policy_sha256=policy.sha256,
    )


def _evaluate_entry(
    intent: PerpIntent,
    acc: MarginAccount,
    market: PerpMarketView,
    specs: Mapping[str, InstrumentSpec],
    counters: PerpCounters,
    policy: PerpPolicy,
    params: SimParams,
    now_ts: int,
    kill_switch: bool,
) -> PerpVerdict:
    inst = intent.instrument
    if intent.action not in ACTIONS:
        return _reject(intent, {BAD_ACTION}, policy)
    side = 1 if intent.action == "open_long" else -1
    r = _common(intent, acc, counters, policy, now_ts)
    if inst not in policy.instruments:
        r.add(NOT_WHITELISTED)
    age = policy.max_data_age_s

    # instruments: the traded one and every held one need a spec, a fresh mark (and, for the traded one,
    # a fresh quote, index and funding)
    marks: dict[str, int] = {}
    for i in set(acc.positions) | {inst}:
        sp = specs.get(i)
        if (
            sp is None
            or not _is_int(sp.tick_uusd)
            or sp.tick_uusd <= 0
            or not _is_int(sp.lot_step_qty)
            or sp.lot_step_qty <= 0
        ):
            r.add(UNKNOWN_INSTRUMENT)
        im = market.instruments.get(i)
        if im is None or not _is_int(im.mark_uusd) or im.mark_uusd <= 0:
            r.add(NO_MARK)
            continue
        marks[i] = im.mark_uusd
        if not _fresh(im.mark_ts, now_ts, age):
            r.add(DATA_STALE)
    fx = (market.fx_bid, market.fx_ask)
    if not (_is_int(fx[0]) and _is_int(fx[1]) and 0 < fx[0] <= fx[1]):
        r.add(NO_FX)
    elif not _fresh(market.fx_ts, now_ts, age):
        r.add(DATA_STALE)
    m = market.instruments.get(inst)
    if not _quote_ok(m):
        r.add(NO_QUOTE)
    if r & {UNKNOWN_INSTRUMENT, NO_FX, NO_QUOTE, NO_MARK}:
        return _reject(intent, r, policy)
    spec = specs[inst]
    assert m is not None and spec.lot_step_qty is not None
    tick, lot = spec.tick_uusd, spec.lot_step_qty
    if not spec.tradeable:
        r.add(NOT_TRADEABLE)
    if not _fresh(m.quote_ts, now_ts, age) or not _fresh(m.funding_ts, now_ts, age):
        r.add(DATA_STALE)
    equity = equity_ueur(acc, marks, *fx)
    if equity <= 0:
        r.add(NO_EQUITY)
    pos = acc.positions.get(inst)
    if pos is not None and (pos.qty > 0) != (side > 0):
        r.add(NO_FLIP)
    if kill_switch:
        r.add(KILL_SWITCH)
    r |= _freeze_halt(acc, equity, counters, policy, now_ts)
    if counters.opens_24h >= policy.max_opens_per_day:
        r.add(DAILY_TRADES)
    last = counters.last_open_ts.get(inst)
    if last is not None and now_ts - last < policy.min_interval_same_open_s:
        r.add(TOO_SOON)

    # market sanity
    mid2 = m.bid_uusd + m.ask_uusd  # twice the mid
    idx = m.index_uusd
    if not _is_int(idx) or idx <= 0 or not _fresh(m.index_ts, now_ts, age):
        r.add(MARK_SANITY)
    else:
        if abs(m.mark_uusd - idx) * BP > policy.max_mark_index_bp * idx:
            r.add(MARK_SANITY)
        if abs(mid2 - 2 * idx) * BP > policy.max_mid_index_bp * 2 * idx:
            r.add(MARK_SANITY)
    if abs(mid2 - 2 * m.mark_uusd) * BP > policy.max_mid_mark_bp * 2 * m.mark_uusd:
        r.add(MARK_SANITY)
    spread = m.ask_uusd - m.bid_uusd
    med = m.median_spread_uusd
    if not _is_int(med) or med < 0 or spread > policy.max_spread_multiple * max(med, tick):
        r.add(SPREAD_ANOMALY)
    rate = m.relative_funding_e12
    if not _is_int(rate):
        r.add(DATA_STALE)
        rate = 0
    elif side * rate >= policy.funding_extreme_e12:
        r.add(FUNDING_EXTREME)

    # intent fields
    size = intent.size_bp
    if not _is_int(size) or size <= 0:
        r.add(BAD_SIZE)
    elif size > policy.max_order_bp:
        r.add(MAX_ORDER_SIZE)
    stop_bp = intent.stop_bp
    if stop_bp is None:
        r.add(STOP_REQUIRED)
    elif not _is_int(stop_bp) or not policy.stop_bp_min <= stop_bp <= policy.stop_bp_max:
        r.add(STOP_RANGE)
    tp_bp = intent.take_profit_bp
    if tp_bp is not None and (not _is_int(tp_bp) or not 0 < tp_bp <= BP):
        r.add(BAD_TAKE_PROFIT)
    horizon = intent.horizon_h
    if horizon is not None and (not _is_int(horizon) or not 0 < horizon <= policy.max_funding_horizon_h):
        r.add(BAD_HORIZON)
    move = intent.expected_move_bp
    if move is not None and (not _is_int(move) or move > policy.max_expected_move_bp):
        r.add(BAD_EXPECTED_MOVE)
    metrics: dict[str, int] = {"equity_ueur": equity}

    # cost versus expected move: round trip + mid-vs-mark gap + adverse funding over the horizon
    spread_bp = ceil_div(spread * 2 * BP, mid2)
    gap_bp = ceil_div(abs(mid2 - 2 * m.mark_uusd) * BP, 2 * m.mark_uusd)
    cost_rt_bp = 2 * (params.taker_fee_bp + params.slippage_bp) + spread_bp + gap_bp
    hours = (
        horizon
        if _is_int(horizon) and 0 < horizon <= policy.max_funding_horizon_h
        else policy.max_funding_horizon_h
    )
    funding_bp = ceil_div(side * rate * hours * BP, E12) if side * rate > 0 else 0
    metrics.update(cost_rt_bp=cost_rt_bp, funding_cost_bp=funding_bp)
    if (
        not _is_int(move)
        or move <= 0
        or (cost_rt_bp + funding_bp) * 100 > policy.max_cost_to_expected_move_pct * move
    ):
        r.add(EDGE_TOO_SMALL)

    if r & {BAD_SIZE, NO_EQUITY, STOP_REQUIRED, STOP_RANGE}:
        return _reject(intent, r, policy, metrics)

    # quantity: notional in EUR -> USD at the bid (fewer dollars), at the expected fill, floored to the lot
    if side > 0:
        price = buy_price(m.ask_uusd, params.slippage_bp, tick)
    else:
        price = sell_price(m.bid_uusd, params.slippage_bp, tick)
    target_uusd = equity * size // BP * fx[0] // MICRO
    q = target_uusd * QTY_SCALE // max(price, 1) // lot * lot
    if price <= 0 or q <= 0 or cost_eur(notional_up(q, price), *fx) < policy.min_order_ueur:
        r.add(ORDER_TOO_SMALL)
        return _reject(intent, r, policy, metrics)
    qty = side * q
    if spec.max_position_qty is not None and abs((pos.qty if pos else 0) + qty) > spec.max_position_qty:
        r.add(MAX_CONTRACT_POSITION)
    fee = fee_ueur(qty, price, params.taker_fee_bp, *fx)
    exit_fee_est = fee_ueur(qty, price, params.taker_fee_bp, *fx)
    start = counters.equity_month_start_ueur
    if policy.monthly_fee_budget_bp == 0 and policy.profile == AGGRESSIVE:
        pass  # no fee budget: the fees stay real and count in the result
    elif (
        not _is_int(start)
        or start <= 0
        or (counters.fees_month_ueur + fee + exit_fee_est) * BP > policy.monthly_fee_budget_bp * start
    ):
        r.add(FEE_BUDGET)

    # stop and target of the whole position after the order (an increase never loosens the stop)
    if side > 0:
        stop = max(tick_down(price * (BP - stop_bp) // BP, tick), tick)
    else:
        stop = tick_up(ceil_div(price * (BP + stop_bp), BP), tick)
    if pos is not None and pos.stop_uusd is not None and NO_FLIP not in r:
        stop = max(stop, pos.stop_uusd) if side > 0 else min(stop, pos.stop_uusd)
    if (side > 0 and stop >= m.mark_uusd) or (side < 0 and stop <= m.mark_uusd):
        r.add(STOP_RANGE)  # would trigger at once
    take_profit = None
    if _is_int(tp_bp) and BAD_TAKE_PROFIT not in r:
        if side > 0:
            take_profit = tick_up(ceil_div(price * (BP + tp_bp), BP), tick)
        else:
            take_profit = max(tick_down(price * (BP - tp_bp) // BP, tick), tick)

    # post-trade state, with the ledger's own rules
    after = copy.deepcopy(acc)
    probe = {
        "instrument": inst,
        "qty": qty,
        "price_uusd": price,
        "fee_ueur": fee,
        "fx_bid": fx[0],
        "fx_ask": fx[1],
        "reason": "intent",
    }
    try:
        apply_fill(after, probe, max(now_ts, acc.last_fill_ts), 0)
    except PerpLedgerError:
        r.add(NO_FLIP)
        return _reject(intent, r, policy, metrics)
    after.positions[inst].stop_uusd = stop
    eq_after = equity_ueur(after, marks, *fx)
    gross_after = gross_exposure_ueur(after, marks, *fx)
    inst_notional = cost_eur(notional_up(after.positions[inst].qty, marks[inst]), *fx)
    risks = {
        i: loss_at_stop_ueur(p.qty, p.stop_uusd, marks[i], specs[i].tick_uusd, policy.stop_gap_bp, params, fx)
        for i, p in after.positions.items()
    }
    metrics.update(
        equity_after_ueur=eq_after,
        gross_after_ueur=gross_after,
        position_after_ueur=inst_notional,
        trade_loss_ueur=risks[inst],
        open_risk_ueur=sum(risks.values()),
        fee_ueur=fee,
    )
    if eq_after <= 0:
        r.add(NO_EQUITY)
    if gross_after * BP > policy.max_leverage_bp * eq_after:
        r.add(MAX_LEVERAGE)
    if policy.profile == AGGRESSIVE:
        r |= _kraken_margins(after, marks, specs, policy, params, fx, eq_after, risks, inst)
        metrics.update(
            initial_margin_ueur=margin_ueur(
                {i: notional_up(p.qty, marks[i]) for i, p in after.positions.items()},
                {i: specs[i].margin_levels for i in after.positions},
                INITIAL,
                *fx,
            )
        )
    elif eq_after * BP < params.initial_margin_bp * gross_after:
        r.add(INITIAL_MARGIN)
    if inst_notional * BP > policy.max_position_bp * eq_after:
        r.add(MAX_POSITION)
    if risks[inst] * BP > policy.max_trade_loss_bp * eq_after:
        r.add(MAX_TRADE_LOSS)
    if sum(risks.values()) * BP > policy.max_open_risk_bp * eq_after:
        r.add(MAX_OPEN_RISK)
    if r:
        return _reject(intent, r, policy, metrics)
    return PerpVerdict(
        intent.intent_id,
        True,
        (),
        qty=qty,
        est_price_uusd=price,
        stop_uusd=stop,
        take_profit_uusd=take_profit,
        policy_sha256=policy.sha256,
        metrics=metrics,
    )
