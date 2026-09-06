"""Regression coverage for the import transaction/schema boundary."""

from datetime import date
import sys
import types

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base,
    Company,
    DailyReport,
    DatabaseManager,
    Project,
    Section,
    SurveyPoint,
    Well,
)
from core.import_diagnostics import PersistenceError, PersistenceIssue
from core.excel_intelligence import DynamicTableExtractor
from core.mineru_engine import DocumentNormalizer


class QtStubs:
    """Allow the headless transaction test to import the Qt dialog."""

    def __enter__(self):
        self.modules = {}
        names = (
            "QApplication QColor QComboBox QDialog QDialogButtonBox QDir "
            "QEventLoop QFileDialog QGroupBox QHBoxLayout QHeaderView QInputDialog "
            "QLabel QLineEdit QMessageBox QProgressBar QPushButton QSplitter "
            "QTabWidget QTableWidget QTableWidgetItem QTextEdit QTimer QVBoxLayout "
            "QWidget QCheckBox QGridLayout QScrollArea QSpinBox QDoubleSpinBox "
            "QListWidget QFrame QToolButton QSizePolicy QAbstractItemView QFont "
            "QDate QTime QItemSelectionModel QStandardItemModel QStandardItem "
            "QBrush QPen QIcon QPixmap QPainter QPrinter QPrintDialog "
            "QSvgGenerator Signal Qt QKeySequence QThread QObject QModelIndex "
            "QVariant QRect QPoint QSize"
        ).split()

        class Fake:
            def __init__(self, *args, **kwargs):
                pass

            def __getattr__(self, name):
                return Fake

            def __call__(self, *args, **kwargs):
                return Fake()

            def connect(self, *args, **kwargs):
                return None

        for module_name in (
            "PySide6", "PySide6.QtWidgets", "PySide6.QtCore", "PySide6.QtGui",
            "PySide6.QtPrintSupport", "PySide6.QtSvg", "PySide6.QtNetwork",
        ):
            if module_name in sys.modules:
                continue
            module = types.ModuleType(module_name)
            module.__getattr__ = lambda name: Fake
            for name in names:
                setattr(module, name, Fake)
            module.__all__ = names
            sys.modules[module_name] = module
            self.modules[module_name] = module
        return self

    def __exit__(self, *args):
        for module_name in self.modules:
            sys.modules.pop(module_name, None)
        sys.modules.pop("dialogs.smart_template_dialog", None)
        sys.modules.pop("dialogs.excel_import_dialog", None)
        return False


def memory_manager():
    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(bind=manager.engine, autoflush=False, autocommit=False)
    return manager


def seed_report(manager):
    session = manager.create_session()
    company = Company(name="Architecture Co", code="ARCH")
    session.add(company)
    session.flush()
    project = Project(name="Architecture Project", code="ARCH-P", company_id=company.id)
    session.add(project)
    session.flush()
    well = Well(name="Architecture Well", project_id=project.id)
    session.add(well)
    session.flush()
    section = Section(name="12-1/4", well_id=well.id)
    session.add(section)
    session.flush()
    report = DailyReport(
        well_id=well.id,
        section_id=section.id,
        report_date=date(2026, 1, 1),
        report_number=1,
    )
    session.add(report)
    session.commit()
    ids = (well.id, report.id)
    session.close()
    return ids


def test_import_diagnostic_is_structured_and_traceable():
    issue = PersistenceIssue.from_exception(
        ValueError("bad source token"),
        stage="import.survey",
        entity="survey_points",
        field="inc",
        source={"file": "report.xlsx", "cell": "F42"},
        row=42,
        original_value="unknown",
        normalized_value=None,
        expected_type="FLOAT",
        operation="flush",
    )
    payload = issue.to_dict()
    assert payload["stage"] == "import.survey"
    assert payload["entity"] == "survey_points"
    assert payload["source"]["cell"] == "F42"
    assert payload["original_value"] == "unknown"
    assert payload["normalized_value"] is None
    assert payload["exception_type"] == "ValueError"
    assert "bad source token" in payload["traceback"]


def test_atomic_report_not_found_carries_persistence_issue():
    manager = memory_manager()
    with pytest.raises(PersistenceError) as raised:
        manager.save_imported_multi_tab_data_atomic(999, 999, {})
    issue = raised.value.to_dict()
    assert issue["stage"] == "persistence.atomic_import"
    assert issue["operation"] == "flush/commit"
    assert issue["exception_type"] == "ValueError"
    assert raised.value.result["diagnostics"]


def test_caller_owned_save_helper_flushes_without_committing():
    manager = memory_manager()
    session = manager.create_session()
    company = Company(name="Flush Co", code="FLUSH")
    session.add(company)
    session.flush()
    project = Project(name="Flush Project", code="FLUSH-P", company_id=company.id)
    session.add(project)
    session.flush()

    assert manager.save_well(
        {"project_id": project.id, "name": "Flush Well"}, session=session
    )
    assert session.in_transaction()
    assert session.query(Well).filter_by(name="Flush Well").one().id
    session.rollback()
    session.close()
    check = manager.create_session()
    assert check.query(Well).filter_by(name="Flush Well").count() == 0
    check.close()


@pytest.mark.parametrize(
    "stage,patch_target,include",
    [
        ("well", "db.save_well", "well"),
        ("mud_report", "dialog._save_mud_report", "mud"),
        ("drilling_parameters", "dialog._save_drilling_params", "drilling"),
        ("time_logs_24h", "dialog._save_time_logs", "time"),
        ("time_logs_morning", "dialog._save_morning_logs", "morning"),
        ("multi_tab_persistence", "db.save_imported_multi_tab_data_atomic", "multi"),
    ],
)
def test_outer_import_rolls_back_after_each_phase(monkeypatch, stage, patch_target, include):
    with QtStubs():
        from dialogs.excel_import_dialog import ExcelImportDialog

        manager = memory_manager()
        well_id, report_id = seed_report(manager)
        dialog = object.__new__(ExcelImportDialog)
        dialog.db = manager
        dialog.well_id = well_id

        def fail(*args, **kwargs):
            raise RuntimeError(f"injected {stage} failure")

        target_object, target_name = patch_target.split(".", 1)
        monkeypatch.setattr(
            manager if target_object == "db" else dialog,
            target_name,
            fail,
        )
        extracted = {
            "well_info": {"field_name": "Imported"} if include == "well" else {},
            "daily_report": {"report_date": "2026-01-03", "section_name": f"new-{stage}"},
        }
        if include == "mud":
            extracted["mud_report"] = {"mw": 10}
        if include == "drilling":
            extracted["drilling_params"] = {"wob_max": 4}
        if include == "time":
            extracted["time_logs_24h"] = [{"time_from": "00:00", "time_to": "01:00", "duration": 1}]
        if include == "morning":
            extracted["time_logs_morning"] = [{"time_from": "00:00", "time_to": "01:00", "duration": 1}]

        result = dialog._do_import(extracted)
        assert result["status"] == "PERSISTENCE_ERROR"
        assert result["failed"] == 1
        assert result["diagnostics"]
        assert result["diagnostics"][-1]["stage"] == f"import.{stage}"

        session = manager.create_session()
        assert session.query(Well).count() == 1
        assert session.query(Section).count() == 1
        assert session.query(DailyReport).count() == 1
        session.close()


def test_nullable_schema_migration_is_idempotent_and_preserves_rows(tmp_path):
    path = tmp_path / "legacy.sqlite"
    manager = DatabaseManager()
    manager.db_path = str(path)
    assert manager.initialize()
    session = manager.create_session()
    company = Company(name="Migration Co", code="MIG")
    session.add(company)
    session.flush()
    project = Project(name="Migration Project", code="MIG-P", company_id=company.id)
    session.add(project)
    session.flush()
    well = Well(name="Migration Well", project_id=project.id)
    session.add(well)
    session.flush()
    section = Section(name="8-1/2", well_id=well.id)
    session.add(section)
    session.flush()
    report = DailyReport(
        well_id=well.id, section_id=section.id, report_date=date(2026, 1, 2)
    )
    session.add(report)
    session.flush()
    session.add(SurveyPoint(well_id=well.id, report_id=report.id, md=100, inc=2, azi=3))
    session.commit()
    session.close()
    manager.close()

    engine = create_engine(f"sqlite:///{path}")
    columns = inspect(engine).get_columns("survey_points")

    def declaration(column):
        value = f'"{column["name"]}" {column["type"]}'
        if column["name"] in {"inc", "azi"}:
            value += " NOT NULL"
        if column.get("primary_key"):
            value += " PRIMARY KEY"
        return value

    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text(
            "CREATE TABLE survey_points_legacy ("
            + ", ".join(declaration(column) for column in columns)
            + ")"
        ))
        names = ", ".join(f'"{column["name"]}"' for column in columns)
        connection.execute(text(
            f"INSERT INTO survey_points_legacy ({names}) SELECT {names} FROM survey_points"
        ))
        connection.execute(text("DROP TABLE survey_points"))
        connection.execute(text("ALTER TABLE survey_points_legacy RENAME TO survey_points"))
        connection.execute(text("PRAGMA foreign_keys=ON"))
    engine.dispose()

    upgraded = DatabaseManager()
    upgraded.db_path = str(path)
    assert upgraded.initialize()
    assert upgraded.audit_orm_schema_nullable_contract() == []
    inspector = inspect(upgraded.engine)
    installed = {column["name"]: column for column in inspector.get_columns("survey_points")}
    assert installed["inc"]["nullable"] is True
    assert installed["azi"]["nullable"] is True
    session = upgraded.create_session()
    assert session.query(SurveyPoint).count() == 1
    session.close()
    upgraded.close()

    reopened = DatabaseManager()
    reopened.db_path = str(path)
    assert reopened.initialize()
    assert reopened.audit_orm_schema_nullable_contract() == []
    reopened.close()


def test_pdf_context_resolves_hrs_and_report_date_without_guessing():
    assert DocumentNormalizer._resolve_field("Hrs", "Time Log Morning") == "time_log_morning.duration"
    assert DocumentNormalizer._resolve_field("Hrs", "Time Log 24H") == "time_log.duration"
    assert DocumentNormalizer._resolve_field("Report Date", "Daily Report Header") == "daily_report.report_date"
    assert DocumentNormalizer._resolve_field("Report Date", "Well Information") == "well_info.report_date"
    assert DocumentNormalizer._resolve_field("Report Date") is None


def test_pdf_no_data_guard_accepts_collection_only_canonical_payload():
    with QtStubs():
        from dialogs.excel_import_dialog import has_meaningful_canonical_data

        assert has_meaningful_canonical_data({"surveys": [{"md": 100}]})
        assert has_meaningful_canonical_data({"document_tables": [{"Hrs": "2"}]})
        assert not has_meaningful_canonical_data({"metadata": {"pages": 2}, "surveys": []})


def test_semantic_table_resolution_overrides_layout_position():
    extractor = DynamicTableExtractor(
        {
            (10, 4): "Activity",
            (10, 8): "From",
            (10, 11): "To",
            (10, 14): "Hrs",
        },
        None,
    )
    columns = [
        {"field": "From", "col": 1},
        {"field": "To", "col": 3},
        {"field": "hrs", "col": 5},
        {"field": "Activity", "col": 7},
    ]
    resolved = extractor._resolve_semantic_columns({"start_row": 11}, columns, 11)
    assert [column["col"] for column in resolved] == [8, 11, 14, 4]
