# Trial log written by the model (verbatim)

# Verdict: NO ROBUST EDGE FOUND

I ran 10 trials out of the 15 allowed, and none passed my checks. The rule handed back (trial 5, "betting against beta") is the most defensible simple candidate, not a validated edge.

All trials were scored with `sandbox_backtest.simulate` on the full design period (FULL), split at the middle bar (H1 = July 1 to about Aug 15, H2 = the rest), per calendar month, and per ticker. In the sandbox, the reference basket scores +59.1%, Sharpe 4.09, H1 +7.9%, H2 +47.3%. The task's stated reference is +61.2%, so the sandbox simulator is close to the judge but not identical.

Before testing, I wrote down these candidates with their mechanisms:
- funding carry
- time-series trend
- cross-sectional momentum
- cross-sectional reversal
- betting against beta (leverage constraints)
- a funding-crowding filter on the basket
- fading liquidation cascades
- short squeezes after negative funding
- volatility-managed exposure

| # | Idea | Economic rationale | Parameters | FULL ret / DD / Sharpe / turnover | H1 / H2 | Months Jul/Aug/Sep | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | Cross-sectional funding carry (long the lowest funding, short the highest) | Leveraged longs pay a premium; whoever receives funding gets paid for supplying leverage | 7-day funding sum, 2 names per side, weekly rebalance | −4.3% / −9.2% / −1.43 / 9x | −2.8 / −1.7 | −1.8 / −7.0 / +4.3 | FAIL. Funding spreads are about 1e-5 per bar, too small; high-funding names kept outperforming |
| 2 | Time-series trend, long/short | Slow information spread, herding, hedging flows | Sign of the 60-bar return, ±1 | −7.0% / −23.2% / −0.53 / 63x | −10.4 / +3.8 | −7.0 / +12.1 / −10.2 | FAIL. Whipsaw and high turnover |
| 3 | Cross-sectional momentum | Slow spread of news across coins | 60-bar return, 2 names per side, daily rebalance | −4.5% / −8.0% / −1.64 / 25x | +1.1 / −5.5 | −0.1 / +0.6 / −4.8 | FAIL |
| 4 | Cross-sectional 1-day reversal | Paid for supplying liquidity against overreaction | 6-bar return, 2 names per side, daily rebalance | −9.6% / −11.3% / −4.03 / 77x | −7.6 / −2.4 | all three negative | FAIL. Costs dominate |
| 5 | **Betting against beta, beta-neutral** | Leverage-constrained traders bid up high-beta alts, so low beta is underpriced | 180-bar beta to the equal-weight market, long 2 lowest at 1/β, short 2 highest at 1/β, weekly | **+4.7% / −4.6% / 1.70 / 2.1x** | **−3.0 / +6.3** | −0.7 / −2.0 / +5.4 | WEAK. Low cost, but H1 negative and the gain is concentrated (BTC long +6.0, LTC +10.1, LINK −6.3) |
| 6 | Basket, flat when aggregate funding is crowded | Crowded leveraged longs come before long-liquidation drops | Flat when 1-day average funding is above the trailing 30-day 80th percentile | +17.1% / −14.4% / 1.95 / 47x | +5.4 / +11.0 | +1.6 / +10.2 / +3.4 | FAIL. Much worse than the plain basket: the filter destroys value |
| 7 | Fade liquidation cascades | Forced liquidations overshoot; liquidity providers are paid to absorb them | \|z\| > 2.5 and volume > 2.5× the 30-day median, fade for 6 bars | −9.8% / −17.2% / −1.68 / 16x | −2.5 / −7.7 | −2.0 / −11.8 / +4.4 | FAIL |
| 8 | Long when a ticker's funding is negative | Crowded shorts lead to short squeezes | 1-day funding sum < 0 means long 1, else flat | +3.0% / −5.5% / 1.04 / 48x | +1.3 / +1.7 | +1.5 / +1.2 / −0.1 | FAIL. Mean next-bar return while in was 6.1 bp, versus 10.2 bp while out, so there is no timing skill; the gain is just long exposure (about 26% of the time) |
| 9 | Volatility-managed basket | Volatility clusters but returns do not scale with it, so exposure scaled by 1/vol should have a better Sharpe | Weight = expanding median vol / 42-bar realized vol, capped at [0, 2] | +39.4% / −9.6% / 3.30 / 4x | −1.8 / +41.3 | −3.9 / +29.3 / +12.4 | FAIL. Worse Sharpe than the basket, and still just long exposure |
| 10 | Robustness check of #5 | Same as #5 | 90-bar beta, rebalance every 18 bars | +3.3% / −3.8% / 1.38 / 5x | −1.9 / +6.4 | +0.6 / −0.4 / +3.4 | Same pattern as #5: H1 negative, BTC/LTC long carries it, LINK short loses |

## Chosen rule and why
I chose trial 5 with its pre-set parameters: a 30-day beta, weekly rebalancing, and 2 names per side.
- **Mechanism:** it has a documented mechanism (leverage constraints) that is not just "being long".
- **Market exposure:** its measured beta to the basket is about 0.04, so it does not depend on the market trending up.
- **Cost:** turnover is very low (about 2x equity, roughly 0.25% in costs over the period).
- **Robustness:** both parameter variants (trials 5 and 10) had the same sign.

It was chosen as the least bad option, not because it passed.

## Known weaknesses
- It lost money in the first half (−3.0%) and in July and August. Almost all the gain is from September.
- The profit is concentrated: long BTC (+6.0) and long LTC (+10.1), partly offset by short LINK (−6.3) and short ETH (−3.3).
- With 6 assets and about 8 weekly rebalances, statistical power is close to zero. A full-period Sharpe of 1.7 over 3 months is consistent with noise.
- Beta-neutral by trailing beta does not mean neutral in a crash, when betas change.
- The net weight is about +1.0 (the long side is levered above 1 because low betas are below 1). This adds funding cost and some exposure if betas are mis-estimated.

## Expected out of sample
I expect a return of about 0% after costs, with a plausible range of roughly −6% to +6% per quarter and a drawdown of around 5%. Costs should be about 0.3% per quarter. I expect it to lose to the basket in any up-trending period. Against random weights with the same (low) turnover, I expect no significant difference.
