# Preregistration, axis 9b: a population of Claude researchers

STATUS: DRAFT

Before any 9b control run the lead replaces the word DRAFT on the line above by the word FROZEN (the gate accepts only a line
that consists of that status marker and nothing else), fills the section "Sessions" below with the output of
`evaluate.py --print-session-list` (one line per session, see the end of this file), and commits the file.
`evaluate.py --session <name> --period control` refuses otherwise, refuses a session whose rule hash is not listed, and refuses a
second control run of the same session (one lock per session).

## Question

Axis 9 gave one answer from one Fable session: the frozen rule returned +10.0% on the control and failed the axis-8 criteria,
but a single session cannot tell luck from skill. Axis 9b asks: across a population of independent researcher sessions given the
same brief, is the mean out-of-sample return of the frozen rules positive, and above what random weights with the same turnover
earn? That is, does "Claude as a researcher" yield a positive result on average, not only once?

## Declaration

- The lead has seen the control results of axes 8, 8b and 9 (October to November 2026 is no longer unseen by the lead). The
  researcher sessions have not: each gets only the 4-hour design bars of 2026-07-01 to 2026-09-30 (guarded in code and tested),
  and the brief contains no control result, no result of any earlier session and no mention of the population.
- The sessions are independent: every session is a fresh API conversation with its own container, no shared context, no memory.
  The brief, the data, the helper simulator and the rules are identical for every session of both models.
- Models: claude-opus-5-5 and, if run, claude-fable-5-2, effort high, server-side code execution. The training cutoff of both
  is before the control window. Residual risk, as in axes 8 and 9: a model may recognise a regime from the shape of the data.
- The axis-9 session (Fable, one rule, +10.0% on the control) is not part of this population: it is reported beside it.
- No session is selected, ranked or dropped before the control. Every session that wrote a rule goes to the control, exactly once.
  No rule is edited, repaired or retuned. No new session is started after the first 9b control number has been seen.

## Design of the experiment

- Same task as axis 9: up to 15 trials, a mandatory trial log, ONE frozen causal rule `targets(df)` per session, or an honest
  "no robust edge found" with the most defensible simple rule.
- Per session: `sessions/<model>-<id>/frozen_rule.py` and `trials_by_model.md` saved verbatim; transcript kept outside the repository.
- Budget: 3 USD per session, 30 USD for the whole of 9b on the axis-09 ledger, and the sum with the axis-08 ledger stays below
  158 USD. The driver stops cleanly when the budget would be passed. The number of sessions is therefore set by the budget and
  by nothing else: it is the number of sessions that completed (rule written or not) before the driver stopped.
- A session that ends without a rule (budget, refusal, no deliverable, rejected format) is reported as "no rule" and counted.
  A rule that fails the causality check is refused, takes its one control slot, and is counted as a failed session. Neither enters
  the primary mean; both enter the secondary mean below.
- Control: the same sealed window as axes 8 and 9 (October to November 2026), through the axis-8 minute bench (decision at the
  bar close, fill at the next minute open, 7 bp fee + 5 bp slippage per side, hourly funding, rebalance band, gross cap), one run
  per session, 20 random bots with the same turnover per session (own weights shuffled in time).
- Gate: the committed FROZEN file must list `session <name> frozen_rule.py sha256: <hex>` for the session being run, and the
  hash must match the file on disk.

## Statistics

Primary: the mean control return across all sessions with a valid rule, compared (a) with 0 and (b) with the mean of the
same-turnover random returns of the same sessions (mean of the per-session differences). Both are reported with the standard
deviation across sessions and a t statistic; with few sessions these are descriptive, not a significance claim. The primary
reading is positive only if the mean is above 0 AND above the mean random return.

Also reported, as counts out of the number of sessions with a control run, not part of the primary reading:
- the axis-8 criteria per session: (1) return above the trend engine at 2x and above the 1x basket, (2) max drawdown no
  deeper than 35%, (3) positive in both control months, (4) return above the 95th percentile of the 20 random bots with the same
  turnover; and how many sessions pass all of them;
- how many sessions beat the basket, the trend engine at 2x, and their own random p95; how many are positive; the median;
- secondary mean with every non-valid session (no rule, refused rule) counted as 0% (cash), computed by the lead from the
  per-session table;
- design results (in sample) next to the control results, per session;
- the share of sessions that label themselves "no robust edge" (the phrase in the rule docstring or trial log), and the mean control
  return of the labelled sessions against the others (also computed by the lead from the per-session table).

Reading: the basket falls about 36% on the control window and the trend engine at 2x gains about 34%. A positive mean with the
random bots earning as much or more would mean the sessions only found a way to trade less in a market that rewarded flatness.

## Sessions

To be filled by the lead after the last session ended and before the commit, one line per session directory, copied from
`python docs/lead/axis-09-llm-researcher/evaluate.py --print-session-list` (the line has this exact form, a session without a
rule reads `session <name> no rule`):

(none yet)
