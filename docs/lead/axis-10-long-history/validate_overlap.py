"""Pipeline check (not one of the preregistered items, and run AFTER the main wick result): the same frozen wick rule and bench on
the same Binance loader, but over the research-v5 year (2025-11-17 -> 2026-10-31, 30-day warm-up as v5). It must land near
the Kraken figures (v5 year: 92 trades, +295%, dd -37%, 71.5 bp/trade) or the long-history loader is suspect.
usage: PYTHONDONTWRITEBYTECODE=1 .venv/bin/python docs/lead/axis-10-long-history/validate_overlap.py"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
from arena.perp.lab import backtest as B  # noqa: E402

C.check_hashes()
ns = {"__file__": str(HERE / "common.py")}
exec(compile((HERE / "common.py").read_text().replace('if ym > "2025-10":', 'if ym > "2026-10":'), "common_overlap", "exec"), ns)
ns["START"] = int(pd.Timestamp("2025-11-17", tz="UTC").timestamp())
ns["END"] = int(pd.Timestamp("2026-11-01", tz="UTC").timestamp())
ns["N"] = (ns["END"] - ns["START"]) // 60
arrs = {k: [] for k in "ohlcf"}
for s in C.SYMS:
    o, h, l, c, f, _, _ = ns["build_symbol"](s)
    for k, a in zip("ohlcf", (o, h, l, c, f)):
        arrs[k].append(a)
ts = np.arange(ns["START"], ns["END"], 60, dtype=np.int64)
d = B.Data(ts, *[np.stack(arrs[k], 1) for k in "ohlc"], np.zeros((len(ts), 6)), np.stack(arrs["f"], 1), tuple(C.SYMS))
spec = importlib.util.spec_from_file_location("wick", C.REPO / "docs/research-v5/finalists/shocks_fade-wickS.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
T = m.targets(d)
out = {}
for name, shift in (("base", 0), ("delay1", 1)):
    t = T if not shift else np.vstack([np.full((shift, 6), np.nan), T[:-shift]])
    r = B.run(d, t, 30 * 1440, d.n, stop_pct=m.STOP_PCT)
    tr = C.trade_table(r, B.Costs())
    rets = np.array([x[2] for x in tr])
    s = r.summary()
    out[name] = dict(total_pct=s["total_pct"], max_dd_pct=s["max_dd_pct"], trades=len(tr), mean_net_bp=round(1e4 * float(rets.mean()), 1),
                     win_rate_pct=round(100 * float((rets > 0).mean()), 1))
    print(name, out[name])
out["kraken_v5_year_for_reference"] = dict(total_pct=295.5, max_dd_pct=-37.3, trades=92, mean_net_bp=71.5, win_rate_pct=77.2)
(HERE / "results" / "overlap_check.json").write_text(json.dumps(out, indent=1))
