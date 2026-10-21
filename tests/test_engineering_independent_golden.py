"""Independent golden values for MCM trajectory, kill sheet, well control and bit hydraulics.

M43 closure, Phase 5. Every expected value here is derived WITHOUT the
implementation's formula or constants:

* MCM: stations are sampled from an explicit 3-D circle (centre-free
  parametrisation P(t) = R sin t T1 + R (1 - cos t) N). Minimum curvature is
  exact for circular arcs, so the engine must reproduce the chord; the test
  never uses the ratio-factor formula.
* Hydrostatics: 1 ppg x 1 ft = (231 in^3/gal)^-1 x 12 in = 0.0519481 psi/ft.
  The engine uses the oilfield rounding 0.052 (0.10 % high), so tolerances
  are stated relative to the exact physics, not to the rounding.
* Capacities: pi/4 d^2 x 12 in / (42 gal x 231 in^3) bbl/ft, not 1029.4.
* Bit hydraulics: Bernoulli with discharge coefficient Cd = 0.95 in SI units;
  jet velocity, hydraulic horsepower and impact force from unit definitions.

Synthetic inputs only. Screening calculations; nothing here is a field
validation.
"""

from __future__ import annotations

import math

import pytest

from core.engineering.engines.trajectory import TrajectoryCalculator
from core.engineering.engines.well_control import WellControlEngine
from core.engineering.well_control_kill_sheet import WellControlKillSheetInputs, compute_kill_sheet
from core.hydraulics_engine import AdvancedHydraulicsEngine as H

PSI_PER_PPG_FT_EXACT = 12.0 / 231.0  # lb/gal over 1 ft of column, in psi
IN3_PER_BBL = 42.0 * 231.0
GAL_PER_FT3 = 1728.0 / 231.0
G_FT_S2 = 32.174
PA_PER_PSI = 6894.757293168
KG_M3_PER_PPG = 119.826427
M3S_PER_GPM = 3.785411784e-3 / 60.0
M2_PER_IN2 = 0.0254 ** 2
ROUNDING = 0.052 / PSI_PER_PPG_FT_EXACT - 1.0  # 0.10 %: oilfield constant vs physics
# The published field constants are rounded: the exact Cd = 0.95 Bernoulli
# constant is 10860.6 (engine 10858, 0.024 % off) and 60 x 32.174 = 1930.44
# (engine 1930, 0.023 % off). 0.05 % separates that rounding from a formula
# error (dropping Cd alone is a 10.8 % change).
FIELD_CONSTANT_ROUNDING = 5e-4


def _capacity_bbl_ft(diameter_in: float, inner_in: float = 0.0) -> float:
    return math.pi / 4.0 * (diameter_in ** 2 - inner_in ** 2) * 12.0 / IN3_PER_BBL


# ---------------------------------------------------------------- MCM

def _unit(inc_deg, azi_deg):
    i, a = math.radians(inc_deg), math.radians(azi_deg)
    return (math.sin(i) * math.cos(a), math.sin(i) * math.sin(a), math.cos(i))  # N, E, down


def _circle_stations(inc1, azi1, toward, radius, angles):
    """Stations on a 3-D circle tangent to (inc1, azi1); returns surveys and exact offsets."""
    t1 = _unit(inc1, azi1)
    dot = sum(a * b for a, b in zip(toward, t1))
    n = [a - dot * b for a, b in zip(toward, t1)]
    norm = math.sqrt(sum(c * c for c in n))
    n = [c / norm for c in n]
    surveys, offsets = [], []
    for t in angles:
        tangent = [math.cos(t) * a + math.sin(t) * b for a, b in zip(t1, n)]
        inc = math.degrees(math.acos(max(-1.0, min(1.0, tangent[2]))))
        azi = math.degrees(math.atan2(tangent[1], tangent[0])) % 360.0
        surveys.append({"md": 1000.0 + radius * t, "inc": inc, "azi": azi})
        offsets.append([radius * math.sin(t) * a + radius * (1 - math.cos(t)) * b for a, b in zip(t1, n)])
    return surveys, offsets


@pytest.mark.parametrize("inc1,azi1,toward", [
    (20.0, 30.0, (0.3, 0.9, 0.2)),     # build and turn
    (45.0, 350.0, (0.0, 0.0, -1.0)),   # drop, crossing north
    (85.0, 120.0, (0.0, 1.0, 0.0)),    # near-horizontal turn
])
def test_mcm_reproduces_an_explicit_circular_arc(inc1, azi1, toward):
    radius, angles = 600.0, [0.0, 0.1, 0.25, 0.4]
    surveys, offsets = _circle_stations(inc1, azi1, toward, radius, angles)
    points = TrajectoryCalculator.calculate(surveys, dls_unit="deg/30m")
    base = points[0]
    for point, (north, east, down) in zip(points[1:], offsets[1:]):
        assert point["north"] - base["north"] == pytest.approx(north, abs=1e-6)
        assert point["east"] - base["east"] == pytest.approx(east, abs=1e-6)
        assert point["tvd"] - base["tvd"] == pytest.approx(down, abs=1e-6)
    expected_dls = math.degrees(1.0 / radius) * 30.0  # constant curvature, deg/30 m
    for point in points[1:]:
        assert point["dls"] == pytest.approx(expected_dls, rel=1e-3)


def test_mcm_straight_and_vertical_singularities():
    straight = TrajectoryCalculator.calculate([{"md": 500.0, "inc": 30.0, "azi": 60.0},
                                               {"md": 800.0, "inc": 30.0, "azi": 60.0}])
    t = _unit(30.0, 60.0)
    assert straight[1]["north"] - straight[0]["north"] == pytest.approx(300.0 * t[0], abs=1e-9)
    assert straight[1]["tvd"] - straight[0]["tvd"] == pytest.approx(300.0 * t[2], abs=1e-9)
    assert straight[1]["dls"] == pytest.approx(0.0, abs=1e-12)
    vertical = TrajectoryCalculator.calculate([{"md": 0.0, "inc": 0.0, "azi": 0.0},
                                               {"md": 300.0, "inc": 0.0, "azi": 270.0}])
    assert vertical[1]["tvd"] == pytest.approx(300.0, abs=1e-9)
    assert vertical[1]["north"] == pytest.approx(0.0, abs=1e-9) and vertical[1]["east"] == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------- well control

def test_kill_mud_weight_icp_fcp_maasp_against_hand_physics():
    mw, sidpp, tvd, scr, shoe, frac_emw = 10.0, 520.0, 10_000.0, 800.0, 5_000.0, 14.0
    kill_exact = mw + sidpp / (PSI_PER_PPG_FT_EXACT * tvd)  # 11.0010 ppg
    kill = WellControlEngine.calculate_kill_mw(mw, sidpp, tvd)
    assert kill == pytest.approx(kill_exact, abs=0.002)
    assert WellControlEngine.calculate_icp(scr, sidpp) == 1320.0  # SCR + SIDPP, no constant involved
    assert WellControlEngine.calculate_fcp(scr, kill, mw) == pytest.approx(scr * kill_exact / mw, abs=0.2)
    maasp_exact = (frac_emw - mw) * PSI_PER_PPG_FT_EXACT * shoe  # 1038.96 psi
    maasp = WellControlEngine.calculate_maasp(max_allowable_mw_ppg=frac_emw, current_mw_ppg=mw, shoe_tvd_ft=shoe)
    assert maasp == pytest.approx(maasp_exact, rel=ROUNDING + 1e-4)


def test_kill_sheet_volumes_strokes_and_pressures_for_a_vertical_well():
    inputs = WellControlKillSheetInputs.from_dict({
        "tvd_ft": 10_000.0, "md_ft": 10_000.0, "shoe_tvd_ft": 5_000.0, "shoe_md_ft": 5_000.0,
        "hole_size_in": 8.5, "casing_id_in": 8.835, "mw_ppg": 10.0, "frac_gradient_psi_ft": 0.75,
        "sidpp_psi": 520.0, "sicp_psi": 700.0, "pit_gain_bbl": 10.0,
        "scr1_psi": 800.0, "scr1_spm": 30.0, "scr2_psi": 1300.0, "scr2_spm": 40.0,
        "pump_output_bbl_stk": 0.1, "method": "Wait & Weight", "well_type": "vertical",
        "pipes": [{"type": "Drill Pipe", "od_in": 5.0, "id_in": 4.276, "length_ft": 10_000.0}],
    })
    result = compute_kill_sheet(inputs)
    assert result.success, result.error
    string_bbl = _capacity_bbl_ft(4.276) * 10_000.0                      # 177.6 bbl
    annulus_bbl = _capacity_bbl_ft(8.835, 5.0) * 5_000.0 + _capacity_bbl_ft(8.5, 5.0) * 5_000.0  # 487.2 bbl
    assert result.total_string_vol_bbl == pytest.approx(string_bbl, rel=1e-3)
    assert result.total_ann_vol_bbl == pytest.approx(annulus_bbl, rel=1e-3)
    assert result.stk_to_bit == pytest.approx(string_bbl / 0.1, rel=1e-3)
    assert result.stk_annular == pytest.approx(annulus_bbl / 0.1, rel=1e-3)
    kill_exact = 10.0 + 520.0 / (PSI_PER_PPG_FT_EXACT * 10_000.0)
    assert result.kill_mw_ppg == pytest.approx(kill_exact, abs=0.002)
    assert result.icp_psi == pytest.approx(800.0 + 520.0)
    assert result.fcp_psi == pytest.approx(800.0 * kill_exact / 10.0, abs=0.2)
    maasp_exact = (0.75 - 10.0 * PSI_PER_PPG_FT_EXACT) * 5_000.0  # gradient-based: 1152.6 psi
    assert result.maasp_psi == pytest.approx(maasp_exact, rel=0.003)


# ------------------------------------------------------- bit hydraulics

@pytest.mark.parametrize("gpm,mw,tfa", [(500.0, 10.0, 0.5), (300.0, 12.5, 0.3313), (800.0, 9.0, 1.2)])
def test_bit_pressure_drop_matches_bernoulli_with_cd_095(gpm, mw, tfa):
    rho = mw * KG_M3_PER_PPG
    velocity = gpm * M3S_PER_GPM / (tfa * M2_PER_IN2)
    expected_psi = rho * velocity ** 2 / (2.0 * 0.95 ** 2) / PA_PER_PSI
    assert H.calc_bit_pressure_drop(gpm, mw, tfa) == pytest.approx(expected_psi, rel=FIELD_CONSTANT_ROUNDING)


def test_jet_velocity_horsepower_and_impact_force_from_unit_definitions():
    gpm, mw, tfa, dp = 500.0, 10.0, 0.5, 1500.0
    ft3_s = gpm / GAL_PER_FT3 / 60.0
    velocity = ft3_s / (tfa / 144.0)                         # ft/s
    assert H.calc_jet_velocity(gpm, tfa) == pytest.approx(velocity, rel=2e-4)
    hhp = ft3_s * dp * 144.0 / 550.0                          # (ft^3/s)(lbf/ft^2) / (ft.lbf/s per hp)
    assert H.calc_bit_hhp(gpm, dp) == pytest.approx(hhp, rel=2e-4)
    slug_s = mw * gpm / 60.0 / G_FT_S2                        # mass flow, slug/s
    assert H.calc_impact_force(mw, gpm, velocity) == pytest.approx(slug_s * velocity, rel=FIELD_CONSTANT_ROUNDING)


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_bit_hydraulics_refuse_invalid_inputs(bad):
    with pytest.raises(ValueError):
        H.calc_bit_pressure_drop(bad, 10.0, 0.5)
    with pytest.raises(ValueError):
        H.calc_bit_pressure_drop(500.0, 10.0, bad)
