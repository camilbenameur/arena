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
