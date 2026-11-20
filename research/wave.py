"""Coded orchestration of a research wave (ARCHITECTURE.md, PROTOCOL sections 4, 6, 7).

No LLM decides whether a trial passes: this module reads sheets (YAML), runs the engine on every grid point,
applies gates C1-C16, selects candidates and writes the reports. Every path is a parameter (tests use tmp).

Format of a sheet `sheets_dir/<name>.yaml` (required fields):
    family, name, mechanism, class_ (directional|hedged), strategy (file name inside `strategies_dir`),
    grid (parameter -> list of values, geometric: >= 3 values, ratio >= 1.25), fixed_params (optional).
The rest of the sheet (who loses on the other side, falsifiable prediction...) is hashed with it but not read
here: the sheet auditor is a separate agent.

Production paths: `research/waves/<n>/sheets/` and `research/waves/<n>/strategies/`.

Freeze (two levels, both required):
  1. `sheets_dir/MANIFEST.json` {file: sha256}, written by `freeze_sheets` BEFORE the wave;
  2. the content of every sheet AND every strategy is compared byte for byte with the git tag
     `research-wave-<n>-sheets` (`git show`): any difference, file missing on disk or extra file -> refusal.
     There is no option to skip it; tests pass a fake git repository (`repo=`).

Research integrity:
  * `criteria.yaml`: `config.verify_criteria` is called at launch AND before every trial (the engine's
    `run_trial` calls it too).
  * Resume: an interrupted wave can be relaunched. A trial (family, parameters, universe, code sha256)
    already closed by an `end` in the journal is NOT rerun: its series is reloaded from the cache
    `<reports>/series/<id>.npz`, whose sha256 must equal `series_sha256` of the `end` (otherwise refusal). A
    `start` without `end` stays counted in N and the trial is redone under a new id.
  * Cumulative caps on the journal, checked BEFORE every line (grid, C15 and C16 included):
    600 in total; wave 1: at most 120 main variants and 6 families.
  * Wave numbers and stop rule: chained events `wave_started`, `wave_ended`, `decision_owner`
    in the journal. Wave n > 1 requires wave n-1 to be finished (`wave_ended`) and its report
    `wave-<n-1>.md` to exist; if the best DSR of wave n-1 is < 0.5 (threshold from criteria.yaml), it requires
    a non-empty `research/waves/<n>/DECISION-OWNER.md`, whose sha256 is recorded in the journal. The stop is
    computed here from the journal, never read from an editable file.
  * V per class: sr_day of ALL research trials in the journal (`journal_sr_days`).
  * Outputs: `wave-<n>-statuses.json` (name, mechanism, binary verdict) is the only output meant for
    agents; all figures are in `wave-<n>.md` (orchestrator and owner).
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import re
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import yaml

from research.config import REPO, verify_criteria
from research.engine.trial import TrialSheet, CapError, TrialResult, run_trial
from research.engine.journal import decimal12, canonical_params
from research.engine.panel import panel_from_data
from research.engine.portfolio import EngineSeries, equal_weighted_basket
from research.gates import stats
from research.gates.adapter import to_trial, to_causality_report, to_basket_series
from research.gates.evaluate import NOT_EVALUABLE, Verdict, evaluate_candidate, grid_valid
from research.gates.arena_replay import replay
from research.gates.selection import Candidate, Selection, select_candidates

DEFAULT_REPORTS = REPO / "research" / "reports"
DEFAULT_WAVES = REPO / "research" / "waves"
SHEET_FIELDS = ("family", "name", "mechanism", "class_", "strategy", "grid")
SHEETS_MANIFEST = "MANIFEST.json"
DECISION_OWNER = "DECISION-OWNER.md"
EVT_WAVE_STARTED, EVT_WAVE_ENDED, EVT_DECISION = "wave_started", "wave_ended", "decision_owner"
FAMILY_PATTERN = re.compile(r"[A-Za-z0-9]+(-[A-Za-z0-9]+)*")
# Gates evaluated before fetching C15 and C16 (PROTOCOL: "for every trial that passes C1-C14").
_GATES_BEFORE = ("C1", "C5", "C6", "C7", "C8", "C9", "C11", "C12", "C13", "C14")


class WaveError(Exception):
    """The wave cannot be launched (unfrozen sheets, cap, stop rule...)."""


@dataclass(frozen=True)
class Sheet:
    file: str
    sha256: str
    family: str
    name: str
    mechanism: str
    class_: str
    strategy: str
    grid: dict
    fixed_params: dict
    perp_signals: bool = False  # directional: perp and funding passed as signals (no perp leg)


@dataclass
class TrialLine:
    id: str
    family: str
    params: dict
    code: str
    verdict: Verdict | None = None
    sharpe_net: float | None = None
    note: str = ""


@dataclass
class WaveReport:
    number: int
    lines: list[TrialLine] = field(default_factory=list)
    refused: dict[str, str] = field(default_factory=dict)  # sheet -> reason
    selection: Selection | None = None
    candidates: list[str] = field(default_factory=list)  # trials that pass every gate
    best_dsr: float | None = None
    stop: bool = False  # stop rule: next wave forbidden without a written owner decision
    n_wave_trials: int = 0  # grid lines of the wave (new or resumed)
    n_resumes: int = 0  # lines (grid, C15, C16) reloaded from the journal without being rerun
    n_extra_lines: int = 0  # arena + control: count in the real N
    n_real_total: int = 0
    cap_reached: bool = False
    report_path: Path | None = None
    statuses_path: Path | None = None


# --------------------------------------------------------------------------------------------------
# Sheets and freeze
# --------------------------------------------------------------------------------------------------


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def freeze_sheets(sheets_dir: Path | str) -> dict:
    """Write `MANIFEST.json` (sha256 of every `*.yaml` sheet). To be committed with the strategies, then
    tagged `research-wave-<n>-sheets` BEFORE the wave."""
    d = Path(sheets_dir)
    man = {p.name: _sha(p.read_bytes()) for p in sorted(d.glob("*.yaml"))}
    (d / SHEETS_MANIFEST).write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")
    return man


def _git(repo: Path, *args: str) -> bytes:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False, timeout=120)
    if r.returncode != 0:
        raise WaveError(f"git {' '.join(args[:2])} failed: {r.stderr.decode(errors='replace')[-300:].strip()}")
    return r.stdout


def _disk_files(d: Path, repo: Path) -> dict[str, bytes]:
    """{path relative to the repo: bytes} of every file in `d` (except __pycache__); symlinks refused."""
    out = {}
    for p in sorted(d.rglob("*")):
        if "__pycache__" in p.parts or p.is_dir():
            continue
        if p.is_symlink():
            raise WaveError(f"{p} is a symbolic link: refused")
        out[p.relative_to(repo).as_posix()] = p.read_bytes()
    return out


def verify_git_freeze(sheets_dir: Path | str, strategies_dir: Path | str, number: int, *,
                     repo: Path | str = REPO, tag: str | None = None) -> None:
    """Compare every file of `sheets_dir` and `strategies_dir` with the content of the git tag
    `research-wave-<number>-sheets` (default): same set of files, same bytes. Raises
    `WaveError` for a difference, a file missing from the tag or from the disk, or a missing tag."""
    tag = tag or f"research-wave-{number}-sheets"
    repo = Path(repo).resolve()
    _git(repo, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}")
    for d in (Path(sheets_dir), Path(strategies_dir)):
        d = d.resolve()
        try:
            rel = d.relative_to(repo).as_posix()
        except ValueError:
            raise WaveError(f"{d} is not inside the repository {repo}: freeze cannot be verified") from None
        items = _git(repo, "ls-tree", "-r", "-z", "--name-only", f"refs/tags/{tag}", "--", rel)
        in_tag = {x for x in items.decode().split("\0") if x and "__pycache__" not in x}
        disk = _disk_files(d, repo)
        if not in_tag:
            raise WaveError(f"{rel} is absent from tag {tag}")
        if absentees := sorted(in_tag - set(disk)):
            raise WaveError(f"file(s) of tag {tag} missing from disk : {absentees}")
        if extra := sorted(set(disk) - in_tag):
            raise WaveError(f"extra file(s) compared with tag {tag} : {extra}")
        for path, content in disk.items():
            if _git(repo, "show", f"refs/tags/{tag}:{path}") != content:
                raise WaveError(f"{path} differs from tag {tag}")


def read_sheets(sheets_dir: Path | str, strategies_dir: Path | str, number: int, *,
                repo: Path | str = REPO, tag: str | None = None) -> list[Sheet]:
    """Read the frozen sheets of wave `number`: manifest, then git tag (sheets AND strategies)."""
    d = Path(sheets_dir)
    man_path = d / SHEETS_MANIFEST
    if not man_path.is_file():
        raise WaveError(f"{man_path} missing: sheets not frozen")
    man = json.loads(man_path.read_text())
    files = sorted(p for p in d.glob("*.yaml"))
    if {p.name for p in files} != set(man):
        raise WaveError("the sheets present are not exactly those of the freeze manifest")
    for p in files:
        if _sha(p.read_bytes()) != man[p.name]:
            raise WaveError(f"{p.name} modified since the freeze (different sha256)")
    verify_git_freeze(sheets_dir, strategies_dir, number, repo=repo, tag=tag)
    out = []
    for p in files:
        content = p.read_bytes()
        doc = yaml.safe_load(content)
        missing = [c for c in SHEET_FIELDS if not isinstance(doc, dict) or c not in doc]
        if missing:
            raise WaveError(f"{p.name} : missing fields {missing}")
        if not isinstance(doc["family"], str) or not FAMILY_PATTERN.fullmatch(doc["family"]):
            raise WaveError(f"{p.name} : family {doc['family']!r} does not match the pattern {FAMILY_PATTERN.pattern} "
                             "(ASCII letters, digits, hyphens: one name = one family for the caps and V)")
        out.append(Sheet(p.name, _sha(content), str(doc["family"]), str(doc["name"]), str(doc["mechanism"]),
                         str(doc["class_"]), str(doc["strategy"]), dict(doc["grid"]),
                         dict(doc.get("fixed_params") or {}), bool(doc.get("perp_signals", False))))
    return out


def grid_points(grid: dict) -> list[dict]:
    names = sorted(grid)
    return [dict(zip(names, vals, strict=True)) for vals in itertools.product(*(sorted(grid[n]) for n in names))]


def _validate_sheet(f: Sheet, criteria, number: int, strat_dir: Path,
                   family_variants: dict[str, int] | None = None) -> str | None:
    """Reason for the refusal, or None. The engine applies the numeric rules; the sheet auditor judges the rest.
    `family_variants`: variants already accepted per family NAME (wave 1); the per-family cap is
    cumulated over all sheets of the same family, not per file. Updated if the sheet is accepted."""
    trials_cfg = criteria.trials
    if f.class_ not in ("directional", "hedged"):
        return f"unknown class {f.class_!r}"
    if Path(f.strategy).name != f.strategy or not (strat_dir / f.strategy).is_file():
        return f"strategy {f.strategy!r} not found in the strategies folder (plain file name expected)"
    n_params = len(f.grid)
    if not trials_cfg.min_parameters <= n_params <= trials_cfg.max_parameters:
        return f"{n_params} parameters (expected {trials_cfg.min_parameters} to {trials_cfg.max_parameters})"
    ok, reason = grid_valid(f.grid, trials_cfg)
    if not ok:
        return f"non-geometric grid: {reason}"
    n = math.prod(len(v) for v in f.grid.values())
    if number == 1:
        total = n + (family_variants or {}).get(f.family, 0)
        if total > trials_cfg.max_variants_per_family_wave_1:
            return (f"{total} variants for family {f.family!r} (all sheets of that family) > "
                    f"{trials_cfg.max_variants_per_family_wave_1} (wave 1)")
        if family_variants is not None:
            family_variants[f.family] = total
    return None


# --------------------------------------------------------------------------------------------------
# Journal: wave numbers, stop rule, resume, V
# --------------------------------------------------------------------------------------------------


def _write_event(journal, type_: str, payload: dict, arena_journal) -> None:
    """Chained wave event, then external anchoring (as after a trial)."""
    journal._add(type_, payload)
    journal.anchor(arena_journal)


def _wave_state(journal) -> tuple[dict[int, dict], dict[int, dict], dict[int, str]]:
    starts: dict[int, dict] = {}
    ends: dict[int, dict] = {}
    decisions: dict[int, str] = {}
    for e in journal.events():
        t, p = e["type"], e["payload"]
        if t == EVT_WAVE_STARTED:
            starts[int(p["number"])] = p
        elif t == EVT_WAVE_ENDED:
            ends[int(p["number"])] = p
        elif t == EVT_DECISION:
            decisions[int(p["number"])] = p["sha256"]
    return starts, ends, decisions


def stop_after(journal, previous_number: int, criteria) -> bool:
    """Stop rule computed FROM THE JOURNAL: the best DSR of wave `previous_number`
    (chained event `wave_ended`) is below the criteria.yaml threshold, or does not exist."""
    _, ends, _ = _wave_state(journal)
    if previous_number not in ends:
        raise WaveError(f"wave {previous_number} is not finished in the journal")
    raw_dsr = ends[previous_number].get("best_dsr")
    try:
        d = float(raw_dsr) if raw_dsr is not None else float("nan")
    except ValueError:
        d = float("nan")
    return not (math.isfinite(d) and d >= criteria.trials.stop_after_wave_1.dsr_max_below)


def _check_number(journal, number: int, criteria, reports: Path, decision_path: Path) -> None:
    """Refuse a wave out of sequence or without the required decision (read-only on the journal)."""
    if number < 1:
        raise WaveError(f"invalid wave number: {number}")
    starts, ends, decisions = _wave_state(journal)
    if number in ends:
        raise WaveError(f"wave {number} is already finished in the journal")
    if number not in starts:
        expected = 1 if not starts else max(starts) + 1
        if number != expected:
            raise WaveError(f"wave number {number}: numbers are consecutive, {expected} expected")
        if expected > 1 and (expected - 1) not in ends:
            raise WaveError(f"wave {expected - 1} is not finished: wave {number} is refused")
    if number == 1:
        return
    if not (reports / f"wave-{number - 1}.md").is_file():
        raise WaveError(f"report of wave {number - 1} ({reports / f'wave-{number - 1}.md'}) missing")
    if stop_after(journal, number - 1, criteria):
        if not decision_path.is_file() or not decision_path.read_bytes().strip():
            raise WaveError(f"stop rule of wave {number - 1}: {decision_path} (written owner decision, "
                             "non-empty) is required")
        sha = _sha(decision_path.read_bytes())
        if number in decisions and decisions[number] != sha:
            raise WaveError(f"{decision_path} changed since it was recorded in the journal")


def journal_sr_days(journal) -> dict[str, dict[str, list[float]]]:
    """class -> family -> sr_day of ALL research trials in the journal (main universe, status OK,
    all waves, resumed trials included; the lab is not part of it)."""
    out: dict[str, dict[str, list[float]]] = {}
    for e in journal.trials().values():
        start, end = e["start"], e["end"]
        if end is None or end.get("status") != "OK" or start.get("universe") != "main":
            continue
        # V is computed on the SAME series as C1: for `hedged`, the series relative to the capital tied up
        # (`gates_sr_day`); for `directional`, total capital (`sr_day`, identical).
        sr_key = "gates_sr_day" if start["class_"] == "hedged" else "sr_day"
        if sr_key not in end:  # never fall back on `sr_day`: less dispersed, it would lower V
            raise WaveError(f"trial {start.get('id')} ({start['class_']}): `end` without `{sr_key}`")
        try:
            x = float(end[sr_key])
        except (ValueError, TypeError):
            continue
        if math.isfinite(x):
            out.setdefault(start["class_"], {}).setdefault(start["family"], []).append(x)
    return out


def _closed_index(journal) -> dict[tuple, tuple[str, dict]]:
    """(family, canonical params, universe, code_sha256) -> (id, payload of the `end`) of closed trials."""
    out = {}
    for eid, e in journal.trials().items():
        if e["end"] is None:
            continue
        start = e["start"]
        out[(start["family"], start["params"], start["universe"], start["code_sha256"])] = (eid, e["end"])
    return out


def _n_starts(journal, *, main_only: bool = False) -> tuple[int, set[str]]:
    evts = [e["payload"] for e in journal.events("start")]
    if main_only:
        evts = [p for p in evts if p.get("universe") == "main"]
    return len(evts), {p["family"] for p in evts}


# --- series cache (resume) -------------------------------------------------------------------


def _series_sha(track: EngineSeries) -> str:
    return hashlib.sha256(np.ascontiguousarray(track.net_returns[track.eval_mask]).tobytes()).hexdigest()


def _save(cache: Path, res: TrialResult) -> None:
    """Write the series of an OK trial (npz) and its causality report (json), atomically."""
    if res.code != "OK" or res.track is None:
        return
    cache.mkdir(parents=True, exist_ok=True)
    arrays = {k: np.asarray(v) for k, v in res.track.__dict__.items() if isinstance(v, np.ndarray)}
    arrays["_class"] = np.array(res.track.class_)
    arrays["_symboles"] = np.array(list(res.track.symbols), dtype=str)
    tmp = cache / f"{res.id}.tmp.npz"
    np.savez(tmp, **arrays)
    (cache / f"{res.id}.causality.json").write_text(json.dumps(res.causality))
    tmp.replace(cache / f"{res.id}.npz")  # the .npz is written last: its presence = complete cache


def _reload(cache: Path, eid: str, end: dict, universe: str) -> TrialResult:
    if end.get("status") != "OK":
        return TrialResult(id=eid, code=str(end.get("status")), universe=universe)
    path = cache / f"{eid}.npz"
    if not path.is_file():
        raise WaveError(f"trial {eid} closed in the journal but its series is missing ({path}): resume "
                         "is impossible without rerunning the trial (which would count it twice)")
    with np.load(path, allow_pickle=False) as z:
        fields = {k: z[k] for k in z.files if not k.startswith("_")}
        track = EngineSeries(class_=str(z["_class"]), symbols=tuple(str(x) for x in z["_symboles"]), **fields)
    if _series_sha(track) != end.get("series_sha256"):
        raise WaveError(f"series of trial {eid}: sha256 differs from the journal's (cache altered)")
    causality = json.loads((cache / f"{eid}.causality.json").read_text()) \
        if (cache / f"{eid}.causality.json").is_file() else None
    return TrialResult(id=eid, code="OK", universe=universe, track=track, causality=causality)


# --------------------------------------------------------------------------------------------------
# Launching a trial (checks, resume, caps)
# --------------------------------------------------------------------------------------------------


def _trial_sheet(f: Sheet) -> TrialSheet:
    return TrialSheet(f.family, f.class_, f.sha256, bool(getattr(f, "perp_signals", False)))


@dataclass
class _Ctx:
    number: int
    data: object
    journal: object
    criteria: object
    strat_dir: Path
    cache: Path
    rep: WaveReport
    arena_journal: object = None
    causality: bool = True
    timeout_s: float | None = None
    spot_cost_bp: int | None = None
    test: bool = False  # tests only: allows a missing arena journal (external anchoring)
    closed: dict = field(default_factory=dict)
    draws_k: dict = field(default_factory=dict)  # family -> draw (wave_started): same k for its variants

    def verify_caps(self, universe: str) -> None:
        """Cumulative caps on the journal, checked BEFORE launching the line."""
        trials_cfg = self.criteria.trials
        n, _ = _n_starts(self.journal)
        if n >= self.criteria.total_cap:
            raise CapError(f"{n} trials already started, total cap {self.criteria.total_cap}")
        if self.number == 1 and universe == "main":
            n1, _ = _n_starts(self.journal, main_only=True)
            if n1 >= trials_cfg.wave_1_cap:
                raise CapError(f"{n1} variants already started, wave 1 cap {trials_cfg.wave_1_cap}")

    def launch(self, f: Sheet, params: dict, universe: str = "main", *, causality: bool | None = None
               ) -> TrialResult:
        verify_criteria(self.criteria)  # before EVERY trial
        code = self.strat_dir / f.strategy
        key = (f.family, canonical_params(params), universe, _sha(code.read_bytes()))
        if key in self.closed:
            eid, end = self.closed[key]
            self.rep.n_resumes += 1
            return _reload(self.cache, eid, end, universe)
        self.verify_caps(universe)
        res = run_trial(
            _trial_sheet(f), code, params, self.data, self.journal, self.criteria, universe=universe,
            arena_journal=self.arena_journal, causality=self.causality if causality is None else causality,
            timeout_s=self.timeout_s, spot_cost_bp=self.spot_cost_bp, test=self.test,
            draw_k=self.draws_k.get(f.family))
        _save(self.cache, res)
        self.closed[key] = (res.id, self.journal.trials()[res.id]["end"])
        return res


# --------------------------------------------------------------------------------------------------
# Wave
# --------------------------------------------------------------------------------------------------


def _arena_closes(data, symbols, days_idx):
    import pandas as pd

    cols = {}
    for s in symbols:
        df = data.spot_1d[s]
        cols[s] = df["close"].reindex(days_idx)
    return pd.DataFrame(cols, index=days_idx)


def run_wave(
    number: int, sheets_dir, strategies_dir, data, journal, criteria, *,
    reports_dir: Path | str = DEFAULT_REPORTS, arena_journal: Path | str | None = None,
    repo: Path | str = REPO, tag: str | None = None, decision_path: Path | str | None = None,
    causality: bool = True, timeout_s: float | None = None, spot_cost_bp: int | None = None,
    control_symbols: list[str] | None = None, test: bool = False,
) -> WaveReport:
    """Launch (or resume) wave `number`. `data`: the loader's `Data` or a `Panel` (tests). Trials
    are written to `journal` (`ResearchJournal`); the anchor goes to `arena_journal` if provided.
    `repo`/`tag`: git repository and freeze tag (default: the project repository and `research-wave-<n>-sheets`).
    `decision_path`: default `sheets_dir/../DECISION-OWNER.md`. `arena_journal` is mandatory (external
    anchoring) unless `test=True`, reserved for tests."""
    verify_criteria(criteria)
    if arena_journal is None and not test:
        raise WaveError("arena journal required (external anchoring); test=True is reserved for tests")
    reports = Path(reports_dir)
    strat_dir = Path(strategies_dir)
    decision = Path(decision_path) if decision_path else Path(sheets_dir).parent / DECISION_OWNER
    trials_cfg = criteria.trials
    rep = WaveReport(number)

    sheets = read_sheets(sheets_dir, strat_dir, number, repo=repo, tag=tag)
    journal.initialize()
    journal.verify_anchor(arena_journal)
    _check_number(journal, number, criteria, reports, decision)
    reports.mkdir(parents=True, exist_ok=True)

    family_names = {f.family for f in sheets}
    if len(family_names) > trials_cfg.max_families_per_wave:
        raise WaveError(f"{len(family_names)} families > {trials_cfg.max_families_per_wave}")
    valid = []
    family_variants: dict[str, int] = {}
    for f in sheets:
        reason = _validate_sheet(f, criteria, number, strat_dir, family_variants)
        if reason:
            rep.refused[f.file] = reason
        else:
            valid.append(f)

    closed = _closed_index(journal)
    ctx = _Ctx(number, data, journal, criteria, strat_dir, reports / "series", rep,
               arena_journal=arena_journal, causality=causality, timeout_s=timeout_s,
               spot_cost_bp=spot_cost_bp, test=test, closed=closed)
    new_trials = 0
    for f in valid:
        code_sha = _sha((strat_dir / f.strategy).read_bytes())
        for pt in grid_points(f.grid):
            key = (f.family, canonical_params({**f.fixed_params, **pt}), "main", code_sha)
            new_trials += key not in closed
    n_starts, _ = _n_starts(journal)
    if n_starts + new_trials > criteria.total_cap:
        raise WaveError(f"{n_starts} + {new_trials} trials would exceed the cap of {criteria.total_cap}")
    if number == 1:
        n1, journal_families = _n_starts(journal, main_only=True)
        if n1 + new_trials > trials_cfg.wave_1_cap:
            raise WaveError(f"{n1} variants already started + {new_trials} to launch > wave 1 cap "
                             f"({trials_cfg.wave_1_cap})")
        families = journal_families | {f.family for f in valid}
        by_casefold: dict[str, set[str]] = {}
        for fam in families:
            by_casefold.setdefault(fam.casefold(), set()).add(fam)
        duplicates = sorted(sorted(v) for v in by_casefold.values() if len(v) > 1)
        if duplicates:
            raise WaveError(f"families that differ only by case (a single family): {duplicates}")
        if len(families) > trials_cfg.max_families_per_wave:
            raise WaveError(f"{len(families)} families (journal included) > {trials_cfg.max_families_per_wave}")

    # --- chained markers: wave launch, owner decision -------------------------------
    starts, _, decisions = _wave_state(journal)
    if number not in starts:
        # One draw per family, written BEFORE any trial and reloaded on resume: all variants of a family
        # (and their arena and control universes) drop the same k warm-up days (bounded per panel), so
        # C7 compares neighbors at the same phase, and a resume does not redraw a new k.
        draws = {fam: int.from_bytes(os.urandom(4), "big") for fam in sorted({f.family for f in valid})}
        _write_event(journal, EVT_WAVE_STARTED, {
            "number": number, "criteria_sha256": criteria.sha256,
            "sheets": {f.file: f.sha256 for f in sheets}, "draws_k": draws}, arena_journal)
    else:
        draws = {k: int(v) for k, v in (starts[number].get("draws_k") or {}).items()}
        absent = sorted({f.family for f in valid} - set(draws))
        if absent:
            raise WaveError(f"wave {number} resumed: families without a k draw in wave_started: {absent}")
    ctx.draws_k = draws
    if number > 1 and stop_after(journal, number - 1, criteria) and number not in decisions:
        _write_event(journal, EVT_DECISION, {"number": number, "sha256": _sha(decision.read_bytes()),
                                                  "file": f"{DECISION_OWNER}"}, arena_journal)

    # --- full grid on the main universe ----------------------------------------------------
    from research.engine.panel import Panel

    main_panel = data if isinstance(data, Panel) else None
    grid_results: list[tuple] = []  # (sheet, params, point, TrialResult)
    try:
        for f in valid:
            for pt in grid_points(f.grid):
                params = {**f.fixed_params, **pt}
                res = ctx.launch(f, params)
                rep.n_wave_trials += 1
                grid_results.append((f, params, pt, res))
    except CapError:
        rep.cap_reached = True

    trials = {}
    for f, params, pt, res in grid_results:
        if res.code == "OK":
            trials[res.id] = to_trial(res, family=f.family, class_=f.class_, params=pt)
    all_trials = list(trials.values())
    sr_days = journal_sr_days(journal)  # V per class: all research trials in the journal

    basket_cache: dict = {}

    def basket(class_: str):
        if "p" not in basket_cache:
            panel = main_panel or panel_from_data(data, "main", with_perp=False,
                                                          arena_symbols=tuple(criteria.arena_universe))
            basket_cache["p"] = (panel, to_basket_series(equal_weighted_basket(panel, criteria)))
        return basket_cache["p"][1]

    candidates: list[Candidate] = []
    verdicts: dict[str, Verdict] = {}
    for f, params, pt, res in grid_results:
        line = TrialLine(res.id, f.family, pt, res.code)
        rep.lines.append(line)
        if res.code != "OK":
            continue
        e = trials[res.id]
        line.sharpe_net = stats.sharpe(e.net)
        caus = to_causality_report(res.causality, criteria)
        kw = {"research_sr_days": sr_days}
        v = evaluate_candidate(e, all_trials, criteria, f.grid, basket(f.class_), None, None, caus, **kw)
        if all(v.gates[c][0] for c in _GATES_BEFORE) and all(ok for ok, _, _ in v.consistency.values()):
            arena, control, n_extra = _c15_c16(f, params, ctx, control_symbols)
            rep.n_extra_lines += n_extra
            v = evaluate_candidate(e, all_trials, criteria, f.grid, basket(f.class_), arena, control, caus, **kw)
        if f.class_ == "hedged":
            v = _without_c15(v)
        line.verdict = v
        verdicts[res.id] = v
        if v.passed:
            rep.candidates.append(res.id)
            candidates.append(Candidate(res.id, v.gates["C1"][1], e.net - basket(f.class_).reindex(e.net.index)))

    dsrs = [v.gates["C1"][1] for v in verdicts.values() if math.isfinite(v.gates["C1"][1])]
    rep.best_dsr = max(dsrs) if dsrs else None
    rep.stop = rep.best_dsr is None or rep.best_dsr < trials_cfg.stop_after_wave_1.dsr_max_below
    rep.selection = select_candidates(candidates, criteria)
    rep.n_real_total = journal.n_ids()
    _write(rep, valid, reports, criteria)
    _write_event(journal, EVT_WAVE_ENDED, {
        "number": number, "best_dsr": None if rep.best_dsr is None else decimal12(rep.best_dsr),
        "candidates": list(rep.candidates), "cap_reached": rep.cap_reached,
        "n_wave_trials": rep.n_wave_trials}, arena_journal)
    return rep


def _without_c15(v: Verdict) -> Verdict:
    """Hedged class: C15 (arena compatibility) is "spot only" (PROTOCOL section 6): not applicable
    (true) and the report says so. C16 also applies to hedged (control symbols that have a perp) and
    stays as evaluated; the other gates and the consistency checks remain required."""
    gates = dict(v.gates)
    gates["C15"] = (True, "not applicable (hedged)", None)
    passed = all(ok for ok, _, _ in gates.values()) and all(ok for ok, _, _ in v.consistency.values())
    return replace(v, gates=gates, passed=passed)


def _is_data_missing(data, sym: str, f: Sheet) -> bool:
    """True if the data the sheet needs is missing for `sym` (hedged: perp; perp_signals: funding).
    The symbol is then "not evaluable" (neither in the numerator of C16, nor in the minimum of 10)."""
    need_perp = f.class_ == "hedged"
    need_funding = f.class_ == "directional" and f.perp_signals
    if not (need_perp or need_funding):
        return False
    if hasattr(data, "control_perp_1h"):  # the loader's `Data`
        if need_perp and data.control_perp_1h.get(sym) is None:
            return True
        return bool(need_funding and data.control_funding.get(sym) is None)
    if sym not in data.symbols:  # `Panel` (tests)
        return True
    panel = data.sub_universe([sym])
    return panel.eligibles_perp is None or not bool(panel.eligibles_perp.any())


def _c15_c16(f: Sheet, params: dict, ctx: _Ctx, control_symbols: list[str] | None = None):
    """C15 (directional only): trial on the arena universe, then riskd/fills replay. C16: one trial per
    control symbol; a symbol whose required data is missing is `NOT_EVALUABLE`, a non-OK trial counts as
    None (failure). Caps are checked before every line; if the cap is reached, the remaining symbols
    are missing (failures, since the C16 denominator is fixed)."""
    import pandas as pd

    from research.engine.panel import Panel

    data, n_extra, arena = ctx.data, 0, None
    if f.class_ == "directional":
        try:
            r = ctx.launch(f, params, "arena", causality=False)
            n_extra += 1
            if r.code == "OK":
                s = r.track
                idx = pd.to_datetime(s.days, unit="s")
                cols = list(s.symbols)
                weight = pd.DataFrame(s.spot_weight, index=idx, columns=cols)
                m = s.eval_mask
                if isinstance(data, Panel):
                    closes = pd.DataFrame(data.sub_universe(cols).spot_1d[:, :, 3], index=idx, columns=cols)
                    closes = closes.where(data.sub_universe(cols).eligibles)
                else:
                    closes = _arena_closes(data, cols, idx)
                arena = replay(weight[m], closes[m], fee_bp=50, slippage_bp=5, half_spread_bp=5)
        except CapError:
            ctx.rep.cap_reached = True
            return None, None, n_extra
    control = {}
    symbols = (list(control_symbols) if control_symbols is not None
                else list(data.control) if hasattr(data, "control") else [])
    for sym in symbols:
        if _is_data_missing(data, sym, f):
            control[sym] = NOT_EVALUABLE
            continue
        try:
            r = ctx.launch(f, params, f"control:{sym}", causality=False)
        except CapError:
            ctx.rep.cap_reached = True
            break
        n_extra += 1
        control[sym] = (to_trial(r, family=f.family, class_=f.class_, params=params)
                         if r.code == "OK" else None)
    return arena, (control or None), n_extra


# --------------------------------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------------------------------


def _fmt(x) -> str:
    if isinstance(x, float):
        return f"{x:.4g}"
    if isinstance(x, dict):
        return "{" + ", ".join(f"{k}: {_fmt(v)}" for k, v in x.items()) + "}"
    if isinstance(x, (tuple, list)):
        return "(" + ", ".join(_fmt(v) for v in x) + ")"
    return str(x)


def _write(rep: WaveReport, sheets: list[Sheet], reports: Path, criteria) -> None:
    L = [f"# Wave {rep.number}", "",
         ("Document for the orchestrator and the owner: it contains figures and goes to no agent. Agents "
          f"only receive `wave-{rep.number}-statuses.json`."), "",
         (f"Grid trials: {rep.n_wave_trials}; extra lines (arena, control): "
          f"{rep.n_extra_lines}; of which reloaded from the journal without a rerun (resume): {rep.n_resumes}; "
          f"real N in the journal: {rep.n_real_total}; DSR N: {criteria.n_dsr}."),
         f"Best DSR: {_fmt(rep.best_dsr)}. Stop rule triggered: {'yes' if rep.stop else 'no'}.", ""]
    if rep.cap_reached:
        L += ["**Trial cap reached: the wave is incomplete.**", ""]
    if rep.refused:
        L += ["## Sheets refused by the engine", ""] + [f"- {k} : {v}" for k, v in sorted(rep.refused.items())] + [""]
    L += ["## All trials", "", "| id | family | parameters | code | net Sharpe | failed gates | passes |",
          "|---|---|---|---|---|---|---|"]
    for ln in rep.lines:
        failures = ", ".join(ln.verdict.failures()) if ln.verdict else ""
        passed = "yes" if ln.verdict and ln.verdict.passed else "no"
        L.append(f"| {ln.id} | {ln.family} | {_fmt(ln.params)} | {ln.code} | {_fmt(ln.sharpe_net)} | {failures} | {passed} |")
    L += ["", "## Detailed verdicts", "",
          ("C16: measure = (share, positives, evaluable, not evaluable, size of the control universe); "
           "the share is relative to the fixed size of the universe."), ""]
    for ln in rep.lines:
        if not ln.verdict:
            continue
        L.append(f"### {ln.id} ({ln.family} {_fmt(ln.params)})")
        for k, (ok, val, threshold) in {**ln.verdict.gates, **ln.verdict.consistency}.items():
            L.append(f"- {k}: {'OK' if ok else 'FAIL'}; measure {_fmt(val)}; threshold {_fmt(threshold)}")
        L.append("")
    L += ["## Selection", ""]
    if rep.selection and rep.selection.retained:
        L.append(f"Retained: {', '.join(rep.selection.retained)}. "
                 f"P(at least one not refuted in paper | H0) = {rep.selection.p_at_least_one_not_refuted:.4f} "
                 "(simulation of the refutation rule of section 9, see gates/selection.py).")
        L += [f"- discarded {k}: {v}" for k, v in rep.selection.discarded.items()]
    else:
        L.append("No candidate: outcome B unless another wave is decided.")
    rep.report_path = reports / f"wave-{rep.number}.md"
    rep.report_path.write_text("\n".join(L) + "\n")

    # Statuses: what the next researchers will see (name, mechanism, binary verdict, nothing else).
    per_family: dict[str, list[TrialLine]] = {}
    for ln in rep.lines:
        per_family.setdefault(ln.family, []).append(ln)
    statuses = []
    for f in sheets:
        lines = per_family.get(f.family, [])
        winner = any(ln.id in rep.candidates for ln in lines)
        statuses.append({"name": f.name, "mechanism": f.mechanism, "verdict": "not_discarded" if winner else "discarded"})
    for sheet_file, reason in sorted(rep.refused.items()):
        statuses.append({"name": sheet_file, "mechanism": "", "verdict": "discarded"})
    rep.statuses_path = reports / f"wave-{rep.number}-statuses.json"
    rep.statuses_path.write_text(json.dumps(statuses, ensure_ascii=False, indent=1) + "\n")
