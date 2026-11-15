"""Accueil des trois ligues et tableau des scores partagé (direction « Tableau des scores », 15/11/2026).

Le premier écran de chaque ligue : une phrase qui dit l'expérience, puis le classement et la courbe côte à côte.
Pas de gros titre (décision du propriétaire du 15/11) : ce sont les rendements et la courbe qui portent l'écran.
"""

from __future__ import annotations

from typing import Any

from arene.site import render as R
from arene.site.render import NBSP, e, eur, layout, pct, tone


def couleurs(chart: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Style de chaque série (id → style de render._styles) : la pastille du classement a la couleur de sa courbe."""
    return {s["id"]: st for s, st in zip(chart["series"], R._styles(chart, None), strict=True)}


def pastille(st: dict[str, Any] | None) -> str:
    if not st:
        return '<span class="sw sw-ref" aria-hidden="true"></span>'
    pointille = " sw-ref" if st.get("dash") else ""
    return f'<span class="sw c{e(st["color"])}{pointille}" aria-hidden="true"></span>'


def _ex_aequo(rows: list[dict[str, Any]]) -> None:
    """Rangs ex æquo : deux rendements égaux (au centième de pour cent affiché) ont le même rang."""
    prec, rang = None, 0
    for i, r in enumerate((r for r in rows if r.get("rang")), 1):
        v = None if r.get("rend") is None else round(r["rend"] * 10_000)
        if v != prec:
            rang, prec = i, v
        r["rang"] = rang


def scores(rows: list[dict[str, Any]], *, label: str, mini: bool = False) -> str:
    """Classement : rang, pastille couleur de courbe, nom (lien) et sous-titre, rendement en grand.

    Chaque ligne : {nom, href, sous, rend (fraction ou None), st (style de courbe), rang (int ou None), attrs (crochets
    du direct), valeur (texte facultatif)}. Le rang absent (référence, arrivé en cours de route) s'écrit « réf. » ou «—»."""
    _ex_aequo(rows)
    items = []
    for r in rows:
        rang = str(r["rang"]) if r.get("rang") else ("réf." if r.get("ref") else "—")
        sous = f'<span class="sc-sous">{e(r["sous"])}</span>' if r.get("sous") else ""
        val = f'<span class="sc-eur">{r["valeur"]}</span>' if r.get("valeur") else ""
        items.append(
            f'<li class="sc{" sc-ref" if r.get("ref") else ""}"><span class="sc-rang">{rang}</span>{pastille(r.get("st"))}'
            f'<span class="sc-nom"><a href="{e(r["href"])}">{e(r["nom"])}</a>{sous}</span>'
            f'<span class="sc-val"><span class="{tone(r.get("rend"))}"{r.get("attrs", "")}>{pct(r.get("rend"))}</span>{val}</span></li>'
        )
    return f'<ol class="scores{" mini" if mini else ""}" aria-label="{e(label)}">{"".join(items)}</ol>'


def une(*, titre: str, chapo: str, classement: str, courbe: str, apres: str = "") -> str:
    """Premier écran d'une ligue : la phrase, puis classement et courbe côte à côte (empilés sur téléphone)."""
    return (
        f'<section class="une" aria-labelledby="titre-page"><h1 id="titre-page" class="titre-page">{titre}</h1>'
        f'<p class="chapo-page">{chapo}</p>'
        f'<div class="une-grille"><div class="une-classement">{classement}{apres}</div>'
        f'<div class="une-courbe">{courbe}</div></div></section>'
    )


def sparkline(chart: dict[str, Any], ids: list[str]) -> str:
    """Petite courbe décorative (les valeurs sont écrites à côté) : la série de chaque id, à l'échelle commune."""
    styles = couleurs(chart)
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

    lignes = [f'<line class="spark-zero" x1="0" x2="{w}" y1="{y(100.0)}" y2="{y(100.0)}"/>']
    for s in series:
        pts = " ".join(
            f"{round((x - x0) / max(1, x1 - x0) * w, 1)},{y(v)}"
            for x, v in zip(chart["x"], s["values"], strict=True)
            if v is not None
        )
        st = styles.get(s["id"]) or {}
        pointille = " spark-ref" if st.get("dash") else ""
        lignes.append(
            f'<polyline class="spark-l s{e(st.get("color", "--muted"))}{pointille}" points="{pts}"/>'
        )
    return f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">{"".join(lignes)}</svg>'


def _perp_rows(ligue: dict[str, Any], dossier_conseil: bool = False) -> list[dict[str, Any]]:
    from arene.site import perp as P
    from arene.site import render_perp as RP

    st = couleurs(ligue["chart"])
    pfs = ligue["portfolios"]
    joueurs = sorted(
        (p for p in pfs if p["kind"] in ("llm", "conseil")), key=lambda p: -(p["rendement"] or 0.0)
    )
    rows = []
    for i, p in enumerate(joueurs, 1):
        rows.append({
            "nom": p["name"], "href": f"{RP._dossier(p)}/{p['slug']}.html", "rend": p["rendement"], "st": st.get(p["id"]),
            "rang": i, "sous": p.get("sous_titre") or "", "attrs": RP._crochet(p, "rend"),
        })  # fmt: skip
    panier = next((p for p in pfs if p["id"] == P.PANIER), None)
    if panier:
        rows.append({
            "nom": "Témoin sans IA", "href": f"{RP._dossier(panier)}/{panier['slug']}.html", "rend": panier["rendement"],
            "st": st.get(panier["id"]), "ref": True, "sous": "achète et garde les 6 cryptos, sans levier",
            "attrs": RP._crochet(panier, "rend"),
        })  # fmt: skip
    return rows


def _spot_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    st = couleurs({"series": data["chart"]["series"]}) if data.get("chart") else {}
    pfs = data["portfolios"]
    llms = sorted((p for p in pfs if p["kind"] == "llm"), key=lambda p: -(p["total_return"] or 0.0))
    rows = [
        {
            "nom": p["name"],
            "href": f"modele/{p['slug']}.html",
            "rend": p["total_return"],
            "st": st.get(p["id"]),
            "rang": i,
            "sous": "n’a encore rien acheté : tout en cash" if not p.get("n_trades") else "",
        }
        for i, p in enumerate(llms, 1)
    ]
    panier = next((p for p in pfs if p["id"] in R.REFERENCES), None)
    if panier:
        rows.append({
            "nom": "Témoin sans IA", "href": f"modele/{panier['slug']}.html", "rend": panier["total_return"],
            "st": st.get(panier["id"]), "ref": True, "sous": "achète et garde, sans levier",
        })  # fmt: skip
    return rows


def _carte(*, href: str, titre: str, quoi: str, rows: list[dict[str, Any]], spark: str, label: str) -> str:
    haut = [r for r in rows if not r.get("ref")][:2] + [r for r in rows if r.get("ref")]
    return (
        f'<article class="ligue-carte"><h2 class="ligue-titre"><a href="{href}">{titre}</a></h2>'
        f'<p class="ligue-quoi">{quoi}</p>{spark}{scores(haut, label=label, mini=True)}'
        f'<p class="ligue-lien"><a href="{href}">Voir la ligue, les décisions et leurs raisons<span aria-hidden="true">→</span></a></p></article>'
    )


def accueil_page(data: dict[str, Any]) -> str:
    """L'accueil : ce qu'est l'expérience en deux phrases, puis une carte par ligue avec son meneur."""
    perp = data["perp"]
    cartes = []
    capital = eur(1_000_000_000, decimals=0)
    cons = perp.get("conseils")
    if cons:
        rows = _perp_rows(cons)
        ids = [p["id"] for p in cons["portfolios"]]
        cartes.append(_carte(
            href="conseils.html", titre="Conseils d’IA",
            quoi=f"Dix Claude Haiku donnent leur avis, un président tranche : Haiku pour l’un, Opus pour l’autre. Levier jusqu’à 10, {capital} fictifs chacun.",
            rows=rows, spark=sparkline(cons["chart"], ids), label="Classement de la ligue des conseils",
        ))  # fmt: skip
    rows = _perp_rows(perp)
    lead = [r for r in perp["portfolios"] if r["kind"] == "llm"]
    ids = [p["id"] for p in sorted(lead, key=lambda p: -(p["rendement"] or 0.0))[:2]] + [
        p["id"] for p in perp["portfolios"] if p["id"].endswith("basket-1x")
    ]
    cartes.append(_carte(
        href="derives.html", titre="IA seules",
        quoi=f"Haiku, Sonnet, Opus et Fable décident chacun seul, à la hausse ou à la baisse. Levier jusqu’à 2, {capital} fictifs chacun.",
        rows=rows, spark=sparkline(perp["chart"], ids), label="Classement de la ligue des IA seules",
    ))  # fmt: skip
    if data.get("portfolios"):
        rows = _spot_rows(data)
        ids = [p["id"] for p in data["portfolios"] if p["kind"] == "llm" or p["id"] in R.REFERENCES]
        cartes.append(_carte(
            href="comptant.html", titre="Comptant",
            quoi=f"Les mêmes IA achètent et revendent des cryptos, sans pari à la baisse ni levier, toutes les 4{NBSP}h. {eur(data['method']['capital_ueur'], decimals=0)} fictifs chacune.",
            rows=rows, spark=sparkline(data["chart"], ids) if data.get("chart") else "", label="Classement de la ligue comptant",
        ))  # fmt: skip
    body = f"""
<section class="une une-accueil" aria-labelledby="titre-page">
<h1 id="titre-page" class="titre-page">Des IA Claude tradent de l’argent fictif sur les prix réels du marché. Font-elles mieux qu’une règle simple, sans IA ?</h1>
<p class="chapo-page">Trois ligues tournent en continu sur les prix de Kraken, frais compris. Chaque décision est publiée avec sa raison, et le journal est vérifiable.</p>
</section>
<div class="ligues">{"".join(cartes)}</div>
<section class="principes" aria-labelledby="titre-principes">
<h2 id="titre-principes">Comment ça marche</h2>
<dl class="principes-liste">
<div><dt>Prix réels, argent fictif</dt><dd>Les ordres sont simulés sur les prix publics de Kraken, avec ses frais. Aucun euro réel n’est engagé.</dd></div>
<div><dt>Un témoin sans IA</dt><dd>Chaque ligue garde une règle simple : acheter et garder. Une IA utile doit faire mieux qu’elle, frais compris.</dd></div>
<div><dt>Tout est publié</dt><dd>Ce que chaque IA a décidé, pourquoi, et ce que le garde-fou a refusé. <a href="methode.html">La méthode</a> détaille les règles.</dd></div>
</dl>
</section>
"""
    return layout(
        title="Accueil", body=body, root="", active="index", data=data, chemin="",
        titre_complet="L’arène : des IA Claude tradent de l’argent fictif", desc=R.DESCRIPTION_SITE,
    )  # fmt: skip
