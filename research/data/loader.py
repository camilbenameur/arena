"""Single loader of the research data: the only entry point to `var/research/data/`.

Guarantees: manifest verified (sha256 of every file); `CutoffError` if a raw row has
`known_at > CUTOFF_TS` (never a silent truncation); protocol tolerances applied.

Table format (one per symbol): index = naive UTC `DatetimeIndex` (ns) = bar open time;
float64 columns `open, high, low, close, volume, quote_volume, trades, taker_buy_base, taker_buy_quote`,
`filled` (bool, synthetic bar), `known_at` (int64, UTC seconds = open + duration).
Funding: index = `fundingTime`, columns `rate` (float64), `known_at` (int64 = fundingTime + 1 s).
Control universe: `control_1d` (always present), `control_1h` (spot 1h), `control_perp_1h` and
`control_funding` (None if the symbol has no archives: no perp, or no spot 1h). A symbol delisted
before 2026-06 simply stops (no end imposed).
Filling (within tolerance; 2018-2019 warm-up without threshold): open = high = low = close = last close,
zero volume, zero return, `filled` true. Each table starts at the symbol's first bar (no NaN before
listing: eligibility is read from the index).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from research.config import CUTOFF_TS, CutoffError, Criteria, load_criteria
from research.data.reader import BAR_COLUMNS, read_zips
from research.data.manifest import CONTROL_UNIVERSE_PATH, sha256_manifest, verify_manifest


class DataError(Exception):
    """Incomplete data or data outside tolerance."""


@dataclass(frozen=True)
class Data:
    root_path: Path
    manifest_sha256: str
    universe: tuple[str, ...]
    control: tuple[str, ...]
    spot_1d: dict[str, pd.DataFrame]
    spot_1h: dict[str, pd.DataFrame]
    perp_1h: dict[str, pd.DataFrame | None]
    funding: dict[str, pd.DataFrame | None]
    control_1d: dict[str, pd.DataFrame]
    control_1h: dict[str, pd.DataFrame | None]
    control_perp_1h: dict[str, pd.DataFrame | None]
    control_funding: dict[str, pd.DataFrame | None]
    # Erratum 3: 1h series outside tolerance are shortened (name -> first open kept, UTC s).
    cut_starts: dict[str, int] = field(default_factory=dict)


def _seconds(idx: pd.DatetimeIndex) -> np.ndarray:
    return idx.as_unit("ns").asi8 // 1_000_000_000


def verify_cutoff(known_at: np.ndarray, name: str) -> None:
    """Raise `CutoffError` if a row is known strictly after the cutoff."""
    if len(known_at) and int(known_at.max()) > CUTOFF_TS:
        n = int((known_at > CUTOFF_TS).sum())
        raise CutoffError(f"{name} : {n} row(s) with known_at > cutoff {CUTOFF_TS} "
                           f"(max {int(known_at.max())})")


def _eligible_start(absent: pd.Series, share_max: float, run_max: int) -> pd.Timestamp | None:
    """Erratum 3: first start (just after a run of missing bars) from which the series meets the 1h
    tolerances; None if there is none. `absent` is the grid of the evaluation window."""
    a = absent.to_numpy()
    n = len(a)
    starts = [0] + [i + 1 for i in range(n - 1) if a[i] and not a[i + 1]]
    for d in starts:
        x = a[d:]
        if not len(x):
            break
        runs = pd.Series(x).groupby((~pd.Series(x)).cumsum()).sum()
        if int(x.sum()) <= share_max * len(x) and int(runs.max()) <= run_max:
            return absent.index[d]
    return None


def _regularize(df: pd.DataFrame, duration_s: int, name: str, crit: Criteria, expected_end: int | None,
                 cuts: dict[str, int] | None = None) -> pd.DataFrame:
    """Check cutoff, gaps and end; fill the 1h gaps within tolerance; add `known_at`."""
    if df.empty:
        raise DataError(f"{name} : empty table")
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise DataError(f"{name} : index not strictly increasing")
    opening = _seconds(df.index)
    verify_cutoff(opening + duration_s, name)
    if expected_end is not None and int(opening[-1]) + duration_s != expected_end:
        raise DataError(f"{name} : last bar closed at {int(opening[-1]) + duration_s}, "
                           f"{expected_end} expected")
    tol = crit.data.tolerances
    grid = pd.date_range(df.index[0], df.index[-1], freq=pd.Timedelta(seconds=duration_s), unit="ns")
    df = df.assign(filled=False)
    if len(grid) > len(df):
        # The protocol tolerances apply to the evaluation window (>= 2020-01-01), after the first
        # listing; warm-up gaps are filled without threshold (and flagged by `filled`).
        absent = pd.Series(~grid.isin(df.index), index=grid)
        window = absent[absent.index >= pd.Timestamp(crit.data.evaluation_window.start)]
        n_window, longest_run = int(window.sum()), int(window.groupby((~window).cumsum()).sum().max()) if len(window) else 0
        if duration_s >= 86400 and n_window > tol.gaps_1d:
            raise DataError(f"{name} : {n_window} gap(s) in 1d in the window (tolerance {tol.gaps_1d})")
        outside = duration_s < 86400 and (n_window > tol.max_gaps_1h_share * len(window)
                                    or longest_run > tol.max_consecutive_gaps_1h)
        if outside and cuts is not None:
            start = _eligible_start(window, tol.max_gaps_1h_share, tol.max_consecutive_gaps_1h)
            if start is not None:
                cuts[name] = int(_seconds(pd.DatetimeIndex([start]))[0])
                return _regularize(df.drop(columns="filled")[df.index >= start], duration_s, name, crit,
                                    expected_end, None)
        if outside:
            raise DataError(f"{name} : {n_window} missing bars out of {len(window)}, longest run {longest_run} "
                               f"(tolerance {tol.max_gaps_1h_share:.4f}, run <= "
                               f"{tol.max_consecutive_gaps_1h})")
        df = df.reindex(grid)
        df["filled"] = df["filled"].astype("boolean").fillna(True).astype(bool)
        df["close"] = df["close"].ffill()
        for c in ("open", "high", "low"):
            df[c] = df[c].fillna(df["close"])
        for c in ("volume", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote"):
            df[c] = df[c].fillna(0.0)
        df.index.name = "open_time"
    df["known_at"] = _seconds(df.index) + duration_s
    return df[BAR_COLUMNS + ["filled", "known_at"]]


def _lab_csv(p: Path) -> pd.DataFrame:
    df = pd.read_csv(p)
    idx = pd.to_datetime(df.pop("open_time_utc"), utc=True).dt.tz_localize(None)
    out = df[BAR_COLUMNS].astype("float64")
    out.index = pd.DatetimeIndex(idx).as_unit("ns")
    out.index.name = "open_time"
    return out.sort_index()


def _zips(root_path: Path, source: str, symbol: str) -> list[Path]:
    d = root_path / "raw" / source / symbol
    return sorted(d.glob("*.zip")) if d.is_dir() else []


def load(root_path: Path | str, criteria: Criteria | None = None, *, symbols: list[str] | None = None,
            control: list[str] | None = None, control_universe_path: Path | str | None = None,
            strict: bool = True) -> Data:
    """Load and validate all the data under `root_path` (project default: `var/research/data`).

    `symbols`/`control`: overrides for tests (default: universe of the criteria and frozen list of
    `research/control_universe.json`). `strict`: require the universe spot series to end exactly at the
    cutoff (2026-06-30 inclusive); tests on small fixtures pass `strict=False`.
    """
    root_path = Path(root_path)
    crit = criteria or load_criteria()
    ctl_path = Path(control_universe_path) if control_universe_path else CONTROL_UNIVERSE_PATH
    verify_manifest(root_path, ctl_path)
    universe = tuple(symbols if symbols is not None else crit.universe)
    if control is None:
        control = json.loads(ctl_path.read_text())["symbols"] if ctl_path.is_file() else []
    control = tuple(control)
    end = CUTOFF_TS if strict else None
    spot_1d, spot_1h, perp_1h, funding, ctl = {}, {}, {}, {}, {}
    ctl_1h, ctl_perp, ctl_fund = {}, {}, {}
    cuts: dict[str, int] = {}

    def perp(s: str, name: str):
        kz, fz = _zips(root_path, "perp_klines_1h", s), _zips(root_path, "perp_funding", s)
        if bool(kz) != bool(fz):
            raise DataError(f"{s} : perp klines and funding must exist together")
        if not kz:
            return None, None
        f = read_zips(fz, funding=True)
        verify_cutoff(f["known_at"].to_numpy(), f"{name} funding")
        k = _regularize(read_zips(kz), 3600, f"{name} perp 1h", crit, None, cuts)
        if f"{name} perp 1h" in cuts:  # the funding follows the shortened start of the perp bars
            f = f[f["known_at"].to_numpy() > cuts[f"{name} perp 1h"]]
        return k, f

    for s in universe:
        for interval, duration, target in (("1d", 86400, spot_1d), ("1h", 3600, spot_1h)):
            p = root_path / "lab" / f"{s}_{interval}.csv"
            if not p.is_file():
                raise DataError(f"{p} missing")
            target[s] = _regularize(_lab_csv(p), duration, f"{s} spot {interval}", crit, end)
        perp_1h[s], funding[s] = perp(s, s)
    for s in control:
        z = _zips(root_path, "spot_klines_1d", s)
        if not z:
            raise DataError(f"{s} : no control archive under {root_path / 'raw'}")
        ctl[s] = _regularize(read_zips(z), 86400, f"{s} control 1d", crit, None)
        z1 = _zips(root_path, "spot_klines_1h", s)
        ctl_1h[s] = _regularize(read_zips(z1), 3600, f"{s} control 1h", crit, None,
                                  cuts) if z1 else None
        ctl_perp[s], ctl_fund[s] = perp(s, f"{s} control")
    return Data(root_path=root_path, manifest_sha256=sha256_manifest(root_path), universe=universe,
                   control=control, spot_1d=spot_1d, spot_1h=spot_1h, perp_1h=perp_1h,
                   funding=funding, control_1d=ctl, control_1h=ctl_1h,
                   control_perp_1h=ctl_perp, control_funding=ctl_fund, cut_starts=cuts)
