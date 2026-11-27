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
