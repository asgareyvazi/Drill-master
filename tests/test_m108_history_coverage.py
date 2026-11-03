"""M108: method/version on new trajectory records (legacy stays NOT REPRODUCIBLE), re-run of a stored
comparison from its own stations, insert-only trajectory saves (D27), full-field unit-aware compare and the
history coverage register. Synthetic data, temporary file SQLite, offscreen Qt.
"""
from __future__ import annotations

import os
from datetime import date, datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from core import calculation_history as ch  # noqa: E402
from core import trajectory_compare as tc  # noqa: E402
from tests.test_m52_trajectory_compare_ui import _select_offset, app, panel, synthetic  # noqa: E402,F401


def _trajectory_entries(db, ids):
    return {e.record_id: e for e in ch.load_history(db, sources=["Trajectory"]) if e.record_id in ids}


def _saved_offset(panel, synthetic):  # noqa: F811
    _select_offset(panel, synthetic[1]["SYN-OFF"])
    panel.crs_check.setChecked(True)
    panel.run()
    assert panel.wait_until_idle() and panel.result.status == tc.ASSESSED
    return panel.save()


def test_a_new_comparison_record_is_versioned_self_contained_and_reruns(panel, synthetic):  # noqa: F811
    from core.database import TrajectoryCalculation

    db = synthetic[0]
    record_id = _saved_offset(panel, synthetic)
    with db.session_scope() as session:
        row = session.query(TrajectoryCalculation).get(record_id)
        assert row.method_version == tc.METHOD_VERSION
        params = dict(row.parameters_json)
    assert params["record_schema"] == tc.RECORD_SCHEMA and params["inputs_sha256"] == tc.inputs_sha256(params["inputs"])
    assert len(params["inputs"]["actual_rows"]) == 4 and len(params["inputs"]["offset_rows"]) == 4
    entry = _trajectory_entries(db, {record_id})[record_id]
    assert entry.version == tc.METHOD_VERSION
    assert ch.entry_status(entry)["reproducible"] == "REPRODUCIBLE"
    outcome = ch.recalculate_entry(entry)
    assert outcome["status"] == "MATCH" and outcome["method_matches"] is True, outcome


def test_a_plan_record_with_targets_reruns_and_detects_a_changed_result(panel, synthetic):  # noqa: F811
    from core.database import TrajectoryCalculation

    db = synthetic[0]
    rows = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 1000.0, "inc": 0.0, "azi": 0.0}]
    assert panel.set_plan_rows(rows, "SYN plan", targets=[{"name": "T1", "north": 0.0, "east": 3.0, "tvd": 600.0,
                                                           "radius": 5.0}])
    panel.run()
    assert panel.wait_until_idle() and panel.result.status == tc.ASSESSED
    record_id = panel.save()
    entry = _trajectory_entries(db, {record_id})[record_id]
    assert entry.inputs["inputs"]["target_checks"][0]["distance_m"] == pytest.approx(3.0, abs=1e-6)
    assert ch.recalculate_entry(entry)["status"] == "MATCH"
    with db.session_scope() as session:                     # a stored result altered outside the application
        row = session.query(TrajectoryCalculation).get(record_id)
        results = dict(row.results_json)
        results["rows"] = [dict(r) for r in results["rows"]]
        results["rows"][0]["distance_m"] = results["rows"][0]["distance_m"] + 0.5
        row.results_json = results
    outcome = ch.recalculate_entry(_trajectory_entries(db, {record_id})[record_id])
    assert outcome["status"] == "DIFFERENT" and outcome["differences"][0]["field_id"] == "rows.0.distance_m"
    with db.session_scope() as session:                     # altered inputs: never recomputed
        row = session.query(TrajectoryCalculation).get(record_id)
        params = dict(row.parameters_json)
        params["inputs"] = dict(params["inputs"], step=1.0)
        row.parameters_json = params
    outcome = ch.recalculate_entry(_trajectory_entries(db, {record_id})[record_id])
    assert outcome["status"] == "UNREADABLE" and "SHA-256" in outcome["detail"]


def test_legacy_trajectory_rows_stay_not_reproducible(synthetic):  # noqa: F811
    from core.database import TrajectoryCalculation

    db, ids = synthetic
    with db.session_scope() as session:
        row = TrajectoryCalculation(well_id=ids["SYN-REF"], method=tc.METHOD_VERSION, calculation_date=date.today(),
                                    parameters_json={"contract": tc.CONTRACT, "inputs": {"actual_stations": 4}},
                                    results_json={"status": "ASSESSED", "rows": []}, description=tc.LABEL)
        session.add(row)
        session.flush()
        legacy_id = row.id
    entry = _trajectory_entries(db, {legacy_id})[legacy_id]
    assert entry.version == "unversioned (legacy)"                  # never given the current method
    status = ch.entry_status(entry)
    assert status["reproducible"] == "NOT REPRODUCIBLE" and "before M108" in status["reproducible_reason"]
    outcome = ch.recalculate_entry(entry)
    assert outcome["status"] == "NOT_REPRODUCIBLE" and "before M108" in outcome["detail"]


def test_reproducibility_reasons_are_exact():
    inputs = {"mode": "offset", "actual_rows": [{"md": 0.0, "inc": 0.0, "azi": 0.0}], "offset_rows": []}
    params = {"record_schema": tc.RECORD_SCHEMA, "inputs": inputs, "inputs_sha256": tc.inputs_sha256(inputs)}
    assert tc.record_reproducibility(params, tc.METHOD_VERSION) == (
        "NOT REPRODUCIBLE", "input station rows not stored: offset_rows")
    assert "not available" in tc.record_reproducibility(params, "M52 something older")[1]
    assert "record schema" in tc.record_reproducibility({"inputs": inputs}, tc.METHOD_VERSION)[1]


def _plan_record():
    rows = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 300.0, "inc": 0.0, "azi": 0.0}]
    inputs = {"mode": "plan", "step": 10.0, "actual_rows": rows, "plan_rows": rows,
              "targets": [{"name": "T", "north": 0.0, "east": 4.0, "tvd": 200.0, "radius": 1.0}]}
    comparison = tc.run_comparison(inputs)
    inputs["target_checks"] = comparison.target_checks
    record = tc.calculation_record(comparison, inputs=inputs)
    return record["parameters_json"], record["results_json"], record["method_version"]


def test_a_missing_result_row_is_a_count_difference():
    params, results, version = _plan_record()
    assert tc.verify_record(params, results, version)["status"] == "MATCH"
    shorter = dict(results, rows=results["rows"][:-1])
    outcome = tc.verify_record(params, shorter, version)
    assert outcome["status"] == "DIFFERENT" and outcome["differences"] == [
        {"field_id": "rows.count", "stored": len(results["rows"]) - 1, "current": len(results["rows"])}]


def test_target_checks_are_part_of_the_verification(monkeypatch):
    params, results, version = _plan_record()
    assert params["inputs"]["target_checks"][0]["distance_m"] == pytest.approx(4.0, abs=1e-6)
    original = tc.target_checks
    monkeypatch.setattr(tc, "target_checks", lambda *a, **k: [dict(c, distance_m=c["distance_m"] + 0.25)
                                                              for c in original(*a, **k)])
    outcome = tc.verify_record(params, results, version)
    assert outcome["status"] == "DIFFERENT"
    assert [d["field_id"] for d in outcome["differences"]] == ["target_checks.0.distance_m"]


def test_save_trajectory_calculation_never_overwrites(synthetic):  # noqa: F811
    from core.database import TrajectoryCalculation

    db, ids = synthetic
    data = {"well_id": ids["SYN-REF"], "calculation_date": date(2026, 1, 5), "method": "Minimum Curvature",
            "parameters": {"note": "first"}, "results": {"td": 1.0}, "description": "SYN first"}
    first = db.save_trajectory_calculation(dict(data))
    second = db.save_trajectory_calculation(dict(data, parameters={"note": "second"}, results={"td": 2.0},
                                                 description="SYN second"))
    assert first and second and first != second
    with db.session_scope() as session:
        rows = {r.id: r for r in session.query(TrajectoryCalculation).filter(
            TrajectoryCalculation.id.in_([first, second]))}
        assert rows[first].results_json == {"td": 1.0} and rows[first].description == "SYN first"
        assert rows[first].method_version is None and rows[second].method_version is None   # no version claimed


def _entry(inputs, results, *, table="calculation_cases", source="Calculation case", version="v1"):
    return ch.HistoryEntry(source, table, 1, 1, "SYN", "m", version, datetime(2026, 1, 1), "S", inputs, results)


def test_full_field_compare_is_unit_aware_and_lists_every_field():
    a = _entry({"k1": {"label": "Length", "value": 1000.0, "unit": "m", "field_id": "length"},
                "k2": {"label": "Additive", "value": "Barite", "unit": ""}, "only_a": {"value": 1.0, "unit": ""}},
               {"values": {"hook_load_lbs": 100000.0, "status": "ok"}, "depth": {"value": 10.0, "unit": "m"}})
    b = _entry({"k1": {"label": "Length", "value": 3280.84, "unit": "ft", "field_id": "length"},
                "k2": {"label": "Additive", "value": "Hematite", "unit": ""}, "only_b": {"value": 2.0, "unit": ""}},
               {"values": {"hook_load_lbs": 101000.0, "status": "ok"}, "depth": {"value": 10.0, "unit": "m"}})
    out = ch.full_field_compare(a, b)
    rows = {r["key"]: r for r in out["inputs"] + out["results"]}
    assert rows["k1"]["status"] == "UNIT MISMATCH" and rows["k1"]["b_in_unit_a"] == pytest.approx(1000.0, abs=1e-3)
    assert rows["k2"]["status"] == "CHANGED"
    assert rows["only_a"]["status"] == "ONLY A" and rows["only_b"]["status"] == "ONLY B"
    hook = rows["values.hook_load_lbs"]
    assert hook["status"] == "DIFFERENT" and hook["unit"] == "lbf" and hook["unit_source"] == "key suffix"
    assert hook["delta"] == 1000.0 and hook["relative"] == pytest.approx(0.01)
    assert rows["values.status"]["status"] == "SAME" and rows["depth"]["status"] == "SAME"
    assert rows["depth"]["unit"] == "m" and rows["depth"]["unit_source"] == "stored"
    assert out["counts"] == {"UNIT MISMATCH": 1, "CHANGED": 1, "ONLY A": 1, "ONLY B": 1, "DIFFERENT": 1, "SAME": 2}
    psi_vs_m = ch.full_field_compare(_entry({"x": {"value": 1.0, "unit": "psi"}}, {}),
                                     _entry({"x": {"value": 1.0, "unit": "m"}}, {}))
    assert psi_vs_m["inputs"][0]["status"] == "UNIT MISMATCH" and "b_in_unit_a" not in psi_vs_m["inputs"][0]


def test_history_tab_compare_shows_the_full_field_table(app, synthetic):  # noqa: F811
    from tabs.calculation_history_tab import CalculationHistoryTab

    db, ids = synthetic
    rows = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 500.0, "inc": 0.0, "azi": 0.0}]
    made = []
    for step in (10.0, 25.0):
        inputs = {"mode": "plan", "step": step, "actual_rows": rows, "plan_rows": rows, "targets": []}
        made.append(tc.save_comparison(db, ids["SYN-NODATUM"], tc.run_comparison(inputs), inputs=inputs))
    tab = CalculationHistoryTab(db)
    try:
        tab.set_well(ids["SYN-NODATUM"])
        tab.select_rows([i for i, e in enumerate(tab.entries) if e.record_id in made])
        out = tab.compare()
        changed = {r["key"]: r for r in out["full"]["inputs"]}
        step = changed["inputs.step"]                         # history lists newest first; either order
        assert step["status"] == "DIFFERENT" and {step["a"], step["b"]} == {10.0, 25.0}
        assert step["delta"] == step["b"] - step["a"] and step["unit"] == ""
        assert changed["inputs_sha256"]["status"] == "CHANGED"
        text = tab.detail.toPlainText()
        assert "Full-field comparison" in text and "inputs.step" in text
    finally:
        tab.deleteLater()
        app.processEvents()


def test_coverage_register_covers_every_calculation_table(synthetic):  # noqa: F811
    from core import database as d

    tables = {m.class_.__tablename__ for m in d.Base.registry.mappers}
    looks_like = {t for t in tables if t.endswith(("_calculations", "_revisions", "_cases")) or "calculation" in t}
    covered = {row[0] for row in ch.COVERAGE}
    assert looks_like <= covered | set(ch.NOT_CALCULATIONS), looks_like - covered - set(ch.NOT_CALCULATIONS)
    assert {row[1] for row in ch.COVERAGE} == set(ch.SOURCES)
    register = ch.coverage(synthetic[0])
    trajectory = next(r for r in register if r["table"] == "trajectory_calculations")
    assert trajectory["records"] >= 1 and 0 <= trajectory["reproducible"] <= trajectory["records"]
    assert all(r["compare"].startswith("full-field") for r in register)


def test_an_old_database_gains_method_version_and_old_rows_stay_unversioned(tmp_path):
    import sqlite3

    from core.database import Company, Project, Well
    from synthetic_operations import make_file_database

    path = tmp_path / "synthetic-m108-legacy.db"
    db = make_file_database(path)
    with db.session_scope() as session:
        company = Company(name="SYN Legacy Co", code="SYNL")
        session.add(company)
        session.flush()
        project = Project(name="SYN Legacy Field", code="SYNLF", company_id=company.id)
        session.add(project)
        session.flush()
        well = Well(name="SYN-LEGACY", code="SYN-LEGACY", project_id=project.id)
        session.add(well)
        session.flush()
        well_id = well.id
    old_id = db.save_trajectory_calculation({"well_id": well_id, "calculation_date": date(2025, 3, 1),
                                             "method": "Minimum Curvature", "parameters": {"md": [0, 100]},
                                             "results": {"td": 100.0}, "description": "SYN legacy run"})
    db.close()
    with sqlite3.connect(path) as con:                   # the pre-M108 schema had no such column
        con.execute("ALTER TABLE trajectory_calculations DROP COLUMN method_version")
        assert "method_version" not in {r[1] for r in con.execute("PRAGMA table_info(trajectory_calculations)")}
    db.initialize()                                      # additive migration on startup, no back-fill
    with sqlite3.connect(path) as con:
        assert "method_version" in {r[1] for r in con.execute("PRAGMA table_info(trajectory_calculations)")}
        assert con.execute("SELECT method_version FROM trajectory_calculations WHERE id = ?",
                           (old_id,)).fetchone() == (None,)
    entry = _trajectory_entries(db, {old_id})[old_id]
    assert entry.version == "unversioned (legacy)" and ch.entry_status(entry)["reproducible"] == "NOT REPRODUCIBLE"
    db.engine.dispose()
