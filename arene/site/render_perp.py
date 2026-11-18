"""Pages de la ligue dérivés (accueil au premier plan du site, une page par portefeuille, section de méthode) et de la
ligue des conseils (accueil, une page par conseil, méthode des conseils ; même journal que les dérivés).

Même direction « Carnet » que le spot : filets, peu de mots, chiffres tabulaires. Tout texte venu du journal est
échappé ; les textes libres des modèles (justification, invalidation) sont publiés tels quels, échappés, bornés.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from arene.site import lisible as L
from arene.site import perp as P
from arene.site.perp import IMPACTS as IMPACTS_FR
from arene.site.render import (
    FLUX_DIRECT,
    MINUS,
    NBSP,
    NNBSP,
    _chart_scripts,
    _group,
    _legende,
    dernier_valeur,
    jj_mm,
    _stat,
    e,
    empiler,
    eur,
    heure,
    iso,
    json_inline,
    layout,
    nom_court,
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


def _apres(rel: list[dict[str, Any]]) -> str:
    return " et ".join(r["label"] for r in rel)


def declencheur(d: dict[str, Any] | None) -> str:
    if not d:
        return "réveil"
    if d.get("type") == "annonce":
        n = len(d.get("annonces") or [])
        return "annonce de Kraken" + (
            f" · {d['annonces'][0]['title']}" if n == 1 else f" · {n}{NBSP}annonces" if n > 1 else ""
        )
    if d.get("type") == "publication":
        return "publication macro" + (f" · après {_apres(d['releases'])}" if d.get("releases") else "")
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
    avec = ""
    n = (d.get("declencheur") or {}).get("news")
    if n and k not in (
        "news",
        "calendar",
    ):  # un autre déclencheur qui portait aussi une annonce ou une publication
        avec = f' <span class="pastille discret" title="{e(_news_titre(n))}">{"annonce de Kraken" if n["annonces"] else "publication macro"} jointe</span>'
    if k == "barre":
        return '<span class="pastille discret">clôture de barre 4 h</span> '
    if k == "restauration":
        return '<span class="pastille discret">fin d’un freinage</span> '
    if k == "veto":
        return f'<span class="pastille reveil">veto · {e(declencheur(d.get("declencheur")))}</span> '
    if k == "cadence":
        return f'<span class="pastille discret">appel régulier</span>{avec} '
    if k == "scheduled":
        return f'<span class="pastille neutre">à sa demande</span>{avec} '
    if k in ("news", "calendar"):
        dec = d.get("declencheur") or {"type": "annonce" if k == "news" else "publication"}
        return f'<span class="pastille reveil">{e(declencheur(dec))}</span> '
    if k not in ("wakeup", "alert", "ordre"):
        return ""
    return f'<span class="pastille reveil">{e(declencheur(d.get("declencheur")))}</span>{avec} '


def _news_titre(n: dict[str, Any]) -> str:
    return " ; ".join([*(f"après {r['label']}" for r in n["releases"]), *(a["title"] for a in n["annonces"])])


NATURES = {
    "incident": "incident",
    "maintenance": "maintenance",
    "delisting": "retrait de contrat",
    "contract_state": "état du contrat",
}
STATUTS = {
    "investigating": "en analyse", "identified": "cause identifiée", "monitoring": "sous surveillance", "resolved": "résolu",
    "postmortem": "analyse terminée", "scheduled": "programmée", "in_progress": "en cours", "verifying": "en vérification",
    "completed": "terminée", "abnormal": "anormal", "normal": "normal", "unlisted": "retiré de la cote",
}  # fmt: skip
CLOS = {"resolved", "postmortem", "completed", "normal", "unlisted"}


def _annonce(a: dict[str, Any]) -> str:
    statut = STATUTS.get(a["status"], a["status"] or "statut inconnu")
    ton = "neutre" if a["status"] in CLOS else ("info" if a["kind"] == "maintenance" else "warn")
    impact = IMPACTS_FR.get(a["impact"])
    morceaux = [f'<span class="pastille {ton}">{e(statut)}</span>']
    if impact and a["status"] not in CLOS:
        morceaux.append(
            f'<span class="pastille {"perte-bg" if a["impact"] in ("major", "critical") else "warn"}">impact {impact}</span>'
        )
    plage = ""
    if a["starts_ts"] and a["ends_ts"]:
        plage = f"du {when(a['starts_ts'], annee=False)} au {when(a['ends_ts'], annee=False)}"
    elif a["starts_ts"]:
        plage = f"à partir du {when(a['starts_ts'], annee=False)}"
    elif a["ends_ts"]:
        plage = f"jusqu’au {when(a['ends_ts'], annee=False)}"
    sous = [e(NATURES.get(a["kind"], "annonce"))]
    if plage:
        sous.append(e(plage))
    if a["instruments"]:
        sous.append(e("contrats : " + ", ".join(a["instruments"])))
    sous.append(f"mis à jour {quand(a['maj_ts'], annee=False)}")
    lien = f' <a href="{e(a["url"])}" rel="noopener noreferrer">Lien Kraken</a>' if a["url"] else ""
    return (
        f'<li class="ligne sans-detail actu"><span class="actu-titre">{e(a["title"])}</span> {" ".join(morceaux)}'
        f'<span class="muted actu-sous">{" · ".join(sous)}{lien}</span></li>'
    )


def actualites_block(perp: dict[str, Any]) -> str:
    """Le calendrier macro des 7 prochains jours et les annonces de Kraken sur les dérivés des 7 derniers jours."""
    act = perp.get("actualites")
    if act is None:
        return ""
    lignes = []
    cal = act.get("calendrier")
    if cal is not None:
        if cal:
            for c in cal:
                rappel = (
                    ' <span class="pastille reveil">rappelle les IA 3 min après</span>' if c["rappel"] else ""
                )
                lignes.append(
                    f'<li class="ligne sans-detail actu"><span class="actu-titre">{e(c["label"])}</span> <span class="muted">{quand(c["ts"], annee=False)}</span>{rappel}</li>'
                )
            cal_html = (
                f'<h3>Prochaines publications macro</h3><ul class="decisions actus">{"".join(lignes)}</ul>'
            )
        else:
            cal_html = '<h3>Prochaines publications macro</h3><p class="muted">Aucune publication macro dans les 7 prochains jours.</p>'
    else:
        cal_html = ""
    ann = act.get("annonces") or []
    if ann:
        ann_html = (
            f'<h3>Annonces de Kraken</h3><ul class="decisions actus">{"".join(_annonce(a) for a in ann)}</ul>'
        )
    else:
        ann_html = '<h3>Annonces de Kraken</h3><p class="muted">Aucune annonce de Kraken sur les dérivés depuis 7 jours.</p>'
    return (
        '<section aria-labelledby="titre-actualites"><h2 id="titre-actualites">Actualités <span class="h-note">sources officielles seulement</span></h2>'
        f'{cal_html}{ann_html}<p class="muted"><a href="methode.html#m-actualites">Ce que voient les IA</a></p></section>'
    )


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
    arch = p.get("archive")
    if arch:
        return f' <span class="pastille neutre">archivé le {jj_mm(arch["ts"])}</span>'
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


def _dossier(p: dict[str, Any]) -> str:
    """Le dossier de la page d'un portefeuille : les conseils ont le leur, le témoin panier reste aux dérivés."""
    return "conseils" if p["kind"] == "conseil" or p["id"] == P.MOTEUR else "derives"


def _hors_regle_court(p: dict[str, Any]) -> str:
    return '<small class="desc">démonstration paper, hors règle 2x</small>' if p["kind"] == "conseil" else ""


def _codes(d: dict[str, Any]) -> dict[str, str]:
    return {"conseil": P.CODES_CONSEIL, "tendance": P.CODES_TENDANCE}.get(str(d.get("regles")), P.CODES)


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


def _chart_block(chart: dict[str, Any], *, focus: str | None = None, focus_name: str | None = None, ligue: str = "derives") -> str:
    if not courbe_visible(chart):
        return '<p class="vide vide-court">La courbe apparaît après 1{NBSP}h{NBSP}30 de relevés. Les valeurs sont dans le tableau.</p>'.replace("{NBSP}", NBSP)
    derniers = "; ".join(
        f"{s['name']}{' (archivé)' if s.get('archive_ts') else ''} {pct((dernier_valeur(s['values']) - 100) / 100) if dernier_valeur(s['values']) is not None else '—'}"
        for s in chart["series"]
    )
    periode = f"du {when(chart['x'][0])} au {when(chart['x'][-1])}"
    if focus_name:
        label = f"Rendement net cumulé de {focus_name}, comparé au témoin panier 1x, {periode}. Valeurs en direct : {derniers}."
    else:
        label = f"Rendement net cumulé des {len(chart['series'])} portefeuilles {'de la ligue des conseils' if ligue == 'conseils' else 'dérivés'}, {periode}. Valeurs en direct : {derniers}."
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


def _tableau(perp: dict[str, Any], *, conseils: bool = False) -> str:
    pfs = perp["portfolios"]
    vmax = max((abs(p["rendement"] or 0.0) for p in pfs), default=0.0)
    from arene.site.render import _svg_barre

    def ligne(p: dict[str, Any]) -> str:
        sous = f'<small class="desc">{e(p["sous_titre"])}</small>' if p.get("sous_titre") else ""
        return (
            f'<tr class="{e(p["kind"])}{" archive" if p.get("archive") else ""}"><th scope="row"><a href="{_dossier(p)}/{e(p["slug"])}.html">{e(p["name"])}</a>{_statut(p)}{sous}{_depuis(perp, p)}{_hors_regle_court(p)}</th>'
            f'<td class="n cle"><span class="{tone(p["rendement"])}"{_crochet(p, "rend")}>{pct(p["rendement"])}</span>{_svg_barre(p["rendement"], vmax)}</td>'
            f'<td class="n"><span{_crochet(p, "val")}>{eur(p["equity_ueur"])}</span></td>'
            f'<td class="n">{levier(p["levier"])}</td>'
            f'<td class="n">{pct(-p["drawdown_max"]) if p["drawdown_max"] else "0,00" + NBSP + "%"}</td>'
            f'<td class="positions-cell">{_positions_cell(p)}</td></tr>'
        )

    def groupe(kind: str, titre: str, n_col: int, note: str = "") -> str:
        lignes = [ligne(p) for p in sorted((p for p in pfs if p["kind"] == kind), key=lambda p: bool(p.get("archive")))]
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
    if conseils:
        nom, corps = "ligue des conseils", groupe("conseil", "Conseils", n_col, P.MARQUE_CONSEIL) + groupe("temoin", "Témoin", n_col)
        cap = "Ligue des conseils : les conseils, puis le témoin de référence"
    else:
        nom, corps = "ligue dérivés", groupe("llm", "Modèles d’IA", n_col) + groupe("temoin", "Témoins", n_col)
        cap = "Ligue dérivés : modèles d’IA, puis témoins"
    return empiler(
        f'<div class="table-scroll" tabindex="0" role="region" aria-label="Tableau de la {nom}, défilable">'
        f'<table class="tableau comparatif empile"><caption class="visuellement-cache">{cap}</caption>'
        f'<thead>{head}</thead>{corps}</table></div>',
        libelles,
    )


def _dernieres(perp: dict[str, Any], titre: str = "Dernières décisions des IA") -> str:
    """La dernière décision de chaque IA : ce qu'elle a fait et pourquoi, en carte ; le détail replié."""
    items = []
    for p in perp["portfolios"]:
        if p["kind"] not in ("llm", "conseil"):
            continue
        d = next((x for x in p["decisions"] if x["statut"] in ("decidee", "echec", "sautee")), None)
        lien = f'<a class="dernier-nom" href="{_dossier(p)}/{e(p["slug"])}.html">{e(p["name"])}</a>'
        if d is None:
            items.append(f'<li class="decision carte-dec"><article><p class="dec-tete">{lien}</p><p class="dec-quoi muted">Pas encore de décision</p></article></li>')
            continue
        items.append(_decision(d, qui=lien))
    if not items:
        return ""
    return (
        f'<section aria-labelledby="titre-dernieres"><h2 id="titre-dernieres">{titre}</h2>'
        f'<ul class="decisions dernieres cartes">{"".join(items)}</ul></section>'
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


def _releve(data: dict[str, Any], perp: dict[str, Any], direct_pfs: list[dict[str, Any]], extra: str = "") -> str:
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
    return f'<ul class="releve">{extra}{"".join(items)}</ul>'


def _lecture(conseils: bool) -> str:
    if conseils:
        items = (
            f"<li><strong>Conseil</strong> : plusieurs IA qui délibèrent avant qu’un président décide. {e(P.HORS_REGLE_CONSEIL)}</li>"
            "<li><strong>Témoin</strong> : le panier 1x (acheter et garder, sans IA) sert de référence ; il est aussi dans la ligue des IA seules.</li>"
            "<li><strong>Long, short</strong> : parier sur la hausse, sur la baisse.</li>"
            "<li><strong>Levier</strong> : montant engagé divisé par la valeur du portefeuille. 10 au plus pour un conseil.</li>"
        )
    else:
        items = (
            "<li><strong>Témoin</strong> : une règle fixe, sans IA. Le panier 1x (acheter et garder) est la référence : une IA utile doit faire mieux, frais compris.</li>"
            "<li><strong>Long, short</strong> : parier sur la hausse, sur la baisse.</li>"
            "<li><strong>Levier</strong> : montant engagé divisé par la valeur du portefeuille. 2 au plus.</li>"
            f"<li><strong>Gelé</strong> : plus d’ouverture pendant 24{NBSP}h après une perte de 5{NBSP}% en un jour.</li>"
        )
    return f'<details class="lecture"><summary>Comment lire ce tableau</summary><ul class="liste-simple">{items}</ul></details>'


def index_page(data: dict[str, Any]) -> str:
    """La ligue des IA seules (dérivés), sur derives.html : classement et courbe au premier écran."""
    from arene.site import accueil as A

    perp = data["perp"]
    pfs = perp["portfolios"]
    tous_llms = [p for p in pfs if p["kind"] == "llm"]
    llms = [p for p in tous_llms if not p.get("archive")]  # les archivés ne jouent plus : ils ne sont plus comptés
    archives = [p for p in tous_llms if p.get("archive")]
    capital = pfs[0]["capital_ueur"] if pfs else 1_000_000_000
    n_tem = len(pfs) - len(tous_llms)
    direct_pfs = [p for p in pfs if _direct_pf(p)]
    noms = [nom_court(p["name"]).replace("Claude ", "") for p in llms]
    if llms:
        titre = f"{_nombre(len(llms))} IA Claude tradent chacune {eur(capital, decimals=0)} fictifs en contrats crypto, à la hausse comme à la baisse."
        chapo = (
            f"{e(_liste_et(noms))} décident chacune seule, plusieurs fois par heure, avec un levier de 2 au plus, "
            f"sur les prix réels de Kraken. {_nombre(n_tem)} règles fixes sans IA servent de témoins ; la référence est le panier acheté et gardé."
        )
        if archives:
            noms_arch = _liste_et([nom_court(p["name"]).replace("Claude ", "") for p in archives])
            chapo += f" {e(noms_arch)}, archivé{'s' if len(archives) > 1 else ''}, reste{'nt' if len(archives) > 1 else ''} en pointillés."
    else:
        titre = f"Des IA Claude tradent {eur(capital, decimals=0)} fictifs chacune en contrats crypto."
        chapo = f"Témoins seuls pour l’instant ; les IA entrent au rendez-vous de {heure(perp['prochain_rdv_ts'])}."
    autre = ""
    if perp.get("conseils"):
        autre = '<li><a href="conseils.html">Voir aussi la ligue des conseils</a></li>'
    body = A.une(
        titre=titre, chapo=chapo,
        classement=A.scores(A._perp_rows(perp), label="Classement de la ligue des IA seules, rendement net"),
        apres=_releve(data, perp, direct_pfs),
        courbe=_chart_block(perp["chart"]) + _archives(tous_llms),
    ) + f"""
{_dernieres(perp)}
<section aria-labelledby="titre-comparatif">
  <h2 id="titre-comparatif">Tous les portefeuilles <span class="h-note">frais et funding compris</span></h2>
  {_tableau(perp)}
  {_lecture(False)}
</section>
{actualites_block(perp)}
<ul class="autres-ligues">{autre}<li><a href="comptant.html">Voir aussi la ligue comptant</a></li></ul>
"""
    ch = perp["chart"]
    return layout(
        title="IA seules", body=body, root="", active="derives", data=data, ligue="perp", chemin="derives.html",
        titre_complet=f"Ligue des IA seules : {_nombre(len(llms)).lower()} IA Claude tradent de l’argent fictif" if llms else "Ligue des IA seules",
        desc=f"{_liste_et(noms) if noms else 'Haiku, Sonnet, Opus et Fable'} tradent chacune {eur(capital, decimals=0)} fictifs en contrats crypto, en simulation sur les prix de Kraken, face à des stratégies sans IA. Classement et décisions expliquées.",
        scripts=(_chart_scripts("", ch, None, dernier="Dernier relevé") if courbe_visible(ch) else "") + _direct_scripts("", perp, direct_pfs),
        direct=bool(direct_pfs),
    )  # fmt: skip


def _desc_pf(p: dict[str, Any]) -> str:
    """Méta-description d'une page de portefeuille : qui, quoi, son rendement, en simulation."""
    qui = {"conseil": "Un conseil de dix IA Claude Haiku et un président", "llm": "Une IA Claude seule"}.get(p["kind"], "Une règle fixe sans IA, témoin")
    if p["id"] == P.CONSEIL_TENDANCE:
        qui = "Un moteur de tendance que trois IA Claude Haiku et un président Opus peuvent seulement freiner"
    return (
        f"{p['name']} : {qui[:1].lower() + qui[1:]}, {eur(p['capital_ueur'], decimals=0)} fictifs en contrats crypto sur les prix de Kraken. "
        f"Rendement net {pct(p['rendement'])}, chaque décision expliquée. Simulation."
    )


def _nombre(n: int) -> str:
    return {1: "Une", 2: "Deux", 3: "Trois", 4: "Quatre", 5: "Cinq", 6: "Six"}.get(n, str(n))


def _liste_et(mots: list[str]) -> str:
    return mots[0] if len(mots) == 1 else ", ".join(mots[:-1]) + " et " + mots[-1]


def _experience(conseils: list[dict[str, Any]]) -> str:
    """Ce que la ligue mesure, en deux phrases."""
    if len(conseils) >= 2:
        return (
            "Deux conseils jouent les mêmes rondes sur les mêmes marchés, avec les mêmes dix conseillers Haiku, les mêmes consignes et la même politique agressive. "
            "Seul le Président change, Haiku pour l’un et Opus pour l’autre : la ligue mesure ce qu’un Président plus cher change au résultat."
        )
    return (
        "Le Conseil Haiku joue seul pour l’instant ; le Conseil Opus le rejoint au déploiement. "
        "Ils auront les mêmes dix conseillers Haiku, les mêmes consignes et la même politique : seul le Président changera, Haiku ou Opus."
    )


def _archives(pfs: list[dict[str, Any]]) -> str:
    """Les portefeuilles retirés de la ligue : leurs données restent, leur courbe est en pointillés et s'arrête au retrait."""
    arch = [p for p in pfs if p.get("archive")]
    if not arch:
        return ""
    noms = _liste_et([f"{p['name']} (le {jj_mm(p['archive']['ts'])})" for p in arch])
    quoi = "conseils archivés" if all(p["kind"] == "conseil" for p in arch) else "portefeuilles archivés"
    return (
        f'<p class="arrivee">Courbes en pointillés : {quoi}, retirés de la ligue avec leurs positions fermées. '
        f"Leur rendement est figé à leur retrait : {e(noms)}.</p>"
    )


def _arrivees(pfs: list[dict[str, Any]]) -> str:
    """Un portefeuille entré après les autres : sa courbe commence à son arrivée, et on le dit sous le graphique."""
    if len(pfs) < 2:
        return ""
    debut = min(p["ouvert_ts"] for p in pfs)
    tard = [p for p in pfs if p["ouvert_ts"] - debut > 3_600 and not p.get("archive")]
    return "".join(
        f'<p class="arrivee">Le {e(p["name"])} a rejoint la ligue le {quand(p["ouvert_ts"], annee=False)} : sa courbe commence là.</p>'
        for p in tard
    )


def _etapes_tendance() -> str:
    return f"""
<section class="etapes" aria-labelledby="titre-etapes">
  <h2 id="titre-etapes">Comment le Conseil Tendance décide</h2>
  <ol class="etapes-liste">
  <li><span class="etape-num">1</span><p><strong>Le moteur décide.</strong> À chaque clôture de barre de 4 heures (00:00, 04:00, 08:00…, UTC), il donne la cible de chaque contrat : long, short ou à plat, avec une taille réglée sur la volatilité.</p></li>
  <li><span class="etape-num">2</span><p><strong>Les IA peuvent freiner.</strong> Trois Haiku (actualités, données, risque) conseillent, un Président Opus fixe un coefficient de 1, 0,5 ou 0 par contrat. Il ne peut ni augmenter, ni inverser, ni ouvrir : sans avis, le moteur joue seul.</p></li>
  <li><span class="etape-num">3</span><p><strong>Le code exécute</strong> l’écart entre la cible et la position, seulement s’il dépasse 5{NBSP}% du portefeuille, avec un stop à 5{NBSP}%. Le garde-fou peut refuser ; l’ordre est alors réduit jusqu’à passer.</p></li>
  </ol>
</section>"""


def conseils_page(data: dict[str, Any]) -> str:
    """Accueil de la ligue des conseils (page du post LinkedIn) : la phrase, le classement et la courbe, puis les
    dernières décisions en clair ; le tableau complet, les actualités et la méthode viennent après."""
    from arene.site import accueil as A

    perp = data["perp"]["conseils"]
    pfs = perp["portfolios"]
    conseils = [p for p in pfs if p["kind"] == "conseil"]
    capital = pfs[0]["capital_ueur"] if pfs else 1_000_000_000
    direct_pfs = [p for p in pfs if _direct_pf(p)]
    n = len(conseils)
    tendance = any(p["id"] == P.CONSEIL_TENDANCE for p in conseils)
    if tendance:
        titre = f"Un conseil d’IA Claude freine un moteur de tendance : {eur(capital, decimals=0)} fictifs."
        chapo = (
            "Un moteur de suivi de tendance décide de chaque position toutes les 4 heures ; trois Claude Haiku et un Président Opus "
            "ne peuvent que le freiner (un coefficient de 1, 0,5 ou 0 par contrat). Objectif fixé : 1 % par jour ; le rendement "
            "réalisé s’affiche à côté, face à un témoin « moteur seul » sans IA. Sur la courbe, ce témoin est le ruban gris "
            "sous la ligne du conseil : tant que le conseil ne freine rien, les deux se confondent."
        ) + (
            " Les anciens conseils Haiku et Opus, retirés le 17/11, restent archivés : leur courbe est en pointillé."
            if any(p["id"] != P.CONSEIL_TENDANCE for p in conseils) else ""
        )
    elif n >= 2:
        titre = f"{_nombre(n)} conseils d’IA Claude tradent {eur(capital, decimals=0)} fictifs chacun. Seul leur président change."
        chapo = (
            "Dix conseillers Claude Haiku donnent leur avis sur des contrats crypto, plusieurs fois par heure ; "
            "un président tranche : Haiku pour l’un, Opus pour l’autre. Mandat agressif (levier jusqu’à 10, objectif : doubler la mise), "
            "en simulation sur les prix réels de Kraken, face à un témoin sans IA."
        )
    else:
        titre = f"Un conseil d’IA Claude trade {eur(capital, decimals=0)} fictifs."
        chapo = e(_experience(conseils))
    body = A.une(
        titre=titre, chapo=chapo,
        classement=A.scores(A._perp_rows(perp), label="Classement de la ligue des conseils, rendement net"),
        apres=_releve(data, perp, direct_pfs),
        courbe=_chart_block(perp["chart"], ligue="conseils") + _arrivees(conseils) + _archives(conseils),
    ) + (_etapes_tendance() if tendance else "") + ("" if tendance else """
<section class="etapes" aria-labelledby="titre-etapes">
  <h2 id="titre-etapes">Comment un conseil décide</h2>
  <ol class="etapes-liste">
  <li><span class="etape-num">1</span><p><strong>Neuf avis, sans se voir.</strong> Chaque conseiller Haiku a un rôle (tendance, cassures, carnet d’ordres, risque…) et dit hausse, baisse ou rien, contrat par contrat.</p></li>
  <li><span class="etape-num">2</span><p><strong>L’avocat du diable</strong> lit ces avis et attaque le pari le plus soutenu.</p></li>
  <li><span class="etape-num">3</span><p><strong>Le président tranche</strong> et passe les ordres. Un garde-fou automatique peut les refuser.</p></li>
  </ol>
</section>""") + f"""
{_dernieres(perp, "Ce qu’ils viennent de décider")}
<section aria-labelledby="titre-comparatif">
  <h2 id="titre-comparatif">Le détail des portefeuilles <span class="h-note">frais et funding compris</span></h2>
  {_tableau(perp, conseils=True)}
  {_lecture(True)}
</section>
{actualites_block(perp)}
<details class="lecture methode-pliee" id="m-conseils-plie"><summary>Les règles des conseils : levier, stops, budget</summary>
{methode_conseils(data)}
</details>
<ul class="autres-ligues"><li><a href="derives.html">Voir aussi les IA seules</a></li><li><a href="comptant.html">Voir aussi la ligue comptant</a></li></ul>
"""
    ch = perp["chart"]
    return layout(
        title="Conseils d’IA", body=body, root="", active="conseils", data=data, ligue="conseils", chemin="conseils.html",
        image="apercu-conseils.png",
        titre_complet=(
            "Un conseil d’IA Claude freine un moteur de tendance, sur de l’argent fictif"
            if tendance else "Deux conseils d’IA Claude tradent de l’argent fictif : Haiku ou Opus à la présidence ?"
        ),
        desc=(
            "Un moteur de tendance décide, trois Claude Haiku et un président Opus ne peuvent que le freiner : 1 000 € fictifs sur les prix réels de Kraken, face à un témoin moteur seul. Classement en direct, chaque décision expliquée."
            if tendance else "Dix Claude Haiku délibèrent, un président Haiku ou Opus tranche : deux conseils d’IA tradent 1 000 € fictifs chacun sur les prix réels de Kraken. Classement en direct, chaque décision expliquée."
        ),
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


def _president(d: dict[str, Any]) -> str:
    """« Président · Opus » : le modèle du Président, discret (rien si le journal ne le dit pas)."""
    m = (d.get("conseil") or {}).get("president")
    return f' <span class="modele-president">Président · {e(m)}</span>' if m else ""


def _justif(d: dict[str, Any]) -> str:
    out = ""
    if d.get("justification"):
        qui = "Étape C · le Président tranche" if d.get("conseil") else "Raisonnement du modèle"
        out += f'<blockquote class="justif"><span class="etiquette">{qui}{_president(d)}</span>{e(d["justification"])}</blockquote>'
    if d.get("outils"):
        outils = ", ".join(
            f'{e(OUTILS_COURTS.get(o["outil"], o["outil"]))}{(" " + e(o["args"])) if o["args"] else ""}{" (erreur)" if o["erreur"] else ""}'
            for o in d["outils"]
        )
        out += f'<p class="outils"><span class="etiquette">A consulté</span>{outils}</p>'
    return out


# ---------------------------------------------------------------------------
# Délibération d'un conseil : étape A (des avis sans se voir), B (l'Avocat du diable), C (le Président : la décision)
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
    if "propositions" in a:  # un conseiller du Conseil Tendance : des freinages, pas des avis de marché
        avis = "".join(
            f"<li><strong>{e(x['instrument'])}</strong> ×{e((x['coefficient'] or '?').replace('.', ','))}"
            + (f" · {e(x['raison'])}" if x.get("raison") else "")
            + "</li>"
            for x in a["propositions"]
        ) or '<li class="muted">aucun freinage proposé</li>'
    else:
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


AVIS_DETAILLES = 12  # sur une page de conseil, les avis complets des 12 dernières rondes ; avant, le résumé seul
_RESUME_SEUL: set[int] = set()  # id() des décisions dont la page ne montre que le résumé de la délibération


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
    if id(d) in _RESUME_SEUL:  # page légère : le détail des avis anciens reste dans le journal et data/conseils.json
        return f'<p class="outils">{resume}<span class="muted"> · avis complets dans le journal et <code>data/conseils.json</code></span></p>'
    corps = ""
    if a_avis:
        n_a_abs = sum(1 for a in a_avis if a["absent"])
        note_a = "sans se voir" + (f" · {pluriel(n_a_abs, 'absent', 'absents')}" if n_a_abs else "")
        corps += f'<h4 class="etape">Étape A · {pluriel(len(a_avis) - n_a_abs, "avis indépendant", "avis indépendants")}<span class="h-note">{note_a}</span></h4><ol class="avis">{"".join(_membre(a) for a in a_avis)}</ol>'
    if b_avis:
        corps += f'<h4 class="etape">Étape B · l’Avocat du diable<span class="h-note">a lu l’étape A</span></h4><ol class="avis">{"".join(_membre(a) for a in b_avis)}</ol>'
    corps += f'<p class="etape etape-c">Étape C · le Président a lu les avis et tranche ci-dessous.{_president(d)}</p>'
    fiche = [x for x in (f"conseillers {c['modele_membres']}" if c.get("modele_membres") else "", f"consignes {c['consignes']}" if c.get("consignes") else "") if x]
    if fiche:
        ligne_fiche = " · ".join(fiche)
        ligne_fiche = ligne_fiche[:1].upper() + ligne_fiche[1:]
        corps += f'<p class="muted fiche-conseil">{e(ligne_fiche)}</p>'
    return f'<details class="deliberation"><summary>{resume}</summary>{corps}</details>'


def _meta(d: dict[str, Any]) -> str:
    meta = []
    if d.get("cout_uusd"):
        meta.append(usd(d["cout_uusd"]))
        c = d.get("conseil") or {}
        if c.get("cout_president_uusd") and c.get("president") not in (None, "Haiku"):  # un Président plus cher pèse l'essentiel
            meta[-1] += f" dont Président {usd(c['cout_president_uusd'])}"
    return f'<span class="decision-meta">{" · ".join(meta)}</span>' if meta else ""


def _detail_libelle(d: dict[str, Any]) -> str:
    """Ce que cache le pli : « Raisonnement du président, 10 avis, ordres et exécution »."""
    mots = []
    c = d.get("conseil") or {}
    if d.get("justification"):
        mots.append("raisonnement du président" if c else "raisonnement complet")
    if c.get("avis"):
        mots.append(pluriel(len(c["avis"]), "avis", "avis"))
    if d.get("actions"):
        mots.append("ordres et exécution")
    elif (d.get("pose") or {}).get("elements"):
        mots.append("ordres préparés et alertes")
    return _maj_txt(", ".join(mots)) if mots else "Le détail"


def _maj_txt(s: str) -> str:
    return s[:1].upper() + s[1:]


def _signe_pct(v: float) -> str:
    return f"{'+' if v > 0 else (MINUS if v < 0 else '')}{abs(round(v)):.0f}{NBSP}%"


def _moteur_ligne(d: dict[str, Any]) -> str:
    """La ligne d'une ronde du Conseil Tendance : les cibles du moteur, les coefficients du conseil avec leur raison,
    les ordres passés. Rien pour les autres portefeuilles."""
    t = d.get("tendance")
    if not t:
        return ""
    cibles = ", ".join(f"{e(i)} {_signe_pct(v)}" for i, v in t["cibles_pct"].items()) or "aucune cible"
    inc = f" · données incomplètes, position gardée : {e(', '.join(t['donnees_incompletes']))}" if t.get("donnees_incompletes") else ""
    lignes = [f'<p class="dec-moteur"><span class="etiquette">Cibles du moteur</span>{cibles}{inc}</p>']
    if t["coefficients"]:
        coefs = " ; ".join(
            f"{e(i)} ×{e(c['coefficient'].replace('.', ','))}" + (f" ({e(c['raison'])})" if c.get("raison") else "")
            for i, c in t["coefficients"].items()
        )
    elif t.get("conseil_absent"):
        coefs = f"le moteur seul ({e(t['conseil_absent'])})"
    elif t["conseil_appele"] and not t["president_ok"]:
        coefs = "le moteur seul (le Président n’a pas rendu de décision)"
    else:
        coefs = "aucun frein : on suit le moteur"
    lignes.append(f'<p class="dec-moteur"><span class="etiquette">Coefficients du conseil</span>{coefs}</p>')
    ordres = []
    for a in d.get("actions") or []:
        if a.get("ecartee") or not a.get("action"):
            continue
        txt = f"{P.ACTIONS.get(a['action'], a['action']).lower()} {e(a['instrument'])}"
        if a.get("taille_pct") is not None:
            txt += f" {pc(a['taille_pct'])}"
        v = a.get("verdict")
        if v is not None and not v.get("approuve"):
            txt += " (refusé)"
        elif a.get("reduite"):
            txt += f" (réduit {a['reduite']} fois pour passer le garde-fou)"
        ordres.append(txt)
    lignes.append(f'<p class="dec-moteur"><span class="etiquette">Ordres</span>{"; ".join(ordres) if ordres else "aucun : tous les écarts sont dans la bande de 5 %"}</p>')
    return "".join(lignes)


def _decision(d: dict[str, Any], *, qui: str = "") -> str:
    """Une décision en carte : ce qui a été décidé et pourquoi, en une ligne chacun ; le détail technique replié."""
    ronde = _pastille_ronde(d)
    tete = f'<p class="dec-tete">{qui}<span class="quand">{quand(d["ts"], annee=False)}</span>{ronde}{_meta(d)}</p>'
    q = L.quoi(d)
    calme = d["statut"] == "decidee" and not d["actions"] and d["kind"] != "ordre"
    classe = "decision carte-dec" + (" calme" if calme else "") + (" ratee" if d["statut"] in ("sautee", "echec") else "")
    corps = f'<p class="dec-quoi">{e(q)}</p>' + _moteur_ligne(d)
    pq = L.pourquoi(d)
    if pq:
        corps += f'<p class="dec-pourquoi"><span class="dec-mot">{e(pq[0])}</span> {e(pq[1])}</p>'
    corps += L.vote_html(d)
    if d["statut"] == "echec" and d.get("erreur"):
        corps += f'<p class="dec-pourquoi muted">{e(d["erreur"])}</p>'
    detail = _deliberation(d) + _justif(d) + (_actions(d) if d["actions"] else "") + _pose(d)
    if detail:
        corps += f'<details class="dec-detail"><summary>{e(_detail_libelle(d))}</summary><div class="decision-pile">{detail}</div></details>'
    return f'<li class="{classe}"><article>{tete}{corps}</article></li>'


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


def _objectif_jour(p: dict[str, Any]) -> str:
    """« objectif : 1 %/jour · réalisé : 0,4 %/jour » : côte à côte et sans fard (Conseil Tendance et son témoin)."""
    o = p.get("objectif_jour")
    if not o:
        return ""
    realise = f"{o['realise_pct']:+.2f}".replace(".", ",").replace("-", MINUS)
    return (
        f'<p class="objectif-jour">objectif : {o["objectif_pct"]}{NBSP}%/jour · réalisé : {realise}{NBSP}%/jour '
        f'<span class="muted">(taux journalier composé depuis l’ouverture, {str(o["jours"]).replace(".", ",")} jours)</span></p>'
    )


def portfolio_page(data: dict[str, Any], p: dict[str, Any]) -> str:
    conseil = p["kind"] == "conseil"
    ligue_c = conseil or p["id"] == P.MOTEUR  # le témoin « moteur seul » vit dans la ligue des conseils
    _RESUME_SEUL.clear()
    avec_avis = [d for d in p.get("decisions") or [] if (d.get("conseil") or {}).get("avis")]
    _RESUME_SEUL.update(id(d) for d in avec_avis[AVIS_DETAILLES:])
    llm = p["kind"] == "llm" or conseil  # le conseil décide comme une IA : décisions, attente, coût
    stats = [
        _stat("Rendement net", f'<span class="{tone(p["rendement"])}"{_crochet(p, "rend")}>{pct(p["rendement"])}</span>', cls="grand", carte="cle"),
        _stat(
            "Valeur", f'<span{_crochet(p, "val")}>{eur(p["equity_ueur"])}</span>',
            f'<small class="sous">départ {eur(p["capital_ueur"], decimals=0)}{f" · objectif {eur(2 * p['capital_ueur'], decimals=0)}" if conseil and p["id"] != P.CONSEIL_TENDANCE else ""}</small>',
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
        if conseil:
            gros = p.get("president") not in (None, "Haiku") and p.get("cout_president_uusd")
            sous = "coût réel des rondes" + (f" · dont Président {usd(p['cout_president_uusd'])}" if gros else "")
        else:
            sous = "équivalent API"
        stats.append(_stat("Coût IA", usd(p["cout_uusd"]), f'<small class="sous">{sous}</small>'))
        q = (p.get("rythme") or {}).get("quota")
        jour = f'<small class="sous">{q["played_today"]} appels aujourd’hui, {q["per_day"]} au plus</small>' if q else ""
        stats.append(_stat("Décisions", str(p["n_rondes"]), f'<small class="sous">{pluriel(p["n_ordres"], "ordre exécuté", "ordres exécutés")}</small>{jour}'))
    else:
        stats.append(_stat("Positions", str(len(p["positions"])), '<small class="sous">ouvertes</small>'))
        stats.append(_stat("Opérations", str(p["n_operations"])))
    alertes = ""
    st = p.get("statut")
    if p.get("archive"):
        solo = p["kind"] == "llm"
        alertes = (
            f'<p class="alerte info"><strong>{"IA archivée" if solo else "Conseil archivé"}</strong> le {quand(p["archive"]["ts"])}. '
            f"Ses positions ont été fermées au marché ; {'elle' if solo else 'il'} ne joue plus et ses chiffres sont figés. "
            f"Sa courbe reste, en pointillés, dans la ligue {'des IA seules' if solo else 'des conseils'}.</p>"
        )
    elif st and st["etat"] == "arrete" and conseil:
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
    perp = data["perp"]["conseils"] if ligue_c else data["perp"]  # la ligue du portefeuille
    chart = _ref_chart(perp, p["id"])
    direct_pfs = [p] if _direct_pf(p) else []
    # Le panier, seule autre courbe de la page, suit lui aussi le prix du moment (il n'a pas de chiffre ici).
    panier = next((x for x in perp["portfolios"] if x["id"] == P.PANIER and x is not p), None)
    if direct_pfs and courbe_visible(chart) and panier and _direct_pf(panier):
        direct_pfs.append(panier)
    direct_etat = '<p class="direct-etat" data-direct-etat hidden></p>' if direct_pfs else ""
    decs = _decisions_groupees(p["decisions"])
    if llm or p["id"] == P.ALEATOIRE:
        vide = "Pas encore de décision : la première arrive au prochain rendez-vous." if llm else "Aucun tirage pour l’instant."
        decs_html = f'<ol class="decisions">{decs}</ol>' if decs else f'<p class="vide">{vide}</p>'
        decisions = f'<section{" class=\"teinte-2\"" if conseil and p["id"].endswith(":opus") else ""} aria-labelledby="titre-decisions"><h2 id="titre-decisions">Décisions <span class="h-note">du plus récent au plus ancien</span></h2>{decs_html}</section>'
        operations = (
            f'<section aria-labelledby="titre-operations"><details class="lecture"><summary><h2 id="titre-operations" class="h2-inline">Opérations</h2>'
            f' <span class="h-note">{pluriel(p["n_operations"], "opération")}</span></summary>{_operations(p)}</details></section>'
        )
    else:
        decisions = ""
        operations = f'<section aria-labelledby="titre-operations"><h2 id="titre-operations">Opérations</h2>{_operations(p)}</section>'
    if ligue_c:
        fil = '<a href="../conseils.html"><span aria-hidden="true">← </span>Ligue des conseils</a>'
    else:
        fil = f'<a href="../derives.html"><span aria-hidden="true">← </span>Ligue dérivés</a><span class="fil-sep" aria-hidden="true">/</span><span>{"Modèles d’IA" if llm else "Témoins"}</span>'
    body = f"""
<p class="fil">{fil}</p>
<header class="tete-modele{" teinte-2" if conseil and p["id"].endswith(":opus") else ""}">
  <h1>{e(p["name"])}</h1>
  {f'<p class="sous-titre">{e(p["sous_titre"])}</p>' if p.get("sous_titre") else ""}
  {f'<p class="marque-conseil">{e(p["marque"])}</p>' if p.get("marque") else ""}
  {f'<p class="chapo">{e(p["description"])}</p>' if p.get("description") else ""}
  {_objectif_jour(p)}
  {f'<p class="hors-regle">{e(p["hors_regle"])} <a href="../conseils.html#m-conseils">Ses règles</a></p>' if p.get("hors_regle") else ""}
</header>
{alertes}
<dl class="stats">{"".join(stats)}</dl>
<section aria-labelledby="titre-courbe"><h2 id="titre-courbe">Rendement net <span class="h-note">frais et funding compris</span></h2>{_chart_block(chart, focus=p["id"], focus_name=p["name"])}</section>
<section aria-labelledby="titre-positions"><h2 id="titre-positions">Positions <span class="h-note">fictives, prix en dollars</span></h2>{direct_etat}{_positions(p)}</section>
{decisions}
{_attente(p) if llm and not p.get("archive") else ""}
{operations}
"""
    return layout(
        title=f"{p['name']} · {'conseils' if ligue_c else 'dérivés'}", body=body, root="../", active=p["id"], data=data,
        ligue="conseils" if ligue_c else "perp", chemin=f"{_dossier(p)}/{p['slug']}.html",
        image="apercu-conseils.png" if ligue_c else "apercu.png",
        desc=_desc_pf(p),
        scripts=(_chart_scripts("../", chart, p["id"], dernier="Dernier relevé") if courbe_visible(chart) else "") + _direct_scripts("../", perp, direct_pfs),
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
    pointeur_conseils = (
        '<p>Les conseils, plusieurs IA qui délibèrent avant qu’un Président décide, ont leur propre ligue, sur le même journal, les mêmes marchés et la même veille : '
        '<a href="conseils.html#m-conseils">leurs règles</a>.</p>\n'
        if perp.get("conseils") else ""
    )
    temoins = "".join(
        f'<div><dt>{e(P.NOMS[k].removeprefix("Témoin "))}</dt><dd>{e(v)}</dd></div>' for k, v in P.DESCRIPTIONS.items() if not k.startswith(P.PREFIXE_CONSEIL)
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
<h3>Les témoins</h3>
<dl class="regles">{temoins}</dl>
<h3 id="m-actualites">Actualités</h3>
<p>Les IA ne voient que des actualités officielles et structurées : la page d’état des dérivés de Kraken et l’état de ses contrats, relevés toutes les 5{NBSP}min, et le calendrier macro américain publié d’avance. Jamais d’articles ni de réseaux sociaux, et jamais les chiffres publiés : seule la réaction du marché leur parvient. Une nouvelle annonce de Kraken, ou une publication FOMC, CPI, emploi (NFP) ou PCE vieille de 3{NBSP}min, rappelle les IA.</p>
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
{pointeur_conseils}<p><span class="pastille {"ok" if ok else "perte-bg"}">Journal de la ligue : {"chaîne intacte" if ok else "ÉCHEC"}</span> {pluriel(j["n_records"], "événement")}.</p>
</section>
"""


def _methode_tendance(budget: str) -> str:
    """Les règles du Conseil Tendance (docs/SPEC-CONSEIL-V4.md et docs/CONSEIL-V4-RECHERCHE.md)."""
    return f"""<section aria-labelledby="m-conseils"><h2 id="m-conseils">Le Conseil Tendance : méthode</h2>
<p>La demande du 17/11/2026 était un conseil qui génère du revenu net « de l’ordre de 10{NBSP}% par jour ». Dix pour cent par jour, composés, font ×17 en un mois : aucune stratégie connue ne tient ce rythme. La page affiche donc l’objectif et le rendement par jour réalisé, côte à côte.</p>
<p>Les anciens conseils (Haiku et Opus) perdaient : avis sans avantage, tailles énormes, une nouvelle décision toutes les 10 minutes. Le Conseil Tendance inverse les rôles : <strong>un moteur décide, les IA ne peuvent que freiner, le code exécute.</strong> {e(P.HORS_REGLE_CONSEIL)}</p>
<ul class="liste-simple">
<li><strong>Le moteur</strong> : un suivi de tendance lent (moyennes mobiles de 2 et 6 jours sur des barres de 4 heures, long et short, taille réglée sur la volatilité, échelle 2x), choisi sur 146 essais de quatre familles de stratégies et gelé avant la lecture du contrôle. Sur 31 jours de contrôle en baisse franche il a fait +21{NBSP}% (reculs jusqu’à −25{NBSP}%) ; en marché sans tendance il tourne autour de zéro. Une seule stratégie, un seul épisode de chaque type : l’avantage est plausible, il n’est pas prouvé.</li>
<li><strong>Les IA</strong> : trois Haiku (actualités, données, risque) conseillent, un Président Opus fixe pour chaque contrat un coefficient de 1, 0,5 ou 0 qui multiplie la cible du moteur. Ils ne peuvent ni augmenter, ni inverser, ni ouvrir une position que le moteur n’a pas. Le Président échoue ou dépasse son délai : le moteur joue seul.</li>
<li><strong>Le rythme</strong> : une ronde à chaque clôture de barre de 4 heures (00:00, 04:00… UTC), plus une ronde de veto sur une annonce de Kraken, une publication macro ou un mouvement de 2{NBSP}% en une heure, qui ne peut que baisser les coefficients. Ni appel toutes les 10 minutes, ni rappel demandé par une IA.</li>
<li><strong>L’exécution</strong> : un ordre seulement si l’écart entre la cible et la position dépasse 5{NBSP}% du portefeuille ; un stop à 5{NBSP}% sur chaque position. Si le garde-fou refuse un ordre pour sa taille, le code le retente plus petit.</li>
<li><strong>Le témoin « moteur seul »</strong> joue la même cible, sans IA, par le même chemin et sur les mêmes rondes : l’écart avec le Conseil Tendance mesure ce que les IA ajoutent ou retirent.</li>
</ul>
<dl class="regles">
<div><dt>Levier</dt><dd>10 au plus, avec les marges de Kraken ; l’échelle du moteur donne environ 1,4 en moyenne, avec des pointes vers 4 à 6. Un ordre jusqu’à 400{NBSP}% de la valeur du portefeuille.</dd></div>
<div><dt>Stop</dt><dd>5{NBSP}% sur chaque position ; perte au stop de 25{NBSP}% du portefeuille au plus par position, 59{NBSP}% pour tous les stops réunis.</dd></div>
<div><dt>Coût</dt><dd>Le coût d’un aller-retour ne dépasse pas un tiers du mouvement attendu. Celui du moteur est mesuré hors ligne (+2,47{NBSP}% brut par trade sur les 64 jours d’entraînement), pas déclaré.</dd></div>
<div><dt>Rythme</dt><dd>48 ouvertures ou ajustements par 24{NBSP}h au plus, sans délai entre deux ; ni gel quotidien, ni budget de frais (les frais restent réels et comptés).</dd></div>
<div><dt>Arrêt</dt><dd>À −60{NBSP}% depuis son plus haut : positions fermées, plus aucune ronde. Seul l’opérateur de l’arène peut le relancer, à la main.</dd></div>
{budget}</dl>
<p class="muted">Marchés, veille et journal sont ceux de la <a href="derives.html">ligue des IA seules</a>.</p>
</section>
"""


def methode_conseils(data: dict[str, Any]) -> str:
    """Les règles de la ligue des conseils (section de sa page d'accueil)."""
    perp = data["perp"]["conseils"]
    conseils = [p for p in perp["portfolios"] if p["kind"] == "conseil"]
    membres = "".join(
        f"<li><strong>{e(n)}</strong> (étape {etape}) : {e(role)}. <span class=\"muted\">Sources : {e(src)}.</span></li>"
        for n, etape, role, src in P.MEMBRES.values()
    )
    budgets = " ; ".join(
        f"{e(c['name'])} {P.BUDGETS_CONSEIL_USD[c['id']]}{NBSP}$ par jour" for c in conseils if c["id"] in P.BUDGETS_CONSEIL_USD
    )
    budget = (
        f"<div><dt>Budget du jour</dt><dd>{budgets}, en équivalent catalogue. Une ronde qui ne tient plus dans le budget est sautée.</dd></div>\n"
        if budgets else ""
    )
    if any(c["id"] == P.CONSEIL_TENDANCE for c in conseils):
        return _methode_tendance(budget)
    return f"""<section aria-labelledby="m-conseils"><h2 id="m-conseils">Les conseils : méthode</h2>
<p>Un conseil est un portefeuille décidé par dix Claude Haiku 5.5 qui délibèrent à chaque ronde, puis par un Président, avec un mandat agressif : doubler la mise en quelques jours. Les conseils jouent les mêmes rondes que les IA des dérivés (rendez-vous, appel régulier, réveils, alertes, rappels) ; une ronde compte pour un appel dans le plafond du jour, et son coût est la somme des appels de la ronde.</p>
<p>Les conseils ne diffèrent que par leur Président : Haiku pour le Conseil Haiku, Opus pour le Conseil Opus. <strong>{e(P.HORS_REGLE_CONSEIL)}</strong> Ils ne sont donc jamais classés avec les IA des dérivés, qui jouent toutes avec les mêmes règles.</p>
<ul class="liste-simple">
<li><strong>Étape A</strong> : les conseillers donnent chacun un avis sans voir les autres (long, short ou plat par contrat, conviction de 0 à 100, taille, stop, niveau clé, argument). Les rondes d’avant l’arrivée de l’Arbitragiste de paires comptent un avis de moins.</li>
<li><strong>Étape B</strong> : l’Avocat du diable lit ces avis et attaque le trade le plus soutenu.</li>
<li><strong>Étape C</strong> : le Président lit tous les avis et décide, au même format que les IA. Un conseiller en échec est laissé de côté ; sans Président, la ronde ne fait rien.</li>
</ul>
<details class="lecture"><summary>Les membres et leurs sources</summary><ul class="liste-simple">{membres}</ul>
<p class="muted">Sources : TradingAgents (TauricResearch), claude-trading-skills (tradermonty) et HyperGrok (galleonlabs), trois dépôts publics.</p></details>
<dl class="regles">
<div><dt>Levier</dt><dd>10 au plus, avec les marges de Kraken (1 à 2{NBSP}% du montant pour ouvrir) ; une entrée jusqu’à 500{NBSP}% de la valeur du portefeuille, une position jusqu’à 1{NNBSP}000{NBSP}%.</dd></div>
<div><dt>Stop</dt><dd>Obligatoire, entre 1 et 15{NBSP}%, et toujours avant la liquidation ; perte au stop de 25{NBSP}% du portefeuille au plus par trade, 60{NBSP}% pour tous les stops réunis.</dd></div>
<div><dt>Rythme</dt><dd>24 ouvertures par 24{NBSP}h au plus, sans délai entre deux ; ni gel quotidien, ni budget de frais (les frais restent réels et comptés).</dd></div>
<div><dt>Arrêt</dt><dd>À −90{NBSP}% depuis son plus haut (la ruine) : positions fermées, plus aucune ronde. Seul l’opérateur de l’arène peut le relancer, à la main.</dd></div>
<div><dt>Liquidation</dt><dd>Simulée comme chez Kraken : quand la valeur tombe sous la marge de maintenance (la moitié de la marge d’ouverture), testée chaque minute au pire prix, avec 5{NBSP}% de frais de liquidation ; puis 1{NBSP}h sans entrée.</dd></div>
{budget}</dl>
<p class="muted">La politique est la même pour les deux conseils. Marchés, veille, journal et témoin de référence sont ceux de la <a href="derives.html">ligue des IA seules</a>.</p>
</section>
"""
