"""Frozen season (config [season], season_* events, freeze, waiver, status): real journal, fake market."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from arena import cli, season
from arena import cycle as cyc
from arena import watch
from arena.config import ConfigError, load_config, sha256_outside_season
from arena.deciders.llm import prompt_sha256
from arena.journal import Journal, verify
from arena.ledger import equity_ueur, replay
from arena.paths import REPO
from arena.risk.policy import load_policy
from tests.fakes import H4, T0, Env
from tests.test_watch import X, cycle, deciders, make_env, prepare, tick

DAY = 86_400


def of(env: Env, *types: str) -> list[dict]:
    return env.of_type(*types)


def pl(env: Env, t: str) -> list[dict]:
    return [e["payload"] for e in env.of_type(t)]


def codes(env: Env) -> list[tuple[str, str]]:
    return [(a["level"], a["code"]) for a in pl(env, "alert")]


def season_env(tmp_path: Path, name: str = "e", *, start: int = T0 + 300, days: int = 1) -> Env:
    env = make_env(tmp_path, name)
    set_season(env, start_ts=start, duration_days=days)
    return env


def set_season(env: Env, **kw: int | str) -> None:
    txt = env.paths.config.read_text()
    for k, v in kw.items():
        new = f'{k} = "{v}"' if isinstance(v, str) else f"{k} = {v}"
        txt, n = re.subn(rf"^{k} = .*$", new, txt, count=1, flags=re.MULTILINE)
        assert n == 1, k
    env.paths.config.write_text(txt)


def set_fee(env: Env, fee: int) -> None:
    txt = env.paths.config.read_text()
    env.paths.config.write_text(re.sub(r"^taker_fee_bp = \d+", f"taker_fee_bp = {fee}", txt, flags=re.MULTILINE))


def hashes(env: Env) -> dict[str, str]:
    return {
        "config_sha256": load_config(env.paths.config).sha256_outside_season,
        "policy_sha256": load_policy(env.paths.policy).sha256,
        "prompt_sha256": prompt_sha256(),
        "code_sha256": season.code_sha256(env.paths.repo),
    }


def waiver(env: Env, reason: str) -> None:
    (env.paths.var).mkdir(parents=True, exist_ok=True)
    (env.paths.var / "SEASON_WAIVER").write_text(reason + "\n")


# ---------------------------------------------------------------------------------------------- config


def test_start_ts_of_season_1_is_november_13_2026_at_00h05_utc():
    cfg = load_config(REPO / "config" / "arena.toml")
    s = cfg.season
    assert (s.number, s.name, s.start_ts, s.duration_days) == (1, "Season 1", 1794528300, 56)
    assert datetime.fromtimestamp(s.start_ts, UTC) == datetime(2026, 11, 13, 0, 5, tzinfo=UTC)
    assert (s.start_ts - cfg.cycle_delay_s) % cfg.interval_s == 0  # the decision time of the 00:00 cycle


def test_season_table_is_optional_and_validated(tmp_path: Path):
    text = (REPO / "config" / "arena.toml").read_text()
    p = tmp_path / "c.toml"
    without = re.sub(r"\[season\].*?(?=\[\[instruments\]\])", "", text, flags=re.DOTALL)
    assert "[season]" not in without
    p.write_text(without)
    cfg = load_config(p)
    assert cfg.season is None and cfg.sha256_outside_season == sha256_outside_season(without.encode())
    for bad in ("number = 0", 'number = "1"', 'name = ""', "name = 3", "start_ts = 0", "start_ts = 1.5", "duration_days = 0"):
        key = bad.split(" = ")[0]
        p.write_text(re.sub(rf"^{key} = .*$", bad, text, flags=re.MULTILINE))
        with pytest.raises(ConfigError):
            load_config(p)
    p.write_text(text.replace("duration_days = 56", "duration_days = 56\nextra = 1"))
    with pytest.raises(ConfigError):
        load_config(p)
    p.write_text(text.replace("duration_days = 56\n", ""))  # missing key
    with pytest.raises(ConfigError):
        load_config(p)


def test_config_hash_outside_season_is_on_the_parsed_toml(tmp_path: Path):
    raw = (REPO / "config" / "arena.toml").read_bytes()
    base = sha256_outside_season(raw)
    assert sha256_outside_season(raw.replace(b'name = "Season 1"', b'name = "Other"')) == base
    assert sha256_outside_season(raw.replace(b"duration_days = 56", b"duration_days = 30")) == base
    # Parsed, not read line by line: comments, whitespace and formatting have no effect ...
    assert sha256_outside_season(raw.replace(b"taker_fee_bp = 50", b"taker_fee_bp   =   50   # note")) == base
    assert sha256_outside_season(raw.replace(b"e0065 = { L = 20, k = 3, H = 10 }", b"e0065 = { H = 10,   L = 20, k = 3 }")) == base
    assert sha256_outside_season(raw.replace(b"[season]\n", b"[season]\n\n\n")) == base
    assert sha256_outside_season(b"# another comment\n" + raw) == base
    # ... and any value that changes counts.
    assert sha256_outside_season(raw.replace(b"taker_fee_bp = 50", b"taker_fee_bp = 51")) != base
    assert sha256_outside_season(raw.replace(b"max_wakeups_per_day = 6", b"max_wakeups_per_day = 5")) != base
    assert sha256_outside_season(raw.replace(b"daily_budget_usd = 0.10", b"daily_budget_usd = 0.11")) != base
    # The [season] table placed elsewhere in the file changes nothing either (no line-based reading).
    text = raw.decode()
    table = text[text.index("[season]") : text.index("[[instruments]]")]
    moved = (text.replace(table, "") + "\n" + table).encode()
    assert moved != raw and sha256_outside_season(moved) == base
    assert load_config(REPO / "config" / "arena.toml").sha256 != base  # the full hash includes the table


# ---------------------------------------------------------------------------------------------- events


def test_season_started_reference_ended_written_once_at_the_right_cycles(tmp_path: Path):
    env = season_env(tmp_path, start=T0 + 2 * H4 + 300, days=1)
    d = deciders()
    for i in range(10):
        assert cycle(env, i, d).status == "completed"
    t0, tf = T0 + 2 * H4, T0 + 8 * H4
    [start] = of(env, "season_started")
    cfg = load_config(env.paths.config)
    p = start["payload"]
    assert set(p) == {
        "number", "name", "cycle", "planned_cycle_end", "start_ts", "duration_days", "config_sha256", "policy_sha256",
        "prompt_sha256", "code_sha256", "git_head", "claude_cli_version", "portfolios",
    }  # fmt: skip
    assert (p["start_ts"], p["duration_days"], p["claude_cli_version"]) == (T0 + 2 * H4 + 300, 1, None)
    assert p["code_sha256"] == season.code_sha256(REPO) and p["code_sha256"]
    assert (p["number"], p["name"], p["cycle"], p["planned_cycle_end"]) == (1, "Season 1", t0, tf)
    assert {k: p[k] for k in ("config_sha256", "policy_sha256", "prompt_sha256", "code_sha256")} == hashes(env)
    assert p["config_sha256"] == cfg.sha256_outside_season != cfg.sha256
    assert p["portfolios"] == [m.portfolio for m in cfg.models] + list(cfg.benchmarks.portfolios)
    assert isinstance(p["git_head"], str) and p["git_head"]
    # Before the decisions of the start cycle, after its cycle_started.
    seq = lambda typ, **kw: [e["seq"] for e in of(env, typ) if all(e["payload"].get(k) == v for k, v in kw.items())]
    assert seq("cycle_started", cycle=t0)[0] < start["seq"] < min(seq("decision_requested", cycle=t0) + seq("intent", cycle=t0))
    # Reference: right after season_started, BEFORE the decisions (hence before any fill, intent or equity of the cycle),
    # equity at the bid with this cycle's quotes.
    [ref] = of(env, "season_reference")
    first_decision = min(seq("decision_requested", cycle=t0) + seq("intent", cycle=t0) + [e["seq"] for e in of(env, "fill") if e["ts"] == t0])
    assert start["seq"] < ref["seq"] < first_decision and ref["seq"] == start["seq"] + 1
    quotes = {e["payload"]["symbol"]: e["payload"]["bid"] for e in of(env, "quote") if e["ts"] == env.now_of(2)}
    assert len(quotes) == 6
    before = replay(env.events()[: ref["seq"]])
    expected = {p: equity_ueur(st, quotes, quotes) for p, st in sorted(before.items())}
    assert ref["payload"] == {"number": 1, "cycle": t0, "equity": expected} and len(expected) == 8
    assert any(st.positions for st in before.values())  # positions already open: the equity is not trivial
    eq0 = {e["payload"]["portfolio"]: e["payload"]["equity_ueur"] for e in of(env, "equity") if e["payload"]["cycle"] == t0}
    # End: at the first cycle with t >= planned_cycle_end.
    [end] = of(env, "season_ended")
    eqf = {e["payload"]["portfolio"]: e["payload"]["equity_ueur"] for e in of(env, "equity") if e["payload"]["cycle"] == tf}
    assert end["payload"] == {"number": 1, "cycle": tf, "equity": dict(sorted(eqf.items()))}
    assert max(seq("equity", cycle=tf)) < end["seq"] < seq("cycle_completed", cycle=tf)[0]
    assert len(eq0) == 8 and len(eqf) == 8
    assert not [e for e in of(env, "season_started", "season_reference", "season_ended") if e["payload"]["cycle"] < t0]
    assert not pl(env, "season_waiver")
    assert verify(env.paths.journal).ok
    replay(env.events())


def test_idempotence_and_resume_after_crash_between_start_and_reference(tmp_path: Path, monkeypatch):
    env = season_env(tmp_path, days=56)
    real, hit = Journal.append, []

    def flaky(self, type, payload, ts):
        if type == "season_reference" and not hit:
            hit.append(1)
            raise RuntimeError("crash between season_started and season_reference")
        return real(self, type, payload, ts)

    monkeypatch.setattr(Journal, "append", flaky)
    assert cycle(env, 0).status == "failed"
    monkeypatch.setattr(Journal, "append", real)  # (no undo: it would also remove the conftest guards)
    assert len(of(env, "season_started")) == 1 and not of(env, "season_reference")  # crash between the two
    assert not of(env, "decision_requested")  # no decision took place
    rep = cycle(env, 0)
    assert rep.status == "completed" and rep.resumed
    assert len(of(env, "season_started")) == 1
    [ref] = of(env, "season_reference")
    assert ref["payload"]["cycle"] == T0 and set(ref["payload"]["equity"]) == set(hashes_portfolios(env))
    assert ref["seq"] < min(e["seq"] for e in of(env, "decision_requested", "intent", "fill"))  # written before the decisions
    before = env.paths.journal.read_bytes()
    assert cycle(env, 0).status == "already_done" and env.paths.journal.read_bytes() == before
    cycle(env, 1)
    assert len(of(env, "season_started")) == len(of(env, "season_reference")) == 1 and not of(env, "season_ended")


def hashes_portfolios(env: Env) -> list[str]:
    cfg = load_config(env.paths.config)
    return [m.portfolio for m in cfg.models] + list(cfg.benchmarks.portfolios)


# ---------------------------------------------------------------------------------------------- freeze


def change(env: Env, what: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> str:
    """Changes ONE frozen hash; returns its key."""
    if what == "config":
        set_fee(env, 51)
        return "config_sha256"
    if what == "policy":
        pol = tmp_path / f"policy-{env.root.name}.toml"
        pol.write_text(env.paths.policy.read_text() + "\n# changement\n")
        env.paths = replace(env.paths, policy=pol)
        return "policy_sha256"
    monkeypatch.setattr(cyc, "prompt_sha256", lambda: "f" * 64)
    monkeypatch.setattr(watch, "prompt_sha256", lambda: "f" * 64)
    return "prompt_sha256"


@pytest.mark.parametrize("what", ["config", "policy", "prompt"])
def test_refused_when_a_frozen_hash_changes_one_at_a_time(tmp_path: Path, monkeypatch, what: str):
    env = season_env(tmp_path, days=56)
    assert cycle(env, 0).status == "completed"
    before = hashes(env)
    key = change(env, what, monkeypatch, tmp_path)
    rep = cycle(env, 1)
    assert rep.status == "failed" and ("panic", "season_frozen") in rep.alerts
    assert key in rep.error and "season 1 frozen" in rep.error
    others = [k for k in before if k != key]
    assert not any(k in rep.error.split("(")[1].split(")")[0] for k in others)  # only one hash named
    assert len(of(env, "cycle_started")) == 1 and len(of(env, "cycle_completed")) == 1  # nothing started
    assert ("panic", "season_frozen") in codes(env)
    assert not pl(env, "season_waiver")
    # Once the hashes are restored, the cycle resumes.
    monkeypatch.setattr(cyc, "prompt_sha256", prompt_sha256)
    monkeypatch.setattr(watch, "prompt_sha256", prompt_sha256)
    env.paths = replace(env.paths, policy=REPO / "config" / "policy.toml")
    set_fee(env, 50)
    assert cycle(env, 1).status == "completed"


def test_waiver_is_written_and_journaled_once_per_hash_change(tmp_path: Path, monkeypatch):
    env = season_env(tmp_path, days=56)
    cycle(env, 0)
    h0 = hashes(env)
    set_fee(env, 51)
    waiver(env, "fee trial at 51 bp")
    assert cycle(env, 1).status == "completed"
    [d1] = pl(env, "season_waiver")
    assert d1 == {"number": 1, "reason": "fee trial at 51 bp", "hashes_before": h0, "hashes_after": hashes(env)}
    assert d1["hashes_after"]["config_sha256"] != h0["config_sha256"] and d1["hashes_after"]["policy_sha256"] == h0["policy_sha256"]
    assert ("action", "season_waiver") in codes(env)
    cycle(env, 2)  # same change, file still there: no new event
    assert len(pl(env, "season_waiver")) == 1
    h1 = hashes(env)
    change(env, "policy", monkeypatch, tmp_path)  # new change: new waiver, from the last state
    assert cycle(env, 3).status == "completed"
    d2 = pl(env, "season_waiver")[1]
    assert (d2["hashes_before"], d2["hashes_after"]) == (h1, hashes(env)) and d2["reason"] == "fee trial at 51 bp"
    # Without a written reason (empty file), the freeze applies again.
    waiver(env, "")
    set_fee(env, 52)
    assert cycle(env, 4).status == "failed"
    assert len(pl(env, "season_waiver")) == 2


def test_changing_the_season_name_is_not_frozen_other_keys_alert_without_effect(tmp_path: Path):
    env = season_env(tmp_path, days=56)
    cycle(env, 0)
    h0 = hashes(env)
    set_season(env, name="Season 1 renamed")
    assert hashes(env) == h0
    assert cycle(env, 1).status == "completed" and not pl(env, "season_waiver")
    assert not [c for c in codes(env) if c[1] == "season_modified"]  # the name alone: no alert
    assert len(of(env, "season_started")) == 1 and pl(env, "season_started")[0]["name"] == "Season 1"
    assert pl(env, "config_loaded")[-1]["config_sha256"] != pl(env, "config_loaded")[0]["config_sha256"]  # full hash: journaled
    set_season(env, duration_days=30)  # modified during the open season: panic alert, no effect, the cycle runs
    assert cycle(env, 2).status == "completed"
    assert [c for c in codes(env) if c[1] == "season_modified"] == [("panic", "season_modified")]
    cycle(env, 3)
    assert len([c for c in codes(env) if c[1] == "season_modified"]) == 1  # a single alert per state
    assert len(of(env, "season_started")) == 1 and pl(env, "season_started")[0]["planned_cycle_end"] == T0 + 56 * DAY
    assert hashes(env) == h0


def test_a_second_season_started_is_refused_while_one_is_open_next_number(tmp_path: Path):
    env = season_env(tmp_path, days=1)
    d = None
    cycle(env, 0, d)
    set_season(env, number=2, start_ts=T0 + 2 * H4 + 300)  # season 2 requested while season 1 is open
    for i in range(1, 6):
        assert cycle(env, i, d).status == "completed"
    assert [p["number"] for p in pl(env, "season_started")] == [1]  # refused
    assert ("panic", "season_modified") in codes(env)
    assert cycle(env, 6, d).status == "completed" and len(of(env, "season_ended")) == 1  # season 1 ends at cycle 6
    # Ended: season 2 starts (last number + 1), but not a number 3.
    set_season(env, number=3, start_ts=T0 + 7 * H4 + 300)
    assert cycle(env, 7, d).status == "completed"
    assert [p["number"] for p in pl(env, "season_started")] == [1]
    assert [c for c in codes(env) if c[1] == "season_number"] == [("action", "season_number")]
    cycle(env, 8, d)
    assert len([c for c in codes(env) if c[1] == "season_number"]) == 1
    set_season(env, number=2, start_ts=T0 + 8 * H4 + 300)
    assert cycle(env, 9, d).status == "completed"
    assert [p["number"] for p in pl(env, "season_started")] == [1, 2] and pl(env, "season_started")[1]["cycle"] == T0 + 9 * H4
    assert len(of(env, "season_reference")) == 2
    # A season that has already ended and whose number stays in the config does not restart.
    set_season(env, number=1, start_ts=T0 + 300)
    cycle(env, 10, d)
    assert [p["number"] for p in pl(env, "season_started")] == [1, 2]


def code_repo(root: Path) -> Path:
    """Fake file tree (no git: the freeze does not depend on git)."""
    root.mkdir(parents=True, exist_ok=True)
    for f, txt in {
        "arena/cycle.py": "a = 1\n", "arena/deciders/prompt/v1.md": "p\n", "arena/risk/riskd.py": "r = 1\n",
        "arena/ops/killswitch.py": "k = 1\n", "config/policy.toml": "p = 1\n",
        "arena/site/x.py": "x = 1\n", "arena/cli.py": "c = 1\n", "arena/ops/other.py": "o = 1\n",
        "arena/perp/league.py": "l = 1\n", "arena/stats.py": "s = 1\n", "uv.lock": "lock = 1\n", "other/z.py": "z = 1\n",
    }.items():  # fmt: skip
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        (root / f).write_text(txt)
    return root


def test_code_sha256_allowlist_on_disk_without_git(tmp_path: Path):
    repo = code_repo(tmp_path / "repo")
    base = season.code_sha256(repo)
    assert season._code_files(repo) == [
        "arena/cycle.py", "arena/deciders/prompt/v1.md", "arena/ops/killswitch.py", "arena/risk/riskd.py",
        "config/policy.toml",
    ]  # fmt: skip

    def changed(path: str, txt: str = "changed\n") -> bool:
        before = (repo / path).read_text()
        (repo / path).write_text(txt)
        try:
            return season.code_sha256(repo) != base
        finally:
            (repo / path).write_text(before)

    for frozen in ("arena/cycle.py", "arena/deciders/prompt/v1.md", "arena/risk/riskd.py", "arena/ops/killswitch.py",
                 "config/policy.toml"):
        assert changed(frozen), frozen
    for free in ("arena/site/x.py", "arena/cli.py", "arena/ops/other.py", "arena/perp/league.py", "arena/stats.py",
                  "uv.lock", "other/z.py"):
        assert not changed(free), free
    # A new module in a frozen directory changes the hash; an editor file or a cache does not.
    (repo / "arena/risk/riskd.py.swp").write_bytes(b"x")
    (repo / "arena/risk/__pycache__").mkdir()
    (repo / "arena/risk/__pycache__/riskd.cpython-312.pyc").write_bytes(b"x")
    assert season.code_sha256(repo) == base
    (repo / "arena/risk/fresh.py").write_text("n = 1\n")
    assert season.code_sha256(repo) != base
    (repo / "arena/risk/fresh.py").unlink()
    assert season.code_sha256(repo) == base == season.code_sha256(repo)


def test_code_frozen_during_the_season_requires_a_waiver(tmp_path: Path):
    repo = code_repo(tmp_path / "repo")
    env = season_env(tmp_path, days=56)
    env.paths = replace(env.paths, repo=repo)
    assert cycle(env, 0).status == "completed"
    assert pl(env, "season_started")[0]["code_sha256"] == season.code_sha256(repo)
    (repo / "arena/cli.py").write_text("c = 2\n")  # outside the perimeter: allowed
    (repo / "arena/site/x.py").write_text("x = 2\n")
    assert cycle(env, 1).status == "completed"
    before = season.code_sha256(repo)
    (repo / "arena/perp/league.py").write_text("l = 2\n")  # derivatives league: outside the freeze
    assert season.code_sha256(repo) == before
    (repo / "arena/cycle.py").write_text("a = 2  # fix\n")  # inside the perimeter: frozen
    rep = cycle(env, 2)
    assert rep.status == "failed" and "code_sha256" in rep.error and ("panic", "season_frozen") in rep.alerts
    waiver(env, "correctif cycle.py")
    assert cycle(env, 2).status == "completed"
    [d] = pl(env, "season_waiver")
    assert d["hashes_before"]["code_sha256"] != d["hashes_after"]["code_sha256"] == season.code_sha256(repo)
    assert d["hashes_before"]["config_sha256"] == d["hashes_after"]["config_sha256"]


def test_claude_cli_version_is_journaled_not_frozen_info_alert(tmp_path: Path, monkeypatch):
    env = season_env(tmp_path, days=56)
    real = season.claude_cli_version
    monkeypatch.setattr(season, "claude_cli_version", lambda: "2.1.0 (Claude Code)")
    cycle(env, 0)
    assert pl(env, "season_started")[0]["claude_cli_version"] == "2.1.0 (Claude Code)"
    assert pl(env, "config_loaded")[-1]["claude_cli_version"] == "2.1.0 (Claude Code)"
    monkeypatch.setattr(season, "claude_cli_version", lambda: "2.2.0 (Claude Code)")
    assert cycle(env, 1).status == "completed"  # not frozen: the cycle runs without a waiver
    assert not pl(env, "season_waiver")
    assert pl(env, "config_loaded")[-1]["claude_cli_version"] == "2.2.0 (Claude Code)" and len(pl(env, "config_loaded")) == 2
    assert [(a["level"], a["message"]) for a in pl(env, "alert") if a["code"] == "claude_cli_version"] == [
        ("info", "claude --version: 2.1.0 (Claude Code) -> 2.2.0 (Claude Code)")
    ]
    cycle(env, 2)
    assert len(pl(env, "config_loaded")) == 2
    # Without a readable CLI: None.
    monkeypatch.setattr(season, "claude_cli_version", real)  # (no undo: it would also remove the conftest guard)
    assert season.claude_cli_version() is None  # conftest: binary not found, never a real CLI


def test_a_wakeup_is_refused_during_a_frozen_season_unless_waived(tmp_path: Path):
    env = season_env(tmp_path, days=56)
    d = prepare(env, X)
    set_fee(env, 51)
    n = len(of(env, "watch"))
    rep = tick(env, X, d)
    assert rep.trigger is not None and rep.refused == "season_frozen" and rep.wakeup is None
    assert not env.of_type("wakeup_started") and len(of(env, "watch")) == n + 1
    assert of(env, "watch")[-1]["payload"]["refused"] == "season_frozen"
    assert [a["code"] for a in pl(env, "alert")].count("season_frozen") == 1
    assert ("panic", "season_frozen") in codes(env)
    # Written waiver: the wake-up goes ahead (the next cycle will journal the waiver).
    env2 = season_env(tmp_path, "e2", days=56)
    d2 = prepare(env2, X)
    set_fee(env2, 51)
    waiver(env2, "trial")
    rep2 = tick(env2, X, d2)
    assert rep2.refused is None and rep2.wakeup == "completed"
    assert cycle(env2, 1, d2).status == "completed" and len(pl(env2, "season_waiver")) == 1


def test_freeze_is_lifted_after_the_season_ends(tmp_path: Path):
    env = season_env(tmp_path, days=1)  # start at cycle 0, end at cycle 6 (t = T0 + 86,400)
    d = deciders()
    for i in range(5):
        cycle(env, i, d)
    set_fee(env, 51)
    assert cycle(env, 5, d).status == "failed"  # t < planned end: frozen
    assert not of(env, "season_ended")
    assert cycle(env, 6, d).status == "completed"  # t >= planned_cycle_end: the freeze no longer applies, season_ended written
    [end] = of(env, "season_ended")
    assert end["payload"]["cycle"] == T0 + 6 * H4
    assert cycle(env, 7, d).status == "completed" and len(of(env, "season_ended")) == 1 and not pl(env, "season_waiver")


# ---------------------------------------------------------------------------------------------- statut


def status(env: Env, now: int, capsys) -> str:
    capsys.readouterr()
    args = ["--var", str(env.paths.var), "--secrets", str(env.paths.secrets), "--config", str(env.paths.config), "--policy", str(env.paths.policy)]
    assert cli.main([*args, "status"], clients=env.clients, now=lambda: now) == 0
    return capsys.readouterr().out


def test_status_pending_ongoing_and_finished(tmp_path: Path, capsys):
    env = make_env(tmp_path, "pending")  # the repository's table: starts on 2026-11-13
    cycle(env, 0)
    out = status(env, T0 + 1000, capsys)
    assert "season: Season 1 pending (starts at the cycle of 2026-11-13 00:05 UTC, 56 days)" in out

    env = season_env(tmp_path, "ongoing", days=56)
    for i in range(4):
        cycle(env, i)
    out = status(env, T0 + 2 * DAY + 5, capsys)
    assert "season: Season 1 in progress (day 3 of 56), start 2025-11-08 00:00 UTC, waivers: 0" in out
    ref = pl(env, "season_reference")[0]["equity"]
    last = {e["payload"]["portfolio"]: e["payload"]["equity_ueur"] for e in of(env, "equity")}
    for p, b in ref.items():
        cur = last[p]
        eur = f"{cur / 1_000_000:,.2f} EUR"
        assert f"  {p:28s} {eur:>16s} {(cur - b) * 100 / b:+7.2f}%" in out
    set_fee(env, 51)
    waiver(env, "trial")
    cycle(env, 4)
    assert "waivers: 1" in status(env, T0 + 2 * DAY + 5, capsys)

    env = season_env(tmp_path, "finished", days=1)
    for i in range(7):
        cycle(env, i)
    out = status(env, T0 + 6 * H4 + 400, capsys)
    assert f"season: Season 1 ended (cycle {datetime.fromtimestamp(T0 + 6 * H4, UTC).strftime('%Y-%m-%d %H:%M UTC')}), start 2025-11-08 00:00 UTC, waivers: 0" in out
    end = pl(env, "season_ended")[0]["equity"]
    p = "llm:claude-haiku-5-5"
    assert f"  {p:28s}" in out and f"{(end[p] - ref[p]) * 100 / ref[p]:+7.2f}%" in out
