"""Offline replay of the perp league rules on collected public data (step 3 acceptance, study §4.4).

A random trader (the action space of the future `benchmark-perp:random`, study §6) decides every 4 hours;
every intent goes through `evaluate_perp`, every approved one through the simulator, and every closed
minute of the period is processed (stops, take-profits, margin close-out), with hourly funding from
Kraken's history. The question it answers: with the policy's rules, does a margin close-out (or a halt)
ever happen on real data? Each one is listed for review.

Known simplifications (documented, all on the market-data side): the quote at a decision is the mark
close +/- one tick (historical order books are not public), so SPREAD_ANOMALY and the mid-versus-mark part
of MARK_SANITY cannot fire; the index is the spot candle close (missing -> the entry is refused); EUR/USD
is constant (the collector only stores it from 12/11/2026); ORDER_RATE and KILL_SWITCH are not exercised.
The summary lists every rule never triggered: unexercised is not the same as safe.

What it measures: margin close-outs and halts (drawdown checked every minute, at the minute's worst marks),
the closest approach to the close-out threshold (equity / gross exposure, it fires under 25 %), and for
every stopped trade the realized loss versus riskd's prediction. `--amplify K` is a stress variant that
multiplies every log-return by K.

    python -m arene.perp.replay --trajectories 20 [--days 90] [--specs FILE]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from arene.journal import Journal
from arene.perp import riskd as R
from arene.perp.collect import data_root
from arene.perp.config import DEFAULT_CONFIG, default_var, load_perp_config
from arene.perp.kraken_futures import KrakenFuturesClient
from arene.perp.ledger import (
    BP,
    HOUR_S,
    MINUTE_S,
    PerpBook,
    PerpLedgerError,
    equity_ueur,
    gross_exposure_ueur,
    price_pnl_uusd,
    to_eur,
)
from arene.perp.policy import DEFAULT_POLICY, PerpPolicy, load_perp_policy
from arene.perp.riskd import InstrumentMarket, PerpCounters, PerpIntent, PerpMarketView, evaluate_perp
from arene.perp.sim import MinuteCandles, PerpSimulator, SimParams
from arene.perp.store import PerpDataStore
from arene.perp.types import InstrumentSpec

DECISION_S = 4 * HOUR_S
DEFAULT_FX = (1_100_000, 1_100_100)
# Every rule code: the summary lists those the replay never triggered (unexercised is not the same as safe).
ALL_ENTRY_CODES = sorted(v for k, v in vars(R).items() if k.isupper() and isinstance(v, str) and v == k)


@dataclass
class Series:
    mark: dict[int, tuple[int, int, int, int]]
    trade: dict[int, tuple[int, int, int, int]]
    spot_close: dict[int, int]
    funding: dict[int, tuple[int, int]]  # stamp -> (absolute nusd, relative e12)


@dataclass
class TrajectoryReport:
    seed: int
    final_equity_ueur: int = 0
    min_equity_ueur: int = 0
    max_drawdown_bp: int = 0  # measured every minute, at the minute's worst marks
    min_equity_to_gross_bp: int | None = (
        None  # closest approach to the margin close-out (it fires under 2500)
    )
    intents: int = 0
    approved: int = 0
    rejections: dict[str, int] = field(default_factory=dict)
    fills_by_reason: dict[str, int] = field(default_factory=dict)
    margin_closeouts: list[int] = field(default_factory=list)
    halted_at: int | None = None
    absorbed_deficit_ueur: int = 0
    fees_ueur: int = 0
    funding_ueur: int = 0
    missing_funding_hours: int = 0
    problems: int = 0
    stop_loss_over_predicted: int = 0  # stopped trades whose realized loss exceeded riskd's prediction
    worst_stop_loss_ratio_pct: int = 0  # realized / predicted loss of the worst stopped trade, in %


def load_series(
    store: PerpDataStore, symbols: list[str], start: int, end: int, amplify: int = 1
) -> dict[str, Series]:
    """Candles and funding of the period. `amplify` > 1 is a STRESS variant: every price p becomes
    p0 x (p / p0) ** amplify (p0 = first mark open), which multiplies log-returns; the synthetic prices are
    computed with floats and rounded to integers (they are inputs, never money)."""
    out = {}
    for s in symbols:
        marks = store.closed_candles("mark", s, 60, start, end)
        p0 = marks[0].open if marks else 1

        def tr(p: int, p0: int = p0) -> int:
            return p if amplify == 1 else max(1, round(p0 * (p / p0) ** amplify))

        mark = {c.ts: (tr(c.open), tr(c.high), tr(c.low), tr(c.close)) for c in marks}
        trade = {
            c.ts: (tr(c.open), tr(c.high), tr(c.low), tr(c.close))
            for c in store.closed_candles("trade", s, 60, start, end)
        }
        spot = {
            c.ts: tr(c.close)
            for c in store.closed_candles("spot", s, 60, start, end)
            if c.ts % DECISION_S == DECISION_S - 60
        }
        funding = {
            r.ts: (r.funding_nusd, r.relative_funding_e12) for r in store.funding(s).load(start, end + HOUR_S)
        }
        out[s] = Series(mark, trade, spot, funding)
    return out


def random_intents(
    rng: random.Random,
    n: int,
    ts: int,
    held: Mapping[str, Any],
    symbols: list[str],
    min_move_bp: int = 100,
) -> list[PerpIntent]:
    """0-2 actions in the agents' action space (study §6); the side is drawn among those the held position
    allows; the declared move goes down to 1 % so that the cost rule is exercised."""
    out = []
    for k in range(rng.choice((0, 1, 2))):
        inst = rng.choice(symbols)
        pos = held.get(inst)
        if pos is None:
            options = ["open_long", "open_short"]
        else:
            options = ["open_long" if pos.qty > 0 else "open_short", "reduce", "close"]
        action = rng.choice(options)
        iid = f"r{n}:{ts}:{k}"
        if action in ("reduce", "close"):
            out.append(PerpIntent(iid, "R", ts, inst, action, size_bp=rng.randint(1000, 10_000)))
            continue
        stop = rng.randint(200, 1000)
        tp = None if rng.random() < 0.5 else stop * rng.randint(1, 3)
        out.append(
            PerpIntent(
                iid,
                "R",
                ts,
                inst,
                action,
                size_bp=rng.randint(500, 5000),
                stop_bp=stop,
                take_profit_bp=tp,
                horizon_h=rng.randint(24, 168),
                expected_move_bp=rng.randint(min_move_bp, 1500),
                confidence_pct=rng.randint(0, 100),
            )
        )
    return out


def run_trajectory(
    seed: int,
    series: dict[str, Series],
    specs: Mapping[str, InstrumentSpec],
    policy: PerpPolicy,
    params: SimParams,
    start: int,
    end: int,
    workdir: Path,
    fx: tuple[int, int] = DEFAULT_FX,
) -> TrajectoryReport:
    rng = random.Random(seed)
    symbols = sorted(series)
    ticks = {s: specs[s].tick_uusd for s in symbols}
    sim = PerpSimulator(Journal(workdir / f"t{seed}.jsonl"), ticks, params, exclusive=True)
    sim.open_portfolio("R", "benchmark", start)
    rep = TrajectoryReport(seed, min_equity_ueur=params.capital_ueur)
    book = sim._book  # read-only view of the live state (exclusive mode, single writer)
    last_mark: dict[str, int] = {}
    last_rel: dict[str, tuple[int, int]] = {}  # instrument -> (stamp, relative rate)
    opens: list[tuple[int, str]] = []
    month_start: dict[str, tuple[int, int]] = {}
    # (instrument, open_seq) -> (riskd's loss at stop, mark it was measured from) at the last entry
    predicted: dict[tuple[str, int], tuple[int, int]] = {}
    peak = params.capital_ueur
    hourly_equity: list[tuple[int, int]] = []
    n = 0
    for minute in range(start, end, MINUTE_S):
        # the minute just closed: [minute - 60, minute). Nothing later is ever read (no look-ahead).
        closed = minute - MINUTE_S
        for s in symbols:
            if closed in series[s].mark:
                last_mark[s] = series[s].mark[closed][3]
        acc = book.states["R"]
        if acc.positions and closed >= start:
            candles = {
                s: MinuteCandles(series[s].mark[closed], series[s].trade.get(closed))
                for s in acc.positions
                if closed in series[s].mark
            }
            _, problems = sim.process_minute(closed, candles, fx, fallback_marks=last_mark)
            rep.problems += len(problems)
        acc = book.states["R"]
        if acc.margin_closeouts > len(rep.margin_closeouts):
            rep.margin_closeouts.append(closed)
        # funding: the stamp H pays [H - 1 h, H); settled at the first minute of the new hour
        if minute % HOUR_S == 0:
            for s in symbols:
                f = series[s].funding.get(minute)
                if f is not None:
                    last_rel[s] = (minute, f[1])
                if acc.qty_history.get(s):
                    try:
                        if f is None:
                            rep.missing_funding_hours += len(sim.record_missing_funding(s, minute))
                        else:
                            sim.settle_funding(s, minute, f[0], fx)
                    except PerpLedgerError:
                        rep.problems += 1
        acc = book.states["R"]
        if len(last_mark) < len(symbols):
            continue
        # every minute: equity at the minute's worst marks, closeness to the close-out, drawdown and halt
        if acc.positions:
            worst = {}
            for s, p in acc.positions.items():
                c = series[s].mark.get(closed)
                worst[s] = (c[2] if p.qty > 0 else c[1]) if c else last_mark[s]
            eq_w = equity_ueur(acc, worst, *fx)
            gross_w = gross_exposure_ueur(acc, worst, *fx)
            if gross_w > 0:
                ratio = eq_w * BP // gross_w
                if rep.min_equity_to_gross_bp is None or ratio < rep.min_equity_to_gross_bp:
                    rep.min_equity_to_gross_bp = ratio
        else:
            eq_w = acc.collateral_ueur
        eq = equity_ueur(acc, {s: last_mark[s] for s in acc.positions}, *fx)
        peak = max(peak, eq)
        rep.min_equity_ueur = min(rep.min_equity_ueur, eq_w)
        rep.max_drawdown_bp = max(rep.max_drawdown_bp, (peak - eq_w) * BP // peak)
        if minute % HOUR_S == 0:
            hourly_equity.append((minute, eq))
        quotes = {s: (last_mark[s] - ticks[s], last_mark[s] + ticks[s]) for s in symbols}
        if rep.halted_at is None and (peak - eq) * BP >= policy.drawdown_halt_bp * peak:
            sim.flatten("R", minute, quotes, fx, "halt")  # the watcher's halt: checked every minute
            rep.halted_at = minute
        if minute % DECISION_S or rep.halted_at is not None:
            continue
        # rendez-vous: max holding, counters, decisions
        sim.close_expired(minute, quotes, fx)
        mkey = time.strftime("%Y-%m", time.gmtime(minute))
        month_start.setdefault(mkey, (book.states["R"].fees_paid_ueur, eq))
        ago = [e for t, e in hourly_equity if t <= minute - 86400]
        markets = {
            s: InstrumentMarket(
                bid_uusd=quotes[s][0],
                ask_uusd=quotes[s][1],
                quote_ts=minute - 1,
                mark_uusd=last_mark[s],
                mark_ts=minute - 1,
                index_uusd=series[s].spot_close.get(minute - 60),  # missing spot candle -> None -> refused
                index_ts=minute - 1,
                relative_funding_e12=last_rel[s][1] if s in last_rel else None,
                funding_ts=last_rel[s][0] if s in last_rel else None,
                median_spread_uusd=2 * ticks[s],
            )
            for s in symbols
        }
        view = PerpMarketView(markets, fx[0], fx[1], minute)
        orders_this_round = 0
        for it in random_intents(rng, n, minute, book.states["R"].positions, symbols):
            n += 1
            rep.intents += 1
            acc = book.states["R"]
            counters = PerpCounters(
                equity_month_start_ueur=month_start[mkey][1],
                equity_24h_ago_ueur=ago[-1] if ago else params.capital_ueur,
                equity_peak_ueur=peak,
                opens_24h=sum(1 for t, _ in opens if t > minute - 86400),
                orders_last_minute=orders_this_round,
                last_open_ts={
                    s: max(t for t, i in opens if i == s) for s in symbols if any(i == s for _, i in opens)
                },
                fees_month_ueur=acc.fees_paid_ueur - month_start[mkey][0],
            )
            v = evaluate_perp(it, acc, view, specs, counters, policy, params, minute, False)
            if not v.approved:
                for code in v.reasons:
                    rep.rejections[code] = rep.rejections.get(code, 0) + 1
                continue
            try:
                sim.market_order(
                    it.intent_id,
                    "R",
                    it.instrument,
                    v.qty,
                    quotes[it.instrument],
                    fx,
                    minute,
                    marks=last_mark,
                )
                orders_this_round += 1
                if it.action.startswith("open"):
                    sim.set_conditional("R", it.instrument, "stop", v.stop_uusd, minute)
                    if v.take_profit_uusd is not None:
                        sim.set_conditional("R", it.instrument, "take_profit", v.take_profit_uusd, minute)
                    opens.append((minute, it.instrument))
                    pos = book.states["R"].positions[it.instrument]
                    predicted[(it.instrument, pos.open_seq)] = (
                        v.metrics["trade_loss_ueur"],
                        last_mark[it.instrument],
                    )
                rep.approved += 1
            except PerpLedgerError:
                rep.problems += 1
    acc = book.states["R"]
    # stopped trades: the loss from the mark riskd measured from at the last entry (price + exit fee), versus
    # its prediction; measuring from the average entry would also count a loss already open when adding
    shadow = PerpBook()
    for rec in sim.journal.iter_events():
        if rec["type"] == "perp_fill":
            p = rec["payload"]
            rep.fills_by_reason[p["reason"]] = rep.fills_by_reason.get(p["reason"], 0) + 1
            if p["reason"] == "stop":
                pos = shadow.states["R"].positions[p["instrument"]]
                pred, mark0 = predicted.get((p["instrument"], pos.open_seq), (0, 0))
                realized = p["fee_ueur"] - to_eur(
                    price_pnl_uusd(-p["qty"], mark0, p["price_uusd"]), p["fx_bid"], p["fx_ask"]
                )
                if pred and realized > 0:
                    rep.worst_stop_loss_ratio_pct = max(rep.worst_stop_loss_ratio_pct, realized * 100 // pred)
                    if realized > pred:
                        rep.stop_loss_over_predicted += 1
        shadow.apply(rec)
    rep.final_equity_ueur = equity_ueur(acc, {s: last_mark[s] for s in acc.positions}, *fx)
    rep.absorbed_deficit_ueur = acc.absorbed_deficit_ueur
    rep.fees_ueur = acc.fees_paid_ueur
    rep.funding_ueur = acc.funding_paid_ueur
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m arene.perp.replay")
    ap.add_argument("--trajectories", type=int, default=20)
    ap.add_argument("--first-seed", type=int, default=1)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--var", type=Path, default=None)
    ap.add_argument(
        "--specs", type=Path, default=None, help="instruments JSON (Kraken format); default: live public API"
    )
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--amplify", type=int, default=1, help="stress: multiply every log-return by this factor")
    args = ap.parse_args(argv)
    cfg = load_perp_config(DEFAULT_CONFIG)
    policy = load_perp_policy(DEFAULT_POLICY)
    symbols = [i.kraken_symbol for i in cfg.instruments]
    if args.specs:
        import httpx

        from arene.data import RateLimitedHttp

        body = args.specs.read_bytes()
        http = RateLimitedHttp(
            httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body)))
        )
        specs = KrakenFuturesClient(http).instruments(symbols)
    else:
        specs = KrakenFuturesClient().instruments(symbols)
    store = PerpDataStore(data_root(args.var or default_var()))
    end = (int(time.time()) // DECISION_S) * DECISION_S - DECISION_S
    start = end - args.days * 86400
    series = load_series(store, symbols, start, end, args.amplify)
    reports: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as d:
        for seed in range(args.first_seed, args.first_seed + args.trajectories):
            t0 = time.monotonic()
            rep = run_trajectory(seed, series, specs, policy, cfg.simulation, start, end, Path(d))
            row = dict(rep.__dict__, seconds=int(time.monotonic() - t0))
            reports.append(row)
            print(json.dumps(row, sort_keys=True), flush=True)
    summary = {
        "start": start,
        "end": end,
        "trajectories": len(reports),
        "policy_sha256": policy.sha256,
        "margin_closeouts": sum(len(r["margin_closeouts"]) for r in reports),
        "halts": sum(1 for r in reports if r["halted_at"] is not None),
        "absorbed_deficit_ueur": sum(r["absorbed_deficit_ueur"] for r in reports),
        "max_drawdown_bp": max((r["max_drawdown_bp"] for r in reports), default=0),
        "approved": sum(r["approved"] for r in reports),
        "intents": sum(r["intents"] for r in reports),
        "problems": sum(r["problems"] for r in reports),
        "amplify": args.amplify,
        "min_equity_to_gross_bp": min(
            (r["min_equity_to_gross_bp"] for r in reports if r["min_equity_to_gross_bp"] is not None),
            default=None,
        ),
        "stop_loss_over_predicted": sum(r["stop_loss_over_predicted"] for r in reports),
        "worst_stop_loss_ratio_pct": max((r["worst_stop_loss_ratio_pct"] for r in reports), default=0),
        "rejections": dict(
            sorted(
                (code, sum(r["rejections"].get(code, 0) for r in reports))
                for code in {c for r in reports for c in r["rejections"]}
            )
        ),
        "rules_never_exercised": sorted(set(ALL_ENTRY_CODES) - {c for r in reports for c in r["rejections"]}),
    }
    print(json.dumps({"summary": summary}, sort_keys=True))
    if args.out:
        args.out.write_text(
            json.dumps({"summary": summary, "trajectories": reports}, indent=1, sort_keys=True)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
