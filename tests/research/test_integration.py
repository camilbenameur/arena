"""Research integration tests: engine <-> gates, acceptance on real data, anchoring, wave.

Trials go into TEMPORARY journals (tmp_path), never into research/trials.jsonl or var/journal/.
Tests marked `real_data` read var/research/data (cutoff 2026-06-30) and are skipped without it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from arena.config import load_config
from arena.journal import Journal
from arena.ledger import replay
from arena.risk.policy import load_policy
from arena.site import build
from research import wave
from research.config import REPO, load_criteria
from research.engine import sandbox
from research.engine.trial import TrialSheet, compute_metrics, run_trial
from research.engine.journal import ResearchJournal
from research.engine.panel import panel_from_data, synthetic
from research.engine.portfolio import EngineSeries
from research.gates import evaluate, selection, stats
from research.gates.adapter import to_trial, to_causality_report

STRAT = Path(__file__).parent / "strategies"
START_2019_09 = int(pd.Timestamp("2019-09-01", tz="UTC").timestamp())
DATA_ROOT = REPO / "var" / "research" / "data"
SHEET = TrialSheet("F1", "directional", "a" * 64)
E0065_SHARPE = 1.2449864426425823

real_data = pytest.mark.real_data
without_data = pytest.mark.skipif(
    not (DATA_ROOT / "MANIFEST.json").is_file(), reason="var/research/data not built")


@pytest.fixture(scope="module")
def crit():
    return load_criteria()


@pytest.fixture(scope="module", autouse=True)
def _canary():
    sandbox.canary()


@pytest.fixture
def dummy_lab(tmp_path):
    d = tmp_path / "lab"
    d.mkdir()
    lines = [json.dumps({"id": f"E{i:04d}", "prev_hash": "x"}) for i in range(1, 8)]
    (d / "trials.jsonl").write_text("\n".join(lines) + "\n")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    for cmd in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "x"], ["tag", "final-freeze"]):
        subprocess.run(["git", "-C", str(d), *cmd], check=True, env=env, capture_output=True)
    return d


@pytest.fixture
def journal(tmp_path, dummy_lab):
    return ResearchJournal(tmp_path / "trials.jsonl", lab_repo=dummy_lab, clock=lambda: 1_700_000_000)


def sharpe_np(r):
    return float(r.mean() / r.std(ddof=1) * math.sqrt(365))


# --------------------------------------------------------------------------------------------------
# Gap 2: the engine and gates/stats.py give the same metrics
# --------------------------------------------------------------------------------------------------


def test_engine_metrics_equal_gates_on_random_series(crit):
    rng = np.random.default_rng(3)
    for seed in range(5):
        r = rng.standard_t(4, 900) * 0.01 + 0.0006 * (seed + 1)
        n = len(r)
        days = (np.int64(1_577_836_800) + 86400 * np.arange(n)).astype(np.int64)
        z = np.zeros(n)
        track = EngineSeries(
            class_="directional", days=days, net_returns=r, stressed_net_returns=r * 0.9,
            gross_returns=r + 0.001, rotation=np.abs(rng.normal(0, 0.1, n)), rotation_spot=z, rotation_perp=z,
            costs=np.full(n, 0.001), exposure=np.ones(n), immobilized_net_returns=r, funding=z,
            eligible=np.ones(n, bool), eval_mask=np.ones(n, bool), spot_weight=np.zeros((n, 1)),
            perp_weight=np.zeros((n, 1)), symbols=("X",))
        m = compute_metrics(track)
        s = pd.Series(r, index=pd.to_datetime(days, unit="s"))
        sk, ku = stats.moments(s)
        assert m["sharpe_net"] == pytest.approx(stats.sharpe(s), rel=1e-12)
        assert m["sr_day"] == pytest.approx(stats.sr_day(s), rel=1e-12)
        assert m["drawdown"] == pytest.approx(stats.drawdown(s), rel=1e-12)
        assert m["t_nw20"] == pytest.approx(stats.t_newey_west(s, 20), rel=1e-12)
        assert m["net_annualized_return"] == pytest.approx(stats.annualized_return(s), rel=1e-12)
        assert m["annual_turnover"] == pytest.approx(stats.annual_turnover(track.rotation), rel=1e-12)
        assert m["skew"] == pytest.approx(sk, rel=1e-9) and m["kurt"] == pytest.approx(ku, rel=1e-9)
        assert m["sharpe_net_costs_x2"] == pytest.approx(stats.sharpe(s * 0.9), rel=1e-12)


def test_engine_metrics_equal_gates_after_adaptation(tmp_path, journal, crit):
    panel = synthetic(700, 15, 21, with_1h=False, day_start=START_2019_09)
    r = run_trial(SHEET, STRAT / "f1_lab.py", {}, panel, journal, crit, causality=False, test=True)
    assert r.code == "OK", r.detail
    e = to_trial(r, family="F1", class_="directional", params={})
    assert len(e.net) == r.metrics["T"]
    assert r.metrics["sharpe_net"] == pytest.approx(stats.sharpe(e.net), rel=1e-12)
    assert r.metrics["drawdown"] == pytest.approx(stats.drawdown(e.net), rel=1e-12)
    assert r.metrics["t_nw20"] == pytest.approx(stats.t_newey_west(e.net), rel=1e-12)
    assert r.metrics["sharpe_net_costs_x2"] == pytest.approx(stats.sharpe(e.net_stress), rel=1e-12)
    assert r.metrics["annualized_total_cost"] == pytest.approx(float(e.costs.sum() / (len(e.costs) / 365)))


def test_causality_adapter_gives_a_valid_c9_report(tmp_path, journal, crit):
    panel = synthetic(420, 15, 4, with_1h=True, day_start=START_2019_09)
    r = run_trial(SHEET, STRAT / "f1_lab.py", {}, panel, journal, crit, test=True)
    assert r.code == "OK", r.detail
    report = to_causality_report(r.causality, crit)
    assert isinstance(report, evaluate.CausalityReport)
    assert report.n_random_cuts == 20 and report.n_fixed == 3 and report.not_full_hour_share >= 0.4
    ok, value, _ = evaluate.gate_c9(report, crit.gates.C9_causality)
    assert ok and value <= 1e-9
    assert to_causality_report(None, crit) is None and to_causality_report({"ok": False, "error": "x"}, crit) is None


# --------------------------------------------------------------------------------------------------
# Acceptance: 1/15 basket (independent), synthetic then real
# --------------------------------------------------------------------------------------------------


def _independent_basket(close: np.ndarray, cost: float = 0.0060):
    """Holdings in units, value, drift, rotation: without anything from the engine."""
    n = close.shape[1]
    q = (1 / n) / close[0]
    v = 1.0
    prev_rot = 1.0
    net, rot = np.zeros(len(close)), np.zeros(len(close))
    for t in range(1, len(close)):
        v_new = float(q @ close[t])
        net[t] = (v_new / v - 1.0) - cost * prev_rot
        rot[t] = prev_rot
        w_last = q * close[t] / v_new
        prev_rot = float(np.abs(1 / n - w_last).sum())
        q = v_new / n / close[t]
        v = v_new
    return net, rot


def _verify_basket(r, panel, crit):
    net, rot = _independent_basket(panel.spot_1d[:, :, 3], crit.spot_cost_bp / 1e4)
    s = r.track
    assert np.allclose(s.net_returns, net, atol=1e-12, rtol=0)
    assert np.allclose(s.rotation, rot, atol=1e-12, rtol=0)
    m = s.eval_mask
    assert m.sum() > 400
    assert float(r.metrics["sharpe_net"]) == pytest.approx(sharpe_np(net[m]), abs=1e-12)
    e = to_trial(r, family="C", class_="directional", params={})
    assert stats.sharpe(e.net) == pytest.approx(sharpe_np(net[m]), abs=1e-12)
    assert stats.annual_turnover(e.rotation) == pytest.approx(rot[m].sum() / (m.sum() / 365), rel=1e-12)


def test_acceptance_basket_one_fifteenth_synthetic(tmp_path, journal, crit):
    panel = synthetic(650, 15, 11, with_1h=False, late_quotes=False, day_start=START_2019_09)
    r = run_trial(SHEET, STRAT / "constant.py", {}, panel, journal, crit, causality=False, test=True)
    assert r.code == "OK", r.detail
    _verify_basket(r, panel, crit)


def _since(panel, i0):
    sl = slice(i0, None)
    return dataclasses.replace(
        panel, days=panel.days[sl], spot_1d=panel.spot_1d[sl], spot_1h=None, perp_1h=None,
        eligibles=panel.eligibles[sl], eligibles_perp=None, funding_idx=panel.funding_idx[sl],
        funding_rate=panel.funding_rate[sl], funding_ts=panel.funding_ts[sl])


@pytest.fixture(scope="module")
def loaded_data():
    from research.data import load

    return load(DATA_ROOT)


@pytest.fixture(scope="module")
def real_panel(loaded_data):
    return panel_from_data(loaded_data, "main", with_1h=False, with_perp=False)


@real_data
@without_data
def test_acceptance_basket_one_fifteenth_real(tmp_path, journal, crit, real_panel):
    panel = real_panel
    i0 = int(np.argmax(panel.eligibles.all(axis=1)))  # first date where all 15 pairs are listed
    assert panel.eligibles[i0:].all(), "eligibility gap after the last listing"
    trimmed = _since(panel, i0)
    # days_withdrawn=0: exact reproduction of the basket recomputed from the first date with 15 pairs
    r = run_trial(SHEET, STRAT / "constant.py", {}, trimmed, journal, crit, causality=False, test=True,
                       days_withdrawn=0)
    assert r.code == "OK", r.detail
    _verify_basket(r, trimmed, crit)


@real_data
@without_data
def test_acceptance_e0065_real(tmp_path, journal, crit, real_panel):
    """Lab E0065: F1 L=20 k=3 H=10, 15 pairs, rotation on targets, 15 bp, window 2020-01-01 -> 2026-06-30."""
    r = run_trial(SHEET, STRAT / "f1_lab.py", {"L": 20, "k": 3, "H": 10}, real_panel, journal, crit,
                       convention_rotation="target", spot_cost_bp=15, causality=False, test=True,
                       days_withdrawn=0)  # the lab starts on the 1st date: the H=10 phase depends on it
    assert r.code == "OK", r.detail
    assert float(r.metrics["sharpe_net"]) == pytest.approx(E0065_SHARPE, abs=1e-6)
    assert journal.trials()[r.id]["end"]["status"] == "OK"
    assert not (REPO / "research" / "trials.jsonl").exists() or journal.path != REPO / "research" / "trials.jsonl"


# --------------------------------------------------------------------------------------------------
# Gap 3: p(not refuted | H0) by simulation
# --------------------------------------------------------------------------------------------------


def test_p_does_not_refute_simulated_h0_and_constant():
    p = selection.simulate_p_not_refuted()
    assert p == pytest.approx(selection.P_NOT_REFUTED_H0_DEFAULT, abs=1e-12)  # fixed seed: reproducible
    other = selection.simulate_p_not_refuted(seed=7, n_sim=200_000)
    assert abs(other - p) < 0.006
    # return rule alone: P(R >= -0.5 sigma) around 0.9 for a true Sharpe of zero
    single = selection.simulate_p_not_refuted(with_drawdown=False)
    assert 0.89 < single < 0.92 and p <= single + 1e-12
    # power: under a true Sharpe of 1 the rule refutes ~5%; no zero drift here, so p(H0) > 0.85
    assert p > 0.85
    assert selection.prob_at_least_one_not_refuted(3) == pytest.approx(1 - (1 - p) ** 3, abs=1e-12)


# --------------------------------------------------------------------------------------------------
# Step 6: research_anchor breaks neither replay nor the site
# --------------------------------------------------------------------------------------------------


_JOURNAL_LINES = ("events, last seq", "chain intact", "Chain head")


def _hash_directory(d: Path) -> dict[str, str]:
    """sha256 of every site file, EXCEPT the journal metadata (number of events, chain head):
    one more event necessarily changes those lines and nothing else must change."""
    out = {}
    for p in sorted(d.rglob("*")):
        if not p.is_file():
            continue
        raw_bytes = p.read_bytes()
        if p.suffix == ".html":
            lines = [x for x in raw_bytes.decode().splitlines() if not any(m in x for m in _JOURNAL_LINES)]
            raw_bytes = "\n".join(lines).encode()
        elif p.suffix == ".json":
            doc = json.loads(raw_bytes)
            if isinstance(doc, dict):
                doc.pop("journal", None)
            raw_bytes = json.dumps(doc, sort_keys=True).encode()
        out[str(p.relative_to(d))] = hashlib.sha256(raw_bytes).hexdigest()
    return out


def test_research_anchor_in_temporary_arena_journal(tmp_path, journal, crit):
    from tests.test_site import NOW, ROOT, synthetic_journal

    arena = synthetic_journal(tmp_path / "arena" / "events.jsonl")
    cfg = load_config(ROOT / "config" / "arena.toml")
    pol = load_policy(ROOT / "config" / "policy.toml")
    states_before = replay(arena.iter_events())
    build(arena.path, tmp_path / "site_before", config=cfg, policy=pol, now_ts=NOW)

    panel = synthetic(300, 6, 5, with_1h=False, late_quotes=False, day_start=START_2019_09)
    j = ResearchJournal(journal.path, lab_repo=journal.lab_repo, clock=lambda: NOW)
    r = run_trial(SHEET, STRAT / "constant.py", {}, panel, j, crit, causality=False,
                       arena_journal=arena.path)
    assert r.code == "OK"
    anchors = [e for e in Journal(arena.path).iter_events() if e["type"] == "research_anchor"]
    # the engine anchors at least after the `end` (and, since fix A, also after the `start`); the last
    # anchor is that of the current head
    assert len(anchors) >= 1 and anchors[-1]["payload"]["head"] == j.head()
    assert anchors[-1]["payload"]["n_lines"] == j.n_lines()
    assert Journal(arena.path).verify().ok

    states_after = replay(Journal(arena.path).iter_events())
    assert states_after == states_before
    build(arena.path, tmp_path / "site_after", config=cfg, policy=pol, now_ts=NOW)
    # only the journal metadata changes (one more event, another head): everything else is identical
    assert _hash_directory(tmp_path / "site_after") == _hash_directory(tmp_path / "site_before")
    assert (tmp_path / "site_before" / "method.html").read_text() != (tmp_path / "site_after" / "method.html").read_text()
    # and the anchor protects: a truncated research journal is refused
    lines = j.path.read_text().splitlines(keepends=True)
    j.path.write_text("".join(lines[:-1]))
    with pytest.raises(Exception, match="anchor|lines"):
        ResearchJournal(j.path, lab_repo=j.lab_repo).verify_anchor(arena.path)


# --------------------------------------------------------------------------------------------------
# Wave end to end (synthetic data, 2 dummy sheets, temporary folders)
# --------------------------------------------------------------------------------------------------


def _sheet(name, family, class_, strategy, grid, **others):
    return {"family": family, "name": name, "mechanism": f"mechanism of {name}", "class_": class_,
            "strategy": strategy, "grid": grid, "who_loses": "x", "prediction_falsifiable": "x", **others}


ENV_GIT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"}


class Repo:
    """Fake git repository (in tmp): `waves/<n>/{sheets,strategies}` committed and tagged `research-wave-<n>-sheets`."""

    def __init__(self, root_path: Path):
        self.root_path = root_path
        root_path.mkdir(parents=True, exist_ok=True)
        self.env = {**ENV_GIT, "HOME": str(root_path)}
        self._git("init", "-q")

    def _git(self, *args):
        subprocess.run(["git", "-C", str(self.root_path), *args], check=True, env=self.env, capture_output=True)

    def sheets(self, n=1) -> Path:
        return self.root_path / "waves" / str(n) / "sheets"

    def strategies(self, n=1) -> Path:
        return self.root_path / "waves" / str(n) / "strategies"

    def decision(self, n) -> Path:
        return self.root_path / "waves" / str(n) / "DECISION-OWNER.md"

    def add_wave(self, n: int, docs: dict, strategies=("f1_lab.py", "simple_hedged.py"), label=True):
        self.sheets(n).mkdir(parents=True, exist_ok=True)
        self.strategies(n).mkdir(parents=True, exist_ok=True)
        for name, d in docs.items():
            (self.sheets(n) / name).write_text(yaml.safe_dump(d, allow_unicode=True))
        for st in strategies:
            (self.strategies(n) / st).write_bytes((STRAT / st).read_bytes())
        wave.freeze_sheets(self.sheets(n))
        if label:
            self.label(n)
        return self

    def label(self, n: int):
        self._git("add", ".")
        self._git("commit", "-q", "-m", f"wave {n}", "--allow-empty")
        self._git("tag", "-f", f"research-wave-{n}-sheets")


def _wave_docs(prefix=""):
    return {
        "f1.yaml": _sheet("Taker pressure", f"{prefix}F1", "directional", "f1_lab.py",
                          {"L": [10, 20, 40], "k": [2, 3, 5]}, fixed_params={"H": 10}),
        "c1.yaml": _sheet("Simple hedge", f"{prefix}C1", "hedged", "simple_hedged.py",
                          {"size": [0.06, 0.09, 0.13], "k": [2, 3, 4]}),
    }


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path / "repo").add_wave(1, _wave_docs())


def _launch(repo, n, panel, journal, crit, tmp_path, **kw):
    return wave.run_wave(
        n, repo.sheets(n), repo.strategies(n), panel, journal, crit, reports_dir=tmp_path / "reports",
        repo=repo.root_path, causality=kw.pop("causality", False),
        test=kw.pop("test", kw.get("arena_journal") is None), **kw)


def _wave_panel(crit):
    panel = synthetic(820, 15, 8, with_1h=True, with_perp=True, day_start=START_2019_09 - 400 * 86400)
    return dataclasses.replace(panel, symbols=tuple(crit.universe))


def test_wave_end_to_end(tmp_path, journal, crit, repo):
    panel = _wave_panel(crit)
    rep = _launch(repo, 1, panel, journal, crit, tmp_path, arena_journal=tmp_path / "arena.jsonl")
    assert rep.n_wave_trials == 18 and not rep.refused and not rep.cap_reached
    assert journal.n_ids() == 18 and len(rep.lines) == 18
    assert all(ln.code == "OK" for ln in rep.lines), [ln.code for ln in rep.lines]
    assert all(ln.verdict is not None for ln in rep.lines)
    # without a causality test (causality=False), C9 fails everywhere: no candidate, and the report says so
    assert all("C9" in ln.verdict.failures() for ln in rep.lines) and rep.candidates == []
    assert rep.stop is (rep.best_dsr < 0.5)
    md = rep.report_path.read_text()
    assert md.count("| R0") == 18 and "Stop rule triggered: " in md and "C9: FAIL" in md
    statuses = json.loads(rep.statuses_path.read_text())
    assert {s["name"] for s in statuses} == {"Taker pressure", "Simple hedge"}
    assert all(set(s) == {"name", "mechanism", "verdict"} and s["verdict"] == "discarded" for s in statuses)
    assert not any(ch.isdigit() for s in statuses for ch in s["verdict"])
    # no editable JSON file carries the stop rule
    assert not (tmp_path / "reports" / "wave-1.json").exists()
    # every trial is chained and anchored; the wave markers are in the journal
    assert journal.verify_anchor(tmp_path / "arena.jsonl") is None
    assert [e["payload"]["number"] for e in journal.events("wave_started")] == [1]
    assert [e["payload"]["number"] for e in journal.events("wave_ended")] == [1]
    assert wave.stop_after(journal, 1, crit) is rep.stop
    # wave 2 is another wave, other families: it requires the owner's decision if the stop applies
    repo.add_wave(2, _wave_docs("B"))
    if rep.stop:
        with pytest.raises(wave.WaveError, match="stop rule"):
            _launch(repo, 2, panel, journal, crit, tmp_path)
        repo.decision(2).write_text("   \n")
        with pytest.raises(wave.WaveError, match="stop rule"):
            _launch(repo, 2, panel, journal, crit, tmp_path)
        repo.decision(2).write_text("wave 2 authorized")
        repo.label(2)
    assert journal.n_ids() == 18
    rep2 = _launch(repo, 2, panel, journal, crit, tmp_path)
    assert rep2.number == 2 and journal.n_ids() == 36
    if rep.stop:
        dec = journal.events("decision_owner")
        assert len(dec) == 1 and dec[0]["payload"] == {
            "number": 2, "file": "DECISION-OWNER.md",
            "sha256": hashlib.sha256(repo.decision(2).read_bytes()).hexdigest()}


def test_wave_hedged_c15_not_applicable_c16_remains():
    v = evaluate.Verdict(gates={"C15": (False, None, 1), "C16": (False, None, 1), "C1": (True, 1, 1)},
                        consistency={"C2": (True, 1, 1)}, passed=False)
    w = wave._without_c15(v)
    assert w.gates["C15"][1].startswith("not applicable") and w.gates["C15"][0]
    assert w.gates["C16"] == (False, None, 1) and not w.passed  # C16 also applies to hedged
    v2 = dataclasses.replace(v, gates={**v.gates, "C16": (True, 1, 1)})
    assert wave._without_c15(v2).passed
    v3 = dataclasses.replace(v2, gates={**v2.gates, "C1": (False, 0, 1)})
    assert not wave._without_c15(v3).passed


def test_wave_refuses_modified_or_unfrozen_sheet(tmp_path, journal, crit, repo):
    panel = _wave_panel(crit)
    f1 = repo.sheets() / "f1.yaml"
    f1.write_text(f1.read_text() + "\n# tweak\n")
    with pytest.raises(wave.WaveError, match="modified"):
        _launch(repo, 1, panel, journal, crit, tmp_path)
    (repo.sheets() / "MANIFEST.json").unlink()
    with pytest.raises(wave.WaveError, match="not frozen"):
        _launch(repo, 1, panel, journal, crit, tmp_path)
    assert journal.n_ids() == 0  # nothing was tried


def test_wave_refuses_non_geometric_grid_and_too_many_variants(tmp_path, journal, crit):
    docs = {
        "a.yaml": _sheet("Non-geometric", "A", "directional", "f1_lab.py", {"L": [10, 11, 12], "k": [2, 3, 5]}),
        "b.yaml": _sheet("Too many variants", "B", "directional", "f1_lab.py",
                         {"L": [5, 10, 20, 40], "k": [2, 3, 5, 8, 13, 21]}),
        "c.yaml": _sheet("Single parameter", "C", "directional", "f1_lab.py", {"L": [10, 20, 40]}),
    }
    repo = Repo(tmp_path / "repo").add_wave(1, docs)
    rep = _launch(repo, 1, _wave_panel(crit), journal, crit, tmp_path)
    assert set(rep.refused) == {"a.yaml", "b.yaml", "c.yaml"} and rep.n_wave_trials == 0
    assert "non-geometric" in rep.refused["a.yaml"] and "variants" in rep.refused["b.yaml"]
    assert journal.n_ids() == 0


def test_wave_c15_c16_on_named_panel(tmp_path, journal, crit):
    """The C15 path (riskd/fills replay on the arena universe) and C16 (control) run end to end."""
    panel = _wave_panel(crit)
    f = wave.Sheet("f.yaml", "0" * 64, "F1", "Taker pressure", "m", "directional", "f1_lab.py", {}, {})
    ctx = wave._Ctx(1, panel, journal, crit, STRAT, tmp_path / "series", wave.WaveReport(1), causality=False, test=True)
    arena, control, n_extra = wave._c15_c16(
        f, {"L": 20, "k": 3, "H": 10}, ctx, ["ADAUSDT", "ATOMUSDT", "AVAXUSDT"])
    assert n_extra == 4 and arena is not None and math.isfinite(arena.sharpe)
    assert arena.policy_sha256 and set(control) == {"ADAUSDT", "ATOMUSDT", "AVAXUSDT"}
    assert all(v is not None for v in control.values())
    ok, val, _ = evaluate.gate_c16(control, crit.gates.C16_outside_universe, crit.control_size)
    assert not ok and val[4] == 20 and val[2] == 20  # 3 symbols out of 20: fixed denominator
    ok15, val15, _ = evaluate.gate_c15(arena, "directional", crit.gates.C15_arena, crit.gates.C6_drawdown_max)
    assert isinstance(ok15, bool) and len(val15) == 2


def test_cli_canary_and_verify(tmp_path, capsys):
    from research.__main__ import main

    assert main(["canary"]) == 0
    assert "canary OK" in capsys.readouterr().out
    assert main(["--data", str(tmp_path / "empty"), "--journal", str(tmp_path / "absent.jsonl"), "verify"]) == 1
    output = capsys.readouterr().out
    assert "FAIL  data manifest" in output and "research journal: absent" in output
    assert main(["--reports", str(tmp_path), "statuses"]) == 0


def test_cli_wave_freeze(tmp_path, capsys):
    from research.__main__ import main

    d = tmp_path / "waves" / "1" / "sheets"
    d.mkdir(parents=True)
    (d / "x.yaml").write_text(yaml.safe_dump(_sheet("X", "X", "directional", "f1_lab.py", {"L": [10, 20, 40]})))
    assert main(["wave", "1", "--freeze", "--waves", str(tmp_path / "waves")]) == 0
    assert (d / "MANIFEST.json").is_file()
