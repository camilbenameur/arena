"""Chargement typé de config/arene.toml, instruments enrichis par AssetPairs, hash du fichier."""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass, fields
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
class VeilleConfig:
    """Table [veille] (docs/VEILLE.md §2) : tick de la veille, déclencheurs et garde-fous des réveils."""

    tick_s: int = 300
    seuil_mouvement_bp: int = 300
    fenetre_mouvement_s: int = 3600
    cooldown_s: int = 3600
    max_reveils_jour: int = 6
    garde_avant_cycle_s: int = 1800


@dataclass(frozen=True)
class SaisonConfig:
    """Table [saison] (facultative) : une saison gelée de `duree_jours` jours, qui débute au cycle de `debut_ts`."""

    numero: int
    nom: str
    debut_ts: int  # instant d'exécution du cycle de début (HH:05 UTC) ; le cycle de décision est debut_ts - cycle_delay_s
    duree_jours: int


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
    veille: VeilleConfig = VeilleConfig()
    saison: SaisonConfig | None = None
    sha256_hors_saison: str = ""  # hash du fichier sans la table [saison] (base du gel de saison)

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


def sha256_hors_saison(raw: bytes) -> str:
    """sha256 de la config SANS la clé `saison` : le TOML est parsé (`tomllib`), la clé `saison` est retirée, puis le
    reste est sérialisé en JSON canonique (clés triées, sans espaces). Les commentaires, les espaces et l'ordre des
    clés n'ont donc aucun effet ; toute valeur (y compris un nombre) qui change modifie le hash."""
    t = tomllib.loads(raw.decode("utf-8"))
    t.pop("saison", None)
    return hashlib.sha256(json.dumps(t, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _saison(raw: object) -> SaisonConfig | None:
    """Table [saison] facultative : sans elle, rien ne change."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise TypeError("[saison] doit être une table")
    need = {"numero", "nom", "debut_ts", "duree_jours"}
    if set(raw) != need:
        raise ValueError(f"[saison] doit contenir exactement {sorted(need)}")
    for k in ("numero", "debut_ts", "duree_jours"):
        if isinstance(raw[k], bool) or not isinstance(raw[k], int):
            raise TypeError(f"[saison] {k} doit être un entier, reçu {raw[k]!r}")
    if not isinstance(raw["nom"], str) or not raw["nom"].strip():
        raise TypeError("[saison] nom doit être un texte non vide")
    if raw["numero"] < 1 or raw["debut_ts"] <= 0 or raw["duree_jours"] < 1:
        raise ValueError("[saison] numero >= 1, debut_ts > 0 et duree_jours >= 1 sont requis")
    return SaisonConfig(raw["numero"], raw["nom"], raw["debut_ts"], raw["duree_jours"])


def _veille(raw: object) -> VeilleConfig:
    """Table [veille] facultative : valeurs par défaut pour les clés absentes ; entiers stricts, bornes vérifiées."""
    if raw is None:
        return VeilleConfig()
    if not isinstance(raw, dict):
        raise TypeError("[veille] doit être une table")
    known = {f.name for f in fields(VeilleConfig)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"[veille] clés inconnues : {sorted(unknown)}")
    vals = {}
    for k, v in raw.items():
        if isinstance(v, bool) or not isinstance(v, int):
            raise TypeError(f"[veille] {k} doit être un entier, reçu {v!r}")
        vals[k] = v
    out = VeilleConfig(**vals)
    for k in ("tick_s", "seuil_mouvement_bp", "fenetre_mouvement_s", "cooldown_s"):
        if getattr(out, k) <= 0:
            raise ValueError(f"[veille] {k} doit être > 0")
    if out.max_reveils_jour < 0 or out.garde_avant_cycle_s < 0:
        raise ValueError("[veille] max_reveils_jour et garde_avant_cycle_s doivent être >= 0")
    if out.fenetre_mouvement_s % out.tick_s:
        raise ValueError("[veille] fenetre_mouvement_s doit être un multiple de tick_s")
    return out


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
            veille=_veille(t.get("veille")),
            saison=_saison(t.get("saison")),
            sha256_hors_saison=sha256_hors_saison(raw),
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
    if cfg.interval_s % cfg.veille.tick_s:
        raise ConfigError("[veille] tick_s doit diviser interval_s")
    if cfg.decider_backend not in ("api", "abonnement"):
        raise ConfigError("decider_backend doit valoir 'api' ou 'abonnement'")
    if cfg.venue_mode != "paper":
        raise ConfigError("MVP : venue_mode doit être 'paper'")
    return cfg


PAIRS_CACHE_S = 86_400


def load_instruments(
    cfg: Config, client: KrakenClient, *, cache: Path | None = None, now: int | None = None
) -> tuple[Instrument, ...]:
    """Recharge AssetPairs (à faire au démarrage) et renvoie les instruments enrichis.

    Avec `cache` (fichier JSON dans var/) et `now`, la réponse est réutilisée 24 h tant que la liste des paires est
    la même ; si l'appel échoue, un cache périmé sert de repli (les paramètres de paire changent très rarement).
    """
    from arene.data.kraken import PairInfo  # import tardif : évite un cycle d'import

    pairs_wanted = [r.kraken_pair for r in cfg.instrument_refs]
    data = None
    if cache is not None and now is not None:
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("paires") != pairs_wanted:
                data = None
        except (OSError, ValueError):
            data = None
        if data is not None and now - int(data["ts"]) < PAIRS_CACHE_S:
            return cfg.enrich({k: PairInfo(**v) for k, v in data["infos"].items()})
    try:
        infos = client.asset_pairs(pairs_wanted)
    except Exception:
        if data is None:
            raise
        return cfg.enrich({k: PairInfo(**v) for k, v in data["infos"].items()})  # repli : cache périmé
    if cache is not None and now is not None:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(
                json.dumps({"ts": now, "paires": pairs_wanted, "infos": {k: v.__dict__ for k, v in infos.items()}}),
                encoding="utf-8",
            )
        except OSError:
            pass
    return cfg.enrich(infos)
