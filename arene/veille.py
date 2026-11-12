"""Veille continue et réveils sur événement (docs/VEILLE.md).

`run_veille(paths, clients, now_ts, deciders=None)` est lancé toutes les 5 min par `arene-veille.timer`, sans LLM :
1. verrou du cycle SANS attente (cycle ou réveil en cours : sortie sans rien écrire) ; journal cassé : rien écrit ;
2. tick = `now_ts // tick_s * tick_s` ; un événement `veille` déjà journalisé pour ce tick : sortie sans rien écrire ;
3. quotes Kraken, contrôlés symbole par symbole (invalide, spread, saut, confirmation de rupture) ; un symbole rejeté est exclu du tick ;
4. stops en direct jugés sur les bougies Kraken 1 min (2 bougies sous le stop, prix de la dernière clôture avec
   glissement et frais, jamais au-dessus du stop), idempotents par `order_id` ;
5. déclencheur de mouvement (bougies 1 min, aux deux derniers ticks) et garde-fous ; si un réveil part, `reveil_started` est écrit
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
from typing import Any, NamedTuple

from arene import saison
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
from arene.data import DataError, RateLimitedError
from arene.data.kraken import KrakenError
from arene.data.store import BarStore
from arene.deciders.llm import prompt_sha256
from arene.journal import Journal, intent_from_payload, verify
from arene.ledger import equity_ueur, replay
from arene.ops.heartbeat import Heartbeat
from arene.ops.notify import Notifier
from arene.paths import Paths
from arene.risk.policy import Policy, PolicyError, load_policy
from arene.sim.executor import SimExecutor
from arene.types import Bar, Instrument, Quote

log = logging.getLogger("arene.veille")

BP = 10_000
REVEIL_ABANDON_S = 1800  # un réveil interrompu est repris pendant 30 min, puis abandonné
ECHECS_AVANT_ALERTE = 3
SPREAD_FENETRE = 20  # quotes valides pris pour la médiane des spreads
SPREAD_MIN_HISTORIQUE = 5
SPREAD_MULTIPLE = 5
SAUT_MAX_PCT = 15  # un milieu qui s'écarte de 15 % ou plus du dernier quote valide est écarté
SAUT_HORIZON_S = 1800
COHERENCE_PCT = 2  # deux quotes rejetés dont les milieux sont à moins de 2 % l'un de l'autre se confirment
REJETS_AVANT_ALERTE = 3
CHAINE_MAX = 6  # ticks consécutifs acceptés par confirmation de rupture (30 min) ; au-delà, rejet
MINUTE_S = 60
OHLC_DEPUIS_S = 81 * 60  # bougies 1 min lues par tick : 1 h + 15 min de tolérance + le tick précédent (5 min)
REF_TOLERANCE_S = 900  # bougie de référence du mouvement : la dernière bougie tradée à tick - fenêtre ou avant, à 15 min près
OHLC_ECHECS_MIN = 3  # symboles en échec OHLC, sur 3 ticks consécutifs : alerte veille_ohlc
PAUSE_OHLC_DEFAUT_S = 300
BOUGIE_PERIMEE_S = 900  # dernière bougie close plus vieille que 15 min : pas de mesure
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
    confirmes: list[str] = field(default_factory=list)  # symboles acceptés par confirmation de rupture
    declencheur: dict[str, Any] | None = None  # déclencheur évalué (même s'il a été refusé)
    refus: str | None = None  # garde-fou qui a refusé le réveil
    reveil: str | None = None  # None | completed | resumed | abandonne
    alerts: list[tuple[str, str]] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("done", "already_done", "inactive", "busy")


# ---------------------------------------------------------------------------------------- fonctions pures

class H(NamedTuple):
    """Un symbole à un tick passé, relu dans les événements `veille`."""

    tick: int
    bid: int | None  # quote brut (None : quote invalide, non journalisé)
    ask: int | None
    acc: bool  # accepté (dans `quotes`)
    flag: str | None  # motif du rejet (spread, saut, invalide, erreur...), "confirme" si accepté par rupture, sinon None


Hist = dict[str, list[H]]


def prochain_rendez_vous(ts: int, interval_s: int, cycle_delay_s: int) -> int:
    """Premier instant d'exécution d'un cycle (HH:05 UTC) strictement après `ts`."""
    return (ts - cycle_delay_s) // interval_s * interval_s + interval_s + cycle_delay_s


def _mid(bid: int, ask: int) -> int:
    return (bid + ask) // 2


def quote_valide(bid: Any, ask: Any) -> bool:
    return all(isinstance(x, int) and not isinstance(x, bool) for x in (bid, ask)) and 0 < bid <= ask


def construire_hist(veilles: list[dict[str, Any]]) -> Hist:
    """Historique par symbole depuis les événements `veille` (croissant). Les événements sans `quotes_bruts`
    (ancien format) ne donnent que leurs quotes acceptés."""
    hist: Hist = {}
    for pl in sorted(veilles, key=lambda p: p["tick"]):
        bruts, acc = pl.get("quotes_bruts") or pl["quotes"], pl["quotes"]
        rejets, confirmes = pl.get("rejets", {}), pl.get("confirmes", [])
        for sym in sorted(set(bruts) | set(rejets) | set(acc)):
            b, a = bruts.get(sym, (None, None)) if sym in bruts else acc.get(sym, (None, None))
            flag = "confirme" if sym in confirmes else rejets.get(sym)
            hist.setdefault(sym, []).append(H(pl["tick"], b, a, sym in acc, flag))
    return hist


def classer_quote(
    bid: Any, ask: Any, hist: list[H], tick: int, close: int | None = None
) -> tuple[str | None, bool]:
    """(motif de rejet, accepté par confirmation de rupture).

    - `invalide` : toujours rejeté.
    - `spread` : spread > 5 x la médiane des 20 derniers spreads BRUTS du symbole (au moins 5).
    - `saut` : milieu à 15 % ou plus du dernier quote accepté de moins de 30 min, sinon de la dernière clôture 4 h.
    - Un quote rejeté pour spread ou saut est ACCEPTÉ si le tick précédent (à moins de 10 min) a lui aussi été
      rejeté pour spread ou saut (ou accepté par confirmation) et si les deux milieux bruts sont à moins de 2 %.
    """
    if not quote_valide(bid, ask):
        return "invalide", False
    flag = None
    spreads = sorted(e.ask - e.bid for e in [e for e in hist if e.bid is not None][-SPREAD_FENETRE:])
    if len(spreads) >= SPREAD_MIN_HISTORIQUE and ask - bid > SPREAD_MULTIPLE * spreads[len(spreads) // 2]:
        flag = "spread"
    acc = [e for e in hist if e.acc]
    ref = _mid(acc[-1].bid, acc[-1].ask) if acc and tick - acc[-1].tick < SAUT_HORIZON_S else close
    if flag is None and ref and ref > 0 and abs(_mid(bid, ask) - ref) * 100 >= SAUT_MAX_PCT * ref:
        flag = "saut"
    if flag is None:
        return None, False
    prev = precedent(hist, tick)
    run = 0  # ticks de rupture consécutifs déjà vus (rejetés ou acceptés par confirmation)
    for e in reversed(hist):
        if e.flag not in ("spread", "saut", "confirme"):
            break
        run += 1
    if prev is not None and run <= CHAINE_MAX and prev.flag in ("spread", "saut", "confirme") and (prev.flag == "confirme" or not prev.acc):
        pm = _mid(prev.bid, prev.ask)
        if pm > 0 and abs(_mid(bid, ask) - pm) * 100 < COHERENCE_PCT * pm:
            return None, True
    return flag, False


def precedent(hist: list[H], tick: int) -> H | None:
    """Quote (brut, accepté ou non) du tick précédent de ce symbole, à moins de 10 min."""
    prev = [h for h in hist if h.tick < tick and h.bid is not None]
    return prev[-1] if prev and tick - prev[-1].tick <= CONFIRMATION_S else None


def _depasse(mid: int, ref_mid: int, seuil_bp: int) -> bool:
    return ref_mid > 0 and abs(mid - ref_mid) * BP >= seuil_bp * ref_mid


def bougies_closes(bars: list[Bar], tick: int) -> list[Bar]:
    """Bougies 1 min closes au tick (ts + 60 <= tick), triées."""
    return sorted((b for b in bars if b.ts + MINUTE_S <= tick), key=lambda b: b.ts)


def variation_bougies(bars: list[Bar], tick: int, fenetre_s: int) -> tuple[int, int] | None:
    """(clôture de la dernière bougie close tradée, clôture de la dernière bougie close tradée à tick - fenêtre ou
    avant, à 15 min près), ou None. Seules les bougies à volume > 0 comptent (une bougie de remplissage répète un
    cours) ; sans transaction récente (dernière bougie tradée de plus de 15 min), pas de mesure."""
    closed = [b for b in bougies_closes(bars, tick) if b.volume > 0]
    if not closed or tick - (closed[-1].ts + MINUTE_S) > BOUGIE_PERIMEE_S:
        return None
    target = tick - fenetre_s
    refs = [b for b in closed if b.ts <= target and target - b.ts <= REF_TOLERANCE_S]
    if not refs:
        return None
    return closed[-1].close, refs[-1].close


def mouvement(
    minute_bars: dict[str, list[Bar]], tick: int, seuil_bp: int, fenetre_s: int, pas_s: int
) -> tuple[dict[str, Any] | None, dict[str, int]]:
    """(déclencheur, variations_bp par symbole) mesurés sur les TRANSACTIONS (bougies 1 min), jamais sur le ticker.

    Variation = clôture de la dernière bougie close tradée / clôture de la dernière bougie tradée à tick - fenêtre ou
    avant (15 min au plus), moins 1.
    Le seuil doit être dépassé au tick courant ET au tick précédent (tick - pas_s, rejugé avec ses propres bougies),
    dans le même sens. Le plus grand |variation| l'emporte."""
    best: tuple[int, int, str, int] | None = None  # (|d|·1e8/ref, d, symbole, ref)
    variations: dict[str, int] = {}
    for sym in sorted(minute_bars):
        cur = variation_bougies(minute_bars[sym], tick, fenetre_s)
        if cur is None:
            continue
        d, rref = cur[0] - cur[1], cur[1]
        if rref <= 0:
            continue
        bp = (abs(d) * BP * 2 + rref) // (2 * rref)
        variations[sym] = bp if d > 0 else -bp
        prev = variation_bougies(minute_bars[sym], tick - pas_s, fenetre_s)
        if prev is None or prev[1] <= 0:
            continue
        pd = prev[0] - prev[1]
        if not (_depasse(cur[0], rref, seuil_bp) and _depasse(prev[0], prev[1], seuil_bp)) or (d > 0) != (pd > 0):
            continue
        score = abs(d) * 10**8 // rref
        if best is None or score > best[0]:
            best = (score, d, sym, rref)
    if best is None:
        return None, variations
    _, d, sym, rref = best
    bp = (abs(d) * BP * 2 + rref) // (2 * rref)
    return {"type": "mouvement", "symbole": sym, "variation_bp": bp if d > 0 else -bp, "fenetre_s": fenetre_s}, variations


def pause_ohlc(exc: BaseException) -> int | None:
    """Secondes de pause des appels OHLC si `exc` est une limite de débit (HTTP 429 avec Retry-After, ou
    EAPI:Rate limit), sinon None. Défaut : 300 s."""
    if isinstance(exc, RateLimitedError):
        return exc.retry_after or PAUSE_OHLC_DEFAUT_S
    if isinstance(exc, KrakenError) and any("Rate limit" in e for e in exc.errors):
        return PAUSE_OHLC_DEFAUT_S
    return None


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
        self.reuse_partial_quotes = True  # reprise : uniquement les `quote_reveil` déjà écrits, jamais réécrits

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
        """Comme au cycle, avec deux écarts : un symbole sans quote accepté est valorisé à son dernier quote accepté
        (jamais négociable), et PRICE_SANITY compare au dernier cours des TRANSACTIONS (clôture de la dernière bougie
        1 min close, lue dans l'événement `veille` du tick d'origine) : un ticker erroné bloque les entrées."""
        super()._view()
        last_closes = dict(self.market.last_closes)
        origine = next((e["payload"] for e in self._events_of("veille") if e["payload"]["tick"] == self.t), None)
        if origine is not None:
            last_closes.update({s: c for s, c in origine.get("clotures_1m", {}).items() if s in self.symbols})
        marks, bids = dict(self.marks), dict(self.bids)
        clot = (origine or {}).get("clotures_1m", {})
        # Gel, arrêt et mises à plat : chaque symbole vaut max(bid accepté, clôture 1 min) ; un seul flux erroné ne peut
        # ni geler ni arrêter un portefeuille.
        for sym, c in clot.items():
            if sym in bids and c > bids[sym]:
                bids[sym] = c
        self._flat_bids = {s: c for s, c in clot.items() if s in self.quotes}
        for sym in self.symbols:
            if sym in self.quotes:
                continue
            q = self._dernier_quote_valide(sym)
            if q is not None:
                marks[sym], bids[sym] = _mid(q[0], q[1]), q[0]
        self.marks, self.bids = marks, bids
        self.market = replace(self.market, last_closes=last_closes, marks=marks)

    def _flatten_quotes(self) -> dict[str, Quote]:
        out = dict(self.quotes)
        for s, c in getattr(self, "_flat_bids", {}).items():
            q = out[s]
            if c > q.bid:
                out[s] = Quote(q.symbol, q.ts, c, max(q.ask, c))
        return out

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
        origine = next((e["payload"] for e in self._events_of("veille") if e["payload"]["tick"] == t), None)
        if resume and origine is not None:  # la reprise repart des quotes acceptés du tick d'origine
            self.prefetched_quotes = {s: Quote(s, t, b, a) for s, (b, a) in origine["quotes"].items()}
            self.quote_symbols = set(self.prefetched_quotes)
        self._market(True, started[-1]["seq"])
        if resume:
            self.alert("info", "reveil_resumed", "réveil interrompu repris")
            for s, (b, a) in sorted((origine or {"quotes": {}})["quotes"].items()):
                if s not in self.quotes:  # quote_reveil manquant (crash pendant l'écriture) : complété, jamais ignoré
                    self.quotes[s] = Quote(s, t, b, a)
                    self.wn("quote_reveil", self.quotes[s])
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

    def _pause_ohlc(self, ecrire: int | None = None) -> int:
        """Instant (secondes) jusqu'auquel les appels OHLC sont suspendus (`var/veille_ohlc_pause`)."""
        p = self.paths.var / "veille_ohlc_pause"
        try:
            until = int(p.read_text().strip())
        except (OSError, ValueError):
            until = 0
        if ecrire is not None:
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(str(ecrire))
            except OSError:
                pass
        return until

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
        hist = construire_hist(list(veilles.values()))
        store = BarStore(paths.data, "kraken")
        # Saison gelée : calculée au début du tick. Gelé (hashes différents, sans dérogation) : aucun fill ni réveil.
        gel = saison.verifier_gel(
            self.log.events,
            {"config_sha256": cfg.sha256_hors_saison, "policy_sha256": policy.sha256, "prompt_sha256": prompt_sha256(),
             "code_sha256": saison.code_sha256(paths.repo)},
            tick, saison.lire_derogation(paths),
        )  # fmt: skip
        gele = gel.statut == "gele"

        # 1. quotes, contrôlés symbole par symbole
        rejets: dict[str, str] = {}
        confirmes: list[str] = []
        bruts: dict[str, tuple[int, int]] = {}
        quotes: dict[str, Quote] = {}
        try:
            instruments = {
                i.symbol: i
                for i in load_instruments(cfg, self.clients.kraken, cache=paths.var / "asset_pairs.json", now=self.now)
            }
            for s, inst in instruments.items():
                h = hist.get(s, [])
                try:
                    q = self.clients.kraken.ticker(s, inst.kraken_pair)
                    acc = [e for e in h if e.acc]
                    close = None
                    if not (acc and tick - acc[-1].tick < SAUT_HORIZON_S):  # historique périmé : clôture 4 h du store
                        bars = store.load(s, cfg.interval_s, tick)
                        close = bars[-1].close if bars else None
                    motif, confirme = classer_quote(q.bid, q.ask, h, tick, close)
                except Exception as exc:  # noqa: BLE001 - un symbole illisible est écarté, pas tout le tick
                    motif, confirme, q = f"erreur : {type(exc).__name__}", False, None
                if motif != "invalide" and q is not None and not str(motif).startswith("erreur"):
                    bruts[s] = (q.bid, q.ask)
                if motif is None:
                    quotes[s] = q
                    if confirme:
                        confirmes.append(s)
                else:
                    rejets[s] = motif
            if not bruts:
                raise DataError("aucun quote exploitable : " + ", ".join(f"{s} {m}" for s, m in sorted(rejets.items())))
        except Exception as exc:  # noqa: BLE001 - rien n'est écrit ; une alerte au début de la panne
            msg = f"{type(exc).__name__}: {str(exc)[:200]}"
            n = self._echecs() + 1
            self._echecs(n)
            if n == ECHECS_AVANT_ALERTE:
                self._alert("action", "veille_data", f"veille : quotes Kraken inutilisables depuis {n} ticks ({msg})")
            return VeilleReport("failed", tick, error=msg, alerts=self.alerts)
        qd = {s: (q.bid, q.ask) for s, q in quotes.items()}
        for s in instruments:  # épisodes de rejets consécutifs d'un même symbole
            n_prev = 0
            for e in reversed(hist.get(s, [])):
                if e.acc:
                    break
                n_prev += 1
            if s in rejets and n_prev + 1 == REJETS_AVANT_ALERTE:
                self._alert("action", "veille_symbole_ecarte", f"{s} : quotes écartés depuis {REJETS_AVANT_ALERTE} ticks ({rejets[s]})")
            elif s not in rejets and n_prev >= REJETS_AVANT_ALERTE:
                self._alert("info", "veille_symbole_ecarte", f"{s} : quotes de nouveau acceptés")

        # 2. transactions : bougies Kraken 1 min closes (stops et mouvement ne lisent jamais le ticker)
        minute_bars: dict[str, list[Bar]] = {}
        jusqua = self._pause_ohlc()
        limite = self.now < jusqua  # limite de débit en cours : aucun appel OHLC avant l'expiration
        for s, inst in instruments.items():
            if limite:
                rejets.setdefault(s, "ohlc")
                continue
            try:
                bars = bougies_closes(self.clients.kraken.ohlc(s, inst.kraken_pair, 60, tick - OHLC_DEPUIS_S), tick)
                if not bars:
                    raise DataError("aucune bougie 1 min")
                minute_bars[s] = bars
            except Exception as exc:  # noqa: BLE001 - ni stop ni déclencheur sur ce symbole à ce tick
                rejets.setdefault(s, "ohlc")
                pause = pause_ohlc(exc)
                if pause is not None:  # HTTP 429 / Rate limit : on suspend les appels OHLC
                    self._pause_ohlc(self.now + pause)
                    limite = True
        # Aucune bougie lisible : le tick compte dans var/veille_echecs ; sinon (quotes et bougies) retour à la normale.
        if minute_bars:
            if self._echecs(0) >= ECHECS_AVANT_ALERTE:
                self._alert("info", "veille_data", "veille : quotes et bougies Kraken rétablis")
        else:
            n = self._echecs() + 1
            self._echecs(n)
            if n == ECHECS_AVANT_ALERTE:
                self._alert("action", "veille_data", f"veille : aucune bougie 1 min lisible depuis {n} ticks")
        ko_now = sum(1 for m in rejets.values() if m == "ohlc") >= OHLC_ECHECS_MIN
        ko_prev = 0
        for pl_ in sorted((e["payload"] for e in self._of("veille")), key=lambda x: x["tick"], reverse=True):
            if sum(1 for m in pl_.get("rejets", {}).values() if m == "ohlc") < OHLC_ECHECS_MIN:
                break
            ko_prev += 1
        if ko_now and ko_prev + 1 == ECHECS_AVANT_ALERTE:
            self._alert("action", "veille_ohlc", f"veille : lecture des bougies 1 min en échec pour {sum(1 for m in rejets.values() if m == 'ohlc')} symboles depuis {ko_prev + 1} ticks")
        elif not ko_now and ko_prev >= ECHECS_AVANT_ALERTE:
            self._alert("info", "veille_ohlc", "veille : lecture des bougies 1 min rétablie")

        # 2 bis. stops en direct sur les transactions (aucun fill si la saison est gelée)
        executor = SimExecutor(
            self.journal, instruments, cfg.taker_fee_bp, cfg.slippage_bp, cfg.venue_mode, self.fault_injector
        )
        if not gele:
            executor.process_live_stops(minute_bars, tick, {s: b for s, (b, _a) in bruts.items()})
        self.log.refresh()
        suffix = f":veille:{tick}"
        stop_ids = [e["payload"]["order_id"] for e in self._of("fill") if e["payload"]["order_id"].endswith(suffix)]
        rep = VeilleReport("done", tick, stops=stop_ids, rejets=rejets, confirmes=confirmes, alerts=self.alerts)
        if gele and not any(e["payload"]["code"] == "saison_gelee" and e["payload"]["message"] == gel.message for e in self._of("alert")):
            self._alert("panique", "saison_gelee", gel.message)

        # 3 bis. réveil interrompu : reprise, ou réparation puis abandon
        closed = {e["payload"]["reveil"] for e in self._of("reveil_completed", "reveil_abandonne")}
        started = {e["payload"]["reveil"]: e for e in self._of("reveil_started")}
        pending = [(r, e) for r, e in sorted(started.items()) if r not in closed]
        last_cycle_seq = max((e["seq"] for e in self._of("cycle_completed")), default=-1)
        resume: tuple[int, dict[str, Any]] | None = None
        for i, (r, e) in enumerate(pending):
            if i == len(pending) - 1 and tick - r <= REVEIL_ABANDON_S and last_cycle_seq < e["seq"] and not gele:
                resume = (r, e["payload"]["declencheur"])
                continue
            self._abandonner(executor, r)
            rep.reveil = "abandonne"

        # 4. déclencheur et garde-fous (pas de nouveau réveil pendant une reprise)
        launch: dict[str, Any] | None = None
        trigger, variations = mouvement(minute_bars, tick, v.seuil_mouvement_bp, v.fenetre_mouvement_s, v.tick_s)
        if resume is None:
            rep.declencheur = trigger
            if trigger is not None and gele:
                rep.refus = "saison_gelee"
            elif trigger is not None:
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
                acc_h = [e for e in hist.get(s, []) if e.acc]
                last = (acc_h[-1].bid, acc_h[-1].ask) if acc_h else self._dernier_quote_cycle(s)
                if last is not None:
                    marks[s], bids[s] = _mid(*last), last[0]
        self.log.add(
            "veille",
            {
                "tick": tick,
                "quotes": {s: [b, a] for s, (b, a) in sorted(qd.items())},
                "quotes_bruts": {s: [b, a] for s, (b, a) in sorted(bruts.items())},
                "rejets": dict(sorted(rejets.items())),
                "variations_bp": dict(sorted(variations.items())),
                "clotures_1m": {s: b[-1].close for s, b in sorted(minute_bars.items())},
                "confirmes": sorted(confirmes),
                "equity": {p: equity_ueur(st, marks, bids) for p, st in sorted(states.items())},
                "stops": rep.stops,
                "reveil": launch,
                "refus": rep.refus,
                "gel": gele,
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
