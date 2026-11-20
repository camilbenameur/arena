"""Perp league, step 3: riskd (evaluate_perp) and its policy. No network.

The property test runs 3 000 generated worlds by default; set ARENA_PERP_RISKD_EXAMPLES=100000 for the full
acceptance run of the step (docs/ETUDE-AGENTS-TRADERS.md §11, step 3). Its oracle is written here in plain
integers, independently of riskd's helpers.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from arena.data import RateLimitedHttp
from arena.journal import Journal
from arena.perp import riskd as R
from arena.perp.kraken_futures import KrakenFuturesClient
from arena.perp.ledger import MarginAccount, PerpPosition, apply_fill, replay
from arena.perp.policy import PerpPolicyError, load_perp_policy
from arena.perp.riskd import InstrumentMarket, PerpCounters, PerpIntent, PerpMarketView, evaluate_perp
from arena.perp.sim import MinuteCandles, PerpSimulator, SimParams

FIX = Path(__file__).parent / "fixtures" / "perp"
POLICY_PATH = Path(__file__).resolve().parent.parent / "config" / "policy-perp.toml"
POLICY = load_perp_policy(POLICY_PATH)
PARAMS = SimParams()
NOW = 1_794_499_200
FX = (1_100_000, 1_100_100)


def _specs():
    body = (FIX / "instruments.json").read_bytes()
    http = RateLimitedHttp(
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body))),
        sleep=lambda s: None,
        clock=lambda: 0.0,
    )
    return KrakenFuturesClient(http).instruments(POLICY.instruments)


SPECS = _specs()
PRICES = {
    "PF_XBTUSD": 70_000_000_000,
    "PF_ETHUSD": 2_000_000_000,
    "PF_SOLUSD": 80_000_000,
    "PF_XRPUSD": 1_000_000,
    "PF_LINKUSD": 10_000_000,
    "PF_LTCUSD": 50_000_000,
}


def inst_market(price: int, *, tick: int, rate: int = 10_000_000, age: int = 0) -> InstrumentMarket:
    ts = NOW - age
    return InstrumentMarket(
        bid_uusd=price,
        ask_uusd=price + tick,
        quote_ts=ts,
        mark_uusd=price,
        mark_ts=ts,
        index_uusd=price,
        index_ts=ts,
        relative_funding_e12=rate,
        funding_ts=ts,
        median_spread_uusd=tick,
    )


def market(prices: dict[str, int] | None = None, **kw) -> PerpMarketView:
    prices = prices or PRICES
    return PerpMarketView(
        {i: inst_market(p, tick=SPECS[i].tick_uusd, **kw) for i, p in prices.items()}, FX[0], FX[1], NOW
    )


def fresh() -> MarginAccount:
    return MarginAccount("P", 1_000_000_000, 1_000_000_000)


COUNTERS = PerpCounters(
    equity_month_start_ueur=1_000_000_000, equity_24h_ago_ueur=1_000_000_000, equity_peak_ueur=1_000_000_000
)


def intent(action="open_long", inst="PF_XBTUSD", **kw) -> PerpIntent:
    base = {"intent_id": "i", "portfolio": "P", "ts": NOW, "instrument": inst, "action": action}
    if action.startswith("open"):
        base.update(size_bp=2000, stop_bp=300, horizon_h=48, expected_move_bp=800)
    base.update(kw)
    return PerpIntent(**base)


def ev(it, acc=None, mkt=None, counters=COUNTERS, kill=False, policy=POLICY, specs=SPECS):
    return evaluate_perp(it, acc or fresh(), mkt or market(), specs, counters, policy, PARAMS, NOW, kill)


def fill(acc: MarginAccount, inst: str, v, seq: int) -> None:
    probe = {
        "instrument": inst,
        "qty": v.qty,
        "price_uusd": v.est_price_uusd,
        "fee_ueur": v.metrics.get("fee_ueur", 0),
        "fx_bid": FX[0],
        "fx_ask": FX[1],
        "reason": "intent",
    }
    apply_fill(acc, probe, NOW, seq)
    if v.stop_uusd is not None and inst in acc.positions:
        acc.positions[inst].stop_uusd = v.stop_uusd


# ---------------------------------------------------------------------- policy


def test_policy_loads_and_is_consistent():
    assert POLICY.max_leverage_bp == 20_000 and len(POLICY.sha256) == 64
    assert 2 * POLICY.max_open_risk_bp <= POLICY.drawdown_halt_bp


@pytest.mark.parametrize(
    "edit, match",
    [
        (lambda t: t.replace("max_leverage_bp  = 20000", "max_leverage_bp  = 30000"), "hard cap"),
        (lambda t: t.replace("max_trade_loss_bp  = 300", "max_trade_loss_bp  = 600"), "freeze"),
        (lambda t: t.replace("max_open_risk_bp   = 750", "max_open_risk_bp   = 800"), "halt"),
        (lambda t: t.replace("stop_bp_min        = 100", "stop_bp_min        = 2000"), "stop_bp_min"),
        (lambda t: t.replace("daily_loss_freeze_bp = 500", "daily_loss_freeze_bp = 1600"), "freeze"),
        (lambda t: t.replace("max_data_age_s       = 600", "max_data_age_s       = 3600"), "sane bound"),
        (lambda t: "surprise = 1\n" + t, "unknown"),
    ],
)
def test_policy_rejects(tmp_path, edit, match):
    p = tmp_path / "p.toml"
    p.write_text(edit(POLICY_PATH.read_text(encoding="utf-8")), encoding="utf-8")
    with pytest.raises(PerpPolicyError, match=match):
        load_perp_policy(p)


def test_lot_steps_parsed():
    assert SPECS["PF_XBTUSD"].lot_step_qty == 10_000  # 0.0001 BTC
    assert SPECS["PF_XRPUSD"].lot_step_qty == 100_000_000  # 1 XRP


# ---------------------------------------------------------------------- approvals


@pytest.mark.parametrize("action", ["open_long", "open_short"])
def test_entry_approved_and_accepted_by_the_simulator(tmp_path, action):
    v = ev(intent(action))
    assert v.approved, v.reasons
    side = 1 if action == "open_long" else -1
    assert v.qty * side > 0 and v.qty % SPECS["PF_XBTUSD"].lot_step_qty == 0
    assert (v.stop_uusd < v.est_price_uusd) if side > 0 else (v.stop_uusd > v.est_price_uusd)
    sim = PerpSimulator(Journal(tmp_path / "j.jsonl"), {i: s.tick_uusd for i, s in SPECS.items()}, PARAMS)
    sim.open_portfolio("P", "test", 0)
    m = market().instruments["PF_XBTUSD"]
    out = sim.market_order("i", "P", "PF_XBTUSD", v.qty, (m.bid_uusd, m.ask_uusd), FX, NOW, marks=PRICES)
    assert out["price_uusd"] == v.est_price_uusd and out["fee_ueur"] == v.metrics["fee_ueur"]


def test_reductions_pass_even_when_blocked():
    acc = fresh()
    acc.halted, acc.frozen_until_ts = True, NOW + 10
    acc.positions["PF_XBTUSD"] = PerpPosition("PF_XBTUSD", 1_000_000, 70_000_000_000, 0, 1, 68_000_000_000)
    acc.positions["PF_ETHUSD"] = PerpPosition("PF_ETHUSD", 10_000_000, 2_000_000_000, 0, 2, 1_900_000_000)
    only_btc = PerpMarketView({"PF_XBTUSD": market().instruments["PF_XBTUSD"]}, *FX, NOW - 10_000)
    no_btc_policy = replace(POLICY, instruments=("PF_ETHUSD",))
    blocked = replace(COUNTERS, fees_month_ueur=10**12, opens_24h=99, equity_24h_ago_ueur=0)
    for it in (intent("close"), intent("reduce", size_bp=5000)):
        v = ev(it, acc=acc, mkt=only_btc, kill=True, counters=blocked, policy=no_btc_policy)
        assert v.approved, v.reasons
    assert ev(intent("close"), acc=acc).qty == -1_000_000
    assert R.NO_POSITION in ev(intent("close", inst="PF_SOLUSD"), acc=acc).reasons
    junk = replace(market().instruments["PF_XBTUSD"], bid_uusd=1, ask_uusd=2)
    assert (
        R.NO_QUOTE in ev(intent("close"), acc=acc, mkt=PerpMarketView({"PF_XBTUSD": junk}, *FX, NOW)).reasons
    )


# ---------------------------------------------------------------------- each rule


@pytest.mark.parametrize(
    "kw, code",
    [
        ({"size_bp": 6000}, R.MAX_ORDER_SIZE),
        ({"stop_bp": None}, R.STOP_REQUIRED),
        ({"stop_bp": 50}, R.STOP_RANGE),
        ({"stop_bp": 2000}, R.STOP_RANGE),
        ({"expected_move_bp": 50}, R.EDGE_TOO_SMALL),
        ({"expected_move_bp": None}, R.EDGE_TOO_SMALL),
        ({"expected_move_bp": 10**9}, R.BAD_EXPECTED_MOVE),
        ({"size_bp": 0}, R.BAD_SIZE),
        ({"take_profit_bp": -1}, R.BAD_TAKE_PROFIT),
        ({"horizon_h": 169}, R.BAD_HORIZON),
        ({"size_bp": 1}, R.ORDER_TOO_SMALL),
        ({"size_bp": 5000, "stop_bp": 1500}, R.MAX_TRADE_LOSS),
        ({"inst": "PF_DOGEUSD"}, R.NOT_WHITELISTED),
        ({"action": "buy"}, R.BAD_ACTION),
        ({"portfolio": "Q"}, R.BAD_PORTFOLIO),
        ({"ts": NOW - 601}, R.INTENT_STALE),
        ({"ts": NOW + 60}, R.INTENT_STALE),
    ],
)
def test_intent_rules(kw, code):
    v = ev(intent(**kw))
    assert not v.approved and code in v.reasons, v.reasons


@pytest.mark.parametrize(
    "mutate, code",
    [
        ({"kill": True}, R.KILL_SWITCH),
        ({"counters": replace(COUNTERS, opens_24h=4)}, R.DAILY_TRADES),
        ({"counters": replace(COUNTERS, orders_last_minute=20)}, R.ORDER_RATE),
        ({"counters": replace(COUNTERS, last_open_ts={"PF_XBTUSD": NOW - 14_399})}, R.TOO_SOON),
        (
            {"counters": replace(COUNTERS, fees_month_ueur=29_800_000)},
            R.FEE_BUDGET,
        ),  # the order's own fees count
        ({"counters": replace(COUNTERS, equity_month_start_ueur=0)}, R.FEE_BUDGET),
        ({"counters": replace(COUNTERS, equity_peak_ueur=1_200_000_000)}, R.HALTED),
        ({"counters": replace(COUNTERS, equity_24h_ago_ueur=1_060_000_000)}, R.FROZEN),
        ({"counters": replace(COUNTERS, equity_24h_ago_ueur=0)}, R.COUNTERS_MISSING),
        ({"mkt": market(age=601)}, R.DATA_STALE),
        ({"mkt": market(age=-60)}, R.DATA_STALE),  # in the future
        ({"mkt": market(rate=200_000_000)}, R.FUNDING_EXTREME),
    ],
)
def test_context_rules(mutate, code):
    v = ev(intent(), **mutate)
    assert not v.approved and code in v.reasons, v.reasons


def test_boundaries():
    assert ev(intent(), counters=replace(COUNTERS, last_open_ts={"PF_XBTUSD": NOW - 14_400})).approved
    assert ev(intent(), counters=replace(COUNTERS, opens_24h=3)).approved


def test_counters_are_required():
    with pytest.raises(TypeError):
        PerpCounters()  # type: ignore[call-arg]


def test_funding_extreme_only_on_the_paying_side():
    assert ev(intent("open_short"), mkt=market(rate=200_000_000)).approved  # shorts receive
    assert not ev(intent("open_short"), mkt=market(rate=-200_000_000)).approved


def test_market_sanity_rules():
    base = market()
    xbt = base.instruments["PF_XBTUSD"]
    m = xbt.mark_uusd
    off = m * 1009 // 1000
    for bad, code in (
        (replace(xbt, index_uusd=None), R.MARK_SANITY),
        (replace(xbt, index_ts=NOW - 10_000), R.MARK_SANITY),
        (replace(xbt, mark_uusd=m * 102 // 100), R.MARK_SANITY),
        (replace(xbt, bid_uusd=off, ask_uusd=off + 1_000_000), R.MARK_SANITY),  # mid off the mark
        (replace(xbt, ask_uusd=xbt.bid_uusd + 100 * xbt.median_spread_uusd), R.SPREAD_ANOMALY),
        (replace(xbt, median_spread_uusd=None), R.SPREAD_ANOMALY),
        (replace(xbt, funding_ts=None), R.DATA_STALE),
        (replace(xbt, quote_ts=NOW - 10_000), R.DATA_STALE),
        (replace(xbt, ask_uusd=xbt.bid_uusd - 1), R.NO_QUOTE),
    ):
        mkt = PerpMarketView({**base.instruments, "PF_XBTUSD": bad}, *FX, NOW)
        v = ev(intent(), mkt=mkt)
        assert not v.approved and code in v.reasons, (code, v.reasons)
    assert R.DATA_STALE in ev(intent(), mkt=PerpMarketView(base.instruments, FX[0], FX[1], NOW - 601)).reasons
    assert R.NO_FX in ev(intent(), mkt=PerpMarketView(base.instruments, 2, 1, NOW)).reasons


def test_stale_mark_of_another_held_position_blocks_entries():
    acc = fresh()
    acc.positions["PF_SOLUSD"] = PerpPosition("PF_SOLUSD", 100_000_000, 80_000_000, 0, 1, 76_000_000)
    stale_sol = replace(market().instruments["PF_SOLUSD"], mark_ts=NOW - 3 * 86400)
    mkt = PerpMarketView({**market().instruments, "PF_SOLUSD": stale_sol}, *FX, NOW)
    assert R.DATA_STALE in ev(intent(), acc=acc, mkt=mkt).reasons


def test_untradeable_or_incomplete_contract_refused():
    specs = {**SPECS, "PF_XBTUSD": replace(SPECS["PF_XBTUSD"], tradeable=False)}
    assert R.NOT_TRADEABLE in ev(intent(), specs=specs).reasons
    specs = {**SPECS, "PF_XBTUSD": replace(SPECS["PF_XBTUSD"], lot_step_qty=None)}
    assert R.UNKNOWN_INSTRUMENT in ev(intent(), specs=specs).reasons


def test_no_flip_and_never_loosen_the_stop():
    acc = fresh()
    acc.positions["PF_XBTUSD"] = PerpPosition("PF_XBTUSD", -100_000, 70_000_000_000, 0, 1, 72_000_000_000)
    v = ev(intent("open_long"), acc=acc)
    assert R.NO_FLIP in v.reasons and R.STOP_RANGE not in v.reasons
    acc.positions["PF_XBTUSD"] = PerpPosition("PF_XBTUSD", 100_000, 70_000_000_000, 0, 1, 69_500_000_000)
    v = ev(intent("open_long", size_bp=500, stop_bp=1000), acc=acc)
    assert v.approved and v.stop_uusd == 69_500_000_000  # the tighter, existing stop is kept


def test_unrealized_gain_given_back_counts_as_risk():
    """A long bought far below the mark, stop at entry: the loss at its stop is measured from the MARK."""
    acc = fresh()
    acc.positions["PF_XBTUSD"] = PerpPosition("PF_XBTUSD", 1_000_000, 50_000_000_000, 0, 1, 50_000_000_000)
    v = ev(intent(inst="PF_ETHUSD", size_bp=500, stop_bp=200), acc=acc)  # BTC at 70k: 200 USD at risk
    assert R.MAX_OPEN_RISK in v.reasons, v.reasons


def test_open_risk_counts_every_position():
    acc = fresh()
    for n, inst in enumerate(("PF_XBTUSD", "PF_ETHUSD")):
        v = ev(intent(inst=inst, size_bp=5000, stop_bp=400), acc=acc)
        assert v.approved, v.reasons
        fill(acc, inst, v, n + 1)
    v3 = ev(intent(inst="PF_SOLUSD", size_bp=5000, stop_bp=400), acc=acc)
    assert R.MAX_OPEN_RISK in v3.reasons and R.MAX_TRADE_LOSS not in v3.reasons, v3.reasons


def test_internal_error_fails_closed_and_names_the_error():
    broken = PerpMarketView({"PF_XBTUSD": "not a market"}, *FX, NOW)  # type: ignore[dict-item]
    v = ev(intent(), mkt=broken)
    assert not v.approved and v.reasons == (R.INTERNAL_ERROR,) and v.error


# ---------------------------------------------------------------------- properties (independent oracle)


EXAMPLES = int(os.environ.get("ARENA_PERP_RISKD_EXAMPLES", "3000"))


def oracle_cost(uusd: int) -> int:
    return -(-uusd * 1_000_000 // FX[0])


def oracle_pnl_eur(pnl_uusd: int) -> int:
    return pnl_uusd * 1_000_000 // FX[1] if pnl_uusd >= 0 else -oracle_cost(-pnl_uusd)


def oracle(acc: MarginAccount, marks: dict[str, int]) -> dict[str, int]:
    """Plain-integer recomputation of the capped quantities (no riskd or ledger helper)."""
    equity = at_stops = acc.collateral_ueur
    gross = 0
    for i, p in acc.positions.items():
        equity += oracle_pnl_eur((marks[i] - p.entry_uusd) * p.qty // 100_000_000)
        gross += oracle_cost(-(-abs(p.qty) * marks[i] // 100_000_000))
        at_stops += oracle_pnl_eur((p.stop_uusd - p.entry_uusd) * p.qty // 100_000_000)
    return {"equity": equity, "gross": gross, "equity_at_stops": at_stops}


@st.composite
def worlds(draw):
    """0-3 legal positions built through riskd at one set of prices, then the market MOVES (-30 % to +30 %),
    stops crossed by the move are taken out, some stops trail, then one intent (valid or not) is evaluated
    at the new prices."""
    tick = {i: SPECS[i].tick_uusd for i in PRICES}
    pre = [
        intent(
            draw(st.sampled_from(["open_long", "open_short"])),
            inst=draw(st.sampled_from(list(PRICES))),
            size_bp=draw(st.integers(100, 5000)),
            stop_bp=draw(st.integers(100, 1500)),
        )
        for _ in range(draw(st.integers(0, 3)))
    ]
    moves = {i: draw(st.integers(70, 130)) for i in PRICES}
    later = {i: max(tick[i], p * moves[i] // 100 // tick[i] * tick[i]) for i, p in PRICES.items()}
    trail = draw(st.booleans())
    final = intent(
        draw(st.sampled_from(["open_long", "open_short", "reduce", "close"])),
        inst=draw(st.sampled_from([*list(PRICES), "PF_DOGEUSD"])),
        size_bp=draw(st.one_of(st.none(), st.integers(-10, 12_000))),
        stop_bp=draw(st.one_of(st.none(), st.integers(0, 3000))),
        take_profit_bp=draw(st.one_of(st.none(), st.integers(-5, 20_000))),
        horizon_h=draw(st.one_of(st.none(), st.integers(-5, 1000))),
        expected_move_bp=draw(st.one_of(st.none(), st.integers(-5, 5000))),
    )
    rate = draw(st.integers(-400_000_000, 400_000_000))
    return pre, later, trail, final, rate


@settings(max_examples=EXAMPLES, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(worlds())
def test_no_approved_intent_violates_the_rules(world):
    pre, later, trail, final, rate = world
    acc = fresh()
    mkt0 = market(rate=rate)
    for n, it in enumerate(pre):
        v = evaluate_perp(it, acc, mkt0, SPECS, COUNTERS, POLICY, PARAMS, NOW, False)
        if v.approved:
            fill(acc, it.instrument, v, n + 1)
    for i, p in list(acc.positions.items()):
        if (later[i] <= p.stop_uusd) if p.qty > 0 else (later[i] >= p.stop_uusd):
            del acc.positions[i]  # the move went through the stop: that position is gone
        elif trail:  # trail the stop halfway towards the new mark (never loosening)
            half = (p.stop_uusd + later[i]) // 2
            p.stop_uusd = max(p.stop_uusd, half) if p.qty > 0 else min(p.stop_uusd, half)
    v = evaluate_perp(final, acc, market(later, rate=rate), SPECS, COUNTERS, POLICY, PARAMS, NOW, False)
    if not v.approved:
        assert v.qty == 0 and v.reasons
        return
    inst = final.instrument
    before = acc.positions.get(inst)
    if final.action in ("reduce", "close"):
        assert before is not None and 0 < abs(v.qty) <= abs(before.qty) and v.qty * before.qty < 0
        return
    assert inst in POLICY.instruments and v.qty % SPECS[inst].lot_step_qty == 0
    assert before is None or (before.qty > 0) == (v.qty > 0)  # never a flip
    fill(acc, inst, v, 99)
    o = oracle(acc, later)
    eq, gross = o["equity"], o["gross"]
    assert gross * 10_000 <= POLICY.max_leverage_bp * eq + 10_000  # 2x (1 µEUR of rounding slack)
    assert abs(acc.positions[inst].qty) <= SPECS[inst].max_position_qty
    stop = acc.positions[inst].stop_uusd
    assert (stop < later[inst]) if v.qty > 0 else (stop > later[inst])
    # every stop filling at its level (before gap and fees) loses at most the open-risk cap, and never
    # takes the equity under the margin close-out threshold
    assert (eq - o["equity_at_stops"]) * 10_000 <= POLICY.max_open_risk_bp * eq
    assert o["equity_at_stops"] * 10_000 >= PARAMS.closeout_margin_bp * gross


# ---------------------------------------------------------------------- simulated crash


@pytest.mark.parametrize("drop_pct", [25, 35, 45])
def test_simultaneous_crash_on_six_assets(tmp_path, drop_pct):
    """Legal positions on the six instruments, then a crash of -25 to -45 % in one minute: the ledger stays
    exact (invariant, collateral >= 0) and every long is closed by its stop or by the margin close-out."""
    sim = PerpSimulator(Journal(tmp_path / "j.jsonl"), {i: s.tick_uusd for i, s in SPECS.items()}, PARAMS)
    sim.open_portfolio("P", "test", 0)
    mkt = market()
    for n, inst in enumerate(PRICES):
        acc = sim.states()["P"]
        it = intent(inst=inst, size_bp=1500, stop_bp=200)
        v = evaluate_perp(it, acc, mkt, SPECS, COUNTERS, POLICY, PARAMS, NOW, False)
        if not v.approved:
            continue
        m = mkt.instruments[inst]
        sim.market_order(f"o{n}", "P", inst, v.qty, (m.bid_uusd, m.ask_uusd), FX, NOW + n, marks=PRICES)
        sim.set_conditional("P", inst, "stop", v.stop_uusd, NOW + n)
    assert len(sim.states()["P"].positions) >= 3
    minute = (NOW // 60 + 1) * 60
    crash = {
        i: MinuteCandles((p, p, p * (100 - drop_pct) // 100, p * (100 - drop_pct) // 100), None)
        for i, p in PRICES.items()
    }
    fills, problems = sim.process_minute(minute, crash, FX)
    acc = replay(sim.journal.events())["P"]
    assert problems == [] and acc.invariant_ok() and acc.collateral_ueur >= 0
    assert acc.positions == {} and fills
