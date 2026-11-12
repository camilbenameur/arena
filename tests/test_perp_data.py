"""Perp league, step 1: Kraken Futures client, data store, config, collector. No network except `reseau`."""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from arene.data import DataError, RateLimitedHttp
from arene.data.kraken import KrakenClient
from arene.perp import collect as collect_mod
from arene.perp.collect import collect_once, data_root, gap_report, main, run_lock
from arene.perp.config import PerpConfigError, load_perp_config
from arene.perp.kraken_futures import CLOSE_GRACE_S, KrakenFuturesClient
from arene.perp.store import PerpDataStore, Series, TickerSnapshot, missing_steps
from arene.perp.types import BookSnapshot, Candle, FundingRate, FxQuote, OpenInterest, PerpTicker

FIX = Path(__file__).parent / "fixtures" / "perp"
CONFIG = Path(__file__).resolve().parent.parent / "config" / "perp.toml"
SYMBOLS = ["PF_XBTUSD", "PF_ETHUSD", "PF_SOLUSD", "PF_XRPUSD", "PF_LINKUSD", "PF_LTCUSD"]


def fx(name: str) -> bytes:
    return (FIX / name).read_bytes()


class FakeTime:
    def __init__(self) -> None:
        self.t = 1000.0

    def clock(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


def client_for(handler, now: float) -> KrakenFuturesClient:
    ft = FakeTime()
    http = RateLimitedHttp(
        httpx.Client(transport=httpx.MockTransport(handler)), sleep=ft.sleep, clock=ft.clock
    )
    return KrakenFuturesClient(http, now=lambda: now, spot=KrakenClient(http, now=lambda: now))


def route(table: dict[str, bytes]):
    def handler(req: httpx.Request) -> httpx.Response:
        for key, body in table.items():
            if key in req.url.path:
                return httpx.Response(200, content=body)
        return httpx.Response(404, content=b"{}")

    return handler


# ---------------------------------------------------------------------- client


def test_tickers_are_decimal_exact_and_filtered():
    c = client_for(route({"/tickers": fx("tickers.json")}), now=1794498210)
    out, problems = c.tickers(SYMBOLS)
    assert set(out) == set(SYMBOLS) and problems == {}  # PF_PENGUUSD and the FF_ contract are dropped
    raw = {t["symbol"]: t for t in json.loads(fx("tickers.json"))["tickers"]}
    xbt = out["PF_XBTUSD"]
    assert isinstance(xbt.mark_uusd, int) and xbt.bid_uusd <= xbt.ask_uusd
    # exact decimal conversion: µUSD rounded half-even from the literal, never through float
    from decimal import ROUND_HALF_EVEN, Decimal

    text = (FIX / "tickers.json").read_text()
    lit = text.split('"symbol": "PF_XBTUSD"')[1].split('"markPrice": ')[1].split(",")[0]
    assert xbt.mark_uusd == int((Decimal(lit) * 10**6).to_integral_value(ROUND_HALF_EVEN))
    assert xbt.ts == 1794498210
    assert raw["PF_XBTUSD"]["tag"] == "perpetual"


def test_tickers_partial_failure_keeps_healthy_ones():
    body = json.loads(fx("tickers.json"), parse_float=str)
    for tk in body["tickers"]:
        if tk["symbol"] == "PF_ETHUSD":
            del tk["bid"]  # a degraded contract
        if tk["symbol"] == "PF_SOLUSD":
            tk["suspended"] = "false"  # not a JSON boolean
    c = client_for(route({"/tickers": json.dumps(body).encode()}), now=1)
    out, problems = c.tickers(["PF_XBTUSD", "PF_ETHUSD", "PF_SOLUSD", "PF_NOPEUSD"])
    assert set(out) == {"PF_XBTUSD"}
    assert set(problems) == {"PF_ETHUSD", "PF_SOLUSD", "PF_NOPEUSD"}
    assert "absent" in problems["PF_NOPEUSD"] and "malformed" in problems["PF_ETHUSD"]


def test_unsuccessful_response_raises():
    c = client_for(route({"/tickers": b'{"result":"error","error":"x"}'}), now=1)
    with pytest.raises(DataError, match="unsuccessful"):
        c.tickers(["PF_XBTUSD"])


def test_instruments_margin_levels_in_ppm():
    c = client_for(route({"/instruments": fx("instruments.json")}), now=1)
    specs = c.instruments(SYMBOLS)
    xbt, ltc = specs["PF_XBTUSD"], specs["PF_LTCUSD"]
    assert xbt.margin_levels[0].initial_ppm == 10_000 and xbt.margin_levels[0].maintenance_ppm == 5_000
    assert ltc.margin_levels[0].initial_ppm == 20_000 and ltc.margin_levels[0].maintenance_ppm == 10_000
    assert [lv.threshold_uusd for lv in xbt.margin_levels] == sorted(
        lv.threshold_uusd for lv in xbt.margin_levels
    )
    assert xbt.tick_uusd == 1_000_000 and ltc.tick_uusd == 10_000
    assert ltc.max_relative_funding_e12 == 5_000_000_000  # 0.005 per hour


def test_funding_history_parsed_and_sorted():
    c = client_for(route({"/historical-funding-rates": fx("funding_xbt.json")}), now=1)
    rates = c.funding_history("PF_XBTUSD")
    assert len(rates) == 6 and [r.ts for r in rates] == sorted(r.ts for r in rates)
    assert all(r.ts % 3600 == 0 for r in rates)
    assert all(isinstance(r.funding_nusd, int) and isinstance(r.relative_funding_e12, int) for r in rates)


def _candles_payload(start_ms: int, n: int, more: bool) -> bytes:
    rows = [
        {
            "time": start_ms + i * 60_000,
            "open": "100.5",
            "high": "101",
            "low": "99.25",
            "close": "100",
            "volume": "1.5",
        }
        for i in range(n)
    ]
    return json.dumps({"candles": rows, "more_candles": more}).encode()


def test_candles_exclude_open_candle_and_window():
    body = fx("candles_mark_xbt.json")
    rows = json.loads(body)["candles"]
    last_ts = rows[-1]["time"] // 1000
    c = client_for(route({"/charts/v1/mark/": body}), now=last_ts + 30)  # last candle still open
    out = c.candles("mark", "PF_XBTUSD", 60, rows[0]["time"] // 1000, last_ts + 60)
    assert out and out[-1].ts + 60 <= last_ts + 30
    assert all(x.kind == "mark" and x.interval_s == 60 for x in out)
    assert out[0].low <= out[0].open <= out[0].high


def test_candles_pagination_advances():
    calls: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        frm = int(req.url.params["from"])
        calls.append(dict(req.url.params))
        if frm == 0:
            return httpx.Response(200, content=_candles_payload(0, 3, True))
        return httpx.Response(200, content=_candles_payload(frm * 1000, 2, False))

    c = client_for(handler, now=10_000)
    out = c.candles("trade", "PF_XBTUSD", 60, 0, 300)
    assert [x.ts for x in out] == [0, 60, 120, 180, 240]
    assert [int(x["from"]) for x in calls] == [0, 180]
    assert out[0].open == 100_500_000 and out[0].volume_qty == 150_000_000


def test_candles_pagination_that_does_not_advance_raises():
    c = client_for(lambda req: httpx.Response(200, content=_candles_payload(0, 1, True)), now=10_000)
    with pytest.raises(DataError, match="does not advance"):
        c.candles("trade", "PF_XBTUSD", 60, 120, 600)


def test_candles_reject_bad_kind_and_interval():
    c = client_for(route({}), now=1)
    with pytest.raises(ValueError):
        c.candles("index", "PF_XBTUSD", 60, 0, 60)
    with pytest.raises(ValueError):
        c.candles("mark", "PF_XBTUSD", 7, 0, 60)


def test_open_interest_closed_only_and_misaligned_raises():
    body = fx("oi_xbt.json")
    stamps = json.loads(body)["result"]["timestamp"]
    c = client_for(route({"/open-interest": body}), now=stamps[-1] + 20)
    out = c.open_interest("PF_XBTUSD", 3600, stamps[0])
    assert [o.ts for o in out] == [ts for ts in stamps if ts + 3600 <= stamps[-1] + 20 - CLOSE_GRACE_S]
    assert out  # the previous hour is closed and older than the grace
    bad = json.dumps(
        {"result": {"timestamp": [0, 3600], "data": [["1", "1", "1", "1"]], "more": False}, "errors": []}
    )
    c2 = client_for(route({"/open-interest": bad.encode()}), now=10_000)
    with pytest.raises(DataError, match="misaligned"):
        c2.open_interest("PF_XBTUSD", 3600, 0)


def test_order_book_sorted_truncated_and_crossed_flag():
    c = client_for(route({"/orderbook": fx("orderbook_xbt.json")}), now=5)
    b = c.order_book("PF_XBTUSD", 10)
    assert len(b.bids) == 10 and len(b.asks) == 10
    assert [p for p, _ in b.bids] == sorted((p for p, _ in b.bids), reverse=True)
    assert [p for p, _ in b.asks] == sorted(p for p, _ in b.asks)
    assert b.crossed is False
    crossed = {"result": "success", "orderBook": {"bids": [[101, 1]], "asks": [[100, 1]]}}
    c2 = client_for(route({"/orderbook": json.dumps(crossed).encode()}), now=5)
    assert c2.order_book("PF_XBTUSD", 10).crossed is True
    empty = {"result": "success", "orderBook": {"bids": [], "asks": [[100, 1]]}}
    c3 = client_for(route({"/orderbook": json.dumps(empty).encode()}), now=5)
    with pytest.raises(DataError, match="empty"):
        c3.order_book("PF_XBTUSD", 10)


def test_eurusd_from_spot():
    c = client_for(route({"/0/public/Ticker": fx("eurusd.json")}), now=77)
    q = c.eurusd()
    assert q.ts == 77 and 0 < q.bid_uusd_per_eur <= q.ask_uusd_per_eur
    assert q.bid_uusd_per_eur > 1_000_000  # more than one dollar per euro in the fixture


def test_numbers_are_never_parsed_as_float():
    # 20 significant digits: a float would round them; Decimal parsing keeps the exact integer.
    body = (
        b'{"result":"success","tickers":[{"symbol":"PF_XBTUSD","bid":1,"ask":2,"markPrice":1.5,'
        b'"openInterest":123456789012.12345678,"fundingRate":0.000000001500000000001}]}'
    )
    c = client_for(route({"/tickers": body}), now=1)
    out, _ = c.tickers(["PF_XBTUSD"])
    assert out["PF_XBTUSD"].open_interest_qty == 12_345_678_901_212_345_678
    assert (
        out["PF_XBTUSD"].funding_nusd == 2
    )  # 1.500000000001 nano-USD rounds half-even to 2, float gives 1.5
    ft = FakeTime()
    http = RateLimitedHttp(
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b'{"x": 0.1}'))),
        sleep=ft.sleep,
        clock=ft.clock,
    )
    assert isinstance(http.get_json("https://example.org/", parse_float=Decimal)["x"], Decimal)


def test_candle_guards():
    c = client_for(
        lambda r: httpx.Response(
            200,
            content=b'{"candles":[{"time":61500,"open":"1","high":"1",'
            b'"low":"1","close":"1","volume":"0"}],"more_candles":false}',
        ),
        now=10_000,
    )
    with pytest.raises(DataError, match="not on a second"):
        c.candles("mark", "PF_XBTUSD", 60, 0, 600)
    rows = [
        {"time": ms, "open": "1", "high": "1", "low": "1", "close": "1"} for ms in (60_000, 90_000, 120_000)
    ]
    c2 = client_for(lambda r: httpx.Response(200, content=json.dumps({"candles": rows}).encode()), now=10_000)
    out = c2.candles("mark", "PF_XBTUSD", 60, 0, 600)
    assert [x.ts for x in out] == [60, 120] and c2.misaligned_rows == 1
    broken = [{"time": 60_000, "open": "1", "high": "1", "low": "1"}]  # no close
    c3 = client_for(
        lambda r: httpx.Response(200, content=json.dumps({"candles": broken}).encode()), now=10_000
    )
    with pytest.raises(DataError, match="malformed"):
        c3.candles("mark", "PF_XBTUSD", 60, 0, 600)


def test_funding_timestamp_without_zone_is_rejected():
    body = b'{"result":"success","rates":[{"timestamp":"2026-11-12T16:00:00","fundingRate":1,"relativeFundingRate":1}]}'
    c = client_for(route({"/historical-funding-rates": body}), now=1)
    with pytest.raises(DataError, match="time zone"):
        c.funding_history("PF_XBTUSD")


def test_order_book_unsorted_and_zero_levels():
    book = {
        "result": "success",
        "orderBook": {"bids": [[99, 1], [100, 0], [98, 2], [101, 3]], "asks": [[103, 1], [102, 0.5]]},
    }
    c = client_for(route({"/orderbook": json.dumps(book).encode()}), now=5)
    b = c.order_book("PF_XBTUSD", 2)
    assert b.bids == ((101_000_000, 300_000_000), (99_000_000, 100_000_000))  # zero-qty level dropped
    assert b.asks[0][0] == 102_000_000


def test_eurusd_incoherent_quote_raises():
    body = b'{"error":[],"result":{"ZEURZUSD":{"a":["1.10","1","1"],"b":["1.20","1","1"]}}}'
    c = client_for(route({"/0/public/Ticker": body}), now=1)
    with pytest.raises(DataError, match="incoherent"):
        c.eurusd()


# ---------------------------------------------------------------------- store


def _candle(ts: int, close: int = 100) -> Candle:
    return Candle("PF_XBTUSD", "mark", 60, ts, close, close, close, close, 0)


def test_series_dedup_first_wins_and_shards(tmp_path):
    st = PerpDataStore(tmp_path)
    s = st.candles("mark", "PF_XBTUSD", 60)
    day = 86400 * 20000
    assert s.add([_candle(day - 60), _candle(day), _candle(day + 60)]) == 3
    assert s.add([_candle(day, close=999)]) == 0  # never overwritten
    assert s.load(day, day + 1)[0].close == 100
    assert len(list(s.dir.glob("*.jsonl"))) == 2  # two UTC days
    assert s.last_ts() == day + 60 and s.first_ts() == day - 60


def test_closed_candles_never_return_open_candle(tmp_path):
    st = PerpDataStore(tmp_path)
    st.candles("mark", "PF_XBTUSD", 60).add([_candle(0), _candle(60), _candle(120)])
    assert [c.ts for c in st.closed_candles("mark", "PF_XBTUSD", 60, 0, 150)] == [0, 60]
    assert [c.ts for c in st.closed_candles("mark", "PF_XBTUSD", 60, 0, 180)] == [0, 60, 120]


def test_corrupt_line_is_quarantined_and_series_keeps_working(tmp_path):
    warnings: list[str] = []
    s = Series(tmp_path / "x", FundingRate.from_dict, lambda ts: "shard", warnings)
    s.add([FundingRate("PF_XBTUSD", 3600, 1, 1)])
    with (tmp_path / "x" / "shard.jsonl").open("a", encoding="utf-8") as f:
        f.write('{"ts": 7200, "kraken_sym')  # an append in progress (no newline yet): ignored, not corruption
    assert s.last_ts() == 3600 and not warnings
    with (tmp_path / "x" / "shard.jsonl").open("a", encoding="utf-8") as f:
        f.write("\n")  # the torn line is now complete and unreadable: quarantined
    assert s.last_ts() == 3600
    assert (tmp_path / "x" / "shard.jsonl.corrupt-1").exists() and len(warnings) == 1
    assert s.add([FundingRate("PF_XBTUSD", 7200, 2, 2)]) == 1
    assert [r.ts for r in s.load(0, 10_000)] == [3600, 7200] and len(warnings) == 1


def test_append_only_keeps_existing_lines(tmp_path):
    s = PerpDataStore(tmp_path).candles("mark", "PF_XBTUSD", 60)
    s.add([_candle(120), _candle(0)])
    shard = next(s.dir.glob("*.jsonl"))
    before = shard.read_text(encoding="utf-8")
    s.add([_candle(60)])
    after = shard.read_text(encoding="utf-8")
    assert after.startswith(before) and after.count("\n") == 3
    assert [c.ts for c in s.load(0, 1000)] == [0, 60, 120]


@pytest.mark.parametrize("series_kind", ["day", "month"])
def test_shard_boundaries(tmp_path, series_kind):
    st = PerpDataStore(tmp_path)
    if series_kind == "day":
        s = st.candles("mark", "PF_XBTUSD", 60)
        edge = 86400 * 20_400  # a UTC midnight
        recs = [_candle(edge - 60), _candle(edge), _candle(edge + 60)]
    else:
        s = st.funding("PF_XBTUSD")
        edge = 1_793_491_200  # 2026-11-01T00:00:00Z
        recs = [FundingRate("PF_XBTUSD", ts, 1, 1) for ts in (edge - 3600, edge, edge + 3600)]
    s.add(recs)
    assert len(list(s.dir.glob("*.jsonl"))) == 2
    assert [r.ts for r in s.load(edge - 3600, edge)] == [recs[0].ts]  # until on the boundary excludes it
    assert [r.ts for r in s.load(edge, edge + 1)] == [edge]
    assert s.first_ts() == recs[0].ts and s.last_ts() == recs[2].ts


def test_round_trips(tmp_path):
    st = PerpDataStore(tmp_path)
    book = BookSnapshot("PF_XBTUSD", 5, ((2, 3), (1, 4)), ((5, 6),), False)
    st.books("PF_XBTUSD").add([book])
    assert st.books("PF_XBTUSD").load(0, 10) == [book]
    tick = PerpTicker("PF_XBTUSD", 5, 1, 2, 3, None, None, None, None, None, None, None, False, False)
    snap = TickerSnapshot(5, (tick,), FxQuote(5, 1_100_000, 1_100_010))
    st.tickers().add([snap])
    assert st.tickers().load(0, 10) == [snap]
    oi = OpenInterest("PF_XBTUSD", 3600, 0, 1, 2, 0, 1)
    st.open_interest("PF_XBTUSD", 3600).add([oi])
    assert st.open_interest("PF_XBTUSD", 3600).load(0, 1) == [oi]


def test_missing_steps():
    assert missing_steps([0, 60, 180], 60, 0, 240) == [120]
    assert missing_steps([], 60, 30, 150) == [60, 120]


# ---------------------------------------------------------------------- config


def test_config_loads():
    cfg = load_perp_config(CONFIG)
    assert [i.kraken_symbol for i in cfg.instruments] == SYMBOLS
    assert cfg.venue_mode == "paper" and len(cfg.sha256) == 64


@pytest.mark.parametrize(
    "edit, match",
    [
        (lambda t: t.replace('venue_mode = "paper"', 'venue_mode = "live"'), "paper"),
        (lambda t: "surprise = 1\n" + t, "unknown"),
        (lambda t: t.replace('kraken_symbol = "PF_LTCUSD"', 'kraken_symbol = "PI_LTCUSD"'), "linear"),
        (lambda t: t.replace('kraken_symbol = "PF_LTCUSD"', 'kraken_symbol = "PF_XBTUSD"'), "duplicate"),
        (lambda t: t.replace("book_depth = 10", "book_depth = 0"), "positive"),
        (lambda t: t.replace("candle_interval_s = 60", "candle_interval_s = 7"), "Kraken"),
        (
            lambda t: t.replace('candle_kinds = ["mark", "trade", "spot"]', 'candle_kinds = ["last"]'),
            "subset",
        ),
    ],
)
def test_config_rejects(tmp_path, edit, match):
    p = tmp_path / "perp.toml"
    p.write_text(edit(CONFIG.read_text(encoding="utf-8")), encoding="utf-8")
    with pytest.raises(PerpConfigError, match=match):
        load_perp_config(p)


# ---------------------------------------------------------------------- collector


class FakeClient:
    """Stands in for KrakenFuturesClient: deterministic data, failures on demand, call log."""

    def __init__(self, now: int, fail: set[str] | None = None) -> None:
        self.now = now
        self.fail = fail or set()
        self.calls: list[tuple] = []

    def _maybe_fail(self, key: str) -> None:
        if key in self.fail:
            raise DataError(f"injected failure {key}")

    def tickers(self, symbols):
        self.calls.append(("tickers",))
        self._maybe_fail("tickers")
        ok = {s: PerpTicker(s, self.now, 1, 2, 1, 1, 1, 0, 0, 0, 0, 0, False, False) for s in symbols}
        return {s: v for s, v in ok.items() if f"ticker {s}" not in self.fail}, {
            s: "injected" for s in symbols if f"ticker {s}" in self.fail
        }

    def eurusd(self, pair="EURUSD"):
        self.calls.append(("fx",))
        self._maybe_fail("fx")
        return FxQuote(self.now, 1_100_000, 1_100_020)

    def candles(self, kind, sym, iv, from_ts, to_ts):
        self.calls.append(("candles", kind, sym, from_ts, to_ts))
        self._maybe_fail(f"candles {sym}")
        if f"keyerror {sym}" in self.fail:
            raise KeyError("close")
        top = min(to_ts, self.now - 15)
        return [Candle(sym, kind, iv, ts, 1, 1, 1, 1, 0) for ts in range(from_ts, top - iv + 1, iv)]

    def funding_history(self, sym):
        self.calls.append(("funding", sym))
        self._maybe_fail(f"funding {sym}")
        top = self.now // 3600 * 3600  # like Kraken: the stamp of the current hour exists from that hour
        return [FundingRate(sym, ts, 1, 1) for ts in range(top - 48 * 3600, top + 1, 3600)]

    def open_interest(self, sym, iv, since):
        self.calls.append(("oi", sym, since))
        return [OpenInterest(sym, iv, ts, 1, 1, 1, 1) for ts in range(since, self.now - 15 - iv + 1, iv)]

    def order_book(self, sym, depth):
        self.calls.append(("book", sym))
        return BookSnapshot(sym, self.now, ((1, 1),), ((2, 1),), False)


NOW = 1_794_499_200  # a round hour (2026-11-12T16:00:00Z)
EXPECTED_CANDLES_1H = 59  # [NOW - 3600, NOW - 120]: the minute ending at NOW is still within the grace


def test_collect_once_full_run(tmp_path):
    cfg = load_perp_config(CONFIG)
    st = PerpDataStore(data_root(tmp_path))
    r = collect_once(cfg, FakeClient(NOW), st, tmp_path, NOW, backfill_s=3600)
    assert r.ok, r.errors
    for kind in ("mark", "trade", "spot"):
        assert r.counts[f"candles_{kind}"] == 6 * EXPECTED_CANDLES_1H
    assert r.counts["tickers"] == 1 and r.counts["books"] == 6
    assert r.counts["funding"] == 6 * 49  # the first call stores the whole history returned
    snaps = st.tickers().load(0, NOW + 1)
    assert len(snaps) == 1 and snaps[0].fx is not None and len(snaps[0].tickers) == 6
    assert json.loads((tmp_path / "collect_state.json").read_text())["funding_attempt"]["PF_XBTUSD"] == NOW


def test_collect_is_incremental(tmp_path):
    cfg = load_perp_config(CONFIG)
    st = PerpDataStore(data_root(tmp_path))
    collect_once(cfg, FakeClient(NOW), st, tmp_path, NOW, backfill_s=3600)
    later = NOW + 300
    fc = FakeClient(later)
    r = collect_once(cfg, fc, st, tmp_path, later)
    assert r.ok, r.errors
    assert {c[3] for c in fc.calls if c[0] == "candles"} == {NOW - 60}  # right after the last stored one
    assert r.counts["candles_mark"] == 6 * 5
    assert not [c for c in fc.calls if c[0] == "funding"]  # no new funding stamp is due


def test_funding_due_at_each_hour_stamp(tmp_path):
    cfg = load_perp_config(CONFIG)
    st = PerpDataStore(data_root(tmp_path))
    collect_once(cfg, FakeClient(NOW), st, tmp_path, NOW, backfill_s=3600)
    fc = FakeClient(NOW + 3599)
    collect_once(cfg, fc, st, tmp_path, NOW + 3599, backfill_s=3600)
    assert not [c for c in fc.calls if c[0] == "funding"]  # the stamp NOW + 1 h does not exist yet
    fc = FakeClient(NOW + 3600 + 60)
    r = collect_once(cfg, fc, st, tmp_path, NOW + 3660, backfill_s=3600)
    assert len([c for c in fc.calls if c[0] == "funding"]) == 6 and r.counts["funding"] == 6
    assert st.funding("PF_XBTUSD").last_ts() == NOW + 3600


def test_collect_funding_retry_throttled(tmp_path):
    cfg = load_perp_config(CONFIG)
    st = PerpDataStore(data_root(tmp_path))
    failing = {f"funding {s}" for s in SYMBOLS}
    r = collect_once(cfg, FakeClient(NOW, fail=failing), st, tmp_path, NOW, backfill_s=3600)
    assert sum(e.endswith("injected failure funding " + e.split()[0]) for e in r.errors) == 6
    fc2 = FakeClient(NOW + 300, fail=failing)
    collect_once(cfg, fc2, st, tmp_path, NOW + 300, backfill_s=3600)
    assert not [c for c in fc2.calls if c[0] == "funding"]  # retried at most every 15 min
    fc3 = FakeClient(NOW + cfg.funding_retry_s)
    r3 = collect_once(cfg, fc3, st, tmp_path, NOW + cfg.funding_retry_s, backfill_s=3600)
    assert len([c for c in fc3.calls if c[0] == "funding"]) == 6 and r3.counts["funding"] > 0


def test_collect_isolates_errors_of_any_kind(tmp_path):
    cfg = load_perp_config(CONFIG)
    st = PerpDataStore(data_root(tmp_path))
    fail = {"candles PF_SOLUSD", "fx", "keyerror PF_ETHUSD", "ticker PF_LTCUSD"}
    r = collect_once(cfg, FakeClient(NOW, fail=fail), st, tmp_path, NOW, backfill_s=3600)
    assert not r.ok
    assert any(e.startswith("PF_SOLUSD candles mark: DataError") for e in r.errors)
    assert any(e.startswith("PF_ETHUSD candles mark: KeyError") for e in r.errors)
    assert any(e.startswith("fx:") for e in r.errors) and any(
        e.startswith("PF_LTCUSD ticker") for e in r.errors
    )
    assert r.counts["candles_mark"] == 4 * EXPECTED_CANDLES_1H  # the four others are collected
    assert r.counts["books"] == 6  # later steps of the failing instruments still run
    snap = st.tickers().load(0, NOW + 1)[0]
    assert snap.fx is None and len(snap.tickers) == 5  # partial snapshot kept


def test_outage_longer_than_backfill_is_reported(tmp_path):
    cfg = load_perp_config(CONFIG)
    st = PerpDataStore(data_root(tmp_path))
    collect_once(cfg, FakeClient(NOW + 60), st, tmp_path, NOW + 60, backfill_s=7200)
    assert st.open_interest("PF_XBTUSD", 3600).last_ts() == NOW - 3600
    later = NOW + 10 * 86400
    r = collect_once(cfg, FakeClient(later), st, tmp_path, later)
    holes = [e for e in r.errors if "hole of" in e]
    assert len(holes) == 6 * 3 + 6  # every candle series and every open-interest series
    assert st.candles("mark", "PF_XBTUSD", 60).last_ts() is not None


def test_explicit_backfill_also_fetches_backwards(tmp_path):
    cfg = load_perp_config(CONFIG)
    st = PerpDataStore(data_root(tmp_path))
    collect_once(cfg, FakeClient(NOW), st, tmp_path, NOW, backfill_s=600)
    first = st.candles("mark", "PF_XBTUSD", 60).first_ts()
    fc = FakeClient(NOW + 60)
    r = collect_once(cfg, fc, st, tmp_path, NOW + 60, backfill_s=7200)
    backwards = [c for c in fc.calls if c[0] == "candles" and c[4] == first]
    assert len(backwards) == 18 and r.counts["candles_mark_backfill"] > 0
    assert st.candles("mark", "PF_XBTUSD", 60).first_ts() == NOW + 60 - 7200


def test_run_deadline_applies_to_timer_runs_only(tmp_path):
    cfg = load_perp_config(CONFIG)
    ticks = iter(range(0, 10**9, 400))  # every clock() call advances 400 s
    r = collect_once(
        cfg, FakeClient(NOW), PerpDataStore(data_root(tmp_path)), tmp_path, NOW, clock=lambda: next(ticks)
    )
    assert any("run deadline" in e for e in r.errors)
    ticks2 = iter(range(0, 10**9, 400))
    r2 = collect_once(
        cfg,
        FakeClient(NOW),
        PerpDataStore(data_root(tmp_path / "b")),
        tmp_path / "b",
        NOW,
        backfill_s=3600,
        clock=lambda: next(ticks2),
    )
    assert not any("run deadline" in e for e in r2.errors) and r2.counts["books"] == 6


def test_collect_rejects_backfill_out_of_bounds(tmp_path):
    cfg = load_perp_config(CONFIG)
    with pytest.raises(ValueError):
        collect_once(
            cfg, FakeClient(NOW), PerpDataStore(tmp_path), tmp_path, NOW, backfill_s=cfg.max_backfill_s + 1
        )


def test_run_lock_is_exclusive(tmp_path):
    with run_lock(tmp_path) as first:
        assert first
        with run_lock(tmp_path) as second:
            assert not second


def test_gap_report_counts_real_holes(tmp_path):
    cfg = load_perp_config(CONFIG)
    st = PerpDataStore(data_root(tmp_path))
    collect_once(cfg, FakeClient(NOW), st, tmp_path, NOW, backfill_s=3600)
    # a hole in mark candles, a missing funding hour, a crossed book, a run without fx 20 min later
    mark = st.candles("mark", "PF_XBTUSD", 60)
    shard = next(mark.dir.glob("*.jsonl"))
    lines = [ln for ln in shard.read_text().splitlines() if f'"ts":{NOW - 600},' not in ln]
    shard.write_text("\n".join(lines) + "\n")
    fund = st.funding("PF_ETHUSD")
    fshard = next(fund.dir.glob("*.jsonl"))
    flines = [ln for ln in fshard.read_text().splitlines() if json.loads(ln)["ts"] != NOW - 7200]
    fshard.write_text("\n".join(flines) + "\n")
    st.books("PF_XBTUSD").add([BookSnapshot("PF_XBTUSD", NOW + 1, ((2, 1),), ((1, 1),), True)])
    st.tickers().add([TickerSnapshot(NOW + 1200, (), None)])
    rep = gap_report(cfg, st, tmp_path, NOW + 1300, 1)
    x = rep["instruments"]["PF_XBTUSD"]
    assert (
        x["candles_mark"]["missing"] >= 1 and rep["instruments"]["PF_SOLUSD"]["candles_mark"]["missing"] > 0
    )
    assert rep["instruments"]["PF_ETHUSD"]["funding"]["missing"] == 1
    assert x["crossed_books"] == 1 and rep["snapshots_without_fx"] == 1
    assert rep["max_gap_between_runs_s"] == 1200 and rep["missing_run_slots"] == 3
    assert rep["seconds_since_last_run"] == 100


def test_gap_report_empty_series_counts_as_missing(tmp_path):
    cfg = load_perp_config(CONFIG)
    rep = gap_report(cfg, PerpDataStore(data_root(tmp_path)), tmp_path, NOW, 1)
    row = rep["instruments"]["PF_XBTUSD"]["candles_mark"]
    assert row["empty"] is True and row["missing"] > 1000
    assert rep["ticker_snapshots"] == 0 and rep["seconds_since_last_run"] is None


def test_main_run_writes_runs_journal_and_exit_codes(tmp_path, capsys):
    ok = main(["run", "--var", str(tmp_path)], client_factory=lambda: FakeClient(int(time.time())))
    assert ok == 0
    partial = main(
        ["run", "--var", str(tmp_path)], client_factory=lambda: FakeClient(int(time.time()), fail={"fx"})
    )
    assert partial == 3
    lines = [json.loads(x) for p in (tmp_path / "runs").glob("*.jsonl") for x in p.read_text().splitlines()]
    assert [x["ok"] for x in lines] == [True, False]
    assert (tmp_path / "collect_state.json").exists()


def test_main_run_crash_is_recorded_and_raises(tmp_path):
    class Boom(FakeClient):
        def order_book(self, sym, depth):
            raise RuntimeError("unexpected")

    with pytest.raises(RuntimeError):
        main(["run", "--var", str(tmp_path)], client_factory=lambda: Boom(int(time.time())))
    lines = [json.loads(x) for p in (tmp_path / "runs").glob("*.jsonl") for x in p.read_text().splitlines()]
    assert len(lines) == 1 and lines[0]["crash"].startswith("RuntimeError")


def test_main_report_on_empty_store(tmp_path, capsys):
    assert main(["report", "--var", str(tmp_path), "--days", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["ticker_snapshots"] == 0


def test_main_run_with_busy_lock(tmp_path, capsys, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not collect while the lock is held")

    monkeypatch.setattr(collect_mod, "collect_once", boom)
    with run_lock(tmp_path.resolve()):
        assert main(["run", "--var", str(tmp_path)]) == 0
    assert "lock busy" in capsys.readouterr().out
    assert "lock busy" in next((tmp_path / "runs").glob("*.jsonl")).read_text()


def test_main_rejects_bad_backfill(tmp_path):
    assert main(["run", "--var", str(tmp_path), "--backfill-days", "0"]) == 2


def test_main_refuses_the_spot_state_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENE_VAR", str(tmp_path))
    assert main(["run", "--var", str(tmp_path)]) == 2
    assert main(["report", "--var", str(tmp_path / "sub")]) == 2


@pytest.mark.reseau
def test_live_public_api_smoke():
    c = KrakenFuturesClient()
    t, problems = c.tickers(SYMBOLS)
    assert problems == {} and set(t) == set(SYMBOLS)
    assert all(x.bid_uusd > 0 and x.ask_uusd >= x.bid_uusd for x in t.values())
    assert c.eurusd().bid_uusd_per_eur > 0
