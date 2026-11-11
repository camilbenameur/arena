"""Chargement typé de config/arene.toml, instruments enrichis par AssetPairs, hash du fichier."""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from arene.types import MICRO, Instrument, VenueMode

if TYPE_CHECKING:
    from arene.data.kraken import KrakenClient, PairInfo

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "arene.toml"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class InstrumentRef:
    """Instrument tel que déclaré dans le fichier (avant enrichissement par AssetPairs)."""

    symbol: str
    kraken_pair: str
    binance_symbol: str


@dataclass(frozen=True)
class ModelConfig:
    portfolio: str
    model: str
    daily_budget_uusd: int  # micro-dollars par jour
    price_in_uusd_per_mtok: int  # micro-dollars par million de tokens d'entrée
    price_out_uusd_per_mtok: int


@dataclass(frozen=True)
class E0065Params:
    L: int
    k: int
    H: int


@dataclass(frozen=True)
class TemoinsConfig:
    portfolios: tuple[str, ...]
    e0065: E0065Params
    aleatoire_trajectoires: int


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
    temoins: TemoinsConfig
    sha256: str  # hash du fichier brut (journalisé dans config_loaded)
    decider_backend: str = "api"  # "api" (clé Console) ou "abonnement" (claude -p)

    def enrich(self, pairs: dict[str, PairInfo]) -> tuple[Instrument, ...]:
        """Instruments complets (tick, ordre min, coût min) à partir de `KrakenClient.asset_pairs`."""
        out = []
        for ref in self.instrument_refs:
            info = pairs.get(ref.kraken_pair)
            if info is None:
                raise ConfigError(f"paire absente d'AssetPairs: {ref.kraken_pair}")
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
    """Montant décimal du fichier (ex. 0.10 $) -> micro-unités, exact via Decimal(str(x))."""
    d = Decimal(str(x)) * MICRO
    if d != d.to_integral_value():
        raise ConfigError(f"valeur non représentable en micro-unités: {x!r}")
    return int(d)


def load_config(path: Path | str = DEFAULT_PATH) -> Config:
    raw = Path(path).read_bytes()
    try:
        t = tomllib.loads(raw.decode("utf-8"))
        tem = t["temoins"]
        cfg = Config(
            venue_mode=t["venue_mode"],
            capital_ueur=_micro(t["capital_eur"]),
            interval_s=int(t["interval_s"]),
            cycle_delay_s=int(t["cycle_delay_s"]),
            fill_model_version=t["fill_model_version"],
            taker_fee_bp=int(t["taker_fee_bp"]),
            slippage_bp=int(t["slippage_bp"]),
            decider_backend=str(t.get("decider_backend", "api")),
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
            temoins=TemoinsConfig(
                portfolios=tuple(tem["portfolios"]),
                e0065=E0065Params(**{k: int(v) for k, v in tem["e0065"].items()}),
                aleatoire_trajectoires=int(tem["aleatoire_trajectoires"]),
            ),
            sha256=hashlib.sha256(raw).hexdigest(),
        )
    except (KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"config invalide ({path}): {exc!r}") from exc
    if cfg.decider_backend not in ("api", "abonnement"):
        raise ConfigError("decider_backend doit valoir 'api' ou 'abonnement'")
    if cfg.venue_mode != "paper":
        raise ConfigError("MVP : venue_mode doit être 'paper'")
    return cfg


def load_instruments(cfg: Config, client: KrakenClient) -> tuple[Instrument, ...]:
    """Recharge AssetPairs (à faire au démarrage) et renvoie les instruments enrichis."""
    return cfg.enrich(client.asset_pairs([r.kraken_pair for r in cfg.instrument_refs]))
