"""M286: workbench clone, archive and restore for calculation-history records (SYNTHETIC).

Archive and restore are append-only, audited events that need a reason. Archiving hides a record from the
default list only: the record is not deleted, edited or re-run, and it still re-runs as MATCH. A clone is a NEW
case with the exact inputs and stored results, linked ``clone_of``, and is not recalculated.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import text  # noqa: E402

from core import calculation_cases as cc  # noqa: E402
from core import calculation_history as ch  # noqa: E402
from core import calculation_workbench as wb  # noqa: E402
from core.database import AuditLog, CalculationArchiveMark  # noqa: E402
from core.engineering.calculation_verification import VERIFY_MATCH  # noqa: E402
from core.engineering.engines.casing import CasingEngine  # noqa: E402
from core.repositories.casing_repository import CasingCalculationRepository  # noqa: E402
from synthetic_operations import build_synthetic_operations, make_file_database  # noqa: E402

INPUTS = dict(od_in=9.625, id_in=8.681, wall_in=0.472, yield_psi=80000.0, grade="SYN-80",
              internal_pressure_psi=None, external_pressure_psi=None, axial_tension_lbf=None, weight_ppf=None)


@pytest.fixture()
def world(tmp_path):
    db = make_file_database(tmp_path / "m286.db")
    ids = build_synthetic_operations(db)
    dev = ids["dev"]
    repo = CasingCalculationRepository(db)
    result = CasingEngine.evaluate(**INPUTS)
    casing_id = repo.save_run(inputs=INPUTS, result_values=result.values, method=CasingEngine.METHOD,
                              label="SYN M286 casing", well_id=dev)
    case = cc.save_case(db, calculator="SYN calculator", name="SYN M286 case", inputs={"a_ft": 1.0},
                        results={"b_ft": 2.0}, well_id=dev)
    yield db, dev, casing_id, case["id"]
    db.engine.dispose()


def _entry(db, dev, table, record_id):
    return {(e.table, e.record_id): e for e in ch.load_history(db, well_id=dev)}[(table, record_id)]


def _keys(db, dev, **kw):
    return {(e.table, e.record_id) for e in ch.load_history(db, well_id=dev, **kw)}


def test_archive_needs_a_reason_hides_by_default_and_changes_nothing(world):
    db, dev, casing_id, _case_id = world
    entry = _entry(db, dev, "casing_calculations", casing_id)
    total = ch.count_history(db, well_id=dev)
    with pytest.raises(wb.WorkbenchError):
        wb.archive(db, entry, "   ")
    assert wb.state(db, entry) == wb.ACTIVE
    mark = wb.archive(db, entry, "superseded by the SYN revision")
    assert mark["state"] == wb.ARCHIVED and wb.state(db, entry) == wb.ARCHIVED
    key = ("casing_calculations", casing_id)
    assert key not in _keys(db, dev, include_archived=False)
    assert ch.count_history(db, well_id=dev, include_archived=False) == total - 1
    assert key in _keys(db, dev) and ch.count_history(db, well_id=dev) == total     # default call: unchanged
    again = _entry(db, dev, "casing_calculations", casing_id)
    assert again.inputs == entry.inputs and again.results == entry.results
    assert ch.recalculate_entry(again, db)["status"] == VERIFY_MATCH
    with db.session_scope() as session:
        audit = session.query(AuditLog).filter(AuditLog.action == "CALCULATION_ARCHIVE").all()
        assert len(audit) == 1 and audit[0].entity_id == casing_id
        assert "superseded by the SYN revision" in audit[0].details


def test_restore_and_refusals_and_the_mark_trail(world):
    db, dev, casing_id, _case_id = world
    entry = _entry(db, dev, "casing_calculations", casing_id)
    with pytest.raises(wb.WorkbenchError, match="not archived"):
        wb.restore(db, entry, "nothing to restore")
    wb.archive(db, entry, "first")
    with pytest.raises(wb.WorkbenchError, match="already archived"):
        wb.archive(db, entry, "twice")
    wb.restore(db, entry, "needed for the end-of-well report")
    assert wb.state(db, entry) == wb.ACTIVE
    assert ("casing_calculations", casing_id) in _keys(db, dev, include_archived=False)
    assert [(m["action"], m["reason"]) for m in wb.history_of(db, entry)] == [
        ("ARCHIVE", "first"), ("RESTORE", "needed for the end-of-well report")]


def test_archive_marks_are_insert_only(world):
    db, dev, casing_id, _case_id = world
    wb.archive(db, _entry(db, dev, "casing_calculations", casing_id), "guard check")
    with db.engine.begin() as conn:
        mark_id = conn.execute(text("SELECT id FROM calculation_archive_marks")).scalar_one()
    for statement in ("UPDATE calculation_archive_marks SET reason = 'edited' WHERE id = :i",
                      "UPDATE calculation_archive_marks SET action = 'RESTORE' WHERE id = :i",
                      "DELETE FROM calculation_archive_marks WHERE id = :i"):
        with pytest.raises(Exception, match="calculation_archive_marks"):
            with db.engine.begin() as conn:
                conn.execute(text(statement), {"i": mark_id})
    with db.session_scope() as session:
        assert session.get(CalculationArchiveMark, mark_id).reason == "guard check"


def test_clone_of_an_engine_record_is_a_linked_copy_not_a_rerun(world):
    db, dev, casing_id, _case_id = world
    entry = _entry(db, dev, "casing_calculations", casing_id)
    case = wb.clone(db, entry)
    assert case["name"] == "SYN M286 casing (clone)"
    assert case["inputs"] == entry.inputs                      # the frozen input snapshot, copied exactly
    assert case["inputs"]["parameters"]["internal_pressure_psi"] is None        # an absent load stays absent
    assert case["results"] == (entry.full_results or entry.results)
    assert case["method"] == CasingEngine.METHOD and case["method_version"] == entry.version
    assert "not recalculated" in case["note"]
    clone_entry = _entry(db, dev, "calculation_cases", case["id"])
    sources = [item for item in ch.lineage(db, clone_entry) if item["direction"] == "source"]
    assert [(s["link_type"], s["key"], s["verification_status"]) for s in sources] == [
        ("clone_of", f"casing_calculations:{casing_id}", "CLONE")]
    derived = [item for item in ch.lineage(db, entry) if item["direction"] == "derived"]
    assert [d["key"] for d in derived] == [f"calculation_cases:{case['id']}"]
    assert _entry(db, dev, "casing_calculations", casing_id).results == entry.results     # original unchanged


def test_clone_of_a_case_uses_the_case_clone_and_empty_inputs_are_refused(world):
    db, dev, _casing_id, case_id = world
    entry = _entry(db, dev, "calculation_cases", case_id)
    child = wb.clone(db, entry, "SYN variant")
    assert child["parent_id"] == case_id and child["name"] == "SYN variant"
    assert child["inputs"] == {"a_ft": 1.0} and child["results"] == {"b_ft": 2.0}
    entry.inputs = {}
    with pytest.raises(wb.WorkbenchError, match="no readable inputs"):
        wb.clone(db, entry)


def test_workbench_widget_archives_restores_and_clones(world):
    from PySide6.QtWidgets import QApplication

    from tabs.calculation_history_tab import CalculationHistoryTab

    db, dev, casing_id, _case_id = world
    app = QApplication.instance() or QApplication([])
    tab = CalculationHistoryTab(db_manager=db)
    try:
        tab.set_well(dev)

        def row_of(key):
            return next(i for i, e in enumerate(tab.entries) if e.key == key)

        key = f"casing_calculations:{casing_id}"
        total = tab.total
        tab.select_rows([row_of(key)])
        tab._update_actions()
        assert tab.archive_btn.isEnabled() and not tab.restore_btn.isEnabled() and tab.clone_btn.isEnabled()
        tab.ask_reason = lambda _title: None                       # cancelled: nothing happens
        assert tab.archive_selected() is None and tab.total == total
        tab.ask_reason = lambda _title: "SYN obsolete"
        assert tab.archive_selected()["state"] == wb.ARCHIVED
        assert "SYN obsolete" in tab.status.text() and "Nothing was deleted" in tab.status.text()
        assert tab.total == total - 1 and key not in {e.key for e in tab.entries}
        tab.show_archived.setChecked(True)
        assert tab.total == total
        row = row_of(key)
        assert tab.table.item(row, 1).text().endswith("[ARCHIVED]")
        tab.select_rows([row])
        tab._update_actions()
        assert tab.restore_btn.isEnabled() and not tab.archive_btn.isEnabled()
        assert tab.restore_selected()["state"] == wb.ACTIVE
        tab.select_rows([row_of(key)])
        case = tab.clone_selected()
        assert case is not None and tab.total == total + 1
        assert "not recalculated" in tab.status.text()
    finally:
        tab.deleteLater()
        del app


def test_saving_a_recalculation_keeps_its_confirmation_visible(world):
    """D83: the workbench used to refresh after writing the confirmation, replacing it with the row count."""
    from PySide6.QtWidgets import QApplication

    from tabs.calculation_history_tab import CalculationHistoryTab

    db, dev, casing_id, _case_id = world
    app = QApplication.instance() or QApplication([])
    tab = CalculationHistoryTab(db_manager=db)
    try:
        tab.set_well(dev)
        tab.select_rows([next(i for i, e in enumerate(tab.entries) if e.key == f"casing_calculations:{casing_id}")])
        assert tab.recalculate()["status"] == VERIFY_MATCH
        case = tab.save_recalculation()
        assert f"Stored recalculation as case #{case['id']}" in tab.status.text()
    finally:
        tab.deleteLater()
        del app


def test_a_record_that_reuses_a_deleted_records_id_does_not_inherit_its_archive_mark(world):
    db, dev, casing_id, _case_id = world
    wb.archive(db, _entry(db, dev, "casing_calculations", casing_id), "SYN: superseded")
    with db.session_scope() as session:                       # the record leaves (e.g. with its report)
        session.execute(text("DELETE FROM casing_calculations WHERE id = :i"), {"i": casing_id})
    reused = CasingCalculationRepository(db).save_run(
        inputs=INPUTS, result_values=CasingEngine.evaluate(**INPUTS).values, method=CasingEngine.METHOD,
        label="SYN M286 new casing", well_id=dev)
    assert reused == casing_id                                # SQLite reused the highest deleted id
    entry = _entry(db, dev, "casing_calculations", reused)    # listed by default: not archived
    assert wb.state(db, entry) == wb.ACTIVE and len(wb.history_of(db, entry)) == 1   # the old mark stays as evidence
