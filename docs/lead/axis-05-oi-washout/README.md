# Axis 05: open-interest washout reversal

Verdict: **FAIL. No edge at any delay, in the design or in the sealed control.** Gross of costs the rule earns about zero
(+4 bp per event in the design, -4 bp in the control) against 20 bp of round-trip costs. It is not "the wick effect
re-measured" either: the kill rule's condition (an edge only under 5 minutes) is not met because there is no edge at 1 minute
either. Rule, parameters and criteria were frozen in [PREREGISTRATION.md](PREREGISTRATION.md) before any return was computed.

Files: `fetch.py` (polite, resumable download, data kept in `~/dev/_arena-data/axis-05/`, outside git), `prep.py` (zips to
numpy, split into a design file and a control file), `lib.py` (rule, simulator, statistics), `run_design.py`
(16 trials), `run_control.py` (one run, lock file), `tables.py` (prints the tables below), `trials.jsonl`
(every trial, with its parameters and results), `design_events.json` (8 MB, kept with the data in `~/dev/_arena-data/axis-05/`), `control_results.json` (every event).

## 1. Data (Binance USDT-M public dump)
| Symbol | 5-min open interest from | 1-minute klines from | Last day loaded |
|---|---|---|---|
| BTCUSDT | 2020-09-01 | 2020-01-01 | 2026-11-26 |
| ETHUSDT | 2021-12-01 | 2020-01-01 | 2026-11-26 |
| SOLUSDT | 2021-12-01 | 2020-09-14 | 2026-11-26 |
| XRPUSDT | 2021-12-01 | 2020-01-06 | 2026-11-26 |
| LTCUSDT | 2021-12-01 | 2020-01-09 | 2026-11-26 |
| LINKUSDT | 2021-12-01 | 2020-01-17 | 2026-11-26 |

The dump has no 5-minute open interest before 2021-12-01 for five of the six symbols (only BTC goes back to 2020-09), so the
design is effectively 2021-12 to 2025-12 (BTC adds 15 months, but with the 60-day warm-up its first event is 2020-11-06 and only
17 events fall in 2020). Zero-valued OI rows (197 for SOL) were treated as missing. Funding: actual 8-hourly Binance rates (fetched, not
approximated); it is tiny (0.2 bp per event on average). Design: 2021-12 to 2025-12-31. Control: 2026-01-01 to 2026-11-26 (331 days).

Events (long side, one event per symbol per 6 hours): **1,923 in the design (765 event days), 389 in the control (159 event days)**.
Per symbol in the design: BTC 376, ETH 326, SOL 286, XRP 329, LTC 307, LINK 299. Events cluster heavily: the design has 273 days with
3 or more events, up to 16 in a day (all six symbols, several times); 52% of design events and 47% of control events fall on days with
4 or more events. On those crash days the mean net return is -26 bp (design) and -57 bp (control); on quieter days it is -5 bp (design)
and +6 bp (control).

## 2. Delay ladder, net of costs (0.05% fee + 0.05% slippage per side, plus actual funding)
"De-clustered" is one observation per UTC crash day, the equal-weight mean of that day's events. PF = profit factor.
Sum % is the sum of net returns per unit notional, no compounding. Delay 1 is a diagnostic for the kill rule, not a trial.

### Design (to 2025-12-31)
| delay (min) | raw n | raw mean bp | raw PF | de-clust n | de-clust mean bp | de-clust PF | raw mean bp, no wick overlap | de-clust mean bp, no wick overlap (PF) |
|---|---|---|---|---|---|---|---|---|
| 1 (diag) | 1923 | -16.1 | 0.85 | 765 | +0.1 | 1.00 | -10.3 | +3.3 (1.05) |
| 5 | 1923 | -16.8 | 0.84 | 765 | -1.6 | 0.98 | -11.5 | +1.7 (1.03) |
| 15 | 1923 | -16.1 | 0.85 | 765 | -3.4 | 0.95 | -12.7 | -1.8 (0.97) |
| 30 | 1923 | -15.6 | 0.85 | 765 | -4.5 | 0.94 | -17.7 | -6.2 (0.91) |
| 60 | 1923 | -17.2 | 0.84 | 765 | -8.4 | 0.89 | -20.7 | -11.0 (0.85) |

### Sealed control (2026-01-01 to 2026-11-26), run once
| delay (min) | raw n | raw mean bp | raw PF | de-clust n | de-clust mean bp | de-clust PF | raw mean bp, no wick overlap | de-clust mean bp, no wick overlap (PF) |
|---|---|---|---|---|---|---|---|---|
| 1 (diag) | 389 | -20.7 | 0.75 | 159 | -0.8 | 0.98 | -22.0 | -6.1 (0.89) |
| 5 | 389 | -23.0 | 0.73 | 159 | -3.9 | 0.93 | -23.3 | -7.9 (0.86) |
| **15** | **389** | **-23.8** | **0.71** | **159** | **-1.7** | **0.97** | **-21.8** | **-5.0 (0.90)** |
| 30 | 389 | -28.9 | 0.64 | 159 | -7.4 | 0.86 | -25.7 | -8.3 (0.84) |
| 60 | 389 | -30.5 | 0.61 | 159 | -7.2 | 0.86 | -26.5 | -9.0 (0.82) |

The only positive-looking cells are the design de-clustered means at delay 1 to 5 minutes once wick events are removed (+1.7 to +3.3 bp,
PF 1.03 to 1.05). They are within noise, below the 20 bp cost by an order of magnitude, and absent in the control. Losses grow
with delay, which is the usual shape of a faint short-lived effect, but its size is a few basis points gross.

Gross mean per event at 15 minutes: +4.1 bp (design), -3.7 bp (control).

## 3. Overlap with the wick rule
Wick trigger: log move beyond -4.5% in 5, 15 or 30 minutes on Binance 1-minute closes, same symbol, within [t - 4 h, t + 60 min]
of the OI decision time. **Overlap share: 18.9% of design events, 6.9% of control events.** Removing them changes nothing important:
the raw mean stays at -12.7 bp (design) and -21.8 bp (control) at 15 minutes. So the OI signal mostly fires without a wick trigger
(a slow washout over 4 hours, not a one-minute cascade), and this is not a re-measurement of the wick effect.

## 4. Pass/fail (control, 15-minute delay, long side)
| Criterion | Result | Status |
|---|---|---|
| C1 net mean above 0 after all costs, de-clustered and raw | de-clustered -1.7 bp, raw -23.8 bp | FAIL |
| C2 profit factor above 1.3, de-clustered | 0.97 (raw 0.71) | FAIL |
| C3 at least 40 control events | 389 raw events (159 days) | PASS |
| C4 not driven by the top 3 events (sum of raw net returns above 0 without them) | sum -92.5%, without the top 3: -115.6% | FAIL |
| C5 C1 and C2 after removing wick-overlap events, de-clustered | -5.0 bp, PF 0.90 | FAIL |
Overall: **FAIL** (4 of 5 criteria fail). The design period fails the same criteria (C1: -3.4 bp de-clustered, -16.1 bp raw; PF 0.95 and 0.85).
Per symbol at 15 minutes the control is negative for all six (BTC -26, ETH -39, SOL -38, XRP -11, LTC -5, LINK -26 bp), and the design for five of six
(SOL +0.1 bp). By year in the design: 2022 -37 bp, 2023 -7, 2024 +1, 2025 -28; the control 2026 -24 bp.

Short mirror (symmetry test, design only): negative at all four delays (de-clustered -12.5, -7.6, -7.3, -2.5 bp; raw -26 to -18 bp), so
it failed and was not taken to the control.

## 5. Robustness trials (design, 15-minute delay, one change from the base rule; they never replace it)
| # | change | raw n | raw mean bp | raw PF | de-clust mean bp | de-clust PF |
|---|---|---|---|---|---|---|
| 9 | percentile 10% | 2720 | -14.9 | 0.85 | +0.9 | 1.01 |
| 10 | return below -1.0 sigma | 2697 | -17.6 | 0.83 | -7.0 | 0.90 |
| 11 | exit at 3 h | 2427 | -17.7 | 0.79 | -5.3 | 0.89 |
| 12 | exit at 12 h | 1755 | -24.8 | 0.82 | -5.5 | 0.94 |
| 13 | stop at 3 ATR | 1923 | -15.1 | 0.86 | +0.7 | 1.01 |
| 14 | no stop | 1923 | -5.2 | 0.95 | +8.2 | 1.13 |
| 15 | 2 h OI window | 3160 | -10.4 | 0.90 | +7.5 | 1.12 |
| 16 | 8 h OI window | 1351 | -3.8 | 0.96 | +6.7 | 1.10 |

Four of the eight variants show a small positive de-clustered mean (+0.7 to +8.2 bp, PF 1.01 to 1.13), all with a negative raw mean and a PF
below 1.3. This is the same pattern as the base rule (a loss on multi-symbol crash days, slightly positive otherwise), with the stop
removed or the window changed. None approaches the 1.3 bar and none was taken to the control: they are exploration inside a 16-trial
budget, not finalists. Trial list in `trials.jsonl` (16 of the 20 allowed; the 4 spare were not used).

## 6. Verdict
The idea (long after open interest collapses and price falls more than 1.5 sigma over 4 hours) does not pay after costs, on 4 years of design or on
11 months of sealed control, at any entry delay from 1 to 60 minutes. The gross edge is about zero, so there is nothing for a delay to destroy:
the kill rule (edge only under 5 minutes, i.e. the wick effect re-measured) does not apply, and the result is simply "no edge". The losses are concentrated on
multi-symbol crash days (events on the same day are one bet repeated, which the raw numbers overstate), where the rule keeps buying a
falling market; on quiet days the control is about +6 bp per event, which is noise. The axis stops here. It adds nothing to the wick hunter, and
2x leverage is not warranted.

## 7. Deviations and caveats (all stated before they could matter)
- **Voided first design run.** The first design run (file `trials_voided_1_bug_atr_nan.jsonl`, kept) had a bug: symbols listed mid-day had NaN hourly ATR, so only BTC and ETH
  produced events. Fixed in `lib.py` (leading minutes back-filled, which affects only dates before any OI exists, and zero-OI rows set to missing), then the
  16 trials were rerun in full. Nothing in the rule or parameters changed. The control was not opened before the fix.
- **Control run despite a design failure.** The pre-registration says a design failure of C1 at 15 minutes stops the axis without opening the control.
  The control was run anyway, once, because the brief asked for it; it only confirms the failure and cannot reverse it.
- Prices are Binance, not Kraken. The plan's Kraken perps are the trading venue; their funding and fills differ somewhat (not measured here; a gross edge of about zero leaves little room for a venue difference to matter).
- The control's 90-day statistics start from design-period data (a normal warm-up, no 2026 information is used before its own date).
- Events whose 6-hour trade would run past the last data minute are dropped (none matter at this scale).
- OI stamps: a row stamped T is treated as known from T+5 minutes. If the real publication delay is longer, the guard is slightly optimistic, which would only help the rule.
