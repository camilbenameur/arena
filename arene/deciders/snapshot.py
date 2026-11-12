"""Construction de l'instantané donné aux décideurs LLM (SPEC-MVP §9).

Règles :
- aucun float dans le résultat (il est haché et journalisé) : entiers, chaînes décimales, booléens, None ;
- les pourcentages sont des points de base entiers (suffixe `_bp`) ;
- seules des barres closes avant le cycle sont acceptées (ts + interval_s <= cycle_ts), sinon erreur.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from math import isqrt
from typing import Any

from arene.types import Bar, PortfolioState, notional_ueur

SCHEMA_VERSION = "2"
WINDOW_BARS = 42  # 7 jours de barres 4 h
RECENT_CLOSES = 12
RECENT_DECISIONS = 5
MAX_STR_LEN = 600  # longueur maximale d'une chaîne issue de recent_decisions


class FuturLeakError(ValueError):
    """Une barre n'est pas close à l'instant du cycle (fuite du futur)."""


def canonical(obj: Any) -> bytes:
    """Forme canonique du dépôt (identique au journal)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def snapshot_sha256(snapshot: dict) -> str:
    """Empreinte sha256 hex de la forme canonique ; refuse tout float."""
    _assert_no_float(snapshot, "$")
    return hashlib.sha256(canonical(snapshot)).hexdigest()


def _assert_no_float(obj: Any, path: str) -> None:
    if isinstance(obj, float):
        raise TypeError(f"float interdit dans l'instantané ({path})")
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TypeError(f"clé non texte dans l'instantané ({path})")
            _assert_no_float(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _assert_no_float(v, f"{path}[{i}]")


# ---------------------------------------------------------------- formats entiers


def _ratio_bp(num: int, den: int) -> int:
    """num/den en points de base, arrondi au plus proche (den > 0)."""
    n = num * 10_000
    return (2 * n + den) // (2 * den)


def _dec_str(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def eur_price(ueur: int) -> str:
    """Prix exact en EUR sans zéros inutiles (µEUR -> chaîne)."""
    return _dec_str(Decimal(ueur).scaleb(-6))


def eur_cents(ueur: int) -> str:
    """Montant en EUR arrondi au centime (arrondi bancaire), toujours 2 décimales."""
    cents = (Decimal(ueur).scaleb(-4)).quantize(Decimal(1))  # ROUND_HALF_EVEN par défaut
    return format(cents.scaleb(-2), ".2f")


def qty_str(qty: int) -> str:
    return _dec_str(Decimal(qty).scaleb(-8))


def _check_str_len(obj: Any) -> Any:
    """Copie profonde d'un objet JSON simple : refuse les floats, tronque les longues chaînes."""
    if isinstance(obj, float):
        raise TypeError("float interdit dans recent_decisions")
    if isinstance(obj, str):
        return obj[:MAX_STR_LEN]
    if isinstance(obj, dict):
        return {str(k): _check_str_len(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_check_str_len(v) for v in obj]
    if obj is None or isinstance(obj, (bool, int)):
        return obj
    raise TypeError(f"type non sérialisable dans recent_decisions : {type(obj).__name__}")


# ---------------------------------------------------------------- features par symbole


def _validated_bars(symbol: str, bars: list[Bar], cycle_ts: int) -> list[Bar]:
    ordered = sorted(bars, key=lambda b: b.ts)
    last_ts = None
    for b in ordered:
        if b.symbol != symbol:
            raise ValueError(f"barre de {b.symbol} rangée sous {symbol}")
        if b.interval_s <= 0:
            raise ValueError("interval_s doit être > 0")
        if b.ts + b.interval_s > cycle_ts:
            raise FuturLeakError(
                f"{symbol}: barre ts={b.ts} + {b.interval_s}s dépasse le cycle {cycle_ts} (fuite du futur)"
            )
        if last_ts == b.ts:
            raise ValueError(f"{symbol}: barre en double ts={b.ts}")
        last_ts = b.ts
    return ordered


def _symbol_features(symbol: str, bars: list[Bar], cycle_ts: int) -> dict:
    ordered = _validated_bars(symbol, bars, cycle_ts)
    if not ordered:
        return {"bars": 0}
    tail = ordered[-(WINDOW_BARS + 1) :]  # une barre de plus pour le rendement 7 j
    window = ordered[-WINDOW_BARS:]
    closes = [b.close for b in tail]
    last = closes[-1]

    def ret(n: int) -> int | None:
        if len(closes) <= n or closes[-1 - n] <= 0:
            return None
        return _ratio_bp(last - closes[-1 - n], closes[-1 - n])

    # volatilité réalisée : écart-type (en bp, entier) des rendements 4 h de la fenêtre
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


# ---------------------------------------------------------------- portefeuille


def _portfolio_block(
    cycle_ts: int, state: PortfolioState, marks: dict[str, int], fallback: dict[str, int]
) -> dict:
    positions = []
    value_total = 0
    for sym in sorted(state.positions):
        pos = state.positions[sym]
        mark = marks.get(sym, fallback.get(sym))
        if mark is None:
            raise ValueError(f"aucun prix de valorisation pour {sym}")
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
    contexte: dict | None = None,
) -> dict:
    """Instantané déterministe (sans float) donné au décideur pour le cycle `cycle_ts`.

    `marks` : prix de valorisation en µEUR par symbole (milieu du quote) ; à défaut, dernière clôture.
    `contexte` : {"type": "rendez_vous", ...} au cycle de 4 h, {"type": "reveil", "declencheur": ...} à un réveil,
    avec `prochain_rendez_vous_ts` ; à défaut, un rendez-vous 4 h après `cycle_ts`.
    Lève `FuturLeakError` si une barre n'est pas close à `cycle_ts`.
    """
    symbols = {sym: _symbol_features(sym, bars_by_symbol[sym], cycle_ts) for sym in sorted(bars_by_symbol)}
    fallback = {
        s: max(bars_by_symbol[s], key=lambda b: b.ts).close for s in bars_by_symbol if bars_by_symbol[s]
    }
    snap = {
        "schema_version": SCHEMA_VERSION,
        "cycle_ts": int(cycle_ts),
        "bar_interval_s": 14_400,
        "contexte": _check_str_len(
            contexte if contexte is not None else {"type": "rendez_vous", "prochain_rendez_vous_ts": cycle_ts + 14_400}
        ),
        "market": symbols,
        "portfolio": _portfolio_block(cycle_ts, state, marks, fallback),
        "recent_decisions": _check_str_len(list(recent_decisions)[-RECENT_DECISIONS:]),
        "rules": str(policy_summary)[:4000],
    }
    _assert_no_float(snap, "$")
    return snap
