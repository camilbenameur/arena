# Trial log written by the model (verbatim)

## Result: no robust edge found

I tested 10 rules out of the 15 allowed and stopped on purpose. The idea that looked best (Trials 6, 9 and 10) did not hold up when I changed the lookback or split the period in two. More tweaking would only have fitted noise.

**Candidates written down before seeing any result:**
- **C1:** Cross-sectional funding contrarian. Crowded leveraged longs pay funding and overextend.
- **C2:** Cross-sectional 7-day momentum. Information and attention spread slowly across coins.
- **C3:** Cross-sectional 1-day reversal. Paid for supplying liquidity against overreacting flow.
- **C4:** Per-ticker 20-day trend. Slow trend-following and hedging flows, with less trading than the 4-hour EMA engine.
- **C5:** Volatility-managed basket. Volatility clusters and risk-averse traders deleverage.
- **C6:** Basket that goes flat when funding is extreme. Crowding leads to liquidation cascades.
- **C7:** Reversal after a big move on abnormal volume.
- **C8:** BTC moves leading the other coins at 4 hours.

I never tested C6, C7 or C8. Trial 1 suggested C6 would hurt. Trial 3 showed that reversal loses, so C7 looked unlikely. C8 would trade too often for 24 bp round trips.

**Common settings:**
- Cross-sectional rules ("XS" below) are market-neutral: long the 2 best-ranked coins at +1, short the 2 worst at -1.
- Every rule rebalances once a day, at the 20:00 bar close, and holds in between.
- All results come from `sandbox_backtest.simulate`, with costs included.
- Time split: H1 = 1 Jul to 15 Aug, H2 = 15 Aug to 30 Sep.
- My sub-period runs start flat and lose the bar at each boundary. So the month figures don't match the reference: the basket shows Jul +5.6% here against +10.3% in the reference.

**Benchmark, not a trial:** basket 1x returns +59.1%, Sharpe 4.09, max drawdown -9.8%, turnover 1x. H1 +6.8%, H2 +47.0%.

| # | Idea | Parameters | Return | Sharpe | Turnover | H1 / H2 | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | XS funding contrarian (long low funding, short high) | 3-day (18-bar) funding sum | -13.6% | -5.1 | 39x | -4.9 / -9.1 | Reject. Loses in all 3 months. |
| 2 | XS momentum | 7-day return | +0.7% | 0.3 | 30x | +0.1 / -0.4 | Reject. Zero after costs. |
| 3 | XS reversal | 1-day return | -14.5% | -6.3 | 71x | -7.0 / -7.1 | Reject. Flipping it would also lose, because gross profit (~6%) is below costs (~8.5%). |
| 4 | Per-ticker trend, ±1 on the sign of the return | 20-day return | +12.3% | 1.4 | 17x | -4.5 / +16.4 | Reject. Return comes from August only; on average 1/3 net long in a rising market. |
| 5 | Volatility-managed long basket | 60% annual volatility target, 7-day realised volatility, weight capped at 0 to 2 | +76.8% | 3.94 | 6.5x | +1.4 / +71.6 | Reject. It is just the basket with 1.29x leverage; Sharpe is not better. |
| 6 | Trial 1 flipped: long high funding, short low ("funding momentum" = buy what longs pay up for). Decided after seeing Trial 1. | 3-day funding sum | +4.3% | 1.5 | 43x | -0.3 / +4.5 | Suspect. Return is all in August, and LTC loses. |
| 7 | Stability check of Trial 4 | 10-day trend | -12.8% | -1.1 | 28x | -11.2 / -2.8 | Trial 4 is unstable. |
| 8 | Stability check of Trial 4 | 40-day trend | +38.7% | 3.4 | 3x | +1.6 / +35.2 | Not a trend result: flat during the 40-day warm-up, then mostly long. |
| 9 | Stability check of Trial 6 | 1-day funding sum | -1.2% | -0.3 | 72x | -3.3 / +1.1 | Gross profit is used up by costs. |
| 10 | Stability check of Trial 6 | 7-day funding sum | +2.3% | 0.9 | 19x | +2.7 / -0.5 | Sign flips between halves; September -5.4%. Trial 6 rejected. |

**What I learned:**
- Funding-momentum (Trials 6, 9, 10) made a small gross profit at every lookback, about 5–10% over the quarter. After costs it was close to zero, and which half did better changed with the lookback. It also depended on SOL, XRP and ETH, and it was chosen after seeing Trial 1. It is not deployable.
- Time-series trend changed sign with the lookback: 10 days lost, 20 days gained, 40 days was really just long. That is noise plus the rising market.
- Ranking strategies that rebalance daily lose about 4–9% a quarter to costs (30–70x turnover × 12 bp per side). Any real signal must clear that.

**Chosen rule:** the equal-weight long basket at 1x (+1 in every contract).
- It has no fitted parameters and turnover of about 1x, so it cannot be overfitted.
- It labels itself honestly as "no edge": it only collects whatever crypto risk premium exists.
- It meets causality and the output format (552×6, no NaN, all 1.0).

**Known weaknesses:**
- It is 100% market beta. It is not a finding and adds nothing over the basket benchmark; it matches it by construction.
- In a falling or crashing period it loses roughly in line with the market. A -30% or worse quarter is possible, and nothing limits the drawdown.
- Funding is paid while long: about 2–7% a year at design-period rates, and more if funding spikes.

**Expected out-of-sample behaviour:**
- Return ≈ the equal-weight return of the six contracts, minus about 0.1% in costs and about 1–2% a quarter in funding.
- Excess return over the basket ≈ 0. It should beat random weights with the same turnover only if the market rises.
- It should beat trend 2x only if the market rises without sharp reversals.
- The design-period +59% and Sharpe 4 reflect one strongly rising regime and should not be expected again.
