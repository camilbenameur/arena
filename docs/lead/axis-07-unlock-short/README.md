# Axis 7: token-unlock dilution short (Phase 1)

**Verdict: blocked by tooling, not tested.** (The researcher first wrote "inconclusive: too few events"; the adversarial check showed that zero events means zero were attempted, not that few exist.) The feasibility gate was not reached: 0 events could be built with a point-in-time source and archive proof. No preregistration, `events_control.json`, `run_control.py`, design trial or placebo was written or run.

## What was done

- **Perp universe, point-in-time** (`perp_universe.py` -> `perp_universe.json`): first perp date per base asset. Kraken `PF_` via `openingDate` (195 contracts), else Binance USD-M via `onboardDate` (658 bases). 704 bases in total. Caveat: Binance `exchangeInfo` lists live symbols only, so delisted perps are absent (survivorship, small for this use). Many Kraken alt perps only opened in 2024, so Binance is needed as fallback for tokens whose cliff falls earlier; the arena can only trade the Kraken ones.
- **Gate counter** (`count_events.py`): reads `events_sourced.json` and `perp_universe.json` only. An event counts only with size >= 3% of circulating, recipient team/investors, cliff, date >= 2023-01, a source URL, an archive snapshot dated <= T-10, and a perp at T-10. Gate: total >= 60 and control (>= 2025-04-01) >= 25.
- **Result of the counter:** input events 0; design 0, control 0, total 0.

## Why there are no sourced events

- DefiLlama emissions: `https://api.llama.fi/emissions` returned 402 (tried once), as expected.
- DefiLlama's emissions-adapters repository is not reachable on GitHub (404, private).
- Wayback Machine: the availability API works and shows snapshots exist (for example `token.unlocks.app/arbitrum`, `tokenomist.ai/arbitrum`, `defillama.com/unlocks/arbitrum`), but every CDX query and every snapshot fetch returned HTTP 429. (The researcher claimed about 30 minutes of retries; the retained logs show 4 attempts over about 3 minutes on a single URL, and no logged CDX query. The blocker was tried briefly, not exhausted, and no other source was tried.). Without page fetches, neither schedule contents nor "public before T-10" can be shown for any event.
- Building the list from memory would give unverifiable records, which the protocol forbids. `leads_unverified.json` holds 15 recalled cliff candidates (month-level dates, no sizes) only as search leads; they are excluded from all counts. All 15 had a Kraken perp at T-10.

## Reading for the lead

- Even if the Wayback limit lifts, a 60-event build with archive proof needs at least 100 page fetches plus parsing of JS-rendered tracker pages (not checked: whether the snapshots embed the schedule), far beyond the 2-hour data budget. Many unlocks are also linear/monthly rather than cliffs, which shrinks the cliff count.
- Most Kraken alt perps opened in 2024 or later, so a Kraken-only universe cuts design-period events sharply; the control period is better covered.
- Retry conditions: Wayback access without 429 (different IP or later), then start with `leads_unverified.json`.

## Control price confirmation

No price data of any date (Kraken charts, Binance klines, data.binance.vision) was requested or loaded. Only instrument listings (names, opening dates) were read.
