"""Génération du HTML du dashboard (sans framework : f-strings). Tout texte venant du journal est échappé."""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from arene.site.data import CODES_RISQUE, SAUTS

NBSP = " "
NNBSP = " "
MINUS = "−"
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]

BANDEAU = "SIMULÉ — paper, aucun argent réel"
AVERTISSEMENT = (
    "Expérience personnelle, pas un conseil en investissement. Les décisions sont produites par des IA, "
    "en simulation ; des pertes sont possibles. Chiffres avant impôt."
)


def e(x: Any) -> str:
    """Échappement HTML systématique (guillemets compris)."""
    return html.escape("" if x is None else str(x), quote=True)


# ---------------------------------------------------------------------------
# Formats à la française
# ---------------------------------------------------------------------------


def _group(n: int) -> str:
    return f"{n:,}".replace(",", NNBSP)


def eur(ueur: int | None, *, signed: bool = False, decimals: int = 2) -> str:
    if ueur is None:
        return "—"
    sign = MINUS if ueur < 0 else ("+" if signed and ueur > 0 else "")
    unit = 10 ** (6 - decimals)
    v = (abs(ueur) + unit // 2) // unit
    whole, frac = divmod(v, 10**decimals)
    return f"{sign}{_group(whole)},{frac:0{decimals}d}{NBSP}€"


def pct(f: float | None, *, signed: bool = True, digits: int = 2) -> str:
    if f is None:
        return "—"
    v = round(f * 100, digits)
    sign = MINUS if v < 0 else ("+" if signed and v > 0 else "")
    return f"{sign}{abs(v):.{digits}f}".replace(".", ",") + f"{NBSP}%"


def num(f: float | None, digits: int = 2, *, signed: bool = False) -> str:
    if f is None:
        return "—"
    v = round(f, digits)
    sign = MINUS if v < 0 else ("+" if signed and v > 0 else "")
    return f"{sign}{abs(v):.{digits}f}".replace(".", ",")


def usd(uusd: int | None) -> str:
    if uusd is None:
        return "—"
    digits = 2 if uusd >= 1_000_000 else 4
    v = Decimal(uusd) / Decimal(1_000_000)
    return f"{v:.{digits}f}".replace(".", ",") + f"{NBSP}$"


def qty_fmt(q: int) -> str:
    d = (Decimal(q) / Decimal(100_000_000)).normalize()
    s = format(d, "f")
    return s.replace(".", ",")


def when(ts: int | None) -> str:
    if ts is None:
        return "—"
    d = datetime.fromtimestamp(ts, UTC)
    return f"{d.day} {MOIS[d.month - 1]} {d.year}, {d:%H:%M} UTC"


def tone(v: float | None) -> str:
    if v is None or v == 0:
        return ""
    return "gain" if v > 0 else "perte"


def duree(seconds: int) -> str:
    if seconds % 86400 == 0:
        return f"{seconds // 86400}{NBSP}j"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}{NBSP}h"
    return f"{seconds}{NBSP}s"


def bp_pct(bp: int | None) -> str:
    return "—" if bp is None else (f"{bp / 100:.2f}".rstrip("0").rstrip(".").replace(".", ",") + f"{NBSP}%")


def json_inline(obj: Any) -> str:
    """JSON sûr à placer dans <script type="application/json"> (aucun '<' ne subsiste)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


# ---------------------------------------------------------------------------
# Gabarit commun
# ---------------------------------------------------------------------------


def layout(*, title: str, body: str, root: str, active: str, data: dict[str, Any], scripts: str = "") -> str:
    models = [p for p in data["portfolios"]]
    links = "".join(
        f'<a href="{root}modele/{e(p["slug"])}.html"{" aria-current=\"page\"" if active == p["id"] else ""}>{e(p["name"])}</a>'
        for p in models
    )
    nav_top = (
        f'<a href="{root}index.html"{" aria-current=\"page\"" if active == "index" else ""}>Vue d’ensemble</a>'
        f'<a href="{root}methode.html"{" aria-current=\"page\"" if active == "methode" else ""}>Méthode</a>'
    )
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="robots" content="noindex, nofollow">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src data:; connect-src 'self'; base-uri 'none'; form-action 'none'">
<title>{e(title)} · Arène de trading</title>
<link rel="stylesheet" href="{root}vendor/uPlot.min.css">
<link rel="stylesheet" href="{root}assets/site.css">
</head>
<body>
<div class="bandeau" role="status"><strong>{e(BANDEAU)}</strong><span class="venue">venue_mode&nbsp;: {e(data["venue_mode"])}</span></div>
<header class="entete">
  <div class="wrap">
    <a class="marque" href="{root}index.html">Arène de trading</a>
    <nav class="nav" aria-label="Pages principales">{nav_top}</nav>
  </div>
  <div class="wrap"><nav class="nav nav-modeles" aria-label="Portefeuilles">{links}</nav></div>
</header>
<main class="wrap">
{body}
</main>
<footer class="pied wrap">
  <p>{e(AVERTISSEMENT)}</p>
  <p class="muted">Mis à jour le {e(when(data["generated_ts"]))} · tête du journal <code>{e(data["journal"]["head_hash"][:16])}…</code> · {data["journal"]["n_records"]} événements.</p>
</footer>
{scripts}
</body>
</html>
"""


def _chart_scripts(root: str, chart: dict[str, Any], focus: str | None) -> str:
    payload = {"x": chart["x"], "series": chart["series"], "focus": focus}
    return (
        f'<script id="equity-data" type="application/json">{json_inline(payload)}</script>\n'
        f'<script src="{root}vendor/uPlot.iife.min.js"></script>\n'
        f'<script src="{root}assets/chart.js"></script>'
    )


def _chart_block(chart: dict[str, Any]) -> str:
    if len(chart["x"]) < 2:
        return '<p class="vide">Aucun cycle terminé pour l’instant : la courbe apparaîtra après le premier cycle.</p>'
    return (
        '<figure class="graphique"><div id="chart" role="img" '
        'aria-label="Equity des portefeuilles en base 100"></div>'
        '<figcaption>Equity en base 100 au départ. Modèles en couleurs, témoins en gris pointillé. '
        'Cliquer sur un nom dans la légende le masque.</figcaption></figure>'
    )


# ---------------------------------------------------------------------------
# Vue d'ensemble
# ---------------------------------------------------------------------------


def _verdict_hasard(p: dict[str, Any], min_cycles: int) -> str:
    d = p["distinguishable"]
    if p["id"] == "temoin:panier":
        return '<span class="pastille neutre">référence</span>'
    if p["n_cycles"] < min_cycles:
        return '<span class="pastille neutre">trop tôt</span>'
    if d and d["significant"]:
        sens = "au-dessus" if d["mean_diff"] > 0 else "en dessous"
        return f'<span class="pastille info">écart significatif ({sens} du panier)</span>'
    return '<span class="pastille neutre">non distinguable du hasard</span>'


def _sharpe_cell(p: dict[str, Any], min_cycles: int) -> str:
    if p["sharpe"] is None or p["sharpe_ci"] is None:
        return f'<span class="muted">trop tôt</span><small class="sous">dès {min_cycles} cycles</small>'
    lo, hi = p["sharpe_ci"]
    return f'{num(p["sharpe"])}<small class="sous">IC 95{NBSP}% [{num(lo, 1)} ; {num(hi, 1)}]</small>'


def _rank_cell(p: dict[str, Any]) -> str:
    r = p["rank_percentile"]
    if r is None:
        return '<span class="muted">—</span>'
    return f'{num(r, 0)}'


def overview_table(data: dict[str, Any]) -> str:
    mc = data["min_cycles_stats"]
    rows = []
    for p in data["portfolios"]:
        statut = ""
        if p["halted"]:
            statut = ' <span class="pastille perte-bg">arrêté</span>'
        elif p["frozen_until_ts"]:
            statut = ' <span class="pastille warn">gelé</span>'
        cout = usd(p["api_cost_uusd"]) if p["api_cost_uusd"] is not None else '<span class="muted">—</span>'
        rows.append(
            f'<tr class="{e(p["kind"])}"><th scope="row"><a href="modele/{e(p["slug"])}.html">{e(p["name"])}</a>{statut}'
            f'<small class="sous">{"modèle d’IA" if p["kind"] == "llm" else "témoin"}</small>'
            f'<span class="verdict-ligne">{_verdict_hasard(p, mc)}</span></th>'
            f'<td class="n">{eur(p["equity_ueur"])}<small class="sous">base {num(p["base100"], 1)}</small></td>'
            f'<td class="n {tone(p["total_return"])}">{pct(p["total_return"])}</td>'
            f'<td class="n">{pct(-p["max_drawdown"], signed=False) if p["max_drawdown"] else pct(0.0, signed=False)}</td>'
            f'<td class="n">{_sharpe_cell(p, mc)}</td>'
            f'<td class="n">{eur(p["fees_paid_ueur"])}</td>'
            f'<td class="n">{p["n_trades"]}</td>'
            f'<td class="n">{cout}</td>'
            f'<td class="n">{_rank_cell(p)}</td></tr>'
        )
    head = (
        "<tr><th scope=\"col\">Portefeuille</th><th scope=\"col\" class=\"n\">Equity</th>"
        "<th scope=\"col\" class=\"n\">Rendement net</th><th scope=\"col\" class=\"n\">Drawdown max</th>"
        "<th scope=\"col\" class=\"n\">Sharpe</th><th scope=\"col\" class=\"n\">Frais payés</th>"
        "<th scope=\"col\" class=\"n\">Trades</th><th scope=\"col\" class=\"n\">Coût d’API</th>"
        "<th scope=\"col\" class=\"n\">Rang aléatoire <span class=\"nb\">(percentile)</span></th></tr>"
    )
    return (
        '<div class="table-scroll" tabindex="0" role="region" aria-label="Tableau comparatif">'
        f'<table class="tableau"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>'
    )


def index_page(data: dict[str, Any]) -> str:
    nc, mc = data["n_cycles"], data["min_cycles_stats"]
    if nc == 0:
        phrase = "Aucun cycle terminé pour l’instant."
        cls = "neutre"
    elif data["any_llm_distinguishable"]:
        phrase = "Au moins un modèle s’écarte du panier de façon significative. Cela ne dit rien de la suite."
        cls = "info"
    elif nc < mc:
        phrase = f"Trop tôt pour conclure : {nc} cycle{'s' if nc > 1 else ''} sur {mc} minimum. Aucun modèle n’est distinguable du hasard."
        cls = "neutre"
    else:
        phrase = "Aucun modèle n’est distinguable du hasard."
        cls = "neutre"
    meilleur = ""
    if nc:
        meilleur = (
            f'<p class="sous-verdict">{nc} cycle{"s" if nc > 1 else ""} de 4{NBSP}h, du {e(when(data["first_cycle_ts"]))} '
            f'au {e(when(data["last_cycle_ts"]))}. Rendements nets des frais et du glissement simulés.</p>'
        )
    dist = data["distribution"]
    dist_txt = ""
    if dist:
        dist_txt = (
            f'<p class="muted note">Distribution de {dist["n"]}{NBSP}trajectoires aléatoires rejouées sur les mêmes cycles et les mêmes quotes : '
            f'médiane {pct(dist["median"])}, 90{NBSP}% d’entre elles entre {pct(dist["p05"])} et {pct(dist["p95"])}. '
            f'Le rang est le percentile du rendement du portefeuille dans cette distribution.</p>'
        )
    elif data["distribution_note"]:
        dist_txt = f'<p class="muted note">{e(data["distribution_note"])}.</p>'
    body = f"""
<section class="hero {cls}">
  <p class="etiquette">Journal d’expérience · simulation</p>
  <h1>{e(phrase)}</h1>
  {meilleur}
</section>
<section>
  <h2>Equity des 7 portefeuilles</h2>
  {_chart_block(data["chart"])}
</section>
<section>
  <h2>Comparatif</h2>
  {overview_table(data)}
  <p class="muted note">Rendement net après frais ({data["method"]["taker_fee_bp"] / 100:.2f}{NBSP}% par ordre) et glissement ({data["method"]["slippage_bp"]}{NBSP}pb) simulés,
  avant impôt. Le Sharpe annualisé et son intervalle de confiance à 95{NBSP}% (bootstrap par blocs) ne s’affichent qu’à partir de {mc}{NBSP}cycles.
  « Non distinguable du hasard » : l’écart de rendement au témoin panier n’est pas significatif.</p>
  {dist_txt}
</section>
<section class="avis">
  <p><strong>Ce que montre cette page.</strong> Des modèles d’IA décident toutes les 4{NBSP}h sur 6 cryptos cotées en euros, en simulation avec des frais pessimistes.
  Chaque décision est journalisée. Le raisonnement des modèles est publié 24{NBSP}h après la décision. Rien ici n’est un signal ni une recommandation.</p>
</section>
"""
    return layout(
        title="Vue d’ensemble", body=body, root="", active="index", data=data,
        scripts=_chart_scripts("", data["chart"], None) if len(data["chart"]["x"]) >= 2 else "",
    )  # fmt: skip


# ---------------------------------------------------------------------------
# Page modèle
# ---------------------------------------------------------------------------


def _stat(label: str, value: str, extra: str = "", cls: str = "") -> str:
    return f'<div class="stat"><dt>{e(label)}</dt><dd class="{cls}">{value}{extra}</dd></div>'


def _positions(p: dict[str, Any]) -> str:
    if not p["positions"]:
        return f'<p class="vide">Aucune position détenue. Cash : {eur(p["cash_ueur"])}.</p>'
    rows = "".join(
        f'<tr><th scope="row">{e(x["symbol"])}</th><td class="n">{e(qty_fmt(x["qty"]))}</td>'
        f'<td class="n">{eur(x["cost_ueur"])}</td><td class="n">{eur(x["value_ueur"])}</td>'
        f'<td class="n {tone(x["unrealized_ueur"])}">{eur(x["unrealized_ueur"], signed=True)}</td>'
        f'<td class="n">{eur(x["stop_ueur"], decimals=4) if x["stop_ueur"] else "—"}</td>'
        f'<td>{e(when(x["opened_ts"]))}</td></tr>'
        for x in p["positions"]
    )
    return (
        '<div class="table-scroll" tabindex="0" role="region" aria-label="Positions courantes"><table class="tableau">'
        '<thead><tr><th scope="col">Symbole</th><th scope="col" class="n">Quantité</th><th scope="col" class="n">Coût (frais inclus)</th>'
        '<th scope="col" class="n">Valeur au dernier mid</th><th scope="col" class="n">Latent</th><th scope="col" class="n">Stop</th>'
        f'<th scope="col">Ouverte le</th></tr></thead><tbody>{rows}</tbody></table></div>'
        f'<p class="muted note">Cash : {eur(p["cash_ueur"])}.</p>'
    )


def _codes(reasons: list[str]) -> str:
    return "".join(
        f'<span class="code" title="{e(CODES_RISQUE.get(c, c))}"><code>{e(c)}</code> {e(CODES_RISQUE.get(c, "règle inconnue"))}</span>'
        for c in reasons
    )


def _fill_html(f: dict[str, Any]) -> str:
    sens = "achat" if f["side"] == "buy" else "vente"
    motif = {"intent": "", "stop": " (stop)", "max_holding": " (détention maximale)", "kill_switch": " (coupe-circuit)"}.get(
        f["reason"], f" ({f['reason']})"
    )
    return (
        f'<li class="fill">Fill : {sens}{e(motif)} {e(qty_fmt(f["qty"]))} {e(f["symbol"])} à {eur(f["price_ueur"], decimals=4)}, '
        f'frais {eur(f["fee_ueur"], decimals=4)} <span class="muted">· {e(when(f["ts"]))}</span></li>'
    )


def _action_html(a: dict[str, Any]) -> str:
    sens = "acheter" if a["side"] == "buy" else "vendre"
    if a["side"] == "buy":
        detail = f'{bp_pct(a["size_bp"])} de l’equity, stop à {bp_pct(a["stop_bp"])} sous l’entrée'
        if a["expected_move_bp"] is not None:
            detail += f', mouvement attendu {bp_pct(a["expected_move_bp"])}'
    else:
        detail = f'{bp_pct(a["size_bp"])} de la position'
    if a["approved"] is None:
        verdict = '<span class="pastille neutre">sans verdict</span>'
    elif a["approved"]:
        verdict = '<span class="pastille ok">riskd : approuvé</span>'
    else:
        verdict = f'<span class="pastille perte-bg">riskd : rejeté</span><span class="codes">{_codes(a["reasons"])}</span>'
    fills = "".join(_fill_html(f) for f in a["fills"])
    return (
        f'<li class="action"><div><strong>A voulu {sens} {e(a["symbol"])}</strong> · {detail}</div>'
        f'<div class="verdict">{verdict}</div>{f"<ul class=fills>{fills}</ul>" if fills else ""}</li>'
    )


def _decision_compact(d: dict[str, Any]) -> str | None:
    """Ligne d'une décision sans action ni fill (le plus fréquent) ; None si elle mérite une carte entière."""
    if d["actions"] or d["sorties"]:
        return None
    if d["kind"] == "skipped":
        raison = SAUTS.get(d["skip_reason"], d["skip_reason"])
        return (
            f'<div class="ligne"><span class="quand">{e(when(d["cycle"]))}</span>'
            f'<span class="pastille warn">sautée</span> <span class="muted">{e(raison)} <code>{e(d["skip_reason"])}</code></span></div>'
        )
    if d["kind"] != "decided":
        return None
    corps = ""
    if d.get("a_justification"):
        if d["justification_publiee"]:
            corps = f'<blockquote class="justif"><span class="etiquette">Justification du modèle</span>{e(d["justification"])}</blockquote>'
        else:
            corps = f'<div class="justif masquee">Publiée 24{NBSP}h après la décision, le {e(when(d["publication_ts"]))}.</div>'
    cout = f' · coût {usd(d["cost_uusd"])}' if d.get("cost_uusd") else ""
    return (
        f'<details class="ligne"><summary><span class="quand">{e(when(d["cycle"]))}</span>'
        f'<span class="muted">Aucune action{cout}</span></summary>{corps}</details>'
    )


def _decision_html(d: dict[str, Any]) -> str:
    compact = _decision_compact(d)
    if compact is not None:
        return compact
    if d["kind"] == "skipped":
        raison = SAUTS.get(d["skip_reason"], d["skip_reason"])
        tete = f'<span class="pastille warn">décision sautée</span> <span>{e(raison)} <code>{e(d["skip_reason"])}</code></span>'
    elif d["kind"] == "parse_error":
        tete = f'<span class="pastille warn">réponse invalide</span> <span>{e(d["parse_error"])}</span>'
    elif d["kind"] == "temoin":
        tete = '<span class="pastille neutre">règle mécanique</span>'
    else:
        tete = ""
    meta = []
    if d.get("model_returned"):
        meta.append(f'modèle {e(d["model_returned"])}')
    if d.get("cost_uusd"):
        meta.append(f'coût {usd(d["cost_uusd"])}')
    if d.get("output_tokens"):
        meta.append(f'{d["input_tokens"]}+{d["output_tokens"]} tokens')
    meta_html = f'<span class="muted">{" · ".join(meta)}</span>' if meta else ""
    actions = "".join(_action_html(a) for a in d["actions"])
    if d["kind"] == "decided" and not d["actions"]:
        actions = '<li class="action"><em>N’a pris aucune action ce cycle.</em></li>'
    sorties = "".join(_fill_html(f) for f in d["sorties"])
    just = ""
    if d["kind"] in ("decided", "parse_error") and d.get("a_justification"):
        if d["justification_publiee"]:
            just = f'<blockquote class="justif"><span class="etiquette">Justification du modèle</span>{e(d["justification"])}</blockquote>'
        else:
            just = (
                '<div class="justif masquee"><span class="etiquette">Justification</span>'
                f'Publiée 24{NBSP}h après la décision, le {e(when(d["publication_ts"]))}.</div>'
            )
    return (
        f'<article class="decision"><header><h3>{e(when(d["cycle"]))}</h3>{tete}{meta_html}</header>'
        f'{f"<ul class=actions>{actions}</ul>" if actions else ""}'
        f'{f"<ul class=fills>{sorties}</ul>" if sorties else ""}{just}</article>'
    )


def model_page(data: dict[str, Any], p: dict[str, Any], baseline_chart: dict[str, Any]) -> str:
    mc = data["min_cycles_stats"]
    cout = usd(p["api_cost_uusd"]) if p["api_cost_uusd"] is not None else "—"
    stats_html = "".join(
        [
            _stat("Equity", eur(p["equity_ueur"]), f'<small class="sous">base {num(p["base100"], 1)}</small>'),
            _stat("Rendement net", pct(p["total_return"]), cls=tone(p["total_return"])),
            _stat("Drawdown max", pct(-p["max_drawdown"], signed=False) if p["max_drawdown"] else pct(0.0, signed=False)),
            _stat("Sharpe (IC 95 %)", _sharpe_cell(p, mc)),
            _stat("Frais payés", eur(p["fees_paid_ueur"])),
            _stat("Trades", str(p["n_trades"])),
            _stat("Coût d’API cumulé", cout),
            _stat("Rang (percentile) vs aléatoire", _rank_cell(p)),
        ]
    )
    statut = ""
    if p["halted"]:
        statut = '<p class="pastille perte-bg">Portefeuille arrêté (drawdown)</p>'
    elif p["frozen_until_ts"]:
        statut = f'<p class="pastille warn">Portefeuille gelé jusqu’au {e(when(p["frozen_until_ts"]))}</p>'
    skipped = ""
    if p["skipped"]:
        items = "".join(
            f'<li><strong>{n}</strong> × {e(SAUTS.get(r, r))} <code>{e(r)}</code></li>' for r, n in sorted(p["skipped"].items())
        )
        skipped = f'<h3>Décisions sautées</h3><ul class="liste-simple">{items}</ul>'
    rejects = ""
    if p["rejects"]:
        items = "".join(
            f'<li><strong>{n}</strong> × <code>{e(c)}</code> {e(CODES_RISQUE.get(c, ""))}</li>'
            for c, n in sorted(p["rejects"].items(), key=lambda kv: -kv[1])
        )
        rejects = f'<h3>Rejets de riskd par code</h3><ul class="liste-simple">{items}</ul>'
    decs = "".join(_decision_html(d) for d in p["decisions"])
    reste = p["decisions_total"] - len(p["decisions"])
    reste_html = f'<p class="muted">{reste} décisions plus anciennes non affichées (elles restent dans le journal).</p>' if reste > 0 else ""
    if not decs:
        decs = '<p class="vide">Aucune décision journalisée pour ce portefeuille.</p>'
    verdict = ""
    if p["kind"] == "llm" and p["distinguishable"]:
        verdict = f'<p>{_verdict_hasard(p, mc)}</p>'
    body = f"""
<p class="fil"><a href="../index.html">← Vue d’ensemble</a></p>
<h1>{e(p["name"])}</h1>
<p class="muted">{e(p["description"]) if p["description"] else "Modèle d’IA : décide toutes les 4 h à partir d’un instantané calculé par le code ; riskd valide, le simulateur exécute."}
Identifiant : <code>{e(p["id"])}</code></p>
{statut}{verdict}
<dl class="stats">{stats_html}</dl>
<section><h2>Courbe d’equity</h2>{_chart_block(baseline_chart)}</section>
<section><h2>Positions courantes</h2>{_positions(p)}</section>
<section><h2>Décisions</h2>
<p class="muted note">Du plus récent au plus ancien. Le raisonnement du modèle n’est publié que 24{NBSP}h après la décision ; les actions et les verdicts de riskd sont visibles tout de suite.</p>
<div class="deux-col">{skipped}{rejects}</div>
{decs}{reste_html}
</section>
"""
    return layout(
        title=p["name"], body=body, root="../", active=p["id"], data=data,
        scripts=_chart_scripts("../", baseline_chart, p["id"]) if len(baseline_chart["x"]) >= 2 else "",
    )  # fmt: skip


# ---------------------------------------------------------------------------
# Page méthode
# ---------------------------------------------------------------------------

POLITIQUE_LIBELLES = {
    "symbols": ("Paires autorisées", "liste blanche"),
    "max_order_bp": ("Taille maximale d’un achat", "bp_pct:de l’equity"),
    "max_position_bp": ("Position maximale par symbole", "bp_pct:de l’equity après l’ordre"),
    "max_exposure_bp": ("Exposition totale maximale", "bp_pct:de l’equity"),
    "max_trades_per_day": ("Trades par portefeuille et par 24 h", "n"),
    "max_orders_per_minute": ("Ordres par minute (tous portefeuilles)", "n"),
    "min_interval_same_symbol_s": ("Délai minimal entre deux achats du même symbole", "duree"),
    "stop_bp_min": ("Stop minimal à l’achat", "bp_pct:sous l’entrée"),
    "stop_bp_max": ("Stop maximal à l’achat", "bp_pct:sous l’entrée"),
    "max_cost_to_expected_move_pct": ("Coût aller-retour / mouvement attendu, au plus", "pct_int"),
    "max_holding_s": ("Détention maximale (sortie forcée)", "duree"),
    "daily_loss_freeze_bp": ("Perte sur 24 h déclenchant un gel", "bp_pct:de l’equity"),
    "freeze_duration_s": ("Durée du gel", "duree"),
    "drawdown_halt_bp": ("Drawdown déclenchant l’arrêt et la mise à plat", "bp_pct:depuis le plus haut"),
    "monthly_fee_budget_bp": ("Budget de frais du mois civil", "bp_pct:de l’equity de début de mois"),
    "max_quote_deviation_bp": ("Écart maximal quote / dernière clôture", "bp_pct:"),
    "max_spread_multiple": ("Spread maximal (multiple de la médiane des 20 derniers)", "mult"),
    "min_order_ueur": ("Ordre minimal (au moins le minimum Kraken)", "eur"),
}


def _policy_value(key: str, v: Any) -> tuple[str, str]:
    kind = POLITIQUE_LIBELLES[key][1]
    if key == "symbols":
        return ", ".join(v), ""
    if kind.startswith("bp_pct"):
        return bp_pct(v), kind.partition(":")[2]
    if kind == "duree":
        return duree(v), ""
    if kind == "pct_int":
        return f"{v}{NBSP}%", ""
    if kind == "mult":
        return f"× {v}", ""
    if kind == "eur":
        return eur(v), ""
    return str(v), ""


def methode_page(data: dict[str, Any]) -> str:
    m, j, pv = data["method"], data["journal"], data["provenance"]
    pol_rows = "".join(
        f'<tr><th scope="row">{e(POLITIQUE_LIBELLES[k][0])}</th><td class="n">{e(_policy_value(k, v)[0])}</td>'
        f'<td class="muted">{e(_policy_value(k, v)[1])}</td><td><code>{e(k)}</code></td></tr>'
        for k, v in m["policy"].items()
        if k in POLITIQUE_LIBELLES
    )
    ok = j["verify_ok"]
    verif = (
        f'<p><span class="pastille {"ok" if ok else "perte-bg"}">verify() : {"chaîne intacte" if ok else "ÉCHEC"}</span> '
        f'{j["n_records"]} événements, dernier seq {e(j["head_seq"])}.</p>'
    )
    if j["errors"]:
        verif += "<ul class=\"liste-simple\">" + "".join(
            f'<li><code>{e(x["code"])}</code> ligne {x["line"]} : {e(x["message"])}</li>' for x in j["errors"]
        ) + "</ul>"
    modeles = "".join(
        f'<tr><th scope="row"><code>{e(x["model"])}</code></th><td class="n">{usd(x["daily_budget_uusd"])}</td>'
        f'<td class="n">{usd(x["price_in_uusd_per_mtok"])} / {usd(x["price_out_uusd_per_mtok"])}</td></tr>'
        for x in m["models"]
    )
    policy_same = (
        pv["journal_policy_sha256"] is None or pv["journal_policy_sha256"] == pv["policy_sha256"]
    )
    prompts = ", ".join(f'<code>{e(h)}</code>' for h in pv["prompt_hashes"]) or "non journalisé"
    body = f"""
<h1>Méthode</h1>
<p class="muted">Tout ce qui suit décrit l’expérience telle qu’elle est paramétrée. Ce n’est pas un conseil en investissement.</p>

<section><h2>Ce que fait l’arène</h2>
<p>Trois modèles d’IA (Claude Haiku 5.5, Sonnet 5.5, Opus 5.5) et quatre témoins gèrent chacun {eur(m["capital_ueur"], decimals=0)} fictifs sur 6 paires cotées en euros
chez Kraken. Toutes les {duree(m["interval_s"])}, chaque portefeuille décide ; un module de risque (<code>riskd</code>) valide ou rejette chaque intention ;
un simulateur pessimiste exécute les ordres acceptés. Long seulement, sans levier. Chaque événement est écrit dans un journal chaîné.</p></section>

<section><h2>Les témoins</h2>
<div class="table-scroll" tabindex="0" role="region" aria-label="Règles des témoins"><table class="tableau"><tbody>
<tr><th scope="row">Panier</th><td>1/6 de l’equity sur chaque paire au premier cycle (frais compris), puis conservé : achat et conservation.</td></tr>
<tr><th scope="row">60/40</th><td>60 % en BTC, 40 % en cash, rééquilibré le premier cycle de chaque mois civil.</td></tr>
<tr><th scope="row">E0065 (adapté)</th><td>Règle F1 du labo, pression taker : L = {m["e0065"]["L"]}, k = {m["e0065"]["k"]}, H = {m["e0065"]["H"]}. Adaptée : univers des 6 paires, ratio taker calculé sur les bougies journalières Binance USDT, exécution au prix Kraken EUR, reconstitution tous les {m["e0065"]["H"]} jours.</td></tr>
<tr><th scope="row">Aléatoire</th><td>À chaque cycle, 0 à 2 actions tirées au hasard dans le même espace d’actions que les modèles, avec exactement les mêmes règles de risque. Hors ligne, {m["n_trajectoires"]} trajectoires sont rejouées sur les mêmes cycles et les mêmes quotes ; le rang d’un portefeuille est son percentile dans cette distribution.</td></tr>
</tbody></table></div></section>

<section><h2>Frais et glissement simulés</h2>
<p>Modèle d’exécution <code>{e(m["fill_model_version"])}</code> : ordres au marché uniquement. Achat à l’ask majoré de {m["slippage_bp"]}{NBSP}pb, vente au bid minoré de {m["slippage_bp"]}{NBSP}pb,
arrondis au pas de prix dans le sens défavorable. Frais de {m["taker_fee_bp"] / 100:.2f}{NBSP}% du notional par ordre (taker Kraken de base majoré de 25 %), arrondis vers le haut.
Quantités arrondies vers le bas. Un stop est posé à l’entrée ; la détention est limitée à {duree(policy_max_holding(m))}.</p></section>

<section><h2>Politique de risque (paper)</h2>
<p class="muted">Politique chargée à la construction du site. Valeurs de la simulation, plus souples que ne le serait une politique réelle.</p>
<div class="table-scroll" tabindex="0" role="region" aria-label="Politique de risque"><table class="tableau">
<thead><tr><th scope="col">Règle</th><th scope="col" class="n">Valeur</th><th scope="col">Base</th><th scope="col">Clé</th></tr></thead><tbody>{pol_rows}</tbody></table></div></section>

<section><h2>Modèles d’IA et coût d’API</h2>
<div class="table-scroll" tabindex="0" role="region" aria-label="Modèles"><table class="tableau">
<thead><tr><th scope="col">Modèle</th><th scope="col" class="n">Budget par jour</th><th scope="col" class="n">Prix par million de tokens (entrée / sortie)</th></tr></thead><tbody>{modeles}</tbody></table></div>
<p class="muted note">Le prompt système est versionné et son hash est journalisé : {prompts}. Un modèle n’a accès qu’à des barres closes calculées par le code, aucun texte web.
Une décision peut être sautée (pas de clé, budget quotidien atteint, portefeuille gelé…) ; ces décisions sont comptées sur la page de chaque modèle.</p></section>

<section><h2>Intégrité du journal</h2>
{verif}
<p>Hash de tête de chaîne : <code class="hash">{e(j["head_hash"])}</code></p>
<p class="muted">Politique de risque (sha256) : <code class="hash">{e(pv["policy_sha256"])}</code>{"" if policy_same else " — différente de celle du dernier chargement journalisé !"}<br>
Configuration (sha256) : <code class="hash">{e(pv["config_sha256"])}</code><br>
Commit : <code>{e(pv["git_head"] or "non journalisé")}</code></p></section>

<section><h2>Limites, sans maquillage</h2>
<ul class="liste-simple">
<li><strong>Paper.</strong> Aucun ordre réel n’est passé. Un vrai ordre aurait des refus, des exécutions partielles, des pannes et un impact sur le marché que ce simulateur ne reproduit pas.</li>
<li><strong>Frais pessimistes, modèle simplifié.</strong> Les frais et le glissement sont volontairement élevés, mais le glissement est constant et ne dépend ni de la taille ni de la profondeur du carnet.</li>
<li><strong>Petit échantillon.</strong> Quelques semaines de décisions toutes les 4 h ne distinguent presque jamais un modèle du hasard. C’est pourquoi le Sharpe et son intervalle n’apparaissent qu’à partir de {data["min_cycles_stats"]} cycles, et pourquoi « non distinguable du hasard » est le verdict par défaut.</li>
<li><strong>Ce que le journal chaîné prouve.</strong> Qu’aucun événement n’a été modifié, supprimé ou réordonné après coup : chaque ligne contient le hash de la précédente, et le rejeu du journal redonne les chiffres affichés.</li>
<li><strong>Ce qu’il ne prouve pas.</strong> Qu’il n’y a pas eu de triche avant l’écriture : rien n’atteste, à lui seul, que les prix journalisés sont ceux du marché ni que les décisions n’ont pas été choisies parmi plusieurs essais.</li>
<li><strong>Univers étroit et période courte.</strong> 6 cryptos, long seulement ; un résultat ici ne se transpose pas à d’autres marchés, d’autres périodes ni à de l’argent réel.</li>
<li><strong>Avant impôt.</strong> Les chiffres ne tiennent pas compte de la fiscalité.</li>
</ul></section>

<section class="avis"><h2>Avertissement</h2>
<p><strong>Ce n’est pas un conseil en investissement.</strong> Expérience personnelle de simulation ; aucune recommandation, aucun signal, aucune promesse de rendement. Les performances passées, simulées de surcroît, ne préjugent pas des performances futures. Investir dans des crypto-actifs comporte un risque de perte totale.</p></section>
"""
    return layout(title="Méthode", body=body, root="", active="methode", data=data)


def policy_max_holding(m: dict[str, Any]) -> int:
    return int(m["policy"]["max_holding_s"])
