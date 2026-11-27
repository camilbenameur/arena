# Trial log written by the model (verbatim)

# Trial log: verdict NO ROBUST EDGE FOUND

**Headline.** None of the 12 variants I tested (out of 15 allowed) shows an edge that survives my own checks. The frozen rule is the most defensible simple fallback, not a discovery: a long/flat 7-day breakout per contract, volatility-scaled. Its design-period profit is explained by market beta, and its timing contribution was slightly negative.

## Protocol
- Ten candidate rules, each with a mechanism, were written down before any result was seen (list in the session; mapped to trials below).
- Every variant was scored with `sandbox_backtest.simulate`. Twelve variants were run in total and all twelve are listed here.
- Time split: A = Jul 1 – Aug 15, B = Aug 16 – Sep 30. Weights were computed causally on the full history and then simulated on each slice.
- Parameters were set from the economics before running (7-day look-back, 10-day volatility span, 2.5% daily volatility target per contract). Nothing was optimised.
- The only data inspected before the trials were descriptive statistics: funding averages 2–7% annualised per contract, daily volatility is 1.8–3.3%, and correlations are 0.5–0.85.

## Trials (design period, net of 12 bp per side and funding)

| # | Idea and mechanism | Parameters | Full: return / max drawdown / Sharpe / turnover | A / B | Jul / Aug / Sep | Verdict |
|---|---|---|---|---|---|---|
| 1 | Multi-horizon time-series trend, long/short, vol-scaled. Under-reaction and liquidation cascades; other side is forced sellers and faders. | sign of 3/7/14-day return, averaged | +2.4% / -15.6% / 0.47 / 78x | -12.3 / +16.9 | -9.0 / +17.2 / -3.6 | Fail: sign flips between halves, turnover far too high. |
| 2 | Cross-sectional momentum, market-neutral. Slow flow diffusion across alts. | 7-day vol-adjusted return, top 2 vs bottom 2, daily rebalance | -8.4% / -10.9% / -3.06 / 31x | +0.5 / -8.8 | +0.6 / -1.6 / -7.3 | Fail: the loss is mostly XRP (-10.3%). |
| 3 | Cross-sectional 1-day reversal. Liquidity provision after idiosyncratic shocks. | 1-day return, bottom 2 vs top 2, daily rebalance | -14.1% / -16.3% / -6.46 / 67x | -7.4 / -7.3 | -4.4 / -6.4 / -4.2 | Fail: negative even before costs, in every month. |
| 4 | 7-day breakout, stop-and-reverse, long/short per contract. Same mechanism as 1 with built-in hysteresis. | n=42 bars | +1.1% / -17.2% / 0.32 / 23x | -4.2 / +5.2 | -2.6 / +13.3 / -8.4 | Fail: about zero; August only. |
| 5 | Same breakout, long/flat. Crypto drift plus trend persistence, with flat as protection in down-trends. | n=42 bars | +24.4% / -8.4% / 2.51 / 12.6x | -1.3 / +25.9 | -1.9 / +22.9 / +2.9 | Beta, not edge. Chosen as fallback (see below). |
| 6 | Beta-neutral low-beta: long BTC, short alts by 1/beta. Lottery demand for high-beta alts. | 30-day EWMA beta | -6.8% / -8.6% / -2.79 / 0.8x | -0.5 / -6.1 | 0.0 / -2.1 / -3.7 | Fail: one slow bet with no statistical power, and it lost. |
| 7 | Funding-crowding contrarian. Over-leveraged longs pay up before unwinding. | z-score of 3-day funding against own 30 days | -10.1% / -11.7% / -2.87 / 29x | -2.3 / -8.0 | -1.0 / -0.4 / -8.8 | Fail. Funding is too small here to mark crowding. |
| 8 | Fade extreme 1-day moves (over 2 sigma), hold 1 day. Liquidation overshoot. | k=2, hold 6 bars | -16.7% / -27.1% / -1.55 / 30x | +3.6 / -19.8 | +3.9 / -21.2 / +1.6 | Fail: extremes continued in August; 464 short bar-slots vs 141 long, so it was mostly fading the rally. |
| 9 | Breakout as in 4, only when volume exceeds 1.5x the trailing median. Informed flow continues. | n=42, m=1.5 | +6.2% / -15.8% / 0.86 / 19x | -1.1 / +7.2 | +0.4 / +12.8 / -5.8 | Fail: indistinguishable from 4 within noise; LINK supplies +7.6%. |
| 10 | BTC-led trend: all six contracts follow BTC's breakout state, long/short. BTC leads price discovery. | n=42 | +9.7% / -16.2% / 0.99 / 23x | -6.1 / +16.7 | +0.8 / +16.9 / -7.1 | Fail: August only; drawdown is larger than the gain. |
| 11 | Stability check of 5. | n=30 | +17.1% / -11.5% / 1.84 / 17x | -4.8 / +23.0 | -6.7 / +25.6 / -0.2 | Same picture as 5. |
| 12 | Stability check of 5. | n=60 | +18.7% / -9.1% / 2.12 / 10x | -4.0 / +23.4 | -3.7 / +21.1 / +0.9 | Same picture as 5. |

Pre-registered ideas not run, and why:
- **Pure funding carry:** the funding spread across contracts is about 5% a year against 2–3% daily volatility, so the expected Sharpe is negligible.
- **4-hour BTC-to-alt lead-lag:** 24 bp per round trip against roughly 1% volatility per bar would need an implausible hit rate.
- **Trend plus carry:** the carry leg is immaterial for the same reason as pure carry.

Three trials were left unused on purpose; more searching on three months of data would only manufacture a fit.

## What the evidence says
- **Trend, in five forms (1, 4, 9, 10 and the reference engine):** each made money only in August, was flat or negative in July, and lost in September even though the basket rose 18.9% that month. Half A was negative for all of them. That is one episode, not a repeatable edge.
- **Market-neutral ideas (2, 3, 6, 7):** all negative.
- **Fading extremes (8):** negative.
- **Long/flat breakout (5, 11, 12):** stable across look-backs (+17%, +24%, +19%), but the return is beta. Average exposure was about 0.58 of the basket; holding the basket at that constant exposure would have made roughly 1.61^0.58 − 1 ≈ 32%. The rule made 24.4% net, or about 26% before its roughly 1.5% of costs. Timing therefore subtracted about 6 points, which is statistically indistinguishable from zero.
- **Concentration in rule 5:** all six contracts contributed zero or more (XRP +0.03%, LINK +8.1%, the rest in between), but August alone was +22.9% against -1.9% and +2.9% for the other months.

## Chosen rule and why
Rule 5, unchanged, with n=42 fixed before the stability checks and not picked from them. For each contract:
- Go long after the close exceeds the highest close of the previous 42 bars (7 days).
- Go flat after the close falls below the lowest close of the previous 42 bars.
- Hold the state in between; never short.
- Size is 2.5% divided by the EWMA daily volatility, capped at 2.

Reasons for choosing it despite no demonstrated edge:
1. It relies only on two long-documented and economically motivated effects: crypto drift (risk premium) and trend persistence with fast, V-shaped sell-offs. The second is why the short side is dropped: shorts added about -23 points here and doubled turnover.
2. Its downside is bounded. In a falling market it steps aside instead of holding the basket's losses.
3. Turnover is low, about 12.6x per quarter, which costs about 1.5% per quarter. Doubling the cost assumption removes only about another 1.5%.
4. It is insensitive to the look-back (30, 42 and 60 bars give the same picture).
5. Causality was verified by recomputing on truncated data at 40 random bars with exact equality. Output is identical under row shuffling, contains no NaN, and stays within [0, 2].

## Known weaknesses
- **No timing skill was shown in the design period.** It under-performed an exposure-matched basket, and split half A was negative (-1.3%) while B was +25.9%. Essentially the whole design profit is August.
- **It is long-biased.** Against the 1x basket it will lag in a steady rally (design: +24% against +61%). It can only beat the basket if the unseen period contains a sustained decline.
- **Choppy, range-bound markets are its bad case** (July: -1.9%; neighbouring look-backs -3.7% to -6.7%). Repeated false breakouts could cost roughly 5–10% in a quarter. Design maximum drawdown was -8.4%; I would expect up to about -15% out of sample.
- **Per-contract signals are highly correlated**, so it is effectively one market-timing bet with little diversification.
- **Warm-up:** if the unseen data starts without history, there are no positions until the first up-breakout after about 7 days (first position in design: Jul 10).
- **Simulator mismatch:** the bar-level simulator is only an approximation of the minute-level judge.

## Honest out-of-sample expectation
- **Expected alpha after costs:** about zero, with an uncertainty of at least ±10% per quarter.
- **Rising period:** roughly 40–60% of the basket's gain, minus 1–2% of costs. It loses to the basket and probably beats the 2x trend engine on drawdown.
- **Falling period:** a small loss of roughly 0 to -8% from failed breakouts. That beats the basket, and may lose to a long/short trend engine if the decline is orderly.
- **Sideways period:** a loss of about -3% to -10%.
- **Against random weights with the same turnover:** any advantage would come from the long bias and drift, not from skill I can demonstrate.
- **Status:** an unproven fallback, not a validated strategy.
