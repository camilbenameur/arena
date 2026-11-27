# Trial log written by the model (verbatim)

# Trial log — verdict: NO ROBUST EDGE FOUND

## Protocol actually followed

- Twelve candidate rules with mechanisms were written down before any backtest.
- **12 of the 15 allowed trials were used.** Every variant that touched the real data is listed below.
- Code mechanics and the causality check were debugged on synthetic random-walk data, so no trial was spent on bug fixes.
- All scoring used `sandbox_backtest.simulate`. A line-for-line replica, asserted to match it, was used only for monthly and per-ticker attribution.
- Time split: **selection window = July to August (372 bars); hold-out = September (180 bars)**.
  - Trials 1–11 were scored on the selection window only.
  - I froze a choice (trial 1) before opening September.
  - September was then opened once for all rules.
  - Trial 12 was run after the hold-out had been seen. It is disclosed as such and is not an independent confirmation.
- Diagnostics run on already-counted variants (not new rules): a time-shift placebo (200 circular shifts of the weight matrix) and a long-leg / short-leg decomposition, for trial 1 and trial 12.
- Basket in the bar simulator: selection +36.4%, September +15.9%, full period +59.1% (the reference simulator gives +61.2%).
- Statistical power: 92 days means the standard error of an annualised Sharpe is about 2. Nothing below a Sharpe of about 4 is distinguishable from zero.

## Candidates rejected on arithmetic, with no backtest and no trial used

- **Cross-sectional funding carry.** Longs pay for leverage and the receiver is paid for balance sheet.
  - Cross-sectional funding dispersion is about 0.5 bp per 4-hour bar.
  - Funding autocorrelation at one day is about 0.05, so the spread does not persist.
  - The persistent spread (ETH against LTC) is about 0.2 bp per bar, roughly 1.2% per quarter per unit notional, against 24 bp per rebalance and about 1% per bar of idiosyncratic volatility. Not viable.
- **BTC lead-lag on alts.** Would need to predict a 4-hour residual move of about 0.7% well enough to clear 24 bp on every round trip. Implausible, and turnover would exceed 100x.
- **Volatility-targeted long basket.** Pure beta; "merely long" is not a finding.

## Trials

Returns are net of costs and funding. "Alpha t" is the t-statistic of the daily return after removing beta to the basket.

| # | Idea | Economic rationale | Parameters | Sel. Jul–Aug | Hold-out Sep | Full period (return / max DD / turnover) | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | Slow time-series trend, long/short, volatility-scaled | Slow-moving capital and herding; slower than the reference engine so fewer round trips | EMA 20/80 bars, vol span 60, target 1% per bar | +11.2% (Jul -2.6, Aug +14.2), beta 0.53, alpha t -0.6 | **-3.6%**, DD -15.3% | +7.4% / -15.6% / 21.8x | Chosen before the hold-out; **failed the hold-out**. Placebo: 61% of time-shifted copies did at least as well. |
| 2 | Donchian breakout | Same trend mechanism; wide exit channel for low turnover | Entry 60 bars, exit 30 bars | +9.2% (Jul -2.7, Aug +12.2), beta 0.53, alpha t -0.7 | -4.2% | +5.2% / -15.0% / 10.7x | Beta only; fails the hold-out. Reject. |
| 3 | Cross-sectional momentum, neutral | Slow rotation of attention and flows between alts | 42-bar return, long top 2, short bottom 2, daily rebalance | +3.1%, alpha t +0.1; ETH alone contributes +7.3 | -2.3% | +0.7% / -6.2% / 29.9x | One-ticker result, zero alpha, costs 3.6%. Reject. |
| 4 | Cross-sectional 1-day reversal | Paid for supplying liquidity to idiosyncratic flow | 6-bar return, 2 against 2, daily rebalance | -10.9%, alpha t -3.8 | -4.0% | -14.5% / -16.3% / 71.1x | Costs 9.3%, and negative gross. Reject. The inverse would earn less than its costs. |
| 5 | Betting against beta | Leverage-constrained or lottery-seeking buyers overpay for high-beta alts | 120-bar beta, 3 against 3 at 1/beta, weekly rebalance | +2.3%, alpha t -0.2 | +3.5% | +7.4% / -5.6% / 3.3x | Positive in both parts but full-period alpha t is 0.6. A few static pair bets with large offsetting ticker contributions. The mechanism is weak on perps, where leverage is free. Not distinguishable from noise; not selected. |
| 6 | Long-only slow trend | Hold the risk premium only when the trend is up | As trial 1, longs only | +22.0%, beta 0.74, alpha t -0.5 | +5.4% | +28.8% / -8.4% / 12.2x | Return is beta in a rising market, below the basket. "Merely long". Reject as a finding. |
| 7 | Uncrowded trend | Trends where the crowd pays funding are fragile | Trial 1 plus an 18-bar mean funding filter (long only if below 0.5 bp per bar, short only if above 0) | +11.7%, alpha t -0.6 | -7.3% | +3.5% / -14.8% / 33.1x | Filter adds turnover and no value. Reject. |
| 8 | Liquidation-shock reversal | Forced sellers after a large down bar on a volume spike | Return below -2.5 sigma and volume above 2x median; long 1.5 for 6 bars | -0.9% | +7.1% | +6.1% / -2.8% / 9.0x | Failed selection; the whole gain is one month and a few clustered events. Choosing it would be hold-out snooping. Reject. |
| 9 | Residual reversal against BTC | Idiosyncratic alt flow mean-reverts | 120-bar beta, 18-bar residual z-score, enter at 2, exit at 0.5, BTC hedge | -3.9% | +0.1% | -3.8% / -6.1% / 10.2x | Reject. |
| 10 | Stability check of trial 1, faster | Same as trial 1 | EMA 15/60 | +13.7% (Jul -3.5, Aug +17.8), alpha t -0.4 | -4.1% | +9.2% / -14.3% / 23.0x | Same sign and pattern as trial 1. |
| 11 | Stability check of trial 1, slower | Same as trial 1 | EMA 30/120 | +5.9% (Jul -5.1, Aug +11.6), alpha t -1.3 | +4.0% | +10.6% / -11.5% / 12.9x | Same pattern; the September sign differs from the other two speeds. Speeds are statistically indistinguishable. |
| 12 | **Equal-weight ensemble of the three tested speeds (FROZEN)** | Same as trial 1; averaging avoids picking a speed and shrinks the position when the speeds disagree | EMA 15/60, 20/80, 30/120 averaged; vol span 60; target 1% per bar | +10.2% (Jul -3.5, Aug +14.2), beta 0.52, alpha t -0.8 | -0.7%, DD -12.1%, alpha t -0.8 | **+9.8% / -12.4% / 18.6x**, Sharpe 1.31, costs 2.25%, beta 0.48, alpha t -1.2 | **No robust edge.** Handed back as the most defensible simple rule. |

## Checks on the frozen rule (trial 12)

- **Time split:** selection +10.2%, hold-out -0.7%. Not confirmed.
- **Months:** July -3.5%, August +14.2%, September -0.3%. All the profit comes from one month.
- **Against the basket:** beta about 0.5; alpha is negative in both parts (about -14 bp per day, t = -1.2 over the full period). The rule made money because it was net long on average (+0.31) in a market that rose about 60%.
- **Legs:** the long leg returned +24.2% and the short leg -11.9%. Shorts were repeatedly whipsawed in pullbacks.
- **Placebo:** circularly time-shifting the same weights (identical turnover and exposure profile, timing destroyed) gave a mean of +14.6% and a median of +15.6%. About 60% of the 200 shifts did at least as well as the real rule's +9.8%. **The rule shows no timing skill on this sample.**
- **Per ticker (full-period contribution, percentage points):** BTC +0.5, ETH +3.5, SOL +3.9, XRP -4.1, LTC +2.3, LINK +4.4. Not concentrated in one ticker, but XRP is consistently negative.
- **Costs:** 18.6x turnover over three months, about 2.25% of equity or 0.75% per month. This is a certain drag against an unproven gross edge.
- **Parameter stability:** the three speeds give full-period returns of +9.2%, +7.4% and +10.6%. They agree in sign over the full period and in July and August, but not in September.
- **Causality:** recomputing on truncated data at 26 bar times gave a gap of exactly 0. There are no NaNs, weights stay within [-2, 2], and the rule runs when given only later rows (it stays flat for the first 60 bars).

## Why this rule is handed back anyway

Nothing passed, so the choice is the least-bad default rather than a discovery.

1. Time-series trend is the only tested family with substantial evidence outside this sample, and its payoff does not depend on market direction.
2. Averaging the three tested speeds avoids choosing a parameter on 92 days of data, and cuts position size when the speeds disagree.
3. Turnover and risk are moderate: about 0.8x gross and -12% drawdown, against -35.5% for the 2x trend engine.
4. I did not switch to the rules that happened to look good in September (trials 5 and 8). That would be selecting on the hold-out from 12 noisy trials.

## Known weaknesses

- No evidence of alpha: it failed the hold-out, the placebo, and the alpha test against the basket.
- The design period is a single rising regime, so short-side behaviour in a real downtrend is untested.
- It loses in choppy or range-bound markets and in sharp V-shaped reversals.
- Trial 12 was specified after the hold-out had been seen.
- Partial ensemble positions for high-volatility names sit near the 0.3-weight re-trade band, so the minute-level simulator may execute slightly differently from the bar-level one.

## Honest out-of-sample expectation

- Expected alpha is about zero before costs, less a cost drag of roughly 0.5–1% per month.
- Realised quarterly return is plausibly anywhere in ±15%, driven by regime:
  - a moderately positive result if the unseen period has a persistent trend in either direction;
  - a loss of a few percent per month in chop.
- It will probably lag the basket if the market keeps rising and beat it if the market falls.
- Against the 2x trend engine it should be less extreme in both directions, with roughly a third of the drawdown.
- I do not expect it to beat random weights of equal turnover reliably.
