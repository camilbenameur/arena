"""Typed loading of config/arena.toml, instruments enriched from AssetPairs, file hash."""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass, fields
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from arena.types import MICRO, Instrument, VenueMode

if TYPE_CHECKING:
    from arena.data.kraken import KrakenClient, PairInfo

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "arena.toml"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class InstrumentRef:
    """Instrument as declared in the file (before enrichment from AssetPairs)."""

    symbol: str
    kraken_pair: str
    binance_symbol: str


@dataclass(frozen=True)
class ModelConfig:
    portfolio: str
    model: str
    daily_budget_uusd: int  # micro-dollars per day
    price_in_uusd_per_mtok: int  # micro-dollars per million input tokens
    price_out_uusd_per_mtok: int


@dataclass(frozen=True)
class E0065Params:
    L: int
    k: int
    H: int


@dataclass(frozen=True)
class BenchmarksConfig:
    portfolios: tuple[str, ...]
    e0065: E0065Params
    random_paths: int


@dataclass(frozen=True)
class WatchConfig:
    """Table [watch] (docs/WATCH.md §2): watch tick, triggers and wake-up guard rails."""

    tick_s: int = 300
    move_threshold_bp: int = 300
    move_window_s: int = 3600
    cooldown_s: int = 3600
    max_wakeups_per_day: int = 6
    pre_cycle_guard_s: int = 1800


@dataclass(frozen=True)
class SeasonConfig:
    """Table [season] (optional): a frozen season of `duration_days` days, starting at the cycle of `start_ts`."""

    number: int
    name: str
    start_ts: int  # execution time of the start cycle (HH:05 UTC); the decision cycle is start_ts - cycle_delay_s
    duration_days: int


@dataclass(frozen=True)
class Config:
    venue_mode: VenueMode
    capital_ueur: int
    interval_s: int
    cycle_delay_s: int
    fill_model_version: str
    taker_fee_bp: int
    slippage_bp: int
    instrument_refs: tuple[InstrumentRef, ...]
    models: tuple[ModelConfig, ...]
    benchmarks: BenchmarksConfig
    sha256: str  # hash of the raw file (journaled in config_loaded)
    decider_backend: str = "api"  # "api" (Console key) or "subscription" (claude -p)
    watch: WatchConfig = WatchConfig()
    season: SeasonConfig | None = None
    sha256_outside_season: str = ""  # hash of the file without the [season] table (basis of the season freeze)

    def enrich(self, pairs: dict[str, PairInfo]) -> tuple[Instrument, ...]:
        """Full instruments (tick, minimum order, minimum cost) built from `KrakenClient.asset_pairs`."""
        out = []
        for ref in self.instrument_refs:
            info = pairs.get(ref.kraken_pair)
            if info is None:
                raise ConfigError(f"pair missing from AssetPairs: {ref.kraken_pair}")
            out.append(
                Instrument(
                    symbol=ref.symbol,
                    kraken_pair=ref.kraken_pair,
                    binance_symbol=ref.binance_symbol,
                    tick_ueur=info.tick_ueur,
                    lot_min_qty=info.lot_min_qty,
                    cost_min_ueur=info.cost_min_ueur,
                )
            )
        return tuple(out)


def _micro(x: float | str) -> int:
    """Decimal amount from the file (e.g. $0.10) -> micro-units, exact via Decimal(str(x))."""
    d = Decimal(str(x)) * MICRO
    if d != d.to_integral_value():
        raise ConfigError(f"value not representable in micro-units: {x!r}")
    return int(d)


def sha256_outside_season(raw: bytes) -> str:
    """sha256 of the config WITHOUT the `season` key: the TOML is parsed (`tomllib`), the `season` key is removed, then the
    rest is serialised to canonical JSON (sorted keys, no spaces). Comments, whitespace and key order therefore have
    no effect; any value that changes (a number included) changes the hash."""
    t = tomllib.loads(raw.decode("utf-8"))
    t.pop("season", None)
    return hashlib.sha256(json.dumps(t, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _season(raw: object) -> SeasonConfig | None:
    """Optional [season] table: without it, nothing changes."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise TypeError("[season] must be a table")
    need = {"number", "name", "start_ts", "duration_days"}
    if set(raw) != need:
        raise ValueError(f"[season] must contain exactly {sorted(need)}")
    for k in ("number", "start_ts", "duration_days"):
        if isinstance(raw[k], bool) or not isinstance(raw[k], int):
            raise TypeError(f"[season] {k} must be an integer, got {raw[k]!r}")
    if not isinstance(raw["name"], str) or not raw["name"].strip():
        raise TypeError("[season] name must be a non-empty string")
    if raw["number"] < 1 or raw["start_ts"] <= 0 or raw["duration_days"] < 1:
        raise ValueError("[season] number >= 1, start_ts > 0 and duration_days >= 1 are required")
    return SeasonConfig(raw["number"], raw["name"], raw["start_ts"], raw["duration_days"])


def _watch(raw: object) -> WatchConfig:
    """Optional [watch] table: defaults for missing keys; strict integers, bounds checked."""
    if raw is None:
        return WatchConfig()
    if not isinstance(raw, dict):
        raise TypeError("[watch] must be a table")
    known = {f.name for f in fields(WatchConfig)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"[watch] unknown keys: {sorted(unknown)}")
    vals = {}
    for k, v in raw.items():
        if isinstance(v, bool) or not isinstance(v, int):
            raise TypeError(f"[watch] {k} must be an integer, got {v!r}")
        vals[k] = v
    out = WatchConfig(**vals)
    for k in ("tick_s", "move_threshold_bp", "move_window_s", "cooldown_s"):
        if getattr(out, k) <= 0:
            raise ValueError(f"[watch] {k} must be > 0")
    if out.max_wakeups_per_day < 0 or out.pre_cycle_guard_s < 0:
        raise ValueError("[watch] max_wakeups_per_day and pre_cycle_guard_s must be >= 0")
    if out.move_window_s % out.tick_s:
        raise ValueError("[watch] move_window_s must be a multiple of tick_s")
    return out


def load_config(path: Path | str = DEFAULT_PATH) -> Config:
    raw = Path(path).read_bytes()
    try:
        t = tomllib.loads(raw.decode("utf-8"))
        bench = t["benchmarks"]
        cfg = Config(
            venue_mode=t["venue_mode"],
            capital_ueur=_micro(t["capital_eur"]),
            interval_s=int(t["interval_s"]),
            cycle_delay_s=int(t["cycle_delay_s"]),
            fill_model_version=t["fill_model_version"],
            taker_fee_bp=int(t["taker_fee_bp"]),
            slippage_bp=int(t["slippage_bp"]),
            decider_backend=str(t.get("decider_backend", "api")),
            watch=_watch(t.get("watch")),
            season=_season(t.get("season")),
            sha256_outside_season=sha256_outside_season(raw),
            instrument_refs=tuple(
                InstrumentRef(i["symbol"], i["kraken_pair"], i["binance_symbol"]) for i in t["instruments"]
            ),
            models=tuple(
                ModelConfig(
                    portfolio=m["portfolio"],
                    model=m["model"],
                    daily_budget_uusd=_micro(m["daily_budget_usd"]),
                    price_in_uusd_per_mtok=_micro(m["price_in_usd_per_mtok"]),
                    price_out_uusd_per_mtok=_micro(m["price_out_usd_per_mtok"]),
                )
                for m in t["models"]
            ),
            benchmarks=BenchmarksConfig(
                portfolios=tuple(bench["portfolios"]),
                e0065=E0065Params(**{k: int(v) for k, v in bench["e0065"].items()}),
                random_paths=int(bench["random_paths"]),
            ),
            sha256=hashlib.sha256(raw).hexdigest(),
        )
    except (KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"invalid config ({path}): {exc!r}") from exc
    if cfg.interval_s % cfg.watch.tick_s:
        raise ConfigError("[watch] tick_s must divide interval_s")
    if cfg.decider_backend not in ("api", "subscription"):
        raise ConfigError("decider_backend must be 'api' or 'subscription'")
    if cfg.venue_mode != "paper":
        raise ConfigError("MVP: venue_mode must be 'paper'")
    return cfg


PAIRS_CACHE_S = 86_400


def load_instruments(
    cfg: Config, client: KrakenClient, *, cache: Path | None = None, now: int | None = None
) -> tuple[Instrument, ...]:
    """Reloads AssetPairs (to be done at startup) and returns the enriched instruments.

    With `cache` (a JSON file in var/) and `now`, the response is reused for 24 h as long as the list of pairs is
    the same; if the call fails, a stale cache is used as a fallback (pair parameters change very rarely).
    """
    from arena.data.kraken import PairInfo  # late import: avoids an import cycle

    pairs_wanted = [r.kraken_pair for r in cfg.instrument_refs]
    data = None
    if cache is not None and now is not None:
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("pairs") != pairs_wanted:
                data = None
        except (OSError, ValueError):
            data = None
        if data is not None and now - int(data["ts"]) < PAIRS_CACHE_S:
            return cfg.enrich({k: PairInfo(**v) for k, v in data["info"].items()})
    try:
        info = client.asset_pairs(pairs_wanted)
    except Exception:
        if data is None:
            raise
        return cfg.enrich({k: PairInfo(**v) for k, v in data["info"].items()})  # fallback: stale cache
    if cache is not None and now is not None:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(
                json.dumps({"ts": now, "pairs": pairs_wanted, "info": {k: v.__dict__ for k, v in info.items()}}),
                encoding="utf-8",
            )
        except OSError:
            pass
    return cfg.enrich(info)
