# Trial log written by the model (verbatim)

# Verdict: NO ROBUST EDGE FOUND

**Setup.** I wrote down the candidate list before running anything:
- C1: funding carry
- C2: cross-sectional momentum
- C3: short-term reversal
- C4: trend filter
- C5: timing the basket on funding crowding
- C6: low volatility
- C7: BTC lead-lag
- C8: fading liquidation-type bars
- C9: time-of-day / weekday seasonality
- C10: reversal of each coin's move relative to the basket

**How each trial was scored.** Every trial used `sandbox_backtest.simulate`, with costs of 24 bp per round trip and funding included.
- **H1** = the first 276 bars (2026-07-01 to about 08-16). **H2** = the rest.
- **Long-short (L/S) trials:** rank the six coins on the signal, go +1 on the top 2 and −1 on the bottom 2, re-decide every 6 bars (daily) unless stated otherwise.
- **"Before costs" figures:** net return plus turnover × 12 bp, as a rough estimate.

I ran 11 trials and stopped there, deliberately. The 4 unused trials would only have been spent on tuning ideas that had already failed.

| # | Idea (economic rationale) | Parameters | Full: return / max drawdown / Sharpe / turnover | H1 / H2 return | Months (Jul / Aug / Sep) | Verdict |
|---|---|---|---|---|---|---|
| 1 | C1 funding carry, market-neutral: short the coins with the highest funding (crowded leveraged longs pay to hold, crowding should reverse) and collect the carry | 18-bar mean funding, L/S | −13.6% / −14.5 / −5.1 / 39x | −4.9 / −9.2 | −4.0 / −7.5 / −3.0 | FAIL. Wrong sign; costs about 4.7% on top of a loss of about 9% before costs |
| 2 | C2 cross-sectional momentum over 7 days (slow spread of information, retail rotating late) | 42-bar return, L/S | +0.7% / −6.2 / 0.3 / 30x | +0.8 / 0.0 | +0.1 / +3.1 / −2.3 | FAIL. About +4% before costs, nothing after |
| 3 | C4 trend filter, long-only per coin (trend persistence, avoids drawdowns) | close > 120-bar EMA → 1, else 0 | +26.7% / −9.6 / 2.4 / 23x | −7.5 / +37.0 | −5.7 / +20.6 / +10.6 | FAIL. Far below the basket (+59%); this is the basket with worse timing |
| 4 | C6 low volatility (retail overpays for lottery-like high-volatility alts) | 42-bar volatility, long low / short high | −6.3% / −7.9 / −2.6 / 15x | −3.0 / −3.6 | all negative | FAIL |
| 5 | C10 3-day reversal of each coin's move relative to the basket (overshoots revert) | 18-bar residual, L/S | −9.9% / −11.4 / −4.5 / 45x | −4.0 / −6.4 | all negative | FAIL. Even the mirror-image momentum is only about +4.5% before costs, roughly 0 after |
| 6 | Trial 1 with the sign flipped, decided after seeing trial 1: funding as a sign of buying pressure, so go long high funding | 18-bar window, re-decided every 6 bars | +4.3% / −2.7 / 1.5 / 43x | −0.3 / +4.6 | +0.5 / +4.4 / −0.4 | WEAK and chosen after the fact; all of it comes from August |
| 7 | Trial 6, re-decided every 3 days to cut turnover | window 18, every 18 bars | +0.8% / −6.2 / 0.3 / 23x | +0.4 / +0.4 | +0.4 / +5.5 / −4.7 | FAIL |
| 8 | Stability check of trial 6: longer window | window 42, every 18 bars | −1.4% / −8.3 / −0.5 / 12x | +1.4 / −2.7 | +1.6 / +4.9 / −7.4 | FAIL. Result flips sign |
| 9 | Stability check of trial 6: shorter window | window 9, every 18 bars | +5.7% / −5.3 / 2.1 / 26x | −2.1 / +8.0 | −2.2 / +7.7 / +0.3 | FAIL. Depends on the window and comes from one month (August); mostly from XRP |
| 10 | C8 fade bars that look like liquidations: move beyond 2.5 standard deviations on more than 2x median volume (forced sellers or squeezed shorts overshoot) | hold 6 bars, weight 1 | −11.4% / −15.6 / −2.4 / 23x | −2.7 / −9.0 | −2.2 / −12.0 / +2.8 | FAIL. Fading up-moves in an uptrend; only 89 events |
| 11 | Volatility-managed long basket (volatility clusters; cut exposure when volatility is high) | 60% annual volatility target, 42-bar window, weights clipped to [0, 1.5] | +67.2% / −10.5 / 3.95 / 4x | +3.9 / +59.2 | +0.5 / +35.8 / +20.0 | FAIL as alpha. Sharpe is no better than the basket (4.09); it is just the basket at about 1.3x |
| ref | Equal-weight basket at 1x (this simulator) | — | +59.1% / −9.8 / 4.09 / 1x | +7.9 / +47.3 | +5.6 / +28.5 / +15.9 | Returned as the fallback |

## Findings
- **Market-neutral signals:** all of them (funding, momentum, reversal, low volatility, event fades) earn at most a few percent before costs over 3 months. At 15–45x turnover, costs of 2–5% wipe that out.
- **The only positive market-neutral result (funding-as-buying-pressure, trials 6/9) does not hold up:**
  - it was chosen after seeing trial 1;
  - its sign changes with the lookback window (trial 8);
  - its profit is concentrated in August and in XRP/SOL;
  - its H1 result is negative.
- **Timing rules (trend filter, volatility management)** do not beat simply holding the basket, either in return or in Sharpe.
- **Not tested:** C3 (short-term reversal), C5 (funding-crowding timing), C7 (BTC lead-lag) and C9 (seasonality). C3 and C7 are high-turnover ideas that the trial 5 cost picture suggests would not survive 24 bp. Trials 1/6 showed that high funding predicted continuation here, which argues against C5. C9 had a weak mechanism.

## Chosen rule and why
It is the constant equal-weight long basket at 1x (weight 1.0 on each contract), with no parameters and about 1x turnover.
- It makes no claim to an edge.
- It cannot be overfitted and is causal by construction.
- Its trading cost is negligible.
- I chose it over staying flat because a 1x long position in crypto perpetuals is the conventional neutral holding. That is a judgement call, not something the data showed.

## Known weaknesses
- It is 100% market exposure. If the unseen period falls, it loses roughly what the market loses; a drop of 20–40% is possible.
- It pays funding while long, about 2 bp a day here.
- It has no drawdown control.

## What I expect out of sample
- **Relative to the market:** zero excess return. It should track the basket benchmark almost exactly, apart from small differences in the simulator.
- **Absolute return:** equal to the market's direction in the unseen period, which I cannot predict.
- **Relative to random weights with the same (about 1x) turnover:** these are essentially also near-static positions, so I expect no meaningful difference.
- **Relative to the trend engine at 2x:** it will beat it if the market keeps trending or chops sideways, and lose to it in a sustained crash.
- The design-period figures (+59%, Sharpe 4) are the regime's market return, not a forecast.
