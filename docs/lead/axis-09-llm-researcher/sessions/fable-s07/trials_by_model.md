# Trial log written by the model (verbatim)

# Trial log — verdict: NO ROBUST EDGE FOUND

## Protocol

- Nine candidate mechanisms were written down before any result was computed (C1–C9 below).
- Every evaluation went through one harness that calls `sandbox_backtest.simulate` and appends to a log file. **12 trials were run in total (limit 15); all are listed here.** Three were left unused on purpose, because further variants after seeing these results would have been data mining.
- The only looks at the data outside trials were:
  - descriptive statistics (volatility, funding level and autocorrelation, volume spikes) used to set scales;
  - one event-level breakdown of trial T5, with no new variant.
- Time split: H1 = 1 Jul – 15 Aug, H2 = 16 Aug – 30 Sep. All figures are net of 12 bp per side and funding.
- "Alpha" is the design-period return left after removing beta to the equal-weight basket (daily regression). Because the basket made +61%, raw return on any long-biased rule is mostly beta.

## Pre-registered candidates

| # | Mechanism | Who is on the other side |
|---|---|---|
| C1 | Cross-sectional funding carry | Leveraged longs paying for balance sheet |
| C2 | Slow breakout trend, long/short | Under-reaction, stop and liquidation herding |
| C3 | Cross-sectional momentum, 7 days | Slow rotation of attention and capital |
| C4 | Cross-sectional reversal, 3 days | Impatient or forced flow paying for liquidity |
| C5 | BTC lead-lag into alts | Slower price discovery in alts |
| C6 | Capitulation rebound | Forced liquidations paying for immediacy |
| C7 | Per-coin funding crowding timer | Crowded leveraged longs or shorts |
| C8 | Low-volatility tilt | Lottery demand for high-vol alts |
| C9 | Long/flat trend, vol-scaled | Risk premium plus trend filter (beta, the fallback) |

## Trials

All parameters were set a priori from the economics; none was searched.

| # | Idea | Parameters | Return | Max DD | Sharpe | Turnover | H1 / H2 | Jul / Aug / Sep | Cost | Beta | Alpha (t) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 | C1 funding carry, neutral | 7-day mean funding, rank weights, daily rebalance | -7.5% | -10.5% | -3.52 | 17.6x | -4.0 / -3.7 | -3.0 / -7.4 / +2.9 | 2.2% | -0.03 | -6.4% (-1.5) | Fail |
| T2 | C2 Donchian long/short | Enter on 60-bar extreme, exit on 30-bar, 50% vol target | -6.6% | -21.4% | -0.53 | 23.7x | -8.0 / +1.5 | -7.1 / +14.2 / -11.9 | 3.0% | 0.31 | -21.2% (-1.4) | Fail |
| T3 | C3 cross-sectional momentum | 42-bar return, rank weights, daily | +0.4% | -5.5% | 0.25 | 26.0x | +1.2 / -0.7 | +0.4 / +2.8 / -2.6 | 3.1% | 0.08 | -3.5% (-0.8) | Fail |
| T4 | C4 cross-sectional reversal | 18-bar return, rank weights, daily | -6.8% | -8.4% | -3.55 | 41.1x | -3.8 / -3.2 | -1.2 / -4.0 / -1.8 | 5.1% | -0.05 | -4.7% (-1.2) | Fail |
| T5 | C6 capitulation rebound | Bar return < -2 sd, volume > 2x median (42-bar trailing), hold 12 bars, size 1.5 | +11.9% | -3.8% | 2.90 | 18.8x | +0.7 / +11.1 | -1.8 / +3.3 / +10.3 | 2.2% | 0.10 | +6.6% (0.8) | Not robust |
| T6 | C7 funding timer on long basket | 3-day funding: below 0 → weight 2, above 1 bp per bar → 0, else 1 | +51.9% | -13.5% | 3.29 | 26.6x | +1.1 / +50.4 | -1.4 / +35.0 / +14.2 | 2.8% | 1.16 | -13.0% (-1.7) | Fail |
| T7 | C8 low-vol tilt, neutral | 14-day vol, long 3 lowest and short 3 highest, inverse-vol | -2.6% | -6.5% | -0.97 | 9.3x | -4.3 / +1.7 | -0.5 / -1.6 / -0.6 | 1.1% | 0.01 | -3.1% (-0.5) | Fail |
| T8 | C9 long/flat trend | Close above 60-bar SMA, 50% vol target | +23.0% | -12.6% | 2.11 | 48.8x | -8.2 / +34.0 | -6.2 / +23.8 / +6.0 | 5.8% | 0.77 | -16.4% (-1.6) | Fail |
| T9 | C5 BTC lead-lag | BTC bar beyond 1.5 sd → alts in same direction for 3 bars | +0.1% | -11.1% | 0.14 | 66.3x | -6.0 / +6.5 | -2.2 / -2.8 / +5.2 | 8.2% | 0.09 | -3.9% (-0.5) | Fail |
| T10 | T5 perturbation | z = 2.5 | +12.6% | -2.6% | 3.70 | 14.0x | +1.4 / +11.0 | -0.7 / +2.4 / +10.7 | 1.7% | 0.06 | +9.3% (1.3) | Same September dependence |
| T11 | T5 perturbation | hold = 6 bars | +4.0% | -4.0% | 1.17 | 18.8x | -1.8 / +5.9 | -2.1 / -0.6 / +6.9 | 2.3% | 0.08 | +0.2% (0.0) | Unstable |
| T12 | T5 de-risked (**frozen rule**) | size = 1.0, otherwise as T5 | +7.9% | -2.6% | 2.91 | 12.5x | +0.5 / +7.3 | -1.2 / +2.2 / +6.8 | 1.5% | 0.07 | +4.4% (0.8) | Fallback, no robust edge |

Notes on individual failures:

- **T1:** funding dispersion is only about 1% per quarter and has no persistence at 7 days, so price noise dominates the carry.
- **T2:** whipsawed in July and September.
- **T3:** about +3.5% before costs, all of it eaten by costs.
- **T4:** negative even before costs.
- **T6 and T8:** the positive returns are pure beta; the timing itself subtracted value.
- **T7:** this is effectively a short-alts bet, and it lost in an alt rally.
- **T9:** about +8% before costs, about 0 after; too fast for 24 bp.

Taken together the failures describe one regime: a broad alt-led rally in which winners, high-funding coins and high-vol coins kept going, and nothing systematic was paid beyond beta.

## Why the capitulation rule (T5/T10/T11/T12) is not a finding

It is the only family with positive net return and a positive alpha estimate, and it fails my own checks.

- **Event study (T5 triggers).** There were 44 triggers on 27 distinct bars. The mean 12-bar forward return after a trigger is +1.3%, against +1.1% for all 12-bar windows in this period; the median is +0.6%. The triggers therefore earned about the market drift, not a premium.
- **One event.** On 23 Sep, five coins triggered at once; LTC then rose 18% and LINK 13.6% in two days. That single date supplies roughly three quarters of the P&L.
- **Two tickers.** LTC and LINK account for 8.6 of the 8.8 percentage points of gross P&L in T12.
- **Time split.** H1 is +0.5%, H2 is +7.3%; July is negative. The first half shows nothing.
- **Parameter stability.** Raising z to 2.5 changes little (+12.6%), but halving the hold to 6 bars cuts the return to +4.0% with alpha at zero and H1 negative. The sign survives; the size does not.
- **Significance.** The alpha t-statistic is about 0.8 on 92 days, after 12 trials. That is statistically indistinguishable from zero.

## Chosen rule and why

**Capitulation rebound, long only (T12).** After a 4-hour bar closes down more than 2 trailing standard deviations on more than 2x trailing median volume, hold that contract long at weight 1.0 for 12 bars, otherwise stay flat.

It is handed back as the most defensible simple rule, not as a discovery:

- It was pre-registered with a clear counterparty (forced liquidations).
- It has four parameters, all set before testing and none tuned.
- It is in the market on only 42% of bars, with average exposure of about 14% of equity.
- It has the lowest cost of the non-failing candidates (12.5x turnover, about 1.5% per quarter).
- It was not negative in either half of the design period.
- Size was cut from 1.5 to 1.0 purely for risk: if all six contracts fire together, gross exposure is 1x equity, never levered.
- Causality was verified by recomputing on truncated data at 75 bar times, with zero mismatches. Output has no NaN, values are 0 or 1, and warm-up is 43 bars.

## Known weaknesses

- **Long only.** Its positive design result is partly beta in a +61% market.
- **Falling markets.** In a sustained decline it buys every cascade and holds for two days; expect a string of small losses, and a loss of several percent of equity if a market-wide crash continues after all six trigger.
- **Late entry.** It enters at the close of the crash bar, up to four hours after the liquidation; much of any true rebound may already be gone.
- **Lumpy results.** Design-period P&L is one date and two tickers.
- **Simulator.** The bar-level simulator is only an approximation of the minute-level judge.

## Honest out-of-sample expectation

- **Alpha after costs:** about 0, with a plausible range of roughly -3% to +3% per quarter.
- **Total return:** roughly 0.1–0.15 times the basket's return, minus about 1.5% per quarter in costs. That means low single digits positive in a rising market, flat to about -5% in a choppy or falling one.
- **Drawdown:** likely a few percent, larger than the -2.6% seen in the design period.
- **Against the basket:** it will lag in an up market and should lose much less in a down market, simply because it is mostly flat.
- **Against the 2x trend engine:** the outcome will be driven by the trend engine's own large variance, not by skill here.
- **Against random weights of equal turnover:** I do not expect it to be reliably distinguishable.
