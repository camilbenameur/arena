# Preregistration: LLM trading bots on post-cutoff data

STATUS: FROZEN

Before any control run the lead replaces the word DRAFT on the line above by the word FROZEN (the gate accepts only a line
that consists of that status marker and nothing else) and commits the file.

## Question

Can a Claude model, acting as a 4-hour trading bot on six Kraken perps, beat the rules in the arena on data it cannot have
seen in training?

## Data and split

- All models have a training cutoff of June 2026. Usable data: 2026-07-01 to 2026-11-26 (UTC).
- DESIGN decisions 2026-07-31 to 2026-09-30 (372 four-hour decisions): prompt development. The 30-day lookback of every feature
  then starts on or after 2026-07-01 (a margin after the cutoff; the run asserts it). CONTROL decisions 2026-10-01 to
  2026-11-26 (342 decisions): sealed, each frozen bot runs once. Control is unchanged.
- Execution: the arena bench (next-minute-open fills, 5 bp slippage + 7 bp fee per side, hourly funding, gross cap 10x; the
  bot's weights are limited to [-2, 2] x equity/6, so gross at most 2x).
- Prompts carry no date and no price level (see README, leak controls).

## Search budget on DESIGN

At most 3 prompt variants x 3 models (9 bots), each in one execution mode. Every design run is logged (the ledger and
`runs/*/report.json`), failures included. The bot id contains a hash of the prompts and of bars.py and bot.py, so any change
to features, rendering or prompts is a new bot. The frozen set is chosen on DESIGN only and listed below before the control.
Retuning a prompt after reading any control result is forbidden and would make the bot a new bot, with no control left.

## Frozen bots (all 12 design bots, frozen on 2026-11-27 before any control run)

- claude-haiku-5-5__v1_plain-c37a87a1-bb0e9052__low__batch
- claude-haiku-5-5__v2_costaware-7637a02d-bb0e9052__low__batch
- claude-haiku-5-5__v3_overlay-2fe52aba-bb0e9052__low__batch
- claude-sonnet-5-5__v1_plain-c37a87a1-bb0e9052__low__batch
- claude-sonnet-5-5__v2_costaware-7637a02d-bb0e9052__low__batch
- claude-sonnet-5-5__v3_overlay-2fe52aba-bb0e9052__low__batch
- claude-opus-5-5__v1_plain-c37a87a1-bb0e9052__medium__batch
- claude-opus-5-5__v2_costaware-7637a02d-bb0e9052__medium__batch
- claude-opus-5-5__v3_overlay-2fe52aba-bb0e9052__medium__batch
- claude-fable-5-2__v1_plain-c37a87a1-bb0e9052__medium__batch
- claude-fable-5-2__v2_costaware-7637a02d-bb0e9052__medium__batch
- claude-fable-5-2__v3_overlay-2fe52aba-bb0e9052__medium__batch

All 12 design bots go to the control, with no selection: the design ranking is not used to pick a winner, so the
control result of the best bot must be read against 12 tries.

### Deviations from the draft, declared before the control

- The design search used 4 models x 3 prompts = 12 bots, not 3 x 3 = 9: Claude Fable 5.2 was added.
- Wave 1 ran with code hash cbc1d203; the only change to bot.py since then is the addition of the third variant
  (v3_overlay). The v1 and v2 system prompts are unchanged (same prompt hashes), and bars.py is unchanged. The control
  runs under code hash bb0e9052.

### Design results (no bot passes all criteria on design)

| Bot | Return | Max DD | Sharpe | Beats random p95 |
|---|---|---|---|---|
| Haiku v1 plain | +13.7% | -4.7% | 3.87 | yes |
| Haiku v2 cost-aware | +14.7% | -5.3% | 3.27 | no |
| Haiku v3 overlay | +43.3% | -10.4% | 4.40 | yes (43.25% vs 43.19%) |
| Sonnet v1 / v2 / v3 | +8.5% / +9.8% / +45.8% | -5.8% / -7.1% / -11.8% | 2.64 / 2.45 / 4.36 | no |
| Opus v1 / v2 / v3 | +10.0% / +10.9% / +44.2% | -7.8% / -8.4% / -13.7% | 2.54 / 2.31 / 4.08 | no |
| Fable v1 / v2 / v3 | +14.0% / +14.8% / +44.9% | -9.1% / -9.7% / -12.0% | 2.52 / 2.54 / 4.33 | no |
| Trend engine 2x | +37.1% | -27.3% | 2.63 | |
| Basket 1x | +45.8% | -11.9% | 4.30 | |

## Pass criteria (all must hold on the CONTROL, for a bot to be called a success)

1. Total return after costs greater than the frozen trend engine at 2x on the same window, and greater than the 1x equal-weight buy-and-hold basket.
2. Max drawdown no deeper than 35%.
3. Positive return in both control months (October and November).
4. Return above the 95th percentile of 20 random-weight bots with the same turnover (shuffled own weights, calibrated hold probability).

A bot that fails any criterion is reported as failed. With several frozen bots, the report says how many were tried and
that the chance of one passing by luck grows with that number (no selection of the best afterwards).

## Known limits to report with the result

- 57 control days with one market regime: low statistical power; a pass is not proof of skill.
- The trend engine at 2x may carry more leverage than the bot's cap.
- Batch bots are stateless (no knowledge of their positions); sync bots are stateful. They are different bots.
- A model could recognise a regime from the shape of returns despite the leak controls.
