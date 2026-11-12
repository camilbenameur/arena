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


def synthetic_journal(path: Path, avec_fable: bool = False) -> Journal:
    with mock.patch("arene.journal.os.fsync"):  # 3 000 écritures : sans fsync le test reste rapide
        return _synthetic_journal(path, avec_fable)


def _synthetic_journal(path: Path, avec_fable: bool = False) -> Journal:
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
    return j


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
    assert "Quatre IA gèrent chacune" in index
    assert "quatre modèles d’ia" in index.lower()  # méta-description dérivée du journal
    assert "Claude Fable 5.2" in index and "Entré dans l’arène le" in index
    # courbe : pas de point à 100 avant son ouverture (spanGaps relierait sinon le départ à son premier point)
    chart = json.loads((out / "data" / "equity.json").read_text(encoding="utf-8"))
    k = [s["id"] for s in chart["series"]].index(FABLE)
    vals = chart["series"][k]["values"]
    assert all(v is None for v in vals[: FABLE_DEBUT + 1]) and vals[FABLE_DEBUT + 1] is not None
    assert _styles(chart, None)[k]["color"] == "--llm3"
    page = (out / "modele" / "llm-claude-fable-5-2.html").read_text(encoding="utf-8")
    assert "Entré dans l’arène le" in page and "arrivé en cours de route" in page
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
        assert eur(st.fees_paid_ueur) in index


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


def test_version_publique_sans_texte_operateur_avec_404_et_frise(site, tmp_path):
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
    # Frise : chaque cycle affiché porte le préfixe de l'empreinte de son événement cycle_completed.
    hashes = [e["hash"][:8] for e in j.iter_events(strict=False) if e["type"] == "cycle_completed"]
    assert hashes and all(h in index for h in hashes[-6:])
    assert f"Cycle {len(hashes) + 1}" in index  # le prochain cycle, à venir


def test_modele_configure_pas_encore_ouvert(site):
    """Fable est dans la config mais pas dans ce journal : Méthode compte comme l'accueil et l'annonce à part."""
    methode = read(site, "methode.html")
    assert "Trois modèles d’IA (Claude Haiku 5.5, Sonnet 5.5 et Opus 5.5)" in methode
    assert "Claude Fable 5.2 rejoindra l’arène au prochain cycle." in methode
    assert "Trois IA gèrent chacune" in read(site, "index.html")
