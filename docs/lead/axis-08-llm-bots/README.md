# Axis 8: can Claude models trade profitably? (LLM bots on post-cutoff data)

Status: harness built and hardened after two adversarial reviews; dry-run verified; one real pilot (Haiku, 2 bars, under $0.001) proved the sync path, the JSON schema and `effort`. No batch run yet.

## Question and design

Rules-based agents have mostly failed on the sealed controls (see `docs/lead/LOG.md`). Do LLM bots do better? An LLM
backtest is only honest on data the model cannot have memorised. All four current models (claude-haiku-5-5,
claude-sonnet-5-5, claude-opus-5-5, claude-fable-5-2) have a training cutoff of June 2026, so the usable data is
2026-07-01 to 2026-11-26.

| Period | Dates (UTC) | 4h decisions | Use |
|---|---|---|---|
| design | 2026-07-31 to 2026-09-30 | 372 | prompt development, at most 3 variants x 3 models |
| control | 2026-10-01 to 2026-11-26 | 342 | sealed: one run per frozen bot |

The design window starts on 2026-07-31 so that the 30-day lookback of the first decision starts on 2026-07-01, after the
cutoff (a margin: `bars.check_leak_floor` asserts it at every design run). Control is unchanged.

Data: one-year 1-minute candles and hourly funding of the six perps (`~/dev/_arena-data/axis-01`), plus the live
collector's files for 17 to 26 November (the axis-01 candles stop on 17 November; the seam is contiguous). Not modified.

## Files

- `bars.py`: loads the minute grid into the bench's `Data`, builds 4-hour bars, renders the prompt features.
- `bot.py`: system prompts (variants `v1_plain`, `v2_costaware`; one slot left), JSON schema, request builder, response parser, clients (real, fake).
- `budget.py`: hard spend ledger.
- `report.py`: evaluation through the bench, trend and basket references, random baseline, pass criteria.
- `run.py`: CLI.

## The bot

One call per 4-hour bar, all six contracts at once. Output (structured outputs, `output_config.format` JSON schema):
`{"weights": {BTC..LINK: number}, "reason": "..."}`. A weight is a multiple of equity/6, clipped to [-2, 2] (gross at most 2x).
Orders are filled at the next minute's open with the bench's costs: 5 bp slippage + 7 bp fee per side (24 bp round trip), hourly
funding. No temperature and no `thinking` field (Opus 5.5 and Fable 5.2 reject them): depth is `output_config.effort`
(default low for Haiku and Sonnet, medium for Opus and Fable, `--effort` to change). `max_tokens` 16000 including thinking (Opus 5.5 / Fable 5.2 at medium effort must not be cut off; the worst-case reservation uses the same constant; truncations, `stop_reason` max_tokens, are counted per bot in the report and hold the position).
The stable system prompt carries `cache_control`. A `refusal`, `max_tokens`, malformed or missing answer means **hold**
(previous target kept). Same bench as the rules: `arena.perp.lab.backtest.run`.

Two execution paths, which are two different bots (the mode is part of the bot id):
- **batch (default, -50%)**: Message Batches API, one request per bar keyed by `custom_id`, results in any order. A batch
  cannot feed a decision into the next one, so the prompt is **stateless**: the bot is not told its positions or equity.
  Persistence comes only from consistent reading of the market. Results are collected with `--collect` if the run is interrupted.
- **sync**: one call per bar, **stateful** prompt (own weights, equity index, drawdown, cost paid; an approximate track
  record). Full price.

## Leak controls

1. Only data after the cutoff is scored (design and control are both after June 2026).
2. No calendar date or absolute timestamp in any prompt: bars are "t-0, t-1..."; the system prompt tells the model not to guess the period.
3. No price level: returns, ratio to the 30-day mean, drawdown from high, volatility, funding. The 30-day lookback of the first design decision starts on 2026-07-01, never in June (design starts 2026-07-31).
4. Nothing after the bar close enters a feature; the order is filled at the next minute's open.
5. The control is run once per frozen bot, after a committed preregistration (below).
6. Tickers are kept (BTC, ETH...): the model's general knowledge of the assets is legitimate, the levels are hidden.
Residual risk: a model may recognise a regime from the shape of returns; the control reading must be read with that in mind.

## Money

`budget.py`: spend = response usage x list price (Haiku 5.5 $0.10/$0.50, Sonnet 5.5 $2/$10, Opus 5.5 $4/$20, Fable 5.2
$8/$40 per MTok; batch -50%; cache reads at the documented rates: Sonnet 5.5 $0.10, Opus 5.5 and Fable 5.2 $0.20, Haiku
assumed 0.1x input; 5-minute cache writes 1.25x). Before submitting, the worst case (every request writes `max_tokens`)
is reserved; the run is refused if settled spend + open reservations + this projection exceeds `--cap-usd` (never above $160).
`reserve` is atomic (the flock is held across read, check and append) and every reservation has a unique id, so concurrent
submissions cannot both pass nor overwrite each other. `--collect` is idempotent (actuals keyed by batch id + custom_id).
The client has `max_retries=0`: `batches.create` is never retried; a sync call is retried at most twice and only on 429 (released) or 5xx
(the failed attempt's reservation stays open, so a possible double billing is counted). A batch error that may have created the batch
marks `batch.json` as `unknown`, keeps the reservation and blocks resubmission. Stale reservations: `--list-reservations`,
`--release <id>`, `--release-stale <hours>` (only after checking the console).
Ledger: `~/dev/_arena-data/axis-08/spend.jsonl` (append only; dry-runs use `dryrun/spend.jsonl`). The key is read only
through `arena.deciders.llm.read_api_key()`, never printed or written, and `ANTHROPIC_BASE_URL` is ignored by the client.

## How to run

```
.venv/bin/python docs/lead/axis-08-llm-bots/run.py --estimate
.venv/bin/python docs/lead/axis-08-llm-bots/run.py --model haiku --prompt-variant v1_plain --period design --dry-run
.venv/bin/python docs/lead/axis-08-llm-bots/run.py --model sonnet --prompt-variant v2_costaware --period design --cap-usd 20
.venv/bin/python docs/lead/axis-08-llm-bots/run.py ... --collect        # resume a submitted batch
.venv/bin/python docs/lead/axis-08-llm-bots/run.py ... --mode sync      # stateful, full price
.venv/bin/python docs/lead/axis-08-llm-bots/run.py --model haiku --pilot --max-bars 2   # real sync, design only, cap 2 USD, per-call tokens
.venv/bin/python -m pytest docs/lead/axis-08-llm-bots/test_harness.py                    # offline self-tests
```
`--model`: haiku, sonnet, opus, fable (or the full id). Outputs in `~/dev/_arena-data/axis-08/runs/<bot id>__<period>/`
(`decisions.jsonl`, `report.json`). Bot id = model, variant, prompt hash, code hash (bars.py and bot.py: features, rendering, message template), effort, mode.

Control refuses to start unless `PREREGISTRATION.md` exists, is committed in git with no uncommitted change, contains
a line that is exactly `STATUS: FROZEN` and lists the bot id; and it refuses a second run of the same bot id. The lock line is written
only after the budget reservation succeeded and just before the submission or first call (a refused budget leaves no lock, a failed
run after that still counts; dry-run entries are ignored). A second batch submission for the same bot and period is refused
while `batch.json` exists; `--collect` reads the results.

## Report

Every bot goes through the bench like a rule: total return, max drawdown, Sharpe (daily, annualised), turnover (x starting
equity), cost paid (fees + slippage), funding, monthly returns. References on the same window: the frozen trend engine at 1x
and 2x (the council runs 2x; it can lever far more than the bot's 2x cap), the 1x equal-weight buy-and-hold basket, and 20
random-weight bots with the same turnover (the bot's own weight rows shuffled in time, with a hold probability calibrated to
match its turnover). Pass criteria are in `PREREGISTRATION.md`.

## Dry-run result (design window, fake client, zero cost)

Fake bot = random valid weights, with 1% refusals and 1% malformed JSON to exercise the hold fallback. Haiku/v1_plain, batch:
372 decisions (366 ok, 1 refusal, 5 invalid), return -49.4%, max DD -50.0%, turnover 327x, cost 39%; random baseline with the
same turnover -44.1% mean (so a random bot is sunk by costs: the bench works). Trend 2x +37.1% (DD -27.3%), trend 1x +20.5%,
basket 1x +45.8% (July 31 to September was a rising market). A sync run (60 bars), the ledger, the cap refusal and the control
refusal were also exercised. The dry-run says nothing about LLM skill.

## Cost estimate (USD; tokens by characters / 3.5; output tokens per call assumed at 700 / 900 / 1800 / 2500 for Haiku / Sonnet / Opus / Fable at default effort, thinking included)

Cells are `v1_plain / v2_costaware`. No cache assumed; with the system prompt cached the figures drop by 5 to 10%.

| model | calls (design / control) | batch design | batch control | sync design | sync control | worst case batch design |
|---|---|---|---|---|---|---|
| claude-haiku-5-5 | 372 / 342 | 0.09 / 0.10 | 0.09 / 0.09 | 0.19 / 0.20 | 0.17 / 0.18 | 1.52 |
| claude-sonnet-5-5 | 372 / 342 | 2.25 / 2.31 | 2.06 / 2.12 | 4.53 / 4.65 | 4.16 / 4.28 | 30.39 |
| claude-opus-5-5 | 372 / 342 | 7.84 / 7.97 | 7.21 / 7.32 | 15.75 / 16.00 | 14.48 / 14.71 | 60.79 |
| claude-fable-5-2 | 372 / 342 | 20.89 / 21.14 | 19.20 / 19.44 | 41.91 / 42.42 | 38.54 / 39.00 | 121.58 |

Reading: the whole programme in batch is cheap. Design for Haiku, Sonnet and Opus with both variants is about 21; the
three controls about 19 (Haiku, Sonnet, Opus, one variant each is about 17); Fable adds about 41 for design and 19 for control. Sync (stateful) costs twice the batch. Within $160 one can also run the stateful
versions. The output-token assumption is the main uncertainty: calibrate with `--pilot` (6 bars by default). The worst-case reservation (max_tokens 16000 on every call) is large for Opus and
Fable (Fable batch design about 122 USD): it only blocks submission against `--cap-usd`, real spend is the usage.

## Open points before a real batch

1. Pilot so far: Haiku 5.5, low effort, 2 sync bars: about 2200 input tokens (system prompt cached after the first call), 125 to 128
   output tokens, stop_reason end_turn, schema and `effort` accepted, 0.0007 USD. Sonnet, Opus and Fable have not been tried:
   run `--pilot` for each before its first batch (a few cents).
2. Output tokens per call for the larger models at medium effort are still guessed; `max_tokens` is 16000 and truncations are reported.
3. `messages.count_tokens` is not wired in: estimates use the character count.
