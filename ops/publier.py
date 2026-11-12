"""Publie la version publique du dashboard sur GitHub Pages, en sortie seulement.

the host n'ouvre aucun port : elle construit le site public à partir du journal, vérifie qu'il ne contient
rien de privé, puis pousse un unique commit orphelin sur la branche `gh-pages` du dépôt public.
L'historique public ne garde donc que la dernière version (le journal haché, lui, reste ici).

    .venv/bin/python ops/publier.py --depot OWNER/arene --racine /arene/ [--sec]

`--sec` construit et vérifie sans rien pousser. Lancé par arene-publication.timer, après chaque cycle.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TRAVAIL = Path.home() / ".local" / "share" / "arene-publication"

# Ce qui ne doit jamais sortir de the host. Un seul motif trouvé suffit à bloquer la publication.
INTERDITS = [
    (re.compile(r"/home/|~/\.config|\.config/arene|secrets?/"), "chemin local ou dossier de secrets"),
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"), "jeton ou clé"),
    (re.compile(r"CLAUDE\.md|\.claude/|Co-Authored-By|Generated with", re.IGNORECASE), "trace d'outillage"),
    (re.compile(r"abonnement Claude|Claude Code|claude -p"), "mode d’appel des modèles"),
    (re.compile(r"RUNBOOK|docs/[A-Z]"), "document interne"),
    # Une lettre avant @ et un domaine alphabétique : « BTC@65000.5 » dans une justification n'est pas une adresse.
    (re.compile(r"[A-Za-z][\w.+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"), "adresse e-mail"),
    (re.compile(r"\b100\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "adresse ou nom de machine"),
]
TEXTES = {".html", ".json", ".js", ".css", ".txt"}


def construire(dest: Path, racine: str) -> None:
    sys.path.insert(0, str(REPO))
    from arene.config import load_config
    from arene.risk.policy import load_policy
    from arene.site import build

    build(
        REPO / "var" / "journal" / "events.jsonl", dest,
        config=load_config(REPO / "config" / "arene.toml"), policy=load_policy(REPO / "config" / "policy.toml"),
        public=True, racine=racine,
    )  # fmt: skip
    (dest / ".nojekyll").write_text("")


def verifier(dossier: Path) -> list[str]:
    fautes = []
    for f in sorted(dossier.rglob("*")):
        if not f.is_file() or f.suffix not in TEXTES or f.parent.name == "vendor":
            continue
        texte = f.read_text(encoding="utf-8", errors="replace")
        for motif, quoi in INTERDITS:
            if m := motif.search(texte):
                fautes.append(f"{f.relative_to(dossier)} : {quoi} ({m.group(0)[:40]!r})")
    return fautes


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def pousser(site: Path, depot: str) -> None:
    clone = TRAVAIL / "depot"
    if not (clone / ".git").exists():
        clone.mkdir(parents=True, exist_ok=True)
        git("init", "-q", "-b", "gh-pages", cwd=clone)
        git("remote", "add", "origin", f"https://github.com/{depot}.git", cwd=clone)
    nom = git("config", "user.name", cwd=REPO).strip()
    # Adresse noreply de GitHub : le commit public ne montre pas l'adresse e-mail réelle.
    ident = subprocess.run(["gh", "api", "user", "--jq", '"\\(.id)+\\(.login)"'],
                           check=True, capture_output=True, text=True).stdout.strip()  # fmt: skip
    mail = f"{ident}@users.noreply.github.com"
    for c in clone.iterdir():
        if c.name != ".git":
            shutil.rmtree(c) if c.is_dir() else c.unlink()
    for c in site.iterdir():
        (shutil.copytree if c.is_dir() else shutil.copy2)(c, clone / c.name)
    # Commit orphelin : la branche publiée ne contient que la dernière version.
    git("checkout", "-q", "--orphan", "publication", cwd=clone)
    git("add", "-A", cwd=clone)
    quand = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    git("-c", f"user.name={nom}", "-c", f"user.email={mail}", "commit", "-q", "-m", f"Publication du {quand}", cwd=clone)
    git("branch", "-M", "gh-pages", cwd=clone)
    subprocess.run(
        ["git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential",
         "push", "-q", "--force", "origin", "gh-pages"],
        cwd=clone, check=True,
    )  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--depot", required=True, help="dépôt GitHub public, propriétaire/nom")
    ap.add_argument("--racine", required=True, help="chemin du site sur l'hôte, ex. /arene/")
    ap.add_argument("--sec", action="store_true", help="construire et vérifier sans pousser")
    a = ap.parse_args()
    site = TRAVAIL / "site"
    site.parent.mkdir(parents=True, exist_ok=True)
    construire(site, a.racine)
    fautes = verifier(site)
    if fautes:
        print("publication bloquée :", *fautes, sep="\n  ", file=sys.stderr)
        return 1
    if a.sec:
        print(f"vérifié, rien poussé : {site}")
        return 0
    pousser(site, a.depot)
    print(f"publié sur https://github.com/{a.depot} (branche gh-pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
