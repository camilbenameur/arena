# Trial log written by the model (verbatim)

# Verdict: NO ROBUST EDGE FOUND

None of the 11 variants I tested met the criteria I set before looking at results: positive after costs in both halves, not driven by one ticker or month, and stable under parameter changes. The frozen rule is the most defensible simple fallback, not a finding. Its design-period profit is mostly long beta in a rising market, and it earned less than half of what the basket did.

All numbers come from `sandbox_backtest.simulate` on the design CSV, which is a bar-level approximation of the final judge. I used 11 of the 15 allowed trials; every variant I scored is listed.

## Pre-registered candidates

These were written down before any result was computed. "Vol-sized" means weight = 1% per-bar volatility target divided by trailing volatility (90-bar EWM), capped at 2. "Daily" means the target is refreshed only at the 20:00 bar and held in between.

## Trial log

The split is at the midpoint bar: H1 = first 276 bars (1 Jul to mid-Aug), H2 = the rest. H1, H2 and monthly figures are the rule run with weights zeroed outside that window.

| # | Idea | Economic rationale | Parameters | Return | Max DD | Sharpe | Turnover | Cost | H1 / H2 | Jul / Aug / Sep | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | C1 time-series momentum, long/short | Under-reaction and slow flows; hedgers and profit-takers on the other side | sign of 42-bar return, vol-sized | +8.2% | -14.9% | 1.09 | 86x | 10.4% | -7.5 / +16.4 | -5.3 / +13.9 / -0.3 | FAIL: H1 negative, all profit from August, costs exceed the net result |
| 2 | C2 cross-sectional momentum, neutral | Attention and flow chasing among alts | 42-bar return, long top 2 / short bottom 2, daily | -0.2% | -5.2% | -0.01 | 33x | 4.0% | +0.5 / -0.9 | -0.4 / -0.4 / +0.2 | FAIL: zero after costs; per-ticker results are ETH +8.2 against XRP -6.3, i.e. noise |
| 3 | C3 cross-sectional funding carry, neutral | Leveraged longs pay for balance sheet; receive funding for the other side | 18-bar mean funding, long lowest 2 / short highest 2, daily | -13.9% | -14.2% | -5.33 | 43x | 5.1% | -6.3 / -7.9 | -4.6 / -8.0 / -2.2 | FAIL: negative in every month. The carry itself is tiny (each contract's funding sums to 0.6–1.8% over the quarter), so price moves dominate |
| 4 | C4 long-only trend filter | Crypto risk premium plus crash avoidance | close > 60-bar EMA, else flat, vol-sized | +23.4% | -12.3% | 2.23 | 48x | 5.8% | -8.3 / +34.4 | -5.2 / +21.7 / +6.7 | NOT A FINDING: beta. Below the basket (+61%), and negative in H1 |
| 5 | C5 cross-sectional 1-day reversal, neutral | Liquidity provision to overreacting flow | 6-bar return, long bottom 2 / short top 2, daily | -14.0% | -15.5% | -6.48 | 75x | 9.0% | -9.5 / -5.2 | -5.2 / -6.4 / -3.5 | FAIL: loses before costs too |
| 6 | C6 Donchian breakout, long/short | Stop and liquidation cascades | 60-bar entry, 30-bar exit, vol-sized | -0.7% | -17.2% | 0.11 | 19x | 2.3% | -6.6 / +5.7 | -6.0 / +14.1 / -7.9 | FAIL: one good month out of three |
| 7 | C7 long unless funding is crowded | Crowded leveraged longs precede flushes | flat when z-score of 18-bar funding vs trailing 180 bars > 1, vol-sized | +32.8% | -8.5% | 3.47 | 26x | 3.1% | +1.1 / +31.1 | +0.1 / +23.3 / +6.8 | NOT A FINDING: long 77% of the time, yet earns less than the basket with a lower Sharpe (3.47 vs 4.05). The filter shows no timing value |
| 8 | C8 BTC lead-lag into alts | Information diffuses from BTC to alts | alts = sign of BTC 6-bar return, daily | -7.2% | -21.7% | -0.41 | 81x | 9.7% | -9.9 / +2.7 | -2.7 / +5.6 / -10.0 | FAIL: costs exceed any effect |
| 9 | C4 stability check, faster | as trial 4 | EMA 30 | +17.7% | -11.4% | 1.77 | 66x | 7.9% | -9.4 / +29.9 | -8.7 / +24.2 / +3.8 | Same shape as trial 4; more whipsaw cost |
| 10 | C4 stability check, slower | as trial 4 | EMA 120 | +27.7% | -11.5% | 2.59 | 28x | 3.4% | -8.4 / +39.2 | -6.2 / +22.9 / +10.6 | Same shape as trial 4; H1 still negative |
| 11 | C4 with hysteresis to cut costs | as trial 4; the band is set at half a daily sigma so noise around the EMA does not trigger trades | EMA 60, band ±0.5 daily sigma, vol-sized | +27.0% | -8.8% | 2.56 | 16x | 1.9% | -3.6 / +31.6 | -4.4 / +25.7 / +5.3 | CHOSEN as fallback, labelled "no robust edge found" |

C9 (a blend of passing candidates) was never run because nothing passed. Four trials were left unused on purpose.

## What the trials say

- **Market-neutral ideas:** all three (trials 2, 3, 5) were zero or negative after costs.
- **Trend ideas:** every one (trials 1, 4, 6, 9, 10, 11) lost in July and in H1, and made its money in August. That is the same pattern as the reference trend engine, so it is one regime outcome, not six confirmations.
- **Long-biased rules:** trials 4, 7, 9, 10 and 11 are positive only because the market rose. Each earned less than the basket's +61.2% and had a lower Sharpe than its 4.05.
- **Sign flips I did not chase:** trials 3 and 5 lost consistently, which hints that the opposite positions (long high funding, 1-day cross-sectional momentum) made money before costs. My rough estimate for the flipped funding rule is +3–4% net over the quarter; the flipped reversal would be negative after costs. I did not run either: a sign flip chosen after seeing the result has no pre-registered mechanism and is how overfitting happens.

## Time split

I did not select on H1 and confirm on H2; I saw both halves for each trial at the same time. I used the split as a pass/fail consistency test. No rule passed it convincingly: trial 7 is the only one positive in both halves, and its H1 is +1.1%.

## Chosen rule and why

Trial 11: per contract, go long when the close is more than 0.5 daily sigma above its 60-bar EMA, go flat when it is more than 0.5 daily sigma below, otherwise hold the previous state. Size is 1% per-bar volatility target over trailing volatility, capped at 2. It is never short.

- **Not picked for performance.** Trial 7 had a higher return and Sharpe. I chose trial 11 because its behaviour in a regime I have not seen is bounded by construction: it is flat in sustained declines.
- **Parameters from economics, not search.** The 60-bar EMA was fixed before any result; 30 and 120 give the same picture (+17.7% and +27.7%). The band was a single pre-reasoned choice and was not tuned; I ran no other band width.
- **Lowest cost drag of the trend variants.** Turnover is 16x, about 1.9% of equity per quarter in costs. There were 5–8 entries per ticker over three months.
- **Not concentrated.** Five of the six tickers contribute between +2.7% and +7.5%; XRP adds +1.2%.
- **Mechanical checks.** The frozen file reproduces the trial-11 weights exactly. Recomputing on truncated data matched row for row at 80 truncation points. Shuffled input rows give the same output, and there are no NaNs.

## Known weaknesses

- **It is mostly beta.** It was long 44–72% of the time depending on the ticker and captured under half of the basket's return. I found no evidence of timing skill.
- **Choppy markets cost money.** H1 was -3.6% and July -4.4%, while the basket made +10.3% in July.
- **The crash-protection argument is untested.** The design period contains no sustained decline, so the reason for preferring this over plain long rests on a prior, not on this data.
- **Sizing can lever up.** In calm markets the weight reaches the cap of 2 (it did for BTC), so a gap down from a quiet period hits at above-average size.
- **Low power.** Three months, one regime, six highly correlated contracts.
- **Simulator gap.** The bar-level simulator fills at the bar close; the minute-level judge will differ somewhat.

## Honest out-of-sample expectation

- **Expected edge after costs:** about zero, with wide uncertainty.
- **If the market keeps rising:** roughly 40–50% of the basket's return. It will underperform the basket and should beat random weights only through its long bias.
- **If the market is range-bound:** a loss of about 1–2% of equity per month from whipsaws, as in July (-4.4%).
- **If the market falls steadily:** a loss on the first leg down of a few percent, then mostly flat. It should do better than the basket and could do worse than a trend engine that is allowed to short.
- **Against the 2x trend engine:** I expect a smaller drawdown (-8.8% here vs -35.5%), not a reliably higher return.
