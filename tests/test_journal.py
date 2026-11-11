"""Tests du journal chaîné (docs/SPEC-MVP.md §4)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from arene.journal import (
    GENESIS_HASH,
    FloatInPayloadError,
    Journal,
    JournalCorruptError,
    JournalError,
    bar_from_payload,
    canonical,
    fill_from_payload,
    intent_from_payload,
    quote_from_payload,
    record_hash,
    to_payload,
    verdict_from_payload,
    verify,
)
from arene.types import Bar, Fill, Intent, Quote, Side, Verdict

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def jr(tmp_path):
    return Journal(tmp_path / "var" / "journal" / "events.jsonl")


def fill_journal(jr: Journal, n: int = 5) -> None:
    for i in range(n):
        jr.append("alert", {"level": "info", "code": f"c{i}", "message": "é"}, 1_700_000_000 + i)


def rewrite_line(path: Path, idx: int, fn) -> None:
    lines = path.read_bytes().split(b"\n")
    lines[idx] = fn(lines[idx])
    path.write_bytes(b"\n".join(lines))


def test_canonical_est_stable():
    assert canonical({"b": 1, "a": [True, None, "é"]}) == '{"a":[true,null,"é"],"b":1}'.encode()


def test_append_chaine_et_lecture(jr):
    r0 = jr.append("config_loaded", {"policy_sha256": "x"}, 10)
    r1 = jr.append("cycle_started", {"cycle": 1}, 11)
    assert (r0["seq"], r0["prev_hash"]) == (0, GENESIS_HASH)
    assert (r1["seq"], r1["prev_hash"]) == (1, r0["hash"])
    assert r1["hash"] == record_hash(r1)
    assert jr.events() == [r0, r1]
    assert list(jr.iter_events()) == [r0, r1]
    assert jr.last() == r1
    rep = jr.verify()
    assert rep.ok and rep.n_records == 2 and rep.head_hash == r1["hash"] and rep.head_seq == 1


def test_journal_vide(jr):
    assert jr.last() is None
    assert list(jr.iter_events()) == []
    rep = jr.verify()
    assert rep.ok and rep.n_records == 0 and rep.head_hash == GENESIS_HASH


def test_reouverture_continue_la_chaine(jr):
    fill_journal(jr, 3)
    r = Journal(jr.path).append("alert", {"level": "info"}, 99)
    assert r["seq"] == 3
    assert verify(jr.path).ok


@pytest.mark.parametrize(
    "payload",
    [{"x": 1.5}, {"x": {"y": [1, 2.0]}}, {"x": 1e3}, {"a": [{"b": float("nan")}]}],
)
def test_float_refuse(jr, payload):
    with pytest.raises(FloatInPayloadError):
        jr.append("alert", payload, 1)
    assert not jr.path.exists() or jr.path.read_bytes() == b""


def test_ts_float_refuse(jr):
    with pytest.raises(FloatInPayloadError):
        jr.append("alert", {}, 1.5)  # type: ignore[arg-type]
    with pytest.raises(JournalError):
        jr.append("alert", {}, True)  # type: ignore[arg-type]


def test_bool_none_et_gros_entiers_acceptes(jr):
    r = jr.append("alert", {"a": True, "b": None, "c": 10**18, "d": [1, "x"]}, 1)
    assert jr.last() == r


def test_verify_hash_modifie_a_la_bonne_seq(jr):
    fill_journal(jr, 5)
    rewrite_line(jr.path, 2, lambda b: b.replace(b'"c2"', b'"cX"'))
    rep = verify(jr.path)
    assert not rep.ok
    assert [(e.code, e.seq, e.line) for e in rep.errors] == [("hash_mismatch", 2, 3)]


def test_verify_ligne_modifiee_puis_rehachee_casse_la_suivante(jr):
    fill_journal(jr, 5)

    def forge(b: bytes) -> bytes:
        rec = json.loads(b)
        rec["payload"]["code"] = "forge"
        rec["hash"] = record_hash(rec)
        return canonical(rec)

    rewrite_line(jr.path, 1, forge)
    rep = verify(jr.path)
    assert [(e.code, e.seq) for e in rep.errors] == [("prev_hash_mismatch", 2)]


def test_verify_seq_manquant(jr):
    fill_journal(jr, 5)
    lines = jr.path.read_bytes().split(b"\n")
    del lines[2]  # supprime seq 2
    jr.path.write_bytes(b"\n".join(lines))
    rep = verify(jr.path)
    codes = {e.code for e in rep.errors}
    assert "seq_gap" in codes
    gap = next(e for e in rep.errors if e.code == "seq_gap")
    assert gap.seq == 3 and gap.line == 3


def test_verify_float_present_dans_le_fichier(jr):
    fill_journal(jr, 2)
    # ligne forgée avec un hash correct mais un float dans le payload
    last = jr.last()
    rec = {"seq": 2, "ts": 5, "type": "alert", "payload": {"x": 1.5}, "prev_hash": last["hash"]}
    rec["hash"] = record_hash(rec)
    with open(jr.path, "ab") as f:
        f.write(canonical(rec) + b"\n")
    rep = verify(jr.path)
    assert [(e.code, e.seq) for e in rep.errors] == [("float_present", 2)]


def test_verify_float_entier_ecrit_1_0(jr):
    fill_journal(jr, 1)
    last = jr.last()
    rec = {"seq": 1, "ts": 5, "type": "alert", "payload": {"x": 1}, "prev_hash": last["hash"]}
    rec["hash"] = record_hash(rec)
    line = canonical(rec).replace(b'"x":1', b'"x":1.0')
    with open(jr.path, "ab") as f:
        f.write(line + b"\n")
    assert "float_present" in verify(jr.path).codes()


def test_verify_ligne_tronquee_en_fin(jr):
    fill_journal(jr, 3)
    data = jr.path.read_bytes()
    jr.path.write_bytes(data[:-20])
    rep = verify(jr.path)
    assert rep.codes() == ["truncated_tail"]
    assert rep.n_records == 2 and rep.head_seq == 1
    assert rep.errors[0].line == 3 and rep.errors[0].seq == 2


def test_ligne_tronquee_sans_json_invalide_apres_accolade(jr):
    # coupure juste avant le "\n" : le JSON est complet mais la fin de ligne manque
    fill_journal(jr, 2)
    jr.path.write_bytes(jr.path.read_bytes()[:-1])
    assert verify(jr.path).codes() == ["truncated_tail"]


def test_append_refuse_sur_ligne_tronquee_et_ne_repare_pas(jr):
    fill_journal(jr, 3)
    data = jr.path.read_bytes()[:-20]
    jr.path.write_bytes(data)
    with pytest.raises(JournalCorruptError):
        jr.append("alert", {"level": "info"}, 9)
    assert jr.path.read_bytes() == data  # jamais réparé en silence
    with pytest.raises(JournalCorruptError):
        jr.last()
    with pytest.raises(JournalCorruptError):
        list(jr.iter_events())
    assert len(list(jr.iter_events(strict=False))) == 2


def test_append_refuse_sur_derniere_ligne_au_hash_invalide(jr):
    fill_journal(jr, 2)
    rewrite_line(jr.path, 1, lambda b: b.replace(b'"c1"', b'"zz"'))
    with pytest.raises(JournalCorruptError):
        jr.append("alert", {}, 9)


def test_verify_json_illisible_et_ligne_vide(jr):
    fill_journal(jr, 3)
    rewrite_line(jr.path, 1, lambda b: b"{pas du json")
    rep = verify(jr.path)
    assert rep.errors[0].code == "bad_json" and rep.errors[0].line == 2
    assert "seq_gap" in rep.codes()


def test_lecture_du_dernier_avec_grosse_ligne(jr):
    jr.append("alert", {"m": "a"}, 1)
    jr.append("decision_received", {"raw_text": "x" * 300_000}, 2)
    assert jr.last()["seq"] == 1
    assert jr.append("alert", {}, 3)["seq"] == 2
    assert jr.verify().ok


def test_serialisation_des_contrats(jr):
    intent = Intent("i1", "llm:a", 100, "BTC/EUR", Side.BUY, 1500, 300, 24, 400, 70)
    verdict = Verdict("i1", False, ("MAX_ORDER_SIZE", "TOO_SOON"), 0, 0, "ab")
    fill = Fill(
        "i1", "llm:a", "BTC/EUR", Side.SELL, 5, 50_000_000_000, 7, 123, "paper", "pessimiste-v1", "stop"
    )
    bar = Bar("BTC/EUR", 14400, 0, 1, 2, 1, 2, 10)
    quote = Quote("BTC/EUR", 5, 99, 101)
    for typ, obj, back in [
        ("intent", intent, intent_from_payload),
        ("risk_verdict", verdict, verdict_from_payload),
        ("fill", fill, fill_from_payload),
        ("bar", bar, bar_from_payload),
        ("quote", quote, quote_from_payload),
    ]:
        rec = jr.append(typ, obj, 1)  # dataclasse acceptée directement
        assert back(rec["payload"]) == obj
    assert jr.events()[0]["payload"]["side"] == "buy"
    assert type(jr.events()[0]["payload"]["side"]) is str
    assert jr.events()[1]["payload"]["reasons"] == ["MAX_ORDER_SIZE", "TOO_SOON"]
    assert to_payload(fill)["side"] == "sell"


def test_champs_ajoutes_au_payload_sont_ignores_en_relecture():
    p = {**to_payload(Quote("BTC/EUR", 5, 99, 101)), "extra": 1}
    assert quote_from_payload(p) == Quote("BTC/EUR", 5, 99, 101)


WORKER = """
import sys
from arene.journal import Journal
j = Journal(sys.argv[1])
for i in range(int(sys.argv[3])):
    j.append("alert", {"worker": sys.argv[2], "i": i}, 1_700_000_000 + i)
"""


def test_concurrence_deux_processus(tmp_path):
    path = tmp_path / "events.jsonl"
    n = 60
    procs = [
        subprocess.Popen([sys.executable, "-c", WORKER, str(path), name, str(n)], cwd=ROOT)
        for name in ("a", "b", "c")
    ]
    assert all(p.wait(timeout=120) == 0 for p in procs)
    evs = Journal(path).events()
    assert [e["seq"] for e in evs] == list(range(3 * n))
    rep = verify(path)
    assert rep.ok and rep.n_records == 3 * n
    for name in ("a", "b", "c"):
        assert [e["payload"]["i"] for e in evs if e["payload"]["worker"] == name] == list(range(n))
