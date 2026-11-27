"""Sealed control, 2026-01-01 -> latest. Runs ONCE: an exclusive lock file is created before any 2026 row is read."""
import json
import sys
from pathlib import Path
from lib import BASE, CUT, run_all, views

HERE = Path(__file__).resolve().parent
LOCK = Path("~/dev/_arena-data/axis-05/CONTROL_RUN.lock").expanduser()


def main():
    try:
        with LOCK.open("x") as f:
            f.write("control opened\n")
    except FileExistsError:
        sys.exit("REFUSED: the sealed control was already run (lock file exists). No second run.")
    res = {}
    for dl in (1, 5, 15, 30, 60):  # 1 = diagnostic only
        evs = run_all(["design", "control"], dict(BASE, delay=dl), since_ms=CUT)
        res[f"long_delay{dl}"] = dict(views=views(evs), events=evs)
        print(dl, views(evs)["raw"], flush=True)
    (HERE / "control_results.json").write_text(json.dumps(res))
    # the short mirror is NOT run: it failed the design symmetry test (see PREREGISTRATION.md section 3)


if __name__ == "__main__":
    main()
