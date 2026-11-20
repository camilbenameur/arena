"""The site in plain language, for a reader who does not know trading.

Each decision reads in one line: what was decided (`what`), and why (`why`). The technical detail
(full reasoning, opinions, orders, guardrail, execution) stays published, collapsed behind it.

Nothing is invented: `what` translates the journaled actions and orders; `why` counts the real opinions of the
advisers (councils) or quotes the first sentence of the model's reasoning (solo AIs), truncated without being rewritten.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from arena.site.render import e, plural

# Common name of each contract's asset.
CRYPTOS: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ether",
    "SOL": "Solana",
    "XRP": "XRP",
    "LINK": "Chainlink",
    "LTC": "litecoin",
}


def crypto(sym: str) -> str:
    return CRYPTOS.get(sym, sym)


def of_crypto(sym: str) -> str:
    """"in bitcoin", "in Solana" (after "a rise" or "a decline")."""
    return f"in {crypto(sym)}"


def on_crypto(sym: str) -> str:
    """"on bitcoin", "on Solana"."""
    return f"on {crypto(sym)}"


def _capitalize(s: str) -> str:
    return s[:1].upper() + s[1:]


def _list(words: list[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def _side_txt(side: str | None) -> str:
    return {"long": "a rise", "short": "a decline"}.get(side or "", "a move")


def _action(a: dict[str, Any]) -> str | None:
    """An action in plain words, in the third person."""
    act, sym = a.get("action"), a.get("instrument") or "?"
    if not act:
        return None
    if act == "open_long":
        txt = f"bets on a rise {of_crypto(sym)}"
    elif act == "open_short":
        txt = f"bets on a decline {of_crypto(sym)}"
    elif act == "close":
        txt = f"closes its bet {on_crypto(sym)}"
    elif act == "reduce":
        txt = f"scales down its bet {on_crypto(sym)}"
    else:
        return None
    v = a.get("verdict")
    if v is not None and not v.get("approved"):
        txt += " (rejected by the guardrail)"
    return txt


def what(d: dict[str, Any]) -> str:
    """What was decided, in one short sentence, without jargon. Plain text (to be escaped)."""
    if d.get("status") == "skipped":
        return "Round skipped" + (f": {d['jump']}" if d.get("jump") else "")
    if d.get("status") == "failure":
        return "No decision this time (call failed)"
    if d.get("status") == "in_progress":
        return "Decision in progress"
    if d.get("kind") == "order":
        a = (d.get("actions") or [{}])[0]
        txt = _action(a) or "order triggered"
        return _capitalize(f"prepared order triggered: {txt}")
    words = [m for m in (_action(a) for a in d.get("actions") or []) if m]
    elements = (d.get("placed") or {}).get("elements") or []
    orders = [x for x in elements if x.get("type") != "alert"]
    alerts = [x for x in elements if x.get("type") == "alert"]
    if orders:
        targets = []
        for x in orders:
            c = f"{_side_txt(x.get('side'))} {of_crypto(x.get('instrument') or '?')}"
            if c not in targets:
                targets.append(c)
        words.append(f"prepares to bet on {_list(targets)}")
    if alerts and not words:
        syms = sorted({x.get("instrument") or "?" for x in alerts})
        words.append(f"watches {_list([crypto(s) for s in syms])}")
    if not words:
        return "Changes nothing"
    return _capitalize(_list(words[:3]) + (" (and more)" if len(words) > 3 else ""))


_BP = re.compile(r"(?<![\w.,])([+\-−]?)(\d+(?:[.,]\d+)?)\s?bp\b")


def _bp_to_pct(m: re.Match[str]) -> str:
    """'-104 bp' becomes '−1.04%': same number, reader's unit (1 bp = 0.01%)."""
    sign = "−" if m.group(1) in ("-", "−") else ("+" if m.group(1) == "+" else "")
    v = float(m.group(2).replace(",", ".")) / 100
    return f"{sign}{v:.2f}%"


def _first_sentence(text: str, n: int = 200) -> str:
    """The first sentence that gives a reason: short statements of state ("I am flat.") are skipped."""
    t = " ".join(text.split())
    sentences = [p for p in re.split(r"(?<=[.!?])\s", t) if p]
    chosen = next((p for p in sentences if len(p.split()) >= 9), sentences[0] if sentences else t)
    chosen = _BP.sub(_bp_to_pct, chosen)
    if len(chosen) <= n:
        return chosen
    return chosen[:n].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _main_instrument(d: dict[str, Any]) -> tuple[str, str] | None:
    """(contract, side) targeted by the decision: its first action, otherwise its first prepared order."""
    for a in d.get("actions") or []:
        if a.get("action") in ("open_long", "open_short"):
            return a["instrument"], "long" if a["action"] == "open_long" else "short"
    for x in (d.get("placed") or {}).get("elements") or []:
        if x.get("type") != "alert" and x.get("side") in ("long", "short"):
            return x["instrument"], x["side"]
    return None


def votes(d: dict[str, Any]) -> dict[str, Any] | None:
    """The opinions of a council's step A, reduced to one side per adviser on the most discussed contract.

    {"instrument", "in_favor": n (same side as the majority), "against": n, "flat": n, "absentees": n, "side": "long"|"short",
     "advocate": {"instrument", "side"} | None, "total": n, "order": [...]}. None without published opinions."""
    if d.get("trend"):  # the trend council's members brake, they do not vote a direction
        return None
    c = d.get("council") or {}
    opinions = [a for a in c.get("opinions") or [] if a.get("step") == "A"]
    if not opinions:
        return None
    targeted = _main_instrument(d)
    instrument_counts: Counter[str] = Counter()
    for a in opinions:
        for x in a.get("opinions") or []:
            if x.get("position") in ("long", "short"):
                instrument_counts[x["instrument"]] += 1
    if targeted:
        inst = targeted[0]
    elif instrument_counts:
        inst = instrument_counts.most_common(1)[0][0]
    else:
        inst = None
    member_sides: list[str] = []
    absentees = 0
    for a in opinions:
        if a.get("absent"):
            absentees += 1
            continue
        pos = (
            next((x["position"] for x in a.get("opinions") or [] if x.get("instrument") == inst), "flat")
            if inst
            else "flat"
        )
        member_sides.append(pos)
    side_counts = Counter(member_sides)
    if targeted:
        side = targeted[1]
    else:
        side = "long" if side_counts["long"] > side_counts["short"] else "short"
    other = "short" if side == "long" else "long"
    advocate = next(
        (a.get("target") for a in c.get("opinions") or [] if a.get("step") != "A" and a.get("target")), None
    )
    return {
        "instrument": inst, "side": side, "in_favor": side_counts[side], "against": side_counts[other], "flat": side_counts["flat"], "absentees": absentees,
        "total": len(opinions), "advocate": advocate, "order": member_sides,
    }  # fmt: skip


def why(d: dict[str, Any]) -> tuple[str, str] | None:
    """(label, reason in one sentence), plain text to escape. Councils: "Why", counted from the opinions.
    Solo AIs: "In its own words", the first sentence of its reasoning in quotation marks. None otherwise."""
    if d.get("status") != "decided":
        return None
    v = votes(d)
    if v and v["instrument"]:
        expressed = v["total"] - v["absentees"]
        direction = "rising" if v["side"] == "long" else "falling"
        txt = f"{v['in_favor']} advisers out of {expressed} see {crypto(v['instrument'])} {direction}"
        if v["in_favor"] == 1:
            txt = f"1 adviser out of {expressed} sees {crypto(v['instrument'])} {direction}"
        if v["against"]:
            txt += f", {v['against']} the opposite"
        advocate_target = v["advocate"]
        if advocate_target:
            txt += f"; the devil's advocate attacks the bet on {_side_txt(advocate_target['side'])} {of_crypto(advocate_target['instrument'])}"
        return "Why", txt
    if d.get("justification"):
        return "In its own words", f"“{_first_sentence(d['justification'])}”"
    return None


def vote_html(d: dict[str, Any]) -> str:
    """One mark per adviser (▲ rise, ▼ decline, ● no view, ○ absent): the shape says the side, not only
    the colour. Decorative; the `why` sentence says the same thing in text."""
    v = votes(d)
    if not v or not v["instrument"]:
        return ""
    badges = {"long": ("▲", "v-rise"), "short": ("▼", "v-decline"), "flat": ("●", "v-flat")}
    order = sorted(v["order"], key=lambda s: {v["side"]: 0, "flat": 1}.get(s, 2))
    spans = "".join(f'<span class="{badges[s][1]}">{badges[s][0]}</span>' for s in order)
    spans += '<span class="v-absent">○</span>' * v["absentees"]
    legend = []
    if v["in_favor"]:
        legend.append(f"{v['in_favor']} {'rise' if v['side'] == 'long' else 'decline'}")
    if v["against"]:
        legend.append(f"{v['against']} {'decline' if v['side'] == 'long' else 'rise'}")
    if v["flat"]:
        legend.append(f"{v['flat']} no view")
    if v["absentees"]:
        legend.append(plural(v["absentees"], "absent", "absent"))
    return (
        f'<p class="vote"><span class="vote-badges" aria-hidden="true">{spans}</span>'
        f'<span class="vote-legend">{e(crypto(v["instrument"]))} : {e(" · ".join(legend))}</span></p>'
    )
