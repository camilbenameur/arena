# Axis 03: market-neutral funding carry

Question: can EUR 1,000 earn a steady, positive, low-drawdown return by harvesting perpetual
funding market-neutrally (long spot + short perp), net of Kraken-realistic costs, out of sample?

**Verdict: yes, but it is small.** Always-on BTC+ETH cash-and-carry earned about +8%/yr in design
(2020-04 to 2024-06, driven by the 2021 bull) and only **+2.1%/yr in the sealed control**
(2024-07 to 2026-11), **+1.3%/yr over the last 12 months on Kraken's own funding**. Volatility is
0.2-0.9%, max drawdown under 1%. It is a cash substitute, not a growth engine. Every rule that
tries to time it (thresholds, rotation, cross-venue) was worse than just staying on.

## Data (public endpoints, stored outside git in `~/dev/_arena-data/axis-03/`)
| Source | Coverage | Used for |
|---|---|---|
| Binance USD-M funding (8h) | 2019-09 (BTC) / each coin's listing to 2026-11-27, 25 coins | design + control, main series |
| Bybit linear funding | 2020-03 to 2026-11-27, 25 coins (alts on 4h/1h summed into 8h bins) | cross-venue spread |
| Kraken Futures funding (hourly, `relativeFundingRate`) | **only the last ~365 days** (2025-11-26 to 2026-11-27), 25 PF_ perps | venue check on the control window |
| Binance spot and USD-M perp 8h candles (open) | 2019-01 / listing to 2026-11 | both legs' prices, so basis is real |

No venue blocked this server. Kraken's endpoint returns only one year, so Kraken cannot give a
2024-06-30 design/control split: the main study runs on Binance/Bybit, and Kraken is replayed on
its one year (which lies inside the control window). Kraken prices were not downloaded: the
Kraken replay uses Binance spot/perp prices with Kraken's funding (omission: Kraken perp-vs-spot
gap, USD vs USDT/EUR quote).

## Protocol
- Design: 2020-04-01 to 2024-06-30. Sealed control: 2024-07-01 on. `control.py` was written before
  any control number was seen, finalists frozen in `finalists.json`, run once (it refuses a second
  run), all finalists reported below.
- **24 logged trials** (`trials.jsonl`, none failed). 20 planned, then 4 follow-ups after seeing
  that gating lost to always-on (21-24). Cost level, margin sizing and the Kraken replay are
  reported variants of the finalists, not extra trials.
- Finalist selection (stated before the control): ann return >= 5% and Sharpe > 6 in design
  (#1, #2, #3, #21, #24), plus #13 (rotation) and the two cross-venue rules #19/#20 for the
  secondary question.
- Timing (all causal, pessimistic): 8h grid at settlement times; the decision for the interval
  uses funding settled one bar earlier; the trade is at the open of the bar; a pair earns the
  funding of each settlement it holds through.
- Costs per side on leg notional: spot taker 0.40% (0.25% optimistic) + 0.05% slippage; perp
  taker 0.05% + 0.05% slippage; both legs, entry and exit, and on every resize. Idle cash earns 0.
  Pair kept at equity/2 per leg (1x notional per leg, so EUR 500 per leg), resized when a leg
  drifts outside 0.8-1.25x of target (costs charged). Mark-to-market includes the real perp-vs-spot
  gap (basis) at the 8h opens. Round trip on a pair = 1.1% of leg notional = 0.55% of equity.
- Break-even: at 11% funding per year on notional, a position must stay about 37 days to repay costs.

## Design results (base costs, whole EUR 1,000)
| # | Rule | Ann. | Vol | Max DD | Trades/yr | 2020 | 2021 | 2022 | 2023 | 2024H1 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | always-on BTC | 7.4% | 0.9% | -0.8% | 0.2 | 5.5 | 16.6 | 1.7 | 3.9 | 4.3 |
| 2 | always-on ETH | 8.7% | 1.0% | -1.3% | 0.2 | 9.3 | 20.7 | -0.4 | 4.0 | 4.4 |
| 3 | always-on BTC+ETH | 8.1% | 0.9% | -0.6% | 0.5 | 7.4 | 18.7 | 0.6 | 4.0 | 4.3 |
| 21 | BTC+ETH, on unless 21-day (63-settlement) mean funding < 0, re-enter above 3%/yr | 7.5% | 1.0% | -1.7% | 5.2 | 7.5 | 18.5 | -1.3 | 3.6 | 4.3 |
| 24 | rotate top-5 of 25 coins, 42-day trailing funding > 8%/yr | 7.6% | 1.2% | -0.9% | 43.6 | 7.7 | 21.8 | -0.5 | 1.4 | 3.1 |
| 13 | rotate top-3, 21-day trailing > 15% | 6.3% | 1.4% | -1.2% | 37.7 | 7.5 | 19.9 | 0.0 | 0.3 | 0.3 |
| 4-9 | BTC/ETH threshold gates (10-20% enter) | 4.5-6.9% | 1.0-1.2% | -1% to -2.5% | 3-12 | | | | | |
| 10-12,14-16 | fast rotation | -7.8% to +6% | up to 3.4% | down to -32% | 65-196 | | | | | |
| 17-20 | cross-venue Bybit vs Binance perp | -2.0% to +0.3% | <1% | -3% to -9% | 14-120 | | | | | |
Full list with every metric: `trials.jsonl`.

## Sealed control (2024-07-01 to 2026-11-27, 2.4 years)
| # | Rule | Ann. base | Ann. optimistic costs | Ann. with perp at 2x lev. (margin 0.5) | Vol | Max DD | Worst month | % months > 0 | Trades/yr | 2024H2 / 2025 / 2026YTD |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | always-on BTC | 2.28% | 2.38% | 3.04% | 0.25% | -0.42% | -0.17% | 90% | 0.4 | 1.8 / 2.6 / 1.1 |
| 2 | always-on ETH | 1.90% | 2.06% | 2.53% | 0.28% | -0.45% | -0.28% | 86% | 0.4 | 2.0 / 2.0 / 0.6 |
| 3 | always-on BTC+ETH | 2.09% | 2.22% | 2.79% | 0.23% | -0.44% | -0.21% | 90% | 0.8 | 1.9 / 2.3 / 0.9 |
| 21 | BTC+ETH with kill-switch | 1.65% | 1.91% | 2.22% | 0.33% | -0.92% | -0.47% | 79% | 4.2 | 1.5 / 2.3 / 0.2 |
| 24 | rotate top-5 | -0.58% | 0.01% | n/a | 0.56% | -1.8% | -0.49% | 24% | 32 | 0.2 / -1.2 / -0.4 |
| 13 | rotate top-3 | -0.19% | -0.01% | n/a | 0.32% | -0.55% | -0.51% | 3% | 6.6 | mostly flat |
| 19 | cross-venue, 8 coins | -1.7% | | | 0.3% | -4.1% | -0.5% | 7% | 68 | -0.9 / -2.1 / -1.2 |
| 20 | cross-venue BTC | -0.4% | | | 0.2% | -1.0% | -0.2% | 10% | 5.8 | |

Kraken's own funding, last ~12 months (2025-11-27 to 2026-11-27, Binance prices, base costs):
#1 +1.36% (Binance funding same window: 1.30%), #2 +1.16% (0.55%), #3 +1.26% (0.92%),
#21 +0.61% (0.19%). Kraken funding for ETH was higher than Binance's (3.6% vs 2.3% per year on
notional); BTC was 3.7% vs 3.5%. Cross-venue Kraken vs Binance spread: #19 -3.0%, #20 -0.5% (loses).

Funding regime (annual funding on notional, BTC): high in 2020-21 (bull, leveraged longs paying),
about 4-8% in 2023-24H1, about 10% in 2024H2, **about 3.5% over the last year**. A 1x/1x pair
returns half of that on equity, minus costs.

## What failed and why
- Gating and rotation: every entry/exit costs 0.55% of equity; funding is persistent but trailing
  averages flip often, so costs exceed the avoided negative periods. Fast rotation (10,11,12,14,15,16)
  collapsed in the control or churned 65-196 times per year.
- Cross-venue Bybit/Binance: spreads (a few bp per 8h) are below the 0.4% round-trip fee level; both
  venues are also not available to the EU retail user via Kraken. Kraken vs Binance loses as well.

## Practical issues
- Kraken spot is in a separate wallet from Kraken Futures. Shorting the PF_ perp needs margin there;
  the spot leg cannot be used as margin unless the held coin is posted as multi-collateral in the
  futures wallet (then the spot leg is itself the collateral, which is the capital-efficient route).
  Transfers between wallets are quick but not atomic; rebalancing needs both.
- EU retail (MiFID/ESMA) caps leverage on derivatives; Kraken's EU futures access depends on the
  account's classification and country. Check eligibility before any live use.
- PF_ perps are USD-margined; the spot leg is in EUR or USD. The EUR/USD move on the margin is not
  hedged and is not modelled.
- Short perp liquidation: at 1x notional margin the price must roughly double before liquidation; at
  2x leverage (margin 0.5) a +50% spike with a delayed top-up liquidates the short and leaves a naked
  long spot. Spikes in alts are the danger; BTC/ETH only is much safer.
- Kraken funding: quoted per hour as a fraction of price (`relativeFundingRate`), settled hourly;
  I summed it into 8h bins. Funding can turn negative (shorts pay): 5-10% of months were negative.
- Omissions: Kraken perp-vs-spot basis (Binance prices used), exit fees on open positions at the end
  of a window, borrow/withdrawal fees, tax, partial fills. Mark-to-market uses 8h opens, so intra-8h
  basis spikes are not seen.

## Files
`fetch.py` (download), `carry.py` (engine), `strategies.py` (trial specs), `xvenue.py` (cross-venue),
`design.py`, `control.py`, `trials.jsonl`, `finalists.json`, `control_results.json`.
Run: use a venv with pandas, numpy and requests.
