"""The Haiku council of the perp league (docs/SPEC-PERP-CONSEIL-HAIKU.md): ten members, its own aggressive
policy, Kraken's margins. Fake `claude` (tests/fake_claude.py), real MCP servers, the real watcher."""

from __future__ import annotations

import dataclasses
import json
import threading
from pathlib import Path

import pytest

from arene.perp import margin
from arene.perp.agent import OUTPUT_SCHEMA, AgentDecider, parse_decision, prompt_sha256
from arene.perp.agent_round import STANDARD_RULES, rules_text
from arene.perp.council import (
    ADVOCATE,
    MEMBERS,
    PRESIDENT,
    STAGE_A,
    CouncilConfigError,
    CouncilDecider,
    council_record,
    load_council,
    member_prompt,
    member_sha256,
    parse_opinion,
)
from arene.perp.ledger import replay
from arene.perp.llm_league import load_llm_league
from arene.perp.policy import AGGRESSIVE, PerpPolicyError, load_perp_policy
from arene.perp.riskd import LIQUIDATION_BEFORE_STOP, PerpIntent, evaluate_perp
from arene.perp.sim import MinuteCandles, PerpSimulator, SimParams
from arene.perp.types import MarginLevel
from tests.test_perp_agent import fake_runner
from tests.test_perp_llm_league import _view
from tests.test_perp_watcher import POLICY, SPECS, T0, World

COUNCIL = load_council()
NAME = COUNCIL.portfolio
HAIKU = "llm-perp:claude-haiku-5-5"
# one LLM portfolio beside the council keeps the tests short; no cadence (its own test below)
BASE = dataclasses.replace(load_llm_league(), cadence_min=0, rounds_per_day=48)
LEAGUE = dataclasses.replace(BASE, models=BASE.models[:1], council=COUNCIL)
BIG_ENTRY = {
    "actions": [
        {
            "instrument": "PF_XBTUSD", "action": "open_long", "size_pct": 400, "stop_pct": 1.2,
            "take_profit_pct": 4, "horizon_h": 12, "expected_move_pct": 4, "confidence_pct": 60,
            "invalidation": "clôture 1 h sous le niveau",
        }
    ],
    "justification": "je suis le Suiveur et le Trésorier, j'écarte le Contrarien",
}  # fmt: skip


def council_factory(tmp: Path, calls: list, council: dict | None = None, extra: dict | None = None):
    """Deciders for every player: the council with the fake runner (its members told apart by their system
    prompt), the LLM portfolios with the plain fake."""
    lock = threading.Lock()
    plain = fake_runner("normal", extra)

    def counted(cmd, stdin, env, cwd, timeout):
        with lock:
            calls.append(cmd[cmd.index("--model") + 1])
        return plain(cmd, stdin, {**env, "FAKE_CLAUDE_COUNCIL": json.dumps(council or {})}, cwd, timeout)

    def make(m):
        if m.council:
            return CouncilDecider(COUNCIL, tmp / "claude-empty", runner=counted)
        return AgentDecider(m.model, m.portfolio, tmp / "claude-empty", runner=counted, effort=BASE.effort)

    return make


def council_world(tmp_path, council: dict | None = None, league=LEAGUE):
    calls: list[str] = []
    w = World(tmp_path, llm=league, factory=council_factory(tmp_path, calls, council))
    rep = w.w.tick(T0 + 120)
    return w, calls, rep


def payloads(w, type_, portfolio=None):
    return [
        e["payload"]
        for e in w.events(type_)
        if portfolio is None or e["payload"].get("portfolio") == portfolio
    ]


# ---------------------------------------------------------------------- configuration and prompts


def test_the_council_config_and_its_policy_are_valid_and_strict(tmp_path):
    assert COUNCIL.enabled and NAME == "council-perp:haiku" and COUNCIL.model == "claude-haiku-5-5"
    assert COUNCIL.daily_budget_uusd == 10_000_000 and COUNCIL.member_max_tool_calls == 3
    p = COUNCIL.policy
    assert p.profile == AGGRESSIVE and p.max_leverage_bp == 100_000 and p.max_order_bp == 50_000
    assert (p.max_trade_loss_bp, p.max_open_risk_bp, p.drawdown_halt_bp) == (2500, 6000, 9000)
    assert (p.daily_loss_freeze_bp, p.monthly_fee_budget_bp, p.min_interval_same_open_s) == (0, 0, 0)
    # the league's policy is untouched, and neither file loads as the other
    assert POLICY.profile == "standard" and POLICY.max_leverage_bp == 20_000
    with pytest.raises(PerpPolicyError, match="profile"):
        load_perp_policy(Path("config/policy-perp-conseil.toml"))
    with pytest.raises(PerpPolicyError, match="profile"):
        load_perp_policy(Path("config/policy-perp.toml"), profile=AGGRESSIVE)
    text = Path("config/policy-perp-conseil.toml").read_text()
    for bad in ("max_leverage_bp  = 100000", "drawdown_halt_bp     = 9000"):
        worse = text.replace(bad, bad.replace("100000", "110000").replace("9000", "9900"))
        f = tmp_path / "p.toml"
        f.write_text(worse)
        with pytest.raises(PerpPolicyError):
            load_perp_policy(f, profile=AGGRESSIVE)
    cfg = Path("config/perp-conseil.toml").read_text()
    for old, new in (
        ('model = "claude-haiku-5-5"', 'model = "claude-opus-5-5"'),
        ('portfolio = "council-perp:haiku"', 'portfolio = "llm-perp:haiku"'),
        ("members_parallel = 4", "members_parallel = 9"),
        ('policy = "policy-perp-conseil.toml"', 'policy = "policy-perp.toml"'),
    ):
        (tmp_path / "policy-perp-conseil.toml").write_text(text)
        (tmp_path / "policy-perp.toml").write_text(Path("config/policy-perp.toml").read_text())
        (tmp_path / "c.toml").write_text(cfg.replace(old, new))
        with pytest.raises(CouncilConfigError):
            load_council(tmp_path / "c.toml")
    # the default league config never loads the council by itself (the watcher adds it)
    assert load_llm_league().council is None and len(load_llm_league().players) == 4
    assert [m.portfolio for m in LEAGUE.players] == [HAIKU, NAME] and LEAGUE.players[-1].council


def test_ten_members_with_their_role_sources_and_format():
    assert (
        len(MEMBERS) == 10 and len(STAGE_A) == 8 and ADVOCATE.key == "avocat" and PRESIDENT.key == "president"
    )
    shas = set()
    for m in MEMBERS:
        text = member_prompt(m)
        assert (
            "le Conseil Haiku" in text
            and "doubler le capital" in text
            and f"## Ton rôle : {m.name[0].lower()}{m.name[1:]}" in text
        )
        assert "Sources :" in text and "hors de la règle française" in text
        assert ("## Ta décision" in text) == (m is PRESIDENT) and ("## Ton avis" in text) == (
            m is not PRESIDENT
        )
        shas.add(member_sha256(m))
    assert len(shas) == 10
    # the neutral models keep their prompt and their schema
    assert prompt_sha256() == AgentDecider("m", "p", Path("/tmp")).prompt_digest()
    assert OUTPUT_SCHEMA["properties"]["actions"]["items"]["properties"]["size_pct"]["maximum"] == 100


def test_rules_line_of_the_snapshot():
    from dataclasses import asdict

    assert rules_text({**asdict(POLICY), "instruments": []}) == STANDARD_RULES
    line = rules_text({**asdict(COUNCIL.policy), "instruments": []})
    assert "levier 10x max" in line and "entrée <= 500 %" in line and "avant la liquidation" in line
    assert "arrêt à -90 %" in line and "24 ouvertures" in line


def test_parse_opinion_rules():
    ok, err = parse_opinion(
        {
            "avis": [{"instrument": "PF_ETHUSD", "position": "short", "conviction": 70, "taille_pct": 250.5}],
            "cible": None,
            "argument": "x" * 900,
        }
    )
    assert err is None and ok["avis"][0]["taille_pct"] == "250.5" and len(ok["argument"]) == 600
    for bad in (
        {"avis": [], "argument": "x", "decision": 1},
        {"avis": [{"instrument": "PF_DOGEUSD", "position": "long", "conviction": 5}], "argument": "x"},
        {"avis": [{"instrument": "PF_ETHUSD", "position": "long", "conviction": 101}], "argument": "x"},
        {"avis": [{"instrument": "PF_ETHUSD", "position": "long", "conviction": True}], "argument": "x"},
        {
            "avis": [{"instrument": "PF_ETHUSD", "position": "long", "conviction": 5, "taille_pct": 2000}],
            "argument": "x",
        },
        {"avis": [], "argument": "x", "cible": {"instrument": "PF_ETHUSD", "sens": "plat"}},
        "not an object",
    ):
        assert parse_opinion(bad)[0] is None


def test_the_council_parses_sizes_above_the_equity_and_the_models_do_not():
    parsed, err, intents = parse_decision(BIG_ENTRY, NAME, 1, T0, max_size_pct=500)
    assert err is None and intents[0].size_bp == 40_000
    parsed, err, intents = parse_decision(BIG_ENTRY, HAIKU, 1, T0)
    assert intents == [] and "size_pct" in parsed["action_errors"][0]["error"]


# ---------------------------------------------------------------------- a council round in the watcher


def test_a_council_round_end_to_end(tmp_path):
    w, calls, rep = council_world(tmp_path, {"president": BIG_ENTRY})
    assert not rep.problems, rep.problems
    assert calls.count("claude-haiku-5-5") == 1 + 10  # the Haiku portfolio, then the ten members
    ops = payloads(w, "council_opinion", NAME)
    assert [o["member"] for o in ops] == [m.key for m in (*STAGE_A, ADVOCATE)]
    assert all(o["opinion"] is not None and o["error"] is None and o["cost_uusd"] == 12346 for o in ops)
    assert {o["persona_sha256"] for o in ops} == {member_sha256(m) for m in (*STAGE_A, ADVOCATE)}
    assert ops[-1]["opinion"]["cible"] == {"instrument": "PF_XBTUSD", "sens": "long"}
    [d] = payloads(w, "agent_decision", NAME)
    assert d["prompt_sha256"] == member_sha256(PRESIDENT) and d["cost_uusd"] == 10 * 12346
    assert d["council"]["members_ok"] == 9 and d["council"]["members_failed"] == []
    assert d["council"]["config_sha256"] == COUNCIL.sha256
    # the opinions are journaled before the decision, the tool calls carry their member
    seqs = [e["seq"] for e in w.events() if e["payload"].get("portfolio") == NAME]
    kinds = [e["type"] for e in w.events() if e["payload"].get("portfolio") == NAME and e["seq"] in seqs]
    assert kinds.index("agent_decision") > max(i for i, k in enumerate(kinds) if k == "council_opinion")
    tools = payloads(w, "tool_call", NAME)
    assert {t["member"] for t in tools} == {m.key for m in MEMBERS} and [t["n"] for t in tools] == list(
        range(1, len(tools) + 1)
    )
    [rd] = payloads(w, "round_data", NAME)
    assert rd["council_config_sha256"] == COUNCIL.sha256
    # the President's 4x entry passes the council's policy, with its own hash
    [v] = payloads(w, "perp_verdict", NAME)
    assert v["approved"] and v["policy_sha256"] == COUNCIL.policy.sha256
    pos = replay(w.events())[NAME].positions["PF_XBTUSD"]
    assert pos.stop_uusd is not None and abs(pos.qty) > 0
    # the LLM portfolio is untouched: league policy, neutral prompt, no opinion
    [vh] = payloads(w, "perp_verdict", HAIKU)
    assert vh["policy_sha256"] == POLICY.sha256
    [dh] = payloads(w, "agent_decision", HAIKU)
    assert dh["prompt_sha256"] == prompt_sha256() and "council" not in dh
    assert not payloads(w, "council_opinion", HAIKU)
    opened = {p["portfolio"]: p["kind"] for p in payloads(w, "portfolio_opened")}
    assert opened[NAME] == "council" and opened[HAIKU] == "llm"
    # the next tick calls nobody again
    w.advance(T0 + 420)
    w.w.tick(T0 + 420)
    assert len(calls) == 11


def test_stage_a_opinions_are_independent(tmp_path):
    w, _, _ = council_world(tmp_path)
    [rd] = payloads(w, "round_data", NAME)
    base = w.var / rd["path"] / "membres"
    stdin = {m.key: (base / m.key / "stdin.txt").read_text() for m in MEMBERS}
    first = {stdin[m.key] for m in STAGE_A}
    assert len(first) == 1  # the eight members of stage A get the same message...
    msg = first.pop()
    assert "<avis_du_conseil>" not in msg and "funding faible" not in msg  # ...without anyone's opinion
    assert "bilan_du_conseil" in msg
    import hashlib

    assert rd["message_sha256"] == hashlib.sha256(msg.encode()).hexdigest()
    seen = json.loads(stdin["avocat"].split("<avis_du_conseil>\n")[1].split("\n</avis_du_conseil>")[0])
    assert [o["role"] for o in seen] == [m.key for m in STAGE_A]
    final = json.loads(stdin["president"].split("<avis_du_conseil>\n")[1].split("\n</avis_du_conseil>")[0])
    assert [o["role"] for o in final] == [m.key for m in (*STAGE_A, ADVOCATE)]
    # each member has its own round directory and MCP server (its own tool budget)
    assert all(
        json.loads((base / m.key / "round.json").read_text())["meta"]["portfolio"] == NAME for m in MEMBERS
    )


def test_a_failed_member_is_left_out_and_a_failed_president_decides_nothing(tmp_path):
    w, _, _rep = council_world(tmp_path / "a", {"fail": ["contrarien"], "president": BIG_ENTRY})
    ops = {o["member"]: o for o in payloads(w, "council_opinion", NAME)}
    assert ops["contrarien"]["opinion"] is None and ops["contrarien"]["error"]
    assert ops["contrarien"]["cost_uusd"] == COUNCIL_CEILING_UUSD  # it used the model: charged its ceiling
    [d] = payloads(w, "agent_decision", NAME)
    assert d["council"]["members_failed"] == ["contrarien"] and d["parse_error"] is None
    assert payloads(w, "perp_verdict", NAME)
    president = w.var / payloads(w, "round_data", NAME)[0]["path"] / "membres" / "president" / "stdin.txt"
    assert '"contrarien"' not in president.read_text()

    w, _, _ = council_world(tmp_path / "b", {"fail": ["president"], "president": BIG_ENTRY})
    [d] = payloads(w, "agent_decision", NAME)
    assert d["parsed"] is None and str(d["parse_error"]).startswith("president")
    assert not payloads(w, "perp_verdict", NAME) and len(payloads(w, "council_opinion", NAME)) == 9
    assert any(e["type"] == "perp_round_done" for e in w.events())


COUNCIL_CEILING_UUSD = 100_000  # 1 $ for the round (max_budget_usd of the league), a tenth per member


def test_a_crash_inside_the_council_never_loses_the_cost_of_its_calls(tmp_path, monkeypatch):
    import arene.perp.council as C

    real = C.MemberDecider.decide

    def paid_then_crash(self, round_dir, snapshot):
        res = real(self, round_dir, snapshot)
        if self.member.key == "carnet":
            raise ValueError("parse bug after the call")
        return res

    monkeypatch.setattr(C.MemberDecider, "decide", paid_then_crash)
    w, _, _ = council_world(tmp_path / "a")
    ops = {o["member"]: o for o in payloads(w, "council_opinion", NAME)}
    assert (
        ops["carnet"]["opinion"] is None and ops["carnet"]["cost_uusd"] == 12346
    )  # read back from its stream
    [d] = payloads(w, "agent_decision", NAME)
    assert d["cost_uusd"] == 10 * 12346 and d["council"]["members_failed"] == ["carnet"]

    def broken_record(self, m, r, ceiling):
        raise OSError("prompt file unreadable")

    monkeypatch.setattr(C.CouncilDecider, "_record", broken_record)
    w, _, _ = council_world(tmp_path / "b")
    [d] = payloads(w, "agent_decision", NAME)
    assert str(d["parse_error"]).startswith("council crashed") and d["cost_uusd"] == 8 * 12346
    assert not payloads(w, "perp_verdict", NAME)


def test_a_cut_during_the_council_is_never_replayed(tmp_path, monkeypatch):
    calls: list[str] = []
    w = World(tmp_path, llm=LEAGUE, factory=council_factory(tmp_path, calls))
    import arene.perp.council as C

    real = C.MemberDecider.decide

    def cut(self, round_dir, snapshot):
        if self.member.key == "avocat":
            raise SystemExit("power cut")  # the process dies in the middle of the council
        return real(self, round_dir, snapshot)

    monkeypatch.setattr(C.MemberDecider, "decide", cut)
    with pytest.raises(SystemExit):
        w.w.tick(T0 + 120)
    monkeypatch.undo()
    n = len(calls)
    w.advance(T0 + 420)
    w.w.tick(T0 + 420)
    skipped = payloads(w, "perp_llm_skipped", NAME)
    assert len(calls) == n and [s["reason"] for s in skipped] == ["interrupted_after_call"]
    assert not payloads(w, "agent_decision", NAME) and not payloads(w, "council_opinion", NAME)
    # the eight members of stage A were paid (0.0123456 $ each, from their streams): counted in the budget
    from arene.perp.llm_league import spent_today_uusd

    assert skipped[0]["cost_uusd"] == 8 * 12346 and spent_today_uusd(w.events(), NAME, T0 + 420) == 8 * 12346


def test_opinions_of_a_round_cut_before_its_decision_count_in_the_budget():
    from arene.perp.llm_league import spent_today_uusd

    def ev(type_, rnd, cost, ts=100):
        return {"type": type_, "ts": ts, "payload": {"portfolio": NAME, "round": rnd, "cost_uusd": cost}}

    events = [
        ev("council_opinion", 1, 10), ev("council_opinion", 1, 10), ev("agent_decision", 1, 100),  # decided
        ev("council_opinion", 2, 7), ev("council_opinion", 2, 8),  # cut before its decision
        ev("council_opinion", 3, 50, ts=-86_400),  # another day
    ]  # fmt: skip
    assert spent_today_uusd(events, NAME, 200) == 100 + 15


def test_the_council_plays_the_cadence_like_the_models(tmp_path):
    league = dataclasses.replace(LEAGUE, cadence_min=10)
    w, calls, _ = council_world(tmp_path, league=league)
    assert len(calls) == 11
    w.advance(T0 + 720)
    w.w.tick(T0 + 720)
    rounds = [p for p in payloads(w, "perp_round") if p["kind"] == "private"]
    assert rounds and rounds[-1]["portfolios"] == sorted([HAIKU, NAME])
    assert rounds[-1]["triggers"][NAME]["kind"] == "cadence" and len(calls) == 22
    assert w.w.quota(w.events(), NAME, T0 + 720)["played_today"] == 2  # one round of the council, not ten


# ---------------------------------------------------------------------- the aggressive policy and the margins


def _account_view(w):
    from arene.perp.counters import counters_for
    from arene.perp.market import market_view

    view = market_view(w.store, w.w.symbols, T0 + 130)
    return view, counters_for(w.events(), NAME, T0 + 130)


def intent(size_bp: int, stop_bp: int, portfolio=NAME) -> PerpIntent:
    return PerpIntent("i", portfolio, T0 + 130, "PF_XBTUSD", "open_long", size_bp, stop_bp, None, 12, 400, 60)


def test_riskd_council_bounds_and_the_models_keep_theirs(tmp_path):
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    for name in (NAME, HAIKU):
        w.w.sim.open_portfolio(name, "x", T0 + 125)
    view, c = _account_view(w)
    acc = w.w.sim.states()[NAME]
    pol, params = COUNCIL.policy, w.w.cfg.simulation

    def judge(size, stop, policy=pol, name=NAME):
        a = w.w.sim.states()[name]
        return evaluate_perp(intent(size, stop, name), a, view, SPECS, c, policy, params, T0 + 130, False)

    assert judge(40_000, 120).approved  # 4x, stop 1.2 %
    assert set(judge(60_000, 100).reasons) >= {"MAX_ORDER_SIZE"}  # 6x in one entry
    assert set(judge(30_000, 1000).reasons) == {"MAX_TRADE_LOSS"}  # 3x with a 10 % stop: about 33 % lost
    # the same 4x entry for an LLM portfolio, under the league's policy
    assert {"MAX_ORDER_SIZE", "MAX_LEVERAGE", "MAX_POSITION"} <= set(
        judge(40_000, 120, POLICY, HAIKU).reasons
    )
    # a stop past the liquidation is refused: a contract whose maintenance margin is 20 %
    tight = {
        **SPECS,
        "PF_XBTUSD": dataclasses.replace(
            SPECS["PF_XBTUSD"], margin_levels=(MarginLevel(0, 150_000, 200_000),)
        ),
    }
    v = evaluate_perp(intent(50_000, 300), acc, view, tight, c, pol, params, T0 + 130, False)
    assert LIQUIDATION_BEFORE_STOP in v.reasons and "MAX_TRADE_LOSS" not in v.reasons
    # no schedule at all: margined at 100 %, no leverage
    bare = {**SPECS, "PF_XBTUSD": dataclasses.replace(SPECS["PF_XBTUSD"], margin_levels=())}
    v = evaluate_perp(intent(20_000, 120), acc, view, bare, c, pol, params, T0 + 130, False)
    assert "INITIAL_MARGIN" in v.reasons
    assert margin.rate_ppm((), 1, margin.MAINTENANCE) == margin.PPM


def test_riskd_council_has_no_daily_freeze_no_fee_budget_no_delay(tmp_path):
    w = World(tmp_path)
    w.w.tick(T0 + 120)
    w.w.sim.open_portfolio(NAME, "council", T0 + 125)
    view, c = _account_view(w)
    acc = w.w.sim.states()[NAME]
    worse = dataclasses.replace(
        c,
        equity_24h_ago_ueur=2 * acc.capital_ueur,
        fees_month_ueur=10**12,
        last_open_ts={"PF_XBTUSD": T0 + 129},
    )
    v = evaluate_perp(
        intent(20_000, 120), acc, view, SPECS, worse, COUNCIL.policy, w.w.cfg.simulation, T0 + 130, False
    )
    assert v.approved, v.reasons
    v = evaluate_perp(
        intent(2_000, 300, NAME), acc, view, SPECS, worse, POLICY, w.w.cfg.simulation, T0 + 130, False
    )
    assert {"FROZEN", "FEE_BUDGET", "TOO_SOON"} <= set(v.reasons)


def test_the_simulator_uses_kraken_margins_for_the_council_only(tmp_path):
    from arene.journal import Journal

    levels = {"PF_XBTUSD": (MarginLevel(0, 10_000, 5_000),)}
    sim = PerpSimulator(
        Journal(tmp_path / "j.jsonl"), {"PF_XBTUSD": 1_000_000}, SimParams(), margin_levels=levels
    )
    fx = (1_100_000, 1_100_100)
    px = 70_000_000_000  # 70 000 USD
    for name in (NAME, HAIKU):
        sim.open_portfolio(name, "x", 0)
    qty = 4 * 1_100 * 100_000_000 // 70_000 * 1  # about 4x 1 000 EUR of BTC (1e-8 units)
    qty = qty // 10_000 * 10_000
    sim.market_order("c1", NAME, "PF_XBTUSD", qty, (px, px), fx, 60)  # 4x: Kraken's 1 % is covered
    with pytest.raises(Exception, match="initial margin"):
        sim.market_order("h1", HAIKU, "PF_XBTUSD", qty, (px, px), fx, 60)  # the AMF 50 % is not
    # a 10 % fall: the AMF rule (25 % of the gross) would close it out, Kraken's maintenance (0.5 %) does not
    low = px * 90 // 100
    fills, problems = sim.process_minute(120, {"PF_XBTUSD": MinuteCandles((low, low, low, low))}, fx)
    assert not problems and not fills and NAME in {n for n, a in sim.states().items() if a.positions}
    # a 25 % fall: the equity is gone, Kraken's maintenance liquidates
    gone = px * 75 // 100
    fills, _ = sim.process_minute(180, {"PF_XBTUSD": MinuteCandles((gone, gone, gone, gone))}, fx)
    assert [f["reason"] for f in fills] == ["margin_closeout"]


def test_the_watcher_never_freezes_the_council_and_halts_it_at_minus_90(tmp_path, monkeypatch):
    import arene.perp.watcher as W
    from arene.perp.riskd import PerpCounters

    w = World(tmp_path, llm=dataclasses.replace(LEAGUE, models=()))
    for name in (NAME, HAIKU):
        w.w.sim.open_portfolio(name, "x", T0)
    assert w.w.policy_for(NAME) is COUNCIL.policy and w.w.policy_for(HAIKU) is POLICY
    cap = 1_000_000_000
    # 24 h ago twice the equity, peak 2.5 times: -50 % in a day, -60 % from the peak
    monkeypatch.setattr(W, "counters_for", lambda ev, n, ts: PerpCounters(cap, 2 * cap, 5 * cap // 2))
    view, rep = _view(w, T0 + 120)
    w.w._controls(T0 + 120, view, w.events(), rep)
    halted = {p["portfolio"] for p in payloads(w, "portfolio_halted")}
    frozen = {p["portfolio"] for p in payloads(w, "portfolio_frozen")}
    assert NAME not in halted and NAME not in frozen and HAIKU in halted
    monkeypatch.setattr(W, "counters_for", lambda ev, n, ts: PerpCounters(cap, cap, 11 * cap))  # -91 %
    w.w._controls(T0 + 125, view, w.events(), rep)
    assert NAME in {p["portfolio"] for p in payloads(w, "portfolio_halted")}


def test_a_council_without_its_config_keeps_the_stricter_league_policy(tmp_path):
    w = World(tmp_path, llm=dataclasses.replace(LEAGUE, council=None))
    assert w.w.policy_for(NAME) is POLICY
    assert NAME not in {m.portfolio for m in w.w.llm.players}


# ---------------------------------------------------------------------- the record and the resume


def test_council_record_counts_closed_trades():
    def fill(ts, inst, qty, px, reason="intent", fee=1_000_000):
        return {"type": "perp_fill", "ts": ts, "payload": {
            "portfolio": NAME, "instrument": inst, "qty": qty, "price_uusd": px, "fee_ueur": fee,
            "fx_bid": 1_000_000, "fx_ask": 1_000_000, "reason": reason}}  # fmt: skip

    ev = [
        fill(0, "PF_XBTUSD", 100_000_000, 100_000_000_000),  # 1 BTC at 100 000
        fill(600, "PF_XBTUSD", -100_000_000, 101_000_000_000, "take_profit"),  # +1 000 USD
        fill(700, "PF_SOLUSD", -1_000_000_000, 200_000_000),  # short 10 SOL at 200
        fill(800, "PF_SOLUSD", 1_000_000_000, 210_000_000, "stop"),  # -100 USD
        fill(900, "PF_ETHUSD", 100_000_000, 3_000_000_000),  # still open
        {"type": "perp_fill", "ts": 950, "payload": {"portfolio": HAIKU}},
    ]
    r = council_record(ev, NAME, 1_000)
    assert r["trades_fermes"] == 2 and r["gagnants"] == 1 and r["taux_de_reussite_pct"] == 50
    assert r["gain_moyen_eur"] == "998.00" and r["perte_moyenne_eur"] == "-102.00"
    assert r["esperance_par_trade_eur"] == "448.00" and r["sorties_par_raison"] == {
        "take_profit": 1,
        "stop": 1,
    }
    assert r["positions_ouvertes"] == ["PF_ETHUSD"] and r["derniers_trades"][1]["sens"] == "short"
    assert council_record([], NAME, 1)["taux_de_reussite_pct"] is None


def test_resume_lifts_the_halt(tmp_path, capsys):
    from arene.journal import Journal
    from arene.perp.council import main

    var = tmp_path / "var-perp"
    sim = PerpSimulator(Journal(var / "journal" / "events.jsonl"), {})
    sim.open_portfolio(NAME, "council", 0)
    sim.append_event("portfolio_halted", {"portfolio": NAME, "reason": "drawdown", "until_ts": 0}, 1)
    assert main(["resume", "--var", str(var)]) == 0 and "resumed" in capsys.readouterr().out
    assert not PerpSimulator(Journal(var / "journal" / "events.jsonl"), {}).states()[NAME].halted
    assert main(["resume", "--var", str(var)]) == 0 and "nothing to do" in capsys.readouterr().out
