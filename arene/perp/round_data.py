"""The frozen data of an agent round (study §2.3): everything the tools may serve, written BEFORE the model
is called, so that the tools never touch the network and a round stays auditable.

`build_round(...)` writes `<dir>/round.json` (integers and strings only) and returns its sha256. It holds:
- `meta`: round id, time, portfolio, journal head, policy and config hashes;
- `market`: per instrument, OHLC candles of 5 m, 1 h, 4 h and 1 d built from the closed one-minute TRADE
  candles (mark when no trade), the latest order book if it is at most `book_max_age_s` old, funding (current,
  predicted, 24 h and 7 d history), open interest (48 h hourly, closed hours only), mark, index;
- `view`: the riskd market view at the round; `account`: the portfolio state; `counters`; `specs`;
  `policy` and `params` (so `simulate_order` is self-contained); `history`: the portfolio's last decisions;
`agent_orders`: the portfolio's OWN pending alerts and entry orders and what happened to them since its last round.
Nothing after `now_ts` is read.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from arene.perp.agent_orders import orders_view
from arene.perp.ledger import MarginAccount
from arene.perp.policy import PerpPolicy
from arene.perp.riskd import PerpCounters, PerpMarketView
from arene.perp.sim import SimParams
from arene.perp.store import PerpDataStore
from arene.perp.types import InstrumentSpec

INTERVALS = {"5m": 300, "1h": 3600, "4h": 14_400, "1d": 86_400}
DEPTH = {"5m": 48, "1h": 48, "4h": 42, "1d": 30}
HISTORY_DECISIONS = 10


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def aggregate(minutes: Sequence[Any], interval_s: int, until_ts: int) -> list[list[int]]:
    """[ts, open, high, low, close] candles of `interval_s` made of CLOSED one-minute candles; only buckets
    entirely before `until_ts` are returned (a bucket missing minutes is still built from what exists)."""
    buckets: dict[int, list[Any]] = {}
    for c in minutes:
        b = c.ts // interval_s * interval_s
        if b + interval_s <= until_ts:
            buckets.setdefault(b, []).append(c)
    out = []
    for b in sorted(buckets):
        cs = sorted(buckets[b], key=lambda c: c.ts)
        out.append([b, cs[0].open, max(c.high for c in cs), min(c.low for c in cs), cs[-1].close])
    return out


def market_block(store: PerpDataStore, symbol: str, now_ts: int, book_max_age_s: int = 900) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label, iv in INTERVALS.items():
        since = now_ts - iv * (DEPTH[label] + 1)
        minutes = store.closed_candles("trade", symbol, 60, since, now_ts) or store.closed_candles(
            "mark", symbol, 60, since, now_ts
        )
        out[f"candles_{label}"] = aggregate(minutes, iv, now_ts)[-DEPTH[label] :]
    books = store.books(symbol).load(now_ts - book_max_age_s, now_ts + 1)
    out["order_book"] = books[-1].to_dict() if books else None
    funding = store.funding(symbol).load(now_ts - 7 * 86_400, now_ts + 1)
    out["funding_history"] = [[r.ts, r.relative_funding_e12] for r in funding]
    oi = store.open_interest(symbol, 3600).load(now_ts - 48 * 3600, now_ts + 1)
    out["open_interest"] = [[o.ts, o.close_qty] for o in oi if o.ts + o.interval_s <= now_ts]  # closed hours
    return out


def account_block(acc: MarginAccount) -> dict[str, Any]:
    return {
        "portfolio": acc.portfolio,
        "capital_ueur": acc.capital_ueur,
        "collateral_ueur": acc.collateral_ueur,
        "fees_paid_ueur": acc.fees_paid_ueur,
        "funding_paid_ueur": acc.funding_paid_ueur,
        "realized_pnl_ueur": acc.realized_pnl_ueur,
        "absorbed_deficit_ueur": acc.absorbed_deficit_ueur,
        "frozen_until_ts": acc.frozen_until_ts,
        "halted": acc.halted,
        "last_fill_ts": acc.last_fill_ts,
        "positions": {i: asdict(p) for i, p in sorted(acc.positions.items())},
    }


def history_block(events: Sequence[Mapping[str, Any]], portfolio: str, now_ts: int) -> list[dict[str, Any]]:
    """The portfolio's last decisions (justification cut to 400 characters) and its fills since then."""
    out: list[dict[str, Any]] = []
    for e in events:
        if e["ts"] > now_ts:
            continue
        p = e["payload"]
        if e["type"] == "agent_decision" and p.get("portfolio") == portfolio:
            out.append(
                {
                    "ts": e["ts"],
                    "round": p.get("round"),
                    "actions": (p.get("parsed") or {}).get("actions", []),
                    "justification": str((p.get("parsed") or {}).get("justification", ""))[:400],
                    "error": p.get("parse_error"),
                }
            )
        elif e["type"] == "perp_fill" and p.get("portfolio") == portfolio:
            out.append(
                {
                    "ts": e["ts"],
                    "fill": p["instrument"],
                    "qty": p["qty"],
                    "price_uusd": p["price_uusd"],
                    "reason": p["reason"],
                }
            )
    return out[-3 * HISTORY_DECISIONS :]


def build_round(
    out_dir: Path,
    store: PerpDataStore,
    events: Sequence[Mapping[str, Any]],
    view: PerpMarketView,
    acc: MarginAccount,
    counters: PerpCounters,
    specs: Mapping[str, InstrumentSpec],
    policy: PerpPolicy,
    params: SimParams,
    round_id: int,
    now_ts: int,
    config_sha256: str,
    entries_blocked: bool = False,
) -> tuple[dict[str, Any], str]:
    data = {
        "meta": {
            "round": round_id,
            "now_ts": now_ts,
            "portfolio": acc.portfolio,
            "journal_head_seq": events[-1]["seq"] if events else -1,
            "policy_sha256": policy.sha256,
            "config_sha256": config_sha256,
            "entries_blocked": entries_blocked,
        },
        "market": {s: market_block(store, s, now_ts, policy.max_data_age_s) for s in sorted(specs)},
        "view": {
            "instruments": {s: asdict(m) for s, m in sorted(view.instruments.items())},
            "fx_bid": view.fx_bid,
            "fx_ask": view.fx_ask,
            "fx_ts": view.fx_ts,
        },
        "account": account_block(acc),
        "counters": {**asdict(counters), "last_open_ts": dict(counters.last_open_ts)},
        "specs": {s: v.to_dict() for s, v in sorted(specs.items())},
        "policy": {**asdict(policy), "instruments": list(policy.instruments)},
        "params": asdict(params),
        "history": history_block(events, acc.portfolio, now_ts),
        "agent_orders": orders_view([e for e in events if e["ts"] <= now_ts], acc.portfolio),
    }
    raw = _canonical(data)
    out_dir.mkdir(parents=True, exist_ok=True)
    if (out_dir / "round.json").exists():
        raise FileExistsError(f"{out_dir}: this round was already built (a round is never rebuilt)")
    tmp = out_dir / "round.json.tmp"
    tmp.write_bytes(raw)
    os.replace(tmp, out_dir / "round.json")
    return data, hashlib.sha256(raw).hexdigest()
