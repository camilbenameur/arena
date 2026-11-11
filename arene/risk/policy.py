"""Chargement et vérification de cohérence de config/policy.toml (docs/SPEC-MVP.md §7).

La politique est une dataclass gelée, uniquement des entiers (et la liste blanche de symboles).
Le hash sha256 du fichier (octets bruts) est conservé pour être journalisé et recopié dans les verdicts.
Toute incohérence lève `PolicyError` : l'arène refuse de démarrer.
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


class PolicyError(ValueError):
    """Politique absente, illisible ou incohérente."""


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
    sha256: str = ""  # hash du fichier ; non lu dans le TOML


_INT_FIELDS = tuple(f.name for f in fields(Policy) if f.name not in ("symbols", "sha256"))


def _is_int(value: object) -> bool:
    # bool est une sous-classe de int : on l'exclut explicitement.
    return type(value) is int


def validate_policy(policy: Policy) -> None:
    """Vérifie la cohérence ; lève PolicyError au premier défaut (message en clair)."""
    # Types : entiers stricts (pas de float, pas de bool).
    for name in _INT_FIELDS:
        if not _is_int(getattr(policy, name)):
            raise PolicyError(f"{name} doit être un entier")

    # Liste blanche : non vide, chaînes non vides, sans doublon.
    if not isinstance(policy.symbols, tuple) or not policy.symbols:
        raise PolicyError("symbols ne doit pas être vide")
    for s in policy.symbols:
        if not isinstance(s, str) or not s.strip() or s != s.strip():
            raise PolicyError(f"symbole invalide : {s!r}")
    if len(set(policy.symbols)) != len(policy.symbols):
        raise PolicyError("symbols contient un doublon")

    # Toutes les valeurs sont strictement positives.
    for name in _INT_FIELDS:
        if getattr(policy, name) <= 0:
            raise PolicyError(f"{name} doit être > 0")

    # Bornes en points de base.
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
            raise PolicyError(f"{name} doit être <= 10000")
    if policy.max_cost_to_expected_move_pct > 100:
        raise PolicyError("max_cost_to_expected_move_pct doit être <= 100")

    # Hiérarchie des plafonds.
    if not (policy.max_order_bp <= policy.max_position_bp <= policy.max_exposure_bp <= 10_000):
        raise PolicyError("il faut max_order_bp <= max_position_bp <= max_exposure_bp <= 10000")

    # Stop : min < max, et un stop >= 100 % n'aurait pas de sens.
    if not (policy.stop_bp_min < policy.stop_bp_max):
        raise PolicyError("il faut stop_bp_min < stop_bp_max")
    if policy.stop_bp_max >= 10_000:
        raise PolicyError("stop_bp_max doit être < 10000")


def load_policy(path: str | Path) -> Policy:
    """Lit et valide le fichier TOML ; renvoie la politique gelée avec le sha256 du fichier."""
    p = Path(path)
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise PolicyError(f"politique illisible : {p} ({exc})") from exc
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise PolicyError(f"TOML invalide dans {p} : {exc}") from exc

    expected = {f.name for f in fields(Policy)} - {"sha256"}
    missing = sorted(expected - data.keys())
    if missing:
        raise PolicyError(f"clés manquantes : {', '.join(missing)}")
    unknown = sorted(data.keys() - expected)
    if unknown:
        raise PolicyError(f"clés inconnues : {', '.join(unknown)}")

    symbols = data["symbols"]
    if not isinstance(symbols, list):
        raise PolicyError("symbols doit être une liste")
    kwargs = {name: data[name] for name in _INT_FIELDS}
    policy = Policy(symbols=tuple(symbols), sha256=hashlib.sha256(raw).hexdigest(), **kwargs)
    validate_policy(policy)
    return policy
