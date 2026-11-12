"""Orchestration codée d'une vague de recherche (ARCHITECTURE.md, PROTOCOLE §4, §6, §7).

Aucun LLM ne décide d'un passage : ce module lit des fiches (YAML), lance le moteur sur chaque point de grille,
applique les portes C1-C16, sélectionne et écrit les rapports. Tout chemin est un paramètre (tests en tmp).

Format d'une fiche `fiches_dir/<nom>.yaml` (champs obligatoires) :
    famille, nom, mecanisme, classe (directionnel|couvert), strategie (nom de fichier de `strategies_dir`),
    grille (paramètre -> liste de valeurs, géométrique : >= 3 valeurs, rapport >= 1,25), params_fixes (facultatif).
Le reste de la fiche (qui perd de l'autre côté, prédiction falsifiable...) est haché avec elle mais n'est pas lu
ici : l'auditeur de fiche est un agent distinct.

Chemins de production : `recherche/vagues/<n>/fiches/` et `recherche/vagues/<n>/strategies/`.

Gel (deux niveaux, tous deux requis) :
  1. `fiches_dir/MANIFESTE.json` {fichier: sha256}, écrit par `geler_fiches` AVANT la vague ;
  2. le contenu de chaque fiche ET de chaque stratégie est comparé octet pour octet au tag git
     `recherche-vague-<n>-fiches` (`git show`) : toute différence, fichier absent du disque ou en trop → refus.
     Il n'y a plus d'option pour s'en passer ; les tests passent un faux dépôt git (`depot=`).

Intégrité de la recherche :
  * `criteres.yaml` : `config.verifier_criteres` est appelée au lancement ET avant chaque essai (le moteur,
    `executer_essai`, l'appelle aussi).
  * Reprise : une vague interrompue peut être relancée. Un essai (famille, paramètres, univers, sha256 du
    code) déjà clos par une `fin` dans le journal n'est PAS relancé : sa série est relue dans le cache
    `<rapports>/series/<id>.npz`, dont le sha256 doit égaler `serie_sha256` de la `fin` (sinon refus). Un
    `debut` sans `fin` reste compté dans N et l'essai est refait sous un nouvel id.
  * Plafonds cumulatifs sur le journal, vérifiés AVANT chaque ligne (grille, C15 et C16 comprises) :
    600 au total ; vague 1 : 120 variantes principales et 6 familles au plus.
  * Numéros de vague et règle d'arrêt : événements chaînés `vague_debut`, `vague_fin`, `decision_owner`
    dans le journal. La vague n > 1 exige que la vague n−1 soit terminée (`vague_fin`) et son rapport
    `vague-<n−1>.md` présent ; si le meilleur DSR de la vague n−1 est < 0,5 (seuil de criteres.yaml), elle exige
    `recherche/vagues/<n>/DECISION-OWNER.md` non vide, dont le sha256 est consigné dans le journal. L'arrêt est
    calculé ici à partir du journal, jamais lu dans un fichier modifiable.
  * V par classe : sr_jour de TOUS les essais de recherche du journal (`sr_jours_du_journal`).
  * Sorties : `vague-<n>-statuts.json` (nom, mécanisme, verdict binaire) est la seule sortie destinée aux
    agents ; tous les chiffres sont dans `vague-<n>.md` (orchestrateur et the owner).
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import yaml

from recherche.config import REPO, verifier_criteres
from recherche.moteur.essai import FicheEssai, PlafondError, ResultatEssai, executer_essai
from recherche.moteur.journal import decimal12, params_canoniques
from recherche.moteur.panneau import panneau_depuis_donnees
from recherche.moteur.portefeuille import SerieMoteur, panier_equipondere
from recherche.portes import stats
from recherche.portes.adaptateur import vers_essai, vers_rapport_causalite, vers_serie_panier
from recherche.portes.evaluer import NON_EVALUABLE, Verdict, evaluer_candidat, grille_valide
from recherche.portes.replay_arene import rejouer
from recherche.portes.selection import Candidat, Selection, selectionner

RAPPORTS_DEFAUT = REPO / "recherche" / "rapports"
VAGUES_DEFAUT = REPO / "recherche" / "vagues"
CHAMPS_FICHE = ("famille", "nom", "mecanisme", "classe", "strategie", "grille")
MANIFESTE_FICHES = "MANIFESTE.json"
DECISION_OWNER = "DECISION-OWNER.md"
EVT_VAGUE_DEBUT, EVT_VAGUE_FIN, EVT_DECISION = "vague_debut", "vague_fin", "decision_owner"
# Portes évaluées avant d'aller chercher C15 et C16 (PROTOCOLE : « pour chaque essai qui passe C1-C14 »).
_PORTES_AVANT = ("C1", "C5", "C6", "C7", "C8", "C9", "C11", "C12", "C13", "C14")


class VagueError(Exception):
    """La vague ne peut pas être lancée (fiches non gelées, plafond, règle d'arrêt...)."""


@dataclass(frozen=True)
class Fiche:
    fichier: str
    sha256: str
    famille: str
    nom: str
    mecanisme: str
    classe: str
    strategie: str
    grille: dict
    params_fixes: dict
    signaux_perp: bool = False  # directionnel : perp et funding transmis comme signaux (jambe perp nulle)


@dataclass
class LigneEssai:
    id: str
    famille: str
    params: dict
    code: str
    verdict: Verdict | None = None
    sharpe_net: float | None = None
    note: str = ""


@dataclass
class RapportVague:
    numero: int
    lignes: list[LigneEssai] = field(default_factory=list)
    refusees: dict[str, str] = field(default_factory=dict)  # fiche -> raison
    selection: Selection | None = None
    candidats: list[str] = field(default_factory=list)  # essais qui passent tout
    meilleur_dsr: float | None = None
    arret: bool = False  # règle d'arrêt : vague suivante interdite sans décision écrite du propriétaire
    n_essais_vague: int = 0  # lignes de grille de la vague (nouvelles ou reprises)
    n_reprises: int = 0  # lignes (grille, C15, C16) relues du journal sans être relancées
    n_lignes_supplementaires: int = 0  # arène + contrôle : comptent dans N réel
    n_reel_total: int = 0
    plafond_atteint: bool = False
    chemin_rapport: Path | None = None
    chemin_statuts: Path | None = None


# --------------------------------------------------------------------------------------------------
# Fiches et gel
# --------------------------------------------------------------------------------------------------


def _sha(octets: bytes) -> str:
    return hashlib.sha256(octets).hexdigest()


def geler_fiches(fiches_dir: Path | str) -> dict:
    """Écrit `MANIFESTE.json` (sha256 de chaque fiche `*.yaml`). À commiter, avec les stratégies, puis à
    étiqueter `recherche-vague-<n>-fiches` AVANT la vague."""
    d = Path(fiches_dir)
    man = {p.name: _sha(p.read_bytes()) for p in sorted(d.glob("*.yaml"))}
    (d / MANIFESTE_FICHES).write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")
    return man


def _git(depot: Path, *args: str) -> bytes:
    r = subprocess.run(["git", "-C", str(depot), *args], capture_output=True, check=False, timeout=120)
    if r.returncode != 0:
        raise VagueError(f"git {' '.join(args[:2])} a échoué : {r.stderr.decode(errors='replace')[-300:].strip()}")
    return r.stdout


def _fichiers_disque(d: Path, depot: Path) -> dict[str, bytes]:
    """{chemin relatif au dépôt: octets} de tous les fichiers de `d` (hors __pycache__) ; liens refusés."""
    out = {}
    for p in sorted(d.rglob("*")):
        if "__pycache__" in p.parts or p.is_dir():
            continue
        if p.is_symlink():
            raise VagueError(f"{p} est un lien symbolique : refusé")
        out[p.relative_to(depot).as_posix()] = p.read_bytes()
    return out


def verifier_gel_git(fiches_dir: Path | str, strategies_dir: Path | str, numero: int, *,
                     depot: Path | str = REPO, tag: str | None = None) -> None:
    """Compare chaque fichier de `fiches_dir` et de `strategies_dir` au contenu du tag git
    `recherche-vague-<numero>-fiches` (par défaut) : même ensemble de fichiers, mêmes octets. Lève
    `VagueError` pour une différence, un fichier absent du tag ou du disque, ou un tag inexistant."""
    tag = tag or f"recherche-vague-{numero}-fiches"
    depot = Path(depot).resolve()
    _git(depot, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}")
    for d in (Path(fiches_dir), Path(strategies_dir)):
        d = d.resolve()
        try:
            rel = d.relative_to(depot).as_posix()
        except ValueError:
            raise VagueError(f"{d} n'est pas dans le dépôt {depot} : gel impossible à vérifier") from None
        liste = _git(depot, "ls-tree", "-r", "-z", "--name-only", f"refs/tags/{tag}", "--", rel)
        dans_tag = {x for x in liste.decode().split("\0") if x and "__pycache__" not in x}
        disque = _fichiers_disque(d, depot)
        if not dans_tag:
            raise VagueError(f"{rel} est absent du tag {tag}")
        if absents := sorted(dans_tag - set(disque)):
            raise VagueError(f"fichier(s) du tag {tag} absent(s) du disque : {absents}")
        if en_trop := sorted(set(disque) - dans_tag):
            raise VagueError(f"fichier(s) en trop par rapport au tag {tag} : {en_trop}")
        for chemin, octets in disque.items():
            if _git(depot, "show", f"refs/tags/{tag}:{chemin}") != octets:
                raise VagueError(f"{chemin} diffère du tag {tag}")


def lire_fiches(fiches_dir: Path | str, strategies_dir: Path | str, numero: int, *,
                depot: Path | str = REPO, tag: str | None = None) -> list[Fiche]:
    """Lit les fiches gelées de la vague `numero` : manifeste, puis tag git (fiches ET stratégies)."""
    d = Path(fiches_dir)
    man_path = d / MANIFESTE_FICHES
    if not man_path.is_file():
        raise VagueError(f"{man_path} absent : fiches non gelées")
    man = json.loads(man_path.read_text())
    fichiers = sorted(p for p in d.glob("*.yaml"))
    if {p.name for p in fichiers} != set(man):
        raise VagueError("les fiches présentes ne sont pas exactement celles du manifeste de gel")
    for p in fichiers:
        if _sha(p.read_bytes()) != man[p.name]:
            raise VagueError(f"{p.name} modifiée depuis le gel (sha256 différent)")
    verifier_gel_git(fiches_dir, strategies_dir, numero, depot=depot, tag=tag)
    out = []
    for p in fichiers:
        octets = p.read_bytes()
        doc = yaml.safe_load(octets)
        manque = [c for c in CHAMPS_FICHE if not isinstance(doc, dict) or c not in doc]
        if manque:
            raise VagueError(f"{p.name} : champs manquants {manque}")
        out.append(Fiche(p.name, _sha(octets), str(doc["famille"]), str(doc["nom"]), str(doc["mecanisme"]),
                         str(doc["classe"]), str(doc["strategie"]), dict(doc["grille"]),
                         dict(doc.get("params_fixes") or {}), bool(doc.get("signaux_perp", False))))
    return out


def points_de_grille(grille: dict) -> list[dict]:
    noms = sorted(grille)
    return [dict(zip(noms, vals, strict=True)) for vals in itertools.product(*(sorted(grille[n]) for n in noms))]


def _valider_fiche(f: Fiche, criteres, numero: int, strat_dir: Path) -> str | None:
    """Raison du refus, ou None. Le moteur applique les règles chiffrées ; l'auditeur de fiche juge le reste."""
    ess = criteres.essais
    if f.classe not in ("directionnel", "couvert"):
        return f"classe inconnue {f.classe!r}"
    if Path(f.strategie).name != f.strategie or not (strat_dir / f.strategie).is_file():
        return f"stratégie {f.strategie!r} absente du dossier des stratégies (nom de fichier simple attendu)"
    n_par = len(f.grille)
    if not ess.parametres_min <= n_par <= ess.parametres_max:
        return f"{n_par} paramètres (attendu {ess.parametres_min} à {ess.parametres_max})"
    ok, raison = grille_valide(f.grille, ess)
    if not ok:
        return f"grille non géométrique : {raison}"
    n = math.prod(len(v) for v in f.grille.values())
    if numero == 1 and n > ess.variantes_max_par_famille_vague_1:
        return f"{n} variantes > {ess.variantes_max_par_famille_vague_1} (vague 1)"
    return None


# --------------------------------------------------------------------------------------------------
# Journal : numéros de vague, règle d'arrêt, reprise, V
# --------------------------------------------------------------------------------------------------


def _ecrire_evenement(journal, type_: str, payload: dict, journal_arene) -> None:
    """Événement chaîné de la vague, puis ancrage externe (comme après un essai)."""
    journal._ajouter(type_, payload)
    journal.ancrer(journal_arene)


def _etat_vagues(journal) -> tuple[dict[int, dict], dict[int, dict], dict[int, str]]:
    debuts: dict[int, dict] = {}
    fins: dict[int, dict] = {}
    decisions: dict[int, str] = {}
    for e in journal.evenements():
        t, p = e["type"], e["payload"]
        if t == EVT_VAGUE_DEBUT:
            debuts[int(p["numero"])] = p
        elif t == EVT_VAGUE_FIN:
            fins[int(p["numero"])] = p
        elif t == EVT_DECISION:
            decisions[int(p["numero"])] = p["sha256"]
    return debuts, fins, decisions


def arret_apres(journal, numero_precedent: int, criteres) -> bool:
    """Règle d'arrêt calculée À PARTIR DU JOURNAL : le meilleur DSR de la vague `numero_precedent`
    (événement chaîné `vague_fin`) est inférieur au seuil de criteres.yaml, ou n'existe pas."""
    _, fins, _ = _etat_vagues(journal)
    if numero_precedent not in fins:
        raise VagueError(f"la vague {numero_precedent} n'est pas terminée dans le journal")
    brut = fins[numero_precedent].get("meilleur_dsr")
    try:
        d = float(brut) if brut is not None else float("nan")
    except ValueError:
        d = float("nan")
    return not (math.isfinite(d) and d >= criteres.essais.arret_apres_vague_1.dsr_max_inferieur_a)


def _controler_numero(journal, numero: int, criteres, rapports: Path, decision_path: Path) -> None:
    """Refuse une vague hors séquence ou sans la décision requise (lecture seule du journal)."""
    if numero < 1:
        raise VagueError(f"numéro de vague invalide : {numero}")
    debuts, fins, decisions = _etat_vagues(journal)
    if numero in fins:
        raise VagueError(f"la vague {numero} est déjà terminée dans le journal")
    if numero not in debuts:
        attendu = 1 if not debuts else max(debuts) + 1
        if numero != attendu:
            raise VagueError(f"numéro de vague {numero} : les numéros sont consécutifs, {attendu} attendu")
        if attendu > 1 and (attendu - 1) not in fins:
            raise VagueError(f"la vague {attendu - 1} n'est pas terminée : la vague {numero} est refusée")
    if numero == 1:
        return
    if not (rapports / f"vague-{numero - 1}.md").is_file():
        raise VagueError(f"rapport de la vague {numero - 1} ({rapports / f'vague-{numero - 1}.md'}) absent")
    if arret_apres(journal, numero - 1, criteres):
        if not decision_path.is_file() or not decision_path.read_bytes().strip():
            raise VagueError(f"règle d'arrêt de la vague {numero - 1} : {decision_path} (décision écrite du propriétaire, "
                             "non vide) est requis")
        sha = _sha(decision_path.read_bytes())
        if numero in decisions and decisions[numero] != sha:
            raise VagueError(f"{decision_path} a changé depuis son enregistrement dans le journal")


def sr_jours_du_journal(journal) -> dict[str, dict[str, list[float]]]:
    """classe -> famille -> sr_jour de TOUS les essais de recherche du journal (univers principal, statut OK,
    toutes vagues, reprises comprises ; le labo n'y figure pas)."""
    out: dict[str, dict[str, list[float]]] = {}
    for e in journal.essais().values():
        d, f = e["debut"], e["fin"]
        if f is None or f.get("statut") != "OK" or d.get("univers") != "principal":
            continue
        try:
            x = float(f["sr_jour"])
        except (KeyError, ValueError):
            continue
        if math.isfinite(x):
            out.setdefault(d["classe"], {}).setdefault(d["famille"], []).append(x)
    return out


def _index_clos(journal) -> dict[tuple, tuple[str, dict]]:
    """(famille, params canoniques, univers, code_sha256) -> (id, payload de la `fin`) des essais clos."""
    out = {}
    for eid, e in journal.essais().items():
        if e["fin"] is None:
            continue
        d = e["debut"]
        out[(d["famille"], d["params"], d["univers"], d["code_sha256"])] = (eid, e["fin"])
    return out


def _n_debuts(journal, *, principal_seulement: bool = False) -> tuple[int, set[str]]:
    evts = [e["payload"] for e in journal.evenements("debut")]
    if principal_seulement:
        evts = [p for p in evts if p.get("univers") == "principal"]
    return len(evts), {p["famille"] for p in evts}


# --- cache des séries (reprise) -------------------------------------------------------------------


def _sha_serie(serie: SerieMoteur) -> str:
    return hashlib.sha256(np.ascontiguousarray(serie.rendements_nets[serie.masque_eval]).tobytes()).hexdigest()


def _sauver(cache: Path, res: ResultatEssai) -> None:
    """Écrit la série d'un essai OK (npz) et son rapport de causalité (json), de façon atomique."""
    if res.code != "OK" or res.serie is None:
        return
    cache.mkdir(parents=True, exist_ok=True)
    arrays = {k: np.asarray(v) for k, v in res.serie.__dict__.items() if isinstance(v, np.ndarray)}
    arrays["_classe"] = np.array(res.serie.classe)
    arrays["_symboles"] = np.array(list(res.serie.symboles), dtype=str)
    tmp = cache / f"{res.id}.tmp.npz"
    np.savez(tmp, **arrays)
    (cache / f"{res.id}.causalite.json").write_text(json.dumps(res.causalite))
    tmp.replace(cache / f"{res.id}.npz")  # le .npz est écrit en dernier : sa présence = cache complet


def _recharger(cache: Path, eid: str, fin: dict, univers: str) -> ResultatEssai:
    if fin.get("statut") != "OK":
        return ResultatEssai(id=eid, code=str(fin.get("statut")), univers=univers)
    chemin = cache / f"{eid}.npz"
    if not chemin.is_file():
        raise VagueError(f"essai {eid} clos dans le journal mais sa série est introuvable ({chemin}) : reprise "
                         "impossible sans relancer l'essai (ce qui le compterait deux fois)")
    with np.load(chemin, allow_pickle=False) as z:
        champs = {k: z[k] for k in z.files if not k.startswith("_")}
        serie = SerieMoteur(classe=str(z["_classe"]), symboles=tuple(str(x) for x in z["_symboles"]), **champs)
    if _sha_serie(serie) != fin.get("serie_sha256"):
        raise VagueError(f"série de l'essai {eid} : sha256 différent de celui du journal (cache altéré)")
    causalite = json.loads((cache / f"{eid}.causalite.json").read_text()) \
        if (cache / f"{eid}.causalite.json").is_file() else None
    return ResultatEssai(id=eid, code="OK", univers=univers, serie=serie, causalite=causalite)


# --------------------------------------------------------------------------------------------------
# Lancement d'un essai (vérifications, reprise, plafonds)
# --------------------------------------------------------------------------------------------------


def _fiche_essai(f: Fiche) -> FicheEssai:
    return FicheEssai(f.famille, f.classe, f.sha256, bool(getattr(f, "signaux_perp", False)))


@dataclass
class _Ctx:
    numero: int
    donnees: object
    journal: object
    criteres: object
    strat_dir: Path
    cache: Path
    rap: RapportVague
    journal_arene: object = None
    causalite: bool = True
    timeout_s: float | None = None
    cout_spot_bp: int | None = None
    test: bool = False  # tests seulement : autorise un journal d'arène absent (ancrage externe)
    clos: dict = field(default_factory=dict)

    def verifier_plafonds(self, univers: str) -> None:
        """Plafonds cumulatifs sur le journal, vérifiés AVANT de lancer la ligne."""
        ess = self.criteres.essais
        n, _ = _n_debuts(self.journal)
        if n >= self.criteres.plafond_total:
            raise PlafondError(f"{n} essais déjà commencés, plafond total {self.criteres.plafond_total}")
        if self.numero == 1 and univers == "principal":
            n1, _ = _n_debuts(self.journal, principal_seulement=True)
            if n1 >= ess.plafond_vague_1:
                raise PlafondError(f"{n1} variantes déjà commencées, plafond de la vague 1 {ess.plafond_vague_1}")

    def lancer(self, f: Fiche, params: dict, univers: str = "principal", *, causalite: bool | None = None
               ) -> ResultatEssai:
        verifier_criteres(self.criteres)  # avant CHAQUE essai
        code = self.strat_dir / f.strategie
        cle = (f.famille, params_canoniques(params), univers, _sha(code.read_bytes()))
        if cle in self.clos:
            eid, fin = self.clos[cle]
            self.rap.n_reprises += 1
            return _recharger(self.cache, eid, fin, univers)
        self.verifier_plafonds(univers)
        res = executer_essai(
            _fiche_essai(f), code, params, self.donnees, self.journal, self.criteres, univers=univers,
            journal_arene=self.journal_arene, causalite=self.causalite if causalite is None else causalite,
            timeout_s=self.timeout_s, cout_spot_bp=self.cout_spot_bp, test=self.test)
        _sauver(self.cache, res)
        self.clos[cle] = (res.id, self.journal.essais()[res.id]["fin"])
        return res


# --------------------------------------------------------------------------------------------------
# Vague
# --------------------------------------------------------------------------------------------------


def _closes_arene(donnees, symboles, jours_idx):
    import pandas as pd

    cols = {}
    for s in symboles:
        df = donnees.spot_1d[s]
        cols[s] = df["close"].reindex(jours_idx)
    return pd.DataFrame(cols, index=jours_idx)


def executer_vague(
    numero: int, fiches_dir, strategies_dir, donnees, journal, criteres, *,
    rapports_dir: Path | str = RAPPORTS_DEFAUT, journal_arene: Path | str | None = None,
    depot: Path | str = REPO, tag: str | None = None, decision_path: Path | str | None = None,
    causalite: bool = True, timeout_s: float | None = None, cout_spot_bp: int | None = None,
    symboles_controle: list[str] | None = None, test: bool = False,
) -> RapportVague:
    """Lance (ou reprend) la vague `numero`. `donnees` : `Donnees` du chargeur ou `Panneau` (tests). Les essais
    sont écrits dans `journal` (`JournalRecherche`) ; l'ancrage va dans `journal_arene` s'il est fourni.
    `depot`/`tag` : dépôt git et tag du gel (par défaut le dépôt du projet et `recherche-vague-<n>-fiches`).
    `decision_path` : par défaut `fiches_dir/../DECISION-OWNER.md`. `journal_arene` est obligatoire (ancrage
    externe) sauf `test=True`, réservé aux tests."""
    verifier_criteres(criteres)
    if journal_arene is None and not test:
        raise VagueError("journal de l'arène obligatoire (ancrage externe) ; test=True réservé aux tests")
    rapports = Path(rapports_dir)
    strat_dir = Path(strategies_dir)
    decision = Path(decision_path) if decision_path else Path(fiches_dir).parent / DECISION_OWNER
    ess = criteres.essais
    rap = RapportVague(numero)

    fiches = lire_fiches(fiches_dir, strat_dir, numero, depot=depot, tag=tag)
    journal.demarrer()
    journal.verifier_ancrage(journal_arene)
    _controler_numero(journal, numero, criteres, rapports, decision)
    rapports.mkdir(parents=True, exist_ok=True)

    if len(fiches) > ess.familles_max_par_vague:
        raise VagueError(f"{len(fiches)} familles > {ess.familles_max_par_vague}")
    valides = []
    for f in fiches:
        raison = _valider_fiche(f, criteres, numero, strat_dir)
        if raison:
            rap.refusees[f.fichier] = raison
        else:
            valides.append(f)

    clos = _index_clos(journal)
    ctx = _Ctx(numero, donnees, journal, criteres, strat_dir, rapports / "series", rap,
               journal_arene=journal_arene, causalite=causalite, timeout_s=timeout_s,
               cout_spot_bp=cout_spot_bp, test=test, clos=clos)
    nouveaux = 0
    for f in valides:
        code_sha = _sha((strat_dir / f.strategie).read_bytes())
        for pt in points_de_grille(f.grille):
            cle = (f.famille, params_canoniques({**f.params_fixes, **pt}), "principal", code_sha)
            nouveaux += cle not in clos
    n_debuts, _ = _n_debuts(journal)
    if n_debuts + nouveaux > criteres.plafond_total:
        raise VagueError(f"{n_debuts} + {nouveaux} essais dépasseraient le plafond de {criteres.plafond_total}")
    if numero == 1:
        n1, familles_journal = _n_debuts(journal, principal_seulement=True)
        if n1 + nouveaux > ess.plafond_vague_1:
            raise VagueError(f"{n1} variantes déjà commencées + {nouveaux} à lancer > plafond de la vague 1 "
                             f"({ess.plafond_vague_1})")
        familles = familles_journal | {f.famille for f in valides}
        if len(familles) > ess.familles_max_par_vague:
            raise VagueError(f"{len(familles)} familles (journal compris) > {ess.familles_max_par_vague}")

    # --- marqueurs chaînés : lancement de la vague, décision du propriétaire -------------------------------
    debuts, _, decisions = _etat_vagues(journal)
    if numero not in debuts:
        _ecrire_evenement(journal, EVT_VAGUE_DEBUT, {
            "numero": numero, "criteres_sha256": criteres.sha256,
            "fiches": {f.fichier: f.sha256 for f in fiches}}, journal_arene)
    if numero > 1 and arret_apres(journal, numero - 1, criteres) and numero not in decisions:
        _ecrire_evenement(journal, EVT_DECISION, {"numero": numero, "sha256": _sha(decision.read_bytes()),
                                                  "fichier": f"{DECISION_OWNER}"}, journal_arene)

    # --- grille complète sur l'univers principal ----------------------------------------------------
    from recherche.moteur.panneau import Panneau

    pan_principal = donnees if isinstance(donnees, Panneau) else None
    brutes: list[tuple] = []  # (fiche, params, point, ResultatEssai)
    try:
        for f in valides:
            for pt in points_de_grille(f.grille):
                params = {**f.params_fixes, **pt}
                res = ctx.lancer(f, params)
                rap.n_essais_vague += 1
                brutes.append((f, params, pt, res))
    except PlafondError:
        rap.plafond_atteint = True

    essais = {}
    for f, params, pt, res in brutes:
        if res.code == "OK":
            essais[res.id] = vers_essai(res, famille=f.famille, classe=f.classe, params=pt)
    tous = list(essais.values())
    sr_jours = sr_jours_du_journal(journal)  # V par classe : tous les essais de recherche du journal

    panier_cache: dict = {}

    def panier(classe: str):
        if "p" not in panier_cache:
            pan = pan_principal or panneau_depuis_donnees(donnees, "principal", avec_perp=False,
                                                          symboles_arene=tuple(criteres.univers_arene))
            panier_cache["p"] = (pan, vers_serie_panier(panier_equipondere(pan, criteres)))
        return panier_cache["p"][1]

    candidats: list[Candidat] = []
    verdicts: dict[str, Verdict] = {}
    for f, params, pt, res in brutes:
        ligne = LigneEssai(res.id, f.famille, pt, res.code)
        rap.lignes.append(ligne)
        if res.code != "OK":
            continue
        e = essais[res.id]
        ligne.sharpe_net = stats.sharpe(e.net)
        caus = vers_rapport_causalite(res.causalite, criteres)
        kw = {"sr_jours_recherche": sr_jours}
        v = evaluer_candidat(e, tous, criteres, f.grille, panier(f.classe), None, None, caus, **kw)
        if all(v.portes[c][0] for c in _PORTES_AVANT) and all(ok for ok, _, _ in v.coherence.values()):
            arene, controle, supp = _c15_c16(f, params, ctx, symboles_controle)
            rap.n_lignes_supplementaires += supp
            v = evaluer_candidat(e, tous, criteres, f.grille, panier(f.classe), arene, controle, caus, **kw)
        if f.classe == "couvert":
            v = _sans_c15(v)
        ligne.verdict = v
        verdicts[res.id] = v
        if v.passe:
            rap.candidats.append(res.id)
            candidats.append(Candidat(res.id, v.portes["C1"][1], e.net - panier(f.classe).reindex(e.net.index)))

    dsrs = [v.portes["C1"][1] for v in verdicts.values() if math.isfinite(v.portes["C1"][1])]
    rap.meilleur_dsr = max(dsrs) if dsrs else None
    rap.arret = rap.meilleur_dsr is None or rap.meilleur_dsr < ess.arret_apres_vague_1.dsr_max_inferieur_a
    rap.selection = selectionner(candidats, criteres)
    rap.n_reel_total = journal.n_ids()
    _ecrire(rap, valides, rapports, criteres)
    _ecrire_evenement(journal, EVT_VAGUE_FIN, {
        "numero": numero, "meilleur_dsr": None if rap.meilleur_dsr is None else decimal12(rap.meilleur_dsr),
        "candidats": list(rap.candidats), "plafond_atteint": rap.plafond_atteint,
        "n_essais_vague": rap.n_essais_vague}, journal_arene)
    return rap


def _sans_c15(v: Verdict) -> Verdict:
    """Classe couvert : C15 (compatibilité arène) est « spot seulement » (PROTOCOLE §6) : non applicable
    (vraie) et le rapport l'indique. C16 s'applique aussi au couvert (symboles de contrôle qui ont un perp) et
    reste telle qu'évaluée ; les autres portes et les contrôles de cohérence restent requis."""
    portes = dict(v.portes)
    portes["C15"] = (True, "non applicable (couvert)", None)
    passe = all(ok for ok, _, _ in portes.values()) and all(ok for ok, _, _ in v.coherence.values())
    return replace(v, portes=portes, passe=passe)


def _donnee_manquante(donnees, sym: str, f: Fiche) -> bool:
    """Vrai si la donnée dont la fiche a besoin manque pour `sym` (couvert : perp ; signaux_perp : funding).
    Le symbole est alors « non évaluable » (ni au numérateur de C16, ni dans le minimum de 10)."""
    besoin_perp = f.classe == "couvert"
    besoin_funding = f.classe == "directionnel" and f.signaux_perp
    if not (besoin_perp or besoin_funding):
        return False
    if hasattr(donnees, "controle_perp_1h"):  # `Donnees` du chargeur
        if besoin_perp and donnees.controle_perp_1h.get(sym) is None:
            return True
        return bool(besoin_funding and donnees.controle_funding.get(sym) is None)
    if sym not in donnees.symboles:  # `Panneau` (tests)
        return True
    pan = donnees.sous_univers([sym])
    return pan.eligibles_perp is None or not bool(pan.eligibles_perp.any())


def _c15_c16(f: Fiche, params: dict, ctx: _Ctx, symboles_controle: list[str] | None = None):
    """C15 (directionnel seulement) : essai sur l'univers arène puis replay riskd/fills. C16 : un essai par
    symbole de contrôle ; un symbole dont la donnée requise manque est `NON_EVALUABLE`, un essai non OK vaut
    None (échec). Plafonds vérifiés avant chaque ligne ; si le plafond est atteint, les symboles restants
    manquent (échecs, le dénominateur de C16 étant fixe)."""
    import pandas as pd

    from recherche.moteur.panneau import Panneau

    donnees, supp, arene = ctx.donnees, 0, None
    if f.classe == "directionnel":
        try:
            r = ctx.lancer(f, params, "arene", causalite=False)
            supp += 1
            if r.code == "OK":
                s = r.serie
                idx = pd.to_datetime(s.jours, unit="s")
                cols = list(s.symboles)
                poids = pd.DataFrame(s.poids_spot, index=idx, columns=cols)
                m = s.masque_eval
                if isinstance(donnees, Panneau):
                    closes = pd.DataFrame(donnees.sous_univers(cols).spot_1d[:, :, 3], index=idx, columns=cols)
                    closes = closes.where(donnees.sous_univers(cols).eligibles)
                else:
                    closes = _closes_arene(donnees, cols, idx)
                arene = rejouer(poids[m], closes[m], fee_bp=50, slippage_bp=5, demi_spread_bp=5)
        except PlafondError:
            ctx.rap.plafond_atteint = True
            return None, None, supp
    controle = {}
    symboles = (list(symboles_controle) if symboles_controle is not None
                else list(donnees.controle) if hasattr(donnees, "controle") else [])
    for sym in symboles:
        if _donnee_manquante(donnees, sym, f):
            controle[sym] = NON_EVALUABLE
            continue
        try:
            r = ctx.lancer(f, params, f"controle:{sym}", causalite=False)
        except PlafondError:
            ctx.rap.plafond_atteint = True
            break
        supp += 1
        controle[sym] = (vers_essai(r, famille=f.famille, classe=f.classe, params=params)
                         if r.code == "OK" else None)
    return arene, (controle or None), supp


# --------------------------------------------------------------------------------------------------
# Rapports
# --------------------------------------------------------------------------------------------------


def _fmt(x) -> str:
    if isinstance(x, float):
        return f"{x:.4g}"
    if isinstance(x, dict):
        return "{" + ", ".join(f"{k}: {_fmt(v)}" for k, v in x.items()) + "}"
    if isinstance(x, (tuple, list)):
        return "(" + ", ".join(_fmt(v) for v in x) + ")"
    return str(x)


def _ecrire(rap: RapportVague, fiches: list[Fiche], rapports: Path, criteres) -> None:
    L = [f"# Vague {rap.numero}", "",
         ("Document de l'orchestrateur et du propriétaire : il contient des chiffres et ne va à aucun agent. Les "
          f"agents ne reçoivent que `vague-{rap.numero}-statuts.json`."), "",
         (f"Essais de grille : {rap.n_essais_vague} ; lignes supplémentaires (arène, contrôle) : "
          f"{rap.n_lignes_supplementaires} ; dont relues du journal sans relance (reprise) : {rap.n_reprises} ; "
          f"N réel dans le journal : {rap.n_reel_total} ; N du DSR : {criteres.n_dsr}."),
         f"Meilleur DSR : {_fmt(rap.meilleur_dsr)}. Règle d'arrêt déclenchée : {'oui' if rap.arret else 'non'}.", ""]
    if rap.plafond_atteint:
        L += ["**Plafond d'essais atteint : la vague est incomplète.**", ""]
    if rap.refusees:
        L += ["## Fiches refusées par le moteur", ""] + [f"- {k} : {v}" for k, v in sorted(rap.refusees.items())] + [""]
    L += ["## Tous les essais", "", "| id | famille | paramètres | code | Sharpe net | portes en échec | passe |",
          "|---|---|---|---|---|---|---|"]
    for ln in rap.lignes:
        echecs = ", ".join(ln.verdict.echecs()) if ln.verdict else ""
        passe = "oui" if ln.verdict and ln.verdict.passe else "non"
        L.append(f"| {ln.id} | {ln.famille} | {_fmt(ln.params)} | {ln.code} | {_fmt(ln.sharpe_net)} | {echecs} | {passe} |")
    L += ["", "## Verdicts détaillés", "",
          ("C16 : mesure = (part, positifs, évaluables, non évaluables, taille de l'univers de contrôle) ; "
           "la part est rapportée à la taille fixe de l'univers."), ""]
    for ln in rap.lignes:
        if not ln.verdict:
            continue
        L.append(f"### {ln.id} ({ln.famille} {_fmt(ln.params)})")
        for k, (ok, val, seuil) in {**ln.verdict.portes, **ln.verdict.coherence}.items():
            L.append(f"- {k} : {'OK' if ok else 'ÉCHEC'} ; mesure {_fmt(val)} ; seuil {_fmt(seuil)}")
        L.append("")
    L += ["## Sélection", ""]
    if rap.selection and rap.selection.retenus:
        L.append(f"Retenus : {', '.join(rap.selection.retenus)}. "
                 f"P(au moins un non réfuté en paper | H0) = {rap.selection.p_au_moins_un_non_refute:.4f} "
                 "(simulation de la règle de réfutation du §9, voir portes/selection.py).")
        L += [f"- écarté {k} : {v}" for k, v in rap.selection.ecartes.items()]
    else:
        L.append("Aucun candidat : issue B si aucune autre vague n'est décidée.")
    rap.chemin_rapport = rapports / f"vague-{rap.numero}.md"
    rap.chemin_rapport.write_text("\n".join(L) + "\n")

    # Statuts : ce que verront les chercheurs suivants (nom, mécanisme, verdict binaire, rien d'autre).
    par_famille: dict[str, list[LigneEssai]] = {}
    for ln in rap.lignes:
        par_famille.setdefault(ln.famille, []).append(ln)
    statuts = []
    for f in fiches:
        lignes = par_famille.get(f.famille, [])
        gagnante = any(ln.id in rap.candidats for ln in lignes)
        statuts.append({"nom": f.nom, "mecanisme": f.mecanisme, "verdict": "non_ecartee" if gagnante else "ecartee"})
    for fich, raison in sorted(rap.refusees.items()):
        statuts.append({"nom": fich, "mecanisme": "", "verdict": "ecartee"})
    rap.chemin_statuts = rapports / f"vague-{rap.numero}-statuts.json"
    rap.chemin_statuts.write_text(json.dumps(statuts, ensure_ascii=False, indent=1) + "\n")
