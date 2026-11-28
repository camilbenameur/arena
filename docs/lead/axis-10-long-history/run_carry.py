"""Item 3: always-on BTC+ETH cash-and-carry (axis 3 trial 3), recomputed with axis 3's simulator and its "base" cost
model on Binance funding/prices, 2020-01-01 -> 2025-10-31. usage: PYTHONDONTWRITEBYTECODE=1 .venv/bin/python docs/lead/axis-10-long-history/run_carry.py"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

C.check_hashes()
sys.path.insert(0, str(C.REPO / "docs/lead/axis-03-carry"))
import carry  # noqa: E402
import strategies as S  # noqa: E402

OUT = HERE / "results"
OUT.mkdir(exist_ok=True)
START = pd.Timestamp("2020-01-01 00:00", tz="UTC")
END = pd.Timestamp("2025-10-31 16:00", tz="UTC")  # last 8h bar of the period


def main():
    out = {}
    for name, coins, k in (("BTC+ETH", ["BTC", "ETH"], 2), ("BTC", ["BTC"], 1), ("ETH", ["ETH"], 1)):
        data = carry.Data(coins=coins, fund_venue="bn")
        sig = S.sig_always(coins)
        eq, info = carry.simulate(data, START, END, sig, k=k, cost="base")
        assert eq.index[-1] <= END + pd.Timedelta(hours=8), eq.index[-1]
        met = carry.metrics(eq, info)
        yrs = {}
        for y, g in eq.groupby(eq.index.year):
            prev = eq[eq.index < g.index[0]]
            base = prev.iloc[-1] if len(prev) else 1000.0
            seg = pd.concat([pd.Series([base]), g.reset_index(drop=True)])
            yrs[int(y)] = dict(ret_pct=round(100 * float(g.iloc[-1] / base - 1), 3),
                               max_dd_pct=round(100 * float((seg / seg.cummax() - 1).min()), 3))
        out[name] = dict(metrics=met, years=yrs, first=str(eq.index[0]), last=str(eq.index[-1]))
        print(name, met, yrs, flush=True)
        if name == "BTC+ETH":
            # stamp = end of the 8h interval; shift 1 s so that the bar ending at 00:00 belongs to the day it covers
            e = eq.copy(); e.index = e.index - pd.Timedelta(seconds=1)
            d = e.resample("1D").last().dropna()
            np.savez(OUT / "carry_daily.npz", ts=((d.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).to_numpy(), eq=d.to_numpy())
    (OUT / "carry.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
