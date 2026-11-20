"""Retiring a solo model of the LLM league (it is archived)."""

from __future__ import annotations

import dataclasses

import pytest

from arena.perp.agent import AgentDecider
from arena.perp.ledger import replay
from arena.perp.llm_league import LlmLeague
from arena.perp.watcher import retired_portfolios
from tests.test_perp_agent import fake_runner
from tests.test_perp_council import BASE, HAIKU, payloads
from tests.test_perp_watcher import SPECS, T0, World

FABLE = "llm-perp:claude-fable-5-2"
SONNET = "llm-perp:claude-sonnet-5-5"


def _world(tmp_path, monkeypatch, *, position: bool = True, league=None):
    import arena.perp.watcher as W

    monkeypatch.setattr(W, "load_specs", lambda var, symbols, now_ts, client=None: SPECS)
    w = World(tmp_path, llm=league or dataclasses.replace(BASE, models=BASE.models[:1]))
    sim = w.w.sim
    sim.open_portfolio(HAIKU, "llm", T0)
    px = w.prices["PF_XBTUSD"]
    if position:
        sim.market_order("m-open", HAIKU, "PF_XBTUSD", 2_000_000, (px, px + 1_000_000), (1_100_000, 1_100_100), T0 + 30)
        sim.set_conditional(HAIKU, "PF_XBTUSD", "stop", px * 95 // 100, T0 + 31)
    sim.append_event(
        "agent_orders_set",
        {
            "portfolio": HAIKU, "round": T0, "created_ts": T0 + 40, "rejected": [], "entry_orders": [],
            "alerts": [{"id": "a1", "instrument": "PF_XBTUSD", "condition": "below", "price_uusd": px * 9 // 10,
                        "note": "", "expires_ts": T0 + 86_400}],
        },
        T0 + 40,
    )  # fmt: skip
    return w


def test_retire_a_solo_model_flattens_journals_and_replays(tmp_path, monkeypatch):
    from arena.perp.retired import retired_portfolio

    w = _world(tmp_path, monkeypatch)
    out = retired_portfolio(w.var, HAIKU, T0 + 120, reason="archive", note="free text")
    assert out == {"status": "retired", "fills": 1, "orders_ended": 1}
    [fill] = [p for p in payloads(w, "perp_fill", HAIKU) if p["reason"] == "retired"]
    assert fill["qty"] == -2_000_000
    [ended] = payloads(w, "agent_order_ended", HAIKU)
    assert ended["reason"] == "portfolio_retired"
    assert [e["type"] for e in w.events()][-1] == "portfolio_retired"
    acc = replay(w.events())[HAIKU]
    assert acc.retired and acc.retired_ts == T0 + 120 and not acc.positions and acc.invariant_ok()
    px = w.prices["PF_XBTUSD"]
    with pytest.raises(Exception, match="retired"):
        w.w.sim.market_order("again", HAIKU, "PF_XBTUSD", 1_000_000, (px, px + 1_000_000), (1_100_000, 1_100_100), T0 + 200)


def test_retire_a_solo_model_is_idempotent_and_fails_closed(tmp_path, monkeypatch):
    from arena.perp.retired import RetiredError, retired_portfolio

    w = _world(tmp_path, monkeypatch)
    n = len(w.events())
    with pytest.raises(RetiredError, match="no fresh quote"):
        retired_portfolio(w.var, HAIKU, T0 + 5_000)
    assert len(w.events()) == n and not replay(w.events())[HAIKU].retired
    retired_portfolio(w.var, HAIKU, T0 + 120)
    n = len(w.events())
    assert retired_portfolio(w.var, HAIKU, T0 + 500) == {"status": "already_retired", "fills": 0, "orders_ended": 0}
    assert len(w.events()) == n


def test_retire_refuses_benchmarks_and_never_opened(tmp_path, monkeypatch):
    from arena.perp.retired import RetiredError, retired_portfolio

    w = _world(tmp_path, monkeypatch)
    with pytest.raises(RetiredError, match="only a council"):
        retired_portfolio(w.var, "benchmark-perp:basket-1x", T0 + 120)
    with pytest.raises(RetiredError, match="never opened"):
        retired_portfolio(w.var, FABLE, T0 + 120)


def test_retire_cli_for_a_model(tmp_path, monkeypatch, capsys):
    from arena.perp.retired import main

    w = _world(tmp_path, monkeypatch, position=False)
    assert main(["--portfolio", HAIKU, "--var", str(w.var), "--reason", "archive", "--note", "17/11"]) == 0
    assert "retired (0 position(s) flattened, 1 order(s) ended)" in capsys.readouterr().out
    assert main(["--portfolio", HAIKU, "--var", str(w.var)]) == 0
    assert "already retired" in capsys.readouterr().out
    assert main(["--portfolio", "nope", "--var", str(w.var)]) == 3
    [ev] = w.events("portfolio_retired")
    assert ev["payload"]["reason"] == "archive" and ev["payload"]["note"] == "17/11"


def test_a_retired_model_is_skipped_by_every_round_even_if_listed(tmp_path, monkeypatch):
    two = dataclasses.replace(BASE, models=BASE.models[:2], cadence_min=10, wakeups=True)
    assert two.without(frozenset()) is two
    assert [m.portfolio for m in two.without({HAIKU}).models] == [SONNET]
    assert isinstance(two.without({HAIKU}), LlmLeague)
    w = _world(tmp_path, monkeypatch, position=False, league=two)
    w.w.sim.append_event("portfolio_retired", {"portfolio": HAIKU, "ts": T0 + 60, "reason": "archive", "note": ""}, T0 + 60)
    assert retired_portfolios(w.events()) == {HAIKU}
    called: list[str] = []
    plain = fake_runner("normal", None)

    def counted(cmd, stdin, env, cwd, timeout):
        called.append(cmd[cmd.index("--model") + 1])
        return plain(cmd, stdin, env, cwd, timeout)

    w.w.decider_factory = lambda m: AgentDecider(
        m.model, m.portfolio, tmp_path / "claude-empty", runner=counted, effort=BASE.effort
    )
    rep = w.w.tick(T0 + 120)  # the file still lists Haiku: the scheduled rounds and the cadence never call it
    assert not rep.problems, rep.problems
    assert set(called) == {"claude-sonnet-5-5"}
    assert not payloads(w, "agent_decision", HAIKU) and not payloads(w, "perp_llm_skipped", HAIKU)
    assert not [p for p in payloads(w, "perp_equity", HAIKU) if p["ts"] > T0 + 60]  # no more measure either
    assert payloads(w, "agent_decision", SONNET)
