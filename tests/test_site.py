"""Tests du générateur de dashboard (arene/site) sur un journal synthétique de 60 cycles."""

from __future__ import annotations

import dataclasses
import html
import json
import re
from pathlib import Path
from unittest import mock

import pytest

from arene.config import load_config
from arene.journal import Journal
from arene.ledger import equity_ueur, replay
from arene.risk.policy import load_policy
from arene.site import build
from arene.types import QTY_SCALE, ceil_div, notional_ueur

ROOT = Path(__file__).resolve().parent.parent
CYCLE_S = 14_400
T0 = 1_789_000_000 - (1_789_000_000 % CYCLE_S)
N_CYCLES = 60
SYMBOLS = ["BTC/EUR", "ETH/EUR", "SOL/EUR", "XRP/EUR", "LINK/EUR", "LTC/EUR"]
BASE_PX = {"BTC/EUR": 80_000, "ETH/EUR": 3_000, "SOL/EUR": 150, "XRP/EUR": 2, "LINK/EUR": 15, "LTC/EUR": 90}
LLMS = ["llm:claude-haiku-5-5", "llm:claude-sonnet-5-5", "llm:claude-opus-5-5"]
TEMOINS = ["temoin:panier", "temoin:6040", "temoin:e0065", "temoin:aleatoire"]
CAPITAL = 1_000_000_000
INJECTION = "ancien <script>alert('x')</script> & <b>gras</b>"
SECRET_RECENT = "SECRET_RECENT_42"
NOW = T0 + (N_CYCLES - 1) * CYCLE_S + 3_600  # 1 h après le dernier cycle


def _mid(sym: str, i: int) -> tuple[int, int]:
    drift = 1_000_000 * BASE_PX[sym] * (1000 + ((i * 7 + len(sym) * 3) % 23) - 11 + i // 5) // 1000
    return drift - drift // 2000, drift + drift // 2000  # bid, ask


def _fill(j: Journal, pf: str, sym: str, side: str, qty: int, price: int, ts: int, oid: str, reason="intent"):
    notional = notional_ueur(qty, price, round_up=True)
    fee = ceil_div(notional * 50, 10_000)
    j.append("fill", {"order_id": oid, "portfolio": pf, "symbol": sym, "side": side, "qty": qty,
                      "price_ueur": price, "fee_ueur": fee, "ts": ts, "venue_mode": "paper",
                      "fill_model_version": "pessimiste-v1", "reason": reason}, ts)  # fmt: skip


def _intent(j: Journal, pf: str, cyc: int, sym: str, side: str, size_bp: int, iid: str, ts: int, approved=True,
            reasons=(), qty=0):
    j.append("intent", {"intent_id": iid, "portfolio": pf, "cycle": cyc, "symbol": sym, "side": side,
                        "size_bp": size_bp, "stop_bp": 500 if side == "buy" else None,
                        "expected_move_bp": 900 if side == "buy" else None}, ts)  # fmt: skip
    j.append("risk_verdict", {"intent_id": iid, "approved": approved, "reasons": list(reasons), "qty": qty,
                              "reserved_ueur": 0, "policy_sha256": "p"}, ts)  # fmt: skip


FABLE = "llm:claude-fable-5-2"
FABLE_DEBUT = 40  # cycle d'ouverture du cinquième modèle, arrivé en cours de route
FABLE_RAISON = "RAISON_FABLE : le momentum du bitcoin justifie une petite position"


REVEIL_CYCLE = 50  # le réveil a lieu 2 h après ce cycle
REVEIL_RAISON = "REVEIL_RAISON : l'ether décroche, j'achète la baisse"
SAISON_A = 40  # cycle de début de la saison synthétique
DEROGATION = "DEROGATION_TEST : correctif d'un prix aberrant"
XRP_BRUT_ABSURDE = 987_654_321  # quote brut rejeté : ne doit jamais devenir un prix affiché
LINK_REVEIL_ABSURDE = 777_777_777_777  # quote_reveil : ignoré pour les marks


def synthetic_journal(path: Path, avec_fable: bool = False, veille: bool = False, saison_a: int | None = None) -> Journal:
    with mock.patch("arene.journal.os.fsync"):  # 3 000 écritures : sans fsync le test reste rapide
        return _synthetic_journal(path, avec_fable, veille, saison_a)


def _bids(i: int) -> dict[str, int]:
    return {s: _mid(s, i)[0] for s in SYMBOLS}


def _veille(j: Journal, tick: int, i: int, *, bruts: dict | None = None, rejets: dict | None = None, hausse: int = 0,
            reveil: dict | None = None) -> None:
    states = replay(j.iter_events())
    q = {s: list(_mid(s, i)) for s in SYMBOLS}
    if hausse:
        q = {s: [b * (10_000 + hausse) // 10_000, a * (10_000 + hausse) // 10_000] for s, (b, a) in q.items()}
    bids = {s: b for s, (b, _a) in q.items()}
    acceptes = {s: v for s, v in q.items() if s not in (rejets or {})}
    j.append("veille", {
        "tick": tick, "quotes": acceptes, "quotes_bruts": {**q, **(bruts or {})}, "rejets": rejets or {},
        "confirmes": [], "variations_bp": {s: 0 for s in SYMBOLS}, "clotures_1m": {s: (b + a) // 2 for s, (b, a) in q.items()},
        "equity": {pf: equity_ueur(st, bids) for pf, st in states.items()}, "stops": [], "reveil": reveil,
        "refus": None, "gel": False,
    }, tick)  # fmt: skip


def _synthetic_journal(path: Path, avec_fable: bool = False, veille: bool = False, saison_a: int | None = None) -> Journal:
    j = Journal(path)
    j.append("config_loaded", {"policy_sha256": "a" * 64, "config_sha256": "b" * 64, "prompt_sha256": "c" * 64,
                               "git_head": "d" * 40}, T0 - 600)  # fmt: skip
    for pf in LLMS + TEMOINS:
        j.append("portfolio_opened", {"portfolio": pf, "kind": "llm" if pf.startswith("llm") else "temoin",
                                      "capital_ueur": CAPITAL, "venue_mode": "paper"}, T0 - 500)  # fmt: skip
    for i in range(N_CYCLES):
        c = T0 + i * CYCLE_S
        ts = c + 300
        j.append("cycle_started", {"cycle": c}, c)
        if saison_a is not None and i == saison_a:
            states = replay(j.iter_events())
            j.append("saison_debut", {"numero": 1, "nom": "Saison test", "cycle": c, "fin_prevue_cycle": c + 56 * 86_400,
                                      "debut_ts": c + 300, "duree_jours": 56, "config_sha256": "b" * 64,
                                      "policy_sha256": "a" * 64, "prompt_sha256": "c" * 64, "code_sha256": "e" * 64,
                                      "git_head": "d" * 40, "claude_cli_version": None,
                                      "portefeuilles": LLMS + TEMOINS}, c + 2)  # fmt: skip
            j.append("saison_reference", {"numero": 1, "cycle": c, "equity": {
                pf: equity_ueur(states[pf], _bids(i)) for pf in LLMS + TEMOINS}}, c + 3)  # fmt: skip
        if saison_a is not None and i == saison_a + 2:
            h = {"config_sha256": "b" * 64, "policy_sha256": "a" * 64, "prompt_sha256": "c" * 64, "code_sha256": "e" * 64}
            j.append("saison_derogation", {"numero": 1, "raison": DEROGATION, "hashes_avant": h,
                                           "hashes_apres": {**h, "code_sha256": "f" * 64}}, c + 2)  # fmt: skip
        if avec_fable and i == FABLE_DEBUT:
            j.append("portfolio_opened", {"portfolio": FABLE, "kind": "llm", "capital_ueur": CAPITAL,
                                          "venue_mode": "paper"}, c + 1)  # fmt: skip
        for sym in SYMBOLS:
            bid, ask = _mid(sym, i)
            j.append("quote", {"symbol": sym, "ts": ts, "bid": bid, "ask": ask}, ts)
            lo, hi = _mid(sym, i - 1)[0], _mid(sym, i)[1]
            j.append("bar", {"symbol": sym, "interval_s": CYCLE_S, "ts": c - CYCLE_S, "open": lo, "high": hi + 1,
                             "low": lo - 1, "close": (bid + ask) // 2, "volume": 100 * QTY_SCALE}, ts)  # fmt: skip
        px_btc = _mid("BTC/EUR", i)[1] * 10_005 // 10_000
        qty100 = 100_000_000 * QTY_SCALE // px_btc  # ~100 EUR de BTC
        # Témoins : panier et 60/40 achètent au cycle 0.
        if i == 0:
            for k, sym in enumerate(SYMBOLS):
                px = _mid(sym, i)[1] * 10_005 // 10_000
                q = 150_000_000 * QTY_SCALE // px
                _intent(j, "temoin:panier", c, sym, "buy", 1666, f"pan{k}", ts, qty=q)
                _fill(j, "temoin:panier", sym, "buy", q, px, ts, f"pan{k}")
            _intent(j, "temoin:6040", c, "BTC/EUR", "buy", 6000, "p6040", ts, qty=qty100)
            _fill(j, "temoin:6040", "BTC/EUR", "buy", qty100 * 6, px_btc, ts, "p6040")
        # Sonnet : achat cycle 3, rejet cycle 5, vente cycle 10, justification ancienne cycle 7, récente au dernier cycle.
        pf = "llm:claude-sonnet-5-5"
        parsed = None
        if i == 3:
            _intent(j, pf, c, "BTC/EUR", "buy", 1000, "s3", ts, qty=qty100)
            _fill(j, pf, "BTC/EUR", "buy", qty100, px_btc, ts, "s3")
            j.append("stop_set", {"portfolio": pf, "symbol": "BTC/EUR", "stop_ueur": px_btc * 95 // 100}, ts)
            parsed = {"actions": [{"symbol": "BTC/EUR", "side": "buy"}], "justification": "j'ai acheté du bitcoin"}
        elif i == 5:
            _intent(j, pf, c, "ETH/EUR", "buy", 2500, "s5", ts, approved=False, reasons=["MAX_ORDER_SIZE"])
            parsed = {"actions": [{"symbol": "ETH/EUR", "side": "buy"}], "justification": "trop gros"}
        elif i == 7:
            parsed = {"actions": [], "justification": INJECTION}
        elif i == 10:
            pos = replay(j.iter_events())[pf].positions["BTC/EUR"]
            px = _mid("BTC/EUR", i)[0] * 9_995 // 10_000
            _intent(j, pf, c, "BTC/EUR", "sell", 10_000, "s10", ts, qty=pos.qty)
            _fill(j, pf, "BTC/EUR", "sell", pos.qty, px, ts, "s10")
            parsed = {"actions": [{"symbol": "BTC/EUR", "side": "sell"}], "justification": "prise de profit"}
        elif i == N_CYCLES - 1:
            parsed = {"actions": [], "justification": SECRET_RECENT}
        else:
            parsed = {"actions": [], "justification": "rien à faire"}
        j.append("decision_received", {"portfolio": pf, "cycle": c, "model_requested": "claude-sonnet-5-5",
                                       "model_returned": "claude-sonnet-5-5", "raw_text": json.dumps(parsed),
                                       "parsed": parsed, "parse_error": None, "input_tokens": 3000,
                                       "output_tokens": 300, "cost_uusd": 9_000, "latency_ms": 900}, ts)  # fmt: skip
        j.append("decision_skipped", {"portfolio": LLMS[0], "cycle": c, "reason": "no_key"}, ts)
        j.append("decision_received", {"portfolio": LLMS[2], "cycle": c, "model_requested": "claude-opus-5-5",
                                       "model_returned": "claude-opus-5-5", "raw_text": "{}",
                                       "parsed": {"actions": [], "justification": "attendre"}, "parse_error": None,
                                       "input_tokens": 3000, "output_tokens": 200, "cost_uusd": 16_000,
                                       "latency_ms": 1200}, ts)  # fmt: skip
        if avec_fable and i >= FABLE_DEBUT:
            fp = {"actions": [], "justification": "attendre encore"}
            if i == FABLE_DEBUT + 5:
                _intent(j, FABLE, c, "BTC/EUR", "buy", 1000, "f45", ts, qty=qty100)
                _fill(j, FABLE, "BTC/EUR", "buy", qty100, px_btc, ts, "f45")
                fp = {"actions": [{"symbol": "BTC/EUR", "side": "buy"}], "justification": FABLE_RAISON}
            j.append("decision_received", {"portfolio": FABLE, "cycle": c, "model_requested": "claude-fable-5-2",
                                           "model_returned": "claude-fable-5-2", "raw_text": json.dumps(fp),
                                           "parsed": fp, "parse_error": None, "input_tokens": 3000,
                                           "output_tokens": 300, "cost_uusd": 110_000, "latency_ms": 900}, ts)  # fmt: skip
        events = list(j.iter_events())
        states = replay(events)
        marks = {s: sum(_mid(s, i)) // 2 for s in SYMBOLS}
        for p in LLMS + TEMOINS + ([FABLE] if avec_fable and i >= FABLE_DEBUT else []):
            st = states[p]
            j.append("equity", {"portfolio": p, "cycle": c, "cash_ueur": st.cash_ueur,
                                "positions_value_ueur": equity_ueur(st, marks) - st.cash_ueur,
                                "equity_ueur": equity_ueur(st, marks)}, ts + 5)  # fmt: skip
        j.append("cycle_completed", {"cycle": c}, ts + 10)
        if veille and i == REVEIL_CYCLE:
            _reveil(j, c, i)
        if veille and i == N_CYCLES - 1:
            _veille(j, c + 1800, i)
            # Stop de la veille sur l'ETH acheté au réveil, puis un dernier relevé (equity vivante) avec un XRP brut absurde.
            pf = "llm:claude-sonnet-5-5"
            pos = replay(j.iter_events())[pf].positions["ETH/EUR"]
            tick = c + 2400
            _fill(j, pf, "ETH/EUR", "sell", pos.qty, _mid("ETH/EUR", i)[0] * 99 // 100, tick,
                  f"stop:{pf}:ETH/EUR:veille:{tick}", reason="stop")
            _veille(j, tick, i, hausse=100, bruts={"XRP/EUR": [XRP_BRUT_ABSURDE, XRP_BRUT_ABSURDE + 10]},
                    rejets={"XRP/EUR": "saut"})
    return j


def _reveil(j: Journal, c: int, i: int) -> None:
    """Réveil 2 h après le cycle `c` : Sonnet achète de l'ETH ; LTC n'a pas de quote au réveil."""
    r = c + 7200
    decl = {"type": "mouvement", "symbole": "ETH/EUR", "variation_bp": -340, "fenetre_s": 3600}
    _veille(j, c + 1800, i)
    j.append("reveil_started", {"reveil": r, "declencheur": decl}, r + 31)
    _veille(j, r, i, reveil=decl)
    for sym in SYMBOLS:
        if sym == "LTC/EUR":
            continue
        bid, ask = _mid(sym, i)
        if sym == "LINK/EUR":
            bid, ask = LINK_REVEIL_ABSURDE, LINK_REVEIL_ABSURDE + 10
        j.append("quote_reveil", {"symbol": sym, "ts": r, "bid": bid, "ask": ask}, r + 32)
    pf = "llm:claude-sonnet-5-5"
    px = _mid("ETH/EUR", i)[1] * 10_005 // 10_000
    q = 100_000_000 * QTY_SCALE // px
    _intent(j, pf, r, "ETH/EUR", "buy", 1000, "rv1", r + 40, qty=q)
    _fill(j, pf, "ETH/EUR", "buy", q, px, r + 40, "rv1")
    parsed = {"actions": [{"symbol": "ETH/EUR", "side": "buy"}], "justification": REVEIL_RAISON}
    j.append("decision_received", {"portfolio": pf, "cycle": r, "model_requested": "claude-sonnet-5-5",
                                   "model_returned": "claude-sonnet-5-5", "raw_text": json.dumps(parsed),
                                   "parsed": parsed, "parse_error": None, "input_tokens": 3000,
                                   "output_tokens": 300, "cost_uusd": 9_000, "latency_ms": 900}, r + 39)  # fmt: skip
    j.append("reveil_completed", {"reveil": r}, r + 60)


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> tuple[Path, Journal]:
    tmp = tmp_path_factory.mktemp("site")
    j = synthetic_journal(tmp / "events.jsonl")
    cfg = load_config(ROOT / "config" / "arene.toml")
    cfg = dataclasses.replace(cfg, temoins=dataclasses.replace(cfg.temoins, aleatoire_trajectoires=60))
    policy = load_policy(ROOT / "config" / "policy.toml")
    out = tmp / "site"
    build(j.path, out, config=cfg, policy=policy, now_ts=NOW)
    return out, j


def read(site, rel: str) -> str:
    return (site[0] / rel).read_text(encoding="utf-8")


def test_fichiers_presents(site):
    out, _ = site
    for rel in ["index.html", "methode.html", "vendor/uPlot.iife.min.js", "vendor/uPlot.min.css",
                "vendor/SHA256SUMS", "data/summary.json", "data/equity.json", "data/method.json"]:  # fmt: skip
        assert (out / rel).is_file(), rel
    for pf in LLMS + TEMOINS:
        slug = re.sub(r"[^a-z0-9]+", "-", pf).strip("-")
        assert (out / "modele" / f"{slug}.html").is_file()
        assert (out / "data" / f"modele-{slug}.json").is_file()


def test_venue_mode_dans_chaque_json(site):
    out, _ = site
    files = sorted((out / "data").glob("*.json"))
    assert len(files) >= 10
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d.get("venue_mode") == "paper", f.name


def test_bandeau_simule_partout(site):
    out, _ = site
    for f in out.rglob("*.html"):
        txt = f.read_text(encoding="utf-8")
        assert "Simulation\u202f: argent fictif, aucun ordre réel" in txt, f.name
        assert "ARGENT RÉEL" not in txt, f.name


def test_bandeau_argent_reel_si_venue_live():
    from arene.site.render import layout

    data = {"portfolios": [], "venue_mode": "live", "generated_ts": T0,
            "journal": {"n_records": 1, "head_hash": "a" * 64}}  # fmt: skip
    page = layout(title="t", body="", root="", active="index", data=data)
    assert "ARGENT RÉEL" in page and "venue_mode" in page
    assert "Simulation\u202f: argent fictif, aucun ordre réel" not in page


def test_csp_stricte_et_aucun_style_inline(site):
    out, _ = site
    for f in out.rglob("*.html"):
        txt = f.read_text(encoding="utf-8")
        assert "'unsafe-inline'" not in txt, f.name
        assert "style-src 'self'" in txt, f.name
        assert not re.search(r"\sstyle\s*=", txt), f.name  # la CSP bloquerait tout attribut style


def test_modele_sans_decision_ni_rang_ni_cout(site):
    """Un modèle dont toutes les décisions ont été sautées n'affiche ni rang ni coût : il n'a rien décidé."""
    index = read(site, "index.html")
    ligne = re.search(r'<tr class="llm inactif">.*?</tr>', index, re.DOTALL)
    assert ligne and "Claude Haiku 5.5" in ligne.group(0)
    assert "n’a jamais décidé" in ligne.group(0) and "sans décision" in ligne.group(0) and "aucun appel" in ligne.group(0)
    haiku = read(site, "modele/llm-claude-haiku-5-5.html")
    assert "Ce modèle n’a encore jamais décidé" in haiku
    sonnet = read(site, "modele/llm-claude-sonnet-5-5.html")
    assert "jamais décidé" not in sonnet


def test_formats_francais():
    from arene.site.render import eur, typo_fr

    assert eur(1_000_000_000, decimals=0) == "1\u202f000\u00a0€"
    assert eur(-1_234_567) == "\u22121,23\u00a0€"
    assert typo_fr("<p>a : b ; « c »</p><code>x : y</code>") == "<p>a\u202f: b\u202f; «\u202fc\u202f»</p><code>x : y</code>"


def test_justification_publiee_des_la_decision(site):
    """Décision du propriétaire (12/11/2026) : plus de délai de 24 h, la justification la plus récente est publiée."""
    page = read(site, "modele/llm-claude-sonnet-5-5.html")
    assert SECRET_RECENT in page  # décision prise 1 h avant la construction
    assert "prise de profit" in page
    assert "après la décision" not in page and "masquee" not in page
    assert "après la décision" not in read(site, "methode.html")


def test_decision_avec_ordres_montre_le_raisonnement_a_cote_des_ordres(site):
    page = read(site, "modele/llm-claude-sonnet-5-5.html")
    # la vente du cycle 10 : carte dépliée, raisonnement puis ordres dans le même bloc, jamais dans un <details>
    i = page.index("prise de profit")
    carte = page[page.rindex('<li class="decision">', 0, i) : page.index("</li>", i)]
    assert '<div class="decision-corps"><blockquote class="justif">' in carte
    assert "Raisonnement du modèle" in carte and '<div class="decision-ordres">' in carte
    assert "<details" not in carte
    assert carte.index("prise de profit") < carte.index("tableau actions")
    assert '<span class="resume-ordres">Vente BTC/EUR</span>' in carte
    # un ordre refusé garde aussi son raisonnement à côté
    j = page.index("</span>trop gros</blockquote>")
    refus = page[page.rindex('<li class="decision">', 0, j) : page.index("</li>", j)]
    assert "decision-corps" in refus and "MAX_ORDER_SIZE" in refus
    # sur mobile (cartes empilées), le verdict sans chiffre reste visible : seules les cellules « — » sont masquées
    assert re.search(r'<td data-label="Contrôle de risque"(?! data-vide)[^>]*><span class="pastille perte-bg">refusé', refus)
    assert re.search(r'<td data-label="Contrôle de risque"(?! data-vide)[^>]*><span class="pastille ok">accepté', carte)
    # une décision « ne rien faire » reste repliée
    k = page.index("rien à faire")
    assert "<details>" in page[page.rindex('<li class="ligne">', 0, k) : k]


@pytest.fixture(scope="module")
def site_fable(tmp_path_factory) -> tuple[Path, Journal]:
    tmp = tmp_path_factory.mktemp("site_fable")
    j = synthetic_journal(tmp / "events.jsonl", avec_fable=True)
    cfg = load_config(ROOT / "config" / "arene.toml")
    cfg = dataclasses.replace(cfg, temoins=dataclasses.replace(cfg.temoins, aleatoire_trajectoires=20))
    out = tmp / "site"
    build(j.path, out, config=cfg, policy=load_policy(ROOT / "config" / "policy.toml"), now_ts=NOW)
    return out, j


def test_cinquieme_modele_arrive_en_cours_de_route(site_fable):
    from arene.site.render import COULEUR_LLM, _styles

    assert COULEUR_LLM[FABLE] == 3
    out, _ = site_fable
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "quatre modèles d’ia" in index.lower()  # méta-description dérivée du journal
    assert "Claude Fable 5.2" in index and "depuis le" in index
    # courbe : pas de point à 100 avant son ouverture (spanGaps relierait sinon le départ à son premier point)
    chart = json.loads((out / "data" / "equity.json").read_text(encoding="utf-8"))
    k = [s["id"] for s in chart["series"]].index(FABLE)
    vals = chart["series"][k]["values"]
    assert all(v is None for v in vals[: FABLE_DEBUT + 1]) and vals[FABLE_DEBUT + 1] is not None
    assert _styles(chart, None)[k]["color"] == "--llm3"
    page = (out / "modele" / "llm-claude-fable-5-2.html").read_text(encoding="utf-8")
    assert "Entré dans l’arène le" in page and "arrivé en cours" in page
    assert FABLE_RAISON in page and "Achat BTC/EUR" in page
    p = json.loads((out / "data" / "modele-llm-claude-fable-5-2.json").read_text(encoding="utf-8"))
    assert p["late"] is True and p["rank_percentile"] is None
    assert p["n_cycles"] == N_CYCLES - FABLE_DEBUT
    # les autres gardent leur rang et leur point de départ à 100
    autres = json.loads((out / "data" / "modele-llm-claude-sonnet-5-5.json").read_text(encoding="utf-8"))
    assert autres["late"] is False and autres["rank_percentile"] is not None
    assert chart["series"][0]["values"][0] == 100.0
    methode = (out / "methode.html").read_text(encoding="utf-8")
    assert "Quatre modèles d’IA (Claude Haiku 5.5, Sonnet 5.5, Opus 5.5 et Fable 5.2)" in methode
    assert "Claude Fable 5.2 est entré dans l’arène le" in methode


def test_injection_html_echappee(site):
    out, _ = site
    for f in out.rglob("*.html"):
        txt = f.read_text(encoding="utf-8")
        assert "<script>alert" not in txt
        assert "<b>gras</b>" not in txt
    page = read(site, "modele/llm-claude-sonnet-5-5.html")
    assert html.escape(INJECTION, quote=True) in page


def test_rejet_riskd_en_clair_et_sauts_comptes(site):
    sonnet = read(site, "modele/llm-claude-sonnet-5-5.html")
    assert "MAX_ORDER_SIZE" in sonnet and "ordre trop gros" in sonnet and "refusé" in sonnet
    haiku = read(site, "modele/llm-claude-haiku-5-5.html")
    assert "sautée" in haiku and "modèle pas encore branché" in haiku
    summary = json.loads(read(site, "data/summary.json"))
    h = next(p for p in summary["portfolios"] if p["id"] == "llm:claude-haiku-5-5")
    assert h["skipped"] == {"no_key": N_CYCLES}


def test_chiffres_du_tableau_egaux_au_rejeu(site):
    _out, j = site
    states = replay(j.iter_events())
    marks = {s: sum(_mid(s, N_CYCLES - 1)) // 2 for s in SYMBOLS}
    summary = json.loads(read(site, "data/summary.json"))
    assert len(summary["portfolios"]) == 7
    for p in summary["portfolios"]:
        st = states[p["id"]]
        assert p["equity_ueur"] == equity_ueur(st, marks)
        assert p["fees_paid_ueur"] == st.fees_paid_ueur
    index = read(site, "index.html")
    from arene.site.render import eur

    for st in states.values():
        assert eur(equity_ueur(st, marks)) in index
        page = read(site, f"modele/{st.portfolio.replace(':', '-')}.html")
        assert eur(st.fees_paid_ueur) in page  # les frais sont sur la page du portefeuille


def test_non_distinguable_du_hasard(site):
    index = read(site, "index.html")
    assert "non distinguable du hasard" in index
    summary = json.loads(read(site, "data/summary.json"))
    assert summary["any_llm_distinguishable"] is False
    sonnet = next(p for p in summary["portfolios"] if p["id"] == "llm:claude-sonnet-5-5")
    assert sonnet["sharpe"] is not None and len(sonnet["sharpe_ci"]) == 2  # 60 cycles >= 30
    assert sonnet["rank_percentile"] is not None
    assert sonnet["api_cost_uusd"] == 9_000 * N_CYCLES


def test_trop_tot_sous_30_cycles(tmp_path):
    cfg = load_config(ROOT / "config" / "arene.toml")
    cfg = dataclasses.replace(cfg, temoins=dataclasses.replace(cfg.temoins, aleatoire_trajectoires=5))
    j = Journal(tmp_path / "e.jsonl")
    j.append("portfolio_opened", {"portfolio": "llm:claude-sonnet-5-5", "kind": "llm", "capital_ueur": CAPITAL,
                                  "venue_mode": "paper"}, T0)  # fmt: skip
    for i in range(3):
        j.append("equity", {"portfolio": "llm:claude-sonnet-5-5", "cycle": T0 + i * CYCLE_S, "cash_ueur": CAPITAL,
                            "positions_value_ueur": 0, "equity_ueur": CAPITAL}, T0 + i * CYCLE_S)  # fmt: skip
    build(j.path, tmp_path / "s", config=cfg, policy=load_policy(ROOT / "config" / "policy.toml"), now_ts=T0 + 10**6)
    index = (tmp_path / "s" / "index.html").read_text(encoding="utf-8")
    assert "trop tôt" in index.lower()


def test_aucune_url_externe(site):
    out, _ = site
    pattern = re.compile(r"""(?:src|href|action)\s*=\s*["']\s*(?:https?:)?//""", re.IGNORECASE)
    for f in out.rglob("*.html"):
        txt = f.read_text(encoding="utf-8")
        if f.name != "methode.html":
            assert not re.search(r"https?://", txt), f.name
        assert not pattern.search(txt), f.name
    assert "https://" not in (out / "assets" / "site.css").read_text()
    assert "@import" not in (out / "vendor" / "uPlot.min.css").read_text()


def test_methode_contient_hash_de_tete_et_verify(site):
    _out, j = site
    page = read(site, "methode.html")
    head = j.verify().head_hash
    assert head in page
    assert "chaîne intacte" in page
    assert "pas un conseil en investissement" in page
    assert "c" * 64 in page  # hash du prompt


def test_reconstruction_atomique_ecrase_proprement(site, tmp_path):
    _out, j = site
    cfg = load_config(ROOT / "config" / "arene.toml")
    cfg = dataclasses.replace(cfg, temoins=dataclasses.replace(cfg.temoins, aleatoire_trajectoires=5))
    dest = tmp_path / "var" / "site"
    pol = load_policy(ROOT / "config" / "policy.toml")
    build(j.path, dest, config=cfg, policy=pol, now_ts=NOW)
    (dest / "reste.txt").write_text("x")
    build(j.path, dest, config=cfg, policy=pol, now_ts=NOW)
    assert not (dest / "reste.txt").exists()
    assert [p.name for p in dest.parent.iterdir()] == ["site"]  # aucun dossier temporaire résiduel


def test_couleur_stable_d_une_page_a_l_autre():
    """Opus garde sa couleur sur sa page, même quand le graphique n'affiche que lui et le panier."""
    from arene.site.render import _styles

    serie = lambda i, k: {"id": i, "kind": k, "name": i, "values": [100.0]}
    seul = {"x": [0], "series": [serie("llm:claude-opus-5-5", "llm"), serie("temoin:panier", "temoin")]}
    assert _styles(seul, None)[0]["color"] == "--llm2"


def test_pas_de_courbe_sous_trois_cycles(tmp_path):
    cfg = load_config(ROOT / "config" / "arene.toml")
    cfg = dataclasses.replace(cfg, temoins=dataclasses.replace(cfg.temoins, aleatoire_trajectoires=5))
    j = Journal(tmp_path / "e.jsonl")
    j.append("portfolio_opened", {"portfolio": "temoin:panier", "kind": "temoin", "capital_ueur": CAPITAL,
                                  "venue_mode": "paper"}, T0)  # fmt: skip
    j.append("equity", {"portfolio": "temoin:panier", "cycle": T0, "cash_ueur": CAPITAL,
                        "positions_value_ueur": 0, "equity_ueur": CAPITAL}, T0)  # fmt: skip
    build(j.path, tmp_path / "s", config=cfg, policy=load_policy(ROOT / "config" / "policy.toml"), now_ts=T0 + 3600)
    index = (tmp_path / "s" / "index.html").read_text(encoding="utf-8")
    assert "Courbe à partir de 3" in index
    assert "chart.js" not in index


def test_version_publique_sans_texte_operateur_avec_404(site, tmp_path):
    out_prive, j = site
    cfg = load_config(ROOT / "config" / "arene.toml")
    cfg = dataclasses.replace(cfg, temoins=dataclasses.replace(cfg.temoins, aleatoire_trajectoires=60))
    out = tmp_path / "public"
    build(j.path, out, config=cfg, policy=load_policy(ROOT / "config" / "policy.toml"), now_ts=NOW, public=True, racine="/arene/")
    index = (out / "index.html").read_text(encoding="utf-8")
    assert 'class="a-faire' not in index
    assert "RUNBOOK" not in index and ".config/arene" not in index
    page404 = (out / "404.html").read_text(encoding="utf-8")
    assert 'href="/arene/assets/site.css"' in page404 and "Cette page n’existe pas" in page404
    assert not (out_prive / "404.html").exists()  # sans racine, pas de 404 (le site privé n'en a pas besoin)
    # Épuré : pas de gros titre visible ; le h1 reste pour les lecteurs d'écran.
    assert '<h1 class="visuellement-cache">' in index


def test_modele_configure_pas_encore_ouvert(site):
    """Fable est dans la config mais pas dans ce journal : Méthode compte comme l'accueil et l'annonce à part."""
    methode = read(site, "methode.html")
    assert "Trois modèles d’IA (Claude Haiku 5.5, Sonnet 5.5 et Opus 5.5)" in methode
    assert "Claude Fable 5.2 rejoindra l’arène au prochain cycle." in methode
    assert "Trois modèles d’IA" in read(site, "index.html")  # méta-description et h1


# --------------------------------------------------------------------------- veille, réveils, saison


def _cfg(n: int = 60):
    cfg = load_config(ROOT / "config" / "arene.toml")
    return dataclasses.replace(cfg, temoins=dataclasses.replace(cfg.temoins, aleatoire_trajectoires=n))


@pytest.fixture(scope="module")
def veille_site(tmp_path_factory):
    from arene.site.data import compute

    tmp = tmp_path_factory.mktemp("veille")
    j = synthetic_journal(tmp / "events.jsonl", veille=True)
    pol = load_policy(ROOT / "config" / "policy.toml")
    with mock.patch.dict("os.environ", {"ARENE_SITE_CACHE": ""}):
        data = compute(j.path, _cfg(), pol, now_ts=NOW)
        build(j.path, tmp / "site", config=_cfg(), policy=pol, now_ts=NOW)
    return tmp / "site", j, data


def test_equity_vivante_lue_dans_la_veille(veille_site):
    out, j, data = veille_site
    veilles = [e["payload"] for e in j.iter_events() if e["type"] == "veille"]
    dernier = veilles[-1]
    assert data["live"]["ts"] == dernier["tick"]
    for p in data["portfolios"]:
        assert p["equity_ueur"] == dernier["equity"][p["id"]] and p["equity_live"]
        assert p["total_return"] == pytest.approx(dernier["equity"][p["id"]] / CAPITAL - 1)
    assert data["chart"]["kinds"][-1] == "veille" and data["chart"]["x"][-1] == dernier["tick"]
    assert data["chart"]["x"] == sorted(set(data["chart"]["x"]))  # strictement croissant
    assert data["n_cycles"] == N_CYCLES  # ni les relevés ni le réveil ne sont des cycles
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "Valeurs en direct" in index and "Dernier réveil" in index and "ETH −3,4" in index
    assert ">En direct\u202f: " in index and "jusqu’après" not in index


def test_quotes_bruts_et_quote_reveil_jamais_affiches_comme_prix(veille_site):
    from arene.site.render import eur, prix

    out, _j, data = veille_site
    marks = {x["symbol"]: x["mark_ueur"] for p in data["portfolios"] for x in p["positions"]}
    assert marks["XRP/EUR"] != XRP_BRUT_ABSURDE and marks["LINK/EUR"] != LINK_REVEIL_ABSURDE
    for f in out.rglob("*.html"):
        txt = f.read_text(encoding="utf-8")
        for absurde in (XRP_BRUT_ABSURDE, LINK_REVEIL_ABSURDE):
            assert str(absurde) not in txt and prix(absurde) not in txt and eur(absurde) not in txt, f.name


def test_decision_de_reveil_avec_son_declencheur_et_stop_de_veille(veille_site):
    out, _j, data = veille_site
    sonnet = next(p for p in data["portfolios"] if p["id"] == "llm:claude-sonnet-5-5")
    r = T0 + REVEIL_CYCLE * CYCLE_S + 7200
    d = next(d for d in sonnet["decisions"] if d["cycle"] == r)
    assert d["ronde"] == "reveil" and d["declencheur"]["symbole"] == "ETH/EUR" and d["actions"][0]["fills"]
    stop = next(d for d in sonnet["decisions"] if d["kind"] == "stop_veille")
    assert stop["sorties"][0]["reason"] == "stop" and ":veille:" in stop["sorties"][0]["order_id"]
    page = (out / "modele" / "llm-claude-sonnet-5-5.html").read_text(encoding="utf-8")
    assert "réveil · ETH −3,4\u00a0% en 1\u00a0h" in page
    assert html.escape(REVEIL_RAISON, quote=True) in page
    assert "Vente sur stop, détectée par la veille" in page


def test_trajectoires_rejouent_les_reveils_completes(veille_site):
    from arene.site.data import _cycle_data, _reveils

    _out, j, _data = veille_site
    events = list(j.iter_events())
    rondes = _cycle_data(events, CYCLE_S, _reveils(events))
    r = T0 + REVEIL_CYCLE * CYCLE_S + 7200
    rv = next(x.data for x in rondes if x.data.ts == r and x.reveil)
    assert set(rv.quotes) == set(SYMBOLS) - {"LTC/EUR"}  # seuls les symboles cotés au réveil sont négociables
    assert "LTC/EUR" in rv.marks and not rv.bars
    assert len(rondes) == N_CYCLES + 1
    assert [x.data.ts for x in rondes] == sorted(x.data.ts for x in rondes)
    # Un réveil abandonné n'est pas rejoué.
    sans = _cycle_data(events, CYCLE_S, {r: {"statut": "abandonne"}})
    assert all(x.data.ts != r for x in sans)


def test_rejeu_du_hasard_identique_au_moteur_sans_reveil(site):
    """Sans réveil, le rejeu du site rend exactement les nombres du simulateur du moteur (garde-fou de dérive)."""
    from arene.site.data import _cycle_data, _instruments
    from arene.site.hasard import trajectoires
    from arene.temoins.trajectoires import simulate_random_trajectories

    _out, j = site
    events = list(j.iter_events())
    rondes = _cycle_data(events, CYCLE_S, {})
    cfg, pol = _cfg(), load_policy(ROOT / "config" / "policy.toml")
    kw = {"policy": pol, "instruments": _instruments(cfg), "fee_bp": cfg.taker_fee_bp,
          "slippage_bp": cfg.slippage_bp, "capital_ueur": CAPITAL}  # fmt: skip
    assert trajectoires(rondes, 25, **kw) == simulate_random_trajectories([r.data for r in rondes], 25, **kw)


def test_rejeu_du_hasard_avec_reveil_sans_quote_ne_tombe_pas(veille_site):
    """Au réveil, un symbole sans quote n'est pas négociable (le simulateur du moteur levait KeyError)."""
    from arene.site.data import _cycle_data, _instruments, _reveils
    from arene.site.hasard import trajectoires

    _out, j, data = veille_site
    events = list(j.iter_events())
    cfg, pol = _cfg(), load_policy(ROOT / "config" / "policy.toml")
    finals = trajectoires(_cycle_data(events, CYCLE_S, _reveils(events)), 200, policy=pol,
                          instruments=_instruments(cfg), fee_bp=cfg.taker_fee_bp, slippage_bp=cfg.slippage_bp,
                          capital_ueur=CAPITAL)  # fmt: skip
    assert len(finals) == 200 and data["distribution"] is not None and data["distribution_note"] is None


def test_cache_des_trajectoires(tmp_path, veille_site):
    from arene.site.data import compute

    _out, j, data = veille_site
    pol = load_policy(ROOT / "config" / "policy.toml")
    with mock.patch.dict("os.environ", {"ARENE_SITE_CACHE": str(tmp_path / "cache")}):
        a = compute(j.path, _cfg(), pol, now_ts=NOW)
        assert (tmp_path / "cache" / "trajectoires.json").is_file()
        with mock.patch("arene.site.data.trajectoires_depuis", side_effect=AssertionError("recalcul")):
            b = compute(j.path, _cfg(), pol, now_ts=NOW)
    assert a["distribution"] == b["distribution"] == data["distribution"]


@pytest.fixture(scope="module")
def saison_site(tmp_path_factory):
    from arene.site.data import compute

    tmp = tmp_path_factory.mktemp("saison")
    j = synthetic_journal(tmp / "events.jsonl", saison_a=SAISON_A)
    pol = load_policy(ROOT / "config" / "policy.toml")
    with mock.patch.dict("os.environ", {"ARENE_SITE_CACHE": ""}):
        data = compute(j.path, _cfg(), pol, now_ts=NOW)
        build(j.path, tmp / "site", config=_cfg(), policy=pol, now_ts=NOW)
    return tmp / "site", j, data


def test_saison_classe_depuis_la_reference(saison_site):
    out, j, data = saison_site
    ref = next(e["payload"] for e in j.iter_events() if e["type"] == "saison_reference")
    c0 = T0 + SAISON_A * CYCLE_S
    assert data["saison"]["statut"] == "ouverte" and data["saison"]["cycle"] == c0
    assert data["n_cycles"] == N_CYCLES - SAISON_A
    for p in data["portfolios"]:
        assert p["base_ueur"] == ref["equity"][p["id"]]
        assert p["total_return"] == pytest.approx(p["equity_ueur"] / ref["equity"][p["id"]] - 1)
        assert not p["late"] and p["rank_percentile"] is not None
    assert data["chart"]["x"][0] == c0 - 1 and data["chart"]["kinds"][0] == "depart"
    assert all(s["values"][0] == 100.0 for s in data["chart"]["series"])
    assert all(x >= c0 - 1 for x in data["chart"]["x"])  # le rodage n'est pas sur la courbe
    rod = {r["id"]: r["total_return"] for r in data["rodage"]["portfolios"]}
    assert rod["temoin:panier"] == pytest.approx(ref["equity"]["temoin:panier"] / CAPITAL - 1)
    assert data["rodage"]["n_cycles"] == SAISON_A
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "Saison test" in index and "jour " in index and "Rodage, hors classement" in index
    assert "depuis le début de la saison" in index
    assert html.escape(DEROGATION.split(" : ")[1], quote=True) in index
    methode = (out / "methode.html").read_text(encoding="utf-8")
    assert html.escape(DEROGATION.split(" : ")[1], quote=True) in methode and "(code)" in methode


def test_saison_prevue_annoncee_avant_son_debut(site):
    index = read(site, "index.html")
    assert "Saison 1" in index and "rodage en cours, hors classement" in index


def test_stop_sur_barre_ignore_une_barre_commencee_avant_un_achat_au_reveil():
    """Un achat au réveil (09:35) n'est pas stoppé par le plus bas d'une barre ouverte à 08:00 (garde du moteur)."""
    from arene.site.data import _instruments
    from arene.site.hasard import Ronde, trajectoires
    from arene.temoins import aleatoire
    from arene.temoins.trajectoires import CycleData
    from arene.types import Bar, Quote, Side

    cfg, pol = _cfg(), load_policy(ROOT / "config" / "policy.toml")
    c0, r, c1 = T0, T0 + 7200, T0 + CYCLE_S
    bid, ask = _mid("BTC/EUR", 0)
    mid = (bid + ask) // 2
    q = {"BTC/EUR": Quote("BTC/EUR", c0, bid, ask)}
    barre = Bar("BTC/EUR", CYCLE_S, c0, mid, mid, mid // 2, mid, 100 * QTY_SCALE)  # plus bas à -50 %, AVANT l'achat

    def decide(ts, state, marks, context):
        if ts != r:
            return []
        return [aleatoire.make_intent(aleatoire.PORTFOLIO, ts, 0, "BTC/EUR", Side.BUY, 1000, stop_bp=500,
                                      expected_move_bp=900)]  # fmt: skip

    rondes = [
        Ronde(CycleData(c0, q, {"BTC/EUR": mid}, {"BTC/EUR": mid}, {})),
        Ronde(CycleData(r, {"BTC/EUR": Quote("BTC/EUR", r, bid, ask)}, {"BTC/EUR": mid}, {"BTC/EUR": mid}, {}), True),
        Ronde(CycleData(c1, {"BTC/EUR": Quote("BTC/EUR", c1, bid, ask)}, {"BTC/EUR": mid}, {"BTC/EUR": mid},
                        {"BTC/EUR": [barre]})),
    ]
    with mock.patch("arene.site.hasard.aleatoire.decide", side_effect=decide):
        [final] = trajectoires(rondes, 1, policy=pol, instruments={"BTC/EUR": _instruments(cfg)["BTC/EUR"]},
                               fee_bp=cfg.taker_fee_bp, slippage_bp=cfg.slippage_bp, capital_ueur=CAPITAL)  # fmt: skip
    assert final > CAPITAL * 0.99  # la position est toujours là (un stop aurait coûté 5 % de 10 %, plus les frais)


def test_raison_de_derogation_filtree_en_public():
    from arene.site.render import raison_derogation

    assert raison_derogation({"public": False}, "voir /srv/x/notes") == "voir /srv/x/notes"
    assert raison_derogation({"public": True}, "voir /srv/x/notes") == "raison consignée dans le journal"
    assert raison_derogation({"public": True}, "contact a@b.fr") == "raison consignée dans le journal"
    assert raison_derogation({"public": True}, "correctif d’un prix aberrant") == "correctif d’un prix aberrant"
