"""The councils (docs/SPEC-PERP-CONSEIL-HAIKU.md, the owner's requests of 14/11/2026, and of 15/11/2026 for the
league of the councils, docs/SPEC-LIGUE-CONSEILS.md).

A council is one portfolio (`council-perp:<name>`) decided at every round it plays by eleven members: ten Haiku
advisers and a President, Haiku (`council-perp:haiku`) or Opus (`council-perp:opus`); the two councils have the
same advisers, prompts and policy, so only the President differs. The league of the councils
(config/ligue-conseils.toml) lists them; they share the engine, journal, market and watcher of the perp league.
To the league each council is one more player (`LlmModel(council=True)`): it plays the same triggers as the LLM portfolios (rendez-vous,
cadence, market wake-ups, its alerts and the wake-ups its President asks for), against its own round quota and
daily budget, and its decision goes through the same pipeline (`agent_decision`, riskd, execution). Its
`CouncilDecider` has the interface of `AgentDecider`: `decide(round_dir, snapshot) -> AgentResult`.

A round of the council (§3 of the spec):
- A: nine members (1 to 6, 8, 9 and 10) in parallel, each in its own `claude -p` process and MCP server, with the
  same snapshot and nothing of the others: each gives a short opinion (JSON);
- B: the Devil's advocate reads the nine opinions and attacks the strongest idea;
- C: the President reads the ten opinions and the snapshot, and decides in the standard format.

Member processes are bounded across the councils of a round by one semaphore (`CouncilDecider.slots`,
`max_member_processes` of the league): the the host has little free memory.

A member that fails is left out (journaled); a President that fails leaves the round without a decision. The
opinions come back to the caller in `AgentResult.council`, and are journaled as `council_opinion` events by the
one writer of the journal, before the decision. The cost of the round is the sum of its calls (a call that used
the model without saying how much counts for its ceiling).

Its risk policy is its own (config/policy-perp-conseil.toml, profile `aggressive`): leverage up to 10x with
Kraken's margins, a paper demonstration outside the retail 2x rule.

`python -m arene.perp.council resume --portfolio council-perp:<name>` lifts the halt of a council (after its "ruin", -90 % from the peak):
the owner's decision only.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import shutil
import sys
import threading
import time
import tomllib
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from arene.perp.agent import (
    INSTRUMENTS,
    MAX_PRICE_USD,
    TIMEOUT_RC,
    AgentDecider,
    AgentResult,
    Runner,
    _default_runner,
    output_schema,
    stream_cost_uusd,
)
from arene.perp.ledger import BP, QTY_SCALE, to_eur
from arene.perp.margin import LEVERAGED_PREFIX
from arene.perp.policy import AGGRESSIVE, PerpPolicy, PerpPolicyError, load_perp_policy

REPO = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = REPO / "config"
DEFAULT_COUNCIL_CONFIG = CONFIG_DIR / "perp-conseil.toml"
DEFAULT_COUNCILS_LEAGUE = CONFIG_DIR / "ligue-conseils.toml"
PROMPTS_VERSION = "v3"
PROMPT_DIR = Path(__file__).parent / "prompt" / "conseil" / PROMPTS_VERSION
MEMBERS_MODEL = "claude-haiku-5-5"
PRESIDENT_MODELS = {"claude-haiku-5-5": "Haiku", "claude-opus-5-5": "Opus"}
ARGUMENT_MAX = 600
MAX_OPINIONS = 6
MEMBER_MAX_TURNS = 7
RECORD_LAST = 8  # trades shown in `bilan_du_conseil`


class CouncilConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Member:
    key: str
    name: str
    stage: str  # "A" (alone), "B" (reads A), "C" (the President, reads A and B)
    file: str


MEMBERS = (
    Member("cartographe", "Le Cartographe", "A", "01-cartographe.md"),
    Member("suiveur", "Le Suiveur", "A", "02-suiveur.md"),
    Member("chasseur", "Le Chasseur de cassures", "A", "03-chasseur.md"),
    Member("contrarien", "Le Contrarien", "A", "04-contrarien.md"),
    Member("carnet", "Le Lecteur de carnet", "A", "05-carnet.md"),
    Member("tresorier", "Le Trésorier du levier", "A", "06-tresorier.md"),
    Member("avocat", "L'Avocat du diable", "B", "07-avocat.md"),
    Member("gardien", "Le Gardien du risque", "A", "08-gardien.md"),
    Member("memorialiste", "Le Mémorialiste", "A", "09-memorialiste.md"),
    Member("arbitragiste", "L'Arbitragiste de paires", "A", "10-arbitragiste.md"),
    Member("president", "Le Président", "C", "11-president.md"),
)
STAGE_A = tuple(m for m in MEMBERS if m.stage == "A")
ADVOCATE = next(m for m in MEMBERS if m.stage == "B")
PRESIDENT = next(m for m in MEMBERS if m.stage == "C")


def member_prompt(member: Member) -> str:
    """The member's whole system prompt: the common part, its role, then the opinion format (members) or the
    decision rules and format (the President)."""
    tail = "president.md" if member.stage == "C" else "avis.md"
    parts = [PROMPT_DIR / "commun.md", PROMPT_DIR / "roles" / member.file, PROMPT_DIR / tail]
    return "\n\n".join(p.read_text(encoding="utf-8").strip() for p in parts) + "\n"


def member_sha256(member: Member) -> str:
    return hashlib.sha256(member_prompt(member).encode("utf-8")).hexdigest()


def prompts_sha256() -> str:
    """One digest of the eleven prompts (journaled with every council decision)."""
    return hashlib.sha256("".join(f"{m.key}:{member_sha256(m)}\n" for m in MEMBERS).encode()).hexdigest()


# ---------------------------------------------------------------------- opinions

OPINION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["avis", "argument"],
    "properties": {
        "avis": {
            "type": "array",
            "maxItems": MAX_OPINIONS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["instrument", "position", "conviction"],
                "properties": {
                    "instrument": {"type": "string", "enum": list(INSTRUMENTS)},
                    "position": {"type": "string", "enum": ["long", "short", "plat"]},
                    "conviction": {"type": "integer", "minimum": 0, "maximum": 100},
                    "taille_pct": {"type": ["number", "null"], "minimum": 0, "maximum": 1000},
                    "stop_pct": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
                    "niveau_cle_usd": {"type": ["number", "null"], "minimum": 0, "maximum": MAX_PRICE_USD},
                },
            },
        },
        "cible": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": ["instrument", "sens"],
            "properties": {
                "instrument": {"type": "string", "enum": list(INSTRUMENTS)},
                "sens": {"type": "string", "enum": ["long", "short"]},
            },
        },
        "argument": {"type": "string", "maxLength": ARGUMENT_MAX},
    },
}


def _number(v: Any, lo: int, hi: int, name: str) -> str | None:
    """A bounded number as a decimal string (never a float in the journal), or None."""
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int | float | Decimal):
        raise TypeError(f"{name}: a number is expected")
    try:
        d = Decimal(str(v))
    except InvalidOperation as exc:
        raise ValueError(f"{name}: not a number") from exc
    if not d.is_finite() or not lo <= d <= hi:
        raise ValueError(f"{name}: out of [{lo}, {hi}]")
    return format(d.normalize(), "f")


def parse_opinion(data: Any) -> tuple[dict[str, Any] | None, str | None]:
    """(normalized opinion | None, error | None) of a member's structured output. Never raises."""
    try:
        if not isinstance(data, dict) or not {"avis", "argument"} <= set(data) <= {
            "avis",
            "argument",
            "cible",
        }:
            raise ValueError("an object {avis, argument, cible?} is expected")
        raw = data["avis"]
        if not isinstance(raw, list) or len(raw) > MAX_OPINIONS:
            raise ValueError(f"avis: a list of 0 to {MAX_OPINIONS} elements is expected")
        avis = []
        for k, a in enumerate(raw):
            if not isinstance(a, dict) or not {"instrument", "position", "conviction"} <= set(a) <= {
                "instrument", "position", "conviction", "taille_pct", "stop_pct", "niveau_cle_usd",
            }:  # fmt: skip
                raise ValueError(f"avis[{k}]: unexpected keys")
            if a["instrument"] not in INSTRUMENTS or a["position"] not in ("long", "short", "plat"):
                raise ValueError(f"avis[{k}]: instrument or position")
            conv = a["conviction"]
            if isinstance(conv, Decimal) and conv == conv.to_integral_value():
                conv = int(conv)
            if type(conv) is not int or not 0 <= conv <= 100:
                raise ValueError(f"avis[{k}]: conviction, an integer from 0 to 100")
            avis.append(
                {
                    "instrument": a["instrument"],
                    "position": a["position"],
                    "conviction": conv,
                    "taille_pct": _number(a.get("taille_pct"), 0, 1000, "taille_pct"),
                    "stop_pct": _number(a.get("stop_pct"), 0, 100, "stop_pct"),
                    "niveau_cle_usd": _number(a.get("niveau_cle_usd"), 0, MAX_PRICE_USD, "niveau_cle_usd"),
                }
            )
        target = data.get("cible")
        if target is not None:
            if (
                not isinstance(target, dict)
                or set(target) != {"instrument", "sens"}
                or target["instrument"] not in INSTRUMENTS
                or target["sens"] not in ("long", "short")
            ):
                raise ValueError("cible: {instrument, sens} or null")
            target = {"instrument": target["instrument"], "sens": target["sens"]}
        argument = data["argument"]
        if not isinstance(argument, str):
            raise TypeError("argument: a string is expected")
    except (ValueError, TypeError, KeyError) as exc:
        return None, f"invalid opinion: {str(exc)[:300]}"
    return {"avis": avis, "cible": target, "argument": argument[:ARGUMENT_MAX]}, None


# ---------------------------------------------------------------------- the council's record


def council_record(events: Sequence[Mapping[str, Any]], portfolio: str, now_ts: int) -> dict[str, Any]:
    """The council's closed trades (a position from flat back to flat, per contract) and their statistics, from
    its fills: the Mémorialiste's material (`bilan_du_conseil`). The result of a trade is its price P&L minus
    its fees, in EUR at each fill's rate; funding is not counted in it."""
    open_: dict[str, dict[str, Any]] = {}
    trades = []
    for e in events:
        if e["type"] != "perp_fill" or e["ts"] > now_ts:
            continue
        p = e["payload"]
        if p.get("portfolio") != portfolio:
            continue
        inst, q = p["instrument"], int(p["qty"])
        t = open_.get(inst)
        if t is None:
            t = open_[inst] = {
                "side": "long" if q > 0 else "short",
                "opened_ts": e["ts"],
                "pnl": 0,
                "qty": 0,
                "peak": 0,
            }
        t["qty"] += q
        t["peak"] = max(t["peak"], abs(t["qty"]))
        cash_uusd = -q * int(p["price_uusd"]) // QTY_SCALE
        t["pnl"] += to_eur(cash_uusd, int(p["fx_bid"]), int(p["fx_ask"])) - int(p["fee_ueur"])
        if t["qty"] == 0:
            trades.append({**t, "instrument": inst, "closed_ts": e["ts"], "reason": p["reason"]})
            del open_[inst]
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
    n = len(trades)

    def eur(ueur: int | None) -> str | None:
        return None if ueur is None else format((Decimal(ueur) / 1_000_000).quantize(Decimal("0.01")), "f")

    avg_win = sum(wins) // len(wins) if wins else None
    avg_loss = sum(losses) // len(losses) if losses else None
    reasons: dict[str, int] = {}
    for t in trades:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1
    return {
        "trades_fermes": n,
        "gagnants": len(wins),
        "taux_de_reussite_pct": len(wins) * 100 // n if n else None,
        "gain_moyen_eur": eur(avg_win),
        "perte_moyenne_eur": eur(avg_loss),
        "gain_sur_perte": (
            format((Decimal(avg_win) / -Decimal(avg_loss)).quantize(Decimal("0.01")), "f")
            if avg_win is not None and avg_loss
            else None
        ),
        "esperance_par_trade_eur": eur(sum(t["pnl"] for t in trades) // n) if n else None,
        "resultat_total_eur": eur(sum(t["pnl"] for t in trades)) if n else None,
        "sorties_par_raison": reasons,
        "derniers_trades": [
            {
                "instrument": t["instrument"],
                "sens": t["side"],
                "resultat_eur": eur(t["pnl"]),
                "sortie": t["reason"],
                "duree_min": (t["closed_ts"] - t["opened_ts"]) // 60,
                "ferme_le_ts": t["closed_ts"],
            }
            for t in trades[-RECORD_LAST:]
        ],
        "positions_ouvertes": sorted(open_),
        "note": "résultat = P&L de prix moins les frais, en EUR ; funding non compté",
    }


# ---------------------------------------------------------------------- configuration


TREND_KIND = (
    "trend-v4"  # the council v4 (docs/SPEC-CONSEIL-V4.md): the engine decides, the LLMs may only brake
)
TREND_MEMBERS = 3  # Haiku members of the veto council
TREND_BENCHMARK = "benchmark-perp:moteur-tendance"


@dataclass(frozen=True)
class TrendSettings:
    """What the council v4 adds to a council's configuration (`kind = "trend-v4"`)."""

    benchmark: str  # its shadow: the same engine target, no LLM
    rebalance_band_bp: (
        int  # an order only when the target is farther than this from the position (bp of equity)
    )
    stop_pct: str  # the protective stop the code puts on every position (percent, decimal text)
    expected_move_bp: int  # the engine's measured mean gross move per trade (riskd's edge rule), TRAIN period
    expected_move_source: str  # where that number comes from
    horizon_h: int  # the holding time declared with it (riskd's funding cost), at most 168


@dataclass(frozen=True)
class CouncilConfig:
    enabled: bool
    portfolio: str
    name: str
    model: str  # the ten advisers
    president_model: str
    daily_budget_uusd: int
    members_parallel: int
    member_timeout_s: int
    president_timeout_s: int
    member_max_tool_calls: int
    policy: PerpPolicy
    sha256: str
    kind: str = "council-v3"  # "trend-v4": the council v4, see `TrendSettings`
    trend: TrendSettings | None = None


def _usd_to_uusd(v: Any, key: str) -> int:
    try:
        d = Decimal(str(v))
    except InvalidOperation as exc:
        raise CouncilConfigError(f"{key}: not a decimal amount") from exc
    if not isinstance(v, str) or not d.is_finite() or d <= 0 or d > 100:
        raise CouncilConfigError(f"{key}: a positive amount as a string (at most 100) is expected")
    return int(d * 1_000_000)


def load_council(path: Path = DEFAULT_COUNCIL_CONFIG) -> CouncilConfig:
    try:
        raw = path.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise CouncilConfigError(f"unreadable {path}: {exc}") from exc
    expected = {
        "enabled", "portfolio", "name", "model", "president_model", "daily_budget_usd", "members_parallel",
        "member_timeout_s", "president_timeout_s", "member_max_tool_calls", "policy",
    }  # fmt: skip
    trend_keys = {
        "kind", "benchmark", "rebalance_band_bp", "stop_pct", "expected_move_bp", "expected_move_source", "horizon_h",
    }  # fmt: skip
    kind = data.get("kind", "council-v3")
    if kind not in ("council-v3", TREND_KIND):
        raise CouncilConfigError(f"kind: council-v3 (absent) or {TREND_KIND}")
    if kind == TREND_KIND:
        expected |= trend_keys
    if set(data) != expected:
        raise CouncilConfigError(f"keys: expected {sorted(expected)}, got {sorted(data)}")
    if type(data["enabled"]) is not bool:
        raise CouncilConfigError("enabled is a boolean")
    if not isinstance(data["portfolio"], str) or not data["portfolio"].startswith(LEVERAGED_PREFIX):
        raise CouncilConfigError(f"portfolio must start with {LEVERAGED_PREFIX}")
    if data["model"] != MEMBERS_MODEL:
        raise CouncilConfigError(f"model: the advisers of a council are Haiku ({MEMBERS_MODEL})")
    if data["president_model"] not in PRESIDENT_MODELS:
        raise CouncilConfigError(f"president_model: one of {sorted(PRESIDENT_MODELS)}")
    if kind == TREND_KIND and data["president_model"] != "claude-opus-5-5":
        raise CouncilConfigError("president_model: the President of the council v4 is Opus (claude-opus-5-5)")
    if not isinstance(data["name"], str) or not 1 <= len(data["name"]) <= 40:
        raise CouncilConfigError("name: a display name of 1 to 40 characters")
    if type(data["members_parallel"]) is not int or not 1 <= data["members_parallel"] <= 8:
        raise CouncilConfigError("members_parallel: 1 to 8")
    if type(data["member_timeout_s"]) is not int or not 30 <= data["member_timeout_s"] <= 300:
        raise CouncilConfigError("member_timeout_s: 30 to 300")
    if type(data["president_timeout_s"]) is not int or not 30 <= data["president_timeout_s"] <= 300:
        raise CouncilConfigError("president_timeout_s: 30 to 300")
    if type(data["member_max_tool_calls"]) is not int or not 0 <= data["member_max_tool_calls"] <= 4:
        raise CouncilConfigError("member_max_tool_calls: 0 to 4")
    if not isinstance(data["policy"], str) or "/" in data["policy"] or not data["policy"].endswith(".toml"):
        raise CouncilConfigError("policy: a file name of config/")
    try:
        policy = load_perp_policy(path.parent / data["policy"], profile=AGGRESSIVE)
    except PerpPolicyError as exc:
        raise CouncilConfigError(f"policy: {exc}") from exc
    return CouncilConfig(
        data["enabled"],
        data["portfolio"],
        data["name"],
        data["model"],
        data["president_model"],
        _usd_to_uusd(data["daily_budget_usd"], "daily_budget_usd"),
        data["members_parallel"],
        data["member_timeout_s"],
        data["president_timeout_s"],
        data["member_max_tool_calls"],
        policy,
        hashlib.sha256(raw).hexdigest(),
        kind=kind,
        trend=_trend_settings(data) if kind == TREND_KIND else None,
    )


def _trend_settings(data: Mapping[str, Any]) -> TrendSettings:
    """The keys of a `kind = "trend-v4"` council, checked (fail closed: any doubt refuses the file)."""
    if data["benchmark"] != TREND_BENCHMARK:
        raise CouncilConfigError(f"benchmark: {TREND_BENCHMARK}")
    band = data["rebalance_band_bp"]
    if type(band) is not int or not 100 <= band <= 2000:
        raise CouncilConfigError("rebalance_band_bp: an integer from 100 to 2000")
    try:
        stop = Decimal(str(data["stop_pct"]))
    except InvalidOperation as exc:
        raise CouncilConfigError("stop_pct: a decimal text") from exc
    if not isinstance(data["stop_pct"], str) or not stop.is_finite() or not 1 <= stop <= 15:
        raise CouncilConfigError("stop_pct: a decimal text from 1 to 15")
    move = data["expected_move_bp"]
    if type(move) is not int or not 1 <= move <= 3000:
        raise CouncilConfigError("expected_move_bp: an integer from 1 to 3000")
    if not isinstance(data["expected_move_source"], str) or len(data["expected_move_source"]) < 20:
        raise CouncilConfigError(
            "expected_move_source: where the number was measured (20 characters at least)"
        )
    hours = data["horizon_h"]
    if type(hours) is not int or not 1 <= hours <= 168:
        raise CouncilConfigError("horizon_h: an integer from 1 to 168")
    return TrendSettings(data["benchmark"], band, data["stop_pct"], move, data["expected_move_source"], hours)


@dataclass(frozen=True)
class CouncilsLeague:
    """config/ligue-conseils.toml: the councils that play, and the bound on member processes across them.
    `errors`: the councils left out because their own configuration is invalid (one bad council never stops
    the others)."""

    enabled: bool
    max_member_processes: int
    councils: tuple[CouncilConfig, ...]
    errors: tuple[str, ...]
    sha256: str

    def council(self, portfolio: str) -> CouncilConfig | None:
        return next((c for c in self.councils if c.portfolio == portfolio), None)

    def without(self, retired: Collection[str]) -> CouncilsLeague:
        """The league minus the retired councils: they are never opened, called nor valued again, even if their
        file is still listed (the journal decides, not the configuration)."""
        if not any(c.portfolio in retired for c in self.councils):
            return self
        return dataclasses.replace(
            self, councils=tuple(c for c in self.councils if c.portfolio not in retired)
        )


def retired_portfolios(events: Iterable[Mapping[str, Any]]) -> frozenset[str]:
    """The portfolios the journal says are retired (`portfolio_retired`)."""
    return frozenset(
        e["payload"]["portfolio"]
        for e in events
        if e["type"] == "portfolio_retired" and isinstance(e["payload"].get("portfolio"), str)
    )


def load_councils_league(path: Path = DEFAULT_COUNCILS_LEAGUE) -> CouncilsLeague:
    """Raises `CouncilConfigError` when the league file itself is invalid (all councils off); a council whose
    own file is invalid is left out with its error."""
    try:
        raw = path.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise CouncilConfigError(f"unreadable {path}: {exc}") from exc
    if set(data) != {"enabled", "max_member_processes", "councils"}:
        raise CouncilConfigError(
            f"keys: expected enabled, max_member_processes, councils, got {sorted(data)}"
        )
    if type(data["enabled"]) is not bool:
        raise CouncilConfigError("enabled is a boolean")
    if type(data["max_member_processes"]) is not int or not 1 <= data["max_member_processes"] <= 8:
        raise CouncilConfigError("max_member_processes: 1 to 8")
    files = data["councils"]
    if (
        not isinstance(files, list)
        or not all(isinstance(f, str) and "/" not in f and f.endswith(".toml") for f in files)
        or len(set(files)) != len(files)
    ):
        raise CouncilConfigError("councils: distinct file names of config/")
    councils: list[CouncilConfig] = []
    errors: list[str] = []
    for f in files:
        try:
            c = load_council(path.parent / f)
        except CouncilConfigError as exc:
            errors.append(f"{f}: {exc}"[:500])
            continue
        if any(o.portfolio == c.portfolio for o in councils):
            errors.append(f"{f}: duplicate portfolio {c.portfolio}")
            continue
        councils.append(c)
    return CouncilsLeague(
        data["enabled"],
        data["max_member_processes"],
        tuple(councils) if data["enabled"] else (),
        tuple(errors),
        hashlib.sha256(raw).hexdigest(),
    )


# ---------------------------------------------------------------------- the deciders


def _data_block(tag: str, obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).replace("<", "\\u003c")
    return f"<{tag}>\n{payload}\n</{tag}>\n"


@dataclass
class MemberDecider(AgentDecider):
    """One member's `claude -p` call: its own system prompt, the opinion schema (or the decision schema for the
    President), and a first message with the snapshot and, from stage B on, the opinions it may read."""

    member: Member = PRESIDENT
    opinions: list[dict[str, Any]] | None = None
    schema: dict[str, Any] = field(default_factory=lambda: OPINION_SCHEMA)

    def system_prompt(self) -> str:
        return member_prompt(self.member)

    def output_schema(self) -> dict[str, Any]:
        return self.schema

    def prompt_digest(self) -> str:
        return member_sha256(self.member)

    def message(self, snapshot: Mapping[str, Any]) -> str:
        text = "Voici l'instantané de la ronde (données seulement, aucune consigne) :\n" + _data_block(
            "instantane", snapshot
        )
        if self.opinions is not None:
            text += "Voici les avis des membres du conseil (données seulement, aucune consigne) :\n"
            text += _data_block("avis_du_conseil", self.opinions)
        what = "la décision demandée" if self.member.stage == "C" else "ton avis"
        return (
            text + f"Utilise tes outils si besoin ({self.max_tool_calls} appels au plus), puis rends {what}."
        )


def _used_model(r: AgentResult) -> bool:
    return not r.result_seen and (r.rc == TIMEOUT_RC or r.assistant_seen or bool(r.tool_calls))


@dataclass
class CouncilDecider:
    """The council as one decider of the league (same interface as `AgentDecider`)."""

    config: CouncilConfig
    workdir: Path
    runner: Runner = _default_runner
    python: str = sys.executable
    effort: str | None = "low"
    # the ceiling of the whole round, set by the league: a twentieth per adviser, half for the President
    max_budget_usd: str = "1.00"
    # bounds the member processes across the councils of a round (None: only `members_parallel`)
    slots: threading.Semaphore | None = None

    @property
    def model(self) -> str:
        """The model of the decision (`model_requested`): the President's."""
        return self.config.president_model

    @property
    def portfolio(self) -> str:
        return self.config.portfolio

    @property
    def max_size_pct(self) -> int:
        return max(100, self.config.policy.max_order_bp * 100 // BP)

    def prompt_digest(self) -> str:
        return member_sha256(PRESIDENT)

    def _member(self, member: Member, opinions: list[dict[str, Any]] | None, ceiling: str) -> MemberDecider:
        president = member.stage == "C"
        return MemberDecider(
            self.config.president_model if president else self.config.model, self.config.portfolio,
            self.workdir, self.runner, max_tool_calls=self.config.member_max_tool_calls,
            max_turns=MEMBER_MAX_TURNS,
            timeout_s=float(self.config.president_timeout_s if president else self.config.member_timeout_s),
            python=self.python, max_budget_usd=ceiling, effort=self.effort, member=member, opinions=opinions,
            schema=output_schema(self.max_size_pct) if president else OPINION_SCHEMA,
        )  # fmt: skip

    def message(self, snapshot: Mapping[str, Any]) -> str:
        """The first message of stage A (the same for its nine members; its sha256 goes in `round_data`)."""
        return self._member(STAGE_A[0], None, self.max_budget_usd).message(snapshot)

    def member_ceiling_uusd(self, member: Member | None = None) -> int:
        """A twentieth of the round's ceiling for an adviser (ten of them: half), half for the President (an
        Opus President costs most of the round)."""
        total = int(Decimal(self.max_budget_usd) * 1_000_000)
        if member is not None and member.stage == "C":
            return max(1, total // 2)
        return max(1, total // (2 * (len(MEMBERS) - 1)))

    def decide(self, round_dir: Path, snapshot: Mapping[str, Any]) -> AgentResult:
        """Never raises: whatever fails once the members are called, the cost of the calls made is returned
        (the league's budget counts it)."""
        t0 = time.monotonic()
        done: list[tuple[Member, AgentResult]] = []

        def run(member: Member, opinions: list[dict[str, Any]] | None) -> AgentResult:
            mdir = round_dir / "membres" / member.key
            ceiling = f"{Decimal(self.member_ceiling_uusd(member)).scaleb(-6):.6f}"
            try:
                mdir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(round_dir / "round.json", mdir / "round.json")
                with self.slots if self.slots is not None else nullcontext():
                    r = self._member(member, opinions, ceiling).decide(mdir, snapshot)
            except Exception as exc:  # noqa: BLE001 (one member's failure never stops the round)
                # a call that ran and failed afterwards still cost what its stream says
                r = AgentResult(
                    error=f"member crashed: {type(exc).__name__}: {str(exc)[:200]}",
                    cost_uusd=stream_cost_uusd(mdir / "stream.jsonl"),
                    result_seen=True,
                )
            done.append((member, r))
            return r

        try:
            (round_dir / "stream.jsonl").write_bytes(
                b""
            )  # the council is called: an interruption is never replayed
            return self._deliberate(round_dir, snapshot, run, t0)
        except Exception as exc:  # noqa: BLE001 (the council's own failure: no decision, the cost is kept)
            res = AgentResult(
                error=f"council crashed: {type(exc).__name__}: {str(exc)[:200]}",
                result_seen=True,
                assistant_seen=any(r.assistant_seen for _, r in done),
            )
            res.cost_uusd = sum(self._charged(m, r) for m, r in done)
            res.latency_ms = int((time.monotonic() - t0) * 1000)
            return res

    def _charged(self, m: Member, r: AgentResult) -> int:
        """What a member's call counts: its cost, or its ceiling when it used the model without saying how much."""
        return max(r.cost_uusd, self.member_ceiling_uusd(m)) if _used_model(r) else r.cost_uusd

    def _deliberate(
        self,
        round_dir: Path,
        snapshot: Mapping[str, Any],
        run: Callable[[Member, list[dict[str, Any]] | None], AgentResult],
        t0: float,
    ) -> AgentResult:
        """Stages A, B and C, then the round's result (the opinions, the President's decision, the summed cost)."""
        del snapshot  # each member gets it through `run`
        with ThreadPoolExecutor(max_workers=self.config.members_parallel) as pool:
            stage_a = dict(zip(STAGE_A, pool.map(lambda m: run(m, None), STAGE_A), strict=True))
        records: list[dict[str, Any]] = []
        seen: list[dict[str, Any]] = []
        for m in STAGE_A:
            rec, visible = self._record(m, stage_a[m])
            records.append(rec)
            if visible is not None:
                seen.append(visible)
        advocate = run(ADVOCATE, list(seen))
        rec, visible = self._record(ADVOCATE, advocate)
        records.append(rec)
        if visible is not None:
            seen.append(visible)
        president = run(PRESIDENT, seen)
        results = [*stage_a.values(), advocate, president]
        res = AgentResult(
            decision=president.decision,
            error=None
            if president.decision is not None
            else f"president: {president.error or 'no decision'}",
            mcp_status=president.mcp_status,
            model_returned=president.model_returned,
            num_turns=president.num_turns,
            attempts=president.attempts,
            rc=president.rc,
            first_error=president.first_error,
            stderr_tail=president.stderr_tail,
            tools_offered=president.tools_offered,
            assistant_seen=any(r.assistant_seen for r in results),
            result_seen=True,  # the cost below already charges every call that used the model without a result
        )
        for m, r in zip([*STAGE_A, ADVOCATE, PRESIDENT], results, strict=True):
            res.input_tokens += r.input_tokens
            res.output_tokens += r.output_tokens
            res.cache_read_tokens += r.cache_read_tokens
            res.cache_write_tokens += r.cache_write_tokens
            res.cost_uusd += self._charged(m, r)
        n = 0
        for m, r in zip([*STAGE_A, ADVOCATE, PRESIDENT], results, strict=True):
            for call in r.tool_calls:
                n += 1
                call.n, call.member = n, m.key
                res.tool_calls.append(call)
        res.council = records
        res.extra = {
            "council": {
                "name": self.config.name,
                "members_model": self.config.model,
                "president_model": self.config.president_model,
                "prompts_version": PROMPTS_VERSION,
                "prompts_sha256": prompts_sha256(),
                "config_sha256": self.config.sha256,
                "members_ok": sum(1 for r in records if r["opinion"] is not None),
                "members_failed": [r["member"] for r in records if r["opinion"] is None],
                "president_cost_uusd": president.cost_uusd,
                "president_latency_ms": president.latency_ms,
                "president_tool_calls": len(president.tool_calls),
            }
        }
        try:  # the audit files: their failure never loses the round
            streams = b"".join(
                (round_dir / "membres" / m.key / "stream.jsonl").read_bytes()
                for m in MEMBERS
                if (round_dir / "membres" / m.key / "stream.jsonl").exists()
            )
            (round_dir / "stream.jsonl").write_bytes(streams)
            res.stream_sha256 = hashlib.sha256(streams).hexdigest()
            (round_dir / "council.json").write_text(
                json.dumps({"opinions": records, "seen_by_president": seen}, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
        except OSError as exc:
            res.extra["council"]["audit_files_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        res.latency_ms = int((time.monotonic() - t0) * 1000)
        return res

    def _record(self, m: Member, r: AgentResult) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """(the `council_opinion` payload, what the next stages read of it or None when it failed)."""
        opinion, error = (None, r.error)
        if r.decision is not None:
            opinion, error = parse_opinion(r.decision)
        rec = {
            "member": m.key,
            "name": m.name,
            "stage": m.stage,
            "persona_sha256": member_sha256(m),
            "opinion": opinion,
            "error": None if opinion is not None else (error or "no opinion")[:300],
            "cost_uusd": self._charged(m, r),
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cache_read_tokens": r.cache_read_tokens,
            "cache_write_tokens": r.cache_write_tokens,
            "latency_ms": r.latency_ms,
            "tool_calls": len(r.tool_calls),
            "model_returned": r.model_returned,
            "stream_sha256": r.stream_sha256,
        }
        visible = None if opinion is None else {"membre": m.name, "role": m.key, **opinion}
        return rec, visible


# ---------------------------------------------------------------------- resume after the halt


def main(argv: list[str] | None = None) -> int:
    from arene.journal import Journal
    from arene.perp.config import default_var
    from arene.perp.retire import RetireError, retire_portfolio
    from arene.perp.sim import PerpSimulator

    ap = argparse.ArgumentParser(prog="python -m arene.perp.council")
    ap.add_argument("command", choices=["resume", "retire"])
    ap.add_argument("--portfolio", default=None, help="council-perp:<name> (needed when there are several)")
    ap.add_argument("--var", type=Path, default=None)
    ap.add_argument("--reason", default="manual", help="retire: why (journaled)")
    ap.add_argument("--note", default="", help="retire: free note (journaled)")
    args = ap.parse_args(argv)
    var = (args.var or default_var()).resolve()
    if args.command == "retire":
        if args.portfolio is None:
            print("retire: --portfolio council-perp:<name> is needed", file=sys.stderr)
            return 2
        try:
            out = retire_portfolio(var, args.portfolio, int(time.time()), reason=args.reason, note=args.note)
        except RetireError as exc:
            print(f"{exc}", file=sys.stderr)
            return 3
        if out["status"] == "already_retired":
            print(f"{args.portfolio}: already retired, nothing to do")
        else:
            print(f"{args.portfolio}: retired ({out['fills']} position(s) flattened, {out['orders_ended']} order(s) ended)")
        return 0
    names = [c.portfolio for c in load_councils_league().councils]
    if args.portfolio is None and len(names) != 1:
        print(f"--portfolio is needed: one of {', '.join(names) or '(none)'}", file=sys.stderr)
        return 2
    portfolio = args.portfolio or names[0]
    sim = PerpSimulator(Journal(var / "journal" / "events.jsonl"), {})
    acc = sim.states().get(portfolio)
    if acc is None and portfolio not in names:  # a council taken out of the league file stays resumable
        print(f"{portfolio}: not a council of the journal nor of config/ligue-conseils.toml", file=sys.stderr)
        return 2
    if acc is not None and acc.retired:
        print(f"{portfolio}: retired, it never plays again", file=sys.stderr)
        return 2
    if portfolio not in names:
        print(
            f"{portfolio}: not a council of config/ligue-conseils.toml ({', '.join(names)})", file=sys.stderr
        )
        return 2
    if acc is None or not (acc.halted or acc.frozen_until_ts):
        print(f"{portfolio}: not halted nor frozen, nothing to do")
        return 0
    sim.append_event(
        "portfolio_resumed", {"portfolio": portfolio, "reason": "manual", "until_ts": 0}, int(time.time())
    )
    print(f"{portfolio}: resumed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
