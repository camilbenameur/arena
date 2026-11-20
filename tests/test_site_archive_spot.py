"""Spot league site: an archived model (`arena retired`) stays dotted, stopped at its withdrawal."""

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
from tests.test_site_perp import NOW, _cfg, _table_row, read, text

from arena.ledger import replay
from arena.site import build, data
from arena.site.render import short_date

RETIRE_AFTER = 50


@pytest.fixture(scope="module")
def site_spot_archive(tmp_path_factory) -> tuple[Path, Path]:
    tmp = tmp_path_factory.mktemp("spot-archive")
    spot = synthetic_journal(tmp / "var" / "journal" / "events.jsonl", with_fable=True, retired_fable_after=RETIRE_AFTER)
    perp = F.build(tmp / "var-perp" / "journal" / "events.jsonl")
    out = tmp / "site"
    config, policy = _cfg()
    build(spot.path, out, config=config, policy=policy, now_ts=NOW, public=True, root_path="/arena/", perp_journal=perp)
    return out, spot.path


def test_curve_data_is_pinned_at_withdrawal(site_spot_archive):
    out, journal = site_spot_archive
    config, policy = _cfg()
    d = data.compute(journal, config, policy, NOW)
    by_id = {p["id"]: p for p in d["portfolios"]}
    arch = by_id[FABLE]["archive"]
    assert arch is not None and set(arch) == {"ts", "equity_ueur"}  # the free-text note is never read
    assert by_id["llm:claude-sonnet-5-5"]["archive"] is None
    flat = replay(__import__("arena.journal", fromlist=["Journal"]).Journal(journal).iter_events())[FABLE]
    assert not flat.positions and arch["equity_ueur"] == flat.cash_ueur == by_id[FABLE]["equity_ueur"]
    assert by_id[FABLE]["total_return"] == pytest.approx(arch["equity_ueur"] / by_id[FABLE]["base_ueur"] - 1)
    s = {x["id"]: x for x in d["chart"]["series"]}
    assert s[FABLE]["archive_ts"] == arch["ts"] and "archive_ts" not in s["llm:claude-sonnet-5-5"]
    x = d["chart"]["x"]
    vals = s[FABLE]["values"]
    assert any(t > arch["ts"] for t in x)  # the others continue
    assert all(v is None for v, t in zip(vals, x, strict=True) if t > arch["ts"])
    last = [v for v in vals if v is not None][-1]
    assert last == pytest.approx(arch["equity_ueur"] / by_id[FABLE]["base_ueur"] * 100, abs=1e-3)  # frozen at the sale


def test_spot_dotted_ranking_table_and_sheet(site_spot_archive):
    out, _ = site_spot_archive
    page = read(out, "spot.html")
    assert "NOTE_PRIVATE" not in page
    curve = json.loads(html.unescape(re.search(r'<script id="equity-data"[^>]*>(.*?)</script>', page).group(1)))
    st = {s["id"]: t for s, t in zip(curve["series"], curve["styles"], strict=True)}
    assert st[FABLE]["dash"] == [1, 6] and st[FABLE]["archive"]
    assert not st["llm:claude-sonnet-5-5"].get("archive")
    legend = re.search(r'<ul class="legend".*?</ul>', page, flags=re.DOTALL).group(0)
    arch_ts = next(s["archive_ts"] for s in curve["series"] if s["id"] == FABLE)
    assert legend.count(f"withdrawn on {short_date(arch_ts)}") == 1
    t = text(page)
    assert "Dotted curves" in t and "archived" in t
    ranking = re.search(r'<ol class="scores".*?</ol>', page, flags=re.DOTALL).group(0)
    lines = re.findall(r'<li class="sc[^"]*".*?</li>', ranking, flags=re.DOTALL)
    assert "Fable" in lines[-1] and "sc-archive-line" in lines[-1] and "sw-archive" in lines[-1]
    assert "withdrawn on" in text(lines[-1]) and '<span class="sc-rank">—</span>' in lines[-1]
    line = _table_row(page, "Claude Fable 5.2")
    assert 'class="llm archive"' in line and "archived on" in text(line)
    sheet = text(read(out, "model/llm-claude-fable-5-2.html"))
    assert "Archived AI" in sheet and "its figures are frozen" in sheet and "Dotted curves" not in sheet
    assert "archived, positions sold" in sheet  # the withdrawal sale, named in the operations
    home = read(out, "index.html")
    assert "NOTE_PRIVATE" not in home
    assert SYMBOLS  # (the fixture covers the six pairs)
