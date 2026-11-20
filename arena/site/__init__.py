"""Static dashboard (docs/SPEC-MVP.md §13): `build(journal, out_dir, config=, policy=)`.

Everything is recomputed from the journal alone on every call; the output folder is replaced atomically
(neighbouring temporary folder, then rename). No external resource: uPlot is copied from `vendor/`.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from arena.config import Config
from arena.risk.policy import Policy
from arena.site import home, render, render_perp
from arena.site import data as site_data
from arena.site import perp as site_perp

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"
ASSETS = HERE / "assets"
FONTS = HERE / "fonts"  # IBM Plex Sans and Mono (OFL-1.1), Latin subset, checksums in fonts/SHA256SUMS
VENDOR_FILES = ("uPlot.iife.min.js", "uPlot.min.css", "LICENSE-uPlot.txt", "SHA256SUMS")

__all__ = ["build"]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _json(path: Path, obj: Any) -> None:
    _write(path, json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n")


def build(
    journal_path: Path, out_dir: Path, *, config: Config, policy: Policy, now_ts: int | None = None,
    public: bool = False, root_path: str | None = None, perp_journal: Path | None = None,
) -> None:
    """`public` removes the line meant for the operator; `root_path` (absolute path of the site, e.g. "/arena/")
    is used by the 404 page, which the host serves at any depth.

    The derivatives league (`perp_journal`, by default <repo>/var-perp/journal/events.jsonl next to the spot journal)
    comes to the front as soon as its journal exists: the home page then covers all leagues, and spot moves to spot.html."""
    journal_path, out_dir = Path(journal_path), Path(out_dir)
    data = site_data.compute(journal_path, config, policy, now_ts)
    data["public"] = public
    data["root_path"] = root_path or "/"
    pj = site_perp.perp_journal_path(journal_path) if perp_journal is None else Path(perp_journal)
    try:
        data["perp"] = site_perp.compute(pj, data["generated_ts"])
    except Exception:  # the derivatives league must never prevent the spot site from being built
        logging.getLogger("arena.site").exception("derivatives league: computation failed, site built without it")
        data["perp"] = None
    vm, gen = data["venue_mode"], data["generated_ts"]

    tmp = out_dir.with_name(f".{out_dir.name}.tmp-{os.getpid()}")
    old = out_dir.with_name(f".{out_dir.name}.old-{os.getpid()}")
    for d in (tmp, old):
        shutil.rmtree(d, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        (tmp / "vendor").mkdir()
        for name in VENDOR_FILES:
            shutil.copyfile(VENDOR / name, tmp / "vendor" / name)
        (tmp / "assets").mkdir()
        for f in ASSETS.iterdir():
            shutil.copyfile(f, tmp / "assets" / f.name)
        (tmp / "fonts").mkdir()
        for f in FONTS.iterdir():
            shutil.copyfile(f, tmp / "fonts" / f.name)

        # Published JSON (each with venue_mode; justifications are published as soon as the decision is made).
        meta = {"venue_mode": vm, "generated_ts": gen}
        _json(tmp / "data" / "summary.json", {
            **meta, "n_cycles": data["n_cycles"], "first_cycle_ts": data["first_cycle_ts"],
            "last_cycle_ts": data["last_cycle_ts"], "min_cycles_stats": data["min_cycles_stats"],
            "any_llm_distinguishable": data["any_llm_distinguishable"], "distribution": data["distribution"],
            "portfolios": [
                {k: v for k, v in p.items() if k not in ("decisions", "series_ueur", "positions")}
                for p in data["portfolios"]
            ],
        })  # fmt: skip
        _json(tmp / "data" / "equity.json", {**meta, **data["chart"], "unit": "base100"})
        _json(tmp / "data" / "method.json", {**meta, "journal": data["journal"], "provenance": data["provenance"], "method": data["method"]})
        for p in data["portfolios"]:
            _json(tmp / "data" / f"model-{p['slug']}.json", {**meta, **p})

        perp = data["perp"]
        if perp:
            _write(tmp / "index.html", home.home_page(data))
            _write(tmp / "derivatives.html", render_perp.index_page(data))
            _write(tmp / "spot.html", render.index_page(data))
            for p in perp["portfolios"]:
                _write(tmp / "derivatives" / f"{p['slug']}.html", render_perp.portfolio_page(data, p))
            councils = perp.get("councils")
            if councils:  # the councils league: same journal, its own page and one page per council
                _write(tmp / "councils.html", render_perp.councils_page(data))
                for p in councils["portfolios"]:
                    if p["kind"] == "council" or p["id"] == "benchmark-perp:trend-engine":  # and its "engine alone" benchmark
                        _write(tmp / "councils" / f"{p['slug']}.html", render_perp.portfolio_page(data, p))
                _json(tmp / "data" / "councils.json", {**meta, **councils})
            _json(tmp / "data" / "derivatives.json", {**meta, **{k: v for k, v in perp.items() if k != "councils"}})  # already filtered by site.perp
        else:
            _write(tmp / "index.html", render.index_page(data))
        _write(tmp / "method.html", render.method_page(data))
        if root_path is not None:
            _write(tmp / "404.html", render.page_404(data, root_path))
        if public and root_path is not None:  # indexed public version: sitemap and robots
            base = f"{render.SITE_HOST}{root_path}"
            pages = sorted(
                str(f.relative_to(tmp)) for f in tmp.rglob("*.html") if f.name != "404.html"
            ) + [f"model/{p['slug']}.html" for p in data["portfolios"]]
            pages = sorted({("" if x == "index.html" else x) for x in pages})
            urls = "".join(f"<url><loc>{base}{x}</loc></url>" for x in pages)
            _write(tmp / "sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')
            _write(tmp / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {base}sitemap.xml\n")
        for p in data["portfolios"]:
            focus_chart = _model_chart(data, p)
            _write(tmp / "model" / f"{p['slug']}.html", render.model_page(data, p, focus_chart))

        if out_dir.exists():
            os.replace(out_dir, old)
        os.replace(tmp, out_dir)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    shutil.rmtree(old, ignore_errors=True)


def _model_chart(data: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    """Curve of a portfolio with the basket as reference."""
    keep = {p["id"], "benchmark:basket"}
    return {"x": data["chart"]["x"], "kinds": data["chart"].get("kinds", []),
            "series": [s for s in data["chart"]["series"] if s["id"] in keep]}
