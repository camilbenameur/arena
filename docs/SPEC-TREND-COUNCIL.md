# Council v4 "Trend Council": specification

A redesign of the council with everything permitted, aiming at a council that generates net income, on the order of 10% per day.

## 1. The principle

What the audit showed about the old council:
- LLM persona opinions with no edge;
- huge sizes;
- a re-decision every 10 min, hence 140x turnover.

Council v4 inverts the roles:
- **the engine decides**: the frozen trend engine (`arena/perp/lab/trend.py`, `FROZEN`, at scale 2x) gives the target of each contract at each 4-hour bar close;
- **the LLMs can only brake**: each contract receives a coefficient of 1, 0.5 or 0, applied to the engine's target. They can neither increase, nor invert, nor open a position the engine does not hold;
- **the code executes**: it computes the gap between the final target and the position, and sends an order only if the gap exceeds 5% of equity (the bench's band). Orders go through riskd like for every other player.

## 2. The portfolio

- `council-perp:trend`, named "Trend Council", `kind = "council"` (councils league), €1,000.
- Config file `config/perp-council-trend.toml`, listed alone in `config/council-league.toml`. The old councils are retired (`portfolio_retired`).
- Policy `config/policy-perp-council-trend.toml`, `aggressive` profile, with these changes:
  - **gross leverage ≤ 10x**. The engine's own: 0.7x on average to 1x, hence about 1.4x to 2x, with peaks toward 4 to 6x;
  - **order size ≤ 400% of equity**: the engine caps at 2 per contract, times the scale of 2;
  - **protective stop at 5%** placed by the code on each position (tested on the bench: no effect on the result). The loss at the stop must stay ≤ 25% per position and ≤ 60% in total, as today. If riskd refuses, the code reduces the size until it passes, instead of abandoning the order;
  - **edge rule** (cost ≤ 33% of the expected move): the expected move of an engine order is measured offline, not declared. We take the engine's mean gross move per trade over the training set, computed once and written in the config with its source. The engine must not be blocked by a rule made for LLMs that declare their own expected move;
  - **at most 48 openings or adjustments per day** (6 contracts × 6 bars), with no minimum delay: the engine decides only every 4 h;
  - **halt at −60%**, with a manual resume.

## 3. The pace

- **One round per 4-hour bar close**: 00:00, 04:00, 08:00, 12:00, 16:00 and 20:00 UTC, at the watcher's first tick after HH:00. The candles used are the 1-minute candles closed up to HH:59 of the previous bar. The bench showed that the alignment of the bars does not matter (from +6 to +14% on the control).
- **An additional veto round**, only on a news item (a Kraken `news_item`, a macro release from the calendar) or a market wake-up at 2% in 1 h. It can only lower the current coefficients, never raise them above the engine's target.
- The council does not follow the 10-minute cadence nor the recalls requested by the agent. It keeps the league's round quota.

## 4. The live engine

- **The data:** it loads from the store (`arena/perp/store.py`) the last 30 days of 1-minute (trade) candles of the 6 contracts, on the minute grid, with the gaps filled as in `backtest.load`. The grid is aligned so that a bar ends at 03:59, 07:59, 11:59, 15:59, 19:59 and 23:59 UTC.
- **The computation:** it calls `trend.latest(data, TrendParams(scale=2.0))`, which returns the target of each contract as a signed notional relative to equity.
- **The data guard:** if the bar's data is incomplete (more than 5% of minutes missing over a contract's last 24 h), that contract keeps its position and the incident is journaled.
- **The journal:** it receives `trend_engine_target` (portfolio, bar ts, targets per contract, z, volatility, version and sha256 of the parameters). The event is written before the deliberation.

## 5. The council (the LLMs)

It has 3 Haiku members and 1 Opus President (`claude-opus-5-5`). Each receives:
- the usual snapshot: positions, equity, leverage, news, calendar, `council_summary`;
- the engine's target;
- the engine's bench summary: what it earns in trends, what it loses in ranges.

The members:
1. **The News Watcher:** a Kraken announcement (incident, maintenance, contract in special mode) or a macro release within the coming hour justifies 0.5 or 0 on the affected contracts, for the duration of the event.
2. **The Data Controller:** inconsistent prices between sources, gaps or a stale view justify 0.
3. **The Risk Advocate:** it flags when all positions go the same way, because the 6 contracts are correlated and in practice amount to a single bet, and when the drawdown approaches the halt. It may propose 0.5. It can never propose cutting a trend because it "thinks it will reverse": the engine judges that.
4. **The President:** it decides, with a coefficient per contract in {0, 0.5, 1} and a validity duration (at most until the next bar). The default coefficient is **1**. It justifies each coefficient other than 1 in one factual sentence.

Neutral instructions:
- no doubling target;
- no incentive to trade;
- the council's role is to avoid accidents, not to predict.

If the President fails or exceeds its timeout, the coefficients are 1: the engine alone is applied.

## 6. The "engine alone" benchmark

`benchmark-perp:trend-engine` plays the same engine target at 2x, without the LLMs, through the same execution path, on the same 4-hour rounds. The gap between this benchmark and the Trend Council measures what the LLMs add or remove. It appears in the councils league.

## 7. The site

- The councils league shows:
  - the Trend Council and its engine benchmark, as a solid line;
  - the old councils (Haiku, Opus) dotted, "retired on 2026-11-17".
- On the council's page, the line of each round says:
  - the engine's target per contract;
  - the council's coefficients and their reason;
  - the orders placed.
- It displays, side by side and without embellishment, the objective (1% per day, initially 10% per day) and the realized return per day.

## 8. The cost

A round is 3 Haiku calls and 1 Opus call, about $0.06 to $0.10. With 6 to 10 rounds per day, that is under $1/day. Daily budget: $5.
