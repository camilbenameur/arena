"""Journal chaîné des essais de recherche (enveloppe de `arene.journal.Journal`) et ancrage externe.

Types d'événements : `genese_labo` (première ligne), `debut` (avant le calcul), `fin` (après). Aucun float :
les métriques sont des chaînes décimales à 12 chiffres significatifs (`decimal12`). Le détail technique d'un
échec (traces) ne va jamais dans ce journal mais dans `<journal>.technique.jsonl`, lu par l'orchestrateur.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from arene.journal import Journal, JournalError

DEPOT_LABO = Path.home() / "dev" / "labo-trading"
TAG_LABO = "gel-final"
TYPE_GENESE, TYPE_DEBUT, TYPE_FIN, TYPE_ANCRE = "genese_labo", "debut", "fin", "research_anchor"


class AncrageError(JournalError):
    """Le journal de recherche est plus court que le dernier ancrage, ou la tête ancrée n'y figure pas."""


def decimal12(x: Any) -> str:
    """Chaîne décimale à 12 chiffres significatifs (`nan`, `inf` explicites) ; jamais un float."""
    if isinstance(x, bool):
        return str(x).lower()
    if isinstance(x, int):
        return str(x)
    x = float(x)
    if math.isnan(x):
        return "nan"
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return format(x, ".12g")


def _sans_float(obj: Any) -> Any:
    if isinstance(obj, float):
        return decimal12(obj)
    if isinstance(obj, dict):
        return {str(k): _sans_float(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sans_float(v) for v in obj]
    return obj


def params_canoniques(params: dict) -> str:
    return json.dumps(params, sort_keys=True, separators=(",", ":"), allow_nan=False)


class JournalRecherche:
    def __init__(self, path: str | Path, *, depot_labo: Path | str = DEPOT_LABO, tag_labo: str = TAG_LABO,
                 horloge: Callable[[], int] | None = None):
        self.path = Path(path)
        self.journal = Journal(self.path)
        self.depot_labo = Path(depot_labo)
        self.tag_labo = tag_labo
        self._horloge = horloge or (lambda: int(time.time()))
        self.path_technique = self.path.with_name(self.path.name + ".technique.jsonl")

    # --- écriture --------------------------------------------------------------------------------
    def _ajouter(self, type_: str, payload: dict) -> dict:
        return self.journal.append(type_, _sans_float(payload), self._horloge())

    def genese_labo(self) -> dict:
        """Première ligne : tête (sha256 de la dernière ligne) et nombre de lignes du journal du labo au tag
        `gel-final`, lus tels quels par `git show`. Refuse si le journal n'est pas vide."""
        if self.journal.last() is not None:
            raise JournalError("genese_labo doit être la première ligne d'un journal vide")
        r = subprocess.run(["git", "-C", str(self.depot_labo), "show", f"{self.tag_labo}:essais.jsonl"],
                           capture_output=True, check=False, timeout=60)
        if r.returncode != 0:
            raise JournalError(f"git show {self.tag_labo}:essais.jsonl a échoué : {r.stderr.decode()[-200:]}")
        lignes = [ligne for ligne in r.stdout.split(b"\n") if ligne]
        return self._ajouter(TYPE_GENESE, {
            "tag": self.tag_labo, "n_lignes": len(lignes),
            "tete": hashlib.sha256(lignes[-1]).hexdigest() if lignes else "0" * 64,
            "sha256_fichier": hashlib.sha256(r.stdout).hexdigest()})

    def demarrer(self) -> None:
        """Écrit la genèse si le journal est vide ; sinon vérifie qu'elle est bien la première ligne."""
        if self.journal.last() is None:
            self.genese_labo()
            return
        premiere = next(self.journal.iter_events())
        if premiere["type"] != TYPE_GENESE:
            raise JournalError("la première ligne du journal n'est pas genese_labo")

    def debut(self, payload: dict) -> dict:
        return self._ajouter(TYPE_DEBUT, payload)

    def fin(self, payload: dict) -> dict:
        return self._ajouter(TYPE_FIN, payload)

    def technique(self, essai_id: str, detail: str) -> None:
        """Détail d'un échec, pour l'orchestrateur seulement (fichier non chaîné)."""
        ligne = json.dumps({"ts": self._horloge(), "id": essai_id, "detail": detail[-4000:]},
                           ensure_ascii=False)
        with open(self.path_technique, "a", encoding="utf-8") as f:
            f.write(ligne + "\n")

    # --- lecture ---------------------------------------------------------------------------------
    def evenements(self, type_: str | None = None) -> list[dict]:
        return [e for e in self.journal.iter_events() if type_ is None or e["type"] == type_]

    def n_ids(self) -> int:
        """Nombre d'essais commencés (un essai sans `fin` compte)."""
        return len(self.evenements(TYPE_DEBUT))

    def prochain_id(self) -> str:
        return f"R{self.n_ids() + 1:04d}"

    def essais(self) -> dict[str, dict]:
        """{id: {"debut": payload, "fin": payload|None}} relus depuis le fichier."""
        out: dict[str, dict] = {}
        for e in self.journal.iter_events():
            if e["type"] == TYPE_DEBUT:
                out[e["payload"]["id"]] = {"debut": e["payload"], "fin": None}
            elif e["type"] == TYPE_FIN:
                out[e["payload"]["id"]]["fin"] = e["payload"]
        return out

    def n_lignes(self) -> int:
        last = self.journal.last()
        return 0 if last is None else last["seq"] + 1

    def tete(self) -> str:
        last = self.journal.last()
        return "0" * 64 if last is None else last["hash"]

    def verifier(self) -> None:
        rapport = self.journal.verify()
        if not rapport.ok:
            raise JournalError(f"journal de recherche corrompu : {rapport.codes()}")

    # --- ancrage ---------------------------------------------------------------------------------
    def ancrer(self, journal_arene_path: str | Path | None) -> dict | None:
        """Écrit `research_anchor {tete, n_lignes}` dans le journal de l'arène, seulement si un chemin est
        fourni. Renvoie l'enregistrement écrit (ou None)."""
        if journal_arene_path is None:
            return None
        return Journal(journal_arene_path).append(
            TYPE_ANCRE, {"tete": self.tete(), "n_lignes": self.n_lignes(), "journal": self.path.name},
            self._horloge())

    def verifier_ancrage(self, journal_arene_path: str | Path | None) -> None:
        """Refuse si le journal est plus court que le dernier ancrage ou si la tête ancrée n'y figure pas."""
        self.verifier()
        if journal_arene_path is None:
            return
        ancres = [e for e in Journal(journal_arene_path).iter_events() if e["type"] == TYPE_ANCRE
                  and e["payload"].get("journal") == self.path.name]
        if not ancres:
            return
        derniere = ancres[-1]["payload"]
        n = derniere["n_lignes"]
        if self.n_lignes() < n:
            raise AncrageError(f"journal de {self.n_lignes()} lignes, dernier ancrage à {n}")
        for e in self.journal.iter_events():
            if e["seq"] == n - 1:
                if e["hash"] != derniere["tete"]:
                    raise AncrageError("la tête ancrée ne figure pas dans le journal (historique réécrit)")
                return
        raise AncrageError("ligne ancrée introuvable")
