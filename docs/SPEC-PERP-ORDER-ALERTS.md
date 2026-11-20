# Perpetuals league: alerts and entry orders placed by the agents

Each agent places alerts and entry orders itself, managed by the watcher between rounds, without an LLM call. Outside the Season 1 freeze: spot is not touched.

## 1. What the agent can leave at each round

The structured output gains two **optional** fields:

- `alerts`: at most 3 price alerts. An alert wakes its owner, and only the owner, when the mark crosses a level.
  `{"instrument", "condition": "above"|"below", "price_usd", "note" (≤ 120 chars, optional), "expires_h" (1-24, optional, 4 by default)}`
- `entry_orders`: at most 3 conditional entry orders. When the mark crosses the level, the watcher submits the entry to the guardrail and then executes it, without calling the model.
  `{"instrument", "side": "long"|"short", "condition": "above"|"below", "price_usd", "size_pct", "stop_pct", "take_profit_pct"?, "horizon_h"?, "expected_move_pct"?, "confidence_pct"?, "invalidation"?, "expires_h"?}`
  Same bounds as the opening actions (`BOUNDS`, horizon 1-168); `size_pct`, `stop_pct`, `horizon_h` and `expected_move_pct` are mandatory (without the last two, the guardrail would always refuse). A number sent as text is rejected.

**Each valid decision replaces the whole set.** All items of the previous set that are still pending are ended (`replaced`); an item repeated identically becomes a new item of the new set. A missing or invalid decision (failure, timeout, skipped round) touches nothing: what is placed runs until it expires.

**Validation at creation**, item by item (an invalid item is rejected and noted, the others stay), against the market **at the moment the decision is applied** (the view re-read after the call), and the items count from that moment (`created_ts`): a level crossed while the model was thinking is rejected as already crossed.
- the level is at most 25% away from the snapshot's mark;
- the level is not already crossed: `above` requires a level above the mark, `below` below it. Otherwise, an immediate entry would bypass the round;
- a `long` + `above` entry order is a breakout buy, `long` + `below` a dip buy: both are allowed.

The identifier of each item is a sha256 of (portfolio, round, type, rank, content), like the intents.

## 2. What the watcher does

At each tick, once the minutes are processed (before `_controls` and `_rounds`), **even if the market view is stale**: processed minutes are never re-examined by the next tick. The sweep starts from the last minute of the last `perp_tick` (not of a `perp_checkpoint`): a tick killed in the middle of catching up sweeps its minutes again, and a crossing already journaled is never journaled twice. Each step, and each crossing, has its own error guard.

1. **Resume** (fresh view only): the triggered entry orders that are not yet resolved (points 6 and 7).
2. **Halt:** a halted portfolio has all its items ended (`portfolio_halted`), before any crossing.
3. **Crossing**, on the newly processed closed 1-min mark candles, in order: `below` is crossed when the low ≤ level, `above` when the high ≥ level. Only the minutes that start from the creation and before the expiry count, even if the tick that sees them comes after the expiry.
4. **Expiry:** an item whose `expires_ts` has passed is expired (`expired`).
5. **Alert crossed:** `agent_alert_triggered`. It is consumed (an alert serves only once).
6. **Entry order crossed:**
   - `agent_entry_triggered`, then, with a fresh view (otherwise at the first fresh tick), if the crossing minute is less than 15 min old (`ENTRY_MAX_LAG_S`): a `PerpIntent` `open_long`/`open_short` with the order's fields and `intent_id` = the order's id, judged by `evaluate_perp` on the fresh view and the counters of the moment (leverage, mandatory stop, sizes, freeze, circuit breaker); `perp_verdict`; if approved, execution by `_execute` of `agent_round` (market order at the current price, slippage and fees, then stop and target; closing if the stop cannot be placed);
   - if the minute is older (catching up after an outage): `perp_execution` `not_executed_stale_trigger`, never executed late.
   - The order is consumed in all cases. A refusal is returned to the agent at its next round.
7. **Idempotence after a crash:** an order triggered without a `perp_verdict` is judged at the next tick (or noted `not_executed_stale_trigger` if it has exceeded 15 min); an approved verdict without a `perp_fill` is re-judged on the fresh view and then executed (`not_executed_refused_on_resume` if the guardrail now refuses), the market order being idempotent through its id; a `perp_fill` without a `perp_execution` is never replayed: if the stop is missing, the position is closed (`closed_without_stop`). Nothing is executed twice, and no position remains without a stop.

## 3. The private wake-up

A crossed alert requests an **`alert` round** for its owner alone:
- `perp_round` `{round, kind: "alert", portfolios: [<owner>], trigger: {alert_id, instrument, condition, price_usd, note}, ts}`;
- only this LLM portfolio plays. Neither the benchmarks nor the other models play, and nothing is shown to them;
- **limits:** 1 h since this portfolio's last round, at most 4 `alert` rounds per portfolio per UTC day, none within the 30 min before a scheduled round nor near a spot cycle (`near_spot_cycle`), the daily budget like any round. A crossed alert that waits more than 1 h is no longer served by a wake-up;
- one round per tick: a scheduled round or a market wake-up goes first; an `alert` round then waits for the next tick;
- **any round played by the owner serves** its pending crossed alerts: they appear in its snapshot;
- `alert` rounds count neither in the delay nor in the cap of the market wake-ups (which stay common to all).

## 4. Confidentiality

No agent sees a rival's levels, triggers or `alert` rounds:
- the snapshot and `round.json` contain only the items of the portfolio called;
- the MCP tools (`history` included) read only the events of the portfolio called;
- the trigger of a market wake-up stays a market move, never someone's alert.

The public site can display everything: the models do not read it.

## 5. What the agent sees at the next round

In the snapshot, under `account`:
- `pending_alerts` and `pending_entry_orders`: its items in progress, with level, expiry (UTC time) and what it wrote;
- `since_your_last_round`: its triggered alerts, its triggered orders (with the verdict, the refusal reasons and the fill price), its expired items, and its items rejected at creation.

The instructions (v4) describe the two fields in a few lines, without pushing to trade: placing nothing is a valid decision.

## 6. Events (`var-perp` journal)

| Type | Payload |
|---|---|
| `agent_orders_set` | `portfolio, round, alerts[], entry_orders[], rejected[] {kind, k, error}` (the replaced items each have their `agent_order_ended`); each alert `{id, instrument, condition, price_uusd, note, expires_ts}`, each order `{id, instrument, side, condition, price_uusd, size_bp, stop_bp, take_profit_bp, horizon_h, expected_move_bp, confidence_pct, invalidation, expires_ts}` |
| `agent_alert_triggered` | `portfolio, id, instrument, condition, price_uusd, minute, mark_high_uusd, mark_low_uusd` |
| `agent_entry_triggered` | `portfolio, id, instrument, side, condition, price_uusd, minute, mark_high_uusd, mark_low_uusd` |
| `agent_order_ended` | `portfolio, id, kind (alert|entry), reason (expired|replaced|portfolio_halted)` |
| `perp_round` | `kind: "alert"`, `portfolios: [name]` in addition |
| `perp_verdict`, `perp_execution`, `perp_fill`, `conditional_order` | unchanged; `intent_id` = id of the entry order |

`agent_orders_set` is written only if the decision is valid. The pending state is recomputed from the journal: the portfolio's last `agent_orders_set`, minus the items triggered or ended since.
