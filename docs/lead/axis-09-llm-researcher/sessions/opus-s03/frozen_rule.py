"""Frozen rule: slow Donchian channel breakout, per contract, long/short, fixed size.
Enter long (+1) when the 4h close exceeds the highest high of the previous 120 bars (20 days);
enter short (-1) when it falls below the lowest low of the previous 120 bars. Exit a long when the
close falls below the lowest low of the previous 60 bars (10 days); exit a short when it rises above
the highest high of the previous 60 bars. Otherwise hold. Causal: only bars <= t are used.
Label: NO ROBUST EDGE FOUND -- this is the most defensible simple rule, not a validated edge."""
import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
ENTRY = 120  # bars (20 days), classic Turtle 20-day breakout
EXIT = 60    # bars (10 days), classic 10-day exit
SIZE = 1.0   # equity/6 per contract


def _wide(df, col):
    w = df.pivot_table(index="ts", columns="ticker", values=col, aggfunc="last")
    return w.reindex(columns=TICKERS).sort_index()


def targets(df):
    close, high, low = _wide(df, "close"), _wide(df, "high"), _wide(df, "low")
    hi_in = high.rolling(ENTRY).max().shift(1)
    lo_in = low.rolling(ENTRY).min().shift(1)
    hi_out = high.rolling(EXIT).max().shift(1)
    lo_out = low.rolling(EXIT).min().shift(1)
    out = pd.DataFrame(0.0, index=close.index, columns=TICKERS)
    for t in TICKERS:
        c, a, b, x, y = (s[t].to_numpy(float) for s in (close, hi_in, lo_in, hi_out, lo_out))
        p = 0.0
        res = np.zeros(len(c))
        for i in range(len(c)):
            if p == 0.0:
                if c[i] > a[i]:
                    p = SIZE
                elif c[i] < b[i]:
                    p = -SIZE
            elif p > 0 and c[i] < y[i]:
                p = 0.0
            elif p < 0 and c[i] > x[i]:
                p = 0.0
            res[i] = p
        out[t] = res
    out = out.fillna(0.0).clip(-2.0, 2.0)
    out.index.name = "ts"
    return out
