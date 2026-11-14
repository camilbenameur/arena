"""Journal synthétique de la ligue dérivés, cohérent pour le ledger du moteur (fills, funding, equity recalculés).

Deux jours, un tick toutes les 5 min, 4 IA et 3 témoins. Couvre : ouverture long et short avec stop et objectif,
refus du garde-fou, stop touché par la veille, réveil, ronde sautée (budget), réponse sans décision, funding payé
et reçu, gel. Y glisse aussi des champs privés (chemins, stderr, version du CLI, outils offerts, message d'alerte)
pour vérifier qu'ils ne sortent jamais sur le site.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from arene.journal import Journal
from arene.perp.ledger import (
    PerpBook,
    equity_ueur,
    funding_amount_ueur,
    gross_exposure_ueur,
    qty_seconds,
    unrealized_ueur,
)

T0 = 1_794_528_000  # 13/11/2026 ? multiple de 3600 ; les rendez-vous tombent à k*14400 + 7200
FX = (1_105_100, 1_105_160)
BASE = {"BTC-PERP": 88_650_000_000, "ETH-PERP": 3_200_000_000, "SOL-PERP": 140_000_000, "XRP-PERP": 550_000,
        "LINK-PERP": 14_000_000, "LTC-PERP": 85_000_000}  # fmt: skip
PF_KRAKEN = {"BTC-PERP": "PF_XBTUSD", "ETH-PERP": "PF_ETHUSD", "SOL-PERP": "PF_SOLUSD", "XRP-PERP": "PF_XRPUSD",
             "LINK-PERP": "PF_LINKUSD", "LTC-PERP": "PF_LTCUSD"}  # fmt: skip
LLMS = ["llm-perp:claude-haiku-5-5", "llm-perp:claude-sonnet-5-5", "llm-perp:claude-opus-5-5", "llm-perp:claude-fable-5-2"]
TEMOINS = ["benchmark-perp:basket-1x", "benchmark-perp:trend", "benchmark-perp:random"]
CONSEIL = "council-perp:haiku"
ARG_CARTO = "Régime baissier net sur ETH : 4 h sous SMA20, MACD négatif. Short avec stop serré."
ARG_AVOCAT = "Le short ETH arrive sur la bande basse : la baisse est déjà faite, le rebond guette."
RAISON_PRESIDENT = "Short ETH à 300 %, stop 3 %. Je suis le Cartographe et le Suiveur ; j'écarte l'Avocat."
FABLE_RAISON = "ETH perd 3 % sur 24 h, funding positif : les longs paient. RSI 4 h sous 45. Je vends 25 % à découvert."
INVALIDATION = "clôture 4 h au-dessus de 3 300 $"
SECRET = "/tmp/arena/var-perp/rounds/x"
NOTE_ALERTE = "cassure du plus haut de la veille"
INVAL_ORDRE = "SOL clôture 4 h sous 120 $"
ALERTE_BTC = "a1" * 32
ORDRE_SOL = "e1" * 32
ALERTE_LTC = "a2" * 32
ALERTE_ETH = "a3" * 32


def prix(inst: str, ts: int) -> int:
    k = list(BASE).index(inst)
    t = (ts - T0) / 86_400
    drift = {0: 0.02, 1: -0.05, 2: 0.03, 3: -0.01, 4: 0.015, 5: -0.02}[k] * t
    return int(BASE[inst] * (1 + drift + 0.012 * math.sin(t * 9 + k)))


def qty_pour(eur: int, inst: str, ts: int) -> int:
    usd = eur * FX[0] // 1_000_000  # µEUR -> µUSD
    return usd * 100_000_000 // prix(inst, ts)


class Gen:
    def __init__(self, path: Path) -> None:
        self.j = Journal(path)
        self.book = PerpBook()
        self.n = 0

    def add(self, t: str, p: dict, ts: int) -> None:
        rec = self.j.append(t, p, ts)
        self.book.apply(rec)

    def fill(self, pf: str, inst: str, qty: int, ts: int, reason: str = "intent", oid: str | None = None) -> str:
        self.n += 1
        oid = oid or f"t:{pf}:{inst}:{self.n}"
        px = prix(inst, ts)
        fee = abs(qty) * px // 100_000_000 * 7 // 10_000 * 1_000_000 // FX[0] + 1
        self.add("perp_fill", {"order_id": oid, "portfolio": pf, "instrument": inst, "qty": qty, "price_uusd": px,
                               "fee_ueur": fee, "fx_bid": FX[0], "fx_ask": FX[1], "reason": reason,
                               "fill_model_version": "pessimiste-perp-v1", "ts": ts}, ts)  # fmt: skip
        return oid

    def cond(self, pf: str, inst: str, kind: str, px: int | None, ts: int) -> None:
        self.add("conditional_order", {"portfolio": pf, "instrument": inst, "kind": kind, "price_uusd": px, "ts": ts}, ts)


def build(path: Path, *, ruine: bool = False) -> Path:
    """`ruine` : le Conseil Haiku finit arrêté (`portfolio_halted`, ruine à -90 %)."""
    g = Gen(path)
    for pf in TEMOINS + LLMS:
        g.add("portfolio_opened", {"portfolio": pf, "kind": "llm" if pf in LLMS else "benchmark", "league": "perp",
                                   "capital_ueur": 1_000_000_000, "venue_mode": "paper"}, T0)  # fmt: skip
    rdvs = [T0 + 7_200 + 14_400 * k for k in range(12)]
    wake = rdvs[2] + 5_400
    fin = T0 + 2 * 86_400
    rnd = 0
    for ts in range(T0 + 300, fin + 1, 300):
        # Funding de l'heure close, pour chaque position tenue pendant l'heure.
        if ts % 3_600 == 0:
            for pf, acc in g.book.states.items():
                for inst, hist in acc.qty_history.items():
                    qs = qty_seconds(hist, ts - 3_600, ts)
                    if qs:
                        rate = prix(inst, ts) // 100 * (1 if inst != "XRP-PERP" else -1)  # ±0,001 % par heure
                        if inst == "LTC-PERP" and ts == T0 + 4 * 3_600:
                            g.add("funding_missing", {"portfolio": pf, "instrument": inst, "stamp": ts, "qty_seconds": qs}, ts)
                            continue
                        amt = funding_amount_ueur(qs, rate, *FX)
                        g.add("funding", {"portfolio": pf, "instrument": inst, "stamp": ts, "qty_seconds": qs, "rate_nusd": rate,
                                          "fx_bid": FX[0], "fx_ask": FX[1], "amount_ueur": amt}, ts)  # fmt: skip
        if ts == rdvs[10] - 600:  # le Conseil Haiku entre en cours de route
            g.add("portfolio_opened", {"portfolio": CONSEIL, "kind": "council", "league": "perp", "capital_ueur": 1_000_000_000,
                                       "venue_mode": "paper"}, ts)  # fmt: skip
        if ts in (rdvs[10], rdvs[11]):
            _ronde_conseil(g, ts, ouvre=ts == rdvs[10])
        if ruine and ts == fin:
            g.add("portfolio_halted", {"portfolio": CONSEIL, "reason": "drawdown", "until_ts": 0}, ts)
        if ts in rdvs or ts == wake:
            rnd += 1
            _ronde(g, ts, rnd, wake=ts == wake)
        if ts == rdvs[1] + 1_800:  # l'ordre d'entrée de Fable est franchi entre deux rondes
            _ordre_declenche(g, ts)
        if ts == rdvs[1] + 3_600:  # son alerte BTC aussi : ronde privée « alert »
            _alerte_et_ronde_privee(g, ts)
        if ts == rdvs[1] + 3_000:  # la veille touche le stop de Sonnet
            acc = g.book.states["llm-perp:claude-sonnet-5-5"]
            if "BTC-PERP" in acc.positions:
                g.fill("llm-perp:claude-sonnet-5-5", "BTC-PERP", -acc.positions["BTC-PERP"].qty, ts + 59, "stop",
                       f"stop:llm-perp:claude-sonnet-5-5:BTC-PERP:1:{ts}")  # fmt: skip
        if rdvs[11] < ts <= rdvs[11] + 2_400 and ts % 600 == 0:  # appels réguliers de Sonnet, sans ordre
            _appel_sonnet(g, ts, fin)
        if ts == rdvs[3] + 600:
            g.add("portfolio_frozen", {"portfolio": "llm-perp:claude-opus-5-5", "reason": "daily_loss", "until_ts": ts + 86_400 * 30}, ts)
            g.add("alert", {"level": "action", "code": "perp_llm_round_failed", "message": f"OSError: {SECRET} the host"}, ts)
        for pf, acc in g.book.states.items():
            marks = {i: prix(i, ts) for i in acc.positions}
            g.add("perp_equity", {"portfolio": pf, "ts": ts, "collateral_ueur": acc.collateral_ueur,
                                  "unrealized_ueur": unrealized_ueur(acc, marks, *FX), "equity_ueur": equity_ueur(acc, marks, *FX),
                                  "gross_ueur": gross_exposure_ueur(acc, marks, *FX), "marks": marks,
                                  "fx_bid": FX[0], "fx_ask": FX[1]}, ts)  # fmt: skip
        g.add("perp_tick", {"tick": ts, "last_minute": ts - 60, "minutes": 5, "fills": 0, "rounds": [], "pending_funding": [],
                            "notes": [f"note {SECRET}"], "problems": []}, ts)  # fmt: skip
    return path


def _decision(g: Gen, pf: str, rnd: int, ts: int, kind: str, actions: list[dict], raison: str, outils: list[tuple[str, dict]]) -> None:
    trig = json.dumps({"instrument": "PF_SOLUSD", "move_bp": -342, "window_s": 3600, "pending_ts": ts - 300}) if kind == "wakeup" else "null"
    g.add("round_data", {"portfolio": pf, "round": rnd, "kind": kind, "trigger": trig, "sha256": "a" * 64, "message_sha256": "b" * 64,
                         "path": SECRET, "llm_config_sha256": "c" * 64, "budget_ceiling_uusd": 1_000_000}, ts)  # fmt: skip
    for n, (tool, args) in enumerate(outils, 1):
        g.add("tool_call", {"portfolio": pf, "round": rnd, "n": n, "tool": tool, "arguments": json.dumps(args, sort_keys=True),
                            "response": json.dumps({"brut": SECRET}), "response_sha256": "d" * 64, "is_error": False}, ts)  # fmt: skip
    g.add("agent_decision", {
        "portfolio": pf, "round": rnd, "kind": kind, "model_requested": pf.split(":")[1], "model_returned": pf.split(":")[1],
        "prompt_sha256": "e" * 64, "parsed": {"actions": actions, "justification": raison, "action_errors": []}, "parse_error": None,
        "tool_calls": len(outils), "num_turns": 3, "input_tokens": 12, "output_tokens": 640, "cache_read_tokens": 6400,
        "cache_write_tokens": 0, "cost_uusd": 75_000, "latency_ms": 13_200, "attempts": 1, "first_error": None, "cli_rc": 0,
        "cli_version": "2.1.99-secret", "stderr_tail": f"warning {SECRET}", "mcp_status": "connected",
        "tools_offered": ["mcp__arene__bougies-secret"], "stream_sha256": "f" * 64, "budget_ceiling_uusd": 1_000_000,
        "result_seen": True, "charge_ceiling": False,
    }, ts)  # fmt: skip


def _action(inst: str, action: str, size: str, stop: str | None = None, tp: str | None = None, inval: str | None = None) -> dict:
    return {"instrument": PF_KRAKEN[inst], "action": action, "size_pct": size, "stop_pct": stop, "take_profit_pct": tp,
            "horizon_h": 24, "expected_move_pct": "5", "confidence_pct": "60", "invalidation": inval}  # fmt: skip


def _executer(g: Gen, pf: str, inst: str, action: str, ts: int, k: int, approuve: bool, motifs: list[str] | None = None,
              qty: int = 0, stop_pct: int | None = None, tp_pct: int | None = None) -> None:  # fmt: skip
    iid = f"{pf}:{ts}:{k}".encode().hex()[:64]
    g.add("perp_verdict", {"intent_id": iid, "portfolio": pf, "instrument": PF_KRAKEN[inst], "action": action, "approved": approuve,
                           "reasons": motifs or [], "qty": qty if approuve else None, "policy_sha256": "9" * 64, "error": None}, ts)  # fmt: skip
    if not approuve:
        return
    g.fill(pf, inst, qty, ts, "intent", iid)
    px = prix(inst, ts)
    if stop_pct:
        g.cond(pf, inst, "stop", px * (100 - stop_pct) // 100 if qty > 0 else px * (100 + stop_pct) // 100, ts)
    if tp_pct:
        g.cond(pf, inst, "take_profit", px * (100 + tp_pct) // 100 if qty > 0 else px * (100 - tp_pct) // 100, ts)
    g.add("perp_execution", {"intent_id": iid, "portfolio": pf, "instrument": PF_KRAKEN[inst], "status": "filled", "error": None}, ts)


def _ordre_declenche(g: Gen, ts: int) -> None:
    """Spec alertes-ordres §2.6 : franchissement, verdict, fill, stop et exécution, tous avec intent_id = id de l'ordre."""
    fable = LLMS[3]
    px = prix("SOL-PERP", ts)
    g.add("agent_entry_triggered", {"portfolio": fable, "id": ORDRE_SOL, "instrument": "PF_SOLUSD", "side": "long", "condition": "below",
                                    "price_uusd": px, "minute": ts - 120, "mark_high_uusd": px + 10, "mark_low_uusd": px - 10}, ts)  # fmt: skip
    qty = qty_pour(100_000_000, "SOL-PERP", ts)
    g.add("perp_verdict", {"intent_id": ORDRE_SOL, "portfolio": fable, "instrument": "PF_SOLUSD", "action": "open_long", "approved": True,
                           "reasons": [], "qty": qty, "policy_sha256": "9" * 64, "error": None}, ts)  # fmt: skip
    g.fill(fable, "SOL-PERP", qty, ts, "intent", ORDRE_SOL)
    g.cond(fable, "SOL-PERP", "stop", px * 96 // 100, ts)
    g.cond(fable, "SOL-PERP", "take_profit", px * 108 // 100, ts)
    g.add("perp_execution", {"intent_id": ORDRE_SOL, "portfolio": fable, "instrument": "PF_SOLUSD", "status": "filled", "error": None}, ts)
    g.add("agent_order_ended", {"portfolio": fable, "id": ALERTE_LTC, "kind": "alert", "reason": "expired"}, ts)


def _appel_sonnet(g: Gen, ts: int, fin: int) -> None:
    """Un appel régulier (ou rappel demandé) de Sonnet après le dernier rendez-vous : aucune action. Le dernier
    demande un rappel encore à venir au moment de la construction du site, et un rappel invalide est refusé."""
    sonnet = LLMS[1]
    kind = "scheduled" if ts % 1_800 == 0 else "cadence"
    _decision(g, sonnet, ts, ts + 10, kind, [], f"Rien à faire à {ts % 86_400 // 60} min : marché calme.", [])
    g.add("agent_orders_set", {"portfolio": sonnet, "round": ts, "created_ts": ts + 10, "alerts": [], "entry_orders": [],
                               "rejected": [{"kind": "wakeup", "k": 0, "error": f"next_wakeup_min out of range {SECRET}"}]}, ts + 10)  # fmt: skip
    g.add("agent_wakeup_set", {"portfolio": sonnet, "round": ts, "minutes": 30, "due_ts": fin + 1_500}, ts + 11)


def _alerte_et_ronde_privee(g: Gen, ts: int) -> None:
    fable = LLMS[3]
    px = prix("BTC-PERP", ts)
    g.add("agent_alert_triggered", {"portfolio": fable, "id": ALERTE_BTC, "instrument": "PF_XBTUSD", "condition": "above",
                                    "price_uusd": px, "minute": ts - 60, "mark_high_uusd": px, "mark_low_uusd": px - 5}, ts)  # fmt: skip
    r = ts + 300
    trig = {"alert_id": ALERTE_BTC, "instrument": "PF_XBTUSD", "condition": "above", "price_usd": "89540.5", "note": NOTE_ALERTE}
    g.add("perp_round", {"round": r, "kind": "alert", "portfolios": [fable], "trigger": trig, "ts": r}, r)
    g.add("round_data", {"portfolio": fable, "round": r, "kind": "alert", "trigger": json.dumps(trig), "sha256": "a" * 64,
                         "message_sha256": "b" * 64, "path": SECRET}, r + 10)  # fmt: skip
    g.add("agent_decision", {"portfolio": fable, "round": r, "kind": "alert", "model_requested": "claude-fable-5-2",
                             "parsed": {"actions": [], "justification": "La cassure ne tient pas sur le volume. J'attends.", "action_errors": []},
                             "parse_error": None, "cost_uusd": 40_000}, r + 40)  # fmt: skip
    g.add("agent_orders_set", {"portfolio": fable, "round": r, "created_ts": r + 40, "rejected": [], "entry_orders": [],
                               "alerts": [{"id": ALERTE_ETH, "instrument": "PF_ETHUSD", "condition": "below",
                                           "price_uusd": 3_050_000_000, "note": "support hebdomadaire", "expires_ts": r + 86_400 * 30}]}, r + 40)  # fmt: skip
    g.add("perp_round_done", {"round": r}, r + 60)


def _ronde(g: Gen, ts: int, rnd: int, *, wake: bool) -> None:
    kind = "wakeup" if wake else "rendezvous"
    trig = {"instrument": "PF_SOLUSD", "move_bp": -342, "window_s": 3600, "pending_ts": ts - 300} if wake else None
    g.add("perp_round", {"round": ts, "kind": kind, "trigger": trig, "ts": ts}, ts)
    t = ts + 30
    if rnd == 1:  # témoins : panier 1/6 long partout, tendance long/short avec stop 10 %
        for i, inst in enumerate(BASE):
            g.fill("benchmark-perp:basket-1x", inst, qty_pour(166_000_000, inst, t), t)
            q = qty_pour(160_000_000, inst, t) * (1 if i % 2 == 0 else -1)
            g.fill("benchmark-perp:trend", inst, q, t)
            px = prix(inst, t)
            g.cond("benchmark-perp:trend", inst, "stop", px * 90 // 100 if q > 0 else px * 110 // 100, t)
        _executer(g, "benchmark-perp:random", "LTC-PERP", "open_long", t, 0, True, qty=qty_pour(100_000_000, "LTC-PERP", t), stop_pct=5)
        _executer(g, "benchmark-perp:random", "XRP-PERP", "open_short", t, 1, False, ["EDGE_TOO_SMALL", "MAX_TRADE_LOSS"])
    t = ts + 60
    fable, sonnet, opus, haiku = LLMS[3], LLMS[1], LLMS[2], LLMS[0]
    if rnd == 1:
        _decision(g, fable, ts, t, kind, [_action("ETH-PERP", "open_short", "25", "4", "8", INVALIDATION)], FABLE_RAISON,
                  [("indicateurs", {"instrument": "PF_ETHUSD", "intervalle": "4h"}), ("derives", {"instrument": "PF_ETHUSD"})])
        _executer(g, fable, "ETH-PERP", "open_short", t, 0, True, qty=-qty_pour(250_000_000, "ETH-PERP", t), stop_pct=4, tp_pct=8)
        _decision(g, sonnet, ts, t, kind, [_action("BTC-PERP", "open_long", "30", "1", None, "BTC sous 87 000 $")],
                  "Tendance haussière sur 4 h, funding neutre. Long BTC 30 %, stop serré.", [("bougies", {"instrument": "PF_XBTUSD", "intervalle": "1h", "n": 24})])
        _executer(g, sonnet, "BTC-PERP", "open_long", t, 0, True, qty=qty_pour(300_000_000, "BTC-PERP", t), stop_pct=1)
        _decision(g, opus, ts, t, kind, [_action("SOL-PERP", "open_long", "20", "5", "10", "SOL sous 130 $"),
                                         _action("LINK-PERP", "open_short", "10", "3", None, "LINK au-dessus de 15 $")],
                  "SOL rebondit sur un support, LINK s'essouffle. Deux positions modestes.", [("simuler_ordre", {"instrument": "PF_SOLUSD", "action": "open_long", "size_pct": 20})])
        _executer(g, opus, "SOL-PERP", "open_long", t, 0, True, qty=qty_pour(200_000_000, "SOL-PERP", t), stop_pct=5, tp_pct=10)
        _executer(g, opus, "LINK-PERP", "open_short", t, 1, False, ["EDGE_TOO_SMALL", "TOO_SOON"])
        _decision(g, haiku, ts, t, kind, [], "Signal contradictoire, le coût aller-retour n'est pas couvert. Je ne fais rien.", [])
    elif rnd == 2:
        _decision(g, fable, ts, t, kind, [_action("ETH-PERP", "close", "100")], "L'objectif est loin, le funding s'inverse : je ferme.", [])
        acc = g.book.states[fable]
        _executer(g, fable, "ETH-PERP", "close", t, 0, True, qty=-acc.positions["ETH-PERP"].qty)
        exp = t + 4 * 3_600
        g.add("agent_orders_set", {
            "portfolio": fable, "round": ts, "created_ts": t,
            "alerts": [
                {"id": ALERTE_BTC, "instrument": "PF_XBTUSD", "condition": "above", "price_uusd": prix("BTC-PERP", t) * 101 // 100,
                 "note": NOTE_ALERTE, "expires_ts": exp},
                {"id": ALERTE_LTC, "instrument": "PF_LTCUSD", "condition": "below", "price_uusd": prix("LTC-PERP", t) * 90 // 100,
                 "note": None, "expires_ts": t + 3_600},
            ],
            "entry_orders": [
                {"id": ORDRE_SOL, "instrument": "PF_SOLUSD", "side": "long", "condition": "below", "price_uusd": prix("SOL-PERP", t) * 99 // 100,
                 "size_bp": 1_000, "stop_bp": 400, "take_profit_bp": 800, "horizon_h": 24, "expected_move_bp": 500,
                 "confidence_pct": 55, "invalidation": INVAL_ORDRE, "expires_ts": exp},
            ],
            "rejected": [{"kind": "entry", "k": 1, "error": f"level more than 25 % away from the mark {SECRET}"}],
        }, t)  # fmt: skip
        g.add("perp_llm_skipped", {"portfolio": haiku, "round": ts, "reason": "daily_budget"}, t)
    elif rnd == 3:
        g.add("round_data", {"portfolio": haiku, "round": ts, "kind": kind, "trigger": "null", "sha256": "a" * 64, "message_sha256": "b" * 64,
                             "path": SECRET, "llm_config_sha256": "c" * 64, "budget_ceiling_uusd": 100_000}, t)  # fmt: skip
        g.add("agent_decision", {"portfolio": haiku, "round": ts, "kind": kind, "model_requested": "claude-haiku-5-5", "parsed": None,
                                 "parse_error": f"no structured output: Traceback {SECRET}", "cost_uusd": 1_600, "latency_ms": 8_800,
                                 "stderr_tail": SECRET, "cli_version": "2.1.99-secret"}, t)  # fmt: skip
    if wake:
        _decision(g, opus, ts, t, kind, [_action("SOL-PERP", "reduce", "50")], "SOL chute de 3,4 % en une heure : je réduis de moitié.", [])
        acc = g.book.states[opus]
        _executer(g, opus, "SOL-PERP", "reduce", t, 0, True, qty=-acc.positions["SOL-PERP"].qty // 2)
    g.add("perp_round_done", {"round": ts}, t + 30)


def _avis(g: Gen, ts: int, rnd: int, member: str, name: str, stage: str, opinion: dict | None, error: str | None = None) -> None:
    g.add("council_opinion", {"portfolio": CONSEIL, "round": rnd, "member": member, "name": name, "stage": stage,
                              "persona_sha256": "1" * 64, "opinion": opinion, "error": error, "cost_uusd": 1_500,
                              "input_tokens": 4, "output_tokens": 900, "latency_ms": 8_000, "tool_calls": 1,
                              "model_returned": "claude-haiku-5-5", "stream_sha256": "2" * 64}, ts)  # fmt: skip


def _ronde_conseil(g: Gen, ts: int, *, ouvre: bool) -> None:
    """Une ronde du conseil : 8 avis (étape A, dont un absent), l'Avocat (B), puis la décision du Président (C)."""
    t = ts + 50
    kind = "rendezvous" if ouvre else "cadence"
    g.add("round_data", {"portfolio": CONSEIL, "round": ts, "kind": kind, "trigger": "null", "sha256": "a" * 64, "message_sha256": "b" * 64,
                         "path": SECRET, "council_config_sha256": "c" * 64, "budget_ceiling_uusd": 1_000_000}, t)  # fmt: skip
    short = {"instrument": "PF_ETHUSD", "position": "short", "conviction": 65, "taille_pct": "250", "stop_pct": "2.5", "niveau_cle_usd": "3150"}
    plat = {"instrument": "PF_ETHUSD", "position": "plat", "conviction": 40, "taille_pct": None, "stop_pct": None, "niveau_cle_usd": None}
    membres = [("cartographe", "Le Cartographe"), ("suiveur", "Le Suiveur"), ("chasseur", "Le Chasseur de cassures"),
               ("contrarien", "Le Contrarien"), ("carnet", "Le Lecteur de carnet"), ("tresorier", "Le Trésorier du levier"),
               ("gardien", "Le Gardien du risque"), ("memorialiste", "Le Mémorialiste")]  # fmt: skip
    for k, (m, n) in enumerate(membres):
        if m == "carnet":
            _avis(g, t, ts, m, n, "A", None, f"member crashed: OSError: {SECRET}")
            continue
        avis = [plat] if m == "contrarien" else [short]
        _avis(g, t, ts, m, n, "A", {"avis": avis, "cible": None, "argument": ARG_CARTO if m == "cartographe" else f"Avis {k} sur ETH."})
    _avis(g, t, ts, "avocat", "L'Avocat du diable", "B",
          {"avis": [plat], "cible": {"instrument": "PF_ETHUSD", "sens": "short"}, "argument": ARG_AVOCAT})
    for n, (m, tool) in enumerate([("cartographe", "indicateurs"), ("avocat", "derives"), ("president", "simuler_ordre")], 1):
        g.add("tool_call", {"portfolio": CONSEIL, "round": ts, "member": m, "n": n, "tool": tool,
                            "arguments": json.dumps({"instrument": "PF_ETHUSD", "intervalle": "4h"}), "response": SECRET,
                            "response_sha256": "d" * 64, "is_error": False}, t)  # fmt: skip
    actions = [_action("ETH-PERP", "open_short", "300", "3", "4", "reprise de 3 300 $"), _action("ETH-PERP", "open_short", "500", "15")] if ouvre else []
    g.add("agent_decision", {
        "portfolio": CONSEIL, "round": ts, "kind": kind, "model_requested": "claude-haiku-5-5", "model_returned": "claude-haiku-5-5",
        "parsed": {"actions": actions, "justification": RAISON_PRESIDENT if ouvre else "Je garde le short.", "action_errors": []},
        "parse_error": None, "cost_uusd": 24_849, "latency_ms": 41_000, "cli_version": "2.1.99-secret", "stderr_tail": SECRET,
        "council": {"config_sha256": "c" * 64, "prompts_sha256": "e" * 64, "members_ok": 8, "members_failed": ["carnet"],
                    "president_cost_uusd": 3_905, "president_latency_ms": 9_861, "president_tool_calls": 1},
    }, t)  # fmt: skip
    if ouvre:
        _executer(g, CONSEIL, "ETH-PERP", "open_short", t, 0, True, qty=-qty_pour(3_000_000_000, "ETH-PERP", t), stop_pct=3, tp_pct=4)
        _executer(g, CONSEIL, "ETH-PERP", "open_short", t, 1, False, ["MAX_LEVERAGE", "LIQUIDATION_BEFORE_STOP"])
