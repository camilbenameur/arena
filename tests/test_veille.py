"""Veille continue et réveils (docs/VEILLE.md) : vrai journal en dossier temporaire, marché et décideurs factices.

Frise commune : cycle 0 à T0+300 (terminé à T0+300), tick de référence R, tick X = R + 3600 où le mouvement joue.
Fenêtre où un réveil est permis après le cycle 0 : de T0+3900 (délai de 3600 s) à T0+12900 (30 min avant le
rendez-vous de T0+14700). Aucun test n'appelle `claude -p` ni le réseau.
"""

from __future__ import annotations

import random
import re
from pathlib import Path

import pytest

from arene import cli
from arene import cycle as cyc
from arene.config import ConfigError, load_config
from arene.cycle import cycle_lock, run_cycle
from arene.deciders.snapshot import SCHEMA_VERSION
from arene.journal import Journal, verify
from arene.ledger import equity_ueur, replay
from arene.paths import REPO
from arene.sim.fills import market_fill
from arene.temoins.aleatoire import seed_for
from arene.types import Instrument, Quote, Side, notional_ueur
from arene.veille import mouvement, prochain_rendez_vous, run_veille
from tests.fakes import (
    H4,
    HAIKU,
    OPUS,
    SONNET,
    SYMBOLS,
    T0,
    Env,
    FakeKraken,
    NoKeyDecider,
    ScriptedDecider,
    action,
)

REFS = ("temoin:panier", "temoin:6040", "temoin:e0065")
BTC = "BTC/EUR"
BTC_REF = 1_000_000_000  # milieu de référence de BTC aux ticks de test : 1 000 EUR, pour des seuils exacts
BTC_INST = Instrument("BTC/EUR", "XBTEUR", "BTCUSDT", 100_000, 6_000, 450_000)


class LiveKraken(FakeKraken):
    """Marché factice dont le ticker peut être forcé symbole par symbole (mouvement intra-barre)."""

    def __init__(self, clock) -> None:
        super().__init__(clock)
        self.override: dict[str, tuple[int, int]] = {}

    def ticker(self, symbol: str, pair: str) -> Quote:
        if symbol in self.override:
            bid, ask = self.override[symbol]
            return Quote(symbol, self.clock.now, bid, ask)
        return super().ticker(symbol, pair)


class Recorder(ScriptedDecider):
    def __init__(self, model: str, portfolio: str, plan) -> None:
        super().__init__(model, portfolio, plan)
        self.spent: list[int] = []
        self.snaps: list[dict] = []

    def decide(self, snapshot: dict, spent_today_uusd: int):
        self.spent.append(spent_today_uusd)
        self.snaps.append(snapshot)
        return super().decide(snapshot, spent_today_uusd)


def make_env(tmp_path: Path, name: str = "e") -> Env:
    env = Env(tmp_path / name)
    env.kraken = env.clients.kraken = LiveKraken(env.clock)
    return env


def deciders(haiku_plan=None) -> dict:
    return {
        HAIKU: Recorder("claude-haiku-5-5", HAIKU, haiku_plan or (lambda i, s: None)),
        SONNET: Recorder("claude-sonnet-5-5", SONNET, lambda i, s: None),
        OPUS: NoKeyDecider("claude-opus-5-5", OPUS),
    }


def buy_btc_at_cycle_0(i: int, snap: dict):
    return [action(BTC, size=10, stop=5)] if i == 0 and snap["contexte"]["type"] == "rendez_vous" else None


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


def set_veille(env: Env, **kw: int) -> None:
    txt = env.paths.config.read_text()
    for k, v in kw.items():
        txt, n = re.subn(rf"^{k} = \d+", f"{k} = {v}", txt, flags=re.MULTILINE)
        assert n == 1, k
    env.paths.config.write_text(txt)


def set_btc(env: Env, mid: int) -> None:
    env.kraken.override[BTC] = (mid, mid)


def prepare(env: Env, x: int, d: dict | None = None, bp: int = 300) -> dict:
    """Cycle 0, tick de référence R = x - 3600 (BTC à BTC_REF), puis BTC forcé à +bp pour le tick x."""
    d = d if d is not None else deciders()
    cycle(env, 0, d)
    set_btc(env, BTC_REF)
    ref = tick(env, x - 3600, d)
    assert ref.status == "done" and ref.declencheur is None
    set_btc(env, BTC_REF * (10_000 + bp) // 10_000)
    return d


def check_journal(env: Env) -> None:
    rep = verify(env.paths.journal)
    assert rep.ok, rep.errors
    replay(env.events())  # ne lève pas


def reveil_events(env: Env) -> list[str]:
    return [e["type"] for e in env.of_type("reveil_started", "reveil_completed", "reveil_abandonne")]


X = T0 + 4200  # premier tick où le mouvement (référence à T0+600) et les garde-fous permettent un réveil


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
    v = of(env, "veille")[-1]
    p = v["payload"]
    assert set(p) == {"tick", "quotes", "equity", "stops", "reveil"}
    assert p["stops"] == [] and p["reveil"] is None
    assert set(p["quotes"]) == set(SYMBOLS)
    q = env.kraken.ticker("ETH/EUR", "ETHEUR")
    assert p["quotes"]["ETH/EUR"] == [q.bid, q.ask]
    bids = {s: b for s, (b, _a) in p["quotes"].items()}
    marks = {s: (b + a) // 2 for s, (b, a) in p["quotes"].items()}
    states = replay(before)
    assert p["equity"] == {name: equity_ueur(st, marks, bids) for name, st in sorted(states.items())}
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


def test_journal_casse_rien_ecrit_code_1(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    p = env.paths.journal
    lines = p.read_bytes().split(b"\n")
    lines[3] = lines[3].replace(b'"type"', b'"tYpe"', 1)
    p.write_bytes(b"\n".join(lines))
    before = p.read_bytes()
    rep = tick(env, T0 + 600)
    assert rep.status == "refused" and not rep.ok and p.read_bytes() == before
    assert not env.requests


def test_avant_le_premier_cycle_la_veille_n_ecrit_rien(tmp_path: Path):
    env = make_env(tmp_path)
    rep = tick(env, T0 + 600)
    assert rep.status == "inactive" and rep.ok and not env.paths.journal.exists()


def test_quotes_en_echec_rien_ecrit_alerte_apres_trois_ticks_une_par_heure(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    size = env.paths.journal.stat().st_size
    env.kraken.fail_ticker = True
    for k in range(2):
        rep = tick(env, T0 + 600 + 300 * k)
        assert rep.status == "failed" and not rep.ok
    assert env.paths.journal.stat().st_size == size
    tick(env, T0 + 1200)  # troisième échec consécutif
    alerts = [a for a in pl(env, "alert") if a["code"] == "veille_data"]
    assert len(alerts) == 1 and alerts[0]["level"] == "action"
    tick(env, T0 + 1500)
    assert len([a for a in pl(env, "alert") if a["code"] == "veille_data"]) == 1  # au plus une par heure
    assert not of(env, "veille")
    tick(env, T0 + 1200 + 3600)
    assert len([a for a in pl(env, "alert") if a["code"] == "veille_data"]) == 2
    env.kraken.fail_ticker = False
    assert tick(env, T0 + 6000).status == "done"
    env.kraken.fail_ticker = True
    tick(env, T0 + 6300)  # le compteur est reparti de zéro : un seul échec
    assert len([a for a in pl(env, "alert") if a["code"] == "veille_data"]) == 2
    check_journal(env)


def test_mediane_des_spreads_du_cycle_inchangee_par_la_veille(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    quotes_before = of(env, "quote")
    for k in range(6):
        set_btc(env, BTC_REF + k * 1000)
        tick(env, T0 + 600 + 300 * k)
    assert of(env, "quote") == quotes_before  # la veille ne journalise aucun `quote`

    def medians(events):
        spreads: dict[str, list[int]] = {}
        for e in events:
            spreads.setdefault(e["payload"]["symbol"], []).append(e["payload"]["ask"] - e["payload"]["bid"])
        return {s: sorted(v[-20:])[len(v[-20:]) // 2] for s, v in spreads.items()}

    assert medians(of(env, "quote")) == medians(quotes_before)
    assert len(of(env, "veille")) == 6


# ---------------------------------------------------------------------------------------------- stops en direct


def stop_of(env: Env, portfolio: str = HAIKU, symbol: str = BTC) -> int:
    return [s for s in pl(env, "stop_set") if s["portfolio"] == portfolio and s["symbol"] == symbol][-1]["stop_ueur"]


def test_stop_execute_au_bid_avec_glissement_et_frais_sans_double_vente(tmp_path: Path):
    env = make_env(tmp_path)
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    qty = replay(env.events())[HAIKU].positions[BTC].qty
    stop = stop_of(env)
    bid = stop - 1_000_000
    env.kraken.override[BTC] = (bid, bid + 100_000)
    r = T0 + 600
    rep = tick(env, r, d)
    oid = f"stop:{HAIKU}:{BTC}:veille:{r}"
    assert oid in rep.stops
    fill = next(f for f in pl(env, "fill") if f["order_id"] == oid)
    px = bid * (10_000 - 5) // 10_000 // 100_000 * 100_000  # glissement 5 bp, tick vers le bas
    fee = -(-notional_ueur(qty, px, round_up=True) * 50 // 10_000)  # frais taker 50 bp, vers le haut
    assert (fill["side"], fill["qty"], fill["price_ueur"], fill["fee_ueur"], fill["ts"], fill["reason"]) == (
        "sell", qty, px, fee, r, "stop",
    )  # fmt: skip
    assert (px, fee) == market_fill(Side.SELL, qty, Quote(BTC, r, bid, bid + 100_000), BTC_INST, 50, 5)
    assert BTC not in replay(env.events())[HAIKU].positions
    assert of(env, "veille")[-1]["payload"]["stops"] == rep.stops
    # Le glissement est bien compté : le prix de vente est sous le bid, pas au niveau du stop.
    assert px < bid
    n_fills = len(of(env, "fill"))
    tick(env, r)  # même tick : rien de plus
    assert len(of(env, "fill")) == n_fills

    # Le cycle suivant voit la barre T0 sous le stop (krach de 6 %) : la position est déjà vendue, pas de seconde vente.
    env.kraken.override.clear()
    env.kraken.crash(BTC, T0, 940)
    cycle(env, 1, d)
    haiku_btc = [f for f in pl(env, "fill") if f["portfolio"] == HAIKU and f["symbol"] == BTC and f["side"] == "sell"]
    assert [f["order_id"] for f in haiku_btc] == [oid]
    assert not [f for f in pl(env, "fill") if f["order_id"] == f"stop:{HAIKU}:{BTC}:{T0}"]
    check_journal(env)


def test_position_rachetee_apres_un_stop_de_veille_reste_geree(tmp_path: Path):
    env = make_env(tmp_path)

    def plan(i, snap):
        return [action(BTC, size=10, stop=5)] if i in (0, 1) else None

    d = deciders(plan)
    cycle(env, 0, d)
    stop0 = stop_of(env)
    env.kraken.override[BTC] = (stop0 - 1_000_000, stop0 - 900_000)
    r = T0 + 600
    tick(env, r, d)
    assert BTC not in replay(env.events())[HAIKU].positions
    env.kraken.override.clear()
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


# ---------------------------------------------------------------------------------------------- déclencheurs


@pytest.mark.parametrize(("bp", "reveil"), [(299, False), (300, True), (-300, True), (-299, False)])
def test_declencheur_de_mouvement_au_seuil_exact(tmp_path: Path, bp: int, reveil: bool):
    env = make_env(tmp_path)
    d = prepare(env, X, bp=bp)
    rep = tick(env, X, d)
    trig = {"type": "mouvement", "symbole": BTC, "variation_bp": bp, "fenetre_s": 3600}
    if reveil:
        assert rep.declencheur == trig and rep.reveil == "completed"
        assert of(env, "veille")[-1]["payload"]["reveil"] == trig
        assert pl(env, "reveil_started") == [{"reveil": X, "declencheur": trig}]
    else:
        assert rep.declencheur is None and rep.reveil is None
        assert of(env, "veille")[-1]["payload"]["reveil"] is None
        assert not reveil_events(env)


def test_mouvement_fonction_pure_le_plus_grand_l_emporte_et_sans_reference_rien():
    cur = {"A": (1_040_000, 1_040_000), "B": (900_000, 900_000), "C": (1_000_000, 1_000_000)}
    ref = {"A": (1_000_000, 1_000_000), "B": (1_000_000, 1_000_000), "C": (1_000_000, 1_000_000)}
    assert mouvement(cur, ref, 300, 3600) == {"type": "mouvement", "symbole": "B", "variation_bp": -1000, "fenetre_s": 3600}
    assert mouvement(cur, {}, 300, 3600) is None
    assert mouvement({"A": (1_029_900, 1_029_900)}, {"A": (1_000_000, 1_000_000)}, 300, 3600) is None
    assert mouvement({"A": (1_030_000, 1_030_000)}, {"A": (1_000_000, 1_000_000)}, 300, 3600)["variation_bp"] == 300


def test_pas_de_declencheur_de_mouvement_sans_veille_de_reference(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)
    set_btc(env, BTC_REF * 2)  # +100 % mais aucun événement veille à X - 3600
    rep = tick(env, X)
    assert rep.declencheur is None and not reveil_events(env)


def test_declencheur_de_stop_sur_un_portefeuille_llm_et_pas_sur_un_temoin(tmp_path: Path):
    # LLM : le stop de Haiku déclenche un réveil.
    env = make_env(tmp_path, "llm")
    d = deciders(buy_btc_at_cycle_0)
    cycle(env, 0, d)
    stop = stop_of(env)
    env.kraken.override[BTC] = (stop - 1_000_000, stop - 900_000)
    rep = tick(env, X, d)
    trig = {"type": "stop", "portefeuille": HAIKU, "symbole": BTC}
    assert rep.declencheur == trig and rep.reveil == "completed"
    assert pl(env, "reveil_started") == [{"reveil": X, "declencheur": trig}]
    assert of(env, "veille")[-1]["payload"]["reveil"] == trig

    # Témoin : son stop est exécuté par la veille mais ne réveille personne.
    env2 = make_env(tmp_path, "temoin")
    cycle(env2, 0)
    assert BTC in replay(env2.events())["temoin:panier"].positions
    low = 2_000_000_000
    Journal(env2.paths.journal).append(
        "stop_set", {"portfolio": "temoin:panier", "symbol": BTC, "stop_ueur": low + 5_000_000}, T0 + 400
    )
    env2.kraken.override[BTC] = (low, low + 100_000)
    rep2 = tick(env2, X)
    assert f"stop:temoin:panier:{BTC}:veille:{X}" in rep2.stops
    assert BTC not in replay(env2.events())["temoin:panier"].positions
    assert rep2.declencheur is None and rep2.reveil is None and not reveil_events(env2)
    assert of(env2, "veille")[-1]["payload"]["reveil"] is None
    check_journal(env2)


# ---------------------------------------------------------------------------------------------- garde-fous


def test_garde_fou_delai_depuis_la_derniere_ronde(tmp_path: Path):
    last = T0 + 300  # fin du cycle 0
    for cooldown, ok in [(X - last + 1, False), (X - last, True)]:  # 3901 s refuse, 3900 s passe (pas de "<")
        env = make_env(tmp_path, f"cd{cooldown}")
        set_veille(env, cooldown_s=cooldown)
        d = prepare(env, X)
        rep = tick(env, X, d)
        assert rep.declencheur is not None
        assert (rep.refus, rep.reveil) == ((None, "completed") if ok else ("cooldown", None))
        assert bool(reveil_events(env)) is ok
        assert of(env, "veille")[-1]["payload"]["reveil"] == (rep.declencheur if ok else None)


def test_le_delai_compte_aussi_les_reveils(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X)
    assert tick(env, X, d).reveil == "completed"  # terminé à X + 30
    # Nouveau mouvement de +3 % par rapport à la veille de X, une heure plus tard : 3570 s après la dernière ronde.
    set_btc(env, BTC_REF * 10_300 // 10_000 * 10_300 // 10_000)
    rep = tick(env, X + 3600, d)
    assert rep.declencheur is not None and rep.refus == "cooldown" and rep.reveil is None
    assert len(of(env, "reveil_started")) == 1


def test_garde_fou_plafond_par_jour(tmp_path: Path):
    for cap, ok in [(1, False), (2, True)]:
        env = make_env(tmp_path, f"cap{cap}")
        set_veille(env, max_reveils_jour=cap)
        d = prepare(env, X)
        j = Journal(env.paths.journal)
        j.append("reveil_started", {"reveil": T0 + 150, "declencheur": {"type": "stop", "portefeuille": HAIKU, "symbole": BTC}}, T0 + 160)
        j.append("reveil_completed", {"reveil": T0 + 150}, T0 + 200)  # un réveil plus tôt dans le même jour UTC
        rep = tick(env, X, d)
        assert (rep.refus, rep.reveil) == ((None, "completed") if ok else ("plafond_jour", None))
    # Un réveil de la veille (jour UTC précédent) ne compte pas.
    env = make_env(tmp_path, "veille-jour")
    set_veille(env, max_reveils_jour=1)
    d = prepare(env, X)
    j = Journal(env.paths.journal)
    j.append("reveil_started", {"reveil": T0 - 5000, "declencheur": {"type": "stop", "portefeuille": HAIKU, "symbole": BTC}}, T0 + 160)
    j.append("reveil_completed", {"reveil": T0 - 5000}, T0 + 170)
    assert tick(env, X, d).reveil == "completed"


def test_garde_fou_avant_le_cycle(tmp_path: Path):
    rdv = T0 + H4 + 300
    assert prochain_rendez_vous(T0 + 4200, H4, 300) == rdv
    assert prochain_rendez_vous(T0 + 300, H4, 300) == rdv  # à HH:05 pile, le prochain est dans 4 h
    assert prochain_rendez_vous(T0, H4, 300) == T0 + 300
    for x, ok in [(rdv - 1800, True), (rdv - 1500, False)]:  # 1800 s avant passe, 1500 s avant refuse
        env = make_env(tmp_path, f"av{x}")
        d = prepare(env, x)
        rep = tick(env, x, d)
        assert rep.declencheur is not None
        assert (rep.refus, rep.reveil) == ((None, "completed") if ok else ("avant_cycle", None))
        assert of(env, "veille")[-1]["payload"]["reveil"] == (rep.declencheur if ok else None)


def test_garde_fou_cycle_incomplet(tmp_path: Path):
    env = make_env(tmp_path)
    cycle(env, 0)

    def boom(p: str) -> None:
        raise RuntimeError("crash simulé")

    assert cycle(env, 1, on_portfolio_done=boom).status == "failed"  # cycle_started sans cycle_completed
    x = T0 + H4 + 4200
    set_btc(env, BTC_REF)
    tick(env, x - 3600)
    set_btc(env, BTC_REF * 10_300 // 10_000)
    rep = tick(env, x)
    assert rep.declencheur is not None and rep.refus == "cycle" and rep.reveil is None
    assert not reveil_events(env)
    # Le cycle repris et terminé lève ce garde-fou.
    set_btc(env, BTC_REF)
    env.kraken.override.clear()
    assert cycle(env, 1).status == "completed"


def test_pas_de_reveil_pendant_un_cycle_en_cours(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X)
    before = env.paths.journal.read_bytes()
    with cycle_lock(env.paths):  # un cycle (ou un réveil) tient le verrou
        rep = tick(env, X, d)
    assert rep.status == "busy" and env.paths.journal.read_bytes() == before


# ---------------------------------------------------------------------------------------------- le réveil


def aleatoire_tick() -> int:
    """Premier tick X' >= X où le tirage de l'aléatoire donne au moins une action (cherché, pas supposé)."""
    for k in range(40):
        x = X + 300 * k
        if x <= T0 + 12900 and random.Random(seed_for(x, 0)).randrange(3) >= 1:
            return x
    raise AssertionError("aucun tick favorable")


def test_le_reveil_fait_decider_llm_et_aleatoire_pas_les_references_sans_equity(tmp_path: Path):
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
    i0 = max(i for i, t in enumerate(types) if t == "reveil_started")
    assert types[i0 + 1:].count("reveil_completed") == 1 and types.index("reveil_completed") > i0
    after = [e for e in env.events()[i0:]]
    # Quotes journalisées avant la décision, comme au cycle.
    qs = [e for e in after if e["type"] == "quote"]
    assert len(qs) == 6 and max(i for i, e in enumerate(after) if e["type"] == "quote") < min(
        i for i, e in enumerate(after) if e["type"] in ("decision_requested", "intent")
    )
    assert {e["payload"]["symbol"]: e["payload"]["bid"] for e in qs}[BTC] == BTC_REF * 10_300 // 10_000
    # LLM : Haiku décide, Sonnet aussi (appel factice), Opus sans clé ; l'identifiant du réveil est le champ `cycle`.
    got = {p["portfolio"] for p in pl(env, "decision_received") if p["cycle"] == x}
    assert got == {HAIKU, SONNET}
    assert {p["portfolio"]: p["reason"] for p in pl(env, "decision_skipped") if p["cycle"] == x} == {OPUS: "no_key"}
    # Aléatoire : ses intentions du tirage, via riskd ; références : rien.
    own = [p for p in pl(env, "intent") if p["cycle"] == x]
    assert len([p for p in own if p["portfolio"] == "temoin:aleatoire"]) == n_alea
    assert {p["portfolio"] for p in own} <= {"temoin:aleatoire", HAIKU, SONNET}
    verdict_ids = {p["intent_id"] for p in pl(env, "risk_verdict")}
    assert {p["intent_id"] for p in own} <= verdict_ids
    refs_after = {p: replay(env.events())[p] for p in REFS}
    assert refs_after == refs_before
    assert not [p for p in own if p["portfolio"] in REFS]
    assert not [f for f in of(env, "fill")[fills_before:] if f["payload"]["portfolio"] in REFS]
    # Pas d'equity au réveil.
    assert len(of(env, "equity")) == equity_before
    # Chaque décideur est appelé une fois par ronde, avec le contexte de réveil.
    snap = d[HAIKU].snaps[-1]
    assert snap["schema_version"] == SCHEMA_VERSION == "2" and snap["cycle_ts"] == x
    check_journal(env)


def test_contexte_dans_l_instantane(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X)
    tick(env, X, d)
    cycle(env, 1, d)
    snaps = d[HAIKU].snaps
    assert [s["contexte"]["type"] for s in snaps] == ["rendez_vous", "reveil", "rendez_vous"]
    assert snaps[0]["contexte"] == {"type": "rendez_vous", "prochain_rendez_vous_ts": T0 + H4 + 300}
    trig = {"type": "mouvement", "symbole": BTC, "variation_bp": 300, "fenetre_s": 3600}
    assert snaps[1]["contexte"] == {"type": "reveil", "declencheur": trig, "prochain_rendez_vous_ts": T0 + H4 + 300}
    assert snaps[2]["contexte"] == {"type": "rendez_vous", "prochain_rendez_vous_ts": T0 + 2 * H4 + 300}
    assert {s["schema_version"] for s in snaps} == {"2"}
    # Les décisions du réveil figurent dans recent_decisions du cycle suivant.
    assert X in [r["cycle"] for r in snaps[2]["recent_decisions"]]
    # Le prompt système parle des réveils.
    from arene.deciders.llm import load_system_prompt

    assert "réveillé entre deux rendez-vous" in load_system_prompt()


def test_budget_quotidien_partage_entre_cycles_et_reveils(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X)  # le cycle 0 a coûté 1500 µ$ à Haiku
    tick(env, X, d)
    cycle(env, 1, d)
    assert d[HAIKU].spent == [0, 1500, 3000]
    assert d[SONNET].spent == [0, 1500, 3000]


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
    rep = tick(env, x, d)
    assert rep.reveil == "completed"
    assert [k["active"] for k in pl(env, "kill_switch")] == [True]
    new = [f for f in pl(env, "fill")[n_fills:]]
    assert new and all(f["side"] == "sell" for f in new)  # aucune entrée, de personne
    assert f"exit:{HAIKU}:LINK/EUR:{x}:kill_switch" in {f["order_id"] for f in new}
    skipped = {p["portfolio"]: p["reason"] for p in pl(env, "decision_skipped") if p["cycle"] == x}
    assert skipped[HAIKU] == skipped[SONNET] == "kill_switch"
    assert not [p for p in pl(env, "decision_received") if p["cycle"] == x and p["portfolio"] == HAIKU]
    verdicts = {v["intent_id"]: v for v in pl(env, "risk_verdict")}
    alea = [p for p in pl(env, "intent") if p["cycle"] == x and p["portfolio"] == "temoin:aleatoire"]
    buys = [p for p in alea if p["side"] == "buy"]
    assert all(not verdicts[p["intent_id"]]["approved"] and "KILL_SWITCH" in verdicts[p["intent_id"]]["reasons"] for p in buys)
    assert not replay(env.events())[HAIKU].positions
    check_journal(env)


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

    def plan(i, snap):
        if snap["contexte"]["type"] == "reveil":
            return [action("ETH/EUR")]
        return None

    clean = make_env(tmp_path, "clean")
    dc = prepare(clean, x, deciders(plan))
    assert tick(clean, x, dc).reveil == "completed"

    for after in (HAIKU, "temoin:aleatoire"):
        env = make_env(tmp_path, f"crash-{after.split(':')[0]}{after[-3:]}")
        d = prepare(env, x, deciders(plan))
        crashed_reveil(env, d, x, after)
        assert ("panique", "reveil_exception") in [(a["level"], a["code"]) for a in pl(env, "alert")]
        rep = tick(env, x + 300, d)
        assert rep.reveil == "resumed" and rep.status == "done"
        assert reveil_events(env) == ["reveil_started", "reveil_completed"]
        assert pl(env, "reveil_completed") == [{"reveil": x}]
        assert ("info", "reveil_resumed") in [(a["level"], a["code"]) for a in pl(env, "alert")]
        assert of(env, "veille")[-1]["payload"]["reveil"] is None  # la reprise ne lance pas de nouveau réveil
        ids = [f["payload"]["order_id"] for f in of(env, "fill")]
        assert len(ids) == len(set(ids)), "double fill après la reprise"
        assert sorted(ids) == sorted(f["payload"]["order_id"] for f in of(clean, "fill"))
        assert replay(env.events()) == replay(clean.events())
        for p in (HAIKU, SONNET):  # une seule décision par portefeuille et par réveil
            assert len([r for r in pl(env, "decision_received") if r["cycle"] == x and r["portfolio"] == p]) == 1
        if after == HAIKU:  # sa décision était journalisée avant le crash : jamais redemandée à la reprise
            assert d[HAIKU].calls == 2  # cycle 0 + réveil
        assert len([q for q in of(env, "quote") if q["ts"] >= x]) == 6  # quotes du réveil non journalisées deux fois
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
    assert ("action", "reveil_abandonne") in [(a["level"], a["code"]) for a in pl(env, "alert")]
    assert len(of(env, "fill")) == n_fills
    tick(env, x + 2400, d)
    assert reveil_events(env) == ["reveil_started", "reveil_abandonne"]  # pas d'abandon répété
    check_journal(env)

    env2 = make_env(tmp_path, "juste")
    d2 = prepare(env2, x)
    crashed_reveil(env2, d2, x)
    assert tick(env2, x + 1800, d2).reveil == "resumed"  # 30 min pile : encore repris
    assert reveil_events(env2) == ["reveil_started", "reveil_completed"]


def test_un_abandon_compte_pour_le_delai_et_le_plafond(tmp_path: Path):
    x = aleatoire_tick()
    env = make_env(tmp_path)
    d = prepare(env, x)
    crashed_reveil(env, d, x)
    tick(env, x + 2100, d)  # abandon, journalisé à l'heure du mur x + 2130
    set_btc(env, BTC_REF * 10_300 // 10_000 * 10_300 // 10_000)
    rep = tick(env, x + 3600, d)  # mouvement de +3 % depuis la veille de x, mais l'abandon est trop récent
    assert rep.declencheur is not None and rep.refus == "cooldown"
    assert reveil_events(env) == ["reveil_started", "reveil_abandonne"]


# ---------------------------------------------------------------------------------------------- cycle après réveils


def run_scenario(env: Env) -> dict:
    d = prepare(env, X, deciders(lambda i, s: [action("ETH/EUR")] if s["contexte"]["type"] == "reveil" else None))
    tick(env, X, d)
    env.kraken.override.clear()
    cycle(env, 1, d)
    return d


def test_un_cycle_apres_des_reveils_reste_deterministe_et_ne_touche_pas_les_references(tmp_path: Path):
    a, b, c = make_env(tmp_path, "a"), make_env(tmp_path, "b"), make_env(tmp_path, "c")
    run_scenario(a)
    run_scenario(b)
    assert verify(a.paths.journal).head_hash == verify(b.paths.journal).head_hash
    # Sans veille ni réveil : les références (aucun réveil pour elles) finissent dans le même état.
    cycle(c, 0)
    cycle(c, 1)
    sa, sc = replay(a.events()), replay(c.events())
    assert {p: sa[p] for p in REFS} == {p: sc[p] for p in REFS}
    # Le cycle 1 a bien tourné normalement : equity pour les 8 portefeuilles, une fois chacun.
    eq1 = [e["payload"]["portfolio"] for e in a.of_type("equity") if e["payload"]["cycle"] == T0 + H4]
    assert sorted(eq1) == sorted(sc)
    assert len([e for e in a.of_type("cycle_completed")]) == 2
    check_journal(a)


def test_replay_et_verify_apres_une_journee_de_veille_et_de_reveils(tmp_path: Path):
    env = make_env(tmp_path)
    d = prepare(env, X, deciders(lambda i, s: [action("ETH/EUR")] if s["contexte"]["type"] == "reveil" else None))
    tick(env, X, d)
    env.kraken.override.clear()
    for k in range(1, 12):
        tick(env, X + 300 * k, d)
    cycle(env, 1, d)
    for k in range(1, 6):
        tick(env, T0 + H4 + 600 + 300 * k, d)
    assert len(of(env, "veille")) == 1 + 1 + 11 + 5
    check_journal(env)


# ---------------------------------------------------------------------------------------------- config, CLI


def test_config_veille_valeurs_par_defaut_et_validation(tmp_path: Path):
    cfg = load_config(REPO / "config" / "arene.toml")
    v = cfg.veille
    assert (v.tick_s, v.seuil_mouvement_bp, v.fenetre_mouvement_s) == (300, 300, 3600)
    assert (v.cooldown_s, v.max_reveils_jour, v.garde_avant_cycle_s) == (3600, 6, 1800)
    assert cyc.LOCK_WAIT_S == 600
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


def cli_args(env: Env) -> list[str]:
    return ["--var", str(env.paths.var), "--secrets", str(env.paths.secrets), "--config", str(env.paths.config),
            "--policy", str(env.paths.policy)]  # fmt: skip


def test_commande_arene_veille_codes_de_sortie(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    built: list[int] = []
    monkeypatch.setattr(cli, "_build_site", lambda paths, clients, now, **kw: built.append(now) or 0)
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
    assert run(T0 + 1230) == 1  # quotes en échec : code 1
    env.kraken.fail_ticker = False
    assert built == []  # aucun réveil : le site n'est pas reconstruit


def test_commande_arene_veille_reconstruit_le_site_apres_un_reveil(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    built: list[int] = []
    monkeypatch.setattr(cli, "_build_site", lambda paths, clients, now, **kw: built.append(now) or 0)
    monkeypatch.setattr(cyc, "default_deciders", lambda cfg, paths: deciders())
    for name, extra, expected in [("avec", [], [X + 30]), ("sans", ["--no-site"], [])]:
        built.clear()
        env = make_env(tmp_path, name)
        prepare(env, X)
        env.clock.now = X + 30
        assert cli.main([*cli_args(env), "veille", *extra], clients=env.clients, now=lambda: X + 30) == 0
        assert pl(env, "reveil_completed") == [{"reveil": X}]
        assert built == expected
