"""Ledger tests: hand-computed golden scenarios, properties, counters, SQLite view."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from arena.journal import Journal
from arena.ledger import (
    LedgerError,
    equity_24h_ago,
    equity_ueur,
    fees_month,
    last_intent_ts,
    month_start_ts,
    orders_last_minute,
    peak_equity,
    rebuild_sqlite,
    replay,
    trades_last_24h,
)
from arena.types import QTY_SCALE, PortfolioState, Position, ceil_div, notional_ueur

GOLDEN = sorted((Path(__file__).parent / "golden" / "pnl").glob("*.json"))
T0 = 1_700_000_000  # 2023-11-14 22:13:20 UTC
CAP = 1_000_000_000


def rec(typ, ts, seq=0, **payload):
    return {"seq": seq, "ts": ts, "type": typ, "payload": payload}


def opened(name="p", cap=CAP, ts=T0):
    return rec("portfolio_opened", ts, portfolio=name, kind="llm", capital_ueur=cap, venue_mode="paper")


def fill(
    ts,
    name="p",
    sym="BTC/EUR",
    side="buy",
    qty=100_000,
    price=50_000_000_000,
    fee=250_000,
    reason="intent",
    order_id=None,
):
    r = rec(
        "fill",
        ts,
        portfolio=name,
        symbol=sym,
        side=side,
        qty=qty,
        price_ueur=price,
        fee_ueur=fee,
        reason=reason,
        order_id=order_id or f"o{ts}{side}{sym}",
        venue_mode="paper",
        fill_model_version="pessimistic-v1",
    )
    r["payload"]["ts"] = ts
    return r


# --------------------------------------------------------------------------- golden scenarios


def test_at_least_ten_golden_scenarios():
    assert len(GOLDEN) >= 10


@pytest.mark.parametrize("path", GOLDEN, ids=lambda p: p.stem)
def test_scenario_d_or(path, tmp_path):
    g = json.loads(path.read_text())
    assert g["explanation"].strip()
    # goes through the real journal: write, re-read, verify, replay
    jr = Journal(tmp_path / "events.jsonl")
    for e in g["events"]:
        jr.append(e["type"], e["payload"], e["ts"])
    assert jr.verify().ok
    states = replay(jr.iter_events())
    assert set(states) == set(g["expected"])
    for name, exp in g["expected"].items():
        s = states[name]
        assert s.cash_ueur == exp["cash_ueur"]
        assert s.fees_paid_ueur == exp["fees_paid_ueur"]
        assert s.realized_pnl_ueur == exp["realized_pnl_ueur"]
        assert {k: (p.qty, p.cost_ueur, p.stop_ueur) for k, p in s.positions.items()} == {
            k: (v["qty"], v["cost_ueur"], v["stop_ueur"]) for k, v in exp["positions"].items()
        }
        assert equity_ueur(s, g["marks"]) == exp["equity_ueur"]
        # invariant: cash + cost of the positions = capital + realized P&L
        capital = next(
            e["payload"]["capital_ueur"]
            for e in g["events"]
            if e["type"] == "portfolio_opened" and e["payload"]["portfolio"] == name
        )
        assert s.cash_ueur + sum(p.cost_ueur for p in s.positions.values()) == capital + s.realized_pnl_ueur


# --------------------------------------------------------------------------- errors and states


def test_sequence_errors():
    with pytest.raises(LedgerError):
        replay([fill(T0)])  # unknown portfolio
    with pytest.raises(LedgerError):
        replay([opened(), opened()])
    with pytest.raises(LedgerError):  # short sale
        replay([opened(), fill(T0, side="sell")])
    with pytest.raises(LedgerError):  # negative cash
        replay([opened(cap=1_000), fill(T0)])
    with pytest.raises(LedgerError):  # stop without a position
        replay([opened(), rec("stop_set", T0, portfolio="p", symbol="BTC/EUR", stop_ueur=1)])
    with pytest.raises(LedgerError):  # float refused
        replay([opened(), fill(T0, price=5.5)])
    with pytest.raises(LedgerError):  # sale > position
        replay([opened(), fill(T0), fill(T0 + 1, side="sell", qty=100_001)])


def test_freeze_stop_resume():
    s = replay(
        [
            opened(),
            rec("portfolio_frozen", T0, portfolio="p", reason="daily_loss", until_ts=T0 + 86_400),
            rec("portfolio_halted", T0 + 1, portfolio="p", reason="drawdown", until_ts=None),
        ]
    )["p"]
    assert s.frozen_until_ts == T0 + 86_400 and s.halted
    s = replay(
        [
            opened(),
            rec("portfolio_halted", T0, portfolio="p", reason="drawdown", until_ts=None),
            rec("portfolio_resumed", T0 + 1, portfolio="p", reason="manual", until_ts=None),
        ]
    )["p"]
    assert not s.halted and s.frozen_until_ts == 0


def test_unknown_events_ignored_and_stop_erased_at_sell():
    evs = [
        opened(),
        rec("cycle_started", T0, cycle=1),
        fill(T0 + 1),
        rec("stop_set", T0 + 2, portfolio="p", symbol="BTC/EUR", stop_ueur=45_000_000_000),
        fill(T0 + 3, side="sell"),
        fill(T0 + 4),
    ]
    s = replay(evs)["p"]
    assert s.positions["BTC/EUR"].stop_ueur is None  # new position, old stop gone


def test_equity_bid_priority_and_missing_price():
    s = PortfolioState("p", 10, {"BTC/EUR": Position("BTC/EUR", 3, 100, 0)})
    assert equity_ueur(s, {"BTC/EUR": 50_000_000_000}) == 10 + 1500
    assert equity_ueur(s, {"BTC/EUR": 1}, bids={"BTC/EUR": 33_333_333_333}) == 10 + 999  # rounded down
    with pytest.raises(LedgerError):
        equity_ueur(s, {})


# --------------------------------------------------------------------------- counters


def test_trades_last_24h():
    evs = [
        opened(),
        opened("q"),
        fill(T0 - 90_000),
        fill(T0 - 86_400),  # outside the window (bound excluded)
        fill(T0 - 86_399, side="sell", qty=1, price=1, fee=0),
        fill(T0, sym="ETH/EUR"),
        fill(T0 - 10, reason="stop", sym="SOL/EUR"),
        fill(T0 + 5),
        fill(T0, name="q"),
    ]
    assert trades_last_24h(evs, "p", T0) == 2
    assert trades_last_24h(evs, "p", T0, include_forced=True) == 3
    assert trades_last_24h(evs, "q", T0) == 1


def test_orders_last_minute():
    def os_(ts, oid, state="SUBMITTING"):
        return rec("order_state", ts, order_id=oid, state=state, detail="")

    evs = [
        os_(T0 - 61, "a"),
        os_(T0 - 59, "b"),
        os_(T0 - 59, "b", "ACKED"),
        os_(T0 - 1, "c"),
        os_(T0 - 1, "c"),
        os_(T0, "d", "INTENT"),
        os_(T0 + 1, "e"),
    ]
    assert orders_last_minute(evs, T0) == 2


def test_fees_month_utc_calendar_month():
    d = lambda y, m, dd, h=0: int(
        __import__("datetime").datetime(y, m, dd, h, tzinfo=__import__("datetime").UTC).timestamp()
    )  # noqa: E731
    nov_start = d(2026, 11, 1)
    assert month_start_ts(d(2026, 11, 30, 23)) == nov_start
    assert month_start_ts(nov_start) == nov_start
    evs = [
        fill(nov_start - 1, fee=1000),
        fill(nov_start, fee=10),
        fill(d(2026, 11, 15), fee=20),
        fill(d(2026, 11, 15), name="q", fee=500),
        fill(d(2026, 12, 1), fee=7000),
    ]
    assert fees_month(evs, "p", d(2026, 11, 20)) == 30
    assert fees_month(evs, "p", d(2026, 12, 1)) == 7000


def test_last_intent_ts():
    def it(ts, iid, sym="BTC/EUR", name="p"):
        return rec("intent", ts, intent_id=iid, portfolio=name, symbol=sym, side="buy", size_bp=1)

    evs = [it(10, "a"), it(30, "b"), it(20, "c", sym="ETH/EUR"), it(40, "d", name="q")]
    assert last_intent_ts(evs, "p", "BTC/EUR") == 30
    assert last_intent_ts(evs, "p", "BTC/EUR", exclude_intent_id="b") == 10
    assert last_intent_ts(evs, "p", "BTC/EUR", before_ts=30) == 10
    assert last_intent_ts(evs, "p", "SOL/EUR") is None


def test_peak_and_equity_24h():
    def eq(ts, v, name="p"):
        return rec("equity", ts, portfolio=name, cycle=ts, cash_ueur=v, positions_value_ueur=0, equity_ueur=v)

    evs = [opened(ts=T0), eq(T0 + 100, 1_050_000_000), eq(T0 + 200, 900_000_000), eq(T0 + 300, 5, "q")]
    assert peak_equity(evs, "p") == 1_050_000_000
    assert peak_equity([opened(), eq(T0 + 1, 800_000_000)], "p") == CAP  # the initial capital counts
    assert peak_equity(evs, "zz") is None
    now = T0 + 86_400 + 150
    assert equity_24h_ago(evs, "p", now) == 1_050_000_000  # last equity with ts <= now - 24 h
    assert equity_24h_ago(evs, "p", T0 + 5000) == CAP  # too recent: falls back to the capital
    assert equity_24h_ago(evs, "zz", now) is None


# --------------------------------------------------------------------------- Derived SQLite


def test_rebuild_sqlite(tmp_path):
    jr = Journal(tmp_path / "e.jsonl")
    jr.append(
        "portfolio_opened",
        {"portfolio": "p", "kind": "llm", "capital_ueur": 10**15, "venue_mode": "paper"},
        T0,
    )
    f = fill(T0 + 1)["payload"]
    jr.append("fill", f, T0 + 1)
    jr.append(
        "equity",
        {
            "portfolio": "p",
            "cycle": T0,
            "cash_ueur": 10**15,
            "positions_value_ueur": 5,
            "equity_ueur": 10**15 + 5,
        },
        T0 + 2,
    )
    jr.append(
        "decision_received",
        {
            "portfolio": "p",
            "cycle": T0,
            "model_requested": "m",
            "model_returned": "m",
            "raw_text": "x",
            "parsed": None,
            "parse_error": "e",
            "input_tokens": 1,
            "output_tokens": 2,
            "cost_uusd": 3,
            "latency_ms": 4,
        },
        T0 + 3,
    )
    jr.append("decision_skipped", {"portfolio": "p", "cycle": T0, "reason": "budget"}, T0 + 4)
    db = tmp_path / "ledger.sqlite"
    assert rebuild_sqlite(jr.iter_events(), db) == {"fills": 1, "equity": 1, "decisions": 2}
    con = sqlite3.connect(db)
    assert con.execute("SELECT qty, price_ueur, fee_ueur, side FROM fills").fetchall() == [
        (100_000, 50_000_000_000, 250_000, "buy")
    ]
    assert con.execute("SELECT equity_ueur FROM equity").fetchone() == (10**15 + 5,)
    assert con.execute("SELECT kind, reason, cost_uusd FROM decisions ORDER BY seq").fetchall() == [
        ("received", None, 3),
        ("skipped", "budget", None),
    ]
    assert con.execute("SELECT value FROM meta WHERE key='head_seq'").fetchone() == ("4",)
    con.close()
    # idempotent rebuild: starting again from zero
    assert rebuild_sqlite(jr.iter_events(), db)["fills"] == 1


# --------------------------------------------------------------------------- properties

SYMS = ["BTC/EUR", "ETH/EUR", "XRP/EUR"]
op_st = st.tuples(
    st.sampled_from(["buy", "sell"]),
    st.integers(0, 2),
    st.integers(1, 1000),
    st.integers(1_000, 100_000_000_000),
)


def build_valid_events(capital: int, ops) -> list[dict]:
    """Build a valid sequence: quantities are bounded by the cash and the positions held."""
    cash, held = capital, {s: 0 for s in SYMS}
    evs = [opened(cap=capital)]
    ts = T0
    for side, i, permille, price in ops:
        sym, ts = SYMS[i], ts + 1
        if side == "buy":
            qty = (cash * permille // 1000) * QTY_SCALE // price
            while qty > 0:
                gross = notional_ueur(qty, price, round_up=True)
                fee = ceil_div(gross * 50, 10_000)
                if gross + fee <= cash:
                    break
                qty = qty * 9 // 10
            if qty <= 0:
                continue
            cash -= gross + fee
            held[sym] += qty
        else:
            qty = held[sym] if permille == 1000 else held[sym] * permille // 1000
            if qty <= 0:
                continue
            gross = notional_ueur(qty, price, round_up=False)
            fee = ceil_div(gross * 50, 10_000)
            cash += gross - fee
            held[sym] -= qty
        evs.append(fill(ts, sym=sym, side=side, qty=qty, price=price, fee=fee))
    return evs


@settings(max_examples=300, deadline=None)
@given(capital=st.integers(1_000_000, 10**13), ops=st.lists(op_st, max_size=40))
def test_prop_replay_invariants_positive_cash(capital, ops):
    evs = build_valid_events(capital, ops)
    s1, s2 = replay(evs), replay(list(evs))
    assert s1 == s2  # determinism
    s = s1["p"]
    assert s.cash_ueur >= 0  # no negative cash on a valid sequence
    assert all(p.qty > 0 and p.cost_ueur >= 0 for p in s.positions.values())
    assert s.cash_ueur + sum(p.cost_ueur for p in s.positions.values()) == capital + s.realized_pnl_ueur
    assert s.fees_paid_ueur == sum(e["payload"]["fee_ueur"] for e in evs if e["type"] == "fill")


@settings(max_examples=25, deadline=None)
@given(capital=st.integers(1_000_000, 10**13), ops=st.lists(op_st, max_size=15))
def test_prop_replay_from_identical_file(capital, ops):
    evs = build_valid_events(capital, ops)
    with tempfile.TemporaryDirectory() as d:
        jr = Journal(Path(d) / "e.jsonl")
        for e in evs:
            jr.append(e["type"], e["payload"], e["ts"])
        assert jr.verify().ok
        assert replay(jr.iter_events()) == replay(evs)
