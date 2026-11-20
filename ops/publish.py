"""Publish the public version of the dashboard to GitHub Pages, outbound only.

The host opens no port: it builds the public site from the journal, checks that it contains nothing private,
then pushes a single orphan commit to the `gh-pages` branch of the public repository.
The public history therefore keeps only the latest version (the hash-chained journal stays here).

    .venv/bin/python ops/publish.py --repo OWNER/arena --root-path /arena/ [--dry-run]

`--dry-run` builds and checks without pushing. Run by arena-publish.timer every 30 min (HH:25 and HH:55 UTC).

Besides the generic checks below, the publication refuses any match of the private patterns (names and other
owner-specific strings) listed one regular expression per line in $ARENA_PUBLISH_DENY, by default
~/.config/arena/publish-deny.txt. That file stays outside the repository on purpose.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORK = Path.home() / ".local" / "share" / "arena-publish"

# What must never leave the host. A single match is enough to block the publication.
FORBIDDEN = [
    (re.compile(r"/home/|~/\.config|\.config/arena|secrets?/"), "local path or secrets folder"),
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"), "token or key"),
    (re.compile(r"Claude subscription|Claude Code|claude -p"), "how the models are invoked"),
    (re.compile(r"RUNBOOK|docs/[A-Z]"), "internal document"),
    # A letter before @ and an alphabetic domain: "BTC@65000.5" in a justification is not an address.
    (re.compile(r"[A-Za-z][\w.+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"), "e-mail address"),
    (re.compile(r"\b100\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "machine address or name"),
]
TEXTS = {".html", ".json", ".js", ".css", ".txt"}


def private_patterns() -> list[tuple[re.Pattern[str], str]]:
    """The owner's private patterns (see the module docstring); none when the file is absent."""
    path = Path(os.environ.get("ARENA_PUBLISH_DENY") or Path.home() / ".config" / "arena" / "publish-deny.txt")
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [(re.compile(line, re.IGNORECASE), "private pattern") for line in lines if line.strip() and not line.startswith("#")]


def build(dest: Path, root_path: str) -> None:
    sys.path.insert(0, str(REPO))
    from arena.config import load_config
    from arena.risk.policy import load_policy
    from arena.site import build

    build(
        REPO / "var" / "journal" / "events.jsonl", dest,
        config=load_config(REPO / "config" / "arena.toml"), policy=load_policy(REPO / "config" / "policy.toml"),
        public=True, root_path=root_path,
    )  # fmt: skip
    (dest / ".nojekyll").write_text("")


def verify(directory: Path) -> list[str]:
    violations = []
    patterns = FORBIDDEN + private_patterns()
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix not in TEXTS or path.parent.name == "vendor":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern, label in patterns:
            if match := pattern.search(text):
                violations.append(f"{path.relative_to(directory)}: {label} ({match.group(0)[:40]!r})")
    return violations


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def push(site: Path, repo: str) -> None:
    clone = WORK / "repo"
    if not (clone / ".git").exists():
        clone.mkdir(parents=True, exist_ok=True)
        git("init", "-q", "-b", "gh-pages", cwd=clone)
        git("remote", "add", "origin", f"https://github.com/{repo}.git", cwd=clone)
    name = git("config", "user.name", cwd=REPO).strip()
    # GitHub noreply address: the public commit does not show the real e-mail address.
    ident = subprocess.run(["gh", "api", "user", "--jq", '"\\(.id)+\\(.login)"'],
                           check=True, capture_output=True, text=True).stdout.strip()  # fmt: skip
    mail = f"{ident}@users.noreply.github.com"
    for entry in clone.iterdir():
        if entry.name != ".git":
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
    for entry in site.iterdir():
        (shutil.copytree if entry.is_dir() else shutil.copy2)(entry, clone / entry.name)
    # Orphan commit: the published branch holds only the latest version.
    git("checkout", "-q", "--orphan", "publication", cwd=clone)
    git("add", "-A", cwd=clone)
    stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    git("-c", f"user.name={name}", "-c", f"user.email={mail}", "commit", "-q", "-m", f"Publish {stamp}", cwd=clone)
    git("branch", "-M", "gh-pages", cwd=clone)
    subprocess.run(
        ["git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential",
         "push", "-q", "--force", "origin", "gh-pages"],
        cwd=clone, check=True,
    )  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True, help="public GitHub repository, owner/name")
    ap.add_argument("--root-path", required=True, help="path of the site on the host, e.g. /arena/")
    ap.add_argument("--dry-run", action="store_true", help="build and check without pushing")
    args = ap.parse_args()
    site = WORK / "site"
    site.parent.mkdir(parents=True, exist_ok=True)
    build(site, args.root_path)
    violations = verify(site)
    if violations:
        print("publication blocked:", *violations, sep="\n  ", file=sys.stderr)
        return 1
    if args.dry_run:
        print(f"verified, nothing pushed: {site}")
        return 0
    push(site, args.repo)
    print(f"published to https://github.com/{args.repo} (gh-pages branch)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
