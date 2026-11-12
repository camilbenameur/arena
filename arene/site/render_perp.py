"""Pages de la ligue dérivés : accueil (premier plan du site), une page par portefeuille, section de méthode.

Même direction « Carnet » que le spot : filets, peu de mots, chiffres tabulaires. Tout texte venu du journal est
échappé ; les textes libres des modèles (justification, invalidation) sont publiés tels quels, échappés, bornés.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from arene.site import perp as P
from arene.site.render import (
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


def declencheur(d: dict[str, Any] | None) -> str:
    if not d:
        return "réveil"
    mv = d.get("move_bp")
    if mv is None:
        return f"réveil · {d.get('instrument') or '?'}"
    return f"réveil · {d['instrument']} {pct(mv / 10_000, digits=1)} en 1{NBSP}h"


def _pastille_ronde(d: dict[str, Any]) -> str:
    if d.get("kind") != "wakeup":
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
        return ' <span class="pastille perte-bg">arrêté</span>'
    return ' <span class="pastille warn">gelé</span>'


def _depuis(perp: dict[str, Any], p: dict[str, Any]) -> str:
    """« depuis le 13 nov., 02:00 UTC » pour un portefeuille entré après l'ouverture de la ligue (rendement mesuré depuis)."""
    if perp.get("ouverte_ts") and p["ouvert_ts"] - perp["ouverte_ts"] > 900:
        return f'<small class="desc">depuis le {quand(p["ouvert_ts"], annee=False)}</small>'
    return ""


def _funding_cell(p: dict[str, Any]) -> str:
    n = p["funding_net_ueur"]
    if not p["funding_paye_ueur"] and not p["funding_recu_ueur"]:
        return '<span class="muted">—</span>'
    # Payé = coût : affiché en négatif pour le portefeuille.
    return f'<span class="{tone(-n)}">{eur(-n, signed=True)}</span>'


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
        f"{_legende(chart, focus)}</figure>"
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
            f'<tr class="{e(p["kind"])}"><th scope="row"><a href="derives/{e(p["slug"])}.html">{e(p["name"])}</a>{_statut(p)}{_depuis(perp, p)}</th>'
            f'<td class="n cle"><span class="{tone(p["rendement"])}">{pct(p["rendement"])}</span>{_svg_barre(p["rendement"], vmax)}</td>'
            f'<td class="n">{eur(p["equity_ueur"])}</td>'
            f'<td class="n">{levier(p["levier"])}</td>'
            f'<td class="n">{pct(-p["drawdown_max"]) if p["drawdown_max"] else "0,00" + NBSP + "%"}</td>'
            f'<td class="positions-cell">{_positions_cell(p)}</td></tr>'
        )

    def groupe(kind: str, titre: str, n_col: int) -> str:
        lignes = [ligne(p) for p in pfs if p["kind"] == kind]
        if not lignes:
            return ""
        return f'<tbody><tr class="groupe"><th scope="rowgroup" colspan="{n_col}">{titre}</th></tr>{"".join(lignes)}</tbody>'

    n_col = 6
    head = (
        '<tr><th scope="col">Portefeuille</th><th scope="col" class="n">Rendement net</th><th scope="col" class="n">Valeur</th>'
        '<th scope="col" class="n">Levier</th><th scope="col" class="n">Pire baisse</th><th scope="col">Positions</th></tr>'
    )
    libelles = ["Rendement net", "Valeur", "Levier", "Pire baisse", "Positions"]
    return empiler(
        '<div class="table-scroll" tabindex="0" role="region" aria-label="Tableau de la ligue dérivés, défilable">'
        '<table class="tableau comparatif empile"><caption class="visuellement-cache">Ligue dérivés : modèles d’IA puis témoins</caption>'
        f'<thead>{head}</thead>{groupe("llm", "Modèles d’IA", n_col)}{groupe("temoin", "Témoins", n_col)}</table></div>',
        libelles,
    )


def _dernieres(perp: dict[str, Any]) -> str:
    """La dernière décision de chaque IA : ce qu'elle a fait, et pourquoi, en une ligne dépliable."""
    items = []
    for p in perp["portfolios"]:
        if p["kind"] != "llm":
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
        corps = _justif(d)
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
    return _resume(d["actions"])


def index_page(data: dict[str, Any]) -> str:
    perp = data["perp"]
    pfs = perp["portfolios"]
    llms = [p for p in pfs if p["kind"] == "llm"]
    n_tem = len(pfs) - len(llms)
    capital = pfs[0]["capital_ueur"] if pfs else 1_000_000_000
    panier = next((p for p in pfs if p["id"] == P.PANIER), None)
    if llms and any(d["statut"] == "decidee" for p in llms for d in p["decisions"]):
        best = max(llms, key=lambda p: p["rendement"] or 0.0)
        verdict = f"En tête des IA : {best['name']} {pct(best['rendement'])}"
        if panier:
            verdict += f" · référence sans IA (panier) {pct(panier['rendement'])}"
    elif llms:
        verdict = f"Les {len(llms)}{NBSP}IA décident à partir du rendez-vous de {heure(perp['prochain_rdv_ts'])}"
    else:
        verdict = f"Témoins seuls pour l’instant · les 4{NBSP}IA entrent au rendez-vous de {heure(perp['prochain_rdv_ts'])}"
    qui = f"{len(llms)}{NBSP}IA et {n_tem}{NBSP}témoins sans IA" if llms else f"{n_tem}{NBSP}témoins sans IA"
    items = [f'<li>Prochain rendez-vous <time datetime="{iso(perp["prochain_rdv_ts"])}">{heure(perp["prochain_rdv_ts"])}</time></li>']
    if perp["live_ts"]:
        frais = data["generated_ts"] - perp["live_ts"] <= 1_800
        mot = "Valeurs en direct" if frais else "Dernières valeurs du"
        quand_txt = heure(perp["live_ts"]) if frais else when(perp["live_ts"], annee=False)
        items.append(f'<li>{mot} <time datetime="{iso(perp["live_ts"])}">{e(quand_txt)}</time></li>')
    if perp["journal"]["verify_ok"]:
        items.append('<li><a href="methode.html#m-derives">Journal vérifié</a></li>')
    else:
        items.append('<li class="perte-txt">Journal : vérification en échec</li>')

    body = f"""
<h1 class="visuellement-cache">Ligue dérivés : des IA gèrent chacune {eur(capital, decimals=0)} fictifs en contrats perpétuels, face à des témoins sans IA</h1>
<section class="etat" aria-label="État de la ligue dérivés">
  <p class="saison"><strong>Ligue dérivés</strong> · {qui} · {eur(capital, decimals=0)} fictifs chacun, à la hausse ou à la baisse</p>
  <p class="avancee"><strong>{e(verdict)}</strong></p>
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
  <li><strong>Levier</strong> : montant engagé divisé par la valeur du portefeuille. 2 au plus.</li>
  <li><strong>Gelé</strong> : plus d’ouverture pendant 24{NBSP}h après une perte de 5{NBSP}% en un jour.</li>
  </ul></details>
</section>
{_dernieres(perp)}
"""
    ch = perp["chart"]
    return layout(
        title="Ligue dérivés", body=body, root="", active="index", data=data, ligue="perp",
        scripts=_chart_scripts("", ch, None) if courbe_visible(ch) else "",
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
        f'<td class="n">{usd_prix(x["entree_uusd"])}</td><td class="n">{usd_prix(x["mark_uusd"])}</td>'
        + (f'<td class="n">{usd_prix(x["stop_uusd"])}</td>' if stop else "")
        + (f'<td class="n">{usd_prix(x["objectif_uusd"])}</td>' if obj else "")
        + f'<td class="n {tone(x["latent_ueur"])}">{eur(x["latent_ueur"], signed=True)}</td></tr>'
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


def _garde_fou(a: dict[str, Any]) -> str:
    v = a.get("verdict")
    if v is None:
        return '<span class="pastille neutre">sans verdict</span>'
    if v["approuve"]:
        return '<span class="pastille ok">accepté</span>'
    codes = "".join(f'<span class="code">{e(P.CODES.get(c, "règle inconnue"))}</span>' for c in v["motifs"])
    return f'<span class="pastille perte-bg">refusé</span><span class="codes">{codes}</span>'


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
        f'<tr><th scope="row">{e(a["instrument"])}</th><td>{_intention(a)}</td><td>{_garde_fou(a)}</td><td class="n">{_execution(a)}</td></tr>'
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
        out += f'<blockquote class="justif"><span class="etiquette">Raisonnement du modèle</span>{e(d["justification"])}</blockquote>'
    if d.get("outils"):
        outils = ", ".join(
            f'{e(OUTILS_COURTS.get(o["outil"], o["outil"]))}{(" " + e(o["args"])) if o["args"] else ""}{" (erreur)" if o["erreur"] else ""}'
            for o in d["outils"]
        )
        out += f'<p class="outils"><span class="etiquette">A consulté</span>{outils}</p>'
    return out


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
            txt = '<span class="muted">Aucun ordre</span>'
        resume = f'<span class="quand">{quand(d["ts"])}</span>{ronde}{txt}{_meta(d)}'
        corps = _justif(d)
        return f'<li class="ligne"><details><summary>{resume}</summary>{corps}</details></li>' if corps else f'<li class="ligne">{resume}</li>'
    tete = f'{ronde}<span class="resume-ordres">{e(_resume(d["actions"]))}</span>'
    corps = f'<div class="decision-pile">{_justif(d)}{_actions(d)}</div>'
    return f'<li class="decision"><article><header><h3>{quand(d["ts"])}</h3>{tete}{_meta(d)}</header>{corps}</article></li>'


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
    llm = p["kind"] == "llm"
    stats = [
        _stat("Rendement net", pct(p["rendement"]), cls=f"grand {tone(p['rendement'])}", carte="cle"),
        _stat("Valeur", eur(p["equity_ueur"]), f'<small class="sous">départ {eur(p["capital_ueur"], decimals=0)}</small>'),
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
        stats.append(_stat("Coût IA", usd(p["cout_uusd"]), '<small class="sous">équivalent API</small>'))
        stats.append(_stat("Décisions", str(p["n_rondes"]), f'<small class="sous">{pluriel(p["n_ordres"], "avec ordre", "avec ordres")}</small>'))
    else:
        stats.append(_stat("Positions", str(len(p["positions"])), '<small class="sous">ouvertes</small>'))
        stats.append(_stat("Opérations", str(p["n_operations"])))
    alertes = ""
    st = p.get("statut")
    if st and st["etat"] == "arrete":
        alertes = '<p class="alerte perte-bg">Portefeuille arrêté : baisse de 15 % depuis son sommet, positions fermées.</p>'
    elif st:
        jusqu = f" jusqu’au {quand(st['jusqu'])}" if st.get("jusqu") else ""
        alertes = f'<p class="alerte warn">Portefeuille gelé{jusqu} : aucune nouvelle ouverture.</p>'
    chart = _ref_chart(data["perp"], p["id"])
    decs = "".join(_decision(d) for d in p["decisions"])
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
<p class="fil"><a href="../index.html"><span aria-hidden="true">← </span>Ligue dérivés</a><span class="fil-sep" aria-hidden="true">/</span><span>{"Modèles d’IA" if llm else "Témoins"}</span></p>
<header class="tete-modele">
  <h1>{e(p["name"])}</h1>
  {f'<p class="chapo">{e(p["description"])}</p>' if p.get("description") else ""}
</header>
{alertes}
<dl class="stats">{"".join(stats)}</dl>
<section aria-labelledby="titre-courbe"><h2 id="titre-courbe">Rendement net <span class="h-note">frais et funding compris</span></h2>{_chart_block(chart, focus=p["id"], focus_name=p["name"])}</section>
<section aria-labelledby="titre-positions"><h2 id="titre-positions">Positions <span class="h-note">fictives, prix en dollars</span></h2>{_positions(p)}</section>
{decisions}
{operations}
"""
    return layout(
        title=f"{p['name']} · dérivés", body=body, root="../", active=p["id"], data=data, ligue="perp",
        scripts=_chart_scripts("../", chart, p["id"]) if courbe_visible(chart) else "",
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
<div><dt>Prix</dt><dd>En dollars, convertis en euros au cours EUR/USD du moment.</dd></div>
</dl>
<h3>Les témoins</h3>
<dl class="regles">{temoins}</dl>
<h3>Ce que l’IA peut consulter</h3>
<p>Un instantané du compte et des 6 marchés, puis 4 appels au plus parmi 6 outils en lecture seule, figés au début de la ronde (ni web, ni donnée postérieure) :</p>
<ul class="liste-simple">{outils}</ul>
<p>Chaque décision donne une justification et, pour chaque ordre, une condition d’invalidation. Le garde-fou la juge, puis l’exécution est simulée.</p>
<p><span class="pastille {"ok" if ok else "perte-bg"}">Journal de la ligue : {"chaîne intacte" if ok else "ÉCHEC"}</span> {pluriel(j["n_records"], "événement")}.</p>
</section>
"""
