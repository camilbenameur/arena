# Axis 04 preregistration (written 2026-11-27, before the control period was read)

## Step 0 outcome that fixes the universe
Kraken fee pages (kraken.com/pro/fees, support article "How do stablecoin/FX fees work?"): pairs with a stablecoin as
base, stablecoin pairs and fiat/FX pairs pay one identical fee for maker and taker, 0.20% at the entry tier
(0.20% / 0.20%), and these trades do not count toward the 30-day volume, so a 1,000 portfolio never leaves the tier.
USDG/USD has its own schedule: maker 0.00%, taker 0.01%. USDe pairs 0/0. PYUSD and RLUSD are not named on the page.

Plan stop rule: fee >= 0.20% per side -> drop the 20-30 bp levels; fee still > 0.10% after that -> abandon.
Applied: USDT/EUR, USDC/EUR, USDT/USD, USDC/USD (and PYUSD, RLUSD, which fall under the same stablecoin/FX
schedule as far as the page says) are ABANDONED: a 0.20% fee per side exceeds the 0.50% max-discount
capture economics at the plan's own threshold. USDG/USD (fee <= 0.01%) is the only pair that survives the rule and is the
only pair tested. For the abandoned pairs only a descriptive count of daily-low events is reported (no trial, no P&L).
Disclosure: before writing this file I read daily OHLC (last 720 days, including the control window) for min low / max high
of each pair only; no event counts or P&L for USDG/USD were computed.

## Data
Kraken public Trades tape for USDGUSD (listing late 2024) to 2026-11-27, EURUSD daily OHLC for EUR conversion.
Design: tape start -> 2026-03-31 (the 2024-01 start is impossible, the pair did not exist). Control: 2026-04-01 -> 2026-11-27, read once.

## Frozen rule (par = 1.0000, USD pair)
- Size per fill: 25% of a 1,000 EUR portfolio = 250 EUR, converted to USD at the EURUSD daily close of the fill day. One position at a time.
- Resting limit buy at par - L bp. L in {20, 30, 50}. Re-armed when flat.
- Fill model: a bid at price P fills when, counting tape trades with price <= P from 1 s after the order is live, the cumulative
  volume reaches 3x our size inside a window of 3,600 s and comprises at least 3 distinct prints, none of them more than 50%
  of that cumulative volume. Fill price = P. Trades with price <= 0.952 (-480 bp or worse) are discarded as one-lot wicks.
- On fill, a limit sell at par - 5 bp rests; same fill model mirrored (trades >= price, 3x size, 3 prints, 1 s delay).
- Holding cap H in {3, 5, 10} days: then market exit at the next trade price minus 1 bp, taker fee 0.01%.
- Hard exit: if every trade over a continuous 1 h stretch (>= 1 trade) is below 0.97, market exit at the last of them, same costs.
- Fees: maker 0.00%, taker 0.01%.
- Trials: the 9 combinations (L, H). All logged to trials.jsonl including zero-fill ones.
- Recovery: a fill "recovers" if a 1-minute volume-weighted price >= 0.9990 occurs within 10 days after the fill.

## Primary candidate and pass criteria
Primary = the design trial with the highest net P&L among those with >= 15 fills; if none has >= 15 fills, the
default primary is L=30, H=10 (so the control still runs once and is reported, and the verdict is FAIL on criterion 1).
Criteria, all required:
1. >= 15 fills in design (primary trial).
2. >= 80% of design fills recover within 10 days.
3. Control net P&L after fees > 0 (primary trial, EUR on 1,000).
4. Worst single fill loss (design + control) smaller than 4 times the average gain per winning fill.
5. The same rule at L=50 only, taken alone, has positive control net P&L.
Control is run once by control.py, which writes a lock file and refuses to run again.
A pass is a plausibility check, not statistical proof.

## Addendum written after design, before control (2026-11-27)
Design finished: all 9 trials have >= 36 fills, so the primary is the highest-net trial: L=50. The three caps H=3,5,10
tie exactly on design net, so the tie-break is the shortest cap: primary = L=50, H=3. Because the primary is already the 50 bp level, criterion 5
is evaluated on the L=50 trials at each cap (all three must be net positive in control to count as "survives"). All 9 trials are also run on control and reported.
