# Trial log written by the model (verbatim)

# Trial log — verdict: NO ROBUST EDGE FOUND

## Protocol (written to file before any backtest)
- Eight candidates with mechanisms were pre-registered; four further ideas were rejected without testing and used no trial:
  - BTC→alt lead-lag at 4h: any edge is far below 24 bp.
  - Time-of-day seasonality: no mechanism.
  - Low-vol / betting-against-beta: a near-static bet, so one observation in three months.
  - Vol-managed long basket: merely long.
- Every `simulate()` of a selectable rule variant counts as one trial. Split, month and ticker diagnostics come from the same run.
- No signal-versus-forward-return scans were done outside the trials.
- Time split: SELECT = Jul–Aug (first two thirds), CONFIRM = Sep (last third). Weights are computed causally on the full file and sliced.
- Pass criterion: net > 0 in both parts, not driven by one ticker or month, and parameter neighbours agree.
- Trials used: **10 of 15**. I stopped deliberately; more search on 92 days would be noise-mining.

## Trials
All results are net of costs, from `sandbox_backtest.simulate`. "Turn" is turnover in multiples of equity.

| # | Idea | Economic rationale | Parameters | Full | Jul–Aug | Sep | Turn | Verdict |
|---|------|--------------------|------------|------|---------|-----|------|---------|
| 1 | XSMOM: long top 2 / short bottom 2 by past return, market neutral | Slow attention and flow diffusion across coins; the other side is contrarian profit-takers | 42-bar return, daily rebalance, ±1 | +0.02% (Sharpe 0.06, DD −6.5%) | +1.74% | −1.62% | 28.8x | FAIL. Gross +3.4% fully eaten by 3.4% cost; Sep negative; XRP −9.9% vs +13.7% from the rest |
| 2 | XSFUND: long 2 lowest / short 2 highest funding | The crowded levered side pays funding and is prone to unwinds | 18-bar mean funding, daily, ±1 | −11.32% (Sharpe −3.95) | −11.38% | −0.25% | 38.9x | FAIL. Funding received +0.14% is negligible; high-funding names kept rising |
| 3 | TSMOM: slow per-ticker trend | Herding and under-reaction; slower than the reference engine, so fewer whipsaws | sign of 60-bar return × min(2, 1%/σ60), daily | −18.85% (DD −26.1%) | −11.29% | −8.92% | 31.0x | FAIL. Whipsawed in Jul and Sep |
| 4 | LIQREB: fade extreme high-volume bars (symmetric) | Forced liquidation flow creates temporary pressure; the liquidity provider earns the rebound | \|ret\| > 2.5σ60 and volume > 2× 60-bar median, hold 6 bars, ±1.5 (86 events) | −21.17% | −19.90% | −1.57% | 28.9x | FAIL. Extreme bars continued; every ticker negative; −17.7% in Aug alone |
| 5 | RESREV: fade 3-day residual vs basket | Idiosyncratic flow shocks in a one-factor market revert | enter \|z\| > 2 (90-bar std), exit \|z\| < 0.5, ±1.5 (40 entries) | −3.25% | −8.16% | +5.34% | 19.5x | FAIL. Sign flips between the two parts |
| 6 | TSCARRY: always be the funding receiver | The funding payer is the crowded, impatient side | w = −sign(18-bar mean funding), daily | −27.51% | −11.17% | −18.50% | 27.7x | FAIL. Effectively short a rising market (correlation with basket −0.83); funding earned only +0.86% |
| 7 | VOLMOM: 3-day residual momentum only where volume is elevated | Attention-driven inflows persist for days | 18-bar residual return, 18-bar volume > 90-bar volume, top 2 / bottom 2, daily | −0.06% | −0.47% | +0.41% | 27.6x | FAIL. Zero net; cost 3.4% |
| — | COMBO of 1 and 2 | — | — | not run | — | — | — | Pre-condition not met (trial 2 failed SELECT) |
| 8 | XSMOM with overlapping tranches (J = K = 7 days). Committed as the fallback before running | Same mechanism as trial 1; tranche averaging chosen on turnover alone (28.7x → 8.4x, computed without returns) | 42-bar return, mean of last 42 bars of the daily top 2 / bottom 2 snapshot, size 1.0 | **−3.76%** (Sharpe −1.80, DD −7.35%) | −2.89% | −1.17% | 8.2x | FAIL. Months +1.0 / −3.9 / −0.9; cost 1.0%; XRP −8.2% gross |
| 9 | Stability neighbour of 8 | same | J = K = 21 | −0.87% | +0.90% | −1.78% | 16.2x | FAIL. Zero within noise |
| 10 | Stability neighbour of 8 | same | J = K = 84 | +0.15% | +0.57% | −0.48% | 3.1x | FAIL. Zero within noise |

Things run that are not trials, disclosed for completeness:
- One harness crash before any result printed.
- A turnover-only comparison of daily rebalancing against tranche smoothing, with no returns involved.
- Re-running the frozen file to confirm it reproduces trial 8 exactly (−3.76%, 8.2x), plus the causality check.
- A placebo that applies trial 8's weights with ticker labels permuted (719 permutations, same turnover). It is not a selectable rule. Mean −1.66%, standard deviation 3.56%, 5th/50th/95th percentiles −7.1 / −2.0 / +4.4%. Trial 8 sits at about the 30th percentile, so it is indistinguishable from random weights.

## What the design period says
- **Nothing passes.** No rule is net-positive in both parts of the split.
- **Momentum family (trials 1, 8, 9, 10):** full-period net results are +0.0, −3.8, −0.9 and +0.2%. All four are negative in September.
- **XRP dominates.** In every momentum variant the gross P&L is positive on four or five tickers and −5 to −10% on XRP, a persistent laggard the rule shorted 54% of the time. The same episode drives −9 to −10% in trials 1, 2 and 4.
- **Fade and carry ideas (trials 2, 4, 6) lose clearly.** I did not sign-flip them. That would be a post-hoc rule whose profit sits in one month (August) and largely one ticker.
- **Power.** With 92 days, even a true Sharpe of 2 gives a t-statistic of about 1. Nothing here is close to distinguishable from zero.

## Chosen rule and why
Trial 8: cross-sectional 7-day momentum with overlapping tranches, market neutral, at most 0.67x gross. It is labelled **no robust edge found**.

I chose it by a decision rule written before running trials 8–10. The rule was: hand back trial 8 unless it is net-negative in both splits and both neighbours are net-negative on the full period, in which case hand back all zeros.

- Trial 8 was negative in both splits and trial 9 was negative. Trial 10 was +0.15%, so the all-zero trigger was missed by a hair.
- I am applying the pre-commitment as written rather than re-deciding after seeing results. A stand-aside rule (all zeros) is essentially equally defensible.
- I did not switch to trial 10, the best-scoring and lowest-turnover neighbour. That would be selection on noise.
- Parameters come from convention, not search: 7-day formation equals 7-day holding, top and bottom third, size 1.0.

Why this family at all: it is the only one with a documented prior in crypto, it has no market beta (correlation with the basket 0.03, average net exposure 0.00), it has the lowest cost drag (about 1% per quarter), and its risk is bounded (design maximum drawdown −7.4%).

## Known weaknesses
- **Negative on the design data** in both parts of the split, and not better than label-permuted placebos.
- **Six assets.** Each side is two names, so one idiosyncratic name (XRP here) decides the outcome.
- **Rebalance anchor.** Snapshots are taken at the 00:00 UTC bar; a different hour would give somewhat different numbers.
- **Warm-up.** If the evaluation file starts cold, the first 42 bars are flat and the next 42 ramp up. With the design history prepended there is no warm-up.
- **No-trade band lag.** Tranche steps are about 0.14 weight units per day against a 0.3 band, so positions lag targets by one to three days.
- **Simulator gap.** The sandbox fills at the bar close; the judge fills at the next minute's open. At 8x turnover the difference should be small.

## Honest out-of-sample expectation
- **Return:** gross edge about 0, costs about −1% per quarter (8x turnover × 12 bp), funding about 0. That gives a net of roughly **−1% per quarter, ±4% at one standard deviation**. Drawdown should be in the mid single digits.
- **Against the basket:** it wins only if the market is flat or down. It will lose badly to the basket in another +60% quarter.
- **Against the trend engine at 2x:** the outcome will be decided mostly by the trend engine's own large swings, not by this rule.
- **Against random weights with the same turnover:** a coin flip.

The finding is that, on this three-month single-regime sample with 24 bp round-trip costs, none of the seven mechanisms tested shows an edge that survives a simple time split.
