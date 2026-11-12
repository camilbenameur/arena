"""Veille continue et réveils sur événement (docs/VEILLE.md).

`run_veille(paths, clients, now_ts, deciders=None)` est lancé toutes les 5 min par `arene-veille.timer`, sans LLM :
1. verrou du cycle SANS attente (cycle ou réveil en cours : sortie sans rien écrire) ; journal cassé : rien écrit ;
2. tick = `now_ts // tick_s * tick_s` ; un événement `veille` déjà journalisé pour ce tick : sortie sans rien écrire ;
3. quotes Kraken, contrôlés symbole par symbole (invalide, spread, saut) ; un symbole invalide est exclu du tick ;
4. stops en direct, confirmés sur deux ticks, au bid avec glissement et frais, idempotents par `order_id` ;
5. déclencheur de mouvement (confirmé sur deux ticks) et garde-fous ; si un réveil part, `reveil_started` est écrit
   AVANT l'événement `veille` et avant tout appel réseau du réveil ;
6. événement `veille` (horodaté au tick), puis le réveil : une ronde de décision (LLM et aléatoire) rejouée par
   `_Runner` (sous-classe `_ReveilRunner`), sous le même verrou. Un réveil interrompu est repris par un tick suivant
   dans les 30 min (si aucun cycle n'a été terminé depuis), sinon réparé puis abandonné (`reveil_abandonne`).

Le réveil n'écrit jamais d'événement `equity` ; son identifiant (`reveil` = tick) remplit le champ `cycle` des
événements de décision, et ses quotes sont journalisés sous `quote_reveil`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
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
from arene.journal import Journal, intent_from_payload, verify
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
SPREAD_FENETRE = 20  # quotes valides pris pour la médiane des spreads
SPREAD_MIN_HISTORIQUE = 5
SPREAD_MULTIPLE = 5
SAUT_MAX_PCT = 15  # un milieu qui s'écarte de 15 % ou plus du dernier quote valide est écarté
SAUT_HORIZON_S = 1800
CONFIRMATION_S = 600  # le tick précédent (stops, mouvement) doit dater de 10 min au plus
REFERENCE_TOLERANCE_S = 900  # référence du mouvement : quote valide à tick - fenêtre ou avant, de 15 min au plus
ALERTE_JOURNAL_CASSE_S = 3600


# ---------------------------------------------------------------------------------------- rapport


@dataclass
class VeilleReport:
    status: str  # done | already_done | inactive | busy | refused | failed | reveil_failed
    tick: int | None = None
    n_events: int = 0  # événements ajoutés au journal par ce lancement
    stops: list[str] = field(default_factory=list)  # order_id des stops de ce tick
    rejets: dict[str, str] = field(default_factory=dict)  # symbole -> motif du quote écarté
    declencheur: dict[str, Any] | None = None  # déclencheur évalué (même s'il a été refusé)
    refus: str | None = None  # garde-fou qui a refusé le réveil
    reveil: str | None = None  # None | completed | resumed | abandonne
    alerts: list[tuple[str, str]] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("done", "already_done", "inactive", "busy")


# ---------------------------------------------------------------------------------------- fonctions pures

Hist = dict[str, list[tuple[int, int, int]]]  # symbole -> [(tick, bid, ask)] des quotes valides, croissant


def prochain_rendez_vous(ts: int, interval_s: int, cycle_delay_s: int) -> int:
    """Premier instant d'exécution d'un cycle (HH:05 UTC) strictement après `ts`."""
    return (ts - cycle_delay_s) // interval_s * interval_s + interval_s + cycle_delay_s


def _mid(bid: int, ask: int) -> int:
    return (bid + ask) // 2


def quote_valide(bid: Any, ask: Any) -> bool:
    return all(isinstance(x, int) and not isinstance(x, bool) for x in (bid, ask)) and 0 < bid <= ask


def classer_quote(bid: Any, ask: Any, hist: list[tuple[int, int, int]], tick: int) -> str | None:
    """Motif de rejet d'un quote (`invalide`, `spread`, `saut`), ou None s'il est valide.

    `hist` : quotes valides déjà journalisés dans les événements `veille` pour ce symbole.
    """
    if not quote_valide(bid, ask):
        return "invalide"
    spreads = sorted(a - b for _, b, a in hist[-SPREAD_FENETRE:])
    if len(spreads) >= SPREAD_MIN_HISTORIQUE and ask - bid > SPREAD_MULTIPLE * spreads[len(spreads) // 2]:
        return "spread"
    if hist and tick - hist[-1][0] < SAUT_HORIZON_S:
        prev = _mid(hist[-1][1], hist[-1][2])
        if prev > 0 and abs(_mid(bid, ask) - prev) * 100 >= SAUT_MAX_PCT * prev:
            return "saut"
    return None


def reference_a(hist: list[tuple[int, int, int]], target: int) -> tuple[int, int, int] | None:
    """Quote valide le plus proche de `target` ou avant, à moins de 15 min."""
    best = None
    for h in hist:
        if h[0] <= target and target - h[0] <= REFERENCE_TOLERANCE_S:
            best = h
    return best


def precedent(hist: list[tuple[int, int, int]], tick: int) -> tuple[int, int, int] | None:
    """Quote valide du tick précédent de ce symbole, à moins de 10 min."""
    prev = [h for h in hist if h[0] < tick]
    return prev[-1] if prev and tick - prev[-1][0] <= CONFIRMATION_S else None


def _depasse(mid: int, ref_mid: int, seuil_bp: int) -> bool:
    return ref_mid > 0 and abs(mid - ref_mid) * BP >= seuil_bp * ref_mid


def mouvement(
    quotes: dict[str, tuple[int, int]], hist: Hist, tick: int, seuil_bp: int, fenetre_s: int
) -> dict[str, Any] | None:
    """Instrument dont le milieu a bougé d'au moins `seuil_bp` sur la fenêtre, au tick courant ET au tick précédent
    (même sens, chacun contre sa propre référence). Le plus grand |variation| l'emporte. Mesuré au milieu du quote."""
    best: tuple[int, int, str, int] | None = None  # (|d|·BP/ref arrondi bas en 1e-8, d, symbole, ref)
    for sym in sorted(quotes):
        h = hist.get(sym, [])
        ref = reference_a(h, tick - fenetre_s)
        prev = precedent(h, tick)
        prev_ref = reference_a(h, prev[0] - fenetre_s) if prev else None
        if ref is None or prev is None or prev_ref is None:
            continue
        mid, rmid = _mid(*quotes[sym]), _mid(ref[1], ref[2])
        pmid, prmid = _mid(prev[1], prev[2]), _mid(prev_ref[1], prev_ref[2])
        d, pd = mid - rmid, pmid - prmid
        if not (_depasse(mid, rmid, seuil_bp) and _depasse(pmid, prmid, seuil_bp)) or (d > 0) != (pd > 0):
            continue
        score = abs(d) * 10**8 // rmid
        if best is None or score > best[0]:
            best = (score, d, sym, rmid)
    if best is None:
        return None
    _, d, sym, rmid = best
    bp = (abs(d) * BP * 2 + rmid) // (2 * rmid)
    return {"type": "mouvement", "symbole": sym, "variation_bp": bp if d > 0 else -bp, "fenetre_s": fenetre_s}


def _alerte_reveil(
    elog: EventLog, notifier: Notifier, now: int, reveil: int, level: str, code: str, message: str
) -> bool:
    """Alerte tracée « [réveil N] » : une seule par réveil et par code (journal relu)."""
    tag = f"[réveil {reveil}] "
    elog.refresh()
    if any(
        e["type"] == "alert" and e["payload"]["code"] == code and e["payload"]["message"].startswith(tag)
        for e in elog.events
    ):
        return False
    notifier.alert(level, code, tag + message, now)
    elog.refresh()
    return True


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
        self.prefetched_quotes = quotes  # quotes valides du tick, journalisés en `quote_reveil` avant la décision
        self.quote_symbols = set(quotes)
        self.quote_type = "quote_reveil"
        self.fetch_binance = False  # E0065 ne tourne pas au réveil

    def alert(self, level: str, code: str, message: str) -> None:
        if _alerte_reveil(self.log, self.notifier, self.now, self.t, level, code, message):
            self.alerts.append((level, code))

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

    def _view(self) -> None:
        """Comme au cycle, avec deux écarts : un symbole sans quote valide est valorisé à son dernier quote valide
        (jamais négociable), et PRICE_SANITY compare au milieu du quote du tick précédent de la veille."""
        super()._view()
        veilles = sorted(
            (e["payload"] for e in self._events_of("veille") if e["payload"]["tick"] < self.t),
            key=lambda pl: pl["tick"],
        )
        last_closes = dict(self.market.last_closes)
        for sym in self.symbols:
            for pl in reversed(veilles):
                if sym in pl["quotes"]:
                    last_closes[sym] = _mid(*pl["quotes"][sym])
                    break
        marks, bids = dict(self.marks), dict(self.bids)
        for sym in self.symbols:
            if sym in self.quotes:
                continue
            q = self._dernier_quote_valide(sym)
            if q is not None:
                marks[sym], bids[sym] = _mid(q[0], q[1]), q[0]
        self.marks, self.bids = marks, bids
        self.market = replace(self.market, last_closes=last_closes, marks=marks)

    def _dernier_quote_valide(self, sym: str) -> tuple[int, int] | None:
        for e in reversed(self._events_of("veille")):
            if sym in e["payload"]["quotes"]:
                b, a = e["payload"]["quotes"][sym]
                return b, a
        for e in reversed(self._events_of("quote")):
            if e["payload"]["symbol"] == sym:
                return e["payload"]["bid"], e["payload"]["ask"]
        return None

    def run_reveil(self, resume: bool) -> None:
        """Exécute ou reprend le réveil `self.t` (`reveil_started` est déjà journalisé)."""
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
        self._market(True, started[-1]["seq"])
        if resume:
            self.alert("info", "reveil_resumed", "réveil interrompu repris")
        self._journal_market()
        self._view()
        self._resolve_unknowns()
        self._freeze_halt()
        self._kill_and_dormancy()
        self._decide_and_execute()
        self.wn("reveil_completed", {"reveil": t})


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

    def _echecs(self, new: int | None = None) -> int:
        """Compteur d'échecs consécutifs de lecture des quotes (`var/veille_echecs`, hors journal). Renvoie la valeur
        lue ; `new` l'écrit (0 supprime le fichier)."""
        p = self.paths.var / "veille_echecs"
        try:
            n = int(p.read_text().strip() or 0)
        except (OSError, ValueError):
            n = 0
        try:
            if new is not None and new != n:
                if new == 0:
                    p.unlink(missing_ok=True)
                else:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(str(new))
        except OSError:
            pass
        return n

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
        if not self._of("cycle_completed"):
            return VeilleReport("inactive", tick)  # aucun cycle encore : le cycle ouvre le journal, pas la veille
        veilles = {e["payload"]["tick"]: e["payload"] for e in self._of("veille")}
        if tick in veilles:
            return VeilleReport("already_done", tick)
        hist: Hist = {}
        for t_, pl in sorted(veilles.items()):
            for sym, (b, a) in pl["quotes"].items():
                hist.setdefault(sym, []).append((t_, b, a))

        # 1. quotes, contrôlés symbole par symbole
        rejets: dict[str, str] = {}
        quotes: dict[str, Quote] = {}
        try:
            instruments = {i.symbol: i for i in load_instruments(cfg, self.clients.kraken)}
            for s, inst in instruments.items():
                try:
                    q = self.clients.kraken.ticker(s, inst.kraken_pair)
                    motif = classer_quote(q.bid, q.ask, hist.get(s, []), tick)
                except Exception as exc:  # noqa: BLE001 - un symbole illisible est écarté, pas tout le tick
                    motif = f"erreur : {type(exc).__name__}"
                if motif is None:
                    quotes[s] = q
                else:
                    rejets[s] = motif
            if not quotes:
                raise DataError("aucun quote valide : " + ", ".join(f"{s} {m}" for s, m in sorted(rejets.items())))
        except Exception as exc:  # noqa: BLE001 - rien n'est écrit ; une alerte au début de la panne
            msg = f"{type(exc).__name__}: {str(exc)[:200]}"
            n = self._echecs() + 1
            self._echecs(n)
            if n == ECHECS_AVANT_ALERTE:
                self._alert("action", "veille_data", f"veille : quotes Kraken inutilisables depuis {n} ticks ({msg})")
            return VeilleReport("failed", tick, error=msg, alerts=self.alerts)
        if self._echecs(0) >= ECHECS_AVANT_ALERTE:
            self._alert("info", "veille_data", "veille : quotes Kraken rétablis")
        qd = {s: (q.bid, q.ask) for s, q in quotes.items()}

        # 2. stops en direct, confirmés par le tick valide précédent (à moins de 10 min)
        prev_bids = {s: p[1] for s in quotes if (p := precedent(hist.get(s, []), tick)) is not None}
        executor = SimExecutor(
            self.journal, instruments, cfg.taker_fee_bp, cfg.slippage_bp, cfg.venue_mode, self.fault_injector
        )
        executor.process_live_stops(quotes, tick, prev_bids)
        self.log.refresh()
        suffix = f":veille:{tick}"
        stop_ids = [e["payload"]["order_id"] for e in self._of("fill") if e["payload"]["order_id"].endswith(suffix)]
        rep = VeilleReport("done", tick, stops=stop_ids, rejets=rejets, alerts=self.alerts)

        # 3. réveil interrompu : reprise, ou réparation puis abandon
        closed = {e["payload"]["reveil"] for e in self._of("reveil_completed", "reveil_abandonne")}
        started = {e["payload"]["reveil"]: e for e in self._of("reveil_started")}
        pending = [(r, e) for r, e in sorted(started.items()) if r not in closed]
        last_cycle_seq = max((e["seq"] for e in self._of("cycle_completed")), default=-1)
        resume: tuple[int, dict[str, Any]] | None = None
        for i, (r, e) in enumerate(pending):
            if i == len(pending) - 1 and tick - r <= REVEIL_ABANDON_S and last_cycle_seq < e["seq"]:
                resume = (r, e["payload"]["declencheur"])
                continue
            self._abandonner(executor, r)
            rep.reveil = "abandonne"

        # 4. déclencheur et garde-fous (pas de nouveau réveil pendant une reprise)
        launch: dict[str, Any] | None = None
        if resume is None:
            trigger = mouvement(qd, hist, tick, v.seuil_mouvement_bp, v.fenetre_mouvement_s)
            rep.declencheur = trigger
            if trigger is not None:
                rep.refus = self._garde_fous(tick)
                if rep.refus is None:
                    launch = trigger
                    # Le réveil est consigné d'abord : avant l'événement `veille` et avant tout appel réseau du réveil.
                    self.log.add("reveil_started", {"reveil": tick, "declencheur": trigger}, self.now)

        # 5. événement veille, après les stops
        states = replay(self.log.events)
        marks = {s: _mid(b, a) for s, (b, a) in qd.items()}
        bids = {s: b for s, (b, _a) in qd.items()}
        for s in instruments:  # symbole écarté : valorisé à son dernier quote valide
            if s not in qd:
                last = hist[s][-1][1:] if hist.get(s) else self._dernier_quote_cycle(s)
                if last is not None:
                    marks[s], bids[s] = _mid(*last), last[0]
        self.log.add(
            "veille",
            {
                "tick": tick,
                "quotes": {s: [b, a] for s, (b, a) in sorted(qd.items())},
                "rejets": dict(sorted(rejets.items())),
                "equity": {p: equity_ueur(st, marks, bids) for p, st in sorted(states.items())},
                "stops": rep.stops,
                "reveil": launch,
                "refus": rep.refus,
            },
            tick,
        )

        # 6. réveil
        todo = resume if resume is not None else (tick, launch) if launch is not None else None
        if todo is not None:
            r, trigger = todo
            rv = None
            try:
                rv = _ReveilRunner(
                    self.paths, self.clients, self.now, self.journal, self.notifier,
                    Heartbeat(self.paths.secrets, self.notifier),
                    self.deciders, self.fault_injector, self.on_portfolio_done,
                    cfg=cfg, policy=policy, instruments=instruments, reveil=r, declencheur=trigger, quotes=quotes,
                )  # fmt: skip
                rv.run_reveil(resume is not None)
                rep.reveil = "resumed" if resume is not None else "completed"
            except (CycleAbort, DataError) as exc:
                level, code, msg = (
                    (exc.level, exc.code, exc.message) if isinstance(exc, CycleAbort) else ("action", "data_error", str(exc))
                )
                if _alerte_reveil(self.log, self.notifier, self.now, r, level, code, msg):
                    self.alerts.append((level, code))
                rep.status, rep.error = "reveil_failed", msg
            except Exception as exc:
                log.exception("réveil interrompu par une exception non prévue")
                msg = f"{type(exc).__name__}: {str(exc)[:300]}"
                if _alerte_reveil(self.log, self.notifier, self.now, r, "panique", "reveil_exception", msg):
                    self.alerts.append(("panique", "reveil_exception"))
                rep.status, rep.error = "reveil_failed", msg
            finally:
                if rv is not None:
                    self.alerts.extend(a for a in rv.alerts if a not in self.alerts)
        self.log.refresh()
        rep.n_events = len(self.log.events) - n_before
        return rep

    def _dernier_quote_cycle(self, sym: str) -> tuple[int, int] | None:
        for e in reversed(self._of("quote")):
            if e["payload"]["symbol"] == sym:
                return e["payload"]["bid"], e["payload"]["ask"]
        return None

    def _abandonner(self, executor: SimExecutor, r: int) -> None:
        """Répare la ronde interrompue (fill sans stop_set, ordre SUBMITTING/ACKED), puis journalise l'abandon."""
        for e in self._of("intent"):
            if e["payload"]["cycle"] == r:
                executor.settle_interrupted(intent_from_payload(e["payload"]), self.now)
        self.log.refresh()
        self.log.add("reveil_abandonne", {"reveil": r}, self.now)
        _alerte_reveil(
            self.log, self.notifier, self.now, r, "action", "reveil_abandonne", "réveil abandonné (non terminé)"
        )
        self.alerts.append(("action", "reveil_abandonne"))

    def _garde_fous(self, tick: int) -> str | None:
        """Motif du premier garde-fou qui refuse un réveil à ce tick, ou None."""
        cfg, v = self.cfg, self.cfg.veille
        done = [e["payload"]["cycle"] for e in self._of("cycle_completed")]
        if any(e["payload"]["cycle"] > max(done, default=-1) for e in self._of("cycle_started")):
            return "cycle_incomplet"
        if tick % cfg.interval_s == 0:
            return "cycle"  # l'identifiant du réveil se confondrait avec celui d'un cycle
        rondes = [e["ts"] for e in self._of("cycle_completed", "reveil_started", "reveil_completed", "reveil_abandonne")]
        if rondes and tick - max(rondes) < v.cooldown_s:
            return "delai"
        today = [e for e in self._of("reveil_started") if e["payload"]["reveil"] // DAY_S == tick // DAY_S]
        if len(today) >= v.max_reveils_jour:
            return "plafond"
        if prochain_rendez_vous(tick, cfg.interval_s, cfg.cycle_delay_s) - tick < v.garde_avant_cycle_s:
            return "avant_cycle"
        return None


# ---------------------------------------------------------------------------------------- point d'entrée


def _alerte_journal_casse(paths: Paths, notifier: Notifier, now: int, error: str) -> None:
    """Une alerte `panique` par heure au plus (état dans `var/veille_journal_casse`, jamais dans le journal)."""
    p = paths.var / "veille_journal_casse"
    try:
        last = int(p.read_text().strip())
    except (OSError, ValueError):
        last = None
    if last is not None and 0 <= now - last < ALERTE_JOURNAL_CASSE_S:
        return
    notifier.journal_enabled = False  # on n'écrit jamais dans un journal cassé
    notifier.send("panique", "journal_casse", f"journal cassé, veille arrêtée : {error}")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(now))
    except OSError:
        pass


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
        _alerte_journal_casse(paths, notifier, now_ts, str(exc))
        return VeilleReport("refused", error=str(exc))
    except Exception as exc:
        log.exception("veille interrompue par une exception non prévue")
        return VeilleReport("failed", error=f"{type(exc).__name__}: {str(exc)[:300]}")
