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
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from arene.perp.agent import AgentDecider, AgentResult, cli_version, parse_decision
from arene.perp.agent_orders import pending_state, pending_wakeup, validate_levels
from arene.perp.counters import counters_for
from arene.perp.ledger import (
    BP,
    PerpLedgerError,
    equity_ueur,
    gross_exposure_ueur,
    price_pnl_uusd,
    to_eur,
)
from arene.perp.mcp_server import eur, pct_e12_hour, qty, usd
from arene.perp.policy import AGGRESSIVE, PerpPolicy
from arene.perp.riskd import PerpMarketView, evaluate_perp
from arene.perp.round_data import build_round
from arene.perp.sim import PerpSimulator
from arene.perp.store import PerpDataStore
from arene.perp.types import InstrumentSpec


def _pct(bp: int | None) -> str | None:
    return None if bp is None else format((Decimal(bp) / 100).normalize(), "f")


def _utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


_KIND_FR = {"alert": "alerte", "entry": "ordre_d_entree", "wakeup": "reveil"}


def rounds_snapshot(rounds: Mapping[str, Any] | None) -> dict[str, Any]:
    """The agent's rounds of the day and its pending wake-up (French keys, like the rest of the snapshot)."""
    if not rounds:
        return {}
    q = rounds.get("quota")
    due = rounds.get("next_wakeup_ts")
    out: dict[str, Any] = {"reveil_demande_utc": _utc(due) if due is not None else None}
    if q:
        out |= {
            "rondes_par_jour": q["per_day"],
            "rondes_jouees_aujourd_hui": q["played_today"],
            "rendez_vous_restants_aujourd_hui": q["rendezvous_left"],
            # this round is not counted in played_today yet: what is left once it is played
            "rondes_hors_rendez_vous_restantes": max(0, q["extra_left"] - 1),
        }
    return {"rondes": out}


def orders_snapshot(view: Mapping[str, Any]) -> dict[str, Any]:
    """The agent's own alerts and entry orders for the snapshot (French keys, like the rest of it)."""
    since = view["since"]
    return {
        "alertes_en_attente": [
            {
                "instrument": a["instrument"],
                "condition": a["condition"],
                "niveau_usd": usd(a["price_uusd"]),
                "echeance_utc": _utc(a["expires_ts"]),
                "note": a.get("note"),
            }
            for a in view["alerts"]
        ],
        "ordres_d_entree_en_attente": [
            {
                "instrument": o["instrument"],
                "sens": o["side"],
                "condition": o["condition"],
                "niveau_usd": usd(o["price_uusd"]),
                "taille_pct": _pct(o["size_bp"]),
                "stop_pct": _pct(o["stop_bp"]),
                "objectif_pct": _pct(o["take_profit_bp"]),
                "horizon_h": o["horizon_h"],
                "mouvement_attendu_pct": _pct(o["expected_move_bp"]),
                "confiance_pct": o["confidence_pct"],
                "invalidation": o["invalidation"],
                "echeance_utc": _utc(o["expires_ts"]),
            }
            for o in view["entries"]
        ],
        "depuis_ta_derniere_ronde": {
            "alertes_declenchees": [
                {
                    "instrument": a["instrument"],
                    "condition": a["condition"],
                    "niveau_usd": usd(a["price_uusd"]),
                    "minute_utc": _utc(a["minute"]),
                    "note": a["note"],
                }
                for a in since["alerts_triggered"]
            ],
            "ordres_declenches": [
                {
                    "instrument": o["instrument"],
                    "sens": o["side"],
                    "condition": o["condition"],
                    "niveau_usd": usd(o["price_uusd"]),
                    "minute_utc": _utc(o["minute"]),
                    "garde_fou": None
                    if o["approved"] is None
                    else ("approuve" if o["approved"] else "refuse"),
                    "raisons_de_refus": o["reasons"],
                    "execution": o["status"],
                    "prix_de_remplissage_usd": usd(o["fill_price_uusd"]),
                    "invalidation": o.get("invalidation"),
                }
                for o in since["entries_triggered"]
            ],
            "elements_expires": [
                {
                    "type": "alerte" if x["kind"] == "alert" else "ordre_d_entree",
                    "instrument": x["instrument"],
                    "condition": x["condition"],
                    "niveau_usd": usd(x["price_uusd"]),
                    "raison": x["reason"],
                }
                for x in since["ended"]
            ],
            "elements_rejetes": [
                {
                    "type": _KIND_FR.get(x["kind"], x["kind"]),
                    "rang": x["k"],
                    "erreur": x["error"],
                }
                for x in since["rejected"]
            ],
        },
    }


STANDARD_RULES = (
    "levier 2x max, stop obligatoire 1-15 %, perte au stop <= 3 % (tous stops <= 7,5 %), 4 ouvertures / 24 h"
)


def _pct_fr(bp: int) -> str:
    return format((Decimal(bp) / 100).normalize(), "f").replace(".", ",")


def rules_text(policy: Mapping[str, Any] | None) -> str:
    """The rules line of the snapshot: the standard one, or the council's from its own policy."""
    if not policy or policy.get("profile") != AGGRESSIVE:
        return STANDARD_RULES
    p = policy
    return (
        f"levier {p['max_leverage_bp'] // BP}x max (marges de Kraken), entrée <= {_pct_fr(p['max_order_bp'])} % "
        f"de l'equity, position <= {_pct_fr(p['max_position_bp'])} %, stop obligatoire "
        f"{_pct_fr(p['stop_bp_min'])}-{_pct_fr(p['stop_bp_max'])} % et avant la liquidation, perte au stop "
        f"<= {_pct_fr(p['max_trade_loss_bp'])} % (tous stops <= {_pct_fr(p['max_open_risk_bp'])} %), "
        f"{p['max_opens_per_day']} ouvertures / 24 h, arrêt à -{_pct_fr(p['drawdown_halt_bp'])} % du plus haut"
    )


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
            "funding_pct_heure": pct_e12_hour(v.get("relative_funding_e12")),
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
            "quantite": qty(p["qty"]),
            "sens": "long" if p["qty"] > 0 else "short",
            "entree_usd": usd(p["entry_uusd"]),
            "mark_usd": usd(mark),
            "pnl_latent_eur": eur(pnl),
            "stop_usd": usd(p["stop_uusd"]),
            "objectif_usd": usd(p["take_profit_uusd"]),
            "ouverte_depuis_h": (now - p["opened_ts"]) // 3600,
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
    return {
        "heure_utc": now,
        "appel": {"type": kind, "declencheur": trigger},
        "compte": {
            "collateral_eur": eur(acc["collateral_ueur"]),
            "equity_eur": eur(equity),
            "levier_bp": gross * BP // equity if equity > 0 else None,
            "funding_paye_eur": eur(acc["funding_paid_ueur"]),
            "frais_payes_eur": eur(acc["fees_paid_ueur"]),
            "gele_jusqu_a": acc["frozen_until_ts"] or None,
            "arrete": acc["halted"],
            "entrees_bloquees": bool(data["meta"].get("entries_blocked")),
            "positions": positions,
            **orders_snapshot(data["agent_orders"]),
            **rounds_snapshot(data.get("rounds")),
        },
        "marche": market,
        "tes_conditions_d_invalidation": invalidations,
        "regles": rules_text(data.get("policy")),
    }


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
        config_sha256, _blocked(entries_blocked), quota=quota,
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
    for op in res.council:  # the council's members, before its decision (docs/SPEC-PERP-CONSEIL-HAIKU.md §3)
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
            res.decision, name, round_id, now_ts, max_size_pct=getattr(ctx.decider, "max_size_pct", None)
        )
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
        acc = sim.states()[name]
        c = counters_for(sim.journal.events(), name, now_ts)
        v = evaluate_perp(
            it, acc, view, ctx.specs, c, ctx.policy, sim.params, now_ts, _blocked(ctx.entries_blocked)
        )
        sim.append_event(
            "perp_verdict",
            {
                "intent_id": it.intent_id,
                "portfolio": name,
                "instrument": it.instrument,
                "action": it.action,
                "approved": v.approved,
                "reasons": list(v.reasons),
                "qty": v.qty,
                "policy_sha256": v.policy_sha256,
                "error": v.error,
            },
            now_ts,
        )
        if v.approved:
            _execute(sim, name, it.intent_id, it.instrument, it.action, v, quotes, marks, fx, now_ts)
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
        "alert", {"level": "panique", "code": "perp_position_without_stop", "message": message[:1000]}, now_ts
    )
    return closed


def exposure_bp(sim: PerpSimulator, name: str, marks: Mapping[str, int], fx: Sequence[int]) -> int:
    acc = sim.states()[name]
    eq = equity_ueur(acc, marks, fx[0], fx[1])
    return gross_exposure_ueur(acc, marks, fx[0], fx[1]) * BP // max(eq, 1)
