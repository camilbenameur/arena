"""Runs the golden perp scenarios (tests/golden/perp/scenarios.json) through the real simulator and ledger."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from arene.journal import Journal
from arene.perp.ledger import PerpBook, PerpLedgerError, apply_fill
from arene.perp.sim import MinuteCandles, PerpSimulator, SimParams

GOLDEN = Path(__file__).parent / "golden" / "perp"


def load_scenarios() -> dict[str, Any]:
    return json.loads((GOLDEN / "scenarios.json").read_text(encoding="utf-8"))


def run_scenario(steps: list[dict[str, Any]], tmp: Path, spec: dict[str, Any]) -> dict[str, Any]:
    journal = Journal(tmp / "events.jsonl")
    sim = PerpSimulator(journal, spec["ticks"], SimParams(**spec["params"]))
    sim.open_portfolio("P", "test", 0)
    error = False
    mids: dict[str, int] = {}
    for n, step in enumerate(steps, 1):
        fx = tuple(step["fx"]) if "fx" in step else None
        op = step["op"]
        try:
            if op == "market":
                mids[step["instrument"]] = (step["bid"] + step["ask"]) // 2
                sim.market_order(
                    f"o{n}",
                    "P",
                    step["instrument"],
                    step["qty"],
                    (step["bid"], step["ask"]),
                    fx,
                    step["ts"],
                    marks=mids,
                )
            elif op == "conditional":
                sim.set_conditional("P", step["instrument"], step["kind"], step["price"], step["ts"])
            elif op == "minute":
                cs = {
                    i: MinuteCandles(tuple(c["mark"]), tuple(c["trade"]) if c.get("trade") else None)
                    for i, c in step["candles"].items()
                }
                sim.process_minute(step["ts"], cs, fx)
            elif op == "funding":
                sim.settle_funding(step["instrument"], step["stamp"], step["rate_nusd"], fx)
            elif op == "missing_funding":
                sim.record_missing_funding(step["instrument"], step["stamp"])
            elif op == "max_holding":
                sim.close_expired(step["ts"], {i: tuple(q) for i, q in step["quotes"].items()}, fx)
            else:
                raise ValueError(op)
        except PerpLedgerError:
            if not step.get("expect_error"):
                raise
            error = True
    events = journal.events()
    book = PerpBook()
    fills, fundings = [], []
    for e in events:
        p = e["payload"]
        if e["type"] == "perp_fill":
            eff = apply_fill(copy.deepcopy(book.states[p["portfolio"]]), p, e["ts"], e["seq"])
            fills.append(
                {
                    "reason": p["reason"],
                    "instrument": p["instrument"],
                    "qty": p["qty"],
                    "price_uusd": p["price_uusd"],
                    "fee_ueur": p["fee_ueur"],
                    "realized_ueur": eff.realized_ueur,
                }
            )
        elif e["type"] == "funding":
            fundings.append(
                {"instrument": p["instrument"], "stamp": p["stamp"], "amount_ueur": p["amount_ueur"]}
            )
        book.apply(e)
    acc = book.states["P"]
    assert acc.invariant_ok()
    return {
        "fills": fills,
        "fundings": fundings,
        "error_raised": error,
        "margin_closeout": any(e["type"] == "margin_closeout" for e in events),
        "final": {
            "collateral_ueur": acc.collateral_ueur,
            "realized_pnl_ueur": acc.realized_pnl_ueur,
            "fees_paid_ueur": acc.fees_paid_ueur,
            "funding_paid_ueur": acc.funding_paid_ueur,
            "absorbed_deficit_ueur": acc.absorbed_deficit_ueur,
            "positions": [
                {"instrument": i, "qty": p.qty, "entry_uusd": p.entry_uusd}
                for i, p in sorted(acc.positions.items())
            ],
        },
    }
