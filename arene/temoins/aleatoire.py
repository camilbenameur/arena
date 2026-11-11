"""temoin:aleatoire : agent aléatoire dans le même espace d'actions que les LLM (docs/SPEC-MVP.md §10).

À chaque cycle, graine = sha256(cycle_ts, "aleatoire", trajectoire) ; on tire 0, 1 ou 2 actions :
symbole uniforme, côté uniforme parmi les côtés possibles (achat si du cash, vente si une position),
taille uniforme 1-20 % de l'equity pour un achat, 1-100 % de la position pour une vente, stop 2-10 %,
mouvement attendu 5-15 %. Les intentions passent ensuite par riskd comme celles d'un LLM : ce module
ne fait que les produire. La trajectoire 0 est la trajectoire vivante ; la simulation hors ligne
(trajectoires.py) utilise les numéros 1..n.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping

from arene.temoins import TemoinContext, make_intent
from arene.types import Intent, PortfolioState, Side

PORTFOLIO = "temoin:aleatoire"
MAX_ACTIONS = 2
SIZE_BP = (100, 2000)  # achat : 1 à 20 % de l'equity
SELL_SIZE_BP = (100, 10000)  # vente : 1 à 100 % de la position, comme les LLM
STOP_BP = (200, 1000)  # 2 à 10 %
EXPECTED_MOVE_BP = (500, 1500)  # 5 à 15 %


def seed_for(cycle_ts: int, trajectoire: int) -> int:
    """Graine entière dérivée de sha256(cycle_ts, "aleatoire", trajectoire) (JSON canonique)."""
    raw = json.dumps([cycle_ts, "aleatoire", trajectoire], separators=(",", ":")).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest(), "big")


def decide(
    cycle_ts: int, state: PortfolioState, marks: Mapping[str, int], context: TemoinContext
) -> list[Intent]:
    """0 à 2 intentions tirées avec la graine du cycle ; déterministe pour (cycle_ts, trajectoire)."""
    rng = random.Random(seed_for(cycle_ts, context.trajectoire))
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
