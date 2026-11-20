"""Ledger of the perpetual futures league, rebuilt from its own journal only (docs/SPEC-PERP-LEDGER.md).

Integers only. Collateral and euro amounts in µEUR, prices in µUSD, signed quantities in 1e-8 units,
EUR/USD in µUSD per EUR. Every USD -> EUR conversion is unfavourable to the portfolio (spec §1).

Invariant (spec §3): collateral = capital + realized_pnl - fees_paid - funding_paid + absorbed_deficit,
and collateral >= 0 after every event (negative-balance protection).

`PerpBook` replays the journal incrementally (one event at a time) and refuses what the spec forbids:
a flip, a duplicate order id or funding stamp, a fill older than the portfolio's previous fill or than a
funding stamp already settled, a funding amount that does not match its own recomputation.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from arena.types import MICRO, QTY_SCALE, ceil_div

BP = 10_000
HOUR_S = 3600
MINUTE_S = 60
NANO_PER_MICRO = 1_000  # nano-USD per µUSD
LEAGUE = "perp"
FILL_REASONS = (
    "intent",
    "stop",
    "take_profit",
    "margin_closeout",
    "max_holding",
    "halt",
    "kill_switch",
    "no_stop",  # a deciding portfolio's position found without a stop is closed at once
    "retired",  # a council taken out of the league (`python -m arena.perp.council retire`): flat, then archived
)


class PerpLedgerError(ValueError):
    """An event sequence the ledger refuses (flip, duplicate, unknown portfolio, funding mismatch...)."""


# ---------------------------------------------------------------------- integer helpers (spec §1)


def sgn(x: int) -> int:
    return (x > 0) - (x < 0)


def notional_up(qty: int, price_uusd: int) -> int:
    return ceil_div(abs(qty) * price_uusd, QTY_SCALE)


def notional_down(qty: int, price_uusd: int) -> int:
    return abs(qty) * price_uusd // QTY_SCALE


def _check_fx(fx_bid: Any, fx_ask: Any) -> None:
    if type(fx_bid) is not int or type(fx_ask) is not int or fx_bid <= 0 or fx_ask < fx_bid:
        raise PerpLedgerError(f"inconsistent EUR/USD quote (bid={fx_bid!r}, ask={fx_ask!r})")


def cost_eur(uusd: int, fx_bid: int, fx_ask: int) -> int:
    """An amount the portfolio PAYS (>= 0 µUSD) in µEUR, rounded up, at the bid (more euros)."""
    _check_fx(fx_bid, fx_ask)
    if uusd < 0:
        raise PerpLedgerError("cost_eur of a negative amount")
    return ceil_div(uusd * MICRO, fx_bid)


def gain_eur(uusd: int, fx_bid: int, fx_ask: int) -> int:
    """An amount the portfolio RECEIVES (>= 0 µUSD) in µEUR, rounded down, at the ask (fewer euros)."""
    _check_fx(fx_bid, fx_ask)
    if uusd < 0:
        raise PerpLedgerError("gain_eur of a negative amount")
    return uusd * MICRO // fx_ask


def to_eur(uusd: int, fx_bid: int, fx_ask: int) -> int:
    """Signed amount (P&L) in µEUR: gains at the ask rounded down, losses at the bid rounded up."""
    return gain_eur(uusd, fx_bid, fx_ask) if uusd >= 0 else -cost_eur(-uusd, fx_bid, fx_ask)


def price_pnl_uusd(qty: int, entry_uusd: int, price_uusd: int) -> int:
    """P&L in µUSD of `qty` (signed) entered at `entry_uusd`, valued at `price_uusd`; rounded towards -inf."""
    return sgn(qty) * (price_uusd - entry_uusd) * abs(qty) // QTY_SCALE


def funding_amount_ueur(qty_seconds: int, rate_nusd: int, fx_bid: int, fx_ask: int) -> int:
    """Funding PAID (> 0) or received (< 0) in µEUR for `qty_seconds` (signed quantity x seconds held
    during the funding hour) at the hourly rate `rate_nusd` (spec §4)."""
    num = qty_seconds * rate_nusd
    den = QTY_SCALE * NANO_PER_MICRO * HOUR_S
    if num >= 0:
        return cost_eur(ceil_div(num, den), fx_bid, fx_ask)
    return -gain_eur((-num) // den, fx_bid, fx_ask)


def qty_seconds(history: list[tuple[int, int]], start: int, end: int) -> int:
    """Integral of the signed quantity over [start, end). `history` = [(ts, qty after the fill)], in order."""
    total, qty, cursor = 0, 0, start
    for ts, q in history:
        if ts <= start:
            qty = q
            continue
        if ts >= end:
            break
        total += qty * (ts - cursor)
        cursor, qty = ts, q
    return total + qty * (end - cursor)


# ---------------------------------------------------------------------- state


@dataclass
class PerpPosition:
    instrument: str
    qty: int  # signed: > 0 long, < 0 short
    entry_uusd: int
    opened_ts: int
    open_seq: int  # journal seq of the opening fill: identifies this position among later reopenings
    stop_uusd: int | None = None
    take_profit_uusd: int | None = None
    stop_armed_ts: int | None = None  # ts of the conditional_order that set the current stop
    take_profit_armed_ts: int | None = None


@dataclass
class MarginAccount:
    portfolio: str
    capital_ueur: int
    collateral_ueur: int
    positions: dict[str, PerpPosition] = field(default_factory=dict)
    fees_paid_ueur: int = 0
    funding_paid_ueur: int = 0
    realized_pnl_ueur: int = 0
    absorbed_deficit_ueur: int = 0
    frozen_until_ts: int = 0
    halted: bool = False
    retired_ts: int | None = None  # `portfolio_retired`: flat for good, never opens or plays again
    margin_closeouts: int = 0
    missing_funding: int = 0
    last_fill_ts: int = 0
    qty_history: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    funding_cursor: dict[str, int] = field(default_factory=dict)  # last settled stamp per instrument

    @property
    def retired(self) -> bool:
        return self.retired_ts is not None

    def invariant_ok(self) -> bool:
        expected = (
            self.capital_ueur
            + self.realized_pnl_ueur
            - self.fees_paid_ueur
            - self.funding_paid_ueur
            + self.absorbed_deficit_ueur
        )
        return self.collateral_ueur == expected and self.collateral_ueur >= 0

    def _protect_negative_balance(self) -> None:
        if self.collateral_ueur < 0:
            self.absorbed_deficit_ueur += -self.collateral_ueur
            self.collateral_ueur = 0


@dataclass(frozen=True)
class FillEffect:
    realized_ueur: int
    closed: bool


def _int(v: Any, name: str) -> int:
    if type(v) is not int:
        raise PerpLedgerError(f"{name} must be an integer, got {v!r}")
    return v


def apply_fill(acc: MarginAccount, p: Mapping[str, Any], ts: int, seq: int) -> FillEffect:
    """Applies a `perp_fill` payload to the account (spec §4). Raises on a flip or a bad value."""
    inst = p["instrument"]
    d = _int(p["qty"], "qty")
    price = _int(p["price_uusd"], "price_uusd")
    fee = _int(p["fee_ueur"], "fee_ueur")
    fx_bid, fx_ask = p["fx_bid"], p["fx_ask"]
    _check_fx(fx_bid, fx_ask)
    _int(ts, "ts")
    if d == 0 or price <= 0 or fee < 0:
        raise PerpLedgerError(f"invalid fill (qty={d}, price={price}, fee={fee})")
    if p.get("reason") not in FILL_REASONS:
        raise PerpLedgerError(f"unknown fill reason {p.get('reason')!r}")
    if ts < acc.last_fill_ts:
        raise PerpLedgerError(
            f"{acc.portfolio}: fill at {ts} is older than the previous fill ({acc.last_fill_ts})"
        )
    if ts < acc.funding_cursor.get(inst, 0):
        raise PerpLedgerError(f"{acc.portfolio} {inst}: fill at {ts} inside an hour whose funding is settled")
    pos = acc.positions.get(inst)
    realized = 0
    closed = False
    if pos is None or sgn(d) == sgn(pos.qty):
        if pos is None:
            acc.positions[inst] = PerpPosition(inst, d, price, ts, seq)
        else:
            q0, q1 = abs(pos.qty), abs(d)
            num = q0 * pos.entry_uusd + q1 * price
            pos.entry_uusd = ceil_div(num, q0 + q1) if pos.qty > 0 else num // (q0 + q1)
            pos.qty += d
    else:
        if abs(d) > abs(pos.qty):
            raise PerpLedgerError(
                f"{acc.portfolio} {inst}: a fill cannot flip a position ({pos.qty} then {d})"
            )
        realized = to_eur(price_pnl_uusd(-d, pos.entry_uusd, price), fx_bid, fx_ask)
        pos.qty += d
        if pos.qty == 0:
            del acc.positions[inst]
            closed = True
    acc.qty_history.setdefault(inst, []).append((ts, acc.positions[inst].qty if inst in acc.positions else 0))
    acc.last_fill_ts = ts
    acc.realized_pnl_ueur += realized
    acc.collateral_ueur += realized - fee
    acc.fees_paid_ueur += fee
    acc._protect_negative_balance()
    return FillEffect(realized, closed)


def _check_stamp(acc: MarginAccount, inst: str, stamp: int) -> None:
    _int(stamp, "stamp")
    if stamp % HOUR_S:
        raise PerpLedgerError(f"funding stamp {stamp} is not on an hour")
    if stamp <= acc.funding_cursor.get(inst, -1):
        raise PerpLedgerError(
            f"{acc.portfolio} {inst}: funding stamp {stamp} is not after the last settled one"
        )


def apply_funding(acc: MarginAccount, p: Mapping[str, Any]) -> int:
    """Applies a `funding` payload; recomputes quantity x time and the amount, refuses a mismatch."""
    inst, stamp = p["instrument"], p["stamp"]
    _check_stamp(acc, inst, stamp)
    qs = qty_seconds(acc.qty_history.get(inst, []), stamp - HOUR_S, stamp)
    if _int(p["qty_seconds"], "qty_seconds") != qs:
        raise PerpLedgerError(
            f"{acc.portfolio} {inst}: funding qty_seconds {p['qty_seconds']} != recomputed {qs}"
        )
    if qs == 0:
        raise PerpLedgerError(f"{acc.portfolio} {inst}: funding for an hour without any position")
    amount = funding_amount_ueur(qs, _int(p["rate_nusd"], "rate_nusd"), p["fx_bid"], p["fx_ask"])
    if _int(p["amount_ueur"], "amount_ueur") != amount:
        raise PerpLedgerError(
            f"{acc.portfolio} {inst}: funding amount {p['amount_ueur']} != recomputed {amount}"
        )
    acc.funding_cursor[inst] = stamp
    acc.collateral_ueur -= amount
    acc.funding_paid_ueur += amount
    acc._protect_negative_balance()
    return amount


def apply_missing_funding(acc: MarginAccount, p: Mapping[str, Any]) -> None:
    """An hour held with no published rate: nothing is charged, but it is counted (spec §4)."""
    inst, stamp = p["instrument"], p["stamp"]
    _check_stamp(acc, inst, stamp)
    qs = qty_seconds(acc.qty_history.get(inst, []), stamp - HOUR_S, stamp)
    if _int(p["qty_seconds"], "qty_seconds") != qs or qs == 0:
        raise PerpLedgerError(f"{acc.portfolio} {inst}: missing-funding record does not match the position")
    acc.funding_cursor[inst] = stamp
    acc.missing_funding += 1


def apply_conditional(acc: MarginAccount, p: Mapping[str, Any]) -> None:
    pos = acc.positions.get(p["instrument"])
    if pos is None:
        raise PerpLedgerError(f"{acc.portfolio}: conditional order on a missing position ({p['instrument']})")
    ts = _int(p["ts"], "ts")
    price = p.get("price_uusd")
    if price is not None and (_int(price, "price_uusd") <= 0):
        raise PerpLedgerError("conditional order price must be > 0")
    if p["kind"] == "stop":
        pos.stop_uusd, pos.stop_armed_ts = price, (ts if price is not None else None)
    elif p["kind"] == "take_profit":
        pos.take_profit_uusd, pos.take_profit_armed_ts = price, (ts if price is not None else None)
    else:
        raise PerpLedgerError(f"unknown conditional order kind {p['kind']!r}")


class PerpBook:
    """Incremental replay of the league journal: states plus the keys that must stay unique."""

    def __init__(self) -> None:
        self.states: dict[str, MarginAccount] = {}
        self.orders: dict[str, tuple[str, str, int]] = {}  # order_id -> (portfolio, instrument, qty)
        self.funding_keys: set[tuple[str, str, int]] = set()
        self.equity_keys: set[tuple[str, int]] = set()
        self.closeout_summaries: set[tuple[str, int]] = set()
        self.incomplete_minutes: set[tuple[str, int]] = set()
        self.last_seq = -1

    def account(self, name: str) -> MarginAccount:
        try:
            return self.states[name]
        except KeyError:
            raise PerpLedgerError(f"unknown portfolio (never opened): {name}") from None

    def check(self, type_: str, payload: Mapping[str, Any], ts: int) -> None:
        """Raises if `apply` would refuse this event; touches nothing (works on a copy)."""
        shadow = PerpBook()
        shadow.orders, shadow.funding_keys = self.orders, self.funding_keys
        shadow.equity_keys, shadow.closeout_summaries = self.equity_keys, self.closeout_summaries
        shadow.incomplete_minutes = self.incomplete_minutes
        name = payload.get("portfolio")
        shadow.states = dict(self.states)
        if name in self.states:
            shadow.states[name] = copy.deepcopy(self.states[name])
        shadow._dispatch(type_, payload, ts, self.last_seq + 1, dry=True)

    def apply(self, rec: Mapping[str, Any]) -> None:
        seq = rec.get("seq", self.last_seq + 1)
        if seq <= self.last_seq:
            raise PerpLedgerError(f"journal seq {seq} not after {self.last_seq}")
        self._dispatch(rec["type"], rec["payload"], rec["ts"], seq, dry=False)
        self.last_seq = seq

    def _dispatch(self, t: str, p: Mapping[str, Any], ts: int, seq: int, *, dry: bool) -> None:
        if t == "portfolio_opened":
            if p.get("league") != LEAGUE:
                raise PerpLedgerError(f"portfolio_opened outside the perp league: {p!r}")
            name = p["portfolio"]
            if name in self.states:
                raise PerpLedgerError(f"portfolio opened twice: {name}")
            cap = _int(p["capital_ueur"], "capital_ueur")
            if cap <= 0:
                raise PerpLedgerError("capital must be > 0")
            self.states[name] = MarginAccount(name, cap, cap)
        elif t == "perp_fill":
            oid = p["order_id"]
            if oid in self.orders:
                raise PerpLedgerError(f"duplicate order id {oid}")
            apply_fill(self.account(p["portfolio"]), p, ts, seq)
            if not dry:
                self.orders[oid] = (p["portfolio"], p["instrument"], p["qty"])
        elif t in ("funding", "funding_missing"):
            key = (p["portfolio"], p["instrument"], p["stamp"])
            if key in self.funding_keys:
                raise PerpLedgerError(f"funding already settled for {key}")
            acc = self.account(p["portfolio"])
            apply_funding(acc, p) if t == "funding" else apply_missing_funding(acc, p)
            if not dry:
                self.funding_keys.add(key)
        elif t == "conditional_order":
            apply_conditional(self.account(p["portfolio"]), p)
        elif t == "margin_closeout":
            key = (p["portfolio"], _int(p["minute"], "minute"))
            if key in self.closeout_summaries:
                raise PerpLedgerError(f"duplicate margin_closeout summary {key}")
            acc = self.account(p["portfolio"])
            if not dry:
                acc.margin_closeouts += 1
                self.closeout_summaries.add(key)
        elif t == "perp_equity":
            key = (p["portfolio"], _int(p["ts"], "ts"))
            if key in self.equity_keys:
                raise PerpLedgerError(f"duplicate perp_equity {key}")
            self.account(p["portfolio"])
            if not dry:
                self.equity_keys.add(key)
        elif t == "minute_incomplete":
            key = (p["portfolio"], _int(p["minute"], "minute"))
            if not dry:
                self.incomplete_minutes.add(key)
        elif t == "portfolio_frozen":
            self.account(p["portfolio"]).frozen_until_ts = _int(p["until_ts"], "until_ts")
        elif t == "portfolio_halted":
            self.account(p["portfolio"]).halted = True
        elif t == "portfolio_resumed":
            acc = self.account(p["portfolio"])
            acc.halted, acc.frozen_until_ts = False, 0
        elif t == "portfolio_retired":
            acc = self.account(p["portfolio"])
            if acc.positions:
                raise PerpLedgerError(f"{acc.portfolio}: cannot be retired with open positions")
            if acc.retired_ts is None:  # a second event keeps the first retirement date
                acc.retired_ts = _int(ts, "ts")


def replay(events: Iterable[Mapping[str, Any]]) -> dict[str, MarginAccount]:
    """Rebuilds every perp portfolio from the journal events (unknown event types are ignored)."""
    book = PerpBook()
    for rec in events:
        book.apply(rec)
    return book.states


# ---------------------------------------------------------------------- valuation (spec §5)


def _mark(marks: Mapping[str, int], inst: str) -> int:
    m = marks.get(inst)
    if type(m) is not int or m <= 0:
        raise PerpLedgerError(f"no valid mark to value {inst}")
    return m


def unrealized_ueur(acc: MarginAccount, marks: Mapping[str, int], fx_bid: int, fx_ask: int) -> int:
    """Sum of the unrealized P&L of every position, converted position by position (unfavourably)."""
    return sum(
        to_eur(price_pnl_uusd(pos.qty, pos.entry_uusd, _mark(marks, inst)), fx_bid, fx_ask)
        for inst, pos in acc.positions.items()
    )


def equity_ueur(acc: MarginAccount, marks: Mapping[str, int], fx_bid: int, fx_ask: int) -> int:
    return acc.collateral_ueur + unrealized_ueur(acc, marks, fx_bid, fx_ask)


def gross_exposure_ueur(acc: MarginAccount, marks: Mapping[str, int], fx_bid: int, fx_ask: int) -> int:
    return sum(
        cost_eur(notional_up(pos.qty, _mark(marks, inst)), fx_bid, fx_ask)
        for inst, pos in acc.positions.items()
    )
