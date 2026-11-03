"""M106: multi-target (chained curve-hold) and S-profile solvers.

Goldens are forward-constructed: a profile with known inclinations, azimuths and lengths is integrated here
with planar arc + tangent geometry written in this file (not the solver's algebra, not ``design_plan``); the
solver must recover the profile from the resulting target centres. Infeasible cases return a structured code.
The solver claims feasibility only; nothing is minimised.
"""
from __future__ import annotations

import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import well_plan_designer as wpd  # noqa: E402


def _unit(inc, azi):
    i, a = math.radians(inc), math.radians(azi)
    return (math.sin(i) * math.cos(a), math.sin(i) * math.sin(a), math.cos(i))


def _arc(p, t0, inc1, azi1, dls):
    """End point of a constant-curvature arc from direction t0 to (inc1, azi1) at ``dls`` deg/30 m."""
    t1 = _unit(inc1, azi1)
    phi = math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(t0, t1)))))
    if phi < 1e-12:
        return p, t1, 0.0
    radius = 5400.0 / (math.pi * dls)
    normal = tuple((b - math.cos(phi) * a) / math.sin(phi) for a, b in zip(t0, t1))
    end = tuple(x + radius * (math.sin(phi) * t + (1 - math.cos(phi)) * n) for x, t, n in zip(p, t0, normal))
    return end, t1, radius * phi


def _hold(p, t, length):
    return tuple(x + length * c for x, c in zip(p, t))


def _target(name, p):
    return {"name": name, "north": p[0], "east": p[1], "tvd": p[2]}


# ---- forward-constructed goldens ------------------------------------------------------------------------
LEGS = ((30.0, 45.0, 3.0, 400.0), (50.0, 80.0, 2.5, 300.0), (20.0, 100.0, 2.0, 250.0))   # inc, azi, dls, hold


def _three_target_world():
    p, t, md = (0.0, 0.0, 500.0), _unit(0.0, 0.0), 500.0
    targets, mds = [], []
    for number, (inc, azi, dls, hold) in enumerate(LEGS, 1):
        p, t, curve = _arc(p, t, inc, azi, dls)
        p = _hold(p, t, hold)
        md += curve + hold
        targets.append(_target(f"T{number}", p))
        mds.append(md)
    return targets, mds


def test_three_targets_build_turn_and_drop_are_recovered():
    targets, mds = _three_target_world()
    answer = wpd.solve_multi_target(targets, kop_md=500.0, dls=[leg[2] for leg in LEGS])
    assert answer["feasible"] and answer["code"] == "OK", answer["reason"]
    for leg, (inc, azi, _dls, hold) in zip(answer["legs"], LEGS):
        assert leg["inc"] == pytest.approx(inc, abs=1e-7) and leg["azi"] == pytest.approx(azi, abs=1e-7)
        assert leg["hold_length"] == pytest.approx(hold, abs=1e-6)
    assert [leg["target_md"] for leg in answer["legs"]] == pytest.approx(mds, abs=1e-6)
    assert answer["td_md"] == pytest.approx(mds[-1], abs=1e-6)
    verification = answer["verification"]
    assert verification["converged"] and all(r["distance"] < 1e-6 for r in verification["targets"])
    kinds = [s["type"] for s in answer["segments"]]
    assert kinds == ["hold", "curve", "hold", "curve", "hold", "curve", "hold"]
    assert answer["legs"][2]["inc"] < answer["legs"][1]["inc"]               # leg 3 drops (and turns)


def test_hold_after_a_target_is_honoured():
    p, t = (0.0, 0.0, 500.0), _unit(0.0, 0.0)
    p, t, _ = _arc(p, t, 25.0, 10.0, 3.0)
    t1 = _hold(p, t, 200.0)
    after = _hold(t1, t, 150.0)                                              # 150 m hold after T1
    p2, t2, _ = _arc(after, t, 40.0, 60.0, 2.0)
    t2_point = _hold(p2, t2, 300.0)
    answer = wpd.solve_multi_target([_target("T1", t1), _target("T2", t2_point)], kop_md=500.0, dls=[3.0, 2.0],
                                    hold_after=[150.0])
    assert answer["feasible"], answer["reason"]
    assert answer["legs"][1]["kop_md"] == pytest.approx(answer["legs"][0]["target_md"] + 150.0)
    assert answer["legs"][1]["inc"] == pytest.approx(40.0, abs=1e-7)
    assert answer["legs"][1]["hold_length"] == pytest.approx(300.0, abs=1e-6)


def test_one_target_matches_the_m86_curve_hold_solver():
    target = {"north": 300.0, "east": 400.0, "tvd": 1500.0}
    single = wpd.solve_build_hold(target, kop_md=500.0, dls=3.0)
    multi = wpd.solve_multi_target([target], kop_md=500.0, dls=3.0)
    assert multi["feasible"] and multi["segments"] == single["segments"]


def test_s_profile_is_recovered_from_a_forward_constructed_target():
    theta, tangent, final_inc, final_hold, azi = 35.0, 600.0, 5.0, 250.0, 120.0
    p, t = (0.0, 0.0, 500.0), _unit(0.0, azi)
    p, t, build = _arc(p, t, theta, azi, 2.0)
    p = _hold(p, t, tangent)
    p, t, drop = _arc(p, t, final_inc, azi, 1.5)
    p = _hold(p, t, final_hold)
    answer = wpd.solve_s_profile(_target("S", p), kop_md=500.0, build_dls=2.0, drop_dls=1.5, final_inc=final_inc,
                                 final_hold=final_hold)
    assert answer["feasible"], answer["reason"]
    assert answer["inc"] == pytest.approx(theta, abs=1e-7) and answer["hold_length"] == pytest.approx(tangent, abs=1e-6)
    assert answer["azi"] == pytest.approx(azi, abs=1e-9)
    assert answer["td_md"] == pytest.approx(500.0 + build + tangent + drop + final_hold, abs=1e-6)
    assert [s["type"] for s in answer["segments"]] == ["hold", "curve", "hold", "curve", "hold"]
    assert answer["verification"]["converged"] and answer["verification"]["targets"][0]["distance"] < 1e-6


def test_s_profile_back_to_vertical_from_an_offset_tie_in():
    tie = {"md": 200.0, "inc": 0.0, "azi": 0.0, "tvd": 199.5, "north": 3.0, "east": -2.0}
    p, t = (3.0, -2.0, 199.5 + 600.0), _unit(0.0, 0.0)                   # KOP at 800 m MD
    p, t, _ = _arc(p, t, 28.0, 300.0, 2.5)
    p = _hold(p, t, 450.0)
    p, t, _ = _arc(p, t, 0.0, 300.0, 2.0)
    answer = wpd.solve_s_profile(_target("V", p), kop_md=800.0, build_dls=2.5, drop_dls=2.0, tie_in=tie)
    assert answer["feasible"], answer["reason"]
    assert answer["inc"] == pytest.approx(28.0, abs=1e-7) and answer["hold_length"] == pytest.approx(450.0, abs=1e-6)


def test_the_objective_and_acceptance_are_stated_without_an_optimality_claim():
    targets, _ = _three_target_world()
    answer = wpd.solve_multi_target(targets, kop_md=500.0, dls=[leg[2] for leg in LEGS])
    assert "Nothing is minimised" in answer["objective"] and "not an optimum" in answer["objective"]
    assert "canonical minimum-curvature engine" in answer["convergence"]
    assert answer["verification"]["tolerance_m"] == wpd.TARGET_TOLERANCE_M


# ---- infeasible / limits ------------------------------------------------------------------------------------
def test_multi_target_infeasible_cases_are_structured():
    targets, _ = _three_target_world()
    rates = [leg[2] for leg in LEGS]
    assert wpd.solve_multi_target([], kop_md=500.0, dls=3.0)["code"] == "NO_TARGETS"
    limited = wpd.solve_multi_target(targets, kop_md=500.0, dls=rates, dls_limit=2.8)
    assert limited["code"] == "DLS_LIMIT" and limited["failed_leg"] == 1 and limited["segments"] == []
    capped = wpd.solve_multi_target(targets, kop_md=500.0, dls=rates, max_inc=45.0)
    assert capped["code"] == "INC_LIMIT" and capped["failed_leg"] == 2 and "Leg 2 (T2)" in capped["reason"]
    behind = [targets[0], {"name": "Back", "north": targets[0]["north"] - 10 * _unit(30, 45)[0],
                           "east": targets[0]["east"] - 10 * _unit(30, 45)[1],
                           "tvd": targets[0]["tvd"] - 10 * _unit(30, 45)[2]}]
    refused = wpd.solve_multi_target(behind, kop_md=500.0, dls=3.0)
    assert refused["code"] == "TARGET_BEHIND" and refused["failed_leg"] == 2
    tight = [targets[0], {"name": "Tight", "north": targets[0]["north"] + 20.0, "east": targets[0]["east"] - 20.0,
                          "tvd": targets[0]["tvd"] + 5.0}]
    inside = wpd.solve_multi_target(tight, kop_md=500.0, dls=[3.0, 1.0])
    assert inside["code"] == "INSIDE_TURN_RADIUS" and inside["failed_leg"] == 2
    assert wpd.solve_multi_target(targets, kop_md=500.0, dls=[3.0, 2.0])["code"] == "INVALID_INPUT"
    assert wpd.solve_multi_target(targets, kop_md=float("nan"), dls=rates)["code"] == "INVALID_INPUT"
    assert wpd.solve_multi_target(targets, kop_md=500.0, dls=rates, hold_after=-1.0)["code"] == "INVALID_INPUT"


def test_s_profile_infeasible_cases_are_structured():
    far = {"north": 800.0, "east": 0.0, "tvd": 3000.0}
    ok = wpd.solve_s_profile(far, kop_md=500.0, build_dls=2.0, drop_dls=1.5, final_hold=300.0)
    assert ok["feasible"]
    cases = (
        (dict(tie_in={"md": 600.0, "inc": 10.0, "azi": 0.0}), "NOT_SUPPORTED"),
        (dict(target={"north": 800.0, "east": 0.0, "tvd": 900.0}), "INSIDE_TURN_RADIUS"),
        (dict(target={"north": 0.0, "east": 0.0, "tvd": 3000.0}), "NO_DISPLACEMENT"),
        (dict(target={"north": 800.0, "east": 0.0, "tvd": 400.0}), "TARGET_NOT_BELOW_KOP"),
        (dict(max_inc=20.0), "INC_LIMIT"),
        (dict(dls_limit=1.8), "DLS_LIMIT"),
        (dict(final_inc=40.0), "NO_DROP"),
        (dict(drop_dls=0.0), "NON_POSITIVE_RATE"),
        (dict(kop_md=float("inf")), "INVALID_INPUT"),
        (dict(final_inc=95.0), "INVALID_INPUT"),
    )
    base = dict(target=far, kop_md=500.0, build_dls=2.0, drop_dls=1.5, final_hold=300.0)
    for change, code in cases:
        kwargs = dict(base, **change)
        answer = wpd.solve_s_profile(kwargs.pop("target"), **kwargs)
        assert answer["code"] == code and not answer["feasible"] and answer["segments"] == [], (change, answer)


def test_a_path_that_misses_a_target_is_never_reported_as_solved(monkeypatch):
    targets, _ = _three_target_world()
    real = wpd.closest_on_path

    def off_by_a_metre(stations, point):
        near = real(stations, point)
        return dict(near, distance=near["distance"] + 1.0)
    monkeypatch.setattr(wpd, "closest_on_path", off_by_a_metre)
    answer = wpd.solve_multi_target(targets, kop_md=500.0, dls=[leg[2] for leg in LEGS])
    assert answer["code"] == "NOT_CONVERGED" and not answer["feasible"] and answer["segments"] == []
    assert answer["verification"]["converged"] is False


def test_a_target_reached_out_of_order_is_not_converged(monkeypatch):
    targets, _ = _three_target_world()
    real = wpd.closest_on_path

    def early(stations, point):
        near = real(stations, point)
        return dict(near, md=near["md"] - 500.0)                       # passes the centre at another MD
    monkeypatch.setattr(wpd, "closest_on_path", early)
    answer = wpd.solve_multi_target(targets, kop_md=500.0, dls=[leg[2] for leg in LEGS])
    assert answer["code"] == "NOT_CONVERGED"


# ---- desktop -------------------------------------------------------------------------------------------------
def test_designer_panel_solves_through_all_targets_and_an_s_profile(tmp_path, monkeypatch):
    from PySide6 import QtWidgets

    from tabs import well_plan_designer_panel as panel_module
    from tabs.trajectory_viewer import TrajectoryViewerTab
    from tests.test_m70_integrity import _open, _seed

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    manager = _open(tmp_path / "m106.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    widget = TrajectoryViewerTab(manager)
    try:
        widget.set_context(ids["A"][0])
        designer = widget.plan_designer
        targets, _ = _three_target_world()
        for t in targets:
            designer.add_target(t["name"], t["north"], t["east"], t["tvd"], 1.0)
        designer.kop_spin.setValue(500.0)
        designer.build_spin.setValue(3.0)
        designer.dls_limit_spin.setValue(0.0)                               # no limit
        designer.solver_mode_combo.setCurrentIndex(designer.solver_mode_combo.findData(panel_module.SOLVE_ALL))
        assert designer.solve_btn.text() == "Solve through all targets" and not designer.drop_spin.isEnabled()
        answer = designer.solve_to_target()
        assert answer["feasible"] and designer.result.ok
        assert all(t["hit"] for t in designer.result.targets)                # every target within 1 m on the plan
        assert "not an optimum" in designer.summary_label.text()
        designer.max_inc_spin.setValue(20.0)
        refused = designer.solve_to_target()
        assert refused["code"] == "INC_LIMIT" and "[INC_LIMIT]" in designer.summary_label.text()
        designer.max_inc_spin.setValue(90.0)
        designer.solver_mode_combo.setCurrentIndex(designer.solver_mode_combo.findData(panel_module.SOLVE_S))
        assert designer.drop_spin.isEnabled()
        designer.target_table.setRowCount(0)
        designer.add_target("S", 800.0, 0.0, 3000.0, 1.0)
        designer.build_spin.setValue(2.0)
        designer.drop_spin.setValue(1.5)
        designer.final_hold_spin.setValue(300.0)
        s_answer = designer.solve_to_target()
        assert s_answer["feasible"] and designer.result.ok and designer.result.targets[0]["hit"]
        assert designer.segment_table.rowCount() == len(s_answer["segments"])
    finally:
        widget.compare_panel.wait_until_idle()
        widget.deleteLater()
        app.processEvents()
        manager.close()
