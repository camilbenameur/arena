"""Risk policy of the perp league: loading and consistency checks of config/policy-perp.toml.

The policy is a frozen dataclass of integers (plus the instrument whitelist). The sha256 of the file bytes is
kept to be journaled and copied into every verdict. Any inconsistency raises `PerpPolicyError`.
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from arene.paths import REPO

DEFAULT_POLICY = REPO / "config" / "policy-perp.toml"
BP = 10_000


class PerpPolicyError(ValueError):
    """Missing, unreadable or inconsistent perp policy."""


@dataclass(frozen=True)
class PerpPolicy:
    instruments: tuple[str, ...]
    max_order_bp: int
    max_position_bp: int
    max_leverage_bp: int
    stop_bp_min: int
    stop_bp_max: int
    max_trade_loss_bp: int
    max_open_risk_bp: int
    stop_gap_bp: int
    max_cost_to_expected_move_pct: int
    max_funding_horizon_h: int
    max_expected_move_bp: int
    funding_extreme_e12: int
    max_opens_per_day: int
    max_orders_per_minute: int
    min_interval_same_open_s: int
    monthly_fee_budget_bp: int
    daily_loss_freeze_bp: int
    freeze_duration_s: int
    drawdown_halt_bp: int
    max_mark_index_bp: int
    max_mid_index_bp: int
    max_mid_mark_bp: int
    max_spread_multiple: int
    max_data_age_s: int
    min_order_ueur: int
    sha256: str = ""


_INTS = tuple(f.name for f in fields(PerpPolicy) if f.name not in ("instruments", "sha256"))


def validate(p: PerpPolicy) -> None:
    for name in _INTS:
        v = getattr(p, name)
        if type(v) is not int or v <= 0:
            raise PerpPolicyError(f"{name} must be a positive integer")
    if not p.instruments or len(set(p.instruments)) != len(p.instruments):
        raise PerpPolicyError("instruments must be a non-empty list without duplicates")
    if any(not isinstance(i, str) or not i.startswith("PF_") for i in p.instruments):
        raise PerpPolicyError("only linear perpetuals (PF_*) are allowed")
    if not p.max_order_bp <= p.max_position_bp <= p.max_leverage_bp:
        raise PerpPolicyError("need max_order_bp <= max_position_bp <= max_leverage_bp")
    if p.max_leverage_bp > 2 * BP:
        raise PerpPolicyError("max_leverage_bp above 20000 (2x): the hard cap of decision D2")
    if not p.stop_bp_min < p.stop_bp_max < BP:
        raise PerpPolicyError("need stop_bp_min < stop_bp_max < 10000")
    if not p.max_trade_loss_bp <= p.max_open_risk_bp:
        raise PerpPolicyError("need max_trade_loss_bp <= max_open_risk_bp")
    if not p.max_trade_loss_bp < p.daily_loss_freeze_bp:
        raise PerpPolicyError(
            "one stopped trade must not freeze the portfolio: max_trade_loss_bp < daily_loss_freeze_bp"
        )
    if not 2 * p.max_open_risk_bp <= p.drawdown_halt_bp:
        raise PerpPolicyError(
            "all stops together must stay under half the halt: 2 x max_open_risk_bp <= drawdown_halt_bp"
        )
    for name in (
        "daily_loss_freeze_bp",
        "drawdown_halt_bp",
        "monthly_fee_budget_bp",
        "max_mark_index_bp",
        "max_mid_index_bp",
    ):
        if getattr(p, name) >= BP:
            raise PerpPolicyError(f"{name} must be < 10000")
    if not p.daily_loss_freeze_bp < p.drawdown_halt_bp:
        raise PerpPolicyError("the freeze must come before the halt: daily_loss_freeze_bp < drawdown_halt_bp")
    bounds = {
        "max_cost_to_expected_move_pct": 50,
        "max_data_age_s": 900,
        "max_spread_multiple": 10,
        "max_funding_horizon_h": 168,
        "funding_extreme_e12": 500_000_000,
        "max_expected_move_bp": 5000,
        "stop_gap_bp": 1000,
        "max_mid_mark_bp": 200,
        "max_opens_per_day": 24,
        "max_orders_per_minute": 60,
        "monthly_fee_budget_bp": 1000,
        "min_order_ueur": 100_000_000,
    }
    for name, hi in bounds.items():
        if getattr(p, name) > hi:
            raise PerpPolicyError(f"{name} above its sane bound {hi}")
    if p.stop_bp_max + p.stop_gap_bp >= BP:
        raise PerpPolicyError("stop_bp_max + stop_gap_bp must be < 10000")


def load_perp_policy(path: str | Path = DEFAULT_POLICY) -> PerpPolicy:
    pth = Path(path)
    try:
        raw = pth.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise PerpPolicyError(f"unreadable perp policy {pth}: {exc}") from exc
    expected = set(_INTS) | {"instruments"}
    missing, unknown = sorted(expected - data.keys()), sorted(data.keys() - expected)
    if missing:
        raise PerpPolicyError(f"missing keys: {', '.join(missing)}")
    if unknown:
        raise PerpPolicyError(f"unknown keys: {', '.join(unknown)}")
    if not isinstance(data["instruments"], list):
        raise PerpPolicyError("instruments must be a list")
    pol = PerpPolicy(
        instruments=tuple(data["instruments"]),
        sha256=hashlib.sha256(raw).hexdigest(),
        **{k: data[k] for k in _INTS},
    )
    validate(pol)
    return pol
