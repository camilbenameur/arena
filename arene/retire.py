"""Retrait d'un modèle de la ligue comptant (demande du 17/11/2026 : « on va passer Fable en pointillé, en archive »).

`retire_portfolio(paths, clients, portfolio, now_ts)` prend le verrou du cycle (ni cycle ni réveil ne tourne, aucun
ne démarre), lit un quote Kraken frais pour chaque position, vend tout au bid avec le modèle de fill du simulateur
(raison `retired`), puis journalise `portfolio_retired` (equity figée = le cash, quotes utilisés). Dès lors le cycle
et la veille ne jouent ni ne valorisent plus ce portefeuille (`arene.ledger.retired_portfolios`), et le site dessine
sa courbe en pointillés, arrêtée à ce retrait. Idempotent : un portefeuille déjà retiré n'est pas touché. Ferme
fermé : sans quote valide pour chaque position, rien n'est écrit.

Les quotes ne sont PAS journalisés en événements `quote` (le site les rattache au cycle en cours et fausserait le
rejeu du hasard) : ils sont dans le payload de `portfolio_retired`.
"""

from __future__ import annotations

from typing import Any

from arene import cycle as cyc
from arene.config import load_config, load_instruments
from arene.journal import Journal, verify
from arene.ledger import replay, retired_portfolios
from arene.paths import Paths
from arene.sim.executor import SimExecutor
from arene.types import Quote
from arene.veille import quote_valide

LOCK_WAIT_S = 600.0  # un cycle ou un réveil peut tenir le verrou quelques minutes : on l'attend, on ne le double jamais
RAISON_FILL = "retired"


class RetireError(RuntimeError):
    """Le portefeuille n'est pas retiré (rien n'a été écrit, ou seulement des ventes que `retire` reprend)."""


def retire_portfolio(
    paths: Paths,
    clients: cyc.Clients,
    portfolio: str,
    now_ts: int,
    *,
    reason: str = "manual",
    note: str = "",
    lock_wait_s: float = LOCK_WAIT_S,
) -> dict[str, Any]:
    """Renvoie {"status": "retired" | "already_retired", "fills": n, "equity_ueur": n}."""
    journal = Journal(paths.journal)
    try:
        with cyc.cycle_lock(paths, lock_wait_s):
            if not verify(paths.journal).ok:
                raise RetireError("journal cassé : retrait refusé (voir docs/RUNBOOK.md)")
            cfg = load_config(paths.config)
            if portfolio not in [m.portfolio for m in cfg.models]:
                raise RetireError(f"{portfolio} : seul un modèle d'IA de la config peut être retiré, pas un témoin")
            elog = cyc.EventLog(journal)
            elog.refresh()
            states = replay(elog.events)
            st = states.get(portfolio)
            if st is None:
                raise RetireError(f"{portfolio} : jamais ouvert dans ce journal")
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
                        raise RetireError(f"{portfolio} : {sym} n'est plus dans la config, impossible de le vendre")
                    try:
                        q = clients.kraken.ticker(sym, inst.kraken_pair)
                    except Exception as exc:  # noqa: BLE001 - quoi que ce soit : on n'écrit rien
                        raise RetireError(f"{portfolio} : quote {sym} illisible ({type(exc).__name__}) : rien d'écrit") from exc
                    if not quote_valide(q.bid, q.ask):
                        raise RetireError(f"{portfolio} : quote {sym} invalide ({q.bid}/{q.ask}) : rien d'écrit")
                    quotes[sym] = q
                ex = SimExecutor(journal, instruments, cfg.taker_fee_bp, cfg.slippage_bp, cfg.venue_mode)
                fills = len(ex.flatten(portfolio, quotes, now_ts, RAISON_FILL))
                elog.refresh()
                st = replay(elog.events)[portfolio]
                if st.positions:  # un prix nul au fill : ne jamais archiver un portefeuille encore exposé
                    raise RetireError(f"{portfolio} : positions restantes {sorted(st.positions)} : relancer `arene retire`")
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
        raise RetireError(f"verrou du cycle toujours occupé après {lock_wait_s:.0f} s : réessayer ({exc})") from exc
