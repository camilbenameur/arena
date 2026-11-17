"""Offline bench for council strategies on the perp league's 1-minute data (var-perp/data/kraken_futures).

The execution model copies the paper simulator (`arene/perp/sim.py`, fill model `pessimiste-perp-v1`) so that a
result here is what the live league would book:
- a decision taken at the close of minute i is filled at the OPEN of minute i+1, buys at open * (1 + 5 bp), sells
  at open * (1 - 5 bp), plus a taker fee of 7 bp of the traded notional;
- a protective stop (optional, per position, % from the entry fill) triggers when the minute's high/low crosses it
  and fills at the worse of the stop level and that minute's open, minus the same 5 bp slippage and 7 bp fee;
- funding: every hour on the hour, a position pays (long, positive rate) or receives notional * relative rate.

Weights are signed notional / equity per instrument (2.0 = long twice the equity). Equity compounds; a target is
rebalanced only when it moves by more than `rebalance_band` of equity, so a constant target does not churn fees.

Periods: TRAIN is the first 64 days, HOLDOUT the rest. Strategies are designed on TRAIN only; HOLDOUT is read once
per finalist (see `docs/CONSEIL-V4-RECHERCHE.md`).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

INSTRUMENTS = ("PF_XBTUSD", "PF_ETHUSD", "PF_SOLUSD", "PF_XRPUSD", "PF_LTCUSD", "PF_LINKUSD")
DATA_ROOT = Path(__file__).resolve().parents[3] / "var-perp" / "data" / "kraken_futures"
TRAIN_DAYS = 64
MINUTE = 60


@dataclass(frozen=True)
class Costs:
    fee_bp: float = 7.0
    slippage_bp: float = 5.0


@dataclass
class Data:
    ts: np.ndarray  # (N,) minute open timestamps, contiguous
    open: np.ndarray  # (N, K) USD, forward-filled over missing minutes
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray  # (N, K) base-asset quantity, 0 for missing minutes
    funding: np.ndarray  # (N, K) relative hourly rate applied at that minute (0 except on the hour)
    instruments: tuple[str, ...] = INSTRUMENTS

    @property
    def n(self) -> int:
        return len(self.ts)

    def index_of(self, ts: int) -> int:
        return int(np.searchsorted(self.ts, ts))

    def split(self) -> tuple[int, int, int]:
        """(start, train_end, end) minute indices: TRAIN = [start, train_end), HOLDOUT = [train_end, end)."""
        return 0, min(self.n, TRAIN_DAYS * 1440), self.n


def load(root: Path = DATA_ROOT, kind: str = "trade") -> Data:
    """Loads the 1-minute candles of the six contracts on a common contiguous minute grid."""
    per: dict[str, dict[int, tuple[float, float, float, float, float]]] = {}
    for inst in INSTRUMENTS:
        rows: dict[int, tuple[float, float, float, float, float]] = {}
        for f in sorted((root / "candles" / kind / inst / "1m").glob("*.jsonl")):
            for line in f.read_text().splitlines():
                c = json.loads(line)
                rows[int(c["ts"])] = (
                    c["open"] / 1e6,
                    c["high"] / 1e6,
                    c["low"] / 1e6,
                    c["close"] / 1e6,
                    c.get("volume_qty", 0) / 1e8,
                )
        per[inst] = rows
    t0 = max(min(r) for r in per.values())
    t1 = min(max(r) for r in per.values())
    ts = np.arange(t0, t1 + MINUTE, MINUTE, dtype=np.int64)
    n, k = len(ts), len(INSTRUMENTS)
    arr = {name: np.full((n, k), np.nan) for name in ("open", "high", "low", "close")}
    vol = np.zeros((n, k))
    for j, inst in enumerate(INSTRUMENTS):
        rows = per[inst]
        for i, t in enumerate(ts):
            r = rows.get(int(t))
            if r is not None:
                arr["open"][i, j], arr["high"][i, j], arr["low"][i, j], arr["close"][i, j], vol[i, j] = r
        # a missing minute: flat at the previous close
        c = arr["close"][:, j]
        last = np.nan
        for i in range(n):
            if np.isnan(c[i]):
                arr["open"][i, j] = arr["high"][i, j] = arr["low"][i, j] = arr["close"][i, j] = last
            else:
                last = c[i]
    funding = np.zeros((n, k))
    for j, inst in enumerate(INSTRUMENTS):
        for f in sorted((root / "funding" / inst).glob("*.jsonl")):
            for line in f.read_text().splitlines():
                r = json.loads(line)
                t = int(r["ts"])
                if t0 <= t <= t1 and (t - t0) % MINUTE == 0:
                    funding[(t - t0) // MINUTE, j] = r["relative_funding_e12"] / 1e12
    return Data(ts, arr["open"], arr["high"], arr["low"], arr["close"], vol, funding)


@dataclass
class Trade:
    instrument: str
    entry_ts: int
    exit_ts: int
    side: int
    entry: float
    exit: float
    notional: float  # USD at entry
    reason: str


@dataclass
class Result:
    equity: np.ndarray  # (M,) equity at each minute close of the run, start = 1.0
    ts: np.ndarray
    fees: float  # in units of starting equity
    slippage: float
    funding: float
    turnover: float  # traded notional / starting equity
    trades: list[Trade] = field(default_factory=list)

    def daily_returns(self) -> np.ndarray:
        e = self.equity[:: 1440]
        e = np.append(e, self.equity[-1])
        return np.diff(e) / e[:-1]

    def summary(self) -> dict[str, float]:
        days = len(self.equity) / 1440
        total = float(self.equity[-1] - 1.0)
        d = self.daily_returns()
        peak = np.maximum.accumulate(self.equity)
        dd = float(np.min(self.equity / peak - 1.0))
        sharpe = float(np.mean(d) / np.std(d) * np.sqrt(365)) if np.std(d) > 0 else 0.0
        wins = [t for t in self.trades if (t.exit - t.entry) * t.side > 0]
        return {
            "days": round(days, 1),
            "total_pct": round(100 * total, 2),
            "per_day_pct": round(100 * ((self.equity[-1]) ** (1 / max(days, 1e-9)) - 1), 3),
            "sharpe": round(sharpe, 2),
            "max_dd_pct": round(100 * dd, 2),
            "fees_pct": round(100 * self.fees, 2),
            "slippage_pct": round(100 * self.slippage, 2),
            "funding_pct": round(100 * self.funding, 2),
            "turnover_x": round(self.turnover, 1),
            "trades": len(self.trades),
            "win_rate_pct": round(100 * len(wins) / len(self.trades), 1) if self.trades else 0.0,
            "ruined": bool(np.min(self.equity) <= 0.1),
        }


# A strategy maps (data, i) -> target weights (K,) decided at the close of minute i, or None = keep.
Strategy = Callable[[Data, int], "np.ndarray | None"]


def run(
    data: Data,
    targets: np.ndarray | Strategy,
    start: int,
    end: int,
    step_min: int = 1,
    stop_pct: float | None = None,
    rebalance_band: float = 0.05,
    costs: Costs = Costs(),
    max_gross: float = 10.0,
) -> Result:
    """Runs the strategy on minutes [start, end). `targets`: either a (N, K) matrix of weights where row i is the
    target decided at the close of minute i (NaN = keep), or a callable. Decisions are read every `step_min`
    minutes. `max_gross`: the gross leverage cap of the council policy (10x)."""
    k = data.open.shape[1]
    qty = np.zeros(k)  # signed base quantity
    entry = np.zeros(k)  # fill price of the open position
    entry_ts = np.zeros(k, dtype=np.int64)
    cash = 1.0  # equity units, USD-like (the EUR/USD conversion cancels out in returns)
    fees = slip = fund = turnover = 0.0
    trades: list[Trade] = []
    eq = np.empty(end - start)
    fee = costs.fee_bp / 1e4
    sl = costs.slippage_bp / 1e4
    pending: np.ndarray | None = None

    def close_part(j: int, dq: float, price: float, ts: int, reason: str) -> None:
        """Books the realized P&L of reducing position j by dq (opposite sign to qty[j])."""
        nonlocal cash
        cash += -dq * (price - entry[j])  # -dq has the sign of qty
        if abs(qty[j] + dq) < 1e-12:
            trades.append(
                Trade(data.instruments[j], int(entry_ts[j]), ts, int(np.sign(qty[j])), entry[j], price,
                      abs(qty[j]) * entry[j], reason)
            )

    def fill(j: int, dq: float, ref: float, ts: int, reason: str) -> None:
        nonlocal cash, fees, slip, turnover
        if dq == 0:
            return
        price = ref * (1 + sl) if dq > 0 else ref * (1 - sl)
        notional = abs(dq) * price
        cash -= notional * fee
        fees += notional * fee
        slip += abs(dq) * ref * sl
        turnover += notional
        q0 = qty[j]
        if q0 == 0 or np.sign(q0) == np.sign(dq):  # open or add: weighted entry
            new = q0 + dq
            entry[j] = (q0 * entry[j] + dq * price) / new if q0 else price
            if q0 == 0:
                entry_ts[j] = ts
            qty[j] = new
            return
        red = -q0 if abs(dq) >= abs(q0) else dq  # reduce (and maybe flip)
        close_part(j, red, price, ts, reason)
        qty[j] = q0 + red
        rest = dq - red
        if qty[j] == 0:
            entry[j] = 0.0
        if rest != 0:
            qty[j] = rest
            entry[j] = price
            entry_ts[j] = ts

    def equity_at(px: np.ndarray) -> float:
        return cash + float(np.sum(qty * (px - entry)))

    for i in range(start, end):
        ts = int(data.ts[i])
        o, h, lo = data.open[i], data.high[i], data.low[i]
        if pending is not None:  # decision of minute i-1, filled at this open
            e = equity_at(o)
            want = np.clip(pending, -max_gross, max_gross)
            g = np.sum(np.abs(want))
            if g > max_gross:
                want = want * max_gross / g
            cur = qty * o / max(e, 1e-12)
            for j in range(k):
                if abs(want[j] - cur[j]) > rebalance_band or (want[j] == 0 and qty[j] != 0):
                    fill(j, want[j] * e / o[j] - qty[j], o[j], ts, "signal")
            pending = None
        if stop_pct is not None:
            for j in range(k):
                if qty[j] > 0 and lo[j] <= entry[j] * (1 - stop_pct):
                    fill(j, -qty[j], min(entry[j] * (1 - stop_pct), o[j]), ts, "stop")
                elif qty[j] < 0 and h[j] >= entry[j] * (1 + stop_pct):
                    fill(j, -qty[j], max(entry[j] * (1 + stop_pct), o[j]), ts, "stop")
        if data.funding[i].any():
            pay = float(np.sum(qty * data.close[i] * data.funding[i]))
            cash -= pay
            fund -= pay
        e = equity_at(data.close[i])
        eq[i - start] = e
        if e <= 0:
            eq[i - start:] = 0.0
            break
        if (i - start) % step_min == 0 and i + 1 < end:
            if callable(targets):
                w = targets(data, i)
            else:
                w = targets[i]
                w = None if np.all(np.isnan(w)) else np.nan_to_num(w, nan=0.0)
            if w is not None:
                pending = np.asarray(w, dtype=float)
    return Result(eq, data.ts[start:end], fees, slip, fund, turnover, trades)


def resample_close(data: Data, minutes: int) -> np.ndarray:
    """Close of the last minute of each completed block of `minutes`, forward-filled per minute (no lookahead:
    row i holds the close of the latest block ending at or before i)."""
    out = np.full_like(data.close, np.nan)
    for i in range(minutes - 1, data.n, minutes):
        out[i] = data.close[i]
    return _ffill(out)


def _ffill(a: np.ndarray) -> np.ndarray:
    a = a.copy()
    for j in range(a.shape[1]):
        last = np.nan
        col = a[:, j]
        for i in range(len(col)):
            if np.isnan(col[i]):
                col[i] = last
            else:
                last = col[i]
    return a
