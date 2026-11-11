"""Orchestration codée d'une vague de recherche (ARCHITECTURE.md, PROTOCOLE §4, §6, §7).

Aucun LLM ne décide d'un passage : ce module lit des fiches (YAML), lance le moteur sur chaque point de grille,
applique les portes C1-C16, sélectionne et écrit les rapports. Tout chemin est un paramètre (tests en tmp).

Format d'une fiche `fiches_dir/<nom>.yaml` (champs obligatoires) :
    famille, nom, mecanisme, classe (directionnel|couvert), strategie (fichier de `strategies_dir`),
    grille (paramètre -> liste de valeurs, géométrique : >= 3 valeurs, rapport >= 1,25), params_fixes (facultatif).
Le reste de la fiche (qui perd de l'autre côté, prédiction falsifiable...) est haché avec elle mais n'est pas lu
ici : l'auditeur de fiche est un agent distinct.
Gel : `fiches_dir/MANIFESTE.json` {fichier: sha256}, écrit par `geler_fiches` AVANT la vague ; la vague refuse
toute fiche absente du manifeste ou modifiée, et (avec `verifier_git`) toute fiche non commitée.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from recherche.config import REPO
from recherche.moteur.essai import FicheEssai, PlafondError, executer_essai
from recherche.moteur.panneau import panneau_depuis_donnees
from recherche.moteur.portefeuille import panier_equipondere
from recherche.portes import stats
from recherche.portes.adaptateur import vers_essai, vers_rapport_causalite, vers_serie_panier
from recherche.portes.evaluer import Verdict, evaluer_candidat, grille_valide
from recherche.portes.replay_arene import rejouer
from recherche.portes.selection import Candidat, Selection, selectionner

RAPPORTS_DEFAUT = REPO / "recherche" / "rapports"
CHAMPS_FICHE = ("famille", "nom", "mecanisme", "classe", "strategie", "grille")
MANIFESTE_FICHES = "MANIFESTE.json"
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
    n_essais_vague: int = 0  # essais de grille (plafond de variantes)
    n_lignes_supplementaires: int = 0  # arène + contrôle : comptent dans N réel
    n_reel_total: int = 0
    plafond_atteint: bool = False
    chemin_rapport: Path | None = None
    chemin_statuts: Path | None = None


# --------------------------------------------------------------------------------------------------
# Fiches
# --------------------------------------------------------------------------------------------------


def _sha(octets: bytes) -> str:
    return hashlib.sha256(octets).hexdigest()


def geler_fiches(fiches_dir: Path | str) -> dict:
    """Écrit `MANIFESTE.json` (sha256 de chaque fiche `*.yaml`). À commiter AVANT la vague."""
    d = Path(fiches_dir)
    man = {p.name: _sha(p.read_bytes()) for p in sorted(d.glob("*.yaml"))}
    (d / MANIFESTE_FICHES).write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")
    return man


def _git_propre(chemin: Path) -> bool:
    r = subprocess.run(["git", "-C", str(chemin.parent), "status", "--porcelain", "--", str(chemin)],
                       capture_output=True, text=True, check=False)
    suivi = subprocess.run(["git", "-C", str(chemin.parent), "ls-files", "--error-unmatch", str(chemin)],
                           capture_output=True, check=False)
    return r.returncode == 0 and not r.stdout.strip() and suivi.returncode == 0


def lire_fiches(fiches_dir: Path | str, *, verifier_git: bool = False) -> list[Fiche]:
    d = Path(fiches_dir)
    man_path = d / MANIFESTE_FICHES
    if not man_path.is_file():
        raise VagueError(f"{man_path} absent : fiches non gelées")
    man = json.loads(man_path.read_text())
    fichiers = sorted(p for p in d.glob("*.yaml"))
    if {p.name for p in fichiers} != set(man):
        raise VagueError("les fiches présentes ne sont pas exactement celles du manifeste de gel")
    out = []
    for p in fichiers:
        octets = p.read_bytes()
        if _sha(octets) != man[p.name]:
            raise VagueError(f"{p.name} modifiée depuis le gel (sha256 différent)")
        if verifier_git and not _git_propre(p):
            raise VagueError(f"{p.name} n'est pas commitée ou a des modifications locales")
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


def _valider_fiche(f: Fiche, criteres, numero: int) -> str | None:
    """Raison du refus, ou None. Le moteur applique les règles chiffrées ; l'auditeur de fiche juge le reste."""
    ess = criteres.essais
    if f.classe not in ("directionnel", "couvert"):
        return f"classe inconnue {f.classe!r}"
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
# Vague
# --------------------------------------------------------------------------------------------------


def _fiche_essai(f: Fiche) -> FicheEssai:
    return FicheEssai(f.famille, f.classe, f.sha256, bool(getattr(f, "signaux_perp", False)))


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
    verifier_git: bool = False, decision_ecrite: Path | str | None = None, causalite: bool = True,
    timeout_s: float | None = None, cout_spot_bp: int | None = None,
    symboles_controle: list[str] | None = None,
) -> RapportVague:
    """Lance la vague `numero`. `donnees` : `Donnees` du chargeur ou `Panneau` (tests). Les essais sont
    écrits dans `journal` (`JournalRecherche`) ; l'ancrage va dans `journal_arene` s'il est fourni."""
    rapports = Path(rapports_dir)
    rapports.mkdir(parents=True, exist_ok=True)
    strat_dir = Path(strategies_dir)
    ess = criteres.essais
    rap = RapportVague(numero)

    if numero > 1:
        prec = rapports / f"vague-{numero - 1}.json"
        if prec.is_file() and json.loads(prec.read_text()).get("arret") and not (
                decision_ecrite and Path(decision_ecrite).is_file()):
            raise VagueError(f"règle d'arrêt de la vague {numero - 1} : une décision écrite du propriétaire est requise")

    fiches = lire_fiches(fiches_dir, verifier_git=verifier_git)
    if numero == 1 and len(fiches) > ess.familles_max_par_vague:
        raise VagueError(f"{len(fiches)} familles > {ess.familles_max_par_vague}")
    valides = []
    for f in fiches:
        raison = _valider_fiche(f, criteres, numero)
        if raison:
            rap.refusees[f.fichier] = raison
        else:
            valides.append(f)
    total = sum(math.prod(len(v) for v in f.grille.values()) for f in valides)
    if numero == 1 and total > ess.plafond_vague_1:
        raise VagueError(f"{total} essais prévus > plafond de la vague 1 ({ess.plafond_vague_1})")
    if journal.n_ids() + total > criteres.plafond_total:
        raise VagueError(f"{journal.n_ids()} + {total} essais dépasseraient le plafond de {criteres.plafond_total}")

    # --- grille complète sur l'univers principal -------------------------------------------------
    from recherche.moteur.panneau import Panneau

    pan_principal = donnees if isinstance(donnees, Panneau) else None
    brutes: list[tuple] = []  # (fiche, params, ResultatEssai)
    try:
        for f in valides:
            code = strat_dir / f.strategie
            for pt in points_de_grille(f.grille):
                params = {**f.params_fixes, **pt}
                res = executer_essai(_fiche_essai(f), code, params, donnees, journal, criteres,
                                     journal_arene=journal_arene, causalite=causalite, timeout_s=timeout_s,
                                     cout_spot_bp=cout_spot_bp)
                rap.n_essais_vague += 1
                brutes.append((f, params, pt, res))
    except PlafondError:
        rap.plafond_atteint = True

    essais = {}
    for f, params, pt, res in brutes:
        if res.code == "OK":
            essais[res.id] = vers_essai(res, famille=f.famille, classe=f.classe, params=pt)
    tous = list(essais.values())

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
        v = evaluer_candidat(e, tous, criteres, f.grille, panier(f.classe), None, None, caus)
        if f.classe == "directionnel" and all(v.portes[c][0] for c in _PORTES_AVANT) \
                and all(ok for ok, _, _ in v.coherence.values()):
            arene, controle, supp = _c15_c16(f, params, donnees, journal, criteres, strat_dir, rap,
                                              journal_arene, timeout_s, cout_spot_bp, symboles_controle)
            rap.n_lignes_supplementaires += supp
            v = evaluer_candidat(e, tous, criteres, f.grille, panier(f.classe), arene, controle, caus)
        elif f.classe == "couvert":
            v = _sans_c15_c16(v)
        ligne.verdict = v
        verdicts[res.id] = v
        if v.passe:
            rap.candidats.append(res.id)
            candidats.append(Candidat(res.id, v.portes["C1"][1], e.net - panier(f.classe).reindex(e.net.index)))

    dsrs = [v.portes["C1"][1] for v in verdicts.values() if math.isfinite(v.portes["C1"][1])]
    rap.meilleur_dsr = max(dsrs) if dsrs else None
    if numero == 1:
        rap.arret = rap.meilleur_dsr is None or rap.meilleur_dsr < ess.arret_apres_vague_1.dsr_max_inferieur_a
    rap.selection = selectionner(candidats, criteres)
    rap.n_reel_total = journal.n_ids()
    _ecrire(rap, valides, rapports, criteres)
    return rap


def _sans_c15_c16(v: Verdict) -> Verdict:
    """Classe couvert : C15 est « spot seulement » (PROTOCOLE §6) et la stratégie couverte n'est pas
    applicable à l'univers de contrôle (spot 1 j, sans perp) : les deux sont marquées non applicables
    (vraies) et le rapport l'indique. Les autres portes et les contrôles de cohérence restent requis."""
    portes = dict(v.portes)
    portes["C15"] = (True, "non applicable (couvert)", None)
    portes["C16"] = (True, "non applicable (couvert)", None)
    passe = all(ok for ok, _, _ in portes.values()) and all(ok for ok, _, _ in v.coherence.values())
    return replace(v, portes=portes, passe=passe)


def _c15_c16(f, params, donnees, journal, criteres, strat_dir, rap, journal_arene, timeout_s, cout_spot_bp,
             symboles_controle=None):
    """C15 : essai sur l'univers arène puis replay riskd/fills. C16 : un essai par symbole de contrôle."""
    import pandas as pd

    from recherche.moteur.panneau import Panneau

    code = strat_dir / f.strategie
    supp = 0
    arene = None
    try:
        r = executer_essai(_fiche_essai(f), code, params, donnees, journal, criteres, univers="arene",
                           journal_arene=journal_arene, causalite=False, timeout_s=timeout_s,
                           cout_spot_bp=cout_spot_bp)
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
        rap.plafond_atteint = True
        return None, None, supp
    controle = {}
    symboles = (list(symboles_controle) if symboles_controle is not None
                else list(donnees.controle) if hasattr(donnees, "controle") else [])
    for sym in symboles:
        try:
            r = executer_essai(_fiche_essai(f), code, params, donnees, journal, criteres,
                               univers=f"controle:{sym}", journal_arene=journal_arene, causalite=False,
                               timeout_s=timeout_s, cout_spot_bp=cout_spot_bp)
        except PlafondError:
            rap.plafond_atteint = True
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
         (f"Essais de grille : {rap.n_essais_vague} ; lignes supplémentaires (arène, contrôle) : "
          f"{rap.n_lignes_supplementaires} ; N réel dans le journal : {rap.n_reel_total} ; "
          f"N du DSR : {criteres.n_dsr}."),
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
    L += ["", "## Verdicts détaillés", ""]
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
    (rapports / f"vague-{rap.numero}.json").write_text(json.dumps(
        {"numero": rap.numero, "arret": rap.arret, "candidats": rap.candidats, "n_reel": rap.n_reel_total},
        indent=1) + "\n")
