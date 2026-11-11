import dataclasses
import hashlib
import tomllib
from datetime import UTC, datetime

import pytest

from recherche.config import (
    ARENE_TOML,
    COUPURE_TS,
    CRITERES_PATH,
    CriteresError,
    charger_criteres,
)


def test_coupure_est_le_2026_07_01_utc():
    assert COUPURE_TS == int(datetime(2026, 7, 1, tzinfo=UTC).timestamp())


def test_charge_criteres_reels():
    c = charger_criteres()
    assert c.sha256 == hashlib.sha256(CRITERES_PATH.read_bytes()).hexdigest()
    assert c.version == "recherche-v1"
    assert c.coupure_ts == COUPURE_TS
    assert len(c.univers) == 15 and set(c.univers_arene) <= set(c.univers)
    assert c.controle_taille == 20
    assert (c.n_dsr, c.plafond_total, c.plafond_vague_1) == (726, 600, 120)
    assert c.portes.C6_drawdown_max.directionnel == 0.45
    assert c.portes["C8_directionnel"]["replications"] == 5000
    assert c.donnees.tolerances.trous_1h_consecutifs_max == 6


def test_couts_en_points_de_base_entiers():
    c = charger_criteres()
    assert (c.cout_spot_bp, c.cout_perp_bp, c.stress_multiplicateur) == (60, 10, 2)
    assert all(type(v) is int for v in (c.cout_spot_bp, c.cout_perp_bp, c.stress_multiplicateur))
    assert c.cout_bp("spot") == 60 and c.cout_bp("perp", stress=True) == 20


def test_couts_coherents_avec_arene_toml():
    arene = tomllib.loads(ARENE_TOML.read_text())
    c = charger_criteres()
    assert c.cout_spot_bp == arene["taker_fee_bp"] + arene["slippage_bp"] + 5


def test_criteres_gele():
    c = charger_criteres()
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.cout_spot_bp = 1
    with pytest.raises(AttributeError):
        c.couts_bp.spot_par_rotation = 1
    with pytest.raises(TypeError):
        c.couts_bp["spot_par_rotation"] = 1


def test_cout_flottant_refuse(tmp_path):
    texte = CRITERES_PATH.read_text().replace("spot_par_rotation: 60", "spot_par_rotation: 60.5")
    p = tmp_path / "c.yaml"
    p.write_text(texte)
    with pytest.raises(CriteresError):
        charger_criteres(p)


def test_coupure_modifiee_refusee(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(CRITERES_PATH.read_text().replace("2026-07-01T00:00:00Z", "2026-08-01T00:00:00Z", 1))
    with pytest.raises(CriteresError):
        charger_criteres(p)


def test_cle_manquante(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("version: x\n")
    with pytest.raises(CriteresError):
        charger_criteres(p)
