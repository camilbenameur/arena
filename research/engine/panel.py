"""Data panel of the engine: numpy arrays aligned on a grid of UTC days.

The panel is what the engine slices into `Day` messages. It is built from `Data` (loader) or
from synthetic series (`synthetic`, used by the tests and by the C9 causality test).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from research.engine.contract import HOURS, N_COLUMNS

DAY_S = 86400
_COLS = ["open", "high", "low", "close", "volume", "taker_buy_base"]


@dataclass(frozen=True)
class Panel:
    symbols: tuple[str, ...]
    days: np.ndarray  # (T,) int64, open of the day in UTC seconds
    spot_1d: np.ndarray  # (T, N, 6)
    spot_1h: np.ndarray | None  # (T, N, 24, 6)
    perp_1h: np.ndarray | None  # (T, N, 24, 6)
    eligibles: np.ndarray  # (T, N) bool
    eligibles_perp: np.ndarray | None  # (T, N) bool
    funding_idx: tuple  # T int64 arrays: pair of each settlement of the day
    funding_rate: tuple  # T float64 arrays
    funding_ts: tuple  # T int64 arrays: fundingTime (seconds)

    @property
    def n_days(self) -> int:
        return len(self.days)

    @property
    def n_pairs(self) -> int:
        return len(self.symbols)

    def _replace(self, **kw) -> Panel:
        return replace(self, **kw)

    def swap(self, perm: np.ndarray) -> Panel:
        """Column k of the result = column `perm[k]` of the original (weights are mapped back through `inv`)."""
        perm = np.asarray(perm)
        inv = np.empty_like(perm)
        inv[perm] = np.arange(len(perm))
        fi = tuple(inv[a] if len(a) else a for a in self.funding_idx)
        return self._replace(
            symbols=tuple(self.symbols[p] for p in perm),
            spot_1d=self.spot_1d[:, perm],
            spot_1h=None if self.spot_1h is None else self.spot_1h[:, perm],
            perp_1h=None if self.perp_1h is None else self.perp_1h[:, perm],
            eligibles=self.eligibles[:, perm],
            eligibles_perp=None if self.eligibles_perp is None else self.eligibles_perp[:, perm],
            funding_idx=fi)

    def sub_universe(self, symbols: list[str] | tuple[str, ...]) -> Panel:
        pos = {s: k for k, s in enumerate(self.symbols)}
        cols = np.array([pos[s] for s in symbols])
        fresh = np.full(self.n_pairs, -1, dtype=np.int64)
        fresh[cols] = np.arange(len(cols))
        fi, ft, fs = [], [], []
        for a, b, c in zip(self.funding_idx, self.funding_rate, self.funding_ts, strict=True):
            guard = fresh[a] >= 0 if len(a) else np.zeros(0, dtype=bool)
            fi.append(fresh[a][guard])
            ft.append(b[guard])
            fs.append(c[guard])
        # days with no listed pair at the start: removed (the stream starts at the first listing)
        first_listed = int(np.argmax(self.eligibles[:, cols].any(axis=1)))
        sl = slice(first_listed, None)
        return Panel(
            symbols=tuple(symbols), days=self.days[sl], spot_1d=self.spot_1d[sl][:, cols],
            spot_1h=None if self.spot_1h is None else self.spot_1h[sl][:, cols],
            perp_1h=None if self.perp_1h is None else self.perp_1h[sl][:, cols],
            eligibles=self.eligibles[sl][:, cols],
            eligibles_perp=None if self.eligibles_perp is None else self.eligibles_perp[sl][:, cols],
            funding_idx=tuple(fi[sl]), funding_rate=tuple(ft[sl]), funding_ts=tuple(fs[sl]))

    def truncate(self, n_days: int) -> Panel:
        sl = slice(0, n_days)
        return self._replace(
            days=self.days[sl], spot_1d=self.spot_1d[sl],
            spot_1h=None if self.spot_1h is None else self.spot_1h[sl],
            perp_1h=None if self.perp_1h is None else self.perp_1h[sl],
            eligibles=self.eligibles[sl],
            eligibles_perp=None if self.eligibles_perp is None else self.eligibles_perp[sl],
            funding_idx=self.funding_idx[sl], funding_rate=self.funding_rate[sl],
            funding_ts=self.funding_ts[sl])

    def trim_start(self, k: int) -> Panel:
        """Panel without its first `k` days (warm-up removed from the stream sent to the strategy)."""
        if k <= 0:
            return self
        sl = slice(k, None)
        return self._replace(
            days=self.days[sl], spot_1d=self.spot_1d[sl],
            spot_1h=None if self.spot_1h is None else self.spot_1h[sl],
            perp_1h=None if self.perp_1h is None else self.perp_1h[sl],
            eligibles=self.eligibles[sl],
            eligibles_perp=None if self.eligibles_perp is None else self.eligibles_perp[sl],
            funding_idx=self.funding_idx[sl], funding_rate=self.funding_rate[sl],
            funding_ts=self.funding_ts[sl])

    def rescale(self, factors: np.ndarray) -> Panel:
        """Prices x factor (per pair), volumes and taker buys / factor (same traded value)."""
        f = np.asarray(factors, dtype=np.float64)

        def scale_array(a):
            if a is None:
                return None
            fp = f.reshape((1, len(f)) + (1,) * (a.ndim - 3))[..., None]
            b = a.copy()
            b[..., 0:4] = a[..., 0:4] * fp
            b[..., 4:6] = a[..., 4:6] / fp
            return b

        return self._replace(spot_1d=scale_array(self.spot_1d), spot_1h=scale_array(self.spot_1h),
                               perp_1h=scale_array(self.perp_1h))

    def corrupt_after(self, cutoff: int, rng: np.random.Generator) -> Panel:
        """Replaces with noise any data whose `known_at` > `cutoff` (UTC seconds)."""
        T, N = self.n_days, self.n_pairs
        h_end = self.days[:, None] + (np.arange(HOURS)[None, :] + 1) * 3600  # (T, 24)
        noise_h = np.broadcast_to((h_end > cutoff)[:, None, :], (T, N, HOURS))
        d_end = self.days + DAY_S
        noise_d = d_end > cutoff  # (T,)
        noise_dn = np.broadcast_to(noise_d[:, None], (T, N))

        def noise(shape):
            b = np.exp(rng.normal(0.0, 1.0, shape))
            return b

        s1d = self.spot_1d.copy()
        s1d[noise_dn] = noise(s1d[noise_dn].shape) * 100.0
        s1h = None
        if self.spot_1h is not None:
            s1h = self.spot_1h.copy()
            s1h[noise_h] = noise(s1h[noise_h].shape) * 100.0
        p1h = None
        if self.perp_1h is not None:
            p1h = self.perp_1h.copy()
            p1h[noise_h] = noise(p1h[noise_h].shape) * 100.0
        elig = self.eligibles.copy()
        elig[noise_dn] = rng.random(elig[noise_dn].shape) < 0.5
        elp = None
        if self.eligibles_perp is not None:
            elp = self.eligibles_perp.copy()
            elp[noise_dn] = rng.random(elp[noise_dn].shape) < 0.5
        ft = tuple(np.where(s + 1 > cutoff, rng.normal(0, 1e-3, len(s)), t)
                   for t, s in zip(self.funding_rate, self.funding_ts, strict=True))
        return self._replace(spot_1d=s1d, spot_1h=s1h, perp_1h=p1h, eligibles=elig,
                               eligibles_perp=elp, funding_rate=ft)

    def rebase(self, volume_days: int = 30) -> Panel:
        """Panel as the STRATEGY sees it (the engine itself computes returns on the real prices).

        - prices (o,h,l,c, spot and perp) divided, per pair, by the pair's first valid spot close:
          the absolute level no longer identifies either the pair or the date;
        - volumes (and taker buys) divided, per pair, by the running mean volume of the first `volume_days`
          listed days: from day `volume_days` on the divisor is fixed, before that it equals the
          mean of the volumes of the listed days known up to and including the current day (close). Causal: the
          divisor of day t depends only on data from days <= t.
        Zeros (unlisted pair) stay zeros. The first valid close is that of the listing day,
        hence known as soon as the pair exists."""
        T, N = self.n_days, self.n_pairs
        close = self.spot_1d[:, :, 3]
        valid = self.eligibles & (close > 0)
        level = np.ones(N)
        vscale = np.ones((T, N))
        for k in range(N):
            idx = np.flatnonzero(valid[:, k])
            if len(idx) == 0:
                continue
            level[k] = close[idx[0], k]
            avg = np.cumsum(self.spot_1d[idx, k, 4]) / np.arange(1, len(idx) + 1)
            if len(avg) >= volume_days:
                avg[volume_days - 1:] = avg[volume_days - 1]
            avg = np.where(np.isfinite(avg) & (avg > 0), avg, 1.0)
            vscale[idx, k] = avg

        def reb(a):
            if a is None:
                return None
            b = a.copy()
            extra = (1,) * (a.ndim - 3)
            b[..., 0:4] = a[..., 0:4] / level.reshape((1, N) + extra)[..., None]
            b[..., 4:6] = a[..., 4:6] / vscale.reshape((T, N) + extra)[..., None]
            return b

        return self._replace(spot_1d=reb(self.spot_1d), spot_1h=reb(self.spot_1h), perp_1h=reb(self.perp_1h))

    def day(self, i: int):
        """`Day` message of day i."""
        from research.engine.contract import Day

        idx, rates, ts = self.funding_idx[i], self.funding_rate[i], self.funding_ts[i]
        # Order of the settlements: (PERMUTED column index, timestamp). The original order (by pair of the universe
        # file, then by settlement) would reveal the permutation: the list sent to the strategy is
        # sorted by stream column, hence independent of the pairs' identity.
        order = np.lexsort((ts, idx)) if len(idx) else np.zeros(0, dtype=np.int64)
        idx, rates = idx[order], rates[order]
        return Day(
            i=i, spot_1d=self.spot_1d[i],
            spot_1h=None if self.spot_1h is None else self.spot_1h[i],
            perp_1h=None if self.perp_1h is None else self.perp_1h[i],
            funding=[(int(a), float(b)) for a, b in zip(idx, rates, strict=True)],
            eligibles=self.eligibles[i],
            eligibles_perp=None if self.eligibles_perp is None else self.eligibles_perp[i])

    # --- derived series used by the portfolio -------------------------------------------
    def spot_returns(self) -> np.ndarray:
        """(T, N): return of day t (close t-1 -> close t); 0 if either close is missing."""
        return _returns(self.spot_1d[:, :, 3])

    def perp_returns(self) -> np.ndarray:
        if self.perp_1h is None:
            return np.zeros((self.n_days, self.n_pairs))
        return _returns(self.perp_1h[:, :, HOURS - 1, 3])

    def funding_per_day(self) -> np.ndarray:
        """(T, N): sum of the funding rates of the settlements falling in each day."""
        out = np.zeros((self.n_days, self.n_pairs))
        for i, (a, b) in enumerate(zip(self.funding_idx, self.funding_rate, strict=True)):
            if len(a):
                np.add.at(out[i], a, b)
        return out


def _returns(close: np.ndarray) -> np.ndarray:
    r = np.zeros_like(close)
    prev, cur = close[:-1], close[1:]
    ok = (prev > 0) & (cur > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        r[1:] = np.where(ok, cur / np.where(prev > 0, prev, 1.0) - 1.0, 0.0)
    return r


# ----------------------------------------------------------------------------------------------------
# Construction from `Data`
# ----------------------------------------------------------------------------------------------------


def _seconds(idx: pd.DatetimeIndex) -> np.ndarray:
    return idx.as_unit("ns").asi8 // 1_000_000_000


def panel_from_tables(
    symbols: list[str], spot_1d: dict[str, pd.DataFrame], spot_1h: dict[str, pd.DataFrame] | None = None,
    perp_1h: dict[str, pd.DataFrame | None] | None = None,
    funding: dict[str, pd.DataFrame | None] | None = None,
) -> Panel:
    """Aligns per-symbol tables (loader format) on a common grid of days."""
    d0 = min(int(_seconds(spot_1d[s].index)[0]) for s in symbols)
    d1 = max(int(_seconds(spot_1d[s].index)[-1]) for s in symbols)
    d0 -= d0 % DAY_S
    days = np.arange(d0, d1 + 1, DAY_S, dtype=np.int64)
    T, N = len(days), len(symbols)
    s1d = np.zeros((T, N, N_COLUMNS))
    elig = np.zeros((T, N), dtype=bool)
    for k, s in enumerate(symbols):
        df = spot_1d[s]
        pos = (_seconds(df.index) - d0) // DAY_S
        s1d[pos, k] = df[_COLS].to_numpy()
        elig[pos, k] = True
    s1h = None
    if spot_1h is not None:
        s1h = np.zeros((T, N, HOURS, N_COLUMNS))
        for k, s in enumerate(symbols):
            df = spot_1h[s]
            sec = _seconds(df.index) - d0
            ok = (sec >= 0) & (sec // DAY_S < T)  # a 1 h bar outside the 1 d grid would be filed under the wrong day
            sec = sec[ok]
            s1h[sec // DAY_S, k, (sec % DAY_S) // 3600] = df[_COLS].to_numpy()[ok]
    p1h, elp = None, None
    fi = [[] for _ in range(T)]
    ft = [[] for _ in range(T)]
    fs = [[] for _ in range(T)]
    if perp_1h is not None and any(perp_1h.get(s) is not None for s in symbols):
        p1h = np.zeros((T, N, HOURS, N_COLUMNS))
        elp = np.zeros((T, N), dtype=bool)
        for k, s in enumerate(symbols):
            df = perp_1h.get(s)
            if df is None:
                continue
            sec = _seconds(df.index) - d0
            ok = (sec >= 0) & (sec // DAY_S < T)
            sec = sec[ok]
            p1h[sec // DAY_S, k, (sec % DAY_S) // 3600] = df[_COLS].to_numpy()[ok]
            elp[sec // DAY_S, k] = True
            fdf = (funding or {}).get(s)
            if fdf is not None:
                fsec = _seconds(fdf.index)
                for t, x in zip(fsec, fdf["rate"].to_numpy(), strict=True):
                    j = (int(t) - d0) // DAY_S
                    if 0 <= j < T:
                        fi[j].append(k)
                        ft[j].append(float(x))
                        fs[j].append(int(t))
    return Panel(
        symbols=tuple(symbols), days=days, spot_1d=s1d, spot_1h=s1h, perp_1h=p1h, eligibles=elig,
        eligibles_perp=elp,
        funding_idx=tuple(np.array(a, dtype=np.int64) for a in fi),
        funding_rate=tuple(np.array(a, dtype=np.float64) for a in ft),
        funding_ts=tuple(np.array(a, dtype=np.int64) for a in fs))


def panel_from_data(data, universe: str = "main", *, with_1h: bool = True,
                           with_perp: bool = True, arena_symbols: tuple[str, ...] | None = None) -> Panel:
    """`universe`: "main" (the 15 pairs), "arena" (`arena_symbols`, otherwise the 6 of the criteria via
    the caller) or "control:<SYM>" (a control symbol: 1 d, 1 h, perp bars and funding from the loader
    when they exist)."""
    if universe.startswith("control:"):
        sym = universe.split(":", 1)[1]
        h1 = getattr(data, "control_1h", None) or {}
        pp = getattr(data, "control_perp_1h", None) or {}
        fd = getattr(data, "control_funding", None) or {}
        # same tables, same columns and same `known_at` as the main universe; None if absent.
        return panel_from_tables(
            [sym], {sym: data.control_1d[sym]},
            {sym: h1[sym]} if with_1h and h1.get(sym) is not None else None,
            {sym: pp[sym]} if with_perp and pp.get(sym) is not None else None,
            {sym: fd.get(sym)} if with_perp and pp.get(sym) is not None else None)
    syms = list(data.universe)
    panel = panel_from_tables(
        syms, data.spot_1d, data.spot_1h if with_1h else None,
        data.perp_1h if with_perp else None, data.funding if with_perp else None)
    if universe == "main":
        return panel
    if universe == "arena":
        if arena_symbols is None:
            raise ValueError("universe 'arena': provide arena_symbols (criteria.arena_universe)")
        return panel.sub_universe(list(arena_symbols))
    raise ValueError(f"unknown universe: {universe!r}")


# ----------------------------------------------------------------------------------------------------
# Synthetic data
# ----------------------------------------------------------------------------------------------------


def synthetic(
    n_days: int = 400, n_pairs: int = 15, seed: int = 0, *, with_1h: bool = True, with_perp: bool = False,
    day_start: int = 1_514_764_800, late_quotes: bool = True, sigma_h: float = 0.004,
    regimes: bool = False,
) -> Panel:
    """Coherent synthetic panel (1 d bar = aggregate of its 24 1 h bars). No real data.
    `regimes=True`: varied market regimes (trends, crashes, sustained high positive or negative funding,
    negative basis); see `varied_synthetic`."""
    rng = np.random.default_rng(seed)
    T, N, H = n_days, n_pairs, HOURS
    day_start -= day_start % DAY_S
    days = day_start + DAY_S * np.arange(T, dtype=np.int64)
    common = rng.normal(0.0, sigma_h * 0.6, (T * H, 1))
    if regimes:
        state = _market_states(rng, T)
        mu_j = np.array([0.0002, 0.0012, -0.0010, -0.02])[state]
        vol_j = np.array([1.0, 1.2, 1.6, 3.0])[state]
        beta = rng.uniform(0.6, 1.4, N)
        mu_h = np.repeat(mu_j / H, H)[:, None] * beta[None, :]
        vol_h = np.repeat(vol_j, H)[:, None]
        ret = mu_h + (rng.normal(0.0, sigma_h, (T * H, N)) + common) * vol_h
    else:
        ret = rng.normal(0.0002, sigma_h, (T * H, N)) + common
    level0 = np.exp(rng.uniform(-1.0, 9.0, N))
    close = level0 * np.exp(np.cumsum(ret, axis=0))
    open_ = np.vstack([level0[None, :], close[:-1]])
    amp = np.abs(rng.normal(0.0, sigma_h * 0.5, (T * H, N)))
    high = np.maximum(open_, close) * (1.0 + amp)
    low = np.minimum(open_, close) * (1.0 - amp)
    vol = np.exp(rng.normal(8.0, 0.6, (T * H, N)))
    part = np.clip(0.5 + 0.08 * np.tanh(ret / sigma_h) + rng.normal(0.0, 0.05, (T * H, N)), 0.05, 0.95)
    taker = vol * part
    bars = np.stack([open_, high, low, close, vol, taker], axis=-1).reshape(T, H, N, 6).transpose(0, 2, 1, 3)
    bars = np.ascontiguousarray(bars)  # (T, N, 24, 6)
    s1d = np.empty((T, N, 6))
    s1d[..., 0] = bars[:, :, 0, 0]
    s1d[..., 1] = bars[..., 1].max(axis=2)
    s1d[..., 2] = bars[..., 2].min(axis=2)
    s1d[..., 3] = bars[:, :, -1, 3]
    s1d[..., 4] = bars[..., 4].sum(axis=2)
    s1d[..., 5] = bars[..., 5].sum(axis=2)
    elig = np.ones((T, N), dtype=bool)
    if late_quotes and N > 2:
        for k in range(N // 3, N):
            first = int(rng.integers(1, max(2, T // 3)))
            elig[:first, k] = False
    s1d[~elig] = 0.0
    bars[~elig] = 0.0
    s1h = bars if with_1h else None
    p1h = elp = None
    fi, ft, fs = [], [], []
    if with_perp:
        if regimes:
            ann, base = _funding_and_base(rng, T, N, H, state)
        else:
            base = rng.normal(0.0, 0.0005, (T * H, N))
        pm = np.stack([x * (1.0 + base) for x in (open_, high, low, close)], axis=-1)
        pv = np.stack([vol * 3.0, taker * 3.0], axis=-1)
        pb = np.concatenate([pm, pv], axis=-1).reshape(T, H, N, 6).transpose(0, 2, 1, 3)
        p1h = np.ascontiguousarray(pb)
        elp = elig.copy()
        elp[: max(1, T // 10)] = False
        p1h[~elp] = 0.0
        if regimes:
            rate = ann[:, None, :] / 1095.0 + rng.normal(0.0, 0.00003, (T, 3, N))
        else:
            rate = rng.normal(0.00005, 0.00015, (T, 3, N))
        for i in range(T):
            ok = np.flatnonzero(elp[i])
            idx = np.tile(ok, 3).astype(np.int64)
            rates = rate[i][:, ok].reshape(-1)
            ts = np.repeat(days[i] + np.array([0, 8, 16]) * 3600, len(ok)).astype(np.int64)
            fi.append(idx)
            ft.append(rates)
            fs.append(ts)
    else:
        z = np.zeros(0)
        fi = [z.astype(np.int64)] * T
        ft = [z] * T
        fs = [z.astype(np.int64)] * T
    return Panel(
        symbols=tuple(f"S{k:02d}" for k in range(N)), days=days, spot_1d=s1d, spot_1h=s1h, perp_1h=p1h,
        eligibles=elig, eligibles_perp=elp, funding_idx=tuple(fi), funding_rate=tuple(ft),
        funding_ts=tuple(fs))


def _market_states(rng: np.random.Generator, T: int) -> np.ndarray:
    """(T,) market states in blocks: 0 calm, 1 uptrend, 2 downtrend, 3 crash (2 to 8 days)."""
    state = np.zeros(T, dtype=np.int64)
    t = 0
    while t < T:
        e = int(rng.choice(4, p=[0.35, 0.30, 0.25, 0.10]))
        duration = int(rng.integers(2, 9)) if e == 3 else int(rng.integers(20, 121))
        state[t:t + duration] = e
        t += duration
    return state


def _funding_and_base(rng: np.random.Generator, T: int, N: int, H: int, state: np.ndarray):
    """(annualized funding (T, N), perp/spot basis per hour (T*H, N)): funding levels in blocks of 40 to 250
    days (negative, zero, moderate, high, extreme), partly common to the market; mean-reverting basis tied
    to funding, negative in a crash and in a downtrend."""
    levels = np.array([-0.15, -0.05, 0.0, 0.12, 0.25, 0.5, 1.0, 1.4])
    ann = np.empty((T, N))
    for k in range(N):
        t = 0
        while t < T:
            duration = int(rng.integers(40, 251))
            ann[t:t + duration, k] = rng.choice(levels)
            t += duration
    market = np.array([0.0, 0.3, -0.12, -0.25])[state]
    ann = 0.6 * ann + 0.4 * rng.choice(levels[3:], size=1) * (state[:, None] == 1) + market[:, None]
    target = 0.006 * ann - np.where(state == 3, 0.02, 0.0)[:, None] - np.where(state == 2, 0.004, 0.0)[:, None]
    b = np.zeros((T, N))
    cur = target[0].copy()
    noise = rng.normal(0.0, 0.0015, (T, N))
    for i in range(T):
        cur = 0.9 * cur + 0.1 * target[i] + noise[i]
        b[i] = cur
    base_h = np.repeat(b, H, axis=0) + rng.normal(0.0, 0.0003, (T * H, N))
    return ann, base_h


def varied_synthetic(n_days: int = 1300, n_pairs: int = 15, seed: int | None = None, **kw) -> Panel:
    """Synthetic panel with varied regimes for the C9 causality check (>= 1,300 days: strategies with
    a long history, e.g. 365 days of funding, produce non-trivial weights).
    `seed=None`: seed drawn from `os.urandom` on each call."""
    import os

    if seed is None:
        seed = int.from_bytes(os.urandom(8), "big")
    kw.setdefault("with_perp", True)
    return synthetic(n_days, n_pairs, seed, regimes=True, **kw)
