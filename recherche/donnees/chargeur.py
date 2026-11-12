"""Chargeur unique des données de recherche : seul point d'entrée vers `var/recherche/donnees/`.

Garanties : manifeste vérifié (sha256 de chaque fichier) ; `CoupureError` si une ligne brute a
`connue_a > COUPURE_TS` (jamais de troncature silencieuse) ; tolérances du protocole appliquées.

Format des tables (une par symbole) : index `DatetimeIndex` UTC naïf (ns) = ouverture de la barre ;
colonnes float64 `open, high, low, close, volume, quote_volume, trades, taker_buy_base, taker_buy_quote`,
`rempli` (bool, barre synthétique), `connue_a` (int64, secondes UTC = ouverture + durée).
Funding : index = `fundingTime`, colonnes `taux` (float64), `connue_a` (int64 = fundingTime + 1 s).
Univers de contrôle : `controle_1d` (toujours présent), `controle_1h` (spot 1 h), `controle_perp_1h` et
`controle_funding` (None si le symbole n'a pas d'archives : pas de perp, ou pas de spot 1 h). Un symbole
délisté avant 2026-06 s'arrête simplement (aucune fin imposée).
Remplissage (dans la tolérance ; échauffement 2018-2019 sans seuil) : open = high = low = close = dernier close, volume nul,
rendement nul, `rempli` vrai. Chaque table commence à la première barre du symbole (pas de NaN avant la
cotation : l'éligibilité se lit sur l'index).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from recherche.config import COUPURE_TS, CoupureError, Criteres, charger_criteres
from recherche.donnees.lecture import COLONNES_BARRE, lire_zips
from recherche.donnees.manifeste import UNIVERS_CONTROLE_PATH, sha256_manifeste, verifier_manifeste


class DonneesError(Exception):
    """Données incomplètes ou hors tolérance."""


@dataclass(frozen=True)
class Donnees:
    racine: Path
    manifeste_sha256: str
    univers: tuple[str, ...]
    controle: tuple[str, ...]
    spot_1d: dict[str, pd.DataFrame]
    spot_1h: dict[str, pd.DataFrame]
    perp_1h: dict[str, pd.DataFrame | None]
    funding: dict[str, pd.DataFrame | None]
    controle_1d: dict[str, pd.DataFrame]
    controle_1h: dict[str, pd.DataFrame | None]
    controle_perp_1h: dict[str, pd.DataFrame | None]
    controle_funding: dict[str, pd.DataFrame | None]
    # Erratum 3 : séries 1 h hors tolérance raccourcies (nom -> première ouverture gardée, s UTC).
    debuts_coupes: dict[str, int] = field(default_factory=dict)


def _secondes(idx: pd.DatetimeIndex) -> np.ndarray:
    return idx.as_unit("ns").asi8 // 1_000_000_000


def verifier_coupure(connue_a: np.ndarray, nom: str) -> None:
    """Lève `CoupureError` si une ligne est connue strictement après la coupure."""
    if len(connue_a) and int(connue_a.max()) > COUPURE_TS:
        n = int((connue_a > COUPURE_TS).sum())
        raise CoupureError(f"{nom} : {n} ligne(s) avec connue_a > coupure {COUPURE_TS} "
                           f"(max {int(connue_a.max())})")


def _debut_admissible(absent: pd.Series, part_max: float, suite_max: int) -> pd.Timestamp | None:
    """Erratum 3 : premier début (juste après une suite de barres manquantes) à partir duquel la série
    respecte les tolérances 1 h ; None si aucun. `absent` est la grille de la fenêtre d'évaluation."""
    a = absent.to_numpy()
    n = len(a)
    debuts = [0] + [i + 1 for i in range(n - 1) if a[i] and not a[i + 1]]
    for d in debuts:
        x = a[d:]
        if not len(x):
            break
        runs = pd.Series(x).groupby((~pd.Series(x)).cumsum()).sum()
        if int(x.sum()) <= part_max * len(x) and int(runs.max()) <= suite_max:
            return absent.index[d]
    return None


def _regulariser(df: pd.DataFrame, duree_s: int, nom: str, crit: Criteres, fin_attendue: int | None,
                 coupes: dict[str, int] | None = None) -> pd.DataFrame:
    """Contrôle coupure, trous et fin ; remplit les trous 1 h dans la tolérance ; ajoute `connue_a`."""
    if df.empty:
        raise DonneesError(f"{nom} : table vide")
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise DonneesError(f"{nom} : index non strictement croissant")
    ouverture = _secondes(df.index)
    verifier_coupure(ouverture + duree_s, nom)
    if fin_attendue is not None and int(ouverture[-1]) + duree_s != fin_attendue:
        raise DonneesError(f"{nom} : dernière barre fermée à {int(ouverture[-1]) + duree_s}, "
                           f"{fin_attendue} attendu")
    tol = crit.donnees.tolerances
    grille = pd.date_range(df.index[0], df.index[-1], freq=pd.Timedelta(seconds=duree_s), unit="ns")
    df = df.assign(rempli=False)
    if len(grille) > len(df):
        # Les tolérances du protocole s'appliquent à la fenêtre d'évaluation (>= 2020-01-01), après la
        # première cotation ; les trous de l'échauffement sont remplis sans seuil (et signalés par `rempli`).
        absent = pd.Series(~grille.isin(df.index), index=grille)
        fen = absent[absent.index >= pd.Timestamp(crit.donnees.fenetre_evaluation.debut)]
        n_fen, suite = int(fen.sum()), int(fen.groupby((~fen).cumsum()).sum().max()) if len(fen) else 0
        if duree_s >= 86400 and n_fen > tol.trous_1d:
            raise DonneesError(f"{nom} : {n_fen} trou(s) en 1 j dans la fenêtre (tolérance {tol.trous_1d})")
        hors = duree_s < 86400 and (n_fen > tol.trous_1h_part_max * len(fen)
                                    or suite > tol.trous_1h_consecutifs_max)
        if hors and coupes is not None:
            debut = _debut_admissible(fen, tol.trous_1h_part_max, tol.trous_1h_consecutifs_max)
            if debut is not None:
                coupes[nom] = int(_secondes(pd.DatetimeIndex([debut]))[0])
                return _regulariser(df.drop(columns="rempli")[df.index >= debut], duree_s, nom, crit,
                                    fin_attendue, None)
        if hors:
            raise DonneesError(f"{nom} : {n_fen} barres manquantes sur {len(fen)}, plus longue suite {suite} "
                               f"(tolérance {tol.trous_1h_part_max:.4f}, suite <= "
                               f"{tol.trous_1h_consecutifs_max})")
        df = df.reindex(grille)
        df["rempli"] = df["rempli"].astype("boolean").fillna(True).astype(bool)
        df["close"] = df["close"].ffill()
        for c in ("open", "high", "low"):
            df[c] = df[c].fillna(df["close"])
        for c in ("volume", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote"):
            df[c] = df[c].fillna(0.0)
        df.index.name = "open_time"
    df["connue_a"] = _secondes(df.index) + duree_s
    return df[COLONNES_BARRE + ["rempli", "connue_a"]]


def _csv_labo(p: Path) -> pd.DataFrame:
    df = pd.read_csv(p)
    idx = pd.to_datetime(df.pop("open_time_utc"), utc=True).dt.tz_localize(None)
    out = df[COLONNES_BARRE].astype("float64")
    out.index = pd.DatetimeIndex(idx).as_unit("ns")
    out.index.name = "open_time"
    return out.sort_index()


def _zips(racine: Path, source: str, symbole: str) -> list[Path]:
    d = racine / "brut" / source / symbole
    return sorted(d.glob("*.zip")) if d.is_dir() else []


def charger(racine: Path | str, criteres: Criteres | None = None, *, symboles: list[str] | None = None,
            controle: list[str] | None = None, univers_controle_path: Path | str | None = None,
            strict: bool = True) -> Donnees:
    """Charge et valide toutes les données sous `racine` (défaut du projet : `var/recherche/donnees`).

    `symboles`/`controle` : surcharges pour les tests (défaut : univers des critères et liste figée de
    `recherche/univers_controle.json`). `strict` : exige que les séries spot de l'univers se terminent
    exactement à la coupure (2026-06-30 inclus) ; les tests de petites fixtures passent `strict=False`.
    """
    racine = Path(racine)
    crit = criteres or charger_criteres()
    ctl_path = Path(univers_controle_path) if univers_controle_path else UNIVERS_CONTROLE_PATH
    verifier_manifeste(racine, ctl_path)
    univers = tuple(symboles if symboles is not None else crit.univers)
    if controle is None:
        controle = json.loads(ctl_path.read_text())["symboles"] if ctl_path.is_file() else []
    controle = tuple(controle)
    fin = COUPURE_TS if strict else None
    spot_1d, spot_1h, perp_1h, funding, ctl = {}, {}, {}, {}, {}
    ctl_1h, ctl_perp, ctl_fund = {}, {}, {}
    coupes: dict[str, int] = {}

    def perp(s: str, nom: str):
        kz, fz = _zips(racine, "perp_klines_1h", s), _zips(racine, "perp_funding", s)
        if bool(kz) != bool(fz):
            raise DonneesError(f"{s} : perp klines et funding doivent exister ensemble")
        if not kz:
            return None, None
        f = lire_zips(fz, funding=True)
        verifier_coupure(f["connue_a"].to_numpy(), f"{nom} funding")
        k = _regulariser(lire_zips(kz), 3600, f"{nom} perp 1h", crit, None, coupes)
        if f"{nom} perp 1h" in coupes:  # le funding suit le début raccourci des barres perp
            f = f[f["connue_a"].to_numpy() > coupes[f"{nom} perp 1h"]]
        return k, f

    for s in univers:
        for intervalle, duree, cible in (("1d", 86400, spot_1d), ("1h", 3600, spot_1h)):
            p = racine / "labo" / f"{s}_{intervalle}.csv"
            if not p.is_file():
                raise DonneesError(f"{p} absent")
            cible[s] = _regulariser(_csv_labo(p), duree, f"{s} spot {intervalle}", crit, fin)
        perp_1h[s], funding[s] = perp(s, s)
    for s in controle:
        z = _zips(racine, "spot_klines_1d", s)
        if not z:
            raise DonneesError(f"{s} : aucune archive de contrôle sous {racine / 'brut'}")
        ctl[s] = _regulariser(lire_zips(z), 86400, f"{s} contrôle 1d", crit, None)
        z1 = _zips(racine, "spot_klines_1h", s)
        ctl_1h[s] = _regulariser(lire_zips(z1), 3600, f"{s} contrôle 1h", crit, None,
                                  coupes) if z1 else None
        ctl_perp[s], ctl_fund[s] = perp(s, f"{s} contrôle")
    return Donnees(racine=racine, manifeste_sha256=sha256_manifeste(racine), univers=univers,
                   controle=controle, spot_1d=spot_1d, spot_1h=spot_1h, perp_1h=perp_1h,
                   funding=funding, controle_1d=ctl, controle_1h=ctl_1h,
                   controle_perp_1h=ctl_perp, controle_funding=ctl_fund, debuts_coupes=coupes)
