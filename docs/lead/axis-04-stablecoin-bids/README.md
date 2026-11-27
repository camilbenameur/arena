# Axis 04: stablecoin discount bids (Kraken spot)

Protocol: `docs/lead/PLAN-v6.md` section 1; frozen before the control read in `PREREGISTRATION.md`.
Code: `fetch.py` (tape download), `bt.py` (engine and fill model), `design.py` (9 trials), `control.py` (sealed, refuses a second run).
Outputs: `trials.jsonl` (9 design trials with every fill), `control_results.json` (9 control runs). Raw data lives outside git.

## Verdict
Formal PASS on the single pair that survives the fee rule (USDG/USD), but a weak pass: it rests on 8 independent
events in design (25 of the 36 fills come from the single 2025-10-10 crash) and 1 event in control. Treat it as
a plausibility check worth roughly EUR 20-30 a year on a 1,000 portfolio, not as proof. Every other pair in the plan is abandoned by the fee rule.

## Step 0: Kraken fees (official pages)
- Kraken Pro fee page and support article "How do stablecoin/FX fees work?": pairs with a stablecoin as base (USDT/USD), stablecoin
  pairs and fiat/FX pairs (EUR/USD) use a separate schedule, one identical fee for maker and taker: 0.20% / 0.20% at the entry tier.
  These trades do not count toward the 30-day volume, so a 1,000 portfolio never leaves the entry tier.
- USDG/USD: maker 0.00%, taker 0.01%. USDe pairs: 0/0. PYUSD and RLUSD are not named on the page (assumed under the stablecoin schedule).
- Stop rule applied: fee >= 0.20% per side drops the 20-30 bp levels; the fee is then still above 0.10%, so USDT/EUR, USDC/EUR, USDT/USD, USDC/USD
  (and PYUSD, RLUSD) are abandoned. A 50 bp discount minus 20 bp in plus 20 bp out leaves 10 bp before slippage on an exit that is itself an order at par - 5 bp.
  USDG/USD is the only pair kept. Because its fee is about zero, the 20 and 30 bp levels were also kept for it.
- Descriptive only (daily OHLC, last 720 days, no P&L): days with a daily low at or below 0.995 on the USD pairs: USDT 17, USDC 16, PYUSD 30, RLUSD 7 (in 605 days), USDG 21.
  Median daily volume (units): USDT 181M, USDC 54M, PYUSD 73k, RLUSD 59k, USDG 0.8M. EUR-pair counts against EURUSD-implied par are unreliable from daily bars and are not used.

## Data actually obtained
- USDG/USD full tick tape: 1,761,043 raw trade rows (1,409,139 unique) from 2024-11-04 (listing) to 2026-11-27. The 2024-01 start is impossible, the pair did not exist.
  Design = 2024-11-04 -> 2026-03-31, control = 2026-04-01 -> 2026-11-27.
- EURUSD daily OHLC (for EUR conversion), daily OHLC of the other pairs (Kraken returns 720 days at most). No tape was downloaded for the abandoned pairs.
- Fill-model degradation: none for USDG/USD (real tape). Limits: the model cannot see queue priority beyond the 1 s delay and the 3x volume test.

## Results (EUR, 1,000 portfolio, 250 EUR per fill)
Design (fills / net EUR / recovered within 10 days / exits target-cap-hard):
| bid bp | caps 3, 5, 10 days (identical) |
|---|---|
| 20 | 43 / +16.16 / 100% / 43-0-0 |
| 30 | 39 / +24.45 / 100% / 39-0-0 |
| 50 | 36 / +40.70 / 100% / 36-0-0 |

Control (2026-04-01 -> 2026-11-27, read once): 2 fills at every level, both on 2026-10-07 (one event); net +0.75 (20 bp), +1.25 (30 bp), +2.26 (50 bp); no cap or hard exits.
Events: 10 independent clusters at 20/30 bp and 8 at 50 bp in design (fills more than 6 h apart), 1 in control.
Worst fill: no fill lost money (the worst is the smallest gain, +1.13 EUR at 50 bp; lowest tape print after a fill was 0.900, but the target at par - 5 bp filled in seconds-to-minutes, median 30 s, max 38 min).
Caps never mattered: no position reached 3 days, and the 0.97 hard exit never triggered.
Primary (L=50, H=3, tie-break in the addendum): design +40.70 EUR over about 17 months (about 29 EUR a year), control +2.26 EUR.

## Criteria
1. >= 15 design fills: PASS (36).
2. >= 80% recover within 10 days: PASS (100%).
3. Control net positive after fees: PASS (+2.26 EUR; all 9 control runs positive).
4. Worst fill smaller than 4 average gains: PASS, but vacuous (no losing fill occurred; no true depeg is in the sample).
5. Survives the 50 bp level only: PASS (50 bp is positive at every cap in control).

## Caveats
- One event dominates: 2025-10-10 gave 25 of the 36 design fills. Independent evidence is 8 design events and 1 control event.
- No sustained depeg happened on USDG/USD in the window; the tail loss the plan warns about (about 2.5% of the portfolio) is untested here.
- Fills assume the bid is live when a thin-book panic prints; the tape rule (3x size, 3 prints, 1 s delay) ignores queue position and cancelled liquidity, so real fills are likely fewer. The pair is thin (median 0.8M units a day).
- The 9 trials differ only in level and cap; the caps are inert, so there are effectively 3 trials.
- Daily-range stats of all pairs were read before the freeze (disclosed in the preregistration); no USDG/USD P&L was computed before it.
