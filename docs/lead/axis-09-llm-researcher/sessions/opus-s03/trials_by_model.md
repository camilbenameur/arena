# Trial log written by the model (verbatim)

# Trial log — verdict: **NO ROBUST EDGE FOUND**

**Setup.** Every trial was scored with `sandbox_backtest.simulate` on the full design period, which costs 24 bp per round trip, applies the 0.3-unit trading band and charges funding.
- **Time split:** H1 = 2026-07-01 to 2026-08-14, H2 = 2026-08-15 to 2026-09-30. Weights were computed causally on the full data and then sliced.
- **Count:** 11 rule variants were evaluated, which is all of them; the hard limit was 15.
- **Benchmark:** one random-weights run (200 draws), which is a benchmark and not a rule variant.

## Candidates written down before any results (with mechanism)
- C1 **Cross-sectional funding carry:** short the highest 3-day funding, long the lowest. Crowded leveraged longs overpay for perps, so funding should mean-revert along with price.
- C2 **Cross-sectional momentum (7 days):** information spreads slowly across alts, and herding.
- C3 **Cross-sectional 1-day reversal:** we get paid for providing liquidity to impatient flow.
- C4 **Slow trend, long or flat (above the 20-day average):** trends persist and drawdowns are avoided.
- C5 **Volatility-managed long:** volatility clusters while expected returns don't scale with it (Moreira–Muir).
- C6 **Crowding filter:** hold long only when funding is below its own expanding median, i.e. avoid crowded longs.
- C7 **Fade 2.5-sigma basket shocks for 24 hours:** forced liquidations overshoot.
- C8 **Large caps vs alts, dollar-neutral (betting against beta):** leverage-constrained, lottery-seeking traders overpay for high-beta alts.
- C9 **Donchian breakout 20d/10d, long/short:** the trend-following risk premium, slow so it trades little.
- C10 **Residual reversal vs BTC:** dropped untested, because C3 already showed that short-term reversal loses after costs.

## Trials

| # | Rule and parameters | Full period: ret / maxDD / Sharpe / turnover | H1 | H2 | Months Jul / Aug / Sep | Verdict |
|---|---|---|---|---|---|---|
| 1 | C1 funding carry, 18-bar mean, top/bottom 2, ±1, daily | -13.6% / -14.5% / -5.1 / 39x | -4.9 | -9.1 | -4.0 / -7.5 / -3.0 | Reject: high-funding coins kept outperforming |
| 2 | C2 momentum, 42-bar return, top/bottom 2, daily | +0.7 / -6.2 / 0.3 / 30x | +0.1 | -0.4 | 0.1 / 3.1 / -2.3 | Reject: nothing left after costs; mixed by ticker |
| 3 | C3 reversal, 6-bar return, daily | -14.5 / -16.3 / -6.3 / 71x | -7.0 | -7.1 | all negative | Reject: costs alone are about 8.5%, and it loses before costs too |
| 4 | C4 long/flat, close above 120-bar average, daily | +25.4 / -9.4 / 2.4 / 8x | -4.8 | +30.3 | -4.0 / 22.4 / 6.1 | Reject: just market beta (average net 0.53x), worse than a scaled basket |
| 5 | C6 crowding filter, long only | +13.0 / -7.9 / 2.4 / 22x | +1.6 | +10.0 | 0.6 / 15.3 / -2.9 | Reject: beta at 0.37x exposure, adds nothing over the basket |
| 6 | C7 fade 2.5-sigma 4-hour basket shock, hold 6 bars, symmetric (16 events) | -19.5 / -22.9 / -3.0 / 19x | -2.0 | -17.9 | -2.0 / -19.0 / 1.5 | Reject: shocks continued instead of reversing |
| 7 | C8 BTC/ETH +1 each, other four alts -0.5 each, held constant | -2.6 / -6.7 / -1.2 / 0.7x | +2.1 | -4.1 | 2.4 / -0.5 / -4.4 | Reject: sign flips between halves |
| 8 | C5 volatility-managed long, w = 0.0107 / 42-bar volatility, capped at 2 | +63.4 / -11.0 / 3.8 / 6x | +0.1 | +59.1 | -1.3 / 38.5 / 17.7 | Reject: leveraged basket (about 1.1x), Sharpe below the basket's 4.05 |
| 9 | **C9 Donchian 120/60 bars (20d/10d), ±1** | **+12.3 / -9.7 / 1.5 / 4.6x** | **-1.9** | **+13.3** | -2.2 / 17.7 / -3.1 | Weak: chosen as most defensible, not robust |
| 10 | C9 stability check, 90/45 bars | +11.1 / -9.0 / 1.4 / 5.5x | -3.6 | +14.0 | -2.5 / 15.9 / -2.1 | Same shape as #9 |
| 11 | C9 stability check, 180/90 bars | +19.5 / -9.4 / 2.2 / 2.4x | -0.5 | +18.8 | 0.0 / 11.2 / 6.8 | Same direction; the 30-day warm-up uses up almost all of July |

**Benchmark (not a rule variant).** 200 runs of random long/flat/short weights per ticker, each switching state with probability 1/60 per bar.
- Mean turnover was 7.8x.
- The median return was -1.3%, the 90th percentile +12.7% and the 95th percentile +18.1%.
- Only 11% of random runs reached #9's +12.3%. That is **not significant**, and the random runs had higher turnover than #9.

**Chosen rule: #9, Donchian 20-day / 10-day breakout, long/short, ±1 unit per contract.** It is labelled *no robust edge found*.
- The parameters are the textbook Turtle System-1 values. I did not search for them, and nearby settings (#10, #11) give the same sign and similar size.
- It is long/short and symmetric, so it is not merely long. Average net exposure was +0.32 and average gross 0.48.
- Turnover is very low (4.6x, about 0.55% of equity in costs), so costs can't sink it.
- Every ticker but XRP contributed a small amount: BTC +2.5, ETH +1.9, SOL +5.8, XRP -1.5, LTC +3.4, LINK +0.4.
- On the design data it beat the trend engine at 2x on both return (12.3% vs 2.8%) and drawdown (-9.7% vs -35.5%). It is far below the basket (+61%).

**Known weaknesses.**
1. All of its profit comes from August. It lost in July and September and in H1, so its result is just the August trend.
2. It made only about 13 round trips in total, which gives almost no statistical power.
3. It doesn't beat random weights at its own turnover in any meaningful way.
4. It can't trade during the first 20 days of any series.
5. In choppy markets it bleeds through false breakouts.
6. Its long bias in this sample came from the up-market, not from the rule.

**Expected out of sample.** Expect roughly zero after costs, give or take about 10% over three months. It should make money only if one or more contracts trend strongly in either direction. In a range-bound market expect a small loss (-2% to -5%) from whipsaws. Drawdowns should be about 10%, and costs small (under 1% per quarter). I don't claim an edge.

**Side observation, not exploited.** Trials 1, 3 and 6 all lost because moves *continued* rather than reverted. That hints at short-horizon continuation in this regime. I didn't turn it into a rule, because it came from looking at results and testing it would have been data mining.
