import numpy as np
import pandas as pd

TICKERS = ["BTC", "ETH", "SOL", "XRP", "LTC", "LINK"]
N_ENTRY = 60   # 10 days of 4-hour bars: breakout channel
N_EXIT = 30    # 5 days of 4-hour bars: exit channel
SIZE = 1.0     # weight units (equity/6 per contract) -> gross exposure never above 1x equity


def _wide(df, col):
    w = df.pivot(index="ts", columns="ticker", values=col).sort_index()
    return w.reindex(columns=TICKERS)


def targets(df):
    """Slow Donchian channel breakout, long/short, per contract.

    Long when the bar closes above the highest high of the previous N_ENTRY bars, short when it closes below the
    lowest low of the previous N_ENTRY bars; a long is closed when the close falls below the lowest low of the
    previous N_EXIT bars, a short when it rises above the highest high of the previous N_EXIT bars.
    Only bars with ts <= t are used for row t (rolling windows shifted by one bar, forward state machine).
    """
    close, high, low = _wide(df, "close"), _wide(df, "high"), _wide(df, "low")
    hi_in = high.rolling(N_ENTRY, min_periods=N_ENTRY).max().shift(1)
    lo_in = low.rolling(N_ENTRY, min_periods=N_ENTRY).min().shift(1)
    hi_out = high.rolling(N_EXIT, min_periods=N_EXIT).max().shift(1)
    lo_out = low.rolling(N_EXIT, min_periods=N_EXIT).min().shift(1)
    out = pd.DataFrame(0.0, index=close.index, columns=TICKERS)
    for k in TICKERS:
        c = close[k].to_numpy(float)
        a, b = hi_in[k].to_numpy(float), lo_in[k].to_numpy(float)
        x, y = hi_out[k].to_numpy(float), lo_out[k].to_numpy(float)
        pos, col = 0.0, np.zeros(len(c))
        for t in range(len(c)):
            if not (np.isnan(a[t]) or np.isnan(b[t]) or np.isnan(c[t])):
                if pos > 0 and c[t] < y[t]:
                    pos = 0.0
                if pos < 0 and c[t] > x[t]:
                    pos = 0.0
                if c[t] > a[t]:
                    pos = SIZE
                elif c[t] < b[t]:
                    pos = -SIZE
            col[t] = pos
        out[k] = col
    out.index.name = "ts"
    return out.fillna(0.0).clip(-2.0, 2.0)
