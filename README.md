# Arena

A paper-trading arena where LLMs manage crypto portfolios, code validates every order, and everything is journaled and measured honestly.

> **Paper money only. Not financial advice.** No real order is ever sent to any exchange; all fills are simulated with pessimistic fees and slippage.

## What it is

An experiment in evaluating LLM "traders" under hard constraints. Several Claude models (Haiku, Sonnet, Opus, Fable) each run a simulated portfolio, next to benchmark portfolios that use no AI (equal-weight basket, 60/40, a trend engine, random trajectories). There are three leagues:

- **Spot league**: 6 crypto/EUR pairs, 1,000 EUR of paper capital per portfolio, one decision every 4 h, plus event-driven wake-ups.
- **Perpetual-futures league**: Kraken Futures paper market, up to 2x leverage, model-set stops, alerts and wake-ups, tools exposed over an MCP server.
- **Councils league**: groups of models (members plus a president) acting as one portfolio, compared with the single models.

## How it works

1. Market data (REST) and news/macro calendar are collected into a local store.
2. On a timer, each model receives a snapshot and returns structured decisions (via the `claude` CLI or the API).
3. A risk engine checks every intent against a hashed policy (leverage, size, drawdown halt); rejected intents are logged.
4. A simulator fills orders pessimistically; every event is appended to a hash-chained journal.
5. A SQLite ledger is rebuilt from the journal and a static site (HTML/JSON) is generated from it.

## Quick start

```bash
uv sync
uv run pytest -q -m "not network"
uv run arene --help
uv run arene verify       # check the journal chain
uv run arene status
```

A real cycle needs network access to public exchange data and either the `claude` CLI or an Anthropic API key (read from a `secrets` directory, never from the repository).

## Integrity

- **Hash-chained journal**: `var/journal/events.jsonl`, one line per event `{seq, ts, type, payload, prev_hash, hash}` with `hash = sha256(canonical record)`. No floats allowed; truncated lines are reported, never silently repaired. `arene verify` walks the chain.
- **Ledger**: a SQLite database that can always be rebuilt from the journal (`arene rebuild-ledger`).
- **Kill switch**: a sentinel file (`arene kill` / `arene unkill`) halts trading at the next cycle, optionally flattening positions at once.
- A season freezes code, configuration, risk policy and prompt by sha256; any change aborts the next cycle.

## Notes

- Code identifiers and most design documents (`docs/`, `research/`) are currently in French; an English translation is planned.
- Using a personal LLM subscription as the decider may conflict with the provider's terms; use an API key if in doubt.
- Model names are those of the evaluated models; there is no partnership with their vendors.

## License

MIT, see `LICENSE`. Bundled fonts and chart library carry their own licenses (IBM Plex: OFL, uPlot: MIT).
