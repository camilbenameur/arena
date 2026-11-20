"""Runtime paths of the arena (var/, secrets, sentinel files). Everything is overridable for tests.

Recognised environment variables: ARENA_VAR (state directory, default `var/` of the repository), ARENA_SECRETS
(default `~/.config/arena/secrets`), ARENA_USER_KILL (default `~/.config/arena/KILL`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _home_cfg() -> Path:
    return Path.home() / ".config" / "arena"


@dataclass(frozen=True)
class Paths:
    var: Path
    config: Path = REPO / "config" / "arena.toml"
    policy: Path = REPO / "config" / "policy.toml"
    secrets: Path = field(default_factory=lambda: _home_cfg() / "secrets")
    user_kill: Path = field(default_factory=lambda: _home_cfg() / "KILL")
    repo: Path = REPO

    @classmethod
    def from_env(
        cls,
        var: str | Path | None = None,
        secrets: str | Path | None = None,
        config: str | Path | None = None,
        policy: str | Path | None = None,
    ) -> Paths:
        env = os.environ
        kw: dict[str, Path] = {"var": Path(var or env.get("ARENA_VAR") or REPO / "var")}
        if secrets or env.get("ARENA_SECRETS"):
            kw["secrets"] = Path(secrets or env["ARENA_SECRETS"])
        if env.get("ARENA_USER_KILL"):
            kw["user_kill"] = Path(env["ARENA_USER_KILL"])
        if config:
            kw["config"] = Path(config)
        if policy:
            kw["policy"] = Path(policy)
        return cls(**kw)

    @property
    def journal(self) -> Path:
        return self.var / "journal" / "events.jsonl"

    @property
    def data(self) -> Path:
        return self.var / "data"

    @property
    def kill(self) -> Path:
        return self.var / "KILL"

    @property
    def ack(self) -> Path:
        return self.var / "ack"

    @property
    def site(self) -> Path:
        return self.var / "site"

    @property
    def sqlite(self) -> Path:
        return self.var / "ledger.sqlite"

    @property
    def lock(self) -> Path:
        return self.var / "cycle.lock"
