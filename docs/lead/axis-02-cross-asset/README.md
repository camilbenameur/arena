# Axis 02: cross-asset daily strategies vs buy-and-hold and 60/40

Question: for a EUR 1,000 account, does a simple daily-rebalanced cross-asset rule beat (a) a global equity index and (b) a 60/40, on risk-adjusted and raw return, net of costs, out of sample?

**Verdict: no.** None of the 5 finalists beat buy-and-hold ACWI/SPY or 60/40 on raw return in the sealed control, and none beat them on Sharpe. The best (C3, inverse-vol core 5) delivered a Sharpe of 0.51 vs 0.54 for 60/40 and 0.58 for ACWI, with a lower return (5.8% vs 7.6% / 11.4%). Nothing here is worth a new paper portfolio.

## Data (Yahoo chart API, adjusted close = total return; Stooq now sits behind a JavaScript challenge)
Stored outside git in `~/dev/_arena-data/axis-02/`. Tradable proxies, all liquid ETFs, USD: SPY (1993), EFA (2001-08), EEM (2003-04), TLT/IEF/SHY (2002-07), GLD (2004-11), DBC (2006-02), VNQ (2004-09), FXE (2005-12), FXY (2007-02), UUP (2007-03), ACWI (2008-03, the "global equity index" reference), BTC-USD (2014-09, spot, no ETF before 2024), ETH-USD (2017-11, downloaded but unused: it starts after the design cut). ^IRX (3-month bill) is the cash rate, ^TNX minus ^IRX the term spread. No index data was spliced in; all history is the ETFs themselves. Common start of the 11-ETF universe: 2007-03; with a 12-month warm-up the evaluation starts 2008-04-01. FX rate-differential carry was not testable (no free policy-rate series obtained), so the carry family is only bond term premium.

## Protocol
- Design 2008-04-01 -> 2015-12-31 (7.7 years, includes the 2008 crisis; thin). Sealed control 2016-01-01 -> 2026-11-25 (10.9 years). Design code only ever sees data truncated at 2015-12-31.
- `control.py` was written before any control number was seen, refuses to run twice, ran once for all finalists together. All finalist control results are reported.
- Finalist rule, fixed beforehand: best design Sharpe in each family group (trend, momentum/dual, risk parity, carry, seasonality) = at most 5.
- 22 logged trials (`trials.jsonl`, failures included, none dropped). Standard parameters only (252d momentum, 210d SMA, 60d vol, 10% vol target); no sweeps.
- Execution: signal on close t, trade at close t+1, position earns from t+2. Cost 10 bp per side on all traded weight; no-trade band of 2 pp per asset (fixed, to avoid micro-trades). Cash earns the 3-month bill rate (generous for a EUR account: Kraken pays nothing on idle cash). 2x variant = same weights x2, borrowing at bill rate + 0.5%/yr. All in USD; EUR/USD currency risk and UCITS vs US-ETF differences are ignored. Fractional shares assumed available. The reference 60/40 (60% ACWI / 40% IEF) is rebalanced daily and cost-free, which favours it; the references pay no cost at all.
- Sharpe is on excess over the bill rate. DSR: probability that the true Sharpe is above the threshold implied by selecting the best of 22 trials (threshold SR about 0.27 annualised given the spread of trial Sharpes).

## Finalists
- **D2 carry**: hold IEF when 10y-3m term spread > 0, else cash. Rationale: bond term premium is earned when the curve is positively sloped. Note: in design the spread was never negative, so this was literally buy-and-hold IEF (zero trades); the design Sharpe of 0.62 is a rates-fall regime, not evidence for the rule.
- **E2 seasonality**: SPY from November to April, cash otherwise (Halloween effect). 2 trades per year.
- **C3 risk parity**: inverse 60-day-vol weights on SPY, TLT, IEF, GLD, DBC, always 100% invested, 2 pp band.
- **A5 trend**: 12-month time-series momentum on all 11 ETFs, each long-or-flat, sized to 10% vol / N, gross <= 1x, rest cash (Moskowitz-Ooi-Pedersen style, long-only).
- **B4 dual momentum**: best of SPY/EFA if its 12-month return > 0, else IEF (GEM-like).
Cross-sectional momentum alone (B1) and the BTC variants (A7, B5, C4) were tried and did not win their family.

## Results
### Design (2008-04 to 2015-12)
| | CAGR | Vol | Sharpe | Max DD | Worst year | % pos. years |
|---|---|---|---|---|---|---|
| D2 | 4.6% | 7.4% | 0.62 | -10.4% | -6.6% | 75.0% |
| E2 | 8.2% | 14.4% | 0.61 | -31.6% | -1.1% | 87.5% |
| C3 | 4.0% | 7.1% | 0.57 | -11.0% | -5.9% | 75.0% |
| A5 | 1.5% | 3.6% | 0.40 | -3.9% | 0.1% | 100.0% |
| B4 | 4.5% | 15.3% | 0.36 | -20.5% | -11.3% | 62.5% |
| REF BH_ACWI | 3.6% | 23.7% | 0.26 | -56.3% | -34.3% | 62.5% |
| REF BH_SPY | 8.0% | 22.1% | 0.45 | -51.5% | -30.3% | 87.5% |
| REF 60_40_ACWI_IEF | 4.9% | 13.2% | 0.42 | -34.9% | -16.9% | 75.0% |

### Sealed control (2016-01 to 2026-11)
| | CAGR | Vol | Sharpe | Max DD | Worst year | % pos. years | turnover/yr | trades/yr |
|---|---|---|---|---|---|---|---|---|
| D2 1x | 1.2% | 5.3% | -0.18 | -22.6% | -15.0% | 72.7% | 2.6x | 3 |
| D2 2x | -0.6% | 10.6% | -0.22 | -42.3% | -30.1% | 63.6% | 5.1x | 3 |
| E2 1x | 7.2% | 14.5% | 0.39 | -33.7% | -12.6% | 72.7% | 2.1x | 2 |
| E2 2x | 9.7% | 29.0% | 0.39 | -58.8% | -27.2% | 54.5% | 4.2x | 2 |
| C3 1x | 5.8% | 7.0% | 0.51 | -18.9% | -11.8% | 81.8% | 0.8x | 33 |
| C3 2x | 8.3% | 14.0% | 0.47 | -35.7% | -25.1% | 72.7% | 1.6x | 33 |
| A5 1x | 3.0% | 3.7% | 0.19 | -7.6% | -4.8% | 81.8% | 7.1x | 95 |
| A5 2x | 3.3% | 7.3% | 0.17 | -16.3% | -11.4% | 72.7% | 14.1x | 95 |
| B4 1x | 4.5% | 14.9% | 0.22 | -29.2% | -21.0% | 54.5% | 22.6x | 23 |
| B4 2x | 3.8% | 29.7% | 0.20 | -55.1% | -40.8% | 45.5% | 45.2x | 23 |
| REF BH_ACWI | 11.4% | 17.1% | 0.58 | -33.5% | -18.4% | 81.8% | | |
| REF BH_SPY | 14.1% | 17.8% | 0.70 | -33.7% | -18.2% | 81.8% | | |
| REF 60_40_ACWI_IEF | 7.6% | 10.3% | 0.54 | -22.4% | -16.6% | 81.8% | | |

### Control cost sensitivity, CAGR / Sharpe at 0 bp, 10 bp (base), 20 bp per side
| | 0 bp | 10 bp | 20 bp |
|---|---|---|---|
| D2 | 1.4% / -0.14 | 1.2% / -0.18 | 0.9% / -0.23 |
| E2 | 7.4% / 0.41 | 7.2% / 0.39 | 7.0% / 0.38 |
| C3 | 5.9% / 0.52 | 5.8% / 0.51 | 5.7% / 0.50 |
| A5 | 3.7% / 0.38 | 3.0% / 0.19 | 2.2% / -0.00 |
| B4 | 6.9% / 0.37 | 4.5% / 0.22 | 2.1% / 0.06 |


## Reading
- Equity beta won. 2016-2026 was a strong equity decade; every rule that sits partly in cash or bonds lags on raw return, and only C3 comes close on Sharpe. ACWI (0.58), 60/40 (0.54) and SPY (0.70) all have a higher control Sharpe than every finalist (best 0.51).
- Design winners did not carry over: D2 (Sharpe 0.62 to -0.18, the bond bear market), B4 (0.36 to 0.22), A5 (0.40 to 0.19). The design window was small and a single regime. Design Sharpes of 0.4-0.6 are below or only slightly above the ~0.27 post-selection threshold plus noise (DSR 0.64-0.84 on 22 trials), so none was significant even before the control.
- Trend (A5) is hurt by costs at this size: 7x turnover and 95 trades per year; at 20 bp its Sharpe is 0. Dual momentum B4 loses most of its control return to costs (6.9% at 0 bp, 2.1% at 20 bp).
- 2x scaling of C3 raises CAGR to 8.3% (Sharpe 0.47, max DD -36%), still below ACWI's 11.4% with a similar drawdown, so it is not an improvement.
- E2 (Halloween) matches ACWI's drawdown with a lower return: not an edge over holding the index.
- Where cross-asset rules help is drawdown only: C3 and A5 cut max drawdown to -19% / -8% vs -34% for the index. For a EUR 1,000 account with a return objective that is not what the arena asks for.

## Account reality (EUR 1,000)
Trades per year (asset-level, control): E2 2, D2 3, B4 23, C3 33, A5 95. With fractional shares, a 2 pp band is EUR 20 minimum trade; A5 and C3 would be dominated by broker minimum fees unless commission-free (UCITS ETF commission-free brokers exist in the EU, but spreads on small UCITS lines are often 5-20 bp, i.e. the 10 bp assumption is not conservative for DBC/FXE/FXY/UUP equivalents, several of which have no UCITS twin).

## Broker
Kraken (the arena's only broker) cannot trade these: it lists crypto spot and crypto perpetuals (and some tokenised xStocks in certain regions), not ETFs, bond funds or FX ETFs. Implementing this would need an EU broker with fractional UCITS ETFs (Trade Republic, Scalable, Interactive Brokers); IBKR is the only one offering all asset classes and FX in one account. US-listed ETFs (SPY, TLT, GLD...) are not available to EU retail (PRIIPs), so the realistic instruments are UCITS twins (e.g. IWDA/VWCE, IBTE/IEGA, SGLD, a broad commodity UCITS), which differ from the proxies tested here.

## Caveats
Single decade of control, one equity bull regime; 2008-2015 design is 7.7 years; Yahoo adjusted closes; USD only; no taxes; cash proxy generous; 60/40 reference costless; term spread signal uses same-day close data (published daily, no lookahead beyond the t+1 execution); band rule is a design choice shared by all trials.

## Files
`fetch.py` (download), `lib.py` (engine, metrics, DSR), `strategies.py` (22 trials), `design.py`, `control.py` (run once), `make_tables.py`, `trials.jsonl`, `finalists.json`, `design_refs.json`, `control_results.json`, `tables.md` (all-trial table).
