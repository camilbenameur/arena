"""Contrats partagés de l'arène. Tous les modules s'appuient sur ces types.

Règles d'unités (non négociables, voir docs/SPEC-MVP.md §2) :
- Cash et prix en EUR, stockés en entiers de micro-euros (1 EUR = 1_000_000 µEUR).
- Quantités d'actif de base en entiers d'unités minimales : 1 unité = 10**-8 de l'actif (QTY_SCALE).
- Aucun float dans le chemin de l'argent. Les floats ne servent qu'aux statistiques et à l'affichage.
- Arrondis toujours défavorables au portefeuille : frais arrondis vers le haut, produit d'une vente
  vers le bas, coût d'un achat vers le haut.
- Horodatages : entiers en secondes Unix UTC (ts) ; les chaînes ISO 8601 ne servent qu'à l'affichage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

MICRO = 1_000_000  # µEUR par EUR
QTY_SCALE = 100_000_000  # unités minimales par unité d'actif de base

VenueMode = Literal["live", "paper", "backtest", "synthetic"]


def ceil_div(a: int, b: int) -> int:
    """Division entière arrondie vers le haut (b > 0)."""
    return -((-a) // b)


def notional_ueur(qty: int, price_ueur: int, *, round_up: bool) -> int:
    """Valeur en µEUR de `qty` unités minimales au prix `price_ueur` (µEUR par unité entière d'actif)."""
    num = qty * price_ueur
    return ceil_div(num, QTY_SCALE) if round_up else num // QTY_SCALE


@dataclass(frozen=True)
class Instrument:
    symbol: str  # forme canonique "BTC/EUR"
    kraken_pair: str  # ex. "XBTEUR" (altname Kraken)
    binance_symbol: str  # ex. "BTCUSDT", sert seulement au signal du témoin E0065
    tick_ueur: int  # pas de prix en µEUR
    lot_min_qty: int  # quantité minimale d'ordre (unités minimales)
    cost_min_ueur: int  # notional minimal d'ordre (µEUR)


@dataclass(frozen=True)
class Bar:
    """Barre OHLCV close. ts = début de la barre (UTC, secondes). Prix en µEUR, volume en unités minimales."""

    symbol: str
    interval_s: int
    ts: int
    open: int
    high: int
    low: int
    close: int
    volume: int


@dataclass(frozen=True)
class Quote:
    """Meilleur prix au moment de l'exécution simulée."""

    symbol: str
    ts: int
    bid: int
    ask: int


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Intent:
    """Intention émise par un décideur (modèle ou témoin). Jamais un ordre : riskd la valide d'abord.

    size_bp : taille en points de base (1/10 000) de l'equity du portefeuille pour un achat,
              ou de la position détenue pour une vente (10_000 = tout vendre).
    stop_bp : distance du stop sous le prix d'entrée, en points de base (achats seulement).
    """

    intent_id: str  # sha256 hex de la forme canonique (portfolio, cycle, index, contenu)
    portfolio: str  # ex. "llm:claude-sonnet-5-5", "temoin:panier"
    cycle: int  # ts du cycle de décision
    symbol: str
    side: Side
    size_bp: int
    stop_bp: int | None = None
    horizon_h: int | None = None
    expected_move_bp: int | None = None
    confidence_pct: int | None = None


class OrderState(StrEnum):
    INTENT = "INTENT"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    SUBMITTING = "SUBMITTING"
    ACKED = "ACKED"
    UNKNOWN = "UNKNOWN"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELED = "CANCELED"


@dataclass(frozen=True)
class Verdict:
    intent_id: str
    approved: bool
    reasons: tuple[str, ...]  # codes de règle stables, ex. "MAX_ORDER_SIZE", "DAILY_TRADES"
    qty: int = 0  # quantité approuvée (unités minimales), 0 si rejet
    reserved_ueur: int = 0  # notional réservé (achat) ou attendu (vente)
    policy_sha256: str = ""


@dataclass(frozen=True)
class Fill:
    order_id: str  # = intent_id pour une entrée ; "stop:<intent_id>" ou "exit:<...>" pour une sortie
    portfolio: str
    symbol: str
    side: Side
    qty: int
    price_ueur: int
    fee_ueur: int
    ts: int
    venue_mode: VenueMode
    fill_model_version: str
    reason: str = "intent"  # "intent" | "stop" | "max_holding" | "kill_switch"


@dataclass
class Position:
    symbol: str
    qty: int
    cost_ueur: int  # coût total d'acquisition frais inclus (coût moyen pondéré)
    opened_ts: int
    stop_ueur: int | None = None


@dataclass
class PortfolioState:
    portfolio: str
    cash_ueur: int
    positions: dict[str, Position] = field(default_factory=dict)
    fees_paid_ueur: int = 0
    realized_pnl_ueur: int = 0
    frozen_until_ts: int = 0
    halted: bool = False  # arrêt (drawdown) : revue humaine requise
