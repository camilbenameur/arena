# Trial log written by the model (verbatim)

## Verdict: NO ROBUST EDGE FOUND

The rule I'm handing back is the most defensible simple rule I tested. It is not a proven edge.

## Candidates written down before any test (each with its rationale)

| # | Candidate | Rationale (who is on the other side, why it should survive 24 bp) |
|---|---|---|
| A | Cross-sectional 7-day momentum, market-neutral (long top 2, short bottom 2) | Attention and capital rotate slowly across coins, so retail inflows chase recent winners with a lag. Holding for days keeps turnover low. |
| B | Cross-sectional 1-day reversal | Liquidity provision: a trader who needs to trade now pushes the price too far and it comes back. Risk: the bounce is smaller than 24 bp. |
| C | Funding carry (long the lowest trailing funding, short the highest) | Crowded leveraged longs pay a premium. Funding is persistent, and crowded positions tend to unwind. |
| D | Time-series trend, 20 days, sized by inverse volatility, long/short | Herding and slow reaction to news; well documented in crypto. Daily decisions keep turnover low. |
| E | Basket scaled down when aggregate funding is high | When leverage is crowded, liquidation cascades become more likely. |
| F | Alt residual versus BTC beta, mean reversion over several days | Index and pair arbitrageurs pull deviations back. |
| G | BTC leads alts by one bar | Information reaches BTC first and spreads to alts slowly. |
| H | Funding filter on trend (skip longs when funding is crowded) | Same as C and E. |

E, F, G and H were never tested. B already failed on costs, and G and F are faster versions of the same kind of signal.

## Trial log (every variant evaluated; sandbox `simulate`, 12 bp per side)

H1 and H2 are the first and second halves of the bars, each simulated separately. Per-ticker attribution is gross of costs, in %.

| # | Idea | Params | Return / max DD / Sharpe / turnover | H1 / H2 | Jul / Aug / Sep | Verdict |
|---|---|---|---|---|---|---|
| 1 | A: XS momentum | 7d lookback, ±1, daily rebalance | +0.7% / −6.2% / 0.33 / 30x | +0.8 / 0.0 | +0.1 / +3.1 / −2.3 | Reject. Gross edge about 4%, roughly eaten by costs; ETH +7 and XRP −7 dominate. |
| 2 | B: XS reversal | 1d lookback, daily | −14.5% / −16.3% / −6.3 / 71x | −7.8 / −7.3 | negative every month | Reject. Wrong sign, and costs of about 8.5%. |
| 3 | C: funding carry | 3d funding sum, daily | −13.6% / −14.5% / −5.1 / 39x | −4.9 / −9.2 | negative every month | Reject. High funding marked strength, not crowding, in this regime. I did not flip the sign: that would be a fit after seeing the result. |
| 4 | D: TS trend | 20d sign × min(1, 2%/daily vol over 7d), daily | +9.0% / −12.5% / 1.36 / 16.5x | −3.5 / +13.1 | −2.3 / +13.8 / −2.0 | Weak. All the profit is in August; average net long about 0.21. |
| 5 | D, stability check | 10d lookback | −13.7% / −21.4% / −1.82 / 25.6x | −10.2 / −3.9 | −9.5 / +10.9 / −13.7 | Fails. Very sensitive to lookback. |
| 6 | D, stability check | 30d lookback | +25.2% / −8.0% / 3.26 / 7.9x | +2.6 / +21.0 | 0 (warm-up) / +12.4 / +11.0 | Looks good, but it is long about 90% of the time in an uptrend. Only beta. |
| 7 | (budget slot not used) | – | – | – | – | – |
| 8 | A, cost fix | 7d lookback, weekly rebalance | −9.5% / −13.5% / −3.9 / 10.8x | −2.4 / −7.6 | +0.8 / −6.5 / −4.1 | Reject. XRP −12. |
| 9 | D, ensemble (chosen) | mean of signs at 10/20/30d × the same vol sizing, daily | +9.9% / −10.6% / 1.74 / 11.1x | +0.4 / +9.5 | 0.0 (warm-up) / +11.4 / −2.1 | Most defensible, but no proven edge. |

- There are 9 trial numbers with one unused slot (#7), so 8 variants were actually evaluated.
- Average exposure, as a fraction of equity: T4 net 0.21 and gross 0.62; T6 net 0.33 and gross 0.52; T9 net 0.19 and gross 0.38. Short positions make up 22%, 10% and 16% of ticker-bar slots respectively.
- Basket held at a constant 0.19–0.33 net long would have returned roughly 12–20% over the period. So the trend results match their average beta, and there is no evidence of timing skill.
- The split test as specified (choose on H1, confirm on H2) failed. On H1 the best rule was XS momentum (+0.8%), which then made 0.0% on H2. The trend rules were negative or flat on H1.

## Chosen rule and why

T9: a multi-horizon time-series trend.
- **Signal:** the average of sign(10d), sign(20d) and sign(30d) log return, per contract.
- **Sizing:** multiplied by min(1, 2% / trailing 7-day daily vol).
- **Timing:** decided once per day, at the 00:00 UTC close; weights are at most 1 per contract.

Why this one:
- The parameters come from convention, not from a search: standard 10/20/30-day horizons and a round-number risk target.
- Averaging three horizons removes the extreme lookback sensitivity seen in trials 4–6, where results ran from −14% to +25%.
- It can go short, so it is not merely long.
- Turnover is low, about 11x a quarter, so costs are about 1.3% a quarter.
- It beat the 2x trend engine on the design period (+9.9% vs +2.8%, drawdown −10.6% vs −35.5%) at a quarter of its turnover.

## Known weaknesses

- **Low exposure:** average net long is only about 0.19, so it badly lags the basket in a bull market.
- **No timing evidence:** its design return matches its average beta.
- **One month did all the work:** the profit comes from August; September was −2.1%.
- **Warm-up:** it needs 30 days of history. If the judge passes only the unseen period, the rule is flat for about the first 30 days.
- **Choppy markets:** the 10-day component will whipsaw.
- **Concentration:** XRP lost money; LINK contributed the most, gross +4.1%.

## What to expect out of sample (honestly)

- **Base case:** close to zero alpha. Returns should be roughly 0.2–0.4 times the market's direction over long trends, minus about 1.3% a quarter in costs. Expect roughly −5% to +10% a quarter.
- **Strong trends either way:** expect it to be positive with moderate drawdowns (about 10%).
- **Ranging market:** expect a small loss from whipsaws and costs.
- **Against random weights with the same turnover:** I expect it to win only if the unseen period trends.

I found no market-neutral edge that survives 24 bp round trips in this sample.
