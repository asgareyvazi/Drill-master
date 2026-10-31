"""M52 centre-to-centre trajectory comparison / clearance SCREENING (core/trajectory_compare.py).

References are analytical geometry (a circle of constant build rate, straight
skew lines, parallel verticals), independent of the minimum-curvature formula
under test.  The canonical engine supplies station positions; the module's
own contribution - exact arc interpolation and continuous closest approach -
is what these cases check.  Synthetic numbers only.
"""
from __future__ import annotations

import math

import pytest

from core import trajectory_compare as tc
from core.well_trajectory import compose_well_trajectory


def traj(*stations):
    return compose_well_trajectory([{"md": md, "inc": inc, "azi": azi} for md, inc, azi in stations])


def well(name="W", northing=0.0, easting=0.0, rte_msl=0.0):
    return {"name": name, "northing": northing, "easting": easting, "rte_msl": rte_msl}


# ---- exact interpolation -----------------------------------------------------------------------------
def test_interpolation_follows_the_constant_build_circle():
    length = 300.0                                   # 0 -> 90 deg in one segment: radius R = L / (pi/2)
    path = tc.path_from_trajectory(traj((0, 0, 0), (length, 90, 0)))
    radius = length / (math.pi / 2)
    for s in (0.0, 17.3, 75.0, 150.0, 222.2, 300.0):
        north, east, down = path.position(s)
        assert north == pytest.approx(radius * (1 - math.cos(s / radius)), abs=1e-6)
        assert down == pytest.approx(radius * math.sin(s / radius), abs=1e-6)
        assert east == pytest.approx(0.0, abs=1e-9)
        inc, _ = path.angles(s)
        assert inc == pytest.approx(math.degrees(s / radius), abs=1e-6)


def test_interpolation_reproduces_the_engine_stations():
    trajectory = traj((0, 0, 0), (250, 12, 40), (600, 35, 75), (900, 35, 75), (1200, 60, 120))
    path = tc.path_from_trajectory(trajectory)
    for station in trajectory.stations:
        assert path.position(station.md) == pytest.approx((station.north, station.east, station.tvd), abs=1e-6)


def test_a_straight_segment_is_a_line_and_outside_the_range_is_none():
    path = tc.path_from_trajectory(traj((0, 30, 90), (200, 30, 90)))
    north, east, down = path.position(100)
    assert (north, east, down) == pytest.approx((0.0, 100 * math.sin(math.radians(30)),
                                                 100 * math.cos(math.radians(30))), abs=1e-9)
    assert path.position(200.5) is None and path.position(-1) is None


# ---- continuous closest approach ----------------------------------------------------------------------
def test_closest_approach_between_skew_lines_is_found_between_stations():
    reference = traj((0, 0, 0), (300, 0, 0))                     # vertical at the origin
    offset = traj((0, 45, 180), (300, 45, 180))                  # heads south at 45 deg
    result = tc.compare_wells(reference, well("R"), offset, well("O", northing=100.0, easting=5.0),
                              same_crs_confirmed=True, step=25.0)
    assert result.status == tc.ASSESSED and result.label == tc.LABEL
    assert result.closest["distance_m"] == pytest.approx(5.0, abs=0.01)
    assert result.closest["reference_md"] == pytest.approx(100.0, abs=0.01)
    assert result.closest["offset_md"] == pytest.approx(100 / math.sin(math.radians(45)), abs=0.01)
    stations_only = min(math.dist((0, 0, r), (100 - o * math.sin(math.radians(45)), 5, o * math.cos(math.radians(45))))
                        for r in (0, 300) for o in (0, 300))
    assert stations_only > 50                                    # a station-pair method would miss it


def test_parallel_verticals_are_separated_by_the_wellhead_offset():
    a, b = traj((0, 0, 0), (1000, 0, 0)), traj((0, 0, 0), (1000, 0, 0))
    result = tc.compare_wells(a, well("A", 1000.0, 2000.0), b, well("B", 1006.0, 2008.0),
                              same_crs_confirmed=True, step=50.0)
    assert result.closest["distance_m"] == pytest.approx(10.0, abs=0.01)
    assert all(r["distance_m"] == pytest.approx(10.0, abs=0.01) for r in result.rows)


def test_rotary_table_elevations_put_both_wells_on_one_vertical_datum():
    a, b = traj((0, 0, 0), (1000, 0, 0)), traj((0, 0, 0), (1000, 0, 0))
    result = tc.compare_wells(a, well("A", rte_msl=10.0), b, well("B", easting=3.0, rte_msl=14.0),
                              same_crs_confirmed=True, step=50.0)
    row = next(r for r in result.rows if r["reference_md"] == 500.0)
    assert row["offset_md"] == pytest.approx(504.0, abs=0.01)    # same depth below MSL, 4 m more MD
    assert row["distance_m"] == pytest.approx(3.0, abs=0.01)


def test_the_global_minimum_wins_over_a_local_one():
    # North 100 m, two 90 deg turns of radius 50 m (to east, then south), then 200 m south:
    # the return leg runs along east = 100 m from north 100 m back past north 0.
    u_path = tc.path_from_trajectory(traj((0, 90, 0), (100, 90, 0), (100 + 25 * math.pi, 90, 90),
                                          (100 + 50 * math.pi, 90, 180), (300 + 50 * math.pi, 90, 180)))
    assert u_path.position(100 + 25 * math.pi) == pytest.approx((150.0, 50.0, 0.0), abs=1e-6)
    point = (0.0, 100.0, 0.0)                     # 100 m from the first leg, ON the return leg
    md, distance = tc.closest_point(u_path, point, step=40.0)
    assert distance == pytest.approx(0.0, abs=1e-4)
    assert md == pytest.approx(200 + 50 * math.pi, abs=1e-3)


def test_a_deeper_minimum_between_coarse_samples_is_found_although_another_sample_is_closer():
    # Same U path.  The point is 55 m from the first leg AT a sample (MD 0) and 45 m from the
    # return leg at MD 200 + 50*pi, which lies between samples (step 200): the best SAMPLE is on
    # the first leg (55 < sqrt(45^2 + 42.9^2)), the true minimum is on the return leg.
    u_path = tc.path_from_trajectory(traj((0, 90, 0), (100, 90, 0), (100 + 25 * math.pi, 90, 90),
                                          (100 + 50 * math.pi, 90, 180), (300 + 50 * math.pi, 90, 180)))
    point = (0.0, 55.0, 0.0)
    samples = u_path.sample_mds(200.0)
    nearest_sample = min(math.dist(u_path.position(m), point) for m in samples)
    assert nearest_sample == pytest.approx(55.0, abs=1e-6)          # the premise: a sample on the wrong leg wins
    md, distance = tc.closest_point(u_path, point, step=200.0)
    assert distance == pytest.approx(45.0, abs=1e-4)
    assert md == pytest.approx(200 + 50 * math.pi, abs=1e-3)


def test_a_180_degree_dogleg_is_not_assessed_instead_of_dividing_by_zero():
    reversing = traj((0, 90, 0), (100, 90, 0), (200, 90, 180))
    result = tc.compare_plan(traj((0, 90, 0), (100, 90, 0)), reversing)
    assert result.status == tc.NOT_ASSESSED and "arc undefined" in result.reasons[0]
    with pytest.raises(ValueError, match="arc undefined"):
        tc.path_from_trajectory(reversing).position(150)


# ---- plan vs actual -----------------------------------------------------------------------------------
def test_dropping_below_a_horizontal_plan_is_low_and_drifting_clockwise_is_right():
    plan = traj((0, 90, 0), (1000, 90, 0))
    low = tc.compare_plan(traj((0, 80, 0), (500, 80, 0)), plan, step=50.0)
    last = low.rows[-1]
    assert last["high_m"] == pytest.approx(-500 * math.cos(math.radians(80)), abs=0.01)
    assert last["right_m"] == pytest.approx(0.0, abs=0.01)
    assert last["plan_md"] == pytest.approx(500 * math.sin(math.radians(80)), abs=0.01)
    right = tc.compare_plan(traj((0, 90, 10), (500, 90, 10)), plan, step=50.0)
    assert right.rows[-1]["right_m"] == pytest.approx(500 * math.sin(math.radians(10)), abs=0.01)
    assert right.rows[-1]["high_m"] == pytest.approx(0.0, abs=0.01)
    assert abs(right.rows[-1]["along_m"]) < 0.01                 # closest point: the miss is normal to the plan


def test_actual_beyond_the_plan_is_noted():
    result = tc.compare_plan(traj((0, 0, 0), (600, 0, 0)), traj((0, 0, 0), (400, 0, 0)), step=50.0)
    assert "outside the plan MD range" in result.rows[-1]["note"] and result.warnings


# ---- NOT ASSESSED states --------------------------------------------------------------------------------
def test_unconfirmed_crs_and_missing_datum_are_not_assessed_with_every_reason():
    a, b = traj((0, 0, 0), (500, 0, 0)), traj((0, 0, 0), (500, 0, 0))
    result = tc.compare_wells(a, well("A"), b, {"name": "B", "northing": None, "easting": 1.0, "rte_msl": "x"},
                              same_crs_confirmed=False)
    assert result.status == tc.NOT_ASSESSED and result.rows == [] and result.closest is None
    text = " | ".join(result.reasons)
    assert "CRS" in text and "offset well: northing is missing" in text and "offset well: rte_msl is missing" in text


def test_too_few_stations_is_not_assessed():
    result = tc.compare_plan(traj((100, 0, 0)), traj((0, 0, 0), (100, 0, 0)))
    assert result.status == tc.NOT_ASSESSED and "actual" in result.reasons[0]


# ---- plan import ---------------------------------------------------------------------------------------
def test_plan_table_reads_aliases_and_converts_feet_when_stated():
    rows = tc.plan_rows_from_table([["Measured Depth (ft)", "Inclination", "Azimuth"],
                                    ["0", "0", "0"], ["1000", "10", "45"], ["", "", ""]], length_unit="ft")
    assert rows == [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": pytest.approx(304.8), "inc": 10.0, "azi": 45.0}]


@pytest.mark.parametrize("table, message", [
    ([["MD", "Inc"], ["0", "0"], ["1", "1"]], "Missing plan column"),
    ([["MD", "Inc", "Azi"], ["0", "0", "0"], ["10", "abc", "0"]], "Row 3"),
    ([["MD", "Inc", "Azi"], ["0", "0", "0"]], "at least two"),
    ([], "empty"),
])
def test_bad_plan_tables_are_refused_with_the_reason(table, message):
    with pytest.raises(tc.PlanImportError, match=message):
        tc.plan_rows_from_table(table)


def test_plan_csv_and_xlsx_files(tmp_path):
    csv_path = tmp_path / "plan.csv"
    csv_path.write_text("MD;INC;AZI\n0;0;0\n500;20;90\n", encoding="utf-8")
    assert tc.read_plan_file(str(csv_path))[1] == {"md": 500.0, "inc": 20.0, "azi": 90.0}
    from openpyxl import Workbook
    workbook = Workbook()
    for row in (("md", "inc", "azi"), (0, 0, 0), (400, 15, 30)):
        workbook.active.append(row)
    xlsx = tmp_path / "plan.xlsx"
    workbook.save(xlsx)
    assert tc.read_plan_file(str(xlsx))[1] == {"md": 400.0, "inc": 15.0, "azi": 30.0}
    with pytest.raises(tc.PlanImportError):
        tc.read_plan_file(str(tmp_path / "plan.pdf"))


def test_calculation_record_carries_label_contract_and_inputs():
    result = tc.compare_plan(traj((0, 0, 0), (300, 0, 0)), traj((0, 0, 0), (300, 0, 0)))
    record = tc.calculation_record(result, inputs={"actual_well_id": 1, "plan_rows": 2})
    assert record["description"] == tc.LABEL and record["method"].startswith("M52")
    assert record["results_json"]["contract"]["uncertainty"].startswith("none")
    assert record["parameters_json"]["inputs"] == {"actual_well_id": 1, "plan_rows": 2}
