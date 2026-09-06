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
    assert report.field_provenance["daily_report.report_date"]["source_sheet"] == "Unfamiliar Layout"


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
