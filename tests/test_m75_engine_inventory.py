"""M75: the engine inventory stays current; the last hydraulics function without a test gets one.

References are hand arithmetic here (oilfield units): annular volume
(Dh^2 - Dp^2) / 1029.4 bbl/ft times length; bit hydraulics
dP = Q^2 MW / (10858 TFA^2), HHP = Q dP / 1714, Vn = Q / (3.117 TFA).
"""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pytest

from core.hydraulics_engine import AdvancedHydraulicsEngine as engine

ROOT = Path(__file__).resolve().parents[1]


def test_engine_inventory_document_is_current():
    result = subprocess.run([sys.executable, "tools/quality/engine_inventory.py", "--check"], cwd=ROOT,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_engine_and_hydraulics_function_is_named_by_a_test():
    sys.path.insert(0, str(ROOT / "tools" / "quality"))
    import engine_inventory as inventory

    tests = inventory._tests()
    assert len(inventory.engines()) >= 9
    missing = [r["symbol"] for r in inventory.engines() + inventory.hydraulics()
               if not inventory._referencing(r["symbol"].split(".")[-1], tests)]
    assert missing == []


def test_annular_volume_matches_hand_arithmetic_and_rejects_bad_geometry():
    assert engine.calc_annular_volume(8.5, 5.0, 1000.0) == pytest.approx((72.25 - 25.0) / 1029.4 * 1000.0, rel=1e-12)
    assert engine.calc_annular_volume(8.5, 5.0, 1.0) == pytest.approx(engine.calc_annular_capacity_bbl_ft(8.5, 5.0))
    for args in [(5.0, 5.0, 10.0), (8.5, 0.0, 10.0), (8.5, 5.0, 0.0), (4.0, 5.0, 10.0)]:
        with pytest.raises(ValueError):
            engine.calc_annular_volume(*args)
    for bad in (math.nan, math.inf):
        with pytest.raises(ValueError):
            engine.calc_annular_volume(8.5, 5.0, bad)


def test_bit_hydraulics_chain_matches_hand_arithmetic():
    q, mw, tfa = 500.0, 10.0, 0.5
    dp = q * q * mw / (10858.0 * tfa * tfa)                 # 920.98 psi
    assert engine.calc_bit_pressure_drop(q, mw, tfa) == pytest.approx(dp, rel=1e-12)
    assert engine.calc_tfa_from_pressure_drop(q, mw, dp) == pytest.approx(tfa, rel=1e-12)
    assert engine.calc_bit_hhp(q, dp) == pytest.approx(q * dp / 1714.0, rel=1e-12)
    assert engine.calc_jet_velocity(q, tfa) == pytest.approx(q / (3.117 * tfa), rel=1e-12)
    assert engine.calc_hsi(engine.calc_bit_hhp(q, dp), 8.5) == pytest.approx(
        q * dp / 1714.0 / (math.pi / 4 * 8.5 ** 2), rel=1e-12)
