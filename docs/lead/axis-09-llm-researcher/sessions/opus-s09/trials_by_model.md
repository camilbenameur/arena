# Trial log written by the model (verbatim)

# Research log: no robust edge found

## Setup
- The data covers 552 four-hour bars × 6 perpetual futures, from 2026-07 to 2026-09. Every trial was scored with `sandbox_backtest.simulate` (24 bp per round trip, funding charged, 0.3-unit trading band).
- For each trial I report the full period, the first half (H1 = bars 0–275, about 1 Jul to 16 Aug), the second half (H2 = bars 276–551), each month, the result per ticker (the rule run with only that ticker active) and turnover.
- The look-ahead check recomputes the weights on data cut off at a random bar t and compares row t. All tested functions passed.
- **Pre-registration:** before running any backtest I wrote the candidates C1–C10 below, each with a mechanism and fixed parameters. Trials 4, 9, 10 and 11 were *post hoc*: they reverse or re-tune a rule after seeing its result, and are flagged as data-mined.

## Pre-registered candidates (mechanism)
- **C1 Funding carry, cross-sectional:** short the contracts with high funding and buy those with low funding. Crowded leveraged longs overpay, and the crowding unwinds. Low turnover (daily).
- **C2 Cross-sectional 7-day momentum:** buy the 2 strongest, short the 2 weakest. Information spreads slowly across altcoins and investors chase recent winners. Market neutral, daily.
- **C3 Cross-sectional 1-day reversal:** liquidity providers are paid for absorbing overreaction.
- **C6 Lead-lag:** BTC prices news first, and altcoins catch up with a lag.
- **C7 Volume-shock reversal:** price moves on very high volume are forced liquidations that overshoot, then revert.
- **C8 Contrarian on extreme funding, per contract:** funding far above a contract's own recent level means crowding, followed by liquidation.
- **C4, C5, C9, C10 (not tested):** time-series trend, a volatility-managed long basket, a betting-against-beta long/short and trend with a funding filter. I dropped them because they are essentially long the market or duplicate the trend engine already given as a reference.

## Trials (all of them)
| # | Idea | Parameters | Full ret / DD / Sharpe / turnover | H1 / H2 | Jul / Aug / Sep | Verdict |
|---|---|---|---|---|---|---|
| 1 | C1 funding carry, cross-sectional | 3-day average funding, short top 2 / long bottom 2, ±1, daily | −13.6% / −14.5% / −5.1 / 39x | −4.9 / −9.2 | −4.0 / −7.5 / −3.0 | Rejected. Consistently wrong sign. |
| 2 | C2 cross-sectional momentum 7d | 42-bar return, long top 2 / short bottom 2, ±1, daily | +0.7% / −6.2% / 0.33 / 30x | +0.8 / 0.0 | +0.1 / +3.1 / −2.3 | Roughly zero after costs. ETH +6.8, XRP −7.0. **Chosen as the fallback.** |
| 3 | C3 cross-sectional reversal 1d | 6-bar return, long losers / short winners, daily | −14.5% / −16.3% / −6.3 / 71x | −7.8 / −7.3 | −4.9 / −6.2 / −4.0 | Rejected. About 8.5% of the loss is costs. |
| 4 | Trial 1 reversed (POST HOC): follow funding | 3-day average funding, long high / short low | +4.3% / −2.7% / 1.46 / 43x | −0.3 / +4.6 | +0.5 / +4.4 / −0.4 | Rejected. All gain in August, from SOL and XRP; LTC −4.6; lost in H1. |
| 5 | Cross-sectional momentum 3d | 18-bar return, top 2 / bottom 2, daily | −1.1% / −6.9% / −0.45 / 46x | −1.6 / +0.7 | −2.2 / −0.4 / +1.8 | Rejected. |
| 6 | C6 lead-lag BTC → altcoins | Altcoin vs BTC 1-bar gap >1.5%, catch-up trade with BTC hedge, hold 1 bar | −4.8% / −5.5% / −3.4 / 82x | −1.0 / −3.8 | −0.4 / −1.6 / −2.8 | Rejected. Costs eat it. |
| 7 | C7 volume-shock reversal | Volume >3× 30-bar median and move >2σ; fade for 6 bars | −14.1% / −17.0% / −3.1 / 19x | −3.7 / −10.9 | −3.4 / −12.0 / +1.1 | Rejected. Every ticker negative. |
| 8 | C8 contrarian on extreme funding | 1-day funding z-score vs its own past 30 days, beyond ±2 | −0.7% / −4.0% / −0.18 / 16x | −0.3 / −0.5 | −0.6 / −0.2 / 0.0 | Rejected. No effect. |
| 9 | Trial 7 reversed (POST HOC): ride volume shocks | Same events, follow the move for 6 bars | +10.1% / −6.9% / 2.1 / 23x | +1.7 / +8.4 | +2.0 / +11.3 / −3.0 | Rejected, see notes below. |
| 10 | Stability of trial 4 | Funding window 6 bars | −1.2% / −5.3% / −0.33 / 72x | −2.5 / +1.4 | −0.5 / 0.1 / −0.6 | Unstable. |
| 11 | Stability of trial 4 | Funding window 42 bars | +2.3% / −6.9% / 0.9 / 19x | +2.6 / −0.3 | +2.5 / +5.7 / −5.4 | Unstable. Sign flips by half; ETH and SOL positive, LTC and LINK negative. |
| 12 | Trial 2 with weekly rebalance (cost reduction set by reasoning, not search) | 7-day momentum, rebalance at the close of the Sunday 20:00 UTC bar | −9.5% / −13.5% / −3.9 / 11x | −2.4 / −7.6 | +0.8 / −6.5 / −4.1 | Rejected. XRP −11.6 on only 12 rebalances; very sensitive to rebalance timing. |

**Notes on trial 9:**
- The event study had 80 events at only 51 distinct timestamps. The average 6-bar gross move was +1.0%, but only +0.18% after removing the 5 biggest trades, which is below the 0.24% round-trip cost.
- Up-shocks were followed by +1.8% on average, down-shocks by −1.1%. So the gain is mostly "buy after up-moves in a rising market" plus August, not a symmetric effect.

## Time-split summary
Under a strict "choose on H1, confirm on H2" protocol, nothing passes:
- Trials 4, 9 and 11 were chosen *after* seeing the full sample, and trial 4 lost money in H1.
- Trial 9 was positive in both halves, but only because of the trend and its largest trades.
- The chosen fallback (trial 2) made +0.8% in H1 and 0.0% in H2.

## Chosen rule and why
**Trial 2 (C2): cross-sectional 7-day momentum, market neutral, rebalanced daily, ±1 on the top 2 and bottom 2. Status: NO ROBUST EDGE FOUND.**
- It was pre-registered with parameters set by reasoning (one-week horizon, top and bottom third) and was never tuned or reversed.
- It is zero net exposure, so it is not just "long in a rising market".
- It is backed by published crypto cross-sectional momentum research, and on design data it covered its costs: about +4% gross, about 3.6% costs, +0.7% net.
- I preferred it to the higher-scoring trials 4 and 9 because their results come from reversing a rule after seeing the data, and they fail checks on stability, concentration and drift.

## Known weaknesses
- The design result is roughly zero, with a large spread: per ticker from ETH +6.8% to XRP −7.0%, and by month from August +3.1% to September −2.3%.
- It depends heavily on rebalance timing: the weekly version (trial 12) made −9.5%.
- Turnover of about 30x equity per quarter costs about 3.6% a quarter, a known loss against an unproven gain.
- With only 6 assets, the long and short legs are 2 contracts each, so single-name events dominate.

## What I expect on unseen data
- Expected return after costs is about −4% to +2% per quarter (central estimate about −1%). Max drawdown is likely 5–10% and Sharpe is likely between −1 and +1.
- It should look roughly like random weights with the same turnover. Beating them would be weak evidence for cross-sectional momentum, not proof.
- It will very likely trail the basket in a rising market. Against the 2x trend engine, it has much smaller drawdowns but no reliable return advantage.
- Staying flat (all zeros) would have equal or better expected value.
