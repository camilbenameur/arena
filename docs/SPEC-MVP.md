# MVP specification (paper, spot crypto)

This document is the contract between modules. A module that needs a deviation reports it instead of inventing one.

## 0. Rules for anyone writing code here

- **No real orders, no venue keys** in the MVP. Everything is `venue_mode = "paper"`.
- **Never read, print, copy or create** anything in `~/.config/arena/secrets/`: secrets are placed there by the operator. The code reads these files at run time; tests use fakes.
- Write nothing outside this repository. Do not touch the separate lab repository (not public); the sealed lab holdout (not public) is neither read nor written.
- No new dependency without declaring it in the report (`pyproject.toml` is maintained centrally; do not run `uv add`).
- Python 3.12, `uv run pytest`. Tests run without network by default; a network test carries the `network` marker.
- Comments and docstrings in English; code names in English, consistent with `arena/types.py`.

## 1. Scope and promise

An arena of 3 Claude models (Haiku 5.5, Sonnet 5.5, Opus 5.5) and benchmarks, which decides every 4 h on Kraken's spot EUR crypto, in paper trading with pessimistic fees. Every decision, every simulated fill and every figure is journaled, replayable and displayed on a private dashboard labelled SIMULATED. Alerts work even if the host goes down. No P&L promise, no ranking.

Universe (6 pairs, all listed in EUR on Kraken and in USDT on Binance):

| Symbol | Kraken (altname) | Binance (E0065 signal only) | tick | min order | min cost |
|---|---|---|---|---|---|
| BTC/EUR | XBTEUR | BTCUSDT | €0.1 | 0.00006 | €0.45 |
| ETH/EUR | ETHEUR | ETHUSDT | €0.01 | 0.002 | €0.45 |
| SOL/EUR | SOLEUR | SOLUSDT | €0.01 | 0.05 | €0.45 |
| XRP/EUR | XRPEUR | XRPUSDT | €0.00001 | 4 | €0.45 |
| LINK/EUR | LINKEUR | LINKUSDT | €0.00001 | 0.35 | €0.45 |
| LTC/EUR | LTCEUR | LTCUSDT | €0.01 | 0.08 | €0.45 |

(Values read from `https://api.kraken.com/0/public/AssetPairs` on 2026-11-11; to be reloaded at startup.)

## 2. Units

See `arena/types.py`: integer µEUR, quantities in 1e-8, timestamps in UTC seconds, unfavorable rounding. No float anywhere in the money path.

## 3. Layout

```
arena/
  types.py          contracts
  journal.py        hash-chained JSONL journal, reading, verification, replay
  ledger.py         portfolio state derived from the journal, P&L, derived SQLite
  data/kraken.py    4h candles, ticker, AssetPairs (public API)
  data/binance.py   public 1d candles (taker_buy_base) for E0065
  data/store.py     local candle cache, gap detection
  risk/policy.py    loading and consistency of config/policy.toml
  risk/riskd.py     evaluate(intent, state, market, policy, counters)
  deciders/llm.py   LLM decider harness (snapshot, prompt, schema)
  deciders/prompt/  versioned system prompt
  sim/fills.py      pessimistic fill simulator, stops, maximum holding
  sim/executor.py   order state machine, simulated execution
  benchmarks/       basket, 60/40, adapted E0065, random (live + 1,000 paths)
  stats.py          returns, drawdown, Sharpe and block-bootstrap interval
  cycle.py          one 4h cycle end to end, idempotent
  ops/              heartbeat, ntfy, circuit breaker, dormancy
  site/             static dashboard generator
  cli.py            `arena <command>`
config/policy.toml  paper risk policy (hashed into the journal at each load)
config/arena.toml   universe, capital, cadence, models, budgets
var/                runtime state, ignored by git (journal, cache, built site)
tests/              one test file per module, golden scenarios in tests/golden/
```

## 4. Journal (source of truth)

- File `var/journal/events.jsonl`, one line per event, append-only.
- Fields: `seq` (integer, from 0, no gaps), `ts` (UTC s), `type`, `payload` (object), `prev_hash` (hex, `"0"*64` for seq 0), `hash`.
- `hash = sha256(canonical(record without "hash"))`, `canonical` = `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` encoded as UTF-8. No float in an event (integers, strings, booleans, null, lists, objects).
- Writing: exclusive `fcntl.flock` lock on a `.lock` file, re-read of the last line for `seq`/`prev_hash`, write, `flush` + `os.fsync`. A truncated line at the end of the file (crash) is detected by `verify()` and reported, never silently repaired.
- `verify(path) -> VerifyReport`: chain intact, seq continuous, no float.
- Event types (minimal payload; a module may add fields, never remove any):

| type | payload |
|---|---|
| `config_loaded` | `policy_sha256`, `config_sha256`, `prompt_sha256`, `git_head` |
| `cycle_started` / `cycle_completed` | `cycle` |
| `bar` | fields of `Bar` (only the bars used by a cycle) |
| `quote` | fields of `Quote` |
| `portfolio_opened` | `portfolio`, `kind` (`llm`/`benchmark`), `capital_ueur`, `venue_mode` |
| `decision_requested` | `portfolio`, `cycle`, `model`, `snapshot_sha256` |
| `decision_received` | `portfolio`, `cycle`, `model_requested`, `model_returned`, `raw_text`, `parsed` (or null), `parse_error`, `input_tokens`, `output_tokens`, `cost_uusd` (micro-dollars), `latency_ms` |
| `decision_skipped` | `portfolio`, `cycle`, `reason` (`no_key`, `budget`, `frozen`, `halted`, `kill_switch`, `api_error`) |
| `intent` | fields of `Intent` |
| `risk_verdict` | fields of `Verdict` |
| `order_state` | `order_id`, `state`, `detail` |
| `fill` | fields of `Fill` |
| `stop_set` | `portfolio`, `symbol`, `stop_ueur` |
| `equity` | `portfolio`, `cycle`, `cash_ueur`, `positions_value_ueur`, `equity_ueur` |
| `portfolio_frozen` / `portfolio_halted` / `portfolio_resumed` | `portfolio`, `reason`, `until_ts` |
| `kill_switch` | `active`, `source` |
| `alert` | `level` (`info`/`action`/`panic`), `code`, `message` |

- `ledger.replay(events) -> dict[str, PortfolioState]` rebuilds the entire state from the journal alone. The SQLite file `var/ledger.sqlite` is a derived view, rebuildable at any time (`arena rebuild-ledger`), never a source.

## 5. Data

- Kraken `GET /0/public/OHLC?pair=<altname>&interval=240&since=<ts>`: the last bar returned is **still forming**; exclude it. Conversion of text prices to µEUR **without going through float** (`Decimal`). Volume in 1e-8 units.
- Kraken `GET /0/public/Ticker?pair=...`: `a[0]` ask, `b[0]` bid -> `Quote`.
- Kraken `GET /0/public/AssetPairs`: tick, ordermin, costmin.
- Binance `GET /api/v3/klines?symbol=...&interval=1d`: only for the E0065 benchmark signal (column 9 = taker_buy_base, column 5 = volume). Public data, no account.
- Cache `var/data/<source>/<symbol>_<interval>.jsonl`, deduplicated by `ts`. `gaps()` lists the missing bars. Limits respected: 1 request/s, 3 attempts, exponential backoff, max delay 10 s.
- The snapshot given to the models contains **only** bars closed before the cycle: a test checks there is no future leakage.

## 6. Portfolios

- Paper capital: **€1,000 per portfolio** (close to the future real amount, so that fees weigh as they would in reality).
- Portfolios: `llm:claude-haiku-5-5`, `llm:claude-sonnet-5-5`, `llm:claude-opus-5-5`, `benchmark:basket`, `benchmark:sixty-forty`, `benchmark:e0065`, `benchmark:random`.
- Long only, no leverage, cash in EUR (no interest).

## 7. Risk (`riskd`): paper policy

`config/policy.toml` (paper values; the real policy will be stricter). The `basket`, `sixty-forty` and `e0065` benchmarks are references and do not go through the size caps; `benchmark:random` goes through **exactly** the same rules as the LLMs.

| key | value | rule |
|---|---|---|
| `symbols` | the 6 | whitelist (code `NOT_WHITELISTED`) |
| `max_order_bp` | 2000 | buy <= 20% of equity (`MAX_ORDER_SIZE`) |
| `max_position_bp` | 4000 | position per symbol <= 40% of equity after the order (`MAX_POSITION`) |
| `max_exposure_bp` | 10000 | total exposure <= 100%, cash >= 0 after fees (`MAX_EXPOSURE`, `INSUFFICIENT_CASH`) |
| `max_trades_per_day` | 2 | per portfolio, sliding 24 h window, sells included (`DAILY_TRADES`) |
| `max_orders_per_minute` | 20 | all portfolios; 7 portfolios x 2 actions decide at the same instant in paper; to be brought down to 5 per venue in live trading (`ORDER_RATE`) |
| `min_interval_same_symbol_s` | 14400 | anti-oscillation (`TOO_SOON`) |
| `stop_bp_min` / `stop_bp_max` | 100 / 2500 | buy without a stop or outside the bounds -> rejection (`STOP_REQUIRED`, `STOP_RANGE`) |
| `max_cost_to_expected_move_pct` | 33 | estimated round-trip cost <= 33% of the declared expected move (`EDGE_TOO_SMALL`); missing move -> rejection |
| `max_holding_s` | 604800 | 7 days, exit forced by the simulator |
| `daily_loss_freeze_bp` | 500 | loss >= 5% of equity over 24 h -> 24 h freeze (`FROZEN`) |
| `drawdown_halt_bp` | 2000 | drawdown >= 20% from the peak -> flatten and halt until `arena resume` (`HALTED`) |
| `monthly_fee_budget_bp` | 100 | calendar-month fees >= 1% of start-of-month equity -> freeze until the next month (`FEE_BUDGET`) |
| `max_quote_deviation_bp` | 300 | quote mid more than 3% from the last close -> no entry (`PRICE_SANITY`) |
| `max_spread_multiple` | 3 | spread > 3 x the median of the last 20 quotes -> no entry (`SPREAD_ANOMALY`) |
| `min_order_ueur` | max(Kraken costmin, €5) | (`ORDER_TOO_SMALL`) |

- `evaluate()` is a **pure function**: same inputs -> same verdict. The counters (trades over 24 h, orders per minute, monthly fees) are computed **from the journal** and passed as an argument.
- A sell can never exceed the position held (no short selling: `NO_SHORT`). Sells are not subject to `EDGE_TOO_SMALL` nor to the size caps.
- Circuit breaker (file `var/KILL` or `~/.config/arena/KILL`): no entries; the LLM and random portfolios are flattened at the next cycle.
- `policy.py` checks consistency at load time (bounds, `stop_bp_min < stop_bp_max`, positive budgets, known symbols) and refuses to start otherwise. Policy hash in every verdict.

## 8. Simulated execution (`fill_model_version = "pessimiste-v1"`)

- Market orders only (taker). Buy at `ask x (1 + 5 bp)`, sell at `bid x (1 - 5 bp)`, rounded to the tick unfavorably.
- Fees: `0.50%` of the notional (Kraken Pro base taker 0.40% plus 25%), rounded up.
- Quantity rounded down to 1e-8; rejected if below `lot_min_qty` or `cost_min`.
- Stops: set at entry (`stop_ueur = entry price x (1 - stop_bp/10000)`). At each cycle, for each closed 4h bar since the last cycle: if `low <= stop`, exit at `min(stop, open)` (gap) minus 5 bp, fees included (`reason = "stop"`).
- Maximum holding: forced exit at the cycle's bid (`reason = "max_holding"`).
- State machine: `INTENT -> RISK_APPROVED | RISK_REJECTED -> SUBMITTING -> ACKED -> FILLED`, each transition journaled. In paper mode `UNKNOWN` can be simulated for tests (fault injection): a second order is never issued for the same intent, the state is queried instead; an `UNKNOWN` order lasting more than 2 cycles freezes the portfolio.
- Idempotency: an `intent_id` already seen in the journal is never re-executed.

## 9. LLM deciders

- `anthropic` SDK (Python). Models: `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`. The identifier returned by the API is journaled; alert if it differs from the one requested.
- Key read at run time from `$CREDENTIALS_DIRECTORY/anthropic_api_key`, otherwise `~/.config/arena/secrets/anthropic_api_key`. **No key -> `decision_skipped` with `no_key`**; the rest of the arena keeps running.
- Snapshot (same for the 3 models): cycle timestamp, for each symbol the last 42 4h bars (7 days) summarized as features computed by the code (4 h / 24 h / 7 d returns, realized volatility, price position within the 7-day range, relative volume) + the last 12 closes; positions, cash, equity, stops, unrealized P&L; risk rules in plain language; the portfolio's last 5 decisions (short summary). No web text.
- Requested output as JSON (tool or SDK structured output):
  `{"actions": [{"symbol", "side": "buy"|"sell", "size_pct": 0-20 (buy, % of equity) or 0-100 (sell, % of the position), "stop_pct": 1-25, "horizon_h", "expected_move_pct", "confidence_pct"}], "justification": "<= 1,200 characters"}`; 0 to 2 actions; `actions: []` = do nothing.
- Conversion to `Intent` by the code (percentages -> basis points, integers). Invalid JSON -> `parse_error`, no intent, no further retry beyond 1.
- Per-model daily budget (USD) in `config/arena.toml`: Haiku 0.10; Sonnet 0.50; Opus 0.90 (about $45/month in total, under the key's $50 limit). Budget exceeded -> `decision_skipped budget`. Cost computed from the tokens and a price table in the config (Opus 4/20, Sonnet 2/10, Haiku 0.10/0.50 $ per million tokens, input/output).
- `max_tokens` bounded, default `temperature`, max timeout 120 s, 2 attempts on network error or 5xx/529, never on 4xx.
- System prompt versioned in `arena/deciders/prompt/v1.md`, hash journaled.
- Tests with a fake client (no network call): valid JSON, invalid, off-list, negative or huge sizes, injection in the justification, budget overrun, different returned model. 20 frozen snapshots in `tests/golden/snapshots/` checked against invariants (not exact responses).

## 10. Benchmarks

- `benchmark:basket`: at the first cycle, 1/6 of equity on each symbol (fees included), then held (buy-and-hold).
- `benchmark:sixty-forty`: 60% BTC / 40% cash, rebalanced at the first cycle of each calendar month.
- `benchmark:e0065`: rule F1 of the separate lab repository (not public; "persistent taker buying pressure"), parameters L = 20, k = 3, H = 10, **adapted**: universe of the 6 pairs, taker ratio computed on Binance USDT 1d candles, execution at the Kraken EUR price; reconstituted every H days of data at the first cycle after 00:00 UTC. Labelled "adapted" everywhere.
- `benchmark:random`: at each cycle, with a seed derived from the cycle, draws 0 to 2 actions from the same action-space distribution as the LLMs (uniform symbol, uniform side among the possible ones, uniform size 1-20%, stop 2-10%, expected move 5-15%), goes through `riskd`. Offline (when building the site), 1,000 paths replayed over the same cycles and the same quotes give the return distribution; the rank of each LLM is displayed.

## 11. Cycle

`arena cycle` (launched by a systemd user timer at HH:05 UTC for HH in {0,4,8,12,16,20}):
1. Load config and policy (hash), verify the journal (`verify`), refuse to run if the chain is broken.
2. Cycle = start of the last closed 4h bar + 4 h. If `cycle_completed` already exists for this cycle: exit (idempotency). If `cycle_started` without `completed`: resume without re-executing the intents already seen.
3. Data (bars, quotes), journal those used.
4. Stops and maximum holding.
5. Freeze / halt / circuit breaker / dormancy.
6. Benchmarks, then LLM deciders in parallel (max timeout), then `riskd`, then simulated execution.
7. Equity of each portfolio, `cycle_completed`.
8. Site build, external heartbeat, alerts.

## 12. Operations

- systemd **user** units (`~/.config/systemd/user/`, linger enabled): `arena-cycle.service` + `.timer`, `arena-site.service` (serves `var/site/` on `127.0.0.1:8787`). Template files in `ops/systemd/`, installation by `scripts/install-user-units.sh` (no sudo).
- External heartbeat: URL read from `~/.config/arena/secrets/healthcheck_url` (Healthchecks.io or equivalent, account created by the operator), pinged at the end of each cycle; `/fail` if the cycle fails. The external service alerts if no ping arrives within 4 h 30.
- Alerts: ntfy, URL in `~/.config/arena/secrets/ntfy_url` (+ optional `ntfy_token`). 3 levels; only `panic` is high priority. Without a secret, the alert is written to the journal only.
- Circuit breaker: `arena kill` / `arena unkill` (sentinel file), effective at the next cycle at the latest; `arena kill --now` launches an immediate flattening cycle.
- Dormancy: if `var/ack` (written by `arena ack`) is more than 7 days old, no more entries; at 9 days, flatten.
- `docs/RUNBOOK.md`: one page.

## 13. Dashboard (private)

- Generated by `arena build-site` into `var/site/`: `index.html`, `model/<id>.html`, `method.html`, `data/*.json`. HTML/CSS/JS with no build chain; uPlot charts copied into `site/vendor/` with their hash.
- Permanent **SIMULATED (paper)** banner. The `venue_mode` field is mandatory in every published JSON, validated by a test.
- Overview: equity of the 7 portfolios on a base of 100, net return, max drawdown, fees, number of trades, API cost per model, rank in the random distribution, with the note "indistinguishable from chance" as long as the gap is not significant.
- Model page: curve, positions, decision log (justification published as soon as the decision is made; in the first version it was displayed 24 h later), `riskd` rejections by code.
- Method page: rules, fees, policy, journal hash (chain head), honest limitations.

## 14. MVP acceptance criteria

Tests green; `verify()` OK; replay = ledger = site to the µEUR; `riskd` accepts no violation over 100,000 generated intents (hypothesis); circuit breaker effective in < 1 min with `--now`; simulated outage -> external alert; real cost per decision measured.
