"""Axis 04 data: Kraken public trades tape (resumable, polite) + EURUSD daily OHLC.
Usage: fetch.py PAIR [since_unix]. Data in ~/dev/_arena-data/axis-04 (outside git)."""
import json, sys, time, urllib.request
from pathlib import Path
D = Path("~/dev/_arena-data/axis-04/raw").expanduser(); D.mkdir(parents=True, exist_ok=True)
def get(p):
    for i in range(8):
        try:
            j = json.load(urllib.request.urlopen("https://api.kraken.com/0/public/" + p, timeout=30))
            if not j.get("error"): return j["result"]
            time.sleep(5 * (i + 1))
        except Exception: time.sleep(5)
    raise SystemExit("api failure")
def tape(pair, since):
    f = D / f"trades_{pair}.jsonl"; cur = since * 10**9
    if f.exists():
        last = f.read_text().strip().splitlines()[-1]; cur = json.loads(last)["next"]
    n = 0
    with f.open("a") as o:
        while True:
            r = get(f"Trades?pair={pair}&since={cur}&count=1000")
            k = [x for x in r if x != "last"][0]; rows = r[k]
            nxt = int(r["last"])
            if not rows: break
            o.write(json.dumps({"t": [[float(x[0]), float(x[1]), float(x[2])] for x in rows], "next": nxt}) + "\n"); o.flush()
            n += len(rows)
            if nxt == cur or (len(rows) < 1000 and nxt/1e9 > time.time() - 5): break
            cur = nxt; time.sleep(1.1)
            if n % 50000 < 1000: print(pair, n, time.strftime("%F", time.gmtime(cur/1e9)), flush=True)
    print(pair, "done", n)
if __name__ == "__main__":
    if sys.argv[1] == "EURUSD":
        r = get("OHLC?pair=EURUSD&interval=1440"); (D / "ohlc1440_EURUSD.json").write_text(json.dumps(r["ZEURZUSD"]))
    else: tape(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1704067200)
