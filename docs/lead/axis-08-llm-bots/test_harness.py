"""Offline self-tests of the harness (no network, no API key): pytest docs/lead/axis-08-llm-bots/test_harness.py"""

from __future__ import annotations

import json
import multiprocessing as mp
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bot as BOT  # noqa: E402
import budget as BUD  # noqa: E402
import run as RUN  # noqa: E402


def _reqs(n=3, bid="m__v"):
    user = "x"
    return [{"custom_id": f"d_{t:04d}", "params": BOT.build_params("claude-haiku-5-5", "low", "v1_plain", user)}
            for t in range(n)]


# --- 1. control gate regex
def test_frozen_regex_is_line_anchored():
    assert RUN.is_frozen("title\nSTATUS: FROZEN\nmore")
    assert not RUN.is_frozen("STATUS: DRAFT (change to `STATUS: FROZEN` later)")
    assert not RUN.is_frozen("text STATUS: FROZEN")
    assert not RUN.is_frozen("STATUS: FROZEN but not yet")
    assert not RUN.is_frozen("status: frozen")


def test_shipped_8b_preregistration_is_frozen_with_16_bots():
    # frozen by the lead on 2026-11-27: 12 replicates (part A) and 4 high-effort sync bots (part B)
    text = RUN.PREREG_8B.read_text()
    assert RUN.is_frozen(text)
    assert sum(1 for line in text.splitlines() if line.startswith("- claude-")) == 16


# --- 2. control lock only after a successful reserve, dry runs ignored
def test_lock_written_after_reserve_not_when_budget_refuses(tmp_path):
    led = BUD.Ledger(tmp_path / "spend.jsonl")
    lock = lambda: RUN.take_control_lock("bot1", "abc", False, tmp_path)  # noqa: E731
    with pytest.raises(BUD.BudgetExceeded):
        RUN.submit_batch(BOT.FakeClient(), led, tmp_path / "r1", "k", _reqs(), proj=50.0, cap=1.0, fake=True, lock_fn=lock) \
            if (tmp_path / "r1").mkdir() is None else None
    assert not (tmp_path / "control_runs.jsonl").exists()
    (tmp_path / "r2").mkdir()
    RUN.submit_batch(BOT.FakeClient(), led, tmp_path / "r2", "k", _reqs(), proj=0.5, cap=1.0, fake=True, lock_fn=lock)
    assert RUN.control_ran("bot1", tmp_path)
    with pytest.raises(SystemExit):
        RUN.take_control_lock("bot1", "abc", False, tmp_path)


def test_dry_run_lock_entries_are_ignored(tmp_path):
    RUN.take_control_lock("bot2", "abc", True, tmp_path)
    assert not RUN.control_ran("bot2", tmp_path)
    RUN.take_control_lock("bot2", "abc", False, tmp_path)  # a real run is still allowed after a dry-run
    assert RUN.control_ran("bot2", tmp_path)


# --- 4. atomic reserve across processes
def _worker(path, q):
    led = BUD.Ledger(Path(path))
    ok = 0
    for _ in range(10):
        try:
            led.reserve("same-key", 1.0, 10.0)
            ok += 1
        except BUD.BudgetExceeded:
            pass
    q.put(ok)


def test_reserve_is_atomic_under_two_processes(tmp_path):
    path = tmp_path / "spend.jsonl"
    q = mp.Queue()
    ps = [mp.Process(target=_worker, args=(str(path), q)) for _ in range(2)]
    [p.start() for p in ps]
    [p.join() for p in ps]
    got = q.get() + q.get()
    led = BUD.Ledger(path)
    assert got == 10  # cap 10, 20 attempts of 1.0: exactly 10 succeed, never 11
    assert led.totals()["reserved"] == pytest.approx(10.0)
    assert len(led.open_reservations()) == 10  # same key reserved many times: none overwrote another


def test_release_and_stale(tmp_path):
    led = BUD.Ledger(tmp_path / "s.jsonl")
    rid = led.reserve("a", 1.0, 5.0)
    assert led.release(rid) and not led.release(rid)
    led.reserve("b", 1.0, 5.0)
    assert led.release_stale(0) and led.totals()["reserved"] == 0


# --- 5. a second batch submission is refused
def test_second_batch_submission_refused(tmp_path):
    led = BUD.Ledger(tmp_path / "s.jsonl")
    cl = BOT.FakeClient()
    RUN.submit_batch(cl, led, tmp_path, "k", _reqs(), 0.5, 5.0, fake=True)
    before = led.totals()
    with pytest.raises(SystemExit, match="already exists"):
        RUN.submit_batch(cl, led, tmp_path, "k", _reqs(), 0.5, 5.0, fake=True)
    assert led.totals() == before  # nothing reserved by the refused attempt


class _Boom:
    def __init__(self, status):
        self.messages = SimpleNamespace(batches=SimpleNamespace(create=self._c))
        self.status = status

    def _c(self, requests):
        e = RuntimeError("x")
        e.status_code = self.status
        raise e


def test_batch_create_errors_are_explicit(tmp_path):
    led = BUD.Ledger(tmp_path / "s.jsonl")
    (tmp_path / "a").mkdir()
    with pytest.raises(RuntimeError):  # 400: definite, released, resubmission allowed
        RUN.submit_batch(_Boom(400), led, tmp_path / "a", "k", _reqs(), 0.5, 5.0, fake=True)
    assert led.totals()["reserved"] == 0 and not (tmp_path / "a" / "batch.json").exists()
    (tmp_path / "b").mkdir()
    with pytest.raises(SystemExit, match="unknown"):  # 500: may exist, reservation kept, resubmission blocked
        RUN.submit_batch(_Boom(500), led, tmp_path / "b", "k", _reqs(), 0.5, 5.0, fake=True)
    assert led.totals()["reserved"] == pytest.approx(0.5)
    with pytest.raises(SystemExit, match="already exists"):
        RUN.submit_batch(_Boom(500), led, tmp_path / "b", "k", _reqs(), 0.5, 5.0, fake=True)


# --- 4. collect is idempotent
def test_collect_idempotent(tmp_path):
    led = BUD.Ledger(tmp_path / "s.jsonl")
    cl = BOT.FakeClient()
    RUN.submit_batch(cl, led, tmp_path, "k", _reqs(5), 0.5, 5.0, fake=True)
    d1 = RUN.collect_batch(cl, led, tmp_path, "claude-haiku-5-5", dry_run=False, poll_s=0)
    n1 = sum(1 for e in led._events() if e["kind"] == "actual")
    s1 = led.totals()
    d2 = RUN.collect_batch(cl, led, tmp_path, "claude-haiku-5-5", dry_run=False, poll_s=0)
    assert n1 == 5 and sum(1 for e in led._events() if e["kind"] == "actual") == 5
    assert led.totals() == s1 and s1["reserved"] == 0
    assert {t: d["usd"] for t, d in d1.items()} == {t: d["usd"] for t, d in d2.items()}


# --- 5. sync retry guard: a 5xx attempt stays counted
def test_sync_5xx_retry_keeps_reservation_open(tmp_path):
    led = BUD.Ledger(tmp_path / "s.jsonl")
    calls = []

    class C:
        def __init__(self):
            self.messages = SimpleNamespace(create=self.create)

        def create(self, **p):
            calls.append(1)
            if len(calls) == 1:
                e = RuntimeError("overloaded")
                e.status_code = 529
                raise e
            return BOT.FakeClient().messages.create(**p)

    p = BOT.build_params("claude-haiku-5-5", "low", "v1_plain", "hello")
    msg, rid = RUN.guarded_call(C(), led, p, "claude-haiku-5-5", "k", 0.01, 1.0, sleep=lambda s: None)
    assert len(calls) == 2
    assert len(led.open_reservations()) == 2  # the failed attempt's worst case is still counted
    RUN.settle_sync(led, rid, "claude-haiku-5-5", msg, False)
    assert len(led.open_reservations()) == 1


# --- 3. bot id covers the code
def test_bot_id_contains_code_hash():
    assert BOT.code_hash() in RUN.bot_id("claude-haiku-5-5", "v1_plain", "low", "batch")


def test_max_tokens_and_truncation_status():
    assert BOT.MAX_TOKENS >= 16000
    msg = SimpleNamespace(stop_reason="max_tokens", content=[])
    assert BOT.parse_message(msg)[2] == "max_tokens"


# --- axis 8b: frozen code, replicate gate, sync resume
FROZEN_CODE_HASH = "bb0e9052"


def test_frozen_code_hash_unchanged_and_frozen_ids_still_compute():
    assert BOT.code_hash() == FROZEN_CODE_HASH
    ids = RUN.listed_ids(RUN.PREREG.read_text())
    assert len(ids) == 12 and all(i.split("__")[1].endswith("-" + FROZEN_CODE_HASH) for i in ids)
    recomputed = {RUN.bot_id(m, v, e, "batch") for m, e in BOT.MODELS.values() for v in BOT.VARIANTS}
    assert recomputed == ids


def _prereg_repo(tmp_path, monkeypatch, *, axis8_frozen=True, b_text=None, commit_b=True, base="BASE"):
    """Throw-away git repo holding fake PREREGISTRATION.md / PREREGISTRATION-8b.md, wired into the run module."""
    import subprocess

    d = tmp_path / "repo" / "docs"
    d.mkdir(parents=True)
    g = lambda *a: subprocess.run(["git", "-C", str(tmp_path / "repo"), *a], check=True, capture_output=True)  # noqa: E731
    g("init", "-q")
    g("config", "user.email", "test")
    g("config", "user.name", "t")
    g("config", "commit.gpgsign", "false")
    p8 = d / "PREREGISTRATION.md"
    p8.write_text(f"STATUS: {'FROZEN' if axis8_frozen else 'DRAFT'}\n- {base}\n")
    g("add", "-A")
    g("commit", "-qm", "axis8")
    pb = d / "PREREGISTRATION-8b.md"
    if b_text is not None:
        pb.write_text(b_text)
        if commit_b:
            g("add", "-A")
            g("commit", "-qm", "8b")
    monkeypatch.setattr(RUN.BR, "REPO", tmp_path / "repo")
    monkeypatch.setattr(RUN, "PREREG", p8)
    monkeypatch.setattr(RUN, "PREREG_8B", pb)
    monkeypatch.setattr(RUN, "DATA_DIR", tmp_path / "data")
    return tmp_path / "repo"


def test_replicate_gate_needs_8b_file(tmp_path, monkeypatch):
    _prereg_repo(tmp_path, monkeypatch)  # no 8b file at all
    with pytest.raises(SystemExit, match="PREREGISTRATION-8b.md"):
        RUN.control_gate("BASE", False, replicate=1)


def test_replicate_gate_needs_base_in_axis8_and_replicate_listed_and_frozen(tmp_path, monkeypatch):
    _prereg_repo(tmp_path, monkeypatch, b_text="STATUS: FROZEN\n- BASE__r1\n- OTHER__r1\n")
    assert RUN.control_gate("BASE", False, replicate=1)  # base in axis 8, BASE__r1 listed, 8b frozen and committed
    with pytest.raises(SystemExit, match="not listed in PREREGISTRATION-8b"):
        RUN.control_gate("BASE", False, replicate=2)  # r2 not listed
    with pytest.raises(SystemExit, match="axis-8 preregistration"):
        RUN.control_gate("OTHER", False, replicate=1)  # OTHER__r1 is listed in 8b but OTHER is not a frozen axis-8 bot
    with pytest.raises(SystemExit, match="replicate must be"):
        RUN.control_gate("BASE", False, replicate=4)


def test_replicate_gate_refuses_draft_or_uncommitted_8b(tmp_path, monkeypatch):
    _prereg_repo(tmp_path, monkeypatch, b_text="STATUS: DRAFT\n- BASE__r1\n")
    with pytest.raises(SystemExit, match="STATUS: FROZEN"):
        RUN.control_gate("BASE", False, replicate=1)
    (tmp_path / "x").mkdir()
    _prereg_repo(tmp_path / "x", monkeypatch, b_text="STATUS: FROZEN\n- BASE__r1\n", commit_b=False)
    with pytest.raises(SystemExit, match="not committed"):
        RUN.control_gate("BASE", False, replicate=1)


def test_replicate_listing_is_exact_not_substring(tmp_path, monkeypatch):
    # only the replicate id is listed in 8b: the plain base id must not pass as a (new-bot) listing, and the gate for the
    # original bot still follows axis 8 (and is refused once its lock exists)
    _prereg_repo(tmp_path, monkeypatch, b_text="STATUS: FROZEN\n- BASE__r1\n")
    assert RUN.listed_ids("- BASE__r1\n") == {"BASE__r1"} and "BASE" not in RUN.listed_ids("- BASE__r1\n")


def test_replicate_never_overwrites_original(tmp_path, monkeypatch):
    _prereg_repo(tmp_path, monkeypatch, b_text="STATUS: FROZEN\n- BASE__r1\n")
    # (a) the control lock of the original does not block the replicate, and the replicate lock does not touch the original's
    RUN.take_control_lock("BASE", "c", False, RUN.DATA_DIR)
    assert RUN.control_gate("BASE", False, replicate=1)  # the original already ran: the replicate is still allowed
    RUN.take_control_lock(RUN.replicate_id("BASE", 1), "c", False, RUN.DATA_DIR)
    assert RUN.control_ran("BASE") and RUN.control_ran("BASE__r1")
    with pytest.raises(SystemExit, match="already ran"):
        RUN.control_gate("BASE", False, replicate=1)  # a replicate runs once
    # (b) run directories differ; a submitted original batch.json stays intact and a replicate cannot reuse its directory
    root = tmp_path / "runs"
    o, r = RUN.run_dir_for(root, "BASE", "control"), RUN.run_dir_for(root, "BASE", "control", 1)
    assert o != r and r.name == "BASE__r1__control"
    o.mkdir(parents=True), r.mkdir(parents=True)
    led = BUD.Ledger(tmp_path / "s.jsonl")
    RUN.submit_batch(BOT.FakeClient(), led, o, "k", _reqs(), 0.5, 5.0, fake=True)
    before = (o / "batch.json").read_text()
    RUN.submit_batch(BOT.FakeClient(), led, r, "k2", _reqs(), 0.5, 5.0, fake=True)  # own directory: fine
    with pytest.raises(SystemExit, match="already exists"):
        RUN.submit_batch(BOT.FakeClient(), led, r, "k2", _reqs(), 0.5, 5.0, fake=True)
    assert (o / "batch.json").read_text() == before


def test_new_8b_bot_gate_uses_8b_file(tmp_path, monkeypatch):
    _prereg_repo(tmp_path, monkeypatch, b_text="STATUS: FROZEN\n- NEWSYNC\n")
    assert RUN.control_gate("NEWSYNC", False)
    with pytest.raises(SystemExit, match="not listed"):
        RUN.control_gate("UNKNOWN", False)


def test_spread_report():
    import report as REP

    mk = lambda r: {"bot": {"return_pct": r, "max_dd_pct": -5.0, "sharpe": 1.0, "turnover_x": 10.0, "months_pct": {}},  # noqa: E731
                    "random": {"share_beaten_by_bot": 0.1}, "all_pass": False}
    sp = REP.spread({"original": mk(-5.0), "r1": mk(-3.0), "r2": mk(-8.0)})
    assert sp["return_range_pp"] == 5.0 and sp["n_runs"] == 3 and sp["return_min_pct"] == -8.0
    assert "spread over 3 runs" in REP.spread_table(sp)


def _sync_setup(tmp_path):
    import bars as BR

    s, e = BR.PERIODS["design"]
    data, i0 = BR.load_data(s, e)
    return BR.make_bars(data, i0)


class _Counting(BOT.FakeClient):
    def __init__(self):
        super().__init__(0)
        self.calls = 0
        inner = self.messages.create

        def create(**p):
            self.calls += 1
            return inner(**p)

        self.messages.create = create


def test_sync_resume_does_not_recall_decided_bars(tmp_path):
    try:
        b = _sync_setup(tmp_path)
    except Exception as ex:  # noqa: BLE001  (market data not on this machine)
        pytest.skip(f"no market data: {ex}")
    led = BUD.Ledger(tmp_path / "s.jsonl")
    part = tmp_path / "decisions.partial.jsonl"
    kw = dict(model="claude-opus-5-5", effort="high", variant="v1_plain", b=b, bid="B", period="design", cap=50.0, dry_run=False,
              partial_path=part)
    # run 1 "crashes" after 3 decisions
    c1 = _Counting()
    RUN.sync_loop(c1, led, n=3, **kw)
    assert c1.calls == 3 and len(RUN.load_partial(part, 6)) == 3
    spent = led.totals()["settled"]
    with part.open("a") as f:
        f.write('{"t": 3, "status": "o')  # a torn last line from the crash
    done = RUN.load_partial(part, 6)
    assert sorted(done) == [0, 1, 2]
    # resume: only bars 3..5 are called, decided bars cost nothing more
    c2 = _Counting()
    prompts = []
    orig = c2.messages.create
    c2.messages.create = lambda **p: (prompts.append(p["messages"][0]["content"]), orig(**p))[1]
    out = RUN.sync_loop(c2, led, n=6, done=done, **kw)
    assert c2.calls == 3 and sorted(out) == [0, 1, 2, 3, 4, 5]
    assert all(out[t] is done[t] for t in range(3))
    assert led.totals()["settled"] > spent and len([e for e in led._events() if e["kind"] == "actual"]) == 6
    # the state shown at bar 3 after resume equals the state an uninterrupted run shows (track record replayed)
    c3 = _Counting()
    prompts3 = []
    orig3 = c3.messages.create
    c3.messages.create = lambda **p: (prompts3.append(p["messages"][0]["content"]), orig3(**p))[1]
    RUN.sync_loop(c3, BUD.Ledger(tmp_path / "ref.jsonl"), n=6, **{**kw, "partial_path": None})
    assert prompts == prompts3[3:]
