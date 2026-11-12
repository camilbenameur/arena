# ruff: noqa: F811  (fixtures importées de test_correctifs_vague)
"""Non-régression de la revue 2 : V des couverts, porte C9 fermée sans clé, plafonds par nom de famille.

Journaux, dépôts git et rapports dans tmp_path ; données synthétiques seulement.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest
import yaml

from recherche import vague
from recherche.config import Section, charger_criteres
from recherche.portes import dsr
from recherche.portes.adaptateur import vers_rapport_causalite
from tests.recherche.test_correctifs_vague import (  # noqa: F401  (fixtures)
    _docs_f1,
    _lancer,
    depot,
    journal,
    labo_factice,
)
from tests.recherche.test_integration import _panneau_vague


@pytest.fixture(scope="module")
def crit():
    return charger_criteres()


def _essai(journal, eid, fam, classe, **metriques):
    journal.debut({"id": eid, "famille": fam, "classe": classe, "fiche_sha256": "f", "code_sha256": "c",
                   "params": eid, "univers": "principal"})
    journal.fin({"id": eid, "statut": "OK", **metriques})


# --- 1. V des couverts sur la série de C1 ---------------------------------------------------------


def test_v_des_couverts_vient_de_portes_sr_jour(journal):
    journal.demarrer()
    # capital total : sr_jour très dispersé ; capital immobilisé (série de C1) : peu dispersé
    for i, (tot, imm) in enumerate([("0.01", "0.050"), ("0.09", "0.052"), ("-0.07", "0.048")]):
        _essai(journal, f"R{i}", "C", "couvert", sr_jour=tot, portes_sr_jour=imm)
    _essai(journal, "R9", "D", "directionnel", sr_jour="0.03", portes_sr_jour="0.99")
    sr = vague.sr_jours_du_journal(journal)
    assert sr["couvert"]["C"] == [0.05, 0.052, 0.048]
    assert sr["directionnel"]["D"] == [0.03]  # directionnel : capital total, inchangé
    T = 500
    v = dsr.variance_classe(sr["couvert"], T)
    assert v == pytest.approx(max(float(np.var([0.05, 0.052, 0.048], ddof=1)), 1 / (T - 1)))
    assert v < float(np.var([0.01, 0.09, -0.07], ddof=1))


# --- 2. C9 : porte fermée si la clé reel_ok est absente --------------------------------------------


def test_reel_ok_absent_ferme_la_porte_c9(crit):
    caus = {"ecart_coupures": 0.0, "ecart_permutation": 0.0, "ecart_echelle": 0.0, "n_coupures": 30,
            "coupures_heure_non_pleine": 10, "deterministe": True, "evaluable": True}
    assert vers_rapport_causalite(caus, crit).invariances_ok is False
    assert vers_rapport_causalite({**caus, "reel_ok": True}, crit).invariances_ok is True
    assert vers_rapport_causalite({**caus, "reel_ok": False}, crit).invariances_ok is False


# --- 3. plafonds par nom de famille ----------------------------------------------------------------


def test_deux_fiches_de_meme_famille_partagent_le_plafond(tmp_path, journal, depot, crit):
    ess = crit.essais.vers_dict()
    ess.update(familles_max_par_vague=1, variantes_max_par_famille_vague_1=10)
    c = dataclasses.replace(crit, essais=Section(ess))
    doc = yaml.safe_load((depot.fiches() / "f1.yaml").read_text())
    (depot.fiches() / "f1b.yaml").write_text(yaml.safe_dump({**doc, "nom": "Seconde fiche, même famille"}))
    vague.geler_fiches(depot.fiches())
    depot.etiqueter(1)
    pan = _panneau_vague(crit)
    # avant la correction : 2 fiches comptées comme 2 familles -> VagueError ; 9 + 9 variantes passaient
    rap = _lancer(depot, 1, pan, journal, c, tmp_path)
    assert "f1b.yaml" in rap.refusees and "F1" in rap.refusees["f1b.yaml"]
    assert "f1.yaml" not in rap.refusees
    assert rap.n_essais_vague == 9


# --- 4. revue 2 bis : nom de famille, tirage k par famille ------------------------------------------


@pytest.mark.parametrize("nom", ["momentum ", "Momentum ", "mom_entum", "mom--x", ""])
def test_famille_hors_motif_refusee(tmp_path, depot, nom):
    doc = yaml.safe_load((depot.fiches() / "f1.yaml").read_text())
    (depot.fiches() / "f1.yaml").write_text(yaml.safe_dump({**doc, "famille": nom}))
    vague.geler_fiches(depot.fiches())
    depot.etiqueter(1)
    with pytest.raises(vague.VagueError, match="famille"):
        vague.lire_fiches(depot.fiches(), depot.strategies(), 1, depot=depot.racine)


def test_familles_qui_ne_different_que_par_la_casse_refusees(tmp_path, journal, depot, crit):
    doc = yaml.safe_load((depot.fiches() / "f1.yaml").read_text())
    (depot.fiches() / "f1b.yaml").write_text(yaml.safe_dump({**doc, "famille": doc["famille"].lower()}))
    vague.geler_fiches(depot.fiches())
    depot.etiqueter(1)
    with pytest.raises(vague.VagueError, match="casse"):
        _lancer(depot, 1, _panneau_vague(crit), journal, crit, tmp_path)


def test_un_tirage_k_par_famille_ecrit_avant_les_essais_et_relu(tmp_path, journal, depot, crit, monkeypatch):
    from recherche.moteur import bac_a_sable
    vus = []
    reel = bac_a_sable.tirer_jours_retires

    def espion(pan, criteres, tirage=None):
        vus.append(tirage)
        return reel(pan, criteres, tirage=tirage)

    monkeypatch.setattr(bac_a_sable, "tirer_jours_retires", espion)
    _lancer(depot, 1, _panneau_vague(crit), journal, crit, tmp_path)
    (deb,) = journal.evenements("vague_debut")
    tirages = deb["payload"]["tirages_k"]
    assert set(tirages) == {"F1"} and vus and all(t == tirages["F1"] for t in vus)
    ks = {e["fin"]["jours_retires"] for e in journal.essais().values() if e["fin"].get("statut") == "OK"}
    assert len(ks) == 1  # toutes les variantes de la famille : même k
