"""Operations tests: heartbeat, ntfy, kill switch, dormancy, command line. No network."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx
import pytest

from arena import cli
from arena.cycle import run_cycle
from arena.journal import Journal
from arena.ledger import replay
from arena.ops import dormancy, killswitch
from arena.ops.heartbeat import Heartbeat
from arena.ops.notify import Notifier
from tests.fakes import DAY, H4, HAIKU, T0, Env, action, make_deciders


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.delenv("ARENA_VAR", raising=False)
    monkeypatch.delenv("ARENA_SECRETS", raising=False)
    monkeypatch.setenv("ARENA_USER_KILL", str(tmp_path / "user_KILL"))


def recorder(status: int = 200):
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(status, text="OK")

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


# ---------------------------------------------------------------------------------------------- ntfy


def test_ntfy_priorities_and_token(tmp_path: Path):
    (tmp_path / "ntfy_url").write_text("https://ntfy.example/arena\n")
    (tmp_path / "ntfy_token").write_text("tk_test")
    http, seen = recorder()
    j = Journal(tmp_path / "j.jsonl")
    n = Notifier(j, tmp_path, http)
    for level, prio in (("info", "2"), ("action", "3"), ("panic", "5")):
        n.alert(level, f"code_{level}", f"message {level} ü", 1000)
        assert seen[-1].headers["priority"] == prio
        assert seen[-1].headers["authorization"] == "Bearer tk_test"
        assert seen[-1].content.decode() == f"message {level} ü"
        assert str(seen[-1].url) == "https://ntfy.example/arena"
    assert [e["payload"]["level"] for e in j.events()] == ["info", "action", "panic"]
    with pytest.raises(ValueError):
        n.alert("urgent", "x", "x", 1)


def test_ntfy_without_secret_writes_only_to_the_journal(tmp_path: Path):
    http, seen = recorder()
    j = Journal(tmp_path / "j.jsonl")
    Notifier(j, tmp_path, http).alert("panic", "boom", "msg", 5)
    assert not seen and j.events()[0]["payload"]["code"] == "boom"


def test_ntfy_without_token_has_no_authorization_header(tmp_path: Path):
    (tmp_path / "ntfy_url").write_text("https://ntfy.example/x")
    http, seen = recorder()
    Notifier(None, tmp_path, http).alert("action", "c", "m", 1)
    assert "authorization" not in seen[0].headers


def test_ntfy_network_outage_does_not_raise(tmp_path: Path):
    (tmp_path / "ntfy_url").write_text("https://ntfy.example/x")

    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    j = Journal(tmp_path / "j.jsonl")
    n = Notifier(j, tmp_path, httpx.Client(transport=httpx.MockTransport(boom)))
    assert n.alert("panic", "c", "m", 1) is not None  # the alert stays in the journal
    assert n.send("info", "c", "m") is False


# ---------------------------------------------------------------------------------------------- heartbeat


def test_heartbeat_success_and_fail(tmp_path: Path):
    (tmp_path / "healthcheck_url").write_text("https://hc.example/ping/uuid/\n")
    http, seen = recorder()
    hb = Heartbeat(tmp_path, Notifier(None, tmp_path, http))
    assert hb.ping(True, 1) is True
    assert hb.ping(False, 2) is True
    assert [str(r.url) for r in seen] == ["https://hc.example/ping/uuid", "https://hc.example/ping/uuid/fail"]


def test_heartbeat_absent_is_noop_journaled_once(tmp_path: Path):
    http, seen = recorder()
    j = Journal(tmp_path / "j.jsonl")
    hb = Heartbeat(tmp_path, Notifier(j, tmp_path, http))
    assert hb.ping(True, 1) is False and hb.ping(False, 2) is False
    assert not seen
    assert [e["payload"]["code"] for e in j.events()] == ["heartbeat_absent"]


def test_heartbeat_http_error_does_not_raise(tmp_path: Path):
    (tmp_path / "healthcheck_url").write_text("https://hc.example/u")
    http, _ = recorder(500)
    assert Heartbeat(tmp_path, Notifier(None, tmp_path, http)).ping(True, 1) is False


def test_cycle_pings_heartbeat_at_end_of_cycle(tmp_path: Path):
    env = Env(tmp_path, {"healthcheck_url": "https://hc.example/u", "ntfy_url": "https://ntfy.example/n"})
    env.clock.now = env.now_of(0)
    assert run_cycle(env.paths, env.clients, env.clock.now, deciders=make_deciders()).status == "completed"
    pings = [str(r.url) for r in env.requests if "hc.example" in str(r.url)]
    assert pings == ["https://hc.example/u"]
    # re-running the same cycle (already done) sends nothing more
    run_cycle(env.paths, env.clients, env.clock.now, deciders=make_deciders())
    assert len([r for r in env.requests if "hc.example" in str(r.url)]) == 1


# ---------------------------------------------------------------------------------------------- kill switch, dormancy


def test_killswitch_files(tmp_path: Path):
    env = Env(tmp_path)
    assert not killswitch.is_active(env.paths)
    killswitch.activate(env.paths)
    assert killswitch.active_sources(env.paths) == [str(env.paths.kill)]
    env.paths.user_kill.touch()
    assert len(killswitch.active_sources(env.paths)) == 2
    assert set(killswitch.deactivate(env.paths)) == {env.paths.kill, env.paths.user_kill}
    assert not killswitch.is_active(env.paths) and killswitch.deactivate(env.paths) == []


def test_dormancy_levels_and_reference(tmp_path: Path):
    env = Env(tmp_path)
    assert dormancy.level(7 * DAY - 1) == dormancy.OK
    assert dormancy.level(7 * DAY) == dormancy.NO_ENTRIES
    assert dormancy.level(9 * DAY - 1) == dormancy.NO_ENTRIES
    assert dormancy.level(9 * DAY) == dormancy.FLATTEN
    assert dormancy.age_s(env.paths, 10 * DAY, since_ts=3 * DAY) == 7 * DAY  # without an ack: since startup
    dormancy.write_ack(env.paths, 8 * DAY)
    assert dormancy.age_s(env.paths, 10 * DAY, since_ts=0) == 2 * DAY
    assert dormancy.age_s(env.paths, 5 * DAY, since_ts=0) == 0  # clock running behind: never negative


# ---------------------------------------------------------------------------------------------- CLI


def run_cli(env: Env, *args: str, now: int | None = None) -> int:
    ts = now if now is not None else env.clock.now
    return cli.main(["--var", str(env.paths.var), "--secrets", str(env.sec), "--config", str(env.paths.config), *args], clients=env.clients, now=lambda: ts)


def hold(idx: int, snap: dict):
    return [action("BTC/EUR"), action("ETH/EUR")] if idx == 0 else None


def test_cli_kill_now_takes_effect_within_a_minute(tmp_path: Path):
    env = Env(tmp_path)
    env.clock.now = env.now_of(0)
    run_cycle(env.paths, env.clients, env.clock.now, deciders=make_deciders(hold))
    assert replay(Journal(env.paths.journal).events())[HAIKU].positions
    env.clock.now = env.now_of(0) + 1800  # half an hour later, outside a cycle
    t0 = time.monotonic()
    assert run_cli(env, "kill", "--now") == 0
    assert time.monotonic() - t0 < 60
    st = replay(Journal(env.paths.journal).events())
    assert not st[HAIKU].positions and not st["benchmark:random"].positions and st["benchmark:basket"].positions
    fills = [e["payload"] for e in Journal(env.paths.journal).events() if e["type"] == "fill" and e["payload"]["reason"] == "kill_switch"]
    assert {f["portfolio"] for f in fills} >= {HAIKU}
    assert killswitch.is_active(env.paths)
    # the next cycle buys nothing again
    n = len(fills)
    env.clock.now = env.now_of(1)
    run_cycle(env.paths, env.clients, env.clock.now, deciders=make_deciders(hold))
    assert not replay(Journal(env.paths.journal).events())[HAIKU].positions
    assert len([e for e in Journal(env.paths.journal).events() if e["type"] == "fill" and e["payload"]["reason"] == "kill_switch"]) == n


def test_cli_kill_unkill_ack_resume_status_verify(tmp_path: Path, capsys: pytest.CaptureFixture):
    env = Env(tmp_path)
    env.clock.now = env.now_of(0)
    run_cycle(env.paths, env.clients, env.clock.now, deciders=make_deciders(hold))

    assert run_cli(env, "kill") == 0 and killswitch.is_active(env.paths)
    assert run_cli(env, "unkill") == 0 and not killswitch.is_active(env.paths)
    events = Journal(env.paths.journal).events()
    assert [e["payload"]["active"] for e in events if e["type"] == "kill_switch"] == [True, False]

    assert run_cli(env, "ack") == 0 and dormancy.ack_ts(env.paths) == env.clock.now

    assert run_cli(env, "resume", "unknown") == 2
    assert run_cli(env, "resume", HAIKU) == 0
    assert Journal(env.paths.journal).events()[-1]["type"] == "portfolio_resumed"

    capsys.readouterr()
    assert run_cli(env, "status") == 0
    out = capsys.readouterr().out
    assert "journal: OK" in out and HAIKU in out and "kill switch: inactive" in out and "last completed cycle" in out
    assert "last alert" in out

    assert run_cli(env, "verify") == 0
    assert run_cli(env, "rebuild-ledger") == 0 and env.paths.sqlite.exists()


def test_cli_verify_and_status_report_a_broken_journal(tmp_path: Path, capsys: pytest.CaptureFixture):
    env = Env(tmp_path)
    env.clock.now = env.now_of(0)
    run_cycle(env.paths, env.clients, env.clock.now, deciders=make_deciders())
    with open(env.paths.journal, "ab") as f:
        f.write(b'{"seq": 99')  # truncated line
    assert run_cli(env, "verify") == 1
    assert run_cli(env, "status") == 1
    assert run_cli(env, "rebuild-ledger") == 1
    assert run_cli(env, "resume", HAIKU) == 1
    assert "BROKEN" in capsys.readouterr().out


def test_cli_cycle_failure_gives_nonzero_code_and_ping_fail(tmp_path: Path):
    env = Env(tmp_path, {"healthcheck_url": "https://hc.example/u"})
    env.clock.now = env.now_of(0)
    env.kraken.fail_ticker = True
    assert run_cli(env, "cycle", "--no-site") == 1
    assert [str(r.url) for r in env.requests] == ["https://hc.example/u/fail"]
    env.kraken.fail_ticker = False
    env.requests.clear()
    assert run_cli(env, "cycle", "--no-site") == 0  # the slot is still open: the cycle goes through
    assert [str(r.url) for r in env.requests] == ["https://hc.example/u"]


def test_cli_build_site_handles_a_missing_module_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture):
    env = Env(tmp_path)
    monkeypatch.setitem(sys.modules, "arena.site", None)  # simulates a nonexistent module (ImportError)
    assert run_cli(env, "build-site") == 2
    assert "build-site is unavailable" in capsys.readouterr().err


def test_cli_build_site_calls_arena_site_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = Env(tmp_path)
    calls = []
    fake = type(sys)("arena.site")
    fake.build = lambda journal, out, *, config, policy: calls.append((journal, out, config.capital_ueur, policy.max_order_bp))
    monkeypatch.setitem(sys.modules, "arena.site", fake)
    assert run_cli(env, "build-site") == 0
    assert calls == [(env.paths.journal, env.paths.site, 1_000_000_000, 2000)]


def test_cli_smoke_llm_refuses_without_a_key(tmp_path: Path, capsys: pytest.CaptureFixture):
    env = Env(tmp_path)
    assert run_cli(env, "smoke-llm", HAIKU) == 2
    assert "no API key" in capsys.readouterr().err
    assert not env.paths.journal.exists()  # nothing is written


def test_cli_smoke_llm_one_call_without_an_order(tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch):
    import json

    from tests.fakes import fake_anthropic_client

    env = Env(tmp_path, {"anthropic_api_key": "dummy-key"})
    env.clock.now = env.now_of(0)
    text = json.dumps({"actions": [action("BTC/EUR")], "justification": "ok"})
    monkeypatch.setattr("arena.deciders.llm.LLMDecider._default_factory", staticmethod(fake_anthropic_client(text, "claude-haiku-5-5")))
    assert run_cli(env, "smoke-llm", HAIKU) == 0
    out = capsys.readouterr().out
    assert "valid, 1 action" in out and "no order executed" in out
    assert not env.paths.journal.exists()


def test_systemd_units_and_install_script():
    root = Path(__file__).resolve().parent.parent
    timer = (root / "ops/systemd/arena-cycle.timer").read_text()
    assert "OnCalendar=*-*-* 00,04,08,12,16,20:05:00 UTC" in timer and "Persistent=true" in timer
    site = (root / "ops/systemd/arena-site.service").read_text()
    assert "127.0.0.1" in site and "8787" in site and "var/site" in site
    script = (root / "scripts/install-user-units.sh").read_text()
    assert "daemon-reload" in script and "enable --now" in script
    assert "systemctl --user enable" not in script.split("cat <<MSG")[0]  # it does not enable anything itself


def test_cycle_timer_schedule_is_at_hh05_utc():
    """The cycle decided at HH:05 belongs to the HH:00 slot (start of the last closed bar + 4 h)."""
    for h in (0, 4, 8, 12, 16, 20):
        now = T0 + h * 3600 + 300
        assert now // H4 * H4 == T0 + h * 3600
