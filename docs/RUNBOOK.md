# Arena runbook (paper)

Everything is launched from the repository directory with `uv run arena <command>`. State lives in `var/`, secrets in
`~/.config/arena/secrets/` (never in the repository). Everything is **paper**: no alert concerns real money.

## Reading the state
- `arena status`: last cycle, equity per portfolio (at the bid), freezes/halts, circuit breaker, dormancy, last alert, journal verify.
- `arena verify`: is the journal chain intact? (exit code 0 = OK). Chain head = fingerprint of the whole history.
- `journalctl --user -u arena-cycle.service -n 80`: output of the last cycle. `systemctl --user list-timers arena-cycle.timer`.

## Stopping everything
1. `arena kill`: no more buys; at the next cycle the LLM and random portfolios are flattened.
2. `arena kill --now`: same, with immediate flattening (under a minute). The file `~/.config/arena/KILL` has the same effect as `var/KILL`.
3. Full stop: `systemctl --user disable --now arena-cycle.timer arena-watch.timer`. To restart: `arena unkill`, then `systemctl --user enable --now arena-cycle.timer arena-watch.timer`. (To stop only the watch: see "Watch and wake-ups".)

## Flattening everything
`arena kill --now`, then `arena status` (positions = 0 for the LLMs and the random trader). The reference benchmarks (basket, 6040, E0065) stay invested: they are references, not decision-makers.

## Confirming presence (dormancy)
`arena ack` at least once every 7 days: with no ack for 7 days, no more entries; after 9 days, the LLMs and the random trader are flattened. (With no ack at all, the count starts from the first launch.)

## Resuming a portfolio
- **Frozen** (loss >= 5% in 24 h): it restarts on its own after 24 h. To force it: `arena resume <portfolio>`.
- **Halted** (drawdown >= 20%, already flattened): understand why first (`arena status`, journal), then `arena resume llm:claude-haiku-5-5` (example). The equity peak restarts from the flat equity.

## What to do on each alert (ntfy; always in the journal too)
| code | level | action |
|---|---|---|
| `cycle_exception` | panic | Cycle interrupted. `journalctl` for the cause, `arena verify`, then rerun `arena cycle`: it **resumes** without a double fill. |
| `journal_broken` | panic | See "Broken journal". No cycle runs while `verify` fails. |
| `config_invalid` | panic | `config/arena.toml` or `policy.toml` refused: fix it (message in the alert), rerun. |
| `data_stale`, `data_error` | action | Kraken unavailable or late. Rerun `arena cycle` within the same 4h slot; otherwise the cycle is lost (gap in the curves, nothing broken). |
| `binance_data`, `e0065_data` | action | Binance 1d data missing: E0065 skips this cycle. Fixes itself. |
| `portfolio_halted` | action | Drawdown halt: see "Resuming a portfolio". |
| `portfolio_frozen` | info | 24 h freeze (loss, or UNKNOWN order > 2 cycles). Nothing to do unless `unknown_order`: read the journal. |
| `kill_switch` | action/info | Circuit breaker armed / lifted (by you, normally). |
| `dormancy_no_entries`, `dormancy_flatten` | action | `arena ack`. |
| `model_mismatch` | action | The API answered with a different model than requested: this cycle's decisions are no longer comparable; check the models config. |
| `llm_api_error`, `llm_budget` | action/info | LLM call failed or daily budget reached (decision skipped, the rest keeps running). |
| `site_build` | action | The dashboard could not be rebuilt; `arena build-site` to see the error. No effect on the journal. |
| `heartbeat_absent` | info | No `healthcheck_url`: no external heartbeat. To be set up. |
| no ping received within 4 h 30 (Healthchecks) | — | The host or the timer is down: `systemctl --user status arena-cycle.timer`, `loginctl show-user $USER -p Linger`. |

## Watch and wake-ups
Specification: `docs/WATCH.md`. The 4h scheduled round is unchanged; `arena-watch.timer` adds a tick every 5 min (HH:MM:30 UTC), with no LLM except on a wake-up.

**What a tick does** (`arena watch`): takes the cycle lock without waiting (cycle or wake-up in progress: it exits without writing anything, code 0), reads the Kraken quotes (used only to value equity and to execute the wake-up's orders) and discards the doubtful ones, reads the Kraken 1-min candles (the trades), sells any position for which at least 2 closed 1-min candles have a low below the stop (price: last 1-min close minus slippage, never above the stop, taker fees), writes a `watch` event (quotes, `raw_quotes`, `rejected`, `variations_bp`, `closes_1m`, equity, the tick's stops, wake-up, `refused`), then starts a wake-up if a move of at least 3% over 1 h, measured on trades and confirmed at the last two ticks, passes all the guardrails. A wake-up is a decision round for all the LLMs and `benchmark:random`; it writes `wakeup_started` (before the `watch` event), the decision events (`cycle` field = the wake-up identifier, a multiple of 300 s that is not a scheduled round), `wakeup_quote`s, then `wakeup_completed`, and never any `equity`. After a completed wake-up, `arena watch` asks systemd to rebuild the site (`arena-site-build.service`); `--no-site` avoids it.

**Reading**
- `journalctl --user -u arena-watch.service -n 40`: one line per tick (`watch <time>: done  events=1 ...`, with `stops=`, `discarded quotes=`, `trigger=` and `wakeup=` when they exist). `systemctl --user list-timers arena-watch.timer`. The site: `journalctl --user -u arena-site-build.service -n 20`.
- In the journal: `grep -E '"type":"(wakeup_started|wakeup_completed|wakeup_abandoned)"' var/journal/events.jsonl | tail`. A `wakeup_started` without `wakeup_completed` is a wake-up in progress or interrupted: the next tick resumes it (30 min, if no cycle has completed since), otherwise it is repaired then abandoned.
- `rejected` of a `watch` event contains `"ohlc"` for a symbol whose 1-min candle read failed: neither stop nor trigger on it at that tick (the cycle's 4h bar safety net stays active).
- A refused trigger leaves its trace in the `refused` field of the `watch` event (`delay`, `cap`, `before_cycle`, `cycle_incomplete`, `cycle`) and in the tick's output: `trigger=move (refused: delay)`.
- `arena status` does not show the watch; `arena verify` verifies it like everything else (about 290 `watch` events per day).
- State files outside the journal: `var/asset_pairs.json` (24 h AssetPairs cache, can be deleted), `var/watch_ohlc_pause` (instant until which OHLC calls are suspended), `var/watch_failures` (number of consecutive ticks with no valid quote at all; deleted at the first successful tick; do not edit it, it may be deleted) and `var/watch_journal_broken` (time of the watch's last `journal_broken` alert, so that only one is sent per hour).

**Stopping**
- No more wake-ups, live stops kept: set `max_wakeups_per_day = 0` in `[watch]` of `config/arena.toml` (effective at the next tick; `config_loaded` is journaled).
- No watch at all: `systemctl --user disable --now arena-watch.timer`. The stop safety net on 4h bars in the cycle stays active, as before. The cycle will send the `watch_absent` alert once, since the watch has already run.
- `arena kill` / `arena kill --now` act on wake-ups as on cycles: a wake-up under circuit breaker flattens the LLMs and the random trader and refuses any entry; a KILL armed during an LLM call blocks the buy that follows. The watch itself never flattens.
- Settings (`[watch]`): `move_threshold_bp` (300 = 3%), `move_window_s` (3600), `cooldown_s` (3600), `max_wakeups_per_day` (6), `pre_cycle_guard_s` (1800), `tick_s` (300, must divide `interval_s`). Any change alters the config hash.

**New alerts**
| code | level | action |
|---|---|---|
| `watch_data` | action then info | Action: no symbol has a usable quote (all invalid or unreadable) for 3 consecutive ticks (a single alert at the start of the outage; the failed ticks write nothing, exit code 1). Live stops are not running: the 4h bar safety net stays active. "Recovered" info at the first successful tick. |
| `watch_ohlc` | action then info | At least 3 symbols without readable 1-min candles (`rejected "ohlc"`) for 3 consecutive ticks: neither stop nor move on them (the cycle's 4h bar safety net stays active). On a rate limit (429, `Retry-After` capped at 600 s) OHLC calls are suspended (`var/watch_ohlc_pause`, 300 s by default). Info on recovery. |
| `season_modified` | panic | The `[season]` table was modified (other than `name`) during the open season: no effect, put it back as it was. |
| `season_number` | action | The `number` of `[season]` is not the last + 1: the season is not started. |
| `claude_cli_version` | info | The version of `claude --version` changed (not frozen, journaled in `config_loaded`). |
| `watch_symbol_discarded` | action then info | A symbol's quotes have been rejected (`spread` or `jump`, see `rejected` of the `watch` events) for 3 consecutive ticks without a coherent breakout being confirmed: erratic Kraken quotes. No stop or trigger on it, equity at its last accepted quote. Clears by itself; info on return. |
| `watch_absent` | action | Raised by the cycle: no `watch` event for more than 30 min. `systemctl --user status arena-watch.timer`, `journalctl --user -u arena-watch.service`. One alert per absence. |
| `journal_broken` (watch) | panic | The watch refuses to run on a broken journal (at most one alert per hour, ntfy only). See "Broken journal". |
| `wakeup_resumed` | info | An interrupted wake-up was resumed by a later tick (without double decision or double fill). Nothing to do. |
| `wakeup_abandoned` | action | An incomplete wake-up was repaired then abandoned (more than 30 min, or a cycle completed in the meantime). See `wakeup_exception` or `data_stale` just before; decisions already received stay journaled. It counts in the day's cap and in the delay. |
| `wakeup_exception` | panic | Wake-up interrupted by an exception: `journalctl --user -u arena-watch.service`, then `arena verify`. Later ticks resume it (up to 30 min). One alert per wake-up and per code. |
| `data_stale`, `data_error`, `llm_api_error`, `llm_budget`, `model_mismatch`, `kill_switch`, `dormancy_*` | — | Same codes and same actions as in the cycle; they may also come from a wake-up (message prefixed `[wakeup N]`, one alert per wake-up and per code). The daily budget (`daily_budget_usd`) is shared between cycles and wake-ups. |

A cycle waits for the lock for up to 600 s (`LOCK_WAIT_S`): if a wake-up holds it, the HH:05 cycle starts when the wake-up ends (`arena-cycle.service`: `TimeoutStartSec=1500`).

## Season 1
A frozen season of 8 weeks (56 days), with no change of cadence, models, prompt or risk policy. The earlier shakedown period is excluded from the rankings. `[season]` table of `config/arena.toml` (optional: without it, nothing changes): `number`, `name`, `start_ts` (2026-11-13 at 00:05 UTC, the execution of the 00:00 cycle), `duration_days`.

**Events** (all in the journal):
- `season_started`: written at the first cycle whose decision instant `t` is >= `start_ts - cycle_delay_s`, before its decisions. It freezes `config_sha256`, `policy_sha256`, `prompt_sha256`, `code_sha256`, `git_head`, the list of portfolios, `start_ts`, `duration_days` and `claude_cli_version` (output of `claude --version`, or `null`), and sets `planned_cycle_end = t + 56 days`. Refused while a season is open (a `season_started` without `season_ended`); its `number` must equal the last + 1 (otherwise alert `action/season_number`, no effect).
- `season_reference`: written BEFORE the starting cycle's decisions, right after `season_started`: `{number, cycle, equity: {portfolio: µEUR}}`, the equity of each portfolio at the bid with that cycle's quotes. It is the basis of the rankings; nothing is reset.
- `season_ended`: at the first cycle with `t >= planned_cycle_end`, after its `equity` events. The freeze is lifted afterwards.
- `season_waiver`: see below.

**What is frozen** (from `season_started` to `planned_cycle_end`): four hashes. If one differs from that of `season_started`, the cycle AND the wake-ups refuse to run, and the watch writes no more fills (`panic/season_frozen`, the message names the hash: config, risk policy, system prompt or code). A `[season]` modified during the open season (other than `name`) triggers `panic/season_modified` and has no effect. `git_head` and `claude_cli_version` are not frozen (a CLI version change is journaled in `config_loaded` and alerted as `info`).
- `config_sha256` is the sha256 of the config **without the `season` key**, computed on the parsed TOML (`tomllib`) then serialized as canonical JSON (sorted keys, no spaces): comments, whitespace and key order have no effect, any value that changes alters the hash (computation: `arena.config.sha256_outside_season`). `config_loaded` keeps the full file hash.
- `policy_sha256`: `config/policy.toml`; `prompt_sha256`: `arena/deciders/prompt/v1.md`.
- `code_sha256`: the bytes, read from disk (without git) in sorted path order, of an allowlist: `arena/__init__.py`, `config.py`, `cycle.py`, `watch.py`, `journal.py`, `ledger.py`, `types.py`, `paths.py`, `season.py`, `ops/dormancy.py`, `ops/killswitch.py`, the directories `arena/data/`, `deciders/`, `risk/`, `sim/`, `benchmarks/` (.py, .md, .toml, .json, .txt files, excluding `__pycache__`), and `config/policy.toml` (computation: `arena.season.code_sha256`). Outside the freeze: `arena/site/`, `arena/cli.py`, `arena/perp/` (perpetual-futures league), `arena/stats.py`, `uv.lock`. Any fix to the frozen code during the season, including a new module in a frozen directory, requires a written, journaled waiver. Limitation: an update of a dependency (`uv.lock`) or of the `claude` CLI is not frozen; the CLI version is journaled and alerted.

**Waiving.** Write a reason into `var/SEASON_WAIVER` (`echo "reason" > var/SEASON_WAIVER`): the cycle then journals `season_waiver {number, reason, hashes_before, hashes_after}` (once per hash change, `hashes_before` = the previous frozen state) and then runs; a wake-up runs too. Empty or missing file: the freeze applies. Delete the file once the waiver is over; every waiver is visible in `arena status` and on the site.

**Reading the rankings.** `arena status` shows the season (pending, in progress: day N of 56, or ended), the number of waivers and the performance of each portfolio since `season_reference` (equity at the bid, current or from `season_ended`). Rankings are computed from `season_reference`, never from the initial capital; the shakedown period (before `season_started`) is presented separately.

## Broken journal (`arena verify` fails)
1. **Delete nothing, edit nothing.** Copy the file: `cp var/journal/events.jsonl /path/to/backup/`.
2. `arena verify` reports the line and the code. `truncated_tail` = crash during a write (last line cut off); `hash_mismatch` / `prev_hash_mismatch` = line modified or lost.
3. A repair is a human decision, never automatic: truncate to the last valid line (`head -n <N> events.jsonl > clean.jsonl`), check with `verify`, note the incident, then replace. Lost events are lost: the current cycle will be resumed at the next `arena cycle`.
4. `var/ledger.sqlite` and `var/site/` are derived: `arena rebuild-ledger`, `arena build-site`.

## Spot checks
- `arena smoke-llm <portfolio>`: a single real call (costs a few cents), with no order and no journal. Refuses if there is no key.
- Nothing is ever sent to a venue: venue secrets do not exist in the MVP.
