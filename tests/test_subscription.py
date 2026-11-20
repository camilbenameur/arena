"""Decider on the subscription (`claude -p`): isolated command, JSON output parsing, errors, budget."""

from __future__ import annotations

import json

from arena.deciders.llm import SubscriptionDecider

SNAP = {"cycle_ts": 1_800_000_000, "symbols": {}}


def _out(structured, *, cost=0.0123, model="claude-sonnet-5-5", is_error=False, status=None, subtype="success"):
    return json.dumps({
        "type": "result", "subtype": subtype, "is_error": is_error, "api_error_status": status,
        "total_cost_usd": cost, "structured_output": structured, "result": json.dumps(structured),
        "usage": {"input_tokens": 10, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 5,
                  "output_tokens": 80},
        "modelUsage": {model: {"costUSD": cost}},
    })


def _decider(tmp_path, outputs, budget="0.50", calls=None):
    seq = list(outputs)

    def runner(cmd, text, env, cwd, timeout):
        if calls is not None:
            calls.append((cmd, text, env, cwd))
        return seq.pop(0)

    return SubscriptionDecider("claude-sonnet-5-5", "llm:claude-sonnet-5-5", ("2", "10"), budget,
                               workdir=tmp_path / "empty", runner=runner, sleep=lambda s: None)


ACTION = {"actions": [{"symbol": "BTC/EUR", "side": "buy", "size_pct": 10, "stop_pct": 5, "horizon_h": 24,
                       "expected_move_pct": 6, "confidence_pct": 55}], "justification": "test"}


def test_isolated_call_without_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-pass")
    calls = []
    res = _decider(tmp_path, [(0, _out(ACTION), "")], calls=calls).decide(SNAP, 0)
    cmd, text, env, _cwd = calls[0]
    assert "ANTHROPIC_API_KEY" not in env
    for flag in ("-p", "--no-session-persistence", "--strict-mcp-config"):
        assert flag in cmd
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-5-5"
    assert "<snapshot>" in text
    assert res.skipped_reason is None and res.parse_error is None
    assert len(res.intents) == 1 and res.intents[0].size_bp == 1000
    assert res.model_returned == "claude-sonnet-5-5"
    assert res.cost_uusd == 12_300 and res.input_tokens == 1015 and res.output_tokens == 80


def test_5xx_error_is_retried_then_succeeds(tmp_path):
    res = _decider(tmp_path, [(1, _out(None, is_error=True, status=529, subtype="error"), ""),
                              (0, _out(ACTION), "")]).decide(SNAP, 0)
    assert res.skipped_reason is None and len(res.intents) == 1


def test_4xx_error_is_not_retried(tmp_path):
    res = _decider(tmp_path, [(1, _out(None, is_error=True, status=400, subtype="error"), "")]).decide(SNAP, 0)
    assert res.skipped_reason == "api_error" and "status=400" in res.error


def test_unreadable_output_and_missing_cli(tmp_path):
    res = _decider(tmp_path, [(1, "not json", "")] * 3).decide(SNAP, 0)
    assert res.skipped_reason == "api_error"


def test_budget_exceeded_without_call(tmp_path):
    calls = []
    res = _decider(tmp_path, [], budget="0.0001", calls=calls).decide(SNAP, 0)
    assert res.skipped_reason == "budget" and calls == []


def test_invalid_output_gives_parse_error(tmp_path):
    bad = {"actions": [{"symbol": "DOGE/EUR", "side": "buy", "size_pct": 10}], "justification": "x"}
    res = _decider(tmp_path, [(0, _out(bad), "")]).decide(SNAP, 0)
    assert res.parse_error and res.intents == []
