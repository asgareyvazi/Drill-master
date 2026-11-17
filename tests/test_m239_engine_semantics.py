"""M239: tests for the survivors of the extended mutation catalogue ``tools/quality/mutation_m231_m260.py``.

The extension mutated the casing engine, the torque-and-drag engine and the kill sheet, which no earlier catalogue
had touched. Six realistic defects survived the existing tests (diagnostic ``--only`` run on 5ff4d09 plus the
modified tree). Writing an independent oracle for one of them, the API 5C3 transition coefficient, exposed
**D77**: F and G were negative, so the transition regime was never used. Fixed in
``core/engineering/engines/casing.py``; the method id gained ``transition F r3``.

The collapse oracle does not reuse the engine's F formula. It derives F from the defining property of API 5C3: the
transition line ``Yp (F / (D/t) - G)``, with ``G = F B/A``, meets the elastic curve ``46.95e6 / ((D/t) (D/t - 1)^2)``
at the transition/elastic limit ``(2 + B/A) / (3 B/A)``. It then checks continuity at both regime boundaries and
tangency at the elastic one numerically. SYNTHETIC geometries; screening only.
"""
from __future__ import annotations

import dataclasses

import pytest

from core.engineering.engines.casing import CasingEngine
from core.engineering.engines.torque_drag import TorqueDragEngine
from core.engineering.well_control_kill_sheet import build_canonical_kill_sheet_inputs, compute_kill_sheet

YIELDS = (40_000.0, 55_000.0, 80_000.0, 110_000.0, 125_000.0)


def _elastic(dt):
    return 46.95e6 / (dt * (dt - 1.0) ** 2)


# ---- D77: API 5C3 collapse regimes -----------------------------------------------------------------------------
@pytest.mark.parametrize("yp", YIELDS)
def test_transition_coefficient_follows_from_meeting_the_elastic_curve(yp):
    a, b, c, f, g = CasingEngine._abc(yp)
    ba = b / a
    dt_te = (2.0 + ba) / (3.0 * ba)
    f_oracle = _elastic(dt_te) / (yp * (1.0 / dt_te - ba))
    assert f > 0 and g > 0
    assert f == pytest.approx(f_oracle, rel=1e-9)
    assert g == pytest.approx(f_oracle * ba, rel=1e-9)


@pytest.mark.parametrize("yp", YIELDS)
def test_collapse_regime_limits_are_ordered_and_the_curve_is_continuous(yp):
    dt_yp, dt_pt, dt_te, a, b, c, f, g = CasingEngine._dt_limits(yp)
    assert dt_yp < dt_pt < dt_te

    def plastic(dt):
        return yp * (a / dt - b) - c

    def transition(dt):
        return yp * (f / dt - g)

    assert plastic(dt_pt) == pytest.approx(transition(dt_pt), rel=1e-9)
    assert transition(dt_te) == pytest.approx(_elastic(dt_te), rel=1e-9)
    h = 1e-4
    slope_t = (transition(dt_te + h) - transition(dt_te - h)) / (2 * h)
    slope_e = (_elastic(dt_te + h) - _elastic(dt_te - h)) / (2 * h)
    assert slope_t == pytest.approx(slope_e, rel=1e-5)


@pytest.mark.parametrize("od, wall, yp", [(9.625, 0.352, 55_000.0), (13.375, 0.380, 55_000.0),
                                           (10.75, 0.350, 80_000.0), (9.625, 0.395, 80_000.0)])
def test_a_wall_between_the_plastic_and_elastic_limits_uses_the_transition_regime(od, wall, yp):
    result = CasingEngine.collapse(od, wall, yp)
    assert result.success, result.error
    values = result.values
    assert values["dt_plastic_transition"] < values["d_over_t"] <= values["dt_transition_elastic"]
    assert values["regime"] == "transition"
    _, _, _, _, _, _, f, g = CasingEngine._dt_limits(yp)
    assert values["collapse_rating_psi"] == pytest.approx(yp * (f / (od / wall) - g), abs=0.06)


def test_regime_boundaries_are_continuous_in_the_engine_output():
    yp, od = 55_000.0, 10.0
    _, dt_pt, dt_te, *_ = CasingEngine._dt_limits(yp)
    for dt in (dt_pt, dt_te):
        below = CasingEngine.collapse(od, od / (dt * (1 - 1e-7)), yp).values["collapse_rating_psi"]
        above = CasingEngine.collapse(od, od / (dt * (1 + 1e-7)), yp).values["collapse_rating_psi"]
        assert below == pytest.approx(above, abs=0.2)


# ---- casing design factor -------------------------------------------------------------------------------------
def test_burst_working_pressure_divides_by_the_design_factor():
    result = CasingEngine.burst(9.625, 0.545, 80_000.0, design_factor=1.25)
    assert result.success, result.error
    rating = 0.875 * 2.0 * 80_000.0 * 0.545 / 9.625
    assert result.values["burst_rating_psi"] == pytest.approx(rating, abs=0.06)
    assert result.values["working_pressure_psi"] == pytest.approx(rating / 1.25, abs=0.06)
    assert CasingEngine.burst(9.625, 0.545, 80_000.0).values["working_pressure_psi"] is None


# ---- torque and drag input contract ---------------------------------------------------------------------------
SURVEY = [{"md": 0, "inc": 0, "azi": 0}, {"md": 3048.0, "inc": 0, "azi": 0}]
BHA = [{"length": 3048.0, "weight": 19.5, "od": 5.0, "id": 4.276}]


def test_a_friction_factor_entered_in_percent_is_rejected():
    assert TorqueDragEngine.calculate(SURVEY, BHA, mud_density_ppg=10.0, friction_factor=0.25).success
    result = TorqueDragEngine.calculate(SURVEY, BHA, mud_density_ppg=10.0, friction_factor=25)
    assert result.success is False
    assert "friction_factor" in result.error


def test_a_zero_mud_weight_is_rejected_not_treated_as_air():
    result = TorqueDragEngine.calculate(SURVEY, BHA, mud_density_ppg=0.0, friction_factor=0.25)
    assert result.success is False
    assert "mud_density_ppg" in result.error


# ---- kill sheet annulus geometry ------------------------------------------------------------------------------
RAW = dict(
    tvd_m=3000, md_m=3200, shoe_tvd_m=2000, shoe_md_m=2000, hole_size_in=8.5,
    casing_id_in=8.835, casing_od_in=9.625, mw_pcf=90.0,
    frac_gradient_psi_ft=0.8, sidpp_psi=500, sicp_psi=700, pit_gain_bbl=10,
    scr1_psi=800, scr1_spm=30, scr2_psi=600, scr2_spm=25,
    pump_output_bbl_stk=0.09, method="Wait & Weight", well_type="Vertical",
    pipes_m=[
        {"type": "DP", "od": 5.0, "id": 4.276, "length": 2800.0},
        {"type": "HWDP", "od": 5.0, "id": 3.0, "length": 200.0},
        {"type": "DC", "od": 6.5, "id": 2.8125, "length": 200.0},
    ],
)


def test_reference_kill_sheet_assesses_the_annulus():
    result = compute_kill_sheet(build_canonical_kill_sheet_inputs(**RAW))
    assert result.success, result.error
    assert result.total_ann_vol_bbl > 0 and result.total_well_vol_bbl > result.total_string_vol_bbl


def test_an_explicit_zero_casing_id_does_not_produce_a_partial_annulus():
    result = compute_kill_sheet(build_canonical_kill_sheet_inputs(**dict(RAW, casing_id_in=0.0)))
    assert result.success, result.error
    assert result.total_ann_vol_bbl is None
    assert result.total_well_vol_bbl is None
    assert result.stk_annular is None


def test_a_shoe_below_the_measured_depth_is_not_used_for_annular_geometry():
    inp = build_canonical_kill_sheet_inputs(**RAW)
    deeper = dataclasses.replace(inp, shoe_md_ft=inp.md_ft + 500.0)
    result = compute_kill_sheet(deeper)
    assert result.success, result.error
    assert result.total_ann_vol_bbl is None
    assert result.total_well_vol_bbl is None
