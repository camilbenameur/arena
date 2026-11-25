"""Pages of the derivatives league (home page of the site, one page per portfolio, method section) and of the councils
league (home page, one page per council, councils method; same journal as the derivatives).

Same "notebook" direction as the spot league: rules, few words, tabular figures. Any text coming from the journal is
escaped; the models' free texts (justification, invalidation) are published as is, escaped, and length-capped.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from arena.site import readable as L
from arena.site import perp as P
from arena.site.perp import IMPACTS
from arena.site.render import (
    DIRECT_FEED,
    MINUS,
    NBSP,
    _chart_scripts,
    pause_note,
    _group,
    _legend,
    last_value,
    short_date,
    _stat,
    e,
    stack,
    eur,
    hour,
    iso,
    json_inline,
    layout,
    short_name,
    pct,
    plural,
    stamp,
    tone,
    usd,
    when,
)

SHORT_TOOLS = {
    "candles": "candles", "order_book": "order book", "derivatives": "funding", "indicators": "indicators",
    "simulate_order": "order simulation", "history": "its history",
}  # fmt: skip
MIN_POINTS = 3  # under 3 readings (90 min), the curve is only a straight line


def price_usd(uusd: int | None) -> str:
    """Price of a contract in dollars: 2 decimals above $100, 4 below (XRP)."""
    if uusd is None:
        return "—"
    digits = 2 if abs(uusd) >= 100_000_000 else 4
    v = (Decimal(abs(uusd)) / Decimal(1_000_000)).quantize(Decimal(1).scaleb(-digits))
    whole, _, frac = f"{v:f}".partition(".")
    return f"{MINUS if uusd < 0 else ''}${_group(int(whole))}.{frac}"


def quantity(q: int) -> str:
    """Quantity in units of the underlying, at most 6 significant digits: "0.783846", "323.987"."""
    d = Decimal(abs(q)) / Decimal(100_000_000)
    if d == 0:
        return "0"
    d = round(d, max(0, 5 - d.adjusted())).normalize()
    return format(d, "f")


def pc(v: float | None, *, sign: bool = False) -> str:
    """"25%" from a figure already in % (the `*_pct` fields of the decisions)."""
    if v is None:
        return "—"
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return f"{'+' if sign and v > 0 else ''}{s}%"


def leverage(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x:.2f}x"


def level(cond: str | None, price: int | None) -> str:
    """"above $98,000.00", "below $3,200.00"."""
    word = {"above": "above", "below": "below"}.get(cond or "", "at")
    return f"{word} {price_usd(price)}"


def _after(rel: list[dict[str, Any]]) -> str:
    return " and ".join(r["label"] for r in rel)


def trigger(d: dict[str, Any] | None) -> str:
    if not d:
        return "wake-up"
    if d.get("type") == "announcement":
        n = len(d.get("announcements") or [])
        return "Kraken announcement" + (
            f" · {d['announcements'][0]['title']}" if n == 1 else f" · {n} announcements" if n > 1 else ""
        )
    if d.get("type") == "publication":
        return "macro release" + (f" · after {_after(d['releases'])}" if d.get("releases") else "")
    if d.get("type") == "alert":
        return f"its alert · {d.get('instrument') or '?'} {level(d.get('condition'), d.get('price_uusd'))}"
    if d.get("type") == "order":
        return f"entry order · {d.get('instrument') or '?'} {level(d.get('condition'), d.get('price_uusd'))}"
    move = d.get("move_bp")
    if move is None:
        return f"wake-up · {d.get('instrument') or '?'}"
    return f"wake-up · {d['instrument']} {pct(move / 10_000, digits=1)} in 1 h"


def _round_pill(d: dict[str, Any]) -> str:
    """Why the AI was called outside a scheduled round. The regular call, by far the most frequent, stays discreet."""
    k = d.get("kind")
    attached_news = ""
    n = (d.get("trigger") or {}).get("news")
    if n and k not in (
        "news",
        "calendar",
    ):  # another trigger that also carried an announcement or a release
        attached_news = f' <span class="pill subtle" title="{e(_news_title(n))}">{"Kraken announcement" if n["announcements"] else "macro release"} attached</span>'
    if k == "bar":
        return '<span class="pill subtle">4 h bar close</span> '
    if k == "restoration":
        return '<span class="pill subtle">end of a braking</span> '
    if k == "veto":
        return f'<span class="pill wakeup">veto · {e(trigger(d.get("trigger")))}</span> '
    if k == "cadence":
        return f'<span class="pill subtle">regular call</span>{attached_news} '
    if k == "scheduled":
        return f'<span class="pill neutral">at its request</span>{attached_news} '
    if k in ("news", "calendar"):
        dec = d.get("trigger") or {"type": "announcement" if k == "news" else "publication"}
        return f'<span class="pill wakeup">{e(trigger(dec))}</span> '
    if k not in ("wakeup", "alert", "order"):
        return ""
    return f'<span class="pill wakeup">{e(trigger(d.get("trigger")))}</span>{attached_news} '


def _news_title(n: dict[str, Any]) -> str:
    return "; ".join([*(f"after {r['label']}" for r in n["releases"]), *(a["title"] for a in n["announcements"])])


KINDS = {
    "incident": "incident",
    "maintenance": "maintenance",
    "delisting": "contract delisting",
    "contract_state": "contract state",
}
STATUSES = {
    "investigating": "investigating", "identified": "cause identified", "monitoring": "monitoring", "resolved": "resolved",
    "postmortem": "analysis complete", "scheduled": "scheduled", "in_progress": "in progress", "verifying": "verifying",
    "completed": "completed", "abnormal": "abnormal", "normal": "normal", "unlisted": "delisted",
}  # fmt: skip
CLOSED = {"resolved", "postmortem", "completed", "normal", "unlisted"}


def _announcement(a: dict[str, Any]) -> str:
    status = STATUSES.get(a["status"], a["status"] or "unknown status")
    tone_ = "neutral" if a["status"] in CLOSED else ("info" if a["kind"] == "maintenance" else "warn")
    impact = IMPACTS.get(a["impact"])
    chunks = [f'<span class="pill {tone_}">{e(status)}</span>']
    if impact and a["status"] not in CLOSED:
        chunks.append(
            f'<span class="pill {"loss-bg" if a["impact"] in ("major", "critical") else "warn"}">{impact} impact</span>'
        )
    span = ""
    if a["starts_ts"] and a["ends_ts"]:
        span = f"from {when(a['starts_ts'], year=False)} to {when(a['ends_ts'], year=False)}"
    elif a["starts_ts"]:
        span = f"from {when(a['starts_ts'], year=False)}"
    elif a["ends_ts"]:
        span = f"until {when(a['ends_ts'], year=False)}"
    details = [e(KINDS.get(a["kind"], "announcement"))]
    if span:
        details.append(e(span))
    if a["instruments"]:
        details.append(e("contracts: " + ", ".join(a["instruments"])))
    details.append(f"updated {stamp(a['update_ts'], year=False)}")
    link = f' <a href="{e(a["url"])}" rel="noopener noreferrer">Kraken link</a>' if a["url"] else ""
    return (
        f'<li class="line no-detail news-item"><span class="news-title">{e(a["title"])}</span> {" ".join(chunks)}'
        f'<span class="muted news-sub">{" · ".join(details)}{link}</span></li>'
    )


def news_block(perp: dict[str, Any]) -> str:
    """The macro calendar of the next 7 days and Kraken's derivatives announcements of the last 7 days."""
    news = perp.get("news")
    if news is None:
        return ""
    lines = []
    cal = news.get("calendar")
    if cal is not None:
        if cal:
            for c in cal:
                recall = (
                    ' <span class="pill wakeup">recalls the AIs 3 min after</span>' if c["recall"] else ""
                )
                lines.append(
                    f'<li class="line no-detail news-item"><span class="news-title">{e(c["label"])}</span> <span class="muted">{stamp(c["ts"], year=False)}</span>{recall}</li>'
                )
            cal_html = (
                f'<h3>Upcoming macro releases</h3><ul class="decisions news-list">{"".join(lines)}</ul>'
            )
        else:
            cal_html = '<h3>Upcoming macro releases</h3><p class="muted">No macro release in the next 7 days.</p>'
    else:
        cal_html = ""
    ann = news.get("announcements") or []
    if ann:
        ann_html = (
            f'<h3>Kraken announcements</h3><ul class="decisions news-list">{"".join(_announcement(a) for a in ann)}</ul>'
        )
    else:
        ann_html = '<h3>Kraken announcements</h3><p class="muted">No Kraken derivatives announcement in the last 7 days.</p>'
    return (
        '<section aria-labelledby="title-news"><h2 id="title-news">News <span class="h-note">official sources only</span></h2>'
        f'{cal_html}{ann_html}<p class="muted"><a href="method.html#m-news">What the AIs see</a></p></section>'
    )


def _actions_summary(actions: list[dict[str, Any]]) -> str:
    """"Short ETH, closes BTC"; "No orders" without actions."""
    words = []
    for a in actions:
        if a.get("discarded") and not a.get("action"):
            words.append("discarded action")
            continue
        verb = {"open_long": "long", "open_short": "short", "reduce": "reduces", "close": "closes"}.get(a.get("action") or "", "?")
        words.append(f"{verb} {a['instrument']}")
    if not words:
        return "No orders"
    txt = ", ".join(words)
    return txt[:1].upper() + txt[1:]


def element(x: dict[str, Any]) -> str:
    """An alert or an entry order on one HTML line (the model's texts are escaped)."""
    place = f"{e(x['instrument'])} {level(x.get('condition'), x.get('price_uusd'))}"
    if x["type"] == "alert":
        txt = f"<strong>Alert</strong> {place}"
        if x.get("note"):
            txt += f' <span class="muted">“{e(x["note"])}”</span>'
        return txt
    parts = [f"<strong>{e((x.get('side') or '?').capitalize())} order</strong> {place}"]
    if x.get("size_pct") is not None:
        parts.append(f"{pc(x['size_pct'])} of the portfolio")
    if x.get("stop_pct") is not None:
        parts.append(f"stop {pc(x['stop_pct'])}")
    if x.get("target_pct") is not None:
        parts.append(f"target {pc(x['target_pct'])}")
    txt = " · ".join(parts)
    if x.get("invalidation"):
        txt += f'<span class="invalidation">Invalid if: {e(x["invalidation"])}</span>'
    return txt


def _placed_summary(d: dict[str, Any]) -> str:
    """"1 alert and 1 entry order set"; empty if nothing."""
    els = (d.get("placed") or {}).get("elements") or []
    n_alerts = sum(1 for x in els if x["type"] == "alert")
    n_orders = len(els) - n_alerts
    words = [m for m in (plural(n_alerts, "alert set", "alerts set") if n_alerts else "", plural(n_orders, "entry order set", "entry orders set") if n_orders else "") if m]
    if d.get("recall_ts"):
        words.append(f"recall at {hour(d['recall_ts'])}")
    return " and ".join(words)


def _placed(d: dict[str, Any]) -> str:
    placed = d.get("placed") or {}
    els, refused = placed.get("elements") or [], placed.get("refused") or []
    if not els and not refused and not d.get("recall_ts"):
        return ""
    items = "".join(f"<li>{element(x)}</li>" for x in els)
    if d.get("recall_ts"):
        items += f"<li><strong>Recall</strong> requested for {hour(d['recall_ts'])}</li>"
    if refused:
        reason_list = sorted({r["reason"] for r in refused})
        items += f'<li class="muted">{plural(len(refused), "refused", "refused")} at creation: {e(", ".join(reason_list))}</li>'
    return f'<div class="placed"><span class="label">Left for later</span><ul class="list-simple">{items}</ul></div>'


def _positions_cell(p: dict[str, Any]) -> str:
    if not p["positions"]:
        return '<span class="muted">none</span>'
    return " ".join(
        f'<span class="side side-{x["side"]}">{e(x["instrument"])} {x["side"]}</span>' for x in p["positions"]
    )


def _status(p: dict[str, Any]) -> str:
    arch = p.get("archive")
    if arch:
        return f' <span class="pill neutral">archived on {short_date(arch["ts"])}</span>'
    st = p.get("status")
    if not st:
        return ""
    if st["state"] == "stopped":
        return f' <span class="pill loss-bg">{"stopped, ruined" if p["kind"] == "council" else "stopped"}</span>'
    return ' <span class="pill warn">frozen</span>'


def _since(perp: dict[str, Any], p: dict[str, Any]) -> str:
    """"since Nov 13, 02:00 UTC" for a portfolio that entered after the league opened (return measured since)."""
    if perp.get("opened_ts") and p["open_ts"] - perp["opened_ts"] > 900:
        return f'<small class="desc">since {stamp(p["open_ts"], year=False)}</small>'
    return ""


def _folder(p: dict[str, Any]) -> str:
    """The folder of a portfolio's page: councils have their own, the basket benchmark stays with the derivatives."""
    return "councils" if p["kind"] == "council" or p["id"] == P.TREND_ENGINE else "derivatives"


def _short_outside_rule(p: dict[str, Any]) -> str:
    return '<small class="desc">paper demo, outside the 2x rule</small>' if p["kind"] == "council" else ""


def _robot_account(p: dict[str, Any]) -> str:
    """A robot's line: what it saw (shocks) and did (trades); nothing for the other portfolios."""
    if p["kind"] != "robot":
        return ""
    return f'<small class="account-robot">{plural(p.get("n_shocks") or 0, "shock seen", "shocks seen")} · {plural(p.get("n_trades") or 0, "trade", "trades")}</small>'


def _codes(d: dict[str, Any]) -> dict[str, str]:
    return {"council": P.COUNCIL_CODES, "trend": P.TREND_CODES}.get(str(d.get("rules")), P.CODES)


def _funding_cell(p: dict[str, Any]) -> str:
    n = p["funding_net_ueur"]
    if not p["funding_paid_ueur"] and not p["funding_received_ueur"]:
        return '<span class="muted">—</span>'
    # Paid = cost: shown as negative for the portfolio.
    return f'<span class="{tone(-n)}">{eur(-n, signed=True)}</span>'


# ---------------------------------------------------------------------------
# Live prices (assets/direct.js)
# ---------------------------------------------------------------------------


def _pos_direct(x: dict[str, Any]) -> bool:
    return bool(x.get("product")) and isinstance(x.get("mark_uusd"), int) and isinstance(x.get("latent_ueur"), int)


def _direct_pf(p: dict[str, Any]) -> bool:
    """A portfolio is revalued live if it has a priced position and a published euro-dollar rate."""
    return bool(p.get("fx")) and any(_pos_direct(x) for x in p["positions"])


def _live_attrs(p: dict[str, Any], what: str, x: dict[str, Any] | None = None) -> str:
    """Attributes that mark a figure to revalue live; nothing if the portfolio does not lend itself to it."""
    if not _direct_pf(p) or (x is not None and not _pos_direct(x)):
        return ""
    out = f' data-direct="{what}" data-pf="{e(p["slug"])}"'
    return out + (f' data-p="{e(x["product"])}"' if x is not None else "")


def _direct_scripts(root: str, perp: dict[str, Any], pfs: list[dict[str, Any]]) -> str:
    """The published positions (quantity, entry price, official unrealized P&L) that direct.js revalues at the current mark."""
    if not pfs:
        return ""
    ref: dict[str, int] = {}
    out: dict[str, Any] = {}
    for p in pfs:
        pos = [x for x in p["positions"] if _pos_direct(x)]
        for x in pos:
            ref[x["product"]] = x["mark_uusd"]
        out[p["slug"]] = {
            "c": p["capital_ueur"], "eq": p["equity_ueur"], "fx": p["fx"],
            "pos": [{"p": x["product"], "q": x["signed_qty"], "e": x["entry_uusd"], "l": x["latent_ueur"]} for x in pos],
        }  # fmt: skip
    payload = {
        "flow": DIRECT_FEED, "products": sorted(ref), "ref": ref, "pf": out,
        "statement": hour(perp["live_ts"]) if perp.get("live_ts") else "",
    }  # fmt: skip
    return f'\n<script id="direct-data" type="application/json">{json_inline(payload)}</script>\n<script src="{root}assets/direct.js"></script>'


# ---------------------------------------------------------------------------
# Curve
# ---------------------------------------------------------------------------


def _ref_chart(perp: dict[str, Any], focus: str | None) -> dict[str, Any]:
    ch = perp["chart"]
    if focus is None:
        return ch
    keep = {focus, P.BASKET}
    return {**ch, "series": [s for s in ch["series"] if s["id"] in keep]}


def curve_visible(chart: dict[str, Any]) -> bool:
    return len(chart["x"]) >= MIN_POINTS and bool(chart["series"])


def _chart_block(chart: dict[str, Any], *, focus: str | None = None, focus_name: str | None = None, league: str = "derivatives") -> str:
    if not curve_visible(chart):
        return '<p class="empty empty-short">The curve appears after 90 minutes of readings. The values are in the table.</p>'
    last_items = "; ".join(
        f"{s['name']}{' (archived)' if s.get('archive_ts') else ''} {pct((last_value(s['values']) - 100) / 100) if last_value(s['values']) is not None else '—'}"
        for s in chart["series"]
    )
    period = f"from {when(chart['x'][0])} to {when(chart['x'][-1])}"
    if focus_name:
        label = f"Cumulative net return of {focus_name}, compared with the 1x basket benchmark, {period}. Latest values: {last_items}."
    else:
        label = f"Cumulative net return of the {len(chart['series'])} portfolios of the {'councils' if league == 'councils' else 'derivatives'} league, {period}. Latest values: {last_items}."
    return (
        '<figure class="chart-panel">'
        f'<div id="chart" class="chart-area" role="img" aria-label="{e(label)}">'
        '<noscript><p class="empty">Chart: JavaScript required. Values in the table.</p></noscript></div>'
        # The curve is the journal's: its legend dates the reading, the live estimate is elsewhere.
        f'{_legend(chart, focus).replace(">Live: ", ">Latest snapshot: ", 1)}{pause_note(chart)}</figure>'
    )


# ---------------------------------------------------------------------------
# League home page
# ---------------------------------------------------------------------------


def _table(perp: dict[str, Any], *, councils: bool = False) -> str:
    pfs = perp["portfolios"]
    vmax = max((abs(p["net_return"] or 0.0) for p in pfs), default=0.0)
    from arena.site.render import _svg_bar

    def line(p: dict[str, Any]) -> str:
        subtitle_html = f'<small class="desc">{e(p["subtitle"])}</small>' if p.get("subtitle") else ""
        return (
            f'<tr class="{e(p["kind"])}{" archive" if p.get("archive") else ""}"><th scope="row"><a href="{_folder(p)}/{e(p["slug"])}.html">{e(p["name"])}</a>{_status(p)}{subtitle_html}{_robot_account(p)}{_since(perp, p)}{_short_outside_rule(p)}</th>'
            f'<td class="n key"><span class="{tone(p["net_return"])}"{_live_attrs(p, "ret")}>{pct(p["net_return"])}</span>{_svg_bar(p["net_return"], vmax)}</td>'
            f'<td class="n"><span{_live_attrs(p, "val")}>{eur(p["equity_ueur"])}</span></td>'
            f'<td class="n">{leverage(p["leverage"])}</td>'
            f'<td class="n">{pct(-p["drawdown_max"]) if p["drawdown_max"] else "0.00%"}</td>'
            f'<td class="positions-cell">{_positions_cell(p)}</td></tr>'
        )

    def group(kind: str, title: str, n_col: int, note: str = "") -> str:
        lines = [line(p) for p in sorted((p for p in pfs if p["kind"] == kind), key=lambda p: bool(p.get("archive")))]
        if not lines:
            return ""
        note = f' <span class="h-note">{e(note)}</span>' if note else ""
        return f'<tbody class="group-{kind}"><tr class="group"><th scope="rowgroup" colspan="{n_col}">{title}{note}</th></tr>{"".join(lines)}</tbody>'

    n_col = 6
    head = (
        '<tr><th scope="col">Portfolio</th><th scope="col" class="n">Net return</th><th scope="col" class="n">Value</th>'
        '<th scope="col" class="n">Leverage</th><th scope="col" class="n">Worst drawdown</th><th scope="col">Positions</th></tr>'
    )
    labels = ["Net return", "Value", "Leverage", "Worst drawdown", "Positions"]
    if councils:
        name, body = "councils league", group("council", "Councils", n_col, P.COUNCIL_BADGE) + group("benchmark", "Benchmark", n_col)
        caption = "Councils league: the councils, then the reference benchmark"
    else:
        name, body = "derivatives league", group("llm", "AI models", n_col) + group("robot", "Robots", n_col, "no AI") + group("benchmark", "Benchmarks", n_col)
        caption = "Derivatives league: AI models, robots, then benchmarks"
    return stack(
        f'<div class="table-scroll" tabindex="0" role="region" aria-label="Table of the {name}, scrollable">'
        f'<table class="table comparison stacked"><caption class="visually-hidden">{caption}</caption>'
        f'<thead>{head}</thead>{body}</table></div>',
        labels,
    )


def _latest(perp: dict[str, Any], title: str = "Latest AI decisions") -> str:
    """Each AI's latest decision: what it did and why, as a card; the detail folded."""
    items = []
    for p in perp["portfolios"]:
        if p["kind"] not in ("llm", "council"):
            continue
        d = next((x for x in p["decisions"] if x["status"] in ("decided", "failure", "skipped")), None)
        link = f'<a class="last-name" href="{_folder(p)}/{e(p["slug"])}.html">{e(p["name"])}</a>'
        if d is None:
            items.append(f'<li class="decision card-dec"><article><p class="dec-head">{link}</p><p class="dec-what muted">No decision yet</p></article></li>')
            continue
        items.append(_decision(d, who=link))
    if not items:
        return ""
    return (
        f'<section aria-labelledby="title-latest"><h2 id="title-latest">{title}</h2>'
        f'<ul class="decisions latest cards">{"".join(items)}</ul></section>'
    )


def _summary_line(d: dict[str, Any]) -> str:
    if d["status"] == "skipped":
        return f"Round skipped: {d['jump']}"
    if d["status"] == "failure":
        return f"No decision ({d['error']})"
    placed = _placed_summary(d)
    if not d["actions"] and placed:
        return f"No orders, {placed}"
    return _actions_summary(d["actions"]) + (f", {placed}" if placed else "")


def _statement(data: dict[str, Any], perp: dict[str, Any], direct_pfs: list[dict[str, Any]], extra: str = "") -> str:
    items = [f'<li>Next scheduled round <time datetime="{iso(perp["next_scheduled_round_ts"])}">{hour(perp["next_scheduled_round_ts"])}</time></li>']
    if perp["live_ts"]:
        live = data["generated_ts"] - perp["live_ts"] <= 1_800
        word = "Live values" if live else "Latest values from"
        when_txt = hour(perp["live_ts"]) if live else when(perp["live_ts"], year=False)
        items.append(f'<li><span data-direct-word>{word}</span> <time datetime="{iso(perp["live_ts"])}">{e(when_txt)}</time></li>')
        if direct_pfs:
            items.append('<li class="direct-status" data-direct-status data-short hidden></li>')
    if perp["journal"]["verify_ok"]:
        items.append('<li><a href="method.html#m-derivatives">Journal verified</a></li>')
    else:
        items.append('<li class="loss-txt">Journal: verification failed</li>')
    return f'<ul class="statement">{extra}{"".join(items)}</ul>'


def _reading_guide(councils: bool) -> str:
    if councils:
        items = (
            f"<li><strong>Council</strong>: several AIs that deliberate before a president decides. {e(P.COUNCIL_OUTSIDE_RULE)}</li>"
            "<li><strong>Benchmark</strong>: the 1x basket (buy and hold, no AI) is the reference; it is also in the solo AIs league.</li>"
            "<li><strong>Long, short</strong>: betting on a rise, on a decline.</li>"
            "<li><strong>Leverage</strong>: amount committed divided by the portfolio's value. At most 10 for a council.</li>"
        )
    else:
        items = (
            "<li><strong>Benchmark</strong>: a fixed rule, no AI. The 1x basket (buy and hold) is the reference: a useful AI must do better, fees included.</li>"
            "<li><strong>Long, short</strong>: betting on a rise, on a decline.</li>"
            "<li><strong>Leverage</strong>: amount committed divided by the portfolio's value. At most 2.</li>"
            f"<li><strong>Frozen</strong>: no new openings for 24{NBSP}h after a 5% loss in one day.</li>"
        )
    return f'<details class="reading"><summary>How to read this table</summary><ul class="list-simple">{items}</ul></details>'


def index_page(data: dict[str, Any]) -> str:
    """The solo AIs league (derivatives), on derivatives.html: ranking and curve on the first screen."""
    from arena.site import home as A

    perp = data["perp"]
    pfs = perp["portfolios"]
    all_llms = [p for p in pfs if p["kind"] == "llm"]
    llms = [p for p in all_llms if not p.get("archive")]  # archived ones no longer play: they are no longer counted
    archives = [p for p in all_llms if p.get("archive")]
    capital = pfs[0]["capital_ueur"] if pfs else 1_000_000_000
    n_bench = len(pfs) - len(all_llms)
    direct_pfs = [p for p in pfs if _direct_pf(p)]
    names = [short_name(p["name"]).replace("Claude ", "") for p in llms]
    if llms:
        who = "Claude AI trades" if len(llms) == 1 else "Claude AIs each trade"
        title = f"{_number(len(llms))} {who} {eur(capital, decimals=0)} of play money in crypto contracts, betting on rises and declines alike."
        lead = (
            f"{e(_join_and(names))} each decide alone, several times an hour, with leverage of 2 at most, "
            f"on real Kraken prices. {_number(n_bench)} fixed rules without AI serve as benchmarks; the reference is the basket, bought and held."
        )
        if archives:
            arch_names = _join_and([short_name(p["name"]).replace("Claude ", "") for p in archives])
            lead += f" {e(arch_names)}, archived, {'remain' if len(archives) > 1 else 'remains'} dotted."
    else:
        title = f"Claude AIs each trade {eur(capital, decimals=0)} of play money in crypto contracts."
        lead = f"Benchmarks only for now; the AIs join at the {hour(perp['next_scheduled_round_ts'])} scheduled round."
    other = ""
    if perp.get("councils"):
        other = '<li><a href="councils.html">See also the councils league</a></li>'
    body = A.front_section(
        title=title, lead=lead,
        ranking=A.scores(A._perp_rows(perp), label="Solo AIs league ranking, net return"),
        after=_statement(data, perp, direct_pfs),
        curve=_chart_block(perp["chart"]) + _archives(all_llms),
    ) + f"""
{_latest(perp)}
<section aria-labelledby="title-comparison">
  <h2 id="title-comparison">All portfolios <span class="h-note">fees and funding included</span></h2>
  {_table(perp)}
  {_reading_guide(False)}
</section>
{news_block(perp)}
<ul class="other-leagues">{other}<li><a href="spot.html">See also the spot league</a></li></ul>
"""
    ch = perp["chart"]
    return layout(
        title="Solo AIs", body=body, root="", active="derivatives", data=data, league="perp", path="derivatives.html",
        complete_title=f"Solo AIs league: {_number(len(llms)).lower()} Claude AI{'s' if len(llms) > 1 else ''} trade play money" if llms else "Solo AIs league",
        desc=f"{_join_and(names) if names else 'Haiku, Sonnet, Opus and Fable'} each trade {eur(capital, decimals=0)} of play money in crypto contracts, simulated on Kraken prices, against strategies without AI. Ranking and explained decisions.",
        scripts=(_chart_scripts("", ch, None, last="Latest snapshot") if curve_visible(ch) else "") + _direct_scripts("", perp, direct_pfs),
        direct=bool(direct_pfs),
    )  # fmt: skip


def _desc_pf(p: dict[str, Any]) -> str:
    """Meta description of a portfolio page: who, what, its return, in simulation."""
    who = {"council": "A council of ten Claude Haiku AIs and a president", "llm": "A single Claude AI"}.get(p["kind"], "A fixed rule without AI, a benchmark")
    if p["kind"] == "robot":
        who = "A robot without AI that plays the rebound after a wick of more than 4.5%"
    if p["id"] == P.COUNCIL_TREND:
        who = "A trend engine that three Claude Haiku AIs and an Opus president can only brake"
    return (
        f"{p['name']}: {who[:1].lower() + who[1:]}, {eur(p['capital_ueur'], decimals=0)} of play money in crypto contracts on Kraken prices. "
        f"Net return {pct(p['net_return'])}, every decision explained. Simulation."
    )


def _number(n: int) -> str:
    return {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six"}.get(n, str(n))


def _join_and(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _experiment(councils: list[dict[str, Any]]) -> str:
    """What the league measures, in two sentences."""
    if len(councils) >= 2:
        return (
            "Two councils play the same rounds on the same markets, with the same ten Haiku advisers, the same instructions and the same aggressive policy. "
            "Only the President changes, Haiku for one and Opus for the other: the league measures what a more expensive President changes in the result."
        )
    return (
        "The Haiku council plays alone for now; the Opus council joins it at deployment. "
        "They will have the same ten Haiku advisers, the same instructions and the same policy: only the President will change, Haiku or Opus."
    )


def _archives(pfs: list[dict[str, Any]]) -> str:
    """Portfolios withdrawn from the league: their data stays, their curve is dotted and stops at the withdrawal."""
    arch = [p for p in pfs if p.get("archive")]
    if not arch:
        return ""
    names = _join_and([f"{p['name']} (on {short_date(p['archive']['ts'])})" for p in arch])
    what = "archived councils" if all(p["kind"] == "council" for p in arch) else "archived portfolios"
    return (
        f'<p class="arrival">Dotted curves: {what}, withdrawn from the league with their positions closed. '
        f"Their return is frozen at their withdrawal: {e(names)}.</p>"
    )


def _arrivals(pfs: list[dict[str, Any]]) -> str:
    """A portfolio that entered after the others: its curve starts at its arrival, and the page says so under the chart."""
    if len(pfs) < 2:
        return ""
    start = min(p["open_ts"] for p in pfs)
    latecomers = [p for p in pfs if p["open_ts"] - start > 3_600 and not p.get("archive")]
    return "".join(
        f'<p class="arrival">{e(p["name"])} joined the league on {stamp(p["open_ts"], year=False)}: its curve starts there.</p>'
        for p in latecomers
    )


def _trend_steps() -> str:
    return """
<section class="steps" aria-labelledby="title-steps">
  <h2 id="title-steps">How the Trend council decides</h2>
  <ol class="steps-list">
  <li><span class="step-num">1</span><p><strong>The engine decides.</strong> At each 4-hour bar close (00:00, 04:00, 08:00… UTC), it gives the target for each contract: long, short or flat, with a size scaled to volatility.</p></li>
  <li><span class="step-num">2</span><p><strong>The AIs can brake.</strong> Three Haiku (news, data, risk) advise, an Opus President sets a coefficient of 1, 0.5 or 0 per contract. It can neither increase, nor invert, nor open: without an opinion, the engine plays alone.</p></li>
  <li><span class="step-num">3</span><p><strong>The code executes</strong> the gap between target and position, only if it exceeds 5% of the portfolio, with a 5% stop. The guardrail can reject; the order is then reduced until it passes.</p></li>
  </ol>
</section>"""


def councils_page(data: dict[str, Any]) -> str:
    """Home page of the councils league: the sentence, the ranking and the curve, then the latest decisions in plain
    words; the full table, the news and the method come after."""
    from arena.site import home as A

    perp = data["perp"]["councils"]
    pfs = perp["portfolios"]
    councils = [p for p in pfs if p["kind"] == "council"]
    capital = pfs[0]["capital_ueur"] if pfs else 1_000_000_000
    direct_pfs = [p for p in pfs if _direct_pf(p)]
    n = len(councils)
    trend = any(p["id"] == P.COUNCIL_TREND for p in councils)
    if trend:
        title = f"A council of Claude AIs brakes a trend engine: {eur(capital, decimals=0)} of play money."
        lead = (
            "A trend-following engine decides each position every 4 hours; three Claude Haiku and an Opus President "
            "can only brake it (a coefficient of 1, 0.5 or 0 per contract). Fixed target: 1% per day; the realized "
            "return is shown next to it, against an “engine alone” benchmark without AI. On the chart, this benchmark is the gray ribbon "
            "under the council's line: as long as the council brakes nothing, the two coincide."
        ) + (
            " The former Haiku and Opus councils, withdrawn on Nov 17, remain archived: their curve is dotted."
            if any(p["id"] != P.COUNCIL_TREND for p in councils) else ""
        )
    elif n >= 2:
        title = f"{_number(n)} Claude AI councils each trade {eur(capital, decimals=0)} of play money. Only their president changes."
        lead = (
            "Ten Claude Haiku advisers give their opinion on crypto contracts, several times an hour; "
            "a president decides: Haiku for one, Opus for the other. Aggressive mandate (leverage up to 10, goal: double the stake), "
            "simulated on real Kraken prices, against a benchmark without AI."
        )
    else:
        title = f"A Claude AI council trades {eur(capital, decimals=0)} of play money."
        lead = e(_experiment(councils))
    body = A.front_section(
        title=title, lead=lead,
        ranking=A.scores(A._perp_rows(perp), label="Councils league ranking, net return"),
        after=_statement(data, perp, direct_pfs),
        curve=_chart_block(perp["chart"], league="councils") + _arrivals(councils) + _archives(councils),
    ) + (_trend_steps() if trend else "") + ("" if trend else """
<section class="steps" aria-labelledby="title-steps">
  <h2 id="title-steps">How a council decides</h2>
  <ol class="steps-list">
  <li><span class="step-num">1</span><p><strong>Nine opinions, without seeing each other.</strong> Each Haiku adviser has a role (trend, breakouts, order book, risk…) and says rise, decline or nothing, contract by contract.</p></li>
  <li><span class="step-num">2</span><p><strong>The Devil's Advocate</strong> reads these opinions and attacks the best-supported bet.</p></li>
  <li><span class="step-num">3</span><p><strong>The president decides</strong> and places the orders. An automatic guardrail can reject them.</p></li>
  </ol>
</section>""") + f"""
{_latest(perp, "What they just decided")}
<section aria-labelledby="title-comparison">
  <h2 id="title-comparison">Portfolio details <span class="h-note">fees and funding included</span></h2>
  {_table(perp, councils=True)}
  {_reading_guide(True)}
</section>
{news_block(perp)}
<details class="reading method-folded" id="m-councils-folded"><summary>Council rules: leverage, stops, budget</summary>
{councils_method(data)}
</details>
<ul class="other-leagues"><li><a href="derivatives.html">See also the solo AIs</a></li><li><a href="spot.html">See also the spot league</a></li></ul>
"""
    ch = perp["chart"]
    return layout(
        title="AI councils", body=body, root="", active="councils", data=data, league="councils", path="councils.html",
        image="preview-councils.png",
        complete_title=(
            "A council of Claude AIs brakes a trend engine, with play money"
            if trend else "Two Claude AI councils trade play money: Haiku or Opus as president?"
        ),
        desc=(
            "A trend engine decides, three Claude Haiku and an Opus president can only brake it: €1,000 of play money on real Kraken prices, against an engine-alone benchmark. Live ranking, every decision explained."
            if trend else "Ten Claude Haiku deliberate, a Haiku or Opus president decides: two AI councils trade €1,000 of play money each on real Kraken prices. Live ranking, every decision explained."
        ),
        scripts=(_chart_scripts("", ch, None, last="Latest snapshot") if curve_visible(ch) else "") + _direct_scripts("", perp, direct_pfs),
        direct=bool(direct_pfs),
    )  # fmt: skip


# ---------------------------------------------------------------------------
# A portfolio's page
# ---------------------------------------------------------------------------


def _positions(p: dict[str, Any]) -> str:
    if not p["positions"]:
        return f'<p class="empty">No open position. Equity: {eur(p["equity_ueur"])}.</p>'
    has_stop = any(x["stop_uusd"] for x in p["positions"])
    has_target = any(x["target_uusd"] for x in p["positions"])
    rows = "".join(
        f'<tr><th scope="row">{e(x["instrument"])}</th><td><span class="side side-{x["side"]}">{x["side"]}</span></td>'
        f'<td class="n">{eur(x["notional_ueur"])}<small class="sub">{e(quantity(x["qty"]))} {e(x["instrument"])}</small></td>'
        f'<td class="n">{price_usd(x["entry_uusd"])}</td><td class="n"><span{_live_attrs(p, "mark", x)}>{price_usd(x["mark_uusd"])}</span></td>'
        + (f'<td class="n">{price_usd(x["stop_uusd"])}</td>' if has_stop else "")
        + (f'<td class="n">{price_usd(x["target_uusd"])}</td>' if has_target else "")
        + f'<td class="n"><span class="{tone(x["latent_ueur"])}"{_live_attrs(p, "lat", x)}>{eur(x["latent_ueur"], signed=True)}</span></td></tr>'
        for x in p["positions"]
    )
    return stack(
        '<div class="table-scroll" tabindex="0" role="region" aria-label="Positions table, scrollable"><table class="table stacked">'
        '<caption class="visually-hidden">Open positions, prices in dollars, values in euros</caption>'
        '<thead><tr><th scope="col">Contract</th><th scope="col">Side</th><th scope="col" class="n">Exposure</th>'
        '<th scope="col" class="n">Entry</th><th scope="col" class="n">Current price</th>'
        + ('<th scope="col" class="n">Stop</th>' if has_stop else "")
        + ('<th scope="col" class="n">Target</th>' if has_target else "")
        + '<th scope="col" class="n">Unrealized P&amp;L</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>",
        ["Side", "Exposure", "Entry", "Current price"] + (["Stop"] if has_stop else []) + (["Target"] if has_target else []) + ["Unrealized P&L"],
    )


def _intent(a: dict[str, Any]) -> str:
    if not a.get("action"):
        return '<span class="muted">invalid action, discarded</span>'
    parts = [f"<strong>{e(P.ACTIONS.get(a['action'], a['action']))}</strong>"]
    if a.get("size_pct") is not None:
        parts.append(f"{pc(a['size_pct'])} {'of the portfolio' if a['action'].startswith('open') else 'of the position'}")
    if a.get("stop_pct") is not None:
        parts.append(f"stop {pc(a['stop_pct'])}")
    if a.get("target_pct") is not None:
        parts.append(f"target {pc(a['target_pct'])}")
    if a.get("horizon_h"):
        parts.append(f"{a['horizon_h']} h")
    if a.get("confidence_pct") is not None:
        parts.append(f"confidence {pc(a['confidence_pct'])}")
    txt = " · ".join(parts)
    if a.get("invalidation"):
        txt += f'<span class="invalidation">Invalid if: {e(a["invalidation"])}</span>'
    if a.get("discarded"):
        txt += '<span class="muted"> · discarded (invalid)</span>'
    return txt


def _guardrail(a: dict[str, Any], codes: dict[str, str] = P.CODES) -> str:
    v = a.get("verdict")
    if v is None:
        return '<span class="pill neutral">no verdict</span>'
    if v["approved"]:
        return '<span class="pill ok">accepted</span>'
    reason_list = "".join(f'<span class="code">{e(codes.get(c, "unknown rule"))}</span>' for c in v["reason_list"])
    return f'<span class="pill loss-bg">rejected</span><span class="codes">{reason_list}</span>'


def _execution(a: dict[str, Any]) -> str:
    st = a.get("execution")
    if a["fills"]:
        out = "".join(
            f'<span class="exec">{"buy" if f["qty"] > 0 else "sell"} {e(quantity(f["qty"]))} {e(a["instrument"])} at {price_usd(f["price_uusd"])}'
            f'<small class="sub">fees {eur(f["fees_ueur"], decimals=4)}</small></span>'
            for f in a["fills"]
        )
        if st and st != "filled":
            out += f'<span class="muted exec-note">{e(P.EXECUTIONS.get(st, st))}</span>'
        return out
    if st:
        return f'<span class="muted">{e(P.EXECUTIONS.get(st, st))}</span>'
    return '<span class="muted">not executed</span>'


def _actions(d: dict[str, Any]) -> str:
    rows = "".join(
        f'<tr><th scope="row">{e(a["instrument"])}</th><td>{_intent(a)}</td><td>{_guardrail(a, _codes(d))}</td><td class="n">{_execution(a)}</td></tr>'
        for a in d["actions"]
    )
    return stack(
        f'<div class="table-scroll actions-scroll" tabindex="0" role="region" aria-label="Actions of {e(when(d["ts"]))}, scrollable">'
        '<table class="table actions stacked"><thead><tr><th scope="col">Contract</th><th scope="col">Intent</th>'
        '<th scope="col">Guardrail</th><th scope="col" class="n">Execution</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>",
        ["Intent", "Guardrail", "Execution"],
    )


def _president(d: dict[str, Any]) -> str:
    """"President · Opus": the President's model, discreet (nothing if the journal does not say)."""
    m = (d.get("council") or {}).get("president")
    return f' <span class="model-president">President · {e(m)}</span>' if m else ""


def _rationale(d: dict[str, Any]) -> str:
    out = ""
    if d.get("justification"):
        who = "Step C · the President decides" if d.get("council") else "Model reasoning"
        out += f'<blockquote class="rationale"><span class="label">{who}{_president(d)}</span>{e(d["justification"])}</blockquote>'
    if d.get("tools"):
        out += f'<p class="tools"><span class="label">Consulted</span>{_tools_txt(d["tools"])}</p>'
    return out


# ---------------------------------------------------------------------------
# A council's deliberation: step A (opinions without seeing each other), B (the Devil's Advocate), C (the President: the decision)
# ---------------------------------------------------------------------------

def _tools_txt(tools: list[dict[str, Any]]) -> str:
    return ", ".join(
        f'{e(SHORT_TOOLS.get(o["tool"], o["tool"]))}{(" " + e(o["args"])) if o["args"] else ""}{" (error)" if o["error"] else ""}'
        for o in tools
    )


def _opinions_line(x: dict[str, Any]) -> str:
    """"short ETH · conviction 60 · 250% · stop 2.5% · key level $1,894.00"."""
    parts = [f'<span class="side side-{x["position"]}">{x["position"]}</span> <strong>{e(x["instrument"])}</strong>']
    if x.get("conviction") is not None:
        parts.append(f'conviction {x["conviction"]}')
    if x["position"] != "flat":
        if x.get("size_pct") is not None:
            parts.append(pc(x["size_pct"]))
        if x.get("stop_pct") is not None:
            parts.append(f"stop {pc(x['stop_pct'])}")
    if x.get("level_uusd") is not None:
        parts.append(f"key level {price_usd(x['level_uusd'])}")
    return " · ".join(parts)


def _member(a: dict[str, Any]) -> str:
    role = f'<span class="role">{e(a["role"])}</span>' if a.get("role") else ""
    head = f'<p class="member-head"><strong>{e(a["name"])}</strong>{role}</p>'
    if a["absent"]:
        return f'<li class="member absent">{head}<p class="muted"><span class="pill neutral">absent</span> {e(a["error"] or "call failed")}</p></li>'
    target = ""
    if a.get("target"):
        target = f'<p class="target"><span class="label">Attacks</span>the {e(a["target"]["side"])} {e(a["target"]["instrument"])}</p>'
    if "proposals" in a:  # an adviser of the Trend council: brakes, not market opinions
        opinions = "".join(
            f"<li><strong>{e(x['instrument'])}</strong> ×{e(x['coefficient'] or '?')}"
            + (f" · {e(x['reason'])}" if x.get("reason") else "")
            + "</li>"
            for x in a["proposals"]
        ) or '<li class="muted">no braking proposed</li>'
    else:
        opinions = "".join(f"<li>{_opinions_line(x)}</li>" for x in a["opinions"]) or '<li class="muted">no position advised</li>'
    arg = f'<p class="argument">{e(a["argument"])}</p>' if a.get("argument") else ""
    tools = f'<p class="tools"><span class="label">Consulted</span>{_tools_txt(a["tools"])}</p>' if a.get("tools") else ""
    return f'<li class="member">{head}{target}<ul class="opinions-positions">{opinions}</ul>{arg}{tools}</li>'


def _opinion_lean(opinions: list[dict[str, Any]]) -> str:
    """Where the step A opinions lean: "short ETH ×5, short SOL ×2, flat ×1" (a member counts once per idea)."""
    from collections import Counter

    c: Counter[str] = Counter()
    for a in opinions:
        if a["absent"] or a["step"] != "A":
            continue
        ideas = {f'{x["position"]} {x["instrument"]}' for x in a["opinions"] if x["position"] != "flat"}
        c.update(ideas or {"flat"})
    return ", ".join(f"{k} ×{n}" for k, n in c.most_common(3))


DETAILED_OPINIONS = 12  # on a council page, the full opinions of the last 12 rounds; before that, the summary only
_SUMMARY_ONLY: set[int] = set()  # id() of the decisions whose page only shows the deliberation summary


def _deliberation(d: dict[str, Any]) -> str:
    c = d.get("council")
    if not c:
        return ""
    if c.get("opinions_outside_page"):
        return f'<p class="tools muted"><span class="label">Deliberation</span>{plural(c["opinions_outside_page"], "opinion")}, kept in the journal (the page shows those of the last {P.DELIBERATIONS_MAX} rounds).</p>'
    if not c.get("opinions"):
        return ""
    a_opinions = [a for a in c["opinions"] if a["step"] == "A"]
    b_opinions = [a for a in c["opinions"] if a["step"] != "A"]
    n_ok = sum(1 for a in c["opinions"] if not a["absent"])
    n_abs = len(c["opinions"]) - n_ok
    words = [plural(n_ok, "opinion")]
    if n_abs:
        words.append(plural(n_abs, "absent", "absent"))
    t = _opinion_lean(c["opinions"])
    if t:
        words.append(t)
    advocate = next((a for a in b_opinions if a.get("target")), None)
    if advocate:
        words.append(f"the Devil's Advocate attacks the {advocate['target']['side']} {advocate['target']['instrument']}")
    summary = f'<span class="label">Deliberation</span><span class="muted">{e(" · ".join(words))}</span>'
    if id(d) in _SUMMARY_ONLY:  # light page: the detail of the older opinions stays in the journal and data/councils.json
        return f'<p class="tools">{summary}<span class="muted"> · full opinions in the journal and <code>data/councils.json</code></span></p>'
    body = ""
    if a_opinions:
        n_a_abs = sum(1 for a in a_opinions if a["absent"])
        note_a = "without seeing each other" + (f" · {plural(n_a_abs, 'absent', 'absent')}" if n_a_abs else "")
        body += f'<h4 class="step">Step A · {plural(len(a_opinions) - n_a_abs, "independent opinion")}<span class="h-note">{note_a}</span></h4><ol class="opinions">{"".join(_member(a) for a in a_opinions)}</ol>'
    if b_opinions:
        body += f'<h4 class="step">Step B · the Devil’s Advocate<span class="h-note">read step A</span></h4><ol class="opinions">{"".join(_member(a) for a in b_opinions)}</ol>'
    body += f'<p class="step step-c">Step C · the President read the opinions and decides below.{_president(d)}</p>'
    sheet = [x for x in (f"advisers {c['model_members']}" if c.get("model_members") else "", f"instructions {c['instructions']}" if c.get("instructions") else "") if x]
    if sheet:
        sheet_line = " · ".join(sheet)
        sheet_line = sheet_line[:1].upper() + sheet_line[1:]
        body += f'<p class="muted sheet-council">{e(sheet_line)}</p>'
    return f'<details class="deliberation"><summary>{summary}</summary>{body}</details>'


def _meta(d: dict[str, Any]) -> str:
    meta = []
    if d.get("cost_uusd"):
        meta.append(usd(d["cost_uusd"]))
        c = d.get("council") or {}
        if c.get("chair_cost_uusd") and c.get("president") not in (None, "Haiku"):  # a more expensive President weighs most
            meta[-1] += f" incl. President {usd(c['chair_cost_uusd'])}"
    return f'<span class="decision-meta">{" · ".join(meta)}</span>' if meta else ""


def _detail_label(d: dict[str, Any]) -> str:
    """What the fold hides: "President's reasoning, 10 opinions, orders and execution"."""
    words = []
    c = d.get("council") or {}
    if d.get("justification"):
        words.append("President's reasoning" if c else "full reasoning")
    if c.get("opinions"):
        words.append(plural(len(c["opinions"]), "opinion"))
    if d.get("actions"):
        words.append("orders and execution")
    elif (d.get("placed") or {}).get("elements"):
        words.append("prepared orders and alerts")
    return _capitalize_first(", ".join(words)) if words else "Details"


def _capitalize_first(s: str) -> str:
    return s[:1].upper() + s[1:]


def _pct_sign(v: float) -> str:
    return f"{'+' if v > 0 else (MINUS if v < 0 else '')}{abs(round(v)):.0f}%"


def _engine_line(d: dict[str, Any]) -> str:
    """A Trend council round's line: the engine's targets, the council's coefficients with their reason, the orders
    placed. Nothing for the other portfolios."""
    t = d.get("trend")
    if not t:
        return ""
    targets = ", ".join(f"{e(i)} {_pct_sign(v)}" for i, v in t["targets_pct"].items()) or "no target"
    incomplete = f" · incomplete data, position kept: {e(', '.join(t['incomplete_data']))}" if t.get("incomplete_data") else ""
    lines = [f'<p class="dec-engine"><span class="label">Engine targets</span>{targets}{incomplete}</p>']
    if t["coefficients"]:
        coefs = "; ".join(
            f"{e(i)} ×{e(c['coefficient'])}" + (f" ({e(c['reason'])})" if c.get("reason") else "")
            for i, c in t["coefficients"].items()
        )
    elif t.get("council_absent"):
        coefs = f"engine alone ({e(t['council_absent'])})"
    elif t["council_called"] and not t["president_ok"]:
        coefs = "engine alone (the President returned no decision)"
    else:
        coefs = "no brake: follow the engine"
    lines.append(f'<p class="dec-engine"><span class="label">Council coefficients</span>{coefs}</p>')
    orders = []
    for a in d.get("actions") or []:
        if a.get("discarded") or not a.get("action"):
            continue
        txt = f"{P.ACTIONS.get(a['action'], a['action']).lower()} {e(a['instrument'])}"
        if a.get("size_pct") is not None:
            txt += f" {pc(a['size_pct'])}"
        v = a.get("verdict")
        if v is not None and not v.get("approved"):
            txt += " (rejected)"
        elif a.get("reduced"):
            txt += f" (reduced {a['reduced']} times to pass the guardrail)"
        orders.append(txt)
    lines.append(f'<p class="dec-engine"><span class="label">Orders</span>{"; ".join(orders) if orders else "none: all gaps are within the 5% band"}</p>')
    return "".join(lines)


def _decision(d: dict[str, Any], *, who: str = "") -> str:
    """A decision as a card: what was decided and why, one line each; the technical detail folded."""
    llm_round = _round_pill(d)
    head = f'<p class="dec-head">{who}<span class="when">{stamp(d["ts"], year=False)}</span>{llm_round}{_meta(d)}</p>'
    what = L.what(d)
    calm = d["status"] == "decided" and not d["actions"] and d["kind"] != "order"
    class_ = "decision card-dec" + (" calm" if calm else "") + (" failed" if d["status"] in ("skipped", "failure") else "")
    body = f'<p class="dec-what">{e(what)}</p>' + _engine_line(d)
    why = L.why(d)
    if why:
        body += f'<p class="dec-why"><span class="dec-word">{e(why[0])}</span> {e(why[1])}</p>'
    body += L.vote_html(d)
    if d["status"] == "failure" and d.get("error"):
        body += f'<p class="dec-why muted">{e(d["error"])}</p>'
    detail = _deliberation(d) + _rationale(d) + (_actions(d) if d["actions"] else "") + _placed(d)
    if detail:
        body += f'<details class="dec-detail"><summary>{e(_detail_label(d))}</summary><div class="decision-stack">{detail}</div></details>'
    return f'<li class="{class_}"><article>{head}{body}</article></li>'


GROUP_MIN = 3  # from 3 calm decisions in a row, a single folded line


def _calm(d: dict[str, Any]) -> bool:
    """A decision without orders (no failure, no skip): the usual case of regular calls."""
    return d["status"] == "decided" and not d["actions"] and d["kind"] != "order"


def _grouped_decisions(ds: list[dict[str, Any]]) -> str:
    """The timeline, where each run of at least GROUP_MIN decisions without orders fits on one expandable line."""
    out, i = [], 0
    while i < len(ds):
        j = i
        while j < len(ds) and _calm(ds[j]):
            j += 1
        if j - i >= GROUP_MIN:
            run = ds[i:j]
            placed_count = sum(1 for d in run if (d.get("placed") or {}).get("elements"))
            note = f" · {placed_count} with alerts or orders set" if placed_count else ""
            summary = (
                f'<span class="when">{stamp(run[-1]["ts"], year=False)} → {hour(run[0]["ts"])}</span>'
                f'<span class="muted">{plural(len(run), "decision without orders", "decisions without orders")}{e(note)}</span>'
            )
            out.append(f'<li class="line group-calm"><details><summary>{summary}</summary><ol class="decisions">{"".join(_decision(d) for d in run)}</ol></details></li>')
            i = j
        elif j > i:
            out.extend(_decision(d) for d in ds[i:j])
            i = j
        else:
            out.append(_decision(ds[i]))
            i += 1
    return "".join(out)


def _pending(p: dict[str, Any]) -> str:
    """Pending alerts and entry orders, then what became of the previous ones (folded)."""
    pending = p.get("pending")
    if not pending:
        return ""
    in_progress = pending["alerts"] + pending["orders"]
    pace = p.get("pace") or {}
    lines = []
    if pace.get("wakeup_ts"):
        lines.append(f'<li class="line"><span class="el"><strong>Recall</strong> it requested</span><span class="muted">at {hour(pace["wakeup_ts"])}</span></li>')
    if pace.get("next_ts"):
        lines.append(
            f'<li class="line"><span class="el"><strong>Regular call</strong> <span class="muted">at least every {pace["cadence_min"]} min</span></span>'
            f'<span class="muted">at the latest at {hour(pace["next_ts"])}</span></li>'
        )
    if in_progress or lines:
        body = '<ul class="decisions pending">' + "".join(lines) + "".join(
            f'<li class="line"><span class="el">{element(x)}</span><span class="muted">until {stamp(x["expire_ts"], year=False) if x.get("expire_ts") else "—"}</span></li>'
            for x in in_progress
        ) + "</ul>"
    else:
        body = '<p class="empty empty-short">Nothing pending.</p>'
    history_html = ""
    if pending["history"]:
        def issue(x: dict[str, Any]) -> str:
            if x["issue"] == "fired":
                word = "triggered"
                detail = f" · {x['issue_detail']}" if x.get("issue_detail") else ""
                return f'<span class="issue"><span class="pill ok">{word}</span><span class="muted">{e(detail)}</span></span>'
            return f'<span class="issue"><span class="pill neutral">{e(x.get("issue_detail") or "ended")}</span></span>'

        rows = "".join(
            f'<li class="line"><span class="el">{element(x)}</span>{issue(x)}<span class="muted">{stamp(x["ts"], year=False)}</span></li>' for x in pending["history"]
        )
        history_html = f'<details class="reading previous"><summary>Previous ones</summary><ul class="decisions pending">{rows}</ul></details>'
    return (
        '<section aria-labelledby="title-pending"><h2 id="title-pending">Pending <span class="h-note">next call, alerts and entry orders</span></h2>'
        f"{body}{history_html}</section>"
    )


def _operations(p: dict[str, Any]) -> str:
    if not p["operations"]:
        return '<p class="empty">No operations yet.</p>'
    reason = any(o["reason"] != P.FILL_REASONS["intent"] for o in p["operations"])
    rows = "".join(
        f'<tr><td>{stamp(o["ts"], year=False)}</td><th scope="row">{e(o["instrument"])}</th>'
        f'<td>{"buy" if o["qty"] > 0 else "sell"} {e(quantity(o["qty"]))}</td><td class="n">{price_usd(o["price_uusd"])}</td>'
        f'<td class="n">{eur(o["fees_ueur"], decimals=4)}</td>'
        + (f'<td>{e(o["reason"])}</td>' if reason else "") + "</tr>"
        for o in p["operations"]
    )
    remaining = p["n_operations"] - len(p["operations"])
    more = f'<p class="muted">+{plural(remaining, "older operation")} in the journal.</p>' if remaining > 0 else ""
    return stack(
        '<div class="table-scroll" tabindex="0" role="region" aria-label="Operations table, scrollable"><table class="table stacked">'
        '<caption class="visually-hidden">Executed operations, newest first</caption>'
        '<thead><tr><th scope="col">When</th><th scope="col">Contract</th><th scope="col">Order</th><th scope="col" class="n">Price</th>'
        '<th scope="col" class="n">Fees</th>' + ('<th scope="col">Reason</th>' if reason else "") + "</tr></thead>"
        f"<tbody>{rows}</tbody></table></div>{more}",
        ["When", "Order", "Price", "Fees"] + (["Reason"] if reason else []),
    )


def _daily_target(p: dict[str, Any]) -> str:
    """"target: 1%/day · realized: 0.4%/day": side by side and unvarnished (Trend council and its benchmark)."""
    o = p.get("daily_target")
    if not o:
        return ""
    realized = f"{o['realized_pct']:+.2f}".replace("-", MINUS)
    return (
        f'<p class="daily-goal">target: {o["target_pct"]}%/day · realized: {realized}%/day '
        f'<span class="muted">(compound daily rate since opening, {o["days"]} days)</span></p>'
    )


def portfolio_page(data: dict[str, Any], p: dict[str, Any]) -> str:
    council = p["kind"] == "council"
    councils_league = council or p["id"] == P.TREND_ENGINE  # the "engine alone" benchmark lives in the councils league
    _SUMMARY_ONLY.clear()
    with_opinions = [d for d in p.get("decisions") or [] if (d.get("council") or {}).get("opinions")]
    _SUMMARY_ONLY.update(id(d) for d in with_opinions[DETAILED_OPINIONS:])
    llm = p["kind"] == "llm" or council  # a council decides like an AI: decisions, pending, cost
    stats = [
        _stat("Net return", f'<span class="{tone(p["net_return"])}"{_live_attrs(p, "ret")}>{pct(p["net_return"])}</span>', cls="large", card="key"),
        _stat(
            "Value", f'<span{_live_attrs(p, "val")}>{eur(p["equity_ueur"])}</span>',
            f'<small class="sub">start {eur(p["capital_ueur"], decimals=0)}{f" · target {eur(2 * p['capital_ueur'], decimals=0)}" if council and p["id"] != P.COUNCIL_TREND else ""}</small>',
        ),
        _stat("Leverage", leverage(p["leverage"]), f'<small class="sub">exposure {eur(p["expo_ueur"], decimals=0)}</small>'),
        _stat("Worst drawdown", pct(-p["drawdown_max"]) if p["drawdown_max"] else "0.00%"),
        _stat(
            "Funding", _funding_cell(p),
            f'<small class="sub">paid {eur(p["funding_paid_ueur"])} · received {eur(p["funding_received_ueur"])}</small>'
            if p["funding_paid_ueur"] or p["funding_received_ueur"] else "",
        ),
        _stat("Fees", eur(p["fees_ueur"]), '<small class="sub">0.07% per order</small>'),
    ]  # fmt: skip
    if llm:
        if council:
            costly_president = p.get("president") not in (None, "Haiku") and p.get("chair_cost_uusd")
            cost_note = "actual cost of the rounds" + (f" · incl. President {usd(p['chair_cost_uusd'])}" if costly_president else "")
        else:
            cost_note = "API equivalent"
        stats.append(_stat("AI cost", usd(p["cost_uusd"]), f'<small class="sub">{cost_note}</small>'))
        q = (p.get("pace") or {}).get("quota")
        day = f'<small class="sub">{q["played_today"]} calls today, {q["per_day"]} at most</small>' if q else ""
        stats.append(_stat("Decisions", str(p["n_rounds"]), f'<small class="sub">{plural(p["n_orders"], "order executed", "orders executed")}</small>{day}'))
    else:
        stats.append(_stat("Positions", str(len(p["positions"])), '<small class="sub">open</small>'))
        stats.append(_stat("Operations", str(p["n_operations"])))
        if p["kind"] == "robot":
            stats.append(_stat("Shocks seen", str(p.get("n_shocks") or 0), '<small class="sub">wicks of more than 4.5%</small>'))
            stats.append(_stat("Trades", str(p.get("n_trades") or 0), '<small class="sub">entries executed</small>'))
    alerts = ""
    st = p.get("status")
    if p.get("archive"):
        solo = p["kind"] == "llm"
        alerts = (
            f'<p class="alert info"><strong>{"Archived AI" if solo else "Archived council"}</strong> on {stamp(p["archive"]["ts"])}. '
            "Its positions were closed at market; it no longer plays and its figures are frozen. "
            f"Its curve remains, dotted, in the {'solo AIs' if solo else 'councils'} league.</p>"
        )
    elif st and st["state"] == "stopped" and council:
        alerts = (
            f'<p class="alert loss-bg"><strong>Council stopped</strong> on {stamp(st["ts"]) if st.get("ts") else "—"}: ruin, drawdown of 90% from its peak. '
            "Its positions are closed and it no longer plays. Only the arena operator can restart it, by hand.</p>"
        )
    elif st and st["state"] == "stopped":
        threshold = 60 if p["kind"] == "robot" else 15
        alerts = f'<p class="alert loss-bg">Portfolio stopped: drawdown of {threshold}% from its peak, positions closed.</p>'
    elif st:
        until = f" until {stamp(st['until'])}" if st.get("until") else ""
        cause = " after a liquidation" if st.get("reason") == "margin_closeout" else ""
        alerts = f'<p class="alert warn">Portfolio frozen{cause}{until}: no new openings.</p>'
    perp = data["perp"]["councils"] if councils_league else data["perp"]  # the portfolio's league
    chart = _ref_chart(perp, p["id"])
    direct_pfs = [p] if _direct_pf(p) else []
    # The basket, the only other curve on the page, also follows the current price (it has no figure here).
    basket = next((x for x in perp["portfolios"] if x["id"] == P.BASKET and x is not p), None)
    if direct_pfs and curve_visible(chart) and basket and _direct_pf(basket):
        direct_pfs.append(basket)
    direct_state = '<p class="direct-status" data-direct-status hidden></p>' if direct_pfs else ""
    decs = _grouped_decisions(p["decisions"])
    if llm or p["id"] == P.RANDOM:
        empty = "No decision yet: the first arrives at the next scheduled round." if llm else "No draw yet."
        decs_html = f'<ol class="decisions">{decs}</ol>' if decs else f'<p class="empty">{empty}</p>'
        decisions = f'<section{" class=\"tint-2\"" if council and p["id"].endswith(":opus") else ""} aria-labelledby="title-decisions"><h2 id="title-decisions">Decisions <span class="h-note">newest first</span></h2>{decs_html}</section>'
        operations = (
            f'<section aria-labelledby="title-operations"><details class="reading"><summary><h2 id="title-operations" class="h2-inline">Operations</h2>'
            f' <span class="h-note">{plural(p["n_operations"], "operation")}</span></summary>{_operations(p)}</details></section>'
        )
    else:
        decisions = ""
        operations = f'<section aria-labelledby="title-operations"><h2 id="title-operations">Operations</h2>{_operations(p)}</section>'
    if councils_league:
        breadcrumb = '<a href="../councils.html"><span aria-hidden="true">← </span>Councils league</a>'
    else:
        breadcrumb = f'<a href="../derivatives.html"><span aria-hidden="true">← </span>Solo AIs league</a><span class="feed-sep" aria-hidden="true">/</span><span>{"AI models" if llm else "Benchmarks"}</span>'
    body = f"""
<p class="feed">{breadcrumb}</p>
<header class="head-model{" tint-2" if council and p["id"].endswith(":opus") else ""}">
  <h1>{e(p["name"])}</h1>
  {f'<p class="sub-title">{e(p["subtitle"])}</p>' if p.get("subtitle") else ""}
  {f'<p class="{"badge-robot" if p["kind"] == "robot" else "badge-council"}">{e(p["badge"])}</p>' if p.get("badge") else ""}
  {f'<p class="lead">{e(p["description"])}</p>' if p.get("description") else ""}
  {_daily_target(p)}
  {f'<p class="outside-rule">{e(p["outside_rule"])} <a href="../councils.html#m-councils">Its rules</a></p>' if p.get("outside_rule") else ""}
</header>
{alerts}
<dl class="stats">{"".join(stats)}</dl>
<section aria-labelledby="title-curve"><h2 id="title-curve">Net return <span class="h-note">fees and funding included</span></h2>{_chart_block(chart, focus=p["id"], focus_name=p["name"])}</section>
<section aria-labelledby="title-positions"><h2 id="title-positions">Positions <span class="h-note">simulated, prices in dollars</span></h2>{direct_state}{_positions(p)}</section>
{decisions}
{_pending(p) if llm and not p.get("archive") else ""}
{operations}
"""
    return layout(
        title=f"{p['name']} · {'councils' if councils_league else 'derivatives'}", body=body, root="../", active=p["id"], data=data,
        league="councils" if councils_league else "perp", path=f"{_folder(p)}/{p['slug']}.html",
        image="preview-councils.png" if councils_league else "preview.png",
        desc=_desc_pf(p),
        scripts=(_chart_scripts("../", chart, p["id"], last="Latest snapshot") if curve_visible(chart) else "") + _direct_scripts("../", perp, direct_pfs),
        direct=bool(direct_pfs),
    )  # fmt: skip


# ---------------------------------------------------------------------------
# Method
# ---------------------------------------------------------------------------


def method_section(data: dict[str, Any]) -> str:
    perp = data.get("perp")
    if not perp:
        return ""
    j = perp["journal"]
    ok = j["verify_ok"]
    tools = "".join(f"<li><strong>{e(k)}</strong>: {e(v)}</li>" for k, v in P.TOOLS.items())
    cad = perp.get("cadence_min") or 0
    cadence = f"<li><strong>Regular call</strong>: each AI is called again at the latest {cad} min after its last round.</li>\n" if cad else ""
    if perp.get("rounds_per_day"):
        cadence += f"<li><strong>Cap</strong>: {perp['rounds_per_day']} calls per AI per day, scheduled rounds included.</li>\n"
    councils_pointer = (
        '<p>The councils, several AIs that deliberate before a President decides, have their own league, on the same journal, the same markets and the same watch: '
        '<a href="councils.html#m-councils">their rules</a>.</p>\n'
        if perp.get("councils") else ""
    )
    benchmarks = "".join(
        f'<div><dt>{e(P.NAMES[k].removeprefix("Benchmark "))}</dt><dd>{e(v)}</dd></div>' for k, v in P.DESCRIPTIONS.items() if not k.startswith(P.COUNCIL_PREFIX) and k not in P.ROBOTS
    )
    robots = "".join(f'<div><dt>{e(P.NAMES[k])}</dt><dd>{e(P.DESCRIPTIONS[k])}</dd></div>' for k in P.ROBOTS)
    return f"""
<section aria-labelledby="m-derivatives"><h2 id="m-derivatives">The derivatives league</h2>
<p>Each portfolio has {eur(1_000_000_000, decimals=0)} of play money and trades 6 Kraken Futures perpetual contracts (BTC, ETH, SOL, XRP, LINK, LTC), betting on a rise (long) or a decline (short).
The AIs decide at the scheduled rounds of 02:00, 06:00, 10:00, 14:00, 18:00 and 22:00{NBSP}UTC. A watch reads prices every 5{NBSP}min, triggers stops and targets and counts funding every hour.</p>
<dl class="rules">
<div><dt>Leverage</dt><dd>At most 2; an order does not exceed half the portfolio.</dd></div>
<div><dt>Stop</dt><dd>Mandatory at each opening, between 1 and 15%; loss at the stop of 3% of the portfolio at most, 7.5% for all stops combined.</dd></div>
<div><dt>Guardrails</dt><dd>Freeze for 24{NBSP}h after a 5% loss in one day; permanent stop after a 15% drop from the peak; position closed after 7{NBSP}days.</dd></div>
<div><dt>Costs</dt><dd>Fees of 0.07% and slippage of 0.05% per order, rounded unfavorably; real hourly funding from Kraken; forced closeout if margin falls below 25% of exposure.</dd></div>
<div><dt>Prices</dt><dd>In dollars, converted to euros at the current EUR/USD rate. On this site, positions are also revalued live at Kraken's public price (figures underlined with dots): an estimate, the official figure remains that of the snapshot.</dd></div>
</dl>
<h3>The robots</h3>
<p>Without AI: a fixed rule, played by a separate process that reads prices much more often than the watch. Paper demonstration, outside the 2x rule (leverage up to 10x overall, stop at −60%).</p>
<dl class="rules">{robots}</dl>
<h3>The benchmarks</h3>
<dl class="rules">{benchmarks}</dl>
<h3 id="m-news">News</h3>
<p>The AIs only see official, structured news: Kraken's derivatives status page and the state of its contracts, read every 5{NBSP}min, and the US macro calendar published in advance. Never articles or social networks, and never the published figures: only the market's reaction reaches them. A new Kraken announcement, or an FOMC, CPI, jobs (NFP) or PCE release 3{NBSP}min old, calls the AIs back.</p>
<h3>What the AI can consult</h3>
<p>A snapshot of the account and the 6 markets, then at most 4 calls among 6 read-only tools, frozen at the start of the round (no web, no later data):</p>
<ul class="list-simple">{tools}</ul>
<p>Each decision gives a justification and, for each order, an invalidation condition. The guardrail judges it, then the execution is simulated.</p>
<h3>Between scheduled rounds</h3>
<ul class="list-simple">
{cadence}<li><strong>Recall requested</strong>: at each decision, an AI can ask to be called again in 5 to 60{NBSP}min.</li>
<li><strong>Market wake-up</strong>: a 2% move in 1{NBSP}h on a contract wakes the AIs, at least 15{NBSP}min between two wake-ups.</li>
<li><strong>Alert</strong>: at each decision, an AI can leave at most 3 price alerts. A crossed alert only wakes that AI.</li>
<li><strong>Entry order</strong>: at most 3, at a price level. Once crossed, it passes the guardrail then executes, without calling the AI back. Each decision replaces what was pending.</li>
</ul>
{councils_pointer}<p><span class="pill {"ok" if ok else "loss-bg"}">League journal: {"chain intact" if ok else "FAILED"}</span> {plural(j["n_records"], "event")}.</p>
</section>
"""


def _trend_method(budget: str) -> str:
    """The Trend council's rules (docs/SPEC-TREND-COUNCIL.md)."""
    return f"""<section aria-labelledby="m-councils"><h2 id="m-councils">The Trend council: method</h2>
<p>The initial ambition was a council that generates net income “of the order of 10% per day”. Ten percent per day, compounded, is ×17 in a month: no known strategy sustains that pace. The page therefore shows the target and the realized return per day, side by side.</p>
<p>The former councils (Haiku and Opus) lost money: opinions without an edge, huge sizes, a new decision every 10 minutes. The Trend council reverses the roles: <strong>an engine decides, the AIs can only brake, the code executes.</strong> {e(P.COUNCIL_OUTSIDE_RULE)}</p>
<ul class="list-simple">
<li><strong>The engine</strong>: slow trend following (2-day and 6-day moving averages on 4-hour bars, long and short, size scaled to volatility, 2x scale), chosen among 146 trials from four strategy families and frozen before the holdout was read. Over 31 holdout days in a sharp decline it made +21% (drawdowns down to −25%); in a trendless market it hovers around zero. One strategy, one episode of each type: the edge is plausible, not proven.</li>
<li><strong>The AIs</strong>: three Haiku (news, data, risk) advise, an Opus President sets for each contract a coefficient of 1, 0.5 or 0 that multiplies the engine's target. They can neither increase, nor invert, nor open a position the engine does not have. If the President fails or times out, the engine plays alone.</li>
<li><strong>The pace</strong>: one round at each 4-hour bar close (00:00, 04:00… UTC), plus a veto round on a Kraken announcement, a macro release or a 2% move in an hour, which can only lower the coefficients. No call every 10 minutes, no recall requested by an AI.</li>
<li><strong>The execution</strong>: an order only if the gap between target and position exceeds 5% of the portfolio; a 5% stop on each position. If the guardrail rejects an order for its size, the code retries it smaller.</li>
<li><strong>The “engine alone” benchmark</strong> plays the same target, without AI, through the same path and on the same rounds: the gap with the Trend council measures what the AIs add or remove.</li>
</ul>
<dl class="rules">
<div><dt>Leverage</dt><dd>At most 10, with Kraken's margins; the engine's scale gives about 1.4 on average, with peaks around 4 to 6. An order up to 400% of the portfolio's value.</dd></div>
<div><dt>Stop</dt><dd>5% on each position; loss at the stop of 25% of the portfolio at most per position, 59% for all stops combined.</dd></div>
<div><dt>Cost</dt><dd>The cost of a round trip does not exceed a third of the expected move. The engine's is measured offline (+2.47% gross per trade over the 64 training days), not declared.</dd></div>
<div><dt>Pace</dt><dd>At most 48 openings or adjustments per 24{NBSP}h, with no delay between two; no daily freeze, no fee budget (fees remain real and counted).</dd></div>
<div><dt>Stop-out</dt><dd>At −60% from its peak: positions closed, no more rounds. Only the arena operator can restart it, by hand.</dd></div>
{budget}</dl>
<p class="muted">Markets, watch and journal are those of the <a href="derivatives.html">solo AIs league</a>.</p>
</section>
"""


def councils_method(data: dict[str, Any]) -> str:
    """The rules of the councils league (section of its home page)."""
    perp = data["perp"]["councils"]
    councils = [p for p in perp["portfolios"] if p["kind"] == "council"]
    members = "".join(
        f"<li><strong>{e(n)}</strong> (step {step}): {e(role)}. <span class=\"muted\">Sources: {e(src)}.</span></li>"
        for n, step, role, src in P.MEMBERS.values()
    )
    budgets = "; ".join(
        f"{e(c['name'])} ${P.COUNCIL_BUDGETS_USD[c['id']]}{NBSP}per day" for c in councils if c["id"] in P.COUNCIL_BUDGETS_USD
    )
    budget = (
        f"<div><dt>Daily budget</dt><dd>{budgets}, at list-price equivalent. A round that no longer fits in the budget is skipped.</dd></div>\n"
        if budgets else ""
    )
    if any(c["id"] == P.COUNCIL_TREND for c in councils):
        return _trend_method(budget)
    return f"""<section aria-labelledby="m-councils"><h2 id="m-councils">Councils: method</h2>
<p>A council is a portfolio decided by ten Claude Haiku 5.5 that deliberate at each round, then by a President, with an aggressive mandate: double the stake in a few days. The councils play the same rounds as the derivatives AIs (scheduled rounds, regular call, wake-ups, alerts, recalls); a round counts as one call toward the daily cap, and its cost is the sum of the round's calls.</p>
<p>The councils differ only by their President: Haiku for the Haiku council, Opus for the Opus council. <strong>{e(P.COUNCIL_OUTSIDE_RULE)}</strong> They are therefore never ranked with the derivatives AIs, which all play by the same rules.</p>
<ul class="list-simple">
<li><strong>Step A</strong>: the advisers each give an opinion without seeing the others (long, short or flat per contract, conviction from 0 to 100, size, stop, key level, argument). Rounds from before the Pair Arbitrageur arrived count one opinion fewer.</li>
<li><strong>Step B</strong>: the Devil's Advocate reads these opinions and attacks the best-supported trade.</li>
<li><strong>Step C</strong>: the President reads all the opinions and decides, in the same format as the AIs. An adviser that fails is left aside; without a President, the round does nothing.</li>
</ul>
<details class="reading"><summary>The members and their sources</summary><ul class="list-simple">{members}</ul>
<p class="muted">Sources: TradingAgents (TauricResearch), claude-trading-skills (tradermonty) and HyperGrok (galleonlabs), three public repositories.</p></details>
<dl class="rules">
<div><dt>Leverage</dt><dd>At most 10, with Kraken's margins (1 to 2% of the amount to open); an entry up to 500% of the portfolio's value, a position up to 1,000%.</dd></div>
<div><dt>Stop</dt><dd>Mandatory, between 1 and 15%, and always before liquidation; loss at the stop of 25% of the portfolio at most per trade, 60% for all stops combined.</dd></div>
<div><dt>Pace</dt><dd>At most 24 openings per 24{NBSP}h, with no delay between two; no daily freeze, no fee budget (fees remain real and counted).</dd></div>
<div><dt>Stop-out</dt><dd>At −90% from its peak (ruin): positions closed, no more rounds. Only the arena operator can restart it, by hand.</dd></div>
<div><dt>Liquidation</dt><dd>Simulated as at Kraken: when the value falls below the maintenance margin (half the opening margin), tested every minute at the worst price, with 5% liquidation fees; then 1{NBSP}h without entry.</dd></div>
{budget}</dl>
<p class="muted">The policy is the same for both councils. Markets, watch, journal and reference benchmark are those of the <a href="derivatives.html">solo AIs league</a>.</p>
</section>
"""
