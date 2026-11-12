"""Tests de bout en bout du cycle (docs/SPEC-MVP.md §11) sur un marché synthétique, sans réseau."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from arene.cycle import CycleReport, run_cycle
from arene.deciders.llm import LLMDecider
from arene.journal import Journal, verify
from arene.ledger import equity_ueur, rebuild_sqlite, replay
from arene.sim.executor import SimExecutor
from arene.sim.fills import stop_fill
from arene.types import Instrument
from tests.fakes import (
    DAY,
    H4,
    HAIKU,
    OPUS,
    SONNET,
    SYMBOLS,
    T0,
    Env,
    NoKeyDecider,
    ScriptedDecider,
    action,
    fake_anthropic_client,
    make_deciders,
)

ALL = (HAIKU, SONNET, OPUS, "llm:claude-fable-5-2", "temoin:panier", "temoin:6040", "temoin:e0065", "temoin:aleatoire")


def run_cycles(env: Env, n: int, start: int = 0, deciders=None, **kw) -> list[CycleReport]:
    out = []
    for i in range(start, start + n):
        env.clock.now = env.now_of(i)
        out.append(run_cycle(env.paths, env.clients, env.clock.now, deciders=deciders, **kw))
    return out


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def state_of(env: Env):
    return replay(env.events())


def payloads(env: Env, t: str, portfolio: str | None = None) -> list[dict]:
    return [e["payload"] for e in env.of_type(t) if portfolio is None or e["payload"].get("portfolio") == portfolio]


def alert_codes(env: Env) -> list[tuple[str, str]]:
    return [(a["level"], a["code"]) for a in payloads(env, "alert")]


# ---------------------------------------------------------------------------------------------- 30 cycles


def test_30_cycles_de_bout_en_bout(env: Env):
    reps = run_cycles(env, 30, deciders=make_deciders())
    assert [r.status for r in reps] == ["completed"] * 30
    assert verify(env.paths.journal).ok

    # Premier lancement : une config, 8 portefeuilles de 1 000 EUR en paper (Fable sans décideur factice : sauté).
    assert len(env.of_type("config_loaded")) == 1
    opened = payloads(env, "portfolio_opened")
    assert sorted(o["portfolio"] for o in opened) == sorted(ALL)
    assert {(o["capital_ueur"], o["venue_mode"]) for o in opened} == {(1_000_000_000, "paper")}
    assert len(env.of_type("cycle_started")) == len(env.of_type("cycle_completed")) == 30

    # Décideurs : Haiku décide, Sonnet renvoie du JSON invalide, Opus sans clé.
    assert len(payloads(env, "decision_received", HAIKU)) == 30
    assert all(d["parse_error"] is None for d in payloads(env, "decision_received", HAIKU))
    assert all(d["parse_error"] and d["parsed"] is None for d in payloads(env, "decision_received", SONNET))
    skipped = payloads(env, "decision_skipped", OPUS)
    assert len(skipped) == 30 and {s["reason"] for s in skipped} == {"no_key"}
    assert not payloads(env, "decision_requested", OPUS)
    assert len(payloads(env, "decision_requested", HAIKU)) == 30

    # Témoins de référence : verdict construit, raison REFERENCE ; le panier achète les 6 symboles au cycle 0.
    panier_buys = [f for f in payloads(env, "fill", "temoin:panier") if f["side"] == "buy"]
    assert {f["symbol"] for f in panier_buys} == set(SYMBOLS) and len(panier_buys) == 6
    verdicts = {v["intent_id"]: v for v in payloads(env, "risk_verdict")}
    panier_ids = [i["intent_id"] for i in payloads(env, "intent", "temoin:panier")]
    assert all(verdicts[i]["reasons"] == ["REFERENCE"] and verdicts[i]["approved"] for i in panier_ids)
    assert len([f for f in payloads(env, "fill", "temoin:e0065") if f["side"] == "buy"]) == 3

    # Rejeu du journal = état final : equity du dernier cycle == cash + positions au bid du dernier quote.
    st = state_of(env)
    bids = {e["payload"]["symbol"]: e["payload"]["bid"] for e in env.of_type("quote")[-6:]}
    last_eq = {p["portfolio"]: p for p in payloads(env, "equity") if p["cycle"] == T0 + 29 * H4}
    assert set(last_eq) == set(ALL)
    for p in ALL:
        s = st[p]
        assert equity_ueur(s, bids, bids) == last_eq[p]["equity_ueur"]
        assert s.cash_ueur + sum(x.cost_ueur for x in s.positions.values()) == 1_000_000_000 + s.realized_pnl_ueur
    assert reps[-1].equity_ueur == {p: last_eq[p]["equity_ueur"] for p in ALL}

    # Haiku a vraiment tradé, avec des coûts d'API journalisés.
    assert any(f["side"] == "buy" for f in payloads(env, "fill", HAIKU))
    assert sum(d["cost_uusd"] for d in payloads(env, "decision_received", HAIKU)) == 30 * 1500

    # Idempotence : relancer le dernier cycle ne change pas un octet.
    before = env.paths.journal.read_bytes()
    again = run_cycle(env.paths, env.clients, env.now_of(29), deciders=make_deciders())
    assert again.status == "already_done" and env.paths.journal.read_bytes() == before

    # Vue SQLite dérivée.
    counts = rebuild_sqlite(Journal(env.paths.journal).iter_events(), env.paths.sqlite)
    assert counts["equity"] == 30 * len(ALL)


def test_determinisme(tmp_path: Path):
    heads = []
    for name in ("a", "b"):
        e = Env(tmp_path / name)
        run_cycles(e, 12, deciders=make_deciders())
        heads.append(verify(e.paths.journal).head_hash)
    assert heads[0] == heads[1]


def test_changement_de_config_journalise(env: Env, tmp_path: Path):
    run_cycles(env, 1, deciders=make_deciders())
    pol = tmp_path / "policy2.toml"
    pol.write_text(env.paths.policy.read_text() + "\n# changement\n")
    env.paths = replace(env.paths, policy=pol)
    run_cycles(env, 1, start=1, deciders=make_deciders())
    cfgs = payloads(env, "config_loaded")
    assert len(cfgs) == 2 and cfgs[0]["policy_sha256"] != cfgs[1]["policy_sha256"]


# ---------------------------------------------------------------------------------------------- crash


@pytest.mark.parametrize(
    ("crash_cycle", "crash_after"),
    [(0, "temoin:panier"), (0, "temoin:e0065"), (1, HAIKU), (1, "temoin:aleatoire")],
)
def test_crash_au_milieu_puis_reprise_sans_double_fill(tmp_path: Path, crash_cycle: int, crash_after: str):
    n = 4
    clean = Env(tmp_path / "clean")
    run_cycles(clean, n, deciders=make_deciders())

    e = Env(tmp_path / "crash")
    run_cycles(e, crash_cycle, deciders=make_deciders())

    def boom(p: str) -> None:
        if p == crash_after:
            raise RuntimeError("crash simulé")

    rep = run_cycles(e, 1, start=crash_cycle, deciders=make_deciders(), on_portfolio_done=boom)[0]
    assert rep.status == "failed" and not rep.ok and "crash simulé" in rep.error
    assert verify(e.paths.journal).ok
    assert len(e.of_type("cycle_started")) == crash_cycle + 1 and len(e.of_type("cycle_completed")) == crash_cycle
    assert ("panique", "cycle_exception") in alert_codes(e)

    rep2 = run_cycles(e, n - crash_cycle, start=crash_cycle, deciders=make_deciders())
    assert rep2[0].status == "completed" and rep2[0].resumed and rep2[0].cycle_ts == T0 + crash_cycle * H4

    ids = [f["payload"]["order_id"] for f in e.of_type("fill")]
    assert len(ids) == len(set(ids)), "double fill après la reprise"
    assert sorted(ids) == sorted(f["payload"]["order_id"] for f in clean.of_type("fill"))
    assert state_of(e) == state_of(clean)
    assert verify(e.paths.journal).ok


def test_exception_alerte_panique_et_ping_fail(tmp_path: Path):
    env = Env(tmp_path, {"healthcheck_url": "https://hc.example/uuid"})
    env.kraken.fail_ticker = True
    rep = run_cycles(env, 1, deciders=make_deciders())[0]
    assert rep.status == "failed"
    assert ("panique", "cycle_exception") in alert_codes(env)
    assert [str(r.url) for r in env.requests] == ["https://hc.example/uuid/fail"]
    assert not env.of_type("cycle_started")  # l'échec survient avant le démarrage : rien à moitié fait


def test_donnee_perimee_arrete_proprement(env: Env):
    env.kraken.lag_s = H4  # la dernière barre close n'est pas encore publiée
    rep = run_cycles(env, 1, deciders=make_deciders())[0]
    assert rep.status == "failed" and ("action", "data_stale") in rep.alerts
    assert not env.of_type("cycle_started")


def test_journal_casse_refuse_de_tourner(tmp_path: Path):
    env = Env(tmp_path, {"ntfy_url": "https://ntfy.example/arene", "healthcheck_url": "https://hc.example/u"})
    run_cycles(env, 1, deciders=make_deciders())
    p = env.paths.journal
    lines = p.read_bytes().split(b"\n")
    lines[3] = lines[3].replace(b'"type"', b'"tYpe"', 1)  # altère une ligne : hash cassé
    p.write_bytes(b"\n".join(lines))
    size = p.stat().st_size
    env.requests.clear()
    rep = run_cycles(env, 1, start=1, deciders=make_deciders())[0]
    assert rep.status == "refused" and p.stat().st_size == size
    sent = [(r.method, str(r.url), r.headers.get("priority")) for r in env.requests]
    assert ("POST", "https://ntfy.example/arene", "5") in sent
    assert ("GET", "https://hc.example/u/fail", None) in sent


# ---------------------------------------------------------------------------------------------- coupe-circuit


def buy_then_hold(idx: int, snap: dict):
    return {0: [action("BTC/EUR")], 1: [action("ETH/EUR")], 10: [action("BTC/EUR")]}.get(idx)


def test_coupe_circuit_met_a_plat_et_bloque_les_achats(env: Env):
    d = make_deciders(buy_then_hold)
    run_cycles(env, 6, deciders=d)
    assert state_of(env)[HAIKU].positions
    env.paths.kill.parent.mkdir(parents=True, exist_ok=True)
    env.paths.kill.touch()
    n_fills = len(env.of_type("fill"))
    run_cycles(env, 4, start=6, deciders=d)
    st = state_of(env)
    assert not st[HAIKU].positions and not st["temoin:aleatoire"].positions
    assert st["temoin:panier"].positions  # les références ne sont pas mises à plat
    new = payloads(env, "fill")[n_fills:]
    assert new and all(f["side"] == "sell" for f in new)  # plus aucun achat, de personne
    assert any(f["reason"] == "kill_switch" and f["portfolio"] == HAIKU for f in new)
    assert [e["active"] for e in payloads(env, "kill_switch")] == [True]
    late = [s for s in payloads(env, "decision_skipped") if s["cycle"] >= T0 + 6 * H4]
    assert {s["reason"] for s in late if s["portfolio"] == HAIKU} == {"kill_switch"}
    assert {s["reason"] for s in late if s["portfolio"] == SONNET} == {"kill_switch"}
    # Levée : les achats reprennent (Haiku rachète au cycle 10).
    env.paths.kill.unlink()
    run_cycles(env, 2, start=10, deciders=d)
    assert [e["active"] for e in payloads(env, "kill_switch")] == [True, False]
    assert state_of(env)[HAIKU].positions


def test_coupe_circuit_du_dossier_utilisateur(env: Env):
    env.paths.user_kill.touch()
    run_cycles(env, 2, deciders=make_deciders(buy_then_hold))
    assert not payloads(env, "fill")  # même le panier n'achète pas
    assert payloads(env, "kill_switch")[0]["active"] is True


# ---------------------------------------------------------------------------------------------- gel, arrêt


def big_buy(idx: int, snap: dict):
    return [action("BTC/EUR", size=20, stop=25), action("ETH/EUR", size=20, stop=25)] if idx == 0 else None


def test_gel_puis_reprise_automatique(env: Env):
    env.kraken.crash("BTC/EUR", T0 + H4, 860)
    env.kraken.crash("ETH/EUR", T0 + H4, 860)
    run_cycles(env, 10, deciders=make_deciders(big_buy))
    fr = payloads(env, "portfolio_frozen", HAIKU)
    assert len(fr) == 1 and fr[0]["until_ts"] == T0 + 2 * H4 + DAY and fr[0]["reason"] == "daily_loss"
    assert not payloads(env, "portfolio_halted", HAIKU)
    skipped = {s["cycle"]: s["reason"] for s in payloads(env, "decision_skipped", HAIKU)}
    assert {skipped.get(T0 + i * H4) for i in range(3, 8)} == {"frozen"}
    got = {d["cycle"] for d in payloads(env, "decision_received", HAIKU)}
    assert {T0 + 8 * H4, T0 + 9 * H4} <= got and T0 + 3 * H4 not in got


def test_arret_drawdown_mise_a_plat_et_reprise_manuelle(env: Env):
    env.kraken.crash("BTC/EUR", T0 + H4, 500)
    env.kraken.crash("ETH/EUR", T0 + H4, 500)
    run_cycles(env, 10, deciders=make_deciders(big_buy))
    assert len(payloads(env, "portfolio_halted", HAIKU)) == 1
    st = state_of(env)[HAIKU]
    assert st.halted and not st.positions
    assert len([f for f in payloads(env, "fill", HAIKU) if f["reason"] == "stop"]) == 2
    assert {d["reason"] for d in payloads(env, "decision_skipped", HAIKU) if d["cycle"] >= T0 + 3 * H4} == {"halted"}
    assert ("action", "portfolio_halted") in alert_codes(env)

    # `arene resume` : portfolio_resumed ; le plus haut repart de l'equity à plat (pas de ré-arrêt immédiat).
    Journal(env.paths.journal).append(
        "portfolio_resumed", {"portfolio": HAIKU, "reason": "manual", "until_ts": 0}, env.now_of(10)
    )
    run_cycles(env, 3, start=10, deciders=make_deciders(big_buy))
    assert len(payloads(env, "portfolio_halted", HAIKU)) == 1
    assert not state_of(env)[HAIKU].halted
    assert {d["cycle"] for d in payloads(env, "decision_received", HAIKU)} >= {T0 + 10 * H4, T0 + 12 * H4}


def test_stop_declenche_par_un_gap(env: Env):
    def plan(i, s):
        return [action("SOL/EUR", size=10, stop=5)] if i == 0 else None

    env.kraken.crash("SOL/EUR", T0 + H4, 800)
    run_cycles(env, 3, deciders=make_deciders(plan))
    stops = payloads(env, "stop_set", HAIKU)
    assert len(stops) == 1
    fills = [f for f in payloads(env, "fill", HAIKU) if f["reason"] == "stop"]
    assert len(fills) == 1 and fills[0]["order_id"] == f"stop:{HAIKU}:SOL/EUR:{T0 + H4}"
    bar = env.kraken.bar("SOL/EUR", T0 + H4)
    inst = Instrument("SOL/EUR", "SOLEUR", "SOLUSDT", 10_000, 5_000_000, 450_000)
    expected = stop_fill(stops[0]["stop_ueur"], bar, inst, 5)
    assert fills[0]["price_ueur"] == expected
    assert expected < stops[0]["stop_ueur"]  # sortie au prix d'ouverture après le gap, pas au niveau du stop
    assert "SOL/EUR" not in state_of(env)[HAIKU].positions


# ---------------------------------------------------------------------------------------------- dormance


def test_dormance_sept_jours_puis_neuf_jours(env: Env):
    d = make_deciders(buy_then_hold)
    run_cycles(env, 3, deciders=d)
    assert state_of(env)[HAIKU].positions

    def set_ack(age_days: int, i: int) -> None:
        env.paths.ack.parent.mkdir(parents=True, exist_ok=True)
        env.paths.ack.touch()
        ts = env.now_of(i) - age_days * DAY
        os.utime(env.paths.ack, (ts, ts))

    set_ack(8, 3)  # 7 j dépassés : aucune entrée, pas de mise à plat
    n = len(env.of_type("fill"))
    run_cycles(env, 1, start=3, deciders=d)
    assert [s["reason"] for s in payloads(env, "decision_skipped", HAIKU)] == ["kill_switch"]
    assert state_of(env)[HAIKU].positions
    assert not [f for f in payloads(env, "fill")[n:] if f["side"] == "buy"]
    assert ("action", "dormance_no_entries") in alert_codes(env)

    set_ack(10, 4)  # 9 j : mise à plat
    run_cycles(env, 1, start=4, deciders=d)
    assert not state_of(env)[HAIKU].positions
    assert any(f["reason"] == "dormance" for f in payloads(env, "fill", HAIKU))

    set_ack(0, 5)  # ack frais : retour à la normale
    run_cycles(env, 6, start=5, deciders=d)
    assert state_of(env)[HAIKU].positions
    assert ("info", "dormance_ok") in alert_codes(env)


def test_sans_ack_la_dormance_part_du_premier_evenement(env: Env):
    run_cycles(env, 1, deciders=make_deciders())
    run_cycles(env, 1, start=6 * 8, deciders=make_deciders())  # 8 jours plus tard, jamais d'ack
    assert ("action", "dormance_no_entries") in alert_codes(env)


# ---------------------------------------------------------------------------------------------- ordres UNKNOWN


def _inject_on_haiku(env: Env):
    return lambda oid: any(
        e["type"] == "intent" and e["payload"]["intent_id"] == oid and e["payload"]["portfolio"] == HAIKU
        for e in Journal(env.paths.journal).iter_events()
    )


def test_ordre_unknown_resolu_au_cycle_suivant(env: Env):
    run_cycles(env, 3, deciders=make_deciders(buy_then_hold), fault_injector=_inject_on_haiku(env))
    states = [(p["order_id"], p["state"]) for p in payloads(env, "order_state")]
    haiku_ids = {p["intent_id"] for p in payloads(env, "intent", HAIKU)}
    unknown = [o for o, s in states if s == "UNKNOWN" and o in haiku_ids]
    assert unknown and all((o, "CANCELED") in states for o in unknown)
    assert not payloads(env, "portfolio_frozen")


def test_ordre_unknown_plus_de_deux_cycles_gele(env: Env, monkeypatch):
    monkeypatch.setattr(SimExecutor, "resolve_unknown", lambda self, oid, ts: False)
    plan = make_deciders(lambda i, s: [action("BTC/EUR")] if i == 0 else None)
    run_cycles(env, 5, deciders=plan, fault_injector=_inject_on_haiku(env))
    fr = payloads(env, "portfolio_frozen", HAIKU)
    assert fr and fr[0]["reason"] == "unknown_order"
    assert {d["reason"] for d in payloads(env, "decision_skipped", HAIKU)} == {"frozen"}


# ---------------------------------------------------------------------------------------------- vrai LLMDecider, client factice


def test_llm_decider_reel_avec_client_factice_et_modele_different(tmp_path: Path):
    env = Env(tmp_path, {"ntfy_url": "https://ntfy.example/t"})
    text = json.dumps({"actions": [action("BTC/EUR")], "justification": "test"})
    d = LLMDecider(
        "claude-opus-5-5", OPUS, (4, 20), "0.9",
        client_factory=fake_anthropic_client(text, "claude-opus-4-1"), key_reader=lambda: "cle-factice",
        sleep=lambda s: None,
    )  # fmt: skip
    deciders = {HAIKU: NoKeyDecider("claude-haiku-5-5", HAIKU), SONNET: NoKeyDecider("claude-sonnet-5-5", SONNET), OPUS: d}
    run_cycles(env, 2, deciders=deciders)
    rec = payloads(env, "decision_received", OPUS)
    assert len(rec) == 2 and rec[0]["model_requested"] == "claude-opus-5-5" and rec[0]["model_returned"] == "claude-opus-4-1"
    assert rec[0]["input_tokens"] == 2000 and rec[0]["cost_uusd"] == 2000 * 4 + 300 * 20
    assert ("action", "model_mismatch") in alert_codes(env)
    assert any(str(r.url) == "https://ntfy.example/t" and r.headers["priority"] == "3" for r in env.requests)
    assert any(f["side"] == "buy" for f in payloads(env, "fill", OPUS))


def test_depense_du_jour_calculee_depuis_le_journal(env: Env):
    seen = []

    class Spy(ScriptedDecider):
        def decide(self, snapshot, spent_today_uusd):
            seen.append(spent_today_uusd)
            return super().decide(snapshot, spent_today_uusd)

    d = make_deciders()
    d[HAIKU] = Spy("claude-haiku-5-5", HAIKU, lambda i, s: None)
    run_cycles(env, 3, deciders=d)
    assert seen == [0, 1500, 3000]
