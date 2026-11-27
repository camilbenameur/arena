import os
"""SEALED CONTROL 2016-01-01 -> latest. Written before any control number was seen. Run ONCE, for all finalists together.
Signals are recomputed on all data (history before 2016 only provides warm-up); returns are evaluated from 2016-01-01."""
import json, os, sys
import pandas as pd
from lib import *
from strategies import *
OUT = os.path.dirname(os.path.abspath(__file__)) + "/"
if os.path.exists(OUT + "control_results.json"): sys.exit("control already run; refusing to run twice")
fin = json.load(open(OUT + "finalists.json"))
px = panel(with_btc=True)
res = {}
for tid in fin:
    w = build(tid, px).reindex(columns=px.columns, fill_value=0)
    for name, lev in (("1x", 1.0), ("2x", 2.0)):
        bt = backtest(w, px, start=CONTROL_START, lev=lev)
        m = metrics(bt.ret, turn=bt.turn, ntr=bt.ntrades); m["avg_gross"] = bt.gross.mean()
        res[f"{tid}_{name}"] = m
        if lev == 1.0:
            for c in (0.0, 0.002):   # cost sensitivity
                b2 = backtest(w, px, start=CONTROL_START, cost=c); res[f"{tid}_1x_cost{int(c*1e4)}bp"] = metrics(b2.ret)
for k, s in refs().items():
    res["REF_" + k] = metrics(s[s.index >= CONTROL_START].dropna())
# 'trade-able window' info: last date
res["_last_date"] = str(px.index[-1].date())
json.dump(res, open(OUT + "control_results.json", "w"), default=float, indent=1)
df = pd.DataFrame({k: v for k, v in res.items() if not k.startswith("_")}).T
pd.set_option("display.width", 250, "display.max_columns", 30)
print(df[["CAGR","vol","Sharpe","maxDD","worst_year","pos_years","total","turnover_per_yr","trades_per_yr"]].round(3).to_string())
print(res["_last_date"])
