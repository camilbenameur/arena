#!/usr/bin/env python
"""Axis 9 evaluation of the frozen rule.

  python docs/lead/axis-09-llm-researcher/evaluate.py --period design     # in-sample (the model fitted on it): informative only
  python docs/lead/axis-09-llm-researcher/evaluate.py --period control    # sealed: needs the committed FROZEN preregistration, runs once

Axis 9b (population of sessions, see PREREGISTRATION-9b.md):

  evaluate.py --session opus-s01 --period design      # in sample, informative; can be run any time
  evaluate.py --print-session-list                    # lines to paste into PREREGISTRATION-9b.md before freezing it
  evaluate.py --session opus-s01 --period control     # needs the committed FROZEN 9b file listing this session's sha256; once per session
  evaluate.py --summary                               # design and control of every session, mean/median, counts

Steps: load frozen_rule.py; causality check on the design bars (targets recomputed on truncated data, zero gap required);
map the 4-hour targets onto the axis-8 minute bench; report against trend 2x, basket 1x and random weights with the same
turnover, with the axis-8 pass criteria (beats trend 2x and basket, max drawdown no deeper than 35%, positive in every month,
beats the 95th percentile of 20 random bots with the same turnover).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import common as C  # noqa: E402

RULE = HERE / "frozen_rule.py"
PREREG = HERE / "PREREGISTRATION.md"
PREREG_9B = HERE / "PREREGISTRATION-9b.md"
NO_EDGE_RE = re.compile(r"no robust edge", re.I)


def session_list(repo_dir: Path = HERE) -> str:
    """Lines for the 9b preregistration: one per session directory, with the sha256 of its rule or `no rule`."""
    out = []
    for d in sorted((repo_dir / "sessions").glob("*")) if (repo_dir / "sessions").exists() else []:
        if not d.is_dir() or not C.SESSION_RE.match(d.name):
            continue
        rule = d / "frozen_rule.py"
        out.append(f"session {d.name} frozen_rule.py sha256: {C.sha256_file(rule)}" if rule.exists() else f"session {d.name} no rule")
    return "\n".join(out)


def labelled_no_edge(code_dir: Path) -> bool:
    """True when the session's own rule or log says `no robust edge` (the label the brief asks for when nothing holds up)."""
    for f in ("trials_by_model.md", "frozen_rule.py"):
        p = code_dir / f
        if p.exists() and NO_EDGE_RE.search(p.read_text()):
            return True
    return False


def load_session_rows(repo_dir: Path = HERE, data_dir: Path = C.DATA_DIR) -> list[dict]:
    rows = []
    base = repo_dir / "sessions"
    for d in sorted(base.glob("*")) if base.exists() else []:
        if not d.is_dir() or not C.SESSION_RE.match(d.name):
            continue
        _, tdir = C.session_dirs(d.name, repo_dir, data_dir)
        row = {"session": d.name, "rule": (d / "frozen_rule.py").exists(), "no_edge": labelled_no_edge(d)}
        for per in ("design", "control"):
            f = tdir / f"eval_{per}.json"
            row[per] = json.loads(f.read_text()) if f.exists() else None
        oc = d / "outcome.json"
        row["usd"] = json.loads(oc.read_text()).get("usd") if oc.exists() else None
        rows.append(row)
    return rows


def _rep(row: dict, per: str):
    e = row.get(per)
    return e.get("report") if e else None


def summarize(rows: list[dict]) -> dict:
    """Population statistics over the sessions that have a control report."""
    ctrl = [(r["session"], _rep(r, "control")) for r in rows if _rep(r, "control")]
    rets = [rep["bot"]["return_pct"] for _, rep in ctrl]
    rnd = [rep["random"]["return_mean_pct"] for _, rep in ctrl]
    out = {"n_sessions": len(rows), "n_rule": sum(r["rule"] for r in rows), "n_control": len(ctrl),
           "n_no_edge_label": sum(r["no_edge"] for r in rows if r["rule"]),
           "share_no_edge_label": None, "refused": [r["session"] for r in rows if (r.get("control") or {}).get("refused")]}
    if out["n_rule"]:
        out["share_no_edge_label"] = round(out["n_no_edge_label"] / out["n_rule"], 3)
    if ctrl:
        crit = lambda k: sum(bool(rep["criteria"][k]) for _, rep in ctrl)  # noqa: E731
        out.update(mean_return_pct=round(statistics.fmean(rets), 2), median_return_pct=round(statistics.median(rets), 2),
                   mean_random_pct=round(statistics.fmean(rnd), 2),
                   mean_minus_random_pct=round(statistics.fmean(a - b for a, b in zip(rets, rnd)), 2),
                   n_positive=sum(x > 0 for x in rets), n_beats_basket=crit("beats_basket"), n_beats_trend_2x=crit("beats_trend_2x"),
                   n_beats_random_p95=crit("beats_random_p95"), n_max_dd_ok=crit("max_dd_ok"),
                   n_positive_every_month=crit("positive_every_month"), n_all_pass=sum(bool(rep["all_pass"]) for _, rep in ctrl),
                   basket_pct=ctrl[0][1]["reference"]["basket_1x"]["return_pct"],
                   trend_2x_pct=ctrl[0][1]["reference"]["trend_2x"]["return_pct"])
        if len(rets) > 1:
            sd = statistics.stdev(rets)
            out["std_return_pct"] = round(sd, 2)
            out["t_mean_vs_0"] = round(statistics.fmean(rets) / (sd / len(rets) ** 0.5), 2) if sd > 0 else None
            d = [a - b for a, b in zip(rets, rnd)]
            sdd = statistics.stdev(d)
            out["t_mean_vs_random"] = round(statistics.fmean(d) / (sdd / len(d) ** 0.5), 2) if sdd > 0 else None
    return out


def print_summary(rows: list[dict]) -> None:
    print(f"{'session':16}{'no-edge':>8}{'design%':>9}{'ctrl%':>8}{'maxDD%':>8}{'turn x':>8}{'rand mean':>10}{'rand p95':>9}{'beats rnd':>10}{'pass':>6}{'usd':>7}")
    for r in rows:
        d, c = _rep(r, "design"), _rep(r, "control")
        f = lambda x, w, p=2: f"{x:>{w}.{p}f}" if x is not None else f"{'-':>{w}}"  # noqa: E731
        state = "" if r["rule"] else "  (no rule)"
        if (r.get("control") or {}).get("refused") or (r.get("design") or {}).get("refused"):
            state = "  (rule refused: not causal)"
        print(f"{r['session']:16}{'yes' if r['no_edge'] else 'no':>8}{f(d['bot']['return_pct'] if d else None, 9)}"
              f"{f(c['bot']['return_pct'] if c else None, 8)}{f(c['bot']['max_dd_pct'] if c else None, 8)}"
              f"{f(c['bot']['turnover_x'] if c else None, 8, 1)}{f(c['random']['return_mean_pct'] if c else None, 10)}"
              f"{f(c['random']['return_p95_pct'] if c else None, 9)}{f(c['random']['share_beaten_by_bot'] if c else None, 10)}"
              f"{('yes' if c['all_pass'] else 'no') if c else '-':>6}{f(r['usd'], 7)}{state}")
    s = summarize(rows)
    print()
    for k, v in s.items():
        print(f"{k}: {v}")


def run_session_eval(a, repo_dir: Path = HERE, data_dir: Path = C.DATA_DIR, prereg: Path = PREREG_9B) -> None:
    """Axis 9b: design or control of one session's frozen rule. The control needs the committed FROZEN 9b preregistration listing
    this session's sha256, and is taken once per session (lock in the session's data directory)."""
    code_dir, tdir = C.session_dirs(a.session, repo_dir, data_dir)
    rule = code_dir / "frozen_rule.py"
    if a.rule != RULE:
        raise SystemExit("--rule cannot be combined with --session")
    if not rule.exists():
        raise SystemExit(f"{a.session} has no frozen_rule.py (no rule was written: it counts as a session without a rule)")
    tdir.mkdir(parents=True, exist_ok=True)
    commit = ""
    if a.period == "control":
        commit = C.control_gate_session(prereg, rule, a.session, repo_dir if (repo_dir / ".git").exists() else C.REPO)
        if C.control_ran(tdir):
            raise SystemExit(f"control refused: the control of {a.session} already ran (one rule, one control run)")
    sha = C.sha256_file(rule)
    fn = C.load_rule(rule)
    _, design = C.design_csv()
    gap = C.causality_gap(fn, design)
    print(f"{a.session}: causality gap on design bars: {gap:.3e}")
    if gap > 1e-12:
        if a.period == "control":
            C.take_control_lock(commit, sha, tdir)  # a refused rule still uses up its one control slot: no second try
        (tdir / f"eval_{a.period}.json").write_text(json.dumps({"rule_sha256": sha, "prereg_commit": commit, "causality_gap": gap,
                                                                "refused": "not causal"}, indent=1))
        raise SystemExit("rule refused: not causal (targets change when later rows are removed)")
    if a.period == "control":
        C.take_control_lock(commit, sha, tdir)  # before the control data is touched
    rep = C.evaluate(fn, a.period, a.n_random)
    print(C.REP.table(rep))
    print("criteria:", rep["criteria"], "| ALL PASS:", rep["all_pass"])
    (tdir / f"eval_{a.period}.json").write_text(json.dumps(
        {"rule_sha256": sha, "prereg_commit": commit, "causality_gap": gap, "report": rep}, indent=1, default=float))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", choices=["design", "control"])
    ap.add_argument("--session", default=None, help="axis 9b session name <model>-<id>, e.g. opus-s01")
    ap.add_argument("--summary", action="store_true", help="axis 9b: design and control of every session, population statistics")
    ap.add_argument("--print-session-list", action="store_true", help="axis 9b: the lines to paste into the preregistration")
    ap.add_argument("--rule", type=Path, default=RULE)
    ap.add_argument("--n-random", type=int, default=C.REP.N_RANDOM)
    a = ap.parse_args()
    if a.summary:
        print_summary(load_session_rows())
        return
    if a.print_session_list:
        print(session_list())
        return
    if not a.period:
        raise SystemExit("--period is required (or use --summary / --print-session-list)")
    if a.session:
        return run_session_eval(a)
    if not a.rule.exists():
        raise SystemExit(f"{a.rule.name} does not exist")
    commit = ""
    if a.period == "control":
        if a.rule.resolve() != RULE.resolve():
            raise SystemExit("control refused: only the shipped frozen_rule.py can be run on the control")
        commit = C.control_gate(PREREG, RULE)
        if C.control_ran():
            raise SystemExit("control refused: the axis-9 control already ran (one rule, one control run)")
    fn = C.load_rule(a.rule)
    _, design = C.design_csv()
    gap = C.causality_gap(fn, design)
    print(f"causality gap on design bars: {gap:.3e}")
    if gap > 1e-12:
        raise SystemExit("rule refused: not causal (targets change when later rows are removed)")
    if a.period == "control":
        C.take_control_lock(commit, C.sha256_file(RULE))  # before the control data is touched
    rep = C.evaluate(fn, a.period, a.n_random)
    print(C.REP.table(rep))
    print("criteria:", rep["criteria"], "| ALL PASS:", rep["all_pass"])
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (C.DATA_DIR / f"eval_{a.period}.json").write_text(json.dumps(
        {"rule_sha256": C.sha256_file(a.rule), "prereg_commit": commit, "causality_gap": gap, "report": rep}, indent=1, default=float))


if __name__ == "__main__":
    main()
