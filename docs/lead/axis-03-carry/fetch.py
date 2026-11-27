"""Download public funding + price history for the carry study. Resumable, polite.
Data goes to ~/dev/_arena-data/axis-03/ (never into git)."""
import json, time, sys
from pathlib import Path
import requests

D = Path("~/dev/_arena-data/axis-03").expanduser()
(D / "raw").mkdir(parents=True, exist_ok=True)
COINS = ["BTC","ETH","XRP","ADA","SOL","DOGE","LTC","LINK","DOT","AVAX","BCH","ATOM",
         "UNI","TRX","XLM","AAVE","ETC","FIL","NEAR","ALGO","XTZ","SAND","MANA","CRV","SNX"]
KR = {"BTC":"XBT"}
S = requests.Session()
def get(url, params=None, tries=6):
    for i in range(tries):
        try:
            r = S.get(url, params=params, timeout=30)
            if r.status_code == 200: return r.json()
            if r.status_code in (418, 429): time.sleep(30 * (i + 1))
            elif r.status_code in (400, 404): return None
            else: time.sleep(3)
        except Exception: time.sleep(3)
    return None
def out(name): return D / "raw" / name
def done(name): return out(name).exists()

def binance_funding(c):
    n = f"bn_fund_{c}.json"
    if done(n): return
    rows, st = [], 1546300800000
    while True:
        j = get("https://fapi.binance.com/fapi/v1/fundingRate", dict(symbol=f"{c}USDT", startTime=st, limit=1000))
        if not j: break
        rows += [[x["fundingTime"], float(x["fundingRate"])] for x in j]
        if len(j) < 1000: break
        st = j[-1]["fundingTime"] + 1; time.sleep(0.3)
    out(n).write_text(json.dumps(rows)); print(n, len(rows)); time.sleep(0.3)

def bybit_funding(c):
    n = f"by_fund_{c}.json"
    if done(n): return
    rows, end = [], int(time.time() * 1000)
    while True:
        j = get("https://api.bybit.com/v5/market/funding/history", dict(category="linear", symbol=f"{c}USDT", endTime=end, limit=200))
        if not j or j.get("retCode") != 0: break
        l = j["result"]["list"]
        if not l: break
        rows += [[int(x["fundingRateTimestamp"]), float(x["fundingRate"])] for x in l]
        end = min(int(x["fundingRateTimestamp"]) for x in l) - 1
        if len(l) < 200: break
        time.sleep(0.25)
    rows.sort(); out(n).write_text(json.dumps(rows)); print(n, len(rows))

def binance_klines(c, spot):
    n = f"bn_{'spot' if spot else 'perp'}_8h_{c}.json"
    if done(n): return
    base = "https://api.binance.com/api/v3/klines" if spot else "https://fapi.binance.com/fapi/v1/klines"
    rows, st = [], 1546300800000
    while True:
        j = get(base, dict(symbol=f"{c}USDT", interval="8h", startTime=st, limit=1000))
        if not j: break
        rows += [[x[0], float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in j]
        if len(j) < 1000: break
        st = j[-1][0] + 1; time.sleep(0.3)
    out(n).write_text(json.dumps(rows)); print(n, len(rows)); time.sleep(0.3)

def kraken_funding(c):
    n = f"kr_fund_{c}.json"
    if done(n): return
    j = get("https://futures.kraken.com/derivatives/api/v4/historicalfundingrates", dict(symbol=f"PF_{KR.get(c,c)}USD"))
    if not j or "rates" not in j: print("kraken fail", c); return
    out(n).write_text(json.dumps([[r["timestamp"], r["fundingRate"], r["relativeFundingRate"]] for r in j["rates"]]))
    print(n, len(j["rates"])); time.sleep(0.5)

if __name__ == "__main__":
    for c in COINS:
        kraken_funding(c); binance_funding(c); bybit_funding(c)
        binance_klines(c, True); binance_klines(c, False)
