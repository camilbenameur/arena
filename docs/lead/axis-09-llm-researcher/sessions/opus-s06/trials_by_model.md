# Trial log written by the model (verbatim)

# Research log: no robust edge found

**Verdict:** None of the 11 trials found an edge that holds up after costs. All of them are listed below, including the failures. The rule I'm handing back (T6) is a simple fallback for controlling risk. It is **not** an alpha finding.

**Setup**
- I wrote down all candidates and their parameters, with an economic rationale for each, before looking at any result. Parameters were not tuned.
- The sandbox `simulate` scored every trial (24 bp per round trip, funding charged, 0.3 no-trade band).
- **Time split:** H1 = 2026-07-01 to 2026-08-15, H2 = 2026-08-16 to 2026-09-30. Each half was simulated on its own.
- **Reference:** the basket in the sandbox makes +59.1% (Sharpe 4.09, max drawdown -9.8%). H1 +7.9%, H2 +47.3%.
- **Shared settings:** cross-sectional (XS) rules hold 2 longs and 2 shorts at ±1 weight. Signals update once a day at the 00:00 UTC close unless noted.

## Trial log

| # | Idea | Economic rationale | Params | Full period: return / max DD / Sharpe / turnover | H1 / H2 | Verdict |
|---|---|---|---|---|---|---|
| 1 | XS funding crowding: short the highest funding, long the lowest | Crowded leveraged longs pay a premium and later unwind; short the crowd and collect funding | 3-day summed funding, daily | -13.6% / -14.5% / -5.1 / 39x | -4.9% / -9.2% | **Reject.** Loses in both halves and in every month. |
| 2 | XS momentum | Slow spread of information across alts; attention flows into winners | 7-day return, daily | +0.7% / -6.2% / 0.3 / 30x | +0.8% / 0.0% | **Reject.** Zero after costs; September -2.3%. Profit comes from ETH (+7%) while XRP loses 6.6%. |
| 3 | XS short-term reversal | Paid for supplying liquidity against overreaction | 1-day return, daily | -14.5% / -16.3% / -6.3 / 71x | -7.8% / -7.3% | **Reject.** Negative even before costs, and turnover is high. |
| 4 | Basket timed by funding: long only when the average 3-day funding is below its trailing 30-day median | When longs are crowded, forward returns are worse | Daily | +14.4% / -7.5% / 2.1 / 24x | +3.3% / +10.7% | **Reject.** Average exposure is 0.38. 0.38 × basket would be about +22%, so the timing **subtracts** value. September -2.5%. |
| 5 | Long/flat per ticker: long when the close is above its 20-day SMA | Trend-followers and underreaction; step aside in drawdowns | 20-day SMA (120 bars), daily | +25.4% / -9.4% / 2.4 / 8.4x | -4.0% / +30.6% | **Weak.** Average exposure 0.53. That is below 0.53 × basket (about +31%), so there is no timing alpha. July -4.0%. Low cost. **Chosen as the fallback.** |
| 6 | Betting against beta: long low-beta, short high-beta, beta-neutral | Investors with limited leverage overpay for high beta | 30-day beta, daily | +0.3% / -5.2% / 0.1 / 2.9x | -2.7% / +4.0% | **Reject.** Results flip sign between the halves. |
| 7 | Trial 1 with the sign flipped: long high funding | Persistent leveraged demand (*post hoc*) | Same as trial 1 | +4.3% / -2.7% / 1.5 / 43x | -0.3% / +4.6% | **Reject.** I picked it after seeing trial 1, H1 is negative, and all of the profit is from August. |
| 8 | Long/short per ticker against the 20-day SMA | Two-sided version of trial 5, comparable to the trend engine | 20-day SMA, daily | +9.0% / -17.4% / 1.1 / 15.5x | -5.4% / +15.2% | **Reject.** Drawdown is large, and July (-3.2%) and September (-3.2%) both lose. |
| 9 | XS momentum on a longer horizon, rebalanced weekly | Like trial 2, with less turnover | 14-day return, Sunday 00:00 | -13.4% / -15.8% / -5.2 / 7.8x | -3.7% / -10.3% | **Reject.** This contradicts trial 2, so there is no stable momentum effect. |
| 10 | Stability check of trial 5 | – | 10-day SMA | +18.0% / -12.5% / 1.85 / 17.4x | -5.4% / +24.9% | Same story: below 0.53 × basket, and July loses. |
| 11 | Stability check of trial 5 | – | 40-day SMA | +44.3% / -9.8% / 3.6 / 2.7x | +1.0% / +42.9% | Not informative. The 40-day warm-up keeps it flat through July, and after that it is almost the basket. |

## Monthly results for the chosen rule (trial 5, 20-day SMA)
- **Months:** July -4.0%, August +22.4%, September +6.1%.
- **Gross profit by ticker:** BTC 2.6, ETH 3.1, SOL 5.2, XRP 2.9, LTC 4.7, LINK 6.5 (in % of equity). The profit is spread across tickers rather than coming from one.
- **Causality:** I re-ran the rule on data cut off after bar t, for 20 different t. Row t matched exactly every time. There are no NaNs.

## Why I chose it and what to expect
- **Market-neutral ideas (trials 1, 2, 3, 6, 7, 9):** none was positive in both halves after costs. The funding spread between tickers (about 2–7% a year) is too small to pay for 24 bp round trips.
- **Long/flat trend filter:** this is the most defensible simple rule.
  - It has few parameters, all set from economics: a 20-day mean and one decision a day.
  - Turnover is low, about 8x equity per quarter, which is roughly a 1% cost drag.
  - Profit is spread across tickers.
  - Its only plausible benefit is going flat during long downtrends.
- **Main weakness:** on this data it is just about 0.5x market beta with no timing value. Per unit of exposure it did worse than the basket in every comparison. It loses in choppy markets (July), and the 10-day and 20-day versions show the same weakness.

## Out-of-sample expectation
- Treat the rule as conditional market exposure: about 0.5x the basket on average.
- **Rising market:** about half the basket's return.
- **Falling market, if it trends:** much smaller losses than the basket, because the rule goes flat.
- **Choppy market:** small whipsaw losses, a few percent a quarter.
- **Alpha versus random weights with the same turnover:** none expected, apart from its long bias.
- It should beat the 2x trend engine only because its drawdowns are smaller and its costs lower, not because it predicts better.
