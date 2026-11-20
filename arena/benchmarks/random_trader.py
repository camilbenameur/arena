"""benchmark:random: random agent in the same action space as the LLMs (docs/SPEC-MVP.md §10).

On each cycle, seed = sha256(cycle_ts, SEED_SALT, price_path); draw 0, 1 or 2 actions:
uniform symbol, uniform side among the possible sides (buy if there is cash, sell if there is a position),
uniform size 1-20% of equity for a buy, 1-100% of the position for a sell, stop 2-10%,
expected move 5-15%. The intents then go through riskd like an LLM's: this module only produces them.
Path 0 is the live path; the offline simulation (price_paths.py) uses numbers 1..n.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping

from arena.benchmarks import BenchmarkContext, make_intent
from arena.types import Intent, PortfolioState, Side

PORTFOLIO = "benchmark:random"
MAX_ACTIONS = 2
SIZE_BP = (100, 2000)  # buy: 1 to 20% of equity
SELL_SIZE_BP = (100, 10000)  # sell: 1 to 100% of the position, like the LLMs
STOP_BP = (200, 1000)  # 2 to 10%
EXPECTED_MOVE_BP = (500, 1500)  # 5 to 15%


# Salt of the seed, unchanged since the first cycle (it is the French word for "random"): changing it
# would change every draw, so past cycles could no longer be replayed exactly.
SEED_SALT = "aleatoire"


def seed_for(cycle_ts: int, price_path: int) -> int:
    """Integer seed derived from sha256(cycle_ts, SEED_SALT, price_path) (canonical JSON)."""
    raw = json.dumps([cycle_ts, SEED_SALT, price_path], separators=(",", ":")).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest(), "big")


def decide(
    cycle_ts: int, state: PortfolioState, marks: Mapping[str, int], context: BenchmarkContext
) -> list[Intent]:
    """0 to 2 intents drawn with the cycle seed; deterministic for (cycle_ts, price_path)."""
    rng = random.Random(seed_for(cycle_ts, context.price_path))
    n = rng.randrange(MAX_ACTIONS + 1)
    out: list[Intent] = []
    for i in range(n):
        sym = context.symbols[rng.randrange(len(context.symbols))]
        pos = state.positions.get(sym)
        sides = []
        if state.cash_ueur > 0:
            sides.append(Side.BUY)
        if pos is not None and pos.qty > 0:
            sides.append(Side.SELL)
        if not sides:
            continue
        side = sides[rng.randrange(len(sides))]
        size = rng.randint(*(SIZE_BP if side == Side.BUY else SELL_SIZE_BP))
        if side == Side.BUY:
            stop = rng.randint(*STOP_BP)
            move = rng.randint(*EXPECTED_MOVE_BP)
            out.append(
                make_intent(PORTFOLIO, cycle_ts, i, sym, side, size, stop_bp=stop, expected_move_bp=move)
            )
        else:
            out.append(make_intent(PORTFOLIO, cycle_ts, i, sym, side, size))
    return out
