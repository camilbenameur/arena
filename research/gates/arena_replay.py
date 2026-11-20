"""C15: replay a spot rule on the arena's 6 pairs through the REAL riskd and the REAL fill model.

Uses `arena.risk.riskd.evaluate`, `arena.sim.fills.market_fill` and `arena.risk.policy.load_policy`
(config/policy-strategy.toml). Writes nothing to the arena, uses neither journal nor executor.

Inputs: daily target weights (decided at each day's close, like the engine) and daily closes of the 6
pairs. Each day: positions valued at mid = close, sells first then buys, every order goes through
`evaluate`, then `market_fill`. A rejected order is NOT executed and is counted in `rejected` (never
trimmed or worked around): it stays in the returned Sharpe/drawdown.

Documented workarounds (see config/policy-strategy.toml):
 - stop_bp = 2500 and expected_move_bp = 10000 on every buy (riskd requires them); the stop is not simulated.
 - USDT converted to EUR at 1:1, quote = close +/- half-spread, instruments without a Kraken minimum.
 - buy size = floor in bp of the live equity, capped by cash; if riskd rejects with
   MAX_EXPOSURE / INSUFFICIENT_CASH / MAX_POSITION because of rounding, retry with 1 bp less
   (at most 3 times): this is sizing rounding, not a workaround of a rule.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from arena.risk.policy import Policy, load_policy
from arena.risk.riskd import BP, Counters, MarketView, evaluate
from arena.sim.fills import market_fill
from arena.types import (
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
from research.gates import stats

REPO = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO / "config" / "policy-strategy.toml"
STOP_BP_REPLAY = 2500
EXPECTED_MOVE_BP_REPLAY = 10_000
CAPITAL_EUR = 10_000
PORTFOLIO = "strategy:replay"
_ROUNDING = {"MAX_EXPOSURE", "INSUFFICIENT_CASH", "MAX_POSITION"}


@dataclass(frozen=True)
class ReplayArena:
    returns: pd.Series  # net daily return after each rebalance (post equity / previous day - 1)
    equity_ueur: pd.Series  # equity after rebalance, µEUR
    sharpe: float
    drawdown: float
    n_orders: int
    n_fills: int
    rejected: dict[str, int] = field(default_factory=dict)  # riskd code -> number of rejected orders
    orders_rejected: tuple[tuple[str, str, tuple[str, ...]], ...] = ()  # (date, symbol, codes)
    policy_sha256: str = ""


def symbol_arena(binance: str) -> str:
    """BTCUSDT -> BTC/EUR."""
    if not binance.endswith("USDT"):
        raise ValueError(f"symbol without USDT suffix : {binance}")
    return binance[: -len("USDT")] + "/EUR"


def _instrument(sym: str) -> Instrument:
    return Instrument(sym, sym.replace("/", ""), sym.split("/")[0] + "USDT", 1, 1, 1)


def _quote(sym: str, ts: int, close_ueur: int, half_spread_bp: int) -> Quote:
    bid = close_ueur * (BP - half_spread_bp) // BP
    ask = -((-close_ueur * (BP + half_spread_bp)) // BP)
    return Quote(sym, ts, bid, ask)


class _Replay:
    """State of a replay: one portfolio, one current day."""

    def __init__(self, pol: Policy, insts: dict[str, Instrument], fee_bp: int, slippage_bp: int, capital: int):
        self.pol, self.insts, self.fee_bp, self.slippage_bp = pol, insts, fee_bp, slippage_bp
        self.state = PortfolioState(PORTFOLIO, cash_ueur=capital)
        self.fills_ts: list[int] = []
        self.last_buy: dict[str, int] = {}
        self.rejected: Counter[str] = Counter()
        self.rejected_list: list[tuple[str, str, tuple[str, ...]]] = []
        self.n_orders = self.n_fills = self.n_cycle = 0
        self.peak = self.prev_post = self.month_start_eq = capital
        self.equity_24h_ago = capital
        self.fees_month = 0
        self.month_key: str | None = None
        # current day
        self.ts = 0
        self.day = ""
        self.closes: dict[str, int] = {}
        self.quotes: dict[str, Quote] = {}

    def equity(self) -> int:
        return self.state.cash_ueur + sum(
            notional_ueur(p.qty, self.closes[s], round_up=False) for s, p in self.state.positions.items() if p.qty > 0
        )

    def value(self, sym: str) -> int:
        p = self.state.positions.get(sym)
        return notional_ueur(p.qty, self.closes[sym], round_up=False) if p and p.qty > 0 else 0

    def day_start(self, dt, closes: dict[str, int], half_spread_bp: int) -> int:
        t = pd.Timestamp(dt)
        t = t.tz_localize("UTC") if t.tzinfo is None else t
        self.ts, self.day = int(t.timestamp()), str(t.date())
        self.closes = closes
        self.quotes = {s: _quote(s, self.ts, p, half_spread_bp) for s, p in closes.items()}
        self.n_cycle = 0
        pre = self.equity()
        mk = t.strftime("%Y-%m")
        if mk != self.month_key:
            self.month_key, self.month_start_eq, self.fees_month = mk, pre, 0
        return pre

    def _market(self) -> MarketView:
        return MarketView(
            quotes=self.quotes,
            last_closes=self.closes,
            median_spreads_ueur={s: q.ask - q.bid for s, q in self.quotes.items()},
            marks={s: self.closes[s] for s, p in self.state.positions.items() if p.qty > 0},
        )

    def _counters(self, sym: str) -> Counters:
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

    def try_order(self, sym: str, side: Side, size_bp: int) -> bool:
        """One order through evaluate then market_fill. Rejection = not executed, counted."""
        self.n_orders += 1
        v = None
        for attempt in range(4):
            s = size_bp - attempt
            if s <= 0:
                return False
            intent = Intent(
                intent_id=f"{self.ts}:{sym}:{side.value}:{s}", portfolio=PORTFOLIO, cycle=self.ts, symbol=sym,
                side=side, size_bp=s,
                stop_bp=STOP_BP_REPLAY if side == Side.BUY else None,
                expected_move_bp=EXPECTED_MOVE_BP_REPLAY if side == Side.BUY else None,
            )
            v = evaluate(intent, self.state, self._market(), self.pol, self._counters(sym), self.ts,
                         self.insts, self.fee_bp, self.slippage_bp, False)
            if v.approved:
                self._execute(sym, side, v.qty, v.reserved_ueur)
                return True
            if not set(v.reasons) <= _ROUNDING:
                break
        assert v is not None
        for code in v.reasons:
            self.rejected[code] += 1
        self.rejected_list.append((self.day, sym, v.reasons))
        return False

    def _execute(self, sym: str, side: Side, qty: int, reserve: int) -> None:
        price, fee = market_fill(side, qty, self.quotes[sym], self.insts[sym], self.fee_bp, self.slippage_bp)
        if side == Side.BUY:
            total = notional_ueur(qty, price, round_up=True) + fee
            if total > reserve:  # same guard as SimExecutor
                raise AssertionError("execution price above the riskd reservation")
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

    def end_day(self) -> int:
        post = self.equity()
        self.equity_24h_ago = self.prev_post
        self.peak = max(self.peak, post)
        return post


def replay(
    weight: pd.DataFrame,
    closes: pd.DataFrame,
    policy_path: str | Path = POLICY_PATH,
    fee_bp: int = 50,
    slippage_bp: int = 5,
    half_spread_bp: int = 5,
    capital_eur: int = CAPITAL_EUR,
) -> ReplayArena:
    """Replay `weight` (index = UTC days, columns = Binance symbols, sum <= 1, >= 0).

    fee_bp / slippage_bp = config/arena.toml (50 / 5); half_spread_bp = 5; 60 bp in total per rotation.
    The weights of a day are those decided at that day's close. Raises ValueError on invalid weights.
    """
    pol = load_policy(policy_path)
    if not weight.index.equals(closes.index):
        raise ValueError("weight and closes must have the same index")
    cols = list(weight.columns)
    if set(cols) - set(closes.columns):
        raise ValueError("closes missing for some weight columns")
    w_all = weight.fillna(0.0).to_numpy(dtype=float)
    if (w_all < -1e-12).any() or (w_all.sum(axis=1) > 1 + 1e-9).any():
        raise ValueError("weights out of bounds: long-only spot replay, sum <= 1")
    syms = {c: symbol_arena(c) for c in cols}
    if not set(syms.values()) <= set(pol.symbols):
        raise ValueError("symbols outside the policy whitelist")
    insts = {s: _instrument(s) for s in syms.values()}
    px = closes[cols].astype(float).ffill()

    rj = _Replay(pol, insts, fee_bp, slippage_bp, capital_eur * MICRO)
    rets: list[float] = []
    eq_post: list[int] = []
    for i, dt in enumerate(weight.index):
        cl = {syms[c]: round(float(px[c].iloc[i]) * MICRO) for c in cols
              if np.isfinite(px[c].iloc[i]) and px[c].iloc[i] > 0}
        e0 = rj.day_start(dt, cl, half_spread_bp)
        targets = {syms[c]: float(w_all[i, j]) for j, c in enumerate(cols)}
        # Sells first (they free the cash), then buys.
        for sym, tw in targets.items():
            held = rj.value(sym)
            if held <= 0 or sym not in cl:
                continue
            if tw <= 0:
                rj.try_order(sym, Side.SELL, BP)
            elif held > tw * e0:
                frac = int((held - tw * e0) / held * BP)
                if frac > 0:
                    rj.try_order(sym, Side.SELL, min(frac, BP))
        for sym, tw in targets.items():
            if tw <= 0 or sym not in cl:
                continue
            held, eq = rj.value(sym), rj.equity()
            if tw * e0 <= held or eq <= 0:
                continue
            cash_free = rj.state.cash_ueur  # never more than the cash
            size = min(int((tw * e0 - held) / eq * BP), int(max(cash_free, 0) * BP // eq))
            if size > 0:
                rj.try_order(sym, Side.BUY, size)
        post = rj.end_day()
        rets.append(post / rj.prev_post - 1.0)
        eq_post.append(post)
        rj.prev_post = post

    idx = weight.index
    daily_returns = pd.Series(rets, index=idx, name="arena_replay")
    return ReplayArena(
        returns=daily_returns,
        equity_ueur=pd.Series(eq_post, index=idx, name="equity_ueur"),
        sharpe=stats.sharpe(daily_returns),
        drawdown=stats.drawdown(daily_returns),
        n_orders=rj.n_orders,
        n_fills=rj.n_fills,
        rejected=dict(rj.rejected),
        orders_rejected=tuple(rj.rejected_list),
        policy_sha256=pol.sha256,
    )


__all__ = ["POLICY_PATH", "QTY_SCALE", "ReplayArena", "replay", "symbol_arena"]
