# Trial log written by the model (verbatim)

# Research log: **NO ROBUST EDGE FOUND**

## Setup
- All trials were scored with `sandbox_backtest.simulate` on the full design CSV (2026-07-01 to 2026-09-30).
- **Time split:** H1 = 2026-07-01 to 08-14, H2 = 08-15 to 09-30. Signals are causal and warm-up comes from earlier bars.
- **Also reported:** results per month and per ticker (that ticker's leg alone).
- **Daily rebalancing:** trials marked "daily" change weights only at the 20:00 UTC bar close and hold them otherwise, to limit costs.
- **Pre-registration:** candidates 1 to 7 were written down, with their rationale, before any result was seen.
- **Count:** 12 trials evaluated, out of a limit of 15.

## Trial log
| # | Idea | Economic rationale | Params | Design result (ret / maxDD / Sharpe / turnover) | H1 / H2 | Months Jul/Aug/Sep | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | XS funding carry (short highest funding, long lowest) | Crowded leveraged longs pay a premium and underperform; you also earn the funding | 3d mean funding, 2x2, ±1, daily | -13.6% / -14.5% / -5.13 / 39x | -4.9 / -9.1 | -4.0 / -7.5 / -3.0 | **Fail.** Consistently wrong sign (5 of 6 tickers) |
| 2 | XS momentum | Attention and flows underreact across alts | 7d return, 2x2, daily | +0.7% / -6.2% / 0.33 / 30x | +0.1 / -0.4 | 0.1 / 3.1 / -2.3 | Fail (about zero) |
| 3 | XS 1-day reversal | Paid for providing liquidity after overreaction | 1d return, 2x2, daily | -14.5% / -16.3% / -6.34 / 71x | -7.0 / -7.1 | -4.9 / -6.2 / -4.0 | Fail. Costs plus wrong sign |
| 4 | TS slow trend, vol-scaled | Slow capital chases trends; fewer trades than the EMA engine | 20d sign, 50% vol target per asset, cap 1.5, daily | +11.4% / -16.4% / 1.34 / 24x | -6.2 / +16.8 | -3.1 / +17.8 / -2.4 | Fail. Made all its money in August |
| 5 | Vol-managed long basket | Vol spikes come from forced deleveraging, which is followed by recovery | 50% vol target on basket, cap 2 | +69.0% / -12.7% / 3.66 / 5x | -0.5 / +67.2 | -2.0 / 42.5 / 17.6 | Reject. This is just leveraged beta, not a finding |
| 6 | XS low-vol (betting against beta) | Leverage-constrained buyers overpay for high-vol coins | 7d vol, 2x2, daily | -5.6% / -7.3% / -2.45 / 15x | -2.2 / -2.6 | -1.6 / -2.3 / -1.9 | Fail |
| 7 | Basket timing by funding | Flat when longs are crowded | Flat if average 3d funding > 4 bp per bar | +47.5% / -9.8% / 3.48 / 1x | -1.1 / +47.0 | -2.1 / 28.5 / 15.9 | Reject. Threshold never binds, so this is just the basket |
| 8 | **XS funding momentum** (mirror of #1). **Ex-post hypothesis** | A persistent perp premium shows aggressive leveraged demand, and that demand flow keeps pushing price ("basis momentum") | 3d mean funding, long top-2, short bottom-2, daily | **+4.25% / -2.7% / 1.46 / 43x** | **-0.3 / +4.5** | 0.5 / 4.4 / -0.4 | Weak. Per ticker: XRP +4.9, SOL +2.7, LTC -4.6 |
| 9 | Same as #8, slower (stability check) | Same | 7d mean funding | +2.3% / -6.9% / 0.90 / 19x | +2.7 / -0.5 | 2.5 / 5.7 / -5.4 | Unstable. The positive half flips |
| 10 | TS trend, faster (stability of #4) | Same as #4 | 10d sign | -19.1% / -27.5% / -1.91 / 35x | -15.7 / -6.0 | -13.8 / 14.5 / -17.6 | Fail. Trend depends heavily on the lookback |
| 11 | TS trend, slower (stability of #4) | Same as #4 | 40d sign (flat during the 40d warm-up) | +42.2% / -9.4% / 3.82 / 6x | +2.3 / +37.1 | 0.0 / 20.6 / 18.4 | Reject. Flat in July, then mostly long in an uptrend, so it is beta |
| 12 | #8 delayed by one extra day (does the signal decay?) | If the edge is real, it should not vanish with a one-day delay | shift 6 bars | -1.4% / -6.9% / -0.41 / 43x | -0.1 / -0.3 | 0.8 / 3.2 / -5.0 | Fail. The signal is fragile and decays fast |
| – | Benchmark: random 2-long/2-short, rotated daily (20 seeds) | Null hypothesis for same-style turnover | – | -10.5% ± 4.8% at about 80x turnover | – | – | Reference only |

## Chosen rule: #8 (frozen exactly as above). Label: no robust edge found
- **Why this rule rather than nothing or trend:**
  - Its mirror (#1) was the most consistent pattern in the data. It was negative in all 3 months and both halves, on 5 of 6 tickers, with Sharpe -5 before flipping.
  - The rule is market-neutral (2 long, 2 short), so it is not just riding the up-trend.
  - It had the smallest drawdown of any candidate (-2.7%), and both lookbacks I tried (3d, 7d) were positive in total.
  - Slow trend (#4/#10/#11) was far too sensitive to its lookback; anything long-only is just beta.
- **Implied economics:**
  - Turnover is about 43x equity per quarter, roughly 5% of equity in costs at 12 bp per side.
  - Design-period gross edge was roughly 9% per quarter, and net +4.25%.
  - Funding is paid on the long leg (high-funding coins) and received on the short leg; on net, this is a small cost.
- **Causality:** a truncation re-run at 15 time points gave 0 mismatches.

## Known weaknesses (serious)
1. **Selection after seeing results.** The direction was picked after #1 failed, so the real number of trials is larger than it looks.
2. **Time split fails.** H1 is about 0 (-0.3%) and the whole profit is in H2 / August.
3. **Fragile timing.** A one-day delay (#12) turns it negative, and the 7d version flips which half is positive.
4. **Ticker concentration.** XRP and SOL carry it, while LTC loses -4.6%.
5. **Costs are large relative to the edge.** Turnover is high, and any decay in the signal makes it a net loser.
6. **Only one regime.** The three months were a single bullish period. In an uptrend, funding momentum may just be a proxy for leveraged-long beta in high-beta alts.

## Expected out-of-sample behaviour (honest)
- **Central expectation:** close to zero gross edge, so after about 4 to 5% per quarter in costs, the likely result is **-5% to +3% per quarter, central guess about -2%**.
- **Risk:** drawdowns are probably small (market-neutral, gross 0.67x) and should be modest.
- **Against the benchmarks:**
  - It should beat random weights with matched turnover, because those pay the same costs with no signal.
  - It is unlikely to match the basket if the market trends up again.
  - It may beat trend-engine 2x on drawdown, but not necessarily on return.
- **Bottom line:** I found no rule I would expect to keep working on unseen data.
