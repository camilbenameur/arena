# Preregistration, axis 8b: replicates and stateful high-effort bots

STATUS: FROZEN

Before any control run of 8b the lead replaces the word DRAFT on the line above by the word FROZEN (the gate accepts only a
line that consists of that status marker and nothing else) and commits the file. Bot ids are listed below as bullet lines,
one id per line, exactly as the harness prints them.

## Purpose

- **Part A, replicates.** Measure the sampling noise of the frozen axis-8 control results. Batch outputs differ between calls
  even with identical prompts, so one run per bot says little about how stable a result is. Each of the four plain-prompt
  frozen bots is run again 3 times on the sealed control (r1, r2, r3, same code, same prompt, same effort, same batch mode).
  The report gives the result of every replicate and the spread (min, max, mean, standard deviation of the return) across the
  original run and its three replicates.
- **Part B, stateful high-effort bots.** Test whether more reasoning (effort high) and knowing its own position (sync mode:
  the prompt carries the bot's own weights, equity index, drawdown and cost paid) help Opus 5.5 and Fable 5.2.

## Honest declaration

The lead has already seen the axis-8 control results (all 12 frozen bots failed the sealed control, October to November 2026).
Part B is therefore a weaker out-of-sample test than axis 8: the choice of what to try (a stateful bot, a higher effort) is
informed by those results, and the control window is no longer unseen by the lead. To limit the damage: no prompt change is
allowed (the two prompts and the code hash bb0e9052 are the frozen ones), only the effort and the mode change; every Part B
bot runs on the design window first; and a pass on the control is reported with the number of bots tried and with this
declaration, never as proof of skill. Part A is not affected: it re-measures a result already known, and its only output is
the noise around it.

## Bots

Code hash bb0e9052 (bars.py and bot.py unchanged since the axis-8 freeze).

### Part A: replicates of frozen bots (batch, effort and prompt as in axis 8; control only)

The base ids are the four plain-prompt bots of the axis-8 preregistration. A replicate keeps the base id plus a suffix
`__rN`, has its own run directory and its own control lock, and never overwrites the original run.

- claude-haiku-5-5__v1_plain-c37a87a1-bb0e9052__low__batch__r1
- claude-haiku-5-5__v1_plain-c37a87a1-bb0e9052__low__batch__r2
- claude-haiku-5-5__v1_plain-c37a87a1-bb0e9052__low__batch__r3
- claude-sonnet-5-5__v1_plain-c37a87a1-bb0e9052__low__batch__r1
- claude-sonnet-5-5__v1_plain-c37a87a1-bb0e9052__low__batch__r2
- claude-sonnet-5-5__v1_plain-c37a87a1-bb0e9052__low__batch__r3
- claude-opus-5-5__v1_plain-c37a87a1-bb0e9052__medium__batch__r1
- claude-opus-5-5__v1_plain-c37a87a1-bb0e9052__medium__batch__r2
- claude-opus-5-5__v1_plain-c37a87a1-bb0e9052__medium__batch__r3
- claude-fable-5-2__v1_plain-c37a87a1-bb0e9052__medium__batch__r1
- claude-fable-5-2__v1_plain-c37a87a1-bb0e9052__medium__batch__r2
- claude-fable-5-2__v1_plain-c37a87a1-bb0e9052__medium__batch__r3

### Part B: new stateful bots (sync, effort high; design first, then control)

Four new bots (their ids differ from every axis-8 bot by mode and effort). Each runs on the design window first and then on
the control; all four go to the control with no selection.

- claude-opus-5-5__v1_plain-c37a87a1-bb0e9052__high__sync
- claude-opus-5-5__v2_costaware-7637a02d-bb0e9052__high__sync
- claude-fable-5-2__v1_plain-c37a87a1-bb0e9052__high__sync
- claude-fable-5-2__v2_costaware-7637a02d-bb0e9052__high__sync

A sync run interrupted by a crash is resumed with `--resume` from `decisions.partial.jsonl`: decided bars are not called
again. This changes nothing in the bot (the track record is replayed from the saved decisions).

## Pass criteria

The same four criteria as axis 8, on the control: (1) return above the frozen trend engine at 2x and above the 1x basket;
(2) max drawdown no deeper than 35%; (3) positive in both control months; (4) return above the 95th percentile of 20 random
bots with the same turnover. For Part A, a replicate is reported against the same criteria, and the headline is the spread
across the original and the replicates, not the best replicate.

## Budget

- Total spend ledger at most 155 USD (prepaid API credit of 160 USD; the API refuses calls once the credit is spent).
- Part A batches reserve against the cap with `--reserve-out-tokens 2200` instead of the 16000-token worst case. Every request
  keeps max_tokens 16000. Basis: the largest output seen over the 8,000+ calls of axis 8 is 439 tokens (mean 120 to 160);
  2200 is five times that maximum. Without this, the Fable reservation alone (about 113 USD) would block part A.
- Part B runs in sync mode, which reserves the worst case per call (no change).
- Run order: part A, then part B design, then part B control. If the cap stops a run, the run is reported as not done.

## Known limits

- One market regime, 57 control days: low power, as in axis 8.
- Sync bots are stateful, batch bots are not: different bots. The shadow track record shown to a sync bot is approximate
  (it ignores fills at the next open and funding timing).
- Replicates re-sample the same prompts; they measure noise from the model, not from the data.
