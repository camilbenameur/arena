"""Revue adverse (red team) du MVP : chaque test tente de violer la politique de risque, de fausser le P&L
ou d'afficher un chiffre faux. Un test qui échoue révèle une faille ; un test qui passe est un test de
non-régression. Tout vit dans tmp_path : jamais le `var/` du dépôt ni `~/.config/arene`.
"""

from __future__ import annotations

import json
import random
from dataclasses import replace
from pathlib import Path

import pytest

from arene import cycle as cycle_mod
from arene.config import load_config
from arene.deciders.llm import parse_decision
from arene.journal import Journal, verify
from arene.ledger import LedgerError, replay, trades_last_24h
from arene.risk.policy import load_policy
from arene.risk.riskd import Counters, MarketView, evaluate
from arene.sim.executor import SimExecutor
from arene.site import build as build_site
from arene.site import data as site_data
from arene.temoins import reference_qty
from arene.types import (
    MICRO,
    Instrument,
    Intent,
    PortfolioState,
    Position,
    Quote,
    Side,
    Verdict,
)
from tests.fakes import (
    H4,
    HAIKU,
    T0,
    Env,
    action,
    make_deciders,
)
from tests.test_cycle import payloads, run_cycles

REPO = Path(__file__).resolve().parent.parent
POLICY = load_policy(REPO / "config" / "policy.toml")
NOW = 1_700_000_000
BTC = "BTC/EUR"
INSTR = {
    "BTC/EUR": Instrument("BTC/EUR", "XBTEUR", "BTCUSDT", 100_000, 6_000, 450_000),
    "ETH/EUR": Instrument("ETH/EUR", "ETHEUR", "ETHUSDT", 10_000, 200_000, 450_000),
}
FEE_BP, SLIP_BP = 50, 5


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def buy_plan(idx: int, snap: dict) -> list[dict] | None:
    """Un achat BTC de 10 % au cycle 1, rien d'autre."""
    return [action("BTC/EUR", size=10)] if idx == 1 else None


def deciders_for(plan) -> dict:
    d = make_deciders(plan)
    return d


def mk_intent(side: Side = Side.BUY, symbol: str = BTC, size_bp: int = 1000, idx: int = 0, **kw) -> Intent:
    base = {"stop_bp": 500, "expected_move_bp": 600} if side == Side.BUY else {}
    base.update(kw)
    return Intent(f"i{idx}-{symbol}-{side.value}-{size_bp}", "llm:test", NOW, symbol, side, size_bp, **base)


def mk_market(mid: int = 50_000 * MICRO) -> MarketView:
    quotes = {s: Quote(s, NOW, mid - mid // 4000, mid + mid // 4000) for s in INSTR}
    return MarketView(
        quotes=quotes,
        last_closes={s: mid for s in INSTR},
        median_spreads_ueur={s: quotes[s].ask - quotes[s].bid for s in INSTR},
        marks={s: mid for s in INSTR},
    )


def mk_counters(**kw) -> Counters:
    base = {
        "equity_month_start_ueur": 1_000 * MICRO, "equity_24h_ago_ueur": 1_000 * MICRO,
        "equity_peak_ueur": 1_000 * MICRO, "equity_now_ueur": 1_000 * MICRO,
    }  # fmt: skip
    base.update(kw)
    return Counters(**base)


def ev(intent: Intent, state: PortfolioState, market: MarketView | None = None, counters: Counters | None = None,
       kill: bool = False, policy=POLICY) -> Verdict:  # fmt: skip
    return evaluate(
        intent, state, market or mk_market(), policy, counters or mk_counters(), NOW, INSTR, FEE_BP, SLIP_BP, kill
    )


# ====================================================================== 1. verdict -> exécution


def test_fill_egale_verdict_et_reste_sous_la_reservation(env: Env):
    """L'exécuteur exécute verdict.qty (pas de recalcul) et le total payé ne dépasse pas ce que riskd a réservé."""
    run_cycles(env, 3, deciders=deciders_for(buy_plan))
    verdicts = {v["intent_id"]: v for v in payloads(env, "risk_verdict")}
    fills = [f for f in payloads(env, "fill", HAIKU) if f["reason"] == "intent"]
    assert fills, "Haiku devait acheter"
    for f in fills:
        v = verdicts[f["order_id"]]
        assert v["approved"] and f["qty"] == v["qty"]
        total = -(-f["qty"] * f["price_ueur"] // 100_000_000) + f["fee_ueur"]
        assert total <= v["reserved_ueur"]


def test_executeur_refuse_un_quote_plus_cher_que_celui_du_verdict(tmp_path: Path):
    """Si le quote d'exécution a bougé contre nous après le verdict, le total ne doit pas dépasser la réservation."""
    j = Journal(tmp_path / "j.jsonl")
    j.append("portfolio_opened", {"portfolio": "llm:test", "kind": "llm", "capital_ueur": 1_000 * MICRO,
                                  "venue_mode": "paper"}, NOW)  # fmt: skip
    st = replay(j.iter_events())["llm:test"]
    intent = mk_intent(size_bp=2000)
    verdict = ev(intent, st)
    assert verdict.approved and verdict.reserved_ueur > 0
    ex = SimExecutor(j, INSTR, FEE_BP, SLIP_BP)
    mkt = mk_market()
    pricier = Quote(BTC, NOW, mkt.quotes[BTC].bid, mkt.quotes[BTC].ask * 3 // 2)  # +50 % sur l'ask
    fill = ex.execute(intent, verdict, pricier, NOW)
    if fill is not None:
        total = -(-fill.qty * fill.price_ueur // 100_000_000) + fill.fee_ueur
        assert total <= verdict.reserved_ueur, f"fill {total} > réservé {verdict.reserved_ueur}"
    s2 = replay(j.iter_events())["llm:test"]
    assert s2.cash_ueur >= 0


def test_executeur_n_execute_pas_un_verdict_rejete_ni_d_un_autre_intent(tmp_path: Path):
    j = Journal(tmp_path / "j.jsonl")
    j.append("portfolio_opened", {"portfolio": "llm:test", "kind": "llm", "capital_ueur": 1_000 * MICRO,
                                  "venue_mode": "paper"}, NOW)  # fmt: skip
    st = replay(j.iter_events())["llm:test"]
    ex = SimExecutor(j, INSTR, FEE_BP, SLIP_BP)
    q = mk_market().quotes[BTC]
    good = ev(mk_intent(size_bp=1000, idx=1), st)
    other = mk_intent(size_bp=1000, idx=2)
    assert ex.execute(other, good, q, NOW) is None  # verdict d'un autre intent_id
    bad = ev(mk_intent(size_bp=2500, idx=3), st)  # MAX_ORDER_SIZE
    assert not bad.approved
    assert ex.execute(mk_intent(size_bp=2500, idx=3), bad, q, NOW) is None
    assert not [e for e in j.iter_events() if e["type"] == "fill"]


# ====================================================================== 2. fractionnement


def two_buys_plan(size: int):
    def plan(idx: int, snap: dict):
        if idx == 1:
            return [action("BTC/EUR", size=size), action("BTC/EUR", size=size)]
        return None

    return plan


def test_deux_achats_meme_symbole_meme_cycle_sont_bornes(env: Env):
    """Deux achats de 20 % sur le même symbole dans le même cycle : le second est refusé (TOO_SOON)."""
    run_cycles(env, 2, deciders=deciders_for(two_buys_plan(20)))
    ids = [i["intent_id"] for i in payloads(env, "intent", HAIKU)]
    assert len(ids) == 2
    verdicts = {v["intent_id"]: v for v in payloads(env, "risk_verdict")}
    assert verdicts[ids[0]]["approved"]
    assert not verdicts[ids[1]]["approved"] and "TOO_SOON" in verdicts[ids[1]]["reasons"]
    st = replay(env.events())[HAIKU]
    eq = payloads(env, "equity", HAIKU)[-1]["equity_ueur"]
    assert st.positions["BTC/EUR"].cost_ueur * 10_000 <= 4000 * eq


def test_fractionnement_sans_garde_temporelle_reste_borne_par_max_position(tmp_path: Path):
    """Même sans TOO_SOON, la position cumulée (état rejoué après chaque fill) reste <= 40 %."""
    pol = replace(POLICY, min_interval_same_symbol_s=0, max_trades_per_day=10)
    st = PortfolioState("llm:test", 1_000 * MICRO)
    mkt = mk_market()
    n_ok = 0
    ex_price = None
    for k in range(5):
        v = ev(mk_intent(size_bp=2000, idx=k), st, mkt, policy=pol)
        if not v.approved:
            assert "MAX_POSITION" in v.reasons
            break
        n_ok += 1
        q = mkt.quotes[BTC]
        from arene.sim.fills import market_fill

        price, fee = market_fill(Side.BUY, v.qty, q, INSTR[BTC], FEE_BP, SLIP_BP)
        ex_price = price
        cost = -(-v.qty * price // 100_000_000) + fee
        st.cash_ueur -= cost
        pos = st.positions.get(BTC)
        if pos:
            pos.qty += v.qty
            pos.cost_ueur += cost
        else:
            st.positions[BTC] = Position(BTC, v.qty, cost, NOW)
    assert ex_price is not None and n_ok <= 2


def test_daily_trades_et_multi_symboles(env: Env):
    """2 symboles dans le même cycle = 2 trades ; au cycle suivant, tout achat est refusé (DAILY_TRADES)."""

    def plan(idx: int, snap: dict):
        if idx in (1, 2):
            return [action("BTC/EUR", size=10), action("ETH/EUR", size=10)]
        return None

    run_cycles(env, 3, deciders=deciders_for(plan))
    fills = [f for f in payloads(env, "fill", HAIKU) if f["side"] == "buy"]
    assert len(fills) == 2
    verdicts = {v["intent_id"]: v for v in payloads(env, "risk_verdict")}
    cyc2 = [i for i in payloads(env, "intent", HAIKU) if i["cycle"] == T0 + 2 * H4]
    assert cyc2 and all(not verdicts[i["intent_id"]]["approved"] for i in cyc2)
    assert all("DAILY_TRADES" in verdicts[i["intent_id"]]["reasons"] for i in cyc2)


def test_compteur_trades_non_remis_a_zero_apres_redemarrage(env: Env):
    """Les compteurs viennent du journal : un nouveau process (nouveau _Runner) voit les trades déjà faits."""

    def plan(idx: int, snap: dict):
        return [action("BTC/EUR", size=5), action("ETH/EUR", size=5)] if idx == 1 else None

    run_cycles(env, 2, deciders=deciders_for(plan))
    assert trades_last_24h(env.events(), HAIKU, T0 + 2 * H4) == 2


def test_second_achat_ne_desserre_pas_le_stop_des_lots_existants(env: Env):
    """Achat avec stop 5 % puis, 4 h plus tard, un petit achat avec stop 25 % : le stop de la position ne baisse pas."""

    def plan(idx: int, snap: dict):
        if idx == 1:
            return [action("BTC/EUR", size=10, stop=5)]
        if idx == 2:
            return [action("BTC/EUR", size=1, stop=25)]
        return None

    run_cycles(env, 3, deciders=deciders_for(plan))
    stops = [e["payload"]["stop_ueur"] for e in env.of_type("stop_set") if e["payload"]["portfolio"] == HAIKU]
    assert len(stops) == 2, stops
    assert stops[1] >= stops[0]
    assert replay(env.events())[HAIKU].positions["BTC/EUR"].stop_ueur >= stops[0]


def test_vente_hors_position_et_au_dela_refusees():
    st = PortfolioState("llm:test", 500 * MICRO, {BTC: Position(BTC, 1_000_000, 100 * MICRO, NOW)})
    assert not ev(mk_intent(Side.SELL, size_bp=10_001), st).approved
    assert not ev(mk_intent(Side.SELL, symbol="ETH/EUR", size_bp=5000), st).approved
    v = ev(mk_intent(Side.SELL, size_bp=10_000), st)
    assert v.approved and v.qty == 1_000_000


# ====================================================================== 3. injection


@pytest.mark.parametrize(
    "sym", ["btc/eur", "Btc/Eur", " BTC/EUR", "BTC/EUR ", "BTC/EUR\n", "BTC／EUR", "BTC/EUR\u200b", "DOGE/EUR", "../../etc"]
)
def test_symbole_hors_liste_ou_casse_differente_refuse(sym: str):
    raw = json.dumps({"actions": [{**action("BTC/EUR"), "symbol": sym}], "justification": "x"})
    parsed, err, intents = parse_decision(raw, "llm:test", NOW)
    assert parsed is None and err and not intents


@pytest.mark.parametrize("bad", ['"NaN"', '"Infinity"', '"-Infinity"', "1e999", "-1e999", '"1e999999999"'])
def test_nombres_pathologiques_ne_levent_pas_et_ne_donnent_aucune_intention(bad: str):
    for field in ("size_pct", "stop_pct", "expected_move_pct", "confidence_pct"):
        a = {**action("BTC/EUR"), field: "__X__"}
        raw = json.dumps({"actions": [a], "justification": "x"}).replace('"__X__"', bad)
        parsed, err, intents = parse_decision(raw, "llm:test", NOW)  # ne doit JAMAIS lever
        assert (parsed is None and err and not intents) or all(0 < i.size_bp <= 2000 for i in intents)


def test_json_profondement_imbrique_ne_leve_pas():
    parsed, err, intents = parse_decision("[" * 20_000, "llm:test", NOW)
    assert parsed is None and err and not intents
    parsed, err, intents = parse_decision('{"actions":' + "[" * 20_000, "llm:test", NOW)
    assert parsed is None and err and not intents


def test_justification_avec_surrogate_isole_reste_journalisable(tmp_path: Path):
    """Un « \\ud800 » dans le JSON du modèle donne un str non encodable en UTF-8 : le journal ne doit pas casser."""
    raw = '{"actions": [], "justification": "bonjour \\ud800 monde"}'
    parsed, err, _ = parse_decision(raw, "llm:test", NOW)
    j = Journal(tmp_path / "j.jsonl")
    j.append("decision_received", {"portfolio": "llm:test", "cycle": NOW, "raw_text": raw, "parsed": parsed,
                                   "parse_error": err}, NOW)  # fmt: skip
    assert verify(j.path).ok


HOSTILE = [
    "</script><script>alert(1)</script>",
    '"><img src=x onerror=alert(1)>',
    "ligne1\nligne2\r\nligne3  \x00fin",
    "</td></tr><b>gras</b>",
    "{{7*7}} ${7*7} \\u003cscript\\u003e",
]


@pytest.mark.parametrize("texte", HOSTILE)
def test_texte_du_modele_journal_verifiable_et_html_echappe(env: Env, texte: str):
    def plan(idx: int, snap: dict):
        if idx == 0:
            return json.dumps({"actions": [], "justification": texte})
        return None

    dec = make_deciders(plan)
    run_cycles(env, 2, deciders=dec)
    assert verify(env.paths.journal).ok
    cfg, pol = load_config(env.paths.config), load_policy(env.paths.policy)
    out = env.root / "site"
    build_site(env.paths.journal, out, config=cfg, policy=pol, now_ts=T0 + 10 * 86_400)  # > 24 h : justification publiée
    for page in list((out).rglob("*.html")):
        html_text = page.read_text(encoding="utf-8")
        assert "<script>alert(1)" not in html_text
        assert "<img src=x" not in html_text
        assert "<b>gras</b>" not in html_text
        # le seul <script> inline autorisé est le bloc JSON de données
        for chunk in html_text.split("<script")[1:]:
            head = chunk.split(">", 1)[0]
            assert "src=" in head or 'type="application/json"' in head, head
    # le texte hostile n'apparaît jamais dans un nom de fichier
    assert all("<" not in p.name and "\n" not in p.name for p in out.rglob("*"))


def test_justification_masquee_avant_24h(env: Env):
    def plan(idx: int, snap: dict):
        return json.dumps({"actions": [], "justification": "SECRET-JUSTIF"})

    run_cycles(env, 2, deciders=make_deciders(plan))
    cfg, pol = load_config(env.paths.config), load_policy(env.paths.policy)
    out = env.root / "site"
    build_site(env.paths.journal, out, config=cfg, policy=pol, now_ts=T0 + 2 * H4 + 3600)
    assert "SECRET-JUSTIF" not in "".join(p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file())


def test_parse_error_ne_fait_pas_fuiter_de_texte_non_borne(env: Env):
    """Le texte d'erreur d'un symbole invalide est tronqué à 300 caractères (pas de fuite avant 24 h)."""
    raw = json.dumps({"actions": [{**action("BTC/EUR"), "symbol": "X" * 5000}], "justification": "x"})
    _, err, _ = parse_decision(raw, "llm:test", NOW)
    assert err is not None and len(err) <= 300


# ====================================================================== 4. crash et reprise


class Boom(RuntimeError):
    pass


def test_crash_avant_equity_puis_reprise_sans_double_execution(env: Env, monkeypatch: pytest.MonkeyPatch):
    run_cycles(env, 1, deciders=deciders_for(buy_plan))
    orig = cycle_mod._Runner._equities
    state = {"n": 0}

    def boom(self):
        state["n"] += 1
        if state["n"] == 1:
            raise Boom("crash avant equity")
        return orig(self)

    monkeypatch.setattr(cycle_mod._Runner, "_equities", boom)
    dec = deciders_for(buy_plan)
    env.clock.now = env.now_of(1)
    r1 = cycle_mod.run_cycle(env.paths, env.clients, env.clock.now, deciders=dec)
    assert r1.status == "failed"
    n_fills = len(payloads(env, "fill"))
    assert n_fills > 0 and not [e for e in payloads(env, "equity") if e["cycle"] == T0 + H4]
    r2 = cycle_mod.run_cycle(env.paths, env.clients, env.clock.now, deciders=dec)
    assert r2.status == "completed" and r2.resumed
    assert len(payloads(env, "fill")) == n_fills  # aucun fill en double
    eq = [e for e in payloads(env, "equity") if e["cycle"] == T0 + H4]
    assert len(eq) == 7 and len({e["portfolio"] for e in eq}) == 7
    assert verify(env.paths.journal).ok
    replay(env.events())  # ne lève pas


def test_crash_entre_fill_et_stop_set_puis_coupe_circuit_ne_brique_pas_le_ledger(
    env: Env, monkeypatch: pytest.MonkeyPatch
):
    """Fill écrit, crash avant stop_set ; KILL posé ; à la reprise la mise à plat vend la position AVANT que
    _repair n'écrive son stop_set : un stop sur une position inexistante fait lever replay() pour toujours."""
    run_cycles(env, 1, deciders=deciders_for(buy_plan))
    orig = Journal.append
    flag = {"armed": True}

    def append(self, type, payload, ts):
        if type == "stop_set" and flag["armed"] and payload.get("portfolio") == HAIKU:
            flag["armed"] = False
            raise Boom("crash entre fill et stop_set")
        return orig(self, type, payload, ts)

    monkeypatch.setattr(Journal, "append", append)
    dec = deciders_for(buy_plan)
    env.clock.now = env.now_of(1)
    r1 = cycle_mod.run_cycle(env.paths, env.clients, env.clock.now, deciders=dec)
    assert r1.status == "failed"
    env.paths.kill.parent.mkdir(parents=True, exist_ok=True)
    env.paths.kill.touch()
    r2 = cycle_mod.run_cycle(env.paths, env.clients, env.clock.now, deciders=dec)
    try:
        st = replay(env.events())
    except LedgerError as exc:  # pragma: no cover - c'est la faille
        pytest.fail(f"ledger brique : {exc}")
    assert r2.status == "completed", r2.error
    assert HAIKU in st and not st[HAIKU].positions  # mis à plat par le coupe-circuit
    assert verify(env.paths.journal).ok


def test_verdict_approuve_avant_crash_n_execute_pas_un_achat_sous_coupe_circuit(
    env: Env, monkeypatch: pytest.MonkeyPatch
):
    """Verdict approuvé écrit, crash avant l'exécution ; l'opérateur pose KILL ; la reprise ne doit PAS acheter."""
    run_cycles(env, 1, deciders=deciders_for(buy_plan))
    orig = SimExecutor.execute
    flag = {"armed": True}

    def execute(self, intent, verdict, quote, now_ts):
        if flag["armed"] and intent.portfolio == HAIKU and intent.side == Side.BUY:
            flag["armed"] = False
            raise Boom("crash avant exécution")
        return orig(self, intent, verdict, quote, now_ts)

    monkeypatch.setattr(SimExecutor, "execute", execute)
    dec = deciders_for(buy_plan)
    env.clock.now = env.now_of(1)
    r1 = cycle_mod.run_cycle(env.paths, env.clients, env.clock.now, deciders=dec)
    assert r1.status == "failed"
    env.paths.kill.parent.mkdir(parents=True, exist_ok=True)
    env.paths.kill.touch()
    cycle_mod.run_cycle(env.paths, env.clients, env.clock.now, deciders=dec)
    buys = [f for f in payloads(env, "fill", HAIKU) if f["side"] == "buy"]
    assert not buys, "achat exécuté alors que le coupe-circuit était actif"
    assert verify(env.paths.journal).ok


def test_reference_approuvee_avant_crash_n_achete_pas_sous_coupe_circuit(env: Env, monkeypatch: pytest.MonkeyPatch):
    """Même scénario pour les témoins de référence (le panier achète au cycle 0)."""
    orig = SimExecutor.execute
    flag = {"armed": True}

    def execute(self, intent, verdict, quote, now_ts):
        if flag["armed"] and intent.portfolio == "temoin:panier" and intent.side == Side.BUY:
            flag["armed"] = False
            raise Boom("crash")
        return orig(self, intent, verdict, quote, now_ts)

    monkeypatch.setattr(SimExecutor, "execute", execute)
    env.clock.now = env.now_of(0)
    r1 = cycle_mod.run_cycle(env.paths, env.clients, env.clock.now, deciders=make_deciders())
    assert r1.status == "failed"
    env.paths.kill.parent.mkdir(parents=True, exist_ok=True)
    env.paths.kill.touch()
    cycle_mod.run_cycle(env.paths, env.clients, env.clock.now, deciders=make_deciders())
    assert not [f for f in payloads(env, "fill", "temoin:panier") if f["side"] == "buy"]


# ====================================================================== 5. P&L


def test_site_valeur_des_positions_coherente_avec_equity(env: Env):
    """cash + Σ valeur des positions affichées == equity affichée (même prix de valorisation : le bid)."""
    run_cycles(env, 6, deciders=deciders_for(buy_plan))
    cfg, pol = load_config(env.paths.config), load_policy(env.paths.policy)
    data = site_data.compute(env.paths.journal, cfg, pol, T0 + 6 * H4)
    checked = 0
    for p in data["portfolios"]:
        if not p["positions"]:
            continue
        checked += 1
        total = p["cash_ueur"] + sum(x["value_ueur"] for x in p["positions"])
        assert total == p["equity_ueur"], (p["id"], total, p["equity_ueur"])
    assert checked >= 3


def test_site_equity_egale_rejeu_du_ledger(env: Env):
    run_cycles(env, 8, deciders=deciders_for(buy_plan))
    cfg, pol = load_config(env.paths.config), load_policy(env.paths.policy)
    data = site_data.compute(env.paths.journal, cfg, pol, T0 + 8 * H4)
    st = replay(env.events())
    last = {e["portfolio"]: e for e in payloads(env, "equity") if e["cycle"] == T0 + 7 * H4}
    for p in data["portfolios"]:
        s = st[p["id"]]
        assert p["cash_ueur"] == s.cash_ueur == last[p["id"]]["cash_ueur"]
        assert p["fees_paid_ueur"] == s.fees_paid_ueur
        assert p["realized_pnl_ueur"] == s.realized_pnl_ueur
        assert p["equity_ueur"] == last[p["id"]]["equity_ueur"]
        assert s.cash_ueur + sum(x.cost_ueur for x in s.positions.values()) == p["capital_ueur"] + s.realized_pnl_ueur


def test_stop_et_sortie_forcee_paient_des_frais_et_le_ledger_reste_coherent(env: Env):
    """Krach après l'achat : le stop frappe, la sortie porte des frais > 0, l'invariant du ledger tient."""
    run_cycles(env, 2, deciders=deciders_for(buy_plan))
    env.kraken.crash("BTC/EUR", T0 + 2 * H4, 800)  # -20 %, au-delà du stop de 5 %
    run_cycles(env, 3, start=2, deciders=deciders_for(buy_plan))
    stops = [f for f in payloads(env, "fill", HAIKU) if f["reason"] == "stop"]
    assert stops and all(f["fee_ueur"] > 0 for f in stops)
    st = replay(env.events())[HAIKU]
    assert not st.positions
    assert st.cash_ueur == 1_000 * MICRO + st.realized_pnl_ueur
    assert st.realized_pnl_ueur < 0
    fees = sum(f["fee_ueur"] for f in payloads(env, "fill", HAIKU))
    assert st.fees_paid_ueur == fees


def test_arrondis_jamais_favorables_a_la_vente(tmp_path: Path):
    """Une vente partielle retire un coût arrondi vers le haut ; solder retire exactement le reste."""
    j = Journal(tmp_path / "j.jsonl")
    j.append("portfolio_opened", {"portfolio": "p", "kind": "llm", "capital_ueur": 1_000 * MICRO, "venue_mode": "paper"}, 1)
    j.append("fill", {"order_id": "a", "portfolio": "p", "symbol": BTC, "side": "buy", "qty": 3, "price_ueur": 33_333_333_333,
                      "fee_ueur": 7, "ts": 2, "venue_mode": "paper", "fill_model_version": "x", "reason": "intent"}, 2)  # fmt: skip
    s = replay(j.iter_events())["p"]
    cost0 = s.positions[BTC].cost_ueur
    j.append("fill", {"order_id": "b", "portfolio": "p", "symbol": BTC, "side": "sell", "qty": 1, "price_ueur": 33_333_333_333,
                      "fee_ueur": 5, "ts": 3, "venue_mode": "paper", "fill_model_version": "x", "reason": "intent"}, 3)  # fmt: skip
    s = replay(j.iter_events())["p"]
    removed = cost0 - s.positions[BTC].cost_ueur
    assert removed * 3 >= cost0  # >= 1/3 du coût (arrondi vers le haut)
    j.append("fill", {"order_id": "c", "portfolio": "p", "symbol": BTC, "side": "sell", "qty": 2, "price_ueur": 33_333_333_333,
                      "fee_ueur": 5, "ts": 4, "venue_mode": "paper", "fill_model_version": "x", "reason": "intent"}, 4)  # fmt: skip
    s = replay(j.iter_events())["p"]
    assert not s.positions and s.cash_ueur == 1_000 * MICRO + s.realized_pnl_ueur


# ====================================================================== 6. témoins de référence


def test_reference_qty_jamais_plus_que_le_cash():
    rng = random.Random(7)
    for _ in range(3000):
        sym = rng.choice(list(INSTR))
        mid = rng.choice([30_000, 50_000, 2_000, 1, 3, 77_777]) * MICRO // rng.choice([1, 1, 3, 1000])
        mid = max(mid, 10_000)
        q = Quote(sym, NOW, mid - mid // 2000, mid + mid // 2000)
        cash = rng.randint(0, 2_000) * MICRO + rng.randint(0, MICRO)
        held = rng.randint(0, 5_000_000)
        st = PortfolioState("temoin:panier", cash)
        if held:
            st.positions[sym] = Position(sym, held, rng.randint(1, 500) * MICRO, NOW)
        marks = {s: mid for s in INSTR}
        size = rng.choice([1, 100, 1666, 6000, 9999, 10_000, 20_000, 50_000])
        intent = Intent("x", "temoin:panier", NOW, sym, Side.BUY, size)
        qty = reference_qty(intent, st, marks, q, INSTR[sym], FEE_BP, SLIP_BP)
        if qty > 0:
            from arene.sim.fills import market_fill

            price, fee = market_fill(Side.BUY, qty, q, INSTR[sym], FEE_BP, SLIP_BP)
            total = -(-qty * price // 100_000_000) + fee
            assert total <= st.cash_ueur, (cash, size, qty, total)
            assert qty >= INSTR[sym].lot_min_qty


def test_temoins_sur_30_cycles_jamais_de_cash_negatif(env: Env):
    run_cycles(env, 30, deciders=make_deciders())
    for e in payloads(env, "equity"):
        assert e["cash_ueur"] >= 0
    replay(env.events())


# ====================================================================== 7. coupe-circuit, gel, arrêt, dormance


def has_buy(env: Env, portfolio: str, cycle: int | None = None) -> bool:
    return any(
        f["side"] == "buy" and (cycle is None or f["ts"] == cycle) for f in payloads(env, "fill", portfolio)
    )


def test_coupe_circuit_aucun_achat_meme_pour_les_temoins(env: Env):
    env.paths.kill.parent.mkdir(parents=True, exist_ok=True)
    env.paths.kill.touch()
    run_cycles(env, 4, deciders=deciders_for(lambda i, s: [action("BTC/EUR", size=10)]))
    assert not payloads(env, "fill")  # ni LLM, ni aléatoire, ni références


def test_coupe_circuit_utilisateur_hors_depot(env: Env):
    env.paths.user_kill.touch()
    run_cycles(env, 2, deciders=deciders_for(lambda i, s: [action("BTC/EUR", size=10)]))
    assert not [f for f in payloads(env, "fill") if f["side"] == "buy"]


def test_dormance_7_jours_plus_d_achat_et_9_jours_mise_a_plat(env: Env):
    from arene.ops import dormance

    run_cycles(env, 3, deciders=deciders_for(lambda i, s: [action("BTC/EUR", size=10)] if i == 1 else None))
    assert has_buy(env, HAIKU)
    dormance.write_ack(env.paths, T0)  # dernier ack très ancien
    i8 = (8 * 86_400) // H4
    run_cycles(env, 1, start=i8, deciders=deciders_for(lambda i, s: [action("ETH/EUR", size=10)]))
    assert not has_buy(env, HAIKU, T0 + i8 * H4)
    i10 = (10 * 86_400) // H4
    run_cycles(env, 1, start=i10, deciders=deciders_for(lambda i, s: [action("ETH/EUR", size=10)]))
    st = replay(env.events())
    assert not st[HAIKU].positions


def test_gel_et_arret_bloquent_les_achats_riskd():
    st = PortfolioState("llm:test", 1_000 * MICRO)
    assert "FROZEN" in ev(mk_intent(), replace(st, frozen_until_ts=NOW + 10)).reasons
    assert "HALTED" in ev(mk_intent(), replace(st, halted=True)).reasons
    assert "KILL_SWITCH" in ev(mk_intent(), st, kill=True).reasons
    # perte 24 h >= 5 % détectée même si le drapeau d'état manque
    c = mk_counters(equity_24h_ago_ueur=1_100 * MICRO)
    assert "FROZEN" in ev(mk_intent(), st, counters=c).reasons
    # drawdown >= 20 % depuis le plus haut
    c = mk_counters(equity_peak_ueur=1_300 * MICRO, equity_24h_ago_ueur=1_000 * MICRO)
    assert "HALTED" in ev(mk_intent(), st, counters=c).reasons


def test_vente_permise_sous_gel_arret_et_coupe_circuit():
    st = PortfolioState("llm:test", 500 * MICRO, {BTC: Position(BTC, 1_000_000, 100 * MICRO, NOW)}, halted=True,
                        frozen_until_ts=NOW + 99)  # fmt: skip
    assert ev(mk_intent(Side.SELL, size_bp=10_000), st, kill=True).approved


def test_portefeuille_gele_llm_ne_decide_pas_et_n_achete_pas(env: Env):
    """Krach de 30 % juste après un achat de 20 % : perte >= 5 % sur 24 h, gel, décision sautée, aucun achat."""
    run_cycles(env, 2, deciders=deciders_for(lambda i, s: [action("BTC/EUR", size=20)] if i == 1 else None))
    env.kraken.crash("*", T0 + H4, 700)  # la barre du cycle 1 clôt à -30 %
    dec = deciders_for(lambda i, s: [action("ETH/EUR", size=10)])
    run_cycles(env, 2, start=2, deciders=dec)
    assert payloads(env, "portfolio_frozen", HAIKU) or payloads(env, "portfolio_halted", HAIKU)
    assert not [f for f in payloads(env, "fill", HAIKU) if f["side"] == "buy" and f["ts"] >= T0 + 2 * H4]
    reasons = {s["reason"] for s in payloads(env, "decision_skipped", HAIKU)}
    assert reasons & {"frozen", "halted"}
