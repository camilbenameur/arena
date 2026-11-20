"""Regression tests for the fixes from the adversarial review of the gates and the wave orchestration.

One test per fix (numbering of the request): 1 sha256 of criteria.yaml, 2 resume and cumulative
caps, 3 stop rule and wave numbers, 4 freeze tied to the git tag, 5 V per class, 6 C7 and ignored
parameters, 7 C16, 8 flat C5/C13, 9 selection tolerance, 10 outputs meant for agents.

Journals, git repositories and reports are in tmp_path; synthetic data only.
"""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import yaml

from research import wave
from research.config import (
    CRITERIA_PATH,
    REPO,
    SHA256_CRITERIA_V1,
    TAG_PROTOCOL,
    CriteriaError,
    Section,
    load_criteria,
    verify_criteria,
)
from research.engine.trial import TrialSheet, CapError, run_trial
from research.engine.journal import ResearchJournal, canonical_params
from research.engine.panel import synthetic
from research.gates import dsr, evaluate, selection, stats
from research.gates.adapter import to_trial


@pytest.fixture(autouse=True)
def _fixed_k(monkeypatch):
    """Exact equivalence between runs (resume, reference): k = 0 days withdrawn, drawn elsewhere."""
    from research.engine import sandbox
    monkeypatch.setattr(sandbox, "draw_days_withdrawn", lambda *a, **k: 0)
from research.gates.evaluate import Trial
from tests.research.test_integration import (
    START_2019_09,
    Repo,
    _wave_docs,
    _sheet,
    _wave_panel,
)

SHEET = TrialSheet("F1", "directional", "a" * 64)


@pytest.fixture(scope="module")
def crit():
    return load_criteria()


@pytest.fixture
def dummy_lab(tmp_path):
    d = tmp_path / "lab"
    d.mkdir()
    (d / "trials.jsonl").write_text("\n".join(json.dumps({"id": f"E{i:04d}", "prev_hash": "x"}) for i in range(1, 8)) + "\n")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    for cmd in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "x"], ["tag", "final-freeze"]):
        subprocess.run(["git", "-C", str(d), *cmd], check=True, env=env, capture_output=True)
    return d


@pytest.fixture
def journal(tmp_path, dummy_lab):
    return ResearchJournal(tmp_path / "trials.jsonl", lab_repo=dummy_lab, clock=lambda: 1_700_000_000)


def _docs_f1():
    return {"f1.yaml": _wave_docs()["f1.yaml"]}  # 9 grid points


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path / "repo").add_wave(1, _docs_f1())


def _launch(repo, n, panel, journal, crit, tmp_path, **kw):
    return wave.run_wave(
        n, repo.sheets(n), repo.strategies(n), panel, journal, crit, reports_dir=tmp_path / "reports",
        repo=repo.root_path, causality=False, test=True, **kw)


def _with_caps(crit, *, total=None, wave_1=None, families=None):
    ess = crit.trials.to_dict()
    if wave_1 is not None:
        ess["wave_1_cap"] = wave_1
    if families is not None:
        ess["max_families_per_wave"] = families
    return dataclasses.replace(crit, trials=Section(ess), total_cap=total or crit.total_cap,
                               wave_1_cap=wave_1 or crit.wave_1_cap)


def _modified_criteria(tmp_path) -> Path:
    p = tmp_path / "criteria_modified.yaml"
    p.write_text(CRITERIA_PATH.read_text().replace("N_dsr: 726", "N_dsr: 400"))
    return p


# ==================================================================================================
# 1. sha256 of criteria.yaml
# ==================================================================================================


def test_expected_sha256_is_the_git_tag_one():
    r = subprocess.run(["git", "-C", str(REPO), "show", f"{TAG_PROTOCOL}:research/criteria.yaml"],
                       capture_output=True, check=False)
    if r.returncode != 0:
        pytest.skip("tag research-protocol-v1 absent")
    assert hashlib.sha256(r.stdout).hexdigest() == SHA256_CRITERIA_V1
    verify_criteria(load_criteria())  # the repository file is indeed the frozen version


def test_modified_criteria_refused_everywhere(tmp_path, journal, repo, crit, capsys, monkeypatch):
    modified = load_criteria(_modified_criteria(tmp_path))
    assert modified.n_dsr == 400 and modified.sha256 != SHA256_CRITERIA_V1
    with pytest.raises(CriteriaError, match="modified"):
        verify_criteria(modified)
    # run_wave: refusal before any write
    with pytest.raises(CriteriaError):
        _launch(repo, 1, _wave_panel(crit), journal, modified, tmp_path)
    assert journal.n_ids() == 0 and journal.n_lines() == 0
    # before EVERY trial (which also protects a Criteria object altered during a wave)
    ctx = wave._Ctx(1, _wave_panel(crit), journal, modified, repo.strategies(), tmp_path / "s",
                     wave.WaveReport(1), test=True)
    f = wave.read_sheets(repo.sheets(), repo.strategies(), 1, repo=repo.root_path)[0]
    with pytest.raises(CriteriaError):
        ctx.launch(f, {"H": 10, "L": 20, "k": 3})
    assert journal.n_ids() == 0
    # CLI `verify`
    from research import __main__ as cli

    monkeypatch.setattr(cli, "load_criteria", lambda: modified)
    assert cli.main(["--data", str(tmp_path / "empty"), "--journal", str(tmp_path / "absent.jsonl"),
                     "verify"]) == 1
    assert "FAIL  criteria.yaml" in capsys.readouterr().out
    # CLI `wave`: refusal (code 2), no trial
    assert cli.main(["--journal", str(journal.path), "--arena-journal", str(tmp_path / "a.jsonl"),
                     "--reports", str(tmp_path / "r"), "wave", "1", "--waves", str(repo.root_path / "waves")]) == 2
    assert journal.n_ids() == 0


# ==================================================================================================
# 2. Wave resume and cumulative caps
# ==================================================================================================


def _interrupt_after(monkeypatch, k: int):
    real = wave.run_trial
    counter = {"n": 0}

    def fake(*a, **kw):
        if counter["n"] >= k:
            raise KeyboardInterrupt("simulated interruption")
        counter["n"] += 1
        return real(*a, **kw)

    monkeypatch.setattr(wave, "run_trial", fake)
    return real


def _start_keys(journal):
    return [(p["family"], p["params"], p["universe"], p["code_sha256"])
            for p in (e["payload"] for e in journal.events("start"))]


def test_resume_after_interruption_no_duplicate_and_n_correct(tmp_path, journal, repo, crit, monkeypatch,
                                                              dummy_lab):
    panel = _wave_panel(crit)
    real = _interrupt_after(monkeypatch, 4)
    with pytest.raises(KeyboardInterrupt):
        _launch(repo, 1, panel, journal, crit, tmp_path)
    assert journal.n_ids() == 4 and len(journal.trials()) == 4
    monkeypatch.setattr(wave, "run_trial", real)
    rep = _launch(repo, 1, panel, journal, crit, tmp_path)
    keys = _start_keys(journal)
    assert journal.n_ids() == 9 and len(set(keys)) == 9  # correct N, no duplicate
    assert rep.n_wave_trials == 9 and rep.n_resumes == 4 and len(rep.lines) == 9
    assert all(e["end"] is not None for e in journal.trials().values())
    assert [e["payload"]["number"] for e in journal.events("wave_started")] == [1]  # a single launch
    # the reloaded series are those of the trial: same Sharpe as a never-interrupted wave
    other = ResearchJournal(tmp_path / "other.jsonl", lab_repo=dummy_lab, clock=lambda: 1_700_000_000)
    ref = wave.run_wave(1, repo.sheets(), repo.strategies(), panel, other, crit,
                               reports_dir=tmp_path / "reports_ref", repo=repo.root_path, causality=False, test=True)
    sh = {canonical_params(ln.params): ln.sharpe_net for ln in rep.lines}
    sh_ref = {canonical_params(ln.params): ln.sharpe_net for ln in ref.lines}
    assert sh.keys() == sh_ref.keys() and all(sh[k] == pytest.approx(sh_ref[k], rel=1e-9) for k in sh)
    # rerunning a finished wave is refused (no accidental duplicate)
    with pytest.raises(wave.WaveError, match="already finished"):
        _launch(repo, 1, panel, journal, crit, tmp_path)


def test_start_without_end_still_counts_and_the_trial_is_redone(tmp_path, journal, repo, crit, monkeypatch):
    panel = _wave_panel(crit)
    real = _interrupt_after(monkeypatch, 3)
    with pytest.raises(KeyboardInterrupt):
        _launch(repo, 1, panel, journal, crit, tmp_path)
    monkeypatch.setattr(wave, "run_trial", real)
    # crash between `start` and `end` of the 4th point: an orphan `start`
    f = wave.read_sheets(repo.sheets(), repo.strategies(), 1, repo=repo.root_path)[0]
    pt = wave.grid_points(f.grid)[3]
    code = hashlib.sha256((repo.strategies() / f.strategy).read_bytes()).hexdigest()
    journal.start({"id": journal.next_id(), "family": f.family, "class_": f.class_, "sheet_sha256": f.sha256,
                   "code_sha256": code, "params": canonical_params({**f.fixed_params, **pt}),
                   "universe": "main"})
    assert journal.n_ids() == 4
    rep = _launch(repo, 1, panel, journal, crit, tmp_path)
    # 3 closed + 1 orphan + 6 new (including the point redone under a new id) = 10: the orphan stays counted
    assert journal.n_ids() == 10 and rep.n_wave_trials == 9 and rep.n_resumes == 3
    keys = _start_keys(journal)
    assert len(keys) - len(set(keys)) == 1
    redone = [e for e in journal.trials().values()
               if e["start"]["params"] == canonical_params({**f.fixed_params, **pt})]
    assert len(redone) == 2 and sorted(x["end"] is None for x in redone) == [False, True]
    assert sum(1 for ln in rep.lines if ln.code == "OK") == 9


def test_caps_cumulative_over_the_journal(tmp_path, journal, repo, crit, monkeypatch):
    panel = _wave_panel(crit)
    real = _interrupt_after(monkeypatch, 5)
    with pytest.raises(KeyboardInterrupt):
        _launch(repo, 1, panel, journal, crit, tmp_path)
    monkeypatch.setattr(wave, "run_trial", real)
    # 5 already started + 4 to launch = 9: refused if the cumulative cap is < 9, whatever the call
    with pytest.raises(wave.WaveError, match="wave 1 cap"):
        _launch(repo, 1, panel, journal, _with_caps(crit, wave_1=8), tmp_path)
    with pytest.raises(wave.WaveError, match="would exceed the cap"):
        _launch(repo, 1, panel, journal, _with_caps(crit, total=8), tmp_path)
    assert journal.n_ids() == 5
    # the exact cap passes
    rep = _launch(repo, 1, panel, journal, _with_caps(crit, total=9, wave_1=9), tmp_path)
    assert journal.n_ids() == 9 and rep.n_wave_trials == 9


def test_family_cap_cumulative_over_the_journal(tmp_path, journal, repo, crit, monkeypatch):
    panel = _wave_panel(crit)
    _interrupt_after(monkeypatch, 1)
    with pytest.raises(KeyboardInterrupt):
        _launch(repo, 1, panel, journal, crit, tmp_path)
    monkeypatch.undo()
    # new sheets (other families) refrozen: F1 stays in the journal -> 3 families in total
    (repo.sheets() / "f1.yaml").unlink()
    docs = _wave_docs("X")
    docs["c2.yaml"] = _sheet("Other", "X2", "directional", "f1_lab.py", {"L": [10, 20, 40], "k": [2, 3, 5]})
    for name, d in docs.items():
        (repo.sheets() / name).write_text(yaml.safe_dump(d))
    wave.freeze_sheets(repo.sheets())
    repo.label(1)
    with pytest.raises(wave.WaveError, match="families"):
        _launch(repo, 1, panel, journal, _with_caps(crit, families=3), tmp_path)


def test_caps_checked_before_each_line_c15_c16_included(tmp_path, journal, crit):
    panel = _wave_panel(crit)
    f = wave.Sheet("f.yaml", "0" * 64, "F1", "n", "m", "directional", "f1_lab.py", {}, {})
    strat = Path(__file__).parent / "strategies"
    params = {"L": 20, "k": 3, "H": 10}
    ctx = wave._Ctx(1, panel, journal, crit, strat, tmp_path / "s", wave.WaveReport(1), causality=False,
                     test=True)
    assert ctx.launch(f, params).code == "OK"
    # total cap = n_ids + 1: the "arena" line passes, the first control line is refused BEFORE launch
    ctx.criteria = _with_caps(crit, total=journal.n_ids() + 1)
    arena, control, n_extra = wave._c15_c16(f, params, ctx, ["ADAUSDT", "ATOMUSDT"])
    assert arena is not None and control is None and n_extra == 1 and ctx.rep.cap_reached
    assert journal.n_ids() == 2  # never beyond the cap
    with pytest.raises(CapError):
        ctx.launch(f, params, "control:ADAUSDT")
    assert journal.n_ids() == 2
    # and wave 1: at most 120 main variants, arena/control lines do not count in it
    ctx2 = wave._Ctx(1, panel, journal, _with_caps(crit, wave_1=1), strat, tmp_path / "s", wave.WaveReport(1),
                      causality=False, test=True)
    with pytest.raises(CapError):
        ctx2.launch(f, {**params, "L": 40})
    assert ctx2.launch(f, params, "control:ADAUSDT").code == "OK"  # universe != main: not subject to the wave 1 cap


# ==================================================================================================
# 3. Stop rule and wave numbers
# ==================================================================================================


def _journal_with(journal, events, reports: Path, report_for=()):
    journal.initialize()
    for type_, payload in events:
        journal._add(type_, payload)
    reports.mkdir(parents=True, exist_ok=True)
    for n in report_for:
        (reports / f"wave-{n}.md").write_text("# report\n")


def _end(n, dsr_):
    return ("wave_ended", {"number": n, "best_dsr": dsr_})


def test_wave_numbers_are_consecutive(tmp_path, journal, crit):
    r, dec = tmp_path / "r", tmp_path / "DECISION-OWNER.md"
    _journal_with(journal, [("wave_started", {"number": 1}), _end(1, "0.97")], r, report_for=(1,))
    check_number = lambda n: wave._check_number(journal, n, crit, r, dec)
    check_number(2)  # DSR 0.97: no stop, no decision needed
    for n in (0, 3, 5):
        with pytest.raises(wave.WaveError, match="consecutive|invalid"):
            check_number(n)
    with pytest.raises(wave.WaveError, match="already finished"):
        check_number(1)
    # a wave started but not finished forbids the next one
    journal._add("wave_started", {"number": 2})
    check_number(2)  # resume of wave 2: allowed
    with pytest.raises(wave.WaveError, match="is not finished"):
        check_number(3)


def test_wave_without_previous_report_or_without_end_is_refused(tmp_path, journal, crit):
    r, dec = tmp_path / "r", tmp_path / "DECISION-OWNER.md"
    _journal_with(journal, [("wave_started", {"number": 1}), _end(1, "0.97")], r)  # no wave-1.md
    with pytest.raises(wave.WaveError, match="report of wave 1"):
        wave._check_number(journal, 2, crit, r, dec)
    with pytest.raises(wave.WaveError, match="is not finished"):
        wave.stop_after(journal, 2, crit)


@pytest.mark.parametrize(("dsr_", "stop"), [("0.97", False), ("0.5", False), ("0.4999", True), ("nan", True),
                                             (None, True)])
def test_stop_computed_from_the_journal(tmp_path, journal, crit, dsr_, stop):
    r, dec = tmp_path / "r", tmp_path / "v" / "2" / "DECISION-OWNER.md"
    _journal_with(journal, [("wave_started", {"number": 1}), _end(1, dsr_)], r, report_for=(1,))
    assert wave.stop_after(journal, 1, crit) is stop
    # a wave-1.json file with "stop: false" changes nothing: it is never read
    (r / "wave-1.json").write_text(json.dumps({"stop": False}))
    if stop:
        with pytest.raises(wave.WaveError, match="stop rule"):
            wave._check_number(journal, 2, crit, r, dec)
        dec.parent.mkdir(parents=True)
        dec.write_text("")
        with pytest.raises(wave.WaveError, match="stop rule"):
            wave._check_number(journal, 2, crit, r, dec)
        dec.write_text("continue.")
    wave._check_number(journal, 2, crit, r, dec)


def test_decision_recorded_by_sha256_and_immutable(tmp_path, journal, crit):
    r, dec = tmp_path / "r", tmp_path / "DECISION-OWNER.md"
    dec.write_text("continue.")
    sha = hashlib.sha256(dec.read_bytes()).hexdigest()
    _journal_with(journal, [("wave_started", {"number": 1}), _end(1, "0.1"), ("wave_started", {"number": 2}),
                            ("decision_owner", {"number": 2, "sha256": sha})], r, report_for=(1,))
    wave._check_number(journal, 2, crit, r, dec)
    dec.write_text("something else after all.")  # modified after being recorded
    with pytest.raises(wave.WaveError, match="changed since"):
        wave._check_number(journal, 2, crit, r, dec)


# ==================================================================================================
# 4. Freeze tied to the git tag
# ==================================================================================================


def _read(repo, **kw):
    return wave.read_sheets(repo.sheets(), repo.strategies(), 1, repo=repo.root_path, **kw)


def test_freeze_matching_the_tag_is_accepted(repo):
    assert {f.family for f in _read(repo)} == {"F1"}


def test_freeze_sheet_modified_after_the_tag_even_with_rebuilt_manifest(repo):
    f = repo.sheets() / "f1.yaml"
    f.write_text(f.read_text() + "\n# tweak\n")
    wave.freeze_sheets(repo.sheets())  # the manifest is rebuilt: only the tag can detect the tweak
    with pytest.raises(wave.WaveError, match="differs from tag"):
        _read(repo)


def test_freeze_strategy_modified_or_extra_or_missing(repo):
    s = repo.strategies() / "f1_lab.py"
    original = s.read_bytes()
    s.write_bytes(original + b"\n# cheat\n")
    with pytest.raises(wave.WaveError, match=r"f1_lab\.py differs from tag"):
        _read(repo)
    s.write_bytes(original)
    _read(repo)
    (repo.strategies() / "other.py").write_text("x = 1\n")
    with pytest.raises(wave.WaveError, match="extra file"):
        _read(repo)
    (repo.strategies() / "other.py").unlink()
    s.unlink()
    with pytest.raises(wave.WaveError, match="missing"):
        _read(repo)


def test_freeze_extra_or_missing_sheet(repo):
    (repo.sheets() / "z.yaml").write_text(yaml.safe_dump(_sheet("Z", "Z", "directional", "f1_lab.py", {"L": [1, 2, 4]})))
    wave.freeze_sheets(repo.sheets())
    with pytest.raises(wave.WaveError, match="extra file"):
        _read(repo)
    (repo.sheets() / "z.yaml").unlink()
    (repo.sheets() / "f1.yaml").unlink()
    wave.freeze_sheets(repo.sheets())
    with pytest.raises(wave.WaveError, match="missing"):
        _read(repo)


def test_freeze_without_tag_or_outside_repo_or_symlink(tmp_path, repo):
    with pytest.raises(wave.WaveError):
        wave.read_sheets(repo.sheets(), repo.strategies(), 2, repo=repo.root_path)  # tag wave-2 does not exist
    with pytest.raises(wave.WaveError):
        wave.read_sheets(repo.sheets(), repo.strategies(), 1, repo=tmp_path)  # not a repository containing the folders
    (repo.strategies() / "link.py").symlink_to(repo.strategies() / "f1_lab.py")
    with pytest.raises(wave.WaveError, match="symbolic link"):
        _read(repo)


def test_no_option_to_bypass_the_freeze(tmp_path):
    import inspect

    from research import __main__ as cli

    assert "verify_git" not in inspect.signature(wave.run_wave).parameters
    assert "verify_git" not in inspect.signature(wave.read_sheets).parameters
    with pytest.raises(SystemExit):
        cli.main(["wave", "1", "--without-git"])
    with pytest.raises(SystemExit):
        cli.main(["wave", "1", "--decision-written", "x"])


def test_cli_wave_outside_repo_refused_by_the_freeze(tmp_path, capsys, monkeypatch, crit):
    """The CLI verifies the freeze against the project repository: folders outside the repository are refused."""
    from research import __main__ as cli
    from research import data

    base = tmp_path / "waves" / "1"
    (base / "sheets").mkdir(parents=True)
    (base / "strategies").mkdir()
    (base / "sheets" / "x.yaml").write_text(yaml.safe_dump(_sheet("X", "X", "directional", "f1_lab.py", {"L": [10, 20, 40]})))
    wave.freeze_sheets(base / "sheets")
    monkeypatch.setattr(data, "load", lambda *a, **k: None)
    assert cli.main(["--journal", str(tmp_path / "e.jsonl"), "--arena-journal", str(tmp_path / "a.jsonl"),
                     "--reports", str(tmp_path / "r"), "wave", "1", "--waves", str(tmp_path / "waves")]) == 2
    assert "wave refused" in capsys.readouterr().err
    assert not (tmp_path / "e.jsonl").exists()


def test_production_paths_aligned_with_the_cli(repo):
    """The CLI and `wave` share the production folder; the layout `<waves>/<n>/{sheets,strategies}` is the one
    a frozen wave has (checked on a synthetic wave, the published repository carries no wave)."""
    from research import __main__ as cli

    assert cli.WAVES == REPO / "research" / "waves" == wave.DEFAULT_WAVES
    assert repo.sheets().relative_to(repo.root_path) == Path("waves") / "1" / "sheets"
    assert repo.strategies().relative_to(repo.root_path) == Path("waves") / "1" / "strategies"
    assert (repo.sheets() / "MANIFEST.json").is_file() and repo.strategies().is_dir()
    assert (cli.WAVES / "1" / "sheets").relative_to(REPO / "research") == repo.sheets().relative_to(repo.root_path)


def test_strategy_outside_the_frozen_directory_is_refused(tmp_path, journal, crit):
    docs = {"a.yaml": _sheet("Escape", "A", "directional", "../f1_lab.py", {"L": [10, 20, 40], "k": [2, 3, 5]})}
    repo = Repo(tmp_path / "repo").add_wave(1, docs)
    rep = _launch(repo, 1, _wave_panel(crit), journal, crit, tmp_path)
    assert "a.yaml" in rep.refused and "strategy" in rep.refused["a.yaml"] and journal.n_ids() == 0


# ==================================================================================================
# 5. V per class
# ==================================================================================================


def _trial_sr(name, family, sr, T=2373, rng=None, class_="directional", universe="main"):
    rng = rng or np.random.default_rng(abs(hash(name)) % 2**32)
    net = rng.normal(0, 0.01, T)
    net = (net - net.mean()) / net.std(ddof=1) * 0.01 + sr * 0.01
    return Trial(name, family, class_, {"k": name}, pd.Series(net), None, None, None, None, universe)


def test_v_protected_against_dummy_families_t5():
    """Replay of proof t5: one truly dispersed family + 5 dummy families of 20 variants."""
    T = 2373
    rng = np.random.default_rng(1)
    true = [float(x) for x in rng.normal(0.045, 0.045, 20)]
    v_single = dsr.class_variance({"A": true}, T)
    # dummies at different levels: the within-family variance of each is zero
    dummy = {f"F{k}": [level] * 20 for k, level in enumerate((0.0, 0.02, 0.04, 0.06, 0.08))}
    sr_per_family = {"A": true, **dummy}
    all_trials = true + [x for v in dummy.values() for x in v]
    intra = (20 * float(np.var(true, ddof=1))) / 20 / 6  # weighted mean: only A has a variance
    pooled = float(np.var(all_trials, ddof=1))
    v = dsr.class_variance(sr_per_family, T)
    assert v == pytest.approx(max(pooled, intra, 1 / (T - 1)))
    assert v > intra * 1.5  # the old formula (weighted mean alone) was diluted by the dummies
    assert v_single > 0
    # the required Sharpe follows: more overall dispersion, more required Sharpe
    assert dsr.required_sharpe(726, T, v) > dsr.required_sharpe(726, T, intra)


def test_v_uses_all_journal_trials_not_only_the_wave(tmp_path, journal, crit):
    """`journal_sr_days`: all waves, main universe, status OK, per class."""
    journal.initialize()

    def trial(eid, fam, class_, universe, status, sr):
        journal.start({"id": eid, "family": fam, "class_": class_, "sheet_sha256": "f", "code_sha256": "c",
                       "params": eid, "universe": universe})
        journal.end({"id": eid, "status": status, **({"sr_day": sr, "gates_sr_day": sr} if status == "OK" else {})})

    trial("R0001", "A", "directional", "main", "OK", "0.05")
    trial("R0002", "A", "directional", "main", "OK", "0.07")
    journal._add("wave_ended", {"number": 1})
    trial("R0003", "B", "directional", "main", "OK", "-0.02")  # next wave
    trial("R0004", "B", "directional", "arena", "OK", "9.0")  # other universe: excluded
    trial("R0005", "B", "directional", "main", "ERROR", None)  # no metric
    trial("R0006", "C", "hedged", "main", "OK", "0.01")
    trial("R0007", "B", "directional", "main", "OK", "nan")
    assert wave.journal_sr_days(journal) == {
        "directional": {"A": [0.05, 0.07], "B": [-0.02]}, "hedged": {"C": [0.01]}}
    # evaluate_candidate: V comes from the journal, not only from the trials of the current wave
    sr = wave.journal_sr_days(journal)
    T = 500
    single = _trial_sr("x", "A", 1.0, T=T)
    v_wave = evaluate.variance_of_class("directional", [single], T)
    v_journal = evaluate.variance_of_class("directional", [single], T, sr)
    assert v_journal == pytest.approx(dsr.class_variance(sr["directional"], T)) and v_journal != v_wave


# ==================================================================================================
# 6. C7: ignored parameters
# ==================================================================================================

SOURCE_IGNORE = '''
import numpy as np
class Strategy:
    def __init__(self, n_pairs, **params):      # the parameters are accepted... and ignored
        self.n = n_pairs
    def step(self, day):
        return np.full(self.n, 1.0 / self.n), np.zeros(self.n)
'''


def test_c7_empty_if_parameters_are_ignored_t5_c7(tmp_path, journal, crit):
    panel = synthetic(900, 6, 9, late_quotes=False, with_1h=False, day_start=1_546_300_800)
    code = tmp_path / "decor.py"
    code.write_text(SOURCE_IGNORE)
    grid = {"L": [10, 20, 40], "s": [0.1, 0.2, 0.4]}
    trials = []
    for L, s in itertools.product(grid["L"], grid["s"]):
        r = run_trial(SHEET, code, {"L": L, "s": s}, panel, journal, crit, causality=False, test=True)
        assert r.code == "OK", r.detail
        trials.append(to_trial(r, family="F", class_="directional", params={"L": L, "s": s}))
    cand = next(e for e in trials if e.params == {"L": 20, "s": 0.2})
    (ok, part, _), detail = evaluate.gate_c7(cand, trials, grid, crit.gates.C7_neighborhood, crit.trials)
    assert not ok and part is None and len(detail["neighbors_identical"]) == 4 and not detail["neighbors"]
    assert "distinct" in detail["reason"]


def _trial_series(name, params, seed, rotation=0.01, n=500, sharpe=1.0):
    z = np.random.default_rng(seed).normal(size=n)
    z = (z - z.mean()) / z.std(ddof=1)
    idx = pd.date_range("2020-01-01", periods=n)
    net = pd.Series(0.01 * (z + sharpe / np.sqrt(365)), index=idx)
    rot = pd.Series(rotation, index=idx)
    return Trial(name, "F", "directional", params, net, net, net, rot, rot * 0)


def test_c7_neighbor_distinct_only_if_series_or_rotation_differs(crit):
    grid = {"a": [1.0, 2.0, 4.0], "b": [1.0, 2.0, 4.0]}
    cfg = crit.gates.C7_neighborhood
    cand = _trial_series("c", {"a": 2.0, "b": 2.0}, 0, sharpe=1.0)

    def neighborhood(distinct: set):
        all_trials = [cand]
        for a, b in itertools.product(grid["a"], grid["b"]):
            if (a, b) == (2.0, 2.0):
                continue
            if (a, b) in distinct:
                all_trials.append(_trial_series(f"{a}{b}", {"a": a, "b": b}, hash((a, b)) % 1000 + 1, sharpe=1.0))
            else:
                all_trials.append(Trial(f"{a}{b}", "F", "directional", {"a": a, "b": b}, cand.net.copy(), cand.net,
                                  cand.net, cand.rotation.copy(), cand.costs))
        return all_trials

    neighbors4 = {(1.0, 2.0), (4.0, 2.0), (2.0, 1.0), (2.0, 4.0)}
    (ok, part, _), detail = evaluate.gate_c7(cand, neighborhood(neighbors4), grid, cfg, crit.trials)
    assert ok and part == 1.0 and not detail["neighbors_identical"]
    # a single active axis (2 distinct neighbors, 2 identical): still valid, the share is computed on the distinct ones
    (ok, part, _), detail = evaluate.gate_c7(cand, neighborhood({(1.0, 2.0), (4.0, 2.0)}), grid, cfg, crit.trials)
    assert ok and len(detail["neighbors"]) == 2 and len(detail["neighbors_identical"]) == 2
    # a single distinct neighbor: failure
    (ok, _, _), detail = evaluate.gate_c7(cand, neighborhood({(1.0, 2.0)}), grid, cfg, crit.trials)
    assert not ok and "distinct" in detail["reason"]
    # same series but different rotation: distinct neighbor
    all_trials = neighborhood(set())
    all_trials = [t if t.id == "c" else Trial(**{**t.__dict__, "rotation": t.rotation + 1e-6}) for t in all_trials]
    (ok, part, _), detail = evaluate.gate_c7(cand, all_trials, grid, cfg, crit.trials)
    assert ok and not detail["neighbors_identical"]


# ==================================================================================================
# 7. C16 in the wave: not evaluable, hedged class concerned
# ==================================================================================================


def _dummy_data(perp: dict, funding: dict):
    return SimpleNamespace(control_perp_1h=perp, control_funding=funding)


def test_missing_data_according_to_the_sheet():
    d = _dummy_data({"A": pd.DataFrame(), "B": None}, {"A": pd.DataFrame(), "B": pd.DataFrame(), "C": None})

    def sheet(class_, signals=False):
        return wave.Sheet("f", "0" * 64, "F", "n", "m", class_, "s.py", {}, {}, signals)

    assert wave._is_data_missing(d, "B", sheet("hedged")) and not wave._is_data_missing(d, "A", sheet("hedged"))
    assert wave._is_data_missing(d, "C", sheet("directional", True))
    assert not wave._is_data_missing(d, "B", sheet("directional", True))
    assert not wave._is_data_missing(d, "C", sheet("directional"))  # spot only: never "not evaluable"


def test_c16_hedged_without_perp_in_the_panel_is_not_evaluable(tmp_path, journal, crit):
    panel = dataclasses.replace(synthetic(300, 6, 3, with_1h=False, with_perp=False, late_quotes=False,
                                          day_start=START_2019_09), symbols=tuple(crit.universe[:6]))
    f = wave.Sheet("f.yaml", "0" * 64, "C1", "n", "m", "hedged", "simple_hedged.py", {}, {})
    ctx = wave._Ctx(1, panel, journal, crit, Path(__file__).parent / "strategies", tmp_path / "s",
                     wave.WaveReport(1), causality=False, test=True)
    arena, control, n_extra = wave._c15_c16(f, {"size": 0.09, "k": 3}, ctx, list(panel.symbols)[:3])
    assert arena is None and n_extra == 0 and journal.n_ids() == 0  # C15 not applicable, no trial launched
    assert control == dict.fromkeys(list(panel.symbols)[:3], evaluate.NOT_EVALUABLE)
    assert not evaluate.gate_c16(control, crit.gates.C16_outside_universe, 20)[0]


# ==================================================================================================
# 8. C5 / C13: flat years and halves
# ==================================================================================================


def _annual_series(flat_years=(), absent=(), noise_per_year=0.01, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", "2026-06-30")
    x = rng.normal(0.0015, noise_per_year, len(idx))
    s = pd.Series(x, index=idx)
    for a in flat_years:
        s[s.index.year == a] = 0.0
    return s[~s.index.year.isin(list(absent))]


def test_c5_flat_year_is_not_positive_nor_below_minus_one():
    cfg = yaml.safe_load(CRITERIA_PATH.read_text())["gates"]["C5_years"]
    ok, sh, _ = evaluate.gate_c5(_annual_series(flat_years=(2022,)), cfg)
    assert ok and sh[2022] == 0.0  # 5 positive years: the flat year does not count among them but does not fail
    # if the flat year brings the count below 4 positive years, C5 fails (it is not positive)
    ok, _, _ = evaluate.gate_c5(_annual_series(flat_years=(2021, 2022, 2023)), cfg)
    assert not ok
    # missing year: always a failure
    ok, sh, _ = evaluate.gate_c5(_annual_series(absent=(2022,)), cfg)
    assert not ok and np.isnan(sh[2022])
    # a year below -1 always fails
    s = _annual_series()
    s[s.index.year == 2022] = np.random.default_rng(5).normal(-0.004, 0.01, int((s.index.year == 2022).sum()))
    assert stats.sharpe(s[s.index.year == 2022]) < -1 and not evaluate.gate_c5(s, cfg)[0]
    # without the option, the Sharpe of a flat year stays NaN (stats behavior unchanged)
    assert np.isnan(stats.sharpe_per_year(_annual_series(flat_years=(2022,)), [2022])[2022])


def test_c13_flat_half_scores_zero_and_fails():
    cfg = yaml.safe_load(CRITERIA_PATH.read_text())["gates"]["C13_halves"]
    rng = np.random.default_rng(2)
    n = 400
    idx = pd.date_range("2020-01-01", periods=n)
    x = rng.normal(0.002, 0.01, n)
    x[: n // 2] = 0.0
    ok, (a, b), _ = evaluate.gate_c13(pd.Series(x, index=idx), cfg)
    assert a == 0.0 and b > 0 and not ok  # > 0 required in each half
    y = rng.normal(0.002, 0.01, n)
    y[n // 2:] = 0.0
    assert evaluate.gate_c13(pd.Series(y, index=idx), cfg)[1][1] == 0.0
    assert stats.sharpe_halves(np.zeros(10)) == (0.0, 0.0)


# ==================================================================================================
# 9. Selection: tolerance and negative correlations
# ==================================================================================================


def _pair(rho, n=500):
    rng = np.random.default_rng(4)
    z1, z2 = rng.normal(size=n), rng.normal(size=n)
    z1 = (z1 - z1.mean()) / z1.std()
    z2 = z2 - z2.mean()
    z2 -= (z2 @ z1) / (z1 @ z1) * z1
    z2 /= z2.std()
    idx = pd.date_range("2020-01-01", periods=n)
    return pd.Series(z1, index=idx), pd.Series(rho * z1 + np.sqrt(1 - rho**2) * z2, index=idx)


def test_selection_comparison_with_tolerance():
    a, b = _pair(0.7)
    rho = float(a.corr(b))
    cands = [selection.Candidate("a", 0.99, a), selection.Candidate("b", 0.96, b)]

    def crit_max(cmax):
        return {"selection": {"max_basket_excess_correlation": cmax, "max_candidates": 3}}

    # rho exceeds the threshold by 5e-13 (floating-point noise): within the 1e-12 tolerance, kept
    assert selection.select_candidates(cands, crit_max(rho - 5e-13)).retained == ("a", "b")
    # rho exceeds the threshold by 5e-12: beyond the tolerance, discarded
    assert selection.select_candidates(cands, crit_max(rho - 5e-12)).retained == ("a",)


def test_selection_keeps_negative_correlations():
    a, _ = _pair(0.0)
    s = selection.select_candidates([selection.Candidate("a", 0.99, a), selection.Candidate("b", 0.96, -a)],
                               {"selection": {"max_basket_excess_correlation": 0.7, "max_candidates": 3}})
    assert s.retained == ("a", "b") and s.correlations[("a", "b")] == pytest.approx(-1.0)


# ==================================================================================================
# 10. Outputs meant for agents: binary statuses only
# ==================================================================================================


def test_cli_wave_shows_only_binary_statuses(tmp_path, journal, repo, crit, capsys, monkeypatch):
    from research import __main__ as cli
    from research import data
    from research.engine import journal as mj

    panel = _wave_panel(crit)
    monkeypatch.setattr(data, "load", lambda *a, **k: panel)
    monkeypatch.setattr(mj, "ResearchJournal", lambda path: journal)
    orig = wave.run_wave
    monkeypatch.setattr(wave, "run_wave", lambda *a, **k: orig(*a, **{**k, "repo": repo.root_path,
                                                                            "causality": False}))
    code = cli.main(["--journal", str(journal.path), "--arena-journal", str(tmp_path / "a.jsonl"),
                     "--reports", str(tmp_path / "reports"), "wave", "1", "--waves", str(repo.root_path / "waves")])
    out = capsys.readouterr().out
    assert code == 0
    assert re.search(r"^- Taker pressure: (discarded|not_discarded) \(", out, re.MULTILINE)
    assert not re.search(r"\d+\.\d+|R\d{4}|[Ss]harpe|DSR|trials", out), out
    statuses = json.loads((tmp_path / "reports" / "wave-1-statuses.json").read_text())
    assert all(set(s) == {"name", "mechanism", "verdict"} for s in statuses)
    # the figures are in the orchestrator's report
    md = (tmp_path / "reports" / "wave-1.md").read_text()
    assert "Best DSR" in md and "goes to no agent" in md
    assert not (tmp_path / "reports" / "wave-1.json").exists()
