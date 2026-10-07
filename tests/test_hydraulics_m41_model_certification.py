"""M41 independent numerical/limiting regressions for rheology and hydraulics.

Oracle units deliberately start in SI. Fann calibration is 0.510 Pa per dial
unit and nominal rates 511/1022 s^-1 (Fann Model 35 R1-B1-F1 manual). Field
pressure correlations are tested only after explicit conversions. These tests
are not API compliance tests or a field validation.
"""

import math

import pytest

from core.hydraulics_engine import (
    AdvancedHydraulicsEngine,
    BitNozzle,
    CasingSection,
    MudProperties,
    PipeSegment,
    SurfaceEquipment,
    WellProfile,
)

FANN_DIAL_PA = 0.510
PSI_PA = 6894.757293168
FT_M = 0.3048
IN_M = 0.0254
FIELD_STRESS_PA = 0.4788025898  # 1 lbf/100 ft^2


def _si_laminar_pl_pipe(theta300, n, velocity_fps, diameter_in, length_ft):
    """Exact Newtonian/generalized-Newtonian pipe balance from wall stress."""
    k_pa_s_n = FANN_DIAL_PA * theta300 / (511.0**n)
    velocity_m_s = velocity_fps * FT_M
    diameter_m = diameter_in * IN_M
    length_m = length_ft * FT_M
    wall_rate = (8.0 * velocity_m_s / diameter_m) * (3.0 * n + 1.0) / (4.0 * n)
    wall_stress_pa = k_pa_s_n * wall_rate**n

    # Axial force balance on a pipe segment: ΔP = 4 τw L / D.
    return 4.0 * wall_stress_pa * length_m / diameter_m / PSI_PA


def _si_newtonian_annulus(theta300, velocity_fps, hole_in, pipe_in, length_ft):
    """Exact concentric-annulus Newtonian solution, not the field correlation."""
    mu_pa_s = FANN_DIAL_PA * theta300 / 511.0
    velocity_m_s = velocity_fps * FT_M
    length_m = length_ft * FT_M
    outer = hole_in * IN_M / 2.0
    inner = pipe_in * IN_M / 2.0
    area_radius = outer**2 - inner**2
    conductance = outer**4 - inner**4 - area_radius**2 / math.log(outer / inner)
    return (
        8.0 * mu_pa_s * velocity_m_s * length_m * area_radius
        / conductance / PSI_PA
    )


def _pl_engine(theta600, theta300, mud_weight_ppg=10.0):
    e = AdvancedHydraulicsEngine()
    e.model = "power_law"
    e.mud = MudProperties(
        mw_pcf=mud_weight_ppg * 7.48052,
        pv=10.0,
        yp=0.0,
        theta600=theta600,
        theta300=theta300,
    )
    return e


def test_fann_power_law_k_unit_contract_matches_fann_si_calibration():
    theta300, theta600 = 25.0, 45.0
    mud = MudProperties(theta300=theta300, theta600=theta600)
    n = 3.32 * math.log10(theta600 / theta300)
    k_si = FANN_DIAL_PA * theta300 / 511.0**n

    # Convert back independently: Pa*s^n -> cP*s^(n-1) numeric convention.
    expected_k_cP_s_nminus1 = 1000.0 * k_si
    assert mud.n_power_law == pytest.approx(n, rel=1e-14)
    assert mud.k_power_law == pytest.approx(expected_k_cP_s_nminus1, rel=1e-12)
    assert mud.k_power_law_field == pytest.approx(k_si / FIELD_STRESS_PA, rel=1e-12)
    assert "cP·s^(n-1)" in MudProperties.calculate_fann_rheology(
        theta600=theta600, theta300=theta300
    )["units"]["power_law_k"]


def test_power_law_pipe_matches_independent_si_wall_stress_solution():
    theta300 = 25.0
    n_target = 0.70
    theta600 = theta300 * 10 ** (n_target / 3.32)
    e = _pl_engine(theta600, theta300)
    velocity_fps, diameter_in, length_ft = 0.004, 4.0, 1200.0
    expected = _si_laminar_pl_pipe(theta300, e.mud.n_power_law, velocity_fps, diameter_in, length_ft)
    actual = e._power_law_pipe_loss(velocity_fps, diameter_in, length_ft, e.mud.mw_ppg)
    assert actual == pytest.approx(expected, rel=2e-10)


def test_power_law_pipe_scaling_limits_k_length_and_flow():
    theta300, theta600 = 25.0, 45.0
    e = _pl_engine(theta600, theta300)
    d, length, velocity = 4.0, 1000.0, 0.002
    baseline = e._power_law_pipe_loss(velocity, d, length, e.mud.mw_ppg)
    twice_length = e._power_law_pipe_loss(velocity, d, 2 * length, e.mud.mw_ppg)
    twice_velocity = e._power_law_pipe_loss(2 * velocity, d, length, e.mud.mw_ppg)
    assert twice_length == pytest.approx(2 * baseline, rel=1e-12)
    assert twice_velocity / baseline == pytest.approx(2 ** e.mud.n_power_law, rel=1e-12)

    e.mud.theta300 *= 2
    e.mud.theta600 *= 2
    k_doubled = e._power_law_pipe_loss(velocity, d, length, e.mud.mw_ppg)
    assert k_doubled == pytest.approx(2 * baseline, rel=1e-12)


def test_power_law_annulus_newtonian_limit_matches_exact_concentric_si_solution():
    # For n=1, θ600=2θ300; the independent oracle solves the exact annular
    # velocity profile, including curvature, rather than copying the field form.
    theta300, theta600 = 25.0, 50.0
    e = _pl_engine(theta600, theta300)
    hole, pipe, length, velocity = 8.0, 4.0, 1000.0, 0.01
    gap = hole - pipe
    area_factor = hole**2 - pipe**2
    annulus_area_m2 = math.pi / 4.0 * area_factor * IN_M**2
    gpm = velocity * FT_M * annulus_area_m2 * 60.0 / 0.003785411784
    expected = _si_newtonian_annulus(theta300, velocity, hole, pipe, length)
    actual = e._power_law_annular_loss(
        velocity, gap, hole, pipe, length, e.mud.mw_ppg, gpm
    )
    assert actual == pytest.approx(expected, rel=0.02)


def test_bingham_pipe_newtonian_limit_is_si_hagen_poiseuille():
    pv_cp, velocity, diameter, length = 12.0, 0.02, 4.0, 1000.0
    viscosity = pv_cp * 1e-3
    expected = (
        32.0 * viscosity * velocity * FT_M * length * FT_M
        / (diameter * IN_M) ** 2 / PSI_PA
    )
    actual = AdvancedHydraulicsEngine.bingham_laminar_pipe_loss(
        pv_cp, 0.0, velocity, diameter, length
    )
    assert actual == pytest.approx(expected, rel=0.004)


def test_bingham_annulus_zero_yield_matches_exact_si_cylindrical_solution():
    pv_cp, velocity, hole, pipe, length = 10.0, 0.6, 8.0, 4.0, 1000.0
    expected = _si_newtonian_annulus(pv_cp, velocity, hole, pipe, length)
    actual = AdvancedHydraulicsEngine.bingham_laminar_annular_loss(
        pv_cp, 0.0, velocity, hole - pipe, length
    )
    assert actual == pytest.approx(expected, rel=0.015)


def test_bingham_transition_label_and_pressure_branch_share_exact_threshold():
    e = AdvancedHydraulicsEngine()
    e.mud = MudProperties(mw_pcf=74.8052, pv=15.0, yp=8.0)
    d, length, mw = 4.0, 100.0, e.mud.mw_ppg
    vc = (1.08 * 15.0 + 1.08 * math.sqrt(15.0**2 + 12.34 * d**2 * 8.0 * mw)) / (mw * d)
    assert e._critical_velocity_fps(d, is_annular=False) == pytest.approx(vc, rel=1e-14)
    below = math.nextafter(vc, 0.0)
    assert e._determine_flow_regime(below, d, is_annular=False) == "Transitional"
    assert e._determine_flow_regime(vc, d, is_annular=False) == "Turbulent"
    assert e._bingham_pipe_loss(below, d, length, mw, 15.0, 8.0) == pytest.approx(
        e.bingham_laminar_pipe_loss(15.0, 8.0, below, d, length)
    )
    assert e._bingham_pipe_loss(vc, d, length, mw, 15.0, 8.0) != pytest.approx(
        e.bingham_laminar_pipe_loss(15.0, 8.0, vc, d, length)
    )


def test_bingham_annular_transition_label_and_loss_branch_share_threshold():
    e = AdvancedHydraulicsEngine()
    e.mud = MudProperties(mw_pcf=74.8052, pv=15.0, yp=8.0)
    gap, hole, pipe, length, mw = 4.0, 8.0, 4.0, 100.0, e.mud.mw_ppg
    expected_vc = (1.08 * 15.0 + 1.08 * math.sqrt(
        15.0**2 + 9.26 * gap**2 * 8.0 * mw
    )) / (mw * gap)
    vc = e._critical_velocity_fps(gap, is_annular=True)
    assert vc == pytest.approx(expected_vc, rel=1e-14)
    v_below = math.nextafter(vc, 0.0)
    assert e._determine_flow_regime(v_below, gap, is_annular=True) == "Transitional"
    assert e._determine_flow_regime(vc, gap, is_annular=True) == "Turbulent"
    assert e._bingham_annular_loss(v_below, gap, hole, pipe, length, mw, 15.0, 8.0) == pytest.approx(
        e.bingham_laminar_annular_loss(15.0, 8.0, v_below, gap, length)
    )
    assert e._bingham_annular_loss(vc, gap, hole, pipe, length, mw, 15.0, 8.0) != pytest.approx(
        e.bingham_laminar_annular_loss(15.0, 8.0, vc, gap, length)
    )


def test_power_law_annular_transition_label_and_loss_branch_share_threshold():
    e = _pl_engine(45.0, 25.0)
    gap, hole, pipe, length = 4.0, 8.0, 4.0, 1000.0
    vc = e._critical_velocity_fps(gap, is_annular=True)
    v_below = math.nextafter(vc, 0.0)
    assert e._determine_flow_regime(v_below, gap, is_annular=True) == "Transitional"
    assert e._determine_flow_regime(vc, gap, is_annular=True) == "Turbulent"
    k_field = e.mud.k_power_law_field
    n = e.mud.n_power_law
    gamma = (144.0 * v_below / gap) * (2.0 * n + 1.0) / (3.0 * n)
    expected_laminar = gamma**n * k_field * length / (300.0 * gap)
    gpm_below = v_below * 60.0 * (hole**2 - pipe**2) / 24.51
    assert e._power_law_annular_loss(
        v_below, gap, hole, pipe, length, e.mud.mw_ppg, gpm_below
    ) == pytest.approx(expected_laminar, rel=1e-12)
    gpm_at = vc * 60.0 * (hole**2 - pipe**2) / 24.51
    expected_turbulent = (
        7.7e-5 * e.mud.mw_ppg**0.8 * gpm_at**1.8 * e.mud.pv**0.2 * length
        / (gap**3 * (hole + pipe)**1.8)
    )
    assert e._power_law_annular_loss(
        vc, gap, hole, pipe, length, e.mud.mw_ppg, gpm_at
    ) == pytest.approx(expected_turbulent, rel=1e-12)


def test_power_law_transition_uses_converted_consistency_and_pressure_branch_threshold():
    theta300, theta600 = 25.0, 45.0
    e = _pl_engine(theta600, theta300)
    d, length = 4.0, 1000.0
    n = e.mud.n_power_law
    k_field = e.mud.k_power_law * 0.001 / FIELD_STRESS_PA
    expected_vc = ((58200.0 * k_field / e.mud.mw_ppg) ** (1.0 / (2.0 - n))) / 60.0 * (
        (1.6 / d) * ((3.0 * n + 1.0) / (4.0 * n))
    ) ** (n / (2.0 - n))
    assert e._critical_velocity_fps(d, is_annular=False) == pytest.approx(expected_vc, rel=1e-14)
    assert e._determine_flow_regime(math.nextafter(expected_vc, 0.0), d, is_annular=False) == "Transitional"
    assert e._determine_flow_regime(expected_vc, d, is_annular=False) == "Turbulent"
    v_below = math.nextafter(expected_vc, 0.0)
    gamma = (96.0 * v_below / d) * (3.0 * n + 1.0) / (4.0 * n)
    expected_laminar = gamma**n * k_field * length / (300.0 * d)
    actual_laminar = e._power_law_pipe_loss(v_below, d, length, e.mud.mw_ppg)
    assert actual_laminar == pytest.approx(expected_laminar, rel=1e-12)
    expected_turbulent = (
        3.6033e-4 * e.mud.mw_ppg**0.8 * expected_vc**1.8
        * e.mud.pv**0.2 * length / d**1.2
    )
    actual_at_threshold = e._power_law_pipe_loss(expected_vc, d, length, e.mud.mw_ppg)
    assert actual_at_threshold == pytest.approx(expected_turbulent, rel=1e-12)


def test_newtonian_power_law_transition_has_dimensionally_consistent_si_reynolds_number():
    theta300 = 25.0
    theta600 = theta300 * 10 ** (1.0 / 3.32)
    e = _pl_engine(theta600, theta300, mud_weight_ppg=10.0)
    n = e.mud.n_power_law
    assert n == pytest.approx(1.0, abs=1e-14)

    # At n=1, K is the Newtonian dynamic viscosity. Independently form Re in SI.
    viscosity_pa_s = FANN_DIAL_PA * theta300 / 511.0**n
    def reynolds(velocity_fps, diameter_in):
        density_kg_m3 = 10.0 * 119.826427316
        return (
            density_kg_m3 * velocity_fps * FT_M * diameter_in * IN_M
            / viscosity_pa_s
        )

    pipe_re = reynolds(e._critical_velocity_fps(4.0, is_annular=False), 4.0)
    annular_re = reynolds(e._critical_velocity_fps(4.0, is_annular=True), 4.0)
    # The source's Power Law transition convention is Re_T = 4270−1370n;
    # the engine's closed-form field estimate is approximate, not a solver.
    expected_transition_re = 4270.0 - 1370.0 * n
    assert pipe_re == pytest.approx(expected_transition_re, rel=0.05)
    assert annular_re == pytest.approx(expected_transition_re, rel=0.05)


def test_hb_yield_estimate_does_not_claim_hb_n_k_or_calculate_pressure_loss():
    rheology = MudProperties.calculate_fann_rheology(
        theta600=45.0, theta300=25.0, theta3=3.0, theta6=4.0
    )
    assert rheology["hb_yield_estimate_lbf100ft2"] == pytest.approx(2.0)
    assert "hb_n" not in rheology and "hb_k" not in rheology
    e = AdvancedHydraulicsEngine()
    e.model = "herschel_bulkley"
    e.mud = MudProperties(
        mw_pcf=74.8052, pv=10.0, yp=5.0,
        theta600=45.0, theta300=25.0, theta3=3.0, theta6=4.0,
    )
    result = e.calculate()
    assert result.scope == "NOT_ASSESSED"
    assert result.total_loss_psi is None
    assert result.errors and "yield-corrected" in result.errors[0]


def test_unassessed_flow_is_unknown_but_explicit_positive_flow_is_preserved():
    e = AdvancedHydraulicsEngine()
    assert e.calculate().flow_rate_gpm is None
    e.flow_rate_gpm = 125.0
    result = e.calculate()
    assert result.scope == "NOT_ASSESSED"
    assert result.flow_rate_gpm == 125.0


def test_uniform_vertical_ecd_is_integrated_from_si_pressure_loss():
    # One uniform interval. The ECD increment at bit must be total APL divided
    # by 0.052*TVD; derive APL independently with the exact SI annulus solution.
    e = AdvancedHydraulicsEngine()
    e.flow_rate_gpm = 1.0
    e.bit_depth_m = 1000.0 * 0.3048
    e.mud = MudProperties(mw_pcf=74.8052, pv=10.0, yp=0.0, theta600=20.0, theta300=10.0)
    e.model = "bingham"
    e.pipe_segments = [PipeSegment(name="DP", od=4.0, id=3.5, length=1000.0 * 0.3048)]
    e.casing_sections = [CasingSection(name="uniform", id=8.0, top_md=0.0, bottom_md=e.bit_depth_m)]
    e.nozzles = [BitNozzle(size_32nds=8, quantity=1)]
    e.surface_equipment = SurfaceEquipment(standpipe_length_m=1.0, standpipe_id_inch=3.0)
    e.well_profile = WellProfile(well_type="vertical")
    result = e.calculate()
    assert result.scope == "SCREENING"
    annulus_area_m2 = math.pi / 4.0 * (8.0**2 - 3.5**2) * IN_M**2
    ann_v_fps = (0.003785411784 / 60.0) / annulus_area_m2 / FT_M
    apl = _si_newtonian_annulus(10.0, ann_v_fps, 8.0, 3.5, 1000.0)
    expected = 10.0 + apl / (0.052 * 1000.0)
    assert result.flow_regimes_annulus == [("DP vs uniform", "Laminar")]
    assert result.ecd_at_bit_ppg == pytest.approx(expected, abs=0.002)


def test_tfa_program_matches_independent_si_circle_areas_and_rejects_fractional_counts():
    from core.engineering.core import BitEngine, EngineeringError

    sizes, counts = (13.0, 16.0), (2, 1)
    expected_in2 = sum(
        quantity * math.pi * ((size / 32.0 * IN_M) / 2.0) ** 2 / IN_M**2
        for size, quantity in zip(sizes, counts)
    )
    assert BitEngine.calculate_tfa_program(list(zip(sizes, counts))) == pytest.approx(expected_in2, rel=1e-14)
    assert BitNozzle(size_32nds=13, quantity=2).total_area == pytest.approx(
        BitEngine.calculate_tfa([13, 13])
    )
    with pytest.raises(EngineeringError, match="positive integer"):
        BitEngine.calculate_tfa_program([(13, 1.5)])


@pytest.mark.parametrize("pipe_open", [False, True])
@pytest.mark.parametrize("operation,sign", [("RIH", 1.0), ("POOH", -1.0)])
def test_surge_swab_geometry_and_signed_density_use_explicit_pipe_state(
    monkeypatch, pipe_open, operation, sign
):
    e = AdvancedHydraulicsEngine()
    e.bit_depth_m = 100.0
    e.mud = MudProperties(mw_pcf=74.8052, pv=10.0, yp=0.0)
    e.pipe_segments = [PipeSegment(name="DP", od=5.0, id=4.0, length=100.0)]
    e.casing_sections = [CasingSection(name="bore", id=10.0, top_md=0.0, bottom_md=100.0)]
    e.well_profile = WellProfile(well_type="vertical")
    captured = []

    def pressure_loss(hole_id, pipe_od, length_ft, flow_gpm):
        captured.append((hole_id, pipe_od, length_ft, flow_gpm))
        return 7.26

    monkeypatch.setattr(e, "_calc_annular_pressure_loss", pressure_loss)
    result = e.calc_surge_swab(60.0, operation, pipe_open)

    annular_area = 10.0**2 - 5.0**2
    displacement_area = 5.0**2 - 4.0**2 if pipe_open else 5.0**2
    flow_area = annular_area + 4.0**2 if pipe_open else annular_area
    induced_fpm = (0.45 + displacement_area / flow_area) * 60.0
    maximum_fpm = 1.5 * induced_fpm
    annulus_area_m2 = math.pi / 4.0 * annular_area * IN_M**2
    expected_flow_gpm = maximum_fpm * FT_M * annulus_area_m2 / 0.003785411784

    assert result["scope"] == "SCREENING"
    assert result["total_pressure_psi"] == 7.3
    assert result["equiv_mw_ppg"] == pytest.approx(
        10.0 + sign * 7.26 / (0.052 * (100.0 * 3.28084)), abs=0.001
    )
    assert result["pipe_status"] == ("Open" if pipe_open else "Closed")
    assert len(captured) == 1
    actual_hole, actual_pipe, actual_length, actual_flow = captured[0]
    assert (actual_hole, actual_pipe) == (10.0, 5.0)
    assert actual_length == pytest.approx(100.0 * 3.28084, rel=1e-12)
    assert actual_flow == pytest.approx(expected_flow_gpm, rel=1e-5)


def test_empirical_surface_factor_is_named_and_not_claimed_as_api():
    e = AdvancedHydraulicsEngine()
    e.surface_equipment = SurfaceEquipment(
        use_api_constant=True, api_surface_loss_constant=120.0
    )
    e.flow_rate_gpm = 100.0
    e.mud = MudProperties(mw_pcf=74.8052, pv=10.0, yp=3.0)
    loss = e._calc_surface_losses()
    expected = 120.0 * e.mud.mw_ppg * 100.0**1.86 / 1e6
    assert loss == pytest.approx(expected, abs=0.01)


def test_zero_flow_does_not_produce_nonfinite_power_law_pressure():
    e = _pl_engine(50.0, 25.0)
    assert e._power_law_pipe_loss(0.0, 4.0, 1000.0, e.mud.mw_ppg) == 0.0


def test_power_law_transition_rejects_unphysical_index_and_nonfinite_readings():
    e = _pl_engine(250.0, 25.0)
    with pytest.raises(ValueError, match="0 < n < 2"):
        e._critical_velocity_fps(4.0, is_annular=False)
    invalid = MudProperties(theta600=float("nan"), theta300=25.0)
    assert invalid.n_power_law == 0.0
    assert invalid.k_power_law == 0.0

    valid_engine = _pl_engine(50.0, 25.0)
    with pytest.raises(ValueError, match="finite real numbers"):
        valid_engine._power_law_pipe_loss(float("nan"), 4.0, 100.0, 10.0)
    with pytest.raises(ValueError, match="nonnegative"):
        valid_engine._power_law_pipe_loss(-0.1, 4.0, 100.0, 10.0)
    with pytest.raises(ValueError, match="invalid geometry"):
        valid_engine._power_law_annular_loss(0.1, 4.0, 4.0, 8.0, 100.0, 10.0, 1.0)


def test_rheology_hydraulics_and_bit_formulas_have_one_production_owner():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    hydraulic = (root / "core/hydraulics_engine.py").read_text(encoding="utf-8")
    bit_core = (root / "core/engineering/core.py").read_text(encoding="utf-8")
    w13 = (root / "tabs/w13_Engineering_Calculator.py").read_text(encoding="utf-8")

    assert hydraulic.count("FANN_LOG_SLOPE_FACTOR * math.log10") == 1
    assert hydraulic.count("1000.0 * FANN_DIAL_STRESS_PA") == 1
    assert hydraulic.count("0.001 / FIELD_STRESS_PA_PER_LBF100FT2") == 1
    assert hydraulic.count("return hole_id_in**2 - pipe_od_in**2") == 1
    assert hydraulic.count("((58200.0 * k / mw)") == 1
    assert hydraulic.count("((38780.0 * k / mw)") == 1
    assert hydraulic.count("return mud_weight_ppg + annular_pressure_loss_psi / (0.052 * tvd_ft)") == 1
    assert bit_core.count("tfa += quantity * math.pi * diameter_in**2 / 4.0") == 1
    assert "math.pi" not in w13[w13.index("class DrillingCalculationEngine:"):w13.index("# ==================== UI TAB")]


def test_w13_fann_display_uses_corrected_k_unit_label():
    import ast
    from pathlib import Path
    from types import SimpleNamespace

    source = Path(__file__).resolve().parents[1] / "tabs/w13_Engineering_Calculator.py"
    module = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "EngineeringCalculatorTab")
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "_mud_rheo")
    namespace = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)

    class Control:
        def __init__(self, value):
            self._value = value

        def value(self):
            return self._value

    output = SimpleNamespace(text="", setText=lambda text: setattr(output, "text", text))
    ui = SimpleNamespace(
        rh_t600=Control(45.0), rh_t300=Control(25.0), rh_t200=Control(15.0),
        rh_t100=Control(8.0), rh_t6=Control(4.0), rh_t3=Control(3.0),
        rh_gel10s=Control(3.0), rh_gel10m=Control(5.0), rh_mw=Control(90.0),
        rh_result=output,
    )
    namespace["_mud_rheo"](ui)
    assert "cP·s^(n−1)" in output.text
    assert "equivalent cP" not in output.text
    assert "K: " in output.text and "510 θ300 / 511^n" in output.text

    ui.rh_t600 = Control(25.0)
    namespace["_mud_rheo"](ui)
    assert output.text.startswith("Not assessed:")
