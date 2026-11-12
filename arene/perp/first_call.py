"""Step 5-bis of the perp league: the first REAL `claude -p` call, on a trial league, never on the league itself.

    python -m arene.perp.first_call preflight --data-var VAR_PERP --spot-var VAR_SPOT [--model M]
    python -m arene.perp.first_call call      --data-var VAR_PERP --spot-var VAR_SPOT [--model M]

`preflight` costs nothing: the exact command and environment of the agent are run with `ANTHROPIC_BASE_URL`
pointing to a closed local port, so no request reaches Anthropic, and the CLI's `init` event is checked
(the MCP server connected, the tools offered are the six `mcp__arene__*` tools plus `StructuredOutput` and
nothing else, no skill, no slash command, no plugin, the permission mode, the model).

`call` makes ONE call (no retry; by default a 0.10 USD ceiling and no `--effort`; step 6 passes
`--step 6 --effort low --budget 1.00`, the spot league's effort) on a trial league in
`VAR_PERP/essais/<ts>/` (its own journal, a fresh portfolio, the real collected market data read only). It
refuses to run within 20 minutes before or 30 minutes after a spot cycle (HH:05 UTC every 4 h), and holds the
spot cycle lock during the call, so no spot cycle or wake-up can run at the same time (a veille tick that
finds the lock taken skips, by design). Every call is logged in `VAR_PERP/llm-calls.jsonl` (model, equivalent
cost, tokens, duration, conformity). The report says whether the stream is conforming: the condition of step 6.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from arene.cycle import CycleBusy, cycle_lock
from arene.journal import Journal
from arene.paths import Paths
from arene.perp.agent import DEFAULT_WORKDIR, TOOL_PREFIX, AgentDecider, _default_runner
from arene.perp.agent_round import run_agent_round, snapshot
from arene.perp.collect import data_root
from arene.perp.config import load_perp_config
from arene.perp.counters import counters_for
from arene.perp.kraken_futures import KrakenFuturesClient
from arene.perp.market import market_view
from arene.perp.policy import load_perp_policy
from arene.perp.round_data import build_round
from arene.perp.sim import PerpSimulator
from arene.perp.store import PerpDataStore

TOOLS = {"bougies", "carnet", "derives", "indicateurs", "simuler_ordre", "historique"}
SPOT_CYCLE_HOURS = range(0, 24, 4)
SPOT_CYCLE_MINUTE = 5
BEFORE_S, AFTER_S = 20 * 60, 30 * 60
BUDGET_USD = "0.10"
LOCK_WAIT_S = 90.0  # a veille tick holds the spot lock a few seconds; a cycle or a wake-up longer: refused


def spot_cycle_too_close(now_ts: int) -> str | None:
    day = now_ts // 86_400 * 86_400
    for d in (day - 86_400, day, day + 86_400):
        for h in SPOT_CYCLE_HOURS:
            c = d + h * 3600 + SPOT_CYCLE_MINUTE * 60
            if c - BEFORE_S <= now_ts <= c + AFTER_S:
                return f"too close to the spot cycle of {time.strftime('%H:%M UTC', time.gmtime(c))}"
    return None


def check_init(init: Mapping[str, Any] | None, model: str) -> list[str]:
    """Problems found in the CLI's init event (empty list: conforming)."""
    if init is None:
        return ["no init event"]
    problems = []
    servers = {s.get("name"): s.get("status") for s in init.get("mcp_servers") or []}
    if servers != {"arene": "connected"}:
        problems.append(f"mcp_servers: {servers}")
    tools = set(init.get("tools") or [])
    expected = {TOOL_PREFIX + t for t in TOOLS}
    if not expected <= tools:
        problems.append(f"missing tools: {sorted(expected - tools)}")
    extra = sorted(tools - expected - {"StructuredOutput"})
    if extra:
        problems.append(f"extra tools: {extra}")
    for key in ("skills", "slash_commands", "plugins"):
        if init.get(key):
            problems.append(f"{key}: {init.get(key)}")
    # the built-in agent types are always listed; they are inert without an Agent tool (checked above: no
    # tool beyond the six and StructuredOutput)
    if init.get("permissionMode") not in (None, "dontAsk"):
        problems.append(f"permissionMode: {init.get('permissionMode')}")
    if init.get("model") not in (None, model):
        problems.append(f"model: {init.get('model')}")
    if init.get("apiKeySource") not in (None, "none"):
        problems.append(f"apiKeySource: {init.get('apiKeySource')} (the subscription is expected)")
    return problems


def first_init(stream: Path) -> dict[str, Any] | None:
    for line in stream.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict) and ev.get("type") == "system" and ev.get("subtype") == "init":
            return ev
    return None


class Trial:
    """A trial league: its own journal, one fresh portfolio, the real collected data (read only)."""

    def __init__(self, root: Path, data_var: Path, model: str, now_ts: int) -> None:
        self.cfg = load_perp_config()
        self.policy = load_perp_policy()
        self.symbols = [i.kraken_symbol for i in self.cfg.instruments]
        self.specs = KrakenFuturesClient().instruments(self.symbols)
        self.store = PerpDataStore(data_root(data_var))
        self.view = market_view(self.store, self.symbols, now_ts)
        if self.view is None:
            raise SystemExit("no recent market snapshot in the collected data")
        self.root = root
        self.now_ts = now_ts
        self.portfolio = f"llm-perp:{model}:essai"
        journal = Journal(root / "journal" / "events.jsonl")
        self.sim = PerpSimulator(
            journal, {s: v.tick_uusd for s, v in self.specs.items()}, self.cfg.simulation
        )
        self.sim.open_portfolio(self.portfolio, "llm", now_ts)

    def decider(
        self,
        model: str,
        runner: Any = _default_runner,
        timeout_s: float = 240.0,
        budget_usd: str = BUDGET_USD,
        effort: str | None = None,
    ) -> AgentDecider:
        return AgentDecider(
            model,
            self.portfolio,
            DEFAULT_WORKDIR,
            runner=runner,
            max_attempts=1,
            max_budget_usd=budget_usd,
            effort=effort,
            timeout_s=timeout_s,
        )


def preflight(args: argparse.Namespace) -> int:
    now = int(time.time())
    root = Path("/var/tmp/arene-perp-5bis") / f"preflight-{now}"
    trial = Trial(root, args.data_var, args.model, now)
    out_dir = root / "round"
    data, _sha = build_round(
        out_dir, trial.store, trial.sim.journal.events(), trial.view, trial.sim.states()[trial.portfolio],
        counters_for(trial.sim.journal.events(), trial.portfolio, now), trial.specs, trial.policy,
        trial.sim.params, now, now, trial.cfg.sha256,
    )  # fmt: skip

    def offline(cmd: list[str], stdin: str, env: dict[str, str], cwd: Path, timeout: float):
        return _default_runner(cmd, stdin, {**env, "ANTHROPIC_BASE_URL": "http://127.0.0.1:9"}, cwd, timeout)

    decider = trial.decider(args.model, runner=offline, timeout_s=45)
    snap = snapshot(data, "rendezvous", None)
    res = decider.decide(out_dir, snap)
    init = first_init(out_dir / "stream.jsonl")
    problems = check_init(init, args.model)
    if res.cost_uusd or res.tool_calls:
        problems.append(
            f"the offline run reports a cost or tool calls: {res.cost_uusd} µUSD, {len(res.tool_calls)}"
        )
    report = {
        "preflight": "ok" if not problems else "problems",
        "problems": problems,
        "first_message_chars": len(decider.message(snap)),
        "system_prompt_chars": len(decider.command(out_dir / "mcp.json")[decider.command(out_dir / "mcp.json").index("--system-prompt") + 1]),
        "init": {k: init.get(k) for k in ("model", "permissionMode", "apiKeySource", "tools", "mcp_servers",
                                          "skills", "slash_commands", "plugins", "agents", "claude_code_version")}
        if init else None,
        "dir": str(root),
    }  # fmt: skip
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 0 if not problems else 1


def call(args: argparse.Namespace) -> int:
    now = int(time.time())
    too_close = spot_cycle_too_close(now)
    if too_close:
        print(f"refused: {too_close}", file=sys.stderr)
        return 2
    spot = Paths.from_env(var=args.spot_var)
    try:
        with cycle_lock(spot, LOCK_WAIT_S):
            root = args.data_var / "essais" / f"{args.step.replace('-', '')}-{now}-{args.model}"
            trial = Trial(root, args.data_var, args.model, now)
            t0 = time.monotonic()
            res = run_agent_round(
                var=root, sim=trial.sim, store=trial.store, decider=trial.decider(args.model, budget_usd=args.budget, effort=args.effort or None), view=trial.view,
                specs=trial.specs, policy=trial.policy, config_sha256=trial.cfg.sha256, round_id=now, now_ts=now,
                kind="rendezvous", trigger=None, entries_blocked=False,
            )  # fmt: skip
            seconds = round(time.monotonic() - t0, 1)
    except CycleBusy:
        print("refused: a spot cycle or wake-up is running", file=sys.stderr)
        return 2
    events = trial.sim.journal.events()
    dec = next(e["payload"] for e in events if e["type"] == "agent_decision")
    rd = next(e["payload"] for e in events if e["type"] == "round_data")
    init = first_init(root / rd["path"] / "stream.jsonl")
    problems = check_init(init, args.model)
    if dec["parse_error"]:
        problems.append(f"decision: {dec['parse_error']}")
    if dec["tool_calls"] > 4:
        problems.append(f"{dec['tool_calls']} tool calls (4 at most)")
    if (
        dec["cost_uusd"] <= 0
        or dec["input_tokens"] + dec["cache_write_tokens"] + dec["cache_read_tokens"] <= 0
    ):
        problems.append("no cost or no tokens reported")
    line = {
        "ts": now,
        "step": args.step,
        "effort": args.effort or None,
        "model_requested": args.model,
        "model_returned": dec["model_returned"],
        "cost_uusd": dec["cost_uusd"],
        "input_tokens": dec["input_tokens"],
        "output_tokens": dec["output_tokens"],
        "cache_read_tokens": dec["cache_read_tokens"],
        "cache_write_tokens": dec["cache_write_tokens"],
        "latency_ms": dec["latency_ms"],
        "seconds": seconds,
        "num_turns": dec["num_turns"],
        "tool_calls": dec["tool_calls"],
        "error": res.error,
        "conforming": not problems,
        "problems": problems,
        "dir": str(root),
    }
    with (args.data_var / "llm-calls.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    print(json.dumps({**line, "decision": dec["parsed"]}, indent=1, ensure_ascii=False))
    return 0 if not problems else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m arene.perp.first_call")
    ap.add_argument("mode", choices=["preflight", "call"])
    ap.add_argument(
        "--data-var", type=Path, required=True, help="the perp league var (collected data, read only)"
    )
    ap.add_argument("--spot-var", type=Path, required=True, help="the spot var (its cycle lock)")
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--step", default="5-bis", help="the label logged with the call (5-bis, 6)")
    ap.add_argument(
        "--effort", default="", help="'' (no flag, the 5-bis default) or low, as in the spot league"
    )
    ap.add_argument("--budget", default=BUDGET_USD, help="--max-budget-usd of the call")
    args = ap.parse_args(argv)
    args.data_var = args.data_var.resolve()
    return preflight(args) if args.mode == "preflight" else call(args)


if __name__ == "__main__":
    sys.exit(main())
