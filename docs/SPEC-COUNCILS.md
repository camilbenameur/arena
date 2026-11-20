# The councils league

## 0. The design

The design is:
- **two councils**, each with **10 Haiku advisors and 1 President**: the Haiku Council (`council-perp:haiku`, Haiku President) and the Opus Council (`council-perp:opus`, Opus President);
- both have **the same advisors, the same instructions and the same policy**: only the President's model changes. The experiment measures what a stronger President is worth on the same opinions;
- both leave the perpetuals league and form the **councils league**. The perpetuals league goes back to: 4 AIs alone and their benchmarks.

The rest of a council's operation (steps, journal, failures, aggressive policy, Kraken liquidation) is that of `docs/SPEC-PERP-COUNCIL-HAIKU.md`, which remains the reference. This document says what changes.

## 1. Eleven members: a tenth advisor

The tenth advisor is **the Pairs Arbitrageur** (step A), drawn from `pair-trade-screener` of [tradermonty/claude-trading-skills](https://github.com/tradermonty/claude-trading-skills) (skills list read on 2026-11-15):
- it plays **relative value** between the six contracts: long the strong, short the weak, or the reverse when the gap is stretched (ratio of a pair and its distance from its mean, as a z-score);
- it also says when the open or proposed positions are only **a single bet** on the market's direction: the six contracts move almost together.

The council lacked it: the nine others judge each contract alone, none looks at their gap.

| # | Member | Step |
|---|---|---|
| 1 to 6, 8, 9 | the same as before | A |
| 7 | The Devil's Advocate | B |
| **10** | **The Pairs Arbitrageur** | **A** |
| 11 | The President | C |

**The v2 instructions** (`arena/perp/prompt/council/v2/`):
- `common.md` no longer names the council nor the model: "one of the eleven members of a trading council"; the portfolio is in the snapshot. The two councils therefore have identical instructions, byte for byte, and the same hashes;
- step A has 9 opinions, the Advocate reads the 9, the President reads the 10;
- `roles/10-arbitrageur.md` is new; the President moves to `roles/11-president.md` and knows the tenth member.

The v1 instructions stay in the repository: they are those of the rounds before 2026-11-15.

## 2. The Opus President

- `president_model` of each council's configuration: `claude-haiku-5-5` or `claude-opus-5-5`. The advisors are always Haiku (`model`).
- **Round caps** (the round's cap comes from the league: $1, or what remains of the day's budget): one twentieth per advisor ($0.05), half for the President ($0.50). Before, each member had a tenth ($0.10); an Opus President could have been cut off.
- **Timeout:** `president_timeout_s`, 240 s for Opus (like the Opus portfolio of the perpetuals league), 90 s for Haiku.
- `agent_decision.model_requested` is the President's model.

## 3. Cost

- **Haiku Council:** about $0.02 per round (11 Haiku calls), $3 to $5 per day; budget $10 per day, unchanged.
- **Opus Council:** 10 Haiku calls (about $0.02) and 1 Opus call (about $0.04 to $0.08: the Opus portfolio of the perpetuals league costs $0.037 per round on average, and the President reads ten opinions in addition), i.e. about $0.06 to $0.10 per round, $9 to $26 per day at 150 to 260 rounds; **budget of $25 per day**, a cap. The amounts are catalog equivalents: the deciders run on the subscription.

## 4. The league

`config/council-league.toml`, hashed; its hash is in each council `round_data` (`councils_league_sha256`):
- `enabled`;
- `councils`: the configuration files of each council (`perp-council.toml`, `perp-council-opus.toml`);
- `max_member_processes = 4`: the members' `claude` processes, **all councils combined**, at any one time. The host has about 3 GB free, and a process takes 300 MB: with the 4 LLMs, at most 7 processes, as with a single council before.

**What the league shares with the perpetuals league:** the engine, the journal (`var-perp/journal/events.jsonl`), the market data, the watcher, the triggers (scheduled rounds, 10-minute cadence, market wake-ups, alerts, recalls) and the round quota (`config/perp-llm.toml`). Each council has its own quota, budget and policy and occupies a slot of the pool of 4 calls. `portfolio_opened.league` stays `"perp"` (the perpetuals registry reads only that); it is `kind == "council"` that classifies a portfolio in the councils league, for the site.

**Failures:** a council whose file is invalid is left aside, with an alert `perp_council_config_invalid`; the other plays. An invalid league file switches off both councils, never the LLMs nor the risk engine. In both cases, the positions of a switched-off council keep their stops and the Kraken liquidation.

**Restarting a council after ruin** (an explicit operator decision):

```bash
cd <repository directory> && .venv/bin/python -m arena.perp.council resume --portfolio council-perp:opus
```

## 5. The journal

- `council_opinion`: 10 per round (9 from step A, then the Advocate), instead of 9. New member: `member = "arbitrageur"`, `name = "The Pairs Arbitrageur"`.
- `agent_decision.council` gains `name` ("Haiku Council", "Opus Council"), `members_model`, `president_model` and `prompts_version` (`"v2"`). These fields are absent from decisions before 2026-11-15: read Haiku and v1.
- The Opus Council opens (`portfolio_opened`, `kind = "council"`) at its first round, with €1,000.

## 6. The duration of a round

Expected: 1 to 2 min per council (9 advisors at 4 processes at most, shared between the two councils, then the Advocate, then the President). In the worst case, with each call cut at its timeout, a round of both councils would exceed the 15 min that systemd grants the watcher (`TimeoutStartSec=900`): the watcher would be killed, and the round marked `interrupted_after_call` at the next tick, its cost re-read from the streams, without being replayed. Extending this timeout is a service change: it requires an explicit operator decision.

## 7. The site

Done in parallel in `arena/site/`: the councils league has its own page, the councils leave the perpetuals league, and the deliberation displays the real number of opinions and the President's model.
