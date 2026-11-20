# Continuous watch and event-driven wake-ups

The fixed 4-hour scheduled round is unchanged; two mechanisms are added on top of it.

## 1. Watch: one tick every 5 minutes, no LLM

`arena watch` is launched by `arena-watch.timer` every 5 minutes (`OnCalendar=*-*-* *:00/5:30 UTC`, with a 30 s offset so it does not land exactly on HH:05:00).

1. **Lock.** The tick takes `cycle_lock` without waiting. If a cycle or a wake-up is already running, it exits without writing anything and returns code 0.
2. **Broken journal.** It writes nothing to the journal and returns code 1. A `panic` alert (ntfy only) is sent at most once per hour (state in `var/watch_journal_broken`). The cycle also alerts.
3. **Before the first cycle.** Status `inactive`, nothing is written: it is the cycle that opens the journal.
4. **Tick identifier.** `tick = now // 300 * 300`. A `watch` event already journaled for this tick makes the tick exit without writing anything (idempotency).
5. **Quotes, checked symbol by symbol.** The tick reads the Kraken ticker for the instruments in the config. Rule, per symbol:
   - **`invalid`** (bid <= 0, ask < bid, non-integer or non-finite value, read error): always rejected, never journaled in `raw_quotes`.
   - **`spread`**: spread > 5 times the median of the symbol's last 20 **raw** spreads (at least 5), that is, those from the `raw_quotes` of `watch` events, rejected ones included, so that the median follows the regime.
   - **`jump`**: mid at 15% or more from the mid of the last accepted quote for that symbol if it is less than 30 min old; otherwise (stale or missing history) from the last 4h close in the bar store, with the same tolerance.
   - **Breakout confirmation.** A quote rejected for `spread` or `jump` is ACCEPTED if the previous tick for that symbol (less than 10 min earlier) was also rejected for `spread` or `jump`, or accepted by confirmation, and if the two raw mids are within 2% of each other. Two consistent ticks are no longer an artifact. The accepted quote becomes the new reference for `jump`; the symbol then appears in `confirmed`. Chained acceptance is capped at 6 consecutive ticks (30 min): beyond that, the symbol is rejected (`watch_symbol_discarded` is sent at the 3rd consecutive rejection and equity stays at the last accepted quote) until the raw median has caught up with the new regime. Example: a stable -20% crash is rejected at the 1st tick and accepted at the 2nd, where the stop fires.
   - A rejected quote has neither a stop nor a move trigger; equity values it at its last accepted quote.
   - The tick fails only if no symbol has a usable quote (all `invalid`): nothing is written and the exit code is 1. If all are merely rejected (`spread`, `jump`), the tick is written (`quotes` empty, `raw_quotes` full): without this, confirmation would never have a previous tick.
   - **Alerts.** `action/watch_symbol_discarded` after 3 consecutive rejections of the same symbol (once per episode), then `info/watch_symbol_discarded` when it is accepted again.
   - The number of consecutive failed ticks is kept in `var/watch_failures` (outside the journal). The `action/watch_data` alert is sent once, at the third consecutive failure (start of the outage); nothing after that; at the first successful tick, an `info/watch_data` "recovered" alert is sent and the file disappears.
6. **Live trades and stops.** Stops and the move are judged on **actual trades**, never on the ticker: at every tick, for each symbol, the Kraken client reads OHLC at `interval=1` (one-minute candles, `since` = tick - 66 min). Only candles closed at the tick count (`ts + 60 <= tick`). If the read fails (or returns nothing) for a symbol, there is neither a stop nor a trigger on that symbol at that tick: the cycle's bar safety net stays in place and the tick records it in `rejected` (`"ohlc"`, in addition to any quote rejections: a symbol whose ticker is accepted keeps its quote).
   - **Condition.** A position that has a stop is sold if, among the closed 1-min candles **with volume > 0** (a filler candle repeats a price: it does not count) since `max(tick - 600, actual execution time of the buy)`, **at least 2 distinct candles** have a low `<= stop`. The actual execution time is the `ts` of the last `quote` or `wakeup_quote` event for that symbol that precedes the opening fill (the fill's `ts` is the decision instant, not the execution instant). A single isolated aberrant candle is not enough: we wait for the next tick. There is no longer a two-tick confirmation: the trades are the confirmation.
   - **Price.** `min(stop, max(1-min close x (1 - slippage), raw ticker bid x (1 - slippage)))`, rounded down to the tick, with taker fees (computed on the final price): a single erroneous feed gives at worst a sale at the stop; with no readable ticker, the 1-min close alone. A computed price `<= 0` is ignored.
   - `order_id`: `stop:{portfolio}:{symbol}:watch:{tick}`; the sale goes through `SimExecutor._forced_sell` (reason `stop`, ts = tick), idempotent by `order_id`. Any fill (`_forced_sell`) whose price or quantity is `<= 0` raises before writing.
   - The stop check on 4h bars, at the next cycle, remains the safety net: it starts from the replayed positions, so a position already sold is not sold again.
   - A watch stop wakes nobody (see §2).
   - **The ticker** is now used only to value `watch.equity` (acceptance rule of point 5, unchanged), to bound the price of a stop (above) and for the execution `wakeup_quote`s of intents.
   - **Frozen season.** The freeze status (see RUNBOOK "Season 1") is computed at the start of the tick: if a frozen hash has changed without a waiver, no fill is written (neither stop nor wake-up), the `panic/season_frozen` alert is sent once, and the `watch` event carries `"freeze": true`.
   - **Candle reads.** `since` = tick - 81 min (1 h window + 15 min reference tolerance + the previous tick). Rate limit (HTTP 429, read with its `Retry-After`, or `EAPI:Rate limit`): OHLC calls are suspended until it expires (300 s by default; state in `var/watch_ohlc_pause`), and the affected symbols are noted `"ohlc"` in `rejected`. At least 3 symbols in `ohlc` for 3 consecutive ticks: `action/watch_ohlc` once, then `info` on recovery. A tick with no readable candle at all is written but counts in `var/watch_failures` (`watch_data` alert at the 3rd).
   - **AssetPairs** is cached for 24 h in `var/asset_pairs.json` (one call per day instead of one per tick; falls back to a stale cache if the call fails). The cycle, for its part, calls AssetPairs at every run.
7. **`watch` event**, written AFTER the stops (and after `wakeup_started` if there is a wake-up), timestamped at the tick:

   ```json
   {"tick": 1794500100,
    "quotes": {"BTC/EUR": [bid_ueur, ask_ueur], "...": [0, 0]},
    "raw_quotes": {"BTC/EUR": [bid_ueur, ask_ueur], "ETH/EUR": [bid_ueur, ask_ueur], "...": [0, 0]},
    "rejected": {"ETH/EUR": "jump", "XRP/EUR": "ohlc"},
    "confirmed": [],
    "variations_bp": {"BTC/EUR": 120, "...": 0},
    "closes_1m": {"BTC/EUR": close_ueur_of_the_last_closed_1_min_candle, "...": 0},
    "equity": {"llm:claude-haiku-5-5": equity_ueur_at_bid, "...": 0},
    "stops": ["stop:llm:...:watch:1794500100"],
    "wakeup": null,
    "refused": null,
    "freeze": false}
   ```

   - `quotes`: the accepted quotes. `raw_quotes`: bid and ask of ALL symbols received, rejected ones included, except `invalid`. `rejected`: `{symbol: reason}` of the discarded quotes (`{}` otherwise). `confirmed`: the symbols accepted by breakout confirmation. `variations_bp`: per symbol, the change at the current tick measured on 1-min candles (signed bp), for the symbols whose OHLC read succeeded. `closes_1m`: the close of the last closed 1-min candle, per symbol (the PRICE_SANITY basis at wake-up). `rejected` may contain `"ohlc"` (candle read failed).
   - `wakeup`: the trigger of the wake-up actually started by this tick (§2), otherwise `null`. `refused`: the reason of the guardrail that refused a trigger (`delay`, `cap`, `before_cycle`, `cycle_incomplete`, `cycle`), otherwise `null`.
   - Size: about 288 events per day.
   - The ledger ignores this type; the site uses it for live equity.
   - The cycle's `quote` events are unchanged: the cycle's spread median reads only `quote` events.
8. **What the watch does not do.** No flattening on circuit breaker (`arena kill --now` already does that). No freeze, no drawdown halt, no maximum holding: all of that stays with the cycle and the wake-up.

## 2. Event-driven wake-ups

A wake-up is an off-schedule decision round for **all the LLM portfolios in the config and `benchmark:random`**. The random trader is the null benchmark for the LLMs: it keeps the same number of opportunities to decide as they have. The reference benchmarks (basket, 6040, E0065) stay on the 4h schedule.

### Trigger: the move, and only the move

Measured on **trades** (closed Kraken 1-min candles **with volume > 0**; the ticker no longer plays a part). Change of an instrument at a tick T = close of the last closed traded candle / close of the last closed traded candle at `T - move_window_s` or before (within 15 min) - 1. The trigger requires `|change| >= move_threshold_bp` **at the current tick AND at the previous tick (T - tick_s), in the same direction**. The previous tick is re-judged with its own candles (same call). Without a reference candle, or without a traded candle less than 15 min old, there is no measurement and no trigger; a symbol whose OHLC read fails has none either.
- Payload: `{"type": "move", "symbol": ..., "variation_bp": ..., "window_s": ...}` (`variation_bp` signed, from the current tick). If several instruments exceed the threshold, the largest `|change|` wins. The measured change of each symbol is in `watch.variations_bp`.
- There is **no "stop" trigger anymore**: it exposed a rival's position and let a single model consume everyone's cap. A stop that is hit is executed by the watch, period.

### Guardrails, all required

Evaluated in this order; the first one that refuses gives the reason in `watch.refused`.
- `cycle_incomplete`: a cycle is running or incomplete (`cycle_started` without `cycle_completed`, more recent than the last completed one).
- `cycle`: the tick is a multiple of `interval_s` (the wake-up identifier would collide with that of a cycle).
- `delay`: at least `cooldown_s` must have elapsed since the last LLM decision round: the most recent of `cycle_completed`, `wakeup_started`, `wakeup_completed` and `wakeup_abandoned` (wall-clock time).
- `cap`: at most `max_wakeups_per_day` wake-ups per UTC day; started wake-ups count, abandoned ones included.
- `before_cycle`: no wake-up within `pre_cycle_guard_s` of the next scheduled round (the execution of the next cycle, HH:05 UTC).
- The circuit breaker and dormancy do not prevent a wake-up; riskd refuses entries there, as in the cycle.

Parameters in `config/arena.toml`, `[watch]` table (default values):

```toml
[watch]
tick_s = 300
move_threshold_bp = 300      # 3%
move_window_s = 3600         # over 1 h
cooldown_s = 3600
max_wakeups_per_day = 6
pre_cycle_guard_s = 1800
```

### Sequence, in the same process and under the same lock as the tick

- **Identifier.** `wakeup = tick`, a multiple of 300 that is not a multiple of `interval_s`. It fills the `cycle` field of `decision_requested`, `decision_received`, `decision_skipped` and `intent`.
- **The wake-up is recorded first.** `wakeup_started {"wakeup": tick, "trigger": {...}}` is written BEFORE the `watch` event and before any network call of the wake-up; then `watch`, then the round, then `wakeup_completed {"wakeup": tick}`.
- **Resumption.** A `wakeup_started` without `wakeup_completed` is resumed by the following ticks, as long as it is at most 30 min old AND no `cycle_completed` has been journaled after it. Decisions already received are not requested again, and the executor is idempotent by `intent_id`. Quotes come from the originating tick: the `wakeup_quote`s already written for this wake-up are re-read without being rewritten, and the missing ones (crash during the write) are completed from the accepted quotes of the `watch` event of the originating tick; the quotes of the resuming tick are never used (all models in a round see the same quotes). A symbol still without a quote is never silently ignored: each intent that targets it receives a rejected `risk_verdict` `NO_QUOTE` and a `RISK_REJECTED` order (same rule in the cycle). One alert per wake-up and per code (`[wakeup N]` in the message). A tick that resumes a wake-up does not start a new one (`watch.wakeup` is `null`).
- **Abandonment.** Otherwise the wake-up is abandoned: the round is first repaired (a fill without `stop_set` receives its stop from the intent, via the executor's `_repair`; SUBMITTING or ACKED orders become UNKNOWN then CANCELED), then `wakeup_abandoned {"wakeup": tick}` is written.
- **Data.**
  - The 4h bars are updated. The last closed bar must be the one ending at `floor(tick / interval) * interval`, otherwise `data_stale`.
  - The tick's accepted quotes are journaled as **`wakeup_quote`** (same payload as `quote`) before the decision. They distort neither the cycle's spread median (`_view` reads only `quote`) nor the site. A discarded symbol is not tradable at wake-up; its positions are valued at their last accepted quote.
  - Marks are at the mid of these quotes.
  - **PRICE_SANITY**: the "last close" given to riskd is the close of the last closed 1-min candle (`watch.closes_1m` of the wake-up tick), and not the 4h close (otherwise a move of more than 3% would make every buy impossible) nor the ticker (so an erroneous ticker blocks entries). In the cycle, nothing changes.
- **Before deciding.** Resolution of UNKNOWN orders, freeze and halt (`_freeze_halt`), then circuit breaker and dormancy. For these checks and for flattening, each symbol is valued at `max(accepted bid, 1-min close from the tick's watch event)`: a single erroneous feed (a ticker that is too low) can neither freeze nor halt a portfolio.
- **Circuit breaker re-read.** `killswitch.active_sources` is re-read just before the execution of each intent, at wake-up as in the cycle: a KILL armed during the LLM call blocks the buy.
- **No equity.** No `equity` event at wake-up: equity series, Sharpe and statistics stay on the 4h schedule. Live equity is in `watch`.
- **Budget.** The daily quota guardrail (`daily_budget_usd`) applies to wake-ups as to cycles.
- **Site.** The watch process no longer rebuilds the site. `systemctl start --no-block` of an already-active oneshot does not chain a second build: a wake-up that finishes during a build does not trigger a new one (the site catches up at the next wake-up or cycle). After a completed wake-up, `arena watch` launches `systemctl --user start --no-block arena-site-build.service` (oneshot, `arena build-site`); a launch failure is ignored and written to the process logs, not to the journal. `--no-site` suppresses this launch.

### Snapshot given to the model

- `SCHEMA_VERSION` becomes `2`.
- A new `"context"` field:
  - in the cycle: `{"type": "scheduled_round", "next_scheduled_round_ts": ...}`;
  - at wake-up: `{"type": "wakeup", "trigger": {...}, "next_scheduled_round_ts": ...}`.
  - `next_scheduled_round_ts` is the execution of the next cycle (HH:05 UTC); `smoke_snapshot` uses the same value.
- The system prompt says that the model is called at a fixed round every 4 h, that it may be woken up between two rounds when an instrument moves by at least the threshold within 1 h, that `context` says which of the two applies, and that nothing obliges it to act. `prompt_sha256` therefore changes, and `config_loaded` is journaled.
- `recent_decisions` includes the decisions of wake-ups; each item carries `"llm_round": "wakeup"` or `"scheduled_round"`.

## 3. The cycle

- **Lock.** The cycle waits for the lock for up to 600 s (`LOCK_WAIT_S`), so as not to fail if a wake-up is finishing; `arena-cycle.service` goes to `TimeoutStartSec=1500`. `arena kill --now` (`flatten_now`) keeps a 120 s wait.
- **Missing-watch alert.** The cycle alerts (`action/watch_absent`, once per absence) if the last `watch` event is more than 30 min old when there has already been one.
- **The rest is unchanged.**
  - `_stops` on bars remains the safety net.
  - `watch` and `wakeup_*` events and wake-up decisions do not count as cycles.
  - riskd's counters (trades per 24 h, orders per minute, monthly fees) see them, since they read the journal.

## 4. Out of scope, and known limitations (not fixed)

- Limit orders and venue-side stops.
- Flattening on drawdown between two cycles.
- For a position opened by a wake-up, the 4h bar safety net acts only from the next bar onward (bars started before the entry are ignored); in the meantime only the watch's live stop protects it.
- The cost of a tick grows with the journal (full re-read at every tick): about 1.4 s at 30 days, about 17 s at one year. An incremental read is to be done after Season 1.
- The possible loss of the random trader's orders in case of a crash while writing a batch of intents already existed in the cycle.
- During the 2 ticks of a ticker break (10 min), `watch.equity`, freeze and halt value the symbol at its last accepted quote. The stops, for their part, do not depend on the ticker: they fire at the first tick where 2 1-min candles are below the stop.
- A one-minute candle exists only if there were trades: an instrument with no trade during the window has neither a stop nor a move measurement at that tick. The candle of the current minute is never read.
