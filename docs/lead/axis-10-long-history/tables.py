"""Prints the markdown tables of the README from results/*.json. usage: python tables.py"""
import json
from pathlib import Path

R = Path(__file__).resolve().parent / "results"
w, t, c, p, o = (json.loads((R / f).read_text()) for f in ("wick.json", "trend.json", "carry.json", "portfolio.json", "overlap_check.json"))
Y = ["2020", "2021", "2022", "2023", "2024", "2025"]
f = lambda x: "n/a" if x is None else f"{x:+.1f}"
print("## wick, portfolio (6 contracts), continuous run")
print("| Variant | Trades | Win % | Mean net bp | Median bp | Total % | Max DD % | " + " | ".join(Y) + " |")
for v, r in w["portfolio"].items():
    print(f"| {v} | {r['trades']} | {r['win_rate_pct']} | {r['mean_net_bp']} | {r['median_net_bp']} | {r['total_pct']} | {r['max_dd_pct']} | " + " | ".join(f(r["years"][y]["ret_pct"]) for y in Y) + " |")
print("## wick fresh-start years")
for v, ys in w["fresh_year"].items():
    print(f"| {v} | " + " | ".join(f"{ys[y]['total_pct']:+.1f} ({ys[y]['trades']} tr, {ys[y]['mean_net_bp']} bp, win {ys[y]['win_rate_pct']}%, dd {ys[y]['max_dd_pct']})" for y in Y) + " |")
b = w["portfolio"]["base"]
print("concentration", {k: b.get(k) for k in ("top5_share_of_gross_profit_pct", "top_year", "top_year_share_of_net_pct", "pnl_by_year_usd_units", "trades_by_year", "stops", "shock_days", "top5_trades", "first_minute_equity_below_0.1")})
print("## per contract")
for s, x in w["per_contract"].items():
    print(f"| {s} | " + " | ".join(f"{x[v]['trades']} / {x[v]['win_rate_pct']} / {x[v]['mean_net_bp']} / {x[v]['total_pct']} / {x[v]['max_dd_pct']}" for v in ("base", "delay1", "cost48")) + " | " + " | ".join(f(x["base"]["years"][y]["ret_pct"]) for y in Y) + " |")
print("## trend")
for k, r in t.items():
    print(f"| {k} | {r['trades']} | {r['win_rate_pct']} | {r['mean_net_bp']} | {r['total_pct']} | {r['max_dd_pct']} | {r['sharpe']} | " + " | ".join(f"{r['years'][y]['ret_pct']:+.1f} / {r['years'][y]['max_dd_pct']:.0f}" for y in Y) + " |")
print("## carry")
for k, r in c.items():
    print(k, r["metrics"]["total_ret"], r["metrics"]["ann_ret"], r["metrics"]["max_dd"], {y: x["ret_pct"] for y, x in r["years"].items()})
print("## portfolio")
for k in ("P1_preregistered", "P2_posthoc_fresh_year", "P3_posthoc_ex_wick_trend_carry_50_50"):
    r = p[k]; print(k, r["total_pct"], r["max_dd_pct"], r["sharpe"], {y: x["ret_pct"] for y, x in r["years"].items()})
print(json.dumps({k: p[k] for k in ("corr_daily_continuous", "corr_monthly_continuous", "worst_month_pct", "worst_day_pct")}))
print(o)
