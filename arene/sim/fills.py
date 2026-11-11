"""Modèle de fills pessimiste (`pessimiste-v1`) : fonctions pures, entiers seulement (SPEC-MVP §8)."""

from __future__ import annotations

from arene.types import Bar, Instrument, Quote, Side, ceil_div, notional_ueur

FILL_MODEL_VERSION = "pessimiste-v1"
BP = 10_000


def _round_up_tick(px: int, tick: int) -> int:
    return ceil_div(px, tick) * tick if tick > 0 else px


def _round_down_tick(px: int, tick: int) -> int:
    return px // tick * tick if tick > 0 else px


def market_fill(
    side: Side, qty: int, quote: Quote, instrument: Instrument, fee_bp: int, slippage_bp: int
) -> tuple[int, int]:
    """(prix en µEUR, frais en µEUR) d'un ordre au marché.

    Achat : ask × (1 + slip), arrondi au tick vers le haut. Vente : bid × (1 − slip), arrondi au tick vers
    le bas. Frais = notional × fee_bp / 10 000 arrondi vers le haut ; le notional des frais est arrondi vers
    le haut (frais maximaux) pour l'achat comme pour la vente.
    """
    if side == Side.BUY:
        price = _round_up_tick(ceil_div(quote.ask * (BP + slippage_bp), BP), instrument.tick_ueur)
    else:
        price = _round_down_tick(quote.bid * (BP - slippage_bp) // BP, instrument.tick_ueur)
    fee = ceil_div(notional_ueur(qty, price, round_up=True) * fee_bp, BP)
    return price, fee


def stop_fill(position_stop_ueur: int, bar: Bar, instrument: Instrument, slippage_bp: int) -> int | None:
    """Prix de sortie d'un stop sur une barre close, ou None si la barre ne l'atteint pas.

    Gap : si la barre ouvre sous le stop, la sortie se fait à l'ouverture. Puis glissement, tick vers le bas.
    """
    if bar.low > position_stop_ueur:
        return None
    base = min(position_stop_ueur, bar.open)
    return _round_down_tick(base * (BP - slippage_bp) // BP, instrument.tick_ueur)


def stop_price(entry_price_ueur: int, stop_bp: int, instrument: Instrument) -> int:
    """Niveau du stop : prix d'entrée × (1 − stop_bp/10 000), arrondi au tick vers le bas."""
    return _round_down_tick(entry_price_ueur * (BP - stop_bp) // BP, instrument.tick_ueur)
