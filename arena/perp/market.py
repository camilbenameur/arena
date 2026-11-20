"""Market view of the perp league at a given instant, built ONLY from the collector's store (no network).

`market_view(store, symbols, now_ts)` gives riskd its `PerpMarketView`: the latest ticker snapshot at or
before `now_ts` (bid, ask, mark, index, funding and their observation time), the median spread over the
last snapshots, and EUR/USD. `last_marks` gives the latest closed one-minute mark per instrument.
Nothing after `now_ts` is ever read.
"""

from __future__ import annotations

from collections.abc import Iterable

from arena.perp.riskd import InstrumentMarket, PerpMarketView
from arena.perp.store import PerpDataStore, TickerSnapshot

SPREAD_WINDOW = 20
LOOKBACK_S = 6 * 3600  # snapshots older than that are not used for the median spread


def recent_snapshots(store: PerpDataStore, now_ts: int, lookback_s: int = LOOKBACK_S) -> list[TickerSnapshot]:
    return store.tickers().load(now_ts - lookback_s, now_ts + 1)


def market_view(store: PerpDataStore, symbols: Iterable[str], now_ts: int) -> PerpMarketView | None:
    """None when there is no snapshot at all (the caller refuses entries)."""
    snaps = recent_snapshots(store, now_ts)
    if not snaps:
        return None
    last = snaps[-1]
    by_sym: dict[str, InstrumentMarket] = {}
    for sym in symbols:
        t = next((x for x in last.tickers if x.kraken_symbol == sym), None)
        if t is None:
            continue
        spreads = sorted(
            x.ask_uusd - x.bid_uusd
            for s in snaps[-SPREAD_WINDOW:]
            for x in s.tickers
            if x.kraken_symbol == sym and x.ask_uusd >= x.bid_uusd > 0
        )
        by_sym[sym] = InstrumentMarket(
            bid_uusd=t.bid_uusd,
            ask_uusd=t.ask_uusd,
            quote_ts=t.ts,
            mark_uusd=t.mark_uusd,
            mark_ts=t.ts,
            index_uusd=t.index_uusd,
            index_ts=t.ts if t.index_uusd is not None else None,
            relative_funding_e12=t.relative_funding_e12,
            funding_ts=t.ts if t.relative_funding_e12 is not None else None,
            median_spread_uusd=spreads[len(spreads) // 2] if spreads else None,
        )
    fx = last.fx
    if fx is None:
        return PerpMarketView(by_sym, 0, 0, last.ts)  # NO_FX for entries; reductions need a quote only
    return PerpMarketView(by_sym, fx.bid_uusd_per_eur, fx.ask_uusd_per_eur, fx.ts)


def worst_half_spread_bp(store: PerpDataStore, symbol: str, now_ts: int, window_s: int = 7 * 86400) -> int:
    """Worst half-spread (bp of the mid) seen over the window: the extra exit slippage of stops (study §3.5)."""
    worst = 0
    for s in store.tickers().load(now_ts - window_s, now_ts + 1):
        for t in s.tickers:
            if t.kraken_symbol == symbol and t.ask_uusd >= t.bid_uusd > 0:
                mid2 = t.ask_uusd + t.bid_uusd
                worst = max(worst, -(-(t.ask_uusd - t.bid_uusd) * 10_000 // mid2))
    return worst
