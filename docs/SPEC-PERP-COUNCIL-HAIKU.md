# Derivatives league: the Haiku Council

> **Since 2026-11-15** (`docs/SPEC-COUNCILS.md`): the council has 11 members (10 Haiku advisors, including the Pairs Arbitrageur, and a President), instructions v2; it plays in the **councils league**, alongside the Opus Council (same advisors, Opus President). What follows remains true for everything else; resuming after ruin takes `--portfolio council-perp:haiku`.

## 0. Scope

The design is the following:
- **one** portfolio, `council-perp:haiku` ("Haiku Council"), of EUR 1,000, in the derivatives league;
- it is decided by **10 Haiku members**, each with the personality of one stage of the best public trading skills: 9 voices, plus 1 President who decides;
- the council trades aggressively, with the goal of doubling the stake in a few days;
- the 4 `llm-perp:*` portfolios do not change: their instructions (v7), decision schema and risk policy remain what they were.

## 1. The ten members and their sources

The roles are drawn from three public repositories. The URLs and star counts were checked on 2026-11-14.

- [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) (122 k stars): analysts, bullish and bearish researchers, trader, risk, manager.
- [tradermonty/claude-trading-skills](https://github.com/tradermonty/claude-trading-skills) (4.6 k stars): real SKILL.md files (crypto-regime-analyzer, contrarian-setup-gate, position-sizer, futures-position-sizer, drawdown-circuit-breaker, pre-trade-discipline-gate, signal-postmortem, breakout-trade-planner).
- [galleonlabs/hypergrok-trading-desk](https://github.com/galleonlabs/hypergrok-trading-desk) (516 stars): a perpetuals desk (desk lead, analysts, risk manager, execution, reviewer).

| # | Member | Stage | Role | Sources |
|---|---|---|---|---|
| 1 | The Mapper | A | regime of each contract (trend, range, volatility); filter | crypto-regime-analyzer; TradingAgents' Technical Analyst |
| 2 | The Follower | A | the trend that can be exploited now; continuation | breakout-trade-planner; Market Wizards |
| 3 | The Breakout Hunter | A | the explosive move that is starting, the entry point; continuation | breakout-trade-planner (momentum burst) |
| 4 | The Contrarian | A | overloaded consensus (funding, OI, RSI); against the trend | contrarian-setup-gate (Shapiro); bearish researcher |
| 5 | The Order Book Reader | A | does the order book support the entry, and at what cost; filter | HyperGrok (analysts, execution) |
| 6 | The Leverage Treasurer | A | size and leverage for the goal, without liquidation; sizes | position-sizer, futures-position-sizer; Kelly; Van Tharp |
| 7 | The Devil's Advocate | B | the best reason not to make the strongest trade; against the trend | TradingAgents' bearish researcher and debate |
| 8 | The Risk Guardian | A | stops, cumulative exposure, distance to ruin; bounds | drawdown-circuit-breaker, pre-trade-discipline-gate; HyperGrok's risk manager |
| 9 | The Historian | A | what the council has already missed or got right (hit rate, gain over loss) | signal-postmortem; Van Tharp's expectancy; HyperGrok's Trade Reviewer |
| 10 | The President | C | decides, sets orders, stops, sizes, alerts and recall; refuses soft consensus | TradingAgents' Portfolio Manager; HyperGrok's Desk Lead |

Disagreement is intended in the roles: 2 and 3 play continuation, 4 and 7 go against the trend, 6 and 8 size or bound, 1 and 5 filter. Each instruction cites its sources.

**The instructions:** `arena/perp/prompt/council/v1/`.
- A member's instruction is made of three parts: `common.md` (the council, the aggressive mandate, the rules, the tools, honesty), `roles/NN-<member>.md` (its role), then `opinions.md` (the format of an opinion), or `president.md` (the rules and the format of the decision) for the President.
- Each complete instruction has its fingerprint (`persona_sha256`) in each opinion. The fingerprint of the President's is the decision's `prompt_sha256`, and `council.prompts_sha256` combines all ten.

## 2. A council round

The council plays the **same triggers** as the four LLMs:
- the 4 h appointment;
- the 10 min cadence;
- market wake-ups;
- its own alerts and the recalls requested by its President.

It has its own round quota (`rounds_per_day` of `config/perp-llm.toml`, 260), and a council round counts as **one** round, not ten. For the league, it is a fifth player (`LlmLeague.players`) that occupies a slot of the pool of 4 parallel calls. Its ten calls run within that slot.

- **Stage A: 8 members in parallel** (1 to 6, 8 and 9), **without seeing each other**, 4 at a time (`members_parallel`).
  - Each member has its own `claude -p` process, its own MCP server (with its budget of 3 tool calls), and its own directory `rounds/<round>/council-perp_haiku/members/<member>/`, which contains a copy of `round.json`.
  - All receive the **same message**: the portfolio snapshot, with `council_summary` added. This message contains no opinion, and its fingerprint is in `round_data.message_sha256`.
  - Each returns a short JSON opinion: for each contract, `long`, `short` or `flat`, a conviction from 0 to 100, and optionally a size, a stop and a key level; then an argument of at most 3 sentences.
- **Stage B: the Devil's Advocate** receives the snapshot and the valid opinions from stage A. It designates its `target` (the strongest trade) and attacks it.
- **Stage C: the President** receives the snapshot and the valid opinions from stages A and B. It returns the decision in the **standard format** (actions, alerts, entry orders, `next_wakeup_min`, justification), with entry sizes up to 500%. It goes through the existing pipeline unchanged: `agent_decision`, riskd, simulated execution, then the alerts, the entry orders and the recall.

**Journal:**
- one `council_opinion` event per member of stages A and B (9), **before** the decision; it carries `member`, `name`, `stage`, `persona_sha256`, `opinion` (or `null` and `error`), `cost_uusd`, the tokens, `latency_ms`, `tool_calls` and `stream_sha256`;
- the President's decision in `agent_decision`, as for the others, with in addition `council`: the fingerprint of the instructions, that of the configuration, the members that succeeded and failed, and the President's cost, time and tool calls;
- the tool calls of all members in `tool_call`, with `member`;
- `round_data.council_config_sha256`.

**Failures:**
- A member that fails is set aside: its opinion is journaled with its error, the round continues, and the following ones do not see it.
- If the President fails, the round does nothing: the `agent_decision` carries `parse_error`, and the positions, stops and orders in place remain.
- **Interruption** (power cut, process killed): as for the LLMs, a round that has its `round_data` is never replayed. `stream.jsonl` is written from the start of the round, so that the resume marks it `interrupted_after_call`. What the interrupted calls cost is re-read from their streams (`stream.jsonl` of each member) and counted in the day's budget (`perp_llm_skipped.cost_uusd`), for the council as for the LLMs. An error of the council itself (disk full, unreadable file) never loses the cost of the calls made: the round ends without a decision, with that cost.

## 3. Cost and load

- **The cost of a round** is the sum of its ten calls.
  - A call that used the model without saying how much (timeout, truncated response) counts for its cap: a tenth of the round cap, i.e. $0.10.
  - The round cap comes from the league (`max_budget_usd` = $1, or what remains of the day's budget).
- **The council's daily budget** is **$10**, a cap. Measured on the league on 2026-11-14, a Haiku call costs about $0.0014 and takes 8 s at the median (11 s at most). A council round therefore costs about $0.015 to $0.02, i.e. $2 to $5 per day at 150 to 260 rounds.
- **The duration of a round** is about 1 min expected: two waves of 4 members, then the Advocate, then the President. In the worst case, with each call cut at 90 s, it takes 6 min; it starts as soon as a pool slot frees up, usually after Haiku alone, and at worst after 4 min. That makes 10 min at most, under the 15 min that systemd grants the watch.
- **The memory** of the host is the limiting factor: about 3 GB free, and 300 MB per `claude` process. With `members_parallel = 4`, there are at most 7 processes at a time: 3 LLMs and 4 members.

## 4. The council's risk policy

It is in `config/policy-perp-council.toml`, with the `aggressive` profile, and applies only to the council.

Doubling is impossible with the league policy: 2x, 3% loss per trade, freeze at -5% over 24 h, halt at -15%. The council's policy is hashed, journaled and copied into each verdict like the league's.

| Rule | League (4 LLMs, benchmarks) | Council |
|---|---|---|
| Total leverage | <= 2x (AMF margin of 50%) | <= 10x, with Kraken's margins |
| One entry | <= 50% of equity | <= 500% |
| One position | <= 100% | <= 1,000% |
| Stop | mandatory, 1 to 15% | mandatory, 1 to 15%, **before liquidation** |
| Loss at the stop of one trade | <= 3% | <= 25% |
| Loss if all stops are hit | <= 7.5% | <= 60% |
| Openings | 4 per 24 h, 4 h between two on a contract | 24 per 24 h, no delay |
| Daily freeze | -5% over 24 h: 24 h freeze | none |
| Fee budget | 3% per month | none (fees remain real) |
| Halt | -15% from the peak | -90% (the "ruin"); an operator restarts it with `resume` |
| Margin closeout | equity < 25% of exposure | equity < Kraken's maintenance margin, then 1 h without entry |
| Cost <= 1/3 of the move, move <= 30%, extreme funding, data and market checks | yes | yes, unchanged |

- **The `aggressive` profile** (`arena/perp/policy.py`) has its own consistency bounds:
  - leverage <= 10x;
  - loss of one trade <= loss of all stops < halt <= 95%;
  - freeze, fee budget and delay between two entries may be 0, which disables them.

  The two files never load in place of one another: each declares its profile, and the loader checks that it is the one it expects.
- **Simulated liquidation is realistic at 10x** (`arena/perp/margin.py`). For the council, the simulator and riskd use each contract's margin grid, as Kraken publishes it (`marginLevels` of `/instruments`):
  - to open, the initial margin: 1% of the notional for BTC, ETH and SOL, 2% for XRP, LINK and LTC, at the council's sizes (the first tier goes up to $200,000 for SOL, and up to $0.5 to 2M for the others);
  - for the margin closeout, the maintenance margin, which is half of it; it is tested every minute, at the worst price of the minute, with 5% liquidation fee on top.

  A contract without a grid is margined at 100%: no leverage. The AMF rule (50% and 25%) would have liquidated a 10x position as soon as it opened.
- **The stop before liquidation** (`LIQUIDATION_BEFORE_STOP`): the equity that remains when the position's stop is hit (the others at the current price) covers the maintenance margin, and this also holds when all stops are hit at the same time. With the caps of 25% and 60%, this rule does not bite today. It guarantees the principle if the policy changes.
- **It is the name that designates the portfolio margined at Kraken** (`council-perp:`), never the configuration. If the council's configuration does not load, the council stops playing, but an already open 10x position keeps Kraken's liquidation: the AMF rule would liquidate it at once. Its policy then becomes the league's, which is stricter: no entry beyond 2x, halt at -15%.
- **Outside the retail rule:** this portfolio exceeds the 2x leverage that the AMF imposes on retail investors for crypto CFDs. It is a **paper demonstration**: it could not go live as is. The instruction says so to the council, and the site must say so too (§6).

**Resuming after ruin:**

```bash
python -m arena.perp.council resume --portfolio council-perp:haiku
```

This command writes `portfolio_resumed` in the journal. It is an operator-only decision.

## 5. What does not change

- The 4 `llm-perp:*` portfolios keep:
  - instructions v7 (same fingerprint);
  - the same decision schema, byte for byte, with `size_pct` <= 100;
  - the policy of `config/policy-perp.toml` (same fingerprint);
  - the AMF rule in the simulator;
  - the same rules line in their snapshot.
- The benchmarks (basket, trend, luck) do not change.
- The only trace in their data: `round.json` now carries `policy.profile = "standard"`.

## 6. The site

- the council is a **separate category**, marked "aggressive · leverage <= 10x · goal x2", and it is **not ranked** with the neutral LLMs;
- its page shows the deliberation of each round: the 9 opinions (`council_opinion`), then the President's decision.

## 7. Configuration

- `config/perp-council.toml`, hashed, its fingerprint is in each council `round_data`. It contains:
  - `enabled`;
  - the portfolio and the model (Haiku only);
  - `daily_budget_usd = "10.00"`;
  - `members_parallel = 4`, `member_timeout_s = 90`, `member_max_tool_calls = 3`;
  - the name of the policy file.
- **An invalid configuration shuts down the council only**, with an alert `perp_council_config_invalid`, and never the LLMs nor the risk engine. `enabled = false` shuts it down too: its positions keep their stops and the watch continues to monitor them.
