# Trial log written by the model (verbatim)

# Trial log — verdict: NO ROBUST EDGE FOUND

None of the pre-registered ideas showed timing or selection skill that I could tell apart from chance on the design period. The frozen rule is a fallback: the simplest, lowest-turnover rule with a well-known mechanism, at its pre-registered parameters. It is not a discovery.

## Protocol

- 13 candidates were written down, each with a mechanism, before any result was seen.
- **12 of the 15 allowed trials were used**; 3 were deliberately left unspent. Every call to `simulate` on a rule variant is counted below.
- Not counted as trials:
  - the 1x basket benchmark (my bar-level run gives +59.1%, against the +61.2% reference);
  - descriptive statistics with no P&L (funding levels, volatility, correlation, how often a signal triggers);
  - the placebo runs attached to each trial.
- All trials were scored with `sandbox_backtest.simulate`. Monthly and per-ticker figures come from a copy of the same loop, asserted to reproduce its headline return.
- The time split is the first half (H1, 276 bars, to mid-August) against the second half (H2). Signals are computed causally on the full history, and the simulator is restarted on each half.
- The placebo mimics the judge's "random weights with the same turnover" test. Each trial's own weight matrix is rolled in time by a random offset and its ticker columns are permuted, 150 times. The "placebo percentile" is the share of those draws the real rule beats; about 50 means no skill beyond its average exposure.
- Causality was checked for every rule by recomputing on truncated data (40 truncation points for the frozen rule, zero gap).

## Trials

Design-period results are net of costs. Sharpe is annualised from daily returns.

| # | Idea and rationale | Parameters (set in advance) | Return | Max DD | Sharpe | Turnover | Months Jul / Aug / Sep | H1 / H2 return | Placebo pctile | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | C1 cross-sectional funding carry, neutral. Leveraged longs pay for balance sheet. | 7-day EMA of funding; long 2 lowest, short 2 highest, ±1.5 | -13.8% | -20.5% | -3.30 | 70x | -6.9 / -10.6 / +3.6 | -9.4 / -5.1 | 31 | FAIL. Funding earned was only +0.55%, price P&L was negative, and costs were about 9.5%. |
| 2 | C3 slow time-series momentum. Under-reaction and herding. | Sign of 42-bar return, scaled to 60% vol | +3.3% | -21.9% | 0.60 | 115x | -7.4 / +17.4 / -4.9 | -9.9 / +14.5 | 59 | FAIL. About 18% gross mostly eaten by 14.5% costs; August only. |
| 3 | C4 cross-sectional momentum, neutral. Slow rotation of flows. | 42-bar return; top 2 / bottom 2, ±1.5 | -2.2% | -8.9% | -0.48 | 99x | -2.9 / +1.8 / -1.0 | -2.9 / +0.9 | 89 | FAIL net. About 10% gross against 12% cost. |
| 4 | C13 residual reversal, neutral. Idiosyncratic flow shocks revert. | 18-bar return minus basket; fade top 2 / bottom 2 | -22.0% | -23.6% | -7.05 | 158x | -4.5 / -12.8 / -6.3 | -9.8 / -13.8 | 37 | FAIL. Gross about -1%; costs 21%. |
| 5 | C7 trend-filtered basket. Avoid deleveraging drawdowns. | Long 1x when the equal-weight index is above its 60-bar EMA, else flat | +22.7% | -14.4% | 2.02 | 45x | -6.8 / +16.7 / +12.8 | -12.9 / +40.8 | 44 | FAIL. Worse than the basket in both halves; timing subtracts value. |
| 6 | C9 capitulation rebound. Buy forced liquidations. | Bar below -2.5 sigma with volume above 2x its 42-bar mean; long 1.5 for 6 bars | +4.0% | -3.4% | 1.60 | 8x | -1.1 / -1.8 / +7.0 | -1.9 / +6.0 | 78 | FAIL. 17 events, and LTC alone made +5.6% while every other ticker was flat or slightly negative. |
| 7 | C10 Donchian breakout, long/short. Stop and hedging flows at range extremes. | 60-bar entry, 30-bar exit, ±1 | +5.9% | -16.2% | 0.81 | 10x | -2.2 / +15.0 / -5.9 | -3.3 / +9.6 | 35 | No skill shown. Cheap (costs 1.2%), but the profit is August only. |
| 8 | C11 betting against beta, static. Lottery demand for alts. | BTC and ETH +2, the four alts -1 | -5.4% | -13.2% | -1.24 | 1x | +4.8 / -1.0 / -8.8 | +3.1 / -8.4 | 39 | FAIL. A single regime bet with one observation. |
| 9 | C6 volatility-targeted long basket. Volatility clusters. | 40% annual target, 42-bar vol, cap 2 | +58.5% | -10.5% | 3.81 | 6x | -1.2 / +37.7 / +16.6 | +1.0 / +56.8 | 37 | FAIL as a finding. It is the basket with a slightly lower Sharpe; pure beta. |
| 10 | C4b, a fix of trial 3: the same momentum with hysteresis to cut turnover. | Enter on rank top/bottom 2, exit on leaving top/bottom 3 | +2.6% | -7.4% | 0.69 | 57x | +0.4 / +3.0 / -0.8 | +0.6 / +2.0 | 81 | Not significant. XRP -9.4 and SOL +8.4 dominate; 6.8% cost a quarter is too much for an unproven edge. |
| 11 | Stability check of trial 7, faster. | 40 / 20 | +6.8% | -18.2% | 0.89 | 14x | -2.9 / +17.9 / -6.8 | -3.6 / +10.8 | 55 | Same profile as trial 7. |
| 12 | Stability check of trial 7, slower. | 90 / 45 | +12.1% | -8.5% | 1.50 | 6x | -2.5 / +15.8 / -0.7 | -2.7 / +15.3 | 56 | Same profile. Deliberately not selected despite the best numbers. |

Candidates not run, so no trial was spent:

- **C2 funding-crowding timing.** The pre-set threshold (7-day funding above 1e-4 per bar) is met on only 0.36% of ticker-bars. The rule would be the basket, so it is untestable here.
- **C5 one-day cross-sectional reversal.** The 3-day version in trial 4 already had 158x turnover and zero gross edge; a 1-day version would cost more than 40% a quarter.
- **C8 BTC lead-lag.** About 110x turnover by arithmetic; it needs more than 24 bp of average continuation per event, which is implausible.
- **C12 carry plus momentum composite.** One component had negative gross and the other was insignificant.

## What the evidence says

- **Nothing beat its own placebo.** The best percentiles were 89 (trial 3, negative after costs) and 81 (trial 10). Across 12 trials, one or two such readings are expected by chance.
- **Costs dominate.** Every rule that re-ranks or flips on a 1-to-7-day horizon turned over 57x to 158x a quarter, which is 7% to 21% of equity in costs. No gross effect was near that size.
- **The trend rules made money only in August**, the one strongly trending month, and lost in July and September. This holds for trials 2, 5, 7, 11, 12 and for the reference trend engine. That is one episode, not a sample.
- **The long rules are beta.** Trials 5 and 9 did no better than randomly shifted versions of themselves.

## Chosen rule and why

The frozen rule is trial 7: Donchian 60/30 breakout, long/short, ±1 weight per contract, so gross exposure never exceeds 1x equity. It is labelled **"no robust edge found"**.

- **Mechanism.** Slow trend-following: under-reaction, and stop or liquidation flows once a 10-day range breaks.
- **Low certain cost.** It turned over about 10x in the quarter, roughly 1.2% of equity in costs, the lowest of the long/short rules tested. If the edge is zero, it loses little.
- **Not structurally long.** It is symmetric and can profit from a sustained fall. In the design period it was long 46% of the time, short 17% and flat 37%.
- **No tuning.** It has two parameters, kept at the pre-registered values. The neighbours 40/20 and 90/45 give the same sign and monthly profile (+6.8% and +12.1%), so the result is not a parameter spike. I did not switch to the better-looking 90/45.
- **Against the references on the design period.** It returned +5.9% with a -16.2% drawdown; the trend engine at 2x returned +2.8% with -35.5%. It is far below the basket (+61%), as any rule that is not simply long must be in this period.

## Known weaknesses

- **No evidence of skill.** Placebo percentile is 35. The design profit is explained by its average net long exposure (+0.29) in a rising market.
- **One month.** All profit is from August (+15.0%); July was -2.2% and September -5.9%. H1 was -3.3% and H2 +9.6%.
- **Whipsaw.** It loses in range-bound markets. LTC had 14 position changes, XRP's gross contribution was -3.7%, and LINK and SOL carry most of the gain.
- **Few bets.** There were 6 to 14 position changes per ticker, the six contracts are about 0.66 correlated, and the whole sample is one three-month regime. Statistical power is close to nil.
- **Simulator gap.** The bar-level simulator fills at the bar close; the real one fills at the next minute's open. For a breakout rule that slippage is small but slightly adverse.
- **Warm-up.** The rule is flat for the first 60 bars (10 days) of whatever history it is given.

## Honest out-of-sample expectation

- **Expected net effect: about zero.** My central guess is a Sharpe between 0 and 0.5, with a cost drag of roughly 1% to 1.5% a quarter.
- **Range.** For a quarter, roughly -12% to +15%, with drawdowns of 10% to 20%.
- **When it pays.** It should make money only if the unseen period has a sustained directional move, up or down, lasting several weeks. It should lose moderately in a choppy range.
- **Against the judge's comparisons.** I do not expect it to beat random weights of equal turnover with any reliability. I expect it to be less bad than the 2x trend engine in adverse periods, simply because it is smaller and slower. It will trail the basket if the market keeps rising and beat it if the market falls.
- **Bottom line.** The data and cost model do not support any tradable edge among the mechanisms tested.
