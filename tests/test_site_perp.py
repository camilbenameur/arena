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


# --- Alertes et ordres d'entrée des agents (docs/SPEC-PERP-ALERTES-ORDRES.md) ---


def _fable(site):
    d = P.compute(Path(site).parent / "var-perp" / "journal" / "events.jsonl", NOW)
    return next(p for p in d["portfolios"] if p["id"] == F.LLMS[3])


def test_ordre_d_entree_declenche_garde_son_verdict_et_son_fill(site):
    fable = _fable(site)
    ordre = [d for d in fable["decisions"] if d["kind"] == "ordre"]
    assert len(ordre) == 1
    a = ordre[0]["actions"][0]
    assert a["action"] == "open_long" and a["instrument"] == "SOL"
    assert a["verdict"] == {"approuve": True, "motifs": []} and a["execution"] == "filled" and len(a["fills"]) == 1
    assert a["invalidation"] == F.INVAL_ORDRE and a["stop_pct"] == 4
    # La décision précédente (fermer ETH) garde son seul verdict et son seul fill.
    ferme = next(d for d in fable["decisions"] if d["kind"] == "rendezvous" and d["actions"] and d["actions"][0]["action"] == "close")
    assert len(ferme["actions"]) == 1 and len(ferme["actions"][0]["fills"]) == 1
    assert fable["n_ordres"] == 3  # short ETH, fermeture, ordre SOL


def test_en_attente_et_historique(site):
    at = _fable(site)["attente"]
    assert [(x["instrument"], x["condition"], x["note"]) for x in at["alertes"]] == [("ETH", "below", "support hebdomadaire")]
    assert at["ordres"] == []
    issues = {(x["type"], x["instrument"]): (x["issue"], x.get("issue_detail")) for x in at["historique"]}
    assert issues[("alerte", "BTC")] == ("declenche", None)
    assert issues[("ordre", "SOL")] == ("declenche", "exécuté")
    assert issues[("alerte", "LTC")] == ("fin", "expiré")


def test_page_montre_reveil_prive_pose_et_attente(site):
    t = texte(lire(site, "derives/llm-perp-claude-fable-5-2.html"))
    assert "En attente" in t and "support hebdomadaire" in t
    assert "son alerte · BTC au-dessus de 89 540,50 $" in t
    assert "ordre d’entrée · SOL sous" in t
    assert "A laissé pour la suite" in t and F.NOTE_ALERTE in t and F.INVAL_ORDRE in t
    assert "refusé à la création : niveau à plus de 25 % du prix" in t
    assert "away from the mark" not in t  # le texte technique du refus ne sort pas
    # Haiku n'a rien laissé : seul son prochain appel régulier est en attente.
    att = re.search(r'<section aria-labelledby="titre-attente">(.*?)</section>', lire(site, "derives/llm-perp-claude-haiku-5-5.html")).group(1)
    assert "Appel régulier" in texte(att) and "<strong>Alerte</strong>" not in att and "<strong>Ordre" not in att
    assert "Entre deux rendez-vous" in texte(lire(site, "methode.html"))


def test_prix_en_direct_estimation_cote_navigateur(site):
    """Demande du propriétaire du 14/11 : prix à quelques secondes. Le navigateur lit le flux public de Kraken et
    revalorise les positions publiées ; la CSP n'ouvre ce flux que sur les pages dérivés qui en ont besoin."""
    import json

    from arene.site.render import CSP, CSP_DIRECT

    idx = lire(site, "index.html")
    assert f'content="{CSP_DIRECT}"' in idx and "connect-src wss://futures.kraken.com" in CSP_DIRECT
    assert (site / "assets" / "direct.js").exists() and 'assets/direct.js"></script>' in idx
    data = json.loads(re.search(r'<script id="direct-data" type="application/json">(.*?)</script>', idx).group(1))
    assert data["flux"] == "wss://futures.kraken.com/ws/v1"
    assert set(data["produits"]) <= set(P.PRODUITS) and data["produits"]
    for slug, pf in data["pf"].items():
        assert f'data-direct="rend" data-pf="{slug}"' in idx and f'data-direct="val" data-pf="{slug}"' in idx
        assert len(pf["fx"]) == 2 and pf["pos"]
        for x in pf["pos"]:
            assert set(x) == {"p", "q", "e", "l"} and x["q"] != 0
    # Rien du journal au-delà des chiffres publiés (ni id d'ordre, ni portefeuille brut).
    assert "llm-perp:" not in json.dumps(data) and "intent" not in json.dumps(data)
    assert 'data-direct-etat data-court hidden' in idx and "<span data-direct-mot>" in idx
    # Page d'un portefeuille avec positions : prix actuel et latent revalorisés, état sous « Positions ».
    pages = {f.name: f.read_text(encoding="utf-8") for f in (site / "derives").glob("*.html")}
    avec = [n for n, h in pages.items() if 'data-direct="mark"' in h]
    assert avec, "aucune page de portefeuille revalorisée en direct"
    for n, h in pages.items():
        if n in avec:
            assert 'data-direct="lat"' in h and '<p class="direct-etat" data-direct-etat hidden></p>' in h
            assert f'content="{CSP_DIRECT}"' in h and "direct.js" in h
        else:  # sans position : ni script, ni connexion
            assert f'content="{CSP}"' in h and "direct.js" not in h
    # La courbe reste celle du journal : son dernier point est un relevé, pas « en direct ».
    assert '"dernier":"Dernier relevé"' in idx
    # Le comptant et la méthode n'ouvrent aucune connexion.
    for nom_page in ("comptant.html", "methode.html"):
        html = lire(site, nom_page)
        assert f'content="{CSP}"' in html and "direct.js" not in html


def test_appels_reguliers_groupes_rappel_et_quota(site):
    """Rondes `cadence` et `scheduled` (≈ 6 par heure) : pastille discrète, suites sans ordre repliées en une ligne,
    rappel demandé en attente, appels du jour face au plafond (docs/COORDINATION-dashboard.md, 13 et 14/11)."""
    page = lire(site, f"derives/{P.slug(F.LLMS[1])}.html")
    t = texte(page)
    assert '<span class="pastille discret">appel régulier</span>' in page
    assert '<span class="pastille neutre">à sa demande</span>' in page
    groupe = re.search(r'<li class="ligne groupe-calme"><details><summary>(.*?)</summary>', page)
    assert groupe and "4 décisions sans ordre" in texte(groupe.group(1))
    # Le rappel demandé (encore à venir) est en attente, et dans ce qu'elle a laissé à chaque décision.
    assert "Rappel qu’elle a demandé" in t and "Rappel demandé pour" in t
    assert "réveil demandé invalide" in t and F.SECRET not in page
    assert "appels aujourd’hui," in t and "Appel régulier" in t and "au plus tard à" in t
    meth = texte(lire(site, "methode.html"))
    assert "Appel régulier" in meth and "Rappel demandé" in meth and "2 % en 1 h" in meth.replace(" ", " ")
