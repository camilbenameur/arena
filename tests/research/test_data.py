"""Tests of the research data. No network (simulated transport) except the test marked `network`.
All the series are synthetic."""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pytest

from research.config import CUTOFF_TS, CutoffError, load_criteria
from research.data import (
    DataError,
    ManifestError,
    load,
    choose_control_universe,
    build_data,
    build_manifest,
    copy_in_sample,
    download_month,
    verify_manifest,
)
from research.data import build as mod_build
from research.data import control as mod_control
from research.data import download as mod_download
from research.data.lab import LabError
from research.data.reader import read_bars_zip, read_funding_zip


def ms(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp() * 1000)


@pytest.fixture(autouse=True)
def _without_pause(monkeypatch):
    monkeypatch.setattr(mod_download, "PAUSE_S", 0.0)


# ---------------------------------------------------------------------------------------- factories

def zip_of(name: str, text: str) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(name.replace(".zip", ".csv"), text)
    return b.getvalue()


def bar_lines(start: str, n: int, step_s: int, header=False, micro=False, price=100.0, qv=10.0, skips=()):
    t0 = ms(start)
    csv_header = ("open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,"
                  "taker_buy_quote_volume,ignore")
    out = [csv_header] if header else []
    for i in range(n):
        if i in skips:
            continue
        o = t0 + i * step_s * 1000
        p = price + i * 0.01
        f = 1000 if micro else 1
        out.append(f"{o * f},{p},{p + 1},{p - 1},{p + 0.5},5,{(o + step_s * 1000 - 1) * f},{qv},7,2,{qv / 2},0")
    return "\n".join(out) + "\n"


def lab_csv(start: str, n: int, step_s: int, skips=()):
    t0 = pd.Timestamp(start)
    out = ["open_time_utc,open,high,low,close,volume,quote_volume,trades,taker_buy_base,taker_buy_quote"]
    for i in range(n):
        if i in skips:
            continue
        t = (t0 + pd.Timedelta(seconds=i * step_s)).strftime("%Y-%m-%dT%H:%M:%SZ")
        p = 50 + i * 0.01
        out.append(f"{t},{p},{p + 1},{p - 1},{p + 0.5},5,{p * 5},7,2,{p * 2}")
    return "\n".join(out) + "\n"


def funding_lines(timestamps_ms: list[int], header=True):
    out = ["calc_time,funding_interval_hours,last_funding_rate"] if header else []
    out += [f"{t},8,0.0001" for t in timestamps_ms]
    return "\n".join(out) + "\n"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class Server:
    """Fake data.binance.vision: serves zips, .CHECKSUM files and S3 listings."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.requests: list[str] = []
        self.wrong_checksum: set[str] = set()

    def add(self, path: str, byte_count: bytes):
        self.files[f"https://data.binance.vision/data/{path}"] = byte_count

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._reply), follow_redirects=True)

    @property
    def n_zips(self) -> int:
        return sum(1 for r in self.requests if r.endswith(".zip"))

    def _reply(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url).split("?")[0]
        self.requests.append(url)
        if url.startswith("https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"):
            prefix = req.url.params["prefix"]
            delim = req.url.params.get("delimiter")
            keys = sorted(u.split("/data.binance.vision/")[1] for u in self.files
                          if u.split("/data.binance.vision/")[1].startswith(prefix))
            body = ["<ListBucketResult xmlns='http://s3.amazonaws.com/doc/2006-03-01/'><IsTruncated>false</IsTruncated>"]
            if delim:
                prefs = sorted({prefix + c[len(prefix):].split("/")[0] + "/" for c in keys})
                body += [f"<CommonPrefixes><Prefix>{p}</Prefix></CommonPrefixes>" for p in prefs]
            else:
                body += [f"<Contents><Key>{c}</Key></Contents>" for c in keys]
            body.append("</ListBucketResult>")
            return httpx.Response(200, text="".join(body))
        if url.endswith(".CHECKSUM"):
            base = url[: -len(".CHECKSUM")]
            if base not in self.files:
                return httpx.Response(404)
            h = "0" * 64 if base in self.wrong_checksum else sha(self.files[base])
            return httpx.Response(200, text=f"{h}  {base.rsplit('/', 1)[-1]}\n")
        if url in self.files:
            return httpx.Response(200, content=self.files[url])
        return httpx.Response(404)


# ------------------------------------------------------------------------------------ pare-feu / url

@pytest.mark.parametrize("year,month", [(2026, 7), (2026, 12), (2027, 1), (2030, 3)])
@pytest.mark.parametrize("source", ["perp_funding", "perp_klines_1h", "spot_klines_1d", "spot_klines_1h"])
def test_month_after_cutoff_raises_without_network(tmp_path, source, year, month):
    class Forbidden(httpx.BaseTransport):
        def handle_request(self, request):
            raise AssertionError("network call forbidden")

    with httpx.Client(transport=Forbidden()) as c, pytest.raises(CutoffError):
        download_month(source, "BTCUSDT", year, month, tmp_path, client=c)
    # And with no client at all: the error even precedes the creation of the client.
    with pytest.raises(CutoffError):
        download_month(source, "BTCUSDT", year, month, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_urls():
    u = mod_download.month_url
    assert u("perp_funding", "BTCUSDT", 2024, 1) == (
        "https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2024-01.zip")
    assert u("perp_klines_1h", "ETHUSDT", 2026, 6) == (
        "https://data.binance.vision/data/futures/um/monthly/klines/ETHUSDT/1h/ETHUSDT-1h-2026-06.zip")
    assert u("spot_klines_1d", "ADAUSDT", 2020, 1) == (
        "https://data.binance.vision/data/spot/monthly/klines/ADAUSDT/1d/ADAUSDT-1d-2020-01.zip")
    assert u("spot_klines_1h", "EOSUSDT", 2021, 3) == (
        "https://data.binance.vision/data/spot/monthly/klines/EOSUSDT/1h/EOSUSDT-1h-2021-03.zip")
    with pytest.raises(ValueError):
        u("other", "BTCUSDT", 2020, 1)


# --------------------------------------------------------------------------------------- download

def test_download_verifies_checksum_and_resumes(tmp_path):
    srv = Server()
    z = zip_of("x.zip", funding_lines([ms("2024-01-01T00:00:00")]))
    srv.add("futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2024-01.zip", z)
    with srv.client() as c:
        p = download_month("perp_funding", "BTCUSDT", 2024, 1, tmp_path, client=c)
        assert p.read_bytes() == z and p.name == "BTCUSDT-fundingRate-2024-01.zip"
        n = len(srv.requests)
        assert download_month("perp_funding", "BTCUSDT", 2024, 1, tmp_path, client=c) == p
        assert len(srv.requests) == n  # skipped, no network
        # corrupted file: downloaded again
        p.write_bytes(b"corrompu")
        download_month("perp_funding", "BTCUSDT", 2024, 1, tmp_path, client=c)
        assert p.read_bytes() == z and len(srv.requests) == n + 2


def test_different_checksum_refused_and_nothing_written(tmp_path):
    srv = Server()
    path = "spot/monthly/klines/AAAUSDT/1d/AAAUSDT-1d-2020-01.zip"
    srv.add(path, zip_of("x.zip", bar_lines("2020-01-01T00:00:00", 31, 86400)))
    srv.wrong_checksum.add("https://data.binance.vision/data/" + path)
    with srv.client() as c, pytest.raises(mod_download.DownloadError):
        download_month("spot_klines_1d", "AAAUSDT", 2020, 1, tmp_path, client=c)
    assert not list(tmp_path.rglob("*.zip"))


def test_archive_absent(tmp_path):
    with Server().client() as c, pytest.raises(mod_download.MissingData):
        download_month("spot_klines_1d", "ZZZUSDT", 2020, 1, tmp_path, client=c)


def test_list_months_filters_after_cutoff():
    srv = Server()
    for a, m in [(2026, 5), (2026, 6), (2026, 7), (2027, 1)]:
        srv.add(f"spot/monthly/klines/AAAUSDT/1d/AAAUSDT-1d-{a}-{m:02d}.zip", b"x")
        srv.add(f"spot/monthly/klines/AAAUSDT/1d/AAAUSDT-1d-{a}-{m:02d}.zip.CHECKSUM", b"x")
    with srv.client() as c:
        assert mod_download.list_months("spot_klines_1d", "AAAUSDT", c) == [(2026, 5), (2026, 6)]


# ------------------------------------------------------------------------------------------- lecture

def test_read_with_or_without_header_and_microseconds():
    a = read_bars_zip(zip_of("a.zip", bar_lines("2024-01-01T00:00:00", 3, 3600, header=True)))
    b = read_bars_zip(zip_of("a.zip", bar_lines("2024-01-01T00:00:00", 3, 3600, header=False)))
    c = read_bars_zip(zip_of("a.zip", bar_lines("2024-01-01T00:00:00", 3, 3600, micro=True)))
    pd.testing.assert_frame_equal(a, b)
    pd.testing.assert_frame_equal(a, c)
    assert a.index[0] == pd.Timestamp("2024-01-01") and a.index.name == "open_time"


def test_read_funding_known_at_is_timestamp_plus_1s():
    t = ms("2024-01-01T08:00:00") + 5  # jitter of a few ms as in the real archives
    f = read_funding_zip(zip_of("f.zip", funding_lines([t])))
    assert int(f["known_at"].iloc[0]) == ms("2024-01-01T08:00:00") // 1000 + 1
    assert f["rate"].iloc[0] == 0.0001


# ------------------------------------------------------------------------------------------- lab

def dummy_lab(src: Path, ok=True):
    src.mkdir(parents=True)
    entries = []
    for name in ("AAAUSDT_1d.csv", "AAAUSDT_1h.csv"):
        content = lab_csv("2026-06-01", 5, 86400)
        (src / name).write_text(content)
        entries.append({"file": name, "bars": 5, "sha256": sha(content.encode()) if ok else "0" * 64})
    (src / "MANIFEST.json").write_text(json.dumps({"files": entries}))


def test_lab_copy_verified(tmp_path):
    dummy_lab(tmp_path / "src")
    out = copy_in_sample(tmp_path / "src", tmp_path / "dest")
    assert sorted(p.name for p in out) == ["AAAUSDT_1d.csv", "AAAUSDT_1h.csv"]
    assert (tmp_path / "dest" / "MANIFEST.json").exists()
    copy_in_sample(tmp_path / "src", tmp_path / "dest")  # resumable


def test_lab_copy_refuses_a_different_sha_and_copies_nothing(tmp_path):
    dummy_lab(tmp_path / "src", ok=False)
    with pytest.raises(LabError):
        copy_in_sample(tmp_path / "src", tmp_path / "dest")
    assert not (tmp_path / "dest").exists()


# ----------------------------------------------------------------------------------------- control

def control_server(n_ok=22):
    srv = Server()

    def add_symbol(sym, qv, n=31):
        srv.add(f"spot/monthly/klines/{sym}/1d/{sym}-1d-2020-01.zip",
                    zip_of("x.zip", bar_lines("2020-01-01T00:00:00", n, 86400, qv=qv)))

    for i in range(n_ok):
        add_symbol(f"C{i:02d}USDT", 1000.0 + i)
    add_symbol("BTCUSDT", 1e9)  # in the universe
    add_symbol("USDCUSDT", 1e9)  # stablecoin
    add_symbol("BNBUPUSDT", 1e9)  # leveraged token
    add_symbol("PARTUSDT", 1e9, n=20)  # 2020-01 incomplete
    srv.add("spot/monthly/klines/NOEURBTC/1d/NOEURBTC-1d-2020-01.zip", b"x")  # not USDT
    srv.add("spot/monthly/klines/LATEUSDT/1d/LATEUSDT-1d-2021-03.zip", b"x")  # no 2020-01
    return srv


def test_control_universe_rule_and_freeze(tmp_path):
    srv = control_server()
    output = tmp_path / "control_universe.json"
    with srv.client() as c:
        items = choose_control_universe(output, cache=tmp_path / "raw", client=c, date="2026-11-11")
    # the 20 largest volumes among C00..C21: C02..C21, by decreasing volume
    assert items == [f"C{i:02d}USDT" for i in range(21, 1, -1)]
    doc = json.loads(output.read_text())
    assert doc["symbols"] == items and doc["date"] == "2026-11-11" and doc["size"] == 20
    n = len(srv.requests)
    with srv.client() as c:  # frozen: reread without network
        assert choose_control_universe(output, cache=tmp_path / "raw", client=c) == items
    assert len(srv.requests) == n


def test_control_universe_resumable(tmp_path):
    srv = control_server()
    with srv.client() as c:
        choose_control_universe(tmp_path / "u.json", cache=tmp_path / "raw", client=c, date="2026-11-11")
    zips = srv.n_zips
    with srv.client() as c:
        choose_control_universe(tmp_path / "u2.json", cache=tmp_path / "raw", client=c, date="2026-11-11")
    # nothing is downloaded again: only the listings are redone, no zip requested twice
    assert srv.n_zips == zips


def test_eligibility():
    u = frozenset({"BTCUSDT"})
    assert mod_control.eligible_candidate("XMRUSDT", u)
    for s in ("BTCUSDT", "USDCUSDT", "TUSDUSDT", "BUSDUSDT", "ETHUPUSDT", "BNBBEARUSDT", "ETHBTC", "EURUSDT"):
        assert not mod_control.eligible_candidate(s, u)


# ------------------------------------------------------------------------------ loader: fixtures

def dummy_root(tmp_path, *, end_1d="2026-06-30", bars_1h=None, skips_1h=(), skips_1d=(),
                   funding=None, perp_start="2026-06-29T00:00:00", perp_n=48, perp_skips=(),
                   with_perp=True, control=True, ctl_skips_1h=(), ctl_perp=True, ctl_1h=True,
                   ctl_1h_start="2026-06-29T00:00:00", ctl_1h_n=48, ctl_funding=None) -> Path:
    """Minimal root: one symbol AAAUSDT, 10 days of 1d, 1h over the requested period."""
    r = tmp_path / "data"
    (r / "lab").mkdir(parents=True)
    end = pd.Timestamp(end_1d)
    start_1d = end - pd.Timedelta(days=9)
    (r / "lab" / "AAAUSDT_1d.csv").write_text(lab_csv(str(start_1d.date()), 10, 86400, skips=skips_1d))
    n1h = bars_1h or 240
    start_1h = end + pd.Timedelta(days=1) - pd.Timedelta(hours=n1h)
    (r / "lab" / "AAAUSDT_1h.csv").write_text(lab_csv(str(start_1h), n1h, 3600, skips=skips_1h))
    if with_perp:
        d = r / "raw" / "perp_klines_1h" / "AAAUSDT"
        d.mkdir(parents=True)
        (d / "AAAUSDT-1h-2026-06.zip").write_bytes(
            zip_of("x.zip", bar_lines(perp_start, perp_n, 3600, header=True, skips=perp_skips)))
        d = r / "raw" / "perp_funding" / "AAAUSDT"
        d.mkdir(parents=True)
        f = funding or [ms("2026-06-29T00:00:00") + k * 8 * 3600_000 + 2 for k in range(6)]
        (d / "AAAUSDT-fundingRate-2026-06.zip").write_bytes(zip_of("x.zip", funding_lines(f)))
    if control:
        d = r / "raw" / "spot_klines_1d" / "CTLUSDT"
        d.mkdir(parents=True)
        (d / "CTLUSDT-1d-2026-06.zip").write_bytes(
            zip_of("x.zip", bar_lines("2026-06-20T00:00:00", 10, 86400, micro=True)))
        if ctl_1h:
            d = r / "raw" / "spot_klines_1h" / "CTLUSDT"
            d.mkdir(parents=True)
            (d / "CTLUSDT-1h-2026-06.zip").write_bytes(
                zip_of("x.zip", bar_lines(ctl_1h_start, ctl_1h_n, 3600, skips=ctl_skips_1h)))
        if ctl_perp:
            d = r / "raw" / "perp_klines_1h" / "CTLUSDT"
            d.mkdir(parents=True)
            (d / "CTLUSDT-1h-2026-06.zip").write_bytes(
                zip_of("x.zip", bar_lines("2026-06-29T00:00:00", 48, 3600, header=True)))
            d = r / "raw" / "perp_funding" / "CTLUSDT"
            d.mkdir(parents=True)
            f = ctl_funding or [ms("2026-06-29T00:00:00") + k * 8 * 3600_000 for k in range(6)]
            (d / "CTLUSDT-fundingRate-2026-06.zip").write_bytes(zip_of("x.zip", funding_lines(f)))
    return r


def ctl_json(tmp_path, symbols=("CTLUSDT",)):
    p = tmp_path / "control_universe.json"
    p.write_text(json.dumps({"symbols": list(symbols)}))
    return p


def payload(tmp_path, r, **kw):
    build_manifest(r, ctl_json(tmp_path))
    return load(r, symbols=["AAAUSDT"], control_universe_path=tmp_path / "control_universe.json",
                   strict=False, **kw)


# ------------------------------------------------------------------------------------ loader: cases

def test_loader_nominal_and_known_at(tmp_path):
    d = payload(tmp_path, dummy_root(tmp_path))
    assert d.universe == ("AAAUSDT",) and d.control == ("CTLUSDT",)
    j = d.spot_1d["AAAUSDT"]
    # 1d bar of 2026-06-30: known_at = cutoff exactly (allowed, strict comparison)
    assert j.index[-1] == pd.Timestamp("2026-06-30") and int(j["known_at"].iloc[-1]) == CUTOFF_TS
    h = d.spot_1h["AAAUSDT"]
    assert h.index[-1] == pd.Timestamp("2026-06-30 23:00") and int(h["known_at"].iloc[-1]) == CUTOFF_TS
    assert (h["known_at"].diff().dropna() == 3600).all() and not h["filled"].any()
    assert j["known_at"].dtype == np.int64 and j["close"].dtype == np.float64
    p = d.perp_1h["AAAUSDT"]
    assert len(p) == 48 and int(p["known_at"].iloc[-1]) == CUTOFF_TS
    f = d.funding["AAAUSDT"]
    assert len(f) == 6
    assert int(f["known_at"].iloc[0]) == ms("2026-06-29T00:00:00") // 1000 + 1  # fundingTime + 1 s (gigue 2 ms)
    c = d.control_1d["CTLUSDT"]
    assert len(c) == 10 and c.index[0] == pd.Timestamp("2026-06-20")  # microseconds normalized
    assert d.manifest_sha256
    h1 = d.control_1h["CTLUSDT"]
    assert len(h1) == 48 and int(h1["known_at"].iloc[-1]) == CUTOFF_TS and not h1["filled"].any()
    assert len(d.control_perp_1h["CTLUSDT"]) == 48
    cf = d.control_funding["CTLUSDT"]
    assert len(cf) == 6 and int(cf["known_at"].iloc[0]) == ms("2026-06-29T00:00:00") // 1000 + 1


def test_control_without_perp_or_1h_gives_none(tmp_path):
    d = payload(tmp_path, dummy_root(tmp_path, ctl_perp=False, ctl_1h=False))
    assert d.control_perp_1h == {"CTLUSDT": None} and d.control_funding == {"CTLUSDT": None}
    assert d.control_1h == {"CTLUSDT": None} and len(d.control_1d["CTLUSDT"]) == 10


def test_delisted_control_stops_without_error(tmp_path):
    # control 1h bars stopped on 2026-03-02: no error, the table ends there
    d = payload(tmp_path, dummy_root(tmp_path, ctl_1h_start="2026-03-01T00:00:00", ctl_1h_n=48))
    assert d.control_1h["CTLUSDT"].index[-1] == pd.Timestamp("2026-03-02 23:00")


def test_control_1h_perp_funding_after_cutoff_raises(tmp_path):
    with pytest.raises(CutoffError, match="control 1h"):
        payload(tmp_path, dummy_root(tmp_path, ctl_1h_start="2026-06-30T12:00:00", ctl_1h_n=13))
    with pytest.raises(CutoffError, match="funding"):
        payload(tmp_path / "f", dummy_root(
            tmp_path / "f", ctl_funding=[ms("2026-06-30T16:00:00"), ms("2026-07-01T00:00:00")]))
    d = payload(tmp_path / "ok", dummy_root(tmp_path / "ok", ctl_funding=[ms("2026-06-30T16:00:00")]))
    assert int(d.control_funding["CTLUSDT"]["known_at"].iloc[-1]) == ms("2026-06-30T16:00:00") // 1000 + 1


def test_control_1h_same_tolerances(tmp_path):
    # 1/48 > 0.1% in the window: erratum 3, the series starts after the gap (nothing is filled)
    d0 = payload(tmp_path, dummy_root(tmp_path, ctl_skips_1h={10}))
    h = d0.control_1h["CTLUSDT"]
    assert len(h) == 37 and not h["filled"].any() and "CTLUSDT control 1h" in d0.cut_starts
    # the same gap before the evaluation window (2019) is filled without threshold
    d = payload(tmp_path / "e", dummy_root(tmp_path / "e", ctl_1h_start="2019-03-01T00:00:00",
                                               ctl_skips_1h={10}))
    assert int(d.control_1h["CTLUSDT"]["filled"].sum()) == 1


def test_manifest_covers_the_control_sources(tmp_path):
    r = dummy_root(tmp_path)
    doc = build_manifest(r, ctl_json(tmp_path))
    for prefix in ("raw/spot_klines_1h/CTLUSDT/", "raw/perp_klines_1h/CTLUSDT/", "raw/perp_funding/CTLUSDT/"):
        assert any(k.startswith(prefix) for k in doc["files"]), prefix
    z = r / "raw" / "spot_klines_1h" / "CTLUSDT" / "CTLUSDT-1h-2026-06.zip"
    z.write_bytes(z.read_bytes() + b"x")
    with pytest.raises(ManifestError, match="differs"):
        verify_manifest(r, tmp_path / "control_universe.json")


def test_missing_perp_gives_none(tmp_path):
    d = payload(tmp_path, dummy_root(tmp_path, with_perp=False))
    assert d.perp_1h["AAAUSDT"] is None and d.funding["AAAUSDT"] is None


def test_bar_after_cutoff_raises(tmp_path):
    # a 1d bar opened on 2026-07-01 has known_at = 2026-07-02 > cutoff
    r = dummy_root(tmp_path)
    p = r / "lab" / "AAAUSDT_1d.csv"
    p.write_text(p.read_text() + "2026-07-01T00:00:00Z,50,51,49,50.5,5,250,7,2,100\n")
    with pytest.raises(CutoffError):
        payload(tmp_path, r)


def test_1h_bar_open_at_the_cutoff_raises(tmp_path):
    r = dummy_root(tmp_path)
    p = r / "lab" / "AAAUSDT_1h.csv"
    p.write_text(p.read_text() + "2026-07-01T00:00:00Z,50,51,49,50.5,5,250,7,2,100\n")
    with pytest.raises(CutoffError):
        payload(tmp_path, r)


def test_perp_bar_after_cutoff_raises(tmp_path):
    with pytest.raises(CutoffError):
        payload(tmp_path, dummy_root(tmp_path, perp_start="2026-06-30T12:00:00", perp_n=13))


def test_funding_at_the_cutoff_raises_but_not_before(tmp_path):
    # fundingTime = 2026-07-01T00:00:00Z -> known_at = cutoff + 1 s: refused
    with pytest.raises(CutoffError):
        payload(tmp_path, dummy_root(tmp_path, funding=[ms("2026-06-30T16:00:00"), ms("2026-07-01T00:00:00")]))
    d = payload(tmp_path / "ok", dummy_root(tmp_path / "ok", funding=[ms("2026-06-30T16:00:00")]))
    assert int(d.funding["AAAUSDT"]["known_at"].iloc[-1]) == ms("2026-06-30T16:00:00") // 1000 + 1


def test_control_after_cutoff_raises(tmp_path):
    r = dummy_root(tmp_path, control=False)
    d = r / "raw" / "spot_klines_1d" / "CTLUSDT"
    d.mkdir(parents=True)
    (d / "CTLUSDT-1d-2026-06.zip").write_bytes(zip_of("x.zip", bar_lines("2026-06-28T00:00:00", 5, 86400)))
    with pytest.raises(CutoffError):
        payload(tmp_path, r)  # the 07-02 bar (opened after the cutoff)


def test_1d_gap_is_refused(tmp_path):
    with pytest.raises(DataError, match="gap"):
        payload(tmp_path, dummy_root(tmp_path, skips_1d={4}))


def test_1h_gap_within_tolerance_is_filled(tmp_path):
    n = 2400  # 1 missing = 0.04% < 0.1%
    d = payload(tmp_path, dummy_root(tmp_path, bars_1h=n, skips_1h={1000}))
    h = d.spot_1h["AAAUSDT"]
    assert len(h) == n and int(h["filled"].sum()) == 1
    filled = h[h["filled"]].iloc[0]
    prev = h["close"].iloc[h.index.get_loc(filled.name) - 1]
    assert filled["close"] == filled["open"] == filled["high"] == filled["low"] == prev
    assert filled["volume"] == 0.0 and filled["trades"] == 0.0


def test_1h_gap_outside_tolerance_is_refused(tmp_path):
    with pytest.raises(DataError, match="missing"):
        payload(tmp_path, dummy_root(tmp_path, skips_1h={10}))  # 1/240 > 0.1%
    with pytest.raises(DataError, match="run"):  # 7 consecutive in a long enough series
        payload(tmp_path / "b", dummy_root(tmp_path / "b", bars_1h=7200, skips_1h=set(range(100, 107))))


def test_strict_requires_the_end_at_the_cutoff(tmp_path):
    r = dummy_root(tmp_path, end_1d="2026-06-29")
    build_manifest(r, ctl_json(tmp_path))
    with pytest.raises(DataError):
        load(r, symbols=["AAAUSDT"], control_universe_path=tmp_path / "control_universe.json", strict=True)


def test_manifest_detects_modification_addition_and_absence(tmp_path):
    r = dummy_root(tmp_path)
    ctl = ctl_json(tmp_path)
    build_manifest(r, ctl)
    verify_manifest(r, ctl)
    csv = r / "lab" / "AAAUSDT_1d.csv"
    old = csv.read_text()
    csv.write_text(old.replace("50.5", "51.5", 1))
    for call in (lambda: verify_manifest(r, ctl),
                  lambda: load(r, symbols=["AAAUSDT"], control_universe_path=ctl, strict=False)):
        with pytest.raises(ManifestError, match="differs"):
            call()
    csv.write_text(old)
    verify_manifest(r, ctl)
    (r / "intruder.txt").write_text("x")
    with pytest.raises(ManifestError, match="unlisted"):
        verify_manifest(r, ctl)
    (r / "intruder.txt").unlink()
    csv.unlink()
    with pytest.raises(ManifestError, match="missing"):
        verify_manifest(r, ctl)
    # the frozen control list is part of the data
    csv.write_text(old)
    ctl.write_text(json.dumps({"symbols": ["OTHER"]}))
    with pytest.raises(ManifestError, match="control_universe"):
        verify_manifest(r, ctl)


def test_loader_without_manifest_is_refused(tmp_path):
    with pytest.raises(ManifestError):
        load(dummy_root(tmp_path), symbols=["AAAUSDT"], strict=False)


# ------------------------------------------------------------------- build_data (offline)

def test_build_data_complete_and_resumable(tmp_path, monkeypatch):
    crit = dataclasses.replace(load_criteria(), universe=("AAAUSDT",), control_size=2)
    monkeypatch.setattr(mod_build, "load_criteria", lambda: crit)
    monkeypatch.setattr(mod_control, "load_criteria", lambda: crit)
    dummy_lab(tmp_path / "lab_src")
    srv = Server()
    for src, sym, name in [("futures/um/monthly/fundingRate", "AAAUSDT", "fundingRate"),
                          ("futures/um/monthly/klines", "AAAUSDT", "1h")]:
        for month in ("2026-05", "2026-06", "2026-07"):  # 2026-07 is listed but must never be requested
            below = "" if name == "fundingRate" else "/1h"
            content = (funding_lines([ms(f"{month}-01T00:00:00")]) if name == "fundingRate"
                       else bar_lines(f"{month}-01T00:00:00", 3, 3600))
            srv.add(f"{src}/{sym}/{sym}-{name}-{month}.zip".replace(f"/{sym}/", f"/{sym}{below}/", 1),
                        zip_of("x.zip", content))
    for i in range(3):
        sym = f"K{i}USDT"
        for month in ("2020-01", "2020-02"):
            n = 31 if month == "2020-01" else 29
            srv.add(f"spot/monthly/klines/{sym}/1d/{sym}-1d-{month}.zip",
                        zip_of("x.zip", bar_lines(f"{month}-01T00:00:00", n, 86400, qv=10.0 + i)))
    for sym in ("K2USDT", "K1USDT"):  # control: spot 1h for both, perp only for K2
        srv.add(f"spot/monthly/klines/{sym}/1h/{sym}-1h-2026-06.zip",
                    zip_of("x.zip", bar_lines("2026-06-01T00:00:00", 3, 3600)))
        srv.add(f"spot/monthly/klines/{sym}/1h/{sym}-1h-2026-07.zip", zip_of("x.zip", bar_lines("2026-07-01T00:00:00", 3, 3600)))
    srv.add("futures/um/monthly/klines/K2USDT/1h/K2USDT-1h-2026-06.zip",
                zip_of("x.zip", bar_lines("2026-06-01T00:00:00", 3, 3600)))
    srv.add("futures/um/monthly/fundingRate/K2USDT/K2USDT-fundingRate-2026-06.zip",
                zip_of("x.zip", funding_lines([ms("2026-06-01T00:00:00")])))
    root_path = tmp_path / "root_path"
    ctl = tmp_path / "control_universe.json"
    with srv.client() as c:
        doc = build_data(root_path, lab_src=tmp_path / "lab_src", control_universe_path=ctl, client=c)
        assert json.loads(ctl.read_text())["symbols"] == ["K2USDT", "K1USDT"]
        assert not any("2026-07" in u for u in srv.requests)
        raw = root_path / "raw"
        assert len(list((raw / "spot_klines_1h").rglob("*.zip"))) == 2
        assert len(list((raw / "perp_klines_1h" / "K2USDT").glob("*.zip"))) == 1
        assert not (raw / "perp_klines_1h" / "K1USDT").exists()  # no perp: normal
        n_zips = srv.n_zips
        verify_manifest(root_path, ctl)
        assert (root_path / "MANIFEST.json").exists() and doc["control_universe_sha256"]
        # resume: no zip requested again
        doc2 = build_data(root_path, lab_src=tmp_path / "lab_src", control_universe_path=ctl, client=c)
        assert srv.n_zips == n_zips
        assert doc2["files"] == doc["files"]


# ------------------------------------------------------------------------------------------- network

@pytest.mark.network
def test_network_funding_btcusdt_2024_01(tmp_path):
    mod_download.PAUSE_S = 1.0
    p = download_month("perp_funding", "BTCUSDT", 2024, 1, tmp_path)
    assert p.exists() and (p.parent / (p.name + ".CHECKSUM")).exists()
    f = read_funding_zip(p.read_bytes(), p.name)
    assert len(f) == 93  # 31 days x 3 funding times
    assert f.index[0].year == 2024 and f.index[-1] < pd.Timestamp("2024-02-01")
    assert (f["known_at"] <= CUTOFF_TS).all()


def test_warmup_gaps_filled_without_threshold_window_gaps_refused():
    from research.data.loader import _regularize

    crit = load_criteria()

    def track(start, n, skips):
        idx = pd.date_range(start, periods=n, freq="D").delete(list(skips))
        return pd.DataFrame({c: 1.0 for c in ["open", "high", "low", "close", "volume", "quote_volume",
                                              "trades", "taker_buy_base", "taker_buy_quote"]}, index=idx)

    out = _regularize(track("2019-12-01", 60, {3, 4, 5}), 86400, "w", crit, None)  # gap in 2019: filled
    assert int(out["filled"].sum()) == 3 and len(out) == 60
    with pytest.raises(DataError, match="gap"):
        _regularize(track("2019-12-01", 60, {40}), 86400, "w", crit, None)  # gap in 2020: refused


def test_erratum3_eligible_start_after_the_last_out_of_tolerance_gap():
    import numpy as np
    import pandas as pd

    from research.data.loader import _eligible_start
    idx = pd.date_range("2020-01-01", periods=20_000, freq="h")
    a = np.zeros(len(idx), bool)
    a[1000:1072] = True   # 72 h
    a[5000:5048] = True   # 48 h
    a[9000:9003] = True   # 3 h: within tolerance, does not cut
    d = _eligible_start(pd.Series(a, index=idx), 0.001, 6)
    assert d == idx[5048]
    assert _eligible_start(pd.Series(np.zeros(10, bool), index=idx[:10]), 0.001, 6) == idx[0]
    whole = np.zeros(100, bool); whole[-10:] = True
    assert _eligible_start(pd.Series(whole, index=idx[:100]), 0.001, 6) is None
