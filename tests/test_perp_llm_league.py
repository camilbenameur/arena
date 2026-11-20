"""Perp league, step 7: the LLM portfolios inside the watcher (fake `claude`, real MCP server)."""

from __future__ import annotations

import dataclasses
import threading
from pathlib import Path

import pytest

from arena.perp.agent import AgentDecider
from arena.perp.ledger import replay
from arena.perp.llm_league import LlmConfigError, load_llm_league
from tests.test_perp_agent import fake_runner
from tests.test_perp_watcher import PRICES, T0, World

CONFIG = load_llm_league()
# the tests of the alerts, the asked wake-ups and the quota run without the default cadence, at 48 rounds a day;
# the cadence has its own tests (CADENCED)
LEAGUE = dataclasses.replace(CONFIG, cadence_min=0, rounds_per_day=48)
CADENCED = dataclasses.replace(CONFIG, cadence_min=15, rounds_per_day=48)
NAMES = [m.portfolio for m in LEAGUE.models]


def factory(tmp: Path, calls: list, mode: str = "normal", extra: dict | None = None):
    lock = threading.Lock()
    run = fake_runner(mode, extra)

    def counted(cmd, stdin, env, cwd, timeout):
        with lock:
            calls.append(cmd[cmd.index("--model") + 1])
        return run(cmd, stdin, env, cwd, timeout)

    return lambda m: AgentDecider(
        m.model, m.portfolio, tmp / "claude-empty", runner=counted, effort=LEAGUE.effort
    )


def test_the_config_file_is_valid_and_strict(tmp_path):
    assert [m.model for m in CONFIG.models] == [
        "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2",
    ]  # fmt: skip
    assert CONFIG.enabled and CONFIG.wakeups and CONFIG.max_parallel == 4
    assert [m.daily_budget_uusd for m in CONFIG.models] == [500_000, 5_000_000, 14_000_000, 30_000_000]
    assert CONFIG.rounds_per_day == 260 and CONFIG.cadence_min == 10
    bad = tmp_path / "bad.toml"
    raw = Path("config/perp-llm.toml").read_text()
    for old, new in (
        ('"0.50"', "0.50"),
        ("rounds_per_day = 260", "rounds_per_day = 5"),
        ("cadence_min = 10", "cadence_min = 4"),
        ("cadence_min = 10", "cadence_min = 61"),
        ("cadence_min = 10", "cadence_min = true"),
        ("cadence_min = 10", "x = 15"),
        ("max_parallel = 4", "max_parallel = 9"),
        ("wakeups = true", "x = 1"),
    ):
        bad.write_text(raw.replace(old, new, 1))
        with pytest.raises((LlmConfigError, ValueError)):
            load_llm_league(bad)


def test_the_four_models_play_the_rendezvous_together(tmp_path):
    calls: list[str] = []
    w = World(tmp_path, llm=LEAGUE, factory=factory(tmp_path, calls))
    rep = w.w.tick(T0 + 120)
    assert not rep.problems, rep.problems
    ev = w.events()
    opened = {e["payload"]["portfolio"]: e["ts"] for e in ev if e["type"] == "portfolio_opened"}
    assert {opened[n] for n in NAMES} == {T0 + 120}  # same start (D8)
    assert sorted(calls) == sorted(m.model for m in LEAGUE.models)
    decisions = {e["payload"]["portfolio"] for e in ev if e["type"] == "agent_decision"}
    assert decisions == set(NAMES)
    rd = [e["payload"] for e in ev if e["type"] == "round_data"]
    assert {r["llm_config_sha256"] for r in rd} == {LEAGUE.sha256} and {r["round"] for r in rd} == {T0}
    assert any(e["type"] == "perp_round_done" and e["payload"]["round"] == T0 for e in ev)
    books = replay(ev)
    assert all(books[n].positions["PF_XBTUSD"].stop_uusd for n in NAMES)  # the fake opens a stopped long
    # the next tick does not call anyone again
    w.advance(T0 + 420)
    w.w.tick(T0 + 420)
    assert len(calls) == 4


def test_wakeups_are_rendezvous_only_until_enabled(tmp_path):
    calls: list[str] = []
    off = dataclasses.replace(LEAGUE, wakeups=False)
    w = World(tmp_path, llm=off, factory=factory(tmp_path, calls))
    w.w.tick(T0 + 120)
    n = len(calls)
    verdicts = [
        e for e in w.events() if e["type"] == "perp_verdict" and "random" in e["payload"]["portfolio"]
    ]
    play(w, T0 + 3 * 3600, "wakeup", {"instrument": "PF_XBTUSD"}, T0 + 3 * 3600 + 30)
    assert len(calls) == n
    # the random benchmark does not play a wake-up the models do not play
    after = [e for e in w.events() if e["type"] == "perp_verdict" and "random" in e["payload"]["portfolio"]]
    assert len(after) == len(verdicts)
    w.w.llm = dataclasses.replace(LEAGUE, wakeups=True)
    play(w, T0 + 3 * 3600 + 300, "wakeup", {"instrument": "PF_XBTUSD"}, T0 + 3 * 3600 + 330)
    assert len(calls) == n + 4


def play(w: World, round_id: int, kind: str, trigger, now: int) -> None:
    view, rep = _view(w, T0 + 120)
    w.w._deferred = None
    w.w._round(round_id, kind, trigger, now, view, rep)
    if w.w._deferred is not None:
        w.w._llm_phase(**w.w._deferred, rep=rep)


def _view(w: World, ts: int):
    from arena.perp.market import market_view
    from arena.perp.watcher import TickReport

    return market_view(w.store, w.w.symbols, ts), TickReport(ts)


def test_budget_and_halt_skip_the_call(tmp_path):
    calls: list[str] = []
    small = dataclasses.replace(
        LEAGUE, models=tuple(dataclasses.replace(m, daily_budget_uusd=1) for m in LEAGUE.models)
    )
    w = World(tmp_path, llm=small, factory=factory(tmp_path, calls))
    w.w.tick(T0 + 120)  # the first round is paid (nothing spent yet today)
    assert len(calls) == 4
    play(w, T0 + 4 * 3600, "rendezvous", None, T0 + 4 * 3600 + 60)
    skipped = [e["payload"] for e in w.events() if e["type"] == "perp_llm_skipped"]
    assert len(calls) == 4 and {s["reason"] for s in skipped} == {"daily_budget"} and len(skipped) == 4


def test_a_failing_finish_still_journals_every_cost(tmp_path, monkeypatch):
    calls: list[str] = []
    w = World(tmp_path, llm=LEAGUE, factory=factory(tmp_path, calls))
    import arena.perp.llm_league as L

    real = L.finish_agent_round
    state = {"n": 0}

    def crash_once(ctx, res, extra=None, **kw):
        state["n"] += 1
        if state["n"] == 2:
            raise OSError("disk")
        return real(ctx, res, extra, **kw)

    monkeypatch.setattr(L, "finish_agent_round", crash_once)
    w.w.tick(T0 + 120)
    ev = w.events()
    decisions = [e["payload"] for e in ev if e["type"] == "agent_decision"]
    assert len(calls) == 4 and len(decisions) == 4 and all(d["cost_uusd"] > 0 for d in decisions)
    assert sum(1 for d in decisions if str(d["parse_error"]).startswith("finish failed")) == 1
    assert any(e["type"] == "perp_round_done" for e in ev)


def test_a_failing_prepare_skips_that_model_only(tmp_path, monkeypatch):
    calls: list[str] = []
    w = World(tmp_path, llm=LEAGUE, factory=factory(tmp_path, calls))
    import arena.perp.llm_league as L

    real = L.prepare_agent_round

    def broken(**kw):
        if "opus" in kw["decider"].portfolio:
            raise OSError("store")
        return real(**kw)

    monkeypatch.setattr(L, "prepare_agent_round", broken)
    w.w.tick(T0 + 120)
    ev = w.events()
    skipped = [e["payload"] for e in ev if e["type"] == "perp_llm_skipped"]
    assert len(calls) == 3 and len(skipped) == 1 and skipped[0]["reason"].startswith("prepare_error")


def test_a_cut_between_prepare_and_call_never_calls(tmp_path, monkeypatch):
    calls: list[str] = []
    w = World(tmp_path, llm=LEAGUE, factory=factory(tmp_path, calls))
    import arena.perp.llm_league as L

    class Cut:
        def __init__(self, *a, **k):
            raise RuntimeError("power cut")

    monkeypatch.setattr(L, "ThreadPoolExecutor", Cut)
    rep = w.w.tick(T0 + 120)
    assert any("llm round" in p for p in rep.problems) and calls == []
    monkeypatch.undo()
    w.advance(T0 + 420)
    w.w.tick(T0 + 420)  # resumes the round: nobody is called, everyone is journaled as interrupted
    ev = w.events()
    reasons = {e["payload"]["reason"] for e in ev if e["type"] == "perp_llm_skipped"}
    assert calls == [] and reasons == {"interrupted_before_call"}
    assert any(e["type"] == "perp_round_done" and e["payload"]["round"] == T0 for e in ev)


def test_timeouts_count_against_the_budget():
    from arena.perp.agent import TIMEOUT_RC, AgentResult
    from arena.perp.llm_league import call_cost_uusd, charge_ceiling

    assert call_cost_uusd({"cost_uusd": 0, "charge_ceiling": True, "budget_ceiling_uusd": 100_000}) == 100_000
    assert call_cost_uusd({"cost_uusd": 5, "charge_ceiling": False, "budget_ceiling_uusd": 100_000}) == 5
    assert charge_ceiling(AgentResult(rc=TIMEOUT_RC))
    assert charge_ceiling(AgentResult(rc=1, assistant_seen=True))
    assert not charge_ceiling(AgentResult(rc=1))  # never reached a model: network, login
    assert not charge_ceiling(AgentResult(rc=0, result_seen=True))


def test_a_network_failure_costs_no_budget(tmp_path):
    from arena.perp.llm_league import spent_today_uusd

    def down(cmd, stdin, env, cwd, timeout):
        return 1, [], "network down"

    w = World(
        tmp_path,
        llm=LEAGUE,
        factory=lambda m: AgentDecider(m.model, m.portfolio, tmp_path / "e", runner=down),
    )
    w.w.tick(T0 + 120)
    ev = w.events()
    assert all(spent_today_uusd(ev, n, T0 + 120) == 0 for n in NAMES)
    assert any(e["type"] == "alert" and e["payload"]["code"] == "perp_llm_no_decision" for e in ev)


def test_refresh_errors_and_stale_views_never_lose_a_call_nor_execute_late(tmp_path, monkeypatch):
    calls: list[str] = []
    w = World(tmp_path, llm=LEAGUE, factory=factory(tmp_path, calls))
    import arena.perp.watcher as W

    real = W.market_view
    n = {"k": 0}

    def flaky(*a, **k):
        n["k"] += 1
        if n["k"] >= 2:  # the first read is the tick's own view; every read after the calls fails
            raise OSError("store")
        return real(*a, **k)

    monkeypatch.setattr(W, "market_view", flaky)
    w.w.tick(T0 + 120)
    ev = w.events()
    assert len(calls) == 4 and len([e for e in ev if e["type"] == "agent_decision"]) == 4
    ex = [e["payload"]["status"] for e in ev if e["type"] == "perp_execution"]
    assert ex and set(ex) == {"not_executed_view_stale"}
    assert all(not replay(ev)[n].positions for n in NAMES)


def test_the_rendezvous_is_two_hours_away_from_the_spot_cycle(tmp_path):
    calls: list[str] = []
    w = World(tmp_path, llm=LEAGUE, factory=factory(tmp_path, calls), offset=2 * 3600)
    rep = w.w.tick(T0 + 120)  # 16:02 UTC: a spot cycle hour, no perp scheduled round
    assert rep.rounds == [] and calls == []
    w.advance(T0 + 2 * 3600 + 120)
    rep = w.w.tick(T0 + 2 * 3600 + 120)  # 18:02 UTC
    assert rep.rounds == [f"rendezvous:{T0 + 2 * 3600}"] and len(calls) == 4


# ---------------------------------------------------------------------- alerts and entry orders (spec)

HAIKU = "llm-perp:claude-haiku-5-5"
HAIKU_MODEL = "claude-haiku-5-5"
LEVEL = 69_437  # USD: below the 70 000 mark of the World
UP_LEVEL = 70_500
BTC_DOWN = 69_000_000_000
BTC_UP = 71_000_000_000


def alert(**kw):
    return {"instrument": "PF_XBTUSD", "condition": "below", "price_usd": LEVEL, "note": "support", **kw}


def entry(**kw):
    return {
        "instrument": "PF_XBTUSD", "side": "long", "condition": "above", "price_usd": UP_LEVEL,
        "size_pct": 10, "stop_pct": 3, "take_profit_pct": 6, "horizon_h": 24, "expected_move_pct": 5, **kw,
    }  # fmt: skip


def orders_world(tmp_path, *, alerts=(), entries=(), league=LEAGUE):
    """A World whose first rendezvous (T0) leaves the given orders for Haiku only; nobody trades."""
    calls: list[str] = []
    extra = {
        "*": {"actions": [], "justification": "j"},
        HAIKU_MODEL: {"alerts": list(alerts), "entry_orders": list(entries)},
    }
    w = World(tmp_path, llm=league, factory=factory(tmp_path, calls, extra=extra))
    rep = w.w.tick(T0 + 120)
    assert not rep.problems, rep.problems
    extra[HAIKU_MODEL] = {}  # later rounds of Haiku post nothing new
    return w, calls, extra


def mark_prices(btc: int) -> dict[str, int]:
    return dict(PRICES, PF_XBTUSD=btc)


def alert_rounds(w):
    return [e["payload"] for e in w.events("perp_round") if e["payload"]["kind"] in ("alert", "private")]


def test_a_crossed_alert_wakes_its_owner_alone(tmp_path):
    w, calls, _ = orders_world(tmp_path, alerts=[alert()])
    assert len(calls) == 4
    set_ev = w.events("agent_orders_set")
    assert [len(e["payload"]["alerts"]) for e in set_ev if e["payload"]["portfolio"] == HAIKU] == [1]
    random_before = len([e for e in w.events("perp_verdict") if "random" in e["payload"]["portfolio"]])
    w.advance(T0 + 3900)
    w.w.tick(T0 + 3900)
    assert not alert_rounds(w)  # not crossed yet
    w.advance(T0 + 4200, mark_prices(BTC_DOWN))
    rep = w.w.tick(T0 + 4200)
    trig = w.events("agent_alert_triggered")
    assert (
        len(trig) == 1
        and trig[0]["payload"]["portfolio"] == HAIKU
        and trig[0]["payload"]["price_uusd"] == LEVEL * 1_000_000
    )
    assert trig[0]["payload"]["mark_low_uusd"] == BTC_DOWN and trig[0]["payload"]["minute"] >= T0 + 3600
    [rnd] = alert_rounds(w)
    own = rnd["triggers"][HAIKU]
    assert rnd["portfolios"] == [HAIKU] and list(rnd["triggers"]) == [HAIKU] and rnd["trigger"] is None
    assert own["kind"] == "alert" and own["alert_id"] == trig[0]["payload"]["id"]
    assert own["price_usd"] == str(LEVEL) and own["note"] == "support"
    assert rep.rounds == [f"private:{T0 + 4200}"]
    assert calls[4:] == [HAIKU_MODEL]  # nobody else was called
    rid = rnd["round"]
    rd = [e["payload"] for e in w.events("round_data") if e["payload"]["round"] == rid]
    assert [r["portfolio"] for r in rd] == [HAIKU] and rd[0]["kind"] == "alert"
    assert (w.var / "rounds" / str(rid)).is_dir() and len(list((w.var / "rounds" / str(rid)).iterdir())) == 1
    assert (
        len([e for e in w.events("perp_verdict") if "random" in e["payload"]["portfolio"]]) == random_before
    )
    assert any(e["type"] == "perp_round_done" and e["payload"]["round"] == rid for e in w.events())
    # the owner's snapshot carries the crossing; the rivals' next round carries nothing about it
    import json

    from arena.perp.agent_round import snapshot

    mine = json.loads((w.var / rd[0]["path"] / "round.json").read_text())
    comp = snapshot(mine, "alert", own)
    assert comp["call"]["type"] == "alert"
    assert comp["account"]["since_your_last_round"]["alerts_triggered"][0]["level_usd"] == str(LEVEL)
    assert comp["account"]["pending_alerts"] == []  # consumed: an alert serves once
    # the next rendezvous: nobody else ever saw it, and the alert is not served twice
    w.advance(T0 + 14400 + 120, mark_prices(BTC_DOWN))
    w.w.tick(T0 + 14400 + 120)
    for e in w.events("round_data"):
        if e["payload"]["portfolio"] != HAIKU:
            raw = (w.var / e["payload"]["path"] / "round.json").read_text()
            assert str(LEVEL) not in raw and "support" not in raw, e["payload"]["portfolio"]
    assert len(alert_rounds(w)) == 1


def test_alert_round_limits(tmp_path, monkeypatch):
    import arena.perp.watcher as W

    # no delay after the owner's last round: the alert is served by the next tick
    w, calls, _ = orders_world(tmp_path / "a", alerts=[alert()])
    w.advance(T0 + 600, mark_prices(BTC_DOWN))
    w.w.tick(T0 + 600)
    assert len(w.events("agent_alert_triggered")) == 1 and len(alert_rounds(w)) == 1
    assert calls[4:] == [HAIKU_MODEL]
    # a crossed alert waiting more than an hour (here: a spot cycle never ending) is no longer served
    w2, calls2, _ = orders_world(tmp_path / "b", alerts=[alert()])
    monkeypatch.setattr(W, "spot_cycle_soon", lambda ts: True)
    w2.advance(T0 + 600, mark_prices(BTC_DOWN))
    w2.w.tick(T0 + 600)
    assert len(w2.events("agent_alert_triggered")) == 1 and not alert_rounds(w2)
    monkeypatch.undo()
    w2.advance(T0 + 4500)
    w2.w.tick(T0 + 4500)
    assert not alert_rounds(w2) and len(calls2) == 4
    # no round left today outside the scheduled rounds: the alert waits for the next one
    w3, calls3, _ = orders_world(tmp_path / "c", alerts=[alert()])
    for i in range(LEAGUE.rounds_per_day):
        w3.w.sim.append_event("round_data", {"portfolio": HAIKU, "round": -1 - i}, T0 + 200)
    w3.advance(T0 + 4200, mark_prices(BTC_DOWN))
    w3.w.tick(T0 + 4200)
    assert len(w3.events("agent_alert_triggered")) == 1 and not alert_rounds(w3) and len(calls3) == 4
    # the spot league holds its cycle lock: the round waits; it is served by the first tick after
    w4, calls4, _ = orders_world(tmp_path / "d", alerts=[alert()])
    import fcntl

    w4.spot.var.mkdir(parents=True, exist_ok=True)
    with open(w4.spot.lock, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        w4.advance(T0 + 4200, mark_prices(BTC_DOWN))
        rep = w4.w.tick(T0 + 4200)
        assert not alert_rounds(w4) and any("spot league" in n for n in rep.notes)
        fcntl.flock(f, fcntl.LOCK_UN)
    w4.advance(T0 + 4500)
    w4.w.tick(T0 + 4500)
    assert len(alert_rounds(w4)) == 1 and calls4[4:] == [HAIKU_MODEL]


def test_no_alert_round_before_a_rendezvous_and_the_rendezvous_serves_it(tmp_path):
    w, calls, _ = orders_world(tmp_path, alerts=[alert(expires_h=24)])
    t = T0 + 4 * 3600 - 200  # the next rendezvous falls within the tick
    w.advance(t, mark_prices(BTC_DOWN))
    w.w.tick(t)
    assert len(w.events("agent_alert_triggered")) == 1 and not alert_rounds(w) and len(calls) == 4
    w.advance(T0 + 4 * 3600 + 120)
    w.w.tick(T0 + 4 * 3600 + 120)  # the rendezvous: every model plays, Haiku sees its crossed alert
    assert len(calls) == 8 and not alert_rounds(w)
    import json

    rd = [e["payload"] for e in w.events("round_data") if e["payload"]["portfolio"] == HAIKU][-1]
    view = json.loads((w.var / rd["path"] / "round.json").read_text())["agent_orders"]
    assert len(view["since"]["alerts_triggered"]) == 1
    w.advance(T0 + 4 * 3600 + 7200)
    w.w.tick(T0 + 4 * 3600 + 7200)
    assert not alert_rounds(w)  # served by the rendezvous: no second round


def test_alert_rounds_do_not_use_the_wakeup_cooldown_nor_the_alert_budget_gate(tmp_path):
    small = dataclasses.replace(
        LEAGUE,
        models=tuple(
            dataclasses.replace(m, daily_budget_uusd=1) if m.model == HAIKU_MODEL else m
            for m in LEAGUE.models
        ),
    )
    # no budget left for the owner: no alert round is even started
    w, calls, _ = orders_world(tmp_path / "a", alerts=[alert()], league=small)
    w.advance(T0 + 4200, mark_prices(BTC_DOWN))
    w.w.tick(T0 + 4200)
    assert len(w.events("agent_alert_triggered")) == 1 and not alert_rounds(w) and len(calls) == 4
    # an alert round does not delay the market wake-ups
    w2, _calls2, _ = orders_world(tmp_path / "b", alerts=[alert()])
    w2.advance(T0 + 4200, mark_prices(BTC_DOWN))
    w2.w.tick(T0 + 4200)
    assert len(alert_rounds(w2)) == 1
    w2.advance(T0 + 4500)
    w2.w.tick(T0 + 4500)
    up = mark_prices(BTC_DOWN)
    up["PF_SOLUSD"] = PRICES["PF_SOLUSD"] * 105 // 100
    w2.advance(T0 + 4800, up)
    rep = w2.w.tick(T0 + 4800)
    assert any(r.startswith("wakeup:") for r in rep.rounds), rep.rounds


def test_an_interrupted_alert_round_is_resumed_for_its_owner_only(tmp_path, monkeypatch):
    w, calls, _ = orders_world(tmp_path, alerts=[alert()])
    import arena.perp.llm_league as L

    class Cut:
        def __init__(self, *a, **k):
            raise RuntimeError("power cut")

    w.advance(T0 + 4200, mark_prices(BTC_DOWN))
    monkeypatch.setattr(L, "ThreadPoolExecutor", Cut)
    rep = w.w.tick(T0 + 4200)
    assert any("llm round" in p for p in rep.problems) and len(calls) == 4
    monkeypatch.undo()
    w.advance(T0 + 4500)
    rep = w.w.tick(T0 + 4500)
    assert any("(resumed)" in r and r.startswith("private:") for r in rep.rounds)
    assert len(calls) == 4  # never called again after a cut
    skipped = [e["payload"] for e in w.events("perp_llm_skipped")]
    assert [s["portfolio"] for s in skipped] == [HAIKU]  # the filter survived the resume: nobody else
    assert any(e["type"] == "perp_round_done" and e["payload"]["round"] == T0 + 4200 for e in w.events())


def test_run_llm_round_only_filters_the_models(tmp_path):
    calls: list[str] = []
    w = World(tmp_path, llm=LEAGUE, factory=factory(tmp_path, calls))
    w.w.tick(T0 + 120)
    view, _ = _view(w, T0 + 120)
    from arena.perp.llm_league import run_llm_round

    n = len(calls)
    run_llm_round(
        league=LEAGUE, var=w.var, sim=w.w.sim, store=w.store, view=view, specs=w.w.specs, policy=w.w.policy,
        config_sha256=w.w.cfg.sha256, round_id=777, now_ts=T0 + 4000, kind="alert", trigger=None,
        entries_blocked=lambda: False, decider_factory=factory(tmp_path, calls), only={HAIKU},
    )  # fmt: skip
    assert calls[n:] == [HAIKU_MODEL]
    assert {e["payload"]["portfolio"] for e in w.events("round_data") if e["payload"]["round"] == 777} == {
        HAIKU
    }


# ---- entry orders


def entry_events(w):
    ev = w.events()
    oid = w.events("agent_entry_triggered")[0]["payload"]["id"]
    return oid, [e for e in ev if e["payload"].get("intent_id") == oid or e["payload"].get("order_id") == oid]


def test_a_crossed_entry_order_goes_through_riskd_and_is_filled_with_a_stop(tmp_path):
    w, calls, _ = orders_world(tmp_path, entries=[entry()])
    w.advance(T0 + 600, mark_prices(BTC_UP))
    rep = w.w.tick(T0 + 600)
    assert not rep.problems, rep.problems
    assert len(calls) == 4  # no model call for an entry order
    [trig] = w.events("agent_entry_triggered")
    assert trig["payload"]["side"] == "long" and trig["payload"]["mark_high_uusd"] == BTC_UP
    oid, evs = entry_events(w)
    kinds = [e["type"] for e in evs]
    assert kinds == ["perp_verdict", "perp_fill", "perp_execution"], kinds
    verdict, fill, execution = (e["payload"] for e in evs)
    assert verdict["approved"] and verdict["portfolio"] == HAIKU and verdict["action"] == "open_long"
    assert fill["reason"] == "intent" and fill["qty"] == verdict["qty"] > 0 and fill["fee_ueur"] > 0
    assert fill["price_uusd"] >= BTC_UP  # filled at market with slippage, not at the level
    assert execution["status"] == "filled"
    pos = replay(w.events())[HAIKU].positions["PF_XBTUSD"]
    assert (
        pos.stop_uusd and pos.take_profit_uusd and pos.stop_uusd < fill["price_uusd"] < pos.take_profit_uusd
    )
    stops = [e for e in w.events("conditional_order") if e["payload"]["portfolio"] == HAIKU]
    assert {e["payload"]["kind"] for e in stops} == {"stop", "take_profit"}
    # consumed: the next ticks do not fire it again
    w.advance(T0 + 1200)
    w.w.tick(T0 + 1200)
    assert (
        len(w.events("agent_entry_triggered")) == 1
        and len([e for e in w.events("perp_fill") if e["payload"]["order_id"] == oid]) == 1
    )


def test_a_refused_entry_is_journaled_and_shown_next_round(tmp_path):
    import json

    from arena.perp.agent_round import snapshot

    w, _calls, _extra = orders_world(tmp_path, entries=[entry(size_pct=100)])  # over the 50 % order cap
    w.advance(T0 + 600, mark_prices(BTC_UP))
    w.w.tick(T0 + 600)
    _oid, evs = entry_events(w)
    assert [e["type"] for e in evs] == ["perp_verdict"] and not evs[0]["payload"]["approved"]
    assert "MAX_ORDER_SIZE" in evs[0]["payload"]["reasons"]
    assert not replay(w.events())[HAIKU].positions
    w.advance(T0 + 4 * 3600 + 120, mark_prices(BTC_UP))
    w.w.tick(T0 + 4 * 3600 + 120)
    rd = [e["payload"] for e in w.events("round_data") if e["payload"]["portfolio"] == HAIKU][-1]
    comp = snapshot(json.loads((w.var / rd["path"] / "round.json").read_text()), "rendezvous", None)["account"]
    [o] = comp["since_your_last_round"]["orders_triggered"]
    assert (
        o["guardrail"] == "refused"
        and "MAX_ORDER_SIZE" in o["refusal_reasons"]
        and o["level_usd"] == str(UP_LEVEL)
    )
    assert o["fill_price_usd"] is None


def test_a_stale_trigger_is_never_executed(tmp_path):
    from arena.perp.watcher import ENTRY_MAX_LAG_S

    assert ENTRY_MAX_LAG_S == 900
    w, _calls, _ = orders_world(tmp_path, entries=[entry()])
    w.advance(T0 + 2400, mark_prices(BTC_UP))  # crossed at ~T0+120.. but the tick only runs 40 min later
    w.w.tick(T0 + 2400)
    oid, evs = entry_events(w)
    assert [e["type"] for e in evs] == ["perp_execution"]
    assert evs[0]["payload"]["status"] == "not_executed_stale_trigger"
    assert not w.events("perp_fill") or all(e["payload"]["order_id"] != oid for e in w.events("perp_fill"))
    assert not replay(w.events())[HAIKU].positions


def test_a_cut_between_trigger_and_verdict_is_resumed_once(tmp_path, monkeypatch):
    import arena.perp.watcher as W

    w, _calls, _ = orders_world(tmp_path, entries=[entry()])
    w.advance(T0 + 600, mark_prices(BTC_UP))
    real = W.evaluate_perp

    def cut(intent, *a, **k):
        if intent.portfolio == HAIKU:
            raise KeyboardInterrupt
        return real(intent, *a, **k)

    monkeypatch.setattr(W, "evaluate_perp", cut)
    with pytest.raises(KeyboardInterrupt):
        w.w.tick(T0 + 600)
    monkeypatch.setattr(W, "evaluate_perp", real)
    assert len(w.events("agent_entry_triggered")) == 1
    assert not [e for e in w.events("perp_fill") if e["payload"]["portfolio"] == HAIKU]
    w.advance(T0 + 900)
    w.w.tick(T0 + 900)
    _oid, evs = entry_events(w)
    assert [e["type"] for e in evs] == ["perp_verdict", "perp_fill", "perp_execution"]
    assert len(w.events("agent_entry_triggered")) == 1 and len(replay(w.events())[HAIKU].positions) == 1


def test_a_cut_between_the_approved_verdict_and_the_execution_is_resumed_once(tmp_path, monkeypatch):
    w, _calls, _ = orders_world(tmp_path, entries=[entry()])
    w.advance(T0 + 600, mark_prices(BTC_UP))
    real = w.w.sim.market_order

    def cut(order_id, portfolio, *a, **k):
        if portfolio == HAIKU:
            raise KeyboardInterrupt
        return real(order_id, portfolio, *a, **k)

    monkeypatch.setattr(w.w.sim, "market_order", cut)
    with pytest.raises(KeyboardInterrupt):
        w.w.tick(T0 + 600)
    monkeypatch.setattr(w.w.sim, "market_order", real)
    oid, evs = entry_events(w)
    assert [e["type"] for e in evs] == ["perp_verdict"] and evs[0]["payload"]["approved"]
    w.advance(T0 + 900)
    w.w.tick(T0 + 900)
    oid, evs = entry_events(w)
    assert [e["type"] for e in evs] == ["perp_verdict", "perp_fill", "perp_execution"]
    assert evs[2]["payload"]["status"] == "filled" and len(w.events("perp_verdict")) == len(
        [e for e in w.events("perp_verdict")]
    )
    assert len([e for e in w.events("perp_verdict") if e["payload"]["intent_id"] == oid]) == 1
    assert replay(w.events())[HAIKU].positions["PF_XBTUSD"].stop_uusd


def test_expiry_halt_and_failures_of_the_orders_step(tmp_path, monkeypatch):
    # an expired element never fires, even if the level is crossed afterwards (the crossing starts after the
    # expiry at T0 + 120 + 3600, and the tick that sees both comes later)
    w, _calls, _ = orders_world(tmp_path / "a", alerts=[alert(expires_h=1)], entries=[entry(expires_h=1)])
    w.advance(T0 + 3840)
    w.advance(T0 + 3900, mark_prices(BTC_UP))
    w.w.tick(T0 + 3900)
    ended = [e["payload"] for e in w.events("agent_order_ended")]
    assert sorted((x["kind"], x["reason"]) for x in ended) == [("alert", "expired"), ("entry", "expired")]
    assert (
        not w.events("agent_alert_triggered")
        and not w.events("agent_entry_triggered")
        and not alert_rounds(w)
    )
    # a halted portfolio expires everything it had pending
    w2, _c, _ = orders_world(tmp_path / "b", alerts=[alert()], entries=[entry()])
    w2.w.sim.append_event(
        "portfolio_halted", {"portfolio": HAIKU, "reason": "drawdown", "until_ts": 0}, T0 + 200
    )
    w2.advance(T0 + 600, mark_prices(BTC_UP))
    w2.w.tick(T0 + 600)
    ended = [e["payload"] for e in w2.events("agent_order_ended")]
    assert sorted(x["reason"] for x in ended) == ["portfolio_halted", "portfolio_halted"]
    assert not w2.events("agent_entry_triggered") and not replay(w2.events())[HAIKU].positions
    # a failure of the step is reported in the tick, never raised, and the tick completes
    w3, _c, _ = orders_world(tmp_path / "c", alerts=[alert()])
    import arena.perp.watcher as W

    monkeypatch.setattr(W.AO, "pending_state", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    w3.advance(T0 + 600)
    rep = w3.w.tick(T0 + 600)
    assert any("agent orders" in p and "boom" in p for p in rep.problems)
    assert w3.events("perp_tick")[-1]["ts"] == T0 + 600


def test_a_crossing_before_the_expiry_counts_even_when_seen_after_it(tmp_path):
    w, _calls, _ = orders_world(tmp_path, alerts=[alert(expires_h=1)])
    w.advance(T0 + 3000)
    w.advance(T0 + 3600, mark_prices(BTC_DOWN))  # crossed before T0 + 3720
    w.advance(T0 + 3900)
    w.w.tick(T0 + 3900)  # first tick since T0 + 120: after the expiry
    assert len(w.events("agent_alert_triggered")) == 1
    assert not [e for e in w.events("agent_order_ended") if e["payload"]["reason"] == "expired"]


def test_crossings_are_detected_even_with_a_stale_market_view(tmp_path):
    w, _calls, _ = orders_world(tmp_path, alerts=[alert()], entries=[entry()])
    # the alert (below) and the entry (above) on two instruments' worth of moves: BTC dips, then rallies;
    # minutes keep coming, but no ticker snapshot for 40 min: the view is stale, and the minutes older than
    # MINUTE_PATIENCE_S are processed without their EUR/USD
    w.minutes(T0 + 120, T0 + 600, mark_prices(BTC_DOWN))
    w.minutes(T0 + 600, T0 + 2400, mark_prices(BTC_UP))
    rep = w.w.tick(T0 + 2400)
    assert any("stale" in p for p in rep.problems), rep
    assert len(w.events("agent_alert_triggered")) == 1 and len(w.events("agent_entry_triggered")) == 1
    assert not w.events("perp_verdict") or all(
        e["payload"]["portfolio"] != HAIKU for e in w.events("perp_verdict")
    )  # an entry is never judged on a stale view
    # the next fresh tick: the crossing is more than 15 min old, never executed late
    w.advance(T0 + 2700, mark_prices(BTC_UP))
    w.w.tick(T0 + 2700)
    _oid, evs = entry_events(w)
    assert [e["payload"]["status"] for e in evs if e["type"] == "perp_execution"] == [
        "not_executed_stale_trigger"
    ]
    assert HAIKU not in {n for n, a in replay(w.events()).items() if a.positions}


def test_a_cut_between_the_fill_and_the_stop_is_never_left_unprotected(tmp_path, monkeypatch):
    w, _calls, _ = orders_world(tmp_path, entries=[entry()])
    w.advance(T0 + 600, mark_prices(BTC_UP))
    real = w.w.sim.set_conditional

    def cut(portfolio, *a, **k):
        if portfolio == HAIKU:
            raise KeyboardInterrupt
        return real(portfolio, *a, **k)

    monkeypatch.setattr(w.w.sim, "set_conditional", cut)
    with pytest.raises(KeyboardInterrupt):
        w.w.tick(T0 + 600)
    monkeypatch.setattr(w.w.sim, "set_conditional", real)
    oid, evs = entry_events(w)
    assert [e["type"] for e in evs] == ["perp_verdict", "perp_fill"]
    w.advance(T0 + 900, mark_prices(BTC_UP))
    w.w.tick(T0 + 900)
    oid, evs = entry_events(w)
    statuses = [e["payload"]["status"] for e in evs if e["type"] == "perp_execution"]
    assert statuses == ["closed_without_stop"]
    assert "PF_XBTUSD" not in replay(w.events())[HAIKU].positions
    assert len([e for e in w.events("perp_fill") if e["payload"]["order_id"] == oid]) == 1


# ---- free wake-ups (docs/SPEC-PERP-FREE-WAKEUPS.md)


def private_rounds(w):
    return [e["payload"] for e in w.events("perp_round") if e["payload"]["kind"] == "private"]


def asked_world(tmp_path, minutes: dict[str, int | None], league=LEAGUE):
    """The first rendezvous (T0) where each model in `minutes` asks to be woken up; nobody trades."""
    calls: list[str] = []
    extra: dict = {"*": {"actions": [], "justification": "j"}}
    for model, n in minutes.items():
        extra[model] = {"next_wakeup_min": n}
    w = World(tmp_path, llm=league, factory=factory(tmp_path, calls, extra=extra))
    rep = w.w.tick(T0 + 120)
    assert not rep.problems, rep.problems
    for model in minutes:
        extra[model] = {}
    return w, calls, extra


def test_a_model_is_woken_up_when_it_asked(tmp_path):
    import json

    from arena.perp.agent_orders import pending_wakeup
    from arena.perp.agent_round import snapshot

    w, calls, _ = asked_world(tmp_path, {HAIKU_MODEL: 30})
    [asked] = w.events("agent_wakeup_set")
    due = asked["payload"]["due_ts"]
    assert asked["payload"]["portfolio"] == HAIKU and asked["payload"]["minutes"] == 30
    assert T0 + 120 + 1800 <= due < T0 + 120 + 1800 + 60  # counted from when the decision is applied
    w.advance(T0 + 1500)
    w.w.tick(T0 + 1500)
    assert not private_rounds(w) and len(calls) == 4  # not yet
    w.advance(T0 + 1800)
    rep = w.w.tick(T0 + 1800)  # the tick starting at most 2.5 min before the time asked serves it
    [rnd] = private_rounds(w)
    assert rep.rounds == [f"private:{T0 + 1800}"] and rnd["portfolios"] == [HAIKU]
    assert rnd["triggers"][HAIKU] == {"kind": "scheduled", "asked_at_round": T0, "due_ts": due}
    assert calls[4:] == [HAIKU_MODEL]
    rd = [e["payload"] for e in w.events("round_data") if e["payload"]["round"] == T0 + 1800]
    assert [r["kind"] for r in rd] == ["scheduled"]
    data = json.loads((w.var / rd[0]["path"] / "round.json").read_text())
    snap = snapshot(data, "scheduled", rnd["triggers"][HAIKU])
    assert snap["call"]["type"] == "scheduled"
    rounds = snap["account"]["rounds"]
    assert rounds["rounds_per_day"] == 48 and rounds["rounds_played_today"] == 1
    from arena.perp.round_quota import rendezvous_left

    left = rendezvous_left(T0 + 1800, 0)
    assert rounds["scheduled_rounds_left_today"] == left
    assert rounds["unscheduled_rounds_left"] == 48 - 1 - left - 1
    assert rounds["wakeup_requested_utc"] is not None  # still pending when the round was built
    assert pending_wakeup(w.events(), HAIKU) is None  # served
    w.advance(T0 + 2100)
    w.w.tick(T0 + 2100)
    assert len(private_rounds(w)) == 1 and len(calls) == 5  # served once


def test_each_decision_replaces_the_asked_wakeup(tmp_path):
    from arena.perp.agent_orders import pending_wakeup

    w, _calls, extra = asked_world(tmp_path, {HAIKU_MODEL: 45})
    assert pending_wakeup(w.events(), HAIKU) is not None
    # an alert-free market wake-up at 00:30: Haiku's decision asks nothing, so the pending wake-up is cancelled
    w.advance(T0 + 1830)
    play_at(w, T0 + 1800, "wakeup", {"instrument": "PF_XBTUSD"}, T0 + 1830)
    sets = [e["payload"] for e in w.events("agent_wakeup_set")]
    assert [s["due_ts"] for s in sets][-1] is None and pending_wakeup(w.events(), HAIKU) is None
    # a decision that asks again replaces it; a model that never asked writes nothing
    extra[HAIKU_MODEL] = {"next_wakeup_min": 5}
    w.advance(T0 + 7230)
    play_at(w, T0 + 7200, "wakeup", {"instrument": "PF_XBTUSD"}, T0 + 7230)
    assert {e["payload"]["portfolio"] for e in w.events("agent_wakeup_set")} == {HAIKU}
    due = pending_wakeup(w.events(), HAIKU)["due_ts"]
    assert T0 + 7200 + 30 + 300 <= due < T0 + 7200 + 30 + 360


def play_at(w: World, round_id: int, kind: str, trigger, now: int) -> None:
    view, rep = _view(w, now)
    w.w._deferred = None
    w.w._round(round_id, kind, trigger, now, view, rep)
    if w.w._deferred is not None:
        w.w._llm_phase(**w.w._deferred, rep=rep)


def test_an_invalid_asked_time_keeps_the_pending_wakeup(tmp_path):
    from arena.perp.agent_orders import pending_wakeup

    w, _calls, extra = asked_world(tmp_path, {HAIKU_MODEL: 45})
    due = pending_wakeup(w.events(), HAIKU)["due_ts"]
    extra[HAIKU_MODEL] = {"next_wakeup_min": 4}
    w.advance(T0 + 1830)
    play_at(w, T0 + 1800, "wakeup", {"instrument": "PF_XBTUSD"}, T0 + 1830)
    [d] = [
        e["payload"]
        for e in w.events("agent_decision")
        if e["payload"]["round"] == T0 + 1800 and e["payload"]["portfolio"] == HAIKU
    ]
    assert d["parse_error"] is None and d["parsed"]["next_wakeup_invalid"]
    assert len(w.events("agent_wakeup_set")) == 1 and pending_wakeup(w.events(), HAIKU)["due_ts"] == due
    # 60.0 is an integer for the CLI's JSON schema: accepted
    extra[HAIKU_MODEL] = {"next_wakeup_min": 60.0}
    w.advance(T0 + 7230)
    play_at(w, T0 + 7200, "wakeup", {"instrument": "PF_XBTUSD"}, T0 + 7230)
    assert w.events("agent_wakeup_set")[-1]["payload"]["minutes"] == 60


def test_an_invalid_asked_time_is_rejected_alone(tmp_path):
    w, _calls, _ = asked_world(tmp_path, {HAIKU_MODEL: 3})
    assert not w.events("agent_wakeup_set")
    [d] = [e["payload"] for e in w.events("agent_decision") if e["payload"]["portfolio"] == HAIKU]
    assert d["parse_error"] is None and d["parsed"]["next_wakeup_min"] is None
    rejected = [
        e["payload"]["rejected"] for e in w.events("agent_orders_set") if e["payload"]["portfolio"] == HAIKU
    ]
    assert rejected == [
        [{"kind": "wakeup", "k": 0, "error": "next_wakeup_min: an integer from 5 to 60 is expected"}]
    ]


def test_two_models_due_at_the_same_tick_share_one_private_round(tmp_path):
    w, calls, _ = asked_world(tmp_path, {HAIKU_MODEL: 30, "claude-sonnet-5-5": 30})
    w.advance(T0 + 1800)
    w.w.tick(T0 + 1800)
    [rnd] = private_rounds(w)
    sonnet = "llm-perp:claude-sonnet-5-5"
    assert rnd["portfolios"] == sorted([HAIKU, sonnet]) and set(rnd["triggers"]) == {HAIKU, sonnet}
    assert sorted(calls[4:]) == sorted([HAIKU_MODEL, "claude-sonnet-5-5"])
    # each model saw its own trigger only
    rd = {
        e["payload"]["portfolio"]: e["payload"]
        for e in w.events("round_data")
        if e["payload"]["round"] == T0 + 1800
    }
    import json

    for p in (HAIKU, sonnet):
        assert json.loads(rd[p]["trigger"]) == rnd["triggers"][p]
    # no benchmark plays a private round
    assert not [
        e
        for e in w.events("perp_verdict")
        if e["payload"]["portfolio"].startswith("random") and e["ts"] >= T0 + 1800
    ]


def test_a_rendezvous_within_the_tick_serves_the_asked_wakeup(tmp_path):
    from arena.perp.agent_orders import pending_wakeup

    w, calls, extra = asked_world(tmp_path, {})
    extra[HAIKU_MODEL] = {"next_wakeup_min": 57}  # asked at about 03:00, due at about 03:58
    w.advance(T0 + 10830)
    play_at(w, T0 + 10800, "wakeup", {"instrument": "PF_XBTUSD"}, T0 + 10830)
    extra[HAIKU_MODEL] = {}
    assert len(calls) == 8 and pending_wakeup(w.events(), HAIKU) is not None
    t = T0 + 4 * 3600 - 90
    w.advance(t)
    w.w.tick(t)
    assert not private_rounds(w) and len(calls) == 8
    w.advance(T0 + 4 * 3600 + 120)
    w.w.tick(T0 + 4 * 3600 + 120)  # the rendezvous serves it
    assert len(calls) == 12 and pending_wakeup(w.events(), HAIKU) is None
    w.advance(T0 + 4 * 3600 + 420)
    w.w.tick(T0 + 4 * 3600 + 420)
    assert not private_rounds(w) and len(calls) == 12


def test_an_asked_wakeup_lapses_after_an_hour(tmp_path, monkeypatch):
    import arena.perp.watcher as W

    w, calls, _ = asked_world(tmp_path, {HAIKU_MODEL: 30})
    monkeypatch.setattr(W, "spot_busy", lambda lock: True)
    for t in range(T0 + 1800, T0 + 1800 + 3900, 300):
        w.advance(t)
        w.w.tick(t)
    monkeypatch.undo()
    w.advance(T0 + 6000)
    w.w.tick(T0 + 6000)
    assert not private_rounds(w) and len(calls) == 4


def test_the_rounds_per_day_quota(tmp_path):
    from arena.perp.round_quota import quota, rendezvous_left

    day = 1_794_441_600
    assert [rendezvous_left(day + h * 3600, 7200) for h in (0, 2, 3, 21, 22, 23)] == [6, 5, 5, 1, 0, 0]
    events = [
        {"type": "round_data", "ts": day + 60 + i, "seq": i, "payload": {"portfolio": "p", "round": i}}
        for i in range(10)
    ]
    events.append(
        {"type": "round_data", "ts": day - 10, "seq": 99, "payload": {"portfolio": "p", "round": 99}}
    )
    q = quota(events, "p", day + 3 * 3600, 48, 7200)
    assert q == {"per_day": 48, "played_today": 10, "rendezvous_left": 5, "extra_left": 33}
    # with no extra round left, the market wake-up leaves the model out (the others play)
    w, calls, _ = asked_world(tmp_path, {})
    for i in range(LEAGUE.rounds_per_day):
        w.w.sim.append_event("round_data", {"portfolio": HAIKU, "round": -1 - i}, T0 + 200)
    w.advance(T0 + 3600 + 300)
    w.w.tick(T0 + 3600 + 300)
    up = dict(PRICES, PF_SOLUSD=PRICES["PF_SOLUSD"] * 1025 // 1000)  # +2.5 %: over the 2 % threshold
    w.advance(T0 + 3600 + 600, up)
    rep = w.w.tick(T0 + 3600 + 600)
    [wk] = [e["payload"] for e in w.events("perp_round") if e["payload"]["kind"] == "wakeup"]
    assert rep.rounds == [f"wakeup:{T0 + 3600 + 600}"]
    assert HAIKU not in wk["portfolios"] and len(wk["portfolios"]) == 3 and HAIKU_MODEL not in calls[4:]
    assert len(calls) == 7


def test_market_wakeups_are_15_min_apart_without_a_daily_cap(tmp_path):
    import arena.perp.watcher as W

    assert W.WAKE_MOVE_BP == 200 and W.WAKE_COOLDOWN_S == 900 and not hasattr(W, "WAKE_MAX_PER_DAY")
    w, _calls, _ = asked_world(tmp_path, {})
    w.advance(T0 + 3600 + 300)
    w.w.tick(T0 + 3600 + 300)
    up = dict(PRICES, PF_SOLUSD=PRICES["PF_SOLUSD"] * 1025 // 1000)
    w.advance(T0 + 3600 + 600, up)
    assert w.w.tick(T0 + 3600 + 600).rounds == [f"wakeup:{T0 + 3600 + 600}"]
    up2 = dict(up, PF_ETHUSD=PRICES["PF_ETHUSD"] * 1025 // 1000)
    w.advance(T0 + 3600 + 900, up2)
    assert w.w.tick(T0 + 3600 + 900).rounds == []  # ETH crossed, but 5 min after the last wake-up
    w.advance(T0 + 3600 + 1500, up2)
    assert w.w.tick(T0 + 3600 + 1500).rounds == [f"wakeup:{T0 + 3600 + 1500}"]  # served 15 min after


def test_a_market_crossing_during_the_spot_guard_is_served_after(tmp_path, monkeypatch):
    import arena.perp.watcher as W

    w, calls, _ = asked_world(tmp_path, {})
    w.advance(T0 + 3600 + 300)
    w.w.tick(T0 + 3600 + 300)
    monkeypatch.setattr(W, "spot_busy", lambda lock: True)
    up = dict(PRICES, PF_SOLUSD=PRICES["PF_SOLUSD"] * 1025 // 1000)
    w.advance(T0 + 3600 + 600, up)
    rep = w.w.tick(T0 + 3600 + 600)
    assert rep.rounds == [] and len(w.events("perp_wake_pending")) == 1  # recorded while waiting
    monkeypatch.undo()
    w.advance(T0 + 3600 + 900, up)
    assert w.w.tick(T0 + 3600 + 900).rounds == [f"wakeup:{T0 + 3600 + 900}"]
    assert len(calls) == 8


def test_a_rendezvous_starts_even_while_a_private_round_waits_for_the_spot_league(tmp_path, monkeypatch):
    import arena.perp.watcher as W

    w, _calls, _ = asked_world(tmp_path, {})
    rid = T0 + 4 * 3600 - 600
    payload = {
        "round": rid, "kind": "private", "trigger": None, "ts": rid, "portfolios": [HAIKU],
        "triggers": {HAIKU: {"kind": "scheduled"}},
    }  # fmt: skip
    w.w.sim.append_event("perp_round", payload, rid)
    monkeypatch.setattr(W, "spot_busy", lambda lock: True)
    w.advance(T0 + 4 * 3600 + 120)
    rep = w.w.tick(T0 + 4 * 3600 + 120)
    assert rep.rounds == [f"rendezvous:{T0 + 4 * 3600}"]


def test_a_move_seen_at_a_rendezvous_is_not_played_again_as_a_wakeup(tmp_path):
    w, calls, _ = asked_world(tmp_path, {})
    w.advance(T0 + 4 * 3600 - 900)
    w.w.tick(T0 + 4 * 3600 - 900)
    up = dict(PRICES, PF_SOLUSD=PRICES["PF_SOLUSD"] * 1025 // 1000)
    w.advance(T0 + 4 * 3600 + 120, up)
    assert w.w.tick(T0 + 4 * 3600 + 120).rounds == [f"rendezvous:{T0 + 4 * 3600}"]
    assert len(w.events("perp_wake_pending")) == 1  # recorded at the rendezvous tick
    w.advance(T0 + 4 * 3600 + 1200, up)
    assert w.w.tick(T0 + 4 * 3600 + 1200).rounds == []  # the models saw it at the rendezvous
    assert len(calls) == 8


# --- default cadence (docs/SPEC-PERP-CADENCE.md) ---


def cadenced_world(tmp_path, minutes: dict[str, int | None], league=CADENCED):
    return asked_world(tmp_path, minutes, league=league)


def test_the_default_cadence_calls_every_model_again(tmp_path):
    import json

    from arena.perp.agent_round import snapshot

    w, calls, _ = cadenced_world(tmp_path, {})
    assert len(calls) == 4
    w.advance(T0 + 600)
    w.w.tick(T0 + 600)
    assert not private_rounds(w) and len(calls) == 4  # not yet: the rendezvous was 8 min ago
    w.advance(T0 + 900)
    rep = w.w.tick(T0 + 900)
    [rnd] = private_rounds(w)
    assert rep.rounds == [f"private:{T0 + 900}"] and rnd["portfolios"] == sorted(NAMES)
    assert {p: t["kind"] for p, t in rnd["triggers"].items()} == dict.fromkeys(NAMES, "cadence")
    assert rnd["triggers"][HAIKU] == {"kind": "cadence", "every_min": 15, "last_round_ts": T0 + 120}
    assert len(calls) == 8
    rd = [e["payload"] for e in w.events("round_data") if e["payload"]["round"] == T0 + 900]
    assert {r["kind"] for r in rd} == {"cadence"}
    data = json.loads((w.var / rd[0]["path"] / "round.json").read_text())
    assert snapshot(data, "cadence", rnd["triggers"][rd[0]["portfolio"]])["call"]["type"] == "cadence"
    for t in (T0 + 1200, T0 + 1500):
        w.advance(t)
        w.w.tick(t)
    assert len(private_rounds(w)) == 1 and len(calls) == 8
    w.advance(T0 + 1800)
    w.w.tick(T0 + 1800)  # 15 min after the last round
    assert len(private_rounds(w)) == 2 and len(calls) == 12


def test_an_asked_wakeup_only_brings_the_cadence_forward(tmp_path):
    from arena.perp.agent_orders import pending_wakeup

    # Haiku asks 45 min, more than the cadence: it is called at the cadence all the same
    w, calls, extra = cadenced_world(tmp_path, {HAIKU_MODEL: 45})
    w.advance(T0 + 900)
    w.w.tick(T0 + 900)
    [rnd] = private_rounds(w)
    assert rnd["portfolios"] == sorted(NAMES) and rnd["triggers"][HAIKU]["kind"] == "cadence"
    assert len(calls) == 8 and pending_wakeup(w.events(), HAIKU) is None  # its decision asked nothing more
    # Sonnet asks 5 min: called earlier than the cadence, as `scheduled`
    extra["claude-sonnet-5-5"] = {"next_wakeup_min": 5}
    w.advance(T0 + 1800)
    w.w.tick(T0 + 1800)
    extra["claude-sonnet-5-5"] = {}
    sonnet = "llm-perp:claude-sonnet-5-5"
    w.advance(T0 + 2100)
    w.w.tick(T0 + 2100)
    last = private_rounds(w)[-1]
    assert last["round"] == T0 + 2100 and last["portfolios"] == [sonnet]
    assert last["triggers"][sonnet]["kind"] == "scheduled"
    # Haiku's 45 min (T0+2820) never bring a call of their own: only the cadence calls it
    for t in range(T0 + 2400, T0 + 3300, 300):
        w.advance(t)
        w.w.tick(t)
    assert all(r["triggers"][HAIKU]["kind"] == "cadence" for r in private_rounds(w) if HAIKU in r["portfolios"])


def test_the_cadence_respects_the_quota_and_can_be_off(tmp_path):
    # T0 is 16:00 UTC: the rendezvous played and the one at 20:00 use the 2 rounds of the day
    w, calls, _ = cadenced_world(tmp_path, {}, league=dataclasses.replace(CADENCED, rounds_per_day=2))
    w.advance(T0 + 900)
    w.w.tick(T0 + 900)
    assert not private_rounds(w) and len(calls) == 4  # no round left outside the scheduled rounds
    off = tmp_path / "off"
    off.mkdir()
    w, calls, _ = cadenced_world(off, {}, league=dataclasses.replace(CADENCED, cadence_min=0))
    w.advance(T0 + 900)
    w.w.tick(T0 + 900)
    assert not private_rounds(w) and len(calls) == 4


def test_a_failed_round_counts_for_the_cadence(tmp_path):
    w, _calls, extra = cadenced_world(tmp_path, {})
    extra[HAIKU_MODEL] = {"actions": "not a list"}  # an invalid decision: the round is played all the same
    w.advance(T0 + 900)
    w.w.tick(T0 + 900)
    [d] = [
        e["payload"]
        for e in w.events("agent_decision")
        if e["payload"]["round"] == T0 + 900 and e["payload"]["portfolio"] == HAIKU
    ]
    assert d["parse_error"]
    extra[HAIKU_MODEL] = {}
    w.advance(T0 + 1500)
    w.w.tick(T0 + 1500)
    assert len(private_rounds(w)) == 1
    w.advance(T0 + 1800)
    w.w.tick(T0 + 1800)
    assert HAIKU in private_rounds(w)[-1]["portfolios"]


def test_the_prompt_states_the_cadence_and_the_wakeup_bounds():
    from arena.perp.agent import PROMPT_PATH, WAKEUP_MAX_MIN, WAKEUP_MIN_MIN

    text = PROMPT_PATH.read_text(encoding="utf-8")
    assert PROMPT_PATH.name == "v8.md"
    assert f"every {CONFIG.cadence_min} minutes" in text
    assert f"from {WAKEUP_MIN_MIN} to {WAKEUP_MAX_MIN}" in text and WAKEUP_MAX_MIN == 60
    assert "often the best" not in text  # the bias against trading is gone


def test_last_played_counts_a_skipped_round():
    from arena.perp.round_quota import last_played

    ev = [
        {"type": "round_data", "ts": 100, "payload": {"portfolio": HAIKU, "round": 1}},
        {"type": "perp_llm_skipped", "ts": 400, "payload": {"portfolio": HAIKU, "round": 2, "reason": "x"}},
        {"type": "round_data", "ts": 900, "payload": {"portfolio": "other", "round": 3}},
    ]
    assert last_played(ev, HAIKU) == 400 and last_played(ev, "nobody") is None


def test_the_ten_minute_cadence_of_the_config(tmp_path):
    league = dataclasses.replace(CONFIG, rounds_per_day=48)
    w, calls, _ = cadenced_world(tmp_path, {HAIKU_MODEL: 30}, league=league)
    w.advance(T0 + 300)
    w.w.tick(T0 + 300)
    assert not private_rounds(w)
    w.advance(T0 + 600)
    w.w.tick(T0 + 600)  # 10 min after 00:02, within the tick; Haiku's 30 min do not delay it
    [rnd] = private_rounds(w)
    assert rnd["portfolios"] == sorted(NAMES) and len(calls) == 8
    assert {t["every_min"] for t in rnd["triggers"].values()} == {10}
