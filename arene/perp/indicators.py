"""Technical indicators for the agents' `indicators` tool, in integers (no float, reproducible).

Definitions follow TA-Lib's (BSD) conventions: EMA seeded with the SMA of its first `n` values; RSI and ATR
with Wilder's smoothing seeded with a simple average. Prices are µUSD; RSI is returned in bp (0-10000);
volatility in bp of the close. Every function returns None when there is not enough data.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import isqrt

BP = 10_000


def sma(values: Sequence[int], n: int) -> int | None:
    if n <= 0 or len(values) < n:
        return None
    return sum(values[-n:]) // n


def ema(values: Sequence[int], n: int) -> int | None:
    """EMA with alpha = 2 / (n + 1), seeded with the SMA of the first n values (integer, floored)."""
    if n <= 0 or len(values) < n:
        return None
    e = sum(values[:n]) // n
    for v in values[n:]:
        e = e + (2 * (v - e)) // (n + 1)
    return e


def rsi_bp(closes: Sequence[int], n: int = 14) -> int | None:
    """Wilder's RSI in bp (0-10000)."""
    if n <= 0 or len(closes) < n + 1:
        return None
    gains = [max(0, closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    losses = [max(0, closes[i - 1] - closes[i]) for i in range(1, len(closes))]
    # Wilder smoothing, scaled by n to stay in integers: avg_n = sum / n, then avg = (avg*(n-1) + x) / n
    g = sum(gains[:n]) * BP  # scaled by BP for precision
    lo = sum(losses[:n]) * BP
    g //= n
    lo //= n
    for x, y in zip(gains[n:], losses[n:], strict=True):
        g = (g * (n - 1) + x * BP) // n
        lo = (lo * (n - 1) + y * BP) // n
    if g + lo == 0:
        return BP // 2
    return g * BP // (g + lo)


def atr(highs: Sequence[int], lows: Sequence[int], closes: Sequence[int], n: int = 14) -> int | None:
    """Wilder's average true range, in the prices' unit."""
    if n <= 0 or not len(highs) == len(lows) == len(closes) or len(closes) < n + 1:
        return None
    trs = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(1, len(closes))
    ]
    a = sum(trs[:n]) // n
    for tr in trs[n:]:
        a = (a * (n - 1) + tr) // n
    return a


def realized_vol_bp(closes: Sequence[int], n: int = 20) -> int | None:
    """Standard deviation of the last n close-to-close returns, in bp (population, integer sqrt)."""
    if n < 2 or len(closes) < n + 1:
        return None
    rets = [(closes[i] - closes[i - 1]) * BP // closes[i - 1] for i in range(len(closes) - n, len(closes))]
    mean_num = sum(rets)
    var_num = sum(r * r for r in rets) * n - mean_num * mean_num  # n^2 * variance
    return isqrt(max(var_num, 0) // (n * n))


def bollinger(closes: Sequence[int], n: int = 20, k: int = 2) -> tuple[int, int, int] | None:
    """(lower, middle, upper): SMA +/- k population standard deviations, integers."""
    if n < 2 or len(closes) < n:
        return None
    w = closes[-n:]
    mid = sum(w) // n
    var = sum((x - mid) ** 2 for x in w) // n
    sd = isqrt(var)
    return mid - k * sd, mid, mid + k * sd


def summary(candles: Sequence[tuple[int, int, int, int]]) -> dict[str, int | None]:
    """The `indicators` tool's payload for one interval: candles = [(open, high, low, close)] oldest first."""
    closes = [c[3] for c in candles]
    highs = [c[1] for c in candles]
    lows = [c[2] for c in candles]
    bb = bollinger(closes)
    ema12, ema26 = ema(closes, 12), ema(closes, 26)
    return {
        "last_close_uusd": closes[-1] if closes else None,
        "sma_20_uusd": sma(closes, 20),
        "ema_20_uusd": ema(closes, 20),
        "ema_50_uusd": ema(closes, 50),
        "macd_uusd": (ema12 - ema26) if ema12 is not None and ema26 is not None else None,
        "rsi_14_bp": rsi_bp(closes, 14),
        "atr_14_uusd": atr(highs, lows, closes, 14),
        "realized_vol_20_bp": realized_vol_bp(closes, 20),
        "bollinger_lower_uusd": bb[0] if bb else None,
        "bollinger_upper_uusd": bb[2] if bb else None,
    }
