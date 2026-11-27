"""Reproducible gate count. Reads events_sourced.json and perp_universe.json only.

An event counts only if ALL hold: size_pct_circ >= 3, recipient in {team, investors},
cliff, date >= 2023-01-01, source_url present, archive_snapshot_date <= date - 10 days,
and a perp existed at T-10 (Kraken openingDate, else Binance onboardDate).
No price data is read.
"""
import json
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTROL_START = date(2025, 4, 1)
OK_RECIP = {"team", "investors", "team+investors"}

def d(s): return date.fromisoformat(s)

def main():
    ev = json.loads((HERE / "events_sourced.json").read_text())
    uni = json.loads((HERE / "perp_universe.json").read_text())
    counts = {"design": 0, "control": 0}
    rejected = []
    for e in ev:
        t = d(e["date"]); t10 = t - timedelta(days=10)
        u = uni.get(e["token"].upper(), {})
        venue = None
        if u.get("kraken_open") and d(u["kraken_open"]) <= t10: venue = "kraken"
        elif u.get("binance_onboard") and d(u["binance_onboard"]) <= t10: venue = "binance"
        why = []
        if t < date(2023, 1, 1): why.append("before 2023")
        if e.get("size_pct_circ", 0) < 3: why.append("size<3%")
        if e.get("recipient") not in OK_RECIP: why.append("recipient")
        if not e.get("source_url"): why.append("no source")
        if not e.get("archive_snapshot_date") or d(e["archive_snapshot_date"]) > t10: why.append("no PIT archive")
        if not venue: why.append("no perp at T-10")
        if why: rejected.append((e["token"], e["date"], why)); continue
        counts["control" if t >= CONTROL_START else "design"] += 1
    total = sum(counts.values())
    verdict = "PASS gate" if total >= 60 and counts["control"] >= 25 else "inconclusive: too few events"
    print(json.dumps({"input_events": len(ev), "counts": counts, "total": total,
                      "rejected": len(rejected), "gate": "total>=60 and control>=25",
                      "verdict": verdict}, indent=1))

if __name__ == "__main__":
    main()
