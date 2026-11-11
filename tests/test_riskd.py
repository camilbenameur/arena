"""Tests de arene/risk/riskd.py : une règle = un test (juste sous / juste au-dessus du seuil),
puis tests de propriété hypothesis (plus de 100 000 intentions générées au total).

Les tests de propriété recalculent TOUT indépendamment avec des fractions exactes (module `fractions`),
sans réutiliser les fonctions de riskd : taille, position, exposition, cash après frais, liste blanche, stop...
"""

from __future__ import annotations

import dataclasses
import random
from fractions import Fraction
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from arene.risk import riskd
from arene.risk.policy import Policy, load_policy
from arene.risk.riskd import (
    ALL_CODES,
    BP,
    Counters,
    MarketView,
    evaluate,
    freeze_or_halt,
)
from arene.types import (
    MICRO,
    QTY_SCALE,
    Instrument,
    Intent,
    PortfolioState,
    Position,
    Quote,
    Side,
    Verdict,
)

POLICY = load_policy(Path(__file__).resolve().parent.parent / "config" / "policy.toml")
NOW = 1_700_000_000
EUR = MICRO

# Instruments du §1 de la spec (tick, ordre min, coût min), en unités entières.
INSTR: dict[str, Instrument] = {
    "BTC/EUR": Instrument("BTC/EUR", "XBTEUR", "BTCUSDT", 100_000, 6_000, 450_000),
    "ETH/EUR": Instrument("ETH/EUR", "ETHEUR", "ETHUSDT", 10_000, 200_000, 450_000),
    "SOL/EUR": Instrument("SOL/EUR", "SOLEUR", "SOLUSDT", 10_000, 5_000_000, 450_000),
    "XRP/EUR": Instrument("XRP/EUR", "XRPEUR", "XRPUSDT", 10, 400_000_000, 450_000),
    "LINK/EUR": Instrument("LINK/EUR", "LINKEUR", "LINKUSDT", 10, 35_000_000, 450_000),
    "LTC/EUR": Instrument("LTC/EUR", "LTCEUR", "LTCUSDT", 10_000, 8_000_000, 450_000),
}
# Prix de référence (µEUR par unité entière).
BASE_PRICE = {
    "BTC/EUR": 50_000 * EUR,
    "ETH/EUR": 2_000 * EUR,
    "SOL/EUR": 100 * EUR,
    "XRP/EUR": 2 * EUR,
    "LINK/EUR": 10 * EUR,
    "LTC/EUR": 80 * EUR,
}
FEE_BP, SLIP_BP = 50, 5
BTC = "BTC/EUR"


# --------------------------------------------------------------------------- aides de test


def quote(symbol: str = BTC, mid: int | None = None, spread: int | None = None) -> Quote:
    mid = BASE_PRICE[symbol] if mid is None else mid
    spread = 20 * EUR if spread is None else spread
    return Quote(symbol, NOW, mid - spread // 2, mid + spread // 2)


def market(**kw: object) -> MarketView:
    base = {
        "quotes": {s: quote(s, spread=BASE_PRICE[s] * 4 // 100_000) for s in INSTR},
        "last_closes": dict(BASE_PRICE),
        "median_spreads_ueur": {s: BASE_PRICE[s] * 4 // 100_000 for s in INSTR},
        "marks": dict(BASE_PRICE),
    }
    # BTC : bid 49 990, ask 50 010 (spread 20 EUR = 4 bp), médiane 20 EUR.
    base["quotes"][BTC] = quote(BTC)  # type: ignore[index]
    base["median_spreads_ueur"][BTC] = 20 * EUR  # type: ignore[index]
    base.update(kw)
    return MarketView(**base)  # type: ignore[arg-type]


def counters(**kw: int | None) -> Counters:
    base: dict[str, int | None] = {
        "trades_24h": 0,
        "orders_last_minute": 0,
        "last_symbol_intent_ts": None,
        "fees_month_ueur": 0,
        "equity_month_start_ueur": 1_000 * EUR,
        "equity_24h_ago_ueur": 1_000 * EUR,
        "equity_peak_ueur": 1_000 * EUR,
        "equity_now_ueur": 1_000 * EUR,
    }
    base.update(kw)
    return Counters(**base)  # type: ignore[arg-type]


def state(cash: int = 1_000 * EUR, positions: dict[str, int] | None = None, **kw: object) -> PortfolioState:
    """`positions` : symbole -> valeur en µEUR au mark de référence."""
    pos: dict[str, Position] = {}
    for sym, value in (positions or {}).items():
        qty = value * QTY_SCALE // BASE_PRICE[sym]
        pos[sym] = Position(sym, qty, value, NOW - 3600)
    return PortfolioState(portfolio="llm:test", cash_ueur=cash, positions=pos, **kw)  # type: ignore[arg-type]


def buy(
    symbol: str = BTC, size_bp: int = 1000, stop_bp: int | None = 500, exp: int | None = 500, **kw
) -> Intent:
    return Intent("i1", "llm:test", NOW, symbol, Side.BUY, size_bp, stop_bp, 24, exp, 60, **kw)


def sell(symbol: str = BTC, size_bp: int = BP) -> Intent:
    return Intent("s1", "llm:test", NOW, symbol, Side.SELL, size_bp)


def run(
    intent: Intent | None = None,
    st_: PortfolioState | None = None,
    mkt: MarketView | None = None,
    cnt: Counters | None = None,
    *,
    now: int = NOW,
    kill: bool = False,
    fee: int = FEE_BP,
    slip: int = SLIP_BP,
    policy: Policy = POLICY,
) -> Verdict:
    return evaluate(
        intent or buy(),
        st_ or state(),
        mkt or market(),
        policy,
        cnt or counters(),
        now,
        INSTR,
        fee,
        slip,
        kill,
    )


def only(v: Verdict, *codes: str) -> None:
    assert not v.approved
    assert v.reasons == tuple(sorted(codes)), v.reasons
    assert v.qty == 0 and v.reserved_ueur == 0


def ok(v: Verdict) -> None:
    assert v.approved, v.reasons
    assert v.reasons == ()
    assert v.qty > 0


# --------------------------------------------------------------------------- cas de référence


def test_achat_de_reference_approuve_et_chiffres_exacts() -> None:
    v = run()
    ok(v)
    assert v.policy_sha256 == POLICY.sha256 and v.intent_id == "i1"
    # prix d'exécution = ask 50 010 EUR x 1,0005 = 50 035,005 EUR -> tick 0,1 EUR : 50 035,1 EUR
    px = 50_035_100_000
    assert v.qty == 100 * EUR * BP * QTY_SCALE // (px * (BP + FEE_BP))
    cost = -((-v.qty * px) // QTY_SCALE)
    fee = -((-cost * FEE_BP) // BP)
    assert v.reserved_ueur == cost + fee <= 100 * EUR  # le budget de 10 % couvre frais compris


def test_codes_exportes_et_tries() -> None:
    assert list(ALL_CODES) == sorted(ALL_CODES)
    for code in (
        "NOT_WHITELISTED", "MAX_ORDER_SIZE", "MAX_POSITION", "MAX_EXPOSURE", "INSUFFICIENT_CASH",
        "DAILY_TRADES", "ORDER_RATE", "TOO_SOON", "STOP_REQUIRED", "STOP_RANGE", "EDGE_TOO_SMALL",
        "FROZEN", "HALTED", "FEE_BUDGET", "PRICE_SANITY", "SPREAD_ANOMALY", "ORDER_TOO_SMALL",
        "NO_SHORT", "KILL_SWITCH",
    ):  # fmt: skip
        assert getattr(riskd, code) == code and code in ALL_CODES


def test_tous_les_codes_violes_sont_renvoyes_tries() -> None:
    v = run(
        buy("DOGE/EUR", size_bp=3000, stop_bp=None, exp=None),
        state(frozen_until_ts=NOW + 1, halted=True),
        cnt=counters(trades_24h=2, orders_last_minute=POLICY.max_orders_per_minute, fees_month_ueur=10 * EUR, last_symbol_intent_ts=NOW),
        kill=True,
    )
    assert not v.approved
    assert list(v.reasons) == sorted(v.reasons)
    for code in (
        "NOT_WHITELISTED", "KILL_SWITCH", "FROZEN", "HALTED", "FEE_BUDGET", "DAILY_TRADES", "ORDER_RATE",
        "STOP_REQUIRED", "EDGE_TOO_SMALL", "MAX_ORDER_SIZE", "UNKNOWN_INSTRUMENT",
    ):  # fmt: skip
        assert code in v.reasons, code


# --------------------------------------------------------------------------- une règle par test


def test_not_whitelisted() -> None:
    v = run(buy("DOGE/EUR"))
    assert "NOT_WHITELISTED" in v.reasons and not v.approved
    # symbole connu de l'instrument mais retiré de la liste blanche
    pol = dataclasses.replace(POLICY, symbols=("ETH/EUR",))
    only(run(policy=pol), "NOT_WHITELISTED")
    ok(run(policy=dataclasses.replace(POLICY, symbols=("BTC/EUR",))))


@pytest.mark.parametrize(("size", "good"), [(2000, True), (2001, False)])
def test_max_order_size(size: int, good: bool) -> None:
    v = run(buy(size_bp=size))
    if good:
        ok(v)
        # même à 20 % : coût + frais <= 20 % de l'equity
        assert v.reserved_ueur <= 200 * EUR
    else:
        only(v, "MAX_ORDER_SIZE")


def test_max_position() -> None:
    # 30 % déjà en BTC (mark) + achat de 10 % : 3 995 bp <= 4 000 -> ok
    ok(run(st_=state(cash=700 * EUR, positions={BTC: 300 * EUR})))
    # 30,1 % + 10 % : ~4 005 bp > 4 000
    only(run(st_=state(cash=699 * EUR, positions={BTC: 301 * EUR})), "MAX_POSITION")
    # une position sur un AUTRE symbole ne compte pas dans le plafond du symbole
    ok(run(st_=state(cash=600 * EUR, positions={"ETH/EUR": 400 * EUR})))


def test_max_exposure_et_cash() -> None:
    # exposition 80 % + achat 20 % = 99,9 % <= 100 %, cash 200 EUR >= coût + frais : ok
    ok(run(buy(size_bp=2000), state(cash=200 * EUR, positions={"ETH/EUR": 400 * EUR, "SOL/EUR": 400 * EUR})))
    # 85 % déjà investis : 85 + 19,9 > 100 % et cash 150 < 200
    v = run(buy(size_bp=2000), state(cash=150 * EUR, positions={"ETH/EUR": 425 * EUR, "SOL/EUR": 425 * EUR}))
    assert not v.approved and {"MAX_EXPOSURE", "INSUFFICIENT_CASH"} <= set(v.reasons)


def test_cash_insuffisant_a_cause_des_frais_seulement() -> None:
    # equity 1000 EUR, achat de 20 % (budget 200 EUR frais compris). cash 199,5 EUR : le coût hors frais
    # (~199,0) tient, coût + frais (~200) non -> INSUFFICIENT_CASH seul, exposition encore <= 100 %.
    v = run(buy(size_bp=2000), state(cash=1_999 * EUR // 10, positions={"ETH/EUR": 8_005 * EUR // 10}))
    only(v, "INSUFFICIENT_CASH")
    # cash exactement égal au total : approuvé, jamais de cash négatif
    ok1 = run(buy(size_bp=2000), state(cash=200 * EUR, positions={"ETH/EUR": 800 * EUR}))
    ok(ok1)
    assert 200 * EUR - ok1.reserved_ueur >= 0


@pytest.mark.parametrize(("n", "good"), [(1, True), (2, False), (3, False)])
def test_daily_trades(n: int, good: bool) -> None:
    v = run(cnt=counters(trades_24h=n))
    ok(v) if good else only(v, "DAILY_TRADES")


@pytest.mark.parametrize(("n", "good"), [(POLICY.max_orders_per_minute - 1, True), (POLICY.max_orders_per_minute, False), (POLICY.max_orders_per_minute + 1, False)])
def test_order_rate(n: int, good: bool) -> None:
    v = run(cnt=counters(orders_last_minute=n))
    ok(v) if good else only(v, "ORDER_RATE")


@pytest.mark.parametrize(("age", "good"), [(14_400, True), (14_399, False), (0, False), (86_400, True)])
def test_too_soon(age: int, good: bool) -> None:
    v = run(cnt=counters(last_symbol_intent_ts=NOW - age))
    ok(v) if good else only(v, "TOO_SOON")


@pytest.mark.parametrize(
    ("stop", "codes"),
    [
        (None, ("STOP_REQUIRED",)),
        (99, ("STOP_RANGE",)),
        (100, ()),
        (2500, ()),
        (2501, ("STOP_RANGE",)),
        (0, ("STOP_RANGE",)),
        (-50, ("STOP_RANGE",)),
        (10**30, ("STOP_RANGE",)),
    ],
)
def test_stop(stop: int | None, codes: tuple[str, ...]) -> None:
    v = run(buy(stop_bp=stop))
    ok(v) if not codes else only(v, *codes)


@pytest.mark.parametrize(
    ("exp", "good"), [(346, True), (345, False), (None, False), (0, False), (-10, False)]
)
def test_edge_too_small(exp: int | None, good: bool) -> None:
    # coût aller-retour = 2 x (50 + 5) + spread 4 bp = 114 bp ; 114 x 100 <= 33 x 346 (11 418) mais pas 345 (11 385)
    v = run(buy(exp=exp))
    ok(v) if good else only(v, "EDGE_TOO_SMALL")


def test_edge_depend_des_frais_et_du_spread() -> None:
    only(run(fee=60, slip=5, intent=buy(exp=346)), "EDGE_TOO_SMALL")  # 2 x 65 + 4 = 134 bp
    wide = market()
    wide.quotes[BTC] = quote(BTC, spread=100 * EUR)  # 20 bp
    wide.median_spreads_ueur[BTC] = 100 * EUR
    only(run(buy(exp=346), mkt=wide), "EDGE_TOO_SMALL")
    ok(run(buy(exp=410), mkt=wide))  # 130 x 100 = 13 000 <= 33 x 410 (13 530)


@pytest.mark.parametrize(("until", "good"), [(NOW, True), (NOW - 1, True), (NOW + 1, False)])
def test_frozen(until: int, good: bool) -> None:
    v = run(st_=state(frozen_until_ts=until))
    ok(v) if good else only(v, "FROZEN")


def test_halted() -> None:
    only(run(st_=state(halted=True)), "HALTED")


@pytest.mark.parametrize(("fees", "good"), [(9_999_999, True), (10_000_000, False), (10_000_001, False)])
def test_fee_budget(fees: int, good: bool) -> None:
    v = run(cnt=counters(fees_month_ueur=fees))
    ok(v) if good else only(v, "FEE_BUDGET")


def test_fee_budget_sans_equity_de_debut_de_mois_refuse() -> None:
    only(run(cnt=counters(equity_month_start_ueur=0)), "FEE_BUDGET")


def test_kill_switch_refuse_les_achats() -> None:
    only(run(kill=True), "KILL_SWITCH")


@pytest.mark.parametrize(
    ("close_eur", "good"),
    [(48_600, True), (48_500, False), (51_000, True), (51_600, False), (50_000, True), (0, False)],
)
def test_price_sanity(close_eur: int, good: bool) -> None:
    # mid = 50 000 EUR ; seuil 3 % de la dernière clôture
    m = market(last_closes={BTC: close_eur * EUR})
    v = run(mkt=m)
    ok(v) if good else only(v, "PRICE_SANITY")


def test_price_sanity_cloture_absente() -> None:
    only(run(mkt=market(last_closes={})), "PRICE_SANITY")


@pytest.mark.parametrize(
    ("median", "good"), [(6_666_667, True), (6_666_666, False), (20 * EUR, True), (0, False)]
)
def test_spread_anomaly(median: int, good: bool) -> None:
    # spread 20 EUR ; limite = 3 x médiane
    m = market(median_spreads_ueur={BTC: median})
    v = run(mkt=m)
    ok(v) if good else only(v, "SPREAD_ANOMALY")


def test_spread_anomaly_mediane_absente() -> None:
    only(run(mkt=market(median_spreads_ueur={})), "SPREAD_ANOMALY")


@pytest.mark.parametrize(("size", "good"), [(51, True), (50, False), (1, False)])
def test_order_too_small_achat(size: int, good: bool) -> None:
    # equity 1000 EUR : 50 bp = 5 EUR de budget, frais compris -> coût hors frais < 5 EUR : refusé
    v = run(buy(size_bp=size))
    ok(v) if good else only(v, "ORDER_TOO_SMALL")


def test_order_too_small_quantite_minimale() -> None:
    # XRP : ordre min 4 XRP. On abaisse le plancher en EUR de la politique pour isoler la règle de quantité.
    pol = dataclasses.replace(POLICY, min_order_ueur=1)
    flat = counters(
        equity_month_start_ueur=400 * EUR,
        equity_24h_ago_ueur=400 * EUR,
        equity_peak_ueur=400 * EUR,
        equity_now_ueur=400 * EUR,
    )
    # budget 20 bp de 400 EUR = 0,8 EUR, soit ~0,4 XRP < 4 XRP (le coût minimal 0,45 EUR est lui respecté)
    v = run(buy("XRP/EUR", size_bp=20), state(cash=400 * EUR), cnt=flat, policy=pol)
    only(v, "ORDER_TOO_SMALL")


def test_equity_nulle_ou_negative() -> None:
    v = run(st_=state(cash=0))
    assert not v.approved and "NO_EQUITY" in v.reasons
    v = run(st_=state(cash=-5 * EUR))
    assert not v.approved and "NO_EQUITY" in v.reasons


def test_quote_absent_ou_incoherent() -> None:
    only(run(mkt=market(quotes={})), "NO_QUOTE")
    only(run(mkt=market(quotes={BTC: Quote(BTC, NOW, 100, 99)})), "NO_QUOTE")  # ask < bid
    only(run(mkt=market(quotes={BTC: Quote(BTC, NOW, 0, 100)})), "NO_QUOTE")


def test_mark_manquant_pour_une_position_detenue() -> None:
    m = market()
    del m.marks["ETH/EUR"]
    v = run(st_=state(cash=500 * EUR, positions={"ETH/EUR": 500 * EUR}), mkt=m)
    assert not v.approved and "NO_MARK" in v.reasons


def test_parametres_absurdes() -> None:
    only(run(fee=-1), "BAD_PARAMS")
    only(run(slip=-1), "BAD_PARAMS")


def test_taille_absurde_achat() -> None:
    only(run(buy(size_bp=0)), "BAD_SIZE")
    only(run(buy(size_bp=-5)), "BAD_SIZE")
    v = run(buy(size_bp=10**40))
    assert not v.approved and "MAX_ORDER_SIZE" in v.reasons


def test_cote_inconnu() -> None:
    i = dataclasses.replace(buy(), side="short")  # type: ignore[arg-type]
    only(run(i), "BAD_SIDE")


# --------------------------------------------------------------------------- ventes


def test_vente_totale_et_partielle() -> None:
    s = state(cash=500 * EUR, positions={BTC: 500 * EUR})
    pos_qty = s.positions[BTC].qty
    v = run(sell(size_bp=BP), s)
    ok(v)
    assert v.qty == pos_qty
    v = run(sell(size_bp=5000), s)
    ok(v)
    assert v.qty == pos_qty * 5000 // BP  # arrondi vers le bas
    # montant attendu : au bid (49 990 EUR), arrondi vers le bas
    assert v.reserved_ueur == v.qty * 49_990 * EUR // QTY_SCALE


def test_no_short() -> None:
    only(run(sell()), "NO_SHORT")  # aucune position
    s = state(cash=500 * EUR, positions={BTC: 500 * EUR})
    only(run(sell(size_bp=10_001), s), "NO_SHORT")  # plus que la position
    only(run(sell("ETH/EUR"), s), "NO_SHORT")  # position sur un autre symbole


@pytest.mark.parametrize("size", [10_000, 9_999, 5_000, 1])
def test_order_too_small_vente(size: int) -> None:
    # position de 4 EUR (< plancher de 5 EUR) : seule la vente totale est exemptée.
    # size_bp = 1 sur une si petite position arrondit à une quantité nulle : refus, jamais d'approbation à 0.
    s = state(cash=996 * EUR, positions={BTC: 4 * EUR})
    v = run(sell(size_bp=size), s)
    if size == BP:
        ok(v)
    else:
        only(v, "ORDER_TOO_SMALL")


def test_vente_partielle_juste_sous_et_au_dessus_du_plancher() -> None:
    # position de 10 EUR : vendre 50 % = 5 EUR (au bid 49 990 contre mark 50 000 : un peu moins) -> trop petit
    s = state(cash=990 * EUR, positions={BTC: 10 * EUR})
    only(run(sell(size_bp=5000), s), "ORDER_TOO_SMALL")
    ok(run(sell(size_bp=5100), s))  # ~5,1 EUR


def test_vente_not_whitelisted_et_order_rate() -> None:
    s = state(cash=500 * EUR, positions={BTC: 500 * EUR})
    only(run(sell(), s, policy=dataclasses.replace(POLICY, symbols=("ETH/EUR",))), "NOT_WHITELISTED")
    only(run(sell(), s, cnt=counters(orders_last_minute=POLICY.max_orders_per_minute)), "ORDER_RATE")
    ok(run(sell(), s, cnt=counters(orders_last_minute=POLICY.max_orders_per_minute - 1)))


def test_vente_permise_si_gele_arrete_kill_switch_et_budgets_epuises() -> None:
    s = state(
        cash=500 * EUR,
        positions={BTC: 500 * EUR},
        frozen_until_ts=NOW + 10**6,
        halted=True,
    )
    c = counters(trades_24h=99, fees_month_ueur=10**12, last_symbol_intent_ts=NOW)
    ok(run(sell(), s, cnt=c, kill=True))
    ok(run(sell(size_bp=1000), s, cnt=c, kill=True))


def test_vente_ignore_edge_taille_prix_et_spread() -> None:
    s = state(cash=500 * EUR, positions={BTC: 500 * EUR})
    m = market(last_closes={BTC: 1}, median_spreads_ueur={BTC: 0})
    i = dataclasses.replace(sell(), stop_bp=None, expected_move_bp=None)
    ok(run(i, s, m))


def test_vente_totale_sans_quote_utilise_le_mark_ou_passe() -> None:
    s = state(cash=500 * EUR, positions={BTC: 500 * EUR})
    ok(run(sell(), s, market(quotes={})))  # mark disponible
    v = run(sell(), s, market(quotes={}, marks={}))
    ok(v)
    assert v.reserved_ueur == 0
    only(run(sell(size_bp=5000), s, market(quotes={}, marks={})), "NO_QUOTE")


# --------------------------------------------------------------------------- freeze_or_halt


@pytest.mark.parametrize(
    ("equity_now", "expected"),
    [
        (951 * EUR, None),  # -4,9 %
        (950 * EUR, "FROZEN"),  # -5 % pile
        (900 * EUR, "FROZEN"),
        (801 * EUR, "FROZEN"),  # drawdown 19,9 %
        (800 * EUR, "HALTED"),  # -20 % pile
        (500 * EUR, "HALTED"),
    ],
)
def test_freeze_or_halt_seuils(equity_now: int, expected: str | None) -> None:
    c = counters(equity_now_ueur=equity_now)
    code, until = freeze_or_halt(state(), c, POLICY, NOW)
    assert code == expected
    assert until == (NOW + POLICY.freeze_duration_s if expected == "FROZEN" else 0)


def test_freeze_or_halt_rien_et_arret_deja_pose() -> None:
    assert freeze_or_halt(state(), counters(), POLICY, NOW) == (None, 0)
    assert freeze_or_halt(state(halted=True), counters(), POLICY, NOW) == ("HALTED", 0)
    # equity de référence nulle : on ne peut pas mesurer, pas de gel
    assert freeze_or_halt(state(), counters(equity_24h_ago_ueur=0, equity_peak_ueur=0), POLICY, NOW) == (
        None,
        0,
    )


def test_gel_recalcule_dans_evaluate_meme_si_le_drapeau_n_est_pas_pose() -> None:
    # equity réelle (cash) 940 EUR vs 1000 EUR il y a 24 h : -6 % -> FROZEN même si state.frozen_until_ts == 0
    only(run(st_=state(cash=940 * EUR), cnt=counters(equity_peak_ueur=940 * EUR)), "FROZEN")
    # drawdown 25 % depuis le plus haut -> HALTED (et pas de gel 24 h : equity_24h_ago == equity)
    only(
        run(
            st_=state(cash=750 * EUR),
            cnt=counters(equity_peak_ueur=1_000 * EUR, equity_24h_ago_ueur=750 * EUR),
        ),
        "HALTED",
    )


# --------------------------------------------------------------------------- pureté, déterminisme


def test_pure_aucune_mutation_des_entrees() -> None:
    s = state(cash=500 * EUR, positions={BTC: 500 * EUR})
    m = market()
    snap_state = dataclasses.replace(s, positions={k: dataclasses.replace(v) for k, v in s.positions.items()})
    snap_market = (dict(m.quotes), dict(m.marks), dict(m.last_closes), dict(m.median_spreads_ueur))
    run(buy(), s, m)
    run(sell(), s, m)
    assert s == snap_state
    assert (dict(m.quotes), dict(m.marks), dict(m.last_closes), dict(m.median_spreads_ueur)) == snap_market


def test_deterministe() -> None:
    results = {run(buy(size_bp=s), cnt=counters(trades_24h=s % 3)) for s in (10, 700, 2500) for _ in range(5)}
    assert len(results) == 3


def test_pas_de_float_dans_le_verdict() -> None:
    v = run()
    assert type(v.qty) is int and type(v.reserved_ueur) is int


# =========================================================================== propriétés (hypothesis)

TALLY = {"examples": 0, "approved_buy": 0, "approved_sell": 0, "rejected": 0}

PROP = {
    "deadline": None,
    "database": None,
    "derandomize": True,
    "suppress_health_check": list(HealthCheck),
}


def exact_equity(s: PortfolioState, marks: dict[str, int]) -> Fraction:
    eq = Fraction(s.cash_ueur)
    for sym, p in s.positions.items():
        if p.qty > 0:
            eq += Fraction(p.qty * marks[sym], QTY_SCALE)
    return eq


def check_invariants(
    intent: Intent,
    s: PortfolioState,
    m: MarketView,
    pol: Policy,
    c: Counters,
    now: int,
    instruments: dict[str, Instrument],
    fee: int,
    slip: int,
    kill: bool,
    v: Verdict,
) -> None:
    """Recalcul indépendant en arithmétique exacte : un verdict approuvé ne viole AUCUN plafond."""
    TALLY["examples"] += 1
    assert isinstance(v, Verdict)
    assert v.intent_id == intent.intent_id and v.policy_sha256 == pol.sha256
    assert type(v.qty) is int and type(v.reserved_ueur) is int
    assert list(v.reasons) == sorted(set(v.reasons))
    assert set(v.reasons) <= set(ALL_CODES)
    assert "INTERNAL_ERROR" not in v.reasons, "exception interne interceptée : bug de riskd"
    if not v.approved:
        TALLY["rejected"] += 1
        assert v.reasons and v.qty == 0 and v.reserved_ueur == 0
        return
    assert v.reasons == () and v.qty > 0 and v.reserved_ueur >= 0
    assert intent.symbol in pol.symbols  # liste blanche (achats et ventes)
    assert c.orders_last_minute < pol.max_orders_per_minute

    if intent.side == Side.SELL:
        TALLY["approved_sell"] += 1
        held = s.positions[intent.symbol].qty
        assert 0 < v.qty <= held, "vente à découvert"
        assert isinstance(intent.size_bp, int) and 0 < intent.size_bp <= BP
        assert v.qty <= held * intent.size_bp // BP or v.qty == held
        if v.qty != held:
            inst = instruments[intent.symbol]
            assert v.qty >= inst.lot_min_qty
            px = m.quotes[intent.symbol].bid if intent.symbol in m.quotes else m.marks[intent.symbol]
            assert Fraction(v.qty * px, QTY_SCALE) >= max(pol.min_order_ueur, inst.cost_min_ueur)
        return

    # --- achat ---
    TALLY["approved_buy"] += 1
    assert intent.side == Side.BUY
    sym = intent.symbol
    assert not kill
    assert s.frozen_until_ts <= now and not s.halted
    assert c.trades_24h < pol.max_trades_per_day
    assert c.last_symbol_intent_ts is None or now - c.last_symbol_intent_ts >= pol.min_interval_same_symbol_s
    assert c.equity_month_start_ueur > 0
    assert c.fees_month_ueur * BP < pol.monthly_fee_budget_bp * c.equity_month_start_ueur
    assert intent.stop_bp is not None and pol.stop_bp_min <= intent.stop_bp <= pol.stop_bp_max
    assert intent.expected_move_bp is not None and intent.expected_move_bp > 0
    assert intent.size_bp is not None and 0 < intent.size_bp <= pol.max_order_bp

    q = m.quotes[sym]
    inst = instruments[sym]
    assert 0 < q.bid <= q.ask
    equity = exact_equity(s, m.marks)
    assert equity > 0

    # coût exact au pire prix d'exécution (ask + glissement), plus frais
    px = Fraction(q.ask * (BP + slip), BP)
    notional = Fraction(v.qty) * px / QTY_SCALE
    total = notional * (BP + fee) / BP
    assert v.reserved_ueur >= total  # le montant réservé est arrondi vers le haut
    assert total * BP <= pol.max_order_bp * equity, "MAX_ORDER_SIZE violé"
    assert s.cash_ueur - total >= 0, "cash négatif après frais"
    held_value = Fraction(0)
    all_value = Fraction(0)
    for psym, p in s.positions.items():
        if p.qty > 0:
            val = Fraction(p.qty * m.marks[psym], QTY_SCALE)
            all_value += val
            if psym == sym:
                held_value = val
    assert (held_value + notional) * BP <= pol.max_position_bp * equity, "MAX_POSITION violé"
    assert (all_value + notional) * BP <= pol.max_exposure_bp * equity, "MAX_EXPOSURE violé"
    # taille minimale
    assert v.qty >= inst.lot_min_qty
    assert notional >= max(pol.min_order_ueur, inst.cost_min_ueur)
    # coût aller-retour <= 33 % du mouvement attendu
    spread_bp = Fraction((q.ask - q.bid) * 2 * BP, q.ask + q.bid)
    assert (2 * (fee + slip) + spread_bp) * 100 <= pol.max_cost_to_expected_move_pct * intent.expected_move_bp
    # prix et spread
    close = m.last_closes[sym]
    assert close > 0 and abs(Fraction(q.bid + q.ask, 2) - close) * BP <= pol.max_quote_deviation_bp * close
    assert (q.ask - q.bid) <= pol.max_spread_multiple * m.median_spreads_ueur[sym]
    # gel et arrêt recalculés
    if c.equity_24h_ago_ueur > 0:
        assert (c.equity_24h_ago_ueur - equity) * BP < pol.daily_loss_freeze_bp * c.equity_24h_ago_ueur
    if c.equity_peak_ueur > 0:
        assert (c.equity_peak_ueur - equity) * BP < pol.drawdown_halt_bp * c.equity_peak_ueur


# --- générateurs ---
# hypothesis fournit une graine entière par exemple ; les scénarios sont tirés d'un `random.Random(graine)`
# via un mini-moteur de stratégies (`g`). Un tirage hypothesis par variable coûtait ~10 ms par exemple
# (100 000 exemples hors budget) ; ici ~0,1 ms. Un échec est rejoué à l'identique avec sa graine.


class Draw:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def __call__(self, strat):
        return strat(self.rng)


class g:
    DrawFn = Draw

    @staticmethod
    def integers(a: int, b: int):
        return lambda rng: rng.randint(a, b)

    @staticmethod
    def sampled_from(xs):
        xs = list(xs)
        return lambda rng: rng.choice(xs)

    @staticmethod
    def booleans():
        return lambda rng: rng.random() < 0.5

    @staticmethod
    def none():
        return lambda rng: None

    @staticmethod
    def one_of(*strats):
        return lambda rng: rng.choice(strats)(rng)

    @staticmethod
    def lists(strat, min_size: int = 0, max_size: int = 5, unique: bool = False):
        def make(rng: random.Random) -> list:
            n = rng.randint(min_size, max_size)
            out: list = []
            for _ in range(n * 3):
                if len(out) >= n:
                    break
                x = strat(rng)
                if not unique or x not in out:
                    out.append(x)
            return out

        return make

    @staticmethod
    def composite(f):
        def factory(*a, **k):
            return lambda rng: f(_bind(rng), *a, **k)

        return factory


def _bind(rng: random.Random) -> Draw:
    d = Draw(0)
    d.rng = rng
    return d


SEED = st.integers(0, 2**62)


def case_of(strategy, seed: int):
    return strategy(random.Random(seed))


SYMS = list(INSTR)


@g.composite
def realistic_case(draw: Draw):
    """Cas proches du réel (montants et prix plausibles), avec des défauts injectés par endroits."""

    def flaw(pct: int) -> bool:
        return draw(g.integers(0, 99)) < pct

    mark_of = {s: BASE_PRICE[s] * draw(g.integers(50, 200)) // 100 for s in SYMS}
    positions: dict[str, Position] = {}
    for sym in SYMS:
        if draw(g.integers(0, 99)) < 35:
            value = draw(g.integers(0, 700 * EUR))
            positions[sym] = Position(sym, value * QTY_SCALE // mark_of[sym], value, NOW - 1000)
    marks = dict(mark_of)
    if flaw(3):
        marks.pop(draw(g.sampled_from(SYMS)), None)
    cash = draw(g.integers(0, 1_500 * EUR)) if not flaw(3) else draw(g.integers(-10 * EUR, 0))
    s = PortfolioState("llm:prop", cash, positions, frozen_until_ts=NOW + 5 if flaw(5) else 0, halted=flaw(3))

    symbol = draw(g.sampled_from(SYMS)) if not flaw(4) else draw(g.sampled_from(["DOGE/EUR", "", "btc/eur"]))
    sbp = draw(g.integers(1, 30)) if not flaw(8) else draw(g.integers(31, 400))
    quotes = {}
    for sym in SYMS:
        half = max(1, mark_of[sym] * sbp // 20_000)
        quotes[sym] = Quote(sym, NOW, mark_of[sym] - half, mark_of[sym] + half)
    if flaw(2):
        quotes.pop(draw(g.sampled_from(SYMS)), None)
    last_closes = {
        sym: mark_of[sym]
        * (draw(g.integers(9_600, 10_400)) if not flaw(6) else draw(g.integers(8_000, 12_000)))
        // BP
        for sym in SYMS
    }
    spreads = {
        sym: max(1, (quotes[sym].ask - quotes[sym].bid) * draw(g.integers(40, 300)) // 100)
        for sym in SYMS
        if sym in quotes
    }
    m = MarketView(quotes, last_closes, spreads, marks)
    equity_guess = max(1, cash) + 500 * EUR
    c = Counters(
        trades_24h=draw(g.integers(0, 3)) if flaw(15) else 0,
        orders_last_minute=draw(g.integers(0, POLICY.max_orders_per_minute + 2)) if flaw(10) else 0,
        last_symbol_intent_ts=None if not flaw(20) else NOW - draw(g.integers(0, 30_000)),
        fees_month_ueur=draw(g.integers(0, 15 * EUR)),
        equity_month_start_ueur=equity_guess if not flaw(2) else 0,
        equity_24h_ago_ueur=equity_guess * draw(g.integers(90, 110)) // 100,
        equity_peak_ueur=equity_guess * draw(g.integers(95, 140)) // 100,
        equity_now_ueur=equity_guess,
    )
    is_buy = draw(g.integers(0, 99)) < 65
    if is_buy:
        intent = Intent(
            "p",
            "llm:prop",
            NOW,
            symbol,
            Side.BUY,
            draw(g.integers(1, 2_300)) if not flaw(10) else draw(g.integers(-5, 12_000)),
            draw(g.integers(100, 2_500)) if not flaw(10) else draw(g.one_of(g.none(), g.integers(-5, 4_000))),
            24,
            draw(g.integers(150, 4_000)) if not flaw(10) else draw(g.one_of(g.none(), g.integers(-5, 600))),
            50,
        )
    else:
        # la vente vise de préférence un symbole réellement détenu
        held = [p for p in positions if positions[p].qty > 0]
        sym = draw(g.sampled_from(held)) if held and not flaw(10) else symbol
        intent = Intent(
            "p",
            "llm:prop",
            NOW,
            sym,
            Side.SELL,
            draw(g.sampled_from([BP, BP, 5_000, 1_000, 1, 9_999, 10_001, 0, -1])),
        )
    fee = 50 if not flaw(10) else draw(g.integers(0, 300))
    slip = 5 if not flaw(10) else draw(g.integers(0, 100))
    return intent, s, m, c, fee, slip, flaw(3)


@settings(max_examples=45_000, **PROP)
@given(SEED)
def test_propriete_realiste_aucun_verdict_approuve_ne_viole_un_plafond(seed: int) -> None:
    case = case_of(realistic_case(), seed)
    intent, s, m, c, fee, slip, kill = case
    v = evaluate(intent, s, m, POLICY, c, NOW, INSTR, fee, slip, kill)
    check_invariants(intent, s, m, POLICY, c, NOW, INSTR, fee, slip, kill, v)
    # déterminisme : même entrées, même verdict
    if seed % 10 == 0:
        assert evaluate(intent, s, m, POLICY, c, NOW, INSTR, fee, slip, kill) == v


wild_int = g.one_of(
    g.integers(-3, 3),
    g.integers(-(10**13), 10**13),
    g.integers(-(10**45), 10**45),
    g.sampled_from([0, 1, -1, 2**31, 2**63, -(2**63), 10**18]),
)
wild_pos = g.one_of(g.integers(0, 3), g.integers(0, 10**12), g.integers(0, 10**40))
opt_wild = g.one_of(g.none(), wild_int)


@g.composite
def wild_case(draw: Draw):
    """Entrées extrêmes : zéros, négatifs, énormes, symboles inconnus, equity nulle, quotes absurdes."""
    sym_pool = [*SYMS, "DOGE/EUR", "", "x" * 50]
    syms = draw(g.lists(g.sampled_from(sym_pool), min_size=0, max_size=4, unique=True))
    positions = {
        sy: Position(sy, draw(wild_int), draw(wild_pos), draw(wild_int), draw(opt_wild)) for sy in syms
    }
    marks = {sy: draw(wild_int) for sy in draw(g.lists(g.sampled_from(sym_pool), max_size=5, unique=True))}
    quotes = {
        sy: Quote(sy, draw(wild_int), draw(wild_int), draw(wild_int))
        for sy in draw(g.lists(g.sampled_from(sym_pool), max_size=5, unique=True))
    }
    s = PortfolioState(
        "llm:wild",
        draw(wild_int),
        positions,
        draw(wild_pos),
        draw(wild_int),
        draw(wild_int),
        draw(g.booleans()),
    )
    m = MarketView(
        quotes,
        {sy: draw(wild_int) for sy in sym_pool if draw(g.booleans())},
        {sy: draw(wild_int) for sy in sym_pool if draw(g.booleans())},
        marks,
    )
    c = Counters(
        draw(wild_int), draw(wild_int), draw(opt_wild), draw(wild_int), draw(wild_int), draw(wild_int),
        draw(wild_int), draw(wild_int),
    )  # fmt: skip
    intent = Intent(
        "w", "llm:wild", draw(wild_int), draw(g.sampled_from(sym_pool)),
        draw(g.sampled_from([Side.BUY, Side.SELL])), draw(wild_int), draw(opt_wild), draw(opt_wild),
        draw(opt_wild), draw(opt_wild),
    )  # fmt: skip
    insts = {
        sy: Instrument(sy, "P", "B", draw(wild_int), draw(wild_int), draw(wild_int))
        for sy in draw(g.lists(g.sampled_from(sym_pool), max_size=6, unique=True))
    }
    return intent, s, m, c, draw(wild_int), draw(wild_int), draw(g.booleans()), draw(wild_int), insts


@settings(max_examples=30_000, **PROP)
@given(SEED)
def test_propriete_entrees_extremes_jamais_d_exception_ni_d_approbation_absurde(seed: int) -> None:
    case = case_of(wild_case(), seed)
    intent, s, m, c, fee, slip, kill, now, insts = case
    v = evaluate(intent, s, m, POLICY, c, now, insts, fee, slip, kill)  # ne doit JAMAIS lever
    check_invariants_wild(intent, s, m, c, now, insts, fee, slip, kill, v)


def check_invariants_wild(intent, s, m, c, now, insts, fee, slip, kill, v) -> None:
    """Pour les entrées extrêmes : mêmes invariants si approuvé ; sinon forme du rejet."""
    if v.approved and intent.side == Side.BUY:
        # un achat approuvé exige des marks et quotes sains pour TOUTES les positions détenues
        assert not kill and fee >= 0 and slip >= 0
        for p in s.positions.values():
            if p.qty > 0:
                assert m.marks[p.symbol] > 0
    check_invariants(intent, s, m, POLICY, c, now, insts, fee, slip, kill, v)


@g.composite
def policies(draw: Draw) -> Policy:
    """Politiques cohérentes aléatoires (plus strictes ou plus lâches que la vraie)."""
    a, b, d = sorted(draw(g.lists(g.integers(1, 10_000), min_size=3, max_size=3)))
    smin = draw(g.integers(1, 5_000))
    return Policy(
        symbols=tuple(
            draw(g.lists(g.sampled_from(SYMS + ["DOGE/EUR"]), min_size=1, max_size=7, unique=True))
        ),
        max_order_bp=a,
        max_position_bp=b,
        max_exposure_bp=d,
        max_trades_per_day=draw(g.integers(1, 5)),
        max_orders_per_minute=draw(g.integers(1, 8)),
        min_interval_same_symbol_s=draw(g.integers(1, 100_000)),
        stop_bp_min=smin,
        stop_bp_max=draw(g.integers(smin + 1, 9_999)),
        max_cost_to_expected_move_pct=draw(g.integers(1, 100)),
        max_holding_s=604_800,
        daily_loss_freeze_bp=draw(g.integers(1, 3_000)),
        freeze_duration_s=86_400,
        drawdown_halt_bp=draw(g.integers(1, 6_000)),
        monthly_fee_budget_bp=draw(g.integers(1, 500)),
        max_quote_deviation_bp=draw(g.integers(1, 2_000)),
        max_spread_multiple=draw(g.integers(1, 10)),
        min_order_ueur=draw(g.integers(1, 20 * EUR)),
        sha256="ab" * 32,
    )


@settings(max_examples=25_000, **PROP)
@given(SEED)
def test_propriete_politiques_aleatoires(seed: int) -> None:
    case = case_of(realistic_case(), seed)
    pol = case_of(policies(), seed + 1)
    intent, s, m, c, fee, slip, kill = case
    # tailles adaptées à la politique tirée, pour exercer aussi les approbations
    if intent.side == Side.BUY and intent.size_bp is not None and intent.size_bp > 0:
        intent = dataclasses.replace(intent, size_bp=max(1, intent.size_bp % (pol.max_order_bp + 300)))
    v = evaluate(intent, s, m, pol, c, NOW, INSTR, fee, slip, kill)
    check_invariants(intent, s, m, pol, c, NOW, INSTR, fee, slip, kill, v)


@settings(max_examples=5_000, **PROP)
@given(SEED)
def test_propriete_ventes_toujours_permises_si_valides(seed: int) -> None:
    case = case_of(realistic_case(), seed)
    """Une vente valide (liste blanche, position suffisante, cadence, taille) passe même gel/arrêt/kill."""
    intent, s, m, c, fee, slip, _ = case
    if intent.side != Side.SELL:
        return
    held = s.positions.get(intent.symbol)
    if held is None or held.qty <= 0 or intent.symbol not in POLICY.symbols or c.orders_last_minute >= POLICY.max_orders_per_minute:
        return
    if intent.size_bp != BP or intent.symbol not in m.quotes:
        return
    s_bad = dataclasses.replace(s, halted=True, frozen_until_ts=NOW + 10**9)
    v = evaluate(intent, s_bad, m, POLICY, c, NOW, INSTR, fee, slip, True)
    assert v.approved and v.qty == held.qty  # mise à plat complète toujours possible


def test_zz_bilan_des_exemples_generes() -> None:
    """Placé en dernier : vérifie que les propriétés ont bien exercé des approbations (pas seulement des rejets)."""
    if TALLY["examples"] == 0:
        pytest.skip("tests de propriété non exécutés dans cette session")
    assert TALLY["examples"] >= 100_000, TALLY
    assert TALLY["approved_buy"] > 1_000, TALLY
    assert TALLY["approved_sell"] > 1_000, TALLY
    assert TALLY["rejected"] > 10_000, TALLY
