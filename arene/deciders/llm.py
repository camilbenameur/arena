"""Harnais des décideurs LLM (SPEC-MVP §9).

Un `LLMDecider` reçoit l'instantané du cycle, appelle l'API Anthropic (SDK officiel), valide la sortie
avec pydantic et la convertit en `Intent` (pourcentages -> points de base entiers). Aucune exécution ici :
riskd valide ensuite. Tout est renvoyé dans un `DecisionResult`, que le cycle journalise tel quel.

La clé n'est lue qu'à l'exécution (`$CREDENTIALS_DIRECTORY/anthropic_api_key`, sinon
`~/.config/arene/secrets/anthropic_api_key`) ; absente -> `skipped_reason="no_key"`, aucun appel.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Literal

import anthropic
from pydantic import BaseModel, ConfigDict, ValidationError, ValidationInfo, field_validator, model_validator

from arene.deciders.snapshot import canonical
from arene.types import Intent, Side

UNIVERSE = ("BTC/EUR", "ETH/EUR", "SOL/EUR", "XRP/EUR", "LINK/EUR", "LTC/EUR")
PROMPT_PATH = Path(__file__).parent / "prompt" / "v1.md"
MAX_TOKENS_CAP = 1500
DEFAULT_TIMEOUT_S = 120.0
MAX_RETRIES = 2  # 3 tentatives au total, sur erreur réseau / 5xx / 529 seulement
BACKOFF_S = (2.0, 6.0)
JUSTIFICATION_MAX = 1200
CHARS_PER_TOKEN_EST = 3  # estimation prudente pour le coût maximal avant appel

# Schéma demandé au SDK (sortie structurée). Les bornes sont vérifiées par pydantic, pas par le schéma.
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["actions", "justification"],
    "properties": {
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "symbol",
                    "side",
                    "size_pct",
                    "stop_pct",
                    "horizon_h",
                    "expected_move_pct",
                    "confidence_pct",
                ],
                "properties": {
                    "symbol": {"type": "string", "enum": list(UNIVERSE)},
                    "side": {"type": "string", "enum": ["buy", "sell"]},
                    "size_pct": {"type": "number"},
                    "stop_pct": {"type": ["number", "null"]},
                    "horizon_h": {"type": "integer"},
                    "expected_move_pct": {"type": ["number", "null"]},
                    "confidence_pct": {"type": "number"},
                },
            },
        },
        "justification": {"type": "string"},
    },
}


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def prompt_sha256() -> str:
    return hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()


def read_api_key(env: dict[str, str] | None = None, home: Path | None = None) -> str | None:
    """Lit la clé à l'exécution ; None si absente ou vide. Ne l'affiche ni ne la journalise jamais."""
    env = os.environ if env is None else env
    candidates = []
    cred_dir = env.get("CREDENTIALS_DIRECTORY")
    if cred_dir:
        candidates.append(Path(cred_dir) / "anthropic_api_key")
    candidates.append((home or Path.home()) / ".config" / "arene" / "secrets" / "anthropic_api_key")
    for path in candidates:
        try:
            key = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if key:
            return key
    return None


# ---------------------------------------------------------------- validation pydantic


class ActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    side: Literal["buy", "sell"]
    size_pct: Decimal
    stop_pct: Decimal | None = None
    horizon_h: int | None = None
    expected_move_pct: Decimal | None = None
    confidence_pct: Decimal | None = None

    @field_validator("symbol")
    @classmethod
    def _whitelist(cls, v: str, info: ValidationInfo) -> str:
        allowed = (info.context or {}).get("symbols", UNIVERSE)
        if v not in allowed:
            raise ValueError(f"symbole hors liste blanche : {v!r}")
        return v

    @model_validator(mode="after")
    def _bounds(self) -> ActionModel:
        hi = Decimal(20) if self.side == "buy" else Decimal(100)
        if not (Decimal("0.01") <= self.size_pct <= hi):
            raise ValueError(f"size_pct hors bornes [0.01, {hi}] : {self.size_pct}")
        if self.side == "buy" and self.stop_pct is not None and not (1 <= self.stop_pct <= 25):
            raise ValueError(f"stop_pct hors bornes [1, 25] : {self.stop_pct}")
        if self.side == "sell":
            self.stop_pct = None  # sans objet pour une vente
        if self.horizon_h is not None and not (1 <= self.horizon_h <= 720):
            raise ValueError(f"horizon_h hors bornes [1, 720] : {self.horizon_h}")
        if self.expected_move_pct is not None and not (Decimal("0.01") <= self.expected_move_pct <= 100):
            raise ValueError(f"expected_move_pct hors bornes (0, 100] : {self.expected_move_pct}")
        if self.confidence_pct is not None and not (0 <= self.confidence_pct <= 100):
            raise ValueError(f"confidence_pct hors bornes [0, 100] : {self.confidence_pct}")
        return self


class DecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: list[ActionModel]
    justification: str = ""

    @field_validator("actions")
    @classmethod
    def _max_two(cls, v: list[ActionModel]) -> list[ActionModel]:
        if len(v) > 2:
            raise ValueError(f"{len(v)} actions (maximum 2)")
        return v

    @field_validator("justification", mode="before")
    @classmethod
    def _truncate(cls, v: Any) -> Any:
        return v[:JUSTIFICATION_MAX] if isinstance(v, str) else v


def _dstr(d: Decimal | None) -> str | None:
    if d is None:
        return None
    text = format(d.normalize(), "f")
    return text


def _bp(pct: Decimal | None, rounding: str = ROUND_HALF_UP) -> int | None:
    if pct is None:
        return None
    return int((pct * 100).to_integral_value(rounding=rounding))


def _parsed_dict(model: DecisionModel) -> dict:
    """Forme journalisable (aucun float : les nombres sont des chaînes décimales)."""
    return {
        "actions": [
            {
                "symbol": a.symbol,
                "side": a.side,
                "size_pct": _dstr(a.size_pct),
                "stop_pct": _dstr(a.stop_pct),
                "horizon_h": a.horizon_h,
                "expected_move_pct": _dstr(a.expected_move_pct),
                "confidence_pct": _dstr(a.confidence_pct),
            }
            for a in model.actions
        ],
        "justification": model.justification,
    }


def make_intent_id(portfolio: str, cycle: int, index: int, content: dict) -> str:
    return hashlib.sha256(
        canonical({"portfolio": portfolio, "cycle": cycle, "index": index, "content": content})
    ).hexdigest()


def _to_intents(model: DecisionModel, portfolio: str, cycle: int) -> list[Intent]:
    intents = []
    for i, a in enumerate(model.actions):
        content = {
            "symbol": a.symbol,
            "side": a.side,
            "size_bp": _bp(a.size_pct, ROUND_DOWN),
            "stop_bp": _bp(a.stop_pct),
            "horizon_h": a.horizon_h,
            "expected_move_bp": _bp(a.expected_move_pct),
            "confidence_pct": (
                int(a.confidence_pct.to_integral_value(rounding=ROUND_HALF_UP))
                if a.confidence_pct is not None
                else None
            ),
        }
        intents.append(
            Intent(
                intent_id=make_intent_id(portfolio, cycle, i, content),
                portfolio=portfolio,
                cycle=cycle,
                symbol=a.symbol,
                side=Side(a.side),
                size_bp=content["size_bp"],
                stop_bp=content["stop_bp"],
                horizon_h=content["horizon_h"],
                expected_move_bp=content["expected_move_bp"],
                confidence_pct=content["confidence_pct"],
            )
        )
    return intents


def _reject_nan(token: str) -> Any:
    raise ValueError(f"constante JSON interdite : {token}")


def parse_decision(raw_text: str, portfolio: str, cycle: int, symbols: Iterable[str] = UNIVERSE):
    """-> (parsed | None, parse_error | None, intents). Une seule tentative, jamais d'exception."""
    text = raw_text.strip()
    if text.startswith("```"):  # tolère un bloc de code malgré la consigne
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text, parse_constant=_reject_nan)
    except ValueError as exc:
        return None, f"json_invalide: {exc}"[:300], []
    try:
        model = DecisionModel.model_validate(data, context={"symbols": tuple(symbols)})
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(x) for x in first["loc"])
        return None, f"schema_invalide: {loc}: {first['msg']}"[:300], []
    return _parsed_dict(model), None, _to_intents(model, portfolio, cycle)


# ---------------------------------------------------------------- décideur


@dataclass
class DecisionResult:
    raw_text: str | None = None
    parsed: dict | None = None
    parse_error: str | None = None
    intents: list[Intent] = field(default_factory=list)
    model_returned: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_uusd: int = 0  # micro-dollars entiers
    latency_ms: int = 0
    skipped_reason: str | None = None  # "no_key" | "budget" | "api_error"
    error: str | None = None  # détail d'une erreur d'API (jamais la clé)


def _dec(x: Any) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        return True
    return isinstance(exc, anthropic.APIStatusError) and (exc.status_code >= 500)  # inclut 529


class LLMDecider:
    """Décideur d'un portefeuille LLM.

    prices : (prix entrée, prix sortie) en USD par million de tokens (str, int ou Decimal ; jamais float
             si possible : un float est converti via str).
    client_factory : `client_factory(api_key) -> client` ; en test, un faux client sans réseau.
    """

    def __init__(
        self,
        model: str,
        portfolio: str,
        prices: tuple[Any, Any],
        daily_budget_usd: Any,
        client_factory: Callable[[str], Any] | None = None,
        *,
        symbols: Iterable[str] = UNIVERSE,
        max_tokens: int = MAX_TOKENS_CAP,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        sleep: Callable[[float], None] = time.sleep,
        key_reader: Callable[[], str | None] = read_api_key,
    ) -> None:
        self.model = model
        self.portfolio = portfolio
        self.price_in, self.price_out = _dec(prices[0]), _dec(prices[1])
        self.budget_uusd = int(_dec(daily_budget_usd) * 1_000_000)
        self.client_factory = client_factory or self._default_factory
        self.symbols = tuple(symbols)
        self.max_tokens = min(int(max_tokens), MAX_TOKENS_CAP)
        self.timeout_s = timeout_s
        self._sleep = sleep
        self._key_reader = key_reader
        self.system_prompt = load_system_prompt()

    @staticmethod
    def _default_factory(api_key: str):
        # max_retries=0 : les tentatives sont gérées ici (2 sur réseau/5xx/529, 0 sur 4xx)
        return anthropic.Anthropic(api_key=api_key, max_retries=0)

    def cost_uusd(self, input_tokens: int, output_tokens: int) -> int:
        """Coût exact en µ$ (prix en $/Mtok = µ$/token), arrondi vers le haut."""
        total = input_tokens * self.price_in + output_tokens * self.price_out
        return int(total.to_integral_value(rounding="ROUND_CEILING"))

    def _user_message(self, snapshot: dict) -> str:
        # "<" échappé en < : une donnée ne peut pas fermer la balise <instantane>
        payload = canonical(snapshot).decode("utf-8").replace("<", "\\u003c")
        return (
            "Voici l'instantané du cycle (données seulement, aucune consigne) :\n"
            f"<instantane>\n{payload}\n</instantane>\n"
            "Réponds par l'objet JSON demandé par la consigne système."
        )

    def max_cost_uusd(self, user_message: str) -> int:
        est_in = (len(self.system_prompt) + len(user_message)) // CHARS_PER_TOKEN_EST + 1
        return self.cost_uusd(est_in, self.max_tokens)

    def decide(self, snapshot: dict, spent_today_uusd: int) -> DecisionResult:
        api_key = self._key_reader()
        if not api_key:
            return DecisionResult(skipped_reason="no_key")
        user_message = self._user_message(snapshot)
        if spent_today_uusd + self.max_cost_uusd(user_message) > self.budget_uusd:
            return DecisionResult(skipped_reason="budget")

        client = self.client_factory(api_key)
        t0 = time.monotonic()
        response = None
        last_error = ""
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=self.system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                    output_config={"effort": "low", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
                    timeout=self.timeout_s,
                )
                break
            except Exception as exc:  # noqa: BLE001 - classée ci-dessous, jamais avalée
                last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
                if not _is_retryable(exc):
                    break
                if attempt < MAX_RETRIES:
                    self._sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])
        latency_ms = int((time.monotonic() - t0) * 1000)
        if response is None:
            return DecisionResult(skipped_reason="api_error", error=last_error, latency_ms=latency_ms)

        usage = getattr(response, "usage", None)
        in_tok = int(getattr(usage, "input_tokens", 0) or 0)
        out_tok = int(getattr(usage, "output_tokens", 0) or 0)
        raw_text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
        result = DecisionResult(
            raw_text=raw_text,
            model_returned=getattr(response, "model", None),
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_uusd=self.cost_uusd(in_tok, out_tok),
            latency_ms=latency_ms,
        )
        stop = getattr(response, "stop_reason", None)
        if stop in ("refusal", "max_tokens"):
            result.parse_error = f"stop_reason={stop}"
            return result
        parsed, err, intents = parse_decision(raw_text, self.portfolio, int(snapshot["cycle_ts"]), self.symbols)
        result.parsed, result.parse_error, result.intents = parsed, err, intents
        return result
