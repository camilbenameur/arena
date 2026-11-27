# Trial log written by the model (verbatim)

# Verdict: NO ROBUST EDGE FOUND

None of the nine pre-registered candidates passed the checks I fixed before running anything. The frozen rule is a pre-committed fallback (a slow long/flat trend filter per asset), not a discovery. Its +29.5% on the design period is market beta: it held about 0.63x long on average in a market that rose 61%, and it lagged buy-and-hold.

## Protocol

- **Pre-registration:** candidates C1–C10, each with a mechanism and parameters, were written to a file before the CSV was loaded.
- **Pass criteria (fixed in advance):**
  - positive after costs in both halves of the design period and in at least 2 of 3 months;
  - no single ticker contributing more than 60% of P&L;
  - sign survives two neighbouring parameter settings;
  - directional rules must show alpha against the basket, not just beta.
- **Scoring:** every variant was scored with `sandbox_backtest.simulate` (24 bp round trip, 0.3-unit band, funding).
- **Trial count:** 12 of 15 used. Every `simulate` call on a distinct weight matrix is logged below. Half, month and ticker breakdowns of the same weights are not counted as extra trials.
- **Time split:** H1 is the first 276 bars (1 Jul to mid-Aug), H2 the last 276 (mid-Aug to 30 Sep). Positions restart flat at the split.
- **Alpha:** residual of daily strategy returns after regressing on the equal-weight basket over the full period. For rules with a warm-up this includes the flat warm-up days, which makes their alpha look worse.
- **Data facts seen before trials:** mean funding is 1.0–3.2e-5 per 4-hour bar (about 2–7% a year); 4-hour volatility is 0.7–1.3%.

## Trial log

| # | Idea | Rationale (who is on the other side) | Parameters | Full: return / max DD / Sharpe / turnover | H1 / H2 | Jul / Aug / Sep | Other | Verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | C1 cross-sectional funding carry, market neutral | Leveraged longs pay for balance sheet; the receiver is paid to warehouse it | 7-day mean funding; long 2 lowest, short 2 highest at ±1; weekly rebalance | -1.5% / -4.3% / -0.51 / 8.9x | -0.4% / -1.2% | -0.8 / -2.7 / +2.0 | Cost 1.1%; alpha +0.4%; funding ranks not persistent | FAIL: the spread is too small to cover 24 bp |
| 2 | C2 cross-sectional momentum, market neutral | Slow diffusion and attention flows into relative winners | 14-day return; top 2 vs bottom 2 at ±1; weekly | -12.1% / -14.3% / -4.93 / 7.8x | -3.1% / -9.5% | +0.6 / -6.7 / -6.4 | XRP -7.0, LINK -6.2 | FAIL. Sign flip declined (see below) |
| 3 | C3 alts-vs-BTC dominance trend, dollar neutral | Risk-appetite rotation persists over weeks | Sign of 14-day change in alt/BTC ratio; BTC ∓2, alts ±0.4; weekly | +3.0% / -2.7% / 1.54 / 4.6x | -1.8% / +4.8% | -1.1 / +0.1 / +4.1 | Alpha -1.4% | FAIL: H1 negative, all gain from September |
| 4 | C4 cross-sectional residual reversal | Paid for providing liquidity to idiosyncratic flow | 3-day return minus cross-section mean; w = -0.75z; daily | -10.3% / -12.1% / -4.06 / 32.7x | -4.8% / -5.7% | -1.1 / -7.2 / -2.3 | Cost 4.1%; negative even before cost | FAIL |
| 5 | C5 basket trend filter, long/flat | Risk premium plus avoiding autocorrelated deleveraging | Equal-weight index, EMA15 > EMA60 | +23.5% / -10.0% / 2.15 / 14.9x | -8.5% / +34.9% | -6.6 / +23.8 / +6.9 | Beta 0.74; alpha -14.4% | FAIL: beta only, whipsawed in H1 |
| 6 | C6 funding-crowding timing, long/flat | Crowded leveraged longs lead to liquidation cascades | Flat when 3-day mean funding > 1e-4 per bar, else long 1 | +47.2% / -9.8% / 3.48 / 3.5x | 0.0% / +47.0% | -2.1 / +29.0 / +16.7 | Triggered on 0.9% of bars; beta 0.96; alpha -7.3% | FAIL: threshold never binds, so this is the basket. Untestable here |
| 7 | C7 Donchian trend, long/short | Under-reaction and stop cascades | Enter on 60-bar extreme, exit on opposite 30-bar extreme, ±1 | +0.9% / -20.4% / 0.31 / 17.3x | -4.5% / +5.7% | -4.0 / +16.2 / -9.5 | Alpha -16.5% | FAIL: same family and same result as the reference trend engine |
| 8 | C8 capitulation-bar fade | Forced liquidations overshoot; liquidity providers earn the bounce | Bar move > 3σ and volume > 2x 42-bar median; fade 1.5 for 6 bars | -15.1% / -20.6% / -2.26 / 19.5x | -2.4% / -13.2% | -1.7 / -18.0 / +5.3 | 54 events, only 11 down; all six tickers negative | FAIL: extreme bars continued rather than reversed |
| 9 | C9 volatility-managed long basket | Volatility clusters; short-term return/vol trade-off is weak | w = clip(60% annual / realised vol, 0, 2) | +61.3% / -12.0% / 3.49 / 3.6x | -2.0% / +64.9% | -4.5 / +41.4 / +19.5 | Beta 1.19; alpha -8.6% | FAIL: leveraged beta |
| – | C10 BTC lead-lag | Slower price discovery in alts | – | not run | – | – | Prior: dead at 4h after 24 bp | Not run; budget kept |
| 10 | F committed fallback: per-asset slow trend, long/flat | Risk premium while the trend is up; step aside in persistent declines | EMA30 > EMA120 gives 1, else 0; 120-bar warm-up | +29.5% / -9.2% / 2.69 / 4.8x | -3.8% / +34.5% | -4.1 / +21.6 / +11.0 | Beta 0.77; alpha -11.1%; cost 0.6%; tickers +1.7 to +6.7 | CHOSEN, labelled "no robust edge found" |
| 11 | F neighbour, reporting only | same | EMA20/80 | +30.2% / -9.7% / 2.74 / 8.9x | 0.0% / +30.3% | -0.4 / +22.8 / +6.5 | Alpha -9.1% | Same picture |
| 12 | F neighbour, reporting only | same | EMA45/180 | +39.1% / -9.8% / 3.39 / 2.0x | 0.0% / +39.1% | -2.1 / +21.8 / +16.7 | Alpha -3.3% | Same picture; not selected despite the higher return |

Reference from the brief: basket +61.2% (Jul +10.3, Aug +23.4, Sep +18.9); trend engine 1x +4.7%; trend engine 2x +2.8%.

## What the trials say

- **Market-neutral ideas (trials 1–4):** all are zero or negative after costs. Cross-sectional funding differences are worth roughly 1% a quarter gross at this size, which is less than the rebalancing cost.
- **Directional ideas (trials 5–9):** every positive return is explained by long exposure in a rising market. Alpha against the basket is negative in each case.
- **Sign flip declined:** trial 2 lost with a Sharpe of -4.9, so the opposite rule (14-day cross-sectional reversal) would have looked good in both halves. I did not take it, for three reasons:
  - it would be a post-hoc flip of a rule I registered with the opposite mechanism;
  - the result rests on about 11 weekly rebalances, a t-statistic near 2.2, which is what the best of 9 trials with either sign allowed produces by chance;
  - the 3-day reversal in trial 4 also lost, so there is no consistent reversal story.

## Chosen rule and why

**Rule:** for each contract, hold 1.0 (equity/6) when the 5-day EMA of the close is above the 20-day EMA, otherwise hold 0. No shorts, no leverage.

- **It was fixed before it was run.** After trials 1–9 failed, I wrote down the fallback and its parameters (5 days and 20 days as round numbers), then ran it. The neighbours in trials 11–12 were run for reporting only; I did not switch to 45/180 although it scored higher.
- **Why this family:** it has the strongest prior of anything I tested (time-series trend plus a long-run premium), low turnover, and a bounded downside. It is long/flat rather than long/short because both long/short trend variants (the reference engine and trial 7) made about nothing with drawdowns near 20%.
- **Cost:** 4.8x turnover in three months, about 0.6% of equity. Costs cannot sink it.
- **Mechanical checks:** it reproduces row t exactly when recomputed on data truncated at t (80 truncation points, 0 mismatches). There are no NaNs, weights are 0 or 1, and it is invariant to row order.

## Known weaknesses

- **No demonstrated timing skill.** On the post-warm-up window (from 21 Jul) it made +28.8% against +42.5% for buy-and-hold. The filter cost about 14 points in this regime.
- **Failed my own split test.** H1 was -3.8%. July is partly a warm-up artefact (20 days flat, then whipsaws).
- **The design period cannot validate it.** There is no sustained decline in the data, so the one situation the filter exists for is untested. Its justification is the prior, not this sample.
- **Six correlated assets are close to one bet.** BTC and LINK each flipped 7 times, so choppy markets will whipsaw it.
- **Warm-up.** It is flat for the first 120 bars of whatever history it is given. If the unseen period is supplied without the design rows, it sits out the first 20 days.

## Honest out-of-sample expectation

Expected alpha after costs is about zero. The rule will behave like roughly 0.5–0.8x of the basket with a lag:

- **Sustained rally:** positive, but well below the basket.
- **Sideways chop:** a loss of a few percent from whipsaws, roughly 1.5–2% of equity a quarter in costs at worst, plus the adverse entry and exit gaps.
- **Sustained decline:** a moderate loss, on the order of -5% to -15%, before going flat. This is where it should beat the basket.

Against the comparisons the judge will make: it should have a much smaller drawdown than the 2x trend engine; it should beat the basket only if the market falls; and against random weights with the same turnover it carries no advantage beyond its long bias. I would not allocate capital to it as an edge.
