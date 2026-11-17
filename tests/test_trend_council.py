"""The council v4 « Conseil Tendance » (docs/SPEC-CONSEIL-V4.md): the engine decides, the LLMs may only brake, the code
executes. A stub `claude` (no model, no network), the real watcher, synthetic 1-minute candles."""

from __future__ import annotations

import dataclasses
import json
import threading
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from arene.perp import benchmarks as B
from arene.perp import trend_council as TC
from arene.perp.agent import INSTRUMENTS
from arene.perp.agent_round import run_intents
from arene.perp.collect import data_root
from arene.perp.council import (
    TREND_KIND,
    CouncilConfigError,
    CouncilsLeague,
    TrendSettings,
    load_council,
    load_councils_league,
)
from arene.perp.lab import backtest as bt
from arene.perp.lab import trend as trend_lab
from arene.perp.ledger import replay
from arene.perp.llm_league import load_llm_league
from arene.perp.margin import leveraged
from arene.perp.market import market_view
from arene.perp.policy import AGGRESSIVE, load_perp_policy
from arene.perp.riskd import PerpIntent
from arene.perp.types import Candle
from tests.test_perp_watcher import PRICES, SPECS, SYMBOLS, T0, World

CONFIG = Path("config/perp-conseil-tendance.toml")
COUNCIL = load_council(CONFIG)
NAME = COUNCIL.portfolio
BENCH = COUNCIL.trend.benchmark
DAY = 86_400
ROLES = {
    "le Veilleur d'actualités": "veilleur",
    "le Contrôleur de données": "controleur",
    "l'Avocat du risque": "avocat_risque",
    "le Président": "president",
}
BASE = dataclasses.replace(load_llm_league(), cadence_min=0, rounds_per_day=48, models=())
LEAGUE = dataclasses.replace(BASE, councils=CouncilsLeague(True, 4, (COUNCIL,), (), "league-sha"))
SETTINGS = COUNCIL.trend
assert SETTINGS is not None


# ---------------------------------------------------------------------- synthetic data and a stub `claude`


def seed_history(
    w: World, end: int = T0 - 7200, days: int = 16, drift: float = 0.03, drop: dict[str, set[int]] | None = None
) -> None:
    """`days` of 1-minute trade candles ending at `end` (exclusive) on the world's last prices, rising by
    `drift` a day with a little noise (a trend the engine goes long on). `drop`: minutes left out per contract."""
    start = (end // DAY - days) * DAY
    ts = np.arange(start, end, 60)
    for k, (inst, last) in enumerate(PRICES.items()):
        rng = np.random.default_rng(100 + k)
        noise = np.cumsum(rng.normal(0, 0.0004, len(ts)))
        noise -= noise[-1]  # ends on the world's price
        px = last * np.exp(-drift * (end - ts) / DAY + noise)
        cs = [
            Candle(inst, "trade", 60, int(t), int(p), int(p), int(p), int(p), 100_000_000)
            for t, p in zip(ts, px, strict=True)
            if int(t) not in (drop or {}).get(inst, set())
        ]
        w.store.candles("trade", inst, 60).add(cs)


def world(tmp_path: Path, runner=None, league=LEAGUE, **seed) -> World:
    w = World(tmp_path, trend_days=0, llm=league)
    seed_history(w, **seed)
    if runner is not None:
        w.w.trend_runner = runner
    return w


def stub_runner(proposals=None, president=None, fail=(), calls=None):
    """A `claude -p` that answers by role. `proposals`: {role: [(instrument, coefficient, reason)]};
    `president`: the structured output of the President (default: nothing to brake); `fail`: roles without a result."""
    lock = threading.Lock()

    def run(cmd, stdin, env, cwd, timeout):
        system = cmd[cmd.index("--system-prompt") + 1]
        role = next(k for name, k in ROLES.items() if f"## Ton rôle : {name}\n" in system)
        with lock:
            if calls is not None:
                calls.append(role)
        if role in fail:
            return 1, [], "boom"
        if role == "president":
            out = president if president is not None else {"coefficients": [], "validite_h": 4, "justification": "rien d'anormal"}
        else:
            props = [{"instrument": i, "coefficient": c, "raison": r} for i, c, r in (proposals or {}).get(role, [])]
            out = {"propositions": props, "resume": "rien d'anormal" if not props else "freinage proposé"}
        ev = {"type": "result", "subtype": "success", "is_error": False, "structured_output": out,
              "total_cost_usd": 0.004, "num_turns": 1, "usage": {"input_tokens": 10, "output_tokens": 5}}  # fmt: skip
        return 0, [json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}}), json.dumps(ev)], ""

    return run


def pres(*items, validite=4):
    return {"coefficients": [{"instrument": i, "coefficient": c, "raison": r} for i, c, r in items],
            "validite_h": validite, "justification": "décision du président"}  # fmt: skip


def bar0(w):
    """The first tick after the bar close at T0, outside the guard of the spot league (HH:00 to HH:05)."""
    w.advance(T0 + 420)
    return w.w.tick(T0 + 420)


def evs(w, type_):
    return [e for e in w.events(type_)]


def fills(w, name):
    return {e["payload"]["instrument"]: e["payload"]["qty"] for e in w.events("perp_fill") if e["payload"]["portfolio"] == name}


# ---------------------------------------------------------------------- the engine, live


def test_live_engine_equals_the_bench_targets_on_the_same_bars(tmp_path):
    w = world(tmp_path)
    data = bt.load(data_root(w.var))
    full = trend_lab.targets(data, TC.ENGINE_PARAMS)
    rows, _ = trend_lab.bar_weights(data, TC.ENGINE_PARAMS)
    assert data.ts[rows[-1]] == T0 - 60  # the bars close at 03:59, 07:59, ..., 23:59
    names = list(data.instruments)
    nonzero = 0
    for back in (0, 1, 5, 12):  # the last bar and earlier ones: the live path reads only what was closed then
        end = T0 - back * 14_400
        live = TC.engine_target(w.store, end + 120)
        assert (live.end_ts, live.bar_ts) == (end, end - 60)
        row = full[int(np.searchsorted(data.ts, end - 60))]
        for j, inst in enumerate(names):
            assert live.target_bp[inst] == round(float(row[j]) * 10_000), (back, inst)
            nonzero += live.target_bp[inst] != 0
    assert nonzero > 10  # the fixture does produce positions
    assert all(abs(t) <= 40_000 for t in live.target_bp.values())  # the cap 2 x the scale 2
    assert TC.params_sha256() == TC.params_sha256(trend_lab.TrendParams(scale=2.0))
    assert TC.ENGINE_PARAMS == dataclasses.replace(trend_lab.FROZEN, scale=2.0)  # the frozen engine, only scaled


def test_a_contract_with_too_many_missing_minutes_keeps_its_position(tmp_path):
    gap = {"PF_XRPUSD": {t for t in range(T0 - 7200 - 5 * 3600, T0 - 7200 - 3600 - 60, 60)}}  # 4 h = 17 % of 24 h
    w = world(tmp_path, drop=gap)
    t = TC.engine_target(w.store, T0 + 120)
    assert set(t.held) == {"PF_XRPUSD"} and t.missing_pct["PF_XRPUSD"] > 5
    ok = TC.engine_target(world(tmp_path / "b").store, T0 + 120)
    assert ok.held == {} and max(ok.missing_pct.values()) == 0
    actions = TC.plan_actions(TC.final_targets(t.target_bp, {}), {}, t.held, SETTINGS)
    assert "PF_XRPUSD" not in {a["instrument"] for a in actions}  # held: no order at all, whatever the target


def test_a_short_history_fails_closed_and_is_journaled(tmp_path):
    w = world(tmp_path, days=5)
    with pytest.raises(TC.EngineError):
        TC.engine_target(w.store, T0 + 120)
    rep = bar0(w)
    ev = w.events("trend_engine_target")
    assert {e["payload"]["portfolio"] for e in ev} == {NAME, BENCH} and all(e["payload"]["status"] == "error" for e in ev)
    assert any("trend engine" in p for p in rep.problems)
    assert not [e for e in w.events("perp_fill") if e["payload"]["portfolio"] in (NAME, BENCH)]  # no engine, no order
    assert any(e["payload"].get("code") == "perp_trend_engine_failed" for e in w.events("alert"))
    assert not w.events("agent_decision")


# ---------------------------------------------------------------------- coefficients and orders


def test_a_coefficient_can_only_lower_an_exposure_never_raise_or_invert_it():
    for target in range(-40_000, 40_001, 997):
        for halves in range(-3, 6):
            f = TC.apply_coefficient(target, halves)
            assert abs(f) <= abs(target) and f * target >= 0  # never farther from 0, never the other side
            assert (halves >= 2) == (f == target) or target == 0 or halves < 2
    assert TC.apply_coefficient(1000, 1) == 500 and TC.apply_coefficient(-1000, 0) == 0
    assert TC.apply_coefficient(1000, 2) == 1000 and TC.apply_coefficient(1000, 9) == 1000  # clamped at 1
    brakes = {"PF_XBTUSD": TC.Brake(1, 9, "x")}
    final = TC.final_targets({"PF_XBTUSD": -8000, "PF_ETHUSD": 3000}, brakes)
    assert final == {"PF_XBTUSD": -4000, "PF_ETHUSD": 3000}


def test_the_president_cannot_send_a_coefficient_above_1_nor_a_negative_one_nor_one_without_a_reason():
    for bad in (1.5, 2, -1, -0.5, 0.3, "0.5", True, None):
        d, err = TC.parse_president(pres(("PF_XBTUSD", bad, "raison")))
        assert err is None and d["halves"] == {}  # the item is dropped: the contract keeps 1
    d, _ = TC.parse_president(pres(("PF_XBTUSD", 0.5, ""), ("PF_ETHUSD", 0, "maintenance annoncée")))
    assert d["halves"] == {"PF_ETHUSD": (0, "maintenance annoncée")}
    d, _ = TC.parse_president(pres(("PF_XBTUSD", 1, "")))
    assert d["halves"] == {"PF_XBTUSD": (2, "")}
    assert TC.parse_president({"coefficients": [], "validite_h": 9, "justification": ""})[0] is None
    assert TC.parse_president("pas du JSON")[0] is None
    assert TC.parse_president({"coefficients": [], "validite_h": 4, "justification": "", "x": 1})[0] is None
    # a member can only propose a brake (0 or 0.5), never 1
    p, _ = TC.parse_proposals({"propositions": [{"instrument": "PF_XBTUSD", "coefficient": 1, "raison": "x"}], "resume": "r"})
    assert p["propositions"] == []


def test_rebalance_band_is_five_percent_of_the_equity():
    s = SETTINGS
    assert s.rebalance_band_bp == 500
    assert TC.plan_actions({"PF_XBTUSD": 10_000}, {"PF_XBTUSD": 9_500}, {}, s) == []  # exactly 5 %: no order
    a = TC.plan_actions({"PF_XBTUSD": 10_000}, {"PF_XBTUSD": 9_499}, {}, s)
    assert [(x["action"], x["size_pct"]) for x in a] == [("open_long", Decimal("5.01"))]  # the missing 501 bp
    # in: open the difference, out: reduce by the part of the position, zero: close, other side: close then open
    final = {"PF_XBTUSD": 20_000, "PF_ETHUSD": -10_000, "PF_SOLUSD": 0, "PF_XRPUSD": 4_000, "PF_LINKUSD": -6_000, "PF_LTCUSD": 0}
    cur = {"PF_XBTUSD": 8_000, "PF_ETHUSD": -20_000, "PF_SOLUSD": 700, "PF_XRPUSD": 0, "PF_LINKUSD": 7_000}
    acts = TC.plan_actions(final, cur, {}, s)
    assert [(a["instrument"], a["action"]) for a in acts] == [
        ("PF_ETHUSD", "reduce"), ("PF_SOLUSD", "close"), ("PF_LINKUSD", "close"),  # the exits first
        ("PF_XBTUSD", "open_long"), ("PF_XRPUSD", "open_long"), ("PF_LINKUSD", "open_short"),
    ]  # fmt: skip
    by = {(a["instrument"], a["action"]): a for a in acts}
    assert by["PF_ETHUSD", "reduce"]["size_pct"] == 50  # half of the position goes
    assert by["PF_XBTUSD", "open_long"]["size_pct"] == 120 and by["PF_LINKUSD", "open_short"]["size_pct"] == 60
    e = by["PF_XBTUSD", "open_long"]  # every entry carries the 5 % stop and the measured expected move
    assert e["stop_pct"] == 5 and e["expected_move_pct"] == Decimal("2.47") and e["horizon_h"] == 168
    assert all("stop_pct" not in a for a in acts if a["action"] in ("close", "reduce"))


# ---------------------------------------------------------------------- the decider: the veto council


def decider(w, kind="barre", prior=None, veto=True, runner=None, exposure=None, engine=None, now=T0 + 120):
    eng = engine or TC.engine_target(w.store, now)
    exp = exposure if exposure is not None else {}
    return TC.TrendDecider(
        COUNCIL, w.var / "claude-empty", eng, now, lambda: exp, kind=kind, prior=prior or {}, veto=veto,
        runner=runner or stub_runner(), max_budget_usd="0.40",
    ), eng  # fmt: skip


def decide(tmp_path, d):
    out = tmp_path / "rd"
    (out / "membres").mkdir(parents=True, exist_ok=True)
    (out / "round.json").write_text("{}")
    return d.decide(out, {"heure_utc": 1})


def final_of(res):
    t = res.extra["trend"]
    return t["final_bp"], t["coefficients"]


def test_the_veto_halves_or_zeroes_a_target_and_the_orders_follow(tmp_path):
    w = world(tmp_path)
    president = pres(("PF_XBTUSD", 0.5, "maintenance annoncée sur le contrat"), ("PF_ETHUSD", 0, "prix incohérents entre sources"))
    d, eng = decider(w, runner=stub_runner(president=president))
    res = decide(tmp_path, d)
    final, coeffs = final_of(res)
    assert final["PF_XBTUSD"] == TC.apply_coefficient(eng.target_bp["PF_XBTUSD"], 1) and final["PF_ETHUSD"] == 0
    assert coeffs["PF_XBTUSD"]["c"] == "0.5" and coeffs["PF_ETHUSD"]["why"] == "prix incohérents entre sources"
    assert coeffs["PF_ETHUSD"]["until_ts"] == T0 + 120 + 4 * 3600 or coeffs["PF_ETHUSD"]["until_ts"] == T0 + 14_400
    opened = {a["instrument"]: a for a in res.decision["actions"]}
    assert opened["PF_XBTUSD"]["size_pct"] * 100 == abs(final["PF_XBTUSD"])  # from flat: the final target
    assert "PF_ETHUSD" not in opened  # a zero target with no position: nothing to do
    for inst, t in eng.target_bp.items():  # no final target is farther from 0 than the engine's, none on the other side
        assert abs(final[inst]) <= abs(t) and final[inst] * t >= 0
    assert res.cost_uusd == 4 * 4000 and len(res.council) == 3  # three members and the President, 0.004 $ each


def test_any_failure_of_the_council_leaves_every_coefficient_at_1(tmp_path):
    w = world(tmp_path)
    _, eng = decider(w)
    proposals = {"veilleur": [("PF_XBTUSD", 0, "annonce")]}
    for fail in (("president",), ("president", "veilleur", "controleur", "avocat_risque")):
        d, _ = decider(w, runner=stub_runner(proposals, pres(("PF_XBTUSD", 0, "x")), fail=fail))
        res = decide(tmp_path, d)
        final, coeffs = final_of(res)
        assert coeffs == {} and final == TC.final_targets(eng.target_bp, {})  # the engine alone
        assert res.extra["trend"]["president_ok"] is False and res.extra["trend"]["president_error"]
    # an invalid President output (not the schema): same
    d, _ = decider(w, runner=stub_runner(president={"coefficients": "tous à zéro", "validite_h": 4, "justification": ""}))
    assert final_of(decide(tmp_path, d))[1] == {}
    # a member that fails is left out, the President still decides
    d, _ = decider(w, runner=stub_runner(president=pres(("PF_SOLUSD", 0.5, "annonce Kraken")), fail=("controleur",)))
    res = decide(tmp_path, d)
    assert res.extra["council"]["members_failed"] == ["controleur"] and "PF_SOLUSD" in final_of(res)[1]
    # a crash of the runner itself
    def boom(*a):
        raise OSError("no cli")
    d, _ = decider(w, runner=boom)
    assert final_of(decide(tmp_path, d))[1] == {}


def test_nothing_to_brake_means_no_llm_call(tmp_path):
    w = world(tmp_path)
    flat = TC.EngineTarget(T0 - 60, T0, dict.fromkeys(INSTRUMENTS, 0), {}, {}, {}, {})
    calls: list[str] = []
    d, _ = decider(w, engine=flat, runner=stub_runner(calls=calls))
    res = decide(tmp_path, d)
    assert calls == [] and res.cost_uusd == 0 and res.extra["trend"]["council_off"] == "nothing_to_brake"
    assert res.decision["actions"] == []
    d, _ = decider(w, veto=False, runner=stub_runner(calls=calls))
    res = decide(tmp_path, d)
    assert calls == [] and res.decision["actions"]  # veto off (budget, league): the engine alone still trades


def test_a_veto_round_only_lowers_and_a_restoration_lifts_expired_brakes(tmp_path):
    w = world(tmp_path)
    now = T0 + 3600
    prior = {"PF_XBTUSD": TC.Brake(0, now + 3600, "contrat en maintenance"), "PF_ETHUSD": TC.Brake(1, now + 3600, "annonce"),
             "PF_SOLUSD": TC.Brake(1, now - 10, "expirée")}  # fmt: skip
    # the President wants XBT back at 1, ETH at 0.5 (not lower), SOL at 0 (lower than 1: the new brake counts)
    president = pres(("PF_XBTUSD", 1, ""), ("PF_ETHUSD", 0.5, "x"), ("PF_LTCUSD", 0, "nouvel incident"))
    d, eng = decider(w, kind="veto", prior=prior, now=now, runner=stub_runner(president=president))
    res = decide(tmp_path, d)
    c = final_of(res)[1]
    assert c["PF_XBTUSD"]["c"] == "0" and c["PF_ETHUSD"]["c"] == "0.5" and c["PF_LTCUSD"]["c"] == "0"
    assert "PF_SOLUSD" not in c  # its validity ended: back to 1
    assert res.extra["trend"]["final_bp"]["PF_XBTUSD"] == 0  # a veto round can never raise what was braked
    # when the President fails in a veto round, the coefficients in force stay
    d, _ = decider(w, kind="veto", prior=prior, now=now, runner=stub_runner(fail=("president",)))
    assert set(final_of(decide(tmp_path, d))[1]) == {"PF_XBTUSD", "PF_ETHUSD"}
    # restauration: no LLM, the expired brake is lifted, the valid ones stay
    calls: list[str] = []
    d, _ = decider(w, kind="restauration", prior=prior, now=now, veto=False, runner=stub_runner(calls=calls))
    res = decide(tmp_path, d)
    assert calls == [] and set(final_of(res)[1]) == {"PF_XBTUSD", "PF_ETHUSD"}


def test_the_prompts_are_neutral_and_hashed():
    text = " ".join(TC.member_prompt(m) for m in TC.MEMBERS).lower()
    for banned in ("doubler", "doubler la mise", "objectif ×2", "aggress"):
        assert banned not in text
    assert "freiner" in text and "coefficient" in text and "ne peut ni augmenter" in text
    assert len({TC.member_sha256(m) for m in TC.MEMBERS}) == 4 and len(TC.prompts_sha256()) == 64


# ---------------------------------------------------------------------- the rounds


def test_a_bar_round_journals_the_engine_first_then_trades_the_council_and_its_shadow_alike(tmp_path):
    calls: list[str] = []
    w = world(tmp_path, runner=stub_runner(calls=calls))
    rep = bar0(w)
    assert not rep.problems, rep.problems
    assert f"trend:barre:{T0}" in rep.rounds and sorted(calls) == ["avocat_risque", "controleur", "president", "veilleur"]
    ev = w.w.journal.events()
    kinds = [e["type"] for e in ev]
    eng = [e for e in ev if e["type"] == "trend_engine_target"]
    assert {e["payload"]["portfolio"] for e in eng} == {NAME, BENCH}
    p = eng[0]["payload"]
    assert p["bar_end_ts"] == T0 and p["bar_ts"] == T0 - 60 and p["engine_version"] and len(p["params_sha256"]) == 64
    assert set(p["targets_bp"]) == set(SYMBOLS) and set(p["z"]) == set(SYMBOLS) and p["scale"] == "2.0"
    assert kinds.index("trend_engine_target") < kinds.index("council_opinion") < kinds.index("agent_decision")
    states = replay(ev)
    assert set(states[NAME].positions) == set(states[BENCH].positions) and states[NAME].positions
    assert fills(w, NAME) == fills(w, BENCH)  # all coefficients 1: the shadow trades exactly like the council
    for pf in (NAME, BENCH):
        assert all(p.stop_uusd is not None for p in states[pf].positions.values()) and states[pf].invariant_ok()
        assert all(e["payload"]["status"] == "filled" for e in w.events("perp_execution") if e["payload"]["portfolio"] == pf)
    # the council's decision carries the engine's numbers and its (empty) coefficients
    dec = [e["payload"] for e in ev if e["type"] == "agent_decision"][0]
    assert dec["portfolio"] == NAME and dec["trend"]["kind"] == "barre" and dec["trend"]["coefficients"] == {}
    assert dec["trend"]["targets_bp"] == p["targets_bp"] and dec["parsed"]["actions"]
    assert dec["council"]["president_model"] == "claude-opus-5-5" and dec["council"]["prompts_version"] == "v4"
    # the second tick of the same bar does nothing, and the 10-minute cadence plays no round for the council
    n = len(w.events())
    w.advance(T0 + 900)
    rep2 = w.w.tick(T0 + 900)
    assert not any(r.startswith("trend") for r in rep2.rounds) and len([e for e in w.events("agent_decision")]) == 1
    assert len(w.events("trend_engine_target")) == len(eng) and len(w.events()) > n


def test_the_shadow_follows_the_engine_when_the_council_brakes(tmp_path):
    president = pres(("PF_XBTUSD", 0, "contrat en maintenance annoncée par Kraken"), ("PF_SOLUSD", 0.5, "publication macro dans l'heure"))
    w = world(tmp_path, runner=stub_runner(president=president))
    bar0(w)
    c, b = fills(w, NAME), fills(w, BENCH)
    assert "PF_XBTUSD" not in c and "PF_XBTUSD" in b  # braked to zero: the council holds nothing, the shadow does
    assert abs(c["PF_SOLUSD"]) < abs(b["PF_SOLUSD"]) and c["PF_SOLUSD"] * b["PF_SOLUSD"] > 0
    assert abs(c["PF_ETHUSD"] - b["PF_ETHUSD"]) <= abs(b["PF_ETHUSD"]) // 50  # same target (the fees of XBT differ)
    dec = [e["payload"] for e in w.events("agent_decision")][0]["trend"]
    assert dec["coefficients"]["PF_XBTUSD"]["c"] == "0" and dec["president_ok"]


def test_the_council_is_not_a_generic_player_and_the_shadow_is_leveraged():
    assert [m.portfolio for m in LEAGUE.players] == [] and [c.portfolio for c in LEAGUE.trend_councils] == [NAME]
    assert leveraged(BENCH) and leveraged(NAME) and BENCH not in B.ALL


def test_the_halted_council_is_skipped_and_the_engine_failure_never_trades(tmp_path):
    w = world(tmp_path, runner=stub_runner())
    bar0(w)
    w.w.sim.append_event("portfolio_halted", {"portfolio": NAME, "reason": "drawdown", "until_ts": 0}, T0 + 130)
    seed_history(w, end=T0 + 14_400 - 60)  # the data of the next bar are there
    w.advance(T0 + 14_400 + 420)
    w.w.tick(T0 + 14_400 + 420)
    assert any(e["payload"]["portfolio"] == NAME and e["payload"]["reason"] == "halted" for e in w.events("perp_llm_skipped"))


def test_riskd_refusal_for_size_retries_smaller_in_a_bounded_loop(tmp_path):
    w = world(tmp_path)
    sim = w.w.sim
    sim.open_portfolio(NAME, "council", T0 + 100)
    tight = dataclasses.replace(COUNCIL.policy, max_trade_loss_bp=1500)  # a 4x entry with a 5 % stop loses ~24 %
    view = market_view(w.store, SYMBOLS, T0 + 120)

    def intent(k, **kw):
        base = dict(intent_id=f"i{k}", portfolio=NAME, ts=T0 + 120, instrument="PF_XBTUSD", action="open_long",
                    size_bp=40_000, stop_bp=500, horizon_h=168, expected_move_bp=247)  # fmt: skip
        return PerpIntent(**{**base, **kw})

    run_intents(sim, NAME, [intent(1)], view, SPECS, tight, T0 + 120, False, shrink=True)
    vs = [e["payload"] for e in w.events("perp_verdict")]
    assert [v["approved"] for v in vs] == [False] * (len(vs) - 1) + [True] and len(vs) > 1
    assert all(v["reasons"] == ["MAX_TRADE_LOSS"] for v in vs[:-1]) and all(v["retry_of"] == "i1" for v in vs[1:])
    sizes = [40_000] + [v["size_bp"] for v in vs[1:]]
    assert sizes == sorted(sizes, reverse=True) and sizes[-1] == 40_000 * 3**(len(vs) - 1) // 4**(len(vs) - 1)
    ex = [e["payload"] for e in w.events("perp_execution")]
    assert len(ex) == 1 and ex[0]["status"] == "filled" and ex[0]["intent_id"] == vs[-1]["intent_id"]
    pos = replay(w.w.journal.events())[NAME].positions["PF_XBTUSD"]
    assert pos.stop_uusd is not None
    # without `shrink`, the same entry is simply refused, once
    sim.open_portfolio("council-perp:b", "council", T0 + 100)
    n = len(w.events("perp_verdict"))
    run_intents(sim, "council-perp:b", [intent(2, portfolio="council-perp:b")], view, SPECS, tight, T0 + 120, False)
    assert len(w.events("perp_verdict")) == n + 1 and len(w.events("perp_execution")) == 1
    # a refusal that a smaller size cannot cure (the edge rule) is never retried
    n = len(w.events("perp_verdict"))
    run_intents(sim, NAME, [intent(3, expected_move_bp=20)], view, SPECS, COUNCIL.policy, T0 + 120, False, shrink=True)
    assert len(w.events("perp_verdict")) == n + 1 and "EDGE_TOO_SMALL" in w.events("perp_verdict")[-1]["payload"]["reasons"]
    # the loop is bounded: a refusal that every size meets stops after SHRINK_TRIES tries
    frozen = dataclasses.replace(COUNCIL.policy, max_trade_loss_bp=100)
    sim.open_portfolio("council-perp:c", "council", T0 + 100)
    n = len(w.events("perp_verdict"))
    run_intents(sim, "council-perp:c", [intent(4, portfolio="council-perp:c")], view, SPECS, frozen, T0 + 120, False, shrink=True)
    assert len(w.events("perp_verdict")) - n <= 1 + 8


def test_the_edge_rule_passes_the_engines_measured_move_and_the_aggressive_policy_is_the_v4_one(tmp_path):
    p = COUNCIL.policy
    assert p.profile == AGGRESSIVE and p.max_order_bp == 40_000 and p.max_leverage_bp == 100_000
    assert (p.max_trade_loss_bp, p.drawdown_halt_bp, p.max_opens_per_day, p.min_interval_same_open_s) == (2500, 6000, 48, 0)
    assert p.max_open_risk_bp < p.drawdown_halt_bp
    # an entry of the engine, as the code builds it, passes the edge rule at the measured move
    w = world(tmp_path)
    w.w.sim.open_portfolio(NAME, "council", T0 + 100)
    view = market_view(w.store, SYMBOLS, T0 + 120)
    act = TC.plan_actions({"PF_XBTUSD": 20_000}, {}, {}, SETTINGS)
    _, err, intents = __import__("arene.perp.agent", fromlist=["parse_decision"]).parse_decision(
        {"actions": act, "justification": "x"}, NAME, 1, T0 + 120, max_size_pct=400, max_actions=12)
    assert err is None and intents[0].expected_move_bp == 247 and intents[0].stop_bp == 500
    run_intents(w.w.sim, NAME, intents, view, SPECS, p, T0 + 120, False)
    assert w.events("perp_verdict")[-1]["payload"]["approved"] is True


# ---------------------------------------------------------------------- the cadence


def test_due_at_bar_close_only_and_ignores_the_ten_minute_cadence(tmp_path):
    cadenced = dataclasses.replace(LEAGUE, cadence_min=10)
    w = world(tmp_path, runner=stub_runner(), league=cadenced)
    assert TC.bar_close(T0 + 119) == T0 and TC.bar_close(T0 - 1) == T0 - 14_400 and TC.bar_close(T0 + 14_399) == T0
    assert not TC.bar_played(w.w.journal.events(), NAME, T0)
    bar0(w)
    assert TC.bar_played(w.w.journal.events(), NAME, T0) and not TC.bar_played(w.w.journal.events(), NAME, T0 + 14_400)
    for k in range(1, 6):  # an hour of ticks: no more round (10 minutes would have called a model again)
        w.advance(T0 + 420 + 600 * k)
        assert not any(r.startswith("trend") for r in w.w.tick(T0 + 420 + 600 * k).rounds)
    assert len(w.events("agent_decision")) == 1
    seed_history(w, end=T0 + 14_400 - 60)  # the next bar: its candles
    w.advance(T0 + 14_400 + 420)
    rep = w.w.tick(T0 + 14_400 + 420)
    assert f"trend:barre:{T0 + 14_400}" in rep.rounds and len(w.events("agent_decision")) == 2


def test_a_market_move_of_two_percent_calls_a_veto_round_that_can_only_brake(tmp_path):
    calls: list[str] = []
    w = world(tmp_path, runner=stub_runner(calls=calls))
    bar0(w)
    before = fills(w, NAME)
    calls.clear()
    w.advance(T0 + 3600)
    assert not any(r.startswith("trend") for r in w.w.tick(T0 + 3600).rounds)  # a quiet hour: no round
    t1 = T0 + 3600 + 900
    crash = {s: p * 97 // 100 for s, p in PRICES.items()}  # -3 % within the hour
    w.advance(t1, crash)
    president = pres(("PF_XBTUSD", 0.5, "mouvement de 3 % en une heure sur le contrat"))
    w.w.trend_runner = stub_runner(president=president, calls=calls)
    rep = w.w.tick(t1)
    assert any(r.startswith("trend:veto") for r in rep.rounds), rep.rounds
    assert sorted(calls) == ["avocat_risque", "controleur", "president", "veilleur"]
    dec = [e["payload"] for e in w.events("agent_decision")][-1]
    assert dec["kind"] == "veto" and dec["trend"]["coefficients"]["PF_XBTUSD"]["c"] == "0.5"
    assert dec["trend"]["targets_bp"] == [e["payload"] for e in w.events("trend_engine_target")][0]["targets_bp"]
    assert before  # the bar's targets are the same: a veto round recomputes nothing
    bench = [e for e in w.events("perp_fill") if e["payload"]["portfolio"] == BENCH]
    assert all(e["ts"] <= T0 + 500 for e in bench)  # the shadow plays the bars only


def test_the_brake_of_a_short_event_is_lifted_by_a_restoration_round_without_llm(tmp_path):
    president = pres(("PF_XBTUSD", 0, "maintenance annoncée de 14:00 à 15:00"), validite=1)
    w = world(tmp_path, runner=stub_runner(president=president))
    bar0(w)
    assert not TC.expired_brakes(w.w.journal.events(), NAME, T0 + 3000)
    assert TC.expired_brakes(w.w.journal.events(), NAME, T0 + 4200)
    calls: list[str] = []
    w.w.trend_runner = stub_runner(calls=calls)
    w.advance(T0 + 4200)
    rep = w.w.tick(T0 + 4200)
    assert f"trend:restauration:{T0}" in rep.rounds and calls == []
    dec = [e["payload"] for e in w.events("agent_decision")][-1]
    assert dec["kind"] == "restauration" and dec["trend"]["coefficients"] == {}
    assert "PF_XBTUSD" in fills(w, NAME)  # the engine reopens what the brake had closed (or never opened)
    assert not TC.expired_brakes(w.w.journal.events(), NAME, T0 + 4800)


# ---------------------------------------------------------------------- configuration


def test_the_v4_config_is_valid_strict_and_the_old_councils_still_load(tmp_path):
    assert COUNCIL.kind == TREND_KIND and COUNCIL.enabled and COUNCIL.daily_budget_uusd == 5_000_000
    assert COUNCIL.model == "claude-haiku-5-5" and COUNCIL.president_model == "claude-opus-5-5"
    assert isinstance(SETTINGS, TrendSettings) and SETTINGS.expected_move_bp == 247 and "TRAIN" in SETTINGS.expected_move_source
    league = load_councils_league()
    assert league.enabled and [c.portfolio for c in league.councils] == [NAME] and league.errors == ()
    old = load_council(Path("config/perp-conseil.toml"))
    assert old.kind == "council-v3" and old.trend is None and load_council(Path("config/perp-conseil-opus.toml")).trend is None
    raw = CONFIG.read_text()
    for old_s, new_s in (
        ('president_model = "claude-opus-5-5"', 'president_model = "claude-haiku-5-5"'),
        ("rebalance_band_bp = 500", "rebalance_band_bp = 5"),
        ('stop_pct = "5"', "stop_pct = 5"),
        ("expected_move_bp = 247", "expected_move_bp = 0"),
        ("horizon_h = 168", "horizon_h = 400"),
        ('kind = "trend-v4"', 'kind = "autre"'),
        ('benchmark = "benchmark-perp:moteur-tendance"', 'benchmark = "benchmark-perp:x"'),
        ("horizon_h = 168", "x = 1"),
    ):
        f = tmp_path / "c.toml"
        f.write_text(raw.replace(old_s, new_s, 1))
        with pytest.raises(CouncilConfigError):
            load_council(f)
    # a v3 file with the v4 keys, or a v4 file with the v3 shape, is refused
    f.write_text(Path("config/perp-conseil.toml").read_text() + '\nbenchmark = "x"\n')
    with pytest.raises(CouncilConfigError):
        load_council(f)
    pol = Path("config/policy-perp-conseil-v4.toml").read_text()
    assert load_perp_policy(Path("config/policy-perp-conseil-v4.toml"), profile=AGGRESSIVE).sha256
    assert "TRAIN" in pol and "MEASURED" in pol


# ---------------------------------------------------------------------- the site


def test_the_site_shows_the_council_its_shadow_and_each_round_line(tmp_path):
    import re

    from arene.risk.policy import load_policy
    from arene.site import build
    from tests.test_site import ROOT, synthetic_journal
    from tests.test_site import _cfg as _config

    president = pres(("PF_XBTUSD", 0.5, "annonce de maintenance sur le contrat"))
    w = world(tmp_path, runner=stub_runner(president=president))
    bar0(w)
    w.advance(T0 + 1200)
    w.w.tick(T0 + 1200)
    spot = synthetic_journal(tmp_path / "var" / "journal" / "events.jsonl")
    out = tmp_path / "site"
    build(spot.path, out, config=_config(), policy=load_policy(ROOT / "config" / "policy.toml"),
          now_ts=T0 + 1500, public=True, racine="/arene/", perp_journal=w.var / "journal" / "events.jsonl")  # fmt: skip

    def clean(h: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).replace(" ", " ").replace("\xa0", " ")

    html = (out / "conseils.html").read_text(encoding="utf-8")
    assert "Conseil Tendance" in clean(html) and "Témoin moteur seul" in clean(html) and "council-perp-tendance.html" in html
    page = (out / "conseils" / "council-perp-tendance.html").read_text(encoding="utf-8")
    ptxt = clean(page)
    assert "objectif : 1 %/jour · réalisé :" in ptxt
    assert "Cibles du moteur" in ptxt and "Coefficients du conseil" in ptxt and "Ordres" in ptxt
    assert "BTC ×0,5" in ptxt and "annonce de maintenance sur le contrat" in ptxt and "Le Veilleur d’actualités" in ptxt
    assert "clôture de barre 4 h" in ptxt
    assert (out / "conseils" / "benchmark-perp-moteur-tendance.html").exists()
    derives = (out / "derives.html").read_text(encoding="utf-8")
    assert "moteur-tendance" not in derives and "Témoin moteur seul" not in derives  # a benchmark of the councils' league only
