"""P6 phase-2 defect regression: a blank or unparseable ``Hrs`` cell is not 0 hours.

The defect (recorded as INV34-002457, ``core/profile_import_engine.py:840``):
``_extract_time_logs`` coerced *any* ``Hrs`` cell that did not parse to
``0.0``, so a row that states a From/To anchor but no duration (or a
non-numeric duration such as ``N/A``) was extracted as a *measured zero hours*.
That collapses the three states the rest of the import path keeps separate:

* a blank duration is derived from the From/To anchors or stays unknown -
  ``ImportValidator.validate_time_logs``: ``duration_value = computed_dur if
  dur in (None, "") else None``, and a non-numeric source value is reported as
  ``"Duration must be numeric"`` with ``duration_value = None``
  (``core/import_quality.py``);
* the persistence boundary turns an unparseable duration into ``None`` plus a
  ``REVIEW_REQUIRED`` item preserving the source token, and persists a blank as
  ``NULL`` ("Invalid source rows are returned as review items rather than
  swallowed" - ``DDRImportService._save_time_logs``), which
  ``DatabaseManager.auto_update_from_daily_report`` counts as
  ``unrecorded_hours`` (``if log.duration is None``).

The fix keeps a parsed number, and otherwise passes the source cell through:
absent/blank -> ``None`` (unstated), non-numeric -> the original token, for the
review boundary to report.  An explicit numeric ``0`` still arrives as ``0.0``.

These tests exercise the real extractor and the real atomic save boundary on an
isolated database; no mocks.
"""

from datetime import date

import pytest

from core.database import (
    Company, DailyReport, DatabaseManager, Project, Section, TimeLog24H, Well,
)
from core.ddr_import_service import DDRImportService

HEADER = {
    1: "From", 2: "To", 3: "Hrs", 4: "Main Phase", 5: "Code", 6: "Sub",
    7: "Status", 8: "NPT", 9: "Rig Activity",
}


def _engine(rows):
    from core.profile_import_engine import ProfileImportEngine

    engine = ProfileImportEngine(None)
    engine.cell_cache = {"Time Logs": {1: dict(HEADER), **rows}}
    return engine


def test_blank_hrs_extracts_as_unstated_not_zero():
    engine = _engine({2: {1: "06:00", 2: "08:00", 3: None, 9: "Drill ahead"}})
    logs = engine._extract_time_logs("Time Logs")

    assert len(logs) == 1
    assert logs[0]["duration"] is None, "a blank Hrs cell is not a 0-hour claim"


def test_non_numeric_hrs_keeps_the_source_token_for_review():
    engine = _engine({2: {1: "06:00", 2: "08:00", 3: "N/A", 9: "Drill ahead"}})
    logs = engine._extract_time_logs("Time Logs")

    assert logs[0]["duration"] == "N/A", (
        "a stated-but-unparseable duration must reach the review boundary as the "
        "source token, never as 0.0"
    )


def test_numeric_hours_are_preserved_including_an_explicit_zero():
    engine = _engine({
        2: {1: "06:00", 2: "08:00", 3: 0, 9: "Reported zero hours"},
        3: {1: "08:00", 2: "14:00", 3: 6, 9: "Drill ahead"},
        4: {1: "14:00", 2: "16:30", 3: "2.5", 9: "Circ"},
    })
    logs = engine._extract_time_logs("Time Logs")

    assert [log["duration"] for log in logs] == [0.0, 6.0, 2.5]


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager()
    manager.db_path = str(tmp_path / "time_log_duration.db")
    assert manager.initialize()
    with manager.session_scope() as session:
        company = session.get(Company, 1)
        company.name, company.code = "Operator", "OP"
        project = session.get(Project, 1)
        project.name, project.code = "Audit", "AUDIT"
        well = session.get(Well, 1)
        well.name, well.code = "Audit Well", "AW"
        section = Section(name="Audit Section", well_id=well.id)
        session.add(section)
        session.flush()
        session.add(DailyReport(well_id=well.id, section_id=section.id, report_number=1,
                                report_date=date(2024, 10, 22)))
    yield manager
    manager.close()


def test_extraction_to_persistence_keeps_unknown_and_zero_apart(db):
    """The extractor's own rows through the real atomic save boundary.

    ``_combo_resolution`` is dropped here only because the code-resolution gate
    is a separate mechanism with its own evidence (p6-batch-012): leaving it in
    would divert the rows to combo review items before the duration rule is
    reached.
    """
    engine = _engine({
        2: {1: "06:00", 2: "08:00", 3: None, 9: "Blank hours"},
        3: {1: "08:00", 2: "10:00", 3: "N/A", 9: "Text hours"},
        4: {1: "10:00", 2: "12:00", 3: 0, 9: "Reported zero"},
    })
    logs = [dict(row, _combo_resolution=None) for row in engine._extract_time_logs("Time Logs")]
    assert [log["duration"] for log in logs] == [None, "N/A", 0.0]

    service = DDRImportService(db, 1)
    result = service._save_time_logs(1, logs)

    with db.session_scope() as session:
        stored = {row.activity_description: row.duration
                  for row in session.query(TimeLog24H).all()}

    # The boundary persists the blank as NULL and the explicit zero as 0.0 ...
    assert result["valid"] == 2
    assert stored == {"Blank hours": None, "Reported zero": 0.0}

    # ... and does NOT persist the row whose duration was supplied but is not a
    # number: it is routed to review with its source token ("Duration must be
    # numeric when supplied"), instead of being stored as a fabricated 0 hours.
    invalid = [item for item in result["review"] if item.get("classification") == "invalid_duration"]
    assert [item["original_value"] for item in invalid] == ["N/A"]
    assert invalid[0]["status"] == "REVIEW_REQUIRED"
    assert "Text hours" not in stored
