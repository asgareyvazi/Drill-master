"""M40 numerical regressions for unit-sensitive hydraulics and geometry.

Reference convention: Boyun Guo and Gefei Liu, “Mud Hydraulics Fundamentals,”
Applied Drilling Circulation Systems: Hydraulics, Calculations, and Models
(2011), Chapter 2, pp. 19–59, Eqs. 2.9–2.11 (power-law rheology) and 2.58–2.59
(Bingham pipe/annulus field-unit correlations). The tests also independently
check the zero-yield pipe limit against Hagen–Poiseuille. No API/RP compliance
is asserted.
"""

import ast
import math
from pathlib import Path

import pytest

from core.engineering.extended import HydraulicsExtended
from core.hydraulics_engine import (
    AdvancedHydraulicsEngine,
    BitNozzle,
    CasingSection,
    MudProperties,
    PipeSegment,
    SurfaceEquipment,
    WellProfile,
)


def _poiseuille_psi(pv_cp, velocity_fps, length_ft, diameter_in):
    """SI Hagen–Poiseuille converted independently to psi and field lengths."""
    viscosity_pa_s = pv_cp * 1e-3
    velocity_m_s = velocity_fps * 0.3048
    length_m = length_ft * 0.3048
    diameter_m = diameter_in * 0.0254
    pressure_pa = 32.0 * viscosity_pa_s * velocity_m_s * length_m / diameter_m**2
    return pressure_pa / 6894.757293168


def test_bingham_pipe_zero_yield_matches_newtonian_unit_ground_truth():
    pv_cp, velocity_fps, length_ft, diameter_in = 1.0, 0.01, 1000.0, 4.0
    expected = _poiseuille_psi(pv_cp, velocity_fps, length_ft, diameter_in)
    engine = AdvancedHydraulicsEngine()

    # The velocity is below the canonical critical velocity for these inputs.
    actual = engine._bingham_pipe_loss(
        velocity_fps, diameter_in, length_ft, mw=10.0, pv=pv_cp, yp=0.0
    )
    assert actual == pytest.approx(expected, rel=0.004)
    assert actual == pytest.approx(pv_cp * velocity_fps * length_ft / (1500 * diameter_in**2))


def test_extended_pipe_uses_same_canonical_field_unit_formula():
    diameter_in, length_ft, velocity_fps = 4.0, 1000.0, 0.01
    flow_rate_gpm = velocity_fps * 2.448 * diameter_in**2
    expected = velocity_fps * length_ft / (1500.0 * diameter_in**2)

    actual = HydraulicsExtended.pressure_loss_pipe(
        mw_ppg=10.0,
        pv_cp=1.0,
        yp_lbf100ft2=0.0,
        flow_rate_gpm=flow_rate_gpm,
        pipe_id_in=diameter_in,
        length_ft=length_ft,
    )
    assert actual["pipe_velocity_ftmin"] == pytest.approx(0.6)
    assert actual["flow_regime"] == "Laminar"
    assert actual["pressure_loss_psi"] == pytest.approx(expected, abs=0.0001)
    assert "ft/s" in actual["formula"]
    assert actual["scope"] == "SCREENING"


def test_bingham_pipe_and_annulus_ground_truth_coefficients():
    pipe = AdvancedHydraulicsEngine.bingham_laminar_pipe_loss_components(
        10.0, 5.0, 2.0, 4.0, 1000.0
    )
    expected_pipe_viscous = 10.0 * 2.0 * 1000.0 / (1500.0 * 4.0**2)
    expected_pipe_yield = 5.0 * 1000.0 / (225.0 * 4.0)
    assert pipe["viscous_psi"] == pytest.approx(expected_pipe_viscous)
    assert pipe["yield_psi"] == pytest.approx(expected_pipe_yield)
    assert sum(pipe.values()) == pytest.approx(expected_pipe_viscous + expected_pipe_yield)

    annulus = AdvancedHydraulicsEngine.bingham_laminar_annular_loss_components(
        10.0, 5.0, 2.0, 4.0, 1000.0
    )
    expected_ann_viscous = 10.0 * 2.0 * 1000.0 / (1000.0 * 4.0**2)
    expected_ann_yield = 5.0 * 1000.0 / (200.0 * 4.0)
    assert annulus["viscous_psi"] == pytest.approx(expected_ann_viscous)
    assert annulus["yield_psi"] == pytest.approx(expected_ann_yield)
    assert sum(annulus.values()) == pytest.approx(expected_ann_viscous + expected_ann_yield)


def test_extended_annulus_converts_display_velocity_before_delegation():
    hole_id, pipe_od, length_ft = 8.0, 4.0, 1000.0
    flow_rate_gpm = 0.6 * (hole_id**2 - pipe_od**2) / 24.51
    expected = 0.6 / 60.0 * length_ft / (1000.0 * (hole_id - pipe_od) ** 2)

    actual = HydraulicsExtended.pressure_loss_annular(
        mw_ppg=10.0,
        pv_cp=1.0,
        yp_lbf100ft2=0.0,
        flow_rate_gpm=flow_rate_gpm,
        hole_id_in=hole_id,
        pipe_od_in=pipe_od,
        length_ft=length_ft,
    )
    assert actual["annular_velocity_ftmin"] == pytest.approx(0.6)
    assert actual["flow_regime"] == "Laminar"
    assert actual["pressure_loss_psi"] == pytest.approx(expected, abs=0.0001)


def test_power_law_consistency_uses_shear_stress_at_511_per_second():
    mud = MudProperties(theta600=45.0, theta300=25.0)
    n = 3.32 * math.log10(45.0 / 25.0)
    expected_k = 510.0 * 25.0 / (511.0**n)
    assert mud.n_power_law == pytest.approx(n)
    assert mud.k_power_law == pytest.approx(expected_k)

    engine = AdvancedHydraulicsEngine()
    engine.mud = mud
    velocity_fps, diameter_in, length_ft = 0.001, 4.0, 1000.0
    gamma = (96.0 * velocity_fps / diameter_in) * (3.0 * n + 1.0) / (4.0 * n)
    expected_loss = gamma**n * expected_k * length_ft / (300.0 * diameter_in)
    assert engine._power_law_pipe_loss(velocity_fps, diameter_in, length_ft, mw=10.0) == pytest.approx(
        expected_loss
    )


def test_fann_rheology_values_are_canonical_and_unit_labelled():
    result = MudProperties.calculate_fann_rheology(
        theta600=45.0, theta300=25.0, theta3=3.0, theta6=4.0
    )
    n = 3.32 * math.log10(45.0 / 25.0)
    assert result["pv_cp"] == pytest.approx(20.0)
    assert result["yp_lbf100ft2"] == pytest.approx(5.0)
    assert result["power_law_n"] == pytest.approx(n)
    assert result["power_law_k_equivalent_cp"] == pytest.approx(510.0 * 25.0 / 511.0**n)
    assert result["hb_yield_estimate_lbf100ft2"] == pytest.approx(2.0)
    assert "equivalent cP" in result["units"]["power_law_k"]
    assert result["scope"] == "SCREENING"
    with pytest.raises(ValueError, match="negative Bingham yield"):
        MudProperties.calculate_fann_rheology(theta600=100.0, theta300=30.0)


def test_w13_rheology_calculator_contains_no_duplicate_formulae():
    source_path = Path(__file__).resolve().parents[1] / "tabs" / "w13_Engineering_Calculator.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    handlers = [
        node for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_mud_rheo"
    ]
    assert len(handlers) == 1
    handler = handlers[0]
    calls = [node for node in ast.walk(handler) if isinstance(node, ast.Call)]
    assert any(
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "calculate_fann_rheology"
        for call in calls
    )
    assert not any(
        isinstance(call.func, ast.Attribute) and call.func.attr == "log10"
        for call in calls
    )


def _geometry_engine():
    engine = AdvancedHydraulicsEngine()
    engine.flow_rate_gpm = 100.0
    engine.bit_depth_m = 304.8  # 1000 ft
    engine.bit_diameter_in = 8.5
    engine.mud = MudProperties(mw_pcf=74.8052, pv=10.0, yp=5.0, theta600=30, theta300=20)
    engine.surface_equipment = SurfaceEquipment(
        standpipe_length_m=30, standpipe_id_inch=3.5,
        hose_length_m=20, hose_id_inch=3.0,
    )
    engine.pipe_segments = [PipeSegment(name="DP", od=4.0, id=3.5, length=304.8)]
    engine.casing_sections = [
        CasingSection(name="Cased hole", section_type="casing", id=8.0, top_md=0, bottom_md=152.4),
        CasingSection(name="Open hole", section_type="open_hole", id=12.0, top_md=152.4, bottom_md=304.8),
    ]
    engine.nozzles = [BitNozzle(size_32nds=16, quantity=3)]
    engine.well_profile = WellProfile(well_type="vertical")
    return engine


def test_power_law_annular_loss_ground_truth_at_laminar_velocity():
    engine = AdvancedHydraulicsEngine()
    engine.model = "power_law"
    engine.mud = MudProperties(mw_pcf=74.8052, pv=20.0, yp=5.0, theta600=45.0, theta300=25.0)
    hole_id, pipe_od, length_ft, velocity_fps = 8.0, 4.0, 1000.0, 0.001
    gap = hole_id - pipe_od
    flow_gpm = velocity_fps * 2.448 * (hole_id**2 - pipe_od**2)
    n = 3.32 * math.log10(45.0 / 25.0)
    k = 510.0 * 25.0 / 511.0**n
    # Independently expand the documented field-unit laminar annulus estimate.
    gamma = (144.0 * velocity_fps / gap) * (2.0 * n + 1.0) / (3.0 * n)
    expected = gamma**n * (k * length_ft / (300.0 * gap))
    actual = engine._power_law_annular_loss(
        velocity_fps, gap, hole_id, pipe_od, length_ft, engine.mud.mw_ppg, flow_gpm
    )
    assert actual == pytest.approx(expected, rel=1e-12)


def test_herschel_bulkley_is_explicitly_an_approximation():
    engine = AdvancedHydraulicsEngine()
    engine.model = "herschel_bulkley"
    engine.mud = MudProperties(
        mw_pcf=74.8052, pv=10.0, yp=5.0,
        theta600=45.0, theta300=25.0, theta3=3.0, theta6=4.0,
    )
    pl = engine._power_law_pipe_loss(0.001, 4.0, 1000.0, engine.mud.mw_ppg)
    hb = engine._hb_pipe_loss(0.001, 4.0, 1000.0, engine.mud.mw_ppg)
    assert hb == pytest.approx(pl + 2.0 * 1000.0 / (225.0 * 4.0))

    complete = _geometry_engine()
    complete.model = "herschel_bulkley"
    complete.mud.theta3 = 3.0
    complete.mud.theta6 = 4.0
    result = complete.calculate()
    assert result.errors == []
    assert result.scope == "SCREENING"
    assert any("not a full HB solver" in warning for warning in result.warnings)


def test_ecd_integrates_the_supplied_intervals_not_a_linear_depth_fraction():
    engine = _geometry_engine()
    result = engine.calculate()
    assert not result.errors
    at_shoe = dict(result.ecd_profile)[152.4]
    pv, yp, mw, flow = 10.0, 5.0, 10.0, 100.0
    v_shoe_fps = flow / (2.448 * (8.0**2 - 4.0**2))
    first_interval_apl = pv * v_shoe_fps * 500.0 / (1000.0 * (8.0 - 4.0) ** 2)
    first_interval_apl += yp * 500.0 / (200.0 * (8.0 - 4.0))
    expected_at_shoe = mw + first_interval_apl / (0.052 * 500.0)
    assert at_shoe == pytest.approx(round(expected_at_shoe, 3))

    at_bit = dict(result.ecd_profile)[304.8]
    v_open_fps = flow / (2.448 * (12.0**2 - 4.0**2))
    open_interval_apl = pv * v_open_fps * 500.0 / (1000.0 * (12.0 - 4.0) ** 2)
    open_interval_apl += yp * 500.0 / (200.0 * (12.0 - 4.0))
    expected_at_bit = mw + (first_interval_apl + open_interval_apl) / (0.052 * 1000.0)
    assert at_bit == pytest.approx(round(expected_at_bit, 3))


def test_directional_tvd_requires_explicit_covered_survey_values():
    profile = WellProfile(well_type="directional")
    with pytest.raises(ValueError, match="without measured survey TVD"):
        profile.get_tvd_at_md(1000.0)

    profile.survey_points = [(0.0, 0.0, 0.0), (1000.0, 30.0, 90.0)]
    with pytest.raises(ValueError, match="missing measured TVD"):
        profile.get_tvd_at_md(500.0)

    profile.survey_points = [(0.0, 0.0, 0.0, 0.0), (1000.0, 30.0, 90.0, 900.0)]
    assert profile.get_tvd_at_md(500.0) == pytest.approx(450.0)
    with pytest.raises(ValueError, match="does not cover"):
        profile.get_tvd_at_md(1200.0)


def test_missing_bore_geometry_is_not_replaced_with_fabricated_open_hole_id():
    engine = _geometry_engine()
    engine.casing_sections = [
        CasingSection(name="Recorded casing", section_type="casing", id=8.0, top_md=0, bottom_md=152.4)
    ]
    result = engine.calculate()
    assert result.errors
    assert "does not cover the full drill-string interval" in result.errors[0]
    assert result.annulus_losses == []
    assert result.ecd_profile == []


def test_w13_engineering_inputs_invalidate_cached_results_and_avoid_geometry_defaults():
    w13 = Path("tabs/w13_Engineering_Calculator.py").read_text(encoding="utf-8")
    dialogs = Path("dialogs/engineering_dialogs.py").read_text(encoding="utf-8")
    assert "valueChanged.connect(self._hy_invalidate_results)" in w13
    assert "self.wc_well_type.currentTextChanged.connect(self._wc_invalidate_kill_result)" in w13
    assert "def _bit_input_changed" in w13
    assert "def _mse_input_changed" in w13
    assert "def _wc_invalidate_kill_result" in w13
    assert "-- Select measured nozzle size --" in dialogs
    assert "self.size.currentData() or 16" not in dialogs
    assert "self.od = self._dspin(0, 0, 50, 3, \" in\")" in dialogs
    assert "self.od = self._dspin(9.625, 0.1, 50, 3, \" in\")" not in dialogs


@pytest.mark.parametrize("nozzles", [[0], [-13], [13, float("nan")], [13, float("inf")], [True], [13, "invalid"]])
def test_canonical_tfa_rejects_invalid_or_partially_missing_nozzle_geometry(nozzles):
    from core.engineering.core import BitEngine
    from core.engineering.result import EngineeringError

    with pytest.raises(EngineeringError, match="nozzle 1|nozzle 2"):
        BitEngine.calculate_tfa(nozzles)


@pytest.mark.parametrize("nozzles", ["13", 13])
def test_canonical_tfa_rejects_non_iterable_or_string_programs(nozzles):
    from core.engineering.core import BitEngine
    from core.engineering.result import EngineeringError

    with pytest.raises(EngineeringError, match="iterable of explicit sizes"):
        BitEngine.calculate_tfa(nozzles)


def test_default_unconfigured_hydraulics_has_no_numeric_result():
    engine = AdvancedHydraulicsEngine()
    result = engine.calculate()
    assert result.errors
    assert result.scope == "NOT_ASSESSED"
    assert result.total_loss_psi is None
    assert result.ecd_profile == []
    assert PipeSegment().od == PipeSegment().id == 0.0
    assert CasingSection().id == 0.0
    assert BitNozzle().size_32nds == BitNozzle().quantity == 0


def _surge_case_engine():
    engine = AdvancedHydraulicsEngine()
    engine.bit_depth_m = 1000 / 3.28084
    engine.mud = MudProperties(mw_pcf=74.8052, pv=10.0, yp=5.0, theta600=30, theta300=20)
    engine.pipe_segments = [
        PipeSegment(name="DP", od=4.0, id=3.5, length=600 / 3.28084),
        PipeSegment(name="BHA", od=6.5, id=2.5, length=400 / 3.28084),
    ]
    engine.casing_sections = [
        CasingSection(name="surface casing", id=8.0, top_md=0, bottom_md=500 / 3.28084),
        CasingSection(name="liner", id=9.875, top_md=500 / 3.28084, bottom_md=800 / 3.28084),
        CasingSection(name="open hole", section_type="open_hole", id=12.0,
                      top_md=800 / 3.28084, bottom_md=1000 / 3.28084),
    ]
    engine.well_profile = WellProfile(well_type="vertical")
    return engine


def _independent_bingham_surges(engine, trip_speed_fpm, pipe_open):
    """Manual field-unit reference from displacement velocity + engine correlation."""
    results = []
    current_ft = 0.0
    for pipe in engine.pipe_segments:
        top = current_ft
        bottom = top + pipe.length_ft
        for bore in engine.casing_sections:
            length = max(0.0, min(bottom, bore.bottom_md * 3.28084) - max(top, bore.top_md * 3.28084))
            if length <= 0:
                continue
            annulus_area = bore.id**2 - pipe.od**2
            if pipe_open:
                displacement_area = pipe.od**2 - pipe.id**2
                velocity_denominator = annulus_area + pipe.id**2
            else:
                displacement_area = pipe.od**2
                velocity_denominator = annulus_area
            fluid_fpm = (0.45 + displacement_area / velocity_denominator) * trip_speed_fpm
            max_fps = (1.5 * fluid_fpm) / 60.0
            gap = bore.id - pipe.od
            mw = engine.mud.mw_ppg
            pv, yp = engine.mud.pv, engine.mud.yp
            critical_fps = (
                1.08 * pv + 1.08 * math.sqrt(pv**2 + 9.26 * gap**2 * yp * mw)
            ) / (mw * gap)
            if max_fps >= critical_fps:
                pressure = mw**0.75 * max_fps**1.75 * pv**0.25 * length / (1396.0 * gap**1.25)
            else:
                pressure = (
                    pv * max_fps * length / (1000.0 * gap**2)
                    + yp * length / (200.0 * gap)
                )
            results.append(pressure)
        current_ft = bottom
    return results


@pytest.mark.parametrize("trip_speed_fpm", [0.5, 60.0, 150.0])
@pytest.mark.parametrize("pipe_open", [False, True])
def test_surge_and_swab_use_piecewise_displacement_units_and_canonical_loss(trip_speed_fpm, pipe_open):
    engine = _surge_case_engine()
    expected_segments = _independent_bingham_surges(engine, trip_speed_fpm, pipe_open)
    expected_pressure = sum(expected_segments)
    surge = engine.calc_surge_swab(trip_speed_fpm, "RIH", pipe_open)
    swab = engine.calc_surge_swab(trip_speed_fpm, "POOH", pipe_open)

    assert surge["scope"] == swab["scope"] == "SCREENING"
    assert surge["total_pressure_psi"] == pytest.approx(expected_pressure, abs=0.11)
    assert swab["total_pressure_psi"] == pytest.approx(expected_pressure, abs=0.11)
    assert surge["equiv_mw_ppg"] > engine.mud.mw_ppg
    assert swab["equiv_mw_ppg"] < engine.mud.mw_ppg
    assert [segment["pressure_psi"] for segment in surge["segments"]] == pytest.approx(
        [round(value, 2) for value in expected_segments], abs=0.011
    )
    assert len(surge["segments"]) == 4  # DP/casing, DP/liner, BHA/liner, BHA/open hole


def test_surge_missing_selection_or_bore_geometry_is_not_assessed():
    engine = _surge_case_engine()
    unselected = engine.calc_surge_swab()
    assert unselected["scope"] == "NOT_ASSESSED"
    assert unselected["type"] == "Not selected"
    result = engine.calc_surge_swab(90.0, "RIH", False)
    engine.casing_sections = []
    result = engine.calc_surge_swab(90.0, "RIH", False)
    assert result["scope"] == "NOT_ASSESSED"
    assert result["total_pressure_psi"] is None
    assert result["equiv_mw_ppg"] is None
    assert result["segments"] == []


def test_surge_pressure_is_sensitive_to_each_explicit_bore_interval():
    engine = _surge_case_engine()
    base = engine.calc_surge_swab(60.0, "RIH", False)["total_pressure_psi"]
    engine.casing_sections[1].id = 10.5
    changed = engine.calc_surge_swab(60.0, "RIH", False)["total_pressure_psi"]
    assert changed != pytest.approx(base)


def test_bit_hydraulics_ground_truth_and_inverse_tfa_consistency():
    engine = AdvancedHydraulicsEngine()
    q_gpm, mw_ppg, tfa_in2, bit_od_in = 500.0, 10.0, 1.0, 8.5
    delta_p = q_gpm**2 * mw_ppg / (10858.0 * tfa_in2**2)
    hhp = q_gpm * delta_p / 1714.0
    hsi = hhp / (math.pi * bit_od_in**2 / 4.0)
    jet_velocity = q_gpm / (3.117 * tfa_in2)
    impact = mw_ppg * q_gpm * jet_velocity / 1930.0

    assert engine.calc_bit_pressure_drop(q_gpm, mw_ppg, tfa_in2) == pytest.approx(delta_p, rel=1e-12)
    assert engine.calc_bit_hhp(q_gpm, delta_p) == pytest.approx(hhp, rel=1e-12)
    assert engine.calc_hsi(hhp, bit_od_in) == pytest.approx(hsi, rel=1e-12)
    assert engine.calc_jet_velocity(q_gpm, tfa_in2) == pytest.approx(jet_velocity, rel=1e-12)
    assert engine.calc_impact_force(mw_ppg, q_gpm, jet_velocity) == pytest.approx(impact, rel=1e-12)

    target_dp = 1000.0
    derived_tfa = engine.calc_tfa_from_pressure_drop(q_gpm, mw_ppg, target_dp)
    assert engine.calc_bit_pressure_drop(q_gpm, mw_ppg, derived_tfa) == pytest.approx(target_dp)
    assert HydraulicsExtended.bit_nozzle_pressure_drop(q_gpm, mw_ppg, derived_tfa)[
        "nozzle_pressure_drop_psi"
    ] == pytest.approx(target_dp, abs=0.1)


def test_annular_velocity_and_critical_flow_match_independent_unit_conversion():
    hole_id, pipe_od, flow_gpm = 8.0, 4.0, 120.0
    expected_velocity_fps = flow_gpm / (2.448 * (hole_id**2 - pipe_od**2))
    actual_velocity = AdvancedHydraulicsEngine._calc_annular_velocity(flow_gpm, hole_id, pipe_od)
    assert actual_velocity == pytest.approx(expected_velocity_fps)

    mw, pv, yp = 10.0, 15.0, 8.0
    gap = hole_id - pipe_od
    critical_fps = (1.08 * pv + 1.08 * math.sqrt(pv**2 + 9.26 * gap**2 * yp * mw)) / (mw * gap)
    annular_area_ft2 = math.pi / 4 * ((hole_id / 12) ** 2 - (pipe_od / 12) ** 2)
    expected_qc = critical_fps * 60 * annular_area_ft2 * 7.4805
    actual = AdvancedHydraulicsEngine.calc_critical_flow_rate(mw, pv, yp, hole_id, pipe_od)
    assert actual["critical_velocity_ft_min"] == pytest.approx(critical_fps * 60, abs=0.1)
    assert actual["critical_flow_rate_gpm"] == pytest.approx(expected_qc, abs=0.1)
    engine = AdvancedHydraulicsEngine()
    engine.mud = MudProperties(mw_pcf=mw * 7.48052, pv=pv, yp=yp)
    assert engine._determine_flow_regime(critical_fps * 0.79, gap, is_annular=True) == "Laminar"
    assert engine._determine_flow_regime(critical_fps * 0.9, gap, is_annular=True) == "Transitional"
    assert engine._determine_flow_regime(critical_fps, gap, is_annular=True) == "Turbulent"


def test_bingham_laminar_coefficients_reject_nonfinite_inputs():
    for value in (float("nan"), float("inf"), -float("inf"), True):
        with pytest.raises(ValueError):
            AdvancedHydraulicsEngine.bingham_laminar_pipe_loss(10.0, 5.0, value, 4.0, 100.0)
        with pytest.raises(ValueError):
            AdvancedHydraulicsEngine.bingham_laminar_annular_loss(10.0, 5.0, 1.0, 4.0, value)
