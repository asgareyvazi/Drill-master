"""M129: Multi-Survey -> immutable survey revisions; anti-collision only on declared survey revisions.

D44: well-to-well centre-to-centre screening (``core.trajectory_compare``) compared an offset well read from
the legacy survey points (no declared azimuth reference or datum) and never checked that both surveys use
the same azimuth reference or a datum the rotary-table elevation applies to. Now both surveys must be survey
revisions declaring grid north and an RKB / RT or MSL datum, otherwise NOT ASSESSED; M52 records keep their
version and re-run under the M52 rules.
D45: the W13 Anti-Collision page took its reference from the unsaved Multi-Survey table (``dd_surveys``), put
the offset well at the same wellhead without saying so and showed a separation-factor column with no
uncertainty model. It is now the trajectory comparison panel on survey revisions.
Goldens are written out here. Synthetic data only; offscreen Qt.
"""
from __future__ import annotations

import inspect
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtWidgets  # noqa: E402

from core import calculation_history as ch  # noqa: E402
from core import calculator_contracts as contracts  # noqa: E402
from core import survey_revisions as sr  # noqa: E402
from core import trajectory_compare as tc  # noqa: E402
from core.well_trajectory import compose_well_trajectory  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402

VERTICAL = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 500.0, "inc": 0.0, "azi": 0.0},
            {"md": 1000.0, "inc": 0.0, "azi": 0.0}]


def _refs(az_ref="grid", az_off="grid", datum_ref="RKB", datum_off="RKB"):
    return {"reference": {"survey_revision_id": 1, "azimuth_reference": az_ref, "depth_datum": datum_ref},
            "offset": {"survey_revision_id": 2, "azimuth_reference": az_off, "depth_datum": datum_off}}


def _well(name, northing=1000.0, easting=2000.0, rte=10.0):
    return {"name": name, "northing": northing, "easting": easting, "rte_msl": rte}


# ---- core: declared references (D44) --------------------------------------------------------------------
def test_grid_rkb_revisions_are_assessed_with_the_new_label():
    a = b = compose_well_trajectory(VERTICAL)
    result = tc.compare_wells(a, _well("A"), b, _well("B", 1006.0, 2008.0), same_crs_confirmed=True, step=50.0,
                              references=_refs())
    assert result.status == tc.ASSESSED and result.closest["distance_m"] == pytest.approx(10.0, abs=0.01)
    assert result.label == "SCREENING — NO ISCWSA UNCERTAINTY — NO SEPARATION FACTOR — NOT APPROVED (centre-to-centre)"
    assert result.method == tc.METHOD_VERSION == "M129 centre-to-centre screening v2"
    assert "separation_factor" not in str(result.to_json()["rows"])


@pytest.mark.parametrize("refs, needle", [
    (_refs(az_off="true"), "offset well: azimuth reference is true"),
    (_refs(az_ref="magnetic"), "reference well: azimuth reference is magnetic"),
    (_refs(datum_off="GL"), "offset well: depth datum is GL"),
    (_refs(datum_ref=""), "reference well: depth datum is not declared"),
    ({"reference": {}, "offset": _refs()["offset"]}, "reference well: the survey is not a survey revision"),
    (None, "offset well: the survey is not a survey revision"),
])
def test_undeclared_or_mismatched_references_are_not_assessed(refs, needle):
    a = compose_well_trajectory(VERTICAL)
    result = tc.compare_wells(a, _well("A"), a, _well("B", 1006.0), same_crs_confirmed=True, references=refs)
    assert result.status == tc.NOT_ASSESSED and result.rows == [] and result.closest is None
    assert any(needle in reason for reason in result.reasons), result.reasons


def test_an_msl_datum_needs_no_rotary_table_elevation():
    # reference TVD is below MSL (rte unknown is fine); offset is below its rotary table 10 m above MSL
    a = b = compose_well_trajectory(VERTICAL)
    result = tc.compare_wells(a, _well("A", rte=None), b, _well("B", 1003.0, 2004.0, rte=10.0),
                              same_crs_confirmed=True, step=50.0, references=_refs(datum_ref="MSL"))
    assert result.status == tc.ASSESSED
    row = next(r for r in result.rows if r["reference_md"] == 500.0)
    assert row["offset_md"] == pytest.approx(510.0, abs=0.01) and row["distance_m"] == pytest.approx(5.0, abs=0.01)
    missing = tc.compare_wells(a, _well("A", rte=None), b, _well("B"), same_crs_confirmed=True,
                               references=_refs())                    # RKB without rte_msl
    assert "reference well: rte_msl is missing" in missing.reasons


def test_an_m52_record_keeps_its_version_and_reruns_under_the_m52_rules():
    rows = [dict(r) for r in VERTICAL]
    inputs = {"mode": "offset", "step": 50.0, "actual_rows": rows, "offset_rows": rows, "same_crs": True,
              "reference_well": _well("A"), "offset_well": _well("B", 1006.0, 2008.0)}      # M52: no references
    old = tc.run_comparison(inputs, version=tc.METHOD_VERSION_V1)
    assert old.status == tc.ASSESSED and old.label == tc.LABEL_V1 and old.method == tc.METHOD_VERSION_V1
    params = {"contract": tc.CONTRACT, "record_schema": tc.RECORD_SCHEMA, "inputs": inputs,
              "inputs_sha256": tc.inputs_sha256(inputs)}
    outcome = tc.verify_record(params, old.to_json(), tc.METHOD_VERSION_V1)
    assert outcome["status"] == "MATCH" and outcome["method_matches"] is True, outcome
    assert tc.run_comparison(inputs).status == tc.NOT_ASSESSED            # a NEW run must declare references
    with pytest.raises(ValueError):
        tc.run_comparison(inputs, version="M52 something older")


# ---- panel: offset survey revision -------------------------------------------------------------------
@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def env(tmp_path, monkeypatch):
    manager = _open(tmp_path / "m129.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    from core.database import Well
    with manager.session_scope() as session:
        for code, (northing, easting) in (("A", (1000.0, 2000.0)), ("B", (1006.0, 2008.0))):
            well = session.get(Well, ids[code][0])
            well.northing, well.easting, well.rte_msl = northing, easting, 10.0
    yield manager, ids
    manager.close()


def _revision(manager, well, azimuth="grid", datum="RKB"):
    return sr.save_revision(manager, well, VERTICAL, depth_datum=datum, azimuth_reference=azimuth)


@pytest.fixture
def panel(app, env):
    from tabs.trajectory_compare_panel import TrajectoryComparePanel
    manager, ids = env
    widget = TrajectoryComparePanel(manager)
    yield widget
    widget.cleanup()
    widget.deleteLater()
    app.processEvents()


def _prepare(panel, ids, actual_id):
    panel.set_well(ids["A"][0])
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("offset"))
    panel.offset_combo.setCurrentIndex(panel.offset_combo.findData(ids["B"][0]))
    panel.actual_combo.setCurrentIndex(panel.actual_combo.findData(actual_id))
    panel.crs_check.setChecked(True)


def test_panel_compares_two_declared_revisions_and_the_record_reruns(panel, env):
    manager, ids = env
    ref, off = _revision(manager, ids["A"][0]), _revision(manager, ids["B"][0])
    _prepare(panel, ids, ref["id"])
    assert panel.offset_rev_combo.currentData() == off["id"]         # newest revision of the offset well
    panel.run()
    assert panel.wait_until_idle() and panel.result.status == tc.ASSESSED, panel.result.reasons
    assert panel.result.closest["distance_m"] == pytest.approx(10.0, abs=0.01)
    assert tc.LABEL in panel.status_label.text() and "NO SEPARATION FACTOR" in panel.label_banner.text()
    record_id = panel.save()
    entry = next(e for e in ch.load_history(manager, sources=["Trajectory"]) if e.record_id == record_id)
    assert entry.version == tc.METHOD_VERSION and ch.recalculate_entry(entry)["status"] == "MATCH"
    from core.database import TrajectoryCalculation
    with manager.session_scope() as session:
        inputs = session.get(TrajectoryCalculation, record_id).parameters_json["inputs"]
    assert inputs["offset_survey_revision_id"] == off["id"] and inputs["offset_source"] == "survey revision"
    assert inputs["references"]["offset"]["azimuth_reference"] == "grid"
    assert inputs["references"]["reference"]["survey_revision_id"] == ref["id"]


def test_panel_true_north_offset_and_legacy_points_are_not_assessed(panel, env):
    manager, ids = env
    ref = _revision(manager, ids["A"][0])
    _revision(manager, ids["B"][0], azimuth="true")
    _prepare(panel, ids, ref["id"])
    panel.run()
    assert panel.wait_until_idle() and panel.result.status == tc.NOT_ASSESSED
    reasons = [panel.reason_list.item(i).text() for i in range(panel.reason_list.count())]
    assert any("offset well: azimuth reference is true" in r for r in reasons)
    assert not panel.save_button.isEnabled() and panel.save() is None
    panel.actual_combo.setCurrentIndex(panel.actual_combo.findData(None))   # live points of the selected well
    panel.run()
    assert panel.wait_until_idle() and panel.result.status == tc.NOT_ASSESSED
    assert any("reference well: the survey is not a survey revision" in r for r in panel.result.reasons)



def test_panel_refuses_a_tampered_offset_revision(panel, env):
    import json

    from sqlalchemy import text

    from core.database import SurveyRevision
    manager, ids = env
    ref, off = _revision(manager, ids["A"][0]), _revision(manager, ids["B"][0])
    with manager.engine.begin() as conn:                      # edit behind the hash (trigger dropped as in M105)
        for (name,) in conn.execute(text("SELECT name FROM sqlite_master WHERE type='trigger' AND "
                                         "name LIKE 'trg_survey_revision_immutable%'")).fetchall():
            conn.execute(text(f"DROP TRIGGER {name}"))
    with manager.session_scope() as session:
        row = session.get(SurveyRevision, off["id"])
        stations = json.loads(row.stations_json)
        stations[1]["inc"] = 3.0
        row.stations_json = json.dumps(stations)
    _prepare(panel, ids, ref["id"])
    panel.run()
    assert panel.result is None and panel.status_label.text().startswith("Not compared:")

# ---- W13 pages ------------------------------------------------------------------------------------------
@pytest.fixture
def w13(app, env, monkeypatch):
    from PySide6.QtCore import QCoreApplication, QEvent

    from tabs import w13_Engineering_Calculator as w13_module
    manager, ids = env
    monkeypatch.setattr(w13_module.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(w13_module.QMessageBox, "warning", lambda *a, **k: None)
    tab = w13_module.EngineeringCalculatorTab(manager)
    tab.on_well_changed(ids["A"][0], {"name": "SYN-A"})
    yield tab
    tab.cleanup()
    tab.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_w13_anti_collision_is_the_revision_panel_without_a_separation_factor(w13, env):
    manager, ids = env
    from tabs import w13_Engineering_Calculator as w13_module
    assert w13.calculator_finder.open_path("Directional › Anti-Collision")
    panel = w13.ac_panel
    assert panel.mode == "offset" and not panel.mode_combo.isEnabled() and panel.well_id == ids["A"][0]
    source = inspect.getsource(w13_module)
    assert "Sep. Factor" not in source and "ac_offset_surveys" not in source
    for name, member in inspect.getmembers(w13_module.EngineeringCalculatorTab, inspect.isfunction):
        if "dd_surveys" in inspect.getsource(member):        # the draft table is read by its own page only
            assert name.startswith("_dd_") or name == "_create_directional_tab", name
    ref, off = _revision(manager, ids["A"][0]), _revision(manager, ids["B"][0])
    w13.on_well_changed(ids["A"][0], {"name": "SYN-A"})
    panel.offset_combo.setCurrentIndex(panel.offset_combo.findData(ids["B"][0]))
    panel.actual_combo.setCurrentIndex(panel.actual_combo.findData(ref["id"]))
    panel.crs_check.setChecked(True)
    panel.run()
    assert panel.wait_until_idle() and panel.result.status == tc.ASSESSED
    assert panel.last_inputs["offset_survey_revision_id"] == off["id"]
    w13.case_bar.refresh()
    assert not w13.case_bar.save_btn.isEnabled()
    assert w13.case_bar.save_case("SYN anti-collision") is None
    assert "trajectory comparison record" in w13.case_bar.status.text()
    w13.on_well_changed(ids["B"][0], {"name": "SYN-B"})                 # the panel follows the well
    assert panel.well_id == ids["B"][0] and panel.result is None


def test_multi_survey_table_is_saved_as_a_declared_revision_and_loaded_back(w13, env):
    manager, ids = env
    assert w13.calculator_finder.open_path("Directional › Multi-Survey")
    w13.dd_surveys = [dict(r) for r in VERTICAL]
    w13._dd_recalculate_from(0)
    w13._dd_refresh_table()
    w13._dd_touch()
    assert w13.dd_source_label.text().startswith("UNSAVED DRAFT")
    assert w13._dd_save_revision() is None and "azimuth reference" in w13.dd_source_label.text()   # undeclared
    w13.dd_azimuth_ref.setCurrentIndex(w13.dd_azimuth_ref.findData("grid"))
    w13.dd_depth_datum.setText("RKB")
    saved = w13._dd_save_revision()
    assert saved["mode"] == "initial" and saved["source_ref"] == "W13 Multi-Survey"
    assert saved["azimuth_reference"] == "grid" and saved["depth_datum"] == "RKB"
    assert saved["wellbore_id"] is None and saved["integrity"] == "VERIFIED"   # no wellbore selected: never inferred
    assert w13.wt_survey_combo.findData(saved["id"]) >= 0                 # Weight / T&D can pin it now
    assert w13._dd_save_revision() is None and "unchanged" in w13.dd_source_label.text()
    # an edit saves a NEW revision (replace) - the first one is never changed
    w13.dd_surveys.append({"md": 1200.0, "inc": 0.0, "azi": 0.0})
    w13._dd_recalculate_from(0)
    w13._dd_touch()
    second = w13._dd_save_revision()
    assert second["mode"] == "replace" and second["parent_id"] == saved["id"] and second["station_count"] == 4
    assert sr.get_revision(manager, saved["id"])["station_count"] == 3
    # load the first revision back into a cleared table
    w13._dd_clear_surveys()
    w13.dd_rev_combo.setCurrentIndex(w13.dd_rev_combo.findData(saved["id"]))
    assert w13._dd_load_revision() and [s["md"] for s in w13.dd_surveys] == [0.0, 500.0, 1000.0]
    assert "loaded, unchanged" in w13.dd_source_label.text()
    w13.case_bar.refresh()
    assert w13.case_bar.save_case("SYN multi-survey") is None and "survey revision" in w13.case_bar.status.text()


def test_a_draft_of_one_well_is_never_saved_for_another(w13, env):
    manager, ids = env
    w13.dd_surveys = [dict(r) for r in VERTICAL]
    w13._dd_recalculate_from(0)
    w13._dd_touch()
    w13.dd_azimuth_ref.setCurrentIndex(w13.dd_azimuth_ref.findData("grid"))
    w13.dd_depth_datum.setText("RKB")
    w13.on_well_changed(ids["B"][0], {"name": "SYN-B"})
    assert f"entered for well #{ids['A'][0]}" in w13.dd_source_label.text()
    assert w13._dd_save_revision() is None and sr.list_revisions(manager, ids["B"][0]) == []
    w13._dd_clear_surveys()
    assert w13.dd_draft_well is None and w13.dd_source_label.text().startswith("Empty")


def test_registry_after_m129():
    assert contracts.CONTRACT_REGISTRY_VERSION == "M129 calculator contracts v7"
    assert set(contracts.RECORDED_ELSEWHERE) == {"Directional › Multi-Survey", "Directional › Anti-Collision"}
    assert set(contracts.RECORDED_ELSEWHERE) <= set(contracts.NOT_SUPPORTED)
    assert "saving it as a survey revision" in contracts.NOT_SUPPORTED["Directional › Multi-Survey"]
    assert "NO SEPARATION FACTOR" in contracts.NOT_SUPPORTED["Directional › Anti-Collision"]
    assert contracts.classification_violations() == []
