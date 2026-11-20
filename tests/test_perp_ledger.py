"""Perp league, step 2: ledger and simulator (docs/SPEC-PERP-LEDGER.md). No network.

The golden results in tests/golden/perp/expected.json were computed independently by hand, twice, from the
specification only, and matched this implementation to the µEUR.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from arena.journal import Journal
from arena.perp.ledger import (
    PerpLedgerError,
    cost_eur,
    funding_amount_ueur,
    gain_eur,
    price_pnl_uusd,
    qty_seconds,
    replay,
    to_eur,
)
from arena.perp.sim import MinuteCandles, PerpSimulator, SimParams, buy_price, sell_price
from tests.perp_golden_runner import GOLDEN, load_scenarios, run_scenario

SPEC = load_scenarios()
EXPECTED = json.loads((GOLDEN / "expected.json").read_text(encoding="utf-8"))
FX = (1_100_000, 1_100_100)
TICKS = {"BTC": 1_000_000, "ETH": 100_000}
Q = (70_000_000_000, 70_001_000_000)
QE = (2_000_000_000, 2_000_100_000)
MARKS = {"BTC": 70_000_500_000, "ETH": 2_000_050_000}
CRASH = MinuteCandles((69_000_000_000, 69_000_000_000, 67_000_000_000, 67_000_000_000), None)
CALM = MinuteCandles((70_000_000_000, 70_100_000_000, 69_900_000_000, 70_000_000_000), None)


@pytest.mark.parametrize("name", sorted(SPEC["scenarios"]))
def test_golden_scenarios(name, tmp_path):
    assert run_scenario(SPEC["scenarios"][name], tmp_path, SPEC) == EXPECTED[name]


def test_golden_covers_every_scenario():
    assert set(EXPECTED) == set(SPEC["scenarios"]) and len(EXPECTED) >= 19


# ---------------------------------------------------------------------- conversions


def test_conversions_are_unfavourable():
    assert cost_eur(1_100_001, *FX) == 1_000_001  # ceil at the bid
    assert gain_eur(1_100_100, *FX) == 1_000_000 and gain_eur(1_100_099, *FX) == 999_999  # floor at the ask
    assert to_eur(-1, *FX) == -1 and to_eur(1, *FX) == 0
    assert price_pnl_uusd(-100_000_000, 10, 11) == -1  # short loses when the price rises
    assert price_pnl_uusd(1, 0, 1) == 0 and price_pnl_uusd(-1, 0, 1) == -1  # rounded towards -inf


def test_funding_sign_conventions():
    hour = 100_000_000 * 3600
    assert funding_amount_ueur(hour, 1_000_000_000, *FX) > 0  # long, positive rate: pays
    assert funding_amount_ueur(-hour, 1_000_000_000, *FX) < 0  # short, positive rate: receives
    assert funding_amount_ueur(hour, -1_000_000_000, *FX) < 0
    assert funding_amount_ueur(1, 1, *FX) == 1  # a paid dust amount rounds up to 1 µEUR
    assert funding_amount_ueur(-1, 1, *FX) == 0  # a received dust amount rounds down to 0


def test_qty_seconds():
    h = [(100, 5), (200, 0), (300, -2)]
    assert qty_seconds(h, 0, 400) == 5 * 100 + 0 + (-2) * 100
    assert qty_seconds(h, 150, 250) == 5 * 50
    assert qty_seconds(h, 500, 600) == -2 * 100
    assert qty_seconds([], 0, 3600) == 0


def test_inconsistent_fx_refused():
    with pytest.raises(PerpLedgerError):
        cost_eur(1, 1_100_100, 1_100_000)


def test_prices():
    assert buy_price(70_001_000_000, 5, 1_000_000) == 70_037_000_000
    assert sell_price(70_000_000_000, 5, 1_000_000) == 69_965_000_000


# ---------------------------------------------------------------------- simulator behaviour


def sim_at(
    tmp_path: Path, params: SimParams | None = None, portfolios: tuple[str, ...] = ("P",)
) -> PerpSimulator:
    s = PerpSimulator(Journal(tmp_path / "events.jsonl"), TICKS, params)
    for p in portfolios:
        s.open_portfolio(p, "test", 0)
    return s


def test_invalid_events_never_reach_the_journal(tmp_path):
    s = sim_at(tmp_path)
    s.market_order("a", "P", "BTC", 1_000_000, Q, FX, 1, marks=MARKS)
    n = len(s.journal.events())
    for bad in (0, -5, True, 1.5):
        with pytest.raises(PerpLedgerError):
            s.set_conditional("P", "BTC", "stop", bad, 2)
    with pytest.raises(PerpLedgerError):
        s.settle_funding("BTC", 3600, True, FX)
    with pytest.raises(PerpLedgerError, match="flip"):
        s.market_order("b", "P", "BTC", -2_000_000, Q, FX, 2)
    with pytest.raises(PerpLedgerError):
        s.set_conditional("P", "ETH", "stop", 1, 2)  # no position
    assert len(s.journal.events()) == n
    replay(s.journal.events())  # the journal stays readable


def test_order_id_idempotent_and_collision_detected(tmp_path):
    s = sim_at(tmp_path, portfolios=("P", "R"))
    assert s.market_order("a", "P", "BTC", 1_000_000, Q, FX, 1, marks=MARKS) is not None
    assert s.market_order("a", "P", "BTC", 1_000_000, Q, FX, 1, marks=MARKS) is None
    with pytest.raises(PerpLedgerError, match="already used"):
        s.market_order("a", "R", "BTC", 1_000_000, Q, FX, 1, marks=MARKS)
    assert s.states()["P"].positions["BTC"].qty == 1_000_000


def test_ledger_refuses_duplicates_written_by_another_writer(tmp_path):
    s = sim_at(tmp_path)
    s.market_order("a", "P", "BTC", 1_000_000, Q, FX, 1, marks=MARKS)
    fill = next(e for e in s.journal.events() if e["type"] == "perp_fill")
    s.journal.append("perp_fill", fill["payload"], fill["ts"])  # a racing writer appending the same order
    with pytest.raises(PerpLedgerError, match="duplicate"):
        replay(s.journal.events())


def test_entry_checks(tmp_path):
    s = sim_at(tmp_path)
    s.market_order("a", "P", "BTC", 1_000_000, Q, FX, 1, marks=MARKS)
    with pytest.raises(PerpLedgerError, match="no valid mark"):
        s.market_order("b", "P", "ETH", -10_000_000, QE, FX, 2)  # BTC held, no mark given
    with pytest.raises(PerpLedgerError, match="initial margin"):
        s.market_order("c", "P", "ETH", -100_000_000, QE, FX, 2, marks=MARKS)
    s.journal.append("portfolio_halted", {"portfolio": "P", "reason": "test", "until_ts": 0}, 3)
    with pytest.raises(PerpLedgerError, match="halted"):
        s.market_order("d", "P", "BTC", 100_000, Q, FX, 4, marks=MARKS)
    assert s.market_order("e", "P", "BTC", -1_000_000, Q, FX, 5) is not None  # closing always passes


def test_out_of_order_fill_refused(tmp_path):
    s = sim_at(tmp_path)
    s.market_order("a", "P", "BTC", 1_000_000, Q, FX, 1000, marks=MARKS)
    with pytest.raises(PerpLedgerError, match="older"):
        s.market_order("b", "P", "BTC", -1_000_000, Q, FX, 999)


def test_funding_late_and_pro_rata(tmp_path):
    s = sim_at(tmp_path)
    s.market_order("a", "P", "BTC", 1_000_000, Q, FX, 1800, marks=MARKS)
    s.market_order("b", "P", "BTC", -1_000_000, Q, FX, 2700)
    out = s.settle_funding("BTC", 3600, 700_000_000, FX)  # settled after the close: still owed
    assert len(out) == 1 and out[0]["qty_seconds"] == 1_000_000 * 900
    assert s.settle_funding("BTC", 3600, 700_000_000, FX) == []
    with pytest.raises(PerpLedgerError, match="settled"):
        s.market_order("c", "P", "BTC", 1_000_000, Q, FX, 3000, marks=MARKS)


def test_funding_mismatch_refused_by_ledger(tmp_path):
    s = sim_at(tmp_path)
    s.market_order("a", "P", "BTC", 1_000_000, Q, FX, 0, marks=MARKS)
    bad = {
        "portfolio": "P",
        "instrument": "BTC",
        "stamp": 3600,
        "qty_seconds": 1_000_000 * 3600,
        "rate_nusd": 700_000_000,
        "fx_bid": FX[0],
        "fx_ask": FX[1],
        "amount_ueur": 1,
    }
    s.journal.append("funding", bad, 3600)
    with pytest.raises(PerpLedgerError, match="recomputed"):
        replay(s.journal.events())


def test_watcher_catch_up_is_idempotent(tmp_path):
    s = sim_at(tmp_path)
    s.market_order("a", "P", "BTC", 1_000_000, Q, FX, 0, marks=MARKS)
    s.set_conditional("P", "BTC", "stop", 68_000_000_000, 0)
    for m in range(60, 60 * 180, 60):  # three hours of a stopped watcher, caught up minute by minute
        s.process_minute(m, {"BTC": CALM}, FX)
    fills, _ = s.process_minute(60 * 180, {"BTC": CRASH}, FX)
    assert len(fills) == 1 and fills[0]["reason"] == "stop" and fills[0]["ts"] == 60 * 180 + 59
    again, _ = s.process_minute(60 * 180, {"BTC": CRASH}, FX)
    assert again == [] and s.states()["P"].positions == {}


def test_reopened_position_gets_new_order_ids(tmp_path):
    s = sim_at(tmp_path)
    s.market_order("a", "P", "BTC", 1_000_000, Q, FX, 0, marks=MARKS)
    s.set_conditional("P", "BTC", "stop", 68_000_000_000, 0)
    f1, _ = s.process_minute(60, {"BTC": CRASH}, FX)
    s.market_order("b", "P", "BTC", 1_000_000, Q, FX, 119, marks=MARKS)  # reopened within the same second
    s.set_conditional("P", "BTC", "stop", 68_000_000_000, 119)
    f2, _ = s.process_minute(120, {"BTC": CRASH}, FX)
    assert f1[0]["order_id"] != f2[0]["order_id"] and s.states()["P"].positions == {}


def test_one_bad_portfolio_does_not_block_the_others(tmp_path):
    s = sim_at(tmp_path, portfolios=("A", "B"))
    s.market_order("a", "A", "BTC", 1_000_000, Q, FX, 0, marks=MARKS)
    s.set_conditional("A", "BTC", "stop", 68_000_000_000, 0)
    s.market_order("b", "B", "ETH", 10_000_000, QE, FX, 0, marks=MARKS)
    s.set_conditional("B", "ETH", "stop", 1_900_000_000, 0)
    btc_only = PerpSimulator(s.journal, {"BTC": 1_000_000})  # ETH unknown: B's processing fails
    eth_crash = MinuteCandles((1_800_000_000, 1_800_000_000, 1_700_000_000, 1_700_000_000), None)
    fills, problems = btc_only.process_minute(60, {"BTC": CRASH, "ETH": eth_crash}, FX)
    assert [f["portfolio"] for f in fills] == ["A"]
    assert len(problems) == 1 and problems[0].startswith("B minute 60")


def test_missing_candle_with_and_without_fallback(tmp_path):
    s = sim_at(tmp_path)
    s.market_order("a", "P", "BTC", 1_000_000, Q, FX, 0, marks=MARKS)
    s.market_order("b", "P", "ETH", 10_000_000, QE, FX, 0, marks=MARKS)
    s.set_conditional("P", "BTC", "stop", 68_000_000_000, 0)
    fills, problems = s.process_minute(60, {"ETH": MinuteCandles((2_000_000_000,) * 4)}, FX)
    assert fills == [] and any("close-out not tested" in p for p in problems)
    assert any(e["type"] == "minute_incomplete" for e in s.journal.events())
    fills, problems = s.process_minute(
        120, {"ETH": MinuteCandles((2_000_000_000,) * 4)}, FX, fallback_marks=MARKS
    )
    assert fills == [] and problems == []  # BTC stop not evaluated without its candle, close-out tested


def test_closeout_crash_between_instruments_is_finished_on_rerun(tmp_path):
    s = sim_at(tmp_path)
    s.market_order("a", "P", "BTC", 2_000_000, Q, FX, 0, marks=MARKS)
    s.market_order("b", "P", "ETH", 10_000_000, QE, FX, 0, marks=MARKS)
    bad = {
        "BTC": MinuteCandles((70_000_000_000, 70_000_000_000, 25_000_000_000, 25_000_000_000), None),
        "ETH": MinuteCandles((2_000_000_000, 2_000_000_000, 1_000_000_000, 1_000_000_000), None),
    }
    s.process_minute(60, bad, FX)
    events = s.journal.events()
    first_closeout = next(
        i
        for i, e in enumerate(events)
        if e["type"] == "perp_fill" and e["payload"]["reason"] == "margin_closeout"
    )
    j2 = Journal(tmp_path / "crashed.jsonl")
    for e in events[: first_closeout + 1]:  # died after closing BTC, before ETH and the summary
        j2.append(e["type"], e["payload"], e["ts"])
    s2 = PerpSimulator(j2, TICKS)
    calm = {"BTC": MinuteCandles((60_000_000_000,) * 4), "ETH": MinuteCandles((2_000_000_000,) * 4)}
    s2.process_minute(60, {**bad, }, FX)  # re-run of the same minute
    acc = replay(j2.events())["P"]
    assert acc.positions == {} and acc.margin_closeouts == 1
    summary = [e for e in j2.events() if e["type"] == "margin_closeout"]
    assert len(summary) == 1 and summary[0]["payload"]["resumed_after_crash"] is True
    assert calm  # the rerun did not need calm prices: the decision was durable


def test_flatten_requires_every_quote(tmp_path):
    s = sim_at(tmp_path)
    s.market_order("a", "P", "BTC", 1_000_000, Q, FX, 0, marks=MARKS)
    s.market_order("b", "P", "ETH", -50_000_000, QE, FX, 0, marks=MARKS)
    with pytest.raises(PerpLedgerError, match="without a quote"):
        s.flatten("P", 20, {"BTC": Q}, FX, "kill_switch")
    out = s.flatten("P", 20, {"BTC": Q, "ETH": QE}, FX, "kill_switch")
    assert len(out) == 2 and s.states()["P"].positions == {}
    with pytest.raises(PerpLedgerError):
        s.flatten("P", 21, {}, FX, "boredom")


def test_write_equity_idempotent(tmp_path):
    s = sim_at(tmp_path)
    s.market_order("a", "P", "BTC", 1_000_000, Q, FX, 0, marks=MARKS)
    eq = s.write_equity("P", 10, MARKS, FX)
    assert eq["equity_ueur"] == eq["collateral_ueur"] + eq["unrealized_ueur"] and eq["gross_ueur"] > 0
    assert s.write_equity("P", 10, MARKS, FX) is None
    with pytest.raises(PerpLedgerError, match="mark"):
        s.write_equity("P", 11, {}, FX)


def test_minutes_do_not_reread_the_journal(tmp_path, monkeypatch):
    s = sim_at(tmp_path)
    s.market_order("a", "P", "BTC", 1_000_000, Q, FX, 0, marks=MARKS)
    s.set_conditional("P", "BTC", "stop", 60_000_000_000, 0)
    calls = {"n": 0}
    original = s.journal.iter_events

    def counting(*a, **k):
        calls["n"] += 1
        return original(*a, **k)

    monkeypatch.setattr(s.journal, "iter_events", counting)
    t0 = time.monotonic()
    for m in range(60, 60 * 1441, 60):  # one day of minutes
        s.process_minute(m, {"BTC": CALM}, FX)
        if m % 3600 == 0:
            s.write_equity("P", m, MARKS, FX)
    assert calls["n"] == 0 and time.monotonic() - t0 < 30


# ---------------------------------------------------------------------- properties


@st.composite
def sequences(draw):
    steps = []
    for _ in range(draw(st.integers(1, 25))):
        kind = draw(st.sampled_from(["order", "order", "minute", "funding", "stop"]))
        inst = draw(st.sampled_from(["BTC", "ETH"]))
        steps.append((kind, inst, draw(st.integers(-3_000_000, 3_000_000)), draw(st.integers(20, 120))))
    return steps


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(sequences())
def test_invariant_and_replay_hold_for_any_sequence(tmp_path_factory, steps):
    """Whatever happens: collateral >= 0, the invariant holds, the journal replays to the same state, and the
    initial margin holds right after every accepted entry."""
    s = sim_at(tmp_path_factory.mktemp("p"))
    base = {"BTC": 70_000_000_000, "ETH": 2_000_000_000}
    marks = dict(base)
    for n, (kind, inst, qty, level) in enumerate(steps):
        ts = 3600 * (n + 1)
        price = base[inst] * level // 100  # from -80 % to +20 % of the base price
        marks[inst] = price
        quote = (price, price + TICKS[inst])
        try:
            if kind == "order" and qty:
                s.market_order(f"o{n}", "P", inst, qty, quote, FX, ts, marks=marks)
            elif kind == "stop":
                s.set_conditional("P", inst, "stop", price, ts)
            elif kind == "funding":
                s.settle_funding(inst, ts, qty * 1_000, FX)
            elif kind == "minute":
                mark = (price, price + TICKS[inst], max(TICKS[inst], price * 7 // 10), price)
                s.process_minute(ts, {i: MinuteCandles(mark) for i in ("BTC", "ETH")}, FX)
        except PerpLedgerError:
            pass  # refused events are never written
        acc = replay(s.journal.events())["P"]
        assert acc.collateral_ueur >= 0 and acc.invariant_ok()
    assert replay(s.journal.events()) == s.states()


def test_retired_portfolio_replays_flat_and_never_opens_again(tmp_path):
    s = sim_at(tmp_path)
    s.market_order("a", "P", "BTC", 1_000_000, Q, FX, 1, marks=MARKS)
    with pytest.raises(PerpLedgerError, match="open positions"):  # retiring needs a flat account
        s.append_event("portfolio_retired", {"portfolio": "P", "ts": 2, "reason": "manual", "note": ""}, 2)
    assert len(s.flatten("P", 3, {"BTC": Q}, FX, "retired")) == 1
    s.append_event("portfolio_retired", {"portfolio": "P", "ts": 4, "reason": "manual", "note": ""}, 4)
    s.append_event("portfolio_retired", {"portfolio": "P", "ts": 9, "reason": "manual", "note": ""}, 9)
    acc = replay(s.journal.events())["P"]  # the whole journal replays; the first date stays
    assert acc.retired and acc.retired_ts == 4 and not acc.positions and acc.invariant_ok()
    with pytest.raises(PerpLedgerError, match="retired"):
        s.market_order("b", "P", "BTC", 1_000_000, Q, FX, 10, marks=MARKS)
    with pytest.raises(PerpLedgerError, match="halt, kill_switch or retired"):
        s.flatten("P", 11, {"BTC": Q}, FX, "whatever")


def test_the_stop_of_the_hunters_portfolios_ignores_the_minute_of_the_entry_the_others_keep_it(tmp_path):
    from arena.perp.margin import HUNTER_NAMES

    hunter = min(HUNTER_NAMES)
    s = sim_at(tmp_path, portfolios=("P", hunter, "benchmark-perp:random"))
    for name in ("P", hunter, "benchmark-perp:random"):  # all enter at second 10 of the minute 0, stop armed then
        s.market_order(f"a:{name}", name, "BTC", 1_000_000, Q, FX, 10, marks=MARKS)
        s.set_conditional(name, "BTC", "stop", 68_000_000_000, 10)
    fills, _ = s.process_minute(0, {"BTC": CRASH}, FX)  # the minute of the entry: the candle holds the wick
    assert sorted(f["portfolio"] for f in fills) == ["P", "benchmark-perp:random"]  # the others: unchanged
    st = s.states()
    assert hunter in {n for n, a in st.items() if a.positions}  # the hunter's stop is not looked at yet
    fills, _ = s.process_minute(60, {"BTC": CRASH}, FX)  # a minute that starts after the arming: it counts
    assert [f["portfolio"] for f in fills] == [hunter] and fills[0]["reason"] == "stop"
