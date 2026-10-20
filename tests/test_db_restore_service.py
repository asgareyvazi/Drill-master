"""Safe restore: authorization, validation, staging, safety copy, recovery, audit (M43).

Destructive steps run only against temporary synthetic databases in tmp_path.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
from pathlib import Path

import pytest
from sqlalchemy import text

from core import db_maintenance as dm
from core import sqlite_connection
from core.authorization import AuthorizationError
from core.database import AuditLog, Company, DatabaseManager, Project, Well


class Principal:
    def __init__(self, *permissions, user_id=1, username="synthetic-admin"):
        self.permissions, self.user_id, self.username = set(permissions), user_id, username

    def has_permission(self, name):
        return name in self.permissions


ADMIN = Principal(dm.MAINTAIN_DATABASE)
VIEWER = Principal("can_export", "can_edit_reports", user_id=2, username="synthetic-viewer")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(data),
                       "DRILLMASTER_DB_PATH": str(data / "live.db"),
                       "DRILLMASTER_BACKUP_DIR": str(data / "backups"), "DRILLMASTER_AI_IMPORT": "0"}.items():
        monkeypatch.setenv(key, value)
    for key in ("DRILLMASTER_ENVIRONMENT", dm.KEEP_ENV, dm.INTERVAL_ENV, sqlite_connection.BUSY_TIMEOUT_ENV):
        monkeypatch.delenv(key, raising=False)
    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    with manager.session_scope() as session:
        company = Company(name="Snapshot Co", code="SNAP")
        session.add(company)
        session.flush()
        project = Project(company_id=company.id, name="Snapshot Project", code="SNAP-PR")
        session.add(project)
        session.flush()
        session.add(Well(project_id=project.id, name="Snapshot Well", code="SNAP-W1"))
    backups = dm.BackupService(manager, data / "backups")
    snapshot = backups.create_backup(ADMIN)
    assert snapshot.ok
    with manager.session_scope() as session:  # data written after the snapshot
        session.add(Company(name="Later Co", code="LATER"))
    restore = dm.RestoreService(manager, backups, drain_timeout=0.5, lock_timeout=0.5)
    yield manager, backups, restore, Path(snapshot.path)
    manager.close()


def _codes(manager):
    """Company codes created by these tests (the app also seeds its own defaults)."""
    with manager.session_scope() as session:
        codes = set(session.execute(text("SELECT code FROM companies")).scalars())
    return codes & {"SNAP", "LATER", "FLIGHT"}


def _fingerprint(manager):
    """Logical content of the live database (independent of WAL file layout)."""
    with manager.session_scope() as session:
        return [tuple(row) for row in session.execute(text(
            "SELECT 'c', id, code FROM companies UNION ALL SELECT 'w', id, code FROM wells ORDER BY 1, 2"))]


def _usable(manager):
    with manager.session_scope() as session:
        session.add(Company(name="Usable Afterwards", code=f"USE-{len(_codes(manager))}"))
    with manager.engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert connection.execute(text("PRAGMA integrity_check")).scalar() == "ok"


def _fail_at(stage, error=None):
    def fault(name):
        if name == stage:
            raise error or RuntimeError(f"injected failure at {stage}")
    return fault


def _staged_leftovers(manager):
    return list(Path(manager.db_path).parent.glob(dm.STAGED_PREFIX + "*"))


def _remanifest(backups, path, **changes):
    manifest = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    manifest.update(size=path.stat().st_size, sha256=dm._sha256(path), **changes)
    path.with_suffix(".json").write_text(json.dumps(manifest), encoding="utf-8")


# ---------------------------------------------------------------- success path

def test_authorized_restore_replaces_data_keeps_a_verified_safety_copy_and_audits(env):
    manager, backups, restore, snapshot = env
    snapshot_digest = dm._sha256(snapshot)
    result = restore.restore(snapshot, ADMIN, confirmed=True)
    assert result.ok and result.stage == "complete", result
    assert result.journal_complete and result.audit_recorded
    assert _codes(manager) == {"SNAP"}  # the later company is gone: the snapshot is live
    with manager.session_scope() as session:
        assert session.execute(text(
            "SELECT w.code FROM wells w JOIN projects p ON p.id=w.project_id JOIN companies c "
            "ON c.id=p.company_id WHERE c.code='SNAP'")).scalars().all() == ["SNAP-W1"]
        assert session.execute(text("PRAGMA foreign_key_check")).fetchall() == []
        assert session.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        entry = session.query(AuditLog).filter_by(action="database_restored").one()
        assert entry.username == "synthetic-admin" and json.loads(entry.details)["safety_copy"] == result.safety_copy
    safety = backups.backup_dir / result.safety_copy
    manifest = backups.read_manifest(safety, deep=True)
    assert manifest and manifest["kind"] == dm.KIND_SAFETY
    with sqlite3.connect(safety) as connection:  # the pre-restore data is preserved
        assert {"SNAP", "LATER"} <= {r[0] for r in connection.execute("SELECT code FROM companies")}
    assert dm._sha256(snapshot) == snapshot_digest  # the source backup is never modified
    events = [e["event"] for e in restore.journal.read()]
    assert events == ["restore_started", "restore_succeeded"]
    assert not _staged_leftovers(manager)
    _usable(manager)


def test_restoring_an_older_supported_schema_migrates_only_a_staged_copy(env):
    manager, backups, restore, snapshot = env
    connection = sqlite3.connect(snapshot)  # make the backup a genuine v5 database (v6 = indexes)
    for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'ix\\_%' ESCAPE '\\'").fetchall():
        connection.execute(f'DROP INDEX "{name}"')
    connection.execute("UPDATE schema_version SET version = 5")
    connection.commit()
    connection.close()
    _remanifest(backups, snapshot, schema_version=5)
    old_digest = dm._sha256(snapshot)
    result = restore.restore(snapshot, ADMIN, confirmed=True)
    assert result.ok, result
    assert dm._sha256(snapshot) == old_digest
    with manager.engine.connect() as live:
        assert live.execute(text("SELECT MAX(version) FROM schema_version")).scalar() == manager.schema_version
        assert live.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'ix\\_%' ESCAPE '\\'")).scalar() > 0
    assert _codes(manager) == {"SNAP"}


# ---------------------------------------------------------------- authorization and confirmation

def test_unauthorized_or_unconfirmed_restore_changes_nothing(env):
    manager, backups, restore, snapshot = env
    before = _fingerprint(manager)
    for actor in (VIEWER, None):  # None: no enforced principal -> fail closed
        with pytest.raises(AuthorizationError):
            restore.restore(snapshot, actor, confirmed=True)
    unconfirmed = restore.restore(snapshot, ADMIN, confirmed=False)
    assert not unconfirmed.ok and "confirmation" in unconfirmed.error
    assert _fingerprint(manager) == before and restore.journal.read() == []
    assert [p for p, _ in backups.list_backups(kinds=(dm.KIND_SAFETY,))] == []
    with manager.session_scope() as session:
        assert session.query(AuditLog).filter_by(action="authorization_denied", entity_type="database").count() == 2


# ---------------------------------------------------------------- candidate validation

def _assert_rejected_without_change(manager, backups, restore, candidate):
    before = _fingerprint(manager)
    result = restore.restore(candidate, ADMIN, confirmed=True)
    assert not result.ok and result.stage == "validate" and result.original_intact, result
    assert _fingerprint(manager) == before
    assert backups.list_backups(kinds=(dm.KIND_SAFETY,)) == [] and not _staged_leftovers(manager)
    # a refused candidate is journalled as a failure, but nothing was started
    assert [e["event"] for e in restore.journal.read()] == ["restore_failed"]
    restore.journal.path.unlink()
    return result


def test_corrupt_and_forged_candidates_are_rejected(env):
    manager, backups, restore, snapshot = env
    data = bytearray(snapshot.read_bytes())
    data[len(data) // 2] ^= 0xFF
    snapshot.write_bytes(bytes(data))  # digest no longer matches its manifest
    assert "manifest" in _assert_rejected_without_change(manager, backups, restore, snapshot).error
    snapshot.write_bytes(b"not a database at all, but a convincing manifest" * 100)
    _remanifest(backups, snapshot)
    assert "SQLite" in _assert_rejected_without_change(manager, backups, restore, snapshot).error


def test_future_and_foreign_schemas_are_rejected(env, tmp_path):
    manager, backups, restore, snapshot = env
    pristine = snapshot.read_bytes()
    with sqlite3.connect(snapshot) as connection:
        connection.execute("INSERT INTO schema_version (version, applied_at) VALUES (?, '2099-01-01')",
                           (manager.schema_version + 1,))
    _remanifest(backups, snapshot, schema_version=manager.schema_version + 1)
    assert "newer" in _assert_rejected_without_change(manager, backups, restore, snapshot).error
    snapshot.write_bytes(pristine)
    with sqlite3.connect(snapshot) as connection:
        connection.execute("DROP TABLE daily_reports")
    _remanifest(backups, snapshot)
    assert "not a DrillMaster" in _assert_rejected_without_change(manager, backups, restore, snapshot).error


def test_path_policy_rejects_outside_files_traversal_and_symlinks(env, tmp_path):
    manager, backups, restore, snapshot = env
    outside = tmp_path / snapshot.name
    shutil.copy2(snapshot, outside)
    shutil.copy2(snapshot.with_suffix(".json"), outside.with_suffix(".json"))
    _assert_rejected_without_change(manager, backups, restore, outside)
    traversal = backups.backup_dir / ".." / ".." / outside.name
    _assert_rejected_without_change(manager, backups, restore, traversal)
    _assert_rejected_without_change(manager, backups, restore, backups.backup_dir / "missing.db")
    _assert_rejected_without_change(manager, backups, restore, manager.db_path)
    if hasattr(os, "symlink"):
        link = backups.backup_dir / "drillmaster_backup_20260101T000000000000Z_0badf00d.db"
        try:
            link.symlink_to(snapshot)
        except OSError:  # Windows without symlink privilege
            return
        assert "symbolic" in _assert_rejected_without_change(manager, backups, restore, link).error


# ---------------------------------------------------------------- failure injection

@pytest.mark.parametrize("stage", ["stage", "maintenance", "safety_copy", "exclusive", "replace"])
def test_failures_before_replacement_leave_the_original_untouched(env, stage):
    manager, backups, restore, snapshot = env
    before = _fingerprint(manager)
    restore.fault = _fail_at(stage)
    result = restore.restore(snapshot, ADMIN, confirmed=True)
    assert not result.ok and result.stage == stage and result.original_intact and result.recovered is None
    assert _fingerprint(manager) == before and not _staged_leftovers(manager)
    # staging happens before the start event: nothing has been touched at that point
    started = [] if stage == "stage" else ["restore_started"]
    assert [e["event"] for e in restore.journal.read()] == started + ["restore_failed"]
    if stage in ("exclusive", "replace"):  # a verified safety copy exists and is kept
        assert backups.read_manifest(backups.backup_dir / result.safety_copy, deep=True)
    with manager.session_scope() as session:
        assert session.query(AuditLog).filter_by(action="database_restore_failed").count() == 1
    _usable(manager)


def test_failed_safety_copy_prevents_replacement(env, monkeypatch):
    manager, backups, restore, snapshot = env
    before = _fingerprint(manager)
    real_create = backups._create
    monkeypatch.setattr(backups, "_create", lambda kind: dm.BackupResult(False, error="injected disk full")
                        if kind == dm.KIND_SAFETY else real_create(kind))
    result = restore.restore(snapshot, ADMIN, confirmed=True)
    assert not result.ok and result.stage == "safety_copy" and "safety copy" in result.error
    assert _fingerprint(manager) == before and result.safety_copy is None
    _usable(manager)


def test_os_level_replace_failure_keeps_the_original(env, monkeypatch):
    manager, backups, restore, snapshot = env
    before = _fingerprint(manager)
    real_replace = os.replace
    live = Path(manager.db_path)

    def deny(source, target, *args, **kwargs):
        if Path(target) == live:
            raise PermissionError("simulated Windows sharing violation on the live file")
        return real_replace(source, target, *args, **kwargs)

    monkeypatch.setattr(os, "replace", deny)
    result = restore.restore(snapshot, ADMIN, confirmed=True)
    assert not result.ok and result.stage == "replace" and result.original_intact
    monkeypatch.undo()
    assert _fingerprint(manager) == before and not _staged_leftovers(manager)
    _usable(manager)


def test_post_replacement_failure_recovers_from_the_safety_copy(env):
    manager, backups, restore, snapshot = env
    before = _fingerprint(manager)
    restore.fault = _fail_at("reopen", dm.VerificationError("injected post-restore verification failure"))
    result = restore.restore(snapshot, ADMIN, confirmed=True)
    assert not result.ok and result.stage == "reopen" and result.recovered is True and result.original_intact
    assert _fingerprint(manager) == before  # the pre-restore data is live again
    assert [e["event"] for e in restore.journal.read()] == ["restore_started", "restore_recovered"]
    assert backups.read_manifest(backups.backup_dir / result.safety_copy, deep=True)
    _usable(manager)


def test_failed_recovery_keeps_the_verified_safety_copy_and_says_so(env, monkeypatch):
    manager, backups, restore, snapshot = env
    restore.fault = _fail_at("reopen")
    monkeypatch.setattr(restore, "_put_back", lambda *_: (_ for _ in ()).throw(OSError("injected recovery failure")))
    result = restore.restore(snapshot, ADMIN, confirmed=True)
    assert not result.ok and result.recovered is False and not result.original_intact
    safety = backups.backup_dir / result.safety_copy
    assert backups.read_manifest(safety, deep=True)
    with sqlite3.connect(safety) as connection:
        assert {"SNAP", "LATER"} <= {r[0] for r in connection.execute("SELECT code FROM companies")}
    assert restore.journal.read()[-1]["event"] == "restore_recovery_failed"


# ---------------------------------------------------------------- connections, WAL, concurrency

def test_an_open_transaction_blocks_the_restore_until_it_ends(env):
    manager, backups, restore, snapshot = env
    session = manager.Session()
    session.execute(text("INSERT INTO companies (name, code) VALUES ('In flight', 'FLIGHT')"))
    try:
        result = restore.restore(snapshot, ADMIN, confirmed=True)
        assert not result.ok and result.stage == "maintenance" and "transactions" in result.error
    finally:
        session.rollback()
        session.close()
    assert "FLIGHT" not in _codes(manager) and "LATER" in _codes(manager)
    assert restore.restore(snapshot, ADMIN, confirmed=True).ok


def test_database_access_during_maintenance_is_refused_not_silently_redirected(env):
    manager, backups, restore, snapshot = env
    observed = {}

    def probe(stage):
        if stage == "exclusive":
            try:
                with manager.session_scope() as session:
                    session.execute(text("SELECT 1")).scalar()
                observed["access"] = "allowed"
            except dm.MaintenanceActive:
                observed["access"] = "refused"

    restore.fault = probe
    assert restore.restore(snapshot, ADMIN, confirmed=True).ok
    assert observed == {"access": "refused"}


def test_another_open_connection_prevents_replacement(env):
    manager, backups, restore, snapshot = env
    before = _fingerprint(manager)
    other = sqlite3.connect(manager.db_path)  # e.g. a second application instance
    other.execute("SELECT COUNT(*) FROM companies").fetchall()
    try:
        result = restore.restore(snapshot, ADMIN, confirmed=True)
        assert not result.ok and result.stage == "exclusive" and "another process" in result.error
    finally:
        other.close()
    assert _fingerprint(manager) == before
    _usable(manager)


def test_concurrent_restore_requests_cannot_overlap(env):
    manager, backups, restore, snapshot = env
    entered, release = threading.Event(), threading.Event()

    def hold():
        with backups.exclusive(timeout=1):
            entered.set()
            release.wait(10)

    holder = threading.Thread(target=hold)
    holder.start()
    try:
        assert entered.wait(10)
        result = restore.restore(snapshot, ADMIN, confirmed=True)
        assert not result.ok and result.stage == "lock" and "already running" in result.error
        assert result.audit_recorded  # refused attempts are audited too
    finally:
        release.set()
        holder.join(10)
    assert not holder.is_alive()
    assert restore.restore(snapshot, ADMIN, confirmed=True).ok


# ---------------------------------------------------------------- audit policy

def test_journal_start_failure_aborts_before_any_change(env):
    manager, backups, restore, snapshot = env
    before = _fingerprint(manager)
    restore.fault = _fail_at("journal:restore_started", OSError("journal disk full"))
    result = restore.restore(snapshot, ADMIN, confirmed=True)
    assert not result.ok and result.stage == "journal" and result.original_intact
    assert _fingerprint(manager) == before and result.safety_copy is None


def test_outcome_audit_failures_never_turn_into_a_false_report(env):
    manager, backups, restore, snapshot = env
    restore.fault = _fail_at("journal:restore_succeeded", OSError("journal disk full"))
    result = restore.restore(snapshot, ADMIN, confirmed=True)
    assert result.ok and result.journal_complete is False  # restore happened; the gap is reported
    restore.fault = _fail_at("audit", RuntimeError("audit store down"))
    second = restore.restore(Path(backups.list_backups(kinds=(dm.KIND_BACKUP,))[0][0]), ADMIN, confirmed=True)
    assert second.ok and second.audit_recorded is False
    restore.fault = None
    failed = dm.RestoreService(manager, backups, drain_timeout=0.5)
    failed.fault = lambda stage: (_ for _ in ()).throw(RuntimeError("x")) if stage in ("exclusive", "audit") else None
    outcome = failed.restore(Path(backups.list_backups(kinds=(dm.KIND_BACKUP,))[0][0]), ADMIN, confirmed=True)
    assert not outcome.ok and outcome.audit_recorded is False and outcome.journal_complete
