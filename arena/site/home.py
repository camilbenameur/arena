"""Home page of the three leagues and the shared scoreboard ("scoreboard" design direction).

The first screen of each league: one sentence that states the experiment, then the ranking and the chart side by side.
No large headline: the returns and the curve carry the screen.
"""

from __future__ import annotations

from typing import Any

from arena.site import render as R
from arena.site.render import e, eur, short_date, layout, pct, tone


def colors(chart: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Style of each series (id -> style from render._styles): the ranking dot has the colour of its curve."""
    return {s["id"]: st for s, st in zip(chart["series"], R._styles(chart, None), strict=True)}


def swatch(st: dict[str, Any] | None) -> str:
    if not st:
        return '<span class="sw sw-ref" aria-hidden="true"></span>'
    dotted = " sw-archive" if st.get("archive") else " sw-ref" if st.get("dash") else ""
    return f'<span class="sw c{e(st["color"])}{dotted}" aria-hidden="true"></span>'


def _tied(rows: list[dict[str, Any]]) -> None:
    """Tied ranks: two equal returns (to the displayed hundredth of a percent) share the same rank."""
    prev, rank = None, 0
    for i, r in enumerate(rows, 1):
        if r.get("archive"):  # an archived council is no longer ranked: its value is frozen at its withdrawal
            r["rank"] = None
            continue
        v = None if r.get("ret") is None else round(r["ret"] * 10_000)
        if v != prev:
            rank, prev = i, v
        r["rank"] = rank


def scores(rows: list[dict[str, Any]], *, label: str, mini: bool = False) -> str:
    """Ranking: rank, curve-colour dot, name (link) and subtitle, return in large type.

    Each row: {name, href, below, ret (fraction or None), st (curve style), rank (int or None), attrs (live-price
    hooks), value (optional text)}. A missing rank (reference, joined mid-way) is written "—"."""
    items = []
    for r in rows:
        rank = str(r["rank"]) if r.get("rank") else "—"
        below = f'<span class="sc-sub">{e(r["below"])}</span>' if r.get("below") else ""
        if r.get("archive"):
            below += f'<span class="sc-sub sc-archive"><span class="tag-archive">archived</span> withdrawn on {short_date(r["archive"]["ts"])}</span>'
        val = f'<span class="sc-eur">{r["value"]}</span>' if r.get("value") else ""
        items.append(
            f'<li class="sc{" sc-ref" if r.get("ref") else ""}{" sc-archive-line" if r.get("archive") else ""}"><span class="sc-rank">{rank}</span>{swatch(r.get("st"))}'
            f'<span class="sc-name"><a href="{e(r["href"])}">{e(r["name"])}</a>{below}</span>'
            f'<span class="sc-val"><span class="{tone(r.get("ret"))}"{r.get("attrs", "")}>{pct(r.get("ret"))}</span>{val}</span></li>'
        )
    return f'<ol class="scores{" mini" if mini else ""}" aria-label="{e(label)}">{"".join(items)}</ol>'


def front_section(*, title: str, lead: str, ranking: str, curve: str, after: str = "") -> str:
    """First screen of a league: the sentence, then ranking and chart side by side (stacked on phones)."""
    return (
        f'<section class="front" aria-labelledby="title-page"><h1 id="title-page" class="title-page">{title}</h1>'
        f'<p class="lead-page">{lead}</p>'
        f'<div class="front-grid"><div class="front-ranking">{ranking}{after}</div>'
        f'<div class="front-curve">{curve}</div></div></section>'
    )


def sparkline(chart: dict[str, Any], ids: list[str]) -> str:
    """Small decorative curve (the values are written next to it): the series of each id, on a common scale."""
    styles = colors(chart)
    series = [s for s in chart["series"] if s["id"] in ids]
    vals = [v for s in series for v in s["values"] if v is not None]
    if len(chart["x"]) < 3 or not vals:
        return ""
    lo, hi = min(vals + [100.0]), max(vals + [100.0])
    span = max(hi - lo, 0.5)
    x0, x1 = chart["x"][0], chart["x"][-1]
    w, h = 300, 80

    def y(v: float) -> float:
        return round(h - 4 - (v - lo) / span * (h - 8), 1)

    lines = [f'<line class="spark-zero" x1="0" x2="{w}" y1="{y(100.0)}" y2="{y(100.0)}"/>']
    for s in series:
        pts = " ".join(
            f"{round((x - x0) / max(1, x1 - x0) * w, 1)},{y(v)}"
            for x, v in zip(chart["x"], s["values"], strict=True)
            if v is not None
        )
        st = styles.get(s["id"]) or {}
        dotted = " spark-archive" if st.get("archive") else " spark-ref" if st.get("dash") else " spark-halo" if st.get("halo") else ""
        lines.append(
            f'<polyline class="spark-l s{e(st.get("color", "--muted"))}{dotted}" points="{pts}"/>'
        )
    return f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">{"".join(lines)}</svg>'


SUB_BENCHMARKS = {
    "benchmark-perp:basket-1x": "no AI · buys and holds the 6 cryptos",
    "benchmark-perp:trend": "no AI · follows the 20-day trend",
    "benchmark-perp:random": "no AI · decides at random",
    "benchmark:basket": "no AI · buys and holds the 6 cryptos",
    "benchmark:6040": "no AI · 60% bitcoin, 40% euros",
    "benchmark:e0065": "no AI · fixed rule on buying pressure",
    "benchmark:random": "no AI · decides at random",
}


def _sort_and_rank(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A single ranking, AIs and benchmarks mixed: if a rule without AI leads, it shows (nothing hidden)."""
    rows.sort(key=lambda r: (bool(r.get("archive")), -(r["ret"] if r["ret"] is not None else -9.0)))
    _tied(rows)
    return rows


def _perp_rows(league: dict[str, Any]) -> list[dict[str, Any]]:
    from arena.site import render_perp as RP

    st = colors(league["chart"])
    rows = []
    for p in league["portfolios"]:
        benchmark = p["kind"] not in ("llm", "council", "robot")  # a robot without AI plays: it is not a reference
        rows.append({
            "name": p["name"], "href": f"{RP._folder(p)}/{p['slug']}.html", "ret": p["net_return"], "st": st.get(p["id"]),
            "below": SUB_BENCHMARKS.get(p["id"], "no AI") if benchmark else (p.get("subtitle") or ""),
            "ref": benchmark, "attrs": RP._live_attrs(p, "ret"), "id": p["id"], "archive": p.get("archive"),
        })  # fmt: skip
    return _sort_and_rank(rows)


def _spot_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    st = colors({"series": data["chart"]["series"]}) if data.get("chart") else {}
    rows = []
    for p in data["portfolios"]:
        benchmark = p["kind"] != "llm"
        below = (
            SUB_BENCHMARKS.get(p["id"], "no AI")
            if benchmark
            else ("has not bought anything yet: all in cash" if not p.get("n_trades") else "")
        )
        rows.append({
            "name": p["name"], "href": f"model/{p['slug']}.html", "ret": p["total_return"], "st": st.get(p["id"]),
            "below": below, "ref": benchmark, "id": p["id"], "archive": p.get("archive"),
        })  # fmt: skip
    return _sort_and_rank(rows)


def _card(
    *, href: str, title: str, what: str, rows: list[dict[str, Any]], chart: dict[str, Any] | None, label: str
) -> str:
    """The top three of the ranking (a benchmark that leads shows up), plus the basket if it is not among them."""
    top = rows[:3]
    top += [r for r in rows[3:] if r.get("id") in R.REFERENCES or str(r.get("id", "")).endswith("basket-1x")]
    spark = sparkline(chart, [r["id"] for r in top]) if chart else ""
    return (
        f'<article class="league-card"><h2 class="league-title"><a href="{href}">{title}</a></h2>'
        f'<p class="league-what">{what}</p>{spark}{scores(top, label=label, mini=True)}'
        f'<p class="league-link"><a href="{href}">See the league, the decisions and their reasons<span aria-hidden="true">→</span></a></p></article>'
    )


def _join_and(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def home_page(data: dict[str, Any]) -> str:
    """The home page: what the experiment is in two sentences, then one card per league with its leader."""
    from arena.site.perp import TREND_COUNCILS

    perp = data["perp"]
    cards = []
    capital = eur(1_000_000_000, decimals=0)
    councils_league = perp.get("councils")
    if councils_league:
        rows = _perp_rows(councils_league)
        archives = [r for r in rows if r.get("archive")]
        what = f"Ten Claude Haiku give their opinion, a president decides: Haiku for one council, Opus for the other. Leverage up to 10, {capital} of play money each."
        if any(p["id"] in TREND_COUNCILS and not p.get("archive") for p in councils_league["portfolios"]):
            what = (
                "A trend engine decides each position; three Claude Haiku and an Opus president can only brake it. "
                f"Leverage up to 10, {capital} of play money. The earlier councils, with the Trend Council at 2x, are archived: their curves remain dotted."
            )
        elif archives and len(archives) == sum(1 for p in councils_league["portfolios"] if p["kind"] == "council"):
            what = "The first two councils, Haiku President and Opus President, are archived: their curves remain dotted."
        cards.append(_card(
            href="councils.html", title="AI councils",
            what=what,
            rows=rows, chart=councils_league["chart"], label="Councils league ranking",
        ))  # fmt: skip
    rows = _perp_rows(perp)
    solos = [p for p in perp["portfolios"] if p["kind"] == "llm"]
    active_names = [p["name"].replace("Claude ", "") for p in solos if not p.get("archive")]
    what_solo = f"Haiku, Sonnet, Opus and Fable each decide alone, betting on a rise or a decline. Leverage up to 2, {capital} of play money each."
    if solos and active_names and len(active_names) < len(solos):
        archived_names = [p["name"].replace("Claude ", "") for p in solos if p.get("archive")]
        what_solo = (
            f"{_join_and(active_names)} each decide alone, betting on a rise or a decline. Leverage up to 2, {capital} of play money each. "
            f"{_join_and(archived_names)}: archived, dotted."
        )
    cards.append(_card(
        href="derivatives.html", title="Solo AIs",
        what=what_solo,
        rows=rows, chart=perp["chart"], label="Solo AIs league ranking",
    ))  # fmt: skip
    if data.get("portfolios"):
        rows = _spot_rows(data)
        cards.append(_card(
            href="spot.html", title="Spot",
            what=f"The same AIs buy and sell crypto, with no bet on a decline and no leverage, every 4 h. {eur(data['method']['capital_ueur'], decimals=0)} of play money each.",
            rows=rows, chart=data.get("chart"), label="Spot league ranking",
        ))  # fmt: skip
    body = f"""
<section class="front front-home" aria-labelledby="title-page">
<h1 id="title-page" class="title-page">Claude AIs trade play money on real market prices. Do they do better than a simple rule without AI?</h1>
<p class="lead-page">Three leagues run continuously on Kraken prices, fees included. Every decision is published with its reason, and the journal is verifiable.</p>
</section>
<div class="leagues">{"".join(cards)}</div>
<section class="principles" aria-labelledby="title-principles">
<h2 id="title-principles">How it works</h2>
<dl class="principles-list">
<div><dt>Real prices, play money</dt><dd>Orders are simulated on Kraken's public prices, with its fees. No real euro is involved.</dd></div>
<div><dt>A benchmark without AI</dt><dd>Each league keeps a simple rule: buy and hold. A useful AI must do better than it, fees included.</dd></div>
<div><dt>Everything is published</dt><dd>What each AI decided, why, and what the guardrail refused. <a href="method.html">The method</a> details the rules.</dd></div>
</dl>
</section>
"""
    return layout(
        title="Home", body=body, root="", active="index", data=data, path="",
        complete_title="The Arena: Claude AIs trade play money", desc=R.DESCRIPTION_SITE,
    )  # fmt: skip
