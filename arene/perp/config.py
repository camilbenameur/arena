"""Loading and validation of config/perp.toml. Any inconsistency raises `PerpConfigError`."""

from __future__ import annotations

import hashlib
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from arene.perp.kraken_futures import RESOLUTIONS
from arene.perp.sim import FILL_MODEL_VERSION, SimParams
from arene.perp.types import CANDLE_KINDS, PerpInstrument

REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG = REPO / "config" / "perp.toml"
DEFAULT_VAR = REPO / "var-perp"


class PerpConfigError(ValueError):
    """Missing, unreadable or inconsistent perp configuration."""


@dataclass(frozen=True)
class PerpConfig:
    venue_mode: str
    data_source: str
    candle_interval_s: int
    candle_kinds: tuple[str, ...]
    open_interest_interval_s: int
    book_depth: int
    backfill_s: int
    run_deadline_s: int
    max_backfill_s: int
    funding_retry_s: int
    fx_pair: str
    instruments: tuple[PerpInstrument, ...]
    simulation: SimParams = field(default_factory=SimParams)
    sha256: str = ""


_INTS = (
    "candle_interval_s",
    "open_interest_interval_s",
    "book_depth",
    "backfill_s",
    "run_deadline_s",
    "max_backfill_s",
    "funding_retry_s",
)


def load_perp_config(path: str | Path = DEFAULT_CONFIG) -> PerpConfig:
    p = Path(path)
    try:
        raw = p.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise PerpConfigError(f"unreadable perp config {p}: {exc}") from exc

    expected = set(_INTS) | {
        "venue_mode",
        "data_source",
        "candle_kinds",
        "fx_pair",
        "instruments",
        "simulation",
    }
    missing, unknown = sorted(expected - data.keys()), sorted(data.keys() - expected)
    if missing:
        raise PerpConfigError(f"missing keys: {', '.join(missing)}")
    if unknown:
        raise PerpConfigError(f"unknown keys: {', '.join(unknown)}")
    if data["venue_mode"] != "paper":
        raise PerpConfigError("venue_mode must be 'paper'")
    if data["data_source"] != "kraken_futures":
        raise PerpConfigError("data_source must be 'kraken_futures'")
    for k in _INTS:
        if type(data[k]) is not int or data[k] <= 0:
            raise PerpConfigError(f"{k} must be a positive integer")
    if data["candle_interval_s"] not in RESOLUTIONS:
        raise PerpConfigError(f"candle_interval_s not offered by Kraken: {data['candle_interval_s']}")
    if data["open_interest_interval_s"] not in RESOLUTIONS:
        raise PerpConfigError("open_interest_interval_s not offered by Kraken")
    if data["backfill_s"] > data["max_backfill_s"]:
        raise PerpConfigError("backfill_s must be <= max_backfill_s")
    kinds = data["candle_kinds"]
    if (
        not isinstance(kinds, list)
        or not kinds
        or any(k not in CANDLE_KINDS for k in kinds)
        or len(set(kinds)) != len(kinds)
    ):
        raise PerpConfigError(f"candle_kinds must be a non-empty subset of {CANDLE_KINDS}")
    if not isinstance(data["fx_pair"], str) or not data["fx_pair"]:
        raise PerpConfigError("fx_pair must be a non-empty string")

    rows = data["instruments"]
    if not isinstance(rows, list) or not rows:
        raise PerpConfigError("instruments must be a non-empty list")
    insts = []
    for row in rows:
        if set(row) != {"symbol", "kraken_symbol", "spot_symbol"} or not all(
            isinstance(v, str) and v for v in row.values()
        ):
            raise PerpConfigError(f"instrument needs exactly symbol, kraken_symbol, spot_symbol: {row!r}")
        if not row["kraken_symbol"].startswith("PF_"):
            raise PerpConfigError(f"only linear perpetuals (PF_*) are allowed: {row['kraken_symbol']}")
        insts.append(PerpInstrument(**row))
    for attr in ("symbol", "kraken_symbol", "spot_symbol"):
        values = [getattr(i, attr) for i in insts]
        if len(set(values)) != len(values):
            raise PerpConfigError(f"duplicate {attr} in instruments")

    simulation = _simulation(data["simulation"])

    return PerpConfig(
        venue_mode=data["venue_mode"],
        data_source=data["data_source"],
        candle_kinds=tuple(kinds),
        fx_pair=data["fx_pair"],
        instruments=tuple(insts),
        simulation=simulation,
        sha256=hashlib.sha256(raw).hexdigest(),
        **{k: data[k] for k in _INTS},
    )


_SIM_KEYS = {
    "fill_model_version",
    "capital_eur",
    "taker_fee_bp",
    "slippage_bp",
    "liquidation_fee_bp",
    "closeout_margin_bp",
    "initial_margin_bp",
    "max_holding_s",
}


def _simulation(table: object) -> SimParams:
    if not isinstance(table, dict) or set(table) != _SIM_KEYS:
        raise PerpConfigError(f"[simulation] needs exactly the keys {sorted(_SIM_KEYS)}")
    if table["fill_model_version"] != FILL_MODEL_VERSION:
        raise PerpConfigError(f"[simulation] fill_model_version must be {FILL_MODEL_VERSION!r}")
    for k in _SIM_KEYS - {"fill_model_version"}:
        if type(table[k]) is not int:
            raise PerpConfigError(f"[simulation] {k} must be an integer")
    if table["capital_eur"] <= 0:
        raise PerpConfigError("[simulation] capital_eur must be > 0")
    try:
        return SimParams(
            taker_fee_bp=table["taker_fee_bp"],
            slippage_bp=table["slippage_bp"],
            liquidation_fee_bp=table["liquidation_fee_bp"],
            closeout_margin_bp=table["closeout_margin_bp"],
            initial_margin_bp=table["initial_margin_bp"],
            max_holding_s=table["max_holding_s"],
            capital_ueur=table["capital_eur"] * 1_000_000,
        )
    except ValueError as exc:
        raise PerpConfigError(f"[simulation] {exc}") from exc


def default_var() -> Path:
    """State directory of the perp league: $ARENE_PERP_VAR, else `var-perp/` at the repository root."""
    return Path(os.environ.get("ARENE_PERP_VAR") or DEFAULT_VAR)
