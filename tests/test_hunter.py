"""The "Wick Hunter" (docs/SPEC-HUNTER.md §8): the frozen rule, its execution on the league's journal, the
witness at the pace of 5 minutes, the watcher's part and the safeguards. A fake Kraken client, synthetic prices, no
network."""

from __future__ import annotations

import dataclasses
import importlib.util
import math
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from arena.perp import benchmarks as B
from arena.perp import hunter as H
from arena.perp import trend_council as TC
from arena.perp.ledger import replay
from arena.perp.margin import leveraged
from arena.perp.types import Candle, FxQuote, PerpTicker
from arena.perp.watcher import PerpWatcher
from tests.test_perp_watcher import CFG, FX, POLICY, PRICES, SPECS, SYMBOLS, T0, World

# the file says `enabled = false` since axis 10 (the hunter is retired): the machinery is still tested enabled
CONFIG = dataclasses.replace(H.load_hunter_config(), enabled=True)
ME, WITNESS = CONFIG.portfolio, CONFIG.benchmark
BTC = "PF_XBTUSD"
START = T0 + 1200  # a multiple of 300; the witness decides at START + 210 + 300 k
FROZEN = Path(__file__).resolve().parent.parent / "docs" / "research-v5" / "finalists" / "shocks_fade-wickS.py"

PriceFn = Callable[[str, int], int]


def flat(sym: str, t: int) -> int:
    return PRICES[sym]


class FakeClient:
    """Kraken Futures, without the network: tickers and candles follow `price(sym, t)` at the clock `now`."""

    def __init__(self, price: PriceFn = flat) -> None:
        self.price = price
        self.now = START
        self.fail = False
        self.calls = 0
        self.fx_calls = 0
        self.candle_calls = 0
        self.on_fresh: Callable[[], None] | None = None

    def tickers(self, symbols):
        self.calls += 1
        if len(symbols) == 1 and self.on_fresh is not None:  # the fresh read just before an entry
            self.on_fresh()
        if self.fail:
            raise OSError("network down")
        out = {}
        for s in symbols:
            p = self.price(s, self.now)
            out[s] = PerpTicker(
                s, self.now, p, p + SPECS[s].tick_uusd, p, p, p, 1, 1, 10_000_000, 10_000_000, 0, False, False
            )
        return out, {}

    def candles(self, kind, sym, interval_s, from_ts, to_ts):
        self.candle_calls += 1
        assert kind == "trade" and interval_s == 60
        ts = -(-from_ts // 60) * 60
        out = []
        while ts + 60 <= min(to_ts, self.now):
            p = self.price(sym, ts + 60)
            out.append(Candle(sym, "trade", 60, ts, p, p, p, p, 0))
            ts += 60
        return out

    def eurusd(self):
        self.fx_calls += 1
        return FxQuote(self.now, FX.bid_uusd_per_eur, FX.ask_uusd_per_eur)


def make(tmp_path: Path, price: PriceFn = flat, cfg: H.HunterConfig = CONFIG) -> tuple[World, FakeClient, H.Hunter]:
    w = World(tmp_path, trend_days=0)
    client = FakeClient(price)
    h = H.Hunter(w.var, cfg, SPECS, client, spot_paths=w.spot, clock=lambda: float(client.now))
    h.start(START)
    return w, client, h


def drive(h: H.Hunter, client: FakeClient, start: int, end: int, every: int = 30) -> None:
    for t in range(start, end + 1, every):
        client.now = t
        h.step(t)


def fills(w: World, name: str, sym: str = BTC) -> list[dict]:
    return [e for e in w.events("perp_fill") if e["payload"]["portfolio"] == name and e["payload"]["instrument"] == sym]


def drop(at: int, factor: float, sym: str = BTC, base: PriceFn = flat) -> PriceFn:
    """`sym` is multiplied by `factor` from the time `at` on."""
    return lambda s, t: round(base(s, t) * factor) if s == sym and t >= at else base(s, t)


def history(prices: dict[int, int], keep_s: int = 3600) -> H.PriceHistory:
    hist = H.PriceHistory(keep_s)
    for ts, px in sorted(prices.items()):
        hist.add(BTC, ts, px)
    return hist


# ---------------------------------------------------------------------- detection


def test_a_fall_of_5_percent_in_10_minutes_is_a_buy_and_a_rise_a_sell():
    base = 70_000_000_000
    h = history({0: base, 300: base, 600: base})
    s = H.detect_shock(h, BTC, 600 + 600, round(base * 0.95), CONFIG)
    assert s is not None and s.window_min in CONFIG.windows_min
    assert s.side == 1 and s.move_bp == round(math.log(0.95) * 10_000)
    s = H.detect_shock(h, BTC, 1200, round(base * 1.05), CONFIG)
    assert s is not None and s.side == -1 and s.move_bp > 450


def test_a_move_of_4_percent_gives_nothing():
    base = 70_000_000_000
    h = history({0: base, 300: base, 600: base})
    assert H.detect_shock(h, BTC, 1200, round(base * 0.96), CONFIG) is None
    assert H.detect_shock(h, BTC, 1200, round(base * 1.04), CONFIG) is None


def test_a_window_without_a_reference_price_does_not_count():
    base = 70_000_000_000
    # nothing at all: no window counts
    assert H.detect_shock(H.PriceHistory(3600), BTC, 2000, round(base * 0.9), CONFIG) is None
    # only a reading from 20 minutes before: the 5 and 15 minute windows have no reference (older than 90 s than
    # their time), the 30 minute one has (the last reading at or before `now - 30 min` is missing too)
    h = history({1000: base})
    assert H.detect_shock(h, BTC, 2200, round(base * 0.9), CONFIG) is None
    # a reference 100 s away from `t - w`: too far; 80 s away: counts
    h = history({1000: base, 1100: round(base * 0.9)})
    far = H.detect_shock(h, BTC, 1000 + 300 + 100 + 1, round(base * 0.9), CONFIG)
    assert far is None or far.window_min != 5
    h = history({1000: base})
    near = H.detect_shock(h, BTC, 1000 + 300 + 80, round(base * 0.95), CONFIG)
    assert near is not None and near.window_min == 5


def test_the_price_of_the_rule_is_the_last_trade_else_the_middle():
    t = PerpTicker(BTC, 1, 100_000, 100_100, 100_050, 100_050, 100_080, 1, 1, 1, 1, 0, False, False)
    assert H.Hunter.price_of(t) == 100_080
    assert H.Hunter.price_of(dataclasses.replace(t, last_uusd=None)) == 100_050


def test_a_last_trade_farther_than_100_bp_from_the_middle_is_not_the_price():
    t = PerpTicker(BTC, 1, 100_000, 100_100, 100_050, 100_050, 100_050, 1, 1, 1, 1, 0, False, False)
    mid = 100_050
    assert H.Hunter.price_of(dataclasses.replace(t, last_uusd=mid + 1000)) == mid + 1000  # exactly 100 bp: kept
    assert H.Hunter.price_of(dataclasses.replace(t, last_uusd=mid + 1001)) == mid  # a stale trade after a wick
    assert H.Hunter.price_of(dataclasses.replace(t, last_uusd=mid - 1001)) == mid


# ---------------------------------------------------------------------- execution


def test_entry_at_2x_with_a_stop_exit_after_60_minutes_lock_and_one_position_at_a_time(tmp_path):
    def price(s, t):
        p = PRICES[s]
        if s != BTC:
            return p
        if t < START + 120:
            return p
        if t < START + 3700:
            return round(p * 0.95)  # the wick: -5 % in 2 minutes, then it stays down
        if t < START + 7260:
            return round(p * 0.95 * 0.95)  # a second fall inside the hold and the lock: ignored
        return round(p * 0.95 * 0.95 * 0.95)  # after the lock: a third

    w, client, h = make(tmp_path, price)
    drive(h, client, START, START + 8000)
    mine = fills(w, ME)
    assert [f["payload"]["reason"] for f in mine] == ["intent", "intent", "intent"], mine
    entry, close, entry2 = (f["payload"] for f in mine)
    assert entry["qty"] > 0 and close["qty"] == -entry["qty"] and entry2["qty"] > 0
    assert mine[0]["ts"] == START + 120  # the very reading that showed the shock
    assert mine[1]["ts"] == START + 120 + 3600  # out at 60 minutes, not before
    assert mine[2]["ts"] >= START + 120 + 7200  # the lock: 60 minutes after the planned exit
    # nothing in between: the shocks of the hold and of the lock were ignored
    signals = [e for e in w.events("hunter_signal") if e["payload"]["portfolio"] == ME]
    assert [e["payload"]["ts"] for e in signals] == [START + 120, mine[2]["ts"]]
    assert all(e["payload"]["side"] == "buy" for e in signals)
    assert [e["payload"]["opened_ts"] for e in w.events("hunter_exit") if e["payload"]["portfolio"] == ME] == [START + 120]
    # the first entry: about 2x the equity, a stop 5 % away
    states = replay([e for e in w.events() if e["ts"] <= START + 130])
    pos = states[ME].positions[BTC]
    mark = round(PRICES[BTC] * 0.95)
    equity = states[ME].collateral_ueur
    exposure = TC.current_exposure_bp(states[ME], {BTC: mark}, FX.bid_uusd_per_eur, equity)[BTC]
    assert 19_000 <= exposure <= 20_100, exposure
    assert pos.stop_uusd is not None and abs(pos.stop_uusd / entry["price_uusd"] - 0.95) < 0.002
    assert w.events("hunter_config") and w.events("hunter_config")[0]["payload"]["config_sha256"] == CONFIG.sha256


def test_the_stop_does_not_lift_the_lock(tmp_path):
    w, client, h = make(tmp_path, drop(START + 120, 0.95))
    drive(h, client, START, START + 300)
    assert len(fills(w, ME)) == 1
    # the position is gone (as if a stop had filled it), the lock runs from the entry: no new entry for 120 minutes
    me = h.players[0]
    px = round(PRICES[BTC] * 0.95)
    quote, fx = (px, px + SPECS[BTC].tick_uusd), (FX.bid_uusd_per_eur, FX.ask_uusd_per_eur)
    h.sim.market_order("stop-out", ME, BTC, -fills(w, ME)[0]["payload"]["qty"], quote, fx, START + 400, "stop")
    drive(h, client, START + 360, START + 7000)
    assert len(fills(w, ME)) == 2 and fills(w, ME)[1]["payload"]["reason"] == "stop"
    assert me.last_entry[BTC] == START + 120


def test_the_same_decision_replayed_does_not_make_a_second_order(tmp_path):
    w, client, h = make(tmp_path, drop(START + 120, 0.95))
    client.now = START + 120
    tickers, _ = client.tickers(SYMBOLS)
    me = h.players[0]
    h.hist.add(BTC, START, PRICES[BTC])
    shock = H.detect_shock(h.hist, BTC, START + 120, tickers[BTC].last_uusd, CONFIG)
    assert shock is not None
    assert h.enter(me, shock, START + 120, tickers) is True
    n = len(w.events())
    assert h.enter(me, shock, START + 121, tickers) is False  # the same shock: nothing at all
    assert len(w.events()) == n
    # the order id is deterministic, so even without the memory of the process the ledger refuses a second fill
    # (a restart reads the signals back from the journal)
    h2 = H.Hunter(w.var, CONFIG, SPECS, client, spot_paths=w.spot, clock=lambda: float(client.now))
    h2.start(START + 130)
    me2 = h2.players[0]
    assert (BTC, START + 120) in me2.done and me2.last_entry[BTC] == START + 120
    assert h2.enter(me2, shock, START + 131, tickers) is False
    assert len(fills(w, ME)) == 1
    intent_ids = {e["payload"]["intent_id"] for e in w.events("hunter_signal")}
    assert len(intent_ids) == 1
    # a restart does not forget the lock either: a new shock 10 minutes later is ignored
    client.price = drop(START + 120, 0.95 * 0.95)
    drive(h2, client, START + 180, START + 900)
    assert len(fills(w, ME)) == 1


def test_the_order_id_is_a_function_of_the_portfolio_the_contract_and_the_time_of_the_shock(tmp_path):
    _w, _client, h = make(tmp_path)
    shock = H.Shock(BTC, 1, 5, -500, 66_000_000_000, START)
    ids = []
    for _ in range(2):
        decision = {
            "actions": [{"instrument": BTC, "action": "open_long", "size_pct": 200, "stop_pct": 5, "horizon_h": 1, "expected_move_pct": 1.13}],
            "justification": "x",
        }
        from arena.perp.agent import parse_decision

        ids.append(parse_decision(decision, ME, shock.ts, START + 3, max_size_pct=200, max_actions=1)[2][0].intent_id)
    other = parse_decision(decision, WITNESS, shock.ts, START + 3, max_size_pct=200, max_actions=1)[2][0].intent_id
    assert ids[0] == ids[1] and ids[0] != other
    assert h.cfg.max_size_pct == 200


# ---------------------------------------------------------------------- the witness


def test_the_benchmark_decides_once_per_slice_on_the_prices_known_then(tmp_path):
    # the wick starts at START + 330 (inside the slice that began at START + 210)
    w, client, h = make(tmp_path, drop(START + 330, 0.95))
    drive(h, client, START, START + 4400, every=30)
    me, wit = fills(w, ME), fills(w, WITNESS)
    assert me and wit
    assert me[0]["ts"] == START + 330  # the hunter: on the reading that shows the shock
    assert wit[0]["ts"] == START + 510  # the witness: the next decision, START + 210 + 300
    assert (wit[0]["ts"] - START - 210) % 300 == 0
    assert me[1]["ts"] == START + 330 + 3600  # the hunter leaves at 60 minutes ...
    assert wit[1]["ts"] == START + 510 + 3600  # ... the witness on the grid, also 60 minutes after its entry
    # its decisions are on the grid only
    for e in w.events("hunter_signal"):
        if e["payload"]["portfolio"] == WITNESS:
            assert (e["ts"] - START - 210) % 300 == 0


def test_a_spike_that_is_over_before_the_next_slice_is_missed_by_the_witness_not_by_the_hunter(tmp_path):
    def price(s, t):
        if s == BTC and START + 330 <= t < START + 390:
            return round(PRICES[s] * 1.06)  # a spike of one minute
        return PRICES[s]

    w, client, h = make(tmp_path, price)
    drive(h, client, START, START + 1200, every=30)
    assert len(fills(w, ME)) >= 1 and fills(w, ME)[0]["payload"]["qty"] < 0  # sold the rise
    assert fills(w, WITNESS) == []
    assert not [e for e in w.events("hunter_signal") if e["payload"]["portfolio"] == WITNESS]


def test_the_witness_is_a_distinct_portfolio_with_the_same_path(tmp_path):
    w, client, h = make(tmp_path, drop(START + 330, 0.95))
    drive(h, client, START, START + 1500, every=30)
    states = replay(w.events())
    assert ME in states and WITNESS in states and states[ME].collateral_ueur != 0
    opened = {e["payload"]["portfolio"]: e["payload"]["kind"] for e in w.events("portfolio_opened")}
    assert opened[ME] == opened[WITNESS] == "robot"
    assert states[WITNESS].positions[BTC].stop_uusd is not None  # the same execution path: a stop on the entry too
    for e in w.events("perp_verdict"):
        assert e["payload"]["portfolio"] in (ME, WITNESS)


# ---------------------------------------------------------------------- the watcher


def watcher_world(tmp_path: Path) -> World:
    w = World(tmp_path, trend_days=0)
    w.w = PerpWatcher(w.var, CFG, POLICY, SPECS, spot_paths=w.spot, hunter=CONFIG)
    return w


def test_the_watcher_opens_the_portfolios_with_the_hunters_policy_and_leverage_rules(tmp_path):
    w = watcher_world(tmp_path)
    assert w.w.policy_for(ME) is CONFIG.policy and w.w.policy_for(WITNESS) is CONFIG.policy
    assert w.w.policy_for(B.RANDOM) is POLICY and w.w.policy_for(B.RANDOM).drawdown_halt_bp != 6000
    assert CONFIG.policy.drawdown_halt_bp == 6000 and CONFIG.policy.daily_loss_freeze_bp == 0
    assert leveraged(ME) and leveraged(WITNESS)  # Kraken's margins, not the AMF 50 % rule
    w.w.tick(T0 + 120)
    assert {e["payload"]["portfolio"]: e["payload"]["kind"] for e in w.events("portfolio_opened")}[ME] == "robot"
    assert WITNESS in replay(w.events())
    assert w.w.sim.open_portfolio(ME, "robot", T0 + 200) is False  # idempotent: the hunter's process opens them too


def test_the_watcher_does_not_close_a_hunter_position_at_the_maximum_holding(tmp_path):
    w = watcher_world(tmp_path)
    w.w.sim.params = dataclasses.replace(w.w.sim.params, max_holding_s=600)
    w.w.tick(T0 + 120)
    quote = (PRICES[BTC], PRICES[BTC] + SPECS[BTC].tick_uusd)
    fx = (FX.bid_uusd_per_eur, FX.ask_uusd_per_eur)
    for name in (B.RANDOM, ME, WITNESS):
        w.w.sim.market_order(f"manual:{name}", name, BTC, 100_000, quote, fx, T0 + 130, marks=PRICES)
        w.w.sim.set_conditional(name, BTC, "stop", PRICES[BTC] * 9 // 10, T0 + 131)
    w.advance(T0 + 1320)
    w.w.tick(T0 + 1320)
    states = replay(w.events())
    assert states[B.RANDOM].positions == {}  # the control: cut after 600 s
    assert BTC in states[ME].positions and BTC in states[WITNESS].positions
    assert not [e for e in w.events("perp_fill") if e["payload"]["reason"] == "max_holding" and e["payload"]["portfolio"] in (ME, WITNESS)]


def test_the_watcher_halts_the_hunter_at_minus_60_percent_not_minus_15(tmp_path):
    w = watcher_world(tmp_path)
    w.w.tick(T0 + 120)
    quote = (PRICES[BTC], PRICES[BTC] + SPECS[BTC].tick_uusd)
    fx = (FX.bid_uusd_per_eur, FX.ask_uusd_per_eur)
    # 2x long on the hunter, the same on the random benchmark; the market falls 20 %: -40 % of the equity
    qty = 28_000  # 1e-8 lots: about 2x of 1 000 EUR at 70 000 USD
    for name in (B.RANDOM, ME):
        w.w.sim.market_order(f"big:{name}", name, BTC, 2_500_000 if name == B.RANDOM else qty * 40, quote, fx, T0 + 130, marks=PRICES)
        w.w.sim.set_conditional(name, BTC, "stop", PRICES[BTC] // 2, T0 + 131)
    down = dict(PRICES, **{BTC: PRICES[BTC] * 80 // 100})
    w.advance(T0 + 420, down)
    w.w.tick(T0 + 420)
    states = replay(w.events())
    assert states[B.RANDOM].halted  # the league's rule: -15 %
    assert not states[ME].halted  # the hunter's: -60 %


# ---------------------------------------------------------------------- the safeguards


def test_the_kill_switch_blocks_the_entries(tmp_path):
    w, client, h = make(tmp_path, drop(START + 120, 0.95))
    (w.var / "KILL").touch()
    drive(h, client, START, START + 600)
    assert fills(w, ME) == [] and fills(w, WITNESS) == []
    verdicts = [e["payload"] for e in w.events("perp_verdict") if e["payload"]["portfolio"] == ME]
    assert verdicts and not any(v["approved"] for v in verdicts)


def test_dormancy_blocks_the_entries(tmp_path):
    w, client, h = make(tmp_path, drop(START + 120, 0.95))
    h._opened_ts = START - 8 * 86_400  # no ack for 8 days
    drive(h, client, START, START + 300)
    assert fills(w, ME) == []


def test_a_network_error_does_not_break_the_loop(tmp_path):
    w, client, h = make(tmp_path, drop(START + 240, 0.95))
    drive(h, client, START, START + 120)
    client.fail = True
    drive(h, client, START + 150, START + 180)  # does not raise
    assert h.stats.errors == 2 and h.stats.reads_ok == 5
    client.fail = False
    drive(h, client, START + 210, START + 300)
    assert len(fills(w, ME)) == 1  # the hunt goes on


def test_a_failing_candles_call_does_not_stop_the_start(tmp_path):
    w = World(tmp_path, trend_days=0)

    class NoCandles(FakeClient):
        def candles(self, *a, **k):
            raise OSError("down")

    client = NoCandles()
    h = H.Hunter(w.var, CONFIG, SPECS, client, spot_paths=w.spot)
    h.start(START)
    assert h.stats.errors == len(SYMBOLS) and len(h.hist) == 0
    drive(h, client, START, START + 60)
    assert len(h.hist) > 0


def test_the_start_primes_the_history_from_the_minute_candles(tmp_path):
    w, client, h = make(tmp_path, drop(START + 120, 0.95))
    assert client.candle_calls == len(SYMBOLS)
    assert len(h.hist) >= len(SYMBOLS) * 30
    # after a restart in the middle of a shock, the hunter sees it at once (no 30 minutes of blindness) ... but does
    # not enter on the first reading after the start, nor on the rest of that episode: the shock may be old
    client.now = START + 120
    h.step(START + 120)
    assert fills(w, ME) == [] and h.stats.shocks == 1
    drive(h, client, START + 150, START + 300)
    assert fills(w, ME) == [] and h.players[0].episodes[BTC] == (START + 120, False)


def test_a_heartbeat_once_an_hour_and_no_event_per_reading(tmp_path):
    w, client, h = make(tmp_path)
    drive(h, client, START + 5, START + 2 * 3600 + 100, every=5)
    beats = w.events("hunter_heartbeat")
    assert len(beats) == 2
    assert beats[0]["payload"]["reads_ok"] >= 700 and beats[0]["payload"]["errors"] == 0
    assert len(w.events()) < 20  # opened, config, heartbeats, equity-free: no line per reading


def test_the_witness_waits_for_the_next_slice_when_started_mid_slice(tmp_path):
    w = World(tmp_path, trend_days=0)
    client = FakeClient(drop(START + 100, 0.95))
    client.now = START + 250  # in the slice of START + 210
    h = H.Hunter(w.var, CONFIG, SPECS, client, spot_paths=w.spot, clock=lambda: float(client.now))
    h.start(START + 250)
    h.step(START + 260)
    assert fills(w, WITNESS) == []


def test_the_config_is_hashed_checked_and_consistent_with_the_frozen_rule():
    assert len(CONFIG.sha256) == 64 and CONFIG.policy.profile == "aggressive"
    mod = _frozen()
    assert CONFIG.threshold == mod.THR and CONFIG.hold_min == mod.HOLD and CONFIG.lock_min == mod.LOCK
    assert Decimal_eq(CONFIG.size_pct, mod.WEIGHT * 100) and Decimal_eq(CONFIG.stop_pct, mod.STOP_PCT * 100)
    assert CONFIG.windows_min == (5, 15, 30) and CONFIG.expected_move_bp == 113 and len(CONFIG.expected_move_source) > 20
    assert (CONFIG.policy.max_order_bp, CONFIG.policy.max_position_bp, CONFIG.policy.max_leverage_bp) == (20_000, 30_000, 100_000)
    assert CONFIG.policy.max_open_risk_bp == 5900 and CONFIG.policy.drawdown_halt_bp == 6000 and CONFIG.policy.max_opens_per_day == 48
    assert CONFIG.policy.min_interval_same_open_s == 0 and CONFIG.policy.daily_loss_freeze_bp == 0


def Decimal_eq(text: str, number: float) -> bool:
    from decimal import Decimal

    return Decimal(text) == Decimal(str(number))


def test_a_bad_config_is_refused(tmp_path):
    text = (Path("config") / "perp-hunter.toml").read_text()
    bad = tmp_path / "perp-hunter.toml"
    (tmp_path / "policy-perp-hunter.toml").write_text((Path("config") / "policy-perp-hunter.toml").read_text())
    bad.write_text(text.replace('portfolio = "robot-perp:hunter"', 'portfolio = "hunter"'))
    with pytest.raises(H.HunterConfigError):
        H.load_hunter_config(bad)
    bad.write_text(text.replace("shock_bp = 450", "shock_bp = 450\nextra = 1"))
    with pytest.raises(H.HunterConfigError):
        H.load_hunter_config(bad)
    bad.write_text(text)
    assert H.load_hunter_config(bad).sha256 == CONFIG.sha256  # the same bytes, the same hash


# ---------------------------------------------------------------------- the rule against the frozen script


def _frozen():
    spec = importlib.util.spec_from_file_location("shocks_fade_wick_s", FROZEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_decisions_at_a_minute_cadence_reproduce_the_frozen_rule():
    mod = _frozen()
    rng = np.random.default_rng(7)
    n, k = 6000, len(CONFIG.instruments)
    steps = rng.normal(0, 0.0008, (n, k))
    for j in range(k):  # wicks: a fall or a rise of 5 to 9 % over 1 to 4 minutes, and a partial return
        for i in rng.choice(np.arange(40, n - 200), 14, replace=False):
            width = int(rng.integers(1, 5))
            sign = -1 if rng.random() < 0.6 else 1
            steps[i : i + width, j] += sign * rng.uniform(0.05, 0.09) / width
            steps[i + width + 1 : i + width + 11, j] -= sign * 0.003
    # a 4 % move that must never trigger
    steps[3000, 0] = -0.04
    close = np.round(np.exp(np.cumsum(steps, axis=0)) * 1_000_000_000)
    frozen = mod.targets(SimpleNamespace(close=close.astype(float)))
    frozen_events = []
    cur = np.zeros(k)
    for i in range(n):
        if np.isnan(frozen[i, 0]):
            continue
        for j in range(k):
            if frozen[i, j] != cur[j]:
                frozen_events.append((i, j, "exit" if frozen[i, j] == 0 else ("enter", int(np.sign(frozen[i, j]))) ))
        cur = frozen[i].copy()
    assert sum(1 for e in frozen_events if e[2] != "exit") >= 10  # the series does hunt

    insts = CONFIG.instruments
    hist = H.PriceHistory(CONFIG.history_min * 60)
    held: dict[str, int] = {}
    last: dict[str, int] = {}
    mine = []
    t0 = 1_800_000_000
    for i in range(n):
        now = t0 + i * 60
        prices = {inst: int(close[i, j]) for j, inst in enumerate(insts)}
        for d in H.decide(CONFIG, hist, now, prices, held, last):
            j = insts.index(d.instrument)
            if d.kind == "exit":
                held.pop(d.instrument)
                mine.append((i, j, "exit"))
            else:
                assert d.shock is not None
                held[d.instrument] = last[d.instrument] = now
                mine.append((i, j, ("enter", d.shock.side)))
        for inst, p in prices.items():
            hist.add(inst, now, p)
    assert sorted(mine) == sorted(frozen_events)


# ---------------------------------------------------------------------- latency, late entries, the rest of the fixes


def make_clocked(tmp_path: Path, price: PriceFn, cfg: H.HunterConfig = CONFIG):
    """A hunter whose clock is `clock["t"]`, set by the test (not by the client's `now`)."""
    w = World(tmp_path, trend_days=0)
    client = FakeClient(price)
    clock = {"t": float(START)}
    h = H.Hunter(w.var, cfg, SPECS, client, spot_paths=w.spot, clock=lambda: clock["t"])
    h.start(START)
    return w, client, h, clock


def step_to(h: H.Hunter, client: FakeClient, clock: dict, t: int) -> None:
    client.now = t
    clock["t"] = float(t)
    h.step()


def test_the_entry_meets_a_fresh_ticker_and_the_real_time_and_the_latency_is_journaled(tmp_path):
    w, client, h, clock = make_clocked(tmp_path, drop(START + 120, 0.95))

    def fresh() -> None:  # 2.5 s later, the contract has fallen further
        clock["t"] += 2.5
        client.price = drop(START + 120, 0.93)

    client.on_fresh = fresh
    for t in range(START, START + 121, 30):
        step_to(h, client, clock, t)
    entry = fills(w, ME)[0]
    assert entry["ts"] == START + 122  # the real time of the order, not that of the reading
    assert entry["payload"]["price_uusd"] > round(PRICES[BTC] * 0.93)
    assert entry["payload"]["price_uusd"] < round(PRICES[BTC] * 0.9501)  # the fresh price (-7 %), not the reading's
    sig = next(e["payload"] for e in w.events("hunter_signal") if e["payload"]["portfolio"] == ME)
    assert sig["read_ts"] == START + 120 and sig["first_seen_ts"] == START + 120 and sig["ts"] == START + 120
    done = [e["payload"] for e in w.events("hunter_entry") if e["payload"]["portfolio"] == ME]
    assert len(done) == 1 and done[0]["status"] == "filled" and done[0]["latency_ms"] == 2500
    assert done[0]["read_ts"] == START + 120 and done[0]["intent_id"] == sig["intent_id"]
    assert entry["payload"]["order_id"].split(":")[0] == sig["intent_id"]


def test_a_refused_entry_is_journaled_with_its_status(tmp_path):
    w, client, h = make(tmp_path, drop(START + 120, 0.95))
    (w.var / "KILL").touch()
    drive(h, client, START, START + 150)
    done = [e["payload"] for e in w.events("hunter_entry") if e["payload"]["portfolio"] == ME]
    assert done and done[0]["status"] == "refused" and done[0]["latency_ms"] == 0


def test_without_a_fresh_ticker_there_is_no_order(tmp_path):
    w, client, h = make(tmp_path, drop(START + 120, 0.95))

    def boom() -> None:
        raise OSError("down")

    client.on_fresh = boom
    drive(h, client, START, START + 150)
    assert fills(w, ME) == [] and not w.events("hunter_signal") and h.stats.errors >= 1


def test_a_refused_entry_is_retried_smaller_twice_at_most(tmp_path):
    tight = dataclasses.replace(CONFIG.policy, max_trade_loss_bp=600)  # 200 % with a 5 % stop is too much
    cfg = dataclasses.replace(CONFIG, policy=tight)
    w, client, h = make(tmp_path, drop(START + 120, 0.95), cfg)
    drive(h, client, START, START + 120)
    mine = [e["payload"] for e in w.events("perp_verdict") if e["payload"]["portfolio"] == ME]
    assert [v["approved"] for v in mine] == [False, False, False]  # the order and two smaller tries: no more
    assert fills(w, ME) == []


def test_run_intents_keeps_eight_tries_for_the_other_callers():
    import inspect

    from arena.perp.agent_round import SHRINK_TRIES, run_intents

    assert inspect.signature(run_intents).parameters["max_shrink_tries"].default == SHRINK_TRIES == 8
    assert H.SHRINK_TRIES_HUNTER == 2


def test_no_entry_when_the_previous_reading_is_older_than_30_seconds(tmp_path):
    w, client, h = make(tmp_path, drop(START + 120, 0.95))
    drive(h, client, START, START + 60)
    client.now = START + 130  # the reading before is 70 s old: the shock may be old
    h.step(START + 130)
    drive(h, client, START + 160, START + 400)
    assert fills(w, ME) == [] and not [e for e in w.events("hunter_signal") if e["payload"]["portfolio"] == ME]


def test_a_refused_entry_is_retried_within_120_seconds_and_is_not_a_new_shock(tmp_path):
    w, client, h = make(tmp_path, drop(START + 120, 0.95))
    (w.var / "KILL").touch()
    drive(h, client, START, START + 150)
    (w.var / "KILL").unlink()  # the refusal was a wick's: it is over at START + 180
    drive(h, client, START + 180, START + 400)
    assert len(fills(w, ME)) == 1 and fills(w, ME)[0]["ts"] == START + 180
    sigs = [e["payload"] for e in w.events("hunter_signal") if e["payload"]["portfolio"] == ME]
    assert len(sigs) == 2 and {s["first_seen_ts"] for s in sigs} == {START + 120}
    assert sigs[0]["intent_id"] != sigs[1]["intent_id"]
    assert h.stats.shocks == 2  # one shock per portfolio (the witness sees the same wick once), not one per attempt


def test_no_retry_after_120_seconds(tmp_path):
    w, client, h = make(tmp_path, drop(START + 120, 0.95))
    (w.var / "KILL").touch()
    drive(h, client, START, START + 300)
    (w.var / "KILL").unlink()
    drive(h, client, START + 330, START + 900)  # the shock still holds, but it is 210 s old and more: too late
    assert fills(w, ME) == []
    sigs = [e["payload"] for e in w.events("hunter_signal") if e["payload"]["portfolio"] == ME]
    assert max(s["ts"] for s in sigs) <= START + 120 + 120 and h.stats.shocks == 2


def test_the_stop_ids_and_signals_of_a_restart_keep_the_episode(tmp_path):
    w, client, h = make(tmp_path, drop(START + 120, 0.95))
    (w.var / "KILL").touch()
    drive(h, client, START, START + 150)
    h2 = H.Hunter(w.var, CONFIG, SPECS, client, spot_paths=w.spot, clock=lambda: float(client.now))
    h2.start(START + 160)
    assert h2.players[0].episodes[BTC] == (START + 120, True)


def test_a_lock_is_set_as_soon_as_the_entry_fill_exists_even_if_the_position_is_already_closed(tmp_path):
    w, client, h = make(tmp_path, drop(START + 120, 0.95))
    me = h.players[0]
    real = h.sim.__class__.market_order

    def open_then_close(self, oid, name, inst, qty, *a, **k):  # the entry fills, and the position is closed at once
        out = real(self, oid, name, inst, qty, *a, **k)
        if name == ME and not oid.startswith("closing"):
            real(self, "closing:" + oid, name, inst, -qty, *a, **k)
        return out

    h.sim.__class__.market_order = open_then_close
    try:
        drive(h, client, START, START + 150)
    finally:
        h.sim.__class__.market_order = real
    assert BTC not in replay(w.events())[ME].positions  # flat again
    assert me.last_entry[BTC] == START + 120  # but the lock runs from the entry
    # a restart reads the same
    h2 = H.Hunter(w.var, CONFIG, SPECS, client, spot_paths=w.spot, clock=lambda: float(client.now))
    h2.start(START + 160)
    assert h2.players[0].last_entry[BTC] == START + 120


def test_the_witness_reasons_in_slices_12_to_exit_24_to_unlock():
    slot = lambda t: (t - CONFIG.witness_offset_s) // CONFIG.witness_period_s
    base = START + 210 + 300 * 3 + 7  # an entry inside slice 3 after the offset (read late in its slice)
    k = slot(base)
    held = {BTC: base}
    prices = {BTC: PRICES[BTC]}
    hist = H.PriceHistory(7200)

    def exits(t):
        return [d.kind for d in H.decide(CONFIG, hist, t, prices, held, {BTC: base}, slot=slot)]

    first_of_slice = lambda n: CONFIG.witness_offset_s + n * CONFIG.witness_period_s
    assert exits(first_of_slice(k + 12) - 1) == []  # the last second of the 11th slice after: no
    assert exits(first_of_slice(k + 12)) == ["exit"]  # the first of the 12th slice after: yes, to the second
    # the lock: 24 slices after the entry's, to the second
    shock_hist = history({first_of_slice(k + 24) - 600: PRICES[BTC], first_of_slice(k + 24) - 300: PRICES[BTC]}, 7200)
    cheap = {BTC: round(PRICES[BTC] * 0.9)}
    free = lambda t: H.decide(CONFIG, shock_hist, t, cheap, {}, {BTC: base}, slot=slot)
    assert free(first_of_slice(k + 24) - 1) == []
    assert [d.kind for d in free(first_of_slice(k + 24))] == ["enter"]


def test_an_exception_in_play_does_not_consume_the_slice(tmp_path, monkeypatch):
    w, client, h = make(tmp_path, drop(START + 100, 0.95))
    wit = h.players[1]
    real = h.enter
    boom = {"on": True}

    def flaky(p, shock, now_ts, tickers, **kw):
        if p.witness and boom["on"]:
            raise RuntimeError("boom")
        return real(p, shock, now_ts, tickers, **kw)

    monkeypatch.setattr(h, "enter", flaky)
    drive(h, client, START, START + 240, every=30)  # the slice that starts at START + 210: the exception
    assert fills(w, WITNESS) == [] and h.stats.errors >= 1
    assert wit.last_slot == h._slot(START)  # the slice was not consumed
    boom["on"] = False
    drive(h, client, START + 270, START + 300, every=30)  # the next readings of the same slice: tried again
    assert fills(w, WITNESS)[0]["ts"] == START + 270 and wit.last_slot == h._slot(START + 270)


def test_the_blind_alert_is_also_sent_by_the_notifier(tmp_path):
    w = World(tmp_path, trend_days=0)
    client = FakeClient()
    client.fail = True
    sent = []
    notifier = SimpleNamespace(send=lambda level, code, message: sent.append((level, code, message)) or True)
    h = H.Hunter(w.var, CONFIG, SPECS, client, spot_paths=w.spot, clock=lambda: float(client.now), notifier=notifier)
    h.start(START)
    for t in range(START + 30, START + 700, 30):
        client.now = t
        h.step(t)
    assert [c for _l, c, _m in sent] == ["perp_hunter_blind"] and sent[0][0] == "action"
    assert [e for e in w.events("alert") if e["payload"]["code"] == "perp_hunter_blind"]


def test_the_start_retries_a_failing_journal_read(tmp_path):
    w = World(tmp_path, trend_days=0)
    client = FakeClient()
    waits = []
    h = H.Hunter(w.var, CONFIG, SPECS, client, spot_paths=w.spot, clock=lambda: float(client.now), sleep=waits.append)
    real = h.sim.journal.events
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] <= 3:
            raise OSError("busy")
        return real()

    h.sim.journal.events = flaky
    h.start(START)  # does not raise
    assert len(waits) >= 3
    h2 = H.Hunter(w.var, CONFIG, SPECS, client, spot_paths=w.spot, sleep=lambda _s: None)
    h2.sim.journal.events = lambda: (_ for _ in ()).throw(OSError("dead"))
    with pytest.raises(OSError):  # still failing after the tries: the process stops (the unit restarts it)
        h2._restore(START)


def test_the_watcher_closes_a_hunter_position_held_for_more_than_3_hours(tmp_path):
    w = watcher_world(tmp_path)
    w.w.tick(T0 + 120)
    quote = (PRICES[BTC], PRICES[BTC] + SPECS[BTC].tick_uusd)
    fx = (FX.bid_uusd_per_eur, FX.ask_uusd_per_eur)
    for name in (ME, WITNESS):
        w.w.sim.market_order(f"manual:{name}", name, BTC, 100_000, quote, fx, T0 + 130, marks=PRICES)
        w.w.sim.set_conditional(name, BTC, "stop", PRICES[BTC] * 9 // 10, T0 + 131)
    assert H.HUNTER_SAFETY_HOLD_S == 3 * 3600
    w.advance(T0 + 3 * 3600 - 600)
    w.w.tick(T0 + 3 * 3600 - 600)
    assert BTC in replay(w.events())[ME].positions  # not yet 3 hours
    w.advance(T0 + 3 * 3600 + 600)
    w.w.tick(T0 + 3 * 3600 + 600)
    states = replay(w.events())
    assert states[ME].positions == {} and states[WITNESS].positions == {}
    assert {e["payload"]["portfolio"] for e in w.events("perp_fill") if e["payload"]["reason"] == "max_holding"} == {ME, WITNESS}


def _config_file(tmp_path, *, enabled: bool):
    """A copy of the hunter's config (with its policy) with `enabled` set: the shipped one says false since axis 10."""
    cfg = tmp_path / "perp-hunter.toml"
    text = H.DEFAULT_CONFIG.read_text(encoding="utf-8").replace("enabled = false", f"enabled = {str(enabled).lower()}")
    cfg.write_text(text, encoding="utf-8")
    (tmp_path / "policy-perp-hunter.toml").write_text(
        (H.DEFAULT_CONFIG.parent / "policy-perp-hunter.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return cfg


def test_only_one_hunter_process_may_run(tmp_path):
    cfg = _config_file(tmp_path, enabled=True)
    fd = H.acquire_lock(tmp_path / "var-perp")
    assert fd is not None
    try:
        assert H.acquire_lock(tmp_path / "var-perp") is None
        assert (tmp_path / "var-perp" / "hunter.lock").exists()
        rc = H.main(["run", "--var", str(tmp_path / "var-perp"), "--config", str(cfg)])  # the lock is taken: message and exit 2
        assert rc == 2
    finally:
        import os

        os.close(fd)
    fd2 = H.acquire_lock(tmp_path / "var-perp")  # released with the process (here: the descriptor)
    assert fd2 is not None
    os.close(fd2)


def test_a_disabled_hunter_exits_0_without_the_lock(tmp_path, capsys):
    cfg = _config_file(tmp_path, enabled=False)
    assert H.main(["run", "--var", str(tmp_path / "var-perp"), "--config", str(cfg)]) == 0
    assert not (tmp_path / "var-perp" / "hunter.lock").exists()


def test_the_unit_restarts_on_failure_but_not_on_exit_2_and_restarts_daily():
    unit = (Path(__file__).resolve().parent.parent / "ops" / "systemd" / "arena-perp-hunter.service").read_text()
    for line in (
        "Restart=on-failure", "RestartPreventExitStatus=2", "StartLimitIntervalSec=600", "StartLimitBurst=10",
        "RuntimeMaxSec=86400", "MemoryMax=1G", "Nice=0", "After=network-online.target",
    ):  # fmt: skip
        assert line in unit.splitlines(), line
    assert unit.index("StartLimitBurst") < unit.index("[Service]")  # in [Unit]
