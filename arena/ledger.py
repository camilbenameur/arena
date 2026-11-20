"""Portfolio state derived from the journal (docs/SPEC-MVP.md §4, §6).

Everything is rebuilt from the events: `replay(events)`. The SQLite file is only a derived view.

Accounting conventions:
- `Position.cost_ueur` = acquisition cost including buy fees (weighted average cost).
- On a sale: cost removed = cost x qty sold / qty held, rounded UP (adverse);
  a sale that closes the position removes exactly the remaining cost.
- Realized P&L = sale proceeds (rounded down) - sell fees - cost removed. It is therefore net of all
  fees (buy fees are part of the cost).
- Invariant: cash + sum of position costs = capital + realized P&L.
- Events are journal records (dict with "type", "ts", "payload"); the counter functions walk `events`
  once: pass a list, not an already-consumed generator.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arena.types import PortfolioState, Position, ceil_div, notional_ueur

DAY_S = 86_400
MINUTE_S = 60


class LedgerError(ValueError):
    """Inconsistent event sequence (short sale, negative cash, unknown portfolio...)."""


def _int(v: Any, name: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise LedgerError(f"{name} must be an integer, got {v!r}")
    return v


def _state(states: dict[str, PortfolioState], name: str) -> PortfolioState:
    try:
        return states[name]
    except KeyError:
        raise LedgerError(f"unknown portfolio (not opened): {name}") from None


def _apply_fill(st: PortfolioState, p: Mapping[str, Any]) -> None:
    qty = _int(p["qty"], "qty")
    price = _int(p["price_ueur"], "price_ueur")
    fee = _int(p["fee_ueur"], "fee_ueur")
    sym = p["symbol"]
    if qty <= 0 or price <= 0 or fee < 0:
        raise LedgerError(f"invalid fill (qty={qty}, price={price}, fee={fee})")
    if p["side"] == "buy":
        total = notional_ueur(qty, price, round_up=True) + fee
        if total > st.cash_ueur:
            raise LedgerError(f"{st.portfolio}: insufficient cash to buy {sym} ({total} > {st.cash_ueur})")
        st.cash_ueur -= total
        pos = st.positions.get(sym)
        if pos is None:
            st.positions[sym] = Position(sym, qty, total, _int(p["ts"], "ts"))
        else:
            pos.qty += qty
            pos.cost_ueur += total
    elif p["side"] == "sell":
        pos = st.positions.get(sym)
        if pos is None or qty > pos.qty:
            raise LedgerError(f"{st.portfolio}: short sale of {sym} ({qty} > {pos.qty if pos else 0})")
        gross = notional_ueur(qty, price, round_up=False)
        cost_removed = pos.cost_ueur if qty == pos.qty else ceil_div(pos.cost_ueur * qty, pos.qty)
        pos.qty -= qty
        pos.cost_ueur -= cost_removed
        if pos.qty == 0:
            del st.positions[sym]
        st.cash_ueur += gross - fee
        st.realized_pnl_ueur += gross - fee - cost_removed
    else:
        raise LedgerError(f"unknown side: {p['side']!r}")
    st.fees_paid_ueur += fee


def replay(events: Iterable[Mapping[str, Any]]) -> dict[str, PortfolioState]:
    """Rebuild the state of all portfolios from the journal events alone."""
    states: dict[str, PortfolioState] = {}
    for rec in events:
        t = rec["type"]
        p = rec["payload"]
        if t == "portfolio_opened":
            name = p["portfolio"]
            if name in states:
                raise LedgerError(f"portfolio already opened: {name}")
            states[name] = PortfolioState(name, _int(p["capital_ueur"], "capital_ueur"))
        elif t == "fill":
            _apply_fill(_state(states, p["portfolio"]), p)
        elif t == "stop_set":
            st = _state(states, p["portfolio"])
            pos = st.positions.get(p["symbol"])
            if pos is None:
                raise LedgerError(f"{st.portfolio}: stop on a nonexistent position ({p['symbol']})")
            pos.stop_ueur = _int(p["stop_ueur"], "stop_ueur")
        elif t == "portfolio_frozen":
            _state(states, p["portfolio"]).frozen_until_ts = _int(p["until_ts"], "until_ts")
        elif t == "portfolio_halted":
            _state(states, p["portfolio"]).halted = True
        elif t == "portfolio_resumed":
            st = _state(states, p["portfolio"])
            st.halted = False
            st.frozen_until_ts = 0
    return states


def retired_portfolios(events: Iterable[Mapping[str, Any]]) -> frozenset[str]:
    """Portfolios retired from the league (`portfolio_retired`, `arena retire`): flat for good, neither the cycle nor
    the watch plays or values them any more. The journal decides, never the configuration."""
    return frozenset(
        rec["payload"]["portfolio"]
        for rec in events
        if rec["type"] == "portfolio_retired" and isinstance(rec["payload"].get("portfolio"), str)
    )


def positions_value_ueur(
    state: PortfolioState, marks: Mapping[str, int], bids: Mapping[str, int] | None = None
) -> int:
    """Value of the positions, rounded down per position. Price = bid if provided, otherwise `marks`."""
    total = 0
    for sym, pos in state.positions.items():
        if bids is not None and sym in bids:
            price = bids[sym]
        elif sym in marks:
            price = marks[sym]
        else:
            raise LedgerError(f"no price to value {sym}")
        total += notional_ueur(pos.qty, price, round_up=False)
    return total


def equity_ueur(
    state: PortfolioState, marks: Mapping[str, int], bids: Mapping[str, int] | None = None
) -> int:
    """Cash + valued positions (at the bid if `bids` provides it, otherwise at the `marks` price), rounded down."""
    return state.cash_ueur + positions_value_ueur(state, marks, bids)


# ---------------------------------------------------------------------------
# Counters derived from the journal (for riskd)
# ---------------------------------------------------------------------------


def month_start_ts(ts: int) -> int:
    """Start (UTC) of the calendar month containing `ts`."""
    d = datetime.fromtimestamp(ts, UTC)
    return int(datetime(d.year, d.month, 1, tzinfo=UTC).timestamp())


def trades_last_24h(
    events: Iterable[Mapping[str, Any]], portfolio: str, now_ts: int, *, include_forced: bool = False
) -> int:
    """Number of trades (buys and sells) of the portfolio over the sliding window ]now-24h, now].

    By default only fills that come from an intent (`reason == "intent"`) count: forced exits
    (stop, maximum holding, kill switch) do not use up the deciders' quota. One trade = one order_id.
    """
    seen: set[str] = set()
    for rec in events:
        if rec["type"] != "fill":
            continue
        p = rec["payload"]
        if p["portfolio"] != portfolio or not (now_ts - DAY_S < rec["ts"] <= now_ts):
            continue
        if not include_forced and p.get("reason", "intent") != "intent":
            continue
        seen.add(p["order_id"])
    return len(seen)


def orders_last_minute(events: Iterable[Mapping[str, Any]], now_ts: int, *, state: str = "SUBMITTING") -> int:
    """Orders sent (`order_state` events in state `state`, one per order_id), all portfolios,
    over ]now-60 s, now]."""
    seen: set[str] = set()
    for rec in events:
        if rec["type"] != "order_state" or not (now_ts - MINUTE_S < rec["ts"] <= now_ts):
            continue
        if rec["payload"].get("state") == state:
            seen.add(rec["payload"]["order_id"])
    return len(seen)


def fees_month(events: Iterable[Mapping[str, Any]], portfolio: str, now_ts: int) -> int:
    """Fees paid by the portfolio in the UTC calendar month of `now_ts` (up to and including now_ts), in µEUR."""
    start = month_start_ts(now_ts)
    total = 0
    for rec in events:
        if rec["type"] == "fill" and rec["payload"]["portfolio"] == portfolio and start <= rec["ts"] <= now_ts:
            total += rec["payload"]["fee_ueur"]
    return total


def last_intent_ts(
    events: Iterable[Mapping[str, Any]],
    portfolio: str,
    symbol: str,
    *,
    exclude_intent_id: str | None = None,
    before_ts: int | None = None,
) -> int | None:
    """ts of the portfolio's last `intent` event on this symbol, or None.

    `exclude_intent_id` skips the intent being evaluated (already journaled before riskd);
    `before_ts` only considers strictly earlier events.
    """
    best: int | None = None
    for rec in events:
        if rec["type"] != "intent":
            continue
        p = rec["payload"]
        if p["portfolio"] != portfolio or p["symbol"] != symbol:
            continue
        if exclude_intent_id is not None and p.get("intent_id") == exclude_intent_id:
            continue
        if before_ts is not None and rec["ts"] >= before_ts:
            continue
        if best is None or rec["ts"] > best:
            best = rec["ts"]
    return best


def peak_equity(events: Iterable[Mapping[str, Any]], portfolio: str) -> int | None:
    """Portfolio equity peak: max of the opening capital and the `equity` events.
    None if the portfolio does not appear."""
    best: int | None = None
    for rec in events:
        p = rec["payload"]
        if rec["type"] == "portfolio_opened" and p["portfolio"] == portfolio:
            v = p["capital_ueur"]
        elif rec["type"] == "equity" and p["portfolio"] == portfolio:
            v = p["equity_ueur"]
        else:
            continue
        if best is None or v > best:
            best = v
    return best


def equity_24h_ago(events: Iterable[Mapping[str, Any]], portfolio: str, now_ts: int) -> int | None:
    """Portfolio equity 24 h ago: last `equity` event with ts <= now_ts - 24 h.

    If none is old enough (recent portfolio), falls back to the opening capital, a conservative
    reference. None if the portfolio was never opened.
    """
    cutoff = now_ts - DAY_S
    capital: int | None = None
    best_ts: int | None = None
    best: int | None = None
    for rec in events:
        p = rec["payload"]
        if rec["type"] == "portfolio_opened" and p["portfolio"] == portfolio:
            capital = p["capital_ueur"]
        elif (
            rec["type"] == "equity"
            and p["portfolio"] == portfolio
            and rec["ts"] <= cutoff
            and (best_ts is None or rec["ts"] >= best_ts)
        ):
            best_ts, best = rec["ts"], p["equity_ueur"]
    return best if best is not None else capital


# ---------------------------------------------------------------------------
# Derived SQLite view
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE fills (
    seq INTEGER PRIMARY KEY, ts INTEGER NOT NULL, order_id TEXT NOT NULL, portfolio TEXT NOT NULL,
    symbol TEXT NOT NULL, side TEXT NOT NULL, qty INTEGER NOT NULL, price_ueur INTEGER NOT NULL,
    fee_ueur INTEGER NOT NULL, reason TEXT NOT NULL, venue_mode TEXT, fill_model_version TEXT
);
CREATE TABLE equity (
    seq INTEGER PRIMARY KEY, ts INTEGER NOT NULL, portfolio TEXT NOT NULL, cycle INTEGER,
    cash_ueur INTEGER NOT NULL, positions_value_ueur INTEGER NOT NULL, equity_ueur INTEGER NOT NULL
);
CREATE TABLE decisions (
    seq INTEGER PRIMARY KEY, ts INTEGER NOT NULL, portfolio TEXT NOT NULL, cycle INTEGER,
    kind TEXT NOT NULL, reason TEXT, model_requested TEXT, model_returned TEXT, parse_error TEXT,
    input_tokens INTEGER, output_tokens INTEGER, cost_uusd INTEGER, latency_ms INTEGER
);
CREATE INDEX fills_portfolio ON fills (portfolio, ts);
CREATE INDEX equity_portfolio ON equity (portfolio, ts);
CREATE INDEX decisions_portfolio ON decisions (portfolio, ts);
"""


def rebuild_sqlite(events: Iterable[Mapping[str, Any]], path: str | Path) -> dict[str, int]:
    """Write the derived view (tables meta, fills, equity, decisions) to `path`, replaced atomically.

    Never a source: it can be deleted and rebuilt. Returns the number of rows per table.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    counts = {"fills": 0, "equity": 0, "decisions": 0}
    head_seq, head_hash = -1, "0" * 64
    con = sqlite3.connect(tmp)
    try:
        con.executescript(_SCHEMA)
        for rec in events:
            t, p, seq, ts = rec["type"], rec["payload"], rec["seq"], rec["ts"]
            head_seq, head_hash = seq, rec.get("hash", head_hash)
            if t == "fill":
                con.execute(
                    "INSERT INTO fills VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (seq, ts, p["order_id"], p["portfolio"], p["symbol"], p["side"], p["qty"], p["price_ueur"],
                     p["fee_ueur"], p.get("reason", "intent"), p.get("venue_mode"), p.get("fill_model_version")),
                )
                counts["fills"] += 1
            elif t == "equity":
                con.execute(
                    "INSERT INTO equity VALUES (?,?,?,?,?,?,?)",
                    (seq, ts, p["portfolio"], p.get("cycle"), p["cash_ueur"], p["positions_value_ueur"],
                     p["equity_ueur"]),
                )
                counts["equity"] += 1
            elif t == "decision_received":
                con.execute(
                    "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (seq, ts, p["portfolio"], p.get("cycle"), "received", None, p.get("model_requested"),
                     p.get("model_returned"), p.get("parse_error"), p.get("input_tokens"), p.get("output_tokens"),
                     p.get("cost_uusd"), p.get("latency_ms")),
                )
                counts["decisions"] += 1
            elif t == "decision_skipped":
                con.execute(
                    "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (seq, ts, p["portfolio"], p.get("cycle"), "skipped", p.get("reason"), None, None, None, None,
                     None, None, None),
                )
                counts["decisions"] += 1
        con.execute("INSERT INTO meta VALUES ('head_seq', ?)", (str(head_seq),))
        con.execute("INSERT INTO meta VALUES ('head_hash', ?)", (head_hash,))
        con.commit()
    finally:
        con.close()
    os.replace(tmp, dest)
    return counts
