"""A fake `claude -p` for the perp agent tests: it starts the round's real MCP server from --mcp-config,
calls tools through JSON-RPC, and prints a stream-json transcript like the CLI's. No model, no network.

FAKE_CLAUDE_MODE: normal | five_tools | no_result | mcp_failed
FAKE_CLAUDE_EXTRA: JSON {<model> or "*": {fields merged into the decision, e.g. alerts, entry_orders, actions}}
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

args = sys.argv[1:]
mode = os.environ.get("FAKE_CLAUDE_MODE", "normal")
from pathlib import Path

cfg = json.loads(Path(args[args.index("--mcp-config") + 1]).read_text())["mcpServers"]["arene"]
model = args[args.index("--model") + 1]
sys.stdin.read()


def out(obj):
    print(json.dumps(obj), flush=True)


if mode == "mcp_failed":
    out({"type": "system", "subtype": "init", "mcp_servers": [{"name": "arene", "status": "failed"}]})
    out(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "structured_output": {"actions": [], "justification": "x"},
        }
    )
    sys.exit(0)

env = dict(os.environ, **cfg.get("env", {}))
srv = subprocess.Popen(
    [cfg["command"], *cfg["args"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env
)
n = 0


def rpc(method, params=None):
    global n
    n += 1
    srv.stdin.write(json.dumps({"jsonrpc": "2.0", "id": n, "method": method, "params": params or {}}) + "\n")
    srv.stdin.flush()
    return json.loads(srv.stdout.readline())


rpc("initialize", {"protocolVersion": "2025-06-18"})
tools = [t["name"] for t in rpc("tools/list")["result"]["tools"]]
out(
    {
        "type": "system",
        "subtype": "init",
        "model": model,
        "mcp_servers": [{"name": "arene", "status": "connected"}],
        "tools": [f"mcp__arene__{t}" for t in tools],
    }
)
calls = [
    ("derives", {"instrument": "PF_XBTUSD"}),
    (
        "simuler_ordre",
        {
            "instrument": "PF_XBTUSD",
            "action": "open_long",
            "size_pct": 20,
            "stop_pct": 3,
            "take_profit_pct": 6,
            "horizon_h": 48,
            "expected_move_pct": 6,
        },
    ),
]
if mode == "five_tools":
    calls += [
        ("bougies", {"instrument": "PF_ETHUSD", "intervalle": "1h", "n": 5}),
        ("historique", {}),
        ("indicateurs", {"instrument": "PF_XBTUSD", "intervalle": "4h"}),
    ]
approved = False
for k, (name, a) in enumerate(calls):
    tid = f"toolu_{k}"
    out(
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "id": tid, "name": f"mcp__arene__{name}", "input": a}]
            },
        }
    )
    r = rpc("tools/call", {"name": name, "arguments": a})["result"]
    text = r["content"][0]["text"]
    if name == "simuler_ordre":
        approved = json.loads(text).get("approuve", False)
    out(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tid,
                        "content": [{"type": "text", "text": text}],
                        "is_error": r["isError"],
                    }
                ]
            },
        }
    )
srv.stdin.close()
srv.wait()
decision = {"actions": [], "justification": "rien de convaincant"}
if approved:
    decision = {
        "actions": [
            {
                "instrument": "PF_XBTUSD",
                "action": "open_long",
                "size_pct": 20,
                "stop_pct": 3,
                "take_profit_pct": 6,
                "horizon_h": 48,
                "expected_move_pct": 6,
                "confidence_pct": 55,
                "invalidation": "clôture 4 h sous 68000",
            }
        ],
        "justification": "funding faible et simulation approuvée",
    }
extra = json.loads(os.environ.get("FAKE_CLAUDE_EXTRA") or "{}")
decision.update(extra.get("*", {}))
decision.update(extra.get(model, {}))
out(
    {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "id": "toolu_so", "name": "StructuredOutput", "input": decision}]
        },
    }
)
if mode == "no_result":
    sys.exit(1)
out(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "num_turns": len(calls) + 2,
        "structured_output": decision,
        "total_cost_usd": 0.0123456,
        "usage": {
            "input_tokens": 1200,
            "output_tokens": 900,
            "cache_read_input_tokens": 30000,
            "cache_creation_input_tokens": 7000,
        },
        "modelUsage": {model: {}},
    }
)
