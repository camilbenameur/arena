"""benchmark:6040: 60% BTC / 40% cash, rebalanced on the first cycle of each calendar month."""

from __future__ import annotations

from collections.abc import Mapping

from arena.ledger import month_start_ts
from arena.benchmarks import BenchmarkContext, never_traded, rebalance_intents
from arena.types import Intent, PortfolioState

PORTFOLIO = "benchmark:6040"
SYMBOL = "BTC/EUR"
TARGET_BP = 6_000


def is_first_cycle_of_month(cycle_ts: int, context: BenchmarkContext) -> bool:
    """True if the cycle is the first of the UTC calendar month: the previous cycle is in another month."""
    start = month_start_ts(cycle_ts)
    if context.prev_cycle_ts is not None:
        return context.prev_cycle_ts < start <= cycle_ts
    return start <= cycle_ts < start + context.interval_s


def decide(
    cycle_ts: int, state: PortfolioState, marks: Mapping[str, int], context: BenchmarkContext
) -> list[Intent]:
    """First cycle (untouched portfolio) or first cycle of a month: bring BTC back to 60% of equity."""
    if not (never_traded(state) or is_first_cycle_of_month(cycle_ts, context)):
        return []
    if SYMBOL not in marks:
        return []
    return rebalance_intents(
        PORTFOLIO, cycle_ts, state, marks, {SYMBOL: TARGET_BP}, (SYMBOL,), context.min_trade_ueur
    )
