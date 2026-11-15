"""Le site en clair, pour un lecteur qui ne connaît pas le trading.

Chaque décision se lit en une ligne : ce qui a été décidé (`quoi`), et pourquoi (`pourquoi`). Le détail technique
(raisonnement complet, avis, ordres, garde-fou, exécution) reste publié, replié derrière.

Rien n'est inventé : `quoi` traduit les actions et les ordres journalisés ; `pourquoi` compte les avis réels des
conseillers (conseils) ou cite la première phrase du raisonnement du modèle (IA seules), tronquée sans être réécrite.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from arene.site.render import NBSP, e, pluriel

# Nom courant de chaque contrat, et sa forme après « de » (« la baisse du bitcoin »).
CRYPTOS: dict[str, tuple[str, str]] = {
    "BTC": ("le bitcoin", "du bitcoin"),
    "ETH": ("l’ether", "de l’ether"),
    "SOL": ("Solana", "de Solana"),
    "XRP": ("XRP", "de XRP"),
    "LINK": ("Chainlink", "de Chainlink"),
    "LTC": ("le litecoin", "du litecoin"),
}


def crypto(sym: str) -> str:
    return CRYPTOS.get(sym, (sym, f"de {sym}"))[0]


def de_crypto(sym: str) -> str:
    return CRYPTOS.get(sym, (sym, f"de {sym}"))[1]


def sur_crypto(sym: str) -> str:
    """« sur le bitcoin », « sur Solana »."""
    return f"sur {crypto(sym)}"


def _maj(s: str) -> str:
    return s[:1].upper() + s[1:]


def _liste(mots: list[str]) -> str:
    if len(mots) <= 1:
        return "".join(mots)
    return ", ".join(mots[:-1]) + " et " + mots[-1]


def _sens_txt(sens: str | None) -> str:
    return {"long": "la hausse", "short": "la baisse"}.get(sens or "", "un mouvement")


def _action(a: dict[str, Any]) -> str | None:
    """Une action en clair, à l'infinitif conjugué (3e personne)."""
    act, sym = a.get("action"), a.get("instrument") or "?"
    if not act:
        return None
    if act == "open_long":
        txt = f"parie sur la hausse {de_crypto(sym)}"
    elif act == "open_short":
        txt = f"parie sur la baisse {de_crypto(sym)}"
    elif act == "close":
        txt = f"ferme son pari {sur_crypto(sym)}"
    elif act == "reduce":
        txt = f"allège son pari {sur_crypto(sym)}"
    else:
        return None
    v = a.get("verdict")
    if v is not None and not v.get("approuve"):
        txt += " (refusé par le garde-fou)"
    return txt


def quoi(d: dict[str, Any]) -> str:
    """Ce qui a été décidé, en une phrase courte, sans jargon. Texte brut (à échapper)."""
    if d.get("statut") == "sautee":
        return "Ronde sautée" + (f" : {d['saut']}" if d.get("saut") else "")
    if d.get("statut") == "echec":
        return "Pas de décision cette fois (appel en échec)"
    if d.get("statut") == "en_cours":
        return "Décision en cours"
    if d.get("kind") == "ordre":
        a = (d.get("actions") or [{}])[0]
        txt = _action(a) or "ordre déclenché"
        return _maj(f"ordre préparé déclenché : {txt}")
    mots = [m for m in (_action(a) for a in d.get("actions") or []) if m]
    els = (d.get("pose") or {}).get("elements") or []
    ordres = [x for x in els if x.get("type") != "alerte"]
    alertes = [x for x in els if x.get("type") == "alerte"]
    if ordres:
        cibles = []
        for x in ordres:
            c = f"{_sens_txt(x.get('sens'))} {de_crypto(x.get('instrument') or '?')}"
            if c not in cibles:
                cibles.append(c)
        mots.append(f"se prépare à parier sur {_liste(cibles)}")
    if alertes and not mots:
        syms = sorted({x.get("instrument") or "?" for x in alertes})
        mots.append(f"surveille {_liste([crypto(s) for s in syms])}")
    if not mots:
        return "Ne change rien"
    return _maj(_liste(mots[:3]) + (" (et plus)" if len(mots) > 3 else ""))


_BP = re.compile(r"(?<![\w.,])([+\-−]?)(\d+(?:[.,]\d+)?)\s?bp\b")


def _bp_en_pct(m: re.Match[str]) -> str:
    """« -104 bp » devient « −1,04 % » : même nombre, unité du lecteur (1 bp = 0,01 %)."""
    signe = "−" if m.group(1) in ("-", "−") else ("+" if m.group(1) == "+" else "")
    v = float(m.group(2).replace(",", ".")) / 100
    return f"{signe}{v:.2f}".replace(".", ",") + NBSP + "%"


def _premiere_phrase(texte: str, n: int = 200) -> str:
    """La première phrase qui donne une raison : on saute les constats d'état courts (« Je suis à plat. »)."""
    t = " ".join(texte.split())
    phrases = [p for p in re.split(r"(?<=[.!?])\s", t) if p]
    choisie = next((p for p in phrases if len(p.split()) >= 9), phrases[0] if phrases else t)
    choisie = _BP.sub(_bp_en_pct, choisie)
    if len(choisie) <= n:
        return choisie
    return choisie[:n].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _instrument_principal(d: dict[str, Any]) -> tuple[str, str] | None:
    """(contrat, sens) visé par la décision : sa première action, sinon son premier ordre préparé."""
    for a in d.get("actions") or []:
        if a.get("action") in ("open_long", "open_short"):
            return a["instrument"], "long" if a["action"] == "open_long" else "short"
    for x in (d.get("pose") or {}).get("elements") or []:
        if x.get("type") != "alerte" and x.get("sens") in ("long", "short"):
            return x["instrument"], x["sens"]
    return None


def votes(d: dict[str, Any]) -> dict[str, Any] | None:
    """Les avis de l'étape A d'un conseil, réduits à un sens par conseiller sur le contrat le plus discuté.

    {"instrument", "pour": n (même sens que la majorité), "contre": n, "plat": n, "absents": n, "sens": "long"|"short",
     "avocat": {"instrument", "sens"} | None, "total": n}. None sans avis publiés."""
    c = d.get("conseil") or {}
    avis = [a for a in c.get("avis") or [] if a.get("etape") == "A"]
    if not avis:
        return None
    vise = _instrument_principal(d)
    compte: Counter[str] = Counter()
    for a in avis:
        for x in a.get("avis") or []:
            if x.get("position") in ("long", "short"):
                compte[x["instrument"]] += 1
    if vise:
        inst = vise[0]
    elif compte:
        inst = compte.most_common(1)[0][0]
    else:
        inst = None
    sens_membre: list[str] = []
    absents = 0
    for a in avis:
        if a.get("absent"):
            absents += 1
            continue
        pos = (
            next((x["position"] for x in a.get("avis") or [] if x.get("instrument") == inst), "plat")
            if inst
            else "plat"
        )
        sens_membre.append(pos)
    n = Counter(sens_membre)
    if vise:
        sens = vise[1]
    else:
        sens = "long" if n["long"] > n["short"] else "short"
    autre = "short" if sens == "long" else "long"
    avocat = next(
        (a.get("cible") for a in c.get("avis") or [] if a.get("etape") != "A" and a.get("cible")), None
    )
    return {
        "instrument": inst, "sens": sens, "pour": n[sens], "contre": n[autre], "plat": n["plat"], "absents": absents,
        "total": len(avis), "avocat": avocat, "ordre": sens_membre,
    }  # fmt: skip


def pourquoi(d: dict[str, Any]) -> tuple[str, str] | None:
    """(étiquette, raison en une phrase), texte brut à échapper. Les conseils : « Pourquoi », compté sur les avis.
    Les IA seules : « En ses mots », la première phrase de son raisonnement entre guillemets. None sinon."""
    if d.get("statut") != "decidee":
        return None
    v = votes(d)
    if v and v["instrument"]:
        exprimes = v["total"] - v["absents"]
        dire = "monter" if v["sens"] == "long" else "baisser"
        txt = f"{v['pour']} conseillers sur {exprimes} voient {crypto(v['instrument'])} {dire}"
        if v["pour"] == 1:
            txt = f"1 conseiller sur {exprimes} voit {crypto(v['instrument'])} {dire}"
        if v["contre"]:
            txt += f", {v['contre']} l’inverse"
        av = v["avocat"]
        if av:
            txt += f" ; l’avocat du diable attaque le pari sur {_sens_txt(av['sens'])} {de_crypto(av['instrument'])}"
        return "Pourquoi", txt
    if d.get("justification"):
        return "En ses mots", f"« {_premiere_phrase(d['justification'])} »"
    return None


def vote_html(d: dict[str, Any]) -> str:
    """Une marque par conseiller (▲ hausse, ▼ baisse, ● sans avis, ○ absent) : la forme dit le sens, pas seulement
    la couleur. Décoratif ; la phrase `pourquoi` dit la même chose en texte."""
    v = votes(d)
    if not v or not v["instrument"]:
        return ""
    marques = {"long": ("▲", "v-hausse"), "short": ("▼", "v-baisse"), "plat": ("●", "v-plat")}
    ordre = sorted(v["ordre"], key=lambda s: {v["sens"]: 0, "plat": 1}.get(s, 2))
    spans = "".join(f'<span class="{marques[s][1]}">{marques[s][0]}</span>' for s in ordre)
    spans += '<span class="v-absent">○</span>' * v["absents"]
    legende = []
    if v["pour"]:
        legende.append(f"{v['pour']}{NBSP}{'hausse' if v['sens'] == 'long' else 'baisse'}")
    if v["contre"]:
        legende.append(f"{v['contre']}{NBSP}{'baisse' if v['sens'] == 'long' else 'hausse'}")
    if v["plat"]:
        legende.append(f"{v['plat']}{NBSP}sans avis")
    if v["absents"]:
        legende.append(pluriel(v["absents"], "absent", "absents").replace(" ", NBSP))
    return (
        f'<p class="vote"><span class="vote-marques" aria-hidden="true">{spans}</span>'
        f'<span class="vote-legende">{e(crypto(v["instrument"]))} : {e(" · ".join(legende))}</span></p>'
    )
