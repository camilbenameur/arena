# Researcher brief: aggressive trading agent (research v5, 2026-11-18)

## The goal

Find an **aggressive trading strategy that earns quickly** on 6 Kraken Futures perpetual contracts (XBT, ETH, SOL, XRP, LTC, LINK, paper trading). Every method is allowed. Leverage goes up to 10x gross.

We are looking for the best possible **compound return** under three constraints:
- never ruin;
- a maximum drawdown of at most 50%;
- a positive result on at least 3 of the 4 blocks of the design period.

The reference engine is the frozen trend follower (`arena/perp/lab/trend.py`, `FROZEN`, at 2x scale): it has to be beaten. On the design period it **loses 20.8%** (drawdown -62%, blocks +40.6 / -49.7 / +3.1 / +8.7): it only won during the August to November 2026 episode. Measure it yourself first anyway, with `trend.targets(d, TrendParams(scale=2.0))` and a 5% stop, and log it as the first trial (`name: "reference-trend-2x"`).

## The rules (non-negotiable)

1. **Data:** only `design()` from the harness, `docs/research-v5/harness.py`. It contains the first 245 days of a year of one-minute candles, from November 2025 to July 2026. **Never** open `data/`, `full.pkl`, `var-perp/` or any other price source: the remainder is a sealed control, read only once by the coordinator. A leak makes all the work unusable.
2. **Causality:** the target decided at minute i uses only data <= i. The coordinator checks this by recomputing your targets on truncated data. Any look into the future disqualifies the strategy.
3. **Real costs:** the `evaluate()` bench counts 24 bp per round trip, hourly funding and stops within the minute. It executes at the open of the next minute. Do not work around the bench.
4. **Log:** every trial, failures included, goes through `log_trial(<family>, <name>, params, res)`. **At most 40 trials.** The more you run, the more likely you are to find a fluke: prefer ideas with an economic rationale over a parameter sweep.
5. **Robustness:** a retained strategy must have at least 3 of 4 blocks positive, and must not depend on a single setting (its close neighbors must also win).
6. **Simulator constraints:** at most 48 orders per day across all contracts. `evaluate()` does not check this: compute it yourself (the number of target changes per day).
7. **Resources:** the machine is shared, with 8 cores and little free memory. Run a single bench process at a time, and load `design()` once per script. To triage ideas you may do a quick vectorized precomputation, but every reported figure comes from `evaluate()`.
8. Work in `docs/research-v5/<family>/`. Do not modify anything in the arena repository.

## What you hand in

- **1 or 2 frozen finalists**, each in a file `docs/research-v5/finalists/<family>_<name>.py`. This file exposes `targets(d) -> np.ndarray` (of size N x 6, NaN = keep) and `STOP_PCT` (a float or None). The parameters are hard-coded in it. It is self-contained: it imports only numpy, pandas and `arena.perp.lab.backtest`.
- **As the final answer, in short text:**
  - for each finalist: the idea in one sentence, its economic rationale, its design result (total, per day, maximum drawdown, blocks, orders per day, turnover);
  - the result of the 2x trend reference over the same period;
  - what failed, one line per idea;
  - if nothing beats the reference, say so plainly. An honest "nothing better" is worth more than a fragile finalist.
