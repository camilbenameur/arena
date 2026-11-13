"""Watcher of the perp league (step 4, docs/ETUDE-AGENTS-TRADERS.md §2.5 and §4.3). No LLM.

Run every 5 minutes by `arene-perp-watcher.timer`, after the collector. One tick:

1. locks: its own, and the collector's (a collection in progress defers the tick); tick id = now // 300 * 300,
   done once (`perp_tick`);
2. the benchmark portfolios are opened at the first tick; the LLM portfolios (config/perp-llm.toml) at their
   first round, all four at the same rendez-vous;
3. closed minutes are processed IN ORDER, as far as the collector has stored them: margin close-out, stops,
   take-profits, with the worst half-spread of the last 7 days as extra exit slippage. The cursor never
   passes a minute that a held instrument still lacks (candle or EUR/USD) unless that minute is older than
   `MINUTE_PATIENCE_S` (then it is processed with the last known marks and recorded as incomplete). Long
   catch-ups write checkpoints; they are capped at 7 days (older holes are reported);
4. hourly funding: each stamp is settled when Kraken has published it and EUR/USD is known; recorded as
   missing when the rate is still absent 3 hours later; otherwise kept pending, in order;
5. the market view must be fresh (`VIEW_MAX_AGE_S`); otherwise no equity, no control, no round, and an alert
   (except the kill switch and dormance, which flatten with the last known quotes);
6. every portfolio: `perp_equity`; the deciding portfolios (the random benchmark, the LLMs later): halt
   (drawdown >= 15 %: flatten and `portfolio_halted`), freeze (loss >= 5 % over 24 h, not re-armed by the same
   loss), maximum holding; the reference benchmarks are never stopped, frozen nor expired. Every margin
   close-out freezes its portfolio and raises a `panique` alert (idempotently, even after a crash);
7. rounds: the 4-hour rendez-vous (02:00, 06:00, ... UTC, away from the spot cycles), and wake-ups when a mark crosses a 3 %-in-1-hour move (the crossing is kept
   pending until the guards allow it or the move fades). A round is done only when `perp_round_done` is
   written: an interrupted round is resumed (its orders and intents are idempotent). The basket is set up and
   rebalanced once per month, the trend decides once per UTC day, each at the first rendez-vous able to.
   The LLM portfolios play the rendez-vous (and the wake-ups once `wakeups = true`): their `claude -p` calls run
   in parallel inside the tick, which holds the watcher lock meanwhile (the next ticks skip, then catch up the
   minutes in order). See `arene/perp/llm_league.py`.

Everything is written to the league's own journal (`var-perp/journal/events.jsonl`). Exit codes: 0 fine,
3 the tick had failures (listed in `perp_tick`), 1 crash (with a `panique` alert when possible).
"""

from __future__ import annotations

import argparse
import bisect
import contextlib
import fcntl
import json
import os
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from arene.journal import Journal
from arene.ops import dormance, killswitch
from arene.ops.notify import Notifier
from arene.paths import Paths
from arene.perp import agent_orders as AO
from arene.perp import benchmarks as B
from arene.perp.agent import AgentDecider
from arene.perp.agent_round import _close_unprotected, _execute
from arene.perp.collect import data_root
from arene.perp.config import PerpConfig, default_var, load_perp_config
from arene.perp.counters import counters_for
from arene.perp.kraken_futures import CLOSE_GRACE_S, KrakenFuturesClient
from arene.perp.ledger import BP, HOUR_S, MINUTE_S, PerpLedgerError, equity_ueur, qty_seconds
from arene.perp.llm_league import (
    LlmConfigError,
    LlmLeague,
    LlmModel,
    has_budget,
    load_llm_league,
    run_llm_round,
)
from arene.perp.market import market_view, worst_half_spread_bp
from arene.perp.mcp_server import usd
from arene.perp.policy import PerpPolicy, load_perp_policy
from arene.perp.riskd import PerpIntent, PerpMarketView, evaluate_perp
from arene.perp.sim import MinuteCandles, PerpSimulator
from arene.perp.store import PerpDataStore
from arene.perp.types import InstrumentSpec

TICK_S = 300
ROUND_S = 4 * HOUR_S
# The rendez-vous fall at 02:00, 06:00, ..., 22:00 UTC: two hours away from the spot cycles (HH:05 every 4 h
# from 00:05), so the two leagues' model calls never run at the same time.
ROUND_OFFSET_S = 2 * HOUR_S
MAX_CATCH_UP_S = 7 * 86_400
MINUTE_PATIENCE_S = 1800  # a held minute without data is waited for 30 min, then processed as incomplete
CHECKPOINT_MINUTES = 360
FX_MAX_AGE_S = 1800
VIEW_MAX_AGE_S = 900
FUNDING_MISSING_AFTER_S = 3 * HOUR_S
WAKE_MOVE_BP = 300  # 3 %
WAKE_FADE_BP = 200  # a pending crossing is dropped when the move falls under 2 %
WAKE_WINDOW_S = HOUR_S
WAKE_PENDING_S = HOUR_S
WAKE_COOLDOWN_S = HOUR_S
WAKE_MAX_PER_DAY = 6  # per UTC day, as docs/VEILLE.md
WAKE_GUARD_BEFORE_ROUND_S = 1800
# no wake-up from 5 min before to 30 min after a spot cycle (HH:05 at 00, 04, ... UTC): the two leagues do not call
# the models at the same time; the crossing stays pending (an hour) and is served after the window
SPOT_CYCLE_S = 4 * HOUR_S
SPOT_CYCLE_OFFSET_S = 300
SPOT_GUARD_BEFORE_S = 300
SPOT_GUARD_AFTER_S = 1800
# Private `alert` rounds (docs/SPEC-PERP-ALERTES-ORDRES.md §3): a crossed alert wakes its owner alone
ALERT_COOLDOWN_S = HOUR_S  # since the owner's last round of any kind
ALERT_MAX_PER_DAY = 4  # per portfolio and UTC day
ALERT_GUARD_BEFORE_ROUND_S = 1800  # none in the 30 min before a rendez-vous
ALERT_PENDING_S = HOUR_S  # a crossed alert waiting longer is no longer served by a wake-up
ENTRY_MAX_LAG_S = 900  # a crossed entry order is executed only if its crossing minute is under 15 min old
ROUND_LATE_S = 1800  # a rendez-vous is run (or resumed) by a tick at most 30 min after its time


def near_spot_cycle(ts: int) -> bool:
    """True from SPOT_GUARD_BEFORE_S before to SPOT_GUARD_AFTER_S after a spot cycle."""
    since = (ts - SPOT_CYCLE_OFFSET_S) % SPOT_CYCLE_S  # seconds since the last spot cycle
    return since < SPOT_GUARD_AFTER_S or SPOT_CYCLE_S - since <= SPOT_GUARD_BEFORE_S


@dataclass
class TickReport:
    tick: int
    skipped: str | None = None
    minutes: int = 0
    fills: int = 0
    funding: int = 0
    rounds: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # expected states (kill switch, dormance...)
    problems: list[str] = field(default_factory=list)  # failures: exit code 3


@contextmanager
def _try_lock(path: Path) -> Iterator[bool]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


class PerpWatcher:
    def __init__(
        self,
        var: Path,
        cfg: PerpConfig,
        policy: PerpPolicy,
        specs: dict[str, InstrumentSpec],
        *,
        spot_paths: Paths | None = None,
        notifier: Notifier | None = None,
        llm: LlmLeague | None = None,
        decider_factory: Callable[[LlmModel], AgentDecider] | None = None,
        round_offset_s: int = ROUND_OFFSET_S,
    ) -> None:
        self.var = var
        self.cfg = cfg
        self.policy = policy
        self.specs = specs
        self.symbols = [i.kraken_symbol for i in cfg.instruments]
        self.store = PerpDataStore(data_root(var))
        self.journal = Journal(var / "journal" / "events.jsonl")
        self.sim = PerpSimulator(self.journal, {s: specs[s].tick_uusd for s in self.symbols}, cfg.simulation)
        self.spot_paths = spot_paths or Paths.from_env()
        self.notifier = notifier
        self.llm = llm
        self.decider_factory = decider_factory
        self.round_offset_s = round_offset_s
        self._deferred: dict[str, Any] | None = None

    # ------------------------------------------------------------------ helpers

    def _append(self, type_: str, payload: dict[str, Any], ts: int) -> None:
        self.sim.append_event(type_, payload, ts)

    def _events(self) -> list[dict[str, Any]]:
        return self.journal.events()

    def _alert(self, level: str, code: str, message: str, ts: int) -> None:
        self._append("alert", {"level": level, "code": code, "message": message[:1000]}, ts)
        if self.notifier is not None:
            self.notifier.send(level, code, message)

    def _alert_rearmed(
        self, events: list[dict[str, Any]], level: str, code: str, message: str, ts: int
    ) -> None:
        """At most one alert of this code per 6 hours."""
        if any(
            e["type"] == "alert" and e["payload"].get("code") == code and ts - e["ts"] < 6 * HOUR_S
            for e in events
        ):
            return
        self._alert(level, code, message, ts)

    def _kill_active(self) -> bool:
        return killswitch.is_active(self.spot_paths) or (self.var / "KILL").exists()

    def _dormance(self, now_ts: int, since_ts: int) -> str:
        return dormance.level(dormance.age_s(self.spot_paths, now_ts, since_ts))

    @staticmethod
    def _fx_at(snaps: list[Any], ts_list: list[int], ts: int) -> tuple[int, int] | None:
        """The latest EUR/USD at or before `ts`, no older than FX_MAX_AGE_S."""
        i = bisect.bisect_right(ts_list, ts) - 1
        while i >= 0 and ts - snaps[i].ts <= FX_MAX_AGE_S:
            fx = snaps[i].fx
            if fx is not None:
                return fx.bid_uusd_per_eur, fx.ask_uusd_per_eur
            i -= 1
        return None

    # ------------------------------------------------------------------ the tick

    def tick(self, now_ts: int) -> TickReport:
        tick = now_ts // TICK_S * TICK_S
        rep = TickReport(tick)
        self._deferred: dict[str, Any] | None = None
        with _try_lock(self.var / "watcher.lock") as mine:
            if not mine:
                rep.skipped = "watcher lock busy"
                return rep
            with _try_lock(self.var / "collect.lock") as collector_idle:
                if not collector_idle:
                    rep.skipped = "collector running"
                    return rep
                self._tick_data(now_ts, tick, rep)
                if rep.skipped:
                    return rep
            # the LLM calls run without the collector's lock (the collector keeps collecting meanwhile), still
            # under the watcher's: no other tick starts before the round is finished
            if self._deferred is not None:
                self._llm_phase(**self._deferred, rep=rep)
        return rep

    def _tick_data(self, now_ts: int, tick: int, rep: TickReport) -> None:
        events = self._events()
        marks_ev = [e for e in events if e["type"] in ("perp_tick", "perp_checkpoint")]
        if any(e["type"] == "perp_tick" and e["payload"]["tick"] == tick for e in marks_ev):
            rep.skipped = "tick already done"
            return
        for name in B.ALL:
            self.sim.open_portfolio(name, "benchmark", now_ts)
        last = marks_ev[-1]["payload"] if marks_ev else None
        last_minute = last["last_minute"] if last else None
        # the agents' orders scan from the last TICK (not a checkpoint): a tick killed during a catch-up scans
        # its minutes again (a crossing already journaled is never journaled twice)
        ticks = [e for e in marks_ev if e["type"] == "perp_tick"]
        prev_minute = ticks[-1]["payload"]["last_minute"] if ticks else None
        pending = list(last["pending_funding"]) if last else []
        self._closeout_followups(events, rep)
        view = market_view(self.store, self.symbols, now_ts)
        fresh = self._is_fresh(view, now_ts)
        snaps = self.store.tickers().load((last_minute or now_ts) - 86_400, now_ts + 1)
        snap_ts = [s.ts for s in snaps]
        last_minute, pending = self._process_minutes(last_minute, now_ts, snaps, snap_ts, pending, rep)
        pending = self._settle_funding(pending, now_ts, snaps, snap_ts, rep)
        events = self._events()
        # crossings are detected on every processed minute, even with a stale view (an entry order then waits
        # for a fresh view, within ENTRY_MAX_LAG_S)
        self._agent_orders(now_ts, view if fresh else None, rep, prev_minute, last_minute)
        events = self._events()
        if fresh:
            assert view is not None
            self._controls(now_ts, view, events, rep)
            self._rounds(now_ts, view, rep, last_minute)
        else:
            rep.problems.append("market view missing or stale: no equity, no control, no round")
            self._alert_rearmed(
                events, "action", "perp_data_stale", "perp league: market data stale or missing", now_ts
            )
            if view is not None:
                self._kill_and_dormance(now_ts, view, events, rep)
        self._append(
            "perp_tick",
            {
                "tick": tick,
                "last_minute": last_minute,
                "pending_funding": pending,
                "minutes": rep.minutes,
                "fills": rep.fills,
                "rounds": rep.rounds,
                "notes": rep.notes[:20],
                "problems": rep.problems[:20],
            },
            now_ts,
        )

    def _is_fresh(self, view: PerpMarketView | None, now_ts: int) -> bool:
        if view is None or now_ts - view.fx_ts > VIEW_MAX_AGE_S or view.fx_bid <= 0:
            return False
        ages = [now_ts - m.quote_ts for m in view.instruments.values()]
        return len(view.instruments) == len(self.symbols) and max(ages) <= VIEW_MAX_AGE_S

    def _llm_phase(
        self,
        *,
        round_id: int,
        kind: str,
        trigger: dict[str, Any] | None,
        now_ts: int,
        view: PerpMarketView,
        blocked: bool,
        ok: bool,
        rep: TickReport,
        portfolios: list[str] | None = None,
    ) -> None:
        """The LLM part of a round, then `perp_round_done`. Decisions are executed on a market view read again
        after the calls (when fresh), at that time: the models get no latency advantage."""
        assert self.llm is not None
        t0 = time.monotonic()

        def refresh() -> tuple[PerpMarketView, int] | None:
            now2 = now_ts + int(time.monotonic() - t0)
            v2 = market_view(self.store, self.symbols, now2)
            return (v2, now2) if self._is_fresh(v2, now2) else None

        try:
            res = run_llm_round(
                league=self.llm, var=self.var, sim=self.sim, store=self.store, view=view, specs=self.specs,
                policy=self.policy, config_sha256=self.cfg.sha256, round_id=round_id, now_ts=now_ts, kind=kind,
                trigger=trigger, entries_blocked=lambda: blocked or self._kill_active(),
                decider_factory=self.decider_factory, refresh=refresh,
                only=None if portfolios is None else set(portfolios),
            )  # fmt: skip
        except Exception as exc:  # noqa: BLE001 (the round stays open: resumed by the next tick)
            message = f"llm round {round_id}: {type(exc).__name__}: {exc}"[:500]
            rep.problems.append(message)
            self._alert("action", "perp_llm_round_failed", message, now_ts)
            return
        rep.notes += res.notes
        if res.failed and res.failed * 2 >= max(res.called, 1):
            self._alert_rearmed(
                self._events(), "action", "perp_llm_no_decision",
                f"perp league: {res.failed} of {res.called} models without a decision at round {round_id}",
                now_ts,
            )  # fmt: skip
        if ok:
            self._append("perp_round_done", {"round": round_id}, now_ts)

    # ------------------------------------------------------------------ minutes and funding

    def _process_minutes(
        self,
        last_minute: int | None,
        now_ts: int,
        snaps: list[Any],
        snap_ts: list[int],
        pending: list[int],
        rep: TickReport,
    ) -> tuple[int, list[int]]:
        clock_limit = (now_ts - CLOSE_GRACE_S) // MINUTE_S * MINUTE_S - MINUTE_S
        stored = [self.store.candles("mark", s, MINUTE_S).last_ts() for s in self.symbols]
        data_limit = min((t for t in stored if t is not None), default=None)
        if last_minute is None:  # a new league starts now: nothing to catch up
            return (data_limit if data_limit is not None else clock_limit), pending
        if clock_limit - last_minute > MAX_CATCH_UP_S:
            rep.problems.append(
                f"catch-up capped: {clock_limit - last_minute - MAX_CATCH_UP_S} s of minutes skipped"
            )
            last_minute = clock_limit - MAX_CATCH_UP_S
        extra = {s: worst_half_spread_bp(self.store, s, now_ts) for s in self.symbols}
        series = {
            s: {
                k: {
                    c.ts: c
                    for c in self.store.closed_candles(k, s, MINUTE_S, last_minute, clock_limit + MINUTE_S)
                }
                for k in ("mark", "trade")
            }
            for s in self.symbols
        }
        last_marks: dict[str, int] = {}
        for s in self.symbols:
            prev = self.store.closed_candles(
                "mark", s, MINUTE_S, last_minute - 86_400, last_minute + MINUTE_S
            )
            if prev:
                last_marks[s] = prev[-1].close
        held = {i for acc in self.sim.states().values() for i in acc.positions}
        cursor = last_minute
        for m in range(last_minute + MINUTE_S, clock_limit + MINUTE_S, MINUTE_S):
            fx = self._fx_at(snaps, snap_ts, m + MINUTE_S - 1)
            lacking = [s for s in held if m not in series[s]["mark"]]
            if held and (lacking or fx is None) and now_ts - (m + MINUTE_S) < MINUTE_PATIENCE_S:
                break  # wait: the collector may still bring this minute
            rep.minutes += 1
            for s in self.symbols:
                c = series[s]["mark"].get(m)
                if c is not None:
                    last_marks[s] = c.close
            if held and fx is None:
                rep.problems.append(
                    f"minute {m}: no EUR/USD after {MINUTE_PATIENCE_S} s, positions not evaluated"
                )
            elif held:
                candles = {}
                for s in held:
                    mk, tr = series[s]["mark"].get(m), series[s]["trade"].get(m)
                    if mk is not None:
                        candles[s] = MinuteCandles(
                            (mk.open, mk.high, mk.low, mk.close),
                            (tr.open, tr.high, tr.low, tr.close) if tr else None,
                        )
                fills, problems = self.sim.process_minute(
                    m, candles, fx, fallback_marks=last_marks, exit_slippage_bp=extra
                )
                rep.fills += len(fills)
                rep.problems.extend(problems)
                if fills:
                    held = {i for acc in self.sim.states().values() for i in acc.positions}
                    if any(f["reason"] == "margin_closeout" for f in fills):
                        self._closeout_followups(self._events(), rep)
            if (m + MINUTE_S) % HOUR_S == 0 and (m + MINUTE_S) not in pending:
                pending.append(m + MINUTE_S)
            cursor = m
            if rep.minutes % CHECKPOINT_MINUTES == 0:
                self._append(
                    "perp_checkpoint", {"last_minute": cursor, "pending_funding": sorted(pending)}, now_ts
                )
        return cursor, sorted(pending)

    def _closeout_followups(self, events: list[dict[str, Any]], rep: TickReport) -> None:
        """Every margin close-out gets its freeze and its alert, exactly once (also after a crash)."""
        done = {
            (e["payload"]["portfolio"], e["payload"].get("minute"))
            for e in events
            if e["type"] == "portfolio_frozen" and e["payload"].get("reason") == "margin_closeout"
        }
        for e in events:
            if e["type"] != "margin_closeout":
                continue
            p = e["payload"]
            if (p["portfolio"], p["minute"]) in done:
                continue
            until = p["minute"] + self.policy.freeze_duration_s
            self._append(
                "portfolio_frozen",
                {
                    "portfolio": p["portfolio"],
                    "reason": "margin_closeout",
                    "minute": p["minute"],
                    "until_ts": until,
                },
                e["ts"],
            )
            self._alert(
                "panique",
                "perp_margin_closeout",
                f"{p['portfolio']}: margin close-out at minute {p['minute']}",
                e["ts"],
            )
            rep.notes.append(f"margin close-out {p['portfolio']} {p['minute']}")

    def _settle_funding(
        self, pending: list[int], now_ts: int, snaps: list[Any], snap_ts: list[int], rep: TickReport
    ) -> list[int]:
        states = self.sim.states()
        stamps = sorted(pending)
        for n, stamp in enumerate(stamps):
            held = [
                s
                for s in self.symbols
                if any(qty_seconds(a.qty_history.get(s, []), stamp - HOUR_S, stamp) for a in states.values())
            ]
            rates = {s: next(iter(self.store.funding(s).load(stamp, stamp + 1)), None) for s in held}
            fx = self._fx_at(snaps, snap_ts, stamp)
            late = now_ts - stamp >= FUNDING_MISSING_AFTER_S
            if (any(r is None for r in rates.values()) and not late) or (fx is None and any(rates.values())):
                if fx is None and late and any(rates.values()):
                    rep.problems.append(f"funding {stamp}: no EUR/USD, kept pending")
                return stamps[n:]  # wait, and keep the stamps in order
            for s, r in rates.items():
                try:
                    if r is None:
                        self.sim.record_missing_funding(s, stamp)
                    else:
                        assert fx is not None
                        rep.funding += len(self.sim.settle_funding(s, stamp, r.funding_nusd, fx))
                except PerpLedgerError as exc:
                    rep.problems.append(f"funding {s} {stamp}: {exc}")
        return []

    # ------------------------------------------------------------------ controls

    def _kill_and_dormance(
        self, now_ts: int, view: PerpMarketView, events: list[dict[str, Any]], rep: TickReport
    ) -> bool:
        """Flattens the deciding portfolios under the kill switch or a 9-day dormance (with whatever quotes
        exist, even stale: reducing risk never waits). Returns True if entries are blocked."""
        opened = min((e["ts"] for e in events if e["type"] == "portfolio_opened"), default=now_ts)
        dorm = self._dormance(now_ts, opened)
        kill = self._kill_active()
        fx = (view.fx_bid, view.fx_ask)
        quotes = {s: (m.bid_uusd, m.ask_uusd) for s, m in view.instruments.items()}
        if (kill or dorm == dormance.FLATTEN) and fx[0] > 0:
            for name, acc in sorted(self.sim.states().items()):
                if name in B.REFERENCES or not acc.positions:
                    continue
                try:
                    self.sim.flatten(name, now_ts, quotes, fx, "kill_switch")
                    reason = "kill switch" if kill else "dormance"
                    self._alert("action", "perp_flattened", f"{name}: flattened ({reason})", now_ts)
                except PerpLedgerError as exc:
                    rep.problems.append(f"{name} flatten: {exc}")
        blocked = kill or dorm != dormance.OK
        if blocked:
            rep.notes.append("kill switch or dormance: no entry for the deciding portfolios")
        return blocked

    def _controls(
        self, now_ts: int, view: PerpMarketView, events: list[dict[str, Any]], rep: TickReport
    ) -> None:
        fx = (view.fx_bid, view.fx_ask)
        quotes = {s: (m.bid_uusd, m.ask_uusd) for s, m in view.instruments.items()}
        marks = {s: m.mark_uusd for s, m in view.instruments.items()}
        self._kill_and_dormance(now_ts, view, events, rep)
        events = self._events()
        deciding = set()
        for name, acc in sorted(self.sim.states().items()):
            try:
                self.sim.write_equity(name, now_ts, marks, fx)
                if name in B.REFERENCES:
                    continue
                deciding.add(name)
                for inst, pos in sorted(acc.positions.items()):
                    if pos.stop_uusd is None:  # a deciding portfolio never holds a position without a stop
                        self.sim.market_order(
                            f"no-stop:{name}:{inst}:{now_ts}", name, inst, -pos.qty, quotes[inst], fx, now_ts,
                            "no_stop", marks=marks,
                        )  # fmt: skip
                        self._alert("panique", "perp_position_without_stop", f"{name} {inst}: closed", now_ts)
                acc = self.sim.states()[name]
                eq = equity_ueur(acc, marks, *fx)
                c = counters_for(events, name, now_ts)
                peak = max(c.equity_peak_ueur, acc.capital_ueur, eq)
                if not acc.halted and (peak - eq) * BP >= self.policy.drawdown_halt_bp * peak:
                    self.sim.flatten(name, now_ts, quotes, fx, "halt")
                    self._append(
                        "portfolio_halted", {"portfolio": name, "reason": "drawdown", "until_ts": 0}, now_ts
                    )
                    self._alert(
                        "action", "perp_portfolio_halted", f"{name}: drawdown, flattened and halted", now_ts
                    )
                    continue
                last_freeze_end = max(
                    (
                        e["payload"]["until_ts"]
                        for e in events
                        if e["type"] == "portfolio_frozen" and e["payload"]["portfolio"] == name
                    ),
                    default=0,
                )
                ago = c.equity_24h_ago_ueur
                if (
                    not acc.halted
                    and acc.frozen_until_ts <= now_ts
                    and now_ts - last_freeze_end >= 86_400  # the same loss does not re-arm a freeze
                    and ago > 0
                    and (ago - eq) * BP >= self.policy.daily_loss_freeze_bp * ago
                ):
                    until = now_ts + self.policy.freeze_duration_s
                    self._append(
                        "portfolio_frozen",
                        {"portfolio": name, "reason": "daily_loss", "until_ts": until},
                        now_ts,
                    )
                    self._alert("info", "perp_portfolio_frozen", f"{name}: loss over 24 h, frozen", now_ts)
            except PerpLedgerError as exc:
                rep.problems.append(f"{name} controls: {exc}")
        try:
            self.sim.close_expired(now_ts, quotes, fx, portfolios=deciding)
        except PerpLedgerError as exc:
            rep.problems.append(f"max holding: {exc}")

    # ------------------------------------------------------------------ agent alerts and entry orders

    def _agent_orders(
        self, now_ts: int, view: PerpMarketView | None, rep: TickReport, prev_minute: int | None, cursor: int
    ) -> None:
        """Alerts and entry orders the agents left (spec §2), on the mark minutes this tick processed
        (`prev_minute` < minute <= `cursor`). State is recomputed from the journal; a failure of one portfolio
        is reported and never stops the tick."""
        events = self._events()
        owners = sorted({e["payload"]["portfolio"] for e in events if e["type"] == "agent_orders_set"})
        cache: dict[str, list[Any]] = {}
        for name in owners:
            try:
                self._agent_orders_for(name, now_ts, view, prev_minute, cursor, cache, rep)
            except Exception as exc:  # noqa: BLE001 (one portfolio's failure never stops the tick)
                rep.problems.append(f"{name} agent orders: {type(exc).__name__}: {exc}"[:300])

    def _new_minutes(
        self, symbol: str, prev_minute: int | None, cursor: int, cache: dict[str, list[Any]]
    ) -> list[Any]:
        if symbol not in cache:
            cache[symbol] = (
                []
                if prev_minute is None or cursor <= prev_minute
                else self.store.closed_candles(
                    "mark", symbol, MINUTE_S, prev_minute + MINUTE_S, cursor + MINUTE_S
                )
            )
        return cache[symbol]

    def _agent_orders_for(
        self,
        name: str,
        now_ts: int,
        view: PerpMarketView | None,
        prev_minute: int | None,
        cursor: int,
        cache: dict[str, list[Any]],
        rep: TickReport,
    ) -> None:
        """Each stage and each crossing in its own try: one failure never hides the others (the minutes of
        this tick are not scanned again by the next one)."""

        def guarded(what: str, fn: Callable[[], None]) -> None:
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                rep.problems.append(f"{name} agent orders, {what}: {type(exc).__name__}: {exc}"[:300])

        # 1. a crash (or a stale view) left a crossed entry order without verdict, or approved without execution
        if view is not None:
            for el, trig in AO.pending_state(self._events(), name).unresolved_entries():
                minute = trig["payload"]["minute"]
                guarded(
                    f"entry {el.id[:12]}",
                    lambda el=el, minute=minute: self._entry_step(name, el, minute, now_ts, view, rep),
                )

        # 2. a halted portfolio loses everything (nothing of it fires any more)
        def expire(only_halted: bool) -> None:
            halted = self.sim.states()[name].halted
            if only_halted and not halted:
                return
            for el in AO.pending_state(self._events(), name).pending:
                if halted or el.data["expires_ts"] <= now_ts:
                    reason = "portfolio_halted" if halted else "expired"
                    self._append(
                        "agent_order_ended",
                        {"portfolio": name, "id": el.id, "kind": el.kind, "reason": reason},
                        now_ts,
                    )

        guarded("halt", lambda: expire(True))
        # 3. crossings on the newly processed minutes, before the expiry (a minute counts if it starts at or
        #    after the creation and before the expiry)
        live = AO.pending_state(self._events(), name).pending
        hits = []
        for rank, el in enumerate(live):
            d = el.data
            for c in self._new_minutes(d["instrument"], prev_minute, cursor, cache):
                if c.ts < el.created_ts or c.ts >= d["expires_ts"]:
                    continue
                if (c.low <= d["price_uusd"]) if d["condition"] == "below" else (c.high >= d["price_uusd"]):
                    hits.append((c.ts, 0 if el.kind == "alert" else 1, rank, el, c))
                    break
        for _ts, _kind, _rank, el, c in sorted(hits, key=lambda h: h[:3]):
            guarded(
                f"{el.kind} {el.id[:12]}", lambda el=el, c=c: self._crossed(name, el, c, now_ts, view, rep)
            )

        # 4. expiry
        guarded("expiry", lambda: expire(False))

    def _crossed(
        self, name: str, el: AO.Element, c: Any, now_ts: int, view: PerpMarketView | None, rep: TickReport
    ) -> None:
        d = el.data
        payload = {
            "portfolio": name,
            "id": el.id,
            "instrument": d["instrument"],
            **({"side": d["side"]} if el.kind == "entry" else {}),
            "condition": d["condition"],
            "price_uusd": d["price_uusd"],
            "minute": c.ts,
            "mark_high_uusd": c.high,
            "mark_low_uusd": c.low,
        }
        self._append(
            "agent_alert_triggered" if el.kind == "alert" else "agent_entry_triggered", payload, now_ts
        )
        rep.notes.append(f"{name}: {el.kind} {d['instrument']} {d['condition']} crossed at {c.ts}")
        if el.kind == "entry" and view is not None:
            self._entry_step(name, el, c.ts, now_ts, view, rep)

    def _entry_step(
        self, name: str, el: AO.Element, minute: int, now_ts: int, view: PerpMarketView, rep: TickReport
    ) -> None:
        """Takes a crossed entry order as far as it goes: verdict, then execution. Idempotent: each stage is
        skipped when the journal already holds it (the market order itself is idempotent by the order id)."""
        events = self._events()
        st = AO.pending_state(events, name)
        oid, d = el.id, el.data
        inst = d["instrument"]
        if oid in st.executions:
            return

        def outcome(status: str, error: str | None = None) -> None:
            self._append(
                "perp_execution",
                {
                    "intent_id": oid,
                    "portfolio": name,
                    "instrument": inst,
                    "status": status,
                    "error": None if error is None else error[:500],
                },
                now_ts,
            )

        acc = self.sim.states()[name]
        if oid in st.fills:  # filled before a crash, the closing record is missing
            pos = acc.positions.get(inst)
            if (
                pos is not None and pos.stop_uusd is None
            ):  # cut between the fill and the stop: never unprotected
                quotes = {s: (m.bid_uusd, m.ask_uusd) for s, m in view.instruments.items()}
                marks = {s: m.mark_uusd for s, m in view.instruments.items()}
                closed = _close_unprotected(
                    self.sim, name, oid, inst, quotes, marks, (view.fx_bid, view.fx_ask), now_ts,
                    PerpLedgerError("resumed after a cut between the fill and the stop"),
                )  # fmt: skip
                outcome("closed_without_stop" if closed else "unprotected_position_open", "resumed")
                return
            missing_tp = pos is not None and d["take_profit_bp"] is not None and pos.take_profit_uusd is None
            outcome(
                "filled_without_take_profit"
                if missing_tp
                else ("filled" if pos is not None else "filled_then_closed"),
                "resumed",
            )
            return
        if now_ts - minute >= ENTRY_MAX_LAG_S:  # a catch-up after a cut: never executed late
            outcome("not_executed_stale_trigger")
            return
        blocked = self._kill_and_dormance(now_ts, view, events, rep)
        action = "open_long" if d["side"] == "long" else "open_short"
        intent = PerpIntent(
            intent_id=oid, portfolio=name, ts=now_ts, instrument=inst, action=action,
            size_bp=d["size_bp"], stop_bp=d["stop_bp"], take_profit_bp=d["take_profit_bp"],
            horizon_h=d["horizon_h"], expected_move_bp=d["expected_move_bp"], confidence_pct=d["confidence_pct"],
        )  # fmt: skip
        counters = counters_for(events, name, now_ts)
        v = evaluate_perp(
            intent, acc, view, self.specs, counters, self.policy, self.cfg.simulation, now_ts, blocked
        )
        if oid not in st.verdicts:
            self._append(
                "perp_verdict",
                {
                    "intent_id": oid,
                    "portfolio": name,
                    "instrument": inst,
                    "action": action,
                    "approved": v.approved,
                    "reasons": list(v.reasons),
                    "qty": v.qty,
                    "policy_sha256": v.policy_sha256,
                    "error": v.error,
                },
                now_ts,
            )
        elif (
            not v.approved
        ):  # approved before a cut, refused now: the stop and the size come from this verdict
            outcome("not_executed_refused_on_resume", ",".join(v.reasons))
            return
        if not v.approved:
            return
        quotes = {s: (m.bid_uusd, m.ask_uusd) for s, m in view.instruments.items()}
        marks = {s: m.mark_uusd for s, m in view.instruments.items()}
        _execute(self.sim, name, oid, inst, action, v, quotes, marks, (view.fx_bid, view.fx_ask), now_ts)

    # ------------------------------------------------------------------ rounds

    def _move_bp(self, symbol: str, last_minute: int) -> int | None:
        """Move over the hour ending with the minute `last_minute`, as seen then (no later data)."""
        until = last_minute + MINUTE_S
        closes = {
            c.ts: c.close
            for c in self.store.closed_candles("mark", symbol, MINUTE_S, until - WAKE_WINDOW_S - 600, until)
        }
        if not closes:
            return None
        last = max(closes)
        ref = closes.get(last - WAKE_WINDOW_S)
        return None if ref is None else (closes[last] - ref) * BP // ref

    def _rounds(self, now_ts: int, view: PerpMarketView, rep: TickReport, cursor: int) -> None:
        events = self._events()
        started = {e["payload"]["round"]: e["payload"] for e in events if e["type"] == "perp_round"}
        done = {e["payload"]["round"] for e in events if e["type"] == "perp_round_done"}
        for rid, r in started.items():  # resume an interrupted round within its window
            if rid not in done and now_ts - r["ts"] < ROUND_LATE_S:
                self._round(
                    rid,
                    r["kind"],
                    r.get("trigger"),
                    now_ts,
                    view,
                    rep,
                    resume=True,
                    portfolios=r.get("portfolios"),
                )
                return
        rdv = (now_ts - self.round_offset_s) // ROUND_S * ROUND_S + self.round_offset_s
        if now_ts - rdv < ROUND_LATE_S and rdv not in started:
            self._round(rdv, "rendezvous", None, now_ts, view, rep)
            return
        if not self._wakeup(now_ts, view, rep, cursor, events, started, rdv):
            self._alert_round(
                now_ts, view, rep, events, started, rdv
            )  # one round per tick: wake-ups come first

    def _wakeup(
        self,
        now_ts: int,
        view: PerpMarketView,
        rep: TickReport,
        cursor: int,
        events: list[dict[str, Any]],
        started: dict[int, dict[str, Any]],
        rdv: int,
    ) -> bool:
        """Market wake-ups: a crossing is recorded, kept pending for an hour, served when the guards allow it.
        True when a round was started."""
        pend = [e for e in events if e["type"] == "perp_wake_pending" and now_ts - e["ts"] < WAKE_PENDING_S]
        served = {
            r.get("trigger", {}).get("pending_ts")
            for r in started.values()
            if r["kind"] == "wakeup" and r.get("trigger")
        }
        cursors = [e["payload"]["last_minute"] for e in events if e["type"] == "perp_tick"]
        prev_cursor = cursors[-1] if cursors else None
        for s in self.symbols:
            mv = self._move_bp(s, cursor)
            prev = self._move_bp(s, prev_cursor) if prev_cursor is not None else None
            if mv is not None and abs(mv) >= WAKE_MOVE_BP and (prev is None or abs(prev) < WAKE_MOVE_BP):
                payload = {"instrument": s, "move_bp": mv, "window_s": WAKE_WINDOW_S}
                self._append("perp_wake_pending", payload, now_ts)
                pend.append({"ts": now_ts, "payload": payload})
        candidates = [
            p
            for p in pend
            if p["ts"] not in served
            and abs(self._move_bp(p["payload"]["instrument"], cursor) or 0) >= WAKE_FADE_BP
        ]
        if not candidates:
            return False
        # private alert rounds count neither in the cooldown nor in the daily cap of the market wake-ups
        last_round = max((r["ts"] for r in started.values() if r["kind"] != "alert"), default=0)
        day = now_ts // 86_400
        today = [r for r in started.values() if r["kind"] == "wakeup" and r["ts"] // 86_400 == day]
        if (
            now_ts - last_round < WAKE_COOLDOWN_S
            or len(today) >= WAKE_MAX_PER_DAY
            or rdv + ROUND_S - now_ts < WAKE_GUARD_BEFORE_ROUND_S
            or near_spot_cycle(now_ts)
        ):
            return False
        best = max(candidates, key=lambda p: abs(p["payload"]["move_bp"]))
        tick = now_ts // TICK_S * TICK_S
        self._round(tick, "wakeup", {**best["payload"], "pending_ts": best["ts"]}, now_ts, view, rep)
        return True

    def _alert_round(
        self,
        now_ts: int,
        view: PerpMarketView,
        rep: TickReport,
        events: list[dict[str, Any]],
        started: dict[int, dict[str, Any]],
        rdv: int,
    ) -> None:
        """A crossed alert wakes its owner alone (spec §3). The oldest waiting alert whose owner passes the
        guards is served; the others wait for the next tick."""
        if self.llm is None or not self.llm.enabled:
            return
        if rdv + ROUND_S - now_ts < ALERT_GUARD_BEFORE_ROUND_S or near_spot_cycle(now_ts):
            return
        models = {m.portfolio: m for m in self.llm.models}
        states = self.sim.states()
        day = now_ts // 86_400
        for a in AO.unserved_alerts(events, now_ts, ALERT_PENDING_S):
            owner = a["portfolio"]
            if owner not in models or states[owner].halted or not has_budget(models[owner], events, now_ts):
                continue
            last = max(
                (
                    e["ts"]
                    for e in events
                    if e["type"] == "round_data" and e["payload"].get("portfolio") == owner
                ),
                default=0,
            )
            today = sum(
                1
                for r in started.values()
                if r["kind"] == "alert" and r.get("portfolios") == [owner] and r["ts"] // 86_400 == day
            )
            if now_ts - last < ALERT_COOLDOWN_S or today >= ALERT_MAX_PER_DAY:
                continue
            trigger = {
                "alert_id": a["id"],
                "instrument": a["instrument"],
                "condition": a["condition"],
                "price_usd": usd(a["price_uusd"]),
                "note": a["note"],
            }
            self._round(now_ts // TICK_S * TICK_S, "alert", trigger, now_ts, view, rep, portfolios=[owner])
            return

    def _round(
        self,
        round_id: int,
        kind: str,
        trigger: dict[str, Any] | None,
        now_ts: int,
        view: PerpMarketView,
        rep: TickReport,
        *,
        resume: bool = False,
        portfolios: list[str] | None = None,
    ) -> None:
        if not resume:
            extra = {} if portfolios is None else {"portfolios": portfolios}
            self._append(
                "perp_round",
                {"round": round_id, "kind": kind, "trigger": trigger, "ts": now_ts, **extra},
                now_ts,
            )
        rep.rounds.append(f"{kind}:{round_id}{' (resumed)' if resume else ''}")
        fx = (view.fx_bid, view.fx_ask)
        quotes = {s: (m.bid_uusd, m.ask_uusd) for s, m in view.instruments.items()}
        marks = {s: m.mark_uusd for s, m in view.instruments.items()}
        events = self._events()
        blocked = self._kill_and_dormance(now_ts, view, events, rep)
        ok = True
        if kind == "rendezvous":
            month = time.strftime("%Y-%m", time.gmtime(now_ts))
            day = now_ts // 86_400
            marker = {
                (e["payload"]["benchmark"], e["payload"]["period"])
                for e in events
                if e["type"] == "perp_benchmark_done"
            }
            if (B.BASKET, month) not in marker:
                ok &= self._basket(now_ts, month, marks, quotes, fx, rep)
            if (B.TREND, str(day)) not in marker:
                ok &= self._trend(now_ts, str(day), marks, quotes, fx, rep)
        private = kind == "alert"  # only its owner plays: no benchmark, no other model
        llm_plays = (
            self.llm is not None
            and self.llm.enabled
            and (kind in ("rendezvous", "alert") or self.llm.wakeups)
        )
        # the random benchmark plays the rounds the models play (wake-ups too only once the models have them)
        if not private and (
            kind == "rendezvous" or self.llm is None or not self.llm.enabled or self.llm.wakeups
        ):
            ok &= self._random(round_id, now_ts, view, quotes, marks, fx, blocked, rep)
        if llm_plays:
            self._deferred = {
                "round_id": round_id, "kind": kind, "trigger": trigger, "now_ts": now_ts, "view": view,
                "blocked": blocked, "ok": ok, "portfolios": portfolios,
            }  # fmt: skip
            return
        if ok:
            self._append("perp_round_done", {"round": round_id}, now_ts)

    def _basket(
        self,
        now_ts: int,
        month: str,
        marks: dict[str, int],
        quotes: dict[str, tuple[int, int]],
        fx: tuple[int, int],
        rep: TickReport,
    ) -> bool:
        acc = self.sim.states()[B.BASKET]
        eq = equity_ueur(acc, marks, *fx)
        ok = True
        for n, (inst, qty) in enumerate(B.basket_orders(acc, eq, marks, fx[0], self.specs)):
            try:
                self.sim.market_order(
                    f"{B.BASKET}:{month}:{n}:{inst}",
                    B.BASKET,
                    inst,
                    qty,
                    quotes[inst],
                    fx,
                    now_ts,
                    marks=marks,
                )
            except PerpLedgerError as exc:
                rep.problems.append(f"{B.BASKET} {inst}: {exc}")
                ok = False
        if ok:
            self._append("perp_benchmark_done", {"benchmark": B.BASKET, "period": month}, now_ts)
        return ok

    def _daily_close(self, inst: str, day_end: int) -> int | None:
        c = self.store.closed_candles("mark", inst, MINUTE_S, day_end - MINUTE_S, day_end)
        return c[-1].close if c else None

    def _trend(
        self,
        now_ts: int,
        day: str,
        marks: dict[str, int],
        quotes: dict[str, tuple[int, int]],
        fx: tuple[int, int],
        rep: TickReport,
    ) -> bool:
        day_end = int(day) * 86_400  # the last closed UTC day ends at the start of today
        closes = {
            s: (self._daily_close(s, day_end), self._daily_close(s, day_end - B.TREND_LOOKBACK_DAYS * 86_400))
            for s in self.symbols
        }
        signals = B.trend_signals(closes)
        unknown = sorted(s for s, v in signals.items() if v is None)
        if unknown:
            rep.notes.append(f"trend: no daily close for {unknown}, kept as is")
        acc = self.sim.states()[B.TREND]
        eq = equity_ueur(acc, marks, *fx)
        ok = True
        for n, (inst, qty, entry) in enumerate(B.trend_orders(acc, eq, signals, marks, fx[0], self.specs)):
            try:
                self.sim.market_order(
                    f"{B.TREND}:{day}:{n}:{inst}", B.TREND, inst, qty, quotes[inst], fx, now_ts, marks=marks
                )
                if entry:
                    fill_px = quotes[inst][1] if qty > 0 else quotes[inst][0]
                    tick = self.specs[inst].tick_uusd
                    if qty > 0:
                        stop = max(fill_px * (BP - B.TREND_STOP_BP) // BP // tick * tick, tick)
                    else:
                        stop = -(-fill_px * (BP + B.TREND_STOP_BP) // BP // tick) * tick
                    self.sim.set_conditional(B.TREND, inst, "stop", stop, now_ts)
            except PerpLedgerError as exc:
                rep.problems.append(f"{B.TREND} {inst}: {exc}")
                ok = False
        if ok:
            self._append(
                "perp_benchmark_done", {"benchmark": B.TREND, "period": day, "signals": signals}, now_ts
            )
        return ok

    def _random(
        self,
        round_id: int,
        now_ts: int,
        view: PerpMarketView,
        quotes: dict[str, tuple[int, int]],
        marks: dict[str, int],
        fx: tuple[int, int],
        blocked: bool,
        rep: TickReport,
    ) -> bool:
        events = self._events()
        seen = {e["payload"]["intent_id"] for e in events if e["type"] == "perp_verdict"}
        acc = self.sim.states()[B.RANDOM]
        ok = True
        for it in B.random_round(round_id, acc.positions, self.symbols):
            if it.intent_id in seen:
                continue  # resumed round: this intent was already judged
            acc = self.sim.states()[B.RANDOM]
            counters = counters_for(self._events(), B.RANDOM, now_ts)
            it = type(it)(**{**it.__dict__, "ts": now_ts})
            v = evaluate_perp(
                it, acc, view, self.specs, counters, self.policy, self.cfg.simulation, now_ts, blocked
            )
            self._append(
                "perp_verdict",
                {
                    "intent_id": it.intent_id,
                    "portfolio": it.portfolio,
                    "instrument": it.instrument,
                    "action": it.action,
                    "approved": v.approved,
                    "reasons": list(v.reasons),
                    "qty": v.qty,
                    "policy_sha256": v.policy_sha256,
                    "error": v.error,
                },
                now_ts,
            )
            if not v.approved:
                continue
            try:
                self.sim.market_order(
                    it.intent_id,
                    B.RANDOM,
                    it.instrument,
                    v.qty,
                    quotes[it.instrument],
                    fx,
                    now_ts,
                    marks=marks,
                )
                if it.action.startswith("open"):
                    self.sim.set_conditional(B.RANDOM, it.instrument, "stop", v.stop_uusd, now_ts)
                    if v.take_profit_uusd is not None:
                        self.sim.set_conditional(
                            B.RANDOM, it.instrument, "take_profit", v.take_profit_uusd, now_ts
                        )
            except PerpLedgerError as exc:
                rep.problems.append(f"{B.RANDOM} {it.instrument}: {exc}")
                ok = False
        return ok


# ---------------------------------------------------------------------- specs and command line


def load_specs(
    var: Path, symbols: list[str], now_ts: int, client: KrakenFuturesClient | None = None
) -> dict[str, InstrumentSpec]:
    """Contract specs, cached in `var/specs.json` for a day (a failure falls back to the cache)."""
    p = var / "specs.json"
    cached = None
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            cached = {s: InstrumentSpec.from_dict(d) for s, d in data["specs"].items()}
            if now_ts - data["ts"] < 86_400 and set(symbols) <= set(cached):
                return cached
        except (OSError, ValueError, KeyError, TypeError):
            cached = None
    try:
        specs = (client or KrakenFuturesClient()).instruments(symbols)
    except Exception:
        if cached is not None:
            return cached
        raise
    var.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"ts": now_ts, "specs": {s: v.to_dict() for s, v in specs.items()}}), encoding="utf-8"
    )
    os.replace(tmp, p)
    return specs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m arene.perp.watcher")
    ap.add_argument("command", choices=["tick"])
    ap.add_argument("--var", type=Path, default=None)
    args = ap.parse_args(argv)
    var = (args.var or default_var()).resolve()
    spot = Paths.from_env()
    if var == spot.var.resolve() or spot.var.resolve() in var.parents:
        print("refusing to use the spot league state directory for the perp league", file=sys.stderr)
        return 2
    journal = Journal(var / "journal" / "events.jsonl")
    notifier = Notifier(None, spot.secrets)  # the watcher journals its alerts itself
    now_ts = int(time.time())
    try:
        cfg = load_perp_config()
        policy = load_perp_policy()
        specs = load_specs(var, [i.kraken_symbol for i in cfg.instruments], now_ts)
        try:
            llm: LlmLeague | None = load_llm_league()
        except LlmConfigError as exc:  # a bad LLM config disables the models, never the risk engine
            llm = None
            notifier.send(
                "action", "perp_llm_config_invalid", f"perp LLM config invalid, models off: {exc}"[:900]
            )
            journal.append(
                "alert",
                {"level": "action", "code": "perp_llm_config_invalid", "message": str(exc)[:1000]},
                now_ts,
            )
        w = PerpWatcher(var, cfg, policy, specs, spot_paths=spot, notifier=notifier, llm=llm)
        rep = w.tick(now_ts)
    except Exception as exc:
        notifier.send(
            "panique", "perp_watcher_crash", f"perp watcher crashed: {type(exc).__name__}: {exc}"[:900]
        )
        with contextlib.suppress(Exception):  # the journal itself may be the problem
            journal.append(
                "alert",
                {
                    "level": "panique",
                    "code": "perp_watcher_crash",
                    "message": f"{type(exc).__name__}: {exc}"[:1000],
                },
                now_ts,
            )
        raise
    print(json.dumps(rep.__dict__, sort_keys=True))
    return 0 if not rep.problems else 3


if __name__ == "__main__":
    sys.exit(main())
