"""Site : ligue dérivés au premier plan, ligue comptant en second (docs/COORDINATION-dashboard.md, 12/11, 21 h 30)."""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import perp_fixture as F
from test_site import ROOT, synthetic_journal
from test_site import _cfg as _config

from arene.journal import Journal
from arene.perp.news import CalendarEvent
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


def test_accueil_des_trois_ligues_puis_une_page_par_ligue(site):
    """Décision du propriétaire du 15/11 : l'accueil présente les trois ligues ; les IA seules (dérivés) passent sur derives.html."""
    acc = lire(site, "index.html")
    for page in ("conseils.html", "derives.html", "comptant.html"):
        assert f'href="{page}"' in acc and (site / page).exists()
    assert acc.count('class="ligue-carte"') == 3 and 'class="scores mini"' in acc
    idx = lire(site, "derives.html")
    assert "<title>Ligue des IA seules" in idx
    assert 'href="comptant.html"' in idx
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
    assert "accepté" in t and "vente" in t and "Ferme son pari sur l’ether" in t


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

    idx = lire(site, "derives.html")
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


# ---------------------------------------------------------------------------
# Ligue des conseils : Conseil Haiku et Conseil Opus, hors de la ligue dérivés (demande du propriétaire du 15/11)
# ---------------------------------------------------------------------------


def _n(s: str) -> str:
    """Sans espaces (fines, insécables, normales) ni apostrophes courbes : la typographie française du site."""
    return re.sub(r"[\s\u00a0\u202f]+", "", html.unescape(s)).replace("\u2019", "'")


def _ligne_tableau(idx: str, nom: str) -> str:
    return next(r for r in re.findall(r"<tr[^>]*>.*?</tr>", idx, flags=re.DOTALL) if f">{nom}</a>" in r)


def _perp(site: Path):
    return P.compute(Path(site).parent / "var-perp" / "journal" / "events.jsonl", NOW)


def test_derives_sans_les_conseils(site):
    d = _perp(site)
    assert [p["kind"] for p in d["portfolios"]] == ["llm"] * 4 + ["temoin"] * 3
    assert not any(s["kind"] == "conseil" for s in d["chart"]["series"])
    idx = lire(site, "derives.html")
    assert "Conseil" not in texte(re.search(r"<tbody.*</table>", idx, flags=re.DOTALL).group(0))
    comparatif = re.search(r'<table class="tableau comparatif.*?</table>', idx, flags=re.DOTALL).group(0)
    assert len(re.findall(r"<tbody[^>]*>.*?</tbody>", comparatif, flags=re.DOTALL)) == 2  # IA, témoins
    classement = texte(re.search(r'<ol class="scores".*?</ol>', idx, flags=re.DOTALL).group(0))
    assert "Claude" in classement and "Conseil" not in classement and "Témoin sans IA" in classement
    assert "trait--conseil" not in idx and "Agressif" not in idx and "un conseil agressif" not in texte(idx)
    for nom in ("council-perp-haiku", "council-perp-opus"):
        assert not (site / "derives" / f"{nom}.html").exists()
    dj = lire(site, "data/derives.json")
    assert "council-perp" not in dj and "Conseil" not in dj
    # La landing renvoie vers l'autre ligue, à côté du lien Comptant.
    assert 'href="conseils.html"' in idx and "ligue des conseils" in texte(idx)


def test_ligue_des_conseils_tableau_classement_et_navigation(site):
    d = _perp(site)["conseils"]
    assert [(p["id"], p["kind"]) for p in d["portfolios"]] == [(F.CONSEIL, "conseil"), (F.OPUS, "conseil"), (F.TEMOINS[0], "temoin")]
    assert {p["id"]: p["name"] for p in d["portfolios"]} == {F.CONSEIL: "Conseil Haiku", F.OPUS: "Conseil Opus", F.TEMOINS[0]: "Témoin panier 1x"}
    assert [s["id"] for s in d["chart"]["series"]] == [p["id"] for p in d["portfolios"]]
    page = lire(site, "conseils.html")
    t = texte(page)
    assert "Haiku ou Opus à la présidence" in page and "Seul leur président change" in t
    comparatif = re.search(r'<table class="tableau comparatif.*?</table>', page, flags=re.DOTALL).group(0)
    corps = re.findall(r"<tbody[^>]*>.*?</tbody>", comparatif, flags=re.DOTALL)
    assert len(corps) == 2 and "Conseil Haiku" in corps[0] and "Conseil Opus" in corps[0] and "Témoin panier 1x" in corps[1]
    assert P.MARQUE_CONSEIL in texte(corps[0])
    assert "10 Haiku · président Haiku" in texte(_ligne_tableau(page, "Conseil Haiku"))
    assert "10 Haiku · président Opus" in texte(_ligne_tableau(page, "Conseil Opus"))
    assert "hors règle 2x" in texte(_ligne_tableau(page, "Conseil Opus"))
    assert 'href="conseils/council-perp-opus.html"' in page and 'href="derives/benchmark-perp-basket-1x.html"' in page
    assert "Claude Haiku 5.5" not in "".join(corps) and "Témoin tendance" not in t  # ni les IA ni les autres témoins
    # L'expérience en une phrase, puis le classement et la courbe aux deux teintes, la navigation et le prix en direct.
    assert "Dix conseillers Claude Haiku" in t and "Haiku pour l’un, Opus pour l’autre" in t
    assert "trait--conseil" in page and "trait--conseil2" in page and "c--conseil2" in page
    classement = texte(re.search(r'<ol class="scores".*?</ol>', page, flags=re.DOTALL).group(0))
    assert "Conseil Haiku" in classement and "Conseil Opus" in classement and "Témoin sans IA" in classement
    assert re.search(r'<nav class="nav"[^>]*>.*?<a href="conseils.html" aria-current="page">Conseils</a>', page, flags=re.DOTALL)
    assert 'id="direct-data"' in page and "council-perp-opus" in re.search(r'<script id="direct-data"[^>]*>(.*?)</script>', page).group(1)
    # Les autres pages du site la proposent aussi.
    assert 'href="conseils.html"' in lire(site, "comptant.html") and 'href="conseils.html"' in lire(site, "methode.html")
    cj = json.loads(lire(site, "data/conseils.json"))
    assert cj["venue_mode"] == "paper" and {p["id"] for p in cj["portfolios"]} == {F.CONSEIL, F.OPUS, F.TEMOINS[0]}


def test_conseil_haiku_page_ancienne_et_nouvelle_ronde(site):
    html_ = lire(site, "conseils/council-perp-haiku.html")
    t = texte(html_)
    assert P.MARQUE_CONSEIL in t and "ne pourrait pas passer au réel telle quelle" in t and "10 Haiku · président Haiku" in t
    assert _n("objectif 2 000 €") in _n(t)
    assert "Ligue des conseils" in t and "conseils.html#m-conseils" in html_
    # Deux rondes repliées : l'ancienne à 8 avis (7 rendus + 1 absent, aucun Arbitragiste), la récente à 9 (Arbitragiste).
    assert html_.count('class="deliberation"') == 2
    assert _n("8 avis · 1 absent") in _n(t) and _n("9 avis · 1 absent") in _n(t)
    assert _n("Étape A · 7 avis indépendants") in _n(t) and _n("Étape A · 8 avis indépendants") in _n(t)  # absents déduits
    assert "L’Arbitragiste de paires" in t and _n(F.ARG_ARBITRAGE) in _n(t)
    assert t.count("L’Arbitragiste de paires") == 1  # un seul : l'ancienne ronde n'en avait pas
    # Président Haiku : champ absent des anciennes décisions, présent dans la récente ; consignes v1 puis v2.
    assert t.count("Président · Haiku") >= 3 and "Président · Opus" not in t
    assert "consignes v1" in t and "consignes v2" in t and "Conseillers Haiku" in t
    # Coût réel de la ronde (sans nombre d'appels codé en dur), jamais « 10 appels ».
    assert "10 appels" not in t and "coût réel des rondes" in t and "dont Président" not in t
    assert "OSError" not in html_


def test_conseil_opus_page_modele_du_president_et_cout_a_part(site):
    html_ = lire(site, "conseils/council-perp-opus.html")
    t = texte(html_)
    assert "Conseil Opus" in t and "10 Haiku · président Opus" in t and P.MARQUE_CONSEIL in t
    assert 'class="tete-modele teinte-2"' in html_ and 'class="teinte-2"' in html_
    assert _n("Étape C · le Président tranche Président · Opus") in _n(t)
    assert _n("9 avis · 1 absent") in _n(t) and _n("Étape A · 8 avis indépendants") in _n(t)
    assert "L’Arbitragiste de paires" in t and "consignes v2" in t
    # Le Président pèse l'essentiel : son coût est montré à part, par ronde et au total.
    assert _n("0,2150 $ dont Président 0,1800 $") in _n(t)
    assert _n("coût réel des rondes · dont Président 0,1800 $") in _n(t)
    assert _n(F.RAISON_OPUS) in _n(t)
    assert "A consulté simulation d’ordre ETH" in t
    assert 'data-direct="lat" data-pf="council-perp-opus" data-p="PF_SOLUSD"' in html_
    # Ses refus se lisent aux bornes de sa politique.
    assert "levier au-delà de 2" not in t


def test_conseil_ordre_des_membres_et_contenu_d_un_avis(site):
    t = texte(lire(site, "conseils/council-perp-opus.html"))
    i_a, i_b, i_c = t.index("Étape A"), t.index("Étape B"), t.index("Étape C · le Président a lu")
    assert i_a < i_b < i_c
    noms = [P.MEMBRES[m][0] for m in P.ORDRE_MEMBRES if P.MEMBRES[m][1] == "A"]
    assert "L’Arbitragiste de paires" in noms and noms.index("L’Arbitragiste de paires") == noms.index("Le Contrarien") + 1
    pos = [t.index(n, i_a) for n in noms]
    assert pos == sorted(pos) and pos[-1] < i_b
    assert "L’Avocat du diable" in t[i_b:i_c] and "Attaque le short ETH" in t[i_b:i_c]
    assert all(_n(x) in _n(t) for x in (F.ARG_CARTO, F.ARG_AVOCAT, F.ARG_ARBITRAGE))
    assert _n("short ETH · conviction 65 · 250 % · stop 2,5 % · niveau clé 3 150,00 $") in _n(t)
    assert "absent erreur interne" in t
    assert _n("9 avis · 1 absent · short ETH ×7, plat ×1 · l’Avocat attaque le short ETH") in _n(t)
    carto = t[t.index("Le Cartographe", i_a): t.index("Le Suiveur", i_a)]
    assert "A consulté indicateurs ETH 4h" in carto and "A consulté funding ETH" in t[i_b:i_c]


def test_conseil_haiku_refus_aux_bornes_de_sa_politique(site):
    t = texte(lire(site, "conseils/council-perp-haiku.html"))
    assert "levier au-delà de 10" in t and "liquidation atteinte avant le stop" in t and "levier au-delà de 2" not in t


def test_conseils_methode_dans_la_ligue_des_conseils(site):
    t = texte(lire(site, "conseils.html")).replace("\xa0", " ").replace("\u202f", " ")
    m = t[t.index("Les conseils : méthode"):]
    for x in ("10 au plus", "500 %", "1 000 %", "avant la liquidation", "25 %", "60 %", "24 ouvertures par 24 h",
              "ni gel quotidien, ni budget de frais", "−90 %", "marge de maintenance", "dix Claude Haiku 5.5",
              "Conseil Haiku 10 $ par jour", "Conseil Opus 25 $ par jour", "équivalent catalogue", "Arbitragiste de paires",
              "pair-trade-screener", "TradingAgents", "Président"):  # fmt: skip
        assert x in m, x
    # La méthode générale des dérivés n'en parle plus que pour renvoyer ici.
    g = texte(lire(site, "methode.html"))
    assert "Hors catégorie" not in g and "Les membres" not in g and "conseils.html#m-conseils" in lire(site, "methode.html")


def test_courbe_relie_le_direct_aux_series(site):
    """direct.js nomme chaque portefeuille par son slug, que porte sa série : la courbe peut ajouter son point en direct."""
    for nom in ("derives.html", "conseils.html"):
        page = lire(site, nom)
        direct = json.loads(html.unescape(re.search(r'<script id="direct-data"[^>]*>(.*?)</script>', page).group(1)))
        courbe = json.loads(html.unescape(re.search(r'<script id="equity-data"[^>]*>(.*?)</script>', page).group(1)))
        assert direct["pf"] and set(direct["pf"]) <= {s.get("slug") for s in courbe["series"]}, nom


def test_conseil_arrete_le_dit(tmp_path):
    spot = synthetic_journal(tmp_path / "var" / "journal" / "events.jsonl")
    perp = F.build(tmp_path / "var-perp" / "journal" / "events.jsonl", ruine=True)
    config, policy = _cfg()
    build(spot.path, tmp_path / "site", config=config, policy=policy, now_ts=NOW, public=True, racine="/arene/", perp_journal=perp)
    t = texte((tmp_path / "site" / "conseils" / "council-perp-haiku.html").read_text(encoding="utf-8"))
    assert "Conseil arrêté" in t and "ruine" in t and "Seul l’opérateur de l’arène peut le relancer" in t
    assert "arrêté, ruine" in texte((tmp_path / "site" / "conseils.html").read_text(encoding="utf-8"))


def test_conseil_deliberations_anciennes_hors_page(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "DELIBERATIONS_MAX", 1)
    perp = F.build(tmp_path / "events.jsonl")
    d = P.compute(perp, NOW)["conseils"]
    c = next(p for p in d["portfolios"] if p["id"] == F.CONSEIL)
    rondes = [x for x in c["decisions"] if x.get("conseil")]
    assert rondes[0]["conseil"]["avis"] and rondes[1]["conseil"]["avis"] == [] and rondes[1]["conseil"]["avis_hors_page"] == 9
    assert rondes[1]["conseil"]["president"] == "Haiku"  # le modèle du Président reste dit, avis ou non


def _ajoute(perp, pf, round_, *, council=None, opinions=(), opened=True):
    j = Journal(perp)
    r = F.T0 + 2 * 86_400 - 300 if round_ is None else round_
    if opened:
        j.append("portfolio_opened", {"portfolio": pf, "kind": "council", "league": "perp", "capital_ueur": 1_000_000_000,
                                      "venue_mode": "paper"}, r - 1)  # fmt: skip
    for op in opinions:
        j.append("council_opinion", {"portfolio": pf, "round": r, "member": "suiveur", "stage": "A", "opinion": op, "error": None}, r)
    j.append("agent_decision", {"portfolio": pf, "round": r, "kind": "cadence", "parsed": {"actions": [], "justification": "ok"},
                                "parse_error": None, "council": council}, r)  # fmt: skip
    return r


def test_conseil_evenements_malformes_ne_cassent_rien(tmp_path):
    perp = F.build(tmp_path / "events.jsonl")
    ops = ({"avis": 5}, {"avis": [{"instrument": "PF_XBTUSD", "position": "long", "conviction": "x", "niveau_cle_usd": "1e400",
                                    "taille_pct": "1e400"}], "cible": [1]}, "texte")  # fmt: skip
    r = _ajoute(perp, F.CONSEIL, None, opinions=ops, opened=False,
                council={"members_ok": 9, "members_failed": 2, "president_model": 7, "president_cost_uusd": "beaucoup",
                         "members_model": ["x"], "prompts_version": {"v": 2}, "name": 3})  # fmt: skip
    d = P.compute(perp, NOW)["conseils"]
    c = next(p for p in d["portfolios"] if p["id"] == F.CONSEIL)
    ronde = next(x for x in c["decisions"] if x["round"] == r)
    assert len(ronde["conseil"]["avis"]) == 1  # rejoué : un seul avis du Suiveur, le dernier
    assert ronde["conseil"]["avis"][0]["absent"]
    assert ronde["conseil"]["president"] is None and ronde["conseil"]["consignes"] is None and ronde["conseil"]["cout_president_uusd"] is None


def test_conseil_inconnu_nom_generique_sans_planter(tmp_path):
    spot = synthetic_journal(tmp_path / "var" / "journal" / "events.jsonl")
    perp = F.build(tmp_path / "var-perp" / "journal" / "events.jsonl")
    _ajoute(perp, F.INCONNU, None, council={"president_model": "claude-sonnet-5-5"})
    assert P.nom(F.INCONNU) == "Conseil Zeta" and P.nom("council-perp:") == "Conseil"
    config, policy = _cfg()
    build(spot.path, tmp_path / "site", config=config, policy=policy, now_ts=NOW, public=True, racine="/arene/", perp_journal=perp)
    out = tmp_path / "site"
    page = (out / "conseils.html").read_text(encoding="utf-8")
    assert ">Conseil Zeta</a>" in page
    z = texte((out / "conseils" / "council-perp-zeta.html").read_text(encoding="utf-8"))
    assert "Président · Sonnet" in z and "Conseil Zeta" in z


def test_sans_conseil_pas_de_ligue_des_conseils(tmp_path):
    """Un journal sans conseil : ni page, ni lien dans la navigation, ni donnée."""
    spot = synthetic_journal(tmp_path / "var" / "journal" / "events.jsonl")
    perp = F.build(tmp_path / "var-perp" / "journal" / "events.jsonl", conseils=False)
    assert P.compute(perp, NOW)["conseils"] is None
    config, policy = _cfg()
    build(spot.path, tmp_path / "site", config=config, policy=policy, now_ts=NOW, public=True, racine="/arene/", perp_journal=perp)
    out = tmp_path / "site"
    assert not (out / "conseils.html").exists() and not (out / "conseils").exists() and not (out / "data" / "conseils.json").exists()
    for f in out.rglob("*.html"):
        assert "conseils.html" not in f.read_text(encoding="utf-8"), f.name


# --- Actualités (annonces de Kraken, calendrier macro) -------------------------------------------------------


@pytest.fixture(scope="module")
def site_actus(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("actus")
    spot = synthetic_journal(tmp / "var" / "journal" / "events.jsonl")
    perp = F.ajoute_actualites(F.build(tmp / "var-perp" / "journal" / "events.jsonl"))
    cal = [
        CalendarEvent(
            "cpi-2026-12",
            "cpi",
            "le CPI de décembre 2026 (BLS)",
            NOW + 2 * 86_400,
            "https://www.bls.gov/schedule/",
        ),
        CalendarEvent(
            "ppi-2026-12",
            "ppi",
            "le PPI de décembre 2026 (BLS)",
            NOW + 3 * 86_400,
            "https://www.bls.gov/schedule/",
        ),
        CalendarEvent(
            "nfp-2027-01",
            "nfp",
            "l’emploi de janvier 2027 (BLS)",
            NOW + 20 * 86_400,
            "https://www.bls.gov/schedule/",
        ),
    ]
    mp = pytest.MonkeyPatch()
    mp.setattr(
        P,
        "load_news_config",
        lambda: SimpleNamespace(calendar=tuple(cal), wake_kinds=("fomc", "cpi", "nfp", "pce")),
    )
    try:
        out = tmp / "site"
        config, policy = _cfg()
        build(
            spot.path,
            out,
            config=config,
            policy=policy,
            now_ts=NOW,
            public=True,
            racine="/arene/",
            perp_journal=perp,
        )
    finally:
        mp.undo()
    return out


def _bloc(html: str) -> str:
    return re.search(r'<section aria-labelledby="titre-actualites">(.*?)</section>', html, re.DOTALL).group(1)


def test_actualites_declencheurs_des_decisions(site_actus):
    t = texte(lire(site_actus, "derives/llm-perp-claude-fable-5-2.html"))
    assert "annonce de Kraken · Délai sur les ordres des dérivés" in t
    c = texte(lire(site_actus, "conseils/council-perp-haiku.html"))
    assert f"publication macro · après {F.LIBELLE_CPI}" in c
    s = texte(lire(site_actus, "derives/llm-perp-claude-sonnet-5-5.html"))
    assert "appel régulier" in s and "annonce de Kraken jointe" in s


def test_actualites_bloc_de_l_accueil_derives_et_des_conseils(site_actus):
    for nom in ("derives.html", "conseils.html"):
        b = _bloc(lire(site_actus, nom))
        t = texte(b)
        assert "le CPI de décembre 2026 (BLS)" in t and "rappelle les IA 3 min après" in t
        assert (
            "le PPI de décembre 2026" in t and t.count("rappelle les IA") == 1
        )  # le PPI ne rappelle pas les IA
        assert "janvier 2027" not in t  # au-delà de 7 jours
        assert "Ancienne annonce" not in t
        assert "retrait" not in t and "Maintenance" in t and "programmée" in t and "contrats : BTC" in t
        assert 'href="https://stspg.io/abc"' in b


def test_actualites_une_annonce_a_plusieurs_versions_montre_la_derniere(site_actus):
    t = texte(_bloc(lire(site_actus, "derives.html")))
    assert t.count("Délai sur les ordres des dérivés") == 1
    assert "résolu" in t and "en analyse" not in t


def test_actualites_titre_echappe_et_lien_non_https_ecarte(site_actus):
    b = _bloc(lire(site_actus, "derives.html"))
    assert "<script>" not in b and "&lt;script&gt;alert(1)&lt;/script&gt;" in b
    assert "javascript:" not in b


def test_actualites_methode_et_export(site_actus):
    t = texte(lire(site_actus, "methode.html"))
    assert (
        "jamais les chiffres publiés" in t
        and "3 min" in t
        and 'id="m-actualites"' in lire(site_actus, "methode.html")
    )
    for nom in ("derives.json", "conseils.json"):
        a = json.loads(lire(site_actus, f"data/{nom}"))["actualites"]
        assert len(a["calendrier"]) == 2 and {x["title"] for x in a["annonces"]} == {
            "Délai sur les ordres des dérivés",
            F.TITRE_PIEGE,
        }


def test_actualites_sans_annonce_ni_calendrier(site, monkeypatch):
    b = _bloc(lire(site, "derives.html"))
    assert "Aucune annonce de Kraken sur les dérivés depuis 7 jours." in texte(b)
    assert json.loads(lire(site, "data/derives.json"))["actualites"]["annonces"] == []


def test_actualites_calendrier_illisible_est_omis(tmp_path, monkeypatch):
    def boom():
        raise ValueError("config cassée")

    monkeypatch.setattr(P, "load_news_config", boom)
    perp = F.build(tmp_path / "p" / "events.jsonl")
    assert P.compute(perp, NOW)["actualites"]["calendrier"] is None
