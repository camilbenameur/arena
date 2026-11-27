# Preregistration, axis 9: Claude as a researcher

STATUS: DRAFT

Before the control run the lead replaces the word DRAFT on the line above by the word FROZEN (the gate accepts only a line
that consists of that status marker and nothing else), adds the line `frozen_rule.py sha256: <64 hex digits>` for the
shipped `frozen_rule.py` on a line of its own (see the end of this file), and commits the file. `evaluate.py --period control` refuses
otherwise, and refuses a second run (lock file).

## Question

Can Claude act as a researcher, not a trader: given only design data, propose, test and freeze ONE trading rule for six
Kraken perps (4-hour bars) that holds out of sample? Axis 8 showed Claude models trading from prices lose out of sample;
here the model is asked to do the research once and hand back a causal rule, which is then run mechanically.

## Declaration

- The lead has seen all earlier control results (axis 8 and 8b: October to November 2026 is no longer unseen by the lead).
  The control is therefore a weaker test of the lead's choices, and no choice of this axis may have been made with it in view.
  The prompt, the harness and the evaluation were written without using any control number.
- The researcher model (claude-fable-5-2) has not seen the control, and gets no data on or after 2026-10-01: the upload and
  the prompt are the 4-hour bars of 2026-07-01 to 2026-09-30 only (guarded in code and tested). Its training cutoff is June 2026.
- Residual risk, as in axis 8: a model may recognise a regime from the shape of the data; read a pass with that in mind.

## Design of the experiment

- Data given to the researcher: 4-hour bars (open, high, low, close, volume, funding) of the six perps, 2026-07-01 to
  2026-09-30, the cost model (7 bp fee + 5 bp slippage per side, 24 bp per round trip, hourly funding), the design results of
  the trend engine 2x and of the basket, and a bar-level helper simulator. It has a code execution sandbox and a budget.
- Task: up to 15 candidate rules, each with an economic rationale; every evaluated variant counts as a trial; a trial log
  is mandatory; guard against overfitting (it is told an unseen later period will be used once); hand back ONE frozen rule
  `targets(df)`: weights per 4-hour bar per contract in [-2, 2] (units of equity/6), causal, numpy and pandas only.
- Rule and log are saved verbatim as `frozen_rule.py` and `trials_by_model.md`. Nothing is edited by hand; if the model
  returns a rule that fails the causality check or the format, the axis is reported as failed, not repaired.
- One session, one rule. No second session, no selection among rules, no retuning after any control number.
- Causality: the rule is recomputed on data truncated after bar t for many t; the rows must be identical (zero gap).
- Control: October to November 2026 (342 four-hour decisions, the sealed window of axis 8), run once through the axis-8 minute bench
  (decision at the bar close, fill at the next minute open, same costs, funding, rebalance band, gross cap).

## Pass criteria (as axis 8)

On the control, all of: (1) return above the frozen trend engine at 2x and above the 1x basket; (2) max drawdown no deeper
than 35%; (3) positive in both control months; (4) return above the 95th percentile of 20 random bots with the same turnover
(own weights shuffled in time). Also reported, not part of the pass: design results (in sample) and the trial log.
Reading: in a falling control window a pass of (1) means beating a trend engine that gained about 34%; failure is the expected outcome.

## Budget

- Axis cap 28 USD (budget ledger of axis 8, own file; the sum with the axis-8 ledger never passes the shared hard total).
  Model claude-fable-5-2, effort high, server-side code execution tool, container time booked on top (assumed upper bound).
- A smoke test of under 1 USD (print the shape and date range of the CSV) proved the upload and tool path before the session.
- If the cap stops the session before a deliverable, the axis is reported as not done; there is no second session.

## Hash of the frozen rule

To be added by the lead after the session and before the commit, on a line of its own, in this exact form:

`frozen_rule.py sha256: <hex>` (without the backticks)
