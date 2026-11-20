"""Mechanical choice of the control universe (C16), frozen in `research/control_universe.json`.

Rule (criteria.yaml): the `size` largest quote volumes of January 2020 among the USDT spot symbols of
data.binance.vision, excluding the universe, delisted symbols included; stablecoins, fiat currencies and
leveraged tokens excluded; any symbol whose 2020-01 data is missing (archive absent or fewer than 31
daily bars) is dropped. The volume is the sum of the `quote_volume` of the 31 1d bars of 2020-01
(the monthly 1d archive contains exactly the bars of the daily archives).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx

from research.config import REPO, load_criteria
from research.data.reader import read_bars_zip
from research.data.download import MissingData, list_spot_symbols, log, download_month

CONTROL_UNIVERSE_PATH = REPO / "research" / "control_universe.json"
STABLES = frozenset({
    "USDC", "BUSD", "TUSD", "USDP", "DAI", "FDUSD", "PAX", "USDS", "USDSB", "SUSD", "UST", "USTC",
    "USDD", "GUSD", "HUSD", "LUSD", "EURI", "AEUR", "EUR", "GBP", "AUD", "TRY", "BRL", "RUB", "UAH",
    "NGN", "ZAR", "IDRT", "BIDR", "BVND", "VAI", "XUSD", "USD1", "PYUSD",
})
_LEVERAGE = re.compile(r"^[A-Z0-9]{2,}(UP|DOWN|BULL|BEAR)$")
RULE = ("largest quote volumes of January 2020 on data.binance.vision (USDT spot, complete 31-bar monthly 1d "
         "archive), excluding the universe, delisted symbols included, stablecoins, fiat currencies and leveraged "
         "tokens excluded; frozen before wave 1")


def eligible_candidate(symbol: str, universe: set[str] | frozenset[str]) -> bool:
    if not symbol.endswith("USDT") or symbol in universe:
        return False
    base = symbol[: -len("USDT")]
    return bool(base) and base not in STABLES and not _LEVERAGE.match(base)


def choose_control_universe(output: Path | str = CONTROL_UNIVERSE_PATH, cache: Path | str | None = None,
                             client: httpx.Client | None = None, date: str | None = None,
                             force: bool = False, candidates: list[str] | None = None) -> list[str]:
    """Return the frozen list; compute it (network) only if `output` does not exist (or `force`).

    `cache`: folder of the raw zips (same layout as the download; default
    `var/research/data/raw`). `candidates`: list of symbols to evaluate (default: public listing).
    """
    output = Path(output)
    crit = load_criteria()
    if output.exists() and not force:
        doc = json.loads(output.read_text())
        if len(doc["symbols"]) != crit.control_size:
            raise ValueError(f"{output} : {len(doc['symbols'])} symbols, {crit.control_size} expected")
        return list(doc["symbols"])
    cache = Path(cache) if cache else REPO / "var" / "research" / "data" / "raw"
    universe = frozenset(crit.universe)
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        listing = candidates if candidates is not None else list_spot_symbols(client)
        cand = sorted(s for s in listing if eligible_candidate(s, universe))
        log(f"control: {len(cand)} USDT candidates to evaluate on 2020-01")
        absent_file = cache / "control_absent_2020-01.txt"
        cache.mkdir(parents=True, exist_ok=True)
        absentees = set(absent_file.read_text().split()) if absent_file.exists() else set()
        volumes: dict[str, float] = {}
        for i, s in enumerate(cand, 1):
            if s in absentees:
                continue
            try:
                zp = download_month("spot_klines_1d", s, 2020, 1, cache, client)
            except MissingData:
                absentees.add(s)
                with absent_file.open("a") as f:
                    f.write(s + "\n")
                continue
            df = read_bars_zip(zp.read_bytes(), zp.name)
            if len(df) == 31:
                volumes[s] = float(df["quote_volume"].sum())
            if i % 25 == 0:
                log(f"control: {i}/{len(cand)} evaluated, {len(volumes)} with complete 2020-01")
    finally:
        if owns_client:
            client.close()
    ranked = sorted(volumes, key=lambda s: (-volumes[s], s))
    if len(ranked) < crit.control_size:
        raise ValueError(f"only {len(ranked)} eligible symbols, {crit.control_size} expected")
    chosen = ranked[: crit.control_size]
    doc = {
        "rule": RULE,
        "source": "https://data.binance.vision/data/spot/monthly/klines/<SYM>/1d/<SYM>-1d-2020-01.zip",
        "date": date or datetime.now(UTC).date().isoformat(),
        "size": crit.control_size,
        "n_candidates_with_2020_01_complete": len(volumes),
        "symbols": chosen,
        "quote_volume_2020_01": {s: volumes[s] for s in chosen},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    return chosen
