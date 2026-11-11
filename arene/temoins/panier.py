"""temoin:panier : 1/6 de l'equity sur chaque symbole au premier cycle (frais compris), puis conservé."""

from __future__ import annotations

from collections.abc import Mapping

from arene.temoins import BP, TemoinContext, make_intent, never_traded
from arene.types import Intent, PortfolioState, Side

PORTFOLIO = "temoin:panier"


def decide(
    cycle_ts: int, state: PortfolioState, marks: Mapping[str, int], context: TemoinContext
) -> list[Intent]:
    """Au premier cycle (portefeuille encore vierge) : un achat de 1/n de l'equity par symbole ; ensuite rien.

    La condition « vierge » (aucune position, aucun frais) rend le témoin idempotent : si le premier
    cycle n'a pas pu acheter (donnée manquante), il retente au suivant ; une fois investi, il est inerte.
    """
    if not never_traded(state):
        return []
    n = len(context.symbols)
    size_bp = BP // n  # 1666 pour 6 : la somme reste <= 100 %
    return [
        make_intent(PORTFOLIO, cycle_ts, i, sym, Side.BUY, size_bp) for i, sym in enumerate(context.symbols)
    ]
