"""Réglages communs : fsync désactivé (le disque de the host le rend ~50x plus lent) ; le journal reste correct."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _no_fsync(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "fsync", lambda fd: None)
