"""Exécution d'un essai : `debut` -> causalité synthétique -> flux réel dans le bac à sable -> simulation -> `fin`.

L'agent appelant ne reçoit que le code fermé (`ResultatEssai.pour_agent()`). Les séries et métriques complètes
restent dans `ResultatEssai.serie` / `.metriques`, pour l'orchestrateur et les portes.

Canaux de sortie (une stratégie est du code hostile qui voit le résultat de ses propres essais) :
- texte : `detail` et le journal technique ne contiennent AUCUN texte venant de la stratégie (ni message
  d'exception, ni trace) : le code fermé, le type d'exception standard et le numéro de jour du flux ;
- temps : les horodatages de `debut`/`fin` sont arrondis à la minute (`JournalRecherche._ts`) ;
- bit résiduel : le code fermé lui-même (6 valeurs) reste lisible par l'agent, et la stratégie choisit s'il
  est OK, ERREUR, TIMEOUT ou FORME_POIDS (et, via le numéro de jour de l'erreur, un jour parmi T pour le
  journal technique, que l'agent ne lit pas). Au plus log2(6) ~ 2,6 bits par essai exposés à l'agent, donc
  au plus ~1 600 bits sur tout recherche-v1 (N <= 600) : le plafond d'essais borne le canal, il ne le ferme pas.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
import os
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from recherche.moteur import bac_a_sable, contrat
from recherche.moteur.contrat import (
    ERREUR,
    OK,
    ErreurEssai,
    FormePoids,
    SourceRefusee,
)
from recherche.moteur.journal import AncrageError, JournalRecherche, decimal12, params_canoniques
from recherche.moteur.panneau import JOUR_S, Panneau, panneau_depuis_donnees, synthetique_varie
from recherche.moteur.portefeuille import CLASSES, SerieMoteur, rapporter, simuler, valider_poids

VERSION_MOTEUR = "recherche-moteur-v2"


class PlafondError(Exception):
    """Le plafond total d'essais (criteres.essais.plafond_total) est atteint : aucun essai de plus."""


@dataclass(frozen=True)
class FicheEssai:
    """Ce que le moteur retient d'une fiche : famille, classe (déclarée avant tout essai), sha256 du fichier."""

    famille: str
    classe: str
    fiche_sha256: str
    signaux_perp: bool = False  # directionnel : reçoit barres perp et funding comme SIGNAUX (jambe perp nulle)


@dataclass
class ResultatEssai:
    id: str
    code: str
    univers: str
    serie: SerieMoteur | None = None
    metriques: dict = field(default_factory=dict)
    detail: str = ""  # technique : orchestrateur seulement
    causalite: dict | None = None

    def pour_agent(self) -> str:
        """Le seul retour destiné à un agent : un code fermé."""
        return self.code


# ----------------------------------------------------------------------------------------------------
# Métriques (strictement ce qu'il faut au journal ; les portes recalculent le reste avec leur propre code)
# ----------------------------------------------------------------------------------------------------


def _sharpe(r: np.ndarray) -> float:
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    return float(r.mean() / sd * math.sqrt(365)) if sd > 0 else float("nan")


def _drawdown(r: np.ndarray) -> float:
    nav = np.concatenate([[1.0], np.cumprod(1.0 + r)])
    return float((1.0 - nav / np.maximum.accumulate(nav)).max())


def _t_nw(r: np.ndarray, retards: int = 20) -> float:
    x = r - r.mean()
    n = len(x)
    lrv = float(x @ x) / n
    for k in range(1, retards + 1):
        lrv += 2.0 * (1.0 - k / (retards + 1)) * float(x[k:] @ x[:-k]) / n
    return float(r.mean() / math.sqrt(lrv / n)) if lrv > 0 else float("nan")


def _annualise(r: np.ndarray) -> float:
    n = len(r)
    nav = float(np.prod(1.0 + r))
    return nav ** (365.0 / n) - 1.0 if n and nav > 0 else float("nan")


def calculer_metriques(serie: SerieMoteur) -> dict:
    """Métriques du journal sur les jours de la fenêtre d'évaluation (masque_eval)."""
    m = serie.masque_eval
    net, net2, brut = serie.rendements_nets[m], serie.rendements_nets_stresses[m], serie.rendements_bruts[m]
    n = len(net)
    if n < 3:
        return {"T": n}
    sd = net.std(ddof=1)
    c = net - net.mean()
    s2 = float((c**2).mean())
    annees = {}
    ans = np.asarray((serie.jours[m].astype("datetime64[s]").astype("datetime64[Y]").astype(int)) + 1970)
    for a in range(2020, 2026):
        ra = net[ans == a]
        annees[str(a)] = _sharpe(ra) if len(ra) > 2 else float("nan")
    return {
        "T": n,
        "sharpe_net": _sharpe(net),
        "sr_jour": float(net.mean() / sd) if sd > 0 else float("nan"),
        "skew": float((c**3).mean() / s2**1.5) if s2 > 0 else float("nan"),
        "kurt": float((c**4).mean() / s2**2) if s2 > 0 else float("nan"),
        "drawdown": _drawdown(net),
        "rotation_annuelle": float(serie.rotation[m].sum() / (n / 365.0)),
        "t_nw20": _t_nw(net),
        "sharpe_net_couts_x2": _sharpe(net2),
        "rendement_annualise_net": _annualise(net),
        "rendement_annualise_brut": _annualise(brut),
        "cout_total_annualise": float(serie.couts[m].sum() / (n / 365.0)),
        "capital_immobilise_moyen": float(serie.exposition[m].mean()),
        "sharpe_par_annee": annees,
        "serie_sha256": hashlib.sha256(np.ascontiguousarray(net).tobytes()).hexdigest(),
    }


def serie_portes(serie: SerieMoteur) -> SerieMoteur:
    """La série telle que les portes la voient : pour `couvert`, rapportée au capital immobilisé de référence
    max(expo_j, expo_{j-1}) (même transformation que `portes.adaptateur`) ; `directionnel` : inchangée."""
    if serie.classe != "couvert":
        return serie
    def r(x):
        return rapporter(x, serie.exposition)
    return dataclasses.replace(
        serie, rendements_nets=r(serie.rendements_nets), rendements_nets_stresses=r(serie.rendements_nets_stresses),
        rendements_bruts=r(serie.rendements_bruts), couts=r(serie.couts))


def calculer_metriques_portes(serie: SerieMoteur) -> dict:
    """Mêmes métriques que `calculer_metriques`, sur la série des portes (capital immobilisé), préfixées
    `portes_` pour ne pas les confondre avec celles sur le capital total."""
    return {f"portes_{k}": v for k, v in calculer_metriques(serie_portes(serie)).items() if k != "T"}


# ----------------------------------------------------------------------------------------------------
# Causalité (C9) sur données synthétiques
# ----------------------------------------------------------------------------------------------------

_CAUSALITE_CACHE: dict = {}
_TOL_CAUSALITE = 1e-9
_JOURS_SYNTH = 1300
VERSION_CAUSALITE = "c9-v2"  # dans la clé du cache : changer le test invalide les résultats mis en cache


def _courir(source: bytes, params: dict, pan: Panneau, classe: str, marge: float, timeout: float,
            strict: bool, jusqu_a: int | None = None, jours_retires: int = 0):
    cotee = np.maximum.accumulate(pan.eligibles, axis=0)

    def valider(i, ws, wp):
        if strict:
            valider_poids(classe, i, ws, wp, cotee[i], None if pan.eligibles_perp is None
                          else pan.eligibles_perp[i], marge)

    return bac_a_sable.executer_flux(source, params, pan, valider, timeout, jusqu_a_erreur=jusqu_a,
                                     jours_retires=jours_retires)


def verifier_causalite(source: bytes, params: dict, criteres, *, classe: str = "directionnel",
                       n_paires: int = 15, avec_1h: bool = True, avec_perp: bool = False,
                       graine_donnees: int | None = None, rng: np.random.Generator | None = None,
                       threads: int = 4, jours_retires: int | None = None) -> dict:
    """C9 sur données synthétiques (jamais réelles). Compare, dans le bac à sable :
    - déterminisme : deux exécutions complètes identiques ;
    - `coupures_aleatoires` + `coupures_fixes` coupures sur `connue_a` : toute donnée connue après la coupure
      est remplacée par du bruit, les poids des jours clos avant la coupure sont inchangés
      (au moins `part_heure_non_pleine_min` des coupures tombent à une heure non pleine) ;
    - permutation des colonnes : les poids suivent la permutation ;
    - échelle : prix × facteur dans [0,1 ; 10], volumes ÷ facteur : poids inchangés.
    Tolérance 1e-9. Renvoie un dict avec `ok` et le détail des contrôles.

    Les données sont `synthetique_varie` : au moins 1 300 jours, régimes variés (tendances, krachs, funding
    élevé positif soutenu ou négatif, base négative, paires qui entrent en cotation) et une graine tirée de
    `os.urandom` À CHAQUE APPEL (`graine_donnees` n'est donné que par les tests) : une stratégie ne peut pas
    reconnaître le jeu de test. Si les poids sont constants sur toute la série, le rapport porte
    `evaluable: False` (rien ne prouve alors la causalité : `adaptateur.vers_rapport_causalite` fait échouer C9).
    `jours_retires` : nombre de jours d'échauffement retirés du flux (None : tiré par appel, un seul tirage
    pour tous les rejeux ; les tests passent 0)."""
    cfg = criteres.portes.C9_causalite
    rng = rng or np.random.default_rng(int.from_bytes(os.urandom(16), "big"))
    if graine_donnees is None:
        graine_donnees = int.from_bytes(os.urandom(8), "big")  # jamais dans une clé de cache
    pan = synthetique_varie(_JOURS_SYNTH, n_paires, graine_donnees, avec_1h=avec_1h, avec_perp=avec_perp)
    T = pan.n_jours
    marge = criteres.marge_perp_part
    timeout = 180.0
    # coupures : instants en secondes UTC
    n_alea, n_fixes = int(cfg.coupures_aleatoires), int(cfg.coupures_fixes)
    min_jour = 40
    coupures = []
    for f in (0.3, 0.55, 0.9)[:n_fixes]:
        coupures.append(int(pan.jours[int(T * f)]) + 12 * 3600)  # 12:00 pile
    jours_tires = rng.choice(np.arange(min_jour, T - 1), size=n_alea, replace=False)
    n_non_pleine = math.ceil(float(cfg.part_heure_non_pleine_min) * (n_alea + n_fixes))
    for k, j in enumerate(jours_tires):
        h = int(rng.integers(0, 24))
        if k < n_non_pleine:
            coupures.append(int(pan.jours[j]) + h * 3600 + int(rng.integers(1, 3600)))
        else:
            coupures.append(int(pan.jours[j]) + h * 3600)
    non_pleines = sum(1 for c in coupures if c % 3600 != 0)
    perm = _permutation_sans_point_fixe(rng, n_paires)
    facteurs = np.exp(rng.uniform(math.log(0.1), math.log(10.0), n_paires))
    # k jours d'échauffement retirés : UN seul tirage pour tous les rejeux de ce contrôle (sinon deux rejeux
    # d'une stratégie qui compte les jours ne seraient pas comparables).
    k_ret = bac_a_sable.tirer_jours_retires(pan, criteres) if jours_retires is None else int(jours_retires)

    def base(_):
        return _courir(source, params, pan, classe, marge, timeout, True, jours_retires=k_ret)

    def coupee(c):
        corr = pan.corrompre_apres(c, rng_local(c))
        ws, wp, n_ok = _courir(source, params, corr, classe, marge, timeout, False, jusqu_a=1, jours_retires=k_ret)
        return c, ws, wp, n_ok

    def rng_local(c):
        return np.random.default_rng([int(c), int.from_bytes(os.urandom(4), "big")])

    def permutee(_):
        p = pan.permuter(perm)
        ws, wp, _n = _courir(source, params, p, classe, marge, timeout, True, jours_retires=k_ret)
        o_s, o_p = np.empty_like(ws), np.empty_like(wp)
        o_s[:, perm], o_p[:, perm] = ws, wp
        return o_s, o_p

    def echelle(_):
        ws, wp, _n = _courir(source, params, pan.mettre_a_l_echelle(facteurs), classe, marge, timeout, True,
                             jours_retires=k_ret)
        return ws, wp

    res = {"ok": False, "n_coupures": len(coupures), "coupures_heure_non_pleine": non_pleines}
    try:
        with ThreadPoolExecutor(max_workers=threads) as ex:
            f_base = [ex.submit(base, k) for k in (0, 1)]
            f_cut = [ex.submit(coupee, c) for c in coupures]
            f_perm = ex.submit(permutee, 0)
            f_ech = ex.submit(echelle, 0)
            (w1s, w1p, _), (w2s, w2p, _) = (f.result() for f in f_base)
            coupes = [f.result() for f in f_cut]
            p_s, p_p = f_perm.result()
            e_s, e_p = f_ech.result()
    except ErreurEssai as e:
        res["erreur"] = f"{e.code}: {e.detail}"[:500]
        res["code"] = e.code
        return res
    res["deterministe"] = bool(max(np.abs(w1s - w2s).max(), np.abs(w1p - w2p).max()) <= _TOL_CAUSALITE)
    res["evaluable"] = bool(np.ptp(w1s, axis=0).max() > _TOL_CAUSALITE or np.ptp(w1p, axis=0).max() > _TOL_CAUSALITE)
    res["n_jours"] = int(T)
    ecart_cut = 0.0
    for c, ws, wp, n_ok in coupes:
        clos = int(np.sum(pan.jours + JOUR_S <= c))  # jours dont la clôture <= coupure
        k = min(clos, n_ok)
        if k < clos:
            ecart_cut = float("inf")  # la stratégie a échoué avant la coupure sur des données propres
            continue
        ecart_cut = max(ecart_cut, float(np.abs(ws[:clos] - w1s[:clos]).max()),
                        float(np.abs(wp[:clos] - w1p[:clos]).max()))
    res["ecart_coupures"] = ecart_cut
    res["ecart_permutation"] = float(max(np.abs(p_s - w1s).max(), np.abs(p_p - w1p).max()))
    res["ecart_echelle"] = float(max(np.abs(e_s - w1s).max(), np.abs(e_p - w1p).max()))
    res["ok"] = bool(res["deterministe"] and ecart_cut <= _TOL_CAUSALITE
                     and res["ecart_permutation"] <= _TOL_CAUSALITE and res["ecart_echelle"] <= _TOL_CAUSALITE
                     and non_pleines >= float(cfg.part_heure_non_pleine_min) * len(coupures) - 1e-9)
    return res


# ----------------------------------------------------------------------------------------------------
# Essai
# ----------------------------------------------------------------------------------------------------

_PANNEAUX: list = []


def _champ(fiche, nom):
    return fiche[nom] if isinstance(fiche, Mapping) else getattr(fiche, nom)


def _signaux_perp(fiche, classe: str) -> bool:
    """Une fiche couvert reçoit toujours perp et funding ; une fiche directionnel seulement si elle le déclare
    (`signaux_perp: true`), et alors comme signaux : `valider_poids` impose toujours une jambe perp nulle."""
    if classe == "couvert":
        return True
    v = fiche.get("signaux_perp", False) if isinstance(fiche, Mapping) else getattr(fiche, "signaux_perp", False)
    return bool(v)


def _panneau(donnees, univers: str, classe: str, criteres, avec_perp: bool | None = None) -> Panneau:
    if avec_perp is None:
        avec_perp = classe == "couvert"
    if isinstance(donnees, Panneau):
        pan = donnees
        if univers.startswith("controle:"):
            pan = pan.sous_univers([univers.split(":", 1)[1]])
        elif univers == "arene":
            pan = pan.sous_univers(list(criteres.univers_arene))
        elif univers != "principal":
            raise ValueError(f"univers inconnu : {univers!r}")
    else:
        for d, u, c, p in _PANNEAUX:
            if d is donnees and u == univers and c == avec_perp:
                return p
        pan = panneau_depuis_donnees(donnees, univers, avec_perp=avec_perp,
                                     symboles_arene=tuple(criteres.univers_arene))
        _PANNEAUX.append((donnees, univers, avec_perp, pan))
        del _PANNEAUX[:-4]
        return pan
    return pan


def _sans_perp(pan: Panneau) -> Panneau:
    z = tuple(a[:0] for a in pan.funding_idx)
    return Panneau(pan.symboles, pan.jours, pan.spot_1d, pan.spot_1h, None, pan.eligibles, None, z,
                   tuple(a[:0] for a in pan.funding_taux), tuple(a[:0] for a in pan.funding_ts))


def _permutation_sans_point_fixe(rng: np.random.Generator, n: int) -> np.ndarray:
    """Permutation qui déplace chaque colonne (sinon le test de permutation pourrait ne rien tester)."""
    while True:
        perm = rng.permutation(n)
        if n < 2 or (perm != np.arange(n)).all():
            return perm


def _derangement(rng: np.random.Generator, ref: np.ndarray) -> np.ndarray:
    """Permutation `p` avec `p[k] != ref[k]` pour tout k : aucune colonne du rejeu ne porte la même paire que
    dans l'exécution de référence (sinon une stratégie qui fuit l'indice de colonne ne serait pas détectée
    sur ces colonnes). Impossible pour n = 1 (une seule paire) : renvoie alors `ref`."""
    n = len(ref)
    if n < 2:
        return np.asarray(ref).copy()
    while True:
        p = rng.permutation(n)
        if (p != ref).all():
            return p


def _controle_reel(source: bytes, params: dict, pan: Panneau, classe: str, marge: float, timeout: float,
                   ws_o: np.ndarray, wp_o: np.ndarray, perm_ref: np.ndarray | None = None,
                   jours_retires: int = 0) -> float:
    """Second contrôle de causalité/invariance, sur les données RÉELLES de l'essai : rejoue la stratégie avec une
    autre permutation et d'autres facteurs d'échelle par paire (tirés par appel, `os.urandom`) ; renvoie l'écart
    maximal des poids, dans le repère des paires réelles, avec ceux de l'exécution principale.
    `perm_ref` : permutation de l'exécution principale ; le rejeu en tire un dérangement relatif (chaque colonne
    change de paire entre les deux exécutions). `jours_retires` : le même k que l'exécution principale."""
    rng = np.random.default_rng(int.from_bytes(os.urandom(16), "big"))
    n = pan.n_paires
    perm = _permutation_sans_point_fixe(rng, n) if perm_ref is None else _derangement(rng, np.asarray(perm_ref))
    facteurs = np.exp(rng.uniform(math.log(0.1), math.log(10.0), n))
    p2 = pan.mettre_a_l_echelle(facteurs).permuter(perm)
    ws, wp, _ = _courir(source, params, p2, classe, marge, timeout, True, jours_retires=jours_retires)
    o_s, o_p = np.empty_like(ws), np.empty_like(wp)
    o_s[:, perm], o_p[:, perm] = ws, wp
    return float(max(np.abs(o_s - ws_o).max(), np.abs(o_p - wp_o).max()))


def executer_essai(fiche, code_path: str | Path, params: dict, donnees, journal: JournalRecherche, criteres,
                   univers: str = "principal", *, journal_arene: str | Path | None = None,
                   convention_rotation: str = "derive", permutation: np.ndarray | None = None,
                   causalite: bool = True, timeout_s: float | None = None,
                   cout_spot_bp: int | None = None, cout_perp_bp: int | None = None,
                   test: bool = False, jours_retires: int | None = None,
                   tirage_k: int | None = None) -> ResultatEssai:
    """Un essai complet. `donnees` : `Donnees` du chargeur ou `Panneau`. Lève `PlafondError` (plafond total),
    `CanariError` (bac à sable défaillant), `AncrageError` (journal incohérent, ou `journal_arene` absent sans
    `test=True`) : ce ne sont pas des essais. Tout autre échec est un essai : `debut` et `fin` sont écrits
    et le code fermé est rendu.

    `journal_arene` est OBLIGATOIRE (ancrage externe, protocole §4) sauf si `test=True` (tests seulement).
    L'ancre est écrite juste après `debut` ET juste après `fin`. `debut` consigne toutes les surcharges
    (causalite, cout_spot_bp, cout_perp_bp, convention_rotation, timeout_s, permutation imposée, test).
    `convention_rotation="cible"` et `cout_spot_bp=15` reproduisent le moteur du labo (acceptation E0065).

    Si `causalite`, deux contrôles : C9 sur synthétique (`verifier_causalite`, graine tirée par appel) puis,
    sur les données réelles de l'essai, rejeu avec une autre permutation et d'autres facteurs d'échelle par
    paire (poids identiques à 1e-9 près) ; un écart donne le code CAUSALITE.

    `jours_retires` : nombre k de jours d'échauffement retirés au DÉBUT du flux envoyé à la stratégie. None :
    tiré une fois par essai (`os.urandom`, dans [0, 365), échauffement restant >= 365 jours, fenêtre
    d'évaluation intacte), le même pour l'exécution principale et son rejeu sur données réelles. Les tests
    d'acceptation de reproduction exacte du labo (E0065, panier) passent `jours_retires=0` : le labo
    démarrait sa série au premier jour des données et la phase de rebalancement (H = 10 jours) en dépend."""
    classe = _champ(fiche, "classe")
    if classe not in CLASSES:
        raise ValueError(f"classe {classe!r} inconnue")
    if journal_arene is None and not test:
        raise AncrageError("journal_arene obligatoire (ancrage externe) ; test=True réservé aux tests")
    bac_a_sable.canari()
    journal.demarrer()
    journal.verifier_ancrage(journal_arene)
    if journal.n_ids() >= criteres.plafond_total:
        raise PlafondError(f"{journal.n_ids()} essais déjà commencés, plafond {criteres.plafond_total}")
    source = Path(code_path).read_bytes()  # lu UNE fois : ce texte est haché, contrôlé et exécuté
    eid = journal.prochain_id()
    journal.debut({
        "id": eid, "famille": _champ(fiche, "famille"), "classe": classe,
        "fiche_sha256": _champ(fiche, "fiche_sha256"), "code_sha256": hashlib.sha256(source).hexdigest(),
        "params": params_canoniques(params), "univers": univers, "criteres_sha256": criteres.sha256,
        "moteur": VERSION_MOTEUR,
        "surcharges": {"causalite": bool(causalite), "cout_spot_bp": cout_spot_bp, "cout_perp_bp": cout_perp_bp,
                       "convention_rotation": convention_rotation, "timeout_s": timeout_s,
                       "permutation_imposee": permutation is not None, "test": bool(test),
                       "jours_retires": jours_retires}})
    journal.ancrer(journal_arene)
    res = ResultatEssai(id=eid, code=ERREUR, univers=univers)
    k_ret = None
    try:
        bac_a_sable.verifier_source(source.decode("utf-8", "replace"), Path(code_path).name)
        signaux = _signaux_perp(fiche, classe)
        pan = _panneau(donnees, univers, classe, criteres, avec_perp=signaux)
        if not signaux and pan.perp_1h is not None:
            pan = _sans_perp(pan)
        k_ret = (bac_a_sable.tirer_jours_retires(pan, criteres, tirage=tirage_k) if jours_retires is None
                 else int(jours_retires))
        if causalite:
            cle = (hashlib.sha256(source).hexdigest(), params_canoniques(params), criteres.sha256, pan.n_paires,
                   pan.spot_1h is not None, pan.perp_1h is not None, classe, _JOURS_SYNTH, VERSION_CAUSALITE)
            if cle not in _CAUSALITE_CACHE:
                _CAUSALITE_CACHE[cle] = verifier_causalite(
                    source, params, criteres, classe=classe, n_paires=pan.n_paires,
                    avec_1h=pan.spot_1h is not None, avec_perp=pan.perp_1h is not None)
            res.causalite = dict(_CAUSALITE_CACHE[cle])
            if not res.causalite["ok"]:
                res.code = res.causalite.get("code", contrat.CAUSALITE)
                # aucune valeur ni texte issus de la stratégie : les noms des contrôles en échec seulement
                echecs = [k for k in ("deterministe",) if not res.causalite.get(k, True)]
                echecs += [k for k in ("ecart_coupures", "ecart_permutation", "ecart_echelle")
                           if res.causalite.get(k, 0.0) > _TOL_CAUSALITE]
                res.detail = f"causalité synthétique en échec : {echecs or res.causalite.get('erreur', '?')}"
                return res
        perm = (np.random.default_rng(int.from_bytes(os.urandom(16), "big")).permutation(pan.n_paires)
                if permutation is None else np.asarray(permutation))
        ppan = pan.permuter(perm)
        delai = timeout_s or float(criteres.timeout_essai_s)
        ws, wp, _ = _courir(source, params, ppan, classe, criteres.marge_perp_part, delai, True,
                            jours_retires=k_ret)
        ws_o, wp_o = np.empty_like(ws), np.empty_like(wp)
        ws_o[:, perm], wp_o[:, perm] = ws, wp
        if causalite:
            ecart = _controle_reel(source, params, pan, classe, criteres.marge_perp_part, delai, ws_o, wp_o,
                                   perm_ref=perm, jours_retires=k_ret)
            res.causalite["ecart_reel"] = ecart
            res.causalite["reel_ok"] = bool(ecart <= _TOL_CAUSALITE)
            if not res.causalite["reel_ok"]:
                res.code = contrat.CAUSALITE
                res.detail = "causalité sur données réelles en échec (permutation et échelles différentes)"
                return res
        res.serie = simuler(pan, ws_o, wp_o, classe, criteres, convention_rotation=convention_rotation,
                            cout_spot_bp=cout_spot_bp, cout_perp_bp=cout_perp_bp)
        res.metriques = {**calculer_metriques(res.serie), **calculer_metriques_portes(res.serie)}
        res.code = OK
    except ErreurEssai as e:
        res.code, res.detail = e.code, e.detail
    except Exception as e:  # noqa: BLE001
        res.code, res.detail = ERREUR, type(e).__name__  # jamais le message (canal de sortie)
    finally:
        fin = {"id": eid, "statut": res.code}
        if k_ret is not None:
            fin["jours_retires"] = int(k_ret)  # k tiré pour cet essai (reproductibilité)
        if res.code == OK:
            for k, v in res.metriques.items():
                fin[k] = {a: decimal12(x) for a, x in v.items()} if isinstance(v, dict) else \
                    (v if isinstance(v, str) else decimal12(v))
        journal.fin(fin)
        if res.detail:
            journal.technique(eid, res.detail)
        journal.ancrer(journal_arene)
    return res


__all__ = [
    "FicheEssai",
    "FormePoids",
    "PlafondError",
    "ResultatEssai",
    "SourceRefusee",
    "calculer_metriques",
    "calculer_metriques_portes",
    "executer_essai",
    "verifier_causalite",
]
