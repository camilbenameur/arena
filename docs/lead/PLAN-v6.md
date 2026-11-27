# Ranked research plan, v6 (Kraken-only, EUR 1,000 per portfolio)

**Ground rules for all axes**
- Freeze the rule, the parameters and the pass criteria in a dated file before the control is opened.
- The sealed control is opened once. Any change after opening counts as a new axis.
- Every trial is counted against the stated budget.
- Costs are modelled at Kraken spot taker 0.40%, perps 0.05% taker per side plus slippage, and funding.
- None of these is a "fast profit" engine. Realistic returns are 0-8% per year, and the first three are mostly cheap falsifications.

---

## 1. Stablecoin discount bids (passive liquidity provision on Kraken spot)

**Payer.** Forced or panicking sellers hit a thin single-venue book and accept 20-400 bp below par. Mint and redeem arbitrage is slow and has size minimums, so the discount can persist for days. We are paid for absorbing the flow, and for the tail risk of a true depeg.

**Rule.**
- Rest limit buys on USDT/EUR, USDC/EUR, RLUSD/EUR, and USDT/USD, USDC/USD, PYUSD/USD, USDG/USD.
- Bid levels are 30 and 50 bp below par. For EUR pairs, par is the FX-implied parity.
- On fill, post a limit sell at par minus 5 bp.
- Time stop after 10 days, then exit at market.
- Hard exit if the coin trades below 0.97 for 1 hour.
- Maximum 25% of the portfolio per fill and 2 coins at once.

**Step 0 (blocking, 30 minutes).** Read Kraken's stablecoin/FX fee table. If the fee is 0.20% per side or more, drop the 20-30 bp levels. If it is still above 0.10%, abandon the axis.

**Data.**
- `https://api.kraken.com/0/public/Trades?pair=USDTEUR&since=` (tick tape, paginated)
- `/0/public/OHLC?pair=...&interval=1` and `interval=1440`
- `/0/public/Depth?pair=...`
- `/0/public/OHLC?pair=EURUSD`

**Protocol.**
- Design: 2024-01 to 2026-03.
- Sealed control: the last 8 months, 2026-04 to 2026-11 (only 2026-03 to 2026-11 is left after design, so use 2026-04 onward).
- Budget: 9 trials (3 bid levels by 3 holding caps).
- Fill model: a bid at level L fills only if the cumulative tape volume at or below L is at least 3 times our size, with a 1-second queue-delay penalty. Daily-low wicks of -480 bp or worse are probably one-lot prints and must not count.
- Pass criteria:
  - at least 15 fills in design;
  - at least 80% recover to within 10 bp of par inside 10 days;
  - control net positive after the stablecoin fee;
  - the worst single fill is smaller than 4 average gains;
  - the result survives the 50 bp level only.

**Expectation.** EUR 20-50 per year (2-5%). Capital is idle otherwise, so the drag is nil. A real depeg to 0.90 on a 25% position costs about 2.5% of the portfolio.

**Main failure reason.** Few independent events and unfillable wicks. A single depeg dominates the tail. Treat a pass as a plausibility check, not statistical proof. The paper engine must fill resting limits only against real tape, or the result is fiction.

---

## 2. Open-interest washout reversal, with a mandatory delay ladder

**Payer.** Liquidated leveraged longs. Deleveraging is already done when open interest collapses, so the concession is paid to whoever absorbs the flow.

**Rule.**
- Universe: BTC, ETH, SOL and 3 other liquid Kraken perps (PF_).
- Signal: the 4h change in Binance USDT-M open interest (5-minute series) is in the bottom 5% of its trailing 90-day distribution, and the 4h return is below -1.5 sigma.
- Action: go long the Kraken perp at the next bar open, at 1x (2x only if the sealed control passes).
- Exit: after 6 hours or at a 2-ATR stop.
- Short side: only if a pre-declared symmetry test passes.
- Pre-registered entry delays: 5, 15, 30 and 60 minutes.

**Data.**
- `https://data.binance.vision/data/futures/um/daily/metrics/<SYM>/<SYM>-metrics-YYYY-MM-DD.zip` (5-minute OI, long/short ratios, taker ratio).
- Prices from `https://futures.kraken.com/api/charts/v1/trade/PF_XBTUSD/1m` or Binance klines in the same dump.
- Use only OI values published before the decision timestamp (the lookahead guard).

**Protocol.**
- Design: 2021-01 to 2025-12 (OI history for each symbol to be verified).
- Sealed control: 2026-01-01 to 2026-11-27, run once.
- Budget: 20 trials.
- Step 1: compute the share of events that coincide with wick-robot triggers, and report results with those events excluded.
- Pass criteria:
  - at the 15-minute delay, control net of costs is above 0 after 0.05% fee per side, 0.05% slippage and funding;
  - profit factor above 1.3;
  - at least 40 control events;
  - not driven by the top 3 events;
  - positive after excluding wick-overlap events.
- Kill rule: if the edge exists only at a delay under 5 minutes, report it as the wick effect re-measured and stop.

**Expectation.** The most likely outcome is near zero at a 15-minute delay. If it works, +5% to +20% per year with 20-30% drawdown at 2x, because events cluster in crashes.

**Main failure reason.**
- The edge is the same liquidation-cascade event the wick robot already trades, and it vanishes with delay.
- Events are clustered across symbols, so "4 of 6 symbols" is weak evidence. Judge on pooled, de-clustered events (one per crash day).

---

## 3. Token-unlock dilution short, beta-hedged (restricted universe)

**Payer.** Price-insensitive recipients (team and investors) and their market makers sell or hedge around the date. Retail longs ignore a public supply schedule, and shorting small caps is capacity-limited.

**Rule.**
- Universe: tokens with a Kraken PF_ perp that have a cliff unlock of at least 3% of circulating supply going to team or investors.
- Short the token perp at T-10 days and cover at T+1 day.
- Hedge with a long PF_XBTUSD leg, sized by 90-day rolling beta.
- At most 5 concurrent positions, 1x gross, 8% stop on the hedged pair.
- Skip if funding is below -0.05% per 8 hours (crowded short).

**Data.**
- Prices from the Kraken charts API. Check `openingDate` in `/derivatives/api/v3/instruments`.
- Unlock schedules are the weak point. DefiLlama emissions returns 402 (paid), so hand-build from project vesting docs and archived pages for the roughly 20-30 tokens that have a PF_ perp.
- Schedules must be point-in-time: use archived versions, not today's revised figures.
- Budget two days, not one. Stop if fewer than 60 events can be built.

**Protocol.**
- Design: 2023-01 to 2025-03.
- Sealed control: 2025-04 to 2026-11.
- Budget: 10 trials (2 entry/exit pairs by 2 size thresholds, plus the funding filter).
- Placebo: random dates on the same tokens.
- Pass criteria:
  - control beta-adjusted net mean per event above +1.5%;
  - hit rate above 55%;
  - at least 25 control events;
  - survives dropping the top 3 events and doubling costs;
  - placebo near zero.
- If fewer than 25 control events exist, the verdict is "inconclusive", not "pass".

**Expectation.** 0-5% per year, with a real chance of negative. A falling market flatters any short, so only the beta-adjusted figure counts.

**Main failure reason.**
- The effect is widely tracked and partly priced in (declines start about 30 days ahead, so a T-10 entry catches the tail).
- The published evidence conflicts across studies.
- The sample is thin on Kraken perps, and small-cap squeezes can cost 8% in a day.

---

## 4. Dated-futures basis, forward-logged and merged into the carry work already running

**Payer.** Leveraged longs who pay a convenience yield for long exposure. The return is locked at entry and does not depend on future funding.

**Rule.**
- Log the Kraken dated-contract term structure (FF_XBTUSD_YYMMDD, FF_ETHUSD_YYMMDD) every hour from `https://futures.kraken.com/derivatives/api/v3/tickers`, plus the spot index.
- Compute the annualised basis net of costs.
- Paper-enter spot long plus dated short only if the net basis is at least 8% per year over cash.
- Hold to expiry, with futures leverage at most 2x and a margin buffer of 30% or more.

**Data and protocol.**
- The Kraken charts API probably does not serve expired contracts. Check once (Deribit expired-contract history is the fallback). If neither works within 2 hours, run forward-only.
- Do not run a separate backtest. Reuse the cash-and-carry harness already in progress and add the dated leg as one more variant (max 4 parameters).
- Stress test: +30% spot move in 3 days, with daily mark-to-market of margin. Pass requires no liquidation and margin utilisation under 60%.
- Sealed control: forward paper, 2 expiry cycles.
- Pass: net annualised return at least 3 points above cash (about 2%).

**Expectation.** Net +2-3% on total capital (the spot leg and margin buffer each tie up cash). It is hard to distinguish from the cash rate. The value is mostly in answering "is fixed carry better than floating carry?" at low marginal cost.

**Main failure reason.**
- Dated contracts are inverse (coin-margined, USD-quoted) while the spot leg is EUR, which adds EUR/USD exposure and convexity.
- Dated-contract volume is tiny, so paper fills are optimistic.
- The basis is thin today (about 7% per year at best), and there are only a handful of independent episodes.

---

## 5. Hack and exploit short on a deterministic severity ratio (no LLM in the loop)

**Payer.** Slow holders of an affected token, and market makers who widen spreads only after the fact.

**Rule.**
- Event source: `https://api.llama.fi/hacks` (free, 1,378 incidents).
- Severity = amount lost / token market cap, or / TVL for protocol tokens.
- Trigger: severity at or above 5%, and the affected token (or the native chain token for bridge hacks) has a Kraken PF_ perp.
- Entry: 30 minutes after the source article timestamp. Timestamps come from the linked source or Wayback. Drop events without a recoverable intraday time.
- Short at 1/10 of equity, 2x maximum, hold 3 days or stop at +8%.
- Beta-hedge comparison against a BTC perp short over the same window.

**Protocol.**
- Design: 2021-01 to 2024-06 (fix the threshold and horizon only).
- Sealed control: 2024-07 to 2026-11.
- Budget: 6 trials.
- Lag ladder: report at 5, 30 and 240 minutes.
- Placebo: random dates on the same tokens.
- Pass criteria:
  - control mean net CAR at the 30-minute lag above +1.5%;
  - at least 15 events;
  - bootstrap 80% lower bound above 0;
  - placebo near zero.
- Reject if the edge exists only at a lag of 5 minutes or less.

**Expectation.** 0-5% per year with fewer than 15 trades a year. The most likely outcome is "inconclusive: too few events".

**Main failure reason.**
- Under 15 control events is likely, since few hacked tokens have a PF_ perp.
- The first-minute move carries most of the drift.
- Beta and rebound confound the 3-day window.
- An LLM classifier adds nothing here and leaks the control period through memorised outcomes, so keep it out.

---

## Rejected ideas

| Idea | One-line reason |
|---|---|
| Macro-release windows (pre-FOMC/CPI drift, post-event fade) | Underpowered by construction: about 3% per-trade standard deviation and 15 control events make t above 2 unreachable. About 8 trades per year caps the return at about 2%. |
| Post-listing fade on new tokens | Kraken lists perps late and only for established tokens, so the sample is a handful of events. Binance results do not transfer, and one squeeze gap erases a year. |
| Perp premium dislocation fade (1-minute, single asset) | A few basis points of gross edge against 0.15-0.20% round trip. The mark-versus-spot signal is circular, and maker fills suffer adverse selection. |
| Cross-sectional perp premium reversal (market-neutral) | Most of the measured reversion is bid-ask bounce and index noise. A 6-leg book with a hedge costs more than the tails pay, and it is the funding signal that already collapsed. |
| PAXG/XAUT versus XAU perp spread | The author's own arithmetic: 30-60 bp of cost against about 34 bp capturable. Only 80 days of history, no weekend effect found, and perp eligibility for EU retail is uncertain. |
| LLM-structured token unlock calendar | A subset of axis 3 with an extractor bolted on. It is a 2-3 day data job that fails the one-day limit, and the LLM adds no edge. |
| Exchange delisting and monitoring-tag short | The tokens that get delisted rarely have a Kraken perp, so there are fewer than 10 events. The Binance endpoint is unverified, and the reaction is instantaneous. |
| LLM-classified hack and regulatory shorts | The control period lies inside the model's knowledge, so it leaks. The sub-minute move dominates, and the plain severity ratio in axis 5 does the same job. |

**Suggested order of work.**
1. Axis 1, starting with the fee check (half a day).
2. Axis 2, starting with the wick-overlap count (one day).
3. Axis 4, as a small add-on to the carry harness that is already running.
4. Axis 5, once the event count is known (a quick data check).
5. Axis 3, only if time remains and at least 60 point-in-time events can be built.

Expect two or three of these to end as "inconclusive" or "fail". That is a valid outcome and should be recorded as such, with no further tuning.
