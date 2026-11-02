"""M72: immutable survey revisions, survey-pinned plan tie-ins, the build-hold solver, plan-vs-actual targets.

SYNTHETIC databases (fresh and upgraded). Independent references: the planar
closed form of a build arc, HD = R(1 - cos t), TVD = KOP + R sin t with
R = 5400/(pi*DLS), and the M55 golden J-profile (TD 1623.9032011 m).
"""
from __future__ import annotations

import math
import sqlite3

import pytest
from sqlalchemy import text

from core import directional_plans as dp
from core import survey_revisions as sr
from core.authorization import AuthorizationError
from core.storage_guards import trigger_statements
from core.well_plan_designer import design_plan, solve_build_hold
from tests.test_database_migration_acceptance import _build_old_schema
from tests.test_m70_integrity import NEW_TABLES, _count, _open, _seed

R3 = 5400.0 / (math.pi * 3.0)                      # build radius at 3 deg/30 m
J_STATIONS = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 500.0, "inc": 0.0, "azi": 0.0},
              {"md": 650.0, "inc": 15.0, "azi": 135.0}, {"md": 800.0, "inc": 30.0, "azi": 135.0}]


@pytest.fixture(params=["fresh", "upgraded"])
def env(request, tmp_path, monkeypatch):
    path = tmp_path / f"{request.param}.sqlite"
    if request.param == "upgraded":
        _build_old_schema(path, 5)
        with sqlite3.connect(path) as connection:
            for table in NEW_TABLES + ("survey_revisions",):
                connection.execute(f"DROP TABLE IF EXISTS {table}")
    manager = _open(path, tmp_path, monkeypatch)
    yield manager, path, _seed(manager)
    manager.close()


def _save(manager, well, rows=J_STATIONS, **kw):
    kw.setdefault("depth_datum", "RKB")
    kw.setdefault("azimuth_reference", "true")
    return sr.save_revision(manager, well, rows, **kw)


# ---- preview rules -----------------------------------------------------------------------------
def test_preview_converts_feet_exactly_and_refuses_undeclared_units_references_and_datums():
    checked = sr.preview([{"md": 1000, "inc": 0, "azi": 0}, {"md": 2000, "inc": 5, "azi": 10}],
                         source_unit="ft", depth_datum="RKB", azimuth_reference="true")
    assert checked.ok and [s["md"] for s in checked.stations] == [304.8, 609.6]
    assert "Unknown depth unit" in sr.preview(J_STATIONS, source_unit="yd", depth_datum="RKB").errors[0]
    assert "azimuth reference" in sr.preview(J_STATIONS, azimuth_reference="north", depth_datum="RKB").errors[0]
    assert "depth datum" in sr.preview(J_STATIONS, azimuth_reference="true").errors[0]


def test_preview_orders_deduplicates_and_reports_conflicts_and_bad_values():
    rows = [{"md": 100, "inc": 1, "azi": 370}, {"md": 0, "inc": 0, "azi": 0}, {"md": 100, "inc": 1, "azi": 10}]
    checked = sr.preview(rows, depth_datum="RKB", azimuth_reference="true")
    assert checked.ok and [s["md"] for s in checked.stations] == [0.0, 100.0]
    assert any("normalised to 10" in w for w in checked.warnings)
    assert any("sorted by MD" in w for w in checked.warnings) and any("kept once" in w for w in checked.warnings)
    conflict = sr.preview([{"md": 0, "inc": 0, "azi": 0}, {"md": 50, "inc": 1, "azi": 0},
                           {"md": 50, "inc": 2, "azi": 0}], depth_datum="RKB", azimuth_reference="true")
    assert not conflict.ok and "appears twice with different angles" in conflict.errors[0]
    bad = sr.preview([{"md": 0, "inc": 0, "azi": 0}, {"md": 10, "inc": 181, "azi": 0},
                      {"md": -1, "inc": 0, "azi": 0}, {"md": float("nan"), "inc": 0, "azi": 0}], depth_datum="RKB", azimuth_reference="true")
    assert len(bad.errors) == 3 and not bad.ok


# ---- storage -----------------------------------------------------------------------------------
def test_a_revision_stores_canonical_positions_matching_the_planar_closed_form(env):
    manager, _path, ids = env
    rev = _save(manager, ids["A"][0])
    end = rev["results"][-1]
    assert rev["revision"] == 1 and rev["mode"] == "initial" and rev["station_count"] == 4
    assert end["tvd"] == pytest.approx(500 + R3 * math.sin(math.radians(30)), abs=1e-6)      # 786.4788976
    assert end["hd"] == pytest.approx(R3 * (1 - math.cos(math.radians(30))), abs=1e-6)      # 76.7617893
    assert rev["stations_sha256"] == sr.stations_sha256(rev["stations"]) and rev["method_version"] == sr.SURVEY_REVISION_VERSION


def test_saved_revisions_are_immutable_and_cascade_with_their_well(env):
    manager, path, ids = env
    rev = _save(manager, ids["A"][0], wellbore_id=ids["A"][1])
    with sqlite3.connect(path) as connection:
        assert set(trigger_statements()) <= {r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'")}
        for column, value in (("stations_json", "[]"), ("revision", 7), ("depth_datum", "MSL"), ("well_id", ids["B"][0])):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(f"UPDATE survey_revisions SET {column} = ? WHERE id = ?", (value, rev["id"]))
    with pytest.raises(Exception, match="immutable"):
        with manager.session_scope() as session:
            session.execute(text("UPDATE survey_revisions SET note='x'"))
    assert manager.delete_hierarchy_entity("well", ids["A"][0]) is True
    assert _count(path, "SELECT COUNT(*) FROM survey_revisions") == 0


def test_replace_append_and_branch_build_new_revisions_and_never_touch_the_parent(env):
    manager, _path, ids = env
    well = ids["A"][0]
    first = _save(manager, well)
    appended = _save(manager, well, [{"md": 830.0, "inc": 30.0, "azi": 135.0}], mode="append", parent_id=first["id"])
    assert appended["station_count"] == 5 and appended["parent_id"] == first["id"] and appended["revision"] == 2
    with pytest.raises(sr.SurveyRevisionError, match="deeper than the parent"):
        _save(manager, well, [{"md": 700.0, "inc": 1.0, "azi": 0.0}], mode="append", parent_id=appended["id"])
    branch = _save(manager, well, [{"md": 700.0, "inc": 25.0, "azi": 90.0}, {"md": 760.0, "inc": 35.0, "azi": 80.0}],
                   mode="branch", parent_id=first["id"], tie_in_md=650.0)
    assert [s["md"] for s in branch["stations"]] == [0.0, 500.0, 650.0, 700.0, 760.0]
    with pytest.raises(sr.SurveyRevisionError, match="not a station"):
        _save(manager, well, J_STATIONS[2:], mode="branch", parent_id=first["id"], tie_in_md=600.0)
    replaced = _save(manager, well, J_STATIONS[:3], mode="replace", parent_id=branch["id"])
    assert replaced["revision"] == 4 and sr.get_revision(manager, first["id"])["stations"] == first["stations"]
    with pytest.raises(sr.SurveyRevisionError, match="mixing references"):
        _save(manager, well, J_STATIONS, mode="replace", parent_id=first["id"], azimuth_reference="grid")
    with pytest.raises(sr.SurveyRevisionError, match="parent revision of this well"):
        _save(manager, ids["B"][0], J_STATIONS, mode="replace", parent_id=first["id"])
    with pytest.raises(sr.SurveyRevisionError, match="does not belong"):
        _save(manager, well, wellbore_id=ids["B"][1])
    assert [r["revision"] for r in sr.list_revisions(manager, well)] == [4, 3, 2, 1]


def test_viewers_cannot_insert_and_nobody_can_update_through_the_service_layer(tmp_path, monkeypatch):
    from tests.test_data_layer_authorization import Principal
    path = tmp_path / "authz.sqlite"
    manager = _open(path, tmp_path, monkeypatch)
    ids = _seed(manager)
    users = dict(sqlite3.connect(path).execute("SELECT username, id FROM users").fetchall())
    manager.enforce_authorization(Principal("viewer", users["admin"], "viewer"))
    with pytest.raises((AuthorizationError, PermissionError)):
        _save(manager, ids["A"][0])
    manager.close()


def test_snapshot_freezes_survey_points_and_compare_reports_differences(env):
    manager, _path, ids = env
    well = ids["A"][0]
    manager.save_survey_points([dict(s, well_id=well) for s in J_STATIONS])
    first = sr.snapshot_survey_points(manager, well, depth_datum="RKB", azimuth_reference="true")
    assert first["source_type"] == "survey_points" and first["station_count"] == 4 and first["mode"] == "initial"
    edited = [dict(s) for s in J_STATIONS[:3]] + [{"md": 800.0, "inc": 31.0, "azi": 135.0},
                                                   {"md": 900.0, "inc": 31.0, "azi": 135.0}]
    second = _save(manager, well, edited, mode="replace", parent_id=first["id"])
    diff = sr.compare_revisions(first, second)
    assert diff["comparable"] and diff["common"] == 4 and diff["added"] == [900.0] and diff["removed"] == []
    (change,) = diff["changed"]
    assert change["md"] == 800.0 and change["inc"] == pytest.approx(1.0) and "tvd" in change
    other = dict(second, azimuth_reference="grid")
    assert sr.compare_revisions(first, other)["comparable"] is False


# ---- plans pinned to a survey revision ---------------------------------------------------------
def test_a_plan_tied_to_a_revision_starts_at_its_station_and_records_the_hash(env):
    manager, _path, ids = env
    well, bore = ids["A"]
    rev = _save(manager, well, [{"md": 0, "inc": 0, "azi": 0}, {"md": 300, "inc": 0, "azi": 0}], wellbore_id=bore)
    tie = sr.tie_in_from_revision(rev)
    inputs = dp.plan_inputs([{"type": "hold", "length": 200.0}, {"type": "curve", "inc": 30.0, "azi": 135.0, "dls": 3.0}],
                            tie_in=tie)
    plan = dp.save_plan(manager, well_id=well, wellbore_id=bore, name="tied", inputs=inputs)
    first = plan["results"]["stations"][0]
    assert first["md"] == 300.0 and first["tvd"] == pytest.approx(300.0)
    assert plan["inputs"]["tie_in"]["survey_sha256"] == rev["stations_sha256"]
    end = plan["results"]["stations"][-1]       # same J-profile geometry as the golden case, from MD 300
    assert end["tvd"] == pytest.approx(500 + R3 * 0.5, abs=1e-6)


@pytest.mark.parametrize("tamper", ["sha", "station", "missing", "other_well"])
def test_a_tie_in_that_does_not_match_its_revision_is_refused(env, tamper):
    manager, _path, ids = env
    well = ids["A"][0]
    rev = _save(manager, well)
    tie = sr.tie_in_from_revision(rev)
    target_well = well
    if tamper == "sha":
        tie["survey_sha256"] = "0" * 64
    elif tamper == "station":
        tie["tvd"] += 0.5
    elif tamper == "missing":
        tie.pop("north")
    else:
        target_well = ids["B"][0]
    with pytest.raises(dp.PlanIntegrityError):
        dp.save_plan(manager, well_id=target_well, name="bad", inputs=dp.plan_inputs(
            [{"type": "hold", "length": 100.0}], tie_in=tie))


# ---- the build-hold solver ---------------------------------------------------------------------
def _golden_target():
    hd = 488.7133898
    return {"tvd": 1500.0, "north": -hd * math.cos(math.radians(45)), "east": hd * math.sin(math.radians(45))}


def test_the_solver_recovers_the_golden_j_profile_and_the_forward_engine_hits_the_centre():
    answer = solve_build_hold(_golden_target(), kop_md=500.0, dls=3.0)
    assert answer["feasible"] and answer["inc"] == pytest.approx(30.0, abs=1e-6)
    assert answer["azi"] == pytest.approx(135.0, abs=1e-9)
    assert answer["hold_length"] == pytest.approx(1623.9032011 - 800.0, abs=1e-6)
    plan = design_plan(answer["segments"], targets=[dict(_golden_target(), name="T", radius=1.0)])
    assert plan.ok and plan.stations[-1]["md"] == pytest.approx(1623.9032011, abs=1e-6)
    assert plan.targets[0]["distance"] < 1e-6 and plan.targets[0]["hit"] is True


def test_the_solver_handles_a_survey_tie_in_and_a_target_straight_below():
    tie = {"md": 300.0, "inc": 0.0, "azi": 0.0, "tvd": 299.0, "north": 2.0, "east": -1.0}
    target = {"tvd": 1200.0, "north": 2.0 - 400.0, "east": -1.0 + 150.0}
    answer = solve_build_hold(target, kop_md=500.0, dls=2.5, tie_in=tie)
    plan = design_plan(answer["segments"], tie_in=tie, targets=[dict(target, name="T", radius=0.5)])
    assert answer["feasible"] and plan.targets[0]["distance"] < 1e-6
    below = solve_build_hold({"tvd": 900.0, "north": 2.0, "east": -1.0}, kop_md=400.0, dls=2.0, tie_in=tie)
    assert below["feasible"] and below["inc"] == 0.0 and all(s["type"] == "hold" for s in below["segments"])


@pytest.mark.parametrize("target,kw,reason", [
    ({"tvd": 600.0, "north": 300.0, "east": 0.0}, {}, "inside the build circle"),
    ({"tvd": 400.0, "north": 10.0, "east": 0.0}, {}, "not below the KOP"),
    ({"tvd": 2000.0, "north": 100.0, "east": 0.0}, {"tie_in": {"md": 100.0, "inc": 5.0, "azi": 0.0}}, "vertical tie-in"),
    ({"tvd": 1100.0, "north": 3000.0, "east": 0.0}, {"max_inc": 60.0}, "exceeds the limit"),
    ({"tvd": float("inf"), "north": 1.0, "east": 0.0}, {}, "finite"),
    ({"tvd": 1500.0, "north": 1.0, "east": 0.0}, {"dls_value": 0.0}, "positive"),
    ({"tvd": 1500.0, "north": 1.0, "east": 0.0}, {"kop": 50.0, "tie_in": {"md": 100.0, "inc": 0.0, "azi": 0.0}}, "above the tie-in"),
])
def test_infeasible_targets_are_explained_never_approximated(target, kw, reason):
    answer = solve_build_hold(target, kop_md=kw.pop("kop", 500.0), dls=kw.pop("dls_value", 3.0), **kw)
    assert answer["feasible"] is False and reason in answer["reason"] and answer["segments"] == []


def test_a_target_on_the_build_circle_needs_no_tangent():
    theta = math.radians(40.0)
    target = {"tvd": 500.0 + R3 * math.sin(theta), "north": R3 * (1 - math.cos(theta)), "east": 0.0}
    answer = solve_build_hold(target, kop_md=500.0, dls=3.0)
    assert answer["feasible"] and answer["inc"] == pytest.approx(40.0, abs=1e-6) and answer["hold_length"] < 1e-5
