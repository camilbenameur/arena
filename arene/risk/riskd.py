"""riskd : le garde-fou de risque (docs/SPEC-MVP.md §7). FONCTION PURE, aucun I/O, aucun float.

`evaluate()` reçoit tout ce dont elle a besoin en argument (état, marché, compteurs issus du journal,
politique) et renvoie un `Verdict` : approuvé avec une quantité, ou rejeté avec TOUS les codes violés.
Tous les montants sont des entiers (µEUR, unités 1e-8) ; les arrondis sont défavorables :
quantité approuvée vers le bas, coût et exposition estimés vers le haut, equity vers le bas.

Principe : en cas de doute (donnée manquante, valeur absurde), on REFUSE l'entrée (fail closed).
Une vente réduit le risque : elle n'est soumise qu'à NOT_WHITELISTED, NO_SHORT, ORDER_RATE et
ORDER_TOO_SMALL (sauf mise à plat complète), et reste permise si le portefeuille est gelé, arrêté
ou si le coupe-circuit est actif.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from arene.risk.policy import Policy
from arene.types import (
    QTY_SCALE,
    Instrument,
    Intent,
    PortfolioState,
    Quote,
    Side,
    Verdict,
    ceil_div,
    notional_ueur,
)

BP = 10_000  # 1 = 100 % en points de base

# --- Codes de règle de la spec §7 ---
NOT_WHITELISTED = "NOT_WHITELISTED"
MAX_ORDER_SIZE = "MAX_ORDER_SIZE"
MAX_POSITION = "MAX_POSITION"
MAX_EXPOSURE = "MAX_EXPOSURE"
INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
DAILY_TRADES = "DAILY_TRADES"
ORDER_RATE = "ORDER_RATE"
TOO_SOON = "TOO_SOON"
STOP_REQUIRED = "STOP_REQUIRED"
STOP_RANGE = "STOP_RANGE"
EDGE_TOO_SMALL = "EDGE_TOO_SMALL"
FROZEN = "FROZEN"
HALTED = "HALTED"
FEE_BUDGET = "FEE_BUDGET"
PRICE_SANITY = "PRICE_SANITY"
SPREAD_ANOMALY = "SPREAD_ANOMALY"
ORDER_TOO_SMALL = "ORDER_TOO_SMALL"
NO_SHORT = "NO_SHORT"
KILL_SWITCH = "KILL_SWITCH"
# --- Codes techniques (entrée absente ou absurde : on refuse) ---
BAD_SIDE = "BAD_SIDE"  # côté ni buy ni sell
BAD_SIZE = "BAD_SIZE"  # size_bp absent, non entier ou <= 0
BAD_PARAMS = "BAD_PARAMS"  # fee_bp / slippage_bp / now_ts négatifs ou non entiers
NO_QUOTE = "NO_QUOTE"  # quote absent ou incohérent (bid <= 0, ask < bid)
NO_MARK = "NO_MARK"  # une position détenue n'a pas de mark > 0 : equity non valorisable
NO_EQUITY = "NO_EQUITY"  # equity <= 0
UNKNOWN_INSTRUMENT = "UNKNOWN_INSTRUMENT"  # symbole absent de `instruments`
INTERNAL_ERROR = "INTERNAL_ERROR"  # bug : exception interceptée, on refuse par sécurité

ALL_CODES: tuple[str, ...] = tuple(
    sorted(
        (
            NOT_WHITELISTED, MAX_ORDER_SIZE, MAX_POSITION, MAX_EXPOSURE, INSUFFICIENT_CASH, DAILY_TRADES,
            ORDER_RATE, TOO_SOON, STOP_REQUIRED, STOP_RANGE, EDGE_TOO_SMALL, FROZEN, HALTED, FEE_BUDGET,
            PRICE_SANITY, SPREAD_ANOMALY, ORDER_TOO_SMALL, NO_SHORT, KILL_SWITCH, BAD_SIDE, BAD_SIZE,
            BAD_PARAMS, NO_QUOTE, NO_MARK, NO_EQUITY, UNKNOWN_INSTRUMENT, INTERNAL_ERROR,
        )
    )
)  # fmt: skip


@dataclass(frozen=True)
class MarketView:
    """Marché au moment de la décision, par symbole (prix en µEUR).

    quotes            : quote courant (bid/ask).
    last_closes       : dernière clôture 4 h (barre close) ; sert au contrôle PRICE_SANITY.
    median_spreads_ueur : médiane de (ask - bid) sur les 20 derniers quotes du symbole. Si l'historique
                        est vide, l'appelant fournit le spread courant (sinon SPREAD_ANOMALY, fail closed).
    marks             : prix de valorisation de chaque position détenue (en pratique le mid du quote).
    """

    quotes: Mapping[str, Quote] = field(default_factory=dict)
    last_closes: Mapping[str, int] = field(default_factory=dict)
    median_spreads_ueur: Mapping[str, int] = field(default_factory=dict)
    marks: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Counters:
    """Compteurs calculés à partir du journal (jamais ailleurs) et passés en argument.

    trades_24h              : fills (achats et ventes) du portefeuille sur les 24 h glissantes.
    orders_last_minute      : ordres, tous portefeuilles confondus, sur la dernière minute.
    last_symbol_intent_ts   : ts de la dernière intention d'ACHAT approuvée de ce portefeuille sur le
                              symbole évalué (None si aucune). Une intention rejetée ne bloque pas.
    fees_month_ueur         : frais payés par le portefeuille dans le mois civil courant.
    equity_month_start_ueur : equity du portefeuille au début du mois civil (capital si ouvert dans le mois).
    equity_24h_ago_ueur     : equity du portefeuille il y a 24 h.
    equity_peak_ueur        : plus haut d'equity du portefeuille.
    equity_now_ueur         : equity courante (dernier événement `equity`), utilisée par freeze_or_halt.
    """

    trades_24h: int = 0
    orders_last_minute: int = 0
    last_symbol_intent_ts: int | None = None
    fees_month_ueur: int = 0
    equity_month_start_ueur: int = 0
    equity_24h_ago_ueur: int = 0
    equity_peak_ueur: int = 0
    equity_now_ueur: int = 0


def _is_int(value: object) -> bool:
    return type(value) is int  # exclut bool et float


def _quote_ok(q: Quote | None) -> bool:
    return q is not None and _is_int(q.bid) and _is_int(q.ask) and q.bid > 0 and q.ask >= q.bid


def _freeze_halt(
    equity_now: int, state: PortfolioState, counters: Counters, policy: Policy, now_ts: int
) -> tuple[str | None, int]:
    """Cœur commun de freeze_or_halt et du contrôle d'évaluation. Priorité à l'arrêt."""
    peak = counters.equity_peak_ueur
    if state.halted:
        return HALTED, 0
    # Drawdown >= seuil depuis le plus haut : (peak - eq) / peak >= bp / 10000.
    if peak > 0 and (peak - equity_now) * BP >= policy.drawdown_halt_bp * peak:
        return HALTED, 0
    ago = counters.equity_24h_ago_ueur
    # Perte >= seuil sur 24 h : (ago - eq) / ago >= bp / 10000.
    if ago > 0 and (ago - equity_now) * BP >= policy.daily_loss_freeze_bp * ago:
        return FROZEN, now_ts + policy.freeze_duration_s
    return None, 0


def freeze_or_halt(
    state: PortfolioState, counters: Counters, policy: Policy, now_ts: int
) -> tuple[str | None, int]:
    """Dit si le portefeuille doit être arrêté, gelé, ou rien.

    Renvoie (HALTED, 0) si drawdown >= drawdown_halt_bp (ou déjà arrêté), (FROZEN, now_ts + durée) si perte
    24 h >= daily_loss_freeze_bp, sinon (None, 0). Équity courante = counters.equity_now_ueur.
    """
    return _freeze_halt(counters.equity_now_ueur, state, counters, policy, now_ts)


def _positions_value(state: PortfolioState, marks: Mapping[str, int], *, round_up: bool) -> int | None:
    """Valeur des positions aux marks ; None si une position détenue n'a pas de mark > 0."""
    total = 0
    for symbol, pos in state.positions.items():
        if pos.qty <= 0:
            continue
        mark = marks.get(symbol)
        if not _is_int(mark) or mark <= 0:
            return None
        total += notional_ueur(pos.qty, mark, round_up=round_up)
    return total


def _reject(intent_id: str, reasons: set[str], policy: Policy) -> Verdict:
    return Verdict(
        intent_id=intent_id,
        approved=False,
        reasons=tuple(sorted(reasons)),
        qty=0,
        reserved_ueur=0,
        policy_sha256=policy.sha256,
    )


def _exec_price(ask: int, slippage_bp: int, tick: int) -> int:
    """Prix d'achat pessimiste : ask majoré du glissement, arrondi vers le haut, puis au tick supérieur."""
    px = ceil_div(ask * (BP + slippage_bp), BP)
    if tick > 0:
        px = ceil_div(px, tick) * tick
    return px


def _buy_total(qty: int, px: int, fee_bp: int) -> tuple[int, int]:
    """(coût, coût + frais) d'un achat, tous deux arrondis vers le haut."""
    cost = notional_ueur(qty, px, round_up=True)
    return cost, cost + ceil_div(cost * fee_bp, BP)


def _buy_qty(budget: int, px: int, fee_bp: int) -> int:
    """Plus grande quantité dont coût + frais (arrondis vers le haut) tient dans `budget` (µEUR)."""
    if budget <= 0:
        return 0
    qty = budget * BP * QTY_SCALE // (px * (BP + fee_bp))
    while qty > 0:
        _, total = _buy_total(qty, px, fee_bp)
        if total <= budget:
            break
        # Un pas de ceil(excès * QTY_SCALE / px) retire au moins `excès` µEUR du coût : une itération suffit.
        qty -= max(1, ceil_div((total - budget) * QTY_SCALE, px))
    return max(qty, 0)


def _evaluate_buy(
    intent: Intent,
    state: PortfolioState,
    market: MarketView,
    policy: Policy,
    counters: Counters,
    now_ts: int,
    instruments: Mapping[str, Instrument],
    fee_bp: int,
    slippage_bp: int,
    kill_switch: bool,
) -> Verdict:
    sym = intent.symbol
    r: set[str] = set()

    if kill_switch:
        r.add(KILL_SWITCH)
    if sym not in policy.symbols:
        r.add(NOT_WHITELISTED)
    instrument = instruments.get(sym)
    if instrument is None:
        r.add(UNKNOWN_INSTRUMENT)

    # Equity (arrondie vers le bas) : cash + positions aux marks.
    pos_floor = _positions_value(state, market.marks, round_up=False)
    equity: int | None = None
    if pos_floor is None:
        r.add(NO_MARK)
    else:
        equity = state.cash_ueur + pos_floor
        if equity <= 0:
            r.add(NO_EQUITY)

    # Gel / arrêt : drapeaux de l'état, et recalcul indépendant depuis l'equity valorisée aux marks.
    if state.frozen_until_ts > now_ts:
        r.add(FROZEN)
    if state.halted:
        r.add(HALTED)
    if equity is not None:
        code, _ = _freeze_halt(equity, state, counters, policy, now_ts)
        if code is not None:
            r.add(code)

    # Budget de frais mensuel : frais >= bp * equity de début de mois (début <= 0 : on refuse).
    start = counters.equity_month_start_ueur
    if start <= 0 or counters.fees_month_ueur * BP >= policy.monthly_fee_budget_bp * start:
        r.add(FEE_BUDGET)

    # Fréquence.
    if counters.trades_24h >= policy.max_trades_per_day:
        r.add(DAILY_TRADES)
    if counters.orders_last_minute >= policy.max_orders_per_minute:
        r.add(ORDER_RATE)
    last = counters.last_symbol_intent_ts
    if last is not None and now_ts - last < policy.min_interval_same_symbol_s:
        r.add(TOO_SOON)

    # Stop obligatoire et borné.
    stop = intent.stop_bp
    if stop is None:
        r.add(STOP_REQUIRED)
    elif not _is_int(stop) or not (policy.stop_bp_min <= stop <= policy.stop_bp_max):
        r.add(STOP_RANGE)

    # Marché : quote, cohérence de prix, spread, coût / gain.
    quote = market.quotes.get(sym)
    quote_ok = _quote_ok(quote)
    expected = intent.expected_move_bp
    if not _is_int(expected) or expected <= 0:
        r.add(EDGE_TOO_SMALL)
    if not quote_ok or quote is None:
        r.add(NO_QUOTE)
    else:
        bid, ask = quote.bid, quote.ask
        close = market.last_closes.get(sym)
        # |mid - close| / close > dev  <=>  |bid + ask - 2 close| * 10000 > dev * 2 * close
        if (
            not _is_int(close)
            or close <= 0
            or abs(bid + ask - 2 * close) * BP > policy.max_quote_deviation_bp * 2 * close
        ):
            r.add(PRICE_SANITY)
        spread = ask - bid
        median = market.median_spreads_ueur.get(sym)
        if not _is_int(median) or median < 0 or spread > policy.max_spread_multiple * median:
            r.add(SPREAD_ANOMALY)
        if _is_int(expected) and expected > 0:
            spread_bp = ceil_div(spread * 2 * BP, bid + ask)  # spread / mid, en bp, vers le haut
            cost_rt_bp = 2 * (fee_bp + slippage_bp) + spread_bp
            if cost_rt_bp * 100 > policy.max_cost_to_expected_move_pct * expected:
                r.add(EDGE_TOO_SMALL)

    # Taille.
    size = intent.size_bp
    size_ok = _is_int(size) and size > 0
    if not size_ok:
        r.add(BAD_SIZE)
    elif size > policy.max_order_bp:
        r.add(MAX_ORDER_SIZE)

    # Quantité et règles qui en dépendent (position, exposition, cash, taille minimale).
    qty = 0
    reserved = 0
    if (
        instrument is not None
        and quote is not None
        and quote_ok
        and equity is not None
        and equity > 0
        and size_ok
        and pos_floor is not None
    ):
        px = _exec_price(quote.ask, slippage_bp, instrument.tick_ueur)
        budget = equity * size // BP  # arrondi vers le bas
        qty = _buy_qty(budget, px, fee_bp)
        cost, total = _buy_total(qty, px, fee_bp)
        reserved = total

        pos_ceil = _positions_value(state, market.marks, round_up=True)
        held = state.positions.get(sym)
        held_ceil = 0
        if held is not None and held.qty > 0:
            held_ceil = notional_ueur(held.qty, market.marks[sym], round_up=True)
        assert pos_ceil is not None  # les marks existent : pos_floor n'est pas None
        if (held_ceil + cost) * BP > policy.max_position_bp * equity:
            r.add(MAX_POSITION)
        if (pos_ceil + cost) * BP > policy.max_exposure_bp * equity:
            r.add(MAX_EXPOSURE)
        if state.cash_ueur - total < 0:
            r.add(INSUFFICIENT_CASH)
        floor_value = notional_ueur(qty, px, round_up=False)
        if (
            qty <= 0
            or qty < instrument.lot_min_qty
            or floor_value < max(policy.min_order_ueur, instrument.cost_min_ueur)
        ):
            r.add(ORDER_TOO_SMALL)

    if r:
        return _reject(intent.intent_id, r, policy)
    return Verdict(
        intent_id=intent.intent_id,
        approved=True,
        reasons=(),
        qty=qty,
        reserved_ueur=reserved,
        policy_sha256=policy.sha256,
    )


def _evaluate_sell(
    intent: Intent,
    state: PortfolioState,
    market: MarketView,
    policy: Policy,
    counters: Counters,
    instruments: Mapping[str, Instrument],
) -> Verdict:
    sym = intent.symbol
    r: set[str] = set()

    if sym not in policy.symbols:
        r.add(NOT_WHITELISTED)
    if counters.orders_last_minute >= policy.max_orders_per_minute:
        r.add(ORDER_RATE)

    size = intent.size_bp
    held = state.positions.get(sym)
    held_qty = held.qty if held is not None else 0
    qty = 0
    if not _is_int(size) or size <= 0:
        r.add(BAD_SIZE)
    elif held_qty <= 0 or size > BP:
        r.add(NO_SHORT)  # rien à vendre, ou plus que la position
    else:
        qty = held_qty if size == BP else held_qty * size // BP  # vers le bas
        if qty == 0:
            r.add(ORDER_TOO_SMALL)  # la fraction demandée arrondit à zéro : jamais d'approbation à qty 0
    full_exit = qty > 0 and qty == held_qty

    # Prix pour valoriser la vente (bid, à défaut le mark) : sert à ORDER_TOO_SMALL et au montant attendu.
    quote = market.quotes.get(sym)
    price: int | None = None
    if _quote_ok(quote) and quote is not None:
        price = quote.bid
    else:
        mark = market.marks.get(sym)
        if _is_int(mark) and mark > 0:
            price = mark
    value = notional_ueur(qty, price, round_up=False) if price is not None else 0

    # Taille minimale : sauf mise à plat complète (une vente totale doit toujours pouvoir passer).
    if qty > 0 and not full_exit:
        instrument = instruments.get(sym)
        if instrument is None:
            r.add(UNKNOWN_INSTRUMENT)
        elif price is None:
            r.add(NO_QUOTE)
        elif qty < instrument.lot_min_qty or value < max(policy.min_order_ueur, instrument.cost_min_ueur):
            r.add(ORDER_TOO_SMALL)

    if r:
        return _reject(intent.intent_id, r, policy)
    return Verdict(
        intent_id=intent.intent_id,
        approved=True,
        reasons=(),
        qty=qty,
        reserved_ueur=value,
        policy_sha256=policy.sha256,
    )


def evaluate(
    intent: Intent,
    state: PortfolioState,
    market: MarketView,
    policy: Policy,
    counters: Counters,
    now_ts: int,
    instruments: dict[str, Instrument],
    fee_bp: int,
    slippage_bp: int,
    kill_switch: bool,
) -> Verdict:
    """Valide une intention. Pure : mêmes entrées, même verdict. Renvoie TOUS les codes violés, triés.

    Achat : quantité = floor(equity × size_bp / 10000 / prix d'exécution), frais compris dans le budget.
    Le prix d'exécution est ask × (1 + slippage), arrondi vers le haut puis au tick. Coût, frais et
    exposition sont arrondis vers le haut, l'equity vers le bas. Position et exposition sont mesurées
    sur l'equity avant l'ordre. Toute exception inattendue devient un rejet INTERNAL_ERROR.
    """
    try:
        if (
            not _is_int(fee_bp)
            or not _is_int(slippage_bp)
            or not _is_int(now_ts)
            or fee_bp < 0
            or slippage_bp < 0
        ):
            return _reject(intent.intent_id, {BAD_PARAMS}, policy)
        if intent.side == Side.BUY:
            return _evaluate_buy(
                intent, state, market, policy, counters, now_ts, instruments, fee_bp, slippage_bp, kill_switch
            )
        if intent.side == Side.SELL:
            return _evaluate_sell(intent, state, market, policy, counters, instruments)
        return _reject(intent.intent_id, {BAD_SIDE}, policy)
    except Exception:  # noqa: BLE001 - fail closed : un bug ne doit jamais produire une approbation
        return _reject(intent.intent_id, {INTERNAL_ERROR}, policy)
