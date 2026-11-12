"""Site : ligue dérivés au premier plan, ligue comptant en second (docs/COORDINATION-dashboard.md, 12/11, 21 h 30)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import perp_fixture as F
from test_site import ROOT, synthetic_journal
from test_site import _cfg as _config

from arene.journal import Journal
from arene.risk.policy import load_policy
from arene.site import build
from arene.site import perp as P


def _cfg():
    return _config(), load_policy(ROOT / "config" / "policy.toml")

NOW = F.T0 + 2 * 86_400 + 100


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("perp")
    spot = synthetic_journal(tmp / "var" / "journal" / "events.jsonl")
    perp = F.build(tmp / "var-perp" / "journal" / "events.jsonl")
    out = tmp / "site"
    config, policy = _cfg()
    build(spot.path, out, config=config,
          policy=policy, now_ts=NOW, public=True, racine="/arene/", perp_journal=perp)  # fmt: skip
    return out


def lire(site: Path, nom: str) -> str:
    return (site / nom).read_text(encoding="utf-8")


def texte(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_derives_au_premier_plan_et_comptant_en_second(site):
    idx = lire(site, "index.html")
    assert "<title>Ligue dérivés" in idx
    assert 'href="comptant.html"' in idx and (site / "comptant.html").exists()
    assert "Ligue comptant" in lire(site, "comptant.html")
    for pf in F.LLMS + F.TEMOINS:
        assert (site / "derives" / f"{P.slug(pf)}.html").exists()
    # Les pages modèles du comptant ramènent au comptant, plus à l'accueil.
    page = next((site / "modele").iterdir()).read_text(encoding="utf-8")
    assert 'href="../comptant.html"' in page


def test_rien_de_prive_ne_sort(site):
    for f in site.rglob("*"):
        if f.suffix in (".html", ".json"):
            t = f.read_text(encoding="utf-8")
            for interdit in ("/home/", "var-perp/rounds", "2.1.99", "bougies-secret", "stderr", "Traceback", "the host", "cli_version",
                             "tools_offered", "llm_config_sha256", "message_sha256"):  # fmt: skip
                assert interdit not in t, (f.name, interdit)


def test_publication_le_verificateur_ne_bloque_pas(site):
    sys.path.insert(0, str(Path(__file__).parent.parent / "ops"))
    import publier

    assert publier.verifier(site) == []


def test_decision_complete_justification_invalidation_outils_verdict_execution(site):
    t = texte(lire(site, "derives/llm-perp-claude-fable-5-2.html"))
    assert F.FABLE_RAISON.split(":")[0] in t
    assert "Invalide si" in t and "3 300 $" in t
    assert "A consulté indicateurs ETH 4h, funding ETH" in t
    assert "accepté" in t and "vente" in t and "Ferme ETH" in t


def test_refus_du_garde_fou_en_clair(site):
    t = texte(lire(site, "derives/llm-perp-claude-opus-5-5.html"))
    assert "refusé" in t
    assert "coûts trop grands face au mouvement attendu" in t
    assert "EDGE_TOO_SMALL" not in t  # le code brut reste dans le JSON, pas dans la page


def test_reveil_saut_et_echec(site):
    assert "réveil · SOL" in texte(lire(site, "derives/llm-perp-claude-opus-5-5.html"))
    t = texte(lire(site, "derives/llm-perp-claude-haiku-5-5.html"))
    assert "budget du jour atteint" in t
    assert "réponse illisible" in t


def test_positions_sens_stop_objectif_et_gel(site):
    t = texte(lire(site, "derives/llm-perp-claude-opus-5-5.html"))
    assert "long" in t and "Stop" in t and "Objectif" in t
    assert "gelé" in t
    tr = texte(lire(site, "derives/benchmark-perp-trend.html"))
    assert "short" in tr and "long" in tr


def test_chiffres_coherents_avec_le_dernier_releve(site):
    events = list(Journal(Path(site).parent / "var-perp" / "journal" / "events.jsonl").iter_events())
    last = {}
    for e in events:
        if e["type"] == "perp_equity":
            last[e["payload"]["portfolio"]] = e["payload"]
    d = P.compute(Path(site).parent / "var-perp" / "journal" / "events.jsonl", NOW)
    for p in d["portfolios"]:
        le = last[p["id"]]
        assert p["equity_ueur"] == le["equity_ueur"]
        assert p["levier"] == pytest.approx(le["gross_ueur"] / le["equity_ueur"])
    fable = next(p for p in d["portfolios"] if p["id"] == F.LLMS[3])
    funding = [e["payload"]["amount_ueur"] for e in events if e["type"] == "funding" and e["payload"]["portfolio"] == F.LLMS[3]]
    assert fable["funding_net_ueur"] == sum(funding)


def test_methode_explique_la_ligue(site):
    t = texte(lire(site, "methode.html"))
    assert "La ligue dérivés" in t and "Ce que l’IA peut consulter" in t and "La ligue comptant" in t


def test_sans_ia_encore_les_temoins_seuls(tmp_path):
    j = Journal(tmp_path / "events.jsonl")
    for pf in F.TEMOINS:
        j.append("portfolio_opened", {"portfolio": pf, "kind": "benchmark", "league": "perp", "capital_ueur": 1_000_000_000,
                                      "venue_mode": "paper"}, F.T0)  # fmt: skip
    d = P.compute(tmp_path / "events.jsonl", F.T0 + 600)
    assert d and not d["llm_presents"] and len(d["portfolios"]) == 3


def test_sans_journal_derives_le_site_reste_celui_du_comptant(tmp_path):
    spot = tmp_path / "var" / "journal" / "events.jsonl"
    synthetic_journal(spot)
    config, policy = _cfg()
    build(spot, tmp_path / "site", config=config, policy=policy, now_ts=NOW, perp_journal=tmp_path / "absent.jsonl")
    assert not (tmp_path / "site" / "comptant.html").exists()
    assert "Vue d’ensemble" in (tmp_path / "site" / "index.html").read_text(encoding="utf-8")


def test_court():
    assert [P.court(x) for x in ("PF_XBTUSD", "BTC-PERP", "PF_LINKUSD", "XRP-PERP")] == ["BTC", "BTC", "LINK", "XRP"]


def _mini(tmp_path, actions, errors, tool_args, statut="filled"):
    j = Journal(tmp_path / "events.jsonl")
    pf = F.LLMS[0]
    j.append("portfolio_opened", {"portfolio": pf, "kind": "llm", "league": "perp", "capital_ueur": 1_000_000_000, "venue_mode": "paper"}, F.T0)
    j.append("tool_call", {"portfolio": pf, "round": F.T0, "n": 1, "tool": "simuler_ordre", "arguments": tool_args,
                           "response": "{}", "response_sha256": "0" * 64, "is_error": False}, F.T0)  # fmt: skip
    j.append("agent_decision", {"portfolio": pf, "round": F.T0, "kind": "rendezvous", "model_requested": "x",
                                "parsed": {"actions": actions, "justification": "j", "action_errors": errors},
                                "parse_error": None, "cost_uusd": 10}, F.T0)  # fmt: skip
    j.append("perp_verdict", {"intent_id": "i0", "portfolio": pf, "instrument": "PF_XBTUSD", "action": "open_long",
                              "approved": True, "reasons": [], "qty": 1000, "policy_sha256": "0", "error": None}, F.T0)  # fmt: skip
    j.append("perp_execution", {"intent_id": "i0", "portfolio": pf, "instrument": "PF_XBTUSD", "status": statut, "error": None}, F.T0)
    return P.compute(tmp_path / "events.jsonl", F.T0 + 60)["portfolios"][0]["decisions"][0]


def test_action_ecartee_ne_vole_pas_le_verdict_de_l_action_valide(tmp_path):
    a = {"instrument": "PF_XBTUSD", "action": "open_long", "size_pct": "10", "stop_pct": "2"}
    d = _mini(tmp_path, [a], [{"k": 0, "error": "bad"}], '{"action": ["x"], "instrument": {"a": 1}}')
    valide, ecartee = d["actions"]
    assert valide["verdict"] == {"approuve": True, "motifs": []} and valide["execution"] == "filled"
    assert ecartee["ecartee"] and ecartee["action"] is None
    assert d["outils"] == [{"outil": "simuler_ordre", "args": "", "erreur": False}]  # arguments absurdes : ni plantage ni texte


def test_statut_d_execution_montre_meme_avec_fills(tmp_path):
    from arene.site.render_perp import _execution

    a = {"instrument": "BTC", "execution": "closed_without_stop", "fills": [{"qty": 10, "prix_uusd": 1_000_000, "frais_ueur": 1}]}
    assert "position refermée" in _execution(a)
