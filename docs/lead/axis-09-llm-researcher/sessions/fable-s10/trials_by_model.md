# Trial log written by the model (verbatim)

# Trial log — verdict: NO ROBUST EDGE FOUND

## Protocol actually followed
- **Candidates:** 12 rules with mechanisms were written down before any result was seen (listed at the end).
- **Trials:** 11 variants were evaluated out of the 15 allowed. Every one is in the table; nothing else was backtested.
- **Scoring:** all figures come from `sandbox_backtest.simulate` at bar level, 12 bp per side, including funding.
- **Not counted as trials:**
  - One calibration run of the equal-weight basket: +59.1% in the sandbox against the +61.2% reference.
  - One descriptive look at volatility, funding levels and correlations, with no signal-versus-return analysis.
- **Time split:** selection is 1 Jul – 15 Aug (276 bars, basket +7.9%); holdout is 16 Aug – 30 Sep (276 bars, basket +47.3%).
- **Blinding:** my harness hid holdout and full-period numbers for trials 1–9. Only the single selection survivor (trial 2) was unblinded for confirmation. Everything else was revealed after trial 9, for documentation only.
- **Stability checks:** trials 10–11 were run unblinded on the fallback's neighbours. They were not used to tune it.
- **Statistical power:** over a 46-day half, the standard error of an annualised Sharpe is about 2.8. A zero-edge rule shows Sharpe above 1.5 in both halves roughly 9% of the time, so with about 10 candidates a false pass was more likely than not. I therefore gave more weight to mechanism and cost arithmetic than to any single number.

## Trials
Weights are ±1 (equity/6 per contract) unless stated. Columns show net return; Sh = Sharpe, DD = max drawdown, TO = turnover in multiples of equity.

| # | Idea and rationale | Parameters | Selection | Holdout | Full period | Months Jul / Aug / Sep | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | Slow time-series momentum, long/short (underreaction, slow flows) | sign of 10-day return, decided once a day | −10.2% (Sh −4.9) | −0.5% | −10.7%, DD −20.6%, Sh −0.96, TO 26.6x | −9.9 / +9.2 / −9.5 | Fail: whipsawed; both legs lost in selection |
| 2 | Cross-sectional momentum, market neutral (flows chase relative winners) | 10-day return, long top 2 / short bottom 2, daily | +1.1% (Sh 1.8, cost 1.4%) | **−5.5% (Sh −3.3)** | −4.5%, DD −8.0%, Sh −1.64, TO 24.8x | −0.1 / +0.6 / −4.8 | Only selection survivor; failed confirmation. One ticker (XRP, −10.7 points) dominates |
| 3 | Donchian breakout long/short (stop and liquidation clusters) | 10-day entry, 5-day exit | −4.7% | +5.8% | +0.8%, DD −20.1%, Sh 0.30, TO 16.9x | −4.2 / +16.2 / −9.4 | Fail: one good month |
| 4 | Basket long/flat on BTC trend (deleveraging cascades persist) | long all six when BTC 10-day return > 0 | −6.6% | +22.6% | +14.4%, DD −8.5%, Sh 1.58, TO 13.0x | −7.5 / +14.7 / +7.2 | Fail: long 59% of the time yet earned about a quarter of the basket, so timing was negative; pure beta |
| 5 | Multi-day residual reversal vs BTC (alt overshoot) | 3-day residual, 20-day beta, 2 vs 2 alts, daily | −3.3% | −2.9% | −5.8%, DD −7.6%, Sh −2.15, TO 30.3x | −0.6 / −2.3 / −3.2 | Fail in every month |
| 6 | Low-volatility tilt (lottery demand for high-vol alts) | 20-day vol, 2 vs 2, inverse-vol legs, weekly | −2.1% | +2.2% | −0.5%, DD −4.4%, Sh −0.32, TO 2.0x | +0.1 / −2.1 / +1.3 | No effect |
| 7 | Cross-sectional funding carry / crowding | 7-day mean funding, long 2 lowest / short 2 highest, daily | −3.9% (Sh −6.6) | −2.3% | −6.0%, DD −10.4%, Sh −2.32, TO 17.8x | −3.0 / −6.8 / +3.7 | Fail: funding received was +0.1% against 2.2% of costs |
| 8 | Cross-sectional 1-day reversal (liquidity provision) | 1-day return, 2 vs 2, daily | −7.6% | −2.4% | −9.6%, DD −11.3%, Sh −4.03, TO 76.7x | −4.5 / −3.1 / −2.4 | Fail: costs alone were 9.8% |
| 9 | **Slow Donchian trend, long/short/flat, inverse-vol size fixed at entry** (multi-week trend with hysteresis to cut whipsaw) | 20-day entry, 10-day exit, weight = clip(1% / 20-day 4h vol, 0.5, 2) | −3.0% (Sh −2.1, TO 3.1x) | +14.3% (Sh 2.1, DD −14.6%) | **+10.7%, DD −14.6%, Sh 1.14, TO 9.5x, cost 1.1%** | −3.2 / +20.5 / −5.9 | Not a finding: one positive month in three. **Chosen as fallback** |
| 10 | Stability of 9, faster | 15-day entry, 7.5-day exit | −6.6% | +15.5% | +7.8%, DD −15.1%, Sh 0.90, TO 11.4x | −4.6 / +16.8 / −3.2 | Same shape as 9 |
| 11 | Stability of 9, slower | 25-day entry, 12.5-day exit | −1.7% | +19.7% | +17.4%, DD −11.5%, Sh 1.72, TO 6.5x | −2.6 / +17.9 / +1.3 | Same shape; better only because it stays long for longer |

Reference points for the same periods: basket +7.9% selection, +47.3% holdout, +59.1% full; the trend engine at 2x returned +2.8% with a −35.5% drawdown.

## Time-split result
- **Selection half:** 10 of the 11 variants lost money. The only positive one, trial 2, made +1.1%, which is indistinguishable from zero.
- **Confirmation:** trial 2 lost 5.5% in the holdout, driven by a single ticker. Nothing passed selection and then confirmation.
- **Holdout gains elsewhere:** every rule that made money in the holdout was a trend rule that was net long during a +47% rally. In trial 9's holdout the long leg earned about +25 points and the short leg lost about 9.
- **Parameter sweep:** results across the 10-, 15-, 20- and 25-day entry channels (trial 3 at unit size, trials 10, 9 and 11 with inverse-vol sizing) improve steadily with slowness. That is the pattern of beta capture, not timing skill.

## Chosen rule and why
The frozen rule is trial 9 exactly; no untested change was made. I chose it on prior grounds, not because of its design-period return:
1. **Mechanism:** multi-week time-series trend is the best-documented effect in major crypto contracts, and the horizon was set from that literature, not searched.
2. **Cost:** it is slow, at about 9.5x equity turnover per quarter (4–6 entries per ticker), so costs are about 1.1% per quarter.
3. **Symmetry:** it stays long/short/flat, so it is not a disguised long-only bet. I did not drop the losing short leg after the fact.
4. **Parameters:** I kept the pre-set 20/10-day channel and did not move to the better-scoring 25-day neighbour.
5. **Size:** gross exposure averages about 0.65x equity, with a largest single weight of 1.79.

The exit channel, volatility window, target volatility and weight clip were set by judgment and never varied.

## Known weaknesses
- **No evidence of edge.** It lost in the selection half, and all profit came from one month (August) and from the long side in a rising market.
- **Negative timing against its own exposure.** It averaged about 0.36x equity net long while the basket made +59%, which would imply roughly +21% from static exposure; it made +10.7%.
- **Chop.** It loses about 3–6% a month in range-bound markets, as in July and September. Its design drawdown was −14.6%.
- **Not blind.** I specified it after seeing the selection-half results of trials 1–8 and trial 2's holdout.
- **Starting position.** At the last design bar it is long all six contracts at weights 0.65–1.27, about 0.9x equity in total. The first weeks out of sample are therefore a bet that the rally continues, until the 10-day exits trigger.
- **Concentration.** The six contracts correlate at 0.5–0.85, so this is effectively one bet.
- **Simulator gap.** The bar-level simulator differed from the minute-level judge by about 2 points on the basket; expect similar slippage in these numbers.

## Honest out-of-sample expectation
- **Return:** about zero after costs, at best a Sharpe of 0 to 0.5 on prior grounds. That is roughly −1% to +3% per quarter, with a plausible range of about ±15%.
- **Against the basket:** it will lag in a continued rally and beat it in a sustained decline.
- **Against the 2x trend engine:** it will probably show a smaller drawdown, but only because it is smaller and slower, not because it is smarter.
- **Against random weights at the same turnover:** I have no evidence it would win.
- **Recommendation:** do not allocate on the basis of this rule. The useful result is that 3 months of 4-hour bars on six correlated contracts, at 24 bp per round trip, cannot support any of the tested ideas.

## Pre-registered candidates
Numbers 5, 7, 8 and 12 were not tested; number 8 is unrelated to trial 8.

1. **Cross-sectional funding carry** — trial 7.
2. **Slow time-series momentum** — trial 1.
3. **Cross-sectional momentum** — trial 2.
4. **Short-term cross-sectional reversal** — trial 8.
5. **BTC lead-lag on alts** — not tested. A rule flipping every 4-hour bar implies turnover above 200x per half, about 25% in costs, which needs an implausible per-bar correlation above 0.1.
6. **Basket long/flat on BTC trend** — trial 4.
7. **Crowding-filtered trend** — not tested, same reason as 12.
8. **Vol-targeted basket** — not tested: it is a risk overlay on beta with no alpha claim.
9. **Multi-day residual reversal** — trial 5.
10. **Low-volatility tilt** — trial 6.
11. **Donchian breakout** — trials 3, 9, 10 and 11.
12. **Funding time-series contrarian** — not tested. Funding averaged 0.1–0.3 bp per 4-hour bar (2–7% a year), with autocorrelation at a one-day lag of about 0.06 for the alts (0.28 for BTC). There was no crowding to trade, and trial 7 confirmed funding carried no signal.
