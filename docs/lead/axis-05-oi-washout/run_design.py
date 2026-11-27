"""Design period only (rows before 2026-01-01 physically exist in the 'design' files). Runs the 16 pre-registered trials."""
import json
from pathlib import Path
import numpy as np
DATA = Path("~/dev/_arena-data/axis-05").expanduser()
from lib import BASE, SYMS, load, run_all, views, stats, _data

HERE = Path(__file__).resolve().parent
KINDS = ["design"]
TRIALS = []
n = 0
for side, name in ((1, "long"), (-1, "short")):
    for dl in (5, 15, 30, 60):
        n += 1
        TRIALS.append((n, f"{name}_delay{dl}", dict(BASE, side=side, delay=dl)))
for name, ch in [("pct10", dict(q=0.10)), ("z1.0", dict(z=1.0)), ("hold3h", dict(hold=180)), ("hold12h", dict(hold=720)),
                 ("stop3atr", dict(stopm=3.0)), ("nostop", dict(stopm=None)), ("oi2h", dict(W5=24)), ("oi8h", dict(W5=96))]:
    n += 1
    TRIALS.append((n, f"var_{name}_delay15", dict(BASE, **ch)))


def main():
    out = HERE / "trials.jsonl"
    if out.exists():
        raise SystemExit("trials.jsonl exists: design already run (void it explicitly and document a deviation to rerun)")
    res = {}
    with out.open("x") as f:
        for i, name, p in TRIALS:
            evs = run_all(KINDS, p)
            v = views(evs)
            rec = dict(kind="trial", trial=i, name=name, params=p, period="design", **v)
            f.write(json.dumps(rec) + "\n"); f.flush()
            res[name] = evs
            print(i, name, v["raw"].get("n"), "mean bp", round(v["raw"].get("mean_bp", 0), 1), "pf", round(v["raw"].get("pf", 0), 2),
                  "| declust n", v["declust"].get("n"), "mean", round(v["declust"].get("mean_bp", 0), 1), "pf", round(v["declust"].get("pf", 0), 2),
                  "| overlap", round(v["overlap_share"] or 0, 2), flush=True)
        # diagnostic: delay 1 minute (view of the base rule, not a trial)
        evs = run_all(KINDS, dict(BASE, delay=1))
        f.write(json.dumps(dict(kind="view", name="long_delay1_diagnostic", period="design", **views(evs))) + "\n")
        res["long_delay1"] = evs
    (DATA / "design_events.json").write_text(json.dumps(res))


if __name__ == "__main__":
    main()
