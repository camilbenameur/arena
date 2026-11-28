# Axis 10: preregistration (written before any number was computed)

Question: do the two rules selected in research v5 on one year of Kraken data (2025-11 -> 2026-11) hold on a long,
never-used history? Binance USDT-perpetual 1-minute klines and funding, 2020-01 -> 2025-10, were not used to select
or tune either rule. **Nothing is retuned. One run per item, all results reported.**

Repository state: commit `479abece474584c1dd80817d7e9290eab4891acf` (HEAD when this file was written).

## 1. Frozen code (sha256)

| Role | File | sha256 |
|---|---|---|
| Wick rule (live "wick hunter") | `docs/research-v5/finalists/shocks_fade-wickS.py` | `a3a3a8fa414423f2800d47d83016589a1a67a7f5c22e483b97e9da346706405c` |
| Trend engine (FROZEN) | `arena/perp/lab/trend.py` | `2fdf8feff9f82b5c54ca8257a064a27c197f1c902ab9aab064d0975948288065` |
| Bench | `arena/perp/lab/backtest.py` | `567035decd5ed989ab33387229864d592b58e54944179722d13cb5a3a190d8bb` |
| Carry simulator | `docs/lead/axis-03-carry/carry.py` | `9b5fb100ec72cbfaa33f833cb1798fbc7b9dd6a3e1a44ee75b88d769efbbb222` |
| Carry rules | `docs/lead/axis-03-carry/strategies.py` | `454e20837d555e6bd021f40fb35cb4d1b5906eb7f04d6fbdfd5de5d4446eb623` |

The scripts of this axis re-check these hashes at start and abort on any mismatch.

## 2. Data and period

- Contracts: BTC, ETH, SOL, XRP, LTC, LINK USDT perpetuals (same six as the Kraken PF_ contracts). Source: Binance
  public dumps in `~/dev/_arena-data/axis-05/` (monthly 1-minute klines, 8-hourly funding). Carry uses axis 3's
  Binance data in `~/dev/_arena-data/axis-03/raw/` (8h prices, funding).
- Period: 2020-01-01 00:00 UTC -> 2025-10-31 23:59 UTC. Nothing after 2025-10-31 is read.
- Calendar years: 2020, 2021, 2022, 2023, 2024, 2025 (Jan-Oct): six "years". 2025 is partial; 2020 is partial for the
  trend engine (30-day warm-up, as in v5: it trades from 2020-01-31) and for SOL (listed 2020-09; before its first
  candle the price is held flat, so no signal is possible).
- Missing minutes: held flat at the previous close (as `backtest.load`). Funding: the Binance rate is applied at its
  settlement minute (rate x position x close), as the bench does for Kraken.
- Venue difference (to be reported): Binance USDT-margined prices and funding, not Kraken USD-margined; same underlying.

## 3. Items

1. **Wick**, exactly as frozen (4.5% log move over 5, 15 or 30 min; opposite side at 2x; 60-min hold; 60-min lock; 5%
   stop; entry at next-minute open), bench costs (7 bp fee + 5 bp slippage per side = 24 bp round trip), six contracts
   traded together (targets computed on the six, as v5), one continuous compounding run from 2020-01-01. Variants:
   base; entry +1 minute (targets shifted one row); costs 48 bp round trip (14 bp fee + 10 bp slippage). Also each
   contract alone (own targets), for the three variants. Metrics: trades, win rate, mean net bp per trade (price move
   between fills minus both fees, as axis 1), total return, max drawdown, per-year return, concentration (top 5 trades
   share of gross profit, best year share, top contract).
2. **Trend engine**, `trend.FROZEN` parameters with `scale` 1.0 and 2.0, 5% protective stop (the live council's
   `stop_pct`), bench costs, six contracts, run from 2020-01-31, continuous compounding, per-year return and max drawdown.
3. **Carry**: always-on BTC+ETH cash-and-carry (axis 3 trial 3), recomputed with `carry.simulate` and its "base" cost
   model on Binance funding over 2020-01-01 -> 2025-10-31 (axis 3 reports it only as 2020-04 start and a split at
   2024-06, so it is recomputed, not copied). Per-year return and max drawdown.
4. **Portfolio**: **equal capital, one third each (wick base, trend at 1x, carry), rebalanced daily to fixed
   weights** (daily returns averaged). Chosen now, before any result. No inverse-volatility or other weighting is
   computed. Common window 2020-01-31 -> 2025-10-31. Per-year return, max drawdown, Sharpe; correlation matrices of
   daily and monthly returns. The portfolio holds the trend at 1x because 1x is the criterion of item 2.

## 4. Metrics

Per year and total: return, max drawdown, trades, win rate (per trade, wick), mean net bp per trade, Sharpe (daily,
sqrt(365)), concentration. A year is "positive" if its return is strictly > 0 (a year with no trade is 0, not positive).

## 5. Reading (fixed in advance)

- **Wick holds** if the base six-contract run is positive in **at least 4 of the 6 years** AND the **+1 minute**
  variant is **positive over the whole period** (total return > 0). Otherwise it does not hold. The 48 bp variant,
  per-contract results and concentration are reported as context and do not change the verdict, but any statement of
  "holds" must carry them.
- **Trend holds** if the 1x run is positive in **at least 4 of the 6 years**. The 2x run is reported, not judged.
- **Carry and portfolio**: no pass/fail threshold was set for carry (axis 3 already judged it a cash substitute). The
  portfolio is read descriptively; it is called "useful" only if it is positive in at least 4 of 6 years and its max
  drawdown is smaller than the wick-alone drawdown.
- A result must not be re-run with changed parameters; bugs found are fixed and the original run discarded with a note.
