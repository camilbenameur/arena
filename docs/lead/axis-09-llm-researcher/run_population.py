#!/usr/bin/env python
"""Axis 9b batch driver: N independent research sessions of one model, same brief, each in its own directory.

  python docs/lead/axis-09-llm-researcher/run_population.py --model opus --n 6                  # sequential
  python docs/lead/axis-09-llm-researcher/run_population.py --model opus --n 6 --parallel 2     # two at a time
  python docs/lead/axis-09-llm-researcher/run_population.py --model opus --n 6 --dry-run        # plan only, no key, no network

Sessions are named <model>-sNN (s01, s02, ...). A session whose directory already exists is skipped, never re-run. Before each
wave the driver checks that the axis-9b budget (30 USD on the axis-09 ledger, and the shared total with axis 8) still covers the
per-session cap (3 USD) of every session of the wave; if not it stops cleanly. A session that reports an axis-level budget stop
or an API error with an open reservation also stops the driver. Every outcome (rule written or not, cost, stop reason) is
appended to population_9b.jsonl in the data directory and written as sessions/<model>-<id>/outcome.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import importlib.util  # noqa: E402

import common as C  # noqa: E402

_spec = importlib.util.spec_from_file_location("axis09_research", HERE / "research.py")
R = importlib.util.module_from_spec(_spec)  # loaded by path: the repository also has a `research` package
sys.modules.setdefault("axis09_research", R)
_spec.loader.exec_module(R)


def sid(i: int) -> str:
    return f"s{i:02d}"


def axis_room(data_dir: Path) -> float:
    """USD left for axis 9b: the smaller of the axis-09 ledger cap and the shared total with axis 8."""
    axis = C.BUD.Ledger(data_dir / "spend.jsonl").totals()["total"]
    other = C.BUD.Ledger(C.BUD.LEDGER).totals()["total"]
    return min(R.AXIS9_PRIOR_USD + R.AXIS9B_CAP_USD - axis, R.SHARED_CAP_USD - other - axis)


def run_population(client, model: str, n: int, *, files: dict, brief: str, parallel: int = 1, start: int = 1,
                   session_cap: float = R.SESSION_CAP_USD, data_dir: Path | None = None, repo_dir: Path | None = None,
                   **kw) -> dict:
    data_dir = C.DATA_DIR if data_dir is None else data_dir
    repo_dir = HERE if repo_dir is None else repo_dir
    todo = [sid(i) for i in range(start, start + n)
            if not C.session_dirs(f"{model}-{sid(i)}", repo_dir, data_dir)[0].exists()
            and not C.session_dirs(f"{model}-{sid(i)}", repo_dir, data_dir)[1].exists()]
    outcomes, stopped = [], None
    while todo:
        room = axis_room(data_dir)
        k = min(parallel, int(room // session_cap), len(todo))
        if k < 1:
            stopped = f"budget: {room:.2f} USD left on axis 9b, below the per-session cap {session_cap:.2f}"
            break
        wave, todo = todo[:k], todo[k:]
        run = lambda s: R.execute_session(client, model, s, files=files, brief=brief, session_cap=session_cap,  # noqa: E731
                                          repo_dir=repo_dir, data_dir=data_dir, **kw)
        if k == 1:
            wave_out = [run(wave[0])]
        else:
            with ThreadPoolExecutor(max_workers=k) as ex:
                wave_out = list(ex.map(run, wave))
        outcomes += wave_out
        halt = next((o for o in wave_out if o["halt"]), None)
        if halt:
            stopped = f"halt after {halt['session']}: {halt['stop']}"
            break
    if todo and stopped is None:
        stopped = "unfinished"
    return {"model": model, "requested": n, "run": len(outcomes), "rules_written": sum(o["rule_written"] for o in outcomes),
            "usd": round(sum(o["usd"] for o in outcomes), 4), "stopped": stopped, "not_run": todo, "outcomes": outcomes}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=sorted(R.MODELS))
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--start", type=int, default=1, help="first session number (s01 by default)")
    ap.add_argument("--parallel", type=int, default=1, choices=[1, 2])
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--max-tokens", type=int, default=64000)
    ap.add_argument("--max-turns", type=int, default=60)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.n < 1:
        raise SystemExit("--n must be at least 1")
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    text, _ = C.design_csv()
    helper = (HERE / "sandbox_backtest.py").read_text()
    brief = R.build_brief(R.design_reference(C.DATA_DIR))
    C.assert_design_only(brief, "brief")
    room = axis_room(C.DATA_DIR)
    print(f"axis 9b room {room:.2f} USD; per-session cap {R.SESSION_CAP_USD}; sessions {sid(a.start)}..{sid(a.start + a.n - 1)} of {a.model}")
    if a.dry_run:
        return
    out = run_population(R.real_client(), a.model, a.n, files=R.population_files(text, helper), brief=brief, parallel=a.parallel,
                         start=a.start, effort=a.effort, max_tokens=a.max_tokens, max_turns=a.max_turns)
    for o in out["outcomes"]:
        print(f"{o['session']}: rule_written={o['rule_written']} usd={o['usd']:.2f} turns={o['turns']} stop={o['stop']}")
    print(json.dumps({k: v for k, v in out.items() if k != "outcomes"}))


if __name__ == "__main__":
    main()
