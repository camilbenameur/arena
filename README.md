# Arena

A paper-trading arena where LLMs manage crypto portfolios, code validates every order, and everything is journaled and measured honestly.

**Live dashboard: [camilbenameur.github.io/arena](https://camilbenameur.github.io/arena/)** (rebuilt every 30 minutes).

> **Paper money only. Not financial advice.** No real order is ever sent to any exchange; all fills are simulated with pessimistic fees and slippage.

## What it is

An experiment in evaluating LLM "traders" under hard constraints. Claude models each run a simulated portfolio, next to benchmark portfolios that use no AI, so that every result can be compared with what a simple rule or pure chance would have done. There are three leagues:

- **Spot league**: 6 crypto/EUR pairs on Kraken, €1,000 of paper capital per portfolio, one decision every 4 hours plus event-driven wake-ups. Benchmarks: an equal-weight basket, a 60/40 portfolio, an adapted taker-pressure rule (E0065, signal from public Binance volumes) and a random trader that uses the same action space and risk rules as the models.
- **Perpetual-futures league**: Kraken Futures paper market, gross leverage capped at 2x for the models, stops set by the models, price alerts, entry orders and self-scheduled wake-ups, with read-only market tools exposed over an MCP server. Benchmarks: a 1x basket, a trend engine and a random trader. A rule-based robot, the *Wick Hunter*, reads prices every 5 seconds and fades liquidation wicks, next to the same rule played at a 5-minute pace.
- **Council league**: several models acting as one portfolio. The *Trend Council* lets a frozen trend engine decide while three Claude Haiku advisers and a Claude Opus president can only brake it (scale a position by 1, 0.5 or 0), compared with the engine alone.

Retired portfolios stay on the dashboard, archived, with their full history.

## How it works

1. Market data (REST) and news (exchange announcements, a macro calendar) are collected into a local store.
2. On a timer or a wake-up, each model receives a snapshot and returns structured decisions (through the `claude` CLI, isolated, or the API).
3. A risk engine (`riskd`) checks every intent against a hashed policy (leverage, size, drawdown halt); rejected intents are journaled with their reason.
4. A simulator fills orders pessimistically; every event is appended to a hash-chained journal.
5. A SQLite ledger is rebuilt from the journal, and a static site (HTML/JSON) is generated from it and published to GitHub Pages.

## Quick start

```bash
uv sync
uv run pytest -q -m "not network"
uv run arena --help
uv run arena verify       # check the journal chain
uv run arena status
```

A real cycle needs network access to public exchange data and either the `claude` CLI or an Anthropic API key (read from a `secrets` directory, never from the repository). `scripts/install-user-units.sh` installs the systemd user units that run the leagues, the dashboard and its publication.

## Integrity

- **Hash-chained journal**: `var/journal/events.jsonl` (and `var-perp/` for the perpetual-futures league), one line per event `{seq, ts, type, payload, prev_hash, hash}` with `hash = sha256(canonical record)`. No floats allowed; truncated lines are reported, never silently repaired. `arena verify` walks the chain.
- **Ledger**: a SQLite database that can always be rebuilt from the journal (`arena rebuild-ledger`).
- **Kill switch**: a sentinel file (`arena kill` / `arena unkill`) halts trading at the next cycle, optionally flattening positions at once.
- **Seasons**: a season freezes code, configuration, risk policy and prompt by sha256; any change aborts the next cycle unless a written waiver is journaled.

## Research

`research/` holds the offline protocol used before any strategy reaches the arena: firewalled data, strategy sheets written blind, a sandboxed engine, statistical gates (C1 to C16) and a sealed holdout read once. `research/reports/` has the results of the three research waves (no candidate survived), and `docs/RESEARCH-V5-AGGRESSIVE-2026-11-18.md` the study behind the Wick Hunter.

## Notes

- The project was first written in French and translated to English on 2026-11-20. The journals written before that date were converted to the English names (values unchanged, the conversion is recorded in each journal); the reasoning the models wrote before that date is still in French, as they wrote it.
- Using a personal LLM subscription as the decider may conflict with the provider's terms; use an API key if in doubt.
- Model names are those of the evaluated models; there is no partnership with their vendors.

## License

MIT, see `LICENSE`. Bundled fonts and chart library carry their own licenses (IBM Plex: OFL, uPlot: MIT).
