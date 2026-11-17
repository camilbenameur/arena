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
7. rounds: the 4-hour rendez-vous (02:00, 06:00, ... UTC, away from the spot cycles), and wake-ups when a mark crosses a 2 %-in-1-hour move (the crossing is kept
   pending until the guards allow it or the move fades). A round is done only when `perp_round_done` is
   written: an interrupted round is resumed (its orders and intents are idempotent). The basket is set up and
   rebalanced once per month, the trend decides once per UTC day, each at the first rendez-vous able to.
   The LLM portfolios play the rendez-vous (and the market wake-ups once `wakeups = true`; their alerts, the wake-ups they ask for and the default cadence `cadence_min` in private rounds): their `claude -p` calls run
   in parallel inside the tick, which holds the watcher lock meanwhile (the next ticks skip, then catch up the
   minutes in order). See `arene/perp/llm_league.py`. The Haiku council (`arene/perp/council.py`) plays like
   one more model, under its own policy (`policy_for`: leverage up to 10x, no daily freeze, halt at -90 %) and
   with Kraken's margins in the simulator (`arene/perp/margin.py`).

Everything is written to the league's own journal (`var-perp/journal/events.jsonl`). Exit codes: 0 fine,
3 the tick had failures (listed in `perp_tick`), 1 crash (with a `panique` alert when possible).
"""

from __future__ import annotations

import argparse
import bisect
import contextlib
import dataclasses
import fcntl
import json
import os
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from arene.journal import Journal
from arene.ops import dormance, killswitch
from arene.ops.notify import Notifier
from arene.paths import Paths
from arene.perp import agent_orders as AO
from arene.perp import benchmarks as B
from arene.perp import news as N
from arene.perp import round_quota as RQ
from arene.perp import trend_council as TC
from arene.perp.agent import AgentDecider, Runner, _default_runner
from arene.perp.agent_round import _close_unprotected, _execute
from arene.perp.collect import data_root
from arene.perp.config import PerpConfig, default_var, load_perp_config
from arene.perp.council import CouncilConfig, CouncilConfigError, load_councils_league, retired_portfolios
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
    spent_today_uusd,
)
from arene.perp.margin import leveraged
from arene.perp.market import market_view, worst_half_spread_bp
from arene.perp.mcp_server import usd
from arene.perp.news import NewsConfig, NewsConfigError, load_news_config
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
# Market wake-ups. Time limits lifted on 13/11/2026 (the owner, docs/SPEC-PERP-REVEILS-LIBRES.md): 2 % in 1 h, 15 min
# between two, no daily cap; the rounds per model and day (`rounds_per_day`) are the only limit left.
WAKE_MOVE_BP = 200  # 2 %
WAKE_FADE_BP = 150  # a pending crossing is dropped when the move falls under 1.5 %
WAKE_WINDOW_S = HOUR_S
WAKE_PENDING_S = HOUR_S
WAKE_COOLDOWN_S = 900
# No extra round (market wake-up, alert, asked wake-up) when a rendez-vous falls within the next tick: the
# rendez-vous serves it.
RDV_SERVES_S = TICK_S
# Spot cycles at HH:05 at 00, 04, ... UTC: no perp round starts in the 5 min before one (a round lasts at most
# about 4 min), and none while the spot league holds its cycle lock (a cycle or a spot wake-up running): the
# perp rounds wait for the next tick, so the two leagues never call the models at the same time.
SPOT_CYCLE_S = 4 * HOUR_S
SPOT_CYCLE_OFFSET_S = 300
SPOT_GUARD_BEFORE_S = 300
# Private rounds (alerts, wake-ups asked by the model): served at the first tick allowed, within the hour.
ALERT_PENDING_S = HOUR_S  # a crossed alert waiting longer is no longer served by a wake-up
ASKED_EARLY_S = TICK_S // 2  # an asked wake-up is served by the tick that starts at most 2.5 min before it
ENTRY_MAX_LAG_S = 900  # a crossed entry order is executed only if its crossing minute is under 15 min old
PRIVATE_KINDS = ("alert", "private")  # "alert": the private rounds before 13/11/2026 15:00 UTC (one owner)
NEWS_READ_S = (
    2 * HOUR_S
)  # collected items older than this, never journaled (the watcher was down), are dropped
NEWS_PENDING_S = HOUR_S  # a new announcement calls a model back within the hour, or its next round shows it
RELEASE_LAPSE_S = 1800  # a macro release calls the models back at most 30 min after its call-back time
CALENDAR_WARN_S = 30 * 86_400  # alert when the macro calendar ends within 30 days
ROUND_LATE_S = 1800  # a rendez-vous is run (or resumed) by a tick at most 30 min after its time


def spot_cycle_soon(ts: int) -> bool:
    """True in the SPOT_GUARD_BEFORE_S before a spot cycle."""
    since = (ts - SPOT_CYCLE_OFFSET_S) % SPOT_CYCLE_S  # seconds since the last spot cycle
    return SPOT_CYCLE_S - since <= SPOT_GUARD_BEFORE_S


def spot_busy(lock: Path) -> bool:
    """True while the spot league holds its cycle lock (a cycle, or a spot watcher tick and its wake-up).
    Only tested, never kept: the spot league is never delayed by the perp league."""
    try:
        fd = os.open(lock, os.O_RDONLY)
    except FileNotFoundError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


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
        news: NewsConfig | None = None,
        trend_runner: Runner = _default_runner,
    ) -> None:
        self.var = var
        self.news = news if news is not None and news.enabled else None
        self.cfg = cfg
        self.policy = policy
        self.specs = specs
        self.symbols = [i.kraken_symbol for i in cfg.instruments]
        self.store = PerpDataStore(data_root(var))
        self.journal = Journal(var / "journal" / "events.jsonl")
        self.sim = PerpSimulator(
            self.journal,
            {s: specs[s].tick_uusd for s in self.symbols},
            cfg.simulation,
            margin_levels={s: specs[s].margin_levels for s in self.symbols},
        )
        self.spot_paths = spot_paths or Paths.from_env()
        self.notifier = notifier
        self.llm = llm
        self.decider_factory = decider_factory
        self.round_offset_s = round_offset_s
        self._deferred: dict[str, Any] | None = None
        self._deferred_trend: dict[str, Any] | None = None
        self.trend_runner = trend_runner

    # ------------------------------------------------------------------ helpers

    def policy_for(self, portfolio: str) -> PerpPolicy:
        """The council's own policy for the council (docs/SPEC-PERP-CONSEIL-HAIKU.md §5), the league's for every
        other portfolio. A council whose configuration did not load keeps the league's policy (2x, halt at
        -15 %): stricter, never looser. The shadow of the council v4 plays under the policy of that council."""
        c = self.llm.council(portfolio) if self.llm is not None else None
        if c is not None and leveraged(portfolio):
            return c.policy
        for t in self.llm.trend_councils if self.llm is not None else ():
            if t.trend is not None and portfolio == t.trend.benchmark:
                return t.policy
        return self.policy

    def _trend_names(self) -> set[str]:
        """The portfolios of the councils v4 (the council and its shadow): the engine manages their exits."""
        out: set[str] = set()
        for t in self.llm.trend_councils if self.llm is not None else ():
            out.add(t.portfolio)
            if t.trend is not None:
                out.add(t.trend.benchmark)
        return out

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
        self._deferred_trend = None
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
            if self._deferred_trend is not None:
                self._trend_phase(**self._deferred_trend, rep=rep)
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
        self._journal_news(now_ts, rep)
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
            self._trend_due(now_ts, view, rep, last_minute)
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

    def _journal_news(self, now_ts: int, rep: TickReport) -> None:
        """The items the collector read since the last tick, journaled once each (`news_item`); the journal is
        what the rounds read (docs/SPEC-PERP-ACTUALITES.md §2). Never stops the tick."""
        if self.news is None:
            return
        try:
            items = N.read_items(self.store.root / "news", now_ts - NEWS_READ_S, now_ts)
            events = self._events()
            known = N.journaled_keys(events)
            for it in items:
                if it.get("key") in known:
                    continue
                known.add(it["key"])
                self._append("news_item", it, now_ts)
                rep.notes.append(f"news: {it['kind']} {it['status']}: {it.get('title', '')}"[:200])
            end = self.news.calendar[-1].ts if self.news.calendar else 0
            if end - now_ts < CALENDAR_WARN_S and not any(
                e["type"] == "alert"
                and e["payload"].get("code") == "perp_news_calendar_ending"
                and now_ts - e["ts"] < 86_400
                for e in events
            ):
                self._alert(
                    "action", "perp_news_calendar_ending",
                    "perp league: the macro calendar (config/calendrier-macro.toml) ends within 30 days: "
                    "add the next official dates", now_ts,
                )  # fmt: skip
        except (OSError, ValueError, KeyError, TypeError) as exc:
            rep.problems.append(f"news: {type(exc).__name__}: {exc}"[:300])

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
        triggers: dict[str, dict[str, Any]] | None = None,
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
                policy=self.policy, policy_of=self.policy_for, config_sha256=self.cfg.sha256, round_id=round_id,
                now_ts=now_ts, kind=kind,
                trigger=trigger, entries_blocked=lambda: blocked or self._kill_active(),
                decider_factory=self.decider_factory, refresh=refresh,
                only=None if portfolios is None else set(portfolios), triggers=triggers,
                quota_of=lambda p: self.quota(self._events(), p, now_ts), news=self.news,
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

    # ------------------------------------------------------------------ the council v4

    def _trend_due(self, now_ts: int, view: PerpMarketView, rep: TickReport, cursor: int) -> None:
        """Decides whether the council v4 plays a round at this tick (docs/SPEC-CONSEIL-V4.md §3), and which:
        - `barre`: once per bar close (00:00, 04:00, ... UTC), at the first tick after it;
        - `restauration`: the engine alone, when a brake's validity ended before the next bar;
        - `veto`: a news item, a macro release or a 2 %-in-1-hour move, with the LLM council (coefficients can
          only go down).
        The council ignores the 10-minute cadence and the wake-ups it asks for. The round itself runs after the
        collector's lock is released (`_trend_phase`). One council at most per tick."""
        if self.llm is None or not self.llm.trend_councils:
            return
        cfg = self.llm.trend_councils[0]
        events = self._events()
        end_ts = TC.bar_close(now_ts)
        kind: str | None = None
        trigger: dict[str, Any] | None = None
        if not TC.bar_played(events, cfg.portfolio, end_ts):
            kind = "barre"
        elif TC.expired_brakes(events, cfg.portfolio, now_ts):
            kind = "restauration"
        veto_allowed, why = self._trend_llm_ok(cfg, events, now_ts)
        if kind is None and veto_allowed and TC.latest_engine(events, cfg.portfolio, end_ts) is not None:
            trigger = self._trend_veto_trigger(cfg, events, now_ts, cursor)
            kind = "veto" if trigger is not None else None
        if kind is None:
            return
        if spot_cycle_soon(now_ts) or spot_busy(self.spot_paths.lock):
            rep.notes.append("spot league cycle soon or running: the council v4 waits for the next tick")
            return
        blocked = self._kill_and_dormance(now_ts, view, events, rep)
        self._deferred_trend = {
            "cfg": cfg, "kind": kind, "trigger": trigger, "now_ts": now_ts, "view": view, "blocked": blocked,
            "veto_allowed": veto_allowed and kind != "restauration", "no_veto_reason": why,
        }  # fmt: skip

    def _trend_llm_ok(
        self, cfg: CouncilConfig, events: list[dict[str, Any]], now_ts: int
    ) -> tuple[bool, str | None]:
        """May the council call its LLMs now? (False, why) when the engine must play alone."""
        assert self.llm is not None
        if not self.llm.enabled:
            return False, "llm_league_off"
        model = LlmModel(cfg.portfolio, cfg.president_model, cfg.daily_budget_uusd, council=True)
        if not has_budget(model, events, now_ts):
            return False, "daily_budget"
        return True, None

    def _trend_veto_trigger(
        self, cfg: CouncilConfig, events: list[dict[str, Any]], now_ts: int, cursor: int
    ) -> dict[str, Any] | None:
        """The reason of a veto round, or None: a Kraken announcement or a macro release the council has not
        seen, or a market move of 2 % in an hour (kept pending for an hour). Within the quota, not just after a
        round (15 minutes), and the portfolio not halted."""
        assert self.llm is not None
        name = cfg.portfolio
        st = self.sim.states().get(name)
        if st is not None and st.halted:
            return None
        if self.quota(events, name, now_ts)["extra_left"] <= 0:
            return None
        last = RQ.last_played(events, name)
        if last is not None and now_ts - last < WAKE_COOLDOWN_S:
            return None
        if self.news is not None:
            info: dict[str, Any] = {}
            due = N.due_releases(self.news, last, now_ts, ASKED_EARLY_S, RELEASE_LAPSE_S)
            if due:
                info["releases"] = [{"id": e.id, "label": e.label, "ts": e.ts} for e in due]
            fresh = N.unseen_news(events, last, now_ts, NEWS_PENDING_S)
            if fresh:
                info["announcements"] = [
                    {"kind": n["kind"], "status": n["status"], "title": n.get("title", ""), "key": n["key"]}
                    for n in fresh[-3:]
                ]
            if info:
                return {"kind": "calendar" if due else "news", **info}
        if self.llm.wakeups:
            pend = [
                p for p in events
                if p["type"] == "perp_wake_pending" and now_ts - p["ts"] < WAKE_PENDING_S
                and (last is None or p["ts"] > last)
                and abs(self._move_bp(p["payload"]["instrument"], cursor) or 0) >= WAKE_FADE_BP
            ]  # fmt: skip
            if pend:
                best = max(pend, key=lambda p: abs(p["payload"]["move_bp"]))
                return {"kind": "wakeup", **best["payload"], "pending_ts": best["ts"]}
        return None

    def _trend_phase(
        self,
        *,
        cfg: CouncilConfig,
        kind: str,
        trigger: dict[str, Any] | None,
        now_ts: int,
        view: PerpMarketView,
        blocked: bool,
        veto_allowed: bool,
        no_veto_reason: str | None,
        rep: TickReport,
    ) -> None:
        """One round of the council v4, after the collector's lock: the engine, the shadow, the veto council, the
        orders. Decisions are executed on a market view read again after the calls, as in `_llm_phase`."""
        assert self.llm is not None
        rep.rounds.append(f"trend:{kind}:{TC.bar_close(now_ts)}")
        t0 = time.monotonic()
        events = self._events()
        remaining = cfg.daily_budget_uusd - spent_today_uusd(events, cfg.portfolio, now_ts)
        max_call = int(Decimal(self.llm.max_budget_usd) * 1_000_000)
        slots = (
            threading.BoundedSemaphore(self.llm.councils.max_member_processes) if self.llm.councils else None
        )

        def refresh() -> tuple[PerpMarketView, int] | None:
            now2 = now_ts + int(time.monotonic() - t0)
            v2 = market_view(self.store, self.symbols, now2)
            return (v2, now2) if self._is_fresh(v2, now2) else None

        try:
            res = TC.run_trend_round(
                cfg=cfg,
                kind=kind,
                trigger=trigger,
                now_ts=now_ts,
                var=self.var,
                sim=self.sim,
                store=self.store,
                view=view,
                specs=self.specs,
                config_sha256=self.cfg.sha256,
                entries_blocked=lambda: blocked or self._kill_active(),
                refresh=refresh,
                news=self.news,
                llm_sha256=self.llm.sha256,
                league_sha256=self.llm.councils.sha256 if self.llm.councils else "",
                effort=self.llm.effort,
                ceiling_uusd=max(1, min(max_call, remaining)),
                veto_allowed=veto_allowed,
                no_veto_reason=no_veto_reason,
                runner=self.trend_runner,
                slots=slots,
            )
        except Exception as exc:  # noqa: BLE001 (positions stay as they are; the next tick tries again)
            message = f"trend round {kind}: {type(exc).__name__}: {exc}"[:500]
            rep.problems.append(message)
            self._alert_rearmed(self._events(), "action", "perp_trend_round_failed", message, now_ts)
            return
        rep.notes += res.notes
        rep.problems += res.problems
        if any("trend engine" in p for p in res.problems):
            self._alert_rearmed(
                self._events(), "action", "perp_trend_engine_failed", "; ".join(res.problems)[:900], now_ts
            )
        if res.failed and res.called:
            self._alert_rearmed(
                self._events(), "action", "perp_llm_no_decision",
                f"perp league: the council v4 {kind} round was not decided", now_ts,
            )  # fmt: skip

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
            until = p["minute"] + self.policy_for(p["portfolio"]).freeze_duration_s
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
            if acc.retired:  # archived data: no more measure, no control
                continue
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
                pol = self.policy_for(name)
                if not acc.halted and (peak - eq) * BP >= pol.drawdown_halt_bp * peak:
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
                    and pol.daily_loss_freeze_bp > 0  # 0: no daily freeze (the council)
                    and (ago - eq) * BP >= pol.daily_loss_freeze_bp * ago
                ):
                    until = now_ts + pol.freeze_duration_s
                    self._append(
                        "portfolio_frozen",
                        {"portfolio": name, "reason": "daily_loss", "until_ts": until},
                        now_ts,
                    )
                    self._alert("info", "perp_portfolio_frozen", f"{name}: loss over 24 h, frozen", now_ts)
            except PerpLedgerError as exc:
                rep.problems.append(f"{name} controls: {exc}")
        try:  # the engine of the council v4 manages its own exits: no 7-day cut of its trends
            self.sim.close_expired(now_ts, quotes, fx, portfolios=deciding - self._trend_names())
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
        retired = {n for n, a in self.sim.states().items() if a.retired}
        owners = sorted(
            {e["payload"]["portfolio"] for e in events if e["type"] == "agent_orders_set"} - retired
        )
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
            intent,
            acc,
            view,
            self.specs,
            counters,
            self.policy_for(name),
            self.cfg.simulation,
            now_ts,
            blocked,
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
        # market crossings are recorded at every tick, whatever round runs or waits (served within the hour)
        self._record_crossings(now_ts, cursor, self._events())
        events = self._events()
        started = {e["payload"]["round"]: e["payload"] for e in events if e["type"] == "perp_round"}
        done = {e["payload"]["round"] for e in events if e["type"] == "perp_round_done"}
        rdv = (now_ts - self.round_offset_s) // ROUND_S * ROUND_S + self.round_offset_s
        waits: list[bool] = []

        def may_start() -> bool:
            """For the rounds outside the rendez-vous: none when the rendez-vous falls within the tick (it serves
            them), none just before a spot cycle nor while the spot league holds its lock (tested only here,
            when a round is about to start)."""
            if rdv + ROUND_S - now_ts <= RDV_SERVES_S:
                return False
            if not waits:
                waits.append(spot_cycle_soon(now_ts) or spot_busy(self.spot_paths.lock))
                if waits[0]:
                    rep.notes.append(
                        "spot league cycle soon or running: perp extra rounds wait for the next tick"
                    )
            return not waits[0]

        for rid, r in started.items():  # resume an interrupted round within its window
            if rid not in done and now_ts - r["ts"] < ROUND_LATE_S:
                if r["kind"] != "rendezvous" and not may_start():
                    continue  # another interrupted round, or a rendez-vous due now, may still start
                self._round(
                    rid,
                    r["kind"],
                    r.get("trigger"),
                    now_ts,
                    view,
                    rep,
                    resume=True,
                    portfolios=r.get("portfolios"),
                    triggers=r.get("triggers"),
                )
                return
        if now_ts - rdv < ROUND_LATE_S and rdv not in started:
            self._round(rdv, "rendezvous", None, now_ts, view, rep)
            return
        # one round per tick: a market wake-up first, then the private rounds
        if not self._wakeup(now_ts, view, rep, cursor, events, started, may_start):
            self._private_round(now_ts, view, rep, events, may_start)

    def quota(self, events: list[dict[str, Any]], portfolio: str, now_ts: int) -> dict[str, int]:
        assert self.llm is not None
        return RQ.quota(events, portfolio, now_ts, self.llm.rounds_per_day, self.round_offset_s)

    def _wakeup(
        self,
        now_ts: int,
        view: PerpMarketView,
        rep: TickReport,
        cursor: int,
        events: list[dict[str, Any]],
        started: dict[int, dict[str, Any]],
        may_start: Callable[[], bool],
    ) -> bool:
        """Market wake-ups: a crossing recorded by `_record_crossings` is kept pending for an hour and served
        when the guards allow it. True when a round was started."""
        pend = [e for e in events if e["type"] == "perp_wake_pending" and now_ts - e["ts"] < WAKE_PENDING_S]
        served = {
            r.get("trigger", {}).get("pending_ts")
            for r in started.values()
            if r["kind"] == "wakeup" and r.get("trigger")
        }
        # private rounds count neither in the cooldown of the market wake-ups (common to all)
        last_round = max((r["ts"] for r in started.values() if r["kind"] not in PRIVATE_KINDS), default=0)
        candidates = [
            p
            for p in pend
            if p["ts"] not in served
            and p["ts"] > last_round  # a move recorded at or before the last common round: the models saw it
            and abs(self._move_bp(p["payload"]["instrument"], cursor) or 0) >= WAKE_FADE_BP
        ]
        if not candidates:
            return False
        if now_ts - last_round < WAKE_COOLDOWN_S:
            return False
        portfolios = None
        if self.llm is not None and self.llm.enabled and self.llm.wakeups:
            # the models out of rounds for today (or halted, or out of budget) sit this wake-up out; none left:
            # no wake-up
            states = self.sim.states()
            eligible = [
                m.portfolio
                for m in self.llm.players
                if m.portfolio in states
                and not states[m.portfolio].halted
                and not states[m.portfolio].retired
                and has_budget(m, events, now_ts)
                and self.quota(events, m.portfolio, now_ts)["extra_left"] > 0
            ]
            if not eligible:
                return False
            if len(eligible) < len(self.llm.players):
                portfolios = eligible
        if not may_start():
            return False
        best = max(candidates, key=lambda p: abs(p["payload"]["move_bp"]))
        tick = now_ts // TICK_S * TICK_S
        self._round(
            tick,
            "wakeup",
            {**best["payload"], "pending_ts": best["ts"]},
            now_ts,
            view,
            rep,
            portfolios=portfolios,
        )
        return True

    def _record_crossings(self, now_ts: int, cursor: int, events: list[dict[str, Any]]) -> None:
        """A move of WAKE_MOVE_BP over the hour, newly reached at this tick: `perp_wake_pending`."""
        cursors = [e["payload"]["last_minute"] for e in events if e["type"] == "perp_tick"]
        prev_cursor = cursors[-1] if cursors else None
        for s in self.symbols:
            mv = self._move_bp(s, cursor)
            prev = self._move_bp(s, prev_cursor) if prev_cursor is not None else None
            if mv is not None and abs(mv) >= WAKE_MOVE_BP and (prev is None or abs(prev) < WAKE_MOVE_BP):
                self._append(
                    "perp_wake_pending", {"instrument": s, "move_bp": mv, "window_s": WAKE_WINDOW_S}, now_ts
                )

    def _private_round(
        self,
        now_ts: int,
        view: PerpMarketView,
        rep: TickReport,
        events: list[dict[str, Any]],
        may_start: Callable[[], bool],
    ) -> None:
        """One private round for every model with a crossed alert, a wake-up it asked for that is due, or whose
        default cadence is due (spec §3, docs/SPEC-PERP-CADENCE.md): each plays alone with its own trigger, and
        sees nothing of the others'. A model is served if it is
        not halted, within its budget and has rounds left today; the others wait (within the hour)."""
        if self.llm is None or not self.llm.enabled:
            return
        states = self.sim.states()
        triggers: dict[str, dict[str, Any]] = {}
        for a in AO.unserved_alerts(events, now_ts, ALERT_PENDING_S):  # oldest first: the first one wins
            triggers.setdefault(
                a["portfolio"],
                {
                    "kind": "alert",
                    "alert_id": a["id"],
                    "instrument": a["instrument"],
                    "condition": a["condition"],
                    "price_usd": usd(a["price_uusd"]),
                    "note": a["note"],
                },
            )
        for m in self.llm.players:
            asked = AO.pending_wakeup(events, m.portfolio)
            if asked is None or asked["due_ts"] - now_ts > ASKED_EARLY_S:
                continue
            if now_ts - asked["due_ts"] >= AO.WAKEUP_LAPSE_S:
                continue  # lapsed: shown as such by the dashboard, never served late
            if m.portfolio in triggers:
                triggers[m.portfolio]["asked_wakeup_ts"] = asked["due_ts"]
            else:
                triggers[m.portfolio] = {
                    "kind": "scheduled",
                    "asked_at_round": asked["round"],
                    "due_ts": asked["due_ts"],
                }
        if self.news is not None:
            # the news (docs/SPEC-PERP-ACTUALITES.md §4): a new announcement, or a macro release a few minutes
            # old, calls back every model that has not played since; with another trigger, it is attached to it
            for m in self.llm.players:
                last = RQ.last_played(events, m.portfolio)
                info: dict[str, Any] = {}
                due = N.due_releases(self.news, last, now_ts, ASKED_EARLY_S, RELEASE_LAPSE_S)
                if due:
                    info["releases"] = [{"id": e.id, "label": e.label, "ts": e.ts} for e in due]
                fresh = N.unseen_news(events, last, now_ts, NEWS_PENDING_S)
                if fresh:
                    info["announcements"] = [
                        {
                            "kind": n["kind"],
                            "status": n["status"],
                            "title": n.get("title", ""),
                            "key": n["key"],
                        }
                        for n in fresh[-3:]
                    ]
                if not info:
                    continue
                if m.portfolio in triggers:
                    triggers[m.portfolio]["news"] = info
                else:
                    triggers[m.portfolio] = {"kind": "calendar" if due else "news", **info}
        if self.llm.cadence_min:
            # the cadence (the owner, 13/11 and 14/11): every model is called again at most `cadence_min` after its
            # last round, whatever that round was (a failed one included). A wake-up it asked for can only bring
            # that call forward: one asked for later than the cadence does not delay it.
            for m in self.llm.players:
                if m.portfolio in triggers:
                    continue
                last = RQ.last_played(events, m.portfolio)
                # a player that never played (a council added to the league) is due now, not at the next
                # rendez-vous (docs/SPEC-LIGUE-CONSEILS.md §5)
                due = now_ts if last is None else last + self.llm.cadence_min * 60
                asked = AO.pending_wakeup(events, m.portfolio, now_ts)
                if asked is not None and asked["due_ts"] <= due:
                    continue  # served as `scheduled`, at its own time
                if due - now_ts > ASKED_EARLY_S:
                    continue
                triggers[m.portfolio] = {
                    "kind": "cadence",
                    "every_min": self.llm.cadence_min,
                    "last_round_ts": last,
                }
        models = {m.portfolio: m for m in self.llm.players}
        served = {
            p: t
            for p, t in triggers.items()
            if p in models
            and not (p in states and (states[p].halted or states[p].retired))  # not opened yet: opens in its round
            and has_budget(models[p], events, now_ts)
            and self.quota(events, p, now_ts)["extra_left"] > 0
        }
        if not served or not may_start():
            return
        owners = sorted(served)
        self._round(
            now_ts // TICK_S * TICK_S,
            "private",
            None,
            now_ts,
            view,
            rep,
            portfolios=owners,
            triggers={p: served[p] for p in owners},
        )

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
        triggers: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        if not resume:
            extra: dict[str, Any] = {} if portfolios is None else {"portfolios": portfolios}
            if triggers is not None:
                extra["triggers"] = triggers
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
        private = kind in PRIVATE_KINDS  # only their owners play: no benchmark, no other model
        llm_plays = (
            self.llm is not None
            and self.llm.enabled
            and (kind == "rendezvous" or private or self.llm.wakeups)
        )
        # the random benchmark plays the rounds the models play (wake-ups too only once the models have them)
        if not private and (
            kind == "rendezvous" or self.llm is None or not self.llm.enabled or self.llm.wakeups
        ):
            ok &= self._random(round_id, now_ts, view, quotes, marks, fx, blocked, rep)
        if llm_plays:
            self._deferred = {
                "round_id": round_id, "kind": kind, "trigger": trigger, "now_ts": now_ts, "view": view,
                "blocked": blocked, "ok": ok, "portfolios": portfolios, "triggers": triggers,
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
        if llm is not None:
            llm = llm.without(retired_portfolios(journal.events()))  # a retired model is never played again
            errors: list[str] = []
            try:  # a bad council config disables that council only; a bad league file, the councils only
                councils = load_councils_league().without(retired_portfolios(journal.events()))
                llm = dataclasses.replace(llm, councils=councils)
                errors = list(councils.errors)
            except CouncilConfigError as exc:
                errors = [f"league of the councils: {exc}"]
            for err in errors:
                notifier.send(
                    "action", "perp_council_config_invalid", f"council config invalid, off: {err}"[:900]
                )
                journal.append(
                    "alert",
                    {"level": "action", "code": "perp_council_config_invalid", "message": err[:1000]},
                    now_ts,
                )
        news: NewsConfig | None = None
        try:  # bad news config: no news, never a stopped watcher
            news = load_news_config()
        except (NewsConfigError, OSError) as exc:
            notifier.send("action", "perp_news_config_invalid", f"perp news config invalid, off: {exc}"[:900])
            journal.append(
                "alert",
                {"level": "action", "code": "perp_news_config_invalid", "message": str(exc)[:1000]},
                now_ts,
            )
        w = PerpWatcher(var, cfg, policy, specs, spot_paths=spot, notifier=notifier, llm=llm, news=news)
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
