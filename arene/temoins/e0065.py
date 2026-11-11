"""temoin:e0065 (ADAPTÉ) : règle F1 « pression d'achat taker persistante » du labo, sur 6 paires.

Règle F1 (hypotheses/F1-pression-taker.md), paramètres L = 20, k = 3, H = 10, adaptée comme suit :
- univers : les 6 paires de l'arène (au lieu de 15) ;
- signal : r_i = taker_buy_base / volume sur les bougies 1 j Binance USDT ; exécution au prix Kraken EUR ;
- jours numérotés depuis le premier jour commun (n = 0) ; un jour D est un jour de reconstitution si
  n(D) mod H == 0 ; le rééquilibrage a lieu au premier cycle après 00:00 UTC de ce jour ;
- une paire est éligible si ses L derniers jours CLOS ont tous un volume > 0 ;
- classement par moyenne de r sur ces L jours (exacte, en fractions), égalité : ordre alphabétique ;
  les k premières visent 1/k de l'equity, les autres 0 (vente totale) ; moins de k éligibles : 1/k chacune ;
- aucune donnée du jour en cours : une barre 1 j n'est lue que si `ts + 86400 <= cycle_ts`.
"""

from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction

from arene.temoins import BP, DAY_S, TemoinContext, rebalance_intents
from arene.types import Intent, PortfolioState

PORTFOLIO = "temoin:e0065"
LABEL = "E0065 (adapté)"


def closed_days(context: TemoinContext, symbol: str, cycle_ts: int) -> dict[int, tuple[int, int]]:
    """{ts du jour: (volume, taker_buy_base)} des seules barres closes à `cycle_ts`."""
    return {
        b.ts: (b.volume, b.taker_buy_base)
        for b in context.day_bars.get(symbol, ())
        if b.ts + DAY_S <= cycle_ts
    }


def day0(context: TemoinContext, cycle_ts: int) -> int | None:
    """Premier jour commun (00:00 UTC) : `context.day0_ts`, sinon le plus tardif des premiers jours."""
    if context.day0_ts is not None:
        return context.day0_ts
    firsts = []
    for sym in context.symbols:
        days = closed_days(context, sym, cycle_ts)
        if days:
            firsts.append(min(days))
    return max(firsts) if firsts else None


def is_rebalance_cycle(cycle_ts: int, context: TemoinContext, day0_ts: int) -> bool:
    """Vrai si c'est le premier cycle de son jour UTC (ou le premier tout court) et que ce jour est un jour
    de reconstitution (n mod H == 0)."""
    day_start = cycle_ts - cycle_ts % DAY_S
    if day_start < day0_ts:
        return False
    if ((day_start - day0_ts) // DAY_S) % context.e0065.H != 0:
        return False
    return context.prev_cycle_ts is None or context.prev_cycle_ts < day_start


def ranking(cycle_ts: int, context: TemoinContext) -> list[tuple[str, Fraction]]:
    """Paires éligibles classées par r̄ décroissant (égalité : symbole alphabétique), avec leur r̄."""
    L = context.e0065.L
    last_day = cycle_ts - cycle_ts % DAY_S - DAY_S  # dernier jour clos
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


def target_weights(cycle_ts: int, context: TemoinContext) -> dict[str, int]:
    """Poids cibles (bp de l'equity) : 1/k pour chacune des k premières paires éligibles."""
    k = context.e0065.k
    picked = [s for s, _ in ranking(cycle_ts, context)[:k]]
    return {s: BP // k for s in picked}


def decide(
    cycle_ts: int, state: PortfolioState, marks: Mapping[str, int], context: TemoinContext
) -> list[Intent]:
    """Au premier cycle d'un jour de reconstitution : vendre ce qui sort, acheter ce qui entre, ajuster."""
    d0 = day0(context, cycle_ts)
    if d0 is None or not is_rebalance_cycle(cycle_ts, context, d0):
        return []
    targets = target_weights(cycle_ts, context)
    symbols = tuple(s for s in context.symbols if s in targets or s in state.positions)
    if any(s not in marks for s in symbols):
        symbols = tuple(s for s in symbols if s in marks)
    return rebalance_intents(PORTFOLIO, cycle_ts, state, marks, targets, symbols, context.min_trade_ueur)
