"""One year of 1-minute trade candles + funding for the 6 contracts, into a research store (not the league's)."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from arene.perp.kraken_futures import KrakenFuturesClient
from arene.perp.store import PerpDataStore
ROOT = Path(__file__).with_name("data") / "kraken_futures"
INST = ("PF_XBTUSD", "PF_ETHUSD", "PF_SOLUSD", "PF_XRPUSD", "PF_LTCUSD", "PF_LINKUSD")
END = 1763337600 + 365 * 86400  # placeholder, overwritten below
c = KrakenFuturesClient(); st = PerpDataStore(ROOT)
now = int(time.time()); start = now - 366 * 86400
for sym in INST:
    s = st.candles("trade", sym, 60)
    t = max(start, (s.last_ts() or start - 60) + 60)
    while t < now - 120:
        t1 = min(t + 10 * 86400, now)
        rows = c.candles("trade", sym, 60, t, t1)
        n = s.add(rows)
        print(sym, time.strftime("%Y-%m-%d", time.gmtime(t)), n, flush=True)
        t = t1
    st.funding(sym).add(c.funding_history(sym))
print("done")
