"""Pessimistic fill model (`pessimiste-v1`): pure functions, integers only (SPEC-MVP §8)."""

from __future__ import annotations

from arena.types import Bar, Instrument, Quote, Side, ceil_div, notional_ueur

FILL_MODEL_VERSION = "pessimistic-v1"
BP = 10_000


def _round_up_tick(px: int, tick: int) -> int:
    return ceil_div(px, tick) * tick if tick > 0 else px


def _round_down_tick(px: int, tick: int) -> int:
    return px // tick * tick if tick > 0 else px


def market_fill(
    side: Side, qty: int, quote: Quote, instrument: Instrument, fee_bp: int, slippage_bp: int
) -> tuple[int, int]:
    """(price in µEUR, fee in µEUR) of a market order.

    Buy: ask x (1 + slip), rounded up to the tick. Sell: bid x (1 - slip), rounded down to the tick.
    Fee = notional x fee_bp / 10,000 rounded up; the fee notional is rounded up (maximum fees) for
    buys and sells alike.
    """
    if side == Side.BUY:
        price = _round_up_tick(ceil_div(quote.ask * (BP + slippage_bp), BP), instrument.tick_ueur)
    else:
        price = _round_down_tick(quote.bid * (BP - slippage_bp) // BP, instrument.tick_ueur)
    fee = ceil_div(notional_ueur(qty, price, round_up=True) * fee_bp, BP)
    return price, fee


def stop_fill(position_stop_ueur: int, bar: Bar, instrument: Instrument, slippage_bp: int) -> int | None:
    """Exit price of a stop on a closed bar, or None if the bar does not reach it.

    Gap: if the bar opens below the stop, the exit is at the open. Then slippage, tick rounded down.
    """
    if bar.low > position_stop_ueur:
        return None
    base = min(position_stop_ueur, bar.open)
    return _round_down_tick(base * (BP - slippage_bp) // BP, instrument.tick_ueur)


def stop_price(entry_price_ueur: int, stop_bp: int, instrument: Instrument) -> int:
    """Stop level: entry price x (1 - stop_bp/10,000), rounded down to the tick."""
    return _round_down_tick(entry_price_ueur * (BP - stop_bp) // BP, instrument.tick_ueur)
