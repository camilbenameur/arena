# Trial log written by the model (verbatim)

# Trials log: verdict "NO ROBUST EDGE FOUND"

None of the candidates passed my own checks. The frozen rule (T5, betting against beta) is the most defensible simple rule I tested, not a finding. Its expected out-of-sample return after costs is about zero.

## Protocol

- **Pre-registration:** nine candidates (C1–C9) with mechanisms were written down before any data was opened.
- **Trials:** 12 of the 15 allowed were used; every variant I evaluated is listed below. The remaining 3 were deliberately left unspent, because nothing justified more search.
- **Parameters:** all were set a priori from the economics (horizons of 3, 7, 10 and 15 days); none was optimised.
- **Scoring:** every trial was scored with `sandbox_backtest.simulate` on the full design period. Half-period, monthly and per-ticker figures come from a replica of that simulator and are summed simple P&L, in % of equity.
- **Time split:** H1 is bars 1–276 (1 Jul to mid-Aug) and H2 is bars 277–552.
- **Verification:** the frozen file was re-run once to confirm it reproduces T5 exactly (+10.22%). That is the same variant, not a new trial. A truncation check on 21 dates gave 0 causality mismatches.

## All trials

Ticker abbreviations in the last column: B = BTC, E = ETH, S = SOL, X = XRP, L = LTC, K = LINK.

| # | Idea and rationale | Parameters | Return | Max DD | Sharpe | Turnover | Cost | H1 / H2 | Jul / Aug / Sep | Per ticker | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 | C1 slow time-series trend, long/short. Under-reaction and liquidation cascades. | Sign of 60-bar return, ±1, daily decision | −10.7% | −20.6% | −0.96 | 26.6x | 3.4% | −10.7 / +0.8 | −10.7 / +10.1 / −9.4 | B −2.4, E −5.8, S +4.9, X −4.2, L −3.4, K +4.5 | FAIL. Loses before costs; whipsawed in two of three months. |
| T2 | C2 cross-sectional momentum, market neutral. Flow rotation persists for days. | 42-bar return, long top 2 / short bottom 2, daily | +0.0% | −6.5% | 0.06 | 28.8x | 3.4% | +1.8 / −1.6 | +0.7 / +1.0 / −1.5 | B −0.3, E +5.6, S +1.5, X −9.8, L +2.9, K +3.8 | FAIL. Gross edge of about 3.5% is entirely eaten by costs; sign flips between halves. |
| T3 | C3 cross-sectional funding carry. Be paid by crowded leveraged longs. | 18-bar mean funding, short top 2 / long bottom 2, daily | −11.3% | −14.7% | −3.95 | 38.9x | 5.0% | −4.6 / −7.2 | −3.7 / −8.0 / −0.1 | B +0.8, E −0.5, S −3.1, X −10.1, L +5.2, K +0.9 | FAIL. Funding collected was only +0.14%; price P&L had the wrong sign. |
| T4 | C4 residual reversal. Liquidity provision against idiosyncratic flow. | 18-bar return, fade top 2 / bottom 2, daily | −9.1% | −10.5% | −4.28 | 46.6x | 5.8% | −3.9 / −5.5 | −1.5 / −3.7 / −4.2 | B +0.1, E −0.1, S −1.6, X +2.4, L −3.6, K −0.8 | FAIL. Negative before costs, and costs are twice the gross loss. |
| T5 | C5 betting against beta. Leverage-constrained buyers overpay for high-beta alts. | 90-bar beta to the equal-weight basket, long 3 lowest / short 3 highest, size 1/beta, weekly | +10.2% | −6.6% | 2.83 | 4.7x | 0.55% | −5.7 / +15.6 | −1.5 / +2.5 / +8.9 | B +5.3, E −2.9, S −6.0, X +5.7, L +11.6, K −3.2 | NOT ROBUST. Stable to lookback, but H1 is negative and it is −1.1% without LTC. |
| T6 | C6 Donchian breakout, long/short. Stop and liquidation clusters beyond range extremes. | 60-bar channel, exit at mid-channel | +6.3% | −15.7% | 0.86 | 17.9x | 2.2% | −5.8 / +13.1 | −4.8 / +15.4 / −3.3 | B −1.0, E −0.4, S +4.2, X −0.4, L +1.8, K +5.3 | FAIL. One month (August) makes all the profit; the same profile as the reference trend engine. |
| T7 | C7 long basket with trend filter. Avoid leverage-unwind regimes. | Basket index above its 60-bar EMA means long 1x, else flat, daily | +26.4% | −10.5% | 2.27 | 17.2x | 2.0% | −9.2 / +34.4 | −7.3 / +22.8 / +9.7 | B +3.1, E +4.2, S +4.7, X +4.1, L +5.4, K +5.7 | FAIL. Pure beta, and worse than the basket (+61%, Sharpe 4.05) on every measure. |
| T8 | C8 momentum plus carry rank combination. | 42-bar momentum rank minus 18-bar funding rank, top 2 / bottom 2, daily | −5.5% | −10.1% | −1.78 | 43.2x | 5.3% | −0.1 / −5.5 | −0.8 / −2.2 / −2.6 | B −1.0, E +2.8, S −1.7, X −7.3, L +3.1, K +3.9 | FAIL. |
| T9 | C9 funding-crowding tilt on a long basket. Extreme funding precedes long squeezes. | Long 1 unless 18-bar funding is above its own trailing 90-bar 80th percentile, daily | +31.2% | −8.7% | 3.25 | 16.1x | 1.8% | +0.5 / +28.0 | −0.9 / +22.8 / +6.6 | B +3.3, E +6.5, S +2.9, X +1.7, L +4.7, K +11.2 | FAIL. Merely long; lower return and Sharpe than the basket, so no timing value shown. |
| T10 | Stability check of T5. | Beta lookback 60 bars | +7.8% | −5.9% | 2.07 | 5.4x | 0.64% | −4.9 / +12.6 | −1.4 / +4.0 / +5.1 | B +7.7, E −3.5, S −4.2, X +5.8, L +11.6, K −9.0 | Same pattern as T5; −3.8% without LTC. |
| T11 | Stability check of T5. | Beta lookback 120 bars | +7.4% | −5.5% | 2.13 | 3.3x | 0.39% | −4.4 / +11.7 | −0.5 / +2.5 / +5.3 | B +5.4, E −1.4, S −4.7, X +4.7, L +11.1, K −7.3 | Same pattern as T5; −3.3% without LTC. |
| T12 | Slower C2, to test whether lower turnover rescues the gross momentum edge. | 84-bar return, top 2 / bottom 2, weekly | −12.1% | −14.3% | −4.93 | 7.8x | 1.0% | −3.0 / −9.8 | +0.7 / −7.1 / −6.3 | B −1.4, E +0.9, S +1.6, X −6.8, L −0.1, K −6.0 | FAIL. Strongly negative, so the gross edge in T2 was noise. |

## What the checks say

- **Market-neutral, faster signals (T2, T3, T4, T8):** none has a gross edge that survives 24 bp per round trip. They trade 29–47x equity per quarter, which costs 3.4–5.8%, against gross edges between −6% and +3.5%.
- **Directional trend (T1, T6):** these reproduce the reference trend engine: a loss in July, a gain in August, nothing in September.
- **Long-biased filters (T7, T9):** both make money only because the period rose 61%, and both underperform the basket in return and Sharpe.
- **Betting against beta (T5, T10, T11):** this is the only family with a positive result that is stable to its parameter.
  - **Parameter stability:** lookbacks of 60, 90 and 120 bars give +7.8%, +10.2% and +7.4%, with drawdowns of 5.5–6.6% and turnover of 3–5x.
  - **Time split fails:** H1 is negative in all three variants (−4.4% to −5.7%, though only about four weeks of H1 are live after warm-up). All the profit is in H2.
  - **One ticker, one month:** LTC contributes about +11.5%, and LTC rose 37% in September while it sat in the long, low-beta leg. Without LTC the three variants return −1.1%, −3.8% and −3.3%.
  - **Not fully market neutral:** average net exposure was +0.21x equity (gross 1.06x), because trailing betas are noisy and the long leg is sized up by 1/beta. In a +61% market that residual long is worth a few percent by itself.
  - **Tiny sample:** about 11 weekly rebalances and 20 trades.

## Chosen rule and why

T5 is frozen exactly as tested, labelled **"no robust edge found"**. I chose it as the least bad option:

- **Mechanism:** it has a documented one (leverage-constrained demand for high-beta coins) that does not depend on market direction.
- **Parameter:** its one material parameter was set a priori (15 days), and the result is insensitive to it.
- **Costs:** it trades about 5x equity per quarter, so costs are roughly 0.5% and funding is negligible. Costs cannot be what kills it.
- **Risk:** it is modest: about 1x gross, near beta-neutral, with a design drawdown of −6.6%.

## Known weaknesses

- The design-period profit is essentially a single LTC rally in a single month, and the first half lost money.
- The rule ran a small net long through a strong up-market, which flatters the result.
- The beta ranking of six coins over 90 bars is noisy; SOL, XRP, LINK, ETH and LTC all switched sides at least once in the weekly rebalances. Much of the P&L is therefore idiosyncratic coin risk rather than a beta premium.
- An alt-led rally in which the high-beta coins outperform by more than their beta will lose money.
- Warm-up is 90 bars plus the wait for the next Monday 00:00 UTC bar, so if the rule is given only new data it stays flat for the first 15–21 days.
- Three months, one regime and six assets give very low statistical power. With 12 trials, a best in-sample Sharpe near 2.8 is well within what luck produces.

## Honest out-of-sample expectation

- **Return:** about 0% per quarter after costs, with a plausible range of roughly ±8–10% and a drawdown of 5–10%.
- **Versus random weights at the same turnover:** I do not expect it to beat them reliably.
- **Versus the basket:** it will lag badly if the market keeps rising, and it is not a hedge that reliably pays if the market falls.
- **Versus the 2x trend engine:** it may look better on drawdown simply because it carries far less risk and turnover. That would be a statement about risk, not about edge.
- **How to read the result:** treat any out-of-sample profit as unproven until it shows up across several coins and periods.
