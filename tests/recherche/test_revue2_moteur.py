"""Non-régression de la 2e revue adverse du moteur (12/11/2026) : univers de contrôle sans 1 h/perp/funding,
ordre du funding qui révèle la permutation, évasion par `collections._sys`, tables de constantes (entiers,
chaînes), date par compte de jours, rejeu de causalité sans dérangement. Données 100 % synthétiques.

Chaque test échoue sur le code d'avant les correctifs.
"""

from __future__ import annotations

import ast
import sys
import types
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from recherche.moteur import bac_a_sable, essai
from recherche.moteur.bac_a_sable import executer_flux, verifier_source
from recherche.moteur.contrat import SourceRefusee
from recherche.moteur.essai import FicheEssai, executer_essai
from recherche.moteur.panneau import panneau_depuis_donnees, synthetique, synthetique_varie
from tests.recherche.test_donnees import charge, racine_factice
from tests.recherche.test_moteur import _canari, crit, ecrire, journal, labo_factice  # noqa: F401

STRAT = Path(__file__).parent / "strategies"
VAGUE1 = Path(__file__).resolve().parents[2] / "recherche" / "vagues" / "1" / "strategies"


def ok(*_):
    return None


# --------------------------------------------------------------------------------------------------
# 1. Univers de contrôle : 1 h, perp et funding branchés
# --------------------------------------------------------------------------------------------------

SRC_COUVERT_PERP = b'''
import numpy as np
class Strategie:
    def __init__(self, n, **p):
        self.n = n
    def pas(self, jour):
        w = np.zeros(self.n)
        if jour.perp_1h is not None and jour.eligibles_perp is not None and jour.eligibles_perp[0] \\
                and jour.eligibles[0]:
            w[0] = 0.25
        return w, w.copy()
'''


def test_controle_branche_1h_perp_et_funding(tmp_path):
    d = charge(tmp_path, racine_factice(tmp_path))
    pan = panneau_depuis_donnees(d, "controle:CTLUSDT")
    assert pan.symboles == ("CTLUSDT",)
    assert pan.spot_1h is not None and pan.perp_1h is not None and pan.eligibles_perp is not None
    assert pan.eligibles_perp.any() and sum(len(a) for a in pan.funding_idx) == 3  # 06-29 ; 06-30 hors grille 1 j
    # mêmes valeurs que les tables du chargeur (colonnes et connue_a identiques à l'univers principal)
    h = d.controle_1h["CTLUSDT"][["open", "high", "low", "close", "volume", "taker_buy_base"]].to_numpy()
    assert np.array_equal(pan.spot_1h[-1, 0], h[:24])  # dernier jour de la grille 1 j = 2026-06-29
    pf = d.controle_perp_1h["CTLUSDT"][["open", "high", "low", "close", "volume", "taker_buy_base"]].to_numpy()
    assert np.array_equal(pan.perp_1h[-1, 0], pf[:24])
    # sans 1 h / perp : None, comme avant
    d2 = charge(tmp_path / "b", racine_factice(tmp_path / "b", ctl_perp=False, ctl_1h=False))
    p2 = panneau_depuis_donnees(d2, "controle:CTLUSDT")
    assert p2.spot_1h is None and p2.perp_1h is None and p2.eligibles_perp is None


def test_controle_couvert_et_signaux_perp_recoivent_leurs_donnees(tmp_path, crit):  # noqa: F811
    d = charge(tmp_path, racine_factice(tmp_path))
    pc = essai._panneau(d, "controle:CTLUSDT", "couvert", crit)
    assert pc.perp_1h is not None and pc.eligibles_perp is not None
    ps = essai._panneau(d, "controle:CTLUSDT", "directionnel", crit, avec_perp=True)  # signaux_perp
    assert ps.perp_1h is not None and ps.eligibles_perp is not None
    for pan in (pc, ps):
        ws, wp, _ = executer_flux(SRC_COUVERT_PERP, {}, pan, ok, 60)
        assert ws.any() and wp.any(), "la stratégie n'a jamais reçu de perp sur l'univers de contrôle"
    # une fiche directionnel sans signaux_perp ne reçoit rien du perp
    assert essai._panneau(d, "controle:CTLUSDT", "directionnel", crit).perp_1h is None
    assert FicheEssai("S", "directionnel", "c" * 64, signaux_perp=True).signaux_perp


# --------------------------------------------------------------------------------------------------
# 2. L'ordre du funding ne révèle pas la permutation
# --------------------------------------------------------------------------------------------------


def test_ordre_funding_independant_de_la_permutation():
    pan = synthetique_varie(200, 15, 3, avec_perp=True)
    for graine in range(3):
        perm = np.random.default_rng(graine).permutation(15)
        pp = pan.permuter(perm)
        for i in (120, 150, 199):
            msgs = pp.jour(i).funding
            idx = [k for k, _ in msgs]
            assert idx == sorted(idx), "les échéances doivent être triées par colonne permutée"
            # à colonne égale, ordre chronologique (les taux suivent les horodatages)
            ts = pp.funding_ts[i]
            tri = np.lexsort((ts, pp.funding_idx[i]))
            assert [t for _, t in msgs] == pp.funding_taux[i][tri].tolist()


SRC_PREMIER_FUNDING = b'''
import numpy as np
class Strategie:
    def __init__(self, n, **p): self.n = n
    def pas(self, j):
        w = np.zeros(self.n)
        if j.funding:
            w[j.funding[0][0]] = 0.5
        return w, np.zeros(self.n)
'''


def test_flux_ne_depend_pas_de_la_permutation_via_le_funding():
    pan = synthetique_varie(120, 15, 5, avec_perp=True)
    sorties = []
    for graine in (1, 2):
        perm = np.random.default_rng(graine).permutation(15)
        ws, _wp, _ = executer_flux(SRC_PREMIER_FUNDING, {}, pan.permuter(perm), ok, 60)
        sorties.append(ws)
    # dans le repère des COLONNES du flux, la stratégie voit la même chose quelle que soit la permutation
    assert np.array_equal(sorties[0], sorties[1])


# --------------------------------------------------------------------------------------------------
# 3. Évasion du contrôle AST
# --------------------------------------------------------------------------------------------------

GAB = ("import collections, numpy as np\nclass Strategie:\n    def __init__(self, n, **p):\n        self.n = n\n"
       "    def pas(self, jour):\n{corps}\n        return np.zeros(self.n), np.zeros(self.n)\n")


def _src(corps: str) -> str:
    return GAB.format(corps="\n".join("        " + ligne for ligne in corps.splitlines()))


REFUSES = {
    "collections._sys": "m = collections._sys.modules",
    "alias_prive": "import collections as _c",
    "from_import_prive": "from collections import _sys",
    "kw_prive": "f = dict(_x=1)",
    "nom_prive": "_s = 1",
    "np_ma_inspect": "m = np.ma.extras.ma.operator",
    "np_char_inspect": "m = np.char.overrides.inspect",
    "from_numpy_ma": "from numpy import ma",
    "type": "t = type(self)",
    "dir": "t = dir(self)",
    "getattr": "t = getattr(self, 'n')",
    "vars": "t = vars(self)",
    "setattr": "setattr(self, 'n', 1)",
    "delattr": "delattr(self, 'n')",
    "ndarray_dump": "np.zeros(3).dump('/tmp/x')",
    "np_load": "np.load('/tmp/x')",
    "np_lib": "np.lib.npyio",
    "np_ctypeslib": "np.ctypeslib",
    "np_testing": "np.testing",
    "np_f2py": "np.f2py",
    "np_memmap": "np.memmap('/tmp/x')",
    "np_tofile": "np.zeros(3).tofile('/tmp/x')",
    "statistics_sys": "import statistics\nstatistics.sys",
    "self_rebondi": "self = collections",
    "self_rebondi_for": "for self in [collections]:\n    pass",
    "self_rebondi_import": "import collections as self",
    "classe_locale_non_liee": "Strategie.pas(collections, None)",
    "int_litteral": "x = int('1010', 2)",
    "float_litteral": "x = float('1.5')",
    "bytes_litteral": "x = bytes('ab', 'ascii')",
    "bytearray_litteral": "x = bytearray('ab', 'ascii')",
    "ord_litteral": "x = ord('a')",
    "fromhex": "x = bytes.fromhex('ab')",
    "int_fstring": "x = int(f'{1}0')",
    "entier_65_bits": f"x = {1 << 64}",
    "entier_negatif_65_bits": f"x = -{1 << 64}",
    "chaines_total": "\n".join(f"s{i} = '{'a' * 60}'" for i in range(9)),
}


@pytest.mark.parametrize("nom", REFUSES)
def test_source_refusee(nom):
    corps = REFUSES[nom]
    texte = _src(corps)
    if nom == "classe_locale_non_liee":
        texte = (GAB.format(corps="        return np.zeros(self.n), np.zeros(self.n)")
                 + "def aide(self):\n    return self._sys\nStrategie.aide(collections)\n")
    with pytest.raises(SourceRefusee):
        verifier_source(texte)


def test_fonction_hors_classe_avec_self_refusee():
    texte = GAB.format(corps="        pass") + "\ndef aide(self):\n    return self._sys\n"
    with pytest.raises(SourceRefusee):
        verifier_source(texte)


ACCEPTES = {
    "attribut_prive_de_self": "self._x = 1\nself._y = self._x + 1",
    "nom_jetable": "a = [0 for _ in range(3)]",
    "entier_64_bits": f"x = {(1 << 64) - 1}",
    "chaines_court": "\n".join(f"s{i} = '{'a' * 60}'" for i in range(2)),
    "float_sur_variable": "x = float(self.n)",
}


@pytest.mark.parametrize("nom", ACCEPTES)
def test_source_acceptee(nom):
    verifier_source(_src(ACCEPTES[nom]))


def test_docstrings_longues_exclues_du_total():
    longue = "x" * 2000
    src = (f'"""{longue}"""\nimport numpy as np\nclass Strategie:\n    """{longue}"""\n'
           f'    def __init__(self, n):\n        """{longue}"""\n        self.n = n\n'
           "    def pas(self, jour):\n        return np.zeros(self.n), np.zeros(self.n)\n")
    verifier_source(src)
    # une chaîne longue qui n'est PAS une docstring est comptée
    src2 = src.replace("        self.n = n\n", f"        self.n = n\n        '{'y' * 60}'\n        s = '{'z' * 500}'\n")
    with pytest.raises(SourceRefusee):
        verifier_source(src2)


def test_strategies_gelees_vague1_passent_le_controle():
    fichiers = sorted(VAGUE1.glob("*.py"))
    assert len(fichiers) == 5
    for f in fichiers:
        verifier_source(f.read_text(encoding="utf-8"), f.name)


def test_aucun_chemin_attribut_vers_un_module_hors_liste_blanche():
    """Parcours des attributs publics (hors ceux que le contrôle refuse) des modules de la liste blanche :
    aucun module hors numpy / liste blanche ne doit rester atteignable (régression sur une mise à jour)."""
    sures = set(bac_a_sable.IMPORTS_PERMIS)
    racines = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import bisect
        import collections
        import functools
        import heapq
        import itertools
        import math
        import statistics

        import numpy as np
        racines = {"numpy": np, "collections": collections, "statistics": statistics, "math": math,
                   "itertools": itertools, "functools": functools, "heapq": heapq, "bisect": bisect}
        vus, sorties = set(), {}

        def interne(m):
            t = m.__name__.split(".")[0]
            return t == "numpy" or t in sures

        def parcourir(m, chemin):
            if id(m) in vus:
                return
            vus.add(id(m))
            for a in dir(m):
                if bac_a_sable.attribut_interdit(a):
                    continue
                try:
                    v = getattr(m, a)
                except Exception:  # noqa: BLE001, S112
                    continue
                if isinstance(v, types.ModuleType):
                    if interne(v):
                        parcourir(v, f"{chemin}.{a}")
                    else:
                        sorties[f"{chemin}.{a}"] = v.__name__

        for n, m in racines.items():
            parcourir(m, n)
    assert sorties == {}, sorties
    assert sys.modules  # le parcours n'a rien importé de dangereux dans ce processus


def test_arbre_ast_ne_cite_aucun_chemin_prive_dans_les_stategies_gelees():
    for f in sorted(VAGUE1.glob("*.py")):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Attribute) and n.attr.startswith("_"):
                assert isinstance(n.value, ast.Name) and n.value.id == "self", (f.name, n.attr)


# --------------------------------------------------------------------------------------------------
# 5. Date par compteur de jours : k jours d'échauffement retirés du flux
# --------------------------------------------------------------------------------------------------

SRC_COMPTEUR = (b"import numpy as np\nclass Strategie:\n    def __init__(self, n, **p):\n        self.n = n; self.c = 0\n"
                b"    def pas(self, j):\n        self.c += 1\n        w = np.zeros(self.n); w[0] = self.c / 1000.0\n"
                b"        return w, np.zeros(self.n)\n")


def test_jours_retires_ne_sont_pas_envoyes():
    pan = synthetique(30, 3, 0, avec_1h=False, cotations_tardives=False)
    appels = []

    def valider(i, a, b):
        appels.append(i)

    ws, _wp, n_ok = executer_flux(SRC_COMPTEUR, {}, pan, valider, 60, jours_retires=7, decalage=20_000)
    assert appels == list(range(7, 30)) and n_ok == 30
    assert (ws[:7] == 0).all()
    assert ws[7, 0] == pytest.approx(1 / 1000) and ws[-1, 0] == pytest.approx(23 / 1000)
    ws0, _wp0, _ = executer_flux(SRC_COMPTEUR, {}, pan, ok, 60)
    assert ws0[0, 0] == pytest.approx(1 / 1000)  # k = 0 : comportement inchangé
    with pytest.raises(ValueError):
        executer_flux(SRC_COMPTEUR, {}, pan, ok, 60, jours_retires=30)


def test_tirage_borne_et_evaluation_intacte(crit):  # noqa: F811
    deb2020 = int(pd.Timestamp("2020-01-01", tz="UTC").timestamp())
    grand = synthetique(1000, 3, 0, avec_1h=False)  # 2018-01-01 : 730 jours d'échauffement
    ks = {bac_a_sable.tirer_jours_retires(grand, crit) for _ in range(300)}
    assert min(ks) >= 0 and max(ks) < 365 and len(ks) > 50
    assert all(730 - k >= 365 for k in ks)  # échauffement restant >= 365 jours
    court = synthetique(1000, 3, 0, avec_1h=False, debut_jour=deb2020 - 380 * 86400)
    assert {bac_a_sable.tirer_jours_retires(court, crit) for _ in range(100)} <= set(range(16))  # 380 - k >= 365
    sans = synthetique(100, 3, 0, avec_1h=False, debut_jour=deb2020)
    assert {bac_a_sable.tirer_jours_retires(sans, crit) for _ in range(50)} == {0}


def test_meme_k_pour_execution_principale_et_rejeu_reel(tmp_path, journal, crit):  # noqa: F811
    pan = synthetique(700, 4, 1, avec_1h=False, cotations_tardives=False)
    code = ecrire(tmp_path, "import numpy as np\nclass Strategie:\n    def __init__(self, n, **p):\n        self.n = n\n"
                  "    def pas(self, j):\n        e = j.eligibles.astype(float)\n"
                  "        return e / max(e.sum(), 1.0), np.zeros(self.n)\n")
    vu = []
    vrai = bac_a_sable.executer_flux

    def espion(source, params, panneau, validateur, timeout_s, **kw):
        vu.append((panneau.n_jours, kw.get("jours_retires")))
        return vrai(source, params, panneau, validateur, timeout_s, **kw)

    mp = pytest.MonkeyPatch()
    mp.setattr(bac_a_sable, "executer_flux", espion)
    try:
        r = executer_essai(FicheEssai("F1", "directionnel", "a" * 64), code, {}, pan, journal, crit,
                           causalite=True, test=True)
    finally:
        mp.undo()
    assert r.code == "OK", r.detail
    reels = [k for n, k in vu if n == 700]
    assert len(reels) == 2 and reels[0] == reels[1] and 0 <= reels[0] < 336  # 700 - 365 + 1
    synth = {k for n, k in vu if n == 1300}
    assert len(synth) == 1  # un seul tirage pour tous les rejeux synthétiques


# --------------------------------------------------------------------------------------------------
# 6. Causalité réelle : rejeu avec un dérangement relatif à la permutation principale
# --------------------------------------------------------------------------------------------------


def test_derangement_relatif():
    rng = np.random.default_rng(0)
    for n in (2, 3, 6, 15):
        for _ in range(50):
            ref = rng.permutation(n)
            p = essai._derangement(rng, ref)
            assert sorted(p.tolist()) == list(range(n)) and (p != ref).all()
    assert essai._derangement(rng, np.array([0])).tolist() == [0]


def test_controle_reel_detecte_toujours_la_fuite_de_colonne():
    src = (STRAT / "fuite_colonne.py").read_bytes()
    pan = synthetique(60, 6, 4, avec_1h=False, cotations_tardives=False)
    rng = np.random.default_rng(0)
    detections = 0
    for _ in range(20):
        perm = rng.permutation(6)
        ws, wp, _ = essai._courir(src, {}, pan.permuter(perm), "directionnel", 0.5, 60, True)
        ws_o, wp_o = np.empty_like(ws), np.empty_like(wp)
        ws_o[:, perm], wp_o[:, perm] = ws, wp
        detections += essai._controle_reel(src, {}, pan, "directionnel", 0.5, 60, ws_o, wp_o,
                                           perm_ref=perm) > 1e-9
    assert detections == 20


# --------------------------------------------------------------------------------------------------
# 7. tmpfs du bac à sable borné
# --------------------------------------------------------------------------------------------------


def test_tmpfs_borne():
    cmd = bac_a_sable._commande("/job", "_worker.py", [])
    i = cmd.index("--tmpfs")
    assert cmd[i - 2:i] == ["--size", str(256 * 2**20)] and cmd[i + 1] == "/tmp"


def test_budget_de_bits_des_litteraux_ferme_le_canal_bytes_et_le_cumul():
    """Revue 2 bis : un littéral bytes lu par index, ou 32 entiers de 64 bits + 512 caractères, codaient
    jusqu'à 6 144 bits de calendrier ; le budget total est de 1 024 bits (gelées : 908 au plus)."""
    import glob

    from recherche.moteur.bac_a_sable import SourceRefusee, verifier_source
    tete = "import numpy as np\n\n\nclass Strategie:\n    def __init__(self, n, **p):\n        self.n = n\n"
    pas = "    def pas(self, j):\n        return np.zeros(self.n), np.zeros(self.n)\n"
    with pytest.raises(SourceRefusee, match="bytes"):
        verifier_source(tete + "        self.c = b'abc'\n" + pas)
    with pytest.raises(SourceRefusee, match="ASCII"):
        verifier_source(tete + "        self.c = 'é'\n" + pas)
    ints = "".join(f"        self.v{i} = {(1 << 63) + i}\n" for i in range(20))  # 20 x 64 bits = 1 280 bits
    with pytest.raises(SourceRefusee, match="bits de littéraux"):
        verifier_source(tete + ints + pas)
    for f in sorted(glob.glob("recherche/vagues/1/strategies/*.py")):
        verifier_source(Path(f).read_text(), f)
