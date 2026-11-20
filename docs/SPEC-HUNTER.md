# The "Wick Hunter": specification

Origin: the v5 research of 2026-11-18 (`docs/RESEARCH-V5-AGGRESSIVE-2026-11-18.md`).

Research and sealed holdout check: `docs/RESEARCH-V5-AGGRESSIVE-2026-11-18.md`. The frozen rule is in `docs/research-v5/finalists/shocks_fade-wickS.py`.

## 1. The rule (frozen, do not modify)

For each contract (XBT, ETH, SOL, XRP, LTC, LINK):
- **shock**: `log(price_now / price_w_min_ago) < -4.5%` for w in {5, 15, 30} gives a buy; `> +4.5%` gives a sell. The rule therefore trades against the wick;
- **entry**: a position of **2x the equity** in notional (200%), in the direction opposite to the shock, with a **5% stop**;
- **exit**: at the close **60 minutes** after the entry, or at the stop;
- **lock**: no new entry on that contract for **60 minutes** after the planned exit (entry + 120 min);
- **one position at a time per contract**: while a position is held, a new shock is ignored.

On the bench, the gain disappears with delay: +37.6% on the holdout when entering at the next minute, +13.9% with 1 minute of delay, -8.1% with 5 minutes. **Speed is the whole strategy.**

## 2. The two portfolios

- **`robot-perp:hunter`**, "Wick Hunter", EUR 1,000. A dedicated process reads the prices every **5 s** and acts as soon as a shock is seen.
- **`benchmark-perp:hunter-5min`**, "5-Minute Hunter", EUR 1,000. This is the benchmark: the same rule, through the same execution path, but it decides only at the watcher's pace, once per 5-minute slice, on the first reading at HH:MM:30 or later (MM a multiple of 5, plus 3). The gap between the two measures what speed is worth.

Both are in the derivatives league.

## 3. The `python -m arena.perp.hunter run` process

It is a user systemd service `arena-perp-hunter.service` (`Type=simple`) that runs from the main checkout, like the watcher.

**Lifecycle:**
- `Restart=on-failure`, `RestartSec=10`, `RestartPreventExitStatus=2`, and `StartLimitIntervalSec=600` / `StartLimitBurst=10` in `[Unit]`: at most 10 restarts in 10 minutes. `After=network-online.target`, `MemoryMax=1G`, `Nice=0`.
- `RuntimeMaxSec=86400`: one restart per day, which reloads the specs and the config. At the deadline, systemd stops the unit with the result `timeout`, a failure for `Restart=on-failure`, which restarts it (checked with a transient unit: `systemd-run --user -p RuntimeMaxSec=3 -p Restart=on-failure sleep 1000` restarts every 3 s).
- `enabled = false` in the config: exit 0, no restart. Invalid config or hunter already running: exit 2, no restart.
- **A single process:** at startup, a non-blocking `flock` on `var-perp/hunter.lock`. If it is already held: message and exit 2. Two hunters would play every entry twice.
- If the hunter's config does not load, the watcher says so (alert `perp_hunter_config_invalid`) and **falls back to the league policy** (2x, stop at -15%, daily freeze, closing at 7 days) for both portfolios, without the hunter's controls: stricter, never looser. The hunter process itself does not start.

Its loop, every 5 s:

1. **Prices:** a single `KrakenFuturesClient.tickers(...)` call for the 6 contracts. The rule's price is the **last traded price** (`last`) when it exists and is **within 100 bp of the bid/ask midpoint**, otherwise the midpoint.
   - The in-memory history keeps the readings of the last 35 minutes.
   - At startup, it is seeded with the one-minute `trade` candles of the last 35 minutes (`client.candles`), so that a restart does not leave the hunter blind for 30 minutes.
   - The price w minutes ago is the last reading or the last one-minute close at `t - w*60` or earlier. If there is none, or if it is more than 90 s away from `t - w*60`, that window does not count.
2. **The market view:** a `PerpMarketView` built from those fresh tickers (bid, ask, mark, index, funding, ts). EUR/USD comes from the store's last reading (`market_view`), or from `client.eurusd`, if it is fresh enough for riskd. The median spread comes from the store (`market_view`).
3. **The decisions:**
   - a shock on a free, unlocked contract gives an entry, except in the "no late entry" cases below;
   - a position whose 60 minutes have elapsed gives a close.
4. **Execution:** through the standard path of the other players: `parse_decision`, then `run_intents(..., shrink=True)`, with a `PerpSimulator` on the league journal. Journal writes are already serialized by the simulator's lock, and the hunter does **not** take the watcher's lock: a watcher tick blocked by an LLM call must never delay an entry.
   - **The fill reflects the real latency.** Just before each entry, the hunter re-reads the contract's fresh ticker (one `tickers` call for that symbol). This ticker (not the one from the reading) makes up the market view, and the order is timestamped with the real time (`int(clock())`). Without a usable fresh ticker, there is no order: it is retried if still within the time limit.
   - **No long replay:** `run_intents(..., max_shrink_tries=2)`: an order refused for its size is retried smaller at most twice (the default for the other players remains `SHRINK_TRIES`, 8).
   - An entry carries `stop_pct = 5`, `horizon_h = 1` and `expected_move_pct = 1.13`. This expected move is measured: on the bench design sample, the rule makes 53 trades, with an average gross move of +113 bp. The source is written in the config, like `expected_move_source` in `config/perp-council-trend.toml`.
   - Order identifiers are deterministic (portfolio, contract, ts of the reading that saw the shock). This is **not** what prevents a second entry: the real protection is the held position (`held`, re-read from the ledger before each entry) and the single-process lock.
   - **No late entry.** No entry (neither hunter nor benchmark) when the previous successful reading is more than 30 s old, nor on the first reading after startup. A shock seen on such a reading makes an episode with no entry: it is never played. A new attempt after a refusal (spread of a wick, etc.) is allowed only within the **120 s** following the first detection of the shock (the bench loses from 5 min of delay). It does not count as a new shock (`stats.shocks`). An episode (contract, `first_seen_ts`) ends at the first reading that no longer shows the shock.
   - **The lock** is set as soon as an entry `perp_fill` exists for the intent, even if the position has already been closed (close without stop): same logic as `_restore`.
5. **The 5-minute benchmark:** it is played by the same process. It evaluates the rule only on the first reading of each 5-minute slice. It uses the same history, but only the prices known at that moment. It reasons **in slices**, with no seconds tolerance: its exit happens 12 slices after the slice of its entry, and its lock lasts until 24 slices after it. An exception during its decision does not consume the slice: the next reading replays it.
6. **Safeguards:**
   - the kill switch (`arena.ops.killswitch`) and dormancy block entries, as for the watcher;
   - a halted portfolio (`halted`) no longer plays;
   - a network error or missing data does not stop the loop: it is counted, and a `hunter_heartbeat` record is journaled at most once per hour (successful readings, errors, shocks seen, orders);
   - the "blind hunter" alert (`perp_hunter_blind`, no reading for 10 minutes, at most one per 6 h) is journaled **and sent by the notifier** (`arena/ops/notify.py`), like the watcher's alerts;
   - at startup, a journal read error is retried (10 times, every 5 s) instead of crashing; if it persists, the process exits (the unit restarts it) rather than playing without its state.

   Not every price reading is journaled.

## 4. The journal

- **`hunter_signal`** (portfolio, contract, side, window, move in bp, price, `ts` and `read_ts` of the reading that saw the shock, `first_seen_ts` of the first detection of the episode): at each entry attempt, before the order. The site counts "shocks seen" by distinct `(portfolio, contract, first_seen_ts)`: retries do not count.
- **`hunter_entry`** (portfolio, contract, intent, `read_ts`, `latency_ms` between that reading and the order, `status` `filled` or `refused`): after execution.
- **Orders and verdicts:** the standard events of `run_intents` (`perp_verdict`, `perp_fill`, `conditional_order`, ...).
- **`hunter_exit`**: at the planned close.

## 5. The risk policy

`config/policy-perp-hunter.toml`, profile `aggressive`, modeled on `config/policy-perp-council-trend.toml`:
- an order <= 200% of equity, a position <= 300%, gross leverage <= 10x;
- the same bounds on the stop, on loss at the stop per position (<= 25%) and on total open risk (<= 59%). If 5 or 6 contracts shock at the same time, the last entries are reduced (`shrink=True`);
- the edge rule is kept (cost <= 33% of the expected move of 113 bp);
- at most 48 openings per day, with no minimum delay;
- no daily freeze; halt at -60% from the peak;
- **the market checks are kept as they are** (mark/index gap, spread, data age). They may refuse an entry in the middle of a wick: that is the real market, and the refusal is journaled as for any player.

Player config: `config/perp-hunter.toml` (portfolios, names, rule parameters, expected move and its source, polling interval). It is hashed and journaled at startup.

## 6. Integration with the watcher

The watcher remains in charge of the minutes (stops within the minute, funding, margin calls, `perp_equity`). For the hunter's two portfolios, it:
- applies the hunter's policy (`policy_for`);
- **does not close** their positions for maximum holding, does not freeze them and does not halt them under the league rules (-15%): the hunter manages its own exits, like `_trend_names` for the Trend Council. The -60% halt of its policy applies;
- opens them at the first tick if the hunter has not already done so (`open_portfolio`, idempotent);
- **safety net:** closes any hunter position held for more than **3 h** (the hunter normally exits at 60 min), through `close_expired` with that threshold (reason `max_holding`);
- **the stop of the two portfolios ignores the minute of the entry** (`sim.py`, `HUNTER_NAMES` defined in `arena/perp/margin.py`): that minute's candle contains the wick being played against, and the stop applies only to minutes that start after it was armed. The other portfolios keep the usual pessimistic behavior.

**Known limitation:** each full read of the journal (about 1 s today) grows with it. The hunter does one per entry (fill reading, `run_intents`, `_refresh` every minute), and the latency of an entry grows with it. To be addressed (index or incremental read) before the journal becomes slow.

## 7. The site

The derivatives league shows the two portfolios, in a "Robots" group (no AI). Their row states:
- the rule in one sentence;
- the shocks seen;
- the trades.

The curve shows them alongside the others.

## 8. The tests (no network)

- **Detection:** a -5% shock over 10 minutes gives a buy, a +5% one a sell. A 4% move gives nothing. A window with no reference price does not count.
- **Execution:** entry at 2x with a stop, close at 60 minutes, 60-minute lock, one position at a time.
- **No second entry:** a held position prevents a new entry on the contract, the lock survives a restart (and an already closed position), and a second process exits with code 2. (Replaying the same shock in the same process has no effect, but that is not the protection.)
- **Latency and late entries:** fresh ticker before the order, order timestamped with the real time, `hunter_entry`; no entry after a gap of more than 30 s, nor on the first reading, nor more than 120 s after the first sighting of the shock; the stop ignores the minute of the entry; the watcher's 3 h net; the `last` price filtered at 100 bp.
- **The 5-minute benchmark:** it decides only once per slice, with the prices known at that moment.
- **The watcher:** it does not close a hunter position at maximum holding and applies the right policy to it.
- **The safeguards:** the kill switch blocks entries; a network error does not break the loop.
- **The rule:** on a synthetic minute series, the hunter's decisions (at one-minute cadence) reproduce those of `docs/research-v5/finalists/shocks_fade-wickS.py`.
