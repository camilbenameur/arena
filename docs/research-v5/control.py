"""Coordinator only. For each frozen finalist: causality check, then ONE read of the sealed control (the 121 days
after the design period), plus the full year. usage: python control.py finalists/*.py"""
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from arena.perp.lab import backtest as B  # noqa: E402
from arena.perp.lab import trend as T  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from harness import DESIGN_DAYS  # noqa: E402

full = pickle.loads((HERE / "full.pkl").read_bytes())
c0 = DESIGN_DAYS * 1440


def cut(d, n):
    return B.Data(d.ts[:n], d.open[:n], d.high[:n], d.low[:n], d.close[:n], d.volume[:n], d.funding[:n])


def causal(fn):
    """Targets computed on truncated data must equal the full-data targets on the common rows."""
    t_full = fn(full)
    worst = 0.0
    for frac in (0.55, 0.7, 0.85, 0.97):
        n = int(full.n * frac)
        t_cut = fn(cut(full, n))
        a, b = t_full[:n], t_cut
        same_nan = np.array_equal(np.isnan(a), np.isnan(b))
        diff = np.nanmax(np.abs(np.nan_to_num(a, nan=0) - np.nan_to_num(b, nan=0)))
        if not same_nan:
            diff = max(diff, 1.0)
        worst = max(worst, float(diff))
    return worst, t_full


def summ(t, stop, a, b):
    r = B.run(full, t, a, b, stop_pct=stop)
    s = r.summary()
    return {k: (v.item() if hasattr(v, "item") else v) for k, v in s.items()}


out = {}
ref = T.targets(full, T.TrendParams(scale=2.0))
out["reference-trend-2x"] = {"control": summ(ref, 0.05, c0, full.n), "year": summ(ref, 0.05, 30 * 1440, full.n)}
for path in sys.argv[1:]:
    spec = importlib.util.spec_from_file_location(Path(path).stem, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    worst, t = causal(m.targets)
    stop = getattr(m, "STOP_PCT", None)
    out[Path(path).stem] = {
        "causality_gap_max": worst,
        "control": summ(t, stop, c0, full.n),
        "year": summ(t, stop, 30 * 1440, full.n),
    }
for k, v in out.items():
    c, y = v["control"], v["year"]
    print(f"{k:40s} causal {v.get('causality_gap_max', 0):.2g} | control {c['total_pct']:+8.1f}% ({c['per_day_pct']:+.3f}/d) dd {c['max_dd_pct']:6.1f} ruin {c['ruined']} | year {y['total_pct']:+8.1f}% dd {y['max_dd_pct']:6.1f}", flush=True)
(HERE / "control.json").write_text(json.dumps(out, indent=1))
