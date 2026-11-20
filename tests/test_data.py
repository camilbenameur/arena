"""Data module tests: no network (mocked httpx transport, recorded fixtures) except those marked `network`."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from arena.config import ConfigError, load_config, load_instruments
from arena.data import DataError, RateLimitedHttp, to_qty, to_ueur
from arena.data.binance import BinanceClient, DayBar
from arena.data.kraken import KrakenClient, KrakenError
from arena.data.store import BarStore
from arena.types import Bar

FIX = Path(__file__).parent / "fixtures"
CONFIG = Path(__file__).resolve().parent.parent / "config" / "arena.toml"
H4 = 14400


def fx(name: str) -> bytes:
    return (FIX / name).read_bytes()


class FakeTime:
    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


def make_http(handler, ft: FakeTime | None = None) -> RateLimitedHttp:
    ft = ft or FakeTime()
    return RateLimitedHttp(
        httpx.Client(transport=httpx.MockTransport(handler)), sleep=ft.sleep, clock=ft.clock
    )


def ok(name: str):
    return lambda req: httpx.Response(200, content=fx(name))


def kraken(handler, now: float) -> KrakenClient:
    return KrakenClient(make_http(handler), now=lambda: now)


OHLC = json.loads(fx("kraken_ohlc.json"))
OHLC_ROWS = OHLC["result"]["XXBTZEUR"]
LAST_TS = int(OHLC_ROWS[-1][0])


# --- conversions -----------------------------------------------------------------------------


def test_conversion_exact():
    assert to_ueur("56622.4") == 56_622_400_000
    assert to_qty("130.20355035") == 13_020_355_035
    assert to_ueur("0.00001") == 10
    assert to_ueur("67181.10000") == 67_181_100_000
    with pytest.raises(DataError):
        to_ueur("abc")


# --- Kraken ----------------------------------------------------------------------------------


def test_ohlc_excludes_current_bar():
    c = kraken(ok("kraken_ohlc.json"), now=LAST_TS + 3600)
    bars = c.ohlc("BTC/EUR", "XBTEUR")
    assert len(bars) == len(OHLC_ROWS) - 1
    assert all(b.ts < LAST_TS for b in bars)
    assert [b.ts for b in bars] == sorted(b.ts for b in bars)


def test_ohlc_keeps_last_bar_if_closed():
    c = kraken(ok("kraken_ohlc.json"), now=LAST_TS + H4)
    assert len(c.ohlc("BTC/EUR", "XBTEUR")) == len(OHLC_ROWS)


def test_ohlc_conversion_fields():
    c = kraken(ok("kraken_ohlc.json"), now=LAST_TS + H4)
    b = c.ohlc("BTC/EUR", "XBTEUR")[-1]
    assert b == Bar(
        "BTC/EUR", H4, LAST_TS, 66_593_700_000, 67_350_400_000, 66_548_000_000, 67_182_700_000, 5_089_968_857
    )


def test_ohlc_request_parameters():
    seen = {}

    def h(req: httpx.Request) -> httpx.Response:
        seen.update(req.url.params)
        return httpx.Response(200, content=fx("kraken_ohlc.json"))

    kraken(h, now=LAST_TS).ohlc("BTC/EUR", "XBTEUR", since=123)
    assert seen == {"pair": "XBTEUR", "interval": "240", "since": "123"}


def test_ticker_quote():
    q = kraken(ok("kraken_ticker.json"), now=1_800_000_000).ticker("BTC/EUR", "XBTEUR")
    assert (q.symbol, q.ts, q.ask, q.bid) == ("BTC/EUR", 1_800_000_000, 67_181_100_000, 67_181_000_000)


def test_asset_pairs_integers():
    p = kraken(ok("kraken_assetpairs.json"), now=0).asset_pairs(["XBTEUR", "ETHEUR", "XRPEUR"])
    assert (p["XBTEUR"].tick_ueur, p["XBTEUR"].lot_min_qty, p["XBTEUR"].cost_min_ueur) == (
        100_000,
        6_000,
        450_000,
    )
    assert p["ETHEUR"].tick_ueur == 10_000 and p["ETHEUR"].lot_min_qty == 200_000
    assert p["XRPEUR"].tick_ueur == 10 and p["XRPEUR"].lot_min_qty == 400_000_000


def test_asset_pairs_missing_pair():
    with pytest.raises(DataError, match="missing"):
        kraken(ok("kraken_assetpairs.json"), now=0).asset_pairs(["XBTEUR", "DOGEEUR"])


def test_kraken_error_typed():
    body = {"error": ["EQuery:Unknown asset pair"], "result": {}}
    calls = []

    def h(req):
        calls.append(1)
        return httpx.Response(200, json=body)

    with pytest.raises(KrakenError) as ei:
        kraken(h, now=0).ohlc("X/EUR", "FOOEUR")
    assert ei.value.errors == ["EQuery:Unknown asset pair"]
    assert len(calls) == 1  # permanent error: no retry


def test_transient_kraken_error_is_retried():
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        if n["i"] < 3:
            return httpx.Response(200, json={"error": ["EService:Unavailable"], "result": {}})
        return httpx.Response(200, content=fx("kraken_ticker.json"))

    assert kraken(h, now=1).ticker("BTC/EUR", "XBTEUR").ask == 67_181_100_000
    assert n["i"] == 3


def test_retry_on_5xx_then_success():
    ft = FakeTime()
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        return httpx.Response(503) if n["i"] < 3 else httpx.Response(200, content=fx("kraken_ticker.json"))

    c = KrakenClient(make_http(h, ft), now=lambda: 1)
    assert c.ticker("BTC/EUR", "XBTEUR").bid == 67_181_000_000
    assert n["i"] == 3
    assert 1.0 in ft.sleeps and 2.0 in ft.sleeps  # exponential backoff


def test_retry_exhausted_after_3_attempts():
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        return httpx.Response(500)

    with pytest.raises(DataError, match="500"):
        kraken(h, now=1).ticker("BTC/EUR", "XBTEUR")
    assert n["i"] == 3


def test_no_retry_on_4xx():
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        return httpx.Response(404)

    with pytest.raises(DataError, match="404"):
        kraken(h, now=1).ticker("BTC/EUR", "XBTEUR")
    assert n["i"] == 1


def test_retry_on_network_error():
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        if n["i"] == 1:
            raise httpx.ConnectTimeout("timeout")
        return httpx.Response(200, content=fx("kraken_ticker.json"))

    assert kraken(h, now=1).ticker("BTC/EUR", "XBTEUR").ask > 0
    assert n["i"] == 2


def test_limit_1_request_per_second():
    ft = FakeTime()
    http = make_http(ok("kraken_ticker.json"), ft)
    c = KrakenClient(http, now=lambda: 1)
    c.ticker("BTC/EUR", "XBTEUR")
    c.ticker("BTC/EUR", "XBTEUR")
    assert ft.sleeps and ft.sleeps[0] == pytest.approx(1.0)


# --- Binance ---------------------------------------------------------------------------------

KL = json.loads(fx("binance_klines.json"))


def test_binance_excludes_current_day_and_converts():
    now = KL[-1][6] // 1000 - 100  # the last day is not over
    c = BinanceClient(make_http(ok("binance_klines.json")), now=lambda: now)
    bars = c.klines_1d("BTCUSDT")
    assert len(bars) == len(KL) - 1
    b = bars[0]
    assert b.ts == KL[0][0] // 1000
    assert b.close == 75_867_590_000 and b.volume == 521_590_597_000 and b.taker_buy_base == 265_902_676_000


def test_binance_finished_day_included():
    c = BinanceClient(make_http(ok("binance_klines.json")), now=lambda: KL[-1][6] // 1000 + 5)
    assert len(c.klines_1d("BTCUSDT")) == len(KL)


# --- Cache -----------------------------------------------------------------------------------


def bar(ts: int, close: int = 100) -> Bar:
    return Bar("BTC/EUR", H4, ts, close, close, close, close, 1)


def test_store_dedup(tmp_path):
    s = BarStore(tmp_path, "kraken")
    assert s.add("BTC/EUR", H4, [bar(0), bar(H4)]) == 2
    assert s.add("BTC/EUR", H4, [bar(H4, 999), bar(2 * H4)]) == 1
    lines = s.path("BTC/EUR", H4).read_text().splitlines()
    assert len(lines) == 3
    assert s.load("BTC/EUR", H4, 10 * H4)[1].close == 100  # the existing one wins
    assert s.path("BTC/EUR", H4) == tmp_path / "kraken" / "BTC-EUR_4h.jsonl"


def test_store_update_incremental(tmp_path):
    s = BarStore(tmp_path, "kraken")
    sinces = []

    def fetch(since):
        sinces.append(since)
        return [bar(0), bar(H4)] if since is None else [bar(H4), bar(2 * H4)]

    assert s.update("BTC/EUR", H4, fetch) == 2
    assert s.update("BTC/EUR", H4, fetch) == 1
    assert sinces == [None, H4]


def test_store_load_no_future_bar(tmp_path):
    s = BarStore(tmp_path, "kraken")
    s.add("BTC/EUR", H4, [bar(i * H4) for i in range(6)])
    for until in (0, 1, H4 - 1, H4, 3 * H4 + 5, 100 * H4):
        got = s.load("BTC/EUR", H4, until)
        assert all(b.ts + H4 <= until for b in got), until
    # bar opened at 3*H4 but not finished at until = 3*H4 + 5: excluded
    assert [b.ts for b in s.load("BTC/EUR", H4, 3 * H4 + 5)] == [0, H4, 2 * H4]
    assert s.load("ETH/EUR", H4, 10**9) == []


def test_store_gaps(tmp_path):
    s = BarStore(tmp_path, "kraken")
    s.add("BTC/EUR", H4, [bar(0), bar(H4), bar(4 * H4), bar(5 * H4)])
    assert s.gaps("BTC/EUR", H4, 6 * H4) == [2 * H4, 3 * H4]
    assert s.gaps("BTC/EUR", H4, 8 * H4) == [2 * H4, 3 * H4, 6 * H4, 7 * H4]
    assert s.gaps("BTC/EUR", H4, 6 * H4, from_ts=-H4) == [-H4, 2 * H4, 3 * H4]
    assert s.gaps("ETH/EUR", H4, 6 * H4) == []


def test_store_binance_roundtrip(tmp_path):
    s = BarStore(tmp_path, "binance")
    d = DayBar("BTCUSDT", 86400, 1, 2, 3)
    s.add("BTCUSDT", 86400, [d])
    assert s.load("BTCUSDT", 86400, 2 * 86400) == [d]
    assert s.path("BTCUSDT", 86400).name == "BTCUSDT_1d.jsonl"


def test_store_corrupted_line(tmp_path):
    s = BarStore(tmp_path, "kraken")
    s.add("BTC/EUR", H4, [bar(0)])
    with s.path("BTC/EUR", H4).open("a") as f:
        f.write('{"symbol": "BTC')
    with pytest.raises(DataError):
        s.load("BTC/EUR", H4, 10**9)


# --- Config ----------------------------------------------------------------------------------


def test_config_and_instruments_enriched():
    cfg = load_config(CONFIG)
    assert cfg.capital_ueur == 1_000_000_000 and cfg.interval_s == H4
    assert len(cfg.sha256) == 64 and len(cfg.instrument_refs) == 6
    assert cfg.models[0].daily_budget_uusd == 100_000 and cfg.models[2].price_out_uusd_per_mtok == 20_000_000
    assert (cfg.benchmarks.e0065.L, cfg.benchmarks.e0065.k, cfg.benchmarks.e0065.H) == (20, 3, 10)
    c = kraken(ok("kraken_assetpairs.json"), now=0)
    # the fixture covers only 3 of the 6 pairs: the enrichment must fail cleanly
    with pytest.raises(DataError):
        load_instruments(cfg, c)


def test_config_invalid(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('venue_mode = "paper"\n')
    with pytest.raises(ConfigError):
        load_config(p)


# --- Real network (public data, no key) -----------------------------------------------


@pytest.mark.network
def test_network_kraken_and_binance():
    import time

    http = RateLimitedHttp()
    k = KrakenClient(http)
    bars = k.ohlc("BTC/EUR", "XBTEUR")
    assert bars and bars[-1].ts + H4 <= time.time()
    q = k.ticker("BTC/EUR", "XBTEUR")
    assert 0 < q.bid <= q.ask
    cfg = load_config(CONFIG)
    inst = load_instruments(cfg, k)
    btc = inst[0]
    assert (btc.tick_ueur, btc.lot_min_qty, btc.cost_min_ueur) == (100_000, 6_000, 450_000)
    days = BinanceClient(http).klines_1d("BTCUSDT", limit=10)
    assert days and days[-1].ts + 86400 <= time.time()
    assert all(d.volume >= d.taker_buy_base > 0 for d in days)
