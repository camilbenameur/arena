"""Site: an archived solo AI (Fable) stays dotted in the solo AIs league."""

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
from tests.test_site_perp import NOW, _cfg, _table_row, _perp, read, text

from arena.site import build
from arena.site.render import short_date

FABLE = "llm-perp:claude-fable-5-2"


@pytest.fixture(scope="module")
def site_fable_archive(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("perp-fable-archive")
    spot = synthetic_journal(tmp / "var" / "journal" / "events.jsonl")
    perp = F.build(tmp / "var-perp" / "journal" / "events.jsonl", archive_fable=True)
    out = tmp / "site"
    config, policy = _cfg()
    build(spot.path, out, config=config, policy=policy, now_ts=NOW, public=True, root_path="/arena/", perp_journal=perp)
    return out


def test_an_archived_ai_only_curve_is_dotted_and_stops_at_withdrawal(site_fable_archive):
    site = site_fable_archive
    d = _perp(site)
    end = F.T0 + 2 * 86_400 - 3_600
    by_id = {p["id"]: p for p in d["portfolios"]}
    assert by_id[FABLE]["archive"] == {"ts": end, "reason": "archive"}  # the free-text note never leaves the journal
    assert by_id[F.LLMS[0]]["archive"] is None
    series = {s["id"]: s for s in d["chart"]["series"]}
    x = d["chart"]["x"]
    assert series[FABLE]["archive_ts"] == end and end in x and x[-1] > end
    assert all(w is None for w, t in zip(series[FABLE]["values"], x, strict=True) if t > end)
    page = read(site, "derivatives.html")
    assert "private free text" not in page
    curve = json.loads(html.unescape(re.search(r'<script id="equity-data"[^>]*>(.*?)</script>', page).group(1)))
    st = {s["id"]: t for s, t in zip(curve["series"], curve["styles"], strict=True)}
    assert st[FABLE]["dash"] == [1, 6] and st[FABLE]["archive"]
    assert not st[F.LLMS[0]].get("archive")
    legend = re.search(r'<ul class="legend".*?</ul>', page, flags=re.DOTALL).group(0)
    assert legend.count(f"withdrawn on {short_date(end)}") == 1
    t = text(page)
    assert "Dotted curves" in t and "Three Claude AIs" in t
    ranking = re.search(r'<ol class="scores".*?</ol>', page, flags=re.DOTALL).group(0)
    lines = re.findall(r'<li class="sc[^"]*".*?</li>', ranking, flags=re.DOTALL)
    assert "Fable" in lines[-1] and "sc-archive-line" in lines[-1] and "sw-archive" in lines[-1]
    assert "withdrawn on" in text(lines[-1]) and '<span class="sc-rank">—</span>' in lines[-1]
    assert 'class="llm archive"' in _table_row(page, "Claude Fable 5.2")
    sheet = text(read(site, "derivatives/llm-perp-claude-fable-5-2.html"))
    assert "Archived AI" in sheet and "its figures are frozen" in sheet and "Pending" not in sheet
    assert "archived, dotted" in text(read(site, "index.html"))
