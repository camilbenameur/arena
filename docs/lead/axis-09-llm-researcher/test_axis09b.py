"""Offline self-tests of axis 9b (population of researcher sessions; no network, no API key):
pytest docs/lead/axis-09-llm-researcher/test_axis09b.py"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import common as C  # noqa: E402
import test_axis09 as T9  # noqa: E402  (FakeClient, message helpers, git repo helper)

R = T9.R


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


EV = _load("axis09_evaluate", "evaluate.py")
POP = _load("axis09_population", "run_population.py")

RULE_OK = "def targets(df):\n    return df\n"
DELIV_OPUS = f"{R.M_RULE}\n{RULE_OK}{R.M_LOG}\nNo robust edge found. log\n{R.M_END}"


class FakeFiles:
    def __init__(self):
        self.n, self.deleted = 0, []

    def upload(self, file, expires_in_seconds=None):
        self.n += 1
        return SimpleNamespace(id=f"f{self.n}")

    def delete(self, i):
        self.deleted.append(i)


class Client(T9.FakeClient):
    def __init__(self, msgs):
        super().__init__(msgs)
        self.files = FakeFiles()


def msg(stop, text="", out=50):
    return T9._msg(stop, text, usage=(100, out))


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated ledgers: the axis-08 ledger and the data dir are temporary, the repo dir is a temporary copy."""
    ax8 = tmp_path / "ax8" / "spend.jsonl"
    monkeypatch.setattr(C.BUD, "LEDGER", ax8)
    return SimpleNamespace(data=tmp_path / "data", repo=tmp_path / "repo", ax8=ax8, path=tmp_path)


def put_actual(path: Path, usd: float):
    led = C.BUD.Ledger(path)
    with led._locked():
        led._append({"kind": "actual", "key": "pre", "usd": usd})


def execute(env, client, sid="s01", model="opus", **kw):
    env.repo.mkdir(parents=True, exist_ok=True)
    return R.execute_session(client, model, sid, files={"a.csv": b"x,y\n1,2\n"}, brief="brief", repo_dir=env.repo,
                             data_dir=env.data, max_turns=4, **kw)


# --- 1. session isolation
def test_session_writes_only_under_its_own_directory(env):
    (env.repo).mkdir(parents=True)
    top = {n: f"sentinel {n}\n" for n in ("frozen_rule.py", "trials_by_model.md")}
    for n, t in top.items():
        (env.repo / n).write_text(t)
    out = execute(env, Client([msg("end_turn", DELIV_OPUS)]))
    assert out["rule_written"] and out["stop"] == "done" and out["session"] == "opus-s01" and not out["halt"]
    d = env.repo / "sessions" / "opus-s01"
    assert (d / "frozen_rule.py").read_text() == RULE_OK and (d / "trials_by_model.md").exists()
    assert json.loads((d / "outcome.json").read_text())["rule_written"] is True
    assert {n: (env.repo / n).read_text() for n in top} == top  # the top-level files are untouched
    t = env.data / "sessions" / "opus-s01"
    assert (t / "transcript_full.jsonl").exists() and (t / "spend.jsonl").exists()  # the transcript is outside the repo dir
    assert not list(env.repo.rglob("transcript*"))
    assert "opus-s01" in (env.data / "population_9b.jsonl").read_text()


def test_two_sessions_do_not_share_files_or_ledgers(env):
    a = execute(env, Client([msg("end_turn", DELIV_OPUS)]), sid="a1")
    b = execute(env, Client([msg("end_turn", DELIV_OPUS.replace("log", "other log"))]), sid="b1")
    assert a["rule_written"] and b["rule_written"]
    la = C.BUD.Ledger(env.data / "sessions" / "opus-a1" / "spend.jsonl").totals()["total"]
    lb = C.BUD.Ledger(env.data / "sessions" / "opus-b1" / "spend.jsonl").totals()["total"]
    axis = C.BUD.Ledger(env.data / "spend.jsonl").totals()["total"]
    assert la > 0 and lb > 0 and abs(axis - (la + lb)) < 1e-9  # the axis-09 ledger holds the sum
    assert "other log" not in (env.repo / "sessions" / "opus-a1" / "trials_by_model.md").read_text()


def test_existing_session_is_never_rerun_and_bad_names_refused(env):
    execute(env, Client([msg("end_turn", DELIV_OPUS)]))
    with pytest.raises(SystemExit, match="already exists"):
        execute(env, Client([msg("end_turn", DELIV_OPUS)]))
    for bad in ("../x", "a/b", "", "-x", "x" * 40):
        with pytest.raises(SystemExit):
            execute(env, Client([]), sid=bad)
    with pytest.raises(SystemExit, match="unknown model"):
        execute(env, Client([]), model="sonnet")


def test_real_axis9_files_untouched_by_the_test_suite():
    # the committed axis-9 outputs at the top are what the axis-9 preregistration lists
    pre = (HERE / "PREREGISTRATION.md").read_text()
    assert C.sha256_file(HERE / "frozen_rule.py") in pre


def test_model_and_params_follow_model_key(env):
    cl = Client([msg("end_turn", DELIV_OPUS)])
    execute(env, cl)
    p = cl.calls[0]
    assert p["model"] == "claude-opus-5-5" and "temperature" not in p and p["output_config"] == {"effort": "high"}
    assert p["thinking"]["type"] == "adaptive" and p["tools"] == [R.CODE_TOOL]
    assert R.MODELS["fable"] == "claude-fable-5-2"


def test_brief_has_no_control_result_and_is_model_free():
    ref = T9.FAKE_REF
    b = R.build_brief(ref)
    for w in ("Fable", "Opus", "claude-", "+10.0", "control", "population", "other session"):
        assert w not in b
    C.assert_design_only(b)


def test_leaking_rule_is_rejected_not_written(env):
    bad = f"{R.M_RULE}\nX = '2026-11-01'\n{R.M_LOG}\nlog\n{R.M_END}"
    out = execute(env, Client([msg("end_turn", bad)]))
    assert not out["rule_written"] and out["stop"].startswith("deliverable rejected")
    assert not (env.repo / "sessions" / "opus-s01" / "frozen_rule.py").exists()
    assert (env.data / "sessions" / "opus-s01" / "rejected_deliverable.txt").exists()


# --- 2. gate with the sha list
def _prereg_repo(tmp_path, status="FROZEN", sessions=("opus-s01", "opus-s02"), commit=True):
    repo, g = T9._repo(tmp_path)
    lines = ["# prereg 9b", f"STATUS: {status}"]
    rules = {}
    for i, s in enumerate(sessions):
        d = repo / "sessions" / s
        d.mkdir(parents=True)
        (d / "frozen_rule.py").write_text(f"def targets(df):\n    return {i}\n")
        rules[s] = d / "frozen_rule.py"
        lines.append(f"session {s} frozen_rule.py sha256: {C.sha256_file(rules[s])}")
    lines.append("session opus-s03 no rule")
    pre = repo / "PREREGISTRATION-9b.md"
    pre.write_text("\n".join(lines) + "\n")
    if commit:
        g("add", ".")
        g("commit", "-q", "-m", "x")
    return repo, pre, rules, g


def test_gate_with_sha_list_accepts_each_listed_session(tmp_path):
    repo, pre, rules, _ = _prereg_repo(tmp_path)
    for s, r in rules.items():
        assert len(C.control_gate_session(pre, r, s, repo)) == 40


def test_gate_refuses_draft_unlisted_wrong_hash_uncommitted(tmp_path):
    repo, pre, rules, g = _prereg_repo(tmp_path / "a", status="DRAFT")
    with pytest.raises(SystemExit, match="STATUS: FROZEN"):
        C.control_gate_session(pre, rules["opus-s01"], "opus-s01", repo)
    repo, pre, rules, g = _prereg_repo(tmp_path / "b")
    with pytest.raises(SystemExit, match="not listed"):  # a session absent from the list
        r = repo / "sessions" / "opus-s09"
        r.mkdir()
        (r / "frozen_rule.py").write_text("def targets(df):\n    return 9\n")
        C.control_gate_session(pre, r / "frozen_rule.py", "opus-s09", repo)
    with pytest.raises(SystemExit, match="not listed"):  # the hash of another session does not open this one
        C.control_gate_session(pre, rules["opus-s02"], "opus-s01", repo)
    rules["opus-s01"].write_text(rules["opus-s01"].read_text() + "# edited after the freeze\n")
    with pytest.raises(SystemExit, match="not listed"):
        C.control_gate_session(pre, rules["opus-s01"], "opus-s01", repo)
    repo, pre, rules, g = _prereg_repo(tmp_path / "c", commit=False)
    with pytest.raises(SystemExit, match="not committed"):
        C.control_gate_session(pre, rules["opus-s01"], "opus-s01", repo)
    repo, pre, rules, g = _prereg_repo(tmp_path / "d")
    pre.write_text(pre.read_text() + "edit\n")
    with pytest.raises(SystemExit, match="uncommitted"):
        C.control_gate_session(pre, rules["opus-s01"], "opus-s01", repo)
    with pytest.raises(SystemExit, match="bad session name"):
        C.control_gate_session(pre, rules["opus-s01"], "../opus-s01", repo)


def test_shipped_9b_preregistration_is_a_draft_with_a_bare_status_line():
    text = (HERE / "PREREGISTRATION-9b.md").read_text()
    assert "STATUS: DRAFT" in text.splitlines() and not C.FROZEN_RE.search(text)
    assert not C.DATE_RE.search("") and "sha256" in text


# --- 3. one control run per session
def test_lock_is_per_session(tmp_path):
    ta, tb = tmp_path / "opus-s01", tmp_path / "opus-s02"
    C.take_control_lock("c" * 40, "h" * 64, ta)
    with pytest.raises(SystemExit, match="already ran"):
        C.take_control_lock("c" * 40, "h" * 64, ta)
    assert not C.control_ran(tb)
    C.take_control_lock("c" * 40, "h" * 64, tb)  # another session is not blocked
    assert C.control_ran(tb)


def test_evaluate_session_control_refuses_when_locked_or_not_frozen(tmp_path):
    repo, pre, rules, g = _prereg_repo(tmp_path / "r")
    data = tmp_path / "data"
    a = SimpleNamespace(session="opus-s01", period="control", rule=EV.RULE, n_random=2)
    _, tdir = C.session_dirs("opus-s01", repo, data)
    tdir.mkdir(parents=True)
    C.take_control_lock("c" * 40, "h" * 64, tdir)
    with pytest.raises(SystemExit, match="already ran"):
        EV.run_session_eval(a, repo, data, pre)
    assert not (tdir / "eval_control.json").exists()
    repo2, pre2, rules2, _ = _prereg_repo(tmp_path / "r2", status="DRAFT")
    with pytest.raises(SystemExit, match="STATUS: FROZEN"):
        EV.run_session_eval(a, repo2, data, pre2)
    a3 = SimpleNamespace(session="opus-s03", period="control", rule=EV.RULE, n_random=2)  # a listed session without a rule
    with pytest.raises(SystemExit, match="no frozen_rule.py"):
        EV.run_session_eval(a3, repo, data, pre)


# --- 4. budget stops
def test_session_cap_stops_session_without_halting_the_population(env):
    # each call costs about 1.5 USD on Opus (75k output tokens): the third call would pass the 3 USD session cap
    cl = Client([msg("pause_turn", "w", out=75000), msg("pause_turn", "w", out=75000), msg("end_turn", DELIV_OPUS, out=75000)])
    out = execute(env, cl)
    assert out["stop"].startswith("budget[session]") and not out["rule_written"] and not out["halt"]
    assert out["usd"] <= 3.0 + 0.05  # the fake ignores max_tokens; the container time is booked on top of the reservation


def test_fit_max_tokens_lowers_output_room_to_remaining_budget(env):
    led = C.BUD.Ledger(env.data / "s.jsonl")
    books = R.Books([("session", led, 1.0)], led)
    params = dict(model="claude-opus-5-5", messages=[{"role": "user", "content": "x" * 3000}], max_tokens=64000)
    R.fit_max_tokens(books, params)
    assert MIN_OK < params["max_tokens"] < 64000
    assert R.projected_usd(params["model"], params["messages"], "", params["max_tokens"]) <= 1.0
    put_actual(env.data / "s.jsonl", 0.99)
    with pytest.raises(C.BUD.BudgetExceeded):
        R.fit_max_tokens(books, dict(params, max_tokens=64000))


MIN_OK = R.MIN_OUT_TOKENS - 1


def test_shared_total_with_axis8_is_enforced_and_halts(env):
    put_actual(env.ax8, 157.9)
    out = execute(env, Client([msg("end_turn", DELIV_OPUS)]))
    assert out["stop"].startswith("budget[axis]") and out["halt"] and not out["rule_written"]


def test_driver_stops_cleanly_when_budget_would_be_exceeded(env):
    env.repo.mkdir(parents=True)
    put_actual(env.data / "spend.jsonl", 28.0)  # axis-09 cap is 31.23: room 3.23 = one session of 3 USD
    cl = Client([msg("end_turn", DELIV_OPUS, out=100000)] * 5)  # about 2.0 USD per session
    out = POP.run_population(cl, "opus", 5, files={"a.csv": b"x\n"}, brief="b", data_dir=env.data, repo_dir=env.repo, max_turns=4)
    assert out["run"] == 1 and out["rules_written"] == 1 and out["stopped"].startswith("budget:")
    assert out["not_run"] == ["s02", "s03", "s04", "s05"] and 1.9 < out["usd"] < 2.2
    assert len(cl.calls) == 1  # no call was made for the sessions that did not fit
    assert (env.repo / "sessions" / "opus-s01" / "outcome.json").exists() and not (env.repo / "sessions" / "opus-s02").exists()
    axis = C.BUD.Ledger(env.data / "spend.jsonl").totals()
    assert axis["total"] <= R.AXIS9_PRIOR_USD + R.AXIS9B_CAP_USD and axis["reserved"] == 0


def test_driver_records_outcomes_skips_existing_and_parallel_waves(env):
    env.repo.mkdir(parents=True)
    cl = Client([msg("end_turn", DELIV_OPUS), msg("end_turn", "no markers here"), msg("end_turn", DELIV_OPUS)] * 3)
    pre = execute(env, Client([msg("end_turn", DELIV_OPUS)]), sid="s01")  # s01 exists: skipped, not re-run
    assert pre["rule_written"]
    out = POP.run_population(cl, "opus", 3, files={"a.csv": b"x\n"}, brief="b", data_dir=env.data, repo_dir=env.repo, parallel=2,
                             max_turns=6)
    assert [o["session"] for o in out["outcomes"]] == ["opus-s02", "opus-s03"] and out["stopped"] is None
    by = {o["session"]: o for o in out["outcomes"]}
    assert sum(o["rule_written"] for o in by.values()) + sum(1 for o in by.values() if not o["rule_written"]) == 2
    for o in by.values():
        assert {"rule_written", "usd", "stop", "turns"} <= set(o)
        assert (env.repo / "sessions" / o["session"] / "outcome.json").exists()
    lines = (env.data / "population_9b.jsonl").read_text().splitlines()
    assert len(lines) == 3


def test_driver_halts_on_api_error(env):
    env.repo.mkdir(parents=True)

    class Boom(Client):
        def _stream(self, **p):
            raise TimeoutError("connection reset")

    out = POP.run_population(Boom([]), "opus", 3, files={"a.csv": b"x\n"}, brief="b", data_dir=env.data, repo_dir=env.repo)
    assert out["run"] == 1 and out["stopped"].startswith("halt") and "TimeoutError" in out["outcomes"][0]["stop"]
    # the reservation of the possibly billed call stays open
    assert C.BUD.Ledger(env.data / "spend.jsonl").totals()["reserved"] > 0


# --- 5. summary
def _rep(ret, rnd_mean, p95, crit, dd=-10.0):
    return {"report": {"bot": {"return_pct": ret, "max_dd_pct": dd, "turnover_x": 5.0, "sharpe": 1.0, "months_pct": {}},
                       "reference": {"basket_1x": {"return_pct": -35.8}, "trend_2x": {"return_pct": 33.9}},
                       "random": {"return_mean_pct": rnd_mean, "return_p95_pct": p95, "share_beaten_by_bot": 0.1},
                       "criteria": crit, "all_pass": all(crit.values())}}


def test_summary_statistics():
    ok = dict(beats_trend_2x=True, beats_basket=True, max_dd_ok=True, positive_every_month=True, beats_random_p95=True)
    bad = dict(ok, beats_trend_2x=False, beats_random_p95=False)
    rows = [
        {"session": "opus-s01", "rule": True, "no_edge": True, "design": None, "control": _rep(10.0, 16.0, 23.0, bad), "usd": 1.0},
        {"session": "opus-s02", "rule": True, "no_edge": False, "design": None, "control": _rep(-4.0, 12.0, 20.0, dict(bad, beats_basket=True)), "usd": 1.0},
        {"session": "opus-s03", "rule": True, "no_edge": True, "design": None, "control": _rep(40.0, 10.0, 30.0, ok), "usd": 1.0},
        {"session": "opus-s04", "rule": False, "no_edge": False, "design": None, "control": None, "usd": 0.5},
    ]
    s = EV.summarize(rows)
    assert s["n_sessions"] == 4 and s["n_rule"] == 3 and s["n_control"] == 3
    assert s["mean_return_pct"] == 15.33 and s["median_return_pct"] == 10.0
    assert s["n_positive"] == 2 and s["n_beats_basket"] == 3 and s["n_beats_trend_2x"] == 1 and s["n_beats_random_p95"] == 1
    assert s["n_all_pass"] == 1 and s["share_no_edge_label"] == 0.667
    assert s["mean_random_pct"] == 12.67 and s["mean_minus_random_pct"] == 2.67
    EV.print_summary(rows)  # prints without error, including the session with no rule


def test_label_detection_and_session_list(tmp_path):
    d = tmp_path / "sessions" / "opus-s01"
    d.mkdir(parents=True)
    (d / "frozen_rule.py").write_text("x = 1\n")
    (d / "trials_by_model.md").write_text("Verdict: NO ROBUST EDGE FOUND\n")
    e = tmp_path / "sessions" / "fable-s02"
    e.mkdir()
    (e / "frozen_rule.py").write_text("x = 2\n")
    (e / "trials_by_model.md").write_text("I found a real edge\n")
    (tmp_path / "sessions" / "opus-s03").mkdir()
    assert EV.labelled_no_edge(d) and not EV.labelled_no_edge(e)
    lines = EV.session_list(tmp_path).splitlines()
    assert lines[0] == f"session fable-s02 frozen_rule.py sha256: {hashlib.sha256(b'x = 2' + b'\n').hexdigest()}"
    assert lines[2] == "session opus-s03 no rule" and len(lines) == 3
    rows = EV.load_session_rows(tmp_path, tmp_path / "data")
    assert [r["session"] for r in rows] == ["fable-s02", "opus-s01", "opus-s03"] and rows[1]["no_edge"] and not rows[2]["rule"]
