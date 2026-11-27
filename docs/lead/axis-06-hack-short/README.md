# Axis 6: short after a hack, sized by severity

**Verdict: inconclusive: too few events.** The feasibility gate failed, so no backtest was written or run.

## Method of the count (no price data touched)

- Events: `https://api.llama.fi/hacks` (1,378 incidents; fetched 2026-11-27). Incidents from 2021-01-01 with amount >= USD 1M: 436.
- Perp availability: Kraken Futures `PF_` instruments (`/derivatives/api/v3/instruments`, 195 contracts) and Binance USD-M symbols (directory listing of data.binance.vision, 1,081 symbols, delisted ones included; the listing gives names only). Almost every candidate is Binance-only: no hacked protocol token other than major chain tokens has a Kraken `PF_` perp.
- Token mapping: hack name matched to a DefiLlama protocol (`api.llama.fi/protocols`) and its token symbol; bridge/chain hacks mapped to the chain's native token.
- Severity denominator: DefiLlama protocol TVL on the day before the incident (`api.llama.fi/protocol/<slug>`), or chain TVL (`/v2/historicalChainTvl/<chain>`) for bridge hacks. Point-in-time market cap is not available from a free source beyond 365 days, so TVL is the only point-in-time denominator. Where TVL is missing (non-DeFi tokens), severity is unknown and the event is counted in the upper bound.
- Script: `count_events.py`; output (dates, tokens, amounts, TVL ratios, no prices): `candidates_nopriced.json`.

## Counts (generous upper bounds, before any timestamp filter)

| Period | Events with perp token | Severity >= 5% by TVL or severity unknown |
|---|---|---|
| Design 2021-01..2024-06 | 59 | 25 |
| Control 2024-07.. | 57 | 20 |

These upper bounds are inflated:
- Chain-TVL ratios for bridge hacks are near zero or meaningless (native-token market cap is not chain TVL); every bridge hack on ETH, BNB or SOL falls out at 5%.
- Several matches are spurious (Alpha Finance mapped to BTC, PancakeSwap, Treasure, Onyx at TVL near zero giving ratios of 300x, 1inch and Yearn Ether where a tiny TVL inflates the ratio while the token market cap ratio is about 1%).
- Credible own-token events with severity at or above 5%: about 12 to 15 in design (for example DODO, Badger, Raydium, dForce, Kyber, WOOFi, Loopring, Elrond, Compound, Euler, Onyx) and about 12 to 15 in control (Radiant, Abracadabra x2, Cetus, GMX, WOO X, UXLINK, Balancer, Resolv, Drift, Humanity, Taiko, Lighter, Initia).

## Timestamps

The llama hacks feed has a day-level date and no source link for any of the candidate events (0 of 45 have a URL). An intraday timestamp has to be dug out by hand per event (post, explorer transaction, article). Even if every one of the 25 design upper-bound events yielded a timestamp, the design count would only reach the gate of 25 with no loss at all, and the first-minute move of a hack is usually not recoverable to 5-minute precision from articles. The control side needs 15 of about 12-20 events, again with no loss.

## Gate

- Design: at most 25 upper bound, about 12 to 15 credible, fewer after timestamp loss. Gate needs 25 with timestamps: **fail**.
- Control: about 12 to 15 credible, 20 upper bound, before timestamp loss. Gate needs 15 with timestamps: **fail or marginal at best**.
- Either failure stops the axis, as the plan predicted ("inconclusive: too few events").

## What was not done

No timestamp recovery, no preregistration, no `events_control.json`, no `run_control.py`, no design trials, no placebo. Nothing was loaded from any price source: no Kraken or Binance candles or klines, for any date. The control period was only touched through event dates, names and TVL.

## Adversarial check (lead's note)

The STOP verdict is sound, and no control-period price was loaded. The check found weaknesses that would matter if the axis ever resumed:
- **Counts:** the severity filter is not in `count_events.py`. Recomputed from `candidates_nopriced.json`, it gives 28 design and 24 control events, not 25 and 20. The "credible 12-15" figures are a manual judgement.
- **Event list:** perp availability and token mapping use today's state (listing dates ignored, delisted symbols kept, crude name matching). That is look-ahead and survivorship, acceptable for a feasibility count but not for a preregistered event list.
- **Timestamps:** every one of the 116 candidates has an empty source field, not only 45 of them.
