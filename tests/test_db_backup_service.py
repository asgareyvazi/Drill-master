"""Verified backup service: snapshot, manifest, naming, retention, locking, scheduling (M43).

Every database here is a temporary synthetic file under pytest's tmp_path.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
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
VIEWER = Principal("can_export", user_id=2, username="synthetic-viewer")


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
        company = Company(name="Synthetic Co", code="SYN-CO")
        session.add(company)
        session.flush()
        project = Project(company_id=company.id, name="Synthetic Project", code="SYN-PR")
        session.add(project)
        session.flush()
        session.add(Well(project_id=project.id, name="Synthetic Well", code="SYN-W1"))
    yield manager, data / "backups"
    manager.close()


def _service(manager, backup_dir, **kwargs):
    return dm.BackupService(manager, backup_dir, **kwargs)


def _managed_files(backup_dir):
    return sorted(p.name for p in backup_dir.glob("drillmaster_*.db"))


# ---------------------------------------------------------------- creation and verification

def test_backup_is_a_verified_single_file_snapshot_with_a_matching_manifest(env):
    manager, backup_dir = env
    with manager.session_scope() as session:  # still in the WAL, not checkpointed
        session.add(Company(name="Late WAL Co", code="SYN-WAL"))
    result = _service(manager, backup_dir).create_backup(ADMIN)
    assert result.ok and result.audit_recorded, result
    path = Path(result.path)
    assert dm.NAME_PATTERN.match(path.name) and path.parent == backup_dir
    assert not path.with_name(path.name + "-wal").exists()
    manifest = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    assert manifest == result.manifest
    assert manifest["kind"] == "backup" and manifest["schema_version"] == manager.schema_version
    assert manifest["size"] == path.stat().st_size and manifest["sha256"] == dm._sha256(path)
    assert set(manifest) == {"format", "kind", "file", "schema_version", "created_utc", "size", "sha256",
                             "app_version"}  # no data, names or paths
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT w.code, p.code, c.code FROM wells w JOIN projects p ON p.id=w.project_id "
            "JOIN companies c ON c.id=p.company_id WHERE w.code='SYN-W1'").fetchall() == [("SYN-W1", "SYN-PR", "SYN-CO")]
        assert connection.execute("SELECT COUNT(*) FROM companies WHERE code='SYN-WAL'").fetchone() == (1,)
    assert dm.BackupService(manager, backup_dir).list_backups(deep=True)[0][0] == path
    with manager.session_scope() as session:
        entry = session.query(AuditLog).filter_by(action="database_backup").one()
        assert entry.username == "synthetic-admin" and entry.entity_name == path.name
        assert "SYN-CO" not in (entry.details or "")


def test_interactive_backup_requires_the_maintenance_permission(env):
    manager, backup_dir = env
    service = _service(manager, backup_dir)
    for actor in (VIEWER, None):  # None: no enforced principal either -> fail closed
        with pytest.raises(AuthorizationError):
            service.create_backup(actor)
    assert _managed_files(backup_dir) == []
    with manager.session_scope() as session:
        assert session.query(AuditLog).filter_by(action="authorization_denied", entity_type="database").count() == 2
    scheduled = service.create_backup(scheduled=True)
    assert scheduled.ok
    with manager.session_scope() as session:
        assert session.query(AuditLog).filter_by(action="database_backup").one().username == "system:backup-scheduler"


def test_name_collision_never_touches_the_existing_file(env, monkeypatch):
    manager, backup_dir = env
    service = _service(manager, backup_dir)
    backup_dir.mkdir(parents=True)
    taken = backup_dir / "drillmaster_backup_20260101T000000000000Z_deadbeef.db"
    taken.write_bytes(b"someone else's file")
    names = iter([taken, backup_dir / "drillmaster_backup_20260101T000000000001Z_cafebabe.db"])
    monkeypatch.setattr(service, "_new_name", lambda kind: next(names))
    result = service.create_backup(ADMIN)
    assert result.ok and Path(result.path).name.endswith("cafebabe.db")
    assert taken.read_bytes() == b"someone else's file"


@pytest.mark.parametrize("stage, error", [("verify", dm.VerificationError("injected")),
                                          ("promote", OSError("injected disk full")),
                                          ("manifest", OSError("injected manifest failure"))])
def test_a_failed_backup_is_never_promoted_and_leaves_no_artifacts(env, stage, error):
    manager, backup_dir = env
    service = _service(manager, backup_dir)
    good = service.create_backup(ADMIN)
    before = {p.name: p.read_bytes() for p in backup_dir.iterdir() if p.is_file() and p.name != dm.LOCK_NAME}

    def fault(name):
        if name == stage:
            raise error

    service.fault = fault
    result = service.create_backup(ADMIN)
    assert not result.ok and "injected" in result.error and result.audit_recorded
    after = {p.name: p.read_bytes() for p in backup_dir.iterdir() if p.is_file() and p.name != dm.LOCK_NAME}
    assert after == before  # previous verified backup untouched, nothing partial or unverified left
    assert [p for p, _ in service.list_backups(deep=True)] == [Path(good.path)]
    with manager.session_scope() as session:
        assert session.query(AuditLog).filter_by(action="database_backup_failed").count() == 1


def test_verification_rejects_a_snapshot_corrupted_before_promotion(env):
    manager, backup_dir = env
    service = _service(manager, backup_dir)

    def corrupt_partial(stage):
        if stage == "verify":
            (partial,) = backup_dir.glob(dm.PARTIAL_PREFIX + "*.partial")
            data = bytearray(partial.read_bytes())
            data[100:4096] = b"\x00" * (4096 - 100)  # destroy the schema page
            partial.write_bytes(bytes(data))

    service.fault = corrupt_partial
    result = service.create_backup(ADMIN)
    assert not result.ok and "VerificationError" in result.error
    assert _managed_files(backup_dir) == [] and not list(backup_dir.glob("*.partial"))


def test_corrupted_backup_is_no_longer_listed_as_verified(env):
    manager, backup_dir = env
    service = _service(manager, backup_dir)
    path = Path(service.create_backup(ADMIN).path)
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0xFF
    path.write_bytes(bytes(data))
    assert service.read_manifest(path, deep=True) is None
    assert service.list_backups(deep=True) == []
    with pytest.raises(dm.VerificationError):
        dm.verify_database_file(backup_dir / "missing.db", max_version=manager.schema_version)


# ---------------------------------------------------------------- retention

def test_retention_keeps_the_newest_verified_backups_and_nothing_else_is_touched(env):
    manager, backup_dir = env
    service = _service(manager, backup_dir, keep=3)
    backup_dir.mkdir(parents=True)
    unrelated = {
        "notes.txt": b"operator notes",
        "drillmaster_backup_manual.db": b"not a managed name",
        "drillmaster_backup_20000101T000000000000Z_00000000.db": b"managed name, no manifest",
    }
    for name, content in unrelated.items():
        (backup_dir / name).write_bytes(content)
    safety = service._create(dm.KIND_SAFETY)
    created = [service.create_backup(ADMIN) for _ in range(5)]
    assert all(r.ok for r in created)
    kept = [p.name for p, _ in service.list_backups(kinds=(dm.KIND_BACKUP,), deep=True)]
    assert kept == [Path(r.path).name for r in reversed(created[-3:])]
    assert sum(len(r.removed) for r in created) == 2
    for name, content in unrelated.items():
        assert (backup_dir / name).read_bytes() == content
    assert Path(safety.path).is_file()  # pre-restore safety copies are never retention candidates
    assert Path(manager.db_path).is_file()


def test_a_failed_latest_attempt_never_removes_the_only_verified_backup(env):
    manager, backup_dir = env
    service = _service(manager, backup_dir, keep=1)
    only = service.create_backup(ADMIN)
    service.fault = lambda stage: (_ for _ in ()).throw(dm.VerificationError("injected")) if stage == "verify" else None
    for _ in range(3):
        assert not service.create_backup(ADMIN).ok
    assert [p for p, _ in service.list_backups(deep=True)] == [Path(only.path)]


def test_retention_survives_a_locked_file_and_reports_it(env, monkeypatch):
    manager, backup_dir = env
    service = _service(manager, backup_dir, keep=1)
    first = Path(service.create_backup(ADMIN).path)
    real_unlink = Path.unlink

    def unlink(self, *args, **kwargs):
        if self == first:
            raise PermissionError("simulated Windows sharing violation")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    result = service.create_backup(ADMIN)
    assert result.ok and result.retention_errors == [first.name] and first.is_file()


def test_settings_are_validated(monkeypatch):
    monkeypatch.setenv(dm.KEEP_ENV, "0")
    assert dm.retention_count() == dm.DEFAULT_KEEP
    monkeypatch.setenv(dm.KEEP_ENV, "abc")
    assert dm.retention_count() == dm.DEFAULT_KEEP
    monkeypatch.setenv(dm.KEEP_ENV, "4")
    assert dm.retention_count() == 4
    monkeypatch.setenv(dm.INTERVAL_ENV, "0")
    assert dm.interval_minutes() == 0
    monkeypatch.setenv(dm.INTERVAL_ENV, "2")
    assert dm.interval_minutes() == dm.DEFAULT_INTERVAL_MINUTES
    with pytest.raises(ValueError):
        dm.BackupService(object(), "unused", keep=0)


# ---------------------------------------------------------------- concurrency and scheduling

def test_concurrent_backup_calls_never_overlap(env):
    manager, backup_dir = env
    service = _service(manager, backup_dir)
    inside, release = threading.Event(), threading.Event()

    def hold(stage):
        if stage == "verify" and not inside.is_set():
            inside.set()
            assert release.wait(10)

    service.fault = hold
    results = {}
    worker = threading.Thread(target=lambda: results.setdefault("first", service.create_backup(ADMIN)))
    worker.start()
    try:
        assert inside.wait(10)
        second = service.create_backup(ADMIN)
        assert not second.ok and second.skipped and "already running" in second.error
    finally:
        release.set()
        worker.join(30)
    assert not worker.is_alive() and results["first"].ok


_LOCK_HOLDER = (
    # Same primitive as core.db_maintenance._ProcessLock on each platform.
    "import msvcrt, sys, time; f = open(sys.argv[1], 'a+b'); f.seek(0); "
    "msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1); print('locked', flush=True); time.sleep(60)"
    if os.name == "nt" else
    "import fcntl, sys, time; f = open(sys.argv[1], 'a+b'); fcntl.flock(f, fcntl.LOCK_EX); "
    "print('locked', flush=True); time.sleep(60)")


def test_another_process_holding_the_lock_blocks_backups_until_it_exits(env):
    manager, backup_dir = env
    backup_dir.mkdir(parents=True)
    holder = subprocess.Popen([sys.executable, "-c", _LOCK_HOLDER, str(backup_dir / dm.LOCK_NAME)],
                              stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "locked"
        blocked = _service(manager, backup_dir).create_backup(ADMIN)
        assert not blocked.ok and blocked.skipped and "another application instance" in blocked.error
    finally:
        holder.kill()  # a crashed/killed instance must not leave a permanent lock
        holder.wait(10)
        holder.stdout.close()
    assert _service(manager, backup_dir).create_backup(ADMIN).ok


def test_scheduler_runs_without_overlap_and_stops_cleanly(env):
    manager, backup_dir = env
    service = _service(manager, backup_dir, keep=2)
    state = {"inside": 0, "max": 0}
    lock = threading.Lock()

    def track(stage):
        if stage == "verify":
            with lock:
                state["inside"] += 1
                state["max"] = max(state["max"], state["inside"])
            time.sleep(0.05)
            with lock:
                state["inside"] -= 1

    service.fault = track
    outcomes = []
    scheduler = dm.BackupScheduler(service, 0.02, on_result=outcomes.append)
    assert scheduler.start() and not scheduler.start()
    deadline = time.monotonic() + 20
    while scheduler.runs < 3 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert scheduler.stop(timeout=30)
    runs = scheduler.runs
    time.sleep(0.1)
    assert scheduler.runs == runs >= 3 and state["max"] == 1
    assert all(r.ok for r in outcomes) and not scheduler.start()
    assert not any(t.name == "drillmaster-backup-scheduler" for t in threading.enumerate())
    assert not dm.BackupScheduler(service, 0).start()  # interval 0 = disabled


def test_shutdown_refuses_new_backups_and_audit_failure_is_reported(env):
    manager, backup_dir = env
    service = _service(manager, backup_dir)
    service.fault = lambda stage: (_ for _ in ()).throw(RuntimeError("audit store down")) if stage == "audit" else None
    result = service.create_backup(ADMIN)
    assert result.ok and result.audit_recorded is False  # the backup is real; the gap is reported
    service.fault = None
    service.shutdown()
    refused = service.create_backup(ADMIN)
    assert not refused.ok and refused.skipped


# ---------------------------------------------------------------- compatibility entry points

def test_auto_backup_and_backup_to_verify_before_publishing(env, tmp_path, monkeypatch):
    manager, backup_dir = env
    path = manager.auto_backup(backup_dir)
    assert path and Path(path).with_suffix(".json").is_file()
    destination = tmp_path / "export" / "copy.db"
    destination.parent.mkdir()
    destination.write_bytes(b"previous export")

    def refuse(_path):
        raise dm.VerificationError("injected verification failure")

    with monkeypatch.context() as patch:
        patch.setattr(dm, "verify_integrity", refuse)
        assert manager.backup_to(destination) is None
    assert destination.read_bytes() == b"previous export"
    assert not list(destination.parent.glob(".drillmaster-backup-*"))
    assert manager.backup_to(destination) == str(destination)
    with manager.session_scope() as session:
        assert session.execute(text("SELECT COUNT(*) FROM wells WHERE code='SYN-W1'")).scalar() == 1


# ---------------------------------------------------------------- release hardening (M43): shutdown and manifests

def test_shutdown_during_a_scheduled_backup_waits_for_it_and_starts_no_other(env):
    """The window's close sequence (service.shutdown, then scheduler.stop) mid-backup."""
    manager, backup_dir = env
    service = _service(manager, backup_dir, keep=5)
    inside, release = threading.Event(), threading.Event()

    def hold(stage):
        if stage == "verify" and not release.is_set():
            inside.set()
            release.wait(30)

    service.fault = hold
    outcomes = []
    scheduler = dm.BackupScheduler(service, 0.01, on_result=outcomes.append)
    assert scheduler.start()
    assert inside.wait(30), "no scheduled backup started"
    service.shutdown()
    assert scheduler.stop(timeout=0.01) is False  # the in-flight backup is not abandoned
    release.set()
    assert scheduler.stop(timeout=30)
    assert [r.ok for r in outcomes] == [True]  # it completed, verified, and nothing else ran
    assert len(service.list_backups(kinds=(dm.KIND_BACKUP,), deep=True)) == 1
    assert not [p.name for p in backup_dir.iterdir() if p.name.startswith(dm.PARTIAL_PREFIX)]
    assert service.create_backup(ADMIN).skipped  # refused after shutdown


@pytest.mark.parametrize("manifest_text", ["{not json", "[]", json.dumps({"format": "other"}), ""])
def test_a_corrupt_manifest_makes_a_backup_unverified_but_never_deleted(env, manifest_text):
    manager, backup_dir = env
    service = _service(manager, backup_dir, keep=1)
    first = Path(service.create_backup(ADMIN).path)
    first.with_suffix(".json").write_text(manifest_text, encoding="utf-8")
    assert service.read_manifest(first) is None
    assert service.list_backups() == []
    with pytest.raises(dm.VerificationError, match="manifest"):
        dm.RestoreService(manager, service).validate_candidate(first)
    assert all(service.create_backup(ADMIN).ok for _ in range(2))
    assert first.is_file()  # unverified files are never retention candidates
