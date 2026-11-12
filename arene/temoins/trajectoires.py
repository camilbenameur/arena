"""Trajectoires aléatoires hors ligne (docs/SPEC-MVP.md §10) : 1 000 rejeux de l'agent aléatoire.

Chaque trajectoire rejoue `temoin:aleatoire` sur les MÊMES cycles et les MÊMES quotes que l'arène, avec
SES graines (numéro de trajectoire 1..n), passe par `riskd.evaluate` (compteurs recalculés dans la
simulation, pas lus dans le journal réel) et par `market_fill` ; les stops (`stop_fill`), la détention
maximale, le gel et l'arrêt (drawdown) sont rejoués comme dans le cycle réel. Entiers seulement.

Le marché de chaque cycle (MarketView : quotes, dernières clôtures, médiane des spreads, marks) est calculé
UNE fois et partagé par toutes les trajectoires.
"""

from __future__ import annotations

import warnings
from bisect import bisect_right
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from arene.ledger import month_start_ts
from arene.risk.policy import Policy
from arene.risk.riskd import BP, Counters, MarketView, evaluate, freeze_or_halt
from arene.sim.fills import market_fill, stop_fill, stop_price
from arene.temoins import TemoinContext, aleatoire
from arene.types import (
    Bar,
    Instrument,
    PortfolioState,
    Position,
    Quote,
    Side,
    ceil_div,
    notional_ueur,
)

DAY_S = 86_400
MINUTE_S = 60
SPREAD_WINDOW = 20


@dataclass(frozen=True)
class CycleData:
    """Ce que le journal a retenu d'un cycle passé.

    ts          : ts du cycle de décision.
    quotes      : quotes journalisés par symbole.
    marks       : prix de valorisation par symbole (en pratique le mid du quote).
    last_closes : dernière clôture 4 h par symbole (PRICE_SANITY) ; à défaut, le mid du quote.
    bars        : barres 4 h closes depuis le cycle précédent, par symbole (pour les stops). Si aucun cycle
                  n'en fournit, les stops ne sont pas simulés (un avertissement est émis).
    """

    ts: int
    quotes: Mapping[str, Quote]
    marks: Mapping[str, int]
    last_closes: Mapping[str, int] = field(default_factory=dict)
    bars: Mapping[str, Sequence[Bar]] = field(default_factory=dict)


@dataclass(frozen=True)
class _Prepared:
    ts: int
    market: MarketView
    bars: Mapping[str, Sequence[Bar]]
    month_start: int


def _prepare(cycles: Sequence[CycleData]) -> list[_Prepared]:
    spreads: dict[str, deque[int]] = {}
    out = []
    for c in cycles:
        medians: dict[str, int] = {}
        closes: dict[str, int] = {}
        for sym, q in c.quotes.items():
            win = spreads.setdefault(sym, deque(maxlen=SPREAD_WINDOW))
            win.append(q.ask - q.bid)
            medians[sym] = sorted(win)[len(win) // 2]
            closes[sym] = c.last_closes.get(sym, (q.bid + q.ask) // 2)
        out.append(
            _Prepared(
                ts=c.ts,
                market=MarketView(c.quotes, closes, medians, c.marks),
                bars=c.bars,
                month_start=month_start_ts(c.ts),
            )
        )
    return out


def _fee(qty: int, price: int, fee_bp: int) -> int:
    return ceil_div(notional_ueur(qty, price, round_up=True) * fee_bp, BP)


def _apply(state: PortfolioState, sym: str, side: Side, qty: int, price: int, fee: int, ts: int) -> bool:
    """Applique un fill comme `ledger.replay`. Faux (sans rien changer) si cash ou position insuffisant."""
    pos = state.positions.get(sym)
    if side == Side.BUY:
        total = notional_ueur(qty, price, round_up=True) + fee
        if qty <= 0 or total > state.cash_ueur:
            return False
        state.cash_ueur -= total
        if pos is None:
            state.positions[sym] = Position(sym, qty, total, ts)
        else:
            pos.qty += qty
            pos.cost_ueur += total
    else:
        if pos is None or qty <= 0 or qty > pos.qty:
            return False
        gross = notional_ueur(qty, price, round_up=False)
        removed = pos.cost_ueur if qty == pos.qty else ceil_div(pos.cost_ueur * qty, pos.qty)
        pos.qty -= qty
        pos.cost_ueur -= removed
        if pos.qty == 0:
            del state.positions[sym]
        state.cash_ueur += gross - fee
    state.fees_paid_ueur += fee
    return True


def _sell_all(
    state: PortfolioState, fees: list[tuple[int, int]], sym: str, price: int, fee: int, ts: int
) -> None:
    if _apply(state, sym, Side.SELL, state.positions[sym].qty, price, fee, ts):
        fees.append((ts, fee))


def _counters(base: tuple[int, int, int, int, int], orders: int, last: int | None, eq_now: int) -> Counters:
    trades, fees_month, eq_month, eq_24h, peak = base
    return Counters(
        trades_24h=trades,
        orders_last_minute=orders,
        last_symbol_intent_ts=last,
        fees_month_ueur=fees_month,
        equity_month_start_ueur=eq_month,
        equity_24h_ago_ueur=eq_24h,
        equity_peak_ueur=peak,
        equity_now_ueur=eq_now,
    )


def _equity(state: PortfolioState, marks: Mapping[str, int]) -> int:
    return state.cash_ueur + sum(
        notional_ueur(p.qty, marks[s], round_up=False) for s, p in state.positions.items()
    )


def _simulate(
    prepared: Sequence[_Prepared],
    trajectoire: int,
    policy: Policy,
    instruments: Mapping[str, Instrument],
    fee_bp: int,
    slippage_bp: int,
    capital_ueur: int,
) -> list[int]:
    """Equity après chaque cycle pour la trajectoire `trajectoire`."""
    state = PortfolioState(aleatoire.PORTFOLIO, capital_ueur)
    context = TemoinContext(symbols=tuple(instruments), trajectoire=trajectoire)
    eq_ts: list[int] = []
    eq_val: list[int] = []
    peak = capital_ueur
    intent_fills: deque[int] = deque()  # ts des fills issus d'une intention (fenêtre 24 h)
    fees: list[tuple[int, int]] = []  # (ts, frais) du mois courant
    last_buy_intent: dict[str, int] = {}

    for cyc in prepared:
        ts, market = cyc.ts, cyc.market
        marks = market.marks
        quotes = market.quotes

        # 4. Stops (barres closes depuis le dernier cycle), puis détention maximale.
        for sym in list(state.positions):
            pos = state.positions[sym]
            inst = instruments[sym]
            if pos.stop_ueur is not None:
                for bar in cyc.bars.get(sym, ()):
                    px = stop_fill(pos.stop_ueur, bar, inst, slippage_bp)
                    if px is not None:
                        _sell_all(state, fees, sym, px, _fee(pos.qty, px, fee_bp), ts)
                        break
            if sym in state.positions and ts - pos.opened_ts >= policy.max_holding_s and sym in quotes:
                px, fee = market_fill(Side.SELL, pos.qty, quotes[sym], inst, fee_bp, slippage_bp)
                _sell_all(state, fees, sym, px, fee, ts)

        # Fenêtres glissantes, équité de référence.
        while intent_fills and intent_fills[0] <= ts - DAY_S:
            intent_fills.popleft()
        fees[:] = [(t, f) for t, f in fees if t >= cyc.month_start]
        i24 = bisect_right(eq_ts, ts - DAY_S)
        eq_24h = eq_val[i24 - 1] if i24 else capital_ueur
        im = bisect_right(eq_ts, cyc.month_start - 1)
        eq_month = eq_val[im - 1] if im else capital_ueur
        eq_now = _equity(state, marks)
        fees_month = sum(f for _, f in fees)

        base = (len(intent_fills), fees_month, eq_month, eq_24h, peak)

        # 5. Gel / arrêt.
        code, until = freeze_or_halt(state, _counters(base, 0, None, eq_now), policy, ts)
        if code == "HALTED" and not state.halted:
            state.halted = True
            for sym in list(state.positions):
                if sym in quotes:
                    pos = state.positions[sym]
                    px, fee = market_fill(Side.SELL, pos.qty, quotes[sym], instruments[sym], fee_bp, slippage_bp)
                    _sell_all(state, fees, sym, px, fee, ts)
            eq_now = _equity(state, marks)
        elif code == "FROZEN":
            state.frozen_until_ts = max(state.frozen_until_ts, until)

        # 6. Décisions, riskd, exécution.
        if not state.halted:
            orders = 0
            for intent in aleatoire.decide(ts, state, marks, context):
                last = last_buy_intent.get(intent.symbol)
                verdict = evaluate(
                    intent, state, market, policy, _counters(base, orders, last, eq_now), ts,
                    instruments, fee_bp, slippage_bp, False,
                )  # fmt: skip
                if not verdict.approved or intent.symbol not in quotes:
                    continue  # symbole sans quote : non négociable (comme NO_QUOTE dans le moteur), jamais KeyError
                orders += 1
                if intent.side == Side.BUY:
                    last_buy_intent[intent.symbol] = ts
                inst = instruments[intent.symbol]
                px, fee = market_fill(intent.side, verdict.qty, quotes[intent.symbol], inst, fee_bp, slippage_bp)
                if _apply(state, intent.symbol, intent.side, verdict.qty, px, fee, ts):
                    intent_fills.append(ts)
                    fees.append((ts, fee))
                    if intent.side == Side.BUY and intent.stop_bp is not None:
                        state.positions[intent.symbol].stop_ueur = stop_price(px, intent.stop_bp, inst)

        eq_end = _equity(state, marks)
        eq_ts.append(ts)
        eq_val.append(eq_end)
        peak = max(peak, eq_end)
    return eq_val


def _normalize(instruments: Mapping[str, Instrument] | Iterable[Instrument]) -> dict[str, Instrument]:
    if isinstance(instruments, Mapping):
        return dict(instruments)
    return {i.symbol: i for i in instruments}


def simulate_trajectory(
    cycles: Sequence[CycleData],
    trajectoire: int,
    *,
    policy: Policy,
    instruments: Mapping[str, Instrument] | Iterable[Instrument],
    fee_bp: int,
    slippage_bp: int,
    capital_ueur: int,
) -> list[int]:
    """Une trajectoire : equity (µEUR) après chaque cycle."""
    return _simulate(
        _prepare(cycles), trajectoire, policy, _normalize(instruments), fee_bp, slippage_bp, capital_ueur
    )


def simulate_random_trajectories(
    cycles: Sequence[CycleData],
    n: int = 1000,
    *,
    policy: Policy,
    instruments: Mapping[str, Instrument] | Iterable[Instrument],
    fee_bp: int,
    slippage_bp: int,
    capital_ueur: int,
) -> list[int]:
    """Equity finale (µEUR) de chacune des `n` trajectoires aléatoires (numéros 1..n), déterministe."""
    if cycles and not any(c.bars for c in cycles):
        warnings.warn("aucune barre 4 h fournie : les stops ne sont pas simulés", RuntimeWarning, stacklevel=2)
    prepared = _prepare(cycles)
    inst = _normalize(instruments)
    if not prepared:
        return [capital_ueur] * n
    return [
        _simulate(prepared, t, policy, inst, fee_bp, slippage_bp, capital_ueur)[-1] for t in range(1, n + 1)
    ]
