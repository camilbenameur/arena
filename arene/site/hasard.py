"""Trajectoires aléatoires du rang « face au hasard », rejouées sur les cycles ET sur les réveils complétés.

Le simulateur du moteur (`arene.temoins.trajectoires`, gelé pendant la saison) ne connaît que des cycles : chaque
ronde y a un quote pour chaque symbole, des stops sur barres et une détention maximale. Un réveil diffère
(docs/VEILLE.md §2) : seuls les symboles cotés au réveil sont négociables (les autres reçoivent NO_QUOTE), il n'y a
ni stop sur barres ni détention maximale, la médiane des spreads reste celle des quotes de cycle, PRICE_SANITY compare
à la clôture 1 min, et aucune equity n'est journalisée (les références 24 h, mois et sommet restent celles des
cycles). Ce module rejoue donc le même agent, avec les mêmes briques du moteur (riskd, fills, `aleatoire.decide`),
en suivant ces écarts. Sans réveil, il rend exactement les mêmes nombres que le simulateur du moteur
(vérifié par tests/test_site.py).
"""

from __future__ import annotations

from bisect import bisect_right
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from arene.ledger import month_start_ts
from arene.risk.policy import Policy
from arene.risk.riskd import MarketView, evaluate, freeze_or_halt
from arene.sim.fills import market_fill, stop_fill, stop_price
from arene.temoins import TemoinContext, aleatoire
from arene.temoins.trajectoires import (
    DAY_S,
    SPREAD_WINDOW,
    CycleData,
    _apply,
    _counters,
    _equity,
    _fee,
    _sell_all,
)
from arene.types import Instrument, PortfolioState, Side


@dataclass(frozen=True)
class Ronde:
    """Un cycle de 4 h (`reveil=False`) ou un réveil complété (`reveil=True`, quotes des seuls symboles cotés)."""

    data: CycleData
    reveil: bool = False


@dataclass(frozen=True)
class _Prepared:
    ts: int
    reveil: bool
    market: MarketView
    bars: Mapping[str, Sequence]
    month_start: int


def _prepare(rondes: Sequence[Ronde]) -> list[_Prepared]:
    spreads: dict[str, deque[int]] = {}
    medians: dict[str, int] = {}  # médiane courante, mise à jour aux seuls cycles (comme `_view` du moteur)
    out = []
    for r in rondes:
        c = r.data
        closes: dict[str, int] = {}
        if not r.reveil:
            for sym, q in c.quotes.items():
                win = spreads.setdefault(sym, deque(maxlen=SPREAD_WINDOW))
                win.append(q.ask - q.bid)
                medians[sym] = sorted(win)[len(win) // 2]
        med = {}
        for sym, q in c.quotes.items():
            # Sans historique de cycle, le spread courant (règle de MarketView : sinon SPREAD_ANOMALY).
            med[sym] = medians.get(sym, q.ask - q.bid)
            closes[sym] = c.last_closes.get(sym, (q.bid + q.ask) // 2)
        out.append(_Prepared(c.ts, r.reveil, MarketView(c.quotes, closes, med, c.marks), c.bars, month_start_ts(c.ts)))
    return out


def _simulate(
    prepared: Sequence[_Prepared], trajectoire: int, policy: Policy, instruments: Mapping[str, Instrument],
    fee_bp: int, slippage_bp: int, capital_ueur: int, depuis: int | None = None,
) -> tuple[int, int]:  # fmt: skip
    """(equity au début de la ronde `depuis`, avant toute action ; equity finale) de la trajectoire `trajectoire`.
    Même déroulé que `trajectoires._simulate` aux cycles. Sans `depuis`, la première valeur est le capital."""
    state = PortfolioState(aleatoire.PORTFOLIO, capital_ueur)
    context = TemoinContext(symbols=tuple(instruments), trajectoire=trajectoire)
    eq_ts: list[int] = []
    eq_val: list[int] = []
    peak = capital_ueur
    intent_fills: deque[int] = deque()
    fees: list[tuple[int, int]] = []
    last_buy_intent: dict[str, int] = {}
    eq_end = capital_ueur
    eq_depart = capital_ueur

    for cyc in prepared:
        ts, market = cyc.ts, cyc.market
        marks, quotes = market.marks, market.quotes
        if depuis is not None and ts == depuis:
            eq_depart = _equity(state, marks)  # comme saison_reference : avant les décisions de la ronde

        # Stops sur barres et détention maximale : aux cycles seulement (le réveil n'en fait pas).
        if not cyc.reveil:
            for sym in list(state.positions):
                pos = state.positions[sym]
                inst = instruments[sym]
                if pos.stop_ueur is not None:
                    for bar in cyc.bars.get(sym, ()):
                        if bar.ts < pos.opened_ts:
                            continue  # barre commencée avant l'entrée (garde de SimExecutor ; utile dès qu'on ouvre au réveil)
                        px = stop_fill(pos.stop_ueur, bar, inst, slippage_bp)
                        if px is not None:
                            _sell_all(state, fees, sym, px, _fee(pos.qty, px, fee_bp), ts)
                            break
                if sym in state.positions and ts - pos.opened_ts >= policy.max_holding_s and sym in quotes:
                    px, fee = market_fill(Side.SELL, pos.qty, quotes[sym], inst, fee_bp, slippage_bp)
                    _sell_all(state, fees, sym, px, fee, ts)

        while intent_fills and intent_fills[0] <= ts - DAY_S:
            intent_fills.popleft()
        fees[:] = [(t, f) for t, f in fees if t >= cyc.month_start]
        i24 = bisect_right(eq_ts, ts - DAY_S)
        eq_24h = eq_val[i24 - 1] if i24 else capital_ueur
        im = bisect_right(eq_ts, cyc.month_start - 1)
        eq_month = eq_val[im - 1] if im else capital_ueur
        eq_now = _equity(state, marks)
        base = (len(intent_fills), sum(f for _, f in fees), eq_month, eq_24h, peak)

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

        if not state.halted:
            orders = 0
            for intent in aleatoire.decide(ts, state, marks, context):
                if intent.symbol not in quotes:
                    continue  # symbole non coté à ce réveil : NO_QUOTE, comme le moteur
                last = last_buy_intent.get(intent.symbol)
                verdict = evaluate(
                    intent, state, market, policy, _counters(base, orders, last, eq_now), ts,
                    instruments, fee_bp, slippage_bp, False,  # type: ignore[arg-type]
                )  # fmt: skip
                if not verdict.approved:
                    continue
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
        if not cyc.reveil:  # aucune equity journalisée au réveil : références 24 h, mois et sommet aux cycles
            eq_ts.append(ts)
            eq_val.append(eq_end)
            peak = max(peak, eq_end)
    return eq_depart, eq_end


def trajectoires(
    rondes: Sequence[Ronde], n: int, *, policy: Policy, instruments: Mapping[str, Instrument], fee_bp: int,
    slippage_bp: int, capital_ueur: int,
) -> list[int]:  # fmt: skip
    """Equity finale (µEUR) des trajectoires 1..n, déterministe."""
    return [f for _d, f in trajectoires_depuis(
        rondes, n, policy=policy, instruments=instruments, fee_bp=fee_bp, slippage_bp=slippage_bp,
        capital_ueur=capital_ueur,
    )]  # fmt: skip


def trajectoires_depuis(
    rondes: Sequence[Ronde], n: int, *, policy: Policy, instruments: Mapping[str, Instrument], fee_bp: int,
    slippage_bp: int, capital_ueur: int, depuis: int | None = None,
) -> list[tuple[int, int]]:  # fmt: skip
    """(equity au début de la ronde `depuis`, equity finale) des trajectoires 1..n. Toutes les rondes sont rejouées
    (le rodage amorce la médiane des spreads, le sommet et les références 24 h et mois), la mesure part de `depuis`."""
    prepared = _prepare(rondes)
    if not prepared:
        return [(capital_ueur, capital_ueur)] * n
    return [
        _simulate(prepared, t, policy, instruments, fee_bp, slippage_bp, capital_ueur, depuis) for t in range(1, n + 1)
    ]
