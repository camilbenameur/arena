"""Tests du moteur de recherche : bac à sable, flux, portefeuille, essai, journal. Données 100 % synthétiques."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from arene.journal import Journal
from recherche.config import charger_criteres
from recherche.moteur import bac_a_sable, contrat
from recherche.moteur.bac_a_sable import CanariError, executer_flux, verifier_source
from recherche.moteur.contrat import DelaiDepasse, ErreurEssai, FormePoids, SourceRefusee
from recherche.moteur.essai import (
    FicheEssai,
    PlafondError,
    calculer_metriques,
    executer_essai,
    verifier_causalite,
)
from recherche.moteur.journal import AncrageError, JournalRecherche, decimal12
from recherche.moteur.panneau import panneau_depuis_tables, synthetique
from recherche.moteur.portefeuille import masque_evaluation, panier_equipondere, simuler, valider_poids

STRAT = Path(__file__).parent / "strategies"
DEBUT_2019_09 = int(pd.Timestamp("2019-09-01", tz="UTC").timestamp())
DEBUT_2018 = int(pd.Timestamp("2018-01-01", tz="UTC").timestamp())


@pytest.fixture(scope="module")
def crit():
    return charger_criteres()


@pytest.fixture(scope="module", autouse=True)
def _canari():
    bac_a_sable.canari()


@pytest.fixture
def labo_factice(tmp_path):
    """Faux dépôt du labo avec le tag gel-final (jamais le vrai journal du labo)."""
    d = tmp_path / "labo"
    d.mkdir()
    lignes = [json.dumps({"id": f"E{i:04d}", "prev_hash": "x"}) for i in range(1, 8)]
    (d / "essais.jsonl").write_text("\n".join(lignes) + "\n")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    for cmd in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "x"], ["tag", "gel-final"]):
        subprocess.run(["git", "-C", str(d), *cmd], check=True, env=env, capture_output=True)
    return d, lignes


@pytest.fixture
def journal(tmp_path, labo_factice):
    return JournalRecherche(tmp_path / "essais.jsonl", depot_labo=labo_factice[0], horloge=lambda: 1_700_000_000)


FICHE = FicheEssai("F1", "directionnel", "a" * 64)


def ecrire(tmp_path, texte, nom="strategie.py"):
    p = tmp_path / nom
    p.write_text(texte)
    return p


def sharpe(r):
    return float(r.mean() / r.std(ddof=1) * math.sqrt(365))


# --------------------------------------------------------------------------------------------------
# Contrat
# --------------------------------------------------------------------------------------------------


def test_jour_champs_et_anonymat():
    champs = [f.name for f in dataclasses.fields(contrat.Jour)]
    assert tuple(champs) == contrat.CHAMPS_JOUR
    assert not {"date", "ts", "symbole", "symboles", "nom"} & set(champs)
    assert contrat.CODES == ("OK", "CAUSALITE", "TIMEOUT", "SOURCE_REFUSEE", "FORME_POIDS", "ERREUR")


def test_codes_alignes_sur_criteres(crit):
    assert tuple(crit.execution.codes_retour) == contrat.CODES


def test_jour_message_forme():
    pan = synthetique(30, 4, 1, avec_perp=True)
    j = pan.jour(3)
    assert j.i == 3 and j.spot_1d.shape == (4, 6) and j.spot_1h.shape == (4, 24, 6)
    assert j.perp_1h.shape == (4, 24, 6) and j.eligibles.dtype == bool
    assert all(isinstance(a, int) and isinstance(b, float) for a, b in j.funding)
    assert len(j.funding) == 3 * int(pan.eligibles_perp[3].sum())


# --------------------------------------------------------------------------------------------------
# Contrôle AST
# --------------------------------------------------------------------------------------------------

GABARIT = "import numpy as np\n\nclass Strategie:\n    def __init__(self, n_paires):\n        self.n = n_paires\n\n    def pas(self, jour):\n{corps}\n        return np.zeros(self.n), np.zeros(self.n)\n"

HOSTILES = {
    "open": "        open('/etc/passwd').read()",
    "open_home": "        open('/root/.bashrc').read()",
    "import_os": "        import os",
    "import_socket": "        import socket",
    "import_subprocess": "        import subprocess",
    "import_time": "        import time",
    "import_random": "        import random",
    "import_pathlib": "        import pathlib",
    "from_os": "        from os import system",
    "dunder_import": "        __import__('os')",
    "eval": "        eval('1+1')",
    "exec": "        exec('x=1')",
    "compile": "        compile('1', 'a', 'eval')",
    "getattr": "        getattr(np, 'load')",
    "globals": "        globals()",
    "dunder_attr": "        np.__dict__",
    "dunder_classe": "        ().__class__.__bases__",
    "np_load": "        np.load('x.npy')",
    "np_fromfile": "        np.fromfile('x')",
    "np_random": "        np.random.rand(3)",
    "np_savetxt": "        np.savetxt('x', np.zeros(3))",
    "np_ctypeslib": "        np.ctypeslib",
    "memoryview": "        memoryview(b'x')",
}


@pytest.mark.parametrize("nom", sorted(HOSTILES))
def test_ast_refuse_hostiles(nom):
    with pytest.raises(SourceRefusee):
        verifier_source(GABARIT.format(corps=HOSTILES[nom]))


def test_ast_refuse_sans_classe_et_syntaxe():
    with pytest.raises(SourceRefusee):
        verifier_source("import numpy as np\nx = 1\n")
    with pytest.raises(SourceRefusee):
        verifier_source("class Strategie(:\n")


def test_ast_accepte_strategies_du_depot():
    for f in ("f1_labo", "constante", "couvert_simple", "memoire_sens", "fuite_echelle", "fuite_colonne"):
        verifier_source((STRAT / f"{f}.py").read_text())


@pytest.mark.parametrize("nom", ["open", "open_home", "import_socket", "import_subprocess", "np_load",
                                 "dunder_import"])
def test_essai_hostile_jamais_un_resultat(tmp_path, journal, crit, nom):
    p = ecrire(tmp_path, GABARIT.format(corps=HOSTILES[nom]))
    r = executer_essai(FICHE, p, {}, synthetique(40, 3, 0), journal, crit, causalite=False, test=True)
    assert r.code == "SOURCE_REFUSEE" and r.serie is None and r.metriques == {}
    assert r.pour_agent() == "SOURCE_REFUSEE"


@pytest.mark.parametrize("corps", [
    "        open('/etc/passwd').read()",
    "        open('/root/.bashrc').read()",
    "        s = __import__('socket')",
    "        s = __import__('os')",
    "        import socket as s",
])
def test_sandbox_ceinture_sans_ast(tmp_path, corps):
    """Même si le contrôle AST était contourné, le worker (builtins restreints + bwrap) ne produit rien."""
    src = GABARIT.format(corps=corps).encode()
    with pytest.raises(ErreurEssai):
        executer_flux(src, {}, synthetique(5, 3, 0), lambda *a: None, 30, verifier_ast=False)


# --------------------------------------------------------------------------------------------------
# Bac à sable bwrap (réel)
# --------------------------------------------------------------------------------------------------


def test_canari_passe():
    bac_a_sable.canari(force=True)


def test_canari_detecte_un_bac_a_sable_troue(monkeypatch):
    """Mutants : sans isolation réseau, puis avec le /tmp de l'hôte visible, le canari doit lever."""
    vrai = bac_a_sable._commande

    def sans_reseau(job, script, args):
        cmd = vrai(job, script, args)
        cmd[cmd.index("--unshare-all")] = "--unshare-pid"
        return cmd

    def tmp_hote(job, script, args):
        cmd = vrai(job, script, args)
        i = cmd.index("--tmpfs")
        cmd[i:i + 2] = ["--bind", "/tmp", "/tmp"]
        return cmd

    for mutant in (sans_reseau, tmp_hote):
        monkeypatch.setattr(bac_a_sable, "_commande", mutant)
        with pytest.raises(CanariError):
            bac_a_sable.canari(force=True)
    monkeypatch.setattr(bac_a_sable, "_commande", vrai)
    bac_a_sable.canari(force=True)


def test_canari_verifie_les_temoins(monkeypatch):
    monkeypatch.setattr(bac_a_sable.shutil, "which", lambda _: None)
    with pytest.raises(CanariError):
        bac_a_sable.canari(force=True)


def test_timeout_boucle_infinie(tmp_path, journal, crit):
    p = ecrire(tmp_path, GABARIT.format(corps="        while True:\n            pass"))
    t0 = time.time()
    r = executer_essai(FICHE, p, {}, synthetique(20, 3, 0), journal, crit, causalite=False, timeout_s=2, test=True)
    assert r.code == "TIMEOUT" and time.time() - t0 < 15
    with pytest.raises(DelaiDepasse):
        executer_flux(p.read_bytes(), {}, synthetique(5, 3, 0), lambda *a: None, 1)


def test_pas_d_erreur_ni_de_trace_pour_l_agent(tmp_path, journal, crit):
    p = ecrire(tmp_path, GABARIT.format(corps="        raise ValueError('secret 12345')"))
    r = executer_essai(FICHE, p, {}, synthetique(20, 3, 0), journal, crit, causalite=False, test=True)
    assert r.pour_agent() == "ERREUR" and r.code in contrat.CODES
    # le détail (orchestrateur) ne contient que le type d'exception standard et le jour, jamais le message
    assert "secret" not in r.detail and "12345" not in r.detail and "ValueError" in r.detail
    assert "jour 0" in r.detail
    texte = journal.path.read_text()
    assert "secret" not in texte and "Traceback" not in texte
    assert "secret" not in journal.path_technique.read_text()


# --------------------------------------------------------------------------------------------------
# Forme des poids
# --------------------------------------------------------------------------------------------------


def _essai_poids(tmp_path, journal, crit, corps, classe="directionnel", avec_perp=False, params=None):
    p = ecrire(tmp_path, GABARIT.format(corps=corps).replace(
        "return np.zeros(self.n), np.zeros(self.n)", ""))
    pan = synthetique(30, 4, 0, avec_perp=avec_perp, cotations_tardives=False)
    fiche = FicheEssai("X", classe, "b" * 64)
    return executer_essai(fiche, p, params or {}, pan, journal, crit, causalite=False, test=True)


@pytest.mark.parametrize("retour,classe,code", [
    ("np.full(self.n, 0.3), np.zeros(self.n)", "directionnel", "FORME_POIDS"),        # somme 1,2
    ("np.full(self.n, 0.25 + 1e-6), np.zeros(self.n)", "directionnel", "FORME_POIDS"),  # 1,000004 : pas de rognage
    ("np.array([-0.1, 0.1, 0.1, 0.1]), np.zeros(self.n)", "directionnel", "FORME_POIDS"),
    ("np.full(self.n, np.nan), np.zeros(self.n)", "directionnel", "FORME_POIDS"),
    ("np.zeros(self.n), np.full(self.n, 0.1)", "directionnel", "FORME_POIDS"),           # perp en directionnel
    ("np.zeros(3), np.zeros(self.n)", "directionnel", "FORME_POIDS"),                    # mauvaise forme
    ("np.full(self.n, 0.1), np.full(self.n, 0.2)", "couvert", "FORME_POIDS"),            # short > long
    ("np.full(self.n, 0.5), np.full(self.n, 0.5)", "couvert", "FORME_POIDS"),            # capital 0,5*4 + 0,25*4 > 1
    ("np.full(self.n, 0.2), np.full(self.n, 0.2)", "couvert", "OK"),                     # 0,8 + 0,4 = 1,2 ? -> voir ci-dessous
    ("np.full(self.n, 0.25), np.zeros(self.n)", "directionnel", "OK"),
    ("np.full(self.n, 0.25), np.zeros(self.n)", "couvert", "OK"),                     # long spot nu : permis (moteur v2)
])
def test_forme_poids(tmp_path, journal, crit, retour, classe, code):
    if classe == "couvert" and code == "OK" and "0.2), np.full(self.n, 0.2)" in retour:
        code = "FORME_POIDS"  # 4 x 0,2 + 0,5 x 4 x 0,2 = 1,2 > 1
    r = _essai_poids(tmp_path, journal, crit, f"        return {retour}", classe=classe, avec_perp=classe == "couvert")
    assert r.code == code, r.detail


def test_forme_poids_pas_de_rognage_des_bornes():
    cotee = np.ones(3, dtype=bool)
    valider_poids("directionnel", 0, np.array([1 / 3] * 3), np.zeros(3), cotee, None, 0.5)  # somme = 1 à 1 ulp
    with pytest.raises(FormePoids):
        valider_poids("directionnel", 0, np.array([0.5, 0.5, 1e-6]), np.zeros(3), cotee, None, 0.5)
    with pytest.raises(FormePoids):
        valider_poids("directionnel", 0, np.array([0.5, 0.0, 0.0]), np.zeros(3), np.array([0, 1, 1], bool), None, 0.5)


def test_poids_sur_paire_non_cotee_refuse(tmp_path, journal, crit):
    p = ecrire(tmp_path, GABARIT.format(corps="        return np.full(self.n, 0.1), np.zeros(self.n)").replace(
        "\n        return np.zeros(self.n), np.zeros(self.n)\n", "\n"))
    pan = synthetique(60, 6, 3, cotations_tardives=True)
    assert not pan.eligibles.all()
    r = executer_essai(FICHE, p, {}, pan, journal, crit, causalite=False, test=True)
    assert r.code == "FORME_POIDS"


# --------------------------------------------------------------------------------------------------
# Portefeuille : arithmétique
# --------------------------------------------------------------------------------------------------


def _mini_panneau(closes):
    """Panneau 1 j seulement depuis une matrice (T, N) de clôtures."""
    closes = np.asarray(closes, dtype=float)
    T, N = closes.shape
    pan = synthetique(T, N, 0, avec_1h=False, cotations_tardives=False, debut_jour=DEBUT_2018)
    s1d = pan.spot_1d.copy()
    s1d[..., 3] = closes
    return dataclasses.replace(pan, spot_1d=s1d)


def test_rotation_derive_a_la_main(crit):
    pan = _mini_panneau([[100, 100], [110, 100], [110, 100]])
    ws = np.array([[0.5, 0.5], [0.5, 0.5], [0.5, 0.5]])
    s = simuler(pan, ws, np.zeros((3, 2)), "directionnel", crit)
    r_p = 0.5 * 0.10
    assert s.rendements_bruts[1] == pytest.approx(r_p)
    # jour 1 : dérivé = (0,5*1,1/1,05 ; 0,5/1,05) -> rotation = 2*|0,5-0,5238095|
    der = 0.5 * 1.1 / 1.05
    rot1 = abs(0.5 - der) + abs(0.5 - 0.5 / 1.05)
    # rotation décidée le jour 0 (achat initial : 1,0) payée au jour 1 ; celle du jour 1 payée au jour 2
    assert s.rotation[1] == pytest.approx(1.0) and s.rotation[2] == pytest.approx(rot1)
    assert s.couts[1] == pytest.approx(0.006) and s.couts[2] == pytest.approx(0.006 * rot1)
    assert s.rendements_nets[1] == pytest.approx(r_p - 0.006)
    assert s.rendements_nets_stresses[2] == pytest.approx(0.0 - 2 * 0.006 * rot1)
    cible = simuler(pan, ws, np.zeros((3, 2)), "directionnel", crit, convention_rotation="cible")
    assert cible.rotation[1] == pytest.approx(1.0) and cible.rotation[2] == pytest.approx(0.0)


def test_cout_stress_double_et_cout_perp(crit):
    pan = synthetique(40, 3, 5, avec_perp=True, cotations_tardives=False)
    ws = np.zeros((40, 3))
    wp = np.zeros((40, 3))
    ws[5:, 0] = 0.4
    wp[5:, 0] = 0.4
    s = simuler(pan, ws, wp, "couvert", crit)
    assert s.rotation_spot[6] == pytest.approx(0.4) and s.rotation_perp[6] == pytest.approx(0.4)
    assert s.couts[6] == pytest.approx(0.4 * 0.0060 + 0.4 * 0.0010)
    assert np.allclose(s.rendements_bruts - s.rendements_nets_stresses, 2 * s.couts)
    assert s.exposition[10] == pytest.approx(0.4 + 0.5 * 0.4)


def test_funding_paye_par_la_position_decidee_avant(crit):
    """Une échéance du jour j est payée par les poids décidés à la clôture j-1 (<= fundingTime)."""
    pan = synthetique(12, 2, 1, avec_perp=True, cotations_tardives=False)
    z = np.zeros(0)
    fi = [z.astype(np.int64)] * 12
    ft = [z] * 12
    fs = [z.astype(np.int64)] * 12
    fi[6], ft[6], fs[6] = np.array([0], dtype=np.int64), np.array([0.01]), np.array([int(pan.jours[6])], dtype=np.int64)
    pan = dataclasses.replace(pan, funding_idx=tuple(fi), funding_taux=tuple(ft), funding_ts=tuple(fs),
                              eligibles_perp=np.ones((12, 2), bool))
    avant = np.zeros((12, 2)); avant[5:, 0] = 0.5   # décidée à la clôture du jour 5 -> paie le jour 6
    apres = np.zeros((12, 2)); apres[6:, 0] = 0.5   # décidée à la clôture du jour 6 -> ne paie pas le jour 6
    s_avant = simuler(pan, avant, avant, "couvert", crit)
    s_apres = simuler(pan, apres, apres, "couvert", crit)
    assert s_avant.funding[6] == pytest.approx(0.005) and s_apres.funding[6] == 0.0
    # P&L brut = spot - perp + funding
    rs, rp = pan.rendements_spot()[6, 0], pan.rendements_perp()[6, 0]
    assert s_avant.rendements_bruts[6] == pytest.approx(0.5 * rs - 0.5 * rp + 0.005)
    # funding reçu par un short quand le taux est positif ; payé quand il est négatif
    ft2 = list(ft); ft2[6] = np.array([-0.01])
    s_neg = simuler(dataclasses.replace(pan, funding_taux=tuple(ft2)), avant, avant, "couvert", crit)
    assert s_neg.funding[6] == pytest.approx(-0.005)


def test_masque_evaluation(crit):
    pan = synthetique(2600, 4, 2, avec_1h=False, cotations_tardives=True, debut_jour=DEBUT_2018)
    el, m = masque_evaluation(pan, "directionnel", crit)
    j = pd.to_datetime(pan.jours, unit="s")
    assert m[(j >= "2020-01-01") & el].all() and not m[j < "2020-01-01"].any() and not m[0]
    # fenêtre perp : fin au 2026-06-29 (hors de portée ici) et exigence spot+perp pour couvert
    pan2 = synthetique(60, 3, 2, avec_perp=True)
    assert not masque_evaluation(pan2, "couvert", crit)[1].any()  # 2018 : hors fenêtre d'évaluation


# --------------------------------------------------------------------------------------------------
# Acceptation 1 : poids 1/15 constants, recalcul indépendant en quantités
# --------------------------------------------------------------------------------------------------


def test_acceptation_panier_un_quinzieme(tmp_path, journal, crit):
    N = 15
    pan = synthetique(650, N, 11, avec_1h=False, cotations_tardives=False, debut_jour=DEBUT_2019_09)
    r = executer_essai(FICHE, STRAT / "constante.py", {}, pan, journal, crit, causalite=False, test=True)
    assert r.code == "OK", r.detail
    # recalcul indépendant : holdings en unités, valeur, dérive, rotation
    p = pan.spot_1d[:, :, 3]
    c = 0.0060
    q = (1 / N) * 1.0 / p[0]
    v = 1.0
    rot_prec = 1.0  # achat initial
    net, rot = np.zeros(len(p)), np.zeros(len(p))
    for t in range(1, len(p)):
        v_new = float(q @ p[t])
        net[t] = (v_new / v - 1.0) - c * rot_prec
        rot[t] = rot_prec
        w_der = q * p[t] / v_new
        rot_prec = float(np.abs(1 / N - w_der).sum())
        q = v_new / N / p[t]
        v = v_new
    s = r.serie
    assert np.allclose(s.rendements_nets, net, atol=1e-12, rtol=0)
    assert np.allclose(s.rotation, rot, atol=1e-12, rtol=0)
    m = s.masque_eval
    assert m.sum() > 400
    assert float(r.metriques["sharpe_net"]) == pytest.approx(sharpe(net[m]), abs=1e-12)
    # le panier du moteur (rebalancé mensuellement) a la même structure : mêmes jours, rotation plus faible
    b = panier_equipondere(pan, crit)
    assert b.rendements_bruts[1:30].shape == (29,)
    assert b.couts.sum() < s.couts.sum()


def test_resultat_journalise_en_chaines(tmp_path, journal, crit):
    pan = synthetique(650, 6, 12, avec_1h=False, cotations_tardives=False, debut_jour=DEBUT_2019_09)
    r = executer_essai(FICHE, STRAT / "constante.py", {"part": 1.0}, pan, journal, crit, causalite=False, test=True)
    e = journal.essais()[r.id]
    assert e["fin"]["statut"] == "OK" and e["fin"]["sharpe_net"] == decimal12(r.metriques["sharpe_net"])
    assert len(e["fin"]["sharpe_net"].replace(".", "").replace("-", "").replace("e", "")) <= 16
    assert Journal(journal.path).verify().ok
    assert "." not in json.dumps(e["fin"]["T"])  # entier
    assert e["debut"]["code_sha256"] == hashlib.sha256((STRAT / "constante.py").read_bytes()).hexdigest()
    assert e["debut"]["params"] == '{"part":1.0}' and e["debut"]["criteres_sha256"] == crit.sha256


# --------------------------------------------------------------------------------------------------
# Acceptation 2 : F1 du labo au contrat du flux = implémentation vectorisée de référence
# --------------------------------------------------------------------------------------------------


def f1_reference(pan, L, k, H, cout=0.0015):
    """Version du labo (pandas, vectorisée sauf le classement), poids de la barre t sur le rendement t+1."""
    T, N = pan.n_jours, pan.n_paires
    cols = [f"P{j:02d}" for j in range(N)]
    vol = pd.DataFrame(pan.spot_1d[:, :, 4], columns=cols).where(pan.eligibles)
    tak = pd.DataFrame(pan.spot_1d[:, :, 5], columns=cols).where(pan.eligibles)
    ratio = (tak / vol).where(vol > 0)
    rbar = ratio.rolling(window=L, min_periods=L).mean().to_numpy()
    poids = np.zeros((T, N))
    courant = np.zeros(N)
    for t in range(T):
        if t % H == 0:
            courant = np.zeros(N)
            ligne = rbar[t]
            el = [i for i in range(N) if np.isfinite(ligne[i])]
            el.sort(key=lambda i: (-ligne[i], i))
            for i in el[:k]:
                courant[i] = 1.0 / k
        poids[t] = courant
    close = pd.DataFrame(pan.spot_1d[:, :, 3], columns=cols).where(pan.eligibles)
    r = close.pct_change(fill_method=None)
    ws = pd.DataFrame(poids, columns=cols).shift(1).fillna(0.0)
    ws = ws.where(r.notna(), 0.0)
    brut = (ws * r.fillna(0.0)).sum(axis=1)
    rot = ws.diff().abs().sum(axis=1)
    rot.iloc[0] = ws.iloc[0].abs().sum()
    return (brut - cout * rot).to_numpy(), rot.to_numpy()


@pytest.mark.parametrize("L,k,H", [(20, 3, 10), (5, 5, 5), (40, 7, 10)])
def test_acceptation_f1_flux_contre_reference_vectorisee(tmp_path, journal, crit, L, k, H):
    pan = synthetique(700, 15, 21, avec_1h=False, cotations_tardives=True, debut_jour=DEBUT_2019_09)
    ref_net, ref_rot = f1_reference(pan, L, k, H)
    r = executer_essai(FICHE, STRAT / "f1_labo.py", {"L": L, "k": k, "H": H}, pan, journal, crit,
                       convention_rotation="cible", cout_spot_bp=15, causalite=False, test=True)
    assert r.code == "OK", r.detail
    s = r.serie
    assert np.allclose(s.rendements_nets, ref_net, atol=1e-12, rtol=0)
    assert np.allclose(s.rotation, ref_rot, atol=1e-12, rtol=0)
    m = s.masque_eval
    assert m.sum() > 500
    assert float(r.metriques["sharpe_net"]) == pytest.approx(sharpe(ref_net[m]), abs=1e-9)


def test_f1_invariant_a_la_permutation_des_colonnes(tmp_path, journal, crit):
    pan = synthetique(300, 15, 5, avec_1h=False, debut_jour=DEBUT_2019_09)
    rng = np.random.default_rng(0)
    series = []
    for _ in range(3):
        r = executer_essai(FICHE, STRAT / "f1_labo.py", {}, pan, journal, crit, causalite=False,
                           permutation=rng.permutation(15), test=True)
        assert r.code == "OK"
        series.append(r.serie.rendements_nets)
    assert np.allclose(series[0], series[1], atol=1e-12) and np.allclose(series[0], series[2], atol=1e-12)


# --------------------------------------------------------------------------------------------------
# Causalité et invariances (C9), sur synthétique
# --------------------------------------------------------------------------------------------------


def test_causalite_f1_passe(crit):
    res = verifier_causalite((STRAT / "f1_labo.py").read_bytes(), {"L": 10, "k": 3, "H": 5}, crit)
    assert res["ok"], res
    assert res["n_coupures"] == 23 and res["coupures_heure_non_pleine"] >= math.ceil(0.4 * 23)
    assert res["ecart_coupures"] <= 1e-9 and res["ecart_permutation"] <= 1e-9 and res["ecart_echelle"] <= 1e-9


def test_causalite_stateful_passe(crit):
    assert verifier_causalite((STRAT / "memoire_sens.py").read_bytes(), {}, crit)["ok"]


def test_causalite_detecte_colonne_et_le_rebasage_neutralise_l_echelle(crit):
    # le niveau absolu des prix n'est plus transmis (rebasage) : fuite_echelle ne peut plus lire le niveau
    a = verifier_causalite((STRAT / "fuite_echelle.py").read_bytes(), {}, crit)
    assert a["ecart_echelle"] <= 1e-9
    b = verifier_causalite((STRAT / "fuite_colonne.py").read_bytes(), {}, crit)
    assert not b["ok"] and b["ecart_permutation"] > 1e-9


def test_essai_code_causalite(tmp_path, journal, crit):
    r = executer_essai(FICHE, STRAT / "fuite_colonne.py", {}, synthetique(80, 5, 4), journal, crit, test=True)
    assert r.code == "CAUSALITE" and r.serie is None
    assert journal.essais()[r.id]["fin"]["statut"] == "CAUSALITE"


def test_troncature_poids_identiques_sur_le_prefixe():
    src = (STRAT / "memoire_sens.py").read_bytes()
    pan = synthetique(120, 8, 9)
    ok = lambda *a: None
    ws, _wp, _ = executer_flux(src, {}, pan, ok, 60)
    for n in (30, 77, 119):
        w2, _, _ = executer_flux(src, {}, pan.tronquer(n), ok, 60)
        assert np.abs(w2 - ws[:n]).max() == 0.0


def test_corruption_du_futur_ne_change_pas_le_passe():
    src = (STRAT / "f1_labo.py").read_bytes()
    pan = synthetique(150, 8, 10)
    ok = lambda *a: None
    ws, _, _ = executer_flux(src, {"L": 5, "k": 3, "H": 3}, pan, ok, 60)
    cut = int(pan.jours[90]) + 5 * 3600 + 17 * 60  # 05:17 du jour 90
    corr = pan.corrompre_apres(cut, np.random.default_rng(0))
    assert not np.array_equal(corr.spot_1d[91], pan.spot_1d[91])
    assert np.array_equal(corr.spot_1d[89], pan.spot_1d[89]) and np.array_equal(corr.spot_1h[89], pan.spot_1h[89])
    w2, _, _ = executer_flux(src, {"L": 5, "k": 3, "H": 3}, corr, ok, 60, jusqu_a_erreur=1)
    assert np.abs(w2[:90] - ws[:90]).max() == 0.0  # jours 0..89 clos avant la coupure


def test_panneau_permuter_et_echelle():
    pan = synthetique(20, 5, 3, avec_perp=True)
    perm = np.array([3, 0, 4, 1, 2])
    p = pan.permuter(perm)
    assert p.symboles == tuple(pan.symboles[i] for i in perm)
    assert np.array_equal(p.spot_1d[:, 0], pan.spot_1d[:, 3])
    for i in range(20):  # le funding suit la colonne
        a = {(pan.symboles[k], t) for k, t in zip(pan.funding_idx[i], pan.funding_taux[i], strict=True)}
        b = {(p.symboles[k], t) for k, t in zip(p.funding_idx[i], p.funding_taux[i], strict=True)}
        assert a == b
    f = np.array([0.1, 10, 1, 2, 5.0])
    e = pan.mettre_a_l_echelle(f)
    assert np.allclose(e.spot_1d[..., 3], pan.spot_1d[..., 3] * f)
    assert np.allclose(e.spot_1d[..., 4] * e.spot_1d[..., 3], pan.spot_1d[..., 4] * pan.spot_1d[..., 3])
    with np.errstate(invalid="ignore"):
        assert np.allclose(e.spot_1d[..., 5] / e.spot_1d[..., 4], pan.spot_1d[..., 5] / pan.spot_1d[..., 4], equal_nan=True)


def test_synthetique_coherent():
    pan = synthetique(30, 4, 1, cotations_tardives=False)
    h = pan.spot_1h
    assert np.allclose(pan.spot_1d[..., 3], h[:, :, -1, 3]) and np.allclose(pan.spot_1d[..., 0], h[:, :, 0, 0])
    assert np.allclose(pan.spot_1d[..., 4], h[..., 4].sum(axis=2))
    assert (pan.spot_1d[..., 1] >= pan.spot_1d[..., 3]).all() and (pan.spot_1d[..., 2] <= pan.spot_1d[..., 0]).all()


def test_panneau_depuis_tables_alignement():
    idx = pd.date_range("2019-12-30", periods=5, freq="D")
    cols = ["open", "high", "low", "close", "volume", "taker_buy_base"]
    a = pd.DataFrame(np.arange(30, dtype=float).reshape(5, 6) + 1, index=idx, columns=cols)
    b = a.iloc[2:].copy()
    p = panneau_depuis_tables(["AAA", "BBB"], {"AAA": a, "BBB": b})
    assert p.n_jours == 5 and p.eligibles[:, 0].all() and list(p.eligibles[:, 1]) == [False, False, True, True, True]
    assert (p.spot_1d[:2, 1] == 0).all() and p.jours[0] == int(pd.Timestamp("2019-12-30", tz="UTC").timestamp())
    s = p.sous_univers(["BBB"])
    assert s.n_jours == 3 and s.eligibles.all()


# --------------------------------------------------------------------------------------------------
# Classe couvert
# --------------------------------------------------------------------------------------------------


def test_essai_couvert(tmp_path, journal, crit):
    pan = synthetique(650, 6, 33, avec_1h=False, avec_perp=True, cotations_tardives=False, debut_jour=DEBUT_2019_09)
    fiche = FicheEssai("carry", "couvert", "c" * 64)
    r = executer_essai(fiche, STRAT / "couvert_simple.py", {"taille": 0.25, "k": 2}, pan, journal, crit,
                       causalite=False, test=True)
    assert r.code == "OK", r.detail
    s = r.serie
    ws, wp = s.poids_spot, s.poids_perp
    assert np.allclose(ws, wp) and np.allclose(ws.sum(axis=1)[100:], 0.5)
    # P&L recalculé : 0,25 par jambe sur les deux premières colonnes cotées perp
    rs, rp, fd = pan.rendements_spot(), pan.rendements_perp(), pan.funding_par_jour()
    brut = np.zeros(pan.n_jours)
    brut[1:] = (ws[:-1] * (rs[1:] - rp[1:] + fd[1:])).sum(axis=1)
    assert np.allclose(s.rendements_bruts, brut, atol=1e-12)
    assert np.allclose(s.exposition[100], 0.5 + 0.5 * 0.5) and abs(s.funding.sum()) > 0
    assert (s.rendements_nets_immobilise[100] * s.exposition[100]) == pytest.approx(s.rendements_nets[100])
    assert r.metriques["T"] > 100


def test_perp_non_fourni_en_directionnel(tmp_path, journal, crit):
    """Une fiche directionnel ne reçoit ni barres perp ni funding : une stratégie qui les exige échoue."""
    pan = synthetique(40, 4, 1, avec_perp=True, cotations_tardives=False)
    r = executer_essai(FICHE, STRAT / "couvert_simple.py", {}, pan, journal, crit, causalite=False, test=True)
    assert r.code == "ERREUR"


# --------------------------------------------------------------------------------------------------
# Journal, ancrage, plafond
# --------------------------------------------------------------------------------------------------


def test_genese_labo(labo_factice, journal):
    _d, lignes = labo_factice
    ev = journal.genese_labo()
    assert ev["seq"] == 0 and ev["type"] == "genese_labo"
    assert ev["payload"]["n_lignes"] == 7 and ev["payload"]["tete"] == hashlib.sha256(lignes[-1].encode()).hexdigest()
    with pytest.raises(Exception, match="première ligne"):
        journal.genese_labo()


def test_debut_avant_fin_et_ordre(tmp_path, journal, crit, monkeypatch):
    vu = {}
    vrai = bac_a_sable.executer_flux

    def espion(*a, **k):
        vu["types"] = [e["type"] for e in journal.evenements()]
        return vrai(*a, **k)

    monkeypatch.setattr(bac_a_sable, "executer_flux", espion)
    pan = synthetique(30, 4, 1, avec_1h=False)
    r = executer_essai(FICHE, STRAT / "constante.py", {}, pan, journal, crit, causalite=False, test=True)
    assert vu["types"] == ["genese_labo", "debut"]  # `debut` est déjà écrit avant le calcul
    assert [e["type"] for e in journal.evenements()] == ["genese_labo", "debut", "fin"]
    assert journal.n_ids() == 1 and r.id == "R0001"
    assert journal.prochain_id() == "R0002"


def test_essai_echoue_compte_et_ferme(tmp_path, journal, crit):
    p = ecrire(tmp_path, "import numpy as np\nclass Strategie:\n    def __init__(self, n):\n        pass\n    def pas(self, jour):\n        return 1 / 0\n")
    executer_essai(FICHE, p, {}, synthetique(20, 3, 0), journal, crit, causalite=False, test=True)
    ev = journal.essais()
    assert list(ev) == ["R0001"] and ev["R0001"]["fin"]["statut"] == "ERREUR"


def test_pas_de_float_dans_le_journal(tmp_path, journal, crit):
    pan = synthetique(650, 6, 12, avec_1h=False, cotations_tardives=False, debut_jour=DEBUT_2019_09)
    executer_essai(FICHE, STRAT / "constante.py", {"part": 0.5}, pan, journal, crit, causalite=False, test=True)
    assert Journal(journal.path).verify().ok  # verify signale tout float
    assert "float_present" not in Journal(journal.path).verify().codes()


def test_plafond_total(tmp_path, journal, crit):
    petit = dataclasses.replace(crit, plafond_total=2)
    pan = synthetique(30, 4, 1, avec_1h=False)
    for _ in range(2):
        executer_essai(FICHE, STRAT / "constante.py", {}, pan, journal, petit, causalite=False, test=True)
    with pytest.raises(PlafondError):
        executer_essai(FICHE, STRAT / "constante.py", {}, pan, journal, petit, causalite=False, test=True)
    assert journal.n_ids() == 2


def test_ancrage_et_verification(tmp_path, journal, crit):
    arene = tmp_path / "arene-journal.jsonl"
    pan = synthetique(30, 4, 1, avec_1h=False)
    for _ in range(2):
        executer_essai(FICHE, STRAT / "constante.py", {}, pan, journal, crit, causalite=False, journal_arene=arene)
    ev = [e for e in Journal(arene).iter_events()]
    assert [e["type"] for e in ev] == ["research_anchor"] * 4  # après chaque debut ET chaque fin
    assert ev[-1]["payload"] == {"tete": journal.tete(), "n_lignes": journal.n_lignes(), "journal": "essais.jsonl",
                                 "genese": journal.hash_genese()}
    journal.verifier_ancrage(arene)
    # journal tronqué (réécriture de l'historique) -> refus
    sauve = journal.path.read_bytes()
    lignes = sauve.split(b"\n")
    journal.path.write_bytes(b"\n".join(lignes[:-3]) + b"\n")
    with pytest.raises(AncrageError, match="dernier ancrage"):
        journal.verifier_ancrage(arene)
    # même longueur, même genèse, historique réécrit (une ligne remplacée, chaîne recalculée) -> tête absente
    journal.path.write_bytes(sauve)
    alt = JournalRecherche(tmp_path / "alt.jsonl", depot_labo=journal.depot_labo, horloge=lambda: 1_700_000_000)
    alt.demarrer()
    assert alt.hash_genese() == journal.hash_genese()
    for k in range(journal.n_lignes() - 1):
        alt.journal.append("debut", {"id": f"R{k:04d}"}, 5)
    journal.path.write_bytes(alt.path.read_bytes())
    with pytest.raises(AncrageError, match="tête ancrée"):
        journal.verifier_ancrage(arene)
    # journal recréé avec une autre genèse -> refus
    alt2 = JournalRecherche(tmp_path / "alt2.jsonl", depot_labo=journal.depot_labo, horloge=lambda: 5)
    alt2.journal.append("genese_labo", {"tag": "x", "n_lignes": 1, "tete": "0" * 64}, 5)
    for k in range(journal.n_lignes() - 1):
        alt2.journal.append("debut", {"id": f"R{k:04d}"}, 5)
    journal.path.write_bytes(alt2.path.read_bytes())
    with pytest.raises(AncrageError, match="genèse"):
        journal.verifier_ancrage(arene)
    # un essai refuse de démarrer si l'ancrage n'est pas respecté
    with pytest.raises(AncrageError):
        executer_essai(FICHE, STRAT / "constante.py", {}, pan, journal, crit, causalite=False, journal_arene=arene)


def test_pas_d_ancrage_sans_chemin(tmp_path, journal):
    journal.demarrer()
    assert journal.ancrer(None) is None
    assert list(tmp_path.glob("*arene*")) == []


def test_demarrer_exige_genese_en_premiere_ligne(tmp_path, labo_factice):
    j = JournalRecherche(tmp_path / "x.jsonl", depot_labo=labo_factice[0])
    j.journal.append("debut", {"id": "R0001"}, 1)
    with pytest.raises(Exception, match="première ligne"):
        j.demarrer()


def test_decimal12():
    assert decimal12(1.2449864426425823) == "1.24498644264"
    assert decimal12(float("nan")) == "nan" and decimal12(3) == "3" and decimal12(1e-20) == "1e-20"


def test_metriques_courtes(crit):
    pan = synthetique(10, 3, 0, avec_1h=False)
    s = simuler(pan, np.zeros((10, 3)), np.zeros((10, 3)), "directionnel", crit)
    assert calculer_metriques(s) == {"T": 0}


# --------------------------------------------------------------------------------------------------
# Performance
# --------------------------------------------------------------------------------------------------


def test_performance_taille_reelle(tmp_path, journal, crit):
    """~3 830 jours (échauffement compris) x 15 paires avec les barres 1 h : bien sous 60 s."""
    pan = synthetique(3830, 15, 77, avec_1h=True, debut_jour=DEBUT_2018)
    t0 = time.time()
    r = executer_essai(FICHE, STRAT / "f1_labo.py", {"L": 20, "k": 3, "H": 10}, pan, journal, crit, test=True)
    dt = time.time() - t0
    assert r.code == "OK", r.detail
    assert r.metriques["T"] == 2373 - 0 or r.metriques["T"] > 2000
    assert r.causalite["ok"]
    assert dt < 60, dt


# --------------------------------------------------------------------------------------------------
# Adaptateur Donnees (format du chargeur) -> Panneau
# --------------------------------------------------------------------------------------------------


def _donnees_depuis_panneau(pan, controle=None):
    from recherche.donnees.chargeur import Donnees

    cols = ["open", "high", "low", "close", "volume", "taker_buy_base"]
    spot_1d, spot_1h, perp_1h, funding = {}, {}, {}, {}
    for k, s in enumerate(pan.symboles):
        ok = pan.eligibles[:, k]
        spot_1d[s] = pd.DataFrame(pan.spot_1d[ok, k], columns=cols,
                                  index=pd.to_datetime(pan.jours[ok], unit="s").as_unit("ns"))
        hs = (pan.jours[ok][:, None] + np.arange(24)[None, :] * 3600).reshape(-1)
        spot_1h[s] = pd.DataFrame(pan.spot_1h[ok, k].reshape(-1, 6), columns=cols,
                                  index=pd.to_datetime(hs, unit="s").as_unit("ns"))
        okp = pan.eligibles_perp[:, k]
        hp = (pan.jours[okp][:, None] + np.arange(24)[None, :] * 3600).reshape(-1)
        perp_1h[s] = pd.DataFrame(pan.perp_1h[okp, k].reshape(-1, 6), columns=cols,
                                  index=pd.to_datetime(hp, unit="s").as_unit("ns"))
        ts, tx = [], []
        for i in range(pan.n_jours):
            m = pan.funding_idx[i] == k
            ts += list(pan.funding_ts[i][m])
            tx += list(pan.funding_taux[i][m])
        funding[s] = pd.DataFrame({"taux": tx, "connue_a": np.array(ts) + 1},
                                  index=pd.to_datetime(ts, unit="s").as_unit("ns"))
    return Donnees(racine=Path("."), manifeste_sha256="0" * 64, univers=pan.symboles, controle=(),
                   spot_1d=spot_1d, spot_1h=spot_1h, perp_1h=perp_1h, funding=funding, controle_1d=controle or {},
                   controle_1h={}, controle_perp_1h={}, controle_funding={})


def test_panneau_depuis_donnees_aller_retour():
    from recherche.moteur.panneau import panneau_depuis_donnees

    pan = synthetique(40, 5, 8, avec_perp=True, cotations_tardives=True, debut_jour=DEBUT_2019_09)
    d = _donnees_depuis_panneau(pan)
    p2 = panneau_depuis_donnees(d, "principal")
    assert p2.symboles == pan.symboles and np.array_equal(p2.jours, pan.jours)
    for a in ("spot_1d", "spot_1h", "perp_1h", "eligibles", "eligibles_perp"):
        assert np.array_equal(getattr(p2, a), getattr(pan, a)), a
    for i in range(pan.n_jours):
        o1, o2 = np.lexsort((pan.funding_ts[i], pan.funding_idx[i])), np.lexsort((p2.funding_ts[i], p2.funding_idx[i]))
        assert np.array_equal(pan.funding_idx[i][o1], p2.funding_idx[i][o2])
        assert np.array_equal(pan.funding_taux[i][o1], p2.funding_taux[i][o2])
    sans = panneau_depuis_donnees(d, "principal", avec_perp=False, avec_1h=False)
    assert sans.perp_1h is None and sans.spot_1h is None
    ar = panneau_depuis_donnees(d, "arene", symboles_arene=("S01", "S03"))
    assert ar.symboles == ("S01", "S03")
    ctl = panneau_depuis_donnees(dataclasses.replace(d, controle_1d={"ZZZ": d.spot_1d["S00"]}), "controle:ZZZ")
    assert ctl.symboles == ("ZZZ",) and ctl.spot_1h is None and ctl.n_paires == 1


def test_essai_univers_arene_et_controle(tmp_path, journal, crit):
    pan = synthetique(650, 15, 4, avec_1h=False, cotations_tardives=False, debut_jour=DEBUT_2019_09)
    arene = tuple(crit.univers_arene)
    pan = dataclasses.replace(pan, symboles=tuple(crit.univers))
    r = executer_essai(FICHE, STRAT / "constante.py", {}, pan, journal, crit, univers="arene", causalite=False, test=True)
    assert r.code == "OK" and r.serie.symboles == arene
    r2 = executer_essai(FICHE, STRAT / "constante.py", {}, pan, journal, crit, univers="controle:BTCUSDT",
                        causalite=False, test=True)
    assert r2.code == "OK" and r2.serie.symboles == ("BTCUSDT",) and r2.serie.poids_spot.shape[1] == 1
    assert [e["univers"] for e in (v["debut"] for v in journal.essais().values())] == ["arene", "controle:BTCUSDT"]
