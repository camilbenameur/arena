#!/usr/bin/env python
"""Axis 9 harness: Claude as a researcher. One long session of claude-fable-5-2 with the server-side code execution tool on
the 4-hour design bars (CSV upload). It proposes and tests up to 15 candidate rules and hands back one frozen rule.

  python docs/lead/axis-09-llm-researcher/research.py --print-brief            # no network
  python docs/lead/axis-09-llm-researcher/research.py --smoke --model opus     # one tiny real call (cap 0.30 USD)
  python docs/lead/axis-09-llm-researcher/research.py --run --model opus --session-id s01   # one axis-9b research session

Axis 9 (one Fable session) is done and committed. Axis 9b runs a population of independent sessions with the same brief:
each writes frozen_rule.py and trials_by_model.md under sessions/<model>-<id>/ (the axis-9 files at the top stay untouched)
and its transcript under the data directory. Budget per session 3 USD, 30 USD for the whole 9b on the axis-09 ledger.

Money: every call reserves its worst case in the axis-8 ledger class (budget.Ledger) before it is made and is settled with
the real usage; container time of the code execution tool is booked on top (assumed 0.05 USD per container-hour, 5-minute
minimum per call, an upper bound of what is billed). Cap 28 USD for the axis, and the sum with the axis-8 ledger never
passes the shared hard total. The API key is read only through arena.deciders.llm.read_api_key() and never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import common as C  # noqa: E402

MODELS = {"fable": "claude-fable-5-2", "opus": "claude-opus-5-5"}
MODEL = MODELS["fable"]
AXIS_CAP_USD = 28.0            # axis 9 (done)
AXIS9_PRIOR_USD = 1.23         # settled spend of axis 9 on the axis-09 ledger before axis 9b (1.222, rounded up)
AXIS9B_CAP_USD = 30.0          # axis 9b total, on the axis-09 ledger
SESSION_CAP_USD = 3.0          # per research session
SHARED_CAP_USD = 158.0         # axis-08 ledger + axis-09 ledger, hard
MIN_OUT_TOKENS = 6000          # a call is not made with less room than this for its output
SMOKE_CAP_USD = 0.30
CONTAINER_USD_PER_HOUR = 0.05
CHARS_PER_TOKEN = 3.0  # conservative for code and tables
MAX_TRIALS = 15
CODE_TOOL = {"type": "code_execution_20260521", "name": "code_execution"}
M_RULE, M_LOG, M_END = "=====FROZEN_RULE_PY=====", "=====TRIALS_LOG_MD=====", "=====END====="


# ------------------------------------------------------------------------------------------------ brief


def _fmt(r: dict) -> str:
    m = ", ".join(f"{k} {v:+.1f}%" for k, v in r["months_pct"].items())
    return (f"return {r['return_pct']:+.1f}%, max drawdown {r['max_dd_pct']:.1f}%, Sharpe {r['sharpe']:.2f}, "
            f"turnover {float(r['turnover_x']):.0f}x equity, months: {m}")


def build_brief(ref: dict) -> str:
    return f"""You are acting as a quantitative RESEARCHER, not a trader. Your job is to find, if one exists, a trading rule that
will keep working on data you have not seen, and to hand back exactly ONE frozen rule. An honest "I found nothing that
holds" is an acceptable and valuable result; an overfitted rule is not.

# Data (uploaded to your code execution sandbox as {C.CSV_NAME}, plus a helper module sandbox_backtest.py)

Find them with `find / -name {C.CSV_NAME} 2>/dev/null` (the container input directory). Load with
`df = pd.read_csv(path, parse_dates=["ts"])`. Long format, one row per (4-hour bar, ticker), sorted by ts then ticker.
Columns: ts (UTC, the bar OPEN time; the bar is complete and known only 4 hours later), ticker (BTC, ETH, SOL, XRP, LTC,
LINK: six USD-margined perpetual futures), open, high, low, close, volume (base asset quantity in the bar), funding (sum
of the hourly relative funding rates inside the bar; positive means longs pay shorts, negative means shorts pay longs).
Coverage: 2026-07-01 00:00 to 2026-09-30 20:00, 552 bars per ticker, 3312 rows. This is the DESIGN period: all you will ever see.
It is a single market regime of about three months; the statistical power is low. Treat every apparent edge with suspicion.
Do not use the network from the sandbox (no downloads, no pip install, no web or API requests): work only with the two
uploaded files. Any outside market data would void the experiment.

# What the rule is

A self-contained Python function `targets(df)` using only numpy and pandas (standard library allowed), no file or network
access, deterministic. Input: a DataFrame with exactly the columns above (same format as the CSV; it may contain MORE
rows than you see, later bars appended, so never normalise with full-sample statistics and never hard-code dates).
Output: a DataFrame indexed by the unique bar times `ts` (sorted, one row per bar), columns BTC, ETH, SOL, XRP, LTC, LINK.
The value in row t is the target weight to hold from the close of bar t until the next decision, as a multiple of
equity/6 per contract, a float in [-2, 2] (long positive, short negative; 0 = flat). No NaN: use 0 during warm-up.

Causality is mandatory and will be checked mechanically: row t may use only rows with ts <= t. The checker recomputes the
rule on data truncated after bar t and requires the same row t, with zero gap, for many t. Any use of future rows (shift(-k),
centered windows, full-sample means or ranks, sorting by future values) fails the rule.

# Cost model (the final judge is a minute-level simulator you do not have)

- Decisions at the close of each 4-hour bar; orders fill at the next minute's open.
- Each side costs 7 bp fee + 5 bp slippage on the traded notional: 24 bp per round trip.
- Hourly funding is charged on the open position (the `funding` column is the per-bar sum of those hourly rates; longs pay
  when positive, shorts receive).
- A contract is re-traded only when its current position differs from the target by more than 5% of equity
  (0.3 weight units); a target of exactly 0 closes any open position. Gross exposure is capped at 10x equity (not binding here).
- sandbox_backtest.py gives `simulate(df, W)` (W: your weights DataFrame indexed by ts) that approximates this at bar level.
  Use it for all your tests, so every trial is scored the same way. It is close to the real simulator but not identical.

# Reference results on the design period (same simulator as the final judge)

- Basket, 1x (equal-weight buy and hold of the six contracts): {_fmt(ref['basket_1x'])}
- Trend engine 1x (EMA crossover on 4-hour closes, volatility targeting, long/short): {_fmt(ref['trend_1x'])}
- Trend engine 2x (the same at double size): {_fmt(ref['trend_2x'])}

The basket gains because the design period trended up; a rule that is merely long is not a finding. The judge will compare
your rule with the trend engine at 2x, with the basket, and with random weights that have the same turnover as your rule.

# Method (follow it)

1. Before you look at any result, write down up to {MAX_TRIALS} candidate rules, EACH with an economic rationale: who is on the
   other side, which constraint or behaviour creates the edge, why it should persist and why costs of 24 bp per round trip do
   not eat it. Rules without a mechanism are not allowed.
2. Test them in your sandbox on the CSV. {MAX_TRIALS} trials is a hard limit that counts EVERY variant you evaluate, including
   parameter tweaks and fixes of a failed idea. Keep a trial log (idea, rationale, parameters, result, verdict), including
   every failure. A log with fewer entries than the number of variants you really ran is a protocol violation.
3. Guard against overfitting: the rule will be run exactly once on an unseen later period, and you will never see that
   period. Prefer few parameters set from the economics, not by search; check stability under small parameter changes; use
   a time split inside the design period (for example choose on the first part, confirm on the rest) and report the
   split results; look at behaviour per ticker and per month, at turnover and at the cost it implies; be sceptical of
   anything whose return comes from one ticker, one month or one trade. State the expected size of the effect after costs.
4. Choose ONE rule. If no candidate holds up under your own checks, say so, and hand back the most defensible simple rule
   anyway, labelled as "no robust edge found" in the log.

# Budget

You have a hard cost budget; the session is stopped when it is spent. Keep each sandbox run short, and stop experimenting
well before you run out: reserve enough effort to write the final answer.

# Final answer format (exactly this, in your last message, nothing after the end marker)

{M_RULE}
<the complete python source of frozen_rule.py: imports, helper functions, and `def targets(df)`; no markdown fences>
{M_LOG}
<markdown: a table or list of every trial (number, idea, economic rationale, parameters, design result, verdict), the time-split
results, the chosen rule and why, its known weaknesses, and what you expect it to do out of sample, honestly>
{M_END}
"""


# ------------------------------------------------------------------------------------------------ money


def projected_usd(model: str, messages: list, system: str, max_tokens: int) -> float:
    chars = len(system) + len(json.dumps(messages, default=lambda o: getattr(o, "model_dump", lambda **k: str(o))(mode="json")))
    return C.BUD.projected_cost(model, int(chars / CHARS_PER_TOKEN) + 2000, max_tokens, 1, False)


class AxisBudget(C.BUD.BudgetExceeded):
    """The axis-09 ledger cap or the shared total with the axis-08 ledger would be passed (stops the whole population)."""


class Books:
    """The ledgers one call is booked on: a list of (scope, Ledger, cap) plus the axis-09 ledger used for the shared total.
    Reserving takes the worst case on every ledger (all or none); settling books the real usage on every ledger."""

    def __init__(self, items: list, shared):
        self.items, self.shared = items, shared

    def room(self) -> tuple[float, str]:
        """USD still available for one call and which limit binds ("axis" or "session"): the smallest margin over every
        ledger cap and the shared total."""
        other = C.BUD.Ledger(C.BUD.LEDGER).totals()["total"]
        m = [(SHARED_CAP_USD - other - self.shared.totals()["total"], "axis")]
        m += [(cap - led.totals()["total"], scope) for scope, led, cap in self.items]
        return min(m, key=lambda x: x[0])

    def reserve(self, key: str, usd: float) -> list:
        other = C.BUD.Ledger(C.BUD.LEDGER).totals()["total"]
        mine = self.shared.totals()["total"]
        if other + mine + usd > SHARED_CAP_USD:
            raise AxisBudget(f"refused: axis-8 ledger {other:.2f} + axis-9 {mine:.2f} + {usd:.2f} > shared total {SHARED_CAP_USD}")
        held = []
        for scope, led, cap in self.items:
            try:
                held.append((led, led.reserve(key, usd, cap)))
            except C.BUD.BudgetExceeded as ex:
                for l2, r2 in held:
                    l2.release(r2)
                raise (AxisBudget if scope == "axis" else C.BUD.BudgetExceeded)(f"{scope} ledger: {ex}") from None
        return held

    def release(self, held: list) -> None:
        for led, rid in held:
            led.release(rid)

    def settle(self, held: list, model: str, msg, elapsed_s: float) -> float:
        usd = 0.0
        cont = round(CONTAINER_USD_PER_HOUR * max(elapsed_s, 300.0) / 3600.0, 6)
        for led, rid in held:
            usd = led.actual(rid, model, usage_dict(msg), False, custom_id=rid, dedupe=rid)
            with led._locked():  # container time of the code execution tool, booked on top of the tokens
                led._append({"kind": "actual", "key": rid + ":container", "usd": cont, "note": "code execution container time (upper bound)"})
            led.release(rid)
        return usd + cont


def usage_dict(msg) -> dict:
    u = msg.usage
    return {k: int(getattr(u, k, 0) or 0) for k in
            ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}


# ------------------------------------------------------------------------------------------------ client and transcript


def real_client():
    import anthropic
    from arena.deciders.llm import read_api_key

    key = read_api_key()
    if not key:
        raise SystemExit("no API key available (arena.deciders.llm.read_api_key() returned None)")
    os.environ.pop("ANTHROPIC_BASE_URL", None)
    return anthropic.Anthropic(api_key=key, base_url="https://api.anthropic.com", max_retries=0, timeout=3600.0)


def _jsonable(x):
    return x.model_dump(mode="json") if hasattr(x, "model_dump") else x


def render_md(turn: int, msg, usd: float) -> str:
    out = [f"\n## Response {turn} (stop_reason {msg.stop_reason}, cost {usd:.4f} USD)\n"]
    for b in msg.content:
        d = _jsonable(b)
        t = d.get("type")
        if t == "text":
            out.append(d["text"])
        elif t == "thinking":
            out.append(f"> thinking summary: {d.get('thinking', '')}")
        elif t == "server_tool_use":
            inp = d.get("input", {})
            code = inp.get("command") or inp.get("file_text") or inp.get("code") or json.dumps(inp, indent=1)
            out.append(f"**{d.get('name')}**\n```\n{code}\n```")
        elif t and t.endswith("_tool_result"):
            out.append(f"**{t}**\n```\n{json.dumps(d.get('content'), indent=1)[:8000]}\n```")
        else:
            out.append(f"[{t}]")
    return "\n\n".join(out) + "\n"


def final_text(msg) -> str:
    return "\n".join(b.text for b in msg.content if b.type == "text")


def parse_deliverable(text: str) -> tuple[str, str] | None:
    m = re.search(re.escape(M_RULE) + r"\s*(.*?)\s*" + re.escape(M_LOG) + r"\s*(.*?)\s*" + re.escape(M_END), text, re.S)
    if not m:
        return None
    code = re.sub(r"^```(?:python)?\n|\n```$", "", m.group(1).strip())
    return code.strip() + "\n", m.group(2).strip() + "\n"


# ------------------------------------------------------------------------------------------------ session


def fit_max_tokens(books: Books, params: dict) -> None:
    """Worst-case reservation stays (input estimate + max_tokens of output), but max_tokens is lowered to what the remaining
    budget can cover; below MIN_OUT_TOKENS the call is not made (a budget stop)."""
    model, msgs, system = params["model"], params["messages"], params.get("system", "")
    room, scope = books.room()
    if projected_usd(model, msgs, system, params["max_tokens"]) <= room:
        return
    base = projected_usd(model, msgs, system, 0)
    fit = int(0.98 * (room - base) / C.BUD.PRICES[model].out * 1e6)
    if fit < MIN_OUT_TOKENS:
        raise (AxisBudget if scope == "axis" else C.BUD.BudgetExceeded)(
            f"only {max(room, 0):.2f} USD left on the {scope} budget, input alone is about {base:.2f}")
    params["max_tokens"] = min(params["max_tokens"], fit)


def call(client, books: Books, key: str, params: dict, elapsed: dict):
    """One streamed call. Worst case reserved first. 429: reservation released; 5xx or unknown errors keep the reservation
    open (the call may have been billed) and stop the session."""
    import bot as BOT  # axis 8: classify_error

    fit_max_tokens(books, params)
    proj = projected_usd(params["model"], params["messages"], params.get("system", ""), params["max_tokens"])
    held = books.reserve(key, proj)
    t0 = time.time()
    try:
        with client.messages.stream(**params) as s:
            msg = s.get_final_message()
    except Exception as ex:  # noqa: BLE001
        kind = BOT.classify_error(ex)
        if kind in ("retry_clean", "definite"):
            books.release(held)
        raise
    usd = books.settle(held, params["model"], msg, time.time() - t0)
    elapsed["usd"] = elapsed.get("usd", 0.0) + usd
    return msg, usd


def run_session(client, brief: str, file_ids: list[str], *, cap: float, effort: str, max_tokens: int, max_turns: int,
                out_dir: Path, tag: str, require_deliverable: bool = True, model: str = MODEL, books: Books | None = None) -> dict:
    if books is None:  # axis-9 style: one ledger in out_dir, which is also the one the shared total is computed on
        led = C.BUD.Ledger(out_dir / "spend.jsonl")
        books = Books([("axis", led, cap)], led)
    content = [{"type": "text", "text": brief}] + [{"type": "container_upload", "file_id": f} for f in file_ids]
    messages: list = [{"role": "user", "content": content}]
    container = None
    out_dir.mkdir(parents=True, exist_ok=True)
    tj = (out_dir / f"transcript_{tag}.jsonl").open("a")
    md = out_dir / f"transcript_{tag}.md"
    md.write_text(f"# Axis 9 transcript ({tag}, {model})\n\n## Brief\n\n{brief}\n")
    spent, nudges = {"usd": 0.0}, 0
    result = {"stop": "max_turns", "deliverable": None, "usd": 0.0, "turns": 0}
    for turn in range(1, max_turns + 1):
        params = dict(model=model, max_tokens=max_tokens, messages=messages, tools=[CODE_TOOL],
                      thinking={"type": "adaptive", "display": "summarized"}, output_config={"effort": effort},
                      cache_control={"type": "ephemeral"})
        if container:
            params["container"] = container
        try:
            msg, usd = call(client, books, f"{tag}:t{turn}", params, spent)
        except C.BUD.BudgetExceeded as ex:
            result["stop"] = f"budget[{'axis' if isinstance(ex, AxisBudget) else 'session'}]: {ex}"
            break
        result.update(turns=turn, usd=spent["usd"])
        if getattr(msg, "container", None) is not None:
            container = msg.container.id
        tj.write(json.dumps({"turn": turn, "stop_reason": msg.stop_reason, "stop_details": _jsonable(msg.stop_details),
                             "usage": _jsonable(msg.usage), "usd": usd, "container": container,
                             "content": [_jsonable(b) for b in msg.content]}) + "\n")
        tj.flush()
        with md.open("a") as f:
            f.write(render_md(turn, msg, usd))
        messages.append({"role": "assistant", "content": msg.content})
        sr = msg.stop_reason
        if sr == "pause_turn":
            continue
        if sr == "refusal":
            result["stop"] = f"refusal: {_jsonable(msg.stop_details)}"
            break
        if sr in ("end_turn", "max_tokens", "stop_sequence", "model_context_window_exceeded"):
            got = parse_deliverable(final_text(msg))
            if not require_deliverable and sr == "end_turn":
                result.update(stop="done", answer=final_text(msg))
                break
            if got:
                result.update(stop="done", deliverable=got)
                break
            if sr == "model_context_window_exceeded" or nudges >= 3:
                result["stop"] = f"no deliverable after {sr}"
                break
            nudges += 1
            ask = ("Continue." if sr == "max_tokens" else
                   f"Hand back your final answer now in the exact format: {M_RULE}, the python source, {M_LOG}, the markdown log, {M_END}.")
            messages.append({"role": "user", "content": ask})
            continue
        result["stop"] = f"unexpected stop_reason {sr}"
        break
    tj.close()
    return result


def write_outputs(deliverable: tuple[str, str], overwrite: bool, dest: Path | None = None) -> None:
    code, log = deliverable
    dest = HERE if dest is None else dest
    dest.mkdir(parents=True, exist_ok=True)
    rule, trials = dest / "frozen_rule.py", dest / "trials_by_model.md"
    if (rule.exists() or trials.exists()) and not overwrite:
        raise SystemExit("frozen_rule.py or trials_by_model.md already exists: refusing to overwrite (use --overwrite)")
    C.assert_design_only(code, "frozen_rule.py")
    rule.write_text(code)
    trials.write_text("# Trial log written by the model (verbatim)\n\n" + log)


# ------------------------------------------------------------------------------------------------ CLI


def design_reference(out_dir: Path) -> dict:
    f = out_dir / "design_reference.json"
    if f.exists():
        return json.loads(f.read_text())
    ref = C.reference_design()
    f.write_text(json.dumps(ref, indent=1, default=float))
    return json.loads(f.read_text())


def upload_all(client, files: dict[str, bytes]) -> list[str]:
    ids = []
    for name, data in files.items():
        C.assert_design_only(data.decode(), name)
        meta = client.files.upload(file=(name, data, "text/plain"), expires_in_seconds=86400)
        ids.append(meta.id)
    return ids


def session_books(tdir: Path, data_dir: Path, session_cap: float, axis_cap: float) -> Books:
    axis = C.BUD.Ledger(data_dir / "spend.jsonl")  # the axis-09 ledger, shared by every 9b session
    return Books([("session", C.BUD.Ledger(tdir / "spend.jsonl"), session_cap), ("axis", axis, axis_cap)], axis)


def execute_session(client, model_key: str, sid: str, *, files: dict, brief: str, session_cap: float = SESSION_CAP_USD,
                    axis_cap: float = AXIS9_PRIOR_USD + AXIS9B_CAP_USD, effort: str = "high", max_tokens: int = 64000,
                    max_turns: int = 60, repo_dir: Path | None = None, data_dir: Path | None = None) -> dict:
    """One independent axis-9b session, start to finish: upload, research loop, outputs under sessions/<model>-<id>/, outcome.
    Refuses a session whose directory already exists. Returns the outcome record (also written next to the outputs)."""
    if model_key not in MODELS:
        raise SystemExit(f"unknown model {model_key}: use one of {sorted(MODELS)}")
    name = f"{model_key}-{sid}"
    code_dir, tdir = C.session_dirs(name, HERE if repo_dir is None else repo_dir, C.DATA_DIR if data_dir is None else data_dir)
    data_dir = C.DATA_DIR if data_dir is None else data_dir
    if code_dir.exists() or tdir.exists():
        raise SystemExit(f"session {name} already exists: refusing to run it again")
    tdir.mkdir(parents=True)
    books = session_books(tdir, data_dir, session_cap, axis_cap)
    out = {"session": name, "model": MODELS[model_key], "effort": effort, "rule_written": False, "usd": 0.0, "stop": "?", "turns": 0,
           "halt": False}
    ids: list[str] = []
    res: dict = {}
    try:
        ids = upload_all(client, files)
        res = run_session(client, brief, ids, cap=session_cap, effort=effort, max_tokens=max_tokens, max_turns=max_turns,
                          out_dir=tdir, tag="full", model=MODELS[model_key], books=books)
        out.update(stop=res["stop"], turns=res["turns"])
    except Exception as ex:  # noqa: BLE001  (an ambiguous API error keeps its reservation open: stop the population)
        out.update(stop=f"error: {type(ex).__name__}: {str(ex)[:200]}", halt=True)
    finally:
        for i in ids:
            try:
                client.files.delete(i)
            except Exception:  # noqa: BLE001
                pass
    if res.get("deliverable"):
        try:
            write_outputs(res["deliverable"], False, code_dir)
            out["rule_written"] = True
        except (ValueError, SystemExit) as ex:
            (tdir / "rejected_deliverable.txt").write_text(res["deliverable"][0] + "\n\n" + res["deliverable"][1])
            out["stop"] = f"deliverable rejected: {ex}"
    st = books.items[0][1].totals()
    out.update(usd=round(st["settled"], 4), open_reservation_usd=round(st["reserved"], 4))
    if out["stop"].startswith("budget[axis]"):
        out["halt"] = True
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "outcome.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    with (data_dir / "population_9b.jsonl").open("a") as f:
        f.write(json.dumps({"ts": int(time.time()), **out}) + "\n")
    return out


def population_files(text: str, helper: str) -> dict:
    return {C.CSV_NAME: text.encode(), "sandbox_backtest.py": helper.encode()}


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--print-brief", action="store_true")
    g.add_argument("--smoke", action="store_true")
    g.add_argument("--run", action="store_true", help="one axis-9b session; needs --session-id")
    ap.add_argument("--model", choices=sorted(MODELS), default="fable")
    ap.add_argument("--session-id", default=None, help="id of the session, letters/digits/_/- (directory sessions/<model>-<id>)")
    ap.add_argument("--cap-usd", type=float, default=None, help="per-session cap (default 3 USD) or smoke cap (default 0.30 USD)")
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--max-tokens", type=int, default=64000)
    ap.add_argument("--max-turns", type=int, default=60)
    a = ap.parse_args()
    data_dir = C.DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    text, df = C.design_csv()
    helper = (HERE / "sandbox_backtest.py").read_text()
    ref = design_reference(data_dir)
    brief = build_brief(ref)
    C.assert_design_only(brief, "brief")
    if a.print_brief:
        print(brief)
        print(f"[csv {len(text)} bytes, {len(df)} rows, ts {df['ts'].min()} .. {df['ts'].max()}]")
        return
    if a.run and not a.session_id:
        raise SystemExit("--run needs --session-id (the axis-9 session is done; the files at the top are never rewritten)")
    cap = a.cap_usd if a.cap_usd is not None else (SMOKE_CAP_USD if a.smoke else SESSION_CAP_USD)
    if cap > (SMOKE_CAP_USD if a.smoke else SESSION_CAP_USD):
        raise SystemExit(f"cap {cap} above the {'smoke' if a.smoke else 'per-session'} cap")
    client = real_client()
    if a.smoke:
        prompt = (f"Use code execution: find {C.CSV_NAME} in the container input directory, load it with pandas "
                  f"(parse_dates=['ts']), and print df.shape, the min and the max of df['ts']. Then answer in one line "
                  f"with those three values. Nothing else.")
        C.assert_design_only(prompt, "smoke prompt")
        tdir = data_dir / "smoke" / a.model
        tdir.mkdir(parents=True, exist_ok=True)
        books = session_books(tdir, data_dir, cap, AXIS9_PRIOR_USD + AXIS9B_CAP_USD)
        ids = upload_all(client, {C.CSV_NAME: text.encode()})
        try:
            res = run_session(client, prompt, ids, cap=cap, effort="low", max_tokens=4000, max_turns=6, out_dir=tdir, tag="smoke",
                              require_deliverable=False, model=MODELS[a.model], books=books)
        finally:
            for i in ids:
                try:
                    client.files.delete(i)
                except Exception:  # noqa: BLE001
                    pass
        print(json.dumps({k: v for k, v in res.items() if k != "deliverable"}, default=str))
        print("smoke ledger", books.items[0][1].totals())
        return
    out = execute_session(client, a.model, a.session_id, files=population_files(text, helper), brief=brief, session_cap=cap,
                          effort=a.effort, max_tokens=a.max_tokens, max_turns=a.max_turns)
    print(json.dumps(out))
    print("axis-09 ledger", C.BUD.Ledger(data_dir / "spend.jsonl").totals())


if __name__ == "__main__":
    main()
