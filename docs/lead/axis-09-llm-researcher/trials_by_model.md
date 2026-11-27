# Trial log written by the model (verbatim)

# Trial log — verdict: NO ROBUST EDGE FOUND

No candidate passed my own checks. The frozen rule (trial 12) is the most defensible simple fallback, not a discovery: it was profitable in August only and lost in September.

## Protocol

- **Pre-registration:** ten candidate rules with mechanisms were written down before any backtest was run.
- **Trials used:** 14 of 15. Every variant evaluated is listed below; one trial was left unused.
- **Scoring:** all trials were scored with `sandbox_backtest.simulate` (12 bp per side, 0.3-unit band, funding).
- **Time split, fixed in advance:** select on July–August, confirm on September.
- **Statistical power:** with about 0.25 years of data, the standard error of an annualised Sharpe is roughly 2. Nothing below a Sharpe of about 4 is distinguishable from zero.
- **Sandbox reference:** the equal-weight basket scores +59.1%, Sharpe 4.09 in the sandbox simulator.

## Trials

Sharpe figures for July–August and September are annualised from daily returns within each window.

| # | Idea and mechanism | Parameters (set a priori) | Return | Max DD | Sharpe | Turnover | Jul / Aug / Sep | Sharpe Jul–Aug / Sep | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Cross-sectional funding carry. Leveraged longs pay for leverage; short the high-funding contracts, long the low. | 42-bar mean funding; long 2, short 2 at ±1 | −5.6% | −10.1% | −2.06 | 31.6x | −2.4 / −7.4 / +4.5 | −6.98 / +4.32 | Fail. Funding spread is 2–7% a year; it earned +0.29% against 4.0% of costs. |
| 2 | Time-series momentum blend. Under-reaction and herding. | Mean sign of 18/42/84-bar returns; 60% vol target | +1.5% | −18.6% | 0.39 | 93.7x | −10.9 / +19.2 / −4.5 | +1.07 / −1.45 | Fail. Costs were 12%; August only. |
| 3 | Cross-sectional momentum. Slow rotation of flows between coins. | 42-bar return; long 2, short 2 | −1.4% | −6.0% | −0.48 | 66.9x | −2.0 / +1.2 / −0.6 | −0.44 / −0.53 | Fail. Zero before costs; costs were 8.2%. |
| 4 | Cross-sectional reversal. Liquidity provision to impatient flow. | 18-bar return; long 2, short 2; daily rebalance | −9.9% | −11.4% | −4.48 | 45.2x | −1.3 / −3.9 / −5.1 | −3.94 / −5.35 | Fail. Negative even before costs. |
| 5 | Donchian breakout. Trend capture with fewer trades. | Enter on 60-bar extreme, exit on 30-bar; 60% vol target | −5.7% | −22.3% | −0.37 | 24.9x | −6.9 / +14.9 / −11.8 | +1.12 / −3.77 | Fail. |
| 6 | BTC lead–lag. Alts follow the BTC trend with a delay. | Alts take the sign of BTC's 18-bar return; 60% vol target | −19.1% | −31.4% | −1.39 | 75.1x | −27.6 / +24.7 / −10.4 | −0.73 / −3.05 | Fail. |
| 7 | Funding-crowding fade. Extreme funding signals crowded positioning. | 18-bar funding z-score against 126 bars; threshold ±1.5 | −15.2% | −18.0% | −2.65 | 39.7x | −3.0 / +2.2 / −14.4 | −0.31 / −5.57 | Fail. It shorted a rising market. |
| 8 | Volatility-managed long basket. Volatility clusters, so scale down when it is high. | Weight = 60% / vol, capped at 2 | +57.8% | −11.7% | 3.45 | 5.0x | −3.5 / +38.4 / +18.2 | +3.03 / +4.41 | Not a finding. Pure long beta, and worse than the plain basket. |
| 9 | Residual reversal against BTC beta. Idiosyncratic liquidity shocks revert. | 18-bar residual z beyond ±1.5; 90-bar beta; BTC hedge; daily rebalance | +2.4% | −3.5% | 1.17 | 17.3x | +0.0 / −0.6 / +2.9 | −0.33 / +5.62 | Fail. Negative in the selection window; XRP −3.2% offsets LINK +3.2%. Noise. |
| 10 | Volume-confirmed momentum. High-volume moves carry information and continue. | Sign of 42-bar sum of return × relative volume (126-bar base); 60% vol target | +14.1% | −19.4% | 1.52 | 57.9x | +0.7 / +18.4 / −4.3 | +2.73 / −1.28 | Best long/short rule in July–August; fails September. Costs were 6.5%. |
| 11 | Plain 7-day momentum with a cost-control fix: hysteresis and half size. | 42 bars; flip only beyond ±0.5σ; 30% vol target | +3.3% | −10.9% | 0.68 | 16.8x | −0.2 / +9.3 / −5.3 | +2.10 / −3.00 | Fail on September. |
| 12 | Trial 10 with the same cost-control fix. **Frozen rule.** | 42 bars; 126-bar volume base; ±0.5σ; 30% vol target | +9.9% | −8.5% | 1.83 | 14.0x | +0.4 / +11.2 / −1.6 | +3.09 / −1.11 | Selected on July–August; **fails September**. |
| 13 | Stability check of trial 12, faster. | 28 bars | +10.8% | −12.5% | 1.62 | 20.2x | −0.4 / +15.9 / −4.0 | +3.02 / −2.32 | Same pattern. |
| 14 | Stability check of trial 12, slower. | 63 bars | −0.1% | −10.6% | 0.06 | 10.9x | +0.0 / +6.4 / −6.1 | +1.72 / −4.18 | Edge disappears; not stable on the slow side. |

## Time-split result

- **Selection (July–August):** the best long/short candidates were the volume-weighted momentum rules, trials 10 and 12, with Sharpe of about 3.
- **Confirmation (September):** every trend variant lost, between −1.6% and −11.8% (trials 2, 5, 6, 10, 11, 12, 13, 14).
- **What the split is really worth:** trial 12 was flat until 28 July because of its 168-bar warm-up. Its "July–August" result is therefore one month, August, the same month in which the reference trend engine made +18.8%.
- **Halves:** trial 12 made +0.9% in the first half and +8.9% in the second.
- **Market-neutral rules (1, 3, 4, 9):** all at or below zero after costs.
- **Funding rules (1, 7):** the funding effect is an order of magnitude smaller than 24 bp per round trip.

## Chosen rule and why

Trial 12: volume-weighted 7-day time-series momentum, flipping only when the signal passes ±0.5σ, with a 30% annualised volatility target per contract.

- **It is what the pre-set protocol selected.** It was the best long/short rule on July–August.
- **Mechanism:** price moves on above-average volume are taken as informed flow that other participants under-react to; low-volume drift is down-weighted.
- **Cost control:** the hysteresis keeps it to 69 trades, 14x turnover and about 1.6% of costs per quarter.
- **Not a disguised long:** mean net exposure was +0.02x equity and mean gross 0.48x. It was long in 41% of ticker-bars, short in 29% and flat in 30%.
- **Per-ticker spread:** SOL +4.5, LTC +3.7, LINK +3.2, ETH +0.8, XRP −0.3, BTC −2.1 (percent of equity).
- **Mechanical checks:** the frozen file reproduces trial 12 exactly, the truncation test shows zero gap at 80 bar times, and shuffling the input rows changes nothing.

## Known weaknesses

- **It failed its own confirmation month.** All profit came from August, one trending month.
- **The volume weighting is unproven.** Its gain over plain momentum (+9.9% against +3.3%) is a single comparison and well within noise.
- **Parameter stability is one-sided.** The 28-bar version looks the same; the 63-bar version returns zero.
- **It is a trend rule.** It will be correlated with the reference trend engine and will lose in choppy, range-bound markets, as it did in September while the basket rose 16.7%.
- **Selection bias.** It is the best of 14 trials in a single three-month regime; the reported Sharpe of 1.8 is biased upward.
- **Warm-up.** It needs 168 bars (28 days) of history before taking a position. If the unseen data does not include earlier bars, it is flat for the first four weeks.
- **Simulator gap.** Results come from the bar-level approximation, not the minute-level judge.

## Honest out-of-sample expectation

- **Expected edge after costs:** about zero. My central guess is a Sharpe between 0 and 0.3, with a quarterly return of roughly 0% ± 8–10% and a cost drag of 1.5–2.5% per quarter.
- **Against the trend engine at 2x:** I expect a smaller drawdown and no reliable difference in return.
- **Against the basket:** I expect it to lag in a strongly rising market and to do better only if the market trends down persistently.
- **Against random weights at equal turnover:** I do not expect it to be statistically distinguishable.
