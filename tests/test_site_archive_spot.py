"""Site, ligue comptant : un modèle archivé (`arene retire`, demande du 17/11) reste en pointillés, arrêté au retrait."""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import perp_fixture as F
from test_site import FABLE, SYMBOLS, synthetic_journal
from tests.test_site_perp import NOW, _cfg, _ligne_tableau, lire, texte

from arene.ledger import replay
from arene.site import build, data
from arene.site.render import jj_mm

RETIRE_APRES = 50


@pytest.fixture(scope="module")
def site_spot_archive(tmp_path_factory) -> tuple[Path, Path]:
    tmp = tmp_path_factory.mktemp("spot-archive")
    spot = synthetic_journal(tmp / "var" / "journal" / "events.jsonl", avec_fable=True, retire_fable_apres=RETIRE_APRES)
    perp = F.build(tmp / "var-perp" / "journal" / "events.jsonl")
    out = tmp / "site"
    config, policy = _cfg()
    build(spot.path, out, config=config, policy=policy, now_ts=NOW, public=True, racine="/arene/", perp_journal=perp)
    return out, spot.path


def test_donnees_courbe_figee_au_retrait(site_spot_archive):
    out, journal = site_spot_archive
    config, policy = _cfg()
    d = data.compute(journal, config, policy, NOW)
    par_id = {p["id"]: p for p in d["portfolios"]}
    arch = par_id[FABLE]["archive"]
    assert arch is not None and set(arch) == {"ts", "equity_ueur"}  # la note libre n'est jamais lue
    assert par_id["llm:claude-sonnet-5-5"]["archive"] is None
    flat = replay(__import__("arene.journal", fromlist=["Journal"]).Journal(journal).iter_events())[FABLE]
    assert not flat.positions and arch["equity_ueur"] == flat.cash_ueur == par_id[FABLE]["equity_ueur"]
    assert par_id[FABLE]["total_return"] == pytest.approx(arch["equity_ueur"] / par_id[FABLE]["base_ueur"] - 1)
    s = {x["id"]: x for x in d["chart"]["series"]}
    assert s[FABLE]["archive_ts"] == arch["ts"] and "archive_ts" not in s["llm:claude-sonnet-5-5"]
    x = d["chart"]["x"]
    vals = s[FABLE]["values"]
    assert any(t > arch["ts"] for t in x)  # les autres continuent
    assert all(v is None for v, t in zip(vals, x, strict=True) if t > arch["ts"])
    dernier = [v for v in vals if v is not None][-1]
    assert dernier == pytest.approx(arch["equity_ueur"] / par_id[FABLE]["base_ueur"] * 100, abs=1e-3)  # figé à la vente


def test_comptant_pointilles_classement_tableau_et_fiche(site_spot_archive):
    out, _ = site_spot_archive
    page = lire(out, "comptant.html")
    assert "NOTE_PRIVEE" not in page
    courbe = json.loads(html.unescape(re.search(r'<script id="equity-data"[^>]*>(.*?)</script>', page).group(1)))
    st = {s["id"]: t for s, t in zip(courbe["series"], courbe["styles"], strict=True)}
    assert st[FABLE]["dash"] == [1, 6] and st[FABLE]["archive"]
    assert not st["llm:claude-sonnet-5-5"].get("archive")
    legende = re.search(r'<ul class="legende".*?</ul>', page, flags=re.DOTALL).group(0)
    arch_ts = next(s["archive_ts"] for s in courbe["series"] if s["id"] == FABLE)
    assert legende.count(f"retiré le {jj_mm(arch_ts)}") == 1
    t = texte(page)
    assert "Courbes en pointillés" in t and "archivé" in t
    classement = re.search(r'<ol class="scores".*?</ol>', page, flags=re.DOTALL).group(0)
    lignes = re.findall(r'<li class="sc[^"]*".*?</li>', classement, flags=re.DOTALL)
    assert "Fable" in lignes[-1] and "sc-archive-ligne" in lignes[-1] and "sw-archive" in lignes[-1]
    assert "retiré le" in texte(lignes[-1]) and '<span class="sc-rang">—</span>' in lignes[-1]
    ligne = _ligne_tableau(page, "Claude Fable 5.2")
    assert 'class="llm archive"' in ligne and "archivé le" in texte(ligne)
    fiche = texte(lire(out, "modele/llm-claude-fable-5-2.html"))
    assert "IA archivée" in fiche and "ses chiffres sont figés" in fiche and "Courbes en pointillés" not in fiche
    assert "archivé, positions vendues" in fiche  # la vente de retrait, nommée dans les opérations
    accueil = lire(out, "index.html")
    assert "NOTE_PRIVEE" not in accueil
    assert SYMBOLS  # (le fixture couvre les six paires)
