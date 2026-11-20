# Perpetuals league: free LLM wake-ups

The time restrictions on the LLMs are removed so that they wake up more often and when they really want to, with far fewer constraints.

**Amended by `docs/SPEC-PERP-CADENCE.md`**: requested wake-up from 5 to 60 min, 144 rounds per day, default cadence of 15 min, instructions v6.

Concerns the perpetuals league only. Spot stays frozen (Season 1) and is not modified. Complements `docs/SPEC-PERP-ORDER-ALERTS.md`, whose §3 (limits of the alert wake-up) and instructions v4 are replaced by what follows.

## 1. The wake-up requested by the agent

The structured output gains an optional field, `next_wakeup_min`: an integer from 5 to 240, or `null`.

- The requested time counts from the moment the decision is applied (`due_ts` = application time + minutes).
- **A single pending wake-up per agent.** Each valid decision, applied on a fresh view, replaces it, or cancels it if it requests none. A missing or invalid decision does not touch it.
- An invalid value (out of bounds, non-integer decimal, boolean, text) is rejected alone, like a rejected order (`rejected` of `agent_orders_set`, `kind: "wakeup"`). The rest of the decision stands, and **so does the pending wake-up**: an invalid value requests nothing and cancels nothing. `60.0` counts as 60 (the CLI's JSON schema counts it as an integer).
- The wake-up is **served** by the first round of the owner that starts at most 5 min before the requested time: its private round, but also a scheduled round or a market wake-up.
- The watcher serves a wake-up at the first check (every 5 min) that starts at most 2 min 30 s before the requested time. A wake-up that could not be served within the hour lapses: it is never served late.

## 2. Private rounds

A **private** round (`kind: "private"`) serves, at once, all the agents that have a crossed alert or a requested wake-up to serve at that tick:

- `perp_round` `{round, kind: "private", portfolios: [...], triggers: {portfolio: trigger}, trigger: null, ts}`;
- each agent's trigger: `{"kind": "alert", alert_id, instrument, condition, price_usd, note}`, plus `asked_wakeup_ts` if a requested wake-up falls due too; or `{"kind": "scheduled", asked_at_round, due_ts}`;
- each agent plays alone, with its trigger, and sees nothing of the others'. The call type it sees (`call.type`, `kind` of `round_data` and `agent_decision`) is `alert` or `scheduled`;
- neither the benchmarks nor the other models play.

The `alert` rounds from before this change (a single owner, a common `trigger`) remain readable and are handled the same way.

**No time limit specific to alerts and requested wake-ups any more.** The maximum of 4 per day, the 1 h delay and the 30 min guard before a scheduled round are removed. What remains:

- **one round per tick**: an agent never plays twice less than 5 min apart;
- **a scheduled round within 5 min**: no unscheduled round; the scheduled round serves alerts and wake-ups;
- **the round quota** (§4) and the daily budget;
- a halted portfolio is never woken.

## 3. Market wake-ups

- Threshold: **2%** in 1 h instead of 3% (reset at 1.5% instead of 2%).
- **15 min** between two market wake-ups instead of 1 h; **no daily maximum any more**.
- Guard before a scheduled round: 5 min instead of 30.
- Private rounds do not count in this delay.
- Models that have no unscheduled round left that day, or no budget left, or are halted, do not play this wake-up: `portfolios` then lists those that play. If no model can play, there is no wake-up. The random benchmark plays market wake-ups as before.
- A crossing is noted (`perp_wake_pending`) at each tick, even when no round can start (scheduled round, spot cycle): it stays servable for an hour.

## 4. The round quota, the only time limit

- `rounds_per_day = 48` per model per UTC day, scheduled rounds included (`config/perp-llm.toml`), the same for the 4 agents. On average one round every 30 min, which the agent spreads as it wants.
- A played round is a `round_data` of the portfolio that day.
- **The remaining scheduled rounds of the day are reserved**: an unscheduled round is played only if at least one round remains once these scheduled rounds are subtracted. A scheduled round is always played.
- The agent sees its quota in its snapshot, under `account.rounds`: `rounds_per_day`, `rounds_played_today`, `scheduled_rounds_left_today`, `unscheduled_rounds_left` (after this one) and `wakeup_requested_utc`.
- **Daily budgets raised** so as never to block before the quota, at the costs measured on 2026-11-13 at 14:03 (Haiku $0.002, Sonnet $0.037, Opus $0.077, Fable $0.164 per round): Haiku $0.20, Sonnet $2.00, Opus $4.00, Fable $8.50 per day. If all 4 agents use their whole quota, that is about $15 per day in API equivalent, on the subscription.

## 5. The spot cycle

The forbidden span (from 5 min before to 30 min after a spot cycle) becomes a queue:

- no unscheduled round starts within the 5 min before a spot cycle (HH:05 to 00, 04, ... UTC): a round lasts at most about 4 min;
- none starts while the spot league holds its cycle lock (`var/cycle.lock`, taken by a cycle or by a check of the spot watcher and its wake-up). It waits for the next tick;
- the perpetuals league only **tests** this lock, and only when a round is about to start: it takes it for a few microseconds and releases it at once. The spot watcher runs at :00:30, :05:30..., the perpetuals watcher at :03:30, :08:30...: the two do not cross in practice, and the spot cycle waits for the lock up to 10 min;
- an interrupted round waiting for the spot league does not prevent a due scheduled round from starting;
- the perpetuals scheduled rounds (02, 06, ..., 22 UTC) are 2 h from the spot cycles and do not wait.

**What is not covered:** a spot-league wake-up that starts during a perpetuals round. Preventing it would require modifying the spot watcher, which is frozen. An exemption would have to be decided explicitly.

## 6. What does not change

riskd; mandatory stops; leverage ≤ 2x; confidentiality between agents; idempotence; `max_parallel = 4`. An entry-order trigger older than 15 min is never executed.

Instructions v5 describe the requested wake-up and the quota, without pushing to wake up or to trade: "Ask for a recall when you have a specific reason to look again at that moment; otherwise, do not ask for one."

## 7. Events (`var-perp` journal)

| Type | Payload |
|---|---|
| `agent_wakeup_set` | `portfolio, round, minutes, due_ts`; `minutes` and `due_ts` set to `null`: the pending wake-up is cancelled (written only if there was one) |
| `perp_round` | `kind: "private"`, `portfolios`, `triggers` (§2); `kind: "wakeup"` may carry `portfolios` when models have no round left |
| `round_data`, `agent_decision` | `kind`: `rendezvous`, `wakeup`, `alert`, `scheduled` |
| `agent_orders_set` | `rejected` may contain `{kind: "wakeup", k: 0, error}` |

The state is recomputed from the journal: pending wake-up = the portfolio's last `agent_wakeup_set`, if it has a `due_ts` and no round of the portfolio starting at most 5 min before has served it.
