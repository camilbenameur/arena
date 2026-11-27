# Preregistration, axis 9b: a population of Claude researchers

STATUS: FROZEN

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

session fable-s01 frozen_rule.py sha256: 607600ce14e06e17400d13cf13378bd5c47d498c7461714877bdd2d188191fb0
session fable-s02 frozen_rule.py sha256: f2d0d8a690ce83deee736778a742d631e93f5fca763fbd71dd6a47e6240fd595
session fable-s03 frozen_rule.py sha256: 7850e218a774fb1164f1a7c7f3eea3a5d691c56f4971b4b5eac206ba4fb64a78
session fable-s04 frozen_rule.py sha256: 8c579b8097281984de03ac6d6c3858e822834c1e2a5a66a47c78bf14ee7bf0b1
session fable-s05 frozen_rule.py sha256: 1ea8d061d8a16425f183b1d0ef42909c84cb6f86d539912fb9008d014f6e3387
session fable-s06 frozen_rule.py sha256: 105606373d341699b48ed0f67f14fd3b2485cee2fe0ff5578994819db898e95b
session fable-s07 frozen_rule.py sha256: 6c34e151cd7d16a5be552f1680a640f38da119d495c2adffb1f950fbd62436a3
session fable-s08 no rule
session fable-s09 frozen_rule.py sha256: 37b4701ce63dfc3daadee70e833ed6201c88731250f9c48a5773e60fb826da07
session fable-s10 frozen_rule.py sha256: c763d3ab82d5a7e2d206353cb2771b90ca3e680c2267062cdbe9565aff019d21
session fable-s11 frozen_rule.py sha256: 65b5f20c82a0be2be06e59f8fa03d36bcf488f8434aaa2ca815511cdaf09ec6d
session fable-s12 frozen_rule.py sha256: ec626975bbab47cb9af8d62b9958dbaf0cfce438ea4961fc4bb4b7246d481bc3
session fable-s13 frozen_rule.py sha256: 4e5c002c8684f860f60773213df8eda69679a175ef45e254c2198669664a7654
session fable-s14 frozen_rule.py sha256: 72365dd12c0060cf32ccf2301a374b1778e4997d99f5e8ea64a302ada7607da7
session fable-s15 frozen_rule.py sha256: a9f855d663e18bd304975d00fe7e591536cf8232ff12ced26c2c0152a1597e03
session fable-s16 frozen_rule.py sha256: a3ac2b92f0101757709b43c494ff911b3816737672e959a757f13945658e1126
session fable-s17 no rule
session opus-s01 frozen_rule.py sha256: 590cf5ef32a1744c40d292c2fffc0cc8fe8895a1f5fca65de5d96c0db73ee75f
session opus-s02 frozen_rule.py sha256: ff78b9c87becdec87c2f87181193eb26f7d52464e5ab828fe23f21d3e8e3142f
session opus-s03 frozen_rule.py sha256: 7190c55287262baa857898a65a0091abc24a94c0ae25e283204d194ed7859aa1
session opus-s04 frozen_rule.py sha256: ee29743c84dbb45de4baec2950ccf6d5e44d477dc1393d37febee379bdc17bbe
session opus-s05 frozen_rule.py sha256: 96873c1c75c641b0128063a541b798e49b27b248a595dc9721a4fc69950b1aea
session opus-s06 frozen_rule.py sha256: 59453d7aab33ab4c3a7e120ca1e3528fe00c5646589559379cf1aa59b5877fd5
session opus-s07 frozen_rule.py sha256: 70f5c00831f94e84e1e39cfca5ad7d435c2abbdcd9edcf819a9bb6f68f8ddcc4
session opus-s08 frozen_rule.py sha256: 517bd293934fee71d80dc4053a4ae240c9bf4109f88f4e790aeca50481a3b026
session opus-s09 frozen_rule.py sha256: 5bce486d3417ed89ae593d30dc1081d0e2a2732c54c9382befafb60ca20278a5
session opus-s10 frozen_rule.py sha256: 29cc90e165f6e9fdfda87243915c03fd86a4eeb560a27836a9768f995cbe3254

Frozen on 2026-11-27 by the lead after the last session ended: 27 sessions run (17 Fable, 10 Opus), 25 rules, 2 Fable sessions without a rule (connection dropped mid-stream; their reservations stay counted). The axis-9b budget was spent; the planned extra Opus sessions were not run. Every transcript was checked: the only network-related words are the brief's own prohibition.
