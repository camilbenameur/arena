"""Tests des témoins (panier, 60/40, E0065 adapté, aléatoire) et des trajectoires aléatoires."""

from __future__ import annotations

import time
import warnings
from datetime import UTC, datetime
from pathlib import Path

from arene.config import E0065Params
from arene.data.binance import DayBar
from arene.ledger import _apply_fill, equity_ueur
from arene.risk.policy import load_policy
from arene.sim.fills import market_fill
from arene.temoins import TemoinContext, aleatoire, e0065, panier, reference_qty, soixante_quarante
from arene.temoins.trajectoires import CycleData, simulate_random_trajectories, simulate_trajectory
from arene.types import MICRO, QTY_SCALE, Bar, Instrument, PortfolioState, Quote, Side

SYMBOLS = ("BTC/EUR", "ETH/EUR", "SOL/EUR", "XRP/EUR", "LINK/EUR", "LTC/EUR")
PRICES = {  # prix de départ en EUR
    "BTC/EUR": 50_000, "ETH/EUR": 2_500, "SOL/EUR": 150, "XRP/EUR": 2, "LINK/EUR": 15, "LTC/EUR": 80,
}  # fmt: skip
INSTRUMENTS = {
    s: Instrument(s, s.replace("/", ""), s.split("/")[0] + "USDT", 10_000, 10_000, 450_000) for s in SYMBOLS
}
FEE, SLIP = 50, 5
POLICY = load_policy(Path(__file__).resolve().parent.parent / "config" / "policy.toml")
H4 = 14_400
DAY = 86_400


def ts_of(y: int, m: int, d: int, h: int = 0) -> int:
    return int(datetime(y, m, d, h, tzinfo=UTC).timestamp())


def quote_at(sym: str, mark: int) -> Quote:
    half = mark // 10_000  # spread de 2 bp
    return Quote(sym, 0, mark - half, mark + half)


def mk_marks(factor: float = 1.0) -> dict[str, int]:
    return {s: int(p * MICRO * factor) for s, p in PRICES.items()}


def execute(intents, state, marks):
    """Exécute des intentions de référence comme le ferait le cycle : reference_qty puis market_fill."""
    for it in intents:
        q = quote_at(it.symbol, marks[it.symbol])
        qty = reference_qty(it, state, marks, q, INSTRUMENTS[it.symbol], FEE, SLIP)
        if qty <= 0:
            continue
        price, fee = market_fill(it.side, qty, q, INSTRUMENTS[it.symbol], FEE, SLIP)
        _apply_fill(
            state,
            {"symbol": it.symbol, "side": it.side.value, "qty": qty, "price_ueur": price, "fee_ueur": fee, "ts": it.cycle},
        )
        assert state.cash_ueur >= 0


def weight_bp(state, marks, sym) -> int:
    pos = state.positions.get(sym)
    if pos is None:
        return 0
    from arene.types import notional_ueur

    return notional_ueur(pos.qty, marks[sym], round_up=False) * 10_000 // equity_ueur(state, marks)


# --------------------------------------------------------------------------------------------- panier


def test_panier_un_sixieme_au_premier_cycle_puis_inerte():
    marks = mk_marks()
    state = PortfolioState("temoin:panier", 1000 * MICRO)
    ctx = TemoinContext(symbols=SYMBOLS)
    c0 = ts_of(2026, 11, 12)
    intents = panier.decide(c0, state, marks, ctx)
    assert [i.symbol for i in intents] == list(SYMBOLS)
    assert all(i.side == Side.BUY and i.size_bp == 1666 and i.stop_bp is None for i in intents)
    assert len({i.intent_id for i in intents}) == 6
    execute(intents, state, marks)
    assert set(state.positions) == set(SYMBOLS)
    for s in SYMBOLS:
        assert 1600 <= weight_bp(state, marks, s) <= 1700  # frais compris dans le budget (poids net des frais)
    assert 0 <= state.cash_ueur < 10_000_000
    # inerte ensuite, même après un mois et un grand mouvement de prix
    assert panier.decide(c0 + H4, state, marks, TemoinContext(symbols=SYMBOLS, cycle_index=1)) == []
    assert panier.decide(c0 + 40 * DAY, state, mk_marks(2.0), TemoinContext(symbols=SYMBOLS, cycle_index=99)) == []


def test_panier_ids_deterministes():
    state = PortfolioState("temoin:panier", 1000 * MICRO)
    ctx = TemoinContext(symbols=SYMBOLS)
    a = panier.decide(1000, state, mk_marks(), ctx)
    b = panier.decide(1000, state, mk_marks(), ctx)
    assert a == b


def test_reference_qty_arrondi_bas_frais_compris_jamais_cash_negatif():
    marks = mk_marks()
    for cash in (1 * MICRO, 7_777_777, 100 * MICRO, 999_999_999, 1000 * MICRO):
        state = PortfolioState("t", cash)
        for sym in SYMBOLS:
            from arene.temoins import make_intent

            it = make_intent("t", 1, 0, sym, Side.BUY, 10_000)  # tout le cash
            q = quote_at(sym, marks[sym])
            qty = reference_qty(it, state, marks, q, INSTRUMENTS[sym], FEE, SLIP)
            if qty:
                from arene.types import notional_ueur

                price, fee = market_fill(Side.BUY, qty, q, INSTRUMENTS[sym], FEE, SLIP)
                assert notional_ueur(qty, price, round_up=True) + fee <= cash
                # maximalité : une unité de plus ne tient plus (à quelques unités près pour l'arrondi)
                price2, fee2 = market_fill(Side.BUY, qty + 1 + QTY_SCALE // price * 2, q, INSTRUMENTS[sym], FEE, SLIP)
                assert notional_ueur(qty + 1 + QTY_SCALE // price * 2, price2, round_up=True) + fee2 > cash


def test_reference_qty_vente_partielle_et_totale():
    marks = mk_marks()
    state = PortfolioState("t", 0)
    from arene.temoins import make_intent
    from arene.types import Position

    state.positions["BTC/EUR"] = Position("BTC/EUR", 1_000_001, 1, 0)
    q = quote_at("BTC/EUR", marks["BTC/EUR"])
    half = make_intent("t", 1, 0, "BTC/EUR", Side.SELL, 5_000)
    assert reference_qty(half, state, marks, q, INSTRUMENTS["BTC/EUR"], FEE, SLIP) == 500_000  # arrondi bas
    full = make_intent("t", 1, 0, "BTC/EUR", Side.SELL, 10_000)
    assert reference_qty(full, state, marks, q, INSTRUMENTS["BTC/EUR"], FEE, SLIP) == 1_000_001


# ------------------------------------------------------------------------------------------------ 6040


def test_6040_reequilibre_au_premier_cycle_du_mois():
    marks = mk_marks()
    state = PortfolioState("temoin:6040", 1000 * MICRO)
    first = ts_of(2026, 11, 12)
    ctx = TemoinContext(symbols=SYMBOLS, cycle_index=0, prev_cycle_ts=None)
    intents = soixante_quarante.decide(first, state, marks, ctx)
    assert len(intents) == 1 and intents[0].symbol == "BTC/EUR" and intents[0].side == Side.BUY
    assert intents[0].size_bp == 6000
    execute(intents, state, marks)
    assert 5900 <= weight_bp(state, marks, "BTC/EUR") <= 6000

    # milieu de mois : rien, même si le poids dérive
    up = mk_marks()
    up["BTC/EUR"] *= 2
    mid = ts_of(2026, 11, 20, 8)
    assert soixante_quarante.decide(mid, state, up, TemoinContext(prev_cycle_ts=mid - H4, cycle_index=50)) == []
    # dernier cycle de novembre : rien
    last = ts_of(2026, 11, 30, 20)
    assert soixante_quarante.decide(last, state, up, TemoinContext(prev_cycle_ts=last - H4)) == []

    # premier cycle de décembre : BTC pèse trop, on vend pour revenir à 60 %
    dec = ts_of(2026, 12, 1)
    ints = soixante_quarante.decide(dec, state, up, TemoinContext(prev_cycle_ts=dec - H4, cycle_index=100))
    assert len(ints) == 1 and ints[0].side == Side.SELL and 0 < ints[0].size_bp < 10_000
    execute(ints, state, up)
    assert 5900 <= weight_bp(state, up, "BTC/EUR") <= 6100
    # le cycle suivant (04:00) ne fait rien
    nxt = dec + H4
    assert soixante_quarante.decide(nxt, state, up, TemoinContext(prev_cycle_ts=dec)) == []

    # BTC trop bas en janvier : on rachète
    down = mk_marks(0.5)
    jan = ts_of(2027, 1, 1)
    ints = soixante_quarante.decide(jan, state, down, TemoinContext(prev_cycle_ts=jan - H4))
    assert len(ints) == 1 and ints[0].side == Side.BUY
    execute(ints, state, down)
    assert 5900 <= weight_bp(state, down, "BTC/EUR") <= 6000


# ------------------------------------------------------------------------------------------------ E0065

D0 = ts_of(2026, 1, 1)  # jour 0 des données synthétiques


def day_series(sym: str, ratios: dict[int, float] | float, first_day: int = 0, last_day: int = 59, volume: int = 100 * QTY_SCALE):
    out = []
    for n in range(first_day, last_day + 1):
        r = ratios if isinstance(ratios, float) else ratios[n]
        out.append(DayBar(sym.replace("/", "") + "T", D0 + n * DAY, 1, volume, int(volume * r)))
    return out


def e0065_ctx(day_bars, **kw) -> TemoinContext:
    return TemoinContext(symbols=SYMBOLS, day_bars=day_bars, e0065=E0065Params(L=20, k=3, H=10), day0_ts=D0, **kw)


BASE_RATIOS = {"BTC/EUR": 0.50, "ETH/EUR": 0.60, "SOL/EUR": 0.70, "XRP/EUR": 0.40, "LINK/EUR": 0.55, "LTC/EUR": 0.65}


def test_e0065_classement_connu_a_la_main():
    bars = {s: day_series(s, r) for s, r in BASE_RATIOS.items()}
    ctx = e0065_ctx(bars)
    cyc = D0 + 20 * DAY  # jour 20 : reconstitution (20 mod 10 == 0), 20 jours clos
    assert [s for s, _ in e0065.ranking(cyc, ctx)] == ["SOL/EUR", "LTC/EUR", "ETH/EUR", "LINK/EUR", "BTC/EUR", "XRP/EUR"]
    assert e0065.target_weights(cyc, ctx) == {"SOL/EUR": 3333, "LTC/EUR": 3333, "ETH/EUR": 3333}
    state = PortfolioState("temoin:e0065", 1000 * MICRO)
    marks = mk_marks()
    ints = e0065.decide(cyc, state, marks, e0065_ctx(bars, prev_cycle_ts=cyc - H4))
    assert {i.symbol for i in ints} == {"SOL/EUR", "LTC/EUR", "ETH/EUR"}
    assert all(i.side == Side.BUY and i.size_bp == 3333 for i in ints)
    execute(ints, state, marks)
    for s in ("SOL/EUR", "LTC/EUR", "ETH/EUR"):
        assert 3250 <= weight_bp(state, marks, s) <= 3333


def test_e0065_reconstitution_tous_les_H_jours_au_premier_cycle_du_jour():
    bars = {s: day_series(s, r) for s, r in BASE_RATIOS.items()}
    state = PortfolioState("temoin:e0065", 1000 * MICRO)
    marks = mk_marks()
    fired = []
    prev = None
    for step in range(55 * 6):
        cyc = D0 + 15 * DAY + step * H4
        ints = e0065.decide(cyc, state, marks, e0065_ctx(bars, prev_cycle_ts=prev, cycle_index=step))
        if ints:
            fired.append((cyc - D0) // DAY)
            assert (cyc - D0) % DAY == 0  # premier cycle du jour : 00:00 UTC
            execute(ints, state, marks)
        prev = cyc
    # jours 20 (achats), puis 30, 40, 50, 60 ne sortent rien de nouveau (classement stable, poids déjà bons)
    assert fired[0] == 20
    assert all(d % 10 == 0 for d in fired)
    # un autre cycle du jour 20 ou 21 ne déclenche rien
    assert e0065.decide(D0 + 20 * DAY + H4, state, marks, e0065_ctx(bars, prev_cycle_ts=D0 + 20 * DAY)) == []
    assert e0065.decide(D0 + 25 * DAY, state, marks, e0065_ctx(bars, prev_cycle_ts=D0 + 25 * DAY - H4)) == []


def test_e0065_rotation_vend_ce_qui_sort_achete_ce_qui_entre():
    # XRP devient la meilleure paire à partir du jour 30 ; BTC reste dernière
    ratios = dict(BASE_RATIOS)
    series = {s: day_series(s, r) for s, r in ratios.items()}
    series["XRP/EUR"] = day_series("XRP/EUR", {n: (0.40 if n < 30 else 0.95) for n in range(60)})
    state = PortfolioState("temoin:e0065", 1000 * MICRO)
    marks = mk_marks()
    c20 = D0 + 20 * DAY
    execute(e0065.decide(c20, state, marks, e0065_ctx(series, prev_cycle_ts=c20 - H4)), state, marks)
    assert set(state.positions) == {"SOL/EUR", "LTC/EUR", "ETH/EUR"}
    # jour 40 : moyenne des jours 20..39 pour XRP = (10 * 0.40 + 10 * 0.95) / 20 = 0.675 -> 2e derrière SOL 0.70
    c40 = D0 + 40 * DAY
    ctx = e0065_ctx(series, prev_cycle_ts=c40 - H4)
    assert [s for s, _ in e0065.ranking(c40, ctx)][:3] == ["SOL/EUR", "XRP/EUR", "LTC/EUR"]
    ints = e0065.decide(c40, state, marks, ctx)
    sells = [i for i in ints if i.side == Side.SELL]
    buys = [i for i in ints if i.side == Side.BUY]
    assert sells[0].symbol == "ETH/EUR" and sells[0].size_bp == 10_000  # sort : vente totale
    assert any(i.symbol == "XRP/EUR" for i in buys)  # entre
    assert ints.index(sells[0]) < ints.index(buys[0])  # les ventes d'abord
    execute(ints, state, marks)
    assert "ETH/EUR" not in state.positions and "XRP/EUR" in state.positions
    for s in ("SOL/EUR", "XRP/EUR", "LTC/EUR"):
        assert 3150 <= weight_bp(state, marks, s) <= 3400


def test_e0065_eligibilite_L_jours_valides():
    bars = {s: day_series(s, r) for s, r in BASE_RATIOS.items()}
    # SOL (meilleure) n'a que 10 jours de données à la reconstitution du jour 20 : inéligible
    bars["SOL/EUR"] = day_series("SOL/EUR", 0.99, first_day=10)
    # LTC a un jour sans volume dans la fenêtre : inéligible
    ltc = day_series("LTC/EUR", 0.65)
    ltc[15] = DayBar(ltc[15].symbol, ltc[15].ts, 1, 0, 0)
    bars["LTC/EUR"] = ltc
    ctx = e0065_ctx(bars)
    cyc = D0 + 20 * DAY
    rank = [s for s, _ in e0065.ranking(cyc, ctx)]
    assert "SOL/EUR" not in rank and "LTC/EUR" not in rank
    assert rank == ["ETH/EUR", "LINK/EUR", "BTC/EUR", "XRP/EUR"]
    # moins de k éligibles : chaque éligible vise 1/k
    only2 = {s: bars[s] for s in ("ETH/EUR", "BTC/EUR")}
    assert e0065.target_weights(cyc, e0065_ctx(only2)) == {"ETH/EUR": 3333, "BTC/EUR": 3333}
    # à 20 jours de données exactement, éligible ; à 19, non
    bars["SOL/EUR"] = day_series("SOL/EUR", 0.99, first_day=0)
    assert "SOL/EUR" in [s for s, _ in e0065.ranking(cyc, e0065_ctx(bars))]
    bars["SOL/EUR"] = day_series("SOL/EUR", 0.99, first_day=1)
    assert "SOL/EUR" not in [s for s, _ in e0065.ranking(cyc, e0065_ctx(bars))]


def test_e0065_egalite_ordre_alphabetique():
    bars = {s: day_series(s, 0.5) for s in SYMBOLS}
    ctx = e0065_ctx(bars)
    assert [s for s, _ in e0065.ranking(D0 + 20 * DAY, ctx)] == sorted(SYMBOLS)
    assert list(e0065.target_weights(D0 + 20 * DAY, ctx)) == ["BTC/EUR", "ETH/EUR", "LINK/EUR"]


def test_e0065_anti_fuite_aucune_donnee_du_jour_en_cours_ni_du_futur():
    base = {s: day_series(s, r, last_day=19) for s, r in BASE_RATIOS.items()}  # jours 0..19 : clos au jour 20 00:00
    cyc = D0 + 20 * DAY
    ref = e0065.target_weights(cyc, e0065_ctx(base))
    assert set(ref) == {"SOL/EUR", "LTC/EUR", "ETH/EUR"}
    # on ajoute la barre du jour en cours (jour 20, non close) et le futur avec un ratio absurde pour BTC
    leaked = {s: list(b) for s, b in base.items()}
    for n in (20, 21, 22):
        leaked["BTC/EUR"].append(DayBar("BTCUSDT", D0 + n * DAY, 1, 100 * QTY_SCALE, 100 * QTY_SCALE))
        leaked["XRP/EUR"].append(DayBar("XRPUSDT", D0 + n * DAY, 1, 100 * QTY_SCALE, 100 * QTY_SCALE))
    assert e0065.ranking(cyc, e0065_ctx(leaked)) == e0065.ranking(cyc, e0065_ctx(base))
    assert e0065.target_weights(cyc, e0065_ctx(leaked)) == ref
    # même chose à un cycle de 04:00 (la barre du jour 20 ne se clôt qu'à 00:00 du jour 21)
    cyc4 = D0 + 21 * DAY - H4
    assert e0065.ranking(cyc4, e0065_ctx(leaked)) == e0065.ranking(cyc, e0065_ctx(base))
    # sans anti-fuite, BTC serait premier : on vérifie que la donnée absurde compterait bien après clôture
    assert e0065.ranking(D0 + 23 * DAY, e0065_ctx(leaked))[0][0] == "BTC/EUR"


def test_e0065_jour0_deduit_des_donnees_si_non_fourni():
    bars = {s: day_series(s, r, first_day=3) for s, r in BASE_RATIOS.items()}
    ctx = TemoinContext(symbols=SYMBOLS, day_bars=bars)
    assert e0065.day0(ctx, D0 + 40 * DAY) == D0 + 3 * DAY


# --------------------------------------------------------------------------------------------- aléatoire


def test_aleatoire_deterministe_pour_une_graine():
    state = PortfolioState("temoin:aleatoire", 1000 * MICRO)
    marks = mk_marks()
    assert aleatoire.seed_for(100, 0) == aleatoire.seed_for(100, 0)
    assert aleatoire.seed_for(100, 0) != aleatoire.seed_for(100, 1)
    assert aleatoire.seed_for(100, 0) != aleatoire.seed_for(104, 0)
    ctx = TemoinContext(symbols=SYMBOLS, trajectoire=3)
    runs = [aleatoire.decide(c, state, marks, ctx) for c in range(0, 400 * H4, H4)]
    again = [aleatoire.decide(c, state, marks, ctx) for c in range(0, 400 * H4, H4)]
    assert runs == again
    other = [aleatoire.decide(c, state, marks, TemoinContext(symbols=SYMBOLS, trajectoire=4)) for c in range(0, 400 * H4, H4)]
    assert runs != other


def test_aleatoire_distribution_de_l_espace_d_actions():
    marks = mk_marks()
    flat = PortfolioState("temoin:aleatoire", 1000 * MICRO)  # aucune position : seulement des achats
    ctx = TemoinContext(symbols=SYMBOLS)
    counts = [0, 0, 0]
    syms = set()
    for c in range(0, 3000 * H4, H4):
        ints = aleatoire.decide(c, flat, marks, ctx)
        counts[len(ints)] += 1
        for i in ints:
            assert i.portfolio == "temoin:aleatoire" and i.side == Side.BUY
            assert 100 <= i.size_bp <= 2000 and 200 <= i.stop_bp <= 1000 and 500 <= i.expected_move_bp <= 1500
            syms.add(i.symbol)
    assert syms == set(SYMBOLS)
    assert all(850 <= n <= 1150 for n in counts)  # 0, 1 ou 2 actions, uniformes
    # avec une position : des ventes apparaissent, uniquement sur le symbole détenu
    from arene.types import Position

    held = PortfolioState("temoin:aleatoire", 1000 * MICRO, {"SOL/EUR": Position("SOL/EUR", QTY_SCALE, 1, 0)})
    sides = set()
    for c in range(0, 2000 * H4, H4):
        for i in aleatoire.decide(c, held, marks, ctx):
            sides.add(i.side)
            if i.side == Side.SELL:
                assert i.symbol == "SOL/EUR" and i.stop_bp is None
    assert sides == {Side.BUY, Side.SELL}
    broke = PortfolioState("temoin:aleatoire", 0)
    assert all(aleatoire.decide(c, broke, marks, ctx) == [] for c in range(0, 200 * H4, H4))


# ------------------------------------------------------------------------------------------- trajectoires


def synth_cycles(n: int, *, crash_bars: bool = False, start: int = ts_of(2026, 11, 12)) -> list[CycleData]:
    """n cycles d'un marché synthétique déterministe (marche pseudo-aléatoire simple)."""
    import random

    rng = random.Random(7)
    prices = {s: PRICES[s] * MICRO for s in SYMBOLS}
    out = []
    for k in range(n):
        ts = start + k * H4
        bars = {}
        quotes = {}
        marks = {}
        closes = {}
        for s in SYMBOLS:
            old = prices[s]
            prices[s] = prices[s] * (10_000 + rng.randint(-60, 60)) // 10_000
            mark = prices[s]
            half = mark // 10_000
            quotes[s] = Quote(s, ts, mark - half, mark + half)
            marks[s] = mark
            closes[s] = mark
            low = old // 3 if crash_bars else min(old, mark)
            bars[s] = (Bar(s, H4, ts - H4, old, max(old, mark), low, mark, 1),)
        out.append(CycleData(ts, quotes, marks, closes, bars))
    return out


def run_traj(cycles, n, **kw):
    return simulate_random_trajectories(
        cycles, n, policy=POLICY, instruments=INSTRUMENTS, fee_bp=FEE, slippage_bp=SLIP, capital_ueur=1000 * MICRO, **kw
    )


def test_trajectoires_deterministes_et_distinctes():
    cycles = synth_cycles(40)
    a = run_traj(cycles, 30)
    b = run_traj(cycles, 30)
    assert a == b
    assert len(a) == 30 and all(isinstance(x, int) for x in a)
    assert len(set(a)) > 15  # les graines diffèrent : les trajectoires aussi
    assert a[:10] == run_traj(cycles, 10)  # la trajectoire t ne dépend pas de n


def test_trajectoires_respectent_riskd_et_les_frais():
    cycles = synth_cycles(60)
    eq = simulate_trajectory(
        cycles, 1, policy=POLICY, instruments=INSTRUMENTS, fee_bp=FEE, slippage_bp=SLIP, capital_ueur=1000 * MICRO
    )
    assert len(eq) == 60 and eq[0] <= 1000 * MICRO and min(eq) > 0
    assert all(e <= 3000 * MICRO for e in eq)  # long seul, sans levier : pas d'explosion
    # sans aucun cycle : le capital intact
    assert run_traj([], 3) == [1000 * MICRO] * 3


def test_trajectoires_les_stops_sont_rejoues():
    calm = synth_cycles(60)
    crash = synth_cycles(60, crash_bars=True)  # chaque barre plonge sous tout stop possible (2-10 %)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        run_traj([CycleData(c.ts, c.quotes, c.marks, c.last_closes) for c in calm], 3)  # sans barres
        assert any("stops" in str(x.message) for x in w)
    a = run_traj(calm, 40)
    b = run_traj(crash, 40)
    assert a != b
    assert sum(b) < sum(a)  # les sorties à perte sur stop coûtent de l'argent


def test_trajectoires_performance_1000_x_180_x_6():
    cycles = synth_cycles(180)
    t0 = time.perf_counter()
    out = run_traj(cycles, 1000)
    dt = time.perf_counter() - t0
    assert len(out) == 1000
    assert dt < 60, f"{dt:.1f} s"
