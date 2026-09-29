"""Data-quality orphan status must reflect real SQLite foreign-key violations."""
from __future__ import annotations

from datetime import date

import pytest

from test_scope_attribution import _base, _mgr, _report, _well


@pytest.fixture
def env():
    db = _mgr()
    project = _base(db)
    well = _well(db, project, "Orphan-check")
    report_id = _report(db, well, 1)
    yield db, {"a": well, "ra": report_id}
    db.close()


def _orphan_metric(db, report_id):
    from core.data_quality import DataQualityService

    return next(
        metric for metric in DataQualityService(db).for_report(report_id)
        if metric.name == "Orphan data check"
    )


def test_database_orphan_check_is_good_when_foreign_keys_are_clean(env):
    db, ids = env
    metric = _orphan_metric(db, ids["ra"])
    assert metric.value == 100.0
    assert metric.status == "good"
    assert metric.evidence["violation_count"] == 0


def test_database_orphan_check_reports_existing_fk_violations(env):
    db, ids = env
    # Simulate a legacy/raw writer that inserted an orphan while SQLite FK
    # enforcement was disabled. The normal DatabaseManager connection enables
    # FK enforcement, but a quality check must still find pre-existing damage.
    raw = db.engine.raw_connection()
    try:
        raw.execute("PRAGMA foreign_keys=OFF")
        raw.execute(
            "INSERT INTO cement_reports (well_id, report_id, report_date) "
            "VALUES (?, ?, ?)",
            (ids["a"], 987654321, date(2026, 1, 1).isoformat()),
        )
        raw.commit()
        raw.execute("PRAGMA foreign_keys=ON")
        raw.commit()
    finally:
        raw.close()

    metric = _orphan_metric(db, ids["ra"])
    assert metric.value == 0.0
    assert metric.status == "critical"
    assert metric.evidence["violation_count"] >= 1
    assert any(item["table"] == "cement_reports" for item in metric.evidence["violations"])


def test_database_orphan_check_is_unknown_when_integrity_query_fails(env, monkeypatch):
    from sqlalchemy.orm import Session

    db, ids = env
    execute = Session.execute

    def reject_integrity_query(self, statement, *args, **kwargs):
        if str(statement).strip().upper() == "PRAGMA FOREIGN_KEY_CHECK":
            raise RuntimeError("integrity query unavailable")
        return execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", reject_integrity_query)
    metric = _orphan_metric(db, ids["ra"])
    assert metric.value is None
    assert metric.status == "unknown"
    assert metric.confidence == 0.0
    assert metric.evidence["violation_count"] is None
