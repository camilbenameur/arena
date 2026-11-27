# Trial log written by the model (verbatim)

# Trials log — verdict: NO ROBUST EDGE FOUND

No candidate passed my pre-registered selection and confirmation test. The frozen rule is the most defensible simple fallback (slow trend with hysteresis, small size), not a discovered edge. Its design-period profit is mostly long beta in a market that rose about 59%.

## Protocol (fixed before any result was seen)

- **Candidates:** 10 rules with rationale and parameters were written to a pre-registration file before any backtest. The remaining 5 trials were reserved for neighbour checks.
- **Time split:** selection (SEL) on July and August; confirmation (CONF) on September, looked at only for rules that passed SEL.
- **Pass criterion on SEL:** net return above 0 after costs, with at least 4 of 6 tickers contributing positively. Market-neutral rules also needed Sharpe above 1; directional rules needed to beat their own beta times the basket.
- **Scoring:** every trial used `sandbox_backtest.simulate`. Every rule passed a truncation causality check before scoring.
- **Trial count:** 15 variants run, 15 logged. No crashed runs or bug-fix reruns.
- **Sandbox basket reference:** SEL +36.4% (Jul +5.6%, Aug +28.5%), Sep +15.9%, full +59.1%. The bench reports +61.2%, so the sandbox differs slightly.

## Trials

Abbreviations: Ret = net return, TO = turnover in multiples of equity, netW = average net weight.

| # | Idea | Economic rationale | Parameters | Design result | Verdict |
|---|---|---|---|---|---|
| 1 | C1 cross-sectional funding carry, market neutral | Leverage-constrained longs pay funding in crowded coins; the receiver is paid for balance sheet, and crowding unwinds | 7d mean funding; long 2 lowest, short 2 highest at ±1; daily rebalance | SEL −10.4%, Sharpe −7.3, TO 11x (Jul −3.6%, Aug −7.1%) | FAIL. High-funding coins kept outperforming. Funding spread is about 1 bp/day, negligible against 24 bp. I did not flip the sign; that would be a post-hoc rule. |
| 2 | C2 cross-sectional momentum, market neutral | Slow capital and attention rotation among alts | 14d return; long top 2, short bottom 2; rebalance every 3 days | SEL +0.3%, Sharpe 0.12, TO 6.6x; 2 of 6 tickers positive | FAIL (noise) |
| 3 | C3 cross-sectional 1-day reversal | Liquidity provision against forced flow; pre-registered as a falsification test because of costs | 24h return; long 2 worst, short 2 best; daily | SEL −10.9%, Sharpe −9.6, TO 48x | FAIL. Costs are about 5.7% and the gross is also negative. |
| 4 | C4 slow time-series trend with hysteresis | Under-reaction and herding; slower than the reference engine, so fewer trades | EMA 120 bars (20d), band ±1%, inverse-vol sizing to 60% per contract, long/short | SEL +20.9%, Sharpe 2.0, DD −14.2%, TO 13.9x, netW +0.25, 5 of 6 tickers positive. CONF Sep +4.9% with beta 0.95 against basket +15.9% (alpha about −9%). Full +27.5%, DD −14.6%, TO 23x, cost drag 2.7% | Passed SEL, FAILED CONF. Positive, but worse than its own beta in September. |
| 5 | C5 betting against beta | Retail lottery demand for high-beta alts | Static: BTC +2, five alts −0.4 each | SEL −1.7%, Sharpe −1.2 | FAIL |
| 6 | C6 funding-crowding market timing | High funding means crowded leveraged longs and cascade risk | Basket long when 3d average funding is below its 30d median, else flat | SEL +13.8%, Sharpe 2.6, TO 10.7x, netW 0.21 (active only in August after warm-up). CONF Sep +1.8% with beta 0.32 (alpha about −3%) | Passed SEL nominally, FAILED CONF. The return is proportional to time in market; no timing skill. |
| 7 | C7 capitulation reversal | Liquidated longs pay a liquidity premium | Basket 4h return below −2.5σ and volume above 2x median; long +1.5 for 12 bars | SEL −0.2%; only 19 bars in position | FAIL / untestable (too few events) |
| 8 | C8 residual pairs reversion | Idiosyncratic liquidity shocks revert | 5d residual against basket; enter at z beyond ±1.5, exit at 0 | SEL +0.4%, Sharpe 0.21, TO 9.3x; 3 of 6 tickers negative | FAIL (noise) |
| 9 | C9 vol-managed long basket | Volatility clusters; long-only benchmark-like rule | Weight = min(2, 60% / 5d basket vol) | SEL +39.7%, Sharpe 3.05, DD −13.7%, against basket Sharpe 3.86 | FAIL. Leveraged beta with worse Sharpe than the basket. |
| 10 | C10 trend with carry gate | Avoid crowded longs and paying shorts | C4, dropping longs when funding is in its own top third and shorts when funding is negative | SEL +4.9%, Sharpe 0.95, TO 21.8x | FAIL. The gate adds turnover and removes profit. |
| 11 | C4 neighbour: span 80 | Stability check | Span 80, band 1% | SEL +26.7%; Sep +0.7%; full +28.1%, DD −14.9%, TO 24.6x | Sign stable; September close to 0 |
| 12 | C4 neighbour: span 180 | Stability check | Span 180, band 1% | SEL +29.4%; Sep +12.8%; full +48.2%, DD −10.2%, TO 13.4x | Sign stable; slower is better in an up-trend |
| 13 | C4 neighbour: band 3% | Band of about one daily σ, so a flip must clear 24 bp | Span 120, band 3% | SEL +25.1%; Sep +12.6%; full +41.9%, DD −11.2%, TO 7.8x; 17 flips | Sign stable; turnover cut by two thirds |
| 14 | C4 neighbour: band 0 | Stability check | Span 120, band 0 | SEL +7.1%, DD −20.9%; Sep +7.7%; full +16.2%, TO 65x; 140 flips | Still positive, but whipsaw and cost take most of it. Hysteresis is essential. |
| 15 | FROZEN: trial 13 at half size | No confirmed edge, so carry less risk | Span 120, band 3%, vol target 30%, weight floor 0.2 | SEL +13.4%, Sharpe 2.39, DD −5.8%, TO 3.1x. CONF Sep +6.0%, Sharpe 3.56, DD −4.1%, TO 1.1x. Full +21.9%, Sharpe 2.82, DD −5.75%, TO 3.9x | Chosen fallback; see below |

## Time-split results of the frozen rule (trial 15)

| Period | Rule | Basket | Note |
|---|---|---|---|
| July | −3.0% | +5.6% | Active only from 21 July because of the 20-day warm-up |
| August | +17.3% | +28.5% | |
| SEL (Jul–Aug) | +13.4% | +36.4% | Per ticker: BTC +3.0, ETH +3.3, SOL +3.4, XRP +2.7, LTC −0.8, LINK +1.4 |
| CONF (Sep) | +6.0% | +15.9% | Per ticker: BTC +0.7, ETH +0.7, SOL +1.1, XRP −0.6, LTC +3.3, LINK +0.9 |
| Full | +21.9% | +59.1% | Cost drag 0.46%, funding −0.55%, realised vol about 24% a year |

In September the rule was long almost throughout at about 0.65x. A beta-matched basket would have made roughly +10%, so the rule's alpha against its own beta was negative (about −4%). The same was true of trial 4.

## Chosen rule and why

- **What it does:** per ticker, go long when the close is more than 3% above the 20-day EMA and short when more than 3% below; inside the band, keep the previous side. Size is 30% annualised vol divided by 20-day realised vol, floored at 0.2 and capped at 2.
- **Why this one:** it is the only family that was positive in both SEL and CONF and across all four parameter neighbours. It has an established mechanism (time-series momentum from under-reaction and herding). Its cost is small and visible: 17 flips and 3.9x turnover, about 0.5% per quarter.
- **How the parameters were set:** span 120 was pre-registered. The 3% band was taken from neighbour trial 13 on cost grounds; trials 14, 4 and 13 show turnover falling from 65x to 23x to 7.8x as the band widens. The half size is a risk decision, not a return optimisation.
- **Disclosed selection:** I picked the band after seeing the full design period. That is a selection among 5 variants, so its numbers are optimistically biased.

## Known weaknesses

- **It is mostly long beta.** The design period is one bull regime. The edge criterion (beating own beta times basket) failed in September for every trend variant.
- **Magnitude is not parameter-stable.** September ranges from +0.7% (span 80) to +12.8% (span 180) at the same sizing. One dip-and-recover episode drives the difference.
- **July chop is essentially untested.** The reference engine lost 13% in July, but warm-up kept this rule flat until 21 July. In the 11 active July days it lost 3.0% (at half size).
- **Shorts were rarely right.** The early-August shorts in SOL, XRP and LTC mostly cost money.
- **Low power.** About 17 independent decisions in total; the Sharpe figures (2.4 to 3.6) mean little.
- **Small weights weaken risk control.** At these sizes the 0.3 re-trade threshold means vol-driven resizing almost never executes. Positions change mainly on flips; the 0.2 floor guarantees a flip always trades.
- **No random-weights test was run.** I did not run a turnover-matched random-weights comparison in the sandbox.
- **Bench mismatch.** The sandbox is a bar-level approximation; the minute-level bench will differ somewhat.

## Honest out-of-sample expectation

- **Alpha:** about zero after costs against a beta-matched basket. The long-run prior for slow crypto trend is a Sharpe of roughly 0 to 0.5, which at about 24% vol is about 0% to +3% per quarter, with a one-sigma range near ±12%.
- **If the trend persists, up or down:** it should capture roughly 30% to 50% of the basket's absolute move. It will lag the basket in a continued rally.
- **If the market chops in a range wider than ±3% around the 20-day EMA:** expect a loss of about 3% to 8%. That is still far smaller than the 2x trend engine would lose in such a regime.
- **Against turnover-matched random weights:** I expect no reliable advantage beyond what the trend's beta delivers.

The design-period figures (+21.9%, Sharpe 2.8) should not be extrapolated.
