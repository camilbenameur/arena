"""Loading and consistency checking of config/policy.toml (docs/SPEC-MVP.md §7).

The policy is a frozen dataclass holding only integers (and the symbol whitelist).
The sha256 hash of the file (raw bytes) is kept so it can be journaled and copied into the verdicts.
Any inconsistency raises `PolicyError`: the arena refuses to start.
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


class PolicyError(ValueError):
    """Policy missing, unreadable or inconsistent."""


@dataclass(frozen=True)
class Policy:
    symbols: tuple[str, ...]
    max_order_bp: int
    max_position_bp: int
    max_exposure_bp: int
    max_trades_per_day: int
    max_orders_per_minute: int
    min_interval_same_symbol_s: int
    stop_bp_min: int
    stop_bp_max: int
    max_cost_to_expected_move_pct: int
    max_holding_s: int
    daily_loss_freeze_bp: int
    freeze_duration_s: int
    drawdown_halt_bp: int
    monthly_fee_budget_bp: int
    max_quote_deviation_bp: int
    max_spread_multiple: int
    min_order_ueur: int
    sha256: str = ""  # file hash; not read from the TOML


_INT_FIELDS = tuple(f.name for f in fields(Policy) if f.name not in ("symbols", "sha256"))


def _is_int(value: object) -> bool:
    # bool is a subclass of int: it is excluded explicitly.
    return type(value) is int


def validate_policy(policy: Policy) -> None:
    """Check consistency; raises PolicyError at the first defect (plain-language message)."""
    # Types: strict integers (no float, no bool).
    for name in _INT_FIELDS:
        if not _is_int(getattr(policy, name)):
            raise PolicyError(f"{name} must be an integer")

    # Whitelist: non-empty, non-empty strings, no duplicates.
    if not isinstance(policy.symbols, tuple) or not policy.symbols:
        raise PolicyError("symbols must not be empty")
    for s in policy.symbols:
        if not isinstance(s, str) or not s.strip() or s != s.strip():
            raise PolicyError(f"invalid symbol: {s!r}")
    if len(set(policy.symbols)) != len(policy.symbols):
        raise PolicyError("symbols contains a duplicate")

    # All values are strictly positive.
    for name in _INT_FIELDS:
        if getattr(policy, name) <= 0:
            raise PolicyError(f"{name} must be > 0")

    # Bounds in basis points.
    for name in (
        "max_order_bp",
        "max_position_bp",
        "max_exposure_bp",
        "daily_loss_freeze_bp",
        "drawdown_halt_bp",
        "monthly_fee_budget_bp",
        "max_quote_deviation_bp",
    ):
        if getattr(policy, name) > 10_000:
            raise PolicyError(f"{name} must be <= 10000")
    if policy.max_cost_to_expected_move_pct > 100:
        raise PolicyError("max_cost_to_expected_move_pct must be <= 100")

    # Hierarchy of the caps.
    if not (policy.max_order_bp <= policy.max_position_bp <= policy.max_exposure_bp <= 10_000):
        raise PolicyError("max_order_bp <= max_position_bp <= max_exposure_bp <= 10000 is required")

    # Stop: min < max, and a stop >= 100% would make no sense.
    if not (policy.stop_bp_min < policy.stop_bp_max):
        raise PolicyError("stop_bp_min < stop_bp_max is required")
    if policy.stop_bp_max >= 10_000:
        raise PolicyError("stop_bp_max must be < 10000")


def load_policy(path: str | Path) -> Policy:
    """Read and validate the TOML file; returns the frozen policy with the file's sha256."""
    p = Path(path)
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise PolicyError(f"policy unreadable: {p} ({exc})") from exc
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise PolicyError(f"invalid TOML in {p}: {exc}") from exc

    expected = {f.name for f in fields(Policy)} - {"sha256"}
    missing = sorted(expected - data.keys())
    if missing:
        raise PolicyError(f"missing keys: {', '.join(missing)}")
    unknown = sorted(data.keys() - expected)
    if unknown:
        raise PolicyError(f"unknown keys: {', '.join(unknown)}")

    symbols = data["symbols"]
    if not isinstance(symbols, list):
        raise PolicyError("symbols must be a list")
    kwargs = {name: data[name] for name in _INT_FIELDS}
    policy = Policy(symbols=tuple(symbols), sha256=hashlib.sha256(raw).hexdigest(), **kwargs)
    validate_policy(policy)
    return policy
