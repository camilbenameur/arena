"""Dashboard statique privé (docs/SPEC-MVP.md §13) : `build(journal, out_dir, config=, policy=)`.

Tout est recalculé depuis le seul journal à chaque appel ; le dossier de sortie est remplacé atomiquement
(dossier temporaire voisin puis renommage). Aucune ressource externe : uPlot est copié depuis `vendor/`.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from arene.config import Config
from arene.risk.policy import Policy
from arene.site import accueil, render, render_perp
from arene.site import data as site_data
from arene.site import perp as site_perp

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"
ASSETS = HERE / "assets"
FONTS = HERE / "fonts"  # IBM Plex Sans et Mono (OFL-1.1), sous-ensemble latin, sommes dans fonts/SHA256SUMS
VENDOR_FILES = ("uPlot.iife.min.js", "uPlot.min.css", "LICENSE-uPlot.txt", "SHA256SUMS")

__all__ = ["build"]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _json(path: Path, obj: Any) -> None:
    _write(path, json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n")


def build(
    journal_path: Path, out_dir: Path, *, config: Config, policy: Policy, now_ts: int | None = None,
    public: bool = False, racine: str | None = None, perp_journal: Path | None = None,
) -> None:
    """`public` retire la ligne destinée à l'opérateur ; `racine` (chemin absolu du site, ex. « /arene/ »)
    sert à la page 404, servie à n'importe quelle profondeur par l'hébergeur.

    La ligue dérivés (`perp_journal`, par défaut <dépôt>/var-perp/journal/events.jsonl voisin du journal spot) passe
    au premier plan dès que son journal existe : l'accueil est alors la sienne, et le spot passe sur comptant.html."""
    journal_path, out_dir = Path(journal_path), Path(out_dir)
    data = site_data.compute(journal_path, config, policy, now_ts)
    data["public"] = public
    data["racine"] = racine or "/"
    pj = site_perp.perp_journal_path(journal_path) if perp_journal is None else Path(perp_journal)
    try:
        data["perp"] = site_perp.compute(pj, data["generated_ts"])
    except Exception:  # la ligue dérivés ne doit jamais empêcher la construction du site comptant
        logging.getLogger("arene.site").exception("ligue dérivés : calcul en échec, site construit sans elle")
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

        # JSON publiés (chacun avec venue_mode ; justifications publiées dès la décision).
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
            _json(tmp / "data" / f"modele-{p['slug']}.json", {**meta, **p})

        perp = data["perp"]
        if perp:
            _write(tmp / "index.html", accueil.accueil_page(data))
            _write(tmp / "derives.html", render_perp.index_page(data))
            _write(tmp / "comptant.html", render.index_page(data))
            for p in perp["portfolios"]:
                _write(tmp / "derives" / f"{p['slug']}.html", render_perp.portfolio_page(data, p))
            conseils = perp.get("conseils")
            if conseils:  # la ligue des conseils : même journal, sa propre page et une page par conseil
                _write(tmp / "conseils.html", render_perp.conseils_page(data))
                for p in conseils["portfolios"]:
                    if p["kind"] == "conseil" or p["id"] == "benchmark-perp:moteur-tendance":  # et son témoin « moteur seul »
                        _write(tmp / "conseils" / f"{p['slug']}.html", render_perp.portfolio_page(data, p))
                _json(tmp / "data" / "conseils.json", {**meta, **conseils})
            _json(tmp / "data" / "derives.json", {**meta, **{k: v for k, v in perp.items() if k != "conseils"}})  # déjà filtré par site.perp
        else:
            _write(tmp / "index.html", render.index_page(data))
        _write(tmp / "methode.html", render.methode_page(data))
        if racine is not None:
            _write(tmp / "404.html", render.page_404(data, racine))
        if public and racine is not None:  # version publique indexée (décision du propriétaire du 15/11) : plan du site et robots
            base = f"{render.SITE_HOTE}{racine}"
            pages = sorted(
                str(f.relative_to(tmp)) for f in tmp.rglob("*.html") if f.name != "404.html"
            ) + [f"modele/{p['slug']}.html" for p in data["portfolios"]]
            pages = sorted({("" if x == "index.html" else x) for x in pages})
            urls = "".join(f"<url><loc>{base}{x}</loc></url>" for x in pages)
            _write(tmp / "sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')
            _write(tmp / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {base}sitemap.xml\n")
        for p in data["portfolios"]:
            focus_chart = _model_chart(data, p)
            _write(tmp / "modele" / f"{p['slug']}.html", render.model_page(data, p, focus_chart))

        if out_dir.exists():
            os.replace(out_dir, old)
        os.replace(tmp, out_dir)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    shutil.rmtree(old, ignore_errors=True)


def _model_chart(data: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    """Courbe d'un portefeuille avec le panier en référence."""
    keep = {p["id"], "temoin:panier"}
    return {"x": data["chart"]["x"], "kinds": data["chart"].get("kinds", []),
            "series": [s for s in data["chart"]["series"] if s["id"] in keep]}
