"""The « Chasseur de mèches » (docs/SPEC-CHASSEUR.md §8): the frozen rule, its execution on the league's journal, the
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

from arene.perp import benchmarks as B
from arene.perp import hunter as H
from arene.perp import trend_council as TC
from arene.perp.ledger import replay
from arene.perp.margin import leveraged
from arene.perp.types import Candle, FxQuote, PerpTicker
from arene.perp.watcher import PerpWatcher
from tests.test_perp_watcher import CFG, FX, POLICY, PRICES, SPECS, SYMBOLS, T0, World

CONFIG = H.load_hunter_config()
ME, WITNESS = CONFIG.portfolio, CONFIG.benchmark
BTC = "PF_XBTUSD"
START = T0 + 1200  # a multiple of 300; the witness decides at START + 210 + 300 k
FROZEN = Path(__file__).resolve().parent.parent / "docs" / "recherche-v5" / "finalistes" / "chocs_fade-mecheS.py"

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

    def tickers(self, symbols):
        self.calls += 1
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
    h = H.Hunter(w.var, cfg, SPECS, client, spot_paths=w.spot)
    h.start(START)
    return w, client, h


def drive(h: H.Hunter, client: FakeClient, start: int, end: int, every: int = 60) -> None:
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
    t = PerpTicker(BTC, 1, 100, 110, 105, 105, 103, 1, 1, 1, 1, 0, False, False)
    assert H.Hunter.price_of(t) == 103
    assert H.Hunter.price_of(dataclasses.replace(t, last_uusd=None)) == 105


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
    h2 = H.Hunter(w.var, CONFIG, SPECS, client, spot_paths=w.spot)
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
        from arene.perp.agent import parse_decision

        ids.append(parse_decision(decision, ME, shock.ts, START + 3, max_size_pct=200, max_actions=1)[2][0].intent_id)
    other = parse_decision(decision, WITNESS, shock.ts, START + 3, max_size_pct=200, max_actions=1)[2][0].intent_id
    assert ids[0] == ids[1] and ids[0] != other
    assert h.cfg.max_size_pct == 200


# ---------------------------------------------------------------------- the witness


def test_the_witness_decides_once_per_slice_on_the_prices_known_then(tmp_path):
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


def test_dormance_blocks_the_entries(tmp_path):
    w, client, h = make(tmp_path, drop(START + 120, 0.95))
    h._opened_ts = START - 8 * 86_400  # no ack for 8 days
    drive(h, client, START, START + 300)
    assert fills(w, ME) == []


def test_a_network_error_does_not_break_the_loop(tmp_path):
    w, client, h = make(tmp_path, drop(START + 240, 0.95))
    drive(h, client, START, START + 120)
    client.fail = True
    drive(h, client, START + 180, START + 210)  # does not raise
    assert h.stats.errors == 1 and h.stats.reads_ok == 3
    client.fail = False
    drive(h, client, START + 240, START + 300)
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
    # after a restart in the middle of a shock, the hunter sees it at once (no 30 minutes of blindness)
    client.now = START + 120
    h.step(START + 120)
    assert len(fills(w, ME)) == 1


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
    h = H.Hunter(w.var, CONFIG, SPECS, client, spot_paths=w.spot)
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


def Decimal_eq(text: str, number: float) -> bool:  # noqa: N802
    from decimal import Decimal

    return Decimal(text) == Decimal(str(number))


def test_a_bad_config_is_refused(tmp_path):
    text = (Path("config") / "perp-chasseur.toml").read_text()
    bad = tmp_path / "perp-chasseur.toml"
    (tmp_path / "policy-perp-chasseur.toml").write_text((Path("config") / "policy-perp-chasseur.toml").read_text())
    bad.write_text(text.replace('portfolio = "robot-perp:chasseur"', 'portfolio = "chasseur"'))
    with pytest.raises(H.HunterConfigError):
        H.load_hunter_config(bad)
    bad.write_text(text.replace("shock_bp = 450", "shock_bp = 450\nextra = 1"))
    with pytest.raises(H.HunterConfigError):
        H.load_hunter_config(bad)
    bad.write_text(text)
    assert H.load_hunter_config(bad).sha256 == CONFIG.sha256  # the same bytes, the same hash


# ---------------------------------------------------------------------- the rule against the frozen script


def _frozen():
    spec = importlib.util.spec_from_file_location("chocs_fade_meche_s", FROZEN)
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
