"""C15 : rejoue une règle spot sur les 6 paires de l'arène à travers le VRAI riskd et le VRAI modèle de fills.

Utilise `arene.risk.riskd.evaluate`, `arene.sim.fills.market_fill` et `arene.risk.policy.load_policy`
(config/policy-strategie.toml). N'écrit rien dans l'arène, n'utilise ni journal ni exécuteur.

Entrées : poids cibles quotidiens (décidés à la clôture de chaque jour, comme le moteur) et clôtures
quotidiennes des 6 paires. À chaque jour : positions valorisées au mid = clôture, ventes d'abord puis achats,
chaque ordre passe par `evaluate`, puis `market_fill`. Un ordre rejeté N'EST PAS exécuté et est compté dans
`rejets` (jamais rogné ni contourné) : il reste dans le Sharpe/drawdown rendus.

Contournements documentés (voir config/policy-strategie.toml) :
 - stop_bp = 2500 et expected_move_bp = 10000 sur chaque achat (riskd les exige) ; le stop n'est pas simulé.
 - USDT converti en EUR à 1:1, quote = clôture +/- demi-spread, instruments sans minimum Kraken.
 - taille d'un achat = floor en bp de l'equity vivante, bornée par le cash ; si riskd rejette pour
   MAX_EXPOSURE / INSUFFICIENT_CASH / MAX_POSITION à cause d'un arrondi, on retente avec 1 bp de moins
   (au plus 3 fois) : c'est de l'arrondi de dimensionnement, pas un contournement d'une règle.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from arene.risk.policy import Policy, load_policy
from arene.risk.riskd import BP, Counters, MarketView, evaluate
from arene.sim.fills import market_fill
from arene.types import (
    MICRO,
    QTY_SCALE,
    Instrument,
    Intent,
    PortfolioState,
    Position,
    Quote,
    Side,
    notional_ueur,
)
from recherche.portes import stats

REPO = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO / "config" / "policy-strategie.toml"
STOP_BP_REPLAY = 2500
EXPECTED_MOVE_BP_REPLAY = 10_000
CAPITAL_EUR = 10_000
PORTFOLIO = "strategie:replay"
_ARRONDI = {"MAX_EXPOSURE", "INSUFFICIENT_CASH", "MAX_POSITION"}


@dataclass(frozen=True)
class ReplayArene:
    rendements: pd.Series  # rendement quotidien net après chaque rééquilibrage (equity post / veille - 1)
    equity_ueur: pd.Series  # equity après rééquilibrage, µEUR
    sharpe: float
    drawdown: float
    n_ordres: int
    n_fills: int
    rejets: dict[str, int] = field(default_factory=dict)  # code riskd -> nombre d'ordres rejetés
    ordres_rejetes: tuple[tuple[str, str, tuple[str, ...]], ...] = ()  # (date, symbole, codes)
    policy_sha256: str = ""


def symbole_arene(binance: str) -> str:
    """BTCUSDT -> BTC/EUR."""
    if not binance.endswith("USDT"):
        raise ValueError(f"symbole sans suffixe USDT : {binance}")
    return binance[: -len("USDT")] + "/EUR"


def _instrument(sym: str) -> Instrument:
    return Instrument(sym, sym.replace("/", ""), sym.split("/")[0] + "USDT", 1, 1, 1)


def _quote(sym: str, ts: int, close_ueur: int, demi_spread_bp: int) -> Quote:
    bid = close_ueur * (BP - demi_spread_bp) // BP
    ask = -((-close_ueur * (BP + demi_spread_bp)) // BP)
    return Quote(sym, ts, bid, ask)


class _Rejeu:
    """État d'un rejeu : un portefeuille, un jour courant."""

    def __init__(self, pol: Policy, insts: dict[str, Instrument], fee_bp: int, slippage_bp: int, capital: int):
        self.pol, self.insts, self.fee_bp, self.slippage_bp = pol, insts, fee_bp, slippage_bp
        self.state = PortfolioState(PORTFOLIO, cash_ueur=capital)
        self.fills_ts: list[int] = []
        self.last_buy: dict[str, int] = {}
        self.rejets: Counter[str] = Counter()
        self.liste_rej: list[tuple[str, str, tuple[str, ...]]] = []
        self.n_ordres = self.n_fills = self.n_cycle = 0
        self.peak = self.prev_post = self.month_start_eq = capital
        self.equity_24h_ago = capital
        self.fees_month = 0
        self.month_key: str | None = None
        # jour courant
        self.ts = 0
        self.jour = ""
        self.closes: dict[str, int] = {}
        self.quotes: dict[str, Quote] = {}

    def equity(self) -> int:
        return self.state.cash_ueur + sum(
            notional_ueur(p.qty, self.closes[s], round_up=False) for s, p in self.state.positions.items() if p.qty > 0
        )

    def valeur(self, sym: str) -> int:
        p = self.state.positions.get(sym)
        return notional_ueur(p.qty, self.closes[sym], round_up=False) if p and p.qty > 0 else 0

    def debut_jour(self, dt, closes: dict[str, int], demi_spread_bp: int) -> int:
        t = pd.Timestamp(dt)
        t = t.tz_localize("UTC") if t.tzinfo is None else t
        self.ts, self.jour = int(t.timestamp()), str(t.date())
        self.closes = closes
        self.quotes = {s: _quote(s, self.ts, p, demi_spread_bp) for s, p in closes.items()}
        self.n_cycle = 0
        pre = self.equity()
        mk = t.strftime("%Y-%m")
        if mk != self.month_key:
            self.month_key, self.month_start_eq, self.fees_month = mk, pre, 0
        return pre

    def _marche(self) -> MarketView:
        return MarketView(
            quotes=self.quotes,
            last_closes=self.closes,
            median_spreads_ueur={s: q.ask - q.bid for s, q in self.quotes.items()},
            marks={s: self.closes[s] for s, p in self.state.positions.items() if p.qty > 0},
        )

    def _compteurs(self, sym: str) -> Counters:
        eq = self.equity()
        return Counters(
            trades_24h=sum(1 for t in self.fills_ts if t > self.ts - 86400),
            orders_last_minute=self.n_cycle,
            last_symbol_intent_ts=self.last_buy.get(sym),
            fees_month_ueur=self.fees_month,
            equity_month_start_ueur=self.month_start_eq,
            equity_24h_ago_ueur=self.equity_24h_ago,
            equity_peak_ueur=max(self.peak, eq),
            equity_now_ueur=eq,
        )

    def passer(self, sym: str, side: Side, size_bp: int) -> bool:
        """Un ordre à travers evaluate puis market_fill. Rejet = non exécuté, compté."""
        self.n_ordres += 1
        v = None
        for essai in range(4):
            s = size_bp - essai
            if s <= 0:
                return False
            intent = Intent(
                intent_id=f"{self.ts}:{sym}:{side.value}:{s}", portfolio=PORTFOLIO, cycle=self.ts, symbol=sym,
                side=side, size_bp=s,
                stop_bp=STOP_BP_REPLAY if side == Side.BUY else None,
                expected_move_bp=EXPECTED_MOVE_BP_REPLAY if side == Side.BUY else None,
            )
            v = evaluate(intent, self.state, self._marche(), self.pol, self._compteurs(sym), self.ts,
                         self.insts, self.fee_bp, self.slippage_bp, False)
            if v.approved:
                self._executer(sym, side, v.qty, v.reserved_ueur)
                return True
            if not set(v.reasons) <= _ARRONDI:
                break
        assert v is not None
        for code in v.reasons:
            self.rejets[code] += 1
        self.liste_rej.append((self.jour, sym, v.reasons))
        return False

    def _executer(self, sym: str, side: Side, qty: int, reserve: int) -> None:
        price, fee = market_fill(side, qty, self.quotes[sym], self.insts[sym], self.fee_bp, self.slippage_bp)
        if side == Side.BUY:
            total = notional_ueur(qty, price, round_up=True) + fee
            if total > reserve:  # même garde que SimExecutor
                raise AssertionError("prix d'exécution au-delà de la réservation de riskd")
            self.state.cash_ueur -= total
            pos = self.state.positions.get(sym)
            if pos is None:
                self.state.positions[sym] = Position(sym, qty, total, self.ts)
            else:
                pos.qty += qty
                pos.cost_ueur += total
            self.last_buy[sym] = self.ts
        else:
            self.state.cash_ueur += notional_ueur(qty, price, round_up=False) - fee
            self.state.positions[sym].qty -= qty
        self.state.fees_paid_ueur += fee
        self.fees_month += fee
        self.fills_ts.append(self.ts)
        self.n_fills += 1
        self.n_cycle += 1

    def fin_jour(self) -> int:
        post = self.equity()
        self.equity_24h_ago = self.prev_post
        self.peak = max(self.peak, post)
        return post


def rejouer(
    poids: pd.DataFrame,
    closes: pd.DataFrame,
    policy_path: str | Path = POLICY_PATH,
    fee_bp: int = 50,
    slippage_bp: int = 5,
    demi_spread_bp: int = 5,
    capital_eur: int = CAPITAL_EUR,
) -> ReplayArene:
    """Rejoue `poids` (index = jours UTC, colonnes = symboles Binance, somme <= 1, >= 0).

    fee_bp / slippage_bp = config/arene.toml (50 / 5) ; demi_spread_bp = 5 ; total 60 pb par rotation.
    Les poids d'un jour sont ceux décidés à la clôture de ce jour. Lève ValueError sur poids invalides.
    """
    pol = load_policy(policy_path)
    if not poids.index.equals(closes.index):
        raise ValueError("poids et closes doivent avoir le même index")
    cols = list(poids.columns)
    if set(cols) - set(closes.columns):
        raise ValueError("clôtures manquantes pour certaines colonnes de poids")
    w_all = poids.fillna(0.0).to_numpy(dtype=float)
    if (w_all < -1e-12).any() or (w_all.sum(axis=1) > 1 + 1e-9).any():
        raise ValueError("poids hors bornes : replay spot long seul, somme <= 1")
    syms = {c: symbole_arene(c) for c in cols}
    if not set(syms.values()) <= set(pol.symbols):
        raise ValueError("symboles hors liste blanche de la politique")
    insts = {s: _instrument(s) for s in syms.values()}
    px = closes[cols].astype(float).ffill()

    rj = _Rejeu(pol, insts, fee_bp, slippage_bp, capital_eur * MICRO)
    rets: list[float] = []
    eq_post: list[int] = []
    for i, dt in enumerate(poids.index):
        cl = {syms[c]: round(float(px[c].iloc[i]) * MICRO) for c in cols
              if np.isfinite(px[c].iloc[i]) and px[c].iloc[i] > 0}
        e0 = rj.debut_jour(dt, cl, demi_spread_bp)
        targets = {syms[c]: float(w_all[i, j]) for j, c in enumerate(cols)}
        # Ventes d'abord (libèrent le cash), puis achats.
        for sym, tw in targets.items():
            held = rj.valeur(sym)
            if held <= 0 or sym not in cl:
                continue
            if tw <= 0:
                rj.passer(sym, Side.SELL, BP)
            elif held > tw * e0:
                frac = int((held - tw * e0) / held * BP)
                if frac > 0:
                    rj.passer(sym, Side.SELL, min(frac, BP))
        for sym, tw in targets.items():
            if tw <= 0 or sym not in cl:
                continue
            held, eq = rj.valeur(sym), rj.equity()
            if tw * e0 <= held or eq <= 0:
                continue
            libre = rj.state.cash_ueur  # jamais plus que le cash
            size = min(int((tw * e0 - held) / eq * BP), int(max(libre, 0) * BP // eq))
            if size > 0:
                rj.passer(sym, Side.BUY, size)
        post = rj.fin_jour()
        rets.append(post / rj.prev_post - 1.0)
        eq_post.append(post)
        rj.prev_post = post

    idx = poids.index
    serie = pd.Series(rets, index=idx, name="replay_arene")
    return ReplayArene(
        rendements=serie,
        equity_ueur=pd.Series(eq_post, index=idx, name="equity_ueur"),
        sharpe=stats.sharpe(serie),
        drawdown=stats.drawdown(serie),
        n_ordres=rj.n_ordres,
        n_fills=rj.n_fills,
        rejets=dict(rj.rejets),
        ordres_rejetes=tuple(rj.liste_rej),
        policy_sha256=pol.sha256,
    )


__all__ = ["POLICY_PATH", "QTY_SCALE", "ReplayArene", "rejouer", "symbole_arene"]
