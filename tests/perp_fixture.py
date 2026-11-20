"""Synthetic journal of the derivatives league, consistent for the engine's ledger (fills, funding and equity recomputed).

Two days, a tick every 5 min, 4 AIs and 3 benchmarks. Covers: long and short openings with stop and target,
risk guard refusal, stop hit by the watcher, wake-up, skipped round (budget), answer without a decision, funding paid
and received, freeze. It also slips in private fields (paths, stderr, CLI version, tools offered, alert message)
to check that they never reach the site.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from arena.journal import Journal
from arena.perp.ledger import (
    PerpBook,
    equity_ueur,
    funding_amount_ueur,
    gross_exposure_ueur,
    qty_seconds,
    unrealized_ueur,
)

T0 = 1_794_528_000  # 13/11/2026, a multiple of 3600; the scheduled rounds fall at k*14400 + 7200
FX = (1_105_100, 1_105_160)
BASE = {"BTC-PERP": 88_650_000_000, "ETH-PERP": 3_200_000_000, "SOL-PERP": 140_000_000, "XRP-PERP": 550_000,
        "LINK-PERP": 14_000_000, "LTC-PERP": 85_000_000}  # fmt: skip
PF_KRAKEN = {"BTC-PERP": "PF_XBTUSD", "ETH-PERP": "PF_ETHUSD", "SOL-PERP": "PF_SOLUSD", "XRP-PERP": "PF_XRPUSD",
             "LINK-PERP": "PF_LINKUSD", "LTC-PERP": "PF_LTCUSD"}  # fmt: skip
LLMS = ["llm-perp:claude-haiku-5-5", "llm-perp:claude-sonnet-5-5", "llm-perp:claude-opus-5-5", "llm-perp:claude-fable-5-2"]
BENCHMARKS = ["benchmark-perp:basket-1x", "benchmark-perp:trend", "benchmark-perp:random"]
ROBOT = "robot-perp:hunter"  # the Wick Hunter and its 5-minute witness (kind "robot")
ROBOT_5MIN = "benchmark-perp:hunter-5min"
COUNCIL = "council-perp:haiku"
OPUS = "council-perp:opus"
UNKNOWN = "council-perp:zeta"  # a council the site does not know
ARG_ARBITRAGE = "ETH weak against SOL: long SOL, short ETH, the strength gap exceeds 8% over 30 days."
OPUS_REASON = "The advisers lean long SOL; the Advocate has nothing new. I buy SOL at 200%, stop 4%."
ARG_MAPPER = "Clear bearish regime on ETH: 4 h below SMA20, MACD negative. Short with a tight stop."
ARG_ADVOCATE = "The ETH short is reaching the lower band: the drop is already done, the rebound is lurking."
CHAIR_REASON = "Short ETH at 300%, stop 3%. I follow the Mapper and the Follower; I discard the Advocate."
FABLE_REASON = "ETH loses 3% over 24 h, funding positive: longs pay. RSI 4 h under 45. I sell 25% short."
INVALIDATION = "4 h close above $3,300"
SECRET = "/tmp/arena/var-perp/rounds/x"
ALERT_NOTE = "breakout of yesterday's high"
INVALID_ORDER = "SOL 4 h close below $120"
ALERT_BTC = "a1" * 32
SOL_ORDER = "e1" * 32
ALERT_LTC = "a2" * 32
ALERT_ETH = "a3" * 32


def price(inst: str, ts: int) -> int:
    k = list(BASE).index(inst)
    t = (ts - T0) / 86_400
    drift = {0: 0.02, 1: -0.05, 2: 0.03, 3: -0.01, 4: 0.015, 5: -0.02}[k] * t
    return int(BASE[inst] * (1 + drift + 0.012 * math.sin(t * 9 + k)))


def qty_for(eur: int, inst: str, ts: int) -> int:
    usd = eur * FX[0] // 1_000_000  # µEUR -> µUSD
    return usd * 100_000_000 // price(inst, ts)


class Gen:
    def __init__(self, path: Path) -> None:
        self.j = Journal(path)
        self.book = PerpBook()
        self.n = 0

    def add(self, t: str, p: dict, ts: int) -> None:
        rec = self.j.append(t, p, ts)
        self.book.apply(rec)

    def fill(self, pf: str, inst: str, qty: int, ts: int, reason: str = "intent", oid: str | None = None) -> str:
        self.n += 1
        oid = oid or f"t:{pf}:{inst}:{self.n}"
        px = price(inst, ts)
        fee = abs(qty) * px // 100_000_000 * 7 // 10_000 * 1_000_000 // FX[0] + 1
        self.add("perp_fill", {"order_id": oid, "portfolio": pf, "instrument": inst, "qty": qty, "price_uusd": px,
                               "fee_ueur": fee, "fx_bid": FX[0], "fx_ask": FX[1], "reason": reason,
                               "fill_model_version": "pessimistic-perp-v1", "ts": ts}, ts)  # fmt: skip
        return oid

    def cond(self, pf: str, inst: str, kind: str, px: int | None, ts: int) -> None:
        self.add("conditional_order", {"portfolio": pf, "instrument": inst, "kind": kind, "price_uusd": px, "ts": ts}, ts)


def build(path: Path, *, ruin: bool = False, councils: bool = True, archive: bool = False,
          archive_fable: bool = False, robots: bool = False) -> Path:
    """`ruin`: the Haiku council ends halted (`portfolio_halted`, ruin at -90%); `councils=False`: no council;
    `archive`: both councils are retired an hour before the end (positions closed, `portfolio_retired`);
    `archive_fable`: the same for the solo AI Fable; `robots`: the Wick Hunter and its witness (two shocks seen, one
    trade for the hunter, one shock without a trade for the witness)."""
    g = Gen(path)
    for pf in BENCHMARKS + LLMS:
        g.add("portfolio_opened", {"portfolio": pf, "kind": "llm" if pf in LLMS else "benchmark", "league": "perp",
                                   "capital_ueur": 1_000_000_000, "venue_mode": "paper"}, T0)  # fmt: skip
    if robots:
        for pf in (ROBOT, ROBOT_5MIN):
            g.add("portfolio_opened", {"portfolio": pf, "kind": "robot", "league": "perp", "capital_ueur": 1_000_000_000,
                                       "venue_mode": "paper"}, T0)  # fmt: skip
    scheduled_rounds = [T0 + 7_200 + 14_400 * k for k in range(12)]
    wake = scheduled_rounds[2] + 5_400
    end = T0 + 2 * 86_400
    rnd = 0
    for ts in range(T0 + 300, end + 1, 300):
        # Funding of the closed hour, for each position held during the hour.
        if ts % 3_600 == 0:
            for pf, acc in g.book.states.items():
                for inst, hist in acc.qty_history.items():
                    qs = qty_seconds(hist, ts - 3_600, ts)
                    if qs:
                        rate = price(inst, ts) // 100 * (1 if inst != "XRP-PERP" else -1)  # ±0.001% per hour
                        if inst == "LTC-PERP" and ts == T0 + 4 * 3_600:
                            g.add("funding_missing", {"portfolio": pf, "instrument": inst, "stamp": ts, "qty_seconds": qs}, ts)
                            continue
                        amt = funding_amount_ueur(qs, rate, *FX)
                        g.add("funding", {"portfolio": pf, "instrument": inst, "stamp": ts, "qty_seconds": qs, "rate_nusd": rate,
                                          "fx_bid": FX[0], "fx_ask": FX[1], "amount_ueur": amt}, ts)  # fmt: skip
        if robots and ts == T0 + 3 * 3_600:  # a wick: the hunter enters, the witness does not see it in time
            iid = "c1" * 32
            g.add("hunter_signal", {"portfolio": ROBOT, "instrument": "PF_XBTUSD", "side": "buy", "window_min": 15, "move_bp": -520,
                                    "price_uusd": price("BTC-PERP", ts), "ts": ts, "first_seen_ts": ts, "intent_id": iid, "rule": "shocks_fade-wickS"}, ts)  # fmt: skip
            g.add("hunter_signal", {"portfolio": ROBOT, "instrument": "PF_XBTUSD", "side": "buy", "window_min": 15, "move_bp": -520,
                                    "price_uusd": price("BTC-PERP", ts), "ts": ts + 5, "first_seen_ts": ts, "intent_id": "c4" * 32, "rule": "shocks_fade-wickS"}, ts)  # fmt: skip  # a new attempt: the same shock
            g.fill(ROBOT, "BTC-PERP", qty_for(2_000_000_000, "BTC-PERP", ts), ts, "intent", iid)
            g.add("hunter_signal", {"portfolio": ROBOT_5MIN, "instrument": "PF_XBTUSD", "side": "buy", "window_min": 30, "move_bp": -480,
                                    "price_uusd": price("BTC-PERP", ts), "ts": ts, "intent_id": "c2" * 32, "rule": "shocks_fade-wickS"}, ts)  # fmt: skip
        if robots and ts == T0 + 4 * 3_600:  # the exit at 60 minutes
            qty = g.book.states[ROBOT].positions["BTC-PERP"].qty
            g.add("hunter_exit", {"portfolio": ROBOT, "instrument": "PF_XBTUSD", "opened_ts": T0 + 3 * 3_600, "due_ts": ts, "intent_id": "c3" * 32}, ts)
            g.fill(ROBOT, "BTC-PERP", -qty, ts, "intent", "c3" * 32)
        if councils and ts == scheduled_rounds[10] - 600:  # the Haiku council joins midway
            g.add("portfolio_opened", {"portfolio": COUNCIL, "kind": "council", "league": "perp", "capital_ueur": 1_000_000_000,
                                       "venue_mode": "paper"}, ts)  # fmt: skip
        if councils and ts == scheduled_rounds[11] - 600:  # the Opus council opens one round later
            g.add("portfolio_opened", {"portfolio": OPUS, "kind": "council", "league": "perp", "capital_ueur": 1_000_000_000,
                                       "venue_mode": "paper"}, ts)  # fmt: skip
        if councils and ts == scheduled_rounds[10]:  # old format: 8 opinions in A, Haiku President without a model field
            _council_round(g, ts, opens=True)
        if councils and ts == scheduled_rounds[11]:  # new format: 9 opinions in A (the Arbitrageur), prompts v2
            _council_round(g, ts, opens=False, arbitrageur=True)
            _council_round(g, ts, opens=True, arbitrageur=True, opus=True)
        if councils and archive and ts == end - 3_600:
            for pf in (COUNCIL, OPUS):
                for inst, pos in list(g.book.states[pf].positions.items()):
                    g.fill(pf, inst, -pos.qty, ts, "retired")
                g.add("portfolio_retired", {"portfolio": pf, "ts": ts, "reason": "overhaul", "note": "everything allowed"}, ts)
        if archive_fable and ts == end - 3_600:
            pf = "llm-perp:claude-fable-5-2"
            for inst, pos in list(g.book.states[pf].positions.items()):
                g.fill(pf, inst, -pos.qty, ts, "retired")
            g.add("portfolio_retired", {"portfolio": pf, "ts": ts, "reason": "archive", "note": "private free text"}, ts)
        if councils and ruin and ts == end:
            g.add("portfolio_halted", {"portfolio": COUNCIL, "reason": "drawdown", "until_ts": 0}, ts)
        if ts in scheduled_rounds or ts == wake:
            rnd += 1
            _llm_round(g, ts, rnd, wake=ts == wake)
        if ts == scheduled_rounds[1] + 1_800:  # Fable's entry order is crossed between two rounds
            _order_triggered(g, ts)
        if ts == scheduled_rounds[1] + 3_600:  # its BTC alert too: private round "alert"
            _alert_and_private_round(g, ts)
        if ts == scheduled_rounds[1] + 3_000:  # the watcher hits Sonnet's stop
            acc = g.book.states["llm-perp:claude-sonnet-5-5"]
            if "BTC-PERP" in acc.positions:
                g.fill("llm-perp:claude-sonnet-5-5", "BTC-PERP", -acc.positions["BTC-PERP"].qty, ts + 59, "stop",
                       f"stop:llm-perp:claude-sonnet-5-5:BTC-PERP:1:{ts}")  # fmt: skip
        if scheduled_rounds[11] < ts <= scheduled_rounds[11] + 2_400 and ts % 600 == 0:  # regular calls of Sonnet, with no order
            _sonnet_call(g, ts, end)
        if ts == scheduled_rounds[3] + 600:
            g.add("portfolio_frozen", {"portfolio": "llm-perp:claude-opus-5-5", "reason": "daily_loss", "until_ts": ts + 86_400 * 30}, ts)
            g.add("alert", {"level": "action", "code": "perp_llm_round_failed", "message": f"OSError: {SECRET} the host"}, ts)
        for pf, acc in g.book.states.items():
            if acc.retired:
                continue
            marks = {i: price(i, ts) for i in acc.positions}
            g.add("perp_equity", {"portfolio": pf, "ts": ts, "collateral_ueur": acc.collateral_ueur,
                                  "unrealized_ueur": unrealized_ueur(acc, marks, *FX), "equity_ueur": equity_ueur(acc, marks, *FX),
                                  "gross_ueur": gross_exposure_ueur(acc, marks, *FX), "marks": marks,
                                  "fx_bid": FX[0], "fx_ask": FX[1]}, ts)  # fmt: skip
        g.add("perp_tick", {"tick": ts, "last_minute": ts - 60, "minutes": 5, "fills": 0, "rounds": [], "pending_funding": [],
                            "notes": [f"note {SECRET}"], "problems": []}, ts)  # fmt: skip
    return path


def _decision(g: Gen, pf: str, rnd: int, ts: int, kind: str, actions: list[dict], reason: str, tools: list[tuple[str, dict]]) -> None:
    trig = json.dumps({"instrument": "PF_SOLUSD", "move_bp": -342, "window_s": 3600, "pending_ts": ts - 300}) if kind == "wakeup" else "null"
    g.add("round_data", {"portfolio": pf, "round": rnd, "kind": kind, "trigger": trig, "sha256": "a" * 64, "message_sha256": "b" * 64,
                         "path": SECRET, "llm_config_sha256": "c" * 64, "budget_ceiling_uusd": 1_000_000}, ts)  # fmt: skip
    for n, (tool, args) in enumerate(tools, 1):
        g.add("tool_call", {"portfolio": pf, "round": rnd, "n": n, "tool": tool, "arguments": json.dumps(args, sort_keys=True),
                            "response": json.dumps({"gross": SECRET}), "response_sha256": "d" * 64, "is_error": False}, ts)  # fmt: skip
    g.add("agent_decision", {
        "portfolio": pf, "round": rnd, "kind": kind, "model_requested": pf.split(":")[1], "model_returned": pf.split(":")[1],
        "prompt_sha256": "e" * 64, "parsed": {"actions": actions, "justification": reason, "action_errors": []}, "parse_error": None,
        "tool_calls": len(tools), "num_turns": 3, "input_tokens": 12, "output_tokens": 640, "cache_read_tokens": 6400,
        "cache_write_tokens": 0, "cost_uusd": 75_000, "latency_ms": 13_200, "attempts": 1, "first_error": None, "cli_rc": 0,
        "cli_version": "2.1.99-secret", "stderr_tail": f"warning {SECRET}", "mcp_status": "connected",
        "tools_offered": ["mcp__arena__candles-secret"], "stream_sha256": "f" * 64, "budget_ceiling_uusd": 1_000_000,
        "result_seen": True, "charge_ceiling": False,
    }, ts)  # fmt: skip


def _action(inst: str, action: str, size: str, stop: str | None = None, tp: str | None = None, invalid: str | None = None) -> dict:
    return {"instrument": PF_KRAKEN[inst], "action": action, "size_pct": size, "stop_pct": stop, "take_profit_pct": tp,
            "horizon_h": 24, "expected_move_pct": "5", "confidence_pct": "60", "invalidation": invalid}  # fmt: skip


def _run(g: Gen, pf: str, inst: str, action: str, ts: int, k: int, approved: bool, reason_list: list[str] | None = None,
              qty: int = 0, stop_pct: int | None = None, tp_pct: int | None = None) -> None:  # fmt: skip
    iid = f"{pf}:{ts}:{k}".encode().hex()[:64]
    g.add("perp_verdict", {"intent_id": iid, "portfolio": pf, "instrument": PF_KRAKEN[inst], "action": action, "approved": approved,
                           "reasons": reason_list or [], "qty": qty if approved else None, "policy_sha256": "9" * 64, "error": None}, ts)  # fmt: skip
    if not approved:
        return
    g.fill(pf, inst, qty, ts, "intent", iid)
    px = price(inst, ts)
    if stop_pct:
        g.cond(pf, inst, "stop", px * (100 - stop_pct) // 100 if qty > 0 else px * (100 + stop_pct) // 100, ts)
    if tp_pct:
        g.cond(pf, inst, "take_profit", px * (100 + tp_pct) // 100 if qty > 0 else px * (100 - tp_pct) // 100, ts)
    g.add("perp_execution", {"intent_id": iid, "portfolio": pf, "instrument": PF_KRAKEN[inst], "status": "filled", "error": None}, ts)


def _order_triggered(g: Gen, ts: int) -> None:
    """Order-alerts spec §2.6: crossing, verdict, fill, stop and execution, all with intent_id = the order's id."""
    fable = LLMS[3]
    px = price("SOL-PERP", ts)
    g.add("agent_entry_triggered", {"portfolio": fable, "id": SOL_ORDER, "instrument": "PF_SOLUSD", "side": "long", "condition": "below",
                                    "price_uusd": px, "minute": ts - 120, "mark_high_uusd": px + 10, "mark_low_uusd": px - 10}, ts)  # fmt: skip
    qty = qty_for(100_000_000, "SOL-PERP", ts)
    g.add("perp_verdict", {"intent_id": SOL_ORDER, "portfolio": fable, "instrument": "PF_SOLUSD", "action": "open_long", "approved": True,
                           "reasons": [], "qty": qty, "policy_sha256": "9" * 64, "error": None}, ts)  # fmt: skip
    g.fill(fable, "SOL-PERP", qty, ts, "intent", SOL_ORDER)
    g.cond(fable, "SOL-PERP", "stop", px * 96 // 100, ts)
    g.cond(fable, "SOL-PERP", "take_profit", px * 108 // 100, ts)
    g.add("perp_execution", {"intent_id": SOL_ORDER, "portfolio": fable, "instrument": "PF_SOLUSD", "status": "filled", "error": None}, ts)
    g.add("agent_order_ended", {"portfolio": fable, "id": ALERT_LTC, "kind": "alert", "reason": "expired"}, ts)


def _sonnet_call(g: Gen, ts: int, end: int) -> None:
    """A regular call (or requested recall) of Sonnet after the last scheduled round: no action. The last one
    asks for a recall still to come when the site is built, and an invalid recall is refused."""
    sonnet = LLMS[1]
    kind = "scheduled" if ts % 1_800 == 0 else "cadence"
    _decision(g, sonnet, ts, ts + 10, kind, [], f"Nothing to do at {ts % 86_400 // 60} min: calm market.", [])
    g.add("agent_orders_set", {"portfolio": sonnet, "round": ts, "created_ts": ts + 10, "alerts": [], "entry_orders": [],
                               "rejected": [{"kind": "wakeup", "k": 0, "error": f"next_wakeup_min out of range {SECRET}"}]}, ts + 10)  # fmt: skip
    g.add("agent_wakeup_set", {"portfolio": sonnet, "round": ts, "minutes": 30, "due_ts": end + 1_500}, ts + 11)


def _alert_and_private_round(g: Gen, ts: int) -> None:
    fable = LLMS[3]
    px = price("BTC-PERP", ts)
    g.add("agent_alert_triggered", {"portfolio": fable, "id": ALERT_BTC, "instrument": "PF_XBTUSD", "condition": "above",
                                    "price_uusd": px, "minute": ts - 60, "mark_high_uusd": px, "mark_low_uusd": px - 5}, ts)  # fmt: skip
    r = ts + 300
    trig = {"alert_id": ALERT_BTC, "instrument": "PF_XBTUSD", "condition": "above", "price_usd": "89540.5", "note": ALERT_NOTE}
    g.add("perp_round", {"round": r, "kind": "alert", "portfolios": [fable], "trigger": trig, "ts": r}, r)
    g.add("round_data", {"portfolio": fable, "round": r, "kind": "alert", "trigger": json.dumps(trig), "sha256": "a" * 64,
                         "message_sha256": "b" * 64, "path": SECRET}, r + 10)  # fmt: skip
    g.add("agent_decision", {"portfolio": fable, "round": r, "kind": "alert", "model_requested": "claude-fable-5-2",
                             "parsed": {"actions": [], "justification": "The breakout does not hold on volume. I wait.", "action_errors": []},
                             "parse_error": None, "cost_uusd": 40_000}, r + 40)  # fmt: skip
    g.add("agent_orders_set", {"portfolio": fable, "round": r, "created_ts": r + 40, "rejected": [], "entry_orders": [],
                               "alerts": [{"id": ALERT_ETH, "instrument": "PF_ETHUSD", "condition": "below",
                                           "price_uusd": 3_050_000_000, "note": "weekly support", "expires_ts": r + 86_400 * 30}]}, r + 40)  # fmt: skip
    g.add("perp_round_done", {"round": r}, r + 60)


def _llm_round(g: Gen, ts: int, rnd: int, *, wake: bool) -> None:
    kind = "wakeup" if wake else "rendezvous"
    trig = {"instrument": "PF_SOLUSD", "move_bp": -342, "window_s": 3600, "pending_ts": ts - 300} if wake else None
    g.add("perp_round", {"round": ts, "kind": kind, "trigger": trig, "ts": ts}, ts)
    t = ts + 30
    if rnd == 1:  # benchmarks: 1/6 basket long everywhere, trend long/short with a 10% stop
        for i, inst in enumerate(BASE):
            g.fill("benchmark-perp:basket-1x", inst, qty_for(166_000_000, inst, t), t)
            q = qty_for(160_000_000, inst, t) * (1 if i % 2 == 0 else -1)
            g.fill("benchmark-perp:trend", inst, q, t)
            px = price(inst, t)
            g.cond("benchmark-perp:trend", inst, "stop", px * 90 // 100 if q > 0 else px * 110 // 100, t)
        _run(g, "benchmark-perp:random", "LTC-PERP", "open_long", t, 0, True, qty=qty_for(100_000_000, "LTC-PERP", t), stop_pct=5)
        _run(g, "benchmark-perp:random", "XRP-PERP", "open_short", t, 1, False, ["EDGE_TOO_SMALL", "MAX_TRADE_LOSS"])
    t = ts + 60
    fable, sonnet, opus, haiku = LLMS[3], LLMS[1], LLMS[2], LLMS[0]
    if rnd == 1:
        _decision(g, fable, ts, t, kind, [_action("ETH-PERP", "open_short", "25", "4", "8", INVALIDATION)], FABLE_REASON,
                  [("indicators", {"instrument": "PF_ETHUSD", "interval": "4h"}), ("derivatives", {"instrument": "PF_ETHUSD"})])
        _run(g, fable, "ETH-PERP", "open_short", t, 0, True, qty=-qty_for(250_000_000, "ETH-PERP", t), stop_pct=4, tp_pct=8)
        _decision(g, sonnet, ts, t, kind, [_action("BTC-PERP", "open_long", "30", "1", None, "BTC below $87,000")],
                  "Bullish trend over 4 h, neutral funding. Long BTC 30%, tight stop.", [("candles", {"instrument": "PF_XBTUSD", "interval": "1h", "n": 24})])
        _run(g, sonnet, "BTC-PERP", "open_long", t, 0, True, qty=qty_for(300_000_000, "BTC-PERP", t), stop_pct=1)
        _decision(g, opus, ts, t, kind, [_action("SOL-PERP", "open_long", "20", "5", "10", "SOL below $130"),
                                         _action("LINK-PERP", "open_short", "10", "3", None, "LINK above $15")],
                  "SOL bounces off a support, LINK runs out of steam. Two modest positions.", [("simulate_order", {"instrument": "PF_SOLUSD", "action": "open_long", "size_pct": 20})])
        _run(g, opus, "SOL-PERP", "open_long", t, 0, True, qty=qty_for(200_000_000, "SOL-PERP", t), stop_pct=5, tp_pct=10)
        _run(g, opus, "LINK-PERP", "open_short", t, 1, False, ["EDGE_TOO_SMALL", "TOO_SOON"])
        _decision(g, haiku, ts, t, kind, [], "Contradictory signal, the round-trip cost is not covered. I do nothing.", [])
    elif rnd == 2:
        _decision(g, fable, ts, t, kind, [_action("ETH-PERP", "close", "100")], "The target is far, funding is reversing: I close.", [])
        acc = g.book.states[fable]
        _run(g, fable, "ETH-PERP", "close", t, 0, True, qty=-acc.positions["ETH-PERP"].qty)
        exp = t + 4 * 3_600
        g.add("agent_orders_set", {
            "portfolio": fable, "round": ts, "created_ts": t,
            "alerts": [
                {"id": ALERT_BTC, "instrument": "PF_XBTUSD", "condition": "above", "price_uusd": price("BTC-PERP", t) * 101 // 100,
                 "note": ALERT_NOTE, "expires_ts": exp},
                {"id": ALERT_LTC, "instrument": "PF_LTCUSD", "condition": "below", "price_uusd": price("LTC-PERP", t) * 90 // 100,
                 "note": None, "expires_ts": t + 3_600},
            ],
            "entry_orders": [
                {"id": SOL_ORDER, "instrument": "PF_SOLUSD", "side": "long", "condition": "below", "price_uusd": price("SOL-PERP", t) * 99 // 100,
                 "size_bp": 1_000, "stop_bp": 400, "take_profit_bp": 800, "horizon_h": 24, "expected_move_bp": 500,
                 "confidence_pct": 55, "invalidation": INVALID_ORDER, "expires_ts": exp},
            ],
            "rejected": [{"kind": "entry", "k": 1, "error": f"level more than 25 % away from the mark {SECRET}"}],
        }, t)  # fmt: skip
        g.add("perp_llm_skipped", {"portfolio": haiku, "round": ts, "reason": "daily_budget"}, t)
    elif rnd == 3:
        g.add("round_data", {"portfolio": haiku, "round": ts, "kind": kind, "trigger": "null", "sha256": "a" * 64, "message_sha256": "b" * 64,
                             "path": SECRET, "llm_config_sha256": "c" * 64, "budget_ceiling_uusd": 100_000}, t)  # fmt: skip
        g.add("agent_decision", {"portfolio": haiku, "round": ts, "kind": kind, "model_requested": "claude-haiku-5-5", "parsed": None,
                                 "parse_error": f"no structured output: Traceback {SECRET}", "cost_uusd": 1_600, "latency_ms": 8_800,
                                 "stderr_tail": SECRET, "cli_version": "2.1.99-secret"}, t)  # fmt: skip
    if wake:
        _decision(g, opus, ts, t, kind, [_action("SOL-PERP", "reduce", "50")], "SOL drops 3.4% in an hour: I halve the position.", [])
        acc = g.book.states[opus]
        _run(g, opus, "SOL-PERP", "reduce", t, 0, True, qty=-acc.positions["SOL-PERP"].qty // 2)
    g.add("perp_round_done", {"round": ts}, t + 30)


def _opinions(g: Gen, ts: int, rnd: int, member: str, name: str, stage: str, opinion: dict | None, error: str | None = None,
          pf: str = COUNCIL) -> None:  # fmt: skip
    g.add("council_opinion", {"portfolio": pf, "round": rnd, "member": member, "name": name, "stage": stage,
                              "persona_sha256": "1" * 64, "opinion": opinion, "error": error, "cost_uusd": 1_500,
                              "input_tokens": 4, "output_tokens": 900, "latency_ms": 8_000, "tool_calls": 1,
                              "model_returned": "claude-haiku-5-5", "stream_sha256": "2" * 64}, ts)  # fmt: skip


def _council_round(g: Gen, ts: int, *, opens: bool, arbitrageur: bool = False, opus: bool = False) -> None:
    """A council round: 8 opinions (9 with the Arbitrageur) in stage A, one of them absent, the Advocate (B), then the
    President's decision (C). Haiku without the Arbitrageur = old format (no model or version field); `opus`: the
    Opus council, Opus President, 9 opinions, which opens a long SOL instead of the ETH short."""
    pf = OPUS if opus else COUNCIL
    t = ts + 50
    kind = "rendezvous" if opens else "cadence"
    g.add("round_data", {"portfolio": pf, "round": ts, "kind": kind, "trigger": "null", "sha256": "a" * 64, "message_sha256": "b" * 64,
                         "path": SECRET, "council_config_sha256": "c" * 64, "budget_ceiling_uusd": 1_000_000}, t)  # fmt: skip
    short = {"instrument": "PF_ETHUSD", "position": "short", "conviction": 65, "size_pct": "250", "stop_pct": "2.5", "key_level_usd": "3150"}
    flat = {"instrument": "PF_ETHUSD", "position": "flat", "conviction": 40, "size_pct": None, "stop_pct": None, "key_level_usd": None}
    members = [("mapper", "The Cartographer"), ("follower", "The Follower"), ("hunter", "The Breakout Hunter"),
               ("contrarian", "The Contrarian"), ("order_book", "The Order Book Reader"), ("treasurer", "The Leverage Treasurer"),
               ("guardian", "The Risk Guardian"), ("historian", "The Historian")]  # fmt: skip
    if arbitrageur:
        members.insert(4, ("arbitrageur", "The Pairs Arbitrageur"))
    for k, (m, n) in enumerate(members):
        if m == "order_book":
            _opinions(g, t, ts, m, n, "A", None, f"member crashed: OSError: {SECRET}", pf=pf)
            continue
        opinions = [flat] if m == "contrarian" else [short]
        _opinions(g, t, ts, m, n, "A", {"opinions": opinions, "target": None, "argument": ARG_ARBITRAGE if m == "arbitrageur" else ARG_MAPPER if m == "mapper" else f"Opinion {k} on ETH."}, pf=pf)
    _opinions(g, t, ts, "advocate", "The Devil's Advocate", "B",
          {"opinions": [flat], "target": {"instrument": "PF_ETHUSD", "side": "short"}, "argument": ARG_ADVOCATE}, pf=pf)
    for n, (m, tool) in enumerate([("mapper", "indicators"), ("advocate", "derivatives"), ("president", "simulate_order")], 1):
        g.add("tool_call", {"portfolio": pf, "round": ts, "member": m, "n": n, "tool": tool,
                            "arguments": json.dumps({"instrument": "PF_ETHUSD", "interval": "4h"}), "response": SECRET,
                            "response_sha256": "d" * 64, "is_error": False}, t)  # fmt: skip
    if opus:
        actions = [_action("SOL-PERP", "open_long", "200", "4", "6", "4 h close below $130")]
    else:
        actions = [_action("ETH-PERP", "open_short", "300", "3", "4", "rebound from $3,300"), _action("ETH-PERP", "open_short", "500", "15")] if opens else []
    reason = OPUS_REASON if opus else CHAIR_REASON if opens else "I keep the short."
    n_members = len(members)
    council = {"config_sha256": "c" * 64, "prompts_sha256": "e" * 64, "members_ok": n_members, "members_failed": ["order_book"],
               "president_cost_uusd": 180_000 if opus else 3_905, "president_latency_ms": 9_861, "president_tool_calls": 1}  # fmt: skip
    if arbitrageur:  # new journal fields; absent from the older decisions
        council.update({"name": "Opus Council" if opus else "Haiku Council", "members_model": "claude-haiku-5-5",
                        "prompts_version": "v2", "president_model": "claude-opus-5-5" if opus else "claude-haiku-5-5"})  # fmt: skip
    g.add("agent_decision", {
        "portfolio": pf, "round": ts, "kind": kind, "model_requested": "claude-haiku-5-5", "model_returned": "claude-haiku-5-5",
        "parsed": {"actions": actions, "justification": reason, "action_errors": []},
        "parse_error": None, "cost_uusd": 215_000 if opus else 24_849, "latency_ms": 41_000, "cli_version": "2.1.99-secret",
        "stderr_tail": SECRET, "council": council,
    }, t)  # fmt: skip
    if opus:
        _run(g, pf, "SOL-PERP", "open_long", t, 0, True, qty=qty_for(2_000_000_000, "SOL-PERP", t), stop_pct=4, tp_pct=6)
    elif opens:
        _run(g, pf, "ETH-PERP", "open_short", t, 0, True, qty=-qty_for(3_000_000_000, "ETH-PERP", t), stop_pct=3, tp_pct=4)
        _run(g, pf, "ETH-PERP", "open_short", t, 1, False, ["MAX_LEVERAGE", "LIQUIDATION_BEFORE_STOP"])


TRAP_TITLE = "Maintenance <script>alert(1)</script> of orders"
CPI_LABEL = "the November 2026 CPI (BLS)"


def _news_item(g: Gen, ts: int, **kw) -> None:
    p = {"source": "kraken_status", "id": "x", "kind": "incident", "title": "t", "status": "investigating", "impact": "minor",
         "published_ts": ts, "updated_ts": ts, "starts_ts": None, "ends_ts": None, "instruments": [], "url": "", "wake": False,
         "key": f"k{ts}", "fetched_ts": ts, "raw_sha256": "d" * 64}  # fmt: skip
    g.add("news_item", {**p, **kw}, ts)


def add_news(path: Path) -> Path:
    """Kraken announcements (two versions of an incident, a maintenance with a trap title, a 10-day-old announcement) and
    three private rounds: `news` (Fable), `calendar` (Haiku council), cadence carrying an announcement (Sonnet)."""
    g = Gen(path)
    end = T0 + 2 * 86_400
    _news_item(g, end - 10 * 86_400, id="old", title="Old Kraken announcement", status="resolved", published_ts=end - 10 * 86_400,
               updated_ts=end - 10 * 86_400, fetched_ts=end - 10 * 86_400)  # fmt: skip
    _news_item(g, end - 3_600, id="inc1", title="Order delays on the derivatives", status="investigating", impact="major",
               instruments=["PF_XBTUSD", "PF_ETHUSD"], url="https://stspg.io/abc")  # fmt: skip
    _news_item(g, end - 600, id="inc1", title="Order delays on the derivatives", status="resolved", impact="major", published_ts=end - 3_600,
               instruments=["PF_XBTUSD", "PF_ETHUSD"], url="https://stspg.io/abc")  # fmt: skip
    _news_item(g, end - 300, id="mt1", kind="maintenance", title=TRAP_TITLE, status="scheduled", impact="maintenance",
               starts_ts=end + 7_200, ends_ts=end + 10_800, instruments=["PF_XBTUSD"], url="javascript:alert(1)")  # fmt: skip
    fable, sonnet = LLMS[3], LLMS[1]
    for pf, rnd, kind, trig in (
        (fable, end + 20, "news", {"announcements": [{"kind": "incident", "status": "resolved", "title": "Order delays on the derivatives", "key": "k"}]}),
        (COUNCIL, end + 40, "calendar", {"releases": [{"id": "cpi-2026-11", "label": CPI_LABEL, "ts": end}]}),
        (sonnet, end + 60, "cadence", {"news": {"announcements": [{"kind": "maintenance", "status": "scheduled", "title": "Announced maintenance", "key": "m"}]}}),
    ):  # fmt: skip
        g.add("perp_round", {"round": rnd, "kind": kind, "portfolios": [pf], "trigger": trig, "ts": rnd}, rnd)
        g.add("round_data", {"portfolio": pf, "round": rnd, "kind": kind, "trigger": json.dumps(trig), "sha256": "a" * 64,
                             "message_sha256": "b" * 64, "path": SECRET}, rnd + 5)  # fmt: skip
        g.add("agent_decision", {"portfolio": pf, "round": rnd, "kind": kind, "model_requested": "claude-haiku-5-5",
                                 "parsed": {"actions": [], "justification": "Nothing to do.", "action_errors": []},
                                 "parse_error": None, "cost_uusd": 1_000}, rnd + 8)  # fmt: skip
        g.add("perp_round_done", {"round": rnd}, rnd + 9)
    return path
