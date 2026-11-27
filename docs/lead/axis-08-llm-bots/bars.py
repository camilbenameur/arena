"""Data and prompt features for the LLM trading bots.

Loads the 1-minute candles and funding of the six perps into the bench's `Data` (arena.perp.lab.backtest), builds
4-hour bars and renders what a trader would see at the close of a bar. Leak controls (see README):
- the text never contains a calendar date or an absolute timestamp: bars are "t-1, t-2, ...";
- prices are never shown as levels: only returns, ratios to the 30-day mean, drawdowns and volatilities.
Nothing after the bar's last minute is used (no lookahead): every feature is a function of minutes <= bar end.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from arena.perp.lab import backtest as B  # noqa: E402

AXIS01 = Path.home() / "dev" / "_arena-data" / "axis-01"
VAR_PERP = REPO / "var-perp" / "data" / "kraken_futures"  # read only: used just for the tail after the axis-01 files
INSTRUMENTS = B.INSTRUMENTS
TICKERS = ("BTC", "ETH", "SOL", "XRP", "LTC", "LINK")
BAR_MIN = 240  # 4 hours
BARS_PER_DAY = 6
WARMUP_DAYS = 45  # history loaded before the window (features need 30 days, the trend engine needs ~15 more)

DT = dt.timezone.utc
LEAK_FLOOR = dt.datetime(2026, 7, 1, tzinfo=DT)  # models' cutoff (June 2026): no prompt feature may look back before this
LOOKBACK_BARS = 180  # 30 days of 4h bars: the longest lookback of any feature (contract_features reads c[-181:])
# design starts 30 days after LEAK_FLOOR so that the 30d lookback of the first decision starts on or after it
PERIODS = {  # [start, end) in UTC
    "design": (dt.datetime(2026, 7, 31, tzinfo=DT), dt.datetime(2026, 10, 1, tzinfo=DT)),
    "control": (dt.datetime(2026, 10, 1, tzinfo=DT), dt.datetime(2026, 11, 27, tzinfo=DT)),
}


def _ts(d: dt.datetime) -> int:
    return int(d.timestamp())


def _read_candles(inst: str, t0: int, t1: int) -> pd.DataFrame:
    df = pd.read_csv(AXIS01 / "candles" / f"{inst}.csv", header=None, names=["ts", "open", "high", "low", "close", "vol"])
    last = int(df["ts"].iloc[-1])
    parts = [df]
    if last < t1 - 60:  # tail from the live collector, same contract, same minute grid (prices stored x 1e6)
        rows = []
        d0 = dt.datetime.fromtimestamp(last, DT).date()
        d1 = dt.datetime.fromtimestamp(t1, DT).date()
        for k in range((d1 - d0).days + 1):
            f = VAR_PERP / "candles" / "trade" / inst / "1m" / f"{d0 + dt.timedelta(days=k)}.jsonl"
            if f.exists():
                for line in f.read_text().splitlines():
                    c = json.loads(line)
                    if c["ts"] > last:
                        rows.append((c["ts"], c["open"] / 1e6, c["high"] / 1e6, c["low"] / 1e6, c["close"] / 1e6,
                                     c.get("volume_qty", 0) / 1e8))
        if rows:
            parts.append(pd.DataFrame(rows, columns=df.columns))
    out = pd.concat(parts).drop_duplicates("ts").set_index("ts").sort_index()
    return out.loc[t0:t1 - 60]


def load_data(start: dt.datetime, end: dt.datetime) -> tuple[B.Data, int]:
    """Bench `Data` on the minute grid [start - WARMUP_DAYS, end). Returns (data, index of the first minute of `start`)."""
    t0 = _ts(start) - WARMUP_DAYS * 86400
    t1 = _ts(end)
    assert t0 % (BAR_MIN * 60) == 0 and t1 % (BAR_MIN * 60) == 0
    ts = np.arange(t0, t1, 60, dtype=np.int64)
    cols = {k: np.empty((len(ts), len(INSTRUMENTS))) for k in ("open", "high", "low", "close", "vol")}
    fund = np.zeros((len(ts), len(INSTRUMENTS)))
    for j, inst in enumerate(INSTRUMENTS):
        df = _read_candles(inst, t0, t1).reindex(ts)
        close = df["close"].ffill().bfill()
        for k in ("open", "high", "low"):
            df[k] = df[k].fillna(close)  # a missing minute: flat at the previous close
        df["close"] = close
        df["vol"] = df["vol"].fillna(0.0)
        for k in cols:
            cols[k][:, j] = df[k].to_numpy()
        for r in json.loads((AXIS01 / "funding" / f"{inst}.json").read_text()):
            t = int(pd.Timestamp(r["timestamp"]).timestamp())
            if t0 <= t < t1 and (t - t0) % 60 == 0:
                fund[(t - t0) // 60, j] = float(r["relativeFundingRate"])
    data = B.Data(ts, cols["open"], cols["high"], cols["low"], cols["close"], cols["vol"], fund)
    return data, WARMUP_DAYS * 1440


@dataclass
class Bars:
    o: np.ndarray  # (nb, K)
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    fund: np.ndarray  # (nb, K) relative funding paid by longs over the bar (sum of the hourly rates)
    end_idx: np.ndarray  # (nb,) minute index of the last minute of each bar
    first: int  # index of the first bar of the window

    @property
    def n(self) -> int:
        return len(self.c)


def make_bars(data: B.Data, start_idx: int) -> Bars:
    nb = data.n // BAR_MIN
    k = data.close.shape[1]
    sl = lambda a: a[: nb * BAR_MIN].reshape(nb, BAR_MIN, k)  # noqa: E731
    return Bars(
        o=sl(data.open)[:, 0], h=sl(data.high).max(1), l=sl(data.low).min(1), c=sl(data.close)[:, -1],
        fund=sl(data.funding).sum(1), end_idx=np.arange(nb) * BAR_MIN + BAR_MIN - 1, first=start_idx // BAR_MIN,
    )


def _pct(x: float) -> str:
    return f"{100 * x:+.2f}"


def contract_features(b: Bars, t: int, j: int) -> dict:
    """Everything the model sees about contract j at the close of bar t (indices <= t only)."""
    c, h = b.c[: t + 1, j], b.h[: t + 1, j]
    px = c[-1]
    ret = lambda n: px / c[-1 - n] - 1  # noqa: E731
    lr = np.diff(np.log(c[-181:]))
    rv = lambda n: float(np.std(lr[-n:]) * np.sqrt(BARS_PER_DAY))  # noqa: E731  daily vol from 4h log returns
    fd = b.fund[: t + 1, j]
    bar_ret = c[-12:] / np.concatenate([[b.o[t - 11, j]], c[-12:-1]]) - 1
    rng = (b.h[t - 11 : t + 1, j] - b.l[t - 11 : t + 1, j]) / c[-12:]
    day_ends = c[::-1][::BARS_PER_DAY][:11][::-1]  # closes of the last 10 whole 24h blocks ending at t
    return {
        "vs_mean30": px / np.mean(c[-180:]) - 1,
        "ret": {"4h": ret(1), "1d": ret(6), "3d": ret(18), "7d": ret(42), "30d": ret(180)},
        "vol": {"7d": rv(42), "30d": rv(180)},
        "dd": {"7d": px / h[-42:].max() - 1, "30d": px / h[-180:].max() - 1},
        "fund_bp_day": {"24h": 1e4 * fd[-6:].sum(), "7d_avg": 1e4 * fd[-42:].sum() / 7},
        "bars": list(zip(bar_ret, rng)),
        "days": list(day_ends[1:] / day_ends[:-1] - 1),
    }


def render_market(b: Bars, t: int) -> str:
    lines = []
    for j, tk in enumerate(TICKERS):
        f = contract_features(b, t, j)
        r, v, d, fu = f["ret"], f["vol"], f["dd"], f["fund_bp_day"]
        lines.append(
            f"{tk}: vs 30d mean {_pct(f['vs_mean30'])}% | return % 4h {_pct(r['4h'])} 1d {_pct(r['1d'])} 3d {_pct(r['3d'])} "
            f"7d {_pct(r['7d'])} 30d {_pct(r['30d'])} | daily vol % 7d {100 * v['7d']:.2f} 30d {100 * v['30d']:.2f} | "
            f"drawdown from high % 7d {_pct(d['7d'])} 30d {_pct(d['30d'])} | funding bp/day paid by longs 24h {fu['24h']:+.1f} "
            f"7d-avg {fu['7d_avg']:+.1f}\n"
            f"  last 12 bars, oldest to newest (return %, range %): "
            + " ".join(f"({100 * a:+.1f},{100 * g:.1f})" for a, g in f["bars"])
            + "\n  last 10 days, oldest to newest (return %): " + " ".join(f"{100 * x:+.1f}" for x in f["days"])
        )
    return "\n".join(lines)


def render_state(weights: np.ndarray, equity: float, peak: float, cost_paid: float) -> str:
    w = " ".join(f"{tk} {x:+.2f}" for tk, x in zip(TICKERS, weights))
    return (
        f"Your current target weights (x equity/6): {w}\n"
        f"Your equity index: {100 * equity:.1f} (start 100), drawdown from your peak {_pct(equity / peak - 1)}%, "
        f"costs paid so far {100 * cost_paid:.2f} points of the starting equity (approximate track record)."
    )


def user_message(b: Bars, t: int, state: str | None) -> str:
    head = "Market at the close of the latest 4-hour bar (t-0). Nothing after it is known."
    body = render_market(b, t)
    tail = state if state is not None else "You are not told your current positions: state the weights you want to hold from now."
    return f"{head}\n\n{body}\n\n{tail}\n\nReturn the target weights for the next 4 hours."


def check_leak_floor(data: B.Data, b: Bars) -> int:
    """Asserts that the oldest candle read by the first decision's features (30d lookback) is on or after LEAK_FLOOR.
    Returns the timestamp of that candle."""
    oldest_close_idx = int(b.end_idx[b.first - LOOKBACK_BARS])  # close of bar t-180, read by c[-181:] at t = first
    ts = int(data.ts[oldest_close_idx - BAR_MIN + 1])  # first minute of that bar is the earliest minute it summarises
    if ts < _ts(LEAK_FLOOR):
        raise SystemExit(f"leak control failed: first decision looks back to {ts}, before {LEAK_FLOOR}")
    return ts
