"""Download of the public monthly archives of data.binance.vision, months <= 2026-06 only.

Firewall: `download_month` raises `CutoffError` for any (year, month) >= (2026, 7) BEFORE any network
request. Each zip is verified against the published `.CHECKSUM`. At most one request per second.
Resumable: a zip already present whose sha256 equals that of the `.CHECKSUM` kept beside it is skipped
without network access.
"""

from __future__ import annotations

import hashlib
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from research.config import LAST_MONTH, CutoffError

BASE = "https://data.binance.vision/data"
LIST = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
PAUSE_S = 1.0  # one request per second
SOURCES = ("perp_funding", "perp_klines_1h", "spot_klines_1d", "spot_klines_1h")


class DownloadError(Exception):
    """Network failure or checksum mismatch."""


class MissingData(DownloadError):
    """The archive does not exist (HTTP 404)."""


_last = [0.0]


def _limit() -> None:
    wait_s = _last[0] + PAUSE_S - time.monotonic()
    if wait_s > 0:
        time.sleep(wait_s)
    _last[0] = time.monotonic()


def _path(source: str, symbol: str) -> str:
    if source == "perp_funding":
        return f"futures/um/monthly/fundingRate/{symbol}"
    if source == "perp_klines_1h":
        return f"futures/um/monthly/klines/{symbol}/1h"
    if source == "spot_klines_1d":
        return f"spot/monthly/klines/{symbol}/1d"
    if source == "spot_klines_1h":
        return f"spot/monthly/klines/{symbol}/1h"
    raise ValueError(f"unknown source: {source!r} (expected: {SOURCES})")


def file_name(source: str, symbol: str, year: int, month: int) -> str:
    mm = f"{year:04d}-{month:02d}"
    return {
        "perp_funding": f"{symbol}-fundingRate-{mm}.zip",
        "perp_klines_1h": f"{symbol}-1h-{mm}.zip",
        "spot_klines_1d": f"{symbol}-1d-{mm}.zip",
        "spot_klines_1h": f"{symbol}-1h-{mm}.zip",
    }[source]


def month_url(source: str, symbol: str, year: int, month: int) -> str:
    return f"{BASE}/{_path(source, symbol)}/{file_name(source, symbol, year, month)}"


def local_path(dest: Path | str, source: str, symbol: str, year: int, month: int) -> Path:
    return Path(dest) / source / symbol / file_name(source, symbol, year, month)


def verify_month(year: int, month: int) -> None:
    if not (1 <= month <= 12):
        raise ValueError(f"invalid month: {month}")
    if (year, month) > LAST_MONTH:
        raise CutoffError(
            f"month {year:04d}-{month:02d} is after {LAST_MONTH[0]:04d}-{LAST_MONTH[1]:02d}: refused"
        )


def _get(client: httpx.Client, url: str, trials: int = 4) -> httpx.Response:
    last_error: Exception | None = None
    for k in range(trials):
        _limit()
        try:
            r = client.get(url, timeout=60.0)
        except httpx.TransportError as e:
            last_error = e
        else:
            if r.status_code == 404:
                raise MissingData(url)
            if r.status_code < 400:
                return r
            last_error = DownloadError(f"HTTP {r.status_code} on {url}")
            if r.status_code < 500 and r.status_code != 429:
                raise last_error
        if k < trials - 1:
            time.sleep(min(30.0, 2.0 ** (k + 1)) if PAUSE_S else 0)
    raise DownloadError(f"failed after {trials} attempts : {url} ({last_error})")


def _text_sha(text: str) -> str:
    m = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    if not m:
        raise DownloadError(f"unreadable CHECKSUM : {text[:80]!r}")
    return m.group(1).lower()


def download_month(source: str, symbol: str, year: int, month: int, dest: Path | str,
                     client: httpx.Client | None = None) -> Path:
    """Download (or find again) the month archive under `dest/<source>/<symbol>/`. Returns its path.

    `CutoffError` if (year, month) >= (2026, 7), before any network access. `MissingData` on 404.
    """
    verify_month(year, month)
    url = month_url(source, symbol, year, month)  # also validates `source`
    target = local_path(dest, source, symbol, year, month)
    checksum_path = target.with_name(target.name + ".CHECKSUM")
    if target.exists() and checksum_path.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() == _text_sha(checksum_path.read_text()):
            return target
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        published = _get(client, url + ".CHECKSUM").text
        expected = _text_sha(published)
        raw_bytes = _get(client, url).content
    finally:
        if owns_client:
            client.close()
    obtained = hashlib.sha256(raw_bytes).hexdigest()
    if obtained != expected:
        raise DownloadError(f"checksum mismatch for {url}: expected {expected}, got {obtained}")
    tmp = target.with_name(target.name + ".part")
    tmp.write_bytes(raw_bytes)
    tmp.replace(target)
    checksum_path.write_text(published if published.endswith("\n") else published + "\n")
    return target


def _list(client: httpx.Client, prefix: str, delimiter: bool) -> tuple[list[str], list[str]]:
    """Paginated S3 listing: (keys, common prefixes)."""
    keys: list[str] = []
    prefs: list[str] = []
    marker = ""
    while True:
        params = {"prefix": prefix, "max-keys": "1000"}
        if delimiter:
            params["delimiter"] = "/"
        if marker:
            params["marker"] = marker
        _limit()
        r = client.get(LIST, params=params, timeout=60.0)
        if r.status_code >= 400:
            raise DownloadError(f"listing HTTP {r.status_code} ({prefix})")
        xml_root = ET.fromstring(r.content)
        ns = xml_root.tag.split("}")[0] + "}" if xml_root.tag.startswith("{") else ""
        keys += [e.findtext(f"{ns}Key") or "" for e in xml_root.findall(f"{ns}Contents")]
        prefs += [e.findtext(f"{ns}Prefix") or "" for e in xml_root.findall(f"{ns}CommonPrefixes")]
        if (xml_root.findtext(f"{ns}IsTruncated") or "").lower() != "true":
            return keys, prefs
        marker = xml_root.findtext(f"{ns}NextMarker") or (keys[-1] if keys else prefs[-1])


def list_months(source: str, symbol: str, client: httpx.Client | None = None) -> list[tuple[int, int]]:
    """Published months (<= 2026-06 only) for a source and a symbol, from the public listing."""
    prefix = f"data/{_path(source, symbol)}/"
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        keys, _ = _list(client, prefix, delimiter=False)
    finally:
        if owns_client:
            client.close()
    out = []
    for c in keys:
        m = re.search(r"-(\d{4})-(\d{2})\.zip$", c)
        if m and c.startswith(prefix) and (int(m[1]), int(m[2])) <= LAST_MONTH:
            out.append((int(m[1]), int(m[2])))
    return sorted(set(out))


def list_spot_symbols(client: httpx.Client | None = None) -> list[str]:
    """All spot symbols with monthly candle archives (delisted ones included)."""
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        _, prefs = _list(client, "data/spot/monthly/klines/", delimiter=True)
    finally:
        if owns_client:
            client.close()
    return sorted(p.rstrip("/").rsplit("/", 1)[-1] for p in prefs)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
