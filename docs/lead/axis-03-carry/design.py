"""Design phase: every trial, data strictly up to 2024-06-30 (control window never loaded into a
result). Appends one JSON line per trial (failures included) to trials.jsonl."""
import json, sys
from pathlib import Path
import pandas as pd
import carry, strategies as S, xvenue

HERE = Path(__file__).resolve().parent
LOG = HERE / "trials.jsonl"
START = pd.Timestamp("2020-04-01", tz="UTC")
END = carry.DESIGN_END

def run_trial(spec, bn, by):
    if spec["type"] == "xv":
        sp = xvenue.spread_frame(by.fund, bn.fund, [c for c in spec["coins"] if c in bn.fund and c in by.fund])
        eq, info = xvenue.simulate(sp, START, END, spec["w"], spec["enter"], spec["exit"], spec["k"])
    else:
        eq, info = carry.simulate(bn, START, END, S.build(spec), k=spec["k"], cost="base")
    return eq, info

def main():
    done = set()
    if LOG.exists():
        done = {json.loads(l)["spec"]["id"] for l in LOG.read_text().splitlines() if l.strip()}
    bn, by = carry.Data(fund_venue="bn"), carry.Data(fund_venue="by")
    print("coins", bn.coins, by.coins)
    for spec in S.DESIGN_TRIALS + S.XV_TRIALS:
        if spec["id"] in done: continue
        rec = dict(spec=spec, phase="design", window=[str(START.date()), str(END.date())])
        try:
            eq, info = run_trial(spec, bn, by)
            rec["metrics"] = carry.metrics(eq, info); rec["by_year"] = carry.by_year(eq)
        except Exception as e:
            rec["error"] = repr(e)
        with LOG.open("a") as f: f.write(json.dumps(rec) + "\n")
        m = rec.get("metrics", {})
        print(spec["id"], spec["type"], spec["coins"][:2], "ann", m.get("ann_ret"), "vol", m.get("ann_vol"), "dd", m.get("max_dd"),
              "sh", m.get("sharpe"), "tr/y", m.get("trades_per_year"), rec.get("by_year"), rec.get("error", ""))
if __name__ == "__main__": main()
