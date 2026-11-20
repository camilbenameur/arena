# Research v5: an aggressive trading agent, 2026-11-18

The goal: an aggressive trading agent, whatever the method, that earns quickly.

Files: `docs/research-v5/` (brief, harness, logs of the 90 trials, finalists, control script and result).

## 1. The protocol

- **The data:** one year of one-minute candles for the 6 contracts and their funding, from 2025-11-17 to 2026-11-18, downloaded from Kraken Futures into a separate research directory (`fetch.py`). The league's data was not touched.
- **The split:**
  - **design** on the first 245 days (2025-11-17 -> 2026-07-20), the only part the researchers saw;
  - **sealed control** on the following 121 days (2026-07-20 -> 2026-11-18), read only once, for all finalists at the same time.
- **The bench:** `arena/perp/lab/backtest.py`, `pessimiste-perp-v1` fill model: execution at the open of the next minute, 24 bp per round trip, hourly funding, gross leverage <= 10x.
- **The researchers:** five research agents in parallel, one per family, with at most 40 trials each, all logged. A retained strategy had to:
  - aim for the maximum compound return;
  - never be ruined;
  - have a drawdown of at most 50%;
  - be positive on at least 3 of 4 blocks.
- **The causality of each finalist:** checked by recomputing its targets on truncated data (zero gap for all 4).

## 2. The trend engine in service loses over the year

The frozen engine at 2x, the one used by the Trend Council and its benchmark, was replayed over the year:

| Period | Return | Max drawdown |
|---|---|---|
| Design (215 d, November 2025 to July 2026) | **-20.8%** | **-62.5%** |
| Control (121 d, July to November 2026) | +69.2% | -26.8% |
| Year | +36.3% | -62.5% |

Between February and April 2026 it lost 50%, in a range-bound market with fast reversals. Its drawdown over the year exceeds the policy's stop, set at -60%. Its good result in research v4 came from a single trend episode, the one from August to November.

## 3. The five families

| Family | Trials | Result |
|---|---|---|
| Aggressive trend (Donchian, ensembles, momentum) | 9 | No finalist. No trend effect on 3 of the 4 blocks, even at zero cost. |
| Intraday (5 min to 1 day: sessions, hour, day, volume) | 15 | No finalist. The gross gain per trade stays under the 24 bp cost. |
| Cross-sectional (lead-lag, pairs, relative momentum) | 16 | One weak candidate: +7.6% in design, fragile. |
| Funding (carry, crowd, cross-sectional) | 24 | Two finalists: +114% and +161% in design, positive on 4 blocks out of 4. |
| Shocks (liquidation wicks) | 26 | One finalist: +187% in design, 3 blocks out of 4 positive. |

## 4. The sealed control

| Finalist | Design | **Control (121 d)** | Drawdown on control | Year |
|---|---|---|---|---|
| Shocks: reversal after a wick of more than 4.5% | +187% | **+37.6%** | -23.5% | +296% (dd -37%) |
| Cross-sectional: reversal + low volatility | +7.6% | +20.8% | -26.3% | +30% |
| Funding: sign flip on funding smoothed over 16 h | +114% | **-45.2%** | -66.9% | +18% |
| Funding: sign flip on funding smoothed over 12 h | +161% | **-64.7%** | -83.1% | -7% |
| (Reference: 2x trend) | -20.8% | +69.2% | -26.8% | +36% (dd -62%) |

- **Funding collapses:** it was overfitting. The narrow plateau of settings suggested as much, and the control confirms it.
- **Shocks hold:**
  - 39 trades on the control, spread over 18 different days, with 69% winners and no dependence on a single episode;
  - the rule: when a contract moves by more than 4.5% (in log terms) over 5, 15 or 30 minutes, take the opposite side at 2x for 60 minutes, with a 5% stop;
  - the rationale: a liquidation cascade overshoots the equilibrium price, then corrects.

## 5. The decisive condition: speed

The bench enters at the open of the minute following the shock. With an execution delay:

| Entry delay | Design | Control |
|---|---|---|
| 0 min | +187% | **+37.6%** |
| 1 min | +140% | +13.9% |
| 2 to 3 min | +105 to +109% | +5.7% |
| 5 min | +111% | **-8.1%** |
| 10 min | +55% | -13.6% |

The league's watch only runs every 5 minutes: at that cadence, the strategy loses. It needs **a dedicated process that reacts in under a minute**: it reads prices every few seconds and only sends the order on a shock. The gain is made in the first minute of the correction.

## 6. What to expect, honestly

- **At best:** about +0.26%/day on the control, i.e. +38% over 4 months, with drawdowns of 25 to 37%.
- The gain comes in bursts: one shock every few days, nothing in between.
- The result rests on few events: about 60 shock days over the year.
- In live trading, a liquidation wick comes with an empty order book: the bench's 5 bp slippage is optimistic there. In paper trading, the league's simulator applies the same model as the bench.
- 10%/day remains out of reach. None of the 90 strategies tried comes close over any length of time.

## 7. Proposed next steps

1. **Build the "wick hunter" in paper trading**, as a portfolio of the perpetual-futures league:
   - a fast process reads prices every 5 to 10 s, spots a move of more than 4.5% over 5, 15 or 30 min, and enters against it at 2x for 60 minutes, with a 5% stop;
   - orders go through riskd, like for the other players;
   - a "5-minute-cadence hunter" benchmark measures what speed is worth.
2. **Review the Trend Council:** its engine has a -62% drawdown over the year. It can be kept as is, knowing it may hit its -60% stop, or reduced to 1x.
