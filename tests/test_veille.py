"""Veille continue et réveils (docs/VEILLE.md) : vrai journal en dossier temporaire, marché et décideurs factices.

Frise commune : cycle 0 à T0+300 (terminé à T0+300). Pour un tick X où le mouvement joue, `prepare` journalise
les ticks X-3900 et X-3600 (références) puis X-300 (confirmation) ; le tick X est lancé par le test. Fenêtre où un
réveil est permis après le cycle 0 : de T0+3900 (délai de 3600 s) à T0+12900 (30 min avant le rendez-vous de
T0+14700). Aucun test n'appelle `claude -p` ni le réseau.
"""

from __future__ import annotations

import random
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest

from arene import cli
from arene import cycle as cyc
from arene.config import ConfigError, load_config
from arene.cycle import cycle_lock, run_cycle
from arene.deciders.llm import load_system_prompt
from arene.deciders.snapshot import SCHEMA_VERSION
from arene.journal import Journal, verify
from arene.ledger import equity_ueur, replay
from arene.paths import REPO
from arene.sim.executor import SimExecutor
from arene.temoins.aleatoire import seed_for
from arene.types import Bar, Instrument, Quote, notional_ueur
from arene.veille import (
    H,
    classer_quote,
    mouvement,
    precedent,
    prochain_rendez_vous,
    run_veille,
    variation_bougies,
)
from tests.fakes import (
    H4,
    HAIKU,
    OPUS,
    SONNET,
    SYMBOLS,
    T0,
    Env,
    FakeKraken,
    ScriptedDecider,
    action,
)

FABLE = "llm:claude-fable-5-2"
LLM_ALL = (HAIKU, SONNET, OPUS, FABLE)
REFS = ("temoin:panier", "temoin:6040", "temoin:e0065")
BTC = "BTC/EUR"
BTC_REF = 60_000_000_000  # milieu de référence de BTC aux ticks de test (multiple de 10 000 : pourcentages exacts)
BTC_INST = Instrument("BTC/EUR", "XBTEUR", "BTCUSDT", 100_000, 6_000, 450_000)
X = T0 + 4200  # premier tick où le mouvement et les garde-fous permettent un réveil


class LiveKraken(FakeKraken):
    """Marché factice : ticker forçable (`override`), transactions forçables (`trades` : cours par morceaux, et
    `bar_override` : une bougie 1 min précise) et lecture OHLC 1 min en panne (`fail_ohlc`)."""

    def __init__(self, clock) -> None:
        super().__init__(clock)
        self.override: dict[str, tuple[int, int]] = {}
        self.trades: dict[str, list[tuple[int, int]]] = {}  # symbole -> [(à partir de ts, cours)]
        self.bar_override: dict[tuple[str, int], tuple[int, int, int, int]] = {}
        self.fail_ohlc: set[str] = set()

    def ticker(self, symbol: str, pair: str) -> Quote:
        if symbol in self.override:
            bid, ask = self.override[symbol]
            return Quote(symbol, self.clock.now, bid, ask)
        return super().ticker(symbol, pair)

    def minute_bar(self, sym: str, ts: int):
        if (sym, ts) in self.bar_override:
            o, h, lo, c = self.bar_override[(sym, ts)]
            return Bar(sym, 60, ts, o, h, lo, c, 1_000_000)
        price = None
        for frm, p in self.trades.get(sym, []):
            if frm <= ts:
                price = p
        if price is not None:
            return Bar(sym, 60, ts, price, price, price, price, 1_000_000)
        return super().minute_bar(sym, ts)

    def ohlc(self, symbol: str, pair: str, interval_s: int = H4, since: int | None = None):
        if interval_s == 60 and symbol in self.fail_ohlc:
            raise RuntimeError("ohlc en panne (test)")
        return super().ohlc(symbol, pair, interval_s, since)


class Recorder(ScriptedDecider):
    def __init__(self, model: str, portfolio: str, plan) -> None:
        super().__init__(model, portfolio, plan)
        self.spent: list[int] = []
        self.snaps: list[dict] = []

    def decide(self, snapshot: dict, spent_today_uusd: int):
        self.spent.append(spent_today_uusd)
        self.snaps.append(snapshot)
        return super().decide(snapshot, spent_today_uusd)


def make_env(tmp_path: Path, name: str = "e", secrets: dict[str, str] | None = None) -> Env:
    env = Env(tmp_path / name, secrets)
    env.kraken = env.clients.kraken = LiveKraken(env.clock)
    return env


def deciders(haiku_plan=None) -> dict:
    """Un décideur factice par LLM de la config (Fable compris) ; seul Haiku suit un plan."""
    none = lambda i, s: None
    return {
        HAIKU: Recorder("claude-haiku-5-5", HAIKU, haiku_plan or none),
        SONNET: Recorder("claude-sonnet-5-5", SONNET, none),
        OPUS: Recorder("claude-opus-5-5", OPUS, none),
        FABLE: Recorder("claude-fable-5-2", FABLE, none),
    }


def buy_btc_at_cycle_0(i: int, snap: dict):
    return [action(BTC, size=10, stop=5)] if i == 0 and snap["contexte"]["type"] == "rendez_vous" else None


def buy_eth_at_reveil(i: int, snap: dict):
    return [action("ETH/EUR")] if snap["contexte"]["type"] == "reveil" else None


def cycle(env: Env, i: int, d: dict | None = None, **kw):
    env.clock.now = env.now_of(i)
    return run_cycle(env.paths, env.clients, env.clock.now, deciders=d if d is not None else deciders(), **kw)


def tick(env: Env, ts: int, d: dict | None = None, **kw):
    """Un tick de veille au créneau `ts` (multiple de 300), lancé 30 s plus tard comme le timer."""
    env.clock.now = ts + 30
    return run_veille(env.paths, env.clients, ts + 30, deciders=d if d is not None else deciders(), **kw)


def of(env: Env, *types: str) -> list[dict]:
    return env.of_type(*types)


def pl(env: Env, t: str) -> list[dict]:
    return [e["payload"] for e in env.of_type(t)]


def codes(env: Env) -> list[tuple[str, str]]:
    return [(a["level"], a["code"]) for a in pl(env, "alert")]


def set_veille(env: Env, **kw: int) -> None:
    txt = env.paths.config.read_text()
    for k, v in kw.items():
        txt, n = re.subn(rf"^{k} = \d+", f"{k} = {v}", txt, flags=re.MULTILINE)
        assert n == 1, k
    env.paths.config.write_text(txt)


def set_trades(env: Env, sym: str, price: int, at: int | None = None) -> None:
    """Les transactions de `sym` se font à `price` à partir de `at` (défaut : l'horloge courante)."""
    env.kraken.trades.setdefault(sym, []).append((env.clock.now if at is None else at, price))


def set_btc(env: Env, mid: int, *, wide: bool = False, at: int | None = None) -> None:
    """BTC au milieu `mid` (multiple de 1000) : ticker immédiat (`wide` : spread de 3 %) et transactions à `mid`
    à partir de `at`."""
    if wide:
        env.kraken.override[BTC] = (mid * 985 // 1000, mid * 1015 // 1000)
    else:
        env.kraken.override[BTC] = (mid * 9995 // 10000, mid * 10005 // 10000)
    set_trades(env, BTC, mid, at)


def set_ticker_btc(env: Env, mid: int) -> None:
    """BTC au milieu `mid` au ticker SEULEMENT : les transactions (bougies 1 min) ne bougent pas."""
    env.kraken.override[BTC] = (mid * 9995 // 10000, mid * 10005 // 10000)


def clear_market(env: Env) -> None:
    env.kraken.override.clear()
    env.kraken.trades.clear()
    env.kraken.bar_override.clear()


def crash_to(env: Env, bid: int, ask: int | None = None, at: int | None = None) -> None:
    """Ticker (bid, ask) et transactions au cours `bid`, à partir de `at` (défaut : l'horloge courante)."""
    env.kraken.override[BTC] = (bid, bid + bid // 1000 if ask is None else ask)
    set_trades(env, BTC, bid, at)


def up(bp: int) -> int:
    return BTC_REF * (10_000 + bp) // 10_000


def prepare(env: Env, x: int, d: dict | None = None, bp: int = 300, *, wide: bool = False) -> dict:
    """Cycle 0 ; BTC traité à BTC_REF puis, dès x-420, à +bp (ticker et transactions) ; un tick à x-300, où le
    mouvement n'est pas encore confirmé (le tick x-600 était encore à BTC_REF). Le tick x est lancé par le test."""
    d = d if d is not None else deciders()
    cycle(env, 0, d)
    set_btc(env, BTC_REF, at=0)
    set_btc(env, up(bp), wide=wide, at=x - 420)
    r = tick(env, x - 300, d)
    assert r.status == "done" and r.declencheur is None
    return d


def check_journal(env: Env) -> None:
    rep = verify(env.paths.journal)
    assert rep.ok, rep.errors
    replay(env.events())  # ne lève pas


def reveil_events(env: Env) -> list[str]:
    return [e["type"] for e in env.of_type("reveil_started", "reveil_completed", "reveil_abandonne")]


def stop_of(env: Env, portfolio: str = HAIKU, symbol: str = BTC) -> int:
    return [s for s in pl(env, "stop_set") if s["portfolio"] == portfolio and s["symbol"] == symbol][-1]["stop_ueur"]


def aleatoire_tick() -> int:
    """Premier tick >= X où le tirage de l'aléatoire donne au moins une action (cherché, pas supposé)."""
    for k in range(40):
        x = X + 300 * k
        if x <= T0 + 12900 and random.Random(seed_for(x, 0)).randrange(3) >= 1:
            return x
    raise AssertionError("aucun tick favorable")


# ---------------------------------------------------------------------------------------------- tick de base


def test_un_evenement_veille_par_tick_idempotent(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    r1 = tick(env, T0 + 600)
    assert r1.status == "done" and r1.tick == T0 + 600 and r1.n_events == 1
    snapshot = env.paths.journal.read_bytes()
    env.clock.now = T0 + 730  # même créneau de 5 min
    again = run_veille(env.paths, env.clients, T0 + 730, deciders=deciders())
    assert again.status == "already_done" and again.n_events == 0 and again.ok
    assert env.paths.journal.read_bytes() == snapshot
    tick(env, T0 + 900)
    ev = of(env, "veille")
    assert [e["payload"]["tick"] for e in ev] == [T0 + 600, T0 + 900]
    assert [e["ts"] for e in ev] == [T0 + 600, T0 + 900]
    check_journal(env)


def test_forme_de_l_evenement_veille_et_equity_au_bid(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0, deciders(buy_btc_at_cycle_0))
    before = env.events()
    tick(env, T0 + 600)
    p = of(env, "veille")[-1]["payload"]
    assert set(p) == {"tick", "quotes", "quotes_bruts", "rejets", "confirmes", "variations_bp", "clotures_1m", "equity", "stops", "reveil", "refus"}
    assert p["quotes_bruts"] == p["quotes"] and p["confirmes"] == []
    # Transactions : bougies 1 min closes ; marché plat, donc variation nulle et clôture = dernier cours.
    last = env.kraken.minute_bar("ETH/EUR", (T0 + 600) // 60 * 60 - 60).close
    assert p["clotures_1m"]["ETH/EUR"] == last and set(p["variations_bp"]) == set(SYMBOLS)
    for sym in SYMBOLS:  # variation = dernière clôture 1 min / clôture 1 min d'il y a 1 h, en bp arrondis
        ref = env.kraken.minute_bar(sym, T0 + 600 - 3600).close
        cur = env.kraken.minute_bar(sym, T0 + 600 - 60).close
        d = cur - ref
        bp = (abs(d) * 20_000 + ref) // (2 * ref)
        assert p["variations_bp"][sym] == (bp if d > 0 else -bp)
    assert p["stops"] == [] and p["reveil"] is None and p["refus"] is None and p["rejets"] == {}
    assert set(p["quotes"]) == set(SYMBOLS)
    q = env.kraken.ticker("ETH/EUR", "ETHEUR")
    assert p["quotes"]["ETH/EUR"] == [q.bid, q.ask]
    bids = {s: b for s, (b, _a) in p["quotes"].items()}
    marks = {s: (b + a) // 2 for s, (b, a) in p["quotes"].items()}
    assert p["equity"] == {name: equity_ueur(st, marks, bids) for name, st in sorted(replay(before).items())}
    assert len(p["equity"]) == 8
    assert not [e for e in of(env, "equity") if e["ts"] >= T0 + 600]  # la veille n'écrit pas d'equity


def test_tick_sans_ecrire_si_le_verrou_est_pris(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    before = env.paths.journal.read_bytes()
    with cycle_lock(env.paths):
        rep = tick(env, T0 + 600)
    assert rep.status == "busy" and rep.ok and env.paths.journal.read_bytes() == before
    assert tick(env, T0 + 600).status == "done"  # verrou libre : le tick passe


def test_avant_le_premier_cycle_la_veille_n_ecrit_rien(tmp_path: Path):
    env = make_env(tmp_path)
    rep = tick(env, T0 + 600)
    assert rep.status == "inactive" and rep.ok and not env.paths.journal.exists()


def test_mediane_des_spreads_du_cycle_inchangee_par_la_veille_et_par_les_reveils(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X, deciders())
    assert [e["payload"]["tick"] for e in of(env, "veille")] == [X - 300]
    quotes_before = of(env, "quote")
    assert tick(env, X, d).reveil == "completed"
    assert of(env, "quote") == quotes_before  # ni la veille ni le réveil n'ajoutent de `quote`
    assert len(of(env, "quote_reveil")) == 6  # les quotes du réveil ont leur propre type

    def medians(events):
        spreads: dict[str, list[int]] = {}
        for e in events:
            spreads.setdefault(e["payload"]["symbol"], []).append(e["payload"]["ask"] - e["payload"]["bid"])
        return {s: sorted(v[-20:])[len(v[-20:]) // 2] for s, v in spreads.items()}

    assert medians(of(env, "quote")) == medians(quotes_before)
    assert {e["payload"]["symbol"] for e in of(env, "quote_reveil")} == set(SYMBOLS)
    check_journal(env)


# ---------------------------------------------------------------------------------------------- 1. prix à zéro


def test_aucun_fill_a_zero_ni_negatif_avant_ecriture(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0, deciders(buy_btc_at_cycle_0))
    ex = SimExecutor(Journal(env.paths.journal), {BTC: BTC_INST}, 50, 5)
    before = env.paths.journal.read_bytes()
    for qty, px in [(1, 0), (1, -5), (0, 100_000), (-1, 100_000)]:
        with pytest.raises(ValueError, match="fill invalide"):
            ex._forced_sell("x", HAIKU, BTC, qty, px, 0, T0 + 600, "stop")
    assert env.paths.journal.read_bytes() == before
    # Un quote dont le bid tombe à 0 (glissement compris) est ignoré par les stops en direct, la mise à plat
    # et le contrôle de détention : le journal reste identique.
    zero = {BTC: Quote(BTC, T0 + 600, 0, 100_000)}
    nulles = {BTC: [Bar(BTC, 60, T0 + 60 * k, 0, 0, 0, 0, 1) for k in range(1, 10)]}  # transactions à 0 : prix de vente nul
    assert ex.process_live_stops(nulles, T0 + 600) == []
    assert ex.flatten(HAIKU, zero, T0 + 600, "kill_switch") == []
    assert ex.process_stops_and_expiry({}, zero, T0 + 600 + 8 * 86_400, 604_800) == []
    assert env.paths.journal.read_bytes() == before
    check_journal(env)


# ---------------------------------------------------------------------------------------------- 2. quotes douteux


def hist_of(n: int, spread: int, mid: int = 1_000_000, step: int = 300, start: int = 1000):
    return [H(start + step * k, mid - spread // 2, mid + spread // 2, True, None) for k in range(n)]


def test_classer_quote_invalide_spread_saut_aux_bornes_exactes():
    t = 1000 + 300 * 6
    assert classer_quote(0, 10, [], t) == ("invalide", False)
    assert classer_quote(10, 9, [], t) == ("invalide", False)
    assert classer_quote(5, 5, [], t) == (None, False)  # bid == ask est valide
    assert classer_quote(True, 10, [], t) == ("invalide", False)
    h = hist_of(5, 1000)  # 5 spreads bruts de 1000 : le contrôle du spread s'applique
    assert classer_quote(1_000_000 - 2500, 1_000_000 + 2500, h, t) == (None, False)  # 5 000 = 5 x la médiane : accepté
    assert classer_quote(1_000_000 - 2500, 1_000_000 + 2501, h, t) == ("spread", False)
    h4 = hist_of(4, 1000)  # 4 quotes seulement : pas de contrôle du spread
    assert classer_quote(1_000_000 - 50_000, 1_000_000 + 50_000, h4, 1000 + 300 * 4) == (None, False)
    # La médiane porte sur les 20 derniers spreads BRUTS, rejetés compris : 20 spreads de 1000 après 10 de 100 000.
    h30 = [H(300 * k, 999_000, 1_099_000, False, "spread") for k in range(10)] + [
        H(3000 + 300 * k, 999_500, 1_000_500, True, None) for k in range(20)
    ]
    assert classer_quote(997_500, 1_002_500, h30, 3000 + 300 * 20) == (None, False)
    assert classer_quote(997_500, 1_002_501, h30, 3000 + 300 * 20) == ("spread", False)
    # Médiane sur les bruts : 10 spreads bruts larges rejetés + 10 acceptés étroits -> médiane large (index 10).
    mix = [H(300 * k, 999_000, 1_099_000, False, "spread") for k in range(11)] + [
        H(3300 + 300 * k, 999_500, 1_000_500, True, None) for k in range(9)
    ]
    assert classer_quote(950_000, 1_050_000, mix, 3300 + 300 * 9) == (None, False)  # spread 100 000 <= 5 x 100 000
    # Saut : milieu à 15 % ou plus du dernier quote accepté de moins de 30 min.
    last = [H(1000, 999_999, 1_000_001, True, None)]
    assert classer_quote(1_149_999, 1_149_999, last, 1000 + 1799) == (None, False)  # 14,9999 %
    assert classer_quote(1_150_000, 1_150_000, last, 1000 + 1799) == ("saut", False)
    assert classer_quote(850_000, 850_000, last, 1000 + 1799) == ("saut", False)
    assert classer_quote(850_001, 850_001, last, 1000 + 1799) == (None, False)
    # Historique périmé (30 min pile) : le saut se mesure contre la clôture 4 h, avec la même tolérance.
    assert classer_quote(1_150_000, 1_150_000, last, 1000 + 1800) == (None, False)  # sans clôture : pas de contrôle
    assert classer_quote(1_150_000, 1_150_000, last, 1000 + 1800, close=1_000_000) == ("saut", False)
    assert classer_quote(1_149_999, 1_149_999, last, 1000 + 1800, close=1_000_000) == (None, False)


def test_confirmation_de_rupture_aux_bornes_exactes():
    prev_saut = [H(1000, 800_000, 800_000, False, "saut")]
    t = 1300
    assert classer_quote(800_000, 800_000, prev_saut, t, close=1_000_000) == (None, True)  # même milieu : confirmé
    assert classer_quote(815_999, 815_999, prev_saut, t, close=1_000_000) == (None, True)  # 1,99 % d'écart
    assert classer_quote(816_000, 816_000, prev_saut, t, close=1_000_000) == ("saut", False)  # 2 % : plus cohérent
    assert classer_quote(784_000, 784_000, prev_saut, t, close=1_000_000) == ("saut", False)
    assert classer_quote(784_001, 784_001, prev_saut, t, close=1_000_000) == (None, True)
    assert classer_quote(800_000, 800_000, prev_saut, 1000 + 601, close=1_000_000) == ("saut", False)  # tick précédent à plus de 10 min
    assert classer_quote(800_000, 800_000, prev_saut, 1000 + 600, close=1_000_000) == (None, True)
    # Le tick précédent doit avoir été rejeté pour spread ou saut (ou confirmé), pas invalide ni normal.
    for flag in ("invalide", "erreur : X", None):
        h = [H(1000, 800_000, 800_000, False, flag)]
        assert classer_quote(800_000, 800_000, h, t, close=1_000_000) == ("saut", False), flag
    # Un quote confirmé devient la référence du saut ; son tick suivant, encore trop large, est confirmé par chaînage.
    assert classer_quote(800_000, 800_000, [H(1000, 800_000, 800_000, True, "confirme")], t, close=1_000_000) == (None, False)
    chain = hist_of(5, 1000, start=0) + [H(1500, 995_000, 1_005_000, True, "confirme")]
    assert classer_quote(995_000, 1_005_000, chain, 1800) == (None, True)
    assert classer_quote(995_000, 1_005_000, chain[:-1], 1800) == ("spread", False)  # sans le tick confirmé : rejeté


def test_quote_ecarte_par_symbole_exclu_du_tick_equity_au_dernier_quote_valide(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)  # le panier détient BTC
    tick(env, T0 + 600)
    first = of(env, "veille")[-1]["payload"]
    env.kraken.override[BTC] = (0, 10)  # bid nul : invalide
    rep = tick(env, T0 + 900)
    p = of(env, "veille")[-1]["payload"]
    assert rep.status == "done" and rep.rejets == {BTC: "invalide"} and p["rejets"] == {BTC: "invalide"}
    assert BTC not in p["quotes"] and set(p["quotes"]) == set(SYMBOLS) - {BTC}
    states = replay(env.events()[: of(env, "veille")[-1]["seq"]])
    bids = {s: b for s, (b, _a) in p["quotes"].items()} | {BTC: first["quotes"][BTC][0]}
    marks = {s: (b + a) // 2 for s, (b, a) in p["quotes"].items()} | {BTC: sum(first["quotes"][BTC]) // 2}
    assert p["equity"]["temoin:panier"] == equity_ueur(states["temoin:panier"], marks, bids)
    # Saut de 20 % : écarté aussi ; revenu à la normale, le symbole reprend.
    mid = sum(first["quotes"][BTC]) // 2
    env.kraken.override[BTC] = (mid * 12 // 10, mid * 12 // 10 + 1000)
    assert tick(env, T0 + 1200).rejets == {BTC: "saut"}
    env.kraken.override.clear()
    assert tick(env, T0 + 1500).rejets == {}


def wide_quote(env: Env, bid_or_mid: int, spread: int, *, bid: bool = False) -> None:
    """BTC avec un spread donné : autour du milieu (défaut) ou à partir du bid (`bid=True`)."""
    if bid:
        env.kraken.override[BTC] = (bid_or_mid, bid_or_mid + spread)
    else:
        env.kraken.override[BTC] = (bid_or_mid - spread // 2, bid_or_mid + spread // 2)


def veille_p(env: Env) -> dict:
    return of(env, "veille")[-1]["payload"]


def test_spread_x10_durable_accepte_au_2e_tick(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    normal = env.kraken.ticker(BTC, "XBTEUR")
    spread10 = 10 * (normal.ask - normal.bid)
    for k in range(5):  # 5 ticks normaux : le contrôle du spread s'applique
        assert tick(env, T0 + 600 + 300 * k).rejets == {}
    wide_quote(env, normal.bid, spread10, bid=True)
    w1 = tick(env, T0 + 2100)
    assert w1.rejets == {BTC: "spread"} and w1.confirmes == []
    p1 = veille_p(env)
    assert BTC not in p1["quotes"] and p1["quotes_bruts"][BTC] == [normal.bid, normal.bid + spread10]
    w2 = tick(env, T0 + 2400)  # deuxième tick cohérent : la rupture est acceptée
    assert w2.rejets == {} and w2.confirmes == [BTC]
    p2 = veille_p(env)
    assert p2["quotes"][BTC] == [normal.bid, normal.bid + spread10] and p2["confirmes"] == [BTC] and p2["rejets"] == {}
    check_journal(env)


def test_krach_du_ticker_sans_transactions_equity_au_dernier_quote_accepte_aucune_vente(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    set_ticker_btc(env, BTC_REF)
    tick(env, T0 + 600, d)
    ok = veille_p(env)["quotes"][BTC]
    set_ticker_btc(env, BTC_REF * 80 // 100)  # le ticker s'effondre, aucune transaction ne suit
    crash = env.kraken.override[BTC]
    w1 = tick(env, T0 + 900, d)
    assert w1.rejets == {BTC: "saut"} and w1.stops == []
    p1 = veille_p(env)
    assert p1["quotes_bruts"][BTC] == list(crash) and BTC not in p1["quotes"]
    pre = replay(env.events()[: of(env, "veille")[-1]["seq"]])["temoin:panier"]
    bids = {s: b for s, (b, _a) in p1["quotes"].items()} | {BTC: ok[0]}  # valorisé au dernier quote accepté
    marks = {s: (b + a) // 2 for s, (b, a) in p1["quotes"].items()} | {BTC: sum(ok) // 2}
    assert p1["equity"]["temoin:panier"] == equity_ueur(pre, marks, bids)
    w2 = tick(env, T0 + 1200, d)  # deuxième tick cohérent : accepté (equity à jour), mais jamais de vente
    assert w2.rejets == {} and w2.confirmes == [BTC] and w2.stops == []
    p2 = veille_p(env)
    pre2 = replay(env.events()[: of(env, "veille")[-1]["seq"]])["temoin:panier"]
    bids2 = {s: b for s, (b, _a) in p2["quotes"].items()}
    marks2 = {s: (b + a) // 2 for s, (b, a) in p2["quotes"].items()}
    assert p2["equity"]["temoin:panier"] == equity_ueur(pre2, marks2, bids2) < p1["equity"]["temoin:panier"]
    assert BTC in replay(env.events())[HAIKU].positions
    check_journal(env)


def test_acceptation_en_chaine_plafonnee_a_6_ticks_puis_rejet_alerte_et_levee(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    normal = env.kraken.ticker(BTC, "XBTEUR")
    for k in range(20):  # 20 spreads bruts normaux : la médiane ne suit le nouveau régime qu'au 11e tick large
        tick(env, T0 + 600 + 300 * k)
    wide_quote(env, normal.bid, 10 * (normal.ask - normal.bid), bid=True)
    out, conf = [], []
    for w in range(1, 12):
        rep = tick(env, T0 + 600 + 300 * (19 + w))
        out.append("ok" if rep.rejets == {} else rep.rejets[BTC])
        conf.append(BTC in rep.confirmes)
        if w in (8, 9, 10):  # chaîne épuisée : le symbole est rejeté, l'equity reste au dernier quote accepté
            assert BTC not in veille_p(env)["quotes"] and veille_p(env)["quotes_bruts"][BTC][0] == normal.bid
    # 1 rejet initial, 6 ticks acceptés par confirmation, 3 rejets, puis la médiane brute a rattrapé : accepté.
    assert out == ["spread"] + ["ok"] * 6 + ["spread"] * 3 + ["ok"]
    assert conf == [False] + [True] * 6 + [False] * 4
    alerts = [(a["level"], a["message"]) for a in pl(env, "alert") if a["code"] == "veille_symbole_ecarte"]
    assert [(lvl, m.startswith(t)) for (lvl, m), t in zip(alerts, ("BTC/EUR : quotes écartés", "BTC/EUR : quotes de nouveau"), strict=True)] == [("action", True), ("info", True)]


def test_tick_aberrant_isole_jamais_accepte_ni_vente_ni_reveil(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    set_ticker_btc(env, BTC_REF)
    tick(env, T0 + 600, d)
    set_ticker_btc(env, BTC_REF * 50 // 100)
    b = tick(env, T0 + 900, d)
    assert b.rejets == {BTC: "saut"} and b.confirmes == [] and b.stops == [] and b.declencheur is None
    assert BTC not in veille_p(env)["quotes"]
    set_ticker_btc(env, BTC_REF)
    c = tick(env, T0 + 1200, d)  # retour à la normale : accepté normalement, pas par confirmation
    assert c.rejets == {} and c.confirmes == [] and c.stops == []
    assert BTC in veille_p(env)["quotes"]
    assert BTC in replay(env.events())[HAIKU].positions and not reveil_events(env)
    assert not [f for f in pl(env, "fill") if f["order_id"].endswith(":veille:" + str(T0 + 900))]


def test_deux_ticks_aberrants_incoherents_entre_eux_restent_rejetes(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    set_ticker_btc(env, BTC_REF)
    tick(env, T0 + 600, d)
    set_ticker_btc(env, BTC_REF * 50 // 100)
    assert tick(env, T0 + 900, d).rejets == {BTC: "saut"}
    set_ticker_btc(env, BTC_REF * 70 // 100)  # -30 % : 40 % d'écart avec le tick précédent
    c = tick(env, T0 + 1200, d)
    assert c.rejets == {BTC: "saut"} and c.confirmes == [] and c.stops == []
    assert BTC not in veille_p(env)["quotes"] and BTC in replay(env.events())[HAIKU].positions


def test_historique_perime_le_saut_se_mesure_contre_la_cloture_4h(tmp_path: Path):
    env = make_env(tmp_path)  # aucun quote de veille : le premier tick compare à la clôture 4 h du store
    cycle(env, 0)
    close = max(env.kraken.ohlc(BTC, "XBTEUR", H4, None), key=lambda b: b.ts).close
    set_ticker_btc(env, close // 10_000 * 10_000 // 2)
    first = tick(env, T0 + 600)
    assert first.rejets == {BTC: "saut"} and BTC not in veille_p(env)["quotes"]
    # Historique accepté vieux de 30 min pile : même règle, puis confirmation au tick suivant.
    env2 = make_env(tmp_path, "e2")
    cycle(env2, 0)
    tick(env2, T0 + 600)  # BTC normal accepté
    set_ticker_btc(env2, close // 10_000 * 10_000 // 2)
    b = tick(env2, T0 + 600 + 1800)
    assert b.rejets == {BTC: "saut"} and b.confirmes == []
    c = tick(env2, T0 + 600 + 2100)
    assert c.rejets == {} and c.confirmes == [BTC]


def test_alerte_symbole_ecarte_et_mediane_sur_les_quotes_bruts(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    for k in range(5):
        set_ticker_btc(env, BTC_REF)
        tick(env, T0 + 600 + 300 * k)
    # Spread x10 durable avec un milieu qui oscille de 3 % : jamais confirmé (écart de 2 % ou plus entre deux ticks).
    outcomes = []
    for w in range(1, 8):
        mid = BTC_REF * (1015 if w % 2 else 985) // 1000
        env.kraken.override[BTC] = (mid * 995 // 1000, mid * 1005 // 1000)
        rep = tick(env, T0 + 1800 + 300 * w)
        outcomes.append((rep.rejets.get(BTC), rep.confirmes))
    # La médiane brute rattrape le régime large au 6e tick large : accepté normalement, sans confirmation.
    assert outcomes == [("spread", [])] * 5 + [(None, [])] * 2
    syms = [(a["level"], a["code"], a["message"][:24]) for a in pl(env, "alert") if a["code"] == "veille_symbole_ecarte"]
    assert syms == [
        ("action", "veille_symbole_ecarte", "BTC/EUR : quotes écartés"),
        ("info", "veille_symbole_ecarte", "BTC/EUR : quotes de nouv"),
    ]
    alerts = [e for e in of(env, "alert") if e["payload"]["code"] == "veille_symbole_ecarte"]
    ticks = [e["ts"] for e in alerts]
    assert ticks == [T0 + 1800 + 300 * 3 + 30, T0 + 1800 + 300 * 6 + 30]  # au 3e rejet, puis à la levée (6e tick)


def test_symbole_ecarte_pas_de_stop_ni_de_declencheur_sur_lui(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    S = stop_of(env)
    set_ticker_btc(env, BTC_REF)
    tick(env, T0 + 600, d)
    # Quote sous le stop mais avec un saut > 15 % (spread de 3 % : ask 3 % au-dessus) : écarté, pas de vente.
    bad = S * 80 // 100
    env.kraken.override[BTC] = (bad, bad + 1000)
    rep = tick(env, T0 + 900, d)
    assert rep.rejets == {BTC: "saut"} and rep.stops == []
    assert BTC in replay(env.events())[HAIKU].positions
    assert rep.declencheur is None


def test_aucun_symbole_valide_le_tick_echoue_sans_rien_ecrire(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    size = env.paths.journal.stat().st_size
    env.kraken.fail_ticker = True
    rep = tick(env, T0 + 600)
    assert rep.status == "failed" and not rep.ok and "aucun quote exploitable" in rep.error
    assert env.paths.journal.stat().st_size == size
    env.kraken.fail_ticker = False
    assert tick(env, T0 + 900).status == "done"


# ---------------------------------------------------------------------------------------------- 3. stops et mouvement sur les transactions


def base_close(env: Env) -> int:
    """Cours plat des transactions de BTC quand rien n'est forcé (clôture 4 h du marché factice)."""
    return env.kraken.minute_bar(BTC, T0).close


def b1(ts: int, o: int, h: int, lo: int, c: int) -> Bar:
    return Bar(BTC, 60, ts, o, h, lo, c, 1)


def fee_of(qty: int, px: int) -> int:
    return -(-notional_ueur(qty, px, round_up=True) * 50 // 10_000)  # frais taker 50 bp, vers le haut


def test_stop_sur_les_transactions_au_dernier_cours_avec_glissement_et_frais(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    qty = replay(env.events())[HAIKU].positions[BTC].qty
    S = stop_of(env)
    low = S - 1_000_000
    set_trades(env, BTC, low, at=T0 + 840)  # les transactions passent sous le stop ; le ticker reste normal
    r1 = tick(env, T0 + 900, d)  # une seule bougie close sous le stop (ts T0+840) : on attend le tick suivant
    assert r1.stops == [] and BTC in replay(env.events())[HAIKU].positions
    r = T0 + 1200
    rep = tick(env, r, d)
    oid = f"stop:{HAIKU}:{BTC}:veille:{r}"
    assert oid in rep.stops
    fill = next(f for f in pl(env, "fill") if f["order_id"] == oid)
    px = low * 9995 // 10_000 // 100_000 * 100_000  # clôture de la dernière bougie x (1 - glissement 5 bp), tick vers le bas
    assert (fill["side"], fill["qty"], fill["price_ueur"], fill["fee_ueur"], fill["ts"], fill["reason"]) == (
        "sell", qty, px, fee_of(qty, px), r, "stop",
    )  # fmt: skip
    assert px < env.kraken.ticker(BTC, "XBTEUR").bid  # le ticker (au-dessus du stop) ne fixe pas le prix
    assert BTC not in replay(env.events())[HAIKU].positions and oid in of(env, "veille")[-1]["payload"]["stops"]
    n = len(of(env, "fill"))
    tick(env, r)  # même tick : rien de plus
    assert len(of(env, "fill")) == n
    # Le cycle suivant voit la barre T0 sous le stop (krach de 6 %) : déjà vendu, pas de seconde vente.
    clear_market(env)
    env.kraken.crash(BTC, T0, 940)
    cycle(env, 1, d)
    sells = [f["order_id"] for f in pl(env, "fill") if f["portfolio"] == HAIKU and f["symbol"] == BTC and f["side"] == "sell"]
    assert sells == [oid] and not [f for f in pl(env, "fill") if f["order_id"] == f"stop:{HAIKU}:{BTC}:{T0}"]
    check_journal(env)


def test_prix_du_stop_jamais_au_dessus_du_stop(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    qty = replay(env.events())[HAIKU].positions[BTC].qty
    S = stop_of(env)
    set_trades(env, BTC, S - 1_000_000, at=T0 + 840)  # deux bougies sous le stop (T0+840, T0+900) ...
    set_trades(env, BTC, base_close(env), at=T0 + 960)  # ... puis le cours remonte bien au-dessus
    r = T0 + 1200
    rep = tick(env, r, d)
    oid = f"stop:{HAIKU}:{BTC}:veille:{r}"
    assert oid in rep.stops
    fill = next(f for f in pl(env, "fill") if f["order_id"] == oid)
    assert base_close(env) * 9995 // 10_000 > S  # la dernière clôture x (1 - glissement) serait au-dessus du stop
    assert fill["price_ueur"] == S and fill["fee_ueur"] == fee_of(qty, S)


def test_bougie_aberrante_isolee_aucune_vente(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    base = base_close(env)
    env.kraken.bar_override[(BTC, T0 + 1080)] = (base, base, 1, base)  # un plus bas à 1 µEUR, une seule minute
    for t in (T0 + 1200, T0 + 1500):
        assert tick(env, t, d).stops == []
    assert BTC in replay(env.events())[HAIKU].positions
    env.kraken.bar_override[(BTC, T0 + 1560)] = (base, base, 1, base)  # deux bougies distinctes dans la fenêtre : la vente part
    env.kraken.bar_override[(BTC, T0 + 1620)] = (base, base, 1, base)
    r = T0 + 1800
    assert f"stop:{HAIKU}:{BTC}:veille:{r}" in tick(env, r, d).stops


def test_glitch_du_ticker_repete_sans_transactions_sous_le_stop_aucune_vente(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    S = stop_of(env)
    env.kraken.override[BTC] = (S - 1_000_000, S - 900_000)  # le ticker annonce un bid sous le stop, tick après tick
    for k in range(5):
        rep = tick(env, T0 + 600 + 300 * k, d)
        assert rep.stops == [] and rep.rejets == {}
        assert veille_p(env)["quotes"][BTC][0] == S - 1_000_000  # le quote erroné est bien accepté par le contrôle du ticker
    assert BTC in replay(env.events())[HAIKU].positions and not [f for f in pl(env, "fill") if f["reason"] == "stop"]


def test_krach_a_moins_3_pct_par_tick_spread_enorme_vente_au_premier_tick_avec_2_bougies(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    qty = replay(env.events())[HAIKU].positions[BTC].qty
    S = stop_of(env)
    base = base_close(env)
    p1, p2, p3 = base * 97 // 100, base * 97 // 100 * 97 // 100, base * 97 // 100 * 97 // 100 * 97 // 100
    assert p1 > S > p2
    t1, t2, t3 = T0 + 900, T0 + 1200, T0 + 1500
    stops = []
    for t, price in ((t1, p1), (t2, p2), (t3, p3)):
        set_trades(env, BTC, price, at=t - 240)  # chaque tick, -3 % de plus
        env.kraken.override[BTC] = (price * 985 // 1000, price * 1015 // 1000)  # ticker : spread de 3 %
        stops.append(tick(env, t, d).stops)
    oid = f"stop:{HAIKU}:{BTC}:veille:{t2}"
    assert oid not in stops[0] and oid in stops[1] and not [x for x in stops[2] if HAIKU in x]
    fill = next(f for f in pl(env, "fill") if f["order_id"] == oid)
    px = p2 * 9995 // 10_000 // 100_000 * 100_000  # dernière clôture 1 min x (1 - glissement)
    assert (fill["price_ueur"], fill["fee_ueur"], fill["qty"]) == (px, fee_of(qty, px), qty) and px < S
    assert BTC not in replay(env.events())[HAIKU].positions
    ref = env.kraken.minute_bar(BTC, t3 - 3600).close  # clôture 1 min d'il y a 1 h (avant tout mouvement)
    assert veille_p(env)["variations_bp"][BTC] == -(((ref - p3) * 20_000 + ref) // (2 * ref))


def test_lecture_ohlc_en_echec_ni_stop_ni_declencheur_sur_le_symbole(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    S = stop_of(env)
    set_trades(env, BTC, S - 1_000_000, at=T0 + 840)
    env.kraken.fail_ohlc.add(BTC)
    rep = tick(env, T0 + 1200, d)
    assert rep.rejets == {BTC: "ohlc"} and rep.stops == [] and BTC in replay(env.events())[HAIKU].positions
    p = veille_p(env)
    assert p["rejets"] == {BTC: "ohlc"} and BTC in p["quotes"] and BTC not in p["clotures_1m"] and BTC not in p["variations_bp"]
    env.kraken.fail_ohlc.clear()  # la lecture revient : le filet de veille reprend (bougies depuis T0+900)
    r = T0 + 1500
    assert f"stop:{HAIKU}:{BTC}:veille:{r}" in tick(env, r, d).stops
    assert veille_p(env)["rejets"] == {}


def test_position_rachetee_apres_un_stop_de_veille_reste_geree(tmp_path: Path):
    env = make_env(tmp_path)

    def plan(i, snap):
        return [action(BTC, size=10, stop=5)] if i in (0, 1) else None

    d = deciders(plan)
    cycle(env, 0, d)
    stop0 = stop_of(env)
    set_trades(env, BTC, stop0 - 1_000_000, at=T0 + 840)
    r = T0 + 1200
    assert f"stop:{HAIKU}:{BTC}:veille:{r}" in tick(env, r, d).stops
    assert BTC not in replay(env.events())[HAIKU].positions
    clear_market(env)
    env.kraken.crash(BTC, T0, 940)  # la barre T0 est sous l'ancien stop
    cycle(env, 1, d)  # rachat
    pos = replay(env.events())[HAIKU].positions[BTC]
    assert pos.opened_ts == T0 + H4
    stop1 = stop_of(env)
    assert stop1 != stop0
    cycle(env, 2, d)  # l'ancien stop ne touche pas la position rachetée
    assert [f["order_id"] for f in pl(env, "fill") if f["portfolio"] == HAIKU and f["side"] == "sell"] == [
        f"stop:{HAIKU}:{BTC}:veille:{r}"
    ]
    assert replay(env.events())[HAIKU].positions[BTC].stop_ueur == stop1
    env.kraken.crash(BTC, T0 + 2 * H4, 800)  # nouveau krach : le filet des barres joue sur la position rachetée
    cycle(env, 3, d)
    sells = [f["order_id"] for f in pl(env, "fill") if f["portfolio"] == HAIKU and f["side"] == "sell"]
    assert sells == [f"stop:{HAIKU}:{BTC}:veille:{r}", f"stop:{HAIKU}:{BTC}:{T0 + 2 * H4}"]
    assert BTC not in replay(env.events())[HAIKU].positions
    check_journal(env)


def test_precedent_fonction_pure():
    h = [H(1000, 10, 12, True, None), H(1900, 20, 22, True, None), H(2800, 30, 32, False, "saut")]
    assert precedent(h, 3100) == h[2]  # le tick précédent compte même rejeté (quote brut)
    assert precedent([H(100, 1, 2, True, None)], 700) is not None and precedent([H(100, 1, 2, True, None)], 701) is None
    assert precedent([H(100, 1, 2, True, None)], 100) is None  # strictement avant
    assert precedent([H(100, None, None, False, "invalide")], 200) is None


def test_variation_bougies_reference_a_2_minutes_et_seuils_exacts():
    # Référence : la bougie la plus proche de tick - fenêtre, à 2 min près ; la plus récente close fixe le cours.
    tick = 7200
    cur = b1(7140, 1_030_000, 1_030_000, 1_030_000, 1_030_000)
    assert variation_bougies([b1(3600 + 120, 1, 1, 1, 1_000_000), cur], tick, 3600) == (1_030_000, 1_000_000)
    assert variation_bougies([b1(3600 + 121, 1, 1, 1, 1_000_000), cur], tick, 3600) is None
    assert variation_bougies([b1(3600 - 120, 1, 1, 1, 1_000_000), cur], tick, 3600) == (1_030_000, 1_000_000)
    near = [b1(3600 - 60, 1, 1, 1, 900_000), b1(3600 + 60, 1, 1, 1, 800_000), b1(3600 + 120, 1, 1, 1, 700_000), cur]
    assert variation_bougies(near, tick, 3600)[1] == 900_000  # à égale distance : la plus ancienne
    assert variation_bougies([b1(3600, 1, 1, 1, 1_000_000), b1(7141, 1, 1, 1, 5)], tick, 3600) is None  # pas encore close
    old = b1(7200 - 60 - 901, 1, 1, 1, 7)  # dernière bougie close vieille de plus de 15 min : pas de mesure
    assert variation_bougies([b1(3600, 1, 1, 1, 1_000_000), old], tick, 3600) is None


def minute_path(changes: dict[int, int], start: int = 3000, end: int = 7200) -> list[Bar]:
    """Bougies plates par minute ; `changes` : {à partir de ts: cours}."""
    out = []
    for ts in range(start, end, 60):
        price = [p for frm, p in sorted(changes.items()) if frm <= ts][-1]
        out.append(b1(ts, price, price, price, price))
    return out


def test_mouvement_sur_les_bougies_variations_seuils_exacts_et_confirmation():
    ref = 1_000_000
    mb = {  # A +4 % et B -10 % depuis 6000 (confirmés aux deux ticks 7200 et 6900), C plat
        "A": minute_path({0: ref, 6000: 1_040_000}), "B": minute_path({0: ref, 6000: 900_000}), "C": minute_path({0: ref}),
    }
    for sym, bars in mb.items():
        mb[sym] = [Bar(sym, 60, b.ts, b.open, b.high, b.low, b.close, 1) for b in bars]
    trig, var = mouvement(mb, 7200, 300, 3600, 300)
    assert trig == {"type": "mouvement", "symbole": "B", "variation_bp": -1000, "fenetre_s": 3600}
    assert var == {"A": 400, "B": -1000, "C": 0}
    # Seuil exact : +3 % déclenche, +2,9999 % non (aux deux ticks).
    for price, expected in ((1_030_000, True), (1_029_999, False), (970_000, True), (970_001, False)):
        bars = {"A": [Bar("A", 60, b.ts, b.open, b.high, b.low, b.close, 1) for b in minute_path({0: ref, 6000: price})]}
        assert (mouvement(bars, 7200, 300, 3600, 300)[0] is not None) is expected, price
    # Confirmation : le tick précédent (6900) était encore plat -> pas de déclencheur, la variation reste mesurée.
    late = {"A": [Bar("A", 60, b.ts, b.open, b.high, b.low, b.close, 1) for b in minute_path({0: ref, 7000: 1_050_000})]}
    trig, var = mouvement(late, 7200, 300, 3600, 300)
    assert trig is None and var == {"A": 500}
    # Sens opposés (-3 % au tick précédent, +3 % au courant) : aucun déclencheur.
    opp = {"A": [Bar("A", 60, b.ts, b.open, b.high, b.low, b.close, 1) for b in minute_path({0: ref, 6000: 970_000, 7000: 1_030_000})]}
    assert mouvement(opp, 7200, 300, 3600, 300)[0] is None
    assert mouvement({}, 7200, 300, 3600, 300) == (None, {})


# ---------------------------------------------------------------------------------------------- 4. déclencheur de stop supprimé


def buy_btc_stop_1pct(i: int, snap: dict):
    return [action(BTC, size=10, stop=1)] if i == 0 and snap["contexte"]["type"] == "rendez_vous" else None


def test_un_stop_de_veille_n_est_plus_un_declencheur_et_le_prompt_le_dit(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_stop_1pct)
    cycle(env, 0, d)
    set_trades(env, BTC, base_close(env) * 98 // 100, at=X - 420)  # -2 % : sous le stop de 1 %, sous le seuil de 3 %
    rep = tick(env, X, d)  # stop exécuté sur un portefeuille LLM
    assert f"stop:{HAIKU}:{BTC}:veille:{X}" in rep.stops
    assert rep.declencheur is None and rep.reveil is None and not reveil_events(env)
    p = veille_p(env)
    assert p["reveil"] is None and p["refus"] is None
    text = load_system_prompt()
    assert "stop" not in text.split("## Ce que tu reçois")[0].lower().replace("stop obligatoire", "")
    assert "Tu décides une fois toutes les 4 heures" not in text
    assert (
        "Tu es appelé à un rendez-vous fixe toutes les 4 heures, et tu peux aussi être réveillé entre deux "
        "rendez-vous quand un instrument bouge d'au moins le seuil en 1 heure ; le champ `contexte` de "
        "l'instantané dit lequel des deux, et rien ne t'oblige à agir."
    ) in text


def test_stop_d_un_temoin_execute_sans_reveil(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    base = base_close(env)
    Journal(env.paths.journal).append(
        "stop_set", {"portfolio": "temoin:panier", "symbol": BTC, "stop_ueur": base * 99 // 100}, T0 + 400
    )
    set_trades(env, BTC, base * 98 // 100, at=X - 420)
    rep = tick(env, X)
    assert f"stop:temoin:panier:{BTC}:veille:{X}" in rep.stops
    assert BTC not in replay(env.events())["temoin:panier"].positions
    assert rep.declencheur is None and not reveil_events(env)
    check_journal(env)


# ---------------------------------------------------------------------------------------------- déclencheur de mouvement


@pytest.mark.parametrize(("bp", "reveil"), [(299, False), (300, True), (-300, True), (-299, False)])
def test_declencheur_de_mouvement_au_seuil_exact(tmp_path: Path, bp: int, reveil: bool):
    env = make_env(tmp_path)
    d = prepare(env, X, bp=bp)
    rep = tick(env, X, d)
    trig = {"type": "mouvement", "symbole": BTC, "variation_bp": bp, "fenetre_s": 3600}
    assert veille_p(env)["variations_bp"][BTC] == bp and set(veille_p(env)["variations_bp"]) == set(SYMBOLS)
    if reveil:
        assert rep.declencheur == trig and rep.reveil == "completed"
        assert of(env, "veille")[-1]["payload"]["reveil"] == trig
        assert pl(env, "reveil_started") == [{"reveil": X, "declencheur": trig}]
    else:
        assert rep.declencheur is None and rep.reveil is None
        assert of(env, "veille")[-1]["payload"]["reveil"] is None
        assert not reveil_events(env)


@pytest.mark.parametrize(
    ("p_bp", "x_bp", "trigger"),
    [(300, 300, True), (0, 300, False), (300, 0, False), (-300, 300, False), (299, 300, False), (300, 299, False)],
)
def test_mouvement_confirme_sur_deux_ticks_meme_sens_chacun_contre_sa_reference(tmp_path, p_bp, x_bp, trigger):
    env = make_env(tmp_path)
    d = deciders()
    cycle(env, 0, d)
    set_btc(env, BTC_REF, at=0)
    set_btc(env, up(p_bp), at=X - 420)  # cours du tick X-300
    set_btc(env, up(x_bp), at=X - 240)  # cours du tick X
    assert tick(env, X - 300, d).declencheur is None
    rep = tick(env, X, d)
    assert (rep.declencheur is not None) is trigger and (rep.reveil == "completed") is trigger


def test_mouvement_mesure_sur_les_transactions_le_ticker_est_ignore(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders()
    cycle(env, 0, d)
    set_btc(env, BTC_REF, at=0)
    for t in (X - 300, X):  # le ticker s'envole de 7 % (accepté par son contrôle), les transactions restent plates
        set_ticker_btc(env, up(700))
        rep = tick(env, t, d)
        assert rep.declencheur is None and rep.reveil is None
    assert veille_p(env)["quotes"][BTC] == [up(700) * 9995 // 10000, up(700) * 10005 // 10000]
    assert veille_p(env)["variations_bp"][BTC] == 0 and not reveil_events(env)
    # Inversement : les transactions montent de 3 %, le ticker reste normal : le déclencheur part.
    env2 = make_env(tmp_path, "e2")
    d2 = prepare(env2, X, bp=300)
    del env2.kraken.override[BTC]
    rep2 = tick(env2, X, d2)
    assert rep2.declencheur == {"type": "mouvement", "symbole": BTC, "variation_bp": 300, "fenetre_s": 3600}
    assert rep2.reveil == "completed"


# ---------------------------------------------------------------------------------------------- garde-fous


def test_garde_fou_delai_depuis_la_derniere_ronde(tmp_path: Path):
    last = T0 + 300  # fin du cycle 0
    for cooldown, ok in [(X - last + 1, False), (X - last, True)]:  # 3901 s refuse, 3900 s passe (pas de "<")
        env = make_env(tmp_path, f"cd{cooldown}")
        set_veille(env, cooldown_s=cooldown)
        d = prepare(env, X)
        rep = tick(env, X, d)
        assert rep.declencheur is not None
        assert (rep.refus, rep.reveil) == ((None, "completed") if ok else ("delai", None))
        assert bool(reveil_events(env)) is ok
        p = of(env, "veille")[-1]["payload"]
        assert (p["reveil"], p["refus"]) == ((rep.declencheur, None) if ok else (None, "delai"))


def test_le_delai_compte_depuis_reveil_started_et_aussi_les_abandons(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X)
    j = Journal(env.paths.journal)
    j.append("reveil_started", {"reveil": T0 + 150, "declencheur": {"type": "mouvement", "symbole": BTC, "variation_bp": 300, "fenetre_s": 3600}}, X - 100)
    j.append("reveil_abandonne", {"reveil": T0 + 150}, T0 + 200)  # l'abandon est ancien, mais le démarrage date de 100 s
    rep = tick(env, X, d)
    assert rep.refus == "delai" and rep.reveil is None


def test_garde_fou_plafond_par_jour_compte_aussi_les_reveils_abandonnes(tmp_path: Path):
    trig = {"type": "mouvement", "symbole": BTC, "variation_bp": 300, "fenetre_s": 3600}
    for cap, ok in [(1, False), (2, True)]:
        for fin in ("reveil_completed", "reveil_abandonne"):
            env = make_env(tmp_path, f"cap{cap}{fin}")
            set_veille(env, max_reveils_jour=cap)
            d = prepare(env, X)
            j = Journal(env.paths.journal)
            j.append("reveil_started", {"reveil": T0 + 150, "declencheur": trig}, T0 + 160)
            j.append(fin, {"reveil": T0 + 150}, T0 + 200)  # un réveil plus tôt dans le même jour UTC
            rep = tick(env, X, d)
            assert (rep.refus, rep.reveil) == ((None, "completed") if ok else ("plafond", None)), (cap, fin)
    # Un réveil du jour UTC précédent ne compte pas.
    env = make_env(tmp_path, "veille-jour")
    set_veille(env, max_reveils_jour=1)
    d = prepare(env, X)
    j = Journal(env.paths.journal)
    j.append("reveil_started", {"reveil": T0 - 5000, "declencheur": trig}, T0 - 4990)
    j.append("reveil_completed", {"reveil": T0 - 5000}, T0 - 4900)
    assert tick(env, X, d).reveil == "completed"


def test_garde_fou_avant_le_cycle(tmp_path: Path):
    rdv = T0 + H4 + 300
    assert prochain_rendez_vous(X, H4, 300) == rdv
    assert prochain_rendez_vous(T0 + 300, H4, 300) == rdv  # à HH:05 pile, le prochain est dans 4 h
    assert prochain_rendez_vous(T0, H4, 300) == T0 + 300
    for x, ok in [(rdv - 1800, True), (rdv - 1500, False)]:  # 1800 s avant passe, 1500 s avant refuse
        env = make_env(tmp_path, f"av{x}")
        d = prepare(env, x)
        rep = tick(env, x, d)
        assert rep.declencheur is not None
        assert (rep.refus, rep.reveil) == ((None, "completed") if ok else ("avant_cycle", None))
        assert of(env, "veille")[-1]["payload"]["refus"] == (None if ok else "avant_cycle")


def test_garde_fou_cycle_incomplet(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)

    def boom(p: str) -> None:
        raise RuntimeError("crash simulé")

    assert cycle(env, 1, on_portfolio_done=boom).status == "failed"  # cycle_started sans cycle_completed
    x = T0 + H4 + 4200
    set_btc(env, BTC_REF)
    for t in (x - 3900, x - 3600):
        tick(env, t)
    set_btc(env, up(300))
    tick(env, x - 300)
    rep = tick(env, x)
    assert rep.declencheur is not None and rep.refus == "cycle_incomplet" and rep.reveil is None
    assert of(env, "veille")[-1]["payload"]["refus"] == "cycle_incomplet"
    assert not reveil_events(env)
    env.kraken.override.clear()
    assert cycle(env, 1).status == "completed"  # le cycle repris lève ce garde-fou


def test_un_tick_multiple_de_4_h_ne_reveille_jamais_meme_sans_garde_avant_cycle(tmp_path: Path):
    env = make_env(tmp_path)
    set_veille(env, garde_avant_cycle_s=0)
    x = T0 + H4  # HH:00 pile : l'identifiant du réveil se confondrait avec celui du cycle
    d = prepare(env, x)
    rep = tick(env, x, d)
    assert rep.declencheur is not None and rep.refus == "cycle" and rep.reveil is None
    assert not reveil_events(env)
    assert of(env, "veille")[-1]["payload"]["refus"] == "cycle"
    # Sans garde-fou « avant le cycle », le tick suivant (HH:05) n'est pas un multiple : le réveil passe.
    assert prochain_rendez_vous(x + 300, H4, 300) == x + H4 + 300


def test_pas_de_reveil_pendant_un_cycle_en_cours(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X)
    before = env.paths.journal.read_bytes()
    with cycle_lock(env.paths):  # un cycle (ou un réveil) tient le verrou
        rep = tick(env, X, d)
    assert rep.status == "busy" and env.paths.journal.read_bytes() == before


# ---------------------------------------------------------------------------------------------- 5. le réveil est consigné d'abord


def test_reveil_started_est_ecrit_avant_l_evenement_veille(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X)
    tick(env, X, d)
    seq = {e["type"]: e["seq"] for e in env.events() if e["ts"] >= X and e["type"] in ("reveil_started", "veille")}
    assert seq["reveil_started"] < seq["veille"]
    first_net = min(e["seq"] for e in of(env, "quote_reveil"))
    assert seq["veille"] < first_net


def test_reveil_qui_echoue_est_repris_une_seule_alerte_par_code_et_par_reveil(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X)

    def boom(p: str) -> None:
        raise RuntimeError("crash simulé")

    for k in range(3):  # trois échecs de suite : X, X+300 (reprise), X+600 (reprise)
        rep = tick(env, X + 300 * k, d, on_portfolio_done=boom)
        assert rep.status == "reveil_failed"
    ex = [a for a in pl(env, "alert") if a["code"] == "reveil_exception"]
    assert len(ex) == 1 and ex[0]["message"].startswith(f"[réveil {X}] ")
    assert [c for c in codes(env) if c[1] == "reveil_resumed"] == [("info", "reveil_resumed")]
    assert reveil_events(env) == ["reveil_started"]
    # Le réveil est dans le plafond et dans le délai dès reveil_started.
    assert pl(env, "reveil_started") == [{"reveil": X, "declencheur": pl(env, "reveil_started")[0]["declencheur"]}]


def test_veille_reveil_ne_contient_qu_un_reveil_demarre(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X)
    tick(env, X, d)
    p = of(env, "veille")[-1]["payload"]
    assert p["reveil"] == pl(env, "reveil_started")[0]["declencheur"] and p["refus"] is None


# ---------------------------------------------------------------------------------------------- le réveil


def test_le_reveil_reveille_tous_les_llm_et_l_aleatoire_pas_les_references_sans_equity(tmp_path: Path):
    x = aleatoire_tick()
    n_alea = random.Random(seed_for(x, 0)).randrange(3)
    env = make_env(tmp_path)
    d = prepare(env, x)
    refs_before = {p: replay(env.events())[p] for p in REFS}
    equity_before = len(of(env, "equity"))
    fills_before = len(of(env, "fill"))
    rep = tick(env, x, d)
    assert rep.reveil == "completed"
    types = [e["type"] for e in env.events()]
    assert types.count("reveil_started") == types.count("reveil_completed") == 1
    assert types.index("reveil_started") < types.index("reveil_completed")
    after = env.events()[max(i for i, t in enumerate(types) if t == "reveil_started") :]
    qs = [e for e in after if e["type"] == "quote_reveil"]
    assert len(qs) == 6 and not [e for e in after if e["type"] == "quote"]
    assert max(i for i, e in enumerate(after) if e["type"] == "quote_reveil") < min(
        i for i, e in enumerate(after) if e["type"] in ("decision_requested", "intent")
    )
    assert {e["payload"]["symbol"]: e["payload"]["bid"] for e in qs}[BTC] == up(300) * 9995 // 10000
    # TOUS les LLM de la config décident, Fable compris, avec le contexte de réveil.
    got = {p["portfolio"] for p in pl(env, "decision_received") if p["cycle"] == x}
    assert got == set(LLM_ALL)
    for p in LLM_ALL:
        assert d[p].snaps[-1]["contexte"]["type"] == "reveil" and d[p].snaps[-1]["cycle_ts"] == x
    # Aléatoire : ses intentions du tirage, via riskd ; références : rien.
    own = [p for p in pl(env, "intent") if p["cycle"] == x]
    assert len([p for p in own if p["portfolio"] == "temoin:aleatoire"]) == n_alea
    assert {p["portfolio"] for p in own} <= {"temoin:aleatoire", *LLM_ALL}
    assert {p["intent_id"] for p in own} <= {p["intent_id"] for p in pl(env, "risk_verdict")}
    assert {p: replay(env.events())[p] for p in REFS} == refs_before
    assert not [f for f in pl(env, "fill")[fills_before:] if f["portfolio"] in REFS]
    assert len(of(env, "equity")) == equity_before  # pas d'equity au réveil
    assert d[HAIKU].snaps[-1]["schema_version"] == SCHEMA_VERSION == "2"
    check_journal(env)


def test_contexte_ronde_et_budget_partage_entre_cycles_et_reveils(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X, deciders(buy_eth_at_reveil))
    tick(env, X, d)
    cycle(env, 1, d)
    snaps = d[HAIKU].snaps
    assert [s["contexte"]["type"] for s in snaps] == ["rendez_vous", "reveil", "rendez_vous"]
    assert snaps[0]["contexte"] == {"type": "rendez_vous", "prochain_rendez_vous_ts": T0 + H4 + 300}
    trig = {"type": "mouvement", "symbole": BTC, "variation_bp": 300, "fenetre_s": 3600}
    assert snaps[1]["contexte"] == {"type": "reveil", "declencheur": trig, "prochain_rendez_vous_ts": T0 + H4 + 300}
    assert snaps[2]["contexte"] == {"type": "rendez_vous", "prochain_rendez_vous_ts": T0 + 2 * H4 + 300}
    # Les décisions du réveil sont dans recent_decisions du cycle suivant, marquées « reveil ».
    rd = snaps[2]["recent_decisions"]
    assert [(r["cycle"], r["ronde"]) for r in rd] == [(T0, "rendez_vous"), (X, "reveil")]
    assert d[HAIKU].spent == [0, 1500, 3000] and d[SONNET].spent == [0, 1500, 3000]  # budget du jour partagé
    assert "réveillé entre deux rendez-vous" in load_system_prompt()


# ---------------------------------------------------------------------------------------------- 8. PRICE_SANITY au réveil


def test_price_sanity_au_reveil_compare_au_dernier_cours_des_transactions(tmp_path: Path):
    env = make_env(tmp_path)

    def plan(i, snap):
        return [action(BTC, size=10, stop=5, move=8)] if snap["contexte"]["type"] == "reveil" else None

    d = prepare(env, X, deciders(plan), bp=500)  # BTC +5 % : à plus de 3 % de la clôture de 4 h
    close = max((b for b in env.kraken.ohlc(BTC, "XBTEUR", H4, None)), key=lambda b: b.ts).close
    assert abs(up(500) - close) * 10_000 > 300 * close  # la clôture 4 h aurait déclenché PRICE_SANITY
    rep = tick(env, X, d)
    assert rep.reveil == "completed" and veille_p(env)["clotures_1m"][BTC] == up(500)
    intent = next(p for p in pl(env, "intent") if p["cycle"] == X and p["portfolio"] == HAIKU)
    verdict = next(v for v in pl(env, "risk_verdict") if v["intent_id"] == intent["intent_id"])
    assert verdict["approved"] and "PRICE_SANITY" not in verdict["reasons"]
    assert BTC in replay(env.events())[HAIKU].positions
    check_journal(env)


def test_un_ticker_errone_bloque_les_entrees_au_reveil(tmp_path: Path):
    env = make_env(tmp_path)

    def plan(i, snap):
        return [action(BTC, size=10, stop=5, move=8)] if snap["contexte"]["type"] == "reveil" else None

    d = prepare(env, X, deciders(plan), bp=300)
    set_ticker_btc(env, up(700))  # ticker +7 % (accepté : moins de 15 % du tick précédent), transactions à +3 %
    rep = tick(env, X, d)
    assert rep.reveil == "completed" and rep.rejets == {} and veille_p(env)["clotures_1m"][BTC] == up(300)
    intent = next(p for p in pl(env, "intent") if p["cycle"] == X and p["portfolio"] == HAIKU)
    verdict = next(v for v in pl(env, "risk_verdict") if v["intent_id"] == intent["intent_id"])
    assert not verdict["approved"] and "PRICE_SANITY" in verdict["reasons"]
    assert not [f for f in pl(env, "fill") if f["portfolio"] == HAIKU and f["side"] == "buy"]


def test_symbole_sans_quote_accepte_verdict_no_quote_jamais_de_continue_muet(tmp_path: Path):
    env = make_env(tmp_path)

    def plan(i, snap):
        return [action(BTC, size=10, stop=5, move=8)] if snap["contexte"]["type"] == "reveil" else None

    d = prepare(env, X, deciders(plan), bp=300)
    env.kraken.override[BTC] = (0, 10)  # ticker invalide : pas de quote accepté ; les transactions déclenchent le réveil
    rep = tick(env, X, d)
    assert rep.reveil == "completed" and rep.rejets == {BTC: "invalide"}
    intent = next(p for p in pl(env, "intent") if p["cycle"] == X and p["portfolio"] == HAIKU)
    verdict = next(v for v in pl(env, "risk_verdict") if v["intent_id"] == intent["intent_id"])
    assert verdict == {**verdict, "approved": False, "reasons": ["NO_QUOTE"], "qty": 0, "reserved_ueur": 0}
    states = [(o["state"], o["detail"]) for o in pl(env, "order_state") if o["order_id"] == intent["intent_id"]]
    assert states == [("RISK_REJECTED", "NO_QUOTE")]
    assert BTC not in replay(env.events())[HAIKU].positions and BTC not in {q["payload"]["symbol"] for q in of(env, "quote_reveil")}
    check_journal(env)


# ---------------------------------------------------------------------------------------------- 9. coupe-circuit


def test_coupe_circuit_pendant_un_reveil_entrees_refusees(tmp_path: Path):
    x = aleatoire_tick()

    def plan(i, snap):
        if snap["contexte"]["type"] == "reveil":
            return [action("ETH/EUR")]
        return [action("LINK/EUR")] if i == 0 else None

    env = make_env(tmp_path)
    d = prepare(env, x, deciders(plan))
    assert "LINK/EUR" in replay(env.events())[HAIKU].positions
    env.paths.kill.parent.mkdir(parents=True, exist_ok=True)
    env.paths.kill.touch()
    n_fills = len(of(env, "fill"))
    assert tick(env, x, d).reveil == "completed"
    assert [k["active"] for k in pl(env, "kill_switch")] == [True]
    new = pl(env, "fill")[n_fills:]
    assert new and all(f["side"] == "sell" for f in new)  # aucune entrée, de personne
    assert f"exit:{HAIKU}:LINK/EUR:{x}:kill_switch" in {f["order_id"] for f in new}
    skipped = {p["portfolio"]: p["reason"] for p in pl(env, "decision_skipped") if p["cycle"] == x}
    assert skipped[HAIKU] == skipped[SONNET] == skipped[FABLE] == "kill_switch"
    verdicts = {v["intent_id"]: v for v in pl(env, "risk_verdict")}
    buys = [p for p in pl(env, "intent") if p["cycle"] == x and p["side"] == "buy"]
    assert all(not verdicts[p["intent_id"]]["approved"] and "KILL_SWITCH" in verdicts[p["intent_id"]]["reasons"] for p in buys)
    assert not replay(env.events())[HAIKU].positions
    check_journal(env)


def kill_during_decide(env: Env, kind: str):
    def plan(i, snap):
        env.paths.kill.parent.mkdir(parents=True, exist_ok=True)
        env.paths.kill.touch()  # armé pendant l'appel LLM
        return [action("ETH/EUR")]

    return plan


def test_kill_arme_pendant_l_appel_llm_bloque_l_achat_au_reveil(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X, deciders())
    d[HAIKU].plan = lambda i, s: (env.paths.kill.parent.mkdir(parents=True, exist_ok=True), env.paths.kill.touch(), [action("ETH/EUR")])[2]
    assert tick(env, X, d).reveil == "completed"
    intent = next(p for p in pl(env, "intent") if p["cycle"] == X and p["portfolio"] == HAIKU)
    verdict = next(v for v in pl(env, "risk_verdict") if v["intent_id"] == intent["intent_id"])
    assert not verdict["approved"] and "KILL_SWITCH" in verdict["reasons"]
    assert not [f for f in pl(env, "fill") if f["portfolio"] == HAIKU and f["side"] == "buy"]


def test_kill_arme_pendant_l_appel_llm_bloque_l_achat_au_cycle(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders()
    d[HAIKU].plan = lambda i, s: (env.paths.kill.parent.mkdir(parents=True, exist_ok=True), env.paths.kill.touch(), [action("ETH/EUR")])[2]
    assert cycle(env, 0, d).status == "completed"
    intent = next(p for p in pl(env, "intent") if p["portfolio"] == HAIKU)
    verdict = next(v for v in pl(env, "risk_verdict") if v["intent_id"] == intent["intent_id"])
    assert not verdict["approved"] and "KILL_SWITCH" in verdict["reasons"]
    assert not [f for f in pl(env, "fill") if f["portfolio"] == HAIKU and f["side"] == "buy"]


def test_attentes_de_verrou_et_delais_systemd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    assert cyc.LOCK_WAIT_S == 600 and cyc.FLATTEN_LOCK_WAIT_S == 120
    waits: list[float] = []

    @contextmanager
    def fake_lock(paths, wait_s=0.0):
        waits.append(wait_s)
        yield

    monkeypatch.setattr(cyc, "cycle_lock", fake_lock)
    env = make_env(tmp_path)
    cycle(env, 0)
    cyc.flatten_now(env.paths, env.clients, T0 + 900)
    cycle(env, 1)
    assert waits == [600.0, 120.0, 600.0]  # cycle, mise à plat immédiate, cycle
    unit = lambda n: (REPO / "ops" / "systemd" / n).read_text()
    assert "TimeoutStartSec=1500" in unit("arene-cycle.service")
    assert "TimeoutStartSec=600" in unit("arene-veille.service")
    assert "OnCalendar=*-*-* *:00/5:30 UTC" in unit("arene-veille.timer")
    site = unit("arene-site-build.service")
    assert "Type=oneshot" in site and site.count("ExecStart=") == 1 and site.endswith("arene build-site\nTimeoutStartSec=600\nNice=10\n")


# ---------------------------------------------------------------------------------------------- 6. reprise et abandon


def crashed_reveil(env: Env, d: dict, x: int, after: str = HAIKU):
    def boom(p: str) -> None:
        if p == after:
            raise RuntimeError("crash simulé")

    rep = tick(env, x, d, on_portfolio_done=boom)
    assert rep.status == "reveil_failed" and not rep.ok and "crash simulé" in rep.error
    assert reveil_events(env) == ["reveil_started"]
    return rep


def test_reprise_d_un_reveil_interrompu_sans_double_decision_ni_double_fill(tmp_path: Path):
    x = aleatoire_tick()
    clean = make_env(tmp_path, "clean")
    dc = prepare(clean, x, deciders(buy_eth_at_reveil))
    assert tick(clean, x, dc).reveil == "completed"
    for after in (HAIKU, "temoin:aleatoire"):
        env = make_env(tmp_path, f"crash-{after[-3:]}")
        d = prepare(env, x, deciders(buy_eth_at_reveil))
        crashed_reveil(env, d, x, after)
        assert ("panique", "reveil_exception") in codes(env)
        rep = tick(env, x + 300, d)
        assert rep.reveil == "resumed" and rep.status == "done"
        assert reveil_events(env) == ["reveil_started", "reveil_completed"]
        assert pl(env, "reveil_completed") == [{"reveil": x}]
        assert ("info", "reveil_resumed") in codes(env)
        assert of(env, "veille")[-1]["payload"]["reveil"] is None  # la reprise ne lance pas de nouveau réveil
        ids = [f["payload"]["order_id"] for f in of(env, "fill")]
        assert len(ids) == len(set(ids)), "double fill après la reprise"
        assert sorted(ids) == sorted(f["payload"]["order_id"] for f in of(clean, "fill"))
        assert replay(env.events()) == replay(clean.events())
        for p in LLM_ALL:  # une seule décision par portefeuille et par réveil
            assert len([r for r in pl(env, "decision_received") if r["cycle"] == x and r["portfolio"] == p]) == 1
        if after == HAIKU:  # sa décision était journalisée avant le crash : jamais redemandée à la reprise
            assert d[HAIKU].calls == 2  # cycle 0 + réveil
        # 7. Les quotes du réveil sont relus à la reprise, pas journalisés une seconde fois.
        assert len(of(env, "quote_reveil")) == 6
        check_journal(env)


def test_reprise_sur_les_quotes_d_origine_jamais_reecrits(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X, deciders(buy_eth_at_reveil))
    d[SONNET].plan = buy_eth_at_reveil  # Sonnet décide à la reprise, Haiku avant le crash
    crashed_reveil(env, d, X, HAIKU)
    origine = {e["payload"]["symbol"]: [e["payload"]["bid"], e["payload"]["ask"]] for e in of(env, "quote_reveil")}
    assert origine["ETH/EUR"] == veille_p(env)["quotes"]["ETH/EUR"]
    eth = origine["ETH/EUR"]
    env.kraken.override["ETH/EUR"] = (eth[0] * 101 // 100, eth[1] * 101 // 100)  # le marché a bougé de 1 % depuis
    rep = tick(env, X + 300, d)
    assert rep.reveil == "resumed"
    again = {e["payload"]["symbol"]: [e["payload"]["bid"], e["payload"]["ask"]] for e in of(env, "quote_reveil")}
    assert len(of(env, "quote_reveil")) == 6 and again == origine  # rien de réécrit
    fills = {f["portfolio"]: f for f in pl(env, "fill") if f["side"] == "buy" and f["symbol"] == "ETH/EUR" and f["ts"] == X}
    assert HAIKU in fills and SONNET in fills
    assert fills[HAIKU]["price_ueur"] == fills[SONNET]["price_ueur"]  # tous les modèles ont vu les mêmes quotes
    assert fills[SONNET]["price_ueur"] < eth[1] * 101 // 100  # et pas ceux du tick de reprise
    check_journal(env)


def test_reprise_apres_un_crash_pendant_l_ecriture_des_quotes_complete_depuis_le_tick_d_origine(tmp_path: Path, monkeypatch):
    env = make_env(tmp_path)
    d = prepare(env, X, deciders(buy_eth_at_reveil))
    real, n = Journal.append, []

    def flaky(self, type, payload, ts):
        if type == "quote_reveil" and len(n) == 2:
            raise RuntimeError("crash au 3e quote")
        if type == "quote_reveil":
            n.append(payload.symbol)
        return real(self, type, payload, ts)

    monkeypatch.setattr(Journal, "append", flaky)
    assert tick(env, X, d).status == "reveil_failed"
    monkeypatch.undo()
    first = [e["payload"] for e in of(env, "quote_reveil")]
    assert [q["symbol"] for q in first] == n and len(n) == 2
    origine = veille_p(env)["quotes"]
    env.kraken.override["SOL/EUR"] = (1, 2)  # le marché a changé depuis (et c'est invalide) : sans effet sur la reprise
    rep = tick(env, X + 300, d)
    assert rep.reveil == "resumed"
    after = [e["payload"] for e in of(env, "quote_reveil")]
    assert after[:2] == first and len(after) == 6  # jamais réécrits ; les 4 manquants complétés
    assert {q["symbol"]: [q["bid"], q["ask"]] for q in after} == origine  # depuis les quotes acceptés du tick d'origine
    assert {q["ts"] for q in after[2:]} == {X}
    check_journal(env)


def test_reveil_abandonne_apres_30_minutes_et_repris_avant(tmp_path: Path):
    x = aleatoire_tick()
    env = make_env(tmp_path, "tard")
    d = prepare(env, x)
    crashed_reveil(env, d, x)
    n_fills = len(of(env, "fill"))
    rep = tick(env, x + 2100, d)  # 35 min après : trop tard
    assert rep.reveil == "abandonne" and rep.status == "done"
    assert reveil_events(env) == ["reveil_started", "reveil_abandonne"]
    assert pl(env, "reveil_abandonne") == [{"reveil": x}]
    assert ("action", "reveil_abandonne") in codes(env)
    assert len(of(env, "fill")) == n_fills
    tick(env, x + 2400, d)
    assert reveil_events(env) == ["reveil_started", "reveil_abandonne"]  # pas d'abandon répété
    assert len([c for c in codes(env) if c[1] == "reveil_abandonne"]) == 1
    check_journal(env)
    env2 = make_env(tmp_path, "juste")
    d2 = prepare(env2, x)
    crashed_reveil(env2, d2, x)
    assert tick(env2, x + 1800, d2).reveil == "resumed"  # 30 min pile : encore repris
    assert reveil_events(env2) == ["reveil_started", "reveil_completed"]


def test_un_reveil_est_abandonne_et_non_repris_si_un_cycle_a_ete_termine_depuis(tmp_path: Path):
    x = aleatoire_tick()
    env = make_env(tmp_path)
    d = prepare(env, x)
    crashed_reveil(env, d, x)
    Journal(env.paths.journal).append("cycle_completed", {"cycle": T0 + H4}, x + 100)
    rep = tick(env, x + 300, d)  # dans les 30 min, mais un cycle a été terminé après reveil_started
    assert rep.reveil == "abandonne" and reveil_events(env) == ["reveil_started", "reveil_abandonne"]
    assert ("info", "reveil_resumed") not in codes(env)


@pytest.mark.parametrize("cut", ["stop_set", "fill"])
def test_abandon_repare_la_ronde_interrompue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cut: str):
    env = make_env(tmp_path)
    d = prepare(env, X, deciders(buy_eth_at_reveil))
    real, hit = Journal.append, []

    def flaky(self, type, payload, ts):
        if type == cut and ts == X and not hit:
            hit.append(1)
            raise RuntimeError("crash entre deux écritures")
        return real(self, type, payload, ts)

    monkeypatch.setattr(Journal, "append", flaky)
    assert tick(env, X, d).status == "reveil_failed"
    monkeypatch.undo()
    intent = next(p for p in pl(env, "intent") if p["cycle"] == X and p["portfolio"] == HAIKU)
    oid = intent["intent_id"]
    states = lambda: [s["state"] for s in pl(env, "order_state") if s["order_id"] == oid]
    if cut == "stop_set":  # fill écrit, stop_set manquant
        assert "ETH/EUR" in replay(env.events())[HAIKU].positions
        assert replay(env.events())[HAIKU].positions["ETH/EUR"].stop_ueur is None
        assert states() == ["SUBMITTING", "ACKED"]
    else:  # ordre ACKED sans fill
        assert "ETH/EUR" not in replay(env.events())[HAIKU].positions
        assert states() == ["SUBMITTING", "ACKED"]
    rep = tick(env, X + 2100, d)
    assert rep.reveil == "abandonne"
    st = replay(env.events())[HAIKU]
    if cut == "stop_set":
        pos = st.positions["ETH/EUR"]
        assert pos.stop_ueur is not None and pos.stop_ueur > 0  # la position a son stop
        assert pl(env, "stop_set")[-1]["symbol"] == "ETH/EUR"
        assert states() == ["SUBMITTING", "ACKED", "FILLED"]
    else:
        assert "ETH/EUR" not in st.positions
        assert states() == ["SUBMITTING", "ACKED", "UNKNOWN", "CANCELED"]
    ids = [f["order_id"] for f in pl(env, "fill")]
    assert len(ids) == len(set(ids))
    assert reveil_events(env) == ["reveil_started", "reveil_abandonne"]
    check_journal(env)


# ---------------------------------------------------------------------------------------------- cycle après réveils


def run_scenario(env: Env) -> dict:
    d = prepare(env, X, deciders(buy_eth_at_reveil))
    tick(env, X, d)
    env.kraken.override.clear()
    cycle(env, 1, d)
    return d


def test_un_cycle_apres_des_reveils_reste_deterministe_et_ne_touche_pas_les_references(tmp_path: Path):
    a, b, c = make_env(tmp_path, "a"), make_env(tmp_path, "b"), make_env(tmp_path, "c")
    run_scenario(a)
    run_scenario(b)
    assert verify(a.paths.journal).head_hash == verify(b.paths.journal).head_hash
    cycle(c, 0)  # sans veille ni réveil
    cycle(c, 1)
    sa, sc = replay(a.events()), replay(c.events())
    assert {p: sa[p] for p in REFS} == {p: sc[p] for p in REFS}
    eq1 = [e["payload"]["portfolio"] for e in a.of_type("equity") if e["payload"]["cycle"] == T0 + H4]
    assert sorted(eq1) == sorted(sc)
    assert len(a.of_type("cycle_completed")) == 2
    check_journal(a)


def test_replay_et_verify_apres_une_journee_de_veille_et_de_reveils(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X, deciders(buy_eth_at_reveil))
    tick(env, X, d)
    env.kraken.override.clear()
    for k in range(1, 12):
        tick(env, X + 300 * k, d)
    cycle(env, 1, d)
    for k in range(1, 6):
        tick(env, T0 + H4 + 600 + 300 * k, d)
    assert len(of(env, "veille")) == 1 + 1 + 11 + 5
    check_journal(env)


# ---------------------------------------------------------------------------------------------- 11. exploitation


def test_veille_data_une_alerte_au_debut_de_la_panne_une_info_au_retablissement(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    size = env.paths.journal.stat().st_size
    env.kraken.fail_ticker = True
    for k in range(2):
        assert tick(env, T0 + 600 + 300 * k).status == "failed"
    assert env.paths.journal.stat().st_size == size and not [c for c in codes(env) if c[1] == "veille_data"]
    tick(env, T0 + 1200)  # troisième échec consécutif : début de la panne
    assert [c for c in codes(env) if c[1] == "veille_data"] == [("action", "veille_data")]
    for k in range(10):  # rien entre le début et le rétablissement, même des heures plus tard
        tick(env, T0 + 1500 + 1200 * k)
    assert [c for c in codes(env) if c[1] == "veille_data"] == [("action", "veille_data")]
    assert (env.paths.var / "veille_echecs").read_text() == "13"
    env.kraken.fail_ticker = False
    assert tick(env, T0 + 20_000).status == "done"
    assert [c for c in codes(env) if c[1] == "veille_data"] == [("action", "veille_data"), ("info", "veille_data")]
    assert not (env.paths.var / "veille_echecs").exists()
    env.kraken.fail_ticker = True  # nouvelle panne : le compteur repart de zéro
    tick(env, T0 + 20_300)
    tick(env, T0 + 20_600)
    assert len([c for c in codes(env) if c[1] == "veille_data"]) == 2
    tick(env, T0 + 20_900)
    assert len([c for c in codes(env) if c[1] == "veille_data"]) == 3
    check_journal(env)


def test_journal_casse_rien_ecrit_code_1_une_alerte_panique_par_heure(tmp_path: Path):
    env = make_env(tmp_path, secrets={"ntfy_url": "https://ntfy.example/arene"})
    cycle(env, 0)
    p = env.paths.journal
    lines = p.read_bytes().split(b"\n")
    lines[3] = lines[3].replace(b'"type"', b'"tYpe"', 1)
    p.write_bytes(b"\n".join(lines))
    before = p.read_bytes()
    env.requests.clear()
    rep = tick(env, T0 + 600)
    assert rep.status == "refused" and not rep.ok and p.read_bytes() == before
    sent = lambda: [(r.method, str(r.url), r.headers.get("priority")) for r in env.requests]
    assert sent() == [("POST", "https://ntfy.example/arene", "5")]
    tick(env, T0 + 900)
    tick(env, T0 + 600 + 3599)
    assert len(sent()) == 1 and p.read_bytes() == before
    tick(env, T0 + 600 + 3600)
    assert len(sent()) == 2 and p.read_bytes() == before


def test_le_cycle_alerte_une_fois_par_absence_de_la_veille(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    cycle(env, 1)
    assert "veille_absente" not in [c[1] for c in codes(env)]  # jamais de veille : le timer n'est pas censé tourner
    tick(env, T0 + H4 + 600)
    cycle(env, 2)  # dernier tick à 4 h de là
    assert [c for c in codes(env) if c[1] == "veille_absente"] == [("action", "veille_absente")]
    cycle(env, 3)  # toujours absente : pas de seconde alerte
    assert len([c for c in codes(env) if c[1] == "veille_absente"]) == 1
    tick(env, T0 + 3 * H4 + 600)  # la veille revient puis s'arrête de nouveau
    cycle(env, 4)
    assert len([c for c in codes(env) if c[1] == "veille_absente"]) == 2
    # Veille récente (moins de 30 min) : pas d'alerte.
    tick(env, T0 + 4 * H4 + 900)
    n = len(codes(env))
    env.clock.now = env.now_of(5)
    tick(env, env.now_of(5) - 330)  # HH:00:00 + ... tick du créneau précédent le cycle
    cycle(env, 5)
    assert len([c for c in codes(env) if c[1] == "veille_absente"]) == 2 and len(codes(env)) >= n


def test_smoke_snapshot_utilise_le_meme_prochain_rendez_vous_que_le_cycle(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    snap = cyc.smoke_snapshot(env.paths, env.clients, HAIKU, T0 + H4 + 600)
    assert snap["contexte"] == cyc.rendez_vous_contexte(T0 + H4, load_config(env.paths.config))
    assert snap["contexte"] == {"type": "rendez_vous", "prochain_rendez_vous_ts": T0 + 2 * H4 + 300}


# ---------------------------------------------------------------------------------------------- config


def test_config_veille_valeurs_par_defaut_et_validation(tmp_path: Path):
    cfg = load_config(REPO / "config" / "arene.toml")
    v = cfg.veille
    assert (v.tick_s, v.seuil_mouvement_bp, v.fenetre_mouvement_s) == (300, 300, 3600)
    assert (v.cooldown_s, v.max_reveils_jour, v.garde_avant_cycle_s) == (3600, 6, 1800)
    text = (REPO / "config" / "arene.toml").read_text()
    sans = re.sub(r"\[veille\].*?(?=\[\[instruments\]\])", "", text, flags=re.DOTALL)
    assert "[veille]" not in sans
    p = tmp_path / "c.toml"
    p.write_text(sans)
    assert load_config(p).veille == v  # table absente : valeurs par défaut
    p.write_text(text.replace("seuil_mouvement_bp = 300", "seuil_mouvement_bp = 150"))
    assert load_config(p).veille.seuil_mouvement_bp == 150
    for bad in ("seuil_mouvement_bp = 0", "cooldown_s = -1", 'tick_s = "300"', "tick_s = 7", "inconnue = 1", "tick_s = 3.5"):
        key = bad.split(" = ")[0]
        mutated = re.sub(rf"^{key} = .*$", bad, text, flags=re.MULTILINE) if key != "inconnue" else text.replace("[veille]", "[veille]\n" + bad)
        p.write_text(mutated)
        with pytest.raises(ConfigError):
            load_config(p)


# ---------------------------------------------------------------------------------------------- 10. CLI et site


def cli_args(env: Env) -> list[str]:
    return ["--var", str(env.paths.var), "--secrets", str(env.paths.secrets), "--config", str(env.paths.config),
            "--policy", str(env.paths.policy)]  # fmt: skip


def fake_systemctl(monkeypatch: pytest.MonkeyPatch, calls: list, error: Exception | None = None) -> None:
    """Remplace subprocess.run pour `systemctl` seulement (git rev-parse du cycle garde le vrai)."""
    real = subprocess.run

    def run(cmd, **kw):
        if cmd[0] != "systemctl":
            return real(cmd, **kw)
        calls.append(cmd)
        if error is not None:
            raise error
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(cli.subprocess, "run", run)


def test_commande_arene_veille_codes_de_sortie(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []
    fake_systemctl(monkeypatch, calls)
    env = make_env(tmp_path)
    cycle(env, 0)

    def run(ts: int, *extra: str) -> int:
        env.clock.now = ts
        return cli.main([*cli_args(env), "veille", *extra], clients=env.clients, now=lambda: ts)

    assert run(T0 + 630) == 0
    assert run(T0 + 640) == 0  # déjà fait
    with cycle_lock(env.paths):
        assert run(T0 + 930) == 0  # occupé : code 0
    env.kraken.fail_ticker = True
    assert run(T0 + 1230) == 1  # aucun quote valide : code 1
    assert calls == []  # aucun réveil : pas de reconstruction du site


def test_apres_un_reveil_le_site_est_reconstruit_par_systemd_pas_dans_le_processus(tmp_path: Path, monkeypatch):
    calls: list[list[str]] = []
    fake_systemctl(monkeypatch, calls)
    monkeypatch.setattr(cli, "_build_site", lambda *a, **k: pytest.fail("le site ne se construit plus dans la veille"))
    monkeypatch.setattr(cyc, "default_deciders", lambda cfg, paths: deciders())
    for name, extra, expected in [
        ("avec", [], [["systemctl", "--user", "start", "--no-block", "arene-site-build.service"]]),
        ("sans", ["--no-site"], []),
    ]:
        calls.clear()
        env = make_env(tmp_path, name)
        prepare(env, X)
        env.clock.now = X + 30
        assert cli.main([*cli_args(env), "veille", *extra], clients=env.clients, now=lambda: X + 30) == 0
        assert pl(env, "reveil_completed") == [{"reveil": X}]
        assert calls == expected


def test_echec_du_lancement_du_site_ignore_et_pas_dans_le_journal(tmp_path: Path, monkeypatch, caplog):
    fake_systemctl(monkeypatch, [], FileNotFoundError("systemctl"))
    monkeypatch.setattr(cyc, "default_deciders", lambda cfg, paths: deciders())
    env = make_env(tmp_path)
    prepare(env, X)
    env.clock.now = X + 30
    n_alerts = len(codes(env))
    with caplog.at_level("WARNING", logger="arene.cli"):
        assert cli.main([*cli_args(env), "veille"], clients=env.clients, now=lambda: X + 30) == 0
    assert "reconstruction du site non lancée" in caplog.text
    assert len(codes(env)) == n_alerts  # rien dans le journal
    fake_systemctl(monkeypatch, [], subprocess.CalledProcessError(1, "systemctl"))
    cli._start_site_build()  # ne lève pas
