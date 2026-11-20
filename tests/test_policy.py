"""Tests of arena/risk/policy.py: loading, hash, consistency, inconsistent policy -> PolicyError."""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path

import pytest

from arena.risk.policy import Policy, PolicyError, load_policy, validate_policy

REPO = Path(__file__).resolve().parent.parent
POLICY_TOML = REPO / "config" / "policy.toml"


@pytest.fixture(scope="module")
def policy() -> Policy:
    return load_policy(POLICY_TOML)


def test_real_config_values_match_the_spec(policy: Policy) -> None:
    assert policy.symbols == ("BTC/EUR", "ETH/EUR", "SOL/EUR", "XRP/EUR", "LINK/EUR", "LTC/EUR")
    assert policy.max_order_bp == 2000
    assert policy.max_position_bp == 4000
    assert policy.max_exposure_bp == 10000
    assert policy.max_trades_per_day == 2
    assert policy.max_orders_per_minute == 20
    assert policy.min_interval_same_symbol_s == 14400
    assert (policy.stop_bp_min, policy.stop_bp_max) == (100, 2500)
    assert policy.max_cost_to_expected_move_pct == 33
    assert policy.max_holding_s == 604800
    assert policy.daily_loss_freeze_bp == 500
    assert policy.freeze_duration_s == 86400
    assert policy.drawdown_halt_bp == 2000
    assert policy.monthly_fee_budget_bp == 100
    assert policy.max_quote_deviation_bp == 300
    assert policy.max_spread_multiple == 3
    assert policy.min_order_ueur == 5_000_000


def test_real_config_consistent(policy: Policy) -> None:
    validate_policy(policy)  # does not raise
    assert policy.max_order_bp <= policy.max_position_bp <= policy.max_exposure_bp <= 10_000
    assert 0 < policy.stop_bp_min < policy.stop_bp_max


def test_hash_is_that_of_the_file(policy: Policy) -> None:
    assert policy.sha256 == hashlib.sha256(POLICY_TOML.read_bytes()).hexdigest()


def test_policy_frozen_and_integers_only(policy: Policy) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.max_order_bp = 1  # type: ignore[misc]
    for f in dataclasses.fields(Policy):
        v = getattr(policy, f.name)
        assert not isinstance(v, float)
        if f.name not in ("symbols", "sha256"):
            assert type(v) is int


def test_hash_changes_if_the_file_changes(tmp_path: Path) -> None:
    text = POLICY_TOML.read_text(encoding="utf-8")
    a, b = tmp_path / "a.toml", tmp_path / "b.toml"
    a.write_text(text, encoding="utf-8")
    b.write_text(text + "\n# comment\n", encoding="utf-8")
    assert load_policy(a).sha256 != load_policy(b).sha256


def _write(tmp_path: Path, **overrides: str | None) -> Path:
    """Copy the real policy, replacing `key = ...` (whole line); None removes the key."""
    lines = []
    for line in POLICY_TOML.read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in overrides:
            if overrides[key] is not None:
                lines.append(f"{key} = {overrides[key]}")
            continue
        lines.append(line)
    out = tmp_path / "policy.toml"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def test_write_helper_identical_without_override(tmp_path: Path, policy: Policy) -> None:
    assert dataclasses.replace(load_policy(_write(tmp_path)), sha256="") == dataclasses.replace(
        policy, sha256=""
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_order_bp": "4001"},  # order > position
        {"max_position_bp": "10001", "max_exposure_bp": "10001"},  # > 10000
        {"max_position_bp": "1999"},  # position < order
        {"max_exposure_bp": "3999"},  # exposure < position
        {"stop_bp_min": "2500"},  # min == max
        {"stop_bp_min": "2600"},  # min > max
        {"stop_bp_max": "10000"},  # stop >= 100%
        {"max_order_bp": "0"},
        {"max_order_bp": "-5"},
        {"max_trades_per_day": "0"},
        {"max_orders_per_minute": "0"},
        {"min_interval_same_symbol_s": "0"},
        {"max_holding_s": "0"},
        {"daily_loss_freeze_bp": "0"},
        {"daily_loss_freeze_bp": "10001"},
        {"freeze_duration_s": "0"},
        {"drawdown_halt_bp": "0"},
        {"drawdown_halt_bp": "10001"},
        {"monthly_fee_budget_bp": "0"},
        {"max_quote_deviation_bp": "0"},
        {"max_spread_multiple": "0"},
        {"min_order_ueur": "0"},
        {"max_cost_to_expected_move_pct": "0"},
        {"max_cost_to_expected_move_pct": "101"},
        {"max_order_bp": "20.5"},  # float refused
        {"max_order_bp": "true"},  # bool refused
        {"max_order_bp": '"2000"'},  # string refused
        {"symbols": "[]"},
        {"symbols": '["BTC/EUR", "BTC/EUR"]'},
        {"symbols": '["BTC/EUR", ""]'},
        {"symbols": '["BTC/EUR", " ETH/EUR"]'},
        {"symbols": '["BTC/EUR", 3]'},
        {"symbols": '"BTC/EUR"'},
        {"max_order_bp": None},  # missing key
        {"symbols": None},
        {"min_order_ueur": None},
    ],
    ids=lambda o: ",".join(f"{k}={v}" for k, v in o.items()),
)
def test_inconsistent_policy_raises_policy_error(tmp_path: Path, overrides: dict[str, str | None]) -> None:
    with pytest.raises(PolicyError):
        load_policy(_write(tmp_path, **overrides))


def test_unknown_key_refused(tmp_path: Path) -> None:
    path = _write(tmp_path)
    path.write_text(path.read_text(encoding="utf-8") + "leverage_max = 3\n", encoding="utf-8")
    with pytest.raises(PolicyError):
        load_policy(path)


def test_missing_file_or_invalid_toml(tmp_path: Path) -> None:
    with pytest.raises(PolicyError):
        load_policy(tmp_path / "absent.toml")
    bad = tmp_path / "bad.toml"
    bad.write_text("this is not = = toml [", encoding="utf-8")
    with pytest.raises(PolicyError):
        load_policy(bad)
    binary = tmp_path / "bin.toml"
    binary.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(PolicyError):
        load_policy(binary)


def test_limit_values_accepted(tmp_path: Path) -> None:
    ok = load_policy(
        _write(
            tmp_path,
            max_order_bp="4000",  # == position
            max_position_bp="4000",
            max_exposure_bp="4000",  # == position
            stop_bp_min="2499",
            stop_bp_max="2500",
        )
    )
    assert ok.max_order_bp == ok.max_position_bp == ok.max_exposure_bp == 4000
    assert ok.stop_bp_max - ok.stop_bp_min == 1


def test_validate_policy_on_built_dataclass(policy: Policy) -> None:
    validate_policy(dataclasses.replace(policy, max_order_bp=policy.max_position_bp))
    with pytest.raises(PolicyError):
        validate_policy(dataclasses.replace(policy, max_order_bp=policy.max_position_bp + 1))
    with pytest.raises(PolicyError):
        validate_policy(dataclasses.replace(policy, max_order_bp=2000.0))  # type: ignore[arg-type]
