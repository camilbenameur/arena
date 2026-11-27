"""Prints the README tables from design_events.json, trials.jsonl and control_results.json."""
import json
from datetime import datetime, timezone
from pathlib import Path
DATA = Path("~/dev/_arena-data/axis-05").expanduser()
from lib import SYMS, stats, declustered, views

HERE = Path(__file__).resolve().parent
des = json.loads((DATA / "design_events.json").read_text())
con = json.loads((HERE / "control_results.json").read_text())
trials = [json.loads(l) for l in (HERE / "trials.jsonl").read_text().splitlines()]


def f(s, k, d=1):
    v = s.get(k)
    return "-" if v is None or v != v else (f"{v:.{d}f}" if v != float("inf") else "inf")


def row(label, s):
    return f"| {label} | {s.get('n',0)} | {f(s,'mean_bp')} | {f(s,'win',2)} | {f(s,'pf',2)} | {f(s,'sum_pct')} | {f(s,'ex_top3_sum_pct')} |"


H = "| view | n | mean net bp | win | PF | sum % | sum ex top 3 % |\n|---|---|---|---|---|---|---|"
for name, evsets in (("DESIGN", {k: v for k, v in des.items()}), ("CONTROL", {k: v["events"] for k, v in con.items()})):
    print(f"\n### {name}: delay ladder\n{H}")
    for dl in (1, 5, 15, 30, 60):
        ev = evsets[f"long_delay{dl}"]
        v = views(ev)
        tag = f"delay {dl}" + (" (diag)" if dl == 1 else "")
        print(row(tag + " raw", v["raw"]))
        print(row(tag + " de-clustered (one obs/day)", v["declust"]))
        print(row(tag + " raw, wick-overlap removed", v["raw_nowick"]))
        print(row(tag + " de-clustered, wick-overlap removed", v["declust_nowick"]))
    ev = evsets["long_delay15"]
    v = views(ev)
    print(f"\n{name} overlap share at all delays: {v['overlap_share']:.3f}; gross mean bp (delay 15) {v['gross_mean_bp']:.1f}; funding mean bp {sum(e['fund'] for e in ev)/len(ev)*1e4:.2f}")
    print("stop share", sum(e['reason']=='stop' for e in ev)/len(ev))
    print(f"\n{name} per symbol, delay 15\n{H}")
    for s in SYMS:
        print(row(s, stats([e["net"] for e in ev if e["sym"] == s])))
    print(f"\n{name} per year, delay 15\n{H}")
    for y in sorted({datetime.fromtimestamp(e["t"] / 1000, timezone.utc).year for e in ev}):
        print(row(str(y), stats([e["net"] for e in ev if datetime.fromtimestamp(e["t"] / 1000, timezone.utc).year == y])))
    first = {s: min(datetime.fromtimestamp(e["t"] / 1000, timezone.utc) for e in ev if e["sym"] == s).date().isoformat() for s in SYMS if any(e["sym"] == s for e in ev)}
    print("first event per symbol", first)
    from collections import Counter
    c = Counter(e["day"] for e in ev)
    print("max events in a single day", max(c.values()), "days with >=3 events", sum(1 for x in c.values() if x >= 3), "event days", len(c))
    big = [d for d, n in c.items() if n >= 4]
    print("share of events on days with >=4 events", sum(c[d] for d in big) / len(ev))
    print("mean net bp on days with >=4 events", 1e4 * sum(e['net'] for e in ev if e['day'] in set(big)) / max(1, sum(c[d] for d in big)),
          "| on days with <=3:", 1e4 * sum(e['net'] for e in ev if e['day'] not in set(big)) / max(1, sum(1 for e in ev if e['day'] not in set(big))))

print("\n### Design trials (all 16, delay and variants)\n| # | name | raw n | raw mean bp | raw PF | declust n | declust mean bp | declust PF | overlap |\n|---|---|---|---|---|---|---|---|---|")
for t in trials:
    if t["kind"] == "trial":
        print(f"| {t['trial']} | {t['name']} | {t['raw']['n']} | {t['raw']['mean_bp']:.1f} | {t['raw']['pf']:.2f} | {t['declust']['n']} | {t['declust']['mean_bp']:.1f} | {t['declust']['pf']:.2f} | {t['overlap_share']:.2f} |")
