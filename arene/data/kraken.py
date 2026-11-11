"""API publique Kraken : OHLC 4 h, Ticker, AssetPairs (aucune clé, aucun compte).

Les prix et volumes sont convertis par `Decimal` (jamais float). Les prix de marché sont arrondis au
µEUR avec ROUND_HALF_EVEN : ce sont des DONNÉES de marché, pas des montants de portefeuille.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from arene.data import (
    DataError,
    RateLimitedHttp,
    TransientDataError,
    to_exact_scaled,
    to_qty,
    to_ueur,
)
from arene.types import MICRO, QTY_SCALE, Bar, Quote

BASE_URL = "https://api.kraken.com"
_TRANSIENT_PREFIXES = ("EService:", "EAPI:Rate limit", "EGeneral:Temporary lockout")


class KrakenError(DataError):
    """Champ "error" non vide dans la réponse Kraken."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("Kraken: " + "; ".join(errors))
        self.errors = errors


class KrakenTransientError(KrakenError, TransientDataError):
    """Erreur Kraken passagère (service indisponible, limite de débit) : relancée par le client."""


def _check_errors(payload: Any) -> None:
    errors = payload.get("error") if isinstance(payload, dict) else ["réponse inattendue"]
    if errors:
        if all(str(e).startswith(_TRANSIENT_PREFIXES) for e in errors):
            raise KrakenTransientError(list(map(str, errors)))
        raise KrakenError(list(map(str, errors)))


@dataclass(frozen=True)
class PairInfo:
    """Paramètres d'une paire (AssetPairs), en entiers : tick en µEUR, ordermin en 1e-8, costmin en µEUR."""

    altname: str
    tick_ueur: int
    lot_min_qty: int
    cost_min_ueur: int


class KrakenClient:
    def __init__(
        self,
        http: RateLimitedHttp | None = None,
        *,
        base_url: str = BASE_URL,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._http = http or RateLimitedHttp()
        self._base = base_url.rstrip("/")
        self._now = now

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = self._http.get_json(f"{self._base}/0/public/{endpoint}", params, retry_if=_check_errors)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise DataError(f"Kraken {endpoint}: résultat absent")
        return result

    def ohlc(self, instrument_symbol: str, kraken_pair: str, interval_s: int = 14400, since: int | None = None) -> list[Bar]:
        """Barres closes seulement, triées par ts (ts = début de barre).

        La barre en cours (dernière renvoyée, ts + interval_s > maintenant) est exclue.
        """
        params: dict[str, Any] = {"pair": kraken_pair, "interval": interval_s // 60}
        if since is not None:
            params["since"] = since
        result = self._get("OHLC", params)
        keys = [k for k in result if k != "last"]
        if len(keys) != 1:
            raise DataError(f"Kraken OHLC: {len(keys)} paires renvoyées pour {kraken_pair}")
        now = int(self._now())
        bars: list[Bar] = []
        for row in result[keys[0]]:
            ts = int(row[0])
            if ts + interval_s > now:  # barre en cours
                continue
            bars.append(
                Bar(
                    symbol=instrument_symbol,
                    interval_s=interval_s,
                    ts=ts,
                    open=to_ueur(row[1]),
                    high=to_ueur(row[2]),
                    low=to_ueur(row[3]),
                    close=to_ueur(row[4]),
                    volume=to_qty(row[6]),
                )
            )
        bars.sort(key=lambda b: b.ts)
        return bars

    def ticker(self, instrument_symbol: str, kraken_pair: str) -> Quote:
        """Meilleur ask (a[0]) et bid (b[0]) -> Quote, ts = heure de la requête."""
        result = self._get("Ticker", {"pair": kraken_pair})
        if len(result) != 1:
            raise DataError(f"Kraken Ticker: {len(result)} paires renvoyées pour {kraken_pair}")
        t = next(iter(result.values()))
        return Quote(symbol=instrument_symbol, ts=int(self._now()), bid=to_ueur(t["b"][0]), ask=to_ueur(t["a"][0]))

    def asset_pairs(self, kraken_pairs: list[str]) -> dict[str, PairInfo]:
        """Paramètres des paires, indexés par altname (ex. "XBTEUR")."""
        result = self._get("AssetPairs", {"pair": ",".join(kraken_pairs)})
        out: dict[str, PairInfo] = {}
        for info in result.values():
            tick = info.get("tick_size")
            if tick is None:
                tick = str(Decimal(1).scaleb(-int(info["pair_decimals"])))
            out[info["altname"]] = PairInfo(
                altname=info["altname"],
                tick_ueur=to_exact_scaled(tick, MICRO),
                lot_min_qty=to_exact_scaled(info["ordermin"], QTY_SCALE),
                cost_min_ueur=to_exact_scaled(info["costmin"], MICRO),
            )
        missing = set(kraken_pairs) - set(out)
        if missing:
            raise DataError(f"Kraken AssetPairs: paires absentes {sorted(missing)}")
        return out
