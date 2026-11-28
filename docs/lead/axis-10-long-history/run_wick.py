"""Item 1: the FROZEN wick rule on Binance 1-minute data, 2020-01-01 -> 2025-10-31. No parameter changed.
Variants: base / entry +1 minute / 48 bp round trip; six contracts together and each contract alone.
usage: PYTHONDONTWRITEBYTECODE=1 .venv/bin/python docs/lead/axis-10-long-history/run_wick.py"""
import importlib.util
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
from arena.perp.lab import backtest as B  # noqa: E402

C.check_hashes()
OUT = HERE / "results"
OUT.mkdir(exist_ok=True)


def delayed(t, m=1):
    out = np.full_like(t, np.nan)
    out[m:] = t[:-m]
    return out


def sub(d, ix):
    return B.Data(d.ts, d.open[:, ix], d.high[:, ix], d.low[:, ix], d.close[:, ix], d.volume[:, ix], d.funding[:, ix],
                  tuple(d.instruments[i] for i in ix))


def analyse(res, costs):
    s = res.summary()
    tr = C.trade_table(res, costs)
    o = dict(trades=len(tr), total_pct=s["total_pct"], max_dd_pct=s["max_dd_pct"], sharpe=s["sharpe"],
             funding_pct=s["funding_pct"], ruined=s["ruined"], years=C.per_year(res))
    below = np.where(res.equity <= 0.1)[0]
    o["first_minute_equity_below_0.1"] = (int(res.ts[below[0]]) if len(below) else None)
    if tr:
        rets = np.array([x[2] for x in tr]); pnl = np.array([x[3] for x in tr])
        yrs = C.year_of(np.array([x[1] for x in tr]))
        o.update(win_rate_pct=round(100 * float((rets > 0).mean()), 1), mean_net_bp=round(1e4 * float(rets.mean()), 1),
                 median_net_bp=round(1e4 * float(np.median(rets)), 1), stops=sum(1 for x in tr if x[4] == "stop"),
                 shock_days=len({int(x[1] // 86400) for x in tr}))
        gp = pnl[pnl > 0].sum()
        o["top5_share_of_gross_profit_pct"] = round(100 * float(np.sort(pnl)[::-1][:5].sum() / gp), 1) if gp > 0 else None
        net = pnl.sum()
        by_y, by_c = defaultdict(float), defaultdict(float)
        cnt_y = defaultdict(int)
        for (inst, _, _, p, _), y in zip(tr, yrs):
            by_y[int(y)] += p; by_c[inst] += p; cnt_y[int(y)] += 1
        o["pnl_by_year_usd_units"] = {k: round(v, 3) for k, v in sorted(by_y.items())}
        o["trades_by_year"] = dict(sorted(cnt_y.items()))
        o["pnl_by_contract_usd_units"] = {k: round(v, 3) for k, v in sorted(by_c.items(), key=lambda kv: -kv[1])}
        o["net_trade_pnl_usd_units"] = round(float(net), 3)
        o["top_year"] = max(by_y, key=by_y.get)
        o["top_year_share_of_net_pct"] = round(100 * by_y[o["top_year"]] / net, 1) if net > 0 else None
        # same measure, without the compounding distortion: sum of net bp per year
        o["top5_trades"] = [(tr[i][0], int(tr[i][1]), round(1e4 * tr[i][2], 1)) for i in np.argsort(-pnl)[:5]]
    return o


def main():
    t0 = time.time()
    d = C.load()
    spec = importlib.util.spec_from_file_location("wick", C.REPO / "docs/research-v5/finalists/shocks_fade-wickS.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    variants = {"base": (lambda t: t, B.Costs()), "delay1": (lambda t: delayed(t, 1), B.Costs()),
                "cost48": (lambda t: t, B.Costs(fee_bp=14.0, slippage_bp=10.0))}
    out = {"portfolio": {}, "per_contract": {}}
    T6 = m.targets(d)
    print("targets", round(time.time() - t0), "s", flush=True)
    for v, (fn, costs) in variants.items():
        res = B.run(d, fn(T6), 0, d.n, stop_pct=m.STOP_PCT, costs=costs)
        out["portfolio"][v] = analyse(res, costs)
        r = out["portfolio"][v]
        print(v, r["trades"], r["total_pct"], r["max_dd_pct"], {y: x["ret_pct"] for y, x in r["years"].items()}, round(time.time() - t0), "s", flush=True)
        ts, eq = C.daily_equity(res)
        np.savez(OUT / f"wick_{v}_daily.npz", ts=ts, eq=eq)
        (OUT / "wick.json").write_text(json.dumps(out, indent=1))
    # POST-HOC DIAGNOSTIC (added after the continuous run was seen to be ruined in March 2020, see README): every calendar
    # year restarts at equity 1.0 with fresh rule state (targets recomputed on that year's data only). Not the
    # preregistered per-year series; reported next to it.
    yr = C.year_of(d.ts)
    out["fresh_year"] = {}
    fresh_daily = {v: [] for v in variants}
    for y in sorted(set(yr)):
        ix = np.where(yr == y)[0]
        a, b = int(ix[0]), int(ix[-1]) + 1
        dy = B.Data(d.ts[a:b], d.open[a:b], d.high[a:b], d.low[a:b], d.close[a:b], d.volume[a:b], d.funding[a:b], d.instruments)
        Ty = m.targets(dy)
        for v, (fn, costs) in variants.items():
            res = B.run(dy, fn(Ty), 0, dy.n, stop_pct=m.STOP_PCT, costs=costs)
            r = analyse(res, costs)
            r.pop("years", None); r.pop("pnl_by_contract_usd_units", None); r.pop("pnl_by_year_usd_units", None)
            out["fresh_year"].setdefault(v, {})[int(y)] = r
            ts, eq = C.daily_equity(res)
            e = np.r_[1.0, eq]
            fresh_daily[v].append((ts, e[1:] / e[:-1] - 1))
            print("fresh", y, v, r["trades"], r["total_pct"], r["max_dd_pct"], round(time.time() - t0), "s", flush=True)
        (OUT / "wick.json").write_text(json.dumps(out, indent=1))
    for v in variants:
        np.savez(OUT / f"wick_{v}_fresh_daily_ret.npz", ts=np.concatenate([x[0] for x in fresh_daily[v]]),
                 ret=np.concatenate([x[1] for x in fresh_daily[v]]))
    for j, s in enumerate(d.instruments):
        ds = sub(d, [j])
        Tj = m.targets(ds)
        for v, (fn, costs) in variants.items():
            res = B.run(ds, fn(Tj), 0, ds.n, stop_pct=m.STOP_PCT, costs=costs)
            r = analyse(res, costs)
            r.pop("pnl_by_contract_usd_units", None)
            out["per_contract"].setdefault(s, {})[v] = r
        r = out["per_contract"][s]["base"]
        print(s, r["trades"], r["total_pct"], r["max_dd_pct"], round(time.time() - t0), "s", flush=True)
        (OUT / "wick.json").write_text(json.dumps(out, indent=1))
    print("done")


if __name__ == "__main__":
    main()
