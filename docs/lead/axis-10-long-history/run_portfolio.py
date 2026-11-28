"""Item 4: fixed-weight portfolio, chosen before any result (PREREGISTRATION.md section 3.4): EQUAL CAPITAL, one third
each (wick base, trend 1x, carry BTC+ETH), rebalanced daily (daily return = mean of the three daily returns), common window
2020-01-31 -> 2025-10-31. Two wick series: P1 = preregistered continuous run; P2 = post-hoc fresh-start-per-year wick
(and trend) series. Needs results/ from run_wick, run_trend, run_carry. usage: python run_portfolio.py"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
A = pd.Timestamp("2020-01-31", tz="UTC").date()
Z = pd.Timestamp("2025-10-31", tz="UTC").date()


def day(ts):
    return pd.to_datetime(np.asarray(ts), unit="s", utc=True).tz_convert("UTC").normalize().date if False else \
        [pd.Timestamp(int(t), unit="s", tz="UTC").date() for t in ts]


def ret_from_eq(f):
    z = np.load(f)
    e = pd.Series(z["eq"], index=pd.to_datetime(day(z["ts"])))
    e0 = pd.concat([pd.Series([1.0 if "carry" not in str(f) else e.iloc[0]], index=[e.index[0] - pd.Timedelta(days=1)]), e])
    return (e0 / e0.shift(1) - 1).dropna()


def ret_from_ret(f):
    z = np.load(f)
    return pd.Series(z["ret"], index=pd.to_datetime(day(z["ts"])))


def stats(r):
    eq = (1 + r).cumprod()
    out = {"total_pct": round(100 * (eq.iloc[-1] - 1), 2),
           "max_dd_pct": round(100 * float((eq / eq.cummax() - 1).min()), 2),
           "sharpe": round(float(r.mean() / r.std() * np.sqrt(365)), 2) if r.std() > 0 else 0.0, "years": {}}
    prev = 1.0
    for y, g in eq.groupby(eq.index.year):
        seg = np.r_[prev, g.to_numpy()]
        out["years"][int(y)] = dict(ret_pct=round(100 * (g.iloc[-1] / prev - 1), 2),
                                    max_dd_pct=round(100 * float((seg / np.maximum.accumulate(seg) - 1).min()), 2))
        prev = float(g.iloc[-1])
    return out


def main():
    carry_eq = np.load(RES / "carry_daily.npz")
    c = pd.Series(carry_eq["eq"], index=pd.to_datetime(day(carry_eq["ts"])))
    c_ret = (c / c.shift(1) - 1).dropna()
    series = {
        "wick_continuous": ret_from_eq(RES / "wick_base_daily.npz"),
        "wick_fresh_year": ret_from_ret(RES / "wick_base_fresh_daily_ret.npz"),
        "trend1x_continuous": ret_from_eq(RES / "trend_1x_daily.npz"),
        "trend1x_fresh_year": ret_from_ret(RES / "trend_1x_fresh_daily_ret.npz"),
        "carry": c_ret,
    }
    df = pd.DataFrame(series)
    df = df[(df.index >= pd.Timestamp(A)) & (df.index <= pd.Timestamp(Z))]
    out = {"n_days": int(len(df)), "nan_days": int(df.isna().any(axis=1).sum()), "first": str(df.index[0].date()), "last": str(df.index[-1].date())}
    df = df.fillna(0.0)
    out["stand_alone"] = {k: stats(df[k]) for k in df.columns}
    out["P1_preregistered"] = stats((df.wick_continuous + df.trend1x_continuous + df.carry) / 3)
    out["P2_posthoc_fresh_year"] = stats((df.wick_fresh_year + df.trend1x_fresh_year + df.carry) / 3)
    # POST-HOC, descriptive only: the same without the wick sleeve (trend 1x and carry, 50/50, daily rebalanced)
    out["P3_posthoc_ex_wick_trend_carry_50_50"] = stats((df.trend1x_continuous + df.carry) / 2)
    # correlation structure
    for name, cols in (("continuous", ["wick_continuous", "trend1x_continuous", "carry"]),
                       ("fresh_year", ["wick_fresh_year", "trend1x_fresh_year", "carry"])):
        d = df[cols]; d.columns = ["wick", "trend1x", "carry"]
        m = (1 + d).resample("MS").prod() - 1
        out[f"corr_daily_{name}"] = d.corr().round(3).to_dict()
        out[f"corr_monthly_{name}"] = m.corr().round(3).to_dict()
        # correlation excluding the wick's flat (no-position) days
        act = d[d.wick != 0]
        out[f"corr_daily_wick_active_days_{name}"] = act.corr().round(3).to_dict()
        out[f"wick_active_days_{name}"] = int(len(act))
    # worst days / months of each standalone series (diversification check)
    m = (1 + df).resample("MS").prod() - 1
    out["worst_month_pct"] = {k: round(100 * float(m[k].min()), 2) for k in df.columns}
    out["worst_day_pct"] = {k: round(100 * float(df[k].min()), 2) for k in df.columns}
    (RES / "portfolio.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
