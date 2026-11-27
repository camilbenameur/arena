"""Shared pieces of axis 9 (an LLM as a researcher): design-only data export, leak guard, causality check, gates.

Imports the axis-8 modules (bars.py, report.py, budget.py) read-only. Nothing here calls the network.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import io
import json
import re
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
AX8 = HERE.parent / "axis-08-llm-bots"
sys.path.insert(0, str(AX8))

import bars as BR  # noqa: E402  (axis 8)
import budget as BUD  # noqa: E402  (axis 8)
import report as REP  # noqa: E402  (axis 8)

REPO = BR.REPO
B = BR.B
TICKERS = BR.TICKERS
DATA_DIR = Path.home() / "dev" / "_arena-data" / "axis-09"
DT = dt.timezone.utc
DESIGN_START = dt.datetime(2026, 7, 1, tzinfo=DT)
DESIGN_END = dt.datetime(2026, 10, 1, tzinfo=DT)  # exclusive: nothing on or after this instant may reach the model
CONTROL = BR.PERIODS["control"]
BAR_MIN = BR.BAR_MIN
COLUMNS = ["ts", "ticker", "open", "high", "low", "close", "volume", "funding"]
CSV_NAME = "bars_4h_design.csv"
FROZEN_RE = re.compile(r"^STATUS: FROZEN$", re.M)
DATE_RE = re.compile(r"(?<!\d)(20\d\d)-(\d\d)-(\d\d)")
_LIMIT = (DESIGN_END.year, DESIGN_END.month, DESIGN_END.day)


# ------------------------------------------------------------------------------------------------ data export


def make_frame(data: "B.Data", ts_lo: dt.datetime, ts_hi: dt.datetime) -> pd.DataFrame:
    """Long frame of 4-hour bars whose OPEN time is in [ts_lo, ts_hi). One row per (bar, ticker), sorted by ts then ticker.
    `ts` is the bar open time (UTC, naive); the bar is complete and known only at ts + 4 hours. volume is the base-asset
    quantity traded in the bar; funding is the sum of the hourly relative rates paid by longs inside the bar."""
    k = data.close.shape[1]
    nb = data.n // BAR_MIN
    sl = lambda a: a[: nb * BAR_MIN].reshape(nb, BAR_MIN, k)  # noqa: E731
    o, h, l_, c = sl(data.open)[:, 0], sl(data.high).max(1), sl(data.low).min(1), sl(data.close)[:, -1]
    v, f = sl(data.volume).sum(1), sl(data.funding).sum(1)
    ts = pd.to_datetime(data.ts[: nb * BAR_MIN : BAR_MIN], unit="s")
    keep = (ts >= pd.Timestamp(ts_lo.replace(tzinfo=None))) & (ts < pd.Timestamp(ts_hi.replace(tzinfo=None)))
    rows = []
    for i in np.where(keep)[0]:
        for j, tk in enumerate(TICKERS):
            rows.append((ts[i], tk, o[i, j], h[i, j], l_[i, j], c[i, j], v[i, j], f[i, j]))
    return pd.DataFrame(rows, columns=COLUMNS)


def frame_to_csv(df: pd.DataFrame) -> str:
    return df.to_csv(index=False, date_format="%Y-%m-%d %H:%M:%S")


def csv_to_frame(text: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(text), parse_dates=["ts"])


def assert_design_only(text: str, what: str = "text") -> None:
    """Refuses any calendar date on or after 2026-10-01 in a string that is about to leave the machine (CSV, prompt, helper
    code). Run on every uploaded file and on the whole prompt."""
    for m in DATE_RE.finditer(text):
        if (int(m.group(1)), int(m.group(2)), int(m.group(3))) >= _LIMIT:
            raise ValueError(f"leak guard: {what} contains the date {m.group(0)}, on or after the design end")


def design_csv() -> tuple[str, pd.DataFrame]:
    data, _ = BR.load_data(DESIGN_START, DESIGN_END)
    df = make_frame(data, DESIGN_START, DESIGN_END)
    text = frame_to_csv(df)
    assert_design_only(text, CSV_NAME)
    back = csv_to_frame(text)
    if not (back["ts"].min() >= pd.Timestamp("2026-07-01") and back["ts"].max() < pd.Timestamp("2026-10-01")):
        raise ValueError("leak guard: design CSV outside the design window")
    return text, back


# ------------------------------------------------------------------------------------------------ rule loading and checks


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_rule(path: Path):
    ns: dict = {"__name__": "frozen_rule"}
    exec(compile(path.read_text(), str(path), "exec"), ns)  # noqa: S102  (the file is the object under test)
    fn = ns.get("targets")
    if not callable(fn):
        raise SystemExit(f"{path.name} defines no callable targets(df)")
    return fn


def run_rule(fn, df: pd.DataFrame) -> pd.DataFrame:
    """Calls targets(df) on a copy and validates the output: index = the unique bar times, columns = TICKERS, finite,
    in [-2, 2]."""
    out = fn(df.copy())
    if not isinstance(out, pd.DataFrame):
        raise ValueError("targets(df) must return a DataFrame")
    ts = pd.Index(sorted(df["ts"].unique()))
    out = out.reindex(columns=list(TICKERS))
    if not out.index.equals(ts):
        out = out.reindex(ts)
    a = out.to_numpy(dtype=float)
    if not np.isfinite(a).all():
        raise ValueError("targets(df): NaN or infinite weights (use 0 during warm-up)")
    if np.abs(a).max() > 2.0 + 1e-9:
        raise ValueError(f"targets(df): weight {np.abs(a).max():.3f} outside [-2, 2]")
    return out


def causality_gap(fn, df: pd.DataFrame, cuts: int = 24, seed: int = 0) -> float:
    """Max absolute difference between the targets computed on the full data and the targets recomputed on data truncated
    after bar t, over every row of the truncated output, for `cuts` values of t (the first rows, the last row and random
    ones in between). A causal rule gives exactly 0."""
    full = run_rule(fn, df)
    times = list(full.index)
    rng = np.random.default_rng(seed)
    pick = sorted({0, 1, 5, len(times) - 2, *rng.integers(2, len(times) - 2, size=cuts).tolist()})
    gap = 0.0
    for i in pick:
        part = run_rule(fn, df[df["ts"] <= times[i]])
        gap = max(gap, float(np.abs(part.to_numpy() - full.iloc[: i + 1].to_numpy()).max()))
    return gap


# ------------------------------------------------------------------------------------------------ evaluation


def evaluate(fn, period: str, n_random: int = 20) -> dict:
    """Maps the 4-hour targets onto the minute bench of axis 8 (bars decided at the close, filled at the next minute open,
    5 bp slippage + 7 bp fee per side, hourly funding) and compares with trend 2x, basket 1x and random same-turnover.
    The rule sees the CSV-format frame of every bar from 2026-07-01 up to the end of the evaluated window."""
    s, e = (DESIGN_START, DESIGN_END) if period == "design" else CONTROL
    data, i0 = BR.load_data(s, e)
    b = BR.make_bars(data, i0)
    rule_data = data if period == "design" else BR.load_data(DESIGN_START, e)[0]
    df = csv_to_frame(frame_to_csv(make_frame(rule_data, DESIGN_START, e)))
    tg = run_rule(fn, df)
    want = [pd.Timestamp(int(data.ts[k * BAR_MIN]), unit="s") for k in range(b.first, b.n)]
    w = tg.reindex(want)
    if w.isna().any().any():
        raise ValueError("targets(df) misses some bars of the evaluated window")
    return REP.evaluate_bot(data, b, i0, w.to_numpy(dtype=float), n_random=n_random)


def reference_design() -> dict:
    """Trend engine (1x, 2x) and 1x basket on the design window (07-01 to 09-30), through the same bench."""
    data, i0 = BR.load_data(DESIGN_START, DESIGN_END)
    from dataclasses import replace as rep

    from arena.perp.lab import trend as T

    out = {}
    for sc in (1.0, 2.0):
        out[f"trend_{int(sc)}x"], _ = REP.run_one(data, T.targets(data, rep(T.FROZEN, scale=sc)), i0)
    out["basket_1x"], _ = REP.run_one(data, REP.basket(data, i0), i0)
    return out


# ------------------------------------------------------------------------------------------------ control gate and lock


def _git(repo: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=False).stdout.strip()


def control_gate(prereg: Path, rule: Path, repo: Path = REPO) -> str:
    """Refuses unless PREREGISTRATION.md is committed, unmodified, has a line-anchored STATUS: FROZEN and lists the sha256 of
    frozen_rule.py as `frozen_rule.py sha256: <hex>` on its own line. Returns the commit holding it. Does not take the lock."""
    if not prereg.exists():
        raise SystemExit(f"control refused: {prereg.name} does not exist")
    if not rule.exists():
        raise SystemExit(f"control refused: {rule.name} does not exist")
    rel = str(prereg.resolve().relative_to(repo.resolve()))
    commit = _git(repo, "log", "-n1", "--format=%H", "--", rel)
    if not commit:
        raise SystemExit(f"control refused: {prereg.name} is not committed in git")
    if _git(repo, "status", "--porcelain", "--", rel):
        raise SystemExit(f"control refused: {prereg.name} has uncommitted changes")
    text = prereg.read_text()
    if not FROZEN_RE.search(text):
        raise SystemExit(f"control refused: {prereg.name} has no line reading exactly STATUS: FROZEN")
    listed = set(re.findall(r"^frozen_rule\.py sha256: ([0-9a-f]{64})$", text, re.M))
    if sha256_file(rule) not in listed:
        raise SystemExit("control refused: the sha256 of frozen_rule.py is not listed in the committed preregistration")
    return commit


def control_ran(data_dir: Path = DATA_DIR) -> bool:
    f = data_dir / "control_run.jsonl"
    return f.exists() and bool(f.read_text().strip())


def take_control_lock(commit: str, rule_sha: str, data_dir: Path = DATA_DIR) -> None:
    """Check-and-write under one flock: the control runs once, ever. Taken before the control data is touched; a crash after
    this point still counts."""
    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / "control_run.jsonl.lock").open("a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        if control_ran(data_dir):
            raise SystemExit("control refused: the axis-9 control already ran (one rule, one control run)")
        with (data_dir / "control_run.jsonl").open("a") as f:
            f.write(json.dumps({"ts": int(time.time()), "prereg_commit": commit, "rule_sha256": rule_sha}) + "\n")
