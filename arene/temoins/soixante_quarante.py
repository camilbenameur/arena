"""temoin:6040 : 60 % BTC / 40 % cash, rééquilibré au premier cycle de chaque mois civil."""

from __future__ import annotations

from collections.abc import Mapping

from arene.ledger import month_start_ts
from arene.temoins import TemoinContext, never_traded, rebalance_intents
from arene.types import Intent, PortfolioState

PORTFOLIO = "temoin:6040"
SYMBOL = "BTC/EUR"
TARGET_BP = 6_000


def is_first_cycle_of_month(cycle_ts: int, context: TemoinContext) -> bool:
    """Vrai si le cycle est le premier du mois civil UTC : le cycle précédent est d'un autre mois."""
    start = month_start_ts(cycle_ts)
    if context.prev_cycle_ts is not None:
        return context.prev_cycle_ts < start <= cycle_ts
    return start <= cycle_ts < start + context.interval_s


def decide(
    cycle_ts: int, state: PortfolioState, marks: Mapping[str, int], context: TemoinContext
) -> list[Intent]:
    """Premier cycle (portefeuille vierge) ou premier cycle d'un mois : ramener BTC à 60 % de l'equity."""
    if not (never_traded(state) or is_first_cycle_of_month(cycle_ts, context)):
        return []
    if SYMBOL not in marks:
        return []
    return rebalance_intents(
        PORTFOLIO, cycle_ts, state, marks, {SYMBOL: TARGET_BP}, (SYMBOL,), context.min_trade_ueur
    )
