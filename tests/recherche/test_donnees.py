"""Tests des données de recherche. Aucun réseau (transport simulé) sauf le test marqué `reseau`.
Toutes les séries sont synthétiques."""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pytest

from recherche.config import COUPURE_TS, CoupureError, charger_criteres
from recherche.donnees import (
    DonneesError,
    ManifesteError,
    charger,
    choisir_univers_controle,
    construire_donnees,
    construire_manifeste,
    copier_in_sample,
    telecharger_mois,
    verifier_manifeste,
)
from recherche.donnees import construire as mod_construire
from recherche.donnees import controle as mod_controle
from recherche.donnees import telecharger as mod_tel
from recherche.donnees.labo import LaboError
from recherche.donnees.lecture import lire_barres_zip, lire_funding_zip


def ms(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp() * 1000)


@pytest.fixture(autouse=True)
def _sans_pause(monkeypatch):
    monkeypatch.setattr(mod_tel, "PAUSE_S", 0.0)


# ---------------------------------------------------------------------------------------- fabriques

def zip_de(nom: str, texte: str) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(nom.replace(".zip", ".csv"), texte)
    return b.getvalue()


def lignes_barres(debut: str, n: int, pas_s: int, entete=False, micro=False, prix=100.0, qv=10.0, saute=()):
    t0 = ms(debut)
    entete_csv = ("open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,"
                  "taker_buy_quote_volume,ignore")
    out = [entete_csv] if entete else []
    for i in range(n):
        if i in saute:
            continue
        o = t0 + i * pas_s * 1000
        p = prix + i * 0.01
        f = 1000 if micro else 1
        out.append(f"{o * f},{p},{p + 1},{p - 1},{p + 0.5},5,{(o + pas_s * 1000 - 1) * f},{qv},7,2,{qv / 2},0")
    return "\n".join(out) + "\n"


def csv_labo(debut: str, n: int, pas_s: int, saute=()):
    t0 = pd.Timestamp(debut)
    out = ["open_time_utc,open,high,low,close,volume,quote_volume,trades,taker_buy_base,taker_buy_quote"]
    for i in range(n):
        if i in saute:
            continue
        t = (t0 + pd.Timedelta(seconds=i * pas_s)).strftime("%Y-%m-%dT%H:%M:%SZ")
        p = 50 + i * 0.01
        out.append(f"{t},{p},{p + 1},{p - 1},{p + 0.5},5,{p * 5},7,2,{p * 2}")
    return "\n".join(out) + "\n"


def lignes_funding(horodatages_ms: list[int], entete=True):
    out = ["calc_time,funding_interval_hours,last_funding_rate"] if entete else []
    out += [f"{t},8,0.0001" for t in horodatages_ms]
    return "\n".join(out) + "\n"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class Serveur:
    """Faux data.binance.vision : sert zips, .CHECKSUM et listings S3."""

    def __init__(self):
        self.fichiers: dict[str, bytes] = {}
        self.requetes: list[str] = []
        self.checksum_faux: set[str] = set()

    def ajouter(self, chemin: str, octets: bytes):
        self.fichiers[f"https://data.binance.vision/data/{chemin}"] = octets

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._repondre), follow_redirects=True)

    @property
    def n_zips(self) -> int:
        return sum(1 for r in self.requetes if r.endswith(".zip"))

    def _repondre(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url).split("?")[0]
        self.requetes.append(url)
        if url.startswith("https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"):
            prefixe = req.url.params["prefix"]
            delim = req.url.params.get("delimiter")
            cles = sorted(u.split("/data.binance.vision/")[1] for u in self.fichiers
                          if u.split("/data.binance.vision/")[1].startswith(prefixe))
            corps = ["<ListBucketResult xmlns='http://s3.amazonaws.com/doc/2006-03-01/'><IsTruncated>false</IsTruncated>"]
            if delim:
                prefs = sorted({prefixe + c[len(prefixe):].split("/")[0] + "/" for c in cles})
                corps += [f"<CommonPrefixes><Prefix>{p}</Prefix></CommonPrefixes>" for p in prefs]
            else:
                corps += [f"<Contents><Key>{c}</Key></Contents>" for c in cles]
            corps.append("</ListBucketResult>")
            return httpx.Response(200, text="".join(corps))
        if url.endswith(".CHECKSUM"):
            base = url[: -len(".CHECKSUM")]
            if base not in self.fichiers:
                return httpx.Response(404)
            h = "0" * 64 if base in self.checksum_faux else sha(self.fichiers[base])
            return httpx.Response(200, text=f"{h}  {base.rsplit('/', 1)[-1]}\n")
        if url in self.fichiers:
            return httpx.Response(200, content=self.fichiers[url])
        return httpx.Response(404)


# ------------------------------------------------------------------------------------ pare-feu / url

@pytest.mark.parametrize("annee,mois", [(2026, 7), (2026, 12), (2027, 1), (2030, 3)])
@pytest.mark.parametrize("source", ["perp_funding", "perp_klines_1h", "spot_klines_1d"])
def test_mois_apres_coupure_leve_sans_reseau(tmp_path, source, annee, mois):
    class Interdit(httpx.BaseTransport):
        def handle_request(self, request):
            raise AssertionError("appel réseau interdit")

    with httpx.Client(transport=Interdit()) as c, pytest.raises(CoupureError):
        telecharger_mois(source, "BTCUSDT", annee, mois, tmp_path, client=c)
    # Et sans client du tout : l'erreur précède même la création du client.
    with pytest.raises(CoupureError):
        telecharger_mois(source, "BTCUSDT", annee, mois, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_urls():
    u = mod_tel.url_mois
    assert u("perp_funding", "BTCUSDT", 2024, 1) == (
        "https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2024-01.zip")
    assert u("perp_klines_1h", "ETHUSDT", 2026, 6) == (
        "https://data.binance.vision/data/futures/um/monthly/klines/ETHUSDT/1h/ETHUSDT-1h-2026-06.zip")
    assert u("spot_klines_1d", "ADAUSDT", 2020, 1) == (
        "https://data.binance.vision/data/spot/monthly/klines/ADAUSDT/1d/ADAUSDT-1d-2020-01.zip")
    with pytest.raises(ValueError):
        u("autre", "BTCUSDT", 2020, 1)


# --------------------------------------------------------------------------------------- téléchargement

def test_telechargement_verifie_checksum_et_reprend(tmp_path):
    srv = Serveur()
    z = zip_de("x.zip", lignes_funding([ms("2024-01-01T00:00:00")]))
    srv.ajouter("futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2024-01.zip", z)
    with srv.client() as c:
        p = telecharger_mois("perp_funding", "BTCUSDT", 2024, 1, tmp_path, client=c)
        assert p.read_bytes() == z and p.name == "BTCUSDT-fundingRate-2024-01.zip"
        n = len(srv.requetes)
        assert telecharger_mois("perp_funding", "BTCUSDT", 2024, 1, tmp_path, client=c) == p
        assert len(srv.requetes) == n  # sauté, sans réseau
        # fichier corrompu : retéléchargé
        p.write_bytes(b"corrompu")
        telecharger_mois("perp_funding", "BTCUSDT", 2024, 1, tmp_path, client=c)
        assert p.read_bytes() == z and len(srv.requetes) == n + 2


def test_checksum_different_refuse_et_rien_n_est_ecrit(tmp_path):
    srv = Serveur()
    chemin = "spot/monthly/klines/AAAUSDT/1d/AAAUSDT-1d-2020-01.zip"
    srv.ajouter(chemin, zip_de("x.zip", lignes_barres("2020-01-01T00:00:00", 31, 86400)))
    srv.checksum_faux.add("https://data.binance.vision/data/" + chemin)
    with srv.client() as c, pytest.raises(mod_tel.TelechargementError):
        telecharger_mois("spot_klines_1d", "AAAUSDT", 2020, 1, tmp_path, client=c)
    assert not list(tmp_path.rglob("*.zip"))


def test_archive_absente(tmp_path):
    with Serveur().client() as c, pytest.raises(mod_tel.DonneeAbsente):
        telecharger_mois("spot_klines_1d", "ZZZUSDT", 2020, 1, tmp_path, client=c)


def test_lister_mois_filtre_apres_coupure():
    srv = Serveur()
    for a, m in [(2026, 5), (2026, 6), (2026, 7), (2027, 1)]:
        srv.ajouter(f"spot/monthly/klines/AAAUSDT/1d/AAAUSDT-1d-{a}-{m:02d}.zip", b"x")
        srv.ajouter(f"spot/monthly/klines/AAAUSDT/1d/AAAUSDT-1d-{a}-{m:02d}.zip.CHECKSUM", b"x")
    with srv.client() as c:
        assert mod_tel.lister_mois("spot_klines_1d", "AAAUSDT", c) == [(2026, 5), (2026, 6)]


# ------------------------------------------------------------------------------------------- lecture

def test_lecture_avec_ou_sans_entete_et_microsecondes():
    a = lire_barres_zip(zip_de("a.zip", lignes_barres("2024-01-01T00:00:00", 3, 3600, entete=True)))
    b = lire_barres_zip(zip_de("a.zip", lignes_barres("2024-01-01T00:00:00", 3, 3600, entete=False)))
    c = lire_barres_zip(zip_de("a.zip", lignes_barres("2024-01-01T00:00:00", 3, 3600, micro=True)))
    pd.testing.assert_frame_equal(a, b)
    pd.testing.assert_frame_equal(a, c)
    assert a.index[0] == pd.Timestamp("2024-01-01") and a.index.name == "open_time"


def test_lecture_funding_connue_a_est_horodatage_plus_1s():
    t = ms("2024-01-01T08:00:00") + 5  # gigue de quelques ms comme dans les archives réelles
    f = lire_funding_zip(zip_de("f.zip", lignes_funding([t])))
    assert int(f["connue_a"].iloc[0]) == ms("2024-01-01T08:00:00") // 1000 + 1
    assert f["taux"].iloc[0] == 0.0001


# ------------------------------------------------------------------------------------------- labo

def labo_factice(src: Path, ok=True):
    src.mkdir(parents=True)
    entrees = []
    for nom in ("AAAUSDT_1d.csv", "AAAUSDT_1h.csv"):
        contenu = csv_labo("2026-06-01", 5, 86400)
        (src / nom).write_text(contenu)
        entrees.append({"fichier": nom, "barres": 5, "sha256": sha(contenu.encode()) if ok else "0" * 64})
    (src / "MANIFESTE.json").write_text(json.dumps({"fichiers": entrees}))


def test_copie_labo_verifiee(tmp_path):
    labo_factice(tmp_path / "src")
    out = copier_in_sample(tmp_path / "src", tmp_path / "dest")
    assert sorted(p.name for p in out) == ["AAAUSDT_1d.csv", "AAAUSDT_1h.csv"]
    assert (tmp_path / "dest" / "MANIFESTE.json").exists()
    copier_in_sample(tmp_path / "src", tmp_path / "dest")  # reprenable


def test_copie_labo_refuse_un_sha_different_et_ne_copie_rien(tmp_path):
    labo_factice(tmp_path / "src", ok=False)
    with pytest.raises(LaboError):
        copier_in_sample(tmp_path / "src", tmp_path / "dest")
    assert not (tmp_path / "dest").exists()


# ----------------------------------------------------------------------------------------- contrôle

def serveur_controle(n_ok=22):
    srv = Serveur()

    def ajout(sym, qv, n=31):
        srv.ajouter(f"spot/monthly/klines/{sym}/1d/{sym}-1d-2020-01.zip",
                    zip_de("x.zip", lignes_barres("2020-01-01T00:00:00", n, 86400, qv=qv)))

    for i in range(n_ok):
        ajout(f"C{i:02d}USDT", 1000.0 + i)
    ajout("BTCUSDT", 1e9)  # dans l'univers
    ajout("USDCUSDT", 1e9)  # stablecoin
    ajout("BNBUPUSDT", 1e9)  # jeton à levier
    ajout("PARTUSDT", 1e9, n=20)  # 2020-01 incomplet
    srv.ajouter("spot/monthly/klines/NOEURBTC/1d/NOEURBTC-1d-2020-01.zip", b"x")  # pas USDT
    srv.ajouter("spot/monthly/klines/LATEUSDT/1d/LATEUSDT-1d-2021-03.zip", b"x")  # pas de 2020-01
    return srv


def test_univers_controle_regle_et_gel(tmp_path):
    srv = serveur_controle()
    sortie = tmp_path / "univers_controle.json"
    with srv.client() as c:
        liste = choisir_univers_controle(sortie, cache=tmp_path / "brut", client=c, date="2026-11-11")
    # les 20 plus gros volumes parmi C00..C21 : C02..C21, par volume décroissant
    assert liste == [f"C{i:02d}USDT" for i in range(21, 1, -1)]
    doc = json.loads(sortie.read_text())
    assert doc["symboles"] == liste and doc["date"] == "2026-11-11" and doc["taille"] == 20
    n = len(srv.requetes)
    with srv.client() as c:  # figé : relu sans réseau
        assert choisir_univers_controle(sortie, cache=tmp_path / "brut", client=c) == liste
    assert len(srv.requetes) == n


def test_univers_controle_reprenable(tmp_path):
    srv = serveur_controle()
    with srv.client() as c:
        choisir_univers_controle(tmp_path / "u.json", cache=tmp_path / "brut", client=c, date="2026-11-11")
    zips = srv.n_zips
    with srv.client() as c:
        choisir_univers_controle(tmp_path / "u2.json", cache=tmp_path / "brut", client=c, date="2026-11-11")
    # rien n'est retéléchargé : seuls les listings sont refaits, aucun zip demandé deux fois
    assert srv.n_zips == zips


def test_admissibilite():
    u = frozenset({"BTCUSDT"})
    assert mod_controle.candidat_admissible("XMRUSDT", u)
    for s in ("BTCUSDT", "USDCUSDT", "TUSDUSDT", "BUSDUSDT", "ETHUPUSDT", "BNBBEARUSDT", "ETHBTC", "EURUSDT"):
        assert not mod_controle.candidat_admissible(s, u)


# ------------------------------------------------------------------------------ chargeur : fixtures

def racine_factice(tmp_path, *, fin_1d="2026-06-30", barres_1h=None, saute_1h=(), saute_1d=(),
                   funding=None, perp_debut="2026-06-29T00:00:00", perp_n=48, perp_saute=(),
                   avec_perp=True, controle=True) -> Path:
    """Racine minimale : un symbole AAAUSDT, 10 jours 1 j, 1 h sur la période demandée."""
    r = tmp_path / "donnees"
    (r / "labo").mkdir(parents=True)
    fin = pd.Timestamp(fin_1d)
    debut_1d = fin - pd.Timedelta(days=9)
    (r / "labo" / "AAAUSDT_1d.csv").write_text(csv_labo(str(debut_1d.date()), 10, 86400, saute=saute_1d))
    n1h = barres_1h or 240
    debut_1h = fin + pd.Timedelta(days=1) - pd.Timedelta(hours=n1h)
    (r / "labo" / "AAAUSDT_1h.csv").write_text(csv_labo(str(debut_1h), n1h, 3600, saute=saute_1h))
    if avec_perp:
        d = r / "brut" / "perp_klines_1h" / "AAAUSDT"
        d.mkdir(parents=True)
        (d / "AAAUSDT-1h-2026-06.zip").write_bytes(
            zip_de("x.zip", lignes_barres(perp_debut, perp_n, 3600, entete=True, saute=perp_saute)))
        d = r / "brut" / "perp_funding" / "AAAUSDT"
        d.mkdir(parents=True)
        f = funding or [ms("2026-06-29T00:00:00") + k * 8 * 3600_000 + 2 for k in range(6)]
        (d / "AAAUSDT-fundingRate-2026-06.zip").write_bytes(zip_de("x.zip", lignes_funding(f)))
    if controle:
        d = r / "brut" / "spot_klines_1d" / "CTLUSDT"
        d.mkdir(parents=True)
        (d / "CTLUSDT-1d-2026-06.zip").write_bytes(
            zip_de("x.zip", lignes_barres("2026-06-20T00:00:00", 10, 86400, micro=True)))
    return r


def ctl_json(tmp_path, symboles=("CTLUSDT",)):
    p = tmp_path / "univers_controle.json"
    p.write_text(json.dumps({"symboles": list(symboles)}))
    return p


def charge(tmp_path, r, **kw):
    construire_manifeste(r, ctl_json(tmp_path))
    return charger(r, symboles=["AAAUSDT"], univers_controle_path=tmp_path / "univers_controle.json",
                   strict=False, **kw)


# ------------------------------------------------------------------------------------ chargeur : cas

def test_chargeur_nominal_et_connue_a(tmp_path):
    d = charge(tmp_path, racine_factice(tmp_path))
    assert d.univers == ("AAAUSDT",) and d.controle == ("CTLUSDT",)
    j = d.spot_1d["AAAUSDT"]
    # barre 1 j du 2026-06-30 : connue_a = coupure exactement (autorisée, comparaison stricte)
    assert j.index[-1] == pd.Timestamp("2026-06-30") and int(j["connue_a"].iloc[-1]) == COUPURE_TS
    h = d.spot_1h["AAAUSDT"]
    assert h.index[-1] == pd.Timestamp("2026-06-30 23:00") and int(h["connue_a"].iloc[-1]) == COUPURE_TS
    assert (h["connue_a"].diff().dropna() == 3600).all() and not h["rempli"].any()
    assert j["connue_a"].dtype == np.int64 and j["close"].dtype == np.float64
    p = d.perp_1h["AAAUSDT"]
    assert len(p) == 48 and int(p["connue_a"].iloc[-1]) == COUPURE_TS
    f = d.funding["AAAUSDT"]
    assert len(f) == 6
    assert int(f["connue_a"].iloc[0]) == ms("2026-06-29T00:00:00") // 1000 + 1  # fundingTime + 1 s (gigue 2 ms)
    c = d.controle_1d["CTLUSDT"]
    assert len(c) == 10 and c.index[0] == pd.Timestamp("2026-06-20")  # microsecondes normalisées
    assert d.manifeste_sha256


def test_perp_absent_donne_none(tmp_path):
    d = charge(tmp_path, racine_factice(tmp_path, avec_perp=False))
    assert d.perp_1h["AAAUSDT"] is None and d.funding["AAAUSDT"] is None


def test_barre_apres_coupure_leve(tmp_path):
    # une barre 1 j ouverte le 2026-07-01 a connue_a = 2026-07-02 > coupure
    r = racine_factice(tmp_path)
    p = r / "labo" / "AAAUSDT_1d.csv"
    p.write_text(p.read_text() + "2026-07-01T00:00:00Z,50,51,49,50.5,5,250,7,2,100\n")
    with pytest.raises(CoupureError):
        charge(tmp_path, r)


def test_barre_1h_ouverte_a_la_coupure_leve(tmp_path):
    r = racine_factice(tmp_path)
    p = r / "labo" / "AAAUSDT_1h.csv"
    p.write_text(p.read_text() + "2026-07-01T00:00:00Z,50,51,49,50.5,5,250,7,2,100\n")
    with pytest.raises(CoupureError):
        charge(tmp_path, r)


def test_barre_perp_apres_coupure_leve(tmp_path):
    with pytest.raises(CoupureError):
        charge(tmp_path, racine_factice(tmp_path, perp_debut="2026-06-30T12:00:00", perp_n=13))


def test_funding_a_la_coupure_leve_mais_pas_avant(tmp_path):
    # fundingTime = 2026-07-01T00:00:00Z -> connue_a = coupure + 1 s : refusé
    with pytest.raises(CoupureError):
        charge(tmp_path, racine_factice(tmp_path, funding=[ms("2026-06-30T16:00:00"), ms("2026-07-01T00:00:00")]))
    d = charge(tmp_path / "ok", racine_factice(tmp_path / "ok", funding=[ms("2026-06-30T16:00:00")]))
    assert int(d.funding["AAAUSDT"]["connue_a"].iloc[-1]) == ms("2026-06-30T16:00:00") // 1000 + 1


def test_controle_apres_coupure_leve(tmp_path):
    r = racine_factice(tmp_path, controle=False)
    d = r / "brut" / "spot_klines_1d" / "CTLUSDT"
    d.mkdir(parents=True)
    (d / "CTLUSDT-1d-2026-06.zip").write_bytes(zip_de("x.zip", lignes_barres("2026-06-28T00:00:00", 5, 86400)))
    with pytest.raises(CoupureError):
        charge(tmp_path, r)  # la barre du 07-02 (ouverte après la coupure)


def test_trou_1d_refuse(tmp_path):
    with pytest.raises(DonneesError, match="trou"):
        charge(tmp_path, racine_factice(tmp_path, saute_1d={4}))


def test_trou_1h_dans_la_tolerance_est_rempli(tmp_path):
    n = 2400  # 1 manquante = 0,04 % < 0,1 %
    d = charge(tmp_path, racine_factice(tmp_path, barres_1h=n, saute_1h={1000}))
    h = d.spot_1h["AAAUSDT"]
    assert len(h) == n and int(h["rempli"].sum()) == 1
    rempli = h[h["rempli"]].iloc[0]
    prec = h["close"].iloc[h.index.get_loc(rempli.name) - 1]
    assert rempli["close"] == rempli["open"] == rempli["high"] == rempli["low"] == prec
    assert rempli["volume"] == 0.0 and rempli["trades"] == 0.0


def test_trou_1h_hors_tolerance_refuse(tmp_path):
    with pytest.raises(DonneesError, match="manquantes"):
        charge(tmp_path, racine_factice(tmp_path, saute_1h={10}))  # 1/240 > 0,1 %
    with pytest.raises(DonneesError, match="suite"):  # 7 consécutives dans une série assez longue
        charge(tmp_path / "b", racine_factice(tmp_path / "b", barres_1h=7200, saute_1h=set(range(100, 107))))


def test_strict_exige_la_fin_a_la_coupure(tmp_path):
    r = racine_factice(tmp_path, fin_1d="2026-06-29")
    construire_manifeste(r, ctl_json(tmp_path))
    with pytest.raises(DonneesError):
        charger(r, symboles=["AAAUSDT"], univers_controle_path=tmp_path / "univers_controle.json", strict=True)


def test_manifeste_detecte_modification_ajout_et_absence(tmp_path):
    r = racine_factice(tmp_path)
    ctl = ctl_json(tmp_path)
    construire_manifeste(r, ctl)
    verifier_manifeste(r, ctl)
    csv = r / "labo" / "AAAUSDT_1d.csv"
    ancien = csv.read_text()
    csv.write_text(ancien.replace("50.5", "51.5", 1))
    for appel in (lambda: verifier_manifeste(r, ctl),
                  lambda: charger(r, symboles=["AAAUSDT"], univers_controle_path=ctl, strict=False)):
        with pytest.raises(ManifesteError, match="différent"):
            appel()
    csv.write_text(ancien)
    verifier_manifeste(r, ctl)
    (r / "intrus.txt").write_text("x")
    with pytest.raises(ManifesteError, match="non listés"):
        verifier_manifeste(r, ctl)
    (r / "intrus.txt").unlink()
    csv.unlink()
    with pytest.raises(ManifesteError, match="manquants"):
        verifier_manifeste(r, ctl)
    # la liste de contrôle figée fait partie des données
    csv.write_text(ancien)
    ctl.write_text(json.dumps({"symboles": ["AUTRE"]}))
    with pytest.raises(ManifesteError, match="univers_controle"):
        verifier_manifeste(r, ctl)


def test_chargeur_sans_manifeste_refuse(tmp_path):
    with pytest.raises(ManifesteError):
        charger(racine_factice(tmp_path), symboles=["AAAUSDT"], strict=False)


# ------------------------------------------------------------------- construire_donnees (hors ligne)

def test_construire_donnees_complet_et_reprenable(tmp_path, monkeypatch):
    crit = dataclasses.replace(charger_criteres(), univers=("AAAUSDT",), controle_taille=2)
    monkeypatch.setattr(mod_construire, "charger_criteres", lambda: crit)
    monkeypatch.setattr(mod_controle, "charger_criteres", lambda: crit)
    labo_factice(tmp_path / "labo_src")
    srv = Serveur()
    for src, sym, nom in [("futures/um/monthly/fundingRate", "AAAUSDT", "fundingRate"),
                          ("futures/um/monthly/klines", "AAAUSDT", "1h")]:
        for mois in ("2026-05", "2026-06", "2026-07"):  # 2026-07 est listé mais ne doit jamais être demandé
            sous = "" if nom == "fundingRate" else "/1h"
            contenu = (lignes_funding([ms(f"{mois}-01T00:00:00")]) if nom == "fundingRate"
                       else lignes_barres(f"{mois}-01T00:00:00", 3, 3600))
            srv.ajouter(f"{src}/{sym}/{sym}-{nom}-{mois}.zip".replace(f"/{sym}/", f"/{sym}{sous}/", 1),
                        zip_de("x.zip", contenu))
    for i in range(3):
        sym = f"K{i}USDT"
        for mois in ("2020-01", "2020-02"):
            n = 31 if mois == "2020-01" else 29
            srv.ajouter(f"spot/monthly/klines/{sym}/1d/{sym}-1d-{mois}.zip",
                        zip_de("x.zip", lignes_barres(f"{mois}-01T00:00:00", n, 86400, qv=10.0 + i)))
    racine = tmp_path / "racine"
    ctl = tmp_path / "univers_controle.json"
    with srv.client() as c:
        doc = construire_donnees(racine, labo_src=tmp_path / "labo_src", univers_controle_path=ctl, client=c)
        assert json.loads(ctl.read_text())["symboles"] == ["K2USDT", "K1USDT"]
        assert not any("2026-07" in u for u in srv.requetes)
        n_zips = srv.n_zips
        verifier_manifeste(racine, ctl)
        assert (racine / "MANIFESTE.json").exists() and doc["univers_controle_sha256"]
        # reprise : plus aucun zip redemandé
        doc2 = construire_donnees(racine, labo_src=tmp_path / "labo_src", univers_controle_path=ctl, client=c)
        assert srv.n_zips == n_zips
        assert doc2["fichiers"] == doc["fichiers"]


# ------------------------------------------------------------------------------------------- réseau

@pytest.mark.reseau
def test_reseau_funding_btcusdt_2024_01(tmp_path):
    mod_tel.PAUSE_S = 1.0
    p = telecharger_mois("perp_funding", "BTCUSDT", 2024, 1, tmp_path)
    assert p.exists() and (p.parent / (p.name + ".CHECKSUM")).exists()
    f = lire_funding_zip(p.read_bytes(), p.name)
    assert len(f) == 93  # 31 jours x 3 échéances
    assert f.index[0].year == 2024 and f.index[-1] < pd.Timestamp("2024-02-01")
    assert (f["connue_a"] <= COUPURE_TS).all()


def test_trous_de_l_echauffement_remplis_sans_seuil_ceux_de_la_fenetre_refuses():
    from recherche.donnees.chargeur import _regulariser

    crit = charger_criteres()

    def serie(debut, n, saute):
        idx = pd.date_range(debut, periods=n, freq="D").delete(list(saute))
        return pd.DataFrame({c: 1.0 for c in ["open", "high", "low", "close", "volume", "quote_volume",
                                              "trades", "taker_buy_base", "taker_buy_quote"]}, index=idx)

    out = _regulariser(serie("2019-12-01", 60, {3, 4, 5}), 86400, "w", crit, None)  # trou en 2019 : rempli
    assert int(out["rempli"].sum()) == 3 and len(out) == 60
    with pytest.raises(DonneesError, match="trou"):
        _regulariser(serie("2019-12-01", 60, {40}), 86400, "w", crit, None)  # trou en 2020 : refusé
