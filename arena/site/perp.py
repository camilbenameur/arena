"""Dashboard data for the derivatives league (perpetual contracts, paper), from its journal ALONE.

Separate journal: `var-perp/journal/events.jsonl` (same hash-chained format as the spot journal). NEVER read
`var-perp/trials/` (trial leagues) nor `var-perp/rounds/` (raw CLI streams) nor `var-perp/llm-calls.jsonl`.

Journal units: µEUR (`_ueur`), µUSD (`_uusd`, prices), quantities in signed 1e-8 units (long > 0), funding
in signed µEUR (> 0 paid). Nothing below publishes a path, an error trace or a tooling detail:
`round_data.path`, `stderr_tail`, `cli_version`, `cli_rc`, `tools_offered`, `mcp_status`, `first_error`,
the raw tool responses, `perp_tick.notes/problems` and the `alert` messages never leave this module.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from arena.journal import Journal, verify
from arena.perp import agent_orders as AO
from arena.perp import round_quota
from arena.perp.ledger import MarginAccount, PerpLedgerError, price_pnl_uusd, replay, to_eur
from arena.perp.llm_league import LlmConfigError, load_llm_league
from arena.perp.news import load_news_config

ROUND_S = 4 * 3600
ROUND_OFFSET_S = 2 * 3600  # rounds at 02:00, 06:00, …, 22:00 UTC
CURVE_STEP_S = 1_800  # one point every 30 min on the curve (plus the last reading)
DECISIONS_MAX = 120
DELIBERATIONS_MAX = 48  # council opinions published for its last 48 rounds (8 h at 10 min); the others stay in the journal
OPERATIONS_MAX = 60
JUSTIFICATION_MAX = 1_200
INVALIDATION_MAX = 200
NOTE_MAX = 160
TITLE_MAX = 120
NEWS_S = 7 * 86_400  # news window: 7 days ahead (calendar) and behind (Kraken announcements)
ANNOUNCEMENTS_MAX = 12
IMPACTS = {"minor": "minor", "major": "major", "critical": "critical"}

BASKET = "benchmark-perp:basket-1x"
TREND = "benchmark-perp:trend"
RANDOM = "benchmark-perp:random"
COUNCIL = "council-perp:haiku"  # the Haiku Council: Haiku President
COUNCIL_OPUS = "council-perp:opus"  # the Opus Council: the same ten Haiku advisers, Opus President
COUNCIL_TREND = "council-perp:trend"  # the Trend Council (v4): the engine decides, the LLMs brake
TREND_ENGINE = "benchmark-perp:trend-engine"  # its benchmark: the same engine, without LLMs
ROBOT = "robot-perp:hunter"  # the Wick Hunter: a robot without AI that reads prices every 5 seconds
ROBOT_5MIN = "benchmark-perp:hunter-5min"  # its benchmark: the same rule, decided only every 5 minutes
ROBOTS = (ROBOT, ROBOT_5MIN)
COUNCIL_PREFIX = "council-perp:"
DAILY_TARGET_PCT = 1  # the stated target (initially 10%, lowered to 1% a day)

NAMES = {
    "llm-perp:claude-haiku-5-5": "Claude Haiku 5.5",
    "llm-perp:claude-sonnet-5-5": "Claude Sonnet 5.5",
    "llm-perp:claude-opus-5-5": "Claude Opus 5.5",
    "llm-perp:claude-fable-5-2": "Claude Fable 5.2",
    COUNCIL: "Haiku Council",
    COUNCIL_OPUS: "Opus Council",
    COUNCIL_TREND: "Trend Council",
    TREND_ENGINE: "Benchmark engine only",
    ROBOT: "Wick Hunter",
    ROBOT_5MIN: "Wick Hunter at a 5-min pace",
    BASKET: "Benchmark basket 1x",
    TREND: "Benchmark trend",
    RANDOM: "Benchmark random",
}
ORDER = list(NAMES)
SUBTITLES = {
    COUNCIL: "10 Haiku · Haiku president",
    COUNCIL_OPUS: "10 Haiku · Opus president",
    COUNCIL_TREND: "trend engine · 3 Haiku and an Opus president who brake",
}
COUNCIL_BUDGETS_USD = {COUNCIL: 10, COUNCIL_OPUS: 25, COUNCIL_TREND: 5}  # the day's budget, at list-price equivalent
DESCRIPTIONS = {
    COUNCIL: "Claude Haiku 5.5 models deliberate every round: independent opinions, a devil's advocate, then a Haiku President who decides.",
    COUNCIL_OPUS: "The same Haiku 5.5 advisers deliberate every round; a Claude Opus 5.5 President decides.",
    COUNCIL_TREND: "A trend-following engine (2-day / 6-day moving averages, long and short, size set by volatility, scale 2x) gives the target of each contract at every 4-hour bar. Three Haiku and an Opus President can only brake: a coefficient of 1, 0.5 or 0 per contract.",
    TREND_ENGINE: "The same trend engine at 2x, without AI, through the same execution path and on the same 4-hour rounds: the gap with the Trend Council measures what the AIs add or remove.",
    ROBOT: "A robot without AI reads prices every 5 seconds. When a contract moves more than 4.5% in 5, 15 or 30 minutes (a wick), it plays the reversal: it buys after a drop and sells after a rise, at 2x the portfolio, with a 5% stop. It exits 60 minutes after entry, then stays out of that contract for 60 minutes. On the bench, the gain disappears with delay: speed is the whole strategy.",
    ROBOT_5MIN: "The same rule, through the same execution path, but deciding only at the pace of a daily review: once per 5-minute slot, on the prices known at that moment. The gap with the Wick Hunter measures what speed earns.",
    BASKET: "Equal-weight buyer of the 6 contracts, without leverage or stop, rebalanced monthly: buy and hold.",
    TREND: "Every day, long on a contract that rose over 20 days, short otherwise; 1/6 of the portfolio per contract, 10% stop.",
    RANDOM: "Draws 0 to 2 decisions at random at each round, under exactly the same risk rules as the AIs.",
}

# The robots (no AI): the rule in one sentence, what they saw and did.
ROBOT_RULE = "plays against wicks: more than 4.5% in 5, 15 or 30 min · 2x · 5% stop · exit at 60 min"
ROBOT_BADGE = "robot without AI · leverage ≤ 10x · paper demonstration, outside the 2x rule"
ROBOT_SUBTITLES = {ROBOT: ROBOT_RULE, ROBOT_5MIN: "the same rule, decided once per 5-min slot"}

TREND_BADGE = "trend engine · leverage ≤ 10x · the AIs can only brake"


def _daily_target(capital: int, equity: int, open_ts: int, now: int) -> dict[str, Any]:
    """The stated target (1%/day) next to the realized return per day, side by side and unvarnished: the compounded
    daily rate since opening (at least one day counted: a portfolio a few hours old shows its return of the day)."""
    days = max((now - open_ts) / 86_400, 1.0)
    realized = (equity / capital) ** (1 / days) - 1 if capital > 0 and equity > 0 else -1.0
    return {"target_pct": DAILY_TARGET_PCT, "realized_pct": round(100 * realized, 3), "days": round(days, 1)}


# The Haiku Council (docs/SPEC-PERP-COUNCIL-HAIKU.md): a separate category, never ranked with the 4 neutral LLMs.
COUNCIL_BADGE = "leverage ≤ 10x"
COUNCIL_OUTSIDE_RULE = "Paper demonstration, outside the retail rule (2x): could not go live as it is."
# The members in stage order: A (opinions without seeing each other), B (the Advocate reads A), C (the President decides).
# (name, stage, role, public sources of the prompt)
MEMBERS = {
    "mapper": ("The Cartographer", "A", "the regime of each contract", "crypto-regime-analyzer; TradingAgents technical analyst"),
    "follower": ("The Follower", "A", "the trend to follow", "breakout-trade-planner"),
    "hunter": ("The Breakout Hunter", "A", "the move that is starting", "breakout-trade-planner (momentum burst)"),
    "contrarian": ("The Contrarian", "A", "the overcrowded consensus", "contrarian-setup-gate; TradingAgents bearish researcher"),
    "arbitrageur": ("The Pairs Arbitrageur", "A", "relative value: long the strong, short the weak", "pair-trade-screener"),
    "order_book": ("The Order Book Reader", "A", "the order book and the cost of entry", "HyperGrok (analysts, execution)"),
    "treasurer": ("The Leverage Treasurer", "A", "size and leverage", "position-sizer, futures-position-sizer"),
    "guardian": ("The Risk Guardian", "A", "stops and distance to ruin", "drawdown-circuit-breaker, pre-trade-discipline-gate; HyperGrok risk manager"),
    "historian": ("The Historian", "A", "what the council has already missed or got right", "signal-postmortem; HyperGrok Trade Reviewer"),
    "advocate": ("The Devil's Advocate", "B", "attacks the most supported trade", "TradingAgents bearish researcher and debate"),
    "president": ("The President", "C", "settles and decides", "TradingAgents Portfolio Manager; HyperGrok Desk Lead"),
}
# The three advisers of the Trend Council (v4): they can only propose to brake the engine.
MEMBERS_V4 = {
    "news_watcher": ("The News Watcher", "A", "Kraken announcements and macro releases", "v4 prompt"),
    "controller": ("The Data Controller", "A", "inconsistent prices, gaps, stale view", "v4 prompt"),
    "risk_advocate": ("The Risk Advocate", "A", "concentration and drawdown", "v4 prompt"),
}
MEMBERS_ORDER = list(MEMBERS)
ALL_MEMBERS = {**MEMBERS, **MEMBERS_V4}
ALL_ORDER = list(ALL_MEMBERS)
ARGUMENT_MAX = 700

ACTIONS = {"open_long": "Opens a long", "open_short": "Opens a short", "reduce": "Reduces", "close": "Closes"}

FILL_REASONS = {
    "intent": "decision",
    "stop": "stop hit",
    "take_profit": "target reached",
    "margin_closeout": "margin close-out",
    "max_holding": "maximum holding (7 d)",
    "halt": "drawdown halt",
    "kill_switch": "circuit breaker",
    "no_stop": "position without stop closed",
    "retired": "council archived, positions closed",
}

EXECUTIONS = {
    "filled": "executed",
    "filled_without_take_profit": "executed, without target",
    "closed_without_stop": "stop could not be placed: position closed again",
    "unprotected_position_open": "position left without stop (closed by the watch)",
    "refused": "refused at execution",
    "error": "execution failed",
    "not_executed_view_stale": "not executed: stale market data",
    "not_executed_stale_trigger": "not executed: crossing seen too late (over 15 min)",
    "not_executed_refused_on_resume": "not executed: refused on resume",
}

END_REASONS = {"expired": "expired", "replaced": "replaced", "portfolio_halted": "cancelled (portfolio halted)", "portfolio_retired": "cancelled (council archived)"}
HISTORY_MAX = 12

JUMPS = {
    "halted": "portfolio halted",
    "daily_budget": "daily budget reached",
    "interrupted_before_call": "round interrupted before the call",
    "interrupted_after_call": "round interrupted after the call",
}

CODES = {
    "NOT_WHITELISTED": "contract not on the allowed list",
    "NOT_TRADEABLE": "contract not tradable right now",
    "UNKNOWN_INSTRUMENT": "unknown contract",
    "BAD_ACTION": "invalid action",
    "BAD_PORTFOLIO": "invalid portfolio",
    "INTENT_STALE": "decision too old",
    "BAD_SIZE": "invalid size",
    "BAD_HORIZON": "invalid horizon",
    "BAD_TAKE_PROFIT": "invalid target",
    "BAD_EXPECTED_MOVE": "invalid expected move",
    "NO_QUOTE": "no price",
    "NO_MARK": "no reference price",
    "NO_FX": "no euro-dollar rate",
    "NO_EQUITY": "portfolio value unknown",
    "NO_POSITION": "no position to reduce",
    "NO_FLIP": "flip forbidden (close first)",
    "KILL_SWITCH": "kill switch active",
    "HALTED": "portfolio halted",
    "FROZEN": "portfolio frozen",
    "COUNTERS_MISSING": "risk counters unavailable",
    "FEE_BUDGET": "monthly fee budget reached",
    "DAILY_TRADES": "4 entries already made in 24 h",
    "ORDER_RATE": "too many orders per minute",
    "TOO_SOON": "less than 4 h since the last entry on this contract",
    "DATA_STALE": "stale market data",
    "MARK_SANITY": "prices inconsistent with each other",
    "SPREAD_ANOMALY": "abnormal bid-ask spread",
    "FUNDING_EXTREME": "extreme funding against the position",
    "MAX_ORDER_SIZE": "order above 50% of the portfolio",
    "STOP_REQUIRED": "entry without stop",
    "STOP_RANGE": "stop outside 1 to 15%",
    "EDGE_TOO_SMALL": "costs too large against the expected move",
    "ORDER_TOO_SMALL": "order too small",
    "MAX_CONTRACT_POSITION": "platform position cap",
    "MAX_POSITION": "position above 100% of the portfolio",
    "MAX_LEVERAGE": "leverage above 2",
    "INITIAL_MARGIN": "insufficient margin after the order",
    "MAX_TRADE_LOSS": "loss at the stop above 3% of the portfolio",
    "MAX_OPEN_RISK": "cumulative losses at the stops above 7.5%",
    "LIQUIDATION_BEFORE_STOP": "liquidation reached before the stop",
    "INTERNAL_ERROR": "internal error of the guardrail",
}

# The same codes, at the bounds of the council policy (config/policy-perp-council.toml).
COUNCIL_CODES = {
    **CODES,
    "DAILY_TRADES": "24 entries already made in 24 h",
    "MAX_ORDER_SIZE": "order above 500% of the portfolio",
    "MAX_POSITION": "position above 1,000% of the portfolio",
    "MAX_LEVERAGE": "leverage above 10",
    "MAX_TRADE_LOSS": "loss at the stop above 25% of the portfolio",
    "MAX_OPEN_RISK": "cumulative losses at the stops above 60%",
}
# And at the bounds of the Trend Council policy and its benchmark (config/policy-perp-council-trend.toml).
TREND_CODES = {
    **COUNCIL_CODES,
    "DAILY_TRADES": "48 entries or adjustments already made in 24 h",
    "MAX_ORDER_SIZE": "order above 400% of the portfolio",
    "MAX_POSITION": "position above 500% of the portfolio",
    "MAX_OPEN_RISK": "cumulative losses at the stops above 59%",
}

TOOLS = {
    "candles": "a contract's candles",
    "order_book": "the order book",
    "derivatives": "funding and open interest",
    "indicators": "technical indicators",
    "simulate_order": "the guardrail verdict, without executing",
    "history": "its past decisions",
}

# The 6 contracts, as Kraken Futures' public feed names them (live prices on the browser side).
PRODUCTS = ("PF_XBTUSD", "PF_ETHUSD", "PF_SOLUSD", "PF_XRPUSD", "PF_LINKUSD", "PF_LTCUSD")

_SYM = re.compile(r"^(?:PF_)?([A-Z0-9]+?)(?:USD)?(?:-PERP)?$")


def short(instrument: str | None) -> str:
    """\"PF_XBTUSD\", \"BTC-PERP\" -> \"BTC\"."""
    if not instrument:
        return "?"
    s = str(instrument).upper()
    if s.endswith("-PERP"):
        base = s[: -len("-PERP")]
    else:
        m = _SYM.match(s)
        base = m.group(1) if m else s
        base = base.removeprefix("PF_")
    return "BTC" if base == "XBT" else base


def product(instrument: str | None) -> str | None:
    """The contract name in Kraken Futures' public feed (\"BTC-PERP\" -> \"PF_XBTUSD\"), or None."""
    c = short(instrument)
    pid = f"PF_{'XBT' if c == 'BTC' else c}USD"
    return pid if pid in PRODUCTS else None


def name(portfolio: str) -> str:
    if portfolio not in NAMES and portfolio.startswith(COUNCIL_PREFIX):  # a council the site does not know yet
        remaining = re.sub(r"[^A-Za-z0-9]+", " ", portfolio[len(COUNCIL_PREFIX):]).strip()
        return f"{remaining[:1].upper()}{remaining[1:]} Council" if remaining else "Council"
    return NAMES.get(portfolio, portfolio.split(":", 1)[-1])


def _model(v: Any) -> str | None:
    """\"claude-opus-5-5\" -> \"Opus\"; None if the model is not recognized."""
    s = str(v).lower() if isinstance(v, str) else ""
    return next((label for k, label in (("opus", "Opus"), ("sonnet", "Sonnet"), ("haiku", "Haiku"), ("fable", "Fable")) if k in s), None)


def _integer(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def slug(portfolio: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", portfolio.lower()).strip("-")


def next_scheduled_round(now: int) -> int:
    return ((now - ROUND_OFFSET_S) // ROUND_S + 1) * ROUND_S + ROUND_OFFSET_S


def perp_journal_path(spot_journal: Path) -> Path:
    """The derivatives league journal, next to the spot var: <repo>/var-perp/journal/events.jsonl."""
    return Path(spot_journal).resolve().parent.parent.parent / "var-perp" / "journal" / "events.jsonl"


def _pct_str(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v))
    except ValueError:
        return None


def _text(v: Any, n: int) -> str | None:
    if not isinstance(v, str) or not v.strip():
        return None
    v = " ".join(v.split())
    return v if len(v) <= n else v[: n - 1].rstrip() + "…"


def _price_uusd(v: Any) -> int | None:
    """\"98000.5\" (dollars as text) -> integer µUSD."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        return None
    return int(d.scaleb(6)) if d.is_finite() and d > 0 else None


def _public_rejection(error: Any, kind: Any = None) -> str:
    """Fixed category of an element refused at creation (the raw text is not published)."""
    if kind == "wakeup":
        return "invalid wake-up request"
    s = str(error or "").lower()
    if "25%" in s or "25 %" in s or "away from the mark" in s:
        return "level more than 25% away from the price"
    if "already crossed" in s:
        return "level already crossed"
    return "invalid element"


def _ts(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None


def _news(d: Mapping[str, Any]) -> dict[str, Any] | None:
    """The news attached to a trigger: macro releases (id, label, time) and Kraken announcements
    (kind, status, title). Texts are bounded; the internal key is not published."""
    rel = d.get("releases")
    ann = d.get("announcements")
    releases = [
        {"label": _text(r.get("label"), 120) or "macro release", "ts": _ts(r.get("ts"))}
        for r in (rel if isinstance(rel, list) else []) if isinstance(r, Mapping)
    ]  # fmt: skip
    announcements = [
        {"kind": str(a.get("kind") or "")[:20], "status": str(a.get("status") or "")[:20], "title": _text(a.get("title"), TITLE_MAX) or "announcement"}
        for a in (ann if isinstance(ann, list) else []) if isinstance(a, Mapping)
    ]  # fmt: skip
    return {"releases": releases[:3], "announcements": announcements[:3]} if releases or announcements else None


def _trigger(raw: Any, kind: str = "wakeup") -> dict[str, Any] | None:
    """The trigger of an off-schedule round. Market wake-up: contract and move. AI alert: contract, direction,
    level and its note. Kraken announcement or macro release: titles and labels. The rest (id, internal window)
    is not published. Any trigger can carry news (`news`)."""
    d = raw
    if isinstance(raw, str):
        try:
            d = json.loads(raw)
        except ValueError:
            return None
    if not isinstance(d, Mapping):
        return None
    out = _bare_trigger(d, kind)
    below = d.get("news") if isinstance(d.get("news"), Mapping) else None
    n = _news(below) if below else None
    if n:
        out["news"] = n
    return out


def _bare_trigger(d: Mapping[str, Any], kind: str) -> dict[str, Any]:
    if kind == "news":
        return {"type": "announcement", **(_news(d) or {"releases": [], "announcements": []})}
    if kind == "calendar":
        return {"type": "publication", **(_news(d) or {"releases": [], "announcements": []})}
    if kind == "scheduled":
        due = d.get("due_ts")
        return {"type": "request", "due_ts": due if isinstance(due, int) and not isinstance(due, bool) else None}
    if kind == "cadence":
        return {"type": "cadence"}
    if kind == "alert":
        cond = d.get("condition")
        return {
            "type": "alert", "instrument": short(d.get("instrument")),
            "condition": cond if cond in ("above", "below") else None, "price_uusd": _price_uusd(d.get("price_usd")),
            "note": _text(d.get("note"), NOTE_MAX),
        }  # fmt: skip
    mv = d.get("move_bp")
    return {
        "type": "market",
        "instrument": short(d.get("instrument")),
        "move_bp": mv if isinstance(mv, int) else None,
        "window_s": d.get("window_s") if isinstance(d.get("window_s"), int) else 3600,
    }


def _public_error(parse_error: Any) -> str | None:
    """Failure category, never the raw text (it may quote the CLI, a trace or a path)."""
    if not parse_error:
        return None
    s = str(parse_error).lower()
    if "budget" in s:
        return "call cost ceiling reached"
    if "no structured output" in s:
        return "unreadable response"
    if "invalid decision" in s:
        return "invalid decision"
    if "timeout" in s or "timed out" in s:
        return "timeout"
    return "call failed"


def _public_absence(error: Any) -> str:
    """Why a council member gave no opinion, by category (never the raw text)."""
    s = str(error or "").lower()
    if "timeout" in s or "timed out" in s:
        return "timeout"
    if "budget" in s:
        return "cost ceiling reached"
    if "crash" in s:
        return "internal error"
    if "no opinion" in s or "no structured output" in s:
        return "no opinion given"
    if "expected" in s or "opinions" in s or "unexpected" in s or "out of" in s or "not a number" in s:
        return "invalid opinion"
    return "call failed"


def _number(v: Any) -> float | None:
    """Decimal number as text (council opinion); None if absent or unreadable."""
    if v is None or isinstance(v, bool):
        return None
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        return None
    if not d.is_finite() or abs(d) > 10**12:  # "1e400": unreadable, not infinity
        return None
    return float(d)


def _member_opinions(p: Mapping[str, Any]) -> dict[str, Any]:
    """A `council_opinion` as the site shows it: position, conviction, size, stop and level per contract."""
    key = str(p.get("member") or "")
    name_m, step, role, _src = ALL_MEMBERS.get(key, (_text(p.get("name"), 60) or "Member", str(p.get("stage") or "A"), None, None))
    op = p.get("opinion") if isinstance(p.get("opinion"), Mapping) else None
    out: dict[str, Any] = {
        "member": key, "name": name_m, "step": step, "role": role, "absent": op is None,
        "error": _public_absence(p.get("error")) if op is None else None,
        "opinions": [], "target": None, "argument": None, "tools": [],
    }  # fmt: skip
    if op is None:
        return out
    opinions = op.get("opinions")
    for a in opinions if isinstance(opinions, list) else []:
        if not isinstance(a, Mapping) or a.get("position") not in ("long", "short", "flat"):
            continue
        conv = a.get("conviction")
        lvl = _number(a.get("key_level_usd"))
        out["opinions"].append({
            "instrument": short(a.get("instrument")), "position": a["position"],
            "conviction": conv if isinstance(conv, int) and not isinstance(conv, bool) and 0 <= conv <= 100 else None,
            "size_pct": _number(a.get("size_pct")), "stop_pct": _number(a.get("stop_pct")),
            "level_uusd": round(lvl * 1_000_000) if lvl is not None else None,
        })  # fmt: skip
    c = op.get("target")
    if isinstance(c, Mapping) and c.get("side") in ("long", "short"):
        out["target"] = {"instrument": short(c.get("instrument")), "side": c["side"]}
    out["argument"] = _text(op.get("argument"), ARGUMENT_MAX)
    props = op.get("proposals")
    if isinstance(props, list):  # an adviser of the Trend Council: proposed brakes (0 or 0.5), never a market opinion
        out["proposals"] = [
            {"instrument": short(x.get("instrument")), "coefficient": x.get("coefficient") if x.get("coefficient") in ("0", "0.5") else None,
             "reason": _text(x.get("reason"), 200)}
            for x in props if isinstance(x, Mapping)
        ]  # fmt: skip
    return out


COEFFICIENTS = ("0", "0.5", "1")


def _trend_round(t: Any) -> dict[str, Any] | None:
    """What the Trend Council did in a round (`agent_decision.trend`): the engine's targets (in % of the
    portfolio, signed), the council's coefficients with their reason, and whether the council was called. Nothing else."""
    if not isinstance(t, Mapping):
        return None

    def pcts(raw: Any) -> dict[str, float]:
        return {short(k): v / 100 for k, v in (raw or {}).items() if isinstance(v, int) and not isinstance(v, bool)} if isinstance(raw, Mapping) else {}

    coefs = {}
    for k, c in (t.get("coefficients") or {}).items() if isinstance(t.get("coefficients"), Mapping) else ():
        if isinstance(c, Mapping) and c.get("c") in COEFFICIENTS:
            coefs[short(k)] = {"coefficient": c["c"], "reason": _text(c.get("why"), 200), "until_ts": _integer(c.get("until_ts"))}
    off = t.get("council_off")
    return {
        "type": t.get("kind") if t.get("kind") in ("bar", "veto", "restoration") else None,
        "bar_ts": _integer(t.get("bar_end_ts")), "targets_pct": pcts(t.get("targets_bp")), "final_pct": pcts(t.get("final_bp")),
        "coefficients": coefs, "council_called": bool(t.get("council_called")),
        "council_absent": {"nothing_to_brake": "nothing to brake", "daily_budget": "daily budget reached", "llm_league_off": "AIs switched off", "restoration": "end of a brake", "spot_cycle": "spot league cycle too close"}.get(str(off)) if off else None,
        "president_ok": bool(t.get("president_ok")),
        "incomplete_data": sorted(short(k) for k in t.get("held") or {}) if isinstance(t.get("held"), Mapping) else [],
    }  # fmt: skip


def _tool_args(tool: str, raw: Any) -> str:
    """A tool call's arguments, summarized: \"BTC 4h\", \"ETH 1h ×24\"."""
    try:
        a = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except ValueError:
        return ""
    if not isinstance(a, Mapping):
        return ""
    parts = []
    if isinstance(a.get("instrument"), str):
        parts.append(short(a["instrument"]))
    if tool == "simulate_order" and isinstance(a.get("action"), str) and a["action"] in ACTIONS:
        parts.append(ACTIONS[a["action"]].lower().replace("opens a ", ""))
    if isinstance(a.get("interval"), str):
        parts.append(a["interval"])
    return " ".join(p for p in parts if re.fullmatch(r"[A-Za-z0-9 ]{1,16}", p))


def _series(events: Iterable[Mapping[str, Any]]) -> dict[str, list[tuple[int, int, int]]]:
    out: dict[str, list[tuple[int, int, int]]] = {}
    for e in events:
        if e["type"] == "perp_equity":
            p = e["payload"]
            out.setdefault(p["portfolio"], []).append((p["ts"], p["equity_ueur"], p.get("gross_ueur") or 0))
    for s in out.values():
        s.sort()
    return out


def _drawdowns(equity_track: list[tuple[int, int, int]]) -> tuple[float, float]:
    """(maximum drawdown, current drawdown), as a fraction of the peak."""
    peak, dd_max, dd = 0, 0.0, 0.0
    for _ts, eq, _g in equity_track:
        peak = max(peak, eq)
        dd = (peak - eq) / peak if peak > 0 else 0.0
        dd_max = max(dd_max, dd)
    return dd_max, dd


def _positions(acc: MarginAccount | None, marks: Mapping[str, int], fx: tuple[int, int] | None) -> list[dict[str, Any]]:
    if acc is None:
        return []
    out = []
    for inst, pos in sorted(acc.positions.items()):
        mark = marks.get(inst)
        latent = notional = None
        if isinstance(mark, int) and mark > 0 and fx:
            try:
                latent = to_eur(price_pnl_uusd(pos.qty, pos.entry_uusd, mark), *fx)
            except PerpLedgerError:
                latent = None
            notional = abs(pos.qty) * mark // 100_000_000 * 1_000_000 // ((fx[0] + fx[1]) // 2)
        out.append({
            "instrument": short(inst), "side": "long" if pos.qty > 0 else "short", "qty": abs(pos.qty),
            "entry_uusd": pos.entry_uusd, "mark_uusd": mark if isinstance(mark, int) else None,
            "stop_uusd": pos.stop_uusd, "target_uusd": pos.take_profit_uusd,
            "latent_ueur": latent, "notional_ueur": notional, "since_ts": pos.opened_ts,
            "product": product(inst), "signed_qty": pos.qty,
        })  # fmt: skip
    return out


def _bp_pct(v: Any) -> float | None:
    return v / 100 if isinstance(v, int) and not isinstance(v, bool) else None


def _element(kind: str, d: Mapping[str, Any], created_ts: int | None = None) -> dict[str, Any]:
    """An alert or entry order placed by an AI, as publishable fields (no id, no technical text)."""
    cond = d.get("condition")
    out: dict[str, Any] = {
        "type": "alert" if kind == "alert" else "order", "instrument": short(d.get("instrument")),
        "condition": cond if cond in ("above", "below") else None,
        "price_uusd": d.get("price_uusd") if isinstance(d.get("price_uusd"), int) else None,
        "expire_ts": d.get("expires_ts") if isinstance(d.get("expires_ts"), int) else None, "placed_ts": created_ts,
    }  # fmt: skip
    if kind == "alert":
        out["note"] = _text(d.get("note"), NOTE_MAX)
    else:
        side = d.get("side")
        out.update({
            "side": side if side in ("long", "short") else None, "size_pct": _bp_pct(d.get("size_bp")),
            "stop_pct": _bp_pct(d.get("stop_bp")), "target_pct": _bp_pct(d.get("take_profit_bp")),
            "horizon_h": d.get("horizon_h") if isinstance(d.get("horizon_h"), int) else None,
            "expected_pct": _bp_pct(d.get("expected_move_bp")),
            "confidence_pct": d.get("confidence_pct") if isinstance(d.get("confidence_pct"), (int, float)) else None,
            "invalidation": _text(d.get("invalidation"), INVALIDATION_MAX),
        })  # fmt: skip
    return out


def _pending(events: list[dict[str, Any]], pf: str) -> dict[str, Any]:
    """Alerts and entry orders of `pf`: what is pending (last `agent_orders_set` minus what has fired or ended
    since, computed by the engine) and what happened to the latest elements (replaced ones excluded: each
    decision replaces the whole set, it is not an event)."""
    st = AO.pending_state(events, pf)
    pending = [_element(el.kind, el.data, el.created_ts) for el in st.pending]
    history_items = []
    for oid, el in st.catalog.items():
        x = None
        if oid in st.triggered:
            x = {**_element(el.kind, el.data, el.created_ts), "ts": st.triggered[oid]["ts"], "issue": "fired"}
            if el.kind == "entry":
                ex, v = st.executions.get(oid), st.verdicts.get(oid)
                if v is not None and not v.get("approved"):
                    x["issue_detail"] = "refused by the guardrail"
                elif ex is not None:
                    x["issue_detail"] = EXECUTIONS.get(str(ex.get("status")), "unknown execution")
        elif oid in st.ended and st.ended[oid]["payload"].get("reason") != "replaced":
            r = str(st.ended[oid]["payload"].get("reason"))
            x = {**_element(el.kind, el.data, el.created_ts), "ts": st.ended[oid]["ts"], "issue": "end", "issue_detail": END_REASONS.get(r, "ended")}
        if x is not None:
            history_items.append(x)
    history_items.sort(key=lambda x: x["ts"], reverse=True)
    return {
        "alerts": [x for x in pending if x["type"] == "alert"],
        "orders": [x for x in pending if x["type"] == "order"],
        "history": history_items[:HISTORY_MAX], "n_placed": len(st.catalog),
    }


def _decisions_llm(events: list[dict[str, Any]], pf: str) -> list[dict[str, Any]]:
    """One entry per round played (or skipped) by the LLM portfolio `pf`, from the most recent to the oldest.

    A round = (portfolio, round). Verdicts and executions have no `round`: they follow the same portfolio's
    decision in the journal, and are attached by `intent_id` (fills by `order_id`)."""
    rounds: dict[int, dict[str, Any]] = {}
    per_intent: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    orders: dict[str, Mapping[str, Any]] = {}  # id of an entry order -> the order as placed
    triggered: dict[str, dict[str, Any]] = {}  # id -> "order fired" entry of the timeline

    def fired(oid: str, ts: int, trig: Mapping[str, Any] | None) -> dict[str, Any]:
        """An entry order fired between two rounds: its own entry, which owns the verdict, execution and fills
        (`intent_id` = the order's id), never the latest decision."""
        if oid not in triggered:
            o = orders[oid]
            el = _element("entry", o)
            action = {
                "instrument": el["instrument"], "action": "open_long" if el["side"] == "long" else "open_short",
                "size_pct": el["size_pct"], "stop_pct": el["stop_pct"], "target_pct": el["target_pct"],
                "horizon_h": el["horizon_h"], "expected_pct": el["expected_pct"], "confidence_pct": el["confidence_pct"],
                "invalidation": el["invalidation"], "discarded": False, "verdict": None, "execution": None, "fills": [],
            }  # fmt: skip
            triggered[oid] = {
                "round": ts, "ts": ts, "kind": "order", "status": "fired", "jump": None,
                "trigger": {"type": "order", "instrument": el["instrument"], "condition": el["condition"], "price_uusd": el["price_uusd"]},
                "justification": None, "actions": [action], "tools": [], "error": None, "cost_uusd": None,
                "latency_ms": None, "tokens": None, "placed": None, "recall_ts": None, "council": None,
            }  # fmt: skip
            per_intent[oid] = action
        return triggered[oid]

    def llm_round(r: int, ts: int) -> dict[str, Any]:
        if r not in rounds:
            rounds[r] = {
                "round": r, "ts": ts, "kind": "rendezvous", "trigger": None, "status": "in_progress", "jump": None,
                "justification": None, "actions": [], "tools": [], "error": None, "cost_uusd": None,
                "latency_ms": None, "tokens": None, "placed": None, "recall_ts": None, "council": None, "trend": None,
            }  # fmt: skip
        return rounds[r]

    def council(d: dict[str, Any]) -> dict[str, Any]:
        if d["council"] is None:
            d["council"] = {
                "opinions": [], "members_ok": None, "absent_members": None, "president": None, "chair_cost_uusd": None,
                "model_members": None, "instructions": None, "_tools": {},
            }
        return d["council"]

    for e in events:
        t, p = e["type"], e["payload"]
        if p.get("portfolio") != pf:
            continue
        if t == "round_data":
            d = llm_round(p["round"], e["ts"])
            d["kind"] = p.get("kind") or "rendezvous"
            d["trigger"] = _trigger(p.get("trigger"), d["kind"]) if d["kind"] in ("wakeup", "alert", "scheduled", "cadence", "news", "calendar") else None
            if d["kind"] == "veto":  # a veto round of the Trend Council: its trigger is a wake-up, an announcement or a release
                try:
                    raw_trigger = json.loads(p.get("trigger")) if isinstance(p.get("trigger"), str) else p.get("trigger")
                    k = raw_trigger.get("kind") if isinstance(raw_trigger, Mapping) and raw_trigger.get("kind") in ("wakeup", "news", "calendar") else "wakeup"
                    d["trigger"] = _trigger(raw_trigger, k)
                except ValueError:
                    d["trigger"] = None
        elif t == "tool_call":
            d = llm_round(p["round"], e["ts"])
            tool = str(p.get("tool") or "").removeprefix("mcp__arena__")
            if tool in TOOLS:
                o = {"tool": tool, "args": _tool_args(tool, p.get("arguments")), "error": bool(p.get("is_error"))}
                member = p.get("member")
                if member and member != "president":  # a council member: its tools go to its opinion
                    council(d)["_tools"].setdefault(str(member), []).append(o)
                else:
                    d["tools"].append(o)
        elif t == "council_opinion":
            c = council(llm_round(p["round"], e["ts"]))
            a = _member_opinions(p)
            # The same member replayed in the same round: the last opinion counts, once.
            c["opinions"] = [x for x in c["opinions"] if not (a["member"] and x["member"] == a["member"])] + [a]
        elif t == "perp_llm_skipped":
            d = llm_round(p["round"], e["ts"])
            reason = str(p.get("reason") or "")
            d["status"], d["jump"] = "skipped", JUMPS.get(reason, "preparation failed" if reason.startswith("prepare_error") else "skipped")
        elif t == "agent_decision":
            d = llm_round(p["round"], e["ts"])
            d["kind"] = p.get("kind") or d["kind"]
            parsed = p.get("parsed") if isinstance(p.get("parsed"), Mapping) else None
            d["cost_uusd"] = p.get("cost_uusd")  # for a council: the actual cost of the round (members and President)
            cs = p.get("council")
            if isinstance(cs, Mapping):
                c = council(d)
                c["members_ok"] = cs.get("members_ok") if isinstance(cs.get("members_ok"), int) else None
                mf = cs.get("members_failed")
                c["absent_members"] = len(mf) if isinstance(mf, list) else None
                # Newer fields: absent from older decisions (Haiku President, v1 prompts).
                c["president"] = "Haiku" if cs.get("president_model") is None else _model(cs.get("president_model"))
                c["chair_cost_uusd"] = _integer(cs.get("president_cost_uusd"))
                c["model_members"] = "Haiku" if cs.get("members_model") is None else _model(cs.get("members_model"))
                v = cs.get("prompts_version")
                c["instructions"] = "v1" if v is None else (v if isinstance(v, str) and re.fullmatch(r"v\d{1,3}", v) else None)
            d["trend"] = _trend_round(p.get("trend"))
            d["latency_ms"] = p.get("latency_ms")
            d["tokens"] = (p.get("input_tokens") or 0) + (p.get("output_tokens") or 0) + (p.get("cache_read_tokens") or 0) + (p.get("cache_write_tokens") or 0)
            if parsed is None:
                d["status"], d["error"] = "failure", _public_error(p.get("parse_error")) or "call failed"
            else:
                d["status"] = "decided"
                d["justification"] = _text(parsed.get("justification"), JUSTIFICATION_MAX)
                # `parsed.actions` keeps only the valid actions; `action_errors[].k` indexes the RAW list.
                n_discarded = sum(1 for a in parsed.get("action_errors") or [] if isinstance(a, Mapping))
                for a in parsed.get("actions") or []:
                    if not isinstance(a, Mapping):
                        continue
                    d["actions"].append({
                        "instrument": short(a.get("instrument")), "action": a.get("action"),
                        "size_pct": _pct_str(a.get("size_pct")), "stop_pct": _pct_str(a.get("stop_pct")),
                        "target_pct": _pct_str(a.get("take_profit_pct")), "horizon_h": a.get("horizon_h") if isinstance(a.get("horizon_h"), int) else None,
                        "expected_pct": _pct_str(a.get("expected_move_pct")), "confidence_pct": _pct_str(a.get("confidence_pct")),
                        "invalidation": _text(a.get("invalidation"), INVALIDATION_MAX),
                        "discarded": False, "verdict": None, "execution": None, "fills": [],
                    })  # fmt: skip
                for _ in range(n_discarded):
                    d["actions"].append({"instrument": "?", "action": None, "discarded": True, "verdict": None, "execution": None, "fills": []})
            current = d
            d["_free"] = [a for a in d["actions"] if not a["discarded"]]
        elif t == "agent_orders_set":
            d = llm_round(p["round"], e["ts"])
            al = [x for x in p.get("alerts") or [] if isinstance(x, Mapping)]
            entries = [x for x in p.get("entry_orders") or [] if isinstance(x, Mapping)]
            for o in entries:
                orders[str(o.get("id"))] = o
            rejected = [x for x in p.get("rejected") or [] if isinstance(x, Mapping)]
            d["placed"] = {
                "elements": [_element("alert", x) for x in al] + [_element("entry", x) for x in entries],
                "refused": [{"type": {"alert": "alert", "wakeup": "wakeup"}.get(str(x.get("kind")), "order"), "reason": _public_rejection(x.get("error"), x.get("kind"))} for x in rejected],
            }  # fmt: skip
        elif t == "agent_wakeup_set":
            d = llm_round(p["round"], e["ts"])
            due = p.get("due_ts")
            d["recall_ts"] = due if isinstance(due, int) and not isinstance(due, bool) else None
        elif t == "agent_entry_triggered" and str(p.get("id")) in orders:
            fired(str(p["id"]), e["ts"], p)
        elif t == "perp_verdict" and str(p.get("intent_id")) in orders:
            a = fired(str(p["intent_id"]), e["ts"], None)["actions"][0]
            a["verdict"] = {"approved": bool(p.get("approved")), "reason_list": [str(c) for c in p.get("reasons") or []]}
        elif t == "perp_verdict" and current is not None and p.get("retry_of") is not None:
            a = per_intent.get(str(p["retry_of"]))  # the entry refused for its size, retried smaller: the same action
            if a is not None:
                a["verdict"] = {"approved": bool(p.get("approved")), "reason_list": [str(c) for c in p.get("reasons") or []]}
                a["reduced"] = (a.get("reduced") or 0) + 1
                per_intent[str(p.get("intent_id"))] = a
        elif t == "perp_verdict" and current is not None:
            free = current.get("_free") or []
            a = next((x for x in free if x["verdict"] is None and x["instrument"] == short(p.get("instrument")) and x["action"] == p.get("action")), None)
            a = a or next((x for x in free if x["verdict"] is None), None)
            if a is not None:
                a["verdict"] = {"approved": bool(p.get("approved")), "reason_list": [str(c) for c in p.get("reasons") or []]}
                per_intent[str(p.get("intent_id"))] = a
        elif t == "perp_execution":
            if str(p.get("intent_id")) in orders:
                fired(str(p["intent_id"]), e["ts"], None)
            a = per_intent.get(str(p.get("intent_id")))
            if a is None and current is not None:
                a = next((x for x in current.get("_free") or [] if x["execution"] is None and x["instrument"] == short(p.get("instrument"))), None)
                if a is not None:
                    per_intent[str(p.get("intent_id"))] = a
            if a is not None:
                a["execution"] = str(p.get("status") or "")
        elif t == "perp_fill":
            oid = str(p.get("order_id") or "")
            a = per_intent.get(oid) or per_intent.get(oid.removesuffix(":no-stop"))
            if a is not None:
                a["fills"].append({"price_uusd": p["price_uusd"], "qty": p["qty"], "fees_ueur": p.get("fee_ueur") or 0, "reason": p.get("reason")})
    for d in rounds.values():
        d.pop("_free", None)
        c = d.get("council")
        if c is not None:
            tools = c.pop("_tools")
            for a in c["opinions"]:
                a["tools"] = tools.get(a["member"], [])
            c["opinions"].sort(key=lambda a: ALL_ORDER.index(a["member"]) if a["member"] in ALL_MEMBERS else 99)
    return sorted([*rounds.values(), *triggered.values()], key=lambda d: (d["ts"] if d["kind"] == "order" else d["round"]), reverse=True)


def _pace(
    events: list[dict[str, Any]], pf: str, now: int, ds: list[dict[str, Any]], league: Any, st: dict[str, Any] | None
) -> dict[str, Any] | None:
    """When the AI will be called again: the wake-up it asked for (computed by the engine), the regular call at
    the latest (cadence after its last round), and its rounds of the day against the quota."""
    if league is None:
        return None
    out: dict[str, Any] = {"cadence_min": league.cadence_min, "wakeup_ts": None, "next_ts": None, "quota": None}
    try:
        w = AO.pending_wakeup(events, pf, now)
        out["wakeup_ts"] = w["due_ts"] if w else None
        out["quota"] = round_quota.quota(events, pf, now, league.rounds_per_day, ROUND_OFFSET_S)
    except (KeyError, TypeError, ValueError):
        pass
    stopped = bool(st and st["state"] == "stopped")
    latest = max((d["ts"] for d in ds if d["kind"] != "order"), default=None)
    if league.enabled and league.cadence_min > 0 and latest is not None and not stopped:
        out["next_ts"] = latest + league.cadence_min * 60
    return out


def _random_decisions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The random benchmark's draws, per round (its verdicts follow the `perp_round` in the journal)."""
    rounds: dict[int, dict[str, Any]] = {}
    cur: dict[str, Any] | None = None
    for e in events:
        t, p = e["type"], e["payload"]
        if t == "perp_round":
            cur = rounds.setdefault(p["round"], {
                "round": p["round"], "ts": e["ts"], "kind": p.get("kind") or "rendezvous",
                "trigger": _trigger(p.get("trigger"), "wakeup") if p.get("kind") == "wakeup" else None,
                "status": "decided", "actions": [],
            })  # fmt: skip
        elif t == "perp_verdict" and p.get("portfolio") == RANDOM and cur is not None:
            cur["actions"].append({
                "instrument": short(p.get("instrument")), "action": p.get("action"), "discarded": False,
                "verdict": {"approved": bool(p.get("approved")), "reason_list": [str(c) for c in p.get("reasons") or []]},
                "execution": None, "fills": [], "_id": str(p.get("intent_id")),
            })  # fmt: skip
        elif t == "perp_fill" and p.get("portfolio") == RANDOM and cur is not None:
            for a in cur["actions"]:
                if a["_id"] == p.get("order_id"):
                    a["fills"].append({"price_uusd": p["price_uusd"], "qty": p["qty"], "fees_ueur": p.get("fee_ueur") or 0, "reason": p.get("reason")})
                    a["execution"] = "filled"
    out = [r for r in rounds.values() if r["actions"]]
    for r in out:
        for a in r["actions"]:
            a.pop("_id", None)
    return sorted(out, key=lambda d: d["round"], reverse=True)[:DECISIONS_MAX]


def _calendar(now: int) -> list[dict[str, Any]] | None:
    """The macro releases of the next 7 days (calendar published in advance), or None if the news configuration
    is unreadable: the site then omits the calendar."""
    try:
        cfg = load_news_config()
        out = [
            {"id": str(c.id), "kind": c.kind, "label": _text(c.label, 120) or c.kind.upper(), "ts": c.ts, "recall": c.kind in cfg.wake_kinds}
            for c in cfg.calendar if now <= c.ts <= now + NEWS_S
        ]  # fmt: skip
    except Exception:  # noqa: BLE001 - never a broken page for a missing or malformed configuration
        return None
    return sorted(out, key=lambda c: (c["ts"], c["id"]))


def _announcements(events: list[dict[str, Any]], now: int) -> list[dict[str, Any]]:
    """Kraken derivatives announcements seen in the last 7 days: the latest version of each (source, id)."""
    last: dict[tuple[str, str], tuple[int, Mapping[str, Any]]] = {}
    for e in events:
        if e["type"] == "news_item" and isinstance(e["payload"], Mapping):
            p = e["payload"]
            last[(str(p.get("source")), str(p.get("id")))] = (
                e["ts"],
                p,
            )  # the journal is ordered: the last version wins
    out = []
    for ts, p in last.values():
        update = max(
            _ts(p.get("updated_ts")) or 0, _ts(p.get("published_ts")) or 0, _ts(p.get("fetched_ts")) or 0, ts
        )
        upcoming = (_ts(p.get("starts_ts")) or 0) > now or (_ts(p.get("ends_ts")) or 0) > now
        if update < now - NEWS_S and not upcoming:
            continue
        url = p.get("url")
        ins = p.get("instruments")
        out.append({
            "kind": str(p.get("kind") or "")[:20], "status": str(p.get("status") or "")[:24], "impact": str(p.get("impact") or "")[:20],
            "title": _text(p.get("title"), TITLE_MAX) or "Kraken announcement", "update_ts": update,
            "starts_ts": _ts(p.get("starts_ts")), "ends_ts": _ts(p.get("ends_ts")),
            "instruments": [short(i) for i in ins[:8]] if isinstance(ins, list) else [],
            "url": url if isinstance(url, str) and url.startswith("https://") and len(url) <= 200 else "",
        })  # fmt: skip
    return sorted(out, key=lambda a: a["update_ts"], reverse=True)[:ANNOUNCEMENTS_MAX]


def compute(path: Path, now: int) -> dict[str, Any] | None:
    """Everything the site shows of the derivatives league, or None if its journal does not exist (yet)."""
    path = Path(path)
    if not path.exists():
        return None
    events = list(Journal(path).iter_events(strict=False))
    opened = {e["payload"]["portfolio"]: e for e in events if e["type"] == "portfolio_opened" and e["payload"].get("league", "perp") == "perp"}
    if not opened:
        return None
    report = verify(path)
    try:
        accounts = replay(events)
    except PerpLedgerError:
        accounts = {}
    series = _series(events)
    last_eq: dict[str, Mapping[str, Any]] = {}
    for e in events:
        if e["type"] == "perp_equity":
            last_eq[e["payload"]["portfolio"]] = e["payload"]

    funding: dict[str, list[int]] = {}
    fills: dict[str, list[dict[str, Any]]] = {}
    status: dict[str, dict[str, Any]] = {}
    shocks: dict[str, set[tuple[str, int]]] = {}  # the Wick Hunter: the shocks seen per portfolio (contract, first seen) ...
    signals: dict[str, str] = {}  # ... and their intended orders (id -> portfolio), to count the trades
    orders: set[str] = set()
    retired: dict[str, dict[str, Any]] = {}  # archived portfolios (portfolio_retired): their data is frozen
    for e in events:
        t, p = e["type"], e["payload"]
        pf = p.get("portfolio")
        if t == "portfolio_retired" and pf not in retired:
            # the operator's free-text note stays in the journal: it may name people (never published)
            retired[pf] = {"ts": e["ts"], "reason": _text(p.get("reason"), 80)}
        if t == "funding":
            funding.setdefault(pf, []).append(int(p.get("amount_ueur") or 0))
        elif t == "hunter_signal":
            # a shock = one episode (contract, first seen): retries after a refusal add none
            first_seen = int(p.get("first_seen_ts", p.get("ts", e["ts"])))
            shocks.setdefault(pf, set()).add((str(p.get("instrument")), first_seen))
            signals[str(p.get("intent_id"))] = pf
        elif t == "perp_fill":
            orders.add(str(p["order_id"]).split(":")[0])  # a reduced order has the ":s1" suffix of the intended order
            fills.setdefault(pf, []).append({
                "ts": e["ts"], "instrument": short(p.get("instrument")), "qty": p["qty"], "price_uusd": p["price_uusd"],
                "fees_ueur": p.get("fee_ueur") or 0, "reason": FILL_REASONS.get(str(p.get("reason")), str(p.get("reason"))),
            })  # fmt: skip
        elif t == "portfolio_halted":
            status[pf] = {"state": "stopped", "until": None, "ts": e["ts"], "reason": p.get("reason")}
        elif t == "portfolio_frozen":
            status[pf] = {"state": "frozen", "until": p.get("until_ts"), "ts": e["ts"], "reason": p.get("reason")}
        elif t == "portfolio_resumed":
            status.pop(pf, None)

    try:
        llm_league = load_llm_league()
    except (LlmConfigError, OSError, ValueError):  # without a readable configuration, neither quota nor cadence is shown
        llm_league = None

    def rank(x: str) -> tuple[int, str]:
        return (ORDER.index(x) if x in ORDER else 99, x)

    def category(o: Mapping[str, Any]) -> str:
        return {"llm": "llm", "council": "council", "robot": "robot"}.get(str(o.get("kind")), "benchmark")

    per_kind = {g: sorted((pf for pf, e in opened.items() if category(e["payload"]) == g), key=rank) for g in ("llm", "council", "robot", "benchmark")}

    portfolios = []
    for pf in per_kind["llm"] + per_kind["council"] + per_kind["robot"] + per_kind["benchmark"]:
        o = opened[pf]["payload"]
        capital = int(o["capital_ueur"])
        latest = last_eq.get(pf)
        equity = int(latest["equity_ueur"]) if latest else capital
        gross = int(latest.get("gross_ueur") or 0) if latest else 0
        fx = (int(latest["fx_bid"]), int(latest["fx_ask"])) if latest and latest.get("fx_bid") and latest.get("fx_ask") else None
        dd_max, dd = _drawdowns(series.get(pf, []))
        f = funding.get(pf, [])
        acc = accounts.get(pf)
        kind = category(o)
        st = status.get(pf)
        if st and st["state"] == "frozen" and (st["until"] or 0) <= now:
            st = None
        p_out: dict[str, Any] = {
            "id": pf, "slug": slug(pf), "name": name(pf), "kind": kind, "description": DESCRIPTIONS.get(pf),
            "open_ts": opened[pf]["ts"],
            "capital_ueur": capital, "equity_ueur": equity, "net_return": equity / capital - 1 if capital else None,
            "drawdown_max": dd_max, "drawdown": dd, "leverage": gross / equity if equity > 0 else None,
            "expo_ueur": gross, "positions": _positions(acc, (latest or {}).get("marks") or {}, fx),
            "fees_ueur": acc.fees_paid_ueur if acc else sum(x["fees_ueur"] for x in fills.get(pf, [])),
            "funding_paid_ueur": sum(x for x in f if x > 0), "funding_received_ueur": -sum(x for x in f if x < 0),
            "funding_net_ueur": sum(f), "n_operations": len(fills.get(pf, [])), "status": st,
            "operations": list(reversed(fills.get(pf, [])))[:OPERATIONS_MAX], "decisions": [],
            "cost_uusd": None, "n_rounds": 0, "n_orders": 0, "fx": list(fx) if fx else None,
            "archive": retired.get(pf),
        }  # fmt: skip
        if pf in (COUNCIL_TREND, TREND_ENGINE):
            p_out["daily_target"] = _daily_target(capital, equity, opened[pf]["ts"], now)
        if pf == TREND_ENGINE:
            p_out["badge"] = TREND_BADGE
        if kind == "robot":
            p_out["badge"], p_out["subtitle"], p_out["rule"] = ROBOT_BADGE, ROBOT_SUBTITLES.get(pf), ROBOT_RULE
            p_out["n_shocks"] = len(shocks.get(pf, ()))
            p_out["n_trades"] = sum(1 for iid, owner in signals.items() if owner == pf and iid in orders)
        if kind in ("llm", "council"):
            ds = _decisions_llm(events, pf)  # all of them: the totals cover the whole journal
            if kind == "council":
                n_delib = 0
                for d in ds:
                    d["rules"] = "trend" if pf == COUNCIL_TREND else "council"  # its refusals read against the bounds of its own policy
                    c = d.get("council")
                    n_delib += 1 if c else 0
                    if c and n_delib > DELIBERATIONS_MAX:  # keeps the page light: ~150 rounds a day, 9 opinions each
                        c["opinions_outside_page"], c["opinions"] = len(c["opinions"]), []
                p_out["badge"], p_out["outside_rule"] = (TREND_BADGE if pf == COUNCIL_TREND else COUNCIL_BADGE), COUNCIL_OUTSIDE_RULE
                p_out["subtitle"] = SUBTITLES.get(pf)
                p_out["chair_cost_uusd"] = sum((d.get("council") or {}).get("chair_cost_uusd") or 0 for d in ds)
                p_out["president"] = next(((d["council"] or {}).get("president") for d in ds if d.get("council") and d["council"].get("president")), None)
                p_out["budget_usd"] = COUNCIL_BUDGETS_USD.get(pf)
            p_out["decisions"] = ds[:DECISIONS_MAX]
            p_out["n_decisions_total"] = len(ds)
            p_out["cost_uusd"] = sum(d["cost_uusd"] or 0 for d in ds)
            p_out["n_rounds"] = sum(1 for d in ds if d["status"] == "decided")
            p_out["n_triggered"] = sum(1 for d in ds if d["kind"] == "order")
            try:
                p_out["pending"] = _pending(events, pf)
            except (KeyError, TypeError, ValueError):  # a malformed event does not break the page
                p_out["pending"] = None
            p_out["n_orders"] = sum(1 for d in ds for a in d["actions"] if a["fills"])
            p_out["pace"] = _pace(events, pf, now, ds, llm_league, {"state": "stopped"} if pf in retired else st)  # archived: no call scheduled
        elif pf == RANDOM:
            p_out["decisions"] = _random_decisions(events)
        portfolios.append(p_out)

    rounds = [e for e in events if e["type"] == "perp_round"]
    done_rounds = {e["payload"]["round"] for e in events if e["type"] == "perp_round_done"}
    common = {
        "venue_mode": next((e["payload"].get("venue_mode", "paper") for e in opened.values()), "paper"),
        "next_scheduled_round_ts": next_scheduled_round(now),
        "n_rounds": len(done_rounds), "last_round_ts": max((e["payload"]["round"] for e in rounds), default=None),
        "journal": {"verify_ok": report.ok, "n_records": report.n_records},
        "cadence_min": llm_league.cadence_min if llm_league and llm_league.enabled else 0,
        "rounds_per_day": llm_league.rounds_per_day if llm_league else None,
        "news": {"calendar": _calendar(now), "announcements": _announcements(events, now)},
    }  # fmt: skip

    def league(pfs: list[dict[str, Any]]) -> dict[str, Any]:
        """A league: its portfolios, its curve (base 100 at capital, one point every 30 min and the last reading)."""
        ids = {p["id"] for p in pfs}
        all_ts = sorted({ts for pf in ids for ts, _e, _g in series.get(pf, [])})
        xs: list[int] = []
        for ts in all_ts:
            if not xs or ts // CURVE_STEP_S != xs[-1] // CURVE_STEP_S:
                xs.append(ts)
            else:
                xs[-1] = ts if ts == all_ts[-1] else xs[-1]
        if all_ts and xs[-1] != all_ts[-1]:
            xs.append(all_ts[-1])
        for p_out in pfs:  # an archived portfolio's curve stops at its withdrawal: that point must exist
            end = (p_out.get("archive") or {}).get("ts")
            if end is not None and end not in xs and xs and xs[0] < end < xs[-1]:
                xs.append(end)
                xs.sort()
        chart_series = []
        for p_out in pfs:
            s = series.get(p_out["id"], [])
            vals: list[float | None] = []
            j, last = 0, None
            end = (p_out.get("archive") or {}).get("ts")
            for x in xs:
                while j < len(s) and s[j][0] <= x:
                    last = s[j][1]
                    j += 1
                vals.append(None if last is None or (end is not None and x > end) else round(last / p_out["capital_ueur"] * 100, 4))
            track = {"id": p_out["id"], "slug": p_out["slug"], "name": p_out["name"], "kind": p_out["kind"], "values": vals}
            if end is not None:
                track["archive_ts"] = end
            chart_series.append(track)
        live = [last_eq[pf]["ts"] for pf in ids if pf in last_eq]
        return {
            **common, "opened_ts": min((opened[pf]["ts"] for pf in ids), default=None), "live_ts": max(live, default=None),
            "llms_present": any(p["kind"] == "llm" for p in pfs), "portfolios": pfs,
            "chart": {"x": xs, "kinds": ["watch"] * len(xs), "series": chart_series},
        }  # fmt: skip

    # The councils have their own league: the basket benchmark is their reference, without leaving the derivatives
    # league; the "engine only" benchmark belongs to that league alone.
    deriv = league([p for p in portfolios if p["kind"] != "council" and p["id"] != TREND_ENGINE])
    councils = [p for p in portfolios if p["kind"] == "council"]
    basket = [p for p in portfolios if p["id"] == BASKET]
    engine = [p for p in portfolios if p["id"] == TREND_ENGINE]
    # The engine benchmark first: its curve (a ribbon) passes under the council's, which stays readable on top.
    deriv["councils"] = league(engine + councils + basket) if councils else None
    return deriv
