"""Tests du module de données : sans réseau (transport httpx mocké, fixtures enregistrées) sauf `reseau`."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from arene.config import ConfigError, load_config, load_instruments
from arene.data import DataError, RateLimitedHttp, to_qty, to_ueur
from arene.data.binance import BinanceClient, DayBar
from arene.data.kraken import KrakenClient, KrakenError
from arene.data.store import BarStore
from arene.types import Bar

FIX = Path(__file__).parent / "fixtures"
CONFIG = Path(__file__).resolve().parent.parent / "config" / "arene.toml"
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


def test_conversion_exacte():
    assert to_ueur("56622.4") == 56_622_400_000
    assert to_qty("130.20355035") == 13_020_355_035
    assert to_ueur("0.00001") == 10
    assert to_ueur("67181.10000") == 67_181_100_000
    with pytest.raises(DataError):
        to_ueur("abc")


# --- Kraken ----------------------------------------------------------------------------------


def test_ohlc_exclut_barre_en_cours():
    c = kraken(ok("kraken_ohlc.json"), now=LAST_TS + 3600)
    bars = c.ohlc("BTC/EUR", "XBTEUR")
    assert len(bars) == len(OHLC_ROWS) - 1
    assert all(b.ts < LAST_TS for b in bars)
    assert [b.ts for b in bars] == sorted(b.ts for b in bars)


def test_ohlc_garde_derniere_barre_si_close():
    c = kraken(ok("kraken_ohlc.json"), now=LAST_TS + H4)
    assert len(c.ohlc("BTC/EUR", "XBTEUR")) == len(OHLC_ROWS)


def test_ohlc_conversion_champs():
    c = kraken(ok("kraken_ohlc.json"), now=LAST_TS + H4)
    b = c.ohlc("BTC/EUR", "XBTEUR")[-1]
    assert b == Bar(
        "BTC/EUR", H4, LAST_TS, 66_593_700_000, 67_350_400_000, 66_548_000_000, 67_182_700_000, 5_089_968_857
    )


def test_ohlc_parametres_requete():
    seen = {}

    def h(req: httpx.Request) -> httpx.Response:
        seen.update(req.url.params)
        return httpx.Response(200, content=fx("kraken_ohlc.json"))

    kraken(h, now=LAST_TS).ohlc("BTC/EUR", "XBTEUR", since=123)
    assert seen == {"pair": "XBTEUR", "interval": "240", "since": "123"}


def test_ticker_quote():
    q = kraken(ok("kraken_ticker.json"), now=1_800_000_000).ticker("BTC/EUR", "XBTEUR")
    assert (q.symbol, q.ts, q.ask, q.bid) == ("BTC/EUR", 1_800_000_000, 67_181_100_000, 67_181_000_000)


def test_asset_pairs_entiers():
    p = kraken(ok("kraken_assetpairs.json"), now=0).asset_pairs(["XBTEUR", "ETHEUR", "XRPEUR"])
    assert (p["XBTEUR"].tick_ueur, p["XBTEUR"].lot_min_qty, p["XBTEUR"].cost_min_ueur) == (
        100_000,
        6_000,
        450_000,
    )
    assert p["ETHEUR"].tick_ueur == 10_000 and p["ETHEUR"].lot_min_qty == 200_000
    assert p["XRPEUR"].tick_ueur == 10 and p["XRPEUR"].lot_min_qty == 400_000_000


def test_asset_pairs_paire_absente():
    with pytest.raises(DataError, match="absentes"):
        kraken(ok("kraken_assetpairs.json"), now=0).asset_pairs(["XBTEUR", "DOGEEUR"])


def test_erreur_kraken_typee():
    body = {"error": ["EQuery:Unknown asset pair"], "result": {}}
    calls = []

    def h(req):
        calls.append(1)
        return httpx.Response(200, json=body)

    with pytest.raises(KrakenError) as ei:
        kraken(h, now=0).ohlc("X/EUR", "FOOEUR")
    assert ei.value.errors == ["EQuery:Unknown asset pair"]
    assert len(calls) == 1  # erreur définitive : pas de nouvelle tentative


def test_erreur_kraken_passagere_reessayee():
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        if n["i"] < 3:
            return httpx.Response(200, json={"error": ["EService:Unavailable"], "result": {}})
        return httpx.Response(200, content=fx("kraken_ticker.json"))

    assert kraken(h, now=1).ticker("BTC/EUR", "XBTEUR").ask == 67_181_100_000
    assert n["i"] == 3


def test_retry_sur_5xx_puis_succes():
    ft = FakeTime()
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        return httpx.Response(503) if n["i"] < 3 else httpx.Response(200, content=fx("kraken_ticker.json"))

    c = KrakenClient(make_http(h, ft), now=lambda: 1)
    assert c.ticker("BTC/EUR", "XBTEUR").bid == 67_181_000_000
    assert n["i"] == 3
    assert 1.0 in ft.sleeps and 2.0 in ft.sleeps  # backoff exponentiel


def test_retry_epuise_apres_3_tentatives():
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        return httpx.Response(500)

    with pytest.raises(DataError, match="500"):
        kraken(h, now=1).ticker("BTC/EUR", "XBTEUR")
    assert n["i"] == 3


def test_pas_de_retry_sur_4xx():
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        return httpx.Response(404)

    with pytest.raises(DataError, match="404"):
        kraken(h, now=1).ticker("BTC/EUR", "XBTEUR")
    assert n["i"] == 1


def test_retry_sur_erreur_reseau():
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        if n["i"] == 1:
            raise httpx.ConnectTimeout("délai")
        return httpx.Response(200, content=fx("kraken_ticker.json"))

    assert kraken(h, now=1).ticker("BTC/EUR", "XBTEUR").ask > 0
    assert n["i"] == 2


def test_limite_1_requete_par_seconde():
    ft = FakeTime()
    http = make_http(ok("kraken_ticker.json"), ft)
    c = KrakenClient(http, now=lambda: 1)
    c.ticker("BTC/EUR", "XBTEUR")
    c.ticker("BTC/EUR", "XBTEUR")
    assert ft.sleeps and ft.sleeps[0] == pytest.approx(1.0)


# --- Binance ---------------------------------------------------------------------------------

KL = json.loads(fx("binance_klines.json"))


def test_binance_exclut_jour_en_cours_et_convertit():
    now = KL[-1][6] // 1000 - 100  # le dernier jour n'est pas terminé
    c = BinanceClient(make_http(ok("binance_klines.json")), now=lambda: now)
    bars = c.klines_1d("BTCUSDT")
    assert len(bars) == len(KL) - 1
    b = bars[0]
    assert b.ts == KL[0][0] // 1000
    assert b.close == 75_867_590_000 and b.volume == 521_590_597_000 and b.taker_buy_base == 265_902_676_000


def test_binance_jour_termine_inclus():
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
    assert s.load("BTC/EUR", H4, 10 * H4)[1].close == 100  # l'existant gagne
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


def test_store_load_aucune_barre_future(tmp_path):
    s = BarStore(tmp_path, "kraken")
    s.add("BTC/EUR", H4, [bar(i * H4) for i in range(6)])
    for until in (0, 1, H4 - 1, H4, 3 * H4 + 5, 100 * H4):
        got = s.load("BTC/EUR", H4, until)
        assert all(b.ts + H4 <= until for b in got), until
    # barre ouverte à 3*H4 mais non terminée à until = 3*H4 + 5 : exclue
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


def test_store_ligne_corrompue(tmp_path):
    s = BarStore(tmp_path, "kraken")
    s.add("BTC/EUR", H4, [bar(0)])
    with s.path("BTC/EUR", H4).open("a") as f:
        f.write('{"symbol": "BTC')
    with pytest.raises(DataError):
        s.load("BTC/EUR", H4, 10**9)


# --- Config ----------------------------------------------------------------------------------


def test_config_et_instruments_enrichis():
    cfg = load_config(CONFIG)
    assert cfg.capital_ueur == 1_000_000_000 and cfg.interval_s == H4
    assert len(cfg.sha256) == 64 and len(cfg.instrument_refs) == 6
    assert cfg.models[0].daily_budget_uusd == 100_000 and cfg.models[2].price_out_uusd_per_mtok == 20_000_000
    assert (cfg.temoins.e0065.L, cfg.temoins.e0065.k, cfg.temoins.e0065.H) == (20, 3, 10)
    c = kraken(ok("kraken_assetpairs.json"), now=0)
    # le fixture ne couvre que 3 des 6 paires : l'enrichissement doit échouer proprement
    with pytest.raises(DataError):
        load_instruments(cfg, c)


def test_config_invalide(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('venue_mode = "paper"\n')
    with pytest.raises(ConfigError):
        load_config(p)


# --- Réseau réel (données publiques, sans clé) -----------------------------------------------


@pytest.mark.reseau
def test_reseau_kraken_et_binance():
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
