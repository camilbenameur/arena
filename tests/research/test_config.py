import dataclasses
import hashlib
import tomllib
from datetime import UTC, datetime

import pytest

from research.config import (
    ARENA_TOML,
    CUTOFF_TS,
    CRITERIA_PATH,
    CriteriaError,
    load_criteria,
)


def test_cutoff_is_2026_07_01_utc():
    assert CUTOFF_TS == int(datetime(2026, 7, 1, tzinfo=UTC).timestamp())


def test_loads_real_criteria():
    c = load_criteria()
    assert c.sha256 == hashlib.sha256(CRITERIA_PATH.read_bytes()).hexdigest()
    assert c.version == "research-v1"
    assert c.cutoff_ts == CUTOFF_TS
    assert len(c.universe) == 15 and set(c.arena_universe) <= set(c.universe)
    assert c.control_size == 20
    assert (c.n_dsr, c.total_cap, c.wave_1_cap) == (726, 600, 120)
    assert c.gates.C6_drawdown_max.directional == 0.45
    assert c.gates["C8_directional"]["replications"] == 5000
    assert c.data.tolerances.max_consecutive_gaps_1h == 6


def test_costs_are_integer_basis_points():
    c = load_criteria()
    assert (c.spot_cost_bp, c.perp_cost_bp, c.stress_multiplier) == (60, 10, 2)
    assert all(type(v) is int for v in (c.spot_cost_bp, c.perp_cost_bp, c.stress_multiplier))
    assert c.cost_bp("spot") == 60 and c.cost_bp("perp", stress=True) == 20


def test_costs_match_arena_toml():
    arena = tomllib.loads(ARENA_TOML.read_text())
    c = load_criteria()
    assert c.spot_cost_bp == arena["taker_fee_bp"] + arena["slippage_bp"] + 5


def test_criteria_are_frozen():
    c = load_criteria()
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.spot_cost_bp = 1
    with pytest.raises(AttributeError):
        c.costs_bp.spot_per_rotation = 1
    with pytest.raises(TypeError):
        c.costs_bp["spot_per_rotation"] = 1


def test_float_cost_is_refused(tmp_path):
    text = CRITERIA_PATH.read_text().replace("spot_per_rotation: 60", "spot_per_rotation: 60.5")
    p = tmp_path / "c.yaml"
    p.write_text(text)
    with pytest.raises(CriteriaError):
        load_criteria(p)


def test_modified_cutoff_is_refused(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(CRITERIA_PATH.read_text().replace("2026-07-01T00:00:00Z", "2026-08-01T00:00:00Z", 1))
    with pytest.raises(CriteriaError):
        load_criteria(p)


def test_missing_key(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("version: x\n")
    with pytest.raises(CriteriaError):
        load_criteria(p)
