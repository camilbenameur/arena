import json
from pathlib import Path
j = json.loads((Path(__file__).resolve().parent / "results.json").read_text())
P, C = j["portfolio"], j["per_contract"]
print("## portfolio")
for u in ["orig6", "A_5M", "B_1M", "B_crypto_only"]:
    for v in ["base", "delay1", "cost48"]:
        r = P[f"{u}|{v}"]
        print(f"| {u} | {v} | {r['events']} | {r.get('shock_days')} | {r.get('win_rate_pct')} | {r.get('mean_net_ret_bp')} | {r.get('median_net_ret_bp')} | {r['total_pct']} | {r['max_dd_pct']} | {r.get('top5_pnl_share_of_gross_profit_pct')} | {r.get('top_contract')} {r.get('top_contract_pnl_share_pct')} | {r.get('max_simultaneous_positions')} |")
print("## quarters")
for u in ["orig6", "A_5M", "B_1M"]:
    for v in ["base", "delay1", "cost48"]:
        print(u, v, P[f"{u}|{v}"]["quarters_pct"])
print("## per contract")
for s, d in C.items():
    b = d["base"]
    print(f"| {s} | {b['events']} | {b.get('win_rate_pct')} | {b.get('mean_net_ret_bp')} | {b['total_pct']} | {b['max_dd_pct']} | {d['delay1']['total_pct']} | {d['cost48']['total_pct']} |")
import numpy as np
for name in ["base","delay1","cost48"]:
    t=[d[name]['total_pct'] for s,d in C.items()]
    print(name,"contracts positive",sum(x>0 for x in t),"/",len(t))
for u in ["A_5M","B_1M"]:
    print(u, P[f"{u}|base"]["pnl_by_contract"])
