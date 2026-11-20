"""benchmark:basket: 1/6 of equity in each symbol on the first cycle (fees included), then held."""

from __future__ import annotations

from collections.abc import Mapping

from arena.benchmarks import BP, BenchmarkContext, make_intent, never_traded
from arena.types import Intent, PortfolioState, Side

PORTFOLIO = "benchmark:basket"


def decide(
    cycle_ts: int, state: PortfolioState, marks: Mapping[str, int], context: BenchmarkContext
) -> list[Intent]:
    """On the first cycle (portfolio still untouched): buy 1/n of equity in each symbol; nothing afterwards.

    The "untouched" condition (no position, no fees) makes the benchmark idempotent: if the first
    cycle could not buy (missing data), it retries on the next one; once invested, it is inert.
    """
    if not never_traded(state):
        return []
    n = len(context.symbols)
    size_bp = BP // n  # 1666 for 6 : the sum stays <= 100%
    return [
        make_intent(PORTFOLIO, cycle_ts, i, sym, Side.BUY, size_bp) for i, sym in enumerate(context.symbols)
    ]
