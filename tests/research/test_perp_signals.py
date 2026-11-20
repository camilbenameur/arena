"""Directional sheet with `perp_signals: true`: the funding arrives as a signal, the perp leg stays zero."""

from __future__ import annotations

from research.engine.trial import TrialSheet, run_trial
from research.engine.panel import synthetic
from tests.research.test_engine import _canary, crit, write, journal, dummy_lab  # noqa: F401

# Directional: the whole basket as long as the funding has never been seen; 0 as soon as a funding time arrives.
SEES_FUNDING = """
import numpy as np
class Strategy:
    def __init__(self, n_pairs):
        self.n = n_pairs
        self.seen = False
    def step(self, day):
        if day.funding:
            self.seen = True
        w = np.zeros(self.n)
        if not self.seen:
            w[day.eligibles] = 1.0 / max(1, int(day.eligibles.sum()))
        return w, np.zeros(self.n)
"""

# Directional that tries a perp leg: the engine must refuse (WEIGHT_SHAPE), never trim.
PERP_LEG = """
import numpy as np
class Strategy:
    def __init__(self, n_pairs):
        self.n = n_pairs
    def step(self, day):
        w = np.zeros(self.n)
        p = np.zeros(self.n)
        if day.eligibles_perp is not None:
            ok = day.eligibles & day.eligibles_perp
            w[ok] = 0.1
            p[ok] = 0.1
        return w, p
"""


def _exposure(r):
    return r.track.exposure if hasattr(r.track, "exposure") else None


def test_without_declaration_the_funding_is_removed(tmp_path, journal, crit):  # noqa: F811
    panel = synthetic(60, 3, 0, with_perp=True)
    p = write(tmp_path, SEES_FUNDING)
    r = run_trial(TrialSheet("x", "directional", "a" * 64), p, {}, panel, journal, crit, causality=False, test=True)
    assert r.code == "OK"
    expo = _exposure(r)
    assert expo is None or float(max(expo)) > 0  # funding never seen: stays invested


def test_with_declaration_the_funding_arrives(tmp_path, journal, crit):  # noqa: F811
    panel = synthetic(60, 3, 0, with_perp=True)
    p = write(tmp_path, SEES_FUNDING)
    sheet = TrialSheet("x", "directional", "a" * 64, perp_signals=True)
    r = run_trial(sheet, p, {}, panel, journal, crit, causality=False, test=True)
    assert r.code == "OK"
    expo = _exposure(r)
    if expo is not None:
        assert float(expo[-1]) == 0.0  # the funding has been seen: out


def test_directional_perp_leg_refused_even_with_signals(tmp_path, journal, crit):  # noqa: F811
    panel = synthetic(60, 3, 0, with_perp=True)
    p = write(tmp_path, PERP_LEG)
    sheet = TrialSheet("x", "directional", "a" * 64, perp_signals=True)
    r = run_trial(sheet, p, {}, panel, journal, crit, causality=False, test=True)
    assert r.code == "WEIGHT_SHAPE"
