"""Rounds per day of the LLM portfolios (docs/SPEC-PERP-FREE-WAKEUPS.md): the only time limit left on the
models' wake-ups.

Each model has `rounds_per_day` rounds per UTC day, scheduled round included. The scheduled rounds still to come today are
reserved: an extra round (a market wake-up, an alert, a wake-up the model asked for) is played only if the
model still has a round left once those are counted. Everything is recomputed from the journal.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

DAY_S = 86_400
ROUND_S = 4 * 3600


def rendezvous_left(now_ts: int, round_offset_s: int) -> int:
    """Scheduled rounds of the current UTC day strictly after `now_ts`."""
    day_end = (now_ts // DAY_S + 1) * DAY_S
    nxt = (now_ts - round_offset_s) // ROUND_S * ROUND_S + round_offset_s + ROUND_S
    return max(0, (day_end - nxt + ROUND_S - 1) // ROUND_S)


def played_today(events: Sequence[Mapping[str, Any]], portfolio: str, now_ts: int) -> int:
    """Rounds the portfolio played today: its `round_data` of the UTC day (one per round)."""
    day = now_ts // DAY_S
    return len(
        {
            e["payload"].get("round")
            for e in events
            if e["type"] == "round_data"
            and e["payload"].get("portfolio") == portfolio
            and e["ts"] // DAY_S == day
        }
    )


def last_played(events: Sequence[Mapping[str, Any]], portfolio: str) -> int | None:
    """Time of the portfolio's last round (its last `round_data`) or skipped round (`perp_llm_skipped`: a round
    whose preparation failed is not retried at every tick), None if it never played."""
    return max(
        (
            e["ts"]
            for e in events
            if e["type"] in ("round_data", "perp_llm_skipped") and e["payload"].get("portfolio") == portfolio
        ),
        default=None,
    )


def quota(
    events: Sequence[Mapping[str, Any]], portfolio: str, now_ts: int, per_day: int, round_offset_s: int
) -> dict[str, int]:
    """{per_day, played_today, rendezvous_left, extra_left}: `extra_left` is how many rounds outside the
    scheduled round the portfolio may still play today."""
    played = played_today(events, portfolio, now_ts)
    scheduled_round = rendezvous_left(now_ts, round_offset_s)
    return {
        "per_day": per_day,
        "played_today": played,
        "rendezvous_left": scheduled_round,
        "extra_left": max(0, per_day - played - scheduled_round),
    }
