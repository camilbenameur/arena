"""Retrait d'un modèle de la ligue comptant (`arene retire`, demande du 17/11/2026) : vente au bid, journal, plus joué."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

import pytest

from arene import cli
from arene.cycle import run_cycle
from arene.journal import Journal, verify
from arene.ledger import replay, retired_portfolios
from arene.retire import RetireError, retire_portfolio
from arene.types import Quote
from arene.veille import run_veille
from tests.fakes import HAIKU, OPUS, SONNET, Env, ScriptedDecider, action, make_deciders

FABLE = "llm:claude-fable-5-2"


def hold(idx: int, snap: dict):
    return [action("BTC/EUR"), action("ETH/EUR")] if idx == 0 else None


class Counting(ScriptedDecider):
    calls = 0

    def decide(self, snapshot: dict, spent_today_uusd: int):
        type(self).calls += 1
        return super().decide(snapshot, spent_today_uusd)


def events(env: Env) -> list[dict]:
    return Journal(env.paths.journal).events()


def of(env: Env, t: str, portfolio: str | None = None) -> list[dict]:
    return [e for e in events(env) if e["type"] == t and (portfolio is None or e["payload"].get("portfolio") == portfolio)]


@pytest.fixture
def env(tmp_path: Path) -> Env:
    e = Env(tmp_path)
    e.clock.now = e.now_of(0)
    run_cycle(e.paths, e.clients, e.clock.now, deciders=make_deciders(hold))
    assert replay(events(e))[HAIKU].positions
    e.clock.now = e.now_of(0) + 1800  # une demi-heure plus tard, hors cycle
    return e


def test_retire_vend_tout_au_bid_journalise_et_rejoue(env: Env):
    avant = replay(events(env))[HAIKU]
    out = retire_portfolio(env.paths, env.clients, HAIKU, env.clock.now, reason="archive", note="texte libre")
    assert out["status"] == "retired" and out["fills"] == len(avant.positions) == 2
    ventes = [e["payload"] for e in of(env, "fill", HAIKU) if e["payload"]["reason"] == "retired"]
    assert {v["symbol"] for v in ventes} == set(avant.positions) and all(v["side"] == "sell" for v in ventes)
    [ev] = of(env, "portfolio_retired")
    p = ev["payload"]
    assert p["portfolio"] == HAIKU and p["ts"] == env.clock.now and p["reason"] == "archive" and p["note"] == "texte libre"
    assert p["fills"] == 2 and set(p["quotes"]) == set(avant.positions)
    after = replay(events(env))[HAIKU]
    assert not after.positions and after.cash_ueur == p["equity_ueur"] == out["equity_ueur"]
    assert events(env)[-1]["type"] == "portfolio_retired" and verify(env.paths.journal).ok
    assert retired_portfolios(events(env)) == {HAIKU}
    # aucun événement `quote` écrit hors cycle (le site les rattacherait au cycle précédent)
    assert not [e for e in events(env) if e["type"] == "quote" and e["ts"] == env.clock.now]
    # les autres portefeuilles ne sont pas touchés
    assert replay(events(env))["temoin:panier"].positions


def test_retire_est_idempotent(env: Env):
    retire_portfolio(env.paths, env.clients, HAIKU, env.clock.now)
    n = len(events(env))
    out = retire_portfolio(env.paths, env.clients, HAIKU, env.clock.now + 600)
    assert out["status"] == "already_retired" and out["fills"] == 0 and len(events(env)) == n


def test_retire_ferme_sans_quote_valide_n_ecrit_rien(env: Env, monkeypatch: pytest.MonkeyPatch):
    n = len(events(env))
    env.kraken.fail_ticker = True
    with pytest.raises(RetireError, match="illisible"):
        retire_portfolio(env.paths, env.clients, HAIKU, env.clock.now)
    assert len(events(env)) == n and replay(events(env))[HAIKU].positions and not retired_portfolios(events(env))
    env.kraken.fail_ticker = False
    monkeypatch.setattr(env.kraken, "ticker", lambda sym, pair: Quote(sym, env.clock.now, 0, 5))  # un bid nul : invalide
    with pytest.raises(RetireError, match="invalide"):
        retire_portfolio(env.paths, env.clients, HAIKU, env.clock.now)
    assert len(events(env)) == n


def test_retire_refuse_un_temoin_un_inconnu_et_attend_le_verrou(env: Env):
    with pytest.raises(RetireError, match="témoin"):
        retire_portfolio(env.paths, env.clients, "temoin:panier", env.clock.now)
    with pytest.raises(RetireError, match="seul un modèle"):
        retire_portfolio(env.paths, env.clients, "llm:inconnu", env.clock.now)
    env.paths.var.mkdir(parents=True, exist_ok=True)
    fd = os.open(env.paths.lock, os.O_CREAT | os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)  # un cycle ou un réveil tourne
    try:
        n = len(events(env))
        with pytest.raises(RetireError, match="verrou"):
            retire_portfolio(env.paths, env.clients, HAIKU, env.clock.now, lock_wait_s=0.3)
        assert len(events(env)) == n
    finally:
        os.close(fd)


def test_le_cycle_ne_joue_ni_ne_valorise_plus_un_portefeuille_retire(env: Env):
    retire_portfolio(env.paths, env.clients, HAIKU, env.clock.now)
    Counting.calls = 0
    d = make_deciders(hold)
    d[HAIKU] = Counting("claude-haiku-5-5", HAIKU, lambda i, s: [action("SOL/EUR")])
    for i in (1, 2):
        env.clock.now = env.now_of(i)
        rep = run_cycle(env.paths, env.clients, env.clock.now, deciders=d)
        assert rep.status == "completed" and HAIKU not in rep.equity_ueur and SONNET in rep.equity_ueur
    assert Counting.calls == 0  # jamais rappelé
    ev = events(env)
    retire_seq = next(e["seq"] for e in ev if e["type"] == "portfolio_retired")
    apres = [e for e in ev if e["seq"] > retire_seq and e["payload"].get("portfolio") == HAIKU]
    assert not apres  # ni décision, ni ordre, ni equity, ni saut
    assert [e for e in ev if e["seq"] > retire_seq and e["type"] == "equity" and e["payload"]["portfolio"] == SONNET]
    assert not replay(ev)[HAIKU].positions and verify(env.paths.journal).ok


def test_la_veille_ne_valorise_plus_un_portefeuille_retire(env: Env):
    retire_portfolio(env.paths, env.clients, HAIKU, env.clock.now)
    env.clock.now = env.now_of(0) + 2400
    rep = run_veille(env.paths, env.clients, env.clock.now)
    assert rep.status == "done"
    v = of(env, "veille")[-1]["payload"]
    assert HAIKU not in v["equity"] and SONNET in v["equity"] and OPUS in v["equity"] and FABLE in v["equity"]


def run_cli(env: Env, *args: str) -> int:
    ts = env.clock.now
    return cli.main(
        ["--var", str(env.paths.var), "--secrets", str(env.sec), "--config", str(env.paths.config), *args],
        clients=env.clients, now=lambda: ts,
    )


def test_cli_retire_status_et_resume_refuse(env: Env, capsys: pytest.CaptureFixture):
    assert run_cli(env, "retire", "temoin:panier") == 1
    assert run_cli(env, "retire", HAIKU, "--reason", "archive", "--note", "17/11") == 0
    out = capsys.readouterr().out
    assert "retiré : 2 position(s) vendue(s)" in out
    assert run_cli(env, "retire", HAIKU) == 0 and "déjà retiré" in capsys.readouterr().out
    [ev] = of(env, "portfolio_retired")
    assert ev["payload"]["reason"] == "archive" and ev["payload"]["note"] == "17/11"
    assert run_cli(env, "resume", HAIKU) == 2  # un retiré ne rejoue jamais
    assert not of(env, "portfolio_resumed")
    capsys.readouterr()
    assert run_cli(env, "status") == 0
    assert "RETIRÉ" in capsys.readouterr().out


def test_retirer_ne_change_ni_la_config_ni_la_politique_ni_la_consigne(env: Env):
    from arene import saison
    from arene.config import load_config
    from arene.deciders.llm import prompt_sha256
    from arene.risk.policy import load_policy

    avant = (load_config(env.paths.config).sha256_hors_saison, load_policy(env.paths.policy).sha256, prompt_sha256())
    retire_portfolio(env.paths, env.clients, HAIKU, env.clock.now)
    apres = (load_config(env.paths.config).sha256_hors_saison, load_policy(env.paths.policy).sha256, prompt_sha256())
    assert avant == apres  # seul le code (cycle, veille, ledger) change : voir `saison.CODE_GELE_FICHIERS`
    assert "arene/retire.py" not in saison.CODE_GELE_FICHIERS and "arene/cycle.py" in saison.CODE_GELE_FICHIERS
