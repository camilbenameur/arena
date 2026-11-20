"""Retirement of a model from the scored league (`arena retired`): sale at the bid, journal, never played again."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

import pytest

from arena import cli
from arena.cycle import run_cycle
from arena.journal import Journal, verify
from arena.ledger import replay, retired_portfolios
from arena.retired import RetiredError, retired_portfolio
from arena.types import Quote
from arena.watch import run_watch
from tests.fakes import HAIKU, OPUS, SONNET, Env, ScriptedDecider, action, make_deciders

FABLE = "llm:claude-fable-5-2"


def hold(idx: int, snap: dict):
    return [action("BTC/EUR"), action("ETH/EUR")] if idx == 0 else None


class Counting(ScriptedDecider):
    calls = 0

    def decide(self, snapshot: dict, spent_today_uusd: int):
        type(self).calls += 1
        return super().decide(snapshot, spent_today_uusd)


def events(env: Env) -> list[dict]:
    return Journal(env.paths.journal).events()


def of(env: Env, t: str, portfolio: str | None = None) -> list[dict]:
    return [e for e in events(env) if e["type"] == t and (portfolio is None or e["payload"].get("portfolio") == portfolio)]


@pytest.fixture
def env(tmp_path: Path) -> Env:
    e = Env(tmp_path)
    e.clock.now = e.now_of(0)
    run_cycle(e.paths, e.clients, e.clock.now, deciders=make_deciders(hold))
    assert replay(events(e))[HAIKU].positions
    e.clock.now = e.now_of(0) + 1800  # half an hour later, outside a cycle
    return e


def test_retired_sells_all_at_bid_journals_and_replays(env: Env):
    before = replay(events(env))[HAIKU]
    out = retired_portfolio(env.paths, env.clients, HAIKU, env.clock.now, reason="archive", note="free text")
    assert out["status"] == "retired" and out["fills"] == len(before.positions) == 2
    sells = [e["payload"] for e in of(env, "fill", HAIKU) if e["payload"]["reason"] == "retired"]
    assert {v["symbol"] for v in sells} == set(before.positions) and all(v["side"] == "sell" for v in sells)
    [ev] = of(env, "portfolio_retired")
    p = ev["payload"]
    assert p["portfolio"] == HAIKU and p["ts"] == env.clock.now and p["reason"] == "archive" and p["note"] == "free text"
    assert p["fills"] == 2 and set(p["quotes"]) == set(before.positions)
    after = replay(events(env))[HAIKU]
    assert not after.positions and after.cash_ueur == p["equity_ueur"] == out["equity_ueur"]
    assert events(env)[-1]["type"] == "portfolio_retired" and verify(env.paths.journal).ok
    assert retired_portfolios(events(env)) == {HAIKU}
    # no `quote` event written outside a cycle (the site would attach it to the previous cycle)
    assert not [e for e in events(env) if e["type"] == "quote" and e["ts"] == env.clock.now]
    # the other portfolios are untouched
    assert replay(events(env))["benchmark:basket"].positions


def test_retired_is_idempotent(env: Env):
    retired_portfolio(env.paths, env.clients, HAIKU, env.clock.now)
    n = len(events(env))
    out = retired_portfolio(env.paths, env.clients, HAIKU, env.clock.now + 600)
    assert out["status"] == "already_retired" and out["fills"] == 0 and len(events(env)) == n


def test_retired_closed_without_a_valid_quote_writes_nothing(env: Env, monkeypatch: pytest.MonkeyPatch):
    n = len(events(env))
    env.kraken.fail_ticker = True
    with pytest.raises(RetiredError, match="unreadable"):
        retired_portfolio(env.paths, env.clients, HAIKU, env.clock.now)
    assert len(events(env)) == n and replay(events(env))[HAIKU].positions and not retired_portfolios(events(env))
    env.kraken.fail_ticker = False
    monkeypatch.setattr(env.kraken, "ticker", lambda sym, pair: Quote(sym, env.clock.now, 0, 5))  # a zero bid: invalid
    with pytest.raises(RetiredError, match="invalid"):
        retired_portfolio(env.paths, env.clients, HAIKU, env.clock.now)
    assert len(events(env)) == n


def test_retired_refuses_a_benchmark_an_unknown_and_waits_for_the_lock(env: Env):
    with pytest.raises(RetiredError, match="not a benchmark"):
        retired_portfolio(env.paths, env.clients, "benchmark:basket", env.clock.now)
    with pytest.raises(RetiredError, match="only an AI model"):
        retired_portfolio(env.paths, env.clients, "llm:unknown", env.clock.now)
    env.paths.var.mkdir(parents=True, exist_ok=True)
    fd = os.open(env.paths.lock, os.O_CREAT | os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)  # a cycle or a wake-up is running
    try:
        n = len(events(env))
        with pytest.raises(RetiredError, match="cycle lock"):
            retired_portfolio(env.paths, env.clients, HAIKU, env.clock.now, lock_wait_s=0.3)
        assert len(events(env)) == n
    finally:
        os.close(fd)


def test_the_cycle_neither_plays_nor_values_a_retired_portfolio(env: Env):
    retired_portfolio(env.paths, env.clients, HAIKU, env.clock.now)
    Counting.calls = 0
    d = make_deciders(hold)
    d[HAIKU] = Counting("claude-haiku-5-5", HAIKU, lambda i, s: [action("SOL/EUR")])
    for i in (1, 2):
        env.clock.now = env.now_of(i)
        rep = run_cycle(env.paths, env.clients, env.clock.now, deciders=d)
        assert rep.status == "completed" and HAIKU not in rep.equity_ueur and SONNET in rep.equity_ueur
    assert Counting.calls == 0  # never called again
    ev = events(env)
    retired_seq = next(e["seq"] for e in ev if e["type"] == "portfolio_retired")
    after = [e for e in ev if e["seq"] > retired_seq and e["payload"].get("portfolio") == HAIKU]
    assert not after  # no decision, no order, no equity, no skip
    assert [e for e in ev if e["seq"] > retired_seq and e["type"] == "equity" and e["payload"]["portfolio"] == SONNET]
    assert not replay(ev)[HAIKU].positions and verify(env.paths.journal).ok


def test_the_watch_no_longer_values_a_retired_portfolio(env: Env):
    retired_portfolio(env.paths, env.clients, HAIKU, env.clock.now)
    env.clock.now = env.now_of(0) + 2400
    rep = run_watch(env.paths, env.clients, env.clock.now)
    assert rep.status == "done"
    v = of(env, "watch")[-1]["payload"]
    assert HAIKU not in v["equity"] and SONNET in v["equity"] and OPUS in v["equity"] and FABLE in v["equity"]


def run_cli(env: Env, *args: str) -> int:
    ts = env.clock.now
    return cli.main(
        ["--var", str(env.paths.var), "--secrets", str(env.sec), "--config", str(env.paths.config), *args],
        clients=env.clients, now=lambda: ts,
    )


def test_cli_retired_status_and_resume_refused(env: Env, capsys: pytest.CaptureFixture):
    assert run_cli(env, "retired", "benchmark:basket") == 1
    assert run_cli(env, "retired", HAIKU, "--reason", "archive", "--note", "17/11") == 0
    out = capsys.readouterr().out
    assert "retired: 2 position(s) sold" in out
    assert run_cli(env, "retired", HAIKU) == 0 and "already retired" in capsys.readouterr().out
    [ev] = of(env, "portfolio_retired")
    assert ev["payload"]["reason"] == "archive" and ev["payload"]["note"] == "17/11"
    assert run_cli(env, "resume", HAIKU) == 2  # a retired portfolio never plays again
    assert not of(env, "portfolio_resumed")
    capsys.readouterr()
    assert run_cli(env, "status") == 0
    assert "RETIRED" in capsys.readouterr().out


def test_retiring_changes_neither_the_config_nor_the_policy_nor_the_instruction(env: Env):
    from arena import season
    from arena.config import load_config
    from arena.deciders.llm import prompt_sha256
    from arena.risk.policy import load_policy

    before = (load_config(env.paths.config).sha256_outside_season, load_policy(env.paths.policy).sha256, prompt_sha256())
    retired_portfolio(env.paths, env.clients, HAIKU, env.clock.now)
    after = (load_config(env.paths.config).sha256_outside_season, load_policy(env.paths.policy).sha256, prompt_sha256())
    assert before == after  # only the code (cycle, watch, ledger) changes: see `season.FROZEN_CODE_FILES`
    assert "arena/retired.py" not in season.FROZEN_CODE_FILES and "arena/cycle.py" in season.FROZEN_CODE_FILES
