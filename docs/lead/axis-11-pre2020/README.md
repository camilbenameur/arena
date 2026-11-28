# Axis 11: the frozen trend engine on Binance spot, 2017-2019

**Question.** Axis 10 suggested, after the fact, that the frozen trend engine at 1x combined with carry looked acceptable on 2020-2025. This axis tests the trend leg on a period nobody had used: Binance spot, from August 2017 to the end of 2019. Perpetual funding did not exist before 2019-09, so the carry leg cannot be tested here.

**Setup.**
- **Rules and costs:** the frozen engine (`arena/perp/lab/trend.py`, hash checked at start) on the frozen bench, at 1x, with the live 5% stop and 24 bp round-trip costs.
- **Shorting:** shorts are assumed free of funding. This is an assumption, not a measurement.
- **Benchmark:** equal-weight buy-and-hold of the coins listed each day, with no costs.
- **Universe:** BTC and ETH from 2017-08, LTC from 2017-12, XRP from 2018-05, LINK from 2019-01. Trading starts on 2017-09-16, after a 30-day warm-up.
- **Preregistration:** `PREREGISTRATION.md`, written before any run.

## Results (corrected data, see below)

| Period | Trend 1x | Equal-weight buy-and-hold | BTC buy-and-hold |
|---|---|---|---|
| 2017 (from 09-16) | +12.8%, max DD -3.4% | +231.0% | +270.7% |
| 2018 | +30.9%, max DD -17.5% | -76.6% | -73.0% |
| 2019 | +48.9%, max DD -15.6% | +60.9% | +94.3% |
| Total | **+120.0%** | +24.4% | +94.5% |
| Max drawdown | **-17.5%** | -86.5% | -83.2% |
| Sharpe | 1.16 | 0.54 | 0.76 |

- **Trades:** 343, win rate 29.7%, +82 bp net per trade. Longs made +224 bp per trade over 159 trades, shorts lost 40 bp per trade over 184 trades. Turnover was 207x, and fees cost 14.5% of starting equity.
- **At 2x (context only):** +237.6%, max drawdown -31.2%.

**Verdict, against the preregistered reading:** the trend leg HOLDS. It is positive in 3 of 3 years, positive in total, and its max drawdown is much smaller than buy-and-hold's.

## What it means

- **Regime dependence:** the frozen trend engine is strongly regime-dependent. On the 2017-2019 boom and bust it made +120% with a -17.5% max drawdown. On 2020-2025 (axis 10) it made -4.2% with a -63% max drawdown. On the Kraken year 2025-2026, the design part of research v5 lost 20.8% and the control part gained 69.2%.
- **Against buy-and-hold:** it loses heavily in strong bull years (2017: +13% against +231%) and wins in long bears (2018). Its value is protection in bears, not return.
- **Trend plus carry:** only the trend half of the idea is supported. The carry half cannot be tested before 2019-09.

## Correction found by the adversarial check

The first version of `run_trend.py` kept only rows stamped exactly on the minute. Binance's December 2017 BTC and ETH files, and part of February 2018, are stamped a few seconds past the minute. About 14 days of the December 2017 peak were silently dropped and flat-filled, which also distorted the benchmark with a fake jump. The loader now floors timestamps to the minute, and the run was repeated with the same frozen files and no parameter changed.

| | First version | Corrected |
|---|---|---|
| Total | +114.4% | +120.0% |
| 2017 | +9.1% | +12.8% |
| Max drawdown | -17.5% | -17.5% |

The verdict is unchanged. Only the corrected figures are reported above.
