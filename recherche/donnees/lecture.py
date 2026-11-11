"""Lecture des zips Binance (bougies et funding) vers des DataFrames à index UTC naïf (ns)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

COLONNES_BARRE = ["open", "high", "low", "close", "volume", "quote_volume", "trades",
                  "taker_buy_base", "taker_buy_quote"]


class LectureError(Exception):
    pass


def _csv_du_zip(octets: bytes, nom: str) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(octets)) as z:
        noms = [n for n in z.namelist() if n.endswith(".csv")]
        if len(noms) != 1:
            raise LectureError(f"{nom} : un seul CSV attendu dans le zip, trouvé {noms}")
        brut = z.read(noms[0])
    # En-tête présent selon les années : détecté par la nature de la première cellule.
    premiere = brut.split(b"\n", 1)[0].split(b",", 1)[0].strip()
    entete = 0 if premiere.lstrip(b"-").replace(b".", b"").isdigit() else 1
    df = pd.read_csv(io.BytesIO(brut), header=None, skiprows=entete)
    if df.empty:
        raise LectureError(f"{nom} : CSV vide")
    return df


def _ms(serie: pd.Series) -> pd.Series:
    """Horodatages en millisecondes ; les archives spot passent en microsecondes à partir de 2025."""
    s = serie.astype("int64")
    return s.where(s < 10**14, s // 1000)


def index_utc(ms: pd.Series) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(ms.to_numpy(), unit="ms")).as_unit("ns")


def lire_barres_zip(octets: bytes, nom: str = "?") -> pd.DataFrame:
    df = _csv_du_zip(octets, nom)
    if df.shape[1] < 11:
        raise LectureError(f"{nom} : {df.shape[1]} colonnes, 11 au moins attendues")
    out = pd.DataFrame({
        "open": df[1], "high": df[2], "low": df[3], "close": df[4], "volume": df[5],
        "quote_volume": df[7], "trades": df[8], "taker_buy_base": df[9], "taker_buy_quote": df[10],
    }).astype("float64")
    out.index = index_utc(_ms(df[0]))
    out.index.name = "open_time"
    return out


def lire_funding_zip(octets: bytes, nom: str = "?") -> pd.DataFrame:
    df = _csv_du_zip(octets, nom)
    if df.shape[1] < 2:
        raise LectureError(f"{nom} : colonnes insuffisantes")
    ms = _ms(df[0])
    out = pd.DataFrame({"taux": df[df.shape[1] - 1].astype("float64").to_numpy()},
                       index=index_utc(ms))
    out.index.name = "funding_time"
    out["connue_a"] = (ms.to_numpy() // 1000 + 1).astype("int64")  # fundingTime + 1 s
    return out


def lire_zips(chemins: list[Path], funding: bool = False) -> pd.DataFrame:
    """Concatène des zips mensuels, trie, déduplique (garde la première occurrence)."""
    morceaux = []
    for p in sorted(chemins):
        octets = Path(p).read_bytes()
        morceaux.append(lire_funding_zip(octets, Path(p).name) if funding
                        else lire_barres_zip(octets, Path(p).name))
    if not morceaux:
        raise LectureError("aucun fichier")
    df = pd.concat(morceaux).sort_index()
    return df[~df.index.duplicated(keep="first")]
