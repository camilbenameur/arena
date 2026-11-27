"""Step 2: one year of 1-minute TRADE candles + hourly funding, window of research v5 (2025-11-17 -> 2026-11-18).
Standalone (urllib), resumable, polite. Data lives OUTSIDE git: ~/dev/_arena-data/axis-01/."""
import json, sys, time, urllib.request, urllib.parse
from pathlib import Path

OUT = Path("~/dev/_arena-data/axis-01").expanduser()
START = 1763337600                 # 2025-11-17 00:00 UTC
END = START + 366 * 86400          # 2026-11-18 00:00 UTC
SLEEP = 0.3
UA = {"User-Agent": "research-client/1.0"}

def get(path, params, tries=6):
    url = "https://futures.kraken.com" + path + ("?" + urllib.parse.urlencode(params) if params else "")
    for k in range(tries):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40))
        except Exception as e:
            wait = 2 ** k
            print("  retry", k, repr(e)[:80], "sleep", wait, flush=True)
            time.sleep(wait)
    raise RuntimeError("giving up: " + url)

def last_ts(f):
    if not f.exists() or f.stat().st_size == 0: return None
    with f.open("rb") as h:
        h.seek(max(0, f.stat().st_size - 200)); tail = h.read().decode().strip().splitlines()
    return int(tail[-1].split(",")[0])

def fetch_candles(sym):
    f = OUT / "candles" / f"{sym}.csv"; f.parent.mkdir(exist_ok=True)
    lt = last_ts(f); cursor = START if lt is None else lt + 60
    if cursor >= END - 60 and lt: return
    n = 0
    with f.open("a") as h:
        while cursor < END:
            p = get(f"/api/charts/v1/trade/{sym}/1m", {"from": cursor, "to": END - 1})
            rows = p.get("candles", [])
            rows = [c for c in rows if START <= int(c["time"]) // 1000 < END and int(c["time"]) // 1000 >= cursor]
            for c in rows:
                h.write(f'{int(c["time"])//1000},{c["open"]},{c["high"]},{c["low"]},{c["close"]},{c["volume"]}\n')
            h.flush(); n += len(rows)
            if not p.get("more_candles") or not rows:
                break
            cursor = int(rows[-1]["time"]) // 1000 + 60
            time.sleep(SLEEP)
    print(sym, "candles +", n, flush=True)

def fetch_funding(sym):
    f = OUT / "funding" / f"{sym}.json"; f.parent.mkdir(exist_ok=True)
    if f.exists(): return
    p = get("/derivatives/api/v3/historical-funding-rates", {"symbol": sym})
    f.write_text(json.dumps(p.get("rates", [])))
    time.sleep(SLEEP)

if __name__ == "__main__":
    u = json.loads((OUT / "universe.json").read_text())
    syms = u["studied"] + [r["symbol"] for r in u["selected"]] + [r["symbol"] for r in u["extended"] if r["symbol"] not in {x["symbol"] for x in u["selected"]}]
    for s in syms:
        fetch_candles(s); fetch_funding(s)
    print("done", len(syms))
