"""Research harness, v5 « agent agressif ».

Researchers ONLY use `design()`: the first DESIGN_DAYS of the year of 1-minute data. The rest (the sealed control)
is read once, by the coordinator, for frozen finalists. Never open data/ or *.pkl other than design.pkl.

    from harness import design, evaluate, log_trial
    d = design()                              # arene.perp.lab.backtest.Data, 6 contracts, 1-minute grid
    res = evaluate(d, targets, stop_pct=None)  # targets: (N, K) weights decided at the close of minute i (NaN = keep)
    log_trial("family", "name", params, res)  # mandatory for EVERY trial, failures included

Execution model = the live paper simulator (pessimiste-perp-v1): fill at the next minute's open, 5 bp slippage +
7 bp taker fee per side (24 bp per round trip), hourly funding, stops inside the minute, gross leverage <= 10x.
"""
from __future__ import annotations

import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from arene.perp.lab import backtest as B  # noqa: E402

HERE = Path(__file__).resolve().parent
DESIGN_DAYS = 245
N_BLOCKS = 4


def design() -> B.Data:
    return pickle.loads((HERE / "design.pkl").read_bytes())


def evaluate(d: B.Data, targets, stop_pct: float | None = None, rebalance_band: float = 0.05, start: int | None = None) -> dict:
    """Runs the bench on the design period from `start` (default: day 30, after a warm-up) and on 4 equal blocks."""
    s0 = 30 * 1440 if start is None else start
    full = B.run(d, targets, s0, d.n, stop_pct=stop_pct, rebalance_band=rebalance_band)
    out = full.summary()
    edges = np.linspace(s0, d.n, N_BLOCKS + 1).astype(int)
    eq = full.equity
    blocks = []
    for a, b in zip(edges[:-1], edges[1:]):
        e0 = 1.0 if a == s0 else eq[a - s0 - 1]
        blocks.append(round(100 * (eq[b - s0 - 1] / e0 - 1), 1) if e0 > 0 else -100.0)
    out["blocks"] = [float(x) for x in blocks]
    out["blocks_positive"] = int(sum(x > 0 for x in blocks))
    return {k: (v.item() if hasattr(v, "item") else v) for k, v in out.items()}


def log_trial(family: str, name: str, params: dict, res: dict) -> None:
    p = HERE / "essais" / f"{family}.jsonl"
    p.parent.mkdir(exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps({"ts": int(time.time()), "name": name, "params": params, "summary": res}) + "\n")
