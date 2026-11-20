"""Stream contract between the engine and a strategy (protocol §3).

This module is copied as is into the sandbox: it depends only on the standard library and numpy.

A `strategy.py` file defines:

    class Strategy:
        def __init__(self, n_pairs: int, **params): ...
        def step(self, day: Day) -> tuple[ndarray, ndarray]: ...   # (spot_weights, perp_weights), each (n_pairs,)

`step` is called once per day, in order, with the data known at the 00:00 UTC close that ends that day
(complete daily bar, its 24 hourly bars, the day's funding settlements).
The strategy receives neither a date nor a pair name: the column order is permuted on every trial.
`perp_weights[j]` is a short notional as a fraction of capital (>= 0).
Prices and volumes received are rebased and `Day.i` is shifted by a random integer: see `Day`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Columns of `spot_1d` and of the 1 h bars: open, high, low, close, volume (base), taker_buy_base.
COL_O, COL_H, COL_L, COL_C, COL_V, COL_TB = range(6)
N_COLUMNS = 6
HOURS = 24

#: Closed codes returned to agents (criteria.yaml: execution.return_codes).
OK = "OK"
CAUSALITY = "CAUSALITY"
TIMEOUT = "TIMEOUT"
SOURCE_REFUSED = "SOURCE_REFUSED"
WEIGHT_SHAPE = "WEIGHT_SHAPE"
ERROR = "ERROR"
CODES = (OK, CAUSALITY, TIMEOUT, SOURCE_REFUSED, WEIGHT_SHAPE, ERROR)

#: Comparison tolerance for the weight bounds (never used to clip).
WEIGHT_TOL = 1e-9


class TrialError(Exception):
    """Failure of a trial with a closed code; `detail` only goes to the technical journal, never to an agent."""

    code = ERROR

    def __init__(self, detail: str = ""):
        super().__init__(detail)
        self.detail = detail


class SourceRefused(TrialError):
    code = SOURCE_REFUSED


class WeightShape(TrialError):
    code = WEIGHT_SHAPE


class DelayExceeded(TrialError):
    code = TIMEOUT


class Causality(TrialError):
    code = CAUSALITY


@dataclass(frozen=True, slots=True)
class Day:
    """Message of the day. `i` = random integer offset (>= 10,000, drawn per trial) + rank of the day in the stream.
    Prices and volumes are REBASED per pair (`Panel.rebase`): price / the pair's first close, volume /
    mean volume of the first 30 listed days. The first k days of the warm-up (k drawn per trial in
    [0, 365), `os.urandom`, identical for the main run and its replays) are not sent: the day rank
    therefore does not give the date by counting days from the (public) start of the data.

    What can still honestly be deduced about a date: `eligibles` / `eligibles_perp` (the listing dates of the
    15 pairs are public: e.g. the perpetuals of 9 pairs appear on the same day, 2022-04-03, and the
    price/tick grid of each pair survives rebasing); a relative day rank between two listings
    (exact gap in days between two events of the stream); seasonality internal to the data (day of week
    through volume, funding settlements). The stream does not hide the epoch from a strategy that recognizes
    these events: it only prevents reading the date from `i`."""

    i: int
    spot_1d: np.ndarray  # (n_pairs, 6) o,h,l,c,v,taker_buy_base; zeros while the pair is not listed
    spot_1h: np.ndarray | None  # (n_pairs, 24, 6)
    perp_1h: np.ndarray | None  # (n_pairs, 24, 6)
    funding: list  # [(pair_idx, rate)] of the settlements whose known_at <= close of the day
    eligibles: np.ndarray  # (n_pairs,) bool: the pair is listed (spot) that day
    eligibles_perp: np.ndarray | None  # (n_pairs,) bool: the perpetual exists that day


DAY_FIELDS = ("i", "spot_1d", "spot_1h", "perp_1h", "funding", "eligibles", "eligibles_perp")
