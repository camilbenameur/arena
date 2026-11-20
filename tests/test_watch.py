"""Continuous watch and wake-ups (docs/WATCH.md): real journal in a temporary directory, fake market and deciders.

Common timeline: cycle 0 at T0+300 (completed at T0+300). For a tick X where the move applies, `prepare` journals
ticks X-3900 and X-3600 (references) then X-300 (confirmation); tick X is launched by the test. Window where a
wake-up is allowed after cycle 0: from T0+3900 (3600 s cooldown) to T0+12900 (30 min before the T0+14700
scheduled round). No test calls `claude -p` or the network.
"""

from __future__ import annotations

import random
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest

from arena import cli
from arena import cycle as cyc
from arena.config import ConfigError, load_config
from arena.cycle import cycle_lock, run_cycle
from arena.deciders.llm import load_system_prompt
from arena.deciders.snapshot import SCHEMA_VERSION
from arena.journal import Journal, verify
from arena.ledger import equity_ueur, replay
from arena.paths import REPO
from arena.sim.executor import SimExecutor
from arena.benchmarks.random_trader import seed_for
from arena.types import Bar, Instrument, Quote, notional_ueur
from arena.watch import (
    HistEntry,
    classify_quote,
    move,
    previous,
    next_scheduled_round,
    run_watch,
    candle_variation,
)
from tests.fakes import (
    H4,
    HAIKU,
    OPUS,
    SONNET,
    SYMBOLS,
    T0,
    Env,
    FakeKraken,
    ScriptedDecider,
    action,
)

FABLE = "llm:claude-fable-5-2"
LLM_ALL = (HAIKU, SONNET, OPUS, FABLE)
REFS = ("benchmark:basket", "benchmark:6040", "benchmark:e0065")
BTC = "BTC/EUR"
BTC_REF = 60_000_000_000  # reference mid of BTC at the test ticks (multiple of 10,000: exact percentages)
BTC_INST = Instrument("BTC/EUR", "XBTEUR", "BTCUSDT", 100_000, 6_000, 450_000)
X = T0 + 4200  # first tick where the move and the guards allow a wake-up


class LiveKraken(FakeKraken):
    """Fake market: forceable ticker (`override`), forceable trades (`trades`: piecewise prices, and `bar_override`:
    one specific 1-min candle) and failing 1-min OHLC reads (`fail_ohlc`)."""

    def __init__(self, clock) -> None:
        super().__init__(clock)
        self.override: dict[str, tuple[int, int]] = {}
        self.trades: dict[str, list[tuple[int, int]]] = {}  # symbol -> [(from ts, price)]
        self.bar_override: dict[tuple[str, int], tuple[int, int, int, int]] = {}
        self.fail_ohlc: set[str] = set()
        self.ohlc_error: Exception | None = None  # raised by any 1-min OHLC call (rate limit, ...)
        self.ohlc_calls = 0
        self.pairs_calls = 0
        self.pairs_error: Exception | None = None

    def ticker(self, symbol: str, pair: str) -> Quote:
        if symbol in self.override:
            bid, ask = self.override[symbol]
            return Quote(symbol, self.clock.now, bid, ask)
        return super().ticker(symbol, pair)

    def minute_bar(self, sym: str, ts: int):
        if (sym, ts) in self.bar_override:
            o, h, lo, c, *vol = self.bar_override[(sym, ts)]  # optional volume (0: filler candle)
            return Bar(sym, 60, ts, o, h, lo, c, vol[0] if vol else 1_000_000)
        price = None
        for frm, p in self.trades.get(sym, []):
            if frm <= ts:
                price = p
        if price is not None:
            return Bar(sym, 60, ts, price, price, price, price, 1_000_000)
        return super().minute_bar(sym, ts)

    def asset_pairs(self, pairs: list[str]):
        self.pairs_calls += 1
        if self.pairs_error is not None:
            raise self.pairs_error
        return super().asset_pairs(pairs)

    def ohlc(self, symbol: str, pair: str, interval_s: int = H4, since: int | None = None):
        if interval_s == 60:
            self.ohlc_calls += 1
            if self.ohlc_error is not None:
                raise self.ohlc_error
            if symbol in self.fail_ohlc:
                raise RuntimeError("ohlc down (test)")
        return super().ohlc(symbol, pair, interval_s, since)


class Recorder(ScriptedDecider):
    def __init__(self, model: str, portfolio: str, plan) -> None:
        super().__init__(model, portfolio, plan)
        self.spent: list[int] = []
        self.snaps: list[dict] = []

    def decide(self, snapshot: dict, spent_today_uusd: int):
        self.spent.append(spent_today_uusd)
        self.snaps.append(snapshot)
        return super().decide(snapshot, spent_today_uusd)


def make_env(tmp_path: Path, name: str = "e", secrets: dict[str, str] | None = None) -> Env:
    env = Env(tmp_path / name, secrets)
    env.kraken = env.clients.kraken = LiveKraken(env.clock)
    return env


def deciders(haiku_plan=None) -> dict:
    """One fake decider per LLM of the config (Fable included); only Haiku follows a plan."""
    none = lambda i, s: None
    return {
        HAIKU: Recorder("claude-haiku-5-5", HAIKU, haiku_plan or none),
        SONNET: Recorder("claude-sonnet-5-5", SONNET, none),
        OPUS: Recorder("claude-opus-5-5", OPUS, none),
        FABLE: Recorder("claude-fable-5-2", FABLE, none),
    }


def buy_btc_at_cycle_0(i: int, snap: dict):
    return [action(BTC, size=10, stop=5)] if i == 0 and snap["context"]["type"] == "scheduled_round" else None


def buy_eth_at_wakeup(i: int, snap: dict):
    return [action("ETH/EUR")] if snap["context"]["type"] == "wakeup" else None


def cycle(env: Env, i: int, d: dict | None = None, **kw):
    env.clock.now = env.now_of(i)
    return run_cycle(env.paths, env.clients, env.clock.now, deciders=d if d is not None else deciders(), **kw)


def tick(env: Env, ts: int, d: dict | None = None, **kw):
    """A watch tick at slot `ts` (multiple of 300), launched 30 s later like the timer."""
    env.clock.now = ts + 30
    return run_watch(env.paths, env.clients, ts + 30, deciders=d if d is not None else deciders(), **kw)


def of(env: Env, *types: str) -> list[dict]:
    return env.of_type(*types)


def pl(env: Env, t: str) -> list[dict]:
    return [e["payload"] for e in env.of_type(t)]


def codes(env: Env) -> list[tuple[str, str]]:
    return [(a["level"], a["code"]) for a in pl(env, "alert")]


def set_watch(env: Env, **kw: int) -> None:
    txt = env.paths.config.read_text()
    for k, v in kw.items():
        txt, n = re.subn(rf"^{k} = \d+", f"{k} = {v}", txt, flags=re.MULTILINE)
        assert n == 1, k
    env.paths.config.write_text(txt)


def set_trades(env: Env, sym: str, price: int, at: int | None = None) -> None:
    """Trades of `sym` happen at `price` from `at` (default: the current clock)."""
    env.kraken.trades.setdefault(sym, []).append((env.clock.now if at is None else at, price))


def set_btc(env: Env, mid: int, *, wide: bool = False, at: int | None = None) -> None:
    """BTC at mid `mid` (multiple of 1000): immediate ticker (`wide`: 3% spread) and trades at `mid` from `at`."""
    if wide:
        env.kraken.override[BTC] = (mid * 985 // 1000, mid * 1015 // 1000)
    else:
        env.kraken.override[BTC] = (mid * 9995 // 10000, mid * 10005 // 10000)
    set_trades(env, BTC, mid, at)


def set_ticker_btc(env: Env, mid: int) -> None:
    """BTC at mid `mid` on the ticker ONLY: trades (1-min candles) do not move."""
    env.kraken.override[BTC] = (mid * 9995 // 10000, mid * 10005 // 10000)


def clear_market(env: Env) -> None:
    env.kraken.override.clear()
    env.kraken.trades.clear()
    env.kraken.bar_override.clear()


def crash_to(env: Env, bid: int, ask: int | None = None, at: int | None = None) -> None:
    """Ticker (bid, ask) and trades at price `bid`, from `at` (default: the current clock)."""
    env.kraken.override[BTC] = (bid, bid + bid // 1000 if ask is None else ask)
    set_trades(env, BTC, bid, at)


def up(bp: int) -> int:
    return BTC_REF * (10_000 + bp) // 10_000


def prepare(env: Env, x: int, d: dict | None = None, bp: int = 300, *, wide: bool = False) -> dict:
    """Cycle 0; BTC traded at BTC_REF then, from x-420, at +bp (ticker and trades); a tick at x-300, where the
    move is not yet confirmed (tick x-600 was still at BTC_REF). Tick x is launched by the test."""
    d = d if d is not None else deciders()
    cycle(env, 0, d)
    set_btc(env, BTC_REF, at=0)
    set_btc(env, up(bp), wide=wide, at=x - 420)
    r = tick(env, x - 300, d)
    assert r.status == "done" and r.trigger is None
    return d


def check_journal(env: Env) -> None:
    rep = verify(env.paths.journal)
    assert rep.ok, rep.errors
    replay(env.events())  # does not raise


def wakeup_events(env: Env) -> list[str]:
    return [e["type"] for e in env.of_type("wakeup_started", "wakeup_completed", "wakeup_abandoned")]


def stop_of(env: Env, portfolio: str = HAIKU, symbol: str = BTC) -> int:
    return [s for s in pl(env, "stop_set") if s["portfolio"] == portfolio and s["symbol"] == symbol][-1]["stop_ueur"]


def random_tick() -> int:
    """First tick >= X where the random draw gives at least one action (searched, not assumed)."""
    for k in range(40):
        x = X + 300 * k
        if x <= T0 + 12900 and random.Random(seed_for(x, 0)).randrange(3) >= 1:
            return x
    raise AssertionError("no favorable tick")


# ---------------------------------------------------------------------------------------------- base tick


def test_one_watch_event_per_tick_idempotent(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    r1 = tick(env, T0 + 600)
    assert r1.status == "done" and r1.tick == T0 + 600 and r1.n_events == 1
    snapshot = env.paths.journal.read_bytes()
    env.clock.now = T0 + 730  # same 5-min slot
    again = run_watch(env.paths, env.clients, T0 + 730, deciders=deciders())
    assert again.status == "already_done" and again.n_events == 0 and again.ok
    assert env.paths.journal.read_bytes() == snapshot
    tick(env, T0 + 900)
    ev = of(env, "watch")
    assert [e["payload"]["tick"] for e in ev] == [T0 + 600, T0 + 900]
    assert [e["ts"] for e in ev] == [T0 + 600, T0 + 900]
    check_journal(env)


def test_watch_event_shape_and_equity_at_bid(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0, deciders(buy_btc_at_cycle_0))
    before = env.events()
    tick(env, T0 + 600)
    p = of(env, "watch")[-1]["payload"]
    assert set(p) == {"tick", "quotes", "raw_quotes", "rejected", "confirmed", "variations_bp", "closes_1m", "equity", "stops", "wakeup", "refused", "freeze"}
    assert p["raw_quotes"] == p["quotes"] and p["confirmed"] == []
    # Trades: closed 1-min candles; flat market, so zero variation and close = last price.
    last = env.kraken.minute_bar("ETH/EUR", (T0 + 600) // 60 * 60 - 60).close
    assert p["closes_1m"]["ETH/EUR"] == last and set(p["variations_bp"]) == set(SYMBOLS)
    for sym in SYMBOLS:  # variation = last 1-min close / 1-min close from 1 h ago, in rounded bp
        ref = env.kraken.minute_bar(sym, T0 + 600 - 3600).close
        cur = env.kraken.minute_bar(sym, T0 + 600 - 60).close
        d = cur - ref
        bp = (abs(d) * 20_000 + ref) // (2 * ref)
        assert p["variations_bp"][sym] == (bp if d > 0 else -bp)
    assert p["stops"] == [] and p["wakeup"] is None and p["refused"] is None and p["rejected"] == {} and p["freeze"] is False
    assert set(p["quotes"]) == set(SYMBOLS)
    q = env.kraken.ticker("ETH/EUR", "ETHEUR")
    assert p["quotes"]["ETH/EUR"] == [q.bid, q.ask]
    bids = {s: b for s, (b, _a) in p["quotes"].items()}
    marks = {s: (b + a) // 2 for s, (b, a) in p["quotes"].items()}
    assert p["equity"] == {name: equity_ueur(st, marks, bids) for name, st in sorted(replay(before).items())}
    assert len(p["equity"]) == 8
    assert not [e for e in of(env, "equity") if e["ts"] >= T0 + 600]  # the watch writes no equity


def test_tick_without_write_if_the_lock_is_taken(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    before = env.paths.journal.read_bytes()
    with cycle_lock(env.paths):
        rep = tick(env, T0 + 600)
    assert rep.status == "busy" and rep.ok and env.paths.journal.read_bytes() == before
    assert tick(env, T0 + 600).status == "done"  # lock free: the tick goes through


def test_before_the_first_cycle_the_watch_writes_nothing(tmp_path: Path):
    env = make_env(tmp_path)
    rep = tick(env, T0 + 600)
    assert rep.status == "inactive" and rep.ok and not env.paths.journal.exists()


def test_median_spreads_of_the_cycle_unchanged_by_the_watch_and_wakeups(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X, deciders())
    assert [e["payload"]["tick"] for e in of(env, "watch")] == [X - 300]
    quotes_before = of(env, "quote")
    assert tick(env, X, d).wakeup == "completed"
    assert of(env, "quote") == quotes_before  # neither the watch nor the wake-up adds a `quote`
    assert len(of(env, "wakeup_quote")) == 6  # the wake-up quotes have their own type

    def medians(events):
        spreads: dict[str, list[int]] = {}
        for e in events:
            spreads.setdefault(e["payload"]["symbol"], []).append(e["payload"]["ask"] - e["payload"]["bid"])
        return {s: sorted(v[-20:])[len(v[-20:]) // 2] for s, v in spreads.items()}

    assert medians(of(env, "quote")) == medians(quotes_before)
    assert {e["payload"]["symbol"] for e in of(env, "wakeup_quote")} == set(SYMBOLS)
    check_journal(env)


# ---------------------------------------------------------------------------------------------- 1. zero prices


def test_no_fill_at_zero_or_negative_before_write(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0, deciders(buy_btc_at_cycle_0))
    ex = SimExecutor(Journal(env.paths.journal), {BTC: BTC_INST}, 50, 5)
    before = env.paths.journal.read_bytes()
    for qty, px in [(1, 0), (1, -5), (0, 100_000), (-1, 100_000)]:
        with pytest.raises(ValueError, match="invalid fill"):
            ex._forced_sell("x", HAIKU, BTC, qty, px, 0, T0 + 600, "stop")
    assert env.paths.journal.read_bytes() == before
    # A quote whose bid falls to 0 (slippage included) is ignored by the live stops, the flattening and the
    # holding check: the journal stays identical.
    zero = {BTC: Quote(BTC, T0 + 600, 0, 100_000)}
    zeros = {BTC: [Bar(BTC, 60, T0 + 60 * k, 0, 0, 0, 0, 1) for k in range(1, 10)]}  # trades at 0: zero sell price
    assert ex.process_live_stops(zeros, T0 + 600) == []
    assert ex.flatten(HAIKU, zero, T0 + 600, "kill_switch") == []
    assert ex.process_stops_and_expiry({}, zero, T0 + 600 + 8 * 86_400, 604_800) == []
    assert env.paths.journal.read_bytes() == before
    check_journal(env)


# ---------------------------------------------------------------------------------------------- 2. dubious quotes


def hist_of(n: int, spread: int, mid: int = 1_000_000, step: int = 300, start: int = 1000):
    return [HistEntry(start + step * k, mid - spread // 2, mid + spread // 2, True, None) for k in range(n)]


def test_classify_quote_invalid_spread_jump_at_exact_bounds():
    t = 1000 + 300 * 6
    assert classify_quote(0, 10, [], t) == ("invalid", False)
    assert classify_quote(10, 9, [], t) == ("invalid", False)
    assert classify_quote(5, 5, [], t) == (None, False)  # bid == ask is valid
    assert classify_quote(True, 10, [], t) == ("invalid", False)
    h = hist_of(5, 1000)  # 5 raw spreads of 1000: the spread check applies
    assert classify_quote(1_000_000 - 2500, 1_000_000 + 2500, h, t) == (None, False)  # 5,000 = 5 x the median: accepted
    assert classify_quote(1_000_000 - 2500, 1_000_000 + 2501, h, t) == ("spread", False)
    h4 = hist_of(4, 1000)  # only 4 quotes: no spread check
    assert classify_quote(1_000_000 - 50_000, 1_000_000 + 50_000, h4, 1000 + 300 * 4) == (None, False)
    # The median covers the last 20 RAW spreads, rejected ones included: 20 spreads of 1000 after 10 of 100,000.
    h30 = [HistEntry(300 * k, 999_000, 1_099_000, False, "spread") for k in range(10)] + [
        HistEntry(3000 + 300 * k, 999_500, 1_000_500, True, None) for k in range(20)
    ]
    assert classify_quote(997_500, 1_002_500, h30, 3000 + 300 * 20) == (None, False)
    assert classify_quote(997_500, 1_002_501, h30, 3000 + 300 * 20) == ("spread", False)
    # Median over raw spreads: 10 wide rejected raw spreads + 10 narrow accepted ones -> wide median (index 10).
    mix = [HistEntry(300 * k, 999_000, 1_099_000, False, "spread") for k in range(11)] + [
        HistEntry(3300 + 300 * k, 999_500, 1_000_500, True, None) for k in range(9)
    ]
    assert classify_quote(950_000, 1_050_000, mix, 3300 + 300 * 9) == (None, False)  # spread 100 000 <= 5 x 100 000
    # Jump: mid 15% or more away from the last accepted quote under 30 min old.
    last = [HistEntry(1000, 999_999, 1_000_001, True, None)]
    assert classify_quote(1_149_999, 1_149_999, last, 1000 + 1799) == (None, False)  # 14.9999%
    assert classify_quote(1_150_000, 1_150_000, last, 1000 + 1799) == ("jump", False)
    assert classify_quote(850_000, 850_000, last, 1000 + 1799) == ("jump", False)
    assert classify_quote(850_001, 850_001, last, 1000 + 1799) == (None, False)
    # Stale history (exactly 30 min): the jump is measured against the 4 h close, with the same tolerance.
    assert classify_quote(1_150_000, 1_150_000, last, 1000 + 1800) == (None, False)  # without a close: no check
    assert classify_quote(1_150_000, 1_150_000, last, 1000 + 1800, close=1_000_000) == ("jump", False)
    assert classify_quote(1_149_999, 1_149_999, last, 1000 + 1800, close=1_000_000) == (None, False)


def test_breakout_confirmation_at_exact_bounds():
    prev_jump = [HistEntry(1000, 800_000, 800_000, False, "jump")]
    t = 1300
    assert classify_quote(800_000, 800_000, prev_jump, t, close=1_000_000) == (None, True)  # same mid: confirmed
    assert classify_quote(815_999, 815_999, prev_jump, t, close=1_000_000) == (None, True)  # 1.99% apart
    assert classify_quote(816_000, 816_000, prev_jump, t, close=1_000_000) == ("jump", False)  # 2%: no longer consistent
    assert classify_quote(784_000, 784_000, prev_jump, t, close=1_000_000) == ("jump", False)
    assert classify_quote(784_001, 784_001, prev_jump, t, close=1_000_000) == (None, True)
    assert classify_quote(800_000, 800_000, prev_jump, 1000 + 601, close=1_000_000) == ("jump", False)  # previous tick more than 10 min away
    assert classify_quote(800_000, 800_000, prev_jump, 1000 + 600, close=1_000_000) == (None, True)
    # The previous tick must have been rejected for spread or jump (or confirmed), not invalid nor normal.
    for flag in ("invalid", "error: X", None):
        h = [HistEntry(1000, 800_000, 800_000, False, flag)]
        assert classify_quote(800_000, 800_000, h, t, close=1_000_000) == ("jump", False), flag
    # A confirmed quote becomes the jump reference; its next tick, still too wide, is confirmed by chaining.
    assert classify_quote(800_000, 800_000, [HistEntry(1000, 800_000, 800_000, True, "is_confirmed")], t, close=1_000_000) == (None, False)
    chain = hist_of(5, 1000, start=0) + [HistEntry(1500, 995_000, 1_005_000, True, "is_confirmed")]
    assert classify_quote(995_000, 1_005_000, chain, 1800) == (None, True)
    assert classify_quote(995_000, 1_005_000, chain[:-1], 1800) == ("spread", False)  # without the confirmed tick: rejected


def test_quote_discarded_by_excluded_symbol_equity_at_last_valid_quote(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)  # the basket holds BTC
    tick(env, T0 + 600)
    first = of(env, "watch")[-1]["payload"]
    env.kraken.override[BTC] = (0, 10)  # zero bid: invalid
    rep = tick(env, T0 + 900)
    p = of(env, "watch")[-1]["payload"]
    assert rep.status == "done" and rep.rejected == {BTC: "invalid"} and p["rejected"] == {BTC: "invalid"}
    assert BTC not in p["quotes"] and set(p["quotes"]) == set(SYMBOLS) - {BTC}
    states = replay(env.events()[: of(env, "watch")[-1]["seq"]])
    bids = {s: b for s, (b, _a) in p["quotes"].items()} | {BTC: first["quotes"][BTC][0]}
    marks = {s: (b + a) // 2 for s, (b, a) in p["quotes"].items()} | {BTC: sum(first["quotes"][BTC]) // 2}
    assert p["equity"]["benchmark:basket"] == equity_ueur(states["benchmark:basket"], marks, bids)
    # 20% jump: discarded too; back to normal, the symbol resumes.
    mid = sum(first["quotes"][BTC]) // 2
    env.kraken.override[BTC] = (mid * 12 // 10, mid * 12 // 10 + 1000)
    assert tick(env, T0 + 1200).rejected == {BTC: "jump"}
    env.kraken.override.clear()
    assert tick(env, T0 + 1500).rejected == {}


def wide_quote(env: Env, bid_or_mid: int, spread: int, *, bid: bool = False) -> None:
    """BTC with a given spread: around the mid (default) or from the bid (`bid=True`)."""
    if bid:
        env.kraken.override[BTC] = (bid_or_mid, bid_or_mid + spread)
    else:
        env.kraken.override[BTC] = (bid_or_mid - spread // 2, bid_or_mid + spread // 2)


def watch_p(env: Env) -> dict:
    return of(env, "watch")[-1]["payload"]


def test_lasting_spread_x10_accepted_at_2nd_tick(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    normal = env.kraken.ticker(BTC, "XBTEUR")
    spread10 = 10 * (normal.ask - normal.bid)
    for k in range(5):  # 5 normal ticks: the spread check applies
        assert tick(env, T0 + 600 + 300 * k).rejected == {}
    wide_quote(env, normal.bid, spread10, bid=True)
    w1 = tick(env, T0 + 2100)
    assert w1.rejected == {BTC: "spread"} and w1.confirmed == []
    p1 = watch_p(env)
    assert BTC not in p1["quotes"] and p1["raw_quotes"][BTC] == [normal.bid, normal.bid + spread10]
    w2 = tick(env, T0 + 2400)  # second consistent tick: the breakout is accepted
    assert w2.rejected == {} and w2.confirmed == [BTC]
    p2 = watch_p(env)
    assert p2["quotes"][BTC] == [normal.bid, normal.bid + spread10] and p2["confirmed"] == [BTC] and p2["rejected"] == {}
    check_journal(env)


def test_ticker_crash_without_trades_equity_at_last_accepted_quote_no_sell(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    set_ticker_btc(env, BTC_REF)
    tick(env, T0 + 600, d)
    ok = watch_p(env)["quotes"][BTC]
    set_ticker_btc(env, BTC_REF * 80 // 100)  # the ticker collapses, no trade follows
    crash = env.kraken.override[BTC]
    w1 = tick(env, T0 + 900, d)
    assert w1.rejected == {BTC: "jump"} and w1.stops == []
    p1 = watch_p(env)
    assert p1["raw_quotes"][BTC] == list(crash) and BTC not in p1["quotes"]
    pre = replay(env.events()[: of(env, "watch")[-1]["seq"]])["benchmark:basket"]
    bids = {s: b for s, (b, _a) in p1["quotes"].items()} | {BTC: ok[0]}  # valued at the last accepted quote
    marks = {s: (b + a) // 2 for s, (b, a) in p1["quotes"].items()} | {BTC: sum(ok) // 2}
    assert p1["equity"]["benchmark:basket"] == equity_ueur(pre, marks, bids)
    w2 = tick(env, T0 + 1200, d)  # second consistent tick: accepted (equity up to date), but never a sale
    assert w2.rejected == {} and w2.confirmed == [BTC] and w2.stops == []
    p2 = watch_p(env)
    pre2 = replay(env.events()[: of(env, "watch")[-1]["seq"]])["benchmark:basket"]
    bids2 = {s: b for s, (b, _a) in p2["quotes"].items()}
    marks2 = {s: (b + a) // 2 for s, (b, a) in p2["quotes"].items()}
    assert p2["equity"]["benchmark:basket"] == equity_ueur(pre2, marks2, bids2) < p1["equity"]["benchmark:basket"]
    assert BTC in replay(env.events())[HAIKU].positions
    check_journal(env)


def test_chained_acceptance_capped_at_6_ticks_then_rejection_alert_and_lift(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    normal = env.kraken.ticker(BTC, "XBTEUR")
    for k in range(20):  # 20 normal raw spreads: the median only follows the new regime at the 11th wide tick
        tick(env, T0 + 600 + 300 * k)
    wide_quote(env, normal.bid, 10 * (normal.ask - normal.bid), bid=True)
    out, conf = [], []
    for w in range(1, 12):
        rep = tick(env, T0 + 600 + 300 * (19 + w))
        out.append("ok" if rep.rejected == {} else rep.rejected[BTC])
        conf.append(BTC in rep.confirmed)
        if w in (8, 9, 10):  # chain exhausted: the symbol is rejected, equity stays at the last accepted quote
            assert BTC not in watch_p(env)["quotes"] and watch_p(env)["raw_quotes"][BTC][0] == normal.bid
    # 1 initial rejection, 6 ticks accepted by confirmation, 3 rejections, then the raw median caught up: accepted.
    assert out == ["spread"] + ["ok"] * 6 + ["spread"] * 3 + ["ok"]
    assert conf == [False] + [True] * 6 + [False] * 4
    alerts = [(a["level"], a["message"]) for a in pl(env, "alert") if a["code"] == "watch_symbol_discarded"]
    assert [(lvl, m.startswith(t)) for (lvl, m), t in zip(alerts, ("BTC/EUR: quotes discarded", "BTC/EUR: quotes accepted again"), strict=True)] == [("action", True), ("info", True)]


def test_isolated_aberrant_tick_never_accepted_nor_sell_nor_wakeup(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    set_ticker_btc(env, BTC_REF)
    tick(env, T0 + 600, d)
    set_ticker_btc(env, BTC_REF * 50 // 100)
    b = tick(env, T0 + 900, d)
    assert b.rejected == {BTC: "jump"} and b.confirmed == [] and b.stops == [] and b.trigger is None
    assert BTC not in watch_p(env)["quotes"]
    set_ticker_btc(env, BTC_REF)
    c = tick(env, T0 + 1200, d)  # back to normal: accepted normally, not by confirmation
    assert c.rejected == {} and c.confirmed == [] and c.stops == []
    assert BTC in watch_p(env)["quotes"]
    assert BTC in replay(env.events())[HAIKU].positions and not wakeup_events(env)
    assert not [f for f in pl(env, "fill") if f["order_id"].endswith(":watch:" + str(T0 + 900))]


def test_two_aberrant_inconsistent_ticks_stay_rejected(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    set_ticker_btc(env, BTC_REF)
    tick(env, T0 + 600, d)
    set_ticker_btc(env, BTC_REF * 50 // 100)
    assert tick(env, T0 + 900, d).rejected == {BTC: "jump"}
    set_ticker_btc(env, BTC_REF * 70 // 100)  # -30%: 40% away from the previous tick
    c = tick(env, T0 + 1200, d)
    assert c.rejected == {BTC: "jump"} and c.confirmed == [] and c.stops == []
    assert BTC not in watch_p(env)["quotes"] and BTC in replay(env.events())[HAIKU].positions


def test_stale_history_the_jump_is_measured_against_the_4h_close(tmp_path: Path):
    env = make_env(tmp_path)  # no watch quote: the first tick compares against the 4 h close from the store
    cycle(env, 0)
    close = max(env.kraken.ohlc(BTC, "XBTEUR", H4, None), key=lambda b: b.ts).close
    set_ticker_btc(env, close // 10_000 * 10_000 // 2)
    first = tick(env, T0 + 600)
    assert first.rejected == {BTC: "jump"} and BTC not in watch_p(env)["quotes"]
    # Accepted history exactly 30 min old: same rule, then confirmation at the next tick.
    env2 = make_env(tmp_path, "e2")
    cycle(env2, 0)
    tick(env2, T0 + 600)  # normal BTC accepted
    set_ticker_btc(env2, close // 10_000 * 10_000 // 2)
    b = tick(env2, T0 + 600 + 1800)
    assert b.rejected == {BTC: "jump"} and b.confirmed == []
    c = tick(env2, T0 + 600 + 2100)
    assert c.rejected == {} and c.confirmed == [BTC]


def test_alert_discarded_symbol_and_median_on_raw_quotes(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    for k in range(5):
        set_ticker_btc(env, BTC_REF)
        tick(env, T0 + 600 + 300 * k)
    # Lasting x10 spread with a mid oscillating by 3%: never confirmed (2% or more apart between two ticks).
    outcomes = []
    for w in range(1, 8):
        mid = BTC_REF * (1015 if w % 2 else 985) // 1000
        env.kraken.override[BTC] = (mid * 995 // 1000, mid * 1005 // 1000)
        rep = tick(env, T0 + 1800 + 300 * w)
        outcomes.append((rep.rejected.get(BTC), rep.confirmed))
    # The raw median catches up with the wide regime at the 6th wide tick: accepted normally, without confirmation.
    assert outcomes == [("spread", [])] * 5 + [(None, [])] * 2
    syms = [(a["level"], a["code"], a["message"][:25].rstrip()) for a in pl(env, "alert") if a["code"] == "watch_symbol_discarded"]
    assert syms == [
        ("action", "watch_symbol_discarded", "BTC/EUR: quotes discarded"),
        ("info", "watch_symbol_discarded", "BTC/EUR: quotes accepted"),
    ]
    alerts = [e for e in of(env, "alert") if e["payload"]["code"] == "watch_symbol_discarded"]
    ticks = [e["ts"] for e in alerts]
    assert ticks == [T0 + 1800 + 300 * 3 + 30, T0 + 1800 + 300 * 6 + 30]  # at the 3rd rejection, then at the lift (6th tick)


def test_discarded_symbol_no_stop_nor_trigger_on_it(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    S = stop_of(env)
    set_ticker_btc(env, BTC_REF)
    tick(env, T0 + 600, d)
    # Quote below the stop but with a jump > 15% (3% spread: ask 3% above): discarded, no sale.
    bad = S * 80 // 100
    env.kraken.override[BTC] = (bad, bad + 1000)
    rep = tick(env, T0 + 900, d)
    assert rep.rejected == {BTC: "jump"} and rep.stops == []
    assert BTC in replay(env.events())[HAIKU].positions
    assert rep.trigger is None


def test_no_valid_symbol_the_tick_fails_without_writing_anything(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    size = env.paths.journal.stat().st_size
    env.kraken.fail_ticker = True
    rep = tick(env, T0 + 600)
    assert rep.status == "failed" and not rep.ok and "no usable quote" in rep.error
    assert env.paths.journal.stat().st_size == size
    env.kraken.fail_ticker = False
    assert tick(env, T0 + 900).status == "done"


# ---------------------------------------------------------------------------------------------- 3. stops and move on trades


def base_close(env: Env) -> int:
    """Flat BTC trade price when nothing is forced (4 h close of the fake market)."""
    return env.kraken.minute_bar(BTC, T0).close


def b1(ts: int, o: int, h: int, lo: int, c: int) -> Bar:
    return Bar(BTC, 60, ts, o, h, lo, c, 1)


def fee_of(qty: int, px: int) -> int:
    return -(-notional_ueur(qty, px, round_up=True) * 50 // 10_000)  # taker fee 50 bp, rounded up


def test_stop_on_trades_at_last_price_with_slippage_and_fees(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    qty = replay(env.events())[HAIKU].positions[BTC].qty
    S = stop_of(env)
    low = S - 1_000_000
    set_trades(env, BTC, low, at=T0 + 840)  # trades go below the stop; the ticker stays normal
    r1 = tick(env, T0 + 900, d)  # only one closed candle below the stop (ts T0+840): wait for the next tick
    assert r1.stops == [] and BTC in replay(env.events())[HAIKU].positions
    r = T0 + 1200
    rep = tick(env, r, d)
    oid = f"stop:{HAIKU}:{BTC}:watch:{r}"
    assert oid in rep.stops
    fill = next(f for f in pl(env, "fill") if f["order_id"] == oid)
    px = S  # ticker above the stop: max(1-min close, ticker bid) x (1 - slippage) is capped at the stop
    assert (fill["side"], fill["qty"], fill["price_ueur"], fill["fee_ueur"], fill["ts"], fill["reason"]) == (
        "sell", qty, px, fee_of(qty, px), r, "stop",
    )  # fmt: skip
    assert env.kraken.ticker(BTC, "XBTEUR").bid * 9995 // 10_000 > S
    assert BTC not in replay(env.events())[HAIKU].positions and oid in of(env, "watch")[-1]["payload"]["stops"]
    n = len(of(env, "fill"))
    tick(env, r)  # same tick: nothing more
    assert len(of(env, "fill")) == n
    # The next cycle sees the T0 bar below the stop (6% crash): already sold, no second sale.
    clear_market(env)
    env.kraken.crash(BTC, T0, 940)
    cycle(env, 1, d)
    sells = [f["order_id"] for f in pl(env, "fill") if f["portfolio"] == HAIKU and f["symbol"] == BTC and f["side"] == "sell"]
    assert sells == [oid] and not [f for f in pl(env, "fill") if f["order_id"] == f"stop:{HAIKU}:{BTC}:{T0}"]
    check_journal(env)


def test_stop_price_never_above_the_stop(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    qty = replay(env.events())[HAIKU].positions[BTC].qty
    S = stop_of(env)
    set_trades(env, BTC, S - 1_000_000, at=T0 + 840)  # two candles below the stop (T0+840, T0+900) ...
    set_trades(env, BTC, base_close(env), at=T0 + 960)  # ... then the price rises well above
    r = T0 + 1200
    rep = tick(env, r, d)
    oid = f"stop:{HAIKU}:{BTC}:watch:{r}"
    assert oid in rep.stops
    fill = next(f for f in pl(env, "fill") if f["order_id"] == oid)
    assert base_close(env) * 9995 // 10_000 > S  # the last close x (1 - slippage) would be above the stop
    assert fill["price_ueur"] == S and fill["fee_ueur"] == fee_of(qty, S)


def test_isolated_aberrant_candle_no_sell(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    base = base_close(env)
    env.kraken.bar_override[(BTC, T0 + 1080)] = (base, base, 1, base)  # a low at 1 µEUR, a single minute
    for t in (T0 + 1200, T0 + 1500):
        assert tick(env, t, d).stops == []
    assert BTC in replay(env.events())[HAIKU].positions
    env.kraken.bar_override[(BTC, T0 + 1560)] = (base, base, 1, base)  # two distinct candles in the window: the sale goes out
    env.kraken.bar_override[(BTC, T0 + 1620)] = (base, base, 1, base)
    r = T0 + 1800
    assert f"stop:{HAIKU}:{BTC}:watch:{r}" in tick(env, r, d).stops


def test_repeated_ticker_glitch_without_trades_under_the_stop_no_sell(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    S = stop_of(env)
    env.kraken.override[BTC] = (S - 1_000_000, S - 900_000)  # the ticker shows a bid below the stop, tick after tick
    for k in range(5):
        rep = tick(env, T0 + 600 + 300 * k, d)
        assert rep.stops == [] and rep.rejected == {}
        assert watch_p(env)["quotes"][BTC][0] == S - 1_000_000  # the erroneous quote is indeed accepted by the ticker check
    assert BTC in replay(env.events())[HAIKU].positions and not [f for f in pl(env, "fill") if f["reason"] == "stop"]


def test_crash_at_minus_3_pct_per_tick_huge_spread_sell_at_first_tick_with_2_candles(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    qty = replay(env.events())[HAIKU].positions[BTC].qty
    S = stop_of(env)
    base = base_close(env)
    p1, p2, p3 = base * 97 // 100, base * 97 // 100 * 97 // 100, base * 97 // 100 * 97 // 100 * 97 // 100
    assert p1 > S > p2
    t1, t2, t3 = T0 + 900, T0 + 1200, T0 + 1500
    stops = []
    for t, price in ((t1, p1), (t2, p2), (t3, p3)):
        set_trades(env, BTC, price, at=t - 240)  # each tick, another -3%
        env.kraken.override[BTC] = (price * 985 // 1000, price * 1015 // 1000)  # ticker: 3% spread
        stops.append(tick(env, t, d).stops)
    oid = f"stop:{HAIKU}:{BTC}:watch:{t2}"
    assert oid not in stops[0] and oid in stops[1] and not [x for x in stops[2] if HAIKU in x]
    fill = next(f for f in pl(env, "fill") if f["order_id"] == oid)
    px = p2 * 9995 // 10_000 // 100_000 * 100_000  # last 1-min close x (1 - slippage)
    assert (fill["price_ueur"], fill["fee_ueur"], fill["qty"]) == (px, fee_of(qty, px), qty) and px < S
    assert BTC not in replay(env.events())[HAIKU].positions
    ref = env.kraken.minute_bar(BTC, t3 - 3600).close  # 1-min close from 1 h ago (before any move)
    assert watch_p(env)["variations_bp"][BTC] == -(((ref - p3) * 20_000 + ref) // (2 * ref))


def test_failed_ohlc_read_no_stop_nor_trigger_on_the_symbol(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    S = stop_of(env)
    set_trades(env, BTC, S - 1_000_000, at=T0 + 840)
    env.kraken.fail_ohlc.add(BTC)
    rep = tick(env, T0 + 1200, d)
    assert rep.rejected == {BTC: "ohlc"} and rep.stops == [] and BTC in replay(env.events())[HAIKU].positions
    p = watch_p(env)
    assert p["rejected"] == {BTC: "ohlc"} and BTC in p["quotes"] and BTC not in p["closes_1m"] and BTC not in p["variations_bp"]
    env.kraken.fail_ohlc.clear()  # the read comes back: the watch safety net resumes (candles since T0+900)
    r = T0 + 1500
    assert f"stop:{HAIKU}:{BTC}:watch:{r}" in tick(env, r, d).stops
    assert watch_p(env)["rejected"] == {}


def test_position_rebought_after_a_watch_stop_stays_managed(tmp_path: Path):
    env = make_env(tmp_path)

    def plan(i, snap):
        return [action(BTC, size=10, stop=5)] if i in (0, 1) else None

    d = deciders(plan)
    cycle(env, 0, d)
    stop0 = stop_of(env)
    set_trades(env, BTC, stop0 - 1_000_000, at=T0 + 840)
    r = T0 + 1200
    assert f"stop:{HAIKU}:{BTC}:watch:{r}" in tick(env, r, d).stops
    assert BTC not in replay(env.events())[HAIKU].positions
    clear_market(env)
    env.kraken.crash(BTC, T0, 940)  # the T0 bar is below the old stop
    cycle(env, 1, d)  # buy-back
    pos = replay(env.events())[HAIKU].positions[BTC]
    assert pos.opened_ts == T0 + H4
    stop1 = stop_of(env)
    assert stop1 != stop0
    cycle(env, 2, d)  # the old stop does not touch the bought-back position
    assert [f["order_id"] for f in pl(env, "fill") if f["portfolio"] == HAIKU and f["side"] == "sell"] == [
        f"stop:{HAIKU}:{BTC}:watch:{r}"
    ]
    assert replay(env.events())[HAIKU].positions[BTC].stop_ueur == stop1
    env.kraken.crash(BTC, T0 + 2 * H4, 800)  # new crash: the bar safety net applies to the bought-back position
    cycle(env, 3, d)
    sells = [f["order_id"] for f in pl(env, "fill") if f["portfolio"] == HAIKU and f["side"] == "sell"]
    assert sells == [f"stop:{HAIKU}:{BTC}:watch:{r}", f"stop:{HAIKU}:{BTC}:{T0 + 2 * H4}"]
    assert BTC not in replay(env.events())[HAIKU].positions
    check_journal(env)


def test_previous_pure_function():
    h = [HistEntry(1000, 10, 12, True, None), HistEntry(1900, 20, 22, True, None), HistEntry(2800, 30, 32, False, "jump")]
    assert previous(h, 3100) == h[2]  # the previous tick counts even if rejected (raw quote)
    assert previous([HistEntry(100, 1, 2, True, None)], 700) is not None and previous([HistEntry(100, 1, 2, True, None)], 701) is None
    assert previous([HistEntry(100, 1, 2, True, None)], 100) is None  # strictly before
    assert previous([HistEntry(100, None, None, False, "invalid")], 200) is None


def test_candle_variation_reference_at_15_minutes_positive_volume():
    # Reference: the last TRADED candle at tick - window or earlier, within 15 min; the last traded one sets the price.
    tick = 7200
    cur = b1(7140, 1_030_000, 1_030_000, 1_030_000, 1_030_000)
    ok = lambda ts, c=1_000_000, v=1: Bar(BTC, 60, ts, 1, 1, 1, c, v)
    assert candle_variation([ok(3600), cur], tick, 3600) == (1_030_000, 1_000_000)
    assert candle_variation([ok(2700), cur], tick, 3600) == (1_030_000, 1_000_000)  # 15 min before the target: accepted
    assert candle_variation([ok(2699), cur], tick, 3600) is None  # 15 min and 1 s: too old
    assert candle_variation([ok(3601), cur], tick, 3600) is None  # never after the target
    assert candle_variation([ok(3000, 900_000), ok(3500, 800_000), ok(3600, 700_000, 0), cur], tick, 3600)[1] == 800_000
    assert candle_variation([ok(3600, 700_000, 0), cur], tick, 3600) is None  # filler candle: ignored
    cur0 = Bar(BTC, 60, 7140, 1, 1, 1, 5, 0)  # the last candle is a filler: take the last traded one
    assert candle_variation([ok(3600), ok(7080, 1_020_000), cur0], tick, 3600) == (1_020_000, 1_000_000)
    assert candle_variation([ok(3600), b1(7141, 1, 1, 1, 5)], tick, 3600) is None  # still open: never read
    assert candle_variation([ok(3600), ok(7200 - 60 - 901)], tick, 3600) is None  # no trade for 15 min


def minute_path(changes: dict[int, int], start: int = 3000, end: int = 7200) -> list[Bar]:
    """Flat candles per minute; `changes`: {from ts: price}."""
    out = []
    for ts in range(start, end, 60):
        price = [p for frm, p in sorted(changes.items()) if frm <= ts][-1]
        out.append(b1(ts, price, price, price, price))
    return out


def test_move_on_candles_variations_exact_thresholds_and_confirmation():
    ref = 1_000_000
    mb = {  # A +4% and B -10% since 6000 (confirmed at both ticks 7200 and 6900), C flat
        "A": minute_path({0: ref, 6000: 1_040_000}), "B": minute_path({0: ref, 6000: 900_000}), "C": minute_path({0: ref}),
    }
    for sym, bars in mb.items():
        mb[sym] = [Bar(sym, 60, b.ts, b.open, b.high, b.low, b.close, 1) for b in bars]
    trig, var = move(mb, 7200, 300, 3600, 300)
    assert trig == {"type": "move", "symbol": "B", "variation_bp": -1000, "window_s": 3600}
    assert var == {"A": 400, "B": -1000, "C": 0}
    # Exact threshold: +3% triggers, +2.9999% does not (at both ticks).
    for price, expected in ((1_030_000, True), (1_029_999, False), (970_000, True), (970_001, False)):
        bars = {"A": [Bar("A", 60, b.ts, b.open, b.high, b.low, b.close, 1) for b in minute_path({0: ref, 6000: price})]}
        assert (move(bars, 7200, 300, 3600, 300)[0] is not None) is expected, price
    # Confirmation: the previous tick (6900) was still flat -> no trigger, the variation is still measured.
    late = {"A": [Bar("A", 60, b.ts, b.open, b.high, b.low, b.close, 1) for b in minute_path({0: ref, 7000: 1_050_000})]}
    trig, var = move(late, 7200, 300, 3600, 300)
    assert trig is None and var == {"A": 500}
    # Opposite directions (-3% at the previous tick, +3% at the current one): no trigger.
    opp = {"A": [Bar("A", 60, b.ts, b.open, b.high, b.low, b.close, 1) for b in minute_path({0: ref, 6000: 970_000, 7000: 1_030_000})]}
    assert move(opp, 7200, 300, 3600, 300)[0] is None
    assert move({}, 7200, 300, 3600, 300) == (None, {})


# ---------------------------------------------------------------------------------------------- 4. stop trigger removed


def buy_btc_stop_1pct(i: int, snap: dict):
    return [action(BTC, size=10, stop=1)] if i == 0 and snap["context"]["type"] == "scheduled_round" else None


def test_a_watch_stop_is_no_longer_a_trigger_and_the_prompt_says_so(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_stop_1pct)
    cycle(env, 0, d)
    set_trades(env, BTC, base_close(env) * 98 // 100, at=X - 420)  # -2%: below the 1% stop, below the 3% threshold
    rep = tick(env, X, d)  # stop executed on an LLM portfolio
    assert f"stop:{HAIKU}:{BTC}:watch:{X}" in rep.stops
    assert rep.trigger is None and rep.wakeup is None and not wakeup_events(env)
    p = watch_p(env)
    assert p["wakeup"] is None and p["refused"] is None
    text = load_system_prompt()
    assert "stop" not in text.split("## What you receive")[0].lower().replace("mandatory stop", "")
    assert "You decide once every 4 hours" not in text
    assert (
        "You are called at a fixed appointment every 4 hours, and you may also be woken between two "
        "appointments when an instrument moves by at least the threshold within 1 hour; the `context` field of "
        "the snapshot says which of the two it is, and nothing obliges you to act."
    ) in text


def test_benchmark_stop_executed_without_wakeup(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    base = base_close(env)
    Journal(env.paths.journal).append(
        "stop_set", {"portfolio": "benchmark:basket", "symbol": BTC, "stop_ueur": base * 99 // 100}, T0 + 400
    )
    set_trades(env, BTC, base * 98 // 100, at=X - 420)
    rep = tick(env, X)
    assert f"stop:benchmark:basket:{BTC}:watch:{X}" in rep.stops
    assert BTC not in replay(env.events())["benchmark:basket"].positions
    assert rep.trigger is None and not wakeup_events(env)
    check_journal(env)


# ---------------------------------------------------------------------------------------------- move trigger


@pytest.mark.parametrize(("bp", "wakeup"), [(299, False), (300, True), (-300, True), (-299, False)])
def test_move_trigger_at_exact_threshold(tmp_path: Path, bp: int, wakeup: bool):
    env = make_env(tmp_path)
    d = prepare(env, X, bp=bp)
    rep = tick(env, X, d)
    trig = {"type": "move", "symbol": BTC, "variation_bp": bp, "window_s": 3600}
    assert watch_p(env)["variations_bp"][BTC] == bp and set(watch_p(env)["variations_bp"]) == set(SYMBOLS)
    if wakeup:
        assert rep.trigger == trig and rep.wakeup == "completed"
        assert of(env, "watch")[-1]["payload"]["wakeup"] == trig
        assert pl(env, "wakeup_started") == [{"wakeup": X, "trigger": trig}]
    else:
        assert rep.trigger is None and rep.wakeup is None
        assert of(env, "watch")[-1]["payload"]["wakeup"] is None
        assert not wakeup_events(env)


@pytest.mark.parametrize(
    ("p_bp", "x_bp", "trigger"),
    [(300, 300, True), (0, 300, False), (300, 0, False), (-300, 300, False), (299, 300, False), (300, 299, False)],
)
def test_move_confirmed_on_two_same_side_ticks_each_against_its_reference(tmp_path, p_bp, x_bp, trigger):
    env = make_env(tmp_path)
    d = deciders()
    cycle(env, 0, d)
    set_btc(env, BTC_REF, at=0)
    set_btc(env, up(p_bp), at=X - 420)  # price at tick X-300
    set_btc(env, up(x_bp), at=X - 240)  # price at tick X
    assert tick(env, X - 300, d).trigger is None
    rep = tick(env, X, d)
    assert (rep.trigger is not None) is trigger and (rep.wakeup == "completed") is trigger


def test_move_measured_on_trades_the_ticker_is_ignored(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders()
    cycle(env, 0, d)
    set_btc(env, BTC_REF, at=0)
    for t in (X - 300, X):  # the ticker soars 7% (accepted by its check), trades stay flat
        set_ticker_btc(env, up(700))
        rep = tick(env, t, d)
        assert rep.trigger is None and rep.wakeup is None
    assert watch_p(env)["quotes"][BTC] == [up(700) * 9995 // 10000, up(700) * 10005 // 10000]
    assert watch_p(env)["variations_bp"][BTC] == 0 and not wakeup_events(env)
    # Conversely: trades rise 3%, the ticker stays normal: the trigger fires.
    env2 = make_env(tmp_path, "e2")
    d2 = prepare(env2, X, bp=300)
    del env2.kraken.override[BTC]
    rep2 = tick(env2, X, d2)
    assert rep2.trigger == {"type": "move", "symbol": BTC, "variation_bp": 300, "window_s": 3600}
    assert rep2.wakeup == "completed"


# ---------------------------------------------------------------------------------------------- guards


def test_guardrail_delay_since_the_last_round(tmp_path: Path):
    last = T0 + 300  # end of cycle 0
    for cooldown, ok in [(X - last + 1, False), (X - last, True)]:  # 3901 s refuses, 3900 s passes (no "<")
        env = make_env(tmp_path, f"cd{cooldown}")
        set_watch(env, cooldown_s=cooldown)
        d = prepare(env, X)
        rep = tick(env, X, d)
        assert rep.trigger is not None
        assert (rep.refused, rep.wakeup) == ((None, "completed") if ok else ("delay", None))
        assert bool(wakeup_events(env)) is ok
        p = of(env, "watch")[-1]["payload"]
        assert (p["wakeup"], p["refused"]) == ((rep.trigger, None) if ok else (None, "delay"))


def test_delay_counts_from_wakeup_started_and_also_abandonments(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X)
    j = Journal(env.paths.journal)
    j.append("wakeup_started", {"wakeup": T0 + 150, "trigger": {"type": "move", "symbol": BTC, "variation_bp": 300, "window_s": 3600}}, X - 100)
    j.append("wakeup_abandoned", {"wakeup": T0 + 150}, T0 + 200)  # the abandonment is old, but the start is 100 s old
    rep = tick(env, X, d)
    assert rep.refused == "delay" and rep.wakeup is None


def test_guardrail_daily_cap_also_counts_abandoned_wakeups(tmp_path: Path):
    trig = {"type": "move", "symbol": BTC, "variation_bp": 300, "window_s": 3600}
    for cap, ok in [(1, False), (2, True)]:
        for end in ("wakeup_completed", "wakeup_abandoned"):
            env = make_env(tmp_path, f"cap{cap}{end}")
            set_watch(env, max_wakeups_per_day=cap)
            d = prepare(env, X)
            j = Journal(env.paths.journal)
            j.append("wakeup_started", {"wakeup": T0 + 150, "trigger": trig}, T0 + 160)
            j.append(end, {"wakeup": T0 + 150}, T0 + 200)  # a wake-up earlier on the same UTC day
            rep = tick(env, X, d)
            assert (rep.refused, rep.wakeup) == ((None, "completed") if ok else ("cap", None)), (cap, end)
    # A wake-up from the previous UTC day does not count.
    env = make_env(tmp_path, "watch-day")
    set_watch(env, max_wakeups_per_day=1)
    d = prepare(env, X)
    j = Journal(env.paths.journal)
    j.append("wakeup_started", {"wakeup": T0 - 5000, "trigger": trig}, T0 - 4990)
    j.append("wakeup_completed", {"wakeup": T0 - 5000}, T0 - 4900)
    assert tick(env, X, d).wakeup == "completed"


def test_guardrail_before_the_cycle(tmp_path: Path):
    scheduled_round = T0 + H4 + 300
    assert next_scheduled_round(X, H4, 300) == scheduled_round
    assert next_scheduled_round(T0 + 300, H4, 300) == scheduled_round  # at exactly HH:05, the next one is in 4 h
    assert next_scheduled_round(T0, H4, 300) == T0 + 300
    for x, ok in [(scheduled_round - 1800, True), (scheduled_round - 1500, False)]:  # 1800 s before passes, 1500 s before refuses
        env = make_env(tmp_path, f"av{x}")
        d = prepare(env, x)
        rep = tick(env, x, d)
        assert rep.trigger is not None
        assert (rep.refused, rep.wakeup) == ((None, "completed") if ok else ("before_cycle", None))
        assert of(env, "watch")[-1]["payload"]["refused"] == (None if ok else "before_cycle")


def test_guardrail_incomplete_cycle(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)

    def boom(p: str) -> None:
        raise RuntimeError("simulated crash")

    assert cycle(env, 1, on_portfolio_done=boom).status == "failed"  # cycle_started without cycle_completed
    x = T0 + H4 + 4200
    set_btc(env, BTC_REF)
    for t in (x - 3900, x - 3600):
        tick(env, t)
    set_btc(env, up(300))
    tick(env, x - 300)
    rep = tick(env, x)
    assert rep.trigger is not None and rep.refused == "cycle_incomplete" and rep.wakeup is None
    assert of(env, "watch")[-1]["payload"]["refused"] == "cycle_incomplete"
    assert not wakeup_events(env)
    env.kraken.override.clear()
    assert cycle(env, 1).status == "completed"  # the resumed cycle lifts this guard


def test_tick_multiple_of_4_h_never_wakes_even_without_pre_cycle_guard(tmp_path: Path):
    env = make_env(tmp_path)
    set_watch(env, pre_cycle_guard_s=0)
    x = T0 + H4  # exactly HH:00: the wake-up identifier would collide with the cycle's
    d = prepare(env, x)
    rep = tick(env, x, d)
    assert rep.trigger is not None and rep.refused == "cycle" and rep.wakeup is None
    assert not wakeup_events(env)
    assert of(env, "watch")[-1]["payload"]["refused"] == "cycle"
    # Without the "before the cycle" guard, the next tick (HH:05) is not a multiple: the wake-up goes through.
    assert next_scheduled_round(x + 300, H4, 300) == x + H4 + 300


def test_no_wakeup_during_a_running_cycle(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X)
    before = env.paths.journal.read_bytes()
    with cycle_lock(env.paths):  # a cycle (or a wake-up) holds the lock
        rep = tick(env, X, d)
    assert rep.status == "busy" and env.paths.journal.read_bytes() == before


# ---------------------------------------------------------------------------------------------- 5. the wake-up is recorded first


def test_wakeup_started_is_written_before_the_watch_event(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X)
    tick(env, X, d)
    seq = {e["type"]: e["seq"] for e in env.events() if e["ts"] >= X and e["type"] in ("wakeup_started", "watch")}
    assert seq["wakeup_started"] < seq["watch"]
    first_net = min(e["seq"] for e in of(env, "wakeup_quote"))
    assert seq["watch"] < first_net


def test_failing_wakeup_is_resumed_one_alert_per_code_and_per_wakeup(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X)

    def boom(p: str) -> None:
        raise RuntimeError("simulated crash")

    for k in range(3):  # three failures in a row: X, X+300 (resume), X+600 (resume)
        rep = tick(env, X + 300 * k, d, on_portfolio_done=boom)
        assert rep.status == "wakeup_failed"
    ex = [a for a in pl(env, "alert") if a["code"] == "wakeup_exception"]
    assert len(ex) == 1 and ex[0]["message"].startswith(f"[wakeup {X}] ")
    assert [c for c in codes(env) if c[1] == "wakeup_resumed"] == [("info", "wakeup_resumed")]
    assert wakeup_events(env) == ["wakeup_started"]
    # The wake-up counts toward the cap and the cooldown as soon as wakeup_started is written.
    assert pl(env, "wakeup_started") == [{"wakeup": X, "trigger": pl(env, "wakeup_started")[0]["trigger"]}]


def test_watch_wakeup_contains_only_one_started_wakeup(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X)
    tick(env, X, d)
    p = of(env, "watch")[-1]["payload"]
    assert p["wakeup"] == pl(env, "wakeup_started")[0]["trigger"] and p["refused"] is None


# ---------------------------------------------------------------------------------------------- the wake-up


def test_wakeup_wakes_all_llms_and_random_not_references_without_equity(tmp_path: Path):
    x = random_tick()
    n_random = random.Random(seed_for(x, 0)).randrange(3)
    env = make_env(tmp_path)
    d = prepare(env, x)
    refs_before = {p: replay(env.events())[p] for p in REFS}
    equity_before = len(of(env, "equity"))
    fills_before = len(of(env, "fill"))
    rep = tick(env, x, d)
    assert rep.wakeup == "completed"
    types = [e["type"] for e in env.events()]
    assert types.count("wakeup_started") == types.count("wakeup_completed") == 1
    assert types.index("wakeup_started") < types.index("wakeup_completed")
    after = env.events()[max(i for i, t in enumerate(types) if t == "wakeup_started") :]
    qs = [e for e in after if e["type"] == "wakeup_quote"]
    assert len(qs) == 6 and not [e for e in after if e["type"] == "quote"]
    assert max(i for i, e in enumerate(after) if e["type"] == "wakeup_quote") < min(
        i for i, e in enumerate(after) if e["type"] in ("decision_requested", "intent")
    )
    assert {e["payload"]["symbol"]: e["payload"]["bid"] for e in qs}[BTC] == up(300) * 9995 // 10000
    # ALL the LLMs of the config decide, Fable included, with the wake-up context.
    got = {p["portfolio"] for p in pl(env, "decision_received") if p["cycle"] == x}
    assert got == set(LLM_ALL)
    for p in LLM_ALL:
        assert d[p].snaps[-1]["context"]["type"] == "wakeup" and d[p].snaps[-1]["cycle_ts"] == x
    # Random: its draw intents, via riskd; references: nothing.
    own = [p for p in pl(env, "intent") if p["cycle"] == x]
    assert len([p for p in own if p["portfolio"] == "benchmark:random"]) == n_random
    assert {p["portfolio"] for p in own} <= {"benchmark:random", *LLM_ALL}
    assert {p["intent_id"] for p in own} <= {p["intent_id"] for p in pl(env, "risk_verdict")}
    assert {p: replay(env.events())[p] for p in REFS} == refs_before
    assert not [f for f in pl(env, "fill")[fills_before:] if f["portfolio"] in REFS]
    assert len(of(env, "equity")) == equity_before  # no equity at wake-up
    assert d[HAIKU].snaps[-1]["schema_version"] == SCHEMA_VERSION == "2"
    check_journal(env)


def test_round_context_and_budget_shared_between_cycles_and_wakeups(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X, deciders(buy_eth_at_wakeup))
    tick(env, X, d)
    cycle(env, 1, d)
    snaps = d[HAIKU].snaps
    assert [s["context"]["type"] for s in snaps] == ["scheduled_round", "wakeup", "scheduled_round"]
    assert snaps[0]["context"] == {"type": "scheduled_round", "next_scheduled_round_ts": T0 + H4 + 300}
    trig = {"type": "move", "symbol": BTC, "variation_bp": 300, "window_s": 3600}
    assert snaps[1]["context"] == {"type": "wakeup", "trigger": trig, "next_scheduled_round_ts": T0 + H4 + 300}
    assert snaps[2]["context"] == {"type": "scheduled_round", "next_scheduled_round_ts": T0 + 2 * H4 + 300}
    # The wake-up decisions are in recent_decisions of the next cycle, marked "wakeup".
    rd = snaps[2]["recent_decisions"]
    assert [(r["cycle"], r["llm_round"]) for r in rd] == [(T0, "scheduled_round"), (X, "wakeup")]
    assert d[HAIKU].spent == [0, 1500, 3000] and d[SONNET].spent == [0, 1500, 3000]  # daily budget shared
    assert "woken between two appointments" in load_system_prompt()


# ---------------------------------------------------------------------------------------------- 8. PRICE_SANITY at wake-up


def test_price_sanity_at_wakeup_compares_to_last_trade_price(tmp_path: Path):
    env = make_env(tmp_path)

    def plan(i, snap):
        return [action(BTC, size=10, stop=5, move=8)] if snap["context"]["type"] == "wakeup" else None

    d = prepare(env, X, deciders(plan), bp=500)  # BTC +5%: more than 3% away from the 4 h close
    close = max((b for b in env.kraken.ohlc(BTC, "XBTEUR", H4, None)), key=lambda b: b.ts).close
    assert abs(up(500) - close) * 10_000 > 300 * close  # the 4 h close would have triggered PRICE_SANITY
    rep = tick(env, X, d)
    assert rep.wakeup == "completed" and watch_p(env)["closes_1m"][BTC] == up(500)
    intent = next(p for p in pl(env, "intent") if p["cycle"] == X and p["portfolio"] == HAIKU)
    verdict = next(v for v in pl(env, "risk_verdict") if v["intent_id"] == intent["intent_id"])
    assert verdict["approved"] and "PRICE_SANITY" not in verdict["reasons"]
    assert BTC in replay(env.events())[HAIKU].positions
    check_journal(env)


def test_erroneous_ticker_blocks_entries_at_wakeup(tmp_path: Path):
    env = make_env(tmp_path)

    def plan(i, snap):
        return [action(BTC, size=10, stop=5, move=8)] if snap["context"]["type"] == "wakeup" else None

    d = prepare(env, X, deciders(plan), bp=300)
    set_ticker_btc(env, up(700))  # ticker +7% (accepted: less than 15% from the previous tick), trades at +3%
    rep = tick(env, X, d)
    assert rep.wakeup == "completed" and rep.rejected == {} and watch_p(env)["closes_1m"][BTC] == up(300)
    intent = next(p for p in pl(env, "intent") if p["cycle"] == X and p["portfolio"] == HAIKU)
    verdict = next(v for v in pl(env, "risk_verdict") if v["intent_id"] == intent["intent_id"])
    assert not verdict["approved"] and "PRICE_SANITY" in verdict["reasons"]
    assert not [f for f in pl(env, "fill") if f["portfolio"] == HAIKU and f["side"] == "buy"]


def test_symbol_without_quote_gives_no_quote_verdict_never_a_silent_continue(tmp_path: Path):
    env = make_env(tmp_path)

    def plan(i, snap):
        return [action(BTC, size=10, stop=5, move=8)] if snap["context"]["type"] == "wakeup" else None

    d = prepare(env, X, deciders(plan), bp=300)
    env.kraken.override[BTC] = (0, 10)  # invalid ticker: no accepted quote; trades trigger the wake-up
    rep = tick(env, X, d)
    assert rep.wakeup == "completed" and rep.rejected == {BTC: "invalid"}
    intent = next(p for p in pl(env, "intent") if p["cycle"] == X and p["portfolio"] == HAIKU)
    verdict = next(v for v in pl(env, "risk_verdict") if v["intent_id"] == intent["intent_id"])
    assert verdict == {**verdict, "approved": False, "reasons": ["NO_QUOTE"], "qty": 0, "reserved_ueur": 0}
    states = [(o["state"], o["detail"]) for o in pl(env, "order_state") if o["order_id"] == intent["intent_id"]]
    assert states == [("RISK_REJECTED", "NO_QUOTE")]
    assert BTC not in replay(env.events())[HAIKU].positions and BTC not in {q["payload"]["symbol"] for q in of(env, "wakeup_quote")}
    check_journal(env)


# ---------------------------------------------------------------------------------------------- 9. kill switch


def test_circuit_breaker_during_a_wakeup_entries_refused(tmp_path: Path):
    x = random_tick()

    def plan(i, snap):
        if snap["context"]["type"] == "wakeup":
            return [action("ETH/EUR")]
        return [action("LINK/EUR")] if i == 0 else None

    env = make_env(tmp_path)
    d = prepare(env, x, deciders(plan))
    assert "LINK/EUR" in replay(env.events())[HAIKU].positions
    env.paths.kill.parent.mkdir(parents=True, exist_ok=True)
    env.paths.kill.touch()
    n_fills = len(of(env, "fill"))
    assert tick(env, x, d).wakeup == "completed"
    assert [k["active"] for k in pl(env, "kill_switch")] == [True]
    new = pl(env, "fill")[n_fills:]
    assert new and all(f["side"] == "sell" for f in new)  # no entry, from anyone
    assert f"exit:{HAIKU}:LINK/EUR:{x}:kill_switch" in {f["order_id"] for f in new}
    skipped = {p["portfolio"]: p["reason"] for p in pl(env, "decision_skipped") if p["cycle"] == x}
    assert skipped[HAIKU] == skipped[SONNET] == skipped[FABLE] == "kill_switch"
    verdicts = {v["intent_id"]: v for v in pl(env, "risk_verdict")}
    buys = [p for p in pl(env, "intent") if p["cycle"] == x and p["side"] == "buy"]
    assert all(not verdicts[p["intent_id"]]["approved"] and "KILL_SWITCH" in verdicts[p["intent_id"]]["reasons"] for p in buys)
    assert not replay(env.events())[HAIKU].positions
    check_journal(env)


def kill_during_decide(env: Env, kind: str):
    def plan(i, snap):
        env.paths.kill.parent.mkdir(parents=True, exist_ok=True)
        env.paths.kill.touch()  # armed during the LLM call
        return [action("ETH/EUR")]

    return plan


def test_kill_armed_during_the_llm_call_blocks_the_buy_at_wakeup(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X, deciders())
    d[HAIKU].plan = lambda i, s: (env.paths.kill.parent.mkdir(parents=True, exist_ok=True), env.paths.kill.touch(), [action("ETH/EUR")])[2]
    assert tick(env, X, d).wakeup == "completed"
    intent = next(p for p in pl(env, "intent") if p["cycle"] == X and p["portfolio"] == HAIKU)
    verdict = next(v for v in pl(env, "risk_verdict") if v["intent_id"] == intent["intent_id"])
    assert not verdict["approved"] and "KILL_SWITCH" in verdict["reasons"]
    assert not [f for f in pl(env, "fill") if f["portfolio"] == HAIKU and f["side"] == "buy"]


def test_kill_armed_during_the_llm_call_blocks_the_buy_at_cycle(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders()
    d[HAIKU].plan = lambda i, s: (env.paths.kill.parent.mkdir(parents=True, exist_ok=True), env.paths.kill.touch(), [action("ETH/EUR")])[2]
    assert cycle(env, 0, d).status == "completed"
    intent = next(p for p in pl(env, "intent") if p["portfolio"] == HAIKU)
    verdict = next(v for v in pl(env, "risk_verdict") if v["intent_id"] == intent["intent_id"])
    assert not verdict["approved"] and "KILL_SWITCH" in verdict["reasons"]
    assert not [f for f in pl(env, "fill") if f["portfolio"] == HAIKU and f["side"] == "buy"]


def test_lock_waits_and_systemd_delays(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    assert cyc.LOCK_WAIT_S == 600 and cyc.FLATTEN_LOCK_WAIT_S == 120
    waits: list[float] = []

    @contextmanager
    def fake_lock(paths, wait_s=0.0):
        waits.append(wait_s)
        yield

    monkeypatch.setattr(cyc, "cycle_lock", fake_lock)
    env = make_env(tmp_path)
    cycle(env, 0)
    cyc.flatten_now(env.paths, env.clients, T0 + 900)
    cycle(env, 1)
    assert waits == [600.0, 120.0, 600.0]  # cycle, immediate flattening, cycle
    unit = lambda n: (REPO / "ops" / "systemd" / n).read_text()
    assert "TimeoutStartSec=1500" in unit("arena-cycle.service")
    assert "TimeoutStartSec=600" in unit("arena-watch.service")
    assert "OnCalendar=*-*-* *:00/5:30 UTC" in unit("arena-watch.timer")
    site = unit("arena-site-build.service")
    assert "Type=oneshot" in site and site.count("ExecStart=") == 1 and site.endswith("arena build-site\nTimeoutStartSec=600\nNice=10\n")


# ---------------------------------------------------------------------------------------------- 6. resume and abandonment


def crashed_wakeup(env: Env, d: dict, x: int, after: str = HAIKU):
    def boom(p: str) -> None:
        if p == after:
            raise RuntimeError("simulated crash")

    rep = tick(env, x, d, on_portfolio_done=boom)
    assert rep.status == "wakeup_failed" and not rep.ok and "simulated crash" in rep.error
    assert wakeup_events(env) == ["wakeup_started"]
    return rep


def test_resuming_an_interrupted_wakeup_without_double_decision_or_double_fill(tmp_path: Path):
    x = random_tick()
    clean = make_env(tmp_path, "clean")
    dc = prepare(clean, x, deciders(buy_eth_at_wakeup))
    assert tick(clean, x, dc).wakeup == "completed"
    for after in (HAIKU, "benchmark:random"):
        env = make_env(tmp_path, f"crash-{after[-3:]}")
        d = prepare(env, x, deciders(buy_eth_at_wakeup))
        crashed_wakeup(env, d, x, after)
        assert ("panic", "wakeup_exception") in codes(env)
        rep = tick(env, x + 300, d)
        assert rep.wakeup == "resumed" and rep.status == "done"
        assert wakeup_events(env) == ["wakeup_started", "wakeup_completed"]
        assert pl(env, "wakeup_completed") == [{"wakeup": x}]
        assert ("info", "wakeup_resumed") in codes(env)
        assert of(env, "watch")[-1]["payload"]["wakeup"] is None  # the resume does not start a new wake-up
        ids = [f["payload"]["order_id"] for f in of(env, "fill")]
        assert len(ids) == len(set(ids)), "double fill after the resume"
        assert sorted(ids) == sorted(f["payload"]["order_id"] for f in of(clean, "fill"))
        assert replay(env.events()) == replay(clean.events())
        for p in LLM_ALL:  # a single decision per portfolio and per wake-up
            assert len([r for r in pl(env, "decision_received") if r["cycle"] == x and r["portfolio"] == p]) == 1
        if after == HAIKU:  # its decision was journaled before the crash: never asked again at the resume
            assert d[HAIKU].calls == 2  # cycle 0 + wake-up
        # 7. The wake-up quotes are reread at the resume, not journaled a second time.
        assert len(of(env, "wakeup_quote")) == 6
        check_journal(env)


def test_resume_on_the_original_quotes_never_rewritten(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X, deciders(buy_eth_at_wakeup))
    d[SONNET].plan = buy_eth_at_wakeup  # Sonnet decides at the resume, Haiku before the crash
    crashed_wakeup(env, d, X, HAIKU)
    origin = {e["payload"]["symbol"]: [e["payload"]["bid"], e["payload"]["ask"]] for e in of(env, "wakeup_quote")}
    assert origin["ETH/EUR"] == watch_p(env)["quotes"]["ETH/EUR"]
    eth = origin["ETH/EUR"]
    env.kraken.override["ETH/EUR"] = (eth[0] * 101 // 100, eth[1] * 101 // 100)  # the market has moved 1% since
    rep = tick(env, X + 300, d)
    assert rep.wakeup == "resumed"
    again = {e["payload"]["symbol"]: [e["payload"]["bid"], e["payload"]["ask"]] for e in of(env, "wakeup_quote")}
    assert len(of(env, "wakeup_quote")) == 6 and again == origin  # nothing rewritten
    fills = {f["portfolio"]: f for f in pl(env, "fill") if f["side"] == "buy" and f["symbol"] == "ETH/EUR" and f["ts"] == X}
    assert HAIKU in fills and SONNET in fills
    assert fills[HAIKU]["price_ueur"] == fills[SONNET]["price_ueur"]  # all models saw the same quotes
    assert fills[SONNET]["price_ueur"] < eth[1] * 101 // 100  # and not those of the resume tick
    check_journal(env)


def test_resume_after_crash_during_quote_write_completes_from_the_original_tick(tmp_path: Path, monkeypatch):
    env = make_env(tmp_path)
    d = prepare(env, X, deciders(buy_eth_at_wakeup))
    real, n = Journal.append, []

    def flaky(self, type, payload, ts):
        if type == "wakeup_quote" and len(n) == 2:
            raise RuntimeError("crash au 3e quote")
        if type == "wakeup_quote":
            n.append(payload.symbol)
        return real(self, type, payload, ts)

    monkeypatch.setattr(Journal, "append", flaky)
    assert tick(env, X, d).status == "wakeup_failed"
    monkeypatch.setattr(Journal, "append", real)  # (no undo: it would also remove the conftest guards)
    first = [e["payload"] for e in of(env, "wakeup_quote")]
    assert [q["symbol"] for q in first] == n and len(n) == 2
    origin = watch_p(env)["quotes"]
    env.kraken.override["SOL/EUR"] = (1, 2)  # the market has changed since (and it is invalid): no effect on the resume
    rep = tick(env, X + 300, d)
    assert rep.wakeup == "resumed"
    after = [e["payload"] for e in of(env, "wakeup_quote")]
    assert after[:2] == first and len(after) == 6  # never rewritten; the 4 missing ones completed
    assert {q["symbol"]: [q["bid"], q["ask"]] for q in after} == origin  # from the accepted quotes of the originating tick
    assert {q["ts"] for q in after[2:]} == {X}
    check_journal(env)


def test_wakeup_abandoned_after_30_minutes_and_resumed_before(tmp_path: Path):
    x = random_tick()
    env = make_env(tmp_path, "late")
    d = prepare(env, x)
    crashed_wakeup(env, d, x)
    n_fills = len(of(env, "fill"))
    rep = tick(env, x + 2100, d)  # 35 min later: too late
    assert rep.wakeup == "abandoned" and rep.status == "done"
    assert wakeup_events(env) == ["wakeup_started", "wakeup_abandoned"]
    assert pl(env, "wakeup_abandoned") == [{"wakeup": x}]
    assert ("action", "wakeup_abandoned") in codes(env)
    assert len(of(env, "fill")) == n_fills
    tick(env, x + 2400, d)
    assert wakeup_events(env) == ["wakeup_started", "wakeup_abandoned"]  # no repeated abandonment
    assert len([c for c in codes(env) if c[1] == "wakeup_abandoned"]) == 1
    check_journal(env)
    env2 = make_env(tmp_path, "exact")
    d2 = prepare(env2, x)
    crashed_wakeup(env2, d2, x)
    assert tick(env2, x + 1800, d2).wakeup == "resumed"  # exactly 30 min: still resumed
    assert wakeup_events(env2) == ["wakeup_started", "wakeup_completed"]


def test_wakeup_is_abandoned_not_resumed_if_a_cycle_finished_since(tmp_path: Path):
    x = random_tick()
    env = make_env(tmp_path)
    d = prepare(env, x)
    crashed_wakeup(env, d, x)
    Journal(env.paths.journal).append("cycle_completed", {"cycle": T0 + H4}, x + 100)
    rep = tick(env, x + 300, d)  # within 30 min, but a cycle completed after wakeup_started
    assert rep.wakeup == "abandoned" and wakeup_events(env) == ["wakeup_started", "wakeup_abandoned"]
    assert ("info", "wakeup_resumed") not in codes(env)


@pytest.mark.parametrize("cut", ["stop_set", "fill"])
def test_abandon_repairs_the_interrupted_round(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cut: str):
    env = make_env(tmp_path)
    d = prepare(env, X, deciders(buy_eth_at_wakeup))
    real, hit = Journal.append, []

    def flaky(self, type, payload, ts):
        if type == cut and ts == X and not hit:
            hit.append(1)
            raise RuntimeError("crash between two writes")
        return real(self, type, payload, ts)

    monkeypatch.setattr(Journal, "append", flaky)
    assert tick(env, X, d).status == "wakeup_failed"
    monkeypatch.setattr(Journal, "append", real)  # (no undo: it would also remove the conftest guards)
    intent = next(p for p in pl(env, "intent") if p["cycle"] == X and p["portfolio"] == HAIKU)
    oid = intent["intent_id"]
    states = lambda: [s["state"] for s in pl(env, "order_state") if s["order_id"] == oid]
    if cut == "stop_set":  # fill written, stop_set missing
        assert "ETH/EUR" in replay(env.events())[HAIKU].positions
        assert replay(env.events())[HAIKU].positions["ETH/EUR"].stop_ueur is None
        assert states() == ["SUBMITTING", "ACKED"]
    else:  # ACKED order without fill
        assert "ETH/EUR" not in replay(env.events())[HAIKU].positions
        assert states() == ["SUBMITTING", "ACKED"]
    rep = tick(env, X + 2100, d)
    assert rep.wakeup == "abandoned"
    st = replay(env.events())[HAIKU]
    if cut == "stop_set":
        pos = st.positions["ETH/EUR"]
        assert pos.stop_ueur is not None and pos.stop_ueur > 0  # the position has its stop
        assert pl(env, "stop_set")[-1]["symbol"] == "ETH/EUR"
        assert states() == ["SUBMITTING", "ACKED", "FILLED"]
    else:
        assert "ETH/EUR" not in st.positions
        assert states() == ["SUBMITTING", "ACKED", "UNKNOWN", "CANCELED"]
    ids = [f["order_id"] for f in pl(env, "fill")]
    assert len(ids) == len(set(ids))
    assert wakeup_events(env) == ["wakeup_started", "wakeup_abandoned"]
    check_journal(env)


# ---------------------------------------------------------------------------------------------- cycle after wake-ups


def run_scenario(env: Env) -> dict:
    d = prepare(env, X, deciders(buy_eth_at_wakeup))
    tick(env, X, d)
    env.kraken.override.clear()
    cycle(env, 1, d)
    return d


def test_cycle_after_wakeups_stays_deterministic_and_leaves_references_untouched(tmp_path: Path):
    a, b, c = make_env(tmp_path, "a"), make_env(tmp_path, "b"), make_env(tmp_path, "c")
    run_scenario(a)
    run_scenario(b)
    assert verify(a.paths.journal).head_hash == verify(b.paths.journal).head_hash
    cycle(c, 0)  # without watch or wake-up
    cycle(c, 1)
    season_info, sc = replay(a.events()), replay(c.events())
    assert {p: season_info[p] for p in REFS} == {p: sc[p] for p in REFS}
    eq1 = [e["payload"]["portfolio"] for e in a.of_type("equity") if e["payload"]["cycle"] == T0 + H4]
    assert sorted(eq1) == sorted(sc)
    assert len(a.of_type("cycle_completed")) == 2
    check_journal(a)


def test_replay_and_verify_after_a_day_of_watch_and_wakeups(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X, deciders(buy_eth_at_wakeup))
    tick(env, X, d)
    env.kraken.override.clear()
    for k in range(1, 12):
        tick(env, X + 300 * k, d)
    cycle(env, 1, d)
    for k in range(1, 6):
        tick(env, T0 + H4 + 600 + 300 * k, d)
    assert len(of(env, "watch")) == 1 + 1 + 11 + 5
    check_journal(env)


# ---------------------------------------------------------------------------------------------- 11. operations


def test_watch_data_one_alert_at_outage_start_one_info_at_recovery(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    size = env.paths.journal.stat().st_size
    env.kraken.fail_ticker = True
    for k in range(2):
        assert tick(env, T0 + 600 + 300 * k).status == "failed"
    assert env.paths.journal.stat().st_size == size and not [c for c in codes(env) if c[1] == "watch_data"]
    tick(env, T0 + 1200)  # third consecutive failure: start of the outage
    assert [c for c in codes(env) if c[1] == "watch_data"] == [("action", "watch_data")]
    for k in range(10):  # nothing between the start and the recovery, even hours later
        tick(env, T0 + 1500 + 1200 * k)
    assert [c for c in codes(env) if c[1] == "watch_data"] == [("action", "watch_data")]
    assert (env.paths.var / "watch_failures").read_text() == "13"
    env.kraken.fail_ticker = False
    assert tick(env, T0 + 20_000).status == "done"
    assert [c for c in codes(env) if c[1] == "watch_data"] == [("action", "watch_data"), ("info", "watch_data")]
    assert not (env.paths.var / "watch_failures").exists()
    env.kraken.fail_ticker = True  # new outage: the counter restarts from zero
    tick(env, T0 + 20_300)
    tick(env, T0 + 20_600)
    assert len([c for c in codes(env) if c[1] == "watch_data"]) == 2
    tick(env, T0 + 20_900)
    assert len([c for c in codes(env) if c[1] == "watch_data"]) == 3
    check_journal(env)


def test_broken_journal_nothing_written_code_1_one_panic_alert_per_hour(tmp_path: Path):
    env = make_env(tmp_path, secrets={"ntfy_url": "https://ntfy.example/arena"})
    cycle(env, 0)
    p = env.paths.journal
    lines = p.read_bytes().split(b"\n")
    lines[3] = lines[3].replace(b'"type"', b'"tYpe"', 1)
    p.write_bytes(b"\n".join(lines))
    before = p.read_bytes()
    env.requests.clear()
    rep = tick(env, T0 + 600)
    assert rep.status == "refused" and not rep.ok and p.read_bytes() == before
    sent = lambda: [(r.method, str(r.url), r.headers.get("priority")) for r in env.requests]
    assert sent() == [("POST", "https://ntfy.example/arena", "5")]
    tick(env, T0 + 900)
    tick(env, T0 + 600 + 3599)
    assert len(sent()) == 1 and p.read_bytes() == before
    tick(env, T0 + 600 + 3600)
    assert len(sent()) == 2 and p.read_bytes() == before


def test_the_cycle_alerts_once_per_watch_absence(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    cycle(env, 1)
    assert "watch_absent" not in [c[1] for c in codes(env)]  # never any watch: the timer is not supposed to run
    tick(env, T0 + H4 + 600)
    cycle(env, 2)  # last tick 4 h away
    assert [c for c in codes(env) if c[1] == "watch_absent"] == [("action", "watch_absent")]
    cycle(env, 3)  # still absent: no second alert
    assert len([c for c in codes(env) if c[1] == "watch_absent"]) == 1
    tick(env, T0 + 3 * H4 + 600)  # the watch comes back then stops again
    cycle(env, 4)
    assert len([c for c in codes(env) if c[1] == "watch_absent"]) == 2
    # Recent watch (under 30 min): no alert.
    tick(env, T0 + 4 * H4 + 900)
    n = len(codes(env))
    env.clock.now = env.now_of(5)
    tick(env, env.now_of(5) - 330)  # HH:00:00 + ... tick of the slot preceding the cycle
    cycle(env, 5)
    assert len([c for c in codes(env) if c[1] == "watch_absent"]) == 2 and len(codes(env)) >= n


def test_smoke_snapshot_uses_the_same_next_scheduled_round_as_the_cycle(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    snap = cyc.smoke_snapshot(env.paths, env.clients, HAIKU, T0 + H4 + 600)
    assert snap["context"] == cyc.scheduled_round_context(T0 + H4, load_config(env.paths.config))
    assert snap["context"] == {"type": "scheduled_round", "next_scheduled_round_ts": T0 + 2 * H4 + 300}


# ---------------------------------------------------------------------------------------------- config


def test_watch_config_defaults_and_validation(tmp_path: Path):
    cfg = load_config(REPO / "config" / "arena.toml")
    v = cfg.watch
    assert (v.tick_s, v.move_threshold_bp, v.move_window_s) == (300, 300, 3600)
    assert (v.cooldown_s, v.max_wakeups_per_day, v.pre_cycle_guard_s) == (3600, 6, 1800)
    text = (REPO / "config" / "arena.toml").read_text()
    without = re.sub(r"\[watch\].*?(?=\[\[instruments\]\])", "", text, flags=re.DOTALL)
    assert "[watch]" not in without
    p = tmp_path / "c.toml"
    p.write_text(without)
    assert load_config(p).watch == v  # table absent: default values
    p.write_text(text.replace("move_threshold_bp = 300", "move_threshold_bp = 150"))
    assert load_config(p).watch.move_threshold_bp == 150
    for bad in ("move_threshold_bp = 0", "cooldown_s = -1", 'tick_s = "300"', "tick_s = 7", "unknown = 1", "tick_s = 3.5"):
        key = bad.split(" = ")[0]
        mutated = re.sub(rf"^{key} = .*$", bad, text, flags=re.MULTILINE) if key != "unknown" else text.replace("[watch]", "[watch]\n" + bad)
        p.write_text(mutated)
        with pytest.raises(ConfigError):
            load_config(p)


# ---------------------------------------------------------------------------------------------- 10. CLI and site


def cli_args(env: Env) -> list[str]:
    return ["--var", str(env.paths.var), "--secrets", str(env.paths.secrets), "--config", str(env.paths.config),
            "--policy", str(env.paths.policy)]  # fmt: skip


def fake_systemctl(monkeypatch: pytest.MonkeyPatch, calls: list, error: Exception | None = None) -> None:
    """Replace subprocess.run for `systemctl` only (the cycle's git rev-parse keeps the real one)."""
    real = subprocess.run

    def run(cmd, **kw):
        if cmd[0] != "systemctl":
            return real(cmd, **kw)
        calls.append(cmd)
        if error is not None:
            raise error
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(cli.subprocess, "run", run)


def test_arena_watch_command_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []
    fake_systemctl(monkeypatch, calls)
    env = make_env(tmp_path)
    cycle(env, 0)

    def run(ts: int, *extra: str) -> int:
        env.clock.now = ts
        return cli.main([*cli_args(env), "watch", *extra], clients=env.clients, now=lambda: ts)

    assert run(T0 + 630) == 0
    assert run(T0 + 640) == 0  # already done
    with cycle_lock(env.paths):
        assert run(T0 + 930) == 0  # busy: code 0
    env.kraken.fail_ticker = True
    assert run(T0 + 1230) == 1  # no valid quote: code 1
    # Site rebuild after every written tick: only the first tick here.
    assert calls == [["systemctl", "--user", "start", "--no-block", "arena-site-build.service"]]


def test_after_a_wakeup_the_site_is_rebuilt_by_systemd_not_in_the_process(tmp_path: Path, monkeypatch):
    calls: list[list[str]] = []
    fake_systemctl(monkeypatch, calls)
    monkeypatch.setattr(cli, "_build_site", lambda *a, **k: pytest.fail("the site is no longer built inside the watch"))
    monkeypatch.setattr(cyc, "default_deciders", lambda cfg, paths: deciders())
    for name, extra, expected in [
        ("including", [], [["systemctl", "--user", "start", "--no-block", "arena-site-build.service"]]),
        ("without", ["--no-site"], []),
    ]:
        calls.clear()
        env = make_env(tmp_path, name)
        prepare(env, X)
        env.clock.now = X + 30
        assert cli.main([*cli_args(env), "watch", *extra], clients=env.clients, now=lambda: X + 30) == 0
        assert pl(env, "wakeup_completed") == [{"wakeup": X}]
        assert calls == expected


def test_site_is_rebuilt_after_each_written_tick_not_otherwise(tmp_path: Path, monkeypatch):
    """Rebuild after every written tick, not only after a wake-up."""
    calls: list = []
    fake_systemctl(monkeypatch, calls)
    env = make_env(tmp_path)
    cycle(env, 0)
    now = T0 + 630
    assert cli.main([*cli_args(env), "watch"], clients=env.clients, now=lambda: now) == 0
    assert calls == [["systemctl", "--user", "start", "--no-block", "arena-site-build.service"]]
    calls.clear()
    assert cli.main([*cli_args(env), "watch"], clients=env.clients, now=lambda: now) == 0  # same tick: nothing written
    assert calls == []
    assert cli.main([*cli_args(env), "watch", "--no-site"], clients=env.clients, now=lambda: now + 300) == 0
    assert calls == []


def test_failed_site_launch_is_ignored_and_not_in_the_journal(tmp_path: Path, monkeypatch, caplog):
    fake_systemctl(monkeypatch, [], FileNotFoundError("systemctl"))
    monkeypatch.setattr(cyc, "default_deciders", lambda cfg, paths: deciders())
    env = make_env(tmp_path)
    prepare(env, X)
    env.clock.now = X + 30
    n_alerts = len(codes(env))
    with caplog.at_level("WARNING", logger="arena.cli"):
        assert cli.main([*cli_args(env), "watch"], clients=env.clients, now=lambda: X + 30) == 0
    assert "site rebuild not started" in caplog.text
    assert len(codes(env)) == n_alerts  # nothing in the journal
    fake_systemctl(monkeypatch, [], subprocess.CalledProcessError(1, "systemctl"))
    cli._start_site_build()  # does not raise


# ---------------------------------------------------------------------------------------------- fix series: stops


def test_zero_volume_fill_candles_do_not_count(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    S = stop_of(env)
    base = base_close(env)
    for ts in (T0 + 840, T0 + 900, T0 + 960):  # three filler candles (volume 0) repeat a price below the stop
        env.kraken.bar_override[(BTC, ts)] = (S - 1, S - 1, S - 1, S - 1, 0)
    assert tick(env, T0 + 1200, d).stops == []
    env.kraken.bar_override[(BTC, T0 + 1020)] = (base, base, S - 1, base, 5)  # only one traded candle: insufficient
    assert tick(env, T0 + 1500, d).stops == []
    env.kraken.bar_override[(BTC, T0 + 1260)] = (base, base, S - 1, base, 5)  # two distinct traded candles
    env.kraken.bar_override[(BTC, T0 + 1320)] = (base, base, S - 1, base, 5)  # within the last 10 minutes
    r = T0 + 1800
    assert f"stop:{HAIKU}:{BTC}:watch:{r}" in tick(env, r, d).stops


def test_stop_window_starts_at_real_execution_time_not_opened_ts(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)  # fill dated T0 (opened_ts), actually executed at T0+300 (ts of the last `quote`)
    pos = replay(env.events())[HAIKU].positions[BTC]
    last_quote = max(e["ts"] for e in of(env, "quote") if e["payload"]["symbol"] == BTC)
    assert pos.opened_ts == T0 and last_quote == T0 + 300
    S = stop_of(env)
    base = base_close(env)
    set_trades(env, BTC, S - 1_000_000, at=T0)  # below the stop BEFORE the actual execution ...
    set_trades(env, BTC, base, at=T0 + 300)  # ... puis normal
    assert tick(env, T0 + 600, d).stops == []  # candles T0..T0+240 precede the purchase: ignored
    assert BTC in replay(env.events())[HAIKU].positions
    env2 = make_env(tmp_path, "e2")
    cycle(env2, 0, d)
    set_trades(env2, BTC, S - 1_000_000, at=T0 + 300)  # below the stop since the actual execution
    r = T0 + 600
    assert f"stop:{HAIKU}:{BTC}:watch:{r}" in tick(env2, r, d).stops


def test_stop_price_two_sources_max_capped_at_stop_without_ticker_close_only(tmp_path: Path):
    def run(tag: str, ticker: tuple[int, int] | None, close_off: int):
        env = make_env(tmp_path, tag)
        d = deciders(buy_btc_at_cycle_0)
        cycle(env, 0, d)
        S = stop_of(env)
        set_trades(env, BTC, S - close_off, at=T0 + 840)
        if ticker is not None:
            env.kraken.override[BTC] = (S - ticker[0], S - ticker[0] + 1_000_000)
        else:
            env.kraken.override[BTC] = (0, 10)  # unreadable (invalid) ticker: the 1-min close alone
        r = T0 + 1200
        assert f"stop:{HAIKU}:{BTC}:watch:{r}" in tick(env, r, d).stops
        return S, next(f["price_ueur"] for f in pl(env, "fill") if f["order_id"] == f"stop:{HAIKU}:{BTC}:watch:{r}")

    sell = lambda p: p * 9995 // 10_000 // 100_000 * 100_000
    S, px = run("close_low", (1_000_000, 0), 3_000_000)  # close S-3M, ticker S-1M: the higher of the two
    assert px == sell(S - 1_000_000)
    S, px = run("ticker_low", (3_000_000, 0), 1_000_000)  # close S-1M, ticker S-3M
    assert px == sell(S - 1_000_000)
    S, px = run("without_ticker", None, 2_000_000)
    assert px == sell(S - 2_000_000)
    S, px = run("ticker_high", (-600_000_000, 0), 2_000_000)  # very high erroneous ticker (> stop): at worst, sale at the stop
    assert px == S


def test_frozen_season_no_frozen_stop_fill_in_the_watch_event(tmp_path: Path):
    from tests.test_season import waiver, season_env, set_fee

    env = season_env(tmp_path, days=56)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    S = stop_of(env)
    set_trades(env, BTC, S - 1_000_000, at=T0 + 840)
    set_fee(env, 51)  # frozen config modified, without waiver
    n = len(of(env, "fill"))
    rep = tick(env, T0 + 1200, d)
    assert rep.stops == [] and len(of(env, "fill")) == n and BTC in replay(env.events())[HAIKU].positions
    assert watch_p(env)["freeze"] is True and watch_p(env)["stops"] == []
    assert [c for c in codes(env) if c[1] == "season_frozen"] == [("panic", "season_frozen")]
    tick(env, T0 + 1500, d)
    assert len([c for c in codes(env) if c[1] == "season_frozen"]) == 1  # a single alert
    waiver(env, "fee trial")  # waiver written: the stops resume
    r = T0 + 1800
    assert f"stop:{HAIKU}:{BTC}:watch:{r}" in tick(env, r, d).stops and watch_p(env)["freeze"] is False


# ---------------------------------------------------------------------------------------------- fix series: wake-up


def test_single_erroneous_stream_does_not_freeze_or_stop_a_portfolio_at_wakeup(tmp_path: Path):
    env = make_env(tmp_path)

    def plan(i, snap):
        if i == 0 and snap["context"]["type"] == "scheduled_round":
            return [action(BTC, size=20, stop=25), action("ETH/EUR", size=20, stop=25)]
        return None

    d = deciders(plan)
    cycle(env, 0, d)
    assert {BTC, "ETH/EUR"} <= set(replay(env.events())[HAIKU].positions)
    sol = env.kraken.minute_bar("SOL/EUR", T0).close
    set_trades(env, "SOL/EUR", sol * 103 // 100, at=X - 420)  # SOL +3% on trades: trigger
    for sym in (BTC, "ETH/EUR"):  # the BTC and ETH tickers show -14% (accepted), without trades
        q = env.kraken.ticker(sym, "x")
        env.kraken.override[sym] = (q.bid * 86 // 100, q.ask * 86 // 100)
    assert tick(env, X - 300, d).trigger is None
    rep = tick(env, X, d)
    assert rep.wakeup == "completed" and rep.rejected == {}
    assert not pl(env, "portfolio_frozen") and not pl(env, "portfolio_halted")  # without the trade floor: freeze at -5.6%
    assert set(replay(env.events())[HAIKU].positions) >= {BTC, "ETH/EUR"}
    check_journal(env)


# ---------------------------------------------------------------------------------------------- fix series: operations


def test_watch_ohlc_alert_fires_once_then_recovers(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    base = T0 + 600
    for k in range(2):  # 3 symbols failing for 2 ticks: no alert yet
        env.kraken.fail_ohlc = {BTC, "ETH/EUR", "SOL/EUR"}
        assert tick(env, base + 300 * k).rejected == dict.fromkeys(env.kraken.fail_ohlc, "ohlc")
    assert not [c for c in codes(env) if c[1] == "watch_ohlc"]
    tick(env, base + 600)  # 3rd consecutive tick
    for k in range(3, 6):  # nothing more as long as it lasts
        tick(env, base + 300 * k)
    assert [c for c in codes(env) if c[1] == "watch_ohlc"] == [("action", "watch_ohlc")]
    env.kraken.fail_ohlc = set()
    tick(env, base + 1800)
    assert [c for c in codes(env) if c[1] == "watch_ohlc"] == [("action", "watch_ohlc"), ("info", "watch_ohlc")]
    env.kraken.fail_ohlc = {BTC, "ETH/EUR"}  # only two symbols: below the threshold of 3
    for k in range(7, 11):
        tick(env, base + 300 * k)
    assert len([c for c in codes(env) if c[1] == "watch_ohlc"]) == 2


def test_tick_without_any_readable_candle_counts_in_watch_failures(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    env.kraken.fail_ohlc = set(SYMBOLS)
    for k in range(3):
        assert tick(env, T0 + 600 + 300 * k).status == "done"  # the tick is written (quotes, equity) all the same
        assert (env.paths.var / "watch_failures").read_text() == str(k + 1)
    assert [c for c in codes(env) if c[1] == "watch_data"] == [("action", "watch_data")]
    env.kraken.fail_ohlc = set()
    tick(env, T0 + 1800)
    assert not (env.paths.var / "watch_failures").exists()
    assert [c for c in codes(env) if c[1] == "watch_data"] == [("action", "watch_data"), ("info", "watch_data")]


def test_rate_limit_suspends_ohlc_calls_until_retry_after(tmp_path: Path):
    from arena.data import RateLimitedError
    from arena.data.kraken import KrakenError

    env = make_env(tmp_path)
    cycle(env, 0)
    env.kraken.ohlc_error = RateLimitedError("HTTP 429 from api.kraken.com", 900)
    n0 = env.kraken.ohlc_calls
    rep = tick(env, T0 + 600)
    assert rep.rejected == dict.fromkeys(SYMBOLS, "ohlc") and env.kraken.ohlc_calls == n0 + 1  # the first call is enough
    # Retry-After of 900 s capped at PAUSE_OHLC_MAX_S = 600 s: never hours without stops or trigger.
    assert (env.paths.var / "watch_ohlc_pause").read_text() == str(T0 + 630 + 600)
    env.kraken.ohlc_error = None
    n1 = env.kraken.ohlc_calls
    assert tick(env, T0 + 900).rejected == dict.fromkeys(SYMBOLS, "ohlc") and env.kraken.ohlc_calls == n1  # paused: no call
    assert tick(env, T0 + 1500).rejected == {} and env.kraken.ohlc_calls == n1 + 6  # pause expired (T0+1530 > T0+1500+30)
    env.kraken.ohlc_error = RateLimitedError("HTTP 429", None)  # without Retry-After: 300 s
    tick(env, T0 + 1800)
    assert (env.paths.var / "watch_ohlc_pause").read_text() == str(T0 + 1830 + 300)
    env.kraken.ohlc_error = KrakenError(["EAPI:Rate limit exceeded"])
    tick(env, T0 + 2400)
    assert (env.paths.var / "watch_ohlc_pause").read_text() == str(T0 + 2430 + 300)
    env.kraken.ohlc_error = RuntimeError("other error")  # an ordinary error suspends nothing
    tick(env, T0 + 3000)
    assert (env.paths.var / "watch_ohlc_pause").read_text() == str(T0 + 2430 + 300)


def test_asset_pairs_cached_24_h_falls_back_to_the_stale_cache(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    n0 = env.kraken.pairs_calls
    tick(env, T0 + 600)
    tick(env, T0 + 900)
    tick(env, T0 + 1200)
    assert env.kraken.pairs_calls == n0 + 1  # a single AssetPairs call for three ticks
    assert (env.paths.var / "asset_pairs.json").exists()
    tick(env, T0 + 600 + 86_400 - 60 * 5 - 30 + 30)  # less than 24 h after the first call (T0+630)
    assert env.kraken.pairs_calls == n0 + 1
    tick(env, T0 + 600 + 86_400 + 300)
    assert env.kraken.pairs_calls == n0 + 2  # stale cache: new call
    env.kraken.pairs_error = RuntimeError("AssetPairs down")
    rep = tick(env, T0 + 600 + 2 * 86_400 + 600)  # stale cache AND failing call: fall back to the cache
    assert rep.status == "done" and env.kraken.pairs_calls == n0 + 3
    env.kraken.pairs_error = None
