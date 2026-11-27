# Preregistration: LLM trading bots on post-cutoff data

STATUS: DRAFT

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

## Frozen bots (to be filled by the lead before committing; the control gate checks that a bot id appears here)

- (bot id 1)
- (bot id 2)
- (bot id 3)

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
