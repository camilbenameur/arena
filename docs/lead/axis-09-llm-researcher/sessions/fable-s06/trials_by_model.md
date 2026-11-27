# Trial log written by the model (verbatim)

# Trial log: verdict "NO ROBUST EDGE FOUND"

None of the 11 pre-registered candidates showed an edge that survives costs, the time split and the concentration checks. The frozen rule (T11) is the most defensible simple fallback: a long/flat market-trend filter with volatility targeting. It is conditional beta, not alpha.

## Protocol
- **Pre-registration:** 11 candidates with mechanisms were written to a file before any return was looked at. Only the CSV header and the helper source had been read.
- **Conventions fixed in advance:**
  - Volatility is the EWMA standard deviation of 4h returns, span 42 bars (7 days), annualised.
  - The risk unit is u_i = clip(target / vol_i, 0, 2), with target 0.60 for T1–T7.
  - "Daily" means the decision is frozen at the 00:00 UTC bar.
- **Time split fixed in advance:** A = first 276 bars (Jul 1 – Aug 15), B = last 276 bars (Aug 16 – Sep 30).
- **Scoring:** every trial was scored with `sandbox_backtest.simulate`.
- **Trials used:** 13 of 15 distinct variants; 2 were left unused on purpose.
- **Not counted as trials:**
  - Descriptive statistics with no signal-to-return content (volatility, correlation, funding scale).
  - Sub-period and per-ticker breakdowns of an already-run variant.
  - The event listing for T8.
- **Rerun:** the first batch crashed on a print-format bug in my reporting code after T1 printed. It was rerun with identical weights and counted once.

**Descriptive facts used:**
- Annualised volatility is 35% for BTC and 48–63% for the others.
- Pairwise 4h correlations are 0.5–0.85, so this is essentially a one-factor market.
- Mean funding is about 0.1–0.3 bp per 4h bar (about 4–7% a year), which is negligible against 24 bp per round trip.

## Trials

| # | Idea | Economic rationale | Parameters | Full: return / max drawdown / Sharpe / turnover | A / B | Jul / Aug / Sep | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | Slow time-series momentum, long/flat, per contract | Under-reaction and leveraged herding; bear legs persist; other side is profit-takers | Long u_i if close > close 84 bars ago | +25.1% / -14.3% / 2.14 / 40x | -9.4% / +38.2% | -7.9 / +27.0 / +5.9 | **Fail.** Gross 30.1% at 0.72 average exposure, against about 32% from exposure alone. Sign flicker cost 4.8%. Loses in A while plain beta gains. |
| 2 | Same, long/short | Tests whether the short leg adds | sign(14d return) × u_i | -1.6% / -20.3% / 0.06 / 70x | -16.7% / +18.2% | -10.9 / +15.9 / -5.3 | **Fail.** Short leg destroys value; cost 9.2%. |
| 3 | Cross-sectional momentum | Flow and attention rotation persists for days | 7d return, +1 top 2 / -1 bottom 2, daily | +0.0% / -6.5% / 0.06 / 29x | +1.9% / -1.8% | +0.7 / +1.1 / -1.6 | **Fail.** Zero; sign flips between halves. |
| 4 | Cross-sectional reversal | Liquidity provision to idiosyncratic liquidation flow | 3d return, long bottom 2 / short top 2, daily | -9.1% / -10.5% / -4.28 / 47x | -4.0% / -5.5% | -1.6 / -3.8 / -4.2 | **Fail.** Negative even before costs (gross -3.7%, cost 5.8%). |
| 5 | Funding crowding, cross-sectional | High funding means crowded levered longs; the short is paid carry plus the unwind | 3d mean funding, short top 2 / long bottom 2, daily | -11.3% / -14.7% / -3.95 / 39x | -4.6% / -7.1% | -3.7 / -8.0 / -0.3 | **Fail.** Gross about -6.6%; carry earned only +0.14%. I did not flip the sign, because that would have no mechanism beyond T3. |
| 6 | Funding time-series | Shorts crowded and paying means squeeze fuel plus paid carry | Long u_i while own 3d mean funding < 0 | +10.1% / -5.6% / 2.29 / 30x | +1.4% / +8.4% | +0.7 / +12.6 / -3.3 | **Fail as alpha.** Average exposure 0.23; gross 13.4% against about 10% from exposure alone. All of it is August. |
| 7 | Volatility-targeted long basket (beta yardstick) | Beta premium and volatility clustering; not a finding by construction | u_i always, target 0.60 | +63.9% / -12.1% / 3.81 / 7x | +2.6% / +60.9% | -0.2 / +36.8 / +18.8 | **Yardstick only.** Pure beta at 1.24x average exposure. Sharpe is no better than the 1x basket (4.05). |
| 8 | Capitulation rebound | Forced liquidations overshoot; liquidity providers are paid | Return < -2.5σ and volume > 2× 42-bar median; long 1.5 for 6 bars | +5.9% / -2.8% / 2.18 / 11x | -0.2% / +6.1% | +0.2 / -1.3 / +7.1 | **Fail.** One trade: LTC on Sep 23 made +24% in a day. The other 22 events average +0.29% a day, below the unconditional daily drift (about 0.55%) and about equal to cost. |
| 9 | Betting against beta | Lottery and leverage-constrained demand overprices high-beta alts | Long BTC, short 5 alts at -0.33, beta-neutral, 30d beta | -4.5% / -5.6% / -2.85 / 0.6x | -0.8% / -4.0% | -0.1 / -1.2 / -3.2 | **Fail.** Alts outran BTC. |
| 10 | BTC lead-lag | Slow diffusion from the price-discovery contract to alts | BTC bar move > 2σ; alts ±1 for 1 bar | +0.8% / -4.4% / 0.47 / 47x | -3.6% / +4.6% | -2.7 / -0.4 / +4.0 | **Fail.** Gross 6.7% against cost 5.8%; halves disagree. |
| 11 | **Basket-level trend, long/flat, with hysteresis (frozen)** | Same mechanism as T1, with the cost problem fixed. One market factor, z-scored 14d basket return, ±0.5σ band. | Lookback 84, z on/off ±0.5, volatility span 42, target 0.50 | **+28.0% / -11.7% / 2.47 / 9.7x** | **-7.0% / +37.6%** | -4.9 / +25.2 / +4.5 | **No edge, chosen as fallback.** Gross 28.2% at 0.65 average exposure, against about 29% from exposure alone, so timing value is about zero. Cost 1.1%, funding -0.7%, 5 state flips. All six tickers contribute 3.5–6.3%. |
| 12 | Perturbation of T11 | Stability check | Lookback 60 (10d) | +23.0% / -12.8% / 2.20 / 16.6x | -8.7% / +35.0% | -8.8 / +28.9 / +4.3 | Same profile, 11 flips. Stable but still no edge. |
| 13 | Perturbation of T11 | Stability check | Lookback 120 (20d) | +27.8% / -10.6% / 2.47 / 9.9x | -5.9% / +35.8% | -7.0 / +27.4 / +5.3 | Same profile. Stable but still no edge. |

**Not run:**
- C11 (trend × funding-crowding filter) was pre-registered as conditional on both C1 and C5 showing something. Neither did.
- Two trials were left unused. Spending them on further variants after ten failures would have been data-mining.

## What the checks say
- **Time split:** no candidate is positive in both halves except T6, which is not better than its own exposure to beta, and T7, which is pure beta.
- **Beta dominates everything.** Each long-biased rule (T1, T6, T11–T13) earns about its average exposure times the basket return. Half A was choppy (the yardstick made +2.6%) and half B was a strong rally (+60.9%). Their "Sharpe above 2" is that rally.
- **Market-neutral ideas** (T3, T4, T5, T9) are zero or negative before or after cost.
- **Costs:** anything above about 30x turnover pays 3.5–9% a quarter, more than any gross effect seen.
- **The only apparent positive anomaly** (T8) is a single trade in a single ticker.

## Chosen rule and why
T11 holds each contract long at clip(0.50 / vol_i, 0, 2) while the market trend state is ON, and is flat otherwise.

- The state is driven by the equal-weight basket's 14-day log return divided by its own EWMA volatility.
- It switches ON above +0.5σ and OFF below -0.5σ, and otherwise keeps the previous state.
- It was **not** chosen for its design return. It underperforms the basket (+28% against +61%) and loses in half A.

It was chosen on prior grounds:
1. Time-series momentum with volatility scaling is the mechanism with the widest support outside this sample.
2. Long/flat keeps the only thing that paid here (beta in up-legs) and bounds the loss in a sustained decline. The long/short leg failed in T2.
3. Parameters were set from economics, not by search:
   - The 14-day horizon was pre-registered.
   - The ±0.5σ band was sized before the run, so that in pure noise a full round trip takes about two weeks.
   - The 0.50 volatility target gives about 1x exposure when ON.
4. Turnover is about 10x a quarter (about 1.1% cost), against 46x for the 2x trend engine.
5. Results are insensitive to lookback (10, 14 and 20 days give +23% to +28%), and no single ticker dominates.

**Mechanical checks:**
- The causality check passed with zero gap on 86 truncation points.
- There are no NaN values and all weights are in [0, 2].
- The output is invariant to row order.
- Warm-up is 84 bars (14 days) of zeros.

## Known weaknesses
- **No demonstrated timing skill.** In-sample timing value is about zero. In the choppy half A it lost 7% while always-long made +2.6%.
- **Whipsaw.** Each false ON/OFF cycle costs roughly 2–5% (entry lag plus about 24 bp on about 1x notional).
- **Long-only.** It will lag the basket in a continuing rally: 0.65 average exposure, a late entry after any dip, and only +4.5% in September against +18.9% for the basket.
- **Slow exit.** It gives back roughly the first 5–10% of a sharp reversal before the 14-day signal turns. A gap crash while ON is fully borne at about 1x.
- **Low power.** One regime, three months, six contracts with 0.5–0.85 correlation: effectively one bet repeated.
- **Warm-up.** If the unseen data does not include the design period, the first 14 days are flat.
- **Simulator.** The bar-level simulator is an approximation. Fills at the next minute's open may differ slightly, but with about 5 flips a quarter this is immaterial.

## Honest out-of-sample expectation
Expected alpha after costs is about 0, with a cost drag of about 1–2% a quarter.

| Unseen regime | Expected behaviour |
|---|---|
| Sustained uptrend | Roughly 0.5–0.7× the basket's return; below the basket; probably above random weights with the same turnover |
| Sustained downtrend | A loss of mid-single digits to about 10%, then flat; much better than the basket; possibly worse than the long/short trend engine |
| Range-bound chop | Minus 5–10% from whipsaws |

- It should carry far less drawdown and turnover than the 2x trend engine.
- I do not expect it to beat random weights with the same turnover for any reason other than the market's direction.
- If the requirement is "evidence of an edge", the correct reading of this study is that none was found.
