"""Accueil des trois ligues et tableau des scores partagé (direction « Tableau des scores », 15/11/2026).

Le premier écran de chaque ligue : une phrase qui dit l'expérience, puis le classement et la courbe côte à côte.
Pas de gros titre (décision du propriétaire du 15/11) : ce sont les rendements et la courbe qui portent l'écran.
"""

from __future__ import annotations

from typing import Any

from arene.site import render as R
from arene.site.render import NBSP, e, eur, jj_mm, layout, pct, tone


def couleurs(chart: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Style de chaque série (id → style de render._styles) : la pastille du classement a la couleur de sa courbe."""
    return {s["id"]: st for s, st in zip(chart["series"], R._styles(chart, None), strict=True)}


def pastille(st: dict[str, Any] | None) -> str:
    if not st:
        return '<span class="sw sw-ref" aria-hidden="true"></span>'
    pointille = " sw-archive" if st.get("archive") else " sw-ref" if st.get("dash") else ""
    return f'<span class="sw c{e(st["color"])}{pointille}" aria-hidden="true"></span>'


def _ex_aequo(rows: list[dict[str, Any]]) -> None:
    """Rangs ex æquo : deux rendements égaux (au centième de pour cent affiché) ont le même rang."""
    prec, rang = None, 0
    for i, r in enumerate(rows, 1):
        if r.get("archive"):  # un conseil archivé ne se classe plus : sa valeur est figée à son retrait
            r["rang"] = None
            continue
        v = None if r.get("rend") is None else round(r["rend"] * 10_000)
        if v != prec:
            rang, prec = i, v
        r["rang"] = rang


def scores(rows: list[dict[str, Any]], *, label: str, mini: bool = False) -> str:
    """Classement : rang, pastille couleur de courbe, nom (lien) et sous-titre, rendement en grand.

    Chaque ligne : {nom, href, sous, rend (fraction ou None), st (style de courbe), rang (int ou None), attrs (crochets
    du direct), valeur (texte facultatif)}. Le rang absent (référence, arrivé en cours de route) s'écrit « réf. » ou «—»."""
    items = []
    for r in rows:
        rang = str(r["rang"]) if r.get("rang") else "—"
        sous = f'<span class="sc-sous">{e(r["sous"])}</span>' if r.get("sous") else ""
        if r.get("archive"):
            sous += f'<span class="sc-sous sc-archive"><span class="tag-archive">archivé</span> retiré le {jj_mm(r["archive"]["ts"])}</span>'
        val = f'<span class="sc-eur">{r["valeur"]}</span>' if r.get("valeur") else ""
        items.append(
            f'<li class="sc{" sc-ref" if r.get("ref") else ""}{" sc-archive-ligne" if r.get("archive") else ""}"><span class="sc-rang">{rang}</span>{pastille(r.get("st"))}'
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
        pointille = " spark-archive" if st.get("archive") else " spark-ref" if st.get("dash") else " spark-halo" if st.get("halo") else ""
        lignes.append(
            f'<polyline class="spark-l s{e(st.get("color", "--muted"))}{pointille}" points="{pts}"/>'
        )
    return f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">{"".join(lignes)}</svg>'


SOUS_TEMOINS = {
    "benchmark-perp:basket-1x": "sans IA · achète et garde les 6 cryptos",
    "benchmark-perp:trend": "sans IA · suit la tendance de 20 jours",
    "benchmark-perp:random": "sans IA · décide au hasard",
    "temoin:panier": "sans IA · achète et garde les 6 cryptos",
    "temoin:6040": "sans IA · 60 % bitcoin, 40 % euros",
    "temoin:e0065": "sans IA · règle fixe sur la pression acheteuse",
    "temoin:aleatoire": "sans IA · décide au hasard",
}


def _classer(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Un seul classement, IA et témoins mêlés : si une règle sans IA mène, ça se voit (rien de caché)."""
    rows.sort(key=lambda r: (bool(r.get("archive")), -(r["rend"] if r["rend"] is not None else -9.0)))
    _ex_aequo(rows)
    return rows


def _perp_rows(ligue: dict[str, Any]) -> list[dict[str, Any]]:
    from arene.site import render_perp as RP

    st = couleurs(ligue["chart"])
    rows = []
    for p in ligue["portfolios"]:
        temoin = p["kind"] not in ("llm", "conseil")
        rows.append({
            "nom": p["name"], "href": f"{RP._dossier(p)}/{p['slug']}.html", "rend": p["rendement"], "st": st.get(p["id"]),
            "sous": SOUS_TEMOINS.get(p["id"], "sans IA") if temoin else (p.get("sous_titre") or ""),
            "ref": temoin, "attrs": RP._crochet(p, "rend"), "id": p["id"], "archive": p.get("archive"),
        })  # fmt: skip
    return _classer(rows)


def _spot_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    st = couleurs({"series": data["chart"]["series"]}) if data.get("chart") else {}
    rows = []
    for p in data["portfolios"]:
        temoin = p["kind"] != "llm"
        sous = (
            SOUS_TEMOINS.get(p["id"], "sans IA")
            if temoin
            else ("n’a encore rien acheté : tout en cash" if not p.get("n_trades") else "")
        )
        rows.append({
            "nom": p["name"], "href": f"modele/{p['slug']}.html", "rend": p["total_return"], "st": st.get(p["id"]),
            "sous": sous, "ref": temoin, "id": p["id"], "archive": p.get("archive"),
        })  # fmt: skip
    return _classer(rows)


def _carte(
    *, href: str, titre: str, quoi: str, rows: list[dict[str, Any]], chart: dict[str, Any] | None, label: str
) -> str:
    """Les trois premiers du classement (un témoin qui mène s'y voit), plus le panier s'il n'y est pas."""
    haut = rows[:3]
    haut += [r for r in rows[3:] if r.get("id") in R.REFERENCES or str(r.get("id", "")).endswith("basket-1x")]
    spark = sparkline(chart, [r["id"] for r in haut]) if chart else ""
    return (
        f'<article class="ligue-carte"><h2 class="ligue-titre"><a href="{href}">{titre}</a></h2>'
        f'<p class="ligue-quoi">{quoi}</p>{spark}{scores(haut, label=label, mini=True)}'
        f'<p class="ligue-lien"><a href="{href}">Voir la ligue, les décisions et leurs raisons<span aria-hidden="true">→</span></a></p></article>'
    )


def _liste_et(mots: list[str]) -> str:
    return mots[0] if len(mots) == 1 else ", ".join(mots[:-1]) + " et " + mots[-1]


def accueil_page(data: dict[str, Any]) -> str:
    """L'accueil : ce qu'est l'expérience en deux phrases, puis une carte par ligue avec son meneur."""
    perp = data["perp"]
    cartes = []
    capital = eur(1_000_000_000, decimals=0)
    cons = perp.get("conseils")
    if cons:
        rows = _perp_rows(cons)
        archives = [r for r in rows if r.get("archive")]
        quoi = f"Dix Claude Haiku donnent leur avis, un président tranche : Haiku pour l’un, Opus pour l’autre. Levier jusqu’à 10, {capital} fictifs chacun."
        if archives and len(archives) == sum(1 for p in cons["portfolios"] if p["kind"] == "conseil"):
            quoi = "Les deux premiers conseils, Président Haiku et Président Opus, sont archivés : leurs courbes restent en pointillés."
        cartes.append(_carte(
            href="conseils.html", titre="Conseils d’IA",
            quoi=quoi,
            rows=rows, chart=cons["chart"], label="Classement de la ligue des conseils",
        ))  # fmt: skip
    rows = _perp_rows(perp)
    solos = [p for p in perp["portfolios"] if p["kind"] == "llm"]
    actifs = [p["name"].replace("Claude ", "") for p in solos if not p.get("archive")]
    quoi_solo = f"Haiku, Sonnet, Opus et Fable décident chacun seul, à la hausse ou à la baisse. Levier jusqu’à 2, {capital} fictifs chacun."
    if solos and actifs and len(actifs) < len(solos):
        arch = [p["name"].replace("Claude ", "") for p in solos if p.get("archive")]
        quoi_solo = (
            f"{_liste_et(actifs)} décident chacun seul, à la hausse ou à la baisse. Levier jusqu’à 2, {capital} fictifs chacun. "
            f"{_liste_et(arch)} : archivé, en pointillés."
        )
    cartes.append(_carte(
        href="derives.html", titre="IA seules",
        quoi=quoi_solo,
        rows=rows, chart=perp["chart"], label="Classement de la ligue des IA seules",
    ))  # fmt: skip
    if data.get("portfolios"):
        rows = _spot_rows(data)
        cartes.append(_carte(
            href="comptant.html", titre="Comptant",
            quoi=f"Les mêmes IA achètent et revendent des cryptos, sans pari à la baisse ni levier, toutes les 4{NBSP}h. {eur(data['method']['capital_ueur'], decimals=0)} fictifs chacune.",
            rows=rows, chart=data.get("chart"), label="Classement de la ligue comptant",
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
