"""Retiring a portfolio that plays: a council (its journal then stays as data) or a
solo model of the LLM league (it is archived).

`python -m arena.perp.retire --portfolio llm-perp:<model>` (or `council-perp:<name>`; the council command
`python -m arena.perp.council retire` is the same thing).

`retire_portfolio` takes the watcher's lock (no round is running, none starts), flattens the portfolio at market
on a fresh market view (reason `retired`), ends its pending agent alerts and entry orders, then journals
`portfolio_retired`. From then on the ledger refuses any entry, the watcher neither values nor calls it, and the
site draws its curve dotted, stopping at that event. Idempotent: a retired portfolio is left alone. Fails closed:
without a fresh quote for every held instrument, nothing is written.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from arena.journal import Journal
from arena.perp import agent_orders as AO
from arena.perp.collect import data_root
from arena.perp.ledger import PerpLedgerError
from arena.perp.margin import LEVERAGED_PREFIX
from arena.perp.market import market_view
from arena.perp.sim import PerpSimulator
from arena.perp.store import PerpDataStore

LLM_PREFIX = "llm-perp:"
RETIRABLE_PREFIXES = (LEVERAGED_PREFIX, LLM_PREFIX)  # the benchmarks are the league's references: never retired
LOCK_WAIT_S = 1200  # a round can hold the watcher lock for a few minutes: wait for it, never race it
VIEW_MAX_AGE_S = 900


class RetiredError(RuntimeError):
    """The portfolio is not retired (nothing was written)."""


@contextlib.contextmanager
def _watcher_lock(path: Path, wait_s: float) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        deadline = time.monotonic() + wait_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RetiredError(f"watcher lock still busy after {wait_s:.0f} s: try again") from None
                time.sleep(1)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def retired_portfolio(
    var: Path,
    portfolio: str,
    now_ts: int,
    *,
    reason: str = "manual",
    note: str = "",
    lock_wait_s: float = LOCK_WAIT_S,
) -> dict[str, Any]:
    """Returns {"status": "retired" | "already_retired", "fills": n, "orders_ended": n}."""
    from arena.perp.config import load_perp_config
    from arena.perp.watcher import load_specs

    if not portfolio.startswith(RETIRABLE_PREFIXES) or portfolio.endswith(":trial"):
        raise RetiredError(f"{portfolio}: only a council ({LEVERAGED_PREFIX}...) or a model ({LLM_PREFIX}...) can be retired")
    cfg = load_perp_config()
    symbols = [i.kraken_symbol for i in cfg.instruments]
    journal = Journal(var / "journal" / "events.jsonl")
    with _watcher_lock(var / "watcher.lock", lock_wait_s):
        specs = load_specs(var, symbols, now_ts)
        sim = PerpSimulator(journal, {s: specs[s].tick_uusd for s in symbols}, cfg.simulation)
        acc = sim.states().get(portfolio)
        if acc is None:
            raise RetiredError(f"{portfolio}: never opened in this journal")
        if acc.retired:
            return {"status": "already_retired", "fills": 0, "orders_ended": 0}
        view = market_view(PerpDataStore(data_root(var)), symbols, now_ts)
        fresh = view is not None and view.fx_bid > 0 and now_ts - view.fx_ts <= VIEW_MAX_AGE_S
        fills = 0
        if acc.positions:
            if (
                view is None
                or not fresh
                or any(i not in view.instruments for i in acc.positions)
                or any(now_ts - view.instruments[i].quote_ts > VIEW_MAX_AGE_S for i in acc.positions)
            ):
                raise RetiredError(
                    f"{portfolio}: no fresh quote or EUR/USD to flatten the positions: nothing written"
                )
            quotes = {s: (m.bid_uusd, m.ask_uusd) for s, m in view.instruments.items()}
            try:
                fills = len(sim.flatten(portfolio, now_ts, quotes, (view.fx_bid, view.fx_ask), "retired"))
            except PerpLedgerError as exc:
                raise RetiredError(f"{portfolio}: flatten refused: {exc}") from exc
        if view is not None and fresh:  # the portfolio's last measure is its final value
            marks = {s: m.mark_uusd for s, m in view.instruments.items()}
            sim.write_equity(portfolio, now_ts, marks, (view.fx_bid, view.fx_ask))
        state = AO.pending_state(journal.events(), portfolio)
        todo = {el.id: el for el in state.pending}
        todo.update({el.id: el for el, _trig in state.unresolved_entries()})
        for el in todo.values():
            sim.append_event(
                "agent_order_ended",
                {"portfolio": portfolio, "id": el.id, "kind": el.kind, "reason": "portfolio_retired"},
                now_ts,
            )
        sim.append_event(
            "portfolio_retired",
            {"portfolio": portfolio, "ts": now_ts, "reason": reason[:200], "note": note[:500]},
            now_ts,
        )
    return {"status": "retired", "fills": fills, "orders_ended": len(todo)}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    from arena.perp.config import default_var

    ap = argparse.ArgumentParser(prog="python -m arena.perp.retire")
    ap.add_argument("--portfolio", required=True, help="llm-perp:<model> or council-perp:<name>")
    ap.add_argument("--var", type=Path, default=None)
    ap.add_argument("--reason", default="manual", help="why (journaled)")
    ap.add_argument("--note", default="", help="free note (journaled, never published)")
    args = ap.parse_args(argv)
    var = (args.var or default_var()).resolve()
    try:
        out = retired_portfolio(var, args.portfolio, int(time.time()), reason=args.reason, note=args.note)
    except RetiredError as exc:
        print(f"{exc}", file=sys.stderr)
        return 3
    if out["status"] == "already_retired":
        print(f"{args.portfolio}: already retired, nothing to do")
    else:
        print(f"{args.portfolio}: retired ({out['fills']} position(s) flattened, {out['orders_ended']} order(s) ended)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
