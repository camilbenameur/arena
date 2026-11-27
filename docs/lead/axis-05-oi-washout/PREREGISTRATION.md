# Axis 05, pre-registration: open-interest washout reversal

Written before any price, open-interest or return was computed for any date, and before any data from
2026-01-01 onwards was opened. Nothing below changes after the first design run. Any later deviation is listed
in the README under "Deviations" and the affected result is labelled as such.

## 1. Data
- Open interest: Binance USDT-M daily `metrics` zips (5-minute series, `sum_open_interest` in contracts, not the USD value,
  so that a price fall does not shrink the series by itself).
- Prices: Binance USDT-M 1-minute klines (monthly zips, daily zips for the current month).
- Funding: Binance USDT-M monthly `fundingRate` zips (actual 8-hourly rates).
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, LTCUSDT, LINKUSDT. These are the Binance twins of the six Kraken
  perpetuals used elsewhere in the arena; the trade is simulated on Binance prices (Kraken candles are not used here).
- Windows: design = first available date to 2025-12-31 (the code refuses to load later rows during design);
  sealed control = 2026-01-01 to the latest available day, read once (section 7).
- Real start dates per symbol are reported in the README.

## 2. Lookahead guard
- The decision grid is every 5 minutes. A metrics row stamped T describes the 5-minute bar that starts at T, so it is
  treated as known only from T+5 min. At decision time t only rows stamped <= t-5 min are used.
- Prices at decision time t use 1-minute bars closed at or before t (last close stamped t-1 min).
- Trailing statistics (90-day open-interest-change distribution and 90-day return sigma) are recomputed once per UTC day
  from data strictly before 00:00 UTC of that day and used unchanged for the whole day.
- A symbol needs 60 days of history before it can signal.

## 3. Frozen rule (long side)
- dOI4h(t) = OI(t-5 min row) / OI(t-4h-5 min row) - 1 (both rows must exist).
- r4h(t) = log(close(t-1 min) / close(t-4h-1 min)).
- Threshold A: the 5th percentile of the dOI4h values sampled every 5 minutes over the trailing 90 days.
- sigma: the standard deviation of r4h sampled every 5 minutes over the same 90 days.
- Signal at decision time t: dOI4h(t) <= A and r4h(t) < -1.5 * sigma.
- Event: the first signal at or after the end of the previous lock. After an event on a symbol, that symbol is locked for
  6 hours from the decision time (signals during the lock are ignored). The lock does not depend on the delay, so every
  delay has exactly the same event set.
- Entry: long at the OPEN of the 1-minute bar stamped t + delay, delay in {5, 15, 30, 60} minutes.
  Diagnostic only (not a pass criterion, used for the kill rule): delay 1 minute.
- Exit: at the open of the 1-minute bar stamped entry + 6 h, or earlier at the stop. Stop price = entry - 2 * ATR, where ATR is the
  mean true range of the last 14 closed hourly bars at decision time (hourly bars built from the 1-minute klines). Stop is
  tested on the 1-minute low from the entry bar on; fill at the stop price, or at the bar open if it opens below it.
- Size: 1x, one unit of notional per event; no netting, no compounding. Per-event return is on notional.
- Short side (symmetry test): the mirror rule (dOI4h >= 95th percentile and r4h > +1.5 sigma, short, same exit logic). It is
  run on the design period only. It is taken to the control only if, on the design period at the 15-minute delay, it
  meets criteria C1 to C5 below; otherwise it is reported as failed and never run on the control.

## 4. Costs
- Fee 0.05% per side, slippage 0.05% per side: 0.20% round trip on notional.
- Funding: the actual Binance funding rate applied at every funding stamp strictly after entry and at or before exit,
  paid by longs when positive (received when negative), reversed for shorts.
- Net return per event = gross price return - 0.20% - funding.

## 5. Mandatory analyses
- Wick overlap. The wick rule's triggers on Binance 1-minute closes: log move over 5, 15 or 30 minutes with absolute value
  above 4.5% (downward for a long event). An OI event overlaps when a downward wick trigger on the same symbol occurred in
  [t - 4 h, t + 60 min]. Report the overlap share of events, and every result with overlapping events removed.
- Pooled, de-clustered. Events are grouped by UTC day of the decision time across all symbols. One observation per
  day is the equal-weight mean net return of that day's events. Report counts of raw events and of event days.
- Per-delay table, per-symbol table, year split, top-3 dependence.
- Kill rule: if the edge (net mean above 0, profit factor above 1.3) exists at delay 1 minute or in the design but not at 5, 15, 30
  and 60 minutes (i.e. only for entries sooner than 5 minutes), the result is reported as the wick effect re-measured and the axis stops.

## 6. Pass criteria (all on the sealed control, 15-minute delay, long side)
- C1: net mean per observation above 0 after all costs, on the de-clustered pool, and the raw event mean also above 0.
- C2: profit factor (sum of positive net returns over sum of absolute negative ones) above 1.3, on the de-clustered pool.
- C3: at least 40 raw events in the control.
- C4: not driven by the top 3 events: the sum of net returns of the raw events stays above 0 once the 3 best events are removed.
- C5: C1 and C2 still hold on the de-clustered pool once wick-overlap events are removed.
- Verdict PASS only if C1 to C5 all hold. The design period is judged by the same criteria except C3, which is waived there.
  A design failure of C1 at 15 minutes stops the axis without opening the control (the control script is only run for a finalist).
- The 2x leverage option of the plan is not used unless PASS; nothing is levered in this study.

## 7. Trial budget and the control
Trial list fixed now (16 of the 20 allowed; the other 4 are an unused reserve; every trial is logged in `trials.jsonl`, with failures):
1 to 4: base long rule at delay 5, 15, 30, 60.
5 to 8: mirror short rule at delay 5, 15, 30, 60 (symmetry test).
9 to 16, all at delay 15 minutes, one change each from the base rule: (9) percentile 10% instead of 5%; (10) return threshold -1.0 sigma;
(11) exit after 3 h; (12) exit after 12 h; (13) stop at 3 ATR; (14) no stop; (15) 2 h OI window; (16) 8 h OI window.
The wick-overlap and de-clustered results are views of trials 1 to 4 and are logged as `kind: view`, not as trials.
Trials 9 to 16 are robustness checks. They never replace the base rule. The finalist set is exactly the base rule at the four delays
(plus the short mirror only if the symmetry test passes). The control is run once by `run_control.py`, which creates an exclusive
lock file before reading any 2026 data and refuses to start if it exists. Every finalist is reported.
