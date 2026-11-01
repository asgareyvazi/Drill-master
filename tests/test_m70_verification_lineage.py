"""M70.4 whole-result plan verification and M70.5 structured lineage.

Synthetic data in temporary SQLite databases (``make_file_database``). The
history-tab test runs offscreen with the real widget (not Windows desktop).
"""
from __future__ import annotations

import copy
import tempfile
from pathlib import Path

import pytest

from core import calculation_cases as cc
from core import calculation_history as ch
from core import directional_plans as dp

SEGMENTS = [{"type": "hold", "length": 500.0}, {"type": "curve", "inc": 30.0, "azi": 135.0, "dls": 3.0},
            {"type": "hold_to_tvd", "tvd": 1500.0}]
INPUTS = dp.plan_inputs(SEGMENTS, targets=[{"name": "T1", "north": -300.0, "east": 300.0, "tvd": 1400.0,
                                            "radius": 50.0}])


@pytest.fixture
def seeded():
    from synthetic_operations import make_file_database
    from core.database import Company, Project, Well

    db = make_file_database(Path(tempfile.mkdtemp(prefix="m70-lineage-")) / "lineage.db")
    with db.session_scope() as session:
        company = Company(name="SYN CO", code="SYN")
        session.add(company)
        session.flush()
        project = Project(name="SYN FIELD", code="SYNF", company_id=company.id)
        session.add(project)
        session.flush()
        wells = [Well(name=f"SYN-L-0{i}", code=f"SYN-L-0{i}", project_id=project.id) for i in (1, 2)]
        session.add_all(wells)
        session.flush()
        well_ids = [w.id for w in wells]
    plan = dp.save_plan(db, well_id=well_ids[0], name="SYN plan", inputs=INPUTS)
    yield db, well_ids, plan
    db.engine.dispose()


def _stored():
    return dp._results(dp.run_inputs(INPUTS))


def _refingerprint(results):
    results = copy.deepcopy(results)
    results["result_sha256"] = dp.result_fingerprint(results)
    return results


def test_an_unchanged_plan_matches_on_every_record():
    outcome = dp.verify_plan_record(INPUTS, _refingerprint(_stored()), dp.PLAN_VERSION)
    assert outcome["status"] == "MATCH" and outcome["method_matches"] is True
    assert outcome["detail"].endswith("records identical") and not outcome["differences"]


def _mutated(path, value):
    results = _stored()
    container = results
    for key in path[:-1]:
        container = container[key]
    container[path[-1]] = value(container[path[-1]]) if callable(value) else value
    return _refingerprint(results)


@pytest.mark.parametrize("path, value, field", [
    (("stations", 10, "east"), lambda v: v + 1e-3, "stations[10].east"),          # interior station only
    (("stations", 10, "north"), lambda v: v - 1e-3, "stations[10].north"),
    (("stations", 20, "inc"), lambda v: v + 1e-4, "stations[20].inc"),
    (("stations", 20, "azi"), lambda v: v + 1e-4, "stations[20].azi"),
    (("stations", 20, "tvd"), lambda v: v + 1e-3, "stations[20].tvd"),
    (("stations", 20, "vs"), lambda v: v + 1e-3, "stations[20].vs"),
    (("stations", 20, "dls"), lambda v: v + 1e-3, "stations[20].dls"),
    (("segments", 1, "end_md"), lambda v: v + 1e-3, "segments[1].end_md"),
    (("segments", 1, "type"), "Drop", "segments[1].type"),
    (("targets", 0, "hit"), False, "targets[0].hit"),
    (("targets", 0, "radius"), 49.0, "targets[0].radius"),
    (("targets", 0, "distance"), lambda v: v + 1e-3, "targets[0].distance"),
    (("targets", 0, "closest_md"), lambda v: v + 1e-3, "targets[0].closest_md"),
    (("targets", 0, "closest_point", "east"), lambda v: v + 1e-3, "targets[0].closest_point.east"),
    (("warnings",), ["forged warning"], "warnings"),
])
def test_any_changed_geometry_target_or_warning_is_different_even_with_equal_headline(path, value, field):
    stored = _mutated(path, value)
    assert stored["stations"][-1]["md"] == _stored()["stations"][-1]["md"]      # TD is unchanged
    outcome = dp.verify_plan_record(INPUTS, stored, dp.PLAN_VERSION)
    assert outcome["status"] == "DIFFERENT"
    assert field in [d["field"] for d in outcome["differences"]]


def test_a_missing_station_and_a_missing_target_are_count_differences():
    stored = _stored()
    del stored["stations"][5]
    stored["targets"] = []
    outcome = dp.verify_plan_record(INPUTS, _refingerprint(stored), dp.PLAN_VERSION)
    fields = [d["field"] for d in outcome["differences"]]
    assert outcome["status"] == "DIFFERENT" and "stations.count" in fields and "targets.count" in fields


def test_azimuth_is_compared_on_the_circle_and_noise_is_tolerated():
    stored = _stored()
    stored["stations"][0]["azi"] = 360.0 - 1e-9          # 0 deg vertical station, same direction
    stored["stations"][30]["north"] += 1e-8              # floating-point noise, below 1e-6 m
    assert dp.verify_plan_record(INPUTS, _refingerprint(stored), dp.PLAN_VERSION)["status"] == "MATCH"


def test_an_altered_stored_result_with_a_stale_fingerprint_is_unreadable():
    stored = _refingerprint(_stored())
    stored["stations"][3]["east"] += 5.0
    outcome = dp.verify_plan_record(INPUTS, stored, dp.PLAN_VERSION)
    assert outcome["status"] == "UNREADABLE" and "fingerprint" in outcome["detail"]


def test_a_method_version_change_is_always_reported():
    outcome = dp.verify_plan_record(INPUTS, _refingerprint(_stored()), "M55 plan designer v1")
    assert outcome["method_matches"] is False and "METHOD CHANGED" in outcome["detail"]
    assert outcome["stored_version"] == "M55 plan designer v1" and outcome["current_method"] == dp.PLAN_VERSION


def test_foreign_units_and_unreadable_inputs_are_not_compared():
    assert dp.verify_plan_record(dict(INPUTS, units={"length": "ft"}), _stored(), dp.PLAN_VERSION)["status"] \
        == "NOT_REPRODUCIBLE"
    assert dp.verify_plan_record({"segments": None}, _stored(), dp.PLAN_VERSION)["status"] in (
        "UNREADABLE", "NOT_REPRODUCIBLE")


def test_history_uses_the_full_stored_plan(seeded):
    db, well_ids, plan = seeded
    (entry,) = [e for e in ch.load_history(db, well_id=well_ids[0]) if e.table == "directional_plan_revisions"]
    assert entry.full_results["stations"] == plan["results"]["stations"]
    assert ch.recalculate_entry(entry)["status"] == "MATCH"


# ---------------------------------------------------------------- M70.5 lineage
def test_a_saved_recalculation_has_structured_lineage_both_ways(seeded):
    db, well_ids, plan = seeded
    (entry,) = [e for e in ch.load_history(db, well_id=well_ids[0]) if e.table == "directional_plan_revisions"]
    outcome = ch.recalculate_entry(entry)
    case = ch.save_recalculation(db, entry, outcome)
    (link,) = cc.source_links(db, case["id"])
    assert (link["link_type"], link["source_table"], link["source_id"]) == (
        "recalculation_of", "directional_plan_revisions", plan["id"])
    assert (link["source_method_version"], link["recalc_method_version"]) == (dp.PLAN_VERSION, dp.PLAN_VERSION)
    assert (link["verification_status"], link["method_changed"], link["source_well_id"]) == (
        "MATCH", False, well_ids[0])
    assert [d["case_id"] for d in cc.derived_cases(db, "directional_plan_revisions", plan["id"])] == [case["id"]]
    (case_entry,) = [e for e in ch.load_history(db, well_id=well_ids[0]) if e.key == f"calculation_cases:{case['id']}"]
    assert [i["key"] for i in ch.lineage(db, case_entry)] == [entry.key]
    assert [i["key"] for i in ch.lineage(db, entry)] == [case_entry.key]


def test_lineage_refuses_a_source_of_another_well_or_a_missing_source(seeded):
    db, well_ids, plan = seeded
    (entry,) = [e for e in ch.load_history(db, well_id=well_ids[0]) if e.table == "directional_plan_revisions"]
    outcome = ch.recalculate_entry(entry)
    forged = copy.copy(entry)
    forged.well_id = well_ids[1]
    with pytest.raises(ValueError, match="belongs to well"):
        ch.save_recalculation(db, forged, outcome)
    missing = copy.copy(entry)
    missing.record_id = 999999
    with pytest.raises(LookupError, match="does not exist"):
        ch.save_recalculation(db, missing, outcome)
    assert not [e for e in ch.load_history(db) if e.table == "calculation_cases"]   # nothing half-written


def test_a_w13_rerun_records_its_lineage(seeded):
    db, well_ids, _plan = seeded
    original = cc.save_case(db, calculator="Quick Calc", name="c", inputs={"a": 1}, results={"r": 2},
                            well_id=well_ids[0])
    rerun = cc.record_rerun(db, original, {"r": 3}, method_version="v2")
    (link,) = cc.source_links(db, rerun["id"])
    assert (link["link_type"], link["source_id"], link["method_changed"]) == ("rerun_of", original["id"], True)


def test_history_tab_lineage_navigation(seeded):
    from PySide6 import QtWidgets
    from tabs.calculation_history_tab import CalculationHistoryTab

    db, well_ids, plan = seeded
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tab = CalculationHistoryTab(db_manager=db)
    try:
        tab.set_well(well_ids[0])
        plan_row = next(i for i, e in enumerate(tab.entries) if e.table == "directional_plan_revisions")
        tab.select_rows([plan_row])
        tab.recalculate()
        case = tab.save_recalculation()
        case_row = next(i for i, e in enumerate(tab.entries) if e.key == f"calculation_cases:{case['id']}")
        tab.select_rows([case_row])
        assert tab.lineage_combo.currentText().startswith("Source: directional_plan_revisions")
        tab.text_edit.setText("no such text")           # a filter that hides the source
        assert tab.open_linked() is True
        assert tab.selected()[0].key == f"directional_plan_revisions:{plan['id']}"
        assert tab.lineage_combo.currentText().startswith(f"Derived: case #{case['id']}")
        assert tab.open_linked() is True and tab.selected()[0].key == f"calculation_cases:{case['id']}"
    finally:
        tab.deleteLater()
        app.processEvents()
