"""Sealed control 2026-04-01 -> end of tape, all 9 trials, run ONCE (lock file)."""
import json, itertools, sys
from pathlib import Path
import numpy as np, bt
HERE = Path(__file__).resolve().parent
OUT = HERE / "control_results.json"
if OUT.exists(): sys.exit("control already run; refusing to run twice")
t, p, v = bt.load(); ez, ed = bt.eurusd(); mvw = bt.minute_vwap(t, p, v)
res = []
for L, H in itertools.product((20, 30, 50), (3, 5, 10)):
    f = bt.run(t, p, v, L, H, bt.DESIGN_END, float(t[-1]) + 1, ez, ed, mvw)
    r = dict(level_bp=L, cap_days=H, period="control", **bt.summarize(f)); r["fills_detail"] = f; res.append(r)
    print({k: r[k] for k in r if k != "fills_detail"})
OUT.write_text(json.dumps(dict(tape_first=float(t[0]), tape_last=float(t[-1]), results=res), default=float))
