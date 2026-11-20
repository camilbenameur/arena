"""HTML generation for the dashboard (no framework: f-strings). Any text coming from the journal is escaped.

No `style` attribute in the HTML: the CSP only allows the site's own style sheets (`style-src 'self'`).
Small gauges and bars are therefore SVGs whose width is an attribute, not a style.
"""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from arena.season import NAMES as FROZEN_ITEM_NAMES
from arena.site.data import RISK_CODES, SKIP_REASONS, name

NBSP = " "
NNBSP = " "  # kept for the modules that import it; the site no longer uses narrow no-break spaces
MINUS = "−"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

REAL_BANNER = "REAL MONEY"
NUMBERS_MIN = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}


def description(data: dict[str, Any]) -> str:
    """Meta description: the number of models and benchmarks comes from the journal, not from a constant."""
    n_llm = sum(1 for p in data.get("portfolios", ()) if p["kind"] == "llm" and not p.get("archive"))
    n_benchmarks = sum(1 for p in data.get("portfolios", ()) if p["kind"] != "llm")
    llm = f"{NUMBERS_MIN.get(n_llm, n_llm)} AI model{'s' if n_llm > 1 else ''}"
    handled = "each manage a" if n_llm > 1 else "manages a"
    return (
        f"{llm[:1].upper() + llm[1:]} {handled} simulated crypto portfolio, compared with "
        f"{NUMBERS_MIN.get(n_benchmarks, n_benchmarks)} simple rule{'s' if n_benchmarks > 1 else ''}. "
        "Decisions every 4 h, values sampled every 5 min, in simulation."
    )
WARNING = "Simulated experiment, not investment advice. Figures are before tax."
CSP = (
    "default-src 'none'; style-src 'self'; script-src 'self'; font-src 'self'; img-src 'self'; "
    "connect-src 'none'; base-uri 'none'; form-action 'none'"
)
# Derivatives pages with live prices: the browser reads Kraken Futures' public feed, nothing else.
DIRECT_FEED = "wss://futures.kraken.com/ws/v1"
CSP_DIRECT = CSP.replace("connect-src 'none'", "connect-src wss://futures.kraken.com")


def e(x: Any) -> str:
    """Systematic HTML escaping (quotes included)."""
    return html.escape("" if x is None else str(x), quote=True)


# ---------------------------------------------------------------------------
# English number and date formats
# ---------------------------------------------------------------------------


def _group(n: int) -> str:
    return f"{n:,}"


def eur(ueur: int | None, *, signed: bool = False, decimals: int = 2) -> str:
    if ueur is None:
        return "—"
    sign = MINUS if ueur < 0 else ("+" if signed and ueur > 0 else "")
    unit = 10 ** (6 - decimals)
    v = (abs(ueur) + unit // 2) // unit
    whole, frac = divmod(v, 10**decimals)
    if decimals == 0:
        return f"{sign}€{_group(whole)}"
    return f"{sign}€{_group(whole)}.{frac:0{decimals}d}"


def price(ueur: int | None) -> str:
    """Unit price: 2 decimals above €100, 4 below (XRP, LINK...)."""
    if ueur is None:
        return "—"
    return eur(ueur, decimals=2 if abs(ueur) >= 100_000_000 else 4)


def pct(f: float | None, *, signed: bool = True, digits: int = 2) -> str:
    if f is None:
        return "—"
    v = round(f * 100, digits)
    sign = MINUS if v < 0 else ("+" if signed and v > 0 else "")
    return f"{sign}{abs(v):.{digits}f}%"


def num(f: float | None, digits: int = 2, *, signed: bool = False) -> str:
    if f is None:
        return "—"
    v = round(f, digits)
    sign = MINUS if v < 0 else ("+" if signed and v > 0 else "")
    return f"{sign}{abs(v):.{digits}f}"


def usd(uusd: int | None) -> str:
    if uusd is None:
        return "—"
    digits = 2 if uusd >= 1_000_000 else 4
    v = Decimal(uusd) / Decimal(1_000_000)
    return f"${v:,.{digits}f}"


def qty_fmt(q: int) -> str:
    d = (Decimal(q) / Decimal(100_000_000)).normalize()
    return format(d, "f")


def when(ts: int | None, *, year: bool = True) -> str:
    if ts is None:
        return "—"
    d = datetime.fromtimestamp(ts, UTC)
    year_part = f", {d.year}" if year else ""
    return f"{MONTHS[d.month - 1]} {d.day}{year_part}, {d:%H:%M} UTC"


def short_date(ts: int) -> str:
    """Short date: Nov 17."""
    d = datetime.fromtimestamp(ts, UTC)
    return f"{MONTHS[d.month - 1]} {d.day}"


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%MZ")


def stamp(ts: int | None, *, year: bool = True) -> str:
    """Readable date inside a <time> (machine-readable for screen readers and the freshness script)."""
    if ts is None:
        return "—"
    return f'<time datetime="{iso(ts)}">{e(when(ts, year=year))}</time>'


def tone(v: float | None) -> str:
    if v is None or v == 0:
        return ""
    return "gain" if v > 0 else "loss"


def duration(seconds: int) -> str:
    if seconds % 86400 == 0:
        return f"{seconds // 86400} d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600} h"
    return f"{seconds} s"


def bp_pct(bp: int | None) -> str:
    return "—" if bp is None else (f"{bp / 100:.2f}".rstrip("0").rstrip(".") + "%")


def trigger_txt(d: dict[str, Any] | None) -> str:
    """"BTC −3.4% in 1 h" (signed change measured on trades, over the trigger's window)."""
    if not d:
        return "wake-up"
    if d.get("type") == "move" and d.get("variation_bp") is not None:
        sym = str(d.get("symbol", "")).removesuffix("/EUR")
        return f"{sym} {pct(d['variation_bp'] / 10_000, digits=1)} in {duration(int(d.get('window_s') or 3600))}"
    return str(d.get("type") or "wake-up")


def hour(ts: int) -> str:
    d = datetime.fromtimestamp(ts, UTC)
    return f"{d:%H:%M} UTC"


def plural(n: int, word: str, words: str | None = None) -> str:
    return f"{_group(n)} {word if n <= 1 else (words or word + 's')}"


def json_inline(obj: Any) -> str:
    """JSON that is safe to place in <script type="application/json"> (no '<' remains)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def short_name(name: str) -> str:
    for pre in ("Claude ", "Benchmark ", "Council "):
        name = name.removeprefix(pre)
    name = name.replace(" (adapted)", "")
    return name[:1].upper() + name[1:]


NOT_APPLICABLE = '<span class="muted" aria-hidden="true">—</span><span class="visually-hidden">not applicable</span>'


# ---------------------------------------------------------------------------
# Shared template
# ---------------------------------------------------------------------------


SITE_HOST = "https://example.github.io"  # host of the public version (GitHub Pages)
SITE_NAME = "The AI Arena"
DESCRIPTION_SITE = (
    "Claude models trade play money on Kraken's real prices, in simulation, against strategies without AI: "
    "live ranking, every decision explained."
)


ALT_PREVIEW = {
    "preview.png": "The Arena, AIs that trade, simulated: three leagues, AI councils, solo AIs and Spot, each against a benchmark without AI.",
    "preview-councils.png": "Diagram of a council: nine Haiku advisers, the devil's advocate, then a Haiku or Opus president. Simulated.",
}


def nav_leagues(root: str, active: str, perp: dict[str, Any] | None) -> str:
    def cur(x: str) -> str:
        return ' aria-current="page"' if active == x else ""

    if not perp:
        return f'<a href="{root}index.html"{cur("index")}>Overview</a><a href="{root}method.html"{cur("method")}>Method</a>'
    return (
        (f'<a href="{root}councils.html"{cur("councils")}>Councils</a>' if perp.get("councils") else "")
        + f'<a href="{root}derivatives.html"{cur("derivatives")}>Solo AIs</a>'
        + f'<a href="{root}spot.html"{cur("spot")}>Spot</a>'
        + f'<a href="{root}method.html"{cur("method")}>Method</a>'
    )


def layout(
    *, title: str, body: str, root: str, active: str, data: dict[str, Any], scripts: str = "", league: str = "spot",
    direct: bool = False, path: str | None = None, desc: str | None = None, complete_title: str | None = None,
    image: str = "preview.png",
) -> str:
    """Shared template. `path` (relative to the site root, e.g. "councils.html") gives the canonical address and
    that of the share preview on the public version; `desc` is the page's meta description."""
    perp = data.get("perp")
    vm = data["venue_mode"]
    if vm == "paper":
        label = '<span class="simulated" title="Play money: no real funds are involved">SIMULATED<span class="simulated-sub"> · play money</span></span>'
        banner = ""
    else:
        label = ""
        banner = (
            f'<p class="banner real"><strong>{e(REAL_BANNER)}</strong>'
            f' <span class="venue">venue_mode: {e(vm)}</span></p>'
        )
    public = bool(data.get("public"))
    root_path = data.get("root_path") or "/"
    page_title = complete_title or f"{title} · {SITE_NAME}"
    desc = desc or (DESCRIPTION_SITE if perp else description(data))
    shared = ""
    if public and path is not None:
        url = f"{SITE_HOST}{root_path}{path}"
        image = f"{SITE_HOST}{root_path}assets/{image}"
        shared = f"""<link rel="canonical" href="{e(url)}">
<meta property="og:type" content="website">
<meta property="og:locale" content="en_US">
<meta property="og:site_name" content="{e(SITE_NAME)}">
<meta property="og:title" content="{e(page_title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url)}">
<meta property="og:image" content="{e(image)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{e(ALT_PREVIEW.get(image, ALT_PREVIEW["preview.png"]))}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(page_title)}">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{e(image)}">
"""
    robots = "index, follow" if public else "noindex, nofollow"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="robots" content="{robots}">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="{CSP_DIRECT if direct else CSP}">
<title>{e(page_title)}</title>
<meta name="description" content="{e(desc)}">
{shared}<link rel="icon" href="{root}assets/icon.svg" type="image/svg+xml">
<link rel="preload" href="{root}fonts/ibm-plex-sans-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{root}fonts/ibm-plex-sans-latin-600-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{root}vendor/uPlot.min.css">
<link rel="stylesheet" href="{root}assets/site.css">
</head>
<body>
<a class="skip-link" href="#content">Skip to content</a>
<header class="header">
  {banner}
  <div class="wrap header-top">
    <a class="badge" href="{root}index.html">The Arena<span class="badge-sub">· AIs that trade</span></a>
    {label}
    <nav class="nav" aria-label="Main pages">{nav_leagues(root, active, perp)}</nav>
  </div>
</header>
<main class="wrap" id="content" tabindex="-1">
{body}
</main>
<footer class="footer wrap">
  <p><strong>Simulation.</strong> {e(WARNING)}</p>
  <p>Updated {stamp(data["generated_ts"])} · <a href="{root}method.html">Method and verifiable journal</a></p>
</footer>
<script src="{root}assets/site.js"></script>
{scripts}
</body>
</html>
"""


def stack(table: str, labels: list[str]) -> str:
    """Add data-label to the <td> cells of each row (in column order after the row header): below 640 px, the
    style sheet stacks each row into a "label: value" card instead of cutting the table off."""
    import re

    def cell(m: re.Match[str], i: Any) -> str:
        # Empty = nothing visible to read ("—", hidden "not applicable"); "accepted" or "rejected" stay displayed.
        visible = re.sub(r'<span class="visually-hidden">.*?</span>', "", m.group(2), flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", "", visible)
        empty = "" if re.search(r"\w", text) else ' data-empty=""'
        return f'<td data-label="{e(next(i, ""))}"{empty}{m.group(1)}>{m.group(2)}</td>'

    def line(m: re.Match[str]) -> str:
        i = iter(labels)
        return re.sub(r"<td((?: [^>]*)?)>(.*?)</td>", lambda c: cell(c, i), m.group(0), flags=re.DOTALL)

    return re.sub(r"<tr(?![^>]*group)[^>]*>.*?</tr>", line, table, flags=re.DOTALL)


DASHES = [[6, 4], [2, 3], [10, 3, 2, 3], [1, 3]]
LLM_COLOR = {"llm:claude-haiku-5-5": 0, "llm:claude-sonnet-5-5": 1, "llm:claude-opus-5-5": 2, "llm:claude-fable-5-2": 3}
N_LLM_COLORS = 4
BENCHMARK_COLOR = {"benchmark:6040": 0, "benchmark:e0065": 1, "benchmark:random": 2, "benchmark-perp:trend": 0, "benchmark-perp:random": 2}
REFERENCES = {"benchmark:basket", "benchmark-perp:basket-1x"}  # the "buy and hold" of each league
# The Trend Council's "engine alone" benchmark: as long as the council does not brake, the two curves are identical.
# It is drawn as a wide, translucent ribbon under the council so that both stay visible when they overlap.
HALOS = {"benchmark-perp:trend-engine"}
HALO_WIDTH = 9
ARCHIVE_DASH = [1, 6]  # fine, widely spaced dots: not mistaken for the benchmarks' dashes
MIN_CURVE_POINTS = 3  # under 3 finished cycles a curve is only a straight line: the table is enough


def last_value(values: list[float | None]) -> float | None:
    """Last published value of a curve (an archived council's stops before the end of the axis)."""
    return next((v for v in reversed(values) if v is not None), None)


def _styles(chart: dict[str, Any], focus: str | None) -> list[dict[str, Any]]:
    """Style of each curve, single source for the chart (chart.js) and the legend rendered here."""
    out, llm, n_bench = [], 0, 0
    for s in chart["series"]:
        focused = focus is not None and s["id"] == focus
        if s["kind"] == "council":  # one tint per council: Haiku magenta, Opus gold
            st = {"color": "--council2" if s["id"].endswith(":opus") else "--council", "dash": None, "width": 2.5}
        elif s["kind"] == "robot":  # the wick hunter: its own tint; its 5-minute-cadence control, the same one dashed
            st = {"color": "--hunter", "dash": [6, 4] if s["id"].endswith("-5min") else None, "width": 2 if s["id"].endswith("-5min") else 2.5}
        elif s["kind"] == "llm":
            k = LLM_COLOR.get(s["id"].replace("llm-perp:", "llm:"), llm)
            st = {"color": f"--llm{k % N_LLM_COLORS}", "dash": None, "width": 2.5}
            llm += 1
        elif s["id"] in REFERENCES:
            st = {"color": "--bench-ref", "dash": [8, 4], "width": 2}
        elif s["id"] in HALOS:
            st = {"color": "--engine", "dash": None, "width": HALO_WIDTH, "halo": True}
        else:
            k = BENCHMARK_COLOR.get(s["id"], n_bench)
            st = {"color": f"--bench{k % 3}", "dash": DASHES[(k + 1) % len(DASHES)], "width": 1.75}
            n_bench += 1
        if focused and not st.get("halo"):
            st["width"], st["dash"] = 3, None
            if s["kind"] not in ("llm", "council", "robot"):
                st["color"] = "--accent"
        if s.get("archive_ts"):  # an archived council: its data is frozen, its curve is finely dotted
            st["dash"], st["archive"] = ARCHIVE_DASH, True
            st["width"] = 2.5 if focused else 2
        st["visible"] = focus is None or focused or s["id"] in REFERENCES
        out.append(st)
    return out


def _legend(chart: dict[str, Any], focus: str | None) -> str:
    """Legend rendered server-side (values of the latest cycle): readable without JavaScript and without layout shift.
    The buttons are disabled until the chart script has taken them over."""
    items = []
    for i, (s, st) in enumerate(zip(chart["series"], _styles(chart, focus), strict=True)):
        if not st["visible"]:
            continue
        v = last_value(s["values"])
        ret = None if v is None else round(v - 100, 2) / 100
        archive_tag = (
            f'<span class="legend-tag">withdrawn on {short_date(s["archive_ts"])}</span>' if s.get("archive_ts") else ""
        )
        dash = f' stroke-dasharray="{" ".join(f"{x * 0.7:g}" for x in st["dash"])}"' if st["dash"] else ""
        stroke_svg = (
            '<svg class="legend-stroke" viewBox="0 0 24 8" width="24" height="8" aria-hidden="true">'
            f'<line class="stroke stroke{st["color"]}" x1="1" x2="23" y1="4" y2="4" stroke-width="{7 if st.get("halo") else min(st["width"], 3):g}" stroke-linecap="round"{dash}/></svg>'
        )
        items.append(
            f'<li><button type="button" class="legend-button" data-series="{i}" aria-pressed="true" disabled>{stroke_svg}'
            f'<span class="legend-name">{e(s["name"])}{archive_tag}</span><span class="legend-val {tone(ret)}">{pct(ret)}</span></button></li>'
        )
    live = (chart.get("kinds") or [""])[-1] == "watch"
    when_txt = f"{'Live' if live else 'Latest cycle'}: {when(chart['x'][-1], year=False)}"
    return f'<p class="legend-when" id="legend-when">{e(when_txt)}</p><ul class="legend" id="legend" aria-label="Curves shown">{"".join(items)}</ul>'


def _chart_scripts(root: str, chart: dict[str, Any], focus: str | None, *, last: str | None = None) -> str:
    """`last`: label of the last snapshot in the legend ("Live" by default)."""
    payload = {
        "x": chart["x"], "kinds": chart.get("kinds") or [], "series": chart["series"], "styles": _styles(chart, focus),
        "short": [short_name(s["name"]) for s in chart["series"]],
    }
    if last:
        payload["last"] = last
    return (
        f'<script id="equity-data" type="application/json">{json_inline(payload)}</script>\n'
        f'<script src="{root}vendor/uPlot.iife.min.js"></script>\n'
        f'<script src="{root}assets/chart.js"></script>'
    )


def _n_curve_cycles(chart: dict[str, Any]) -> int:
    """Finished cycles on the curve (the previous day's snapshots and the starting point do not count)."""
    kinds = chart.get("kinds")
    return sum(1 for k in kinds if k == "cycle") if kinds else len(chart["x"]) - 1


def _curve_visible(chart: dict[str, Any]) -> bool:
    return _n_curve_cycles(chart) >= MIN_CURVE_POINTS


def _chart_block(chart: dict[str, Any], *, focus_name: str | None = None, focus: str | None = None) -> str:
    n = _n_curve_cycles(chart)
    if n < MIN_CURVE_POINTS:
        done = "none has finished" if n <= 0 else f"{plural(n, 'cycle')} finished so far"
        return (
            f'<p class="empty empty-short">Chart from {MIN_CURVE_POINTS} cycles ({done}). '
            "Current returns are in the table.</p>"
        )
    period = f"from {when(chart['x'][1])} to {when(chart['x'][-1])}"
    end = "Live values" if (chart.get("kinds") or [""])[-1] == "watch" else "At the latest cycle"
    last_items = "; ".join(
        f"{s['name']}{' (archived)' if s.get('archive_ts') else ''} {pct((last_value(s['values']) - 100) / 100) if last_value(s['values']) is not None else '—'}"
        for s in chart["series"]
    )
    if focus_name and len(chart["series"]) == 1:
        label = f"Cumulative net return of {focus_name}, the benchmark, {period}. {end}: {last_items}."
    elif focus_name:
        label = f"Cumulative net return of {focus_name}, compared with the basket benchmark, {period}. {end}: {last_items}."
    else:
        label = f"Cumulative net return of the {len(chart['series'])} portfolios, {period}. {end}: {last_items}."
    return (
        '<figure class="chart-panel">'
        f'<div id="chart" class="chart-area" role="img" aria-label="{e(label)}">'
        '<noscript><p class="empty">Chart: JavaScript required. Values are in the table.</p></noscript></div>'
        f"{_legend(chart, focus)}"
        "</figure>"
    )


def _svg_bar(v: float | None, vmax: float) -> str:
    """Diverging bar around zero (decorative: the value is written next to it)."""
    axis = '<rect class="bar-axis" x="49.5" y="0" width="1" height="8"/>'
    if v is None or vmax <= 0 or v == 0:
        return f'<svg class="bar" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true">{axis}</svg>'
    w = min(abs(v) / vmax, 1.0) * 48
    x = 50 if v > 0 else 50 - w
    return (
        '<svg class="bar" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true">'
        f'<rect class="bar-{tone(v)}" x="{x:.2f}" y="1" width="{w:.2f}" height="6" rx="1"/>{axis}</svg>'
    )


def _svg_gauge(ratio: float) -> str:
    w = max(0.0, min(ratio, 1.0)) * 100
    return (
        '<svg class="gauge" viewBox="0 0 100 6" preserveAspectRatio="none" aria-hidden="true">'
        f'<rect class="gauge-track" width="100" height="6" rx="3"/><rect class="gauge-fill" width="{w:.2f}" height="6" rx="3"/></svg>'
    )


# ---------------------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------------------


def never_decides(p: dict[str, Any]) -> bool:
    """AI model from which no valid answer has ever been received (skipped decisions or invalid answers)."""
    return p["kind"] == "llm" and not p.get("n_decided")


def _skip_reason_label(p: dict[str, Any]) -> str | None:
    if not p["skipped"]:
        return None
    code = max(p["skipped"].items(), key=lambda kv: kv[1])[0]
    return SKIP_REASONS.get(code, code)


def _luck_verdict(p: dict[str, Any], min_cycles: int) -> str:
    """Status badge of a row; empty when the first screen already says it all (too early for everyone)."""
    d = p["distinguishable"]
    if p["id"] == "benchmark:basket":
        return '<span class="pill neutral">reference</span>'
    if never_decides(p):
        return '<span class="pill warn">has never decided</span>'
    if p["n_cycles"] < min_cycles:
        return ""
    if d and d["significant"]:
        side = "above" if d["mean_diff"] > 0 else "below"
        return f'<span class="pill info">significant gap ({side} the basket)</span>'
    return '<span class="pill neutral">not distinguishable from chance</span>'


def _sharpe_cell(p: dict[str, Any], min_cycles: int) -> str:
    if p["sharpe"] is None or p["sharpe_ci"] is None:
        return f'<span class="muted">too early</span><small class="sub">from {min_cycles} cycles</small>'
    lo, hi = p["sharpe_ci"]
    return f'{num(p["sharpe"])}<small class="sub">95% CI [{num(lo, 1)}, {num(hi, 1)}]</small>'


def _rank_cell(p: dict[str, Any]) -> str:
    r = p["rank_percentile"]
    if never_decides(p):
        return '<span class="muted">—</span><small class="sub">no decision</small>'
    if r is None and p.get("late"):
        return '<span class="muted">—</span><small class="sub">joined mid-way</small>'
    if r is None:
        return NOT_APPLICABLE
    no_purchase_note = '<small class="sub">no purchase at all</small>' if p["kind"] == "llm" and not p["n_trades"] else ""
    return f"{num(r, 0)}{no_purchase_note}"


def _cost_cell(p: dict[str, Any]) -> str:
    if p["api_cost_uusd"] is None:
        return NOT_APPLICABLE
    if never_decides(p):
        return '<span class="muted">—</span><small class="sub">no call</small>'
    return usd(p["api_cost_uusd"])


def _drawdown(p: dict[str, Any]) -> str:
    return pct(-p["max_drawdown"], signed=False) if p["max_drawdown"] else pct(0.0, signed=False)


def _cost_title(data: dict[str, Any]) -> str:
    if data.get("decider_backend") == "subscription":
        return 'AI cost <span class="count">API equivalent</span>'
    return "API cost"


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


def overview_table(data: dict[str, Any]) -> str:
    min_cycles = data["min_cycles_stats"]
    all_total = all(p["sharpe"] is None for p in data["portfolios"])
    vmax = max((abs(p["total_return"] or 0.0) for p in data["portfolios"]), default=0.0)
    rows = []
    for p in data["portfolios"]:
        status = ""
        if p.get("archive"):
            status = f' <span class="pill neutral">archived on {short_date(p["archive"]["ts"])}</span>'
        elif p["halted"]:
            status = ' <span class="pill loss-bg">halted</span>'
        elif p["frozen_until_ts"]:
            status = ' <span class="pill warn">frozen</span>'
        verdict = _luck_verdict(p, min_cycles)
        verdict_html = f'<span class="verdict-line">{verdict}</span>' if verdict else ""
        if p.get("late") and p.get("start_ts"):
            verdict_html += f'<small class="desc">since {stamp(p["start_ts"], year=False)}</small>'
        inactive = " inactive" if never_decides(p) and not p.get("archive") else ""
        archive_cls = " archive" if p.get("archive") else ""
        rows.append(
            f'<tr class="{e(p["kind"])}{inactive}{archive_cls}"><th scope="row"><a href="model/{e(p["slug"])}.html">{e(p["name"])}</a>{status}{verdict_html}</th>'
            f'<td class="n key"><span class="{tone(p["total_return"])}">{pct(p["total_return"])}</span>{_svg_bar(p["total_return"], vmax)}</td>'
            f'<td class="n">{_rank_cell(p)}</td>'
            f'<td class="n">{eur(p["equity_ueur"])}</td>'
            f'<td class="n">{_drawdown(p)}</td>'
            f'<td class="n">{p["n_trades"]}</td>'
            f'<td class="n">{_cost_cell(p)}</td>'
            + ("" if all_total else f'<td class="n">{_sharpe_cell(p, min_cycles)}</td>')
            + "</tr>"
        )

    def group(llm: bool, title: str) -> str:
        wanted = [(r, p) for r, p in zip(rows, data["portfolios"], strict=True) if (p["kind"] == "llm") == llm]
        lines = [r for r, _p in sorted(wanted, key=lambda rp: bool(rp[1].get("archive")))]  # archived after the active ones
        if not lines:
            return ""
        return f'<tbody><tr class="group"><th scope="rowgroup" colspan="{8 - all_total}">{title}</th></tr>{"".join(lines)}</tbody>'

    head = (
        '<tr><th scope="col">Portfolio</th><th scope="col" class="n">Net return</th>'
        '<th scope="col" class="n">Rank <span class="count">/100 vs chance</span></th><th scope="col" class="n">Value</th>'
        '<th scope="col" class="n">Max drawdown</th><th scope="col" class="n">Orders</th>'
        f'<th scope="col" class="n">{_cost_title(data)}</th>'
        + ("" if all_total else '<th scope="col" class="n">Sharpe</th>')
        + "</tr>"
    )
    labels = ["Net return", "Rank /100 vs chance", "Value", "Max drawdown", "Orders", "AI cost"] + ([] if all_total else ["Sharpe"])
    return stack(
        '<div class="table-scroll" tabindex="0" role="region" aria-label="Comparison table, scrollable">'
        '<table class="table comparison stacked"><caption class="visually-hidden">Portfolio comparison: '
        f'AI models then benchmarks</caption><thead>{head}</thead>'
        f'{group(True, "AI models")}{group(False, "Benchmarks")}</table></div>',
        labels,
    )


NUMBERS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six"}


def _verdict(data: dict[str, Any]) -> str:
    """Verdict of the moment, in everyday words."""
    if not data["n_cycles"]:
        return "The first cycle has not happened yet."
    if data["any_llm_distinguishable"]:
        return "At least one model differs significantly from the basket."
    if data["n_cycles"] < data["min_cycles_stats"]:
        return "Too early to conclude."
    return "No model is distinguishable from chance."


def _advanced(data: dict[str, Any], verdict: str = "") -> str:
    n_cycles, min_cycles, interval_s = data["n_cycles"], data["min_cycles_stats"], data.get("interval_s")
    head = f"<strong>{e(verdict)}</strong>" if verdict else ""
    if n_cycles >= min_cycles:
        return f'<p class="advanced">{head}{_svg_gauge(1.0)}<span>{n_cycles} cycles</span></p>'
    toward = ""
    if data["last_cycle_ts"] and interval_s:
        d = datetime.fromtimestamp(data["last_cycle_ts"] + (min_cycles - n_cycles) * interval_s, UTC)
        toward = f", verdict around {MONTHS[d.month - 1]} {d.day}"
    return (
        f'<p class="advanced">{head}{_svg_gauge(n_cycles / min_cycles if min_cycles else 1.0)}'
        f"<span>Cycle {n_cycles} of {min_cycles}{toward}</span></p>"
    )


def _statement(data: dict[str, Any]) -> str:
    """Status line: latest cycle, next one (refreshed by site.js), journal state."""
    items = []
    last, interval_s = data["last_cycle_ts"], data.get("interval_s")
    if last:
        items.append(f"<li>Latest cycle {stamp(last, year=False)}</li>")
    if last and interval_s:
        nxt = last + interval_s
        items.append(
            f'<li>Next cycle <time datetime="{iso(nxt)}" data-next="{nxt}" data-interval="{interval_s}">{e(when(nxt, year=False))}</time>'
            ' <span class="statement-detail" data-freshness></span></li>'
        )
    live = data.get("live")
    if live:
        freeze = " · season frozen, no orders" if live.get("freeze") else ""
        if _live_fresh(data):
            items.append(f'<li>Live values <time datetime="{iso(live["ts"])}">{hour(live["ts"])}</time>{freeze}</li>')
        else:
            items.append(f'<li class="warn-txt">Latest values {stamp(live["ts"], year=False)}{freeze}</li>')
    last_wakeup = next((r for r in data.get("wakeups") or [] if r["status"] != "abandoned"), None)
    if last_wakeup:
        items.append(f'<li>Latest wake-up {stamp(last_wakeup["wakeup"], year=False)} · {e(trigger_txt(last_wakeup["trigger"]))}</li>')
    j = data["journal"]
    if j["verify_ok"]:
        items.append('<li><a href="method.html#m-journal">Journal verified</a></li>')
    else:
        items.append('<li class="loss-txt"><a href="method.html#m-journal">Journal: verification failed</a></li>')
    return f'<ul class="statement">{"".join(items)}</ul>'


LIVE_FRESH_S = 1_800  # beyond 30 min without a snapshot, the values are no longer called "live"


def _live_fresh(data: dict[str, Any]) -> bool:
    live = data.get("live")
    return bool(live) and data["generated_ts"] - live["ts"] <= LIVE_FRESH_S


# Free-text reason of a waiver: published as is only if nothing in it looks like a path, an address, a token
# or a machine name (otherwise the publishing script would block the whole publication, or worse).
_SUSPECT_REASON = re.compile(r"[/\\~@]|sk-|gh[pousr]_|the host|\b\d{1,3}(?:\.\d{1,3}){3}\b|claude code|claude -p", re.IGNORECASE)


def waiver_reason(data: dict[str, Any], reason: str) -> str:
    if data.get("public") and (_SUSPECT_REASON.search(reason) or len(reason) > 300):
        return "reason recorded in the journal"
    return reason


def _season_head(data: dict[str, Any]) -> str:
    """Season line (planned, open, finished) and waivers, at the top of the home page."""
    season_info = data.get("season")
    if not season_info:
        return ""
    season_name = e(season_info["name"])
    if season_info["status"] == "planned":
        return (
            f'<p class="season"><strong>{season_name}</strong> starting {stamp(season_info["start_ts"], year=False)}'
            " · burn-in under way, not ranked</p>"
        )
    if season_info["status"] == "finished":
        head = f'<p class="season"><strong>{season_name}</strong> ended {stamp(season_info["cycle_end"], year=False)}</p>'
    elif season_info["status"] == "without_reference":
        head = f'<p class="season"><strong>{season_name}</strong> · reference missing from the journal, ranking from the initial capital</p>'
    else:
        head = f'<p class="season"><strong>{season_name}</strong> · day {season_info["day"]} of {season_info["duration_days"]}</p>'
    for d in season_info.get("waivers") or []:
        head += f'<p class="alert warn">Season changed on {stamp(d["ts"], year=False)} (waiver): {e(waiver_reason(data, d["reason"]))}</p>'
    return head


def _burn_in(data: dict[str, Any]) -> str:
    """The burn-in before the season, shown apart and collapsed: it does not count in the ranking."""
    burn_in = data.get("burn_in")
    if not burn_in or not burn_in["portfolios"]:
        return ""
    period = f"from {when(burn_in['start_ts'], year=False)} to {when(burn_in['end_ts'], year=False)}, " if burn_in["start_ts"] else ""
    rows = "".join(
        f'<tr><th scope="row">{e(r["name"])}</th><td class="n {tone(r["total_return"])}">{pct(r["total_return"])}</td></tr>'
        for r in burn_in["portfolios"]
    )
    return (
        f'<details class="reading burn-in"><summary>Burn-in, not ranked <span class="h-note">{e(period)}'
        f'{plural(burn_in["n_cycles"], "cycle")}</span></summary>'
        '<table class="table burn-in-table"><caption class="visually-hidden">Net return during the burn-in</caption>'
        '<thead><tr><th scope="col">Portfolio</th><th scope="col" class="n">Net return</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></details>"
    )


def _to_do(data: dict[str, Any], llms: list[dict[str, Any]]) -> str:
    """A line for the operator: what to do now, or "nothing". Absent from the public version."""
    if data.get("public"):
        return ""
    if not data["n_cycles"]:
        return '<p class="to-do info"><strong>Nothing to do.</strong> The first cycle has not happened yet.</p>'
    skip_reasons = {p["name"]: r for p in llms if (r := _last_skip_reason(p))}
    halted = [p["name"] for p in data["portfolios"] if p["halted"]]
    if skip_reasons:
        reasons = sorted(set(skip_reasons.values()))
        who = f"the {len(llms)} models" if len(skip_reasons) == len(llms) > 1 else ", ".join(sorted(skip_reasons))
        if reasons == ["no_key"] and data.get("decider_backend") == "subscription":
            nxt = data["last_cycle_ts"] + data["interval_s"] if data.get("interval_s") else None
            after = f"after the cycle of {when(nxt, year=False)}" if nxt else "after the next cycle"
            return (
                f'<p class="to-do info"><strong>Nothing to do now.</strong> Come back {e(after)}: '
                "the configuration now uses the subscription, so the models should have decided by then. "
                "Otherwise, see <code>docs/RUNBOOK.md</code>.</p>"
            )
        if reasons == ["no_key"]:
            return (
                '<p class="to-do warn"><strong>To do.</strong> '
                f"{e(who[0].upper() + who[1:])} {'are' if len(skip_reasons) > 1 else 'is'} not playing for lack of an API key: put the key in "
                "<code>~/.config/arena/secrets/anthropic_api_key</code> (see <code>docs/RUNBOOK.md</code>).</p>"
            )
        labels = ", ".join(e(SKIP_REASONS.get(r, r)) for r in reasons)
        return (
            f'<p class="to-do warn"><strong>To check.</strong> At the latest cycle, {e(who)}: decision skipped ({labels}). '
            "See <code>docs/RUNBOOK.md</code>.</p>"
        )
    if halted:
        return f'<p class="to-do warn"><strong>To check.</strong> Portfolio halted: {e(", ".join(halted))}.</p>'
    return ""


def _last_skip_reason(p: dict[str, Any]) -> str | None:
    """Reason for the skip at the latest journaled cycle, or None if the latest decision was not skipped."""
    d = p["decisions"][0] if p["decisions"] else None
    return d["skip_reason"] if d and d["kind"] == "skipped" else None


def _archives(archives: list[dict[str, Any]]) -> str:
    """Models withdrawn from the league: their data stays, their curve is dotted and stops at the withdrawal."""
    if not archives:
        return ""
    names = ", ".join(f"{p['name']} (on {short_date(p['archive']['ts'])})" for p in archives)
    return (
        '<p class="arrival">Dotted curves: archived models, withdrawn from the league with their positions sold. '
        f"Their return is frozen at the withdrawal: {e(names)}.</p>"
    )


def index_page(data: dict[str, Any]) -> str:
    n_cycles, min_cycles = data["n_cycles"], data["min_cycles_stats"]
    llms = [p for p in data["portfolios"] if p["kind"] == "llm" and not p.get("archive")]  # archived ones no longer play
    verdict = _verdict(data)
    m = data["method"]
    distribution = data["distribution"]
    reader = [
        (
            f"<li><strong>Net return</strong>: after fees ({bp_pct(m['taker_fee_bp'])}) and slippage ({bp_pct(m['slippage_bp'])}), before tax.</li>"
        ),
        f"<li><strong>Sharpe</strong>: return per unit of risk, annualized, from {min_cycles} cycles.</li>",
        "<li>A model that bought nothing beats chance because chance pays fees, not because of skill.</li>",
    ]
    if distribution:
        reader.insert(1,
            f"<li><strong>Rank /100</strong>: percentile among {_group(distribution['n'])} random trajectories on the same prices "
            f"(median {pct(distribution['median'])}). 50 = same as chance.</li>"
        )  # fmt: skip
    elif data["distribution_note"]:
        reader.insert(1, f"<li><strong>Rank vs chance</strong>: {e(data['distribution_note'])}.</li>")
    since = "since the start of the season, " if data.get("burn_in") else ""
    from arena.site import home as A

    n_llm = len(llms)
    capital = eur(m["capital_ueur"], decimals=0)
    title = (
        f"{NUMBERS_MIN.get(n_llm, str(n_llm)).capitalize()} Claude AIs buy and sell crypto with {capital} of play money each, without leverage."
        if n_llm > 1 else f"A Claude AI buys and sells crypto with {capital} of play money."
    )
    lead = (
        "They decide every 4 h on Kraken's real prices, fees included, without being able to bet on a decline. "
        "Fixed rules without AI serve as benchmarks, including the basket that is bought and held."
    )
    archives = [p for p in data["portfolios"] if p.get("archive")]
    if archives:
        arch_names = ", ".join(short_name(p["name"]).replace("Claude ", "") for p in archives)
        several = len(archives) > 1
        lead += (
            f" {e(arch_names)}, archived, {'no longer play' if several else 'no longer plays'}: "
            f"{'their curves remain' if several else 'its curve remains'} dotted."
        )
    state = f"""{_season_head(data)}
  {_advanced(data, verdict) if n_cycles else f'<p class="advanced"><strong>{e(verdict)}</strong></p>'}
  {_statement(data)}
  {_to_do(data, llms)}"""
    body = A.front_section(
        title=title, lead=lead,
        ranking=A.scores(A._spot_rows(data), label="Spot league ranking, net return") + f'<div class="status status-front">{state}</div>',
        curve=_chart_block(data["chart"]) + _archives(archives),
    ) + f"""
<section aria-labelledby="title-comparison">
  <h2 id="title-comparison">All portfolios <span class="h-note">{since}fees included</span></h2>
  {overview_table(data)}
  <details class="reading"><summary>How to read this table</summary><ul class="list-simple">{"".join(reader)}</ul></details>
  {_burn_in(data)}
</section>
"""
    return layout(
        title="Spot league" if data.get("perp") else "Overview", body=body, root="",
        active="spot" if data.get("perp") else "index", data=data, path="spot.html" if data.get("perp") else "",
        complete_title="Spot league: Claude AIs buy crypto with play money",
        desc=description(data),
        scripts=_chart_scripts("", data["chart"], None) if _curve_visible(data["chart"]) else "",
    )  # fmt: skip


def page_404(data: dict[str, Any], root_path: str) -> str:
    """Error page: served at any depth, hence the absolute site root."""
    body = """
<section aria-labelledby="title-404">
  <h1 id="title-404">This page does not exist</h1>
  <p class="lead">The address may be mistyped, or the page was renamed. The journal has lost nothing.</p>
  <p class="actions-404"><a class="button" href="{r}index.html">Back to the home page</a> <a href="{r}method.html">Read the method</a></p>
</section>
""".replace("{r}", e(root_path))
    return layout(title="Page not found", body=body, root=root_path, active="", data=data, league="perp")


# ---------------------------------------------------------------------------
# Model page
# ---------------------------------------------------------------------------


def _stat(label: str, value: str, extra: str = "", cls: str = "", card: str = "") -> str:
    return f'<div class="stat {card}"><dt>{label}</dt><dd class="{cls}">{value}{extra}</dd></div>'


def _positions(p: dict[str, Any]) -> str:
    if not p["positions"]:
        return f'<p class="empty">All in cash ({eur(p["cash_ueur"])}).</p>'
    with_stop = any(x["stop_ueur"] for x in p["positions"])
    rows = "".join(
        f'<tr><th scope="row">{e(x["symbol"])}</th><td class="n">{e(qty_fmt(x["qty"]))}</td>'
        f'<td class="n">{eur(x["cost_ueur"])}</td><td class="n">{eur(x["value_ueur"])}</td>'
        f'<td class="n {tone(x["unrealized_ueur"])}">{eur(x["unrealized_ueur"], signed=True)}</td>'
        + (f'<td class="n">{price(x["stop_ueur"]) if x["stop_ueur"] else "—"}</td>' if with_stop else "")
        + f'<td>{stamp(x["opened_ts"])}</td></tr>'
        for x in p["positions"]
    )
    total_cost = sum(x["cost_ueur"] for x in p["positions"])
    vals = [x["value_ueur"] for x in p["positions"]]
    total_value = None if any(v is None for v in vals) else sum(vals)
    total_unrealized = None if total_value is None else total_value - total_cost
    empty = "<td></td>" if with_stop else ""
    footer = (
        f'<tfoot><tr><th scope="row">Total positions</th><td></td><td class="n">{eur(total_cost)}</td><td class="n">{eur(total_value)}</td>'
        f'<td class="n {tone(total_unrealized)}">{eur(total_unrealized, signed=True)}</td>{empty}<td></td></tr>'
        f'<tr><th scope="row">Cash</th><td></td><td></td><td class="n">{eur(p["cash_ueur"])}</td><td></td>{empty}<td></td></tr></tfoot>'
    )
    stop_th = '<th scope="col" class="n">Stop</th>' if with_stop else ""
    labels = ["Quantity", "Cost, fees included", "Value at last bid", "Unrealized"] + (["Stop"] if with_stop else []) + ["Opened on"]
    return stack(
        '<div class="table-scroll" tabindex="0" role="region" aria-label="Positions table, scrollable"><table class="table stacked">'
        '<caption class="visually-hidden">Current positions, valued at the last bid price</caption>'
        '<thead><tr><th scope="col">Pair</th><th scope="col" class="n">Quantity</th><th scope="col" class="n">Cost <span class="count">fees included</span></th>'
        '<th scope="col" class="n">Value <span class="count">at last bid</span></th><th scope="col" class="n">Unrealized</th>'
        f'{stop_th}<th scope="col">Opened on</th></tr></thead><tbody>{rows}</tbody>{footer}</table></div>',
        labels,
    )


def _codes(reasons: list[str]) -> str:
    return "".join(
        f'<span class="code">{e(RISK_CODES.get(c, "unknown rule"))} <code>{e(c)}</code></span>' for c in reasons
    )


def _reason(reason: str) -> str:
    return {"intent": "order", "stop": "stop hit", "max_holding": "maximum holding", "kill_switch": "circuit breaker", "retired": "archived, positions sold"}.get(
        reason, reason
    )


def _execution(fills: list[dict[str, Any]]) -> str:
    if not fills:
        return '<span class="muted">not executed</span>'
    return "".join(
        f'<span class="exec">{e(qty_fmt(f["qty"]))} at {price(f["price_ueur"])}'
        f'<small class="sub">fees {eur(f["fee_ueur"], decimals=4)}</small></span>'
        for f in fills
    )


def _intent(a: dict[str, Any]) -> str:
    if a["side"] == "buy":
        parts = [f'<strong>Buy</strong> · {bp_pct(a["size_bp"])} of the portfolio']
        if a.get("stop_bp") is not None:
            parts.append(f'stop {bp_pct(a["stop_bp"])} below entry')
        if a.get("expected_move_bp") is not None:
            parts.append(f'expected rise {bp_pct(a["expected_move_bp"])}')
        return " · ".join(parts)
    return f'<strong>Sell</strong> · {bp_pct(a["size_bp"])} of the position'


def _risk_verdict(a: dict[str, Any]) -> str:
    if a["approved"] is None:
        return '<span class="pill neutral">no verdict</span>'
    if a["approved"]:
        return '<span class="pill ok">accepted</span>'
    return f'<span class="pill loss-bg">rejected</span><span class="codes">{_codes(a["reasons"])}</span>'


def _actions_table(actions: list[dict[str, Any]], cycle: int) -> str:
    rows = "".join(
        f'<tr><th scope="row">{e(a["symbol"])}</th><td>{_intent(a)}</td><td>{_risk_verdict(a)}</td>'
        f'<td class="n">{_execution(a["fills"])}</td></tr>'
        for a in actions
    )
    return stack(
        f'<div class="table-scroll actions-scroll" tabindex="0" role="region" aria-label="Actions of the cycle of {e(when(cycle))}, scrollable">'
        '<table class="table actions stacked"><thead><tr><th scope="col">Pair</th>'
        '<th scope="col">Intent</th><th scope="col">Risk check</th><th scope="col" class="n">Execution</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div>',
        ["Intent", "Risk check", "Execution"],
    )


def _outputs(fills: list[dict[str, Any]]) -> str:
    if not fills:
        return ""
    items = "".join(
        f'<li><strong>Forced exit</strong> ({e(_reason(f["reason"]))}): sale of {e(qty_fmt(f["qty"]))} {e(f["symbol"])} '
        f'at {price(f["price_ueur"])}, fees {eur(f["fee_ueur"], decimals=4)} <span class="muted">· {stamp(f["ts"], year=False)}</span></li>'
        for f in fills
    )
    return f'<ul class="outputs">{items}</ul>'


def _rationale(d: dict[str, Any]) -> str:
    if not d.get("has_justification"):
        return ""
    return f'<blockquote class="rationale"><span class="label">Model reasoning</span>{e(d["justification"])}</blockquote>'


def _meta(d: dict[str, Any]) -> str:
    meta = []
    if d.get("cost_uusd"):
        meta.append(usd(d["cost_uusd"]))
    return f'<span class="decision-meta">{" · ".join(meta)}</span>' if meta else ""


def _decision_compact(d: dict[str, Any]) -> str | None:
    """Row of a decision with no action or exit (the most frequent); None if it deserves a full card."""
    if d["actions"] or d["outputs"]:
        return None
    if d["kind"] == "skipped":
        reason = SKIP_REASONS.get(d["skip_reason"], d["skip_reason"])
        return (
            f'<li class="line"><span class="when">{stamp(d["cycle"])}</span>'
            f'{_llm_round(d)}<span class="pill warn">skipped</span> <span class="muted">{e(reason)}</span></li>'
        )
    round_badge = _llm_round(d)
    if d["kind"] == "benchmark":
        return (
            f'<li class="line"><span class="when">{stamp(d["cycle"])}</span>{round_badge}'
            '<span class="muted">Rule applied: no order</span></li>'
        )
    if d["kind"] != "decided":
        return None
    body = _rationale(d)
    summary = f'<span class="when">{stamp(d["cycle"])}</span>{round_badge}<span class="muted">No order</span>{_meta(d)}'
    if not body:
        return f'<li class="line">{summary}</li>'
    return f'<li class="line"><details><summary>{summary}</summary>{body}</details></li>'


def _decision_html(d: dict[str, Any]) -> str:
    compact = _decision_compact(d)
    if compact is not None:
        return compact
    if d["kind"] == "skipped":
        head = f'<span class="pill warn">skipped</span> <span>{e(SKIP_REASONS.get(d["skip_reason"], d["skip_reason"]))}</span>'
    elif d["kind"] == "parse_error":
        head = f'<span class="pill warn">invalid answer</span> <span>{e(d["parse_error"])}</span>'
    elif d["kind"] == "benchmark":
        head = '<span class="pill neutral">mechanical rule</span>'
    elif d["kind"] == "stop_watch":
        head = '<span class="pill warn">stop</span> <span>Sale on stop, detected by the watch</span>'
    else:
        head = ""
    head = _llm_round(d) + head
    actions = _actions_table(d["actions"], d["cycle"]) if d["actions"] else ""
    if d["kind"] == "decided" and not d["actions"]:
        actions = '<p class="muted">No action this cycle.</p>'
    if d["actions"]:
        head = f"{head}<span class=\"summary-orders\">{e(_orders_summary(d['actions']))}</span>"
    rationale = _rationale(d)
    orders = f"{actions}{_outputs(d['outputs'])}"
    body = (
        f'<div class="decision-body">{rationale}<div class="decision-orders">{orders}</div></div>'
        if rationale and d["actions"] else f"{orders}{rationale}"
    )
    return (
        f'<li class="decision"><article><header><h3>{stamp(d["cycle"])}</h3>{head}{_meta(d)}</header>'
        f"{body}</article></li>"
    )


def _llm_round(d: dict[str, Any]) -> str:
    """Badge "wake-up · BTC −3.4% in 1 h" of a decision taken outside the 4 h appointment."""
    if d.get("llm_round") != "wakeup":
        return ""
    status = {"abandoned": " (abandoned)", "in_progress": " (in progress)"}.get(d.get("wakeup_status") or "", "")
    return f'<span class="pill wakeup">wake-up · {e(trigger_txt(d.get("trigger")))}{status}</span> '


def _orders_summary(actions: list[dict[str, Any]]) -> str:
    """Header of a decision with orders: "Buy BTC/EUR, sell ETH/EUR"."""
    words = [f'{"buy" if a["side"] == "buy" else "sell"} {a["symbol"]}' for a in actions]
    txt = ", ".join(words)
    return txt[:1].upper() + txt[1:]


def model_page(data: dict[str, Any], p: dict[str, Any], baseline_chart: dict[str, Any]) -> str:
    min_cycles = data["min_cycles_stats"]
    llm = p["kind"] == "llm"
    common_stats = [
        _stat("Net return", pct(p["total_return"]), cls=f"large {tone(p['total_return'])}", card="key"),
        _stat(
            "Portfolio value", eur(p["equity_ueur"]),
            f'<small class="sub">{"live · " if p.get("equity_live") and _live_fresh(data) else ""}'
            f'start {eur(p["base_ueur"], decimals=0 if p["base_ueur"] % 1_000_000 == 0 else 2)}</small>',
        ),
        _stat("Max drawdown", _drawdown(p)),
        _stat("Rank <span class=\"count\">/100 vs chance</span>", _rank_cell(p)),
        _stat("Sharpe", _sharpe_cell(p, min_cycles)),
    ]
    if llm:
        n_dec = p.get("n_decided") or 0
        n_skipped = sum(p["skipped"].values())
        skipped_note = f'<small class="sub">{plural(n_skipped, "skipped", "skipped")}</small>' if n_skipped else ""
        extra = [
            _stat("Orders", str(p["n_trades"]), f'<small class="sub">{eur(p["fees_paid_ueur"])} in fees</small>'),
            _stat(_cost_title(data), _cost_cell(p)),
            _stat("Decisions received", str(n_dec), skipped_note),
        ]
    else:
        extra = [
            _stat("Orders", str(p["n_trades"])),
            _stat("Fees paid", eur(p["fees_paid_ueur"])),
            _stat("Cash", eur(p["cash_ueur"])),
        ]
    stats_html = "".join(common_stats + extra)
    alerts = []
    if p.get("archive"):
        alerts.append(
            f'<p class="alert info"><strong>Archived AI</strong> on {stamp(p["archive"]["ts"])}. '
            "Its positions were sold at market; it no longer plays and its figures are frozen. "
            "Its curve remains, dotted, in the spot league.</p>"
        )
    elif p["halted"]:
        alerts.append('<p class="alert loss-bg">Portfolio halted: maximum drawdown reached, positions closed.</p>')
    elif p["frozen_until_ts"]:
        alerts.append(f'<p class="alert warn">Portfolio frozen until {stamp(p["frozen_until_ts"])}.</p>')
    if never_decides(p) and not p.get("archive"):
        reason = _skip_reason_label(p)
        why = f": {e(reason)}" if reason else ""
        alerts.append(
            f'<p class="alert warn">This model has never decided yet{why}. Its figures are those of a portfolio that stayed in cash.</p>'
        )
    verdict = "" if never_decides(p) or p.get("archive") else _luck_verdict(p, min_cycles)  # the alert already says it
    rejection_notes = []
    if p["rejects"]:
        rejection_notes.append(
            "<p><strong>Risk check rejections</strong>: "
            + ", ".join(
                f"{e(RISK_CODES.get(c, c))} <code>{e(c)}</code> ({n})"
                for c, n in sorted(p["rejects"].items(), key=lambda kv: -kv[1])
            )
            + ".</p>"
        )
    decision_items = "".join(_decision_html(d) for d in p["decisions"])
    remaining = p["decisions_total"] - len(p["decisions"])
    remaining_html = (
        f'<p class="muted">+{plural(remaining, "older decision", "older decisions")} in the journal.</p>'
        if remaining > 0 else ""
    )  # fmt: skip
    decs_html = f'<ol class="decisions">{decision_items}</ol>' if decision_items else '<p class="empty">No decision journaled for this portfolio.</p>'
    desc = p["description"]
    if p.get("late") and p.get("start_ts"):
        alerts.append(
            f'<p class="alert info">Joined the arena on {stamp(p["start_ts"])}: figures since that date.</p>'
        )
    title_h1 = f'<h1>{e(p["name"])}</h1>'
    verdict_html = f'<p class="verdict-head">{verdict}</p>' if verdict else ""
    body = f"""
<p class="feed"><a href="../{"spot.html" if data.get("perp") else "index.html"}"><span aria-hidden="true">← </span>{"Spot league" if data.get("perp") else "Overview"}</a><span class="feed-sep" aria-hidden="true">/</span><span>{"AI models" if llm else "Benchmarks"}</span></p>
<header class="head-model">
  {title_h1}{verdict_html}
  {f'<p class="lead">{e(desc)}</p>' if desc else ""}
</header>
{"".join(alerts)}
<dl class="stats">{stats_html}</dl>
<section aria-labelledby="title-curve"><h2 id="title-curve">Net return <span class="h-note">fees included</span></h2>{_chart_block(baseline_chart, focus_name=p["name"], focus=p["id"])}</section>
<section aria-labelledby="title-positions"><h2 id="title-positions">Positions <span class="h-note">simulated</span></h2>{_positions(p)}</section>
<section aria-labelledby="title-decisions"><h2 id="title-decisions">Decisions <span class="h-note">newest first</span></h2>
{"".join(rejection_notes)}
{decs_html}{remaining_html}
</section>
"""
    return layout(
        title=p["name"], body=body, root="../", active=p["id"], data=data, path=f"model/{p['slug']}.html",
        scripts=_chart_scripts("../", baseline_chart, p["id"]) if _curve_visible(baseline_chart) else "",
    )  # fmt: skip


# ---------------------------------------------------------------------------
# Method page
# ---------------------------------------------------------------------------

POLICY_LABELS = {
    "symbols": ("Allowed pairs", "whitelist"),
    "max_order_bp": ("Maximum size of a buy", "bp_pct:of equity"),
    "max_position_bp": ("Maximum position per symbol", "bp_pct:of equity after the order"),
    "max_exposure_bp": ("Maximum total exposure", "bp_pct:of equity"),
    "max_trades_per_day": ("Trades per portfolio per 24 h", "n"),
    "max_orders_per_minute": ("Orders per minute (all portfolios)", "n"),
    "min_interval_same_symbol_s": ("Minimum delay between two buys of the same symbol", "duration"),
    "stop_bp_min": ("Minimum stop on a buy", "bp_pct:below entry"),
    "stop_bp_max": ("Maximum stop on a buy", "bp_pct:below entry"),
    "max_cost_to_expected_move_pct": ("Round-trip cost / expected move, at most", "pct_int"),
    "max_holding_s": ("Maximum holding (forced exit)", "duration"),
    "daily_loss_freeze_bp": ("24 h loss that triggers a freeze", "bp_pct:of equity"),
    "freeze_duration_s": ("Freeze duration", "duration"),
    "drawdown_halt_bp": ("Drawdown that triggers the halt and flattening", "bp_pct:from the peak"),
    "monthly_fee_budget_bp": ("Fee budget of the calendar month", "bp_pct:of start-of-month equity"),
    "max_quote_deviation_bp": ("Maximum gap between quote and last close", "bp_pct:"),
    "max_spread_multiple": ("Maximum spread (multiple of the median of the last 20)", "mult"),
    "min_order_ueur": ("Minimum order (at least the Kraken minimum)", "eur"),
}


def _policy_value(key: str, v: Any) -> tuple[str, str]:
    kind = POLICY_LABELS[key][1]
    if key == "symbols":
        return ", ".join(v), ""
    if kind.startswith("bp_pct"):
        return bp_pct(v), kind.partition(":")[2]
    if kind == "duration":
        return duration(v), ""
    if kind == "pct_int":
        return f"{v}%", ""
    if kind == "mult":
        return f"× {v}", ""
    if kind == "eur":
        return eur(v), ""
    return str(v), ""


def _list_models(data: dict[str, Any]) -> tuple[str, str]:
    """("Four AI models (Claude Haiku 5.5, Sonnet 5.5, Opus 5.5 and Fable 5.2)", sentence about arrivals).
    Counts the opened portfolios, like the home page; a model that is configured but not yet opened is announced separately."""
    opened = [p for p in data["portfolios"] if p["kind"] == "llm"]
    ids = {p["id"] for p in opened}
    names = [p["name"] if i == 0 else p["name"].removeprefix("Claude ") for i, p in enumerate(opened)]
    n_models = len(names)
    items = (names[0] if n_models == 1 else ", ".join(names[:-1]) + " and " + names[-1]) if names else ""
    head = f"{NUMBERS.get(n_models, str(n_models))} AI model{'s' if n_models > 1 else ''}" + (f" ({items})" if items else "")
    notes = [
        f"{p['name']} joined the arena on {stamp(p['start_ts'], year=False)}, after the others; its figures run from that date."
        for p in opened
        if p.get("late") and p.get("start_ts")
    ]
    notes += [f"{name(model_cfg['portfolio'])} will join the arena at the next cycle." for model_cfg in data["method"]["models"] if model_cfg["portfolio"] not in ids]
    return head, (" " + " ".join(notes)) if notes else ""


def _watch_method(data: dict[str, Any]) -> str:
    watch = data["method"].get("watch")
    if not watch:
        return ""
    return (
        '<section aria-labelledby="m-watch"><h2 id="m-watch">Watch and wake-ups</h2>'
        f"<p>Every {watch['tick_s'] // 60} min, the watch samples the prices, updates the value of the portfolios "
        "and executes the stops, judged on one-minute trades. "
        f"If an asset moves by at least {bp_pct(watch['move_threshold_bp'])} within {duration(watch['move_window_s'])}, the models and the "
        f"random benchmark are woken up to decide outside the appointment: at most {watch['max_wakeups_per_day']} wake-ups per day, "
        f"spaced at least {duration(watch['cooldown_s'])} apart. The Sharpe ratio and the statistics are still computed at the 4 h cycles.</p></section>"
    )


def _season_method(data: dict[str, Any]) -> str:
    season_info = data.get("season")
    if not season_info:
        return ""
    start = season_info["start_ts"] if season_info["status"] == "planned" else season_info["cycle"]
    body = (
        f"<p>{e(season_info['name'])}: {season_info['duration_days']} days starting {stamp(start, year=False)}. "
        "The configuration, the risk policy, the models' prompt and the code are frozen; any change requires "
        "a written waivers, listed here. The ranking starts from the value of each portfolio at the first cycle of the "
        "season; the burn-in before it is excluded.</p>"
    )
    waivers = season_info.get("waivers") or []
    if waivers:
        body += '<ul class="list-simple">' + "".join(
            f"<li>{stamp(d['ts'], year=False)}: {e(waiver_reason(data, d['reason']))}"
            + (f" <span class=\"muted\">({e(', '.join(FROZEN_ITEM_NAMES.get(k, k) for k in d['what']))})</span>" if d["what"] else "")
            + "</li>"
            for d in waivers
        ) + "</ul>"
    elif season_info["status"] != "planned":
        body += '<p class="muted">No waivers.</p>'
    return f'<section aria-labelledby="m-season"><h2 id="m-season">Season</h2>{body}</section>'


def method_page(data: dict[str, Any]) -> str:
    m, j, pv = data["method"], data["journal"], data["provenance"]
    n_benchmarks = sum(1 for p in data["portfolios"] if p["kind"] != "llm")
    models_sentence, arrivals = _list_models(data)
    policy_rows = "".join(
        f'<tr><th scope="row">{e(POLICY_LABELS[k][0])}</th><td class="n" data-label="Value">{e(_policy_value(k, v)[0])}</td>'
        f'<td class="muted" data-label="Basis">{e(_policy_value(k, v)[1])}</td></tr>'
        for k, v in m["policy"].items()
        if k in POLICY_LABELS
    )
    ok = j["verify_ok"]
    check = (
        f'<p><span class="pill {"ok" if ok else "loss-bg"}">Journal verification: {"chain intact" if ok else "FAILED"}</span> '
        f'{plural(j["n_records"], "event")}, last seq {e(j["head_seq"])}.</p>'
    )
    if j["errors"]:
        check += "<ul class=\"list-simple\">" + "".join(
            f'<li><code>{e(x["code"])}</code> line {x["line"]}: {e(x["message"])}</li>' for x in j["errors"]
        ) + "</ul>"
    models = "".join(
        f'<tr><th scope="row"><code>{e(x["model"])}</code></th><td class="n" data-label="Budget per day">{usd(x["daily_budget_uusd"])}</td>'
        f'<td class="n" data-label="Price per million tokens, input / output">{usd(x["price_in_uusd_per_mtok"])} / {usd(x["price_out_uusd_per_mtok"])}</td></tr>'
        for x in m["models"]
    )
    policy_same = (
        pv["journal_policy_sha256"] is None or pv["journal_policy_sha256"] == pv["policy_sha256"]
    )
    prompts = ", ".join(f'<code>{e(h)}</code>' for h in pv["prompt_hashes"]) or "not journaled"
    if data.get("decider_backend") == "subscription" and data.get("public"):
        backend = "<p>The cost shown is the equivalent at the API's list price.</p>"
    elif data.get("decider_backend") == "subscription":
        backend = "<p>Calls go through the subscription, nothing is billed per use; the cost shown is the API equivalent.</p>"
    elif data.get("decider_backend") == "api":
        backend = "<p>The models are called through the Anthropic API; the cost shown is computed with the prices below.</p>"
    else:
        backend = ""
    divergence = "" if policy_same else ' <span class="pill loss-bg">different from the last journaled load</span>'
    body = f"""
<header class="head-model">
  <h1>Method</h1>
</header>
{_perp_method(data)}
<section aria-labelledby="m-arena"><h2 id="m-arena">What the arena does</h2>
<p>{models_sentence} and {NUMBERS_MIN.get(n_benchmarks, n_benchmarks)} benchmarks without AI each manage {eur(m["capital_ueur"], decimals=0)} of play money on 6 Kraken euro pairs.
Every {duration(m["interval_s"])}: decision, risk check, simulated execution. Buys only, no leverage. Everything is written to a hash-chained journal.{arrivals}</p></section>

{_watch_method(data)}
{_season_method(data)}
<section aria-labelledby="m-benchmarks"><h2 id="m-benchmarks">The benchmarks</h2>
<dl class="rules">
<div><dt>Basket</dt><dd>1/6 in each pair at the first cycle, then held.</dd></div>
<div><dt>60/40</dt><dd>60% in BTC, 40% in cash, rebalanced every month.</dd></div>
<div><dt>E0065 (adapted)</dt><dd>Fixed rule on buying pressure (share of buys at the market price, Binance daily candles): L = {m["e0065"]["L"]}, k = {m["e0065"]["k"]}, H = {m["e0065"]["H"]}, recomposed every {m["e0065"]["H"]} days.</dd></div>
<div><dt>Random</dt><dd>0 to 2 randomly drawn actions per cycle, same risk rules. {_group(m["n_paths"])} trajectories of this kind, replayed on the same prices, give the rank /100 of each portfolio.</dd></div>
</dl></section>

<section aria-labelledby="m-fees"><h2 id="m-fees">Simulated fees and slippage</h2>
<p>Model <code>{e(m["fill_model_version"])}</code>, market orders: buy at the ask +{bp_pct(m["slippage_bp"])}, sell at the bid −{bp_pct(m["slippage_bp"])},
fees of {bp_pct(m["taker_fee_bp"])} per order (Kraken taker +25%), roundings always unfavorable. Stop set at entry, holding limited to {duration(policy_max_holding(m))}.
Positions valued at the last bid.</p></section>

<section aria-labelledby="m-risk"><h2 id="m-risk">Risk policy (simulation)</h2>
<p class="muted">More lenient than a real-money policy.</p>
<div class="table-scroll" tabindex="0" role="region" aria-label="Risk policy table, scrollable"><table class="table stacked"><caption class="visually-hidden">Risk check rules</caption>
<thead><tr><th scope="col">Rule</th><th scope="col" class="n">Value</th><th scope="col">Basis</th></tr></thead><tbody>{policy_rows}</tbody></table></div></section>

<section aria-labelledby="m-models"><h2 id="m-models">AI models and cost</h2>
{backend}
<div class="table-scroll" tabindex="0" role="region" aria-label="Models table, scrollable"><table class="table stacked"><caption class="visually-hidden">Budget and prices of the models</caption>
<thead><tr><th scope="col">Model</th><th scope="col" class="n">Budget per day</th><th scope="col" class="n">Price per million tokens <span class="count">input / output</span></th></tr></thead><tbody>{models}</tbody></table></div>
<p class="muted note">Versioned system prompt: {prompts}. The model only sees closed bars computed by the code, no web text.</p></section>

<section aria-labelledby="m-journal"><h2 id="m-journal">Journal integrity</h2>
{check}
<dl class="fingerprints">
<div><dt>Chain head</dt><dd><code class="hash">{e(j["head_hash"])}</code></dd></div>
<div><dt>Risk policy (sha256)</dt><dd><code class="hash">{e(pv["policy_sha256"])}</code>{divergence}</dd></div>
<div><dt>Configuration (sha256)</dt><dd><code class="hash">{e(pv["config_sha256"])}</code></dd></div>
<div><dt>Commit</dt><dd><code>{e(pv["git_head"] or "not journaled")}</code></dd></div>
<div><dt>Execution mode</dt><dd>{"simulation (no real order)" if data["venue_mode"] == "paper" else e(data["venue_mode"])}</dd></div>
</dl></section>

<section aria-labelledby="m-limits"><h2 id="m-limits">Limitations</h2>
<ul class="list-simple">
<li><strong>Simulation.</strong> No rejection, no partial fill, no market impact.</li>
<li><strong>Constant slippage.</strong> Pessimistic fees, but the slippage depends neither on the size nor on the order book.</li>
<li><strong>Small sample.</strong> Before {data["min_cycles_stats"]} cycles, almost nothing can be told apart from chance: that is the default verdict.</li>
<li><strong>Hash-chained journal.</strong> It proves that nothing was modified after the fact, not that the prices or the decisions were not chosen before being written.</li>
<li><strong>Rank against chance.</strong> The trajectories replay cycles and wake-ups, but their stops are only checked at the cycles, on the 4 h bars.</li>
<li><strong>Narrow universe.</strong> 6 cryptos, buys only, short period: nothing that carries over to real money.</li>
</ul></section>

<section class="opinions" aria-labelledby="m-warning"><h2 id="m-warning">Disclaimer</h2>
<p><strong>This is not investment advice.</strong> Personal experiment in simulation, with no recommendation or promise of return. Investing in crypto-assets carries a risk of total loss.</p></section>
"""
    return layout(
        title="Method", body=body, root="", active="method", data=data, league="perp", path="method.html",
        desc="How the arena works: real Kraken prices, simulated orders with fees, guardrails, benchmarks without AI and a verifiable hash-chained journal.",
    )


def _perp_method(data: dict[str, Any]) -> str:
    from arena.site.render_perp import method_section  # local import: render_perp imports this module

    sec = method_section(data)
    return f'{sec}<h2 class="title-league">The spot league</h2>' if sec else ""


def policy_max_holding(m: dict[str, Any]) -> int:
    return int(m["policy"]["max_holding_s"])
