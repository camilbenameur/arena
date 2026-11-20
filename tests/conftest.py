"""Shared settings: fsync disabled (it makes the tests much slower on some disks); the journal stays correct."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _no_fsync(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "fsync", lambda fd: None)


@pytest.fixture(autouse=True)
def _never_real_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may call the real `claude` CLI (subscription): the binary is made unfindable."""
    monkeypatch.setattr("arena.deciders.llm._claude_bin", lambda: "/nonexistent/claude-forbidden-in-tests")
