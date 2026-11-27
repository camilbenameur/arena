"""Sealed control. Run ONCE, after finalists.json is frozen. Reads finalists.json (list of trial
ids), runs each on 2024-07-01 -> last bar, with both cost sets and a 2x-perp-leverage sizing
sensitivity, plus a Kraken-funding replay on the last ~12 months (Kraken keeps only one year of
funding history). Writes control_results.json; refuses to run twice."""
import json, sys
from pathlib import Path
import pandas as pd
import carry, strategies as S, xvenue

HERE = Path(__file__).resolve().parent
OUT = HERE / "control_results.json"
if OUT.exists(): sys.exit("control already run; refusing to run twice")
ids = json.loads((HERE / "finalists.json").read_text())
specs = {s["id"]: s for s in S.DESIGN_TRIALS + S.XV_TRIALS}
bn, by, kr = carry.Data(fund_venue="bn"), carry.Data(fund_venue="by"), carry.Data(fund_venue="kr")
START, END = carry.CONTROL_START, bn.idx[-1]
KSTART = max(kr.fund.dropna(how="all").index.min(), START)
res = {}
for i in ids:
    sp = specs[i]; r = {"spec": sp}
    if sp["type"] == "xv":
        cs = [c for c in sp["coins"] if c in bn.fund and c in by.fund]
        eq, info = xvenue.simulate(xvenue.spread_frame(by.fund, bn.fund, cs), START, END, sp["w"], sp["enter"], sp["exit"], sp["k"])
        r["control_base"] = carry.metrics(eq, info); r["by_half"] = carry.by_year(eq)
        ck = [c for c in cs if c in kr.fund]
        if ck:
            sp_kr = xvenue.spread_frame(kr.fund, bn.fund, ck)
            eq2, info2 = xvenue.simulate(sp_kr, KSTART, END, sp["w"], sp["enter"], sp["exit"], sp["k"])
            r["kraken_vs_binance"] = carry.metrics(eq2, info2)
    else:
        sig = S.build(sp)
        for name, kw in [("control_base", dict(cost="base")), ("control_optim", dict(cost="optim")),
                         ("control_base_margin0.5", dict(cost="base", margin=0.5))]:
            eq, info = carry.simulate(bn, START, END, sig, k=sp["k"], **kw)
            r[name] = carry.metrics(eq, info)
            if name == "control_base": r["by_year"] = carry.by_year(eq)
        sp2 = dict(sp); 
        eqk, infok = carry.simulate(kr, KSTART, END, S.build(sp), k=sp["k"], cost="base")
        r["kraken_funding_replay_base"] = carry.metrics(eqk, infok)
        eqb, infob = carry.simulate(bn, KSTART, END, S.build(sp), k=sp["k"], cost="base")
        r["binance_funding_same_window_base"] = carry.metrics(eqb, infob)
    res[str(i)] = r; print(i, json.dumps({k: v for k, v in r.items() if k != "spec"})[:600])
OUT.write_text(json.dumps(res, indent=1))
