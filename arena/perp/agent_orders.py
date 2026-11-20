"""Alerts and conditional entry orders left by the agents (docs/SPEC-PERP-ORDER-ALERTS.md).

Pure functions over the league journal (nothing is kept in memory between ticks):
- `validate_levels`: the creation rules checked against the round's marks (level within 25 % of the mark,
  not already crossed);
- `pending_state`: what a portfolio has pending, recomputed from the journal: the elements of its LAST
  `agent_orders_set`, minus those triggered or ended since, plus what its triggered entry orders still need
  (a verdict, an execution);
- `orders_view`: the portfolio's own pending set and what happened since its last round (round.json);
- `unserved_alerts`: triggered alerts that no later round of their owner has served yet.

Everything is per portfolio: nothing here ever mixes two portfolios' elements.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

MAX_LEVEL_DISTANCE_BP = 2500  # a level is at most 25 % away from the mark of the snapshot
BP = 10_000


@dataclass
class Element:
    kind: str  # "alert" | "entry"
    data: dict[str, Any]  # the element as journaled in agent_orders_set
    created_ts: int

    @property
    def id(self) -> str:
        return str(self.data["id"])


@dataclass
class OrdersState:
    catalog: dict[str, Element] = field(default_factory=dict)  # every element ever set
    pending: list[Element] = field(default_factory=list)  # alerts first, then entry orders, in set order
    triggered: dict[str, dict[str, Any]] = field(default_factory=dict)  # id -> {payload, ts, seq}
    ended: dict[str, dict[str, Any]] = field(default_factory=dict)  # id -> {payload, ts, seq}
    verdicts: dict[str, dict[str, Any]] = field(default_factory=dict)  # entry order id -> verdict payload
    executions: dict[str, dict[str, Any]] = field(default_factory=dict)  # entry order id -> execution payload
    fills: dict[str, dict[str, Any]] = field(default_factory=dict)  # entry order id -> fill payload

    def unresolved_entries(self) -> list[tuple[Element, dict[str, Any]]]:
        """Triggered entry orders that still need a verdict, or an execution after an approved verdict."""
        out = []
        for oid, trig in sorted(self.triggered.items(), key=lambda kv: kv[1]["seq"]):
            el = self.catalog.get(oid)
            if el is None or el.kind != "entry" or oid in self.executions:
                continue
            verdict = self.verdicts.get(oid)
            if verdict is None or verdict.get("approved"):
                out.append((el, trig))
        return out


def pending_state(events: Sequence[Mapping[str, Any]], portfolio: str) -> OrdersState:
    st = OrdersState()
    current: list[Element] = []
    for e in events:
        p, t = e["payload"], e["type"]
        if t == "agent_orders_set" and p.get("portfolio") == portfolio:
            created = int(p.get("created_ts", e["ts"]))
            current = [Element("alert", a, created) for a in p.get("alerts", [])] + [
                Element("entry", o, created) for o in p.get("entry_orders", [])
            ]
            for el in current:
                st.catalog[el.id] = el
        elif t in ("agent_alert_triggered", "agent_entry_triggered") and p.get("portfolio") == portfolio:
            st.triggered[p["id"]] = {"payload": p, "ts": e["ts"], "seq": e["seq"]}
        elif t == "agent_order_ended" and p.get("portfolio") == portfolio:
            st.ended[p["id"]] = {"payload": p, "ts": e["ts"], "seq": e["seq"]}
        elif t == "perp_verdict" and p.get("portfolio") == portfolio:
            st.verdicts[p["intent_id"]] = p
        elif t == "perp_execution" and p.get("portfolio") == portfolio:
            st.executions[p["intent_id"]] = p
        elif t == "perp_fill" and p.get("portfolio") == portfolio:
            st.fills[p["order_id"]] = p
    st.pending = [el for el in current if el.id not in st.triggered and el.id not in st.ended]
    return st


def validate_levels(
    parsed: Mapping[str, Any], marks_uusd: Mapping[str, int]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """(alerts, entry orders, rejected) of a parsed valid decision, checked against the snapshot's marks.
    Rejected: [{kind, k, error}], the parse rejections first. Elements keep their `expires_h`."""
    rejected = [dict(r) for r in parsed.get("order_errors", [])]
    kept: dict[str, list[dict[str, Any]]] = {"alert": [], "entry": []}
    for kind, key in (("alert", "alerts"), ("entry", "entry_orders")):
        for el in parsed.get(key, []):
            error = level_error(el["condition"], el["price_uusd"], marks_uusd.get(el["instrument"]))
            if error:
                rejected.append({"kind": kind, "k": el["k"], "error": error})
            else:
                kept[kind].append(el)
    return kept["alert"], kept["entry"], rejected


def level_error(condition: str, level: int, mark: int | None) -> str | None:
    if not mark or mark <= 0:
        return "no mark for this instrument in the snapshot"
    if abs(level - mark) * BP > MAX_LEVEL_DISTANCE_BP * mark:
        return "level more than 25 % away from the mark"
    if condition == "above" and level <= mark:
        return "level already crossed: 'above' needs a level over the mark"
    if condition == "below" and level >= mark:
        return "level already crossed: 'below' needs a level under the mark"
    return None


def signature(el: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    """What makes two elements the same order (the id, the expiry and the rank do not)."""
    skip = {"id", "k", "expires_h", "expires_ts"}
    return tuple(sorted((k, v) for k, v in el.items() if k not in skip))


def orders_view(events: Sequence[Mapping[str, Any]], portfolio: str) -> dict[str, Any]:
    """Round data of the portfolio ALONE (integers and strings): its pending set, and what happened to its
    elements since its last round. Called before the round's own `round_data` is journaled."""
    st = pending_state(events, portfolio)
    cutoff = max(
        (
            e["seq"]
            for e in events
            if e["type"] == "round_data" and e["payload"].get("portfolio") == portfolio
        ),
        default=-1,
    )
    alerts_trig, entries_trig, ended, rejected = [], [], [], []
    for oid, trig in sorted(st.triggered.items(), key=lambda kv: kv[1]["seq"]):
        if trig["seq"] <= cutoff or oid not in st.catalog:
            continue
        el, p = st.catalog[oid], trig["payload"]
        if el.kind == "alert":
            alerts_trig.append(
                {
                    "instrument": p["instrument"],
                    "condition": p["condition"],
                    "price_uusd": p["price_uusd"],
                    "note": el.data.get("note"),
                    "minute": p["minute"],
                }
            )
            continue
        verdict, execution, fill = st.verdicts.get(oid), st.executions.get(oid), st.fills.get(oid)
        entries_trig.append(
            {
                "instrument": p["instrument"],
                "side": p["side"],
                "condition": p["condition"],
                "price_uusd": p["price_uusd"],
                "minute": p["minute"],
                "approved": None if verdict is None else bool(verdict["approved"]),
                "reasons": [] if verdict is None else list(verdict.get("reasons", [])),
                "status": None if execution is None else execution["status"],
                "fill_price_uusd": None if fill is None else fill["price_uusd"],
                "invalidation": el.data.get("invalidation"),
            }
        )
    for oid, end in sorted(st.ended.items(), key=lambda kv: kv[1]["seq"]):
        el = st.catalog.get(oid)
        if end["seq"] <= cutoff or el is None or end["payload"]["reason"] == "replaced":
            continue
        ended.append(
            {
                "kind": el.kind,
                "instrument": el.data["instrument"],
                "condition": el.data["condition"],
                "price_uusd": el.data["price_uusd"],
                "reason": end["payload"]["reason"],
            }
        )
    for e in events:
        if (
            e["seq"] > cutoff
            and e["type"] == "agent_orders_set"
            and e["payload"].get("portfolio") == portfolio
        ):
            rejected += [dict(r) for r in e["payload"].get("rejected", [])]
    pend = {"alerts": [], "entries": []}
    for el in st.pending:
        pend["alerts" if el.kind == "alert" else "entries"].append(
            {k: v for k, v in el.data.items() if k != "id"}
        )
    return {
        **pend,
        "since": {
            "alerts_triggered": alerts_trig,
            "entries_triggered": entries_trig,
            "ended": ended,
            "rejected": rejected,
        },
    }


def unserved_alerts(events: Sequence[Mapping[str, Any]], now_ts: int, max_age_s: int) -> list[dict[str, Any]]:
    """Triggered alerts younger than `max_age_s` that no round of their owner has served since (a
    `round_data` or a `perp_llm_skipped` of the owner after the trigger). Oldest first:
    [{portfolio, id, instrument, condition, price_uusd, note, ts, seq}]."""
    last_round_seq: dict[str, int] = {}
    triggers = []
    for e in events:
        p = e["payload"]
        if e["type"] in ("round_data", "perp_llm_skipped"):
            last_round_seq[p.get("portfolio")] = e["seq"]
        elif e["type"] == "agent_alert_triggered" and now_ts - e["ts"] < max_age_s:
            triggers.append(e)
    states: dict[str, OrdersState] = {}
    out = []
    for e in triggers:
        p = e["payload"]
        owner = p["portfolio"]
        if last_round_seq.get(owner, -1) > e["seq"]:
            continue
        st = states.setdefault(owner, pending_state(events, owner))
        el = st.catalog.get(p["id"])
        out.append(
            {
                "portfolio": owner,
                "id": p["id"],
                "instrument": p["instrument"],
                "condition": p["condition"],
                "price_uusd": p["price_uusd"],
                "note": el.data.get("note") if el else None,
                "ts": e["ts"],
                "seq": e["seq"],
            }
        )
    return out


WAKEUP_EARLY_S = 300  # a round of the owner starting at most one tick before the requested time serves it
WAKEUP_LAPSE_S = 3600  # an asked wake-up not served within the hour lapses (never served late)


def pending_wakeup(
    events: Sequence[Mapping[str, Any]], portfolio: str, now_ts: int | None = None
) -> dict[str, Any] | None:
    """The wake-up the portfolio asked for (`agent_wakeup_set`), if no round of its own has served it yet:
    {due_ts, round, seq}. Each valid decision replaces it (`due_ts` null: none); a round of the owner that
    starts at most WAKEUP_EARLY_S before `due_ts` serves it (a scheduled round within the tick, say). With
    `now_ts`, a wake-up lapsed by then (WAKEUP_LAPSE_S after its time) is not pending either."""
    last: Mapping[str, Any] | None = None
    for e in events:
        if e["type"] == "agent_wakeup_set" and e["payload"].get("portfolio") == portfolio:
            last = e
    if last is None or last["payload"].get("due_ts") is None:
        return None
    due, seq = int(last["payload"]["due_ts"]), last["seq"]
    if now_ts is not None and now_ts - due >= WAKEUP_LAPSE_S:
        return None
    for e in events:
        if (
            e["type"] == "round_data"
            and e["seq"] > seq
            and e["payload"].get("portfolio") == portfolio
            and e["ts"] >= due - WAKEUP_EARLY_S
        ):
            return None
    return {"due_ts": due, "round": last["payload"].get("round"), "seq": seq}
