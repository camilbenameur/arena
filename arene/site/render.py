"""Génération du HTML du dashboard (sans framework : f-strings). Tout texte venant du journal est échappé.

Aucun attribut `style` dans le HTML : la CSP n'autorise que les feuilles de style du site (`style-src 'self'`).
Les petites jauges et barres sont donc des SVG dont la largeur est un attribut, pas un style.
"""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from arene.site.data import CODES_RISQUE, SAUTS, nom

NBSP = "\u00a0"
NNBSP = "\u202f"
MINUS = "\u2212"
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]

BANDEAU = "Simulation\u202f: argent fictif, aucun ordre réel"
BANDEAU_REEL = "ARGENT RÉEL"
NOMBRES_MIN = {1: "un", 2: "deux", 3: "trois", 4: "quatre", 5: "cinq", 6: "six", 7: "sept", 8: "huit"}


def description(data: dict[str, Any]) -> str:
    """Méta-description : le nombre de modèles et de témoins vient du journal, pas d'une constante."""
    n_llm = sum(1 for p in data.get("portfolios", ()) if p["kind"] == "llm")
    n_tem = sum(1 for p in data.get("portfolios", ()) if p["kind"] != "llm")
    llm = f"{NOMBRES_MIN.get(n_llm, n_llm)} modèle{'s' if n_llm > 1 else ''} d’IA"
    gere = "gèrent chacun un portefeuille" if n_llm > 1 else "gère un portefeuille"
    return (
        f"{llm[:1].upper() + llm[1:]} {gere} crypto fictif, comparé{'s' if n_llm > 1 else ''} à "
        f"{NOMBRES_MIN.get(n_tem, n_tem)} règle{'s' if n_tem > 1 else ''} simple{'s' if n_tem > 1 else ''}. "
        "Journal d’expérience mis à jour toutes les 4 h, en simulation."
    )
AVERTISSEMENT = (
    "Expérience personnelle, pas un conseil en investissement. Les décisions sont produites par des IA, "
    "en simulation ; des pertes sont possibles. Chiffres avant impôt."
)
CSP = (
    "default-src 'none'; style-src 'self'; script-src 'self'; font-src 'self'; img-src 'none'; "
    "connect-src 'none'; base-uri 'none'; form-action 'none'"
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
    if decimals == 0:
        return f"{sign}{_group(whole)}{NBSP}€"
    return f"{sign}{_group(whole)},{frac:0{decimals}d}{NBSP}€"


def prix(ueur: int | None) -> str:
    """Prix unitaire : 2 décimales au-delà de 100 €, 4 en dessous (XRP, LINK…)."""
    if ueur is None:
        return "—"
    return eur(ueur, decimals=2 if abs(ueur) >= 100_000_000 else 4)


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


def when(ts: int | None, *, annee: bool = True) -> str:
    if ts is None:
        return "—"
    d = datetime.fromtimestamp(ts, UTC)
    a = f" {d.year}" if annee else ""
    return f"{d.day}{NBSP}{MOIS[d.month - 1]}{a}, {d:%H:%M}{NBSP}UTC"


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%MZ")


def quand(ts: int | None, *, annee: bool = True) -> str:
    """Date lisible dans un <time> (lisible par machine pour les lecteurs d'écran et le script de fraîcheur)."""
    if ts is None:
        return "—"
    return f'<time datetime="{iso(ts)}">{e(when(ts, annee=annee))}</time>'


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


def pluriel(n: int, mot: str, mots: str | None = None) -> str:
    return f"{_group(n)}{NBSP}{mot if n <= 1 else (mots or mot + 's')}"


def json_inline(obj: Any) -> str:
    """JSON sûr à placer dans <script type="application/json"> (aucun '<' ne subsiste)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def nom_court(name: str) -> str:
    for pre in ("Claude ", "Témoin "):
        name = name.removeprefix(pre)
    name = name.replace(" (adapté)", "")
    return name[:1].upper() + name[1:]


NON_APPLICABLE = '<span class="muted" aria-hidden="true">—</span><span class="visuellement-cache">sans objet</span>'


# ---------------------------------------------------------------------------
# Gabarit commun
# ---------------------------------------------------------------------------


def layout(*, title: str, body: str, root: str, active: str, data: dict[str, Any], scripts: str = "") -> str:
    def lien(p: dict[str, Any]) -> str:
        courant = ' aria-current="page"' if active == p["id"] else ""
        return f'<a href="{root}modele/{e(p["slug"])}.html"{courant}>{e(nom_court(p["name"]))}</a>'

    llms = "".join(lien(p) for p in data["portfolios"] if p["kind"] == "llm")
    tems = "".join(lien(p) for p in data["portfolios"] if p["kind"] != "llm")
    groupes = ""
    if llms:
        groupes += f'<div class="nav-groupe"><span class="nav-titre" aria-hidden="true">Modèles d’IA</span>{llms}</div>'
    if tems:
        groupes += f'<div class="nav-groupe"><span class="nav-titre" aria-hidden="true">Témoins</span>{tems}</div>'
    nav_top = (
        f'<a href="{root}index.html"{" aria-current=\"page\"" if active == "index" else ""}>Vue d’ensemble</a>'
        f'<a href="{root}methode.html"{" aria-current=\"page\"" if active == "methode" else ""}>Méthode</a>'
    )
    vm = data["venue_mode"]
    if vm == "paper":
        bandeau = f'<p class="bandeau"><span class="bandeau-point" aria-hidden="true"></span><strong>{e(BANDEAU)}</strong></p>'
    else:
        bandeau = (
            f'<p class="bandeau reel"><strong>{e(BANDEAU_REEL)}</strong>'
            f' <span class="venue">venue_mode{NBSP}: {e(vm)}</span></p>'
        )
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="robots" content="noindex, nofollow">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<title>{e(title)} · Arène de trading</title>
<meta name="description" content="{e(description(data))}">
<link rel="preload" href="{root}fonts/ibm-plex-sans-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{root}fonts/ibm-plex-serif-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{root}vendor/uPlot.min.css">
<link rel="stylesheet" href="{root}assets/site.css">
</head>
<body>
<a class="evitement" href="#contenu">Aller au contenu</a>
<header class="entete">
  {bandeau}
  <div class="wrap entete-haut">
    <a class="marque" href="{root}index.html">L’arène <span class="marque-sous">de trading</span></a>
    <nav class="nav" aria-label="Pages principales">{nav_top}</nav>
  </div>
  <nav class="wrap nav-modeles" aria-label="Portefeuilles">{groupes}</nav>
</header>
<main class="wrap" id="contenu" tabindex="-1">
{typo_fr(body)}
</main>
<footer class="pied wrap">
  <p>{typo_fr(e(AVERTISSEMENT))}</p>
  <p>Page construite le {quand(data["generated_ts"])} · journal de {pluriel(data["journal"]["n_records"], "événement")}, tête <code>{e(data["journal"]["head_hash"][:12])}…</code></p>
</footer>
<script src="{root}assets/site.js"></script>
{scripts}
</body>
</html>
"""


_TYPO = [(" ;", NNBSP + ";"), (" :", NNBSP + ":"), (" ?", NNBSP + "?"), (" !", NNBSP + "!"), ("« ", "«" + NNBSP), (" »", NNBSP + "»")]


def typo_fr(fragment: str) -> str:
    """Espaces fines insécables du français dans le texte, sans toucher aux balises <code>, <script>, aux attributs
    ni aux justifications des modèles (publiées telles quelles)."""
    import re

    out = []
    for part in re.split(r"(<code[^>]*>.*?</code>|<script[^>]*>.*?</script>|<blockquote class=\"justif\">.*?</blockquote>|<[^>]+>)", fragment, flags=re.DOTALL):
        if part.startswith("<"):
            out.append(part)
            continue
        for a, b in _TYPO:
            part = part.replace(a, b)
        out.append(part)
    return "".join(out)


def empiler(table: str, libelles: list[str]) -> str:
    """Ajoute data-label aux cellules <td> de chaque ligne (dans l'ordre des colonnes après l'en-tête de ligne) :
    sous 640 px, la feuille de style empile chaque ligne en carte « libellé : valeur » au lieu de couper le tableau."""
    import re

    def cellule(m: re.Match[str], i: Any) -> str:
        # Vide = rien de visible à lire (« — », « sans objet » caché) ; « accepté » ou « refusé » restent affichés.
        visible = re.sub(r'<span class="visuellement-cache">.*?</span>', "", m.group(2), flags=re.DOTALL)
        texte = re.sub(r"<[^>]+>", "", visible)
        vide = "" if re.search(r"\w", texte) else ' data-vide=""'
        return f'<td data-label="{e(next(i, ""))}"{vide}{m.group(1)}>{m.group(2)}</td>'

    def ligne(m: re.Match[str]) -> str:
        i = iter(libelles)
        return re.sub(r"<td((?: [^>]*)?)>(.*?)</td>", lambda c: cellule(c, i), m.group(0), flags=re.DOTALL)

    return re.sub(r"<tr(?![^>]*groupe)[^>]*>.*?</tr>", ligne, table, flags=re.DOTALL)


DASHES = [[6, 4], [2, 3], [10, 3, 2, 3], [1, 3]]
COULEUR_LLM = {"llm:claude-haiku-5-5": 0, "llm:claude-sonnet-5-5": 1, "llm:claude-opus-5-5": 2, "llm:claude-fable-5-2": 3}
N_COULEURS_LLM = 4
COULEUR_TEMOIN = {"temoin:6040": 0, "temoin:e0065": 1, "temoin:aleatoire": 2}
MIN_POINTS_COURBE = 3  # sous 3 cycles terminés, une courbe ne montre qu'une droite : le tableau suffit


def _styles(chart: dict[str, Any], focus: str | None) -> list[dict[str, Any]]:
    """Style de chaque courbe, source unique pour le graphique (chart.js) et la légende rendue ici."""
    out, llm, tem = [], 0, 0
    for s in chart["series"]:
        focused = focus is not None and s["id"] == focus
        if s["kind"] == "llm":
            k = COULEUR_LLM.get(s["id"], llm)
            st = {"color": f"--llm{k % N_COULEURS_LLM}", "dash": None, "width": 2.5}
            llm += 1
        elif s["id"] == "temoin:panier":
            st = {"color": "--tem-ref", "dash": [8, 4], "width": 2}
        else:
            k = COULEUR_TEMOIN.get(s["id"], tem)
            st = {"color": f"--tem{k % 3}", "dash": DASHES[(k + 1) % len(DASHES)], "width": 1.75}
            tem += 1
        if focused:
            st["width"], st["dash"] = 3, None
            if s["kind"] != "llm":
                st["color"] = "--accent"
        st["visible"] = focus is None or focused or s["id"] == "temoin:panier"
        out.append(st)
    return out


def _legende(chart: dict[str, Any], focus: str | None) -> str:
    """Légende rendue côté serveur (valeurs du dernier cycle) : lisible sans JavaScript et sans décalage de mise en page.
    Les boutons sont désactivés tant que le script du graphique ne les a pas pris en charge."""
    items = []
    for i, (s, st) in enumerate(zip(chart["series"], _styles(chart, focus), strict=True)):
        if not st["visible"]:
            continue
        v = s["values"][-1]
        ret = None if v is None else round(v - 100, 2) / 100
        dash = f' stroke-dasharray="{" ".join(f"{x * 0.7:g}" for x in st["dash"])}"' if st["dash"] else ""
        trait = (
            '<svg class="legende-trait" viewBox="0 0 24 8" width="24" height="8" aria-hidden="true">'
            f'<line class="trait trait{st["color"]}" x1="1" x2="23" y1="4" y2="4" stroke-width="{min(st["width"], 3):g}" stroke-linecap="round"{dash}/></svg>'
        )
        items.append(
            f'<li><button type="button" class="legende-bouton" data-serie="{i}" aria-pressed="true" disabled>{trait}'
            f'<span class="legende-nom">{e(s["name"])}</span><span class="legende-val {tone(ret)}">{pct(ret)}</span></button></li>'
        )
    quand_txt = f"Dernier cycle : {when(chart['x'][-1], annee=False)}"
    return f'<p class="legende-quand" id="legende-quand">{e(quand_txt)}</p><ul class="legende" id="legende" aria-label="Courbes affichées">{"".join(items)}</ul>'


def _chart_scripts(root: str, chart: dict[str, Any], focus: str | None) -> str:
    payload = {
        "x": chart["x"], "series": chart["series"], "styles": _styles(chart, focus),
        "short": [nom_court(s["name"]) for s in chart["series"]],
    }
    return (
        f'<script id="equity-data" type="application/json">{json_inline(payload)}</script>\n'
        f'<script src="{root}vendor/uPlot.iife.min.js"></script>\n'
        f'<script src="{root}assets/chart.js"></script>'
    )


def _chart_block(chart: dict[str, Any], *, focus_name: str | None = None, focus: str | None = None) -> str:
    n = len(chart["x"]) - 1
    if n < MIN_POINTS_COURBE:
        fait = "aucun n’est terminé" if n <= 0 else f"{pluriel(n, 'cycle terminé', 'cycles terminés')} pour l’instant"
        return (
            f'<p class="vide vide-court">Courbe à partir de {MIN_POINTS_COURBE}{NBSP}cycles ({fait}). '
            "Les rendements actuels sont dans le tableau.</p>"
        )
    if n == 1:
        periode = f"le premier cycle, le {when(chart['x'][-1])}"
    else:
        periode = f"{n}{NBSP}cycles, du {when(chart['x'][1])} au {when(chart['x'][-1])}"
    derniers = "; ".join(
        f"{s['name']} {pct((s['values'][-1] - 100) / 100) if s['values'][-1] is not None else '—'}"
        for s in chart["series"]
    )
    if focus_name and len(chart["series"]) == 1:
        label = f"Rendement net cumulé de {focus_name}, la référence, depuis le départ jusqu’après {periode}. Au dernier cycle : {derniers}."
        legende = f"Rendement net cumulé depuis le départ. Un point par cycle de 4{NBSP}h."
    elif focus_name:
        label = f"Rendement net cumulé de {focus_name}, comparé au témoin panier, depuis le départ jusqu’après {periode}. Au dernier cycle : {derniers}."
        legende = (
            f"Rendement net cumulé depuis le départ. {e(focus_name)} en trait plein, témoin panier en tirets. "
            f"Un point par cycle de 4{NBSP}h."
        )
    else:
        label = f"Rendement net cumulé des {len(chart['series'])} portefeuilles depuis le départ jusqu’après {periode}. Au dernier cycle : {derniers}."
        legende = "Les boutons ci-dessus masquent ou réaffichent une courbe ; le survol montre les valeurs d’un cycle."
    return (
        '<figure class="graphique">'
        f'<div id="chart" class="graphique-zone" role="img" aria-label="{e(label)}">'
        '<noscript><p class="vide">Le graphique a besoin de JavaScript. Les valeurs du dernier cycle sont dans la légende et le tableau ; la série complète est dans data/equity.json.</p></noscript></div>'
        f"{_legende(chart, focus)}"
        f'<figcaption>{legende}</figcaption></figure>'
    )


def _svg_barre(v: float | None, vmax: float) -> str:
    """Barre divergente autour de zéro (décorative : la valeur est écrite à côté)."""
    axe = '<rect class="barre-axe" x="49.5" y="0" width="1" height="8"/>'
    if v is None or vmax <= 0 or v == 0:
        return f'<svg class="barre" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true">{axe}</svg>'
    w = min(abs(v) / vmax, 1.0) * 48
    x = 50 if v > 0 else 50 - w
    return (
        '<svg class="barre" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true">'
        f'<rect class="barre-{tone(v)}" x="{x:.2f}" y="1" width="{w:.2f}" height="6" rx="1"/>{axe}</svg>'
    )


def _svg_jauge(ratio: float) -> str:
    w = max(0.0, min(ratio, 1.0)) * 100
    return (
        '<svg class="jauge" viewBox="0 0 100 6" preserveAspectRatio="none" aria-hidden="true">'
        f'<rect class="jauge-fond" width="100" height="6" rx="3"/><rect class="jauge-plein" width="{w:.2f}" height="6" rx="3"/></svg>'
    )


# ---------------------------------------------------------------------------
# Statuts
# ---------------------------------------------------------------------------


def jamais_decide(p: dict[str, Any]) -> bool:
    """Modèle d'IA dont aucune réponse valide n'a jamais été reçue (décisions sautées ou réponses invalides)."""
    return p["kind"] == "llm" and not p.get("n_decided")


def _raison_sauts(p: dict[str, Any]) -> str | None:
    if not p["skipped"]:
        return None
    code = max(p["skipped"].items(), key=lambda kv: kv[1])[0]
    return SAUTS.get(code, code)


def _verdict_hasard(p: dict[str, Any], min_cycles: int) -> str:
    """Pastille d'état d'une ligne ; vide quand le premier écran dit déjà tout (trop tôt pour tout le monde)."""
    d = p["distinguishable"]
    if p["id"] == "temoin:panier":
        return '<span class="pastille neutre">référence</span>'
    if jamais_decide(p):
        return '<span class="pastille warn">n’a jamais décidé</span>'
    if p["n_cycles"] < min_cycles:
        return ""
    if d and d["significant"]:
        sens = "au-dessus" if d["mean_diff"] > 0 else "en dessous"
        return f'<span class="pastille info">écart significatif ({sens} du panier)</span>'
    return '<span class="pastille neutre">non distinguable du hasard</span>'


def _sharpe_cell(p: dict[str, Any], min_cycles: int, *, detail: bool = True) -> str:
    if p["sharpe"] is None or p["sharpe_ci"] is None:
        if not detail:
            return '<span class="muted" aria-hidden="true">—</span><span class="visuellement-cache">trop tôt</span>'
        return f'<span class="muted">trop tôt</span><small class="sous">dès {min_cycles}{NBSP}cycles</small>'
    lo, hi = p["sharpe_ci"]
    return f'{num(p["sharpe"])}<small class="sous">IC 95{NBSP}% [{num(lo, 1)} ; {num(hi, 1)}]</small>'


def _rank_cell(p: dict[str, Any]) -> str:
    r = p["rank_percentile"]
    if jamais_decide(p):
        return '<span class="muted">—</span><small class="sous">sans décision</small>'
    if r is None and p.get("late"):
        return '<span class="muted">—</span><small class="sous">arrivé en cours de route</small>'
    if r is None:
        return NON_APPLICABLE
    sans = ", sans aucun achat" if p["kind"] == "llm" and not p["n_trades"] else ""
    return f'{num(r, 0)}<small class="sous">sur 100{sans}</small>'


def _cout_cell(p: dict[str, Any]) -> str:
    if p["api_cost_uusd"] is None:
        return NON_APPLICABLE
    if jamais_decide(p):
        return '<span class="muted">—</span><small class="sous">aucun appel</small>'
    return usd(p["api_cost_uusd"])


def _drawdown(p: dict[str, Any]) -> str:
    return pct(-p["max_drawdown"], signed=False) if p["max_drawdown"] else pct(0.0, signed=False)


def _cout_titre(data: dict[str, Any]) -> str:
    if data.get("decider_backend") == "abonnement":
        return 'Coût de calcul <span class="nb">équivalent API, non facturé</span>'
    return "Coût d’API"


# ---------------------------------------------------------------------------
# Vue d'ensemble
# ---------------------------------------------------------------------------


def overview_table(data: dict[str, Any]) -> str:
    mc = data["min_cycles_stats"]
    tous_tot = all(p["sharpe"] is None for p in data["portfolios"])
    vmax = max((abs(p["total_return"] or 0.0) for p in data["portfolios"]), default=0.0)
    rows = []
    for p in data["portfolios"]:
        statut = ""
        if p["halted"]:
            statut = ' <span class="pastille perte-bg">arrêté</span>'
        elif p["frozen_until_ts"]:
            statut = ' <span class="pastille warn">gelé</span>'
        verdict = _verdict_hasard(p, mc)
        verdict_html = f'<span class="verdict-ligne">{verdict}</span>' if verdict else ""
        if p["kind"] != "llm" and p.get("description"):
            verdict_html += f'<small class="desc">{e(p["description"])}</small>'
        elif p.get("late") and p.get("start_ts"):
            verdict_html += f'<small class="desc">Entré dans l’arène le {quand(p["start_ts"], annee=False)} : chiffres depuis cette date.</small>'
        inactif = " inactif" if jamais_decide(p) else ""
        rows.append(
            f'<tr class="{e(p["kind"])}{inactif}"><th scope="row"><a href="modele/{e(p["slug"])}.html">{e(p["name"])}</a>{statut}{verdict_html}</th>'
            f'<td class="n cle"><span class="{tone(p["total_return"])}">{pct(p["total_return"])}</span>{_svg_barre(p["total_return"], vmax)}</td>'
            f'<td class="n">{_rank_cell(p)}</td>'
            f'<td class="n">{eur(p["equity_ueur"])}</td>'
            f'<td class="n">{_drawdown(p)}</td>'
            f'<td class="n">{p["n_trades"]}<small class="sous">{eur(p["fees_paid_ueur"])} de frais</small></td>'
            f'<td class="n">{_cout_cell(p)}</td>'
            f'<td class="n">{_sharpe_cell(p, mc, detail=not tous_tot)}</td></tr>'
        )

    def groupe(llm: bool, titre: str) -> str:
        lignes = [r for r, p in zip(rows, data["portfolios"], strict=True) if (p["kind"] == "llm") == llm]
        if not lignes:
            return ""
        return f'<tbody><tr class="groupe"><th scope="rowgroup" colspan="8">{titre}</th></tr>{"".join(lignes)}</tbody>'

    sharpe_titre = f'Sharpe <span class="nb">dès {mc}{NBSP}cycles</span>' if tous_tot else "Sharpe"
    head = (
        '<tr><th scope="col">Portefeuille</th><th scope="col" class="n">Rendement net</th>'
        '<th scope="col" class="n">Rang <span class="nb">face au hasard</span></th><th scope="col" class="n">Valeur</th>'
        '<th scope="col" class="n">Pire baisse <span class="nb">depuis un sommet</span></th><th scope="col" class="n">Ordres <span class="nb">et frais</span></th>'
        f'<th scope="col" class="n">{_cout_titre(data)}</th><th scope="col" class="n">{sharpe_titre}</th></tr>'
    )
    libelles = ["Rendement net", "Rang face au hasard", "Valeur", "Pire baisse", "Ordres et frais", "Coût de calcul", "Sharpe"]
    return empiler(
        '<div class="table-scroll" tabindex="0" role="region" aria-label="Tableau comparatif, défilable">'
        '<table class="tableau comparatif empile"><caption class="visuellement-cache">Comparatif des portefeuilles : '
        f'modèles d’IA puis témoins</caption><thead>{head}</thead>'
        f'{groupe(True, "Modèles d’IA")}{groupe(False, "Témoins")}</table></div>',
        libelles,
    )


NOMBRES = {1: "Une", 2: "Deux", 3: "Trois", 4: "Quatre", 5: "Cinq", 6: "Six"}


def _intervalle(lo: float, hi: float) -> str:
    return pct(lo) if round(lo, 4) == round(hi, 4) else f"entre {pct(lo)} et {pct(hi)}"


def _etat(data: dict[str, Any], llms: list[dict[str, Any]], actifs: list[dict[str, Any]]) -> tuple[str, str]:
    """Phrase de tête (faits du dernier cycle) et verdict, en mots de tous les jours."""
    nc, mc, iv = data["n_cycles"], data["min_cycles_stats"], data.get("interval_s") or 14_400
    if nc == 0:
        return "Le premier cycle n’a pas encore eu lieu : les premiers chiffres arriveront juste après.", ""
    heures = nc * iv // 3600
    duree_txt = f"{heures}{NBSP}h" if heures < 48 else f"{heures // 24}{NBSP}jours"
    faits = [f"Après <b>{pluriel(nc, 'cycle')}</b> de décision ({duree_txt}),"]
    rets = [p["total_return"] or 0.0 for p in actifs]
    if llms and not actifs:
        faits.append("les modèles d’IA n’ont encore jamais décidé : seuls les témoins ont joué.")
    elif actifs and all(p["n_trades"] == 0 for p in actifs) and all(abs(r) < 5e-5 for r in rets):
        qui = "les modèles d’IA" if len(actifs) > 1 else "le modèle d’IA"
        faits.append(f"{qui} n’ont rien acheté pour l’instant : ils restent en euros, à <b>{pct(0.0)}</b>." if len(actifs) > 1
                     else f"{qui} n’a rien acheté pour l’instant : il reste en euros, à <b>{pct(0.0)}</b>.")
    elif actifs:
        faits.append(f"les modèles d’IA sont <b>{_intervalle(min(rets), max(rets))}</b>.")
    tems = [p["total_return"] or 0.0 for p in data["portfolios"] if p["kind"] != "llm"]
    if tems:
        faits.append(
            f"Les {len(tems)} témoins, des règles fixes sans IA qui servent de comparaison, sont {_intervalle(min(tems), max(tems))}."
        )
    if data["any_llm_distinguishable"]:
        verdict = "Au moins un modèle s’écarte significativement du panier. Cela ne dit rien de la suite."
    elif nc < mc:
        verdict = "Trop tôt pour conclure."
    else:
        verdict = "Aucun modèle n’est distinguable du hasard."
    return " ".join(faits), verdict


def _avancee(data: dict[str, Any]) -> str:
    nc, mc, iv = data["n_cycles"], data["min_cycles_stats"], data.get("interval_s")
    if nc >= mc:
        return f'<p class="avancee">{_svg_jauge(1.0)}<span>Seuil de {mc}{NBSP}cycles atteint : les statistiques sont calculées.</span></p>'
    vers = ""
    if data["last_cycle_ts"] and iv:
        d = datetime.fromtimestamp(data["last_cycle_ts"] + (mc - nc) * iv, UTC)
        vers = f" (vers le {d.day}{NBSP}{MOIS[d.month - 1]})"
    return (
        f'<p class="avancee">{_svg_jauge(nc / mc if mc else 1.0)}'
        f"<span>{nc} cycle{'s' if nc > 1 else ''} sur les {mc} nécessaires à un premier verdict{vers}</span></p>"
    )


def _releve(data: dict[str, Any]) -> str:
    """Ligne de relevé : dernier cycle, prochain (rafraîchi par site.js), état du journal."""
    items = []
    last, iv = data["last_cycle_ts"], data.get("interval_s")
    if last:
        items.append(f"<li>Dernier cycle : {quand(last, annee=False)}</li>")
    if last and iv:
        nxt = last + iv
        items.append(
            f'<li>Prochain : <time datetime="{iso(nxt)}" data-prochain="{nxt}" data-intervalle="{iv}">{e(when(nxt, annee=False))}</time>'
            ' <span class="releve-detail" data-fraicheur></span></li>'
        )
    j = data["journal"]
    if j["verify_ok"]:
        items.append('<li><a href="methode.html#m-journal">Historique vérifié, non modifié</a></li>')
    else:
        items.append('<li class="perte-txt"><a href="methode.html#m-journal">Journal : vérification en échec</a></li>')
    return f'<ul class="releve">{"".join(items)}</ul>'


def _frise(data: dict[str, Any]) -> str:
    """Signature : chaque cycle terminé est un maillon du journal chaîné, avec son empreinte."""
    cycles = data.get("cycles") or []
    if not cycles:
        return ""
    total = len(cycles)
    montres = cycles[-6:]
    items = []
    for i, c in enumerate(montres, start=total - len(montres) + 1):
        d = datetime.fromtimestamp(c["ts"], UTC)
        h = (c.get("hash") or "")[:8]
        items.append(
            f'<li><b>Cycle {i}</b><span>{d.day}{NBSP}{MOIS[d.month - 1]}, {d:%H}{NBSP}h</span>'
            f'<code title="Empreinte sha256 du cycle dans le journal">{e(h)}</code></li>'
        )
    iv = data.get("interval_s")
    if iv:
        d = datetime.fromtimestamp(cycles[-1]["ts"] + iv, UTC)
        items.append(f'<li class="a-venir"><b>Cycle {total + 1}</b><span>{d.day}{NBSP}{MOIS[d.month - 1]}, {d:%H}{NBSP}h</span><span>à venir</span></li>')
    avant = f" Les {total - len(montres)} précédents sont sur la page Méthode." if total > len(montres) else ""
    return (
        '<div class="frise-bloc"><ol class="frise" aria-label="Derniers cycles et leur empreinte dans le journal">'
        f'{"".join(items)}</ol>'
        f'<p class="frise-legende">Chaque cycle est scellé dans un journal chaîné : son empreinte figure ici, et la page '
        f'<a href="methode.html#m-journal">Méthode</a> dit comment la recalculer.{avant}</p></div>'
    )


def _a_faire(data: dict[str, Any], llms: list[dict[str, Any]]) -> str:
    """Une ligne pour l'opérateur : ce qu'il faut faire maintenant, ou « rien ». Absente de la version publique."""
    if data.get("public"):
        return ""
    if not data["n_cycles"]:
        return '<p class="a-faire info"><strong>Rien à faire.</strong> Le premier cycle n’a pas encore eu lieu.</p>'
    sauts = {p["name"]: r for p in llms if (r := _dernier_saut(p))}
    halted = [p["name"] for p in data["portfolios"] if p["halted"]]
    if sauts:
        raisons = sorted(set(sauts.values()))
        qui = f"les {len(llms)} modèles" if len(sauts) == len(llms) > 1 else ", ".join(sorted(sauts))
        if raisons == ["no_key"] and data.get("decider_backend") == "abonnement":
            nxt = data["last_cycle_ts"] + data["interval_s"] if data.get("interval_s") else None
            apres = f"après le cycle du {when(nxt, annee=False)}" if nxt else "après le prochain cycle"
            return (
                f'<p class="a-faire info"><strong>Rien à faire maintenant.</strong> Revenir {e(apres)} : '
                "la configuration utilise désormais l’abonnement Claude Code, les modèles doivent y avoir décidé. "
                "Sinon, voir <code>docs/RUNBOOK.md</code>.</p>"
            )
        if raisons == ["no_key"]:
            return (
                '<p class="a-faire warn"><strong>À faire.</strong> '
                f"{e(qui[0].upper() + qui[1:])} ne joue{'nt' if len(sauts) > 1 else ''} pas faute de clé d’API : déposer la clé dans "
                "<code>~/.config/arene/secrets/anthropic_api_key</code> (voir <code>docs/J0-OWNER.md</code>).</p>"
            )
        libelles = ", ".join(e(SAUTS.get(r, r)) for r in raisons)
        return (
            f'<p class="a-faire warn"><strong>À vérifier.</strong> Au dernier cycle, {e(qui)} : décision sautée ({libelles}). '
            "Voir <code>docs/RUNBOOK.md</code>.</p>"
        )
    if halted:
        return f'<p class="a-faire warn"><strong>À vérifier.</strong> Portefeuille arrêté : {e(", ".join(halted))}.</p>'
    return ""


def _dernier_saut(p: dict[str, Any]) -> str | None:
    """Raison du saut au dernier cycle journalisé, ou None si la dernière décision n'a pas été sautée."""
    d = p["decisions"][0] if p["decisions"] else None
    return d["skip_reason"] if d and d["kind"] == "skipped" else None


def index_page(data: dict[str, Any]) -> str:
    nc, mc = data["n_cycles"], data["min_cycles_stats"]
    llms = [p for p in data["portfolios"] if p["kind"] == "llm"]
    actifs = [p for p in llms if p.get("n_decided")]
    n_tem = sum(1 for p in data["portfolios"] if p["kind"] != "llm")
    nombre = NOMBRES.get(len(llms), str(len(llms)))
    if len(llms) == 1:
        titre = "Une IA gère un portefeuille crypto fictif. Fait-elle mieux que des règles simples ?"
    else:
        titre = f"{nombre} IA gèrent chacune un portefeuille crypto fictif. Font-elles mieux que des règles simples ?"
    faits, verdict = _etat(data, llms, actifs)
    verdict_html = f" <strong>{e(verdict)}</strong>" if verdict else ""
    m = data["method"]
    dist = data["distribution"]
    lecture = [
        (
            f"<li><strong>Rendement net</strong> : après frais ({bp_pct(m['taker_fee_bp'])} par ordre) et glissement "
            f"({bp_pct(m['slippage_bp'])}) simulés, avant impôt.</li>"
        ),
        "<li><strong>Non distinguable du hasard</strong> : l’écart de rendement au témoin panier n’est pas statistiquement significatif.</li>",
        f"<li><strong>Sharpe</strong> : rendement rapporté au risque pris, annualisé, avec sa fourchette à 95{NBSP}%, affiché à partir de {mc}{NBSP}cycles.</li>",
        "<li><strong>Rang face au hasard</strong> d’un modèle qui n’a rien acheté : il bat les tirages au sort parce qu’eux paient des frais, pas par talent.</li>",
    ]
    if dist:
        lecture.insert(1,
            f"<li><strong>Rang vs hasard</strong> : percentile du rendement parmi {_group(dist['n'])}{NBSP}trajectoires aléatoires "
            f"rejouées sur les mêmes cycles et les mêmes prix (médiane {pct(dist['median'])}, 90{NBSP}% entre {pct(dist['p05'])} et {pct(dist['p95'])}). "
            "50 = comme le hasard ; affiché seulement pour un portefeuille qui a décidé.</li>"
        )  # fmt: skip
    elif data["distribution_note"]:
        lecture.insert(1, f"<li><strong>Rang vs hasard</strong> : {e(data['distribution_note'])}.</li>")
    sous_titre = (
        "Frais compris, en écart au capital de départ. Modèles d’IA en couleur, témoins en gris pointillé ; "
        f"un point par cycle de {duree(data.get('interval_s') or 14_400)}."
    )
    finaux = {round(s["values"][-1], 4) for s in data["chart"]["series"] if s["kind"] == "llm" and s["values"] and s["values"][-1] is not None}
    if len(llms) > 1 and len(finaux) == 1 and all(p["n_trades"] == 0 for p in llms):
        sous_titre += f" Les {len(llms)} courbes d’IA sont confondues : aucun achat, donc aucun écart."
    body = f"""
<section class="hero" aria-labelledby="titre-etat">
  <h1 id="titre-etat">{e(titre)}</h1>
  <div class="hero-texte">
  <p class="chapo">{faits}{verdict_html}</p>
  {_avancee(data) if nc else ""}
  {_releve(data)}
  {_a_faire(data, llms)}
  </div>
</section>
<section class="courbes" aria-labelledby="titre-courbes">
  <h2 id="titre-courbes">Rendement net depuis le départ</h2>
  <p class="sous-titre">{sous_titre}</p>
  {_chart_block(data["chart"])}
  {_frise(data)}
</section>
<section aria-labelledby="titre-comparatif">
  <h2 id="titre-comparatif">Les {len(llms) + n_tem} portefeuilles</h2>
  <p class="sous-titre">Modèles d’IA puis témoins (règles fixes). Chaque nom mène à la page du portefeuille : positions, décisions et justifications.</p>
  {overview_table(data)}
  <details class="lecture"><summary>Comment lire ce tableau</summary><ul class="liste-simple">{"".join(lecture)}</ul></details>
</section>
"""
    return layout(
        title="Vue d’ensemble", body=body, root="", active="index", data=data,
        scripts=_chart_scripts("", data["chart"], None) if len(data["chart"]["x"]) - 1 >= MIN_POINTS_COURBE else "",
    )  # fmt: skip


def page_404(data: dict[str, Any], racine: str) -> str:
    """Page d'erreur : servie à n'importe quelle profondeur, d'où la racine absolue du site."""
    body = """
<section class="hero" aria-labelledby="titre-404">
  <h1 id="titre-404">Cette page n’existe pas</h1>
  <p class="chapo">L’adresse est peut-être mal recopiée, ou la page a été renommée. Le journal, lui, n’a rien perdu.</p>
  <p class="actions-404"><a class="bouton" href="{r}index.html">Revenir à la vue d’ensemble</a> <a href="{r}methode.html">Lire la méthode</a></p>
</section>
""".replace("{r}", e(racine))
    return layout(title="Page introuvable", body=body, root=racine, active="", data=data)


# ---------------------------------------------------------------------------
# Page modèle
# ---------------------------------------------------------------------------


def _stat(label: str, value: str, extra: str = "", cls: str = "", carte: str = "") -> str:
    return f'<div class="stat {carte}"><dt>{label}</dt><dd class="{cls}">{value}{extra}</dd></div>'


def _positions(p: dict[str, Any]) -> str:
    if not p["positions"]:
        return f'<p class="vide">Aucune position détenue : tout est en cash ({eur(p["cash_ueur"])}).</p>'
    avec_stop = any(x["stop_ueur"] for x in p["positions"])
    rows = "".join(
        f'<tr><th scope="row">{e(x["symbol"])}</th><td class="n">{e(qty_fmt(x["qty"]))}</td>'
        f'<td class="n">{eur(x["cost_ueur"])}</td><td class="n">{eur(x["value_ueur"])}</td>'
        f'<td class="n {tone(x["unrealized_ueur"])}">{eur(x["unrealized_ueur"], signed=True)}</td>'
        + (f'<td class="n">{prix(x["stop_ueur"]) if x["stop_ueur"] else "—"}</td>' if avec_stop else "")
        + f'<td>{quand(x["opened_ts"])}</td></tr>'
        for x in p["positions"]
    )
    tot_cout = sum(x["cost_ueur"] for x in p["positions"])
    vals = [x["value_ueur"] for x in p["positions"]]
    tot_val = None if any(v is None for v in vals) else sum(vals)
    tot_lat = None if tot_val is None else tot_val - tot_cout
    vide = "<td></td>" if avec_stop else ""
    pied = (
        f'<tfoot><tr><th scope="row">Total des positions</th><td></td><td class="n">{eur(tot_cout)}</td><td class="n">{eur(tot_val)}</td>'
        f'<td class="n {tone(tot_lat)}">{eur(tot_lat, signed=True)}</td>{vide}<td></td></tr>'
        f'<tr><th scope="row">Cash</th><td></td><td></td><td class="n">{eur(p["cash_ueur"])}</td><td></td>{vide}<td></td></tr></tfoot>'
    )
    stop_th = '<th scope="col" class="n">Stop</th>' if avec_stop else ""
    libelles = ["Quantité", "Coût, frais inclus", "Valeur au dernier bid", "Latent"] + (["Stop"] if avec_stop else []) + ["Ouverte le"]
    return empiler(
        '<div class="table-scroll" tabindex="0" role="region" aria-label="Tableau des positions, défilable"><table class="tableau empile">'
        '<caption class="visuellement-cache">Positions courantes, valorisées au dernier prix acheteur (bid)</caption>'
        '<thead><tr><th scope="col">Paire</th><th scope="col" class="n">Quantité</th><th scope="col" class="n">Coût <span class="nb">frais inclus</span></th>'
        '<th scope="col" class="n">Valeur <span class="nb">au dernier bid</span></th><th scope="col" class="n">Latent</th>'
        f'{stop_th}<th scope="col">Ouverte le</th></tr></thead><tbody>{rows}</tbody>{pied}</table></div>',
        libelles,
    )


def _codes(reasons: list[str]) -> str:
    return "".join(
        f'<span class="code">{e(CODES_RISQUE.get(c, "règle inconnue"))} <code>{e(c)}</code></span>' for c in reasons
    )


def _motif(reason: str) -> str:
    return {"intent": "ordre", "stop": "stop touché", "max_holding": "détention maximale", "kill_switch": "coupe-circuit"}.get(
        reason, reason
    )


def _execution(fills: list[dict[str, Any]]) -> str:
    if not fills:
        return '<span class="muted">non exécuté</span>'
    return "".join(
        f'<span class="exec">{e(qty_fmt(f["qty"]))} à {prix(f["price_ueur"])}'
        f'<small class="sous">frais {eur(f["fee_ueur"], decimals=4)}</small></span>'
        for f in fills
    )


def _intention(a: dict[str, Any]) -> str:
    if a["side"] == "buy":
        parts = [f'<strong>Achat</strong> · {bp_pct(a["size_bp"])} du portefeuille']
        if a.get("stop_bp") is not None:
            parts.append(f'stop {bp_pct(a["stop_bp"])} sous l’entrée')
        if a.get("expected_move_bp") is not None:
            parts.append(f'hausse attendue {bp_pct(a["expected_move_bp"])}')
        return " · ".join(parts)
    return f'<strong>Vente</strong> · {bp_pct(a["size_bp"])} de la position'


def _verdict_risque(a: dict[str, Any]) -> str:
    if a["approved"] is None:
        return '<span class="pastille neutre">sans verdict</span>'
    if a["approved"]:
        return '<span class="pastille ok">accepté</span>'
    return f'<span class="pastille perte-bg">refusé</span><span class="codes">{_codes(a["reasons"])}</span>'


def _actions_table(actions: list[dict[str, Any]], cycle: int) -> str:
    rows = "".join(
        f'<tr><th scope="row">{e(a["symbol"])}</th><td>{_intention(a)}</td><td>{_verdict_risque(a)}</td>'
        f'<td class="n">{_execution(a["fills"])}</td></tr>'
        for a in actions
    )
    return empiler(
        f'<div class="table-scroll actions-scroll" tabindex="0" role="region" aria-label="Actions du cycle du {e(when(cycle))}, défilable">'
        '<table class="tableau actions empile"><thead><tr><th scope="col">Paire</th>'
        '<th scope="col">Intention</th><th scope="col">Contrôle de risque</th><th scope="col" class="n">Exécution</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div>',
        ["Intention", "Contrôle de risque", "Exécution"],
    )


def _sorties(fills: list[dict[str, Any]]) -> str:
    if not fills:
        return ""
    items = "".join(
        f'<li><strong>Sortie forcée</strong> ({e(_motif(f["reason"]))}) : vente de {e(qty_fmt(f["qty"]))} {e(f["symbol"])} '
        f'à {prix(f["price_ueur"])}, frais {eur(f["fee_ueur"], decimals=4)} <span class="muted">· {quand(f["ts"], annee=False)}</span></li>'
        for f in fills
    )
    return f'<ul class="sorties">{items}</ul>'


def _justif(d: dict[str, Any]) -> str:
    if not d.get("a_justification"):
        return ""
    return f'<blockquote class="justif"><span class="etiquette">Raisonnement du modèle</span>{e(d["justification"])}</blockquote>'


def _meta(d: dict[str, Any], equivalent: bool = False) -> str:
    meta = []
    if d.get("model_returned"):
        meta.append(f'<code>{e(d["model_returned"])}</code>')
    if d.get("output_tokens"):
        meta.append(f'{_group(d["input_tokens"] or 0)}{NBSP}jetons en entrée, {_group(d["output_tokens"])} en sortie')
    if d.get("cost_uusd"):
        meta.append(f'coût {"équivalent API " if equivalent else ""}{usd(d["cost_uusd"])}')
    return f'<span class="decision-meta">{" · ".join(meta)}</span>' if meta else ""


def _decision_compact(d: dict[str, Any], equivalent: bool = False) -> str | None:
    """Ligne d'une décision sans action ni sortie (le plus fréquent) ; None si elle mérite une carte entière."""
    if d["actions"] or d["sorties"]:
        return None
    if d["kind"] == "skipped":
        raison = SAUTS.get(d["skip_reason"], d["skip_reason"])
        return (
            f'<li class="ligne"><span class="quand">{quand(d["cycle"])}</span>'
            f'<span class="pastille warn">sautée</span> <span class="muted">{e(raison)}</span></li>'
        )
    if d["kind"] == "temoin":
        return (
            f'<li class="ligne"><span class="quand">{quand(d["cycle"])}</span>'
            '<span class="muted">Règle appliquée : aucun ordre</span></li>'
        )
    if d["kind"] != "decided":
        return None
    corps = _justif(d)
    resume = f'<span class="quand">{quand(d["cycle"])}</span><span class="muted">Aucun ordre</span>{_meta(d, equivalent)}'
    if not corps:
        return f'<li class="ligne">{resume}</li>'
    return f'<li class="ligne"><details><summary>{resume}</summary>{corps}</details></li>'


def _decision_html(d: dict[str, Any], equivalent: bool = False) -> str:
    compact = _decision_compact(d, equivalent)
    if compact is not None:
        return compact
    if d["kind"] == "skipped":
        tete = f'<span class="pastille warn">sautée</span> <span>{e(SAUTS.get(d["skip_reason"], d["skip_reason"]))}</span>'
    elif d["kind"] == "parse_error":
        tete = f'<span class="pastille warn">réponse invalide</span> <span>{e(d["parse_error"])}</span>'
    elif d["kind"] == "temoin":
        tete = '<span class="pastille neutre">règle mécanique</span>'
    else:
        tete = ""
    actions = _actions_table(d["actions"], d["cycle"]) if d["actions"] else ""
    if d["kind"] == "decided" and not d["actions"]:
        actions = '<p class="muted">Aucune action ce cycle.</p>'
    if d["actions"]:
        tete = f"{tete}<span class=\"resume-ordres\">{e(_resume_ordres(d['actions']))}</span>"
    justif = _justif(d)
    ordres = f"{actions}{_sorties(d['sorties'])}"
    corps = (
        f'<div class="decision-corps">{justif}<div class="decision-ordres">{ordres}</div></div>'
        if justif and d["actions"] else f"{ordres}{justif}"
    )
    return (
        f'<li class="decision"><article><header><h3>{quand(d["cycle"])}</h3>{tete}{_meta(d, equivalent)}</header>'
        f"{corps}</article></li>"
    )


def _resume_ordres(actions: list[dict[str, Any]]) -> str:
    """En-tête d'une décision avec ordres : « Achat BTC/EUR, vente ETH/EUR »."""
    mots = [f'{"achat" if a["side"] == "buy" else "vente"} {a["symbol"]}' for a in actions]
    txt = ", ".join(mots)
    return txt[:1].upper() + txt[1:]


def model_page(data: dict[str, Any], p: dict[str, Any], baseline_chart: dict[str, Any]) -> str:
    mc = data["min_cycles_stats"]
    llm = p["kind"] == "llm"
    communs = [
        _stat("Rendement net", pct(p["total_return"]), cls=f"grand {tone(p['total_return'])}", carte="cle"),
        _stat("Valeur du portefeuille", eur(p["equity_ueur"]), f'<small class="sous">départ {eur(p["capital_ueur"], decimals=0)}</small>'),
        _stat("Pire baisse <span class=\"nb\">depuis un sommet</span>", _drawdown(p)),
        _stat("Rang <span class=\"nb\">face au hasard</span>", _rank_cell(p)),
        _stat(f"Sharpe <span class=\"nb\">fourchette à 95{NBSP}%</span>", _sharpe_cell(p, mc)),
    ]
    if llm:
        n_dec = p.get("n_decided") or 0
        n_saut = sum(p["skipped"].values())
        raison = _raison_sauts(p)
        saut_txt = (
            f'<small class="sous">{pluriel(n_saut, "sautée", "sautées")}{f" : {e(raison)}" if raison else ""}</small>' if n_saut else ""
        )
        extra = [
            _stat("Ordres", str(p["n_trades"]), f'<small class="sous">{eur(p["fees_paid_ueur"])} de frais</small>'),
            _stat(_cout_titre(data), _cout_cell(p)),
            _stat("Décisions reçues", str(n_dec), saut_txt),
        ]
    else:
        extra = [
            _stat("Ordres", str(p["n_trades"])),
            _stat("Frais payés", eur(p["fees_paid_ueur"])),
            _stat("Cash", eur(p["cash_ueur"])),
        ]
    stats_html = "".join(communs + extra)
    alertes = []
    if p["halted"]:
        alertes.append('<p class="alerte perte-bg">Portefeuille arrêté : drawdown maximal atteint, positions mises à plat.</p>')
    elif p["frozen_until_ts"]:
        alertes.append(f'<p class="alerte warn">Portefeuille gelé jusqu’au {quand(p["frozen_until_ts"])}.</p>')
    if jamais_decide(p):
        raison = _raison_sauts(p)
        pourquoi = f" : {e(raison)}" if raison else ""
        alertes.append(
            f'<p class="alerte warn">Ce modèle n’a encore jamais décidé{pourquoi}. Ses chiffres sont ceux d’un portefeuille resté en cash.</p>'
        )
    verdict = "" if jamais_decide(p) else _verdict_hasard(p, mc)  # l'alerte le dit déjà
    resume = []
    if p["skipped"] and not jamais_decide(p):
        resume.append(
            "<p><strong>Décisions sautées</strong> : "
            + ", ".join(f"{e(SAUTS.get(r, r))} ({n})" for r, n in sorted(p["skipped"].items(), key=lambda kv: -kv[1]))
            + ".</p>"
        )
    if p["rejects"]:
        resume.append(
            "<p><strong>Ordres refusés par le contrôle de risque</strong> : "
            + ", ".join(
                f"{e(CODES_RISQUE.get(c, c))} <code>{e(c)}</code> ({n})"
                for c, n in sorted(p["rejects"].items(), key=lambda kv: -kv[1])
            )
            + ".</p>"
        )
    equivalent = data.get("decider_backend") == "abonnement"
    decs = "".join(_decision_html(d, equivalent) for d in p["decisions"])
    reste = p["decisions_total"] - len(p["decisions"])
    reste_html = (
        f'<p class="muted">{pluriel(reste, "décision plus ancienne", "décisions plus anciennes")} '
        f'non affichée{"s" if reste > 1 else ""} (elles restent dans le journal).</p>'
        if reste > 0 else ""
    )  # fmt: skip
    decs_html = f'<ol class="decisions">{decs}</ol>' if decs else '<p class="vide">Aucune décision journalisée pour ce portefeuille.</p>'
    desc = p["description"] or (
        f"Modèle d’IA : décide toutes les 4{NBSP}h à partir d’un résumé chiffré du marché calculé par le code ; "
        "le contrôle de risque valide chaque ordre, le simulateur l’exécute."
    )
    note_dec = (
        "Du plus récent au plus ancien. Quand le modèle passe des ordres, son raisonnement est affiché à côté, "
        "avec le verdict du contrôle de risque et l’exécution ; les cycles sans ordre sont repliés."
        if llm
        else "Du plus récent au plus ancien. Les témoins appliquent une règle fixe ; le contrôle de risque les vérifie comme les modèles."
    )
    if p.get("late") and p.get("start_ts"):
        alertes.append(
            f'<p class="alerte info">Entré dans l’arène le {quand(p["start_ts"])}, après les autres portefeuilles : '
            "ses chiffres courent depuis cette date et il n’est pas classé face au hasard, calculé sur toute la période.</p>"
        )
    titre_h1 = f'<h1>{e(p["name"])}</h1>'
    verdict_html = f'<p class="verdict-tete">{verdict}</p>' if verdict else ""
    body = f"""
<p class="fil"><a href="../index.html"><span aria-hidden="true">← </span>Vue d’ensemble</a><span class="fil-sep" aria-hidden="true">/</span><span>{"Modèles d’IA" if llm else "Témoins"}</span></p>
<header class="tete-modele">
  {titre_h1}{verdict_html}
  <p class="chapo">{e(desc)}</p>
</header>
{"".join(alertes)}
<dl class="stats">{stats_html}</dl>
<section aria-labelledby="titre-courbe"><h2 id="titre-courbe">Rendement net depuis le départ</h2>{_chart_block(baseline_chart, focus_name=p["name"], focus=p["id"])}</section>
<section aria-labelledby="titre-positions"><h2 id="titre-positions">Positions courantes</h2>{_positions(p)}
<p class="muted note">Positions fictives, publiées pour suivre l’expérience : ce n’est ni un conseil ni un signal.</p></section>
<section aria-labelledby="titre-decisions"><h2 id="titre-decisions">Décisions</h2>
<p class="muted note">{note_dec}</p>
{"".join(resume)}
{decs_html}{reste_html}
</section>
"""
    return layout(
        title=p["name"], body=body, root="../", active=p["id"], data=data,
        scripts=_chart_scripts("../", baseline_chart, p["id"]) if len(baseline_chart["x"]) - 1 >= MIN_POINTS_COURBE else "",
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


def _liste_modeles(data: dict[str, Any]) -> tuple[str, str]:
    """(« Quatre modèles d’IA (Claude Haiku 5.5, Sonnet 5.5, Opus 5.5 et Fable 5.2) », phrase sur les arrivées).
    Compte les portefeuilles ouverts, comme l'accueil ; un modèle configuré mais pas encore ouvert est annoncé à part."""
    ouverts = [p for p in data["portfolios"] if p["kind"] == "llm"]
    ids = {p["id"] for p in ouverts}
    noms = [p["name"] if i == 0 else p["name"].removeprefix("Claude ") for i, p in enumerate(ouverts)]
    k = len(noms)
    liste = (noms[0] if k == 1 else ", ".join(noms[:-1]) + " et " + noms[-1]) if noms else ""
    tete = f"{NOMBRES.get(k, str(k))} modèle{'s' if k > 1 else ''} d’IA" + (f" ({liste})" if liste else "")
    notes = [
        f"{p['name']} est entré dans l’arène le {quand(p['start_ts'], annee=False)}, après les autres ; ses chiffres courent depuis cette date."
        for p in ouverts
        if p.get("late") and p.get("start_ts")
    ]
    notes += [f"{nom(mo['portfolio'])} rejoindra l’arène au prochain cycle." for mo in data["method"]["models"] if mo["portfolio"] not in ids]
    return tete, (" " + " ".join(notes)) if notes else ""


def methode_page(data: dict[str, Any]) -> str:
    m, j, pv = data["method"], data["journal"], data["provenance"]
    n_tem = sum(1 for p in data["portfolios"] if p["kind"] != "llm")
    phrase_modeles, arrivees = _liste_modeles(data)
    pol_rows = "".join(
        f'<tr><th scope="row">{e(POLITIQUE_LIBELLES[k][0])}</th><td class="n" data-label="Valeur">{e(_policy_value(k, v)[0])}</td>'
        f'<td class="muted" data-label="Base">{e(_policy_value(k, v)[1])}</td></tr>'
        for k, v in m["policy"].items()
        if k in POLITIQUE_LIBELLES
    )
    ok = j["verify_ok"]
    verif = (
        f'<p><span class="pastille {"ok" if ok else "perte-bg"}">Vérification du journal : {"chaîne intacte" if ok else "ÉCHEC"}</span> '
        f'{pluriel(j["n_records"], "événement")}, dernier seq {e(j["head_seq"])}.</p>'
    )
    if j["errors"]:
        verif += "<ul class=\"liste-simple\">" + "".join(
            f'<li><code>{e(x["code"])}</code> ligne {x["line"]} : {e(x["message"])}</li>' for x in j["errors"]
        ) + "</ul>"
    modeles = "".join(
        f'<tr><th scope="row"><code>{e(x["model"])}</code></th><td class="n" data-label="Budget par jour">{usd(x["daily_budget_uusd"])}</td>'
        f'<td class="n" data-label="Prix par million de jetons, entrée / sortie">{usd(x["price_in_uusd_per_mtok"])} / {usd(x["price_out_uusd_per_mtok"])}</td></tr>'
        for x in m["models"]
    )
    policy_same = (
        pv["journal_policy_sha256"] is None or pv["journal_policy_sha256"] == pv["policy_sha256"]
    )
    prompts = ", ".join(f'<code>{e(h)}</code>' for h in pv["prompt_hashes"]) or "non journalisé"
    if data.get("decider_backend") == "abonnement" and data.get("public"):
        backend = "<p>Le coût affiché est l’équivalent au prix catalogue de l’API ; il sert de garde-fou de quota.</p>"
    elif data.get("decider_backend") == "abonnement":
        backend = (
            "<p>Les modèles sont appelés par l’abonnement Claude Code : rien n’est facturé à l’usage. "
            "Le coût affiché est l’équivalent au prix catalogue renvoyé par la CLI ; il sert de garde-fou de quota.</p>"
        )
    elif data.get("decider_backend") == "api":
        backend = "<p>Les modèles sont appelés par l’API Anthropic ; le coût affiché est calculé avec les prix ci-dessous.</p>"
    else:
        backend = ""
    divergence = "" if policy_same else ' <span class="pastille perte-bg">différente du dernier chargement journalisé</span>'
    body = f"""
<header class="tete-modele">
  <h1>Méthode</h1>
  <p class="chapo">L’expérience telle qu’elle est paramétrée aujourd’hui, ses règles et ses limites.</p>
</header>

<section aria-labelledby="m-arene"><h2 id="m-arene">Ce que fait l’arène</h2>
<p>{phrase_modeles} et {NOMBRES_MIN.get(n_tem, n_tem)} témoins gèrent chacun {eur(m["capital_ueur"], decimals=0)} fictifs sur 6 paires cotées en euros
chez Kraken. Toutes les {duree(m["interval_s"])}, chaque portefeuille décide ; un module de contrôle des risques accepte ou refuse chaque ordre voulu ;
un simulateur pessimiste exécute les ordres acceptés. Achats uniquement (pas de vente à découvert), sans effet de levier. Chaque événement est écrit dans un journal chaîné.{arrivees}</p></section>

<section aria-labelledby="m-temoins"><h2 id="m-temoins">Les témoins</h2>
<dl class="regles">
<div><dt>Panier</dt><dd>1/6 de l’equity sur chaque paire au premier cycle (frais compris), puis conservé : achat et conservation.</dd></div>
<div><dt>60/40</dt><dd>60{NBSP}% en BTC, 40{NBSP}% en cash, rééquilibré le premier cycle de chaque mois civil.</dd></div>
<div><dt>E0065 (adapté)</dt><dd>Règle fixe fondée sur la pression acheteuse, c’est-à-dire la part des achats passés au prix du marché (E0065 est son nom de code) : L = {m["e0065"]["L"]}, k = {m["e0065"]["k"]}, H = {m["e0065"]["H"]}. Adaptée : univers des 6 paires, ratio taker calculé sur les bougies journalières Binance USDT, exécution au prix Kraken EUR, reconstitution tous les {m["e0065"]["H"]} jours.</dd></div>
<div><dt>Aléatoire</dt><dd>À chaque cycle, 0 à 2 actions tirées au hasard dans le même espace d’actions que les modèles, avec exactement les mêmes règles de risque. Hors ligne, {_group(m["n_trajectoires"])}{NBSP}trajectoires sont rejouées sur les mêmes cycles et les mêmes prix ; le rang d’un portefeuille est son percentile dans cette distribution.</dd></div>
</dl></section>

<section aria-labelledby="m-frais"><h2 id="m-frais">Frais et glissement simulés</h2>
<p>Modèle d’exécution <code>{e(m["fill_model_version"])}</code> : ordres au marché uniquement. Achat au prix vendeur (ask) majoré de {bp_pct(m["slippage_bp"])}, vente au prix acheteur (bid) minoré de {bp_pct(m["slippage_bp"])},
arrondis au pas de prix dans le sens défavorable. Frais de {bp_pct(m["taker_fee_bp"])} du montant de chaque ordre (taker Kraken de base majoré de 25{NBSP}%), arrondis vers le haut.
Quantités arrondies vers le bas. Un stop est posé à l’entrée ; la détention est limitée à {duree(policy_max_holding(m))}. Les positions sont valorisées au dernier bid.</p></section>

<section aria-labelledby="m-risque"><h2 id="m-risque">Politique de risque (simulation)</h2>
<p class="muted">Valeurs de la simulation, plus souples que ne le serait une politique réelle.</p>
<div class="table-scroll" tabindex="0" role="region" aria-label="Tableau de la politique de risque, défilable"><table class="tableau empile"><caption class="visuellement-cache">Règles du contrôle de risque</caption>
<thead><tr><th scope="col">Règle</th><th scope="col" class="n">Valeur</th><th scope="col">Base</th></tr></thead><tbody>{pol_rows}</tbody></table></div></section>

<section aria-labelledby="m-modeles"><h2 id="m-modeles">Modèles d’IA et coût</h2>
{backend}
<div class="table-scroll" tabindex="0" role="region" aria-label="Tableau des modèles, défilable"><table class="tableau empile"><caption class="visuellement-cache">Budget et prix des modèles</caption>
<thead><tr><th scope="col">Modèle</th><th scope="col" class="n">Budget par jour</th><th scope="col" class="n">Prix par million de jetons <span class="nb">entrée / sortie</span></th></tr></thead><tbody>{modeles}</tbody></table></div>
<p class="muted note">Le prompt système est versionné et son hash est journalisé : {prompts}. Un modèle n’a accès qu’à des barres closes calculées par le code, aucun texte web.
Une décision peut être sautée (modèle pas encore branché, budget quotidien atteint, portefeuille gelé…) ; ces décisions sont comptées sur la page de chaque modèle.</p></section>

<section aria-labelledby="m-journal"><h2 id="m-journal">Intégrité du journal</h2>
{verif}
<dl class="empreintes">
<div><dt>Tête de chaîne</dt><dd><code class="hash">{e(j["head_hash"])}</code></dd></div>
<div><dt>Politique de risque (sha256)</dt><dd><code class="hash">{e(pv["policy_sha256"])}</code>{divergence}</dd></div>
<div><dt>Configuration (sha256)</dt><dd><code class="hash">{e(pv["config_sha256"])}</code></dd></div>
<div><dt>Commit</dt><dd><code>{e(pv["git_head"] or "non journalisé")}</code></dd></div>
<div><dt>Mode d’exécution</dt><dd>{"simulation (aucun ordre réel)" if data["venue_mode"] == "paper" else e(data["venue_mode"])}</dd></div>
</dl></section>

<section aria-labelledby="m-limites"><h2 id="m-limites">Limites, sans maquillage</h2>
<ul class="liste-simple">
<li><strong>Simulation.</strong> Aucun ordre réel n’est passé. Un vrai ordre aurait des refus, des exécutions partielles, des pannes et un impact sur le marché que ce simulateur ne reproduit pas.</li>
<li><strong>Frais pessimistes, modèle simplifié.</strong> Les frais et le glissement sont volontairement élevés, mais le glissement est constant et ne dépend ni de la taille ni de la profondeur du carnet.</li>
<li><strong>Petit échantillon.</strong> Quelques jours à quelques semaines de décisions toutes les 4{NBSP}h ne distinguent presque jamais un modèle du hasard. C’est pourquoi le Sharpe et son intervalle n’apparaissent qu’à partir de {data["min_cycles_stats"]}{NBSP}cycles, et pourquoi « non distinguable du hasard » est le verdict par défaut.</li>
<li><strong>Ce que le journal chaîné prouve.</strong> Qu’aucun événement n’a été modifié, supprimé ou réordonné après coup : chaque ligne contient le hash de la précédente, et le rejeu du journal redonne les chiffres affichés.</li>
<li><strong>Ce qu’il ne prouve pas.</strong> Qu’il n’y a pas eu de triche avant l’écriture : rien n’atteste, à lui seul, que les prix journalisés sont ceux du marché ni que les décisions n’ont pas été choisies parmi plusieurs essais.</li>
<li><strong>Univers étroit et période courte.</strong> 6 cryptos, long seulement ; un résultat ici ne se transpose pas à d’autres marchés, d’autres périodes ni à de l’argent réel.</li>
<li><strong>Avant impôt.</strong> Les chiffres ne tiennent pas compte de la fiscalité.</li>
</ul></section>

<section class="avis" aria-labelledby="m-avertissement"><h2 id="m-avertissement">Avertissement</h2>
<p><strong>Ce n’est pas un conseil en investissement.</strong> Expérience personnelle de simulation ; aucune recommandation, aucun signal, aucune promesse de rendement. Les performances passées, simulées de surcroît, ne préjugent pas des performances futures. Investir dans des crypto-actifs comporte un risque de perte totale.</p></section>
"""
    return layout(title="Méthode", body=body, root="", active="methode", data=data)


def policy_max_holding(m: dict[str, Any]) -> int:
    return int(m["policy"]["max_holding_s"])
