"""Event count for axis 6 (hack short). Uses only the hacks list, perp symbol lists and TVL (no prices).
Writes candidates.json next to the data. No price data is read here."""
import json, re, time, urllib.request
from pathlib import Path

D = Path("~/dev/_arena-data/axis-06").expanduser()
HERE = Path(__file__).resolve().parent
CONTROL_START = 1719792000  # 2024-07-01 UTC
DESIGN_START = 1609459200   # 2021-01-01

hacks = json.load(open(D / "hacks.json"))
prots = json.load(open(D / "protocols.json"))
bn_raw = set(s[:-4] for s in json.load(open(D / "binance_um_symbols.json")) if s.endswith("USDT"))
bn = set(bn_raw) | set(re.sub(r"^1000", "", s) for s in bn_raw)
kr = set(i["symbol"][3:-3] for i in json.load(open(D / "kraken_inst.json"))["instruments"] if i["symbol"].startswith("PF_"))
kr |= {"BTC"} if "XBT" in kr else set()

# Native token of a chain, for bridge / chain hacks (denominator: llama chain TVL)
CHAIN_TOKEN = {"Ethereum": "ETH", "BSC": "BNB", "Binance Smart Chain": "BNB", "Solana": "SOL", "Polygon": "MATIC",
               "Avalanche": "AVAX", "Fantom": "FTM", "Harmony": "ONE", "Terra": "LUNA", "Terra2": "LUNA", "Near": "NEAR",
               "NEAR": "NEAR", "Elrond": "EGLD", "Sui": "SUI", "Arbitrum": "ARB", "Optimism": "OP", "Cronos": "CRO",
               "Moonriver": "MOVR", "Algorand": "ALGO", "Stacks": "STX", "Hedera": "HBAR", "Aptos": "APT", "TON": "TON",
               "Starknet": "STRK", "Cardano": "ADA", "Tron": "TRX", "TRON": "TRX", "Flow": "FLOW", "Saga": "SAGA",
               "Kava": "KAVA", "Celo": "CELO", "Osmosis": "OSMO", "Stellar": "XLM", "zkSync Era": "ZK", "Base": "ETH",
               "Blast": "BLAST", "Scroll": "SCR", "Linea": "ETH", "Mode": "MODE", "Gnosis Chain": "GNO", "Bitcoin": "BTC"}
EXTRA = {  # hack name -> (token, llama slug or None)
    "Elrond": ("EGLD", None), "Mango Markets V3": ("MNGO", None), "Binance Bridge": ("BNB", None),
}

def norm(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\b(v\d|protocol|finance|network|dao|lend|lending|exchange|swap|dex|amm)\b", "", s.lower()))

idx = {}
for p in prots:
    idx.setdefault(norm(p["name"]), []).append(p)

_cache = {}
def get(url):
    if url in _cache: return _cache[url]
    for _ in range(3):
        try:
            _cache[url] = json.load(urllib.request.urlopen(url, timeout=60)); return _cache[url]
        except Exception: time.sleep(2)
    _cache[url] = None; return None

def tvl_before(series, ts):
    best = None
    for r in series:
        if r["date"] < ts: best = r["totalLiquidityUSD"]
        else: break
    return best

out = []
for x in sorted(hacks, key=lambda x: x["date"]):
    if x["date"] < DESIGN_START or (x["amount"] or 0) < 1e6: continue
    name = x["name"]; tok = None; basis = None; tvl = None
    ps = idx.get(norm(name))
    if x["bridgeHack"] or x.get("targetType") in ("Chain", "Layer 1"):
        ch = (x["chain"] or [None])[0]
        tok = CHAIN_TOKEN.get(ch)
        if tok:
            c = get("https://api.llama.fi/v2/historicalChainTvl/" + ch.replace(" ", "%20"))
            if c:
                tvl = tvl_before([{"date": r["date"], "totalLiquidityUSD": r["tvl"]} for r in c], x["date"]); basis = "chainTVL:" + ch
    if tok is None and ps:
        p = max(ps, key=lambda p: p.get("tvl") or 0)
        tok = (p.get("symbol") or "").upper()
        d = get("https://api.llama.fi/protocol/" + p["slug"])
        if d and d.get("tvl"):
            tvl = tvl_before(d["tvl"], x["date"]); basis = "protocolTVL:" + p["slug"]
    if tok is None and name in EXTRA: tok = EXTRA[name][0]
    if not tok: continue
    inb = tok in bn; ink = tok in kr
    if not (inb or ink): continue
    sev = (x["amount"] / tvl) if tvl else None
    out.append(dict(date=time.strftime("%Y-%m-%d", time.gmtime(x["date"])), name=name, amount=x["amount"], token=tok,
                    kraken=ink, binance=inb, tvl=tvl, basis=basis, severity=sev,
                    period="control" if x["date"] >= CONTROL_START else "design", bridge=x["bridgeHack"],
                    source=x.get("source", "")))
json.dump(out, open(D / "candidates.json", "w"), indent=1)
for r in out:
    print(r["period"][:1], r["date"], r["name"][:26], r["token"], "K" if r["kraken"] else "-", "B" if r["binance"] else "-",
          int(r["amount"] / 1e6), (round(r["severity"], 3) if r["severity"] else None), r["basis"])
