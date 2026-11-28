"""Kraken Futures margins for the portfolios that trade with leverage above 2x (the Haiku council,
docs/SPEC-PERP-COUNCIL-HAIKU.md §5).

The other portfolios of the perp league follow the AMF rule for retail crypto CFDs (an entry must leave the
equity at 50 % of the gross exposure, close-out under 25 %: `SimParams`). A leveraged portfolio follows the
contract's own margin schedule instead, as published by Kraken (`marginLevels` of /instruments): an initial
margin to open, and a maintenance margin under which the position is liquidated. The rate of a position is
the one of the highest level its notional reaches (in USD). A contract without a schedule is never margined at
less than 100 %: no leverage at all (fail closed).

Which portfolios: the name decides (`LEVERAGED_PREFIX`), never a configuration that could fail to load. A
council portfolio whose configuration is invalid keeps Kraken's liquidation, so a 10x position is never
suddenly measured against the AMF close-out (that would liquidate it at once).
"""

from __future__ import annotations

from collections.abc import Mapping

from arena.perp.ledger import cost_eur
from arena.perp.types import MarginLevel
from arena.types import ceil_div

LEVERAGED_PREFIX = "council-perp:"
# the shadow benchmark of the council v4 trades at the council's leverage, with the same margins
# and so do the two portfolios of the hunter (docs/SPEC-HUNTER.md: 2x per contract, up to 10x gross; the AMF 50 % rule
# would refuse a 200 % entry)
# The hunter's two portfolios, defined here only (sim.py: the stop ignores the minute of the entry for them;
# watcher.py and hunter.py use the names of the hunter's own configuration)
HUNTER_NAMES = frozenset({"robot-perp:hunter", "benchmark-perp:hunter-5min"})
# The engine-only benchmarks of the Trend Councils: the first one at 2x (retired on axis 10), then the one at 1x
TREND_ENGINE_NAMES = frozenset({"benchmark-perp:trend-engine", "benchmark-perp:trend-engine-1x"})
LEVERAGED_NAMES = (*sorted(TREND_ENGINE_NAMES), *sorted(HUNTER_NAMES))
PPM = 1_000_000
INITIAL = "initial"
MAINTENANCE = "maintenance"


def leveraged(portfolio: str) -> bool:
    return portfolio.startswith(LEVERAGED_PREFIX) or portfolio in LEVERAGED_NAMES


def rate_ppm(levels: tuple[MarginLevel, ...] | None, notional_uusd: int, kind: str) -> int:
    """The margin rate (ppm of the notional) of a position of `notional_uusd`; 100 % without a schedule."""
    best = None
    for lv in levels or ():
        if lv.threshold_uusd <= notional_uusd and (best is None or lv.threshold_uusd >= best.threshold_uusd):
            best = lv
    if best is None:
        return PPM
    rate = best.initial_ppm if kind == INITIAL else best.maintenance_ppm
    return rate if type(rate) is int and 0 < rate <= PPM else PPM


def margin_ueur(
    notionals_uusd: Mapping[str, int],
    levels: Mapping[str, tuple[MarginLevel, ...]],
    kind: str,
    fx_bid: int,
    fx_ask: int,
) -> int:
    """Initial or maintenance margin (µEUR, rounded up, at the unfavourable rate) of positions given by their
    notional in µUSD per instrument."""
    total_uusd = sum(
        ceil_div(n * rate_ppm(levels.get(i), n, kind), PPM) for i, n in notionals_uusd.items() if n > 0
    )
    return cost_eur(total_uusd, fx_bid, fx_ask)
