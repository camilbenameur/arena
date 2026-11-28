"""Item 2: the FROZEN trend engine (trend.FROZEN, scale 1 and 2), 5% protective stop, bench costs, six Binance contracts,
from 2020-01-31 (30-day warm-up, as v5) to 2025-10-31. Continuous compounding (preregistered) plus a post-hoc
fresh-start-per-year diagnostic. usage: PYTHONDONTWRITEBYTECODE=1 .venv/bin/python docs/lead/axis-10-long-history/run_trend.py"""
import dataclasses
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
from arena.perp.lab import backtest as B  # noqa: E402
from arena.perp.lab import trend as T  # noqa: E402

C.check_hashes()
OUT = HERE / "results"
OUT.mkdir(exist_ok=True)
S0 = 30 * 1440
STOP = 0.05


def analyse(res):
    s = res.summary()
    tr = C.trade_table(res, B.Costs())
    o = dict(trades=len(tr), total_pct=s["total_pct"], max_dd_pct=s["max_dd_pct"], sharpe=s["sharpe"], turnover_x=s["turnover_x"],
             fees_pct=s["fees_pct"], funding_pct=s["funding_pct"], ruined=s["ruined"], years=C.per_year(res))
    if tr:
        rets = np.array([x[2] for x in tr])
        o.update(win_rate_pct=round(100 * float((rets > 0).mean()), 1), mean_net_bp=round(1e4 * float(rets.mean()), 1))
    return o


def main():
    t0 = time.time()
    d = C.load()
    yr = C.year_of(d.ts)
    out = {}
    for scale in (1.0, 2.0):
        tg = T.targets(d, dataclasses.replace(T.FROZEN, scale=scale))
        res = B.run(d, tg, S0, d.n, stop_pct=STOP)
        r = analyse(res)
        key = f"{scale:g}x"
        out[key] = r
        ts, eq = C.daily_equity(res)
        np.savez(OUT / f"trend_{key}_daily.npz", ts=ts, eq=eq)
        print(key, r["trades"], r["total_pct"], r["max_dd_pct"], {y: x["ret_pct"] for y, x in r["years"].items()}, round(time.time() - t0), "s", flush=True)
        # post-hoc: each calendar year restarts at equity 1.0 (targets are causal, so slices of the full-period matrix are valid)
        fy, daily = {}, []
        for y in sorted(set(yr)):
            ix = np.where(yr == y)[0]
            a, b = max(int(ix[0]), S0), int(ix[-1]) + 1
            rs = B.run(d, tg, a, b, stop_pct=STOP)
            q = analyse(rs); q.pop("years")
            fy[int(y)] = q
            ts2, eq2 = C.daily_equity(rs)
            e = np.r_[1.0, eq2]
            daily.append((ts2, e[1:] / e[:-1] - 1))
            print("  fresh", key, y, q["trades"], q["total_pct"], q["max_dd_pct"], flush=True)
        out[key]["fresh_year"] = fy
        np.savez(OUT / f"trend_{key}_fresh_daily_ret.npz", ts=np.concatenate([x[0] for x in daily]), ret=np.concatenate([x[1] for x in daily]))
        (OUT / "trend.json").write_text(json.dumps(out, indent=1))
    print("done")


if __name__ == "__main__":
    main()
