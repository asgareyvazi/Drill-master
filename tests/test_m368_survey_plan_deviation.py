"""M368: actual survey vs plan - centreline deviation, target status, persistence, replay and the 3D-view path.

SYNTHETIC. Golden values are by hand, independent of the production code:

* Horizontal plan heading north at TVD 1000 m; a surveyed point 500 m along, 10 m east and 5 m shallower is
  10 m RIGHT and 5 m HIGH, 3D distance sqrt(10^2 + 5^2) = 11.1803 m, along 0.
* M132 survey (vertical to 500 m, build to 30 deg at azimuth 90 by MD 1000 m, R = 500 / (pi/6) = 954.93 m):
  MD 1000 m is at East R (1 - cos 30) = 127.94 m, TVD 500 + R sin 30 = 977.46 m. A 300 m hold at 30 deg / 90 deg
  ends at East 277.94 m, TVD 1237.27 m. Target T1 (East 400, TVD 1200) projects beyond that end, so its
  centreline miss is the distance from the end point: sqrt(122.06^2 + 37.27^2) = 127.62 m > radius 30 = MISS.
"""
from __future__ import annotations

import copy
import dataclasses
import math

import pytest

from core import calculation_history as ch
from core import directional_plans as dp
from core import survey_plan_deviation as spd
from core import survey_revisions as sr
from tests.test_m70_integrity import _open, _seed

ROWS = [{"md": 0, "inc": 0, "azi": 0}, {"md": 500, "inc": 0, "azi": 0}, {"md": 1000, "inc": 30, "azi": 90},
        {"md": 1500, "inc": 30, "azi": 90}]
R = 500 / (math.pi / 6)
E1000, T1000 = R * (1 - math.cos(math.radians(30))), 500 + R * math.sin(math.radians(30))
E1300, T1300 = E1000 + 300 * 0.5, T1000 + 300 * math.cos(math.radians(30))


def _st(md, n, e, tvd, inc, azi):
    return {"md": md, "north": n, "east": e, "tvd": tvd, "inc": inc, "azi": azi}


def _snap(plan, actual, tolerance=None, targets=()):
    return {"plan": {"stations": plan, "targets": list(targets)}, "survey": {"stations": actual},
            "tolerance_m": tolerance}


HORIZONTAL = [_st(1000, 0, 0, 1000, 90, 0), _st(2000, 1000, 0, 1000, 90, 0)]


def test_right_and_high_decomposition_matches_the_hand_values():
    actual = [_st(1000, 0, 0, 1000, 90, 0), _st(1500, 500, 10, 995, 90, 0), _st(1600, 600, -10, 1003, 90, 0)]
    result = spd.evaluate(_snap(HORIZONTAL, actual, tolerance=11.0))
    first, right, left = result["rows"]
    assert first["distance_m"] == pytest.approx(0.0, abs=1e-6) and first["status"] == spd.WITHIN
    assert right["distance_m"] == pytest.approx(math.sqrt(125), abs=1e-6)
    assert (right["right_m"], right["high_m"], right["along_m"]) == pytest.approx((10.0, 5.0, 0.0), abs=1e-6)
    assert right["tvd_difference_m"] == pytest.approx(-5.0) and right["plan_md"] == pytest.approx(1500.0)
    assert right["status"] == spd.OUTSIDE                         # 11.18 > 11
    assert (left["right_m"], left["high_m"]) == pytest.approx((-10.0, -3.0), abs=1e-6)
    assert result["outside"] == 1 and result["max_distance_md"] == pytest.approx(1500.0)


def test_without_a_tolerance_nothing_is_judged():
    result = spd.evaluate(_snap(HORIZONTAL, [_st(1500, 500, 10, 995, 90, 0)]))
    assert result["rows"][0]["status"] == spd.NO_TOLERANCE and result["outside"] == 0
    assert "No tolerance declared" in "\n".join(spd.summary_lines(dict(result, snapshot={})))


def test_vertical_plan_has_no_high_side_or_right():
    plan = [_st(0, 0, 0, 0, 0, 0), _st(1000, 0, 0, 1000, 0, 0)]
    row = spd.evaluate(_snap(plan, [_st(500, 3, 4, 500, 0, 0)]))["rows"][0]
    assert row["distance_m"] == pytest.approx(5.0) and row["high_m"] is None and row["right_m"] is None
    assert "undefined" in row["frame_note"]


def test_stations_beyond_the_plan_end_and_above_the_tie_in_are_labelled():
    actual = [_st(500, 0, 0, 500, 0, 0), _st(2500, 1500, 0, 1000, 90, 0)]
    result = spd.evaluate(_snap(HORIZONTAL, actual))
    assert result["above_tie_in"] == 1 and len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["position_note"] == spd.BEYOND_END and row["along_m"] == pytest.approx(500.0)


def test_target_status_hit_miss_not_reached_and_no_radius():
    actual = [_st(1000, 0, 0, 1000, 90, 0), _st(2000, 1000, 0, 1000, 90, 0)]
    targets = [{"name": "H", "north": 500, "east": 3, "tvd": 1004, "radius": 6},        # 5 m off: HIT
               {"name": "M", "north": 500, "east": 30, "tvd": 1000, "radius": 6},       # 30 m off: MISS
               {"name": "N", "north": 500, "east": 3, "tvd": 1004},                      # no radius
               {"name": "D", "north": 1500, "east": 0, "tvd": 1200, "radius": 50},      # deeper, beyond the end
               {"name": "X", "north": None, "east": 0, "tvd": 1000}]
    rows = {t["name"]: t for t in spd.evaluate(_snap(HORIZONTAL, actual, targets=targets))["targets"]}
    assert rows["H"]["status"] == spd.HIT and rows["H"]["distance_m"] == pytest.approx(5.0)
    assert rows["M"]["status"] == spd.MISS and rows["M"]["distance_m"] == pytest.approx(30.0)
    assert rows["N"]["status"] == spd.NO_RADIUS
    assert rows["D"]["status"] == spd.NOT_REACHED
    assert rows["X"]["status"] == spd.NOT_ASSESSED and rows["X"]["distance_m"] is None


@pytest.fixture
def env(tmp_path, monkeypatch):
    manager = _open(tmp_path / "m368.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    well, bore = ids["A"]
    survey = sr.save_revision(manager, well, ROWS[:3], wellbore_id=bore, depth_datum="RKB", azimuth_reference="true")
    tie = sr.tie_in_from_revision(survey, md=1000)
    plan = dp.save_plan(manager, well_id=well, wellbore_id=bore, name="SYN plan", inputs=dp.plan_inputs(
        [{"type": "hold", "length": 300.0}], tie_in=tie, azimuth_reference="true", depth_datum="RKB",
        targets=[{"name": "T1", "north": 0.0, "east": 400.0, "tvd": 1200.0, "radius": 30.0}]))
    yield {"manager": manager, "well": well, "bore": bore, "survey": survey, "plan": plan, "ids": ids}
    manager.close()


def _actual(env, rows, **kw):
    args = dict(wellbore_id=env["bore"], depth_datum="RKB", azimuth_reference="true")
    args.update(kw)
    return sr.save_revision(env["manager"], env["well"], rows, **args)


def test_an_on_plan_survey_has_zero_deviation_and_the_target_miss_matches_the_hand_value(env):
    on_plan = _actual(env, ROWS[:3] + [{"md": 1300, "inc": 30, "azi": 90}])
    result = spd.run(env["manager"], on_plan["id"], env["plan"]["id"], tolerance_m=0.01)
    assert result["status"] == spd.COMPUTED, result.get("reason")
    assert result["above_tie_in"] == 2 and [r["md"] for r in result["rows"]] == pytest.approx([1000, 1300])
    assert all(r["distance_m"] == pytest.approx(0.0, abs=1e-6) and r["status"] == spd.WITHIN for r in result["rows"])
    target = result["targets"][0]
    assert target["status"] == spd.MISS
    assert target["distance_m"] == pytest.approx(math.hypot(400 - E1300, 1200 - T1300), abs=1e-3)
    assert target["distance_m"] == pytest.approx(127.62, abs=0.01)


def test_turn_right_and_drop_are_signed_right_and_low(env):
    off = _actual(env, ROWS[:3] + [{"md": 1300, "inc": 26, "azi": 100}])
    row = spd.run(env["manager"], off["id"], env["plan"]["id"])["rows"][-1]
    assert row["right_m"] > 0 and row["high_m"] < 0 and row["status"] == spd.NO_TOLERANCE


@pytest.mark.parametrize("change, message", [
    (dict(depth_datum="MSL"), "depth datum differs"),
    (dict(azimuth_reference="grid"), "azimuth reference differs"),
])
def test_reference_mismatch_is_refused_never_converted(env, change, message):
    other = _actual(env, ROWS[:3] + [{"md": 1300, "inc": 30, "azi": 90}], **change)
    result = spd.run(env["manager"], other["id"], env["plan"]["id"])
    assert result["status"] == spd.NOT_ASSESSED and message in result["reason"] and result["rows"] == []


def test_a_survey_in_another_frame_above_the_tie_in_is_refused(env):
    moved = [dict(r) for r in ROWS[:3]] + [{"md": 1300, "inc": 30, "azi": 90}]
    moved[1]["inc"] = 1.0
    result = spd.run(env["manager"], _actual(env, moved)["id"], env["plan"]["id"])
    assert result["status"] == spd.NOT_ASSESSED and "not in the same frame" in result["reason"]


def test_untied_plan_other_well_and_bad_tolerance_are_refused(env):
    m = env["manager"]
    untied = dp.save_plan(m, well_id=env["well"], wellbore_id=env["bore"], name="SYN own frame",
                          inputs=dp.plan_inputs([{"type": "hold", "length": 100.0}], azimuth_reference="true",
                                                depth_datum="RKB"))
    assert "not tied in" in spd.run(m, env["survey"]["id"], untied["id"])["reason"]
    other_well = env["ids"]["B"][0]
    foreign = sr.save_revision(m, other_well, ROWS, depth_datum="RKB", azimuth_reference="true")
    assert "different wells" in spd.run(m, foreign["id"], env["plan"]["id"])["reason"]
    for bad in (0, -1.0, float("nan")):
        assert "positive number" in spd.run(m, env["survey"]["id"], env["plan"]["id"], tolerance_m=bad)["reason"]
    assert "does not exist" in spd.run(m, 99999, env["plan"]["id"])["reason"]


def test_saved_case_replays_match_and_a_tampered_snapshot_is_unreadable(env):
    m = env["manager"]
    off = _actual(env, ROWS[:3] + [{"md": 1300, "inc": 28, "azi": 95}])
    result = spd.run(m, off["id"], env["plan"]["id"], tolerance_m=5.0)
    case = spd.save_case(m, result, well_id=env["well"])
    assert case["method"] == spd.METHOD_ID and case["method_version"] == spd.METHOD_VERSION
    assert case["inputs"]["survey_stations_sha256"]["value"] == off["stations_sha256"]
    entry = next(e for e in ch.load_history(m, sources=["Calculation case"]) if e.record_id == case["id"])
    assert ch.recalculate_entry(entry, m)["status"] == "MATCH"
    tampered = copy.deepcopy(entry.inputs)
    tampered["snapshot"]["value"]["survey"]["stations"][-1]["east"] += 1.0
    out = ch.recalculate_entry(dataclasses.replace(entry, inputs=tampered), m)
    assert out["status"] == "UNREADABLE" and "SHA-256" in out["detail"]
    changed = copy.deepcopy(entry.results)
    changed["station_001_distance_m"]["value"] += 0.5
    out = ch.recalculate_entry(dataclasses.replace(entry, results=changed), m)
    assert out["status"] == "DIFFERENT" and [d["field_id"] for d in out["differences"]] == ["station_001_distance_m"]
    assert ch.recalculate_entry(dataclasses.replace(entry, version="M368 v0"), m)["status"] == "NOT_REPRODUCIBLE"
    with pytest.raises(ValueError, match="another well"):
        spd.save_case(m, result, well_id=env["ids"]["B"][0])
    with pytest.raises(ValueError, match="not computed"):
        spd.save_case(m, spd.run(m, off["id"], env["plan"]["id"], tolerance_m=-1), well_id=env["well"])


# ---- UI: W6 Trajectory › 3D view layer panel › "Plan vs actual…" -------------------------------------------------
def test_layer_panel_button_opens_the_dialog_which_compares_and_saves(env):
    from PySide6 import QtWidgets

    from tabs.trajectory_layers_panel import TrajectoryLayersPanel

    _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    m = env["manager"]
    off = _actual(env, ROWS[:3] + [{"md": 1300, "inc": 28, "azi": 95}])
    panel = TrajectoryLayersPanel(db_manager=m)
    try:
        panel.set_scope(env["well"], env["bore"])
        assert panel.wait()
        assert not panel.deviation_btn.isEnabled() and panel.plan_deviation_dialog() is None   # working survey
        panel.select(base=off["id"], plan=None)
        assert panel.wait() and not panel.deviation_btn.isEnabled()
        panel.select(base=off["id"], plan=env["plan"]["id"])
        assert panel.wait() and panel.deviation_btn.isEnabled()
        panel.deviation_btn.click()
        dialog = panel.deviation_dialog
        assert dialog is not None and dialog.survey_id == off["id"] and dialog.plan_id == env["plan"]["id"]
        dialog.tolerance_edit.setText("1,5")
        assert dialog.run() is None and "not a number" in dialog.summary.text()
        dialog.tolerance_edit.setText("2")
        result = dialog.run()
        assert result["status"] == spd.COMPUTED and dialog.station_table.rowCount() == 2
        assert dialog.target_table.rowCount() == 1 and dialog.target_table.item(0, 1).text() == spd.MISS
        assert dialog.save_btn.isEnabled()
        case = dialog.save()
        assert case and "Saved as calculation case" in dialog.summary.text() and not dialog.save_btn.isEnabled()
        dialog.close()
        dialog.deleteLater()
    finally:
        panel.shutdown()
        panel.deleteLater()
