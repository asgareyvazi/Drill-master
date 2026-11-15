"""M204 (remainder): the immutability guards survive every non-statement write route - restore, migration and cascade.

* restore: a backup taken at the CURRENT schema version but without some guards (taken before a guard was added,
  e.g. the M218 report-revision guards, or from a file whose triggers a file writer dropped) is restored with the
  current guard set immediately - not only after the next application start;
* migration: an existing database without guards gains every guard on start and keeps its rows;
* cascade: deleting a well removes its guarded history (the owner's cascade) while a direct delete stays refused.

Real SQLite files in tmp_path, the real BackupService / RestoreService. SYNTHETIC data only.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date

import pytest

from core import db_maintenance as dm
from core import storage_guards
from tests.test_m198_backup_restore_qualification import _Admin
from tests.test_m70_integrity import _open, _seed

ALL_GUARDS = set(storage_guards.trigger_statements())
REPORT_GUARDS = {n for n in ALL_GUARDS if n.startswith("trg_report_revision_")}


def _triggers(path):
    with closing(sqlite3.connect(path)) as raw:                 # closed: a lingering handle blocks the restore
        return {r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall()}


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("DRILLMASTER_BACKUP_DIR", str(tmp_path / "backups"))
    db = _open(tmp_path / "live.sqlite", tmp_path, monkeypatch)
    db.m204_well = _seed(db)["A"][0]
    yield db, tmp_path
    db.close()


def _report_with_revision(db):
    from core.database import DailyReport, ReportRevision, Section, Well
    with db.session_scope() as s:
        well = s.get(Well, db.m204_well)
        section = Section(well_id=well.id, name="8.5")
        s.add(section)
        s.flush()
        report = DailyReport(well_id=well.id, section_id=section.id, report_number=1, report_date=date(2026, 9, 1))
        s.add(report)
        s.flush()
        revision = ReportRevision(report_id=report.id, revision_no=1, status="Submitted",
                                  snapshot={"report": {"summary": "frozen"}})
        s.add(revision)
        s.flush()
        return well.id, report.id, revision.id


def test_a_same_version_backup_without_guards_is_restored_with_every_current_guard(live):
    db, tmp = live
    _well, _report, revision_id = _report_with_revision(db)
    with closing(sqlite3.connect(db.db_path, isolation_level=None)) as raw:                     # the database as it was before M218
        for name in REPORT_GUARDS:
            raw.execute(f'DROP TRIGGER "{name}"')
    assert not REPORT_GUARDS & _triggers(db.db_path)
    backups = dm.BackupService(db, tmp / "backups")
    snapshot = backups.create_backup(_Admin())
    assert snapshot.ok, snapshot
    with closing(sqlite3.connect(db.db_path, isolation_level=None)) as raw:                     # the running app has its guards back meanwhile
        storage_guards.install(raw)
    result = dm.RestoreService(db, backups, drain_timeout=0.5, lock_timeout=0.5).restore(
        snapshot.path, _Admin(), confirmed=True)
    assert result.ok, result
    assert ALL_GUARDS <= _triggers(db.db_path)                    # immediately, in the same session
    with closing(sqlite3.connect(db.db_path, isolation_level=None)) as raw:
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            raw.execute("UPDATE report_revisions SET snapshot = '{}' WHERE id = ?", (revision_id,))


def test_an_existing_database_without_guards_gains_all_of_them_on_start_and_keeps_its_rows(live):
    from core.database import DatabaseManager, ReportRevision
    db, _tmp = live
    _well, _report, revision_id = _report_with_revision(db)
    db.close()
    with closing(sqlite3.connect(db.db_path, isolation_level=None)) as raw:
        for name in _triggers(db.db_path) & ALL_GUARDS:
            raw.execute(f'DROP TRIGGER "{name}"')
    assert not ALL_GUARDS & _triggers(db.db_path)
    again = DatabaseManager()
    again.db_path = db.db_path
    assert again.initialize()
    try:
        assert ALL_GUARDS <= _triggers(db.db_path)
        with again.session_scope() as s:
            assert s.get(ReportRevision, revision_id).snapshot == {"report": {"summary": "frozen"}}
    finally:
        again.close()


def test_the_owner_cascade_removes_guarded_history_but_a_direct_delete_is_refused(live):
    from core import calculation_cases as cc
    db, _tmp = live
    well, _report, revision_id = _report_with_revision(db)
    case = cc.save_case(db, calculator="Quick Calc", name="M204 cascade", inputs={"a": 1}, results={"r": 1},
                        well_id=well)
    with closing(sqlite3.connect(db.db_path, isolation_level=None)) as raw:
        with pytest.raises(sqlite3.DatabaseError, match="deleted only with its owner"):
            raw.execute("DELETE FROM calculation_cases WHERE id = ?", (case["id"],))
    assert db.delete_well(well)
    with closing(sqlite3.connect(db.db_path, isolation_level=None)) as raw:
        assert raw.execute("SELECT COUNT(*) FROM calculation_cases WHERE id = ?", (case["id"],)).fetchone() == (0,)
        assert raw.execute("SELECT COUNT(*) FROM report_revisions WHERE id = ?", (revision_id,)).fetchone() == (0,)
