"""The LLM portfolios of the perp league (step 7): configuration, daily budgets, and the agent rounds of one
league round, run by the watcher.

The four models decide at the same rendez-vous (D8): their round data are built and journaled one by one,
the `claude -p` calls run in parallel (at most `max_parallel`), then each decision is applied one by one, so
the journal keeps a single writer. A model over its daily budget, or halted, skips the round; a portfolio whose
round was interrupted after its `round_data` is never called again for that round (no second paid call).

The councils of the league of the councils (`arene/perp/council.py`, config/ligue-conseils.toml,
docs/SPEC-LIGUE-CONSEILS.md) are more players when their configuration is loaded (`LlmLeague.councils`): each
plays with the models (`LlmLeague.players`), under its own policy (`policy_of`), and its eleven calls run inside
its one slot of the pool; their member processes together are bounded by `max_member_processes`.
"""

from __future__ import annotations

import hashlib
import threading
import tomllib
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from arene.perp.agent import DEFAULT_WORKDIR, TIMEOUT_RC, AgentDecider, AgentResult, stream_cost_uusd
from arene.perp.agent_round import finish_agent_round, prepare_agent_round
from arene.perp.council import CouncilConfig, CouncilDecider, CouncilsLeague, council_record

REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_LLM_CONFIG = REPO / "config" / "perp-llm.toml"
PREFIX = "llm-perp:"


class LlmConfigError(ValueError):
    pass


@dataclass(frozen=True)
class LlmModel:
    portfolio: str
    model: str
    daily_budget_uusd: int
    council: bool = False  # a council: eleven calls per round, its own policy


@dataclass(frozen=True)
class LlmLeague:
    enabled: bool
    wakeups: bool
    rounds_per_day: int
    cadence_min: int
    max_parallel: int
    timeout_s: int
    max_budget_usd: str
    effort: str | None
    models: tuple[LlmModel, ...]
    sha256: str
    # loaded on their own (config/ligue-conseils.toml): None when the league file is invalid or missing
    councils: CouncilsLeague | None = None

    def council(self, portfolio: str) -> CouncilConfig | None:
        """The configuration of a council that is loaded (enabled or not), else None."""
        return self.councils.council(portfolio) if self.councils is not None else None

    @property
    def players(self) -> tuple[LlmModel, ...]:
        """The models, then the councils that are on."""
        if self.councils is None:
            return self.models
        return (
            *self.models,
            *(
                LlmModel(c.portfolio, c.president_model, c.daily_budget_uusd, council=True)
                for c in self.councils.councils
                if c.enabled
            ),
        )


def _usd_to_uusd(v: Any, key: str) -> int:
    try:
        d = Decimal(str(v))
    except InvalidOperation as exc:
        raise LlmConfigError(f"{key}: not a decimal amount") from exc
    if not isinstance(v, str) or not d.is_finite() or d <= 0 or d > 100:
        raise LlmConfigError(f"{key}: a positive amount as a string (at most 100) is expected")
    return int(d * 1_000_000)


def load_llm_league(path: Path = DEFAULT_LLM_CONFIG) -> LlmLeague:
    try:
        raw = path.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise LlmConfigError(f"unreadable {path}: {exc}") from exc
    expected = {
        "enabled",
        "wakeups",
        "rounds_per_day",
        "cadence_min",
        "max_parallel",
        "timeout_s",
        "max_budget_usd",
        "effort",
        "models",
    }
    if set(data) != expected:
        raise LlmConfigError(f"keys: expected {sorted(expected)}, got {sorted(data)}")
    if type(data["enabled"]) is not bool or type(data["wakeups"]) is not bool:
        raise LlmConfigError("enabled and wakeups are booleans")
    if type(data["rounds_per_day"]) is not int or not 6 <= data["rounds_per_day"] <= 288:
        raise LlmConfigError("rounds_per_day: 6 (the rendez-vous) to 288 (one per tick)")
    cadence = data["cadence_min"]
    if type(cadence) is not int or not (cadence == 0 or 5 <= cadence <= 60):
        raise LlmConfigError("cadence_min: 0 (off) or 5 to 60")
    if type(data["max_parallel"]) is not int or not 1 <= data["max_parallel"] <= 4:
        raise LlmConfigError("max_parallel: 1 to 4")
    if type(data["timeout_s"]) is not int or not 30 <= data["timeout_s"] <= 600:
        raise LlmConfigError("timeout_s: 30 to 600")
    _usd_to_uusd(data["max_budget_usd"], "max_budget_usd")
    if data["effort"] not in ("", "low", "medium", "high"):
        raise LlmConfigError("effort: '', low, medium or high")
    models = []
    if not isinstance(data["models"], list) or (data["enabled"] and not data["models"]):
        raise LlmConfigError("models: a non-empty list when enabled")
    for m in data["models"]:
        if not isinstance(m, dict) or not all(isinstance(m.get(k), str) for k in ("portfolio", "model")):
            raise LlmConfigError(f"model entry: portfolio and model are strings: {m!r}")
        if set(m) != {"portfolio", "model", "daily_budget_usd"}:
            raise LlmConfigError(f"model entry keys: {sorted(m)}")
        if not m["portfolio"].startswith(PREFIX) or m["portfolio"] != PREFIX + m["model"]:
            raise LlmConfigError(f"portfolio must be {PREFIX}<model>: {m['portfolio']}")
        models.append(LlmModel(m["portfolio"], m["model"], _usd_to_uusd(m["daily_budget_usd"], m["model"])))
    if len({m.portfolio for m in models}) != len(models):
        raise LlmConfigError("duplicate portfolio")
    return LlmLeague(
        data["enabled"],
        data["wakeups"],
        data["rounds_per_day"],
        data["cadence_min"],
        data["max_parallel"],
        data["timeout_s"],
        data["max_budget_usd"],
        data["effort"] or None,
        tuple(models),
        hashlib.sha256(raw).hexdigest(),
    )


def call_cost_uusd(payload: Mapping[str, Any]) -> int:
    """What a decision counts against the budget: its reported cost, or its ceiling when a model ran but the
    call ended without a result (timeout, cut): the quota was used but the CLI did not say how much."""
    cost = int(payload.get("cost_uusd") or 0)
    if payload.get("charge_ceiling"):
        cost = max(cost, int(payload.get("budget_ceiling_uusd") or 0))
    return cost


def charge_ceiling(res: AgentResult) -> bool:
    """A call without a result event used the quota only if a model ran: a timeout, or an answer or a tool
    call seen in the stream. A CLI that never reached a model (network, login, spawn failure) costs nothing."""
    return not res.result_seen and (res.rc == TIMEOUT_RC or res.assistant_seen or bool(res.tool_calls))


def spent_today_uusd(events: Sequence[Mapping[str, Any]], portfolio: str, now_ts: int) -> int:
    """The decisions of the UTC day, plus what the rounds cut after their call cost (`perp_llm_skipped`, from
    their streams), plus, for the council, the opinions of a round cut while its decision was being journaled
    (its members were paid; the decision's cost would have included them)."""
    day = now_ts // 86_400
    decided = set()
    total = 0
    for e in events:
        if e["type"] == "agent_decision" and e["payload"].get("portfolio") == portfolio:
            decided.add(e["payload"].get("round"))
            if e["ts"] // 86_400 == day:
                total += call_cost_uusd(e["payload"])
        elif (
            e["type"] == "perp_llm_skipped"
            and e["payload"].get("portfolio") == portfolio
            and e["ts"] // 86_400 == day
        ):
            total += int(e["payload"].get("cost_uusd") or 0)
    return total + sum(
        int(e["payload"].get("cost_uusd") or 0)
        for e in events
        if e["type"] == "council_opinion"
        and e["payload"].get("portfolio") == portfolio
        and e["ts"] // 86_400 == day
        and e["payload"].get("round") not in decided
    )


def has_budget(model: LlmModel, events: Sequence[Mapping[str, Any]], now_ts: int) -> bool:
    """False when less than a twentieth of the model's daily budget is left (about one round)."""
    return (
        model.daily_budget_uusd - spent_today_uusd(events, model.portfolio, now_ts)
        >= model.daily_budget_uusd // 20
    )


def _usd(uusd: int) -> str:
    return f"{Decimal(uusd).scaleb(-6):.6f}"


@dataclass
class LlmRoundReport:
    notes: list[str]
    called: int = 0
    failed: int = 0


def run_llm_round(
    *,
    league: LlmLeague,
    var: Path,
    sim: Any,
    store: Any,
    view: Any,
    specs: Mapping[str, Any],
    policy: Any,
    config_sha256: str,
    round_id: int,
    now_ts: int,
    kind: str,
    trigger: Mapping[str, Any] | None,
    entries_blocked: Callable[[], bool],
    decider_factory: Callable[[LlmModel], AgentDecider] | None = None,
    refresh: Callable[[], tuple[Any, int] | None] | None = None,
    only: set[str] | None = None,
    triggers: Mapping[str, Mapping[str, Any]] | None = None,
    quota_of: Callable[[str], Mapping[str, int]] | None = None,
    policy_of: Callable[[str], Any] | None = None,
    news: Any = None,
) -> LlmRoundReport:
    """Plays the LLM part of one league round; every outcome is journaled (problems never stop the others).

    `refresh` gives the market view and time at which the decisions are executed (after the calls); without
    it, or when it returns None, they are executed on the round's view at its time.

    `only`: the portfolios allowed to play (a private round, or a market wake-up without the models out of
    rounds); the other models are not even looked at.

    `triggers`: in a private round, each portfolio's own trigger ({"kind": "alert" | "scheduled" | "cadence",
    ...}): its `kind` is the call type the model sees, and no model sees another's trigger. `quota_of(portfolio)`: its
    rounds of the day, shown in its snapshot. `policy_of(portfolio)`: its risk policy (the council has its own);
    `policy` for all without it."""
    rep = LlmRoundReport([])
    max_call = _usd_to_uusd(league.max_budget_usd, "max_budget_usd")
    slots = threading.BoundedSemaphore(league.councils.max_member_processes) if league.councils else None

    def make(m: LlmModel, ceiling: int) -> Any:
        if decider_factory is not None:
            d = decider_factory(m)
        elif m.council:
            cfg = league.council(m.portfolio)
            assert cfg is not None
            d = CouncilDecider(cfg, DEFAULT_WORKDIR, effort=league.effort, slots=slots)
        else:
            d = AgentDecider(
                m.model, m.portfolio, DEFAULT_WORKDIR, timeout_s=float(league.timeout_s), effort=league.effort
            )
        d.max_budget_usd = _usd(ceiling)
        return d

    for m in league.players:
        sim.open_portfolio(m.portfolio, "council" if m.council else "llm", now_ts)
    events = sim.journal.events()
    states = sim.states()

    def of_round(type_: str) -> set[str]:
        return {
            e["payload"]["portfolio"]
            for e in events
            if e["type"] == type_ and e["payload"].get("round") == round_id
        }

    started, decided, skipped = (
        of_round("round_data"),
        of_round("agent_decision"),
        of_round("perp_llm_skipped"),
    )
    models = [m for m in league.players if only is None or m.portfolio in only]
    for name in sorted(started - decided - skipped):
        # interrupted (power cut, kill): never called again, never executed late
        path = next(
            (e["payload"]["path"] for e in events if e["type"] == "round_data" and e["payload"].get("portfolio") == name
             and e["payload"].get("round") == round_id), "",
        )  # fmt: skip
        called = (var / path / "stream.jsonl").exists() if path else False
        reason = "interrupted_after_call" if called else "interrupted_before_call"
        skip: dict[str, Any] = {"portfolio": name, "round": round_id, "reason": reason}
        if called:  # what the cut calls cost, as their streams say (the council: its members' streams)
            members = sorted((var / path / "membres").glob("*/stream.jsonl"))
            skip["cost_uusd"] = sum(stream_cost_uusd(f) for f in members or [var / path / "stream.jsonl"])
        sim.append_event("perp_llm_skipped", skip, now_ts)
        rep.notes.append(f"{name}: {reason}, not replayed")
    played = started | skipped
    prepared = []
    for m in models:
        if m.portfolio in played or states[m.portfolio].retired:
            continue  # a retired council is never called, even if its file is still listed
        remaining = m.daily_budget_uusd - spent_today_uusd(events, m.portfolio, now_ts)
        reason = None
        if states[m.portfolio].halted:
            reason = "halted"
        elif not has_budget(m, events, now_ts):
            reason = "daily_budget"
        try:
            if reason is None:
                ceiling = min(max_call, remaining)
                own = triggers.get(m.portfolio) if triggers is not None else None
                extra: dict[str, Any] = {"llm_config_sha256": league.sha256, "budget_ceiling_uusd": ceiling}
                cfg = league.council(m.portfolio) if m.council else None
                if cfg is not None and league.councils is not None:
                    extra["council_config_sha256"] = cfg.sha256
                    extra["councils_league_sha256"] = league.councils.sha256
                ctx = prepare_agent_round(
                    var=var, sim=sim, store=store, decider=make(m, ceiling), view=view, specs=specs,
                    policy=policy_of(m.portfolio) if policy_of is not None else policy,
                    config_sha256=config_sha256, round_id=round_id, now_ts=now_ts,
                    kind=str(own["kind"]) if own else kind, trigger=own if triggers is not None else trigger,
                    entries_blocked=entries_blocked, extra=extra,
                    quota=quota_of(m.portfolio) if quota_of is not None else None,
                    news=news,
                    snapshot_extra=(
                        {"bilan_du_conseil": council_record(events, m.portfolio, now_ts)} if m.council else None
                    ),
                )  # fmt: skip
                if not isinstance(ctx, AgentResult):
                    prepared.append((ctx, ceiling))
                continue
        except Exception as exc:  # noqa: BLE001 (one model's failure never stops the others)
            reason = f"prepare_error: {type(exc).__name__}: {str(exc)[:200]}"
        sim.append_event(
            "perp_llm_skipped", {"portfolio": m.portfolio, "round": round_id, "reason": reason}, now_ts
        )
        rep.notes.append(f"{m.portfolio}: skipped ({reason})")
        if reason.startswith("prepare_error"):
            rep.failed += 1
    if not prepared:
        return rep

    def decide(ctx: Any) -> AgentResult:
        try:
            return ctx.decider.decide(ctx.out_dir, ctx.snapshot)
        except Exception as exc:  # noqa: BLE001 (the decision event is always written)
            return AgentResult(error=f"decider crashed: {type(exc).__name__}: {str(exc)[:200]}")

    rep.called = len(prepared)
    with ThreadPoolExecutor(max_workers=league.max_parallel) as pool:
        futures = {pool.submit(decide, ctx): (ctx, ceiling) for ctx, ceiling in prepared}
        for fut in as_completed(futures):  # each decision is journaled as soon as it is known
            ctx, ceiling = futures[fut]
            res = fut.result()
            fresh = None
            if refresh is not None:
                try:
                    fresh = refresh()
                except Exception as exc:  # noqa: BLE001 (a store error never loses a paid call)
                    rep.notes.append(f"market view not read again: {type(exc).__name__}")
            execute = refresh is None or fresh is not None
            if fresh is not None:
                ctx.view, ctx.now_ts = fresh
            extra = {
                "budget_ceiling_uusd": ceiling,
                "result_seen": res.result_seen,
                "charge_ceiling": charge_ceiling(res),
            }
            try:
                finish_agent_round(ctx, res, extra=extra, execute=execute)
            except Exception as exc:  # noqa: BLE001 (the cost is journaled whatever happens)
                _journal_cost_only(sim, ctx, res, ceiling, exc)
                res.error = res.error or f"finish failed: {type(exc).__name__}"
            if res.error:
                rep.failed += 1
            rep.notes.append(
                f"{ctx.name}: {'error: ' + res.error[:80] if res.error else 'decided'} ({res.cost_uusd} uusd)"
            )
    return rep


def _journal_cost_only(sim: Any, ctx: Any, res: AgentResult, ceiling: int, exc: Exception) -> None:
    """When finishing a decision failed: make sure its cost is in the journal (budgets), once."""
    with suppress(Exception):
        if any(
            e["type"] == "agent_decision"
            and e["payload"].get("portfolio") == ctx.name
            and e["payload"].get("round") == ctx.round_id
            for e in sim.journal.events()
        ):
            return
        sim.append_event(
            "agent_decision",
            {
                "portfolio": ctx.name, "round": ctx.round_id, "kind": ctx.kind, "model_requested": ctx.decider.model,
                "parsed": None, "parse_error": f"finish failed: {type(exc).__name__}: {str(exc)[:200]}",
                "cost_uusd": res.cost_uusd, "input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
                "cache_read_tokens": res.cache_read_tokens, "cache_write_tokens": res.cache_write_tokens,
                "latency_ms": res.latency_ms, "tool_calls": len(res.tool_calls), "result_seen": res.result_seen,
                "charge_ceiling": charge_ceiling(res), "budget_ceiling_uusd": ceiling,
                "stream_sha256": res.stream_sha256,
            },
            ctx.now_ts,
        )  # fmt: skip
