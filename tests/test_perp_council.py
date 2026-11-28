"""The Haiku council of the perp league (docs/SPEC-PERP-COUNCIL-HAIKU.md): ten members, its own aggressive
policy, Kraken's margins. Fake `claude` (tests/fake_claude.py), real MCP servers, the real watcher."""

from __future__ import annotations

import dataclasses
import json
import threading
from pathlib import Path

import pytest

from arena.perp import margin
from arena.perp.agent import OUTPUT_SCHEMA, AgentDecider, parse_decision, prompt_sha256
from arena.perp.agent_round import STANDARD_RULES, rules_text
from arena.perp.council import (
    ADVOCATE,
    MEMBERS,
    PROMPT_DIR,
    PRESIDENT,
    STAGE_A,
    CouncilConfigError,
    CouncilDecider,
    CouncilsLeague,
    council_record,
    load_council,
    load_councils_league,
    member_prompt,
    member_sha256,
    parse_opinion,
)
from arena.perp.ledger import replay
from arena.perp.llm_league import load_llm_league
from arena.perp.policy import AGGRESSIVE, PerpPolicyError, load_perp_policy
from arena.perp.riskd import LIQUIDATION_BEFORE_STOP, PerpIntent, evaluate_perp
from arena.perp.sim import MinuteCandles, PerpSimulator, SimParams
from arena.perp.types import MarginLevel
from tests.test_perp_agent import fake_runner
from tests.test_perp_llm_league import _view
from tests.test_perp_watcher import POLICY, SPECS, T0, World

COUNCIL = load_council()
NAME = COUNCIL.portfolio
OPUS = load_council(Path("config/perp-council-opus.toml"))
ONLY_HAIKU = CouncilsLeague(True, 4, (COUNCIL,), (), "league-sha")
HAIKU = "llm-perp:claude-haiku-5-5"
# one LLM portfolio beside the council keeps the tests short; no cadence (its own test below)
BASE = dataclasses.replace(load_llm_league(), cadence_min=0, rounds_per_day=48)
LEAGUE = dataclasses.replace(BASE, models=BASE.models[:1], councils=ONLY_HAIKU)
BIG_ENTRY = {
    "actions": [
        {
            "instrument": "PF_XBTUSD", "action": "open_long", "size_pct": 400, "stop_pct": 1.2,
            "take_profit_pct": 4, "horizon_h": 12, "expected_move_pct": 4, "confidence_pct": 60,
            "invalidation": "1 h close below the level",
        }
    ],
    "justification": "I am the Follower and the Treasurer, I discard the Contrarian",
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
            cfg = OPUS if m.portfolio == OPUS.portfolio else COUNCIL
            return CouncilDecider(cfg, tmp / "claude-empty", runner=counted)
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
        load_perp_policy(Path("config/policy-perp-council.toml"))
    with pytest.raises(PerpPolicyError, match="profile"):
        load_perp_policy(Path("config/policy-perp.toml"), profile=AGGRESSIVE)
    text = Path("config/policy-perp-council.toml").read_text()
    for bad in ("max_leverage_bp  = 100000", "drawdown_halt_bp     = 9000"):
        worse = text.replace(bad, bad.replace("100000", "110000").replace("9000", "9900"))
        f = tmp_path / "p.toml"
        f.write_text(worse)
        with pytest.raises(PerpPolicyError):
            load_perp_policy(f, profile=AGGRESSIVE)
    cfg = Path("config/perp-council.toml").read_text()
    for old, new in (
        ('model = "claude-haiku-5-5"', 'model = "claude-opus-5-5"'),
        ('portfolio = "council-perp:haiku"', 'portfolio = "llm-perp:haiku"'),
        ("members_parallel = 4", "members_parallel = 9"),
        ('policy = "policy-perp-council.toml"', 'policy = "policy-perp.toml"'),
    ):
        (tmp_path / "policy-perp-council.toml").write_text(text)
        (tmp_path / "policy-perp.toml").write_text(Path("config/policy-perp.toml").read_text())
        (tmp_path / "c.toml").write_text(cfg.replace(old, new))
        with pytest.raises(CouncilConfigError):
            load_council(tmp_path / "c.toml")
    # the default league config never loads the councils by itself (the watcher adds them)
    assert load_llm_league().councils is None and len(load_llm_league().players) == 4
    assert [m.portfolio for m in LEAGUE.players] == [HAIKU, NAME] and LEAGUE.players[-1].council


def test_eleven_members_with_their_role_sources_and_format():
    assert (
        len(MEMBERS) == 11 and len(STAGE_A) == 9 and ADVOCATE.key == "advocate" and PRESIDENT.key == "president"
    )
    assert "arbitrageur" in [m.key for m in STAGE_A]
    shas = set()
    for m in MEMBERS:
        text = member_prompt(m)
        read = lambda p: p.read_text(encoding="utf-8").strip()  # noqa: E731
        assert (
            read(PROMPT_DIR / "common.md") in text
            and read(PROMPT_DIR / "roles" / m.file) in text
            and "Haiku" not in text  # the same prompts for both councils: nothing tells the President's model
        )
        assert (read(PROMPT_DIR / "president.md") in text) == (m is PRESIDENT) and (
            read(PROMPT_DIR / "opinions.md") in text
        ) == (m is not PRESIDENT)
        shas.add(member_sha256(m))
    assert len(shas) == 11
    # the neutral models keep their prompt and their schema
    assert prompt_sha256() == AgentDecider("m", "p", Path("/tmp")).prompt_digest()
    assert OUTPUT_SCHEMA["properties"]["actions"]["items"]["properties"]["size_pct"]["maximum"] == 100


def test_rules_line_of_the_snapshot():
    from dataclasses import asdict

    assert rules_text({**asdict(POLICY), "instruments": []}) == STANDARD_RULES
    line = rules_text({**asdict(COUNCIL.policy), "instruments": []})
    assert "max leverage 10x" in line and "entry <= 500%" in line and "before liquidation" in line
    assert "halt at -90%" in line and "24 opens" in line


def test_parse_opinion_rules():
    ok, err = parse_opinion(
        {
            "opinions": [{"instrument": "PF_ETHUSD", "position": "short", "conviction": 70, "size_pct": 250.5}],
            "target": None,
            "argument": "x" * 900,
        }
    )
    assert err is None and ok["opinions"][0]["size_pct"] == "250.5" and len(ok["argument"]) == 600
    for bad in (
        {"opinions": [], "argument": "x", "decision": 1},
        {"opinions": [{"instrument": "PF_DOGEUSD", "position": "long", "conviction": 5}], "argument": "x"},
        {"opinions": [{"instrument": "PF_ETHUSD", "position": "long", "conviction": 101}], "argument": "x"},
        {"opinions": [{"instrument": "PF_ETHUSD", "position": "long", "conviction": True}], "argument": "x"},
        {
            "opinions": [{"instrument": "PF_ETHUSD", "position": "long", "conviction": 5, "size_pct": 2000}],
            "argument": "x",
        },
        {"opinions": [], "argument": "x", "target": {"instrument": "PF_ETHUSD", "side": "flat"}},
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
    assert calls.count("claude-haiku-5-5") == 1 + 11  # the Haiku portfolio, then the eleven members
    ops = payloads(w, "council_opinion", NAME)
    assert [o["member"] for o in ops] == [m.key for m in (*STAGE_A, ADVOCATE)]
    assert all(o["opinion"] is not None and o["error"] is None and o["cost_uusd"] == 12346 for o in ops)
    assert {o["persona_sha256"] for o in ops} == {member_sha256(m) for m in (*STAGE_A, ADVOCATE)}
    assert ops[-1]["opinion"]["target"] == {"instrument": "PF_XBTUSD", "side": "long"}
    [d] = payloads(w, "agent_decision", NAME)
    assert d["prompt_sha256"] == member_sha256(PRESIDENT) and d["cost_uusd"] == 11 * 12346
    assert d["council"]["members_ok"] == 10 and d["council"]["members_failed"] == []
    assert d["council"]["president_model"] == "claude-haiku-5-5" and d["council"]["name"] == "Haiku Council"
    assert d["council"]["members_model"] == "claude-haiku-5-5" and d["council"]["prompts_version"] == "v3"
    assert d["model_requested"] == "claude-haiku-5-5"
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
    assert rd["council_config_sha256"] == COUNCIL.sha256 and rd["councils_league_sha256"] == "league-sha"
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
    assert len(calls) == 12


def test_stage_a_opinions_are_independent(tmp_path):
    w, _, _ = council_world(tmp_path)
    [rd] = payloads(w, "round_data", NAME)
    base = w.var / rd["path"] / "members"
    stdin = {m.key: (base / m.key / "stdin.txt").read_text() for m in MEMBERS}
    first = {stdin[m.key] for m in STAGE_A}
    assert len(first) == 1  # the nine members of stage A get the same message...
    msg = first.pop()
    assert "<council_opinions>" not in msg and "low funding" not in msg  # ...without anyone's opinion
    assert "council_summary" in msg
    import hashlib

    assert rd["message_sha256"] == hashlib.sha256(msg.encode()).hexdigest()
    seen = json.loads(stdin["advocate"].split("<council_opinions>\n")[1].split("\n</council_opinions>")[0])
    assert [o["role"] for o in seen] == [m.key for m in STAGE_A]
    final = json.loads(stdin["president"].split("<council_opinions>\n")[1].split("\n</council_opinions>")[0])
    assert [o["role"] for o in final] == [m.key for m in (*STAGE_A, ADVOCATE)]
    # each member has its own round directory and MCP server (its own tool budget)
    assert all(
        json.loads((base / m.key / "round.json").read_text())["meta"]["portfolio"] == NAME for m in MEMBERS
    )


def test_a_failed_member_is_left_out_and_a_failed_president_decides_nothing(tmp_path):
    w, _, _rep = council_world(tmp_path / "a", {"fail": ["contrarian"], "president": BIG_ENTRY})
    ops = {o["member"]: o for o in payloads(w, "council_opinion", NAME)}
    assert ops["contrarian"]["opinion"] is None and ops["contrarian"]["error"]
    assert ops["contrarian"]["cost_uusd"] == COUNCIL_CEILING_UUSD  # it used the model: charged its ceiling
    [d] = payloads(w, "agent_decision", NAME)
    assert d["council"]["members_failed"] == ["contrarian"] and d["parse_error"] is None
    assert payloads(w, "perp_verdict", NAME)
    president = w.var / payloads(w, "round_data", NAME)[0]["path"] / "members" / "president" / "stdin.txt"
    assert '"contrarian"' not in president.read_text()

    w, _, _ = council_world(tmp_path / "b", {"fail": ["president"], "president": BIG_ENTRY})
    [d] = payloads(w, "agent_decision", NAME)
    assert d["parsed"] is None and str(d["parse_error"]).startswith("president")
    assert not payloads(w, "perp_verdict", NAME) and len(payloads(w, "council_opinion", NAME)) == 10
    assert any(e["type"] == "perp_round_done" for e in w.events())


COUNCIL_CEILING_UUSD = 50_000  # 1 $ for the round (max_budget_usd of the league), a twentieth per adviser


def test_a_crash_inside_the_council_never_loses_the_cost_of_its_calls(tmp_path, monkeypatch):
    import arena.perp.council as C

    real = C.MemberDecider.decide

    def paid_then_crash(self, round_dir, snapshot):
        res = real(self, round_dir, snapshot)
        if self.member.key == "order_book":
            raise ValueError("parse bug after the call")
        return res

    monkeypatch.setattr(C.MemberDecider, "decide", paid_then_crash)
    w, _, _ = council_world(tmp_path / "a")
    ops = {o["member"]: o for o in payloads(w, "council_opinion", NAME)}
    assert (
        ops["order_book"]["opinion"] is None and ops["order_book"]["cost_uusd"] == 12346
    )  # read back from its stream
    [d] = payloads(w, "agent_decision", NAME)
    assert d["cost_uusd"] == 11 * 12346 and d["council"]["members_failed"] == ["order_book"]

    def broken_record(self, m, r):
        raise OSError("prompt file unreadable")

    monkeypatch.setattr(C.CouncilDecider, "_record", broken_record)
    w, _, _ = council_world(tmp_path / "b")
    [d] = payloads(w, "agent_decision", NAME)
    assert str(d["parse_error"]).startswith("council crashed") and d["cost_uusd"] == 9 * 12346
    assert not payloads(w, "perp_verdict", NAME)


def test_a_cut_during_the_council_is_never_replayed(tmp_path, monkeypatch):
    calls: list[str] = []
    w = World(tmp_path, llm=LEAGUE, factory=council_factory(tmp_path, calls))
    import arena.perp.council as C

    real = C.MemberDecider.decide

    def cut(self, round_dir, snapshot):
        if self.member.key == "advocate":
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
    # the nine members of stage A were paid (0.0123456 $ each, from their streams): counted in the budget
    from arena.perp.llm_league import spent_today_uusd

    assert skipped[0]["cost_uusd"] == 9 * 12346 and spent_today_uusd(w.events(), NAME, T0 + 420) == 9 * 12346


def test_opinions_of_a_round_cut_before_its_decision_count_in_the_budget():
    from arena.perp.llm_league import spent_today_uusd

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
    assert len(calls) == 12
    w.advance(T0 + 720)
    w.w.tick(T0 + 720)
    rounds = [p for p in payloads(w, "perp_round") if p["kind"] == "private"]
    assert rounds and rounds[-1]["portfolios"] == sorted([HAIKU, NAME])
    assert rounds[-1]["triggers"][NAME]["kind"] == "cadence" and len(calls) == 24
    assert w.w.quota(w.events(), NAME, T0 + 720)["played_today"] == 2  # one round of the council, not eleven


# ---------------------------------------------------------------------- the aggressive policy and the margins


def _account_view(w):
    from arena.perp.counters import counters_for
    from arena.perp.market import market_view

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
    from arena.journal import Journal

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
    import arena.perp.watcher as W
    from arena.perp.riskd import PerpCounters

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
    w = World(tmp_path, llm=dataclasses.replace(LEAGUE, councils=None))
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
    assert r["closed_trades"] == 2 and r["winners"] == 1 and r["win_rate_pct"] == 50
    assert r["avg_gain_eur"] == "998.00" and r["avg_loss_eur"] == "-102.00"
    assert r["expectancy_per_trade_eur"] == "448.00" and r["exits_by_reason"] == {
        "take_profit": 1,
        "stop": 1,
    }
    assert r["open_positions"] == ["PF_ETHUSD"] and r["last_trades"][1]["side"] == "short"
    assert council_record([], NAME, 1)["win_rate_pct"] is None


def test_resume_lifts_the_halt(tmp_path, capsys):
    from arena.journal import Journal
    from arena.perp.council import main

    var = tmp_path / "var-perp"
    sim = PerpSimulator(Journal(var / "journal" / "events.jsonl"), {})
    live = load_councils_league().councils[0].portfolio  # the league lists one council (the v4): no --portfolio needed
    assert live == "council-perp:trend-1x"
    sim.open_portfolio(live, "council", 0)
    sim.append_event("portfolio_halted", {"portfolio": live, "reason": "drawdown", "until_ts": 0}, 1)
    assert main(["resume", "--portfolio", "council-perp:nope", "--var", str(var)]) == 2
    assert main(["resume", "--portfolio", NAME, "--var", str(var)]) == 2  # a retired council is not in the league
    assert main(["resume", "--var", str(var)]) == 0 and "resumed" in capsys.readouterr().out
    assert not PerpSimulator(Journal(var / "journal" / "events.jsonl"), {}).states()[live].halted
    assert main(["resume", "--portfolio", live, "--var", str(var)]) == 0
    assert "nothing to do" in capsys.readouterr().out


# ---------------------------------------------------------------------- the league of the councils


# The league file as it was while both councils played (the live file no longer lists them once retired).
TWO_COUNCILS = """enabled = true
max_member_processes = 4
councils = ["perp-council.toml", "perp-council-opus.toml"]
"""


def test_the_league_of_the_councils_config(tmp_path):
    (tmp_path / "council-league.toml").write_text(TWO_COUNCILS)
    for f in ("policy-perp-council.toml", "perp-council.toml", "perp-council-opus.toml"):
        (tmp_path / f).write_text(Path("config", f).read_text())
    league = load_councils_league(tmp_path / "council-league.toml")
    assert [c.portfolio for c in league.councils] == ["council-perp:haiku", "council-perp:opus"]
    assert league.errors == () and league.max_member_processes == 4
    haiku, opus = COUNCIL, OPUS  # still loadable, as history
    assert (haiku.name, haiku.model, haiku.president_model) == (
        "Haiku Council",
        "claude-haiku-5-5",
        "claude-haiku-5-5",
    )
    assert (opus.name, opus.model, opus.president_model) == (
        "Opus Council",
        "claude-haiku-5-5",
        "claude-opus-5-5",
    )
    # the same advisers, prompts and policy: only the President (and its budget and timeout) differ
    assert opus.policy.sha256 == haiku.policy.sha256 and opus.members_parallel == haiku.members_parallel
    assert opus.daily_budget_uusd == 25_000_000 and haiku.daily_budget_uusd == 10_000_000
    assert opus.president_timeout_s == 240 and haiku.president_timeout_s == 90
    # a bad council is left out alone; a bad league file is an error
    opus_bad = (
        Path("config/perp-council-opus.toml").read_text().replace("claude-opus-5-5", "claude-fable-5-2")
    )
    (tmp_path / "perp-council-opus.toml").write_text(opus_bad)
    (tmp_path / "l.toml").write_text(TWO_COUNCILS)
    got = load_councils_league(tmp_path / "l.toml")
    assert [c.portfolio for c in got.councils] == [NAME] and "president_model" in got.errors[0]
    (tmp_path / "l.toml").write_text(TWO_COUNCILS + "extra = 1\n")
    with pytest.raises(CouncilConfigError):
        load_councils_league(tmp_path / "l.toml")
    off = TWO_COUNCILS.replace("enabled = true", "enabled = false")
    (tmp_path / "l.toml").write_text(off)
    assert load_councils_league(tmp_path / "l.toml").councils == ()
    # each council reads its own policy: the league's players (the retired two, loaded as history)
    both_old = CouncilsLeague(True, 4, (haiku, opus), (), "old-league-sha")
    lg = dataclasses.replace(BASE, councils=both_old)
    assert [m.portfolio for m in lg.players][-2:] == [NAME, OPUS.portfolio]
    assert lg.players[-1].model == "claude-opus-5-5" and lg.council(OPUS.portfolio) is opus


def test_the_ceilings_of_a_round_favour_the_president():
    d = CouncilDecider(OPUS, Path("/tmp"))
    assert d.member_ceiling_uusd(STAGE_A[0]) == 50_000 and d.member_ceiling_uusd(ADVOCATE) == 50_000
    assert d.member_ceiling_uusd(PRESIDENT) == 500_000  # 10 x 0.05 + 0.50 = the round's 1 $
    assert d.model == "claude-opus-5-5"
    president = d._member(PRESIDENT, [], "0.5")
    adviser = d._member(STAGE_A[0], None, "0.05")
    assert (president.model, president.timeout_s) == ("claude-opus-5-5", 240.0)
    assert (adviser.model, adviser.timeout_s) == ("claude-haiku-5-5", 90.0)


def test_two_councils_play_the_same_round_haiku_and_opus_presidents(tmp_path):
    both = CouncilsLeague(True, 2, (COUNCIL, OPUS), (), "league-sha")
    lg = dataclasses.replace(LEAGUE, councils=both)
    w, calls, rep = council_world(tmp_path, {"president": BIG_ENTRY}, league=lg)
    assert not rep.problems, rep.problems
    assert calls.count("claude-opus-5-5") == 1 and calls.count("claude-haiku-5-5") == 1 + 11 + 10
    for name, pres in ((NAME, "claude-haiku-5-5"), (OPUS.portfolio, "claude-opus-5-5")):
        ops = payloads(w, "council_opinion", name)
        assert [o["member"] for o in ops] == [m.key for m in (*STAGE_A, ADVOCATE)]
        [d] = payloads(w, "agent_decision", name)
        assert d["council"]["president_model"] == pres and d["model_requested"] == pres
        assert d["prompt_sha256"] == member_sha256(PRESIDENT)  # the same prompts for both
        [v] = payloads(w, "perp_verdict", name)
        assert v["approved"] and v["policy_sha256"] == COUNCIL.policy.sha256
    opened = {p["portfolio"]: (p["kind"], p["league"]) for p in payloads(w, "portfolio_opened")}
    assert opened[OPUS.portfolio] == ("council", "perp")  # same engine and journal; the site shows them apart
    assert w.w.policy_for(OPUS.portfolio) is OPUS.policy


def test_member_processes_are_bounded_across_the_councils(tmp_path):
    both = CouncilsLeague(True, 2, (COUNCIL, OPUS), (), "league-sha")
    lg = dataclasses.replace(LEAGUE, models=(), councils=both)
    lock = threading.Lock()
    live, peak = [0], [0]
    plain = fake_runner("normal")

    def runner(cmd, stdin, env, cwd, timeout):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        try:
            return plain(cmd, stdin, {**env, "FAKE_CLAUDE_COUNCIL": "{}"}, cwd, timeout)
        finally:
            with lock:
                live[0] -= 1

    w = World(tmp_path, llm=lg)  # the league's own deciders (with the shared slots), only the runner is fake
    import arena.perp.llm_league as L

    real = L.CouncilDecider

    def with_runner(*a, **k):
        return real(*a, **{**k, "runner": runner})

    L.CouncilDecider = with_runner
    try:
        rep = w.w.tick(T0 + 120)
    finally:
        L.CouncilDecider = real
    assert not rep.problems, rep.problems
    assert (
        len(payloads(w, "agent_decision", NAME)) == 1
        and len(payloads(w, "agent_decision", OPUS.portfolio)) == 1
    )
    assert peak[0] == 2


def test_a_council_that_never_played_is_due_at_the_next_tick(tmp_path):
    lg = dataclasses.replace(LEAGUE, models=(), cadence_min=10)
    w, calls, _ = council_world(tmp_path, league=lg)
    assert len(calls) == 11  # the scheduled round of T0
    both = CouncilsLeague(True, 4, (COUNCIL, OPUS), (), "league-sha")
    w.w.llm = dataclasses.replace(lg, councils=both)
    w.w.decider_factory = council_factory(tmp_path, calls)
    w.advance(T0 + 420)
    w.w.tick(T0 + 420)  # the Haiku council is not due yet; the Opus council never played: due now
    [d] = payloads(w, "agent_decision", OPUS.portfolio)
    assert (
        d["council"]["president_model"] == "claude-opus-5-5" and len(payloads(w, "agent_decision", NAME)) == 1
    )
    rnd = [p for p in payloads(w, "perp_round") if p["kind"] == "private"][-1]
    assert rnd["portfolios"] == [OPUS.portfolio] and rnd["triggers"][OPUS.portfolio]["last_round_ts"] is None


# ---------------------------------------------------------------------- retiring a council (17/11/2026)


def _retired_world(tmp_path, monkeypatch, *, position: bool = True):
    """A watcher world with the Haiku council opened, holding one long with a stop and one pending alert."""
    import arena.perp.watcher as W

    monkeypatch.setattr(W, "load_specs", lambda var, symbols, now_ts, client=None: SPECS)
    w = World(tmp_path, llm=dataclasses.replace(LEAGUE, models=()))
    sim = w.w.sim
    sim.open_portfolio(NAME, "council", T0)
    px = w.prices["PF_XBTUSD"]
    if position:
        sim.market_order("c-open", NAME, "PF_XBTUSD", 6_280_000, (px, px + 1_000_000), (1_100_000, 1_100_100), T0 + 30)
        sim.set_conditional(NAME, "PF_XBTUSD", "stop", px * 95 // 100, T0 + 31)
    sim.append_event(
        "agent_orders_set",
        {
            "portfolio": NAME, "round": T0, "created_ts": T0 + 40, "rejected": [], "entry_orders": [],
            "alerts": [
                {"id": "a1", "instrument": "PF_XBTUSD", "condition": "below", "price_uusd": px * 9 // 10,
                 "note": "", "expires_ts": T0 + 86_400}
            ],
        },
        T0 + 40,
    )  # fmt: skip
    return w


def test_retire_flattens_journals_and_replays(tmp_path, monkeypatch):
    from arena.perp.retired import retired_portfolio

    w = _retired_world(tmp_path, monkeypatch)
    assert w.w.sim.states()[NAME].positions
    out = retired_portfolio(w.var, NAME, T0 + 120)
    assert out == {"status": "retired", "fills": 1, "orders_ended": 1}
    [fill] = [p for p in payloads(w, "perp_fill", NAME) if p["reason"] == "retired"]
    assert fill["qty"] == -6_280_000
    [ended] = payloads(w, "agent_order_ended", NAME)
    assert ended["id"] == "a1" and ended["reason"] == "portfolio_retired"
    [ev] = [e for e in w.events("portfolio_retired")]
    assert ev["payload"] == {"portfolio": NAME, "ts": T0 + 120, "reason": "manual", "note": ""}
    # a last measure of the portfolio, then the retirement closes the journal of the council
    assert [e["type"] for e in w.events()][-1] == "portfolio_retired"
    assert any(p["ts"] == T0 + 120 for p in payloads(w, "perp_equity", NAME))
    acc = replay(w.events())[NAME]  # the whole journal replays, the account is flat and retired
    assert acc.retired and acc.retired_ts == T0 + 120 and not acc.positions and acc.invariant_ok()
    px = w.prices["PF_XBTUSD"]
    with pytest.raises(Exception, match="retired"):  # never opens again
        w.w.sim.market_order("c-again", NAME, "PF_XBTUSD", 1_000_000, (px, px + 1_000_000), (1_100_000, 1_100_100), T0 + 200)


def test_retire_is_idempotent(tmp_path, monkeypatch):
    from arena.perp.retired import retired_portfolio

    w = _retired_world(tmp_path, monkeypatch)
    retired_portfolio(w.var, NAME, T0 + 120)
    n = len(w.events())
    assert retired_portfolio(w.var, NAME, T0 + 500) == {"status": "already_retired", "fills": 0, "orders_ended": 0}
    assert len(w.events()) == n


def test_retire_fails_closed_without_a_fresh_quote(tmp_path, monkeypatch):
    from arena.perp.retired import RetiredError, retired_portfolio

    w = _retired_world(tmp_path, monkeypatch)
    n = len(w.events())
    with pytest.raises(RetiredError, match="no fresh quote"):
        retired_portfolio(w.var, NAME, T0 + 5_000)  # the last snapshot is 83 minutes old
    assert len(w.events()) == n and not replay(w.events())[NAME].retired


def test_retire_refuses_a_non_council_and_waits_for_the_watcher_lock(tmp_path, monkeypatch):
    import fcntl
    import os

    from arena.perp.retired import RetiredError, retired_portfolio

    w = _retired_world(tmp_path, monkeypatch)
    with pytest.raises(RetiredError, match="only a council"):
        retired_portfolio(w.var, "benchmark-perp:basket-1x", T0 + 120)
    fd = os.open(w.var / "watcher.lock", os.O_CREAT | os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)  # a tick is running
    try:
        n = len(w.events())
        with pytest.raises(RetiredError, match="lock still busy"):
            retired_portfolio(w.var, NAME, T0 + 120, lock_wait_s=0.2)
        assert len(w.events()) == n
    finally:
        os.close(fd)


def test_retire_cli_and_the_resume_refusal(tmp_path, monkeypatch, capsys):
    from arena.perp.council import main

    w = _retired_world(tmp_path, monkeypatch, position=False)
    assert main(["retired", "--var", str(w.var)]) == 2  # which council?
    assert main(["retired", "--portfolio", NAME, "--var", str(w.var), "--reason", "overhaul", "--note", "17/11"]) == 0
    assert "retired (0 position(s) flattened, 1 order(s) ended)" in capsys.readouterr().out
    assert main(["retired", "--portfolio", NAME, "--var", str(w.var)]) == 0
    assert "already retired" in capsys.readouterr().out
    [ev] = w.events("portfolio_retired")
    assert ev["payload"]["reason"] == "overhaul" and ev["payload"]["note"] == "17/11"
    assert main(["resume", "--portfolio", NAME, "--var", str(w.var)]) == 2  # a retired council never plays again
    assert "never plays again" in capsys.readouterr().err


def test_a_retired_council_is_skipped_by_the_league_even_if_listed(tmp_path, monkeypatch):
    from arena.perp.council import retired_portfolios

    both = CouncilsLeague(True, 4, (COUNCIL, OPUS), (), "league-sha")
    assert both.without(frozenset()) is both
    assert [c.portfolio for c in both.without({NAME}).councils] == [OPUS.portfolio]
    w = _retired_world(tmp_path, monkeypatch, position=False)
    w.w.sim.append_event("portfolio_retired", {"portfolio": NAME, "ts": T0 + 60, "reason": "manual", "note": ""}, T0 + 60)
    assert retired_portfolios(w.events()) == {NAME}
    # the file is still listed (the watcher is built with the league as is): the round never calls it
    calls: list[str] = []
    w.w.llm = dataclasses.replace(LEAGUE, models=(), councils=ONLY_HAIKU)
    w.w.decider_factory = council_factory(tmp_path, calls)
    rep = w.w.tick(T0 + 120)
    assert not calls and not payloads(w, "agent_decision", NAME) and not payloads(w, "perp_llm_skipped", NAME)
    assert not rep.problems, rep.problems
    assert not [p for p in payloads(w, "perp_equity", NAME) if p["ts"] > T0 + 60]  # no more measure either
