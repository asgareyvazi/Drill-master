"""SQLite connection configuration, transactions and contention (M43).

Temporary databases only. Threads are always joined with a bound, and no
assertion depends on how long an operation took.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from core import sqlite_connection
from core.database import DatabaseManager, Section, Well


@pytest.fixture()
def env(tmp_path, monkeypatch):
    path = tmp_path / "reliability.db"
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(tmp_path),
                       "DRILLMASTER_DB_PATH": str(path), "DRILLMASTER_AI_IMPORT": "0"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("DRILLMASTER_ENVIRONMENT", raising=False)
    monkeypatch.delenv(sqlite_connection.BUSY_TIMEOUT_ENV, raising=False)
    managers = []

    def open_manager():
        manager = DatabaseManager()
        assert manager.initialize(), manager.last_diagnostic
        managers.append(manager)
        return manager

    yield path, open_manager
    for manager in managers:
        manager.close()


def _settings(manager):
    raw = manager.engine.raw_connection()
    try:
        return sqlite_connection.effective_settings(raw.driver_connection)
    finally:
        raw.close()


# ---------------------------------------------------------------- configuration

def test_every_independent_connection_enforces_foreign_keys(env):
    path, open_manager = env
    first, second = open_manager(), open_manager()
    direct = sqlite_connection.connect(path)
    try:
        for manager in (first, second):
            assert _settings(manager)["foreign_keys"] == 1
            with pytest.raises(IntegrityError):
                with manager.session_scope() as session:
                    session.add(Section(well_id=987654, name="orphan"))
        assert sqlite_connection.effective_settings(direct)["foreign_keys"] == 1
        with pytest.raises(sqlite3.IntegrityError):
            direct.execute("INSERT INTO sections(well_id, name) VALUES (987654, 'orphan')")
    finally:
        direct.close()
    with sqlite3.connect(path) as check:
        assert check.execute("SELECT COUNT(*) FROM sections WHERE name='orphan'").fetchone() == (0,)


def test_busy_timeout_default_override_and_invalid_values(env, monkeypatch):
    path, open_manager = env
    assert _settings(open_manager())["busy_timeout"] == 30_000
    monkeypatch.setenv(sqlite_connection.BUSY_TIMEOUT_ENV, "1500")
    assert _settings(open_manager())["busy_timeout"] == 1500
    direct = sqlite_connection.connect(path)
    try:
        assert sqlite_connection.effective_settings(direct)["busy_timeout"] == 1500
    finally:
        direct.close()
    for bad in ("0", "-5", "abc", "99999999", "1.5"):
        assert sqlite_connection.busy_timeout_ms({sqlite_connection.BUSY_TIMEOUT_ENV: bad}) == 30_000


def test_journal_mode_is_wal_and_a_legacy_rollback_journal_database_is_converted(env, tmp_path):
    path, open_manager = env
    legacy = tmp_path / "legacy-delete-mode.db"
    with sqlite3.connect(legacy) as connection:
        assert connection.execute("PRAGMA journal_mode=DELETE").fetchone() == ("delete",)
        connection.execute("CREATE TABLE t (x)")
    converted = sqlite_connection.connect(legacy)
    try:
        assert sqlite_connection.effective_settings(converted)["journal_mode"] == "wal"
    finally:
        converted.close()
    manager = open_manager()
    settings = _settings(manager)
    assert settings["journal_mode"] == "wal" and settings["synchronous"] == 1  # NORMAL


def test_read_only_connections_never_change_the_journal_mode(tmp_path):
    path = tmp_path / "ro.db"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("CREATE TABLE t (x)")
    reader = sqlite_connection.connect(path, read_only=True)
    try:
        assert reader.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert sqlite_connection.effective_settings(reader)["foreign_keys"] == 1
        with pytest.raises(sqlite3.OperationalError):
            reader.execute("INSERT INTO t VALUES (1)")
    finally:
        reader.close()
    with pytest.raises(sqlite3.OperationalError):
        sqlite_connection.connect(tmp_path / "missing.db", read_only=True)
    assert not (tmp_path / "missing.db").exists()


def test_a_connection_without_foreign_key_support_is_refused():
    class NoForeignKeys:
        def __init__(self):
            self.inner = sqlite3.connect(":memory:")

        def cursor(self):
            outer = self

            class Cursor:
                def execute(self, sql):
                    if sql.strip().upper() == "PRAGMA FOREIGN_KEYS":
                        return outer.inner.execute("SELECT 0")
                    if sql.strip().upper().startswith("PRAGMA FOREIGN_KEYS="):
                        return outer.inner.execute("SELECT 0")
                    return outer.inner.execute(sql)

                def close(self):
                    pass

            return Cursor()

        def execute(self, sql):
            return self.inner.execute(sql)

    with pytest.raises(sqlite_connection.ConnectionConfigurationError):
        sqlite_connection.configure(NoForeignKeys())


def test_settings_are_reapplied_after_reconnection_and_shared_by_sessions(env):
    _, open_manager = env
    manager = open_manager()
    first = manager.create_session()
    second = manager.create_session()
    try:
        # StaticPool: every session of one manager uses the same DB-API connection.
        assert first.connection().connection.dbapi_connection is second.connection().connection.dbapi_connection
    finally:
        first.close()
        second.close()
    manager.engine.dispose()  # forces a brand-new DB-API connection on next use
    assert _settings(manager)["foreign_keys"] == 1
    assert _settings(manager)["busy_timeout"] == 30_000
    with manager.session_scope() as session:
        assert session.execute(text("SELECT COUNT(*) FROM wells")).scalar() >= 0


# ---------------------------------------------------------------- transactions

def test_exception_rolls_back_and_leaves_the_connection_clean(env):
    _, open_manager = env
    manager = open_manager()
    before = None
    with manager.session_scope() as session:
        before = session.query(Well).count()
    with pytest.raises(RuntimeError):
        with manager.session_scope() as session:
            project_id = session.execute(text("SELECT id FROM projects LIMIT 1")).scalar()
            session.add(Well(project_id=project_id, name="ROLLBACK-1", code="RB1"))
            session.flush()
            raise RuntimeError("simulated failure after a flushed insert")
    raw = manager.engine.raw_connection()
    try:
        assert raw.driver_connection.in_transaction is False
    finally:
        raw.close()
    with manager.session_scope() as session:
        assert session.query(Well).count() == before
        assert session.query(Well).filter_by(code="RB1").count() == 0


def test_integrity_failure_does_not_poison_later_work(env):
    _, open_manager = env
    manager = open_manager()
    with pytest.raises(IntegrityError):
        with manager.session_scope() as session:
            session.add(Section(well_id=123456, name="bad"))
    with manager.session_scope() as session:
        project_id = session.execute(text("SELECT id FROM projects LIMIT 1")).scalar()
        session.add(Well(project_id=project_id, name="AFTER-FAILURE", code="AF1"))
    with manager.session_scope() as session:
        assert session.query(Well).filter_by(code="AF1").count() == 1


# ---------------------------------------------------------------- contention

def test_readers_proceed_while_another_connection_holds_the_write_lock(env):
    path, open_manager = env
    manager = open_manager()
    writer = sqlite_connection.connect(path)
    try:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO companies(name, code) VALUES ('Uncommitted Co', 'UNC')")
        with manager.session_scope() as session:  # WAL: the reader sees the last committed state
            assert session.execute(text("SELECT COUNT(*) FROM companies WHERE code='UNC'")).scalar() == 0
        writer.commit()
        with manager.session_scope() as session:
            assert session.execute(text("SELECT COUNT(*) FROM companies WHERE code='UNC'")).scalar() == 1
    finally:
        writer.close()


def test_a_second_writer_fails_with_database_locked_after_its_busy_timeout(env, monkeypatch):
    path, open_manager = env
    monkeypatch.setenv(sqlite_connection.BUSY_TIMEOUT_ENV, "200")
    manager = open_manager()
    holder = sqlite_connection.connect(path)
    try:
        holder.execute("BEGIN IMMEDIATE")
        with pytest.raises(OperationalError, match="locked"):
            with manager.session_scope() as session:
                session.execute(text("INSERT INTO companies(name, code) VALUES ('Blocked', 'BLK')"))
    finally:
        holder.rollback()
        holder.close()
    with manager.session_scope() as session:  # usable again once the lock is gone
        session.execute(text("INSERT INTO companies(name, code) VALUES ('After lock', 'AFL')"))
    with sqlite3.connect(path) as check:
        assert check.execute("SELECT code FROM companies WHERE code IN ('BLK','AFL')").fetchall() == [("AFL",)]


def test_a_writer_waits_for_a_temporary_lock_and_then_succeeds(env):
    path, open_manager = env
    manager = open_manager()  # default 30 s busy timeout
    holder = sqlite_connection.connect(path)
    holder.execute("BEGIN IMMEDIATE")
    locked, release = threading.Event(), threading.Event()
    outcome = {}

    def write():
        locked.set()
        try:
            with manager.session_scope() as session:
                session.execute(text("INSERT INTO companies(name, code) VALUES ('Waited', 'WTD')"))
            outcome["ok"] = True
        except Exception as exc:  # reported below
            outcome["error"] = exc

    worker = threading.Thread(target=write, daemon=True)
    worker.start()
    try:
        assert locked.wait(10)
        release.wait(0.3)  # keep the lock briefly so the writer has to wait
        holder.commit()
    finally:
        holder.close()
        worker.join(30)
    assert not worker.is_alive()
    assert outcome == {"ok": True}
    with sqlite3.connect(path) as check:
        assert check.execute("SELECT COUNT(*) FROM companies WHERE code='WTD'").fetchone() == (1,)


def test_two_managers_write_concurrently_without_lost_updates(env):
    path, open_manager = env
    managers = [open_manager(), open_manager()]
    errors = []

    def writer(manager, prefix):
        try:
            for i in range(25):
                with manager.session_scope() as session:
                    session.execute(text("INSERT INTO companies(name, code) VALUES (:n, :c)"),
                                    {"n": f"{prefix}-{i}", "c": f"{prefix}{i}"})
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(m, p), daemon=True) for m, p in zip(managers, ("A", "B"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not any(t.is_alive() for t in threads)
    assert errors == []
    with sqlite3.connect(path) as check:
        assert check.execute("SELECT COUNT(*) FROM companies WHERE code GLOB '[AB][0-9]*'").fetchone() == (50,)


# ---------------------------------------------------------------- resources

@pytest.mark.skipif(not Path("/proc/self/fd").is_dir(), reason="needs /proc to count descriptors")
def test_repeated_open_close_cycles_do_not_leak_file_handles(env):
    path, _ = env

    def handles():
        names = []
        for fd in os.listdir("/proc/self/fd"):
            try:
                names.append(os.readlink(f"/proc/self/fd/{fd}"))
            except OSError:
                pass
        return sum(1 for name in names if name.startswith(str(path)))

    warm = DatabaseManager()
    assert warm.initialize()
    warm.close()
    baseline = handles()
    for _ in range(20):
        manager = DatabaseManager()
        assert manager.initialize(), manager.last_diagnostic
        with manager.session_scope() as session:
            session.execute(text("SELECT COUNT(*) FROM users")).scalar()
        manager.close()
    assert handles() == baseline == 0
