"""A 4 h cycle end to end, idempotent (docs/SPEC-MVP.md §11).

`run_cycle(paths, clients, now_ts, deciders=None)`:
1. verifies the journal (refuses if it is broken), loads the config and policy (journals `config_loaded` if a hash changes);
2. cycle = `now_ts` rounded down to the start of the 4 h slot; `cycle_completed` already there: exits without writing;
3. data (Kraken 4 h bars, Binance 1 d bars for E0065, quotes), journaled;
4. stops and maximum holding period; 5. freeze / halt / kill switch / dormancy;
6. benchmarks (reference quantity), LLM deciders in parallel, random trader and LLM orders through riskd, simulated execution;
7. bid equity of each portfolio, `cycle_completed`; heartbeat.

Two clocks: `now_ts` (wall clock, for cycle_started/completed, quotes, alerts, config) and `cycle_ts` (decision
time: timestamp of intents, verdicts, orders, fills and equity). The whole decision path is therefore
deterministic and identical when resuming after a crash.

Resume: a `cycle_started` without `cycle_completed` is resumed. Quotes already journaled are reused, LLM
decisions already received are not requested again (re-read from `raw_text`), intents already journaled are
taken as they are (never regenerated), and the executor is idempotent per `intent_id`.
Known limit: a crash between two intent writes of the same batch loses the rest of the batch for that cycle.

Deviations from the spec (flagged): the reference benchmarks (basket, 6040, e0065) are neither frozen nor
halted (they serve as the reference); under the kill switch or dormancy, their buys are refused (KILL_SWITCH)
but their sells go through; the initial Kraken history is 7 days + 2 bars (44 bars) so that the snapshot's
7-day return is defined.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import subprocess
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

from arena import season
from arena.config import Config, ConfigError, load_config, load_instruments
from arena.data import DataError
from arena.data.binance import BinanceClient
from arena.data.kraken import KrakenClient
from arena.data.store import BarStore
from arena.deciders.llm import LLMDecider, SubscriptionDecider, parse_decision, prompt_sha256
from arena.deciders.snapshot import build_snapshot, snapshot_sha256
from arena.journal import Journal, intent_from_payload, verdict_from_payload, verify
from arena.ledger import (
    equity_24h_ago,
    equity_ueur,
    fees_month,
    month_start_ts,
    orders_last_minute,
    positions_value_ueur,
    replay,
    retired_portfolios,
    trades_last_24h,
)
from arena.ops import anthropic_key, dormancy, killswitch
from arena.ops.heartbeat import Heartbeat
from arena.ops.notify import Notifier
from arena.paths import Paths
from arena.risk.policy import Policy, PolicyError, load_policy
from arena.risk.riskd import FROZEN, HALTED, Counters, MarketView, evaluate, freeze_or_halt
from arena.sim.executor import SimExecutor
from arena.sim.fills import market_fill
from arena.benchmarks import BenchmarkContext, random_trader, e0065, basket, reference_qty, sixty_forty
from arena.types import (
    MICRO,
    Bar,
    Instrument,
    Intent,
    PortfolioState,
    Quote,
    Side,
    Verdict,
    notional_ueur,
)

log = logging.getLogger("arena.cycle")

DAY_S = 86_400
HISTORY_S = 7 * DAY_S  # Kraken history of the first run
BINANCE_HISTORY_S = 30 * DAY_S
LLM_TIMEOUT_S = 150.0
UNKNOWN_MAX_CYCLES = 2
SPREAD_WINDOW = 20
LOCK_WAIT_S = 600.0  # a cycle waits for a wake-up or another cycle to finish (docs/WATCH.md §3)
WATCH_ABSENT_S = 1800
FLATTEN_LOCK_WAIT_S = 120.0  # `arena kill --now`: never blocks for more than 2 min

BENCHMARK_MODULES = {
    "benchmark:basket": basket,
    "benchmark:6040": sixty_forty,
    "benchmark:e0065": e0065,
    "benchmark:random": random_trader,
}
REFERENCES = ("benchmark:basket", "benchmark:6040", "benchmark:e0065")
RANDOM = "benchmark:random"


# ---------------------------------------------------------------------------------------- public types


@dataclass
class Clients:
    """Injectable external clients (tests: deterministic doubles)."""

    kraken: Any  # KrakenClient : asset_pairs, ohlc, ticker
    binance: Any  # BinanceClient : klines_1d
    http: httpx.Client | None = None  # heartbeat and ntfy

    @classmethod
    def real(cls) -> Clients:
        return cls(KrakenClient(), BinanceClient(), httpx.Client(timeout=10.0))


@dataclass
class CycleReport:
    status: str  # completed | already_done | stale | busy | refused | failed
    cycle_ts: int | None = None
    n_events: int = 0  # events added to the journal by this run
    n_fills: int = 0
    equity_ueur: dict[str, int] = field(default_factory=dict)
    alerts: list[tuple[str, str]] = field(default_factory=list)  # (level, code)
    error: str | None = None
    resumed: bool = False

    @property
    def ok(self) -> bool:
        return self.status in ("completed", "already_done", "stale")


class CycleAbort(Exception):
    """Planned stop (data unavailable, invalid config): alert of the given level, no traceback."""

    def __init__(self, level: str, code: str, message: str) -> None:
        super().__init__(message)
        self.level, self.code, self.message = level, code, message


class JournalBroken(Exception):
    pass


class CycleBusy(Exception):
    pass


@contextlib.contextmanager
def cycle_lock(paths: Paths, wait_s: float = 0.0) -> Iterator[None]:
    """Exclusive lock: a single cycle (or immediate flatten) at a time."""
    paths.var.mkdir(parents=True, exist_ok=True)
    with open(paths.lock, "a") as f:
        deadline = time.monotonic() + wait_s
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise CycleBusy("another cycle is running") from None
                time.sleep(0.2)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------------------- in-memory journal


class EventLog:
    """Journal + in-memory copy, refreshed by reading the tail of the file (no full re-read)."""

    def __init__(self, journal: Journal) -> None:
        self.journal = journal
        self.events: list[dict[str, Any]] = []
        self._offset = 0

    def refresh(self) -> None:
        p = self.journal.path
        if not p.exists():
            return
        with open(p, "rb") as f:
            f.seek(self._offset)
            data = f.read()
        end = data.rfind(b"\n")
        if end < 0:
            return
        for line in data[: end + 1].splitlines():
            if line.strip():
                self.events.append(json.loads(line))
        self._offset += end + 1

    def add(self, type: str, payload: Any, ts: int) -> dict[str, Any]:
        rec = self.journal.append(type, payload, ts)
        self.refresh()
        return rec


def default_deciders(cfg: Config, paths: Paths) -> dict[str, LLMDecider]:
    """One decider per model in the config.

    decider_backend = "api": Console key read at run time (absent -> no_key).
    decider_backend = "subscription": `claude -p` on the subscription, isolated (see SubscriptionDecider).
    """
    out: dict[str, LLMDecider] = {}
    for m in cfg.models:
        args = (
            m.model,
            m.portfolio,
            (Decimal(m.price_in_uusd_per_mtok) / MICRO, Decimal(m.price_out_uusd_per_mtok) / MICRO),
            Decimal(m.daily_budget_uusd) / MICRO,
        )
        if cfg.decider_backend == "subscription":
            out[m.portfolio] = SubscriptionDecider(*args, workdir=paths.var / "claude-empty")
        else:
            out[m.portfolio] = LLMDecider(*args, key_reader=lambda: anthropic_key(paths))
    return out


def scheduled_round_context(t: int, cfg: Config) -> dict[str, Any]:
    """`context` of a cycle: the next scheduled round is the execution of the following cycle (HH:05 UTC)."""
    return {"type": "scheduled_round", "next_scheduled_round_ts": t + cfg.interval_s + cfg.cycle_delay_s}


def policy_summary(p: Policy) -> str:
    """Risk rules in plain language, given to the model in the snapshot."""

    def pct(bp: int) -> str:
        return f"{bp // 100}" if bp % 100 == 0 else f"{bp / 100:g}"

    return (
        f"Universe: {', '.join(p.symbols)}. Long only, no leverage, market orders. "
        f"A buy is worth at most {pct(p.max_order_bp)}% of equity; a position at most {pct(p.max_position_bp)}%; "
        f"total exposure at most {pct(p.max_exposure_bp)}%. "
        f"{p.max_trades_per_day} trades per 24 h, at least {p.min_interval_same_symbol_s // 3600} h between two buys "
        f"of the same symbol. A stop is mandatory on every buy, between {pct(p.stop_bp_min)}% and {pct(p.stop_bp_max)}%. "
        f"The estimated round-trip cost must stay below {p.max_cost_to_expected_move_pct}% of the expected move "
        f"that you declare. Forced exit after {p.max_holding_s // DAY_S} days. 24 h freeze if the loss reaches "
        f"{pct(p.daily_loss_freeze_bp)}% in 24 h; halt if the drawdown reaches {pct(p.drawdown_halt_bp)}%. "
        f"Minimum order {p.min_order_ueur // MICRO} EUR."
    )


# ---------------------------------------------------------------------------------------- cycle


class _Runner:
    def __init__(
        self,
        paths: Paths,
        clients: Clients,
        now_ts: int,
        journal: Journal,
        notifier: Notifier,
        heartbeat: Heartbeat,
        deciders: dict[str, Any] | None,
        fault_injector: Callable[[str], bool] | None,
        on_portfolio_done: Callable[[str], None] | None,
    ) -> None:
        self.paths, self.clients, self.now = paths, clients, now_ts
        self.journal, self.notifier, self.heartbeat = journal, notifier, heartbeat
        self.log = EventLog(journal)
        self.given_deciders = deciders
        self.fault_injector = fault_injector
        self.on_portfolio_done = on_portfolio_done
        self.alerts: list[tuple[str, str]] = []
        self.retired: frozenset[str] = frozenset()  # read from the journal by `_config_and_portfolios`
        self.t = 0  # cycle_ts
        # Settings that the wake-up round (arena/watch.py) overrides; during a cycle they keep their original values.
        self.prefetched_quotes: dict[str, Quote] | None = None  # quotes of the tick, otherwise Kraken ticker
        self.fetch_binance = True
        self.quote_type = "quote"  # the wake-up journals its quotes as `wakeup_quote` (median spread untouched)
        self.reuse_partial_quotes = False
        self.quote_symbols: set[str] | None = None  # symbols whose quote is expected (None: all)

    # -------------------------------------------------------------- writing

    def w(self, type: str, payload: Any) -> dict[str, Any]:
        """Decision event, timestamped at the cycle time."""
        return self.log.add(type, payload, self.t)

    def wn(self, type: str, payload: Any) -> dict[str, Any]:
        """Event timestamped at wall-clock time."""
        return self.log.add(type, payload, self.now)

    def alert(self, level: str, code: str, message: str) -> None:
        self.notifier.alert(level, code, message, self.now)
        self.log.refresh()
        self.alerts.append((level, code))

    # -------------------------------------------------------------- reading

    def states(self) -> dict[str, PortfolioState]:
        return replay(self.log.events)

    def _events_of(self, *types: str) -> list[dict[str, Any]]:
        return [e for e in self.log.events if e["type"] in types]

    def _git_head(self) -> str:
        try:
            out = subprocess.run(
                ["git", "-C", str(self.paths.repo), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5, check=False,
            )  # fmt: skip
            return out.stdout.strip() or "unknown"
        except (OSError, subprocess.SubprocessError):
            return "unknown"

    # -------------------------------------------------------------- steps

    def run(self) -> CycleReport:
        paths = self.paths
        rep = verify(paths.journal)
        if not rep.ok:
            raise JournalBroken("; ".join(f"{e.code}@{e.line}" for e in rep.errors[:5]))
        try:
            self.cfg = cfg = load_config(paths.config)
            self.policy = load_policy(paths.policy)
        except (ConfigError, PolicyError) as exc:
            raise CycleAbort("panic", "config_invalid", f"configuration refused: {exc}") from exc
        self.log.refresh()
        n_before = len(self.log.events)

        interval = cfg.interval_s
        self.t = t = self.now // interval * interval
        completed = sorted(e["payload"]["cycle"] for e in self._events_of("cycle_completed"))
        if t in completed:
            return CycleReport("already_done", t)
        if completed and t < completed[-1]:
            return CycleReport("stale", t)

        self._config_and_portfolios()
        self._season_freeze()
        self._watch_absent()
        self.instruments = {i.symbol: i for i in load_instruments(cfg, self.clients.kraken)}
        self.symbols = tuple(self.instruments)
        self.executor = SimExecutor(
            self.journal, self.instruments, cfg.taker_fee_bp, cfg.slippage_bp, cfg.venue_mode, self.fault_injector
        )

        started = [e for e in self._events_of("cycle_started") if e["payload"]["cycle"] == t]
        resume = bool(started)
        self.prev_cycle = completed[-1] if completed else None
        self.cycle_index = len(completed)

        self._market(resume, started[-1]["seq"] if started else None)
        if not resume:
            self.wn("cycle_started", {"cycle": t})
        else:
            self.alert("info", "cycle_resumed", f"resuming interrupted cycle {t}")
        self._journal_market()
        self._view()
        self._season_start()

        self._resolve_unknowns()
        self._stops()
        self._kill_and_dormancy()
        self._freeze_halt()
        self._decide_and_execute()
        self._equities()
        self._season_after_equity()
        self.wn("cycle_completed", {"cycle": t})
        self.heartbeat.ping(True, self.now)
        self.log.refresh()
        report = CycleReport(
            "completed",
            t,
            n_events=len(self.log.events) - n_before,
            n_fills=sum(1 for e in self.log.events[n_before:] if e["type"] == "fill"),
            alerts=self.alerts,
            resumed=resume,
        )
        for e in self.log.events:
            if e["type"] == "equity" and e["payload"]["cycle"] == t:
                report.equity_ueur[e["payload"]["portfolio"]] = e["payload"]["equity_ueur"]
        return report

    def _config_and_portfolios(self) -> None:
        cur = {
            "policy_sha256": self.policy.sha256,
            "config_sha256": self.cfg.sha256,
            "prompt_sha256": prompt_sha256(),
        }
        self._claude_version = season.claude_cli_version()
        last = None
        for e in self._events_of("config_loaded"):
            last = e["payload"]
        changed = last is None or any(last.get(k) != v for k, v in cur.items())
        version_change = last is not None and "claude_cli_version" in last and last["claude_cli_version"] != self._claude_version
        if changed or version_change:
            self.wn("config_loaded", {**cur, "git_head": self._git_head(), "claude_cli_version": self._claude_version})
            if version_change:
                self.alert("info", "claude_cli_version", f"claude --version: {last['claude_cli_version']} -> {self._claude_version}")
        opened = {e["payload"]["portfolio"] for e in self._events_of("portfolio_opened")}
        self.retired = retired_portfolios(self.log.events)  # `arena retired`: no longer played or valued, even if listed in the config
        self.llm_portfolios = tuple(m.portfolio for m in self.cfg.models if m.portfolio not in self.retired)
        self.benchmark_portfolios = tuple(p for p in self.cfg.benchmarks.portfolios if p not in self.retired)
        for name, kind in [(p, "llm") for p in self.llm_portfolios] + [(p, "benchmark") for p in self.benchmark_portfolios]:
            if name not in opened:
                self.wn(
                    "portfolio_opened",
                    {"portfolio": name, "kind": kind, "capital_ueur": self.cfg.capital_ueur,
                     "venue_mode": self.cfg.venue_mode},
                )  # fmt: skip
        self.since_ts = self.log.events[0]["ts"]

    # -------------------------------------------------------------- frozen season

    def _season_hashes(self) -> dict[str, str]:
        """Frozen hashes: config WITHOUT the [season] table, policy, system prompt."""
        return {
            "config_sha256": self.cfg.sha256_outside_season,
            "policy_sha256": self.policy.sha256,
            "prompt_sha256": prompt_sha256(),
            "code_sha256": season.code_sha256(self.paths.repo),
        }

    def _season_freeze(self) -> None:
        """Refuses to run if a frozen hash changed during the season, unless a written waiver exists (journaled)."""
        opened, s = season.season_open(self.log.events), self.cfg.season
        if opened is not None and s is not None:  # [season] modified during the open season (except `name`): no effect
            configured = (s.number, s.start_ts, s.duration_days)
            ref = (opened["number"], opened.get("start_ts"), opened.get("duration_days"))
            msg = f"[season] modified during season {opened['number']}: number/start_ts/duration_days = {configured}, expected {ref}; no effect"
            if configured != ref and ref[1] is not None and not any(
                e["payload"]["code"] == "season_modified" and e["payload"]["message"] == msg for e in self._events_of("alert")
            ):
                self.alert("panic", "season_modified", msg)
        g = season.verify_freeze(self.log.events, self._season_hashes(), self.t, season.read_waiver(self.paths))
        if g.status == "frozen":
            raise CycleAbort("panic", "season_frozen", g.message)
        if g.status == "waiver":
            self.wn(
                "season_waiver",
                {"number": g.number, "reason": season.read_waiver(self.paths)[:1000],
                 "hashes_before": g.before, "hashes_after": g.after},
            )  # fmt: skip
            self.alert("action", "season_waiver", f"season {g.number}: waiver journaled ({', '.join(g.diff)})")

    def _season_start(self) -> None:
        """First cycle with t >= start_ts - cycle_delay_s: `season_started` then `season_reference`, before any decision.

        Refused while a season is open (`season_started` without `season_ended`); the number must be the last one + 1.
        `season_reference`: equity of each portfolio AT THE BID with this cycle's quotes, right after `season_started`
        (when resuming after a crash between the two: written before the decisions of the resumed cycle)."""
        s = self.cfg.season
        start = season.season_open(self.log.events)
        if start is None:
            if s is None or self.t < s.start_ts - self.cfg.cycle_delay_s:
                return
            numbers = [e["payload"]["number"] for e in self._events_of("season_started")]
            if s.number in numbers:
                return  # already started (and ended)
            if s.number != max(numbers, default=0) + 1:
                msg = f"season {s.number} refused: the expected number is {max(numbers, default=0) + 1}"
                if not any(e["payload"]["code"] == "season_number" and e["payload"]["message"] == msg for e in self._events_of("alert")):
                    self.alert("action", "season_number", msg)
                return
            self.wn(
                "season_started",
                {"number": s.number, "name": s.name, "cycle": self.t, "planned_cycle_end": self.t + s.duration_days * DAY_S,
                 "start_ts": s.start_ts, "duration_days": s.duration_days,
                 **self._season_hashes(), "git_head": self._git_head(), "claude_cli_version": self._claude_version,
                 "portfolios": list(self.llm_portfolios + self.benchmark_portfolios)},
            )  # fmt: skip
            start = season.season_open(self.log.events)
        if start is not None and not any(e["payload"]["number"] == start["number"] for e in self._events_of("season_reference")):
            eq = {p: self._equity_bid(st) for p, st in sorted(self.states().items())}
            self.wn("season_reference", {"number": start["number"], "cycle": self.t, "equity": eq})

    def _season_after_equity(self) -> None:
        """After the cycle's `equity` events: `season_ended` if the open season is over (t >= planned_cycle_end)."""
        t = self.t
        start = season.season_open(self.log.events)
        if start is not None and t >= start["planned_cycle_end"]:
            eq = {e["payload"]["portfolio"]: e["payload"]["equity_ueur"] for e in self._events_of("equity") if e["payload"]["cycle"] == t}
            self.wn("season_ended", {"number": start["number"], "cycle": t, "equity": dict(sorted(eq.items()))})

    def _watch_absent(self) -> None:
        """Alert (once per absence) if the watch has stopped: last `watch` event more than 30 min old,
        although there has been one before (the timer is supposed to be running)."""
        watches = [e["ts"] for e in self._events_of("watch")]
        if not watches or self.now - max(watches) <= WATCH_ABSENT_S:
            return
        if any(e["payload"]["code"] == "watch_absent" and e["ts"] > max(watches) for e in self._events_of("alert")):
            return
        self.alert("action", "watch_absent", f"no watch tick for {(self.now - max(watches)) // 60} min")

    def _market(self, resume: bool, started_seq: int | None) -> None:
        """Bars and quotes. When resuming, quotes already journaled are reused (disk cache kept)."""
        t, interval = self.t, self.cfg.interval_s
        bound = t // interval * interval  # = t at a cycle; at a wake-up, end of the last bar that must be closed
        self.store = BarStore(self.paths.data, "kraken")
        self.bstore = BarStore(self.paths.data, "binance")
        quotes: dict[str, Quote] = {}
        if resume and started_seq is not None:
            for e in self.log.events:
                if e["type"] == self.quote_type and e["seq"] > started_seq:
                    q = Quote(**{k: e["payload"][k] for k in ("symbol", "ts", "bid", "ask")})
                    quotes[q.symbol] = q
        expected = set(self.symbols) if self.quote_symbols is None else self.quote_symbols
        if self.reuse_partial_quotes:  # wake-up: a round keeps the quotes already written, even if incomplete
            self.quotes_already_journaled = bool(quotes)
        else:
            self.quotes_already_journaled = bool(expected) and expected <= set(quotes)
        if not self.quotes_already_journaled:
            quotes = {}
            for inst in self.instruments.values():

                def fetch(since: int | None, inst: Instrument = inst) -> list[Bar]:
                    start = since if since is not None else t - HISTORY_S - 2 * interval
                    return self.clients.kraken.ohlc(inst.symbol, inst.kraken_pair, interval, start)

                self.store.update(inst.symbol, interval, fetch)
            for inst in self.instruments.values():
                if self.prefetched_quotes is not None:
                    if inst.symbol in self.prefetched_quotes:
                        quotes[inst.symbol] = self.prefetched_quotes[inst.symbol]
                else:
                    quotes[inst.symbol] = self.clients.kraken.ticker(inst.symbol, inst.kraken_pair)
            if self.fetch_binance:
                self._update_binance()
        self.quotes = quotes
        self.bars: dict[str, list[Bar]] = {}
        for sym in self.symbols:
            bars = self.store.load(sym, interval, t)
            if not bars or bars[-1].ts < bound - interval:
                last = bars[-1].ts if bars else None
                raise CycleAbort(
                    "action", "data_stale", f"{sym}: last closed bar {last}, expected {bound - interval}"
                )
            self.bars[sym] = bars

    def _update_binance(self) -> None:
        t = self.t
        try:
            for inst in self.instruments.values():

                def fetch(since: int | None, inst: Instrument = inst) -> list[Any]:
                    start = since if since is not None else t - BINANCE_HISTORY_S
                    return self.clients.binance.klines_1d(inst.binance_symbol, since=start, limit=1000)

                self.bstore.update(inst.binance_symbol, DAY_S, fetch)
        except Exception as exc:  # noqa: BLE001 - E0065 is skipped if data is missing, the rest carries on
            self.alert("action", "binance_data", f"Binance 1 d unavailable: {type(exc).__name__}: {str(exc)[:200]}")

    def _journal_market(self) -> None:
        if not self.quotes_already_journaled:
            for sym in self.symbols:
                if sym in self.quotes:
                    self.wn(self.quote_type, self.quotes[sym])
        last_bar: dict[str, int] = {}
        for e in self._events_of("bar"):
            p = e["payload"]
            last_bar[p["symbol"]] = max(last_bar.get(p["symbol"], 0), p["ts"])
        for sym in self.symbols:
            for b in self.bars[sym]:
                if b.ts > last_bar.get(sym, -1):
                    self.wn("bar", b)

    def _view(self) -> None:
        spreads: dict[str, list[int]] = {s: [] for s in self.symbols}
        for e in self._events_of("quote"):
            p = e["payload"]
            if p["symbol"] in spreads:
                spreads[p["symbol"]].append(p["ask"] - p["bid"])
        medians = {s: sorted(v[-SPREAD_WINDOW:])[len(v[-SPREAD_WINDOW:]) // 2] for s, v in spreads.items() if v}
        self.marks = {s: (q.bid + q.ask) // 2 for s, q in self.quotes.items()}
        self.bids = {s: q.bid for s, q in self.quotes.items()}
        self.market = MarketView(
            quotes=self.quotes,
            last_closes={s: b[-1].close for s, b in self.bars.items()},
            median_spreads_ueur=medians,
            marks=self.marks,
        )

    # -------------------------------------------------------------- UNKNOWN orders

    def _resolve_unknowns(self) -> None:
        last: dict[str, str] = {}
        for e in self._events_of("order_state"):
            last[e["payload"]["order_id"]] = e["payload"]["state"]
        for oid, state in last.items():
            if state == "UNKNOWN":
                self.executor.resolve_unknown(oid, self.t)
        self.log.refresh()
        for p in self._round_portfolios():
            age = self.executor.unknown_age_cycles(p, self.t, self.cfg.interval_s)
            if age > UNKNOWN_MAX_CYCLES:
                self._freeze(p, "unknown_order", f"UNKNOWN order for {age} cycles")

    def _round_portfolios(self) -> tuple[str, ...]:
        """Portfolios involved in the round (all at a cycle; LLM and random at a wake-up)."""
        return self.llm_portfolios + self.benchmark_portfolios

    def _benchmarks_to_run(self) -> tuple[str, ...]:
        return self.benchmark_portfolios

    def _snapshot_context(self) -> dict[str, Any]:
        """`context` field of the snapshot: here the 4 h scheduled round."""
        return scheduled_round_context(self.t, self.cfg)

    def _freeze(self, portfolio: str, reason: str, detail: str) -> None:
        st = self.states()[portfolio]
        until = self.t + self.policy.freeze_duration_s
        if st.frozen_until_ts >= until:
            return
        self.w("portfolio_frozen", {"portfolio": portfolio, "reason": reason, "until_ts": until})
        self.alert("info", "portfolio_frozen", f"{portfolio} frozen until {until} ({detail})")

    # -------------------------------------------------------------- stops

    def _stops(self) -> None:
        interval, t = self.cfg.interval_s, self.t
        since = self.prev_cycle
        bars = {
            s: [b for b in bs if since is not None and b.ts >= since and b.ts + interval <= t]
            for s, bs in self.bars.items()
        }
        self.executor.process_stops_and_expiry(bars, self.quotes, t, self.policy.max_holding_s)
        self.log.refresh()

    # -------------------------------------------------------------- kill switch, dormancy, freeze, halt

    def _kill_and_dormancy(self) -> None:
        sources = killswitch.active_sources(self.paths)
        kill = bool(sources)
        was = False
        for e in self._events_of("kill_switch"):
            was = bool(e["payload"]["active"])
        if kill != was:
            self.wn("kill_switch", {"active": kill, "source": ",".join(sources) or "released"})
            self.alert("action" if kill else "info", "kill_switch", "kill switch active" if kill else "kill switch released")
        age = dormancy.age_s(self.paths, self.now, self.since_ts)
        lvl = dormancy.level(age)
        last_code = "dormancy_ok"
        for e in self._events_of("alert"):
            if e["payload"]["code"].startswith("dormancy_"):
                last_code = e["payload"]["code"]
        code = f"dormancy_{lvl}"
        if code != last_code:
            self.alert("info" if lvl == dormancy.OK else "action", code, f"dormancy: last ack {age // 3600} h ago")
        self.kill, self.dormant = kill, lvl
        self.entries_blocked = kill or lvl != dormancy.OK
        reason = "kill_switch" if kill else "dormancy" if lvl == dormancy.FLATTEN else None
        if reason:
            for p in self.llm_portfolios + (RANDOM,):
                self.executor.flatten(p, self._flatten_quotes(), self.t, reason)
            self.log.refresh()

    def _flatten_quotes(self) -> dict[str, Quote]:
        """Valuation quotes for the flattens (the wake-up corrects them with the trades)."""
        return self.quotes

    def _equity_bid(self, st: PortfolioState) -> int:
        return equity_ueur(st, self.marks, self.bids)

    def _freeze_halt(self) -> None:
        for p in self.llm_portfolios + (RANDOM,):
            if p not in self.states():
                continue
            st = self.states()[p]
            counters = self._counters(p, None, self._equity_bid(st))
            code, until = freeze_or_halt(st, counters, self.policy, self.t)
            if code == HALTED and not st.halted:
                self.w("portfolio_halted", {"portfolio": p, "reason": "drawdown", "until_ts": 0})
                self.alert("action", "portfolio_halted", f"{p} halted (drawdown): review required, `arena resume {p}`")
                self.executor.flatten(p, self._flatten_quotes(), self.t, "halt")
                self.log.refresh()
            elif code == FROZEN and st.frozen_until_ts <= self.t:
                self.w("portfolio_frozen", {"portfolio": p, "reason": "daily_loss", "until_ts": until})
                self.alert("info", "portfolio_frozen", f"{p} frozen until {until} (24 h loss)")

    # -------------------------------------------------------------- riskd counters (from the journal)

    def _counters(self, p: str, intent: Intent | None, eq_now: int) -> Counters:
        ev, t = self.log.events, self.t
        capital = self.cfg.capital_ueur
        ms = month_start_ts(t)
        eq_month, peak, last_eq, halted = capital, capital, None, False
        approved = {e["payload"]["intent_id"] for e in ev if e["type"] == "risk_verdict" and e["payload"]["approved"]}
        last_buy: int | None = None
        for e in ev:
            pl, ty = e["payload"], e["type"]
            if ty == "equity" and pl["portfolio"] == p:
                last_eq = pl["equity_ueur"]
                peak = max(peak, last_eq)
                if e["ts"] <= ms:
                    eq_month = last_eq
            elif ty == "portfolio_halted" and pl["portfolio"] == p:
                halted = True
            elif ty == "portfolio_resumed" and pl["portfolio"] == p:
                if halted and last_eq is not None:
                    peak = last_eq  # after a manual resume from a halt, the peak restarts from the flat equity
                halted = False
            elif (
                intent is not None and ty == "intent" and pl["portfolio"] == p and pl["symbol"] == intent.symbol
                and pl["side"] == "buy" and pl["intent_id"] != intent.intent_id and pl["intent_id"] in approved
            ):  # fmt: skip
                last_buy = e["ts"] if last_buy is None else max(last_buy, e["ts"])
        return Counters(
            trades_24h=trades_last_24h(ev, p, t),
            orders_last_minute=orders_last_minute(ev, t),
            last_symbol_intent_ts=last_buy,
            fees_month_ueur=fees_month(ev, p, t),
            equity_month_start_ueur=eq_month,
            equity_24h_ago_ueur=equity_24h_ago(ev, p, t) or 0,
            equity_peak_ueur=peak,
            equity_now_ueur=eq_now,
        )

    # -------------------------------------------------------------- decisions and execution

    def _spent_today(self, p: str) -> int:
        day = self.t // DAY_S
        return sum(
            e["payload"].get("cost_uusd") or 0
            for e in self._events_of("decision_received")
            if e["payload"]["portfolio"] == p and e["ts"] // DAY_S == day
        )

    def _recent_decisions(self, p: str) -> list[dict]:
        verdicts = {e["payload"]["intent_id"]: e["payload"] for e in self._events_of("risk_verdict")}
        by_cycle: dict[int, list[str]] = {}
        for e in self._events_of("intent"):
            pl = e["payload"]
            if pl["portfolio"] == p:
                v = verdicts.get(pl["intent_id"])
                out = "?" if v is None else "approved" if v["approved"] else "rejected:" + ",".join(v["reasons"])
                by_cycle.setdefault(pl["cycle"], []).append(f"{pl['side']} {pl['symbol']} {pl['size_bp']}bp {out}")
        recent = []
        for e in self._events_of("decision_received"):
            pl = e["payload"]
            if pl["portfolio"] != p or pl["cycle"] == self.t:
                continue
            parsed = pl.get("parsed") or {}
            recent.append(
                {
                    "cycle": pl["cycle"],
                    "llm_round": "scheduled_round" if pl["cycle"] % self.cfg.interval_s == 0 else "wakeup",
                    "actions": [f"{a['side']} {a['symbol']} {a['size_pct']}%" for a in parsed.get("actions", [])],
                    "outcomes": by_cycle.get(pl["cycle"], []),
                    "parse_error": pl.get("parse_error"),
                    "justification": (parsed.get("justification") or "")[:200],
                }
            )
        return recent[-5:]

    def _own_events(self, type: str, p: str) -> list[dict[str, Any]]:
        return [e for e in self._events_of(type) if e["payload"].get("portfolio") == p and e["payload"].get("cycle") == self.t]

    def _decision_skip(self, p: str, reason: str, detail: str | None = None) -> None:
        pl: dict[str, Any] = {"portfolio": p, "cycle": self.t, "reason": reason}
        if detail:
            pl["detail"] = detail[:300]
        self.w("decision_skipped", pl)

    @staticmethod
    def _has_key(decider: Any) -> bool:
        reader = getattr(decider, "_key_reader", None)
        return True if reader is None else bool(reader())

    def _decide_and_execute(self) -> None:
        cfg, t = self.cfg, self.t
        deciders = default_deciders(cfg, self.paths) if self.given_deciders is None else {}
        deciders = {**deciders, **(self.given_deciders or {})}
        pool = ThreadPoolExecutor(max_workers=max(1, len(self.llm_portfolios)), thread_name_prefix="llm")
        futures: dict[Any, str] = {}
        prior_intents: dict[str, Any] = {}  # portfolio -> intents already decided in a previous run
        for p in self.llm_portfolios:
            decider = deciders.get(p)
            if decider is None:
                continue
            received = self._own_events("decision_received", p)
            skipped = self._own_events("decision_skipped", p)
            if received:
                pl = received[-1]["payload"]
                _, _, intents = parse_decision(pl.get("raw_text") or "", p, t, self.symbols)
                prior_intents[p] = intents
                continue
            if skipped:
                continue
            st = self.states()[p]
            if st.halted:
                self._decision_skip(p, "halted")
            elif st.frozen_until_ts > t:
                self._decision_skip(p, "frozen")
            elif self.entries_blocked:
                self._decision_skip(p, "kill_switch", "circuit-breaker" if self.kill else "dormancy")
            else:
                snap = build_snapshot(
                    t, self.bars, st, self.marks, self._recent_decisions(p), policy_summary(self.policy),
                    context=self._snapshot_context(),
                )
                if self._has_key(decider) and not self._own_events("decision_requested", p):
                    self.w(
                        "decision_requested",
                        {"portfolio": p, "cycle": t, "model": decider.model, "snapshot_sha256": snapshot_sha256(snap)},
                    )
                futures[pool.submit(decider.decide, snap, self._spent_today(p))] = p

        # Benchmarks run while the models think.
        for p in self._benchmarks_to_run():
            self._benchmark(p)

        results: dict[str, Any] = {}
        done, not_done = wait(list(futures), timeout=LLM_TIMEOUT_S)
        for fut in done:
            p = futures[fut]
            try:
                results[p] = fut.result()
            except Exception as exc:  # noqa: BLE001
                results[p] = ("skip", "api_error", f"{type(exc).__name__}: {str(exc)[:200]}")
        for fut in not_done:
            fut.cancel()
            results[futures[fut]] = ("skip", "api_error", f"timeout of {int(LLM_TIMEOUT_S)} s exceeded")
        pool.shutdown(wait=False, cancel_futures=True)

        for p in self.llm_portfolios:
            decider = deciders.get(p)
            if decider is None:
                continue
            intents: list[Intent] = prior_intents.get(p, [])
            if p in results:
                res = results[p]
                if isinstance(res, tuple):  # the call failed (exception, timeout)
                    self._decision_skip(p, res[1], res[2])
                    self.alert("action", "llm_api_error", f"{p} : {res[2]}")
                elif res.skipped_reason:
                    self._decision_skip(p, res.skipped_reason, res.error)
                    if res.skipped_reason == "api_error":
                        self.alert("action", "llm_api_error", f"{p} : {res.error}")
                    elif res.skipped_reason == "budget":
                        self.alert("info", "llm_budget", f"{p} : daily budget reached")
                else:
                    self.w(
                        "decision_received",
                        {
                            "portfolio": p, "cycle": t, "model_requested": decider.model,
                            "model_returned": res.model_returned, "raw_text": res.raw_text or "",
                            "parsed": res.parsed, "parse_error": res.parse_error,
                            "input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
                            "cost_uusd": res.cost_uusd, "latency_ms": res.latency_ms,
                        },
                    )  # fmt: skip
                    if res.model_returned and res.model_returned != decider.model:
                        self.alert("action", "model_mismatch", f"{p} : requested {decider.model}, received {res.model_returned}")
                    if res.parse_error:
                        self.alert("info", "parse_error", f"{p} : {res.parse_error}")
                    intents = list(res.intents)
            self._handle(p, intents, reference=False)
            if self.on_portfolio_done:
                self.on_portfolio_done(p)

    def _benchmark(self, p: str) -> None:
        mod = BENCHMARK_MODULES.get(p)
        if mod is None:
            self.alert("action", "unknown_benchmark", f"unknown benchmark in the config: {p}")
            return
        journaled = self._own_events("intent", p)
        if journaled:
            intents = [intent_from_payload(e["payload"]) for e in journaled]
        else:
            state = self.states()[p]
            if p == "benchmark:e0065" and not self._binance_complete():
                self.alert("action", "e0065_data", "incomplete Binance data: E0065 skipped this cycle")
                intents = []
            else:
                intents = mod.decide(self.t, state, self.marks, self._context(p))
        self._handle(p, intents, reference=p in REFERENCES)
        if self.on_portfolio_done:
            self.on_portfolio_done(p)

    def _binance_complete(self) -> bool:
        need = self.t - self.t % DAY_S - DAY_S
        return all(
            (self.bstore.last_ts(i.binance_symbol, DAY_S) or 0) >= need for i in self.instruments.values()
        )

    def _context(self, p: str) -> BenchmarkContext:
        day0 = None
        for e in self._events_of("cycle_started"):
            day0 = e["payload"]["cycle"]
            break
        day0 = (day0 if day0 is not None else self.t) // DAY_S * DAY_S
        return BenchmarkContext(
            cycle_index=self.cycle_index,
            prev_cycle_ts=self.prev_cycle,
            interval_s=self.cfg.interval_s,
            symbols=self.symbols,
            bars_4h=self.bars,
            day_bars={
                i.symbol: self.bstore.load(i.binance_symbol, DAY_S, self.t) for i in self.instruments.values()
            },
            e0065=self.cfg.benchmarks.e0065,
            day0_ts=day0,
            price_path=0,
            min_trade_ueur=self.policy.min_order_ueur,
        )

    def _reference_verdict(self, intent: Intent, st: PortfolioState) -> Verdict:
        if self.entries_blocked and intent.side == Side.BUY:
            return Verdict(intent.intent_id, False, ("KILL_SWITCH",), 0, 0, self.policy.sha256)
        inst, q = self.instruments[intent.symbol], self.quotes[intent.symbol]
        fee_bp, slip = self.cfg.taker_fee_bp, self.cfg.slippage_bp
        qty = reference_qty(intent, st, self.marks, q, inst, fee_bp, slip)
        if qty <= 0:
            return Verdict(intent.intent_id, False, ("REFERENCE", "ZERO_QTY"), 0, 0, self.policy.sha256)
        price, fee = market_fill(intent.side, qty, q, inst, fee_bp, slip)
        reserved = notional_ueur(qty, price, round_up=True) + fee if intent.side == Side.BUY else notional_ueur(qty, price, round_up=False)
        return Verdict(intent.intent_id, True, ("REFERENCE",), qty, reserved, self.policy.sha256)

    def _buy_now_forbidden(self, intent: Intent, st: PortfolioState) -> bool:
        """An approved verdict awaiting execution (crash between verdict and order) is void if, on resume,
        the kill switch, dormancy, a freeze or a halt forbids the entry."""
        started = any(
            e["payload"].get("order_id") == intent.intent_id for e in self._events_of("order_state", "fill")
        )
        return not started and (self.entries_blocked or st.halted or st.frozen_until_ts > self.t)

    def _no_quote(self, intent: Intent) -> None:
        if not any(e["payload"]["intent_id"] == intent.intent_id for e in self._events_of("risk_verdict")):
            self.w("risk_verdict", Verdict(intent.intent_id, False, ("NO_QUOTE",), 0, 0, self.policy.sha256))
        self.executor.reject(intent, "NO_QUOTE", self.t)
        self.log.refresh()

    def _handle(self, p: str, intents: list[Intent], *, reference: bool) -> None:
        """Journals all intents, then verdict and execution of each one (idempotent)."""
        seen = {e["payload"]["intent_id"] for e in self._events_of("intent")}
        for intent in intents:
            if intent.intent_id not in seen:
                self.w("intent", intent)
        for intent in intents:
            st = self.states().get(p)
            if st is None:
                continue
            if intent.symbol not in self.quotes:  # never a silent `continue`: NO_QUOTE verdict and order rejected
                self._no_quote(intent)
                continue
            if not self.entries_blocked and killswitch.active_sources(self.paths):
                self.kill = self.entries_blocked = True  # armed during the LLM call: the buy that follows must be rejected
            verdict = None
            for e in self._events_of("risk_verdict"):
                if e["payload"]["intent_id"] == intent.intent_id:
                    verdict = verdict_from_payload(e["payload"])
            if verdict is not None and verdict.approved and intent.side == Side.BUY and self._buy_now_forbidden(intent, st):
                verdict = None  # approved before a crash, never executed, and entry is forbidden on resume: re-evaluate
            if verdict is None:
                if reference:
                    verdict = self._reference_verdict(intent, st)
                else:
                    verdict = evaluate(
                        intent, st, self.market, self.policy,
                        self._counters(p, intent, self._equity_bid(st)), self.t, self.instruments,
                        self.cfg.taker_fee_bp, self.cfg.slippage_bp, self.entries_blocked,
                    )  # fmt: skip
                self.w("risk_verdict", verdict)
            self.executor.execute(intent, verdict, self.quotes[intent.symbol], self.t)
            self.log.refresh()

    # -------------------------------------------------------------- equity

    def _equities(self) -> None:
        t = self.t
        have = {e["payload"]["portfolio"] for e in self._events_of("equity") if e["payload"]["cycle"] == t}
        for p, st in sorted(self.states().items()):
            if p in have or p in self.retired:  # a retired portfolio keeps its last equity (`portfolio_retired`)
                continue
            pos = positions_value_ueur(st, self.marks, self.bids)
            self.w(
                "equity",
                {"portfolio": p, "cycle": t, "cash_ueur": st.cash_ueur, "positions_value_ueur": pos,
                 "equity_ueur": st.cash_ueur + pos},
            )  # fmt: skip


# ---------------------------------------------------------------------------------------- entry points


def run_cycle(
    paths: Paths,
    clients: Clients,
    now_ts: int,
    *,
    deciders: dict[str, Any] | None = None,
    fault_injector: Callable[[str], bool] | None = None,
    on_portfolio_done: Callable[[str], None] | None = None,
    lock_wait_s: float = LOCK_WAIT_S,
) -> CycleReport:
    """Runs (or resumes) the cycle of `now_ts`. Never raises: a failure returns a non-ok report.

    `deciders`: {portfolio: object with .model and .decide(snapshot, spent_today_uusd)}; by default the
    LLMDeciders of the config. `fault_injector` and `on_portfolio_done` are test hooks.
    """
    journal = Journal(paths.journal)
    notifier = Notifier(journal, paths.secrets, clients.http)
    heartbeat = Heartbeat(paths.secrets, notifier)
    runner: _Runner | None = None
    try:
        with cycle_lock(paths, lock_wait_s):
            runner = _Runner(paths, clients, now_ts, journal, notifier, heartbeat, deciders, fault_injector, on_portfolio_done)
            return runner.run()
    except CycleBusy as exc:
        return CycleReport("busy", error=str(exc))
    except JournalBroken as exc:
        notifier.journal_enabled = False  # never write to a broken journal
        notifier.send("panic", "journal_broken", f"broken journal, cycle refused: {exc}")
        heartbeat.ping(False, now_ts)
        return CycleReport("refused", error=f"broken journal: {exc}")
    except (CycleAbort, DataError) as exc:
        level, code, msg = (
            (exc.level, exc.code, exc.message) if isinstance(exc, CycleAbort) else ("action", "data_error", str(exc))
        )
        notifier.alert(level, code, msg, now_ts)
        heartbeat.ping(False, now_ts)
        return _failed(runner, msg, (level, code))
    except Exception as exc:
        log.exception("cycle interrupted by an unexpected exception")
        msg = f"{type(exc).__name__}: {str(exc)[:300]}"
        notifier.alert("panic", "cycle_exception", f"cycle interrupted: {msg}", now_ts)
        heartbeat.ping(False, now_ts)
        return _failed(runner, msg, ("panic", "cycle_exception"))


def _failed(runner: _Runner | None, msg: str, alert: tuple[str, str]) -> CycleReport:
    rep = CycleReport("failed", runner.t if runner and runner.t else None, error=msg)
    rep.alerts = (runner.alerts if runner else []) + [alert]
    return rep


def flatten_now(paths: Paths, clients: Clients, now_ts: int, *, source: str = "cli") -> CycleReport:
    """Immediate flatten of the LLM and random portfolios at the bid (for `arena kill --now`)."""
    journal = Journal(paths.journal)
    notifier = Notifier(journal, paths.secrets, clients.http)
    try:
        with cycle_lock(paths, FLATTEN_LOCK_WAIT_S):
            if not verify(paths.journal).ok:
                raise JournalBroken("journal verification failed")
            cfg = load_config(paths.config)
            instruments = {i.symbol: i for i in load_instruments(cfg, clients.kraken)}
            elog = EventLog(journal)
            elog.refresh()
            states = replay(elog.events)
            targets = [
                p for p in [m.portfolio for m in cfg.models] + [RANDOM]
                if p in states and states[p].positions
            ]  # fmt: skip
            symbols = sorted({s for p in targets for s in states[p].positions})
            quotes = {s: clients.kraken.ticker(s, instruments[s].kraken_pair) for s in symbols}
            for q in quotes.values():
                elog.add("quote", q, now_ts)
            was = False
            for e in elog.events:
                if e["type"] == "kill_switch":
                    was = bool(e["payload"]["active"])
            if not was:
                elog.add("kill_switch", {"active": True, "source": source}, now_ts)
            ex = SimExecutor(journal, instruments, cfg.taker_fee_bp, cfg.slippage_bp, cfg.venue_mode)
            n = 0
            for p in targets:
                n += len(ex.flatten(p, quotes, now_ts, "kill_switch"))
            notifier.alert("action", "kill_now", f"immediate flatten: {n} fills ({len(targets)} portfolios)", now_ts)
            return CycleReport("completed", now_ts // cfg.interval_s * cfg.interval_s, n_fills=n)
    except CycleBusy as exc:
        return CycleReport("busy", error=str(exc))
    except Exception as exc:
        log.exception("immediate flatten failed")
        msg = f"{type(exc).__name__}: {str(exc)[:300]}"
        notifier.alert("panic", "kill_now_failed", f"immediate flatten failed: {msg}", now_ts)
        return CycleReport("failed", error=msg)


def smoke_snapshot(paths: Paths, clients: Clients, portfolio: str, now_ts: int) -> dict:
    """Current snapshot of a portfolio (real data through the clients) without journaling anything."""
    cfg, policy = load_config(paths.config), load_policy(paths.policy)
    interval = cfg.interval_s
    t = now_ts // interval * interval
    instruments = {i.symbol: i for i in load_instruments(cfg, clients.kraken)}
    store = BarStore(paths.data, "kraken")
    bars: dict[str, list[Bar]] = {}
    marks: dict[str, int] = {}
    for sym, inst in instruments.items():
        store.update(
            sym, interval,
            lambda since, inst=inst: clients.kraken.ohlc(inst.symbol, inst.kraken_pair, interval, since or t - HISTORY_S - 2 * interval),
        )  # fmt: skip
        bars[sym] = store.load(sym, interval, t)  # type: ignore[assignment]
        q = clients.kraken.ticker(sym, inst.kraken_pair)
        marks[sym] = (q.bid + q.ask) // 2
    el = EventLog(Journal(paths.journal))
    el.refresh()
    st = replay(el.events).get(portfolio) or PortfolioState(portfolio, cfg.capital_ueur)
    return build_snapshot(t, bars, st, marks, [], policy_summary(policy), context=scheduled_round_context(t, cfg))
