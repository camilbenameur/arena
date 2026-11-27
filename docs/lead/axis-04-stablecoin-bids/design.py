"""Design: 9 logged trials on tape start -> 2026-03-31. Control is never read here."""
import json, itertools
from pathlib import Path
import numpy as np, bt
HERE = Path(__file__).resolve().parent
t, p, v = bt.load(); m = t < bt.DESIGN_END
t, p, v = t[m], p[m], v[m]
ez, ed = bt.eurusd(); mvw = bt.minute_vwap(t, p, v)
out = HERE / "trials.jsonl"
if out.exists(): raise SystemExit("trials.jsonl exists; refusing to rerun")
with out.open("w") as o:
    for L, H in itertools.product((20, 30, 50), (3, 5, 10)):
        f = bt.run(t, p, v, L, H, float(t[0]), bt.DESIGN_END, ez, ed, mvw)
        r = dict(level_bp=L, cap_days=H, period="design", **bt.summarize(f)); r["fills_detail"] = f
        o.write(json.dumps(r) + "\n"); print({k: r[k] for k in r if k != "fills_detail"})
print("tape", len(t), "trades", t[0], t[-1], "min", p.min(), "n<=0.9995:", int((p <= 0.9995).sum()), "n<=0.997", int((p <= 0.997).sum()), "n<=0.995", int((p <= 0.995).sum()))
