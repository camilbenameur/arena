"""Retirement of a model from the scored league (the portfolio is archived and shown dashed on the site).

`retired_portfolio(paths, clients, portfolio, now_ts)` takes the cycle lock (no cycle or wake-up is running, none
can start), reads a fresh Kraken quote for each position, sells everything at the bid with the simulator's fill model
(reason `retired`), then journals `portfolio_retired` (frozen equity = the cash, quotes used). From then on the cycle
and the watch neither trade nor value this portfolio (`arena.ledger.retired_portfolios`), and the site draws its
curve dashed, stopping at the retirement. Idempotent: an already retired portfolio is left untouched. Fails
closed: without a valid quote for every position, nothing is written.

The quotes are NOT journaled as `quote` events (the site attaches those to the current cycle, and they would skew the
random-trader replay): they live in the payload of `portfolio_retired`.
"""

from __future__ import annotations

from typing import Any

from arena import cycle as cyc
from arena.config import load_config, load_instruments
from arena.journal import Journal, verify
from arena.ledger import replay, retired_portfolios
from arena.paths import Paths
from arena.sim.executor import SimExecutor
from arena.types import Quote
from arena.watch import quote_valid

LOCK_WAIT_S = 600.0  # a cycle or a wake-up may hold the lock for a few minutes: we wait for it, never run alongside it
REASON_FILL = "retired"


class RetiredError(RuntimeError):
    """The portfolio is not retired (nothing was written, or only sales that `retired` resumes)."""


def retired_portfolio(
    paths: Paths,
    clients: cyc.Clients,
    portfolio: str,
    now_ts: int,
    *,
    reason: str = "manual",
    note: str = "",
    lock_wait_s: float = LOCK_WAIT_S,
) -> dict[str, Any]:
    """Returns {"status": "retired" | "already_retired", "fills": n, "equity_ueur": n}."""
    journal = Journal(paths.journal)
    try:
        with cyc.cycle_lock(paths, lock_wait_s):
            if not verify(paths.journal).ok:
                raise RetiredError("broken journal: retirement refused (see docs/RUNBOOK.md)")
            cfg = load_config(paths.config)
            if portfolio not in [m.portfolio for m in cfg.models]:
                raise RetiredError(f"{portfolio}: only an AI model from the config can be retired, not a benchmark")
            elog = cyc.EventLog(journal)
            elog.refresh()
            states = replay(elog.events)
            st = states.get(portfolio)
            if st is None:
                raise RetiredError(f"{portfolio}: never opened in this journal")
            if portfolio in retired_portfolios(elog.events):
                return {"status": "already_retired", "fills": 0, "equity_ueur": st.cash_ueur}
            quotes: dict[str, Quote] = {}
            fills = 0
            if st.positions:
                instruments = {
                    i.symbol: i
                    for i in load_instruments(cfg, clients.kraken, cache=paths.var / "asset_pairs.json", now=now_ts)
                }
                for sym in sorted(st.positions):
                    inst = instruments.get(sym)
                    if inst is None:
                        raise RetiredError(f"{portfolio}: {sym} is no longer in the config, cannot sell it")
                    try:
                        q = clients.kraken.ticker(sym, inst.kraken_pair)
                    except Exception as exc:  # noqa: BLE001 - whatever the failure: nothing is written
                        raise RetiredError(f"{portfolio}: quote {sym} unreadable ({type(exc).__name__}): nothing written") from exc
                    if not quote_valid(q.bid, q.ask):
                        raise RetiredError(f"{portfolio}: quote {sym} invalid ({q.bid}/{q.ask}): nothing written")
                    quotes[sym] = q
                ex = SimExecutor(journal, instruments, cfg.taker_fee_bp, cfg.slippage_bp, cfg.venue_mode)
                fills = len(ex.flatten(portfolio, quotes, now_ts, REASON_FILL))
                elog.refresh()
                st = replay(elog.events)[portfolio]
                if st.positions:  # a zero price at the fill: never archive a portfolio that is still exposed
                    raise RetiredError(f"{portfolio}: remaining positions {sorted(st.positions)}: rerun `arena retired`")
            elog.add(
                "portfolio_retired",
                {
                    "portfolio": portfolio, "ts": now_ts, "reason": reason[:200], "note": note[:500],
                    "equity_ueur": st.cash_ueur, "fills": fills,
                    "quotes": {s: [q.bid, q.ask] for s, q in sorted(quotes.items())},
                },
                now_ts,
            )
            return {"status": "retired", "fills": fills, "equity_ueur": st.cash_ueur}
    except cyc.CycleBusy as exc:
        raise RetiredError(f"cycle lock still held after {lock_wait_s:.0f} s: retry ({exc})") from exc
