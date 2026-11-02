"""M86: curve-hold target solver from any tie-in direction, structured infeasibility, screening label.

Goldens are closed-form planar arc + tangent geometry derived by hand; the forward check uses the
canonical minimum-curvature engine through ``design_plan`` (not the solver's own algebra).
"""
from __future__ import annotations

import math
import os
import random

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import trajectory_compare as tc  # noqa: E402
from core.well_plan_designer import _max_inc_along_arc, _vector, design_plan, solve_build_hold  # noqa: E402

R3 = 5400.0 / (math.pi * 3.0)          # build radius at 3 deg/30 m
S, C = (lambda d: math.sin(math.radians(d))), (lambda d: math.cos(math.radians(d)))


def _hits(answer, target, tie):
    plan = design_plan(answer["segments"], tie_in=tie, targets=[dict(target, name="T", radius=0.5)])
    assert plan.ok, plan.error
    return plan.targets[0]["distance"]


def test_inclined_tie_in_build_golden():
    """Tie-in inc 30 azi 90; build to 50 deg in the vertical plane, then hold 400 m."""
    tie = {"md": 1000.0, "inc": 30.0, "azi": 90.0, "tvd": 950.0, "north": 5.0, "east": 200.0}
    d_east = R3 * (C(30) - C(50)) + 400 * S(50)
    d_tvd = R3 * (S(50) - S(30)) + 400 * C(50)
    target = {"tvd": 950.0 + d_tvd, "north": 5.0, "east": 200.0 + d_east}
    answer = solve_build_hold(target, kop_md=1000.0, dls=3.0, tie_in=tie)
    assert answer["feasible"] and answer["code"] == "OK"
    assert answer["inc"] == pytest.approx(50.0, abs=1e-7) and answer["azi"] == pytest.approx(90.0, abs=1e-7)
    assert answer["dogleg_deg"] == pytest.approx(20.0, abs=1e-7)
    assert answer["hold_length"] == pytest.approx(400.0, abs=1e-6)
    assert answer["curve_length"] == pytest.approx(R3 * math.radians(20), abs=1e-6)
    assert _hits(answer, target, tie) < 1e-6


def test_drop_golden_with_a_tangent_before_the_kop():
    """Tie-in inc 40 azi 0, hold 100 m to the KOP, drop to 10 deg, hold 250 m."""
    tie = {"md": 800.0, "inc": 40.0, "azi": 0.0, "tvd": 760.0, "north": 120.0, "east": -3.0}
    n0, t0 = 120.0 + 100 * S(40), 760.0 + 100 * C(40)
    target = {"north": n0 + R3 * (C(10) - C(40)) + 250 * S(10),
              "tvd": t0 + R3 * (S(40) - S(10)) + 250 * C(10), "east": -3.0}
    answer = solve_build_hold(target, kop_md=900.0, dls=3.0, tie_in=tie)
    assert answer["feasible"] and answer["inc"] == pytest.approx(10.0, abs=1e-7)
    assert answer["azi"] == pytest.approx(0.0, abs=1e-7) and answer["hold_length"] == pytest.approx(250.0, abs=1e-6)
    assert answer["segments"][0] == {"type": "hold", "length": pytest.approx(100.0)}
    assert answer["kop_tvd"] == pytest.approx(t0) and _hits(answer, target, tie) < 1e-6


def test_horizontal_turn_golden():
    """Horizontal tie-in heading north; turn 30 deg right in the horizontal plane, hold 500 m."""
    tie = {"md": 3000.0, "inc": 90.0, "azi": 0.0, "tvd": 2000.0, "north": 0.0, "east": 0.0}
    target = {"tvd": 2000.0, "north": R3 * S(30) + 500 * C(30), "east": R3 * (1 - C(30)) + 500 * S(30)}
    answer = solve_build_hold(target, kop_md=3000.0, dls=3.0, tie_in=tie)
    assert answer["feasible"] and answer["inc"] == pytest.approx(90.0, abs=1e-7)
    assert answer["azi"] == pytest.approx(30.0, abs=1e-7) and answer["hold_length"] == pytest.approx(500.0, abs=1e-6)
    assert _hits(answer, target, tie) < 1e-6


def test_target_straight_ahead_is_a_pure_hold():
    tie = {"md": 500.0, "inc": 25.0, "azi": 210.0, "tvd": 480.0, "north": 0.0, "east": 0.0}
    t = _vector(25.0, 210.0)
    target = {"north": 700 * t[0], "east": 700 * t[1], "tvd": 480.0 + 700 * t[2]}
    answer = solve_build_hold(target, kop_md=500.0, dls=2.0, tie_in=tie)
    assert answer["feasible"] and answer["dogleg_deg"] == pytest.approx(0.0, abs=1e-6)
    assert [s["type"] for s in answer["segments"]] == ["hold"] and answer["hold_length"] == pytest.approx(700.0)


def test_vertical_tie_in_is_unchanged_from_m72_golden():
    hd = 488.7133898
    target = {"tvd": 1500.0, "north": -hd * C(45), "east": hd * S(45)}
    answer = solve_build_hold(target, kop_md=500.0, dls=3.0)
    assert answer["inc"] == pytest.approx(30.0, abs=1e-6) and answer["azi"] == pytest.approx(135.0, abs=1e-9)
    assert answer["hold_length"] == pytest.approx(1623.9032011 - 800.0, abs=1e-6)


def test_random_feasible_targets_are_hit_by_the_forward_engine():
    rng = random.Random(86)
    solved = 0
    for _ in range(60):
        tie = {"md": 1000.0, "inc": rng.uniform(0, 70), "azi": rng.uniform(0, 360), "tvd": 900.0,
               "north": rng.uniform(-50, 50), "east": rng.uniform(-50, 50)}
        target = {"tvd": 900.0 + rng.uniform(300, 1500), "north": tie["north"] + rng.uniform(-1500, 1500),
                  "east": tie["east"] + rng.uniform(-1500, 1500)}
        answer = solve_build_hold(target, kop_md=1000.0 + rng.uniform(0, 100), dls=rng.uniform(1.5, 6.0),
                                  tie_in=tie, max_inc=180.0)
        if answer["feasible"]:
            solved += 1
            assert _hits(answer, target, tie) < 1e-5
        else:
            assert answer["code"] in {"INSIDE_TURN_RADIUS", "TURN_TOO_LARGE"} and answer["segments"] == []
    assert solved >= 40


@pytest.mark.parametrize("tie, target, kw, code", [
    ({"md": 1000.0, "inc": 30.0, "azi": 0.0, "tvd": 900.0},
     {"tvd": 900.0 - 300 * C(30), "north": -300 * S(30), "east": 0.0}, {}, "TARGET_BEHIND"),
    ({"md": 1000.0, "inc": 30.0, "azi": 0.0, "tvd": 900.0},
     {"tvd": 900.0, "north": 0.0, "east": 150.0}, {}, "INSIDE_TURN_RADIUS"),
    ({"md": 1000.0, "inc": 30.0, "azi": 0.0, "tvd": 900.0},
     {"tvd": 900.0 - 1000 * C(30), "north": -1000 * S(30), "east": 10.0}, {"max_inc": 180.0}, "TURN_TOO_LARGE"),
    ({"md": 2000.0, "inc": 85.0, "azi": 0.0, "tvd": 1500.0},
     {"tvd": 1300.0, "north": 2000.0, "east": 0.0}, {}, "INC_LIMIT"),
    ({"md": 1000.0, "inc": 30.0, "azi": 0.0, "tvd": 900.0},
     {"tvd": 1500.0, "north": 100.0, "east": 0.0}, {"kop_md": 900.0}, "KOP_ABOVE_TIE_IN"),
    ({"md": 1000.0, "inc": float("nan"), "azi": 0.0}, {"tvd": 1500.0, "north": 1.0, "east": 0.0}, {}, "INVALID_INPUT"),
    ({"md": 1000.0, "inc": 190.0, "azi": 0.0}, {"tvd": 1500.0, "north": 1.0, "east": 0.0}, {}, "INVALID_INPUT"),
    ({}, {"tvd": 1500.0, "north": 1.0, "east": 0.0}, {"dls": 0.0, "kop_md": 0.0}, "NON_POSITIVE_RATE"),
])
def test_infeasibility_is_structured(tie, target, kw, code):
    kwargs = {"kop_md": tie.get("md", 0.0), "dls": 3.0, **kw}
    answer = solve_build_hold(target, tie_in=tie, **kwargs)
    assert answer["feasible"] is False and answer["code"] == code and answer["reason"] and answer["segments"] == []


def test_inclination_limit_applies_along_the_arc_not_only_at_the_end():
    """An arc that dips past horizontal peaks between its end points (only relevant above 90 deg)."""
    t0 = _vector(80.0, 0.0)
    c = 0.5 / S(80)                                    # n perpendicular to t0 with n_z = -0.5
    n = (c * C(80), math.sqrt(1 - c * c), -0.5)
    phi = math.radians(150.0)
    end = [math.cos(phi) * x + math.sin(phi) * y for x, y in zip(t0, n)]
    end_inc = math.degrees(math.acos(end[2]))
    end_azi = math.degrees(math.atan2(end[1], end[0])) % 360.0
    sampled = max(math.degrees(math.acos(math.cos(p) * t0[2] + math.sin(p) * n[2]))
                  for p in (phi * k / 4000 for k in range(4001)))      # independent dense sampling
    assert end_inc < 118.0 < sampled
    assert _max_inc_along_arc(t0, n, phi) == pytest.approx(sampled, abs=1e-3)
    tie = {"md": 2000.0, "inc": 80.0, "azi": 0.0, "tvd": 1500.0, "north": 0.0, "east": 0.0}
    forward = design_plan([{"type": "curve", "inc": end_inc, "azi": end_azi, "dls": 3.0},
                           {"type": "hold", "length": 300}], tie_in=tie)
    assert forward.ok, forward.error
    last = forward.stations[-1]
    target = {"tvd": last["tvd"], "north": last["north"], "east": last["east"]}
    ok = solve_build_hold(target, kop_md=2000.0, dls=3.0, tie_in=tie, max_inc=130.0)
    assert ok["feasible"] and ok["dogleg_deg"] == pytest.approx(150.0, abs=1e-6)
    assert ok["max_inc_on_arc"] == pytest.approx(sampled, abs=1e-3)
    refused = solve_build_hold(target, kop_md=2000.0, dls=3.0, tie_in=tie, max_inc=118.0)
    assert refused["code"] == "INC_LIMIT"


def test_screening_label_wording():
    assert tc.LABEL.startswith("SCREENING — NO ISCWSA UNCERTAINTY — NOT APPROVED")


def test_designer_panel_solves_from_an_inclined_survey_tie_in(tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    from core import survey_revisions as sr
    from tabs.trajectory_viewer import TrajectoryViewerTab
    from tests.test_m70_integrity import _open, _seed
    from tests.test_m72_surveys_solver import J_STATIONS
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    manager = _open(tmp_path / "m86.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    widget = TrajectoryViewerTab(manager)
    try:
        widget.set_context(ids["A"][0])
        rev = sr.save_revision(manager, ids["A"][0], J_STATIONS, depth_datum="RKB", azimuth_reference="true")
        designer = widget.plan_designer
        designer.refresh_tie_ins()
        designer.tie_combo.setCurrentIndex(designer.tie_combo.findData(rev["id"]))   # ends at inc 30, azi 135
        designer.add_target("T", -700.0, 900.0, 1600.0, 5.0)
        designer.kop_spin.setValue(850.0)
        designer.build_spin.setValue(2.0)
        answer = designer.solve_to_target()
        assert answer["feasible"] and designer.result.ok and designer.result.targets[0]["distance"] < 1e-6
        assert "dogleg" in designer.summary_label.text()
        designer.add_target("Inside", -300.0, 305.0, 760.0, 5.0)
        designer.target_table.removeRow(0)
        refused = designer.solve_to_target()
        assert refused["feasible"] is False and f"[{refused['code']}]" in designer.summary_label.text()
    finally:
        widget.compare_panel.wait_until_idle()
        widget.deleteLater()
        app.processEvents()
        manager.close()
