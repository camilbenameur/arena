"""Risk policy of the perp league: loading and consistency checks of config/policy-perp.toml.

The policy is a frozen dataclass of integers (plus the instrument whitelist and the profile). The sha256 of the
file bytes is kept to be journaled and copied into every verdict. Any inconsistency raises `PerpPolicyError`.

Two profiles. `standard` (the default, no `profile` key): the rules of decision D2, leverage capped at 2x.
`aggressive` (`profile = "aggressive"`, config/policy-perp-conseil.toml only, docs/SPEC-PERP-CONSEIL-HAIKU.md
§5): the Haiku council's own policy, leverage up to 10x with Kraken's margins, the daily freeze and the fee
budget may be off (0), no delay between two entries on the same contract (0). A paper demonstration outside
the retail 2x rule.
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from arene.paths import REPO

DEFAULT_POLICY = REPO / "config" / "policy-perp.toml"
BP = 10_000
STANDARD = "standard"
AGGRESSIVE = "aggressive"
# keys that may be 0 (off) in the aggressive profile
_OFF_ALLOWED = ("daily_loss_freeze_bp", "monthly_fee_budget_bp", "min_interval_same_open_s")


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
    profile: str = STANDARD


_INTS = tuple(f.name for f in fields(PerpPolicy) if f.name not in ("instruments", "sha256", "profile"))


def validate(p: PerpPolicy) -> None:
    if p.profile == AGGRESSIVE:
        _validate_aggressive(p)
        return
    if p.profile != STANDARD:
        raise PerpPolicyError(f"profile must be {STANDARD} or {AGGRESSIVE}")
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


def _validate_aggressive(p: PerpPolicy) -> None:
    """The council's policy: no cap of decision D2 on leverage (10x at most), but the same structure: every
    entry has a stop, the loss at the stops is bounded and stays under the halt."""
    for name in _INTS:
        v = getattr(p, name)
        if type(v) is not int or v < 0 or (v == 0 and name not in _OFF_ALLOWED):
            raise PerpPolicyError(
                f"{name} must be a positive integer" + (" or 0" if name in _OFF_ALLOWED else "")
            )
    if not p.instruments or len(set(p.instruments)) != len(p.instruments):
        raise PerpPolicyError("instruments must be a non-empty list without duplicates")
    if any(not isinstance(i, str) or not i.startswith("PF_") for i in p.instruments):
        raise PerpPolicyError("only linear perpetuals (PF_*) are allowed")
    if not p.max_order_bp <= p.max_position_bp <= p.max_leverage_bp:
        raise PerpPolicyError("need max_order_bp <= max_position_bp <= max_leverage_bp")
    if p.max_leverage_bp > 10 * BP:
        raise PerpPolicyError("max_leverage_bp above 100000 (10x): the cap of the aggressive profile")
    if not p.stop_bp_min < p.stop_bp_max < BP:
        raise PerpPolicyError("need stop_bp_min < stop_bp_max < 10000")
    if not p.max_trade_loss_bp <= p.max_open_risk_bp < p.drawdown_halt_bp:
        raise PerpPolicyError("need max_trade_loss_bp <= max_open_risk_bp < drawdown_halt_bp")
    if p.drawdown_halt_bp > 9500:
        raise PerpPolicyError("drawdown_halt_bp above 9500: the halt must come before the ruin")
    if p.daily_loss_freeze_bp and not p.max_trade_loss_bp < p.daily_loss_freeze_bp < p.drawdown_halt_bp:
        raise PerpPolicyError("a daily freeze must lie between max_trade_loss_bp and drawdown_halt_bp")
    for name in ("max_mark_index_bp", "max_mid_index_bp"):
        if getattr(p, name) >= BP:
            raise PerpPolicyError(f"{name} must be < 10000")
    bounds = {
        "max_cost_to_expected_move_pct": 50,
        "max_data_age_s": 900,
        "max_spread_multiple": 10,
        "max_funding_horizon_h": 168,
        "funding_extreme_e12": 500_000_000,
        "max_expected_move_bp": 5000,
        "stop_gap_bp": 1000,
        "max_mid_mark_bp": 200,
        "max_opens_per_day": 48,
        "max_orders_per_minute": 60,
        "monthly_fee_budget_bp": 1000,
        "min_order_ueur": 100_000_000,
        "freeze_duration_s": 86_400,
    }
    for name, hi in bounds.items():
        if getattr(p, name) > hi:
            raise PerpPolicyError(f"{name} above its sane bound {hi}")
    if p.stop_bp_max + p.stop_gap_bp >= BP:
        raise PerpPolicyError("stop_bp_max + stop_gap_bp must be < 10000")


def load_perp_policy(path: str | Path = DEFAULT_POLICY, *, profile: str = STANDARD) -> PerpPolicy:
    """`profile`: the profile the caller expects; the file must declare the same one (a standard policy can
    never be loaded where the aggressive one is expected, nor the reverse)."""
    pth = Path(path)
    try:
        raw = pth.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise PerpPolicyError(f"unreadable perp policy {pth}: {exc}") from exc
    declared = data.pop("profile", STANDARD)
    if declared != profile:
        raise PerpPolicyError(f"{pth}: profile {declared!r}, expected {profile!r}")
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
        profile=declared,
        **{k: data[k] for k in _INTS},
    )
    validate(pol)
    return pol
