# Trial log written by the model (verbatim)

# Result: no robust edge found

None of my 12 trials showed an edge beyond simply being long a rising market (the basket's beta), after 24 bp round-trip costs. No trial held up in both halves of the design period. The rule I am handing back is the most defensible simple one, a slow long/flat trend filter. **It is labelled "no robust edge found".**

## Protocol
- I wrote 10 candidate rules, each with a mechanism, before looking at any result (C1–C10 below).
- I evaluated 12 variants with `simulate`. Running the equal-weight basket as a reference does not count as a trial.
- Splits I report for every trial:
  - **Time split:** H1 = 2026-07-01 to 2026-08-14, H2 = 2026-08-15 to 2026-09-30. Each half is simulated from flat, so entry costs are included.
  - Return by month and by ticker.
- 20-day lookbacks need 120 bars of warm-up, so those rules are flat for roughly the first 20 days of July.
- **Reference (sandbox):** basket 1x returned +59.1%, max drawdown −9.8%, Sharpe 4.09. By half: H1 +6.8%, H2 +47.0%. By month: Jul +5.6%, Aug +28.5%, Sep +15.9%.

## Trial log

| # | Idea | Rationale (who is on the other side) | Parameters | Design result (full / H1 / H2; turnover) | Verdict |
|---|---|---|---|---|---|
| 1 | Cross-sectional funding carry: short the 2 highest-funding contracts, long the 2 lowest | Crowded leveraged longs pay a premium; you get paid funding and fade the crowding | 3-day average funding, rebalance daily, ±1 | −11.3% / −4.7% / −7.0%; 39x | Fail. High funding tracked momentum rather than predicting reversal. The funding spread (~1 bp per bar) is far too small to cover costs. |
| 2 | Cross-sectional momentum, market-neutral | Information spreads slowly across alts; herding | 7-day lookback, long top 2 / short bottom 2, rebalance daily | +0.0% / +1.0% / −2.1%; 29x | Fail (it is noise; XRP alone lost −10%) |
| 3 | Per-ticker trend, long/flat | Time-series momentum from slow-moving capital; low turnover | close > 20-day SMA → 1, else 0 | +32.9% (drawdown −7.2%, Sharpe 2.93) / −5.0% / +38.4%; 15x | Mostly beta: average exposure 53%; Jul −4.2%. All 6 tickers positive (+2 to +8%). |
| 4 | Basket long, switched on by basket trend | Collect the risk premium, avoid downtrends | Basket 20-day momentum > 0 | +22.2% / −6.9% / +31.2%; 22x | Worse than #3 and than the basket. Reject. |
| 5 | Cross-sectional 1-day reversal | Providing liquidity to forced flows | Long 2 losers / short 2 winners, rebalance daily | −9.6% / −6.5% / −2.2%; 77x | Fail, eaten by costs |
| 6 | Low-volatility, market-neutral | Demand for lottery-like high-vol coins | 10-day realised vol, long 2 lowest / short 2 highest | −2.8% / −3.1% / +1.2%; 11x | Fail |
| 7 | BTC leads alts | Slow arbitrage across venues | Alts take the sign of BTC's last 4h return if \|r\| > 1% | −7.1% / −9.3% / +2.4%; 87x | Fail |
| 8 | Funding crowding, long/flat | Elevated funding means crowded longs and weak forward returns | Long if 3-day funding ≤ its own trailing 30-day median | +9.8% / +2.1% / +6.4%; 40x | Below the basket at the same exposure. No edge. |
| 9 | Fade volume shocks | Forced liquidations overshoot | \|r\| > 2σ and volume > 2× median → fade for 6 bars | −11.8% / −2.2% / −10.0%; 29x | Fail |
| 10 | Donchian breakout, long/short | Trend persistence | 20-day breakout entry, 10-day exit | +13.3% / −1.9% / +14.3%; 4.6x | Profit came from August only (Jul −2.2%, Sep −2.2%). Reject. |
| 11 | Stability check of #3 | Same as #3 | 15-day SMA | +24.1% / −6.6% / +31.3%; 25x | Same pattern as #3 |
| 12 | Stability check of #3 | Same as #3 | 30-day SMA | +33.5% / −3.7% / +37.1%; 13x | Same pattern as #3 |

Candidates written but never tested: none beyond the above. C1–C10 map to trials 1–10; trials 11 and 12 are parameter checks of trial 3. I stopped at 12 of the 15 allowed trials, on purpose.

## Chosen rule: trial 3, unchanged parameters
For each contract: hold weight 1.0 while the 4h close is above its 20-day (120-bar) simple moving average, otherwise hold 0.
- **Why I chose it:**
  - The mechanism is well documented: time-series momentum, plus cutting exposure in downtrends.
  - It has one parameter, set in advance rather than by search.
  - It is stable across 15, 20 and 30 days: +24%, +33% and +34%.
  - Profit is spread over all six tickers, with no dependence on one ticker.
  - Turnover is low: 15x over the period, so costs were about 1.8% of equity.
  - It is long-only, so there is no short-squeeze tail.
  - It passed a mechanical causality check: I recomputed it on truncated data at 15 dates and got zero mismatches.
- **Diagnostic:** before costs, it earned about 20% more per unit of exposure than the basket. That is not statistically meaningful on one ~3-month uptrend, and part of it comes from skipping the weak early July.

## Known weaknesses
- H1 was negative for every lookback (choppy July with whipsaws); all the gain came in the H2 uptrend. The time split therefore does **not** confirm any timing skill.
- On a beta-adjusted basis it roughly matches the basket. It will underperform the basket in any sustained uptrend, since it averages about 50% exposure.
- It loses money in sideways, choppy markets: whipsaw trades cost about 24 bp each round trip.
- It is flat for the first 20 days if it gets no history before the period it is run on.
- The sandbox simulator approximates fills at the close; the real judge fills at the next minute.

## Expected out-of-sample behaviour (honest)
- **Alpha:** I expect none to be demonstrable. The best guess is about 0.4–0.6× market beta, with losses cut in prolonged declines.
- **Costs:** about 0.5–0.7% of equity per month.
- **By market type:**
  - In an uptrend: positive, but below the basket.
  - In a downtrend: small losses, much smaller than the basket's, because the rule goes flat.
  - In a range: slightly negative, about −2% to −6% per month at worst, as in July.
- **Against random weights with the same turnover:** it should beat them only to the extent the market trends.
