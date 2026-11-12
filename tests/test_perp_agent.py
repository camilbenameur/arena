"""Perp league, step 5: the agent loop (round data, MCP server, claude -p stream, decision, journal). No model:
a fake `claude` (tests/fake_claude.py) starts the round's REAL MCP server and calls its tools."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from arene.perp import indicators as ind
from arene.perp.agent import (
    DEFAULT_WORKDIR,
    INSTRUMENTS,
    OUTPUT_SCHEMA,
    TIMEOUT_RC,
    AgentDecider,
    _default_runner,
    canonical_json,
    parse_decision,
    parse_stream,
)
from arene.perp.agent_round import run_agent_round
from arene.perp.ledger import replay
from arene.perp.market import market_view
from arene.perp.mcp_server import RESPONSE_MAX_CHARS, RoundTools
from arene.perp.riskd import evaluate_perp
from arene.perp.round_data import market_block
from arene.perp.types import BookSnapshot, OpenInterest
from tests.test_perp_watcher import CFG, POLICY, SPECS, SYMBOLS, T0, World

FAKE = Path(__file__).parent / "fake_claude.py"
LLM = "llm-perp:claude-test"


def fake_runner(mode: str = "normal"):
    def run(cmd, stdin, env, cwd, timeout):
        p = subprocess.run(
            [sys.executable, str(FAKE), *cmd[1:]],
            input=stdin,
            check=False,
            capture_output=True,
            text=True,
            env={**env, "FAKE_CLAUDE_MODE": mode},
            cwd=cwd,
            timeout=timeout,
        )
        return p.returncode, p.stdout.splitlines(), p.stderr

    return run


def league(tmp_path: Path) -> World:
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    w.w.sim.open_portfolio(LLM, "llm", T0 + 130)
    return w


def round_for(w: World, mode: str = "normal", now: int = T0 + 140, runner=None, blocked=False, round_id=T0):
    view = market_view(w.store, SYMBOLS, now)
    decider = AgentDecider(
        "claude-haiku-5-5", LLM, w.var / "claude-empty", runner=runner or fake_runner(mode)
    )
    res = run_agent_round(
        var=w.var,
        sim=w.w.sim,
        store=w.store,
        decider=decider,
        view=view,
        specs=SPECS,
        policy=POLICY,
        config_sha256=CFG.sha256,
        round_id=round_id,
        now_ts=now,
        kind="rendezvous",
        trigger=None,
        entries_blocked=blocked,
    )
    return res, w.events()


def test_full_round_with_tools_decision_and_execution(tmp_path):
    w = league(tmp_path)
    res, events = round_for(w)
    assert res.error is None and res.mcp_status == "connected"
    calls = [e["payload"] for e in events if e["type"] == "tool_call"]
    assert [c["tool"] for c in calls] == ["derives", "simuler_ordre"]
    assert all(isinstance(c["response"], str) and isinstance(c["arguments"], str) for c in calls)
    assert all(hashlib.sha256(c["response"].encode()).hexdigest() == c["response_sha256"] for c in calls)
    dec = next(e["payload"] for e in events if e["type"] == "agent_decision")
    assert dec["parse_error"] is None and dec["cost_uusd"] == 12_346 and dec["input_tokens"] == 1200
    assert dec["parsed"]["actions"][0]["invalidation"] == "clôture 4 h sous 68000"
    verdicts = [
        e["payload"] for e in events if e["type"] == "perp_verdict" and e["payload"]["portfolio"] == LLM
    ]
    assert len(verdicts) == 1 and verdicts[0]["approved"]
    pos = replay(events)[LLM].positions["PF_XBTUSD"]
    assert pos.qty > 0 and pos.stop_uusd is not None and pos.take_profit_uusd is not None
    # the round's data are frozen and journaled by their sha256
    rd = next(e["payload"] for e in events if e["type"] == "round_data")
    raw = (w.var / rd["path"] / "round.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == rd["sha256"]
    assert len((w.var / rd["path"] / "trace.jsonl").read_text().splitlines()) == 2


def test_simulate_order_tool_equals_the_final_verdict(tmp_path):
    w = league(tmp_path)
    round_for(w)
    rd = next(e["payload"] for e in w.events() if e["type"] == "round_data")
    tools = RoundTools(w.var / rd["path"], LLM, 4)
    out, err = tools.call(
        "simuler_ordre",
        {
            "instrument": "PF_ETHUSD",
            "action": "open_short",
            "size_pct": Decimal("10.5"),
            "stop_pct": 4,
            "horizon_h": 24,
            "expected_move_pct": 5,
        },
    )
    assert not err
    v = evaluate_perp(
        __import__("arene.perp.riskd", fromlist=["PerpIntent"]).PerpIntent(
            "simulation", LLM, T0 + 140, "PF_ETHUSD", "open_short", size_bp=1050, stop_bp=400, horizon_h=24, expected_move_bp=500
        ),
        tools._account(), tools._view(), tools._specs(), tools._counters(), tools._policy(),
        CFG.simulation, T0 + 140, False,
    )  # fmt: skip
    assert out["approuve"] == v.approved and out["codes_de_refus"] == list(v.reasons)


def test_tool_budget_and_bad_arguments(tmp_path):
    w = league(tmp_path)
    _res, events = round_for(w, "five_tools")
    calls = [e["payload"] for e in events if e["type"] == "tool_call"]
    assert len(calls) == 5 and calls[-1]["is_error"] and "budget" in calls[-1]["response"]
    rd = next(e["payload"] for e in events if e["type"] == "round_data")
    tools = RoundTools(w.var / rd["path"], LLM, 4)
    assert tools.call("bougies", {"instrument": "PF_DOGEUSD", "intervalle": "1h"})[1]
    assert tools.call("rien", {})[1]
    with pytest.raises(ValueError):
        RoundTools(w.var / rd["path"], "someone-else", 4)


def test_no_result_is_no_decision_and_never_retried_after_a_tool(tmp_path):
    w = league(tmp_path)
    _res, events = round_for(w, "no_result")
    dec = next(e["payload"] for e in events if e["type"] == "agent_decision")
    assert dec["parsed"] is None and dec["parse_error"] and dec["tool_calls"] == 2
    assert len([e for e in events if e["type"] == "tool_call"]) == 2  # one attempt only
    assert LLM not in {e["payload"]["portfolio"] for e in events if e["type"] == "perp_fill"}


def test_mcp_server_not_connected_means_no_decision(tmp_path):
    w = league(tmp_path)
    res, _events = round_for(w, "mcp_failed")
    assert res.decision is None and "not connected" in res.error


def test_parse_decision_rules():
    ok = {
        "actions": [
            {
                "instrument": "PF_XBTUSD",
                "action": "open_long",
                "size_pct": 20,
                "stop_pct": 3,
                "expected_move_pct": 6,
            }
        ],
        "justification": "j",
    }
    _parsed, err, intents = parse_decision(json.dumps(ok), "p", 1, 2)
    assert err is None and intents[0].size_bp == 2000 and intents[0].stop_bp == 300
    for bad in ({"actions": [ok["actions"][0]] * 3, "justification": ""}, "not json", [], {"actions": 1}):
        assert parse_decision(bad, "p", 1, 2)[1], bad
    # one invalid action is dropped alone: a close in the same decision is kept
    close = {"instrument": "PF_ETHUSD", "action": "close"}
    for bad_action in (
        {**ok["actions"][0], "extra": 1},
        {**ok["actions"][0], "size_pct": -1},
        {**ok["actions"][0], "action": "buy"},
        {**ok["actions"][0], "size_pct": "NaN"},
        {**ok["actions"][0], "size_pct": True},
        {**ok["actions"][0], "horizon_h": 0},
        {**ok["actions"][0], "horizon_h": 48.5},
        {**ok["actions"][0], "confidence_pct": 101},
        {**ok["actions"][0], "instrument": "PF_DOGEUSD"},
        {**ok["actions"][0], "stop_pct": "1e999999999"},
    ):
        parsed, err, its = parse_decision({"actions": [bad_action, close], "justification": ""}, "p", 1, 2)
        assert err is None and [i.action for i in its] == ["close"], bad_action
        assert len(parsed["action_errors"]) == 1 and parsed["action_errors"][0]["k"] == 0
    # the same decision gives the same intent ids (idempotent replays)
    assert parse_decision(ok, "p", 1, 2)[2][0].intent_id == intents[0].intent_id


def test_command_and_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    d = AgentDecider("claude-sonnet-5-5", LLM, tmp_path)
    cmd = d.command(tmp_path / "mcp.json")
    for flag in ("--strict-mcp-config", "--no-session-persistence", "--verbose"):
        assert flag in cmd
    assert cmd[cmd.index("--tools") + 1] == "" and cmd[cmd.index("--allowedTools") + 1] == "mcp__arene__*"
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == OUTPUT_SCHEMA
    assert "--disable-slash-commands" in cmd and cmd[cmd.index("--max-budget-usd") + 1] == "1.00"
    env = d.env()
    assert "ANTHROPIC_API_KEY" not in env and env["ENABLE_TOOL_SEARCH"] == "false"
    for var in (
        "CLAUDE_CODE_DISABLE_CLAUDE_MDS",
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY",
        "CLAUDE_CODE_DISABLE_BUNDLED_SKILLS",
    ):
        assert env[var] == "1"
    # the schema bounds what the local validation bounds
    item = OUTPUT_SCHEMA["properties"]["actions"]["items"]["properties"]
    assert item["instrument"]["enum"] == list(INSTRUMENTS) and item["horizon_h"]["maximum"] == 168
    # the default working directory is outside any repository
    assert not any((p / ".git").exists() for p in [DEFAULT_WORKDIR, *DEFAULT_WORKDIR.parents])


def test_parse_stream_ignores_other_tools_and_floats_never_appear():
    lines = [
        json.dumps(
            {"type": "system", "subtype": "init", "mcp_servers": [{"name": "arene", "status": "connected"}]}
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "id": "a", "name": "Bash", "input": {}}]},
            }
        ),
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "structured_output": {"actions": [], "justification": ""},
                "total_cost_usd": 0.1,
                "usage": {},
            }
        ),
    ]
    res = parse_stream(lines)
    assert (
        res.tool_calls == []
        and res.decision == {"actions": [], "justification": ""}
        and res.cost_uusd == 100_000
    )


def test_indicators_are_integers_and_sane():
    closes = [100_000_000 + 1_000_000 * (i % 7) - 500_000 * (i % 3) for i in range(60)]
    candles = [(c, c + 200_000, c - 200_000, c) for c in closes]
    s = ind.summary(candles)
    assert all(v is None or type(v) is int for v in s.values())
    assert (
        0 <= s["rsi_14_bp"] <= 10_000
        and s["atr_14_uusd"] > 0
        and s["bollinger_lower_uusd"] < s["bollinger_upper_uusd"]
    )
    assert ind.ema([10] * 30, 20) == 10 and ind.rsi_bp(list(range(1, 30))) == 10_000
    assert ind.sma([1, 2], 3) is None


# ---------------------------------------------------------------------- review of step 5


def _rpc_session(round_dir: Path, lines: list[str]) -> list[dict]:
    p = subprocess.run(
        [sys.executable, "-m", "arene.perp.mcp_server", "--round-dir", str(round_dir), "--portfolio", LLM],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        cwd=Path(__file__).parent.parent,
    )
    assert p.returncode == 0, p.stderr
    return [json.loads(x) for x in p.stdout.splitlines()]


def _call(i: int, name: str, args) -> str:
    return json.dumps(
        {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}
    )


def test_the_mcp_server_survives_any_input(tmp_path):
    w = league(tmp_path)
    round_for(w)
    rd = next(e["payload"] for e in w.events() if e["type"] == "round_data")
    d = w.var / rd["path"]
    lines = [
        json.dumps(
            {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}}
        ),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        (
            '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"simuler_ordre","arguments":'
            '{"instrument":"PF_XBTUSD","action":"open_long","size_pct":1e999999999}}}'
        ),
        (
            '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"simuler_ordre","arguments":'
            '{"instrument":"PF_XBTUSD","action":"open_long","size_pct":1e30,"stop_pct":3}}}'
        ),
        "not json",
        json.dumps({"jsonrpc": "2.0", "id": None, "method": "ping"}),
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}),
    ]
    out = _rpc_session(d, lines)
    by_id = {r.get("id"): r for r in out}
    assert by_id[0]["result"]["protocolVersion"] == "2025-06-18"
    assert by_id[1]["result"]["isError"] and by_id[2]["result"]["isError"]
    assert any(r.get("error", {}).get("code") == -32700 for r in out)
    assert len(by_id[3]["result"]["tools"]) == 6  # still alive after every bad input
    tools = RoundTools(d, LLM, 20)
    for name, args in (
        ("bougies", {"instrument": "PF_XBTUSD", "intervalle": "1h", "n": 48.5}),
        ("bougies", {"instrument": "PF_XBTUSD", "intervalle": "2h"}),
        ("bougies", {"instrument": "PF_XBTUSD", "intervalle": "1h", "x": 1}),
        ("simuler_ordre", {"instrument": "PF_XBTUSD", "action": "open_long", "horizon_h": 10**30}),
        ("historique", "pas un objet"),
    ):
        payload, err = tools.call(name, args)
        assert err and "arguments invalides" in payload["erreur"] and "Python" not in payload["erreur"], args


def test_tool_responses_stay_small(tmp_path):
    w = league(tmp_path)
    for k in range(15):  # a long history with long justifications
        w.w.sim.append_event(
            "agent_decision",
            {"portfolio": LLM, "round": k, "parsed": {"actions": [{"instrument": "PF_XBTUSD", "action": "close",
             "invalidation": "x" * 200}], "justification": "j" * 1200}, "parse_error": None},
            T0 + 130,
        )  # fmt: skip
    round_for(w)
    rd = next(e["payload"] for e in w.events() if e["type"] == "round_data")
    tools = RoundTools(w.var / rd["path"], LLM, 20)
    for name, args in (
        ("historique", {"n": 10}),
        ("bougies", {"instrument": "PF_XBTUSD", "intervalle": "5m", "n": 24}),
        ("indicateurs", {"instrument": "PF_XBTUSD", "intervalle": "5m"}),
        ("derives", {"instrument": "PF_XBTUSD"}),
        ("simuler_ordre", {"instrument": "PF_XBTUSD", "action": "open_long", "size_pct": 10, "stop_pct": 3,
                           "horizon_h": 24, "expected_move_pct": 5}),
    ):  # fmt: skip
        payload, err = tools.call(name, args)
        assert not err and len(json.dumps(payload, ensure_ascii=False)) <= RESPONSE_MAX_CHARS, name


def test_empty_book_side_and_closed_open_interest(tmp_path):
    w = league(tmp_path)
    now = T0 + 140
    w.store.books("PF_XBTUSD").add([BookSnapshot("PF_XBTUSD", now - 60, (), ((1, 1),), False)])
    oi = w.store.open_interest("PF_XBTUSD", 3600)
    oi.add(
        [
            OpenInterest("PF_XBTUSD", 3600, h, 5, 5, 5, h)
            for h in (now // 3600 * 3600 - 3600, now // 3600 * 3600)
        ]
    )
    m = market_block(w.store, "PF_XBTUSD", now)
    assert [ts for ts, _ in m["open_interest"]] == [
        now // 3600 * 3600 - 3600
    ]  # the current hour is not closed
    round_for(w)
    rd = next(e["payload"] for e in w.events() if e["type"] == "round_data")
    payload, err = RoundTools(w.var / rd["path"], LLM, 4).call("carnet", {"instrument": "PF_XBTUSD"})
    assert not err and payload["carnet"] is None


def test_a_round_is_played_once(tmp_path):
    w = league(tmp_path)
    round_for(w)
    res, events = round_for(w)
    assert "already played" in res.error
    assert len([e for e in events if e["type"] == "agent_decision"]) == 1
    rd = next(e["payload"] for e in events if e["type"] == "round_data")
    assert rd["message_sha256"] and rd["trigger"] == "null"
    dec = next(e["payload"] for e in events if e["type"] == "agent_decision")
    assert (
        dec["attempts"] == 1
        and dec["cli_rc"] == 0
        and dec["stream_sha256"]
        and dec["mcp_status"] == "connected"
    )
    stream = (w.var / rd["path"] / "stream.jsonl").read_bytes()
    assert hashlib.sha256(stream).hexdigest() == dec["stream_sha256"]


def test_kill_switch_is_read_again_after_the_call(tmp_path):
    w = league(tmp_path)
    reads = iter([False, True, True, True])
    _res, events = round_for(w, blocked=lambda: next(reads))
    v = next(e["payload"] for e in events if e["type"] == "perp_verdict" and e["payload"]["portfolio"] == LLM)
    assert not v["approved"]
    assert LLM not in {e["payload"]["portfolio"] for e in events if e["type"] == "perp_fill"}


def test_a_position_never_stays_without_a_stop(tmp_path, monkeypatch):
    w = league(tmp_path)
    real = w.w.sim.set_conditional

    def broken(portfolio, instrument, kind, price, ts):
        if kind == "stop":
            raise OSError("disk full")
        return real(portfolio, instrument, kind, price, ts)

    monkeypatch.setattr(w.w.sim, "set_conditional", broken)
    _res, events = round_for(w)
    ex = next(e["payload"] for e in events if e["type"] == "perp_execution")
    assert ex["status"] == "closed_without_stop"
    assert "PF_XBTUSD" not in replay(events)[LLM].positions
    assert any(
        e["payload"].get("code") == "perp_position_without_stop" for e in events if e["type"] == "alert"
    )


def _result_line(cost: str, subtype: str = "success", out=None) -> str:
    return json.dumps({"type": "result", "subtype": subtype, "is_error": subtype != "success", "num_turns": 3,
                       "structured_output": out, "total_cost_usd": Decimal(cost), "usage": {"input_tokens": 10}},
                      default=str).replace('"' + cost + '"', cost)  # fmt: skip


def test_retry_only_after_a_transport_failure(tmp_path):
    calls = []

    def runner(results):
        def run(cmd, stdin, env, cwd, timeout):
            calls.append(1)
            return results[len(calls) - 1]

        return run

    d = tmp_path / "r"
    d.mkdir()
    # an error result (turn limit) costs tokens: never retried
    calls.clear()
    res = AgentDecider(
        "m", LLM, tmp_path / "w", runner=runner([(1, [_result_line("0.02", "error_max_turns")], "")])
    ).decide(d, {})
    assert len(calls) == 1 and res.attempts == 1 and res.cost_uusd == 20_000 and res.decision is None
    # a transport failure (no result event): one retry, costs summed, first error kept
    calls.clear()
    ok = {"actions": [], "justification": "rien"}
    res = AgentDecider(
        "m",
        LLM,
        tmp_path / "w",
        max_attempts=2,
        runner=runner([(1, [], "boom"), (0, [_result_line("0.01", out=ok)], "")]),
    ).decide(d, {})
    assert (
        len(calls) == 2
        and res.attempts == 2
        and res.decision == ok
        and res.first_error
        and res.cost_uusd == 10_000
    )
    # a single paid call (5-bis): never a second one
    calls.clear()
    res = AgentDecider("m", LLM, tmp_path / "w", max_attempts=1, runner=runner([(1, [], "boom")])).decide(
        d, {}
    )
    assert len(calls) == 1 and res.error


def test_a_timeout_keeps_the_partial_stream(tmp_path):
    script = tmp_path / "slow.py"
    tool_use = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "a",
                    "name": "mcp__arene__derives",
                    "input": {"instrument": "PF_XBTUSD"},
                }
            ]
        },
    }
    tool_result = {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "a", "content": "{}", "is_error": False}]}}  # fmt: skip
    script.write_text(
        "import json, sys, time\n"
        f"print(json.dumps({tool_use!r}), flush=True)\n"
        f"print(json.dumps({tool_result!r}), flush=True)\n"
        "time.sleep(60)\n"
    )

    def runner(cmd, stdin, env, cwd, timeout):
        return _default_runner([sys.executable, str(script)], stdin, env, cwd, timeout)

    d = tmp_path / "r"
    d.mkdir()
    res = AgentDecider("m", LLM, tmp_path / "w", runner=runner, timeout_s=3).decide(d, {})
    assert res.rc == TIMEOUT_RC and "timeout" in res.error and res.attempts == 1
    assert [c.tool for c in res.tool_calls] == ["derives"]


def test_pending_mcp_with_a_tool_answer_keeps_the_decision_and_arguments_keep_their_numbers():
    lines = [
        json.dumps({"type": "system", "subtype": "init", "mcp_servers": [{"name": "arene", "status": "pending"}]}),
        (
            '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"a","name":"mcp__arene__simuler_ordre",'
            '"input":{"size_pct":20.50,"instrument":"PF_XBTUSD"}}]}}'
        ),
        json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "a", "content": "{}"}]}}),
        json.dumps({"type": "result", "subtype": "success", "is_error": False, "structured_output": {"actions": [], "justification": ""}}),
    ]  # fmt: skip
    res = parse_stream(lines)
    assert (
        res.decision is not None
        and res.tool_calls[0].arguments == '{"instrument":"PF_XBTUSD","size_pct":20.50}'
    )
    assert canonical_json({"b": [Decimal("1.0"), None, True], "a": "é"}) == '{"a":"é","b":[1.0,null,true]}'
    res = parse_stream([lines[0], lines[3]])
    assert res.decision is None and "not connected" in res.error


def test_no_retry_once_the_model_answered_and_env_is_whitelisted(tmp_path, monkeypatch):
    calls = []
    answered = json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "..."}]}})

    def run(cmd, stdin, env, cwd, timeout):
        calls.append(env)
        return 1, [answered], "cut"

    d = tmp_path / "r"
    d.mkdir()
    for k in (
        "CLAUDECODE",
        "CLAUDE_CODE_SESSION_ID",
        "CLAUDE_EFFORT",
        "ANTHROPIC_BASE_URL",
        "MCP_SERVER_CONNECTION_BATCH_SIZE",
    ):
        monkeypatch.setenv(k, "x")
    res = AgentDecider("m", LLM, tmp_path / "w", runner=run, max_attempts=2).decide(d, {})
    assert len(calls) == 1 and res.error  # the quota was used: never a second call
    env = calls[0]
    assert not [
        k
        for k in env
        if k.startswith(("CLAUDECODE", "ANTHROPIC"))
        or k in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_EFFORT", "MCP_SERVER_CONNECTION_BATCH_SIZE")
    ]
    assert env["HOME"] and env["PATH"]
    assert (d / "stream.jsonl").read_text() == answered
    assert "--effort" not in AgentDecider("m", LLM, tmp_path, effort=None).command(tmp_path / "x.json")


def test_malformed_stream_lines_never_crash():
    lines = ["123", "null", "[1]", '{"type":"user","message":{"content":"hi"}}',
             '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"a","name":"mcp__arene__bougies","input":{"n":1e99999999999999999999}}]}}',
             '{"type":"result","subtype":"success","is_error":false,"total_cost_usd":"abc","structured_output":{"actions":[],"justification":""}}']  # fmt: skip
    res = parse_stream(lines)
    assert res.cost_uusd == 0 and res.error == "unreadable total_cost_usd" and res.tool_calls == []


def test_round_survives_a_crashing_decider_and_a_failing_fill(tmp_path, monkeypatch):
    w = league(tmp_path)

    def crash(cmd, stdin, env, cwd, timeout):
        raise RuntimeError("bug")

    res, events = round_for(w, runner=crash)
    dec = next(e["payload"] for e in events if e["type"] == "agent_decision")
    assert "decider crashed" in dec["parse_error"] and "crashed" in res.error
    w2 = league(tmp_path / "b")
    real = w2.w.sim.market_order

    def failing(order_id, portfolio, *a, **k):
        if portfolio == LLM:
            raise OSError("disk")
        return real(order_id, portfolio, *a, **k)

    monkeypatch.setattr(w2.w.sim, "market_order", failing)
    _res, events = round_for(w2)
    ex = next(e["payload"] for e in events if e["type"] == "perp_execution")
    assert ex["status"] == "error" and "OSError" in ex["error"]


def test_an_unprotected_position_is_reported_open_and_closed_at_the_next_tick(tmp_path, monkeypatch):
    w = league(tmp_path)
    real_cond, real_order = w.w.sim.set_conditional, w.w.sim.market_order

    def no_stop(portfolio, instrument, kind, price, ts):
        if kind == "stop":
            raise OSError("disk")
        return real_cond(portfolio, instrument, kind, price, ts)

    def no_close(order_id, *a, **k):
        if order_id.endswith(":no-stop"):
            raise OSError("disk")
        return real_order(order_id, *a, **k)

    monkeypatch.setattr(w.w.sim, "set_conditional", no_stop)
    monkeypatch.setattr(w.w.sim, "market_order", no_close)
    _res, events = round_for(w)
    ex = next(e["payload"] for e in events if e["type"] == "perp_execution")
    assert ex["status"] == "unprotected_position_open" and "PF_XBTUSD" in replay(events)[LLM].positions
    monkeypatch.undo()
    w.advance(T0 + 600)
    w.w.tick(T0 + 600)
    events = w.events()
    assert "PF_XBTUSD" not in replay(events)[LLM].positions
    assert any(e["payload"].get("reason") == "no_stop" for e in events if e["type"] == "perp_fill")


def test_first_call_guards():
    from arene.perp.first_call import check_init, spot_cycle_too_close

    day = 20_000 * 86_400
    assert spot_cycle_too_close(day + 4 * 3600 + 5 * 60 - 19 * 60)  # 19 min before 04:05
    assert spot_cycle_too_close(day + 4 * 3600 + 5 * 60 + 29 * 60)  # 29 min after
    assert spot_cycle_too_close(day + 2 * 3600) is None
    assert spot_cycle_too_close(day - 60)  # 23:59, before 00:05 of the next day
    good = {
        "mcp_servers": [{"name": "arene", "status": "connected"}],
        "tools": ["StructuredOutput", *(f"mcp__arene__{t}" for t in ("bougies", "carnet", "derives",
                                                                     "indicateurs", "simuler_ordre", "historique"))],
        "permissionMode": "dontAsk", "model": "m", "apiKeySource": "none", "agents": ["Explore"],
    }  # fmt: skip
    assert check_init(good, "m") == []
    assert check_init({**good, "tools": [*good["tools"], "Bash"]}, "m")
    assert check_init({**good, "apiKeySource": "ANTHROPIC_API_KEY"}, "m")
    assert check_init({**good, "plugins": [{"name": "x"}]}, "m")
    assert check_init(None, "m")
