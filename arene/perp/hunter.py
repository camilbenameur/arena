"""The « Chasseur de mèches » of the derivatives league (docs/SPEC-CHASSEUR.md), paper.

The rule is frozen (docs/recherche-v5/finalistes/chocs_fade-mecheS.py): on each contract, a move of more than 4.5 %
(log) in 5, 15 or 30 minutes is played AGAINST, at 2x the equity with a 5 % stop; out 60 minutes after the entry (or at
the stop); then 60 minutes without a new entry on that contract; one position at a time per contract. On the bench the
gain disappears with the delay (+37.6 % entering at the next minute, -8.1 % five minutes late): speed is the whole
strategy. So this module is a process of its own (`python -m arene.perp.hunter run`, unit arene-perp-hunter.service)
that reads the prices every 5 seconds, not a round of the watcher.

Two portfolios, one process, one price history:
- `robot-perp:chasseur`: acts on the first reading that shows a shock;
- `benchmark-perp:chasseur-5min`, the witness: the same rule, the same execution path, but it decides only once per
  slice of 5 minutes (on the first reading at HH:MM:30 or later, MM = a multiple of 5 plus 3, the watcher's real
  delay). The gap between the two measures what the speed brings.

Execution is the standard path of the other players: `parse_decision`, then `run_intents(..., shrink=True)`, on a
`PerpSimulator` on the league's journal. The simulator's own lock serialises the writes; the hunter never takes the
watcher's lock (a watcher tick blocked by a model call must never delay an entry). Order ids are deterministic
(portfolio, contract, time of the shock): a decision replayed after a crash never goes twice.

The state (position, last entry) is read back from the journal and the ledger at start, so a restart forgets nothing
but the price history, which is primed from the one-minute candles. The watcher stays master of the minutes (stops,
funding, margin calls, `perp_equity`) and of the controls the hunter does not do itself (halt at -60 %, kill switch).
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import math
import sys
import time
import tomllib
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from arene.journal import Journal
from arene.ops import dormance, killswitch
from arene.paths import REPO, Paths
from arene.perp.agent import parse_decision
from arene.perp.agent_round import run_intents
from arene.perp.config import default_var, load_perp_config
from arene.perp.kraken_futures import KrakenFuturesClient
from arene.perp.ledger import BP
from arene.perp.market import market_view
from arene.perp.policy import AGGRESSIVE, PerpPolicy, PerpPolicyError, load_perp_policy
from arene.perp.riskd import InstrumentMarket, PerpMarketView
from arene.perp.sim import PerpSimulator
from arene.perp.store import PerpDataStore
from arene.perp.types import InstrumentSpec, PerpTicker

DEFAULT_CONFIG = REPO / "config" / "perp-chasseur.toml"
KIND = "hunter-v1"
RULE = "chocs_fade-mecheS"
PORTFOLIO_PREFIX = "robot-perp:"
BENCHMARK_PREFIX = "benchmark-perp:"
PORTFOLIO_KIND = "robot"  # the `kind` of `portfolio_opened`: the site's group « Robots »
REFRESH_S = 60  # the ledger is read again at least this often (a stop-out is noticed within a minute)
SILENT_ALERT_S = 600  # no reading for this long: an alert (at most one per 6 hours)
ALERT_EVERY_S = 6 * 3600
ERROR_BACKOFF_S = 30
EXIT_RETRY_S = 30  # a planned close that did not go through is tried again after this long


class HunterConfigError(ValueError):
    """Missing, unreadable or inconsistent hunter configuration (fail closed: the process does not start)."""


@dataclass(frozen=True)
class HunterConfig:
    enabled: bool
    portfolio: str
    name: str
    benchmark: str
    benchmark_name: str
    policy: PerpPolicy
    instruments: tuple[str, ...]
    shock_bp: int
    windows_min: tuple[int, ...]
    size_pct: str
    stop_pct: str
    hold_min: int
    lock_min: int
    horizon_h: int
    expected_move_bp: int
    expected_move_source: str
    poll_s: int
    history_min: int
    max_ref_gap_s: int
    retry_after_refusal_s: int
    witness_period_s: int
    witness_offset_s: int
    fx_max_age_s: int
    heartbeat_s: int
    sha256: str

    @property
    def names(self) -> tuple[str, str]:
        return (self.portfolio, self.benchmark)

    @property
    def hold_s(self) -> int:
        return self.hold_min * 60

    @property
    def lock_s(self) -> int:
        return self.lock_min * 60

    @property
    def threshold(self) -> float:
        return self.shock_bp / BP

    @property
    def max_size_pct(self) -> int:
        """The upper bound of `size_pct` given to `parse_decision` (as the council's execution does)."""
        return max(100, self.policy.max_order_bp * 100 // BP)


_KEYS = {
    "kind", "enabled", "portfolio", "name", "benchmark", "benchmark_name", "policy", "instruments", "shock_bp",
    "windows_min", "size_pct", "stop_pct", "hold_min", "lock_min", "horizon_h", "expected_move_bp",
    "expected_move_source", "poll_s", "history_min", "max_ref_gap_s", "retry_after_refusal_s", "witness_period_s",
    "witness_offset_s", "fx_max_age_s", "heartbeat_s",
}  # fmt: skip


def _int(data: Mapping[str, Any], key: str, lo: int, hi: int) -> int:
    v = data[key]
    if type(v) is not int or not lo <= v <= hi:
        raise HunterConfigError(f"{key}: an integer from {lo} to {hi}")
    return v


def _pct(data: Mapping[str, Any], key: str, lo: int, hi: int) -> str:
    v = data[key]
    try:
        d = Decimal(str(v))
    except InvalidOperation as exc:
        raise HunterConfigError(f"{key}: a decimal text") from exc
    if not isinstance(v, str) or not d.is_finite() or not lo <= d <= hi:
        raise HunterConfigError(f"{key}: a decimal text from {lo} to {hi}")
    return v


def load_hunter_config(path: Path = DEFAULT_CONFIG) -> HunterConfig:
    try:
        raw = path.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise HunterConfigError(f"unreadable {path}: {exc}") from exc
    if set(data) != _KEYS:
        raise HunterConfigError(f"keys: expected {sorted(_KEYS)}, got {sorted(data)}")
    if data["kind"] != KIND:
        raise HunterConfigError(f"kind: {KIND}")
    if type(data["enabled"]) is not bool:
        raise HunterConfigError("enabled is a boolean")
    if not isinstance(data["portfolio"], str) or not data["portfolio"].startswith(PORTFOLIO_PREFIX):
        raise HunterConfigError(f"portfolio must start with {PORTFOLIO_PREFIX}")
    if not isinstance(data["benchmark"], str) or not data["benchmark"].startswith(BENCHMARK_PREFIX):
        raise HunterConfigError(f"benchmark must start with {BENCHMARK_PREFIX}")
    for key in ("name", "benchmark_name"):
        if not isinstance(data[key], str) or not 1 <= len(data[key]) <= 40:
            raise HunterConfigError(f"{key}: a display name of 1 to 40 characters")
    if not isinstance(data["policy"], str) or "/" in data["policy"] or not data["policy"].endswith(".toml"):
        raise HunterConfigError("policy: a file name of config/")
    try:
        policy = load_perp_policy(path.parent / data["policy"], profile=AGGRESSIVE)
    except PerpPolicyError as exc:
        raise HunterConfigError(f"policy: {exc}") from exc
    insts = data["instruments"]
    if not isinstance(insts, list) or not insts or not all(isinstance(i, str) for i in insts):
        raise HunterConfigError("instruments: a non-empty list of contracts")
    if len(set(insts)) != len(insts) or not set(insts) <= set(policy.instruments):
        raise HunterConfigError("instruments: no duplicate, all in the policy's instruments")
    windows = data["windows_min"]
    if not isinstance(windows, list) or not windows or any(type(w) is not int or not 1 <= w <= 60 for w in windows):
        raise HunterConfigError("windows_min: a list of integers from 1 to 60")
    source = data["expected_move_source"]
    if not isinstance(source, str) or len(source) < 20:
        raise HunterConfigError("expected_move_source: where the number was measured (20 characters at least)")
    cfg = HunterConfig(
        enabled=data["enabled"],
        portfolio=data["portfolio"],
        name=data["name"],
        benchmark=data["benchmark"],
        benchmark_name=data["benchmark_name"],
        policy=policy,
        instruments=tuple(insts),
        shock_bp=_int(data, "shock_bp", 100, 2000),
        windows_min=tuple(windows),
        size_pct=_pct(data, "size_pct", 1, 1000),
        stop_pct=_pct(data, "stop_pct", 1, 15),
        hold_min=_int(data, "hold_min", 1, 1440),
        lock_min=_int(data, "lock_min", 0, 1440),
        horizon_h=_int(data, "horizon_h", 1, 168),
        expected_move_bp=_int(data, "expected_move_bp", 1, 3000),
        expected_move_source=source,
        poll_s=_int(data, "poll_s", 1, 60),
        history_min=_int(data, "history_min", 2, 240),
        max_ref_gap_s=_int(data, "max_ref_gap_s", 1, 600),
        retry_after_refusal_s=_int(data, "retry_after_refusal_s", 0, 3600),
        witness_period_s=_int(data, "witness_period_s", 60, 3600),
        witness_offset_s=_int(data, "witness_offset_s", 0, 3599),
        fx_max_age_s=_int(data, "fx_max_age_s", 1, 900),
        heartbeat_s=_int(data, "heartbeat_s", 60, 86_400),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    if cfg.history_min * 60 < max(cfg.windows_min) * 60 + cfg.max_ref_gap_s:
        raise HunterConfigError("history_min: shorter than the longest window plus max_ref_gap_s")
    if cfg.witness_offset_s >= cfg.witness_period_s:
        raise HunterConfigError("witness_offset_s: under witness_period_s")
    return cfg


# ---------------------------------------------------------------------- the rule (pure)


class PriceHistory:
    """The readings of each contract (time, price in µUSD), in time order, kept for `keep_s` seconds."""

    def __init__(self, keep_s: int) -> None:
        self.keep_s = keep_s
        self._ts: dict[str, list[int]] = {}
        self._px: dict[str, list[int]] = {}

    def add(self, inst: str, ts: int, price: int) -> bool:
        """False (and nothing kept) for a reading that is not after the last one or whose price is not positive."""
        if price <= 0:
            return False
        tss, pxs = self._ts.setdefault(inst, []), self._px.setdefault(inst, [])
        if tss and ts <= tss[-1]:
            return False
        tss.append(ts)
        pxs.append(price)
        cut = bisect.bisect_left(tss, ts - self.keep_s)
        if cut > 1:  # one reading before the window stays: the reference of the longest window
            del tss[: cut - 1], pxs[: cut - 1]
        return True

    def at_or_before(self, inst: str, ts: int, max_gap_s: int) -> int | None:
        """The last price read at `ts` or before, None when there is none or when it is older than `max_gap_s`."""
        tss = self._ts.get(inst)
        if not tss:
            return None
        i = bisect.bisect_right(tss, ts) - 1
        if i < 0 or ts - tss[i] > max_gap_s:
            return None
        return self._px[inst][i]

    def last(self, inst: str) -> tuple[int, int] | None:
        tss = self._ts.get(inst)
        return (tss[-1], self._px[inst][-1]) if tss else None

    def __len__(self) -> int:
        return sum(len(v) for v in self._ts.values())


@dataclass(frozen=True)
class Shock:
    instrument: str
    side: int  # +1: a fall, we buy; -1: a rise, we sell
    window_min: int
    move_bp: int  # signed move of the window, in bp (log)
    price_uusd: int
    ts: int


@dataclass(frozen=True)
class Decision:
    kind: str  # "enter" | "exit"
    instrument: str
    shock: Shock | None = None
    opened_ts: int | None = None


def detect_shock(
    hist: PriceHistory, inst: str, now_ts: int, price: int, cfg: HunterConfig
) -> Shock | None:
    """The frozen rule's event: for w in the windows (in order, the later one overriding the earlier), the log
    move from the price at `now - w min` to `price`: under -threshold a buy, over +threshold a sell. A window
    without a reference price (none, or one that is too far in time) does not count."""
    ev: Shock | None = None
    for w in cfg.windows_min:
        ref = hist.at_or_before(inst, now_ts - w * 60, cfg.max_ref_gap_s)
        if ref is None:
            continue
        r = math.log(price / ref)
        if r < -cfg.threshold:
            ev = Shock(inst, 1, w, round(r * BP), price, now_ts)
        elif r > cfg.threshold:
            ev = Shock(inst, -1, w, round(r * BP), price, now_ts)
    return ev


def decide(
    cfg: HunterConfig,
    hist: PriceHistory,
    now_ts: int,
    prices: Mapping[str, int],
    held: Mapping[str, int],
    last_entry: Mapping[str, int],
    not_before: Mapping[str, int] | None = None,
    *,
    slack_s: int = 0,
) -> list[Decision]:
    """What the rule does at `now_ts`. `held`: contract -> time the position was opened; `last_entry`: contract ->
    time of its last entry (the lock runs from it: entry + hold + lock). `prices`: the tradable contracts' current
    price. A position whose hold is over is closed (exits come first); a free, unlocked contract with a shock is
    entered. `slack_s`: the witness, that decides on a grid, takes the grid's jitter off the hold and the lock."""
    exits: list[Decision] = []
    enters: list[Decision] = []
    for inst in cfg.instruments:
        if inst in held:
            if now_ts >= held[inst] + cfg.hold_s - slack_s:
                exits.append(Decision("exit", inst, opened_ts=held[inst]))
            continue  # one position at a time: a shock is ignored while one is held
        if inst not in prices:
            continue
        le = last_entry.get(inst)
        if le is not None and now_ts < le + cfg.hold_s + cfg.lock_s - slack_s:
            continue
        if now_ts < (not_before or {}).get(inst, 0):
            continue
        s = detect_shock(hist, inst, now_ts, prices[inst], cfg)
        if s is not None:
            enters.append(Decision("enter", inst, shock=s))
    return exits + enters


# ---------------------------------------------------------------------- the process


@dataclass
class Player:
    """One of the two portfolios: its own state, the rule and the execution path are shared."""

    name: str
    witness: bool
    last_entry: dict[str, int] = field(default_factory=dict)
    held: dict[str, int] = field(default_factory=dict)
    not_before: dict[str, int] = field(default_factory=dict)
    done: set[tuple[str, int]] = field(default_factory=set)  # (contract, time of the shock) already played
    exit_retry: dict[str, int] = field(default_factory=dict)  # contract -> not before: a failing exit is not spammed
    refreshed: int = 0
    last_slot: int | None = None
    halted: bool = False


@dataclass
class Stats:
    since_ts: int
    reads_ok: int = 0
    errors: int = 0
    shocks: int = 0
    orders: int = 0
    last_read_ts: int | None = None


class Hunter:
    def __init__(
        self,
        var: Path,
        cfg: HunterConfig,
        specs: Mapping[str, InstrumentSpec],
        client: Any,
        *,
        spot_paths: Paths | None = None,
        sim: PerpSimulator | None = None,
    ) -> None:
        self.var = var
        self.cfg = cfg
        self.specs = dict(specs)
        self.client = client
        self.spot_paths = spot_paths or Paths.from_env()
        self.symbols = list(cfg.instruments)
        from arene.perp.collect import data_root

        self.store = PerpDataStore(data_root(var))
        self.journal = Journal(var / "journal" / "events.jsonl")
        sim_params = load_perp_config().simulation
        self.sim = sim or PerpSimulator(
            self.journal,
            {s: self.specs[s].tick_uusd for s in self.symbols},
            sim_params,
            margin_levels={s: self.specs[s].margin_levels for s in self.symbols},
        )
        self.hist = PriceHistory(cfg.history_min * 60)
        self.players = [Player(cfg.portfolio, False), Player(cfg.benchmark, True)]
        self.stats = Stats(0)
        self._opened_ts = 0
        self._next_heartbeat = 0
        self._last_silent_alert = 0
        self._fx_cache: tuple[int, tuple[int, int, int]] | None = None  # (fetched at, (bid, ask, quote ts))

    # ------------------------------------------------------------------ start

    def start(self, now_ts: int) -> None:
        """Opens the portfolios (idempotent), journals the configuration, reads the state back, primes the prices."""
        for p in self.players:
            self.sim.open_portfolio(p.name, PORTFOLIO_KIND, now_ts)
        self.sim.append_event(
            "hunter_config",
            {
                "portfolio": self.cfg.portfolio,
                "benchmark": self.cfg.benchmark,
                "config_sha256": self.cfg.sha256,
                "policy_sha256": self.cfg.policy.sha256,
                "rule": RULE,
            },
            now_ts,
        )
        self._restore(now_ts)
        self.stats = Stats(now_ts)
        self._next_heartbeat = now_ts + self.cfg.heartbeat_s
        self._last_silent_alert = now_ts
        for p in self.players:  # a witness started mid-slice waits for the next one
            p.last_slot = self._slot(now_ts) if p.witness else None
        self.prime(now_ts)

    def _restore(self, now_ts: int) -> None:
        """The last entry of each contract and the signals already played, from the journal; the positions from the
        ledger. (The lock must survive a restart: it is entry + 120 minutes, whatever happened to the position.)"""
        signals: dict[str, tuple[str, str, int]] = {}  # intent id -> (portfolio, contract, side)
        names = {p.name: p for p in self.players}
        events = self.sim.journal.events()
        self._opened_ts = min((e["ts"] for e in events if e["type"] == "portfolio_opened"), default=now_ts)
        for e in events:
            t, pl = e["type"], e["payload"]
            if t == "hunter_signal" and pl.get("portfolio") in names:
                signals[pl["intent_id"]] = (pl["portfolio"], pl["instrument"], 1 if pl["side"] == "buy" else -1)
                names[pl["portfolio"]].done.add((pl["instrument"], int(pl["ts"])))
            elif t == "perp_fill" and pl.get("reason") == "intent" and pl.get("portfolio") in names:
                sig = signals.get(str(pl["order_id"]).split(":")[0])
                if sig and sig[0] == pl["portfolio"] and sig[1] == pl["instrument"] and pl["qty"] * sig[2] > 0:
                    names[pl["portfolio"]].last_entry[pl["instrument"]] = e["ts"]
        for p in self.players:
            self._refresh(p, now_ts)

    def prime(self, now_ts: int) -> None:
        """The one-minute `trade` candles of the last `history_min` minutes: a restart does not blind the hunter for
        30 minutes. A candle that opens at S closes at S + 60: its close is the price at S + 60."""
        for sym in self.symbols:
            try:
                candles = self.client.candles(
                    "trade", sym, 60, now_ts - self.cfg.history_min * 60 - 60, now_ts
                )
            except Exception as exc:  # noqa: BLE001 (the history then builds up from the readings)
                self.stats.errors += 1
                print(f"hunter: no candles for {sym}: {type(exc).__name__}: {exc}"[:300], file=sys.stderr)
                continue
            for c in sorted(candles, key=lambda c: c.ts):
                self.hist.add(sym, c.ts + 60, c.close)

    # ------------------------------------------------------------------ the loop

    def _slot(self, now_ts: int) -> int:
        return (now_ts - self.cfg.witness_offset_s) // self.cfg.witness_period_s

    def _blocked(self, now_ts: int) -> bool:
        """The kill switch and the dormance block the entries (the watcher flattens)."""
        if killswitch.is_active(self.spot_paths) or (self.var / "KILL").exists():
            return True
        return dormance.level(dormance.age_s(self.spot_paths, now_ts, self._opened_ts)) != dormance.OK

    @staticmethod
    def price_of(t: PerpTicker) -> int:
        """The price of the rule: the last traded price when there is one, else the middle of bid and ask."""
        return t.last_uusd if t.last_uusd else (t.bid_uusd + t.ask_uusd) // 2

    def step(self, now_ts: int | None = None) -> None:
        """One reading and what it decides. Never raises on a network or data problem: counted, tried again."""
        ts = int(time.time()) if now_ts is None else now_ts
        try:
            tickers, problems = self.client.tickers(self.symbols)
        except Exception as exc:  # noqa: BLE001 (a network error never stops the loop)
            self.stats.errors += 1
            self._silent_check(ts)
            print(f"hunter: tickers failed: {type(exc).__name__}: {exc}"[:300], file=sys.stderr)
            return
        if problems:
            self.stats.errors += 1
        usable = {s: t for s, t in tickers.items() if not t.suspended and t.bid_uusd > 0 and t.ask_uusd >= t.bid_uusd}
        if not usable:
            self.stats.errors += 1
            self._silent_check(ts)
            return
        now_ts = ts
        prices = {s: self.price_of(t) for s, t in usable.items()}
        self.stats.reads_ok += 1
        self.stats.last_read_ts = now_ts
        # the decision of a reading is taken BEFORE the reading enters the history: no reference is the reading itself
        for p in self.players:
            try:
                self._play(p, now_ts, usable, prices)
            except Exception as exc:  # noqa: BLE001 (one portfolio's failure never stops the other, nor the loop)
                self.stats.errors += 1
                print(f"hunter: {p.name}: {type(exc).__name__}: {exc}"[:400], file=sys.stderr)
        for s, px in prices.items():
            self.hist.add(s, now_ts, px)
        self._heartbeat(now_ts)

    def _refresh(self, p: Player, now_ts: int) -> None:
        acc = self.sim.states()[p.name]
        p.held = {i: pos.opened_ts for i, pos in acc.positions.items()}
        p.halted = acc.halted or acc.retired
        p.refreshed = now_ts

    def _play(self, p: Player, now_ts: int, tickers: Mapping[str, PerpTicker], prices: Mapping[str, int]) -> None:
        slack = 0
        if p.witness:  # decides on a grid, once per slice
            slot = self._slot(now_ts)
            if p.last_slot is not None and slot <= p.last_slot:
                return
            p.last_slot = slot
            slack = self.cfg.poll_s
            self._refresh(p, now_ts)
        if p.halted and not p.witness:
            self._refresh(p, now_ts)  # a halted portfolio plays no more; resumed by hand, it is noticed
            if p.halted:
                return
        cands = decide(self.cfg, self.hist, now_ts, prices, p.held, p.last_entry, p.not_before, slack_s=slack)
        if not cands and now_ts - p.refreshed < REFRESH_S:
            return
        if not p.witness:
            self._refresh(p, now_ts)  # authoritative state before acting (and every minute, for the stop-outs)
        if p.halted:
            return
        if not cands:
            return
        cands = decide(self.cfg, self.hist, now_ts, prices, p.held, p.last_entry, p.not_before, slack_s=slack)
        for d in cands:
            if d.kind == "exit":
                if now_ts < p.exit_retry.get(d.instrument, 0):
                    continue
                p.exit_retry[d.instrument] = now_ts + EXIT_RETRY_S
                self.exit_position(p, d, now_ts, tickers)
            elif d.shock is not None:
                self.stats.shocks += 1
                self.enter(p, d.shock, now_ts, tickers)

    # ------------------------------------------------------------------ the market view

    def _fx(self, now_ts: int, base: PerpMarketView | None) -> tuple[int, int, int]:
        """EUR/USD (bid, ask, quote time): the collector's last snapshot when it is fresh enough for riskd, else
        Kraken's (asked at most once a minute); the stale one is kept when Kraken fails (riskd then refuses)."""
        if base is not None and base.fx_bid > 0 and now_ts - base.fx_ts <= self.cfg.fx_max_age_s:
            return base.fx_bid, base.fx_ask, base.fx_ts
        if self._fx_cache is not None and now_ts - self._fx_cache[0] < 60:
            return self._fx_cache[1]
        try:
            q = self.client.eurusd()
            fx = (q.bid_uusd_per_eur, q.ask_uusd_per_eur, q.ts)
            self._fx_cache = (now_ts, fx)
            return fx
        except Exception as exc:  # noqa: BLE001
            print(f"hunter: eurusd failed: {type(exc).__name__}: {exc}"[:300], file=sys.stderr)
        if base is not None:
            return base.fx_bid, base.fx_ask, base.fx_ts
        return 0, 0, now_ts  # NO_FX: riskd refuses the entries, a close needs a quote only

    def view(self, tickers: Mapping[str, PerpTicker], now_ts: int) -> PerpMarketView:
        """The `PerpMarketView` of fresh tickers (bid, ask, mark, index, funding and their time); the median spread
        comes from the store, the EUR/USD from the store or Kraken."""
        try:
            base = market_view(self.store, self.symbols, now_ts)
        except Exception as exc:  # noqa: BLE001 (a store problem never blocks a hunt)
            print(f"hunter: store view failed: {type(exc).__name__}: {exc}"[:300], file=sys.stderr)
            base = None
        by: dict[str, InstrumentMarket] = {}
        for sym, t in tickers.items():
            med = base.instruments[sym].median_spread_uusd if base is not None and sym in base.instruments else None
            by[sym] = InstrumentMarket(
                bid_uusd=t.bid_uusd,
                ask_uusd=t.ask_uusd,
                quote_ts=t.ts,
                mark_uusd=t.mark_uusd,
                mark_ts=t.ts,
                index_uusd=t.index_uusd,
                index_ts=t.ts if t.index_uusd is not None else None,
                relative_funding_e12=t.relative_funding_e12,
                funding_ts=t.ts if t.relative_funding_e12 is not None else None,
                median_spread_uusd=med,
            )
        bid, ask, fx_ts = self._fx(now_ts, base)
        return PerpMarketView(by, bid, ask, fx_ts)

    # ------------------------------------------------------------------ orders

    def enter(self, p: Player, shock: Shock, now_ts: int, tickers: Mapping[str, PerpTicker]) -> bool:
        """The signal is journaled (`hunter_signal`) before the order, then the standard path. Returns True when the
        entry was filled. The same (portfolio, contract, time of the shock) is never played twice."""
        key = (shock.instrument, shock.ts)
        if key in p.done:
            return False
        decision = {
            "actions": [
                {
                    "instrument": shock.instrument,
                    "action": "open_long" if shock.side > 0 else "open_short",
                    "size_pct": Decimal(self.cfg.size_pct),
                    "stop_pct": Decimal(self.cfg.stop_pct),
                    "horizon_h": self.cfg.horizon_h,
                    "expected_move_pct": Decimal(self.cfg.expected_move_bp) / 100,
                }
            ],
            "justification": f"{RULE} : choc de {shock.move_bp} bp en {shock.window_min} min",
        }
        _parsed, error, intents = parse_decision(
            decision, p.name, shock.ts, now_ts, max_size_pct=self.cfg.max_size_pct, max_actions=1
        )
        if error is not None or len(intents) != 1:
            raise ValueError(error or "the entry was not understood")
        p.done.add(key)
        self.sim.append_event(
            "hunter_signal",
            {
                "portfolio": p.name,
                "instrument": shock.instrument,
                "side": "buy" if shock.side > 0 else "sell",
                "window_min": shock.window_min,
                "move_bp": shock.move_bp,
                "price_uusd": shock.price_uusd,
                "ts": shock.ts,
                "intent_id": intents[0].intent_id,
                "rule": RULE,
            },
            now_ts,
        )
        view = self.view(tickers, now_ts)
        run_intents(
            self.sim, p.name, intents, view, self.specs, self.cfg.policy, now_ts, lambda: self._blocked(now_ts),
            shrink=True,
        )  # fmt: skip
        self._refresh(p, now_ts)
        pos_ts = p.held.get(shock.instrument)
        if pos_ts is None:  # refused (a verdict says why): tried again later if the shock still holds
            p.not_before[shock.instrument] = now_ts + self.cfg.retry_after_refusal_s
            return False
        p.last_entry[shock.instrument] = pos_ts
        self.stats.orders += 1
        return True

    def exit_position(self, p: Player, d: Decision, now_ts: int, tickers: Mapping[str, PerpTicker]) -> None:
        """The planned close, 60 minutes after the entry (a stop may have closed it before: nothing to do then)."""
        assert d.opened_ts is not None
        decision = {"actions": [{"instrument": d.instrument, "action": "close"}], "justification": f"{RULE} : sortie"}
        _parsed, error, intents = parse_decision(
            decision, p.name, d.opened_ts + self.cfg.hold_s, now_ts, max_actions=1
        )
        if error is not None or len(intents) != 1:
            raise ValueError(error or "the exit was not understood")
        self.sim.append_event(
            "hunter_exit",
            {
                "portfolio": p.name,
                "instrument": d.instrument,
                "opened_ts": d.opened_ts,
                "due_ts": d.opened_ts + self.cfg.hold_s,
                "intent_id": intents[0].intent_id,
            },
            now_ts,
        )
        view = self.view(tickers, now_ts)
        run_intents(
            self.sim, p.name, intents, view, self.specs, self.cfg.policy, now_ts, lambda: self._blocked(now_ts),
            shrink=True,
        )  # fmt: skip
        self.stats.orders += 1
        self._refresh(p, now_ts)

    # ------------------------------------------------------------------ the monitoring

    def _silent_check(self, now_ts: int) -> None:
        """No successful reading for 10 minutes: the hunter is blind. One alert per 6 hours, in the journal."""
        ref = self.stats.last_read_ts or self.stats.since_ts
        if now_ts - ref >= SILENT_ALERT_S and now_ts - self._last_silent_alert >= ALERT_EVERY_S:
            self._last_silent_alert = now_ts
            try:
                self.sim.append_event(
                    "alert",
                    {
                        "level": "action",
                        "code": "perp_hunter_blind",
                        "message": f"the hunter has read no price for {now_ts - ref} s",
                    },
                    now_ts,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"hunter: alert not written: {type(exc).__name__}: {exc}"[:300], file=sys.stderr)

    def _heartbeat(self, now_ts: int) -> None:
        """One `hunter_heartbeat` per hour (never one per reading): the counts since the last one."""
        if now_ts < self._next_heartbeat:
            return
        s = self.stats
        self.sim.append_event(
            "hunter_heartbeat",
            {
                "portfolio": self.cfg.portfolio,
                "since_ts": s.since_ts,
                "reads_ok": s.reads_ok,
                "errors": s.errors,
                "shocks": s.shocks,
                "orders": s.orders,
                "last_read_ts": s.last_read_ts,
                "history_points": len(self.hist),
            },
            now_ts,
        )
        self.stats = Stats(now_ts, last_read_ts=s.last_read_ts)
        self._next_heartbeat = now_ts + self.cfg.heartbeat_s

    def run(self, *, sleep: Callable[[float], None] = time.sleep, max_steps: int | None = None) -> None:
        """The loop: one reading every `poll_s` seconds, for ever. A failure is printed and the loop goes on."""
        self.start(int(time.time()))
        n = 0
        while max_steps is None or n < max_steps:
            n += 1
            t0 = time.monotonic()
            try:
                self.step()
            except Exception as exc:  # noqa: BLE001 (a crash loop would blind the hunter: wait and try again)
                self.stats.errors += 1
                print(f"hunter: step failed: {type(exc).__name__}: {exc}"[:400], file=sys.stderr)
                sleep(ERROR_BACKOFF_S)
                continue
            sleep(max(0.0, self.cfg.poll_s - (time.monotonic() - t0)))


# ---------------------------------------------------------------------- command line


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m arene.perp.hunter")
    ap.add_argument("command", choices=["run"])
    ap.add_argument("--var", type=Path, default=None)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = ap.parse_args(argv)
    var = (args.var or default_var()).resolve()
    spot = Paths.from_env()
    if var == spot.var.resolve() or spot.var.resolve() in var.parents:
        print("refusing to use the spot league state directory for the perp league", file=sys.stderr)
        return 2
    try:
        cfg = load_hunter_config(args.config)
    except HunterConfigError as exc:
        print(f"hunter configuration invalid: {exc}", file=sys.stderr)
        return 2
    if not cfg.enabled:
        print("the hunter is disabled (enabled = false)", file=sys.stderr)
        return 0
    from arene.perp.watcher import load_specs  # here: the watcher imports this module

    client = KrakenFuturesClient()
    specs = load_specs(var, list(cfg.instruments), int(time.time()), client)
    Hunter(var, cfg, specs, client, spot_paths=spot).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
