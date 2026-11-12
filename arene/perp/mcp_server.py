"""Read-only MCP server of an agent round (study §2.2): a stdio JSON-RPC server, no dependency.

    python -m arene.perp.mcp_server --round-dir DIR --portfolio NAME [--max-calls 4]

It serves six tools from the frozen `DIR/round.json` (built by `round_data.build_round`) and NEVER touches the
network, the journal or a file outside DIR. The fifth call (by default) gets an error asking the model to give
its decision. Every call is traced in `DIR/trace.jsonl` (debugging; the cycle journals the calls itself from
the CLI's stream). Tool texts are in French, like the system prompt.

Numbers sent by the model are parsed as Decimal (never float) and converted to integers. Arguments are checked
against each tool's input schema before the call (a rejected call still counts in the budget); no input, however
odd, can stop the server: every request gets a reply.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from arene.perp import indicators as ind
from arene.perp.agent import canonical_json
from arene.perp.ledger import MarginAccount, PerpPosition
from arene.perp.policy import PerpPolicy
from arene.perp.riskd import InstrumentMarket, PerpCounters, PerpIntent, PerpMarketView, evaluate_perp
from arene.perp.sim import SimParams
from arene.perp.types import InstrumentSpec

PROTOCOL_VERSION = "2025-06-18"
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_PCT = 10_000  # any percent beyond this is refused before any arithmetic
RESPONSE_MAX_CHARS = 2_500  # about 700 tokens: the history is cut to fit
HISTORY_JUSTIFICATION = 120
SERVER_NAME = "arene"
INSTRUMENT_DESC = "Contrat : PF_XBTUSD, PF_ETHUSD, PF_SOLUSD, PF_XRPUSD, PF_LINKUSD ou PF_LTCUSD."


def usd(uusd: int | None) -> str | None:
    """µUSD -> decimal string of USD without trailing zeros."""
    if uusd is None:
        return None
    s = format(Decimal(uusd).scaleb(-6), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def eur(ueur: int | None) -> str | None:
    return None if ueur is None else format(Decimal(ueur).scaleb(-6).quantize(Decimal("0.01")), "f")


def qty(q: int) -> str:
    s = format(Decimal(q).scaleb(-8), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def pct_e12_hour(rate: int | None) -> str | None:
    """Relative hourly rate x 1e12 -> percent per hour as a string."""
    return None if rate is None else format(Decimal(rate).scaleb(-10).normalize(), "f")


TOOLS = [
    {
        "name": "bougies",
        "description": "Bougies closes (horodatage UTC, ouverture, plus haut, plus bas, clôture, en USD) d'un contrat.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "instrument": {"type": "string", "description": INSTRUMENT_DESC},
                "intervalle": {"type": "string", "enum": ["5m", "1h", "4h", "1d"]},
                "n": {"type": "integer", "minimum": 1, "maximum": 24},
            },
            "required": ["instrument", "intervalle"],
        },
    },
    {
        "name": "carnet",
        "description": "Carnet d'ordres relevé au début de la ronde : meilleurs niveaux, spread, profondeur à ±0,5 % et ±1 %.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "instrument": {"type": "string", "description": INSTRUMENT_DESC},
                "profondeur": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["instrument"],
        },
    },
    {
        "name": "derives",
        "description": "Funding (courant, prévu, moyennes 24 h et 7 j, en % par heure), open interest et sa variation sur 24 h, écart mark - index.",
        "inputSchema": {
            "type": "object",
            "properties": {"instrument": {"type": "string", "description": INSTRUMENT_DESC}},
            "required": ["instrument"],
        },
    },
    {
        "name": "indicateurs",
        "description": "Moyennes mobiles, MACD, RSI 14, ATR 14, volatilité réalisée et bandes de Bollinger, calculés sur les bougies closes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "instrument": {"type": "string", "description": INSTRUMENT_DESC},
                "intervalle": {"type": "string", "enum": ["5m", "1h", "4h", "1d"]},
            },
            "required": ["instrument", "intervalle"],
        },
    },
    {
        "name": "simuler_ordre",
        "description": (
            "Verdict du garde-fou (riskd) pour une action, SANS l'exécuter : quantité, prix attendu, stop, "
            "perte au stop, levier du compte après l'ordre, codes de refus. Même calcul que la décision finale."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "instrument": {"type": "string", "description": INSTRUMENT_DESC},
                "action": {"type": "string", "enum": ["open_long", "open_short", "reduce", "close"]},
                "size_pct": {"type": ["number", "null"]},
                "stop_pct": {"type": ["number", "null"]},
                "take_profit_pct": {"type": ["number", "null"]},
                "horizon_h": {"type": ["integer", "null"], "minimum": 1, "maximum": 168},
                "expected_move_pct": {"type": ["number", "null"]},
            },
            "required": ["instrument", "action"],
        },
    },
    {
        "name": "historique",
        "description": "Tes dernières décisions (actions, justification abrégée) et les exécutions qui ont suivi.",
        "inputSchema": {
            "type": "object",
            "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 10}},
        },
    },
]


def pct_to_bp(v: Any, rounding: str = ROUND_HALF_UP) -> int | None:
    if v is None:
        return None
    try:
        d = Decimal(str(v))
    except InvalidOperation as exc:
        raise ValueError(f"nombre illisible : {v!r}") from exc
    if not d.is_finite() or d.adjusted() > 6 or d.copy_abs() > MAX_PCT:
        raise ValueError(f"nombre hors bornes : {v!r}")
    return int((d * 100).to_integral_value(rounding=rounding))


SCHEMAS = {t["name"]: t["inputSchema"] for t in TOOLS}
_TYPES = {"string": "un texte", "integer": "un entier", "number": "un nombre", "null": "null"}


def _sane(v: Any) -> bool:
    """A number small enough for any arithmetic (no context-dependent operation is used to tell)."""
    if isinstance(v, Decimal):
        return v.is_finite() and v.adjusted() <= 6
    return not isinstance(v, int) or isinstance(v, bool) or -(10**7) < v < 10**7


def _is(v: Any, typ: str) -> bool:
    if typ == "null":
        return v is None
    if typ == "string":
        return isinstance(v, str)
    if isinstance(v, bool):
        return False
    if typ == "integer":
        return isinstance(v, int) or (isinstance(v, Decimal) and v.is_finite() and v == v.to_integral_value())
    return isinstance(v, int | Decimal)


def check_arguments(name: str, args: Any) -> str | None:
    """A short French message if `args` does not match the tool's input schema, else None."""
    schema = SCHEMAS[name]
    if not isinstance(args, dict):
        return "les arguments doivent être un objet JSON"
    props = schema["properties"]
    for k in [k for k, v in args.items() if v is None and k not in schema.get("required", [])]:
        del args[k]  # an explicit null for an optional field means "absent"
    unknown = sorted(set(args) - set(props))
    if unknown:
        return f"argument inconnu : {', '.join(unknown)} (attendus : {', '.join(props)})"
    for req in schema.get("required", []):
        if args.get(req) is None:
            return f"argument obligatoire manquant : {req}"
    for k, v in args.items():
        spec = props[k]
        if not _sane(v):
            return f"{k} hors bornes"
        types = spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
        if not any(_is(v, ty) for ty in types):
            return f"{k} doit être {' ou '.join(_TYPES[ty] for ty in types)}"
        if v is None:
            continue
        if "enum" in spec and v not in spec["enum"]:
            return f"{k} doit valoir {', '.join(spec['enum'])}"
        if "minimum" in spec and not spec["minimum"] <= v <= spec["maximum"]:
            return f"{k} doit être entre {spec['minimum']} et {spec['maximum']}"
    return None


class RoundTools:
    def __init__(self, round_dir: Path, portfolio: str, max_calls: int) -> None:
        self.dir = round_dir
        self.portfolio = portfolio
        self.max_calls = max_calls
        self.calls = 0
        self.data = json.loads((round_dir / "round.json").read_text(encoding="utf-8"))
        if self.data["meta"]["portfolio"] != portfolio:
            raise ValueError("this round belongs to another portfolio")

    # ------------------------------------------------------------------ dispatch

    def call(self, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """(payload, is_error)."""
        self.calls += 1
        if self.calls > self.max_calls:
            return {
                "erreur": f"budget de {self.max_calls} appels d'outils épuisé : rends ta décision maintenant."
            }, True
        if name not in SCHEMAS:
            return {"erreur": f"outil inconnu : {name} (cet appel compte dans le budget)"}, True
        problem = check_arguments(name, args)
        if problem:
            return {"erreur": f"arguments invalides : {problem} (cet appel compte dans le budget)"}, True
        try:
            return getattr(self, f"t_{name}")(**args), False
        except ValueError as exc:
            return {"erreur": f"arguments invalides : {str(exc)[:200]}"}, True
        except Exception as exc:  # noqa: BLE001 (never let one call stop the server)
            return {"erreur": f"erreur interne de l'outil ({type(exc).__name__})"}, True

    def _market(self, instrument: str) -> dict[str, Any]:
        m = self.data["market"].get(instrument)
        if m is None:
            raise ValueError(f"contrat inconnu : {instrument}")
        return m

    # ------------------------------------------------------------------ tools

    def t_bougies(self, instrument: str, intervalle: str, n: int = 24) -> dict[str, Any]:
        rows = self._market(instrument).get(f"candles_{intervalle}")
        if rows is None:
            raise ValueError(f"intervalle inconnu : {intervalle}")
        n = max(1, min(int(n), 24))
        return {
            "instrument": instrument,
            "intervalle": intervalle,
            "colonnes": ["ts", "ouverture", "haut", "bas", "cloture"],
            "bougies": [[r[0], usd(r[1]), usd(r[2]), usd(r[3]), usd(r[4])] for r in rows[-n:]],
        }

    def t_carnet(self, instrument: str, profondeur: int = 5) -> dict[str, Any]:
        book = self._market(instrument).get("order_book")
        if not book:
            return {"instrument": instrument, "carnet": None, "note": "aucun carnet récent relevé"}
        k = max(1, min(int(profondeur), 10))
        bids, asks = book["bids"], book["asks"]
        if not bids or not asks or bids[0][0] + asks[0][0] <= 0:
            return {
                "instrument": instrument,
                "carnet": None,
                "note": "carnet vide d'un côté",
                "ts": book["ts"],
            }
        best_bid, best_ask = bids[0][0], asks[0][0]
        mid2 = best_bid + best_ask

        def depth(side: list[list[int]], pct_bp: int, below: bool) -> str:
            lim = mid2 * (10_000 - pct_bp) // 20_000 if below else mid2 * (10_000 + pct_bp) // 20_000
            return qty(sum(q for p, q in side if (p >= lim if below else p <= lim)))

        return {
            "instrument": instrument,
            "ts": book["ts"],
            "age_s": self.data["meta"]["now_ts"] - book["ts"],
            "offres_achat": [[usd(p), qty(q)] for p, q in bids[:k]],
            "offres_vente": [[usd(p), qty(q)] for p, q in asks[:k]],
            "spread_bp": (best_ask - best_bid) * 20_000 // mid2,
            "profondeur_0_5pct": {"achat": depth(bids, 50, True), "vente": depth(asks, 50, False)},
            "profondeur_1pct": {"achat": depth(bids, 100, True), "vente": depth(asks, 100, False)},
            "carnet_croise": book["crossed"],
        }

    def t_derives(self, instrument: str) -> dict[str, Any]:
        m = self._market(instrument)
        v = self.data["view"]["instruments"].get(instrument, {})
        now = self.data["meta"]["now_ts"]
        hist = m["funding_history"]

        def avg(since: int) -> str | None:
            xs = [r for ts, r in hist if ts > since]
            return pct_e12_hour(sum(xs) // len(xs)) if xs else None

        oi = m["open_interest"]
        oi_now = oi[-1][1] if oi else None
        oi_24 = next((q for ts, q in oi if ts >= now - 86_400), None)
        mark, index = v.get("mark_uusd"), v.get("index_uusd")
        return {
            "instrument": instrument,
            "funding_courant_pct_heure": pct_e12_hour(v.get("relative_funding_e12")),
            "funding_moyen_24h_pct_heure": avg(now - 86_400),
            "funding_moyen_7j_pct_heure": avg(now - 7 * 86_400),
            "sens": "positif : les longs paient les shorts",
            "open_interest": qty(oi_now) if oi_now is not None else None,
            "open_interest_variation_24h_pct": (
                format(Decimal((oi_now - oi_24) * 100) / Decimal(oi_24), ".2f") if oi_now and oi_24 else None
            ),
            "mark_usd": usd(mark),
            "index_usd": usd(index),
            "ecart_mark_index_bp": (mark - index) * 10_000 // index if mark and index else None,
        }

    def t_indicateurs(self, instrument: str, intervalle: str) -> dict[str, Any]:
        rows = self._market(instrument).get(f"candles_{intervalle}")
        if rows is None:
            raise ValueError(f"intervalle inconnu : {intervalle}")
        s = ind.summary([(r[1], r[2], r[3], r[4]) for r in rows])
        out: dict[str, Any] = {"instrument": instrument, "intervalle": intervalle, "bougies": len(rows)}
        for k, val in s.items():
            out[k.replace("_uusd", "_usd")] = usd(val) if k.endswith("_uusd") else val
        return out

    def t_simuler_ordre(
        self,
        instrument: str,
        action: str,
        size_pct: Any = None,
        stop_pct: Any = None,
        take_profit_pct: Any = None,
        horizon_h: Any = None,
        expected_move_pct: Any = None,
    ) -> dict[str, Any]:
        d = self.data
        now = d["meta"]["now_ts"]
        intent = PerpIntent(
            intent_id="simulation",
            portfolio=self.portfolio,
            ts=now,
            instrument=instrument,
            action=action,
            size_bp=pct_to_bp(size_pct, ROUND_DOWN),
            stop_bp=pct_to_bp(stop_pct),
            take_profit_bp=pct_to_bp(take_profit_pct),
            horizon_h=None if horizon_h is None else int(horizon_h),
            expected_move_bp=pct_to_bp(expected_move_pct),
        )
        v = evaluate_perp(
            intent, self._account(), self._view(), self._specs(), self._counters(), self._policy(),
            SimParams(**d["params"]), now, bool(d["meta"].get("entries_blocked", False)),
        )  # fmt: skip
        m = dict(v.metrics)
        return {
            "approuve": v.approved,
            "codes_de_refus": list(v.reasons),
            "quantite": qty(v.qty),
            "prix_attendu_usd": usd(v.est_price_uusd),
            "stop_usd": usd(v.stop_uusd),
            "objectif_usd": usd(v.take_profit_uusd),
            "equity_eur": eur(m.get("equity_ueur")),
            "exposition_apres_eur": eur(m.get("gross_after_ueur")),
            "perte_si_stop_eur": eur(m.get("trade_loss_ueur")),
            "perte_si_tous_les_stops_eur": eur(m.get("open_risk_ueur")),
            "cout_aller_retour_bp": m.get("cost_rt_bp"),
            "cout_funding_bp": m.get("funding_cost_bp"),
            "note": (
                "état du compte au début de la ronde ; la décision finale est réévaluée action par action "
                "(la 2e après l'exécution de la 1re), avec le coupe-circuit et ORDER_RATE à ce moment"
            ),
        }

    def t_historique(self, n: int = 5) -> dict[str, Any]:
        n = max(1, min(int(n), 10))
        rows = []
        for h in self.data["history"][-n:]:
            h = dict(h)
            if "justification" in h:
                h["justification"] = str(h["justification"])[:HISTORY_JUSTIFICATION]
            rows.append(h)
        while len(rows) > 1 and len(json.dumps(rows, ensure_ascii=False)) > RESPONSE_MAX_CHARS - 200:
            rows.pop(0)  # the oldest first
        return {"historique": rows, "elements": len(rows)}

    # ------------------------------------------------------------------ rebuild riskd inputs

    def _account(self) -> MarginAccount:
        a = self.data["account"]
        acc = MarginAccount(a["portfolio"], a["capital_ueur"], a["collateral_ueur"])
        acc.fees_paid_ueur, acc.funding_paid_ueur = a["fees_paid_ueur"], a["funding_paid_ueur"]
        acc.realized_pnl_ueur, acc.absorbed_deficit_ueur = a["realized_pnl_ueur"], a["absorbed_deficit_ueur"]
        acc.frozen_until_ts, acc.halted, acc.last_fill_ts = (
            a["frozen_until_ts"],
            a["halted"],
            a["last_fill_ts"],
        )
        acc.positions = {i: PerpPosition(**p) for i, p in a["positions"].items()}
        return acc

    def _view(self) -> PerpMarketView:
        v = self.data["view"]
        return PerpMarketView(
            {i: InstrumentMarket(**m) for i, m in v["instruments"].items()},
            v["fx_bid"],
            v["fx_ask"],
            v["fx_ts"],
        )

    def _counters(self) -> PerpCounters:
        return PerpCounters(**self.data["counters"])

    def _specs(self) -> dict[str, InstrumentSpec]:
        return {s: InstrumentSpec.from_dict(d) for s, d in self.data["specs"].items()}

    def _policy(self) -> PerpPolicy:
        p = dict(self.data["policy"])
        p["instruments"] = tuple(p["instruments"])
        return PerpPolicy(**p)


# ---------------------------------------------------------------------- JSON-RPC over stdio


def _send(msg: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def handle(tools: RoundTools, msg: Any) -> dict[str, Any] | None:
    """The reply to one JSON-RPC message (None for a notification)."""
    if not isinstance(msg, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
    if "id" not in msg:  # notification (e.g. notifications/initialized)
        return None
    mid, method = msg.get("id"), msg.get("method")
    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    if method == "initialize":
        asked = params.get("protocolVersion")
        result: dict[str, Any] = {
            "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": "1"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        name = str(params.get("name", ""))
        args = params.get("arguments")
        payload, is_error = tools.call(name, {} if args is None else args)
        text = json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))
        with (tools.dir / "trace.jsonl").open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "n": tools.calls,
                        "tool": name,
                        "arguments": canonical_json(args if args is not None else {}),
                        "response_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "is_error": is_error,
                    }
                )
                + "\n"
            )
        result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(tools: RoundTools) -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line, parse_float=Decimal)
        except (ValueError, ArithmeticError):
            _send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        try:
            reply = handle(tools, msg)
        except Exception as exc:  # noqa: BLE001 (one bad message never ends the server)
            mid = msg.get("id") if isinstance(msg, dict) else None
            reply = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": type(exc).__name__}}
        if reply is not None:
            _send(reply)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m arene.perp.mcp_server")
    ap.add_argument("--round-dir", type=Path, required=True)
    ap.add_argument("--portfolio", required=True)
    ap.add_argument("--max-calls", type=int, default=4)
    args = ap.parse_args(argv)
    serve(RoundTools(args.round_dir, args.portfolio, args.max_calls))
    return 0


if __name__ == "__main__":
    sys.exit(main())
