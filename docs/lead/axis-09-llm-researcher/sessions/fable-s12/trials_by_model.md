# Trial log written by the model (verbatim)

# Verdict: NO ROBUST EDGE FOUND

None of the candidates survived my own checks. The frozen rule is the most defensible simple fallback, not a discovery: a slow long/short breakout trend rule at half size, which made +0.4% on the design period (Sharpe 0.21) and lost money in the September confirmation month.

## Protocol

- **Pre-registration:** ten candidates (C1–C10) were written down with their mechanisms before any data or result was looked at.
- **Trials:** 11 variants were evaluated, out of the 15 allowed. Every one is listed below. Each was run exactly once, with parameters fixed in advance from the economics and no parameter search.
- **Before the trials:** I ran one descriptive pass (per-ticker returns, volatility, funding levels, correlations). It tested no rule.
- **Scoring:** all trials were scored with `sandbox_backtest.simulate`, so the numbers are bar-level approximations of the real judge.
- **Time split:** selection on July–August, confirmation on September. I also report two halves (1 July–15 August and 16 August–30 September).
- **Not run:**
  - C6 (funding-crowding contrarian) was not run. Funding averaged 0.1–0.3 bp per bar (2–7% annualised), which is not a crowded market, so there were too few episodes to learn anything.
  - C10 (carry + momentum composite) was not run. Its precondition, that both components show something on their own, failed.
- **Not done:** I did not compare any rule with random weights of equal turnover.

## Trial log

Returns are after costs. Cost is the fee and slippage drag over the full period.

| # | Idea | Rationale | Parameters | Full: return / Sharpe / max DD / turnover | Jul–Aug | Sep | Cost | Verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | C1 cross-sectional funding carry | Leveraged longs pay for balance sheet | 42-bar mean funding, long 2 lowest / short 2 highest, ±1, daily rebalance | −6.7% / −2.57 / −10.7% / 17x | −10.4% | +3.8% | 2.0% | **Fail.** Funding earned was only +0.22% in three months, a tenth of the cost. |
| 2 | C2 cross-sectional momentum | Slow diffusion of flows among alts | 84-bar return, long 2 / short 2, daily | −3.1% / −1.04 / −8.0% / 20x | +1.2% | −4.2% | 2.4% | **Fail.** Not confirmed in September. |
| 3 | C3 cross-sectional 1-day reversal | Liquidity provision | 6-bar return, long 2 losers / short 2 winners, daily | −14.5% / −6.34 / −16.3% / 71x | −10.9% | −4.0% | 8.5% | **Fail.** Negative even before costs; costs make it worse. |
| 4 | C4 slow breakout trend, long/short | Under-reaction and liquidation cascades | Enter on 60-bar extreme, exit on 30-bar opposite extreme, 50% vol target per coin | −1.3% / 0.08 / −20.9% / 22x | +9.7% | −10.1% | 2.7% | **Fail.** Not confirmed in September. Monthly: −5.5, +16.1, −10.0. |
| 5 | C5 basket beta timing | Time-series momentum and volatility clustering | Long all six at weight 1 when basket is above its 60-bar average, else flat | +16.6% / 1.67 / −14.7% / 38x | +6.7% | +9.3% | 4.6% | **Fail.** It is long beta with negative timing value: average exposure was 0.58, and a constant 0.58x basket would have made about +32%. |
| 6 | C7 capitulation reversal | Supplying liquidity to forced liquidations | Bar return below −2.5σ and volume above 2x the 60-bar median, then long weight 2 for 6 bars | +7.1% / 1.87 / −4.3% / 13x | −2.3% | +9.6% | 1.6% | **Fail.** 7.0 of the 7.1 points come from LTC, all in September, and the selection period was negative. |
| 7 | C8 residual reversal versus BTC | Alt-specific flows mean-revert | 18-bar relative return, z above 2 to enter, z crossing 0 to exit, ±1, BTC hedge | −3.8% / −2.29 / −5.5% / 11x | −3.1% | −0.8% | 1.3% | **Fail.** |
| 8 | C9 betting against beta | Leverage-constrained buyers overpay for alts | BTC +2, each alt −0.4, static | −5.7% / −2.79 / −7.1% / 0.7x | −1.7% | −4.0% | 0.1% | **Fail.** Alts outperformed BTC all period. |
| 9 | C4 stability check, faster | As trial 4 | Enter 40 / exit 20, 50% vol target | +8.4% / 0.99 / −16.3% / 31x | +14.3% | −4.3% | 3.7% | Same pattern as trial 4. Monthly: −7.2, +23.1, −5.1. |
| 10 | C4 stability check, slower | As trial 4 | Enter 80 / exit 40, 50% vol target | +6.4% / 0.89 / −14.3% / 16x | +11.1% | −4.4% | 1.9% | Same pattern as trial 4. Monthly: −2.4, +13.8, −4.3. |
| 11 | C4 at half size (**frozen rule**) | As trial 4; smaller because no edge is shown | Enter 60 / exit 30, 25% vol target | +0.4% / 0.21 / −11.0% / 11x | +6.1% | −5.4% | 1.4% | **No robust edge.** Chosen as fallback. Monthly: −2.7, +9.0, −5.3. |

## Time-split results for the trend family

| Trial | Jul–Aug (selection) | Sep (confirmation) | First half | Second half |
|---|---|---|---|---|
| 4 (60/30, full size) | +9.7% | −10.1% | −6.5% | +5.1% |
| 9 (40/20) | +14.3% | −4.3% | −6.6% | +15.5% |
| 10 (80/40) | +11.1% | −4.4% | −5.1% | +11.6% |
| 11 (60/30, half size, frozen) | +6.1% | −5.4% | −3.3% | +3.5% |

- **What the split shows:** the trend rules looked good on July–August (Sharpe 1.5–2.1) and every one of them lost in September. All of the profit is the single August trend; July and September were both losses.
- **Parameter stability:** full-period returns across the three window lengths were −1.3%, +6.4% and +8.4%. That spread is the noise level; none of them is distinguishable from zero.
- **No switching:** I kept the pre-specified 60/30 windows even though both neighbours did better in sample. Moving to a neighbour because it scored higher would be selection on noise.
- **Per ticker (trial 11):** BTC −2.3, ETH −2.2, SOL +2.1, XRP −0.6, LTC +1.2, LINK +2.2 points. No single ticker dominates, and there is no consistent sign either.

## The chosen rule and why

**Rule (trial 11).** For each contract:
- go long when the close reaches a new 10-day (60-bar) closing high;
- go short when it reaches a new 10-day closing low;
- go flat when the close touches the opposite 5-day (30-bar) extreme;
- size the position as 25% annualised volatility divided by the 10-day realised volatility, capped at 2.

Weights ranged from −1.42 to +1.12 in the design period, with average gross exposure of about 0.37x equity.

**Why this one, given that nothing passed:**
- **External prior:** time-series trend has the strongest outside support in crypto of the families I tested. That prior is the main reason for the choice, not the design data.
- **Not contradicted:** it is the only non-beta family the design data does not contradict; it sits at roughly zero. Carry, reversal, residual reversal and betting-against-beta were all clearly negative, and the capitulation result is a one-ticker, one-month artefact.
- **Not merely long:** it is long/short with an average net weight of 0.07x, so it is not a disguised long position.
- **Sizing:** it is half size on purpose. With no demonstrated edge, the −21% drawdown of the full-size version is not justified.
- **Cost drag:** turnover is about 11x equity per quarter, so costs are about 1.4% per quarter. That is lower turnover than the reference trend engine at 1x (24x).

**Mechanical checks passed:**
- It reproduces trial 11 exactly.
- Recomputing on truncated data gave the identical row at each of 80 truncation points.
- It returns no NaN, tolerates shuffled input rows, and runs on a later-starting sample.

## Known weaknesses

- **No demonstrated edge.** The in-sample Sharpe is about 0.2, the confirmation month was negative, and three months of six highly correlated contracts (pairwise correlation 0.5–0.85) amount to roughly one independent bet and one trend episode.
- **Whipsaw.** It loses in choppy, range-bound markets (July) and in sharp V-shaped reversals (September, −5.3% while the basket rose 18.9%).
- **Will trail a rally.** In a steadily rising market it will lag the buy-and-hold basket badly; it made +0.4% against the basket's +61% in the design period.
- **Close relative of the benchmark.** It is a slower, smaller cousin of the reference trend engine, so it will be highly correlated with it. It differs mainly in turnover and size, not in information.
- **Path dependence.** Positions depend on where the data starts, and the first 60 bars (10 days) are flat during warm-up.
- **Simulator gap.** All numbers come from the bar-level sandbox, not the minute-level judge.

## Honest out-of-sample expectation

- **Expected return after costs:** roughly zero. On the outside prior alone, perhaps 0 to +2% per quarter, with certain costs of about 1.4% per quarter already included.
- **Plausible range:** about −10% to +10% per quarter, with drawdowns of around 10%.
- **By regime:** it should make money only if the unseen period contains a sustained multi-week move in either direction, and should lose a few percent in a range-bound or sharply reversing market.
- **Versus the benchmarks:**
  - Trend engine 2x: similar sign, with roughly a quarter to a third of the swings.
  - Basket: it loses if the market keeps rallying and wins if the market falls persistently.
  - Random weights of equal turnover: I have no evidence that it beats them.
