"""Simulated execution of the perp league (`pessimiste-perp-v1`, docs/SPEC-PERP-LEDGER.md §5).

The simulator only WRITES journal events; the state is the ledger replayed from the journal
(`PerpBook`, kept in memory and refreshed from the journal when another process wrote to it). Every event
is validated by the ledger on a copy BEFORE it is written, so nothing the ledger would refuse ever reaches
the journal. Writes are serialised by an exclusive lock and are idempotent: order ids carry the identity of
the position (`open_seq`) and the minute, funding is keyed by (portfolio, instrument, stamp).
"""

from __future__ import annotations

import copy
import fcntl
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from arene.journal import Journal
from arene.perp.ledger import (
    BP,
    HOUR_S,
    LEAGUE,
    MINUTE_S,
    MarginAccount,
    PerpBook,
    PerpLedgerError,
    apply_fill,
    cost_eur,
    equity_ueur,
    funding_amount_ueur,
    gross_exposure_ueur,
    notional_up,
    qty_seconds,
    unrealized_ueur,
)
from arene.perp.margin import INITIAL, MAINTENANCE, leveraged, margin_ueur
from arene.perp.types import MarginLevel
from arene.types import ceil_div

FILL_MODEL_VERSION = "pessimiste-perp-v1"

# One closed minute of an instrument: (open, high, low, close) in µUSD.
Ohlc = tuple[int, int, int, int]


@dataclass(frozen=True)
class SimParams:
    taker_fee_bp: int = 7
    slippage_bp: int = 5
    liquidation_fee_bp: int = 500
    closeout_margin_bp: int = 2500
    initial_margin_bp: int = 5000
    max_holding_s: int = 604_800
    capital_ueur: int = 1_000_000_000

    def __post_init__(self) -> None:
        for name in (
            "taker_fee_bp",
            "slippage_bp",
            "liquidation_fee_bp",
            "closeout_margin_bp",
            "initial_margin_bp",
            "max_holding_s",
        ):
            v = getattr(self, name)
            if type(v) is not int or v < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if type(self.capital_ueur) is not int or self.capital_ueur <= 0:
            raise ValueError("capital_ueur must be a positive integer")
        if not 0 < self.closeout_margin_bp <= self.initial_margin_bp <= BP:
            raise ValueError("need 0 < closeout_margin_bp <= initial_margin_bp <= 10000")


@dataclass(frozen=True)
class MinuteCandles:
    """The closed minute of one instrument: mark candle (required) and trade candle (may be missing)."""

    mark: Ohlc
    trade: Ohlc | None = None


def tick_up(p: int, tick: int) -> int:
    return ceil_div(p, tick) * tick


def tick_down(p: int, tick: int) -> int:
    return p // tick * tick


def buy_price(ask: int, slippage_bp: int, tick: int) -> int:
    return tick_up(ceil_div(ask * (BP + slippage_bp), BP), tick)


def sell_price(bid: int, slippage_bp: int, tick: int) -> int:
    return tick_down(bid * (BP - slippage_bp) // BP, tick)


def fee_ueur(qty: int, price_uusd: int, fee_bp: int, fx_bid: int, fx_ask: int) -> int:
    return cost_eur(ceil_div(notional_up(qty, price_uusd) * fee_bp, BP), fx_bid, fx_ask)


def _fx(fx: tuple[int, int]) -> tuple[int, int]:
    if len(fx) != 2 or any(type(x) is not int for x in fx) or fx[0] <= 0 or fx[1] < fx[0]:
        raise PerpLedgerError(f"incoherent EUR/USD quote {fx!r}")
    return fx[0], fx[1]


class PerpSimulator:
    def __init__(
        self,
        journal: Journal,
        ticks: Mapping[str, int],
        params: SimParams | None = None,
        *,
        exclusive: bool = False,
        margin_levels: Mapping[str, tuple[MarginLevel, ...]] | None = None,
    ) -> None:
        """`exclusive=True`: the caller guarantees no other writer (offline replays): no lock, no re-sync.

        `margin_levels`: Kraken's margin schedule per instrument, for the leveraged portfolios
        (`arene/perp/margin.py`): their entries need Kraken's initial margin and their close-out comes when the
        equity falls under Kraken's maintenance margin. Without it, a leveraged portfolio is margined at 100 %."""
        for inst, tick in ticks.items():
            if type(tick) is not int or tick <= 0:
                raise ValueError(f"tick of {inst} must be a positive integer")
        self.journal = journal
        self.ticks = dict(ticks)
        self.params = params or SimParams()
        self._book = PerpBook()
        self._lock_depth = 0
        self._lock_fd: int | None = None
        self.exclusive = exclusive
        self._synced = False
        self.margin_levels = dict(margin_levels or {})

    # ------------------------------------------------------------------ journal, lock, cache

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """One writer at a time (re-entrant within this object): the check-then-append is atomic."""
        if self.exclusive:
            if not self._synced:
                self._sync()
                self._synced = True
            yield
            return
        if self._lock_depth == 0:
            self.journal.path.parent.mkdir(parents=True, exist_ok=True)
            self._lock_fd = os.open(f"{self.journal.path}.sim.lock", os.O_CREAT | os.O_RDWR, 0o644)
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX)
        self._lock_depth += 1
        try:
            self._sync()
            yield
        finally:
            self._lock_depth -= 1
            if self._lock_depth == 0 and self._lock_fd is not None:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
                self._lock_fd = None

    def _sync(self) -> None:
        """Reloads the book only when the journal head moved (another process wrote)."""
        last = self.journal.last()
        head = -1 if last is None else last["seq"]
        if head == self._book.last_seq:
            return
        book = PerpBook()
        for rec in self.journal.iter_events():
            book.apply(rec)
        self._book = book

    def _append(self, type_: str, payload: dict[str, Any], ts: int) -> dict[str, Any]:
        self._book.check(type_, payload, ts)  # the ledger refuses BEFORE anything is written
        rec = self.journal.append(type_, payload, ts)
        self._book.apply(rec)
        return payload

    def append_event(self, type_: str, payload: dict[str, Any], ts: int) -> dict[str, Any]:
        """Appends an event the ledger does not own (rounds, verdicts, alerts...) through the simulator, so
        its in-memory book stays in step with the journal head (no full re-read at the next call)."""
        with self._locked():
            return self._append(type_, payload, ts)

    def states(self) -> dict[str, MarginAccount]:
        with self._locked():
            return copy.deepcopy(self._book.states)

    def _tick(self, inst: str) -> int:
        try:
            return self.ticks[inst]
        except KeyError:
            raise PerpLedgerError(f"unknown instrument {inst}") from None

    # ------------------------------------------------------------------ portfolios and orders

    def open_portfolio(self, portfolio: str, kind: str, ts: int) -> bool:
        with self._locked():
            if portfolio in self._book.states:
                return False
            payload = {
                "portfolio": portfolio,
                "kind": kind,
                "league": LEAGUE,
                "capital_ueur": self.params.capital_ueur,
                "venue_mode": "paper",
            }
            self._append("portfolio_opened", payload, ts)
            return True

    def _fill(
        self,
        name: str,
        oid: str,
        inst: str,
        qty: int,
        price: int,
        fee: int,
        fx: tuple[int, int],
        ts: int,
        reason: str,
    ) -> dict[str, Any]:
        payload = {
            "order_id": oid,
            "portfolio": name,
            "instrument": inst,
            "qty": qty,
            "price_uusd": price,
            "fee_ueur": fee,
            "fx_bid": fx[0],
            "fx_ask": fx[1],
            "reason": reason,
            "fill_model_version": FILL_MODEL_VERSION,
            "ts": ts,
        }
        return self._append("perp_fill", payload, ts)

    def market_order(
        self,
        order_id: str,
        portfolio: str,
        instrument: str,
        qty: int,
        quote: tuple[int, int],
        fx: tuple[int, int],
        ts: int,
        reason: str = "intent",
        *,
        marks: Mapping[str, int] | None = None,
        extra_slippage_bp: int = 0,
    ) -> dict[str, Any] | None:
        """Fills `qty` (signed) at market on `quote` = (bid, ask).

        Returns the fill, or None if `order_id` was already filled with the same portfolio, instrument and
        quantity (a different request under an existing id raises). An `intent` that opens or increases a
        position is refused when the portfolio is halted, frozen or without collateral, and when the
        initial margin (`initial_margin_bp` of the gross exposure, the AMF 50 % rule) is not covered after
        the trade; `marks` values the other held instruments (the traded one is valued at the quote mid).
        """
        if type(qty) is not int or qty == 0:
            raise PerpLedgerError("qty must be a non-zero integer")
        fx = _fx(fx)
        with self._locked():
            done = self._book.orders.get(order_id)
            if done is not None:
                if done != (portfolio, instrument, qty):
                    raise PerpLedgerError(f"order id {order_id} already used for {done}")
                return None
            bid, ask = quote
            if type(bid) is not int or type(ask) is not int or bid <= 0 or ask < bid:
                raise PerpLedgerError(f"incoherent quote {quote}")
            acc = self._book.account(portfolio)
            tick = self._tick(instrument)
            slip = self.params.slippage_bp + extra_slippage_bp
            price = buy_price(ask, slip, tick) if qty > 0 else sell_price(bid, slip, tick)
            fee = fee_ueur(qty, price, self.params.taker_fee_bp, *fx)
            pos = acc.positions.get(instrument)
            increases = pos is None or (qty > 0) == (pos.qty > 0)
            if reason == "intent" and increases:
                self._check_entry(acc, instrument, qty, price, fee, (bid + ask) // 2, marks, fx, ts)
            return self._fill(portfolio, order_id, instrument, qty, price, fee, fx, ts, reason)

    def _check_entry(
        self,
        acc: MarginAccount,
        inst: str,
        qty: int,
        price: int,
        fee: int,
        mid: int,
        marks: Mapping[str, int] | None,
        fx: tuple[int, int],
        ts: int,
    ) -> None:
        if acc.halted:
            raise PerpLedgerError(f"{acc.portfolio} is halted: no entry")
        if ts < acc.frozen_until_ts:
            raise PerpLedgerError(f"{acc.portfolio} is frozen until {acc.frozen_until_ts}: no entry")
        if acc.collateral_ueur <= 0:
            raise PerpLedgerError(f"{acc.portfolio} has no collateral: no entry")
        values = dict(marks or {})
        values[inst] = mid
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
        apply_fill(after, probe, ts, self._book.last_seq + 1)
        equity = equity_ueur(after, values, *fx)
        gross = gross_exposure_ueur(after, values, *fx)
        if leveraged(acc.portfolio):
            need = self._kraken_margin(after, values, INITIAL, fx)
            if equity < need:
                raise PerpLedgerError(
                    f"{acc.portfolio}: Kraken initial margin not covered after the order "
                    f"(equity {equity} µEUR, {need} µEUR required)"
                )
        elif equity * BP < self.params.initial_margin_bp * gross:
            raise PerpLedgerError(
                f"{acc.portfolio}: initial margin not covered after the order "
                f"(equity {equity} µEUR, gross {gross} µEUR, {self.params.initial_margin_bp} bp required)"
            )

    def _kraken_margin(
        self, acc: MarginAccount, values: Mapping[str, int], kind: str, fx: tuple[int, int]
    ) -> int:
        notionals = {i: notional_up(p.qty, values[i]) for i, p in acc.positions.items()}
        return margin_ueur(notionals, {i: self.margin_levels.get(i, ()) for i in notionals}, kind, *fx)

    def set_conditional(
        self, portfolio: str, instrument: str, kind: str, price_uusd: int | None, ts: int
    ) -> None:
        with self._locked():
            payload = {
                "portfolio": portfolio,
                "instrument": instrument,
                "kind": kind,
                "price_uusd": price_uusd,
                "ts": ts,
            }
            self._append("conditional_order", payload, ts)

    # ------------------------------------------------------------------ funding

    def settle_funding(self, instrument: str, stamp: int, rate_nusd: int, fx: tuple[int, int]) -> list[dict]:
        """Settles the rate stamped `stamp` (it pays [stamp - 1 h, stamp)) for every portfolio that held
        `instrument` during that hour, pro rata to quantity x time (spec §4)."""
        if type(rate_nusd) is not int:
            raise PerpLedgerError("rate_nusd must be an integer")
        fx = _fx(fx)
        out = []
        with self._locked():
            for name, acc in sorted(self._book.states.items()):
                qs = qty_seconds(acc.qty_history.get(instrument, []), stamp - HOUR_S, stamp)
                if qs == 0 or (name, instrument, stamp) in self._book.funding_keys:
                    continue
                payload = {
                    "portfolio": name,
                    "instrument": instrument,
                    "stamp": stamp,
                    "qty_seconds": qs,
                    "rate_nusd": rate_nusd,
                    "fx_bid": fx[0],
                    "fx_ask": fx[1],
                    "amount_ueur": funding_amount_ueur(qs, rate_nusd, *fx),
                }
                out.append(self._append("funding", payload, stamp))
        return out

    def record_missing_funding(self, instrument: str, stamp: int) -> list[dict]:
        """An hour whose rate Kraken never published: nothing is charged, but it is recorded (spec §4)."""
        out = []
        with self._locked():
            for name, acc in sorted(self._book.states.items()):
                qs = qty_seconds(acc.qty_history.get(instrument, []), stamp - HOUR_S, stamp)
                if qs == 0 or (name, instrument, stamp) in self._book.funding_keys:
                    continue
                payload = {"portfolio": name, "instrument": instrument, "stamp": stamp, "qty_seconds": qs}
                out.append(self._append("funding_missing", payload, stamp))
        return out

    # ------------------------------------------------------------------ one closed minute

    def process_minute(
        self,
        minute_ts: int,
        candles: Mapping[str, MinuteCandles],
        fx: tuple[int, int],
        *,
        fallback_marks: Mapping[str, int] | None = None,
        exit_slippage_bp: Mapping[str, int] | None = None,
    ) -> tuple[list[dict], list[str]]:
        """Margin close-out, then stops, then take-profits, for every portfolio (spec §5).

        A held instrument without a candle for this minute: a `minute_incomplete` event is written, its
        stop and take-profit are not evaluated, and the close-out test values it at `fallback_marks` (its
        last known mark) or, without one, is not run for that portfolio (reported as a problem). One
        portfolio's failure never stops the others: it is reported in `problems`.
        """
        if type(minute_ts) is not int or minute_ts % MINUTE_S:
            raise PerpLedgerError(f"minute {minute_ts} is not on a minute")
        fx = _fx(fx)
        fills: list[dict] = []
        problems: list[str] = []
        extra = dict(exit_slippage_bp or {})
        with self._locked():
            for name in sorted(self._book.states):
                try:
                    self._minute_for(
                        name, minute_ts, candles, fx, fallback_marks or {}, extra, fills, problems
                    )
                except PerpLedgerError as exc:
                    problems.append(f"{name} minute {minute_ts}: {exc}")
        return fills, problems

    def _minute_for(
        self,
        name: str,
        minute_ts: int,
        candles: Mapping[str, MinuteCandles],
        fx: tuple[int, int],
        fallback: Mapping[str, int],
        extra: Mapping[str, int],
        fills: list[dict],
        problems: list[str],
    ) -> None:
        acc = self._book.states[name]
        fill_ts = max(minute_ts + MINUTE_S - 1, acc.last_fill_ts)  # fills of a minute are stamped at its end
        if self._closeout_started(name, minute_ts):
            self._finish_closeout(name, minute_ts, candles, fallback, fx, extra, fills, fill_ts, None)
            return
        if not acc.positions:
            return
        missing = sorted(i for i in acc.positions if i not in candles)
        if missing and (name, minute_ts) not in self._book.incomplete_minutes:
            self._append(
                "minute_incomplete",
                {"portfolio": name, "minute": minute_ts, "instruments": missing},
                minute_ts,
            )
        worst: dict[str, int] = {}
        for inst, pos in acc.positions.items():
            if inst in candles:
                worst[inst] = candles[inst].mark[2] if pos.qty > 0 else candles[inst].mark[1]
            elif inst in fallback:
                worst[inst] = fallback[inst]
        if len(worst) < len(acc.positions):
            problems.append(f"{name} minute {minute_ts}: close-out not tested, no mark for {missing}")
        else:
            equity = equity_ueur(acc, worst, *fx)
            gross = gross_exposure_ueur(acc, worst, *fx)
            threshold = (
                self._kraken_margin(acc, worst, MAINTENANCE, fx)
                if leveraged(name)
                else ceil_div(self.params.closeout_margin_bp * gross, BP)
            )
            if equity < threshold:
                summary = {"equity_ueur": equity, "threshold_ueur": threshold, "gross_ueur": gross}
                self._finish_closeout(name, minute_ts, candles, fallback, fx, extra, fills, fill_ts, summary)
                return
        for inst in sorted(acc.positions):
            if inst not in candles:
                continue
            pos = acc.positions[inst]
            c = candles[inst]
            tick = self._tick(inst)
            slip = self.params.slippage_bp + extra.get(inst, 0)
            # Stop: pessimistic, it also applies to the minute in which the position or the stop appeared.
            armed = pos.stop_armed_ts
            if pos.stop_uusd is not None and armed is not None and armed < minute_ts + MINUTE_S:
                s = pos.stop_uusd
                price: int | None = None
                if pos.qty > 0 and c.mark[2] <= s:
                    price = sell_price(min(s, c.trade[0] if c.trade else c.mark[0]), slip, tick)
                elif pos.qty < 0 and c.mark[1] >= s:
                    price = buy_price(max(s, c.trade[0] if c.trade else c.mark[0]), slip, tick)
                if price is not None:
                    if price <= 0:
                        price = tick  # a sell can never fill at zero: one tick, and reported
                        problems.append(
                            f"{name} {inst} minute {minute_ts}: stop priced at zero, set to one tick"
                        )
                    oid = f"stop:{name}:{inst}:{pos.open_seq}:{minute_ts}"
                    fee = fee_ueur(pos.qty, price, self.params.taker_fee_bp, *fx)
                    fills.append(self._fill(name, oid, inst, -pos.qty, price, fee, fx, fill_ts, "stop"))
                    continue
            # Take-profit: only once both the position and the order existed for the whole minute.
            t = pos.take_profit_uusd
            tp_armed = pos.take_profit_armed_ts
            if (
                t is not None
                and tp_armed is not None
                and c.trade is not None
                and max(tp_armed, pos.opened_ts) <= minute_ts
            ):
                hit = c.trade[1] >= t + tick if pos.qty > 0 else c.trade[2] <= t - tick
                if hit:
                    oid = f"take_profit:{name}:{inst}:{pos.open_seq}:{minute_ts}"
                    fee = fee_ueur(pos.qty, t, self.params.taker_fee_bp, *fx)
                    fills.append(self._fill(name, oid, inst, -pos.qty, t, fee, fx, fill_ts, "take_profit"))

    def _closeout_ids(self, name: str, minute_ts: int) -> list[str]:
        prefix, suffix = f"margin_closeout:{name}:", f":{minute_ts}"
        return sorted(oid for oid in self._book.orders if oid.startswith(prefix) and oid.endswith(suffix))

    def _closeout_started(self, name: str, minute_ts: int) -> bool:
        return (
            bool(self._closeout_ids(name, minute_ts))
            and (name, minute_ts) not in self._book.closeout_summaries
        )

    def _finish_closeout(
        self,
        name: str,
        minute_ts: int,
        candles: Mapping[str, MinuteCandles],
        fallback: Mapping[str, int],
        fx: tuple[int, int],
        extra: Mapping[str, int],
        fills: list[dict],
        fill_ts: int,
        summary: dict[str, int] | None,
    ) -> None:
        """Closes EVERY remaining position, then writes the summary. A re-run after a crash finishes the
        close-out it finds started, without re-testing the margin (the decision is durable)."""
        acc = self._book.states[name]
        for inst in sorted(acc.positions):
            pos = acc.positions[inst]
            tick = self._tick(inst)
            slip = self.params.slippage_bp + extra.get(inst, 0)
            if inst in candles:
                m = candles[inst].mark
                price = sell_price(m[2], slip, tick) if pos.qty > 0 else buy_price(m[1], slip, tick)
            elif inst in fallback:
                f = fallback[inst]
                price = sell_price(f, slip, tick) if pos.qty > 0 else buy_price(f, slip, tick)
            else:
                raise PerpLedgerError(f"close-out of {inst} impossible: no mark for minute {minute_ts}")
            price = max(price, tick)
            oid = f"margin_closeout:{name}:{inst}:{pos.open_seq}:{minute_ts}"
            fee = fee_ueur(pos.qty, price, self.params.taker_fee_bp + self.params.liquidation_fee_bp, *fx)
            fills.append(self._fill(name, oid, inst, -pos.qty, price, fee, fx, fill_ts, "margin_closeout"))
        if (name, minute_ts) in self._book.closeout_summaries:
            return
        payload = {
            "portfolio": name,
            "minute": minute_ts,
            "equity_ueur": summary["equity_ueur"] if summary else None,
            "threshold_ueur": summary["threshold_ueur"] if summary else None,
            "gross_ueur": summary["gross_ueur"] if summary else None,
            "order_ids": self._closeout_ids(name, minute_ts),
            "resumed_after_crash": summary is None,
        }
        self._append("margin_closeout", payload, fill_ts)

    # ------------------------------------------------------------------ forced exits and measures

    def close_expired(
        self,
        ts: int,
        quotes: Mapping[str, tuple[int, int]],
        fx: tuple[int, int],
        portfolios: set[str] | None = None,
    ) -> list[dict]:
        """Closes, at market, every position held for `max_holding_s` or more (reason max_holding), for the
        given portfolios (all when None)."""
        out = []
        with self._locked():
            for name, acc in sorted(self._book.states.items()):
                if portfolios is not None and name not in portfolios:
                    continue
                for inst, pos in sorted(acc.positions.items()):
                    if ts - pos.opened_ts < self.params.max_holding_s or inst not in quotes:
                        continue
                    oid = f"max_holding:{name}:{inst}:{pos.open_seq}"
                    fill = self.market_order(oid, name, inst, -pos.qty, quotes[inst], fx, ts, "max_holding")
                    if fill:
                        out.append(fill)
        return out

    def flatten(
        self, portfolio: str, ts: int, quotes: Mapping[str, tuple[int, int]], fx: tuple[int, int], reason: str
    ) -> list[dict]:
        """Closes every position of `portfolio` at market (reason `halt` or `kill_switch`). A position without
        a quote raises: a silent no-op would leave a halted portfolio exposed."""
        if reason not in ("halt", "kill_switch"):
            raise PerpLedgerError(f"flatten reason must be halt or kill_switch, got {reason!r}")
        out = []
        with self._locked():
            acc = self._book.account(portfolio)
            missing = sorted(i for i in acc.positions if i not in quotes)
            if missing:
                raise PerpLedgerError(f"{portfolio}: cannot flatten without a quote for {missing}")
            for inst, pos in sorted(acc.positions.items()):
                oid = f"{reason}:{portfolio}:{inst}:{pos.open_seq}"
                fill = self.market_order(oid, portfolio, inst, -pos.qty, quotes[inst], fx, ts, reason)
                if fill:
                    out.append(fill)
        return out

    def write_equity(
        self, portfolio: str, ts: int, marks: Mapping[str, int], fx: tuple[int, int]
    ) -> dict[str, Any] | None:
        """Writes one `perp_equity` measure; None if one already exists for (portfolio, ts)."""
        fx = _fx(fx)
        with self._locked():
            if (portfolio, ts) in self._book.equity_keys:
                return None
            acc = self._book.account(portfolio)
            held = {i: marks.get(i) for i in acc.positions}
            payload = {
                "portfolio": portfolio,
                "ts": ts,
                "collateral_ueur": acc.collateral_ueur,
                "unrealized_ueur": unrealized_ueur(acc, held, *fx),
                "equity_ueur": equity_ueur(acc, held, *fx),
                "gross_ueur": gross_exposure_ueur(acc, held, *fx),
                "marks": dict(sorted(held.items())),
                "fx_bid": fx[0],
                "fx_ask": fx[1],
            }
            return self._append("perp_equity", payload, ts)
