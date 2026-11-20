# Strategy research pipeline: protocol research-v1

Written on 2026-11-11, before any trial. Revised the same day after the adversarial review through four lenses (statistician, cheater, engineer, quantitative researcher; the arbitration is in section 11). The numeric values are in `research/criteria.yaml`, which is authoritative. This protocol extends that of the lightweight lab (a separate lab repository, not public; outcome B on 2026-11-11). It is stricter than the lab protocol, never looser.

## 1. Question, outcomes, and what nothing here proves

A system that "tests every possibility" always finds a winner on history. This pipeline **filters**, it does not prove.

- **Outcome A**: 1 to 3 frozen candidates (hashed code). A spot candidate is wired in as a paper portfolio `strategy:<id>` in the arena. A carry candidate (perpetual leg) is frozen but **not promoted**: the arena does not yet have a perpetual ledger, and access to Kraken perpetuals is not confirmed.
- **Outcome B**: no candidate. A report publishes all trials, losers included. It counts as a success if the protocol is respected.
- **Prior probability of outcome A: under 5%.** The DSR requires a net Sharpe of about 1.9 (N = 726, section 5). Long-only families have no realistic path to both C1 and C6: in the lab, 0 trials out of 125. The realistic space is that of hedged families.
- **No gate controls for model memory**: the models have seen the whole 2018-2026 window. Only data after June 2026 does: the forward paper run (section 9) and, if so decided, the sealed lab holdout (section 10).
- **A paper run of 8 to 12 weeks proves nothing**: the standard error of the annualized Sharpe is 2.6 at 56 days and 2.1 at 84 days. It can only refute (section 9). A confirmation requires the 90% confidence interval of the forward Sharpe to be above 0, i.e. about 300 days for a Sharpe of 1.8 and about 1,000 days for a Sharpe of 1. No move to live trading is decided on paper alone; it is a separate, explicit decision.

## 2. Data firewall (non-negotiable)

- **Cutoff date: 2026-07-01T00:00:00Z excluded.** No market data from a later date enters the research, in any form. From 2026-07-01 to 2026-11-09 extends the **sealed lab holdout** (the sealed lab holdout, not public), which nothing here reads. The arena's cache (`var/data/`) contains recent prices: it is off limits to the research.
- **Allowed sources**, all copied into `var/research/data/`, then hashed into a manifest frozen at the tag `research-engine-v1`:
  1. the lab's in-sample candles (15 USDT pairs, 1 d and 1 h, from 2018-01-01 to 2026-06-30), checked against the lab's `MANIFEST.json`;
  2. Binance's public monthly archives (`data.binance.vision`), **months <= 2026-06**: funding and 1 h candles of the USDT-M perpetuals of the 15 pairs;
  3. the 1 d spot candles of a **control universe** of 20 symbols, months <= 2026-06, chosen by a mechanical rule before wave 1. The rule: the largest quote volumes of January 2020 outside the 15 pairs, delisted ones included, to counter survivorship bias (C16).
- **Firewall checks**:
  - **loader**: it reads only `var/research/data/`, verifies the manifest and raises an error on any row whose `known_at` (section 3) is later than or equal to the cutoff; it never truncates silently;
  - **downloader**: it refuses any month later than 2026-06;
  - **strategy execution**: it runs under `bwrap`, with a whitelist of mounts (venv and standard library read-only, one tmpfs), no network and no access to the repository, to `var/`, to `~/.config` or to the sealed directory;
  - **startup canary**: the engine refuses to start if the sandbox lets through a `connect()`, a read outside the whitelist or a write outside the tmpfs.
- **Agents**: the researchers have no network access to the markets and read no market news. Their web searches concern literature, and every query is logged. The implementation agents **never** see real data: they have only seeded synthetic series and tests.
- **Known limit**: the agents run under the same Unix user as the host, who can read the whole home directory. Separation by a dedicated Unix user (`research-engine`) would require a system change with sudo; it is proposed, not done. Meanwhile, the safeguard is the external anchoring of the journal (section 4), plus instructions and checks.

## 3. Measurement

- **Window.** The evaluation window runs from 2020-01-01 to 2026-06-30; 2018-2019 serves only as warm-up. The Sharpe, the DSR (T), C5, C13 and the basket are computed over the days on which at least one pair of the strategy is eligible. A carry family starts on the first day on which the funding of its pair exists. The perp windows end on 2026-06-29 inclusive.
- **Data.** The tolerances are those of the lab:
  - 1 d: no gap;
  - 1 h: at most 0.1% of missing bars and 6 consecutive bars;
  - filling: close = last close, zero volume, zero return;
  - zero weight before a pair is listed.
- **Information knowledge.** Every row carries `known_at`:
  - bar: `open_time + duration`;
  - funding: `fundingTime + 1 s`.
  A row is visible at time t only if `known_at <= t`.
- **Funding.** A funding settlement is **paid** by the position decided at a close <= `fundingTime`. The engine sums the actual settlements present and never assumes 3 per day.
- **Strategy contract (leakage impossible by construction).**
  - **Flow.** The engine sends the isolated worker, through a pipe, one daily bar at a time. With it come its 24 1 h bars and the day's funding settlements; the worker **never** receives the future.
  - **Output.** At each 00:00 UTC close, the strategy returns a vector of target weights per (pair, leg). The leg is `spot`, or `perp` for hedging only.
  - **Anonymization.** The strategy sees neither a date nor a pair name: an integer index, and columns `P01...P15` in an order drawn at random on each call.
- **Invariances tested on synthetic data**, never on real data:
  - permuting the columns permutes the weights (to within 1e-9);
  - the weights do not change if a pair's prices are multiplied by a factor drawn between 0.1 and 10 and its volumes by the inverse;
  - truncation (section 6, C9) changes nothing.
- **Cadence.** One decision per day at 00:00 UTC. The 1 h bars serve only as input to aggregated signals. A 4 h cadence is out of scope for research-v1.
- **Portfolio and turnover.** The engine holds the portfolio in quantities. Turnover is computed as: turnover = sum |w_target - w_drifted|, with w_drifted = w_{t-1}(1+r)/(1+r_p).
- **Engine acceptance test.** With constant weights of 1/15, it must recover the turnover and net Sharpe of the basket computed independently, and reproduce the lab to within 1e-9 on E0065 with the lab's costs.
- **Costs**, aligned with the arena (`config/arena.toml`: 50 bp taker fee, 5 bp slippage), plus 5 bp half-spread:
  - **spot**: 0.60% per unit of turnover;
  - **perp**: 0.10% per unit of turnover, plus the actual funding;
  - **stress**: costs doubled.
  A test checks consistency between `criteria.yaml` and `arena.toml`.
- **Markets.**
  - **Class `directional`**: long-only spot, weights in [0, 1], sum <= 1, the rest in cash at zero return.
  - **Class `hedged`**: long spot and short perp on the same pair, with short perp <= long spot. The capital tied up is the spot notional plus a perp margin of 50% of the short notional. Return = w_spot * r_spot - w_perp * r_perp + funding received.
  - Directional and neutral perps are out of scope for research-v1.
  - The engine **raises an error** on an out-of-bounds weight; it never clips it.
- **Parameters.** They are fixed, with no walk-forward in research-v1: a grid point is a rule, and its series over the whole window is the tested series.
- **A single engine.** `research/engine/`, frozen at the tag `research-engine-v1` with the sha256 of `criteria.yaml`. No performance computation outside the engine, descriptive statistics included. The engine returns to the agents only a **closed code** (`OK`, `CAUSALITY`, `TIMEOUT`, `SOURCE_REFUSED`, `WEIGHT_SHAPE`, `ERROR`), never a trace or a number. The detail goes to a technical journal, read by the orchestrator and the maintainers.

## 4. Journal, counting, anchoring

- **Chained journal.** `research/trials.jsonl` is chained, in the envelope of `arena/journal.py`. The metrics are stored there as decimal strings with 12 significant digits, recomputed on re-reading.
  - **First line**: `lab_genesis`, which carries the head and the line count of the lab's journal at the tag `final-freeze`.
  - **Per trial**: a `start` line **before** the computation (code_sha256, sheet_sha256, parameters), then an `end` line. A trial without an `end` counts.
- **External anchoring.** After each trial, the head and the line count are written into the arena's journal (event `research_anchor`). The engine refuses to start if its journal is shorter than the last anchor, or if the anchored head does not appear in it.
- **N.** The DSR of any candidate is computed with **N = 726** (126 lab trials + 600, the cap of research-v1), whatever the moment, never with a running N. The actual N is also reported, for information.
- **Caps.**
  - **Research-v1**: 600 trials in total.
  - **Wave 1**: at most 120 trials, i.e. at most 6 families and at most 20 variants per family. Each rule has 2 to 4 parameters.
  - **Stop rule**: if the best DSR of wave 1 is below 0.5, wave 2 is not launched without a written decision.

## 5. Multiple-trial correction

The deflated Sharpe (Bailey and Lopez de Prado, 2014) is computed as in the lab (formulas of its `dsr.py`, tested on the published example), with N = 726.

**Variance V.** It is computed **per class** (`directional`, `hedged`, declared in the sheet before any trial), taking the larger of two values:
- the variance of the `sr_day` of the research trials of that class, computed per family then averaged, weighted by the number of trials;
- 1/(T_candidate - 1).

The lab's `sr_day` values count in N, but not in V: their costs were different. The DSR with a common V is also reported, for information.

**Net Sharpe required for DSR >= 0.95**, recomputed by the review's statistician (T = 2,373, zero skewness, kurtosis of 3; add about 0.02 for fat tails):

| N | V at the floor | standard deviation of the Sharpes of 0.5 | standard deviation of the Sharpes of 0.7 |
|---|---|---|---|
| 326 | 1.79 | ~ 2.2 | 2.69 |
| 726 | 1.89 | ~ 2.3 | 2.86 |

## 6. Selection criteria (all required, net of costs)

**Real gates:**

| Code | Criterion |
|---|---|
| C1 | DSR >= 0.95 (N = 726, V of the class) |
| C5 | Calendar years 2020 to 2025: none under a Sharpe of -1, at least 4 positive |
| C6 | Maximum drawdown <= 45% (class directional) or <= 20% (class hedged), on the compounded net asset value at daily closes |
| C7 | Declared geometric grid (at least 3 values per parameter, ratio >= 1.25 between neighboring values). At least 75% of the direct neighbors (+-1 step) must have a net Sharpe >= 0.6 x that of the candidate and >= 0.5. A candidate at the grid edge or not evaluable fails |
| C8 | **Directional**: beats the equal-weight basket of its universe (rebalanced on the 1st of each month, same costs, same window), by paired block bootstrap with 20-day blocks on the return difference, with one-sided p <= 0.05. **Hedged**: regression of the returns on the basket, annualized alpha with Newey-West t >= 2 and \|beta\| <= 0.3. The alternative drawdown branch is removed |
| C9 | Causality: flow by construction, plus 20 random cuts and 3 fixed ones on `known_at`, of which at least 40% at a non-round hour, and the invariance tests of section 3, on synthetic data |
| C11 | Extremes: Sharpe >= max(0.5; 0.5 x full Sharpe) after removing the best 1% of days (24 days), and > 0 after removing 2% |
| C12 | Total cost paid <= 50% of the annualized gross return. Annual turnover <= 15 (directional) or <= 40 (hedged, each leg counted) |
| C13 | Net Sharpe > 0 in each of the two halves of the window |
| C14 | Materiality: net geometric annualized return >= 4% on the capital tied up (margin included) |
| C15 | Arena compatibility (spot only): strategy replayed on the arena's 6 pairs, at 00:00 UTC, through the real `riskd` and the arena's simulator, with the hashed policy `config/policy-strategy.toml`; net Sharpe > 0 and drawdown <= 1.3 x C6 |
| C16 | Outside the universe: the unchanged strategy, on the control universe of 20 symbols (section 2), has a net Sharpe > 0 on at least 60% of the symbols where it is applicable (reported if not applicable) |

**Consistency checks**, which detect bugs and do not count as independent gates: C2 (net Sharpe >= 0.5), C3 (Newey-West t >= 2), C4 (Sharpe > 0 at doubled costs), C10 (bootstrap of the Sharpe by 20-day blocks, p <= 0.05). They remain required.

**Selection.** The trials that pass everything are ranked by DSR, 3 at most. Of two candidates whose excess returns over the basket are correlated above 0.7 (Pearson, daily), only the one with the higher DSR is kept. No code change after the selection. The report gives the probability that at least one candidate is "not refuted" in paper trading under H0 (about 85% for 3).

## 7. Roles and separation of powers

- **Researchers (Sonnet agents).** Blind waves: all the sheets of a wave are written and hashed before the previous wave is visible. Of past waves, they receive only the name, the mechanism and a binary verdict (discarded or not), never a Sharpe, a chart or a rank. They receive the lab's sheets, without any result, to avoid duplicates.
- **Contents of a sheet**: class; mechanism; who loses on the other side; falsifiable prediction; what would refute it; exact grid; expected gross move per trade; "C1 and C6 reachable together: yes or no, why"; risk of anticipation through memory. **No figure drawn from the data, no date, no named event.**
- **Sheet auditor (separate agent).** It rejects a sheet in any of these cases:
  - duplicate of a family already tested (lab included) without a new mechanism;
  - date or named event;
  - more than 4 parameters, or more than 20 variants in wave 1;
  - non-geometric grid;
  - unauthorized data;
  - unfalsifiable sheet;
  - expected return per unit of turnover below 3 times the leg's round-trip cost.
- **Implementation agent (separate agent).** It writes `strategy.py` according to the contract of section 3, with no import outside the whitelist (AST check inherited from the lab). It sees only synthetic data and the engine's closed codes.
- **Engine (code, not an LLM).** It runs the grid, logs and computes the criteria. **No LLM decides on a pass.**
- **Orchestrator (the script that drives the pipeline).** It launches the engine, reads the verdicts and writes the wave report.
- **Final auditor (separate agent).** Before the freeze, it re-reads each candidate; its output is recorded as is.
- **Maintainers.** They decide on any revision of the protocol, any wave after a stop rule, any overrun of 600 trials, the fate of the lab holdout (section 10) and any move to live trading.

## 8. Acknowledged biases

- Model memory over 2018-2026 (section 1).
- Window already read by 126 lab trials, hence the cumulative N.
- A single asset class, highly correlated; survivorship bias, partly countered by C16.
- Binance data in USDT and execution at Kraken in EUR: basis, currency and liquidity gaps. The increased costs cover only part of them.
- Binance funding and Kraken funding differ; eligibility for perpetuals is not confirmed.
- Execution assumed at the 00:00 UTC close, whereas the arena executes at 00:05.

## 9. Forward paper run: rules written before the first cycle

These rules are hashed into the arena's journal at promotion time. The result is one of three labels: **refuted**, **not refuted (no evidence)** or **technical defect**. "Proven" does not exist in this protocol.

- **Replication.** At the end of the period, the frozen engine is replayed over the same days (later data is then allowed for that sole purpose). There is a **technical defect** if the daily correlation with the paper run is below 0.95, or if the cumulative gap exceeds 1.5 times the stressed cost.
- **Refutation**, calibrated to 5% false refutation for a true Sharpe of 1:
  - cumulative return <= -0.5 x the annualized volatility of the backtest at 56 days, or <= -0.6 x that volatility at 84 days;
  - or paper drawdown above 1.3 times the drawdown of the constrained backtest (C15).
- **Pace.** A single look per week, with an O'Brien-Fleming-type alpha spending of 5% in total.
- **Clean halt.** The policy `config/policy-strategy.toml` applies the halt at the refutation threshold, and not at the 20% of the LLM policy.

## 10. Lab holdout: a reserved decision

The lab holdout (2026-07-01 to 2026-11-09, about 132 days) is the only clean data already available. The status quo is that it stays sealed for a possible second lab round. It may instead be decided that it is used **once** to test a frozen candidate of this research, through the sealed evaluator, with the non-refutation rule of section 9. Without a written decision to that effect, it stays sealed.

## 11. Arbitration of the adversarial review

**Retained:**
- paper rules and labels;
- N fixed at 726 and V per class;
- power table and prior probability;
- flow contract, anonymization and invariances;
- `known_at` and funding convention;
- whitelist firewall, canary and external anchoring;
- closed codes;
- fixed parameters;
- rewritten C7;
- C8 without a drawdown branch, and alpha for the hedged class;
- C11 at 1% and 2%;
- C12 on costs;
- C14 materiality, C15 arena compatibility, C16 outside universe;
- costs of 0.60%;
- wave 1 <= 120 and stop rule;
- hedged class;
- control universe;
- implementation agents on synthetic data;
- blind waves.

**Discarded or deferred:**
- **Dedicated Unix user with sudoers**: system change, to be proposed (section 2).
- **Neutral perp class and directional perp**: no perp ledger in the arena; deferred to research-v2.
- **4 h cadence**: deferred.
- **Criterion "removal of the 24 worst days <= 3 x Sharpe"**: too profile-dependent; reported for information only.
- **C15 with drawdown <= 20%**: replaced by a policy specific to strategies, because the LLM halt makes no sense for a rule with a known drawdown.

## 12. History

- research-v1: 2026-11-11, version frozen before any trial, after the adversarial review.
- Errata research-v1 (2026-11-12, before any real trial, no threshold changed):
  1. Section 6 "about 85% for 3" is wrong. The simulation of the refutation rule of section 9 gives about 91% "not refuted" per candidate without an edge (0.89 to 0.91 depending on the backtest drawdown), i.e. 99.9% for 3 independent candidates (`research/gates/selection.py::simulate_p_not_refuted`). This reinforces the conclusion of section 1: paper trading proves nothing.
  2. Section 3 "Markets": a `directional` sheet may declare `perp_signals: true`. It then receives the perp bars and the funding as **signals**; its perp leg is still forced to zero by the engine (`WEIGHT_SHAPE` otherwise). The data used remains that of section 2. Without this clarification, a family allowed by the audit (r-crowded-funding) would have run without its signal.
  3. Section 3 "Data" (2026-11-12, when loading the real data, before any trial): Binance's 1 h perp archives have the same 120-bar gap (72 h on 2022-02-26, 48 h on 2022-04-01) on nine series (LTC, SOL, TRX, XRP; control ZEC, XLM, VET, IOTA, WAVES), and the control spot 1 h of BTT has 0.17% of missing bars. These gaps are on the archive side, not the markets'. Rule: a 1 h series outside tolerance starts at the first bar after the last out-of-tolerance gap, like a late listing; the funding follows the same start. Nothing is filled beyond the tolerances, no threshold changes, and the rule depends on no result. Shortened starts: `Data.cut_starts` (perp: 2022-04-03; BTT 1 h: 2021-04-25).
  4. Sections 3, 7 and 8 (2026-11-12, before any real trial, no threshold of `criteria.yaml` changed):
     - **Hardenings already in the code, stricter than the text.** (a) The perp short of a `hedged` sheet must cover at least 90% of the spot long, pair by pair and every day, otherwise the engine raises `WEIGHT_SHAPE` (`research/engine/portfolio.py`, `HEDGED_MIN`). (b) V = max(1/(T-1), weighted average of the intra-family variances, variance of the set of the class's `sr_day`): the third term is added to the maximum of the text, so that dummy families of nearly identical variants do not dilute V (`research/gates/dsr.py`). (c) C16 divides the number of control symbols with a strictly positive net Sharpe by the total number of control symbols, i.e. 20, and not by the number of those that ran: a symbol whose trial is not OK or whose Sharpe is not finite counts as a failure, and a non-evaluable symbol (perp or funding data missing) stays in the denominator without being able to be positive; C16 also requires at least 10 evaluable symbols (`research/gates/evaluate.py`, `gate_c16`).
     - **Turnover convention.** The weights returned by the strategy are a target; the weight drift due to prices is rebalanced every day and paid for (convention `drifted`, the default), which applies section 3 to the letter. The lab counted the turnover between successive targets (convention `target`), which serves only for the acceptance test reproducing E0065. This penalizes holding strategies against C8's monthly basket and eats into the turnover budgets of C12. This is the conservative direction: it is recorded and not changed.
     - **Perp short liquidation.** No liquidation of the perp short is modeled (50% margin). This is a limit, reported with the results.
     - **Deducible date.** Despite the random removal of 0 to 364 days of warm-up (drawn once per family at the start of the wave, written into the chained event `wave_started`, the same for all variants of the family and their universes, bounded per panel to keep at least 365 days of warm-up, and zero if the panel has fewer), the date remains partly deducible by a strategy: the `eligible` mask, the public listing dates, the nine perps that start on the same day (erratum 3) and the tick grid. C16 (outside universe) and the replay on the arena's universe remain the safeguard.
     - **Fixed before any trial.** The funding order that undid the column permutation, the AST-check evasion through `collections._sys` and giant literals (hard-coded calendar) are fixed. The control panel now receives the 1 h bars, the perp and the funding (C16 was impossible for `hedged` strategies). V of the `hedged` strategies is computed on the series relative to the capital tied up, the same as that of C1, and not on the total-capital series. The per-family caps (wave 1 variants, number of families) are counted by family name, and not by sheet file; a family name follows the pattern `[A-Za-z0-9]+(-[A-Za-z0-9]+)*`, and two families that differ only by case are refused. Gate C9 stays closed if the check on real data has not returned its result.
  5. Section 3 "Markets" (2026-11-12, written decision, before wave 3, no threshold of `criteria.yaml` changed): the coverage floor of erratum 4 (a) is lifted. A `hedged` sheet may cover from 0 to 100% of its spot long, pair by pair and every day (0 <= perp <= spot); the rest of section 3 does not change (capital tied up, 50% margin, return, error raised with no clipping). The engine becomes `research-engine-v2` (`HEDGED_MIN = 0`), and each trial logs its engine version. The discipline of the class comes from C6 (drawdown <= 20%) and C8 (|beta| <= 0.3 against the basket). The trials of waves 1 and 2 are neither replayed nor removed from N. Limit: the arena has no perp ledger, so a `hedged` candidate could not go to paper trading without that ledger (C15 stays not applicable).
