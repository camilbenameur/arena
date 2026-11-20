"""Tests of the dashboard generator (arena/site) on a synthetic journal of 60 cycles."""

from __future__ import annotations

import dataclasses
import html
import json
import re
from pathlib import Path
from unittest import mock

import pytest

from arena.config import load_config
from arena.journal import Journal
from arena.ledger import equity_ueur, replay
from arena.risk.policy import load_policy
from arena.site import build
from arena.types import QTY_SCALE, ceil_div, notional_ueur

ROOT = Path(__file__).resolve().parent.parent
CYCLE_S = 14_400
T0 = 1_789_000_000 - (1_789_000_000 % CYCLE_S)
N_CYCLES = 60
SYMBOLS = ["BTC/EUR", "ETH/EUR", "SOL/EUR", "XRP/EUR", "LINK/EUR", "LTC/EUR"]
BASE_PX = {"BTC/EUR": 80_000, "ETH/EUR": 3_000, "SOL/EUR": 150, "XRP/EUR": 2, "LINK/EUR": 15, "LTC/EUR": 90}
LLMS = ["llm:claude-haiku-5-5", "llm:claude-sonnet-5-5", "llm:claude-opus-5-5"]
BENCHMARKS = ["benchmark:basket", "benchmark:6040", "benchmark:e0065", "benchmark:random"]
CAPITAL = 1_000_000_000
INJECTION = "old <script>alert('x')</script> & <b>bold</b>"
SECRET_RECENT = "SECRET_RECENT_42"
NOW = T0 + (N_CYCLES - 1) * CYCLE_S + 3_600  # 1 h after the last cycle


def _mid(sym: str, i: int) -> tuple[int, int]:
    drift = 1_000_000 * BASE_PX[sym] * (1000 + ((i * 7 + len(sym) * 3) % 23) - 11 + i // 5) // 1000
    return drift - drift // 2000, drift + drift // 2000  # bid, ask


def _fill(j: Journal, pf: str, sym: str, side: str, qty: int, price: int, ts: int, oid: str, reason="intent"):
    notional = notional_ueur(qty, price, round_up=True)
    fee = ceil_div(notional * 50, 10_000)
    j.append("fill", {"order_id": oid, "portfolio": pf, "symbol": sym, "side": side, "qty": qty,
                      "price_ueur": price, "fee_ueur": fee, "ts": ts, "venue_mode": "paper",
                      "fill_model_version": "pessimistic-v1", "reason": reason}, ts)  # fmt: skip


def _intent(j: Journal, pf: str, cyc: int, sym: str, side: str, size_bp: int, iid: str, ts: int, approved=True,
            reasons=(), qty=0):
    j.append("intent", {"intent_id": iid, "portfolio": pf, "cycle": cyc, "symbol": sym, "side": side,
                        "size_bp": size_bp, "stop_bp": 500 if side == "buy" else None,
                        "expected_move_bp": 900 if side == "buy" else None}, ts)  # fmt: skip
    j.append("risk_verdict", {"intent_id": iid, "approved": approved, "reasons": list(reasons), "qty": qty,
                              "reserved_ueur": 0, "policy_sha256": "p"}, ts)  # fmt: skip


FABLE = "llm:claude-fable-5-2"
FABLE_START = 40  # opening cycle of the fifth model, which arrived midway
FABLE_REASON = "FABLE_REASON: bitcoin momentum justifies a small position"


WAKEUP_CYCLE = 50  # the wake-up happens 2 h after this cycle
WAKEUP_REASON = "WAKEUP_REASON: ether is slipping, I am buying the dip"
SEASON_A = 40  # starting cycle of the synthetic season
WAIVER = "WAIVER_TEST: fix of an outlier price"
XRP_RAW_ABSURD = 987_654_321  # raw quote rejected: must never become a displayed price
LINK_WAKEUP_ABSURD = 777_777_777_777  # wakeup_quote: ignored for the marks


def synthetic_journal(path: Path, with_fable: bool = False, watch: bool = False, season_a: int | None = None,
                      retired_fable_after: int | None = None) -> Journal:
    """`retired_fable_after`: Fable (`with_fable`) is retired at the end of this cycle, positions sold at the bid
    (`portfolio_retired`), then has no more equity."""
    with mock.patch("arena.journal.os.fsync"):  # 3,000 writes: without fsync the test stays fast
        return _synthetic_journal(path, with_fable, watch, season_a, retired_fable_after)


def _bids(i: int) -> dict[str, int]:
    return {s: _mid(s, i)[0] for s in SYMBOLS}


def _watch(j: Journal, tick: int, i: int, *, raw: dict | None = None, rejected: dict | None = None, rise: int = 0,
            wakeup: dict | None = None) -> None:
    states = replay(j.iter_events())
    q = {s: list(_mid(s, i)) for s in SYMBOLS}
    if rise:
        q = {s: [b * (10_000 + rise) // 10_000, a * (10_000 + rise) // 10_000] for s, (b, a) in q.items()}
    bids = {s: b for s, (b, _a) in q.items()}
    accepted = {s: v for s, v in q.items() if s not in (rejected or {})}
    j.append("watch", {
        "tick": tick, "quotes": accepted, "raw_quotes": {**q, **(raw or {})}, "rejected": rejected or {},
        "confirmed": [], "variations_bp": {s: 0 for s in SYMBOLS}, "closes_1m": {s: (b + a) // 2 for s, (b, a) in q.items()},
        "equity": {pf: equity_ueur(st, bids) for pf, st in states.items()}, "stops": [], "wakeup": wakeup,
        "refused": None, "freeze": False,
    }, tick)  # fmt: skip


def _synthetic_journal(path: Path, with_fable: bool = False, watch: bool = False, season_a: int | None = None,
                       retired_fable_after: int | None = None) -> Journal:
    j = Journal(path)
    j.append("config_loaded", {"policy_sha256": "a" * 64, "config_sha256": "b" * 64, "prompt_sha256": "c" * 64,
                               "git_head": "d" * 40}, T0 - 600)  # fmt: skip
    for pf in LLMS + BENCHMARKS:
        j.append("portfolio_opened", {"portfolio": pf, "kind": "llm" if pf.startswith("llm") else "benchmark",
                                      "capital_ueur": CAPITAL, "venue_mode": "paper"}, T0 - 500)  # fmt: skip
    for i in range(N_CYCLES):
        c = T0 + i * CYCLE_S
        ts = c + 300
        j.append("cycle_started", {"cycle": c}, c)
        if season_a is not None and i == season_a:
            states = replay(j.iter_events())
            j.append("season_started", {"number": 1, "name": "Season test", "cycle": c, "planned_cycle_end": c + 56 * 86_400,
                                      "start_ts": c + 300, "duration_days": 56, "config_sha256": "b" * 64,
                                      "policy_sha256": "a" * 64, "prompt_sha256": "c" * 64, "code_sha256": "e" * 64,
                                      "git_head": "d" * 40, "claude_cli_version": None,
                                      "portfolios": LLMS + BENCHMARKS}, c + 2)  # fmt: skip
            j.append("season_reference", {"number": 1, "cycle": c, "equity": {
                pf: equity_ueur(states[pf], _bids(i)) for pf in LLMS + BENCHMARKS}}, c + 3)  # fmt: skip
        if season_a is not None and i == season_a + 2:
            h = {"config_sha256": "b" * 64, "policy_sha256": "a" * 64, "prompt_sha256": "c" * 64, "code_sha256": "e" * 64}
            j.append("season_waiver", {"number": 1, "reason": WAIVER, "hashes_before": h,
                                           "hashes_after": {**h, "code_sha256": "f" * 64}}, c + 2)  # fmt: skip
        if with_fable and i == FABLE_START:
            j.append("portfolio_opened", {"portfolio": FABLE, "kind": "llm", "capital_ueur": CAPITAL,
                                          "venue_mode": "paper"}, c + 1)  # fmt: skip
        for sym in SYMBOLS:
            bid, ask = _mid(sym, i)
            j.append("quote", {"symbol": sym, "ts": ts, "bid": bid, "ask": ask}, ts)
            lo, hi = _mid(sym, i - 1)[0], _mid(sym, i)[1]
            j.append("bar", {"symbol": sym, "interval_s": CYCLE_S, "ts": c - CYCLE_S, "open": lo, "high": hi + 1,
                             "low": lo - 1, "close": (bid + ask) // 2, "volume": 100 * QTY_SCALE}, ts)  # fmt: skip
        px_btc = _mid("BTC/EUR", i)[1] * 10_005 // 10_000
        qty100 = 100_000_000 * QTY_SCALE // px_btc  # ~100 EUR of BTC
        # Benchmarks: basket and 60/40 buy at cycle 0.
        if i == 0:
            for k, sym in enumerate(SYMBOLS):
                px = _mid(sym, i)[1] * 10_005 // 10_000
                q = 150_000_000 * QTY_SCALE // px
                _intent(j, "benchmark:basket", c, sym, "buy", 1666, f"panel{k}", ts, qty=q)
                _fill(j, "benchmark:basket", sym, "buy", q, px, ts, f"panel{k}")
            _intent(j, "benchmark:6040", c, "BTC/EUR", "buy", 6000, "p6040", ts, qty=qty100)
            _fill(j, "benchmark:6040", "BTC/EUR", "buy", qty100 * 6, px_btc, ts, "p6040")
        # Sonnet: buy at cycle 3, rejection at cycle 5, sale at cycle 10, old justification at cycle 7, recent one at the last cycle.
        pf = "llm:claude-sonnet-5-5"
        parsed = None
        if i == 3:
            _intent(j, pf, c, "BTC/EUR", "buy", 1000, "s3", ts, qty=qty100)
            _fill(j, pf, "BTC/EUR", "buy", qty100, px_btc, ts, "s3")
            j.append("stop_set", {"portfolio": pf, "symbol": "BTC/EUR", "stop_ueur": px_btc * 95 // 100}, ts)
            parsed = {"actions": [{"symbol": "BTC/EUR", "side": "buy"}], "justification": "I bought some bitcoin"}
        elif i == 5:
            _intent(j, pf, c, "ETH/EUR", "buy", 2500, "s5", ts, approved=False, reasons=["MAX_ORDER_SIZE"])
            parsed = {"actions": [{"symbol": "ETH/EUR", "side": "buy"}], "justification": "too big"}
        elif i == 7:
            parsed = {"actions": [], "justification": INJECTION}
        elif i == 10:
            pos = replay(j.iter_events())[pf].positions["BTC/EUR"]
            px = _mid("BTC/EUR", i)[0] * 9_995 // 10_000
            _intent(j, pf, c, "BTC/EUR", "sell", 10_000, "s10", ts, qty=pos.qty)
            _fill(j, pf, "BTC/EUR", "sell", pos.qty, px, ts, "s10")
            parsed = {"actions": [{"symbol": "BTC/EUR", "side": "sell"}], "justification": "taking profit"}
        elif i == N_CYCLES - 1:
            parsed = {"actions": [], "justification": SECRET_RECENT}
        else:
            parsed = {"actions": [], "justification": "nothing to do"}
        j.append("decision_received", {"portfolio": pf, "cycle": c, "model_requested": "claude-sonnet-5-5",
                                       "model_returned": "claude-sonnet-5-5", "raw_text": json.dumps(parsed),
                                       "parsed": parsed, "parse_error": None, "input_tokens": 3000,
                                       "output_tokens": 300, "cost_uusd": 9_000, "latency_ms": 900}, ts)  # fmt: skip
        j.append("decision_skipped", {"portfolio": LLMS[0], "cycle": c, "reason": "no_key"}, ts)
        j.append("decision_received", {"portfolio": LLMS[2], "cycle": c, "model_requested": "claude-opus-5-5",
                                       "model_returned": "claude-opus-5-5", "raw_text": "{}",
                                       "parsed": {"actions": [], "justification": "wait"}, "parse_error": None,
                                       "input_tokens": 3000, "output_tokens": 200, "cost_uusd": 16_000,
                                       "latency_ms": 1200}, ts)  # fmt: skip
        fable_played = with_fable and i >= FABLE_START and not (retired_fable_after is not None and i > retired_fable_after)
        if fable_played:
            fp = {"actions": [], "justification": "keep waiting"}
            if i == FABLE_START + 5:
                _intent(j, FABLE, c, "BTC/EUR", "buy", 1000, "f45", ts, qty=qty100)
                _fill(j, FABLE, "BTC/EUR", "buy", qty100, px_btc, ts, "f45")
                fp = {"actions": [{"symbol": "BTC/EUR", "side": "buy"}], "justification": FABLE_REASON}
            j.append("decision_received", {"portfolio": FABLE, "cycle": c, "model_requested": "claude-fable-5-2",
                                           "model_returned": "claude-fable-5-2", "raw_text": json.dumps(fp),
                                           "parsed": fp, "parse_error": None, "input_tokens": 3000,
                                           "output_tokens": 300, "cost_uusd": 110_000, "latency_ms": 900}, ts)  # fmt: skip
        events = list(j.iter_events())
        states = replay(events)
        marks = {s: sum(_mid(s, i)) // 2 for s in SYMBOLS}
        for p in LLMS + BENCHMARKS + ([FABLE] if fable_played else []):
            st = states[p]
            j.append("equity", {"portfolio": p, "cycle": c, "cash_ueur": st.cash_ueur,
                                "positions_value_ueur": equity_ueur(st, marks) - st.cash_ueur,
                                "equity_ueur": equity_ueur(st, marks)}, ts + 5)  # fmt: skip
        j.append("cycle_completed", {"cycle": c}, ts + 10)
        if with_fable and retired_fable_after == i:  # withdrawal of Fable: sale at the bid, then `portfolio_retired`
            rts = c + 3_000
            quotes = {}
            for sym, pos in sorted(replay(j.iter_events())[FABLE].positions.items()):
                bid = _mid(sym, i)[0] * 9_995 // 10_000
                quotes[sym] = list(_mid(sym, i))
                _fill(j, FABLE, sym, "sell", pos.qty, bid, rts, f"exit:{FABLE}:{sym}:{rts}:retired", reason="retired")
            j.append("portfolio_retired", {"portfolio": FABLE, "ts": rts, "reason": "archive", "note": "NOTE_PRIVATE",
                                           "equity_ueur": replay(j.iter_events())[FABLE].cash_ueur, "fills": len(quotes),
                                           "quotes": quotes}, rts)  # fmt: skip
        if watch and i == WAKEUP_CYCLE:
            _wakeup(j, c, i)
        if watch and i == N_CYCLES - 1:
            _watch(j, c + 1800, i)
            # Watch stop on the ETH bought at the wake-up, then a last snapshot (live equity) with an absurd raw XRP.
            pf = "llm:claude-sonnet-5-5"
            pos = replay(j.iter_events())[pf].positions["ETH/EUR"]
            tick = c + 2400
            _fill(j, pf, "ETH/EUR", "sell", pos.qty, _mid("ETH/EUR", i)[0] * 99 // 100, tick,
                  f"stop:{pf}:ETH/EUR:watch:{tick}", reason="stop")
            _watch(j, tick, i, rise=100, raw={"XRP/EUR": [XRP_RAW_ABSURD, XRP_RAW_ABSURD + 10]},
                    rejected={"XRP/EUR": "jump"})
    return j


def _wakeup(j: Journal, c: int, i: int) -> None:
    """Wake-up 2 h after cycle `c`: Sonnet buys some ETH; LTC has no quote at the wake-up."""
    r = c + 7200
    decl = {"type": "move", "symbol": "ETH/EUR", "variation_bp": -340, "window_s": 3600}
    _watch(j, c + 1800, i)
    j.append("wakeup_started", {"wakeup": r, "trigger": decl}, r + 31)
    _watch(j, r, i, wakeup=decl)
    for sym in SYMBOLS:
        if sym == "LTC/EUR":
            continue
        bid, ask = _mid(sym, i)
        if sym == "LINK/EUR":
            bid, ask = LINK_WAKEUP_ABSURD, LINK_WAKEUP_ABSURD + 10
        j.append("wakeup_quote", {"symbol": sym, "ts": r + 25, "bid": bid, "ask": ask}, r + 32)  # ts != tick
    pf = "llm:claude-sonnet-5-5"
    px = _mid("ETH/EUR", i)[1] * 10_005 // 10_000
    q = 100_000_000 * QTY_SCALE // px
    _intent(j, pf, r, "ETH/EUR", "buy", 1000, "rv1", r + 40, qty=q)
    _fill(j, pf, "ETH/EUR", "buy", q, px, r + 40, "rv1")
    parsed = {"actions": [{"symbol": "ETH/EUR", "side": "buy"}], "justification": WAKEUP_REASON}
    j.append("decision_received", {"portfolio": pf, "cycle": r, "model_requested": "claude-sonnet-5-5",
                                   "model_returned": "claude-sonnet-5-5", "raw_text": json.dumps(parsed),
                                   "parsed": parsed, "parse_error": None, "input_tokens": 3000,
                                   "output_tokens": 300, "cost_uusd": 9_000, "latency_ms": 900}, r + 39)  # fmt: skip
    j.append("wakeup_completed", {"wakeup": r}, r + 60)


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> tuple[Path, Journal]:
    tmp = tmp_path_factory.mktemp("site")
    j = synthetic_journal(tmp / "events.jsonl")
    cfg = load_config(ROOT / "config" / "arena.toml")
    cfg = dataclasses.replace(cfg, benchmarks=dataclasses.replace(cfg.benchmarks, random_paths=60))
    policy = load_policy(ROOT / "config" / "policy.toml")
    out = tmp / "site"
    build(j.path, out, config=cfg, policy=policy, now_ts=NOW)
    return out, j


def read(site, rel: str) -> str:
    return (site[0] / rel).read_text(encoding="utf-8")


def test_files_present(site):
    out, _ = site
    for rel in ["index.html", "method.html", "vendor/uPlot.iife.min.js", "vendor/uPlot.min.css",
                "vendor/SHA256SUMS", "data/summary.json", "data/equity.json", "data/method.json"]:  # fmt: skip
        assert (out / rel).is_file(), rel
    for pf in LLMS + BENCHMARKS:
        slug = re.sub(r"[^a-z0-9]+", "-", pf).strip("-")
        assert (out / "model" / f"{slug}.html").is_file()
        assert (out / "data" / f"model-{slug}.json").is_file()


def test_venue_mode_in_each_json(site):
    out, _ = site
    files = sorted((out / "data").glob("*.json"))
    assert len(files) >= 10
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d.get("venue_mode") == "paper", f.name


def test_no_yellow_banner_simulation_still_stated_in_the_footer(site):
    """The "Simulation: play money..." banner is removed from every page (shared component); the footer warning
    stays on each of them."""
    out, _ = site
    pages = list(out.rglob("*.html"))
    assert pages
    for f in pages:
        txt = f.read_text(encoding="utf-8")
        assert 'class="banner' not in txt and "no real order" not in txt.split("<main")[0], f.name
        assert "REAL MONEY" not in txt, f.name
        if f.name != "404.html":
            assert "Simulated experiment, not investment advice" in txt, f.name


def test_real_money_banner_if_live_venue():
    from arena.site.render import layout

    data = {"portfolios": [], "venue_mode": "live", "generated_ts": T0,
            "journal": {"n_records": 1, "head_hash": "a" * 64}}  # fmt: skip
    page = layout(title="t", body="", root="", active="index", data=data)
    assert "REAL MONEY" in page and "venue_mode" in page and 'class="banner real"' in page


def test_strict_csp_and_no_inline_style(site):
    out, _ = site
    for f in out.rglob("*.html"):
        txt = f.read_text(encoding="utf-8")
        assert "'unsafe-inline'" not in txt, f.name
        assert "style-src 'self'" in txt, f.name
        assert not re.search(r"\sstyle\s*=", txt), f.name  # the CSP would block any style attribute


def test_model_without_decision_rank_or_cost(site):
    """A model whose decisions were all skipped shows neither rank nor cost: it decided nothing."""
    index = read(site, "index.html")
    line = re.search(r'<tr class="llm inactive">.*?</tr>', index, re.DOTALL)
    assert line and "Claude Haiku 5.5" in line.group(0)
    assert "has never decided" in line.group(0) and "no decision" in line.group(0) and "no call" in line.group(0)
    haiku = read(site, "model/llm-claude-haiku-5-5.html")
    assert "This model has never decided yet" in haiku
    sonnet = read(site, "model/llm-claude-sonnet-5-5.html")
    assert "never decided" not in sonnet


def test_english_formats():
    from arena.site.render import bp_pct, eur, short_date, num, pct, usd, when

    assert eur(1_000_000_000, decimals=0) == "€1,000"
    assert eur(-1_234_567) == "\u2212€1.23"
    assert eur(5_000_000, signed=True) == "+€5.00"
    assert pct(-0.0022) == "\u22120.22%" and pct(0.5, signed=False) == "50.00%"
    assert num(1.5) == "1.50" and usd(1_234_567_000) == "$1,234.57" and bp_pct(50) == "0.5%"
    assert when(T0) == short_date(T0) + f", 2026, {T0 % 86_400 // 3_600:02d}:00 UTC" and short_date(T0).count(" ") == 1
    for fmt in (eur(1_000_000_000), pct(0.1), when(T0), usd(5_000_000)):
        assert "\u202f" not in fmt and "\u00a0" not in fmt


def test_justification_published_from_the_decision(site):
    """No 24 h delay: the most recent justification is published as soon as the decision is made."""
    page = read(site, "model/llm-claude-sonnet-5-5.html")
    assert SECRET_RECENT in page  # decision made 1 h before the build
    assert "taking profit" in page
    assert "after the decision" not in page and "masked" not in page
    assert "after the decision" not in read(site, "method.html")


def test_decision_with_orders_shows_reasoning_next_to_orders(site):
    page = read(site, "model/llm-claude-sonnet-5-5.html")
    # the sale of cycle 10: expanded card, reasoning then orders in the same block, never in a <details>
    i = page.index("taking profit")
    card = page[page.rindex('<li class="decision">', 0, i) : page.index("</li>", i)]
    assert '<div class="decision-body"><blockquote class="rationale">' in card
    assert "Model reasoning" in card and '<div class="decision-orders">' in card
    assert "<details" not in card
    assert card.index("taking profit") < card.index("table actions")
    assert '<span class="summary-orders">Sell BTC/EUR</span>' in card
    # a rejected order also keeps its reasoning next to it
    j = page.index("</span>too big</blockquote>")
    refused = page[page.rindex('<li class="decision">', 0, j) : page.index("</li>", j)]
    assert "decision-body" in refused and "MAX_ORDER_SIZE" in refused
    # on mobile (stacked cards), the verdict without a figure stays visible: only the "—" cells are hidden
    assert re.search(r'<td data-label="Risk check"(?! data-empty)[^>]*><span class="pill loss-bg">rejected', refused)
    assert re.search(r'<td data-label="Risk check"(?! data-empty)[^>]*><span class="pill ok">accepted', card)
    # a "do nothing" decision stays collapsed
    k = page.index("nothing to do")
    assert "<details>" in page[page.rindex('<li class="line">', 0, k) : k]


@pytest.fixture(scope="module")
def site_fable(tmp_path_factory) -> tuple[Path, Journal]:
    tmp = tmp_path_factory.mktemp("site_fable")
    j = synthetic_journal(tmp / "events.jsonl", with_fable=True)
    cfg = load_config(ROOT / "config" / "arena.toml")
    cfg = dataclasses.replace(cfg, benchmarks=dataclasses.replace(cfg.benchmarks, random_paths=20))
    out = tmp / "site"
    build(j.path, out, config=cfg, policy=load_policy(ROOT / "config" / "policy.toml"), now_ts=NOW)
    return out, j


def test_fifth_model_arriving_midway(site_fable):
    from arena.site.render import LLM_COLOR, _styles

    assert LLM_COLOR[FABLE] == 3
    out, _ = site_fable
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "four ai models" in index.lower()  # meta description derived from the journal
    assert "Claude Fable 5.2" in index and "since" in index
    # curve: no point at 100 before its opening (spanGaps would otherwise link the start to its first point)
    chart = json.loads((out / "data" / "equity.json").read_text(encoding="utf-8"))
    k = [s["id"] for s in chart["series"]].index(FABLE)
    vals = chart["series"][k]["values"]
    assert all(v is None for v in vals[: FABLE_START + 1]) and vals[FABLE_START + 1] is not None
    assert _styles(chart, None)[k]["color"] == "--llm3"
    page = (out / "model" / "llm-claude-fable-5-2.html").read_text(encoding="utf-8")
    assert "Joined the arena on" in page and "joined mid-way" in page
    assert FABLE_REASON in page and "Buy BTC/EUR" in page
    p = json.loads((out / "data" / "model-llm-claude-fable-5-2.json").read_text(encoding="utf-8"))
    assert p["late"] is True and p["rank_percentile"] is None
    assert p["n_cycles"] == N_CYCLES - FABLE_START
    # the others keep their rank and their starting point at 100
    others = json.loads((out / "data" / "model-llm-claude-sonnet-5-5.json").read_text(encoding="utf-8"))
    assert others["late"] is False and others["rank_percentile"] is not None
    assert chart["series"][0]["values"][0] == 100.0
    method = (out / "method.html").read_text(encoding="utf-8")
    assert "Four AI models (Claude Haiku 5.5, Sonnet 5.5, Opus 5.5 and Fable 5.2)" in method
    assert "Claude Fable 5.2 joined the arena on" in method


def test_html_injection_escaped(site):
    out, _ = site
    for f in out.rglob("*.html"):
        txt = f.read_text(encoding="utf-8")
        assert "<script>alert" not in txt
        assert "<b>bold</b>" not in txt
    page = read(site, "model/llm-claude-sonnet-5-5.html")
    assert html.escape(INJECTION, quote=True) in page


def test_riskd_rejection_in_plain_text_and_skips_counted(site):
    sonnet = read(site, "model/llm-claude-sonnet-5-5.html")
    assert "MAX_ORDER_SIZE" in sonnet and "order too large" in sonnet and "rejected" in sonnet
    haiku = read(site, "model/llm-claude-haiku-5-5.html")
    assert "skipped" in haiku and "model not yet connected" in haiku
    summary = json.loads(read(site, "data/summary.json"))
    h = next(p for p in summary["portfolios"] if p["id"] == "llm:claude-haiku-5-5")
    assert h["skipped"] == {"no_key": N_CYCLES}


def test_table_figures_equal_the_replay(site):
    _out, j = site
    states = replay(j.iter_events())
    marks = {s: sum(_mid(s, N_CYCLES - 1)) // 2 for s in SYMBOLS}
    summary = json.loads(read(site, "data/summary.json"))
    assert len(summary["portfolios"]) == 7
    for p in summary["portfolios"]:
        st = states[p["id"]]
        assert p["equity_ueur"] == equity_ueur(st, marks)
        assert p["fees_paid_ueur"] == st.fees_paid_ueur
    index = read(site, "index.html")
    from arena.site.render import eur

    for st in states.values():
        assert eur(equity_ueur(st, marks)) in index
        page = read(site, f"model/{re.sub(r'[^a-z0-9]+', '-', st.portfolio)}.html")
        assert eur(st.fees_paid_ueur) in page  # the fees are on the portfolio's page


def test_indistinguishable_from_luck(site):
    index = read(site, "index.html")
    assert "not distinguishable from chance" in index
    summary = json.loads(read(site, "data/summary.json"))
    assert summary["any_llm_distinguishable"] is False
    sonnet = next(p for p in summary["portfolios"] if p["id"] == "llm:claude-sonnet-5-5")
    assert sonnet["sharpe"] is not None and len(sonnet["sharpe_ci"]) == 2  # 60 cycles >= 30
    assert sonnet["rank_percentile"] is not None
    assert sonnet["api_cost_uusd"] == 9_000 * N_CYCLES


def test_too_early_under_30_cycles(tmp_path):
    cfg = load_config(ROOT / "config" / "arena.toml")
    cfg = dataclasses.replace(cfg, benchmarks=dataclasses.replace(cfg.benchmarks, random_paths=5))
    j = Journal(tmp_path / "e.jsonl")
    j.append("portfolio_opened", {"portfolio": "llm:claude-sonnet-5-5", "kind": "llm", "capital_ueur": CAPITAL,
                                  "venue_mode": "paper"}, T0)  # fmt: skip
    for i in range(3):
        j.append("equity", {"portfolio": "llm:claude-sonnet-5-5", "cycle": T0 + i * CYCLE_S, "cash_ueur": CAPITAL,
                            "positions_value_ueur": 0, "equity_ueur": CAPITAL}, T0 + i * CYCLE_S)  # fmt: skip
    build(j.path, tmp_path / "s", config=cfg, policy=load_policy(ROOT / "config" / "policy.toml"), now_ts=T0 + 10**6)
    index = (tmp_path / "s" / "index.html").read_text(encoding="utf-8")
    assert "too early" in index.lower()


def test_no_external_url(site):
    out, _ = site
    pattern = re.compile(r"""(?:src|href|action)\s*=\s*["']\s*(?:https?:)?//""", re.IGNORECASE)
    for f in out.rglob("*.html"):
        txt = f.read_text(encoding="utf-8")
        if f.name != "method.html":
            assert not re.search(r"https?://", txt), f.name
        assert not pattern.search(txt), f.name
    assert "https://" not in (out / "assets" / "site.css").read_text()
    assert "@import" not in (out / "vendor" / "uPlot.min.css").read_text()


def test_method_contains_head_hash_and_verify(site):
    _out, j = site
    page = read(site, "method.html")
    head = j.verify().head_hash
    assert head in page
    assert "chain intact" in page
    assert "not investment advice" in page
    assert "c" * 64 in page  # prompt hash


def test_atomic_rebuild_overwrites_cleanly(site, tmp_path):
    _out, j = site
    cfg = load_config(ROOT / "config" / "arena.toml")
    cfg = dataclasses.replace(cfg, benchmarks=dataclasses.replace(cfg.benchmarks, random_paths=5))
    dest = tmp_path / "var" / "site"
    pol = load_policy(ROOT / "config" / "policy.toml")
    build(j.path, dest, config=cfg, policy=pol, now_ts=NOW)
    (dest / "remaining.txt").write_text("x")
    build(j.path, dest, config=cfg, policy=pol, now_ts=NOW)
    assert not (dest / "remaining.txt").exists()
    assert [p.name for p in dest.parent.iterdir()] == ["site"]  # no leftover temporary folder


def test_stable_color_from_page_to_page():
    """Opus keeps its colour on its page, even when the chart only shows it and the basket."""
    from arena.site.render import _styles

    track = lambda i, k: {"id": i, "kind": k, "name": i, "values": [100.0]}
    single = {"x": [0], "series": [track("llm:claude-opus-5-5", "llm"), track("benchmark:basket", "benchmark")]}
    assert _styles(single, None)[0]["color"] == "--llm2"


def test_no_curve_under_three_cycles(tmp_path):
    cfg = load_config(ROOT / "config" / "arena.toml")
    cfg = dataclasses.replace(cfg, benchmarks=dataclasses.replace(cfg.benchmarks, random_paths=5))
    j = Journal(tmp_path / "e.jsonl")
    j.append("portfolio_opened", {"portfolio": "benchmark:basket", "kind": "benchmark", "capital_ueur": CAPITAL,
                                  "venue_mode": "paper"}, T0)  # fmt: skip
    j.append("equity", {"portfolio": "benchmark:basket", "cycle": T0, "cash_ueur": CAPITAL,
                        "positions_value_ueur": 0, "equity_ueur": CAPITAL}, T0)  # fmt: skip
    build(j.path, tmp_path / "s", config=cfg, policy=load_policy(ROOT / "config" / "policy.toml"), now_ts=T0 + 3600)
    index = (tmp_path / "s" / "index.html").read_text(encoding="utf-8")
    assert "Chart from 3 cycles" in index
    assert "chart.js" not in index


def test_public_version_without_operator_text_with_404(site, tmp_path):
    out_private, j = site
    cfg = load_config(ROOT / "config" / "arena.toml")
    cfg = dataclasses.replace(cfg, benchmarks=dataclasses.replace(cfg.benchmarks, random_paths=60))
    out = tmp_path / "public"
    build(j.path, out, config=cfg, policy=load_policy(ROOT / "config" / "policy.toml"), now_ts=NOW, public=True, root_path="/arena/")
    index = (out / "index.html").read_text(encoding="utf-8")
    assert 'class="to-do' not in index
    assert "RUNBOOK" not in index and ".config/arena" not in index
    page404 = (out / "404.html").read_text(encoding="utf-8")
    assert 'href="/arena/assets/site.css"' in page404 and "This page does not exist" in page404
    assert not (out_private / "404.html").exists()  # without a root, no 404 (the private site does not need one)
    # Scoreboard: a one-sentence h1 (no large headline), then the ranking and the chart.
    assert '<h1 id="title-page" class="title-page">' in index and 'class="scores"' in index
    # Indexed public version, with a share preview; the private site stays noindex.
    assert '<meta name="robots" content="index, follow">' in index
    assert '<meta property="og:image" content="https://example.github.io/arena/assets/preview.png">' in index
    assert '<link rel="canonical" href="https://example.github.io/arena/">' in index
    assert (out / "assets" / "preview.png").stat().st_size > 10_000
    assert "https://example.github.io/arena/method.html" in (out / "sitemap.xml").read_text(encoding="utf-8")
    private = (out_private / "index.html").read_text(encoding="utf-8")
    assert "noindex" in private and "og:image" not in private
    assert "SIMULATED" in index and "SIMULATED" in page404


def test_configured_model_not_yet_open(site):
    """Fable is in the config but not in this journal: Method counts like the home page and announces it separately."""
    method = read(site, "method.html")
    assert "Three AI models (Claude Haiku 5.5, Sonnet 5.5 and Opus 5.5)" in method
    assert "Claude Fable 5.2 will join the arena at the next cycle." in method
    assert "Three AI models" in read(site, "index.html")  # meta description and h1


# --------------------------------------------------------------------------- watch, wake-ups, season


def _cfg(n: int = 60):
    cfg = load_config(ROOT / "config" / "arena.toml")
    return dataclasses.replace(cfg, benchmarks=dataclasses.replace(cfg.benchmarks, random_paths=n))


@pytest.fixture(scope="module")
def watch_site(tmp_path_factory):
    from arena.site.data import compute

    tmp = tmp_path_factory.mktemp("watch")
    j = synthetic_journal(tmp / "events.jsonl", watch=True)
    pol = load_policy(ROOT / "config" / "policy.toml")
    with mock.patch.dict("os.environ", {"ARENA_SITE_CACHE": ""}):
        data = compute(j.path, _cfg(), pol, now_ts=NOW)
        build(j.path, tmp / "site", config=_cfg(), policy=pol, now_ts=NOW)
    return tmp / "site", j, data


def test_live_equity_read_from_the_watch(watch_site):
    out, j, data = watch_site
    watches = [e["payload"] for e in j.iter_events() if e["type"] == "watch"]
    last = watches[-1]
    assert data["live"]["ts"] == last["tick"]
    for p in data["portfolios"]:
        assert p["equity_ueur"] == last["equity"][p["id"]] and p["equity_live"]
        assert p["total_return"] == pytest.approx(last["equity"][p["id"]] / CAPITAL - 1)
    assert data["chart"]["kinds"][-1] == "watch" and data["chart"]["x"][-1] == last["tick"]
    assert data["chart"]["x"] == sorted(set(data["chart"]["x"]))  # strictly increasing
    assert data["n_cycles"] == N_CYCLES  # neither the snapshots nor the wake-up are cycles
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "Live values" in index and "Latest wake-up" in index and "ETH \u22123.4" in index
    assert ">Live: " in index and "until after" not in index


def test_raw_quotes_and_wakeup_quote_never_shown_as_price(watch_site):
    from arena.site.render import eur, price

    out, _j, data = watch_site
    marks = {x["symbol"]: x["mark_ueur"] for p in data["portfolios"] for x in p["positions"]}
    assert marks["XRP/EUR"] != XRP_RAW_ABSURD and marks["LINK/EUR"] != LINK_WAKEUP_ABSURD
    for f in out.rglob("*.html"):
        txt = f.read_text(encoding="utf-8")
        for absurd in (XRP_RAW_ABSURD, LINK_WAKEUP_ABSURD):
            assert str(absurd) not in txt and price(absurd) not in txt and eur(absurd) not in txt, f.name


def test_wakeup_decision_with_its_trigger_and_watch_stop(watch_site):
    out, _j, data = watch_site
    sonnet = next(p for p in data["portfolios"] if p["id"] == "llm:claude-sonnet-5-5")
    r = T0 + WAKEUP_CYCLE * CYCLE_S + 7200
    d = next(d for d in sonnet["decisions"] if d["cycle"] == r)
    assert d["llm_round"] == "wakeup" and d["trigger"]["symbol"] == "ETH/EUR" and d["actions"][0]["fills"]
    stop = next(d for d in sonnet["decisions"] if d["kind"] == "stop_watch")
    assert stop["outputs"][0]["reason"] == "stop" and ":watch:" in stop["outputs"][0]["order_id"]
    page = (out / "model" / "llm-claude-sonnet-5-5.html").read_text(encoding="utf-8")
    assert "wake-up · ETH \u22123.4% in 1 h" in page
    assert html.escape(WAKEUP_REASON, quote=True) in page
    assert "Sale on stop, detected by the watch" in page


def test_paths_replay_the_complete_wakeups(watch_site):
    from arena.site.data import _cycle_data, _wakeups

    _out, j, _data = watch_site
    events = list(j.iter_events())
    rounds = _cycle_data(events, CYCLE_S, _wakeups(events))
    r = T0 + WAKEUP_CYCLE * CYCLE_S + 7200
    wakeup_round = next(x.data for x in rounds if x.data.ts == r and x.wakeup)
    assert set(wakeup_round.quotes) == set(SYMBOLS) - {"LTC/EUR"}  # only the symbols quoted at the wake-up are tradable
    assert "LTC/EUR" in wakeup_round.marks and not wakeup_round.bars
    assert len(rounds) == N_CYCLES + 1
    assert [x.data.ts for x in rounds] == sorted(x.data.ts for x in rounds)
    # An abandoned wake-up is not replayed.
    without = _cycle_data(events, CYCLE_S, {r: {"status": "abandoned"}})
    assert all(x.data.ts != r for x in without)


def test_luck_replay_identical_to_engine_without_wakeup(site):
    """Without a wake-up, the site's replay returns exactly the numbers of the engine's simulator (drift guard)."""
    from arena.site.data import _cycle_data, _instruments
    from arena.site.luck import price_paths
    from arena.benchmarks.price_paths import simulate_random_trajectories

    _out, j = site
    events = list(j.iter_events())
    rounds = _cycle_data(events, CYCLE_S, {})
    cfg, pol = _cfg(), load_policy(ROOT / "config" / "policy.toml")
    kw = {"policy": pol, "instruments": _instruments(cfg), "fee_bp": cfg.taker_fee_bp,
          "slippage_bp": cfg.slippage_bp, "capital_ueur": CAPITAL}  # fmt: skip
    assert price_paths(rounds, 25, **kw) == simulate_random_trajectories([r.data for r in rounds], 25, **kw)


def test_luck_replay_with_wakeup_without_quote_does_not_fail(watch_site):
    """At a wake-up, a symbol without a quote is not tradable (the engine's simulator used to raise KeyError)."""
    from arena.site.data import _cycle_data, _instruments, _wakeups
    from arena.site.luck import price_paths

    _out, j, data = watch_site
    events = list(j.iter_events())
    cfg, pol = _cfg(), load_policy(ROOT / "config" / "policy.toml")
    finals = price_paths(_cycle_data(events, CYCLE_S, _wakeups(events)), 200, policy=pol,
                          instruments=_instruments(cfg), fee_bp=cfg.taker_fee_bp, slippage_bp=cfg.slippage_bp,
                          capital_ueur=CAPITAL)  # fmt: skip
    assert len(finals) == 200 and data["distribution"] is not None and data["distribution_note"] is None


def test_paths_cache(tmp_path, watch_site):
    from arena.site.data import compute

    _out, j, data = watch_site
    pol = load_policy(ROOT / "config" / "policy.toml")
    with mock.patch.dict("os.environ", {"ARENA_SITE_CACHE": str(tmp_path / "cache")}):
        a = compute(j.path, _cfg(), pol, now_ts=NOW)
        assert (tmp_path / "cache" / "price_paths.json").is_file()
        with mock.patch("arena.site.data.price_paths_since", side_effect=AssertionError("recompute")):
            b = compute(j.path, _cfg(), pol, now_ts=NOW)
    assert a["distribution"] == b["distribution"] == data["distribution"]


@pytest.fixture(scope="module")
def season_site(tmp_path_factory):
    from arena.site.data import compute

    tmp = tmp_path_factory.mktemp("season")
    j = synthetic_journal(tmp / "events.jsonl", season_a=SEASON_A)
    pol = load_policy(ROOT / "config" / "policy.toml")
    with mock.patch.dict("os.environ", {"ARENA_SITE_CACHE": ""}):
        data = compute(j.path, _cfg(), pol, now_ts=NOW)
        build(j.path, tmp / "site", config=_cfg(), policy=pol, now_ts=NOW)
    return tmp / "site", j, data


def test_season_ranked_since_the_reference(season_site):
    out, j, data = season_site
    ref = next(e["payload"] for e in j.iter_events() if e["type"] == "season_reference")
    c0 = T0 + SEASON_A * CYCLE_S
    assert data["season"]["status"] == "opened" and data["season"]["cycle"] == c0
    assert data["n_cycles"] == N_CYCLES - SEASON_A
    for p in data["portfolios"]:
        assert p["base_ueur"] == ref["equity"][p["id"]]
        assert p["total_return"] == pytest.approx(p["equity_ueur"] / ref["equity"][p["id"]] - 1)
        assert not p["late"] and p["rank_percentile"] is not None
    assert data["chart"]["x"][0] == c0 - 1 and data["chart"]["kinds"][0] == "inception"
    assert all(s["values"][0] == 100.0 for s in data["chart"]["series"])
    assert all(x >= c0 - 1 for x in data["chart"]["x"])  # the burn-in is not on the curve
    rod = {r["id"]: r["total_return"] for r in data["burn_in"]["portfolios"]}
    assert rod["benchmark:basket"] == pytest.approx(ref["equity"]["benchmark:basket"] / CAPITAL - 1)
    assert data["burn_in"]["n_cycles"] == SEASON_A
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "Season test" in index and "day " in index and "Burn-in, not ranked" in index
    assert "since the start of the season" in index
    assert html.escape(WAIVER.split(": ")[1], quote=True) in index
    method = (out / "method.html").read_text(encoding="utf-8")
    assert html.escape(WAIVER.split(": ")[1], quote=True) in method and "(code)" in method


def test_planned_season_announced_before_its_start(site):
    index = read(site, "index.html")
    assert "Season 1" in index and "burn-in under way, not ranked" in index


def test_stop_on_bar_ignores_a_bar_started_before_a_buy_at_wakeup():
    """A buy at a wake-up (09:35) is not stopped by the low of a bar opened at 08:00 (engine guard)."""
    from arena.site.data import _instruments
    from arena.site.luck import Round, price_paths
    from arena.benchmarks import random_trader
    from arena.benchmarks.price_paths import CycleData
    from arena.types import Bar, Quote, Side

    cfg, pol = _cfg(), load_policy(ROOT / "config" / "policy.toml")
    c0, r, c1 = T0, T0 + 7200, T0 + CYCLE_S
    bid, ask = _mid("BTC/EUR", 0)
    mid = (bid + ask) // 2
    q = {"BTC/EUR": Quote("BTC/EUR", c0, bid, ask)}
    bar = Bar("BTC/EUR", CYCLE_S, c0, mid, mid, mid // 2, mid, 100 * QTY_SCALE)  # low at -50%, BEFORE the buy

    def decide(ts, state, marks, context):
        if ts != r:
            return []
        return [random_trader.make_intent(random_trader.PORTFOLIO, ts, 0, "BTC/EUR", Side.BUY, 1000, stop_bp=500,
                                      expected_move_bp=900)]  # fmt: skip

    rounds = [
        Round(CycleData(c0, q, {"BTC/EUR": mid}, {"BTC/EUR": mid}, {})),
        Round(CycleData(r, {"BTC/EUR": Quote("BTC/EUR", r, bid, ask)}, {"BTC/EUR": mid}, {"BTC/EUR": mid}, {}), True),
        Round(CycleData(c1, {"BTC/EUR": Quote("BTC/EUR", c1, bid, ask)}, {"BTC/EUR": mid}, {"BTC/EUR": mid},
                        {"BTC/EUR": [bar]})),
    ]
    with mock.patch("arena.site.luck.random_trader.decide", side_effect=decide):
        [final] = price_paths(rounds, 1, policy=pol, instruments={"BTC/EUR": _instruments(cfg)["BTC/EUR"]},
                               fee_bp=cfg.taker_fee_bp, slippage_bp=cfg.slippage_bp, capital_ueur=CAPITAL)  # fmt: skip
    assert final > CAPITAL * 0.99  # the position is still there (a stop would have cost 5% of 10%, plus fees)


def test_waiver_reason_filtered_in_public():
    from arena.site.render import waiver_reason

    assert waiver_reason({"public": False}, "see /srv/x/notes") == "see /srv/x/notes"
    assert waiver_reason({"public": True}, "see /srv/x/notes") == "reason recorded in the journal"
    assert waiver_reason({"public": True}, "contact a@b.fr") == "reason recorded in the journal"
    assert waiver_reason({"public": True}, "fix of an outlier price") == "fix of an outlier price"
