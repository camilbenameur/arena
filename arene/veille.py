"""Veille continue et réveils sur événement (docs/VEILLE.md).

`run_veille(paths, clients, now_ts, deciders=None)` est lancé toutes les 5 min par `arene-veille.timer`, sans LLM :
1. verrou du cycle SANS attente (cycle ou réveil en cours : sortie sans rien écrire) ; journal cassé : rien écrit ;
2. tick = `now_ts // tick_s * tick_s` ; un événement `veille` déjà journalisé pour ce tick : sortie sans rien écrire ;
3. quotes Kraken (échec : rien écrit, alerte `veille_data` après 3 échecs consécutifs, au plus une par heure) ;
4. stops en direct (`SimExecutor.process_live_stops`), au bid avec glissement et frais, idempotents par `order_id` ;
5. déclencheurs (mouvement, stop LLM) et garde-fous, puis événement `veille` (horodaté au tick) ;
6. réveil : une ronde de décision (LLM et aléatoire) rejouée par `_Runner` (sous-classe `_ReveilRunner`), sous le
   même verrou. Un `reveil_started` sans `reveil_completed` est repris par un tick suivant dans les 30 min, sinon
   abandonné (`reveil_abandonne`).

Le réveil n'écrit jamais d'événement `equity` ; son identifiant (`reveil` = tick) remplit le champ `cycle` des
événements de décision, comme l'identifiant d'un cycle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from arene.config import Config, ConfigError, load_config, load_instruments
from arene.cycle import (
    ALEATOIRE,
    DAY_S,
    Clients,
    CycleAbort,
    CycleBusy,
    EventLog,
    JournalBroken,
    _Runner,
    cycle_lock,
)
from arene.data import DataError
from arene.journal import Journal, verify
from arene.ledger import equity_ueur, replay
from arene.ops.heartbeat import Heartbeat
from arene.ops.notify import Notifier
from arene.paths import Paths
from arene.risk.policy import Policy, PolicyError, load_policy
from arene.sim.executor import SimExecutor
from arene.types import Instrument, Quote

log = logging.getLogger("arene.veille")

BP = 10_000
REVEIL_ABANDON_S = 1800  # un réveil interrompu est repris pendant 30 min, puis abandonné
ECHECS_AVANT_ALERTE = 3
ALERTE_DATA_PERIODE_S = 3600


# ---------------------------------------------------------------------------------------- rapport


@dataclass
class VeilleReport:
    status: str  # done | already_done | inactive | busy | refused | failed | reveil_failed
    tick: int | None = None
    n_events: int = 0  # événements ajoutés au journal par ce lancement
    stops: list[str] = field(default_factory=list)  # order_id des stops de ce tick
    declencheur: dict[str, Any] | None = None  # déclencheur évalué (même s'il a été refusé)
    refus: str | None = None  # garde-fou qui a refusé le réveil
    reveil: str | None = None  # None | completed | resumed | abandonne
    alerts: list[tuple[str, str]] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("done", "already_done", "inactive", "busy")


# ---------------------------------------------------------------------------------------- fonctions pures


def prochain_rendez_vous(ts: int, interval_s: int, cycle_delay_s: int) -> int:
    """Premier instant d'exécution d'un cycle (HH:05 UTC) strictement après `ts`."""
    return (ts - cycle_delay_s) // interval_s * interval_s + interval_s + cycle_delay_s


def mouvement(
    cur: dict[str, tuple[int, int]], ref: dict[str, tuple[int, int]], seuil_bp: int, fenetre_s: int
) -> dict[str, Any] | None:
    """Instrument dont le milieu a bougé d'au moins `seuil_bp` depuis `ref` (le plus grand |variation| l'emporte)."""
    best: tuple[Fraction, str, int, int] | None = None
    for sym in sorted(cur):
        if sym not in ref:
            continue
        mid, rmid = (cur[sym][0] + cur[sym][1]) // 2, (ref[sym][0] + ref[sym][1]) // 2
        if rmid <= 0:
            continue
        d = mid - rmid
        if abs(d) * BP < seuil_bp * rmid:  # |mid/rmid - 1| >= seuil, en entiers : 2,99 % non, 3 % oui
            continue
        score = Fraction(abs(d), rmid)
        if best is None or score > best[0]:
            best = (score, sym, d, rmid)
    if best is None:
        return None
    _, sym, d, rmid = best
    bp = (abs(d) * BP * 2 + rmid) // (2 * rmid)
    return {"type": "mouvement", "symbole": sym, "variation_bp": bp if d > 0 else -bp, "fenetre_s": fenetre_s}


def _quote_valide(q: Quote) -> bool:
    return all(isinstance(x, int) and not isinstance(x, bool) for x in (q.bid, q.ask)) and 0 < q.bid <= q.ask


# ---------------------------------------------------------------------------------------- réveil


class _ReveilRunner(_Runner):
    """Ronde de décision hors rendez-vous : même chemin que le cycle (`_Runner`), moins les barres de stop,
    les témoins de référence et l'equity."""

    def __init__(
        self,
        *args: Any,
        cfg: Config,
        policy: Policy,
        instruments: dict[str, Instrument],
        reveil: int,
        declencheur: dict[str, Any],
        quotes: dict[str, Quote],
    ) -> None:
        super().__init__(*args)
        self.cfg, self.policy, self.instruments = cfg, policy, instruments
        self.t = reveil
        self.declencheur = declencheur
        self.prefetched_quotes = quotes  # quotes du tick, journalisées en `quote` avant la décision
        self.fetch_binance = False  # E0065 ne tourne pas au réveil

    # -- périmètre : portefeuilles LLM et aléatoire seulement
    def _round_portfolios(self) -> tuple[str, ...]:
        return self.llm_portfolios + self._temoins_to_run()

    def _temoins_to_run(self) -> tuple[str, ...]:
        return (ALEATOIRE,) if ALEATOIRE in self.temoin_portfolios else ()

    def _contexte(self) -> dict[str, Any]:
        return {
            "type": "reveil",
            "declencheur": self.declencheur,
            "prochain_rendez_vous_ts": prochain_rendez_vous(self.t, self.cfg.interval_s, self.cfg.cycle_delay_s),
        }

    def run_reveil(self) -> bool:
        """Exécute ou reprend le réveil `self.t`. Renvoie True si c'est une reprise."""
        t = self.t
        self.log.refresh()
        self._config_and_portfolios()
        self.symbols = tuple(self.instruments)
        self.executor = SimExecutor(
            self.journal, self.instruments, self.cfg.taker_fee_bp, self.cfg.slippage_bp, self.cfg.venue_mode,
            self.fault_injector,
        )  # fmt: skip
        completed = sorted(e["payload"]["cycle"] for e in self._events_of("cycle_completed"))
        self.prev_cycle = completed[-1] if completed else None
        self.cycle_index = len(completed)
        started = [e for e in self._events_of("reveil_started") if e["payload"]["reveil"] == t]
        resume = bool(started)
        self._market(resume, started[-1]["seq"] if started else None)
        if resume:
            self.alert("info", "reveil_resumed", f"reprise du réveil {t} interrompu")
        else:
            self.wn("reveil_started", {"reveil": t, "declencheur": self.declencheur})
        self._journal_market()
        self._view()
        self._resolve_unknowns()
        self._freeze_halt()
        self._kill_and_dormancy()
        self._decide_and_execute()
        self.wn("reveil_completed", {"reveil": t})
        return resume


# ---------------------------------------------------------------------------------------- tick


class _Veille:
    def __init__(
        self,
        paths: Paths,
        clients: Clients,
        now: int,
        journal: Journal,
        notifier: Notifier,
        deciders: dict[str, Any] | None,
        fault_injector: Any,
        on_portfolio_done: Any,
    ) -> None:
        self.paths, self.clients, self.now = paths, clients, now
        self.journal, self.notifier = journal, notifier
        self.deciders, self.fault_injector, self.on_portfolio_done = deciders, fault_injector, on_portfolio_done
        self.log = EventLog(journal)
        self.alerts: list[tuple[str, str]] = []

    # -- utilitaires
    def _alert(self, level: str, code: str, message: str) -> None:
        self.notifier.alert(level, code, message, self.now)
        self.log.refresh()
        self.alerts.append((level, code))

    def _of(self, *types: str) -> list[dict[str, Any]]:
        return [e for e in self.log.events if e["type"] in types]

    @property
    def _echecs_path(self):
        return self.paths.var / "veille_echecs"

    def _echecs(self, delta: int | None) -> int:
        """Compteur d'échecs consécutifs de lecture des quotes (fichier d'état, hors journal) ; `None` le remet à 0."""
        p = self._echecs_path
        try:
            n = int(p.read_text().strip() or 0)
        except (OSError, ValueError):
            n = 0
        new = 0 if delta is None else n + delta
        if new != n or (delta is None and p.exists()):
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(str(new))
            except OSError:
                pass
        return new

    # -- tick
    def run(self) -> VeilleReport:
        paths = self.paths
        if not verify(paths.journal).ok:
            raise JournalBroken("journal cassé")  # rien n'est écrit : le cycle se charge de l'alerte
        try:
            cfg = load_config(paths.config)
            policy = load_policy(paths.policy)
        except (ConfigError, PolicyError) as exc:
            return VeilleReport("failed", error=f"configuration refusée : {exc}")
        self.cfg, self.policy, v = cfg, policy, cfg.veille
        self.log.refresh()
        n_before = len(self.log.events)
        tick = self.now // v.tick_s * v.tick_s
        cycles_done = sorted(e["payload"]["cycle"] for e in self._of("cycle_completed"))
        if not cycles_done:
            return VeilleReport("inactive", tick)  # aucun cycle encore : le cycle ouvre le journal, pas la veille
        veilles = {e["payload"]["tick"]: e["payload"] for e in self._of("veille")}
        if tick in veilles:
            return VeilleReport("already_done", tick)

        try:
            instruments = {i.symbol: i for i in load_instruments(cfg, self.clients.kraken)}
            quotes = {s: self.clients.kraken.ticker(s, i.kraken_pair) for s, i in instruments.items()}
            bad = [s for s, q in quotes.items() if not _quote_valide(q)]
            if bad:
                raise DataError(f"quote invalide : {', '.join(bad)}")
        except Exception as exc:  # noqa: BLE001 - lecture des quotes : rien n'est écrit, on compte les échecs
            msg = f"{type(exc).__name__}: {str(exc)[:200]}"
            if self._echecs(+1) >= ECHECS_AVANT_ALERTE:
                recent = [
                    e for e in self._of("alert")
                    if e["payload"]["code"] == "veille_data" and self.now - e["ts"] < ALERTE_DATA_PERIODE_S
                ]  # fmt: skip
                if not recent:
                    self._alert("action", "veille_data", f"veille : quotes Kraken indisponibles ({msg})")
            return VeilleReport("failed", tick, error=msg, alerts=self.alerts)
        self._echecs(None)
        qd = {s: (q.bid, q.ask) for s, q in quotes.items()}

        # 1. stops en direct
        executor = SimExecutor(
            self.journal, instruments, cfg.taker_fee_bp, cfg.slippage_bp, cfg.venue_mode, self.fault_injector
        )
        executor.process_live_stops(quotes, tick)
        self.log.refresh()
        suffix = f":veille:{tick}"
        stop_fills = [e["payload"] for e in self._of("fill") if e["payload"]["order_id"].endswith(suffix)]
        rep = VeilleReport("done", tick, stops=[f["order_id"] for f in stop_fills], alerts=self.alerts)

        # 2. réveil interrompu : reprise ou abandon
        llm = {m.portfolio for m in cfg.models}
        closed = {e["payload"]["reveil"] for e in self._of("reveil_completed", "reveil_abandonne")}
        pending = sorted({e["payload"]["reveil"]: e["payload"] for e in self._of("reveil_started")}.items())
        pending = [(r, pl) for r, pl in pending if r not in closed]
        resume: tuple[int, dict[str, Any]] | None = None
        for i, (r, pl) in enumerate(pending):
            if i == len(pending) - 1 and tick - r <= REVEIL_ABANDON_S:
                resume = (r, pl["declencheur"])
            else:
                self.log.add("reveil_abandonne", {"reveil": r}, self.now)
                self._alert("action", "reveil_abandonne", f"réveil {r} abandonné (non terminé après 30 min)")
                rep.reveil = "abandonne"

        # 3. déclencheurs et garde-fous (pas de nouveau réveil pendant une reprise)
        launch: dict[str, Any] | None = None
        if resume is None:
            trigger = None
            ref = veilles.get(tick - v.fenetre_mouvement_s)
            if ref is not None:
                trigger = mouvement(qd, {s: tuple(b) for s, b in ref["quotes"].items()}, v.seuil_mouvement_bp, v.fenetre_mouvement_s)
            if trigger is None:
                for f in stop_fills:
                    if f["portfolio"] in llm:
                        trigger = {"type": "stop", "portefeuille": f["portfolio"], "symbole": f["symbol"]}
                        break
            rep.declencheur = trigger
            if trigger is not None:
                rep.refus = self._garde_fous(tick)
                if rep.refus is None:
                    launch = trigger

        # 4. événement veille, après les stops
        states = replay(self.log.events)
        marks = {s: (b + a) // 2 for s, (b, a) in qd.items()}
        bids = {s: b for s, (b, _a) in qd.items()}
        self.log.add(
            "veille",
            {
                "tick": tick,
                "quotes": {s: [b, a] for s, (b, a) in sorted(qd.items())},
                "equity": {p: equity_ueur(st, marks, bids) for p, st in sorted(states.items())},
                "stops": rep.stops,
                "reveil": launch,
            },
            tick,
        )

        # 5. réveil
        todo = resume if resume is not None else (tick, launch) if launch is not None else None
        if todo is not None:
            r, trigger = todo
            try:
                rv = _ReveilRunner(
                    self.paths, self.clients, self.now, self.journal, self.notifier, Heartbeat(self.paths.secrets, self.notifier),
                    self.deciders, self.fault_injector, self.on_portfolio_done,
                    cfg=cfg, policy=policy, instruments=instruments, reveil=r, declencheur=trigger, quotes=quotes,
                )  # fmt: skip
                try:
                    resumed = rv.run_reveil()
                finally:
                    self.alerts.extend(rv.alerts)
                rep.reveil = "resumed" if resumed else "completed"
            except (CycleAbort, DataError) as exc:
                level, code, msg = (
                    (exc.level, exc.code, exc.message) if isinstance(exc, CycleAbort) else ("action", "data_error", str(exc))
                )
                self.notifier.alert(level, code, msg, self.now)
                self.alerts.append((level, code))
                rep.status, rep.error = "reveil_failed", msg
            except Exception as exc:
                log.exception("réveil interrompu par une exception non prévue")
                msg = f"{type(exc).__name__}: {str(exc)[:300]}"
                self.notifier.alert("panique", "reveil_exception", f"réveil {r} interrompu : {msg}", self.now)
                self.alerts.append(("panique", "reveil_exception"))
                rep.status, rep.error = "reveil_failed", msg
        self.log.refresh()
        rep.n_events = len(self.log.events) - n_before
        return rep

    def _garde_fous(self, tick: int) -> str | None:
        """Code du premier garde-fou qui refuse un réveil à ce tick, ou None."""
        cfg, v = self.cfg, self.cfg.veille
        done = [e["payload"]["cycle"] for e in self._of("cycle_completed")]
        incomplets = [e for e in self._of("cycle_started") if e["payload"]["cycle"] > max(done, default=-1)]
        if incomplets or tick % cfg.interval_s == 0:
            return "cycle"  # cycle en cours ou incomplet ; ou tick qui se confondrait avec l'identifiant d'un cycle
        rondes = [e["ts"] for e in self._of("cycle_completed", "reveil_completed", "reveil_abandonne")]
        if rondes and tick - max(rondes) < v.cooldown_s:
            return "cooldown"
        today = [e for e in self._of("reveil_started") if e["payload"]["reveil"] // DAY_S == tick // DAY_S]
        if len(today) >= v.max_reveils_jour:
            return "plafond_jour"
        if prochain_rendez_vous(tick, cfg.interval_s, cfg.cycle_delay_s) - tick < v.garde_avant_cycle_s:
            return "avant_cycle"
        return None


# ---------------------------------------------------------------------------------------- point d'entrée


def run_veille(
    paths: Paths,
    clients: Clients,
    now_ts: int,
    *,
    deciders: dict[str, Any] | None = None,
    fault_injector: Any = None,
    on_portfolio_done: Any = None,
    lock_wait_s: float = 0.0,
) -> VeilleReport:
    """Un tick de veille (voir le module). Ne lève jamais : un échec renvoie un rapport non ok.

    `lock_wait_s` = 0 : si un cycle ou un réveil tourne, le tick s'arrête sans rien écrire (statut `busy`, ok).
    """
    journal = Journal(paths.journal)
    notifier = Notifier(journal, paths.secrets, clients.http)
    try:
        with cycle_lock(paths, lock_wait_s):
            return _Veille(paths, clients, now_ts, journal, notifier, deciders, fault_injector, on_portfolio_done).run()
    except CycleBusy:
        return VeilleReport("busy")
    except JournalBroken as exc:
        return VeilleReport("refused", error=str(exc))
    except Exception as exc:
        log.exception("veille interrompue par une exception non prévue")
        return VeilleReport("failed", error=f"{type(exc).__name__}: {str(exc)[:300]}")
