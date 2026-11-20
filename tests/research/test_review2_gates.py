# ruff: noqa: F811  (fixtures imported from test_wave_fixes)
"""Review 2 non-regression: V of the hedged class, C9 gate closed without key, caps by family name.

Journals, git repositories and reports in tmp_path; synthetic data only.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest
import yaml

from research import wave
from research.config import Section, load_criteria
from research.gates import dsr
from research.gates.adapter import to_causality_report
from tests.research.test_wave_fixes import (  # noqa: F401  (fixtures)
    _docs_f1,
    _launch,
    repo,
    journal,
    dummy_lab,
)
from tests.research.test_integration import _wave_panel


@pytest.fixture(scope="module")
def crit():
    return load_criteria()


def _trial(journal, eid, fam, class_, **metrics):
    journal.start({"id": eid, "family": fam, "class_": class_, "sheet_sha256": "f", "code_sha256": "c",
                   "params": eid, "universe": "main"})
    journal.end({"id": eid, "status": "OK", **metrics})


# --- 1. V of the hedged class on the C1 series ---------------------------------------------------------


def test_v_of_hedged_comes_from_gates_daily_sr(journal):
    journal.initialize()
    # total capital: very dispersed sr_day; tied-up capital (C1 series): little dispersed
    for i, (total, tied_up) in enumerate([("0.01", "0.050"), ("0.09", "0.052"), ("-0.07", "0.048")]):
        _trial(journal, f"R{i}", "C", "hedged", sr_day=total, gates_sr_day=tied_up)
    _trial(journal, "R9", "D", "directional", sr_day="0.03", gates_sr_day="0.99")
    sr = wave.journal_sr_days(journal)
    assert sr["hedged"]["C"] == [0.05, 0.052, 0.048]
    assert sr["directional"]["D"] == [0.03]  # directional: total capital, unchanged
    T = 500
    v = dsr.class_variance(sr["hedged"], T)
    assert v == pytest.approx(max(float(np.var([0.05, 0.052, 0.048], ddof=1)), 1 / (T - 1)))
    assert v < float(np.var([0.01, 0.09, -0.07], ddof=1))


# --- 2. C9: gate closed if the real_ok key is absent --------------------------------------------


def test_missing_real_ok_closes_gate_c9(crit):
    caus = {"cutoffs_gap": 0.0, "permutation_gap": 0.0, "scale_gap": 0.0, "n_cutoffs": 30,
            "non_full_hour_cutoffs": 10, "deterministic": True, "evaluable": True}
    assert to_causality_report(caus, crit).invariances_ok is False
    assert to_causality_report({**caus, "real_ok": True}, crit).invariances_ok is True
    assert to_causality_report({**caus, "real_ok": False}, crit).invariances_ok is False


# --- 3. caps by family name ----------------------------------------------------------------


def test_two_sheets_of_the_same_family_share_the_cap(tmp_path, journal, repo, crit):
    trials_cfg = crit.trials.to_dict()
    trials_cfg.update(max_families_per_wave=1, max_variants_per_family_wave_1=10)
    c = dataclasses.replace(crit, trials=Section(trials_cfg))
    doc = yaml.safe_load((repo.sheets() / "f1.yaml").read_text())
    (repo.sheets() / "f1b.yaml").write_text(yaml.safe_dump({**doc, "name": "Second sheet, same family"}))
    wave.freeze_sheets(repo.sheets())
    repo.label(1)
    panel = _wave_panel(crit)
    # before the fix: 2 sheets counted as 2 families -> WaveError; 9 + 9 variants passed
    rep = _launch(repo, 1, panel, journal, c, tmp_path)
    assert "f1b.yaml" in rep.refused and "F1" in rep.refused["f1b.yaml"]
    assert "f1.yaml" not in rep.refused
    assert rep.n_wave_trials == 9


# --- 4. review 2 bis: family name, k draw per family ------------------------------------------


@pytest.mark.parametrize("name", ["momentum ", "Momentum ", "mom_entum", "mom--x", ""])
def test_family_outside_pattern_is_refused(tmp_path, repo, name):
    doc = yaml.safe_load((repo.sheets() / "f1.yaml").read_text())
    (repo.sheets() / "f1.yaml").write_text(yaml.safe_dump({**doc, "family": name}))
    wave.freeze_sheets(repo.sheets())
    repo.label(1)
    with pytest.raises(wave.WaveError, match="family"):
        wave.read_sheets(repo.sheets(), repo.strategies(), 1, repo=repo.root_path)


def test_families_differing_only_by_case_are_refused(tmp_path, journal, repo, crit):
    doc = yaml.safe_load((repo.sheets() / "f1.yaml").read_text())
    (repo.sheets() / "f1b.yaml").write_text(yaml.safe_dump({**doc, "family": doc["family"].lower()}))
    wave.freeze_sheets(repo.sheets())
    repo.label(1)
    with pytest.raises(wave.WaveError, match="case"):
        _launch(repo, 1, _wave_panel(crit), journal, crit, tmp_path)


def test_one_k_draw_per_family_written_before_trials_and_reread(tmp_path, journal, repo, crit, monkeypatch):
    from research.engine import sandbox
    seen = []
    real = sandbox.draw_days_withdrawn

    def spy(panel, criteria, draw=None):
        seen.append(draw)
        return real(panel, criteria, draw=draw)

    monkeypatch.setattr(sandbox, "draw_days_withdrawn", spy)
    _launch(repo, 1, _wave_panel(crit), journal, crit, tmp_path)
    (started,) = journal.events("wave_started")
    draws = started["payload"]["draws_k"]
    assert set(draws) == {"F1"} and seen and all(t == draws["F1"] for t in seen)
    ks = {e["end"]["days_withdrawn"] for e in journal.trials().values() if e["end"].get("status") == "OK"}
    assert len(ks) == 1  # all the variants of the family: same k
