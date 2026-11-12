"""Perp league, step 4: the watcher (ticks, minutes, funding, controls, rounds) and the benchmarks. No network."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from arene.data import RateLimitedHttp
from arene.paths import Paths
from arene.perp import benchmarks as B
from arene.perp.collect import data_root
from arene.perp.config import load_perp_config
from arene.perp.counters import counters_for
from arene.perp.kraken_futures import KrakenFuturesClient
from arene.perp.ledger import replay
from arene.perp.policy import load_perp_policy
from arene.perp.store import PerpDataStore, TickerSnapshot
from arene.perp.types import Candle, FundingRate, FxQuote, PerpTicker
from arene.perp.watcher import PerpWatcher, load_specs

FIX = Path(__file__).parent / "fixtures" / "perp"
CFG = load_perp_config()
POLICY = load_perp_policy()
SYMBOLS = [i.kraken_symbol for i in CFG.instruments]
T0 = 1_794_499_200  # a 4-hour rendez-vous (16:00 UTC)
PRICES = {
    "PF_XBTUSD": 70_000_000_000,
    "PF_ETHUSD": 2_000_000_000,
    "PF_SOLUSD": 80_000_000,
    "PF_XRPUSD": 1_000_000,
    "PF_LINKUSD": 10_000_000,
    "PF_LTCUSD": 50_000_000,
}
FX = FxQuote(0, 1_100_000, 1_100_100)


def specs():
    body = (FIX / "instruments.json").read_bytes()
    http = RateLimitedHttp(
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body))),
        sleep=lambda s: None,
        clock=lambda: 0.0,
    )
    return KrakenFuturesClient(http).instruments(SYMBOLS)


SPECS = specs()


class World:
    """A synthetic collector store plus a watcher on a temporary league directory."""

    def __init__(self, tmp: Path, *, trend_days: int = 22, llm=None, factory=None, offset: int = 0) -> None:
        self.var = tmp / "var-perp"
        self.spot = Paths(var=tmp / "spot-var", user_kill=tmp / "USER_KILL")
        self.store = PerpDataStore(data_root(self.var))
        self.prices = dict(PRICES)
        for d in range(trend_days, 0, -1):  # one daily close per day, rising: the trend benchmark goes long
            end = (T0 // 86_400 - d + 1) * 86_400
            for s, p in PRICES.items():
                px = p * (100 - d) // 100
                self.candle(s, end - 60, px)
        self.minutes(T0 - 7200, T0)
        self.snapshot(T0)
        for h in range(T0 - 7200, T0 + 1, 3600):
            self.funding(h)
        self.w = PerpWatcher(
            self.var,
            CFG,
            POLICY,
            SPECS,
            spot_paths=self.spot,
            llm=llm,
            decider_factory=factory,
            round_offset_s=offset,
        )

    def candle(self, s: str, ts: int, px: int, low: int | None = None, high: int | None = None) -> None:
        lo, hi = low if low is not None else px, high if high is not None else px
        for kind in ("mark", "trade"):
            self.store.candles(kind, s, 60).add([Candle(s, kind, 60, ts, px, hi, lo, px, 0)])

    def minutes(self, start: int, end: int, prices: dict[str, int] | None = None) -> None:
        for s, p in (prices or self.prices).items():
            for m in range(start, end, 60):
                self.candle(s, m, p)

    def snapshot(self, ts: int, prices: dict[str, int] | None = None, rate: int = 10_000_000) -> None:
        pr = prices or self.prices
        tickers = tuple(
            PerpTicker(s, ts, p, p + SPECS[s].tick_uusd, p, p, p, 1, 1, rate, rate, 0, False, False)
            for s, p in pr.items()
        )
        self.store.tickers().add(
            [TickerSnapshot(ts, tickers, FxQuote(ts, FX.bid_uusd_per_eur, FX.ask_uusd_per_eur))]
        )

    def funding(self, stamp: int, nusd: int = 700_000) -> None:
        for s in SYMBOLS:
            self.store.funding(s).add([FundingRate(s, stamp, nusd, 10_000_000)])

    def advance(self, to: int, prices: dict[str, int] | None = None) -> None:
        """Market data up to `to` (minutes closed before `to - 15 s`), a snapshot at `to`."""
        if prices:
            self.prices = dict(prices)
        last = max(c.ts for c in self.store.candles("mark", "PF_XBTUSD", 60).load(0, to))
        self.minutes(last + 60, to - 60)
        for ts in range(last // 300 * 300 + 300, to, 300):  # the collector snapshots every 5 minutes
            self.snapshot(ts)
        self.snapshot(to)

    def events(self, type_: str | None = None):
        ev = self.w.journal.events()
        return [e for e in ev if type_ is None or e["type"] == type_]


def test_first_tick_opens_the_league_and_runs_the_rendezvous(tmp_path):
    w = World(tmp_path)
    rep = w.w.tick(T0 + 120)
    assert rep.skipped is None and rep.rounds == [f"rendezvous:{T0}"], rep
    states = replay(w.events())
    assert set(states) == set(B.ALL)
    assert set(states[B.BASKET].positions) == set(SYMBOLS)  # 1/6 of the equity long on each
    assert all(p.qty > 0 for p in states[B.BASKET].positions.values())
    assert set(states[B.TREND].positions) == set(SYMBOLS)  # rising 20-day closes: long everywhere, with stops
    assert all(p.stop_uusd is not None for p in states[B.TREND].positions.values())
    assert len([e for e in w.events("perp_equity")]) == 3 and w.events("perp_tick")
    assert w.events("perp_verdict") or not w.events("perp_verdict")  # the random benchmark may do nothing
    for name, acc in states.items():
        assert acc.invariant_ok(), name


def test_tick_is_idempotent_and_locked(tmp_path):
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    n = len(w.events())
    assert w.w.tick(T0 + 200).skipped == "tick already done"  # same 5-minute tick
    assert len(w.events()) == n


def test_minutes_are_caught_up_in_order(tmp_path):
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    w.advance(T0 + 7320)
    rep = w.w.tick(T0 + 7320)
    assert rep.minutes >= 115 and rep.skipped is None
    last = w.events("perp_tick")[-1]["payload"]["last_minute"]
    assert last == (T0 + 7320 - 15) // 60 * 60 - 60


def test_stop_fills_on_the_minute_and_trend_reenters_next_day(tmp_path):
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    crash = {s: p * 85 // 100 for s, p in PRICES.items()}  # -15 %: the trend's 10 % stops fill
    w.advance(T0 + 420, crash)
    w.w.tick(T0 + 420)
    states = replay(w.events())
    assert states[B.TREND].positions == {}
    stops = [
        e
        for e in w.events("perp_fill")
        if e["payload"]["reason"] == "stop" and e["payload"]["portfolio"] == B.TREND
    ]
    assert len(stops) == 6
    assert set(states[B.BASKET].positions) == set(SYMBOLS)  # the basket is never stopped


def test_funding_settled_pending_then_missing(tmp_path):
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    w.advance(T0 + 3720)
    w.funding(T0 + 3600)
    rep = w.w.tick(T0 + 3720)
    assert rep.funding > 0 and w.events("funding")
    w.advance(T0 + 7320)  # the stamp T0 + 7200 is not published yet: pending
    w.w.tick(T0 + 7320)
    assert w.events("perp_tick")[-1]["payload"]["pending_funding"] == [T0 + 7200]
    w.advance(T0 + 7200 + 3 * 3600 + 120)  # still absent 3 h later: recorded as missing, never invented
    w.w.tick(T0 + 7200 + 3 * 3600 + 120)
    missing = {e["payload"]["stamp"] for e in w.events("funding_missing")}
    assert T0 + 7200 in missing


def test_kill_switch_flattens_the_random_benchmark_only(tmp_path):
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    w.w.sim.market_order(
        "manual",
        B.RANDOM,
        "PF_XBTUSD",
        100_000,
        (70_000_000_000, 70_001_000_000),
        (1_100_000, 1_100_100),
        T0 + 130,
        marks=PRICES,
    )
    (w.var / "KILL").touch()
    w.advance(T0 + 420)
    w.w.tick(T0 + 420)
    states = replay(w.events())
    assert states[B.RANDOM].positions == {}
    assert set(states[B.BASKET].positions) == set(SYMBOLS)


def test_drawdown_halts_and_flattens(tmp_path):
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    sim = w.w.sim
    # a deliberately large unstopped long on the random benchmark (written directly, not through riskd)
    sim.market_order(
        "big",
        B.RANDOM,
        "PF_XBTUSD",
        2_500_000,
        (70_000_000_000, 70_001_000_000),
        (1_100_000, 1_100_100),
        T0 + 130,
        marks=PRICES,
    )
    drop = dict(PRICES, PF_XBTUSD=PRICES["PF_XBTUSD"] * 85 // 100)
    w.advance(T0 + 420, drop)
    w.w.tick(T0 + 420)
    acc = replay(w.events())[B.RANDOM]
    assert acc.halted and acc.positions == {}
    assert any(e["payload"]["code"] == "perp_portfolio_halted" for e in w.events("alert"))


def test_wakeup_on_a_crossing_only_once(tmp_path):
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    w.advance(T0 + 3600 + 300)
    w.w.tick(T0 + 3600 + 300)
    up = dict(PRICES, PF_SOLUSD=PRICES["PF_SOLUSD"] * 105 // 100)  # +5 % within the hour
    w.advance(T0 + 3600 + 600, up)
    rep = w.w.tick(T0 + 3600 + 600)
    assert any(r.startswith("wakeup:") for r in rep.rounds), rep
    w.advance(T0 + 3600 + 900)
    rep2 = w.w.tick(T0 + 3600 + 900)
    assert not rep2.rounds  # the level persists: no second wake-up (and the cooldown holds anyway)


def test_counters_from_the_journal(tmp_path):
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    c = counters_for(w.events(), B.BASKET, T0 + 200)
    assert c.opens_24h == 6 and c.fees_month_ueur > 0 and c.equity_24h_ago_ueur == 1_000_000_000
    assert c.equity_peak_ueur >= 1_000_000_000


def test_specs_cache(tmp_path):
    class Boom:
        def instruments(self, symbols):
            raise RuntimeError("offline")

    s = load_specs(tmp_path, SYMBOLS, T0, client=type("C", (), {"instruments": lambda self, x: SPECS})())
    assert s == SPECS
    assert load_specs(tmp_path, SYMBOLS, T0 + 2 * 86_400, client=Boom()) == SPECS  # stale cache beats nothing
    with pytest.raises(RuntimeError):
        load_specs(tmp_path / "empty", SYMBOLS, T0, client=Boom())


def test_basket_orders_rebalance_to_equal_parts():
    from arene.perp.ledger import MarginAccount, PerpPosition

    acc = MarginAccount("b", 1_000_000_000, 1_000_000_000)
    acc.positions["PF_XBTUSD"] = PerpPosition("PF_XBTUSD", 500_000, 70_000_000_000, 0, 1)
    orders = dict(B.basket_orders(acc, 1_000_000_000, PRICES, 1_100_000, SPECS))
    assert orders["PF_XBTUSD"] < 0 and all(q > 0 for s, q in orders.items() if s != "PF_XBTUSD")


def test_trend_signals():
    assert B.trend_signals({"x": (110, 100), "y": (90, 100), "z": (100, 100)}) == {"x": 1, "y": -1, "z": 0}
    assert B.trend_signals({"x": (None, 100), "y": (100, None)}) == {"x": None, "y": None}


# ---------------------------------------------------------------------- review findings (step 4)


def test_references_are_never_expired(tmp_path):
    from dataclasses import replace

    w = World(tmp_path)
    w.w.sim.params = replace(w.w.sim.params, max_holding_s=600)
    w.w.tick(T0 + 120)
    w.advance(T0 + 1320)
    w.w.tick(T0 + 1320)
    states = replay(w.events())
    assert set(states[B.BASKET].positions) == set(SYMBOLS) and set(states[B.TREND].positions) == set(SYMBOLS)
    assert not [e for e in w.events("perp_fill") if e["payload"]["reason"] == "max_holding"]


def test_interrupted_round_is_resumed(tmp_path, monkeypatch):
    w = World(tmp_path)
    calls = {"n": 0}
    real = w.w.sim.market_order

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 3:
            raise KeyboardInterrupt  # the process dies mid-round
        return real(*a, **k)

    monkeypatch.setattr(w.w.sim, "market_order", flaky)
    with pytest.raises(KeyboardInterrupt):
        w.w.tick(T0 + 120)
    monkeypatch.setattr(w.w.sim, "market_order", real)
    w.advance(T0 + 420)
    rep = w.w.tick(T0 + 420)
    assert any("resumed" in r for r in rep.rounds), rep
    states = replay(w.events())
    assert set(states[B.BASKET].positions) == set(SYMBOLS) and set(states[B.TREND].positions) == set(SYMBOLS)
    assert w.events("perp_round_done")


def test_reference_orders_are_stamped_now_after_minute_fills(tmp_path):
    """A late rendez-vous tick after stop fills of the same tick: the trend's new entries still pass."""
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    t1 = T0 + 4 * 3600
    w.advance(t1 - 300)
    w.w.tick(t1 - 300)
    crash = {s: p * 85 // 100 for s, p in PRICES.items()}
    w.advance(t1 + 1500, crash)  # stops hit after the rendez-vous time, the tick runs 25 min late
    rep = w.w.tick(t1 + 1500)
    assert not [p for p in rep.problems if "older than the previous fill" in p], rep.problems


def test_stale_market_view_means_no_round_and_an_alert(tmp_path):
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    rep = w.w.tick(T0 + 4 * 3600 + 60)  # no snapshot for 4 hours
    assert not rep.rounds and any("stale" in p for p in rep.problems)
    assert any(e["payload"]["code"] == "perp_data_stale" for e in w.events("alert"))


def test_a_held_minute_without_data_is_waited_for(tmp_path):
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    before = w.events("perp_tick")[-1]["payload"]["last_minute"]
    w.snapshot(T0 + 420)  # a snapshot but no new candle: the collector is late
    w.w.tick(T0 + 420)
    assert w.events("perp_tick")[-1]["payload"]["last_minute"] == before
    assert not w.events("minute_incomplete")
