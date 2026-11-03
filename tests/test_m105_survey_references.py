"""M105: explicit vertical depth-datum shift (new revision) and declared plan references.

Synthetic stations and elevations only.  The datum golden is plain arithmetic on the SOURCE
revision's stored results (offset = source elevation - target elevation), never the transform's
own output.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import directional_plans as dp  # noqa: E402
from core import survey_revisions as sr  # noqa: E402
from core import trajectory_compare as tc  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402
from tests.test_m105_survey_integrity import _tamper  # noqa: E402

# RKB is 30 m above MSL, ground level 5 m above MSL -> RKB->GL offset 25 m.
RKB_ELEV, GL_ELEV, OFFSET = 30.0, 5.0, 25.0
SURFACE_ROWS = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 300.0, "inc": 0.0, "azi": 0.0},
                {"md": 600.0, "inc": 20.0, "azi": 45.0}]
BELOW_GL_ROWS = [{"md": 30.0, "inc": 0.0, "azi": 0.0}, {"md": 300.0, "inc": 0.0, "azi": 0.0},
                 {"md": 600.0, "inc": 20.0, "azi": 45.0}, {"md": 900.0, "inc": 35.0, "azi": 60.0}]


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / "m105ref.sqlite"
    manager = _open(path, tmp_path, monkeypatch)
    ids = _seed(manager)
    yield manager, path, ids
    manager.close()


def _shift(manager, rev, **overrides):
    kwargs = dict(source_datum_elevation_m=RKB_ELEV, target_datum_elevation_m=GL_ELEV,
                  elevation_reference="MSL", parameter_source="synthetic rig survey")
    kwargs.update(overrides)
    return sr.transform_depth_datum(manager, rev["id"], kwargs.pop("to_datum", "GL"), **kwargs)


# ---- datum shift -------------------------------------------------------------------------------
def test_a_datum_shift_moves_every_md_and_tvd_by_the_stated_offset_as_a_new_revision(env):
    manager, _path, ids = env
    rev = sr.save_revision(manager, ids["A"][0], BELOW_GL_ROWS, depth_datum="RKB", azimuth_reference="true")
    new = _shift(manager, rev)
    assert new["id"] != rev["id"] and new["parent_id"] == rev["id"] and new["mode"] == "datum_transform"
    assert new["depth_datum"] == "GL" and new["azimuth_reference"] == "true"
    assert new["integrity"] == "VERIFIED" and new["results_integrity"] == "VERIFIED"
    assert sr.verify_results(new)["status"] == "MATCH"
    for old, shifted in zip(rev["results"], new["results"]):
        assert shifted["md"] == pytest.approx(old["md"] - OFFSET, abs=1e-9)
        assert shifted["tvd"] == pytest.approx(old["tvd"] - OFFSET, abs=1e-9)
        for key in ("inc", "azi", "north", "east", "vs", "hd", "dls"):
            assert shifted[key] == pytest.approx(old[key], abs=1e-9), key
    assert new["results"][0]["md"] == pytest.approx(5.0) and new["results"][0]["tvd"] == pytest.approx(5.0)
    import json
    provenance = json.loads(new["source_ref"])
    assert provenance["offset_m"] == OFFSET and provenance["elevation_reference"] == "MSL"
    assert provenance["from_datum"] == "RKB" and provenance["to_datum"] == "GL"
    assert provenance["source_stations_sha256"] == rev["stations_sha256"]
    assert provenance["method_version"] == sr.DATUM_TRANSFORM_VERSION
    assert sr.get_revision(manager, rev["id"])["stations"] == rev["stations"]        # source untouched
    # a revision on another datum is never compared with its source
    assert sr.compare_revisions(rev, new)["comparable"] is False


def test_shifting_back_restores_the_original_stations(env):
    manager, _path, ids = env
    rev = sr.save_revision(manager, ids["A"][0], BELOW_GL_ROWS, depth_datum="RKB", azimuth_reference="true")
    there = _shift(manager, rev)
    back = _shift(manager, there, to_datum="RKB", source_datum_elevation_m=GL_ELEV,
                  target_datum_elevation_m=RKB_ELEV)
    for a, b in zip(rev["stations"], back["stations"]):
        assert b == pytest.approx(a, abs=1e-9)
    assert sr.compare_revisions(rev, back)["changed"] == []


@pytest.mark.parametrize("overrides, message", [
    ({"source_datum_elevation_m": None}, "never assumed to be zero"),
    ({"target_datum_elevation_m": float("nan")}, "finite numbers"),
    ({"target_datum_elevation_m": RKB_ELEV}, "shift would be zero"),
    ({"elevation_reference": " "}, "measured from"),
    ({"parameter_source": ""}, "come from"),
    ({"to_datum": ""}, "target depth datum"),
    ({"to_datum": "rkb"}, "already referred"),
])
def test_incomplete_or_meaningless_datum_parameters_are_refused(env, overrides, message):
    manager, _path, ids = env
    rev = sr.save_revision(manager, ids["A"][0], BELOW_GL_ROWS, depth_datum="RKB", azimuth_reference="true")
    with pytest.raises(sr.SurveyRevisionError, match=message):
        _shift(manager, rev, **overrides)
    assert len(sr.list_revisions(manager, ids["A"][0])) == 1


def test_stations_above_the_new_datum_are_refused_never_dropped(env):
    manager, _path, ids = env
    rev = sr.save_revision(manager, ids["A"][0], SURFACE_ROWS, depth_datum="RKB", azimuth_reference="true")
    with pytest.raises(sr.SurveyRevisionError, match="above the GL datum.*never dropped"):
        _shift(manager, rev)


def test_an_inclined_first_station_is_refused(env):
    manager, _path, ids = env
    rows = [{"md": 100.0, "inc": 2.0, "azi": 0.0}, {"md": 400.0, "inc": 10.0, "azi": 0.0}]
    rev = sr.save_revision(manager, ids["A"][0], rows, depth_datum="RKB", azimuth_reference="true")
    with pytest.raises(sr.SurveyRevisionError, match="only exact when the hole above the first station is vertical"):
        _shift(manager, rev)


def test_a_tampered_source_is_refused_for_a_datum_shift(env):
    manager, path, ids = env
    rev = sr.save_revision(manager, ids["A"][0], BELOW_GL_ROWS, depth_datum="RKB", azimuth_reference="true")
    forged = [dict(r) for r in rev["results"]]
    forged[2]["tvd"] += 1.0
    tampered = _tamper(manager, path, rev["id"], results=forged)
    with pytest.raises(sr.SurveyRevisionError):
        _shift(manager, tampered)


def test_an_azimuth_transform_now_records_its_results_hash(env):
    manager, _path, ids = env
    rev = sr.save_revision(manager, ids["A"][0], BELOW_GL_ROWS, depth_datum="RKB", azimuth_reference="magnetic")
    new = sr.transform_revision(manager, rev["id"], "true", declination_deg=4.0, parameter_source="synthetic",
                                reference_date="2026-01-01")
    assert new["results_integrity"] == "VERIFIED"


# ---- plan references ---------------------------------------------------------------------------
def test_plan_inputs_without_references_keep_the_legacy_shape_and_report_not_declared():
    inputs = dp.plan_inputs([{"type": "hold", "length": 100.0}])
    assert "references" not in inputs
    assert dp.plan_references(inputs) == {"azimuth_reference": None, "depth_datum": None, "declared": False}
    assert dp.reference_text(inputs) == "azimuth_reference=NOT DECLARED; depth_datum=NOT DECLARED"
    declared = dp.plan_inputs([{"type": "hold", "length": 100.0}], azimuth_reference="Grid", depth_datum=" MSL ")
    assert declared["references"] == {"azimuth_reference": "grid", "depth_datum": "MSL"}
    with pytest.raises(dp.PlanIntegrityError, match="Unknown azimuth reference"):
        dp.plan_inputs([{"type": "hold", "length": 100.0}], azimuth_reference="north-ish")


def test_a_plan_contradicting_or_tied_to_an_unverified_survey_is_refused(env):
    manager, path, ids = env
    well = ids["A"][0]
    rev = sr.save_revision(manager, well, BELOW_GL_ROWS, depth_datum="RKB", azimuth_reference="true")
    tie = sr.tie_in_from_revision(rev)
    segments = [{"type": "hold", "length": 100.0}]
    with pytest.raises(dp.PlanIntegrityError, match="declares depth_datum 'GL'"):
        dp.save_plan(manager, well_id=well, name="bad", inputs=dp.plan_inputs(
            segments, tie_in=tie, azimuth_reference="true", depth_datum="GL"))
    with pytest.raises(dp.PlanIntegrityError, match="may only declare"):
        inputs = dp.plan_inputs(segments)
        inputs["references"] = {"crs": "EPSG:0"}
        dp.save_plan(manager, well_id=well, name="bad", inputs=inputs)
    ok = dp.save_plan(manager, well_id=well, name="ok", inputs=dp.plan_inputs(
        segments, tie_in=tie, azimuth_reference="true", depth_datum="rkb"))
    assert dp.plan_references(ok)["declared"] is True
    forged = [dict(r) for r in rev["results"]]
    forged[-1]["north"] += 0.3            # the tie-in station itself is left consistent with `tie`
    _tamper(manager, path, rev["id"], results=forged)
    with pytest.raises(dp.PlanIntegrityError, match="fail their SHA-256 check"):
        dp.save_plan(manager, well_id=well, name="after tamper", inputs=dp.plan_inputs(segments, tie_in=tie))
    _tamper(manager, path, rev["id"], clear_results_hash=True)    # legacy-shaped: recomputation still refuses
    with pytest.raises(dp.PlanIntegrityError, match="north differs"):
        dp.save_plan(manager, well_id=well, name="legacy tamper", inputs=dp.plan_inputs(segments, tie_in=tie))


def test_an_exported_plan_declares_its_reference_and_reads_back(env, tmp_path):
    manager, _path, ids = env
    well = ids["A"][0]
    declared = dp.save_plan(manager, well_id=well, name="decl", inputs=dp.plan_inputs(
        [{"type": "hold", "length": 300.0}, {"type": "curve", "inc": 30.0, "azi": 90.0, "dls": 3.0}],
        azimuth_reference="grid", depth_datum="MSL"))
    legacy = dp.save_plan(manager, well_id=well, name="legacy", inputs=dp.plan_inputs(
        [{"type": "hold", "length": 300.0}, {"type": "curve", "inc": 30.0, "azi": 90.0, "dls": 3.0}]))
    out_decl, out_legacy = tmp_path / "decl.csv", tmp_path / "legacy.csv"
    dp.export_plan_csv(declared, str(out_decl))
    dp.export_plan_csv(legacy, str(out_legacy))
    first = out_decl.read_text(encoding="utf-8").splitlines()[0]
    assert "azimuth_reference=grid; depth_datum=MSL" in first
    assert "azimuth_reference=NOT DECLARED; depth_datum=NOT DECLARED" in out_legacy.read_text(encoding="utf-8")
    rows, reference = tc.read_plan_file_with_reference(str(out_decl))
    assert len(rows) == len(declared["results"]["stations"])
    assert rows[-1]["md"] == pytest.approx(declared["results"]["stations"][-1]["md"], abs=1e-4)
    assert reference == {"azimuth_reference": "grid", "depth_datum": "MSL", "declared": True}
    _rows, reference = tc.read_plan_file_with_reference(str(out_legacy))
    assert reference == {"azimuth_reference": None, "depth_datum": None, "declared": False}


def test_plan_file_reference_comments_are_parsed_strictly(tmp_path):
    semi = tmp_path / "semi.csv"
    semi.write_text("# azimuth_reference: TRUE\n# depth_datum=RKB\nMD;Inc;Azi\n0;0;0\n500;10;20\n", encoding="utf-8")
    rows, reference = tc.read_plan_file_with_reference(str(semi))
    assert len(rows) == 2 and reference["azimuth_reference"] == "true" and reference["declared"]
    assert tc.read_plan_file(str(semi)) == rows
    plain = tmp_path / "plain.csv"
    plain.write_text("MD,Inc,Azi\n0,0,0\n500,10,20\n", encoding="utf-8")
    assert tc.read_plan_file_with_reference(str(plain))[1]["declared"] is False
    twice = tmp_path / "twice.csv"
    twice.write_text("# depth_datum=RKB; depth_datum=GL\nMD,Inc,Azi\n0,0,0\n500,10,20\n", encoding="utf-8")
    with pytest.raises(tc.PlanImportError, match="declares depth_datum twice"):
        tc.read_plan_file_with_reference(str(twice))
    bad = tmp_path / "bad.csv"
    bad.write_text("# azimuth_reference=compass\nMD,Inc,Azi\n0,0,0\n500,10,20\n", encoding="utf-8")
    with pytest.raises(tc.PlanImportError, match="Unknown azimuth reference"):
        tc.read_plan_file_with_reference(str(bad))
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    for row in (["# azimuth_reference=grid; depth_datum=MSL"], ["MD", "Inc", "Azi"], [0, 0, 0], [500, 10, 20]):
        sheet.append(row)
    xlsx = tmp_path / "plan.xlsx"
    book.save(xlsx)
    rows, reference = tc.read_plan_file_with_reference(str(xlsx))
    assert len(rows) == 2 and reference["depth_datum"] == "MSL"


def test_reference_check_refuses_conflicts_and_labels_undeclared_values():
    actual = {"azimuth_reference": "true", "depth_datum": "RKB"}
    assert tc.reference_check({"azimuth_reference": "true", "depth_datum": "rkb"}, actual)["ok"] is True
    conflict = tc.reference_check({"azimuth_reference": "grid", "depth_datum": "RKB"}, actual)
    assert conflict["ok"] is False and "azimuth reference: plan grid vs actual true" in conflict["summary"]
    undeclared = tc.reference_check({}, actual)
    assert undeclared["ok"] is True and "plan depth datum NOT DECLARED" in undeclared["summary"]
    legacy_actual = tc.reference_check({"azimuth_reference": "true", "depth_datum": "RKB"}, {})
    assert legacy_actual["ok"] is True and "actual azimuth reference NOT DECLARED" in legacy_actual["summary"]


def test_the_compare_panel_refuses_a_plan_in_another_reference_and_labels_undeclared_ones(env, tmp_path):
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    manager, _path, ids = env
    well = ids["A"][0]
    rev = sr.save_revision(manager, well, BELOW_GL_ROWS, depth_datum="RKB", azimuth_reference="true")
    from tabs.trajectory_compare_panel import TrajectoryComparePanel
    panel = TrajectoryComparePanel(manager)
    try:
        panel.set_context(well) if hasattr(panel, "set_context") else panel.set_well(well)
        panel.refresh_actual_sources()
        panel.actual_combo.setCurrentIndex(panel.actual_combo.findData(rev["id"]))
        rows = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 900.0, "inc": 30.0, "azi": 45.0}]
        assert panel.set_plan_rows(rows, "synthetic", reference={"azimuth_reference": "true", "depth_datum": "GL"})
        assert "depth datum GL" in panel.plan_label.text()
        assert panel._gather() is None and "References differ" in panel.status_label.text()
        assert panel.set_plan_rows(rows, "synthetic")             # nothing declared
        inputs = panel._gather()
        assert inputs is not None and "plan azimuth reference NOT DECLARED" in inputs["reference_check"]
        panel.run()
        assert panel.wait_until_idle()
        texts = [panel.reason_list.item(i).text() for i in range(panel.reason_list.count())]
        assert any("NOT DECLARED" in t for t in texts)
    finally:
        panel.wait_until_idle()
        panel.deleteLater()
        app.processEvents()
