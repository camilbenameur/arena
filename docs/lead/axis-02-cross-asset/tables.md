ALL TRIALS (design)
| id | family | rule | CAGR | vol | Sharpe | maxDD | turnover/yr | trades/yr | DSR prob |
|---|---|---|---|---|---|---|---|---|---|
| A1 | trend | TSMOM 12m sign, 1/N per asset, rest cash | 2.0% | 6.0% | 0.33 | -8.7% | 6.1x | 67 | 0.57 |
| A2 | trend | price > 10-month SMA (210d), 1/N per asset, rest cash (Faber GTAA) | 1.9% | 5.6% | 0.34 | -8.3% | 8.2x | 91 | 0.58 |
| A3 | trend | TSMOM 12m sign, inverse-vol weights normalised to 100% invested | 1.8% | 7.5% | 0.26 | -11.0% | 14.8x | 233 | 0.49 |
| A4 | trend | 10m SMA, inverse-vol weights normalised to 100% invested | 1.4% | 7.6% | 0.19 | -17.1% | 23.0x | 285 | 0.42 |
| A5 | trend | TSMOM 12m, each asset sized to 10% vol / N (MOP), gross <= 1x | 1.5% | 3.6% | 0.40 | -3.9% | 5.5x | 86 | 0.64 |
| A6 | trend | 1/3/6/12m sign ensemble, 10% vol per asset / N, gross <= 1x | 1.0% | 2.9% | 0.31 | -4.2% | 7.7x | 269 | 0.55 |
| A7 | trend | A4 + BTC in the universe | 1.6% | 7.6% | 0.22 | -15.7% | 22.9x | 286 | 0.45 |
| A8 | trend | 1/3/6/12m ensemble, inverse-vol normalised | 1.5% | 6.6% | 0.23 | -11.0% | 22.7x | 554 | 0.46 |
| B1 | xsmom | cross-sectional 12-1m momentum, top 3 of 11, 1/3 each, no absolute filter | 2.1% | 13.8% | 0.21 | -36.3% | 27.9x | 84 | 0.44 |
| B2 | dual | dual momentum: top 3 of 11 by 12-1m, only if 12-1m > 0, else cash | 2.1% | 13.8% | 0.21 | -36.3% | 27.9x | 84 | 0.44 |
| B3 | dual | dual momentum: top 4 of 11, absolute filter | 3.4% | 12.6% | 0.32 | -20.4% | 23.0x | 92 | 0.55 |
| B4 | dual | GEM-like: best of SPY/EFA if 12m>0 else IEF | 4.5% | 15.3% | 0.36 | -20.5% | 16.0x | 16 | 0.60 |
| B5 | dual | B2 + BTC in the universe | 3.0% | 13.9% | 0.27 | -36.3% | 28.3x | 85 | 0.50 |
| C1 | riskparity | inverse 60d-vol across 11 ETFs, 100% invested | 2.1% | 6.0% | 0.35 | -12.7% | 0.6x | 26 | 0.59 |
| C2 | riskparity | C1 scaled to 10% portfolio vol, gross <= 1x | 2.0% | 5.9% | 0.34 | -12.7% | 0.6x | 26 | 0.58 |
| C3 | riskparity | inverse-vol on core 5 (SPY,TLT,IEF,GLD,DBC), 100% invested | 4.0% | 7.1% | 0.57 | -11.0% | 0.7x | 32 | 0.80 |
| C4 | riskparity | C1 + BTC | 2.2% | 6.0% | 0.37 | -12.7% | 0.6x | 25 | 0.61 |
| D1 | carry | TLT when 10y-3m term spread > 1 pt, else cash | 6.5% | 16.0% | 0.47 | -26.6% | 0.0x | 0 | 0.71 |
| D2 | carry | IEF when term spread > 0, else cash | 4.6% | 7.4% | 0.62 | -10.4% | 0.0x | 0 | 0.84 |
| D3 | carry | TLT when spread > 1 pt, else IEF (always bonds) | 6.5% | 16.0% | 0.47 | -26.6% | 0.0x | 0 | 0.71 |
| E1 | seasonal | SPY on last + first 3 trading days of the month, else cash | 0.5% | 9.0% | 0.09 | -16.3% | 23.9x | 24 | 0.31 |
| E2 | seasonal | SPY Nov-Apr (Halloween), else cash | 8.2% | 14.4% | 0.61 | -31.6% | 2.2x | 2 | 0.83 |

DESIGN
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

CONTROL
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

COST SENSITIVITY control Sharpe/CAGR (0 / 10 / 20 bp)
| D2 | 1.4% / -0.14 | 1.2% / -0.18 | 0.9% / -0.23 |
| E2 | 7.4% / 0.41 | 7.2% / 0.39 | 7.0% / 0.38 |
| C3 | 5.9% / 0.52 | 5.8% / 0.51 | 5.7% / 0.50 |
| A5 | 3.7% / 0.38 | 3.0% / 0.19 | 2.2% / -0.00 |
| B4 | 6.9% / 0.37 | 4.5% / 0.22 | 2.1% / 0.06 |

SR threshold after selection 0.2674850583117059
