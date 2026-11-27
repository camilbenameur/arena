#!/usr/bin/env python
"""Axis 9 evaluation of the frozen rule.

  python docs/lead/axis-09-llm-researcher/evaluate.py --period design     # in-sample (the model fitted on it): informative only
  python docs/lead/axis-09-llm-researcher/evaluate.py --period control    # sealed: needs the committed FROZEN preregistration, runs once

Steps: load frozen_rule.py; causality check on the design bars (targets recomputed on truncated data, zero gap required);
map the 4-hour targets onto the axis-8 minute bench; report against trend 2x, basket 1x and random weights with the same
turnover, with the axis-8 pass criteria (beats trend 2x and basket, max drawdown no deeper than 35%, positive in every month,
beats the 95th percentile of 20 random bots with the same turnover).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import common as C  # noqa: E402

RULE = HERE / "frozen_rule.py"
PREREG = HERE / "PREREGISTRATION.md"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", required=True, choices=["design", "control"])
    ap.add_argument("--rule", type=Path, default=RULE)
    ap.add_argument("--n-random", type=int, default=C.REP.N_RANDOM)
    a = ap.parse_args()
    if not a.rule.exists():
        raise SystemExit(f"{a.rule.name} does not exist")
    commit = ""
    if a.period == "control":
        if a.rule.resolve() != RULE.resolve():
            raise SystemExit("control refused: only the shipped frozen_rule.py can be run on the control")
        commit = C.control_gate(PREREG, RULE)
        if C.control_ran():
            raise SystemExit("control refused: the axis-9 control already ran (one rule, one control run)")
    fn = C.load_rule(a.rule)
    _, design = C.design_csv()
    gap = C.causality_gap(fn, design)
    print(f"causality gap on design bars: {gap:.3e}")
    if gap > 1e-12:
        raise SystemExit("rule refused: not causal (targets change when later rows are removed)")
    if a.period == "control":
        C.take_control_lock(commit, C.sha256_file(RULE))  # before the control data is touched
    rep = C.evaluate(fn, a.period, a.n_random)
    print(C.REP.table(rep))
    print("criteria:", rep["criteria"], "| ALL PASS:", rep["all_pass"])
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (C.DATA_DIR / f"eval_{a.period}.json").write_text(json.dumps(
        {"rule_sha256": C.sha256_file(a.rule), "prereg_commit": commit, "causality_gap": gap, "report": rep}, indent=1, default=float))


if __name__ == "__main__":
    main()
