"""Axis 05: OI washout reversal. Strategy, simulator and statistics (see PREREGISTRATION.md)."""
from pathlib import Path
import numpy as np

ROOT = Path("~/dev/_arena-data/axis-05").expanduser()
PROC = ROOT / "proc"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "LTCUSDT", "LINKUSDT"]
CUT = int(np.datetime64("2026-01-01T00:00:00", "ms").astype("int64"))
DAY = 86_400_000
FEE, SLIP = 0.0005, 0.0005
COST_RT = 2 * (FEE + SLIP)

BASE = dict(q=0.05, z=1.5, W5=48, hold=360, stopm=2.0, delay=15, side=1)


def load(sym, kinds):
    """Concatenate the requested proc files. Design code only ever passes ['design']."""
    parts = [np.load(PROC / f"{sym}_{k}.npz") for k in kinds]
    cat = {key: np.concatenate([p[key] for p in parts]) for key in parts[0].files}
    kt = cat["kt"]
    g0 = (kt[0] // DAY) * DAY
    n = int((kt[-1] - g0) // 60000) + 1
    idx = ((kt - g0) // 60000).astype(int)
    arr = {}
    for name in "ohlc":
        a = np.full(n, np.nan)
        a[idx] = cat[name]
        arr[name] = a
    c = arr["c"]
    # forward fill close; fill gaps of o/h/l with the close
    ok = ~np.isnan(c)
    last = np.maximum.accumulate(np.where(ok, np.arange(n), 0))
    c = c[last]
    first = np.nonzero(ok)[0][0]
    c[:first] = c[first]  # symbols listed mid-day: back-fill the leading minutes (before any OI exists)
    arr["c"] = c
    for name in "ohl":
        a = arr[name]
        arr[name] = np.where(np.isnan(a), c, a)
    cat["oi"] = np.where(cat["oi"] > 0, cat["oi"], np.nan)  # zero OI rows are missing data
    k5 = n // 5
    oi5 = np.full(k5 + 1, np.nan)
    mi = ((cat["mt"] - g0) // 300_000).astype(int)
    sel = (mi >= 0) & (mi <= k5)
    oi5[mi[sel]] = cat["oi"][sel]
    # hourly true range
    H = n // 60
    hh = arr["h"][: H * 60].reshape(H, 60).max(1)
    hl = arr["l"][: H * 60].reshape(H, 60).min(1)
    hc = c[: H * 60].reshape(H, 60)[:, -1]
    prev = np.concatenate([[hc[0]], hc[:-1]])
    tr = np.maximum(hh - hl, np.maximum(np.abs(hh - prev), np.abs(hl - prev)))
    cs = np.concatenate([[0], np.cumsum(tr)])
    atr = np.full(H, np.nan)
    atr[13:] = (cs[14:] - cs[:-14]) / 14
    # wick triggers (1-minute closes)
    wd = np.zeros(n, dtype=bool)
    wu = np.zeros(n, dtype=bool)
    for w in (5, 15, 30):
        r = np.full(n, np.nan)
        r[w:] = np.log(c[w:] / c[:-w])
        wd |= r < -0.045
        wu |= r > 0.045
    return dict(sym=sym, g0=g0, n=n, o=arr["o"], h=arr["h"], l=arr["l"], c=c, oi5=oi5, atr=atr,
                wd=np.concatenate([[0], np.cumsum(wd)]), wu=np.concatenate([[0], np.cumsum(wu)]),
                ft=cat["ft"], fr=cat["fr"])


_thr_cache = {}


def features(d, W5):
    key = (d["sym"], d["n"], W5)
    if key in _thr_cache:
        return _thr_cache[key]
    K = d["n"] // 5
    k = np.arange(K)
    doi = np.full(K, np.nan)
    ok = k >= W5 + 1
    kk = k[ok]
    a, b = d["oi5"][kk - 1], d["oi5"][kk - 1 - W5]
    with np.errstate(all="ignore"):
        doi[ok] = a / b - 1
    r = np.full(K, np.nan)
    ok2 = 5 * k - 1 - 5 * W5 >= 0
    k2 = k[ok2]
    r[ok2] = np.log(d["c"][5 * k2 - 1] / d["c"][5 * k2 - 1 - 5 * W5])
    _thr_cache[key] = (doi, r)
    return doi, r


def daily_thresholds(doi, r, q):
    """Per UTC day: quantile of doi and std of r over the 90 days strictly before the day."""
    K = len(doi)
    days = (K + 287) // 288
    A = np.full(days, np.nan)
    S = np.full(days, np.nan)
    for dd in range(days):
        lo, hi = max(0, (dd - 90) * 288), dd * 288
        seg = doi[lo:hi]
        v = ~np.isnan(seg)
        if v.sum() < 288 * 60:  # fewer than 60 days of valid history
            continue
        A[dd] = np.quantile(seg[v], q)
        rr = r[lo:hi]
        S[dd] = np.nanstd(rr)
    return A, S


def events_for(d, p, since_ms=None):
    doi, r = features(d, p["W5"])
    K = len(doi)
    q = p["q"] if p["side"] == 1 else 1 - p["q"]
    A, S = daily_thresholds(doi, r, q)
    day = np.arange(K) // 288
    Ak, Sk = A[day], S[day]
    with np.errstate(invalid="ignore"):
        if p["side"] == 1:
            sig = (doi <= Ak) & (r < -p["z"] * Sk)
        else:
            sig = (doi >= Ak) & (r > p["z"] * Sk)
    sig &= ~np.isnan(Ak) & ~np.isnan(Sk)
    out = []
    lock_until = -1
    lock_k = p["hold"] // 5
    for k in np.nonzero(sig)[0]:
        if k < lock_until:
            continue
        lock_until = k + lock_k
        m = 5 * k
        t_ms = d["g0"] + m * 60000
        if since_ms is not None and t_ms < since_ms:
            continue
        me = m + p["delay"]
        mx = me + p["hold"]
        if mx >= d["n"]:
            continue  # trade not complete within the data: dropped (counted below)
        hr = m // 60 - 1
        atr = d["atr"][hr] if hr >= 0 else np.nan
        if np.isnan(atr):
            continue
        entry = d["o"][me]
        side = p["side"]
        exit_i, exit_px, reason = mx, d["o"][mx], "time"
        if p["stopm"]:
            if side == 1:
                stop = entry - p["stopm"] * atr
                hit = np.nonzero(d["l"][me:mx] <= stop)[0]
            else:
                stop = entry + p["stopm"] * atr
                hit = np.nonzero(d["h"][me:mx] >= stop)[0]
            if len(hit):
                j = me + hit[0]
                bo = d["o"][j]
                px = (stop if bo > stop else bo) if side == 1 else (stop if bo < stop else bo)
                exit_i, exit_px, reason = j, px, "stop"
        gross = side * (exit_px / entry - 1)
        e_ms, x_ms = d["g0"] + me * 60000, d["g0"] + exit_i * 60000
        i0, i1 = np.searchsorted(d["ft"], e_ms, side="right"), np.searchsorted(d["ft"], x_ms, side="right")
        fund = float(d["fr"][i0:i1].sum())
        net = gross - COST_RT - side * fund
        lo_m, hi_m = max(m - 240, 0), min(m + 60, d["n"] - 1)
        wk = d["wd"] if side == 1 else d["wu"]
        overlap = bool(wk[hi_m + 1] - wk[lo_m] > 0)
        out.append(dict(sym=d["sym"], t=int(t_ms), day=int(t_ms // DAY), gross=float(gross), fund=fund, net=float(net),
                        reason=reason, overlap=overlap, bars=int((exit_i - me)), doi=float(doi[k]), r=float(r[k])))
    return out


def stats(nets):
    x = np.asarray(nets, dtype=float)
    if len(x) == 0:
        return dict(n=0)
    pos, neg = x[x > 0].sum(), -x[x < 0].sum()
    s = np.sort(x)
    return dict(n=int(len(x)), mean_bp=float(x.mean() * 1e4), median_bp=float(np.median(x) * 1e4),
                win=float((x > 0).mean()), pf=float(pos / neg) if neg > 0 else float("inf"),
                sum_pct=float(x.sum() * 100), ex_top3_sum_pct=float(s[:-3].sum() * 100) if len(x) > 3 else float("nan"))


def declustered(evs):
    by = {}
    for e in evs:
        by.setdefault(e["day"], []).append(e["net"])
    return [float(np.mean(v)) for _, v in sorted(by.items())]


def views(evs):
    nw = [e for e in evs if not e["overlap"]]
    return dict(raw=stats([e["net"] for e in evs]), declust=stats(declustered(evs)),
                raw_nowick=stats([e["net"] for e in nw]), declust_nowick=stats(declustered(nw)),
                overlap_share=(sum(e["overlap"] for e in evs) / len(evs)) if evs else None,
                gross_mean_bp=float(np.mean([e["gross"] for e in evs]) * 1e4) if evs else None)


def run_all(kinds, p, since_ms=None):
    evs = []
    for s in SYMS:
        evs += events_for(_data(s, kinds), p, since_ms)
    return sorted(evs, key=lambda e: e["t"])


_dcache = {}


def _data(sym, kinds):
    key = (sym, tuple(kinds))
    if key not in _dcache:
        _dcache[key] = load(sym, kinds)
    return _dcache[key]
