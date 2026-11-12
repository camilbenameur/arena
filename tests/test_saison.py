"""Saison gelée (config [saison], événements saison_*, gel, dérogation, statut) : vrai journal, marché factice."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from arene import cli, saison
from arene import cycle as cyc
from arene import veille as vei
from arene.config import ConfigError, load_config, sha256_hors_saison
from arene.deciders.llm import prompt_sha256
from arene.journal import Journal, verify
from arene.ledger import equity_ueur, replay
from arene.paths import REPO
from arene.risk.policy import load_policy
from tests.fakes import H4, T0, Env
from tests.test_veille import X, cycle, deciders, make_env, prepare, tick

DAY = 86_400


def of(env: Env, *types: str) -> list[dict]:
    return env.of_type(*types)


def pl(env: Env, t: str) -> list[dict]:
    return [e["payload"] for e in env.of_type(t)]


def codes(env: Env) -> list[tuple[str, str]]:
    return [(a["level"], a["code"]) for a in pl(env, "alert")]


def saison_env(tmp_path: Path, name: str = "e", *, debut: int = T0 + 300, jours: int = 1) -> Env:
    env = make_env(tmp_path, name)
    set_saison(env, debut_ts=debut, duree_jours=jours)
    return env


def set_saison(env: Env, **kw: int | str) -> None:
    txt = env.paths.config.read_text()
    for k, v in kw.items():
        new = f'{k} = "{v}"' if isinstance(v, str) else f"{k} = {v}"
        txt, n = re.subn(rf"^{k} = .*$", new, txt, count=1, flags=re.MULTILINE)
        assert n == 1, k
    env.paths.config.write_text(txt)


def set_fee(env: Env, fee: int) -> None:
    txt = env.paths.config.read_text()
    env.paths.config.write_text(re.sub(r"^taker_fee_bp = \d+", f"taker_fee_bp = {fee}", txt, flags=re.MULTILINE))


def hashes(env: Env) -> dict[str, str]:
    return {
        "config_sha256": load_config(env.paths.config).sha256_hors_saison,
        "policy_sha256": load_policy(env.paths.policy).sha256,
        "prompt_sha256": prompt_sha256(),
        "code_sha256": saison.code_sha256(env.paths.repo),
    }


def derogation(env: Env, raison: str) -> None:
    (env.paths.var).mkdir(parents=True, exist_ok=True)
    (env.paths.var / "SAISON_DEROGATION").write_text(raison + "\n")


# ---------------------------------------------------------------------------------------------- config


def test_debut_ts_de_la_saison_1_est_le_13_novembre_2026_a_00h05_utc():
    cfg = load_config(REPO / "config" / "arene.toml")
    s = cfg.saison
    assert (s.numero, s.nom, s.debut_ts, s.duree_jours) == (1, "Saison 1", 1794528300, 56)
    assert datetime.fromtimestamp(s.debut_ts, UTC) == datetime(2026, 11, 13, 0, 5, tzinfo=UTC)
    assert (s.debut_ts - cfg.cycle_delay_s) % cfg.interval_s == 0  # l'instant de décision du cycle de 00:00


def test_table_saison_facultative_et_validee(tmp_path: Path):
    text = (REPO / "config" / "arene.toml").read_text()
    p = tmp_path / "c.toml"
    sans = re.sub(r"\[saison\].*?(?=\[\[instruments\]\])", "", text, flags=re.DOTALL)
    assert "[saison]" not in sans
    p.write_text(sans)
    cfg = load_config(p)
    assert cfg.saison is None and cfg.sha256_hors_saison == sha256_hors_saison(sans.encode())
    for bad in ("numero = 0", 'numero = "1"', 'nom = ""', "nom = 3", "debut_ts = 0", "debut_ts = 1.5", "duree_jours = 0"):
        key = bad.split(" = ")[0]
        p.write_text(re.sub(rf"^{key} = .*$", bad, text, flags=re.MULTILINE))
        with pytest.raises(ConfigError):
            load_config(p)
    p.write_text(text.replace("duree_jours = 56", "duree_jours = 56\nextra = 1"))
    with pytest.raises(ConfigError):
        load_config(p)
    p.write_text(text.replace("duree_jours = 56\n", ""))  # clé manquante
    with pytest.raises(ConfigError):
        load_config(p)


def test_hash_de_la_config_hors_saison_sur_le_toml_parse(tmp_path: Path):
    raw = (REPO / "config" / "arene.toml").read_bytes()
    base = sha256_hors_saison(raw)
    assert sha256_hors_saison(raw.replace(b'nom = "Saison 1"', b'nom = "Autre"')) == base
    assert sha256_hors_saison(raw.replace(b"duree_jours = 56", b"duree_jours = 30")) == base
    # Parsé, pas lu par lignes : commentaires, espaces et mise en forme n'ont aucun effet ...
    assert sha256_hors_saison(raw.replace(b"taker_fee_bp = 50", b"taker_fee_bp   =   50   # note")) == base
    assert sha256_hors_saison(raw.replace(b"e0065 = { L = 20, k = 3, H = 10 }", b"e0065 = { H = 10,   L = 20, k = 3 }")) == base
    assert sha256_hors_saison(raw.replace(b"[saison]\n", b"[saison]\n\n\n")) == base
    assert sha256_hors_saison(b"# autre commentaire\n" + raw) == base
    # ... et toute valeur qui change compte.
    assert sha256_hors_saison(raw.replace(b"taker_fee_bp = 50", b"taker_fee_bp = 51")) != base
    assert sha256_hors_saison(raw.replace(b"max_reveils_jour = 6", b"max_reveils_jour = 5")) != base
    assert sha256_hors_saison(raw.replace(b"daily_budget_usd = 0.10", b"daily_budget_usd = 0.11")) != base
    # La table [saison] placée ailleurs dans le fichier ne change rien non plus (pas de lecture par lignes).
    text = raw.decode()
    table = text[text.index("[saison]") : text.index("[[instruments]]")]
    moved = (text.replace(table, "") + "\n" + table).encode()
    assert moved != raw and sha256_hors_saison(moved) == base
    assert load_config(REPO / "config" / "arene.toml").sha256 != base  # le hash complet inclut la table


# ---------------------------------------------------------------------------------------------- événements


def test_saison_debut_reference_fin_ecrits_une_fois_aux_bons_cycles(tmp_path: Path):
    env = saison_env(tmp_path, debut=T0 + 2 * H4 + 300, jours=1)
    d = deciders()
    for i in range(10):
        assert cycle(env, i, d).status == "completed"
    t0, tf = T0 + 2 * H4, T0 + 8 * H4
    [debut] = of(env, "saison_debut")
    cfg = load_config(env.paths.config)
    p = debut["payload"]
    assert set(p) == {
        "numero", "nom", "cycle", "fin_prevue_cycle", "debut_ts", "duree_jours", "config_sha256", "policy_sha256",
        "prompt_sha256", "code_sha256", "git_head", "claude_cli_version", "portefeuilles",
    }  # fmt: skip
    assert (p["debut_ts"], p["duree_jours"], p["claude_cli_version"]) == (T0 + 2 * H4 + 300, 1, None)
    assert p["code_sha256"] == saison.code_sha256(REPO) and p["code_sha256"]
    assert (p["numero"], p["nom"], p["cycle"], p["fin_prevue_cycle"]) == (1, "Saison 1", t0, tf)
    assert {k: p[k] for k in ("config_sha256", "policy_sha256", "prompt_sha256", "code_sha256")} == hashes(env)
    assert p["config_sha256"] == cfg.sha256_hors_saison != cfg.sha256
    assert p["portefeuilles"] == [m.portfolio for m in cfg.models] + list(cfg.temoins.portfolios)
    assert isinstance(p["git_head"], str) and p["git_head"]
    # Avant les décisions du cycle de début, après son cycle_started.
    seq = lambda typ, **kw: [e["seq"] for e in of(env, typ) if all(e["payload"].get(k) == v for k, v in kw.items())]
    assert seq("cycle_started", cycle=t0)[0] < debut["seq"] < min(seq("decision_requested", cycle=t0) + seq("intent", cycle=t0))
    # Référence : juste après saison_debut, AVANT les décisions (donc avant tout fill, intention ou equity du cycle),
    # equity au bid avec les quotes de ce cycle.
    [ref] = of(env, "saison_reference")
    first_decision = min(seq("decision_requested", cycle=t0) + seq("intent", cycle=t0) + [e["seq"] for e in of(env, "fill") if e["ts"] == t0])
    assert debut["seq"] < ref["seq"] < first_decision and ref["seq"] == debut["seq"] + 1
    quotes = {e["payload"]["symbol"]: e["payload"]["bid"] for e in of(env, "quote") if e["ts"] == env.now_of(2)}
    assert len(quotes) == 6
    before = replay(env.events()[: ref["seq"]])
    expected = {p: equity_ueur(st, quotes, quotes) for p, st in sorted(before.items())}
    assert ref["payload"] == {"numero": 1, "cycle": t0, "equity": expected} and len(expected) == 8
    assert any(st.positions for st in before.values())  # des positions déjà ouvertes : l'equity n'est pas triviale
    eq0 = {e["payload"]["portfolio"]: e["payload"]["equity_ueur"] for e in of(env, "equity") if e["payload"]["cycle"] == t0}
    # Fin : au premier cycle dont t >= fin_prevue_cycle.
    [fin] = of(env, "saison_fin")
    eqf = {e["payload"]["portfolio"]: e["payload"]["equity_ueur"] for e in of(env, "equity") if e["payload"]["cycle"] == tf}
    assert fin["payload"] == {"numero": 1, "cycle": tf, "equity": dict(sorted(eqf.items()))}
    assert max(seq("equity", cycle=tf)) < fin["seq"] < seq("cycle_completed", cycle=tf)[0]
    assert len(eq0) == 8 and len(eqf) == 8
    assert not [e for e in of(env, "saison_debut", "saison_reference", "saison_fin") if e["payload"]["cycle"] < t0]
    assert not pl(env, "saison_derogation")
    assert verify(env.paths.journal).ok
    replay(env.events())


def test_idempotence_et_reprise_apres_crash_entre_debut_et_reference(tmp_path: Path, monkeypatch):
    env = saison_env(tmp_path, jours=56)
    real, hit = Journal.append, []

    def flaky(self, type, payload, ts):
        if type == "saison_reference" and not hit:
            hit.append(1)
            raise RuntimeError("crash entre saison_debut et saison_reference")
        return real(self, type, payload, ts)

    monkeypatch.setattr(Journal, "append", flaky)
    assert cycle(env, 0).status == "failed"
    monkeypatch.setattr(Journal, "append", real)  # (pas d'undo : il retirerait aussi les garde-fous de conftest)
    assert len(of(env, "saison_debut")) == 1 and not of(env, "saison_reference")  # crash entre les deux
    assert not of(env, "decision_requested")  # aucune décision n'a eu lieu
    rep = cycle(env, 0)
    assert rep.status == "completed" and rep.resumed
    assert len(of(env, "saison_debut")) == 1
    [ref] = of(env, "saison_reference")
    assert ref["payload"]["cycle"] == T0 and set(ref["payload"]["equity"]) == set(hashes_portfolios(env))
    assert ref["seq"] < min(e["seq"] for e in of(env, "decision_requested", "intent", "fill"))  # écrite avant les décisions
    before = env.paths.journal.read_bytes()
    assert cycle(env, 0).status == "already_done" and env.paths.journal.read_bytes() == before
    cycle(env, 1)
    assert len(of(env, "saison_debut")) == len(of(env, "saison_reference")) == 1 and not of(env, "saison_fin")


def hashes_portfolios(env: Env) -> list[str]:
    cfg = load_config(env.paths.config)
    return [m.portfolio for m in cfg.models] + list(cfg.temoins.portfolios)


# ---------------------------------------------------------------------------------------------- gel


def change(env: Env, what: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> str:
    """Change UN hash gelé ; renvoie sa clé."""
    if what == "config":
        set_fee(env, 51)
        return "config_sha256"
    if what == "policy":
        pol = tmp_path / f"policy-{env.root.name}.toml"
        pol.write_text(env.paths.policy.read_text() + "\n# changement\n")
        env.paths = replace(env.paths, policy=pol)
        return "policy_sha256"
    monkeypatch.setattr(cyc, "prompt_sha256", lambda: "f" * 64)
    monkeypatch.setattr(vei, "prompt_sha256", lambda: "f" * 64)
    return "prompt_sha256"


@pytest.mark.parametrize("what", ["config", "policy", "prompt"])
def test_refus_quand_un_hash_gele_change_un_a_la_fois(tmp_path: Path, monkeypatch, what: str):
    env = saison_env(tmp_path, jours=56)
    assert cycle(env, 0).status == "completed"
    before = hashes(env)
    key = change(env, what, monkeypatch, tmp_path)
    rep = cycle(env, 1)
    assert rep.status == "failed" and ("panique", "saison_gelee") in rep.alerts
    assert key in rep.error and "saison 1 gelée" in rep.error
    others = [k for k in before if k != key]
    assert not any(k in rep.error.split("(")[1].split(")")[0] for k in others)  # un seul hash nommé
    assert len(of(env, "cycle_started")) == 1 and len(of(env, "cycle_completed")) == 1  # rien n'a commencé
    assert ("panique", "saison_gelee") in codes(env)
    assert not pl(env, "saison_derogation")
    # Les hashes rétablis, le cycle reprend.
    monkeypatch.setattr(cyc, "prompt_sha256", prompt_sha256)
    monkeypatch.setattr(vei, "prompt_sha256", prompt_sha256)
    env.paths = replace(env.paths, policy=REPO / "config" / "policy.toml")
    set_fee(env, 50)
    assert cycle(env, 1).status == "completed"


def test_derogation_ecrite_journalisee_une_fois_par_changement_de_hash(tmp_path: Path, monkeypatch):
    env = saison_env(tmp_path, jours=56)
    cycle(env, 0)
    h0 = hashes(env)
    set_fee(env, 51)
    derogation(env, "essai des frais à 51 bp")
    assert cycle(env, 1).status == "completed"
    [d1] = pl(env, "saison_derogation")
    assert d1 == {"numero": 1, "raison": "essai des frais à 51 bp", "hashes_avant": h0, "hashes_apres": hashes(env)}
    assert d1["hashes_apres"]["config_sha256"] != h0["config_sha256"] and d1["hashes_apres"]["policy_sha256"] == h0["policy_sha256"]
    assert ("action", "saison_derogation") in codes(env)
    cycle(env, 2)  # même changement, fichier toujours là : pas de nouvel événement
    assert len(pl(env, "saison_derogation")) == 1
    h1 = hashes(env)
    change(env, "policy", monkeypatch, tmp_path)  # nouveau changement : nouvelle dérogation, depuis le dernier état
    assert cycle(env, 3).status == "completed"
    d2 = pl(env, "saison_derogation")[1]
    assert (d2["hashes_avant"], d2["hashes_apres"]) == (h1, hashes(env)) and d2["raison"] == "essai des frais à 51 bp"
    # Sans raison écrite (fichier vide), le gel s'applique de nouveau.
    derogation(env, "")
    set_fee(env, 52)
    assert cycle(env, 4).status == "failed"
    assert len(pl(env, "saison_derogation")) == 2


def test_un_changement_du_nom_de_la_saison_n_est_pas_gele_les_autres_cles_alertent_sans_effet(tmp_path: Path):
    env = saison_env(tmp_path, jours=56)
    cycle(env, 0)
    h0 = hashes(env)
    set_saison(env, nom="Saison 1 bis")
    assert hashes(env) == h0
    assert cycle(env, 1).status == "completed" and not pl(env, "saison_derogation")
    assert not [c for c in codes(env) if c[1] == "saison_modifiee"]  # le nom seul : aucune alerte
    assert len(of(env, "saison_debut")) == 1 and pl(env, "saison_debut")[0]["nom"] == "Saison 1"
    assert pl(env, "config_loaded")[-1]["config_sha256"] != pl(env, "config_loaded")[0]["config_sha256"]  # hash complet : journalisé
    set_saison(env, duree_jours=30)  # modifiée pendant la saison ouverte : alerte panique, aucun effet, le cycle tourne
    assert cycle(env, 2).status == "completed"
    assert [c for c in codes(env) if c[1] == "saison_modifiee"] == [("panique", "saison_modifiee")]
    cycle(env, 3)
    assert len([c for c in codes(env) if c[1] == "saison_modifiee"]) == 1  # une seule alerte par état
    assert len(of(env, "saison_debut")) == 1 and pl(env, "saison_debut")[0]["fin_prevue_cycle"] == T0 + 56 * DAY
    assert hashes(env) == h0


def test_un_second_saison_debut_est_refuse_tant_qu_une_saison_est_ouverte_numero_suivant(tmp_path: Path):
    env = saison_env(tmp_path, jours=1)
    d = None
    cycle(env, 0, d)
    set_saison(env, numero=2, debut_ts=T0 + 2 * H4 + 300)  # une saison 2 demandée alors que la 1 est ouverte
    for i in range(1, 6):
        assert cycle(env, i, d).status == "completed"
    assert [p["numero"] for p in pl(env, "saison_debut")] == [1]  # refusée
    assert ("panique", "saison_modifiee") in codes(env)
    assert cycle(env, 6, d).status == "completed" and len(of(env, "saison_fin")) == 1  # la 1 se termine au cycle 6
    # Terminée : la saison 2 démarre (dernier numéro + 1), mais pas un numéro 3.
    set_saison(env, numero=3, debut_ts=T0 + 7 * H4 + 300)
    assert cycle(env, 7, d).status == "completed"
    assert [p["numero"] for p in pl(env, "saison_debut")] == [1]
    assert [c for c in codes(env) if c[1] == "saison_numero"] == [("action", "saison_numero")]
    cycle(env, 8, d)
    assert len([c for c in codes(env) if c[1] == "saison_numero"]) == 1
    set_saison(env, numero=2, debut_ts=T0 + 8 * H4 + 300)
    assert cycle(env, 9, d).status == "completed"
    assert [p["numero"] for p in pl(env, "saison_debut")] == [1, 2] and pl(env, "saison_debut")[1]["cycle"] == T0 + 9 * H4
    assert len(of(env, "saison_reference")) == 2
    # Une saison déjà terminée dont le numéro reste dans la config ne redémarre pas.
    set_saison(env, numero=1, debut_ts=T0 + 300)
    cycle(env, 10, d)
    assert [p["numero"] for p in pl(env, "saison_debut")] == [1, 2]


def code_repo(root: Path) -> Path:
    """Arborescence factice (sans git : le gel ne dépend pas de git)."""
    root.mkdir(parents=True, exist_ok=True)
    for f, txt in {
        "arene/cycle.py": "a = 1\n", "arene/deciders/prompt/v1.md": "p\n", "arene/risk/riskd.py": "r = 1\n",
        "arene/ops/killswitch.py": "k = 1\n", "config/policy.toml": "p = 1\n",
        "arene/site/x.py": "x = 1\n", "arene/cli.py": "c = 1\n", "arene/ops/autre.py": "o = 1\n",
        "arene/perp/ligue.py": "l = 1\n", "arene/stats.py": "s = 1\n", "uv.lock": "lock = 1\n", "autre/z.py": "z = 1\n",
    }.items():  # fmt: skip
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        (root / f).write_text(txt)
    return root


def test_code_sha256_liste_blanche_sur_le_disque_sans_git(tmp_path: Path):
    repo = code_repo(tmp_path / "repo")
    base = saison.code_sha256(repo)
    assert saison._fichiers_code(repo) == [
        "arene/cycle.py", "arene/deciders/prompt/v1.md", "arene/ops/killswitch.py", "arene/risk/riskd.py",
        "config/policy.toml",
    ]  # fmt: skip

    def changed(path: str, txt: str = "changé\n") -> bool:
        before = (repo / path).read_text()
        (repo / path).write_text(txt)
        try:
            return saison.code_sha256(repo) != base
        finally:
            (repo / path).write_text(before)

    for gele in ("arene/cycle.py", "arene/deciders/prompt/v1.md", "arene/risk/riskd.py", "arene/ops/killswitch.py",
                 "config/policy.toml"):
        assert changed(gele), gele
    for libre in ("arene/site/x.py", "arene/cli.py", "arene/ops/autre.py", "arene/perp/ligue.py", "arene/stats.py",
                  "uv.lock", "autre/z.py"):
        assert not changed(libre), libre
    # Un module neuf dans un dossier gelé change le hash ; un fichier d'éditeur ou un cache, non.
    (repo / "arene/risk/riskd.py.swp").write_bytes(b"x")
    (repo / "arene/risk/__pycache__").mkdir()
    (repo / "arene/risk/__pycache__/riskd.cpython-312.pyc").write_bytes(b"x")
    assert saison.code_sha256(repo) == base
    (repo / "arene/risk/neuf.py").write_text("n = 1\n")
    assert saison.code_sha256(repo) != base
    (repo / "arene/risk/neuf.py").unlink()
    assert saison.code_sha256(repo) == base == saison.code_sha256(repo)


def test_code_gele_pendant_la_saison_derogation_exigee(tmp_path: Path):
    repo = code_repo(tmp_path / "repo")
    env = saison_env(tmp_path, jours=56)
    env.paths = replace(env.paths, repo=repo)
    assert cycle(env, 0).status == "completed"
    assert pl(env, "saison_debut")[0]["code_sha256"] == saison.code_sha256(repo)
    (repo / "arene/cli.py").write_text("c = 2\n")  # hors périmètre : permis
    (repo / "arene/site/x.py").write_text("x = 2\n")
    assert cycle(env, 1).status == "completed"
    avant = saison.code_sha256(repo)
    (repo / "arene/perp/ligue.py").write_text("l = 2\n")  # ligue dérivés : hors gel
    assert saison.code_sha256(repo) == avant
    (repo / "arene/cycle.py").write_text("a = 2  # correctif\n")  # dans le périmètre : gelé
    rep = cycle(env, 2)
    assert rep.status == "failed" and "code_sha256" in rep.error and ("panique", "saison_gelee") in rep.alerts
    derogation(env, "correctif cycle.py")
    assert cycle(env, 2).status == "completed"
    [d] = pl(env, "saison_derogation")
    assert d["hashes_avant"]["code_sha256"] != d["hashes_apres"]["code_sha256"] == saison.code_sha256(repo)
    assert d["hashes_avant"]["config_sha256"] == d["hashes_apres"]["config_sha256"]


def test_version_de_la_cli_claude_journalisee_non_gelee_alerte_info(tmp_path: Path, monkeypatch):
    env = saison_env(tmp_path, jours=56)
    reelle = saison.claude_cli_version
    monkeypatch.setattr(saison, "claude_cli_version", lambda: "2.1.0 (Claude Code)")
    cycle(env, 0)
    assert pl(env, "saison_debut")[0]["claude_cli_version"] == "2.1.0 (Claude Code)"
    assert pl(env, "config_loaded")[-1]["claude_cli_version"] == "2.1.0 (Claude Code)"
    monkeypatch.setattr(saison, "claude_cli_version", lambda: "2.2.0 (Claude Code)")
    assert cycle(env, 1).status == "completed"  # non gelée : le cycle tourne sans dérogation
    assert not pl(env, "saison_derogation")
    assert pl(env, "config_loaded")[-1]["claude_cli_version"] == "2.2.0 (Claude Code)" and len(pl(env, "config_loaded")) == 2
    assert [(a["level"], a["message"]) for a in pl(env, "alert") if a["code"] == "claude_cli_version"] == [
        ("info", "claude --version : 2.1.0 (Claude Code) -> 2.2.0 (Claude Code)")
    ]
    cycle(env, 2)
    assert len(pl(env, "config_loaded")) == 2
    # Sans CLI lisible : None.
    monkeypatch.setattr(saison, "claude_cli_version", reelle)  # (pas d'undo : il retirerait aussi le garde-fou de conftest)
    assert saison.claude_cli_version() is None  # conftest : binaire introuvable, jamais de vraie CLI


def test_un_reveil_est_refuse_pendant_la_saison_gelee_sauf_derogation(tmp_path: Path):
    env = saison_env(tmp_path, jours=56)
    d = prepare(env, X)
    set_fee(env, 51)
    n = len(of(env, "veille"))
    rep = tick(env, X, d)
    assert rep.declencheur is not None and rep.refus == "saison_gelee" and rep.reveil is None
    assert not env.of_type("reveil_started") and len(of(env, "veille")) == n + 1
    assert of(env, "veille")[-1]["payload"]["refus"] == "saison_gelee"
    assert [a["code"] for a in pl(env, "alert")].count("saison_gelee") == 1
    assert ("panique", "saison_gelee") in codes(env)
    # Dérogation écrite : le réveil part (le cycle suivant journalisera la dérogation).
    env2 = saison_env(tmp_path, "e2", jours=56)
    d2 = prepare(env2, X)
    set_fee(env2, 51)
    derogation(env2, "essai")
    rep2 = tick(env2, X, d2)
    assert rep2.refus is None and rep2.reveil == "completed"
    assert cycle(env2, 1, d2).status == "completed" and len(pl(env2, "saison_derogation")) == 1


def test_gel_leve_apres_la_fin_de_saison(tmp_path: Path):
    env = saison_env(tmp_path, jours=1)  # début au cycle 0, fin au cycle 6 (t = T0 + 86 400)
    d = deciders()
    for i in range(5):
        cycle(env, i, d)
    set_fee(env, 51)
    assert cycle(env, 5, d).status == "failed"  # t < fin_prevue : gelé
    assert not of(env, "saison_fin")
    assert cycle(env, 6, d).status == "completed"  # t >= fin_prevue_cycle : le gel ne s'applique plus, saison_fin écrite
    [fin] = of(env, "saison_fin")
    assert fin["payload"]["cycle"] == T0 + 6 * H4
    assert cycle(env, 7, d).status == "completed" and len(of(env, "saison_fin")) == 1 and not pl(env, "saison_derogation")


# ---------------------------------------------------------------------------------------------- statut


def status(env: Env, now: int, capsys) -> str:
    capsys.readouterr()
    args = ["--var", str(env.paths.var), "--secrets", str(env.paths.secrets), "--config", str(env.paths.config), "--policy", str(env.paths.policy)]
    assert cli.main([*args, "status"], clients=env.clients, now=lambda: now) == 0
    return capsys.readouterr().out


def test_statut_en_attente_en_cours_et_terminee(tmp_path: Path, capsys):
    env = make_env(tmp_path, "attente")  # la table du dépôt : début le 13/11/2026
    cycle(env, 0)
    out = status(env, T0 + 1000, capsys)
    assert "saison : Saison 1 en attente (début au cycle du 2026-11-13 00:05 UTC, 56 jours)" in out

    env = saison_env(tmp_path, "cours", jours=56)
    for i in range(4):
        cycle(env, i)
    out = status(env, T0 + 2 * DAY + 5, capsys)
    assert "saison : Saison 1 en cours (jour 3 sur 56), début 2025-11-08 00:00 UTC, dérogations : 0" in out
    ref = pl(env, "saison_reference")[0]["equity"]
    last = {e["payload"]["portfolio"]: e["payload"]["equity_ueur"] for e in of(env, "equity")}
    for p, b in ref.items():
        cur = last[p]
        eur = f"{cur / 1_000_000:,.2f} EUR".replace(",", " ")
        assert f"  {p:28s} {eur:>16s} {(cur - b) * 100 / b:+7.2f} %" in out
    set_fee(env, 51)
    derogation(env, "essai")
    cycle(env, 4)
    assert "dérogations : 1" in status(env, T0 + 2 * DAY + 5, capsys)

    env = saison_env(tmp_path, "finie", jours=1)
    for i in range(7):
        cycle(env, i)
    out = status(env, T0 + 6 * H4 + 400, capsys)
    assert f"saison : Saison 1 terminée (cycle {datetime.fromtimestamp(T0 + 6 * H4, UTC).strftime('%Y-%m-%d %H:%M UTC')}), début 2025-11-08 00:00 UTC, dérogations : 0" in out
    fin = pl(env, "saison_fin")[0]["equity"]
    p = "llm:claude-haiku-5-5"
    assert f"  {p:28s}" in out and f"{(fin[p] - ref[p]) * 100 / ref[p]:+7.2f} %" in out
