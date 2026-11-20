"""Complete, resumable build of `var/research/data/`."""

from __future__ import annotations

from pathlib import Path

import httpx

from research.config import REPO, load_criteria
from research.data.control import CONTROL_UNIVERSE_PATH, choose_control_universe
from research.data.lab import LAB_IN_SAMPLE, copy_in_sample
from research.data.manifest import build_manifest
from research.data.download import list_months, log, download_month

DEFAULT_ROOT = REPO / "var" / "research" / "data"


def build_data(root_path: Path | str = DEFAULT_ROOT, *, lab_src: Path | str = LAB_IN_SAMPLE,
                       control_universe_path: Path | str = CONTROL_UNIVERSE_PATH,
                       client: httpx.Client | None = None) -> dict:
    """Copy the lab candles, choose the control universe, download the archives (months <= 2026-06), build the manifest.

    Resumable: any file already present and verified is skipped without network access; progress goes to stderr.
    Returns the manifest. Duration: several hours at 1 request/s (about 8,000 archives with the control universe).
    """
    root_path = Path(root_path)
    root_path.mkdir(parents=True, exist_ok=True)
    crit = load_criteria()
    log(f"[1/4] copying the lab in-sample candles -> {root_path / 'lab'}")
    copy_in_sample(lab_src, root_path / "lab")
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        log("[2/4] control universe")
        control = choose_control_universe(control_universe_path, cache=root_path / "raw", client=client)
        plan: list[tuple[str, str, int, int]] = []
        log("[3/4] download plan (public listings)")
        requests = [(src, s) for s in crit.universe for src in ("perp_funding", "perp_klines_1h")]
        requests += [("spot_klines_1d", s) for s in control]
        # Control universe (C16): same sources as the main universe; a symbol without a perp simply has
        # no month listed (normal).
        requests += [(src, s) for s in control
                     for src in ("spot_klines_1h", "perp_klines_1h", "perp_funding")]
        for src, s in requests:
            plan += [(src, s, a, m) for a, m in list_months(src, s, client)]
        log(f"[4/4] {len(plan)} archives to verify/download")
        for k, (src, s, a, m) in enumerate(plan, 1):
            download_month(src, s, a, m, root_path / "raw", client)
            if k % 25 == 0 or k == len(plan):
                log(f"  {k}/{len(plan)} (last: {src} {s} {a}-{m:02d})")
    finally:
        if owns_client:
            client.close()
    doc = build_manifest(root_path, control_universe_path)
    log(f"manifest written: {len(doc['files'])} files")
    return doc
