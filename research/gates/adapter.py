"""Engine -> gates adapter: the engine `TrialResult` to the gates `Trial` and `CausalityReport`.

No performance computation here: the engine series are cut to the evaluation window (`eval_mask`) and,
for the `hedged` class only, expressed relative to the reference tied-up capital (PROTOCOL §3: "tied-up
capital = spot notional + perp margin"): max(expo_j, expo_{j-1}), so that the cost of a full exit
(exposure 0 on the day of the cost) does not vanish. For `directional`, the series are the engine's as they
are (total capital = 1, cash earns zero).
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from research.engine.portfolio import relative_to
from research.gates.evaluate import Trial, CausalityReport


def _series(values: np.ndarray, days: np.ndarray, mask: np.ndarray, exposure: np.ndarray | None) -> pd.Series:
    """Dated series over the evaluation window; `exposure` not None: expressed relative to the reference tied-up
    capital max(expo_j, expo_{j-1}) (the divisor is computed on the WHOLE series before the mask is applied)."""
    v = values if exposure is None else relative_to(values, exposure)
    return pd.Series(v[mask].astype(float), index=pd.to_datetime(days[mask], unit="s"))


def to_trial(result, *, family: str, class_: str, params: Mapping[str, float]) -> Trial:
    """`result`: engine `TrialResult` with a `track` (code OK). Raises ValueError otherwise."""
    track = result.track
    if track is None:
        raise ValueError(f"trial {result.id} has no series (code {result.code})")
    mask = track.eval_mask
    divisor = track.exposure if class_ == "hedged" else None

    def ser(x):
        return _series(x, track.days, mask, divisor)

    return Trial(
        id=result.id, family=family, class_=class_, params=dict(params),
        net=ser(track.net_returns), net_stress=ser(track.stressed_net_returns), gross=ser(track.gross_returns),
        rotation=_series(track.rotation, track.days, mask, None), costs=ser(track.costs), universe=result.universe)


def to_causality_report(causality: dict | None, criteria) -> CausalityReport | None:
    """C9 summary from `TrialResult.causality` (dict from `verify_causality`). None if absent or if the
    test could not run to the end (key `error`)."""
    if not causality or "cutoffs_gap" not in causality:
        return None
    n_fixed = int(criteria.gates.C9_causality.fixed_cutoffs)
    n = int(causality["n_cutoffs"])
    gap = max(causality["cutoffs_gap"], causality["permutation_gap"], causality["scale_gap"])
    tol = 1e-9
    return CausalityReport(
        n_random_cuts=n - n_fixed, n_fixed=n_fixed,
        not_full_hour_share=causality["non_full_hour_cutoffs"] / n if n else 0.0,
        max_gap=float(gap),
        invariances_ok=bool(causality.get("deterministic", False) and causality["permutation_gap"] <= tol
                            and causality["scale_gap"] <= tol
                            # constant weights over the whole synthetic series: nothing proves causality
                            and causality.get("evaluable", False)
                            # second check, on the trial's real data (permutation + scales)
                            and causality.get("real_ok", False)))


def to_basket_series(basket_series) -> pd.Series:
    """Net returns of the engine basket over its evaluation window, as a dated `pd.Series`."""
    m = basket_series.eval_mask
    return pd.Series(basket_series.net_returns[m].astype(float),
                     index=pd.to_datetime(basket_series.days[m], unit="s"))
