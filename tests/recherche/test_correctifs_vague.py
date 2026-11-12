"""Non-régression des correctifs de la revue adverse sur les portes et l'orchestration de vague.

Un test par correctif (numérotation de la demande) : 1 sha256 de criteres.yaml, 2 reprise et plafonds
cumulatifs, 3 règle d'arrêt et numéros de vague, 4 gel lié au tag git, 5 V par classe, 6 C7 et paramètres
ignorés, 7 C16, 8 C5/C13 à plat, 9 tolérance de la sélection, 10 sorties destinées aux agents.

Journaux, dépôts git et rapports sont dans tmp_path ; données synthétiques seulement.
"""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import yaml

from recherche import vague
from recherche.config import (
    CRITERES_PATH,
    REPO,
    SHA256_CRITERES_V1,
    TAG_PROTOCOLE,
    CriteresError,
    Section,
    charger_criteres,
    verifier_criteres,
)
from recherche.moteur.essai import FicheEssai, PlafondError, executer_essai
from recherche.moteur.journal import JournalRecherche, params_canoniques
from recherche.moteur.panneau import synthetique
from recherche.portes import dsr, evaluer, selection, stats
from recherche.portes.adaptateur import vers_essai
from recherche.portes.evaluer import Essai
from tests.recherche.test_integration import (
    DEBUT_2019_09,
    Depot,
    _docs_vague,
    _fiche,
    _panneau_vague,
)

FICHE = FicheEssai("F1", "directionnel", "a" * 64)


@pytest.fixture(scope="module")
def crit():
    return charger_criteres()


@pytest.fixture
def labo_factice(tmp_path):
    d = tmp_path / "labo"
    d.mkdir()
    (d / "essais.jsonl").write_text("\n".join(json.dumps({"id": f"E{i:04d}", "prev_hash": "x"}) for i in range(1, 8)) + "\n")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    for cmd in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "x"], ["tag", "gel-final"]):
        subprocess.run(["git", "-C", str(d), *cmd], check=True, env=env, capture_output=True)
    return d


@pytest.fixture
def journal(tmp_path, labo_factice):
    return JournalRecherche(tmp_path / "essais.jsonl", depot_labo=labo_factice, horloge=lambda: 1_700_000_000)


def _docs_f1():
    return {"f1.yaml": _docs_vague()["f1.yaml"]}  # 9 points de grille


@pytest.fixture
def depot(tmp_path):
    return Depot(tmp_path / "depot").ajouter_vague(1, _docs_f1())


def _lancer(depot, n, pan, journal, crit, tmp_path, **kw):
    return vague.executer_vague(
        n, depot.fiches(n), depot.strategies(n), pan, journal, crit, rapports_dir=tmp_path / "rapports",
        depot=depot.racine, causalite=False, test=True, **kw)


def _avec_plafonds(crit, *, total=None, vague_1=None, familles=None):
    ess = crit.essais.vers_dict()
    if vague_1 is not None:
        ess["plafond_vague_1"] = vague_1
    if familles is not None:
        ess["familles_max_par_vague"] = familles
    return dataclasses.replace(crit, essais=Section(ess), plafond_total=total or crit.plafond_total,
                               plafond_vague_1=vague_1 or crit.plafond_vague_1)


def _criteres_modifie(tmp_path) -> Path:
    p = tmp_path / "criteres_modif.yaml"
    p.write_text(CRITERES_PATH.read_text().replace("N_dsr: 726", "N_dsr: 400"))
    return p


# ==================================================================================================
# 1. sha256 de criteres.yaml
# ==================================================================================================


def test_sha256_attendu_est_celui_du_tag_git():
    r = subprocess.run(["git", "-C", str(REPO), "show", f"{TAG_PROTOCOLE}:recherche/criteres.yaml"],
                       capture_output=True, check=False)
    if r.returncode != 0:
        pytest.skip("tag recherche-protocole-v1 absent")
    assert hashlib.sha256(r.stdout).hexdigest() == SHA256_CRITERES_V1
    verifier_criteres(charger_criteres())  # le fichier du dépôt est bien la version figée


def test_criteres_modifie_est_refuse_partout(tmp_path, journal, depot, crit, capsys, monkeypatch):
    modif = charger_criteres(_criteres_modifie(tmp_path))
    assert modif.n_dsr == 400 and modif.sha256 != SHA256_CRITERES_V1
    with pytest.raises(CriteresError, match="modifié"):
        verifier_criteres(modif)
    # executer_vague : refus avant toute écriture
    with pytest.raises(CriteresError):
        _lancer(depot, 1, _panneau_vague(crit), journal, modif, tmp_path)
    assert journal.n_ids() == 0 and journal.n_lignes() == 0
    # avant CHAQUE essai (ce qui protège aussi un objet Criteres altéré en cours de vague)
    ctx = vague._Ctx(1, _panneau_vague(crit), journal, modif, depot.strategies(), tmp_path / "s",
                     vague.RapportVague(1), test=True)
    f = vague.lire_fiches(depot.fiches(), depot.strategies(), 1, depot=depot.racine)[0]
    with pytest.raises(CriteresError):
        ctx.lancer(f, {"H": 10, "L": 20, "k": 3})
    assert journal.n_ids() == 0
    # CLI `verifier`
    from recherche import __main__ as cli

    monkeypatch.setattr(cli, "charger_criteres", lambda: modif)
    assert cli.main(["--donnees", str(tmp_path / "vide"), "--journal", str(tmp_path / "absent.jsonl"),
                     "verifier"]) == 1
    assert "ECHEC  criteres.yaml" in capsys.readouterr().out
    # CLI `vague` : refus (code 2), aucun essai
    assert cli.main(["--journal", str(journal.path), "--journal-arene", str(tmp_path / "a.jsonl"),
                     "--rapports", str(tmp_path / "r"), "vague", "1", "--vagues", str(depot.racine / "vagues")]) == 2
    assert journal.n_ids() == 0


# ==================================================================================================
# 2. Reprise de vague et plafonds cumulatifs
# ==================================================================================================


def _interrompre_apres(monkeypatch, k: int):
    reel = vague.executer_essai
    compte = {"n": 0}

    def faux(*a, **kw):
        if compte["n"] >= k:
            raise KeyboardInterrupt("coupure simulée")
        compte["n"] += 1
        return reel(*a, **kw)

    monkeypatch.setattr(vague, "executer_essai", faux)
    return reel


def _cles_debuts(journal):
    return [(p["famille"], p["params"], p["univers"], p["code_sha256"])
            for p in (e["payload"] for e in journal.evenements("debut"))]


def test_reprise_apres_interruption_aucun_doublon_et_n_juste(tmp_path, journal, depot, crit, monkeypatch,
                                                              labo_factice):
    pan = _panneau_vague(crit)
    reel = _interrompre_apres(monkeypatch, 4)
    with pytest.raises(KeyboardInterrupt):
        _lancer(depot, 1, pan, journal, crit, tmp_path)
    assert journal.n_ids() == 4 and len(journal.essais()) == 4
    monkeypatch.setattr(vague, "executer_essai", reel)
    rap = _lancer(depot, 1, pan, journal, crit, tmp_path)
    cles = _cles_debuts(journal)
    assert journal.n_ids() == 9 and len(set(cles)) == 9  # N juste, aucun doublon
    assert rap.n_essais_vague == 9 and rap.n_reprises == 4 and len(rap.lignes) == 9
    assert all(e["fin"] is not None for e in journal.essais().values())
    assert [e["payload"]["numero"] for e in journal.evenements("vague_debut")] == [1]  # un seul lancement
    # les séries relues sont celles de l'essai : mêmes Sharpe qu'une vague jamais interrompue
    autre = JournalRecherche(tmp_path / "autre.jsonl", depot_labo=labo_factice, horloge=lambda: 1_700_000_000)
    ref = vague.executer_vague(1, depot.fiches(), depot.strategies(), pan, autre, crit,
                               rapports_dir=tmp_path / "rapports_ref", depot=depot.racine, causalite=False, test=True)
    sh = {params_canoniques(ln.params): ln.sharpe_net for ln in rap.lignes}
    sh_ref = {params_canoniques(ln.params): ln.sharpe_net for ln in ref.lignes}
    assert sh.keys() == sh_ref.keys() and all(sh[k] == pytest.approx(sh_ref[k], rel=1e-9) for k in sh)
    # relancer une vague terminée est refusé (pas de doublon par erreur)
    with pytest.raises(vague.VagueError, match="déjà terminée"):
        _lancer(depot, 1, pan, journal, crit, tmp_path)


def test_debut_sans_fin_reste_compte_et_l_essai_est_refait(tmp_path, journal, depot, crit, monkeypatch):
    pan = _panneau_vague(crit)
    reel = _interrompre_apres(monkeypatch, 3)
    with pytest.raises(KeyboardInterrupt):
        _lancer(depot, 1, pan, journal, crit, tmp_path)
    monkeypatch.setattr(vague, "executer_essai", reel)
    # plantage entre `debut` et `fin` du 4e point : un `debut` orphelin
    f = vague.lire_fiches(depot.fiches(), depot.strategies(), 1, depot=depot.racine)[0]
    pt = vague.points_de_grille(f.grille)[3]
    code = hashlib.sha256((depot.strategies() / f.strategie).read_bytes()).hexdigest()
    journal.debut({"id": journal.prochain_id(), "famille": f.famille, "classe": f.classe, "fiche_sha256": f.sha256,
                   "code_sha256": code, "params": params_canoniques({**f.params_fixes, **pt}),
                   "univers": "principal"})
    assert journal.n_ids() == 4
    rap = _lancer(depot, 1, pan, journal, crit, tmp_path)
    # 3 clos + 1 orphelin + 6 nouveaux (dont le point refait sous un nouvel id) = 10 : l'orphelin reste compté
    assert journal.n_ids() == 10 and rap.n_essais_vague == 9 and rap.n_reprises == 3
    cles = _cles_debuts(journal)
    assert len(cles) - len(set(cles)) == 1
    refaits = [e for e in journal.essais().values()
               if e["debut"]["params"] == params_canoniques({**f.params_fixes, **pt})]
    assert len(refaits) == 2 and sorted(x["fin"] is None for x in refaits) == [False, True]
    assert sum(1 for ln in rap.lignes if ln.code == "OK") == 9


def test_plafonds_cumulatifs_sur_le_journal(tmp_path, journal, depot, crit, monkeypatch):
    pan = _panneau_vague(crit)
    reel = _interrompre_apres(monkeypatch, 5)
    with pytest.raises(KeyboardInterrupt):
        _lancer(depot, 1, pan, journal, crit, tmp_path)
    monkeypatch.setattr(vague, "executer_essai", reel)
    # 5 déjà commencés + 4 à lancer = 9 : refusés si le plafond cumulatif est < 9, quel que soit l'appel
    with pytest.raises(vague.VagueError, match="plafond de la vague 1"):
        _lancer(depot, 1, pan, journal, _avec_plafonds(crit, vague_1=8), tmp_path)
    with pytest.raises(vague.VagueError, match="dépasseraient le plafond"):
        _lancer(depot, 1, pan, journal, _avec_plafonds(crit, total=8), tmp_path)
    assert journal.n_ids() == 5
    # le plafond exact passe
    rap = _lancer(depot, 1, pan, journal, _avec_plafonds(crit, total=9, vague_1=9), tmp_path)
    assert journal.n_ids() == 9 and rap.n_essais_vague == 9


def test_plafond_familles_cumulatif_sur_le_journal(tmp_path, journal, depot, crit, monkeypatch):
    pan = _panneau_vague(crit)
    _interrompre_apres(monkeypatch, 1)
    with pytest.raises(KeyboardInterrupt):
        _lancer(depot, 1, pan, journal, crit, tmp_path)
    monkeypatch.undo()
    # nouvelles fiches (autres familles) regelées : F1 reste dans le journal -> 3 familles au total
    (depot.fiches() / "f1.yaml").unlink()
    docs = _docs_vague("X")
    docs["c2.yaml"] = _fiche("Autre", "X2", "directionnel", "f1_labo.py", {"L": [10, 20, 40], "k": [2, 3, 5]})
    for nom, d in docs.items():
        (depot.fiches() / nom).write_text(yaml.safe_dump(d))
    vague.geler_fiches(depot.fiches())
    depot.etiqueter(1)
    with pytest.raises(vague.VagueError, match="familles"):
        _lancer(depot, 1, pan, journal, _avec_plafonds(crit, familles=3), tmp_path)


def test_plafonds_verifies_avant_chaque_ligne_c15_c16_comprises(tmp_path, journal, crit):
    pan = _panneau_vague(crit)
    f = vague.Fiche("f.yaml", "0" * 64, "F1", "n", "m", "directionnel", "f1_labo.py", {}, {})
    strat = Path(__file__).parent / "strategies"
    params = {"L": 20, "k": 3, "H": 10}
    ctx = vague._Ctx(1, pan, journal, crit, strat, tmp_path / "s", vague.RapportVague(1), causalite=False,
                     test=True)
    assert ctx.lancer(f, params).code == "OK"
    # plafond total = n_ids + 1 : la ligne « arène » passe, la première ligne de contrôle est refusée AVANT le lancement
    ctx.criteres = _avec_plafonds(crit, total=journal.n_ids() + 1)
    arene, controle, supp = vague._c15_c16(f, params, ctx, ["ADAUSDT", "ATOMUSDT"])
    assert arene is not None and controle is None and supp == 1 and ctx.rap.plafond_atteint
    assert journal.n_ids() == 2  # jamais au-delà du plafond
    with pytest.raises(PlafondError):
        ctx.lancer(f, params, "controle:ADAUSDT")
    assert journal.n_ids() == 2
    # et la vague 1 : 120 variantes principales au plus, les lignes arène/contrôle n'y comptent pas
    ctx2 = vague._Ctx(1, pan, journal, _avec_plafonds(crit, vague_1=1), strat, tmp_path / "s", vague.RapportVague(1),
                      causalite=False, test=True)
    with pytest.raises(PlafondError):
        ctx2.lancer(f, {**params, "L": 40})
    assert ctx2.lancer(f, params, "controle:ADAUSDT").code == "OK"  # univers != principal : pas du plafond vague 1


# ==================================================================================================
# 3. Règle d'arrêt et numéros de vague
# ==================================================================================================


def _journal_avec(journal, evenements, rapports: Path, rapport_pour=()):
    journal.demarrer()
    for type_, payload in evenements:
        journal._ajouter(type_, payload)
    rapports.mkdir(parents=True, exist_ok=True)
    for n in rapport_pour:
        (rapports / f"vague-{n}.md").write_text("# rapport\n")


def _fin(n, dsr_):
    return ("vague_fin", {"numero": n, "meilleur_dsr": dsr_})


def test_numeros_de_vague_consecutifs(tmp_path, journal, crit):
    r, dec = tmp_path / "r", tmp_path / "DECISION-OWNER.md"
    _journal_avec(journal, [("vague_debut", {"numero": 1}), _fin(1, "0.97")], r, rapport_pour=(1,))
    ctrl = lambda n: vague._controler_numero(journal, n, crit, r, dec)
    ctrl(2)  # DSR 0,97 : pas d'arrêt, pas de décision nécessaire
    for n in (0, 3, 5):
        with pytest.raises(vague.VagueError, match="consécutifs|invalide"):
            ctrl(n)
    with pytest.raises(vague.VagueError, match="déjà terminée"):
        ctrl(1)
    # une vague commencée mais non terminée interdit la suivante
    journal._ajouter("vague_debut", {"numero": 2})
    ctrl(2)  # reprise de la vague 2 : permise
    with pytest.raises(vague.VagueError, match="n'est pas terminée"):
        ctrl(3)


def test_vague_sans_rapport_precedent_ou_sans_fin_refusee(tmp_path, journal, crit):
    r, dec = tmp_path / "r", tmp_path / "DECISION-OWNER.md"
    _journal_avec(journal, [("vague_debut", {"numero": 1}), _fin(1, "0.97")], r)  # pas de vague-1.md
    with pytest.raises(vague.VagueError, match="rapport de la vague 1"):
        vague._controler_numero(journal, 2, crit, r, dec)
    with pytest.raises(vague.VagueError, match="n'est pas terminée"):
        vague.arret_apres(journal, 2, crit)


@pytest.mark.parametrize(("dsr_", "arret"), [("0.97", False), ("0.5", False), ("0.4999", True), ("nan", True),
                                             (None, True)])
def test_arret_calcule_depuis_le_journal(tmp_path, journal, crit, dsr_, arret):
    r, dec = tmp_path / "r", tmp_path / "v" / "2" / "DECISION-OWNER.md"
    _journal_avec(journal, [("vague_debut", {"numero": 1}), _fin(1, dsr_)], r, rapport_pour=(1,))
    assert vague.arret_apres(journal, 1, crit) is arret
    # un fichier vague-1.json « arret: false » ne change rien : il n'est jamais lu
    (r / "vague-1.json").write_text(json.dumps({"arret": False}))
    if arret:
        with pytest.raises(vague.VagueError, match="arrêt"):
            vague._controler_numero(journal, 2, crit, r, dec)
        dec.parent.mkdir(parents=True)
        dec.write_text("")
        with pytest.raises(vague.VagueError, match="arrêt"):
            vague._controler_numero(journal, 2, crit, r, dec)
        dec.write_text("the owner : on continue.")
    vague._controler_numero(journal, 2, crit, r, dec)


def test_decision_consignee_par_sha256_et_immuable(tmp_path, journal, crit):
    r, dec = tmp_path / "r", tmp_path / "DECISION-OWNER.md"
    dec.write_text("the owner : on continue.")
    sha = hashlib.sha256(dec.read_bytes()).hexdigest()
    _journal_avec(journal, [("vague_debut", {"numero": 1}), _fin(1, "0.1"), ("vague_debut", {"numero": 2}),
                            ("decision_owner", {"numero": 2, "sha256": sha})], r, rapport_pour=(1,))
    vague._controler_numero(journal, 2, crit, r, dec)
    dec.write_text("the owner : en fait, autre chose.")  # modifiée après consignation
    with pytest.raises(vague.VagueError, match="a changé"):
        vague._controler_numero(journal, 2, crit, r, dec)


# ==================================================================================================
# 4. Gel lié au tag git
# ==================================================================================================


def _lire(depot, **kw):
    return vague.lire_fiches(depot.fiches(), depot.strategies(), 1, depot=depot.racine, **kw)


def test_gel_conforme_au_tag_accepte(depot):
    assert {f.famille for f in _lire(depot)} == {"F1"}


def test_gel_fiche_modifiee_apres_le_tag_meme_avec_manifeste_refait(depot):
    f = depot.fiches() / "f1.yaml"
    f.write_text(f.read_text() + "\n# retouche\n")
    vague.geler_fiches(depot.fiches())  # le manifeste est refait : seul le tag peut déceler la retouche
    with pytest.raises(vague.VagueError, match="diffère du tag"):
        _lire(depot)


def test_gel_strategie_modifiee_ou_en_trop_ou_absente(depot):
    s = depot.strategies() / "f1_labo.py"
    original = s.read_bytes()
    s.write_bytes(original + b"\n# triche\n")
    with pytest.raises(vague.VagueError, match=r"f1_labo\.py diffère du tag"):
        _lire(depot)
    s.write_bytes(original)
    _lire(depot)
    (depot.strategies() / "autre.py").write_text("x = 1\n")
    with pytest.raises(vague.VagueError, match="en trop"):
        _lire(depot)
    (depot.strategies() / "autre.py").unlink()
    s.unlink()
    with pytest.raises(vague.VagueError, match="absent"):
        _lire(depot)


def test_gel_fiche_en_trop_ou_absente(depot):
    (depot.fiches() / "z.yaml").write_text(yaml.safe_dump(_fiche("Z", "Z", "directionnel", "f1_labo.py", {"L": [1, 2, 4]})))
    vague.geler_fiches(depot.fiches())
    with pytest.raises(vague.VagueError, match="en trop"):
        _lire(depot)
    (depot.fiches() / "z.yaml").unlink()
    (depot.fiches() / "f1.yaml").unlink()
    vague.geler_fiches(depot.fiches())
    with pytest.raises(vague.VagueError, match="absent"):
        _lire(depot)


def test_gel_sans_tag_ou_hors_depot_ou_lien_symbolique(tmp_path, depot):
    with pytest.raises(vague.VagueError):
        vague.lire_fiches(depot.fiches(), depot.strategies(), 2, depot=depot.racine)  # tag vague-2 inexistant
    with pytest.raises(vague.VagueError):
        vague.lire_fiches(depot.fiches(), depot.strategies(), 1, depot=tmp_path)  # pas un dépôt contenant les dossiers
    (depot.strategies() / "lien.py").symlink_to(depot.strategies() / "f1_labo.py")
    with pytest.raises(vague.VagueError, match="lien symbolique"):
        _lire(depot)


def test_aucune_option_pour_contourner_le_gel(tmp_path):
    import inspect

    from recherche import __main__ as cli

    assert "verifier_git" not in inspect.signature(vague.executer_vague).parameters
    assert "verifier_git" not in inspect.signature(vague.lire_fiches).parameters
    with pytest.raises(SystemExit):
        cli.main(["vague", "1", "--sans-git"])
    with pytest.raises(SystemExit):
        cli.main(["vague", "1", "--decision-ecrite", "x"])


def test_cli_vague_hors_depot_refusee_par_le_gel(tmp_path, capsys, monkeypatch, crit):
    """La CLI vérifie le gel contre le dépôt du projet : des dossiers hors dépôt sont refusés."""
    from recherche import __main__ as cli
    from recherche import donnees

    base = tmp_path / "vagues" / "1"
    (base / "fiches").mkdir(parents=True)
    (base / "strategies").mkdir()
    (base / "fiches" / "x.yaml").write_text(yaml.safe_dump(_fiche("X", "X", "directionnel", "f1_labo.py", {"L": [10, 20, 40]})))
    vague.geler_fiches(base / "fiches")
    monkeypatch.setattr(donnees, "charger", lambda *a, **k: None)
    assert cli.main(["--journal", str(tmp_path / "e.jsonl"), "--journal-arene", str(tmp_path / "a.jsonl"),
                     "--rapports", str(tmp_path / "r"), "vague", "1", "--vagues", str(tmp_path / "vagues")]) == 2
    assert "vague refusée" in capsys.readouterr().err
    assert not (tmp_path / "e.jsonl").exists()


def test_chemins_de_production_alignes_sur_la_cli():
    from recherche import __main__ as cli

    assert cli.VAGUES == REPO / "recherche" / "vagues" == vague.VAGUES_DEFAUT
    assert (cli.VAGUES / "1" / "fiches" / "MANIFESTE.json").is_file() and (cli.VAGUES / "1" / "strategies").is_dir()


def test_une_strategie_hors_du_dossier_gele_est_refusee(tmp_path, journal, crit):
    docs = {"a.yaml": _fiche("Évasion", "A", "directionnel", "../f1_labo.py", {"L": [10, 20, 40], "k": [2, 3, 5]})}
    depot = Depot(tmp_path / "depot").ajouter_vague(1, docs)
    rap = _lancer(depot, 1, _panneau_vague(crit), journal, crit, tmp_path)
    assert "a.yaml" in rap.refusees and "stratégie" in rap.refusees["a.yaml"] and journal.n_ids() == 0


# ==================================================================================================
# 5. V par classe
# ==================================================================================================


def _essai_sr(nom, famille, sr, T=2373, rng=None, classe="directionnel", univers="principal"):
    rng = rng or np.random.default_rng(abs(hash(nom)) % 2**32)
    net = rng.normal(0, 0.01, T)
    net = (net - net.mean()) / net.std(ddof=1) * 0.01 + sr * 0.01
    return Essai(nom, famille, classe, {"k": nom}, pd.Series(net), None, None, None, None, univers)


def test_v_protegee_contre_les_familles_factices_t5():
    """Reprise de la preuve t5 : une vraie famille dispersée + 5 familles factices de 20 variantes."""
    T = 2373
    rng = np.random.default_rng(1)
    vraie = [float(x) for x in rng.normal(0.045, 0.045, 20)]
    v_seule = dsr.variance_classe({"A": vraie}, T)
    # factices à des niveaux différents : la variance intra-famille de chacune est nulle
    factices = {f"F{k}": [niveau] * 20 for k, niveau in enumerate((0.0, 0.02, 0.04, 0.06, 0.08))}
    sr_par_famille = {"A": vraie, **factices}
    tous = vraie + [x for v in factices.values() for x in v]
    intra = (20 * float(np.var(vraie, ddof=1))) / 20 / 6  # moyenne pondérée : seule A a une variance
    ensemble = float(np.var(tous, ddof=1))
    v = dsr.variance_classe(sr_par_famille, T)
    assert v == pytest.approx(max(ensemble, intra, 1 / (T - 1)))
    assert v > intra * 1.5  # l'ancienne formule (moyenne pondérée seule) était diluée par les factices
    assert v_seule > 0
    # le Sharpe requis suit : plus de dispersion d'ensemble, plus de Sharpe requis
    assert dsr.sharpe_requis(726, T, v) > dsr.sharpe_requis(726, T, intra)


def test_v_utilise_tous_les_essais_du_journal_pas_seulement_la_vague(tmp_path, journal, crit):
    """`sr_jours_du_journal` : toutes les vagues, univers principal, statut OK, par classe."""
    journal.demarrer()

    def essai(eid, fam, classe, univers, statut, sr):
        journal.debut({"id": eid, "famille": fam, "classe": classe, "fiche_sha256": "f", "code_sha256": "c",
                       "params": eid, "univers": univers})
        journal.fin({"id": eid, "statut": statut, **({"sr_jour": sr} if statut == "OK" else {})})

    essai("R0001", "A", "directionnel", "principal", "OK", "0.05")
    essai("R0002", "A", "directionnel", "principal", "OK", "0.07")
    journal._ajouter("vague_fin", {"numero": 1})
    essai("R0003", "B", "directionnel", "principal", "OK", "-0.02")  # vague suivante
    essai("R0004", "B", "directionnel", "arene", "OK", "9.0")  # autre univers : exclu
    essai("R0005", "B", "directionnel", "principal", "ERREUR", None)  # pas de métrique
    essai("R0006", "C", "couvert", "principal", "OK", "0.01")
    essai("R0007", "B", "directionnel", "principal", "OK", "nan")
    assert vague.sr_jours_du_journal(journal) == {
        "directionnel": {"A": [0.05, 0.07], "B": [-0.02]}, "couvert": {"C": [0.01]}}
    # evaluer_candidat : V vient du journal, pas des seuls essais de la vague en cours
    sr = vague.sr_jours_du_journal(journal)
    T = 500
    seul = _essai_sr("x", "A", 1.0, T=T)
    v_vague = evaluer.variance_de_classe("directionnel", [seul], T)
    v_journal = evaluer.variance_de_classe("directionnel", [seul], T, sr)
    assert v_journal == pytest.approx(dsr.variance_classe(sr["directionnel"], T)) and v_journal != v_vague


# ==================================================================================================
# 6. C7 : paramètres ignorés
# ==================================================================================================

SOURCE_IGNORE = '''
import numpy as np
class Strategie:
    def __init__(self, n_paires, **params):      # les paramètres sont acceptés... et ignorés
        self.n = n_paires
    def pas(self, jour):
        return np.full(self.n, 1.0 / self.n), np.zeros(self.n)
'''


def test_c7_vide_si_les_parametres_sont_ignores_t5_c7(tmp_path, journal, crit):
    pan = synthetique(900, 6, 9, cotations_tardives=False, avec_1h=False, debut_jour=1_546_300_800)
    code = tmp_path / "decor.py"
    code.write_text(SOURCE_IGNORE)
    grille = {"L": [10, 20, 40], "s": [0.1, 0.2, 0.4]}
    essais = []
    for L, s in itertools.product(grille["L"], grille["s"]):
        r = executer_essai(FICHE, code, {"L": L, "s": s}, pan, journal, crit, causalite=False, test=True)
        assert r.code == "OK", r.detail
        essais.append(vers_essai(r, famille="F", classe="directionnel", params={"L": L, "s": s}))
    cand = next(e for e in essais if e.params == {"L": 20, "s": 0.2})
    (ok, part, _), det = evaluer.porte_c7(cand, essais, grille, crit.portes.C7_voisinage, crit.essais)
    assert not ok and part is None and len(det["voisins_identiques"]) == 4 and not det["voisins"]
    assert "distinct" in det["raison"]


def _essai_serie(nom, params, graine, rotation=0.01, n=500, sharpe=1.0):
    z = np.random.default_rng(graine).normal(size=n)
    z = (z - z.mean()) / z.std(ddof=1)
    idx = pd.date_range("2020-01-01", periods=n)
    net = pd.Series(0.01 * (z + sharpe / np.sqrt(365)), index=idx)
    rot = pd.Series(rotation, index=idx)
    return Essai(nom, "F", "directionnel", params, net, net, net, rot, rot * 0)


def test_c7_voisin_distinct_seulement_si_serie_ou_rotation_differe(crit):
    grille = {"a": [1.0, 2.0, 4.0], "b": [1.0, 2.0, 4.0]}
    cfg = crit.portes.C7_voisinage
    cand = _essai_serie("c", {"a": 2.0, "b": 2.0}, 0, sharpe=1.0)

    def voisinage(distincts: set):
        tous = [cand]
        for a, b in itertools.product(grille["a"], grille["b"]):
            if (a, b) == (2.0, 2.0):
                continue
            if (a, b) in distincts:
                tous.append(_essai_serie(f"{a}{b}", {"a": a, "b": b}, hash((a, b)) % 1000 + 1, sharpe=1.0))
            else:
                tous.append(Essai(f"{a}{b}", "F", "directionnel", {"a": a, "b": b}, cand.net.copy(), cand.net,
                                  cand.net, cand.rotation.copy(), cand.couts))
        return tous

    voisins4 = {(1.0, 2.0), (4.0, 2.0), (2.0, 1.0), (2.0, 4.0)}
    (ok, part, _), det = evaluer.porte_c7(cand, voisinage(voisins4), grille, cfg, crit.essais)
    assert ok and part == 1.0 and not det["voisins_identiques"]
    # un seul axe actif (2 voisins distincts, 2 identiques) : encore valide, la part se calcule sur les distincts
    (ok, part, _), det = evaluer.porte_c7(cand, voisinage({(1.0, 2.0), (4.0, 2.0)}), grille, cfg, crit.essais)
    assert ok and len(det["voisins"]) == 2 and len(det["voisins_identiques"]) == 2
    # un seul voisin distinct : échec
    (ok, _, _), det = evaluer.porte_c7(cand, voisinage({(1.0, 2.0)}), grille, cfg, crit.essais)
    assert not ok and "distinct" in det["raison"]
    # même série mais rotation différente : voisin distinct
    tous = voisinage(set())
    tous = [t if t.id == "c" else Essai(**{**t.__dict__, "rotation": t.rotation + 1e-6}) for t in tous]
    (ok, part, _), det = evaluer.porte_c7(cand, tous, grille, cfg, crit.essais)
    assert ok and not det["voisins_identiques"]


# ==================================================================================================
# 7. C16 dans la vague : non évaluable, couvert concerné
# ==================================================================================================


def _donnees_factices(perp: dict, funding: dict):
    return SimpleNamespace(controle_perp_1h=perp, controle_funding=funding)


def test_donnee_manquante_selon_la_fiche():
    d = _donnees_factices({"A": pd.DataFrame(), "B": None}, {"A": pd.DataFrame(), "B": pd.DataFrame(), "C": None})

    def fiche(classe, signaux=False):
        return vague.Fiche("f", "0" * 64, "F", "n", "m", classe, "s.py", {}, {}, signaux)

    assert vague._donnee_manquante(d, "B", fiche("couvert")) and not vague._donnee_manquante(d, "A", fiche("couvert"))
    assert vague._donnee_manquante(d, "C", fiche("directionnel", True))
    assert not vague._donnee_manquante(d, "B", fiche("directionnel", True))
    assert not vague._donnee_manquante(d, "C", fiche("directionnel"))  # spot seul : jamais « non évaluable »


def test_c16_couvert_sans_perp_dans_le_panneau_est_non_evaluable(tmp_path, journal, crit):
    pan = dataclasses.replace(synthetique(300, 6, 3, avec_1h=False, avec_perp=False, cotations_tardives=False,
                                          debut_jour=DEBUT_2019_09), symboles=tuple(crit.univers[:6]))
    f = vague.Fiche("f.yaml", "0" * 64, "C1", "n", "m", "couvert", "couvert_simple.py", {}, {})
    ctx = vague._Ctx(1, pan, journal, crit, Path(__file__).parent / "strategies", tmp_path / "s",
                     vague.RapportVague(1), causalite=False, test=True)
    arene, controle, supp = vague._c15_c16(f, {"taille": 0.09, "k": 3}, ctx, list(pan.symboles)[:3])
    assert arene is None and supp == 0 and journal.n_ids() == 0  # C15 non applicable, aucun essai lancé
    assert controle == dict.fromkeys(list(pan.symboles)[:3], evaluer.NON_EVALUABLE)
    assert not evaluer.porte_c16(controle, crit.portes.C16_hors_univers, 20)[0]


# ==================================================================================================
# 8. C5 / C13 : années et moitiés à plat
# ==================================================================================================


def _serie_annuelle(annees_plates=(), absentes=(), bruit_par_an=0.01, graine=0):
    rng = np.random.default_rng(graine)
    idx = pd.date_range("2020-01-01", "2026-06-30")
    x = rng.normal(0.0015, bruit_par_an, len(idx))
    s = pd.Series(x, index=idx)
    for a in annees_plates:
        s[s.index.year == a] = 0.0
    return s[~s.index.year.isin(list(absentes))]


def test_c5_annee_a_plat_non_positive_non_sous_moins_un():
    cfg = yaml.safe_load(CRITERES_PATH.read_text())["portes"]["C5_annees"]
    ok, sh, _ = evaluer.porte_c5(_serie_annuelle(annees_plates=(2022,)), cfg)
    assert ok and sh[2022] == 0.0  # 5 années positives : l'année à plat ne compte pas parmi elles mais n'échoue pas
    # si l'année à plat fait passer sous 4 années positives, C5 échoue (elle n'est pas positive)
    ok, _, _ = evaluer.porte_c5(_serie_annuelle(annees_plates=(2021, 2022, 2023)), cfg)
    assert not ok
    # année absente : toujours un échec
    ok, sh, _ = evaluer.porte_c5(_serie_annuelle(absentes=(2022,)), cfg)
    assert not ok and np.isnan(sh[2022])
    # une année sous -1 échoue toujours
    s = _serie_annuelle()
    s[s.index.year == 2022] = np.random.default_rng(5).normal(-0.004, 0.01, int((s.index.year == 2022).sum()))
    assert stats.sharpe(s[s.index.year == 2022]) < -1 and not evaluer.porte_c5(s, cfg)[0]
    # sans l'option, le Sharpe d'une année à plat reste NaN (comportement de stats inchangé)
    assert np.isnan(stats.sharpe_par_annee(_serie_annuelle(annees_plates=(2022,)), [2022])[2022])


def test_c13_moitie_a_plat_vaut_zero_et_echoue():
    cfg = yaml.safe_load(CRITERES_PATH.read_text())["portes"]["C13_moities"]
    rng = np.random.default_rng(2)
    n = 400
    idx = pd.date_range("2020-01-01", periods=n)
    x = rng.normal(0.002, 0.01, n)
    x[: n // 2] = 0.0
    ok, (a, b), _ = evaluer.porte_c13(pd.Series(x, index=idx), cfg)
    assert a == 0.0 and b > 0 and not ok  # > 0 requis dans chaque moitié
    y = rng.normal(0.002, 0.01, n)
    y[n // 2:] = 0.0
    assert evaluer.porte_c13(pd.Series(y, index=idx), cfg)[1][1] == 0.0
    assert stats.sharpe_moities(np.zeros(10)) == (0.0, 0.0)


# ==================================================================================================
# 9. Sélection : tolérance et corrélations négatives
# ==================================================================================================


def _paire(rho, n=500):
    rng = np.random.default_rng(4)
    z1, z2 = rng.normal(size=n), rng.normal(size=n)
    z1 = (z1 - z1.mean()) / z1.std()
    z2 = z2 - z2.mean()
    z2 -= (z2 @ z1) / (z1 @ z1) * z1
    z2 /= z2.std()
    idx = pd.date_range("2020-01-01", periods=n)
    return pd.Series(z1, index=idx), pd.Series(rho * z1 + np.sqrt(1 - rho**2) * z2, index=idx)


def test_selection_comparaison_avec_tolerance():
    a, b = _paire(0.7)
    rho = float(a.corr(b))
    cands = [selection.Candidat("a", 0.99, a), selection.Candidat("b", 0.96, b)]

    def crit_max(cmax):
        return {"selection": {"correlation_exces_panier_max": cmax, "candidats_max": 3}}

    # rho dépasse le seuil de 5e-13 (bruit flottant) : dans la tolérance de 1e-12, gardé
    assert selection.selectionner(cands, crit_max(rho - 5e-13)).retenus == ("a", "b")
    # rho dépasse le seuil de 5e-12 : au-delà de la tolérance, écarté
    assert selection.selectionner(cands, crit_max(rho - 5e-12)).retenus == ("a",)


def test_selection_ne_retire_pas_les_correlations_negatives():
    a, _ = _paire(0.0)
    s = selection.selectionner([selection.Candidat("a", 0.99, a), selection.Candidat("b", 0.96, -a)],
                               {"selection": {"correlation_exces_panier_max": 0.7, "candidats_max": 3}})
    assert s.retenus == ("a", "b") and s.correlations[("a", "b")] == pytest.approx(-1.0)


# ==================================================================================================
# 10. Sorties destinées aux agents : statuts binaires seulement
# ==================================================================================================


def test_cli_vague_n_affiche_que_des_statuts_binaires(tmp_path, journal, depot, crit, capsys, monkeypatch):
    from recherche import __main__ as cli
    from recherche import donnees
    from recherche.moteur import journal as mj

    pan = _panneau_vague(crit)
    monkeypatch.setattr(donnees, "charger", lambda *a, **k: pan)
    monkeypatch.setattr(mj, "JournalRecherche", lambda path: journal)
    orig = vague.executer_vague
    monkeypatch.setattr(vague, "executer_vague", lambda *a, **k: orig(*a, **{**k, "depot": depot.racine,
                                                                            "causalite": False}))
    code = cli.main(["--journal", str(journal.path), "--journal-arene", str(tmp_path / "a.jsonl"),
                     "--rapports", str(tmp_path / "rapports"), "vague", "1", "--vagues", str(depot.racine / "vagues")])
    out = capsys.readouterr().out
    assert code == 0
    assert re.search(r"^- Pression taker : (ecartee|non_ecartee) \(", out, re.MULTILINE)
    assert not re.search(r"\d+\.\d+|R\d{4}|[Ss]harpe|DSR|essais", out), out
    statuts = json.loads((tmp_path / "rapports" / "vague-1-statuts.json").read_text())
    assert all(set(s) == {"nom", "mecanisme", "verdict"} for s in statuts)
    # les chiffres sont dans le rapport de l'orchestrateur
    md = (tmp_path / "rapports" / "vague-1.md").read_text()
    assert "Meilleur DSR" in md and "ne va à aucun agent" in md
    assert not (tmp_path / "rapports" / "vague-1.json").exists()
