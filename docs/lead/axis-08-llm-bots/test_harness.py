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


def test_shipped_preregistration_is_not_frozen():
    assert not RUN.is_frozen(RUN.PREREG.read_text())


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
