# Trial log written by the model (verbatim)

# Trial log — verdict: NO ROBUST EDGE FOUND

None of the 11 variants I tested holds up under my own checks. The frozen rule is the most defensible simple one (trial 8), handed back as a low-risk placeholder, not as a finding. I expect it to return roughly zero after costs out of sample.

## Protocol

- **Pre-registration:** 15 candidate rules (C1–C15) with mechanisms were written down before any data was loaded. Parameters were set from the economics, not by search.
- **Trials used:** 11 of 15. Every `simulate` evaluation of a candidate is listed below.
- **Uncounted runs, disclosed:**
  - One calibration run of the given reference basket (sandbox +59.1% versus the stated +61.2%, so the sandbox is close). It is not a candidate; if it is counted, the total is 12.
  - The first call of C12 crashed on a shape error before producing any result. The code was fixed without changing the rule and run once, as trial 8.
  - The frozen file was checked to give the same weights as trial 8 (maximum difference 2e-15). It was not re-scored.
- **Descriptive statistics looked at (not signals):** annualised volatility per ticker (BTC 35% to XRP 63%), mean funding (2–7% a year on every ticker), and the correlation matrix (0.5–0.85).
- **Time split:** A = 1 Jul to 15 Aug, B = 16 Aug to 30 Sep. Rules were computed on the full history and scored on each part separately.
- **Cost:** approximated as turnover × 12 bp.

## Trials

Returns are in % of equity. "Turn" is traded notional as a multiple of equity.

| # | Idea and parameters | Rationale (pre-registered) | Full: return / maxDD / Sharpe / turn / cost | Split A / B | Months Jul / Aug / Sep | Verdict |
|---|---|---|---|---|---|---|
| 1 | C1 slow time-series trend: sign of 60-bar return, inverse-vol sized, daily rebalance | Slow information diffusion, liquidation cascades | −15.4 / −27.6 / −1.36 / 30x / 3.7 | −11.3 / −4.6 | −10.0 / +12.9 / −16.1 | FAIL. Whipsaw; same character as the reference trend engine. |
| 2 | C2 cross-sectional momentum: 42-bar return, long top 2 / short bottom 2, daily rebalance | Flow chasing, slow rotation between alts | +0.7 / −6.2 / 0.33 / 30x / 3.6 | +0.8 / 0.0 | +0.1 / +3.1 / −2.3 | FAIL. Gross about +4% is eaten by costs; ETH +6.8 and XRP −7.0 cancel. |
| 3 | C3 cross-sectional funding carry: 18-bar mean funding, long 2 lowest / short 2 highest, daily | Leveraged longs pay for balance sheet | −13.6 / −14.5 / −5.13 / 39x / 4.7 | −4.9 / −9.2 | −4.0 / −7.5 / −3.0 | FAIL, consistently. Funding spreads are too small to pay for any rebalancing, and high-funding contracts kept outperforming. |
| 4 | C4 long basket, flat when 3-day basket funding is above its trailing 30-day 75th percentile | Crowded longs raise liquidation risk | +17.2 / −10.1 / 2.12 / 25x / 3.0 | +3.1 / +13.7 | +2.4 / +16.3 / −2.1 | FAIL. Pure beta: average exposure 0.64 × basket would be about +38%, so the timing lost about 20 points. |
| 5 | C6 liquidation-flush reversal: bar below −2.5σ with volume above 2× median, long 2.0 for 6 bars | Forced sellers pay for immediacy | +6.8 / −3.4 / 1.83 / 18x / 2.2 | −1.4 / +8.2 | −1.3 / −1.4 / +9.7 | FAIL. LTC contributes +7.2 of +6.8, all in September: one ticker, one month. |
| 6 | C8 long basket only when BTC is above its 60-bar SMA, daily | Avoid de-leveraging regimes | +22.6 / −10.1 / 2.14 / 16x / 2.0 | −8.4 / +33.9 | −8.1 / +22.4 / +8.4 | FAIL. Pure beta: exposure 0.53 × basket would be about +31%; negative timing value; lost in A while the basket gained 7.9. |
| 7 | C10 volume-confirmed breakout: 30-bar high/low with volume above 1.5× median, exit on 15-bar opposite extreme | Stop clusters, real flow | +6.2 / −15.5 / 0.81 / 18x / 2.1 | −6.6 / +13.8 | −4.9 / +19.1 / −6.0 | FAIL. One month (August), drawdown 2.5× the return. |
| 8 | **C12 betting against beta: 84-bar vol, long 2 lowest / short 2 highest, each leg sized median vol / own vol, weekly rebalance** | Leverage-seeking traders overpay for high-beta alts | **+1.6 / −4.1 / 0.73 / 3.3x / 0.4** | **−3.4 / +6.3** | −1.0 / −0.8 / +3.6 | NOT SIGNIFICANT (t about 0.4). Split not confirmed. Bounded risk, lowest cost. |
| 9 | C2w: trial 2 with weekly rebalance (cost-motivated variant) | Same as C2; a 7-day signal should not need daily trading | −9.5 / −13.5 / −3.90 / 11x / 1.3 | −2.4 / −7.6 | +0.8 / −6.5 / −4.1 | FAIL. The sign flips with rebalance frequency, so trial 2 was noise. |
| 10 | C12 stability, vol window 42 | Same as C12 | +2.8 / −3.7 / 1.26 / 5.9x / 0.7 | −2.2 / +5.5 | −2.0 / +2.8 / +2.0 | Same character as trial 8. |
| 11 | C12 stability, vol window 126 | Same as C12 | −0.2 / −4.5 / −0.17 / 2.0x / 0.2 | −2.0 / +2.3 | +0.2 / −2.0 / +1.3 | About zero; sign not stable. |

**Per-ticker contribution, trial 8:** BTC +5.3, ETH +0.6, SOL −4.7, XRP +0.2, LTC +5.1, LINK −4.5. Gains on the long legs are offset by losses on the short alts.

**Not run (budget and priors):**
- C5 BTC lead-lag and C11 one-day reversal: daily or faster turnover against 24 bp cannot plausibly survive.
- C7 vol-managed basket and C14 tilted basket: merely long.
- C9 residual momentum and C13 momentum-plus-carry composite: their components failed in trials 2, 3 and 9.

**Observation not pursued:** the sign-flipped C3 (long high funding) would have been roughly +4% after costs. Flipping a sign after seeing the result, with no pre-registered mechanism, is data mining, so it was not tested or used.

## What the design period says

1. **No market-neutral signal survives.** Momentum, carry, reversal-on-flush and low-vol all sit within noise. Three months gives a standard error of about 2 Sharpe units, and nothing reached t = 1 consistently in both halves.
2. **Every "good-looking" result is beta.** Trials 4 and 6 have Sharpe around 2.1 only because they are long 50–65% of the time in a +59% quarter. Against their own average exposure, the timing destroyed value.
3. **Cost is the only reliable quantity.** Daily-rebalanced rules paid 2–5% a quarter, which is larger than any gross effect I measured.

## Chosen rule: trial 8 (C12), at its pre-registered parameters

I chose trial 8 at the 84-bar window I wrote down beforehand, not the better-looking 42-bar neighbour. Reasons, none of which is "it made money":

- **Cheapest:** 3.3x turnover, about 0.4% cost per quarter.
- **Not a disguised long:** daily beta to the basket is 0.03 (correlation 0.16); net exposure is about +0.13× equity and gross about 0.57×.
- **Bounded:** maximum drawdown was 4–4.5% across all three windows.
- **Mechanism has support outside this sample:** leverage-constrained demand for high-beta assets is documented across asset classes.
- **Mechanics:** only two real parameters (vol window, legs per side). It passed a truncation causality check at about 80 bars with zero difference, and gives the same output on shuffled rows, string timestamps and a later start date. There are no NaNs and weights stay within [−0.99, 1.84].

## Known weaknesses

- **No statistical evidence:** +1.6% in three months is t about 0.4; half A was negative for all three windows and half B positive; the sign flips at the 126-bar window.
- **Alt-season risk:** it is structurally short the most volatile alts (XRP and LINK most weeks) and long BTC plus whichever of ETH, LTC, SOL or XRP is calmest that week. A sharp alt squeeze or a single-name spike on a short leg hurts, with no stop.
- **Funding drag:** the long leg (BTC, ETH) paid the highest funding in this sample, a small negative carry that is included in the results.
- **Slow to react:** weekly rebalancing means up to 7 days of stale positions. Warm-up is 14 days plus the wait for the next Monday 00:00 UTC, so it is flat for the first 2–3 weeks of any new sample.
- **Simulator gap:** the bar-level sandbox is 2 points off the stated minute-level basket figure, so small numbers like these are within simulator error.

## Honest out-of-sample expectation

- **Return:** about 0% a quarter after costs. My prior Sharpe is 0 to 0.3, which is +0 to +0.5% a quarter gross against about 0.4% cost, with a plausible range of roughly ±5% and drawdown of 3–6%.
- **Versus random weights at the same turnover:** I expect it to be indistinguishable.
- **Versus the basket:** it will lag in a continued rally and beat it in a sell-off, simply because it carries almost no market exposure.
- **Versus the 2x trend engine:** mainly much lower risk and cost; it will lag in a strongly trending quarter.
- **Bottom line:** the design period contains no rule I would call an edge.
