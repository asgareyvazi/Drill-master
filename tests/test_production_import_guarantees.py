"""Focused regression tests for the production import boundary."""

from datetime import date
import sqlite3

from openpyxl import Workbook

from core.canonical_mapper import resolve_canonical_field, review_item
from core.excel_intelligence import ExcelIntelligence
from core.import_diagnostics import ImportStatus, determine_import_status
from core.import_router import route_file


def test_status_precedence_is_explicit_and_deterministic():
    assert determine_import_status() == ImportStatus.ACCEPT.value
    assert determine_import_status(review_required=True) == ImportStatus.REVIEW_REQUIRED.value
    assert determine_import_status(validation_error=True, review_required=True) == ImportStatus.VALIDATION_ERROR.value
    assert determine_import_status(persistence_error=True, validation_error=True) == ImportStatus.PERSISTENCE_ERROR.value


def test_contextual_ambiguous_pdf_labels_use_the_shared_resolver():
    assert resolve_canonical_field("Report Date", "Daily Report header") == "daily_report.report_date"
    assert resolve_canonical_field("Report Date", "Well Information") == "well_info.report_date"
    assert resolve_canonical_field("Hrs", "Morning Time Log") == "time_log_morning.duration"
    assert resolve_canonical_field("Hrs", "24H Time Log") == "time_log.duration"
    assert resolve_canonical_field("Hrs", "") is None


def test_review_item_retains_document_and_location_provenance():
    item = review_item(
        field="daily_report.report_date",
        original_value="not-a-date",
        location={"file": "DDR.pdf", "page": 2, "row": 4, "column": 1, "cell": "x=10,y=20"},
        reason="Date is not unambiguous",
        entity="daily_report",
    ).to_dict()
    assert item["source_document"] == "DDR.pdf"
    assert item["source_location"]["page"] == 2
    assert item["field"] == "daily_report.report_date"
    assert item["status"] == ImportStatus.REVIEW_REQUIRED.value


def test_unknown_xlsx_uses_excel_ir_without_mineru(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Unfamiliar Layout"
    sheet["A1"] = "Daily Report"
    sheet["A2"] = "Report Date"
    sheet["B2"] = date(2026, 9, 5)
    sheet["A4"] = "Morning Time Log"
    sheet["A5"] = "Hrs"
    sheet["B5"] = 8
    source = tmp_path / "arbitrary-name.xlsx"
    workbook.save(source)

    route = route_file(str(source), template_matcher=lambda _sheets: None)
    assert route.engine == "excel_intelligence"
    assert route.fallback_engine is None

    loaded = __import__("openpyxl").load_workbook(source, data_only=True)
    report = ExcelIntelligence(loaded, {}, source_file=str(source)).extract_generic()
    assert report.canonical_json["daily_report"]["report_date"] == date(2026, 9, 5)
    assert report.canonical_json["time_logs_morning"][0]["duration"] == 8
    assert report.fields_accepted == 0
    assert report.fields_review == 2
    assert all(result.status == "REVIEW_REQUIRED" for result in report.field_results)
    assert report.field_provenance["daily_report.report_date"]["source_sheet"] == "Unfamiliar Layout"


def test_generic_real_workbook_label_cannot_become_neighbor_value():
    from pathlib import Path
    from openpyxl import load_workbook

    source = Path(__file__).resolve().parents[1] / "08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx"
    workbook = load_workbook(source, data_only=True)
    try:
        report = ExcelIntelligence(workbook, {}, source_file=str(source)).extract_generic()
    finally:
        workbook.close()
    wind = next(item for item in report.field_results if item.canonical_field == "safety.wind_direction")
    assert wind.status != "OK"
    assert wind.value is None
    assert not any("TEMP" in str(candidate.get("value", "")).upper() for candidate in wind.candidates)
    assert report.canonical_json["safety"]["wind_direction"] is None


def test_generic_table_headers_are_not_stitched_across_blank_columns():
    from core.semantic_tables import detect_tables

    side_by_side = {
        (1, 1): "Measured Depth", (1, 2): "Inclination", (1, 5): "Azimuth",
        (2, 1): 100, (2, 2): 5, (2, 5): 200,
    }
    tables, _consumed = detect_tables({"Unknown": side_by_side})
    assert tables == []

    contiguous = {
        (1, 1): "Measured Depth", (1, 2): "Inclination", (1, 3): "Azimuth",
        (2, 1): 100, (2, 2): 5, (2, 3): 200,
    }
    tables, _consumed = detect_tables({"Unknown": contiguous})
    assert len(tables) == 1
    assert tables[0][1] == "surveys"
    assert tables[0][-1][0]["survey.md"] == 100


def test_unmerged_template_label_cannot_borrow_a_far_right_cell():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Test"
    sheet["B2"] = "Wind Direction"
    sheet["G2"] = "FLC-DA9 / FLC-DA413"
    template = {
        "sheet_1_Test": {
            "Safety": [{
                "field": "Wind Direction", "row": 2, "col": 2,
                "canonical": "safety.wind_direction",
            }],
        },
    }
    report = ExcelIntelligence(workbook, template).extract()
    result = next(item for item in report.field_results if item.canonical_field == "safety.wind_direction")
    assert result.status == "UNRESOLVED"
    assert report.canonical_json.get("safety", {}).get("wind_direction") != "FLC-DA9 / FLC-DA413"


def test_confidence_review_status_is_present_in_extraction_review_rows(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Test"
    sheet["A2"] = "Well Name"
    sheet["B2"] = "Well-42"
    source = tmp_path / "preferred-anchor.xlsx"
    workbook.save(source)
    template = {
        "sheet_1_Test": {
            "Well": [{
                "field": "Well Name", "row": 20, "col": 20,
                "canonical": "well_info.name",
            }],
        },
    }
    report, extracted = __import__("core.ddr_import_service", fromlist=["DDRImportService"]).DDRImportService().extract_file(
        str(source), template=template
    )
    result = next(item for item in report.field_results if item.canonical_field == "well_info.name")
    assert result.status == "REVIEW_REQUIRED"
    row = next(item for item in extracted["metadata"]["review_matrix"] if item["target_field"] == "well_info.name")
    assert row["decision"] == "REVIEW"
    assert row["normalized_value"] == "Well-42"


def test_unresolved_scalar_and_table_proposals_are_not_persisted(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from core.database import (
        Base, DatabaseManager, Company, Project, Well, Section,
        DailyReport, SurveyPoint, SafetyReport,
    )
    from core.ddr_import_service import DDRImportService
    from core.import_quality import unresolved_review_items

    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(bind=manager.engine, autoflush=False, autocommit=False)
    session = manager.create_session()
    try:
        company = Company(name="Review Company", code="REVIEW")
        session.add(company)
        session.flush()
        project = Project(name="Review Project", code="REVIEW", company_id=company.id)
        session.add(project)
        session.flush()
        well = Well(name="Review Well", code="REVIEW-WELL", project_id=project.id)
        session.add(well)
        session.flush()
        section = Section(name="Review Section", well_id=well.id)
        session.add(section)
        session.commit()
        well_id = well.id
    finally:
        session.close()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Unknown"
    sheet["A1"] = "Daily Report"
    sheet["A2"] = "Report Date"
    sheet["B2"] = date(2026, 9, 30)
    sheet["A4"] = "Wind Direction"
    sheet["B4"] = "NNE"
    sheet["D1"] = "Measured Depth"
    sheet["E1"] = "Inclination"
    sheet["F1"] = "Azimuth"
    sheet["D2"] = 100
    sheet["E2"] = 5
    sheet["F2"] = 200
    source = tmp_path / "unknown-source.xlsx"
    workbook.save(source)

    service = DDRImportService(manager, well_id)
    report, payload = service.extract_file(str(source), template={})
    assert report.template_version == "generic-ir"
    assert all(item["decision"] == "REVIEW" for item in payload["metadata"]["review_matrix"])
    assert {item["target_field"] for item in payload["metadata"]["review_matrix"]} >= {
        "daily_report.report_date", "safety.wind_direction",
        "survey.md", "survey.inc", "survey.azi",
    }
    # A user confirms only the report date. All generic scalar/table proposals
    # remain unresolved and must be absent from the persisted business data.
    report_date_review = next(
        item for item in payload["metadata"]["review_matrix"]
        if item["target_field"] == "daily_report.report_date"
    )
    report_date_review["decision"] = "ACCEPT"
    pending = unresolved_review_items(payload["metadata"]["review_matrix"])
    assert len(pending) == 4

    result = service.import_records(payload)
    assert result["report_id"] and result["status"] == "REVIEW_REQUIRED", result
    with manager.session_scope() as active:
        assert active.query(DailyReport).filter_by(id=result["report_id"]).count() == 1
        assert active.query(SurveyPoint).filter_by(report_id=result["report_id"]).count() == 0
        assert active.query(SafetyReport).filter_by(report_id=result["report_id"]).count() == 0

    # Explicit acceptance imports the table values; explicit rejection removes
    # the scalar proposal. Resolved review history stays in audit but does not
    # leave the final report in REVIEW_REQUIRED.
    resolved_reviews = [{
        "target_field": "daily_report.report_date", "canonical_field": "daily_report.report_date",
        "decision": "ACCEPT", "detected_table": "scalar",
    }]
    for field, column in (("survey.md", 1), ("survey.inc", 2), ("survey.azi", 3)):
        cell = f"R2C{column}"
        resolved_reviews.append({
            "target_field": field, "canonical_field": field,
            "decision": "CONFIRMED", "detected_table": "surveys",
            "row": 2, "column": column, "sheet": "Measurements",
            "source_cell": cell,
            "source_location": {"sheet": "Measurements", "row": 2, "column": column, "cell": cell},
        })
    resolved_reviews.append({
        "target_field": "safety.wind_direction", "canonical_field": "safety.wind_direction",
        "decision": "REJECT", "detected_table": "scalar",
    })
    resolved = DDRImportService(manager, well_id).import_records({
        "daily_report": {"report_date": date(2026, 10, 1)},
        "surveys": [{
            "md": 100, "inc": 5, "azi": 200,
            "_source_row": 2, "_source_sheet": "Measurements",
            "_source_cells": {"survey.md": "R2C1", "survey.inc": "R2C2", "survey.azi": "R2C3"},
        }],
        "safety": {"wind_direction": "NNE"},
        "metadata": {"review_matrix": resolved_reviews},
    })
    assert resolved["report_id"] and resolved["status"] == "ACCEPT", resolved
    with manager.session_scope() as active:
        assert active.query(SurveyPoint).filter_by(report_id=resolved["report_id"]).count() == 1
        assert active.query(SafetyReport).filter_by(report_id=resolved["report_id"]).count() == 0
    manager.close()


def test_review_helpers_block_pending_rows_and_apply_row_scoped_edits():
    from core.import_quality import apply_review_decisions, unresolved_review_items

    extracted = {
        "surveys": [{
            "md": 100, "inc": 5, "azi": 200,
            "_source_row": 2, "_source_sheet": "Measurements",
            "_source_cells": {"survey.md": "R2C1"},
        }],
    }
    item = {
        "target_field": "survey.md", "canonical_field": "survey.md",
        "detected_table": "surveys", "sheet": "Measurements",
        "row": 2, "column": 1, "source_cell": "R2C1",
        "source_location": {"sheet": "Measurements", "row": 2, "column": 1, "cell": "R2C1"},
        "original_value": 100, "normalized_value": 100, "value": 100,
        "decision": "REVIEW",
    }
    assert unresolved_review_items([item]) == [item]
    assert unresolved_review_items([item, None]) == [item]
    assert unresolved_review_items([{**item, "decision": "REJECT"}]) == []

    item["decision"] = "CONFIRMED"
    item["normalized_value"] = "150"
    item["value"] = "150"
    apply_review_decisions(extracted, [item])
    assert extracted["surveys"][0]["md"] == 150

    # MinerU review rows use a document-level table label and human-readable
    # page/row source text. The dotted field still resolves to its row list.
    extracted["surveys"][0]["md"] = 100
    pdf_item = {
        **item,
        "detected_table": "MinerU document",
        "source_cell": "page 1 row 2",
        "decision": "CONFIRMED",
        "normalized_value": "175",
        "value": "175",
    }
    apply_review_decisions(extracted, [pdf_item])
    assert extracted["surveys"][0]["md"] == 175

    rejected = {**item, "decision": "REJECT"}
    extracted["surveys"][0]["md"] = 150
    apply_review_decisions(extracted, [rejected])
    assert "md" not in extracted["surveys"][0]


def test_preview_confirm_requires_explicit_decisions_when_qt_is_available(monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import pytest
    widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from dialogs import excel_import_dialog as dialog_module

    app = widgets.QApplication.instance() or widgets.QApplication([])
    item = {
        "target_field": "survey.md", "canonical_field": "survey.md",
        "detected_table": "surveys", "decision": "REVIEW",
        "normalized_value": 100, "value": 100,
    }
    dialog = dialog_module.ImportPreviewDialog(
        "synthetic.xlsx", {"surveys": []}, {"review": [item], "errors": 0},
    )
    warnings = []

    class MessageBoxStub:
        @staticmethod
        def warning(*args):
            warnings.append(args)

    monkeypatch.setattr(dialog_module, "QMessageBox", MessageBoxStub)
    dialog._confirm()
    assert not dialog.confirmed and warnings
    dialog.table.item(0, 9).setText("ACCEPT")
    dialog._confirm()
    assert dialog.confirmed
    dialog.close()
    app.processEvents()


def test_v2_rebuild_preserves_unknown_live_sqlite_objects(tmp_path):
    from core.database import DatabaseManager

    path = tmp_path / "legacy-contract.sqlite"
    first = DatabaseManager()
    first.db_path = str(path)
    assert first.initialize()
    first.close()

    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute(
        "ALTER TABLE survey_points ADD COLUMN legacy_note TEXT NOT NULL DEFAULT 'keep'"
    )
    connection.execute(
        "INSERT INTO survey_points(id, well_id, md, inc, azi, legacy_note) "
        "VALUES (1, 1, 100, 2, 3, 'source')"
    )
    sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='survey_points'"
    ).fetchone()[0]
    legacy_sql = (
        sql.replace("inc FLOAT,", "inc FLOAT NOT NULL,")
        .replace("azi FLOAT,", "azi FLOAT NOT NULL,")
        .replace("PRIMARY KEY (id)", "PRIMARY KEY (id)")
        .replace("CREATE TABLE survey_points", "CREATE TABLE survey_points_legacy")
    )
    # Rebuild the table as a v1-style live schema while retaining the
    # additional column and source data.
    connection.execute(legacy_sql)
    columns = [row[1] for row in connection.execute("PRAGMA table_info(survey_points)").fetchall()]
    quoted = ", ".join(f'"{name}"' for name in columns)
    connection.execute(
        f"INSERT INTO survey_points_legacy ({quoted}) SELECT {quoted} FROM survey_points"
    )
    connection.execute("DROP TABLE survey_points")
    connection.execute("ALTER TABLE survey_points_legacy RENAME TO survey_points")
    connection.execute("CREATE INDEX survey_legacy_idx ON survey_points(legacy_note)")
    connection.execute("CREATE TABLE survey_audit (id INTEGER PRIMARY KEY, survey_id INTEGER)")
    connection.execute(
        "CREATE TRIGGER survey_legacy_trg AFTER UPDATE OF legacy_note ON survey_points "
        "BEGIN INSERT INTO survey_audit(survey_id) VALUES (new.id); END"
    )
    connection.commit()
    connection.close()

    upgraded = DatabaseManager()
    upgraded.db_path = str(path)
    assert upgraded.initialize()
    raw = upgraded.engine.raw_connection()
    try:
        columns = {row[1]: row for row in raw.execute("PRAGMA table_info(survey_points)")}
        assert columns["inc"][3] == 0
        assert columns["azi"][3] == 0
        assert columns["legacy_note"][4] == "'keep'"
        assert raw.execute("SELECT legacy_note FROM survey_points WHERE id=1").fetchone()[0] == "source"
        assert raw.execute("SELECT 1 FROM sqlite_master WHERE name='survey_legacy_idx'").fetchone()
        assert raw.execute("SELECT 1 FROM sqlite_master WHERE name='survey_legacy_trg'").fetchone()
        raw.execute("UPDATE survey_points SET legacy_note='changed' WHERE id=1")
        assert raw.execute("SELECT survey_id FROM survey_audit").fetchone()[0] == 1
    finally:
        raw.close()
        upgraded.close()


def test_future_schema_is_rejected_before_startup(tmp_path):
    path = tmp_path / "future.sqlite"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE schema_version (version INTEGER NOT NULL, applied_at DATETIME NOT NULL)"
    )
    connection.execute(
        "INSERT INTO schema_version(version, applied_at) VALUES (99, CURRENT_TIMESTAMP)"
    )
    connection.commit()
    connection.close()

    from core.database import DatabaseManager

    manager = DatabaseManager()
    manager.db_path = str(path)
    assert manager.initialize() is False
    assert manager.last_diagnostic["status"] == ImportStatus.PERSISTENCE_ERROR.value
    assert "future" in manager.last_diagnostic["message"].lower()
    manager.close()
