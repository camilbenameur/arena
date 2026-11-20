"""Building the snapshot given to the LLM deciders (SPEC-MVP §9).

Rules:
- no float in the result (it is hashed and journaled): integers, decimal strings, booleans, None;
- percentages are integer basis points (suffix `_bp`);
- only bars closed before the cycle are accepted (ts + interval_s <= cycle_ts), otherwise an error.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from math import isqrt
from typing import Any

from arena.types import Bar, PortfolioState, notional_ueur

SCHEMA_VERSION = "2"
WINDOW_BARS = 42  # 7 days of 4 h bars
RECENT_CLOSES = 12
RECENT_DECISIONS = 5
MAX_STR_LEN = 600  # maximum length of a string coming from recent_decisions


class FutureLeakError(ValueError):
    """A bar is not closed at the cycle instant (future leak)."""


def canonical(obj: Any) -> bytes:
    """Canonical form of the object (identical to the journal)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def snapshot_sha256(snapshot: dict) -> str:
    """Hex sha256 fingerprint of the canonical form; rejects any float."""
    _assert_no_float(snapshot, "$")
    return hashlib.sha256(canonical(snapshot)).hexdigest()


def _assert_no_float(obj: Any, path: str) -> None:
    if isinstance(obj, float):
        raise TypeError(f"float not allowed in the snapshot ({path})")
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TypeError(f"non-text key in the snapshot ({path})")
            _assert_no_float(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _assert_no_float(v, f"{path}[{i}]")


# ---------------------------------------------------------------- integer formats


def _ratio_bp(num: int, den: int) -> int:
    """num/den in basis points, rounded to nearest (den > 0)."""
    n = num * 10_000
    return (2 * n + den) // (2 * den)


def _dec_str(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def eur_price(ueur: int) -> str:
    """Exact price in EUR without trailing zeros (µEUR -> string)."""
    return _dec_str(Decimal(ueur).scaleb(-6))


def eur_cents(ueur: int) -> str:
    """Amount in EUR rounded to the cent (banker's rounding), always 2 decimals."""
    cents = (Decimal(ueur).scaleb(-4)).quantize(Decimal(1))  # ROUND_HALF_EVEN by default
    return format(cents.scaleb(-2), ".2f")


def qty_str(qty: int) -> str:
    return _dec_str(Decimal(qty).scaleb(-8))


def _bounded_json_copy(obj: Any) -> Any:
    """Deep copy of a simple JSON object: rejects floats, truncates long strings."""
    if isinstance(obj, float):
        raise TypeError("float not allowed in recent_decisions")
    if isinstance(obj, str):
        return obj[:MAX_STR_LEN]
    if isinstance(obj, dict):
        return {str(k): _bounded_json_copy(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_bounded_json_copy(v) for v in obj]
    if obj is None or isinstance(obj, (bool, int)):
        return obj
    raise TypeError(f"type not serializable in recent_decisions: {type(obj).__name__}")


# ---------------------------------------------------------------- per-symbol features


def _validated_bars(symbol: str, bars: list[Bar], cycle_ts: int) -> list[Bar]:
    ordered = sorted(bars, key=lambda b: b.ts)
    last_ts = None
    for b in ordered:
        if b.symbol != symbol:
            raise ValueError(f"bar of {b.symbol} filed under {symbol}")
        if b.interval_s <= 0:
            raise ValueError("interval_s must be > 0")
        if b.ts + b.interval_s > cycle_ts:
            raise FutureLeakError(
                f"{symbol}: bar ts={b.ts} + {b.interval_s}s exceeds cycle {cycle_ts} (future leak)"
            )
        if last_ts == b.ts:
            raise ValueError(f"{symbol}: duplicate bar ts={b.ts}")
        last_ts = b.ts
    return ordered


def _symbol_features(symbol: str, bars: list[Bar], cycle_ts: int) -> dict:
    ordered = _validated_bars(symbol, bars, cycle_ts)
    if not ordered:
        return {"bars": 0}
    tail = ordered[-(WINDOW_BARS + 1) :]  # one more bar for the 7-day return
    window = ordered[-WINDOW_BARS:]
    closes = [b.close for b in tail]
    last = closes[-1]

    def ret(n: int) -> int | None:
        if len(closes) <= n or closes[-1 - n] <= 0:
            return None
        return _ratio_bp(last - closes[-1 - n], closes[-1 - n])

    # realized volatility: standard deviation (in bp, integer) of the window's 4 h returns
    rets = [_ratio_bp(closes[i] - closes[i - 1], closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
    vol = None
    if len(rets) >= 2:
        n = len(rets)
        s, s2 = sum(rets), sum(r * r for r in rets)
        var_num = s2 * n - s * s  # n² · variance
        vol = isqrt(var_num // (n * n)) if var_num > 0 else 0

    hi = max(b.high for b in window)
    lo = min(b.low for b in window)
    range_pos = _ratio_bp(last - lo, hi - lo) if hi > lo else 5000
    range_pos = max(0, min(10_000, range_pos))

    prev_vols = [b.volume for b in window[:-1]]
    rel_vol = None
    if prev_vols:
        mean_num = sum(prev_vols)
        if mean_num > 0:
            rel_vol = _ratio_bp(window[-1].volume * len(prev_vols), mean_num)

    return {
        "bars": len(window),
        "last_bar_ts": ordered[-1].ts,
        "last_close_eur": eur_price(last),
        "ret_4h_bp": ret(1),
        "ret_24h_bp": ret(6),
        "ret_7d_bp": ret(WINDOW_BARS),
        "vol_4h_bp": vol,
        "range_7d_low_eur": eur_price(lo),
        "range_7d_high_eur": eur_price(hi),
        "range_7d_pos_bp": range_pos,
        "rel_volume_bp": rel_vol,
        "last_closes_eur": [eur_price(b.close) for b in ordered[-RECENT_CLOSES:]],
    }


# ---------------------------------------------------------------- portfolio


def _portfolio_block(
    cycle_ts: int, state: PortfolioState, marks: dict[str, int], fallback: dict[str, int]
) -> dict:
    positions = []
    value_total = 0
    for sym in sorted(state.positions):
        pos = state.positions[sym]
        mark = marks.get(sym, fallback.get(sym))
        if mark is None:
            raise ValueError(f"no valuation price for {sym}")
        value = notional_ueur(pos.qty, mark, round_up=False)
        value_total += value
        positions.append((pos, mark, value))
    equity = state.cash_ueur + value_total
    out_positions = []
    for pos, mark, value in positions:
        pnl = value - pos.cost_ueur
        out_positions.append(
            {
                "symbol": pos.symbol,
                "qty": qty_str(pos.qty),
                "mark_eur": eur_price(mark),
                "value_eur": eur_cents(value),
                "cost_eur": eur_cents(pos.cost_ueur),
                "unrealized_pnl_eur": eur_cents(pnl),
                "unrealized_pnl_bp": _ratio_bp(pnl, pos.cost_ueur) if pos.cost_ueur > 0 else None,
                "weight_bp": _ratio_bp(value, equity) if equity > 0 else None,
                "stop_eur": eur_price(pos.stop_ueur) if pos.stop_ueur is not None else None,
                "held_h": max(0, (cycle_ts - pos.opened_ts) // 3600),
            }
        )
    return {
        "portfolio": state.portfolio,
        "cash_eur": eur_cents(state.cash_ueur),
        "equity_eur": eur_cents(equity),
        "cash_weight_bp": _ratio_bp(state.cash_ueur, equity) if equity > 0 else None,
        "positions": out_positions,
        "fees_paid_eur": eur_cents(state.fees_paid_ueur),
        "realized_pnl_eur": eur_cents(state.realized_pnl_ueur),
        "frozen": state.frozen_until_ts > cycle_ts,
        "halted": bool(state.halted),
    }


def build_snapshot(
    cycle_ts: int,
    bars_by_symbol: dict[str, list[Bar]],
    state: PortfolioState,
    marks: dict[str, int],
    recent_decisions: list[dict],
    policy_summary: str,
    context: dict | None = None,
) -> dict:
    """Deterministic snapshot (no float) given to the decider for cycle `cycle_ts`.

    `marks`: valuation prices in µEUR per symbol (quote mid); defaults to the latest close.
    `context`: {"type": "scheduled_round", ...} on the 4 h cycle, {"type": "wakeup", "trigger": ...} on a wake-up,
    with `next_scheduled_round_ts`; defaults to a scheduled round 4 h after `cycle_ts`.
    Raises `FutureLeakError` if a bar is not closed at `cycle_ts`.
    """
    symbols = {sym: _symbol_features(sym, bars_by_symbol[sym], cycle_ts) for sym in sorted(bars_by_symbol)}
    fallback = {
        s: max(bars_by_symbol[s], key=lambda b: b.ts).close for s in bars_by_symbol if bars_by_symbol[s]
    }
    snap = {
        "schema_version": SCHEMA_VERSION,
        "cycle_ts": int(cycle_ts),
        "bar_interval_s": 14_400,
        "context": _bounded_json_copy(
            context if context is not None else {"type": "scheduled_round", "next_scheduled_round_ts": cycle_ts + 14_400}
        ),
        "market": symbols,
        "portfolio": _portfolio_block(cycle_ts, state, marks, fallback),
        "recent_decisions": _bounded_json_copy(list(recent_decisions)[-RECENT_DECISIONS:]),
        "rules": str(policy_summary)[:4000],
    }
    _assert_no_float(snap, "$")
    return snap
