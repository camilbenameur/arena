"""The news of the perp league: Kraken's official announcements and the US macro calendar
(docs/SPEC-PERP-NEWS.md). No free text from the web ever reaches a model.

Two sources, both official and structured:
- **Kraken's announcements**, read by the collector every 5 minutes (`collect_news`):
  - the status page (Statuspage API of status.kraken.com): open incidents, upcoming and active maintenances of
    the "Kraken Derivatives" components, and the delisting notices that cite one of the league's contracts. Only
    the title (cleaned, 120 characters), status, impact, times and link are kept; never the body;
  - the state of each contract (Kraken Futures `instruments/status`): price dislocation, extreme volatility and
    its initial margin multiplier. The titles of these items are written here, in French.
- **The macro calendar** (`config/macro-calendar.toml`): dates published in advance (FOMC, CPI, jobs, PCE...),
  so no feed is needed.

The collector archives the raw payloads by sha256 (`<data>/news/raw/`) and the normalized items (`<data>/news/items/`); the
watcher journals each new item as `news_item` (the journal is the reference: a round reads only journaled items,
at or before its time), and the round dossier freezes the `news` block. A new item, or a macro release a few
minutes old, calls the models back (trigger `news` or `calendar`, docs/SPEC-PERP-NEWS.md §4).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arena.paths import REPO

DEFAULT_CONFIG = REPO / "config" / "perp-news.toml"
SOURCE_STATUS = "kraken_status"
SOURCE_INSTRUMENTS = "kraken_instruments"
CALENDAR_KINDS = ("fomc", "fomc_minutes", "cpi", "nfp", "ppi", "pce", "gdp")
TITLE_MAX = 120
RECENT_KEYS = 500  # the collector remembers this many item keys, so an unchanged item is written once
# the league's contracts and the asset names a delisting notice may use for them
TICKERS = {
    "PF_XBTUSD": ("BTC", "XBT", "Bitcoin"),
    "PF_ETHUSD": ("ETH", "Ethereum"),
    "PF_SOLUSD": ("SOL", "Solana"),
    "PF_XRPUSD": ("XRP",),
    "PF_LINKUSD": ("LINK", "Chainlink"),
    "PF_LTCUSD": ("LTC", "Litecoin"),
}
# the statuses after which an announcement is over (it then leaves the snapshot once older than the window)
CLOSED = {"resolved", "postmortem", "completed", "normal", "unlisted"}
NOT_TRADING = {"Cross-Exchange Transfers", "Single Sign-On"}


class NewsConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    kind: str
    label: str
    ts: int
    source: str


@dataclass(frozen=True)
class NewsConfig:
    enabled: bool
    calendar: tuple[CalendarEvent, ...]
    calendar_sha256: str
    wake_kinds: tuple[str, ...]
    wake_after_s: int
    ahead_s: int
    past_s: int
    status_api: str
    derivatives_group_id: str
    instruments_url: str
    window_s: int
    max_items: int
    sha256: str

    def wake_events(self) -> list[CalendarEvent]:
        return [e for e in self.calendar if e.kind in self.wake_kinds]


def _iso(text: str) -> int:
    return int(datetime.fromisoformat(text).timestamp())


def _int(cfg: Mapping[str, Any], key: str, lo: int, hi: int) -> int:
    v = cfg.get(key)
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise NewsConfigError(f"{key}: an integer in [{lo}, {hi}] is required")
    return v


def load_calendar(path: Path) -> tuple[tuple[CalendarEvent, ...], str]:
    raw = path.read_bytes()
    try:
        doc = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise NewsConfigError(f"{path.name}: {exc}") from exc
    out: list[CalendarEvent] = []
    seen: set[str] = set()
    for n, e in enumerate(doc.get("event", [])):
        try:
            ev = CalendarEvent(
                id=str(e["id"]), kind=str(e["kind"]), label=str(e["label"]), ts=_iso(str(e["ts_utc"])),
                source=str(e["source"]),
            )  # fmt: skip
        except (KeyError, ValueError, TypeError) as exc:
            raise NewsConfigError(f"{path.name}: event {n}: {exc}") from exc
        if ev.kind not in CALENDAR_KINDS:
            raise NewsConfigError(f"{path.name}: event {ev.id}: unknown kind {ev.kind!r}")
        if ev.id in seen:
            raise NewsConfigError(f"{path.name}: event {ev.id} twice")
        if not ev.label or len(ev.label) > TITLE_MAX or not ev.source.startswith("https://"):
            raise NewsConfigError(
                f"{path.name}: event {ev.id}: label of 1 to {TITLE_MAX} characters, https source"
            )
        seen.add(ev.id)
        out.append(ev)
    return tuple(sorted(out, key=lambda e: (e.ts, e.id))), hashlib.sha256(raw).hexdigest()


def load_news_config(path: Path = DEFAULT_CONFIG) -> NewsConfig:
    raw = path.read_bytes()
    try:
        cfg = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise NewsConfigError(f"{path.name}: {exc}") from exc
    enabled = cfg.get("enabled")
    if not isinstance(enabled, bool):
        raise NewsConfigError("enabled: true or false")
    cal_name = cfg.get("calendar")
    if not isinstance(cal_name, str) or "/" in cal_name:
        raise NewsConfigError("calendar: a file name next to the configuration")
    calendar, cal_sha = load_calendar(path.parent / cal_name)
    kinds = cfg.get("calendar_wake_kinds")
    if not isinstance(kinds, list) or any(k not in CALENDAR_KINDS for k in kinds):
        raise NewsConfigError(f"calendar_wake_kinds: a list among {CALENDAR_KINDS}")
    urls = {}
    for key in ("status_api", "instruments_status_url"):
        v = cfg.get(key)
        if not isinstance(v, str) or not v.startswith("https://"):
            raise NewsConfigError(f"{key}: an https URL")
        urls[key] = v
    group = cfg.get("derivatives_group_id")
    if not isinstance(group, str) or not re.fullmatch(r"[a-z0-9]{6,20}", group):
        raise NewsConfigError("derivatives_group_id: the Statuspage id of the 'Kraken Derivatives' group")
    return NewsConfig(
        enabled=enabled,
        calendar=calendar,
        calendar_sha256=cal_sha,
        wake_kinds=tuple(kinds),
        wake_after_s=_int(cfg, "calendar_wake_after_min", 1, 30) * 60,
        ahead_s=_int(cfg, "calendar_ahead_h", 1, 336) * 3600,
        past_s=_int(cfg, "calendar_past_h", 1, 48) * 3600,
        status_api=urls["status_api"].rstrip("/") + "/",
        derivatives_group_id=group,
        instruments_url=urls["instruments_status_url"],
        window_s=_int(cfg, "announcements_window_h", 1, 168) * 3600,
        max_items=_int(cfg, "max_items", 1, 20),
        sha256=hashlib.sha256(raw + cal_sha.encode()).hexdigest(),
    )


# ---------------------------------------------------------------------------------------------- normalizing

_UNSAFE = re.compile(r"[\x00-\x1f\x7f<>`{}\[\]\\|*_#~$]")


def clean_title(text: Any) -> str:
    """An official title, made inert: no control or markup character, single spaces, 120 characters at most."""
    s = _UNSAFE.sub(" ", str(text))
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= TITLE_MAX else s[: TITLE_MAX - 1].rstrip() + "…"


def _ts(text: Any) -> int | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        return _iso(text)
    except ValueError:
        return None


def cited_instruments(text: str, instruments: Sequence[str]) -> list[str]:
    """The league's contracts a text cites by a whole-word asset name (a delisting notice)."""
    out = []
    for inst in instruments:
        names = TICKERS.get(inst, ())
        if any(re.search(rf"(?<![A-Za-z0-9]){re.escape(n)}(?![A-Za-z0-9])", text) for n in names):
            out.append(inst)
    return out


def _derivatives(record: Mapping[str, Any], group_id: str) -> bool:
    comps = record.get("components") or []
    # trading components only: transfers between accounts and sign-in do not touch a paper portfolio
    if any(
        isinstance(c, Mapping) and c.get("group_id") == group_id and c.get("name") not in NOT_TRADING
        for c in comps
    ):
        return True
    name = str(record.get("name", ""))
    return (
        not comps
        and bool(re.search(r"derivatives|futures", name, re.IGNORECASE))
        and not re.search(r"\bUS\b", name)
    )


def status_item(
    record: Mapping[str, Any], kind: str, group_id: str, instruments: Sequence[str]
) -> dict[str, Any] | None:
    """A Statuspage incident or maintenance -> a normalized item, or None when it does not concern the league:
    a component of the derivatives group, or a delisting notice citing one of the league's contracts."""
    name = str(record.get("name", ""))
    cited: list[str] = []
    if re.search(r"delist", name, re.IGNORECASE):
        bodies = " ".join(
            str(u.get("body", "")) for u in record.get("incident_updates") or [] if isinstance(u, Mapping)
        )
        cited = cited_instruments(name + " " + bodies, instruments)
        if not cited:
            return None
        kind = "delisting"
    elif not _derivatives(record, group_id):
        return None
    rid = str(record.get("id", ""))
    if not re.fullmatch(r"[a-z0-9]{6,20}", rid):
        return None
    status = str(record.get("status", ""))
    return {
        "source": SOURCE_STATUS,
        "id": rid,
        "kind": kind,
        "title": clean_title(name),
        "status": status if re.fullmatch(r"[a-z_]{1,20}", status) else "unknown",
        "impact": str(record.get("impact") or "none")[:20],
        "published_ts": _ts(record.get("created_at")),
        "updated_ts": _ts(record.get("updated_at")),
        "starts_ts": _ts(record.get("scheduled_for")) or _ts(record.get("started_at")),
        "ends_ts": _ts(record.get("scheduled_until")) or _ts(record.get("resolved_at")),
        "instruments": cited,
        "url": str(record.get("shortlink") or "")[:80]
        if str(record.get("shortlink", "")).startswith("https://")
        else "",
        "wake": status not in CLOSED or kind == "incident",
    }


def contract_state(row: Mapping[str, Any]) -> str:
    """'normal', or the abnormal flags of a contract, e.g. 'dislocation:up;volatility:x2'."""
    parts = []
    if row.get("experiencingDislocation") is True:
        d = row.get("priceDislocationDirection")
        parts.append(
            f"dislocation:{'up' if d == 'ABOVE_UPPER_BOUND' else 'down' if d == 'BELOW_LOWER_BOUND' else str(d or '?').lower()[:12]}"
        )
    if row.get("experiencingExtremeVolatility") is True:
        m = row.get("extremeVolatilityInitialMarginMultiplier")
        parts.append(f"volatility:x{m if isinstance(m, int) and not isinstance(m, bool) else '?'}")
    return ";".join(parts) or "normal"


def contract_title(inst: str, state: str) -> str:
    if state == "normal":
        return f"{inst}: back to normal according to Kraken (no more price dislocation or extreme volatility)"
    bits = []
    for part in state.split(";"):
        key, _, val = part.partition(":")
        if key == "dislocation":
            side = {"up": "upward", "down": "downward"}.get(val, "")
            bits.append(f"abnormal price dislocation {side}".strip())
        elif key == "volatility":
            bits.append(f"extreme volatility, initial margin {val}")
    return clean_title(f"{inst}: " + ", ".join(bits) + " (according to Kraken)")


def contract_items(
    payload: Mapping[str, Any], instruments: Sequence[str], previous: Mapping[str, str]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Kraken's state of each contract -> an item per contract whose state changed (a first sighting counts
    only when abnormal), and the new states."""
    rows = payload.get("instrumentStatus")
    if payload.get("result") != "success" or not isinstance(rows, list):
        raise ValueError("instruments/status: unsuccessful response")
    states = dict(previous)
    items = []
    by = {r.get("tradeable"): r for r in rows if isinstance(r, Mapping)}
    for inst in instruments:
        if inst not in by:
            continue
        st = contract_state(by[inst])
        if st == previous.get(inst, "normal"):
            states[inst] = st
            continue
        states[inst] = st
        items.append(
            {
                "source": SOURCE_INSTRUMENTS,
                "id": inst,
                "kind": "contract_state",
                "title": contract_title(inst, st),
                "status": "normal" if st == "normal" else "abnormal",
                "state": st,
                "impact": "none" if st == "normal" else "major",
                "published_ts": None,
                "updated_ts": None,
                "starts_ts": None,
                "ends_ts": None,
                "instruments": [inst],
                "url": "",
                "wake": st != "normal",
            }
        )
    return items, states


def item_key(item: Mapping[str, Any]) -> str:
    """An item is written (and journaled) once per status: a new status is a new version."""
    return f"{item['source']}:{item['id']}:{item['status']}:{item.get('state', '')}"


# ---------------------------------------------------------------------------------------------- collector


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode(
        "utf-8"
    )


def _day(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")


def _month(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m")


def collect_news(
    cfg: NewsConfig,
    get_json: Callable[[str], Any],
    root: Path,
    state: dict[str, Any],
    now_ts: int,
    instruments: Sequence[str],
) -> dict[str, int]:
    """One collection: fetches, archives each raw payload under its sha256 (`root/raw/<2>/<sha>.json`), and appends the NEW items (a key not
    written recently) to `root/items/<YYYY-MM>.jsonl`. `state` (the collector's) keeps the open announcements, the
    contracts' states and the recent keys. An announcement that leaves the open lists is looked up in the full
    lists, for its final status. Raises on a source error (the collector records it; nothing is written)."""
    shas: dict[str, str] = {}

    def fetch(name: str, url: str) -> Any:
        payload = get_json(url)
        data = _canonical(payload)
        sha = hashlib.sha256(data).hexdigest()
        # content-addressed: an unchanged payload (most runs) is stored once
        p = root / "raw" / sha[:2] / f"{sha}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_bytes(data)
        shas[name] = sha
        return payload

    api = cfg.status_api
    lists = {
        "incident": fetch("incidents-unresolved", api + "incidents/unresolved.json").get("incidents") or [],
        "maintenance": (
            fetch("maintenances-upcoming", api + "scheduled-maintenances/upcoming.json").get(
                "scheduled_maintenances"
            )
            or []
        )
        + (
            fetch("maintenances-active", api + "scheduled-maintenances/active.json").get(
                "scheduled_maintenances"
            )
            or []
        ),
    }
    contracts = fetch("instruments-status", cfg.instruments_url)
    items: list[dict[str, Any]] = []
    now_open: dict[str, str] = {}
    for kind, records in lists.items():
        for r in records:
            if not isinstance(r, Mapping):
                continue
            it = status_item(r, kind, cfg.derivatives_group_id, instruments)
            if it is not None:
                it["raw_sha256"] = shas[
                    "incidents-unresolved" if kind == "incident" else "maintenances-upcoming"
                ]
                items.append(it)
                now_open[it["id"]] = kind
    previous_open: dict[str, str] = dict(state.get("news_open") or {})
    gone = {i: k for i, k in previous_open.items() if i not in now_open}
    if gone:  # their final status, from the full lists (rare: one fetch per list concerned)
        full = {}
        if "incident" in gone.values():
            full["incident"] = fetch("incidents", api + "incidents.json").get("incidents") or []
        if "maintenance" in gone.values():
            full["maintenance"] = (
                fetch("maintenances", api + "scheduled-maintenances.json").get("scheduled_maintenances") or []
            )
        for gid, kind in gone.items():
            lst = full.get("incident" if kind == "incident" else "maintenance", [])
            rec = next((r for r in lst if isinstance(r, Mapping) and r.get("id") == gid), None)
            it = (
                status_item(
                    rec,
                    "incident" if kind == "incident" else "maintenance",
                    cfg.derivatives_group_id,
                    instruments,
                )
                if rec
                else None
            )
            if it is None:
                it = {
                    "source": SOURCE_STATUS, "id": gid, "kind": kind, "title": "", "status": "unlisted",
                    "impact": "none", "published_ts": None, "updated_ts": None, "starts_ts": None,
                    "ends_ts": None, "instruments": [], "url": "", "wake": False,
                }  # fmt: skip
            it["raw_sha256"] = shas.get("incidents" if kind == "incident" else "maintenances", "")
            items.append(it)
    c_items, c_states = contract_items(contracts, instruments, state.get("news_contracts") or {})
    for it in c_items:
        it["raw_sha256"] = shas["instruments-status"]
    items += c_items
    recent: list[str] = list(state.get("news_keys") or [])
    seen = set(recent)
    new = []
    for it in items:
        k = item_key(it)
        if k in seen:
            continue
        seen.add(k)
        recent.append(k)
        new.append({**it, "key": k, "fetched_ts": now_ts})
    if new:
        p = root / "items" / f"{_month(now_ts)}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            for it in new:
                f.write(json.dumps(it, sort_keys=True, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    state["news_open"] = now_open  # {id: the list it was read from}
    state["news_contracts"] = c_states
    state["news_keys"] = recent[-RECENT_KEYS:]
    return {"news_items": len(new), "news_open": len(now_open)}


def read_items(root: Path, since_ts: int, until_ts: int) -> list[dict[str, Any]]:
    """The collected items fetched in [since_ts, until_ts], oldest first (a torn last line is skipped)."""
    out = []
    months = sorted({_month(since_ts), _month(until_ts)})
    for m in months:
        p = root / "items" / f"{m}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                it = json.loads(line)
            except ValueError:
                continue
            if (
                isinstance(it, dict)
                and isinstance(it.get("fetched_ts"), int)
                and since_ts <= it["fetched_ts"] <= until_ts
            ):
                out.append(it)
    return out


# ---------------------------------------------------------------------------------------------- journal & round


def journaled_keys(events: Sequence[Mapping[str, Any]]) -> set[str]:
    return {e["payload"].get("key") for e in events if e["type"] == "news_item"}


def announcements(events: Sequence[Mapping[str, Any]], cfg: NewsConfig, now_ts: int) -> list[dict[str, Any]]:
    """The latest version of each journaled announcement at `now_ts`: the open ones, and those of the window;
    newest first, `cfg.max_items` at most."""
    last: dict[tuple[str, str], tuple[int, Mapping[str, Any]]] = {}
    for e in events:
        if e["type"] == "news_item" and e["ts"] <= now_ts:
            p = e["payload"]
            last[(p["source"], p["id"])] = (e["ts"], p)
    keep = [(ts, p) for ts, p in last.values() if p["status"] not in CLOSED or now_ts - ts <= cfg.window_s]
    keep.sort(key=lambda x: -x[0])
    out = []
    for ts, p in keep[: cfg.max_items]:
        out.append(
            {
                "seen_ts": ts,
                "kind": p["kind"],
                "title": p.get("title", ""),
                "status": p["status"],
                "impact": p.get("impact", "none"),
                "starts_ts": p.get("starts_ts"),
                "ends_ts": p.get("ends_ts"),
                "instruments": list(p.get("instruments") or []),
                "key": p["key"],
            }
        )
    return out


def calendar_window(cfg: NewsConfig, now_ts: int) -> list[dict[str, Any]]:
    return [
        {"id": e.id, "kind": e.kind, "label": e.label, "ts": e.ts, "wakes": e.kind in cfg.wake_kinds}
        for e in cfg.calendar
        if now_ts - cfg.past_s <= e.ts <= now_ts + cfg.ahead_s
    ]


def news_block(events: Sequence[Mapping[str, Any]], cfg: NewsConfig, now_ts: int) -> dict[str, Any]:
    """The `news` block of a round dossier (integers and strings only): journaled items and the calendar."""
    last_cal = cfg.calendar[-1].ts if cfg.calendar else None
    return {
        "config_sha256": cfg.sha256,
        "calendar": calendar_window(cfg, now_ts),
        "calendar_ends_ts": last_cal,
        "announcements": announcements(events, cfg, now_ts),
    }


def unseen_news(
    events: Sequence[Mapping[str, Any]], since_ts: int | None, now_ts: int, max_age_s: int
) -> list[Mapping[str, Any]]:
    """The journaled items that call the models back (`wake`), journaled after `since_ts` (the portfolio's last
    round) and at most `max_age_s` old; oldest first."""
    return [
        {**e["payload"], "journaled_ts": e["ts"]}
        for e in events
        if e["type"] == "news_item"
        and e["payload"].get("wake")
        and (since_ts is None or e["ts"] > since_ts)
        and 0 <= now_ts - e["ts"] <= max_age_s
    ]


def due_releases(
    cfg: NewsConfig, since_ts: int | None, now_ts: int, early_s: int, lapse_s: int
) -> list[CalendarEvent]:
    """The waking releases whose call-back time (`ts + wake_after_s`) is due at `now_ts` (from `early_s` before
    to `lapse_s` after), for a portfolio whose last round started before that time (a round just after the
    release saw too little of the reaction)."""
    out = []
    for e in cfg.wake_events():
        due = e.ts + cfg.wake_after_s
        if due - early_s <= now_ts < due + lapse_s and (since_ts is None or since_ts < due - early_s):
            out.append(e)
    return out
