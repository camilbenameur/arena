"""Loading of the numeric criteria (`criteria.yaml`) and firewall constants.

`criteria.yaml` is authoritative. The `Criteria` object is frozen: its sections are read-only views,
accessible by key (`c.costs_bp["spot_per_rotation"]`) or by attribute (`c.costs_bp.spot_per_rotation`).
Costs are integers in basis points; any float in their place is refused.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
CRITERIA_PATH = REPO / "research" / "criteria.yaml"
ARENA_TOML = REPO / "config" / "arena.toml"

#: 2026-07-01T00:00:00Z. Nothing equal or later enters the research; `known_at` > CUTOFF_TS is refused.
CUTOFF_TS = 1_782_864_000
#: Last month (year, month) allowed for download.
LAST_MONTH = (2026, 6)


class CutoffError(Exception):
    """Data later than the cutoff (2026-07-01T00:00:00Z) was requested or encountered."""


class CriteriaError(Exception):
    """`criteria.yaml` is invalid, inconsistent or different from the frozen version."""


#: sha256 of `research/criteria.yaml` at git tag `research-protocol-v1`
#: (`git show research-protocol-v1:research/criteria.yaml | sha256sum`). A test rereads the tag and compares.
SHA256_CRITERIA_V1 = "1402cfed6cb220eaf8c788d989899be3e2f8cb0a5dcc2be7e5dd737a2cf3b6f9"
TAG_PROTOCOL = "research-protocol-v1"


def verify_criteria(criteria: Criteria, expected: str = SHA256_CRITERIA_V1) -> None:
    """Raise `CriteriaError` if the sha256 of `criteria` is not that of the file frozen at tag
    `research-protocol-v1`. To be called before any trial: `run_wave` (before every trial), the
    CLI `verify` command, and the engine's `run_trial`."""
    if criteria.sha256 != expected:
        raise CriteriaError(
            f"criteria.yaml modified: sha256 {criteria.sha256[:16]}... instead of {expected[:16]}... "
            f"(version frozen at tag {TAG_PROTOCOL}); no trial is launched")


class Section(Mapping):
    """Read-only view of a YAML section: keys AND attributes, recursive."""

    __slots__ = ("_d",)

    def __init__(self, d: Mapping[str, Any]):
        object.__setattr__(self, "_d", {k: _freeze(v) for k, v in d.items()})

    def __getitem__(self, k):
        return self._d[k]

    def __iter__(self):
        return iter(self._d)

    def __len__(self):
        return len(self._d)

    def __getattr__(self, k):
        try:
            return self._d[k]
        except KeyError:
            raise AttributeError(k) from None

    def __setattr__(self, k, v):
        raise AttributeError("Section is read-only")

    def __repr__(self):
        return f"Section({self._d!r})"

    def to_dict(self) -> dict:
        return {k: (v.to_dict() if isinstance(v, Section) else list(v) if isinstance(v, tuple) else v)
                for k, v in self._d.items()}


def _freeze(v):
    if isinstance(v, Mapping):
        return Section(v)
    if isinstance(v, list):
        return tuple(_freeze(x) for x in v)
    return v


def _integer_bp(name: str, v) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise CriteriaError(f"{name} must be an integer in basis points, got {v!r}")
    if v < 0:
        raise CriteriaError(f"{name} must be >= 0")
    return v


def _ts(iso: str) -> int:
    return int(datetime.fromisoformat(iso).astimezone(UTC).timestamp())


@dataclass(frozen=True)
class Criteria:
    sha256: str
    version: str
    cutoff_ts: int
    universe: tuple[str, ...]
    arena_universe: tuple[str, ...]
    control_size: int
    spot_cost_bp: int
    perp_cost_bp: int
    stress_multiplier: int
    perp_share_margin: float
    n_dsr: int
    total_cap: int
    wave_1_cap: int
    trial_timeout_s: int
    data: Section
    costs_bp: Section
    classes: Section
    trials: Section
    dsr: Section
    gates: Section
    consistency: Section
    selection: Section
    paper: Section
    execution: Section

    def cost_bp(self, leg: str, stress: bool = False) -> int:
        """Cost per unit of rotation, in whole bp (`leg`: "spot" or "perp")."""
        base = {"spot": self.spot_cost_bp, "perp": self.perp_cost_bp}[leg]
        return base * (self.stress_multiplier if stress else 1)


def load_criteria(path: Path | str = CRITERIA_PATH) -> Criteria:
    raw_bytes = Path(path).read_bytes()
    raw = yaml.safe_load(raw_bytes)
    if not isinstance(raw, dict):
        raise CriteriaError("criteria.yaml: mapping expected at the root")
    try:
        data_sec, costs_sec, trials_sec = raw["data"], raw["costs_bp"], raw["trials"]
        cutoff = _ts(data_sec["cutoff_excluded"])
        if cutoff != CUTOFF_TS:
            raise CriteriaError(f"cutoff_excluded ({cutoff}) differs from CUTOFF_TS ({CUTOFF_TS})")
        universe = tuple(data_sec["universe"])
        arena = tuple(data_sec["arena_universe"])
        if len(set(universe)) != len(universe) or not set(arena) <= set(universe):
            raise CriteriaError("universe: duplicates or arena_universe outside universe")
        spot = _integer_bp("costs_bp.spot_per_rotation", costs_sec["spot_per_rotation"])
        perp = _integer_bp("costs_bp.perp_per_rotation", costs_sec["perp_per_rotation"])
        stress = _integer_bp("costs_bp.stress_multiplier", costs_sec["stress_multiplier"])
        return Criteria(
            sha256=hashlib.sha256(raw_bytes).hexdigest(),
            version=str(raw["version"]),
            cutoff_ts=cutoff,
            universe=universe,
            arena_universe=arena,
            control_size=int(data_sec["control_universe"]["size"]),
            spot_cost_bp=spot,
            perp_cost_bp=perp,
            stress_multiplier=stress,
            perp_share_margin=float(costs_sec["perp_share_margin"]),
            n_dsr=int(trials_sec["N_dsr"]),
            total_cap=int(trials_sec["total_cap"]),
            wave_1_cap=int(trials_sec["wave_1_cap"]),
            trial_timeout_s=int(raw["execution"]["trial_timeout_s"]),
            data=Section(data_sec),
            costs_bp=Section(costs_sec),
            classes=Section(raw["classes"]),
            trials=Section(trials_sec),
            dsr=Section(raw["dsr"]),
            gates=Section(raw["gates"]),
            consistency=Section(raw["consistency"]),
            selection=Section(raw["selection"]),
            paper=Section(raw["paper"]),
            execution=Section(raw["execution"]),
        )
    except KeyError as e:
        raise CriteriaError(f"criteria.yaml: missing key {e}") from None
