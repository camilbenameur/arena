"""Point-in-time perp universe: first date a perp existed per base asset.

Kraken Futures PF_ instruments (openingDate) and Binance USD-M (onboardDate).
No price data is read. Output: perp_universe.json (committed, small).
Caveat: Binance exchangeInfo lists only live symbols, so delisted perps are missing.
"""
import json, re, urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = Path("~/dev/_arena-data/axis-07").expanduser()
DATA.mkdir(parents=True, exist_ok=True)

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "research-client"})
    return json.load(urllib.request.urlopen(req, timeout=60))

def main():
    k = get("https://futures.kraken.com/derivatives/api/v3/instruments")["instruments"]
    b = get("https://fapi.binance.com/fapi/v1/exchangeInfo")["symbols"]
    (DATA / "kraken_instr.json").write_text(json.dumps(k))
    (DATA / "binance_ex.json").write_text(json.dumps(b))
    uni = {}
    for i in k:
        if i["symbol"].startswith("PF_") and i.get("openingDate"):
            base = i["base"].upper()
            uni.setdefault(base, {})["kraken_open"] = i["openingDate"][:10]
    for s in b:
        if s.get("contractType") != "PERPETUAL" or s.get("quoteAsset") != "USDT":
            continue
        base = re.sub(r"^1000+", "", s["baseAsset"]).upper()
        d = datetime.fromtimestamp(s["onboardDate"] / 1000, timezone.utc).strftime("%Y-%m-%d")
        cur = uni.setdefault(base, {})
        if "binance_onboard" not in cur or d < cur["binance_onboard"]:
            cur["binance_onboard"] = d
    (HERE / "perp_universe.json").write_text(json.dumps(dict(sorted(uni.items())), indent=0))
    print(len(uni), "bases;", sum("kraken_open" in v for v in uni.values()), "on Kraken;",
          sum("binance_onboard" in v for v in uni.values()), "on Binance")

if __name__ == "__main__":
    main()
