"""Données du dashboard pour la ligue dérivés (contrats perpétuels, paper), à partir de son journal SEUL.

Journal séparé : `var-perp/journal/events.jsonl` (même format haché que le spot). Ne JAMAIS lire
`var-perp/essais/` (ligues d'essai) ni `var-perp/rounds/` (flux bruts du CLI) ni `var-perp/llm-calls.jsonl`.

Unités du journal : µEUR (`_ueur`), µUSD (`_uusd`, prix), quantités en 1e-8 d'unité signées (long > 0), funding
en µEUR signé (> 0 payé). Rien de ce qui suit ne publie un chemin, une trace d'erreur ou un détail d'outillage :
`round_data.path`, `stderr_tail`, `cli_version`, `cli_rc`, `tools_offered`, `mcp_status`, `first_error`,
les réponses brutes des outils, `perp_tick.notes/problems` et les messages d'`alert` ne sortent jamais de ce module
(docs/COORDINATION-dashboard.md, demande du 12/11, 21 h 30 UTC).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from arene.journal import Journal, verify
from arene.perp import agent_orders as AO
from arene.perp.ledger import MarginAccount, PerpLedgerError, price_pnl_uusd, replay, to_eur

ROUND_S = 4 * 3600
ROUND_OFFSET_S = 2 * 3600  # rendez-vous à 02:00, 06:00, …, 22:00 UTC
PAS_COURBE_S = 1_800  # un point toutes les 30 min sur la courbe (plus le dernier relevé)
DECISIONS_MAX = 120
OPERATIONS_MAX = 60
JUSTIFICATION_MAX = 1_200
INVALIDATION_MAX = 200
NOTE_MAX = 160

PANIER = "benchmark-perp:basket-1x"
TENDANCE = "benchmark-perp:trend"
ALEATOIRE = "benchmark-perp:random"

NOMS = {
    "llm-perp:claude-haiku-5-5": "Claude Haiku 5.5",
    "llm-perp:claude-sonnet-5-5": "Claude Sonnet 5.5",
    "llm-perp:claude-opus-5-5": "Claude Opus 5.5",
    "llm-perp:claude-fable-5-2": "Claude Fable 5.2",
    PANIER: "Témoin panier 1x",
    TENDANCE: "Témoin tendance",
    ALEATOIRE: "Témoin aléatoire",
}
ORDRE = list(NOMS)
DESCRIPTIONS = {
    PANIER: "Acheteur à parts égales des 6 contrats, sans levier ni stop, rééquilibré chaque mois : acheter et garder.",
    TENDANCE: "Chaque jour, long sur un contrat qui a monté sur 20 jours, short sinon ; 1/6 du portefeuille par contrat, stop à 10 %.",
    ALEATOIRE: "Tire 0 à 2 décisions au hasard à chaque rendez-vous, avec exactement les mêmes règles de risque que les IA.",
}

ACTIONS = {"open_long": "Ouvre un long", "open_short": "Ouvre un short", "reduce": "Réduit", "close": "Ferme"}

RAISONS_FILL = {
    "intent": "décision",
    "stop": "stop touché",
    "take_profit": "objectif atteint",
    "margin_closeout": "clôture sur marge",
    "max_holding": "détention maximale (7 j)",
    "halt": "arrêt sur drawdown",
    "kill_switch": "coupe-circuit",
    "no_stop": "position sans stop fermée",
}

EXECUTIONS = {
    "filled": "exécuté",
    "filled_without_take_profit": "exécuté, sans objectif",
    "closed_without_stop": "stop impossible à poser : position refermée",
    "unprotected_position_open": "position restée sans stop (fermée par la veille)",
    "refused": "refusé à l’exécution",
    "error": "échec de l’exécution",
    "not_executed_view_stale": "non exécuté : données de marché périmées",
    "not_executed_stale_trigger": "non exécuté : franchissement vu trop tard (plus de 15 min)",
    "not_executed_refused_on_resume": "non exécuté : refusé à la reprise",
}

FINS = {"expired": "expiré", "replaced": "remplacé", "portfolio_halted": "annulé (portefeuille arrêté)"}
HISTORIQUE_MAX = 12

SAUTS = {
    "halted": "portefeuille arrêté",
    "daily_budget": "budget du jour atteint",
    "interrupted_before_call": "ronde interrompue avant l’appel",
    "interrupted_after_call": "ronde interrompue après l’appel",
}

CODES = {
    "NOT_WHITELISTED": "contrat hors de la liste autorisée",
    "NOT_TRADEABLE": "contrat non négociable en ce moment",
    "UNKNOWN_INSTRUMENT": "contrat inconnu",
    "BAD_ACTION": "action invalide",
    "BAD_PORTFOLIO": "portefeuille invalide",
    "INTENT_STALE": "décision trop ancienne",
    "BAD_SIZE": "taille invalide",
    "BAD_HORIZON": "horizon invalide",
    "BAD_TAKE_PROFIT": "objectif invalide",
    "BAD_EXPECTED_MOVE": "mouvement attendu invalide",
    "NO_QUOTE": "aucun prix",
    "NO_MARK": "aucun prix de référence",
    "NO_FX": "aucun cours euro-dollar",
    "NO_EQUITY": "valeur du portefeuille inconnue",
    "NO_POSITION": "aucune position à réduire",
    "NO_FLIP": "retournement interdit (fermer d’abord)",
    "KILL_SWITCH": "coupe-circuit actif",
    "HALTED": "portefeuille arrêté",
    "FROZEN": "portefeuille gelé",
    "COUNTERS_MISSING": "compteurs de risque indisponibles",
    "FEE_BUDGET": "budget de frais du mois atteint",
    "DAILY_TRADES": "4 ouvertures déjà faites en 24 h",
    "ORDER_RATE": "trop d’ordres à la minute",
    "TOO_SOON": "moins de 4 h depuis la dernière ouverture sur ce contrat",
    "DATA_STALE": "données de marché périmées",
    "MARK_SANITY": "prix incohérents entre eux",
    "SPREAD_ANOMALY": "écart achat-vente anormal",
    "FUNDING_EXTREME": "funding extrême contre la position",
    "MAX_ORDER_SIZE": "ordre au-delà de 50 % du portefeuille",
    "STOP_REQUIRED": "ouverture sans stop",
    "STOP_RANGE": "stop hors de 1 à 15 %",
    "EDGE_TOO_SMALL": "coûts trop grands face au mouvement attendu",
    "ORDER_TOO_SMALL": "ordre trop petit",
    "MAX_CONTRACT_POSITION": "plafond de position de la plateforme",
    "MAX_POSITION": "position au-delà de 100 % du portefeuille",
    "MAX_LEVERAGE": "levier au-delà de 2",
    "INITIAL_MARGIN": "marge insuffisante après l’ordre",
    "MAX_TRADE_LOSS": "perte au stop au-delà de 3 % du portefeuille",
    "MAX_OPEN_RISK": "pertes cumulées aux stops au-delà de 7,5 %",
    "INTERNAL_ERROR": "erreur interne du garde-fou",
}

OUTILS = {
    "bougies": "les bougies d’un contrat",
    "carnet": "le carnet d’ordres",
    "derives": "le funding et l’open interest",
    "indicateurs": "les indicateurs techniques",
    "simuler_ordre": "le verdict du garde-fou, sans exécuter",
    "historique": "ses décisions passées",
}

# Les 6 contrats, tels que le flux public de Kraken Futures les nomme (prix en direct côté navigateur).
PRODUITS = ("PF_XBTUSD", "PF_ETHUSD", "PF_SOLUSD", "PF_XRPUSD", "PF_LINKUSD", "PF_LTCUSD")

_SYM = re.compile(r"^(?:PF_)?([A-Z0-9]+?)(?:USD)?(?:-PERP)?$")


def court(instrument: str | None) -> str:
    """« PF_XBTUSD », « BTC-PERP » → « BTC »."""
    if not instrument:
        return "?"
    s = str(instrument).upper()
    if s.endswith("-PERP"):
        base = s[: -len("-PERP")]
    else:
        m = _SYM.match(s)
        base = m.group(1) if m else s
        base = base.removeprefix("PF_")
    return "BTC" if base == "XBT" else base


def produit(instrument: str | None) -> str | None:
    """Le nom du contrat dans le flux public de Kraken Futures (« BTC-PERP » → « PF_XBTUSD »), ou None."""
    c = court(instrument)
    pid = f"PF_{'XBT' if c == 'BTC' else c}USD"
    return pid if pid in PRODUITS else None


def nom(portfolio: str) -> str:
    return NOMS.get(portfolio, portfolio.split(":", 1)[-1])


def slug(portfolio: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", portfolio.lower()).strip("-")


def prochain_rendez_vous(now: int) -> int:
    return ((now - ROUND_OFFSET_S) // ROUND_S + 1) * ROUND_S + ROUND_OFFSET_S


def perp_journal_path(spot_journal: Path) -> Path:
    """Le journal de la ligue dérivés, voisin du var du spot : <dépôt>/var-perp/journal/events.jsonl."""
    return Path(spot_journal).resolve().parent.parent.parent / "var-perp" / "journal" / "events.jsonl"


def _pct_str(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v))
    except ValueError:
        return None


def _texte(v: Any, n: int) -> str | None:
    if not isinstance(v, str) or not v.strip():
        return None
    v = " ".join(v.split())
    return v if len(v) <= n else v[: n - 1].rstrip() + "…"


def _prix_uusd(v: Any) -> int | None:
    """« 98000.5 » (dollars en texte) -> µUSD entiers."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        return None
    return int(d.scaleb(6)) if d.is_finite() and d > 0 else None


def _rejet_public(error: Any) -> str:
    """Catégorie fixe d'un élément refusé à la création (le texte brut n'est pas publié)."""
    s = str(error or "").lower()
    if "25 %" in s or "away from the mark" in s:
        return "niveau à plus de 25 % du prix"
    if "already crossed" in s:
        return "niveau déjà franchi"
    return "élément invalide"


def _declencheur(raw: Any, kind: str = "wakeup") -> dict[str, Any] | None:
    """Le déclencheur d'une ronde hors rendez-vous. Réveil de marché : contrat et variation. Alerte de l'IA :
    contrat, sens, niveau et sa note. Le reste (id, fenêtre interne) n'est pas publié."""
    d = raw
    if isinstance(raw, str):
        try:
            d = json.loads(raw)
        except ValueError:
            return None
    if not isinstance(d, Mapping):
        return None
    if kind == "alert":
        cond = d.get("condition")
        return {
            "type": "alerte", "instrument": court(d.get("instrument")),
            "condition": cond if cond in ("above", "below") else None, "prix_uusd": _prix_uusd(d.get("price_usd")),
            "note": _texte(d.get("note"), NOTE_MAX),
        }  # fmt: skip
    mv = d.get("move_bp")
    return {
        "type": "marche",
        "instrument": court(d.get("instrument")),
        "move_bp": mv if isinstance(mv, int) else None,
        "window_s": d.get("window_s") if isinstance(d.get("window_s"), int) else 3600,
    }


def _erreur_publique(parse_error: Any) -> str | None:
    """Catégorie d'échec, jamais le texte brut (il peut citer le CLI, une trace ou un chemin)."""
    if not parse_error:
        return None
    s = str(parse_error).lower()
    if "budget" in s:
        return "plafond de coût de l’appel atteint"
    if "no structured output" in s:
        return "réponse illisible"
    if "invalid decision" in s:
        return "décision invalide"
    if "timeout" in s or "timed out" in s:
        return "délai dépassé"
    return "échec de l’appel"


def _outil_args(tool: str, raw: Any) -> str:
    """Les arguments d'un appel d'outil, résumés : « BTC 4h », « ETH 1h ×24 »."""
    try:
        a = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except ValueError:
        return ""
    if not isinstance(a, Mapping):
        return ""
    parts = []
    if isinstance(a.get("instrument"), str):
        parts.append(court(a["instrument"]))
    if tool == "simuler_ordre" and isinstance(a.get("action"), str) and a["action"] in ACTIONS:
        parts.append(ACTIONS[a["action"]].lower().replace("ouvre un ", ""))
    if isinstance(a.get("intervalle"), str):
        parts.append(a["intervalle"])
    return " ".join(p for p in parts if re.fullmatch(r"[A-Za-z0-9 ]{1,16}", p))


def _series(events: Iterable[Mapping[str, Any]]) -> dict[str, list[tuple[int, int, int]]]:
    out: dict[str, list[tuple[int, int, int]]] = {}
    for e in events:
        if e["type"] == "perp_equity":
            p = e["payload"]
            out.setdefault(p["portfolio"], []).append((p["ts"], p["equity_ueur"], p.get("gross_ueur") or 0))
    for s in out.values():
        s.sort()
    return out


def _drawdowns(serie: list[tuple[int, int, int]]) -> tuple[float, float]:
    """(drawdown maximal, drawdown actuel), en fraction du sommet."""
    peak, dd_max, dd = 0, 0.0, 0.0
    for _ts, eq, _g in serie:
        peak = max(peak, eq)
        dd = (peak - eq) / peak if peak > 0 else 0.0
        dd_max = max(dd_max, dd)
    return dd_max, dd


def _positions(acc: MarginAccount | None, marks: Mapping[str, int], fx: tuple[int, int] | None) -> list[dict[str, Any]]:
    if acc is None:
        return []
    out = []
    for inst, pos in sorted(acc.positions.items()):
        mark = marks.get(inst)
        latent = notionnel = None
        if isinstance(mark, int) and mark > 0 and fx:
            try:
                latent = to_eur(price_pnl_uusd(pos.qty, pos.entry_uusd, mark), *fx)
            except PerpLedgerError:
                latent = None
            notionnel = abs(pos.qty) * mark // 100_000_000 * 1_000_000 // ((fx[0] + fx[1]) // 2)
        out.append({
            "instrument": court(inst), "sens": "long" if pos.qty > 0 else "short", "qty": abs(pos.qty),
            "entree_uusd": pos.entry_uusd, "mark_uusd": mark if isinstance(mark, int) else None,
            "stop_uusd": pos.stop_uusd, "objectif_uusd": pos.take_profit_uusd,
            "latent_ueur": latent, "notionnel_ueur": notionnel, "depuis_ts": pos.opened_ts,
            "produit": produit(inst), "qty_signee": pos.qty,
        })  # fmt: skip
    return out


def _bp_pct(v: Any) -> float | None:
    return v / 100 if isinstance(v, int) and not isinstance(v, bool) else None


def _element(kind: str, d: Mapping[str, Any], created_ts: int | None = None) -> dict[str, Any]:
    """Une alerte ou un ordre d'entrée posé par une IA, en champs publiables (ni id, ni texte technique)."""
    cond = d.get("condition")
    out: dict[str, Any] = {
        "type": "alerte" if kind == "alert" else "ordre", "instrument": court(d.get("instrument")),
        "condition": cond if cond in ("above", "below") else None,
        "prix_uusd": d.get("price_uusd") if isinstance(d.get("price_uusd"), int) else None,
        "expire_ts": d.get("expires_ts") if isinstance(d.get("expires_ts"), int) else None, "pose_ts": created_ts,
    }  # fmt: skip
    if kind == "alert":
        out["note"] = _texte(d.get("note"), NOTE_MAX)
    else:
        side = d.get("side")
        out.update({
            "sens": side if side in ("long", "short") else None, "taille_pct": _bp_pct(d.get("size_bp")),
            "stop_pct": _bp_pct(d.get("stop_bp")), "objectif_pct": _bp_pct(d.get("take_profit_bp")),
            "horizon_h": d.get("horizon_h") if isinstance(d.get("horizon_h"), int) else None,
            "attendu_pct": _bp_pct(d.get("expected_move_bp")),
            "confiance_pct": d.get("confidence_pct") if isinstance(d.get("confidence_pct"), (int, float)) else None,
            "invalidation": _texte(d.get("invalidation"), INVALIDATION_MAX),
        })  # fmt: skip
    return out


def _attente(events: list[dict[str, Any]], pf: str) -> dict[str, Any]:
    """Alertes et ordres d'entrée de `pf` : ce qui est en attente (dernier `agent_orders_set` moins ce qui est
    déclenché ou terminé depuis, calcul du moteur) et ce qui est arrivé aux derniers éléments (hors remplacés :
    chaque décision remplace l'ensemble, ce n'est pas un événement)."""
    st = AO.pending_state(events, pf)
    pending = [_element(el.kind, el.data, el.created_ts) for el in st.pending]
    histo = []
    for oid, el in st.catalog.items():
        x = None
        if oid in st.triggered:
            x = {**_element(el.kind, el.data, el.created_ts), "ts": st.triggered[oid]["ts"], "issue": "declenche"}
            if el.kind == "entry":
                ex, v = st.executions.get(oid), st.verdicts.get(oid)
                if v is not None and not v.get("approved"):
                    x["issue_detail"] = "refusé par le garde-fou"
                elif ex is not None:
                    x["issue_detail"] = EXECUTIONS.get(str(ex.get("status")), "exécution inconnue")
        elif oid in st.ended and st.ended[oid]["payload"].get("reason") != "replaced":
            r = str(st.ended[oid]["payload"].get("reason"))
            x = {**_element(el.kind, el.data, el.created_ts), "ts": st.ended[oid]["ts"], "issue": "fin", "issue_detail": FINS.get(r, "terminé")}
        if x is not None:
            histo.append(x)
    histo.sort(key=lambda x: x["ts"], reverse=True)
    return {
        "alertes": [x for x in pending if x["type"] == "alerte"],
        "ordres": [x for x in pending if x["type"] == "ordre"],
        "historique": histo[:HISTORIQUE_MAX], "n_poses": len(st.catalog),
    }


def _decisions_llm(events: list[dict[str, Any]], pf: str) -> list[dict[str, Any]]:
    """Une entrée par ronde jouée (ou sautée) par le portefeuille LLM `pf`, de la plus récente à la plus ancienne.

    Une ronde = (portefeuille, round). Les verdicts et exécutions n'ont pas de `round` : ils suivent la décision du
    même portefeuille dans le journal, et sont rattachés par `intent_id` (les fills par `order_id`)."""
    rondes: dict[int, dict[str, Any]] = {}
    par_intent: dict[str, dict[str, Any]] = {}
    courante: dict[str, Any] | None = None
    ordres: dict[str, Mapping[str, Any]] = {}  # id d'un ordre d'entrée -> l'ordre tel que posé
    declenches: dict[str, dict[str, Any]] = {}  # id -> entrée « ordre déclenché » de la chronologie

    def declenche(oid: str, ts: int, trig: Mapping[str, Any] | None) -> dict[str, Any]:
        """Un ordre d'entrée déclenché entre deux rondes : sa propre entrée, à qui appartiennent verdict,
        exécution et fills (`intent_id` = id de l'ordre), jamais à la dernière décision."""
        if oid not in declenches:
            o = ordres[oid]
            el = _element("entry", o)
            action = {
                "instrument": el["instrument"], "action": "open_long" if el["sens"] == "long" else "open_short",
                "taille_pct": el["taille_pct"], "stop_pct": el["stop_pct"], "objectif_pct": el["objectif_pct"],
                "horizon_h": el["horizon_h"], "attendu_pct": el["attendu_pct"], "confiance_pct": el["confiance_pct"],
                "invalidation": el["invalidation"], "ecartee": False, "verdict": None, "execution": None, "fills": [],
            }  # fmt: skip
            declenches[oid] = {
                "round": ts, "ts": ts, "kind": "ordre", "statut": "declenche", "saut": None,
                "declencheur": {"type": "ordre", "instrument": el["instrument"], "condition": el["condition"], "prix_uusd": el["prix_uusd"]},
                "justification": None, "actions": [action], "outils": [], "erreur": None, "cout_uusd": None,
                "latence_ms": None, "jetons": None, "pose": None,
            }  # fmt: skip
            par_intent[oid] = action
        return declenches[oid]

    def ronde(r: int, ts: int) -> dict[str, Any]:
        if r not in rondes:
            rondes[r] = {
                "round": r, "ts": ts, "kind": "rendezvous", "declencheur": None, "statut": "en_cours", "saut": None,
                "justification": None, "actions": [], "outils": [], "erreur": None, "cout_uusd": None,
                "latence_ms": None, "jetons": None, "pose": None,
            }  # fmt: skip
        return rondes[r]

    for e in events:
        t, p = e["type"], e["payload"]
        if p.get("portfolio") != pf:
            continue
        if t == "round_data":
            d = ronde(p["round"], e["ts"])
            d["kind"] = p.get("kind") or "rendezvous"
            d["declencheur"] = _declencheur(p.get("trigger"), d["kind"]) if d["kind"] in ("wakeup", "alert") else None
        elif t == "tool_call":
            d = ronde(p["round"], e["ts"])
            tool = str(p.get("tool") or "").removeprefix("mcp__arene__")
            if tool in OUTILS:
                d["outils"].append({"outil": tool, "args": _outil_args(tool, p.get("arguments")), "erreur": bool(p.get("is_error"))})
        elif t == "perp_llm_skipped":
            d = ronde(p["round"], e["ts"])
            reason = str(p.get("reason") or "")
            d["statut"], d["saut"] = "sautee", SAUTS.get(reason, "préparation impossible" if reason.startswith("prepare_error") else "sautée")
        elif t == "agent_decision":
            d = ronde(p["round"], e["ts"])
            d["kind"] = p.get("kind") or d["kind"]
            parsed = p.get("parsed") if isinstance(p.get("parsed"), Mapping) else None
            d["cout_uusd"] = p.get("cost_uusd")
            d["latence_ms"] = p.get("latency_ms")
            d["jetons"] = (p.get("input_tokens") or 0) + (p.get("output_tokens") or 0) + (p.get("cache_read_tokens") or 0) + (p.get("cache_write_tokens") or 0)
            if parsed is None:
                d["statut"], d["erreur"] = "echec", _erreur_publique(p.get("parse_error")) or "échec de l’appel"
            else:
                d["statut"] = "decidee"
                d["justification"] = _texte(parsed.get("justification"), JUSTIFICATION_MAX)
                # `parsed.actions` ne garde que les actions valides ; `action_errors[].k` indexe la liste BRUTE.
                n_ecartees = sum(1 for a in parsed.get("action_errors") or [] if isinstance(a, Mapping))
                for a in parsed.get("actions") or []:
                    if not isinstance(a, Mapping):
                        continue
                    d["actions"].append({
                        "instrument": court(a.get("instrument")), "action": a.get("action"),
                        "taille_pct": _pct_str(a.get("size_pct")), "stop_pct": _pct_str(a.get("stop_pct")),
                        "objectif_pct": _pct_str(a.get("take_profit_pct")), "horizon_h": a.get("horizon_h") if isinstance(a.get("horizon_h"), int) else None,
                        "attendu_pct": _pct_str(a.get("expected_move_pct")), "confiance_pct": _pct_str(a.get("confidence_pct")),
                        "invalidation": _texte(a.get("invalidation"), INVALIDATION_MAX),
                        "ecartee": False, "verdict": None, "execution": None, "fills": [],
                    })  # fmt: skip
                for _ in range(n_ecartees):
                    d["actions"].append({"instrument": "?", "action": None, "ecartee": True, "verdict": None, "execution": None, "fills": []})
            courante = d
            d["_libres"] = [a for a in d["actions"] if not a["ecartee"]]
        elif t == "agent_orders_set":
            d = ronde(p["round"], e["ts"])
            al = [x for x in p.get("alerts") or [] if isinstance(x, Mapping)]
            en = [x for x in p.get("entry_orders") or [] if isinstance(x, Mapping)]
            for o in en:
                ordres[str(o.get("id"))] = o
            rej = [x for x in p.get("rejected") or [] if isinstance(x, Mapping)]
            d["pose"] = {
                "elements": [_element("alert", x) for x in al] + [_element("entry", x) for x in en],
                "refus": [{"type": "alerte" if x.get("kind") == "alert" else "ordre", "motif": _rejet_public(x.get("error"))} for x in rej],
            }  # fmt: skip
        elif t == "agent_entry_triggered" and str(p.get("id")) in ordres:
            declenche(str(p["id"]), e["ts"], p)
        elif t == "perp_verdict" and str(p.get("intent_id")) in ordres:
            a = declenche(str(p["intent_id"]), e["ts"], None)["actions"][0]
            a["verdict"] = {"approuve": bool(p.get("approved")), "motifs": [str(c) for c in p.get("reasons") or []]}
        elif t == "perp_verdict" and courante is not None:
            libres = courante.get("_libres") or []
            a = next((x for x in libres if x["verdict"] is None and x["instrument"] == court(p.get("instrument")) and x["action"] == p.get("action")), None)
            a = a or next((x for x in libres if x["verdict"] is None), None)
            if a is not None:
                a["verdict"] = {"approuve": bool(p.get("approved")), "motifs": [str(c) for c in p.get("reasons") or []]}
                par_intent[str(p.get("intent_id"))] = a
        elif t == "perp_execution":
            if str(p.get("intent_id")) in ordres:
                declenche(str(p["intent_id"]), e["ts"], None)
            a = par_intent.get(str(p.get("intent_id")))
            if a is None and courante is not None:
                a = next((x for x in courante.get("_libres") or [] if x["execution"] is None and x["instrument"] == court(p.get("instrument"))), None)
                if a is not None:
                    par_intent[str(p.get("intent_id"))] = a
            if a is not None:
                a["execution"] = str(p.get("status") or "")
        elif t == "perp_fill":
            oid = str(p.get("order_id") or "")
            a = par_intent.get(oid) or par_intent.get(oid.removesuffix(":no-stop"))
            if a is not None:
                a["fills"].append({"prix_uusd": p["price_uusd"], "qty": p["qty"], "frais_ueur": p.get("fee_ueur") or 0, "raison": p.get("reason")})
    for d in rondes.values():
        d.pop("_libres", None)
    return sorted([*rondes.values(), *declenches.values()], key=lambda d: (d["ts"] if d["kind"] == "ordre" else d["round"]), reverse=True)


def _decisions_aleatoire(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Les tirages du témoin aléatoire, par ronde (ses verdicts suivent le `perp_round` dans le journal)."""
    rondes: dict[int, dict[str, Any]] = {}
    cur: dict[str, Any] | None = None
    for e in events:
        t, p = e["type"], e["payload"]
        if t == "perp_round":
            cur = rondes.setdefault(p["round"], {
                "round": p["round"], "ts": e["ts"], "kind": p.get("kind") or "rendezvous",
                "declencheur": _declencheur(p.get("trigger"), "wakeup") if p.get("kind") == "wakeup" else None,
                "statut": "decidee", "actions": [],
            })  # fmt: skip
        elif t == "perp_verdict" and p.get("portfolio") == ALEATOIRE and cur is not None:
            cur["actions"].append({
                "instrument": court(p.get("instrument")), "action": p.get("action"), "ecartee": False,
                "verdict": {"approuve": bool(p.get("approved")), "motifs": [str(c) for c in p.get("reasons") or []]},
                "execution": None, "fills": [], "_id": str(p.get("intent_id")),
            })  # fmt: skip
        elif t == "perp_fill" and p.get("portfolio") == ALEATOIRE and cur is not None:
            for a in cur["actions"]:
                if a["_id"] == p.get("order_id"):
                    a["fills"].append({"prix_uusd": p["price_uusd"], "qty": p["qty"], "frais_ueur": p.get("fee_ueur") or 0, "raison": p.get("reason")})
                    a["execution"] = "filled"
    out = [r for r in rondes.values() if r["actions"]]
    for r in out:
        for a in r["actions"]:
            a.pop("_id", None)
    return sorted(out, key=lambda d: d["round"], reverse=True)[:DECISIONS_MAX]


def compute(path: Path, now: int) -> dict[str, Any] | None:
    """Tout ce que le site montre de la ligue dérivés, ou None si son journal n'existe pas (encore)."""
    path = Path(path)
    if not path.exists():
        return None
    events = list(Journal(path).iter_events(strict=False))
    opened = {e["payload"]["portfolio"]: e for e in events if e["type"] == "portfolio_opened" and e["payload"].get("league", "perp") == "perp"}
    if not opened:
        return None
    report = verify(path)
    try:
        accounts = replay(events)
    except PerpLedgerError:
        accounts = {}
    series = _series(events)
    last_eq: dict[str, Mapping[str, Any]] = {}
    for e in events:
        if e["type"] == "perp_equity":
            last_eq[e["payload"]["portfolio"]] = e["payload"]

    funding: dict[str, list[int]] = {}
    fills: dict[str, list[dict[str, Any]]] = {}
    statut: dict[str, dict[str, Any]] = {}
    for e in events:
        t, p = e["type"], e["payload"]
        pf = p.get("portfolio")
        if t == "funding":
            funding.setdefault(pf, []).append(int(p.get("amount_ueur") or 0))
        elif t == "perp_fill":
            fills.setdefault(pf, []).append({
                "ts": e["ts"], "instrument": court(p.get("instrument")), "qty": p["qty"], "prix_uusd": p["price_uusd"],
                "frais_ueur": p.get("fee_ueur") or 0, "raison": RAISONS_FILL.get(str(p.get("reason")), str(p.get("reason"))),
            })  # fmt: skip
        elif t == "portfolio_halted":
            statut[pf] = {"etat": "arrete", "jusqu": None}
        elif t == "portfolio_frozen":
            statut[pf] = {"etat": "gele", "jusqu": p.get("until_ts")}
        elif t == "portfolio_resumed":
            statut.pop(pf, None)

    llm_ids = sorted((pf for pf, e in opened.items() if e["payload"].get("kind") == "llm"), key=lambda x: (ORDRE.index(x) if x in ORDRE else 99, x))
    tem_ids = sorted((pf for pf, e in opened.items() if e["payload"].get("kind") != "llm"), key=lambda x: (ORDRE.index(x) if x in ORDRE else 99, x))

    portfolios = []
    for pf in llm_ids + tem_ids:
        o = opened[pf]["payload"]
        capital = int(o["capital_ueur"])
        le = last_eq.get(pf)
        equity = int(le["equity_ueur"]) if le else capital
        gross = int(le.get("gross_ueur") or 0) if le else 0
        fx = (int(le["fx_bid"]), int(le["fx_ask"])) if le and le.get("fx_bid") and le.get("fx_ask") else None
        dd_max, dd = _drawdowns(series.get(pf, []))
        f = funding.get(pf, [])
        acc = accounts.get(pf)
        kind = "llm" if o.get("kind") == "llm" else "temoin"
        st = statut.get(pf)
        if st and st["etat"] == "gele" and (st["jusqu"] or 0) <= now:
            st = None
        p_out: dict[str, Any] = {
            "id": pf, "slug": slug(pf), "name": nom(pf), "kind": kind, "description": DESCRIPTIONS.get(pf),
            "ouvert_ts": opened[pf]["ts"],
            "capital_ueur": capital, "equity_ueur": equity, "rendement": equity / capital - 1 if capital else None,
            "drawdown_max": dd_max, "drawdown": dd, "levier": gross / equity if equity > 0 else None,
            "expo_ueur": gross, "positions": _positions(acc, (le or {}).get("marks") or {}, fx),
            "frais_ueur": acc.fees_paid_ueur if acc else sum(x["frais_ueur"] for x in fills.get(pf, [])),
            "funding_paye_ueur": sum(x for x in f if x > 0), "funding_recu_ueur": -sum(x for x in f if x < 0),
            "funding_net_ueur": sum(f), "n_operations": len(fills.get(pf, [])), "statut": st,
            "operations": list(reversed(fills.get(pf, [])))[:OPERATIONS_MAX], "decisions": [],
            "cout_uusd": None, "n_rondes": 0, "n_ordres": 0, "fx": list(fx) if fx else None,
        }  # fmt: skip
        if kind == "llm":
            ds = _decisions_llm(events, pf)  # toutes : les totaux portent sur le journal entier
            p_out["decisions"] = ds[:DECISIONS_MAX]
            p_out["n_decisions_total"] = len(ds)
            p_out["cout_uusd"] = sum(d["cout_uusd"] or 0 for d in ds)
            p_out["n_rondes"] = sum(1 for d in ds if d["statut"] == "decidee")
            p_out["n_declenches"] = sum(1 for d in ds if d["kind"] == "ordre")
            try:
                p_out["attente"] = _attente(events, pf)
            except (KeyError, TypeError, ValueError):  # un événement mal formé ne casse pas la page
                p_out["attente"] = None
            p_out["n_ordres"] = sum(1 for d in ds for a in d["actions"] if a["fills"])
        elif pf == ALEATOIRE:
            p_out["decisions"] = _decisions_aleatoire(events)
        portfolios.append(p_out)

    # Courbe : base 100 au capital, un point toutes les 30 min et le dernier relevé.
    all_ts = sorted({ts for s in series.values() for ts, _e, _g in s})
    xs: list[int] = []
    for ts in all_ts:
        if not xs or ts // PAS_COURBE_S != xs[-1] // PAS_COURBE_S:
            xs.append(ts)
        else:
            xs[-1] = ts if ts == all_ts[-1] else xs[-1]
    if all_ts and xs[-1] != all_ts[-1]:
        xs.append(all_ts[-1])
    chart_series = []
    for p_out in portfolios:
        s = series.get(p_out["id"], [])
        vals: list[float | None] = []
        j, last = 0, None
        for x in xs:
            while j < len(s) and s[j][0] <= x:
                last = s[j][1]
                j += 1
            vals.append(None if last is None else round(last / p_out["capital_ueur"] * 100, 4))
        chart_series.append({"id": p_out["id"], "name": p_out["name"], "kind": "llm" if p_out["kind"] == "llm" else "temoin", "values": vals})
    debut = min((e["ts"] for e in opened.values()), default=None)
    chart = {"x": xs, "kinds": ["veille"] * len(xs), "series": chart_series}

    rounds = [e for e in events if e["type"] == "perp_round"]
    done = {e["payload"]["round"] for e in events if e["type"] == "perp_round_done"}
    live_ts = max(last_eq[pf]["ts"] for pf in last_eq) if last_eq else None
    return {
        "venue_mode": next((e["payload"].get("venue_mode", "paper") for e in opened.values()), "paper"),
        "ouverte_ts": debut, "live_ts": live_ts, "prochain_rdv_ts": prochain_rendez_vous(now),
        "n_rondes": len(done), "derniere_ronde_ts": max((e["payload"]["round"] for e in rounds), default=None),
        "llm_presents": bool(llm_ids), "portfolios": portfolios, "chart": chart,
        "journal": {"verify_ok": report.ok, "n_records": report.n_records},
    }
