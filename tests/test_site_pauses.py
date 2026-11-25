"""Absence pauses drawn on the curves (arena/site/pauses.py)."""

from __future__ import annotations

import os
from pathlib import Path

from arena.site.pauses import ack_times, clip, dormancy_pauses

D = 86_400


def test_no_pause_while_acks_arrive_within_7_days() -> None:
    assert dormancy_pauses([6 * D, 12 * D], 0, 18 * D) == []


def test_pause_from_day_7_to_the_late_ack() -> None:
    assert dormancy_pauses([14 * D], 0, 15 * D) == [[7 * D, 14 * D]]


def test_ongoing_pause_ends_now_and_counts_from_the_last_ack() -> None:
    assert dormancy_pauses([3 * D], 0, 12 * D) == [[10 * D, 12 * D]]


def test_acks_before_the_league_start_do_not_count() -> None:
    assert dormancy_pauses([-D], 0, 8 * D) == [[7 * D, 8 * D]]


def test_unknown_start_gives_no_pause() -> None:
    assert dormancy_pauses([], None, 30 * D) == []


def test_clip_keeps_overlaps_only() -> None:
    assert clip([[1, 3], [5, 20], [30, 40]], [2, 10]) == [[2, 3], [5, 10]]
    assert clip([[1, 3]], [2]) == []


def test_ack_times_merge_journal_and_file(tmp_path: Path) -> None:
    f = tmp_path / "ack"
    f.touch()
    os.utime(f, (500, 500))
    events = [
        {"type": "operator_ack", "payload": {"ack_ts": 100}},
        {"type": "operator_ack", "payload": {"ack_ts": True}},
        {"type": "alert", "payload": {"ack_ts": 200}},
    ]
    assert ack_times(events, f) == [100, 500]
    assert ack_times(events, tmp_path / "missing") == [100]
