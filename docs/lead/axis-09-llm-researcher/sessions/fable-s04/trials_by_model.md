# Trial log written by the model (verbatim)

# Trial log — verdict: NO ROBUST EDGE FOUND

## Protocol

- **Pre-registration:** 11 candidates were written down with a mechanism before any backtest.
- **Trials:** 12 of the 15 allowed were run. Every `simulate` call on a candidate rule is listed below; there were no unlogged variants.
- **Parameters:** all were fixed from the economics before each run. The only parameter variations are T8 and T9, which are stability checks of T5.
- **Scoring:** every trial used `sandbox_backtest.simulate` on the full design file. Split, monthly and per-ticker figures come from the equity curve of that same run, using a copy of the simulator loop that also tracks attribution.
- **Time split:** H1 = 1 Jul to 15 Aug, H2 = 16 Aug to 30 Sep.
- **Other runs that are not trials:**
  - One descriptive pass before any backtest (total returns, volatility, funding levels, correlations), used to judge cost feasibility.
  - One identity and causality check of the frozen file. Its weights are bit-identical to T5, so its `simulate` output repeats T5.
- **Causality:** the frozen rule was recomputed on data truncated at 184 different bars, with zero mismatches. It is also invariant to row order.

Descriptive facts that shaped the cost reasoning:

- Funding averages 0.1–0.3 bp per 4h bar (2–7% a year).
- The cross-sectional spread in 7-day mean funding is about 0.4 bp per bar, roughly 8% a year on a long/short pair. That is small next to 24 bp per round trip and bar volatility of 0.75–1.35%.
- Pairwise correlations are 0.5–0.85, so the six contracts are close to a single bet.

## Trials

"Daily" means the decision is refreshed once a day at the 00:00 UTC close. "Vol-scaled" means weight = 1% / 60-bar volatility, capped at 2.

| # | Idea | Economic rationale | Parameters | Return | Max DD | Sharpe | Turnover | Cost | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| T1 | Slow time-series momentum, long/short | Under-reaction and herding; other side is profit-takers and hedgers | sign of 60-bar (10-day) return, vol-scaled, daily | −19.0% | −26.7% | −1.92 | 34x | 4.1% | FAIL. Loses in July and September; shorts into a rising, choppy market |
| T2 | Cross-sectional momentum, market-neutral | Slow rotation of capital between coins | 42-bar (7-day) return, long top 2 / short bottom 2, daily | +0.7% | −6.2% | 0.33 | 30x | 3.6% | FAIL. Gross about +4%, eaten by costs; t ≈ 0.2; ETH +6.7 and XRP −7.3 offset |
| T3 | Cross-sectional 1-day reversal | Liquidity provision after forced flows | 6-bar return, long bottom 2 / short top 2, daily | −14.5% | −16.3% | −6.34 | 71x | 8.5% | FAIL. Negative in all three months. Gross is about −6%, so the mirror image (untested) would gross about +6% against about 8.5% of costs |
| T4 | Cross-sectional funding carry | Levered longs pay for leverage; collect it | 42-bar mean funding, long lowest 2 / short highest 2, daily | −6.7% | −10.7% | −2.57 | 17x | 2.0% | FAIL. Funding collected was only +0.2%; price moves went against it (high-funding coins kept rising) |
| T5 | Trend-filtered long, per coin | Risk premium is earned in up-trends; filter cuts the left tail | long 1.0 if close > 120-bar SMA, else 0, daily | +25.4% | −9.4% | 2.42 | 8.4x | 1.0% | NOT AN EDGE. Return is beta; see below. Chosen as fallback |
| T6 | Donchian breakout, long/short | Stop and liquidation clustering beyond range extremes | enter on 60-bar extreme, exit on 30-bar opposite extreme, vol-scaled | −1.5% | −19.6% | 0.03 | 21x | 2.5% | FAIL. August +15% is cancelled by July and September |
| T7 | Market-level trend filter | One regime signal for six correlated coins | all six long when equal-weight index > its 120-bar SMA, daily | +18.3% | −15.6% | 1.73 | 15.5x | 1.9% | Worse than per-coin T5; double the turnover |
| T8 | T5 stability, shorter | as T5 | lookback 90 | +17.9% | −12.5% | 1.82 | 13.1x | 1.6% | Same sign and shape; more whipsaw |
| T9 | T5 stability, longer | as T5 | lookback 180 | +30.5% | −9.9% | 2.76 | 6.6x | 0.8% | Same shape. Better only because it is closer to buy-and-hold; not selected |
| T10 | Funding-crowding timing on the long basket | Extreme funding means crowded longs and cascade risk | flat when 18-bar basket funding > trailing 180-bar 90th percentile, daily | +34.6% | −9.8% | 3.21 | 5.3x | 0.6% | FAIL as timing. Out about 10% of the time and gave up about 27 points against the 1x basket |
| T11 | Low-volatility cross-section | Lottery demand overprices high-vol alts | long 2 lowest / short 2 highest 60-bar vol, vol-scaled, daily | 0.0% | −5.7% | −0.01 | 13.6x | 1.6% | FAIL. H1 −5.4%, H2 +5.7%; effectively a static BTC-versus-alts bet |
| T12 | Volume-confirmed momentum | High-volume moves carry informed flow | sign of 60-bar volume-weighted return, vol-scaled, daily | −11.3% | −19.2% | −1.17 | 25x | 3.0% | FAIL. Same pattern as T1 |

Pre-registered but not run (not counted as trials):

- **BTC lead–lag at one bar.** Dismissed on arithmetic: a 4-hour hold must clear 24 bp per round trip against about 0.6% residual volatility, which needs an implausible hit rate.
- **Momentum plus carry composite.** Both components failed on their own (T2, T4), so combining them would be mining.
- Three trials were left unused on purpose.

## Time split and months (same runs)

| # | H1 return | H2 return | H1 Sharpe | H2 Sharpe | Jul | Aug | Sep | t-stat of daily returns |
|---|---|---|---|---|---|---|---|---|
| T1 | −15.0% | −4.8% | −5.4 | −0.6 | −13.3 | +11.5 | −16.3 | −0.95 |
| T2 | +0.8% | −0.1% | 1.3 | −0.2 | +0.1 | +3.0 | −2.3 | 0.16 |
| T3 | −7.8% | −7.2% | −10.1 | −4.7 | −4.9 | −6.3 | −4.0 | −3.15 |
| T4 | −4.5% | −2.3% | −8.5 | −1.2 | −3.6 | −7.0 | +4.1 | −1.28 |
| T5 (chosen) | −4.0% | +30.6% | −2.5 | 4.0 | −4.0 | +22.3 | +6.8 | 1.20 |
| T6 | −6.3% | +5.1% | −3.7 | 1.0 | −5.4 | +15.4 | −9.8 | 0.01 |
| T7 | −5.9% | +25.7% | −3.6 | 3.3 | −3.9 | +23.5 | −0.4 | 0.86 |
| T8 | −4.5% | +23.5% | −2.3 | 3.3 | −5.1 | +22.3 | +1.6 | 0.90 |
| T9 | −2.2% | +33.5% | −2.4 | 4.2 | −2.1 | +21.6 | +9.6 | 1.37 |
| T10 | −1.5% | +36.7% | −0.3 | 5.2 | −2.1 | +17.9 | +16.7 | 1.59 |
| T11 | −5.4% | +5.7% | −5.6 | 5.3 | −2.3 | −0.5 | +2.8 | −0.01 |
| T12 | −9.5% | −2.0% | −3.9 | −0.2 | −11.4 | +12.7 | −11.2 | −0.58 |

No rule is positive in both halves. Every rule with a positive total is long-biased and earns it in H2, which is the August rally.

## What the design data say

- No long/short or market-neutral rule made money after costs. The best is T2 at +0.7% with t ≈ 0.2, which is noise.
- Trend timing at 7–30 day horizons subtracted value in this sample.
  - T5 held an average net exposure of 0.53x and returned +25.4%.
  - A static 0.53x basket would have returned roughly +30% (my approximation from the reference basket's monthly returns, not a simulated run).
  - So the filter's timing contribution is about −5 points, of which 1.0 is fees.
  - Part of that gap is the 20-day warm-up, during which T5 is flat.
- Funding was not a usable contrarian signal here, in the cross-section (T4) or as a crowding timer (T10). I deliberately did not flip the signs: a post-hoc "long high funding" rule with |t| ≈ 1.3 would be data mining.
- With about 92 daily observations, even a true Sharpe of 2 gives t ≈ 1. Nothing here could have been confirmed, only rejected.

## Chosen rule: T5, exactly as pre-registered

Per coin, hold +1.0 (equity/6, unlevered) when close is above its 20-day SMA (120 bars), otherwise flat. The decision is refreshed once a day at the 00:00 UTC close. There is one economic parameter (20 days), one execution choice (daily refresh) and no fitted values.

Why this one, given that nothing showed an edge:

- **Lowest cost drag of the pre-registered rules.** Turnover is 8.4x per quarter, about 1% in fees, across 48 trades. If its timing edge is zero, it costs little.
- **Its protection is mechanical, not statistical.** In a sustained decline it sits flat, so the left tail is cut whether or not momentum "works".
- **It is stable to the parameter.** Lookbacks of 90, 120 and 180 give +17.9%, +25.4% and +30.5%, with the same monthly shape. I kept 120 because it was set in advance; 180 looks better only because it is closer to buy-and-hold.
- **It is not concentrated.** Every ticker contributes positively (BTC +2.6, ETH +3.0, SOL +5.5, XRP +2.9, LTC +5.3, LINK +7.0 points). The concentration is in time: August is +22.3% of the +25.4%.
- **It cannot be short or levered.** Maximum gross is 1x equity.

## Known weaknesses

- **The design return is beta, not skill.** It should not be read as evidence the rule works. The t-stat of daily returns is 1.2, and that is on a long-biased rule in a market that rose 61%.
- **Whipsaw in choppy markets.** July was −4.0% and H1 was −4.0%; the first 20 days of that are warm-up, so the loss came from the last third of July.
- **Late on both sides.** It enters after a rise and exits after a fall. It decides once a day and carries the gap risk in between.
- **Effectively one bet.** The six coins are 0.5–0.85 correlated.
- **Warm-up.** If the unseen period is supplied without the design history, the rule is flat for the first 20 days. I left this alone rather than add an untested variant.
- **Bar grid assumption.** The daily refresh assumes bars open at 00/04/…/20 UTC. On a different grid the rule would stay flat.
- **Simulator gap.** The bar-level simulator fills at the close; the real one fills at the next minute's open. At 8x turnover the difference should be small.

## Honest out-of-sample expectation

- **Timing alpha after costs:** about zero. Plausible range is −5 to +5 points per quarter, with about −1 point of certain fee drag.
- **Sustained up-trend:** roughly 40–60% of the basket's gain. It will lag the basket.
- **Sustained decline:** a single-digit loss, then flat. It should beat the basket. It will lag a short-capable trend engine if that engine catches the move.
- **Sideways, choppy market:** roughly −4% to −10% per quarter from whipsaws.
- **Against random weights at the same turnover:** no claim beyond the long bias. If the unseen period falls or chops, this rule can lose to them.
- **Bottom line:** I found nothing in this three-month sample that I would expect to keep working net of 24 bp per round trip. This rule is a conservative default, not a discovery.
