"""Tests d'intégration de la recherche : moteur <-> portes, acceptation sur données réelles, ancrage, vague.

Les essais vont dans des journaux TEMPORAIRES (tmp_path), jamais dans recherche/essais.jsonl ni var/journal/.
Les tests marqués `donnees_reelles` lisent var/recherche/donnees (coupure 2026-06-30) et se sautent sans elles.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from arene.config import load_config
from arene.journal import Journal
from arene.ledger import replay
from arene.risk.policy import load_policy
from arene.site import build
from recherche import vague
from recherche.config import REPO, charger_criteres
from recherche.moteur import bac_a_sable
from recherche.moteur.essai import FicheEssai, calculer_metriques, executer_essai
from recherche.moteur.journal import JournalRecherche
from recherche.moteur.panneau import panneau_depuis_donnees, synthetique
from recherche.moteur.portefeuille import SerieMoteur
from recherche.portes import evaluer, selection, stats
from recherche.portes.adaptateur import vers_essai, vers_rapport_causalite

STRAT = Path(__file__).parent / "strategies"
DEBUT_2019_09 = int(pd.Timestamp("2019-09-01", tz="UTC").timestamp())
RACINE_DONNEES = REPO / "var" / "recherche" / "donnees"
FICHE = FicheEssai("F1", "directionnel", "a" * 64)
E0065_SHARPE = 1.2449864426425823

donnees_reelles = pytest.mark.donnees_reelles
sans_donnees = pytest.mark.skipif(
    not (RACINE_DONNEES / "MANIFESTE.json").is_file(), reason="var/recherche/donnees non construit")


@pytest.fixture(scope="module")
def crit():
    return charger_criteres()


@pytest.fixture(scope="module", autouse=True)
def _canari():
    bac_a_sable.canari()


@pytest.fixture
def labo_factice(tmp_path):
    d = tmp_path / "labo"
    d.mkdir()
    lignes = [json.dumps({"id": f"E{i:04d}", "prev_hash": "x"}) for i in range(1, 8)]
    (d / "essais.jsonl").write_text("\n".join(lignes) + "\n")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    for cmd in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "x"], ["tag", "gel-final"]):
        subprocess.run(["git", "-C", str(d), *cmd], check=True, env=env, capture_output=True)
    return d


@pytest.fixture
def journal(tmp_path, labo_factice):
    return JournalRecherche(tmp_path / "essais.jsonl", depot_labo=labo_factice, horloge=lambda: 1_700_000_000)


def sharpe_np(r):
    return float(r.mean() / r.std(ddof=1) * math.sqrt(365))


# --------------------------------------------------------------------------------------------------
# Écart 2 : le moteur et portes/stats.py donnent les mêmes métriques
# --------------------------------------------------------------------------------------------------


def test_metriques_moteur_egales_aux_portes_sur_serie_aleatoire(crit):
    rng = np.random.default_rng(3)
    for graine in range(5):
        r = rng.standard_t(4, 900) * 0.01 + 0.0006 * (graine + 1)
        n = len(r)
        jours = (np.int64(1_577_836_800) + 86400 * np.arange(n)).astype(np.int64)
        z = np.zeros(n)
        serie = SerieMoteur(
            classe="directionnel", jours=jours, rendements_nets=r, rendements_nets_stresses=r * 0.9,
            rendements_bruts=r + 0.001, rotation=np.abs(rng.normal(0, 0.1, n)), rotation_spot=z, rotation_perp=z,
            couts=np.full(n, 0.001), exposition=np.ones(n), rendements_nets_immobilise=r, funding=z,
            eligible=np.ones(n, bool), masque_eval=np.ones(n, bool), poids_spot=np.zeros((n, 1)),
            poids_perp=np.zeros((n, 1)), symboles=("X",))
        m = calculer_metriques(serie)
        s = pd.Series(r, index=pd.to_datetime(jours, unit="s"))
        sk, ku = stats.moments(s)
        assert m["sharpe_net"] == pytest.approx(stats.sharpe(s), rel=1e-12)
        assert m["sr_jour"] == pytest.approx(stats.sr_jour(s), rel=1e-12)
        assert m["drawdown"] == pytest.approx(stats.drawdown(s), rel=1e-12)
        assert m["t_nw20"] == pytest.approx(stats.t_newey_west(s, 20), rel=1e-12)
        assert m["rendement_annualise_net"] == pytest.approx(stats.rendement_annualise(s), rel=1e-12)
        assert m["rotation_annuelle"] == pytest.approx(stats.rotation_annuelle(serie.rotation), rel=1e-12)
        assert m["skew"] == pytest.approx(sk, rel=1e-9) and m["kurt"] == pytest.approx(ku, rel=1e-9)
        assert m["sharpe_net_couts_x2"] == pytest.approx(stats.sharpe(s * 0.9), rel=1e-12)


def test_metriques_moteur_egales_aux_portes_apres_adaptation(tmp_path, journal, crit):
    pan = synthetique(700, 15, 21, avec_1h=False, debut_jour=DEBUT_2019_09)
    r = executer_essai(FICHE, STRAT / "f1_labo.py", {}, pan, journal, crit, causalite=False, test=True)
    assert r.code == "OK", r.detail
    e = vers_essai(r, famille="F1", classe="directionnel", params={})
    assert len(e.net) == r.metriques["T"]
    assert r.metriques["sharpe_net"] == pytest.approx(stats.sharpe(e.net), rel=1e-12)
    assert r.metriques["drawdown"] == pytest.approx(stats.drawdown(e.net), rel=1e-12)
    assert r.metriques["t_nw20"] == pytest.approx(stats.t_newey_west(e.net), rel=1e-12)
    assert r.metriques["sharpe_net_couts_x2"] == pytest.approx(stats.sharpe(e.net_stress), rel=1e-12)
    assert r.metriques["cout_total_annualise"] == pytest.approx(float(e.couts.sum() / (len(e.couts) / 365)))


def test_adaptateur_causalite_donne_un_rapport_c9_valide(tmp_path, journal, crit):
    pan = synthetique(420, 15, 4, avec_1h=True, debut_jour=DEBUT_2019_09)
    r = executer_essai(FICHE, STRAT / "f1_labo.py", {}, pan, journal, crit, test=True)
    assert r.code == "OK", r.detail
    rapport = vers_rapport_causalite(r.causalite, crit)
    assert isinstance(rapport, evaluer.RapportCausalite)
    assert rapport.n_aleatoires == 20 and rapport.n_fixes == 3 and rapport.part_heure_non_pleine >= 0.4
    ok, valeur, _ = evaluer.porte_c9(rapport, crit.portes.C9_causalite)
    assert ok and valeur <= 1e-9
    assert vers_rapport_causalite(None, crit) is None and vers_rapport_causalite({"ok": False, "erreur": "x"}, crit) is None


# --------------------------------------------------------------------------------------------------
# Acceptation : panier 1/15 (indépendant), synthétique puis réel
# --------------------------------------------------------------------------------------------------


def _panier_independant(close: np.ndarray, cout: float = 0.0060):
    """Holdings en unités, valeur, dérive, rotation : sans rien du moteur."""
    n = close.shape[1]
    q = (1 / n) / close[0]
    v = 1.0
    rot_prec = 1.0
    net, rot = np.zeros(len(close)), np.zeros(len(close))
    for t in range(1, len(close)):
        v_new = float(q @ close[t])
        net[t] = (v_new / v - 1.0) - cout * rot_prec
        rot[t] = rot_prec
        w_der = q * close[t] / v_new
        rot_prec = float(np.abs(1 / n - w_der).sum())
        q = v_new / n / close[t]
        v = v_new
    return net, rot


def _verifier_panier(r, pan, crit):
    net, rot = _panier_independant(pan.spot_1d[:, :, 3], crit.cout_spot_bp / 1e4)
    s = r.serie
    assert np.allclose(s.rendements_nets, net, atol=1e-12, rtol=0)
    assert np.allclose(s.rotation, rot, atol=1e-12, rtol=0)
    m = s.masque_eval
    assert m.sum() > 400
    assert float(r.metriques["sharpe_net"]) == pytest.approx(sharpe_np(net[m]), abs=1e-12)
    e = vers_essai(r, famille="C", classe="directionnel", params={})
    assert stats.sharpe(e.net) == pytest.approx(sharpe_np(net[m]), abs=1e-12)
    assert stats.rotation_annuelle(e.rotation) == pytest.approx(rot[m].sum() / (m.sum() / 365), rel=1e-12)


def test_acceptation_panier_un_quinzieme_synthetique(tmp_path, journal, crit):
    pan = synthetique(650, 15, 11, avec_1h=False, cotations_tardives=False, debut_jour=DEBUT_2019_09)
    r = executer_essai(FICHE, STRAT / "constante.py", {}, pan, journal, crit, causalite=False, test=True)
    assert r.code == "OK", r.detail
    _verifier_panier(r, pan, crit)


def _depuis(pan, i0):
    sl = slice(i0, None)
    return dataclasses.replace(
        pan, jours=pan.jours[sl], spot_1d=pan.spot_1d[sl], spot_1h=None, perp_1h=None,
        eligibles=pan.eligibles[sl], eligibles_perp=None, funding_idx=pan.funding_idx[sl],
        funding_taux=pan.funding_taux[sl], funding_ts=pan.funding_ts[sl])


@pytest.fixture(scope="module")
def donnees_chargees():
    from recherche.donnees import charger

    return charger(RACINE_DONNEES)


@pytest.fixture(scope="module")
def panneau_reel(donnees_chargees):
    return panneau_depuis_donnees(donnees_chargees, "principal", avec_1h=False, avec_perp=False)


@donnees_reelles
@sans_donnees
def test_acceptation_panier_un_quinzieme_reel(tmp_path, journal, crit, panneau_reel):
    pan = panneau_reel
    i0 = int(np.argmax(pan.eligibles.all(axis=1)))  # première date où les 15 paires sont cotées
    assert pan.eligibles[i0:].all(), "trou d'éligibilité après la dernière cotation"
    sous = _depuis(pan, i0)
    # jours_retires=0 : reproduction exacte du panier recalculé depuis la première date à 15 paires
    r = executer_essai(FICHE, STRAT / "constante.py", {}, sous, journal, crit, causalite=False, test=True,
                       jours_retires=0)
    assert r.code == "OK", r.detail
    _verifier_panier(r, sous, crit)


@donnees_reelles
@sans_donnees
def test_acceptation_e0065_reel(tmp_path, journal, crit, panneau_reel):
    """E0065 du labo : F1 L=20 k=3 H=10, 15 paires, rotation sur cibles, 15 pb, fenêtre 2020-01-01 -> 2026-06-30."""
    r = executer_essai(FICHE, STRAT / "f1_labo.py", {"L": 20, "k": 3, "H": 10}, panneau_reel, journal, crit,
                       convention_rotation="cible", cout_spot_bp=15, causalite=False, test=True,
                       jours_retires=0)  # le labo démarre à la 1re date : la phase H=10 en dépend
    assert r.code == "OK", r.detail
    assert float(r.metriques["sharpe_net"]) == pytest.approx(E0065_SHARPE, abs=1e-6)
    assert journal.essais()[r.id]["fin"]["statut"] == "OK"
    assert not (REPO / "recherche" / "essais.jsonl").exists() or journal.path != REPO / "recherche" / "essais.jsonl"


# --------------------------------------------------------------------------------------------------
# Écart 3 : p(non réfuté | H0) par simulation
# --------------------------------------------------------------------------------------------------


def test_p_non_refute_h0_simule_et_constante():
    p = selection.simuler_p_non_refute()
    assert p == pytest.approx(selection.P_NON_REFUTE_H0_DEFAUT, abs=1e-12)  # graine fixe : reproductible
    autre = selection.simuler_p_non_refute(graine=7, n_sim=200_000)
    assert abs(autre - p) < 0.006
    # règle de rendement seule : P(R >= -0,5 sigma) autour de 0,9 pour un Sharpe vrai nul
    seul = selection.simuler_p_non_refute(avec_drawdown=False)
    assert 0.89 < seul < 0.92 and p <= seul + 1e-12
    # puissance : sous un Sharpe vrai de 1 la règle réfute ~5 % ; pas de dérive nulle ici, donc p(H0) > 0,85
    assert p > 0.85
    assert selection.proba_au_moins_un_non_refute(3) == pytest.approx(1 - (1 - p) ** 3, abs=1e-12)


# --------------------------------------------------------------------------------------------------
# Étape 6 : research_anchor ne casse ni replay ni le site
# --------------------------------------------------------------------------------------------------


_LIGNES_JOURNAL = ("événements, tête", "chaîne intacte", "Tête de chaîne")


def _hash_dossier(d: Path) -> dict[str, str]:
    """sha256 de chaque fichier du site, SAUF les métadonnées du journal (nombre d'événements, tête de chaîne) :
    un événement de plus change forcément ces lignes et rien d'autre ne doit changer."""
    out = {}
    for p in sorted(d.rglob("*")):
        if not p.is_file():
            continue
        octets = p.read_bytes()
        if p.suffix == ".html":
            lignes = [x for x in octets.decode().splitlines() if not any(m in x for m in _LIGNES_JOURNAL)]
            octets = "\n".join(lignes).encode()
        elif p.suffix == ".json":
            doc = json.loads(octets)
            if isinstance(doc, dict):
                doc.pop("journal", None)
            octets = json.dumps(doc, sort_keys=True).encode()
        out[str(p.relative_to(d))] = hashlib.sha256(octets).hexdigest()
    return out


def test_research_anchor_dans_journal_arene_temporaire(tmp_path, journal, crit):
    from tests.test_site import NOW, ROOT, synthetic_journal

    arene = synthetic_journal(tmp_path / "arene" / "events.jsonl")
    cfg = load_config(ROOT / "config" / "arene.toml")
    pol = load_policy(ROOT / "config" / "policy.toml")
    etats_avant = replay(arene.iter_events())
    build(arene.path, tmp_path / "site_avant", config=cfg, policy=pol, now_ts=NOW)

    pan = synthetique(300, 6, 5, avec_1h=False, cotations_tardives=False, debut_jour=DEBUT_2019_09)
    j = JournalRecherche(journal.path, depot_labo=journal.depot_labo, horloge=lambda: NOW)
    r = executer_essai(FICHE, STRAT / "constante.py", {}, pan, j, crit, causalite=False,
                       journal_arene=arene.path)
    assert r.code == "OK"
    ancres = [e for e in Journal(arene.path).iter_events() if e["type"] == "research_anchor"]
    # le moteur ancre au moins après la `fin` (et, depuis la correction A, aussi après le `debut`) ; le dernier
    # ancrage est celui de la tête courante
    assert len(ancres) >= 1 and ancres[-1]["payload"]["tete"] == j.tete()
    assert ancres[-1]["payload"]["n_lignes"] == j.n_lignes()
    assert Journal(arene.path).verify().ok

    etats_apres = replay(Journal(arene.path).iter_events())
    assert etats_apres == etats_avant
    build(arene.path, tmp_path / "site_apres", config=cfg, policy=pol, now_ts=NOW)
    # seules les métadonnées du journal changent (un événement de plus, une autre tête) : tout le reste est identique
    assert _hash_dossier(tmp_path / "site_apres") == _hash_dossier(tmp_path / "site_avant")
    assert (tmp_path / "site_avant" / "index.html").read_text() != (tmp_path / "site_apres" / "index.html").read_text()
    # et l'ancrage protège : un journal de recherche tronqué est refusé
    lignes = j.path.read_text().splitlines(keepends=True)
    j.path.write_text("".join(lignes[:-1]))
    with pytest.raises(Exception, match="ancrage|lignes"):
        JournalRecherche(j.path, depot_labo=j.depot_labo).verifier_ancrage(arene.path)


# --------------------------------------------------------------------------------------------------
# Vague de bout en bout (données synthétiques, 2 fiches factices, dossiers temporaires)
# --------------------------------------------------------------------------------------------------


def _fiche(nom, famille, classe, strategie, grille, **autres):
    return {"famille": famille, "nom": nom, "mecanisme": f"mécanisme de {nom}", "classe": classe,
            "strategie": strategie, "grille": grille, "qui_perd": "x", "prediction_falsifiable": "x", **autres}


ENV_GIT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"}


class Depot:
    """Faux dépôt git (dans tmp) : `vagues/<n>/{fiches,strategies}` commités et étiquetés `recherche-vague-<n>-fiches`."""

    def __init__(self, racine: Path):
        self.racine = racine
        racine.mkdir(parents=True, exist_ok=True)
        self.env = {**ENV_GIT, "HOME": str(racine)}
        self._git("init", "-q")

    def _git(self, *args):
        subprocess.run(["git", "-C", str(self.racine), *args], check=True, env=self.env, capture_output=True)

    def fiches(self, n=1) -> Path:
        return self.racine / "vagues" / str(n) / "fiches"

    def strategies(self, n=1) -> Path:
        return self.racine / "vagues" / str(n) / "strategies"

    def decision(self, n) -> Path:
        return self.racine / "vagues" / str(n) / "DECISION-OWNER.md"

    def ajouter_vague(self, n: int, docs: dict, strategies=("f1_labo.py", "couvert_simple.py"), etiqueter=True):
        self.fiches(n).mkdir(parents=True, exist_ok=True)
        self.strategies(n).mkdir(parents=True, exist_ok=True)
        for nom, d in docs.items():
            (self.fiches(n) / nom).write_text(yaml.safe_dump(d, allow_unicode=True))
        for st in strategies:
            (self.strategies(n) / st).write_bytes((STRAT / st).read_bytes())
        vague.geler_fiches(self.fiches(n))
        if etiqueter:
            self.etiqueter(n)
        return self

    def etiqueter(self, n: int):
        self._git("add", ".")
        self._git("commit", "-q", "-m", f"vague {n}", "--allow-empty")
        self._git("tag", "-f", f"recherche-vague-{n}-fiches")


def _docs_vague(prefixe=""):
    return {
        "f1.yaml": _fiche("Pression taker", f"{prefixe}F1", "directionnel", "f1_labo.py",
                          {"L": [10, 20, 40], "k": [2, 3, 5]}, params_fixes={"H": 10}),
        "c1.yaml": _fiche("Couverture simple", f"{prefixe}C1", "couvert", "couvert_simple.py",
                          {"taille": [0.06, 0.09, 0.13], "k": [2, 3, 4]}),
    }


@pytest.fixture
def depot(tmp_path):
    return Depot(tmp_path / "depot").ajouter_vague(1, _docs_vague())


def _lancer(depot, n, pan, journal, crit, tmp_path, **kw):
    return vague.executer_vague(
        n, depot.fiches(n), depot.strategies(n), pan, journal, crit, rapports_dir=tmp_path / "rapports",
        depot=depot.racine, causalite=kw.pop("causalite", False),
        test=kw.pop("test", kw.get("journal_arene") is None), **kw)


def _panneau_vague(crit):
    pan = synthetique(820, 15, 8, avec_1h=True, avec_perp=True, debut_jour=DEBUT_2019_09 - 400 * 86400)
    return dataclasses.replace(pan, symboles=tuple(crit.univers))


def test_vague_de_bout_en_bout(tmp_path, journal, crit, depot):
    pan = _panneau_vague(crit)
    rap = _lancer(depot, 1, pan, journal, crit, tmp_path, journal_arene=tmp_path / "arene.jsonl")
    assert rap.n_essais_vague == 18 and not rap.refusees and not rap.plafond_atteint
    assert journal.n_ids() == 18 and len(rap.lignes) == 18
    assert all(ln.code == "OK" for ln in rap.lignes), [ln.code for ln in rap.lignes]
    assert all(ln.verdict is not None for ln in rap.lignes)
    # sans test de causalité (causalite=False), C9 échoue partout : aucun candidat, et c'est dit
    assert all("C9" in ln.verdict.echecs() for ln in rap.lignes) and rap.candidats == []
    assert rap.arret is (rap.meilleur_dsr < 0.5)
    md = rap.chemin_rapport.read_text()
    assert md.count("| R0") == 18 and "Règle d'arrêt déclenchée : " in md and "C9 : ÉCHEC" in md
    statuts = json.loads(rap.chemin_statuts.read_text())
    assert {s["nom"] for s in statuts} == {"Pression taker", "Couverture simple"}
    assert all(set(s) == {"nom", "mecanisme", "verdict"} and s["verdict"] == "ecartee" for s in statuts)
    assert not any(ch.isdigit() for s in statuts for ch in s["verdict"])
    # aucun fichier JSON modifiable ne porte la règle d'arrêt
    assert not (tmp_path / "rapports" / "vague-1.json").exists()
    # chaque essai est chaîné et ancré ; les marqueurs de vague sont dans le journal
    assert journal.verifier_ancrage(tmp_path / "arene.jsonl") is None
    assert [e["payload"]["numero"] for e in journal.evenements("vague_debut")] == [1]
    assert [e["payload"]["numero"] for e in journal.evenements("vague_fin")] == [1]
    assert vague.arret_apres(journal, 1, crit) is rap.arret
    # la vague 2 est une autre vague, d'autres familles : elle exige la décision du propriétaire si l'arrêt s'applique
    depot.ajouter_vague(2, _docs_vague("B"))
    if rap.arret:
        with pytest.raises(vague.VagueError, match="arrêt"):
            _lancer(depot, 2, pan, journal, crit, tmp_path)
        depot.decision(2).write_text("   \n")
        with pytest.raises(vague.VagueError, match="arrêt"):
            _lancer(depot, 2, pan, journal, crit, tmp_path)
        depot.decision(2).write_text("the owner : vague 2 autorisée")
        depot.etiqueter(2)
    assert journal.n_ids() == 18
    rap2 = _lancer(depot, 2, pan, journal, crit, tmp_path)
    assert rap2.numero == 2 and journal.n_ids() == 36
    if rap.arret:
        dec = journal.evenements("decision_owner")
        assert len(dec) == 1 and dec[0]["payload"] == {
            "numero": 2, "fichier": "DECISION-OWNER.md",
            "sha256": hashlib.sha256(depot.decision(2).read_bytes()).hexdigest()}


def test_vague_couvert_c15_non_applicable_c16_reste():
    v = evaluer.Verdict(portes={"C15": (False, None, 1), "C16": (False, None, 1), "C1": (True, 1, 1)},
                        coherence={"C2": (True, 1, 1)}, passe=False)
    w = vague._sans_c15(v)
    assert w.portes["C15"][1].startswith("non applicable") and w.portes["C15"][0]
    assert w.portes["C16"] == (False, None, 1) and not w.passe  # C16 s'applique aussi au couvert
    v2 = dataclasses.replace(v, portes={**v.portes, "C16": (True, 1, 1)})
    assert vague._sans_c15(v2).passe
    v3 = dataclasses.replace(v2, portes={**v2.portes, "C1": (False, 0, 1)})
    assert not vague._sans_c15(v3).passe


def test_vague_refuse_fiche_modifiee_ou_non_gelee(tmp_path, journal, crit, depot):
    pan = _panneau_vague(crit)
    f1 = depot.fiches() / "f1.yaml"
    f1.write_text(f1.read_text() + "\n# retouche\n")
    with pytest.raises(vague.VagueError, match="modifiée"):
        _lancer(depot, 1, pan, journal, crit, tmp_path)
    (depot.fiches() / "MANIFESTE.json").unlink()
    with pytest.raises(vague.VagueError, match="non gelées"):
        _lancer(depot, 1, pan, journal, crit, tmp_path)
    assert journal.n_ids() == 0  # rien n'a été essayé


def test_vague_refuse_grille_non_geometrique_et_trop_de_variantes(tmp_path, journal, crit):
    docs = {
        "a.yaml": _fiche("Pas géométrique", "A", "directionnel", "f1_labo.py", {"L": [10, 11, 12], "k": [2, 3, 5]}),
        "b.yaml": _fiche("Trop de variantes", "B", "directionnel", "f1_labo.py",
                         {"L": [5, 10, 20, 40], "k": [2, 3, 5, 8, 13, 21]}),
        "c.yaml": _fiche("Un seul paramètre", "C", "directionnel", "f1_labo.py", {"L": [10, 20, 40]}),
    }
    depot = Depot(tmp_path / "depot").ajouter_vague(1, docs)
    rap = _lancer(depot, 1, _panneau_vague(crit), journal, crit, tmp_path)
    assert set(rap.refusees) == {"a.yaml", "b.yaml", "c.yaml"} and rap.n_essais_vague == 0
    assert "non géométrique" in rap.refusees["a.yaml"] and "variantes" in rap.refusees["b.yaml"]
    assert journal.n_ids() == 0


def test_vague_c15_c16_sur_panneau_nomme(tmp_path, journal, crit):
    """Le chemin C15 (replay riskd/fills sur l'univers arène) et C16 (contrôle) tourne de bout en bout."""
    pan = _panneau_vague(crit)
    f = vague.Fiche("f.yaml", "0" * 64, "F1", "Pression taker", "m", "directionnel", "f1_labo.py", {}, {})
    ctx = vague._Ctx(1, pan, journal, crit, STRAT, tmp_path / "series", vague.RapportVague(1), causalite=False, test=True)
    arene, controle, supp = vague._c15_c16(
        f, {"L": 20, "k": 3, "H": 10}, ctx, ["ADAUSDT", "ATOMUSDT", "AVAXUSDT"])
    assert supp == 4 and arene is not None and math.isfinite(arene.sharpe)
    assert arene.policy_sha256 and set(controle) == {"ADAUSDT", "ATOMUSDT", "AVAXUSDT"}
    assert all(v is not None for v in controle.values())
    ok, val, _ = evaluer.porte_c16(controle, crit.portes.C16_hors_univers, crit.controle_taille)
    assert not ok and val[4] == 20 and val[2] == 20  # 3 symboles sur 20 : dénominateur fixe
    ok15, val15, _ = evaluer.porte_c15(arene, "directionnel", crit.portes.C15_arene, crit.portes.C6_drawdown_max)
    assert isinstance(ok15, bool) and len(val15) == 2


def test_cli_canari_et_verifier(tmp_path, capsys):
    from recherche.__main__ import main

    assert main(["canari"]) == 0
    assert "canari OK" in capsys.readouterr().out
    assert main(["--donnees", str(tmp_path / "vide"), "--journal", str(tmp_path / "absent.jsonl"), "verifier"]) == 1
    sortie = capsys.readouterr().out
    assert "ECHEC  manifeste" in sortie and "journal de recherche : absent" in sortie
    assert main(["--rapports", str(tmp_path), "statuts"]) == 0


def test_cli_vague_geler(tmp_path, capsys):
    from recherche.__main__ import main

    d = tmp_path / "vagues" / "1" / "fiches"
    d.mkdir(parents=True)
    (d / "x.yaml").write_text(yaml.safe_dump(_fiche("X", "X", "directionnel", "f1_labo.py", {"L": [10, 20, 40]})))
    assert main(["vague", "1", "--geler", "--vagues", str(tmp_path / "vagues")]) == 0
    assert (d / "MANIFESTE.json").is_file()
