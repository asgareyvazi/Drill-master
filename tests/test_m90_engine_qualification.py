"""M90: independent goldens for engine entry points that had none (closed forms written out here).

Covered elsewhere (not repeated): minimum curvature, kill sheet, bit hydraulics
(test_engineering_independent_golden), casing VME (test_casing_vme_independent), vertical
soft-string, weight-up, free point (test_engineering_ground_truth), Teale MSE / W13 contracts
(test_m87), cement annulus (test_m74, test_m89).
"""
from __future__ import annotations

import math

import pytest

from core.engineering.engines.casing import CasingEngine
from core.engineering.engines.cement import CementEngine
from core.engineering.engines.fishing import FishingEngine
from core.engineering.engines.mud_volume import MudVolumeEngine
from core.engineering.engines.torque_drag import TorqueDragEngine

FT_PER_M = 3.28084


# ---- mud: dilution by material balance ---------------------------------------------------------
def test_dilution_material_balance():
    # 500 bbl of 12.0 ppg diluted with 8.33 ppg water to 11.0 ppg: V_w = 500 (12-11)/(11-8.33)
    r = MudVolumeEngine.dilution(12.0, 11.0, 500.0, 8.33)
    water = 500.0 * 1.0 / (11.0 - 8.33)
    assert r.success and r.values["water_required_bbl"] == pytest.approx(water, abs=5e-4)
    # mass check: (500*12 + V_w*8.33) / (500 + V_w) = 11
    assert (500 * 12.0 + water * 8.33) / (500 + water) == pytest.approx(11.0, rel=1e-12)
    assert r.values["final_volume_bbl"] == pytest.approx(500.0 + water, abs=5e-4)
    for bad in ((11.0, 12.0, 500.0, 8.33), (12.0, 8.0, 500.0, 8.33), (12.0, 11.0, 0.0, 8.33)):
        assert not MudVolumeEngine.dilution(*bad).success


# ---- casing: pipe-body yield --------------------------------------------------------------------
def test_pipe_body_yield_from_the_annular_area():
    # 9-5/8 in 47 ppf, 8.681 in ID, 80 ksi: A = pi/4 (9.625^2 - 8.681^2) = 13.572 in^2 -> 1,085,800 lbf
    area = math.pi / 4.0 * (9.625 ** 2 - 8.681 ** 2)
    r = CasingEngine.tensile(9.625, 8.681, 80000.0, design_factor=1.6)
    assert r.success and r.values["cross_section_in2"] == pytest.approx(area, abs=5e-5)
    assert r.values["pipe_body_yield_lbf"] == pytest.approx(area * 80000.0, abs=0.5)
    assert r.values["working_tension_lbf"] == pytest.approx(area * 80000.0 / 1.6, abs=0.5)
    assert area == pytest.approx(13.572, abs=5e-4)
    for bad in ((9.625, 9.7, 80000.0), (9.625, 0.0, 80000.0), (0.0, 8.0, 80000.0)):
        assert not CasingEngine.tensile(*bad).success


# ---- cement: top of cement from a slurry volume -------------------------------------------------
def test_toc_from_volume_with_excess():
    # 12.25 in hole, 9.625 in casing: cap = (12.25^2 - 9.625^2)/1029.4 bbl/ft; 30 % excess; 200 bbl
    cap = (12.25 ** 2 - 9.625 ** 2) / 1029.4 * 1.3
    r = CementEngine.toc_from_volume(12.25, 9.625, 200.0, 30.0, 8000.0)
    assert r.success
    assert r.values["cement_height_ft"] == pytest.approx(200.0 / cap, abs=0.005)
    assert r.values["toc_md_ft"] == pytest.approx(8000.0 - 200.0 / cap, abs=0.005)
    assert not CementEngine.toc_from_volume(9.0, 9.625, 200.0, 30.0, 8000.0).success
    assert not CementEngine.toc_from_volume(12.25, 9.625, -1.0, 30.0, 8000.0).success


# ---- fishing: overshot clearance band -----------------------------------------------------------
@pytest.mark.parametrize("fish, overshot, compatible", [
    (6.5, 6.625, True), (6.5, 6.5, False), (6.5, 7.0, False), (6.5, 6.999, True), (6.5, 6.4, False)])
def test_overshot_clearance_band(fish, overshot, compatible):
    r = FishingEngine.overshot_fit(fish, overshot)
    assert r.success and r.values["clearance_in"] == pytest.approx(overshot - fish, abs=5e-4)
    assert r.values["compatible"] is compatible


# ---- torque & drag: straight inclined tangent (no curvature) -----------------------------------
@pytest.mark.parametrize("inc", [30.0, 60.0])
def test_soft_string_on_a_straight_inclined_tangent(inc):
    # On a straight tangent the normal force per length is w*BF*sin(theta): pickup / slack-off add /
    # subtract mu*N to the axial component w*BF*cos(theta); rotating removes axial friction.
    length_m, ppf, mw, mu = 1000.0, 19.5, 10.0, 0.25
    survey = [{"md": 0.0, "inc": inc, "azi": 45.0}, {"md": length_m, "inc": inc, "azi": 45.0}]
    bha = [{"length": length_m, "weight": ppf, "od": 5.0, "id": 4.276}]
    r = TorqueDragEngine.calculate(survey, bha, mud_density_ppg=mw, friction_factor=mu)
    assert r.success, r.error
    w = length_m * FT_PER_M * ppf * (1.0 - mw / 65.5)                      # buoyed weight, lbf
    th = math.radians(inc)
    assert r.values["hookload_rotating"] == pytest.approx(w * math.cos(th) / 1000.0, abs=0.01)
    assert r.values["hookload_pickup"] == pytest.approx(w * (math.cos(th) + mu * math.sin(th)) / 1000.0, abs=0.01)
    assert r.values["hookload_slackoff"] == pytest.approx(w * (math.cos(th) - mu * math.sin(th)) / 1000.0,
                                                          abs=0.01)
    # rotating torque: mu * N * r with r = OD/2 (ft)
    torque = mu * w * math.sin(th) * (5.0 / 2.0 / 12.0)
    assert r.values["surface_torque_rotating_ft_lbf"] == pytest.approx(torque, rel=2e-3)
