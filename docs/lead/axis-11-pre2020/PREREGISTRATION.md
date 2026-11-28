# Axis 11: preregistration (written before any number was computed)

Question: axis 10 found, post hoc, that the frozen trend engine at 1x combined 50/50 with always-on carry looked decent
on 2020-2025. That idea was formed after seeing those years. Does the TREND leg alone hold on a period never touched:
Binance SPOT data 2017-08 -> 2019-12? (Carry cannot be tested: perpetual funding did not exist before 2019-09.)
**Nothing is retuned. One run, all results reported.**

Repository state when written: commit `f2ccade` is the last commit; the working tree is not committed. At this point only
the raw monthly zips had been downloaded (no price was read, no engine run).

## 1. Frozen code (sha256)

| Role | File | sha256 |
|---|---|---|
| Trend engine (FROZEN) | `arena/perp/lab/trend.py` | `2fdf8feff9f82b5c54ca8257a064a27c197f1c902ab9aab064d0975948288065` |
| Bench | `arena/perp/lab/backtest.py` | `567035decd5ed989ab33387229864d592b58e54944179722d13cb5a3a190d8bb` |

The scripts re-check both hashes and abort on mismatch. Same hashes as axis 10: the engine and bench are identical.
`TrendParams` has **no long-only switch**, so no long-flat variant is run (none is invented).

## 2. Data and period

- Source: `data.binance.vision` spot monthly 1-minute klines (the engine needs minute closes: 4-hour bars are taken from
  minute blocks and the volatility from hourly closes), stored in `~/dev/_arena-data/axis-11/`, outside git.
- Universe by availability on the dump server (first month with a file; a coin is traded only from its first candle,
  before which its price is held flat so no signal is possible, as in axis 10):
  - 2017: BTCUSDT, ETHUSDT (from 2017-08), LTCUSDT (from 2017-12)
  - 2018: the above plus XRPUSDT (from 2018-05)
  - 2019: the above plus LINKUSDT (from 2019-01)
  - SOL did not exist.
  Spot Tether pairs only; no coin is selected on performance.
- Grid: 2017-08-01 00:00 UTC -> 2019-12-31 23:59 UTC, minute grid. A missing minute is held flat at the previous close
  (as `backtest.load`).
- Trading start: **2017-09-16 00:00 UTC** (30 days after the first BTC candle, 2017-08-17, the engine's 30-day warm-up
  as in v5 and axis 10). "2017" therefore means 2017-09-16 -> 2017-12-31. End: 2019-12-31.
- Years scored: 2017 (partial, from the trading start), 2018, 2019.

## 3. Run

`trend.FROZEN` with scale 1.0 (the judged run) and, as context only, scale 2.0; 5% protective stop (the live council's
`stop_pct`); bench costs `Costs()` = 7 bp fee + 5 bp slippage per side = 24 bp round trip; long and short both allowed as the
engine does; **shorting is assumed available at the perp cost model with ZERO funding** (spot has no short and no
funding, so this is an assumption, not a measurement; perpetual funding in 2019 was typically small and positive, so
longs would have paid and shorts received a little: ignoring it is a simplification). Continuous compounding from the
trading start; per-year returns are calendar slices of that run. Max gross 10x, rebalance band 5%, as the bench defaults.

## 4. Benchmark and metrics

- Benchmark "buy-and-hold of the same universe": **equal weight across the coins listed on each day, rebalanced daily,
  long only, no costs** (this flatters the benchmark slightly). Same window, same data. BTC buy-and-hold is reported as context.
- Metrics, per year and for the whole window: return, max drawdown (within year and whole-window), Sharpe (daily returns,
  sqrt(365)), trades, win rate, mean net bp per trade, turnover (traded notional / starting equity), fees. Same for the benchmark
  (return, max drawdown, Sharpe).
- A year is "positive" if its return is strictly > 0.

## 5. Reading (fixed in advance)

The trend leg **holds** if ALL of:
1. 1x return positive in at least 2 of the 3 calendar years (2017 from 09-16, 2018, 2019);
2. 1x total return over the whole window positive;
3. 1x whole-window max drawdown smaller in magnitude (better) than the equal-weight buy-and-hold's.

Otherwise it does not hold. The 2x run, BTC buy-and-hold, per-year drawdown and trade statistics are context and do not
change the verdict. What the verdict implies for "trend 1x + carry 50/50": if trend does not hold here, the axis 10 combination
(+36%, drawdown -33%) is not supported as an out-of-sample idea; if it holds, the trend leg is supported on a third regime
but the carry leg remains untested before 2019-09. No result is re-run with changed parameters.
