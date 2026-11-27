"""Design phase: every trial is evaluated on data truncated at 2015-12-31 only. Logs all trials, picks finalists by a pre-stated rule."""
import os
import json, sys, numpy as np
from lib import *
from strategies import *
OUT = os.path.dirname(os.path.abspath(__file__)) + "/"
EVAL_START = "2008-04-01"
def px_for(tid, end):
    p = panel(with_btc=True); p = p[p.index <= end]
    return p
rows = []
rets = {}
for tid in TRIALS:
    px = px_for(tid, DESIGN_END)
    w = build(tid, px)
    etfcols = px.columns
    bt = backtest(w.reindex(columns=etfcols, fill_value=0), px, start=EVAL_START, end=DESIGN_END)
    m = metrics(bt.ret, turn=bt.turn, ntr=bt.ntrades); m["avg_gross"] = bt.gross.mean()
    rets[tid] = bt.ret
    rows.append(dict(trial=tid, family=TRIALS[tid][0], desc=TRIALS[tid][1], **m))
n = len(rows); srs = [r["Sharpe"] for r in rows]
for r in rows:
    d, sr0 = deflated_sharpe(r["Sharpe"], int(r["years"]*252), r["skew"], r["kurt"], n, srs)
    r["DSR_prob"] = d; r["SR_threshold_after_selection"] = sr0; r["n_trials"] = n
with open(OUT + "trials.jsonl", "w") as f:
    for r in rows: f.write(json.dumps(r, default=float) + "\n")
# references on identical design window
refl = {}
for k, s in refs().items():
    s = s[(s.index >= EVAL_START) & (s.index <= DESIGN_END)]
    refl[k] = metrics(s)
json.dump(refl, open(OUT + "design_refs.json", "w"), default=float, indent=1)
# finalist rule (fixed before looking at design numbers): best design Sharpe within each family group, at most 5.
df = pd.DataFrame(rows); df["grp"] = df.family.map(FAMILY_GROUP)
fin = df.sort_values("Sharpe", ascending=False).groupby("grp").head(1).sort_values("Sharpe", ascending=False)
json.dump(list(fin.trial), open(OUT + "finalists.json", "w"))
pd.set_option("display.width", 250, "display.max_columns", 30)
print(df[["trial","family","CAGR","vol","Sharpe","maxDD","worst_year","pos_years","turnover_per_yr","trades_per_yr","avg_gross","DSR_prob"]].round(3).to_string())
print(json.dumps({k:{a:round(b,3) for a,b in v.items() if a in("CAGR","vol","Sharpe","maxDD","worst_year")} for k,v in refl.items()}, indent=1))
print("finalists", list(fin.trial))
