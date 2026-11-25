"""`arena` command line (docs/SPEC-MVP.md §11-12).

Global options (before the command): --var, --secrets, --config, --policy; otherwise the ARENA_VAR and
ARENA_SECRETS environment variables. `main(argv, clients=..., now=...)` is injectable for tests.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from arena import cycle as cyc
from arena import watch
from arena.config import ConfigError, load_config
from arena.journal import Journal, JournalError, verify
from arena.ledger import rebuild_sqlite, replay, retired_portfolios
from arena.ops import anthropic_key, dormancy, killswitch
from arena.ops.notify import Notifier
from arena.paths import Paths
from arena.risk.policy import PolicyError, load_policy


def _iso(ts: int | None) -> str:
    return "-" if ts is None else datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d %H:%M UTC")


def _eur(ueur: int) -> str:
    return f"{ueur / 1_000_000:,.2f} EUR"


def _last_kill_state(events: list[dict]) -> bool:
    state = False
    for e in events:
        if e["type"] == "kill_switch":
            state = bool(e["payload"]["active"])
    return state


def _journal_kill(paths: Paths, active: bool, source: str, ts: int) -> None:
    """Journals a kill switch state change (no duplicates, nothing written to a broken journal)."""
    j = Journal(paths.journal)
    try:
        if verify(paths.journal).ok and _last_kill_state(j.events()) != active:
            j.append("kill_switch", {"active": active, "source": source}, ts)
    except JournalError as exc:
        print(f"journal not written: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------------------- commands


def cmd_cycle(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    rep = cyc.run_cycle(paths, clients, now)
    print(f"cycle {_iso(rep.cycle_ts)}: {rep.status}  events={rep.n_events}  fills={rep.n_fills}")
    for p, eq in sorted(rep.equity_ueur.items()):
        print(f"  {p:28s} {_eur(eq)}")
    if rep.error:
        print(f"error: {rep.error}", file=sys.stderr)
    if rep.status == "completed" and not a.no_site:
        _build_site(paths, clients, now, quiet_missing=True)
    return 0 if rep.ok else 1


SITE_BUILD_UNIT = "arena-site-build.service"


def _start_site_build() -> None:
    """Asks systemd to rebuild the site (outside this process, without waiting). A failure is ignored."""
    try:
        subprocess.run(
            ["systemctl", "--user", "start", "--no-block", SITE_BUILD_UNIT],
            check=True, capture_output=True, timeout=15,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError) as exc:
        logging.getLogger("arena.cli").warning("site rebuild not started: %s: %s", type(exc).__name__, exc)


def cmd_watch(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    rep = watch.run_watch(paths, clients, now)
    extra = f"  stops={len(rep.stops)}" if rep.stops else ""
    if rep.rejected:
        extra += f"  quotes_rejected={','.join(f'{s}:{m}' for s, m in sorted(rep.rejected.items()))}"
    if rep.trigger:
        extra += f"  trigger={rep.trigger['type']}" + (f" (refused: {rep.refused})" if rep.refused else "")
    if rep.wakeup:
        extra += f"  wakeup={rep.wakeup}"
    print(f"watch {_iso(rep.tick)}: {rep.status}  events={rep.n_events}{extra}")
    if rep.error:
        print(f"error: {rep.error}", file=sys.stderr)
    # The private site is rebuilt after every written tick (so the "live" value is refreshed every 5 min), not only
    # after a wake-up. Started without waiting, outside this process.
    if rep.status == "done" and rep.n_events > 0 and not a.no_site:
        _start_site_build()
    return 0 if rep.ok else 1


def _build_site(paths: Paths, clients: cyc.Clients, now: int, *, quiet_missing: bool = False) -> int:
    try:
        from arena.site import build  # lazy import: the module is written separately
    except ImportError:
        if not quiet_missing:
            print("arena.site does not exist (yet): build-site is unavailable.", file=sys.stderr)
        return 2
    try:
        build(paths.journal, paths.site, config=load_config(paths.config), policy=load_policy(paths.policy))
    except Exception as exc:
        logging.getLogger("arena.cli").exception("site build failed")
        Notifier(Journal(paths.journal), paths.secrets, clients.http).alert(
            "action", "site_build", f"site build failed: {type(exc).__name__}: {str(exc)[:200]}", now
        )
        return 1
    print(f"site built in {paths.site}")
    return 0


def cmd_kill(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    path = killswitch.activate(paths)
    print(f"kill switch armed ({path}): no more buys, LLM and random portfolios are flattened.")
    if not a.now:
        _journal_kill(paths, True, "cli", now)
        print("Takes effect at the next cycle at the latest; use `arena kill --now` to flatten immediately.")
        return 0
    t0 = time.monotonic()
    rep = cyc.flatten_now(paths, clients, now)
    print(f"immediate flatten: {rep.status}, {rep.n_fills} fills in {time.monotonic() - t0:.1f} s")
    if rep.error:
        print(f"error: {rep.error}", file=sys.stderr)
    return 0 if rep.status == "completed" else 1


def cmd_unkill(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    removed = killswitch.deactivate(paths)
    _journal_kill(paths, False, "cli", now)
    print("kill switch released: " + (", ".join(map(str, removed)) if removed else "it was not armed."))
    print("Buying resumes at the next cycle (flattened positions are not bought back).")
    return 0


def cmd_ack(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    dormancy.write_ack(paths, now)
    # Journaled so that the site can date each pause for absence (arena/site/pauses.py); var/ack keeps only the last.
    try:
        if verify(paths.journal).ok:
            Journal(paths.journal).append("operator_ack", {"ack_ts": now}, now)
    except JournalError as exc:
        print(f"journal not written: {exc}", file=sys.stderr)
    print(f"presence confirmed ({_iso(now)}): dormancy restarts from zero.")
    return 0


def cmd_resume(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    if not verify(paths.journal).ok:
        print("broken journal: resume refused (see docs/RUNBOOK.md).", file=sys.stderr)
        return 1
    j = Journal(paths.journal)
    states = replay(j.events())
    if a.portfolio not in states:
        print(f"unknown portfolio: {a.portfolio} (known: {', '.join(sorted(states))})", file=sys.stderr)
        return 2
    if a.portfolio in retired_portfolios(j.events()):
        print(f"{a.portfolio} is retired from the league (archived): it never plays again.", file=sys.stderr)
        return 2
    j.append("portfolio_resumed", {"portfolio": a.portfolio, "reason": "manual", "until_ts": 0}, now)
    print(f"{a.portfolio} resumed: freeze and halt lifted, its decisions resume at the next cycle.")
    return 0


def cmd_retire(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    from arena.retired import RetiredError, retired_portfolio

    try:
        out = retired_portfolio(paths, clients, a.portfolio, now, reason=a.reason, note=a.note)
    except RetiredError as exc:
        print(f"retirement refused: {exc}", file=sys.stderr)
        return 1
    if out["status"] == "already_retired":
        print(f"{a.portfolio}: already retired, nothing to do.")
    else:
        print(f"{a.portfolio} retired: {out['fills']} position(s) sold at the bid, frozen value {_eur(out['equity_ueur'])}.")
        print("No more cycles or wake-ups for it; its return stays on the site, dashed.")
    return 0


def _status_season(paths: Paths, ev: list[dict], now: int) -> None:
    """Season: pending, in progress (day N of D) or ended, and performance since `season_reference`."""
    try:
        cfg = load_config(paths.config)
    except ConfigError:
        cfg = None
    starts = [e["payload"] for e in ev if e["type"] == "season_started"]
    if not starts:
        if cfg is not None and cfg.season is not None:
            s = cfg.season
            print(f"season: {s.name} pending (starts at the cycle of {_iso(s.start_ts)}, {s.duration_days} days)")
        return
    d = starts[-1]
    ends = [e["payload"] for e in ev if e["type"] == "season_ended" and e["payload"]["number"] == d["number"]]
    refs = [e["payload"] for e in ev if e["type"] == "season_reference" and e["payload"]["number"] == d["number"]]
    duration = (d["planned_cycle_end"] - d["cycle"]) // 86_400
    waiver = sum(1 for e in ev if e["type"] == "season_waiver" and e["payload"]["number"] == d["number"])
    if ends:
        state = f"ended (cycle {_iso(ends[0]['cycle'])})"
    else:
        state = f"in progress (day {min(duration, max(0, now - d['cycle']) // 86_400 + 1)} of {duration})"
    print(f"season: {d['name']} {state}, start {_iso(d['cycle'])}, waivers: {waiver}")
    if not refs:
        print("  (no season_reference yet)")
        return
    base = refs[0]["equity"]
    last = ends[0]["equity"] if ends else {}
    if not ends:
        for e in ev:
            if e["type"] == "equity":
                last[e["payload"]["portfolio"]] = e["payload"]["equity_ueur"]
            elif e["type"] == "portfolio_retired":
                last[e["payload"]["portfolio"]] = e["payload"]["equity_ueur"]
    print("  performance since the reference (equity at the bid):")
    for p, b in sorted(base.items()):
        cur = last.get(p, b)
        print(f"  {p:28s} {_eur(cur):>16s} {(cur - b) * 100 / b if b else 0:+7.2f}%")


def cmd_status(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    rep = verify(paths.journal)
    print(f"journal: {'OK' if rep.ok else 'BROKEN'}  {rep.n_records} events  head {rep.head_hash[:12]}")
    for e in rep.errors[:5]:
        print(f"  ! {e.code} line {e.line}: {e.message}")
    if rep.n_records == 0 or not rep.ok:
        return 0 if rep.ok else 1
    ev = Journal(paths.journal).events()
    done = [e["payload"]["cycle"] for e in ev if e["type"] == "cycle_completed"]
    started = [e["payload"]["cycle"] for e in ev if e["type"] == "cycle_started"]
    last = f"{_iso(done[-1])} ({(now - done[-1]) // 3600} h)" if done else "none"
    pending = f"  ! cycle {_iso(started[-1])} started but not completed" if started and (not done or started[-1] > done[-1]) else ""
    print(f"last completed cycle: {last}  ({len(done)} in total)")
    if pending:
        print(pending)
    states = replay(ev)
    eq = {e["payload"]["portfolio"]: e["payload"]["equity_ueur"] for e in ev if e["type"] == "equity"}
    capital = {e["payload"]["portfolio"]: e["payload"]["capital_ueur"] for e in ev if e["type"] == "portfolio_opened"}
    retired_set = retired_portfolios(ev)
    for e in ev:
        if e["type"] == "portfolio_retired":  # the value frozen at retirement (after the sale), not the last cycle's
            eq[e["payload"]["portfolio"]] = e["payload"]["equity_ueur"]
    print("equity (at the bid):")
    for p, st in sorted(states.items()):
        cur = eq.get(p, capital.get(p, 0))
        flag = " RETIRED" if p in retired_set else " HALTED" if st.halted else " FROZEN" if st.frozen_until_ts > now else ""
        pct = (cur - capital[p]) * 100 / capital[p] if capital.get(p) else 0
        print(f"  {p:28s} {_eur(cur):>16s} {pct:+6.2f}%  positions={len(st.positions)}{flag}")
    _status_season(paths, ev, now)
    srcs = killswitch.active_sources(paths)
    print(f"kill switch: {'ARMED (' + ', '.join(srcs) + ')' if srcs else 'inactive'}")
    first = ev[0]["ts"]
    age = dormancy.age_s(paths, now, first)
    print(f"dormancy: last ack {age // 3600} h ago  ({dormancy.level(age)}); limits 7 d / 9 d")
    alerts = [e for e in ev if e["type"] == "alert"]
    if alerts:
        al = alerts[-1]
        print(f"last alert: [{al['payload']['level']}] {al['payload']['code']} {_iso(al['ts'])}: {al['payload']['message']}")
    else:
        print("last alert: none")
    return 0


def cmd_verify(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    rep = verify(paths.journal)
    print(f"journal {paths.journal}: {'OK' if rep.ok else 'BROKEN'}  {rep.n_records} events  head {rep.head_hash}")
    for e in rep.errors[:20]:
        print(f"  {e.code} line {e.line} (seq {e.seq}): {e.message}")
    return 0 if rep.ok else 1


def cmd_rebuild_ledger(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    if not verify(paths.journal).ok:
        print("broken journal: rebuild refused.", file=sys.stderr)
        return 1
    counts = rebuild_sqlite(Journal(paths.journal).iter_events(), paths.sqlite)
    print(f"{paths.sqlite} rebuilt: {counts}")
    return 0


def cmd_build_site(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    return _build_site(paths, clients, now)


def cmd_smoke_llm(a: argparse.Namespace, paths: Paths, clients: cyc.Clients, now: int) -> int:
    cfg = load_config(paths.config)
    if cfg.decider_backend == "api" and not anthropic_key(paths):
        print("refused: no API key (anthropic_api_key); nothing was called.", file=sys.stderr)
        return 2
    deciders = cyc.default_deciders(cfg, paths)
    decider = deciders.get(a.portfolio)
    if decider is None:
        print(f"unknown LLM portfolio: {a.portfolio} (known: {', '.join(deciders)})", file=sys.stderr)
        return 2
    snapshot = cyc.smoke_snapshot(paths, clients, a.portfolio, now)
    res = decider.decide(snapshot, 0)
    print(f"single call, no order executed, nothing journaled. model requested {decider.model}")
    if res.skipped_reason:
        print(f"not called / failed: {res.skipped_reason} {res.error or ''}", file=sys.stderr)
        return 1
    n = len((res.parsed or {}).get("actions", []))
    print(f"model returned {res.model_returned}  tokens {res.input_tokens}/{res.output_tokens}  cost {res.cost_uusd} µ$  {res.latency_ms} ms")
    print(f"format: {'valid, ' + str(n) + ' action(s)' if res.parse_error is None else 'INVALID: ' + res.parse_error}")
    if res.parsed:
        print(f"justification: {res.parsed['justification'][:300]}")
    return 0 if res.parse_error is None else 1


# ---------------------------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="arena", description="Trading arena (paper).")
    ap.add_argument("--var", help="state directory (default: $ARENA_VAR or the repository's var/)")
    ap.add_argument("--secrets", help="secrets directory (default: $ARENA_SECRETS or ~/.config/arena/secrets)")
    ap.add_argument("--config", help="alternative config/arena.toml")
    ap.add_argument("--policy", help="alternative config/policy.toml")
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("cycle", help="run (or resume) the current cycle")
    c.add_argument("--no-site", action="store_true", help="do not rebuild the site after the cycle")
    w = sub.add_parser("watch", help="one watch tick (live stops, possible wake-up), no LLM except on a wake-up")
    w.add_argument("--no-site", action="store_true", help="do not request a site rebuild after a wake-up")
    k = sub.add_parser("kill", help="arm the kill switch")
    k.add_argument("--now", action="store_true", help="flatten immediately (LLM and random portfolios)")
    sub.add_parser("unkill", help="release the kill switch")
    sub.add_parser("ack", help="confirm the operator's presence (resets dormancy)")
    r = sub.add_parser("resume", help="resume a frozen or halted portfolio")
    r.add_argument("portfolio")
    rt = sub.add_parser("retired", help="retire a model from the league: sell everything at the bid, archive (irreversible)")
    rt.add_argument("portfolio")
    rt.add_argument("--reason", default="manual", help="reason (journaled)")
    rt.add_argument("--note", default="", help="free-form note (journaled, never published)")
    sub.add_parser("status", help="human-readable status summary")
    sub.add_parser("verify", help="verify the journal chain")
    sub.add_parser("rebuild-ledger", help="rebuild var/ledger.sqlite from the journal")
    sub.add_parser("build-site", help="build the dashboard into var/site")
    s = sub.add_parser("smoke-llm", help="one real model call, without executing any order")
    s.add_argument("portfolio")
    return ap


COMMANDS: dict[str, Callable[..., int]] = {
    "cycle": cmd_cycle,
    "watch": cmd_watch,
    "kill": cmd_kill,
    "unkill": cmd_unkill,
    "ack": cmd_ack,
    "resume": cmd_resume,
    "retired": cmd_retire,
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
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per request: too chatty
    args = build_parser().parse_args(argv)
    paths = Paths.from_env(args.var, args.secrets, args.config, args.policy)
    ts = now() if now else int(time.time())
    try:
        return COMMANDS[args.command](args, paths, clients or cyc.Clients.real(), ts)
    except (ConfigError, PolicyError) as exc:
        print(f"invalid configuration: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
