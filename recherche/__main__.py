"""CLI de la recherche : `uv run python -m recherche <commande>`.

Commandes : donnees-construire, canari, vague <n> [--geler], statuts, verifier.
Valeurs par défaut : données `var/recherche/donnees`, fiches `recherche/fiches/vague-<n>`, stratégies
`recherche/strategies`, journal `recherche/essais.jsonl`, rapports `recherche/rapports`. Le journal de l'arène
(ancrage `research_anchor`) est `var/journal/events.jsonl`, sauf `--sans-ancrage` ou `--journal-arene`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from recherche.config import REPO, charger_criteres

DONNEES = REPO / "var" / "recherche" / "donnees"
JOURNAL = REPO / "recherche" / "essais.jsonl"
RAPPORTS = REPO / "recherche" / "rapports"
FICHES = REPO / "recherche" / "fiches"
STRATEGIES = REPO / "recherche" / "strategies"
JOURNAL_ARENE = REPO / "var" / "journal" / "events.jsonl"


def _canari(_a) -> int:
    from recherche.moteur import bac_a_sable

    bac_a_sable.canari()
    print("canari OK : le bac à sable refuse le réseau, les lectures hors liste blanche et les écritures hors tmpfs")
    return 0


def _construire(a) -> int:
    from recherche.donnees import construire_donnees

    doc = construire_donnees(a.donnees)
    print(f"manifeste : {len(doc['fichiers'])} fichiers")
    return 0


def _vague(a) -> int:
    from recherche.donnees import charger
    from recherche.moteur.journal import JournalRecherche
    from recherche.vague import VagueError, executer_vague, geler_fiches

    fiches = Path(a.fiches) / f"vague-{a.numero}"
    if a.geler:
        man = geler_fiches(fiches)
        print(f"{len(man)} fiches gelées dans {fiches / 'MANIFESTE.json'} : à commiter avant de lancer la vague")
        return 0
    crit = charger_criteres()
    donnees = charger(a.donnees, crit)
    journal = JournalRecherche(a.journal)
    ancre = None if a.sans_ancrage else Path(a.journal_arene)
    try:
        rap = executer_vague(a.numero, fiches, a.strategies, donnees, journal, crit, rapports_dir=a.rapports,
                             journal_arene=ancre, verifier_git=not a.sans_git, decision_ecrite=a.decision_ecrite)
    except VagueError as e:
        print(f"vague refusée : {e}", file=sys.stderr)
        return 2
    print(f"vague {a.numero} : {rap.n_essais_vague} essais, candidats {rap.candidats or 'aucun'}, "
          f"arrêt {'oui' if rap.arret else 'non'} ; rapport {rap.chemin_rapport}")
    return 0


def _statuts(a) -> int:
    fichiers = sorted(Path(a.rapports).glob("vague-*-statuts.json"))
    if not fichiers:
        print("aucun statut")
        return 0
    for f in fichiers:
        print(f"# {f.name}")
        for s in json.loads(f.read_text()):
            print(f"- {s['nom']} : {s['verdict']} ({s['mecanisme']})")
    return 0


def _verifier(a) -> int:
    from recherche.donnees.manifeste import verifier_manifeste
    from recherche.moteur.journal import JournalRecherche

    crit = charger_criteres()
    ok = True

    def rapport(nom: str, bon: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= bon
        print(f"{'OK    ' if bon else 'ECHEC '} {nom}{' : ' + detail if detail else ''}")

    rapport("criteres.yaml", True, crit.sha256[:16])
    try:
        verifier_manifeste(a.donnees)
        rapport("manifeste des données", True)
    except Exception as e:  # noqa: BLE001
        rapport("manifeste des données", False, str(e)[:200])
    if Path(a.journal).is_file():
        j = JournalRecherche(a.journal)
        try:
            j.verifier_ancrage(None if a.sans_ancrage else a.journal_arene)
            rapport("journal de recherche", True, f"{j.n_lignes()} lignes, {j.n_ids()} essais, tête {j.tete()[:16]}")
        except Exception as e:  # noqa: BLE001
            rapport("journal de recherche", False, str(e)[:200])
    else:
        rapport("journal de recherche", True, "absent (aucun essai)")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m recherche")
    p.add_argument("--donnees", default=str(DONNEES))
    p.add_argument("--journal", default=str(JOURNAL))
    p.add_argument("--rapports", default=str(RAPPORTS))
    p.add_argument("--journal-arene", default=str(JOURNAL_ARENE))
    p.add_argument("--sans-ancrage", action="store_true")
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("donnees-construire").set_defaults(f=_construire)
    sp.add_parser("canari").set_defaults(f=_canari)
    v = sp.add_parser("vague")
    v.add_argument("numero", type=int)
    v.add_argument("--geler", action="store_true", help="écrit MANIFESTE.json des fiches (avant le commit)")
    v.add_argument("--fiches", default=str(FICHES))
    v.add_argument("--strategies", default=str(STRATEGIES))
    v.add_argument("--sans-git", action="store_true")
    v.add_argument("--decision-ecrite", default=None)
    v.set_defaults(f=_vague)
    sp.add_parser("statuts").set_defaults(f=_statuts)
    sp.add_parser("verifier").set_defaults(f=_verifier)
    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    raise SystemExit(main())
