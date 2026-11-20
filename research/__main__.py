"""Research CLI: `uv run python -m research <command>`.

Commands: build-data, canary, wave <n> [--freeze], statuses, verify.
Defaults: data `var/research/data`, sheets `research/waves/<n>/sheets`, strategies
`research/waves/<n>/strategies`, owner decision `research/waves/<n>/DECISION-OWNER.md`, journal
`research/trials.jsonl`, reports `research/reports`. The arena journal (`research_anchor` anchor) is
`var/journal/events.jsonl`, unless `--without-anchor` or `--arena-journal` is given.

The freeze is always verified against the git tag `research-wave-<n>-sheets`; there is no option to
skip it. `criteria.yaml` is compared with its frozen sha256 (tag `research-protocol-v1`) before any trial.
The output of `wave` and `statuses` (read by agents) contains only binary statuses; the figures
are in `wave-<n>.md`, for the orchestrator and the owner.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from research.config import REPO, CriteriaError, load_criteria, verify_criteria

DATA = REPO / "var" / "research" / "data"
JOURNAL = REPO / "research" / "trials.jsonl"
REPORTS = REPO / "research" / "reports"
WAVES = REPO / "research" / "waves"
ARENA_JOURNAL = REPO / "var" / "journal" / "events.jsonl"


def _canary(_a) -> int:
    from research.engine import sandbox

    sandbox.canary()
    print("canary OK: the sandbox refuses network access, reads outside the allowlist and writes outside tmpfs")
    return 0


def _build(a) -> int:
    from research.data import build_data

    doc = build_data(a.data)
    print(f"manifest: {len(doc['files'])} files")
    return 0


def _wave(a) -> int:
    from research.wave import WaveError, run_wave, freeze_sheets

    base = Path(a.waves) / str(a.number)
    sheets, strategies = base / "sheets", base / "strategies"
    if a.freeze:
        man = freeze_sheets(sheets)
        print(f"{len(man)} sheets frozen in {sheets / 'MANIFEST.json'}: commit them with the strategies, "
              f"then tag research-wave-{a.number}-sheets, before launching the wave")
        return 0
    from research.data import load
    from research.engine.journal import ResearchJournal

    if a.without_anchor:
        print("wave refused: external anchoring is mandatory for a wave (--without-anchor refused)",
              file=sys.stderr)
        return 2
    try:
        crit = load_criteria()
        verify_criteria(crit)
        data = load(a.data, crit)
        journal = ResearchJournal(a.journal)
        anchor = Path(a.arena_journal)
        rep = run_wave(a.number, sheets, strategies, data, journal, crit, reports_dir=a.reports,
                             arena_journal=anchor, decision_path=base / "DECISION-OWNER.md")
    except (WaveError, CriteriaError) as e:
        print(f"wave refused: {e}", file=sys.stderr)
        return 2
    # Output meant for agents: binary statuses only (no figures, no trial ids).
    print(f"wave {a.number} finished{' (INCOMPLETE: cap reached)' if rep.cap_reached else ''}.")
    return _display_statuses(rep.statuses_path)


def _display_statuses(path: Path) -> int:
    print(f"# {path.name}")
    for s in json.loads(path.read_text()):
        print(f"- {s['name']}: {s['verdict']} ({s['mechanism']})")
    return 0


def _statuses(a) -> int:
    files = sorted(Path(a.reports).glob("wave-*-statuses.json"))
    if not files:
        print("no status")
        return 0
    for f in files:
        _display_statuses(f)
    return 0


def _verify(a) -> int:
    from research.data.manifest import verify_manifest
    from research.engine.journal import ResearchJournal

    crit = load_criteria()
    ok = True

    def report(name: str, good: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= good
        print(f"{'OK    ' if good else 'FAIL '} {name}{': ' + detail if detail else ''}")

    try:
        verify_criteria(crit)
        report("criteria.yaml", True, crit.sha256[:16])
    except CriteriaError as e:
        report("criteria.yaml", False, str(e)[:200])
    try:
        verify_manifest(a.data)
        report("data manifest", True)
    except Exception as e:  # noqa: BLE001
        report("data manifest", False, str(e)[:200])
    if Path(a.journal).is_file():
        j = ResearchJournal(a.journal)
        try:
            j.verify_anchor(None if a.without_anchor else a.arena_journal)
            report("research journal", True, f"{j.n_lines()} lines, {j.n_ids()} trials, head {j.head()[:16]}")
        except Exception as e:  # noqa: BLE001
            report("research journal", False, str(e)[:200])
    else:
        report("research journal", True, "absent (no trial)")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m research")
    p.add_argument("--data", default=str(DATA))
    p.add_argument("--journal", default=str(JOURNAL))
    p.add_argument("--reports", default=str(REPORTS))
    p.add_argument("--arena-journal", default=str(ARENA_JOURNAL))
    p.add_argument("--without-anchor", action="store_true")
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("build-data").set_defaults(f=_build)
    sp.add_parser("canary").set_defaults(f=_canary)
    v = sp.add_parser("wave")
    v.add_argument("number", type=int)
    v.add_argument("--freeze", action="store_true", help="write MANIFEST.json of the sheets (before the commit)")
    v.add_argument("--waves", default=str(WAVES), help="waves folder (<n>/sheets, <n>/strategies)")
    v.set_defaults(f=_wave)
    sp.add_parser("statuses").set_defaults(f=_statuses)
    sp.add_parser("verify").set_defaults(f=_verify)
    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    raise SystemExit(main())
