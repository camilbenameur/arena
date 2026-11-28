"""Shared loader for axis 10: Binance 1-minute klines + funding (axis-05 download) on a common minute grid,
2020-01-01 -> 2025-10-31, as an `arena.perp.lab.backtest.Data`. Streams one monthly zip at a time; the assembled
arrays are cached outside git in ~/dev/_arena-data/axis-10/."""
import hashlib
import sys
import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
HERE = Path(__file__).resolve().parent
SRC = Path("~/dev/_arena-data/axis-05").expanduser()
CACHE = Path("~/dev/_arena-data/axis-10").expanduser()
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "LTCUSDT", "LINKUSDT"]
START = int(pd.Timestamp("2020-01-01", tz="UTC").timestamp())
END = int(pd.Timestamp("2025-11-01", tz="UTC").timestamp())  # exclusive
N = (END - START) // 60
FROZEN = {
    "docs/research-v5/finalists/shocks_fade-wickS.py": "a3a3a8fa414423f2800d47d83016589a1a67a7f5c22e483b97e9da346706405c",
    "arena/perp/lab/trend.py": "2fdf8feff9f82b5c54ca8257a064a27c197f1c902ab9aab064d0975948288065",
    "arena/perp/lab/backtest.py": "567035decd5ed989ab33387229864d592b58e54944179722d13cb5a3a190d8bb",
    "docs/lead/axis-03-carry/carry.py": "9b5fb100ec72cbfaa33f833cb1798fbc7b9dd6a3e1a44ee75b88d769efbbb222",
    "docs/lead/axis-03-carry/strategies.py": "454e20837d555e6bd021f40fb35cb4d1b5906eb7f04d6fbdfd5de5d4446eb623",
}


def check_hashes():
    for rel, h in FROZEN.items():
        got = hashlib.sha256((REPO / rel).read_bytes()).hexdigest()
        if got != h:
            raise SystemExit(f"hash mismatch {rel}: {got}")


def _read_zip(p, names=None):
    with zipfile.ZipFile(p) as z:
        raw = z.read(z.namelist()[0])
    df = pd.read_csv(io.BytesIO(raw), header=0 if not raw[:1].isdigit() else None)
    return df.iloc[:, :]


def build_symbol(sym):
    o = np.full(N, np.nan); h = o.copy(); l = o.copy(); c = o.copy()
    cols = ["t", "o", "h", "l", "c"]
    # monthly dumps are truncated for 2022-02 and 2022-04 on SOL/XRP/LTC: 5 daily files fill those days (gapfill/)
    files = sorted((SRC / "klines" / sym).glob("*.zip")) + sorted((CACHE / "gapfill").glob(f"{sym}-1m-*.zip"))
    for p in files:
        ym = p.stem.split("-1m-")[1]
        if ym > "2025-10":
            continue
        df = _read_zip(p).iloc[:, :5]
        df.columns = ["t", "o", "h", "l", "c"]
        t = df["t"].to_numpy(dtype=np.int64)
        t = np.where(t > 10**14, t // 1000, t) // 1000
        idx = (t - START) // 60
        ok = (idx >= 0) & (idx < N) & ((t - START) % 60 == 0)
        idx = idx[ok]
        for arr, col in ((o, "o"), (h, "h"), (l, "l"), (c, "c")):
            arr[idx] = df[col].to_numpy(dtype=float)[ok]
    valid = ~np.isnan(c)
    first = int(np.argmax(valid))
    last = np.maximum.accumulate(np.where(valid, np.arange(N), -1))
    fillc = np.where(last >= 0, c[np.maximum(last, 0)], np.nan)
    fillc[:first] = o[first]  # before listing: flat at the first open (no signal possible)
    for arr in (o, h, l, c):
        arr[~valid] = fillc[~valid]
    f = np.zeros(N)
    for p in sorted((SRC / "funding" / sym).glob("*.zip")):
        df = _read_zip(p).iloc[:, :3]
        df.columns = ["t", "i", "r"]
        t = df["t"].to_numpy(dtype=np.int64) // 1000
        m = np.round((t - START) / 60).astype(np.int64)
        ok = (m >= 0) & (m < N)
        f[m[ok]] += df["r"].to_numpy(dtype=float)[ok]
    return o, h, l, c, f, first, int((~valid).sum())


def load():
    from arena.perp.lab import backtest as B
    CACHE.mkdir(parents=True, exist_ok=True)
    cf = CACHE / "grid.npz"
    if not cf.exists():
        arrs = {k: [] for k in "ohlcf"}
        info = {}
        for s in SYMS:
            o, h, l, c, f, first, miss = build_symbol(s)
            for k, a in zip("ohlcf", (o, h, l, c, f)):
                arrs[k].append(a)
            info[s] = dict(first_minute_index=first, filled_minutes=miss, funding_events=int((f != 0).sum()))
            print(s, info[s], flush=True)
        np.savez(cf, **{k: np.stack(v, 1) for k, v in arrs.items()})
        import json
        (CACHE / "grid_info.json").write_text(json.dumps(info, indent=1))
    z = np.load(cf)
    ts = np.arange(START, END, 60, dtype=np.int64)
    return B.Data(ts, z["o"], z["h"], z["l"], z["c"], np.zeros_like(z["o"]), z["f"], tuple(SYMS))


# ---------------------------------------------------------------- analysis helpers
def year_of(ts):
    return pd.to_datetime(ts, unit="s", utc=True).year.to_numpy()


def per_year(res, start_label=None):
    """Calendar-year return and max drawdown from a bench Result (equity at each minute close)."""
    eq = res.equity
    yr = year_of(res.ts)
    out = {}
    prev = 1.0
    for y in sorted(set(yr)):
        ix = np.where(yr == y)[0]
        seg = eq[ix]
        base = prev
        out[int(y)] = dict(ret_pct=round(100 * (seg[-1] / base - 1), 2),
                           max_dd_pct=round(100 * float(np.min(seg / np.maximum.accumulate(np.r_[base, seg])[1:] - 1)), 2))
        prev = float(seg[-1])
    return out


def daily_equity(res):
    """Equity at the last minute of each UTC day -> (day timestamps, equity)."""
    idx = np.arange(1439, len(res.equity), 1440)
    return res.ts[idx], res.equity[idx]


def trade_table(res, costs):
    fee = costs.fee_bp / 1e4
    rows = []
    for t in res.trades:
        ret = t.side * (t.exit / t.entry - 1) - 2 * fee
        rows.append((t.instrument, t.entry_ts, ret, t.notional * ret, t.reason))
    return rows
