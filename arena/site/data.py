"""Computation of all the dashboard data from the journal ALONE (docs/SPEC-MVP.md §13).

`compute()` returns a dictionary ready for JSON (floats allowed: display only). Nothing here writes a file,
except the cache of the random trajectories (outside the repository, see `_distribution`). The models'
justifications are published as soon as the decision is made.

Watch and wake-ups (docs/WATCH.md): the live equity comes from `watch.equity`; `watch.raw_quotes` and the
`wakeup_quote` events are never used as a displayed price. Wake-ups are decision rounds outside the 4 h grid
(their `cycle` is the wake-up's tick), never cycles.

Season: as soon as a `season_reference` exists, every ranking and every measurement starts from its equity,
never from the initial capital; the burn-in before it is summarized apart.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import os
import re
import time
from collections import Counter
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path
from typing import Any

from arena import stats
from arena.config import Config
from arena.journal import Journal, verify
from arena.ledger import replay
from arena.risk.policy import Policy
from arena.site.luck import Round, price_paths_since
from arena.benchmarks.price_paths import CycleData
from arena.types import Bar, Instrument, Quote, notional_ueur

MIN_CYCLES_STATS = 30  # below this number of cycles: "too early" (Sharpe CI, distinction from chance)
BASELINE = "benchmark:basket"
RANDOM = "benchmark:random"
JUSTIFICATION_MAX = 2_000
DECISIONS_MAX = 200  # decisions kept per model page (the most recent ones)
CURVE_STEP_WATCH_S = 1_800  # one watch snapshot every 30 min on the curve (plus the last one)
WAKEUPS_MAX = 50

# Precisions of the universe (SPEC §1): the site does not receive AssetPairs, this is only used to replay the random benchmark.
_INSTRUMENT_TABLE = {
    "BTC/EUR": (100_000, 6_000),
    "ETH/EUR": (10_000, 200_000),
    "SOL/EUR": (10_000, 5_000_000),
    "XRP/EUR": (10, 400_000_000),
    "LINK/EUR": (10, 35_000_000),
    "LTC/EUR": (10_000, 8_000_000),
}
_COST_MIN_UEUR = 450_000

NAMES = {
    "llm:claude-haiku-5-5": "Claude Haiku 5.5",
    "llm:claude-sonnet-5-5": "Claude Sonnet 5.5",
    "llm:claude-opus-5-5": "Claude Opus 5.5",
    "llm:claude-fable-5-2": "Claude Fable 5.2",
    "benchmark:basket": "Benchmark basket",
    "benchmark:6040": "Benchmark 60/40",
    "benchmark:e0065": "Benchmark E0065 (adapted)",
    "benchmark:random": "Benchmark random",
}
DESCRIPTIONS = {
    "benchmark:basket": "1/6 of the portfolio in each of the 6 cryptos at the first cycle, then held: the market.",
    "benchmark:6040": "60% in bitcoin, 40% in euros, rebalanced at the start of each month.",
    "benchmark:e0065": "Fixed rule based on buying pressure (share of buys made at the market price), parameters L = 20, k = 3, H = 10.",
    "benchmark:random": "Draws 0 to 2 random actions per cycle, with exactly the same risk rules as the models.",
}

RISK_CODES = {
    "NOT_WHITELISTED": "pair outside the allowed list",
    "MAX_ORDER_SIZE": "order too large (per-order cap)",
    "MAX_POSITION": "position too large on this symbol",
    "MAX_EXPOSURE": "total exposure too high",
    "INSUFFICIENT_CASH": "insufficient cash (fees included)",
    "DAILY_TRADES": "24 h trade quota reached",
    "ORDER_RATE": "too many orders per minute",
    "TOO_SOON": "too soon after the last intent on this symbol",
    "STOP_REQUIRED": "buy without a stop",
    "STOP_RANGE": "stop outside the allowed bounds",
    "EDGE_TOO_SMALL": "estimated cost too large compared with the expected move",
    "FROZEN": "portfolio frozen",
    "HALTED": "portfolio halted (drawdown)",
    "FEE_BUDGET": "monthly fee budget reached",
    "PRICE_SANITY": "quote price too far from the last close",
    "SPREAD_ANOMALY": "abnormal bid/ask spread",
    "ORDER_TOO_SMALL": "order below the minimum",
    "NO_SHORT": "short selling not allowed",
    "KILL_SWITCH": "circuit breaker active",
    "NO_QUOTE": "no quote available",
    "NO_MARK": "no valuation price",
    "NO_EQUITY": "equity unavailable",
    "UNKNOWN_INSTRUMENT": "unknown instrument",
    "BAD_PARAMS": "invalid parameters",
    "BAD_SIDE": "invalid side",
    "BAD_SIZE": "invalid size",
    "INTERNAL_ERROR": "internal riskd error",
}

SKIP_REASONS = {
    "no_key": "model not yet connected",
    "budget": "daily API budget reached",
    "frozen": "portfolio frozen",
    "halted": "portfolio halted",
    "kill_switch": "circuit breaker active",
    "api_error": "API error",
}


def slug(portfolio: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", portfolio.lower()).strip("-")


def name(portfolio: str) -> str:
    return NAMES.get(portfolio, portfolio)


def _instruments(config: Config) -> dict[str, Instrument]:
    out = {}
    for ref in config.instrument_refs:
        tick, lot = _INSTRUMENT_TABLE.get(ref.symbol, (10, 1))
        out[ref.symbol] = Instrument(ref.symbol, ref.kraken_pair, ref.binance_symbol, tick, lot, _COST_MIN_UEUR)
    return out


def _cycle_data(
    events: list[dict[str, Any]], interval_s: int, wakeups: Mapping[int, dict[str, Any]] | None = None
) -> list[Round]:
    """Rebuild what the journal retained of each finished round: cycles (quotes, marks, 4 h bars) and
    completed wake-ups (`wakeup_quote` quotes, 1-minute closes of their tick, no bar), sorted by time.

    At a wake-up, only the quoted symbols are tradable (as at the real wake-up); the others keep their last
    mark for valuation."""
    completed = {e["payload"]["cycle"] for e in events if e["type"] == "cycle_completed"}
    wakeups = wakeups or {}
    cur: int | None = None
    quotes: dict[int, dict[str, Quote]] = {}
    bars: dict[int, dict[str, list[Bar]]] = {}
    closes_after: dict[int, dict[str, int]] = {}
    last_closes: dict[str, int] = {}
    order: list[int] = []
    rq: dict[int, dict[str, Quote]] = {}
    close_1m: dict[int, dict[str, int]] = {}
    watch_mids: list[tuple[int, dict[str, int]]] = []  # (tick, mids of the ACCEPTED quotes) in journal order
    cur_wakeup: int | None = None
    for e in events:
        t, p = e["type"], e["payload"]
        if t == "wakeup_started":
            cur_wakeup = p["wakeup"]
            continue
        if t in ("wakeup_completed", "wakeup_abandoned"):
            if p.get("wakeup") == cur_wakeup:
                cur_wakeup = None
            continue
        if t == "wakeup_quote":
            # Attached to the open wake-up that precedes it (wake-ups do not overlap); `ts` is the time of the
            # quote, not necessarily the wake-up's tick.
            if cur_wakeup is not None:
                rq.setdefault(cur_wakeup, {})[p["symbol"]] = Quote(p["symbol"], p["ts"], p["bid"], p["ask"])
            continue
        if t == "watch":
            if p.get("tick") in wakeups:
                close_1m[p["tick"]] = dict(p.get("closes_1m") or {})
            mids = {s: (b + a) // 2 for s, (b, a) in (p.get("quotes") or {}).items()}
            if mids:
                watch_mids.append((p["tick"], mids))
            continue
        if t == "cycle_started":
            cur = p["cycle"]
            if cur not in quotes:
                order.append(cur)
                quotes[cur], bars[cur] = {}, {}
        elif cur is None:
            continue
        elif t == "quote":
            quotes[cur][p["symbol"]] = Quote(p["symbol"], p["ts"], p["bid"], p["ask"])
        elif t == "bar" and p.get("interval_s") == interval_s:
            bar = Bar(p["symbol"], p["interval_s"], p["ts"], p["open"], p["high"], p["low"], p["close"], p["volume"])
            bars[cur].setdefault(bar.symbol, []).append(bar)
            if bar.ts + interval_s <= cur:
                last_closes[bar.symbol] = bar.close
        closes_after[cur] = dict(last_closes)
    rounds = [(c, "cycle") for c in order if c in completed]
    rounds += [(r, "wakeup") for r, info in wakeups.items() if info.get("status") == "complete" and rq.get(r)]
    out: list[Round] = []
    carry: dict[str, Quote] = {}
    marks_carry: dict[str, int] = {}
    closes_carry: dict[str, int] = {}
    watch_mids.sort(key=lambda x: x[0])
    last_watch: dict[str, int] = {}
    iv = 0
    for c, kind in sorted(rounds):
        if kind == "cycle":
            carry.update(quotes[c])  # a symbol without a quote this cycle keeps the last known one
            q = dict(carry)
            marks = {s: (x.bid + x.ask) // 2 for s, x in q.items()}
            closes_carry = {**marks, **closes_after.get(c, {})}
            marks_carry.update(marks)
            out.append(Round(CycleData(c, q, marks, dict(closes_carry), bars[c])))
        else:
            q = rq[c]
            # Symbol not quoted at the wake-up: its last accepted quote from the watch, like `_last_valid_quote`.
            while iv < len(watch_mids) and watch_mids[iv][0] <= c:
                last_watch.update(watch_mids[iv][1])
                iv += 1
            marks_carry.update({s: (x.bid + x.ask) // 2 for s, x in q.items()})
            marks_r = {**marks_carry, **{s: m for s, m in last_watch.items() if s not in q}}
            lc = {**closes_carry, **{s: v for s, v in close_1m.get(c, {}).items() if s in q}}
            out.append(Round(CycleData(c, q, marks_r, lc, {}), wakeup=True))
    return out


def _series_from_events(events: list[dict[str, Any]]) -> dict[str, dict[int, int]]:
    out: dict[str, dict[int, int]] = {}
    for e in events:
        if e["type"] == "equity":
            p = e["payload"]
            out.setdefault(p["portfolio"], {})[p.get("cycle", e["ts"])] = p["equity_ueur"]
    return out


def _fill_view(p: Mapping[str, Any], ts: int) -> dict[str, Any]:
    return {
        "ts": ts,
        "order_id": p["order_id"],
        "symbol": p["symbol"],
        "side": p["side"],
        "qty": p["qty"],
        "price_ueur": p["price_ueur"],
        "fee_ueur": p["fee_ueur"],
        "reason": p.get("reason", "intent"),
    }


def _decisions(
    events: list[dict[str, Any]], cycles: list[int], wakeups: Mapping[int, dict[str, Any]] | None = None
) -> dict[str, list[dict[str, Any]]]:
    """One row per (portfolio, round): 4 h cycle or wake-up (`round`, `trigger`). Forced sales
    are filed under the round that precedes them; a stop sale from the watch (`...:watch:{tick}`) has its own row,
    at the tick's time."""
    wakeups = wakeups or {}
    rows: dict[tuple[str, int], dict[str, Any]] = {}
    verdicts: dict[str, dict[str, Any]] = {}
    fills_by_order: dict[str, list[dict[str, Any]]] = {}
    forced: dict[tuple[str, int], list[dict[str, Any]]] = {}

    def row(portfolio: str, cycle: int, ts: int) -> dict[str, Any]:
        key = (portfolio, cycle)
        if key not in rows:
            rows[key] = {
                "portfolio": portfolio, "cycle": cycle, "ts": ts, "kind": "benchmark" if portfolio.startswith("benchmark:") else "pending",
                "skip_reason": None, "model_requested": None, "model_returned": None, "cost_uusd": None,
                "input_tokens": None, "output_tokens": None, "parse_error": None, "justification": None,
                "actions": [], "outputs": [],
                "llm_round": "wakeup" if cycle in wakeups else "scheduled_round",
                "trigger": (wakeups.get(cycle) or {}).get("trigger"),
                "wakeup_status": (wakeups.get(cycle) or {}).get("status"),
            }  # fmt: skip
        return rows[key]

    for e in events:
        t, p, ts = e["type"], e["payload"], e["ts"]
        if t == "risk_verdict":
            verdicts[p["intent_id"]] = p
        elif t == "fill":
            fills_by_order.setdefault(p["order_id"], []).append(_fill_view(p, ts))
    intent_ids: set[str] = set()
    for e in events:
        t, p, ts = e["type"], e["payload"], e["ts"]
        if t == "decision_skipped":
            r = row(p["portfolio"], p["cycle"], ts)
            r["kind"], r["skip_reason"] = "skipped", p["reason"]
        elif t == "decision_received":
            r = row(p["portfolio"], p["cycle"], ts)
            r["ts"] = ts
            r["kind"] = "parse_error" if p.get("parse_error") else "decided"
            for k in ("model_requested", "model_returned", "cost_uusd", "input_tokens", "output_tokens", "parse_error"):
                r[k] = p.get(k)
            parsed = p.get("parsed")
            text = parsed.get("justification") if isinstance(parsed, dict) else None
            if not isinstance(text, str):
                text = p.get("raw_text") if isinstance(p.get("raw_text"), str) else None
            r["justification"] = text[:JUSTIFICATION_MAX] if text else None
            r["has_justification"] = bool(text)
        elif t == "intent":
            r = row(p["portfolio"], p["cycle"], ts)
            if p["intent_id"] in intent_ids:
                continue
            intent_ids.add(p["intent_id"])
            v = verdicts.get(p["intent_id"])
            r["actions"].append({
                "intent_id": p["intent_id"], "symbol": p["symbol"], "side": p["side"], "size_bp": p["size_bp"],
                "stop_bp": p.get("stop_bp"), "expected_move_bp": p.get("expected_move_bp"),
                "horizon_h": p.get("horizon_h"), "confidence_pct": p.get("confidence_pct"),
                "approved": None if v is None else bool(v["approved"]),
                "reasons": [] if v is None else list(v.get("reasons", ())),
                "qty": 0 if v is None else v.get("qty", 0),
                "fills": fills_by_order.get(p["intent_id"], []),
            })  # fmt: skip
    cyc_sorted = sorted(set(cycles) | set(wakeups))
    for e in events:
        if e["type"] != "fill" or e["payload"]["order_id"] in intent_ids:
            continue
        p = e["payload"]
        if ":watch:" in p["order_id"]:
            c = e["ts"]  # stop from the watch: its own row, at the tick's time
        else:
            i = bisect.bisect_right(cyc_sorted, e["ts"]) - 1
            c = cyc_sorted[i] if i >= 0 else e["ts"]
        forced.setdefault((p["portfolio"], c), []).append(_fill_view(p, e["ts"]))
    for (pf, c), fl in forced.items():
        r = row(pf, c, c)
        r["outputs"] = fl
        if r["kind"] in ("pending", "benchmark") and not r["actions"] and any(":watch:" in f["order_id"] for f in fl):
            r["kind"], r["llm_round"] = "stop_watch", "watch"
    out: dict[str, list[dict[str, Any]]] = {}
    for (pf, _c), r in sorted(rows.items(), key=lambda kv: kv[0][1], reverse=True):
        if r["kind"] == "pending":
            r["kind"] = "decided" if r["actions"] else "unknown"
        out.setdefault(pf, []).append(r)
    return out


def _wakeups(events: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Wake-ups: {tick: {wakeup, ts (wall-clock time), trigger, status}}; status complete | abandoned | in_progress."""
    out: dict[int, dict[str, Any]] = {}
    for e in events:
        t, p = e["type"], e["payload"]
        if t == "wakeup_started":
            out[p["wakeup"]] = {"wakeup": p["wakeup"], "ts": e["ts"], "trigger": p.get("trigger"), "status": "in_progress"}
        elif t in ("wakeup_completed", "wakeup_abandoned") and p.get("wakeup") in out:
            out[p["wakeup"]]["status"] = "complete" if t == "wakeup_completed" else "abandoned"
    return out


def _season(events: list[dict[str, Any]], config: Config, now: int) -> dict[str, Any] | None:
    """Latest journaled season (start, reference, waivers, end), or the season planned by the config."""
    starts = [e for e in events if e["type"] == "season_started"]
    if not starts:
        sc = getattr(config, "season", None)
        if sc is None:
            return None
        return {"status": "planned", "number": sc.number, "name": sc.name, "start_ts": sc.start_ts,
                "duration_days": sc.duration_days}  # fmt: skip
    d = starts[-1]["payload"]
    num = d["number"]
    ref = next((e["payload"] for e in events if e["type"] == "season_reference" and e["payload"]["number"] == num), None)
    end = next((e for e in events if e["type"] == "season_ended" and e["payload"]["number"] == num), None)
    waivers = []
    for e in events:
        if e["type"] == "season_waiver" and e["payload"]["number"] == num:
            hashes_before, hashes_after = e["payload"].get("hashes_before") or {}, e["payload"].get("hashes_after") or {}
            waivers.append({"ts": e["ts"], "reason": e["payload"].get("reason", ""),
                          "what": sorted(k for k in set(hashes_before) | set(hashes_after) if hashes_before.get(k) != hashes_after.get(k))})  # fmt: skip
    cycle_start = d["cycle"]
    day = max(1, min(d.get("duration_days") or 1, (min(now, d["planned_cycle_end"]) - cycle_start) // 86_400 + 1))
    return {
        "status": "finished" if end else ("opened" if ref else "without_reference"),
        "number": num, "name": d.get("name") or f"Season {num}", "cycle": cycle_start,
        "planned_cycle_end": d["planned_cycle_end"], "start_ts": d.get("start_ts"), "duration_days": d.get("duration_days"),
        "day": day, "reference": ref, "cycle_end": end["payload"]["cycle"] if end else None,
        "waivers": waivers,
    }  # fmt: skip


def _cache_dir() -> Path | None:
    v = os.environ.get("ARENA_SITE_CACHE")
    if v == "":
        return None
    return Path(v) if v else Path.home() / ".cache" / "arena-site"


def _distribution(
    rounds: list[Round], config: Config, policy: Policy, capital: int, since: int | None = None
) -> list[float]:
    """Return of each random trajectory since round `since` (otherwise since the capital). The computation only changes with a new round: the last result
    is kept in a cache (a single entry, outside the repository, key = sha256 of all the inputs)."""
    n = config.benchmarks.random_paths
    key_src = json.dumps(
        [[r.data.ts, r.wakeup, sorted((s, q.bid, q.ask) for s, q in r.data.quotes.items()),
          sorted(r.data.marks.items()), sorted(r.data.last_closes.items()),
          sorted((s, [(b.ts, b.open, b.high, b.low, b.close) for b in bs]) for s, bs in r.data.bars.items())]
         for r in rounds] + [since, hashlib.sha256((Path(__file__).parent / "luck.py").read_bytes()).hexdigest()] + [n, policy.sha256, config.taker_fee_bp, config.slippage_bp, capital,
                                 sorted(r.symbol for r in config.instrument_refs)],
    )  # fmt: skip
    key = hashlib.sha256(key_src.encode()).hexdigest()
    cache = _cache_dir()
    file = cache / "price_paths.json" if cache else None
    if file is not None:
        try:
            c = json.loads(file.read_text(encoding="utf-8"))
            if c.get("key") == key and isinstance(c.get("rets"), list) and len(c["rets"]) == n:
                return [float(v) for v in c["rets"]]
        except (OSError, ValueError):
            pass
    pairs = price_paths_since(
        rounds, n, policy=policy, instruments=_instruments(config), fee_bp=config.taker_fee_bp,
        slippage_bp=config.slippage_bp, capital_ueur=capital, since=since,
    )  # fmt: skip
    rets = [f / d - 1.0 if d else 0.0 for d, f in pairs]
    if file is not None:
        try:
            file.parent.mkdir(parents=True, exist_ok=True)
            tmp = file.with_suffix(f".tmp-{os.getpid()}")
            tmp.write_text(json.dumps({"key": key, "rets": rets}), encoding="utf-8")
            os.replace(tmp, file)
        except OSError:
            pass
    return rets


def compute(journal_path: Path, config: Config, policy: Policy, now_ts: int | None = None) -> dict[str, Any]:
    now = int(time.time()) if now_ts is None else int(now_ts)
    journal = Journal(journal_path)
    events = list(journal.iter_events(strict=False))
    report = verify(journal_path)
    states = replay(events)
    equity_by_pf = _series_from_events(events)
    capital = {e["payload"]["portfolio"]: e["payload"]["capital_ueur"] for e in events if e["type"] == "portfolio_opened"}
    kinds = {e["payload"]["portfolio"]: e["payload"].get("kind", "llm") for e in events if e["type"] == "portfolio_opened"}
    ids = sorted(capital, key=lambda p: (0 if kinds[p] == "llm" else 1, list(NAMES).index(p) if p in NAMES else 99, p))
    # Retired portfolios (`arena retired`): sold at the bid, value frozen in the event. The free-text note is never read.
    retired: dict[str, dict[str, Any]] = {}
    for e in events:
        if e["type"] == "portfolio_retired" and e["payload"]["portfolio"] not in retired:
            retired[e["payload"]["portfolio"]] = {"ts": e["ts"], "equity_ueur": e["payload"]["equity_ueur"]}
    wakeups = _wakeups(events)
    season = _season(events, config, now)
    watches = [e["payload"] for e in events if e["type"] == "watch"]
    watches.sort(key=lambda v: v["tick"])
    seq_watch = max((i for i, e in enumerate(events) if e["type"] == "watch"), default=-1)
    seq_cycle = max((i for i, e in enumerate(events) if e["type"] == "cycle_completed"), default=-1)

    all_cycles = sorted({c for s in equity_by_pf.values() for c in s})
    # Measured period: the season (from its reference) as soon as it exists, otherwise everything from the first cycle.
    ref = season["reference"] if season and season.get("reference") else None
    cycle_end = season.get("cycle_end") if ref else None
    if ref is not None:
        ref_cycle = ref["cycle"]
        cycles = [c for c in all_cycles if c >= ref_cycle and (cycle_end is None or c <= cycle_end)]
        x0: int | None = ref_cycle - 1  # the reference is taken BEFORE the decisions of the starting cycle
        base = {pf: ref["equity"][pf] for pf in ids if pf in ref.get("equity", {})}
    else:
        ref_cycle = None
        cycles = all_cycles
        x0 = (all_cycles[0] - config.interval_s) if all_cycles else None
        base = dict(capital)

    # Live equity: the latest watch tick more recent than the last cycle (and inside the season if it has ended).
    live = None
    if watches and seq_watch > seq_cycle and (not all_cycles or watches[-1]["tick"] > all_cycles[-1]) and cycle_end is None:
        v = watches[-1]
        live = {"ts": v["tick"], "equity": dict(v.get("equity") or {}), "freeze": bool(v.get("freeze"))}

    # Position marks: last ACCEPTED bid, at the cycle (`quote`) or at the watch (`watch.quotes`).
    # Never `watch.raw_quotes` nor `wakeup_quote`.
    last_marks: dict[str, int] = {}
    last_quote_ts: int | None = None
    for e in events:
        if e["type"] == "quote":
            p = e["payload"]
            last_marks[p["symbol"]] = p["bid"]  # valuation at the bid, like the cycle's equity (cash + positions = equity)
            last_quote_ts = max(last_quote_ts or 0, p["ts"])
        elif e["type"] == "watch":
            p = e["payload"]
            for sym, (b, _a) in (p.get("quotes") or {}).items():
                last_marks[sym] = b
            if p.get("quotes"):
                last_quote_ts = max(last_quote_ts or 0, p["tick"])

    # Distribution of the random trajectories, replayed on the same rounds (cycles AND completed wake-ups, where the
    # live random benchmark also decides) and the same quotes, over the measured period.
    distribution: list[float] = []
    dist_note = None
    # All rounds up to the last measured cycle: the rank compares returns at the same instant (the last
    # cycle, not the live equity), and the burn-in seeds the trajectories' state without counting in the measurement.
    bound = cycles[-1] if cycles else None
    rounds_measured = [r for r in _cycle_data(events, config.interval_s, wakeups) if bound is not None and r.data.ts <= bound]
    random_capital = capital.get(RANDOM) or config.capital_ueur
    if rounds_measured:
        try:
            distribution = _distribution(rounds_measured, config, policy, random_capital, ref_cycle)
        except Exception as exc:  # noqa: BLE001 - the site must not fail because of a statistic
            dist_note = f"rang indisponible : {type(exc).__name__}"
    dist_summary = None
    if distribution:
        srt = sorted(distribution)
        n = len(srt)
        dist_summary = {
            "n": n, "p05": srt[int(0.05 * (n - 1))], "median": srt[(n - 1) // 2], "p95": srt[int(0.95 * (n - 1))],
        }  # fmt: skip

    decisions = _decisions(events, all_cycles, wakeups)
    costs: Counter[str] = Counter()
    decided: Counter[str] = Counter()
    skipped: dict[str, Counter[str]] = {}
    rejects: dict[str, Counter[str]] = {}
    for e in events:
        t, p = e["type"], e["payload"]
        if t == "decision_received":
            costs[p["portfolio"]] += p.get("cost_uusd") or 0
            if not p.get("parse_error"):
                decided[p["portfolio"]] += 1  # an invalid answer is not a decision
        elif t == "decision_skipped":
            skipped.setdefault(p["portfolio"], Counter())[p["reason"]] += 1
    intent_owner = {e["payload"]["intent_id"]: e["payload"]["portfolio"] for e in events if e["type"] == "intent"}
    for e in events:
        if e["type"] == "risk_verdict" and not e["payload"]["approved"]:
            pf = intent_owner.get(e["payload"]["intent_id"])
            if pf:
                rejects.setdefault(pf, Counter()).update(e["payload"].get("reasons", ()))
    trades: dict[str, set[str]] = {}
    for e in events:
        if e["type"] == "fill":
            trades.setdefault(e["payload"]["portfolio"], set()).add(e["payload"]["order_id"])

    cycle_set = set(cycles)

    def track(pf: str) -> list[int]:
        """Equity at the start of the measured period, then equity at each cycle of that period."""
        s = equity_by_pf.get(pf, {})
        pts = [s[c] for c in sorted(s) if c in cycle_set]
        return ([base[pf]] if pf in base else [capital[pf]]) + pts

    # A portfolio without equity at the start of the period (model added during the experiment or the season) is
    # only compared from its own start: no point at 100 before it, no rank against chance over the period.
    opened_ts = {e["payload"]["portfolio"]: e["ts"] for e in events if e["type"] == "portfolio_opened"}

    def inception(pf: str) -> int | None:
        s = [c for c in equity_by_pf.get(pf, {}) if c in cycle_set]
        if ref is not None and pf in base:
            return ref_cycle
        return min(s) if s else opened_ts.get(pf)

    def is_late(pf: str) -> bool:
        if ref is not None:
            return pf not in base
        d = inception(pf)
        return bool(all_cycles) and d is not None and d > all_cycles[0]

    base_pf = {BASELINE: track(BASELINE)} if BASELINE in capital else {}
    portfolios: list[dict[str, Any]] = []
    for pf in ids:
        st = states[pf]
        series = track(pf)
        n = len(series) - 1
        alive = live["equity"].get(pf) if live else None
        archive = retired.get(pf)
        final = archive["equity_ueur"] if archive else alive if alive is not None else series[-1]
        rets = stats.returns(series)
        enough = n >= MIN_CYCLES_STATS
        sh = stats.sharpe(rets) if len(rets) >= 2 else None
        ci = stats.sharpe_ci(rets) if enough else None
        start = series[0]
        tr = final / start - 1.0 if start else 0.0
        dist = None
        if pf != BASELINE and base_pf and len(rets) >= 2:
            b = stats.returns(base_pf[BASELINE])
            m = min(len(b), len(rets))
            if m >= 2:
                d = stats.distinguishable(rets[-m:], b[-m:])
                dist = {"significant": bool(d.significant and enough), "mean_diff": d.mean_diff,
                        "ci_low": d.ci_low, "ci_high": d.ci_high}  # fmt: skip
        positions = []
        for sym, pos in st.positions.items():
            mark = last_marks.get(sym)
            val = None if mark is None else notional_ueur(pos.qty, mark, round_up=False)
            positions.append({
                "symbol": sym, "qty": pos.qty, "cost_ueur": pos.cost_ueur, "opened_ts": pos.opened_ts,
                "stop_ueur": pos.stop_ueur, "mark_ueur": mark, "value_ueur": val,
                "unrealized_ueur": None if val is None else val - pos.cost_ueur,
            })  # fmt: skip
        late = is_late(pf)
        portfolios.append({
            "id": pf, "slug": slug(pf), "name": name(pf), "kind": kinds[pf], "description": DESCRIPTIONS.get(pf),
            "capital_ueur": capital[pf], "base_ueur": start, "equity_ueur": final, "equity_live": alive is not None,
            "base100": final / start * 100 if start else 100.0,
            "n_cycles": n, "total_return": tr, "max_drawdown": stats.max_drawdown(series + ([final] if alive is not None or archive else [])),
            "sharpe": sh if enough else None, "sharpe_ci": list(ci) if ci else None, "too_early": not enough,
            "fees_paid_ueur": st.fees_paid_ueur, "realized_pnl_ueur": st.realized_pnl_ueur,
            "n_trades": len(trades.get(pf, ())), "api_cost_uusd": costs[pf] if kinds[pf] == "llm" else None,
            "rank_percentile": (
                stats.rank_in_distribution(series[-1] / start - 1.0 if start else 0.0, distribution)
                if distribution and not late else None
            ),
            "start_ts": inception(pf), "late": late,
            "distinguishable": dist, "cash_ueur": st.cash_ueur, "halted": st.halted,
            "frozen_until_ts": st.frozen_until_ts if st.frozen_until_ts > now else 0,
            "positions": positions,
            "n_decided": decided[pf] if kinds[pf] == "llm" else None,
            "skipped": dict(skipped.get(pf, {})), "rejects": dict(rejects.get(pf, {})),
            "decisions_total": len(decisions.get(pf, ())),
            "decisions": decisions.get(pf, [])[:DECISIONS_MAX],
            "series_ueur": series, "archive": archive,
        })  # fmt: skip

    # Curve: start of the period, each cycle (the cycle's equity), a watch snapshot every 30 min between the
    # cycles, and the last snapshot (live equity). Real-time axis: the snapshots are not on the 4 h grid.
    pts: dict[int, tuple[str, Mapping[str, int]]] = {}
    t_min = ref_cycle if ref_cycle is not None else (all_cycles[0] if all_cycles else None)
    t_max = cycle_end
    for v in watches:
        tk = v["tick"]
        if t_min is None or tk < t_min or (t_max is not None and tk > t_max):
            continue
        if tk % CURVE_STEP_WATCH_S == 0 or (live is not None and tk == live["ts"]):
            pts[tk] = ("watch", v.get("equity") or {})
    for c in cycles:
        pts[c] = ("cycle", {pf: s[c] for pf, s in equity_by_pf.items() if c in s})
    xs = sorted(pts)
    x = ([x0] if x0 is not None else []) + xs
    x_kinds = (["inception"] if x0 is not None else []) + [pts[t][0] for t in xs]
    chart = []
    for p in portfolios:
        b0 = p["base_ueur"]
        vals: list[float | None] = ([None if p["late"] else 100.0]) if x0 is not None else []
        vals += [round(pts[t][1][p["id"]] / b0 * 100, 4) if p["id"] in pts[t][1] and b0 else None for t in xs]
        chart_series = {"id": p["id"], "name": p["name"], "kind": p["kind"], "values": vals}
        if p["archive"]:  # frozen curve: nothing after the withdrawal, whose last value is that of the sale
            end = p["archive"]["ts"]
            vals[:] = [None if (t > end and i > 0) else v for i, (t, v) in enumerate(zip(x, vals, strict=True))]
            last = max((i for i, v in enumerate(vals) if v is not None), default=None)
            if last is not None and b0:
                vals[last] = round(p["equity_ueur"] / b0 * 100, 4)
            chart_series["archive_ts"] = end
        chart.append(chart_series)

    burn_in = None
    if ref is not None:
        before = [c for c in all_cycles if c < ref_cycle]
        burn_in = {
            "start_ts": before[0] if before else None, "end_ts": ref_cycle, "n_cycles": len(before),
            "portfolios": [
                {"id": pf, "name": name(pf), "kind": kinds[pf],
                 "total_return": ref["equity"][pf] / capital[pf] - 1.0 if capital.get(pf) else None}
                for pf in ids if pf in ref.get("equity", {})
            ],
        }  # fmt: skip

    wakeups_list = [
        {k: r[k] for k in ("wakeup", "ts", "trigger", "status")}
        for r in sorted(wakeups.values(), key=lambda r: r["wakeup"], reverse=True)
    ][:WAKEUPS_MAX]

    cfg_events = [e for e in events if e["type"] == "config_loaded"]
    cfg_last = cfg_events[-1]["payload"] if cfg_events else {}
    llm_dist = [p for p in portfolios if p["kind"] == "llm" and p["distinguishable"]]
    any_distinguishable = any(p["distinguishable"]["significant"] for p in llm_dist)
    vc = getattr(config, "watch", None)
    return {
        "venue_mode": config.venue_mode,
        "generated_ts": now,
        "n_cycles": len(cycles),
        "first_cycle_ts": cycles[0] if cycles else None,
        "last_cycle_ts": all_cycles[-1] if all_cycles else None,
        "interval_s": config.interval_s,
        "decider_backend": getattr(config, "decider_backend", None),
        "last_quote_ts": last_quote_ts,
        "min_cycles_stats": MIN_CYCLES_STATS,
        "any_llm_distinguishable": any_distinguishable,
        "distribution": dist_summary,
        "distribution_note": dist_note,
        "portfolios": portfolios,
        "chart": {"x": x, "kinds": x_kinds, "series": chart, "n_cycles": len(cycles)},
        "live": {"ts": live["ts"], "freeze": live["freeze"]} if live else None,
        "wakeups": wakeups_list,
        "n_wakeups": len(wakeups),
        "season": season,
        "burn_in": burn_in,
        # Finished cycles and their link in the hash-chained journal (hash of the cycle_completed event).
        "cycles": [
            {"ts": e["payload"]["cycle"], "hash": e.get("hash"), "seq": e.get("seq")}
            for e in sorted((e for e in events if e["type"] == "cycle_completed"), key=lambda e: e["payload"]["cycle"])
        ],
        "journal": {
            "verify_ok": report.ok, "n_records": report.n_records, "head_seq": report.head_seq,
            "head_hash": report.head_hash, "errors": [
                {"code": er.code, "line": er.line, "message": er.message} for er in report.errors[:10]
            ],
        },
        "provenance": {
            "policy_sha256": policy.sha256, "config_sha256": config.sha256,
            "journal_policy_sha256": cfg_last.get("policy_sha256"),
            "journal_config_sha256": cfg_last.get("config_sha256"),
            "prompt_sha256": cfg_last.get("prompt_sha256"),
            "prompt_hashes": sorted({e["payload"].get("prompt_sha256") for e in cfg_events if e["payload"].get("prompt_sha256")}),
            "git_head": cfg_last.get("git_head"),
        },
        "method": {
            "fill_model_version": config.fill_model_version, "taker_fee_bp": config.taker_fee_bp,
            "slippage_bp": config.slippage_bp, "capital_ueur": config.capital_ueur,
            "interval_s": config.interval_s, "n_paths": config.benchmarks.random_paths,
            "e0065": {"L": config.benchmarks.e0065.L, "k": config.benchmarks.e0065.k, "H": config.benchmarks.e0065.H},
            "watch": None if vc is None else {
                "tick_s": vc.tick_s, "move_threshold_bp": vc.move_threshold_bp,
                "move_window_s": vc.move_window_s, "max_wakeups_per_day": vc.max_wakeups_per_day,
                "cooldown_s": vc.cooldown_s,
            },
            "models": [{"portfolio": m.portfolio, "model": m.model, "daily_budget_uusd": m.daily_budget_uusd,
                        "price_in_uusd_per_mtok": m.price_in_uusd_per_mtok,
                        "price_out_uusd_per_mtok": m.price_out_uusd_per_mtok} for m in config.models],
            "policy": {f.name: (list(getattr(policy, f.name)) if f.name == "symbols" else getattr(policy, f.name))
                       for f in fields(Policy) if f.name != "sha256"},
        },
    }
