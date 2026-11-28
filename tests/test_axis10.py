"""Axis 10 (docs/lead/LOG.md): the Trend Council at 1x, the Wick Hunter retired, the carry benchmark."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from arena.perp import benchmarks as B
from arena.perp.council import CouncilConfigError, load_council, load_councils_league
from arena.perp.hunter import load_hunter_config
from arena.perp.ledger import PerpLedgerError, replay, total_equity_ueur
from arena.perp.margin import HUNTER_NAMES, leveraged
from arena.perp.retired import RETIRABLE_NAMES, RetiredError, retired_portfolio
from arena.perp.trend_council import ENGINE_PARAMS, engine_params
from tests.test_perp_watcher import PRICES, SPECS, T0, World

CFG_1X = Path("config/perp-council-trend-1x.toml")
FX = (1_100_000, 1_100_100)
BTC, ETH = "PF_XBTUSD", "PF_ETHUSD"


# ---------------------------------------------------------------------- the Trend Council at 1x


def test_the_league_lists_the_1x_council_alone_and_it_is_scaled_1x():
    league = load_councils_league()
    assert [c.portfolio for c in league.councils] == ["council-perp:trend-1x"] and league.errors == ()
    c = league.councils[0]
    assert c.trend.benchmark == "benchmark-perp:trend-engine-1x" and c.trend.engine_scale == "1.0"
    assert engine_params(c).scale == 1.0 and engine_params(c) == dataclasses.replace(ENGINE_PARAMS, scale=1.0)
    assert leveraged(c.portfolio) and leveraged(c.trend.benchmark)
    assert c.trend.expected_move_bp == 247 and "inherited" in c.trend.expected_move_source


def test_the_1x_council_keeps_the_rules_of_the_2x_one_except_the_scale_and_the_names():
    old, new = load_council(Path("config/perp-council-trend.toml")), load_council(CFG_1X)
    assert old.trend.engine_scale == "2.0" and old.portfolio == "council-perp:trend"  # the absent key means 2x
    keep = ("model", "president_model", "daily_budget_uusd", "members_parallel", "member_max_tool_calls")
    assert all(getattr(old, k) == getattr(new, k) for k in keep)
    a, b = old.trend, new.trend
    assert (a.rebalance_band_bp, a.stop_pct, a.horizon_h) == (b.rebalance_band_bp, b.stop_pct, b.horizon_h)
    assert old.policy.max_order_bp == new.policy.max_order_bp and old.policy.drawdown_halt_bp == new.policy.drawdown_halt_bp
    assert old.policy.max_open_risk_bp == new.policy.max_open_risk_bp


def test_engine_scale_is_validated(tmp_path):
    raw = CFG_1X.read_text()
    (tmp_path / "policy-perp-council-trend-1x.toml").write_text(Path("config/policy-perp-council-trend-1x.toml").read_text())
    f = tmp_path / "c.toml"
    for bad in ('engine_scale = "3.0"', "engine_scale = 1.0", 'engine_scale = "1"'):
        f.write_text(raw.replace('engine_scale = "1.0"', bad, 1))
        with pytest.raises(CouncilConfigError, match="engine_scale"):
            load_council(f)
    f.write_text(raw.replace('benchmark = "benchmark-perp:trend-engine-1x"', 'benchmark = "benchmark-perp:x"', 1))
    with pytest.raises(CouncilConfigError, match="benchmark"):
        load_council(f)


def test_the_retired_trend_portfolios_are_retirable_and_the_other_benchmarks_are_not(tmp_path):
    assert {"benchmark-perp:trend-engine", "robot-perp:hunter", "benchmark-perp:hunter-5min"} <= RETIRABLE_NAMES
    for name in (B.BASKET, B.TREND, B.RANDOM, B.CARRY):
        with pytest.raises(RetiredError, match="can be retired"):
            retired_portfolio(tmp_path, name, T0)


# ---------------------------------------------------------------------- the Wick Hunter retired


def test_the_hunter_is_disabled_in_its_config_and_its_process_exits_cleanly(capsys):
    cfg = load_hunter_config()
    assert cfg.enabled is False and cfg.portfolio == "robot-perp:hunter" and {cfg.portfolio, cfg.benchmark} == HUNTER_NAMES
    from arena.perp import hunter as H

    assert H.main(["run", "--var", "/nonexistent-var-for-the-test"]) == 0  # no lock, no network, nothing started
    assert "disabled" in capsys.readouterr().err


def test_a_disabled_hunter_is_not_opened_by_the_watcher(tmp_path):
    from arena.perp.config import load_perp_config
    from arena.perp.policy import load_perp_policy
    from arena.perp.watcher import PerpWatcher

    w = World(tmp_path)
    w.w = PerpWatcher(w.var, load_perp_config(), load_perp_policy(), SPECS, spot_paths=w.spot, hunter=load_hunter_config())
    assert w.w.hunter is None
    w.w.tick(T0 + 120)
    assert not (set(replay(w.events())) & HUNTER_NAMES)


# ---------------------------------------------------------------------- the carry: the plan


def _acc(tmp_path):
    w = World(tmp_path)
    w.w.sim.open_portfolio(B.CARRY, "benchmark", T0)
    return w, w.w.sim.states()[B.CARRY]


def test_the_plan_opens_both_pairs_at_250_eur_a_leg_spot_before_the_short(tmp_path):
    _w, acc = _acc(tmp_path)
    marks = {i: PRICES[i] for i in B.CARRY_INSTRUMENTS}
    steps = B.carry_plan(acc, acc.capital_ueur, marks, marks, FX[0], SPECS)
    assert [(s.leg, s.instrument) for s in steps] == [("spot", BTC), ("perp", BTC), ("spot", ETH), ("perp", ETH)]
    assert all(s.why == "entry" for s in steps)
    for inst in B.CARRY_INSTRUMENTS:
        spot = next(s for s in steps if s.leg == "spot" and s.instrument == inst).qty
        perp = next(s for s in steps if s.leg == "perp" and s.instrument == inst).qty
        assert spot > 0 and perp == -spot  # equal quantity: delta neutral
        usd = spot * marks[inst] // 100_000_000
        assert abs(usd - 250 * FX[0]) < 250 * FX[0] // 100 + marks[inst] * SPECS[inst].lot_step_qty // 100_000_000  # EUR 250 at the bid


def test_the_plan_leaves_a_leg_inside_the_band_alone_and_resizes_both_legs_outside_it(tmp_path):
    _w, acc = _acc(tmp_path)
    px = {i: PRICES[i] for i in B.CARRY_INSTRUMENTS}
    entry = {s.leg + s.instrument: s.qty for s in B.carry_plan(acc, acc.capital_ueur, px, px, FX[0], SPECS)}
    acc.spot_qty = {i: entry["spot" + i] for i in B.CARRY_INSTRUMENTS}
    from arena.perp.ledger import PerpPosition

    acc.positions = {i: PerpPosition(i, entry["perp" + i], px[i], T0, 1) for i in B.CARRY_INSTRUMENTS}

    def plan(factor_bp: int):
        moved = {i: p * factor_bp // 10_000 for i, p in px.items()}
        return B.carry_plan(acc, acc.capital_ueur, moved, moved, FX[0], SPECS)

    assert plan(10_000) == [] and plan(12_000) == [] and plan(8_500) == []  # inside 0.8 to 1.25
    up = plan(13_000)  # +30 %: both legs of both coins are worth 1.3 x target: sell the excess
    assert [s.why for s in up] == ["rebalance"] * 4
    assert [(s.leg, s.qty < 0) for s in up if s.instrument == BTC] == [("spot", True), ("perp", False)]  # reductions
    down = plan(7_500)  # -25 %: both legs below 0.8: add to both, spot first, then the short
    assert [(s.leg, s.qty > 0) for s in down if s.instrument == BTC] == [("spot", True), ("perp", False)]
    assert all(s.qty > 0 for s in down if s.leg == "spot") and all(s.qty < 0 for s in down if s.leg == "perp")
    acc.spot_qty[BTC] = 0  # a half-built pair is itself outside the band
    assert any(s.instrument == BTC and s.leg == "spot" for s in plan(10_000))


def test_the_plan_skips_a_coin_without_a_price(tmp_path):
    _w, acc = _acc(tmp_path)
    px = {i: PRICES[i] for i in B.CARRY_INSTRUMENTS}
    steps = B.carry_plan(acc, acc.capital_ueur, px, {BTC: None, ETH: px[ETH]}, FX[0], SPECS)
    assert {s.instrument for s in steps} == {ETH}


# ---------------------------------------------------------------------- the carry: the ledger


def test_a_spot_fill_moves_cash_charges_the_fee_and_keeps_the_invariant(tmp_path):
    w, acc0 = _acc(tmp_path)
    sim, px = w.w.sim, PRICES[BTC]
    qty = 1_000_000  # 0.01 BTC
    fill = sim.spot_order("s1", B.CARRY, BTC, qty, px, FX, T0 + 10, fee_bp=40, slippage_bp=5)
    assert fill["price_uusd"] == px * 10_005 // 10_000  # a buy pays the slippage above the index
    acc = sim.states()[B.CARRY]
    notional_eur = fill["price_uusd"] * qty // 100_000_000 * 1_000_000 // FX[0]
    assert acc.spot_qty == {BTC: qty} and acc.invariant_ok()
    assert abs(acc.spot_invested_ueur - notional_eur) <= 2
    assert acc.fees_paid_ueur == fill["fee_ueur"] and abs(fill["fee_ueur"] - notional_eur * 40 // 10_000) <= 2  # 0.40 %
    assert acc.collateral_ueur == acc0.capital_ueur - acc.spot_invested_ueur - fill["fee_ueur"]
    # valued at the index and counted in the published equity
    marks = {BTC: px}
    up = total_equity_ueur(acc, {}, {BTC: px * 110 // 100}, *FX)
    assert up - total_equity_ueur(acc, {}, marks, *FX) > 0  # a rising index raises the equity through the spot leg
    # replay of the journal gives the same account, and the same order id is idempotent
    assert replay(w.events())[B.CARRY].spot_qty == {BTC: qty}
    assert sim.spot_order("s1", B.CARRY, BTC, qty, px, FX, T0 + 11, fee_bp=40, slippage_bp=5) is None
    sale = sim.spot_order("s2", B.CARRY, BTC, -qty, px, FX, T0 + 20, fee_bp=40, slippage_bp=5)
    assert sale["price_uusd"] == px * 9_995 // 10_000  # a sale receives the slippage below
    flat = sim.states()[B.CARRY]
    assert flat.spot_qty == {} and flat.invariant_ok()
    assert flat.collateral_ueur < acc0.capital_ueur  # the round trip cost 2 x (0.40 % + 5 bp) of the leg


def test_a_spot_fill_the_ledger_refuses(tmp_path):
    w, _ = _acc(tmp_path)
    sim, px = w.w.sim, PRICES[BTC]
    with pytest.raises(PerpLedgerError, match="exceeds"):
        sim.spot_order("x1", B.CARRY, BTC, -1, px, FX, T0 + 5, fee_bp=40, slippage_bp=5)
    with pytest.raises(PerpLedgerError, match="cannot pay"):
        sim.spot_order("x2", B.CARRY, BTC, 10_000_000_000, px, FX, T0 + 6, fee_bp=40, slippage_bp=5)
    with pytest.raises(PerpLedgerError, match="no valid index"):
        sim.spot_order("x3", B.CARRY, BTC, 1_000_000, 0, FX, T0 + 7, fee_bp=40, slippage_bp=5)
    sim.spot_order("x4", B.CARRY, BTC, 1_000_000, px, FX, T0 + 8, fee_bp=40, slippage_bp=5)
    # a portfolio holding a spot leg cannot be retired
    with pytest.raises(PerpLedgerError, match="open positions"):
        sim.append_event("portfolio_retired", {"portfolio": B.CARRY, "ts": T0 + 9, "reason": "x", "note": ""}, T0 + 9)
    with pytest.raises(PerpLedgerError, match="no valid mark"):
        sim.write_equity(B.CARRY, T0 + 30, {}, FX)  # the equity of a spot leg needs its price


# ---------------------------------------------------------------------- the carry: the watcher


def _carry_events(w):
    return [e for e in w.events() if e["payload"].get("portfolio") == B.CARRY]


def test_the_first_round_opens_the_two_pairs_and_the_equity_counts_the_spot_legs(tmp_path):
    w = World(tmp_path)
    rep = w.w.tick(T0 + 120)
    assert not [p for p in rep.problems if "carry" in p], rep.problems
    acc = replay(w.events())[B.CARRY]
    assert set(acc.spot_qty) == set(B.CARRY_INSTRUMENTS) and set(acc.positions) == set(B.CARRY_INSTRUMENTS)
    for inst in B.CARRY_INSTRUMENTS:
        assert acc.positions[inst].qty == -acc.spot_qty[inst]  # short perp = long spot, same quantity
        assert acc.positions[inst].stop_uusd is None  # a reference: no stop
    assert acc.invariant_ok()
    spot_fills = [e["payload"] for e in w.events("spot_fill")]
    [plan] = [e["payload"] for e in w.events("carry_plan")]  # the reason of the orders is journaled first
    assert plan["why"] == ["entry"] and plan["spot_price"] == "kraken_index" and len(plan["steps"]) == 4
    assert len(spot_fills) == 2 and all(f["fee_ueur"] > 0 and f["reason"] == "intent" for f in spot_fills)
    n = len(w.events())
    w.w.tick(T0 + 300)  # the next tick: its equity measure counts the legs, and nothing more is traded
    eq = [e["payload"] for e in w.events("perp_equity") if e["payload"]["portfolio"] == B.CARRY][-1]
    assert eq["spot_ueur"] > 0 and set(eq["spot_marks"]) == set(B.CARRY_INSTRUMENTS)
    # EUR 1,000 less the costs of entry (spot 0.45 % + perp 0.12 % on EUR 500 each side, and the spreads), no price bet
    assert 985_000_000 < eq["equity_ueur"] < 1_000_000_000
    assert len(w.events("spot_fill")) == 2 and len([e for e in w.events("perp_fill") if e["payload"]["portfolio"] == B.CARRY]) == 2
    assert len(w.events()) > n


def test_the_short_receives_the_funding_and_a_price_rise_does_not_change_the_equity(tmp_path):
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    first = [e["payload"] for e in w.events("perp_equity") if e["payload"]["portfolio"] == B.CARRY][-1]["equity_ueur"]
    rise = {i: p * 110 // 100 for i, p in PRICES.items()}  # +10 %: inside the band, no rebalance
    w.funding(T0 + 3600, nusd=700_000)
    w.advance(T0 + 3900, rise)
    w.w.tick(T0 + 3900)
    funding = [e["payload"] for e in w.events("funding") if e["payload"]["portfolio"] == B.CARRY]
    assert funding and all(f["amount_ueur"] < 0 for f in funding)  # a short is paid by the longs: received
    last = [e["payload"] for e in w.events("perp_equity") if e["payload"]["portfolio"] == B.CARRY][-1]["equity_ueur"]
    assert abs(last - first) < 5_000_000  # a delta-neutral pair: a +10 % move costs a few euros of spread at most
    assert len(w.events("spot_fill")) == 2  # no rebalance


def test_a_move_outside_the_band_rebalances_both_legs_with_costs(tmp_path):
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    fees0 = replay(w.events())[B.CARRY].fees_paid_ueur
    rise = {i: p * 130 // 100 for i, p in PRICES.items()}  # +30 %: out of the 0.8 to 1.25 band
    w.funding(T0 + 3600)
    w.funding(T0 + 7200)
    w.funding(T0 + 10_800)
    w.funding(T0 + 14_400)
    w.advance(T0 + 14_520, rise)
    rep = w.w.tick(T0 + 14_520)  # the next scheduled round (the band is checked at each one, every 4 hours)
    assert rep.rounds and rep.rounds[0].startswith("rendezvous"), rep.rounds
    assert not [p for p in rep.problems if "carry" in p], rep.problems
    spot = [e["payload"] for e in w.events("spot_fill")]
    assert w.events("carry_plan")[-1]["payload"]["why"] == ["rebalance"]
    assert len(spot) == 4 and [f["qty"] < 0 for f in spot[2:]] == [True, True]  # sold back to target
    acc = replay(w.events())[B.CARRY]
    assert acc.fees_paid_ueur > fees0 and acc.invariant_ok()
    for inst in B.CARRY_INSTRUMENTS:
        assert acc.positions[inst].qty == -acc.spot_qty[inst]
    # and the pair is back near EUR 250 a leg: value of the spot leg in EUR
    from arena.perp.ledger import spot_value_ueur

    value = spot_value_ueur(acc, {i: rise[i] for i in B.CARRY_INSTRUMENTS}, *FX)
    assert abs(value - 500_000_000) < 20_000_000


def test_the_carry_is_a_reference_never_stopped_nor_cut_at_the_maximum_holding(tmp_path):
    assert B.CARRY in B.REFERENCES and B.CARRY in B.ALL and not leveraged(B.CARRY)
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    w.w.sim.params = dataclasses.replace(w.w.sim.params, max_holding_s=60)  # any other portfolio would be cut at once
    w.w.tick(T0 + 600)
    acc = replay(w.events())[B.CARRY]
    assert len(acc.positions) == 2 and not acc.halted and not [e for e in w.events("perp_fill") if e["payload"]["reason"] == "max_holding"]


# ---------------------------------------------------------------------- the retirements


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("council-perp:trend", "council"),
        ("benchmark-perp:trend-engine", "benchmark"),
        ("robot-perp:hunter", "robot"),
        ("benchmark-perp:hunter-5min", "benchmark"),
    ],
)
def test_the_retired_portfolios_are_flattened_journaled_with_their_reason_and_never_trade_again(
    tmp_path, monkeypatch, name, kind
):
    import arena.perp.watcher as W

    monkeypatch.setattr(W, "load_specs", lambda var, symbols, now_ts, client=None: SPECS)
    w = World(tmp_path)
    sim, px = w.w.sim, w.prices[BTC]
    sim.open_portfolio(name, kind, T0)
    sim.market_order("o1", name, BTC, 2_000_000, (px, px + 1_000_000), FX, T0 + 30)
    sim.set_conditional(name, BTC, "stop", px * 95 // 100, T0 + 31)
    reason = "axis 10: the frozen rule fails on 2020-2025"
    out = retired_portfolio(w.var, name, T0 + 120, reason=reason, note="owner approved")
    assert out["status"] == "retired" and out["fills"] == 1
    [ev] = [e["payload"] for e in w.events("portfolio_retired") if e["payload"]["portfolio"] == name]
    assert ev["reason"] == reason and ev["note"] == "owner approved"
    acc = replay(w.events())[name]
    assert acc.retired and not acc.positions and acc.invariant_ok()
    with pytest.raises(PerpLedgerError, match="retired"):
        sim.market_order("o2", name, BTC, 1_000_000, (px, px + 1_000_000), FX, T0 + 200)
    n = len(w.events())
    assert retired_portfolio(w.var, name, T0 + 300)["status"] == "already_retired" and len(w.events()) == n


def test_the_site_draws_the_retired_trend_and_hunter_dotted_and_the_new_ones_live(tmp_path):
    from arena.site import perp as P

    assert P.NAMES[P.COUNCIL_TREND_1X] == "Trend Council 1x" and P.NAMES[P.COUNCIL_TREND] == "Trend Council 2x"
    assert P.TREND_ENGINES == (P.TREND_ENGINE, P.TREND_ENGINE_1X) and P.TREND_COUNCILS == (P.COUNCIL_TREND, P.COUNCIL_TREND_1X)
    assert "cash substitute" in P.CARRY_BADGE and "no bet on price" in P.CARRY_BADGE
    assert "valuation" in P.CARRY_NOTE and P.DESCRIPTIONS[P.CARRY] and P.DESCRIPTIONS[P.COUNCIL_TREND_1X]
    assert "Archived" in P.DESCRIPTIONS[P.COUNCIL_TREND] and "Archived" in P.DESCRIPTIONS[P.TREND_ENGINE]


def test_the_site_shows_the_carry_as_a_labelled_benchmark_and_the_1x_trend_next_to_the_archived_2x(tmp_path):
    import json
    import re
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    import perp_fixture as F
    import test_site_perp as S
    from test_site import synthetic_journal

    from arena.journal import Journal
    from arena.site import build

    spot = synthetic_journal(tmp_path / "var" / "journal" / "events.jsonl")
    perp = F.build(tmp_path / "var-perp" / "journal" / "events.jsonl")
    j, ts = Journal(perp), S.NOW - 600
    fx = {"fx_bid": 1_100_000, "fx_ask": 1_100_100}
    for name, kind in (("benchmark-perp:carry", "benchmark"), ("council-perp:trend-1x", "council"), ("benchmark-perp:trend-engine-1x", "benchmark")):
        j.append("portfolio_opened", {"portfolio": name, "kind": kind, "league": "perp", "capital_ueur": 1_000_000_000, "venue_mode": "paper"}, ts)
    spot_fill = {"order_id": "c1", "portfolio": "benchmark-perp:carry", "instrument": "PF_XBTUSD", "qty": 300_000, "price_uusd": 88_000_000_000,
                 "fee_ueur": 960_000, "reason": "intent", "index_uusd": 87_950_000_000, "ts": ts + 1, **fx}  # fmt: skip
    j.append("spot_fill", spot_fill, ts + 1)
    j.append("perp_equity", {"portfolio": "benchmark-perp:carry", "ts": ts + 2, "collateral_ueur": 735_000_000, "unrealized_ueur": 0,
                             "equity_ueur": 999_000_000, "gross_ueur": 0, "marks": {}, "spot_ueur": 264_000_000,
                             "spot_marks": {"PF_XBTUSD": 88_000_000_000}, "spot_qty": {"PF_XBTUSD": 300_000}, **fx}, ts + 2)  # fmt: skip
    j.append("portfolio_retired", {"portfolio": F.LLMS[0], "ts": ts + 3, "reason": "axis 10: frozen rule fails on 2020-2025", "note": "private"}, ts + 3)
    out = tmp_path / "site"
    config, policy = S._cfg()
    build(spot.path, out, config=config, policy=policy, now_ts=S.NOW, public=True, root_path="/arena/", perp_journal=perp)
    page = (out / "derivatives" / "benchmark-perp-carry.html").read_text(encoding="utf-8")
    flat = S.text(page)
    assert "a cash substitute: earns the funding paid by leveraged longs, no bet on price" in flat
    assert "valuation only" in flat and "Spot legs" in flat and "BTC spot" in flat and "A benchmark, not a player" in flat
    d = json.loads((out / "data" / "derivatives.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in d["portfolios"]}
    assert by_id["benchmark-perp:carry"]["kind"] == "benchmark" and by_id["benchmark-perp:carry"]["archive"] is None
    assert by_id["benchmark-perp:carry"]["spot_legs"][0]["instrument"] == "BTC"
    assert by_id[F.LLMS[0]]["archive"] == {"ts": ts + 3, "reason": "axis 10: frozen rule fails on 2020-2025"}  # the note stays private
    assert "private" not in json.dumps(d)
    c = json.loads((out / "data" / "councils.json").read_text(encoding="utf-8"))
    ids = {p["id"]: p for p in c["portfolios"]}
    assert ids["council-perp:trend-1x"]["name"] == "Trend Council 1x" and ids["benchmark-perp:trend-engine-1x"]["name"] == "Benchmark engine only 1x"
    assert (out / "councils" / "council-perp-trend-1x.html").exists() and (out / "councils" / "benchmark-perp-trend-engine-1x.html").exists()
    home = (out / "councils.html").read_text(encoding="utf-8")
    assert re.search(r"Trend Council 1x", home)
