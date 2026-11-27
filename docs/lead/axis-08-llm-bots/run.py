#!/usr/bin/env python
"""CLI of the LLM-bot backtests. Examples (from the repository root, venv active):

  python docs/lead/axis-08-llm-bots/run.py --estimate
  python docs/lead/axis-08-llm-bots/run.py --model haiku --prompt-variant v1_plain --period design --dry-run
  python docs/lead/axis-08-llm-bots/run.py --model haiku --prompt-variant v2_costaware --period design --cap-usd 5
  python docs/lead/axis-08-llm-bots/run.py --model haiku --prompt-variant v1_plain --period design --cap-usd 5 --collect
  python docs/lead/axis-08-llm-bots/run.py --model haiku --pilot --max-bars 2          # real sync calls, cap 2 USD, design only
  python docs/lead/axis-08-llm-bots/run.py --list-reservations
  python docs/lead/axis-08-llm-bots/run.py --release <reservation id>                  # after checking the console

Default path: Message Batches API (-50%), stateless prompts (the bot is not told its positions, because the 4-hour
decisions of a batch cannot depend on each other). --mode sync: one call per bar, stateful prompts (own weights, equity,
drawdown), full price. Control mode needs a committed PREREGISTRATION.md that lists the bot id, and runs once per bot id.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bars as BR  # noqa: E402
import bot as BOT  # noqa: E402
import budget as BUD  # noqa: E402
import report as REP  # noqa: E402

DATA_DIR = Path.home() / "dev" / "_arena-data" / "axis-08"
PREREG = HERE / "PREREGISTRATION.md"
PREREG_8B = HERE / "PREREGISTRATION-8b.md"  # axis 8b: replicates of frozen bots (part A) and stateful high-effort bots (part B)
MAX_REPLICATE = 3
EFFORTS = ("low", "medium", "high")
# assumed output tokens per call INCLUDING thinking at the default effort (to be calibrated with the pilot)
OUT_TOKENS = {"claude-haiku-5-5": 700, "claude-sonnet-5-5": 900, "claude-opus-5-5": 1800, "claude-fable-5-2": 2500}
CHARS_PER_TOKEN = 3.5
PILOT_CAP_USD = 2.0
PILOT_BARS = 6
SYNC_ATTEMPTS = 3
FROZEN_RE = re.compile(r"^STATUS: FROZEN$", re.M)


def bot_id(model: str, variant: str, effort: str, mode: str) -> str:
    """model, variant + prompt hash + code hash (bars.py, bot.py: features, rendering, message template), effort, mode."""
    return f"{model}__{variant}-{BOT.prompt_hash(variant)}-{BOT.code_hash()}__{effort}__{mode}"


# ------------------------------------------------------------------------------------------------ control gate


def _git(*a: str) -> str:
    return subprocess.run(["git", "-C", str(BR.REPO), *a], capture_output=True, text=True, check=False).stdout.strip()


def is_frozen(text: str) -> bool:
    return FROZEN_RE.search(text) is not None


def _read_lock(data_dir: Path) -> list[dict]:
    f = data_dir / "control_runs.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f.exists() else []


def listed_ids(text: str) -> set[str]:
    """Bot ids listed as bullet lines ("- id" or "- `id`", nothing else on the line). Exact match: a replicate id
    ("<base>__r1") never makes its base id look listed, nor the reverse."""
    return set(re.findall(r"^[-*]\s+`?([^\s`]+)`?\s*$", text, re.M))


def replicate_id(bid: str, n: int) -> str:
    """Id of a replicate of a frozen bot: same bot id + suffix. It names the run directory and the control lock."""
    return f"{bid}__r{n}"


def run_dir_for(root: Path, bid: str, period: str, replicate: int | None = None) -> Path:
    return root / f"{replicate_id(bid, replicate) if replicate else bid}__{period}"


def control_ran(bid: str, data_dir: Path | None = None) -> bool:
    """True when a REAL (non dry-run) control run of this bot id is on record."""
    return any(e["bot_id"] == bid and not e.get("dry_run") for e in _read_lock(data_dir or DATA_DIR))


def take_control_lock(bid: str, prereg_commit: str, dry_run: bool, data_dir: Path | None = None) -> None:
    """Check-and-write under one flock. Called only AFTER the budget reservation succeeded and just before the first
    submission or call: a refused budget leaves no lock, a failed run after this point still counts."""
    d = data_dir or DATA_DIR
    d.mkdir(parents=True, exist_ok=True)
    with (d / "control_runs.jsonl.lock").open("a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        if control_ran(bid, d):
            raise SystemExit(f"control refused: {bid} already ran on the control (use --collect to read its results)")
        with (d / "control_runs.jsonl").open("a") as f:
            f.write(json.dumps({"ts": int(time.time()), "bot_id": bid, "prereg_commit": prereg_commit, "dry_run": dry_run}) + "\n")


def _committed(path: Path) -> tuple[str, str]:
    """(commit, text) of a preregistration file that exists, is committed, is unmodified and is frozen; else SystemExit."""
    rel = str(path.relative_to(BR.REPO))
    if not path.exists():
        raise SystemExit(f"control refused: {path.name} does not exist")
    commit = _git("log", "-n1", "--format=%H", "--", rel)
    if not commit:
        raise SystemExit(f"control refused: {path.name} is not committed in git")
    if _git("status", "--porcelain", "--", rel):
        raise SystemExit(f"control refused: {path.name} has uncommitted changes")
    text = path.read_text()
    if not is_frozen(text):
        raise SystemExit(f"control refused: {path.name} has no line reading exactly STATUS: FROZEN")
    return commit, text


def control_gate(bid: str, collect: bool, replicate: int | None = None) -> str:
    """Refuses unless the right preregistration is committed (and unmodified), frozen, lists this bot, and this bot has not
    run on the control before. Returns the commit that holds it. Does not write the lock.
    - replicate n: PREREGISTRATION.md must list the base id `bid` AND PREREGISTRATION-8b.md must list `bid__rN`;
      the control lock is the replicate id, so the original run's lock is never touched.
    - a bot listed in PREREGISTRATION-8b.md (new stateful bots): that file must be frozen and committed.
    - otherwise: PREREGISTRATION.md (axis 8) must list `bid`."""
    if replicate is not None:
        if not 1 <= replicate <= MAX_REPLICATE:
            raise SystemExit(f"control refused: replicate must be 1..{MAX_REPLICATE}")
        if not PREREG_8B.exists():
            raise SystemExit("control refused: a replicate needs PREREGISTRATION-8b.md, which does not exist")
        _, text8 = _committed(PREREG)
        if bid not in listed_ids(text8):
            raise SystemExit(f"control refused: base bot id {bid} is not listed in the axis-8 preregistration")
        commit, textb = _committed(PREREG_8B)
        rid = replicate_id(bid, replicate)
        if rid not in listed_ids(textb):
            raise SystemExit(f"control refused: replicate id {rid} is not listed in PREREGISTRATION-8b.md")
        lock_id = rid
    elif PREREG_8B.exists() and bid in listed_ids(PREREG_8B.read_text()):
        commit, _ = _committed(PREREG_8B)
        lock_id = bid
    else:
        commit, text = _committed(PREREG)
        if bid not in text:
            raise SystemExit(f"control refused: bot id {bid} is not listed in the committed preregistration")
        lock_id = bid
    if not collect and control_ran(lock_id):
        raise SystemExit(f"control refused: {lock_id} already ran on the control (use --collect or --resume to read or finish it)")
    return commit


# ------------------------------------------------------------------------------------------------ estimate


def sample_prompts(variant: str, mode: str, period: str, every: int = 6):
    s, e = BR.PERIODS[period]
    data, i0 = BR.load_data(s, e)
    b = BR.make_bars(data, i0)
    n = b.n - b.first
    st = BR.render_state(np.zeros(6), 1.0, 1.0, 0.0) if mode == "sync" else None
    users = [BR.user_message(b, b.first + k, st) for k in range(0, n, every)]
    return n, users


def estimate(client_count=None) -> list[dict]:
    rows = []
    for variant in BOT.VARIANTS:
        for mode in ("batch", "sync"):
            for period in ("design", "control"):
                n, users = sample_prompts(variant, mode, period)
                sys_t = len(BOT.VARIANTS[variant]) / CHARS_PER_TOKEN + len(json.dumps(BOT.OUTPUT_SCHEMA)) / CHARS_PER_TOKEN
                user_t = float(np.mean([len(u) for u in users])) / CHARS_PER_TOKEN
                for model, price in BUD.PRICES.items():
                    batch = mode == "batch"
                    out = OUT_TOKENS[model]
                    nocache = BUD.usage_cost(model, {"input_tokens": n * (sys_t + user_t), "output_tokens": n * out}, batch)
                    cached = BUD.usage_cost(model, {"input_tokens": n * user_t, "output_tokens": n * out,
                                                    "cache_read_input_tokens": (n - 1) * sys_t,
                                                    "cache_creation_input_tokens": sys_t}, batch)
                    worst = BUD.projected_cost(model, int(sys_t + user_t), BOT.MAX_TOKENS, n, batch)
                    rows.append({"model": model, "variant": variant, "mode": mode, "period": period, "calls": n,
                                 "sys_tok": round(sys_t), "user_tok": round(user_t), "out_tok_assumed": out,
                                 "usd": round(nocache, 2), "usd_cached": round(cached, 2), "usd_worst": round(worst, 2)})
    return rows


def print_estimate(rows: list[dict]) -> None:
    print("| model | variant | mode | period | calls | in tok/call | out tok/call (assumed) | est. USD | est. USD, system cached | worst case USD |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['model']} | {r['variant']} | {r['mode']} | {r['period']} | {r['calls']} | {r['sys_tok'] + r['user_tok']} | "
              f"{r['out_tok_assumed']} | {r['usd']:.2f} | {r['usd_cached']:.2f} | {r['usd_worst']:.2f} |")


# ------------------------------------------------------------------------------------------------ calls and batches


def shadow_state(b: BR.Bars, w: np.ndarray, eq: float, cost: float, t: int, new_w: np.ndarray | None):
    """Approximate own track record of the bot over bar t with weights w (x equity/6), then the cost of moving to new_w."""
    r = b.c[t] / b.o[t] - 1
    eq *= 1 + float(np.sum(w / 6 * r) - np.sum(w / 6 * b.fund[t]))
    if new_w is not None:
        c = float(np.sum(np.abs(new_w - w)) / 6 * 12e-4)
        eq *= 1 - c
        cost += c
    return eq, cost


def decision_from_message(t: int, msg, usd: float) -> dict:
    w, reason, status = BOT.parse_message(msg)
    return {"t": t, "status": status, "reason": reason, "weights": None if w is None else w.tolist(),
            "usage": BOT.usage_dict(msg), "stop_reason": getattr(msg, "stop_reason", None), "usd": usd}


def guarded_call(client, ledger: BUD.Ledger, params: dict, model: str, base_key: str, proj_usd: float, cap: float,
                 before_first_call=None, sleep=time.sleep):
    """One synchronous call, no SDK retry. Every attempt has its OWN reservation, taken before the attempt:
    - 429 (rejected before processing): reservation released, retry;
    - 5xx (may have been processed): the reservation STAYS OPEN (counted against the cap), then retry;
    - other 4xx: reservation released, error raised; timeout, connection or unknown error: reservation stays open, raised.
    So a second billing can never go uncounted. Returns (message, reservation id, usd already settled)."""
    for attempt in range(SYNC_ATTEMPTS):
        rid = ledger.reserve(f"{base_key}:a{attempt}", proj_usd, cap)
        if before_first_call is not None and attempt == 0:
            before_first_call()
        try:
            msg = client.messages.create(**params)
        except Exception as ex:  # noqa: BLE001
            kind = BOT.classify_error(ex)
            if kind == "retry_clean":
                ledger.release(rid)
            elif kind == "definite":
                ledger.release(rid)
                raise
            elif kind == "ambiguous":
                raise
            if attempt == SYNC_ATTEMPTS - 1:
                raise
            sleep(2 ** (attempt + 1))
            continue
        return msg, rid
    raise AssertionError("unreachable")


def settle_sync(ledger: BUD.Ledger, rid: str, model: str, msg, dry_run: bool) -> float:
    u = {} if dry_run else BOT.usage_dict(msg)
    usd = ledger.actual(rid, model, u, False, custom_id=rid, dedupe=rid)
    ledger.release(rid)
    return usd


def load_partial(path: Path, n: int) -> dict[int, dict]:
    """Decisions already made (and paid) by an interrupted sync run. A torn last line is ignored."""
    out: dict[int, dict] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                d = json.loads(line)
                if 0 <= int(d["t"]) < n:
                    out[int(d["t"])] = d
            except (ValueError, KeyError, TypeError):
                continue
    return out


def sync_loop(client, ledger, model, effort, variant, b, n, bid, period, cap, dry_run, lock_fn=None, on_call=None,
              partial_path: Path | None = None, done: dict[int, dict] | None = None) -> dict[int, dict]:
    """One call per bar. `done` = decisions of an interrupted run: those bars are NOT called again (they were paid); their
    weights replay the stateful track record (equity, drawdown, cost) exactly as the original run saw it."""
    done = done or {}
    decisions: dict[int, dict] = {}
    w, eq, peak, cost = np.zeros(6), 1.0, 1.0, 0.0
    for t in range(n):
        eq, cost = shadow_state(b, w, eq, cost, b.first + t, None) if t else (eq, cost)
        peak = max(peak, eq)
        if t in done:
            decisions[t] = done[t]
            if done[t]["weights"] is not None:
                w = np.array(done[t]["weights"])
            continue
        user = BR.user_message(b, b.first + t, BR.render_state(w, eq, peak, cost))
        p = BOT.build_params(model, effort, variant, user)
        in_tok = int((len(user) + len(BOT.VARIANTS[variant])) / CHARS_PER_TOKEN) + 300
        proj = BUD.projected_cost(model, in_tok, BOT.MAX_TOKENS, 1, False)
        msg, rid = guarded_call(client, ledger, p, model, f"{bid}:{period}:{t:04d}", proj, cap,
                                before_first_call=lock_fn if t == 0 else None)
        usd = settle_sync(ledger, rid, model, msg, dry_run)
        decisions[t] = decision_from_message(t, msg, usd)
        if partial_path is not None:
            with partial_path.open("a") as f:
                f.write(json.dumps(decisions[t]) + "\n")
        if on_call:
            on_call(decisions[t])
        if decisions[t]["weights"] is not None:
            w = np.array(decisions[t]["weights"])
    return decisions


def _requests(client_is_fake: bool, reqs: list[dict]):
    return reqs if client_is_fake else _to_sdk(reqs)


def _to_sdk(reqs: list[dict]):
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    return [Request(custom_id=r["custom_id"], params=MessageCreateParamsNonStreaming(**r["params"])) for r in reqs]


def _write_json(path: Path, obj: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj))
    tmp.replace(path)


def submit_batch(client, ledger: BUD.Ledger, run_dir: Path, key: str, reqs: list[dict], proj: float, cap: float, *,
                 fake: bool, lock_fn=None, chunk: int = 5000) -> tuple[list[str], str]:
    """Submits once. Refuses if batch.json already exists (a previous submission, even one that failed in an unknown way,
    must be settled with --collect or inspected by hand). No SDK retry (batches.create is not idempotent). Order:
    reserve (atomic) -> control lock -> batch.json 'submitting' -> create -> batch.json 'submitted'."""
    batch_file = run_dir / "batch.json"
    if batch_file.exists():
        raise SystemExit(f"refused: {batch_file.name} already exists for this bot and period (state "
                         f"{json.loads(batch_file.read_text()).get('state')}); use --collect, never submit twice")
    rid = ledger.reserve(key, proj, cap, note=f"batch of {len(reqs)}")  # BudgetExceeded: nothing submitted, no lock
    if lock_fn is not None:
        lock_fn()
    state = {"state": "submitting", "batch_ids": [], "reserve_id": rid, "n": len(reqs)}
    _write_json(batch_file, state)
    try:
        for k in range(0, len(reqs), chunk):
            bt = client.messages.batches.create(requests=_requests(fake, reqs[k:k + chunk]))
            state["batch_ids"].append(bt.id)
            _write_json(batch_file, state)
    except Exception as ex:  # noqa: BLE001
        if not state["batch_ids"] and BOT.classify_error(ex) in ("definite", "retry_clean"):
            ledger.release(rid)  # rejected before anything was created
            batch_file.unlink()
            raise
        state["state"] = "unknown"  # the batch may exist at the provider: keep the reservation, block resubmission
        state["error"] = f"{type(ex).__name__}: {str(ex)[:200]}"
        _write_json(batch_file, state)
        raise SystemExit(f"batch submission outcome unknown ({state['error']}). Reservation {rid} kept open and batch.json "
                         "marked 'unknown': check the console for a batch before anything else; do not resubmit.") from ex
    state["state"] = "submitted"
    _write_json(batch_file, state)
    return state["batch_ids"], rid


def collect_batch(client, ledger: BUD.Ledger, run_dir: Path, model: str, *, dry_run: bool, poll_s: float = 60.0) -> dict[int, dict]:
    """Reads the results of the submitted batch(es). Idempotent: every actual is keyed by batch id + custom_id and is
    appended at most once, however many times this runs. Releases the batch reservation at the end."""
    batch_file = run_dir / "batch.json"
    if not batch_file.exists():
        raise SystemExit("--collect: no batch.json for this bot and period")
    st = json.loads(batch_file.read_text())
    if st.get("state") != "submitted" or not st.get("batch_ids"):
        raise SystemExit(f"--collect: batch.json state is {st.get('state')!r} (error: {st.get('error')}): "
                         "inspect the console, this run cannot be collected automatically")
    decisions: dict[int, dict] = {}
    for batch_id in st["batch_ids"]:
        BOT.poll_batch(client, batch_id, every_s=poll_s)
        for r in client.messages.batches.results(batch_id):
            t = int(r.custom_id.rsplit("_", 1)[1])
            if r.result.type == "succeeded":
                msg = r.result.message
                u = {} if dry_run else BOT.usage_dict(msg)
                usd = ledger.actual(st["reserve_id"], model, u, True, custom_id=r.custom_id, dedupe=f"{batch_id}:{r.custom_id}")
                decisions[t] = decision_from_message(t, msg, usd)
            else:
                decisions[t] = {"t": t, "status": r.result.type, "reason": "", "weights": None, "usage": {}, "usd": 0.0}
    ledger.release(st["reserve_id"])
    return decisions


# ------------------------------------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--prompt-variant", default="v1_plain", choices=list(BOT.VARIANTS))
    ap.add_argument("--period", default="design", choices=["design", "control"])
    ap.add_argument("--mode", default="batch", choices=["batch", "sync"])
    ap.add_argument("--effort", default=None, choices=list(EFFORTS), help="default: low for Haiku/Sonnet, medium for Opus/Fable")
    ap.add_argument("--replicate", type=int, default=None, metavar="N",
                    help=f"axis 8b part A: run a FROZEN batch bot again as replicate N (1..{MAX_REPLICATE}); run directory and control "
                    "lock use the suffix __rN, never the original's; needs a frozen PREREGISTRATION-8b.md on the control")
    ap.add_argument("--reserve-out-tokens", type=int, default=None,
                    help="batch only: output tokens per request used for the spend reservation (default: max_tokens, the worst "
                         "case). Requests keep max_tokens. Declared in the preregistration when used.")
    ap.add_argument("--resume", action="store_true",
                    help="sync only: continue an interrupted run from decisions.partial.jsonl; decided bars are not called again")
    ap.add_argument("--spread", action="store_true",
                    help="print the original run and its replicates side by side (return spread) for this bot and period, then exit")
    ap.add_argument("--cap-usd", type=float, default=None, help="hard cap on the total spend ledger (max 160)")
    ap.add_argument("--dry-run", action="store_true", help="fake client, zero cost, no key needed")
    ap.add_argument("--estimate", action="store_true", help="print the cost table and exit (no model call)")
    ap.add_argument("--collect", action="store_true", help="collect the results of an already submitted batch")
    ap.add_argument("--pilot", action="store_true", help=f"sync, design window only, first --max-bars (default {PILOT_BARS}) bars, "
                    f"cap {PILOT_CAP_USD} USD, real API: prints tokens, stop_reason and cost per call; never touches the control")
    ap.add_argument("--max-bars", type=int, default=None, help="only the first N decisions (tests, pilot)")
    ap.add_argument("--list-reservations", action="store_true", help="print the open reservations of the ledger and exit")
    ap.add_argument("--release", metavar="RID", help="release one open reservation (after checking the console)")
    ap.add_argument("--release-stale", type=float, metavar="HOURS", help="release every open reservation older than HOURS")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n-random", type=int, default=REP.N_RANDOM)
    a = ap.parse_args()

    if a.estimate:
        rows = estimate()
        print_estimate(rows)
        print(f"\ntoken estimate: characters / {CHARS_PER_TOKEN}")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "estimate.json").write_text(json.dumps(rows, indent=1))
        return

    ledger = BUD.Ledger(DATA_DIR / "dryrun" / "spend.jsonl") if a.dry_run else BUD.Ledger()
    if a.list_reservations or a.release or a.release_stale is not None:
        if a.release:
            print("released" if ledger.release(a.release) else "not open (unknown id or already released)")
        if a.release_stale is not None:
            print("released:", ledger.release_stale(a.release_stale * 3600))
        for e in ledger.open_reservations():
            print(f"open  {e['key']}  {e['usd']:.4f} USD  ts={e['ts']}  {e.get('note', '')}")
        print("ledger:", ledger.totals())
        return

    model, effort0 = BOT.resolve_model(a.model)
    effort = a.effort or effort0
    if a.pilot:
        if a.period == "control" or a.collect:
            raise SystemExit("--pilot never touches the control and has nothing to collect")
        a.mode, a.period = "sync", "design"
        a.max_bars = a.max_bars or PILOT_BARS
        # the cap applies to the whole ledger: the pilot allowance (--cap-usd, at most PILOT_CAP_USD) is ADDED to what is spent
        a.cap_usd = ledger.totals()["total"] + (min(a.cap_usd, PILOT_CAP_USD) if a.cap_usd is not None else PILOT_CAP_USD)
    bid = bot_id(model, a.prompt_variant, effort, a.mode)
    if a.replicate is not None and not 1 <= a.replicate <= MAX_REPLICATE:
        raise SystemExit(f"--replicate must be 1..{MAX_REPLICATE}")
    if a.replicate is not None and a.pilot:
        raise SystemExit("--pilot and --replicate do not combine")
    if a.resume and (a.mode != "sync" or a.collect):
        raise SystemExit("--resume is for an interrupted sync run (batches use --collect)")
    lock_id = replicate_id(bid, a.replicate) if a.replicate else bid
    if a.spread:
        sub0 = "dryrun" if a.dry_run else "runs"
        runs = {"original": run_dir_for(DATA_DIR / sub0, bid, a.period)}
        runs.update({f"r{k}": run_dir_for(DATA_DIR / sub0, bid, a.period, k) for k in range(1, MAX_REPLICATE + 1)})
        reps = {k: json.loads((d / "report.json").read_text()) for k, d in runs.items() if (d / "report.json").exists()}
        if not reps:
            raise SystemExit("--spread: no report.json found for this bot and period")
        sp = REP.spread(reps)
        print(REP.spread_table(sp))
        (DATA_DIR / "spread").mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "spread" / f"{bid}__{a.period}.json").write_text(json.dumps(sp, indent=1))
        return
    prereg_commit = ""
    if a.period == "control":
        prereg_commit = control_gate(bid, a.collect or a.resume, a.replicate)
    if not a.dry_run and a.cap_usd is None:
        raise SystemExit("--cap-usd is required for a real run")

    s, e = BR.PERIODS[a.period]
    data, i0 = BR.load_data(s, e)
    b = BR.make_bars(data, i0)
    if a.period == "design":
        print("leak control: oldest candle read by the first decision:", dt_str(BR.check_leak_floor(data, b)))
    n = b.n - b.first if a.max_bars is None else min(a.max_bars, b.n - b.first)
    sub = "pilot" if a.pilot else ("dryrun" if a.dry_run else "runs")
    run_dir = run_dir_for(DATA_DIR / sub, bid, a.period, a.replicate)
    if a.replicate and run_dir == run_dir_for(DATA_DIR / sub, bid, a.period):
        raise SystemExit("a replicate must have its own run directory")
    run_dir.mkdir(parents=True, exist_ok=True)
    cap = a.cap_usd if a.cap_usd is not None else BUD.HARD_TOTAL_CAP
    client = BOT.FakeClient(a.seed + (a.replicate or 0)) if a.dry_run else BOT.real_client()
    batch = a.mode == "batch"
    print(f"bot {lock_id} | period {a.period} | {n} decisions | {'DRY-RUN' if a.dry_run else 'REAL'} | ledger {ledger.totals()}")

    lock_fn = None
    if a.period == "control" and not a.collect:
        if not (a.resume and control_ran(lock_id)):  # a resumed run already holds its lock
            lock_fn = lambda: take_control_lock(lock_id, prereg_commit, a.dry_run)  # noqa: E731

    if batch:
        batch_file = run_dir / "batch.json"
        if a.dry_run and not a.collect and batch_file.exists():
            batch_file.unlink()  # a fake batch lives only in memory: a stale dry-run file is meaningless
        if a.collect:
            decisions = collect_batch(client, ledger, run_dir, model, dry_run=a.dry_run, poll_s=0 if a.dry_run else 60)
        else:
            reqs = [{"custom_id": f"d_{t:04d}",
                     "params": BOT.build_params(model, effort, a.prompt_variant, BR.user_message(b, b.first + t, None))}
                    for t in range(n)]
            in_tok = int(np.mean([len(r["params"]["messages"][0]["content"]) for r in reqs]) / CHARS_PER_TOKEN
                         + len(BOT.VARIANTS[a.prompt_variant]) / CHARS_PER_TOKEN) + 300
            proj = BUD.projected_cost(model, in_tok, a.reserve_out_tokens or BOT.MAX_TOKENS, n, True)
            ids, rid = submit_batch(client, ledger, run_dir, f"{lock_id}:{a.period}", reqs, proj, cap, fake=a.dry_run, lock_fn=lock_fn)
            print(f"reserved {proj:.2f} USD (output tokens assumed {a.reserve_out_tokens or BOT.MAX_TOKENS} per request; request max_tokens {BOT.MAX_TOKENS}) of cap {cap:.2f}; submitted", ids)
            decisions = collect_batch(client, ledger, run_dir, model, dry_run=a.dry_run, poll_s=0 if a.dry_run else 60)
    else:
        def on_call(d: dict) -> None:
            if a.pilot:
                u = d["usage"]
                print(f"  call t={d['t']}: in {u.get('input_tokens')} out {u.get('output_tokens')} "
                      f"cache_read {u.get('cache_read_input_tokens')} cache_write {u.get('cache_creation_input_tokens')} | "
                      f"stop_reason {d['stop_reason']} | status {d['status']} | cost {d['usd']:.6f} USD")
        partial = run_dir / "decisions.partial.jsonl"
        if a.pilot or (a.dry_run and not a.resume):
            partial.unlink(missing_ok=True)  # pilot and dry-run: nothing worth keeping
        done = load_partial(partial, n)
        if done and not a.resume:
            raise SystemExit(f"{partial.name} holds {len(done)} paid decisions of an interrupted run: use --resume (never restart "
                             "a paid run from scratch)")
        if not a.pilot and not a.dry_run and (run_dir / "decisions.jsonl").exists():
            raise SystemExit("decisions.jsonl already exists for this bot and period: a finished paid run is never overwritten "
                             "or resumed")
        if done:
            # drop any torn last line before appending, so a resumed call never lands on a corrupt fragment
            partial.write_text("".join(json.dumps(done[t]) + "\n" for t in sorted(done)))
        if done:
            print(f"resuming: {len(done)} of {n} decisions already made, {n - len(done)} calls left; open reservations from the "
                  "interrupted call (if any) stay counted against the cap, see --list-reservations")
        decisions = sync_loop(client, ledger, model, effort, a.prompt_variant, b, n, lock_id, a.period, cap, a.dry_run,
                              lock_fn=lock_fn, on_call=on_call, partial_path=partial, done=done)

    statuses: dict[str, int] = {}
    for d in decisions.values():
        statuses[d["status"]] = statuses.get(d["status"], 0) + 1
    spend = round(sum(d["usd"] for d in decisions.values()), 6)
    (run_dir / "decisions.jsonl").write_text("\n".join(json.dumps(decisions[t]) for t in sorted(decisions)) + "\n")

    if a.pilot:
        ok = statuses.get("ok", 0)
        print(f"PILOT: {len(decisions)} calls, statuses {statuses}, total cost {spend:.6f} USD; effort '{effort}' and the JSON "
              f"schema were accepted by the API ({ok} schema-valid answers); max_tokens truncations {statuses.get('max_tokens', 0)}")
        print("ledger:", ledger.totals())
        return

    # assemble the target weights: an invalid, refused, truncated or missing decision holds the previous weights
    W = np.zeros((n, 6))
    prev = np.zeros(6)
    for t in range(n):
        d = decisions.get(t)
        if d and d["weights"] is not None:
            prev = np.array(d["weights"])
        W[t] = prev
    rep = REP.evaluate_bot(data, b, i0, W, seed=a.seed, n_random=a.n_random)
    out_tok = [d["usage"].get("output_tokens", 0) for d in decisions.values() if d.get("usage")]
    rep.update({"bot_id": lock_id, "replicate": a.replicate, "period": a.period, "decisions": n, "statuses": statuses,
                "truncations": statuses.get("max_tokens", 0), "max_tokens": BOT.MAX_TOKENS,
                "output_tokens_max": max(out_tok) if out_tok else 0,
                "output_tokens_mean": round(float(np.mean(out_tok)), 1) if out_tok else 0,
                "spend_usd": spend, "dry_run": a.dry_run})
    (run_dir / "report.json").write_text(json.dumps(rep, indent=1, default=float))
    print(REP.table(rep))
    print("criteria:", rep["criteria"], "| all pass:", rep["all_pass"])
    print("ledger:", ledger.totals(), "| output:", run_dir)


def dt_str(ts: int) -> str:
    import datetime as dt

    return dt.datetime.fromtimestamp(ts, BR.DT).strftime("%Y-%m-%d %H:%M UTC")


if __name__ == "__main__":
    main()
