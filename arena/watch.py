"""Continuous watch and event-driven wake-ups (docs/WATCH.md).

`run_watch(paths, clients, now_ts, deciders=None)` is launched every 5 min by `arena-watch.timer`, without an LLM:
1. cycle lock WITHOUT waiting (cycle or wake-up running: exit, nothing written); broken journal: nothing written;
2. tick = `now_ts // tick_s * tick_s`; a `watch` event already journaled for this tick: exit, nothing written;
3. Kraken quotes, checked symbol by symbol (invalid, spread, jump, breakout confirmation); a rejected symbol is
   excluded from the tick;
4. live stops judged on Kraken 1-min candles (2 candles below the stop, price of the last close with slippage and
   fees, never above the stop), idempotent per `order_id`;
5. move trigger (1-min candles, at the last two ticks) and guards; if a wake-up starts, `wakeup_started` is written
   BEFORE the `watch` event and before any network call of the wake-up;
6. `watch` event (timestamped at the tick), then the wake-up: a decision round (LLM and random) replayed by
   `_Runner` (subclass `_WakeupRunner`), under the same lock. An interrupted wake-up is resumed by a later tick
   within 30 min (if no cycle has completed since), otherwise repaired and then abandoned (`wakeup_abandoned`).

The wake-up never writes an `equity` event; its identifier (`wakeup` = tick) fills the `cycle` field of the
decision events, and its quotes are journaled as `wakeup_quote`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any, NamedTuple

from arena import season
from arena.config import Config, ConfigError, load_config, load_instruments
from arena.cycle import (
    RANDOM,
    DAY_S,
    Clients,
    CycleAbort,
    CycleBusy,
    EventLog,
    JournalBroken,
    _Runner,
    cycle_lock,
)
from arena.data import DataError, RateLimitedError
from arena.data.kraken import KrakenError
from arena.data.store import BarStore
from arena.deciders.llm import prompt_sha256
from arena.journal import Journal, intent_from_payload, verify
from arena.ledger import equity_ueur, replay, retired_portfolios
from arena.ops.heartbeat import Heartbeat
from arena.ops.notify import Notifier
from arena.paths import Paths
from arena.risk.policy import Policy, PolicyError, load_policy
from arena.sim.executor import SimExecutor
from arena.types import Bar, Instrument, Quote

log = logging.getLogger("arena.watch")

BP = 10_000
WAKEUP_ABANDON_S = 1800  # an interrupted wake-up is resumed for 30 min, then abandoned
FAILURES_BEFORE_ALERT = 3
SPREAD_WINDOW = 20  # valid quotes used for the median spread
SPREAD_MIN_HISTORY = 5
SPREAD_MULTIPLE = 5
JUMP_MAX_PCT = 15  # a mid that deviates 15% or more from the last valid quote is discarded
JUMP_HORIZON_S = 1800
CONSISTENCY_PCT = 2  # two rejected quotes whose mids are within 2% of each other confirm each other
REJECTED_BEFORE_ALERT = 3
CONFIRMATION_RUN_MAX = 6  # consecutive ticks accepted by breakout confirmation (30 min); beyond that, rejection
MINUTE_S = 60
OHLC_SINCE_S = 81 * 60  # 1-min candles read per tick: 1 h + 15 min tolerance + the previous tick (5 min)
REF_TOLERANCE_S = 900  # move reference candle: the last traded candle at tick - window or earlier, within 15 min
OHLC_FAILURES_MIN = 3  # symbols failing OHLC, over 3 consecutive ticks: watch_ohlc alert
PAUSE_OHLC_DEFAULT_S = 300
#: Cap on the OHLC call pause: a longer Retry-After (beyond 10 min) is brought down to this cap and alerted; the
#: watch must never go hours without stops or trigger on the strength of a single header.
PAUSE_OHLC_MAX_S = 600
STALE_CANDLE_S = 900  # last closed candle older than 15 min: no measurement
CONFIRMATION_S = 600  # the previous tick (stops, move) must be at most 10 min old
REFERENCE_TOLERANCE_S = 900  # move reference: valid quote at tick - window or earlier, at most 15 min old
JOURNAL_BROKEN_ALERT_S = 3600


# ---------------------------------------------------------------------------------------- report


@dataclass
class WatchReport:
    status: str  # done | already_done | inactive | busy | refused | failed | wakeup_failed
    tick: int | None = None
    n_events: int = 0  # events added to the journal by this run
    stops: list[str] = field(default_factory=list)  # order_id of this tick's stops
    rejected: dict[str, str] = field(default_factory=dict)  # symbol -> reason the quote was discarded
    confirmed: list[str] = field(default_factory=list)  # symbols accepted by breakout confirmation
    trigger: dict[str, Any] | None = None  # trigger evaluated (even if refused)
    refused: str | None = None  # guard that refused the wake-up
    wakeup: str | None = None  # None | completed | resumed | abandoned
    alerts: list[tuple[str, str]] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("done", "already_done", "inactive", "busy")


# ---------------------------------------------------------------------------------------- pure functions

class HistEntry(NamedTuple):
    """One symbol at a past tick, reread from the `watch` events."""

    tick: int
    bid: int | None  # raw quote (None: invalid quote, not journaled)
    ask: int | None
    acc: bool  # accepted (in `quotes`)
    flag: str | None  # rejection reason (spread, jump, invalid, error...), "is_confirmed" if accepted by breakout, else None


Hist = dict[str, list[HistEntry]]


def next_scheduled_round(ts: int, interval_s: int, cycle_delay_s: int) -> int:
    """First execution instant of a cycle (HH:05 UTC) strictly after `ts`."""
    return (ts - cycle_delay_s) // interval_s * interval_s + interval_s + cycle_delay_s


def _mid(bid: int, ask: int) -> int:
    return (bid + ask) // 2


def quote_valid(bid: Any, ask: Any) -> bool:
    return all(isinstance(x, int) and not isinstance(x, bool) for x in (bid, ask)) and 0 < bid <= ask


def build_hist(watches: list[dict[str, Any]]) -> Hist:
    """Per-symbol history from the `watch` events (ascending). Events without `raw_quotes` (old format) only
    yield their accepted quotes."""
    hist: Hist = {}
    for pl in sorted(watches, key=lambda p: p["tick"]):
        raw, acc = pl.get("raw_quotes") or pl["quotes"], pl["quotes"]
        rejected, confirmed = pl.get("rejected", {}), pl.get("confirmed", [])
        for sym in sorted(set(raw) | set(rejected) | set(acc)):
            b, a = raw.get(sym, (None, None)) if sym in raw else acc.get(sym, (None, None))
            flag = "is_confirmed" if sym in confirmed else rejected.get(sym)
            hist.setdefault(sym, []).append(HistEntry(pl["tick"], b, a, sym in acc, flag))
    return hist


def classify_quote(
    bid: Any, ask: Any, hist: list[HistEntry], tick: int, close: int | None = None
) -> tuple[str | None, bool]:
    """(rejection reason, accepted by breakout confirmation).

    - `invalid`: always rejected.
    - `spread`: spread > 5 x the median of the symbol's last 20 RAW spreads (at least 5).
    - `jump`: mid 15% or more away from the last accepted quote under 30 min old, otherwise from the last 4 h close.
    - A quote rejected for spread or jump is ACCEPTED if the previous tick (within 10 min) was also rejected for
      spread or jump (or accepted by confirmation) and the two raw mids are within 2%.
    """
    if not quote_valid(bid, ask):
        return "invalid", False
    flag = None
    spreads = sorted(e.ask - e.bid for e in [e for e in hist if e.bid is not None][-SPREAD_WINDOW:])
    if len(spreads) >= SPREAD_MIN_HISTORY and ask - bid > SPREAD_MULTIPLE * spreads[len(spreads) // 2]:
        flag = "spread"
    acc = [e for e in hist if e.acc]
    ref = _mid(acc[-1].bid, acc[-1].ask) if acc and tick - acc[-1].tick < JUMP_HORIZON_S else close
    if flag is None and ref and ref > 0 and abs(_mid(bid, ask) - ref) * 100 >= JUMP_MAX_PCT * ref:
        flag = "jump"
    if flag is None:
        return None, False
    prev = previous(hist, tick)
    run = 0  # consecutive breakout ticks already seen (rejected or accepted by confirmation)
    for e in reversed(hist):
        if e.flag not in ("spread", "jump", "is_confirmed"):
            break
        run += 1
    if prev is not None and run <= CONFIRMATION_RUN_MAX and prev.flag in ("spread", "jump", "is_confirmed") and (prev.flag == "is_confirmed" or not prev.acc):
        pm = _mid(prev.bid, prev.ask)
        if pm > 0 and abs(_mid(bid, ask) - pm) * 100 < CONSISTENCY_PCT * pm:
            return None, True
    return flag, False


def previous(hist: list[HistEntry], tick: int) -> HistEntry | None:
    """Quote (raw, accepted or not) of this symbol's previous tick, within 10 min."""
    prev = [h for h in hist if h.tick < tick and h.bid is not None]
    return prev[-1] if prev and tick - prev[-1].tick <= CONFIRMATION_S else None


def _exceeds(mid: int, ref_mid: int, threshold_bp: int) -> bool:
    return ref_mid > 0 and abs(mid - ref_mid) * BP >= threshold_bp * ref_mid


def closed_candles(bars: list[Bar], tick: int) -> list[Bar]:
    """1-min candles closed at the tick (ts + 60 <= tick), sorted."""
    return sorted((b for b in bars if b.ts + MINUTE_S <= tick), key=lambda b: b.ts)


def candle_variation(bars: list[Bar], tick: int, window_s: int) -> tuple[int, int] | None:
    """(close of the last closed traded candle, close of the last closed traded candle at tick - window or earlier,
    within 15 min), or None. Only candles with volume > 0 count (a filler candle repeats a price); without a recent
    trade (last traded candle older than 15 min), no measurement."""
    closed = [b for b in closed_candles(bars, tick) if b.volume > 0]
    if not closed or tick - (closed[-1].ts + MINUTE_S) > STALE_CANDLE_S:
        return None
    target = tick - window_s
    refs = [b for b in closed if b.ts <= target and target - b.ts <= REF_TOLERANCE_S]
    if not refs:
        return None
    return closed[-1].close, refs[-1].close


def move(
    minute_bars: dict[str, list[Bar]], tick: int, threshold_bp: int, window_s: int, step_s: int
) -> tuple[dict[str, Any] | None, dict[str, int]]:
    """(trigger, variations_bp per symbol) measured on TRADES (1-min candles), never on the ticker.

    Variation = close of the last closed traded candle / close of the last traded candle at tick - window or
    earlier (15 min at most), minus 1.
    The threshold must be exceeded at the current tick AND at the previous tick (tick - step_s, rejudged with its own
    candles), in the same direction. The largest |variation| wins."""
    best: tuple[int, int, str, int] | None = None  # (|d|·1e8/ref, d, symbol, ref)
    variations: dict[str, int] = {}
    for sym in sorted(minute_bars):
        cur = candle_variation(minute_bars[sym], tick, window_s)
        if cur is None:
            continue
        d, rref = cur[0] - cur[1], cur[1]
        if rref <= 0:
            continue
        bp = (abs(d) * BP * 2 + rref) // (2 * rref)
        variations[sym] = bp if d > 0 else -bp
        prev = candle_variation(minute_bars[sym], tick - step_s, window_s)
        if prev is None or prev[1] <= 0:
            continue
        pd = prev[0] - prev[1]
        if not (_exceeds(cur[0], rref, threshold_bp) and _exceeds(prev[0], prev[1], threshold_bp)) or (d > 0) != (pd > 0):
            continue
        score = abs(d) * 10**8 // rref
        if best is None or score > best[0]:
            best = (score, d, sym, rref)
    if best is None:
        return None, variations
    _, d, sym, rref = best
    bp = (abs(d) * BP * 2 + rref) // (2 * rref)
    return {"type": "move", "symbol": sym, "variation_bp": bp if d > 0 else -bp, "window_s": window_s}, variations


def pause_ohlc(exc: BaseException) -> int | None:
    """Seconds to pause OHLC calls if `exc` is a rate limit (HTTP 429 with Retry-After, or EAPI:Rate limit), else
    None. Default: 300 s."""
    if isinstance(exc, RateLimitedError):
        return min(exc.retry_after or PAUSE_OHLC_DEFAULT_S, PAUSE_OHLC_MAX_S)
    if isinstance(exc, KrakenError) and any("Rate limit" in e for e in exc.errors):
        return PAUSE_OHLC_DEFAULT_S
    return None


def _alert_wakeup(
    elog: EventLog, notifier: Notifier, now: int, wakeup: int, level: str, code: str, message: str
) -> bool:
    """Alert tagged "[wakeup N]": only one per wake-up and per code (journal reread)."""
    tag = f"[wakeup {wakeup}] "
    elog.refresh()
    if any(
        e["type"] == "alert" and e["payload"]["code"] == code and e["payload"]["message"].startswith(tag)
        for e in elog.events
    ):
        return False
    notifier.alert(level, code, tag + message, now)
    elog.refresh()
    return True


# ---------------------------------------------------------------------------------------- wake-up


class _WakeupRunner(_Runner):
    """Decision round outside the schedule: same path as the cycle (`_Runner`), minus the stop bars, the reference
    benchmarks and the equity."""

    def __init__(
        self,
        *args: Any,
        cfg: Config,
        policy: Policy,
        instruments: dict[str, Instrument],
        wakeup: int,
        trigger: dict[str, Any],
        quotes: dict[str, Quote],
    ) -> None:
        super().__init__(*args)
        self.cfg, self.policy, self.instruments = cfg, policy, instruments
        self.t = wakeup
        self.trigger = trigger
        self.prefetched_quotes = quotes  # valid quotes of the tick, journaled as `wakeup_quote` before the decision
        self.quote_symbols = set(quotes)
        self.quote_type = "wakeup_quote"
        self.fetch_binance = False  # E0065 does not run at wake-up
        self.reuse_partial_quotes = True  # resume: only the `wakeup_quote` events already written, never rewritten

    def alert(self, level: str, code: str, message: str) -> None:
        if _alert_wakeup(self.log, self.notifier, self.now, self.t, level, code, message):
            self.alerts.append((level, code))

    # -- scope: LLM and random portfolios only
    def _round_portfolios(self) -> tuple[str, ...]:
        return self.llm_portfolios + self._benchmarks_to_run()

    def _benchmarks_to_run(self) -> tuple[str, ...]:
        return (RANDOM,) if RANDOM in self.benchmark_portfolios else ()

    def _snapshot_context(self) -> dict[str, Any]:
        return {
            "type": "wakeup",
            "trigger": self.trigger,
            "next_scheduled_round_ts": next_scheduled_round(self.t, self.cfg.interval_s, self.cfg.cycle_delay_s),
        }

    def _view(self) -> None:
        """As in the cycle, with two differences: a symbol without an accepted quote is valued at its last accepted quote
        (never tradable), and PRICE_SANITY compares against the last TRADE price (close of the last closed 1-min
        candle, read from the `watch` event of the originating tick): a wrong ticker blocks entries."""
        super()._view()
        last_closes = dict(self.market.last_closes)
        origin = next((e["payload"] for e in self._events_of("watch") if e["payload"]["tick"] == self.t), None)
        if origin is not None:
            last_closes.update({s: c for s, c in origin.get("closes_1m", {}).items() if s in self.symbols})
        marks, bids = dict(self.marks), dict(self.bids)
        close = (origin or {}).get("closes_1m", {})
        # Freeze, halt and flattening: each symbol is worth max(accepted bid, 1-min close); a single faulty feed can
        # neither freeze nor halt a portfolio.
        for sym, c in close.items():
            if sym in bids and c > bids[sym]:
                bids[sym] = c
        self._flat_bids = {s: c for s, c in close.items() if s in self.quotes}
        for sym in self.symbols:
            if sym in self.quotes:
                continue
            q = self._last_valid_quote(sym)
            if q is not None:
                marks[sym], bids[sym] = _mid(q[0], q[1]), q[0]
        self.marks, self.bids = marks, bids
        self.market = replace(self.market, last_closes=last_closes, marks=marks)

    def _flatten_quotes(self) -> dict[str, Quote]:
        out = dict(self.quotes)
        for s, c in getattr(self, "_flat_bids", {}).items():
            q = out[s]
            if c > q.bid:
                out[s] = Quote(q.symbol, q.ts, c, max(q.ask, c))
        return out

    def _last_valid_quote(self, sym: str) -> tuple[int, int] | None:
        for e in reversed(self._events_of("watch")):
            if sym in e["payload"]["quotes"]:
                b, a = e["payload"]["quotes"][sym]
                return b, a
        for e in reversed(self._events_of("quote")):
            if e["payload"]["symbol"] == sym:
                return e["payload"]["bid"], e["payload"]["ask"]
        return None

    def run_wakeup(self, resume: bool) -> None:
        """Run or resume wake-up `self.t` (`wakeup_started` is already journaled)."""
        t = self.t
        self.log.refresh()
        self._config_and_portfolios()
        self.symbols = tuple(self.instruments)
        self.executor = SimExecutor(
            self.journal, self.instruments, self.cfg.taker_fee_bp, self.cfg.slippage_bp, self.cfg.venue_mode,
            self.fault_injector,
        )  # fmt: skip
        completed = sorted(e["payload"]["cycle"] for e in self._events_of("cycle_completed"))
        self.prev_cycle = completed[-1] if completed else None
        self.cycle_index = len(completed)
        started = [e for e in self._events_of("wakeup_started") if e["payload"]["wakeup"] == t]
        origin = next((e["payload"] for e in self._events_of("watch") if e["payload"]["tick"] == t), None)
        if resume and origin is not None:  # resume restarts from the accepted quotes of the originating tick
            self.prefetched_quotes = {s: Quote(s, t, b, a) for s, (b, a) in origin["quotes"].items()}
            self.quote_symbols = set(self.prefetched_quotes)
        self._market(True, started[-1]["seq"])
        if resume:
            self.alert("info", "wakeup_resumed", "interrupted wake-up resumed")
            for s, (b, a) in sorted((origin or {"quotes": {}})["quotes"].items()):
                if s not in self.quotes:  # missing wakeup_quote (crash during the write): completed, never ignored
                    self.quotes[s] = Quote(s, t, b, a)
                    self.wn("wakeup_quote", self.quotes[s])
        self._journal_market()
        self._view()
        self._resolve_unknowns()
        self._freeze_halt()
        self._kill_and_dormancy()
        self._decide_and_execute()
        self.wn("wakeup_completed", {"wakeup": t})


# ---------------------------------------------------------------------------------------- tick


class _Watch:
    def __init__(
        self,
        paths: Paths,
        clients: Clients,
        now: int,
        journal: Journal,
        notifier: Notifier,
        deciders: dict[str, Any] | None,
        fault_injector: Any,
        on_portfolio_done: Any,
    ) -> None:
        self.paths, self.clients, self.now = paths, clients, now
        self.journal, self.notifier = journal, notifier
        self.deciders, self.fault_injector, self.on_portfolio_done = deciders, fault_injector, on_portfolio_done
        self.log = EventLog(journal)
        self.alerts: list[tuple[str, str]] = []

    # -- utilities
    def _alert(self, level: str, code: str, message: str) -> None:
        self.notifier.alert(level, code, message, self.now)
        self.log.refresh()
        self.alerts.append((level, code))

    def _of(self, *types: str) -> list[dict[str, Any]]:
        return [e for e in self.log.events if e["type"] in types]

    def _failures(self, new: int | None = None) -> int:
        """Counter of consecutive quote read failures (`var/watch_failures`, outside the journal). Returns the value
        read; `new` writes it (0 deletes the file)."""
        p = self.paths.var / "watch_failures"
        try:
            n = int(p.read_text().strip() or 0)
        except (OSError, ValueError):
            n = 0
        try:
            if new is not None and new != n:
                if new == 0:
                    p.unlink(missing_ok=True)
                else:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(str(new))
        except OSError:
            pass
        return n

    def _pause_ohlc(self, write: int | None = None) -> int:
        """Instant (seconds) until which OHLC calls are suspended (`var/watch_ohlc_pause`)."""
        p = self.paths.var / "watch_ohlc_pause"
        try:
            until = int(p.read_text().strip())
        except (OSError, ValueError):
            until = 0
        if write is not None:
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(str(write))
            except OSError:
                pass
        return until

    # -- tick
    def run(self) -> WatchReport:
        paths = self.paths
        if not verify(paths.journal).ok:
            raise JournalBroken("journal broken")  # nothing is written: the cycle handles the alert
        try:
            cfg = load_config(paths.config)
            policy = load_policy(paths.policy)
        except (ConfigError, PolicyError) as exc:
            return WatchReport("failed", error=f"configuration rejected: {exc}")
        self.cfg, self.policy, v = cfg, policy, cfg.watch
        self.log.refresh()
        n_before = len(self.log.events)
        tick = self.now // v.tick_s * v.tick_s
        if not self._of("cycle_completed"):
            return WatchReport("inactive", tick)  # no cycle yet: the cycle opens the journal, not the watch
        watches = {e["payload"]["tick"]: e["payload"] for e in self._of("watch")}
        if tick in watches:
            return WatchReport("already_done", tick)
        hist = build_hist(list(watches.values()))
        store = BarStore(paths.data, "kraken")
        # Frozen season: computed at the start of the tick. Frozen (different hashes, no waiver): no fill, no wake-up.
        freeze = season.verify_freeze(
            self.log.events,
            {"config_sha256": cfg.sha256_outside_season, "policy_sha256": policy.sha256, "prompt_sha256": prompt_sha256(),
             "code_sha256": season.code_sha256(paths.repo)},
            tick, season.read_waiver(paths),
        )  # fmt: skip
        frozen = freeze.status == "frozen"

        # 1. quotes, checked symbol by symbol
        rejected: dict[str, str] = {}
        confirmed: list[str] = []
        raw: dict[str, tuple[int, int]] = {}
        quotes: dict[str, Quote] = {}
        try:
            instruments = {
                i.symbol: i
                for i in load_instruments(cfg, self.clients.kraken, cache=paths.var / "asset_pairs.json", now=self.now)
            }
            for s, inst in instruments.items():
                h = hist.get(s, [])
                try:
                    q = self.clients.kraken.ticker(s, inst.kraken_pair)
                    acc = [e for e in h if e.acc]
                    close = None
                    if not (acc and tick - acc[-1].tick < JUMP_HORIZON_S):  # stale history: 4 h close from the store
                        bars = store.load(s, cfg.interval_s, tick)
                        close = bars[-1].close if bars else None
                    reason, is_confirmed = classify_quote(q.bid, q.ask, h, tick, close)
                except Exception as exc:  # noqa: BLE001 - an unreadable symbol is discarded, not the whole tick
                    reason, is_confirmed, q = f"error: {type(exc).__name__}", False, None
                if reason != "invalid" and q is not None and not str(reason).startswith("error"):
                    raw[s] = (q.bid, q.ask)
                if reason is None:
                    quotes[s] = q
                    if is_confirmed:
                        confirmed.append(s)
                else:
                    rejected[s] = reason
            if not raw:
                raise DataError("no usable quote: " + ", ".join(f"{s} {m}" for s, m in sorted(rejected.items())))
        except Exception as exc:  # noqa: BLE001 - nothing is written; one alert at the start of the outage
            msg = f"{type(exc).__name__}: {str(exc)[:200]}"
            n = self._failures() + 1
            self._failures(n)
            if n == FAILURES_BEFORE_ALERT:
                self._alert("action", "watch_data", f"watch: Kraken quotes unusable for {n} ticks ({msg})")
            return WatchReport("failed", tick, error=msg, alerts=self.alerts)
        accepted_quotes = {s: (q.bid, q.ask) for s, q in quotes.items()}
        for s in instruments:  # episodes of consecutive rejections for the same symbol
            n_rejected_prev = 0
            for e in reversed(hist.get(s, [])):
                if e.acc:
                    break
                n_rejected_prev += 1
            if s in rejected and n_rejected_prev + 1 == REJECTED_BEFORE_ALERT:
                self._alert("action", "watch_symbol_discarded", f"{s}: quotes discarded for {REJECTED_BEFORE_ALERT} ticks ({rejected[s]})")
            elif s not in rejected and n_rejected_prev >= REJECTED_BEFORE_ALERT:
                self._alert("info", "watch_symbol_discarded", f"{s}: quotes accepted again")

        # 2. trades: closed Kraken 1-min candles (stops and move never read the ticker)
        minute_bars: dict[str, list[Bar]] = {}
        until = self._pause_ohlc()
        rate_limited = self.now < until  # rate limit in effect: no OHLC call before it expires
        for s, inst in instruments.items():
            if rate_limited:
                rejected.setdefault(s, "ohlc")
                continue
            try:
                bars = closed_candles(self.clients.kraken.ohlc(s, inst.kraken_pair, 60, tick - OHLC_SINCE_S), tick)
                if not bars:
                    raise DataError("no 1-min candle")
                minute_bars[s] = bars
            except Exception as exc:  # noqa: BLE001 - no stop and no trigger on this symbol at this tick
                rejected.setdefault(s, "ohlc")
                pause = pause_ohlc(exc)
                if pause is not None:  # HTTP 429 / Rate limit: suspend the OHLC calls
                    self._pause_ohlc(self.now + pause)
                    rate_limited = True
        # No readable candle: the tick counts in var/watch_failures; otherwise (quotes and candles) back to normal.
        if minute_bars:
            if self._failures(0) >= FAILURES_BEFORE_ALERT:
                self._alert("info", "watch_data", "watch: Kraken quotes and candles recovered")
        else:
            n = self._failures() + 1
            self._failures(n)
            if n == FAILURES_BEFORE_ALERT:
                self._alert("action", "watch_data", f"watch: no readable 1-min candle for {n} ticks")
        ohlc_failing_now = sum(1 for m in rejected.values() if m == "ohlc") >= OHLC_FAILURES_MIN
        ohlc_failing_prev = 0
        for past_watch in sorted((e["payload"] for e in self._of("watch")), key=lambda x: x["tick"], reverse=True):
            if sum(1 for m in past_watch.get("rejected", {}).values() if m == "ohlc") < OHLC_FAILURES_MIN:
                break
            ohlc_failing_prev += 1
        if ohlc_failing_now and ohlc_failing_prev + 1 == FAILURES_BEFORE_ALERT:
            self._alert("action", "watch_ohlc", f"watch: 1-min candle read failing for {sum(1 for m in rejected.values() if m == 'ohlc')} symbols for {ohlc_failing_prev + 1} ticks")
        elif not ohlc_failing_now and ohlc_failing_prev >= FAILURES_BEFORE_ALERT:
            self._alert("info", "watch_ohlc", "watch: 1-min candle read recovered")

        # 2 bis. live stops on trades (no fill if the season is frozen)
        executor = SimExecutor(
            self.journal, instruments, cfg.taker_fee_bp, cfg.slippage_bp, cfg.venue_mode, self.fault_injector
        )
        if not frozen:
            executor.process_live_stops(minute_bars, tick, {s: b for s, (b, _a) in raw.items()})
        self.log.refresh()
        suffix = f":watch:{tick}"
        stop_ids = [e["payload"]["order_id"] for e in self._of("fill") if e["payload"]["order_id"].endswith(suffix)]
        rep = WatchReport("done", tick, stops=stop_ids, rejected=rejected, confirmed=confirmed, alerts=self.alerts)
        if frozen and not any(e["payload"]["code"] == "season_frozen" and e["payload"]["message"] == freeze.message for e in self._of("alert")):
            self._alert("panic", "season_frozen", freeze.message)

        # 3 bis. interrupted wake-up: resume, or repair then abandon
        closed = {e["payload"]["wakeup"] for e in self._of("wakeup_completed", "wakeup_abandoned")}
        started = {e["payload"]["wakeup"]: e for e in self._of("wakeup_started")}
        pending = [(r, e) for r, e in sorted(started.items()) if r not in closed]
        last_cycle_seq = max((e["seq"] for e in self._of("cycle_completed")), default=-1)
        resume: tuple[int, dict[str, Any]] | None = None
        for i, (r, e) in enumerate(pending):
            if i == len(pending) - 1 and tick - r <= WAKEUP_ABANDON_S and last_cycle_seq < e["seq"] and not frozen:
                resume = (r, e["payload"]["trigger"])
                continue
            self._abandon(executor, r)
            rep.wakeup = "abandoned"

        # 4. trigger and guards (no new wake-up during a resume)
        launch: dict[str, Any] | None = None
        trigger, variations = move(minute_bars, tick, v.move_threshold_bp, v.move_window_s, v.tick_s)
        if resume is None:
            rep.trigger = trigger
            if trigger is not None and frozen:
                rep.refused = "season_frozen"
            elif trigger is not None:
                rep.refused = self._guards(tick)
                if rep.refused is None:
                    launch = trigger
                    # The wake-up is recorded first: before the `watch` event and before any network call of the wake-up.
                    self.log.add("wakeup_started", {"wakeup": tick, "trigger": trigger}, self.now)

        # 5. watch event, after the stops
        states = replay(self.log.events)
        retired = retired_portfolios(self.log.events)  # `arena retired`: their value is frozen, no more snapshots
        marks = {s: _mid(b, a) for s, (b, a) in accepted_quotes.items()}
        bids = {s: b for s, (b, _a) in accepted_quotes.items()}
        for s in instruments:  # discarded symbol: valued at its last valid quote
            if s not in accepted_quotes:
                acc_h = [e for e in hist.get(s, []) if e.acc]
                last = (acc_h[-1].bid, acc_h[-1].ask) if acc_h else self._last_cycle_quote(s)
                if last is not None:
                    marks[s], bids[s] = _mid(*last), last[0]
        self.log.add(
            "watch",
            {
                "tick": tick,
                "quotes": {s: [b, a] for s, (b, a) in sorted(accepted_quotes.items())},
                "raw_quotes": {s: [b, a] for s, (b, a) in sorted(raw.items())},
                "rejected": dict(sorted(rejected.items())),
                "variations_bp": dict(sorted(variations.items())),
                "closes_1m": {s: b[-1].close for s, b in sorted(minute_bars.items())},
                "confirmed": sorted(confirmed),
                "equity": {p: equity_ueur(st, marks, bids) for p, st in sorted(states.items()) if p not in retired},
                "stops": rep.stops,
                "wakeup": launch,
                "refused": rep.refused,
                "freeze": frozen,
            },
            tick,
        )

        # 6. wake-up
        todo = resume if resume is not None else (tick, launch) if launch is not None else None
        if todo is not None:
            r, trigger = todo
            wakeup_runner = None
            try:
                wakeup_runner = _WakeupRunner(
                    self.paths, self.clients, self.now, self.journal, self.notifier,
                    Heartbeat(self.paths.secrets, self.notifier),
                    self.deciders, self.fault_injector, self.on_portfolio_done,
                    cfg=cfg, policy=policy, instruments=instruments, wakeup=r, trigger=trigger, quotes=quotes,
                )  # fmt: skip
                wakeup_runner.run_wakeup(resume is not None)
                rep.wakeup = "resumed" if resume is not None else "completed"
            except (CycleAbort, DataError) as exc:
                level, code, msg = (
                    (exc.level, exc.code, exc.message) if isinstance(exc, CycleAbort) else ("action", "data_error", str(exc))
                )
                if _alert_wakeup(self.log, self.notifier, self.now, r, level, code, msg):
                    self.alerts.append((level, code))
                rep.status, rep.error = "wakeup_failed", msg
            except Exception as exc:
                log.exception("wake-up interrupted by an unexpected exception")
                msg = f"{type(exc).__name__}: {str(exc)[:300]}"
                if _alert_wakeup(self.log, self.notifier, self.now, r, "panic", "wakeup_exception", msg):
                    self.alerts.append(("panic", "wakeup_exception"))
                rep.status, rep.error = "wakeup_failed", msg
            finally:
                if wakeup_runner is not None:
                    self.alerts.extend(a for a in wakeup_runner.alerts if a not in self.alerts)
        self.log.refresh()
        rep.n_events = len(self.log.events) - n_before
        return rep

    def _last_cycle_quote(self, sym: str) -> tuple[int, int] | None:
        for e in reversed(self._of("quote")):
            if e["payload"]["symbol"] == sym:
                return e["payload"]["bid"], e["payload"]["ask"]
        return None

    def _abandon(self, executor: SimExecutor, r: int) -> None:
        """Repair the interrupted round (fill without stop_set, SUBMITTING/ACKED order), then journal the abandonment."""
        for e in self._of("intent"):
            if e["payload"]["cycle"] == r:
                executor.settle_interrupted(intent_from_payload(e["payload"]), self.now)
        self.log.refresh()
        self.log.add("wakeup_abandoned", {"wakeup": r}, self.now)
        _alert_wakeup(
            self.log, self.notifier, self.now, r, "action", "wakeup_abandoned", "wake-up abandoned (not completed)"
        )
        self.alerts.append(("action", "wakeup_abandoned"))

    def _guards(self, tick: int) -> str | None:
        """Reason of the first guard that refuses a wake-up at this tick, or None."""
        cfg, v = self.cfg, self.cfg.watch
        done = [e["payload"]["cycle"] for e in self._of("cycle_completed")]
        if any(e["payload"]["cycle"] > max(done, default=-1) for e in self._of("cycle_started")):
            return "cycle_incomplete"
        if tick % cfg.interval_s == 0:
            return "cycle"  # the wake-up identifier would collide with a cycle's
        rounds = [e["ts"] for e in self._of("cycle_completed", "wakeup_started", "wakeup_completed", "wakeup_abandoned")]
        if rounds and tick - max(rounds) < v.cooldown_s:
            return "delay"
        today = [e for e in self._of("wakeup_started") if e["payload"]["wakeup"] // DAY_S == tick // DAY_S]
        if len(today) >= v.max_wakeups_per_day:
            return "cap"
        if next_scheduled_round(tick, cfg.interval_s, cfg.cycle_delay_s) - tick < v.pre_cycle_guard_s:
            return "before_cycle"
        return None


# ---------------------------------------------------------------------------------------- entry point


def _alert_journal_broken(paths: Paths, notifier: Notifier, now: int, error: str) -> None:
    """At most one `panic` alert per hour (state in `var/watch_journal_broken`, never in the journal)."""
    p = paths.var / "watch_journal_broken"
    try:
        last = int(p.read_text().strip())
    except (OSError, ValueError):
        last = None
    if last is not None and 0 <= now - last < JOURNAL_BROKEN_ALERT_S:
        return
    notifier.journal_enabled = False  # never write into a broken journal
    notifier.send("panic", "journal_broken", f"journal broken, watch stopped: {error}")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(now))
    except OSError:
        pass


def run_watch(
    paths: Paths,
    clients: Clients,
    now_ts: int,
    *,
    deciders: dict[str, Any] | None = None,
    fault_injector: Any = None,
    on_portfolio_done: Any = None,
    lock_wait_s: float = 0.0,
) -> WatchReport:
    """One watch tick (see the module docstring). Never raises: a failure returns a non-ok report.

    `lock_wait_s` = 0: if a cycle or a wake-up is running, the tick stops without writing anything (status `busy`, ok).
    """
    journal = Journal(paths.journal)
    notifier = Notifier(journal, paths.secrets, clients.http)
    try:
        with cycle_lock(paths, lock_wait_s):
            return _Watch(paths, clients, now_ts, journal, notifier, deciders, fault_injector, on_portfolio_done).run()
    except CycleBusy:
        return WatchReport("busy")
    except JournalBroken as exc:
        _alert_journal_broken(paths, notifier, now_ts, str(exc))
        return WatchReport("refused", error=str(exc))
    except Exception as exc:
        log.exception("watch interrupted by an unexpected exception")
        return WatchReport("failed", error=f"{type(exc).__name__}: {str(exc)[:300]}")
