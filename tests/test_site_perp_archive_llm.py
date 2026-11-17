"""Site : une IA seule archivée (Fable, demande du 17/11) reste en pointillés dans la ligue des IA seules."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent))

import perp_fixture as F
from test_site import synthetic_journal
from tests.test_site_perp import NOW, _cfg, _ligne_tableau, _perp, lire, texte

from arene.site import build
from arene.site.render import jj_mm

FABLE = "llm-perp:claude-fable-5-2"


@pytest.fixture(scope="module")
def site_fable_archive(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("perp-fable-archive")
    spot = synthetic_journal(tmp / "var" / "journal" / "events.jsonl")
    perp = F.build(tmp / "var-perp" / "journal" / "events.jsonl", archive_fable=True)
    out = tmp / "site"
    config, policy = _cfg()
    build(spot.path, out, config=config, policy=policy, now_ts=NOW, public=True, racine="/arene/", perp_journal=perp)
    return out


def test_ia_seule_archivee_courbe_en_pointilles_arretee_au_retrait(site_fable_archive):
    site = site_fable_archive
    d = _perp(site)
    fin = F.T0 + 2 * 86_400 - 3_600
    par_id = {p["id"]: p for p in d["portfolios"]}
    assert par_id[FABLE]["archive"] == {"ts": fin, "raison": "archive"}  # la note libre ne sort pas du journal
    assert par_id[F.LLMS[0]]["archive"] is None
    series = {s["id"]: s for s in d["chart"]["series"]}
    x = d["chart"]["x"]
    assert series[FABLE]["archive_ts"] == fin and fin in x and x[-1] > fin
    assert all(w is None for w, t in zip(series[FABLE]["values"], x, strict=True) if t > fin)
    page = lire(site, "derives.html")
    assert "texte libre privé" not in page
    courbe = json.loads(html.unescape(re.search(r'<script id="equity-data"[^>]*>(.*?)</script>', page).group(1)))
    st = {s["id"]: t for s, t in zip(courbe["series"], courbe["styles"], strict=True)}
    assert st[FABLE]["dash"] == [1, 6] and st[FABLE]["archive"]
    assert not st[F.LLMS[0]].get("archive")
    legende = re.search(r'<ul class="legende".*?</ul>', page, flags=re.DOTALL).group(0)
    assert legende.count(f"retiré le {jj_mm(fin)}") == 1
    t = texte(page)
    assert "Courbes en pointillés" in t and "Trois IA Claude" in t
    classement = re.search(r'<ol class="scores".*?</ol>', page, flags=re.DOTALL).group(0)
    lignes = re.findall(r'<li class="sc[^"]*".*?</li>', classement, flags=re.DOTALL)
    assert "Fable" in lignes[-1] and "sc-archive-ligne" in lignes[-1] and "sw-archive" in lignes[-1]
    assert "retiré le" in texte(lignes[-1]) and '<span class="sc-rang">—</span>' in lignes[-1]
    assert 'class="llm archive"' in _ligne_tableau(page, "Claude Fable 5.2")
    fiche = texte(lire(site, "derives/llm-perp-claude-fable-5-2.html"))
    assert "IA archivée" in fiche and "ses chiffres sont figés" in fiche and "En attente" not in fiche
    assert "archivé, en pointillés" in texte(lire(site, "index.html"))
