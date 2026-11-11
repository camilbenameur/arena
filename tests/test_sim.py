"""Tests de arene/sim : arrondis, stops, idempotence, UNKNOWN, reprise après crash, bout en bout."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arene.journal import Journal
from arene.ledger import equity_ueur, replay
from arene.risk.policy import load_policy
from arene.risk.riskd import Counters, MarketView, evaluate
from arene.sim.executor import SimExecutor
from arene.sim.fills import FILL_MODEL_VERSION, market_fill, stop_fill, stop_price
from arene.types import MICRO, QTY_SCALE, Bar, Instrument, Intent, Quote, Side, Verdict

POLICY = load_policy(Path(__file__).resolve().parent.parent / "config" / "policy.toml")
EUR = MICRO
T0 = 1_700_000_000
BTC = "BTC/EUR"
BTC_I = Instrument(BTC, "XBTEUR", "BTCUSDT", 100_000, 6_000, 450_000)  # tick 0,1 EUR
XRP_I = Instrument("XRP/EUR", "XRPEUR", "XRPUSDT", 10, 400_000_000, 450_000)
INSTR = {BTC: BTC_I, "XRP/EUR": XRP_I}
P = "llm:test"


def q(bid: int, ask: int, sym: str = BTC, ts: int = T0) -> Quote:
    return Quote(sym, ts, bid, ask)


def mk(tmp_path, capital=1_000 * EUR, fault=None, portfolios=(P,)):
    j = Journal(tmp_path / "events.jsonl")
    for p in portfolios:
        j.append(
            "portfolio_opened",
            {"portfolio": p, "kind": "llm", "capital_ueur": capital, "venue_mode": "paper"},
            T0,
        )
    return j, SimExecutor(j, INSTR, 50, 5, fault_injector=fault)


def buy_intent(iid="i1", stop_bp=500, p=P):
    return Intent(iid, p, T0, BTC, Side.BUY, 1000, stop_bp, 24, 500, 60)


def ok(iid="i1", qty=100_000, p=P):  # 0,001 BTC
    return Verdict(iid, True, (), qty, 100 * EUR, "h")


def fills_in(j):
    return [e for e in j.events() if e["type"] == "fill"]


def states_of(j, oid):
    return [
        e["payload"]["state"]
        for e in j.events()
        if e["type"] == "order_state" and e["payload"]["order_id"] == oid
    ]


# --------------------------------------------------------------------------- fills purs


def test_achat_arrondi_tick_vers_le_haut():
    # ask 50 000,03 € ×1,0005 = 50 025,015 € -> tick 0,1 -> 50 025,1 €
    price, _ = market_fill(Side.BUY, 100_000, q(49_990 * EUR, 50_000_030_000), BTC_I, 50, 5)
    assert price == 50_025_100_000


def test_vente_arrondi_tick_vers_le_bas():
    # bid 49 990,05 × 0,9995 = 49 965,0550... -> 49 965,0 €
    price, _ = market_fill(Side.SELL, 100_000, q(49_990_050_000, 50_010 * EUR), BTC_I, 50, 5)
    assert price == 49_965_000_000
    assert price % BTC_I.tick_ueur == 0


def test_frais_arrondis_vers_le_haut():
    # 3 unités 1e-8 à 1,5 EUR : notional 0,045 µEUR -> 1 µEUR ; frais 1 × 50 / 10000 -> 1 µEUR
    price, fee = market_fill(Side.BUY, 3, q(1_000_000, 1_500_000), XRP_I, 50, 0)
    assert price == 1_500_000 and fee == 1
    _, fee = market_fill(Side.BUY, QTY_SCALE, q(1, 100 * EUR), BTC_I, 50, 0)
    assert fee == 500_000  # exact : 100 € × 0,5 %
    _, fee = market_fill(Side.BUY, QTY_SCALE, q(1, 100 * EUR + 1), XRP_I, 50, 0)
    assert fee == 500_001  # 500 000,005 arrondi vers le haut


def test_stop_non_touche_et_touche():
    bar = Bar(BTC, 14400, T0, 50_000 * EUR, 51_000 * EUR, 48_000 * EUR, 49_000 * EUR, 1)
    assert stop_fill(47_000 * EUR, bar, BTC_I, 5) is None
    # low == stop : touché, pas de gap -> stop × 0,9995
    assert stop_fill(48_000 * EUR, bar, BTC_I, 5) == 47_976 * EUR


def test_gap_sous_le_stop():
    bar = Bar(BTC, 14400, T0, 44_000 * EUR, 44_500 * EUR, 43_000 * EUR, 44_000 * EUR, 1)
    assert stop_fill(45_000 * EUR, bar, BTC_I, 5) == 43_978 * EUR  # 44 000 × 0,9995, pas 45 000


def test_stop_price_arrondi_bas():
    assert stop_price(50_025_100_000, 500, BTC_I) == 47_523_800_000  # 47 523,845 -> tick bas
    assert stop_price(50_025_100_000, 500, BTC_I) % BTC_I.tick_ueur == 0


# --------------------------------------------------------------------------- exécuteur


def test_execute_sequence_et_stop(tmp_path):
    j, ex = mk(tmp_path)
    f = ex.execute(buy_intent(), ok(), q(49_990 * EUR, 50_010 * EUR), T0)
    assert f is not None and f.reason == "intent" and f.fill_model_version == FILL_MODEL_VERSION
    assert f.price_ueur == 50_035_100_000  # 50 010 × 1,0005 = 50 035,005 -> tick haut
    assert states_of(j, "i1") == ["SUBMITTING", "ACKED", "FILLED"]
    fe = fills_in(j)[0]["payload"]
    assert fe["venue_mode"] == "paper" and fe["fill_model_version"] == FILL_MODEL_VERSION
    st = replay(j.iter_events())[P]
    assert st.positions[BTC].stop_ueur == stop_price(f.price_ueur, 500, BTC_I)
    assert j.verify().ok


def test_refus_si_non_approuve(tmp_path):
    j, ex = mk(tmp_path)
    v = Verdict("i1", False, ("MAX_ORDER_SIZE",))
    assert ex.execute(buy_intent(), v, q(49_990 * EUR, 50_010 * EUR), T0) is None
    assert fills_in(j) == []
    assert states_of(j, "i1") == ["RISK_REJECTED"]
    assert ex.execute(buy_intent(), v, q(49_990 * EUR, 50_010 * EUR), T0) is None
    assert states_of(j, "i1") == ["RISK_REJECTED"]  # pas de doublon


def test_idempotence_meme_intention_deux_fois(tmp_path):
    j, ex = mk(tmp_path)
    quote = q(49_990 * EUR, 50_010 * EUR)
    assert ex.execute(buy_intent(), ok(), quote, T0) is not None
    n = len(j.events())
    assert ex.execute(buy_intent(), ok(), quote, T0 + 10) is None
    assert len(fills_in(j)) == 1 and len(j.events()) == n


def test_unknown_jamais_renvoye(tmp_path):
    j, ex = mk(tmp_path, fault=lambda oid: True)
    quote = q(49_990 * EUR, 50_010 * EUR)
    assert ex.execute(buy_intent(), ok(), quote, T0) is None
    assert states_of(j, "i1") == ["SUBMITTING", "UNKNOWN"] and fills_in(j) == []
    assert ex.execute(buy_intent(), ok(), quote, T0 + 60) is None  # pas de second envoi
    assert states_of(j, "i1") == ["SUBMITTING", "UNKNOWN"]
    # âge et résolution
    assert ex.unknown_age_cycles(P, T0 + 3 * 14_400) == 3
    assert ex.unknown_age_cycles("autre", T0 + 3 * 14_400) == 0
    assert ex.resolve_unknown("i1", T0 + 3 * 14_400) is True
    assert states_of(j, "i1")[-1] == "CANCELED"
    assert ex.unknown_age_cycles(P, T0 + 3 * 14_400) == 0
    assert ex.resolve_unknown("i1", T0 + 3 * 14_400) is False
    assert ex.execute(buy_intent(), ok(), quote, T0 + 99) is None and fills_in(j) == []


def _truncate_after(path: Path, keep_types: int) -> None:
    """Simule un crash : garde seulement les `keep_types` premiers événements puis recalcule rien (coupe nette)."""
    lines = path.read_text().splitlines(keepends=True)
    path.write_text("".join(lines[:keep_types]))


@pytest.mark.parametrize("keep", [1, 2])  # après SUBMITTING, après ACKED (avant le fill)
def test_crash_entre_submitting_et_filled(tmp_path, keep):
    j, ex = mk(tmp_path)
    ex.execute(buy_intent(), ok(), q(49_990 * EUR, 50_010 * EUR), T0)
    _truncate_after(j.path, 1 + keep)  # portfolio_opened + keep états
    assert j.verify().ok and fills_in(j) == []
    ex2 = SimExecutor(Journal(j.path), INSTR, 50, 5)
    assert ex2.execute(buy_intent(), ok(), q(49_990 * EUR, 50_010 * EUR), T0 + 60) is None
    assert fills_in(j) == []  # aucun double fill, aucun renvoi
    assert states_of(j, "i1")[-1] == "UNKNOWN"
    assert ex2.resolve_unknown("i1", T0 + 120)
    assert fills_in(j) == []


def test_crash_apres_fill_avant_stop_complete_a_la_reprise(tmp_path):
    j, ex = mk(tmp_path)
    ex.execute(buy_intent(), ok(), q(49_990 * EUR, 50_010 * EUR), T0)
    _truncate_after(j.path, 4)  # opened, SUBMITTING, ACKED, fill
    ex2 = SimExecutor(Journal(j.path), INSTR, 50, 5)
    assert ex2.execute(buy_intent(), ok(), q(49_990 * EUR, 50_010 * EUR), T0 + 60) is None
    assert len(fills_in(j)) == 1
    assert replay(j.iter_events())[P].positions[BTC].stop_ueur is not None
    assert states_of(j, "i1")[-1] == "FILLED"
    n = len(j.events())
    ex2.execute(buy_intent(), ok(), q(49_990 * EUR, 50_010 * EUR), T0 + 90)
    assert len(j.events()) == n


def test_cash_insuffisant_canceled(tmp_path):
    j, ex = mk(tmp_path, capital=10 * EUR)
    assert ex.execute(buy_intent(), ok(), q(49_990 * EUR, 50_010 * EUR), T0) is None
    assert states_of(j, "i1") == ["CANCELED"] and fills_in(j) == []
    detail = next(e for e in j.events() if e["type"] == "order_state")["payload"]["detail"]
    assert "cash insuffisant" in detail


def test_sous_minimums_canceled(tmp_path):
    j, ex = mk(tmp_path)
    assert (
        ex.execute(buy_intent("a"), ok("a", qty=5_999), q(49_990 * EUR, 50_010 * EUR), T0) is None
    )  # < lot_min
    assert states_of(j, "a") == ["CANCELED"]
    # lot ok (6 000) mais notional 3 € < 0,45 ? 0,00006 BTC à 50 000 € = 3 € : ok ; on teste le cost_min avec un XRP
    cheap = Instrument("XRP/EUR", "XRPEUR", "XRPUSDT", 10, 1, 450_000)
    ex2 = SimExecutor(j, {"XRP/EUR": cheap}, 50, 5)
    it = Intent("b", P, T0, "XRP/EUR", Side.BUY, 10, 500, 24, 500, 60)
    assert ex2.execute(it, ok("b", qty=1_000), q(1 * EUR, 2 * EUR, "XRP/EUR"), T0) is None  # 0,00001 XRP
    assert states_of(j, "b") == ["CANCELED"]


def bar(ts, o, h, lo, c, sym=BTC):
    return Bar(sym, 14_400, ts, o * EUR, h * EUR, lo * EUR, c * EUR, 1)


def open_position(tmp_path, **kw):
    j, ex = mk(tmp_path, **kw)
    f = ex.execute(buy_intent(), ok(), q(49_990 * EUR, 50_010 * EUR), T0)
    assert f
    return j, ex, f


def test_stop_plusieurs_barres_ordre_et_idempotence(tmp_path):
    j, ex, _ = open_position(tmp_path)
    stop = replay(j.iter_events())[P].positions[BTC].stop_ueur
    assert stop == 47_533_300_000
    t1 = T0 + 14_400
    bars = {
        BTC: [bar(t1 + 14_400, 47_000, 47_500, 46_000, 46_500), bar(t1, 50_000, 50_500, 47_000, 49_000)]
    }  # désordonnées
    now = T0 + 28_800
    out = ex.process_stops_and_expiry(bars, {BTC: q(46_000 * EUR, 46_010 * EUR, ts=now)}, now, 604_800)
    assert len(out) == 1 and out[0].reason == "stop"
    # première barre (t1) touche le stop (low 47 000 < 47 533,3), ouverture 50 000 > stop -> sortie au stop
    assert out[0].order_id == f"stop:{P}:{BTC}:{t1}"
    assert out[0].price_ueur == (stop * 9_995 // 10_000) // 100_000 * 100_000
    assert BTC not in replay(j.iter_events())[P].positions
    assert ex.process_stops_and_expiry(bars, {}, now, 604_800) == []  # rejouer : rien de plus


def test_stop_ignore_barre_anterieure_a_l_entree(tmp_path):
    _, ex, _ = open_position(tmp_path)
    old = bar(T0 - 14_400, 50_000, 50_000, 10_000, 10_000)
    assert ex.process_stops_and_expiry({BTC: [old]}, {}, T0 + 100, 604_800) == []


def test_stop_gap(tmp_path):
    _, ex, _ = open_position(tmp_path)
    b = bar(T0 + 14_400, 40_000, 41_000, 39_000, 40_500)
    out = ex.process_stops_and_expiry({BTC: [b]}, {}, T0 + 28_800, 604_800)
    assert out[0].price_ueur == 40_000 * EUR * 9_995 // 10_000


def test_detention_maximale(tmp_path):
    j, ex, _ = open_position(tmp_path)
    now = T0 + 604_800
    quote = q(51_000 * EUR, 51_020 * EUR, ts=now)
    assert ex.process_stops_and_expiry({}, {BTC: quote}, now - 1, 604_800) == []
    out = ex.process_stops_and_expiry({}, {BTC: quote}, now, 604_800)
    assert len(out) == 1 and out[0].reason == "max_holding" and out[0].qty == 100_000
    assert out[0].price_ueur == 51_000 * EUR * 9_995 // 10_000 // 100_000 * 100_000
    assert ex.process_stops_and_expiry({}, {BTC: quote}, now + 5, 604_800) == []
    assert not replay(j.iter_events())[P].positions


def test_flatten(tmp_path):
    j, ex, _ = open_position(tmp_path)
    quotes = {BTC: q(49_000 * EUR, 49_010 * EUR, ts=T0 + 10)}
    out = ex.flatten(P, quotes, T0 + 10, "kill_switch")
    assert len(out) == 1 and out[0].reason == "kill_switch" and out[0].side == Side.SELL
    assert not replay(j.iter_events())[P].positions
    assert ex.flatten(P, quotes, T0 + 10, "kill_switch") == []
    assert ex.flatten("inconnu", quotes, T0 + 10, "halt") == []


# --------------------------------------------------------------------------- bout en bout


def test_bout_en_bout_riskd_execute_ledger(tmp_path):
    j, ex = mk(tmp_path)
    quote = q(49_990 * EUR, 50_010 * EUR)
    intent = Intent("e2e", P, T0, BTC, Side.BUY, 1500, 500, 24, 500, 60)
    state = replay(j.iter_events())[P]
    mkt = MarketView(
        quotes={BTC: quote},
        last_closes={BTC: 50_000 * EUR},
        median_spreads_ueur={BTC: 20 * EUR},
        marks={BTC: 50_000 * EUR},
    )
    cnt = Counters(0, 0, None, 0, 1_000 * EUR, 1_000 * EUR, 1_000 * EUR, 1_000 * EUR)
    v = evaluate(intent, state, mkt, POLICY, cnt, T0, INSTR, 50, 5, False)
    assert v.approved, v.reasons
    f = ex.execute(intent, v, quote, T0)
    assert f is not None and f.qty == v.qty
    st = replay(j.iter_events())[P]
    pos = st.positions[BTC]
    assert st.cash_ueur + pos.cost_ueur == 1_000 * EUR + st.realized_pnl_ueur  # au µEUR
    assert st.fees_paid_ueur == f.fee_ueur
    # sortie : vente complète, P&L réalisé cohérent
    out = ex.flatten(P, {BTC: q(50_500 * EUR, 50_520 * EUR, ts=T0 + 3600)}, T0 + 3600, "halt")
    st = replay(j.iter_events())[P]
    assert not st.positions
    assert st.cash_ueur == 1_000 * EUR + st.realized_pnl_ueur
    assert equity_ueur(st, {}) == st.cash_ueur
    assert st.fees_paid_ueur == f.fee_ueur + out[0].fee_ueur
    assert j.verify().ok
    json.dumps(j.events())  # aucun float
