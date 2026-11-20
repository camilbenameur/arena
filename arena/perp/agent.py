"""Agent decider of the perp league (study §2): one `claude -p` call per round, with the read-only MCP tools.

The CLI runs on a Claude subscription (`decider_backend = "subscription"`), isolated: no built-in tool (`--tools ""`),
only the `mcp__arena__*` tools of the round's server, no user settings, no session, `ANTHROPIC_API_KEY` removed.
The output is the stream (`--output-format stream-json --verbose`): every tool call and its result are read
from it, in order, so the caller can journal them; the final decision is the structured output validated by
`--json-schema`, then validated again here and converted into `PerpIntent`s (percent -> bp integers).

Isolation: a custom system prompt, no project instruction file, no auto-memory, no skills or slash commands, an empty working
directory outside any repository, `--max-budget-usd` as a hard ceiling.

A retry only after a transport failure (no `result` event, no tool call): a run that produced a result, even
an error (turn limit, schema retries exhausted, quota), is never retried, and the cost and tokens of every
attempt are summed. A round with no structured output is "no decision". On a timeout, the partial stream is
still parsed so the tool calls already made are journaled.
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, field_validator

from arena.perp.riskd import PerpIntent

PROMPT_PATH = Path(__file__).parent / "prompt" / "v8.md"
MCP_SERVER = "arena"
TOOL_PREFIX = f"mcp__{MCP_SERVER}__"
MAX_TOOL_CALLS = 4
MAX_TURNS = 9
TIMEOUT_S = 240.0
TIMEOUT_RC = -9  # the runner's return code when the CLI was killed on timeout
MAX_BUDGET_USD = "1.00"  # hard ceiling of one call (equivalent cost on the subscription)
JUSTIFICATION_MAX = 1200
INVALIDATION_MAX = 200
NOTE_MAX = 120
MAX_ORDERS = 3  # alerts, and entry orders, per decision
EXPIRES_DEFAULT_H = 4
WAKEUP_MIN_MIN = 5  # a wake-up asked by the model: one watcher tick at least...
WAKEUP_MAX_MIN = 60  # ...and at most an hour
MAX_PRICE_USD = 1_000_000_000
# Claude Code's built-in plugins, turned off (the preflight of step 5-bis checks none is loaded)
BUILTIN_PLUGINS = (
    "cc-plugin-agents-md@builtin",
    "cc-plugin-privacy@builtin",
    "cc-plugin-plugin-authoring@builtin",
)
ENV_KEEP = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "TMPDIR", "TZ", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR")
INSTRUMENTS = ("PF_XBTUSD", "PF_ETHUSD", "PF_SOLUSD", "PF_XRPUSD", "PF_LINKUSD", "PF_LTCUSD")
# an empty directory outside any git repository or project instruction file
DEFAULT_WORKDIR = Path("/var/tmp/arena-perp-claude-empty")
# bounds shared by the CLI schema and the local validation (percent)
BOUNDS = {
    "size_pct": (0, 100),
    "stop_pct": (0, 100),
    "take_profit_pct": (0, 1000),
    "expected_move_pct": (0, 100),
    "confidence_pct": (0, 100),
}


def _num(name: str, hi: int | None = None) -> dict[str, Any]:
    lo, top = BOUNDS[name]
    return {"type": ["number", "null"], "minimum": lo, "maximum": top if hi is None else hi}


def _bounded(name: str, hi: int | None = None) -> dict[str, Any]:
    lo, top = BOUNDS[name]
    return {"type": "number", "minimum": lo, "maximum": top if hi is None else hi}


_ORDER_COMMON = {
    "instrument": {"type": "string", "enum": list(INSTRUMENTS)},
    "condition": {"type": "string", "enum": ["above", "below"]},
    "price_usd": {"type": "number", "minimum": 0, "maximum": MAX_PRICE_USD},
    "expires_h": {"type": ["integer", "null"], "minimum": 1, "maximum": 24},
}


def output_schema(max_size_pct: int = 100) -> dict[str, Any]:
    """The decision schema; `max_size_pct` bounds `size_pct` (100 for the LLM portfolios, more for the council,
    whose policy allows entries above the equity)."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["actions", "justification"],
        "properties": {
            "actions": {
                "type": "array",
                "maxItems": 2,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["instrument", "action"],
                    "properties": {
                        "instrument": {"type": "string", "enum": list(INSTRUMENTS)},
                        "action": {"type": "string", "enum": ["open_long", "open_short", "reduce", "close"]},
                        "size_pct": _num("size_pct", max_size_pct),
                        "stop_pct": _num("stop_pct"),
                        "take_profit_pct": _num("take_profit_pct"),
                        "horizon_h": {"type": ["integer", "null"], "minimum": 1, "maximum": 168},
                        "expected_move_pct": _num("expected_move_pct"),
                        "confidence_pct": _num("confidence_pct"),
                        "invalidation": {"type": ["string", "null"], "maxLength": INVALIDATION_MAX},
                    },
                },
            },
            "justification": {"type": "string", "maxLength": JUSTIFICATION_MAX},
            "next_wakeup_min": {
                "type": ["integer", "null"],
                "minimum": WAKEUP_MIN_MIN,
                "maximum": WAKEUP_MAX_MIN,
            },
            "alerts": {
                "type": "array",
                "maxItems": MAX_ORDERS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["instrument", "condition", "price_usd"],
                    "properties": {
                        **_ORDER_COMMON,
                        "note": {"type": ["string", "null"], "maxLength": NOTE_MAX},
                    },
                },
            },
            "entry_orders": {
                "type": "array",
                "maxItems": MAX_ORDERS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "instrument",
                        "side",
                        "condition",
                        "price_usd",
                        "size_pct",
                        "stop_pct",
                        "horizon_h",
                        "expected_move_pct",
                    ],
                    "properties": {
                        **_ORDER_COMMON,
                        "side": {"type": "string", "enum": ["long", "short"]},
                        "size_pct": _bounded("size_pct", max_size_pct),
                        "stop_pct": _bounded("stop_pct"),
                        "take_profit_pct": _num("take_profit_pct"),
                        "horizon_h": {"type": "integer", "minimum": 1, "maximum": 168},
                        "expected_move_pct": _bounded("expected_move_pct"),
                        "confidence_pct": _num("confidence_pct"),
                        "invalidation": {"type": ["string", "null"], "maxLength": INVALIDATION_MAX},
                    },
                },
            },
        },
    }


OUTPUT_SCHEMA: dict[str, Any] = output_schema()


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def prompt_sha256() -> str:
    return hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()


# ---------------------------------------------------------------------- decision validation


def _clean(v: Any, n: int) -> Any:
    return v[:n].encode("utf-8", "replace").decode("utf-8") if isinstance(v, str) else v


class _Bounded(BaseModel):
    """Numeric fields named in BOUNDS: no boolean, finite, within the shared bounds."""

    @field_validator(*BOUNDS, mode="before", check_fields=False)
    @classmethod
    def _no_bool(cls, v: Any) -> Any:
        if isinstance(v, bool | str):
            raise ValueError("a boolean or a string is not a number")  # noqa: TRY004 (pydantic needs ValueError)
        return v

    @field_validator(*BOUNDS, check_fields=False)
    @classmethod
    def _bounds(cls, v: Decimal | None, info: Any) -> Decimal | None:
        lo, hi = BOUNDS[info.field_name]
        if info.field_name == "size_pct" and info.context and info.context.get("max_size_pct"):
            hi = info.context["max_size_pct"]  # the council (an entry may exceed the equity)
        if v is not None and (not v.is_finite() or v < lo or v > hi):
            raise ValueError(f"{info.field_name} out of bounds [{lo}, {hi}]: {v}")
        return v


class ActionV3(_Bounded):
    model_config = ConfigDict(extra="forbid")

    instrument: Literal[INSTRUMENTS]  # type: ignore[valid-type]
    action: Literal["open_long", "open_short", "reduce", "close"]
    size_pct: Decimal | None = None
    stop_pct: Decimal | None = None
    take_profit_pct: Decimal | None = None
    horizon_h: StrictInt | None = Field(default=None, ge=1, le=168)
    expected_move_pct: Decimal | None = None
    confidence_pct: Decimal | None = None
    invalidation: str | None = None

    @field_validator("invalidation", mode="before")
    @classmethod
    def _cut(cls, v: Any) -> Any:
        return _clean(v, INVALIDATION_MAX)


class _Level(_Bounded):
    instrument: Literal[INSTRUMENTS]  # type: ignore[valid-type]
    condition: Literal["above", "below"]
    price_usd: Decimal
    expires_h: StrictInt | None = Field(default=None, ge=1, le=24)

    @field_validator("price_usd", mode="before")
    @classmethod
    def _no_bool_price(cls, v: Any) -> Any:
        if isinstance(v, bool | str):
            raise ValueError("a boolean or a string is not a number")  # noqa: TRY004
        return v

    @field_validator("price_usd")
    @classmethod
    def _price(cls, v: Decimal) -> Decimal:
        if not v.is_finite() or v <= 0 or v > MAX_PRICE_USD:
            raise ValueError(f"price_usd out of bounds (0, {MAX_PRICE_USD}]: {v}")
        return v


class AlertV4(_Level):
    model_config = ConfigDict(extra="forbid")

    note: str | None = None

    @field_validator("note", mode="before")
    @classmethod
    def _cut_note(cls, v: Any) -> Any:
        return _clean(v, NOTE_MAX)


class EntryOrderV4(_Level):
    model_config = ConfigDict(extra="forbid")

    side: Literal["long", "short"]
    size_pct: Decimal
    stop_pct: Decimal
    take_profit_pct: Decimal | None = None
    horizon_h: StrictInt = Field(ge=1, le=168)  # riskd needs both to judge the cost against the move
    expected_move_pct: Decimal
    confidence_pct: Decimal | None = None
    invalidation: str | None = None

    @field_validator("invalidation", mode="before")
    @classmethod
    def _cut(cls, v: Any) -> Any:
        return _clean(v, INVALIDATION_MAX)

    @field_validator("size_pct", "stop_pct", "expected_move_pct")
    @classmethod
    def _positive(cls, v: Decimal, info: Any) -> Decimal:
        if v <= 0:
            raise ValueError(f"{info.field_name} must be > 0: {v}")
        return v


def _bp(v: Decimal | None, rounding: str = ROUND_HALF_UP) -> int | None:
    return None if v is None else int((v * 100).to_integral_value(rounding=rounding))


def _dstr(v: Decimal | None) -> str | None:
    if v is None:
        return None
    s = format(v.normalize(), "f")
    return s


def _uusd(price: Decimal) -> int:
    return int((price * 1_000_000).to_integral_value(rounding=ROUND_HALF_UP))


def _order_id(portfolio: str, round_id: int, kind: str, k: int, content: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            {"p": portfolio, "r": round_id, "kind": kind, "k": k, "c": content}, sort_keys=True
        ).encode()
    ).hexdigest()


def _parse_orders(
    raw: Any, kind: str, portfolio: str, round_id: int, max_size_pct: int | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(valid elements, errors) of `alerts` or `entry_orders`; each element is validated on its own.
    An element is {id, instrument, condition, price_uusd, ..., expires_h}: integers and strings only."""
    model = AlertV4 if kind == "alert" else EntryOrderV4
    out, errors = [], []
    for k, item in enumerate(raw):
        try:
            o = model.model_validate(item, context={"max_size_pct": max_size_pct})
        except ValidationError as exc:
            errors.append({"kind": kind, "k": k, "error": str(exc)[:300]})
            continue
        content: dict[str, Any] = {
            "instrument": o.instrument,
            "condition": o.condition,
            "price_uusd": _uusd(o.price_usd),
            "expires_h": o.expires_h if o.expires_h is not None else EXPIRES_DEFAULT_H,
        }
        if isinstance(o, AlertV4):
            content["note"] = o.note
        else:
            content.update(
                side=o.side,
                size_bp=_bp(o.size_pct, ROUND_DOWN),
                stop_bp=_bp(o.stop_pct),
                take_profit_bp=_bp(o.take_profit_pct),
                horizon_h=o.horizon_h,
                expected_move_bp=_bp(o.expected_move_pct),
                confidence_pct=int(o.confidence_pct.to_integral_value(rounding=ROUND_HALF_UP))
                if o.confidence_pct is not None
                else None,
                invalidation=o.invalidation,
            )
        zero = content["price_uusd"] <= 0 or (
            kind == "entry" and (not content["size_bp"] or not content["stop_bp"])
        )
        if zero:
            errors.append({"kind": kind, "k": k, "error": "level or size rounds to zero"})
            continue
        out.append({"id": _order_id(portfolio, round_id, kind, k, content), "k": k, **content})
    return out, errors


def parse_decision(
    data: Any,
    portfolio: str,
    round_id: int,
    now_ts: int,
    *,
    max_size_pct: int | None = None,
    max_actions: int = 2,
) -> tuple[dict[str, Any] | None, str | None, list[PerpIntent]]:
    """(journalable parsed decision | None, error | None, intents). Never raises.

    `max_size_pct`: the upper bound of `size_pct` when it is not 100 (the council); riskd judges the rest.
    `max_actions`: the longest list of actions (2; the council v4 rebalances up to six contracts at once).

    Each action is validated on its own: an invalid action is dropped and its error kept in the parsed
    decision (`action_errors`), so one bad entry never discards a close in the same decision. The same holds
    for each alert (`alerts`) and entry order (`entry_orders`), whose rejections are in `order_errors`. The
    decision itself is invalid only when it is not an object with at most two actions, and at most three
    alerts and three entry orders (absent or null: none)."""
    try:
        if isinstance(data, str):
            data = json.loads(data, parse_float=Decimal)
        if not isinstance(data, dict) or set(data) - {
            "actions",
            "justification",
            "alerts",
            "entry_orders",
            "next_wakeup_min",
        }:
            raise ValueError(
                "an object {actions, justification, alerts?, entry_orders?, next_wakeup_min?} is expected"
            )
        raw_actions = data.get("actions")
        if not isinstance(raw_actions, list) or len(raw_actions) > max_actions:
            raise ValueError(f"actions: a list of 0 to {max_actions} elements is expected")
        raw_orders = {}
        for key in ("alerts", "entry_orders"):
            raw_orders[key] = data.get(key) if data.get(key) is not None else []
            if not isinstance(raw_orders[key], list) or len(raw_orders[key]) > MAX_ORDERS:
                raise ValueError(f"{key}: a list of 0 to {MAX_ORDERS} elements is expected")
        justification = _clean(data.get("justification", ""), JUSTIFICATION_MAX)
        if not isinstance(justification, str):
            raise TypeError("justification: a string is expected")
    except (ValueError, TypeError) as exc:
        return None, f"invalid decision: {str(exc)[:300]}", []
    intents, parsed_actions, errors = [], [], []
    for k, raw in enumerate(raw_actions):
        try:
            a = ActionV3.model_validate(raw, context={"max_size_pct": max_size_pct})
        except ValidationError as exc:
            errors.append({"k": k, "error": str(exc)[:300]})
            continue
        content = {
            "instrument": a.instrument,
            "action": a.action,
            "size_bp": _bp(a.size_pct, ROUND_DOWN),
            "stop_bp": _bp(a.stop_pct),
            "take_profit_bp": _bp(a.take_profit_pct),
            "horizon_h": a.horizon_h,
            "expected_move_bp": _bp(a.expected_move_pct),
            "confidence_pct": int(a.confidence_pct.to_integral_value(rounding=ROUND_HALF_UP))
            if a.confidence_pct is not None
            else None,
        }
        iid = hashlib.sha256(
            json.dumps(
                {"p": portfolio, "r": round_id, "k": k, "c": content, "i": a.invalidation}, sort_keys=True
            ).encode()
        ).hexdigest()
        intents.append(PerpIntent(intent_id=iid, portfolio=portfolio, ts=now_ts, **content))
        parsed_actions.append(
            {k2: _dstr(v) if isinstance(v, Decimal) else v for k2, v in a.model_dump().items()}
        )
    alerts, alert_errors = _parse_orders(raw_orders["alerts"], "alert", portfolio, round_id)
    entries, entry_errors = _parse_orders(
        raw_orders["entry_orders"], "entry", portfolio, round_id, max_size_pct
    )
    wakeup, wakeup_errors = _parse_wakeup(data.get("next_wakeup_min"))
    parsed = {
        "actions": parsed_actions,
        "justification": justification,
        "action_errors": errors,
        "alerts": alerts,
        "entry_orders": entries,
        "order_errors": alert_errors + entry_errors + wakeup_errors,
        "next_wakeup_min": wakeup,
        "next_wakeup_invalid": bool(wakeup_errors),
    }
    return parsed, None, intents


def _parse_wakeup(raw: Any) -> tuple[int | None, list[dict[str, Any]]]:
    """(minutes | None, errors) of `next_wakeup_min`: an integer from 5 to 60, absent or null for none. A bad
    value is dropped alone (the rest of the decision stands, and so does the pending wake-up) and noted like a
    rejected order."""
    if raw is None:
        return None, []
    if isinstance(raw, Decimal) and raw.is_finite() and raw == raw.to_integral_value():
        raw = int(raw)  # 60.0: an integer for the JSON schema the CLI checks against
    if type(raw) is not int or not WAKEUP_MIN_MIN <= raw <= WAKEUP_MAX_MIN:
        error = f"next_wakeup_min: an integer from {WAKEUP_MIN_MIN} to {WAKEUP_MAX_MIN} is expected"
        return None, [{"kind": "wakeup", "k": 0, "error": error}]
    return raw, []


def canonical_json(obj: Any) -> str:
    """JSON text with sorted keys where a Decimal is written as the bare number the model sent (never as a
    string, never through a float)."""
    if isinstance(obj, Decimal):
        return str(obj) if obj.is_finite() else json.dumps(str(obj))  # "20.50", "1E+30": as sent
    if isinstance(obj, dict):
        items = sorted(obj.items(), key=lambda kv: str(kv[0]))
        return (
            "{"
            + ",".join(f"{json.dumps(str(k), ensure_ascii=False)}:{canonical_json(v)}" for k, v in items)
            + "}"
        )
    if isinstance(obj, list | tuple):
        return "[" + ",".join(canonical_json(v) for v in obj) + "]"
    return json.dumps(obj, ensure_ascii=False)


# ---------------------------------------------------------------------- the CLI stream


@dataclass
class ToolCall:
    n: int
    tool: str
    arguments: str  # JSON text (never parsed into floats)
    response: str
    is_error: bool
    member: str | None = None  # the council member who made the call (None: a single-model portfolio)


@dataclass
class AgentResult:
    decision: Any = None  # the structured output (JSON-compatible), or None
    tool_calls: list[ToolCall] = field(default_factory=list)
    mcp_status: str | None = None
    model_returned: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_uusd: int = 0
    num_turns: int = 0
    latency_ms: int = 0
    error: str | None = None
    stderr_tail: str = ""
    assistant_seen: bool = False  # the model answered at least once (the quota was used)
    result_seen: bool = False  # a `result` event was read (the run reached its end, even with an error)
    attempts: int = 0
    rc: int | None = None
    first_error: str | None = None  # the error of a first attempt that was retried
    stream_sha256: str | None = None
    tools_offered: list[str] = field(default_factory=list)  # from the init event
    council: list[dict[str, Any]] = field(
        default_factory=list
    )  # the council's opinions (council_opinion events)
    extra: dict[str, Any] = field(default_factory=dict)  # more fields for the agent_decision event


def _blocks(ev: Mapping[str, Any]) -> list[dict[str, Any]]:
    msg = ev.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def parse_stream(lines: Iterable[str]) -> AgentResult:
    """Reads `claude -p --output-format stream-json --verbose` line by line."""
    res = AgentResult()
    pending: dict[str, tuple[str, str]] = {}  # tool_use_id -> (tool name, arguments JSON)
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line, parse_float=Decimal)
        except (ValueError, ArithmeticError):
            continue
        if not isinstance(ev, dict):
            continue
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            servers = {s.get("name"): s.get("status") for s in ev.get("mcp_servers") or []}
            res.mcp_status = servers.get(MCP_SERVER, "absent")
            res.tools_offered = [str(x) for x in ev.get("tools") or []]
        elif t == "assistant":
            res.assistant_seen = True
            for block in _blocks(ev):
                if block.get("type") == "tool_use" and str(block.get("name", "")).startswith(TOOL_PREFIX):
                    args = canonical_json(block.get("input") or {})
                    pending[block["id"]] = (block["name"][len(TOOL_PREFIX) :], args)
        elif t == "user":
            for block in _blocks(ev):
                if block.get("type") != "tool_result" or block.get("tool_use_id") not in pending:
                    continue
                name, args = pending.pop(block["tool_use_id"])
                content = block.get("content")
                if isinstance(content, list):
                    text = "".join(c.get("text", "") for c in content if isinstance(c, dict))
                else:
                    text = str(content or "")
                res.tool_calls.append(
                    ToolCall(len(res.tool_calls) + 1, name, args, text, bool(block.get("is_error")))
                )
        elif t == "result":
            res.result_seen = True
            res.num_turns = int(ev.get("num_turns") or 0)
            usage = ev.get("usage") or {}
            res.input_tokens = int(usage.get("input_tokens") or 0)
            res.output_tokens = int(usage.get("output_tokens") or 0)
            res.cache_read_tokens = int(usage.get("cache_read_input_tokens") or 0)
            res.cache_write_tokens = int(usage.get("cache_creation_input_tokens") or 0)
            try:
                res.cost_uusd = int(
                    (Decimal(str(ev.get("total_cost_usd") or 0)) * 1_000_000).to_integral_value(
                        rounding="ROUND_CEILING"
                    )
                )
            except ArithmeticError:
                res.cost_uusd = 0
                res.error = "unreadable total_cost_usd"
            models = list((ev.get("modelUsage") or {}).keys())
            res.model_returned = ",".join(models) or None
            if ev.get("is_error") or ev.get("subtype") != "success":
                res.error = f"result {ev.get('subtype')}: {str(ev.get('result'))[:200]}"
            elif ev.get("structured_output") is None:
                res.error = "no structured output"
            else:
                res.decision = ev["structured_output"]
    ok_tool = any(not c.is_error for c in res.tool_calls)
    if res.mcp_status not in (None, "connected") and not (res.mcp_status == "pending" and ok_tool):
        res.error = res.error or f"MCP server {MCP_SERVER} not connected ({res.mcp_status})"
        res.decision = None
    return res


def stream_cost_uusd(path: Path) -> int:
    """The cost the CLI reported in a saved stream (every `result` event, every attempt); 0 without one. For the
    rounds cut after their call, and the calls whose parsing failed: the money spent is still counted."""
    total = 0
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0
    for line in lines:
        try:
            ev = json.loads(line, parse_float=Decimal)
            if isinstance(ev, dict) and ev.get("type") == "result":
                cost = Decimal(str(ev.get("total_cost_usd") or 0)) * 1_000_000
                total += max(0, int(cost.to_integral_value(rounding="ROUND_CEILING")))
        except (ValueError, ArithmeticError):
            continue
    return total


# ---------------------------------------------------------------------- the decider


def claude_bin() -> str:
    found = shutil.which("claude")
    return found or str(Path.home() / ".local" / "bin" / "claude")


def _write_stream(round_dir: Path, lines: list[str]) -> str:
    """Writes the raw stream of every attempt (before any parsing) and returns its sha256."""
    raw = "\n".join(lines).encode("utf-8")
    (round_dir / "stream.jsonl").write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


@functools.cache
def cli_version() -> str | None:
    """`claude --version`, journaled with each decision (no model call)."""
    try:
        p = subprocess.run(
            [claude_bin(), "--version"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip()[:100] or None


Runner = Callable[[list[str], str, dict[str, str], Path, float], tuple[int, list[str], str]]


def _default_runner(
    cmd: list[str], stdin: str, env: dict[str, str], cwd: Path, timeout: float
) -> tuple[int, list[str], str]:
    """Runs the CLI in its own process group; on timeout the whole group (CLI and MCP server) is killed and
    the partial stream is returned with `TIMEOUT_RC`."""
    p = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=cwd,
        start_new_session=True,
    )
    try:
        out, err = p.communicate(stdin, timeout=timeout)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(p.pid, signal.SIGKILL)
        out, err = p.communicate()
        rc = TIMEOUT_RC
    return rc, (out or "").splitlines(), (err or "")[-2000:]


@dataclass
class AgentDecider:
    model: str
    portfolio: str
    workdir: Path  # stable and empty: the cache is tied to the working directory
    runner: Runner = _default_runner
    max_tool_calls: int = MAX_TOOL_CALLS
    max_turns: int = MAX_TURNS
    timeout_s: float = TIMEOUT_S
    python: str = sys.executable
    max_attempts: int = 1  # 2 allows one retry after a transport failure before any model answer
    max_budget_usd: str = MAX_BUDGET_USD
    effort: str | None = "low"  # None: the flag is not passed (a model may not support it)

    def system_prompt(self) -> str:
        return load_prompt()

    def output_schema(self) -> dict[str, Any]:
        return OUTPUT_SCHEMA

    def prompt_digest(self) -> str:
        """The sha256 journaled with the decision (`prompt_sha256`)."""
        return prompt_sha256()

    def mcp_config(self, round_dir: Path) -> dict[str, Any]:
        return {
            "mcpServers": {
                MCP_SERVER: {
                    "command": self.python,
                    "args": [
                        "-m",
                        "arena.perp.mcp_server",
                        "--round-dir",
                        str(round_dir),
                        "--portfolio",
                        self.portfolio,
                        "--max-calls",
                        str(self.max_tool_calls),
                    ],
                    "env": {"PYTHONPATH": str(Path(__file__).resolve().parent.parent.parent)},
                }
            }
        }

    def command(self, mcp_path: Path) -> list[str]:
        return [
            claude_bin(), "-p",
            "--model", self.model,
            "--output-format", "stream-json", "--verbose",
            "--json-schema", json.dumps(self.output_schema(), separators=(",", ":")),
            "--system-prompt", self.system_prompt(),
            "--tools", "",
            "--mcp-config", str(mcp_path), "--strict-mcp-config",
            "--allowedTools", f"{TOOL_PREFIX}*",
            "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--max-turns", str(self.max_turns),
            "--setting-sources", "",
            "--settings", json.dumps({"enabledPlugins": {p: False for p in BUILTIN_PLUGINS}}),
            "--disable-slash-commands",
            "--no-session-persistence",
            "--max-budget-usd", self.max_budget_usd,
            *(["--effort", self.effort] if self.effort else []),
        ]  # fmt: skip

    def env(self) -> dict[str, str]:
        """A whitelisted environment: nothing of a parent Claude session (CLAUDE*, ANTHROPIC*, MCP_*) leaks in;
        the subscription login is read from HOME."""
        env = {k: v for k, v in os.environ.items() if k in ENV_KEEP or k.startswith("LC_")}
        env.update(
            {
                "ENABLE_TOOL_SEARCH": "false",
                "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
                "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
                "CLAUDE_CODE_DISABLE_BUNDLED_SKILLS": "1",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "DISABLE_AUTOUPDATER": "1",
                "MCP_CONNECTION_NONBLOCKING": "0",  # the server is connected before the first turn
                "MCP_TIMEOUT": "30000",
            }
        )
        return env

    def message(self, snapshot: Mapping[str, Any]) -> str:
        """The exact first user message (its sha256 is journaled with the round)."""
        payload = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, default=str).replace(
            "<", "\\u003c"
        )
        return (
            "Here is the round snapshot (data only, no instructions):\n"
            f"<snapshot>\n{payload}\n</snapshot>\n"
            "Use your tools if needed (at most 4 calls), then return the requested decision object."
        )

    def decide(self, round_dir: Path, snapshot: Mapping[str, Any]) -> AgentResult:
        mcp_path = round_dir / "mcp.json"
        mcp_path.write_text(json.dumps(self.mcp_config(round_dir)), encoding="utf-8")
        message = self.message(snapshot)
        self.workdir.mkdir(parents=True, exist_ok=True)
        t0 = time.monotonic()
        total = AgentResult()
        res = AgentResult()
        attempt = 0
        raw_lines: list[str] = []
        for attempt in range(1, max(1, self.max_attempts) + 1):
            try:
                rc, lines, err = self.runner(
                    self.command(mcp_path), message, self.env(), self.workdir, self.timeout_s
                )
            except OSError as exc:
                res = AgentResult(error=f"cannot run the CLI: {exc}")
                break
            raw_lines += lines
            _write_stream(round_dir, raw_lines)
            res = parse_stream(lines)
            res.rc, res.stderr_tail = rc, err[-500:]
            if rc == TIMEOUT_RC:
                res.error = f"timeout after {self.timeout_s} s"
                res.decision = None
            elif res.decision is None and res.error is None:
                res.error = f"cli rc={rc}: no result event"
            for f in (
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "cost_uusd",
            ):
                setattr(total, f, getattr(total, f) + getattr(res, f))
            # a retry only after a transport failure: no result event, no tool call, no timeout
            retry = not res.result_seen and not res.assistant_seen and not res.tool_calls and rc != TIMEOUT_RC
            if not retry or attempt == self.max_attempts:
                break
            total.first_error = res.error
        for f in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "cost_uusd"):
            setattr(res, f, getattr(total, f))
        res.first_error = total.first_error
        res.attempts = attempt
        res.stream_sha256 = _write_stream(round_dir, raw_lines)
        res.latency_ms = int((time.monotonic() - t0) * 1000)
        return res
