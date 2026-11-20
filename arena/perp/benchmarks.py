"""Benchmarks of the perp league (docs/ETUDE-AGENTS-TRADERS.md §6).

- `benchmark-perp:basket-1x`: long 1x on the six perpetuals in equal parts (1/6 of the equity each), set at the
  first round and rebalanced at the first round of each calendar month; never stopped. A REFERENCE: it does
  not go through the size, frequency, fee or holding rules (the simulator's initial margin still applies).
- `benchmark-perp:trend`: once a day (first round after 00:00 UTC), per instrument: long if the 20-day return
  is positive, short otherwise, 1/6 of the equity at 1x, stop at 10 %; it changes side only when the sign
  changes (close then open) and re-enters at the next daily signal after a stop. A REFERENCE as well.
- `benchmark-perp:random`: the null benchmark. At every round (scheduled rounds AND wake-ups, like the LLMs), 0-2
  intents drawn in the agents' action space, through riskd with exactly the LLMs' rules.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping

from arena.perp.ledger import BP, MarginAccount
from arena.perp.replay import random_intents
from arena.perp.riskd import PerpIntent
from arena.perp.types import InstrumentSpec
from arena.types import MICRO, QTY_SCALE

BASKET = "benchmark-perp:basket-1x"
TREND = "benchmark-perp:trend"
RANDOM = "benchmark-perp:random"
# The shadow of the council v4 (docs/SPEC-TREND-COUNCIL.md §6): the frozen engine's target at 2x, no LLM. It is not in
# `ALL`: the watcher opens it only when the council v4 is configured.
TREND_ENGINE = "benchmark-perp:trend-engine"
ALL = (BASKET, TREND, RANDOM)
REFERENCES = (BASKET, TREND)
TREND_LOOKBACK_DAYS = 20
TREND_STOP_BP = 1000


def target_qty(equity_ueur: int, share_bp: int, mark_uusd: int, fx_bid: int, lot: int) -> int:
    """Quantity (>= 0) worth `share_bp` of the equity at the mark, EUR -> USD at the bid, floored to the lot."""
    usd = equity_ueur * share_bp // BP * fx_bid // MICRO
    return usd * QTY_SCALE // mark_uusd // lot * lot


def basket_orders(
    acc: MarginAccount,
    equity_ueur: int,
    marks: Mapping[str, int],
    fx_bid: int,
    specs: Mapping[str, InstrumentSpec],
) -> list[tuple[str, int]]:
    """Signed quantities that bring every instrument to 1/6 of the equity, long (reductions first)."""
    n = len(marks)
    orders = []
    for inst in sorted(marks):
        lot = specs[inst].lot_step_qty or 1
        want = target_qty(equity_ueur, BP // n, marks[inst], fx_bid, lot)
        have = acc.positions[inst].qty if inst in acc.positions else 0
        if want != have:
            orders.append((inst, want - have))
    return sorted(orders, key=lambda o: o[1])  # sells (reductions) before buys free margin first


def trend_signals(closes_now_then: Mapping[str, tuple[int | None, int | None]]) -> dict[str, int | None]:
    """+1 / -1 / 0 per instrument from (close of the last day, close 20 days before); None when either is
    missing: an unknown signal never trades (the position and its stop are kept)."""
    out: dict[str, int | None] = {}
    for inst, (now, then) in closes_now_then.items():
        out[inst] = None if now is None or then is None else (now > then) - (now < then)
    return out


def trend_orders(
    acc: MarginAccount,
    equity_ueur: int,
    signals: Mapping[str, int | None],
    marks: Mapping[str, int],
    fx_bid: int,
    specs: Mapping[str, InstrumentSpec],
) -> list[tuple[str, int, bool]]:
    """(instrument, signed qty, is_entry): closes of positions against the signal first, then entries."""
    n = len(marks)
    closes, entries = [], []
    for inst in sorted(signals):
        sig = signals[inst]
        if sig is None:
            continue  # unknown: keep whatever is held
        pos = acc.positions.get(inst)
        if pos is not None and (sig == 0 or (pos.qty > 0) != (sig > 0)):
            closes.append((inst, -pos.qty, False))
            pos = None
        if pos is None and sig != 0 and inst in marks:
            lot = specs[inst].lot_step_qty or 1
            q = target_qty(equity_ueur, BP // n, marks[inst], fx_bid, lot)
            if q > 0:
                entries.append((inst, sig * q, True))
    return closes + entries


def random_round(round_id: int, held: Mapping[str, object], symbols: list[str]) -> list[PerpIntent]:
    """The random benchmark's intents for a round, seeded by the round id (reproducible)."""
    seed = int.from_bytes(hashlib.sha256(f"{RANDOM}:{round_id}".encode()).digest()[:8], "big")
    out = random_intents(random.Random(seed), round_id, round_id, held, symbols, min_move_bp=500)  # study §6
    return [
        PerpIntent(**{**i.__dict__, "portfolio": RANDOM, "intent_id": f"{RANDOM}:{i.intent_id}"}) for i in out
    ]
