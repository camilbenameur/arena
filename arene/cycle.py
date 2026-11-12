"""Un cycle de 4 h de bout en bout, idempotent (docs/SPEC-MVP.md §11).

`run_cycle(paths, clients, now_ts, deciders=None)` :
1. vérifie le journal (refus s'il est cassé), charge config et politique (journal `config_loaded` si un hash change) ;
2. cycle = `now_ts` arrondi au début du créneau de 4 h ; `cycle_completed` déjà là : sortie sans rien écrire ;
3. données (barres Kraken 4 h, Binance 1 j pour E0065, quotes), journalisées ;
4. stops et détention maximale ; 5. gel / arrêt / coupe-circuit / dormance ;
6. témoins (quantité de référence), décideurs LLM en parallèle, aléatoire et LLM via riskd, exécution simulée ;
7. equity au bid de chaque portefeuille, `cycle_completed` ; heartbeat.

Deux horloges : `now_ts` (mur, pour cycle_started/completed, quotes, alertes, config) et `cycle_ts` (instant
de décision : horodatage des intentions, verdicts, ordres, fills et equity). Tout le chemin de décision est
ainsi déterministe et identique à la reprise après un crash.

Reprise : un `cycle_started` sans `cycle_completed` est repris. Les quotes déjà journalisées sont réutilisées,
les décisions LLM déjà reçues ne sont pas redemandées (relues depuis `raw_text`), les intentions déjà
journalisées sont reprises telles quelles (jamais régénérées), et l'exécuteur est idempotent par `intent_id`.
Limite connue : un crash entre deux écritures d'intentions d'un même lot perd la fin du lot pour ce cycle.

Choix d'écart à la spec (signalés) : les témoins de référence (panier, 6040, e0065) ne sont ni gelés ni
arrêtés (ils servent de référence) ; sous coupe-circuit ou dormance, leurs achats sont refusés (KILL_SWITCH)
mais leurs ventes passent ; l'historique initial Kraken est de 7 jours + 2 barres (44 barres) pour que le
rendement 7 j de l'instantané soit défini.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import subprocess
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

from arene import saison
from arene.config import Config, ConfigError, load_config, load_instruments
from arene.data import DataError
from arene.data.binance import BinanceClient
from arene.data.kraken import KrakenClient
from arene.data.store import BarStore
from arene.deciders.llm import LLMDecider, SubscriptionDecider, parse_decision, prompt_sha256
from arene.deciders.snapshot import build_snapshot, snapshot_sha256
from arene.journal import Journal, intent_from_payload, verdict_from_payload, verify
from arene.ledger import (
    equity_24h_ago,
    equity_ueur,
    fees_month,
    month_start_ts,
    orders_last_minute,
    positions_value_ueur,
    replay,
    trades_last_24h,
)
from arene.ops import anthropic_key, dormance, killswitch
from arene.ops.heartbeat import Heartbeat
from arene.ops.notify import Notifier
from arene.paths import Paths
from arene.risk.policy import Policy, PolicyError, load_policy
from arene.risk.riskd import FROZEN, HALTED, Counters, MarketView, evaluate, freeze_or_halt
from arene.sim.executor import SimExecutor
from arene.sim.fills import market_fill
from arene.temoins import TemoinContext, aleatoire, e0065, panier, reference_qty, soixante_quarante
from arene.types import (
    MICRO,
    Bar,
    Instrument,
    Intent,
    PortfolioState,
    Quote,
    Side,
    Verdict,
    notional_ueur,
)

log = logging.getLogger("arene.cycle")

DAY_S = 86_400
HISTORY_S = 7 * DAY_S  # historique Kraken du premier lancement
BINANCE_HISTORY_S = 30 * DAY_S
LLM_TIMEOUT_S = 150.0
UNKNOWN_MAX_CYCLES = 2
SPREAD_WINDOW = 20
LOCK_WAIT_S = 600.0  # un cycle attend la fin d'un réveil ou d'un autre cycle (docs/VEILLE.md §3)
VEILLE_ABSENTE_S = 1800
FLATTEN_LOCK_WAIT_S = 120.0  # `arene kill --now` : ne bloque pas plus de 2 min

TEMOIN_MODULES = {
    "temoin:panier": panier,
    "temoin:6040": soixante_quarante,
    "temoin:e0065": e0065,
    "temoin:aleatoire": aleatoire,
}
REFERENCES = ("temoin:panier", "temoin:6040", "temoin:e0065")
ALEATOIRE = "temoin:aleatoire"


# ---------------------------------------------------------------------------------------- types publics


@dataclass
class Clients:
    """Clients externes injectables (tests : doublures déterministes)."""

    kraken: Any  # KrakenClient : asset_pairs, ohlc, ticker
    binance: Any  # BinanceClient : klines_1d
    http: httpx.Client | None = None  # heartbeat et ntfy

    @classmethod
    def real(cls) -> Clients:
        return cls(KrakenClient(), BinanceClient(), httpx.Client(timeout=10.0))


@dataclass
class CycleReport:
    status: str  # completed | already_done | stale | busy | refused | failed
    cycle_ts: int | None = None
    n_events: int = 0  # événements ajoutés au journal par ce lancement
    n_fills: int = 0
    equity_ueur: dict[str, int] = field(default_factory=dict)
    alerts: list[tuple[str, str]] = field(default_factory=list)  # (niveau, code)
    error: str | None = None
    resumed: bool = False

    @property
    def ok(self) -> bool:
        return self.status in ("completed", "already_done", "stale")


class CycleAbort(Exception):
    """Arrêt prévu (donnée indisponible, config invalide) : alerte du niveau donné, pas de traceback."""

    def __init__(self, level: str, code: str, message: str) -> None:
        super().__init__(message)
        self.level, self.code, self.message = level, code, message


class JournalBroken(Exception):
    pass


class CycleBusy(Exception):
    pass


@contextlib.contextmanager
def cycle_lock(paths: Paths, wait_s: float = 0.0) -> Iterator[None]:
    """Verrou exclusif : un seul cycle (ou mise à plat immédiate) à la fois."""
    paths.var.mkdir(parents=True, exist_ok=True)
    with open(paths.lock, "a") as f:
        deadline = time.monotonic() + wait_s
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise CycleBusy("un autre cycle est en cours") from None
                time.sleep(0.2)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------------------- journal en mémoire


class EventLog:
    """Journal + copie en mémoire, rafraîchie par lecture de la queue du fichier (pas de relecture complète)."""

    def __init__(self, journal: Journal) -> None:
        self.journal = journal
        self.events: list[dict[str, Any]] = []
        self._offset = 0

    def refresh(self) -> None:
        p = self.journal.path
        if not p.exists():
            return
        with open(p, "rb") as f:
            f.seek(self._offset)
            data = f.read()
        end = data.rfind(b"\n")
        if end < 0:
            return
        for line in data[: end + 1].splitlines():
            if line.strip():
                self.events.append(json.loads(line))
        self._offset += end + 1

    def add(self, type: str, payload: Any, ts: int) -> dict[str, Any]:
        rec = self.journal.append(type, payload, ts)
        self.refresh()
        return rec


def default_deciders(cfg: Config, paths: Paths) -> dict[str, LLMDecider]:
    """Un décideur par modèle de la config.

    decider_backend = "api" : clé Console lue à l'exécution (absente -> no_key).
    decider_backend = "abonnement" : `claude -p` sur l'abonnement, isolé (voir SubscriptionDecider).
    """
    out: dict[str, LLMDecider] = {}
    for m in cfg.models:
        args = (
            m.model,
            m.portfolio,
            (Decimal(m.price_in_uusd_per_mtok) / MICRO, Decimal(m.price_out_uusd_per_mtok) / MICRO),
            Decimal(m.daily_budget_uusd) / MICRO,
        )
        if cfg.decider_backend == "abonnement":
            out[m.portfolio] = SubscriptionDecider(*args, workdir=paths.var / "claude-vide")
        else:
            out[m.portfolio] = LLMDecider(*args, key_reader=lambda: anthropic_key(paths))
    return out


def rendez_vous_contexte(t: int, cfg: Config) -> dict[str, Any]:
    """`contexte` d'un cycle : le prochain rendez-vous est l'exécution du cycle suivant (HH:05 UTC)."""
    return {"type": "rendez_vous", "prochain_rendez_vous_ts": t + cfg.interval_s + cfg.cycle_delay_s}


def policy_summary(p: Policy) -> str:
    """Règles de risque en clair, données au modèle dans l'instantané."""

    def pct(bp: int) -> str:
        return f"{bp // 100}" if bp % 100 == 0 else f"{bp / 100:g}"

    return (
        f"Univers : {', '.join(p.symbols)}. Long seulement, sans levier, ordres au marché. "
        f"Un achat vaut au plus {pct(p.max_order_bp)} % de l'equity ; une position au plus {pct(p.max_position_bp)} % ; "
        f"exposition totale au plus {pct(p.max_exposure_bp)} %. "
        f"{p.max_trades_per_day} trades par 24 h, {p.min_interval_same_symbol_s // 3600} h minimum entre deux achats "
        f"d'un même symbole. Stop obligatoire à l'achat entre {pct(p.stop_bp_min)} % et {pct(p.stop_bp_max)} %. "
        f"Le coût aller-retour estimé doit rester sous {p.max_cost_to_expected_move_pct} % du mouvement attendu "
        f"que vous déclarez. Sortie forcée après {p.max_holding_s // DAY_S} jours. Gel 24 h si perte de "
        f"{pct(p.daily_loss_freeze_bp)} % en 24 h ; arrêt si drawdown de {pct(p.drawdown_halt_bp)} %. "
        f"Ordre minimal {p.min_order_ueur // MICRO} EUR."
    )


# ---------------------------------------------------------------------------------------- cycle


class _Runner:
    def __init__(
        self,
        paths: Paths,
        clients: Clients,
        now_ts: int,
        journal: Journal,
        notifier: Notifier,
        heartbeat: Heartbeat,
        deciders: dict[str, Any] | None,
        fault_injector: Callable[[str], bool] | None,
        on_portfolio_done: Callable[[str], None] | None,
    ) -> None:
        self.paths, self.clients, self.now = paths, clients, now_ts
        self.journal, self.notifier, self.heartbeat = journal, notifier, heartbeat
        self.log = EventLog(journal)
        self.given_deciders = deciders
        self.fault_injector = fault_injector
        self.on_portfolio_done = on_portfolio_done
        self.alerts: list[tuple[str, str]] = []
        self.t = 0  # cycle_ts
        # Réglages que la ronde de réveil (arene/veille.py) surcharge ; au cycle ils restent aux valeurs d'origine.
        self.prefetched_quotes: dict[str, Quote] | None = None  # quotes du tick, sinon ticker Kraken
        self.fetch_binance = True
        self.quote_type = "quote"  # le réveil journalise ses quotes sous `quote_reveil` (médiane des spreads intacte)
        self.reuse_partial_quotes = False
        self.quote_symbols: set[str] | None = None  # symboles dont le quote est attendu (None : tous)

    # -------------------------------------------------------------- écriture

    def w(self, type: str, payload: Any) -> dict[str, Any]:
        """Événement de décision, horodaté au cycle."""
        return self.log.add(type, payload, self.t)

    def wn(self, type: str, payload: Any) -> dict[str, Any]:
        """Événement horodaté à l'heure du mur."""
        return self.log.add(type, payload, self.now)

    def alert(self, level: str, code: str, message: str) -> None:
        self.notifier.alert(level, code, message, self.now)
        self.log.refresh()
        self.alerts.append((level, code))

    # -------------------------------------------------------------- lecture

    def states(self) -> dict[str, PortfolioState]:
        return replay(self.log.events)

    def _events_of(self, *types: str) -> list[dict[str, Any]]:
        return [e for e in self.log.events if e["type"] in types]

    def _git_head(self) -> str:
        try:
            out = subprocess.run(
                ["git", "-C", str(self.paths.repo), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5, check=False,
            )  # fmt: skip
            return out.stdout.strip() or "unknown"
        except (OSError, subprocess.SubprocessError):
            return "unknown"

    # -------------------------------------------------------------- étapes

    def run(self) -> CycleReport:
        paths = self.paths
        rep = verify(paths.journal)
        if not rep.ok:
            raise JournalBroken("; ".join(f"{e.code}@{e.line}" for e in rep.errors[:5]))
        try:
            self.cfg = cfg = load_config(paths.config)
            self.policy = load_policy(paths.policy)
        except (ConfigError, PolicyError) as exc:
            raise CycleAbort("panique", "config_invalide", f"configuration refusée : {exc}") from exc
        self.log.refresh()
        n_before = len(self.log.events)

        interval = cfg.interval_s
        self.t = t = self.now // interval * interval
        completed = sorted(e["payload"]["cycle"] for e in self._events_of("cycle_completed"))
        if t in completed:
            return CycleReport("already_done", t)
        if completed and t < completed[-1]:
            return CycleReport("stale", t)

        self._config_and_portfolios()
        self._saison_gel()
        self._veille_absente()
        self.instruments = {i.symbol: i for i in load_instruments(cfg, self.clients.kraken)}
        self.symbols = tuple(self.instruments)
        self.executor = SimExecutor(
            self.journal, self.instruments, cfg.taker_fee_bp, cfg.slippage_bp, cfg.venue_mode, self.fault_injector
        )

        started = [e for e in self._events_of("cycle_started") if e["payload"]["cycle"] == t]
        resume = bool(started)
        self.prev_cycle = completed[-1] if completed else None
        self.cycle_index = len(completed)

        self._market(resume, started[-1]["seq"] if started else None)
        if not resume:
            self.wn("cycle_started", {"cycle": t})
        else:
            self.alert("info", "cycle_resumed", f"reprise du cycle {t} interrompu")
        self._journal_market()
        self._view()
        self._saison_debut()

        self._resolve_unknowns()
        self._stops()
        self._kill_and_dormancy()
        self._freeze_halt()
        self._decide_and_execute()
        self._equities()
        self._saison_apres_equity()
        self.wn("cycle_completed", {"cycle": t})
        self.heartbeat.ping(True, self.now)
        self.log.refresh()
        report = CycleReport(
            "completed",
            t,
            n_events=len(self.log.events) - n_before,
            n_fills=sum(1 for e in self.log.events[n_before:] if e["type"] == "fill"),
            alerts=self.alerts,
            resumed=resume,
        )
        for e in self.log.events:
            if e["type"] == "equity" and e["payload"]["cycle"] == t:
                report.equity_ueur[e["payload"]["portfolio"]] = e["payload"]["equity_ueur"]
        return report

    def _config_and_portfolios(self) -> None:
        cur = {
            "policy_sha256": self.policy.sha256,
            "config_sha256": self.cfg.sha256,
            "prompt_sha256": prompt_sha256(),
        }
        self._claude_version = saison.claude_cli_version()
        last = None
        for e in self._events_of("config_loaded"):
            last = e["payload"]
        changed = last is None or any(last.get(k) != v for k, v in cur.items())
        version_change = last is not None and "claude_cli_version" in last and last["claude_cli_version"] != self._claude_version
        if changed or version_change:
            self.wn("config_loaded", {**cur, "git_head": self._git_head(), "claude_cli_version": self._claude_version})
            if version_change:
                self.alert("info", "claude_cli_version", f"claude --version : {last['claude_cli_version']} -> {self._claude_version}")
        opened = {e["payload"]["portfolio"] for e in self._events_of("portfolio_opened")}
        self.llm_portfolios = tuple(m.portfolio for m in self.cfg.models)
        self.temoin_portfolios = tuple(self.cfg.temoins.portfolios)
        for name, kind in [(p, "llm") for p in self.llm_portfolios] + [(p, "temoin") for p in self.temoin_portfolios]:
            if name not in opened:
                self.wn(
                    "portfolio_opened",
                    {"portfolio": name, "kind": kind, "capital_ueur": self.cfg.capital_ueur,
                     "venue_mode": self.cfg.venue_mode},
                )  # fmt: skip
        self.since_ts = self.log.events[0]["ts"]

    # -------------------------------------------------------------- saison gelée

    def _saison_hashes(self) -> dict[str, str]:
        """Hashes gelés : config SANS la table [saison], politique, consigne système."""
        return {
            "config_sha256": self.cfg.sha256_hors_saison,
            "policy_sha256": self.policy.sha256,
            "prompt_sha256": prompt_sha256(),
            "code_sha256": saison.code_sha256(self.paths.repo),
        }

    def _saison_gel(self) -> None:
        """Refuse de tourner si un hash gelé a changé pendant la saison, sauf dérogation écrite (journalisée)."""
        ouverte, s = saison.saison_ouverte(self.log.events), self.cfg.saison
        if ouverte is not None and s is not None:  # [saison] modifiée pendant la saison ouverte (hors `nom`) : sans effet
            lu = (s.numero, s.debut_ts, s.duree_jours)
            ref = (ouverte["numero"], ouverte.get("debut_ts"), ouverte.get("duree_jours"))
            msg = f"[saison] modifiée pendant la saison {ouverte['numero']} : numero/debut_ts/duree_jours = {lu}, attendu {ref} ; sans effet"
            if lu != ref and ref[1] is not None and not any(
                e["payload"]["code"] == "saison_modifiee" and e["payload"]["message"] == msg for e in self._events_of("alert")
            ):
                self.alert("panique", "saison_modifiee", msg)
        g = saison.verifier_gel(self.log.events, self._saison_hashes(), self.t, saison.lire_derogation(self.paths))
        if g.statut == "gele":
            raise CycleAbort("panique", "saison_gelee", g.message)
        if g.statut == "derogation":
            self.wn(
                "saison_derogation",
                {"numero": g.numero, "raison": saison.lire_derogation(self.paths)[:1000],
                 "hashes_avant": g.avant, "hashes_apres": g.apres},
            )  # fmt: skip
            self.alert("action", "saison_derogation", f"saison {g.numero} : dérogation journalisée ({', '.join(g.diff)})")

    def _saison_debut(self) -> None:
        """Premier cycle dont t >= debut_ts - cycle_delay_s : `saison_debut` puis `saison_reference`, avant toute décision.

        Refusé tant qu'une saison est ouverte (`saison_debut` sans `saison_fin`) ; le numéro doit valoir le dernier + 1.
        `saison_reference` : equity de chaque portefeuille AU BID avec les quotes de ce cycle, juste après `saison_debut`
        (reprise après un crash entre les deux : écrite avant les décisions du cycle repris)."""
        s = self.cfg.saison
        debut = saison.saison_ouverte(self.log.events)
        if debut is None:
            if s is None or self.t < s.debut_ts - self.cfg.cycle_delay_s:
                return
            numeros = [e["payload"]["numero"] for e in self._events_of("saison_debut")]
            if s.numero in numeros:
                return  # déjà commencée (et terminée)
            if s.numero != max(numeros, default=0) + 1:
                msg = f"saison {s.numero} refusée : le numéro attendu est {max(numeros, default=0) + 1}"
                if not any(e["payload"]["code"] == "saison_numero" and e["payload"]["message"] == msg for e in self._events_of("alert")):
                    self.alert("action", "saison_numero", msg)
                return
            self.wn(
                "saison_debut",
                {"numero": s.numero, "nom": s.nom, "cycle": self.t, "fin_prevue_cycle": self.t + s.duree_jours * DAY_S,
                 "debut_ts": s.debut_ts, "duree_jours": s.duree_jours,
                 **self._saison_hashes(), "git_head": self._git_head(), "claude_cli_version": self._claude_version,
                 "portefeuilles": list(self.llm_portfolios + self.temoin_portfolios)},
            )  # fmt: skip
            debut = saison.saison_ouverte(self.log.events)
        if debut is not None and not any(e["payload"]["numero"] == debut["numero"] for e in self._events_of("saison_reference")):
            eq = {p: self._equity_bid(st) for p, st in sorted(self.states().items())}
            self.wn("saison_reference", {"numero": debut["numero"], "cycle": self.t, "equity": eq})

    def _saison_apres_equity(self) -> None:
        """Après les `equity` du cycle : `saison_fin` si la saison ouverte est finie (t >= fin_prevue_cycle)."""
        t = self.t
        debut = saison.saison_ouverte(self.log.events)
        if debut is not None and t >= debut["fin_prevue_cycle"]:
            eq = {e["payload"]["portfolio"]: e["payload"]["equity_ueur"] for e in self._events_of("equity") if e["payload"]["cycle"] == t}
            self.wn("saison_fin", {"numero": debut["numero"], "cycle": t, "equity": dict(sorted(eq.items()))})

    def _veille_absente(self) -> None:
        """Alerte (une fois par absence) si la veille s'est arrêtée : dernier événement `veille` vieux de plus de 30 min,
        alors qu'il y en a déjà eu un (le timer est censé tourner)."""
        veilles = [e["ts"] for e in self._events_of("veille")]
        if not veilles or self.now - max(veilles) <= VEILLE_ABSENTE_S:
            return
        if any(e["payload"]["code"] == "veille_absente" and e["ts"] > max(veilles) for e in self._events_of("alert")):
            return
        self.alert("action", "veille_absente", f"aucun tick de veille depuis {(self.now - max(veilles)) // 60} min")

    def _market(self, resume: bool, started_seq: int | None) -> None:
        """Barres et quotes. À la reprise, les quotes déjà journalisées sont réutilisées (cache disque conservé)."""
        t, interval = self.t, self.cfg.interval_s
        bound = t // interval * interval  # = t au cycle ; au réveil, fin de la dernière barre qui doit être close
        self.store = BarStore(self.paths.data, "kraken")
        self.bstore = BarStore(self.paths.data, "binance")
        quotes: dict[str, Quote] = {}
        if resume and started_seq is not None:
            for e in self.log.events:
                if e["type"] == self.quote_type and e["seq"] > started_seq:
                    q = Quote(**{k: e["payload"][k] for k in ("symbol", "ts", "bid", "ask")})
                    quotes[q.symbol] = q
        expected = set(self.symbols) if self.quote_symbols is None else self.quote_symbols
        if self.reuse_partial_quotes:  # réveil : une ronde garde les quotes déjà écrits, même incomplets
            self.quotes_already_journaled = bool(quotes)
        else:
            self.quotes_already_journaled = bool(expected) and expected <= set(quotes)
        if not self.quotes_already_journaled:
            quotes = {}
            for inst in self.instruments.values():

                def fetch(since: int | None, inst: Instrument = inst) -> list[Bar]:
                    start = since if since is not None else t - HISTORY_S - 2 * interval
                    return self.clients.kraken.ohlc(inst.symbol, inst.kraken_pair, interval, start)

                self.store.update(inst.symbol, interval, fetch)
            for inst in self.instruments.values():
                if self.prefetched_quotes is not None:
                    if inst.symbol in self.prefetched_quotes:
                        quotes[inst.symbol] = self.prefetched_quotes[inst.symbol]
                else:
                    quotes[inst.symbol] = self.clients.kraken.ticker(inst.symbol, inst.kraken_pair)
            if self.fetch_binance:
                self._update_binance()
        self.quotes = quotes
        self.bars: dict[str, list[Bar]] = {}
        for sym in self.symbols:
            bars = self.store.load(sym, interval, t)
            if not bars or bars[-1].ts < bound - interval:
                last = bars[-1].ts if bars else None
                raise CycleAbort(
                    "action", "data_stale", f"{sym} : dernière barre close {last}, attendue {bound - interval}"
                )
            self.bars[sym] = bars

    def _update_binance(self) -> None:
        t = self.t
        try:
            for inst in self.instruments.values():

                def fetch(since: int | None, inst: Instrument = inst) -> list[Any]:
                    start = since if since is not None else t - BINANCE_HISTORY_S
                    return self.clients.binance.klines_1d(inst.binance_symbol, since=start, limit=1000)

                self.bstore.update(inst.binance_symbol, DAY_S, fetch)
        except Exception as exc:  # noqa: BLE001 - E0065 sera sauté si les données manquent, le reste continue
            self.alert("action", "binance_data", f"Binance 1 j indisponible : {type(exc).__name__}: {str(exc)[:200]}")

    def _journal_market(self) -> None:
        if not self.quotes_already_journaled:
            for sym in self.symbols:
                if sym in self.quotes:
                    self.wn(self.quote_type, self.quotes[sym])
        last_bar: dict[str, int] = {}
        for e in self._events_of("bar"):
            p = e["payload"]
            last_bar[p["symbol"]] = max(last_bar.get(p["symbol"], 0), p["ts"])
        for sym in self.symbols:
            for b in self.bars[sym]:
                if b.ts > last_bar.get(sym, -1):
                    self.wn("bar", b)

    def _view(self) -> None:
        spreads: dict[str, list[int]] = {s: [] for s in self.symbols}
        for e in self._events_of("quote"):
            p = e["payload"]
            if p["symbol"] in spreads:
                spreads[p["symbol"]].append(p["ask"] - p["bid"])
        medians = {s: sorted(v[-SPREAD_WINDOW:])[len(v[-SPREAD_WINDOW:]) // 2] for s, v in spreads.items() if v}
        self.marks = {s: (q.bid + q.ask) // 2 for s, q in self.quotes.items()}
        self.bids = {s: q.bid for s, q in self.quotes.items()}
        self.market = MarketView(
            quotes=self.quotes,
            last_closes={s: b[-1].close for s, b in self.bars.items()},
            median_spreads_ueur=medians,
            marks=self.marks,
        )

    # -------------------------------------------------------------- ordres UNKNOWN

    def _resolve_unknowns(self) -> None:
        last: dict[str, str] = {}
        for e in self._events_of("order_state"):
            last[e["payload"]["order_id"]] = e["payload"]["state"]
        for oid, state in last.items():
            if state == "UNKNOWN":
                self.executor.resolve_unknown(oid, self.t)
        self.log.refresh()
        for p in self._round_portfolios():
            age = self.executor.unknown_age_cycles(p, self.t, self.cfg.interval_s)
            if age > UNKNOWN_MAX_CYCLES:
                self._freeze(p, "unknown_order", f"ordre UNKNOWN depuis {age} cycles")

    def _round_portfolios(self) -> tuple[str, ...]:
        """Portefeuilles concernés par la ronde (tous au cycle ; LLM et aléatoire au réveil)."""
        return self.llm_portfolios + self.temoin_portfolios

    def _temoins_to_run(self) -> tuple[str, ...]:
        return self.temoin_portfolios

    def _contexte(self) -> dict[str, Any]:
        """Champ `contexte` de l'instantané : ici le rendez-vous de 4 h."""
        return rendez_vous_contexte(self.t, self.cfg)

    def _freeze(self, portfolio: str, reason: str, detail: str) -> None:
        st = self.states()[portfolio]
        until = self.t + self.policy.freeze_duration_s
        if st.frozen_until_ts >= until:
            return
        self.w("portfolio_frozen", {"portfolio": portfolio, "reason": reason, "until_ts": until})
        self.alert("info", "portfolio_frozen", f"{portfolio} gelé jusqu'à {until} ({detail})")

    # -------------------------------------------------------------- stops

    def _stops(self) -> None:
        interval, t = self.cfg.interval_s, self.t
        since = self.prev_cycle
        bars = {
            s: [b for b in bs if since is not None and b.ts >= since and b.ts + interval <= t]
            for s, bs in self.bars.items()
        }
        self.executor.process_stops_and_expiry(bars, self.quotes, t, self.policy.max_holding_s)
        self.log.refresh()

    # -------------------------------------------------------------- coupe-circuit, dormance, gel, arrêt

    def _kill_and_dormancy(self) -> None:
        sources = killswitch.active_sources(self.paths)
        kill = bool(sources)
        was = False
        for e in self._events_of("kill_switch"):
            was = bool(e["payload"]["active"])
        if kill != was:
            self.wn("kill_switch", {"active": kill, "source": ",".join(sources) or "levé"})
            self.alert("action" if kill else "info", "kill_switch", "coupe-circuit actif" if kill else "coupe-circuit levé")
        age = dormance.age_s(self.paths, self.now, self.since_ts)
        lvl = dormance.level(age)
        last_code = "dormance_ok"
        for e in self._events_of("alert"):
            if e["payload"]["code"].startswith("dormance_"):
                last_code = e["payload"]["code"]
        code = f"dormance_{lvl}"
        if code != last_code:
            self.alert("info" if lvl == dormance.OK else "action", code, f"dormance : dernier ack il y a {age // 3600} h")
        self.kill, self.dormant = kill, lvl
        self.entries_blocked = kill or lvl != dormance.OK
        reason = "kill_switch" if kill else "dormance" if lvl == dormance.FLATTEN else None
        if reason:
            for p in self.llm_portfolios + (ALEATOIRE,):
                self.executor.flatten(p, self._flatten_quotes(), self.t, reason)
            self.log.refresh()

    def _flatten_quotes(self) -> dict[str, Quote]:
        """Quotes de valorisation des mises à plat (le réveil les corrige avec les transactions)."""
        return self.quotes

    def _equity_bid(self, st: PortfolioState) -> int:
        return equity_ueur(st, self.marks, self.bids)

    def _freeze_halt(self) -> None:
        for p in self.llm_portfolios + (ALEATOIRE,):
            if p not in self.states():
                continue
            st = self.states()[p]
            counters = self._counters(p, None, self._equity_bid(st))
            code, until = freeze_or_halt(st, counters, self.policy, self.t)
            if code == HALTED and not st.halted:
                self.w("portfolio_halted", {"portfolio": p, "reason": "drawdown", "until_ts": 0})
                self.alert("action", "portfolio_halted", f"{p} arrêté (drawdown) : revue requise, `arene resume {p}`")
                self.executor.flatten(p, self._flatten_quotes(), self.t, "halt")
                self.log.refresh()
            elif code == FROZEN and st.frozen_until_ts <= self.t:
                self.w("portfolio_frozen", {"portfolio": p, "reason": "daily_loss", "until_ts": until})
                self.alert("info", "portfolio_frozen", f"{p} gelé jusqu'à {until} (perte 24 h)")

    # -------------------------------------------------------------- compteurs riskd (depuis le journal)

    def _counters(self, p: str, intent: Intent | None, eq_now: int) -> Counters:
        ev, t = self.log.events, self.t
        capital = self.cfg.capital_ueur
        ms = month_start_ts(t)
        eq_month, peak, last_eq, halted = capital, capital, None, False
        approved = {e["payload"]["intent_id"] for e in ev if e["type"] == "risk_verdict" and e["payload"]["approved"]}
        last_buy: int | None = None
        for e in ev:
            pl, ty = e["payload"], e["type"]
            if ty == "equity" and pl["portfolio"] == p:
                last_eq = pl["equity_ueur"]
                peak = max(peak, last_eq)
                if e["ts"] <= ms:
                    eq_month = last_eq
            elif ty == "portfolio_halted" and pl["portfolio"] == p:
                halted = True
            elif ty == "portfolio_resumed" and pl["portfolio"] == p:
                if halted and last_eq is not None:
                    peak = last_eq  # après une reprise manuelle d'un arrêt, le plus haut repart de l'equity à plat
                halted = False
            elif (
                intent is not None and ty == "intent" and pl["portfolio"] == p and pl["symbol"] == intent.symbol
                and pl["side"] == "buy" and pl["intent_id"] != intent.intent_id and pl["intent_id"] in approved
            ):  # fmt: skip
                last_buy = e["ts"] if last_buy is None else max(last_buy, e["ts"])
        return Counters(
            trades_24h=trades_last_24h(ev, p, t),
            orders_last_minute=orders_last_minute(ev, t),
            last_symbol_intent_ts=last_buy,
            fees_month_ueur=fees_month(ev, p, t),
            equity_month_start_ueur=eq_month,
            equity_24h_ago_ueur=equity_24h_ago(ev, p, t) or 0,
            equity_peak_ueur=peak,
            equity_now_ueur=eq_now,
        )

    # -------------------------------------------------------------- décisions et exécution

    def _spent_today(self, p: str) -> int:
        day = self.t // DAY_S
        return sum(
            e["payload"].get("cost_uusd") or 0
            for e in self._events_of("decision_received")
            if e["payload"]["portfolio"] == p and e["ts"] // DAY_S == day
        )

    def _recent_decisions(self, p: str) -> list[dict]:
        verdicts = {e["payload"]["intent_id"]: e["payload"] for e in self._events_of("risk_verdict")}
        by_cycle: dict[int, list[str]] = {}
        for e in self._events_of("intent"):
            pl = e["payload"]
            if pl["portfolio"] == p:
                v = verdicts.get(pl["intent_id"])
                out = "?" if v is None else "approved" if v["approved"] else "rejected:" + ",".join(v["reasons"])
                by_cycle.setdefault(pl["cycle"], []).append(f"{pl['side']} {pl['symbol']} {pl['size_bp']}bp {out}")
        out_list = []
        for e in self._events_of("decision_received"):
            pl = e["payload"]
            if pl["portfolio"] != p or pl["cycle"] == self.t:
                continue
            parsed = pl.get("parsed") or {}
            out_list.append(
                {
                    "cycle": pl["cycle"],
                    "ronde": "rendez_vous" if pl["cycle"] % self.cfg.interval_s == 0 else "reveil",
                    "actions": [f"{a['side']} {a['symbol']} {a['size_pct']}%" for a in parsed.get("actions", [])],
                    "outcomes": by_cycle.get(pl["cycle"], []),
                    "parse_error": pl.get("parse_error"),
                    "justification": (parsed.get("justification") or "")[:200],
                }
            )
        return out_list[-5:]

    def _own_events(self, type: str, p: str) -> list[dict[str, Any]]:
        return [e for e in self._events_of(type) if e["payload"].get("portfolio") == p and e["payload"].get("cycle") == self.t]

    def _decision_skip(self, p: str, reason: str, detail: str | None = None) -> None:
        pl: dict[str, Any] = {"portfolio": p, "cycle": self.t, "reason": reason}
        if detail:
            pl["detail"] = detail[:300]
        self.w("decision_skipped", pl)

    @staticmethod
    def _has_key(decider: Any) -> bool:
        reader = getattr(decider, "_key_reader", None)
        return True if reader is None else bool(reader())

    def _decide_and_execute(self) -> None:
        cfg, t = self.cfg, self.t
        deciders = default_deciders(cfg, self.paths) if self.given_deciders is None else {}
        deciders = {**deciders, **(self.given_deciders or {})}
        pool = ThreadPoolExecutor(max_workers=max(1, len(self.llm_portfolios)), thread_name_prefix="llm")
        futures: dict[Any, str] = {}
        pre: dict[str, Any] = {}  # portefeuille -> ("seen", intents) déjà décidé à une exécution précédente
        for p in self.llm_portfolios:
            decider = deciders.get(p)
            if decider is None:
                continue
            received = self._own_events("decision_received", p)
            skipped = self._own_events("decision_skipped", p)
            if received:
                pl = received[-1]["payload"]
                _, _, intents = parse_decision(pl.get("raw_text") or "", p, t, self.symbols)
                pre[p] = intents
                continue
            if skipped:
                continue
            st = self.states()[p]
            if st.halted:
                self._decision_skip(p, "halted")
            elif st.frozen_until_ts > t:
                self._decision_skip(p, "frozen")
            elif self.entries_blocked:
                self._decision_skip(p, "kill_switch", "coupe-circuit" if self.kill else "dormance")
            else:
                snap = build_snapshot(
                    t, self.bars, st, self.marks, self._recent_decisions(p), policy_summary(self.policy),
                    contexte=self._contexte(),
                )
                if self._has_key(decider) and not self._own_events("decision_requested", p):
                    self.w(
                        "decision_requested",
                        {"portfolio": p, "cycle": t, "model": decider.model, "snapshot_sha256": snapshot_sha256(snap)},
                    )
                futures[pool.submit(decider.decide, snap, self._spent_today(p))] = p

        # Témoins pendant que les modèles réfléchissent.
        for p in self._temoins_to_run():
            self._temoin(p)

        results: dict[str, Any] = {}
        done, not_done = wait(list(futures), timeout=LLM_TIMEOUT_S)
        for fut in done:
            p = futures[fut]
            try:
                results[p] = fut.result()
            except Exception as exc:  # noqa: BLE001
                results[p] = ("skip", "api_error", f"{type(exc).__name__}: {str(exc)[:200]}")
        for fut in not_done:
            fut.cancel()
            results[futures[fut]] = ("skip", "api_error", f"délai de {int(LLM_TIMEOUT_S)} s dépassé")
        pool.shutdown(wait=False, cancel_futures=True)

        for p in self.llm_portfolios:
            decider = deciders.get(p)
            if decider is None:
                continue
            intents: list[Intent] = pre.get(p, [])
            if p in results:
                res = results[p]
                if isinstance(res, tuple):  # échec de l'appel (exception, délai)
                    self._decision_skip(p, res[1], res[2])
                    self.alert("action", "llm_api_error", f"{p} : {res[2]}")
                elif res.skipped_reason:
                    self._decision_skip(p, res.skipped_reason, res.error)
                    if res.skipped_reason == "api_error":
                        self.alert("action", "llm_api_error", f"{p} : {res.error}")
                    elif res.skipped_reason == "budget":
                        self.alert("info", "llm_budget", f"{p} : budget du jour atteint")
                else:
                    self.w(
                        "decision_received",
                        {
                            "portfolio": p, "cycle": t, "model_requested": decider.model,
                            "model_returned": res.model_returned, "raw_text": res.raw_text or "",
                            "parsed": res.parsed, "parse_error": res.parse_error,
                            "input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
                            "cost_uusd": res.cost_uusd, "latency_ms": res.latency_ms,
                        },
                    )  # fmt: skip
                    if res.model_returned and res.model_returned != decider.model:
                        self.alert("action", "model_mismatch", f"{p} : demandé {decider.model}, reçu {res.model_returned}")
                    if res.parse_error:
                        self.alert("info", "parse_error", f"{p} : {res.parse_error}")
                    intents = list(res.intents)
            self._handle(p, intents, reference=False)
            if self.on_portfolio_done:
                self.on_portfolio_done(p)

    def _temoin(self, p: str) -> None:
        mod = TEMOIN_MODULES.get(p)
        if mod is None:
            self.alert("action", "temoin_inconnu", f"témoin inconnu dans la config : {p}")
            return
        journaled = self._own_events("intent", p)
        if journaled:
            intents = [intent_from_payload(e["payload"]) for e in journaled]
        else:
            state = self.states()[p]
            if p == "temoin:e0065" and not self._binance_complete():
                self.alert("action", "e0065_data", "données Binance incomplètes : E0065 sauté ce cycle")
                intents = []
            else:
                intents = mod.decide(self.t, state, self.marks, self._context(p))
        self._handle(p, intents, reference=p in REFERENCES)
        if self.on_portfolio_done:
            self.on_portfolio_done(p)

    def _binance_complete(self) -> bool:
        need = self.t - self.t % DAY_S - DAY_S
        return all(
            (self.bstore.last_ts(i.binance_symbol, DAY_S) or 0) >= need for i in self.instruments.values()
        )

    def _context(self, p: str) -> TemoinContext:
        day0 = None
        for e in self._events_of("cycle_started"):
            day0 = e["payload"]["cycle"]
            break
        day0 = (day0 if day0 is not None else self.t) // DAY_S * DAY_S
        return TemoinContext(
            cycle_index=self.cycle_index,
            prev_cycle_ts=self.prev_cycle,
            interval_s=self.cfg.interval_s,
            symbols=self.symbols,
            bars_4h=self.bars,
            day_bars={
                i.symbol: self.bstore.load(i.binance_symbol, DAY_S, self.t) for i in self.instruments.values()
            },
            e0065=self.cfg.temoins.e0065,
            day0_ts=day0,
            trajectoire=0,
            min_trade_ueur=self.policy.min_order_ueur,
        )

    def _reference_verdict(self, intent: Intent, st: PortfolioState) -> Verdict:
        if self.entries_blocked and intent.side == Side.BUY:
            return Verdict(intent.intent_id, False, ("KILL_SWITCH",), 0, 0, self.policy.sha256)
        inst, q = self.instruments[intent.symbol], self.quotes[intent.symbol]
        fee_bp, slip = self.cfg.taker_fee_bp, self.cfg.slippage_bp
        qty = reference_qty(intent, st, self.marks, q, inst, fee_bp, slip)
        if qty <= 0:
            return Verdict(intent.intent_id, False, ("REFERENCE", "ZERO_QTY"), 0, 0, self.policy.sha256)
        price, fee = market_fill(intent.side, qty, q, inst, fee_bp, slip)
        reserved = notional_ueur(qty, price, round_up=True) + fee if intent.side == Side.BUY else notional_ueur(qty, price, round_up=False)
        return Verdict(intent.intent_id, True, ("REFERENCE",), qty, reserved, self.policy.sha256)

    def _buy_now_forbidden(self, intent: Intent, st: PortfolioState) -> bool:
        """Un verdict approuvé en attente d'exécution (crash entre verdict et ordre) ne vaut plus si, à la reprise,
        le coupe-circuit, la dormance, le gel ou l'arrêt interdit l'entrée."""
        started = any(
            e["payload"].get("order_id") == intent.intent_id for e in self._events_of("order_state", "fill")
        )
        return not started and (self.entries_blocked or st.halted or st.frozen_until_ts > self.t)

    def _no_quote(self, intent: Intent) -> None:
        if not any(e["payload"]["intent_id"] == intent.intent_id for e in self._events_of("risk_verdict")):
            self.w("risk_verdict", Verdict(intent.intent_id, False, ("NO_QUOTE",), 0, 0, self.policy.sha256))
        self.executor.reject(intent, "NO_QUOTE", self.t)
        self.log.refresh()

    def _handle(self, p: str, intents: list[Intent], *, reference: bool) -> None:
        """Journalise toutes les intentions, puis verdict et exécution de chacune (idempotent)."""
        seen = {e["payload"]["intent_id"] for e in self._events_of("intent")}
        for intent in intents:
            if intent.intent_id not in seen:
                self.w("intent", intent)
        for intent in intents:
            st = self.states().get(p)
            if st is None:
                continue
            if intent.symbol not in self.quotes:  # jamais de `continue` muet : verdict NO_QUOTE et ordre refusé
                self._no_quote(intent)
                continue
            if not self.entries_blocked and killswitch.active_sources(self.paths):
                self.kill = self.entries_blocked = True  # armé pendant l'appel LLM : l'achat qui suit doit être refusé
            verdict = None
            for e in self._events_of("risk_verdict"):
                if e["payload"]["intent_id"] == intent.intent_id:
                    verdict = verdict_from_payload(e["payload"])
            if verdict is not None and verdict.approved and intent.side == Side.BUY and self._buy_now_forbidden(intent, st):
                verdict = None  # approuvé avant un crash, jamais exécuté, et l'entrée est interdite à la reprise : on réévalue
            if verdict is None:
                if reference:
                    verdict = self._reference_verdict(intent, st)
                else:
                    verdict = evaluate(
                        intent, st, self.market, self.policy,
                        self._counters(p, intent, self._equity_bid(st)), self.t, self.instruments,
                        self.cfg.taker_fee_bp, self.cfg.slippage_bp, self.entries_blocked,
                    )  # fmt: skip
                self.w("risk_verdict", verdict)
            self.executor.execute(intent, verdict, self.quotes[intent.symbol], self.t)
            self.log.refresh()

    # -------------------------------------------------------------- equity

    def _equities(self) -> None:
        t = self.t
        have = {e["payload"]["portfolio"] for e in self._events_of("equity") if e["payload"]["cycle"] == t}
        for p, st in sorted(self.states().items()):
            if p in have:
                continue
            pos = positions_value_ueur(st, self.marks, self.bids)
            self.w(
                "equity",
                {"portfolio": p, "cycle": t, "cash_ueur": st.cash_ueur, "positions_value_ueur": pos,
                 "equity_ueur": st.cash_ueur + pos},
            )  # fmt: skip


# ---------------------------------------------------------------------------------------- points d'entrée


def run_cycle(
    paths: Paths,
    clients: Clients,
    now_ts: int,
    *,
    deciders: dict[str, Any] | None = None,
    fault_injector: Callable[[str], bool] | None = None,
    on_portfolio_done: Callable[[str], None] | None = None,
    lock_wait_s: float = LOCK_WAIT_S,
) -> CycleReport:
    """Exécute (ou reprend) le cycle de `now_ts`. Ne lève jamais : un échec renvoie un rapport non ok.

    `deciders` : {portefeuille: objet avec .model et .decide(snapshot, dépense_du_jour_uusd)} ; par défaut les
    LLMDecider de la config. `fault_injector` et `on_portfolio_done` sont des crochets de test.
    """
    journal = Journal(paths.journal)
    notifier = Notifier(journal, paths.secrets, clients.http)
    heartbeat = Heartbeat(paths.secrets, notifier)
    runner: _Runner | None = None
    try:
        with cycle_lock(paths, lock_wait_s):
            runner = _Runner(paths, clients, now_ts, journal, notifier, heartbeat, deciders, fault_injector, on_portfolio_done)
            return runner.run()
    except CycleBusy as exc:
        return CycleReport("busy", error=str(exc))
    except JournalBroken as exc:
        notifier.journal_enabled = False  # on n'écrit jamais dans un journal cassé
        notifier.send("panique", "journal_casse", f"journal cassé, cycle refusé : {exc}")
        heartbeat.ping(False, now_ts)
        return CycleReport("refused", error=f"journal cassé : {exc}")
    except (CycleAbort, DataError) as exc:
        level, code, msg = (
            (exc.level, exc.code, exc.message) if isinstance(exc, CycleAbort) else ("action", "data_error", str(exc))
        )
        notifier.alert(level, code, msg, now_ts)
        heartbeat.ping(False, now_ts)
        return _failed(runner, msg, (level, code))
    except Exception as exc:
        log.exception("cycle interrompu par une exception non prévue")
        msg = f"{type(exc).__name__}: {str(exc)[:300]}"
        notifier.alert("panique", "cycle_exception", f"cycle interrompu : {msg}", now_ts)
        heartbeat.ping(False, now_ts)
        return _failed(runner, msg, ("panique", "cycle_exception"))


def _failed(runner: _Runner | None, msg: str, alert: tuple[str, str]) -> CycleReport:
    rep = CycleReport("failed", runner.t if runner and runner.t else None, error=msg)
    rep.alerts = (runner.alerts if runner else []) + [alert]
    return rep


def flatten_now(paths: Paths, clients: Clients, now_ts: int, *, source: str = "cli") -> CycleReport:
    """Mise à plat immédiate des portefeuilles LLM et aléatoire au bid (pour `arene kill --now`)."""
    journal = Journal(paths.journal)
    notifier = Notifier(journal, paths.secrets, clients.http)
    try:
        with cycle_lock(paths, FLATTEN_LOCK_WAIT_S):
            if not verify(paths.journal).ok:
                raise JournalBroken("vérification du journal en échec")
            cfg = load_config(paths.config)
            instruments = {i.symbol: i for i in load_instruments(cfg, clients.kraken)}
            elog = EventLog(journal)
            elog.refresh()
            states = replay(elog.events)
            targets = [
                p for p in [m.portfolio for m in cfg.models] + [ALEATOIRE]
                if p in states and states[p].positions
            ]  # fmt: skip
            symbols = sorted({s for p in targets for s in states[p].positions})
            quotes = {s: clients.kraken.ticker(s, instruments[s].kraken_pair) for s in symbols}
            for q in quotes.values():
                elog.add("quote", q, now_ts)
            was = False
            for e in elog.events:
                if e["type"] == "kill_switch":
                    was = bool(e["payload"]["active"])
            if not was:
                elog.add("kill_switch", {"active": True, "source": source}, now_ts)
            ex = SimExecutor(journal, instruments, cfg.taker_fee_bp, cfg.slippage_bp, cfg.venue_mode)
            n = 0
            for p in targets:
                n += len(ex.flatten(p, quotes, now_ts, "kill_switch"))
            notifier.alert("action", "kill_now", f"mise à plat immédiate : {n} fills ({len(targets)} portefeuilles)", now_ts)
            return CycleReport("completed", now_ts // cfg.interval_s * cfg.interval_s, n_fills=n)
    except CycleBusy as exc:
        return CycleReport("busy", error=str(exc))
    except Exception as exc:
        log.exception("mise à plat immédiate en échec")
        msg = f"{type(exc).__name__}: {str(exc)[:300]}"
        notifier.alert("panique", "kill_now_failed", f"mise à plat immédiate impossible : {msg}", now_ts)
        return CycleReport("failed", error=msg)


def smoke_snapshot(paths: Paths, clients: Clients, portfolio: str, now_ts: int) -> dict:
    """Instantané courant d'un portefeuille (données réelles via les clients) sans rien journaliser."""
    cfg, policy = load_config(paths.config), load_policy(paths.policy)
    interval = cfg.interval_s
    t = now_ts // interval * interval
    instruments = {i.symbol: i for i in load_instruments(cfg, clients.kraken)}
    store = BarStore(paths.data, "kraken")
    bars: dict[str, list[Bar]] = {}
    marks: dict[str, int] = {}
    for sym, inst in instruments.items():
        store.update(
            sym, interval,
            lambda since, inst=inst: clients.kraken.ohlc(inst.symbol, inst.kraken_pair, interval, since or t - HISTORY_S - 2 * interval),
        )  # fmt: skip
        bars[sym] = store.load(sym, interval, t)  # type: ignore[assignment]
        q = clients.kraken.ticker(sym, inst.kraken_pair)
        marks[sym] = (q.bid + q.ask) // 2
    el = EventLog(Journal(paths.journal))
    el.refresh()
    st = replay(el.events).get(portfolio) or PortfolioState(portfolio, cfg.capital_ueur)
    return build_snapshot(t, bars, st, marks, [], policy_summary(policy), contexte=rendez_vous_contexte(t, cfg))
