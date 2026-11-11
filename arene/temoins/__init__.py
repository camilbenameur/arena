"""Témoins de l'arène (docs/SPEC-MVP.md §10) : panier, 60/40, E0065 adapté, aléatoire.

Chaque témoin expose `decide(cycle_ts, state, marks, context) -> list[Intent]`. Les intentions sont exprimées
comme celles des LLM : `size_bp` en points de base de l'equity pour un achat, de la position pour une vente.

`panier`, `6040` et `e0065` sont des RÉFÉRENCES : elles ne passent pas par les plafonds de taille de riskd.
Leur quantité est calculée par `reference_qty` (arrondi vers le bas, frais compris, jamais de cash négatif).
`aleatoire` passe par riskd exactement comme un LLM (c'est le cycle qui l'appelle).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from arene.config import E0065Params
from arene.data.binance import DayBar
from arene.deciders.llm import UNIVERSE, make_intent_id
from arene.ledger import equity_ueur
from arene.sim.fills import market_fill
from arene.types import (
    QTY_SCALE,
    Bar,
    Instrument,
    Intent,
    PortfolioState,
    Quote,
    Side,
    notional_ueur,
)

BP = 10_000
DAY_S = 86_400


@dataclass(frozen=True)
class TemoinContext:
    """Ce que le cycle fournit aux témoins en plus de l'état et des marks.

    cycle_index   : numéro du cycle depuis le début de l'arène (0 = premier).
    prev_cycle_ts : ts du cycle précédent (None au tout premier).
    interval_s    : durée d'un cycle (4 h).
    symbols       : univers, dans l'ordre canonique.
    bars_4h       : barres 4 h closes par symbole (information ; aucun témoin n'en a besoin pour décider).
    day_bars      : bougies 1 j Binance par symbole CANONIQUE ("BTC/EUR"), pour E0065. Seules les barres
                    closes à `cycle_ts` sont lues, quoi que contienne la liste (anti-fuite).
    e0065         : paramètres L, k, H.
    day0_ts       : premier jour commun (00:00 UTC) servant à numéroter les jours de E0065. À figer une fois
                    pour toutes par l'appelant ; si None, calculé comme le plus tardif des premiers jours
                    disponibles (fragile si le cache est tronqué par le haut).
    trajectoire   : numéro de trajectoire de l'aléatoire (0 = la trajectoire vivante).
    min_trade_ueur: sous ce notional, un ajustement de référence est ignoré (poussière).
    """

    cycle_index: int = 0
    prev_cycle_ts: int | None = None
    interval_s: int = 14_400
    symbols: tuple[str, ...] = UNIVERSE
    bars_4h: Mapping[str, Sequence[Bar]] = field(default_factory=dict)
    day_bars: Mapping[str, Sequence[DayBar]] = field(default_factory=dict)
    e0065: E0065Params = field(default_factory=lambda: E0065Params(L=20, k=3, H=10))
    day0_ts: int | None = None
    trajectoire: int = 0
    min_trade_ueur: int = 5_000_000


def never_traded(state: PortfolioState) -> bool:
    """Vrai tant que le portefeuille n'a ni position ni frais payés (aucun achat n'a encore eu lieu)."""
    return not state.positions and state.fees_paid_ueur == 0


def make_intent(
    portfolio: str,
    cycle: int,
    index: int,
    symbol: str,
    side: Side,
    size_bp: int,
    *,
    stop_bp: int | None = None,
    horizon_h: int | None = None,
    expected_move_bp: int | None = None,
    confidence_pct: int | None = None,
) -> Intent:
    """Intention avec un `intent_id` fabriqué comme celui des LLM (`make_intent_id`)."""
    content = {
        "symbol": symbol,
        "side": side.value,
        "size_bp": size_bp,
        "stop_bp": stop_bp,
        "horizon_h": horizon_h,
        "expected_move_bp": expected_move_bp,
        "confidence_pct": confidence_pct,
    }
    return Intent(
        intent_id=make_intent_id(portfolio, cycle, index, content),
        portfolio=portfolio,
        cycle=cycle,
        symbol=symbol,
        side=side,
        size_bp=size_bp,
        stop_bp=stop_bp,
        horizon_h=horizon_h,
        expected_move_bp=expected_move_bp,
        confidence_pct=confidence_pct,
    )


def rebalance_intents(
    portfolio: str,
    cycle_ts: int,
    state: PortfolioState,
    marks: Mapping[str, int],
    targets_bp: Mapping[str, int],
    symbols: Sequence[str],
    min_trade_ueur: int,
) -> list[Intent]:
    """Intentions qui ramènent chaque symbole de `symbols` vers son poids cible (bp de l'equity).

    Les ventes viennent d'abord (elles libèrent le cash des achats). Un symbole détenu qui n'a pas de cible
    est vendu en totalité. Un écart de valeur sous `min_trade_ueur` est ignoré. Un achat est exprimé en bp
    de l'equity, une vente en bp de la position (arrondis vers le bas, donc jamais trop gros).
    """
    equity = equity_ueur(state, marks)
    if equity <= 0:
        return []
    sells: list[tuple[str, int]] = []
    buys: list[tuple[str, int]] = []
    for sym in symbols:
        pos = state.positions.get(sym)
        held = notional_ueur(pos.qty, marks[sym], round_up=False) if pos and pos.qty > 0 else 0
        target = equity * targets_bp.get(sym, 0) // BP
        gap = target - held
        if abs(gap) < min_trade_ueur and not (target == 0 and held > 0):
            continue
        if gap < 0:
            frac = BP if target == 0 else (-gap) * BP // held
            if frac > 0:
                sells.append((sym, min(frac, BP)))
        elif gap > 0:
            size = gap * BP // equity
            if size > 0:
                buys.append((sym, size))
    out: list[Intent] = []
    for sym, size in sells:
        out.append(make_intent(portfolio, cycle_ts, len(out), sym, Side.SELL, size))
    for sym, size in buys:
        out.append(make_intent(portfolio, cycle_ts, len(out), sym, Side.BUY, size))
    return out


def reference_qty(
    intent: Intent,
    state: PortfolioState,
    marks: Mapping[str, int],
    quote: Quote,
    instrument: Instrument,
    fee_bp: int,
    slippage_bp: int,
) -> int:
    """Quantité (1e-8) à exécuter pour une intention de référence ; 0 = ne rien exécuter.

    Achat : budget = equity × size_bp / 10 000, plafonné au cash ; plus grande quantité dont le coût
    (arrondi vers le haut) + frais tient dans le budget (arrondi vers le bas, jamais de cash négatif).
    Vente : position × size_bp / 10 000 vers le bas (toute la position si size_bp >= 10 000).
    Sous le lot minimal ou le coût minimal de l'instrument : 0.
    """
    if intent.size_bp <= 0:
        return 0
    if intent.side == Side.SELL:
        pos = state.positions.get(intent.symbol)
        if pos is None or pos.qty <= 0:
            return 0
        if intent.size_bp >= BP:
            return pos.qty  # mise à plat : toujours permise
        qty = pos.qty * intent.size_bp // BP
        if qty <= 0:
            return 0
        price, _ = market_fill(Side.SELL, qty, quote, instrument, fee_bp, slippage_bp)
        if qty < instrument.lot_min_qty or notional_ueur(qty, price, round_up=False) < instrument.cost_min_ueur:
            return 0
        return qty

    equity = equity_ueur(state, marks)
    budget = min(equity * intent.size_bp // BP, state.cash_ueur)
    if budget <= 0:
        return 0
    price, _ = market_fill(Side.BUY, QTY_SCALE, quote, instrument, fee_bp, slippage_bp)  # le prix ne dépend pas de qty
    if price <= 0:
        return 0
    qty = budget * BP * QTY_SCALE // (price * (BP + fee_bp))
    while qty > 0:
        _, fee = market_fill(Side.BUY, qty, quote, instrument, fee_bp, slippage_bp)
        total = notional_ueur(qty, price, round_up=True) + fee
        if total <= budget:
            break
        qty -= max(1, (total - budget) * QTY_SCALE // price)
    if qty <= 0 or qty < instrument.lot_min_qty:
        return 0
    if notional_ueur(qty, price, round_up=False) < instrument.cost_min_ueur:
        return 0
    return qty
