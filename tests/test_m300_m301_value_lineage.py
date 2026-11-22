"""M300: every review item gets one lineage check; M301: lineage of imported values without a review item.

Real Excel route on the SYNTHETIC golden workbook (tests/fixtures/synthetic_ddr_golden_a.xlsx), fresh database.
M300 outcomes: MATCH / CHANGED_SINCE against the latest correction, else the value persisted when the import
accepted the proposal; NOT_CHECKED with a reason when that is unknown; UNREADABLE for a corrupt payload or
history; NOT_APPLICABLE when nothing was accepted. M301: header values imported without review get a stable
identity and the same stages from the immutable import audit; no review item is ever created for them.
"""
from __future__ import annotations

import json
import shutil
import warnings
from pathlib import Path

import pytest
from sqlalchemy import text

from core import ddr_value_states as vs
from core import import_value_lineage as ivl

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_ddr_golden_a.xlsx"


def _import(tmp_path, accept=(), cells=None):
    from PySide6.QtWidgets import QApplication

    from core import ddr_import_pipeline as pipe
    from core.database import DatabaseManager, Project, Well
    from core.ddr_import_service import DDRImportService
    from core.ddr_well_identity import CHOOSE_SELECTED, make_decision
    from core.import_quality import apply_review_decisions
    from core.import_router import route_file
    from dialogs.excel_import_dialog import has_meaningful_canonical_data

    QApplication.instance() or QApplication([])
    source = tmp_path / "golden.xlsx"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if cells:
            import openpyxl
            book = openpyxl.load_workbook(FIXTURE)
            for cell, value in cells.items():
                book["DDR Remark"][cell] = value
            book.save(source)
        else:
            shutil.copyfile(FIXTURE, source)
        service = DDRImportService()
        out = pipe.prepare_import(str(source), route=route_file, template_matcher=service._auto_match_template,
                                  extract_file=service.extract_file, meaningful=has_meaningful_canonical_data)
    for row in out.import_report["review"]:
        row["decision"] = "ACCEPT" if row.get("target_field") in accept else "DEFER"
    apply_review_decisions(out.extracted, out.import_report["review"])
    db = DatabaseManager()
    db.db_path = str(tmp_path / "m300.db")
    assert db.initialize()
    with db.session_scope() as session:
        well = Well(name="M300 selected", code="M300", project_id=session.query(Project).first().id)
        session.add(well)
        session.flush()
        well_id = well.id
    target = DDRImportService(db, well_id)
    out.extracted["metadata"]["well_identity_decision"] = make_decision(
        target.assess_well_identity(out.extracted["well_info"]), CHOOSE_SELECTED, "M300 test")
    result = target.import_records(out.extracted)
    assert result["report_id"], result["details"]
    items = {i["target_field"]: i for i in db.get_import_review_items(well_id) if i["review_type"] != "continuation"}
    return db, well_id, result["report_id"], items


@pytest.fixture
def accepted(tmp_path):
    # R11 (depth 06:00) blank: the extractor proposes 155 from the neighbouring cell for review; the operator accepts.
    db, well, report, items = _import(tmp_path, accept=("daily_report.depth_0600", "mud_report.oil_percent",
                                                        "daily_report.note_03"), cells={"R11": None})
    yield db, well, report, items
    db.close()


def _set_report(db, report, column, value):
    from core.database import DailyReport
    with db.session_scope() as session:
        setattr(session.get(DailyReport, report), column, value)


def _payload(db, item_id, mutate):
    from core.database import ImportReviewItem
    with db.session_scope() as session:
        row = session.get(ImportReviewItem, item_id)
        data = json.loads(row.payload_json)
        mutate(data)
        row.payload_json = json.dumps(data)


# ---- M300 ----------------------------------------------------------------------------------------------------
def test_accepted_without_correction_is_checked_against_the_persisted_value(accepted):
    db, well, report, items = accepted
    item = items["daily_report.depth_0600"]
    assert item["state"] == "ACCEPTED" and item["payload"]["normalized_value"] == 155.0
    lineage = ivl.value_lineage(db, item["id"], well)
    assert lineage["check"] == ivl.MATCH and lineage["expected"] == lineage["stored_now"] == 155.0
    assert lineage["expected_basis"] == "the value persisted when the import accepted it"
    _set_report(db, report, "depth_0600", 170.0)                   # changed later by another route
    changed = ivl.value_lineage(db, item["id"], well)
    assert changed["check"] == ivl.CHANGED_SINCE and (changed["stored_now"], changed["expected"]) == (170.0, 155.0)
    assert "CHANGED SINCE ACCEPTANCE" in ivl.summary_line(changed)


def test_an_accepted_proposal_without_a_value_is_reported_as_such(accepted):
    db, well, _report, items = accepted
    oil = items["mud_report.oil_percent"]                          # golden: "5" under a combined label, no value
    lineage = ivl.value_lineage(db, oil["id"], well)
    assert (lineage["check"], lineage["expected"], lineage["stored_now"]) == (ivl.MATCH, None, None)
    assert lineage["reason"] == "the accepted proposal carried no value and the field is still empty"


def test_an_unresolvable_target_is_not_checked_with_the_reason(accepted):
    db, well, _report, items = accepted
    lineage = ivl.value_lineage(db, items["daily_report.note_03"]["id"], well)
    assert lineage["check"] == ivl.NOT_CHECKED and "cannot be resolved" in lineage["reason"]
    assert "NOT_CHECKED: the target cannot be resolved" in ivl.summary_line(lineage)


def test_without_a_snapshot_the_normalized_value_is_used_unless_a_conversion_is_declared(accepted):
    db, well, _report, items = accepted
    kcl = items["daily_report.depth_0600"]
    _payload(db, kcl["id"], lambda data: data.pop("target_at_creation"))
    lineage = ivl.value_lineage(db, kcl["id"], well)
    assert lineage["expected_basis"] == "the accepted normalized value (no persisted snapshot)"
    assert lineage["check"] == ivl.MATCH and lineage["expected"] == 155.0
    _payload(db, kcl["id"], lambda data: data.update(source_unit="ft", normalized_unit="m"))
    converted = ivl.value_lineage(db, kcl["id"], well)
    assert converted["check"] == ivl.NOT_CHECKED and "conversion" in converted["reason"]


def test_unreadable_payload_or_history_is_unreadable(accepted):
    db, well, _report, items = accepted
    oil, kcl = items["mud_report.oil_percent"], items["daily_report.depth_0600"]
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE import_review_items SET payload_json = '{broken' WHERE id = :id"), {"id": oil["id"]})
        conn.execute(text("UPDATE import_review_items SET decision_history_json = '[oops' WHERE id = :id"),
                     {"id": kcl["id"]})
    for item in (oil, kcl):
        lineage = ivl.value_lineage(db, item["id"], well)
        assert lineage["check"] == ivl.UNREADABLE and "cannot be read" in lineage["reason"]


def test_pending_and_rejected_items_are_not_applicable(accepted):
    db, well, _report, items = accepted
    pending = next(i for i in items.values() if i["state"] == "DEFERRED_UNRESOLVED")
    assert ivl.value_lineage(db, pending["id"], well)["check"] == ivl.NOT_APPLICABLE
    db.resolve_import_review_item(pending["id"], well, "REJECT", "SYN: not a value")
    rejected = ivl.value_lineage(db, pending["id"], well)
    assert rejected["check"] == ivl.NOT_APPLICABLE and "REJECTED" in rejected["reason"], rejected


def test_every_check_is_one_of_the_five_outcomes(accepted):
    db, well, _report, items = accepted
    assert {ivl.value_lineage(db, i["id"], well)["check"] for i in items.values()} <= set(ivl.CHECKS)


# ---- M301 ----------------------------------------------------------------------------------------------------
def _review_items(db):
    from core.database import ImportReviewItem
    with db.session_scope() as session:
        return session.query(ImportReviewItem).count()


def test_an_imported_header_value_without_review_has_a_stable_lineage(tmp_path):
    db, _well, report, _items = _import(tmp_path)
    try:
        before = _review_items(db)
        first = ivl.imported_value_lineage(db, report, "depth_0000")
        again = ivl.imported_value_lineage(db, report, "depth_0000")
        assert first["identity"] == again["identity"] and first["identity"].startswith(f"iv:{report}:daily_report.")
        assert [s["stage"] for s in first["stages"]] == list(ivl.STAGES)
        source, parsed, normalized, correction, final = first["stages"]
        assert (source["detail"]["sheet"], source["detail"]["cell"], source["detail"]["route"]) == \
            ("DDR Remark", "R9", "excel")
        assert parsed["detail"]["original_text"] in (155, 155.0, "155") and normalized["detail"]["value"] == 155.0
        assert correction["status"] == "NONE" and final["status"] == "IMPORTED_WITHOUT_REVIEW"
        assert first["check"] == ivl.MATCH and first["review_item_id"] is None
        assert _review_items(db) == before                                      # no fake review item
    finally:
        db.close()


def test_a_later_typed_entry_is_changed_since_and_named(tmp_path):
    db, _well, report, _items = _import(tmp_path)
    try:
        vs.record_authored(db, report, "depth_0000", "160")
        lineage = ivl.imported_value_lineage(db, report, "depth_0000")
        assert lineage["check"] == ivl.CHANGED_SINCE and lineage["stored_now"] == 160.0
        assert "typed entry" in lineage["reason"] and len(lineage["later_changes"]) == 1
        assert "155.0 -> 160.0" in lineage["later_changes"][0]["details"]
    finally:
        db.close()


def test_a_value_with_a_review_item_points_to_it_and_blank_fields_are_not_applicable(tmp_path):
    db, _well, report, _items = _import(tmp_path, cells={"R9": "1,500"})
    try:
        lineage = ivl.imported_value_lineage(db, report, "depth_0000")
        assert lineage["check"] == ivl.NOT_APPLICABLE and lineage["review_item_id"] is not None
        assert "review item" in lineage["reason"]
        wob = ivl.imported_value_lineage(db, report, "wob")
        assert wob["check"] == ivl.NOT_CHECKED and "no provenance" in wob["reason"]
    finally:
        db.close()


def test_a_report_without_an_import_record_is_not_checked(tmp_path):
    from synthetic_operations import build_synthetic_operations, make_file_database

    db = make_file_database(tmp_path / "manual.db")
    try:
        report = build_synthetic_operations(db)["reports"][1]
        lineage = ivl.imported_value_lineage(db, report, "depth_2400")
        assert lineage["check"] == ivl.NOT_CHECKED and "no import record" in lineage["reason"]
        assert lineage["identity"] is None and lineage["stages"] == []
        with pytest.raises(ivl.LineageError):
            ivl.imported_value_lineage(db, report, "summary")
    finally:
        db.engine.dispose()
