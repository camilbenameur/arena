"""Doublures déterministes pour les tests du cycle : marché synthétique, clients factices, décideurs factices.

Aucun réseau. Le marché est une fonction pure de (symbole, ts) : même appel, même barre. Les krachs sont des
décalages de niveau (en pour-mille) à partir d'un ts, avec un gap à l'ouverture de la première barre touchée.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

from arene.cycle import Clients
from arene.data.binance import DayBar
from arene.data.kraken import PairInfo
from arene.deciders.llm import DecisionResult, parse_decision
from arene.paths import REPO, Paths
from arene.types import Bar, Quote

H4 = 14_400
DAY = 86_400
T0 = 20_400 * DAY  # début de jour UTC, multiple de 4 h
SYMBOLS = ("BTC/EUR", "ETH/EUR", "SOL/EUR", "XRP/EUR", "LINK/EUR", "LTC/EUR")
BASES = {
    "BTC/EUR": 60_000_000_000,
    "ETH/EUR": 2_500_000_000,
    "SOL/EUR": 150_000_000,
    "XRP/EUR": 500_000,
    "LINK/EUR": 12_000_000,
    "LTC/EUR": 80_000_000,
}
PAIR_INFO = {
    "XBTEUR": PairInfo("XBTEUR", 100_000, 6_000, 450_000),
    "ETHEUR": PairInfo("ETHEUR", 10_000, 200_000, 450_000),
    "SOLEUR": PairInfo("SOLEUR", 10_000, 5_000_000, 450_000),
    "XRPEUR": PairInfo("XRPEUR", 10, 400_000_000, 450_000),
    "LINKEUR": PairInfo("LINKEUR", 10, 35_000_000, 450_000),
    "LTCEUR": PairInfo("LTCEUR", 10_000, 8_000_000, 450_000),
}


class Clock:
    def __init__(self, now: int = T0) -> None:
        self.now = now


def _h(sym: str, k: int) -> int:
    return (k * 2_654_435_761 + sum(map(ord, sym)) * 40_503) % 2**32


class FakeKraken:
    """Même interface que KrakenClient : asset_pairs, ohlc (barres closes seulement), ticker."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.crashes: list[tuple[str, int, int]] = []  # (symbole ou "*", à partir du ts, facteur en pour-mille)
        self.fail_ticker = False
        self.lag_s = 0  # retard de publication simulé (barres closes masquées)

    def crash(self, symbol: str, from_ts: int, permille: int) -> None:
        self.crashes.append((symbol, from_ts, permille))

    def _level(self, sym: str, ts: int) -> int:
        lvl = 1000
        for s, frm, f in self.crashes:
            if s in (sym, "*") and ts >= frm:
                lvl = lvl * f // 1000
        return lvl

    def _raw_close(self, sym: str, k: int) -> int:
        wiggle = (_h(sym, k) % 201) - 100  # +-1 % autour de la base, sans dérive
        return BASES[sym] * (10_000 + wiggle) // 10_000

    def bar(self, sym: str, ts: int) -> Bar:
        k = ts // H4
        lvl = self._level(sym, ts)
        o, c = self._raw_close(sym, k - 1) * lvl // 1000, self._raw_close(sym, k) * lvl // 1000
        hi, lo = max(o, c) * 1003 // 1000, min(o, c) * 997 // 1000
        vol = (1 + _h(sym, k + 7) % 9) * 100_000_000
        return Bar(sym, H4, ts, o, hi, lo, c, vol)

    def asset_pairs(self, pairs: list[str]) -> dict[str, PairInfo]:
        return {p: PAIR_INFO[p] for p in pairs}

    def minute_bar(self, sym: str, ts: int) -> Bar:
        """Bougie d'une minute : plate au dernier cours de clôture 4 h (même niveau que le ticker). Surchargeable."""
        c = self.bar(sym, ts // H4 * H4 - H4).close
        return Bar(sym, 60, ts, c, c, c, c, 1_000_000)

    def ohlc(self, symbol: str, pair: str, interval_s: int = H4, since: int | None = None) -> list[Bar]:
        if interval_s == 60:  # bougies 1 min closes, ts > since (comme Kraken)
            last = self.clock.now // 60 * 60 - 60
            lo = last - 60 * 60 * 12 if since is None else since // 60 * 60 + 60
            return [self.minute_bar(symbol, ts) for ts in range(max(lo, T0 - 20 * DAY), last + 1, 60)]
        last = (self.clock.now - self.lag_s) // H4 * H4 - H4  # dernière barre close
        first = T0 - 20 * DAY
        lo = first if since is None else max(first, since // H4 * H4 + H4)
        return [self.bar(symbol, ts) for ts in range(lo, last + 1, H4)]

    def ticker(self, symbol: str, pair: str) -> Quote:
        if self.fail_ticker:
            raise RuntimeError("ticker en panne (test)")
        last = self.clock.now // H4 * H4 - H4
        c = self.bar(symbol, last).close
        return Quote(symbol, self.clock.now, c * 9_995 // 10_000, c * 10_005 // 10_000)


class FakeBinance:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def klines_1d(self, binance_symbol: str, since: int | None = None, limit: int = 1000) -> list[DayBar]:
        out = []
        last = self.clock.now // DAY * DAY - DAY
        first = T0 - 60 * DAY
        lo = first if since is None else max(first, since // DAY * DAY)
        for ts in range(lo, last + 1, DAY):
            k = ts // DAY
            vol = (1000 + _h(binance_symbol, k) % 500) * 100_000_000
            taker = vol * (40 + _h(binance_symbol, k + 3) % 25) // 100
            out.append(DayBar(binance_symbol, ts, 1_000_000, vol, taker))
        return out[-limit:]


class Env:
    """Une arène de test : répertoires temporaires, marché factice, transport HTTP enregistré."""

    def __init__(self, root: Path, secrets: dict[str, str] | None = None) -> None:
        self.root = root
        self.sec = root / "secrets"
        self.sec.mkdir(parents=True, exist_ok=True)
        for k, v in (secrets or {}).items():
            (self.sec / k).write_text(v)
        # Copie de la config réelle en mode "api" : un test ne doit jamais lancer `claude -p` sur l'abonnement.
        cfg_text = (REPO / "config" / "arene.toml").read_text()
        test_cfg = root / "arene-test.toml"
        test_cfg.write_text(cfg_text.replace('decider_backend = "abonnement"', 'decider_backend = "api"'))
        self.paths = Paths(
            var=root / "var", secrets=self.sec, user_kill=root / "user_KILL",
            config=test_cfg, policy=REPO / "config" / "policy.toml",
        )  # fmt: skip
        self.clock = Clock()
        self.kraken = FakeKraken(self.clock)
        self.binance = FakeBinance(self.clock)
        self.requests: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            self.requests.append(req)
            return httpx.Response(200, text="OK")

        self.http = httpx.Client(transport=httpx.MockTransport(handler))
        self.clients = Clients(self.kraken, self.binance, self.http)

    @staticmethod
    def now_of(i: int) -> int:
        return T0 + i * H4 + 300

    def events(self) -> list[dict]:
        from arene.journal import Journal

        return Journal(self.paths.journal).events()

    def of_type(self, *types: str) -> list[dict]:
        return [e for e in self.events() if e["type"] in types]


# ---------------------------------------------------------------- décideurs factices

Plan = Callable[[int, dict], "list[dict] | str | None"]


def action(symbol: str, side: str = "buy", size: int = 10, stop: int = 5, move: int = 5) -> dict:
    a: dict[str, Any] = {"symbol": symbol, "side": side, "size_pct": size, "horizon_h": 24, "confidence_pct": 60}
    if side == "buy":
        a.update(stop_pct=stop, expected_move_pct=move)
    else:
        a.update(stop_pct=None, expected_move_pct=None)
    return a


class ScriptedDecider:
    """Décideur factice : `plan(index_du_cycle, snapshot)` renvoie des actions, une chaîne brute, ou None."""

    def __init__(self, model: str, portfolio: str, plan: Plan, model_returned: str | None = None) -> None:
        self.model, self.portfolio, self.plan, self.model_returned = model, portfolio, plan, model_returned
        self.calls = 0

    def decide(self, snapshot: dict, spent_today_uusd: int) -> DecisionResult:
        self.calls += 1
        idx = (snapshot["cycle_ts"] - T0) // H4
        out = self.plan(idx, snapshot)
        raw = out if isinstance(out, str) else json.dumps({"actions": out or [], "justification": f"cycle {idx}"})
        parsed, err, intents = parse_decision(raw, self.portfolio, snapshot["cycle_ts"])
        return DecisionResult(
            raw_text=raw, parsed=parsed, parse_error=err, intents=intents,
            model_returned=self.model_returned or self.model,
            input_tokens=1000, output_tokens=200, cost_uusd=1500, latency_ms=10,
        )  # fmt: skip


class NoKeyDecider:
    def __init__(self, model: str, portfolio: str) -> None:
        self.model, self.portfolio = model, portfolio
        self._key_reader = lambda: None

    def decide(self, snapshot: dict, spent_today_uusd: int) -> DecisionResult:
        return DecisionResult(skipped_reason="no_key")


HAIKU = "llm:claude-haiku-5-5"
SONNET = "llm:claude-sonnet-5-5"
OPUS = "llm:claude-opus-5-5"


def default_plan(idx: int, snap: dict) -> list[dict] | None:
    if idx % 4 == 1:
        return [action(SYMBOLS[(idx // 4) % 6])]
    if idx % 4 == 3:
        return [action(SYMBOLS[((idx - 2) // 4) % 6], "sell", 100)]
    return None


def make_deciders(haiku_plan: Plan = default_plan) -> dict[str, Any]:
    """Haiku : plan scripté ; Sonnet : JSON invalide ; Opus : pas de clé."""
    return {
        HAIKU: ScriptedDecider("claude-haiku-5-5", HAIKU, haiku_plan),
        SONNET: ScriptedDecider("claude-sonnet-5-5", SONNET, lambda i, s: "ceci n'est pas du JSON {"),
        OPUS: NoKeyDecider("claude-opus-5-5", OPUS),
    }


def fake_anthropic_client(text: str, model: str) -> Callable[[str], Any]:
    """client_factory pour un vrai LLMDecider : renvoie toujours `text`, annonce le modèle `model`."""

    def factory(api_key: str) -> Any:
        def create(**kw: Any) -> Any:
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=text)],
                usage=SimpleNamespace(input_tokens=2000, output_tokens=300),
                model=model,
                stop_reason="end_turn",
            )

        return SimpleNamespace(messages=SimpleNamespace(create=create))

    return factory
