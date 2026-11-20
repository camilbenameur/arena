"""Site: the derivatives league in the foreground, the spot league second."""

from __future__ import annotations

import html
import html as html_lib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import perp_fixture as F
from test_site import ROOT, synthetic_journal
from test_site import _cfg as _config

from arena.journal import Journal
from arena.perp.news import CalendarEvent
from arena.risk.policy import load_policy
from arena.site import build
from arena.site import perp as P
from arena.site.render import short_date


def _cfg():
    return _config(), load_policy(ROOT / "config" / "policy.toml")

NOW = F.T0 + 2 * 86_400 + 100
ARBITRAGEUR = P.MEMBERS["arbitrageur"][0]
NOTE_ETH = "weekly support"  # note of the ETH alert, as written in the fixture


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("perp")
    spot = synthetic_journal(tmp / "var" / "journal" / "events.jsonl")
    perp = F.build(tmp / "var-perp" / "journal" / "events.jsonl")
    out = tmp / "site"
    config, policy = _cfg()
    build(spot.path, out, config=config,
          policy=policy, now_ts=NOW, public=True, root_path="/arena/", perp_journal=perp)  # fmt: skip
    return out


def read(site: Path, name: str) -> str:
    return (site / name).read_text(encoding="utf-8")


def text(html: str) -> str:
    return html_lib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)))


def test_home_of_the_three_leagues_then_a_page_per_league(site):
    """The home page presents the three leagues; the solo AIs (derivatives) live on derivatives.html."""
    acc = read(site, "index.html")
    for page in ("councils.html", "derivatives.html", "spot.html"):
        assert f'href="{page}"' in acc and (site / page).exists()
    assert acc.count('class="league-card"') == 3 and 'class="scores mini"' in acc
    idx = read(site, "derivatives.html")
    assert "<title>Solo AIs league" in idx
    assert 'href="spot.html"' in idx
    assert "Spot league" in read(site, "spot.html")
    for pf in F.LLMS + F.BENCHMARKS:
        assert (site / "derivatives" / f"{P.slug(pf)}.html").exists()
    # The spot model pages link back to the spot league, no longer to the home page.
    page = next((site / "model").iterdir()).read_text(encoding="utf-8")
    assert 'href="../spot.html"' in page


def test_nothing_private_leaks(site):
    for f in site.rglob("*"):
        if f.suffix in (".html", ".json"):
            t = f.read_text(encoding="utf-8")
            for forbidden in ("/home/", "var-perp/rounds", "2.1.99", "candles-secret", "stderr", "Traceback", "the host", "cli_version",
                             "tools_offered", "llm_config_sha256", "message_sha256"):  # fmt: skip
                assert forbidden not in t, (f.name, forbidden)


def test_publication_the_verifier_does_not_block(site):
    sys.path.insert(0, str(Path(__file__).parent.parent / "ops"))
    import publish

    assert publish.verify(site) == []


def test_full_decision_justification_invalidation_tools_verdict_execution(site):
    t = text(read(site, "derivatives/llm-perp-claude-fable-5-2.html"))
    assert F.FABLE_REASON.split(":")[0] in t
    assert "Invalid if" in t and "$3,300" in t
    assert "Consulted indicators ETH 4h, funding ETH" in t
    assert "accepted" in t and "sell" in t and "closes its bet on ether" in t.lower()


def test_guardrail_refusal_in_plain_text(site):
    t = text(read(site, "derivatives/llm-perp-claude-opus-5-5.html"))
    assert "rejected" in t
    assert P.CODES["EDGE_TOO_SMALL"] in t
    assert "EDGE_TOO_SMALL" not in t  # the raw code stays in the JSON, not on the page


def test_wakeup_skip_and_failure(site):
    assert "wake-up · SOL" in text(read(site, "derivatives/llm-perp-claude-opus-5-5.html"))
    t = text(read(site, "derivatives/llm-perp-claude-haiku-5-5.html"))
    assert P.JUMPS["daily_budget"] in t
    assert "unreadable response" in t


def test_positions_side_stop_target_and_freeze(site):
    t = text(read(site, "derivatives/llm-perp-claude-opus-5-5.html"))
    assert "long" in t and "Stop" in t and "Target" in t
    assert "frozen" in t
    tr = text(read(site, "derivatives/benchmark-perp-trend.html"))
    assert "short" in tr and "long" in tr


def test_figures_consistent_with_the_last_statement(site):
    events = list(Journal(Path(site).parent / "var-perp" / "journal" / "events.jsonl").iter_events())
    last = {}
    for e in events:
        if e["type"] == "perp_equity":
            last[e["payload"]["portfolio"]] = e["payload"]
    d = P.compute(Path(site).parent / "var-perp" / "journal" / "events.jsonl", NOW)
    for p in d["portfolios"]:
        latest = last[p["id"]]
        assert p["equity_ueur"] == latest["equity_ueur"]
        assert p["leverage"] == pytest.approx(latest["gross_ueur"] / latest["equity_ueur"])
    fable = next(p for p in d["portfolios"] if p["id"] == F.LLMS[3])
    funding = [e["payload"]["amount_ueur"] for e in events if e["type"] == "funding" and e["payload"]["portfolio"] == F.LLMS[3]]
    assert fable["funding_net_ueur"] == sum(funding)


def test_method_explains_the_league(site):
    t = text(read(site, "method.html"))
    assert "The derivatives league" in t and "What the AI can consult" in t and "The spot league" in t


def test_without_ai_yet_only_the_benchmarks(tmp_path):
    j = Journal(tmp_path / "events.jsonl")
    for pf in F.BENCHMARKS:
        j.append("portfolio_opened", {"portfolio": pf, "kind": "benchmark", "league": "perp", "capital_ueur": 1_000_000_000,
                                      "venue_mode": "paper"}, F.T0)  # fmt: skip
    d = P.compute(tmp_path / "events.jsonl", F.T0 + 600)
    assert d and not d["llms_present"] and len(d["portfolios"]) == 3


def test_without_perp_journal_the_site_stays_the_spot_one(tmp_path):
    spot = tmp_path / "var" / "journal" / "events.jsonl"
    synthetic_journal(spot)
    config, policy = _cfg()
    build(spot, tmp_path / "site", config=config, policy=policy, now_ts=NOW, perp_journal=tmp_path / "absent.jsonl")
    assert not (tmp_path / "site" / "spot.html").exists()
    assert "Overview" in (tmp_path / "site" / "index.html").read_text(encoding="utf-8")


def test_short():
    assert [P.short(x) for x in ("PF_XBTUSD", "BTC-PERP", "PF_LINKUSD", "XRP-PERP")] == ["BTC", "BTC", "LINK", "XRP"]


def _mini(tmp_path, actions, errors, tool_args, status="filled"):
    j = Journal(tmp_path / "events.jsonl")
    pf = F.LLMS[0]
    j.append("portfolio_opened", {"portfolio": pf, "kind": "llm", "league": "perp", "capital_ueur": 1_000_000_000, "venue_mode": "paper"}, F.T0)
    j.append("tool_call", {"portfolio": pf, "round": F.T0, "n": 1, "tool": "simulate_order", "arguments": tool_args,
                           "response": "{}", "response_sha256": "0" * 64, "is_error": False}, F.T0)  # fmt: skip
    j.append("agent_decision", {"portfolio": pf, "round": F.T0, "kind": "rendezvous", "model_requested": "x",
                                "parsed": {"actions": actions, "justification": "j", "action_errors": errors},
                                "parse_error": None, "cost_uusd": 10}, F.T0)  # fmt: skip
    j.append("perp_verdict", {"intent_id": "i0", "portfolio": pf, "instrument": "PF_XBTUSD", "action": "open_long",
                              "approved": True, "reasons": [], "qty": 1000, "policy_sha256": "0", "error": None}, F.T0)  # fmt: skip
    j.append("perp_execution", {"intent_id": "i0", "portfolio": pf, "instrument": "PF_XBTUSD", "status": status, "error": None}, F.T0)
    return P.compute(tmp_path / "events.jsonl", F.T0 + 60)["portfolios"][0]["decisions"][0]


def test_a_discarded_action_does_not_steal_the_valid_action_verdict(tmp_path):
    a = {"instrument": "PF_XBTUSD", "action": "open_long", "size_pct": "10", "stop_pct": "2"}
    d = _mini(tmp_path, [a], [{"k": 0, "error": "bad"}], '{"action": ["x"], "instrument": {"a": 1}}')
    valid, discarded = d["actions"]
    assert valid["verdict"] == {"approved": True, "reason_list": []} and valid["execution"] == "filled"
    assert discarded["discarded"] and discarded["action"] is None
    assert d["tools"] == [{"tool": "simulate_order", "args": "", "error": False}]  # absurd arguments: neither a crash nor any text


def test_execution_status_shows_even_with_fills(tmp_path):
    from arena.site.render_perp import _execution

    a = {"instrument": "BTC", "execution": "closed_without_stop", "fills": [{"qty": 10, "price_uusd": 1_000_000, "fees_ueur": 1}]}
    assert P.EXECUTIONS["closed_without_stop"] in _execution(a)


# --- Agents' alerts and entry orders (docs/SPEC-PERP-ORDER-ALERTS.md) ---


def _fable(site):
    d = P.compute(Path(site).parent / "var-perp" / "journal" / "events.jsonl", NOW)
    return next(p for p in d["portfolios"] if p["id"] == F.LLMS[3])


def test_a_triggered_entry_order_keeps_its_verdict_and_fill(site):
    fable = _fable(site)
    order = [d for d in fable["decisions"] if d["kind"] == "order"]
    assert len(order) == 1
    a = order[0]["actions"][0]
    assert a["action"] == "open_long" and a["instrument"] == "SOL"
    assert a["verdict"] == {"approved": True, "reason_list": []} and a["execution"] == "filled" and len(a["fills"]) == 1
    assert a["invalidation"] == F.INVALID_ORDER and a["stop_pct"] == 4
    # The previous decision (closing ETH) keeps its own verdict and its own fill only.
    closed = next(d for d in fable["decisions"] if d["kind"] == "rendezvous" and d["actions"] and d["actions"][0]["action"] == "close")
    assert len(closed["actions"]) == 1 and len(closed["actions"][0]["fills"]) == 1
    assert fable["n_orders"] == 3  # short ETH, close, SOL order


def test_pending_and_history(site):
    pending = _fable(site)["pending"]
    assert [(x["instrument"], x["condition"], x["note"]) for x in pending["alerts"]] == [("ETH", "below", NOTE_ETH)]
    assert pending["orders"] == []
    issues = {(x["type"], x["instrument"]): (x["issue"], x.get("issue_detail")) for x in pending["history"]}
    assert issues[("alert", "BTC")] == ("fired", None)
    assert issues[("order", "SOL")] == ("fired", "executed")
    assert issues[("alert", "LTC")] == ("end", "expired")


def test_page_shows_private_wakeup_placed_and_pending(site):
    t = text(read(site, "derivatives/llm-perp-claude-fable-5-2.html"))
    assert "Pending" in t and NOTE_ETH in t
    assert "its alert · BTC above $89,540.50" in t
    assert "entry order · SOL below" in t
    assert "Left for later" in t and F.ALERT_NOTE in t and F.INVALID_ORDER in t
    assert "refused at creation: level more than 25% away from the price" in t
    assert "away from the mark" not in t  # the technical refusal text does not come out
    # Haiku left nothing: only its next regular call is pending.
    pending_html = re.search(r'<section aria-labelledby="title-pending">(.*?)</section>', read(site, "derivatives/llm-perp-claude-haiku-5-5.html")).group(1)
    assert "Regular call" in text(pending_html) and "<strong>Alert</strong>" not in pending_html and " order</strong>" not in pending_html
    assert "Between scheduled rounds" in text(read(site, "method.html"))


def test_live_price_estimate_browser_side(site):
    """Prices within a few seconds: the browser reads Kraken's public feed and revalues the published positions;
    the CSP only opens this feed on the derivatives pages that need it."""
    import json

    from arena.site.render import CSP, CSP_DIRECT

    idx = read(site, "derivatives.html")
    assert f'content="{CSP_DIRECT}"' in idx and "connect-src wss://futures.kraken.com" in CSP_DIRECT
    assert (site / "assets" / "direct.js").exists() and 'assets/direct.js"></script>' in idx
    data = json.loads(re.search(r'<script id="direct-data" type="application/json">(.*?)</script>', idx).group(1))
    assert data["flow"] == "wss://futures.kraken.com/ws/v1"
    assert set(data["products"]) <= set(P.PRODUCTS) and data["products"]
    for slug, pf in data["pf"].items():
        assert f'data-direct="ret" data-pf="{slug}"' in idx and f'data-direct="val" data-pf="{slug}"' in idx
        assert len(pf["fx"]) == 2 and pf["pos"]
        for x in pf["pos"]:
            assert set(x) == {"p", "q", "e", "l"} and x["q"] != 0
    # Nothing from the journal beyond the published figures (no order id, no raw portfolio).
    assert "llm-perp:" not in json.dumps(data) and "intent" not in json.dumps(data)
    assert 'data-direct-status data-short hidden' in idx and "<span data-direct-word>" in idx
    # Page of a portfolio with positions: current price and unrealized P&L revalued, state under "Positions".
    pages = {f.name: f.read_text(encoding="utf-8") for f in (site / "derivatives").glob("*.html")}
    with_direct_marks = [n for n, h in pages.items() if 'data-direct="mark"' in h]
    assert with_direct_marks, "no portfolio page revalued live"
    for n, h in pages.items():
        if n in with_direct_marks:
            assert 'data-direct="lat"' in h and '<p class="direct-status" data-direct-status hidden></p>' in h
            assert f'content="{CSP_DIRECT}"' in h and "direct.js" in h
        else:  # without a position: no script, no connection
            assert f'content="{CSP}"' in h and "direct.js" not in h
    # The curve stays the journal's: its last point is a snapshot, not "live".
    assert '"last":"Latest snapshot"' in idx
    # The spot league and the method open no connection.
    for page_name in ("spot.html", "method.html"):
        html = read(site, page_name)
        assert f'content="{CSP}"' in html and "direct.js" not in html


def test_regular_calls_grouped_recall_and_quota(site):
    """`cadence` and `scheduled` rounds (about 6 per hour): discreet pill, runs without orders folded into one line,
    requested recall pending, calls of the day against the cap."""
    page = read(site, f"derivatives/{P.slug(F.LLMS[1])}.html")
    t = text(page)
    assert '<span class="pill subtle">regular call</span>' in page
    assert '<span class="pill neutral">at its request</span>' in page
    group = re.search(r'<li class="line group-calm"><details><summary>(.*?)</summary>', page)
    assert group and "4 decisions without orders" in text(group.group(1))
    # The requested recall (still to come) is pending, and in what it left at each decision.
    assert "Recall it requested" in t and "Recall requested for" in t
    assert "invalid wake-up request" in t and F.SECRET not in page
    assert "calls today," in t and "Regular call" in t and "at the latest at" in t
    meth = text(read(site, "method.html"))
    assert "Regular call" in meth and "Recall requested" in meth and "2% move in 1 h" in meth.replace("\xa0", " ")


# ---------------------------------------------------------------------------
# Councils league: the Haiku council and the Opus council, outside the derivatives league
# ---------------------------------------------------------------------------


def _n(s: str) -> str:
    """Without spaces (thin, no-break, regular) or curly apostrophes, to compare texts regardless of typography."""
    return re.sub(r"[\s\u00a0\u202f]+", "", html.unescape(s)).replace("\u2019", "'")


def _table_row(idx: str, name: str) -> str:
    return next(r for r in re.findall(r"<tr[^>]*>.*?</tr>", idx, flags=re.DOTALL) if f">{name}</a>" in r)


def _perp(site: Path):
    return P.compute(Path(site).parent / "var-perp" / "journal" / "events.jsonl", NOW)


def test_perp_without_the_councils(site):
    d = _perp(site)
    assert [p["kind"] for p in d["portfolios"]] == ["llm"] * 4 + ["benchmark"] * 3
    assert not any(s["kind"] == "council" for s in d["chart"]["series"])
    idx = read(site, "derivatives.html")
    assert "Council" not in text(re.search(r"<tbody.*</table>", idx, flags=re.DOTALL).group(0))
    comparison = re.search(r'<table class="table comparison.*?</table>', idx, flags=re.DOTALL).group(0)
    assert len(re.findall(r"<tbody[^>]*>.*?</tbody>", comparison, flags=re.DOTALL)) == 2  # AIs, benchmarks
    ranking = text(re.search(r'<ol class="scores".*?</ol>', idx, flags=re.DOTALL).group(0))
    assert "Claude" in ranking and "Council" not in ranking and "no AI" in ranking
    assert "stroke--council" not in idx and "Aggressive" not in idx and "an aggressive council" not in text(idx)
    for name in ("council-perp-haiku", "council-perp-opus"):
        assert not (site / "derivatives" / f"{name}.html").exists()
    dj = read(site, "data/derivatives.json")
    assert "council-perp" not in dj and "Council" not in dj
    # The landing page links to the other league, next to the spot link.
    assert 'href="councils.html"' in idx and "councils league" in text(idx)


def test_council_league_table_ranking_and_navigation(site):
    d = _perp(site)["councils"]
    assert [(p["id"], p["kind"]) for p in d["portfolios"]] == [(F.COUNCIL, "council"), (F.OPUS, "council"), (F.BENCHMARKS[0], "benchmark")]
    assert {p["id"]: p["name"] for p in d["portfolios"]} == {F.COUNCIL: P.NAMES[F.COUNCIL], F.OPUS: P.NAMES[F.OPUS], F.BENCHMARKS[0]: P.NAMES[P.BASKET]}
    assert [s["id"] for s in d["chart"]["series"]] == [p["id"] for p in d["portfolios"]]
    page = read(site, "councils.html")
    t = text(page)
    assert "Haiku or Opus as president" in page and "Only their president changes" in t
    comparison = re.search(r'<table class="table comparison.*?</table>', page, flags=re.DOTALL).group(0)
    body = re.findall(r"<tbody[^>]*>.*?</tbody>", comparison, flags=re.DOTALL)
    assert len(body) == 2 and P.NAMES[F.COUNCIL] in body[0] and P.NAMES[F.OPUS] in body[0] and P.NAMES[P.BASKET] in body[1]
    assert P.COUNCIL_BADGE in text(body[0])
    assert P.SUBTITLES[F.COUNCIL] in text(_table_row(page, P.NAMES[F.COUNCIL]))
    assert P.SUBTITLES[F.OPUS] in text(_table_row(page, P.NAMES[F.OPUS]))
    assert "outside the 2x rule" in text(_table_row(page, P.NAMES[F.OPUS]))
    assert 'href="councils/council-perp-opus.html"' in page and 'href="derivatives/benchmark-perp-basket-1x.html"' in page
    assert "Claude Haiku 5.5" not in "".join(body) and P.NAMES[P.TREND] not in t  # neither the AIs nor the other benchmarks
    # The experiment in one sentence, then the ranking and the curve in both tints, the navigation and the live price.
    assert "Ten Claude Haiku advisers" in t and "Haiku for one, Opus for the other" in t
    assert "stroke--council" in page and "stroke--council2" in page and "c--council2" in page
    ranking = text(re.search(r'<ol class="scores".*?</ol>', page, flags=re.DOTALL).group(0))
    assert P.NAMES[F.COUNCIL] in ranking and P.NAMES[F.OPUS] in ranking and "no AI" in ranking
    assert re.search(r'<nav class="nav"[^>]*>.*?<a href="councils.html" aria-current="page">Councils</a>', page, flags=re.DOTALL)
    assert 'id="direct-data"' in page and "council-perp-opus" in re.search(r'<script id="direct-data"[^>]*>(.*?)</script>', page).group(1)
    # The other pages of the site offer it too.
    assert 'href="councils.html"' in read(site, "spot.html") and 'href="councils.html"' in read(site, "method.html")
    cj = json.loads(read(site, "data/councils.json"))
    assert cj["venue_mode"] == "paper" and {p["id"] for p in cj["portfolios"]} == {F.COUNCIL, F.OPUS, F.BENCHMARKS[0]}


def test_council_haiku_old_page_and_new_round(site):
    html_ = read(site, "councils/council-perp-haiku.html")
    t = text(html_)
    assert P.COUNCIL_BADGE in t and P.COUNCIL_OUTSIDE_RULE in t and P.SUBTITLES[F.COUNCIL] in t
    assert _n("target €2,000") in _n(t)
    assert "Councils league" in t and "councils.html#m-councils" in html_
    # Two folded rounds: the old one with 8 opinions (7 returned + 1 absent, no Arbitrageur), the recent one with 9 (Arbitrageur).
    assert html_.count('class="deliberation"') == 2
    assert _n("8 opinions · 1 absent") in _n(t) and _n("9 opinions · 1 absent") in _n(t)
    assert _n("Step A · 7 independent opinions") in _n(t) and _n("Step A · 8 independent opinions") in _n(t)  # absentees deducted
    assert ARBITRAGEUR in t and _n(F.ARG_ARBITRAGE) in _n(t)
    assert t.count(ARBITRAGEUR) == 1  # only one: the old round had none
    # Haiku President: field absent from the old decisions, present in the recent one; instructions v1 then v2.
    assert t.count("President · Haiku") >= 3 and "President · Opus" not in t
    assert "instructions v1" in t and "instructions v2" in t and "Advisers Haiku" in t
    # Actual cost of the round (no hard-coded number of calls), never "10 calls".
    assert "10 calls" not in t and "actual cost of the rounds" in t and "incl. President" not in t
    assert "OSError" not in html_


def test_council_opus_page_chair_model_and_separate_cost(site):
    html_ = read(site, "councils/council-perp-opus.html")
    t = text(html_)
    assert P.NAMES[F.OPUS] in t and P.SUBTITLES[F.OPUS] in t and P.COUNCIL_BADGE in t
    assert 'class="head-model tint-2"' in html_ and 'class="tint-2"' in html_
    assert _n("Step C · the President decides President · Opus") in _n(t)
    assert _n("9 opinions · 1 absent") in _n(t) and _n("Step A · 8 independent opinions") in _n(t)
    assert ARBITRAGEUR in t and "instructions v2" in t
    # The President weighs most: its cost is shown separately, per round and in total.
    assert _n("$0.2150 incl. President $0.1800") in _n(t)
    assert _n("actual cost of the rounds · incl. President $0.1800") in _n(t)
    assert _n(F.OPUS_REASON) in _n(t)
    assert "Consulted order simulation ETH" in t
    assert 'data-direct="lat" data-pf="council-perp-opus" data-p="PF_SOLUSD"' in html_
    # Its rejections read against the bounds of its own policy.
    assert "leverage above 2" not in t


def test_council_member_order_and_content_of_an_opinion(site):
    t = text(read(site, "councils/council-perp-opus.html"))
    i_a, i_b, i_c = t.index("Step A"), t.index("Step B"), t.index("Step C · the President read")
    assert i_a < i_b < i_c
    names = [P.MEMBERS[m][0] for m in P.MEMBERS_ORDER if P.MEMBERS[m][1] == "A"]
    assert ARBITRAGEUR in names and names.index(ARBITRAGEUR) == names.index(P.MEMBERS["contrarian"][0]) + 1
    pos = [t.index(n, i_a) for n in names]
    assert pos == sorted(pos) and pos[-1] < i_b
    assert P.MEMBERS["advocate"][0] in t[i_b:i_c] and "Attacks the short ETH" in t[i_b:i_c]
    assert all(_n(x) in _n(t) for x in (F.ARG_MAPPER, F.ARG_ADVOCATE, F.ARG_ARBITRAGE))
    assert _n("short ETH · conviction 65 · 250% · stop 2.5% · key level $3,150.00") in _n(t)
    assert "absent internal error" in t
    assert _n("9 opinions · 1 absent · short ETH ×7, flat ×1 · the Devil’s Advocate attacks the short ETH") in _n(t)
    mapper = t[t.index(P.MEMBERS["mapper"][0], i_a): t.index(P.MEMBERS["follower"][0], i_a)]
    assert "Consulted indicators ETH 4h" in mapper and "Consulted funding ETH" in t[i_b:i_c]


def test_council_haiku_refusal_at_the_bounds_of_its_policy(site):
    t = text(read(site, "councils/council-perp-haiku.html"))
    assert P.COUNCIL_CODES["MAX_LEVERAGE"] in t and P.COUNCIL_CODES["LIQUIDATION_BEFORE_STOP"] in t and "leverage above 2" not in t


def test_councils_method_in_the_council_league(site):
    t = text(read(site, "councils.html")).replace("\xa0", " ").replace("\u202f", " ")
    m = t[t.index("Councils: method"):]
    for x in ("At most 10", "500%", "1,000%", "before liquidation", "25%", "60%", "24 openings per 24 h",
              "no daily freeze, no fee budget", "−90%", "maintenance margin", "ten Claude Haiku 5.5",
              f"{P.NAMES[F.COUNCIL]} $10 per day", f"{P.NAMES[F.OPUS]} $25 per day", "list-price equivalent", ARBITRAGEUR,
              "pair-trade-screener", "TradingAgents", "President"):  # fmt: skip
        assert x in m, x
    # The general derivatives method only mentions them to point here.
    g = text(read(site, "method.html"))
    assert "Out of category" not in g and "The members" not in g and "councils.html#m-councils" in read(site, "method.html")


def test_curve_links_the_live_to_the_series(site):
    """direct.js names each portfolio by its slug, which its series carries: the curve can add its live point."""
    for name in ("derivatives.html", "councils.html"):
        page = read(site, name)
        direct = json.loads(html.unescape(re.search(r'<script id="direct-data"[^>]*>(.*?)</script>', page).group(1)))
        curve = json.loads(html.unescape(re.search(r'<script id="equity-data"[^>]*>(.*?)</script>', page).group(1)))
        assert direct["pf"] and set(direct["pf"]) <= {s.get("slug") for s in curve["series"]}, name


def test_council_stopped_says_so(tmp_path):
    spot = synthetic_journal(tmp_path / "var" / "journal" / "events.jsonl")
    perp = F.build(tmp_path / "var-perp" / "journal" / "events.jsonl", ruin=True)
    config, policy = _cfg()
    build(spot.path, tmp_path / "site", config=config, policy=policy, now_ts=NOW, public=True, root_path="/arena/", perp_journal=perp)
    t = text((tmp_path / "site" / "councils" / "council-perp-haiku.html").read_text(encoding="utf-8"))
    assert "Council stopped" in t and "ruin" in t and "Only the arena operator can restart it" in t
    assert "stopped, ruined" in text((tmp_path / "site" / "councils.html").read_text(encoding="utf-8"))


def test_council_old_deliberations_off_page(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "DELIBERATIONS_MAX", 1)
    perp = F.build(tmp_path / "events.jsonl")
    d = P.compute(perp, NOW)["councils"]
    c = next(p for p in d["portfolios"] if p["id"] == F.COUNCIL)
    rounds = [x for x in c["decisions"] if x.get("council")]
    assert rounds[0]["council"]["opinions"] and rounds[1]["council"]["opinions"] == [] and rounds[1]["council"]["opinions_outside_page"] == 9
    assert rounds[1]["council"]["president"] == "Haiku"  # the President's model is still stated, with or without opinions


def _append_council_round(perp, pf, round_, *, council=None, opinions=(), opened=True):
    j = Journal(perp)
    r = F.T0 + 2 * 86_400 - 300 if round_ is None else round_
    if opened:
        j.append("portfolio_opened", {"portfolio": pf, "kind": "council", "league": "perp", "capital_ueur": 1_000_000_000,
                                      "venue_mode": "paper"}, r - 1)  # fmt: skip
    for op in opinions:
        j.append("council_opinion", {"portfolio": pf, "round": r, "member": "follower", "stage": "A", "opinion": op, "error": None}, r)
    j.append("agent_decision", {"portfolio": pf, "round": r, "kind": "cadence", "parsed": {"actions": [], "justification": "ok"},
                                "parse_error": None, "council": council}, r)  # fmt: skip
    return r


def test_council_malformed_events_break_nothing(tmp_path):
    perp = F.build(tmp_path / "events.jsonl")
    ops = ({"opinions": 5}, {"opinions": [{"instrument": "PF_XBTUSD", "position": "long", "conviction": "x", "key_level_usd": "1e400",
                                    "size_pct": "1e400"}], "target": [1]}, "text")  # fmt: skip
    r = _append_council_round(perp, F.COUNCIL, None, opinions=ops, opened=False,
                council={"members_ok": 9, "members_failed": 2, "president_model": 7, "president_cost_uusd": "many",
                         "members_model": ["x"], "prompts_version": {"v": 2}, "name": 3})  # fmt: skip
    d = P.compute(perp, NOW)["councils"]
    c = next(p for p in d["portfolios"] if p["id"] == F.COUNCIL)
    llm_round = next(x for x in c["decisions"] if x["round"] == r)
    assert len(llm_round["council"]["opinions"]) == 1  # replayed: a single opinion from the Follower, the last one
    assert llm_round["council"]["opinions"][0]["absent"]
    assert llm_round["council"]["president"] is None and llm_round["council"]["instructions"] is None and llm_round["council"]["chair_cost_uusd"] is None


def test_unknown_council_generic_name_without_crashing(tmp_path):
    spot = synthetic_journal(tmp_path / "var" / "journal" / "events.jsonl")
    perp = F.build(tmp_path / "var-perp" / "journal" / "events.jsonl")
    _append_council_round(perp, F.UNKNOWN, None, council={"president_model": "claude-sonnet-5-5"})
    assert P.name(F.UNKNOWN) == "Zeta Council" and P.name("council-perp:") == "Council"
    config, policy = _cfg()
    build(spot.path, tmp_path / "site", config=config, policy=policy, now_ts=NOW, public=True, root_path="/arena/", perp_journal=perp)
    out = tmp_path / "site"
    page = (out / "councils.html").read_text(encoding="utf-8")
    assert ">Zeta Council</a>" in page
    z = text((out / "councils" / "council-perp-zeta.html").read_text(encoding="utf-8"))
    assert "President · Sonnet" in z and "Zeta Council" in z


def test_without_council_no_council_league(tmp_path):
    """A journal without a council: no page, no navigation link, no data."""
    spot = synthetic_journal(tmp_path / "var" / "journal" / "events.jsonl")
    perp = F.build(tmp_path / "var-perp" / "journal" / "events.jsonl", councils=False)
    assert P.compute(perp, NOW)["councils"] is None
    config, policy = _cfg()
    build(spot.path, tmp_path / "site", config=config, policy=policy, now_ts=NOW, public=True, root_path="/arena/", perp_journal=perp)
    out = tmp_path / "site"
    assert not (out / "councils.html").exists() and not (out / "councils").exists() and not (out / "data" / "councils.json").exists()
    for f in out.rglob("*.html"):
        assert "councils.html" not in f.read_text(encoding="utf-8"), f.name


# --- News (Kraken announcements, macro calendar) -------------------------------------------------------


@pytest.fixture(scope="module")
def site_news(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("news")
    spot = synthetic_journal(tmp / "var" / "journal" / "events.jsonl")
    perp = F.add_news(F.build(tmp / "var-perp" / "journal" / "events.jsonl"))
    cal = [
        CalendarEvent(
            "cpi-2026-12",
            "cpi",
            "the December 2026 CPI (BLS)",
            NOW + 2 * 86_400,
            "https://www.bls.gov/schedule/",
        ),
        CalendarEvent(
            "ppi-2026-12",
            "ppi",
            "the December 2026 PPI (BLS)",
            NOW + 3 * 86_400,
            "https://www.bls.gov/schedule/",
        ),
        CalendarEvent(
            "nfp-2027-01",
            "nfp",
            "the January 2027 jobs report (BLS)",
            NOW + 20 * 86_400,
            "https://www.bls.gov/schedule/",
        ),
    ]
    mp = pytest.MonkeyPatch()
    mp.setattr(
        P,
        "load_news_config",
        lambda: SimpleNamespace(calendar=tuple(cal), wake_kinds=("fomc", "cpi", "nfp", "pce")),
    )
    try:
        out = tmp / "site"
        config, policy = _cfg()
        build(
            spot.path,
            out,
            config=config,
            policy=policy,
            now_ts=NOW,
            public=True,
            root_path="/arena/",
            perp_journal=perp,
        )
    finally:
        mp.undo()
    return out


def _incident(site: Path) -> str:
    """Title of the incident announcement of the fixture (the one that is not the escaping trap)."""
    announcements = json.loads(read(site, "data/derivatives.json"))["news"]["announcements"]
    return next(x["title"] for x in announcements if x["title"] != F.TRAP_TITLE)


def _block(html: str) -> str:
    return re.search(r'<section aria-labelledby="title-news">(.*?)</section>', html, re.DOTALL).group(1)


def test_news_triggers_of_the_decisions(site_news):
    t = text(read(site_news, "derivatives/llm-perp-claude-fable-5-2.html"))
    assert f"Kraken announcement · {_incident(site_news)}" in t
    c = text(read(site_news, "councils/council-perp-haiku.html"))
    assert f"macro release · after {F.CPI_LABEL}" in c
    s = text(read(site_news, "derivatives/llm-perp-claude-sonnet-5-5.html"))
    assert "regular call" in s and "Kraken announcement attached" in s


def test_news_block_on_the_home_page_of_perp_and_councils(site_news):
    for name in ("derivatives.html", "councils.html"):
        b = _block(read(site_news, name))
        t = text(b)
        assert "the December 2026 CPI (BLS)" in t and "recalls the AIs 3 min after" in t
        assert (
            "the December 2026 PPI" in t and t.count("recalls the AIs") == 1
        )  # the PPI does not recall the AIs
        assert "January 2027" not in t  # beyond 7 days
        assert "Old announcement" not in t
        assert "withdrawal" not in t and "Maintenance" in t and "scheduled" in t and "contracts: BTC" in t
        assert 'href="https://stspg.io/abc"' in b


def test_news_announcement_with_several_versions_shows_the_last(site_news):
    t = text(_block(read(site_news, "derivatives.html")))
    assert t.count(_incident(site_news)) == 1
    assert "resolved" in t and "investigating" not in t


def test_news_title_escaped_and_non_https_link_discarded(site_news):
    b = _block(read(site_news, "derivatives.html"))
    assert "<script>" not in b and "&lt;script&gt;alert(1)&lt;/script&gt;" in b
    assert "javascript:" not in b


def test_news_method_and_export(site_news):
    t = text(read(site_news, "method.html"))
    assert (
        "never the published figures" in t
        and "3 min" in t
        and 'id="m-news"' in read(site_news, "method.html")
    )
    for name in ("derivatives.json", "councils.json"):
        a = json.loads(read(site_news, f"data/{name}"))["news"]
        assert len(a["calendar"]) == 2 and {x["title"] for x in a["announcements"]} == {
            _incident(site_news),
            F.TRAP_TITLE,
        }


def test_news_without_announcement_or_calendar(site, monkeypatch):
    b = _block(read(site, "derivatives.html"))
    assert "No Kraken derivatives announcement in the last 7 days." in text(b)
    assert json.loads(read(site, "data/derivatives.json"))["news"]["announcements"] == []


def test_news_unreadable_calendar_is_omitted(tmp_path, monkeypatch):
    def boom():
        raise ValueError("broken config")

    monkeypatch.setattr(P, "load_news_config", boom)
    perp = F.build(tmp_path / "p" / "events.jsonl")
    assert P.compute(perp, NOW)["news"]["calendar"] is None


@pytest.fixture(scope="module")
def site_archives(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("perp-archives")
    spot = synthetic_journal(tmp / "var" / "journal" / "events.jsonl")
    perp = F.build(tmp / "var-perp" / "journal" / "events.jsonl", archive=True)
    out = tmp / "site"
    config, policy = _cfg()
    build(spot.path, out, config=config, policy=policy, now_ts=NOW, public=True, root_path="/arena/", perp_journal=perp)
    return out


def test_archived_councils_dotted_curve_stopped_at_withdrawal(site_archives):
    site = site_archives
    d = _perp(site)["councils"]
    end = F.T0 + 2 * 86_400 - 3_600
    by_id = {p["id"]: p for p in d["portfolios"]}
    assert by_id[F.COUNCIL]["archive"] == {"ts": end, "reason": "overhaul"}  # the note stays in the journal, never published
    assert by_id[F.BENCHMARKS[0]]["archive"] is None
    series = {s["id"]: s for s in d["chart"]["series"]}
    assert series[F.COUNCIL]["archive_ts"] == end and "archive_ts" not in series[F.BENCHMARKS[0]]
    x = d["chart"]["x"]
    assert end in x and x[-1] > end  # the benchmark continues after the withdrawal
    for pf in (F.COUNCIL, F.OPUS):
        v = series[pf]["values"]
        assert v[x.index(end)] is not None and all(w is None for w, t in zip(v, x, strict=True) if t > end)
        assert by_id[pf]["net_return"] == pytest.approx(v[x.index(end)] / 100 - 1, abs=1e-4)  # frozen at the withdrawal
    # the chart: dotted style, same tints; legend with the withdrawal date
    page = read(site, "councils.html")
    curve = json.loads(html.unescape(re.search(r'<script id="equity-data"[^>]*>(.*?)</script>', page).group(1)))
    st = {s["id"]: t for s, t in zip(curve["series"], curve["styles"], strict=True)}
    assert st[F.COUNCIL]["dash"] == [1, 6] and st[F.COUNCIL]["archive"] and st[F.COUNCIL]["color"] == "--council"
    assert st[F.OPUS]["dash"] == [1, 6] and st[F.OPUS]["color"] == "--council2"
    assert not st[F.BENCHMARKS[0]].get("archive") and st[F.BENCHMARKS[0]]["dash"] != [1, 6]
    legend = re.search(r'<ul class="legend".*?</ul>', page, flags=re.DOTALL).group(0)
    assert legend.count(f"withdrawn on {short_date(end)}") == 2 and legend.count("legend-tag") == 2 and "stroke-dasharray" in legend
    assert "Dotted curves" in text(page) and "archived" in text(page)


def test_archived_councils_ranking_and_table_marked_after_the_active_ones(site_archives):
    page = read(site_archives, "councils.html")
    ranking = re.search(r'<ol class="scores".*?</ol>', page, flags=re.DOTALL).group(0)
    lines = re.findall(r'<li class="sc[^"]*".*?</li>', ranking, flags=re.DOTALL)
    names = [re.search(r">([^<]+)</a>", li).group(1) for li in lines]
    assert names[0] == P.NAMES[P.BASKET] and set(names[1:]) == {P.NAMES[F.COUNCIL], P.NAMES[F.OPUS]}  # the archived ones after
    for li in lines[1:]:
        assert "sc-archive-line" in li and "sw-archive" in li and "archived" in li and "withdrawn on" in text(li)
        assert '<span class="sc-rank">—</span>' in li  # no longer ranked
    assert "sw-archive" not in lines[0]
    line = _table_row(page, P.NAMES[F.COUNCIL])
    assert 'class="council archive"' in line and "archived on" in text(line)
    # its page: says so, keeps its dotted curve, no planned call and no "pending"
    haiku = read(site_archives, "councils/council-perp-haiku.html")
    t = text(haiku)
    assert "Archived council" in t and "its figures are frozen" in t and "Pending" not in t
    curve = json.loads(html.unescape(re.search(r'<script id="equity-data"[^>]*>(.*?)</script>', haiku).group(1)))
    assert curve["styles"][0]["dash"] == [1, 6] and curve["series"][0]["archive_ts"]
    # the home page card says so too, and no page breaks
    home = text(read(site_archives, "index.html"))
    assert "archived" in home
    assert 'stroke--council"' in page


# ---------------------------------------------------------------------------
# The Wick Hunter: the "Robots" group of the derivatives league
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def site_robots(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("perp-robots")
    spot = synthetic_journal(tmp / "var" / "journal" / "events.jsonl")
    perp = F.build(tmp / "var-perp" / "journal" / "events.jsonl", councils=False, robots=True)
    out = tmp / "site"
    config, policy = _cfg()
    build(spot.path, out, config=config, policy=policy, now_ts=NOW, public=True, root_path="/arena/", perp_journal=perp)
    return out


def test_robots_group_in_the_perp_league_with_rule_shocks_and_trades(site_robots):
    d = _perp(site_robots)
    robots = [p for p in d["portfolios"] if p["kind"] == "robot"]
    assert [p["id"] for p in robots] == [F.ROBOT, F.ROBOT_5MIN]
    assert [p["name"] for p in robots] == [P.NAMES[F.ROBOT], P.NAMES[F.ROBOT_5MIN]]
    assert [p["kind"] for p in d["portfolios"]] == ["llm"] * 4 + ["robot"] * 2 + ["benchmark"] * 3  # AIs, robots, benchmarks
    hunter, benchmark = robots
    assert (hunter["n_shocks"], hunter["n_trades"]) == (1, 1) and (benchmark["n_shocks"], benchmark["n_trades"]) == (1, 0)
    assert hunter["n_operations"] == 2 and hunter["positions"] == []  # entered then exited
    idx = read(site_robots, "derivatives.html")
    comparison = re.search(r'<table class="table comparison.*?</table>', idx, flags=re.DOTALL).group(0)
    assert 'group-robot' in comparison and "Robots" in text(comparison) and len(re.findall(r"<tbody[^>]*>", comparison)) == 3
    line = text(re.search(r'<tr class="robot[^"]*">.*?</tr>', comparison, flags=re.DOTALL).group(0))
    assert P.NAMES[F.ROBOT] in line and "4.5" in line and "1 shock seen" in line and "1 trade" in line
    assert "robot-perp-hunter" in idx and (site_robots / "derivatives" / "robot-perp-hunter.html").exists()


def test_robots_own_color_and_benchmark_curve_dashed(site_robots):
    d = _perp(site_robots)
    from arena.site.render import _styles

    st = dict(zip((s["id"] for s in d["chart"]["series"]), _styles(d["chart"], None), strict=True))
    assert st[F.ROBOT]["color"] == "--hunter" and st[F.ROBOT]["dash"] is None
    assert st[F.ROBOT_5MIN]["color"] == "--hunter" and st[F.ROBOT_5MIN]["dash"]
    assert all(v["color"] != "--hunter" for k, v in st.items() if k not in (F.ROBOT, F.ROBOT_5MIN))
    css = (Path(__file__).parent.parent / "arena" / "site" / "assets" / "site.css").read_text(encoding="utf-8")
    assert "--hunter:" in css and ".stroke--hunter" in css


def test_robots_hunter_page_without_any_person_name(site_robots):
    page = read(site_robots, "derivatives/robot-perp-hunter.html")
    t = text(page)
    assert P.NAMES[F.ROBOT] in t and "Shocks seen" in t and "Trades" in t and "robot without AI" in t
    for name in ("owner-first-name", "owner-last-name"):  # the visible text (the publication domain, irrelevant, is not text)
        assert name not in t.lower() and name not in text(read(site_robots, "derivatives.html")).lower()
    assert any("The robots" in text(f.read_text(encoding="utf-8")) for f in site_robots.glob("*.html"))
