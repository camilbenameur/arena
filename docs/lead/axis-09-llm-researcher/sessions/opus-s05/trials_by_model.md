# Trial log written by the model (verbatim)

# Result: NO ROBUST EDGE FOUND

I ran 12 of the 15 allowed trials. None of them showed a cost-adjusted edge that held up. The rule handed back is the most defensible simple rule I had. It is labelled "no robust edge found" and is not a discovery.

## Setup
- Every trial was scored with `sandbox_backtest.simulate`: 12 bp per side, a 0.3-unit trading band, and funding.
- Time split: H1 = 2026-07-01 to 08-15, H2 = 2026-08-16 to 09-30. I also report each month.
- Per-ticker figures come from running the backtest on one ticker's weights at a time.
- Unless a trial says otherwise, the rule decides once a day, on the 20:00 UTC bar, to keep turnover down. Weights are ±1 per leg.
- I wrote the candidate list and its rationales before looking at any result. Three candidates were never tested: BTC→alt lead-lag, fading volume shocks, and time-of-day seasonality. Their mechanisms were the weakest, or too fast for 24 bp round-trip costs.

## Trial log (every variant that was run)

| # | Idea | Economic rationale | Parameters | Full: return / maxDD / Sharpe / turnover | H1 / H2 | Jul / Aug / Sep | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | Cross-sectional funding carry, market-neutral | Leveraged longs pay a premium; short the most crowded coins, collect funding | 7-day mean funding; long the 2 lowest, short the 2 highest; weekly rebalance | -3.5% / -7.4% / -1.2 / 8.5x | +0.4 / -4.0 | -0.7 / -4.3 / +1.2 | Reject. Funding differences across coins are only ~2–7% a year, so the carry is tiny. Price moves (ETH up) swamp it. |
| 2 | Time-series trend, per ticker | Investors under-react, then herd; a slow signal keeps costs small | Sign of 120-bar (20-day) return; daily decision | +12.3% / -16.4% / 1.37 / 17.3x | -3.8 / +17.0 | -2.3 / +16.7 / -2.1 | Weak. All the gain is in August. |
| 3 | Cross-sectional momentum, 7 days | Attention and money rotate between coins | 42-bar return; long top 2, short bottom 2; daily | +0.7% / -6.2% / 0.33 / 29.9x | +0.8 / 0.0 | +0.1 / +3.1 / -2.3 | Reject. Nothing left after costs. |
| 4 | Cross-sectional 1-day reversal | Getting paid to supply liquidity after overshoots | 6-bar return; long the 2 losers, short the 2 winners; daily | -14.5% / -16.3% / -6.3 / 71x | -7.8 / -7.3 | negative every month | Reject. Costs plus a wrong sign. |
| 5 | Market trend filter on the basket | Avoid holding through drawdowns | Long all 6 if the basket's log price is above its 120-bar mean, else flat | +20.5% / -14.0% / 1.90 / 13.2x | -5.9 / +28.0 | -3.9 / +23.6 / +0.7 | Reject. It is just conditional long beta, and it loses in H1. |
| 6 | 3-day residual reversal vs the basket | Coin-specific overreaction | 18-bar return minus basket return; long the 2 lowest, short the 2 highest; daily | -9.9% / -11.4% / -4.5 / 45x | -4.0 / -6.4 | negative every month | Reject. |
| 7 | Slow cross-sectional momentum | Same as #3, but slower to cut costs | 120-bar return; long top 2, short bottom 2; weekly | -1.6% / -6.9% / -0.57 / 3.9x | -2.2 / +0.3 | -0.4 / -3.7 / +2.4 | Reject. |
| 8 | #2 stability check | — | Lookback 60 bars | -12.8% / -27.0% / -1.12 / 28x | -10.5 / -2.5 | -9.6 / +14.4 / -15.1 | Fails the stability check. |
| 9 | #2 stability check | — | Lookback 180 bars | +30.6% / -9.8% / 2.96 / 7.6x | +3.2 / +26.6 | 0.0 (warm-up) / +14.9 / +12.6 | Looks good, but see the beta test below. |
| 10 | #2 with volatility scaling | Size each coin by risk | 120-bar sign × (50% target vol / realised vol), capped at ±2 | +19.3% / -15.0% / 1.79 / 23x | -4.5 / +24.6 | -2.8 / +23.1 / -1.3 | Weak. All in August. |
| 11 | Funding-crowding timing on the basket | High funding means crowded longs and a fragile market | Long the basket only when 3-day mean funding ≤ 30-day mean | +4.9% / -11.9% / 0.87 / 17x | +1.3 / +3.6 | 0.0 / +11.4 / -6.4 | Reject. |
| 12 | Equal-weight ensemble of time-series trend lookbacks | Same as #2; averaging the lookbacks avoids choosing one by search | Mean of the signs over 60, 120 and 180 bars; daily decision | +9.2% / -14.3% / 1.16 / 16.2x | -3.6 / +13.4 | -4.0 / +15.7 / -1.9 | **Handed back.** No edge. |

**Beta test.** This was an extra check, not a new rule. I regressed daily gross returns, from 31 July onward, on the equal-weight basket. Gross means before trading costs.

| Rule | Beta | Alpha (bp/day) | t-stat |
|---|---|---|---|
| #9 | 0.79 | -5 | -0.4 |
| #10 | 0.79 | -18 | -1.0 |
| #12 | 0.69 | -20 | -1.45 |

Every trend variant's return is explained by its long exposure in a rising market. Gross alpha is zero or negative even before costs, and costs take it further down.

## Why I chose #12
- It has a mechanism with a long track record: time-series momentum in crypto and futures generally.
- It uses no parameter picked by search. I deliberately did **not** pick the best lookback (180). The lookback results range from -13% to +31%, which is how fragile this signal is.
- Turnover is moderate (~16x equity per quarter, so about 2% cost drag).
- It can go short, so it can cut losses in a sustained bear market.
- It passes a causality check: I recomputed it on data cut off at 60 random bars and got 0 mismatches. Output has no NaN and stays within [-2, 2].

## Known weaknesses
- I found no alpha. The design-period profit (+9.2%) is all long beta in an uptrend, and the strategy did much worse than the basket (+61%).
- Results depend heavily on the lookback.
- Profit is concentrated in August; July and September lost money.
- Per ticker, LINK made +4.5% and BTC and XRP lost. Whipsaw losses are likely in choppy markets.
- There is a 30-day warm-up and one trading decision per day.

## Out-of-sample expectation (honest)
- In a trending market, up or down, it should make money with beta of about 0.5–0.7 to the trend's direction.
- In a range-bound market, expect a small loss: about 2% per quarter in costs, plus whipsaw. Drawdowns of 15–25% are plausible.
- Compared with random weights at the same turnover, I expect no reliable advantage beyond what its trend-following exposure gives.
- Compared with the 2x trend engine, it should be less volatile because it runs at about half the gross exposure.
- My expected alpha after costs is about zero or slightly negative.
