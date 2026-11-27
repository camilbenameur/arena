"""Evaluates target weights through the same bench as the rules (arena.perp.lab.backtest.run) and compares them with
the frozen trend engine (1x and 2x), the 1x equal-weight buy-and-hold basket and random weights with the same turnover."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace

import numpy as np

import bars as BR
from bars import B

from arena.perp.lab import trend as T  # noqa: E402

N_RANDOM = 20
HOLD_GRID = (0.0, 0.5, 0.7, 0.8, 0.9, 0.95, 0.98, 0.995)


def bot_matrix(data: B.Data, b: BR.Bars, weights: np.ndarray) -> np.ndarray:
    """(N, K) bench targets from per-bar weights (nb_window, K) in units of equity/6: row = last minute of the bar."""
    t = np.full(data.close.shape, np.nan)
    t[b.end_idx[b.first : b.first + len(weights)]] = weights / 6.0
    return t


def run_one(data: B.Data, targets: np.ndarray, s0: int) -> tuple[dict, np.ndarray]:
    res = B.run(data, targets, s0, data.n)
    s = res.summary()
    months = {}
    ts = res.ts
    mon = np.array([dt.datetime.fromtimestamp(int(x), BR.DT).strftime("%Y-%m") for x in ts[::1440]])
    eq = res.equity[::1440]
    for m in dict.fromkeys(mon):
        idx = np.where(mon == m)[0]
        a, z = idx[0], idx[-1]
        e0 = 1.0 if a == 0 else eq[a - 1]
        months[str(m)] = round(float(100 * (eq[z] / e0 - 1)), 2)
    out = {
        "return_pct": s["total_pct"], "max_dd_pct": s["max_dd_pct"], "sharpe": s["sharpe"],
        "turnover_x": s["turnover_x"], "cost_paid_pct": round(s["fees_pct"] + s["slippage_pct"], 2),
        "funding_pct": s["funding_pct"], "months_pct": months, "ruined": s["ruined"],
    }
    return out, res.equity


def basket(data: B.Data, s0: int) -> np.ndarray:
    t = np.full(data.close.shape, np.nan)
    t[s0] = 1.0 / data.close.shape[1]
    return t


def random_like(weights: np.ndarray, p_hold: float, rng: np.random.Generator) -> np.ndarray:
    """Rows of the bot's own weights shuffled in time; each bar keeps the previous row with probability p_hold."""
    rows = weights[rng.permutation(len(weights))]
    out = np.empty_like(rows)
    out[0] = rows[0]
    for i in range(1, len(rows)):
        out[i] = out[i - 1] if rng.random() < p_hold else rows[i]
    return out


def evaluate_bot(data: B.Data, b: BR.Bars, s0: int, weights: np.ndarray, seed: int = 0, n_random: int = N_RANDOM) -> dict:
    bot, _ = run_one(data, bot_matrix(data, b, weights), s0)
    ref = {}
    for sc in (1.0, 2.0):
        ref[f"trend_{int(sc)}x"], _ = run_one(data, T.targets(data, replace(T.FROZEN, scale=sc)), s0)
    ref["basket_1x"], _ = run_one(data, basket(data, s0), s0)
    # random weights with the bot's turnover: calibrate the hold probability on one seed, then n_random seeds
    best, gap = HOLD_GRID[0], 1e18
    for p in HOLD_GRID:
        r, _ = run_one(data, bot_matrix(data, b, random_like(weights, p, np.random.default_rng(seed))), s0)
        if abs(r["turnover_x"] - bot["turnover_x"]) < gap:
            best, gap = p, abs(r["turnover_x"] - bot["turnover_x"])
    rets, dds, tos = [], [], []
    for k in range(n_random):
        r, _ = run_one(data, bot_matrix(data, b, random_like(weights, best, np.random.default_rng(seed + 1 + k))), s0)
        rets.append(r["return_pct"]); dds.append(r["max_dd_pct"]); tos.append(r["turnover_x"])
    rets = np.array(rets)
    rnd = {
        "hold_prob": best, "n": n_random, "return_mean_pct": round(float(rets.mean()), 2),
        "return_p95_pct": round(float(np.percentile(rets, 95)), 2), "turnover_mean_x": round(float(np.mean(tos)), 1),
        "max_dd_mean_pct": round(float(np.mean(dds)), 2),
        "share_beaten_by_bot": round(float(np.mean(bot["return_pct"] > rets)), 2),
    }
    months = list(bot["months_pct"].values())
    verdict = {
        "beats_trend_2x": bot["return_pct"] > ref["trend_2x"]["return_pct"],
        "beats_basket": bot["return_pct"] > ref["basket_1x"]["return_pct"],
        "max_dd_ok": bot["max_dd_pct"] >= -35.0,
        "positive_every_month": all(m > 0 for m in months),
        "beats_random_p95": bot["return_pct"] > rnd["return_p95_pct"],
    }
    return {"bot": bot, "reference": ref, "random": rnd, "criteria": verdict, "all_pass": all(verdict.values())}


def table(rep: dict) -> str:
    rows = [("bot", rep["bot"])] + [(k, v) for k, v in rep["reference"].items()]
    h = f"{'':12}{'return%':>9}{'maxDD%':>9}{'Sharpe':>8}{'turnover x':>11}{'cost %':>8}{'funding %':>10}"
    lines = [h]
    for k, v in rows:
        lines.append(f"{k:12}{v['return_pct']:>9.2f}{v['max_dd_pct']:>9.2f}{v['sharpe']:>8.2f}{v['turnover_x']:>11.1f}"
                     f"{v['cost_paid_pct']:>8.2f}{v['funding_pct']:>10.2f}")
    r = rep["random"]
    lines.append(f"{'random':12}{r['return_mean_pct']:>9.2f}{r['max_dd_mean_pct']:>9.2f}{'':>8}{r['turnover_mean_x']:>11.1f}"
                 f"   (mean of {r['n']}, p95 {r['return_p95_pct']}%, bot beats {100 * r['share_beaten_by_bot']:.0f}%)")
    st = rep.get("statuses")
    if st is not None:
        lines.append(f"statuses: {st} | truncated by max_tokens (held): {rep.get('truncations', 0)} of {rep.get('decisions', '?')}")
    lines.append("months (bot): " + ", ".join(f"{m} {v:+.1f}%" for m, v in rep["bot"]["months_pct"].items()))
    return "\n".join(lines)


def spread(reports: dict[str, dict]) -> dict:
    """Original run + replicates of the same frozen bot (label -> report.json): per-run figures and the spread of the
    return. Batch outputs differ between calls even with identical prompts, so the spread is the sampling noise."""
    per = {k: {"return_pct": v["bot"]["return_pct"], "max_dd_pct": v["bot"]["max_dd_pct"], "sharpe": v["bot"]["sharpe"],
               "turnover_x": v["bot"]["turnover_x"], "months_pct": v["bot"]["months_pct"],
               "beats_random_share": v["random"]["share_beaten_by_bot"], "all_pass": v["all_pass"]} for k, v in reports.items()}
    rets = np.array([p["return_pct"] for p in per.values()])
    return {"n_runs": len(per), "per_run": per, "return_min_pct": round(float(rets.min()), 2),
            "return_max_pct": round(float(rets.max()), 2), "return_mean_pct": round(float(rets.mean()), 2),
            "return_std_pct": round(float(rets.std(ddof=1)), 2) if len(rets) > 1 else None,
            "return_range_pp": round(float(rets.max() - rets.min()), 2), "any_pass": any(p["all_pass"] for p in per.values())}


def spread_table(sp: dict) -> str:
    lines = [f"{'run':10}{'return%':>9}{'maxDD%':>9}{'Sharpe':>8}{'turnover x':>11}{'beats random':>14}{'all pass':>10}"]
    for k, p in sp["per_run"].items():
        lines.append(f"{k:10}{p['return_pct']:>9.2f}{p['max_dd_pct']:>9.2f}{p['sharpe']:>8.2f}{p['turnover_x']:>11.1f}"
                     f"{100 * p['beats_random_share']:>13.0f}%{str(p['all_pass']):>10}")
    lines.append(f"spread over {sp['n_runs']} runs: return {sp['return_min_pct']:+.2f}% to {sp['return_max_pct']:+.2f}% "
                 f"(range {sp['return_range_pp']:.2f} pp, mean {sp['return_mean_pct']:+.2f}%, std {sp['return_std_pct']})")
    return "\n".join(lines)
