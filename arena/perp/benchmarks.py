"""Benchmarks of the perp league (docs/ETUDE-AGENTS-TRADERS.md §6).

- `benchmark-perp:basket-1x`: long 1x on the six perpetuals in equal parts (1/6 of the equity each), set at the
  first round and rebalanced at the first round of each calendar month; never stopped. A REFERENCE: it does
  not go through the size, frequency, fee or holding rules (the simulator's initial margin still applies).
- `benchmark-perp:trend`: once a day (first round after 00:00 UTC), per instrument: long if the 20-day return
  is positive, short otherwise, 1/6 of the equity at 1x, stop at 10 %; it changes side only when the sign
  changes (close then open) and re-enters at the next daily signal after a stop. A REFERENCE as well.
- `benchmark-perp:carry`: a cash substitute, no bet on price (docs/lead/axis-03-carry, axis 10). Always-on BTC + ETH
  cash-and-carry: per coin, a long SPOT leg and a short PERP leg of equal quantity, EUR 250 of notional per leg from
  day one (a quarter of the capital per leg), never traded again except to bring a leg back to target when it drifts
  outside 0.8 to 1.25 times the target (axis 3's rule). The league has no spot instrument: the spot leg is a
  valuation only (`spot_fill` events, ledger `spot_qty`), priced at the perpetual's INDEX price (Kraken's spot
  index, already collected with every ticker) converted at the EUR/USD quote, with the spot taker cost of axis 3
  (0.40 % per side plus 5 bp of slippage) charged on entry and on each rebalance. The perp leg goes through the normal
  ledger (taker fee and slippage as for everyone) and earns the funding the leveraged longs pay. A REFERENCE: it
  goes through no size, frequency or stop rule.
- `benchmark-perp:random`: the null benchmark. At every round (scheduled rounds AND wake-ups, like the LLMs), 0-2
  intents drawn in the agents' action space, through riskd with exactly the LLMs' rules.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping
from dataclasses import dataclass

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
CARRY = "benchmark-perp:carry"
ALL = (BASKET, TREND, RANDOM, CARRY)
REFERENCES = (BASKET, TREND, CARRY)
CARRY_INSTRUMENTS = ("PF_XBTUSD", "PF_ETHUSD")  # BTC and ETH
CARRY_LEG_SHARE_BP = 2500  # EUR 250 of EUR 1,000 per leg per coin (4 legs: spot and perp of two coins)
CARRY_BAND_LOW_BP = 8000  # a leg under 0.8 x target ...
CARRY_BAND_HIGH_BP = 12500  # ... or over 1.25 x target brings both legs of the coin back to target
CARRY_SPOT_FEE_BP = 40  # Kraken spot taker 0.40 % per side
CARRY_SPOT_SLIPPAGE_BP = 5
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


@dataclass(frozen=True)
class CarryStep:
    leg: str  # "spot" | "perp"
    instrument: str
    qty: int  # signed: spot > 0 buys, perp < 0 sells (short)
    why: str  # "entry" | "rebalance"


def carry_plan(
    acc: MarginAccount,
    capital_ueur: int,
    marks: Mapping[str, int],
    index: Mapping[str, int | None],
    fx_bid: int,
    specs: Mapping[str, InstrumentSpec],
) -> list[CarryStep]:
    """The steps that bring the carry to target, or [] when both legs of every coin are inside the band.

    Per coin the target is `CARRY_LEG_SHARE_BP` of the CAPITAL (fixed, not of the equity: the benchmark is never
    resized to its gains) worth of quantity on each leg, the same quantity on both. A coin is traded only when a
    leg is missing (entry) or drifted out of 0.8 to 1.25 times the target notional (spot at the index, perp at the
    mark); then BOTH legs go back to the target quantity. Reductions come first (they free cash and margin), then
    the spot purchase, then the short: a purchase never waits for a short that the margin would refuse. A coin
    without a price is left as it is."""
    steps: list[CarryStep] = []
    for inst in CARRY_INSTRUMENTS:
        mark, idx = marks.get(inst), index.get(inst)
        if not mark or not idx or inst not in specs:
            continue
        lot = specs[inst].lot_step_qty or 1
        target_q = target_qty(capital_ueur, CARRY_LEG_SHARE_BP, mark, fx_bid, lot)
        if target_q <= 0:
            continue
        target_usd = capital_ueur * CARRY_LEG_SHARE_BP // BP * fx_bid // MICRO
        spot_q = acc.spot_qty.get(inst, 0)
        pos = acc.positions.get(inst)
        perp_q = -pos.qty if pos is not None else 0
        spot_usd = spot_q * idx // QTY_SCALE
        perp_usd = perp_q * mark // QTY_SCALE
        outside = any(
            v * BP < CARRY_BAND_LOW_BP * target_usd or v * BP > CARRY_BAND_HIGH_BP * target_usd
            for v in (spot_usd, perp_usd)
        )
        if not outside:
            continue
        why = "entry" if spot_q == 0 and perp_q == 0 else "rebalance"
        d_spot, d_perp = target_q - spot_q, -(target_q - perp_q)  # d_perp < 0: sell more
        coin = []
        if d_spot < 0:
            coin.append(CarryStep("spot", inst, d_spot, why))
        if d_perp > 0:
            coin.append(CarryStep("perp", inst, d_perp, why))
        if d_spot > 0:
            coin.append(CarryStep("spot", inst, d_spot, why))
        if d_perp < 0:
            coin.append(CarryStep("perp", inst, d_perp, why))
        steps += coin
    return steps
