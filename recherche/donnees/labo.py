"""Copie des bougies in-sample du labo (lecture seule côté labo), vérifiées contre son MANIFESTE.json."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

LABO_IN_SAMPLE = Path.home() / "dev" / "labo-trading" / "donnees" / "in-sample"


class LaboError(Exception):
    pass


def _sha_fichier(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def copier_in_sample(src: Path | str = LABO_IN_SAMPLE, dest: Path | str = Path("var/recherche/donnees/labo")
                     ) -> list[Path]:
    """Vérifie le sha256 de chaque fichier de `src` listé dans `MANIFESTE.json`, puis le copie dans `dest`.

    Rien n'est copié si un fichier source ne correspond pas. Reprenable : un fichier déjà présent dans
    `dest` avec le bon sha256 est sauté. `MANIFESTE.json` du labo est copié aussi. Renvoie les chemins de `dest`.
    """
    src, dest = Path(src), Path(dest)
    octets_m = (src / "MANIFESTE.json").read_bytes()
    entrees = json.loads(octets_m)["fichiers"]
    if not entrees:
        raise LaboError("MANIFESTE.json du labo sans fichier")
    for e in entrees:
        f = src / e["fichier"]
        if not f.is_file():
            raise LaboError(f"{e['fichier']} absent de {src}")
        if _sha_fichier(f) != e["sha256"]:
            raise LaboError(f"{e['fichier']} : sha256 différent du MANIFESTE.json du labo")
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for e in entrees:
        cible = dest / e["fichier"]
        if not (cible.is_file() and _sha_fichier(cible) == e["sha256"]):
            tmp = cible.with_name(cible.name + ".part")
            shutil.copyfile(src / e["fichier"], tmp)
            tmp.replace(cible)
        out.append(cible)
    (dest / "MANIFESTE.json").write_bytes(octets_m)
    return out
