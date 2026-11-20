"""Reading of the Binance zips (candles and funding) into DataFrames with a naive UTC (ns) index."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

BAR_COLUMNS = ["open", "high", "low", "close", "volume", "quote_volume", "trades",
                  "taker_buy_base", "taker_buy_quote"]


class ReadError(Exception):
    pass


def _zip_csv(raw_bytes: bytes, name: str) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
        names = [n for n in z.namelist() if n.endswith(".csv")]
        if len(names) != 1:
            raise ReadError(f"{name} : exactly one CSV expected in the zip, found {names}")
        csv_bytes = z.read(names[0])
    # The header is present depending on the year: detected from the nature of the first cell.
    first = csv_bytes.split(b"\n", 1)[0].split(b",", 1)[0].strip()
    header = 0 if first.lstrip(b"-").replace(b".", b"").isdigit() else 1
    df = pd.read_csv(io.BytesIO(csv_bytes), header=None, skiprows=header)
    if df.empty:
        raise ReadError(f"{name} : empty CSV")
    return df


def _ms(col: pd.Series) -> pd.Series:
    """Timestamps in milliseconds; the spot archives switch to microseconds from 2025."""
    s = col.astype("int64")
    return s.where(s < 10**14, s // 1000)


def index_utc(ms: pd.Series) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(ms.to_numpy(), unit="ms")).as_unit("ns")


def read_bars_zip(raw_bytes: bytes, name: str = "?") -> pd.DataFrame:
    df = _zip_csv(raw_bytes, name)
    if df.shape[1] < 11:
        raise ReadError(f"{name} : {df.shape[1]} columns, at least 11 expected")
    out = pd.DataFrame({
        "open": df[1], "high": df[2], "low": df[3], "close": df[4], "volume": df[5],
        "quote_volume": df[7], "trades": df[8], "taker_buy_base": df[9], "taker_buy_quote": df[10],
    }).astype("float64")
    out.index = index_utc(_ms(df[0]))
    out.index.name = "open_time"
    return out


def read_funding_zip(raw_bytes: bytes, name: str = "?") -> pd.DataFrame:
    df = _zip_csv(raw_bytes, name)
    if df.shape[1] < 2:
        raise ReadError(f"{name} : not enough columns")
    ms = _ms(df[0])
    out = pd.DataFrame({"rate": df[df.shape[1] - 1].astype("float64").to_numpy()},
                       index=index_utc(ms))
    out.index.name = "funding_time"
    out["known_at"] = (ms.to_numpy() // 1000 + 1).astype("int64")  # fundingTime + 1 s
    return out


def read_zips(paths: list[Path], funding: bool = False) -> pd.DataFrame:
    """Concatenate monthly zips, sort, deduplicate (keep the first occurrence)."""
    chunks = []
    for p in sorted(paths):
        raw_bytes = Path(p).read_bytes()
        chunks.append(read_funding_zip(raw_bytes, Path(p).name) if funding
                        else read_bars_zip(raw_bytes, Path(p).name))
    if not chunks:
        raise ReadError("no file")
    df = pd.concat(chunks).sort_index()
    return df[~df.index.duplicated(keep="first")]
