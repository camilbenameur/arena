"""Perp league, step 7: the LLM portfolios inside the watcher (fake `claude`, real MCP server)."""

from __future__ import annotations

import dataclasses
import threading
from pathlib import Path

import pytest

from arene.perp.agent import AgentDecider
from arene.perp.ledger import replay
from arene.perp.llm_league import LlmConfigError, load_llm_league
from tests.test_perp_agent import fake_runner
from tests.test_perp_watcher import T0, World

LEAGUE = load_llm_league()
NAMES = [m.portfolio for m in LEAGUE.models]


def factory(tmp: Path, calls: list, mode: str = "normal"):
    lock = threading.Lock()
    run = fake_runner(mode)

    def counted(cmd, stdin, env, cwd, timeout):
        with lock:
            calls.append(cmd[cmd.index("--model") + 1])
        return run(cmd, stdin, env, cwd, timeout)

    return lambda m: AgentDecider(
        m.model, m.portfolio, tmp / "claude-empty", runner=counted, effort=LEAGUE.effort
    )


def test_the_config_file_is_valid_and_strict(tmp_path):
    assert [m.model for m in LEAGUE.models] == [
        "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2",
    ]  # fmt: skip
    assert LEAGUE.enabled and LEAGUE.wakeups and LEAGUE.max_parallel == 4
    assert [m.daily_budget_uusd for m in LEAGUE.models] == [100_000, 900_000, 1_800_000, 3_500_000]
    bad = tmp_path / "bad.toml"
    raw = Path("config/perp-llm.toml").read_text()
    for old, new in (
        ('"0.10"', "0.10"),
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
    from arene.perp.market import market_view
    from arene.perp.watcher import TickReport

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
    import arene.perp.llm_league as L

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
    import arene.perp.llm_league as L

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
    import arene.perp.llm_league as L

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
    from arene.perp.agent import TIMEOUT_RC, AgentResult
    from arene.perp.llm_league import call_cost_uusd, charge_ceiling

    assert call_cost_uusd({"cost_uusd": 0, "charge_ceiling": True, "budget_ceiling_uusd": 100_000}) == 100_000
    assert call_cost_uusd({"cost_uusd": 5, "charge_ceiling": False, "budget_ceiling_uusd": 100_000}) == 5
    assert charge_ceiling(AgentResult(rc=TIMEOUT_RC))
    assert charge_ceiling(AgentResult(rc=1, assistant_seen=True))
    assert not charge_ceiling(AgentResult(rc=1))  # never reached a model: network, login
    assert not charge_ceiling(AgentResult(rc=0, result_seen=True))


def test_a_network_failure_costs_no_budget(tmp_path):
    from arene.perp.llm_league import spent_today_uusd

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
    import arene.perp.watcher as W

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
    rep = w.w.tick(T0 + 120)  # 16:02 UTC: a spot cycle hour, no perp rendez-vous
    assert rep.rounds == [] and calls == []
    w.advance(T0 + 2 * 3600 + 120)
    rep = w.w.tick(T0 + 2 * 3600 + 120)  # 18:02 UTC
    assert rep.rounds == [f"rendezvous:{T0 + 2 * 3600}"] and len(calls) == 4
