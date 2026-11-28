# Axis 10: the two v5 rules on 2020-2025 Binance history (genuine out of sample)

Research v5 selected the wick rule and checked the trend engine on one year of Kraken data (2025-11 -> 2026-11). This axis runs both,
**frozen and untouched**, on Binance USDT perpetuals (BTC, ETH, SOL, XRP, LTC, LINK), 1-minute klines and funding, **2020-01-01 -> 2025-10-31**,
a period never used to select or tune either rule. Plus always-on BTC+ETH carry and a fixed-weight portfolio.
`PREREGISTRATION.md` (written before any number, file hashes of the frozen code inside) fixes the rules, the metrics and the pass/fail reading.
Scripts re-check the hashes at start.

**Verdicts (as preregistered)**
- **Wick rule: does NOT hold.** Base run negative in 0 of 6 years (wiped out in March 2020, then 5 of 6 years at -95% to -100%); with the +1 minute delay the total is -100%. It trades 10 times more often than on Kraken's year and averages -35 bp per trade.
- **Trend engine at 1x: does NOT hold.** Positive in 3 of 6 years (2020, 2021, 2023), not the 4 required; total -4% over 5.8 years, max drawdown -63%. At 2x: -72%, drawdown -92%.
- **Carry: holds, as a cash substitute.** Positive every year, +7.1% a year, max drawdown -1.0%. (No threshold was preregistered.)
- **Portfolio (equal capital, preregistered): -99%.** The wick sleeve destroys it. Without the wick, trend 1x and carry 50/50 returns +36% (descriptive, post hoc).

## Method

| | |
|---|---|
| Data | Binance USD-M public dumps in `~/dev/_arena-data/axis-05/` (monthly 1m klines, 8h funding), carry on axis 3's `~/dev/_arena-data/axis-03/raw/` |
| Grid | 3,068,640 minutes, 2020-01-01 -> 2025-10-31, `common.py`. Missing minute: flat at the previous close (as `backtest.load`). Before a contract's first candle the price is held flat (no signal possible): XRP trades from 2020-01-06, LTC 2020-01-09, LINK 2020-01-17, SOL 2020-09-14 |
| Gap fill | Binance's monthly dumps are truncated for 2022-02 (from the 26th) and 2022-04 (days 1-2) on SOL, XRP and LTC. Left alone, the flat fill makes a fake +4% to +8% jump when the data resumes, which would trigger a fake wick. The 15 missing daily files were downloaded (the one gap that required a download) into `~/dev/_arena-data/axis-10/gapfill/` |
| Bench | `arena/perp/lab/backtest.py` untouched: next-minute open fill, 7 bp fee + 5 bp slippage per side (24 bp round trip), 5% stop, 10x gross cap, funding at each settlement minute |
| Wick | `shocks_fade-wickS.py` untouched, six contracts together (as v5), one continuous compounding run from 2020-01-01 |
| Trend | `trend.FROZEN`, `scale` 1 and 2, 5% stop (the live council's `stop_pct`), from 2020-01-31 (30-day warm-up as v5) |
| Carry | axis 3 `carry.simulate`, trial 3 (always-on BTC+ETH), "base" costs (0.55% of equity per round trip), 2020-01-01 -> 2025-10-31 |
| Years | 2020, 2021, 2022, 2023, 2024, 2025 (Jan-Oct); 2020 starts 2020-01-31 for trend and portfolio |

Venue difference: Binance USDT-margined prices and funding, not Kraken USD-margined; same underlying coins. **Pipeline check** (`validate_overlap.py`,
run after the main result): the same loader and rule on the v5 year (2025-11-17 -> 2026-10-31) gives +109% (86 trades, 41 bp per trade, 69% wins, DD -41%) against
Kraken's +295% (92 trades, 72 bp, 77%, DD -37%); with +1 minute delay +138% against +173%. Same sign and order of magnitude, so the loader and the rule are not what fails below., so Binance is less favourable than Kraken even in that year (cause not investigated).

## 1. Wick rule, six contracts together

Net bp per trade = price move between fills (slippage included) minus both fees, per unit notional (as axis 1); funding is in the equity figures.

| Variant | Trades | Win % | Mean net bp | Median bp | Total % | Max DD % | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 3664 | 49.6 | -34.7 | -2.3 | -100.0 | -100.0 | -99.9 | -100.0 | -99.0 | -24.1 | -98.0 | -95.1 |
| entry +1 min | 3825 | 48.0 | -38.7 | -15.1 | -100.0 | -100.0 | -100.0 | -100.0 | -99.3 | +49.0 | -97.5 | -98.5 |
| costs 48 bp | 4290 | 41.9 | -66.7 | -52.1 | -100.0 | -100.0 | -100.0 | -100.0 | -99.9 | -76.4 | -99.5 | -98.6 |

Reading of the preregistered continuous run: equity fell from 0.78 to 0.02 between 2020-03-09 and 2020-03-17 (the March 2020 crash: repeated buy-the-drop entries at up to 2x per contract, stops
gapped through), and the bench stops once equity is at or below zero, so every later year is mechanically about -100%. That reading is weak evidence on its own, so a **post-hoc diagnostic** was added
after seeing the ruin: each calendar year restarts at equity 1.0 with fresh rule state (not preregistered, does not change the verdict).

| Fresh-start year, base: return % (trades, mean net bp, win %) | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|
| base | -99.9 (811, -25.8, 54) | -100.0 (1407, -28.7, 51) | -99.0 (490, -33.7, 48) | -24.1 (242, +9.1, 56) | -98.0 (290, -41.2, 50) | -95.1 (250, -46.7, 48) |
| entry +1 min | -100.0 (820, -34.0, 54) | -100.0 (1411, -30.2, 51) | -99.3 (489, -38.4, 46) | **+49.0** (238, +27.4, 58) | -97.5 (293, -39.8, 52) | -98.5 (255, -65.9, 43) |
| costs 48 bp | -100.0 | -100.0 | -99.9 | -76.2 | -99.5 | -98.6 |

Even with a fresh start every year the base is negative in 6 of 6 years, and mean net bp is negative in 5 of 6 (only 2023 is +9 bp). The +1 minute variant is positive in 1 year (2023), negative overall.
The rule fires 250 to 1400 times a year here, against 92 on Kraken's year: on these Binance minutes, 4.5% moves over 5 to 30 minutes are ordinary on the mid-cap coins, as axis 1 found on Kraken's small coins.

**Per contract** (alone at 2x, own targets; trades / win % / mean net bp / total % / max DD %), and base per-year return:

| Contract | base | +1 min | 48 bp | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|
| BTC | 156 / 56 / +9.2 / -0.2 / -39 | 156 / 56 / +22.4 / +49.8 / -42 | 156 / 52 / -15.3 / -53.8 / -59 | -20.8 | +3.6 | +2.5 | +15.4 | +16.1 | -11.4 |
| ETH | 284 / 51 / -27.8 / -88.7 / -94 | 284 / 50 / -24.7 / -86.5 / -94 | 284 / 48 / -50.9 / -97.0 / -98 | +37.8 | -79.4 | -40.5 | +1.5 | -30.8 | -4.9 |
| SOL | 791 / 50 / -22.7 / -99.5 / -100 | 791 / 49 / -20.0 / -99.3 | 791 / 46 / -46.7 / -100 | -14.7 | -84.0 | -82.5 | -43.6 | -47.3 | -35.6 |
| XRP | 742 / 54 / -30.0 / -99.8 / -100 | 742 / 51 / -40.1 / -99.9 | 742 / 50 / -52.9 / -100 | -86.3 | -94.0 | -45.4 | +43.5 | -64.9 | -0.7 |
| LTC | 450 / 55 / -29.0 / -97.0 / -98 | 450 / 53 / -35.4 / -98.2 | 450 / 52 / -52.1 / -99.6 | -37.4 | -86.6 | -17.6 | -8.9 | -62.8 | +29.3 |
| LINK | 647 / 49 / -34.9 / -99.8 / -100 | 647 / 50 / -41.0 / -99.9 | 647 / 46 / -58.7 / -100 | -82.5 | -65.8 | -61.7 | -23.0 | -54.8 | -68.1 |

Only BTC is near break-even (+9 bp, 156 trades in 5.8 years, about 27 a year, -0.2% total with a -39% drawdown, and +50% with a 1 minute delay): the one place the "large-cap liquidation wick"
idea is not contradicted, on few trades and with a drawdown as large as the whole Kraken-year figure. ETH, the second largest, is already negative.

**Concentration.** Top 5 trades = 21% of gross profit (all on LINK, LTC and XRP in Feb-Mar 2020, +360 to +910 bp each). Because the run is ruined, money-weighted year shares are not
meaningful; by trade count, 2020 (811) and 2021 (1408) are 57% of all trades. There is no profitable year to be concentrated in: 2023 is the only positive one, and only with the delay.

## 2. Trend engine (frozen), 1x and 2x, 5% stop

| Scale | Trades | Win % | Mean net bp | Total % | Max DD % | Sharpe | 2020* | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | 1443 | 26.1 | -17.9 | -4.2 | -63.2 | 0.20 | +36.9 | +5.0 | -29.5 | +54.8 | -15.1 | -28.1 |
| 2x | 1470 | 23.9 | -118.3 | -71.6 | -91.9 | 0.16 | +69.7 | -22.3 | -56.2 | +88.6 | -40.5 | -56.2 |

\* 2020-01-31 -> 2020-12-31. Max drawdown inside each year, 1x: -31, -34, -58, -34, -46, -35 (%). Fresh-start years (post hoc) give the same signs (1x: +36.9, +3.3, -28.7, +55.2, -15.1, -27.5).
**1x is positive in 3 of 6 years: the preregistered "holds" threshold (4 of 6) is not met.** Its good years are 2020 and 2023 (2021 is flat); it gives back more than it earns in range-bound and falling years, and over the whole period it is flat to negative with a -63% drawdown. This agrees with v5's own finding that the engine's Kraken
result came from one trend episode.

## 3. Carry (always-on BTC+ETH, axis 3 trial 3, base costs)

| | Total % | Ann. % | Max DD % | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|
| BTC+ETH | +49.5 | +7.1 | -1.0 | +10.9 | +18.7 | +0.6 | +4.0 | +6.6 | +1.9 |
| BTC | +44.5 | +6.5 | -1.5 | +8.1 | +16.3 | +1.7 | +3.9 | +6.4 | +2.2 |
| ETH | +54.2 | +7.7 | -1.3 | +13.7 | +20.7 | -0.4 | +4.0 | +6.8 | +1.7 |

Axis 3's table only starts in 2020-04 and splits at 2024-06, so this is recomputed (axis 3 figures: 2021 +18.7, 2022 +0.6, 2023 +4.0: they match). 94% of months positive. The return follows the funding regime (2021 = 38% of the total);
the last two years are +6.6% and +1.9% (10 months). No threshold was preregistered; it is the only sleeve that is positive every year.

## 4. Portfolio: equal capital, one third each, rebalanced daily (chosen before any result)

Sleeves: wick base (continuous), trend 1x, carry. Window 2020-01-31 -> 2025-10-31 (2,101 days).

| Portfolio | Total % | Max DD % | Sharpe | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|
| **P1 preregistered** (wick + trend 1x + carry) | -99.2 | -99.3 | -0.87 | -57.5 | -79.9 | -63.6 | +27.3 | -57.5 | -49.3 |
| P2 post hoc (wick and trend restarted each year) | -99.1 | -99.3 | -0.87 | -57.5 | -80.0 | -63.5 | +27.3 | -57.5 | -49.1 |
| P3 post hoc, descriptive (no wick: trend 1x + carry, 50/50) | +36.3 | -32.8 | 0.35 | +25.8 | +14.4 | -13.7 | +29.9 | -3.3 | -12.7 |

Preregistered "useful" reading: positive in at least 4 of 6 years and drawdown smaller than the wick alone: **not met** (1 of 6 years positive). Diversification does not rescue a sleeve that loses 95% to 100% a year:
the wick's worst day is -98% and its worst month -99.9%, so a daily-rebalanced third of capital is lost within weeks every year. Even P3 is poor (3 of 6 positive years, -33% drawdown, Sharpe 0.35): carry is too small
to offset a trend sleeve that draws down 30 to 60%.

Correlation of daily returns (continuous series; monthly in brackets): wick-trend -0.03 (+0.11), wick-carry +0.08 (-0.17), trend-carry +0.07 (+0.18). All three are close to uncorrelated, so a
rule that was positive would have diversified well; none of the correlations is a reason to hold a negative sleeve. Restricting to the 748 days with a wick position changes nothing (-0.04, +0.10, +0.07).
Worst month: wick -99.9%, trend 1x -25.4%, carry -0.5%. Worst day: -98.1%, -11.0%, -0.7%.

## Verdict and consequences

- The v5 wick result **does not generalise in time**. On the six contracts' 2020-2025 Binance history the frozen rule loses in every year it can be scored (the one positive cell is 2023 with a 1-minute delay), loses on 5 of 6 contracts, and
  is ruined by the March 2020 crash. Combined with axis 1 (it does not generalise across contracts) and the pipeline check (it does work on Binance in the v5 year: +109%), the evidence is that the Kraken edge
  of 2025-11 -> 2026-11 belongs to that year (the Feb 2026 crash and a wick-friendly regime), not to a stable effect. Treat the live hunter as a lottery ticket, not an engine.
  BTC alone is the only near-neutral contract (+9 bp, 27 trades a year).
- The frozen trend engine is **regime dependent**: 3 good years in 6, negative overall at 1x and badly negative at 2x (-72%, DD -92%). The Trend Council's current gain says little about its expectation.
- Carry is the only sleeve that worked in every year, at a size (+7% over 2020-2025, +2% in 2025) that cannot carry a portfolio.

## Files

`PREREGISTRATION.md` (written first), `common.py` (loader, hashes, helpers), `run_wick.py`, `run_trend.py`, `run_carry.py`, `run_portfolio.py` (run in this order), `validate_overlap.py` (pipeline check), `tables.py`, `results/*.json` and daily
series `results/*.npz`. Data and the 15 gap-fill files stay outside git in `~/dev/_arena-data/axis-10/`.
Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python docs/lead/axis-10-long-history/run_wick.py` (about 20 minutes), `run_trend.py` (3 minutes), `run_carry.py`, `run_portfolio.py`.

## Deviations and caveats (all disclosed)

1. The preregistered continuous wick run is ruined in March 2020; fresh-start-per-year runs (wick, trend) and the P2 and P3 portfolios were added **after seeing that**, labelled post hoc, and do not change any verdict.
2. First wick run was killed after its first result to add the fresh-start diagnostic and a ruin timestamp, then restarted unchanged otherwise; no parameter was touched. A check of the loader found the truncated monthly dumps
   (gap fill above) before any reported number was produced.
3. The 10x gross cap and the bench's "ruin" convention (equity <= 0 stops the run) shape the ruined-year numbers; per-trade mean bp (which does not depend on compounding) is negative in the same years.
4. The 6 years include two partial ones (2020 starts 01-31 for trend, SOL lists in September; 2025 ends 10-31). Years are calendar years, a year with no trade would count as not positive (none occurred).
5. Binance, not Kraken: different prices and funding. The overlap year shows the rule still works there (about 63% lower return than Kraken's), so the venue does not explain a result this negative.

## Corrections from the adversarial checks (lead's note)

- **Ruin mechanics:** the continuous wick equity never reaches zero (1.3e-8 at the end of 2021, 9e-14 at the end of 2025), so the bench's stop at zero never fired. The per-year figures are relative returns on a near-zero equity. The fresh-start years, which restart at 1.0 each year, agree with them to two decimals and are the right evidence. The +49% for 2023 with the 1-minute delay is a return on near-zero equity, not a real gain.
- **Trend funding drag:** funding costs the trend engine 47.9 points at 1x and 103.0 at 2x over the six years, mostly in the long-biased bull phases of 2021 and 2024 on Binance. This does not change the 3-of-6 verdict, but part of the loss is specific to the venue.
- **Venue gap on the v5 year:** on Binance the wick rule gives +109% (41 bp per trade), against +295% (72 bp) on Kraken for the same year. A venue penalty exists, but it cannot explain -34.7 bp per trade over six years.
- **Data:** four multi-coin flat stretches (exchange halts) and one bad ETH tick (2020-03-13) remain in the data. Clamping the bad tick leaves the 2020 result unchanged.
