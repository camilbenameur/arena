"""Market data collector of the perpetual futures league (step 1). No LLM, no portfolio, no order.

One run (every 5 minutes, from a systemd user timer, or by hand):
1. tickers of every instrument and the EUR/USD quote -> one snapshot;
2. for each instrument: closed one-minute candles (mark, trade, spot index) since the last stored one;
3. hourly funding history when a new hourly stamp is due (at most one call per `funding_retry_s`);
4. hourly open interest when a new closed hour is due;
5. top of the order book.

Each instrument is collected independently: an error on one is recorded and never stops the others. After
an outage, a run catches up at most `backfill_s` back and records any older hole as an error. With
`--backfill-days N` the run ALSO fetches backwards, before the first stored record, down to N days.

Every run appends a summary to `runs/<YYYY-MM>.jsonl`, including skipped runs (lock busy) and crashes.
Runs are serialised by a non-blocking lock.

    python -m arena.perp.collect run [--var DIR] [--config PATH] [--backfill-days N]
    python -m arena.perp.collect report [--var DIR] [--config PATH] [--days N]

Exit codes: 0 success or lock busy; 3 the run finished with data errors (see runs/); 2 configuration or
usage error; 1 crash (unexpected exception, traceback on stderr, crash line in runs/).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from arena.data import DataError
from arena.paths import REPO
from arena.perp.config import DEFAULT_CONFIG, PerpConfig, PerpConfigError, default_var, load_perp_config
from arena.perp.kraken_futures import CLOSE_GRACE_S, KrakenFuturesClient
from arena.perp.news import DEFAULT_CONFIG as NEWS_CONFIG
from arena.perp.news import NewsConfig, NewsConfigError, collect_news, load_news_config
from arena.perp.store import PerpDataStore, TickerSnapshot, missing_steps

HOUR_S = 3600
RUN_SLOT_S = 300  # the timer period
FUNDING_STALE_S = 4 * HOUR_S
EXIT_OK, EXIT_CRASH, EXIT_USAGE, EXIT_DATA_ERRORS = 0, 1, 2, 3
# Errors a malformed payload or a full disk can raise: recorded per instrument, never fatal to the run.
RECORDED_ERRORS = (DataError, KeyError, IndexError, ValueError, TypeError, ArithmeticError, OSError)


@dataclass
class RunReport:
    ts: int
    config_sha256: str
    counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "ok": self.ok,
            "config_sha256": self.config_sha256,
            "counts": dict(sorted(self.counts.items())),
            "errors": self.errors,
            "duration_ms": self.duration_ms,
        }


def data_root(var: Path) -> Path:
    return var / "data" / "kraken_futures"


@contextmanager
def run_lock(var: Path) -> Iterator[bool]:
    """Yields True if the lock was acquired, False if another run holds it (never waits)."""
    var.mkdir(parents=True, exist_ok=True)
    fd = os.open(var / "collect.lock", os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _state_path(var: Path) -> Path:
    return var / "collect_state.json"


def _load_state(var: Path) -> dict[str, Any]:
    p = _state_path(var)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}  # the state only throttles funding retries: losing it is harmless
    return data if isinstance(data, dict) else {}


def _save_state(var: Path, state: dict[str, Any]) -> None:
    p = _state_path(var)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)


def append_run_line(var: Path, line: dict[str, Any]) -> None:
    month = datetime.fromtimestamp(line["ts"], UTC).strftime("%Y-%m")
    p = var / "runs" / f"{month}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n")
        f.flush()
        os.fsync(f.fileno())


def collect_once(
    cfg: PerpConfig,
    client: KrakenFuturesClient,
    store: PerpDataStore,
    var: Path,
    now_ts: int,
    *,
    backfill_s: int | None = None,
    clock: Callable[[], float] = time.monotonic,
    news: NewsConfig | None = None,
    news_get: Callable[[str], Any] | None = None,
) -> RunReport:
    """One collection run. Market-data and storage errors go into the report, per instrument.

    `backfill_s` given explicitly (the --backfill-days option) also fetches BACKWARDS, before the first
    stored record; by default (None) the run only catches up forwards, at most `cfg.backfill_s`.

    `news` (enabled) and `news_get`: Kraken's announcements are read too (docs/SPEC-PERP-NEWS.md); an
    error there is recorded and never touches the market data.
    """
    t0 = clock()
    report = RunReport(ts=now_ts, config_sha256=cfg.sha256)
    explicit = backfill_s is not None
    backfill = cfg.backfill_s if backfill_s is None else backfill_s
    if not 0 < backfill <= cfg.max_backfill_s:
        raise ValueError(f"backfill must be in (0, {cfg.max_backfill_s}] seconds")
    horizon = now_ts - backfill
    state = _load_state(var)
    symbols = [i.kraken_symbol for i in cfg.instruments]

    def count(key: str, n: int) -> None:
        report.counts[key] = report.counts.get(key, 0) + n

    def guarded(label: str, fn: Callable[[], None]) -> None:
        try:
            fn()
        except RECORDED_ERRORS as exc:
            report.errors.append(f"{label}: {type(exc).__name__}: {exc}"[:400])

    def unrecoverable(label: str, last: int, step: int) -> None:
        """An outage longer than the automatic catch-up leaves a hole: say so, never silently."""
        if last + step < horizon:
            report.errors.append(
                f"{label}: hole of {horizon - last - step} s before {horizon} not fetched "
                f"(longer than backfill_s); run with --backfill-days to fill it if needed"
            )

    # 1. Snapshot: the tickers that could be read, and EUR/USD. Stored even if partial.
    def snapshot() -> None:
        tickers, problems = client.tickers(symbols)
        for sym, why in sorted(problems.items()):
            report.errors.append(f"{sym} ticker: {why}"[:400])
        fx = None
        try:
            fx = client.eurusd(cfg.fx_pair)
        except RECORDED_ERRORS as exc:
            report.errors.append(f"fx: {type(exc).__name__}: {exc}"[:400])
        if tickers or fx:
            snap = TickerSnapshot(
                ts=now_ts, tickers=tuple(tickers[s] for s in symbols if s in tickers), fx=fx
            )
            count("tickers", store.tickers().add([snap]))

    guarded("tickers", snapshot)

    iv = cfg.candle_interval_s
    oiv = cfg.open_interest_interval_s
    try:
        # 1b. Kraken's official announcements (small payloads, before the per-instrument loop and its deadline)
        if news is not None and news.enabled and news_get is not None:

            def announcements() -> None:
                for k, v in collect_news(news, news_get, store.root / "news", state, now_ts, symbols).items():
                    count(k, v)

            guarded("news", announcements)
        for n, inst in enumerate(cfg.instruments):
            # The deadline protects the 5-minute timer; an explicit backfill (run by hand) may take longer.
            if not explicit and clock() - t0 > cfg.run_deadline_s:
                skipped = [i.kraken_symbol for i in cfg.instruments[n:]]
                report.errors.append(f"run deadline of {cfg.run_deadline_s} s reached, skipped {skipped}")
                break
            sym = inst.kraken_symbol

            # 2. One-minute candles of each kind.
            for kind in cfg.candle_kinds:

                def candles(kind: str = kind, sym: str = sym) -> None:
                    series = store.candles(kind, sym, iv)
                    last, first = series.last_ts(), series.first_ts()
                    if last is None:
                        start = horizon
                    else:
                        unrecoverable(f"{sym} candles {kind}", last, iv)
                        start = max(horizon, last + iv)
                    fetched = client.candles(kind, sym, iv, -(-start // iv) * iv, now_ts)
                    count(f"candles_{kind}", series.add(fetched))
                    if explicit and first is not None and first > horizon:
                        older = client.candles(kind, sym, iv, -(-horizon // iv) * iv, first)
                        count(f"candles_{kind}_backfill", series.add(older))

                guarded(f"{sym} candles {kind}", candles)

            # 3. Funding: the rate stamped H is published at H. Kraken returns the whole history (about one
            # year) in one call, so the first call stores all of it, and later calls only when H is due.
            def funding(sym: str = sym) -> None:
                series = store.funding(sym)
                last = series.last_ts()
                due_stamp = now_ts // HOUR_S * HOUR_S
                tried = state.get("funding_attempt", {}).get(sym)
                throttled = isinstance(tried, int) and 0 <= now_ts - tried < cfg.funding_retry_s
                if (last is None or due_stamp > last) and not throttled:
                    state.setdefault("funding_attempt", {})[sym] = now_ts
                    rates = client.funding_history(sym)
                    count("funding", series.add(r for r in rates if last is None or r.ts > last))
                    last = series.last_ts()
                if last is not None and now_ts - last > FUNDING_STALE_S:
                    report.errors.append(f"{sym} funding: last stamp is {now_ts - last} s old")

            guarded(f"{sym} funding", funding)

            # 4. Open interest: a new hourly candle is due once the previous hour is closed.
            def open_interest(sym: str = sym) -> None:
                series = store.open_interest(sym, oiv)
                last, first = series.last_ts(), series.first_ts()
                last_closed = (now_ts - CLOSE_GRACE_S) // oiv * oiv - oiv
                since: int | None
                if last is None:
                    since = horizon
                elif last < last_closed:
                    unrecoverable(f"{sym} open_interest", last, oiv)
                    since = max(horizon, last + oiv)
                else:
                    since = None
                if since is not None:
                    fetched = client.open_interest(sym, oiv, -(-since // oiv) * oiv)
                    count("open_interest", series.add(fetched))
                if explicit and first is not None and first > horizon:
                    fetched = client.open_interest(sym, oiv, -(-horizon // oiv) * oiv)
                    count("open_interest_backfill", series.add(o for o in fetched if o.ts < first))

            guarded(f"{sym} open_interest", open_interest)

            # 5. Order book.
            def book(sym: str = sym) -> None:
                count("books", store.books(sym).add([client.order_book(sym, cfg.book_depth)]))

            guarded(f"{sym} book", book)
    finally:
        _save_state(var, state)

    misaligned = getattr(client, "misaligned_rows", 0)
    if misaligned:
        report.counts["misaligned_rows_dropped"] = misaligned
    report.errors.extend(f"store: {w}"[:400] for w in store.warnings)
    report.duration_ms = int((clock() - t0) * 1000)
    return report


# ---------------------------------------------------------------------- quality report


def gap_report(cfg: PerpConfig, store: PerpDataStore, var: Path, now_ts: int, days: int) -> dict[str, Any]:
    """Coverage over the last `days` days, measured up to the LAST collection run (not up to now).

    An empty series counts as entirely missing. A missing one-minute TRADE candle can be legitimate (no
    trade in that minute); Kraken's own funding history also has holes (hours absent at the source), so a
    few missing funding hours after a backfill are expected. Missing MARK or SPOT candles, missing runs or
    a long `seconds_since_last_run` are collector problems.
    """
    since = now_ts - days * 86400
    snaps = store.tickers().load(since, now_ts + 1)
    last_run = snaps[-1].ts if snaps else None
    ref = last_run if last_run is not None else now_ts
    iv, oiv = cfg.candle_interval_s, cfg.open_interest_interval_s

    def coverage(present: list[int], step: int, start: int, end: int) -> dict[str, Any]:
        return {
            "from": start,
            "to": end,
            "present": len(present),
            "missing": len(missing_steps(present, step, start, end)),
            "empty": not present,
        }

    out: dict[str, Any] = {"now_ts": now_ts, "days": days, "last_run_ts": last_run, "instruments": {}}
    # Candle and open-interest stamps strictly before these bounds were closed at the last run.
    cend = (ref - CLOSE_GRACE_S) // iv * iv - iv + 1
    oend = (ref - CLOSE_GRACE_S) // oiv * oiv - oiv + 1
    fend = ref // HOUR_S * HOUR_S + 1  # the funding stamp of the current hour is published at that hour
    for inst in cfg.instruments:
        sym = inst.kraken_symbol
        row: dict[str, Any] = {}
        for kind in cfg.candle_kinds:
            series = store.candles(kind, sym, iv)
            first = series.first_ts()
            start = max(since, first) if first is not None else since
            row[f"candles_{kind}"] = coverage([c.ts for c in series.load(start, cend)], iv, start, cend)
        fseries = store.funding(sym)
        ffirst = fseries.first_ts()
        fstart = max(since, ffirst) if ffirst is not None else since
        row["funding"] = coverage([r.ts for r in fseries.load(fstart, fend)], HOUR_S, fstart, fend)
        oseries = store.open_interest(sym, oiv)
        ofirst = oseries.first_ts()
        ostart = max(since, ofirst) if ofirst is not None else since
        row["open_interest"] = coverage([o.ts for o in oseries.load(ostart, oend)], oiv, ostart, oend)
        books = store.books(sym).load(since, now_ts + 1)
        row["books"] = len(books)
        row["crossed_books"] = sum(1 for b in books if b.crossed)
        row["snapshots_without_ticker"] = sum(
            1 for s in snaps if sym not in {t.kraken_symbol for t in s.tickers}
        )
        out["instruments"][sym] = row

    out["ticker_snapshots"] = len(snaps)
    out["snapshots_without_fx"] = sum(1 for s in snaps if s.fx is None)
    out["seconds_since_last_run"] = None if last_run is None else now_ts - last_run
    if snaps:
        ts = [s.ts for s in snaps]
        out["max_gap_between_runs_s"] = max((b - a for a, b in pairwise(ts)), default=0)
        slots = {t // RUN_SLOT_S for t in ts}
        out["missing_run_slots"] = (ts[-1] // RUN_SLOT_S - ts[0] // RUN_SLOT_S + 1) - len(slots)
    runs = _read_runs(var, since, now_ts)
    out["runs"] = {
        "total": len(runs),
        "with_errors": sum(1 for r in runs if r.get("ok") is False and "crash" not in r),
        "crashed": sum(1 for r in runs if "crash" in r),
        "skipped": sum(1 for r in runs if "skipped" in r),
    }
    return out


def _read_runs(var: Path, since: int, until: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    d = var / "runs"
    if not d.exists():
        return out
    for p in sorted(d.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict) and isinstance(rec.get("ts"), int) and since <= rec["ts"] <= until:
                out.append(rec)
    return out


# ---------------------------------------------------------------------- command line


def _spot_var() -> Path:
    return Path(os.environ.get("ARENA_VAR") or REPO / "var").resolve()


def main(
    argv: list[str] | None = None, client_factory: Callable[[], KrakenFuturesClient] | None = None
) -> int:
    ap = argparse.ArgumentParser(prog="python -m arena.perp.collect", description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["run", "report"])
    ap.add_argument(
        "--var", type=Path, default=None, help="state directory (default: $ARENA_PERP_VAR or var-perp/)"
    )
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--backfill-days", type=int, default=None, help="run: also fetch backwards, N days")
    ap.add_argument("--days", type=int, default=7, help="report: window in days")
    ap.add_argument("--news-config", type=Path, default=NEWS_CONFIG)
    args = ap.parse_args(argv)

    try:
        cfg = load_perp_config(args.config)
    except PerpConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    var = (args.var or default_var()).resolve()
    spot = _spot_var()
    if var == spot or spot in var.parents:
        print(f"refusing to use the spot league state directory {spot} for the perp league", file=sys.stderr)
        return EXIT_USAGE
    store = PerpDataStore(data_root(var))
    now_ts = int(time.time())

    if args.command == "report":
        print(json.dumps(gap_report(cfg, store, var, now_ts, args.days), indent=1, sort_keys=True))
        return EXIT_OK

    backfill_s = None if args.backfill_days is None else args.backfill_days * 86400
    if backfill_s is not None and not 0 < backfill_s <= cfg.max_backfill_s:
        print(f"--backfill-days must be between 1 and {cfg.max_backfill_s // 86400}", file=sys.stderr)
        return EXIT_USAGE
    with run_lock(var) as acquired:
        if not acquired:
            line = {"ts": now_ts, "skipped": "lock busy"}
            append_run_line(var, line)
            print(json.dumps(line))
            return EXIT_OK
        client = (client_factory or KrakenFuturesClient)()
        news: NewsConfig | None = None
        news_error = None
        try:
            news = load_news_config(args.news_config)
        except (NewsConfigError, OSError) as exc:
            news_error = f"news config: {type(exc).__name__}: {exc}"[:400]
        try:
            report = collect_once(
                cfg,
                client,
                store,
                var,
                now_ts,
                backfill_s=backfill_s,
                news=news,
                news_get=getattr(client, "get_url_json", None),
            )
            if news_error:
                report.errors.append(news_error)
        except Exception as exc:
            append_run_line(var, {"ts": now_ts, "ok": False, "crash": f"{type(exc).__name__}: {exc}"[:400]})
            raise
        append_run_line(var, report.to_dict())
    print(json.dumps(report.to_dict(), sort_keys=True))
    return EXIT_OK if report.ok else EXIT_DATA_ERRORS


if __name__ == "__main__":
    sys.exit(main())
