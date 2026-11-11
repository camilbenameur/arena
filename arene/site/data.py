"""Calcul de toutes les données du dashboard à partir du journal SEUL (docs/SPEC-MVP.md §13).

`compute()` renvoie un dictionnaire prêt pour JSON (floats permis : affichage seulement). Rien ici n'écrit
de fichier. Les justifications des modèles ne sont présentes que si la décision a au moins 24 h.
"""

from __future__ import annotations

import bisect
import re
import time
import warnings
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
from arene.temoins.trajectoires import CycleData, simulate_random_trajectories
from arene.types import Bar, Instrument, Quote, notional_ueur

DELAY_PUBLICATION_S = 24 * 3600
MIN_CYCLES_STATS = 30  # sous ce nombre de cycles : « trop tôt » (IC du Sharpe, distinction du hasard)
BASELINE = "temoin:panier"
ALEATOIRE = "temoin:aleatoire"
JUSTIFICATION_MAX = 2_000
DECISIONS_MAX = 200  # décisions conservées par page modèle (les plus récentes)

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
    "temoin:panier": "Témoin panier",
    "temoin:6040": "Témoin 60/40",
    "temoin:e0065": "Témoin E0065 (adapté)",
    "temoin:aleatoire": "Témoin aléatoire",
}
DESCRIPTIONS = {
    "temoin:panier": "1/6 de l'equity sur chacune des 6 paires au premier cycle, puis conservé.",
    "temoin:6040": "60 % BTC / 40 % cash, rééquilibré le premier cycle de chaque mois civil.",
    "temoin:e0065": "Règle F1 du labo (pression taker), paramètres L = 20, k = 3, H = 10, adaptée à l'univers Kraken EUR.",
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
    "no_key": "pas de clé d’API",
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


def _cycle_data(events: list[dict[str, Any]], interval_s: int) -> list[CycleData]:
    """Reconstruit ce que le journal a retenu de chaque cycle terminé (quotes, marks, barres 4 h)."""
    completed = {e["payload"]["cycle"] for e in events if e["type"] == "cycle_completed"}
    cur: int | None = None
    quotes: dict[int, dict[str, Quote]] = {}
    bars: dict[int, dict[str, list[Bar]]] = {}
    closes_after: dict[int, dict[str, int]] = {}
    last_closes: dict[str, int] = {}
    order: list[int] = []
    for e in events:
        t, p = e["type"], e["payload"]
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
    out: list[CycleData] = []
    carry: dict[str, Quote] = {}
    for c in sorted(order):
        if c not in completed:
            continue
        carry.update(quotes[c])  # un symbole sans quote ce cycle garde le dernier connu
        q = dict(carry)
        marks = {s: (x.bid + x.ask) // 2 for s, x in q.items()}
        lc = {**{s: m for s, m in marks.items()}, **closes_after.get(c, {})}
        out.append(CycleData(c, q, marks, lc, bars[c]))
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


def _decisions(events: list[dict[str, Any]], cycles: list[int], now_ts: int) -> dict[str, list[dict[str, Any]]]:
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
                "justification_publiee": False, "publication_ts": None, "actions": [], "sorties": [],
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
            r["publication_ts"] = ts + DELAY_PUBLICATION_S
            r["justification_publiee"] = now_ts >= ts + DELAY_PUBLICATION_S
            r["justification"] = texte[:JUSTIFICATION_MAX] if (texte and r["justification_publiee"]) else None
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
    cyc_sorted = sorted(cycles)
    for e in events:
        if e["type"] != "fill" or e["payload"]["order_id"] in intent_ids:
            continue
        p = e["payload"]
        i = bisect.bisect_right(cyc_sorted, e["ts"]) - 1
        c = cyc_sorted[i] if i >= 0 else e["ts"]
        forced.setdefault((p["portfolio"], c), []).append(_fill_view(p, e["ts"]))
    for (pf, c), fl in forced.items():
        row(pf, c, c)["sorties"] = fl
    out: dict[str, list[dict[str, Any]]] = {}
    for (pf, _c), r in sorted(rows.items(), key=lambda kv: kv[0][1], reverse=True):
        if r["kind"] == "pending":
            r["kind"] = "decided" if r["actions"] else "inconnu"
        out.setdefault(pf, []).append(r)
    return out


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

    all_cycles = sorted({c for s in equity_by_pf.values() for c in s})
    x0 = (all_cycles[0] - config.interval_s) if all_cycles else None
    x = ([x0] if x0 is not None else []) + all_cycles
    last_marks: dict[str, int] = {}
    last_quote_ts: int | None = None
    for e in events:
        if e["type"] == "quote":
            p = e["payload"]
            last_marks[p["symbol"]] = p["bid"]  # valorisation au bid, comme l'equity du cycle (cash + positions = equity)
            last_quote_ts = p["ts"]

    # Distribution des trajectoires aléatoires, rejouées sur les mêmes cycles et quotes.
    distribution: list[float] = []
    dist_note = None
    cycle_data = _cycle_data(events, config.interval_s)
    cap_ref = capital.get(ALEATOIRE) or config.capital_ueur
    if cycle_data:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                finals = simulate_random_trajectories(
                    cycle_data, config.temoins.aleatoire_trajectoires, policy=policy,
                    instruments=_instruments(config), fee_bp=config.taker_fee_bp,
                    slippage_bp=config.slippage_bp, capital_ueur=cap_ref,
                )  # fmt: skip
            distribution = [f / cap_ref - 1.0 for f in finals]
        except Exception as exc:  # noqa: BLE001 - le site ne doit pas tomber pour une statistique
            dist_note = f"rang indisponible : {type(exc).__name__}"
    dist_summary = None
    if distribution:
        srt = sorted(distribution)
        n = len(srt)
        dist_summary = {
            "n": n, "p05": srt[int(0.05 * (n - 1))], "median": srt[(n - 1) // 2], "p95": srt[int(0.95 * (n - 1))],
        }  # fmt: skip

    decisions = _decisions(events, all_cycles, now)
    costs: Counter[str] = Counter()
    decided: Counter[str] = Counter()
    skipped: dict[str, Counter[str]] = {}
    rejects: dict[str, Counter[str]] = {}
    for e in events:
        t, p = e["type"], e["payload"]
        if t == "decision_received":
            costs[p["portfolio"]] += p.get("cost_uusd") or 0
            decided[p["portfolio"]] += 1
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

    def rets_of(pf: str) -> list[float]:
        s = equity_by_pf.get(pf, {})
        return stats.returns([capital[pf]] + [s[c] for c in sorted(s)]) if s else []

    portfolios: list[dict[str, Any]] = []
    for pf in ids:
        st = states[pf]
        s = equity_by_pf.get(pf, {})
        series = [capital[pf]] + [s[c] for c in sorted(s)]
        final = series[-1]
        rets = stats.returns(series)
        n = len(s)
        enough = n >= MIN_CYCLES_STATS
        sh = stats.sharpe(rets) if len(rets) >= 2 else None
        ci = stats.sharpe_ci(rets) if enough else None
        tr = stats.total_return(series)
        dist = None
        if pf != BASELINE and BASELINE in equity_by_pf and len(rets) >= 2:
            base = rets_of(BASELINE)
            m = min(len(base), len(rets))
            if m >= 2:
                d = stats.distinguishable(rets[-m:], base[-m:])
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
        portfolios.append({
            "id": pf, "slug": slug(pf), "name": nom(pf), "kind": kinds[pf], "description": DESCRIPTIONS.get(pf),
            "capital_ueur": capital[pf], "equity_ueur": final, "base100": final / capital[pf] * 100,
            "n_cycles": n, "total_return": tr, "max_drawdown": stats.max_drawdown(series),
            "sharpe": sh if enough else None, "sharpe_ci": list(ci) if ci else None, "too_early": not enough,
            "fees_paid_ueur": st.fees_paid_ueur, "realized_pnl_ueur": st.realized_pnl_ueur,
            "n_trades": len(trades.get(pf, ())), "api_cost_uusd": costs[pf] if kinds[pf] == "llm" else None,
            "rank_percentile": stats.rank_in_distribution(tr, distribution) if distribution else None,
            "distinguishable": dist, "cash_ueur": st.cash_ueur, "halted": st.halted,
            "frozen_until_ts": st.frozen_until_ts if st.frozen_until_ts > now else 0,
            "positions": positions,
            "n_decided": decided[pf] if kinds[pf] == "llm" else None,
            "skipped": dict(skipped.get(pf, {})), "rejects": dict(rejects.get(pf, {})),
            "decisions_total": len(decisions.get(pf, ())),
            "decisions": decisions.get(pf, [])[:DECISIONS_MAX],
            "series_ueur": series,
        })  # fmt: skip

    chart = []
    for p in portfolios:
        s = equity_by_pf.get(p["id"], {})
        vals: list[float | None] = [100.0] if x0 is not None else []
        vals += [round(s[c] / capital[p["id"]] * 100, 4) if c in s else None for c in all_cycles]
        chart.append({"id": p["id"], "name": p["name"], "kind": p["kind"], "values": vals})

    cfg_events = [e for e in events if e["type"] == "config_loaded"]
    cfg_last = cfg_events[-1]["payload"] if cfg_events else {}
    llm_dist = [p for p in portfolios if p["kind"] == "llm" and p["distinguishable"]]
    any_distinguishable = any(p["distinguishable"]["significant"] for p in llm_dist)
    return {
        "venue_mode": config.venue_mode,
        "generated_ts": now,
        "n_cycles": len(all_cycles),
        "first_cycle_ts": all_cycles[0] if all_cycles else None,
        "last_cycle_ts": all_cycles[-1] if all_cycles else None,
        "interval_s": config.interval_s,
        "decider_backend": getattr(config, "decider_backend", None),
        "last_quote_ts": last_quote_ts,
        "min_cycles_stats": MIN_CYCLES_STATS,
        "any_llm_distinguishable": any_distinguishable,
        "distribution": dist_summary,
        "distribution_note": dist_note,
        "portfolios": portfolios,
        "chart": {"x": x, "series": chart},
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
            "models": [{"portfolio": m.portfolio, "model": m.model, "daily_budget_uusd": m.daily_budget_uusd,
                        "price_in_uusd_per_mtok": m.price_in_uusd_per_mtok,
                        "price_out_uusd_per_mtok": m.price_out_uusd_per_mtok} for m in config.models],
            "policy": {f.name: (list(getattr(policy, f.name)) if f.name == "symbols" else getattr(policy, f.name))
                       for f in fields(Policy) if f.name != "sha256"},
        },
    }
