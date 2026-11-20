"""The council v4, the "Trend Council" (docs/SPEC-TREND-COUNCIL.md).

The roles are inverted compared to the councils before it:
- **the engine decides**: `arena.perp.lab.trend` (frozen on 2026-11-17, scale 2x) gives the target of each contract
  at the close of each 4-hour bar. It is journaled (`trend_engine_target`) before anything else;
- **the LLMs may only brake**: three Haiku members and an Opus President give each contract a coefficient of 1, 0.5
  or 0, which multiplies the target. They cannot raise it, invert it, nor open what the engine does not hold. Any
  failure of the council leaves every coefficient at 1: the engine alone;
- **the code executes**: the gap between the final target and the position becomes standard actions (open, reduce,
  close, with a protective stop), only when it exceeds the band (5% of the equity). They go through riskd like
  every other player's; an entry refused for its size is retried smaller (`agent_round.run_intents`).

`benchmark-perp:trend-engine` plays the same engine target without the LLMs, through the same execution path.

The watcher calls `run_trend_round` (arena/perp/watcher.py `_trend_phase`): once per bar close (`bar`), and for
the rounds in between (`veto` on a news item, a macro release or a 2%-in-1-hour move: coefficients can only go
down; `restoration`: the engine alone, when a brake's validity ends).
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from arena.perp.agent import (
    INSTRUMENTS,
    AgentResult,
    Runner,
    _default_runner,
    parse_decision,
    stream_cost_uusd,
)
from arena.perp.agent_round import finish_agent_round, prepare_agent_round, run_intents
from arena.perp.council import (
    CouncilConfig,
    Member,
    MemberDecider,
    TrendSettings,
    _used_model,
    council_record,
)
from arena.perp.lab import trend as trend_lab
from arena.perp.lab.backtest import INSTRUMENTS as ENGINE_INSTRUMENTS
from arena.perp.lab.backtest import Data
from arena.perp.ledger import BP, QTY_SCALE, MarginAccount, equity_ueur
from arena.perp.llm_league import charge_ceiling
from arena.perp.riskd import PerpMarketView
from arena.perp.sim import PerpSimulator
from arena.perp.store import PerpDataStore
from arena.perp.types import InstrumentSpec
from arena.types import MICRO

PROMPTS_VERSION = "v4"
PROMPT_DIR = Path(__file__).parent / "prompt" / "council-trend"
ENGINE_PARAMS = replace(
    trend_lab.FROZEN, scale=2.0
)  # the frozen engine at the council's scale: never edited here
ENGINE_VERSION = "trend-frozen-2026-11-17"
BAR_S = ENGINE_PARAMS.bar_hours * 3600
DAY_S = 86_400
HISTORY_DAYS = 30  # the 1-minute candles the engine reads (its EMAs settle in 6 days; 30 is the lab's habit)
MIN_HISTORY_DAYS = 14  # less than that: the engine is not computed (fail closed)
MAX_MISSING_PCT = 5  # of the last 24 h of minutes, per contract
MAX_TAIL_GAP_S = 1800  # a contract whose last candle is older than that at the bar close is stale
MAX_ACTIONS = 12  # six contracts, each a close then an open at most
HALVES = {0: "0", 1: "0.5", 2: "1"}  # a coefficient in halves: 0, 1 or 2
REASON_MAX = 200
RESUME_MAX = 300
MIN_CALL_S = 20.0  # a model call given less time (deadline before a spot cycle) is not made
JUSTIFICATION_MAX = 600
VALIDITY_MAX_H = 4
KINDS = ("bar", "veto", "restoration")
# What the engine did on the bench (measured offline), given to every member.
ENGINE_SUMMARY = {
    "engine": "slow trend following (EMA 2 d / 6 d on 4-hour bars), long and short, volatility targeting, scale 2x",
    "in_trend": (
        "64-day training period: +102% (1.1%/day); sealed 31-day holdout in a clear decline: +21% "
        "(0.62%/day), maximum drawdown -24.6%"
    ),
    "in_range": "around zero, sometimes slightly negative (a 16-day block at -3.4% at 1x): its normal costs",
    "source": "docs/COUNCIL-V4-RESEARCH.md",
}


class EngineError(Exception):
    """The engine could not be computed from the stored data (no target is better than a wrong one)."""


# ---------------------------------------------------------------------- the engine, live


@dataclass(frozen=True)
class EngineTarget:
    bar_ts: int  # minute timestamp of the last minute of the bar (HH:59)
    end_ts: int  # the bar's close (HH:00), the clock of the rounds
    target_bp: dict[str, int]  # signed notional / equity in bp, scale applied
    z: dict[str, str]
    vol_day_bp: dict[str, int]  # the contract's daily volatility (bp of price)
    held: dict[str, str]  # contract -> why its data is not trusted: it keeps its position
    missing_pct: dict[str, int]

    def payload(self, portfolio: str) -> dict[str, Any]:
        return {
            "portfolio": portfolio,
            "status": "ok",
            "bar_ts": self.bar_ts,
            "bar_end_ts": self.end_ts,
            "targets_bp": dict(self.target_bp),
            "z": dict(self.z),
            "vol_day_bp": dict(self.vol_day_bp),
            "held": dict(self.held),
            "missing_pct": dict(self.missing_pct),
            "engine_version": ENGINE_VERSION,
            "params_sha256": params_sha256(),
            "scale": "2.0",
        }

    @classmethod
    def from_payload(cls, p: Mapping[str, Any]) -> EngineTarget:
        return cls(
            int(p["bar_ts"]),
            int(p["bar_end_ts"]),
            {str(k): int(v) for k, v in p["targets_bp"].items()},
            {str(k): str(v) for k, v in p["z"].items()},
            {str(k): int(v) for k, v in p["vol_day_bp"].items()},
            {str(k): str(v) for k, v in p["held"].items()},
            {str(k): int(v) for k, v in p["missing_pct"].items()},
        )


def params_sha256(p: trend_lab.TrendParams = ENGINE_PARAMS) -> str:
    return hashlib.sha256(json.dumps(asdict(p), sort_keys=True).encode()).hexdigest()


def bar_close(now_ts: int) -> int:
    """The close (HH:00 UTC, a multiple of 4 h) of the last complete bar at `now_ts`."""
    return now_ts // BAR_S * BAR_S


def load_data(
    store: PerpDataStore,
    end_ts: int,
    instruments: Sequence[str] = ENGINE_INSTRUMENTS,
    days: int = HISTORY_DAYS,
) -> tuple[Data, dict[str, int], dict[str, int]]:
    """The last `days` of 1-minute trade candles on a contiguous minute grid that starts at 00:00 UTC, so that
    the 4-hour bars close at 03:59, 07:59, ..., 23:59, and the engine's daily re-estimate falls on UTC days.
    Missing minutes are flat at the previous close, as in `backtest.load`. Returns (data, % of the last 24 h of
    minutes missing per contract, seconds between the last candle's end and `end_ts` per contract)."""
    start = (end_ts // DAY_S - days) * DAY_S
    rows: dict[str, dict[int, Any]] = {}
    for inst in instruments:
        candles = store.closed_candles("trade", inst, 60, start, end_ts)
        if not candles:
            raise EngineError(f"no trade candle for {inst}")
        rows[inst] = {c.ts: c for c in candles}
    first = max(min(r) for r in rows.values())
    start = max(start, -(-first // DAY_S) * DAY_S)
    if end_ts - start < MIN_HISTORY_DAYS * DAY_S:
        raise EngineError(f"history of {(end_ts - start) // DAY_S} days, {MIN_HISTORY_DAYS} needed")
    ts = np.arange(start, end_ts, 60, dtype=np.int64)
    n, k = len(ts), len(instruments)
    arr = {name: np.full((n, k), np.nan) for name in ("open", "high", "low", "close")}
    vol = np.zeros((n, k))
    missing: dict[str, int] = {}
    tail: dict[str, int] = {}
    for j, inst in enumerate(instruments):
        present = np.zeros(n, dtype=bool)
        for t, c in rows[inst].items():
            i = (t - start) // 60
            if 0 <= i < n and (t - start) % 60 == 0:
                arr["open"][i, j], arr["high"][i, j] = c.open / 1e6, c.high / 1e6
                arr["low"][i, j], arr["close"][i, j] = c.low / 1e6, c.close / 1e6
                vol[i, j] = c.volume_qty / 1e8
                present[i] = True
        day = min(1440, n)
        missing[inst] = round(100 * (day - int(present[-day:].sum())) / day)
        tail[inst] = end_ts - (max(rows[inst]) + 60)
        close = (
            pd.Series(arr["close"][:, j]).ffill().bfill().to_numpy()
        )  # a missing minute: flat at the last close
        for name in arr:
            col = arr[name][:, j]
            col[~present] = close[~present]
    funding = np.zeros((n, k))
    return (
        Data(ts, arr["open"], arr["high"], arr["low"], arr["close"], vol, funding, tuple(instruments)),
        missing,
        tail,
    )


def _diagnostics(data: Data, p: trend_lab.TrendParams) -> tuple[np.ndarray, np.ndarray]:
    """(z, daily volatility) of the last bar, from the engine's own helpers and formulas (for the journal only:
    the target comes from `trend.latest`)."""
    n, k = data.close.shape
    h = p.bar_hours
    m = 60 * h
    n_bars = n // m
    c = data.close[: n_bars * m].reshape(n_bars, m, k)[:, -1]
    sd1 = trend_lab._hourly_sd(data.close, p.vol_window_h)[np.arange(n_bars) * h + h - 1]
    ef, es = trend_lab._ewm(c, p.fast), trend_lab._ewm(c, p.slow)
    z = np.nan_to_num(((ef - es) / es) / (sd1 * np.sqrt(p.slow * h)))
    return z[-1], (sd1 * np.sqrt(24))[-1]


def engine_target(
    store: PerpDataStore, now_ts: int, params: trend_lab.TrendParams = ENGINE_PARAMS
) -> EngineTarget:
    """The engine's target at the last bar close before `now_ts`. Raises `EngineError` when the data cannot
    support it. A contract whose last 24 h are too incomplete (more than 5% of the minutes missing, or a stale
    tail) is listed in `held`: its position is kept, whatever its target says."""
    end_ts = bar_close(now_ts)
    data, missing, tail = load_data(store, end_ts)
    bar_ts, w = trend_lab.latest(data, params)
    if bar_ts != end_ts - 60:
        raise EngineError(f"the last bar ends at {bar_ts}, not at {end_ts - 60}")
    z, vol = _diagnostics(data, params)
    target, zs, vols, held = {}, {}, {}, {}
    for j, inst in enumerate(data.instruments):
        if not math.isfinite(w[j]) or abs(w[j]) > params.cap * params.scale + 1e-9:
            held[inst] = "target not finite or above the cap"
            target[inst] = 0
        else:
            target[inst] = round(float(w[j]) * BP)
        if missing[inst] > MAX_MISSING_PCT:
            held[inst] = f"{missing[inst]}% of the last 24 h of minutes missing"
        elif tail[inst] > MAX_TAIL_GAP_S:
            held[inst] = f"last candle {tail[inst] // 60} min before the bar close"
        zs[inst] = (
            format(Decimal(float(z[j])).quantize(Decimal("0.0001")), "f") if math.isfinite(z[j]) else "0"
        )
        vols[inst] = round(float(vol[j]) * BP) if math.isfinite(vol[j]) else 0
    return EngineTarget(bar_ts, end_ts, target, zs, vols, held, missing)


# ---------------------------------------------------------------------- coefficients and orders


@dataclass(frozen=True)
class Brake:
    """A coefficient below 1 in force on a contract: 0 or 1 half-unit, until `until_ts`, and why."""

    halves: int
    until_ts: int
    why: str


def apply_coefficient(target_bp: int, halves: int) -> int:
    """The target times a coefficient of `halves`/2, clamped to [0, 1]: same sign, never farther from 0."""
    h = min(2, max(0, int(halves)))
    return (1 if target_bp >= 0 else -1) * (abs(target_bp) * h // 2)


def final_targets(engine_bp: Mapping[str, int], brakes: Mapping[str, Brake]) -> dict[str, int]:
    """The engine's targets with the coefficients in force. A contract without a brake keeps its target."""
    return {i: apply_coefficient(t, brakes[i].halves if i in brakes else 2) for i, t in engine_bp.items()}


def current_exposure_bp(
    acc: MarginAccount, marks: Mapping[str, int], fx_bid: int, equity_ueur_: int
) -> dict[str, int]:
    """Signed notional of each position at the mark, in bp of the equity (EUR to USD at the bid, as riskd sizes)."""
    eq_uusd = equity_ueur_ * fx_bid // MICRO
    out: dict[str, int] = {}
    for inst, pos in acc.positions.items():
        if inst in marks and eq_uusd > 0:
            n = abs(pos.qty) * marks[inst] // QTY_SCALE
            out[inst] = (1 if pos.qty > 0 else -1) * (n * BP // eq_uusd)
    return out


def plan_actions(
    final_bp: Mapping[str, int],
    current_bp: Mapping[str, int],
    held: Mapping[str, str],
    settings: TrendSettings,
    instruments: Sequence[str] = INSTRUMENTS,
) -> list[dict[str, Any]]:
    """The standard actions that bring each position to its final target, only when the gap exceeds the band.

    Reductions and closes come first (they free margin), then the entries. A contract whose data is not
    trusted (`held`) keeps its position. A target of 0 closes the position whatever the band. A target on the
    other side closes, then opens. size_pct: an entry, in % of the equity; a reduction, in % of the position."""
    closes: list[dict[str, Any]] = []
    opens: list[dict[str, Any]] = []
    move = Decimal(settings.expected_move_bp) / 100

    def entry(inst: str, side: int, size_bp: int) -> dict[str, Any]:
        return {
            "instrument": inst,
            "action": "open_long" if side > 0 else "open_short",
            "size_pct": Decimal(size_bp) / 100,
            "stop_pct": Decimal(settings.stop_pct),
            "horizon_h": settings.horizon_h,
            "expected_move_pct": move,
        }

    for inst in instruments:
        if inst in held or inst not in final_bp:
            continue
        t, c = final_bp[inst], current_bp.get(inst, 0)
        if t == 0:
            if c != 0:
                closes.append({"instrument": inst, "action": "close"})
            continue
        if abs(t - c) <= settings.rebalance_band_bp:
            continue
        side = 1 if t > 0 else -1
        if c != 0 and (c > 0) != (t > 0):  # the other side: close, then open (riskd forbids a flip)
            closes.append({"instrument": inst, "action": "close"})
            opens.append(entry(inst, side, abs(t)))
        elif abs(t) > abs(c):
            opens.append(entry(inst, side, abs(t) - abs(c)))
        else:
            keep = (abs(c) - abs(t)) * BP // abs(c)
            if keep >= BP:
                closes.append({"instrument": inst, "action": "close"})
            elif keep > 0:
                closes.append({"instrument": inst, "action": "reduce", "size_pct": Decimal(keep) / 100})
    return closes + opens


# ---------------------------------------------------------------------- the veto council

MEMBERS = (
    Member("news_watcher", "The News Watcher", "A", "01-news-watcher.md"),
    Member("controller", "The Data Controller", "A", "02-controller.md"),
    Member("risk_advocate", "The Risk Advocate", "A", "03-risk-advocate.md"),
    Member("president", "The President", "C", "04-president.md"),
)
STAGE_A = tuple(m for m in MEMBERS if m.stage == "A")
PRESIDENT = next(m for m in MEMBERS if m.stage == "C")

_COEFF = {"type": "number", "enum": [0, 0.5, 1]}
_ITEM = {
    "type": "object",
    "additionalProperties": False,
    "required": ["instrument", "coefficient", "reason"],
    "properties": {
        "instrument": {"type": "string", "enum": list(INSTRUMENTS)},
        "coefficient": _COEFF,
        "reason": {"type": "string", "maxLength": REASON_MAX},
    },
}
PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["proposals", "resume"],
    "properties": {
        "proposals": {
            "type": "array",
            "maxItems": len(INSTRUMENTS),
            "items": {
                **_ITEM,
                "properties": {**_ITEM["properties"], "coefficient": {"type": "number", "enum": [0, 0.5]}},
            },
        },
        "resume": {"type": "string", "maxLength": RESUME_MAX},
    },
}
DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["coefficients", "validity_h", "justification"],
    "properties": {
        "coefficients": {"type": "array", "maxItems": len(INSTRUMENTS), "items": _ITEM},
        "validity_h": {"type": "integer", "minimum": 1, "maximum": VALIDITY_MAX_H},
        "justification": {"type": "string", "maxLength": JUSTIFICATION_MAX},
    },
}


def member_prompt(member: Member) -> str:
    stage_file = "president.md" if member.stage == "C" else "opinions.md"
    parts = [PROMPT_DIR / "common.md", PROMPT_DIR / "roles" / member.file, PROMPT_DIR / stage_file]
    return "\n\n".join(p.read_text(encoding="utf-8").strip() for p in parts) + "\n"


def member_sha256(member: Member) -> str:
    return hashlib.sha256(member_prompt(member).encode("utf-8")).hexdigest()


def prompts_sha256() -> str:
    return hashlib.sha256("".join(f"{m.key}:{member_sha256(m)}\n" for m in MEMBERS).encode()).hexdigest()


def _halves(v: Any, allowed: tuple[int, ...]) -> int:
    """0, 0.5 or 1 as halves (0, 1, 2); ValueError for anything else (a bool, a string, 0.3...)."""
    if isinstance(v, bool) or not isinstance(v, int | float | Decimal):
        raise TypeError("coefficient: a number is expected")
    try:
        h = Decimal(str(v)) * 2
    except InvalidOperation as exc:
        raise ValueError("coefficient: not a number") from exc
    if not h.is_finite() or h != h.to_integral_value() or int(h) not in allowed:
        raise ValueError(f"coefficient: one of {[HALVES[a] for a in allowed]}")
    return int(h)


def _items(raw: Any, allowed: tuple[int, ...]) -> list[dict[str, Any]]:
    """The valid items of a list of {instrument, coefficient, reason}; an invalid item is dropped alone (the
    contract then keeps 1). A coefficient below 1 needs a reason."""
    if not isinstance(raw, list) or len(raw) > len(INSTRUMENTS):
        raise ValueError(f"a list of 0 to {len(INSTRUMENTS)} elements is expected")
    out: dict[str, dict[str, Any]] = {}
    for a in raw:
        try:
            if not isinstance(a, dict) or set(a) != {"instrument", "coefficient", "reason"}:
                raise ValueError("unexpected keys")
            if a["instrument"] not in INSTRUMENTS or not isinstance(a["reason"], str):
                raise ValueError("instrument or reason")
            h = _halves(a["coefficient"], allowed)
            reason = " ".join(a["reason"].split())[:REASON_MAX]
            if h < 2 and not reason:
                raise ValueError("a coefficient below 1 needs a reason")
        except (ValueError, TypeError):
            continue
        out[a["instrument"]] = {"instrument": a["instrument"], "halves": h, "reason": reason}
    return list(out.values())


def parse_proposals(data: Any) -> tuple[dict[str, Any] | None, str | None]:
    """(normalized member opinion | None, error | None). Never raises."""
    try:
        if (
            not isinstance(data, dict)
            or set(data) != {"proposals", "resume"}
            or not isinstance(data["resume"], str)
        ):
            raise ValueError("an object {proposals, resume} is expected")
        items = [i for i in _items(data["proposals"], (0, 1)) if i["halves"] < 2]
    except (ValueError, TypeError) as exc:
        return None, f"invalid opinion: {str(exc)[:300]}"
    return {
        "opinions": [],
        "target": None,
        "argument": " ".join(data["resume"].split())[:RESUME_MAX],
        "proposals": [
            {"instrument": i["instrument"], "coefficient": HALVES[i["halves"]], "reason": i["reason"]}
            for i in items
        ],
    }, None


def parse_president(data: Any) -> tuple[dict[str, Any] | None, str | None]:
    """(normalized decision | None, error | None): `halves` per contract with its reason, the validity in hours,
    the justification. A contract not listed, or listed invalidly, is 1. Never raises."""
    try:
        if not isinstance(data, dict) or set(data) != {"coefficients", "validity_h", "justification"}:
            raise ValueError("an object {coefficients, validity_h, justification} is expected")
        v = data["validity_h"]
        if isinstance(v, Decimal) and v == v.to_integral_value():
            v = int(v)
        if type(v) is not int or not 1 <= v <= VALIDITY_MAX_H:
            raise ValueError(f"validity_h: an integer from 1 to {VALIDITY_MAX_H}")
        if not isinstance(data["justification"], str):
            raise TypeError("justification: a string is expected")
        items = _items(data["coefficients"], (0, 1, 2))
    except (ValueError, TypeError) as exc:
        return None, f"invalid decision: {str(exc)[:300]}"
    return {
        "halves": {i["instrument"]: (i["halves"], i["reason"]) for i in items},
        "validity_h": v,
        "justification": " ".join(data["justification"].split())[:JUSTIFICATION_MAX],
    }, None


def merge_brakes(
    new: Mapping[str, tuple[int, str]],
    until_ts: int,
    prior: Mapping[str, Brake],
    *,
    only_lower: bool,
) -> dict[str, Brake]:
    """The coefficients in force after a council: only those below 1 are kept. In a `veto` round
    (`only_lower`) a contract already braked keeps the lowest of the two: a round can never raise a coefficient."""
    out: dict[str, Brake] = {}
    for inst in INSTRUMENTS:
        h, why = new.get(inst, (2, ""))
        old = prior.get(inst)
        if only_lower and old is not None:
            if h < old.halves:
                out[inst] = Brake(h, until_ts, why)
            else:
                out[inst] = old
        elif h < 2:
            out[inst] = Brake(h, until_ts, why)
    return out


def brakes_payload(brakes: Mapping[str, Brake]) -> dict[str, Any]:
    return {i: {"c": HALVES[b.halves], "until_ts": b.until_ts, "why": b.why} for i, b in brakes.items()}


def brakes_from_payload(raw: Any) -> dict[str, Brake]:
    out: dict[str, Brake] = {}
    if isinstance(raw, Mapping):
        for inst, b in raw.items():
            try:
                h = next(k for k, v in HALVES.items() if v == b["c"])
                out[str(inst)] = Brake(h, int(b["until_ts"]), str(b.get("why") or ""))
            except (KeyError, TypeError, ValueError, StopIteration):
                continue
    return out


def brakes_in_force(events: Sequence[Mapping[str, Any]], portfolio: str, end_ts: int) -> dict[str, Brake]:
    """The coefficients left by the portfolio's last decision of the bar that closed at `end_ts` (none: empty).
    The caller drops those whose validity ended."""
    last: Mapping[str, Any] | None = None
    for e in events:
        t = (
            e["payload"].get("trend")
            if e["type"] == "agent_decision" and e["payload"].get("portfolio") == portfolio
            else None
        )
        if isinstance(t, Mapping) and t.get("bar_end_ts") == end_ts:
            last = t
    return brakes_from_payload(last.get("coefficients")) if last else {}


def latest_engine(events: Sequence[Mapping[str, Any]], portfolio: str, end_ts: int) -> EngineTarget | None:
    """The engine target journaled for the bar that closed at `end_ts` (status ok), else None."""
    found = None
    for e in events:
        p = e["payload"]
        if (
            e["type"] == "trend_engine_target"
            and p.get("portfolio") == portfolio
            and p.get("bar_end_ts") == end_ts
            and p.get("status") == "ok"
        ):
            found = p
    return EngineTarget.from_payload(found) if found else None


def bar_played(events: Sequence[Mapping[str, Any]], portfolio: str, end_ts: int) -> bool:
    """The council has played (or been skipped for) the bar round of the bar that closed at `end_ts`."""
    return any(
        e["type"] in ("round_data", "perp_llm_skipped")
        and e["payload"].get("portfolio") == portfolio
        and e["payload"].get("round") == end_ts
        for e in events
    )


def expired_brakes(events: Sequence[Mapping[str, Any]], portfolio: str, now_ts: int) -> bool:
    """A brake of the current bar whose validity ended and was not lifted yet: a `restoration` round is due."""
    end_ts = bar_close(now_ts)
    return any(b.until_ts <= now_ts for b in brakes_in_force(events, portfolio, end_ts).values())


# ---------------------------------------------------------------------- the decider


def _result_cost(m: Member, r: AgentResult, ceiling: int) -> int:
    return max(r.cost_uusd, ceiling) if _used_model(r) else r.cost_uusd


@dataclass
class VetoMemberDecider(MemberDecider):
    """One member's call of the council v4: its own prompts (council-trend), its own schema."""

    def system_prompt(self) -> str:
        return member_prompt(self.member)

    def prompt_digest(self) -> str:
        return member_sha256(self.member)


@dataclass
class TrendDecider:
    """The council v4 as the decider of a round (same interface as `AgentDecider`: `decide(round_dir,
    snapshot) -> AgentResult`). Its decision is the list of standard actions that follow from the engine's
    target and the coefficients; the veto council runs only when `veto` is true."""

    config: CouncilConfig
    workdir: Path
    engine: EngineTarget
    now_ts: int
    exposure_bp: Callable[
        [], Mapping[str, int]
    ]  # the current positions, bp of the equity (read when planning)
    kind: str = "bar"
    prior: Mapping[str, Brake] = field(default_factory=dict)  # the coefficients in force before the round
    veto: bool = True
    no_veto_reason: str | None = None
    runner: Runner = _default_runner
    python: str = sys.executable
    effort: str | None = "low"
    max_budget_usd: str = "1.00"  # the ceiling of the whole round, set by the watcher
    slots: threading.Semaphore | None = None
    # time.monotonic() by which every model call has ended (a bar round started just before a spot cycle), or None
    deadline: float | None = None
    shrink_on_refusal = True  # read by `finish_agent_round`: an entry refused for its size is retried smaller
    max_actions = MAX_ACTIONS

    @property
    def model(self) -> str:
        return self.config.president_model

    @property
    def portfolio(self) -> str:
        return self.config.portfolio

    @property
    def max_size_pct(self) -> int:
        return max(100, self.config.policy.max_order_bp * 100 // BP)

    def prompt_digest(self) -> str:
        return member_sha256(PRESIDENT)

    def timeout_s(self, president: bool) -> float:
        """A call's timeout: the configured one, cut by the deadline (the members, called first, get half of
        the time left, the President all of it)."""
        base = float(self.config.president_timeout_s if president else self.config.member_timeout_s)
        if self.deadline is None:
            return base
        left = self.deadline - time.monotonic()
        return max(0.0, min(base, left if president else left / 2))

    def _member(
        self, member: Member, opinions: list[dict[str, Any]] | None, ceiling: str
    ) -> VetoMemberDecider:
        president = member.stage == "C"
        return VetoMemberDecider(
            self.config.president_model if president else self.config.model, self.config.portfolio,
            self.workdir, self.runner, max_tool_calls=self.config.member_max_tool_calls, max_turns=7,
            timeout_s=self.timeout_s(president),
            python=self.python, max_budget_usd=ceiling, effort=self.effort, member=member, opinions=opinions,
            schema=DECISION_SCHEMA if president else PROPOSAL_SCHEMA,
        )  # fmt: skip

    def message(self, snapshot: Mapping[str, Any]) -> str:
        """The first message of the members (its sha256 goes in `round_data`)."""
        return self._member(STAGE_A[0], None, self.max_budget_usd).message(snapshot)

    def member_ceiling_uusd(self, member: Member) -> int:
        """Half of the round's ceiling for the President (Opus), an eighth for each of the three members."""
        total = int(Decimal(self.max_budget_usd) * 1_000_000)
        return max(1, total // 2) if member.stage == "C" else max(1, total // 8)

    def _worth_calling(self) -> bool:
        """Nothing to brake when the engine holds nothing and neither does the account."""
        return any(t != 0 for t in self.engine.target_bp.values()) or any(self.exposure_bp().values())

    def decide(self, round_dir: Path, snapshot: Mapping[str, Any]) -> AgentResult:
        """Never raises: whatever fails in the veto council, the coefficients stay 1 (engine alone) and the cost
        of the calls made is returned (the league's budget counts it)."""
        t0 = time.monotonic()
        done: list[tuple[Member, AgentResult]] = []
        records: list[dict[str, Any]] = []
        president: dict[str, Any] | None = None
        pres_error: str | None = None
        called = False
        off = self.no_veto_reason
        if self.veto and not self._worth_calling():
            off = "nothing_to_brake"
        elif self.veto and self.timeout_s(False) < MIN_CALL_S:
            off = "spot_cycle"  # too little time before the spot cycle: the two leagues never call models together
        elif self.veto:
            called = True
            try:
                (round_dir / "stream.jsonl").write_bytes(b"")  # the council is called: never replayed if cut
                records, president, pres_error = self._council(round_dir, snapshot, done)
            except Exception as exc:  # noqa: BLE001 (the council's failure never stops the engine)
                pres_error = f"council crashed: {type(exc).__name__}: {str(exc)[:200]}"
                president = None
        end_ts = self.engine.end_ts
        next_bar = end_ts + BAR_S
        valid = {i: b for i, b in self.prior.items() if b.until_ts > self.now_ts}
        if self.kind == "restoration":
            brakes = dict(valid)
        elif president is not None:
            until = min(next_bar, self.now_ts + president["validity_h"] * 3600)
            brakes = merge_brakes(president["halves"], until, valid, only_lower=self.kind == "veto")
        else:  # no council, or a failure of its President: the coefficients in force stay (veto) or are 1 (bar)
            brakes = dict(valid) if self.kind == "veto" else {}
        final = final_targets(self.engine.target_bp, brakes)
        exposure = dict(self.exposure_bp())
        actions = plan_actions(final, exposure, self.engine.held, self.config.trend)  # type: ignore[arg-type]
        res = AgentResult(
            decision={"actions": actions, "justification": self._justification(final, brakes, actions, decided=president is not None)},
            assistant_seen=any(r.assistant_seen for _, r in done),
            result_seen=True,  # the cost below already charges every call that used the model without a result
        )
        pres = next((r for m, r in done if m.stage == "C"), None)
        if pres is not None:
            res.mcp_status, res.model_returned, res.num_turns = (
                pres.mcp_status,
                pres.model_returned,
                pres.num_turns,
            )
            res.attempts, res.rc, res.first_error = pres.attempts, pres.rc, pres.first_error
            res.stderr_tail, res.tools_offered = pres.stderr_tail, pres.tools_offered
        for m, r in done:
            res.input_tokens += r.input_tokens
            res.output_tokens += r.output_tokens
            res.cache_read_tokens += r.cache_read_tokens
            res.cache_write_tokens += r.cache_write_tokens
            res.cost_uusd += _result_cost(m, r, self.member_ceiling_uusd(m))
        n = 0
        for m, r in done:
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
                "president_cost_uusd": pres.cost_uusd if pres is not None else 0,
                "president_latency_ms": pres.latency_ms if pres is not None else 0,
                "president_tool_calls": len(pres.tool_calls) if pres is not None else 0,
            },
            "trend": {
                "kind": self.kind,
                "bar_ts": self.engine.bar_ts,
                "bar_end_ts": end_ts,
                "engine_version": ENGINE_VERSION,
                "params_sha256": params_sha256(),
                "targets_bp": dict(self.engine.target_bp),
                "final_bp": final,
                "held": dict(self.engine.held),
                "exposure_bp": exposure,
                "coefficients": brakes_payload(brakes),
                "council_called": called,
                "council_off": off,
                "president_ok": president is not None,
                "president_error": pres_error,
                "validity_h": president["validity_h"] if president else None,
                "justification": president["justification"] if president else None,
            },
        }
        res.latency_ms = int((time.monotonic() - t0) * 1000)
        try:  # the audit file: its failure never loses the round
            (round_dir / "council.json").write_text(
                json.dumps({"opinions": records, "trend": res.extra["trend"]}, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
        except OSError:
            pass
        return res

    def _council(
        self, round_dir: Path, snapshot: Mapping[str, Any], done: list[tuple[Member, AgentResult]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None, str | None]:
        """The three members in parallel, then the President. (opinion records, the President's decision or
        None, why it is None)."""

        def run(member: Member, opinions: list[dict[str, Any]] | None) -> AgentResult:
            mdir = round_dir / "members" / member.key
            ceiling = f"{Decimal(self.member_ceiling_uusd(member)).scaleb(-6):.6f}"
            try:
                mdir.mkdir(parents=True, exist_ok=True)
                (mdir / "round.json").write_bytes((round_dir / "round.json").read_bytes())
                with self.slots if self.slots is not None else nullcontext():
                    r = self._member(member, opinions, ceiling).decide(mdir, snapshot)
            except Exception as exc:  # noqa: BLE001 (one member's failure never stops the round)
                r = AgentResult(
                    error=f"member crashed: {type(exc).__name__}: {str(exc)[:200]}",
                    cost_uusd=stream_cost_uusd(mdir / "stream.jsonl"),
                    result_seen=True,
                )
            done.append((member, r))
            return r

        with ThreadPoolExecutor(max_workers=self.config.members_parallel) as pool:
            stage_a = dict(zip(STAGE_A, pool.map(lambda m: run(m, None), STAGE_A), strict=True))
        records: list[dict[str, Any]] = []
        seen: list[dict[str, Any]] = []
        for m in STAGE_A:
            r = stage_a[m]
            opinion, error = (None, r.error)
            if r.decision is not None:
                opinion, error = parse_proposals(r.decision)
            records.append(
                {
                    "member": m.key,
                    "name": m.name,
                    "stage": m.stage,
                    "persona_sha256": member_sha256(m),
                    "opinion": opinion,
                    "error": None if opinion is not None else (error or "no opinion")[:300],
                    "cost_uusd": _result_cost(m, r, self.member_ceiling_uusd(m)),
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "cache_read_tokens": r.cache_read_tokens,
                    "cache_write_tokens": r.cache_write_tokens,
                    "latency_ms": r.latency_ms,
                    "tool_calls": len(r.tool_calls),
                    "model_returned": r.model_returned,
                    "stream_sha256": r.stream_sha256,
                }
            )
            if opinion is not None:
                seen.append({"member": m.name, "role": m.key, **opinion})
        if self.timeout_s(True) < MIN_CALL_S:
            return records, None, "president: not called, the spot cycle is too close"
        pres = run(PRESIDENT, seen)
        try:  # the members' streams, in one file like the other councils
            streams = b"".join(
                (round_dir / "members" / m.key / "stream.jsonl").read_bytes()
                for m in MEMBERS
                if (round_dir / "members" / m.key / "stream.jsonl").exists()
            )
            (round_dir / "stream.jsonl").write_bytes(streams)
        except OSError:
            pass
        if pres.decision is None:
            return records, None, f"president: {pres.error or 'no decision'}"[:300]
        decision, error = parse_president(pres.decision)
        return records, decision, None if decision is not None else error

    def _justification(
        self,
        final: Mapping[str, int],
        brakes: Mapping[str, Brake],
        actions: Sequence[Mapping[str, Any]],
        decided: bool = True,
    ) -> str:
        eng = ", ".join(
            f"{i.removeprefix('PF_').removesuffix('USD')} {t / 100:+.0f}%"
            for i, t in self.engine.target_bp.items()
        )
        brk = ", ".join(
            f"{i.removeprefix('PF_').removesuffix('USD')} x{HALVES[b.halves]}" for i, b in brakes.items()
        )
        if not brk:  # "the engine alone" only when the council did not decide
            brk = "no brake, following the engine" if decided else "none, the engine alone (the council did not decide)"
        return f"Trend engine ({self.kind}): targets {eng}. Council coefficients: {brk}. {len(actions)} order(s)."[
            :1200
        ]


# ---------------------------------------------------------------------- one round


def snapshot_blocks(engine: EngineTarget, brakes: Mapping[str, Brake], now_ts: int) -> dict[str, Any]:
    """The blocks the council reads besides the usual snapshot: the engine's target, its record, the brakes."""
    return {
        "engine_target": {
            i: {
                "target_pct_equity": format((Decimal(t) / 100).normalize(), "f"),
                "z": engine.z.get(i),
                "daily_volatility_pct": format((Decimal(engine.vol_day_bp.get(i, 0)) / 100).normalize(), "f"),
                "data": f"incomplete ({engine.held[i]}): the contract keeps its position"
                if i in engine.held
                else "ok",
            }
            for i, t in engine.target_bp.items()
        },
        "closed_bar_utc": engine.end_ts,
        "engine_summary": ENGINE_SUMMARY,
        "coefficients_in_force": {
            i: {"coefficient": HALVES[b.halves], "reason": b.why, "valid_until_utc": b.until_ts}
            for i, b in brakes.items()
            if b.until_ts > now_ts
        },
    }


def journal_engine(sim: PerpSimulator, portfolio: str, engine: EngineTarget, now_ts: int) -> None:
    """`trend_engine_target`, once per portfolio and bar (written before any deliberation)."""
    if not any(
        e["type"] == "trend_engine_target"
        and e["payload"].get("portfolio") == portfolio
        and e["payload"].get("bar_end_ts") == engine.end_ts
        and e["payload"].get("status") == "ok"
        for e in sim.journal.events()
    ):
        sim.append_event("trend_engine_target", engine.payload(portfolio), now_ts)


def journal_engine_error(sim: PerpSimulator, portfolio: str, end_ts: int, error: str, now_ts: int) -> None:
    """The engine could not be computed: one `trend_engine_target` with status `error` per portfolio and bar."""
    if not any(
        e["type"] == "trend_engine_target"
        and e["payload"].get("portfolio") == portfolio
        and e["payload"].get("bar_end_ts") == end_ts
        for e in sim.journal.events()
    ):
        sim.append_event(
            "trend_engine_target",
            {"portfolio": portfolio, "status": "error", "bar_end_ts": end_ts, "error": error[:300],
             "engine_version": ENGINE_VERSION, "params_sha256": params_sha256()},
            now_ts,
        )  # fmt: skip


def play_benchmark(
    *,
    cfg: CouncilConfig,
    engine: EngineTarget,
    sim: PerpSimulator,
    view: PerpMarketView,
    specs: Mapping[str, InstrumentSpec],
    now_ts: int,
    entries_blocked: bool | Callable[[], bool],
) -> int:
    """The shadow benchmark of the bar: the engine's target, every coefficient 1, through the same execution path
    as the council (`parse_decision`, then `run_intents`). Returns the number of orders judged."""
    assert cfg.trend is not None
    name = cfg.trend.benchmark
    marks = {s: m.mark_uusd for s, m in view.instruments.items()}
    acc = sim.states()[name]
    eq = equity_ueur(acc, marks, view.fx_bid, view.fx_ask)
    actions = plan_actions(
        final_targets(engine.target_bp, {}),
        current_exposure_bp(acc, marks, view.fx_bid, eq),
        engine.held,
        cfg.trend,
    )
    _parsed, error, intents = parse_decision(
        {"actions": actions, "justification": "engine-only benchmark"},
        name, engine.end_ts, now_ts, max_size_pct=max(100, cfg.policy.max_order_bp * 100 // BP), max_actions=MAX_ACTIONS,
    )  # fmt: skip
    if error is not None:
        raise ValueError(error)
    run_intents(sim, name, intents, view, specs, cfg.policy, now_ts, entries_blocked, shrink=True)
    return len(intents)


@dataclass
class TrendRoundResult:
    notes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    called: int = 0
    failed: int = 0


def run_trend_round(
    *,
    cfg: CouncilConfig,
    kind: str,
    trigger: Mapping[str, Any] | None,
    now_ts: int,
    var: Path,
    sim: PerpSimulator,
    store: PerpDataStore,
    view: PerpMarketView,
    specs: Mapping[str, InstrumentSpec],
    config_sha256: str,
    entries_blocked: bool | Callable[[], bool],
    refresh: Callable[[], tuple[PerpMarketView, int] | None] | None = None,
    news: Any = None,
    llm_sha256: str = "",
    league_sha256: str = "",
    effort: str | None = "low",
    ceiling_uusd: int = 1_000_000,
    veto_allowed: bool = True,
    no_veto_reason: str | None = None,
    runner: Runner = _default_runner,
    slots: threading.Semaphore | None = None,
    workdir: Path = Path("/var/tmp/arena-perp-claude-empty"),
    engine: EngineTarget | None = None,
    deadline: float | None = None,
) -> TrendRoundResult:
    """Plays one round of the council v4 (and, for a `bar`, of its shadow). Every outcome is journaled; an
    engine failure leaves every position as it is (fail closed). `engine`: given for the tests; otherwise a
    `bar` computes it from the store and the other kinds read the one journaled for the current bar.
    `deadline`: time.monotonic() by which the model calls have ended (see `TrendDecider.deadline`)."""
    assert cfg.trend is not None and kind in KINDS
    rep = TrendRoundResult()
    name, bench = cfg.portfolio, cfg.trend.benchmark
    sim.open_portfolio(name, "council", now_ts)
    sim.open_portfolio(bench, "benchmark", now_ts)
    end_ts = bar_close(now_ts)
    events = sim.journal.events()
    if engine is None:
        if kind == "bar":
            try:
                engine = engine_target(store, now_ts)
            except Exception as exc:  # noqa: BLE001 (no engine, no order: the positions stay)
                msg = f"{type(exc).__name__}: {exc}"
                for pf in (name, bench):
                    journal_engine_error(sim, pf, end_ts, msg, now_ts)
                rep.problems.append(f"trend engine not computed for the bar of {end_ts}: {msg}"[:300])
                return rep
        else:
            engine = latest_engine(events, name, end_ts)
            if engine is None:
                rep.notes.append(f"{kind}: no engine target for the bar of {end_ts}")
                return rep
    for pf in (name, bench):
        journal_engine(sim, pf, engine, now_ts)
    markers = {
        (e["payload"]["benchmark"], e["payload"]["period"])
        for e in sim.journal.events()
        if e["type"] == "perp_benchmark_done"
    }
    if kind == "bar" and (bench, str(end_ts)) not in markers:
        try:
            n = play_benchmark(
                cfg=cfg,
                engine=engine,
                sim=sim,
                view=view,
                specs=specs,
                now_ts=now_ts,
                entries_blocked=entries_blocked,
            )
            sim.append_event("perp_benchmark_done", {"benchmark": bench, "period": str(end_ts)}, now_ts)
            rep.notes.append(f"{bench}: {n} order(s)")
        except Exception as exc:  # noqa: BLE001 (the shadow never stops the council)
            rep.problems.append(f"{bench}: {type(exc).__name__}: {exc}"[:300])
    round_id = end_ts if kind == "bar" else now_ts // 300 * 300
    events = sim.journal.events()
    if any(
        e["type"] == "round_data"
        and e["payload"].get("portfolio") == name
        and e["payload"].get("round") == round_id
        for e in events
    ):
        if not any(
            e["type"] in ("agent_decision", "perp_llm_skipped")
            and e["payload"].get("portfolio") == name
            and e["payload"].get("round") == round_id
            for e in events
        ):  # interrupted after its calls began: never replayed (no second paid call); the next bar rebalances
            called = (var / "rounds" / str(round_id) / name.replace(":", "_") / "stream.jsonl").exists()
            sim.append_event(
                "perp_llm_skipped",
                {
                    "portfolio": name,
                    "round": round_id,
                    "reason": "interrupted_after_call" if called else "interrupted_before_call",
                },
                now_ts,
            )
            rep.notes.append(f"{name}: round {round_id} interrupted, not replayed")
        return rep
    if sim.states()[name].halted:
        sim.append_event(
            "perp_llm_skipped", {"portfolio": name, "round": round_id, "reason": "halted"}, now_ts
        )
        rep.notes.append(f"{name}: skipped (halted)")
        return rep
    prior = brakes_in_force(events, name, end_ts)
    marks = {s: m.mark_uusd for s, m in view.instruments.items()}

    def exposure() -> Mapping[str, int]:
        acc = sim.states()[name]
        return current_exposure_bp(acc, marks, view.fx_bid, equity_ueur(acc, marks, view.fx_bid, view.fx_ask))

    decider = TrendDecider(
        cfg, workdir, engine, now_ts, exposure, kind=kind, prior=prior, veto=kind != "restoration" and veto_allowed,
        no_veto_reason=no_veto_reason if kind != "restoration" else "restoration", runner=runner, effort=effort,
        max_budget_usd=f"{Decimal(ceiling_uusd).scaleb(-6):.6f}", slots=slots, deadline=deadline,
    )  # fmt: skip
    try:
        ctx = prepare_agent_round(
            var=var, sim=sim, store=store, decider=decider, view=view, specs=specs, policy=cfg.policy,
            config_sha256=config_sha256, round_id=round_id, now_ts=now_ts, kind=kind,
            trigger=trigger if trigger is not None else {"bar_utc": end_ts}, entries_blocked=entries_blocked,
            extra={
                "llm_config_sha256": llm_sha256, "budget_ceiling_uusd": ceiling_uusd,
                "council_config_sha256": cfg.sha256, "councils_league_sha256": league_sha256,
                "trend_params_sha256": params_sha256(),
            },
            snapshot_extra={
                **snapshot_blocks(engine, prior, now_ts),
                "council_summary": council_record(sim.journal.events(), name, now_ts),
            },
            news=news,
        )  # fmt: skip
    except Exception as exc:  # noqa: BLE001
        sim.append_event(
            "perp_llm_skipped",
            {
                "portfolio": name,
                "round": round_id,
                "reason": f"prepare_error: {type(exc).__name__}: {str(exc)[:200]}",
            },
            now_ts,
        )
        rep.failed += 1
        rep.problems.append(f"{name}: prepare error {type(exc).__name__}")
        return rep
    if not hasattr(ctx, "out_dir"):  # an AgentResult: this portfolio already played this round
        return rep
    rep.called = 1
    try:
        res = ctx.decider.decide(ctx.out_dir, ctx.snapshot)
    except Exception as exc:  # noqa: BLE001 (the decision event is always written)
        res = AgentResult(error=f"decider crashed: {type(exc).__name__}: {str(exc)[:200]}")
    fresh = None
    if refresh is not None:
        try:
            fresh = refresh()
        except Exception as exc:  # noqa: BLE001 (a store error never loses a paid call)
            rep.notes.append(f"market view not read again: {type(exc).__name__}")
    execute = refresh is None or fresh is not None
    if fresh is not None:
        ctx.view, ctx.now_ts = fresh
    try:
        finish_agent_round(
            ctx, res,
            extra={"budget_ceiling_uusd": ceiling_uusd, "result_seen": res.result_seen, "charge_ceiling": charge_ceiling(res)},
            execute=execute,
        )  # fmt: skip
    except Exception as exc:  # noqa: BLE001 (the cost is journaled whatever happens)
        rep.problems.append(f"{name}: finish failed: {type(exc).__name__}: {exc}"[:300])
        rep.failed += 1
    if res.error:
        rep.failed += 1
    rep.notes.append(
        f"{name}: {kind}{' error: ' + res.error[:80] if res.error else ''} ({res.cost_uusd} uusd)"
    )
    return rep
