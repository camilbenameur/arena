"""Turn the downloaded zips into two numpy files per symbol: design (< 2026-01-01) and control (>= 2026-01-01).
Streams one zip at a time. Run: python prep.py"""
import csv, io, zipfile
from pathlib import Path
import numpy as np

ROOT = Path("~/dev/_arena-data/axis-05").expanduser()
OUT = ROOT / "proc"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "LTCUSDT", "LINKUSDT"]
CUT = int(np.datetime64("2026-01-01T00:00:00", "ms").astype("int64"))


def rows(zpath):
    with zipfile.ZipFile(zpath) as z:
        for n in z.namelist():
            with z.open(n) as f:
                for r in csv.reader(io.TextIOWrapper(f)):
                    yield r


def klines(sym):
    ts, o, h, l, c = [], [], [], [], []
    files = sorted((ROOT / "klines" / sym).glob("*.zip")) + sorted((ROOT / "klines_daily" / sym).glob("*.zip"))
    for fp in files:
        for r in rows(fp):
            if not r or not r[0].isdigit():
                continue
            t = int(r[0])
            if t > 10**14:
                t //= 1000
            ts.append(t); o.append(float(r[1])); h.append(float(r[2])); l.append(float(r[3])); c.append(float(r[4]))
    ts = np.array(ts, dtype=np.int64)
    idx = np.argsort(ts, kind="stable")
    ts = ts[idx]
    arr = [np.array(x)[idx] for x in (o, h, l, c)]
    keep = np.concatenate([[True], np.diff(ts) > 0])
    return ts[keep], [a[keep] for a in arr]


def metrics(sym):
    ts, oi = [], []
    for fp in sorted((ROOT / "metrics" / sym).glob("*.zip")):
        for r in rows(fp):
            if not r or not r[0][:1].isdigit():
                continue
            t = int(np.datetime64(r[0].replace(" ", "T"), "ms").astype("int64"))
            ts.append(t); oi.append(float(r[2]))
    ts = np.array(ts, dtype=np.int64)
    oi = np.array(oi)
    idx = np.argsort(ts, kind="stable")
    ts, oi = ts[idx], oi[idx]
    keep = np.concatenate([[True], np.diff(ts) > 0])
    return ts[keep], oi[keep]


def funding(sym):
    ts, fr = [], []
    for fp in sorted((ROOT / "funding" / sym).glob("*.zip")):
        for r in rows(fp):
            if not r or not r[0].isdigit():
                continue
            ts.append(int(r[0])); fr.append(float(r[2]))
    ts = np.array(ts, dtype=np.int64); fr = np.array(fr)
    idx = np.argsort(ts)
    return ts[idx], fr[idx]


def main():
    OUT.mkdir(exist_ok=True)
    for sym in SYMS:
        kt, (o, h, l, c) = klines(sym)
        mt, oi = metrics(sym)
        ft, fr = funding(sym)
        print(sym, "klines", np.datetime_as_string(kt[[0, -1]].astype("datetime64[ms]")), len(kt),
              "metrics", np.datetime_as_string(mt[[0, -1]].astype("datetime64[ms]")), len(mt),
              "funding", len(ft), flush=True)
        for name, sel_k, sel_m, sel_f in [("design", kt < CUT, mt < CUT, ft < CUT), ("control", kt >= CUT, mt >= CUT, ft >= CUT)]:
            np.savez_compressed(OUT / f"{sym}_{name}.npz", kt=kt[sel_k], o=o[sel_k], h=h[sel_k], l=l[sel_k], c=c[sel_k],
                                mt=mt[sel_m], oi=oi[sel_m], ft=ft[sel_f], fr=fr[sel_f])


if __name__ == "__main__":
    main()
