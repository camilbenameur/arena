# Trial log written by the model (verbatim)

# Trial log — verdict: NO ROBUST EDGE FOUND

## Protocol

- **Pre-registration:** 12 candidate rules with mechanisms were written down before any result was computed.
- **Trials used:** 11 of 15. Every variant was run through one harness that appends to a log file, so the count is mechanical. I stopped early on purpose.
- **Scoring:** every trial was scored with `sandbox_backtest.simulate`. As a sanity check, the 1x basket scores +59.1% in the sandbox against +61.2% in the reference.
- **Time split:** selection on July–August, confirmation on September. Each month was also simulated separately, starting flat.
- **Pass criteria, fixed before testing:** positive after costs in both selection and confirmation; no single ticker or month carrying the result; parameter neighbours (about ±33% on lookback) agreeing.
- **Descriptive facts looked at before trials (not trials):**
  - Volatility per 4-hour bar is 0.75% (BTC) to 1.35% (XRP).
  - Funding averages about 0.1–0.3 bp per bar, or 2–7% a year, so carry income is negligible next to 24 bp round-trip costs.
  - Pairwise return correlations are 0.5–0.85.
- **Not counted as a trial:** one re-run of the frozen file to confirm it reproduces trial 3 exactly (maximum weight difference 0.0).

## Trials

Market-neutral rules hold the top two and bottom two contracts at ±1.5 weight. Returns are after costs and funding.

| # | Idea | Economic rationale | Parameters | Full design: return / max drawdown / Sharpe / turnover | Jul / Aug / Sep | Jul–Aug (selection) | Sep (confirmation) | Verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | Cross-sectional funding carry (short top-2 funding, long bottom-2) | Leveraged longs pay for balance sheet; the receiver is paid to take the other side | 42-bar mean funding, daily rebalance | −8.9% / −15.3% / −2.32 / 26x | −4.5 / −10.1 / +5.5 | −13.9% | +5.5% | FAIL. Sign flips between split halves; funding is too small to matter. PnL is ETH/SOL against LINK |
| 2 | Cross-sectional momentum, 7-day | Slow capital rotation between majors and alts | 42-bar return, daily rebalance | −0.1% / −9.6% / 0.06 / 43x | +1.0 / +1.5 / −2.5 | +2.6% | −2.5% | FAIL. Zero after costs; one ticker (XRP, −14.7%) dominates |
| 3 | Slow time-series trend, long/short, inverse-vol sized | Under-reaction and liquidation cascades; slow, so few round trips | EMA 18/90, 1% vol reference | +8.5% / −15.3% / 1.09 / 20x | −3.6 / +15.4 / −2.7 | +11.0% (Sharpe 1.74) | −2.7% (Sharpe −0.82) | NOT CONFIRMED. All profit is August; average net long 0.30 in a +59% market |
| 4 | Basket long/flat above its 10-day average | Earn the risk premium, step aside in drawdowns | SMA 60 on the equal-weight index | +16.6% / −14.7% / 1.67 / 38x | −6.9 / +14.7 / +9.3 | +6.7% | +9.3% | FAIL as a finding. It is diluted beta: average exposure 0.58 earned 16.6%, where 0.58 × basket would be about 34%, so the timing was negative |
| 5 | 1-bar cross-sectional reversal (pre-registered as no. 7) | Liquidity provision to forced flow | Rebalance every bar | −56.5% / −56.6% / −20.8 / 500x | −23.4 / −26.5 / −22.8 | −43.7% | −22.8% | FAIL. Costs destroy it, as expected |
| 6 | BTC lead-lag: alts follow a large BTC bar (no. 8) | Attention and liquidity delay | BTC move above 1%, hold alts one bar at ±1.5 | −10.6% / −14.0% / −1.67 / 127x | −12.9 / +1.6 / +1.0 | −11.5% | +1.0% | FAIL. Follow-through is below 24 bp |
| 7 | Volume-confirmed breakout (no. 10) | Informed flow and stop cascades | 30-bar channel, 15-bar exit, volume above 1.5x average | +9.8% / −23.4% / 0.93 / 24x | −6.7 / +32.6 / −10.9 | +23.4% | −10.9% | FAIL. Best in selection, worst trend rule in confirmation: one-month luck |
| 8 | Momentum plus carry rank combination (no. 11) | Avoid paying carry against crowded trends | 42 bars, daily rebalance | −0.6% / −11.4% / 0.03 / 43x | −0.4 / −6.7 / +6.5 | −6.9% | +6.5% | FAIL. Unstable sign; driven by LINK (+15.9%) |
| 9 | Trial 3 robustness, faster | Same as 3 | EMA 12/60 | +7.7% / −15.7% / 1.04 / 26x | −3.7 / +19.0 / −6.1 | +14.2% | −6.1% | Same shape as 3; not confirmed |
| 10 | Trial 3 robustness, slower | Same as 3 | EMA 24/120 | +14.9% / −8.9% / 1.76 / 13x | −3.8 / +14.2 / +4.5 | +9.7% | +4.5% | Best in sample, but one favourable draw out of three neighbours; not treated as confirmation |
| 11 | Donchian breakout without the volume filter, slower | Same as 3 and 7, with hysteresis for lower turnover | 60-bar entry, 30-bar exit | +8.0% / −23.6% / 0.82 / 15x | −3.3 / +22.9 / −9.7 | +18.7% | −9.7% | FAIL in confirmation |

**Pre-registered but not run:**
- Volatility-managed basket: pure beta, and a long-only rule is not a finding.
- Funding-crowding timing: funding is too small, and trial 1 showed no stable link between funding and returns.
- Multi-day residual reversal: it is the mirror image of trial 2, so about zero gross and negative after costs.
- Alt/BTC ratio trend: near-duplicate of trial 2.

I preferred to leave four trials unused than to spend them on these.

## What the split says

- **Market-neutral ideas (1, 2, 8):** about zero or negative, with the sign flipping between July–August and September and results driven by single tickers. There is no evidence of a cross-sectional edge.
- **Fast ideas (5, 6):** killed by the 24 bp round trip.
- **Trend family (3, 7, 9, 10, 11):** every member lost in July (−3% to −7%), won in August (+14% to +33%) and was mixed in September (−11% to +4.5%). This is the same profile as the reference trend engine (−13 / +19 / +2).
- **Trend is not alpha here:** the trend rules were on average 0.2–0.4 net long in a market that rose about 60%. Their +8% to +15% is no more than that average long exposure would have earned passively. The result is "long-ish in the one strong month".
- **Selection would have misled:** the July–August winner (trial 7, +23%) was the worst trend rule in September (−11%). That is what picking by in-sample performance does on this sample.

## Chosen rule and why

I froze **trial 3: EMA(18) vs EMA(90) on 4-hour closes, long/short per contract, weight = sign × min(2, 1% / EWM bar volatility), flat for the first 90 bars.** It is labelled "no robust edge found".

- **Why this one:** it is the pre-registered centre parameter set, not the in-sample best. Trial 10 (24/120) scored better, but choosing it after the fact would be selection on noise.
- **Parameter stability:** both neighbours (12/60 and 24/120) are positive on the full period (+7.7% and +14.9%) with the same monthly shape. Profit is spread over SOL, LTC and LINK (+3% to +5% each); XRP is negative (−2.4%) and BTC and ETH are about zero.
- **Mechanism:** time-series trend has the most outside support of anything tested, and it does not depend on the market going up.
- **Costs:** about 20x turnover over three months, roughly 2.4% of equity. There are 6–11 sign flips per ticker in the period.
- **Mechanical checks:** the rule was recomputed on data truncated at 80 different bars with zero gap. It has no NaN, weights stay in [−2, 2], it is independent of row order, and it uses only recursive EMAs with no full-sample statistics or dates.

## Known weaknesses

- **No confirmation:** September was −2.7% (Sharpe −0.82). All design-period profit comes from one month.
- **Whipsaw:** it loses in range-bound markets, as in July (−3.6%). The design drawdown was −15.3% and could be larger out of sample.
- **Low power:** three months, one regime, about 8 independent trend trades per ticker. A Sharpe of 1.1 on this sample cannot be told apart from zero.
- **Correlation:** the six contracts are 0.5–0.85 correlated, so this is close to one bet on market direction held six times.
- **Warm-up:** the first 15 days of any new sample are flat.
- **Simulator gap:** the bar-level sandbox is only an approximation of the minute-level judge (the basket differs by about 2 points).

## Honest out-of-sample expectation

- **Expected edge after costs:** about zero, perhaps a small positive (order of 0–3% per quarter) if the next period trends in either direction, and about −5% to −10% if it chops. The uncertainty is around ±15% per quarter.
- **Against random weights at the same turnover:** I do not expect it to beat them reliably. The design data give no evidence that it would.
- **Against the 2x trend engine:** it should behave like a slower, half-sized version: correlated, with lower turnover and a smaller drawdown. It is not reliably better in return.
- **Against the basket:** it will lag in a strong up-market, as it did here (+8.5% against +61%). It should do better only in a sustained decline, where it can go short.
- **Overall:** the valuable result of this study is the negative one. With 24 bp round-trip costs and three months of 4-hour data, none of the eight distinct mechanisms I tested (carry, cross-sectional momentum, slow trend, basket filter, short-term reversal, lead-lag, breakout, momentum-carry combination) shows an edge that survives a simple time split.
