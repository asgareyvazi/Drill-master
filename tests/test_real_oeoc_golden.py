"""Real OEOC DDR golden regression — LTA, Safety, POB Logistics.

Verifies the complete canonical path for the real workbook
(08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx + templates/OEOC_DDR_v3.json):

    workbook/template -> extraction (canonical) -> database -> UI getters

Covers the three report categories:
    * Well-level LTA (daily_report.lta_day -> Well.lta_day)
    * Safety Report (days_without_lti, drill dates, Jalali provenance)
    * POB Logistics (logistics breakdown -> ServiceCompanyPOB rows)

No company-specific parsing is exercised here — only the generic
template/canonical/DB pipeline.
"""

import json
import os
from pathlib import Path

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

REPO = Path(__file__).resolve().parent.parent
WORKBOOK = REPO / "08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx"
TEMPLATE = REPO / "templates" / "OEOC_DDR_v3.json"


def _workbook():
    from openpyxl import load_workbook
    return load_workbook(str(WORKBOOK), data_only=True)


@pytest.fixture(scope="module")
def oeoc_report():
    """Extraction result (ImportReport) for the real OEOC workbook."""
    if not WORKBOOK.exists() or not TEMPLATE.exists():
        pytest.skip("Real OEOC workbook/template not available")
    from core.excel_intelligence import ExcelIntelligence
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    return ExcelIntelligence(_workbook(), template).extract()


@pytest.fixture(scope="module")
def canonical(oeoc_report):
    return oeoc_report.canonical_json


@pytest.fixture()
def db():
    """In-memory database for DB-path tests."""
    from core.database import DatabaseManager, Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(
        bind=manager.engine, autoflush=False, autocommit=False
    )
    return manager


def _seed_well_report(db):
    """Create Company/Project/Well/Section/DailyReport and return ids."""
    from core.database import Company, Project, Well, Section, DailyReport
    from datetime import date

    session = db.create_session()
    try:
        comp = Company(name="OEOC", code="OEOC")
        session.add(comp)
        session.flush()
        proj = Project(name="Test Project", code="T-P", company_id=comp.id)
        session.add(proj)
        session.flush()
        well = Well(
            name="OEOC Well", code="OEOC-W", field_name="Test",
            project_id=proj.id,
        )
        session.add(well)
        session.flush()
        sec = Section(name="17-1/2\"", well_id=well.id)
        session.add(sec)
        session.flush()
        report = DailyReport(
            well_id=well.id, section_id=sec.id, report_number=1,
            report_date=date(2024, 10, 22), status="Draft",
        )
        session.add(report)
        session.flush()
        session.commit()
        return well.id, sec.id, report.id
    finally:
        session.close()


# ============================================================
# 1. LTA — extraction
# ============================================================
class TestLTAExtraction:
    def test_lta_day_extracted(self, canonical):
        daily = canonical.get("daily_report", {})
        assert daily.get("lta_day") == 468, daily.get("lta_day")

    def test_actual_rig_days_extracted(self, canonical):
        daily = canonical.get("daily_report", {})
        assert daily.get("actual_rig_days") is not None
        assert float(daily["actual_rig_days"]) == pytest.approx(7.25)


# ============================================================
# 2. Safety — extraction
# ============================================================
class TestSafetyExtraction:
    def test_days_without_lti(self, canonical):
        safety = canonical.get("safety", {})
        assert safety.get("days_without_lti") == 468

    def test_last_bop_test_preserved_as_token(self, canonical):
        """Jalali date 1403-07-30 must be preserved as a provenance token,
        never parsed into a wrong-calendar date and never dropped."""
        safety = canonical.get("safety", {})
        assert safety.get("last_bop_test") == "1403-07-30"

    def test_drill_dates_not_contaminated(self, canonical):
        """Missing drill dates must stay missing — the extractor must NOT
        pick values from the neighbouring cement-additives column."""
        safety = canonical.get("safety", {})
        for key in ("last_fire_drill", "last_bop_drill", "last_h2s_drill"):
            assert safety.get(key) in (None, ""), f"{key} contaminated: {safety.get(key)}"


# ============================================================
# 3. POB Logistics — extraction
# ============================================================
class TestPOBExtraction:
    def test_pob_breakdown(self, canonical):
        logistics = canonical.get("logistics", {})
        assert logistics.get("pob_rig") == 76
        assert logistics.get("pob_client") == 3
        assert logistics.get("pob_msa") == 7
        assert logistics.get("pob_service") == 14
        assert logistics.get("pob_catering") == 22
        assert logistics.get("pob_labour") == 8

    def test_pob_total(self, canonical):
        logistics = canonical.get("logistics", {})
        assert logistics.get("pob_total") == 130

    def test_pob_breakdown_sums_to_total(self, canonical):
        logistics = canonical.get("logistics", {})
        breakdown = sum(
            logistics.get(k) or 0
            for k in ("pob_rig", "pob_client", "pob_msa", "pob_service",
                      "pob_catering", "pob_labour", "pob_other")
        )
        assert breakdown == logistics.get("pob_total")


# ============================================================
# Database path (canonical -> DB -> UI getters)
# ============================================================
class TestDatabasePath:
    def test_safety_and_pob_saved(self, db, canonical):
        from core.database import (DailyReport, SafetyReport, ServiceCompanyPOB,
                                   Well)
        well_id, section_id, report_id = _seed_well_report(db)

        # Well-level LTA: same merge the import dialog performs generically
        well_info = dict(canonical.get("well_info", {}))
        daily = canonical.get("daily_report", {})
        for key in ("lta_day", "actual_rig_days"):
            if key in daily and daily.get(key) not in (None, "") and key not in well_info:
                well_info[key] = daily[key]
        well_info["id"] = well_id
        assert db.save_well(well_info)

        # Canonical -> DB via the atomic importer
        result = db.save_imported_multi_tab_data_atomic(
            well_id, report_id, dict(canonical)
        )
        assert result.get("failed") == 0, result
        assert result.get("safety_report") == 1, result
        assert result.get("pob_records", 0) >= 1, result

        # Safety (UI tab w8 consumes get_safety_report)
        safety = db.get_safety_report(well_id, report_id=report_id)
        assert safety is not None
        assert safety["days_without_lti"] == 468
        assert safety["last_fire_drill"] is None
        assert "1403-07-30" in (safety.get("safety_observations") or "")

        # POB (UI tab w7 consumes get_service_company_pob)
        pobs = db.get_service_company_pob(well_id, report_id=report_id)
        companies = {p["company_name"]: p["personnel_count"] for p in pobs}
        assert companies.get("Rig Crew") == 76
        assert companies.get("Client") == 3
        assert companies.get("Labour") == 8
        total = sum(p["personnel_count"] for p in pobs)
        assert total == 130  # total row not stored -> no double counting

        # LTA (UI tab w1 consumes well data)
        well = db.get_well_by_id(well_id)
        assert well is not None
        assert well.get("lta_day") == 468

    def test_safety_drill_dates_never_fake(self, db, canonical):
        """Drill dates missing in the workbook must stay NULL in the DB —
        never defaulted to today or 0."""
        from core.database import DailyReport, SafetyReport
        well_id, section_id, report_id = _seed_well_report(db)
        db.save_imported_multi_tab_data_atomic(
            well_id, report_id, dict(canonical)
        )
        session = db.create_session()
        try:
            row = session.query(SafetyReport).filter_by(
                report_id=report_id
            ).first()
            assert row.last_fire_drill is None
            assert row.last_bop_drill is None
            assert row.last_h2s_drill is None
            assert row.days_without_lti == 468
        finally:
            session.close()


# ============================================================
# 4. 24h Time Log — Excel timedelta handling (14:00, 24:00)
# ============================================================
class _QtStubs:
    """Context manager: injects minimal PySide6 stubs so headless
    environments can import dialogs modules, then removes them again
    so other tests never observe the stubs."""

    def __enter__(self):
        import sys
        import types

        self._sys = sys
        self._stubs = {}
        qt_names = (
            "QApplication QColor QComboBox QDialog QDialogButtonBox QDir "
            "QEventLoop QFileDialog QGroupBox QHBoxLayout QHeaderView "
            "QInputDialog QLabel QLineEdit QMessageBox QProgressBar "
            "QPushButton QSplitter QTabWidget QTableWidget QTableWidgetItem "
            "QTextEdit QTimer QVBoxLayout QWidget QCheckBox QGridLayout "
            "QScrollArea QSpinBox QDoubleSpinBox QListWidget QFrame "
            "QToolButton QSizePolicy QAbstractItemView QFont QDate QTime "
            "QItemSelectionModel QStandardItemModel QStandardItem QBrush "
            "QPen QIcon QPixmap QPainter QPrinter QPrintDialog QSvgGenerator "
            "Signal Qt QColor QKeySequence QThread QObject QModelIndex "
            "QVariant QRect QPoint QSize"
        ).split()

        class _Fake:
            def __init__(self, *a, **k): pass
            def __getattr__(self, name): return _Fake
            def __call__(self, *a, **k): return _Fake()
            def connect(self, *a, **k): return None

        for mod_name in ("PySide6", "PySide6.QtWidgets", "PySide6.QtCore",
                         "PySide6.QtGui", "PySide6.QtPrintSupport",
                         "PySide6.QtSvg", "PySide6.QtNetwork"):
            if mod_name in sys.modules:
                continue
            mod = types.ModuleType(mod_name)
            mod.__getattr__ = lambda n: _Fake
            for name in qt_names:
                setattr(mod, name, _Fake)
            mod.__all__ = qt_names
            sys.modules[mod_name] = mod
            self._stubs[mod_name] = mod
        return self

    def __exit__(self, *exc):
        for name in self._stubs:
            self._sys.modules.pop(name, None)
        self._sys.modules.pop("dialogs.smart_template_dialog", None)
        self._sys.modules.pop("dialogs.excel_import_dialog", None)
        return False


class Test24HTimeLog:
    """Excel stores wall-clock times as datetime.timedelta cells
    (14:00 -> timedelta(seconds=50400), 24:00 -> timedelta(days=1)).
    They must be parsed, validated and stored — never dropped."""

    def test_raw_2400_timedelta_present_in_canonical(self, canonical):
        from datetime import timedelta
        logs = canonical.get("time_logs_24h", [])
        real = [r for r in logs if r.get("time_from") not in (None, "")]
        assert len(real) == 7
        # The day-closing row is 23:30 -> 24:00 (timedelta(days=1))
        last = real[-1]
        assert last["time_to"] == timedelta(days=1), last["time_to"]
        assert last["duration"] == pytest.approx(0.5)
        # Mid-day rows are plain timedeltas as well
        mid = real[3]  # 14:00 -> 21:30
        assert mid["time_from"] == timedelta(seconds=50400)
        assert mid["time_to"] == timedelta(seconds=77400)

    def test_to_time_timedelta_branch(self):
        """ValueNormalizer.to_time must accept dt_time, datetime,
        Excel timedelta and numeric fractions (no silent None)."""
        with _QtStubs():
            from dialogs.smart_template_dialog import ValueNormalizer
            from datetime import datetime, timedelta, time as dt_time

            assert ValueNormalizer.to_time(dt_time(6, 0)) == dt_time(6, 0)
            assert ValueNormalizer.to_time(datetime(2024, 10, 22, 14, 0)) == dt_time(14, 0)
            # Excel timedeltas (openpyxl time cells)
            assert ValueNormalizer.to_time(timedelta(seconds=50400)) == dt_time(14, 0)
            assert ValueNormalizer.to_time(timedelta(seconds=77400)) == dt_time(21, 30)
            assert ValueNormalizer.to_time(timedelta(seconds=84600)) == dt_time(23, 30)
            # 24:00 -> 00:00 convention (same as the "24:00" string branch)
            assert ValueNormalizer.to_time(timedelta(days=1)) == dt_time(0, 0)
            assert ValueNormalizer.to_time("24:00") == dt_time(0, 0)
            # Numeric fraction of a day
            assert ValueNormalizer.to_time(0.583333) == dt_time(13, 59)
            assert ValueNormalizer.to_time(None) is None

    def test_validator_minutes_handles_timedelta(self):
        """TimeLogValidator._to_minutes must treat Excel timedeltas and
        24:00 as 1440 minutes so the day-closing row validates."""
        from core.import_quality import TimeLogValidator
        from datetime import timedelta

        assert TimeLogValidator._to_minutes(timedelta(seconds=50400)) == 840
        assert TimeLogValidator._to_minutes(timedelta(days=1)) == 1440
        assert TimeLogValidator._to_minutes("24:00") == 1440

    def test_real_24h_rows_validate_clean(self, canonical):
        """The 7 real rows must close the 24h day without blocking errors."""
        from core.import_quality import TimeLogValidator
        real = [r for r in canonical.get("time_logs_24h", [])
                if r.get("time_from") not in (None, "")]
        report = TimeLogValidator.validate_logs(real, sheet="Time Logs 24H")
        assert report.failed == 0, report.issues

    def test_db_stores_2400_row(self, db, canonical):
        """The day-closing row 23:30 -> 24:00 is stored (00:00 convention)
        with its 0.5 h duration — the row is not dropped. Drives the same
        production save path the import dialog uses (_save_time_logs)."""
        from core.database import DailyReport, TimeLog24H
        well_id, section_id, report_id = _seed_well_report(db)
        with _QtStubs():
            from dialogs.excel_import_dialog import ExcelImportDialog
            dlg = object.__new__(ExcelImportDialog)
            dlg.db = db
            # Same filtering the dialog applies: drop all-empty rows
            valid = [
                row for row in canonical.get("time_logs_24h", [])
                if isinstance(row, dict)
                and row.get("time_from") not in (None, "")
                and row.get("time_to") not in (None, "")
            ]
            assert len(valid) == 7
            dlg._save_time_logs(report_id, valid)
        session = db.create_session()
        try:
            rows = session.query(TimeLog24H).filter_by(
                report_id=report_id
            ).order_by(TimeLog24H.id).all()
            assert len(rows) == 7
            last = rows[-1]
            assert (last.time_from.hour, last.time_from.minute) == (23, 30)
            assert (last.time_to.hour, last.time_to.minute) == (0, 0)
            assert last.duration == pytest.approx(0.5)
            total = sum(r.duration or 0 for r in rows)
            assert total == pytest.approx(24.0)
        finally:
            session.close()


# ============================================================
# 5. Lookahead — genuinely empty source rows stay excluded
# ============================================================
class TestLookaheadEmptySourceRows:
    """The workbook contains 13 lookahead rows; the last two (Oct 26 /
    Oct 27) have a date and 24 hrs but a genuinely empty activity cell.
    They must stay excluded — no fabricated activities."""

    def test_empty_activity_rows_excluded_from_canonical(self, canonical):
        lookahead = canonical.get("lookahead", [])
        assert len(lookahead) == 13
        with_activity = [r for r in lookahead
                         if str(r.get("activity", "")).strip()]
        assert len(with_activity) == 11
        # The two excluded rows really have no usable activity text
        empty = [r for r in lookahead
                 if not str(r.get("activity", "")).strip()]
        assert len(empty) == 2
        for row in empty:
            assert str(row.get("activity", "")).strip() == ""
            assert row.get("hours") in (None, "", 24)  # only a date/hours stub

    def test_only_eleven_stored(self, db, canonical):
        from core.database import DailyReport, SevenDaysLookahead
        well_id, section_id, report_id = _seed_well_report(db)
        result = db.save_imported_multi_tab_data_atomic(
            well_id, report_id, dict(canonical)
        )
        assert result.get("failed") == 0, result
        session = db.create_session()
        try:
            rows = session.query(SevenDaysLookahead).filter_by(
                report_id=report_id
            ).all()
            assert len(rows) == 11
            for row in rows:
                assert str(row.activity).strip(), row.activity
        finally:
            session.close()


# ============================================================
# 6. NPT -> Service Company preservation
# ============================================================
class TestNPTServiceCompany:
    """NPT hours belonging to a service company are preserved on the
    existing ServiceCompany row (service.npt_hours). No NPT records are
    invented when the source has none; the generic company mapping is
    used — no company-specific branches."""

    def test_no_npt_invented_for_real_workbook(self, canonical):
        services = canonical.get("service_companies", [])
        assert len(services) == 6
        for svc in services:
            assert str(svc.get("company_name", "")).strip()
            # Source workbook has no Total NPT values -> no npt_hours key,
            # and no NPTReport rows may be fabricated from nothing.
            assert svc.get("npt_hours") in (None, "")

    def test_six_companies_saved_no_duplicates(self, db, canonical):
        from core.database import (DailyReport, ServiceCompany)
        well_id, section_id, report_id = _seed_well_report(db)
        result = db.save_imported_multi_tab_data_atomic(
            well_id, report_id, dict(canonical)
        )
        assert result.get("failed") == 0, result
        session = db.create_session()
        try:
            rows = session.query(ServiceCompany).filter_by(
                report_id=report_id
            ).all()
            assert len(rows) == 6
            names = [r.company_name for r in rows]
            assert names.count("OEOC") == 2  # two distinct OEOC services
            assert sorted(names) == sorted(
                ["Vira", "APAD", "GEO Data", "OEOC", "SPAD Energy", "OEOC"]
            )
            assert all(r.npt_hours is None for r in rows)
        finally:
            session.close()

    def test_service_npt_hours_generic_path(self, db):
        """A service row WITH Total NPT hours keeps them on its existing
        ServiceCompany row — one row, no duplicate company."""
        from core.database import (DailyReport, ServiceCompany)
        well_id, section_id, report_id = _seed_well_report(db)
        canonical = {
            "service_companies": [
                {"company_name": "SPAD Energy", "service_type": "CMT Service",
                 "npt_hours": 4.5},
                {"company_name": "Vira", "service_type": "Mud Service",
                 "npt_hours": 2.25},
            ]
        }
        result = db.save_imported_multi_tab_data_atomic(
            well_id, report_id, canonical
        )
        assert result.get("failed") == 0, result
        companies = db.get_service_companies(well_id, report_id=report_id)
        assert len(companies) == 2
        by_name = {c["company_name"]: c for c in companies}
        assert by_name["SPAD Energy"]["npt_hours"] == pytest.approx(4.5)
        assert by_name["Vira"]["npt_hours"] == pytest.approx(2.25)

    def test_npt_report_responsible_party_from_contractor(self, db):
        """An NPT time-log row attributed to a company flows into the
        existing npt_reports representation with that company preserved."""
        from core.database import (DailyReport, TimeLog24H)
        from datetime import time
        well_id, section_id, report_id = _seed_well_report(db)
        session = db.create_session()
        try:
            session.add(TimeLog24H(
                report_id=report_id,
                time_from=time(14, 0), time_to=time(15, 0),
                duration=1.0, main_code="NPT", is_npt=True,
                contractor="SPAD Energy",
                activity_description="Cement unit breakdown",
            ))
            session.commit()
        finally:
            session.close()

        assert db.auto_update_from_daily_report(report_id) is True
        reports = db.get_npt_reports(report_id=report_id)
        assert len(reports) == 1
        assert reports[0]["responsible_party"] == "SPAD Energy"
        assert reports[0]["duration_hours"] == pytest.approx(1.0)


# ============================================================
# 7. Fuel/Water — canonical keys persist, no invented zeros
# ============================================================
class TestFuelWaterImport:
    """The 'Bulk Data' block (fw_/dw_/fuel_rig_/fuel_camp_ on hand,
    used, received) must land on FuelWaterInventory — previously the
    canonical keys did not match any column and the row was saved with
    fabricated zeros."""

    def test_fuel_water_canonical_values_persist(self, db, canonical):
        from core.database import DailyReport, FuelWaterInventory
        well_id, section_id, report_id = _seed_well_report(db)
        result = db.save_imported_multi_tab_data_atomic(
            well_id, report_id, dict(canonical)
        )
        assert result.get("failed") == 0, result
        session = db.create_session()
        try:
            row = session.query(FuelWaterInventory).filter_by(
                report_id=report_id
            ).first()
            assert row is not None
            # Source values from the real workbook
            assert row.fuel_stock == 80000
            assert row.fuel_camp_stock == 6100
            assert row.dw_stock == 1100
            assert row.water_stock == 28000
            assert row.water_received == 15000
            assert row.water_consumed == 12000
            assert row.fuel_consumed == 3000
            # Remaining = stock + received - consumed (water only; the
            # workbook has no fuel received -> fuel_remaining stays NULL
            # instead of a fabricated 0).
            assert row.water_remaining == pytest.approx(31000)
            assert row.fuel_remaining is None
        finally:
            session.close()

    def test_fuel_water_getter_exposes_extras(self, db, canonical):
        from core.database import DailyReport
        well_id, section_id, report_id = _seed_well_report(db)
        db.save_imported_multi_tab_data_atomic(well_id, report_id, dict(canonical))
        data = db.get_fuel_water_inventory(well_id, report_id=report_id)
        assert data and len(data) == 1
        row = data[0]
        assert row["fuel_stock"] == 80000
        assert row["dw_stock"] == 1100
        assert row["fuel_camp_stock"] == 6100


# ============================================================
# 8. Mud extras — chemistry + pit volumes + N.C provenance
# ============================================================
class TestMudExtrasImport:
    def test_mud_chemistry_persists(self, db, canonical):
        from core.database import DailyReport, MudReport
        from datetime import date as _date
        well_id, section_id, report_id = _seed_well_report(db)
        report_date = _date.fromisoformat(canonical["daily_report"]["report_date"])
        with _QtStubs():
            from dialogs.excel_import_dialog import ExcelImportDialog
            dlg = object.__new__(ExcelImportDialog)
            dlg.db = db
            dlg.well_id = well_id
            dlg._save_mud_report(
                dict(canonical.get("mud_report", {})), report_id,
                report_date,
            )
        session = db.create_session()
        try:
            row = session.query(MudReport).filter_by(report_id=report_id).first()
            assert row.calcium == 320
            assert row.kcl == 12
            assert row.total_hardness == 400
        finally:
            session.close()

    def test_report_header_volumes_map_to_mud(self, db, canonical):
        from core.database import DailyReport, MudReport
        well_id, section_id, report_id = _seed_well_report(db)
        # The dialog path performs the daily_report -> mud mapping; the
        # atomic saver alone cannot see the dialog. Exercise the dialog
        # helper directly with the real canonical data.
        from datetime import date as _date
        report_date = _date.fromisoformat(canonical["daily_report"]["report_date"])
        with _QtStubs():
            from dialogs.excel_import_dialog import ExcelImportDialog
            dlg = object.__new__(ExcelImportDialog)
            dlg.db = db
            dlg.well_id = well_id
            dlg._save_mud_report(
                dict(canonical.get("mud_report", {})), report_id,
                report_date,
                daily_report=canonical.get("daily_report", {}),
            )
        session = db.create_session()
        try:
            row = session.query(MudReport).filter_by(report_id=report_id).first()
            assert row.volume_hole == 218
            assert row.total_circulated == 758
            assert row.loss_surface == 158
            assert row.fl is None  # N.C -> NULL
            import json as _json
            pits = _json.loads(row.pit_volumes_json)
            assert pits["suction1_vol"] == 270
            assert pits["degasser_mw"] == 71
            assert pits["reserve3_mw"] == 62
            # N.C source token preserved as provenance, never 0
            assert "fl (original): N.C" in (row.summary or "")
        finally:
            session.close()


# ============================================================
# 9. Bit run summary + drilling parameter extras
# ============================================================
class TestBitRunImport:
    def test_bit_run_fields_map(self, db, canonical):
        from core.database import DailyReport, DrillingParameters
        well_id, section_id, report_id = _seed_well_report(db)
        from datetime import date as _date
        report_date = _date.fromisoformat(canonical["daily_report"]["report_date"])
        with _QtStubs():
            from dialogs.excel_import_dialog import ExcelImportDialog
            dlg = object.__new__(ExcelImportDialog)
            dlg.db = db
            dlg.well_id = well_id
            dlg._save_drilling_params(
                dict(canonical.get("drilling_params", {})), report_id,
                report_date,
                param_table=canonical.get("drilling_params_table") or [],
                scr_data=canonical.get("scr_data") or [],
            )
        session = db.create_session()
        try:
            row = session.query(DrillingParameters).filter_by(
                report_id=report_id
            ).first()
            assert row.bit_drilled == pytest.approx(70)
            assert row.cum_drilled == pytest.approx(76)
            assert row.hours_on_bottom == pytest.approx(8.5)
            assert row.cum_hours == pytest.approx(14)
            assert row.avg_rop == pytest.approx(5.428571, abs=1e-4)
            assert row.bit_no == "2"
            assert row.manufacturer == "KingDream"
        finally:
            session.close()


# ============================================================
# 10. BHA / downhole / formation / casing / cement / solid
#     control / material request — previously dropped rows
# ============================================================
class TestRowTablesPersistence:
    def test_bha_components_persist(self, db, canonical):
        from core.database import DailyReport, BHAReport
        well_id, section_id, report_id = _seed_well_report(db)
        db.save_imported_multi_tab_data_atomic(well_id, report_id, dict(canonical))
        session = db.create_session()
        try:
            row = session.query(BHAReport).filter_by(report_id=report_id).first()
            assert row is not None
            assert len(row.bha_data_json or []) == 9
            assert row.bha_data_json[0]["component_name"] == '17-1/2" MT Bit'
        finally:
            session.close()

    def test_downhole_formation_casing_cement_persist(self, db, canonical):
        import json as _json
        from core.database import (DailyReport, DownholeEquipment,
                                   FormationReport, CasingReport, CementReport)
        well_id, section_id, report_id = _seed_well_report(db)
        db.save_imported_multi_tab_data_atomic(well_id, report_id, dict(canonical))
        session = db.create_session()
        try:
            de = session.query(DownholeEquipment).filter_by(report_id=report_id).first()
            assert len(de.equipment_data_json or []) == 3
            assert de.equipment_data_json[0]["equipment_name"] == '9-1/2" Bit Sub'
            fr = session.query(FormationReport).filter_by(report_id=report_id).first()
            assert fr.formations_json[0]["name"] == "Aghajari"
            cs = session.query(CasingReport).filter_by(report_id=report_id).first()
            casing = _json.loads(cs.casing_json)
            assert casing[0]["size"] == 20
            assert casing[0]["grade"] == "K-55"
            assert casing[0]["thread"] == "BTC"
            cm = session.query(CementReport).filter_by(report_id=report_id).first()
            materials = _json.loads(cm.materials_json)
            assert len(materials) == 9
            assert materials[0]["material"] == "FLC-DA9 / FLC-DA413"
        finally:
            session.close()

    def test_solid_control_and_material_request_persist(self, db, canonical):
        from core.database import (DailyReport, EquipmentLog, MaterialRequest)
        well_id, section_id, report_id = _seed_well_report(db)
        db.save_imported_multi_tab_data_atomic(well_id, report_id, dict(canonical))
        session = db.create_session()
        try:
            eqs = session.query(EquipmentLog).filter_by(report_id=report_id).all()
            assert len(eqs) == 9
            assert all(e.equipment_type == "Solid Control" for e in eqs)
            names = {e.equipment_name for e in eqs}
            assert "Shaker #1" in names
            mrs = session.query(MaterialRequest).filter_by(report_id=report_id).all()
            assert len(mrs) == 1
            assert "Needle valve" in mrs[0].requested_items
        finally:
            session.close()

    def test_forecast_persists(self, db, canonical):
        from core.database import DailyReport
        from datetime import date as _date
        well_id, section_id, report_id = _seed_well_report(db)
        with _QtStubs():
            from dialogs.excel_import_dialog import ExcelImportDialog
            dlg = object.__new__(ExcelImportDialog)
            dlg.db = db
            dlg.well_id = well_id
            dr = dict(canonical.get("daily_report", {}))
            dr["well_id"] = well_id
            dr["section_id"] = section_id
            dr["report_date"] = _date.fromisoformat(canonical["daily_report"]["report_date"])
            if dr.get("forecast") in (None, ""):
                dr["forecast"] = canonical["daily_report"].get("forecast")
            saved = db.save_daily_report(dr)
        session = db.create_session()
        try:
            row = session.query(DailyReport).filter_by(id=saved["id"]).first()
            assert row.forecast == 'Cont. Drlg 17-1/2" HS.'
        finally:
            session.close()


# ============================================================
# 11. Surveys — missing derived values stay NULL (no invented 0)
# ============================================================
class TestSurveyNoInventedZeros:
    def test_surveys_keep_nulls(self, db, canonical):
        from core.database import DailyReport, SurveyPoint
        well_id, section_id, report_id = _seed_well_report(db)
        db.save_imported_multi_tab_data_atomic(well_id, report_id, dict(canonical))
        session = db.create_session()
        try:
            rows = session.query(SurveyPoint).filter_by(
                report_id=report_id
            ).order_by(SurveyPoint.md).all()
            assert len(rows) == 3
            for r in rows:
                # md/inc are real source values
                assert r.md in (50.0, 108.0, 146.0)
                # azi/tvd/north/east/vs/hd/dls were NOT in the workbook
                assert r.tvd is None
                assert r.north is None
                assert r.vs is None
                assert r.hd is None
                assert r.dls is None
        finally:
            session.close()


# ============================================================
# 12. Service companies — hole section / duration / issue
# ============================================================
class TestServiceCompanyExtraFields:
    def test_service_extra_fields_persist(self, db, canonical):
        from core.database import DailyReport, ServiceCompany
        well_id, section_id, report_id = _seed_well_report(db)
        db.save_imported_multi_tab_data_atomic(well_id, report_id, dict(canonical))
        session = db.create_session()
        try:
            rows = session.query(ServiceCompany).filter_by(
                report_id=report_id
            ).all()
            assert len(rows) == 6
            by_name_type = {(r.company_name, r.service_type): r for r in rows}
            spad = by_name_type[("SPAD Energy", "CMT Service")]
            assert spad.hole_section == '26" HS'
            assert spad.duration_day == pytest.approx(1)
            oeoc_wh = by_name_type[("OEOC", "Wellhead Crew")]
            assert oeoc_wh.duration_day == pytest.approx(3)
        finally:
            session.close()


# ============================================================
# 13. Boats header row must not leak into canonical data
# ============================================================
class TestBoatsNoPhantomRows:
    def test_boats_section_has_no_header_phantom(self, oeoc_report):
        """The Boats table in this workbook contains only its header
        (Name/Time/Date/... — merged cells). It must not be captured as a
        data record, so canonical 'boats' stays empty and nothing can
        persist as a phantom boat row."""
        canonical = oeoc_report.canonical_json
        boats = canonical.get("boats", []) or []
        assert boats == []
        for row in boats:
            # a data row must never consist solely of header tokens
            header_tokens = {"name", "time", "date", "status", "arrival",
                             "departure", "pax"}
            values = {str(v).strip().lower() for v in row.values() if v}
            assert not values.issubset(header_tokens)


# ============================================================
# 14. Full _do_import pipeline on a fresh DB (well creation)
# ============================================================
class TestFullImportPipeline:
    def test_do_import_creates_well_and_report(self, oeoc_report):
        """Regression: _resolve_import_well bound a SQLAlchemy Row object
        as project_id on fresh DBs (session.query(...).first() in 2.x is a
        Row, not a tuple) -> 'type Row is not supported' insert failure.
        The full production pipeline must import 102 records / 0 failed
        and create the well + daily report."""
        from core.database import DatabaseManager, Base, Company, Project, Well, DailyReport

        manager = DatabaseManager()
        manager.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(manager.engine)
        manager.Session = sessionmaker(
            bind=manager.engine, autoflush=False, autocommit=False
        )
        s0 = manager.create_session()
        comp = Company(name="OEOC", code="OEOC")
        s0.add(comp)
        s0.flush()
        proj = Project(name="P", code="P", company_id=comp.id)
        s0.add(proj)
        s0.commit()
        s0.close()

        with _QtStubs():
            from dialogs.excel_import_dialog import ExcelImportDialog
            dlg = object.__new__(ExcelImportDialog)
            dlg.db = manager
            dlg.well_id = None
            result = dlg._do_import(dict(oeoc_report.canonical_json))

        assert result.get("imported") == 102
        assert result.get("failed") == 0
        session = manager.create_session()
        try:
            well = session.query(Well).first()
            assert well is not None
            assert well.name == "AZNS-207"
            assert well.lta_day == 468
            report = session.query(DailyReport).first()
            assert report is not None
            assert report.report_date.isoformat() == "2024-10-22"
            assert report.forecast == 'Cont. Drlg 17-1/2" HS.'
        finally:
            session.close()


# ============================================================
# 15. save_survey_points NULL preservation (w6 UI save path)
# ============================================================
class TestSaveSurveyPointsNulls:
    def test_save_survey_points_keeps_derived_nulls(self, db):
        """Regression: save_survey_points defined its float helper inside
        the update branch, so the INSERT branch raised NameError, and
        derived columns were coerced to 0.0. Insert path must work and
        NULLs must persist for tvd/north/east/vs/hd/dls (inc/azi are
        NOT NULL -> 0)."""
        from core.database import SurveyPoint
        well_id, section_id, report_id = _seed_well_report(db)
        ok = db.save_survey_points([
            {
                "well_id": well_id,
                "section_id": section_id,
                "report_id": report_id,
                "md": 50.0,
                "inc": None,
                "azi": None,
                "tvd": None,
                "north": None,
                "east": None,
                "vs": None,
                "hd": None,
                "dls": None,
            }
        ])
        assert ok is True
        session = db.create_session()
        try:
            row = session.query(SurveyPoint).filter_by(
                report_id=report_id, md=50.0
            ).first()
            assert row is not None
            assert row.inc == 0      # NOT NULL column fallback
            assert row.azi == 0
            assert row.tvd is None
            assert row.north is None
            assert row.east is None
            assert row.vs is None
            assert row.hd is None
            assert row.dls is None
        finally:
            session.close()

    def test_save_survey_points_update_path_keeps_nulls(self, db):
        """Same row saved again (update path) must also keep NULLs."""
        from core.database import SurveyPoint
        well_id, section_id, report_id = _seed_well_report(db)
        point = {
            "well_id": well_id, "section_id": section_id,
            "report_id": report_id, "md": 108.0,
            "inc": 2.0, "azi": 180.0,
            "tvd": None, "north": None, "east": None,
            "vs": None, "hd": None, "dls": None,
        }
        assert db.save_survey_points([point]) is True
        assert db.save_survey_points([point]) is True
        session = db.create_session()
        try:
            rows = session.query(SurveyPoint).filter_by(report_id=report_id).all()
            assert len(rows) == 1
            assert rows[0].inc == 2.0
            assert rows[0].tvd is None
        finally:
            session.close()
