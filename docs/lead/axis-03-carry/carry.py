"""Market-neutral carry simulator on an 8h grid (UTC 00/08/16 = Binance/Bybit settlement times).

Conventions (all causal, deliberately pessimistic):
  * interval i = (t_i, t_i+1]. Position held over interval i earns the funding settled at t_i+1.
  * The decision for interval i uses only funding settled at t_i-1 or before; it is executed at
    the open price of bar i (so there is one full 8h of latency between the last funding seen
    and the trade).
  * Cash-and-carry leg size N: spot long + perp short of N each (1x per leg, ~equity/2 per leg
    in total, idle cash earns 0). Units are fixed at entry (no rebalancing of the hedge).
  * Mark-to-market PnL includes the perp-vs-spot gap (basis) because both prices are real
    (Binance spot and Binance USD-M perp open prices); funding is paid on perp notional at the
    perp open price of the settlement bar.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

D = Path("~/dev/_arena-data/axis-03").expanduser()
RAW = D / "raw"
COINS = ["BTC","ETH","XRP","ADA","SOL","DOGE","LTC","LINK","DOT","AVAX","BCH","ATOM",
         "UNI","TRX","XLM","AAVE","ETC","FIL","NEAR","ALGO","XTZ","SAND","MANA","CRV","SNX"]
H8 = 8 * 3600 * 1000
DESIGN_END = pd.Timestamp("2024-06-30 16:00", tz="UTC")     # last bar of the design window
CONTROL_START = pd.Timestamp("2024-07-01 00:00", tz="UTC")

COSTS = {  # per side, fraction of leg notional
    "base":  dict(spot=0.0040, perp=0.0005, slip=0.0005),
    "optim": dict(spot=0.0025, perp=0.0005, slip=0.0005),
}

def _bin8(rows, col=1):
    """rows [[ts_ms, rate],...] -> series on the 8h grid (sum of rates inside each 8h bin,
    stamped at the bin's settlement time = right edge)."""
    if not rows: return pd.Series(dtype=float)
    a = np.array(rows, dtype=float)
    ts = a[:, 0].astype("int64")
    grid = ((ts + H8 // 2) // H8) * H8   # nearest settlement time (binance stamps are +1ms etc)
    s = pd.Series(a[:, col], index=pd.to_datetime(grid, unit="ms", utc=True))
    return s.groupby(level=0).sum()

def load_funding(venue, c):
    f = RAW / f"{venue}_fund_{c}.json"
    if not f.exists(): return pd.Series(dtype=float)
    rows = json.loads(f.read_text())
    if venue == "kr":
        # [iso ts, absolute, relative hourly]; use relative (fraction of price per hour)
        ts = pd.to_datetime([r[0] for r in rows], utc=True)
        s = pd.Series([r[2] for r in rows], index=ts)
        # settlement at hour h pays for hour h-1..h; bin into 8h windows ending at 00/08/16 (right-closed)
        return s.resample("8h", closed="right", label="right").sum()
    return _bin8(rows)

def load_px(kind, c):
    f = RAW / f"bn_{kind}_8h_{c}.json"
    if not f.exists(): return pd.Series(dtype=float)
    a = np.array(json.loads(f.read_text()))
    return pd.Series(a[:, 1], index=pd.to_datetime(a[:, 0].astype("int64"), unit="ms", utc=True))  # open

class Data:
    def __init__(self, coins=COINS, fund_venue="bn"):
        self.coins = []
        sp, pp, fn = {}, {}, {}
        for c in coins:
            s, p, f = load_px("spot", c), load_px("perp", c), load_funding(fund_venue, c)
            if len(s) < 500 or len(p) < 500 or len(f) < 100: continue
            sp[c], pp[c], fn[c] = s, p, f
            self.coins.append(c)
        idx = pd.DatetimeIndex(sorted(set().union(*[set(s.index) for s in sp.values()])))
        self.idx = idx
        self.spot = pd.DataFrame(sp).reindex(idx)
        self.perp = pd.DataFrame(pp).reindex(idx)
        self.fund = pd.DataFrame(fn).reindex(idx)   # funding settled at t (nan if none)

def trailing(fund, w):
    # mean funding per 8h over the last w settlements, using only data up to and incl. row t
    return fund.rolling(w, min_periods=max(2, w // 2)).mean()

def simulate(data, start, end, signal_fn, k=1, cost="base", equity0=1000.0, margin=1.0):
    """signal_fn(data) -> DataFrame (bool) 'want carry on coin c over the interval that follows t'
    computed from info up to row t. Position over interval i uses signal row i-1.
    Allocation: each wanted coin gets equity/(2*k_eff) per leg, k = max simultaneous slots
    (signal_fn must already cap the set at k). Returns (equity Series, trades df, funding earned)."""
    c = COSTS[cost]
    cap = 1.0 + margin   # cash tied per unit of leg notional: spot 1 + perp margin (1x per leg => 2)
    leg_cost = c["spot"] + c["slip"], c["perp"] + c["slip"]
    sig = signal_fn(data).shift(1).fillna(False).astype(bool)   # decision for bar i from row i-1
    sigv = sig.values
    idx = data.idx
    mask = (idx >= start) & (idx <= end)
    pos = np.where(mask)[0]
    E = equity0; invested = {}   # coin -> dict(us, up, N)
    eq, times = [], []
    ntr = 0; fund_tot = 0.0; cost_tot = 0.0
    spot, perp, fund = data.spot.values, data.perp.values, data.fund.values
    cols = list(data.coins); ci = {c_: j for j, c_ in enumerate(cols)}
    for n_, i in enumerate(pos[:-1]):
        t = idx[i]
        want = [cols[j] for j in range(len(cols)) if sigv[i, j] and not np.isnan(spot[i, j]) and not np.isnan(perp[i, j])]
        # exits
        for c_ in list(invested):
            if c_ not in want:
                p = invested.pop(c_); j = ci[c_]
                N_exit = p["us"] * spot[i, j]
                fee = (N_exit * leg_cost[0] + p["up"] * perp[i, j] * leg_cost[1])
                E -= fee; cost_tot += fee; ntr += 1
        # entries
        new = [c_ for c_ in want if c_ not in invested]
        if new:
            n_slots = max(k, len(invested) + len(new)) if k else len(want)
            free = E - sum(cap * p["N"] for p in invested.values())
            for c_ in new:
                j = ci[c_]
                N = min(E / (cap * n_slots), max(free, 0) / cap)
                if N <= 1: continue
                fee = N * (leg_cost[0] + leg_cost[1])
                E -= fee; cost_tot += fee; free -= cap * N + fee
                invested[c_] = dict(us=N / spot[i, j], up=N / perp[i, j], N=N)
                ntr += 1
        # keep each pair sized to equity/(2*slots): resize when a leg drifts outside [0.8, 1.25] of target.
        # (fixed units would let the hedge notional drift with price and overstate funding)
        slots = max(k, len(invested)) if k else max(len(invested), 1)
        for c_, p in invested.items():
            j = ci[c_]
            if np.isnan(spot[i, j]) or np.isnan(perp[i, j]): continue
            tgt = E / (cap * slots); ns, npp = p["us"] * spot[i, j], p["up"] * perp[i, j]
            if max(ns, npp) > 1.25 * tgt or min(ns, npp) < 0.8 * tgt:
                fee = abs(tgt - ns) * leg_cost[0] + abs(tgt - npp) * leg_cost[1]
                E -= fee; cost_tot += fee
                p["us"], p["up"], p["N"] = tgt / spot[i, j], tgt / perp[i, j], tgt
        # earn over interval i -> i+1
        i2 = pos[n_ + 1] if pos[n_ + 1] == i + 1 else i + 1
        for c_, p in invested.items():
            j = ci[c_]
            if np.isnan(spot[i2, j]) or np.isnan(perp[i2, j]):
                continue
            pnl = p["us"] * (spot[i2, j] - spot[i, j]) - p["up"] * (perp[i2, j] - perp[i, j])
            f = fund[i2, j]
            if not np.isnan(f):
                fe = p["up"] * perp[i2, j] * f; pnl += fe; fund_tot += fe
            E += pnl
        eq.append(E); times.append(idx[i2])
    # liquidate marker (no exit fee at the end: mark-to-market equity; fees on open positions ignored
    # -- negligible vs the horizon, and stated in the README)
    s = pd.Series(eq, index=times)
    yrs = (times[-1] - times[0]).days / 365.25 if times else 0
    return s, dict(entries_exits=ntr, per_year=ntr / max(yrs, 1e-9), funding=fund_tot, costs=cost_tot)

def metrics(eq, info=None, eq0=1000.0):
    if len(eq) < 10: return {}
    eq = pd.concat([pd.Series([eq0], index=[eq.index[0] - pd.Timedelta(hours=8)]), eq])
    yrs = (eq.index[-1] - eq.index[0]).total_seconds() / (365.25 * 86400)
    tot = eq.iloc[-1] / eq0
    cagr = tot ** (1 / yrs) - 1 if tot > 0 else -1
    d = eq.resample("1D").last().dropna()
    r = d.pct_change().dropna()
    vol = r.std() * np.sqrt(365)
    dd = (eq / eq.cummax() - 1).min()
    m = eq.resample("MS").last()
    mr = pd.concat([pd.Series([eq0], index=[eq.index[0]]), m]).pct_change().dropna()
    out = dict(total_ret=tot - 1, ann_ret=cagr, ann_vol=vol, sharpe=(r.mean() * 365) / (r.std() * np.sqrt(365)) if r.std() > 0 else 0,
               max_dd=dd, worst_month=mr.min(), pct_pos_months=(mr > 0).mean(), n_months=len(mr), years=yrs)
    if info: out.update(trades_per_year=info["per_year"], funding_eur=info["funding"], costs_eur=info["costs"])
    return {k: (round(float(v), 4) if isinstance(v, (float, np.floating)) else v) for k, v in out.items()}

def by_year(eq, eq0=1000.0):
    res = {}
    for y, g in eq.groupby(eq.index.year):
        prev = eq[eq.index < g.index[0]]
        base = prev.iloc[-1] if len(prev) else eq0
        res[int(y)] = round(float(g.iloc[-1] / base - 1), 4)
    return res
