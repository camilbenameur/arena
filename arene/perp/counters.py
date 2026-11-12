"""riskd counters of a perp portfolio, computed from the league journal only (riskd stays pure).

- `opens_24h` / `last_open_ts`: fills of reason `intent` that opened or increased a position;
- `orders_last_minute`: fills of reason `intent` in the last 60 s, all portfolios;
- `fees_month_ueur`: fees of every kind in the calendar month (forced exits and close-outs included);
- equity references from `perp_equity` measures (written every watcher tick): the month start, 24 h ago and
  the peak. A portfolio younger than 24 h uses its capital as the 24 h reference.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from arene.perp.riskd import PerpCounters

DAY_S = 86_400


def month_start_ts(ts: int) -> int:
    d = datetime.fromtimestamp(ts, UTC)
    return int(datetime(d.year, d.month, 1, tzinfo=UTC).timestamp())


def counters_for(events: Iterable[Mapping[str, Any]], portfolio: str, now_ts: int) -> PerpCounters:
    month0 = month_start_ts(now_ts)
    capital = None
    opens: list[tuple[int, str]] = []
    orders_minute = 0
    fees_month = 0
    peak = None
    month_start_eq = None
    ago_eq = None
    qty: dict[str, int] = {}
    for rec in events:
        t, p, ts = rec["type"], rec["payload"], rec["ts"]
        if ts > now_ts:
            continue
        if t == "portfolio_opened" and p["portfolio"] == portfolio:
            capital = p["capital_ueur"]
        elif t == "perp_fill":
            if p["reason"] == "intent" and now_ts - 60 < ts <= now_ts:
                orders_minute += 1
            if p["portfolio"] != portfolio:
                continue
            q0 = qty.get(p["instrument"], 0)
            q1 = q0 + p["qty"]
            qty[p["instrument"]] = q1
            if p["reason"] == "intent" and abs(q1) > abs(q0):
                opens.append((ts, p["instrument"]))
            if ts >= month0:
                fees_month += p["fee_ueur"]
        elif t == "perp_equity" and p["portfolio"] == portfolio:
            eq = p["equity_ueur"]
            peak = eq if peak is None else max(peak, eq)
            if ts < month0:
                month_start_eq = eq  # the last measure before the month: the month-start equity
            if ts <= now_ts - DAY_S:
                ago_eq = eq
    cap = capital or 0
    return PerpCounters(
        equity_month_start_ueur=month_start_eq if month_start_eq is not None else cap,
        equity_24h_ago_ueur=ago_eq if ago_eq is not None else cap,
        equity_peak_ueur=max(peak or 0, cap),
        opens_24h=sum(1 for ts, _ in opens if ts > now_ts - DAY_S),
        orders_last_minute=orders_minute,
        last_open_ts={i: max(ts for ts, j in opens if j == i) for i in {j for _, j in opens}},
        fees_month_ueur=fees_month,
    )
