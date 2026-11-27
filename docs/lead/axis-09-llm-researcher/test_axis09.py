"""Offline self-tests of axis 9 (no network, no API key): pytest docs/lead/axis-09-llm-researcher/test_axis09.py"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as C  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("axis09_research", Path(__file__).resolve().parent / "research.py")
R = importlib.util.module_from_spec(_spec)  # loaded by path: the repository also has a `research` package
sys.modules["axis09_research"] = R
_spec.loader.exec_module(R)

T = list(C.TICKERS)
FAKE_REF = {k: {"return_pct": 1.0, "max_dd_pct": -1.0, "sharpe": 1.0, "turnover_x": 1.0, "months_pct": {"2026-07": 1.0}}
            for k in ("basket_1x", "trend_1x", "trend_2x")}


def synth(n=120, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2026-07-01", periods=n, freq="4h")
    rows = []
    for tk in T:
        px = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
        for i in range(n):
            rows.append((ts[i], tk, px[i], px[i] * 1.005, px[i] * 0.995, px[i], 1.0, 0.0))
    return pd.DataFrame(rows, columns=C.COLUMNS).sort_values(["ts", "ticker"]).reset_index(drop=True)


def _wide(df):
    return df.pivot(index="ts", columns="ticker", values="close")[T]


def causal_rule(df):
    c = _wide(df)
    return np.sign(c / c.shift(6) - 1).fillna(0.0)


def lookahead_rule(df):
    c = _wide(df)
    return np.sign(c.shift(-1) / c - 1).fillna(0.0)  # uses the next bar


def fullsample_rule(df):
    c = _wide(df)
    return np.sign(c - c.mean()).fillna(0.0)  # full-sample mean: a subtler lookahead


# --- 1. nothing on or after 2026-10-01 is uploaded or prompted
def test_guard_refuses_late_dates():
    C.assert_design_only("2026-09-30 20:00:00 and 2026-07-01")
    for bad in ("2026-10-01", "x 2026-11-05 y", "2027-01-01T00:00:00", "2026-12-31"):
        with pytest.raises(ValueError):
            C.assert_design_only(bad)


def test_brief_and_helper_have_no_late_date():
    C.assert_design_only(R.build_brief(FAKE_REF), "brief")
    C.assert_design_only((Path(R.__file__).parent / "sandbox_backtest.py").read_text(), "helper")


def test_real_design_csv_ends_before_october():
    try:
        text, df = C.design_csv()
    except (FileNotFoundError, OSError):
        pytest.skip("candle data not on this machine")
    assert df["ts"].min() == pd.Timestamp("2026-07-01 00:00:00")
    assert df["ts"].max() == pd.Timestamp("2026-09-30 20:00:00")
    assert df["ts"].max() < pd.Timestamp("2026-10-01")
    assert len(df) == 552 * 6 and list(df.columns) == C.COLUMNS
    C.assert_design_only(text)
    assert "2026-10" not in text


def test_make_frame_drops_late_bars():
    # a Data object extending past the design end: bars on or after the end are cut by make_frame
    n_bars, k = 12, 6
    ts = (pd.Timestamp("2026-09-30 16:00").value // 10**9) + np.arange(n_bars * C.BAR_MIN) * 60
    z = np.ones((len(ts), k))
    data = C.B.Data(ts.astype(np.int64), z, z, z, z, z, np.zeros_like(z))
    df = C.make_frame(data, C.DESIGN_START, C.DESIGN_END)
    assert df["ts"].max() == pd.Timestamp("2026-09-30 20:00:00") and len(df) == 2 * 6


# --- 2. causality
def test_causality_passes_causal_rule_and_catches_lookahead():
    df = synth()
    assert C.causality_gap(causal_rule, df, cuts=8) == 0.0
    assert C.causality_gap(lookahead_rule, df, cuts=8) > 0.5
    assert C.causality_gap(fullsample_rule, df, cuts=8) > 0.0


def test_rule_output_validation():
    df = synth(30)
    with pytest.raises(ValueError):
        C.run_rule(lambda d: causal_rule(d) * 3, df)  # outside [-2, 2]
    with pytest.raises(ValueError):
        C.run_rule(lambda d: causal_rule(d).replace(0.0, np.nan), df)  # NaN
    assert C.run_rule(causal_rule, df).shape == (30, 6)


# --- 3. control gate and lock
def _repo(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    g = lambda *a: subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *a],  # noqa: E731
                                  check=True, capture_output=True)
    g("init", "-q")
    return tmp_path, g


def _setup(tmp_path, status="FROZEN", with_hash=True, commit=True):
    repo, g = _repo(tmp_path)
    rule = repo / "frozen_rule.py"
    rule.write_text("def targets(df):\n    return None\n")
    pre = repo / "PREREGISTRATION.md"
    lines = ["# prereg", f"STATUS: {status}"]
    if with_hash:
        lines.append(f"frozen_rule.py sha256: {C.sha256_file(rule)}")
    pre.write_text("\n".join(lines) + "\n")
    if commit:
        g("add", ".")
        g("commit", "-q", "-m", "x")
    return repo, pre, rule, g


def test_gate_accepts_committed_frozen_with_hash(tmp_path):
    repo, pre, rule, _ = _setup(tmp_path)
    assert len(C.control_gate(pre, rule, repo)) == 40


def test_gate_refuses_draft_uncommitted_modified_or_wrong_hash(tmp_path):
    repo, pre, rule, g = _setup(tmp_path / "a", status="DRAFT")
    with pytest.raises(SystemExit, match="STATUS: FROZEN"):
        C.control_gate(pre, rule, repo)
    repo, pre, rule, g = _setup(tmp_path / "b", commit=False)
    with pytest.raises(SystemExit, match="not committed"):
        C.control_gate(pre, rule, repo)
    repo, pre, rule, g = _setup(tmp_path / "c")
    pre.write_text(pre.read_text() + "edit\n")
    with pytest.raises(SystemExit, match="uncommitted"):
        C.control_gate(pre, rule, repo)
    repo, pre, rule, g = _setup(tmp_path / "d", with_hash=False)
    with pytest.raises(SystemExit, match="sha256"):
        C.control_gate(pre, rule, repo)
    repo, pre, rule, g = _setup(tmp_path / "e")
    rule.write_text(rule.read_text() + "# changed after the freeze\n")
    with pytest.raises(SystemExit, match="sha256"):
        C.control_gate(pre, rule, repo)


def test_status_line_is_anchored(tmp_path):
    repo, pre, rule, g = _setup(tmp_path, status="FROZEN but not yet")
    with pytest.raises(SystemExit, match="STATUS: FROZEN"):
        C.control_gate(pre, rule, repo)


def test_shipped_axis9_preregistration_is_frozen_with_the_rule_hash():
    # frozen by the lead on 2026-11-27 after Fable's session, before the single control run
    text = (Path(R.__file__).parent / "PREREGISTRATION.md").read_text()
    assert C.FROZEN_RE.search(text) and "frozen_rule.py sha256: " in text


def test_control_lock_refuses_second_run(tmp_path):
    assert not C.control_ran(tmp_path)
    C.take_control_lock("c" * 40, "h" * 64, tmp_path)
    assert C.control_ran(tmp_path)
    with pytest.raises(SystemExit, match="already ran"):
        C.take_control_lock("c" * 40, "h" * 64, tmp_path)


# --- 4. session loop (fake client): pause_turn loop, refusal, deliverable parsing, budget stop
def _msg(stop, text="", usage=(100, 50)):
    blk = [SimpleNamespace(type="text", text=text, model_dump=lambda mode=None, t=text: {"type": "text", "text": t})] if text else []
    u = SimpleNamespace(input_tokens=usage[0], output_tokens=usage[1], cache_creation_input_tokens=0, cache_read_input_tokens=0,
                        model_dump=lambda mode=None: {})
    return SimpleNamespace(stop_reason=stop, stop_details=None, content=blk, usage=u, container=SimpleNamespace(id="c1"))


class _Stream:
    def __init__(self, m):
        self.m = m

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.m


class FakeClient:
    def __init__(self, msgs):
        self.msgs, self.calls = list(msgs), []
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **p):
        self.calls.append(p)
        return _Stream(self.msgs.pop(0))


DELIV = f"{R.M_RULE}\ndef targets(df):\n    return df\n{R.M_LOG}\nlog\n{R.M_END}"


def test_session_loops_on_pause_turn_and_parses_deliverable(tmp_path):
    cl = FakeClient([_msg("pause_turn", "working"), _msg("end_turn", DELIV)])
    res = R.run_session(cl, "brief", ["f1"], cap=5.0, effort="high", max_tokens=1000, max_turns=5, out_dir=tmp_path, tag="t")
    assert res["stop"] == "done" and res["turns"] == 2
    assert res["deliverable"][0].startswith("def targets") and res["deliverable"][1].strip() == "log"
    assert cl.calls[1]["container"] == "c1" and cl.calls[1]["messages"][-1]["role"] == "assistant"  # resumed, no new user turn
    assert cl.calls[0]["model"] == "claude-fable-5-2" and "temperature" not in cl.calls[0] and cl.calls[0]["output_config"] == {"effort": "high"}
    assert (tmp_path / "transcript_t.jsonl").exists() and res["usd"] > 0


def test_session_stops_on_refusal(tmp_path):
    res = R.run_session(FakeClient([_msg("refusal")]), "b", [], cap=5.0, effort="high", max_tokens=1000, max_turns=3, out_dir=tmp_path, tag="r")
    assert res["stop"].startswith("refusal") and res["deliverable"] is None


def test_session_budget_stop_before_any_call(tmp_path):
    cl = FakeClient([_msg("end_turn", DELIV)])
    res = R.run_session(cl, "b", [], cap=0.01, effort="high", max_tokens=64000, max_turns=3, out_dir=tmp_path, tag="x")
    assert res["stop"].startswith("budget") and cl.calls == []


def test_write_outputs_refuses_late_dates_and_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "HERE", tmp_path)
    with pytest.raises(ValueError):
        R.write_outputs(("x = '2026-11-01'\n", "log\n"), False)
    R.write_outputs(("def targets(df):\n    return df\n", "log\n"), False)
    with pytest.raises(SystemExit):
        R.write_outputs(("def targets(df):\n    return df\n", "log\n"), False)
