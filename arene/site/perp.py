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
from arene.perp import round_quota
from arene.perp.ledger import MarginAccount, PerpLedgerError, price_pnl_uusd, replay, to_eur
from arene.perp.llm_league import LlmConfigError, load_llm_league
from arene.perp.news import load_news_config

ROUND_S = 4 * 3600
ROUND_OFFSET_S = 2 * 3600  # rendez-vous à 02:00, 06:00, …, 22:00 UTC
PAS_COURBE_S = 1_800  # un point toutes les 30 min sur la courbe (plus le dernier relevé)
DECISIONS_MAX = 120
DELIBERATIONS_MAX = 48  # avis du conseil publiés pour ses 48 dernières rondes (8 h à 10 min) ; les autres : le journal
OPERATIONS_MAX = 60
JUSTIFICATION_MAX = 1_200
INVALIDATION_MAX = 200
NOTE_MAX = 160
TITRE_MAX = 120
ACTU_S = 7 * 86_400  # fenêtre des actualités : 7 jours devant (calendrier) et derrière (annonces de Kraken)
ANNONCES_MAX = 12
IMPACTS = {"minor": "mineur", "major": "majeur", "critical": "critique"}

PANIER = "benchmark-perp:basket-1x"
TENDANCE = "benchmark-perp:trend"
ALEATOIRE = "benchmark-perp:random"
CONSEIL = "council-perp:haiku"  # le Conseil Haiku : Président Haiku
CONSEIL_OPUS = "council-perp:opus"  # le Conseil Opus : mêmes dix conseillers Haiku, Président Opus
CONSEIL_TENDANCE = "council-perp:tendance"  # le Conseil Tendance (v4) : le moteur décide, les LLM freinent
MOTEUR = "benchmark-perp:moteur-tendance"  # son témoin : le même moteur, sans LLM
PREFIXE_CONSEIL = "council-perp:"
OBJECTIF_JOUR_PCT = 1  # l'objectif fixé, revu le 17/11/2026 : « On va plutôt dire 1% par jour » (d'abord 10 %)

NOMS = {
    "llm-perp:claude-haiku-5-5": "Claude Haiku 5.5",
    "llm-perp:claude-sonnet-5-5": "Claude Sonnet 5.5",
    "llm-perp:claude-opus-5-5": "Claude Opus 5.5",
    "llm-perp:claude-fable-5-2": "Claude Fable 5.2",
    CONSEIL: "Conseil Haiku",
    CONSEIL_OPUS: "Conseil Opus",
    CONSEIL_TENDANCE: "Conseil Tendance",
    MOTEUR: "Témoin moteur seul",
    PANIER: "Témoin panier 1x",
    TENDANCE: "Témoin tendance",
    ALEATOIRE: "Témoin aléatoire",
}
ORDRE = list(NOMS)
SOUS_TITRES = {
    CONSEIL: "10 Haiku · président Haiku",
    CONSEIL_OPUS: "10 Haiku · président Opus",
    CONSEIL_TENDANCE: "moteur de tendance · 3 Haiku et un président Opus qui freinent",
}
BUDGETS_CONSEIL_USD = {CONSEIL: 10, CONSEIL_OPUS: 25, CONSEIL_TENDANCE: 5}  # budget du jour, en équivalent catalogue
DESCRIPTIONS = {
    CONSEIL: "Des Claude Haiku 5.5 délibèrent à chaque ronde : des avis indépendants, un avocat du diable, puis un Président Haiku qui décide.",
    CONSEIL_OPUS: "Les mêmes conseillers Haiku 5.5 délibèrent à chaque ronde ; c’est un Président Claude Opus 5.5 qui décide.",
    CONSEIL_TENDANCE: "Un moteur de suivi de tendance (moyennes mobiles 2 j / 6 j, long et short, taille réglée sur la volatilité, échelle 2x) donne la cible de chaque contrat à chaque barre de 4 h. Trois Haiku et un Président Opus peuvent seulement freiner : un coefficient de 1, 0,5 ou 0 par contrat.",
    MOTEUR: "Le même moteur de tendance à 2x, sans IA, par le même chemin d’exécution et sur les mêmes rondes de 4 h : l’écart avec le Conseil Tendance mesure ce que les IA ajoutent ou retirent.",
    PANIER: "Acheteur à parts égales des 6 contrats, sans levier ni stop, rééquilibré chaque mois : acheter et garder.",
    TENDANCE: "Chaque jour, long sur un contrat qui a monté sur 20 jours, short sinon ; 1/6 du portefeuille par contrat, stop à 10 %.",
    ALEATOIRE: "Tire 0 à 2 décisions au hasard à chaque rendez-vous, avec exactement les mêmes règles de risque que les IA.",
}

MARQUE_TENDANCE = "moteur de tendance · levier ≤ 10x · les IA ne peuvent que freiner"


def _objectif_jour(capital: int, equity: int, ouvert_ts: int, now: int) -> dict[str, Any]:
    """L'objectif fixé (1 %/jour) face au rendement par jour réalisé, côte à côte et sans fard : le taux journalier
    composé depuis l'ouverture (au moins un jour compté : un portefeuille de quelques heures montre son rendement du jour)."""
    jours = max((now - ouvert_ts) / 86_400, 1.0)
    realise = (equity / capital) ** (1 / jours) - 1 if capital > 0 and equity > 0 else -1.0
    return {"objectif_pct": OBJECTIF_JOUR_PCT, "realise_pct": round(100 * realise, 3), "jours": round(jours, 1)}


# Le Conseil Haiku (docs/SPEC-PERP-CONSEIL-HAIKU.md) : une catégorie à part, jamais classée avec les 4 LLM neutres.
MARQUE_CONSEIL = "levier ≤ 10x"
HORS_REGLE_CONSEIL = "Démonstration paper, hors de la règle des particuliers (2x) : ne pourrait pas passer au réel telle quelle."
# Les membres dans l'ordre des étapes : A (avis sans se voir), B (l'Avocat lit A), C (le Président tranche).
# (nom, étape, rôle, sources publiques de la consigne)
MEMBRES = {
    "cartographe": ("Le Cartographe", "A", "le régime de chaque contrat", "crypto-regime-analyzer ; analyste technique de TradingAgents"),
    "suiveur": ("Le Suiveur", "A", "la tendance à suivre", "breakout-trade-planner"),
    "chasseur": ("Le Chasseur de cassures", "A", "le mouvement qui démarre", "breakout-trade-planner (momentum burst)"),
    "contrarien": ("Le Contrarien", "A", "le consensus surchargé", "contrarian-setup-gate ; chercheur baissier de TradingAgents"),
    "arbitragiste": ("L’Arbitragiste de paires", "A", "la valeur relative : long le fort, short le faible", "pair-trade-screener"),
    "carnet": ("Le Lecteur de carnet", "A", "le carnet et le coût d’entrée", "HyperGrok (analystes, exécution)"),
    "tresorier": ("Le Trésorier du levier", "A", "la taille et le levier", "position-sizer, futures-position-sizer"),
    "gardien": ("Le Gardien du risque", "A", "les stops et la distance à la ruine", "drawdown-circuit-breaker, pre-trade-discipline-gate ; risk manager de HyperGrok"),
    "memorialiste": ("Le Mémorialiste", "A", "ce que le conseil a déjà raté ou réussi", "signal-postmortem ; Trade Reviewer de HyperGrok"),
    "avocat": ("L’Avocat du diable", "B", "attaque le trade le plus soutenu", "chercheur baissier et débat de TradingAgents"),
    "president": ("Le Président", "C", "tranche et décide", "Portfolio Manager de TradingAgents ; Desk Lead de HyperGrok"),
}
# Les trois conseillers du Conseil Tendance (v4) : ils ne peuvent que proposer de freiner le moteur.
MEMBRES_V4 = {
    "veilleur": ("Le Veilleur d’actualités", "A", "annonces de Kraken et publications macro", "consigne v4"),
    "controleur": ("Le Contrôleur de données", "A", "prix incohérents, trous, vue périmée", "consigne v4"),
    "avocat_risque": ("L’Avocat du risque", "A", "concentration et drawdown", "consigne v4"),
}
ORDRE_MEMBRES = list(MEMBRES)
TOUS_MEMBRES = {**MEMBRES, **MEMBRES_V4}
ORDRE_TOUS = list(TOUS_MEMBRES)
ARGUMENT_MAX = 700

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
    "retired": "conseil archivé, positions fermées",
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

FINS = {"expired": "expiré", "replaced": "remplacé", "portfolio_halted": "annulé (portefeuille arrêté)", "portfolio_retired": "annulé (conseil archivé)"}
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
    "LIQUIDATION_BEFORE_STOP": "liquidation atteinte avant le stop",
    "INTERNAL_ERROR": "erreur interne du garde-fou",
}

# Les mêmes codes, aux bornes de la politique du conseil (config/policy-perp-conseil.toml).
CODES_CONSEIL = {
    **CODES,
    "DAILY_TRADES": "24 ouvertures déjà faites en 24 h",
    "MAX_ORDER_SIZE": "ordre au-delà de 500 % du portefeuille",
    "MAX_POSITION": "position au-delà de 1 000 % du portefeuille",
    "MAX_LEVERAGE": "levier au-delà de 10",
    "MAX_TRADE_LOSS": "perte au stop au-delà de 25 % du portefeuille",
    "MAX_OPEN_RISK": "pertes cumulées aux stops au-delà de 60 %",
}
# Et aux bornes de la politique du Conseil Tendance et de son témoin (config/policy-perp-conseil-v4.toml).
CODES_TENDANCE = {
    **CODES_CONSEIL,
    "DAILY_TRADES": "48 ouvertures ou ajustements déjà faits en 24 h",
    "MAX_ORDER_SIZE": "ordre au-delà de 400 % du portefeuille",
    "MAX_POSITION": "position au-delà de 500 % du portefeuille",
    "MAX_OPEN_RISK": "pertes cumulées aux stops au-delà de 59 %",
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
    if portfolio not in NOMS and portfolio.startswith(PREFIXE_CONSEIL):  # un conseil que le site ne connaît pas encore
        reste = re.sub(r"[^A-Za-z0-9]+", " ", portfolio[len(PREFIXE_CONSEIL):]).strip()
        return f"Conseil {reste[:1].upper()}{reste[1:]}" if reste else "Conseil"
    return NOMS.get(portfolio, portfolio.split(":", 1)[-1])


def _modele(v: Any) -> str | None:
    """« claude-opus-5-5 » -> « Opus » ; None si le modèle n'est pas reconnu."""
    s = str(v).lower() if isinstance(v, str) else ""
    return next((label for k, label in (("opus", "Opus"), ("sonnet", "Sonnet"), ("haiku", "Haiku"), ("fable", "Fable")) if k in s), None)


def _entier(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


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


def _rejet_public(error: Any, kind: Any = None) -> str:
    """Catégorie fixe d'un élément refusé à la création (le texte brut n'est pas publié)."""
    if kind == "wakeup":
        return "réveil demandé invalide"
    s = str(error or "").lower()
    if "25 %" in s or "away from the mark" in s:
        return "niveau à plus de 25 % du prix"
    if "already crossed" in s:
        return "niveau déjà franchi"
    return "élément invalide"


def _ts(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None


def _news(d: Mapping[str, Any]) -> dict[str, Any] | None:
    """Les actualités jointes à un déclencheur : publications macro (id, libellé, heure) et annonces de Kraken
    (nature, statut, titre). Textes bornés ; la clé interne n'est pas publiée."""
    rel = d.get("releases")
    ann = d.get("announcements")
    releases = [
        {"label": _texte(r.get("label"), 120) or "publication macro", "ts": _ts(r.get("ts"))}
        for r in (rel if isinstance(rel, list) else []) if isinstance(r, Mapping)
    ]  # fmt: skip
    annonces = [
        {"kind": str(a.get("kind") or "")[:20], "status": str(a.get("status") or "")[:20], "title": _texte(a.get("title"), TITRE_MAX) or "annonce"}
        for a in (ann if isinstance(ann, list) else []) if isinstance(a, Mapping)
    ]  # fmt: skip
    return {"releases": releases[:3], "annonces": annonces[:3]} if releases or annonces else None


def _declencheur(raw: Any, kind: str = "wakeup") -> dict[str, Any] | None:
    """Le déclencheur d'une ronde hors rendez-vous. Réveil de marché : contrat et variation. Alerte de l'IA :
    contrat, sens, niveau et sa note. Annonce de Kraken ou publication macro : titres et libellés. Le reste (id,
    fenêtre interne) n'est pas publié. Tout déclencheur peut porter des actualités (`news`)."""
    d = raw
    if isinstance(raw, str):
        try:
            d = json.loads(raw)
        except ValueError:
            return None
    if not isinstance(d, Mapping):
        return None
    out = _declencheur_nu(d, kind)
    sous = d.get("news") if isinstance(d.get("news"), Mapping) else None
    n = _news(sous) if sous else None
    if n:
        out["news"] = n
    return out


def _declencheur_nu(d: Mapping[str, Any], kind: str) -> dict[str, Any]:
    if kind == "news":
        return {"type": "annonce", **(_news(d) or {"releases": [], "annonces": []})}
    if kind == "calendar":
        return {"type": "publication", **(_news(d) or {"releases": [], "annonces": []})}
    if kind == "scheduled":
        due = d.get("due_ts")
        return {"type": "demande", "due_ts": due if isinstance(due, int) and not isinstance(due, bool) else None}
    if kind == "cadence":
        return {"type": "cadence"}
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


def _absence_publique(error: Any) -> str:
    """Pourquoi un membre du conseil n'a pas rendu d'avis, par catégorie (jamais le texte brut)."""
    s = str(error or "").lower()
    if "timeout" in s or "timed out" in s:
        return "délai dépassé"
    if "budget" in s:
        return "plafond de coût atteint"
    if "crash" in s:
        return "erreur interne"
    if "no opinion" in s or "no structured output" in s:
        return "pas d’avis rendu"
    if "expected" in s or "avis" in s or "unexpected" in s or "out of" in s or "not a number" in s:
        return "avis invalide"
    return "échec de l’appel"


def _nombre(v: Any) -> float | None:
    """Nombre décimal en texte (avis du conseil) ; None s'il est absent ou illisible."""
    if v is None or isinstance(v, bool):
        return None
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        return None
    if not d.is_finite() or abs(d) > 10**12:  # « 1e400 » : illisible, pas l'infini
        return None
    return float(d)


def _avis_membre(p: Mapping[str, Any]) -> dict[str, Any]:
    """Un `council_opinion` tel que le site le montre : position, conviction, taille, stop et niveau par contrat."""
    key = str(p.get("member") or "")
    nom_m, etape, role, _src = TOUS_MEMBRES.get(key, (_texte(p.get("name"), 60) or "Membre", str(p.get("stage") or "A"), None, None))
    op = p.get("opinion") if isinstance(p.get("opinion"), Mapping) else None
    out: dict[str, Any] = {
        "membre": key, "nom": nom_m, "etape": etape, "role": role, "absent": op is None,
        "erreur": _absence_publique(p.get("error")) if op is None else None,
        "avis": [], "cible": None, "argument": None, "outils": [],
    }  # fmt: skip
    if op is None:
        return out
    avis = op.get("avis")
    for a in avis if isinstance(avis, list) else []:
        if not isinstance(a, Mapping) or a.get("position") not in ("long", "short", "plat"):
            continue
        conv = a.get("conviction")
        niv = _nombre(a.get("niveau_cle_usd"))
        out["avis"].append({
            "instrument": court(a.get("instrument")), "position": a["position"],
            "conviction": conv if isinstance(conv, int) and not isinstance(conv, bool) and 0 <= conv <= 100 else None,
            "taille_pct": _nombre(a.get("taille_pct")), "stop_pct": _nombre(a.get("stop_pct")),
            "niveau_uusd": round(niv * 1_000_000) if niv is not None else None,
        })  # fmt: skip
    c = op.get("cible")
    if isinstance(c, Mapping) and c.get("sens") in ("long", "short"):
        out["cible"] = {"instrument": court(c.get("instrument")), "sens": c["sens"]}
    out["argument"] = _texte(op.get("argument"), ARGUMENT_MAX)
    props = op.get("propositions")
    if isinstance(props, list):  # un conseiller du Conseil Tendance : des freinages proposés (0 ou 0,5), jamais un avis de marché
        out["propositions"] = [
            {"instrument": court(x.get("instrument")), "coefficient": x.get("coefficient") if x.get("coefficient") in ("0", "0.5") else None,
             "raison": _texte(x.get("raison"), 200)}
            for x in props if isinstance(x, Mapping)
        ]  # fmt: skip
    return out


COEFFICIENTS = ("0", "0.5", "1")


def _tendance_ronde(t: Any) -> dict[str, Any] | None:
    """Ce que le Conseil Tendance a fait d'une ronde (`agent_decision.trend`) : les cibles du moteur (en % du
    portefeuille, signées), les coefficients du conseil avec leur raison, et si le conseil a été appelé. Rien d'autre."""
    if not isinstance(t, Mapping):
        return None

    def pcts(raw: Any) -> dict[str, float]:
        return {court(k): v / 100 for k, v in (raw or {}).items() if isinstance(v, int) and not isinstance(v, bool)} if isinstance(raw, Mapping) else {}

    coefs = {}
    for k, c in (t.get("coefficients") or {}).items() if isinstance(t.get("coefficients"), Mapping) else ():
        if isinstance(c, Mapping) and c.get("c") in COEFFICIENTS:
            coefs[court(k)] = {"coefficient": c["c"], "raison": _texte(c.get("why"), 200), "jusqu_a_ts": _entier(c.get("until_ts"))}
    off = t.get("council_off")
    return {
        "type": t.get("kind") if t.get("kind") in ("barre", "veto", "restauration") else None,
        "barre_ts": _entier(t.get("bar_end_ts")), "cibles_pct": pcts(t.get("targets_bp")), "finales_pct": pcts(t.get("final_bp")),
        "coefficients": coefs, "conseil_appele": bool(t.get("council_called")),
        "conseil_absent": {"nothing_to_brake": "rien à freiner", "daily_budget": "budget du jour atteint", "llm_league_off": "IA coupées", "restauration": "fin d’un freinage", "spot_cycle": "cycle de la ligue comptant trop proche"}.get(str(off)) if off else None,
        "president_ok": bool(t.get("president_ok")),
        "donnees_incompletes": sorted(court(k) for k in t.get("held") or {}) if isinstance(t.get("held"), Mapping) else [],
    }  # fmt: skip


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
                "latence_ms": None, "jetons": None, "pose": None, "rappel_ts": None, "conseil": None,
            }  # fmt: skip
            par_intent[oid] = action
        return declenches[oid]

    def ronde(r: int, ts: int) -> dict[str, Any]:
        if r not in rondes:
            rondes[r] = {
                "round": r, "ts": ts, "kind": "rendezvous", "declencheur": None, "statut": "en_cours", "saut": None,
                "justification": None, "actions": [], "outils": [], "erreur": None, "cout_uusd": None,
                "latence_ms": None, "jetons": None, "pose": None, "rappel_ts": None, "conseil": None, "tendance": None,
            }  # fmt: skip
        return rondes[r]

    def conseil(d: dict[str, Any]) -> dict[str, Any]:
        if d["conseil"] is None:
            d["conseil"] = {
                "avis": [], "membres_ok": None, "membres_absents": None, "president": None, "cout_president_uusd": None,
                "modele_membres": None, "consignes": None, "_outils": {},
            }
        return d["conseil"]

    for e in events:
        t, p = e["type"], e["payload"]
        if p.get("portfolio") != pf:
            continue
        if t == "round_data":
            d = ronde(p["round"], e["ts"])
            d["kind"] = p.get("kind") or "rendezvous"
            d["declencheur"] = _declencheur(p.get("trigger"), d["kind"]) if d["kind"] in ("wakeup", "alert", "scheduled", "cadence", "news", "calendar") else None
            if d["kind"] == "veto":  # une ronde de veto du Conseil Tendance : son déclencheur est un réveil, une annonce ou une publication
                try:
                    brut = json.loads(p.get("trigger")) if isinstance(p.get("trigger"), str) else p.get("trigger")
                    k = brut.get("kind") if isinstance(brut, Mapping) and brut.get("kind") in ("wakeup", "news", "calendar") else "wakeup"
                    d["declencheur"] = _declencheur(brut, k)
                except ValueError:
                    d["declencheur"] = None
        elif t == "tool_call":
            d = ronde(p["round"], e["ts"])
            tool = str(p.get("tool") or "").removeprefix("mcp__arene__")
            if tool in OUTILS:
                o = {"outil": tool, "args": _outil_args(tool, p.get("arguments")), "erreur": bool(p.get("is_error"))}
                membre = p.get("member")
                if membre and membre != "president":  # un membre du conseil : ses outils vont à son avis
                    conseil(d)["_outils"].setdefault(str(membre), []).append(o)
                else:
                    d["outils"].append(o)
        elif t == "council_opinion":
            c = conseil(ronde(p["round"], e["ts"]))
            a = _avis_membre(p)
            # Un même membre rejoué dans la même ronde : le dernier avis compte, une seule fois.
            c["avis"] = [x for x in c["avis"] if not (a["membre"] and x["membre"] == a["membre"])] + [a]
        elif t == "perp_llm_skipped":
            d = ronde(p["round"], e["ts"])
            reason = str(p.get("reason") or "")
            d["statut"], d["saut"] = "sautee", SAUTS.get(reason, "préparation impossible" if reason.startswith("prepare_error") else "sautée")
        elif t == "agent_decision":
            d = ronde(p["round"], e["ts"])
            d["kind"] = p.get("kind") or d["kind"]
            parsed = p.get("parsed") if isinstance(p.get("parsed"), Mapping) else None
            d["cout_uusd"] = p.get("cost_uusd")  # pour un conseil : le coût réel de la ronde (membres et Président)
            cs = p.get("council")
            if isinstance(cs, Mapping):
                c = conseil(d)
                c["membres_ok"] = cs.get("members_ok") if isinstance(cs.get("members_ok"), int) else None
                mf = cs.get("members_failed")
                c["membres_absents"] = len(mf) if isinstance(mf, list) else None
                # Champs plus récents : absents des anciennes décisions (Président Haiku, consignes v1).
                c["president"] = "Haiku" if cs.get("president_model") is None else _modele(cs.get("president_model"))
                c["cout_president_uusd"] = _entier(cs.get("president_cost_uusd"))
                c["modele_membres"] = "Haiku" if cs.get("members_model") is None else _modele(cs.get("members_model"))
                v = cs.get("prompts_version")
                c["consignes"] = "v1" if v is None else (v if isinstance(v, str) and re.fullmatch(r"v\d{1,3}", v) else None)
            d["tendance"] = _tendance_ronde(p.get("trend"))
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
                "refus": [{"type": {"alert": "alerte", "wakeup": "reveil"}.get(str(x.get("kind")), "ordre"), "motif": _rejet_public(x.get("error"), x.get("kind"))} for x in rej],
            }  # fmt: skip
        elif t == "agent_wakeup_set":
            d = ronde(p["round"], e["ts"])
            due = p.get("due_ts")
            d["rappel_ts"] = due if isinstance(due, int) and not isinstance(due, bool) else None
        elif t == "agent_entry_triggered" and str(p.get("id")) in ordres:
            declenche(str(p["id"]), e["ts"], p)
        elif t == "perp_verdict" and str(p.get("intent_id")) in ordres:
            a = declenche(str(p["intent_id"]), e["ts"], None)["actions"][0]
            a["verdict"] = {"approuve": bool(p.get("approved")), "motifs": [str(c) for c in p.get("reasons") or []]}
        elif t == "perp_verdict" and courante is not None and p.get("retry_of") is not None:
            a = par_intent.get(str(p["retry_of"]))  # l'entrée refusée pour sa taille, retentée plus petite : la même action
            if a is not None:
                a["verdict"] = {"approuve": bool(p.get("approved")), "motifs": [str(c) for c in p.get("reasons") or []]}
                a["reduite"] = (a.get("reduite") or 0) + 1
                par_intent[str(p.get("intent_id"))] = a
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
        c = d.get("conseil")
        if c is not None:
            outils = c.pop("_outils")
            for a in c["avis"]:
                a["outils"] = outils.get(a["membre"], [])
            c["avis"].sort(key=lambda a: ORDRE_TOUS.index(a["membre"]) if a["membre"] in TOUS_MEMBRES else 99)
    return sorted([*rondes.values(), *declenches.values()], key=lambda d: (d["ts"] if d["kind"] == "ordre" else d["round"]), reverse=True)


def _rythme(
    events: list[dict[str, Any]], pf: str, now: int, ds: list[dict[str, Any]], ligue: Any, st: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Quand l'IA sera rappelée : le réveil qu'elle a demandé (calcul du moteur), l'appel régulier au plus tard
    (cadence après sa dernière ronde), et ses rondes du jour face au quota."""
    if ligue is None:
        return None
    out: dict[str, Any] = {"cadence_min": ligue.cadence_min, "reveil_ts": None, "prochain_ts": None, "quota": None}
    try:
        w = AO.pending_wakeup(events, pf, now)
        out["reveil_ts"] = w["due_ts"] if w else None
        out["quota"] = round_quota.quota(events, pf, now, ligue.rounds_per_day, ROUND_OFFSET_S)
    except (KeyError, TypeError, ValueError):
        pass
    arrete = bool(st and st["etat"] == "arrete")
    derniere = max((d["ts"] for d in ds if d["kind"] != "ordre"), default=None)
    if ligue.enabled and ligue.cadence_min > 0 and derniere is not None and not arrete:
        out["prochain_ts"] = derniere + ligue.cadence_min * 60
    return out


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


def _calendrier(now: int) -> list[dict[str, Any]] | None:
    """Les publications macro des 7 prochains jours (calendrier publié d'avance), ou None si la configuration
    des actualités n'est pas lisible : le site omet alors le calendrier."""
    try:
        cfg = load_news_config()
        out = [
            {"id": str(c.id), "kind": c.kind, "label": _texte(c.label, 120) or c.kind.upper(), "ts": c.ts, "rappel": c.kind in cfg.wake_kinds}
            for c in cfg.calendar if now <= c.ts <= now + ACTU_S
        ]  # fmt: skip
    except Exception:  # noqa: BLE001 - jamais de page cassée pour une configuration absente ou mal formée
        return None
    return sorted(out, key=lambda c: (c["ts"], c["id"]))


def _annonces(events: list[dict[str, Any]], now: int) -> list[dict[str, Any]]:
    """Les annonces de Kraken sur les dérivés vues depuis 7 jours : la dernière version de chacune (source, id)."""
    last: dict[tuple[str, str], tuple[int, Mapping[str, Any]]] = {}
    for e in events:
        if e["type"] == "news_item" and isinstance(e["payload"], Mapping):
            p = e["payload"]
            last[(str(p.get("source")), str(p.get("id")))] = (
                e["ts"],
                p,
            )  # le journal est ordonné : la dernière version gagne
    out = []
    for ts, p in last.values():
        maj = max(
            _ts(p.get("updated_ts")) or 0, _ts(p.get("published_ts")) or 0, _ts(p.get("fetched_ts")) or 0, ts
        )
        a_venir = (_ts(p.get("starts_ts")) or 0) > now or (_ts(p.get("ends_ts")) or 0) > now
        if maj < now - ACTU_S and not a_venir:
            continue
        url = p.get("url")
        ins = p.get("instruments")
        out.append({
            "kind": str(p.get("kind") or "")[:20], "status": str(p.get("status") or "")[:24], "impact": str(p.get("impact") or "")[:20],
            "title": _texte(p.get("title"), TITRE_MAX) or "Annonce de Kraken", "maj_ts": maj,
            "starts_ts": _ts(p.get("starts_ts")), "ends_ts": _ts(p.get("ends_ts")),
            "instruments": [court(i) for i in ins[:8]] if isinstance(ins, list) else [],
            "url": url if isinstance(url, str) and url.startswith("https://") and len(url) <= 200 else "",
        })  # fmt: skip
    return sorted(out, key=lambda a: a["maj_ts"], reverse=True)[:ANNONCES_MAX]


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
    retires: dict[str, dict[str, Any]] = {}  # portefeuilles archivés (portfolio_retired) : leurs données sont figées
    for e in events:
        t, p = e["type"], e["payload"]
        pf = p.get("portfolio")
        if t == "portfolio_retired" and pf not in retires:
            # the operator's free-text note stays in the journal: it may name people (never published)
            retires[pf] = {"ts": e["ts"], "raison": _texte(p.get("reason"), 80)}
        if t == "funding":
            funding.setdefault(pf, []).append(int(p.get("amount_ueur") or 0))
        elif t == "perp_fill":
            fills.setdefault(pf, []).append({
                "ts": e["ts"], "instrument": court(p.get("instrument")), "qty": p["qty"], "prix_uusd": p["price_uusd"],
                "frais_ueur": p.get("fee_ueur") or 0, "raison": RAISONS_FILL.get(str(p.get("reason")), str(p.get("reason"))),
            })  # fmt: skip
        elif t == "portfolio_halted":
            statut[pf] = {"etat": "arrete", "jusqu": None, "ts": e["ts"], "raison": p.get("reason")}
        elif t == "portfolio_frozen":
            statut[pf] = {"etat": "gele", "jusqu": p.get("until_ts"), "ts": e["ts"], "raison": p.get("reason")}
        elif t == "portfolio_resumed":
            statut.pop(pf, None)

    try:
        ligue_llm = load_llm_league()
    except (LlmConfigError, OSError, ValueError):  # sans configuration lisible, ni quota ni cadence affichés
        ligue_llm = None

    def rang(x: str) -> tuple[int, str]:
        return (ORDRE.index(x) if x in ORDRE else 99, x)

    def genre(o: Mapping[str, Any]) -> str:
        return {"llm": "llm", "council": "conseil"}.get(str(o.get("kind")), "temoin")

    par_genre = {g: sorted((pf for pf, e in opened.items() if genre(e["payload"]) == g), key=rang) for g in ("llm", "conseil", "temoin")}

    portfolios = []
    for pf in par_genre["llm"] + par_genre["conseil"] + par_genre["temoin"]:
        o = opened[pf]["payload"]
        capital = int(o["capital_ueur"])
        le = last_eq.get(pf)
        equity = int(le["equity_ueur"]) if le else capital
        gross = int(le.get("gross_ueur") or 0) if le else 0
        fx = (int(le["fx_bid"]), int(le["fx_ask"])) if le and le.get("fx_bid") and le.get("fx_ask") else None
        dd_max, dd = _drawdowns(series.get(pf, []))
        f = funding.get(pf, [])
        acc = accounts.get(pf)
        kind = genre(o)
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
            "archive": retires.get(pf),
        }  # fmt: skip
        if pf in (CONSEIL_TENDANCE, MOTEUR):
            p_out["objectif_jour"] = _objectif_jour(capital, equity, opened[pf]["ts"], now)
        if pf == MOTEUR:
            p_out["marque"] = MARQUE_TENDANCE
        if kind in ("llm", "conseil"):
            ds = _decisions_llm(events, pf)  # toutes : les totaux portent sur le journal entier
            if kind == "conseil":
                n_delib = 0
                for d in ds:
                    d["regles"] = "tendance" if pf == CONSEIL_TENDANCE else "conseil"  # ses refus se lisent aux bornes de sa propre politique
                    c = d.get("conseil")
                    n_delib += 1 if c else 0
                    if c and n_delib > DELIBERATIONS_MAX:  # la page reste légère : ~150 rondes par jour, 9 avis chacune
                        c["avis_hors_page"], c["avis"] = len(c["avis"]), []
                p_out["marque"], p_out["hors_regle"] = (MARQUE_TENDANCE if pf == CONSEIL_TENDANCE else MARQUE_CONSEIL), HORS_REGLE_CONSEIL
                p_out["sous_titre"] = SOUS_TITRES.get(pf)
                p_out["cout_president_uusd"] = sum((d.get("conseil") or {}).get("cout_president_uusd") or 0 for d in ds)
                p_out["president"] = next(((d["conseil"] or {}).get("president") for d in ds if d.get("conseil") and d["conseil"].get("president")), None)
                p_out["budget_usd"] = BUDGETS_CONSEIL_USD.get(pf)
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
            p_out["rythme"] = _rythme(events, pf, now, ds, ligue_llm, {"etat": "arrete"} if pf in retires else st)  # archivé : plus d'appel prévu
        elif pf == ALEATOIRE:
            p_out["decisions"] = _decisions_aleatoire(events)
        portfolios.append(p_out)

    rounds = [e for e in events if e["type"] == "perp_round"]
    done = {e["payload"]["round"] for e in events if e["type"] == "perp_round_done"}
    commun = {
        "venue_mode": next((e["payload"].get("venue_mode", "paper") for e in opened.values()), "paper"),
        "prochain_rdv_ts": prochain_rendez_vous(now),
        "n_rondes": len(done), "derniere_ronde_ts": max((e["payload"]["round"] for e in rounds), default=None),
        "journal": {"verify_ok": report.ok, "n_records": report.n_records},
        "cadence_min": ligue_llm.cadence_min if ligue_llm and ligue_llm.enabled else 0,
        "rondes_par_jour": ligue_llm.rounds_per_day if ligue_llm else None,
        "actualites": {"calendrier": _calendrier(now), "annonces": _annonces(events, now)},
    }  # fmt: skip

    def ligue(pfs: list[dict[str, Any]]) -> dict[str, Any]:
        """Une ligue : ses portefeuilles, sa courbe (base 100 au capital, un point toutes les 30 min et le dernier relevé)."""
        ids = {p["id"] for p in pfs}
        all_ts = sorted({ts for pf in ids for ts, _e, _g in series.get(pf, [])})
        xs: list[int] = []
        for ts in all_ts:
            if not xs or ts // PAS_COURBE_S != xs[-1] // PAS_COURBE_S:
                xs.append(ts)
            else:
                xs[-1] = ts if ts == all_ts[-1] else xs[-1]
        if all_ts and xs[-1] != all_ts[-1]:
            xs.append(all_ts[-1])
        for p_out in pfs:  # la courbe d'un archivé s'arrête à son retrait : ce point doit exister
            fin = (p_out.get("archive") or {}).get("ts")
            if fin is not None and fin not in xs and xs and xs[0] < fin < xs[-1]:
                xs.append(fin)
                xs.sort()
        chart_series = []
        for p_out in pfs:
            s = series.get(p_out["id"], [])
            vals: list[float | None] = []
            j, last = 0, None
            fin = (p_out.get("archive") or {}).get("ts")
            for x in xs:
                while j < len(s) and s[j][0] <= x:
                    last = s[j][1]
                    j += 1
                vals.append(None if last is None or (fin is not None and x > fin) else round(last / p_out["capital_ueur"] * 100, 4))
            serie = {"id": p_out["id"], "slug": p_out["slug"], "name": p_out["name"], "kind": p_out["kind"], "values": vals}
            if fin is not None:
                serie["archive_ts"] = fin
            chart_series.append(serie)
        live = [last_eq[pf]["ts"] for pf in ids if pf in last_eq]
        return {
            **commun, "ouverte_ts": min((opened[pf]["ts"] for pf in ids), default=None), "live_ts": max(live, default=None),
            "llm_presents": any(p["kind"] == "llm" for p in pfs), "portfolios": pfs,
            "chart": {"x": xs, "kinds": ["veille"] * len(xs), "series": chart_series},
        }  # fmt: skip

    # Les conseils ont leur ligue : le témoin panier leur sert de référence, sans quitter la ligue dérivés ; le
    # témoin « moteur seul » est un témoin de cette ligue seulement.
    deriv = ligue([p for p in portfolios if p["kind"] != "conseil" and p["id"] != MOTEUR])
    conseils = [p for p in portfolios if p["kind"] == "conseil"]
    panier = [p for p in portfolios if p["id"] == PANIER]
    moteur = [p for p in portfolios if p["id"] == MOTEUR]
    deriv["conseils"] = ligue(conseils + panier + moteur) if conseils else None
    return deriv
