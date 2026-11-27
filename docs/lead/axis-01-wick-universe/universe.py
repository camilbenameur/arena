"""Step 1: pick the universe (public Kraken Futures API, no key). Writes universe.json outside git."""
import json, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("~/dev/_arena-data/axis-01").expanduser()
STUDIED = ["PF_XBTUSD", "PF_ETHUSD", "PF_SOLUSD", "PF_XRPUSD", "PF_LTCUSD", "PF_LINKUSD"]
MIN_VOL_USD = 5e6
MIN_AGE_DAYS = 180
MAX_N = 30
UA = {"User-Agent": "research-client/1.0"}

def get(path):
    r = urllib.request.Request("https://futures.kraken.com" + path, headers=UA)
    return json.load(urllib.request.urlopen(r, timeout=30))

ins = {i["symbol"]: i for i in get("/derivatives/api/v3/instruments")["instruments"]}
tick = {t["symbol"]: t for t in get("/derivatives/api/v3/tickers")["tickers"]}
now = datetime.now(timezone.utc)
def pick(min_vol):
    out = []
    for sym, i in ins.items():
        t = tick.get(sym)
        if not sym.startswith("PF_") or sym in STUDIED or not t or i.get("suspended") or t.get("suspended") or t.get("tag") != "perpetual": continue
        vol = float(t.get("volumeQuote") or 0)
        age = (now - datetime.fromisoformat(i["openingDate"].replace("Z", "+00:00"))).days
        if vol >= min_vol and age >= MIN_AGE_DAYS: out.append({"symbol": sym, "vol24h_usd": vol, "age_days": age, "opening": i["openingDate"]})
    out.sort(key=lambda r: -r["vol24h_usd"])
    return out

rows, rej = [], {"studied": 0, "not_perp_pf": 0, "low_volume": 0, "too_recent": 0, "suspended": 0}
for sym, i in ins.items():
    if not sym.startswith("PF_"): rej["not_perp_pf"] += 1; continue
    if sym in STUDIED: rej["studied"] += 1; continue
    t = tick.get(sym)
    if not t or i.get("suspended") or t.get("suspended") or t.get("tag") != "perpetual": rej["suspended"] += 1; continue
    vol = float(t.get("volumeQuote") or 0)
    age = (now - datetime.fromisoformat(i["openingDate"].replace("Z", "+00:00"))).days
    if vol < MIN_VOL_USD: rej["low_volume"] += 1; continue
    if age < MIN_AGE_DAYS: rej["too_recent"] += 1; continue
    rows.append({"symbol": sym, "vol24h_usd": vol, "age_days": age, "opening": i["openingDate"]})
rows.sort(key=lambda r: -r["vol24h_usd"])
print("eligible:", len(rows), "rejections:", rej)
sel = rows[:MAX_N]
for r in sel: print(f'{r["symbol"]:16s} {r["vol24h_usd"]/1e6:9.1f}M  age {r["age_days"]}d')
# Secondary universe B (declared BEFORE any backtest): the 5 M filter keeps only 5 contracts, and two of the six
# studied contracts (LINK 3.4 M, LTC 0.9 M) would themselves fail it, so B relaxes ONLY the volume floor to 1 M.
ext = pick(1e6)[:MAX_N]
print("B (>= 1M, <=30):", len(ext), [r["symbol"] for r in ext])
(OUT / "universe.json").write_text(json.dumps({"extended": ext, "snapshot": now.isoformat(), "eligible_count": len(rows), "rejections": rej,
    "selected": sel, "studied": STUDIED, "all_eligible": rows}, indent=1))
