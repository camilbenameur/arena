# Research lead log

Daily log of the research lead. Tracker: GitHub issue #1. Paper trading only, starting capital EUR 1,000.

## 2026-11-27, day 1

**Health:** all services running. Spot journal verified (7,897 events), kill switch inactive, last presence confirmation 43 h ago.

**Standings (since each portfolio opened):**

| League | Portfolio | Return |
|---|---|---|
| Derivatives | Benchmark trend (20 days) | +9.8% |
| Derivatives | Benchmark trend engine | +7.8% |
| Derivatives | Trend Council | +7.0% |
| Derivatives | Sonnet / Opus / Haiku / Fable | +1.1% / +0.7% / -0.6% / -1.2% |
| Derivatives | Wick hunter (and 5-min twin) | 0.0%, no trade yet |
| Derivatives | Basket 1x | -10.1% |
| Spot | AIs | 0.0% to -0.6% |
| Spot | Benchmarks | -4.0% to -15.1% |

**Reading:** the only things making money are trend followers, in a falling market. Research v5 showed the trend engine lost 21% in the first 8 months of the year: its current gain is regime-dependent. The one rule that survived a sealed control (wick reversal) has not traded yet.

**Axis 1 started:** the frozen wick rule, with no retuning, on the other liquid Kraken Futures perpetuals. More contracts means more events (the rule fired on ~60 days per year on 6 contracts), and running a rule unchanged on instruments it never saw is a clean out-of-sample test. Stress tests: entry 1 minute late, doubled costs.

**Axis 2 done: no.** Cross-asset daily rules (trend, dual momentum, risk parity, bond carry, seasonality), 11 ETFs from 2008, design 2008-2015, sealed control 2016-2026 read once, 22 trials. No finalist beats buy-and-hold or 60/40 on return or Sharpe in the control. Best control: SPY November to April (7.2% CAGR) and risk parity (5.8%), against 11.4% for a global equity index and 7.6% for 60/40. Cross-asset rules only cut drawdowns. Kraken cannot trade these instruments anyway (an EU broker with UCITS ETFs would be needed). Details: `axis-02-cross-asset/README.md`.

**Axis 1 done: no.** The frozen wick rule does not generalise beyond the 6 contracts it was designed on. Same year, same bench, no retuning:

| Universe | Events | Base | Entry +1 min | Costs 48 bp |
|---|---|---|---|---|
| Original 6 | 92 | +295% / DD -37% | +173% | +155% |
| 5 new contracts, volume >= USD 5M | 287 | -34% / DD -85% | -50% | -83% |
| 26 new contracts, volume >= USD 1M | 1,497 | +1,129% / DD -95% | -41% | -98.5% |

On smaller coins the rule fires 2 to 7 times more often, at a much lower gain per trade (-1.8 to +15.6 bp against 71.5 bp): ordinary volatility, not liquidation wicks. The 26-contract result comes from one quarter and one coin (QNT: 64% of the P&L), and turns negative with a one-minute delay or doubled costs.

**Consequence for the live hunter:** it stays on the 6 large contracts, and its edge must now be read as a large-cap effect that has not been confirmed elsewhere. Its live record (still zero trades) is the next real test. No change to the robot.

**Next axes, ranked (`PLAN-v6.md`).** A 9-agent workflow (4 researchers by angle, 4 adversarial critics, 1 ranker) proposed 12 ideas, and the critics kept 2. The ranked plan:
1. resting bids on stablecoins below par on Kraken spot;
2. reversal after an open-interest washout, with a ladder of entry delays (to tell it apart from the wick effect);
3. a beta-hedged short before token unlocks;
4. dated-futures basis, as an add-on to the carry axis;
5. a short after hacks, sized by severity.

8 ideas were rejected, with reasons: macro-release windows, post-listing fade, perp premium fades, the gold-token spread, delisting shorts, and LLM classifiers (the control period lies inside the models' knowledge, so they leak). None is a fast-profit engine: realistic expectations are 0 to 8% per year, and the first three are mainly cheap falsifications.

**Axis 3 done: it works, but it is a cash substitute.** Market-neutral carry (long spot, short perp), Binance and Bybit funding from 2020, design up to mid-2024, sealed control after, 24 trials, Kraken retail costs.
- **Always-on BTC+ETH:** +2.1% a year in the control, max drawdown -0.4%, 90% of months positive. On Kraken's own funding over the last 12 months, +1.3%. It was +18.7% in 2021: the return follows the funding regime.
- **Variants:** every timing, rotation and cross-venue variant did worse, from -1.7% to +1.7% a year. A round trip costs 0.55% of equity, so anything that trades often loses.
- **Verdict:** worth running only as a low-risk benchmark (EUR 13 to 20 a year on EUR 1,000), not as a profit source. It is not added to the arena for now.

**Axis 4 done: inconclusive, not worth running.** Resting bids below par on Kraken stablecoins.
- **Fees:** stablecoin and FX pairs cost 0.20% per side, which kills the rule on USDT, USDC, PYUSD and RLUSD. Only USDG/USD (0.00% maker, 0.01% taker) is left.
- **USDG/USD:** it passes every criterion on paper, at about EUR 29 a year. But the result rests on 8 independent events in design (25 of 36 fills on the 2025-10-10 crash) and on a single one in the control (2 fills on 2026-10-07). No fill ever lost money, so the tail risk was never tested.
- **The two adversarial checks:** both judged the result unsound.
  - The preregistration cannot be shown to predate the design results.
  - The engine was written while the control period was being downloaded.
  - The fill model ignores the queue and counts sweeps as independent prints.

**Process fix from now on:** I commit each preregistration to git myself before any control run, so its date and content can be verified. The control-run lock also becomes a commit.

**Axis 5 done: no.** Reversal after an open-interest washout, on Binance 5-minute open interest from 2020-2021 for 6 contracts. Design runs to 2025, the sealed control covers 2026, 16 trials.
- **Result:** net of 0.20% round-trip costs, every delay from 5 to 60 minutes loses in both design and control. At 15 minutes the control loses -24 bp per event, or -1.7 bp counting one event per crash day. All 6 contracts are negative.
- **Before costs:** the rule earns +4 bp in design and -4 bp in control, far below the 20 bp of costs.
- **Not the wick effect:** removing the 7 to 19% of events that coincide with wicks changes nothing.
- **Verification:** both adversarial checks judged the result sound.

**Axis 6 stopped at the feasibility gate: too few events.** Short after a hack, sized by severity.
- **Event count:** DefiLlama lists 1,378 incidents. About 12 to 15 credible events per period have a perp on the affected token, almost all on Binance only and none on Kraken. That is at most 28 design and 24 control events, before any loss from missing timestamps.
- **Timestamps:** the dates are day-level only, with no source links, so an entry 30 minutes after the hack cannot be reconstructed.
- **Prices:** none were loaded, and the adversarial check confirms it.
- **Verdict:** not testable honestly.

**Axis 7 blocked by tooling, not tested.** Short before token unlocks.
- **No event built:** the agent could not assemble any event with point-in-time proof that the schedule was public. DefiLlama emissions is paid, and the Wayback Machine returned HTTP 429.
- **Overstated effort:** the adversarial check found the researcher claimed 30 minutes of retries, while the logs show 4 attempts over 3 minutes. Its "too few events" verdict really meant "not attempted". The README is corrected.
- **Kept for a retry:** a point-in-time perp universe (704 assets, first Kraken or Binance listing date) and 15 unverified leads. The retry would use other sources: archived tracker pages through a browser, project docs, or on-chain vesting contracts.

**End of day 1: 7 axes, no winning strategy to run.**
- **Clear no:** the wick rule beyond its 6 large contracts, cross-asset ETFs, the open-interest washout.
- **Holds but small:** market-neutral carry, about +2% a year.
- **Inconclusive:** stablecoin bids.
- **Untestable or blocked:** shorts after hacks, shorts before unlocks.

The only live candidate is still the wick hunter on the 6 large contracts, waiting for its first wick.

## 2026-11-27 evening, day 2 started early (at the user's request)

**Axis 8: LLM trading bots, tested without leakage.** The earlier rejection of LLM classifiers came from leakage: the control period was inside the models' knowledge. Every current model (Haiku 5.5, Sonnet 5.5, Opus 5.5, Fable 5.2) has a training-data cutoff of June 2026. A backtest on July to November 2026 is therefore clean: the models cannot know those prices.
- **Prompts:** no dates and no absolute price levels.
- **Split:** design July to September, sealed control October to November.
- **Comparison:** each bot is compared with the trend engine, the basket and a random bot with the same turnover.
- **Budget:** about $160 of API credit to use before December, through the Batch API (-50%), with a hard spend cap in the harness.
- **Phase 1 (now):** build the harness and a zero-cost dry run. Real runs start once the key is stored on this machine.

**Axis 8, harness ready and first batches submitted.**
- **Fixes:** the 8 flaws found by the checkers are fixed and re-verified. They were: a bypassable control gate, a dry run burning the control run, a non-atomic spend cap, a possible double batch submission, a bot id blind to the feature code, and June data in the first design month (design now starts 2026-07-31).
- **Pilots:** 2 calls per model, and every model accepted the JSON schema and the effort setting. Answers are short (~120 output tokens), so a full design pass in batch costs about $0.10 (Haiku), $1 (Sonnet), $2 (Opus) and $4.5 (Fable).
- **Wave 1:** Haiku x 2 prompts, Sonnet x 2, Opus x 1, all in batch. Spend so far: $0.10.

**Axis 8, wave 1 results (design window, 2026-07-31 to 2026-09-30, 372 decisions, batch, stateless bots).**

| Bot | Return | Max DD | Sharpe | Turnover | Beats random with same turnover |
|---|---|---|---|---|---|
| Haiku, plain prompt | +13.7% | -4.7% | 3.87 | 17x | 95% of draws |
| Haiku, cost-aware prompt | +14.7% | -5.3% | 3.27 | 35x | 80% |
| Opus, plain prompt | +10.0% | -7.8% | 2.54 | 18x | 60% |
| Sonnet, cost-aware prompt | +9.8% | -7.1% | 2.45 | 29x | 60% |
| Sonnet, plain prompt | +8.5% | -5.8% | 2.64 | 12x | 60% |
| Trend engine 2x | +37.1% | -27.3% | 2.63 | 39x | |
| Basket 1x | +45.8% | -11.9% | 4.30 | 1x | |

**Reading:**
- All five bots make money with small drawdowns, but they hold little exposure in a rising market. None beats the basket or the trend engine on return.
- Only Haiku with the plain prompt beats the random bot with the same turnover at the 95% level.
- Spend so far: $4.41.

**Wave 2 (running):** a third and last prompt variant, "overlay": start from the basket and deviate only with a view. It runs on Haiku, Sonnet, Opus and Fable, together with the other Opus and Fable variants.

**Axis 8, wave 2 and freeze.**
- **The overlay prompt** (start from the basket, deviate only with a view) brings every model close to the basket: +43.3% (Haiku), +45.8% (Sonnet), +44.2% (Opus), +44.9% (Fable), against +45.8% for the basket itself.
- **Fable:** with the plain and cost-aware prompts it does no better than Haiku (+14.0% and +14.8%).
- **On design, no bot passes all criteria.** Only Haiku beats the random bot with the same turnover, plain at the 95% level and overlay barely.
- **Freeze:** the preregistration is frozen and committed (04cdcfc). All 12 design bots go to the sealed control, with no selection, and both deviations are declared: Fable added, and the code hash changed only by the added variant.
- **Spend:** $22.09 at the freeze. The control runs are under way.

**Axis 8, sealed control done: all 12 LLM bots fail.** Control window October to November 2026 (342 decisions, a falling market). The basket lost 35.8%, while the trend engine at 2x gained +33.9%.

| Bot | Plain | Cost-aware | Overlay |
|---|---|---|---|
| Haiku 5.5 | -12.0% | -11.3% | -34.1% |
| Sonnet 5.5 | -5.1% | -3.8% | -34.6% |
| Opus 5.5 | -2.7% | -4.5% | -35.0% |
| Fable 5.2 | -5.5% | -4.5% | -35.4% |

- **Basket and trend:** every bot beats the basket but stays far below the trend engine, and none is positive in both months.
- **Timing:** the decisive test is the random bot built from each bot's own weights shuffled in time. The plain and cost-aware bots beat it in only 0 to 15% of draws (the random versions average about +3%). Their timing is worse than chance out of sample. On design, the same bots beat it in 55 to 95% of draws, so there is no stable skill.
- **Overlay:** the overlay bots simply track the basket down.
- **Incident:** the cost-aware Haiku submission failed with a connection error. The API batch list showed that no batch had been created, so its lock was removed by hand (logged in `control_overrides.jsonl`), and it ran once afterwards.
- **Spend:** $42.63.

**Verdict:** on data the models cannot have seen, Claude models deciding from prices every 4 hours do not trade profitably, at any model size or prompt tried. Bigger models lose less, but do not make money.

**Axis 8b launched (preregistration frozen, 3b83b15).** It runs with the remaining API credit.
- **Part A:** 3 replicates of each of the four plain-prompt frozen bots on the control, to measure the sampling noise of their result.
- **Part B:** Opus and Fable at high effort, in stateful mode (they see their own position, equity and drawdown), with the plain and cost-aware prompts, design then control.
- **Declared upfront:** the lead had already seen the axis 8 control results, so part B is a weaker out-of-sample test. Only effort and mode change, not the prompts.
- **Fixes made before launch:**
  - Resuming a run now repairs a torn decision file before appending.
  - A finished run can no longer be resumed.
  - Batches reserve against 2,200 output tokens per request instead of 16,000. The largest output seen so far is 439. This is declared in the preregistration.

**Axis 8b, part B design (high effort, stateful, sync).** Opus plain +5.0%, Opus cost-aware +10.6%, Fable plain +12.1%, Fable cost-aware +12.8%. These bots trade less (turnover 4 to 7x), but they beat the random bot with the same turnover in only 10 to 20% of draws, worse than the low-effort stateless bots on the same window. Knowing their own position and thinking harder did not help on design. All 4 go to the control as preregistered. Ledger: about $80.

**Axis 8b, part B control: all 4 fail.** Opus plain -2.4%, Opus cost-aware +0.2%, Fable plain -4.4%, Fable cost-aware -4.2% (October to November 2026). Each beats the random bot with the same turnover in only 0 to 10% of draws. Thinking harder and knowing its own position lowers turnover and drawdown, but the bots still pick their moments worse than chance. Ledger after part B: $117.

**Axis 9: Claude Fable as a researcher, not a trader.**
- **Setup:** Fable got only the design data (4-hour bars, July to September 2026) and a code sandbox. It used no network, as the transcript shows.
- **Its own verdict:** in one session it ran 14 trials, each with a mechanism written down in advance. It labelled its result "no robust edge found". It froze a volume-weighted 7-day momentum rule with hysteresis and a volatility target, and predicted a Sharpe of 0 to 0.3 out of sample. Cost: $1.14.
- **Sealed control:**
  - Results:
    - October to November: +10.0%, max drawdown -8.5%, Sharpe 2.74.
    - Design: +10.1%.
  - Against the references, it beats the basket (-35.8%) but not the trend engine at 2x (+33.9%). It is flat in October (-0.2%), and the random bot with the same turnover (+16.4% on average) beats it in 90% of draws.
  - It fails the preregistered criteria, but it is the only LLM-originated result that is positive out of sample. Its honest self-assessment matched what happened better than any trading bot did.

**Axis 8b, part A: replicates (original control run + 3 replicates per plain-prompt bot).**

| Bot | Returns over 4 runs | Mean | Beats same-turnover random |
|---|---|---|---|
| Haiku | -12.0% to -6.4% | -9.2% | 0 to 10% of draws |
| Sonnet | -7.0% to -2.8% | -4.9% | 0 to 5% |
| Opus | -4.4% to -0.4% | -2.4% | 0 to 10% |
| Fable | -5.5% to -4.6% | -5.1% | 5 to 15% |

The losses are stable across samples: no run of any model is positive. Total API spend so far: $124.8 (axis 8: $123.6, axis 9: $1.2).

**Axis 9b: a population of LLM researchers (preregistration cebde1f).** 27 independent sessions: 17 Fable, 10 Opus. Each got only the design data and its own code sandbox, used no network, and returned 25 frozen rules in all (2 sessions dropped). Every rule was evaluated once on the sealed control (October to November 2026).

| | Rules | Mean control return | Positive | Mean of same-turnover random |
|---|---|---|---|---|
| Fable 5.2 | 15 | +1.1% | 6 | |
| Opus 5.5 | 10 | -4.1% | 3 | |
| All | 25 | **-1.0%** (median -5.0%, sd 16.1) | 9 | **+2.7%** |

- **Primary reading:** negative. The mean is below 0 (t = -0.3) and below the same-turnover random bots (difference -3.7 points, t = -3.9).
- **Against the references:** no rule beats the trend engine at 2x (+33.9%), none passes all the axis-8 criteria, and only 1 of 25 beats its own random p95. 23 beat the basket (-35.8%), but 2 Opus sessions simply froze "hold the basket" (-36.2%).
- **What drives the results:** each rule's control return tracks its net long or short lean, not its timing. Its random version, made of the same weights shuffled in time, lands on the same side.
- **Self-assessment:** all 25 sessions labelled themselves "no robust edge found". Their honest self-assessment was the most reliable output of the experiment.
- **Spend:** axis 9 and 9b cost $23.6. API total: about $147 of the $160 credit, plus about $5 held for the two dropped sessions.

**Conclusion of axes 8 to 9b (LLMs, data after their training cutoff):** neither as traders (12 bots, 16 replicates, 4 high-effort stateful bots) nor as researchers (26 rules) did Claude models produce a trading edge out of sample. They are useful for honest critique and for running the protocol, not for alpha.

## 2026-11-28, day 3

**Health:** all services running overnight, journal verified, kill switch inactive, last presence confirmation 60 h ago.

**Axis 10 (started): the frozen survivors on six years never used to choose them.** Research v5 selected the wick rule and the trend engine on Kraken data from 2025-11 to 2026-11 only. Binance minute data from 2020 is already on disk from axis 5. Axis 10 runs:
- the frozen wick rule, unchanged, on 2020 to 2025 per year, with the delay and cost stress tests;
- the frozen trend engine on the same years;
- a portfolio of wick, trend and carry, with weights fixed before looking.

The pass rules are written before any computation:
- the wick rule must be positive in at least 4 of 6 years and positive overall with a 1-minute delay;
- the trend engine must be positive in at least 4 of 6 years.

**Axis 10 done: neither frozen survivor holds over 2020 to 2025.** Binance minute data, never used to choose the rules. Both checks judged the result sound.
- **Wick rule (the live wick hunter):**
  - Positive in 0 of 6 years, even restarting each year at full equity.
  - -34.7 bp per trade over 3,664 trades, against +72 bp on the Kraken year it was chosen on. On these years it fires 250 to 1,400 times a year, against 92 on that year.
  - Per contract, only BTC alone is near break-even (+9 bp per trade). Every alt is ruined.
  - The 2025-2026 edge was specific to that year: it holds neither across contracts (axis 1) nor across time (axis 10).
- **Trend engine (Trend Council and its benchmark):** at 1x, +36.9, +5.0, -29.5, +54.8, -15.1 and -28.1% per year, so 3 of 6 positive (the threshold was 4). Total -4.2%, max drawdown -63%. At 2x, the live setting: -71.6%, max drawdown -92%.
- **Carry:** positive every year, +7.1% a year with a -1.0% max drawdown. Only a cash substitute.
- **Portfolio (equal thirds, fixed in advance):** -99.2%, ruined by the wick sleeve. Post hoc only, trend 1x plus carry at 50/50 gives +36.3% with a -32.8% max drawdown.

**Consequence:** both robots now in service in the derivatives league (wick hunter, Trend Council at 2x) are, on the long history, lottery tickets with a ruin risk. They trade paper money, so nothing real is at stake, but the site presents them as research results. Decision for the owner: keep them running as documented experiments, or retire them.
