"""Exécuteur simulé (paper) : machine à états d'ordre, idempotence, stops, détention maximale.

Tout passe par le journal. Ordre d'écriture d'une entrée : SUBMITTING, ACKED, `fill`, `stop_set`, FILLED.
Le fill est écrit AVANT l'état FILLED : un crash ne peut jamais laisser un état FILLED sans fill. À la
reprise, un fill présent sans stop_set ni FILLED est complété ; un ordre resté en SUBMITTING/ACKED sans fill
n'est jamais renvoyé : il passe UNKNOWN puis `resolve_unknown` l'annule (en paper, réputé non exécuté).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from arene.journal import Journal, fill_from_payload
from arene.ledger import replay
from arene.sim.fills import FILL_MODEL_VERSION, market_fill, stop_fill, stop_price
from arene.types import (
    Bar,
    Fill,
    Instrument,
    Intent,
    OrderState,
    Quote,
    Side,
    VenueMode,
    Verdict,
    notional_ueur,
)

_DONE = {OrderState.FILLED, OrderState.CANCELED, OrderState.RISK_REJECTED, OrderState.UNKNOWN}
DEFAULT_CYCLE_S = 14_400


class SimExecutor:
    def __init__(
        self,
        journal: Journal,
        instruments: Mapping[str, Instrument] | Iterable[Instrument],
        fee_bp: int,
        slippage_bp: int,
        venue_mode: VenueMode = "paper",
        fault_injector: Callable[[str], bool] | None = None,
    ):
        """`fault_injector(order_id) -> True` fait passer l'ordre en UNKNOWN (sans fill), pour les tests."""
        self.journal = journal
        self.instruments: dict[str, Instrument] = (
            dict(instruments) if isinstance(instruments, Mapping) else {i.symbol: i for i in instruments}
        )
        self.fee_bp = fee_bp
        self.slippage_bp = slippage_bp
        self.venue_mode: VenueMode = venue_mode
        self.fault_injector = fault_injector

    # ------------------------------------------------------------------ lecture du journal

    def _scan(self) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
        """(états successifs par order_id, payload du fill par order_id)."""
        states: dict[str, list[str]] = {}
        fills: dict[str, dict[str, Any]] = {}
        for ev in self.journal.iter_events():
            p = ev["payload"]
            if ev["type"] == "order_state":
                states.setdefault(p["order_id"], []).append(p["state"])
            elif ev["type"] == "fill":
                fills[p["order_id"]] = p
        return states, fills

    def _state_of(self, order_id: str) -> list[str]:
        return self._scan()[0].get(order_id, [])

    def _log_state(self, order_id: str, state: OrderState, detail: str, now_ts: int, **extra: Any) -> None:
        self.journal.append(
            "order_state", {"order_id": order_id, "state": state.value, "detail": detail, **extra}, now_ts
        )

    # ------------------------------------------------------------------ entrées

    def execute(self, intent: Intent, verdict: Verdict, quote: Quote, now_ts: int) -> Fill | None:
        """Exécute une intention approuvée. Renvoie le Fill, ou None (rejet, annulation, UNKNOWN, déjà traité)."""
        oid = intent.intent_id
        states, fills = self._scan()
        if oid in fills:
            self._repair(intent, fills[oid], states.get(oid, []), now_ts)
            return None
        hist = states.get(oid, [])
        if any(s in {x.value for x in _DONE} for s in hist):
            return None
        if hist:  # SUBMITTING/ACKED sans issue (crash) : on n'envoie JAMAIS un second ordre
            self._log_state(
                oid,
                OrderState.UNKNOWN,
                "reprise après interruption : issue inconnue",
                now_ts,
                portfolio=intent.portfolio,
            )
            return None
        if not verdict.approved or verdict.intent_id != oid:
            self._log_state(
                oid,
                OrderState.RISK_REJECTED,
                ",".join(verdict.reasons) or "non approuvé",
                now_ts,
                portfolio=intent.portfolio,
            )
            return None

        reason = self._pre_check(intent, verdict, quote)
        price = fee = 0
        if reason is None:
            inst = self.instruments[intent.symbol]
            price, fee = market_fill(intent.side, verdict.qty, quote, inst, self.fee_bp, self.slippage_bp)
            reason = self._funds_check(intent, verdict.qty, price, fee)
            if reason is None and intent.side == Side.BUY:
                # Le quote d'exécution peut avoir bougé depuis le verdict : jamais payer plus que riskd n'a réservé.
                total = notional_ueur(verdict.qty, price, round_up=True) + fee
                if total > verdict.reserved_ueur:
                    reason = f"prix d'exécution au-delà de la réservation de riskd ({total} > {verdict.reserved_ueur})"
        if reason is not None:
            self._log_state(oid, OrderState.CANCELED, reason, now_ts, portfolio=intent.portfolio)
            return None

        self._log_state(oid, OrderState.SUBMITTING, "", now_ts, portfolio=intent.portfolio)
        if self.fault_injector is not None and self.fault_injector(oid):
            self._log_state(oid, OrderState.UNKNOWN, "faute injectée", now_ts, portfolio=intent.portfolio)
            return None
        self._log_state(oid, OrderState.ACKED, "", now_ts, portfolio=intent.portfolio)
        fill = Fill(
            oid,
            intent.portfolio,
            intent.symbol,
            intent.side,
            verdict.qty,
            price,
            fee,
            now_ts,
            self.venue_mode,
            FILL_MODEL_VERSION,
            "intent",
        )
        self.journal.append("fill", fill, now_ts)
        self._repair(intent, None, [OrderState.ACKED.value], now_ts, fill)
        return fill

    def _pre_check(self, intent: Intent, verdict: Verdict, quote: Quote) -> str | None:
        inst = self.instruments.get(intent.symbol)
        if inst is None:
            return f"instrument inconnu : {intent.symbol}"
        if quote.symbol != intent.symbol:
            return "quote d'un autre symbole"
        qty = verdict.qty
        if qty <= 0 or qty < inst.lot_min_qty:
            return f"quantité {qty} sous le minimum {inst.lot_min_qty}"
        ref = quote.ask if intent.side == Side.BUY else quote.bid
        if notional_ueur(qty, ref, round_up=False) < inst.cost_min_ueur:
            return f"notional sous le coût minimal {inst.cost_min_ueur}"
        return None

    def _funds_check(self, intent: Intent, qty: int, price: int, fee: int) -> str | None:
        st = replay(self.journal.iter_events()).get(intent.portfolio)
        if st is None:
            return f"portefeuille inconnu : {intent.portfolio}"
        if intent.side == Side.BUY:
            total = notional_ueur(qty, price, round_up=True) + fee
            if total > st.cash_ueur:
                return f"cash insuffisant ({total} > {st.cash_ueur})"
        else:
            pos = st.positions.get(intent.symbol)
            if pos is None or qty > pos.qty:
                return f"vente supérieure à la position ({qty} > {pos.qty if pos else 0})"
        return None

    def _repair(
        self,
        intent: Intent,
        fill_payload: dict[str, Any] | None,
        hist: list[str],
        now_ts: int,
        fill: Fill | None = None,
    ) -> None:
        """Complète stop_set et l'état FILLED après un fill (nominal, ou reprise après crash)."""
        if fill is None:
            assert fill_payload is not None
            fill = fill_from_payload(fill_payload)
            stops = [e for e in self.journal.iter_events() if e["type"] == "stop_set"]
            has_stop = any(
                e["payload"]["portfolio"] == fill.portfolio
                and e["payload"]["symbol"] == fill.symbol
                and e["ts"] >= fill.ts
                for e in stops
            )
        else:
            has_stop = False
        if fill.side == Side.BUY and intent.stop_bp is not None and not has_stop and self._holds(fill):
            stop = stop_price(fill.price_ueur, intent.stop_bp, self.instruments[fill.symbol])
            # Un second achat ne doit jamais desserrer le stop des lots déjà détenus (stop 25 % sur 1 % de plus).
            stop = max(stop, self._current_stop(fill))
            self.journal.append(
                "stop_set", {"portfolio": fill.portfolio, "symbol": fill.symbol, "stop_ueur": stop}, fill.ts
            )
        if OrderState.FILLED.value not in hist:
            self._log_state(fill.order_id, OrderState.FILLED, "", now_ts, portfolio=fill.portfolio)

    def _holds(self, fill: Fill) -> bool:
        """Vrai si le portefeuille détient encore le symbole : un stop_set sur une position soldée entre-temps
        (mise à plat à la reprise après crash) ferait lever `replay` pour toujours."""
        st = replay(self.journal.iter_events()).get(fill.portfolio)
        return st is not None and fill.symbol in st.positions

    def _current_stop(self, fill: Fill) -> int:
        """Stop déjà posé sur la position avant ce fill (0 si aucun)."""
        st = replay(self.journal.iter_events()).get(fill.portfolio)
        pos = st.positions.get(fill.symbol) if st else None
        return pos.stop_ueur or 0 if pos else 0

    # ------------------------------------------------------------------ UNKNOWN

    def resolve_unknown(self, order_id: str, now_ts: int) -> bool:
        """Paper : un ordre UNKNOWN est réputé non exécuté, il passe CANCELED. Renvoie True si annulé."""
        hist = self._state_of(order_id)
        if not hist or hist[-1] != OrderState.UNKNOWN.value:
            return False
        self._log_state(order_id, OrderState.CANCELED, "UNKNOWN résolu : réputé non exécuté (paper)", now_ts)
        return True

    def unknown_age_cycles(self, portfolio: str, now_ts: int, cycle_s: int = DEFAULT_CYCLE_S) -> int:
        """Âge en cycles du plus ancien ordre UNKNOWN non résolu du portefeuille (0 si aucun).

        Le cycle gèle le portefeuille si ce nombre dépasse 2.
        """
        owner: dict[str, str] = {}
        since: dict[str, int] = {}
        for ev in self.journal.iter_events():
            p = ev["payload"]
            if ev["type"] != "order_state":
                continue
            oid = p["order_id"]
            if "portfolio" in p:
                owner[oid] = p["portfolio"]
            if p["state"] == OrderState.UNKNOWN.value:
                since.setdefault(oid, ev["ts"])
            else:
                since.pop(oid, None)
        return max(
            ((now_ts - ts) // cycle_s for oid, ts in since.items() if owner.get(oid) == portfolio), default=0
        )

    # ------------------------------------------------------------------ sorties forcées

    def _forced_sell(
        self,
        order_id: str,
        portfolio: str,
        symbol: str,
        qty: int,
        price: int,
        fee: int,
        now_ts: int,
        reason: str,
    ) -> Fill:
        fill = Fill(
            order_id,
            portfolio,
            symbol,
            Side.SELL,
            qty,
            price,
            fee,
            now_ts,
            self.venue_mode,
            FILL_MODEL_VERSION,
            reason,
        )
        self.journal.append("fill", fill, now_ts)
        self._log_state(order_id, OrderState.FILLED, reason, now_ts, portfolio=portfolio)
        return fill

    def process_stops_and_expiry(
        self,
        bars_since_last_cycle: Mapping[str, list[Bar]],
        quotes: Mapping[str, Quote],
        now_ts: int,
        max_holding_s: int,
    ) -> list[Fill]:
        """Stops barre par barre (ordre chronologique), puis détention maximale. Idempotent."""
        out: list[Fill] = []
        _, done_fills = self._scan()
        done = set(done_fills)
        for pname, st in sorted(replay(self.journal.iter_events()).items()):
            for sym, pos in sorted(st.positions.items()):
                inst = self.instruments.get(sym)
                if inst is None:
                    continue
                sold = False
                if pos.stop_ueur is not None:
                    for bar in sorted(bars_since_last_cycle.get(sym, []), key=lambda b: b.ts):
                        if bar.ts < pos.opened_ts:
                            continue  # barre commencée avant l'entrée
                        px = stop_fill(pos.stop_ueur, bar, inst, self.slippage_bp)
                        if px is None:
                            continue
                        oid = f"stop:{pname}:{sym}:{bar.ts}"
                        if oid in done:
                            break
                        _, fee = market_fill(
                            Side.SELL, pos.qty, Quote(sym, bar.ts, px, px), inst, self.fee_bp, 0
                        )
                        out.append(self._forced_sell(oid, pname, sym, pos.qty, px, fee, now_ts, "stop"))
                        done.add(oid)
                        sold = True
                        break
                if sold or now_ts - pos.opened_ts < max_holding_s:
                    continue
                q = quotes.get(sym)
                oid = f"exit:{pname}:{sym}:{pos.opened_ts}:max_holding"
                if q is None or oid in done:
                    continue
                px, fee = market_fill(Side.SELL, pos.qty, q, inst, self.fee_bp, self.slippage_bp)
                out.append(self._forced_sell(oid, pname, sym, pos.qty, px, fee, now_ts, "max_holding"))
                done.add(oid)
        return out

    def process_live_stops(self, quotes: Mapping[str, Quote], tick: int) -> list[Fill]:
        """Stops en direct de la veille : toute position dont le bid est au niveau du stop (ou en dessous) est
        vendue tout de suite, au bid avec glissement et frais taker. `order_id` = stop:{portefeuille}:{symbole}:veille:{tick},
        idempotent. Le contrôle sur barres du cycle suivant part des positions rejouées : il ne revend rien."""
        out: list[Fill] = []
        _, done_fills = self._scan()
        for pname, st in sorted(replay(self.journal.iter_events()).items()):
            for sym, pos in sorted(st.positions.items()):
                inst, q = self.instruments.get(sym), quotes.get(sym)
                if inst is None or q is None or pos.stop_ueur is None or q.bid > pos.stop_ueur:
                    continue
                oid = f"stop:{pname}:{sym}:veille:{tick}"
                if oid in done_fills:
                    continue
                px, fee = market_fill(Side.SELL, pos.qty, q, inst, self.fee_bp, self.slippage_bp)
                out.append(self._forced_sell(oid, pname, sym, pos.qty, px, fee, tick, "stop"))
        return out

    def flatten(self, portfolio: str, quotes: Mapping[str, Quote], now_ts: int, reason: str) -> list[Fill]:
        """Vend toutes les positions au bid (reason : "kill_switch" ou "halt"). Idempotent par (now_ts, reason)."""
        st = replay(self.journal.iter_events()).get(portfolio)
        if st is None:
            return []
        _, done_fills = self._scan()
        out: list[Fill] = []
        for sym, pos in sorted(st.positions.items()):
            q, inst = quotes.get(sym), self.instruments.get(sym)
            oid = f"exit:{portfolio}:{sym}:{now_ts}:{reason}"
            if q is None or inst is None or oid in done_fills:
                continue
            px, fee = market_fill(Side.SELL, pos.qty, q, inst, self.fee_bp, self.slippage_bp)
            out.append(self._forced_sell(oid, portfolio, sym, pos.qty, px, fee, now_ts, reason))
        return out
