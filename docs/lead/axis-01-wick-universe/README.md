# Axis 01: does the frozen "wick" rule generalise to other Kraken Futures perpetuals?

Rule under test, run **untouched** (`docs/research-v5/finalists/shocks_fade-wickS.py`): log move > 4.5% over 5, 15 or 30 min,
take the opposite side at 2x per contract for 60 min, 5% stop, 60 min lock after exit, entry at the next minute's open.
Bench: `arena/perp/lab/backtest.py` (7 bp fee + 5 bp slippage per side = 24 bp round trip; hourly funding; 10x gross cap).
Zero trials of new parameters. Window 2025-11-17 -> 2026-11-18, same as v5; metrics start after the same 30-day warm-up
as the v5 "year" figure. No design/control split here: the whole year is out of sample for the new contracts (the rule was
never fitted on them).

Files: `universe.py` (selection), `fetch.py` (1-minute candles + funding, data in `~/dev/_arena-data/axis-01/`, outside git),
`run.py` (backtests), `tables.py` (prints the tables below from `results.json`).

## 1. Universe

Public API snapshot taken 2026-11-27. PF_ perpetuals, excluding the 6 studied, 24h quote volume >= USD 5M, listed >= 180 days:
**only 5 contracts qualify** (of 205 instruments: 10 non-PF, 184 below the volume floor, 6 already studied).
- **Universe A (the specified filter, 5 contracts):** ZEC, HYPE, NVDAX (tokenised stock), NEAR, XMR.
- **Universe B (declared before any backtest, relaxes only the volume floor to USD 1M, top 30 -> 26 contracts):** A plus
  ADA, SEI, DOGE, TAO, UNI, CRV, FET, ENA, INJ, SUI, PUMP, DOT, QNT, MSTRX, PEPE, SPYX, WLD, XLM, AAVE, XAUT, WIF.
  Reason: 5 contracts is too few, and two of the original six (LINK 3.4M, LTC 0.9M) would themselves fail the 5M floor.
  B contains 4 tokenised stock/ETF/gold contracts (NVDAX, MSTRX, SPYX, XAUT); "B crypto only" drops them.
- **orig6:** XBT, ETH, SOL, XRP, LTC, LINK re-fetched into the same store, as the same-year reference. It reproduces v5's
  year figure (+295.5%, dd -37.3% vs +296%, -37%).

Caveat: liquidity is a snapshot of today, not of the window. Candle gaps are forward-filled flat (as `backtest.load`).

## 2. Sizing and overlap (finalist's own logic, kept)
Each contract gets an independent +-2x position; a contract in a trade or in its 60-min lock ignores new shocks. Positions
across contracts are not netted. The only portfolio limit is the bench's 10x gross cap (targets are scaled down pro rata
above it). With 6 or 5 contracts the cap hardly binds (max 12x / 10x gross); in B, up to **24 positions were open at once**
(48x requested), so in market-wide sell-offs the cap silently shrinks every position and B's "2x" is not 2x. The finalist is
applied to exactly the set of contracts traded (it re-emits the whole target row on any change; slicing would add spurious
rebalances).

## 3. Portfolio results (whole year)
Net return per trade = price move between fills (slippage included) minus both fees, per unit notional; funding excluded
(it is in the equity figures; it is tiny here). Events = closed trades.

| Universe | Variant | Events | Shock days | Win % | Mean net/trade bp | Median bp | Total % | Max DD % | Top-5 trades, share of gross profit | Top contract (share of P&L) |
|---|---|---|---|---|---|---|---|---|---|---|
| orig6 | base | 92 | 31 | 77.2 | 71.5 | 91.8 | +295.5 | -37.3 | 26% | LINK 39% |
| orig6 | entry +1 min | 91 | 31 | 68.1 | 53.9 | 63.5 | +173.3 | -34.9 | 29% | SOL 45% |
| orig6 | costs 48 bp | 92 | 31 | 71.7 | 48.1 | 67.9 | +155.2 | -39.0 | 29% | SOL 49% |
| A (5, >=5M) | base | 287 | 130 | 55.7 | -1.8 | 32.3 | **-34.4** | -84.7 | 17% | (P&L negative; NEAR -1.18, HYPE +0.82 in start-equity units) |
| A | entry +1 min | 288 | 130 | 50.7 | -6.9 | 12.0 | -49.9 | -84.0 | 20% | |
| A | costs 48 bp | 287 | 130 | 51.9 | -25.2 | 8.3 | -83.3 | -92.7 | 20% | |
| B (26, >=1M) | base | 1497 | 249 | 57.8 | 15.6 | 40.2 | +1129.5 | -94.6 | 9% | QNT 64% |
| B | entry +1 min | 1467 | 249 | 56.5 | 11.6 | 26.3 | **-41.2** | -95.4 | 7% | QNT 107% |
| B | costs 48 bp | 1500 | 249 | 53.7 | -8.2 | 17.4 | **-98.5** | -99.8 | 11% | QNT 180% |
| B crypto only (22) | base / +1 min / 48 bp | 1434 / 1404 / 1437 | 242 | 58.7 / 57.3 / 54.4 | 15.7 / 12.5 / -8.0 | | +1042.6 / -35.8 / -98.2 | -95.0 / -95.3 / -99.8 | | QNT |

(Shares above 100% mean the contract made more than the whole portfolio, others lost.)

### Per quarter (portfolio return, %; 2025Q4 and 2026Q4 are partial)
| Universe / variant | 25Q4 | 26Q1 | 26Q2 | 26Q3 | 26Q4 |
|---|---|---|---|---|---|
| orig6 base | +20.5 | +100.1 | +19.2 | +37.6 | 0.0 |
| orig6 +1 min | +20.6 | +69.5 | +17.4 | +19.0 | -4.3 |
| orig6 48 bp | +17.5 | +65.8 | +14.8 | +20.2 | -5.1 |
| A base | +19.5 | +173.3 | -64.1 | -27.2 | -23.2 |
| A +1 min | +9.9 | +134.6 | -71.4 | -7.2 | -26.7 |
| A 48 bp | +14.0 | +82.1 | -76.9 | -44.8 | -36.8 |
| B base | +39.3 | +650.3 | +16.6 | -7.2 | +8.7 |
| B +1 min | +24.9 | +125.6 | -61.6 | +9.0 | -50.1 |
| B 48 bp | +14.3 | +28.9 | -82.4 | -84.0 | -64.9 |

orig6 is positive in every quarter under all three variants. A and B are positive in one quarter (2026Q1, the February
crash) and lose in most others once frictions are added. B's base total is 2026Q1 alone (+650%).

## 4. Per contract (single-contract runs at 2x, whole year; total return %, base / +1 min / 48 bp)
| Contract | Events | Win % | Mean net bp | Total % | Max DD % | +1 min | 48 bp |
|---|---|---|---|---|---|---|---|
| XBT | 3 | 100 | 300 | +18.7 | -3.2 | +14.6 | +17.1 |
| ETH | 15 | 93 | 78 | +24.0 | -14.5 | +13.8 | +15.6 |
| SOL | 18 | 83 | 132 | +56.4 | -14.6 | +41.8 | +44.0 |
| XRP | 18 | 56 | 18 | +3.2 | -29.9 | -4.0 | -5.3 |
| LTC | 13 | 77 | 17 | +2.5 | -18.3 | +23.7 | -3.5 |
| LINK | 21 | 71 | 60 | +26.4 | -17.4 | +19.4 | +14.5 |
| ZEC (A) | 123 | 63 | 7.8 | -3.3 | -60.8 | -53.3 | -45.6 |
| HYPE (A) | 36 | 69 | 69.9 | +57.2 | -16.4 | +36.3 | +32.7 |
| NVDAX (A) | 7 | 29 | 22.5 | +1.5 | -15.7 | +2.0 | -1.8 |
| NEAR (A) | 72 | 44 | -43.5 | -51.6 | -56.1 | -42.0 | -65.7 |
| XMR (A) | 43 | 49 | 19.4 | +10.1 | -42.8 | +28.7 | -10.1 |
| ADA | 21 | 67 | -3.2 | -4.2 | -24.1 | +28.4 | -13.2 |
| SEI | 25 | 60 | 32.6 | +13.4 | -26.7 | +17.9 | +0.9 |
| DOGE | 18 | 72 | 107.1 | +40.9 | -19.5 | +106.0 | +29.8 |
| TAO | 42 | 55 | 0.2 | -5.9 | -35.1 | -17.6 | -22.9 |
| UNI | 51 | 55 | -12.1 | -17.8 | -41.1 | -8.3 | -35.2 |
| CRV | 37 | 65 | 18.7 | +9.3 | -16.1 | +44.9 | -8.1 |
| FET | 70 | 64 | 83.5 | +186.5 | -23.6 | +101.6 | +106.6 |
| ENA | 106 | 59 | 42.2 | +108.2 | -26.2 | +198.1 | +26.5 |
| INJ | 63 | 59 | 17.3 | +13.1 | -32.9 | +90.7 | -15.9 |
| SUI | 36 | 61 | 32.6 | +20.7 | -22.1 | +51.5 | +1.9 |
| PUMP | 128 | 63 | 47.5 | +181.7 | -42.4 | +185.8 | +54.4 |
| DOT | 31 | 68 | 3.4 | -1.4 | -22.7 | +65.9 | -14.8 |
| QNT | 105 | 65 | 114.7 | +716.7 | -62.3 | +291.9 | +406.8 |
| MSTRX | 49 | 45 | -0.5 | -6.0 | -19.7 | -22.8 | -25.6 |
| PEPE | 68 | 69 | 50.3 | +79.1 | -30.5 | +75.9 | +30.2 |
| SPYX | 3 | 33 | 194.8 | +11.6 | -1.5 | +11.6 | +10.1 |
| WLD | 129 | 59 | 5.5 | -6.0 | -64.8 | +3.9 | -48.6 |
| XLM | 36 | 61 | 23.9 | +12.2 | -24.7 | +47.5 | -5.2 |
| AAVE | 41 | 66 | 52.6 | +45.1 | -20.8 | +26.7 | +18.8 |
| XAUT | 1 | 100 | 220 | +4.4 | -5.2 | +2.3 | +3.9 |
| WIF | 61 | 56 | 7.9 | +0.4 | -53.8 | -43.7 | -29.4 |

Contracts with a positive total: 24 of 32 base (all 6 original positive, 18 of 26 new), 25 of 32 with +1 min entry
(1 min delay is *not* uniformly worse per contract: single contracts are noisy), **16 of 32 with 48 bp costs**.
Note the per-contract mean edge falls with fewer, thinner events: new contracts fire 2 to 7x more often than the big six
(median ~40 vs 15 events) at a much lower gain per trade (mean net 15.6 bp in B vs 71.5 bp in orig6), i.e. the move
threshold is hit by routine volatility in smaller coins, not by liquidation wicks, so the "overshoot" premise is weaker.

## 5. Verdict: **no, or at best weakly**
- On the specified filter (5 contracts) the rule **loses** (-34%, dd -85%) and is worse with delay and costs.
- On the broader 26-contract set, the headline +1130% is an artefact of a few things: 2026Q1 = +650%, QNT alone = 64% of
  P&L, drawdown -95%, 24 simultaneous positions hitting the 10x cap. It turns into **-41% with a 1-minute delay** and
  **-98.5% at 48 bp**: no robust edge. Mean net gain per trade (15.6 bp) is below the doubled cost.
- 18/26 new contracts are positive in the base run, but only about half survive 48 bp; the edge that survives all stress
  is in the large liquid caps (XBT, ETH, SOL, LINK, HYPE, FET, PUMP, QNT, PEPE, AAVE, DOGE in single-contract runs).
  Picking those now would be selection on the same data, so it is a hypothesis, not a result.
- The original six remain the only set where it holds up under all three variants (+296 / +173 / +155%), which is
  consistent with a real effect in the deepest books, but 31 shock days is a thin sample.
- Not tested: real order-book depth (the wick happens on an empty book; thin alts are the worst case).

## 6. Follow-up ideas (not run)
1. Pre-registered liquidity gate (e.g. 30-day median volume floor, decided before looking), tested on the second half of
   a fresh data window, to ask whether the big-cap-only effect is real.
2. Event-level slippage study using order-book snapshots at shock time, to price entries realistically before any further
   backtest.
3. A shock-size scaling check on the same frozen rule (does return per trade rise with move size / volume spike?), as a
   diagnostic of the "overshoot" premise, not as a tuned threshold.
