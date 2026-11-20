# Perpetuals league: cadence and trader instructions (v6, then v7)

**Since 2026-11-14, see §5:** the 10-minute cadence became a ceiling, 260 rounds per day, instructions v7, budgets revised. §1 to §3 describe the state of 2026-11-13 (15 min, a requested recall replaces the cadence).

Spec of 2026-11-13. The motivation: the LLMs activate too rarely; several times per hour is wanted, and above all still no forced trades.

Concerns the perpetuals league only; spot stays frozen. Complements `docs/SPEC-PERP-FREE-WAKEUPS.md`, whose §1 (bounds of the requested wake-up) and instructions (v5 replaced by v6) it changes.

## 0. The findings (journal of 2026-11-13, 02:00 to 18:03 UTC)

- **24 decisions, 0 entries.** All conclude "no clear edge, I stay flat", often citing the round-trip cost.
- **0 recalls requested** since the free wake-ups went live (16:00 UTC). The recall was optional, and instructions v5 discouraged it ("Each round costs... otherwise, do not ask for one"). The agents played only at scheduled rounds and at 2 market wake-ups: 6 rounds in 16 h.
- Instructions v5 pushed toward doing nothing: "Doing nothing is a valid decision, and often the best", "look for the best decision, not the most active".

## 1. The default cadence

New key `cadence_min` of `config/perp-llm.toml`: **15**. 0 switches it off; otherwise from 5 to 60.

- An agent with **no pending recall** is recalled `cadence_min` after **its last round**, whatever it was (scheduled round, wake-up, alert, recall, cadence, including a round without a valid decision). It is served by the watcher's check that starts at most 2 min 30 s before that time.
- It plays in a **private round**, with the trigger `{"kind": "cadence", "every_min": 15, "last_round_ts": ...}`; the call type it sees is `cadence`. Several agents due at the same tick share the private round, each with its own trigger.
- A round whose preparation failed (`perp_llm_skipped`) counts as a round for the cadence: it is not retried at every tick.
- `wakeups = false` switches off the market wake-ups, not the cadence: the cadence is switched off with `cadence_min = 0`.
- **A recall it requested replaces the cadence** as long as it is pending: `next_wakeup_min` now goes from **5 to 60** (instead of 240), so that an agent is always recalled at least once per hour. A valid decision without `next_wakeup_min` cancels the pending recall: the agent returns to the cadence.
- The same conditions as for the other private rounds apply: agent not halted, daily budget, rounds of the day, one round per tick, nothing within the 5 min before a scheduled round, queue behind the spot league. A market wake-up goes first, and also serves the cadence (it is a round).

## 2. The day's rounds and the budgets

- `rounds_per_day`: **144** (instead of 48), i.e. one round every 10 min on average: the 96 of the cadence, plus the alerts, the market wake-ups and the closer recalls. The remaining scheduled rounds of the day are still kept.
- Daily budgets, so that the quota comes before them: Haiku $0.50, Sonnet $8.00, Opus $16.00, Fable $36.00 (costs measured on 2026-11-13 on rounds without a trade: $0.002, $0.033, $0.072 and $0.166 per round; a margin of about 1.5x for rounds that trade).
- **Expected cost**, in API equivalent on the subscription: about $27 per day at the cadence alone (≈ 100 rounds per agent) at the cost of rounds without a trade, more when the agents trade; $60 at most (the budgets). Fable accounts for more than half. A model out of budget is no longer called until midnight UTC, scheduled rounds aside.

## 3. Instructions v6

- The agent is a **trader**: it is there to take positions and manage them.
- **No certainty needed**, only a positive expectation after costs: a modest view justifies a small position (5 to 15% of equity) with a tight stop, rather than nothing.
- Long and short are equal.
- **Staying flat is a bet like any other**, judged like the others: it earns nothing and cannot beat any benchmark. The agent stays flat only if it has no view on any of the six contracts, and it says why.
- At each call, it manages what is open. It uses its openings (the guardrail limits their number) and its entry orders.
- It gives the guardrail's cost threshold (expected move of at least about 0.8%) and the monthly fee limit, so that "small position" does not end in a refusal.
- Removed: "often the best", "not the most active", "Each round costs".

**Nothing obliges an agent to trade**: no minimum exposure is imposed, and the guardrail (riskd) does not change. It still limits to 4 openings per 24 h, with 4 h between two openings on the same contract, leverage 2x at most.

## 4. What does not change

riskd, stops, leverage, private rounds, idempotence, `max_parallel` 4, no trigger executed beyond 15 min, scheduled rounds every 4 h, benchmarks, spot frozen.

## 5. 10-minute cadence, ceiling of the gap (2026-11-14)

The allowed consumption is doubled relative to the current one. Instructions v7.

- **The findings:** from 18:28 to 01:40 UTC, about $2.3 in API equivalent, i.e. roughly $8 per day. Three agents were asking for a 30 min recall on their own, which put them at 2 or 3 rounds per hour.
- **`cadence_min` = 10, and the cadence becomes a ceiling:** an agent is recalled **at the latest** 10 min after its last round. A recall it requested can only bring this call forward (to 5 min): requested later than the cadence, it no longer delays it. The `next_wakeup_min` values are still accepted from 5 to 60, but only 5 to 7 bring the call forward by one tick; the instructions suggest only 5.
- **6 rounds per hour per agent**, instead of 2 to 3. `rounds_per_day`: 260 (the cadence alone makes 144; an agent that asked for 5 min at every round would play 288).
- **Expected cost:** about $20 per day (Haiku $0.2, Sonnet $2.1, Opus $5.3, Fable $12 for 144 rounds; $28 at 200 rounds), at the mean cost per round measured that night ($0.0014, $0.014, $0.037 and $0.084), i.e. 2 to 2.5 times the previous consumption. Fable accounts for more than half.
- **Daily budgets**, caps against a runaway and not targets, at about twice the expected cost: Haiku $0.50, Sonnet $5, Opus $14, Fable $30.
