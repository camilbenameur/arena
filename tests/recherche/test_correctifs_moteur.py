"""Non-régression des correctifs du moteur (revue adverse du 12/11/2026). Données 100 % synthétiques.

Chaque test échoue sur le code d'avant les correctifs : date qui fuit par `Jour.i`, niveau absolu des prix,
C9 reconnaissable, classe couvert diluée, évasion par les cadres de générateurs, journal sans ancre ni
genèse, canaux de sortie (texte, temps).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from arene.journal import Journal
from recherche.config import charger_criteres
from recherche.moteur import bac_a_sable, essai
from recherche.moteur.bac_a_sable import DECALAGE_MIN, executer_flux, verifier_source
from recherche.moteur.contrat import FormePoids, SourceRefusee
from recherche.moteur.essai import (
    FicheEssai,
    calculer_metriques_portes,
    executer_essai,
    verifier_causalite,
)
from recherche.moteur.journal import AncrageError, JournalRecherche
from recherche.moteur.panneau import JOUR_S, synthetique, synthetique_varie
from recherche.moteur.portefeuille import diviseur_immobilise, simuler, valider_poids
from recherche.portes.adaptateur import vers_essai, vers_rapport_causalite

REPO = Path(__file__).resolve().parents[2]
STRAT = Path(__file__).parent / "strategies"
VAGUE1 = REPO / "recherche" / "vagues" / "1"
DEBUT_2020 = int(pd.Timestamp("2020-01-01", tz="UTC").timestamp())
FICHE = FicheEssai("F1", "directionnel", "a" * 64)
FICHE_C = FicheEssai("C1", "couvert", "b" * 64)

GABARIT = ("import numpy as np\n\nclass Strategie:\n    def __init__(self, n_paires, **p):\n        self.n = n_paires\n\n"
           "    def pas(self, jour):\n{corps}\n")


@pytest.fixture(scope="module")
def crit():
    return charger_criteres()


@pytest.fixture(scope="module", autouse=True)
def _canari():
    bac_a_sable.canari()


@pytest.fixture
def journal(tmp_path):
    import subprocess

    d = tmp_path / "labo"
    d.mkdir()
    (d / "essais.jsonl").write_text(json.dumps({"id": "E0001"}) + "\n")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    for cmd in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "x"], ["tag", "gel-final"]):
        subprocess.run(["git", "-C", str(d), *cmd], check=True, env=env, capture_output=True)
    return JournalRecherche(tmp_path / "essais.jsonl", depot_labo=d, horloge=lambda: 1_700_000_031)


def ecrire(tmp_path, corps, nom="strategie.py"):
    p = tmp_path / nom
    p.write_text(GABARIT.format(corps=corps))
    return p


def ok(*_):
    return None


# --------------------------------------------------------------------------------------------------
# 1. La date ne fuit plus : index décalé, prix et volumes rebasés
# --------------------------------------------------------------------------------------------------


def test_jour_i_decale_aleatoirement_par_essai():
    src = GABARIT.format(corps="        w = np.zeros(self.n)\n        w[0] = jour.i / 1e8\n        return w, np.zeros(self.n)").encode()
    pan = synthetique(12, 3, 0, avec_1h=False, cotations_tardives=False)
    debuts = []
    for _ in range(3):
        ws, _wp, _ = executer_flux(src, {}, pan, ok, 60)
        i = np.rint(ws[:, 0] * 1e8).astype(int)
        assert (np.diff(i) == 1).all()  # on peut compter les jours...
        debuts.append(int(i[0]))
    assert min(debuts) >= DECALAGE_MIN  # ... mais i ne vaut plus le rang depuis 2018-01-01
    assert len(set(debuts)) == 3
    ws, _wp, _ = executer_flux(src, {}, pan, ok, 60, decalage=123_456)
    assert round(ws[0, 0] * 1e8) == 123_456


def test_rebasage_prix_et_volumes_causal():
    pan = synthetique(80, 5, 3, avec_1h=True, avec_perp=True, cotations_tardives=True)
    vue = pan.rebaser()
    for k in range(pan.n_paires):
        idx = np.flatnonzero(pan.eligibles[:, k])
        # prix : divisés par le premier close de la paire
        assert vue.spot_1d[idx[0], k, 3] == pytest.approx(1.0)
        assert np.allclose(vue.spot_1d[idx, k, 3], pan.spot_1d[idx, k, 3] / pan.spot_1d[idx[0], k, 3])
        # perp : même diviseur (la base perp/spot est conservée)
        assert np.allclose(vue.perp_1h[idx, k, :, 3] / vue.spot_1h[idx, k, :, 3],
                           pan.perp_1h[idx, k, :, 3] / pan.spot_1h[idx, k, :, 3])
        # volumes : moyenne courante puis moyenne des 30 premiers jours cotés
        v = pan.spot_1d[idx, k, 4]
        for n in (0, 5, 28, 29, 40):
            if n < len(idx):
                m = v[: min(n + 1, 30)].mean()
                assert vue.spot_1d[idx[n], k, 4] == pytest.approx(v[n] / m)
        assert np.all(vue.spot_1d[~pan.eligibles[:, k], k] == 0.0)


def test_rebasage_ne_depend_que_du_passe():
    pan = synthetique(90, 4, 5, cotations_tardives=True)
    futur = pan.corrompre_apres(int(pan.jours[50]) + 5 * 3600, np.random.default_rng(0))
    a, b = pan.rebaser(), futur.rebaser()
    avant = slice(0, 50)  # jours entièrement clos avant la coupure
    assert np.array_equal(a.spot_1d[avant], b.spot_1d[avant])
    assert np.array_equal(a.spot_1h[avant], b.spot_1h[avant])


def test_la_strategie_ne_voit_plus_le_niveau_absolu(tmp_path):
    # poids = 0,1 x close du jour : avec le rebasage, 0,1 le premier jour pour toutes les paires
    src = GABARIT.format(corps="        return np.where(jour.eligibles, 0.1 * jour.spot_1d[:, 3], 0.0), np.zeros(self.n)").encode()
    pan = synthetique(5, 6, 1, avec_1h=False, cotations_tardives=False)
    assert pan.spot_1d[0, :, 3].max() / pan.spot_1d[0, :, 3].min() > 5  # niveaux réels très différents
    ws, _wp, _ = executer_flux(src, {}, pan, ok, 60)
    assert np.allclose(ws[0], 0.1)


def test_rendements_calcules_sur_les_prix_reels(tmp_path, journal, crit):
    pan = synthetique(40, 4, 2, avec_1h=False, cotations_tardives=False, debut_jour=DEBUT_2020)
    r = executer_essai(FICHE, STRAT / "constante.py", {}, pan, journal, crit, causalite=False, test=True)
    brut = r.serie.rendements_bruts
    attendu = pan.rendements_spot()[1:].mean(axis=1)
    assert np.allclose(brut[1:], attendu)


def test_ast_refuse_les_grandes_tables_de_constantes():
    def src(corps):
        return GABARIT.format(corps="        " + corps + "\n        return np.zeros(self.n), np.zeros(self.n)")

    verifier_source(src("x = [" + ",".join(["1"] * 16) + "]"))  # 16 éléments : permis
    for table in ("[" + ",".join(["1"] * 17) + "]", "(" + ",".join(["1"] * 17) + ")",
                  "{" + ",".join(f"'{i}'" for i in range(17)) + "}",
                  "{" + ",".join(f"{i}:0" for i in range(17)) + "}"):
        with pytest.raises(SourceRefusee):
            verifier_source(src("x = " + table))
    verifier_source(src("; ".join(f"x{i} = {i + 2}" for i in range(31))))  # 31 + 0 autres littéraux numériques
    with pytest.raises(SourceRefusee, match="littéraux numériques"):
        verifier_source(src("; ".join(f"x{i} = {i + 2}" for i in range(33))))
    with pytest.raises(SourceRefusee):  # table dans une chaîne
        verifier_source(src("x = '" + "01" * 100 + "'"))
    verifier_source('"""' + "docstring très longue " * 20 + '"""\n' + src("x = 1"))  # docstring : permise


@pytest.mark.parametrize(
    "p", [p for p in sorted((VAGUE1 / "strategies").glob("*.py")) + sorted(STRAT.glob("*.py"))
          if p.name != "__init__.py"], ids=lambda p: p.name)
def test_ast_accepte_les_strategies_legitimes(p):
    verifier_source(p.read_text(), p.name)


# --------------------------------------------------------------------------------------------------
# 2. C9 : données variées à graine tirée par appel, évaluable, second contrôle sur les données réelles
# --------------------------------------------------------------------------------------------------


def test_causalite_graine_par_appel_et_jeu_long(crit, monkeypatch):
    vus = []
    reel = essai.synthetique_varie

    def espion(n_jours, n_paires, graine=None, **kw):
        vus.append((n_jours, graine))
        return reel(n_jours, n_paires, graine, **kw)

    monkeypatch.setattr(essai, "synthetique_varie", espion)
    src = (STRAT / "memoire_sens.py").read_bytes()
    r1 = verifier_causalite(src, {}, crit, n_paires=6)
    r2 = verifier_causalite(src, {}, crit, n_paires=6)
    assert r1["ok"] and r2["ok"]
    assert all(n >= 1300 for n, _ in vus) and r1["n_jours"] >= 1300
    assert vus[0][1] != vus[1][1]  # graine : os.urandom, différente à chaque appel (None -> tirée dans le générateur)


def test_synthetique_varie_graine_aleatoire_et_regimes():
    a, b = synthetique_varie(1300, 6), synthetique_varie(1300, 6)
    assert not np.array_equal(a.spot_1d, b.spot_1d)
    assert np.array_equal(synthetique_varie(1300, 6, 7).spot_1d, synthetique_varie(1300, 6, 7).spot_1d)
    r = a.rendements_spot()[:, :].mean(axis=1)
    assert r.min() < -0.05  # au moins un krach
    ann = np.array([t.mean() * 1095 for t in a.funding_taux if len(t)])
    assert ann.max() > 0.5 and ann.min() < 0.0  # funding élevé soutenu et négatif
    base = a.perp_1h[:, :, -1, 3] / a.spot_1h[:, :, -1, 3] - 1.0
    assert base[a.eligibles_perp].min() < -0.005  # base négative
    assert (~a.eligibles[:, 5]).any()  # paires qui entrent en cotation


def _params_fiche(nom):
    f = yaml.safe_load((VAGUE1 / "fiches" / f"{nom}.yaml").read_text())
    p = dict(f.get("params_fixes") or {})
    for k, v in f["grille"].items():
        p[k] = v[len(v) // 2]
    return f["classe"], bool(f.get("signaux_perp", False)), p


@pytest.mark.parametrize("nom", ["m-semivar", "r-fonds-foule", "c-carry-rang", "c-carry-persistant", "c-carry-regime"])
def test_strategies_vague1_ont_des_poids_non_triviaux_en_causalite(crit, nom):
    classe, signaux, params = _params_fiche(nom)
    r = verifier_causalite((VAGUE1 / "strategies" / f"{nom}.py").read_bytes(), params, crit, classe=classe,
                           n_paires=15, avec_perp=classe == "couvert" or signaux)
    assert r["ok"] and r["evaluable"], r


def test_poids_constants_rendent_le_rapport_non_evaluable(crit):
    zero = GABARIT.format(corps="        return np.zeros(self.n), np.zeros(self.n)").encode()
    r = verifier_causalite(zero, {}, crit, n_paires=4, avec_1h=False)
    assert r["evaluable"] is False
    assert vers_rapport_causalite(r, crit).invariances_ok is False
    r2 = verifier_causalite((STRAT / "memoire_sens.py").read_bytes(), {}, crit, n_paires=6, avec_1h=False)
    assert r2["evaluable"] is True and vers_rapport_causalite(r2, crit).invariances_ok is False  # sans reel_ok
    r2["reel_ok"] = True  # le rejeu sur données réelles est ajouté par executer_essai
    assert vers_rapport_causalite(r2, crit).invariances_ok is True


def test_controle_reel_detecte_une_fuite_que_le_synthetique_ne_voit_pas(tmp_path, journal, crit, monkeypatch):
    # on neutralise le contrôle synthétique : seul le rejeu sur les données de l'essai peut attraper la fuite
    monkeypatch.setattr(essai, "verifier_causalite", lambda *a, **k: {
        "ok": True, "evaluable": True, "n_coupures": 23, "coupures_heure_non_pleine": 10, "deterministe": True,
        "ecart_coupures": 0.0, "ecart_permutation": 0.0, "ecart_echelle": 0.0})
    essai._CAUSALITE_CACHE.clear()
    pan = synthetique(60, 6, 4, avec_1h=False, cotations_tardives=False)
    r = executer_essai(FICHE, STRAT / "fuite_colonne.py", {}, pan, journal, crit, test=True)
    assert r.code == "CAUSALITE" and r.serie is None and "réelles" in r.detail
    r2 = executer_essai(FICHE, STRAT / "memoire_sens.py", {}, pan, journal, crit, test=True)
    assert r2.code == "OK" and r2.causalite["reel_ok"] and r2.causalite["ecart_reel"] <= 1e-9
    essai._CAUSALITE_CACHE.clear()


def test_cache_causalite_jamais_pour_un_autre_code_ou_d_autres_parametres(tmp_path, journal, crit, monkeypatch):
    appels = []

    def faux(source, params, criteres, **k):
        appels.append((source, dict(params)))
        return {"ok": True, "evaluable": True, "n_coupures": 23, "coupures_heure_non_pleine": 10,
                "deterministe": True, "ecart_coupures": 0.0, "ecart_permutation": 0.0, "ecart_echelle": 0.0}

    monkeypatch.setattr(essai, "verifier_causalite", faux)
    essai._CAUSALITE_CACHE.clear()
    pan = synthetique(30, 4, 1, avec_1h=False, cotations_tardives=False)
    src = (STRAT / "memoire_sens.py").read_text()
    a = tmp_path / "a.py"
    a.write_text(src)
    b = tmp_path / "b.py"
    b.write_text(src + "\n# autre code\n")

    def go(p, params):
        executer_essai(FICHE, p, params, pan, journal, crit, test=True)

    go(a, {})
    go(a, {})
    assert len(appels) == 1  # même code, mêmes paramètres : cache
    go(a, {"k": 2})
    assert len(appels) == 2  # autres paramètres
    go(b, {})
    assert len(appels) == 3  # autre code
    essai._CAUSALITE_CACHE.clear()


# --------------------------------------------------------------------------------------------------
# 3-4. Classe couvert : coûts d'une sortie complète, couverture stricte
# --------------------------------------------------------------------------------------------------


class _Res:
    def __init__(self, serie):
        self.serie, self.id, self.code, self.univers = serie, "R0001", "OK", "principal"


def test_couvert_cout_de_sortie_complete_conserve(crit):
    T = 100
    pan = synthetique(T, 3, 1, avec_1h=False, avec_perp=True, cotations_tardives=False, debut_jour=DEBUT_2020)
    ws, wp = np.zeros((T, 3)), np.zeros((T, 3))
    for j in range(T):
        if (j // 10) % 2 == 1 and j >= 20:  # 10 jours investis, 10 jours à plat
            ws[j, 0] = wp[j, 0] = 0.4
    s = simuler(pan, ws, wp, "couvert", crit)
    expo_inv = 0.4 + crit.marge_perp_part * 0.4
    e = vers_essai(_Res(s), famille="C1", classe="couvert", params={})
    m = s.masque_eval
    assert s.couts[m].sum() > 0
    # coûts totaux de la série des portes = coûts réels (investi à exposition constante)
    assert e.couts.sum() * expo_inv == pytest.approx(s.couts[m].sum(), rel=1e-12)
    # le jour d'une sortie complète (exposition du jour 0) garde son coût
    sortie = np.flatnonzero((s.exposition == 0) & (np.concatenate([[0.0], s.exposition[:-1]]) > 0) & (s.couts > 0))
    assert len(sortie) >= 2
    assert (diviseur_immobilise(s.exposition)[sortie] == pytest.approx(expo_inv))
    assert np.allclose(s.rendements_nets_immobilise[sortie], (s.rendements_bruts - s.couts)[sortie] / expo_inv)


def test_metriques_des_portes_distinctes_de_celles_du_capital_total(tmp_path, journal, crit):
    pan = synthetique(150, 4, 3, avec_1h=False, avec_perp=True, cotations_tardives=False, debut_jour=DEBUT_2020)
    r = executer_essai(FICHE_C, STRAT / "couvert_simple.py", {"taille": 0.3, "k": 2}, pan, journal, crit,
                       causalite=False, test=True)
    assert r.code == "OK", r.detail
    fin = journal.essais()[r.id]["fin"]
    assert "sharpe_net" in fin and "portes_sharpe_net" in fin and "portes_drawdown" in fin
    assert fin["rendement_annualise_net"] != fin["portes_rendement_annualise_net"]
    p = calculer_metriques_portes(r.serie)
    assert p["portes_sharpe_net"] == r.metriques["portes_sharpe_net"]
    e = vers_essai(r, famille="C1", classe="couvert", params={})
    assert float(fin["portes_sharpe_net"]) == pytest.approx(
        float(e.net.mean() / e.net.std(ddof=1) * math.sqrt(365)), rel=1e-9)


def test_couvert_exige_une_vraie_couverture():
    cot = np.ones(3, dtype=bool)
    el = np.ones(3, dtype=bool)
    ws = np.array([0.1, 0.1, 0.0])
    valider_poids("couvert", 0, ws, np.array([0.09, 0.1, 0.0]), cot, el, 0.5)  # 90 % : permis
    valider_poids("couvert", 0, ws, ws.copy(), cot, el, 0.5)
    for wp in ([0.089, 0.1, 0.0], [0.0, 0.0, 0.0], [0.1, 0.1, 0.05], [0.11, 0.1, 0.0]):
        with pytest.raises(FormePoids):
            valider_poids("couvert", 0, ws, np.array(wp), cot, el, 0.5)


# --------------------------------------------------------------------------------------------------
# 5. AST : évasion par les cadres de générateurs
# --------------------------------------------------------------------------------------------------

FRAME_ESCAPE = '''
import numpy as np

class Strategie:
    def __init__(self, n_paires, **p):
        self.n = n_paires
        def g():
            yield me.gi_frame.f_back
        me = g()
        f = next(me)
        while f.f_back is not None and "vrai_import" not in f.f_locals:
            f = f.f_back
        raise RuntimeError(repr(f.f_globals["os"].listdir("/")))
    def pas(self, jour):
        return np.zeros(self.n), np.zeros(self.n)
'''


def test_frame_escape_refuse_par_l_ast_et_jamais_executee():
    with pytest.raises(SourceRefusee, match="interdit"):
        verifier_source(FRAME_ESCAPE)
    with pytest.raises(SourceRefusee):
        executer_flux(FRAME_ESCAPE.encode(), {}, synthetique(5, 3, 1), ok, 30.0)


@pytest.mark.parametrize("attr", [
    "gi_frame", "gi_code", "cr_frame", "cr_await", "ag_frame", "ag_code", "f_back", "f_locals", "f_globals",
    "f_builtins", "tb_frame", "tb_next", "co_code", "co_consts", "__traceback__", "__code__", "__globals__",
    "__closure__", "__subclasses__", "__mro__", "__bases__", "__class__", "__dict__", "__getattribute__"])
def test_ast_refuse_les_attributs_d_introspection(attr):
    with pytest.raises(SourceRefusee):
        verifier_source(GABARIT.format(corps=f"        x = jour.{attr}\n        return np.zeros(self.n), np.zeros(self.n)"))


# --------------------------------------------------------------------------------------------------
# 6. Journal : ancres après debut et fin, genèse, journal_arene exigé, surcharges consignées
# --------------------------------------------------------------------------------------------------


def test_ancre_apres_debut_et_apres_fin(tmp_path, journal, crit):
    arene = tmp_path / "arene.jsonl"
    pan = synthetique(30, 4, 1, avec_1h=False)
    executer_essai(FICHE, STRAT / "constante.py", {}, pan, journal, crit, causalite=False, journal_arene=arene)
    ancres = [e["payload"] for e in Journal(arene).iter_events()]
    assert [a["n_lignes"] for a in ancres] == [2, 3]  # genese + debut ; genese + debut + fin
    assert all(a["genese"] == journal.hash_genese() for a in ancres)
    assert [e["type"] for e in journal.evenements()] == ["genese_labo", "debut", "fin"]


def test_journal_renomme_ou_recree_refuse(tmp_path, journal, crit):
    arene = tmp_path / "arene.jsonl"
    pan = synthetique(30, 4, 1, avec_1h=False)
    executer_essai(FICHE, STRAT / "constante.py", {}, pan, journal, crit, causalite=False, journal_arene=arene)
    renomme = JournalRecherche(tmp_path / "autre.jsonl", depot_labo=journal.depot_labo, horloge=lambda: 1_700_000_031)
    renomme.path.write_bytes(journal.path.read_bytes())
    with pytest.raises(AncrageError, match="renomm"):
        renomme.verifier_ancrage(arene)
    # recréé (même nom, genèse écrite à un autre moment, chaîne différente) : refus
    journal.path.unlink()
    neuf = JournalRecherche(journal.path, depot_labo=journal.depot_labo, horloge=lambda: 1_800_000_000)
    neuf.demarrer()
    with pytest.raises(AncrageError, match="genèse"):
        neuf.verifier_ancrage(arene)
    with pytest.raises(AncrageError):
        executer_essai(FICHE, STRAT / "constante.py", {}, pan, neuf, crit, causalite=False, journal_arene=arene)
    # recréé à l'identique de genèse (même horloge) mais plus court que la dernière ancre : refus
    journal.path.unlink()
    court = JournalRecherche(journal.path, depot_labo=journal.depot_labo, horloge=lambda: 1_700_000_031)
    court.demarrer()
    with pytest.raises(AncrageError, match="dernier ancrage"):
        court.verifier_ancrage(arene)


def test_journal_arene_obligatoire_hors_test(tmp_path, journal, crit):
    pan = synthetique(30, 4, 1, avec_1h=False, cotations_tardives=False)
    with pytest.raises(AncrageError, match="journal_arene"):
        executer_essai(FICHE, STRAT / "constante.py", {}, pan, journal, crit, causalite=False)
    assert journal.n_ids() == 0 and not journal.path.exists()
    r = executer_essai(FICHE, STRAT / "constante.py", {}, pan, journal, crit, causalite=False, test=True)
    assert r.code == "OK"


def test_debut_consigne_toutes_les_surcharges(tmp_path, journal, crit):
    pan = synthetique(30, 4, 1, avec_1h=False)
    executer_essai(FICHE, STRAT / "constante.py", {}, pan, journal, crit, causalite=False, test=True,
                   cout_spot_bp=15, cout_perp_bp=3, convention_rotation="cible", timeout_s=77)
    s = journal.evenements("debut")[0]["payload"]["surcharges"]
    assert s["causalite"] is False and s["cout_spot_bp"] == 15 and s["cout_perp_bp"] == 3
    assert s["convention_rotation"] == "cible" and str(s["timeout_s"]) == "77"  # jamais de float dans le journal
    assert s["test"] is True


# --------------------------------------------------------------------------------------------------
# 7. Canaux de sortie : texte et temps
# --------------------------------------------------------------------------------------------------


def test_aucun_texte_de_strategie_dans_detail_ni_journal(tmp_path, journal, crit):
    pan = synthetique(20, 3, 0, avec_1h=False, cotations_tardives=False)
    cas = {
        "message": "        raise ValueError('SECRET-42')",
        "classe_perso": "        class SecretXYZ(Exception):\n            pass\n        raise SecretXYZ('SECRET-42')",
        "forme": "        return np.zeros(2), np.zeros(self.n)",
        "poids": "        return np.full(self.n, 0.512345678), np.zeros(self.n)",
    }
    for nom, corps in cas.items():
        p = ecrire(tmp_path, corps, nom + ".py")
        r = executer_essai(FICHE, p, {}, pan, journal, crit, causalite=False, test=True)
        assert r.code in ("ERREUR", "FORME_POIDS"), nom
        for banni in ("SECRET", "XYZ", "0.5123", "(2,)", "Traceback"):
            assert banni not in r.detail, (nom, r.detail)
        assert "jour" in r.detail
    assert "ValueError" in journal.path_technique.read_text()
    assert "exception_non_standard" in journal.path_technique.read_text()
    tout = journal.path.read_text() + journal.path_technique.read_text()
    for banni in ("SECRET", "SecretXYZ", "0.5123", "Traceback"):
        assert banni not in tout


def test_horodatages_arrondis_a_la_minute(tmp_path, journal, crit):
    arene = tmp_path / "arene.jsonl"
    pan = synthetique(20, 3, 0, avec_1h=False, cotations_tardives=False)
    p = ecrire(tmp_path, "        raise ValueError('x')")
    executer_essai(FICHE, p, {}, pan, journal, crit, causalite=False, journal_arene=arene)
    attendu = 1_700_000_031 - 1_700_000_031 % 60
    assert attendu != 1_700_000_031
    assert {e["ts"] for e in journal.journal.iter_events()} == {attendu}
    assert json.loads(journal.path_technique.read_text().splitlines()[0])["ts"] == attendu
    assert {e["ts"] for e in Journal(arene).iter_events()} == {attendu}


def test_n_jours_synthetiques_et_jour_sans_date():
    assert essai._JOURS_SYNTH >= 1300
    assert JOUR_S == 86400
