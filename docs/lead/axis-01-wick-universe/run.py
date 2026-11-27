"""Steps 3-4: run the FROZEN finalist docs/research-v5/finalists/shocks_fade-wickS.py, untouched, on the new contracts.
No parameter is changed. Variants: base / entry delayed 1 minute / doubled costs (48 bp round trip).
usage: .venv/bin/python docs/lead/axis-01-wick-universe/run.py"""
import importlib.util, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from arena.perp.lab import backtest as B  # noqa: E402

DATA = Path("~/dev/_arena-data/axis-01").expanduser()
HERE = Path(__file__).resolve().parent
START = 1763337600
END = START + 366 * 86400
S0 = 30 * 1440                       # same warm-up as the v5 "year" figure
NON_CRYPTO = {"PF_NVDAXUSD", "PF_MSTRXUSD", "PF_SPYXUSD", "PF_XAUTUSD"}  # tokenised stocks / ETF / gold

u = json.loads((DATA / "universe.json").read_text())
STUDIED = u["studied"]
A = [r["symbol"] for r in u["selected"]]
EXT = [r["symbol"] for r in u["extended"]]
ALL = STUDIED + [s for s in A + EXT if s not in STUDIED]
ALL = list(dict.fromkeys(ALL))


def load(symbols):
    ts = np.arange(START, END, 60, dtype=np.int64)
    n, k = len(ts), len(symbols)
    o, h, l, c = (np.full((n, k), np.nan) for _ in range(4)); v = np.zeros((n, k)); f = np.zeros((n, k))
    for j, s in enumerate(symbols):
        a = np.loadtxt(DATA / "candles" / f"{s}.csv", delimiter=",", ndmin=2)
        idx = ((a[:, 0] - START) // 60).astype(int)
        ok = (idx >= 0) & (idx < n)
        a, idx = a[ok], idx[ok]
        for arr, col in ((o, 1), (h, 2), (l, 3), (c, 4)):
            arr[idx, j] = a[:, col]
        v[idx, j] = a[:, 5]
        # missing minute: flat at the previous close (as backtest.load); before the first candle: flat at its open
        cj = c[:, j]
        valid = ~np.isnan(cj)
        last = np.maximum.accumulate(np.where(valid, np.arange(n), -1))
        first = int(np.argmax(valid))
        fillc = np.where(last >= 0, cj[np.maximum(last, 0)], np.nan)
        fillc[:first] = o[first, j]
        for arr in (o, h, l, c):
            arr[~valid, j] = fillc[~valid]
        for r in json.loads((DATA / "funding" / f"{s}.json").read_text()):
            t = int(datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).timestamp())
            if START <= t < END and (t - START) % 60 == 0:
                f[(t - START) // 60, j] = float(r["relativeFundingRate"])
    return B.Data(ts, o, h, l, c, v, f, tuple(symbols))


def sub(d, syms):
    ix = [d.instruments.index(s) for s in syms]
    return B.Data(d.ts, d.open[:, ix], d.high[:, ix], d.low[:, ix], d.close[:, ix], d.volume[:, ix], d.funding[:, ix], tuple(syms)), ix


def delayed(t, m=1):
    out = np.full_like(t, np.nan); out[m:] = t[:-m]; return out


def qlabel(ts):
    d = datetime.fromtimestamp(int(ts), timezone.utc); return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def analyse(res, costs):
    eq, ts = res.equity, res.ts
    s = res.summary()
    fee = costs.fee_bp / 1e4
    tr = []
    for t in res.trades:
        ret = t.side * (t.exit / t.entry - 1) - 2 * fee          # price move incl. slippage fills, minus both fees
        tr.append((t.instrument, t.entry_ts, ret, t.notional * ret))
    rets = np.array([x[2] for x in tr]); pnl = np.array([x[3] for x in tr])
    out = {"events": len(tr), "total_pct": s["total_pct"], "max_dd_pct": s["max_dd_pct"], "per_day_pct": s["per_day_pct"],
           "funding_pct": s["funding_pct"], "ruined": s["ruined"], "turnover_x": s["turnover_x"]}
    if tr:
        out.update(win_rate_pct=round(100 * float((rets > 0).mean()), 1), mean_net_ret_bp=round(1e4 * float(rets.mean()), 1),
                   median_net_ret_bp=round(1e4 * float(np.median(rets)), 1),
                   shock_days=len({datetime.fromtimestamp(x[1], timezone.utc).date() for x in tr}),
                   stops=sum(1 for t in res.trades if t.reason == "stop"))
        order = np.argsort(-pnl)
        gp = pnl[pnl > 0].sum()
        out["top5_pnl_share_of_gross_profit_pct"] = round(100 * float(pnl[order[:5]].sum() / gp), 1) if gp > 0 else None
        out["top5_pnl_usd_units"] = round(float(pnl[order[:5]].sum()), 3)
        out["net_trade_pnl_usd_units"] = round(float(pnl.sum()), 3)
        by = {}
        for inst, _, _, p in tr: by[inst] = by.get(inst, 0.0) + p
        top = max(by, key=lambda k: by[k])
        out["top_contract"] = top; out["top_contract_pnl_share_pct"] = round(100 * by[top] / pnl.sum(), 1) if pnl.sum() > 0 else None
        out["pnl_by_contract"] = {k: round(v, 3) for k, v in sorted(by.items(), key=lambda kv: -kv[1])}
        # max simultaneous positions
        ev = sorted([(t.entry_ts, 1) for t in res.trades] + [(t.exit_ts, -1) for t in res.trades], key=lambda x: (x[0], x[1]))
        cur = mx = 0
        for _, dlt in ev: cur += dlt; mx = max(mx, cur)
        out["max_simultaneous_positions"] = mx
    # per calendar quarter
    q = np.array([qlabel(t) for t in ts[::1440]]); qs = {}
    daily_idx = np.arange(0, len(eq), 1440)
    labs = [qlabel(ts[i]) for i in daily_idx]
    for lab in dict.fromkeys(labs):
        ii = [i for i, l in zip(daily_idx, labs) if l == lab]
        a = ii[0]; b = min(ii[-1] + 1439, len(eq) - 1)
        e0 = 1.0 if a == 0 else eq[a - 1]
        qs[lab] = round(100 * (eq[b] / e0 - 1), 1)
    out["quarters_pct"] = qs
    return out


def main():
    t0 = time.time()
    d = load(ALL)
    print("loaded", d.n, len(ALL), "contracts in", round(time.time() - t0), "s", flush=True)
    spec = importlib.util.spec_from_file_location("shocks_fade_wickS", REPO / "docs/research-v5/finalists/shocks_fade-wickS.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    stop = m.STOP_PCT
    # The finalist re-emits the whole target row when ANY column changes, so it is always applied to the exact set of
    # contracts being traded (as v5 did for its 6): T is recomputed per universe / per contract, never sliced.
    variants = {"base": (lambda t: t, B.Costs()), "delay1": (lambda t: delayed(t, 1), B.Costs()),
                "cost48": (lambda t: t, B.Costs(fee_bp=14.0, slippage_bp=10.0))}
    universes = {"orig6": STUDIED, "A_5M": A, "B_1M": EXT, "A+B_union_no_orig": list(dict.fromkeys(A + EXT)),
                 "B_crypto_only": [s for s in EXT if s not in NON_CRYPTO]}
    out = {"universe": {k: v for k, v in universes.items()}, "portfolio": {}, "per_contract": {}}
    for uname, syms in universes.items():
        ds, ix = sub(d, syms)
        Tu = m.targets(ds)
        for vname, (fn, costs) in variants.items():
            res = B.run(ds, fn(Tu), S0, ds.n, stop_pct=stop, costs=costs)
            out["portfolio"][f"{uname}|{vname}"] = analyse(res, costs)
            r = out["portfolio"][f"{uname}|{vname}"]
            print(f"{uname:20s} {vname:7s} ev {r['events']:4d} total {r['total_pct']:+9.1f}% dd {r['max_dd_pct']:6.1f}%  [{round(time.time()-t0)}s]", flush=True)
        (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for s in ALL:
        ds, ix = sub(d, [s])
        Tu = m.targets(ds)
        for vname, (fn, costs) in variants.items():
            res = B.run(ds, fn(Tu), S0, ds.n, stop_pct=stop, costs=costs)
            r = analyse(res, costs); r.pop("pnl_by_contract", None)
            out["per_contract"].setdefault(s, {})[vname] = r
        r = out["per_contract"][s]["base"]
        print(f"{s:14s} ev {r['events']:3d} total {r['total_pct']:+8.1f}% dd {r['max_dd_pct']:6.1f}%", flush=True)
        (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("done", round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
