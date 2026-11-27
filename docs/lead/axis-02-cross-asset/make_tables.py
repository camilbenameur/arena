import os
import json, pandas as pd
O=os.path.dirname(os.path.abspath(__file__)) + "/"
t=pd.DataFrame([json.loads(l) for l in open(O+"trials.jsonl")]).set_index("trial")
dr=json.load(open(O+"design_refs.json")); c=json.load(open(O+"control_results.json")); fin=json.load(open(O+"finalists.json"))
p=lambda x:f"{x*100:.1f}%"
def row(n,m,extra=""): return f"| {n} | {p(m['CAGR'])} | {p(m['vol'])} | {m['Sharpe']:.2f} | {p(m['maxDD'])} | {p(m['worst_year'])} | {p(m['pos_years'])} |{extra}"
H="| | CAGR | Vol | Sharpe | Max DD | Worst year | % pos. years |"
print("ALL TRIALS (design)\n| id | family | rule | CAGR | vol | Sharpe | maxDD | turnover/yr | trades/yr | DSR prob |\n|---|---|---|---|---|---|---|---|---|---|")
for i,r in t.iterrows(): print(f"| {i} | {r.family} | {r.desc} | {p(r.CAGR)} | {p(r.vol)} | {r.Sharpe:.2f} | {p(r.maxDD)} | {r.turnover_per_yr:.1f}x | {r.trades_per_yr:.0f} | {r.DSR_prob:.2f} |")
print("\nDESIGN\n"+H+"\n|---|---|---|---|---|---|---|")
for f in fin: print(row(f,t.loc[f]))
for k,v in dr.items(): print(row("REF "+k,v))
print("\nCONTROL\n"+H+" turnover/yr | trades/yr |\n|---|---|---|---|---|---|---|---|---|")
for f in fin:
  for s in ("1x","2x"):
    m=c[f"{f}_{s}"]; print(row(f"{f} {s}",m,f" {m['turnover_per_yr']:.1f}x | {m['trades_per_yr']:.0f} |"))
for k in ("BH_ACWI","BH_SPY","60_40_ACWI_IEF"): print(row("REF "+k,c["REF_"+k]," | |"))
print("\nCOST SENSITIVITY control Sharpe/CAGR (0 / 10 / 20 bp)")
for f in fin: print(f"| {f} | "+" | ".join(f"{c[k]['CAGR']*100:.1f}% / {c[k]['Sharpe']:.2f}" for k in (f+"_1x_cost0bp",f+"_1x",f+"_1x_cost20bp"))+" |")
print("\nSR threshold after selection", t.SR_threshold_after_selection.iloc[0])
