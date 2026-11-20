"""Simulated (paper) executor: order state machine, idempotence, stops, maximum holding.

Everything goes through the journal. Write order for an entry: SUBMITTING, ACKED, `fill`, `stop_set`, FILLED.
The fill is written BEFORE the FILLED state: a crash can never leave a FILLED state without a fill. On
recovery, a fill present without stop_set or FILLED is completed; an order left in SUBMITTING/ACKED without a fill
is never resent: it goes UNKNOWN, then `resolve_unknown` cancels it (in paper trading, presumed not executed).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from arena.journal import Journal, fill_from_payload
from arena.ledger import replay
from arena.sim.fills import BP, FILL_MODEL_VERSION, market_fill, stop_fill, stop_price
from arena.types import (
    Bar,
    Fill,
    Instrument,
    Intent,
    OrderState,
    Quote,
    Side,
    VenueMode,
    Verdict,
    ceil_div,
    notional_ueur,
)

_DONE = {OrderState.FILLED, OrderState.CANCELED, OrderState.RISK_REJECTED, OrderState.UNKNOWN}
DEFAULT_CYCLE_S = 14_400
MINUTE_S = 60
STOP_WINDOW_S = 600  # window of 1-minute candles judged by a watch stop
STOP_MIN_BARS = 2  # distinct candles below the stop required


class SimExecutor:
    def __init__(
        self,
        journal: Journal,
        instruments: Mapping[str, Instrument] | Iterable[Instrument],
        fee_bp: int,
        slippage_bp: int,
        venue_mode: VenueMode = "paper",
        fault_injector: Callable[[str], bool] | None = None,
    ):
        """`fault_injector(order_id) -> True` sends the order to UNKNOWN (without a fill), for tests."""
        self.journal = journal
        self.instruments: dict[str, Instrument] = (
            dict(instruments) if isinstance(instruments, Mapping) else {i.symbol: i for i in instruments}
        )
        self.fee_bp = fee_bp
        self.slippage_bp = slippage_bp
        self.venue_mode: VenueMode = venue_mode
        self.fault_injector = fault_injector

    # ------------------------------------------------------------------ reading the journal

    def _scan(self) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
        """(successive states per order_id, fill payload per order_id)."""
        states: dict[str, list[str]] = {}
        fills: dict[str, dict[str, Any]] = {}
        for ev in self.journal.iter_events():
            p = ev["payload"]
            if ev["type"] == "order_state":
                states.setdefault(p["order_id"], []).append(p["state"])
            elif ev["type"] == "fill":
                fills[p["order_id"]] = p
        return states, fills

    def _state_of(self, order_id: str) -> list[str]:
        return self._scan()[0].get(order_id, [])

    def _log_state(self, order_id: str, state: OrderState, detail: str, now_ts: int, **extra: Any) -> None:
        self.journal.append(
            "order_state", {"order_id": order_id, "state": state.value, "detail": detail, **extra}, now_ts
        )

    # ------------------------------------------------------------------ entries

    def execute(self, intent: Intent, verdict: Verdict, quote: Quote, now_ts: int) -> Fill | None:
        """Execute an approved intent. Returns the Fill, or None (rejection, cancellation, UNKNOWN, already handled)."""
        oid = intent.intent_id
        states, fills = self._scan()
        if oid in fills:
            self._repair(intent, fills[oid], states.get(oid, []), now_ts)
            return None
        hist = states.get(oid, [])
        if any(s in {x.value for x in _DONE} for s in hist):
            return None
        if hist:  # SUBMITTING/ACKED without an outcome (crash): a second order is NEVER sent
            self._log_state(
                oid,
                OrderState.UNKNOWN,
                "recovery after interruption: outcome unknown",
                now_ts,
                portfolio=intent.portfolio,
            )
            return None
        if not verdict.approved or verdict.intent_id != oid:
            self._log_state(
                oid,
                OrderState.RISK_REJECTED,
                ",".join(verdict.reasons) or "not approved",
                now_ts,
                portfolio=intent.portfolio,
            )
            return None

        reason = self._pre_check(intent, verdict, quote)
        price = fee = 0
        if reason is None:
            inst = self.instruments[intent.symbol]
            price, fee = market_fill(intent.side, verdict.qty, quote, inst, self.fee_bp, self.slippage_bp)
            if price <= 0:
                reason = f"zero execution price ({price})"
            else:
                reason = self._funds_check(intent, verdict.qty, price, fee)
            if reason is None and intent.side == Side.BUY:
                # The execution quote may have moved since the verdict: never pay more than riskd reserved.
                total = notional_ueur(verdict.qty, price, round_up=True) + fee
                if total > verdict.reserved_ueur:
                    reason = f"execution price above riskd's reservation ({total} > {verdict.reserved_ueur})"
        if reason is not None:
            self._log_state(oid, OrderState.CANCELED, reason, now_ts, portfolio=intent.portfolio)
            return None

        self._log_state(oid, OrderState.SUBMITTING, "", now_ts, portfolio=intent.portfolio)
        if self.fault_injector is not None and self.fault_injector(oid):
            self._log_state(oid, OrderState.UNKNOWN, "injected fault", now_ts, portfolio=intent.portfolio)
            return None
        self._log_state(oid, OrderState.ACKED, "", now_ts, portfolio=intent.portfolio)
        fill = Fill(
            oid,
            intent.portfolio,
            intent.symbol,
            intent.side,
            verdict.qty,
            price,
            fee,
            now_ts,
            self.venue_mode,
            FILL_MODEL_VERSION,
            "intent",
        )
        self.journal.append("fill", fill, now_ts)
        self._repair(intent, None, [OrderState.ACKED.value], now_ts, fill)
        return fill

    def _pre_check(self, intent: Intent, verdict: Verdict, quote: Quote) -> str | None:
        inst = self.instruments.get(intent.symbol)
        if inst is None:
            return f"unknown instrument: {intent.symbol}"
        if quote.symbol != intent.symbol:
            return "quote is for another symbol"
        qty = verdict.qty
        if qty <= 0 or qty < inst.lot_min_qty:
            return f"quantity {qty} below the minimum {inst.lot_min_qty}"
        ref = quote.ask if intent.side == Side.BUY else quote.bid
        if notional_ueur(qty, ref, round_up=False) < inst.cost_min_ueur:
            return f"notional below the minimum cost {inst.cost_min_ueur}"
        return None

    def _funds_check(self, intent: Intent, qty: int, price: int, fee: int) -> str | None:
        st = replay(self.journal.iter_events()).get(intent.portfolio)
        if st is None:
            return f"unknown portfolio: {intent.portfolio}"
        if intent.side == Side.BUY:
            total = notional_ueur(qty, price, round_up=True) + fee
            if total > st.cash_ueur:
                return f"insufficient cash ({total} > {st.cash_ueur})"
        else:
            pos = st.positions.get(intent.symbol)
            if pos is None or qty > pos.qty:
                return f"sale larger than the position ({qty} > {pos.qty if pos else 0})"
        return None

    def _repair(
        self,
        intent: Intent,
        fill_payload: dict[str, Any] | None,
        hist: list[str],
        now_ts: int,
        fill: Fill | None = None,
    ) -> None:
        """Complete stop_set and the FILLED state after a fill (nominal, or recovery after a crash)."""
        if fill is None:
            assert fill_payload is not None
            fill = fill_from_payload(fill_payload)
            stops = [e for e in self.journal.iter_events() if e["type"] == "stop_set"]
            has_stop = any(
                e["payload"]["portfolio"] == fill.portfolio
                and e["payload"]["symbol"] == fill.symbol
                and e["ts"] >= fill.ts
                for e in stops
            )
        else:
            has_stop = False
        if fill.side == Side.BUY and intent.stop_bp is not None and not has_stop and self._holds(fill):
            stop = stop_price(fill.price_ueur, intent.stop_bp, self.instruments[fill.symbol])
            # A second buy must never loosen the stop of the lots already held (25% stop on a further 1%).
            stop = max(stop, self._current_stop(fill))
            self.journal.append(
                "stop_set", {"portfolio": fill.portfolio, "symbol": fill.symbol, "stop_ueur": stop}, fill.ts
            )
        if OrderState.FILLED.value not in hist:
            self._log_state(fill.order_id, OrderState.FILLED, "", now_ts, portfolio=fill.portfolio)

    def _holds(self, fill: Fill) -> bool:
        """True if the portfolio still holds the symbol: a stop_set on a position closed in the meantime
        (flatten during crash recovery) would make `replay` raise forever."""
        st = replay(self.journal.iter_events()).get(fill.portfolio)
        return st is not None and fill.symbol in st.positions

    def _current_stop(self, fill: Fill) -> int:
        """Stop already set on the position before this fill (0 if none)."""
        st = replay(self.journal.iter_events()).get(fill.portfolio)
        pos = st.positions.get(fill.symbol) if st else None
        return pos.stop_ueur or 0 if pos else 0

    # ------------------------------------------------------------------ UNKNOWN

    def resolve_unknown(self, order_id: str, now_ts: int) -> bool:
        """Paper: an UNKNOWN order is presumed not executed and goes to CANCELED. Returns True if canceled."""
        hist = self._state_of(order_id)
        if not hist or hist[-1] != OrderState.UNKNOWN.value:
            return False
        self._log_state(order_id, OrderState.CANCELED, "UNKNOWN resolved: presumed not executed (paper)", now_ts)
        return True

    def unknown_age_cycles(self, portfolio: str, now_ts: int, cycle_s: int = DEFAULT_CYCLE_S) -> int:
        """Age in cycles of the portfolio's oldest unresolved UNKNOWN order (0 if none).

        The cycle freezes the portfolio if this number exceeds 2.
        """
        owner: dict[str, str] = {}
        since: dict[str, int] = {}
        for ev in self.journal.iter_events():
            p = ev["payload"]
            if ev["type"] != "order_state":
                continue
            oid = p["order_id"]
            if "portfolio" in p:
                owner[oid] = p["portfolio"]
            if p["state"] == OrderState.UNKNOWN.value:
                since.setdefault(oid, ev["ts"])
            else:
                since.pop(oid, None)
        return max(
            ((now_ts - ts) // cycle_s for oid, ts in since.items() if owner.get(oid) == portfolio), default=0
        )

    # ------------------------------------------------------------------ forced exits

    def _forced_sell(
        self,
        order_id: str,
        portfolio: str,
        symbol: str,
        qty: int,
        price: int,
        fee: int,
        now_ts: int,
        reason: str,
    ) -> Fill:
        if price <= 0 or qty <= 0:  # never a zero fill in the journal (the ledger would refuse it forever)
            raise ValueError(f"invalid fill refused before writing ({order_id}: qty={qty}, price={price})")
        fill = Fill(
            order_id,
            portfolio,
            symbol,
            Side.SELL,
            qty,
            price,
            fee,
            now_ts,
            self.venue_mode,
            FILL_MODEL_VERSION,
            reason,
        )
        self.journal.append("fill", fill, now_ts)
        self._log_state(order_id, OrderState.FILLED, reason, now_ts, portfolio=portfolio)
        return fill

    def process_stops_and_expiry(
        self,
        bars_since_last_cycle: Mapping[str, list[Bar]],
        quotes: Mapping[str, Quote],
        now_ts: int,
        max_holding_s: int,
    ) -> list[Fill]:
        """Stops bar by bar (chronological order), then maximum holding. Idempotent."""
        out: list[Fill] = []
        _, done_fills = self._scan()
        done = set(done_fills)
        for pname, st in sorted(replay(self.journal.iter_events()).items()):
            for sym, pos in sorted(st.positions.items()):
                inst = self.instruments.get(sym)
                if inst is None:
                    continue
                sold = False
                if pos.stop_ueur is not None:
                    for bar in sorted(bars_since_last_cycle.get(sym, []), key=lambda b: b.ts):
                        if bar.ts < pos.opened_ts:
                            continue  # bar started before the entry
                        px = stop_fill(pos.stop_ueur, bar, inst, self.slippage_bp)
                        if px is None or px <= 0:
                            continue
                        oid = f"stop:{pname}:{sym}:{bar.ts}"
                        if oid in done:
                            break
                        _, fee = market_fill(
                            Side.SELL, pos.qty, Quote(sym, bar.ts, px, px), inst, self.fee_bp, 0
                        )
                        out.append(self._forced_sell(oid, pname, sym, pos.qty, px, fee, now_ts, "stop"))
                        done.add(oid)
                        sold = True
                        break
                if sold or now_ts - pos.opened_ts < max_holding_s:
                    continue
                q = quotes.get(sym)
                oid = f"exit:{pname}:{sym}:{pos.opened_ts}:max_holding"
                if q is None or oid in done:
                    continue
                px, fee = market_fill(Side.SELL, pos.qty, q, inst, self.fee_bp, self.slippage_bp)
                if px <= 0:
                    continue
                out.append(self._forced_sell(oid, pname, sym, pos.qty, px, fee, now_ts, "max_holding"))
                done.add(oid)
        return out

    def process_live_stops(
        self, minute_bars: Mapping[str, list[Bar]], tick: int, ticker_bids: Mapping[str, int] | None = None
    ) -> list[Fill]:
        """Live stops of the watch, judged on TRADES (closed 1-minute Kraken candles).

        A position is sold if, among the closed candles WITH VOLUME > 0 since `max(tick - 600, actual
        execution time of the buy)`, at least 2 distinct candles have a low <= stop (a single filler or
        outlier candle is not enough: wait for the next tick). The actual execution time is the `ts` of the last
        `quote` or `wakeup_quote` event of the symbol that precedes the opening fill (otherwise, `opened_ts`).
        Price: `min(stop, max(1-minute close x (1 - slippage), raw ticker bid x (1 - slippage)))`, rounded down to the
        tick, with taker fees: a single faulty feed gives at worst a sale at the stop; without a readable
        ticker, the 1-minute close alone. `order_id` = stop:{portfolio}:{symbol}:watch:{tick}, idempotent. A symbol
        missing from `minute_bars` has no stop on that tick. A computed price of zero or less is ignored."""
        out: list[Fill] = []
        last_quote: dict[str, int] = {}
        held: dict[tuple[str, str], int] = {}
        opened_exec_ts: dict[tuple[str, str], int] = {}
        done_fills: set[str] = set()
        for ev in self.journal.iter_events():
            t, p = ev["type"], ev["payload"]
            if t in ("quote", "wakeup_quote"):
                last_quote[p["symbol"]] = ev["ts"]
            elif t == "fill":
                done_fills.add(p["order_id"])
                key = (p["portfolio"], p["symbol"])
                if p["side"] == "buy":
                    if held.get(key, 0) == 0:
                        opened_exec_ts[key] = last_quote.get(p["symbol"], p["ts"])
                    held[key] = held.get(key, 0) + p["qty"]
                else:
                    held[key] = held.get(key, 0) - p["qty"]
        for pname, st in sorted(replay(self.journal.iter_events()).items()):
            for sym, pos in sorted(st.positions.items()):
                inst, bars = self.instruments.get(sym), minute_bars.get(sym)
                if inst is None or not bars or pos.stop_ueur is None:
                    continue
                closed = sorted((b for b in bars if b.ts + MINUTE_S <= tick), key=lambda b: b.ts)
                if not closed:
                    continue
                since = max(tick - STOP_WINDOW_S, opened_exec_ts.get((pname, sym), pos.opened_ts))
                hits = {b.ts for b in closed if b.volume > 0 and b.ts >= since and b.low <= pos.stop_ueur}
                if len(hits) < STOP_MIN_BARS:
                    continue
                oid = f"stop:{pname}:{sym}:watch:{tick}"
                if oid in done_fills:
                    continue
                sources = [closed[-1].close]
                if ticker_bids and ticker_bids.get(sym):
                    sources.append(ticker_bids[sym])
                px = min(
                    pos.stop_ueur,
                    max(market_fill(Side.SELL, pos.qty, Quote(sym, tick, c, c), inst, self.fee_bp, self.slippage_bp)[0] for c in sources),
                )
                if px <= 0:
                    continue
                fee = ceil_div(notional_ueur(pos.qty, px, round_up=True) * self.fee_bp, BP)
                out.append(self._forced_sell(oid, pname, sym, pos.qty, px, fee, tick, "stop"))
        return out

    def reject(self, intent: Intent, reason: str, now_ts: int) -> None:
        """Order refused before sending (e.g. NO_QUOTE): state RISK_REJECTED, only once (idempotent)."""
        if not self._state_of(intent.intent_id):
            self._log_state(intent.intent_id, OrderState.RISK_REJECTED, reason, now_ts, portfolio=intent.portfolio)

    def settle_interrupted(self, intent: Intent, now_ts: int) -> None:
        """Repair an order interrupted by a crash before abandoning its round: a fill without `stop_set` gets its
        stop (from the intent) and its FILLED state; an order left SUBMITTING/ACKED without a fill goes UNKNOWN then
        CANCELED (paper: presumed not executed). Never sends an order."""
        oid = intent.intent_id
        states, fills = self._scan()
        hist = states.get(oid, [])
        if oid in fills:
            self._repair(intent, fills[oid], hist, now_ts)
        elif hist and hist[-1] in (OrderState.SUBMITTING.value, OrderState.ACKED.value):
            self._log_state(oid, OrderState.UNKNOWN, "round abandoned: outcome unknown", now_ts, portfolio=intent.portfolio)
            self.resolve_unknown(oid, now_ts)
        elif hist and hist[-1] == OrderState.UNKNOWN.value:
            self.resolve_unknown(oid, now_ts)

    def flatten(self, portfolio: str, quotes: Mapping[str, Quote], now_ts: int, reason: str) -> list[Fill]:
        """Sell all positions at the bid (reason: "kill_switch" or "halt"). Idempotent per (now_ts, reason)."""
        st = replay(self.journal.iter_events()).get(portfolio)
        if st is None:
            return []
        _, done_fills = self._scan()
        out: list[Fill] = []
        for sym, pos in sorted(st.positions.items()):
            q, inst = quotes.get(sym), self.instruments.get(sym)
            oid = f"exit:{portfolio}:{sym}:{now_ts}:{reason}"
            if q is None or inst is None or oid in done_fills:
                continue
            px, fee = market_fill(Side.SELL, pos.qty, q, inst, self.fee_bp, self.slippage_bp)
            if px <= 0:
                continue
            out.append(self._forced_sell(oid, portfolio, sym, pos.qty, px, fee, now_ts, reason))
        return out
