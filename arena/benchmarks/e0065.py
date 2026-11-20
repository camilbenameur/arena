"""benchmark:e0065 (ADAPTED): rule F1, "persistent taker buy pressure", on 6 pairs.

Rule F1 with parameters L = 20, k = 3, H = 10, adapted as follows:
- universe: the arena's 6 pairs (instead of 15);
- signal: r_i = taker_buy_base / volume on Binance USDT 1-day candles; execution at the Kraken EUR price;
- days are numbered from the first common day (n = 0); a day D is a rebalance day if
  n(D) mod H == 0; the rebalance happens on the first cycle after 00:00 UTC of that day;
- a pair is eligible if its last L CLOSED days all have volume > 0;
- ranking by mean r over those L days (exact, in fractions), ties: alphabetical order;
  the top k target 1/k of equity each, the others 0 (full sell); fewer than k eligible: 1/k each;
- no data from the current day: a 1-day bar is read only if `ts + 86400 <= cycle_ts`.
"""

from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction

from arena.benchmarks import BP, DAY_S, BenchmarkContext, rebalance_intents
from arena.types import Intent, PortfolioState

PORTFOLIO = "benchmark:e0065"
LABEL = "E0065 (adapted)"


def closed_days(context: BenchmarkContext, symbol: str, cycle_ts: int) -> dict[int, tuple[int, int]]:
    """{day ts: (volume, taker_buy_base)} for the bars closed at `cycle_ts` only."""
    return {
        b.ts: (b.volume, b.taker_buy_base)
        for b in context.day_bars.get(symbol, ())
        if b.ts + DAY_S <= cycle_ts
    }


def day0(context: BenchmarkContext, cycle_ts: int) -> int | None:
    """First common day (00:00 UTC): `context.day0_ts`, otherwise the latest of the first days."""
    if context.day0_ts is not None:
        return context.day0_ts
    firsts = []
    for sym in context.symbols:
        days = closed_days(context, sym, cycle_ts)
        if days:
            firsts.append(min(days))
    return max(firsts) if firsts else None


def is_rebalance_cycle(cycle_ts: int, context: BenchmarkContext, day0_ts: int) -> bool:
    """True if this is the first cycle of its UTC day (or the very first) and that day is a rebalance
    day (n mod H == 0)."""
    day_start = cycle_ts - cycle_ts % DAY_S
    if day_start < day0_ts:
        return False
    if ((day_start - day0_ts) // DAY_S) % context.e0065.H != 0:
        return False
    return context.prev_cycle_ts is None or context.prev_cycle_ts < day_start


def ranking(cycle_ts: int, context: BenchmarkContext) -> list[tuple[str, Fraction]]:
    """Eligible pairs ranked by descending mean r (ties: alphabetical symbol), with their mean r."""
    L = context.e0065.L
    last_day = cycle_ts - cycle_ts % DAY_S - DAY_S  # last closed day
    scored: list[tuple[str, Fraction]] = []
    for sym in context.symbols:
        days = closed_days(context, sym, cycle_ts)
        total = Fraction(0)
        ok = True
        for d in range(last_day - (L - 1) * DAY_S, last_day + 1, DAY_S):
            vol, taker = days.get(d, (0, 0))
            if vol <= 0:
                ok = False
                break
            total += Fraction(taker, vol)
        if ok:
            scored.append((sym, total / L))
    scored.sort(key=lambda t: (-t[1], t[0]))
    return scored


def target_weights(cycle_ts: int, context: BenchmarkContext) -> dict[str, int]:
    """Target weights (bp of equity): 1/k for each of the top k eligible pairs."""
    k = context.e0065.k
    picked = [s for s, _ in ranking(cycle_ts, context)[:k]]
    return {s: BP // k for s in picked}


def decide(
    cycle_ts: int, state: PortfolioState, marks: Mapping[str, int], context: BenchmarkContext
) -> list[Intent]:
    """On the first cycle of a rebalance day: sell what drops out, buy what comes in, adjust."""
    d0 = day0(context, cycle_ts)
    if d0 is None or not is_rebalance_cycle(cycle_ts, context, d0):
        return []
    targets = target_weights(cycle_ts, context)
    symbols = tuple(s for s in context.symbols if s in targets or s in state.positions)
    if any(s not in marks for s in symbols):
        symbols = tuple(s for s in symbols if s in marks)
    return rebalance_intents(PORTFOLIO, cycle_ts, state, marks, targets, symbols, context.min_trade_ueur)
