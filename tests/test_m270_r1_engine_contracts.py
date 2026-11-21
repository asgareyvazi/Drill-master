"""M270 (R-1): engineering contracts of the seven modules no earlier mutation catalogue reached.

Every expected number is worked out by hand in the test (comments show the arithmetic) from the formula the
module itself documents - the engines' own helpers are never used to produce an expected value.  The tests
pin the contracts that ``tools/quality/mutation_m261_m290.py`` mutates: validity gates, unknown-versus-zero,
units, signs and labels.  SYNTHETIC inputs only; nothing here is field or vendor data.
"""
from __future__ import annotations

import math

import pytest

from core.engineering import casing_persistence as CP
from core.engineering import mud_volume_persistence as MV
from core.engineering.engines.anti_collision import AntiCollisionEngine as AC
from core.engineering.engines.bit_performance import BitPerformanceEngine as BP
from core.engineering.engines.fishing import FishingEngine as FI
from core.engineering.engines.trajectory import TrajectoryCalculator as TR
from core.engineering.engines.well_control import WellControlEngine as WC


# ---------------------------------------------------------------------------------------- anti-collision
def _station(md, tvd=0.0, north=0.0, east=0.0, **extra):
    return dict(md=md, tvd=tvd, north=north, east=east, **extra)


def _pair(ref_extra=None, off_extra=None, offset_east=10.0, offset_tvd_shift=0.0):
    ref = [_station(0.0, **(ref_extra or {})), _station(100.0, tvd=100.0, **(ref_extra or {}))]
    off = [_station(0.0, tvd=offset_tvd_shift, east=offset_east, **(off_extra or {})),
           _station(100.0, tvd=100.0 + offset_tvd_shift, east=offset_east, **(off_extra or {}))]
    return ref, off


@pytest.mark.parametrize("bad", [
    [_station(-1.0), _station(10.0)],               # negative MD
    [_station(10.0), _station(10.0)],               # zero-length interval
    [_station(10.0), _station(5.0)],                # MD going backwards
])
def test_ac_refuses_invalid_station_md(bad):
    ref, _off = _pair()
    assert not AC.screen_clearance(bad, ref).success


def test_ac_refuses_a_negative_sigma():
    ref, off = _pair(ref_extra=dict(sigma_north=-1.0, sigma_east=0.0, sigma_tvd=0.0),
                     off_extra=dict(sigma_north=1.0, sigma_east=0.0, sigma_tvd=0.0))
    assert not AC.screen_clearance(ref, off).success


def test_ac_combines_sigma_root_sum_square():
    # north sigmas 3 and 4 -> sqrt(9 + 16) = 5; east / tvd 0; separation 10 (east) -> SF = 10 / 5 = 2
    ref, off = _pair(ref_extra=dict(sigma_north=3.0, sigma_east=0.0, sigma_tvd=0.0),
                     off_extra=dict(sigma_north=4.0, sigma_east=0.0, sigma_tvd=0.0))
    result = AC.screen_clearance(ref, off)
    assert result.success, result.error
    closest = result.values["closest_approach"]
    assert closest["combined_sigma"] == pytest.approx(5.0)
    assert closest["separation_factor"] == pytest.approx(2.0)


def test_ac_partial_uncertainty_gives_no_separation_factor():
    ref, off = _pair(ref_extra=dict(sigma_north=3.0), off_extra=dict(sigma_north=4.0))
    result = AC.screen_clearance(ref, off)
    assert result.success, result.error
    assert result.values["closest_approach"]["separation_factor"] is None
    assert result.values["uncertainty"]["available"] is False


def test_ac_clearance_needs_both_radii_and_subtracts_them():
    ref, off = _pair(ref_extra=dict(wellbore_radius=1.0))
    one = AC.screen_clearance(ref, off)
    assert one.success and one.values["closest_approach"]["clearance"] is None
    ref, off = _pair(ref_extra=dict(wellbore_radius=1.0), off_extra=dict(wellbore_radius=2.0))
    both = AC.screen_clearance(ref, off)
    assert both.values["closest_approach"]["clearance"] == pytest.approx(10.0 - 3.0)


def test_ac_distance_is_three_dimensional():
    # offset 6 east and 8 deeper at every MD -> sqrt(36 + 64) = 10
    ref, off = _pair(offset_east=6.0, offset_tvd_shift=8.0)
    result = AC.screen_clearance(ref, off)
    assert result.values["minimum_separation"] == pytest.approx(10.0)


def test_ac_refuses_trajectories_without_common_md():
    ref = [_station(0.0), _station(100.0, tvd=100.0)]
    off = [_station(200.0, tvd=200.0, east=5.0), _station(300.0, tvd=300.0, east=5.0)]
    assert not AC.screen_clearance(ref, off).success


def test_ac_threshold_must_be_positive_and_touching_it_is_an_event():
    ref, off = _pair()
    assert not AC.screen_clearance(ref, off, collision_threshold=0).success
    scan = AC.screen_clearance(ref, off, collision_threshold=10.0).values["collision_scan"]
    assert scan["status"] == "alert" and scan["minimum_margin"] == pytest.approx(0.0)
    assert len(scan["events"]) == 2                 # both stations sit exactly on the threshold


def test_ac_never_claims_iscwsa():
    ref, off = _pair()
    result = AC.screen_clearance(ref, off)
    assert result.metadata["iscwsa_compliant"] is False
    assert result.values["uncertainty"]["iscwsa_applied"] is False


# ---------------------------------------------------------------------------------------- bit performance
def test_bp_revolutions_use_mean_rpm():
    # ((100 + 140) / 2) x 10 h x 60 / 1000 = 72 k.rev
    result = BP.bit_revolutions(100, 140, 10)
    assert result.value == pytest.approx(72.0)
    assert not BP.bit_revolutions(140, 100, 10).success


def test_bp_weighted_rop_undefined_and_excluded_rows():
    none = BP.weighted_rop([{"depth_in": 100, "depth_out": None, "hours_on_bottom": 5}])
    assert none.success and none.value is None
    mixed = BP.weighted_rop([
        {"depth_in": 1000, "depth_out": 1100, "hours_on_bottom": 10},     # 100 m / 10 h
        {"depth_in": 1100, "depth_out": 1000, "hours_on_bottom": 10},     # out < in: excluded whole
    ])
    assert mixed.value == pytest.approx(10.0)
    assert mixed.values["excluded_rows"] == 1
    assert any("excluded" in w for w in mixed.warnings)


def test_bp_d_exponent_uses_lbf_form():
    rop, rpm, wob, bit = 50.0, 120.0, 30000.0, 8.5
    expected = math.log10(rop / (60 * rpm)) / math.log10(12 * wob / (1e6 * bit))
    assert BP.d_exponent(rop, rpm, wob, bit).value == pytest.approx(round(expected, 4))


def test_bp_cost_per_foot_hourly_rig_rate_and_full_cycle():
    # 24,000 $/day = 1,000 $/h: (1,000 x 10 + 5,000) / 1,000 ft = 15 $/ft; with 20 rotating h: 35 $/ft
    assert BP.cost_per_foot(24000, 10, 5000, 1000).value == pytest.approx(15.0)
    assert BP.cost_per_foot(24000, 10, 5000, 1000, rotating_hours=20).value == pytest.approx(35.0)


# ---------------------------------------------------------------------------------------- fishing
def test_fi_adjusted_weight_and_zero_wall():
    # 2.67 x (5.0^2 - 4.276^2) = 2.67 x 6.715824 = 17.93 lb/ft
    assert FI.adjusted_weight(5.0, 4.276).value == pytest.approx(17.93, abs=0.01)
    assert not FI.adjusted_weight(5.0, 5.0).success


def test_fi_free_point():
    # 735294 x 10 in x 19.5 lb/ft / 50,000 lbf = 2867.65 ft
    assert FI.free_point(10.0, 19.5, 50000.0).value == pytest.approx(2867.65, abs=0.1)
    assert not FI.free_point(10.0, 19.5, 0.0).success


def test_fi_stretch_falls_with_mud_weight():
    # 10,000^2 x (65.44 - 1.44 x 10) / 96,250,000 = 1e8 x 51.04 / 9.625e7 = 53.03 in
    assert FI.string_stretch(10000.0, 10.0).value == pytest.approx(53.03, abs=0.01)
    assert FI.string_stretch(10000.0, 12.0).value < FI.string_stretch(10000.0, 10.0).value


def test_fi_stretch_in_air_matches_hookes_law_for_a_hanging_bar():
    """D81: a bar hanging under its own weight stretches rho g L^2 / (2E) - quadratic in length.  Steel
    65.44 ppg = 65.44 x 7.48052 / 1728 lb/in^3, E = 30e6 psi; L = 5,000 ft = 60,000 in."""
    rho = 65.44 * 7.48052 / 1728.0
    expected = rho * 60000.0 ** 2 / (2 * 30.0e6)                    # = 17.0 in
    assert FI.string_stretch(5000.0, 0.0).value == pytest.approx(expected, rel=2e-3)
    assert FI.string_stretch(10000.0, 0.0).value == pytest.approx(4 * FI.string_stretch(5000.0, 0.0).value,
                                                                  rel=1e-3)


def test_fi_jar_forces():
    # buoyed 100,000 x 0.85 = 85,000; up = 85,000 + 20,000 = 105,000; setting 0.8 x 105,000 = 84,000
    result = FI.jar_operating_range(100000.0, 0.85, 20000.0)
    assert result.values["upward_force_lbs"] == 105000
    assert result.values["downward_force_lbs"] == 85000
    assert result.values["recommended_jar_setting_lbs"] == 84000


def test_fi_overshot_needs_clearance():
    assert FI.overshot_fit(5.0, 5.0).values["compatible"] is False
    assert FI.overshot_fit(5.0, 5.25).values["compatible"] is True


# ---------------------------------------------------------------------------------------- trajectory wrapper
SURVEYS = [{"md": 0.0, "inc": 0.0, "azi": 0.0},
           {"md": 300.0, "inc": 0.0, "azi": 90.0},
           {"md": 600.0, "inc": 30.0, "azi": 90.0}]


def test_tr_wrapper_passes_vs_azimuth_and_maps_axes():
    north_vs = TR.calculate(SURVEYS, vs_azimuth=0.0)[-1]
    east_vs = TR.calculate(SURVEYS, vs_azimuth=90.0)[-1]
    assert east_vs["east"] > 50 and abs(east_vs["north"]) < 1e-6     # due-east build
    assert east_vs["vs"] == pytest.approx(east_vs["east"])
    assert north_vs["vs"] == pytest.approx(0.0, abs=1e-6)
    assert north_vs["hd"] == pytest.approx(math.hypot(north_vs["north"], north_vs["east"]))


def test_tr_wrapper_passes_the_dls_unit():
    # 30 deg over 300 m: 3.0 deg/30 m; the same dogleg per 30.48 m (100 ft) is 3.048
    per_30m = TR.calculate(SURVEYS, dls_unit="deg/30m")[-1]["dls"]
    per_100ft = TR.calculate(SURVEYS, dls_unit="deg/100ft")[-1]["dls"]
    assert per_30m == pytest.approx(3.0, rel=1e-6)
    assert per_100ft == pytest.approx(3.048, rel=1e-6)


# ---------------------------------------------------------------------------------------- well control
def test_wc_kill_mw_icp_fcp():
    # 10 + 520 / (0.052 x 10,000) = 11.0 ppg; ICP 800 + 500 = 1300; FCP 800 x 11 / 10 = 880
    assert WC.calculate_kill_mw(10.0, 520.0, 10000.0) == pytest.approx(11.0)
    assert not WC.kill_mw(10.0, 520.0, 0.0).success
    assert WC.calculate_icp(800.0, 500.0) == pytest.approx(1300.0)
    assert WC.calculate_fcp(800.0, 11.0, 10.0) == pytest.approx(880.0)


def test_wc_maasp_refuses_frac_below_mud():
    assert not WC.maasp(max_allowable_mw_ppg=9.0, current_mw_ppg=10.0, shoe_tvd_ft=5000.0).success


def test_wc_lot_surface_pressure_adds_to_the_mud_head():
    # frac EMW = 10 + 520 / (0.052 x 5,000) = 12 ppg -> MAASP = (12 - 10) x 0.052 x 5,000 = 520 psi
    result = WC.kick_tolerance(mw_ppg=10.0, shoe_tvd_ft=5000.0, current_tvd_ft=8000.0,
                               lot_pressure_psi=520.0, influx_emw_ppg=2.0,
                               annular_capacity_bbl_ft=0.05, formation_emw_ppg=10.5)
    assert result.success, result.error
    assert result.values["maasp_psi"] == pytest.approx(520.0, abs=0.5)


def test_wc_trip_margin_sign():
    # 10.5 ppg mud over a 10.0 ppg pore pressure = +0.5 ppg overbalance
    result = WC.trip_margin(mw_ppg=10.5, formation_emw_ppg=10.0)
    assert result.success, result.error
    assert result.value == pytest.approx(0.5)


# ---------------------------------------------------------------------------------------- mud volume snapshot
def test_mv_unknown_stays_unknown_through_snapshot_and_rerun():
    snap = MV.build_snapshot(inputs={"additions_bbl": 5.0, "losses_bbl": float("nan")}, method="m")
    assert snap["parameters"]["active_volume_bbl"] is None
    assert snap["parameters"]["losses_bbl"] is None
    assert MV.snapshot_to_engine_args(snap)["active_volume_bbl"] is None
    assert not MV.recalculate_from_snapshot(snap).success


def test_mv_summary_keeps_net_change():
    summary = MV.result_summary({"active_volume_bbl": 500.0, "final_volume_bbl": 510.0, "net_change_bbl": 10.0})
    assert summary["net_change_bbl"] == 10.0


# ---------------------------------------------------------------------------------------- casing snapshot
def test_cp_absent_loads_stay_absent_and_labels_and_source_are_kept():
    snap = CP.build_snapshot(inputs={"od_in": 9.625, "id_in": 8.835, "grade": "L80"}, method="m",
                             source={"architecture_revision": 3})
    assert snap["parameters"]["internal_pressure_psi"] is None
    assert CP.snapshot_to_engine_args(snap)["internal_pressure_psi"] is None
    assert snap["parameters"]["grade"] == "L80"
    assert snap["source"] == {"architecture_revision": 3}


def test_cp_summary_keeps_collapse_rating():
    assert CP.result_summary({"collapse_rating_psi": 2023.4})["collapse_rating_psi"] == 2023.4
