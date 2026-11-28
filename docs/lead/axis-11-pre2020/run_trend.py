"""Axis 11: the FROZEN trend engine on Binance spot 2017-08 -> 2019-12 (see PREREGISTRATION.md).
usage: PYTHONDONTWRITEBYTECODE=1 .venv/bin/python docs/lead/axis-11-pre2020/run_trend.py"""
import dataclasses
import hashlib
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO))
from arena.perp.lab import backtest as B  # noqa: E402
from arena.perp.lab import trend as T  # noqa: E402

FROZEN = {"arena/perp/lab/trend.py": "2fdf8feff9f82b5c54ca8257a064a27c197f1c902ab9aab064d0975948288065",
          "arena/perp/lab/backtest.py": "567035decd5ed989ab33387229864d592b58e54944179722d13cb5a3a190d8bb"}
for rel, h in FROZEN.items():
    if hashlib.sha256((REPO / rel).read_bytes()).hexdigest() != h:
        raise SystemExit(f"hash mismatch {rel}")

SRC = Path("~/dev/_arena-data/axis-11").expanduser()
OUT = HERE / "results"
OUT.mkdir(exist_ok=True)
SYMS = ["BTCUSDT", "ETHUSDT", "LTCUSDT", "XRPUSDT", "LINKUSDT"]
ts_ = lambda s: int(pd.Timestamp(s, tz="UTC").timestamp())  # noqa: E731
START, END = ts_("2017-08-01"), ts_("2020-01-01")
N = (END - START) // 60
S0 = (ts_("2017-09-16") - START) // 60
STOP = 0.05


def build(sym):
    o = np.full(N, np.nan); h = o.copy(); l = o.copy(); c = o.copy()
    for p in sorted((SRC / "klines" / sym).glob("*.zip")):
        with zipfile.ZipFile(p) as z:
            raw = z.read(z.namelist()[0])
        df = pd.read_csv(io.BytesIO(raw), header=None).iloc[:, :5]
        df.columns = ["t", "o", "h", "l", "c"]
        t = df["t"].to_numpy(dtype=np.int64)
        t = np.where(t > 10**14, t // 1000, t) // 1000
        idx = (t - START) // 60
        # timestamps floored to the minute: some Binance months (Dec 2017, Feb 2018) are stamped a few seconds past the
        # minute; the first version kept only exact minutes and silently dropped about 14 days of BTC/ETH (found by the
        # adversarial check). If two rows fall in the same minute, the last one wins.
        ok = (idx >= 0) & (idx < N)
        for arr, col in ((o, "o"), (h, "h"), (l, "l"), (c, "c")):
            arr[idx[ok]] = df[col].to_numpy(dtype=float)[ok]
    valid = ~np.isnan(c)
    first = int(np.argmax(valid))
    last = np.maximum.accumulate(np.where(valid, np.arange(N), -1))
    fillc = c[np.maximum(last, 0)]
    fillc[:first] = o[first]
    for arr in (o, h, l, c):
        arr[~valid] = fillc[~valid]
    return o, h, l, c, first, int((~valid).sum()) - first


def load():
    cols = [build(s) for s in SYMS]
    info = {s: dict(first_candle=str(pd.Timestamp(START + 60 * x[4], unit="s")), missing_minutes_after_listing=x[5]) for s, x in zip(SYMS, cols)}
    st = lambda i: np.stack([x[i] for x in cols], 1)  # noqa: E731
    ts = np.arange(START, END, 60, dtype=np.int64)
    d = B.Data(ts, st(0), st(1), st(2), st(3), np.zeros((N, len(SYMS))), np.zeros((N, len(SYMS))), tuple(SYMS))
    return d, info, [x[4] for x in cols]


def year_of(ts):
    return pd.to_datetime(ts, unit="s", utc=True).year.to_numpy()


def stats(eq_daily):
    """eq_daily: daily equity (start=1 prepended not needed)."""
    r = np.diff(np.r_[1.0, eq_daily]) / np.r_[1.0, eq_daily][:-1]
    peak = np.maximum.accumulate(np.r_[1.0, eq_daily])[1:]
    return dict(total_pct=round(100 * (eq_daily[-1] - 1), 2), max_dd_pct=round(100 * float(np.min(eq_daily / peak - 1)), 2),
                sharpe=round(float(r.mean() / r.std() * np.sqrt(365)), 2) if r.std() > 0 else 0.0)


def by_year(dts, eq):
    yr = year_of(dts)
    out, prev = {}, 1.0
    for y in sorted(set(yr)):
        seg = eq[yr == y]
        pk = np.maximum.accumulate(np.r_[prev, seg])[1:]
        out[int(y)] = dict(ret_pct=round(100 * (seg[-1] / prev - 1), 2), max_dd_pct=round(100 * float(np.min(seg / pk - 1)), 2))
        prev = float(seg[-1])
    return out


def main():
    t0 = time.time()
    d, info, first = load()
    print(info, flush=True)
    out = dict(data=info, trading_start="2017-09-16")
    days = np.arange(S0 + 1439, N, 1440)  # last minute of each UTC day from the start
    dts = d.ts[days]
    # benchmark: equal weight over coins listed that day, daily rebalanced, no costs
    px = d.close[S0 - 1 + 0:: 1440][: len(days) + 1] if False else None
    cd = d.close[np.r_[S0 - 1, days]]  # close at the end of the day before start, then each day
    listed = np.array([[(S0 - 1 + 1440 * k) >= f + 1440 for f in first] for k in range(len(days) + 1)])  # listed >= 1 day before
    rets = cd[1:] / cd[:-1] - 1
    lm = listed[:-1]
    ew = np.where(lm.sum(1) > 0, (np.where(lm, rets, 0).sum(1)) / np.maximum(lm.sum(1), 1), 0)
    beq = np.cumprod(1 + ew)
    out["bench_ew"] = dict(**stats(beq), years=by_year(dts, beq))
    bt = np.cumprod(1 + rets[:, 0])
    out["bench_btc"] = dict(**stats(bt), years=by_year(dts, bt))
    print("EW", out["bench_ew"], "\nBTC", out["bench_btc"], flush=True)
    for scale in (1.0, 2.0):
        tg = T.targets(d, dataclasses.replace(T.FROZEN, scale=scale))
        res = B.run(d, tg, S0, N, stop_pct=STOP)
        s = res.summary()
        eqd = res.equity[1439::1440]
        tr = [(t.side * (t.exit / t.entry - 1) - 2 * 7e-4) for t in res.trades]
        r = dict(trades=len(tr), win_rate_pct=round(100 * float(np.mean(np.array(tr) > 0)), 1) if tr else 0,
                 mean_net_bp=round(1e4 * float(np.mean(tr)), 1) if tr else 0, turnover_x=s["turnover_x"], fees_pct=s["fees_pct"],
                 ruined=s["ruined"], **stats(eqd), years=by_year(res.ts[1439::1440], eqd),
                 stop_exits=sum(t.reason == "stop" for t in res.trades),
                 by_coin={x: sum(1 for t in res.trades if t.instrument == x) for x in SYMS})
        # long/short split of mean net bp
        for nm, sd in (("long", 1), ("short", -1)):
            q = [(t.side * (t.exit / t.entry - 1) - 2 * 7e-4) for t in res.trades if t.side == sd]
            r[f"{nm}_trades"], r[f"{nm}_mean_bp"] = len(q), round(1e4 * float(np.mean(q)), 1) if q else 0
        out[f"{scale:g}x"] = r
        np.savez(OUT / f"trend_{scale:g}x_daily.npz", ts=res.ts[1439::1440], eq=eqd)
        print(f"{scale:g}x", {k: v for k, v in r.items()}, round(time.time() - t0), "s", flush=True)
        (OUT / "trend.json").write_text(json.dumps(out, indent=1))
    np.savez(OUT / "bench_daily.npz", ts=dts, ew=beq, btc=bt)
    print("done")


if __name__ == "__main__":
    main()
