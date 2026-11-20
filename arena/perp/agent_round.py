"""One agent round for one portfolio of the perp league (study §2.3), end to end:

1. a round is played once: if the journal already holds its `round_data` for this portfolio, nothing runs
   (no second paid call, no rebuilt data);
2. the round's data are frozen in `var-perp/rounds/<round>/<portfolio>/round.json` (sha256 journaled in
   `round_data`, with the trigger and the sha256 of the exact first message), with the riskd inputs as they
   are now;
3. the model is called (`AgentDecider`), with the snapshot as its first message;
4. every tool call is journaled (`tool_call`, the response kept as a JSON TEXT, never as numbers), then the
   decision (`agent_decision`: tokens, equivalent cost, latency, turns, attempts, CLI return code and stderr
   tail, stream sha256, errors);
5. each intent goes through riskd (`perp_verdict`) AFTER the call, on the state at that moment (kill switch
   re-read, the second action after the fill of the first), and each approved one through the simulator,
   with its stop and take-profit. Every outcome is a `perp_execution` event. A position whose stop cannot be
   set is closed at once: a position never stays open without a stop.

The journal stays the only source of truth, written by this process only (the MCP server writes nothing but
its local trace).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from arena.perp.agent import AgentDecider, AgentResult, cli_version, parse_decision
from arena.perp.agent_orders import pending_state, pending_wakeup, validate_levels
from arena.perp.counters import counters_for
from arena.perp.ledger import (
    BP,
    PerpLedgerError,
    equity_ueur,
    gross_exposure_ueur,
    price_pnl_uusd,
    to_eur,
)
from arena.perp.mcp_server import eur, pct_e12_hour, qty, usd
from arena.perp.news import NewsConfig
from arena.perp.policy import AGGRESSIVE, PerpPolicy
from arena.perp.riskd import (
    INITIAL_MARGIN,
    LIQUIDATION_BEFORE_STOP,
    MAX_LEVERAGE,
    MAX_OPEN_RISK,
    MAX_ORDER_SIZE,
    MAX_POSITION,
    MAX_TRADE_LOSS,
    PerpIntent,
    PerpMarketView,
    evaluate_perp,
)
from arena.perp.round_data import build_round
from arena.perp.sim import PerpSimulator
from arena.perp.store import PerpDataStore
from arena.perp.types import InstrumentSpec


def _pct(bp: int | None) -> str | None:
    return None if bp is None else format((Decimal(bp) / 100).normalize(), "f")


def _utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


_KIND_LABELS = {"alert": "alert", "entry": "entry_order", "wakeup": "wakeup"}


def rounds_snapshot(rounds: Mapping[str, Any] | None) -> dict[str, Any]:
    """The agent's rounds of the day and its pending wake-up."""
    if not rounds:
        return {}
    q = rounds.get("quota")
    due = rounds.get("next_wakeup_ts")
    out: dict[str, Any] = {"wakeup_requested_utc": _utc(due) if due is not None else None}
    if q:
        out |= {
            "rounds_per_day": q["per_day"],
            "rounds_played_today": q["played_today"],
            "scheduled_rounds_left_today": q["rendezvous_left"],
            # this round is not counted in played_today yet: what is left once it is played
            "unscheduled_rounds_left": max(0, q["extra_left"] - 1),
        }
    return {"rounds": out}


def orders_snapshot(view: Mapping[str, Any]) -> dict[str, Any]:
    """The agent's own alerts and entry orders for the snapshot."""
    since = view["since"]
    return {
        "pending_alerts": [
            {
                "instrument": a["instrument"],
                "condition": a["condition"],
                "level_usd": usd(a["price_uusd"]),
                "expiry_utc": _utc(a["expires_ts"]),
                "note": a.get("note"),
            }
            for a in view["alerts"]
        ],
        "pending_entry_orders": [
            {
                "instrument": o["instrument"],
                "side": o["side"],
                "condition": o["condition"],
                "level_usd": usd(o["price_uusd"]),
                "size_pct": _pct(o["size_bp"]),
                "stop_pct": _pct(o["stop_bp"]),
                "target_pct": _pct(o["take_profit_bp"]),
                "horizon_h": o["horizon_h"],
                "expected_move_pct": _pct(o["expected_move_bp"]),
                "confidence_pct": o["confidence_pct"],
                "invalidation": o["invalidation"],
                "expiry_utc": _utc(o["expires_ts"]),
            }
            for o in view["entries"]
        ],
        "since_your_last_round": {
            "alerts_triggered": [
                {
                    "instrument": a["instrument"],
                    "condition": a["condition"],
                    "level_usd": usd(a["price_uusd"]),
                    "minute_utc": _utc(a["minute"]),
                    "note": a["note"],
                }
                for a in since["alerts_triggered"]
            ],
            "orders_triggered": [
                {
                    "instrument": o["instrument"],
                    "side": o["side"],
                    "condition": o["condition"],
                    "level_usd": usd(o["price_uusd"]),
                    "minute_utc": _utc(o["minute"]),
                    "guardrail": None
                    if o["approved"] is None
                    else ("approved" if o["approved"] else "refused"),
                    "refusal_reasons": o["reasons"],
                    "execution": o["status"],
                    "fill_price_usd": usd(o["fill_price_uusd"]),
                    "invalidation": o.get("invalidation"),
                }
                for o in since["entries_triggered"]
            ],
            "expired_items": [
                {
                    "type": "alert" if x["kind"] == "alert" else "entry_order",
                    "instrument": x["instrument"],
                    "condition": x["condition"],
                    "level_usd": usd(x["price_uusd"]),
                    "reason": x["reason"],
                }
                for x in since["ended"]
            ],
            "rejected_items": [
                {
                    "type": _KIND_LABELS.get(x["kind"], x["kind"]),
                    "rank": x["k"],
                    "error": x["error"],
                }
                for x in since["rejected"]
            ],
        },
    }


STANDARD_RULES = (
    "max leverage 2x, mandatory stop 1-15%, loss at stop <= 3% (all stops <= 7.5%), 4 opens / 24 h"
)


def _pct_text(bp: int) -> str:
    return format((Decimal(bp) / 100).normalize(), "f")


def rules_text(policy: Mapping[str, Any] | None) -> str:
    """The rules line of the snapshot: the standard one, or the council's from its own policy."""
    if not policy or policy.get("profile") != AGGRESSIVE:
        return STANDARD_RULES
    p = policy
    return (
        f"max leverage {p['max_leverage_bp'] // BP}x (Kraken margins), entry <= {_pct_text(p['max_order_bp'])}% "
        f"of equity, position <= {_pct_text(p['max_position_bp'])}%, mandatory stop "
        f"{_pct_text(p['stop_bp_min'])}-{_pct_text(p['stop_bp_max'])}% and before liquidation, loss at stop "
        f"<= {_pct_text(p['max_trade_loss_bp'])}% (all stops <= {_pct_text(p['max_open_risk_bp'])}%), "
        f"{p['max_opens_per_day']} opens / 24 h, halt at -{_pct_text(p['drawdown_halt_bp'])}% from the peak"
    )


NEWS_KIND_LABELS = {
    "incident": "incident",
    "maintenance": "maintenance",
    "delisting": "contract delisting",
    "contract_state": "contract state",
}
NEWS_NOTE = (
    "Official Kraken announcements (derivatives status page, state of each contract), collected every "
    "5 minutes, and the calendar of US releases. The published figures (CPI, jobs...) are not provided: "
    "only the market's reaction shows them."
)


def news_snapshot(news: Mapping[str, Any], now: int) -> dict[str, Any]:
    """The `news` block (docs/SPEC-PERP-NEWS.md §5): times in UTC seconds."""
    return {
        "macro_calendar": [
            {
                "publication": e["label"],
                "type": e["kind"],
                "time_utc": e["ts"],
                "in_min": (e["ts"] - now) // 60,
                "remind_me": e["wakes"],
            }
            for e in news.get("calendar", [])
        ],
        "kraken_announcements": [
            {
                "title": a["title"],
                "type": NEWS_KIND_LABELS.get(a["kind"], a["kind"]),
                "status": a["status"],
                "impact": a["impact"],
                "start_utc": a.get("starts_ts"),
                "end_utc": a.get("ends_ts"),
                "seen_at_utc": a["seen_ts"],
                "contracts": a.get("instruments", []),
            }
            for a in news.get("announcements", [])
        ],
        "note": NEWS_NOTE,
    }


def snapshot(data: Mapping[str, Any], kind: str, trigger: Mapping[str, Any] | None) -> dict[str, Any]:
    """The first message: compact (the tools give the detail), with what the prompt promises: positions and
    their unrealized P&L, equity, leverage, open interest."""
    now = data["meta"]["now_ts"]
    acc = data["account"]
    view = data["view"]["instruments"]
    fx = (data["view"]["fx_bid"], data["view"]["fx_ask"])
    market = {}
    for s, m in data["market"].items():
        h1 = m["candles_1h"]
        last = h1[-1][4] if h1 else None

        def ret(n: int, h1: list[list[int]] = h1, last: int | None = last) -> int | None:
            return (last - h1[-1 - n][4]) * BP // h1[-1 - n][4] if last and len(h1) > n else None

        v = view.get(s, {})
        oi = m.get("open_interest") or []
        market[s] = {
            "mark_usd": usd(v.get("mark_uusd")),
            "bid_usd": usd(v.get("bid_uusd")),
            "ask_usd": usd(v.get("ask_uusd")),
            "ret_1h_bp": ret(1),
            "ret_4h_bp": ret(4),
            "ret_24h_bp": ret(24),
            "funding_pct_hour": pct_e12_hour(v.get("relative_funding_e12")),
            "open_interest": qty(oi[-1][1]) if oi else None,
        }
    positions, unrealized, gross = {}, 0, 0
    for i, p in acc["positions"].items():
        mark = view.get(i, {}).get("mark_uusd")
        pnl = to_eur(price_pnl_uusd(p["qty"], p["entry_uusd"], mark), *fx) if mark else None
        unrealized += pnl or 0
        if mark:
            gross += to_eur(abs(p["qty"]) * mark // 100_000_000, *fx)
        positions[i] = {
            "quantity": qty(p["qty"]),
            "side": "long" if p["qty"] > 0 else "short",
            "entry_usd": usd(p["entry_uusd"]),
            "mark_usd": usd(mark),
            "pnl_latent_eur": eur(pnl),
            "stop_usd": usd(p["stop_uusd"]),
            "target_usd": usd(p["take_profit_uusd"]),
            "open_since_h": (now - p["opened_ts"]) // 3600,
        }
    equity = acc["collateral_ueur"] + unrealized
    invalidations = [
        {
            "ts": h["ts"],
            "actions": [
                {"instrument": a.get("instrument"), "invalidation": a.get("invalidation")}
                for a in h["actions"]
            ],
        }
        for h in data["history"]
        if h.get("actions")
    ][-3:]
    out = {
        "time_utc": now,
        "call": {"type": kind, "trigger": trigger},
        "account": {
            "collateral_eur": eur(acc["collateral_ueur"]),
            "equity_eur": eur(equity),
            "leverage_bp": gross * BP // equity if equity > 0 else None,
            "funding_paid_eur": eur(acc["funding_paid_ueur"]),
            "fees_paid_eur": eur(acc["fees_paid_ueur"]),
            "frozen_until": acc["frozen_until_ts"] or None,
            "stopped": acc["halted"],
            "blocked_entries": bool(data["meta"].get("entries_blocked")),
            "positions": positions,
            **orders_snapshot(data["agent_orders"]),
            **rounds_snapshot(data.get("rounds")),
        },
        "market": market,
        "your_invalidation_conditions": invalidations,
        "rules": rules_text(data.get("policy")),
    }
    if data.get("news") is not None:
        out["news"] = news_snapshot(data["news"], now)
    return out


def _blocked(entries_blocked: bool | Callable[[], bool]) -> bool:
    return bool(entries_blocked()) if callable(entries_blocked) else bool(entries_blocked)


@dataclass
class RoundContext:
    """What `prepare_agent_round` built and journaled, for the call and for `finish_agent_round`."""

    var: Path
    sim: PerpSimulator
    decider: AgentDecider
    view: PerpMarketView
    specs: Mapping[str, InstrumentSpec]
    policy: PerpPolicy
    round_id: int
    now_ts: int
    kind: str
    entries_blocked: bool | Callable[[], bool]
    out_dir: Path
    snapshot: dict[str, Any]

    @property
    def name(self) -> str:
        return self.decider.portfolio


def run_agent_round(
    *,
    var: Path,
    sim: PerpSimulator,
    store: PerpDataStore,
    decider: AgentDecider,
    view: PerpMarketView,
    specs: Mapping[str, InstrumentSpec],
    policy: PerpPolicy,
    config_sha256: str,
    round_id: int,
    now_ts: int,
    kind: str,
    trigger: Mapping[str, Any] | None,
    entries_blocked: bool | Callable[[], bool],
) -> AgentResult:
    """`entries_blocked` may be a callable: it is then read again for every intent, after the model call."""
    ctx = prepare_agent_round(
        var=var, sim=sim, store=store, decider=decider, view=view, specs=specs, policy=policy,
        config_sha256=config_sha256, round_id=round_id, now_ts=now_ts, kind=kind, trigger=trigger,
        entries_blocked=entries_blocked,
    )  # fmt: skip
    if isinstance(ctx, AgentResult):
        return ctx
    try:
        res = decider.decide(ctx.out_dir, ctx.snapshot)
    except Exception as exc:  # noqa: BLE001 (the decision event is always written)
        res = AgentResult(error=f"decider crashed: {type(exc).__name__}: {str(exc)[:200]}")
    finish_agent_round(ctx, res)
    return res


def prepare_agent_round(
    *,
    var: Path,
    sim: PerpSimulator,
    store: PerpDataStore,
    decider: AgentDecider,
    view: PerpMarketView,
    specs: Mapping[str, InstrumentSpec],
    policy: PerpPolicy,
    config_sha256: str,
    round_id: int,
    now_ts: int,
    kind: str,
    trigger: Mapping[str, Any] | None,
    entries_blocked: bool | Callable[[], bool],
    extra: Mapping[str, Any] | None = None,
    quota: Mapping[str, int] | None = None,
    snapshot_extra: Mapping[str, Any] | None = None,
    news: NewsConfig | None = None,
) -> RoundContext | AgentResult:
    """Freezes and journals the round's data (`round_data`); an AgentResult with an error if this portfolio
    already played this round. Thread-free: the caller may run `decider.decide` in parallel afterwards.

    `snapshot_extra`: more top-level blocks of the snapshot (the council's record), in the message hashed."""
    name = decider.portfolio
    events = sim.journal.events()
    if any(
        e["type"] == "round_data"
        and e["payload"].get("portfolio") == name
        and e["payload"].get("round") == round_id
        for e in events
    ):
        return AgentResult(error=f"round {round_id} already played for {name}: never played twice")
    acc = sim.states()[name]
    counters = counters_for(events, name, now_ts)
    out_dir = var / "rounds" / str(round_id) / name.replace(":", "_")
    data, sha = build_round(
        out_dir, store, events, view, acc, counters, specs, policy, sim.params, round_id, now_ts,
        config_sha256, _blocked(entries_blocked), quota=quota, news=news,
    )  # fmt: skip
    snap = {**snapshot(data, kind, trigger), **dict(snapshot_extra or {})}
    message = decider.message(snap)
    sim.append_event(
        "round_data",
        {
            "portfolio": name,
            "round": round_id,
            "kind": kind,
            "trigger": json.dumps(trigger, sort_keys=True, ensure_ascii=False, default=str),
            "sha256": sha,
            "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
            "path": str(out_dir.relative_to(var)),
            **dict(extra or {}),
        },
        now_ts,
    )
    return RoundContext(
        var, sim, decider, view, specs, policy, round_id, now_ts, kind, entries_blocked, out_dir, snap,
    )  # fmt: skip


def finish_agent_round(
    ctx: RoundContext, res: AgentResult, extra: Mapping[str, Any] | None = None, *, execute: bool = True
) -> None:
    """Journals the tool calls and the decision, then judges and executes each intent, in order."""
    sim, name, round_id, now_ts, view = ctx.sim, ctx.name, ctx.round_id, ctx.now_ts, ctx.view
    for op in res.council:  # the council's members, before its decision (docs/SPEC-PERP-COUNCIL-HAIKU.md §3)
        sim.append_event("council_opinion", {"portfolio": name, "round": round_id, **op}, now_ts)
    for call in res.tool_calls:
        sim.append_event(
            "tool_call",
            {
                "portfolio": name,
                "round": round_id,
                "n": call.n,
                "tool": call.tool,
                "arguments": call.arguments,
                "response": call.response[:20_000],
                "response_sha256": hashlib.sha256(call.response.encode()).hexdigest(),
                "is_error": call.is_error,
                **({"member": call.member} if call.member is not None else {}),
            },
            now_ts,
        )
    parsed, perr, intents = (None, res.error, [])
    if res.decision is not None:
        parsed, perr, intents = parse_decision(
            res.decision, name, round_id, now_ts,
            max_size_pct=getattr(ctx.decider, "max_size_pct", None),
            max_actions=getattr(ctx.decider, "max_actions", 2),
        )  # fmt: skip
    sim.append_event(
        "agent_decision",
        {
            "portfolio": name,
            "round": round_id,
            "kind": ctx.kind,
            "model_requested": ctx.decider.model,
            "model_returned": res.model_returned,
            "prompt_sha256": ctx.decider.prompt_digest(),
            "parsed": parsed,
            "parse_error": perr,
            "tool_calls": len(res.tool_calls),
            "num_turns": res.num_turns,
            "input_tokens": res.input_tokens,
            "output_tokens": res.output_tokens,
            "cache_read_tokens": res.cache_read_tokens,
            "cache_write_tokens": res.cache_write_tokens,
            "cost_uusd": res.cost_uusd,
            "latency_ms": res.latency_ms,
            "attempts": res.attempts,
            "first_error": res.first_error,
            "cli_rc": res.rc,
            "cli_version": cli_version(),
            "stderr_tail": res.stderr_tail[-300:],
            "mcp_status": res.mcp_status,
            "tools_offered": res.tools_offered,
            "stream_sha256": res.stream_sha256,
            **res.extra,
            **dict(extra or {}),
        },
        now_ts,
    )
    run_intents(
        sim, name, intents, view, ctx.specs, ctx.policy, now_ts, ctx.entries_blocked,
        execute=execute, shrink=bool(getattr(ctx.decider, "shrink_on_refusal", False)),
    )  # fmt: skip
    # only a valid decision applied on a fresh market replaces the pending set (without a fresh view, its levels
    # could not be checked on the market of the moment: the set in place stays, like after no decision)
    if parsed is not None and perr is None and execute:
        for code, step in (
            ("perp_agent_orders_failed", _set_agent_orders),
            ("perp_agent_wakeup_failed", _set_wakeup),
        ):
            try:
                step(ctx, parsed)
            except Exception as exc:  # noqa: BLE001 (the actions are done: the failure is journaled, never raised)
                sim.append_event(
                    "alert",
                    {
                        "level": "action",
                        "code": code,
                        "message": f"{name} round {round_id}: {type(exc).__name__}: {exc}"[:1000],
                    },
                    now_ts,
                )


# Refusals a smaller order may cure (the council v4 retries them smaller): size, loss at the stop, leverage, margin.
SHRINKABLE = frozenset(
    {
        MAX_TRADE_LOSS, MAX_OPEN_RISK, LIQUIDATION_BEFORE_STOP, MAX_LEVERAGE, INITIAL_MARGIN, MAX_POSITION,
        MAX_ORDER_SIZE,
    }
)  # fmt: skip
SHRINK_TRIES = 8  # each try keeps 3/4 of the size: 8 tries go down to a tenth
SHRINK_NUM, SHRINK_DEN = 3, 4


def run_intents(
    sim: PerpSimulator,
    name: str,
    intents: Sequence[PerpIntent],
    view: PerpMarketView,
    specs: Mapping[str, InstrumentSpec],
    policy: PerpPolicy,
    now_ts: int,
    entries_blocked: bool | Callable[[], bool],
    *,
    execute: bool = True,
    shrink: bool = False,
    max_shrink_tries: int = SHRINK_TRIES,
) -> None:
    """Judges each intent by riskd (`perp_verdict`) on the state at that moment, then executes the approved ones
    (`perp_execution`). One path for the agents and for the shadow benchmark of the council v4.

    `shrink`: an entry refused only for its size (`SHRINKABLE`) is retried with 3/4 of the size, at most
    `max_shrink_tries` times (`SHRINK_TRIES` by default), instead of being dropped; each try has its own verdict (`retry_of`, `shrink_step`)."""
    quotes = {s: (m.bid_uusd, m.ask_uusd) for s, m in view.instruments.items()}
    marks = {s: m.mark_uusd for s, m in view.instruments.items()}
    fx = (view.fx_bid, view.fx_ask)
    for it in intents:
        if not execute:  # no fresh market view after the call: journaled, never executed at stale prices
            sim.append_event(
                "perp_execution",
                {
                    "intent_id": it.intent_id,
                    "portfolio": name,
                    "instrument": it.instrument,
                    "status": "not_executed_view_stale",
                    "error": None,
                },
                now_ts,
            )
            continue
        attempt, step = it, 0
        while True:
            acc = sim.states()[name]
            c = counters_for(sim.journal.events(), name, now_ts)
            v = evaluate_perp(
                attempt, acc, view, specs, c, policy, sim.params, now_ts, _blocked(entries_blocked)
            )
            sim.append_event(
                "perp_verdict",
                {
                    "intent_id": attempt.intent_id,
                    "portfolio": name,
                    "instrument": attempt.instrument,
                    "action": attempt.action,
                    "approved": v.approved,
                    "reasons": list(v.reasons),
                    "qty": v.qty,
                    "policy_sha256": v.policy_sha256,
                    "error": v.error,
                    **({"retry_of": it.intent_id, "shrink_step": step, "size_bp": attempt.size_bp} if step else {}),
                },
                now_ts,
            )  # fmt: skip
            if v.approved:
                _execute(
                    sim,
                    name,
                    attempt.intent_id,
                    attempt.instrument,
                    attempt.action,
                    v,
                    quotes,
                    marks,
                    fx,
                    now_ts,
                )
                break
            if (
                not shrink
                or not attempt.action.startswith("open")
                or not v.reasons
                or not set(v.reasons) <= SHRINKABLE
                or step >= max_shrink_tries
                or not attempt.size_bp
            ):
                break
            step += 1
            smaller = attempt.size_bp * SHRINK_NUM // SHRINK_DEN
            if smaller <= 0:
                break
            attempt = replace(attempt, intent_id=f"{it.intent_id}:s{step}", size_bp=smaller)


def _set_wakeup(ctx: RoundContext, parsed: Mapping[str, Any]) -> None:
    """A valid decision replaces the wake-up the portfolio asked for: `agent_wakeup_set` with the time asked
    (counted from when the decision is applied), or with `due_ts` null when it asks none and one is pending."""
    if parsed.get("next_wakeup_invalid"):
        return  # an invalid time asks nothing and cancels nothing: the pending wake-up stays
    minutes = parsed.get("next_wakeup_min")
    if minutes is None and pending_wakeup(ctx.sim.journal.events(), ctx.name, ctx.now_ts) is None:
        return
    ctx.sim.append_event(
        "agent_wakeup_set",
        {
            "portfolio": ctx.name,
            "round": ctx.round_id,
            "minutes": minutes,
            "due_ts": None if minutes is None else ctx.now_ts + int(minutes) * 60,
        },
        ctx.now_ts,
    )


def _set_agent_orders(ctx: RoundContext, parsed: Mapping[str, Any]) -> None:
    """A valid decision replaces the portfolio's whole set of alerts and entry orders: `agent_orders_set`,
    then one `agent_order_ended` (`replaced`) per element of the previous set still pending (a restated
    element is a new element of the new set).

    The levels are checked on the market as it is when the decision is applied (`ctx.view`, read again after
    the call), and the elements count from that time (`created_ts`): a level crossed while the model was
    thinking is rejected as already crossed, never filled on minutes the model did not see."""
    sim, name = ctx.sim, ctx.name
    created_ts = ctx.now_ts
    marks = {s: m.mark_uusd for s, m in ctx.view.instruments.items()}
    alerts, entries, rejected = validate_levels(parsed, marks)

    def final(el: Mapping[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in el.items() if k not in ("k", "expires_h")}
        out["expires_ts"] = created_ts + int(el["expires_h"]) * 3600
        return out

    new_alerts, new_entries = [final(a) for a in alerts], [final(o) for o in entries]
    old = pending_state(sim.journal.events(), name).pending
    sim.append_event(
        "agent_orders_set",
        {
            "portfolio": name,
            "round": ctx.round_id,
            "created_ts": created_ts,
            "alerts": new_alerts,
            "entry_orders": new_entries,
            "rejected": rejected,
        },
        ctx.now_ts,
    )
    for el in old:
        sim.append_event(
            "agent_order_ended",
            {"portfolio": name, "id": el.id, "kind": el.kind, "reason": "replaced"},
            ctx.now_ts,
        )


def _execute(
    sim: PerpSimulator,
    name: str,
    intent_id: str,
    instrument: str,
    action: str,
    v: Any,
    quotes: Mapping[str, tuple[int, int]],
    marks: Mapping[str, int],
    fx: tuple[int, int],
    now_ts: int,
) -> None:
    """Fill, then stop and take-profit; every outcome is journaled as `perp_execution`."""

    def outcome(status: str, error: str | None = None) -> None:
        sim.append_event(
            "perp_execution",
            {
                "intent_id": intent_id,
                "portfolio": name,
                "instrument": instrument,
                "status": status,
                "error": None if error is None else error[:500],
            },
            now_ts,
        )

    try:
        sim.market_order(intent_id, name, instrument, v.qty, quotes[instrument], fx, now_ts, marks=marks)
    except Exception as exc:  # noqa: BLE001 (approved by riskd but not executed: journaled, never hidden)
        outcome("refused" if isinstance(exc, PerpLedgerError) else "error", f"{type(exc).__name__}: {exc}")
        sim.append_event(
            "alert",
            {
                "level": "action",
                "code": "perp_execution_refused",
                "message": f"{name} {intent_id}: {exc}"[:1000],
            },
            now_ts,
        )
        return
    if not action.startswith("open"):
        outcome("filled")
        return
    try:
        sim.set_conditional(name, instrument, "stop", v.stop_uusd, now_ts)
    except Exception as exc:  # noqa: BLE001 (a position never stays without a stop)
        closed = _close_unprotected(sim, name, intent_id, instrument, quotes, marks, fx, now_ts, exc)
        outcome(
            "closed_without_stop" if closed else "unprotected_position_open", f"{type(exc).__name__}: {exc}"
        )
        return
    try:
        if v.take_profit_uusd is not None:
            sim.set_conditional(name, instrument, "take_profit", v.take_profit_uusd, now_ts)
    except Exception as exc:  # noqa: BLE001 (the stop is in place: the position stays, the miss is journaled)
        outcome("filled_without_take_profit", f"{type(exc).__name__}: {exc}")
        return
    outcome("filled")


def _close_unprotected(
    sim: PerpSimulator,
    name: str,
    intent_id: str,
    instrument: str,
    quotes: Mapping[str, tuple[int, int]],
    marks: Mapping[str, int],
    fx: tuple[int, int],
    now_ts: int,
    cause: Exception,
) -> bool:
    """Closes a position whose stop could not be set; True when it is really closed."""
    pos = sim.states()[name].positions.get(instrument)
    message = (
        f"{name} {instrument}: stop not set after the fill of {intent_id} ({type(cause).__name__}: {cause})"
    )
    try:
        if pos is not None:
            sim.market_order(
                f"{intent_id}:no-stop",
                name,
                instrument,
                -pos.qty,
                quotes[instrument],
                fx,
                now_ts,
                "no_stop",
                marks=marks,
            )
    except Exception as exc:  # noqa: BLE001
        message += f"; the closing order failed too ({type(exc).__name__}: {exc})"
    closed = instrument not in sim.states()[name].positions
    if not closed:
        message += "; THE POSITION IS STILL OPEN WITHOUT A STOP"
    sim.append_event(
        "alert", {"level": "panic", "code": "perp_position_without_stop", "message": message[:1000]}, now_ts
    )
    return closed


def exposure_bp(sim: PerpSimulator, name: str, marks: Mapping[str, int], fx: Sequence[int]) -> int:
    acc = sim.states()[name]
    eq = equity_ueur(acc, marks, fx[0], fx[1])
    return gross_exposure_ueur(acc, marks, fx[0], fx[1]) * BP // max(eq, 1)
