# Specification of the perp ledger and simulator (step 2)

This document is the contract of `arena/perp/ledger.py` and `arena/perp/sim.py`. The golden scenarios are computed by hand **from this text**, independently of the code.

References:
- the French retail CFD rule (AMF 2019), annex I.

## 1. Units and rounding

Everything is in **integers**, never floats.

| Quantity | Unit |
|---|---|
| collateral, fees, P&L and funding in euros | µEUR (1 EUR = 10^6) |
| contract prices | µUSD (1 USD = 10^6) |
| quantity | 1e-8 of a unit of the base asset; **signed**: > 0 long, < 0 short |
| absolute funding rate | nano-USD per unit of asset per hour (1 USD = 10^9) |
| EUR/USD rate | µUSD per EUR (`fx_bid` <= `fx_ask`) |
| rates | basis points (bp, 1/10,000) |

Notation: `ceil(a/b)` and `floor(a/b)` are integer divisions rounded up and down (b > 0). `|x|` is the absolute value, and `sgn(q)` is +1 for a long, -1 for a short.

**R1, notional.**
- `notional_up(q, p) = ceil(|q| × p / 10^8)` (in µUSD);
- `notional_down(q, p) = floor(|q| × p / 10^8)`.

**R2, USD -> EUR conversion, always unfavorable to the portfolio:**
- an amount **to pay** (loss, fees, funding paid, exposure): `cost_eur(u) = ceil(u × 10^6 / fx_bid)`;
- an amount **received** (gain, funding received): `gain_eur(u) = floor(u × 10^6 / fx_ask)`.

Dividing by the smaller rate (`fx_bid`) gives more euros, which penalizes a cost. Dividing by the larger (`fx_ask`) gives fewer, which penalizes a gain.

**R3, conversion of a signed amount** (unrealized or realized P&L): `to_eur(u) = gain_eur(u)` if u >= 0, otherwise `-cost_eur(-u)`.

**R4, tick.**
- `tick_up(p) = ceil(p / tick) × tick`;
- `tick_down(p) = floor(p / tick) × tick`.

## 2. Parameters (`config/perp.toml`, section `[simulation]`)

| key | value | meaning |
|---|---|---|
| `fill_model_version` | `"pessimiste-perp-v1"` | |
| `capital_eur` | 1000 | initial collateral of each portfolio |
| `taker_fee_bp` | 7 | Kraken's 0.05% increased by 25%, rounded up |
| `slippage_bp` | 5 | |
| `liquidation_fee_bp` | 500 | fee added on a margin closeout (prudence: Kraken would take 2.5%) |
| `closeout_margin_bp` | 2500 | closeout if equity falls below 25% of gross exposure (half of the 50% margin of the AMF rule) |
| `initial_margin_bp` | 5000 | an entry must leave an equity >= 50% of gross exposure (AMF rule: 2:1 on crypto) |
| `max_holding_s` | 604800 | 7 days |

## 3. State of a portfolio (`MarginAccount`)

- **`collateral_ueur`**. At the start, it equals the capital. It is never negative after an event.
- **`positions`**, with at most one position per instrument. A position carries:
  - `qty` (signed) and `entry_uusd` (average entry price);
  - `opened_ts`;
  - `open_seq`, the seq of the opening fill, which identifies it among reopenings;
  - `stop_uusd` and `take_profit_uusd`, possibly null, each with the ts of the order that set it (`stop_armed_ts`, `take_profit_armed_ts`).
- **Quantity history** of each instrument: the list of pairs (ts of the fill, quantity after the fill), used for funding.
- **Cumulative totals**:
  - `fees_paid_ueur`;
  - `funding_paid_ueur` (signed, > 0 = paid);
  - `realized_pnl_ueur` (price P&L only);
  - `absorbed_deficit_ueur`;
  - the number of hours with no published rate (`missing_funding`).
- **Flags**: `frozen_until_ts`, `halted`.

**Invariant:**

    collateral = capital + realized_pnl − fees_paid − funding_paid + absorbed_deficit

**Negative balance.** If an event leaves `collateral < 0`, then `absorbed_deficit += −collateral` and `collateral = 0`. This is the negative balance protection.

## 4. Events of the league journal (`var-perp/journal/events.jsonl`)

The journal is the same code as the spot journal, `arena.journal.Journal`: chained, with no floats. The ledger is rebuilt solely from these events, in `seq` order.

**It refuses:**
- an `order_id` already seen;
- a funding already settled for (portfolio, instrument, stamp);
- a duplicate closeout summary or equity measurement;
- a fill whose ts is **earlier** than the portfolio's previous fill, or than a funding stamp already settled on that instrument.

The simulator validates each event with the ledger **before** writing it: a refused event never reaches the journal.

### `portfolio_opened`

`{portfolio, kind, league: "perp", capital_ueur, venue_mode: "paper"}`

### `perp_fill`

`{order_id, portfolio, instrument, qty, price_uusd, fee_ueur, fx_bid, fx_ask, reason, fill_model_version, ts}`

- **`qty` is the signed change**: > 0 buys, < 0 sells.
- **`reason`** is `intent`, `stop`, `take_profit`, `margin_closeout`, `max_holding`, `halt` or `kill_switch`.

Application by the ledger (position before the fill: `q`, `e`; change `d` at price `p`):

1. **Opening or increase**: no position, or `sgn(d) = sgn(q)`.
   - New quantity: `q + d`.
   - Average price:
     - long: `ceil((|q|×e + |d|×p) / (|q|+|d|))`;
     - short: `floor(...)` of the same expression.
   - Unfavorable in both cases.
   - `opened_ts` and `open_seq` are those of the opening fill, and do not change on an increase.
2. **Reduction or close**: `sgn(d) ≠ sgn(q)` and `|d| <= |q|`.
   - Realized P&L: `r = floor(sgn(q) × (p − e) × |d| / 10^8)` in µUSD, i.e. an integer division toward −∞.
   - Converted by R3, it is added to `realized_pnl` and to the collateral.
   - If `|d| = |q|`, the position and its conditional orders disappear.
3. **Flip** (`|d| > |q|` in the opposite direction): **refused**. A close, then an opening, are required.
4. **Fees**: `fee_ueur` is deducted from the collateral and added to `fees_paid`. The ledger refuses a negative fee.
5. **History**: the pair (ts, quantity after the fill) is appended to the instrument's history.
6. **Negative balance**: rule of §3.

### `conditional_order`

`{portfolio, instrument, kind: "stop" | "take_profit", price_uusd | null, ts}`

- Sets, modifies or cancels (`null`) the stop or target of an **existing** position.
- The price must be an integer > 0.
- The event's `ts` becomes the moment when the order is armed.

### `funding`

`{portfolio, instrument, stamp, qty_seconds, rate_nusd, fx_bid, fx_ask, amount_ueur}`

- **`stamp`** = H, a round hour. The rate timestamped H by Kraken pays the hour [H − 1 h, H).
- **`qty_seconds`** is the integral of the signed quantity over [H − 1 h, H), computed on the history of §3:
  - for each interval between two fills, the quantity held × the duration in seconds;
  - a position opened or closed during the hour therefore pays only for the time it was held.
  - The ledger recomputes it and refuses a mismatch, or an hour in which no position was held.
- **Amount paid**, in µUSD: `m = qty_seconds × rate_nusd / (10^8 × 10^3 × 3600)`. If it is positive, it is paid: a long pays when the rate is positive, a short pays when it is negative. Rounding:
  - paid: `ceil(m)` µUSD, then `cost_eur`;
  - received: `floor(−m)` µUSD, then `gain_eur`, counted negative.
- **`amount_ueur`** (> 0 = paid) is recomputed by the ledger, which refuses a mismatch.
- Effect: `collateral −= amount_ueur` and `funding_paid += amount_ueur`, then the negative balance rule.
- **Only once** per (portfolio, instrument, stamp), and always in increasing stamp order.
- A later fill can no longer fall within an already settled hour.
- Settlement may be late: `qty_seconds` comes from the history, not from the position at the time of settlement.

### `funding_missing`

`{portfolio, instrument, stamp, qty_seconds}`

An hour held for which Kraken published no rate.
- Nothing is charged, but the hour is counted.
- It also counts as settled: it can no longer be paid afterwards.

### `margin_closeout`

`{portfolio, minute, equity_ueur, threshold_ueur, gross_ueur, order_ids, resumed_after_crash}`

Summary written **after** the `perp_fill` events with reason `margin_closeout`, only once per (portfolio, minute).

### `minute_incomplete`

`{portfolio, minute, instruments}`

A minute processed without the candle of one or more held instruments (see §5).

### `perp_equity`

`{portfolio, ts, collateral_ueur, unrealized_ueur, equity_ueur, gross_ueur, marks, fx_bid, fx_ask}`

Measurement written by the simulator, only once per (portfolio, ts). It is used for the equity peak and for statistics.

## 5. Simulator (`pessimiste-perp-v1`)

### Market order on a quote (bid, ask)

- **Price:**
  - buy (`d > 0`): `tick_up(ceil(ask × (10000 + slippage_bp) / 10000))`;
  - sell (`d < 0`): `tick_down(floor(bid × (10000 − slippage_bp) / 10000))`.
- **Fees:** `fee_uusd = ceil(notional_up(d, price) × taker_fee_bp / 10000)`, then `fee_ueur = cost_eur(fee_uusd)`.
  - For every fill, stops, targets and closeouts included, the fee notional is taken **at the execution price**.
- **Entry** (reason `intent`, which opens or increases a position): it is **refused** in four cases.
  - the portfolio is halted;
  - it is frozen (`ts < frozen_until_ts`);
  - it has no collateral left;
  - **the initial margin is not covered after the order**, that is `equity × 10000 < initial_margin_bp × gross exposure`.
    - This calculation is done on the state after the fill, fees included.
    - The traded instrument is valued at the quote midpoint, and the others at the mark supplied by the caller.
    - Without a mark for a held instrument, the order is refused.
- **Reductions and closes**: they always go through.
- **Identifier already used:**
  - same portfolio, instrument and quantity: nothing is done;
  - any other request: error.

### Valuation

- **Unrealized P&L** of a position at mark `m`: `u = floor(sgn(q) × (m − e) × |q| / 10^8)` µUSD, converted by R3 **position by position**.
- **Equity** = collateral + Σ of the converted unrealized amounts.
- **Gross exposure** (EUR) = Σ `cost_eur(notional_up(q, m))`.

### Processing a minute M (from M to M + 59 s)

Minutes are processed in chronological order, with the **mark** candle (and the **trade** candle if it exists) of each held instrument.

**Timestamping.** The fills of a minute are timestamped **at its end**, `M + 59`, or at the portfolio's last fill if that is later. A minute therefore cannot be processed after a more recent fill: the minutes must be processed before placing new orders.

Three steps are applied **in this order**.

1. **Margin closeout, on the whole account**, all positions included, even those opened during the minute (pessimistic).
   - Worst mark of the minute: `mark.low` for a long, `mark.high` for a short. The worst cases of all instruments are assumed simultaneous.
   - Equity and gross exposure are computed at these worst marks.
   - If `equity × 10000 < closeout_margin_bp × exposure`, **all** positions are closed:
     - price, on the mark candle: sell at `tick_down(floor(mark.low × (10000 − slippage_bp)/10000))`, buy back at `tick_up(ceil(mark.high × (10000 + slippage_bp)/10000))`;
     - at least one tick;
     - fees: `ceil(notional_up(q, price) × (taker_fee_bp + liquidation_fee_bp) / 10000)`, converted by `cost_eur`.
   - Then the `margin_closeout` event. The rest of the minute is ignored for that portfolio.
   - **Resume after a crash:** if a closeout of this minute has been started (a `margin_closeout` fill exists without its summary), it is **completed** without re-testing the margin. The decision is durable.
2. **Stops**, armed **before the end** of the minute (`stop_armed_ts < M + 60`). A stop placed during the minute therefore applies to the whole minute (pessimistic).
   - **Long with stop `s`**: triggered if `mark.low <= s`.
     - Base: `min(s, trade.open)`, or `mark.open` without a trade candle.
     - Price: `tick_down(floor(base × (10000 − slippage_bp)/10000))`.
   - **Short with stop `s`**: triggered if `mark.high >= s`.
     - Base: `max(s, trade.open)`, or `mark.open` without a trade candle.
     - Price: `tick_up(ceil(base × (10000 + slippage_bp)/10000))`.
   - A zero price becomes one tick, and this is flagged.
   - Full close, at the taker rate. Reason `stop`.
3. **Targets** of the positions still open, armed **and** opened at the latest at the start of the minute (`max(take_profit_armed_ts, opened_ts) <= M`). A limit order cannot benefit from a price prior to its existence.
   - **Long with target `t`**: executed if `trade.high >= t + tick`, at price `t`, without slippage.
   - **Short with target `t`**: executed if `trade.low <= t − tick`, at price `t`.
   - Without a trade candle, no target. Full close, at the taker rate. Reason `take_profit`.

**Exit slippage.** The caller may add, per instrument, an extra slippage to stops and closeouts: the worst half-spread of the last 7 days, measured by the watcher. This accounts for the residual optimism of the model.

**Missing candle** for a held instrument:
- the `minute_incomplete` event is written;
- its stop and its target are not evaluated;
- the margin closeout values it at its last known mark, supplied by the caller. Without that mark, it is not tested, and this is flagged.

**Isolation.** The error of one portfolio does not prevent the processing of the others.

### Exchange rate, maximum holding, identifiers

- **EUR/USD.** The rate used is that of the last reading at the minute or before. It is written in each event.
- **Maximum holding.** When `ts − opened_ts >= max_holding_s`, the position is closed at the current quote, like a market order. Reason `max_holding`.
- **Flattening** (`halt`, `kill_switch`): all positions at market. Without a quote for a held instrument, it is an error, never a silent omission.
- **Identifiers**, which carry the identity of the position (`open_seq`):
  - stop: `stop:<portfolio>:<instrument>:<open_seq>:<minute>`;
  - target: `take_profit:<portfolio>:<instrument>:<open_seq>:<minute>`;
  - closeout: `margin_closeout:<portfolio>:<instrument>:<open_seq>:<minute>`;
  - holding: `max_holding:<portfolio>:<instrument>:<open_seq>`;
  - flattening: `<reason>:<portfolio>:<instrument>:<open_seq>`.
- **Writes.** They are done under an exclusive lock (`<journal>.sim.lock`): the idempotence check and the write are atomic.
