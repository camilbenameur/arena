"""Pages de la ligue dérivés : accueil (premier plan du site), une page par portefeuille, section de méthode.

Même direction « Carnet » que le spot : filets, peu de mots, chiffres tabulaires. Tout texte venu du journal est
échappé ; les textes libres des modèles (justification, invalidation) sont publiés tels quels, échappés, bornés.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from arene.site import perp as P
from arene.site.render import (
    FLUX_DIRECT,
    MINUS,
    NBSP,
    NNBSP,
    _chart_scripts,
    _group,
    _legende,
    _stat,
    e,
    empiler,
    eur,
    heure,
    iso,
    json_inline,
    layout,
    pct,
    pluriel,
    quand,
    tone,
    usd,
    when,
)

OUTILS_COURTS = {
    "bougies": "bougies", "carnet": "carnet d’ordres", "derives": "funding", "indicateurs": "indicateurs",
    "simuler_ordre": "simulation d’ordre", "historique": "son historique",
}  # fmt: skip
MIN_POINTS = 3  # sous 3 relevés (1 h 30), la courbe n'est qu'une droite


def usd_prix(uusd: int | None) -> str:
    """Prix d'un contrat en dollars : 2 décimales au-delà de 100 $, 4 en dessous (XRP)."""
    if uusd is None:
        return "—"
    digits = 2 if abs(uusd) >= 100_000_000 else 4
    v = (Decimal(abs(uusd)) / Decimal(1_000_000)).quantize(Decimal(1).scaleb(-digits))
    whole, _, frac = f"{v:f}".partition(".")
    return f"{MINUS if uusd < 0 else ''}{_group(int(whole))},{frac}{NBSP}$"


def quantite(q: int) -> str:
    """Quantité en unités du sous-jacent, 6 chiffres significatifs au plus : « 0,783846 », « 323,987 »."""
    d = Decimal(abs(q)) / Decimal(100_000_000)
    if d == 0:
        return "0"
    d = round(d, max(0, 5 - d.adjusted())).normalize()
    return format(d, "f").replace(".", ",")


def pc(v: float | None, *, signe: bool = False) -> str:
    """« 25 % » à partir d'un pourcentage déjà en % (champs `*_pct` des décisions)."""
    if v is None:
        return "—"
    s = f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{'+' if signe and v > 0 else ''}{s}{NBSP}%"


def levier(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x:.2f}".replace(".", ",") + f"{NBSP}×"


def niveau(cond: str | None, prix: int | None) -> str:
    """« au-dessus de 98 000,00 $ », « sous 3 200,00 $ »."""
    mot = {"above": "au-dessus de", "below": "sous"}.get(cond or "", "à")
    return f"{mot} {usd_prix(prix)}"


def declencheur(d: dict[str, Any] | None) -> str:
    if not d:
        return "réveil"
    if d.get("type") == "alerte":
        return f"son alerte · {d.get('instrument') or '?'} {niveau(d.get('condition'), d.get('prix_uusd'))}"
    if d.get("type") == "ordre":
        return f"ordre d’entrée · {d.get('instrument') or '?'} {niveau(d.get('condition'), d.get('prix_uusd'))}"
    mv = d.get("move_bp")
    if mv is None:
        return f"réveil · {d.get('instrument') or '?'}"
    return f"réveil · {d['instrument']} {pct(mv / 10_000, digits=1)} en 1{NBSP}h"


def _pastille_ronde(d: dict[str, Any]) -> str:
    """Pourquoi l'IA a été appelée hors rendez-vous. L'appel régulier, de loin le plus fréquent, reste discret."""
    k = d.get("kind")
    if k == "cadence":
        return '<span class="pastille discret">appel régulier</span> '
    if k == "scheduled":
        return '<span class="pastille neutre">à sa demande</span> '
    if k not in ("wakeup", "alert", "ordre"):
        return ""
    return f'<span class="pastille reveil">{e(declencheur(d.get("declencheur")))}</span> '


def _resume(actions: list[dict[str, Any]]) -> str:
    """« Short ETH, ferme BTC » ; « Aucun ordre » sans action."""
    mots = []
    for a in actions:
        if a.get("ecartee") and not a.get("action"):
            mots.append("action écartée")
            continue
        verbe = {"open_long": "long", "open_short": "short", "reduce": "réduit", "close": "ferme"}.get(a.get("action") or "", "?")
        mots.append(f"{verbe} {a['instrument']}")
    if not mots:
        return "Aucun ordre"
    txt = ", ".join(mots)
    return txt[:1].upper() + txt[1:]


def element(x: dict[str, Any]) -> str:
    """Une alerte ou un ordre d'entrée en une ligne HTML (textes du modèle échappés)."""
    lieu = f"{e(x['instrument'])} {niveau(x.get('condition'), x.get('prix_uusd'))}"
    if x["type"] == "alerte":
        txt = f"<strong>Alerte</strong> {lieu}"
        if x.get("note"):
            txt += f' <span class="muted">« {e(x["note"])} »</span>'
        return txt
    parts = [f"<strong>Ordre {e(x.get('sens') or '?')}</strong> {lieu}"]
    if x.get("taille_pct") is not None:
        parts.append(f"{pc(x['taille_pct'])} du portefeuille")
    if x.get("stop_pct") is not None:
        parts.append(f"stop {pc(x['stop_pct'])}")
    if x.get("objectif_pct") is not None:
        parts.append(f"objectif {pc(x['objectif_pct'])}")
    txt = " · ".join(parts)
    if x.get("invalidation"):
        txt += f'<span class="invalidation">Invalide si{NNBSP}: {e(x["invalidation"])}</span>'
    return txt


def _pose_resume(d: dict[str, Any]) -> str:
    """« 1 alerte et 1 ordre posés » ; vide si rien."""
    els = (d.get("pose") or {}).get("elements") or []
    na = sum(1 for x in els if x["type"] == "alerte")
    no = len(els) - na
    mots = [m for m in (pluriel(na, "alerte posée", "alertes posées") if na else "", pluriel(no, "ordre d’entrée posé", "ordres d’entrée posés") if no else "") if m]
    if d.get("rappel_ts"):
        mots.append(f"rappel à {heure(d['rappel_ts'])}")
    return " et ".join(mots)


def _pose(d: dict[str, Any]) -> str:
    pose = d.get("pose") or {}
    els, refus = pose.get("elements") or [], pose.get("refus") or []
    if not els and not refus and not d.get("rappel_ts"):
        return ""
    items = "".join(f"<li>{element(x)}</li>" for x in els)
    if d.get("rappel_ts"):
        items += f"<li><strong>Rappel</strong> demandé pour {heure(d['rappel_ts'])}</li>"
    if refus:
        motifs = sorted({r["motif"] for r in refus})
        items += f'<li class="muted">{pluriel(len(refus), "refusé", "refusés")} à la création : {e(", ".join(motifs))}</li>'
    return f'<div class="pose"><span class="etiquette">A laissé pour la suite</span><ul class="liste-simple">{items}</ul></div>'


def _positions_cell(p: dict[str, Any]) -> str:
    if not p["positions"]:
        return '<span class="muted">aucune</span>'
    return " ".join(
        f'<span class="sens sens-{x["sens"]}">{e(x["instrument"])} {x["sens"]}</span>' for x in p["positions"]
    )


def _statut(p: dict[str, Any]) -> str:
    st = p.get("statut")
    if not st:
        return ""
    if st["etat"] == "arrete":
        return f' <span class="pastille perte-bg">{"arrêté, ruine" if p["kind"] == "conseil" else "arrêté"}</span>'
    return ' <span class="pastille warn">gelé</span>'


def _depuis(perp: dict[str, Any], p: dict[str, Any]) -> str:
    """« depuis le 13 nov., 02:00 UTC » pour un portefeuille entré après l'ouverture de la ligue (rendement mesuré depuis)."""
    if perp.get("ouverte_ts") and p["ouvert_ts"] - perp["ouverte_ts"] > 900:
        return f'<small class="desc">depuis le {quand(p["ouvert_ts"], annee=False)}</small>'
    return ""


def _hors_regle_court(p: dict[str, Any]) -> str:
    return '<small class="desc">démonstration paper, hors règle 2x</small>' if p["kind"] == "conseil" else ""


def _codes(d: dict[str, Any]) -> dict[str, str]:
    return P.CODES_CONSEIL if d.get("regles") == "conseil" else P.CODES


def _funding_cell(p: dict[str, Any]) -> str:
    n = p["funding_net_ueur"]
    if not p["funding_paye_ueur"] and not p["funding_recu_ueur"]:
        return '<span class="muted">—</span>'
    # Payé = coût : affiché en négatif pour le portefeuille.
    return f'<span class="{tone(-n)}">{eur(-n, signed=True)}</span>'


# ---------------------------------------------------------------------------
# Prix en direct (assets/direct.js)
# ---------------------------------------------------------------------------


def _pos_direct(x: dict[str, Any]) -> bool:
    return bool(x.get("produit")) and isinstance(x.get("mark_uusd"), int) and isinstance(x.get("latent_ueur"), int)


def _direct_pf(p: dict[str, Any]) -> bool:
    """Un portefeuille se revalorise en direct s'il a une position chiffrée et un cours euro-dollar publié."""
    return bool(p.get("fx")) and any(_pos_direct(x) for x in p["positions"])


def _crochet(p: dict[str, Any], quoi: str, x: dict[str, Any] | None = None) -> str:
    """Attributs qui désignent un chiffre à revaloriser en direct ; rien si le portefeuille ne s'y prête pas."""
    if not _direct_pf(p) or (x is not None and not _pos_direct(x)):
        return ""
    out = f' data-direct="{quoi}" data-pf="{e(p["slug"])}"'
    return out + (f' data-p="{e(x["produit"])}"' if x is not None else "")


def _direct_scripts(root: str, perp: dict[str, Any], pfs: list[dict[str, Any]]) -> str:
    """Les positions publiées (quantité, prix d'entrée, latent officiel) que direct.js revalorise au mark du moment."""
    if not pfs:
        return ""
    ref: dict[str, int] = {}
    out: dict[str, Any] = {}
    for p in pfs:
        pos = [x for x in p["positions"] if _pos_direct(x)]
        for x in pos:
            ref[x["produit"]] = x["mark_uusd"]
        out[p["slug"]] = {
            "c": p["capital_ueur"], "eq": p["equity_ueur"], "fx": p["fx"],
            "pos": [{"p": x["produit"], "q": x["qty_signee"], "e": x["entree_uusd"], "l": x["latent_ueur"]} for x in pos],
        }  # fmt: skip
    payload = {
        "flux": FLUX_DIRECT, "produits": sorted(ref), "ref": ref, "pf": out,
        "releve": heure(perp["live_ts"]) if perp.get("live_ts") else "",
    }  # fmt: skip
    return f'\n<script id="direct-data" type="application/json">{json_inline(payload)}</script>\n<script src="{root}assets/direct.js"></script>'


# ---------------------------------------------------------------------------
# Courbe
# ---------------------------------------------------------------------------


def _ref_chart(perp: dict[str, Any], focus: str | None) -> dict[str, Any]:
    ch = perp["chart"]
    if focus is None:
        return ch
    keep = {focus, P.PANIER}
    return {**ch, "series": [s for s in ch["series"] if s["id"] in keep]}


def courbe_visible(chart: dict[str, Any]) -> bool:
    return len(chart["x"]) >= MIN_POINTS and bool(chart["series"])


def _chart_block(chart: dict[str, Any], *, focus: str | None = None, focus_name: str | None = None) -> str:
    if not courbe_visible(chart):
        return '<p class="vide vide-court">La courbe apparaît après 1{NBSP}h{NBSP}30 de relevés. Les valeurs sont dans le tableau.</p>'.replace("{NBSP}", NBSP)
    derniers = "; ".join(
        f"{s['name']} {pct((s['values'][-1] - 100) / 100) if s['values'][-1] is not None else '—'}" for s in chart["series"]
    )
    periode = f"du {when(chart['x'][0])} au {when(chart['x'][-1])}"
    if focus_name:
        label = f"Rendement net cumulé de {focus_name}, comparé au témoin panier 1x, {periode}. Valeurs en direct : {derniers}."
    else:
        label = f"Rendement net cumulé des {len(chart['series'])} portefeuilles dérivés, {periode}. Valeurs en direct : {derniers}."
    return (
        '<figure class="graphique">'
        f'<div id="chart" class="graphique-zone" role="img" aria-label="{e(label)}">'
        '<noscript><p class="vide">Graphique : JavaScript requis. Valeurs dans le tableau.</p></noscript></div>'
        # La courbe est celle du journal : sa légende date le relevé, l'estimation en direct est ailleurs.
        f'{_legende(chart, focus).replace(">En direct : ", ">Dernier relevé : ", 1)}</figure>'
    )


# ---------------------------------------------------------------------------
# Accueil de la ligue
# ---------------------------------------------------------------------------


def _tableau(perp: dict[str, Any]) -> str:
    pfs = perp["portfolios"]
    vmax = max((abs(p["rendement"] or 0.0) for p in pfs), default=0.0)
    from arene.site.render import _svg_barre

    def ligne(p: dict[str, Any]) -> str:
        return (
            f'<tr class="{e(p["kind"])}"><th scope="row"><a href="derives/{e(p["slug"])}.html">{e(p["name"])}</a>{_statut(p)}{_depuis(perp, p)}{_hors_regle_court(p)}</th>'
            f'<td class="n cle"><span class="{tone(p["rendement"])}"{_crochet(p, "rend")}>{pct(p["rendement"])}</span>{_svg_barre(p["rendement"], vmax)}</td>'
            f'<td class="n"><span{_crochet(p, "val")}>{eur(p["equity_ueur"])}</span></td>'
            f'<td class="n">{levier(p["levier"])}</td>'
            f'<td class="n">{pct(-p["drawdown_max"]) if p["drawdown_max"] else "0,00" + NBSP + "%"}</td>'
            f'<td class="positions-cell">{_positions_cell(p)}</td></tr>'
        )

    def groupe(kind: str, titre: str, n_col: int, note: str = "") -> str:
        lignes = [ligne(p) for p in pfs if p["kind"] == kind]
        if not lignes:
            return ""
        note = f' <span class="h-note">{e(note)}</span>' if note else ""
        return f'<tbody class="groupe-{kind}"><tr class="groupe"><th scope="rowgroup" colspan="{n_col}">{titre}{note}</th></tr>{"".join(lignes)}</tbody>'

    n_col = 6
    head = (
        '<tr><th scope="col">Portefeuille</th><th scope="col" class="n">Rendement net</th><th scope="col" class="n">Valeur</th>'
        '<th scope="col" class="n">Levier</th><th scope="col" class="n">Pire baisse</th><th scope="col">Positions</th></tr>'
    )
    libelles = ["Rendement net", "Valeur", "Levier", "Pire baisse", "Positions"]
    return empiler(
        '<div class="table-scroll" tabindex="0" role="region" aria-label="Tableau de la ligue dérivés, défilable">'
        '<table class="tableau comparatif empile"><caption class="visuellement-cache">Ligue dérivés : modèles d’IA, hors catégorie, puis témoins</caption>'
        f'<thead>{head}</thead>{groupe("llm", "Modèles d’IA", n_col)}{groupe("conseil", "Hors catégorie", n_col, P.MARQUE_CONSEIL)}'
        f'{groupe("temoin", "Témoins", n_col)}</table></div>',
        libelles,
    )


def _dernieres(perp: dict[str, Any]) -> str:
    """La dernière décision de chaque IA : ce qu'elle a fait, et pourquoi, en une ligne dépliable."""
    items = []
    for p in perp["portfolios"]:
        if p["kind"] not in ("llm", "conseil"):
            continue
        d = next((x for x in p["decisions"] if x["statut"] in ("decidee", "echec", "sautee")), None)
        lien = f'<a class="dernier-nom" href="derives/{e(p["slug"])}.html">{e(p["name"])}</a>'
        if d is None:
            items.append(f'<li class="ligne sans-detail">{lien}<span class="muted">pas encore de décision</span></li>')
            continue
        resume = (
            f'{lien}<span class="quand">{quand(d["ts"], annee=False)}</span>{_pastille_ronde(d)}'
            f'<span class="resume-ordres">{e(_resume_ligne(d))}</span>'
        )
        corps = _justif(d) + _pose(d)
        items.append(
            f'<li class="ligne"><details><summary>{resume}</summary>{corps}</details></li>' if corps else f'<li class="ligne sans-detail">{resume}</li>'
        )
    if not items:
        return ""
    return (
        '<section aria-labelledby="titre-dernieres"><h2 id="titre-dernieres">Dernières décisions des IA</h2>'
        f'<ul class="decisions dernieres">{"".join(items)}</ul></section>'
    )


def _resume_ligne(d: dict[str, Any]) -> str:
    if d["statut"] == "sautee":
        return f"Ronde sautée : {d['saut']}"
    if d["statut"] == "echec":
        return f"Pas de décision ({d['erreur']})"
    pose = _pose_resume(d)
    if not d["actions"] and pose:
        return f"Aucun ordre, {pose}"
    return _resume(d["actions"]) + (f", {pose}" if pose else "")


def index_page(data: dict[str, Any]) -> str:
    perp = data["perp"]
    pfs = perp["portfolios"]
    llms = [p for p in pfs if p["kind"] == "llm"]
    conseils = [p for p in pfs if p["kind"] == "conseil"]
    n_tem = len(pfs) - len(llms) - len(conseils)
    capital = pfs[0]["capital_ueur"] if pfs else 1_000_000_000
    panier = next((p for p in pfs if p["id"] == P.PANIER), None)
    if llms and any(d["statut"] == "decidee" for p in llms for d in p["decisions"]):
        best = max(llms, key=lambda p: p["rendement"] or 0.0)
        verdict = f'En tête des IA : {e(best["name"])} <span{_crochet(best, "rend")}>{pct(best["rendement"])}</span>'
        if panier:
            verdict += f' · référence sans IA (panier) <span{_crochet(panier, "rend")}>{pct(panier["rendement"])}</span>'
        for c in conseils:  # hors catégorie : à côté du classement, jamais dedans
            verdict += f' · hors catégorie, {e(c["name"])} <span{_crochet(c, "rend")}>{pct(c["rendement"])}</span>'
    elif llms:
        verdict = e(f"Les {len(llms)}{NBSP}IA décident à partir du rendez-vous de {heure(perp['prochain_rdv_ts'])}")
    else:
        verdict = e(f"Témoins seuls pour l’instant · les 4{NBSP}IA entrent au rendez-vous de {heure(perp['prochain_rdv_ts'])}")
    qui = f"{len(llms)}{NBSP}IA et {n_tem}{NBSP}témoins sans IA" if llms else f"{n_tem}{NBSP}témoins sans IA"
    if conseils:
        qui = f"{len(llms)}{NBSP}IA, un conseil agressif et {n_tem}{NBSP}témoins sans IA"
    direct_pfs = [p for p in pfs if _direct_pf(p)]
    items = [f'<li>Prochain rendez-vous <time datetime="{iso(perp["prochain_rdv_ts"])}">{heure(perp["prochain_rdv_ts"])}</time></li>']
    if perp["live_ts"]:
        frais = data["generated_ts"] - perp["live_ts"] <= 1_800
        mot = "Valeurs en direct" if frais else "Dernières valeurs du"
        quand_txt = heure(perp["live_ts"]) if frais else when(perp["live_ts"], annee=False)
        items.append(f'<li><span data-direct-mot>{mot}</span> <time datetime="{iso(perp["live_ts"])}">{e(quand_txt)}</time></li>')
        if direct_pfs:
            items.append('<li class="direct-etat" data-direct-etat data-court hidden></li>')
    if perp["journal"]["verify_ok"]:
        items.append('<li><a href="methode.html#m-derives">Journal vérifié</a></li>')
    else:
        items.append('<li class="perte-txt">Journal : vérification en échec</li>')

    lecture_levier = f" (10 pour le {e(conseils[0]['name'])})" if conseils else ""
    lecture_conseil = (
        f"  <li><strong>Hors catégorie</strong> : {e(conseils[0]['name'])}, dix Haiku qui délibèrent avec un mandat agressif. {e(P.HORS_REGLE_CONSEIL)} Il n’est pas classé avec les IA.</li>\n"
        if conseils else ""
    )
    body = f"""
<h1 class="visuellement-cache">Ligue dérivés : des IA gèrent chacune {eur(capital, decimals=0)} fictifs en contrats perpétuels, face à des témoins sans IA</h1>
<section class="etat" aria-label="État de la ligue dérivés">
  <p class="saison"><strong>Ligue dérivés</strong> · {qui} · {eur(capital, decimals=0)} fictifs chacun, à la hausse ou à la baisse</p>
  <p class="avancee"><strong>{verdict}</strong></p>
  <ul class="releve">{"".join(items)}</ul>
</section>
<section class="courbes" aria-labelledby="titre-courbes">
  <h2 id="titre-courbes">Rendement net <span class="h-note">frais et funding compris</span></h2>
  {_chart_block(perp["chart"])}
</section>
<section aria-labelledby="titre-comparatif">
  <h2 id="titre-comparatif">Portefeuilles</h2>
  {_tableau(perp)}
  <details class="lecture"><summary>Comment lire ce tableau</summary><ul class="liste-simple">
  <li><strong>Témoin</strong> : une règle fixe, sans IA. Le panier 1x (acheter et garder) est la référence : une IA utile doit faire mieux, frais compris.</li>
  <li><strong>Long, short</strong> : parier sur la hausse, sur la baisse.</li>
  <li><strong>Levier</strong> : montant engagé divisé par la valeur du portefeuille. 2 au plus{lecture_levier}.</li>
{lecture_conseil}  <li><strong>Gelé</strong> : plus d’ouverture pendant 24{NBSP}h après une perte de 5{NBSP}% en un jour.</li>
  </ul></details>
</section>
{_dernieres(perp)}
"""
    ch = perp["chart"]
    return layout(
        title="Ligue dérivés", body=body, root="", active="index", data=data, ligue="perp",
        scripts=(_chart_scripts("", ch, None, dernier="Dernier relevé") if courbe_visible(ch) else "") + _direct_scripts("", perp, direct_pfs),
        direct=bool(direct_pfs),
    )  # fmt: skip


# ---------------------------------------------------------------------------
# Page d'un portefeuille
# ---------------------------------------------------------------------------


def _positions(p: dict[str, Any]) -> str:
    if not p["positions"]:
        return f'<p class="vide">Aucune position ouverte. Valeur en marge{NNBSP}: {eur(p["equity_ueur"])}.</p>'
    stop = any(x["stop_uusd"] for x in p["positions"])
    obj = any(x["objectif_uusd"] for x in p["positions"])
    rows = "".join(
        f'<tr><th scope="row">{e(x["instrument"])}</th><td><span class="sens sens-{x["sens"]}">{x["sens"]}</span></td>'
        f'<td class="n">{eur(x["notionnel_ueur"])}<small class="sous">{e(quantite(x["qty"]))} {e(x["instrument"])}</small></td>'
        f'<td class="n">{usd_prix(x["entree_uusd"])}</td><td class="n"><span{_crochet(p, "mark", x)}>{usd_prix(x["mark_uusd"])}</span></td>'
        + (f'<td class="n">{usd_prix(x["stop_uusd"])}</td>' if stop else "")
        + (f'<td class="n">{usd_prix(x["objectif_uusd"])}</td>' if obj else "")
        + f'<td class="n"><span class="{tone(x["latent_ueur"])}"{_crochet(p, "lat", x)}>{eur(x["latent_ueur"], signed=True)}</span></td></tr>'
        for x in p["positions"]
    )
    return empiler(
        '<div class="table-scroll" tabindex="0" role="region" aria-label="Tableau des positions, défilable"><table class="tableau empile">'
        '<caption class="visuellement-cache">Positions ouvertes, prix en dollars, valeurs en euros</caption>'
        '<thead><tr><th scope="col">Contrat</th><th scope="col">Sens</th><th scope="col" class="n">Exposition</th>'
        '<th scope="col" class="n">Entrée</th><th scope="col" class="n">Prix actuel</th>'
        + ('<th scope="col" class="n">Stop</th>' if stop else "")
        + ('<th scope="col" class="n">Objectif</th>' if obj else "")
        + '<th scope="col" class="n">Latent</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>",
        ["Sens", "Exposition", "Entrée", "Prix actuel"] + (["Stop"] if stop else []) + (["Objectif"] if obj else []) + ["Latent"],
    )


def _intention(a: dict[str, Any]) -> str:
    if not a.get("action"):
        return '<span class="muted">action invalide, écartée</span>'
    parts = [f"<strong>{e(P.ACTIONS.get(a['action'], a['action']))}</strong>"]
    if a.get("taille_pct") is not None:
        parts.append(f"{pc(a['taille_pct'])} {'du portefeuille' if a['action'].startswith('open') else 'de la position'}")
    if a.get("stop_pct") is not None:
        parts.append(f"stop {pc(a['stop_pct'])}")
    if a.get("objectif_pct") is not None:
        parts.append(f"objectif {pc(a['objectif_pct'])}")
    if a.get("horizon_h"):
        parts.append(f"{a['horizon_h']}{NBSP}h")
    if a.get("confiance_pct") is not None:
        parts.append(f"confiance {pc(a['confiance_pct'])}")
    txt = " · ".join(parts)
    if a.get("invalidation"):
        txt += f'<span class="invalidation">Invalide si{NNBSP}: {e(a["invalidation"])}</span>'
    if a.get("ecartee"):
        txt += '<span class="muted"> · écartée (invalide)</span>'
    return txt


def _garde_fou(a: dict[str, Any], codes: dict[str, str] = P.CODES) -> str:
    v = a.get("verdict")
    if v is None:
        return '<span class="pastille neutre">sans verdict</span>'
    if v["approuve"]:
        return '<span class="pastille ok">accepté</span>'
    motifs = "".join(f'<span class="code">{e(codes.get(c, "règle inconnue"))}</span>' for c in v["motifs"])
    return f'<span class="pastille perte-bg">refusé</span><span class="codes">{motifs}</span>'


def _execution(a: dict[str, Any]) -> str:
    st = a.get("execution")
    if a["fills"]:
        out = "".join(
            f'<span class="exec">{"achat" if f["qty"] > 0 else "vente"} {e(quantite(f["qty"]))} {e(a["instrument"])} à {usd_prix(f["prix_uusd"])}'
            f'<small class="sous">frais {eur(f["frais_ueur"], decimals=4)}</small></span>'
            for f in a["fills"]
        )
        if st and st != "filled":
            out += f'<span class="muted exec-note">{e(P.EXECUTIONS.get(st, st))}</span>'
        return out
    if st:
        return f'<span class="muted">{e(P.EXECUTIONS.get(st, st))}</span>'
    return '<span class="muted">non exécuté</span>'


def _actions(d: dict[str, Any]) -> str:
    rows = "".join(
        f'<tr><th scope="row">{e(a["instrument"])}</th><td>{_intention(a)}</td><td>{_garde_fou(a, _codes(d))}</td><td class="n">{_execution(a)}</td></tr>'
        for a in d["actions"]
    )
    return empiler(
        f'<div class="table-scroll actions-scroll" tabindex="0" role="region" aria-label="Actions du {e(when(d["ts"]))}, défilable">'
        '<table class="tableau actions empile"><thead><tr><th scope="col">Contrat</th><th scope="col">Intention</th>'
        '<th scope="col">Garde-fou</th><th scope="col" class="n">Exécution</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>",
        ["Intention", "Garde-fou", "Exécution"],
    )


def _justif(d: dict[str, Any]) -> str:
    out = ""
    if d.get("justification"):
        qui = "Étape C · le Président tranche" if d.get("conseil") else "Raisonnement du modèle"
        out += f'<blockquote class="justif"><span class="etiquette">{qui}</span>{e(d["justification"])}</blockquote>'
    if d.get("outils"):
        outils = ", ".join(
            f'{e(OUTILS_COURTS.get(o["outil"], o["outil"]))}{(" " + e(o["args"])) if o["args"] else ""}{" (erreur)" if o["erreur"] else ""}'
            for o in d["outils"]
        )
        out += f'<p class="outils"><span class="etiquette">A consulté</span>{outils}</p>'
    return out


# ---------------------------------------------------------------------------
# Délibération du Conseil Haiku : étape A (8 avis), B (l'Avocat du diable), C (le Président : la décision)
# ---------------------------------------------------------------------------

def _outils_txt(outils: list[dict[str, Any]]) -> str:
    return ", ".join(
        f'{e(OUTILS_COURTS.get(o["outil"], o["outil"]))}{(" " + e(o["args"])) if o["args"] else ""}{" (erreur)" if o["erreur"] else ""}'
        for o in outils
    )


def _avis_ligne(x: dict[str, Any]) -> str:
    """« short ETH · conviction 60 · 250 % · stop 2,5 % · niveau 1 894,00 $ »."""
    parts = [f'<span class="sens sens-{x["position"]}">{x["position"]}</span> <strong>{e(x["instrument"])}</strong>']
    if x.get("conviction") is not None:
        parts.append(f'conviction {x["conviction"]}')
    if x["position"] != "plat":
        if x.get("taille_pct") is not None:
            parts.append(pc(x["taille_pct"]))
        if x.get("stop_pct") is not None:
            parts.append(f"stop {pc(x['stop_pct'])}")
    if x.get("niveau_uusd") is not None:
        parts.append(f"niveau clé {usd_prix(x['niveau_uusd'])}")
    return " · ".join(parts)


def _membre(a: dict[str, Any]) -> str:
    role = f'<span class="role">{e(a["role"])}</span>' if a.get("role") else ""
    tete = f'<p class="membre-tete"><strong>{e(a["nom"])}</strong>{role}</p>'
    if a["absent"]:
        return f'<li class="membre absent">{tete}<p class="muted"><span class="pastille neutre">absent</span> {e(a["erreur"] or "échec de l’appel")}</p></li>'
    cible = ""
    if a.get("cible"):
        cible = f'<p class="cible"><span class="etiquette">Attaque</span>le {e(a["cible"]["sens"])} {e(a["cible"]["instrument"])}</p>'
    avis = "".join(f"<li>{_avis_ligne(x)}</li>" for x in a["avis"]) or '<li class="muted">aucune position conseillée</li>'
    arg = f'<p class="argument">{e(a["argument"])}</p>' if a.get("argument") else ""
    outils = f'<p class="outils"><span class="etiquette">A consulté</span>{_outils_txt(a["outils"])}</p>' if a.get("outils") else ""
    return f'<li class="membre">{tete}{cible}<ul class="avis-positions">{avis}</ul>{arg}{outils}</li>'


def _tendance(avis: list[dict[str, Any]]) -> str:
    """Ce que penchent les avis de l'étape A : « short ETH ×5, short SOL ×2, plat ×1 » (un membre compte une fois par idée)."""
    from collections import Counter

    c: Counter[str] = Counter()
    for a in avis:
        if a["absent"] or a["etape"] != "A":
            continue
        idees = {f'{x["position"]} {x["instrument"]}' for x in a["avis"] if x["position"] != "plat"}
        c.update(idees or {"plat"})
    return ", ".join(f"{k}{NBSP}×{n}" for k, n in c.most_common(3))


def _deliberation(d: dict[str, Any]) -> str:
    c = d.get("conseil")
    if not c:
        return ""
    if c.get("avis_hors_page"):
        return f'<p class="outils muted"><span class="etiquette">Délibération</span>{pluriel(c["avis_hors_page"], "avis", "avis")}, gardés dans le journal (la page montre ceux des {P.DELIBERATIONS_MAX} dernières rondes).</p>'
    if not c.get("avis"):
        return ""
    a_avis = [a for a in c["avis"] if a["etape"] == "A"]
    b_avis = [a for a in c["avis"] if a["etape"] != "A"]
    n_ok = sum(1 for a in c["avis"] if not a["absent"])
    n_abs = len(c["avis"]) - n_ok
    mots = [pluriel(n_ok, "avis", "avis")]
    if n_abs:
        mots.append(pluriel(n_abs, "absent", "absents"))
    t = _tendance(c["avis"])
    if t:
        mots.append(t)
    avocat = next((a for a in b_avis if a.get("cible")), None)
    if avocat:
        mots.append(f"l’Avocat attaque le {avocat['cible']['sens']} {avocat['cible']['instrument']}")
    resume = f'<span class="etiquette">Délibération</span><span class="muted">{e(" · ".join(mots))}</span>'
    corps = ""
    if a_avis:
        corps += f'<h4 class="etape">Étape A · {pluriel(len(a_avis), "avis indépendant", "avis indépendants")}<span class="h-note">sans se voir</span></h4><ol class="avis">{"".join(_membre(a) for a in a_avis)}</ol>'
    if b_avis:
        corps += f'<h4 class="etape">Étape B · l’Avocat du diable<span class="h-note">a lu l’étape A</span></h4><ol class="avis">{"".join(_membre(a) for a in b_avis)}</ol>'
    corps += '<p class="etape etape-c">Étape C · le Président a lu les avis et tranche ci-dessous.</p>'
    return f'<details class="deliberation"><summary>{resume}</summary>{corps}</details>'


def _meta(d: dict[str, Any]) -> str:
    meta = []
    if d.get("cout_uusd"):
        meta.append(usd(d["cout_uusd"]))
    return f'<span class="decision-meta">{" · ".join(meta)}</span>' if meta else ""


def _decision(d: dict[str, Any]) -> str:
    ronde = _pastille_ronde(d)
    if d["statut"] in ("sautee", "echec", "en_cours") or not d["actions"]:
        if d["statut"] == "sautee":
            txt = f'<span class="pastille warn">sautée</span> <span class="muted">{e(d["saut"])}</span>'
        elif d["statut"] == "echec":
            txt = f'<span class="pastille warn">sans décision</span> <span class="muted">{e(d["erreur"])}</span>'
        elif d["statut"] == "en_cours":
            txt = '<span class="muted">en cours</span>'
        else:
            txt = f'<span class="muted">{e(_resume_ligne(d))}</span>'
        resume = f'<span class="quand">{quand(d["ts"])}</span>{ronde}{txt}{_meta(d)}'
        corps = _deliberation(d) + _justif(d) + _pose(d)
        return f'<li class="ligne"><details><summary>{resume}</summary>{corps}</details></li>' if corps else f'<li class="ligne">{resume}</li>'
    tete = f'{ronde}<span class="resume-ordres">{e(_resume_ligne(d))}</span>'
    corps = f'<div class="decision-pile">{_deliberation(d)}{_justif(d)}{_actions(d)}{_pose(d)}</div>'
    return f'<li class="decision"><article><header><h3>{quand(d["ts"])}</h3>{tete}{_meta(d)}</header>{corps}</article></li>'


GROUPE_MIN = 3  # à partir de 3 décisions calmes d'affilée, une seule ligne repliée


def _calme(d: dict[str, Any]) -> bool:
    """Une décision sans ordre (ni échec, ni saut) : le cas courant des appels réguliers."""
    return d["statut"] == "decidee" and not d["actions"] and d["kind"] != "ordre"


def _decisions_groupees(ds: list[dict[str, Any]]) -> str:
    """La chronologie, où chaque suite d'au moins GROUPE_MIN décisions sans ordre tient sur une ligne dépliable."""
    out, i = [], 0
    while i < len(ds):
        j = i
        while j < len(ds) and _calme(ds[j]):
            j += 1
        if j - i >= GROUPE_MIN:
            run = ds[i:j]
            n_pose = sum(1 for d in run if (d.get("pose") or {}).get("elements"))
            note = f" · {pluriel(n_pose, 'pose des alertes ou ordres', 'posent des alertes ou ordres')}" if n_pose else ""
            resume = (
                f'<span class="quand">{quand(run[-1]["ts"], annee=False)} → {heure(run[0]["ts"])}</span>'
                f'<span class="muted">{pluriel(len(run), "décision sans ordre", "décisions sans ordre")}{e(note)}</span>'
            )
            out.append(f'<li class="ligne groupe-calme"><details><summary>{resume}</summary><ol class="decisions">{"".join(_decision(d) for d in run)}</ol></details></li>')
            i = j
        elif j > i:
            out.extend(_decision(d) for d in ds[i:j])
            i = j
        else:
            out.append(_decision(ds[i]))
            i += 1
    return "".join(out)


def _attente(p: dict[str, Any]) -> str:
    """Alertes et ordres d'entrée en attente, puis ce qu'il est advenu des précédents (replié)."""
    at = p.get("attente")
    if not at:
        return ""
    en_cours = at["alertes"] + at["ordres"]
    ry = p.get("rythme") or {}
    lignes = []
    if ry.get("reveil_ts"):
        lignes.append(f'<li class="ligne"><span class="el"><strong>Rappel</strong> qu’elle a demandé</span><span class="muted">à {heure(ry["reveil_ts"])}</span></li>')
    if ry.get("prochain_ts"):
        lignes.append(
            f'<li class="ligne"><span class="el"><strong>Appel régulier</strong> <span class="muted">toutes les {ry["cadence_min"]}{NBSP}min au moins</span></span>'
            f'<span class="muted">au plus tard à {heure(ry["prochain_ts"])}</span></li>'
        )
    if en_cours or lignes:
        corps = '<ul class="decisions attente">' + "".join(lignes) + "".join(
            f'<li class="ligne"><span class="el">{element(x)}</span><span class="muted">jusqu’au {quand(x["expire_ts"], annee=False) if x.get("expire_ts") else "—"}</span></li>'
            for x in en_cours
        ) + "</ul>"
    else:
        corps = '<p class="vide vide-court">Rien en attente.</p>'
    histo = ""
    if at["historique"]:
        def issue(x: dict[str, Any]) -> str:
            if x["issue"] == "declenche":
                mot = "déclenchée" if x["type"] == "alerte" else "déclenché"
                det = f" · {x['issue_detail']}" if x.get("issue_detail") else ""
                return f'<span class="issue"><span class="pastille ok">{mot}</span><span class="muted">{e(det)}</span></span>'
            return f'<span class="issue"><span class="pastille neutre">{e(x.get("issue_detail") or "terminé")}</span></span>'

        rows = "".join(
            f'<li class="ligne"><span class="el">{element(x)}</span>{issue(x)}<span class="muted">{quand(x["ts"], annee=False)}</span></li>' for x in at["historique"]
        )
        histo = f'<details class="lecture precedents"><summary>Les précédents</summary><ul class="decisions attente">{rows}</ul></details>'
    return (
        '<section aria-labelledby="titre-attente"><h2 id="titre-attente">En attente <span class="h-note">prochain appel, alertes et ordres d’entrée</span></h2>'
        f"{corps}{histo}</section>"
    )


def _operations(p: dict[str, Any]) -> str:
    if not p["operations"]:
        return '<p class="vide">Aucune opération pour l’instant.</p>'
    motif = any(o["raison"] != P.RAISONS_FILL["intent"] for o in p["operations"])
    rows = "".join(
        f'<tr><td>{quand(o["ts"], annee=False)}</td><th scope="row">{e(o["instrument"])}</th>'
        f'<td>{"achat" if o["qty"] > 0 else "vente"} {e(quantite(o["qty"]))}</td><td class="n">{usd_prix(o["prix_uusd"])}</td>'
        f'<td class="n">{eur(o["frais_ueur"], decimals=4)}</td>'
        + (f'<td>{e(o["raison"])}</td>' if motif else "") + "</tr>"
        for o in p["operations"]
    )
    reste = p["n_operations"] - len(p["operations"])
    plus = f'<p class="muted">+{pluriel(reste, "opération plus ancienne", "opérations plus anciennes")} dans le journal.</p>' if reste > 0 else ""
    return empiler(
        '<div class="table-scroll" tabindex="0" role="region" aria-label="Tableau des opérations, défilable"><table class="tableau empile">'
        '<caption class="visuellement-cache">Opérations exécutées, de la plus récente à la plus ancienne</caption>'
        '<thead><tr><th scope="col">Quand</th><th scope="col">Contrat</th><th scope="col">Ordre</th><th scope="col" class="n">Prix</th>'
        '<th scope="col" class="n">Frais</th>' + ('<th scope="col">Motif</th>' if motif else "") + "</tr></thead>"
        f"<tbody>{rows}</tbody></table></div>{plus}",
        ["Contrat", "Ordre", "Prix", "Frais"] + (["Motif"] if motif else []),
    )


def portfolio_page(data: dict[str, Any], p: dict[str, Any]) -> str:
    conseil = p["kind"] == "conseil"
    llm = p["kind"] == "llm" or conseil  # le conseil décide comme une IA : décisions, attente, coût
    stats = [
        _stat("Rendement net", f'<span class="{tone(p["rendement"])}"{_crochet(p, "rend")}>{pct(p["rendement"])}</span>', cls="grand", carte="cle"),
        _stat(
            "Valeur", f'<span{_crochet(p, "val")}>{eur(p["equity_ueur"])}</span>',
            f'<small class="sous">départ {eur(p["capital_ueur"], decimals=0)}{f" · objectif {eur(2 * p['capital_ueur'], decimals=0)}" if conseil else ""}</small>',
        ),
        _stat("Levier", levier(p["levier"]), f'<small class="sous">exposition {eur(p["expo_ueur"], decimals=0)}</small>'),
        _stat("Pire baisse", pct(-p["drawdown_max"]) if p["drawdown_max"] else f"0,00{NBSP}%"),
        _stat(
            "Funding", _funding_cell(p),
            f'<small class="sous">payé {eur(p["funding_paye_ueur"])} · reçu {eur(p["funding_recu_ueur"])}</small>'
            if p["funding_paye_ueur"] or p["funding_recu_ueur"] else "",
        ),
        _stat("Frais", eur(p["frais_ueur"]), '<small class="sous">0,07 % par ordre</small>'),
    ]  # fmt: skip
    if llm:
        stats.append(_stat("Coût IA", usd(p["cout_uusd"]), f'<small class="sous">{"10 appels Haiku par ronde" if conseil else "équivalent API"}</small>'))
        q = (p.get("rythme") or {}).get("quota")
        jour = f'<small class="sous">{q["played_today"]} appels aujourd’hui, {q["per_day"]} au plus</small>' if q else ""
        stats.append(_stat("Décisions", str(p["n_rondes"]), f'<small class="sous">{pluriel(p["n_ordres"], "avec ordre", "avec ordres")}</small>{jour}'))
    else:
        stats.append(_stat("Positions", str(len(p["positions"])), '<small class="sous">ouvertes</small>'))
        stats.append(_stat("Opérations", str(p["n_operations"])))
    alertes = ""
    st = p.get("statut")
    if st and st["etat"] == "arrete" and conseil:
        alertes = (
            f'<p class="alerte perte-bg"><strong>Conseil arrêté</strong> le {quand(st["ts"]) if st.get("ts") else "—"} : ruine, baisse de 90{NBSP}% depuis son plus haut. '
            "Ses positions sont fermées et il ne joue plus. Seul l’opérateur de l’arène peut le relancer, à la main.</p>"
        )
    elif st and st["etat"] == "arrete":
        alertes = '<p class="alerte perte-bg">Portefeuille arrêté : baisse de 15 % depuis son sommet, positions fermées.</p>'
    elif st:
        jusqu = f" jusqu’au {quand(st['jusqu'])}" if st.get("jusqu") else ""
        cause = " après une liquidation" if st.get("raison") == "margin_closeout" else ""
        alertes = f'<p class="alerte warn">Portefeuille gelé{cause}{jusqu} : aucune nouvelle ouverture.</p>'
    chart = _ref_chart(data["perp"], p["id"])
    direct_pfs = [p] if _direct_pf(p) else []
    direct_etat = '<p class="direct-etat" data-direct-etat hidden></p>' if direct_pfs else ""
    decs = _decisions_groupees(p["decisions"])
    if llm or p["id"] == P.ALEATOIRE:
        vide = "Pas encore de décision : la première arrive au prochain rendez-vous." if llm else "Aucun tirage pour l’instant."
        decs_html = f'<ol class="decisions">{decs}</ol>' if decs else f'<p class="vide">{vide}</p>'
        decisions = f'<section aria-labelledby="titre-decisions"><h2 id="titre-decisions">Décisions <span class="h-note">du plus récent au plus ancien</span></h2>{decs_html}</section>'
        operations = (
            f'<section aria-labelledby="titre-operations"><details class="lecture"><summary><h2 id="titre-operations" class="h2-inline">Opérations</h2>'
            f' <span class="h-note">{pluriel(p["n_operations"], "opération")}</span></summary>{_operations(p)}</details></section>'
        )
    else:
        decisions = ""
        operations = f'<section aria-labelledby="titre-operations"><h2 id="titre-operations">Opérations</h2>{_operations(p)}</section>'
    body = f"""
<p class="fil"><a href="../index.html"><span aria-hidden="true">← </span>Ligue dérivés</a><span class="fil-sep" aria-hidden="true">/</span><span>{"Hors catégorie" if conseil else "Modèles d’IA" if llm else "Témoins"}</span></p>
<header class="tete-modele">
  <h1>{e(p["name"])}</h1>
  {f'<p class="marque-conseil">{e(p["marque"])}</p>' if p.get("marque") else ""}
  {f'<p class="chapo">{e(p["description"])}</p>' if p.get("description") else ""}
  {f'<p class="hors-regle">{e(p["hors_regle"])} <a href="../methode.html#m-conseil">Ses règles</a></p>' if p.get("hors_regle") else ""}
</header>
{alertes}
<dl class="stats">{"".join(stats)}</dl>
<section aria-labelledby="titre-courbe"><h2 id="titre-courbe">Rendement net <span class="h-note">frais et funding compris</span></h2>{_chart_block(chart, focus=p["id"], focus_name=p["name"])}</section>
<section aria-labelledby="titre-positions"><h2 id="titre-positions">Positions <span class="h-note">fictives, prix en dollars</span></h2>{direct_etat}{_positions(p)}</section>
{_attente(p) if llm else ""}
{decisions}
{operations}
"""
    return layout(
        title=f"{p['name']} · dérivés", body=body, root="../", active=p["id"], data=data, ligue="perp",
        scripts=(_chart_scripts("../", chart, p["id"], dernier="Dernier relevé") if courbe_visible(chart) else "") + _direct_scripts("../", data["perp"], direct_pfs),
        direct=bool(direct_pfs),
    )  # fmt: skip


# ---------------------------------------------------------------------------
# Méthode
# ---------------------------------------------------------------------------


def methode_section(data: dict[str, Any]) -> str:
    perp = data.get("perp")
    if not perp:
        return ""
    j = perp["journal"]
    ok = j["verify_ok"]
    outils = "".join(f"<li><strong>{e(k)}</strong> : {e(v)}</li>" for k, v in P.OUTILS.items())
    cad = perp.get("cadence_min") or 0
    cadence = f"<li><strong>Appel régulier</strong> : chaque IA est rappelée au plus tard {cad}{NBSP}min après sa dernière ronde.</li>\n" if cad else ""
    if perp.get("rondes_par_jour"):
        cadence += f"<li><strong>Plafond</strong> : {perp['rondes_par_jour']} appels par IA et par jour, rendez-vous compris.</li>\n"
    conseil = next((p for p in perp["portfolios"] if p["kind"] == "conseil"), None)
    membres = "".join(
        f"<li><strong>{e(n)}</strong> ({'étape ' + etape}) : {e(role)}</li>" for n, etape, role in P.MEMBRES.values()
    )
    section_conseil = (
        f"""<h3 id="m-conseil">Hors catégorie : le {e(conseil["name"])}</h3>
<p>Un portefeuille de plus, décidé par dix Claude Haiku 5.5 qui délibèrent à chaque ronde, avec un mandat agressif : doubler la mise en quelques jours. Il joue les mêmes rondes que les IA (rendez-vous, appel régulier, réveils, alertes, rappels) ; une ronde compte pour un appel dans le plafond du jour, et son coût est celui de ses dix appels.</p>
<p><strong>{e(P.HORS_REGLE_CONSEIL)}</strong> Il n’est donc jamais classé avec les IA, qui jouent toutes avec les mêmes règles.</p>
<ul class="liste-simple">
<li><strong>Étape A</strong> : huit membres donnent chacun un avis sans voir les autres (long, short ou plat par contrat, conviction de 0 à 100, taille, stop, niveau clé, argument).</li>
<li><strong>Étape B</strong> : l’Avocat du diable lit ces avis et attaque le trade le plus soutenu.</li>
<li><strong>Étape C</strong> : le Président lit les neuf avis et décide, au même format que les IA. Un membre en échec est laissé de côté ; sans Président, la ronde ne fait rien.</li>
</ul>
<details class="lecture"><summary>Les dix membres</summary><ul class="liste-simple">{membres}</ul></details>
<dl class="regles">
<div><dt>Levier</dt><dd>10 au plus, avec les marges de Kraken (1 à 2{NBSP}% du montant pour ouvrir) ; une entrée jusqu’à 500{NBSP}% de la valeur du portefeuille, une position jusqu’à 1{NNBSP}000{NBSP}%.</dd></div>
<div><dt>Stop</dt><dd>Obligatoire, entre 1 et 15{NBSP}%, et toujours avant la liquidation ; perte au stop de 25{NBSP}% du portefeuille au plus par trade, 60{NBSP}% pour tous les stops réunis.</dd></div>
<div><dt>Rythme</dt><dd>24 ouvertures par 24{NBSP}h au plus, sans délai entre deux ; ni gel quotidien, ni budget de frais (les frais restent réels et comptés).</dd></div>
<div><dt>Arrêt</dt><dd>À −90{NBSP}% depuis son plus haut (la ruine) : positions fermées, plus aucune ronde. Seul l’opérateur de l’arène peut le relancer, à la main.</dd></div>
<div><dt>Liquidation</dt><dd>Simulée comme chez Kraken : quand la valeur tombe sous la marge de maintenance (la moitié de la marge d’ouverture), testée chaque minute au pire prix, avec 5{NBSP}% de frais de liquidation ; puis 1{NBSP}h sans entrée.</dd></div>
</dl>
"""
        if conseil else ""
    )
    temoins = "".join(
        f'<div><dt>{e(P.NOMS[k].removeprefix("Témoin "))}</dt><dd>{e(v)}</dd></div>' for k, v in P.DESCRIPTIONS.items()
    )
    return f"""
<section aria-labelledby="m-derives"><h2 id="m-derives">La ligue dérivés</h2>
<p>Chaque portefeuille a {eur(1_000_000_000, decimals=0)} fictifs et négocie 6 contrats perpétuels de Kraken Futures (BTC, ETH, SOL, XRP, LINK, LTC), à la hausse (long) ou à la baisse (short).
Les IA décident aux rendez-vous de 02:00, 06:00, 10:00, 14:00, 18:00 et 22:00{NBSP}UTC. Une veille relève les prix toutes les 5{NBSP}min, déclenche stops et objectifs et compte le funding chaque heure.</p>
<dl class="regles">
<div><dt>Levier</dt><dd>2 au plus ; un ordre ne dépasse pas la moitié du portefeuille.</dd></div>
<div><dt>Stop</dt><dd>Obligatoire à chaque ouverture, entre 1 et 15{NBSP}% ; perte au stop de 3{NBSP}% du portefeuille au plus, 7,5{NBSP}% pour tous les stops réunis.</dd></div>
<div><dt>Garde-fous</dt><dd>Gel de 24{NBSP}h après une perte de 5{NBSP}% en un jour ; arrêt définitif après une baisse de 15{NBSP}% depuis le sommet ; position fermée après 7{NBSP}jours.</dd></div>
<div><dt>Coûts</dt><dd>Frais de 0,07{NBSP}% et glissement de 0,05{NBSP}% par ordre, arrondis défavorables ; funding horaire réel de Kraken ; clôture forcée si la marge tombe sous 25{NBSP}% de l’exposition.</dd></div>
<div><dt>Prix</dt><dd>En dollars, convertis en euros au cours EUR/USD du moment. Sur ce site, les positions sont aussi revalorisées en direct au prix public de Kraken (chiffres soulignés en pointillé) : une estimation, le chiffre officiel reste celui du relevé.</dd></div>
</dl>
{section_conseil}<h3>Les témoins</h3>
<dl class="regles">{temoins}</dl>
<h3>Ce que l’IA peut consulter</h3>
<p>Un instantané du compte et des 6 marchés, puis 4 appels au plus parmi 6 outils en lecture seule, figés au début de la ronde (ni web, ni donnée postérieure) :</p>
<ul class="liste-simple">{outils}</ul>
<p>Chaque décision donne une justification et, pour chaque ordre, une condition d’invalidation. Le garde-fou la juge, puis l’exécution est simulée.</p>
<h3>Entre deux rendez-vous</h3>
<ul class="liste-simple">
{cadence}<li><strong>Rappel demandé</strong> : à chaque décision, une IA peut demander à être rappelée dans 5 à 60{NBSP}min.</li>
<li><strong>Réveil de marché</strong> : un mouvement de 2{NBSP}% en 1{NBSP}h sur un contrat réveille les IA, 15{NBSP}min au moins entre deux réveils.</li>
<li><strong>Alerte</strong> : à chaque décision, une IA peut laisser 3 alertes de prix au plus. Une alerte franchie ne réveille qu’elle.</li>
<li><strong>Ordre d’entrée</strong> : 3 au plus, à un niveau de prix. Franchi, il passe le garde-fou puis s’exécute, sans rappeler l’IA. Chaque décision remplace ce qui était en attente.</li>
</ul>
<p><span class="pastille {"ok" if ok else "perte-bg"}">Journal de la ligue : {"chaîne intacte" if ok else "ÉCHEC"}</span> {pluriel(j["n_records"], "événement")}.</p>
</section>
"""
