"""Calcul de toutes les données du dashboard à partir du journal SEUL (docs/SPEC-MVP.md §13).

`compute()` renvoie un dictionnaire prêt pour JSON (floats permis : affichage seulement). Rien ici n'écrit
de fichier, sauf le cache des trajectoires aléatoires (hors du dépôt, voir `_distribution`). Les justifications
des modèles sont publiées dès la décision (décision du propriétaire, 12/11/2026).

Veille et réveils (docs/COORDINATION-dashboard.md, entrée -3) : l'equity vivante vient de `veille.equity` ;
`veille.quotes_bruts` et les `quote_reveil` ne servent jamais de prix affiché. Les réveils sont des rondes de
décision hors de la grille de 4 h (leur `cycle` vaut le tick du réveil), jamais des cycles.

Saison (entrée -4) : dès qu'un `saison_reference` existe, tout classement et toute mesure partent de son equity,
jamais du capital initial ; le rodage d'avant est résumé à part.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import os
import re
import time
from collections import Counter
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path
from typing import Any

from arene import stats
from arene.config import Config
from arene.journal import Journal, verify
from arene.ledger import replay
from arene.risk.policy import Policy
from arene.site.hasard import Ronde, trajectoires_depuis
from arene.temoins.trajectoires import CycleData
from arene.types import Bar, Instrument, Quote, notional_ueur

MIN_CYCLES_STATS = 30  # sous ce nombre de cycles : « trop tôt » (IC du Sharpe, distinction du hasard)
BASELINE = "temoin:panier"
ALEATOIRE = "temoin:aleatoire"
JUSTIFICATION_MAX = 2_000
DECISIONS_MAX = 200  # décisions conservées par page modèle (les plus récentes)
PAS_COURBE_VEILLE_S = 1_800  # un relevé de veille toutes les 30 min sur la courbe (plus le dernier)
REVEILS_MAX = 50

# Précisions de l'univers (SPEC §1) : le site ne reçoit pas AssetPairs, il ne sert qu'à rejouer l'aléatoire.
_INSTRUMENT_TABLE = {
    "BTC/EUR": (100_000, 6_000),
    "ETH/EUR": (10_000, 200_000),
    "SOL/EUR": (10_000, 5_000_000),
    "XRP/EUR": (10, 400_000_000),
    "LINK/EUR": (10, 35_000_000),
    "LTC/EUR": (10_000, 8_000_000),
}
_COST_MIN_UEUR = 450_000

NOMS = {
    "llm:claude-haiku-5-5": "Claude Haiku 5.5",
    "llm:claude-sonnet-5-5": "Claude Sonnet 5.5",
    "llm:claude-opus-5-5": "Claude Opus 5.5",
    "llm:claude-fable-5-2": "Claude Fable 5.2",
    "temoin:panier": "Témoin panier",
    "temoin:6040": "Témoin 60/40",
    "temoin:e0065": "Témoin E0065 (adapté)",
    "temoin:aleatoire": "Témoin aléatoire",
}
DESCRIPTIONS = {
    "temoin:panier": "1/6 du portefeuille sur chacune des 6 cryptos au premier cycle, puis conservé : le marché.",
    "temoin:6040": "60 % en bitcoin, 40 % en euros, rééquilibré au début de chaque mois.",
    "temoin:e0065": "Règle fixe fondée sur la pression acheteuse (part des achats passés au prix du marché), paramètres L = 20, k = 3, H = 10.",
    "temoin:aleatoire": "Tire 0 à 2 actions au hasard par cycle, avec exactement les mêmes règles de risque que les modèles.",
}

CODES_RISQUE = {
    "NOT_WHITELISTED": "paire hors de la liste autorisée",
    "MAX_ORDER_SIZE": "ordre trop gros (plafond par ordre)",
    "MAX_POSITION": "position trop grosse sur ce symbole",
    "MAX_EXPOSURE": "exposition totale trop élevée",
    "INSUFFICIENT_CASH": "cash insuffisant (frais compris)",
    "DAILY_TRADES": "quota de trades sur 24 h atteint",
    "ORDER_RATE": "trop d'ordres à la minute",
    "TOO_SOON": "trop tôt après la dernière intention sur ce symbole",
    "STOP_REQUIRED": "achat sans stop",
    "STOP_RANGE": "stop hors des bornes autorisées",
    "EDGE_TOO_SMALL": "coût estimé trop grand par rapport au mouvement attendu",
    "FROZEN": "portefeuille gelé",
    "HALTED": "portefeuille arrêté (drawdown)",
    "FEE_BUDGET": "budget de frais du mois atteint",
    "PRICE_SANITY": "prix du quote trop éloigné de la dernière clôture",
    "SPREAD_ANOMALY": "écart bid/ask anormal",
    "ORDER_TOO_SMALL": "ordre sous le minimum",
    "NO_SHORT": "vente à découvert interdite",
    "KILL_SWITCH": "coupe-circuit actif",
    "NO_QUOTE": "aucun quote disponible",
    "NO_MARK": "aucun prix de valorisation",
    "NO_EQUITY": "equity indisponible",
    "UNKNOWN_INSTRUMENT": "instrument inconnu",
    "BAD_PARAMS": "paramètres invalides",
    "BAD_SIDE": "sens invalide",
    "BAD_SIZE": "taille invalide",
    "INTERNAL_ERROR": "erreur interne de riskd",
}

SAUTS = {
    "no_key": "modèle pas encore branché",
    "budget": "budget quotidien d’API atteint",
    "frozen": "portefeuille gelé",
    "halted": "portefeuille arrêté",
    "kill_switch": "coupe-circuit actif",
    "api_error": "erreur d’API",
}


def slug(portfolio: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", portfolio.lower()).strip("-")


def nom(portfolio: str) -> str:
    return NOMS.get(portfolio, portfolio)


def _instruments(config: Config) -> dict[str, Instrument]:
    out = {}
    for ref in config.instrument_refs:
        tick, lot = _INSTRUMENT_TABLE.get(ref.symbol, (10, 1))
        out[ref.symbol] = Instrument(ref.symbol, ref.kraken_pair, ref.binance_symbol, tick, lot, _COST_MIN_UEUR)
    return out


def _cycle_data(
    events: list[dict[str, Any]], interval_s: int, reveils: Mapping[int, dict[str, Any]] | None = None
) -> list[Ronde]:
    """Reconstruit ce que le journal a retenu de chaque ronde terminée : cycles (quotes, marks, barres 4 h) et
    réveils complétés (quotes `quote_reveil`, clôtures 1 min de leur tick, sans barre), triés par instant.

    Au réveil, seuls les symboles cotés sont négociables (comme au réveil réel) ; les autres gardent leur dernier
    mark pour la valorisation."""
    completed = {e["payload"]["cycle"] for e in events if e["type"] == "cycle_completed"}
    reveils = reveils or {}
    cur: int | None = None
    quotes: dict[int, dict[str, Quote]] = {}
    bars: dict[int, dict[str, list[Bar]]] = {}
    closes_after: dict[int, dict[str, int]] = {}
    last_closes: dict[str, int] = {}
    order: list[int] = []
    rq: dict[int, dict[str, Quote]] = {}
    clot_1m: dict[int, dict[str, int]] = {}
    veille_mids: list[tuple[int, dict[str, int]]] = []  # (tick, mids des quotes ACCEPTÉS) dans l'ordre du journal
    cur_reveil: int | None = None
    for e in events:
        t, p = e["type"], e["payload"]
        if t == "reveil_started":
            cur_reveil = p["reveil"]
            continue
        if t in ("reveil_completed", "reveil_abandonne"):
            if p.get("reveil") == cur_reveil:
                cur_reveil = None
            continue
        if t == "quote_reveil":
            # Rattaché au réveil ouvert qui le précède (les réveils ne se chevauchent pas) ; `ts` est l'instant du
            # quote, pas forcément le tick du réveil (COORDINATION-dashboard, réponses du moteur du 12/11).
            if cur_reveil is not None:
                rq.setdefault(cur_reveil, {})[p["symbol"]] = Quote(p["symbol"], p["ts"], p["bid"], p["ask"])
            continue
        if t == "veille":
            if p.get("tick") in reveils:
                clot_1m[p["tick"]] = dict(p.get("clotures_1m") or {})
            mids = {s: (b + a) // 2 for s, (b, a) in (p.get("quotes") or {}).items()}
            if mids:
                veille_mids.append((p["tick"], mids))
            continue
        if t == "cycle_started":
            cur = p["cycle"]
            if cur not in quotes:
                order.append(cur)
                quotes[cur], bars[cur] = {}, {}
        elif cur is None:
            continue
        elif t == "quote":
            quotes[cur][p["symbol"]] = Quote(p["symbol"], p["ts"], p["bid"], p["ask"])
        elif t == "bar" and p.get("interval_s") == interval_s:
            bar = Bar(p["symbol"], p["interval_s"], p["ts"], p["open"], p["high"], p["low"], p["close"], p["volume"])
            bars[cur].setdefault(bar.symbol, []).append(bar)
            if bar.ts + interval_s <= cur:
                last_closes[bar.symbol] = bar.close
        closes_after[cur] = dict(last_closes)
    rondes = [(c, "cycle") for c in order if c in completed]
    rondes += [(r, "reveil") for r, info in reveils.items() if info.get("statut") == "complete" and rq.get(r)]
    out: list[Ronde] = []
    carry: dict[str, Quote] = {}
    marks_carry: dict[str, int] = {}
    closes_carry: dict[str, int] = {}
    veille_mids.sort(key=lambda x: x[0])
    derniere_veille: dict[str, int] = {}
    iv = 0
    for c, kind in sorted(rondes):
        if kind == "cycle":
            carry.update(quotes[c])  # un symbole sans quote ce cycle garde le dernier connu
            q = dict(carry)
            marks = {s: (x.bid + x.ask) // 2 for s, x in q.items()}
            closes_carry = {**marks, **closes_after.get(c, {})}
            marks_carry.update(marks)
            out.append(Ronde(CycleData(c, q, marks, dict(closes_carry), bars[c])))
        else:
            q = rq[c]
            # Symbole non coté au réveil : son dernier quote accepté de la veille, comme `_dernier_quote_valide`.
            while iv < len(veille_mids) and veille_mids[iv][0] <= c:
                derniere_veille.update(veille_mids[iv][1])
                iv += 1
            marks_carry.update({s: (x.bid + x.ask) // 2 for s, x in q.items()})
            marks_r = {**marks_carry, **{s: m for s, m in derniere_veille.items() if s not in q}}
            lc = {**closes_carry, **{s: v for s, v in clot_1m.get(c, {}).items() if s in q}}
            out.append(Ronde(CycleData(c, q, marks_r, lc, {}), reveil=True))
    return out


def _series_from_events(events: list[dict[str, Any]]) -> dict[str, dict[int, int]]:
    out: dict[str, dict[int, int]] = {}
    for e in events:
        if e["type"] == "equity":
            p = e["payload"]
            out.setdefault(p["portfolio"], {})[p.get("cycle", e["ts"])] = p["equity_ueur"]
    return out


def _fill_view(p: Mapping[str, Any], ts: int) -> dict[str, Any]:
    return {
        "ts": ts,
        "order_id": p["order_id"],
        "symbol": p["symbol"],
        "side": p["side"],
        "qty": p["qty"],
        "price_ueur": p["price_ueur"],
        "fee_ueur": p["fee_ueur"],
        "reason": p.get("reason", "intent"),
    }


def _decisions(
    events: list[dict[str, Any]], cycles: list[int], reveils: Mapping[int, dict[str, Any]] | None = None
) -> dict[str, list[dict[str, Any]]]:
    """Une ligne par (portefeuille, ronde) : cycle de 4 h ou réveil (`ronde`, `declencheur`). Les ventes forcées
    se rangent sous la ronde qui les précède ; une vente sur stop de la veille (`…:veille:{tick}`) a sa propre ligne,
    à l'instant du tick."""
    reveils = reveils or {}
    rows: dict[tuple[str, int], dict[str, Any]] = {}
    verdicts: dict[str, dict[str, Any]] = {}
    fills_by_order: dict[str, list[dict[str, Any]]] = {}
    forced: dict[tuple[str, int], list[dict[str, Any]]] = {}

    def row(portfolio: str, cycle: int, ts: int) -> dict[str, Any]:
        key = (portfolio, cycle)
        if key not in rows:
            rows[key] = {
                "portfolio": portfolio, "cycle": cycle, "ts": ts, "kind": "temoin" if portfolio.startswith("temoin:") else "pending",
                "skip_reason": None, "model_requested": None, "model_returned": None, "cost_uusd": None,
                "input_tokens": None, "output_tokens": None, "parse_error": None, "justification": None,
                "actions": [], "sorties": [],
                "ronde": "reveil" if cycle in reveils else "rendez_vous",
                "declencheur": (reveils.get(cycle) or {}).get("declencheur"),
                "reveil_statut": (reveils.get(cycle) or {}).get("statut"),
            }  # fmt: skip
        return rows[key]

    for e in events:
        t, p, ts = e["type"], e["payload"], e["ts"]
        if t == "risk_verdict":
            verdicts[p["intent_id"]] = p
        elif t == "fill":
            fills_by_order.setdefault(p["order_id"], []).append(_fill_view(p, ts))
    intent_ids: set[str] = set()
    for e in events:
        t, p, ts = e["type"], e["payload"], e["ts"]
        if t == "decision_skipped":
            r = row(p["portfolio"], p["cycle"], ts)
            r["kind"], r["skip_reason"] = "skipped", p["reason"]
        elif t == "decision_received":
            r = row(p["portfolio"], p["cycle"], ts)
            r["ts"] = ts
            r["kind"] = "parse_error" if p.get("parse_error") else "decided"
            for k in ("model_requested", "model_returned", "cost_uusd", "input_tokens", "output_tokens", "parse_error"):
                r[k] = p.get(k)
            parsed = p.get("parsed")
            texte = parsed.get("justification") if isinstance(parsed, dict) else None
            if not isinstance(texte, str):
                texte = p.get("raw_text") if isinstance(p.get("raw_text"), str) else None
            r["justification"] = texte[:JUSTIFICATION_MAX] if texte else None
            r["a_justification"] = bool(texte)
        elif t == "intent":
            r = row(p["portfolio"], p["cycle"], ts)
            if p["intent_id"] in intent_ids:
                continue
            intent_ids.add(p["intent_id"])
            v = verdicts.get(p["intent_id"])
            r["actions"].append({
                "intent_id": p["intent_id"], "symbol": p["symbol"], "side": p["side"], "size_bp": p["size_bp"],
                "stop_bp": p.get("stop_bp"), "expected_move_bp": p.get("expected_move_bp"),
                "horizon_h": p.get("horizon_h"), "confidence_pct": p.get("confidence_pct"),
                "approved": None if v is None else bool(v["approved"]),
                "reasons": [] if v is None else list(v.get("reasons", ())),
                "qty": 0 if v is None else v.get("qty", 0),
                "fills": fills_by_order.get(p["intent_id"], []),
            })  # fmt: skip
    cyc_sorted = sorted(set(cycles) | set(reveils))
    for e in events:
        if e["type"] != "fill" or e["payload"]["order_id"] in intent_ids:
            continue
        p = e["payload"]
        if ":veille:" in p["order_id"]:
            c = e["ts"]  # stop de la veille : sa propre ligne, à l'heure du tick
        else:
            i = bisect.bisect_right(cyc_sorted, e["ts"]) - 1
            c = cyc_sorted[i] if i >= 0 else e["ts"]
        forced.setdefault((p["portfolio"], c), []).append(_fill_view(p, e["ts"]))
    for (pf, c), fl in forced.items():
        r = row(pf, c, c)
        r["sorties"] = fl
        if r["kind"] in ("pending", "temoin") and not r["actions"] and any(":veille:" in f["order_id"] for f in fl):
            r["kind"], r["ronde"] = "stop_veille", "veille"
    out: dict[str, list[dict[str, Any]]] = {}
    for (pf, _c), r in sorted(rows.items(), key=lambda kv: kv[0][1], reverse=True):
        if r["kind"] == "pending":
            r["kind"] = "decided" if r["actions"] else "inconnu"
        out.setdefault(pf, []).append(r)
    return out


def _reveils(events: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Réveils : {tick: {reveil, ts (heure du mur), declencheur, statut}} ; statut complete | abandonne | en_cours."""
    out: dict[int, dict[str, Any]] = {}
    for e in events:
        t, p = e["type"], e["payload"]
        if t == "reveil_started":
            out[p["reveil"]] = {"reveil": p["reveil"], "ts": e["ts"], "declencheur": p.get("declencheur"), "statut": "en_cours"}
        elif t in ("reveil_completed", "reveil_abandonne") and p.get("reveil") in out:
            out[p["reveil"]]["statut"] = "complete" if t == "reveil_completed" else "abandonne"
    return out


def _saison(events: list[dict[str, Any]], config: Config, now: int) -> dict[str, Any] | None:
    """Dernière saison journalisée (début, référence, dérogations, fin), ou la saison prévue par la config."""
    debuts = [e for e in events if e["type"] == "saison_debut"]
    if not debuts:
        sc = getattr(config, "saison", None)
        if sc is None:
            return None
        return {"statut": "prevue", "numero": sc.numero, "nom": sc.nom, "debut_ts": sc.debut_ts,
                "duree_jours": sc.duree_jours}  # fmt: skip
    d = debuts[-1]["payload"]
    num = d["numero"]
    ref = next((e["payload"] for e in events if e["type"] == "saison_reference" and e["payload"]["numero"] == num), None)
    fin = next((e for e in events if e["type"] == "saison_fin" and e["payload"]["numero"] == num), None)
    derog = []
    for e in events:
        if e["type"] == "saison_derogation" and e["payload"]["numero"] == num:
            av, ap = e["payload"].get("hashes_avant") or {}, e["payload"].get("hashes_apres") or {}
            derog.append({"ts": e["ts"], "raison": e["payload"].get("raison", ""),
                          "quoi": sorted(k for k in set(av) | set(ap) if av.get(k) != ap.get(k))})  # fmt: skip
    debut_cycle = d["cycle"]
    jour = max(1, min(d.get("duree_jours") or 1, (min(now, d["fin_prevue_cycle"]) - debut_cycle) // 86_400 + 1))
    return {
        "statut": "terminee" if fin else ("ouverte" if ref else "sans_reference"),
        "numero": num, "nom": d.get("nom") or f"Saison {num}", "cycle": debut_cycle,
        "fin_prevue_cycle": d["fin_prevue_cycle"], "debut_ts": d.get("debut_ts"), "duree_jours": d.get("duree_jours"),
        "jour": jour, "reference": ref, "fin_cycle": fin["payload"]["cycle"] if fin else None,
        "derogations": derog,
    }  # fmt: skip


def _cache_dir() -> Path | None:
    v = os.environ.get("ARENE_SITE_CACHE")
    if v == "":
        return None
    return Path(v) if v else Path.home() / ".cache" / "arene-site"


def _distribution(
    rondes: list[Ronde], config: Config, policy: Policy, capital: int, depuis: int | None = None
) -> list[float]:
    """Rendement de chaque trajectoire aléatoire depuis la ronde `depuis` (sinon depuis le capital). Le calcul ne change qu'avec une nouvelle ronde : le dernier résultat
    est gardé dans un cache (une seule entrée, hors du dépôt, clé = sha256 de toutes les entrées)."""
    n = config.temoins.aleatoire_trajectoires
    key_src = json.dumps(
        [[r.data.ts, r.reveil, sorted((s, q.bid, q.ask) for s, q in r.data.quotes.items()),
          sorted(r.data.marks.items()), sorted(r.data.last_closes.items()),
          sorted((s, [(b.ts, b.open, b.high, b.low, b.close) for b in bs]) for s, bs in r.data.bars.items())]
         for r in rondes] + [depuis, hashlib.sha256((Path(__file__).parent / "hasard.py").read_bytes()).hexdigest()] + [n, policy.sha256, config.taker_fee_bp, config.slippage_bp, capital,
                                 sorted(r.symbol for r in config.instrument_refs)],
    )  # fmt: skip
    key = hashlib.sha256(key_src.encode()).hexdigest()
    cache = _cache_dir()
    fichier = cache / "trajectoires.json" if cache else None
    if fichier is not None:
        try:
            c = json.loads(fichier.read_text(encoding="utf-8"))
            if c.get("key") == key and isinstance(c.get("rets"), list) and len(c["rets"]) == n:
                return [float(v) for v in c["rets"]]
        except (OSError, ValueError):
            pass
    paires = trajectoires_depuis(
        rondes, n, policy=policy, instruments=_instruments(config), fee_bp=config.taker_fee_bp,
        slippage_bp=config.slippage_bp, capital_ueur=capital, depuis=depuis,
    )  # fmt: skip
    rets = [f / d - 1.0 if d else 0.0 for d, f in paires]
    if fichier is not None:
        try:
            fichier.parent.mkdir(parents=True, exist_ok=True)
            tmp = fichier.with_suffix(f".tmp-{os.getpid()}")
            tmp.write_text(json.dumps({"key": key, "rets": rets}), encoding="utf-8")
            os.replace(tmp, fichier)
        except OSError:
            pass
    return rets


def compute(journal_path: Path, config: Config, policy: Policy, now_ts: int | None = None) -> dict[str, Any]:
    now = int(time.time()) if now_ts is None else int(now_ts)
    journal = Journal(journal_path)
    events = list(journal.iter_events(strict=False))
    report = verify(journal_path)
    states = replay(events)
    equity_by_pf = _series_from_events(events)
    capital = {e["payload"]["portfolio"]: e["payload"]["capital_ueur"] for e in events if e["type"] == "portfolio_opened"}
    kinds = {e["payload"]["portfolio"]: e["payload"].get("kind", "llm") for e in events if e["type"] == "portfolio_opened"}
    ids = sorted(capital, key=lambda p: (0 if kinds[p] == "llm" else 1, list(NOMS).index(p) if p in NOMS else 99, p))
    # Portefeuilles retirés (`arene retire`) : vendus au bid, valeur figée dans l'événement. La note libre n'est jamais lue.
    retires: dict[str, dict[str, Any]] = {}
    for e in events:
        if e["type"] == "portfolio_retired" and e["payload"]["portfolio"] not in retires:
            retires[e["payload"]["portfolio"]] = {"ts": e["ts"], "equity_ueur": e["payload"]["equity_ueur"]}
    reveils = _reveils(events)
    saison = _saison(events, config, now)
    veilles = [e["payload"] for e in events if e["type"] == "veille"]
    veilles.sort(key=lambda v: v["tick"])
    seq_veille = max((i for i, e in enumerate(events) if e["type"] == "veille"), default=-1)
    seq_cycle = max((i for i, e in enumerate(events) if e["type"] == "cycle_completed"), default=-1)

    all_cycles = sorted({c for s in equity_by_pf.values() for c in s})
    # Période mesurée : la saison (depuis sa référence) dès qu'elle existe, sinon tout depuis le premier cycle.
    ref = saison["reference"] if saison and saison.get("reference") else None
    fin_cycle = saison.get("fin_cycle") if ref else None
    if ref is not None:
        ref_cycle = ref["cycle"]
        cycles = [c for c in all_cycles if c >= ref_cycle and (fin_cycle is None or c <= fin_cycle)]
        x0: int | None = ref_cycle - 1  # la référence est prise AVANT les décisions du cycle de début
        base = {pf: ref["equity"][pf] for pf in ids if pf in ref.get("equity", {})}
    else:
        ref_cycle = None
        cycles = all_cycles
        x0 = (all_cycles[0] - config.interval_s) if all_cycles else None
        base = dict(capital)

    # Equity vivante : le dernier tick de veille plus récent que le dernier cycle (et dans la saison si elle est finie).
    live = None
    if veilles and seq_veille > seq_cycle and (not all_cycles or veilles[-1]["tick"] > all_cycles[-1]) and fin_cycle is None:
        v = veilles[-1]
        live = {"ts": v["tick"], "equity": dict(v.get("equity") or {}), "gel": bool(v.get("gel"))}

    # Marks des positions : dernier bid ACCEPTÉ, au cycle (`quote`) ou à la veille (`veille.quotes`).
    # Jamais `veille.quotes_bruts` ni `quote_reveil`.
    last_marks: dict[str, int] = {}
    last_quote_ts: int | None = None
    for e in events:
        if e["type"] == "quote":
            p = e["payload"]
            last_marks[p["symbol"]] = p["bid"]  # valorisation au bid, comme l'equity du cycle (cash + positions = equity)
            last_quote_ts = max(last_quote_ts or 0, p["ts"])
        elif e["type"] == "veille":
            p = e["payload"]
            for sym, (b, _a) in (p.get("quotes") or {}).items():
                last_marks[sym] = b
            if p.get("quotes"):
                last_quote_ts = max(last_quote_ts or 0, p["tick"])

    # Distribution des trajectoires aléatoires, rejouées sur les mêmes rondes (cycles ET réveils complétés, où le
    # témoin aléatoire vivant décide aussi) et les mêmes quotes, sur la période mesurée.
    distribution: list[float] = []
    dist_note = None
    # Toutes les rondes jusqu'au dernier cycle mesuré : le rang compare des rendements au même instant (le dernier
    # cycle, pas l'equity vivante), et le rodage amorce l'état des trajectoires sans compter dans la mesure.
    borne = cycles[-1] if cycles else None
    cycle_data = [r for r in _cycle_data(events, config.interval_s, reveils) if borne is not None and r.data.ts <= borne]
    cap_ref = capital.get(ALEATOIRE) or config.capital_ueur
    if cycle_data:
        try:
            distribution = _distribution(cycle_data, config, policy, cap_ref, ref_cycle)
        except Exception as exc:  # noqa: BLE001 - le site ne doit pas tomber pour une statistique
            dist_note = f"rang indisponible : {type(exc).__name__}"
    dist_summary = None
    if distribution:
        srt = sorted(distribution)
        n = len(srt)
        dist_summary = {
            "n": n, "p05": srt[int(0.05 * (n - 1))], "median": srt[(n - 1) // 2], "p95": srt[int(0.95 * (n - 1))],
        }  # fmt: skip

    decisions = _decisions(events, all_cycles, reveils)
    costs: Counter[str] = Counter()
    decided: Counter[str] = Counter()
    skipped: dict[str, Counter[str]] = {}
    rejects: dict[str, Counter[str]] = {}
    for e in events:
        t, p = e["type"], e["payload"]
        if t == "decision_received":
            costs[p["portfolio"]] += p.get("cost_uusd") or 0
            if not p.get("parse_error"):
                decided[p["portfolio"]] += 1  # une réponse invalide n'est pas une décision
        elif t == "decision_skipped":
            skipped.setdefault(p["portfolio"], Counter())[p["reason"]] += 1
    intent_owner = {e["payload"]["intent_id"]: e["payload"]["portfolio"] for e in events if e["type"] == "intent"}
    for e in events:
        if e["type"] == "risk_verdict" and not e["payload"]["approved"]:
            pf = intent_owner.get(e["payload"]["intent_id"])
            if pf:
                rejects.setdefault(pf, Counter()).update(e["payload"].get("reasons", ()))
    trades: dict[str, set[str]] = {}
    for e in events:
        if e["type"] == "fill":
            trades.setdefault(e["payload"]["portfolio"], set()).add(e["payload"]["order_id"])

    cyc_set = set(cycles)

    def serie(pf: str) -> list[int]:
        """Equity de départ de la période mesurée, puis equity à chaque cycle de cette période."""
        s = equity_by_pf.get(pf, {})
        pts = [s[c] for c in sorted(s) if c in cyc_set]
        return ([base[pf]] if pf in base else [capital[pf]]) + pts

    # Un portefeuille sans equity au départ de la période (modèle ajouté en cours d'expérience ou de saison) n'est
    # comparé qu'à partir de son départ : pas de point à 100 avant lui, pas de rang face au hasard sur la période.
    opened_ts = {e["payload"]["portfolio"]: e["ts"] for e in events if e["type"] == "portfolio_opened"}

    def depart(pf: str) -> int | None:
        s = [c for c in equity_by_pf.get(pf, {}) if c in cyc_set]
        if ref is not None and pf in base:
            return ref_cycle
        return min(s) if s else opened_ts.get(pf)

    def tardif(pf: str) -> bool:
        if ref is not None:
            return pf not in base
        d = depart(pf)
        return bool(all_cycles) and d is not None and d > all_cycles[0]

    base_pf = {BASELINE: serie(BASELINE)} if BASELINE in capital else {}
    portfolios: list[dict[str, Any]] = []
    for pf in ids:
        st = states[pf]
        series = serie(pf)
        n = len(series) - 1
        vivante = live["equity"].get(pf) if live else None
        archive = retires.get(pf)
        final = archive["equity_ueur"] if archive else vivante if vivante is not None else series[-1]
        rets = stats.returns(series)
        enough = n >= MIN_CYCLES_STATS
        sh = stats.sharpe(rets) if len(rets) >= 2 else None
        ci = stats.sharpe_ci(rets) if enough else None
        start = series[0]
        tr = final / start - 1.0 if start else 0.0
        dist = None
        if pf != BASELINE and base_pf and len(rets) >= 2:
            b = stats.returns(base_pf[BASELINE])
            m = min(len(b), len(rets))
            if m >= 2:
                d = stats.distinguishable(rets[-m:], b[-m:])
                dist = {"significant": bool(d.significant and enough), "mean_diff": d.mean_diff,
                        "ci_low": d.ci_low, "ci_high": d.ci_high}  # fmt: skip
        positions = []
        for sym, pos in st.positions.items():
            mark = last_marks.get(sym)
            val = None if mark is None else notional_ueur(pos.qty, mark, round_up=False)
            positions.append({
                "symbol": sym, "qty": pos.qty, "cost_ueur": pos.cost_ueur, "opened_ts": pos.opened_ts,
                "stop_ueur": pos.stop_ueur, "mark_ueur": mark, "value_ueur": val,
                "unrealized_ueur": None if val is None else val - pos.cost_ueur,
            })  # fmt: skip
        late = tardif(pf)
        portfolios.append({
            "id": pf, "slug": slug(pf), "name": nom(pf), "kind": kinds[pf], "description": DESCRIPTIONS.get(pf),
            "capital_ueur": capital[pf], "base_ueur": start, "equity_ueur": final, "equity_live": vivante is not None,
            "base100": final / start * 100 if start else 100.0,
            "n_cycles": n, "total_return": tr, "max_drawdown": stats.max_drawdown(series + ([final] if vivante is not None or archive else [])),
            "sharpe": sh if enough else None, "sharpe_ci": list(ci) if ci else None, "too_early": not enough,
            "fees_paid_ueur": st.fees_paid_ueur, "realized_pnl_ueur": st.realized_pnl_ueur,
            "n_trades": len(trades.get(pf, ())), "api_cost_uusd": costs[pf] if kinds[pf] == "llm" else None,
            "rank_percentile": (
                stats.rank_in_distribution(series[-1] / start - 1.0 if start else 0.0, distribution)
                if distribution and not late else None
            ),
            "start_ts": depart(pf), "late": late,
            "distinguishable": dist, "cash_ueur": st.cash_ueur, "halted": st.halted,
            "frozen_until_ts": st.frozen_until_ts if st.frozen_until_ts > now else 0,
            "positions": positions,
            "n_decided": decided[pf] if kinds[pf] == "llm" else None,
            "skipped": dict(skipped.get(pf, {})), "rejects": dict(rejects.get(pf, {})),
            "decisions_total": len(decisions.get(pf, ())),
            "decisions": decisions.get(pf, [])[:DECISIONS_MAX],
            "series_ueur": series, "archive": archive,
        })  # fmt: skip

    # Courbe : départ de la période, chaque cycle (equity du cycle), un relevé de veille toutes les 30 min entre les
    # cycles, et le dernier relevé (equity vivante). Axe en temps réel : les relevés ne sont pas sur la grille de 4 h.
    pts: dict[int, tuple[str, Mapping[str, int]]] = {}
    t_min = ref_cycle if ref_cycle is not None else (all_cycles[0] if all_cycles else None)
    t_max = fin_cycle
    for v in veilles:
        tk = v["tick"]
        if t_min is None or tk < t_min or (t_max is not None and tk > t_max):
            continue
        if tk % PAS_COURBE_VEILLE_S == 0 or (live is not None and tk == live["ts"]):
            pts[tk] = ("veille", v.get("equity") or {})
    for c in cycles:
        pts[c] = ("cycle", {pf: s[c] for pf, s in equity_by_pf.items() if c in s})
    xs = sorted(pts)
    x = ([x0] if x0 is not None else []) + xs
    kinds_x = (["depart"] if x0 is not None else []) + [pts[t][0] for t in xs]
    chart = []
    for p in portfolios:
        b0 = p["base_ueur"]
        vals: list[float | None] = ([None if p["late"] else 100.0]) if x0 is not None else []
        vals += [round(pts[t][1][p["id"]] / b0 * 100, 4) if p["id"] in pts[t][1] and b0 else None for t in xs]
        serie_c = {"id": p["id"], "name": p["name"], "kind": p["kind"], "values": vals}
        if p["archive"]:  # courbe figée : rien après le retrait, dont la dernière valeur est celle de la vente
            fin = p["archive"]["ts"]
            vals[:] = [None if (t > fin and i > 0) else v for i, (t, v) in enumerate(zip(x, vals, strict=True))]
            dernier = max((i for i, v in enumerate(vals) if v is not None), default=None)
            if dernier is not None and b0:
                vals[dernier] = round(p["equity_ueur"] / b0 * 100, 4)
            serie_c["archive_ts"] = fin
        chart.append(serie_c)

    rodage = None
    if ref is not None:
        avant = [c for c in all_cycles if c < ref_cycle]
        rodage = {
            "debut_ts": avant[0] if avant else None, "fin_ts": ref_cycle, "n_cycles": len(avant),
            "portfolios": [
                {"id": pf, "name": nom(pf), "kind": kinds[pf],
                 "total_return": ref["equity"][pf] / capital[pf] - 1.0 if capital.get(pf) else None}
                for pf in ids if pf in ref.get("equity", {})
            ],
        }  # fmt: skip

    reveils_liste = [
        {k: r[k] for k in ("reveil", "ts", "declencheur", "statut")}
        for r in sorted(reveils.values(), key=lambda r: r["reveil"], reverse=True)
    ][:REVEILS_MAX]

    cfg_events = [e for e in events if e["type"] == "config_loaded"]
    cfg_last = cfg_events[-1]["payload"] if cfg_events else {}
    llm_dist = [p for p in portfolios if p["kind"] == "llm" and p["distinguishable"]]
    any_distinguishable = any(p["distinguishable"]["significant"] for p in llm_dist)
    vc = getattr(config, "veille", None)
    return {
        "venue_mode": config.venue_mode,
        "generated_ts": now,
        "n_cycles": len(cycles),
        "first_cycle_ts": cycles[0] if cycles else None,
        "last_cycle_ts": all_cycles[-1] if all_cycles else None,
        "interval_s": config.interval_s,
        "decider_backend": getattr(config, "decider_backend", None),
        "last_quote_ts": last_quote_ts,
        "min_cycles_stats": MIN_CYCLES_STATS,
        "any_llm_distinguishable": any_distinguishable,
        "distribution": dist_summary,
        "distribution_note": dist_note,
        "portfolios": portfolios,
        "chart": {"x": x, "kinds": kinds_x, "series": chart, "n_cycles": len(cycles)},
        "live": {"ts": live["ts"], "gel": live["gel"]} if live else None,
        "reveils": reveils_liste,
        "n_reveils": len(reveils),
        "saison": saison,
        "rodage": rodage,
        # Cycles terminés et leur maillon du journal chaîné (empreinte de l'événement cycle_completed).
        "cycles": [
            {"ts": e["payload"]["cycle"], "hash": e.get("hash"), "seq": e.get("seq")}
            for e in sorted((e for e in events if e["type"] == "cycle_completed"), key=lambda e: e["payload"]["cycle"])
        ],
        "journal": {
            "verify_ok": report.ok, "n_records": report.n_records, "head_seq": report.head_seq,
            "head_hash": report.head_hash, "errors": [
                {"code": er.code, "line": er.line, "message": er.message} for er in report.errors[:10]
            ],
        },
        "provenance": {
            "policy_sha256": policy.sha256, "config_sha256": config.sha256,
            "journal_policy_sha256": cfg_last.get("policy_sha256"),
            "journal_config_sha256": cfg_last.get("config_sha256"),
            "prompt_sha256": cfg_last.get("prompt_sha256"),
            "prompt_hashes": sorted({e["payload"].get("prompt_sha256") for e in cfg_events if e["payload"].get("prompt_sha256")}),
            "git_head": cfg_last.get("git_head"),
        },
        "method": {
            "fill_model_version": config.fill_model_version, "taker_fee_bp": config.taker_fee_bp,
            "slippage_bp": config.slippage_bp, "capital_ueur": config.capital_ueur,
            "interval_s": config.interval_s, "n_trajectoires": config.temoins.aleatoire_trajectoires,
            "e0065": {"L": config.temoins.e0065.L, "k": config.temoins.e0065.k, "H": config.temoins.e0065.H},
            "veille": None if vc is None else {
                "tick_s": vc.tick_s, "seuil_mouvement_bp": vc.seuil_mouvement_bp,
                "fenetre_mouvement_s": vc.fenetre_mouvement_s, "max_reveils_jour": vc.max_reveils_jour,
                "cooldown_s": vc.cooldown_s,
            },
            "models": [{"portfolio": m.portfolio, "model": m.model, "daily_budget_uusd": m.daily_budget_uusd,
                        "price_in_uusd_per_mtok": m.price_in_uusd_per_mtok,
                        "price_out_uusd_per_mtok": m.price_out_uusd_per_mtok} for m in config.models],
            "policy": {f.name: (list(getattr(policy, f.name)) if f.name == "symbols" else getattr(policy, f.name))
                       for f in fields(Policy) if f.name != "sha256"},
        },
    }
