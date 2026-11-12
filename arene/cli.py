"""Ligne de commande `arene` (docs/SPEC-MVP.md §11-12).

Options globales (avant la commande) : --var, --secrets, --config, --policy ; sinon variables ARENE_VAR,
ARENE_SECRETS. `main(argv, clients=..., now=...)` est injectable pour les tests.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from arene import cycle as cyc
from arene import veille as vei
from arene.config import ConfigError, load_config
from arene.journal import Journal, JournalError, verify
from arene.ledger import rebuild_sqlite, replay
from arene.ops import anthropic_key, dormance, killswitch
from arene.ops.notify import Notifier
from arene.paths import Paths
from arene.risk.policy import PolicyError, load_policy


def _iso(ts: int | None) -> str:
    return "-" if ts is None else datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d %H:%M UTC")


def _eur(ueur: int) -> str:
    return f"{ueur / 1_000_000:,.2f} EUR".replace(",", " ")


def _last_kill_state(events: list[dict]) -> bool:
    state = False
    for e in events:
        if e["type"] == "kill_switch":
            state = bool(e["payload"]["active"])
    return state


def _journal_kill(paths: Paths, active: bool, source: str, ts: int) -> None:
    """Journalise un changement d'état du coupe-circuit (sans doublon, sans écrire dans un journal cassé)."""
    j = Journal(paths.journal)
    try:
        if verify(paths.journal).ok and _last_kill_state(j.events()) != active:
            j.append("kill_switch", {"active": active, "source": source}, ts)
    except JournalError as exc:
        print(f"journal non écrit : {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------------------- commandes


def cmd_cycle(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    rep = cyc.run_cycle(paths, clients, now)
    print(f"cycle {_iso(rep.cycle_ts)} : {rep.status}  événements={rep.n_events}  fills={rep.n_fills}")
    for p, eq in sorted(rep.equity_ueur.items()):
        print(f"  {p:28s} {_eur(eq)}")
    if rep.error:
        print(f"erreur : {rep.error}", file=sys.stderr)
    if rep.status == "completed" and not a.no_site:
        _build_site(paths, clients, now, quiet_missing=True)
    return 0 if rep.ok else 1


SITE_BUILD_UNIT = "arene-site-build.service"


def _start_site_build() -> None:
    """Demande à systemd de reconstruire le site (hors de ce processus, sans attendre). Un échec est ignoré."""
    try:
        subprocess.run(
            ["systemctl", "--user", "start", "--no-block", SITE_BUILD_UNIT],
            check=True, capture_output=True, timeout=15,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError) as exc:
        logging.getLogger("arene.cli").warning("reconstruction du site non lancée : %s: %s", type(exc).__name__, exc)


def cmd_veille(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    rep = vei.run_veille(paths, clients, now)
    extra = f"  stops={len(rep.stops)}" if rep.stops else ""
    if rep.rejets:
        extra += f"  quotes écartés={','.join(f'{s}:{m}' for s, m in sorted(rep.rejets.items()))}"
    if rep.declencheur:
        extra += f"  declencheur={rep.declencheur['type']}" + (f" (refusé : {rep.refus})" if rep.refus else "")
    if rep.reveil:
        extra += f"  reveil={rep.reveil}"
    print(f"veille {_iso(rep.tick)} : {rep.status}  événements={rep.n_events}{extra}")
    if rep.error:
        print(f"erreur : {rep.error}", file=sys.stderr)
    # Décision du propriétaire (12/11/2026, 18 h 50 UTC) : le site privé est reconstruit après chaque tick écrit (valeur
    # « en direct » à jour toutes les 5 min), et pas seulement après un réveil. Lancé sans attendre, hors du processus.
    if rep.status == "done" and rep.n_events > 0 and not a.no_site:
        _start_site_build()
    return 0 if rep.ok else 1


def _build_site(paths: Paths, clients: cyc.Clients, now: int, *, quiet_missing: bool = False) -> int:
    try:
        from arene.site import build  # import paresseux : le module est écrit à part
    except ImportError:
        if not quiet_missing:
            print("arene.site n'existe pas (encore) : build-site indisponible.", file=sys.stderr)
        return 2
    try:
        build(paths.journal, paths.site, config=load_config(paths.config), policy=load_policy(paths.policy))
    except Exception as exc:
        logging.getLogger("arene.cli").exception("construction du site en échec")
        Notifier(Journal(paths.journal), paths.secrets, clients.http).alert(
            "action", "site_build", f"construction du site en échec : {type(exc).__name__}: {str(exc)[:200]}", now
        )
        return 1
    print(f"site construit dans {paths.site}")
    return 0


def cmd_kill(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    path = killswitch.activate(paths)
    print(f"coupe-circuit armé ({path}) : plus aucun achat, mise à plat des portefeuilles LLM et aléatoire.")
    if not a.now:
        _journal_kill(paths, True, "cli", now)
        print("Effet au plus tard au prochain cycle ; `arene kill --now` pour une mise à plat immédiate.")
        return 0
    t0 = time.monotonic()
    rep = cyc.flatten_now(paths, clients, now)
    print(f"mise à plat immédiate : {rep.status}, {rep.n_fills} fills en {time.monotonic() - t0:.1f} s")
    if rep.error:
        print(f"erreur : {rep.error}", file=sys.stderr)
    return 0 if rep.status == "completed" else 1


def cmd_unkill(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    removed = killswitch.deactivate(paths)
    _journal_kill(paths, False, "cli", now)
    print("coupe-circuit levé : " + (", ".join(map(str, removed)) if removed else "il n'était pas armé."))
    print("Les achats reprennent au prochain cycle (les positions mises à plat ne sont pas rachetées).")
    return 0


def cmd_ack(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    dormance.write_ack(paths, now)
    print(f"présence confirmée ({_iso(now)}) : la dormance repart de zéro.")
    return 0


def cmd_resume(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    if not verify(paths.journal).ok:
        print("journal cassé : reprise refusée (voir docs/RUNBOOK.md).", file=sys.stderr)
        return 1
    j = Journal(paths.journal)
    states = replay(j.events())
    if a.portfolio not in states:
        print(f"portefeuille inconnu : {a.portfolio} (connus : {', '.join(sorted(states))})", file=sys.stderr)
        return 2
    j.append("portfolio_resumed", {"portfolio": a.portfolio, "reason": "manual", "until_ts": 0}, now)
    print(f"{a.portfolio} repris : gel et arrêt levés, ses décisions reprennent au prochain cycle.")
    return 0


def _status_saison(paths: Paths, ev: list[dict], now: int) -> None:
    """Saison : en attente, en cours (jour N sur D) ou terminée, et la performance depuis `saison_reference`."""
    try:
        cfg = load_config(paths.config)
    except ConfigError:
        cfg = None
    debuts = [e["payload"] for e in ev if e["type"] == "saison_debut"]
    if not debuts:
        if cfg is not None and cfg.saison is not None:
            s = cfg.saison
            print(f"saison : {s.nom} en attente (début au cycle du {_iso(s.debut_ts)}, {s.duree_jours} jours)")
        return
    d = debuts[-1]
    fins = [e["payload"] for e in ev if e["type"] == "saison_fin" and e["payload"]["numero"] == d["numero"]]
    refs = [e["payload"] for e in ev if e["type"] == "saison_reference" and e["payload"]["numero"] == d["numero"]]
    duree = (d["fin_prevue_cycle"] - d["cycle"]) // 86_400
    derog = sum(1 for e in ev if e["type"] == "saison_derogation" and e["payload"]["numero"] == d["numero"])
    if fins:
        etat = f"terminée (cycle {_iso(fins[0]['cycle'])})"
    else:
        etat = f"en cours (jour {min(duree, max(0, now - d['cycle']) // 86_400 + 1)} sur {duree})"
    print(f"saison : {d['nom']} {etat}, début {_iso(d['cycle'])}, dérogations : {derog}")
    if not refs:
        print("  (pas encore de saison_reference)")
        return
    base = refs[0]["equity"]
    last = fins[0]["equity"] if fins else {}
    if not fins:
        for e in ev:
            if e["type"] == "equity":
                last[e["payload"]["portfolio"]] = e["payload"]["equity_ueur"]
    print("  performance depuis la référence (equity au bid) :")
    for p, b in sorted(base.items()):
        cur = last.get(p, b)
        print(f"  {p:28s} {_eur(cur):>16s} {(cur - b) * 100 / b if b else 0:+7.2f} %")


def cmd_status(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    rep = verify(paths.journal)
    print(f"journal : {'OK' if rep.ok else 'CASSÉ'}  {rep.n_records} événements  tête {rep.head_hash[:12]}")
    for e in rep.errors[:5]:
        print(f"  ! {e.code} ligne {e.line} : {e.message}")
    if rep.n_records == 0 or not rep.ok:
        return 0 if rep.ok else 1
    ev = Journal(paths.journal).events()
    done = [e["payload"]["cycle"] for e in ev if e["type"] == "cycle_completed"]
    started = [e["payload"]["cycle"] for e in ev if e["type"] == "cycle_started"]
    last = f"{_iso(done[-1])} ({(now - done[-1]) // 3600} h)" if done else "aucun"
    pending = f"  ! cycle {_iso(started[-1])} commencé mais non terminé" if started and (not done or started[-1] > done[-1]) else ""
    print(f"dernier cycle terminé : {last}  ({len(done)} au total)")
    if pending:
        print(pending)
    states = replay(ev)
    eq = {e["payload"]["portfolio"]: e["payload"]["equity_ueur"] for e in ev if e["type"] == "equity"}
    capital = {e["payload"]["portfolio"]: e["payload"]["capital_ueur"] for e in ev if e["type"] == "portfolio_opened"}
    print("equity (au bid) :")
    for p, st in sorted(states.items()):
        cur = eq.get(p, capital.get(p, 0))
        flag = " ARRÊTÉ" if st.halted else " GELÉ" if st.frozen_until_ts > now else ""
        pct = (cur - capital[p]) * 100 / capital[p] if capital.get(p) else 0
        print(f"  {p:28s} {_eur(cur):>16s} {pct:+6.2f} %  positions={len(st.positions)}{flag}")
    _status_saison(paths, ev, now)
    srcs = killswitch.active_sources(paths)
    print(f"coupe-circuit : {'ARMÉ (' + ', '.join(srcs) + ')' if srcs else 'inactif'}")
    first = ev[0]["ts"]
    age = dormance.age_s(paths, now, first)
    print(f"dormance : dernier ack il y a {age // 3600} h  ({dormance.level(age)}) ; limites 7 j / 9 j")
    alerts = [e for e in ev if e["type"] == "alert"]
    if alerts:
        al = alerts[-1]
        print(f"dernière alerte : [{al['payload']['level']}] {al['payload']['code']} {_iso(al['ts'])} : {al['payload']['message']}")
    else:
        print("dernière alerte : aucune")
    return 0


def cmd_verify(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    rep = verify(paths.journal)
    print(f"journal {paths.journal} : {'OK' if rep.ok else 'CASSÉ'}  {rep.n_records} événements  tête {rep.head_hash}")
    for e in rep.errors[:20]:
        print(f"  {e.code} ligne {e.line} (seq {e.seq}) : {e.message}")
    return 0 if rep.ok else 1


def cmd_rebuild_ledger(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    if not verify(paths.journal).ok:
        print("journal cassé : reconstruction refusée.", file=sys.stderr)
        return 1
    counts = rebuild_sqlite(Journal(paths.journal).iter_events(), paths.sqlite)
    print(f"{paths.sqlite} reconstruit : {counts}")
    return 0


def cmd_build_site(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    return _build_site(paths, clients, now)


def cmd_smoke_llm(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    cfg = load_config(paths.config)
    if cfg.decider_backend == "api" and not anthropic_key(paths):
        print("refus : aucune clé API (anthropic_api_key) ; rien n'a été appelé.", file=sys.stderr)
        return 2
    deciders = cyc.default_deciders(cfg, paths)
    decider = deciders.get(a.portfolio)
    if decider is None:
        print(f"portefeuille LLM inconnu : {a.portfolio} (connus : {', '.join(deciders)})", file=sys.stderr)
        return 2
    snapshot = cyc.smoke_snapshot(paths, clients, a.portfolio, now)
    res = decider.decide(snapshot, 0)
    print(f"appel unique, aucun ordre exécuté, rien journalisé. modèle demandé {decider.model}")
    if res.skipped_reason:
        print(f"non appelé / échec : {res.skipped_reason} {res.error or ''}", file=sys.stderr)
        return 1
    n = len((res.parsed or {}).get("actions", []))
    print(f"modèle renvoyé {res.model_returned}  tokens {res.input_tokens}/{res.output_tokens}  coût {res.cost_uusd} µ$  {res.latency_ms} ms")
    print(f"format : {'valide, ' + str(n) + ' action(s)' if res.parse_error is None else 'INVALIDE : ' + res.parse_error}")
    if res.parsed:
        print(f"justification : {res.parsed['justification'][:300]}")
    return 0 if res.parse_error is None else 1


# ---------------------------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="arene", description="Arène de trading (paper).")
    ap.add_argument("--var", help="répertoire d'état (défaut : $ARENE_VAR ou var/ du dépôt)")
    ap.add_argument("--secrets", help="dossier des secrets (défaut : $ARENE_SECRETS ou ~/.config/arene/secrets)")
    ap.add_argument("--config", help="config/arene.toml alternatif")
    ap.add_argument("--policy", help="config/policy.toml alternatif")
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("cycle", help="exécute (ou reprend) le cycle courant")
    c.add_argument("--no-site", action="store_true", help="ne reconstruit pas le site après le cycle")
    w = sub.add_parser("veille", help="un tick de veille (stops en direct, réveil éventuel), sans LLM sauf réveil")
    w.add_argument("--no-site", action="store_true", help="ne demande pas la reconstruction du site après un réveil")
    k = sub.add_parser("kill", help="arme le coupe-circuit")
    k.add_argument("--now", action="store_true", help="met à plat tout de suite (LLM et aléatoire)")
    sub.add_parser("unkill", help="lève le coupe-circuit")
    sub.add_parser("ack", help="confirme la présence de l'opérateur (réarme la dormance)")
    r = sub.add_parser("resume", help="reprend un portefeuille gelé ou arrêté")
    r.add_argument("portfolio")
    sub.add_parser("status", help="résumé lisible de l'état")
    sub.add_parser("verify", help="vérifie la chaîne du journal")
    sub.add_parser("rebuild-ledger", help="reconstruit var/ledger.sqlite depuis le journal")
    sub.add_parser("build-site", help="construit le dashboard dans var/site")
    s = sub.add_parser("smoke-llm", help="un appel réel au modèle, sans exécuter d'ordre")
    s.add_argument("portfolio")
    return ap


COMMANDS: dict[str, Callable[..., int]] = {
    "cycle": cmd_cycle,
    "veille": cmd_veille,
    "kill": cmd_kill,
    "unkill": cmd_unkill,
    "ack": cmd_ack,
    "resume": cmd_resume,
    "status": cmd_status,
    "verify": cmd_verify,
    "rebuild-ledger": cmd_rebuild_ledger,
    "build-site": cmd_build_site,
    "smoke-llm": cmd_smoke_llm,
}


def main(
    argv: Sequence[str] | None = None,
    *,
    clients: cyc.Clients | None = None,
    now: Callable[[], int] | None = None,
) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # une ligne par requête : trop bavard
    args = build_parser().parse_args(argv)
    paths = Paths.from_env(args.var, args.secrets, args.config, args.policy)
    ts = now() if now else int(time.time())
    try:
        return COMMANDS[args.command](args, paths, clients or cyc.Clients.real(), ts)
    except (ConfigError, PolicyError) as exc:
        print(f"configuration invalide : {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
