"""M47: file-backed connection isolation, writers and maintenance.

Every test uses a real ``DatabaseManager`` on a temporary SYNTHETIC SQLite
file - never ``:memory:``, which keeps one shared connection on purpose and is
no evidence of file-backed concurrency behaviour. Threads are coordinated
with Events/Barriers and always joined with a bound; no assertion depends on
timing. Persistent state is checked through an independent ``sqlite3``
connection, not through the session under test.

Before M47 every session of a manager aliased one DB-API connection
(``StaticPool``); the docstrings say what the old code did.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from core import db_maintenance as dm
from core import sqlite_connection
from core.database import Company, DatabaseManager, Project, Well
from core.export_jobs import worker_database

JOIN = 30  # seconds; a bound for joins, never an expected duration


class Principal:
    def __init__(self, *permissions, user_id=1, username="synthetic-admin"):
        self.permissions, self.user_id, self.username = set(permissions), user_id, username

    def has_permission(self, name):
        return name in self.permissions


ADMIN = Principal(dm.MAINTAIN_DATABASE)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    path = data / "synthetic-m47.db"
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(data),
                       "DRILLMASTER_DB_PATH": str(path), "DRILLMASTER_BACKUP_DIR": str(data / "backups"),
                       "DRILLMASTER_AI_IMPORT": "0"}.items():
        monkeypatch.setenv(key, value)
    for key in ("DRILLMASTER_ENVIRONMENT", sqlite_connection.BUSY_TIMEOUT_ENV, sqlite_connection.POOL_SIZE_ENV,
                sqlite_connection.POOL_TIMEOUT_ENV, dm.KEEP_ENV, dm.INTERVAL_ENV):
        monkeypatch.delenv(key, raising=False)
    managers = []

    def open_manager():
        manager = DatabaseManager()
        assert manager.initialize(), manager.last_diagnostic
        managers.append(manager)
        return manager

    yield path, open_manager
    # Leak check: every test must have returned every connection it took.
    leaks = {id(m): m.connection_diagnostics() for m in managers}
    for manager in managers:
        manager.close()
    for info in leaks.values():
        assert info["checkedout"] == 0, info
        assert info["gate"]["checked_out"] == 0 and info["gate"]["connecting"] == 0, info
        assert info["gate"]["closed"] is False, info


def _rows(path, sql="SELECT code FROM companies WHERE code LIKE 'SYN-M47-%' ORDER BY code"):
    """Committed state through a brand-new, independent connection."""
    connection = sqlite3.connect(str(path))
    try:
        return [row[0] for row in connection.execute(sql)]
    finally:
        connection.close()


def _integrity_ok(path):
    connection = sqlite3.connect(str(path))
    try:
        return connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    finally:
        connection.close()


def _raw(session):
    return session.connection().connection.dbapi_connection


def _thread(target, *args):
    errors = []

    def body():
        try:
            target(*args)
        except BaseException as exc:  # reported to the test thread
            errors.append(exc)

    thread = threading.Thread(target=body, daemon=True)
    thread.start()
    return thread, errors


def _join(thread, errors):
    thread.join(JOIN)
    assert not thread.is_alive(), "worker thread did not finish within the bound"
    if errors:
        raise errors[0]


# ---------------------------------------------------------------- session isolation

def test_file_manager_uses_a_bounded_queue_pool_with_documented_sizing(env, monkeypatch):
    _, open_manager = env
    manager = open_manager()
    assert type(manager.engine.pool).__name__ == "QueuePool"
    assert manager.engine.pool.size() == sqlite_connection.DEFAULT_POOL_SIZE
    assert manager.engine.pool.timeout() == sqlite_connection.DEFAULT_POOL_TIMEOUT_S
    monkeypatch.setenv(sqlite_connection.POOL_SIZE_ENV, "3")
    monkeypatch.setenv(sqlite_connection.POOL_TIMEOUT_ENV, "7")
    assert sqlite_connection.pool_settings() == {"pool_size": 3, "max_overflow": 3, "pool_timeout": 7}


@pytest.mark.parametrize("raw", ["0", "601", "-1", "abc", "1.5"])
def test_invalid_pool_settings_fall_back_to_defaults_with_a_warning(raw, caplog):
    environ = {sqlite_connection.POOL_SIZE_ENV: raw, sqlite_connection.POOL_TIMEOUT_ENV: raw}
    with caplog.at_level(logging.WARNING, logger="core.sqlite_connection"):
        settings = sqlite_connection.pool_settings(environ)
    assert settings == {"pool_size": sqlite_connection.DEFAULT_POOL_SIZE,
                        "max_overflow": sqlite_connection.DEFAULT_POOL_SIZE,
                        "pool_timeout": sqlite_connection.DEFAULT_POOL_TIMEOUT_S}
    assert sum("Ignoring invalid" in r.getMessage() for r in caplog.records) == 2


def test_concurrent_sessions_have_distinct_verified_connections(env):
    _, open_manager = env
    manager = open_manager()
    sessions = [manager.create_session() for _ in range(3)]
    try:
        raws = [_raw(s) for s in sessions]
        assert len({id(r) for r in raws}) == 3
        for raw in raws:
            settings = sqlite_connection.effective_settings(raw)
            assert settings["foreign_keys"] == 1 and settings["busy_timeout"] == 30_000
            assert str(settings["journal_mode"]).lower() == "wal" and settings["synchronous"] == 1
        assert manager.connection_diagnostics()["checkedout"] == 3
    finally:
        for session in sessions:
            session.close()
    assert manager.connection_diagnostics()["checkedout"] == 0


def test_closing_one_session_does_not_roll_back_another_sessions_pending_write(env):
    """Old code: B's close reset (rolled back) the shared connection, so A's
    flushed insert vanished and A's commit then stored nothing, without error."""
    path, open_manager = env
    manager = open_manager()
    a = manager.create_session()
    try:
        a.add(Company(name="SYNTHETIC A", code="SYN-M47-A"))
        a.flush()
        b = manager.create_session()
        assert b.execute(text("SELECT COUNT(*) FROM companies WHERE code = 'SYN-M47-A'")).scalar() == 0
        b.close()                                               # reset-on-return of B's own connection
        a.commit()
    finally:
        a.close()
    assert _rows(path) == ["SYN-M47-A"]


def test_rollback_in_one_session_does_not_touch_another(env):
    """Old code: B's rollback rolled back A's flushed insert as well."""
    path, open_manager = env
    manager = open_manager()
    a, b = manager.create_session(), manager.create_session()
    try:
        a.add(Company(name="SYNTHETIC KEEP", code="SYN-M47-KEEP"))
        a.flush()
        b.execute(text("SELECT 1"))
        b.rollback()
        a.commit()
    finally:
        a.close()
        b.close()
    assert _rows(path) == ["SYN-M47-KEEP"]


def test_a_failed_flush_in_one_session_does_not_affect_another(env, monkeypatch):
    """Old code: B's failed flush and rollback discarded A's pending insert.

    With A holding SQLite's single write lock, B's insert cannot even start:
    it waits ``busy_timeout`` and fails explicitly. After A committed, B's
    retry reaches the foreign-key check and fails on the constraint itself."""
    path, open_manager = env
    monkeypatch.setenv(sqlite_connection.BUSY_TIMEOUT_ENV, "200")
    manager = open_manager()
    a = manager.create_session()
    try:
        a.add(Company(name="SYNTHETIC SURVIVOR", code="SYN-M47-SURV"))
        a.flush()
        b = manager.create_session()
        try:
            b.add(Project(company_id=987654, name="SYNTHETIC ORPHAN", code="SYN-M47-ORPH"))
            with pytest.raises(OperationalError) as caught:
                b.flush()
            assert "locked" in str(caught.value.orig).lower()
            b.rollback()
        finally:
            b.close()
        a.commit()
    finally:
        a.close()
    assert _rows(path) == ["SYN-M47-SURV"]
    with pytest.raises(IntegrityError):
        with manager.session_scope() as session:
            session.add(Project(company_id=987654, name="SYNTHETIC ORPHAN", code="SYN-M47-ORPH"))
    assert _rows(path) == ["SYN-M47-SURV"]
    assert _rows(path, "SELECT code FROM projects WHERE code = 'SYN-M47-ORPH'") == []


def test_a_commit_in_one_session_never_commits_another_sessions_pending_write(env):
    """Old code: B's commit also committed A's flushed insert (silent
    transaction propagation), so A's later rollback could not undo it."""
    path, open_manager = env
    manager = open_manager()
    a = manager.create_session()
    try:
        a.add(Company(name="SYNTHETIC DISCARD", code="SYN-M47-DISC"))
        a.flush()
        a.rollback()                                            # A changes its mind first ...
        a.add(Company(name="SYNTHETIC PENDING", code="SYN-M47-PEND"))
        a.flush()
        done = threading.Event()

        def other_writer():                                     # ... B commits its own row meanwhile
            with manager.session_scope() as b:
                b.add(Company(name="SYNTHETIC OTHER", code="SYN-M47-OTHR"))
            done.set()

        thread, errors = _thread(other_writer)
        a.rollback()                                            # releases A's write lock; B proceeds
        _join(thread, errors)
        assert done.is_set()
    finally:
        a.close()
    assert _rows(path) == ["SYN-M47-OTHR"]


def test_a_connection_is_reused_only_after_it_was_returned(env, monkeypatch):
    path, open_manager = env
    monkeypatch.setenv(sqlite_connection.POOL_SIZE_ENV, "1")
    monkeypatch.setenv(sqlite_connection.POOL_TIMEOUT_ENV, "1")
    manager = open_manager()
    first, second = manager.create_session(), manager.create_session()   # size 1 + overflow 1
    try:
        first_raw, second_raw = _raw(first), _raw(second)
        third = manager.create_session()
        with pytest.raises(PoolTimeoutError):                    # explicit pool-exhaustion error
            third.connection()
        third.close()
        first.close()
        reused = manager.create_session()
        try:
            assert _raw(reused) is first_raw and _raw(reused) is not second_raw
        finally:
            reused.close()
    finally:
        second.close()


def test_connections_are_released_on_success_error_and_rollback_paths(env):
    path, open_manager = env
    manager = open_manager()
    with manager.session_scope() as session:
        session.add(Company(name="SYNTHETIC OK", code="SYN-M47-OK"))
    with pytest.raises(IntegrityError):
        with manager.session_scope() as session:
            session.add(Company(name="SYNTHETIC DUP", code="SYN-M47-OK"))
    with pytest.raises(RuntimeError):
        with manager.session_scope() as session:
            session.execute(text("SELECT 1"))
            raise RuntimeError("synthetic failure")
    session = manager.create_session()
    session.execute(text("SELECT 1"))
    manager.release_session(session)
    assert manager.connection_diagnostics()["checkedout"] == 0
    assert _rows(path) == ["SYN-M47-OK"]


def test_a_pooled_connection_that_lost_foreign_keys_is_never_reused(env):
    _, open_manager = env
    manager = open_manager()
    raw = manager.engine.raw_connection()
    leaked = raw.driver_connection
    leaked.execute("PRAGMA foreign_keys=OFF")                   # e.g. a migration that could not undo it
    raw.close()                                                 # back into the pool with FK off
    session = manager.create_session()
    try:
        current = _raw(session)
        assert current is not leaked
        assert current.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(IntegrityError):
            session.add(Project(company_id=987654, name="SYNTHETIC ORPHAN", code="SYN-M47-FK"))
            session.flush()
        session.rollback()
    finally:
        session.close()


# ---------------------------------------------------------------- H1 reproduction

def test_h1_reader_thread_on_the_manager_during_a_pending_write(env):
    """H1 at the pool level. Old code: the reader thread's session shared the
    UI session's connection; its close rolled the pending insert back and the
    UI commit then "succeeded" storing nothing."""
    path, open_manager = env
    manager = open_manager()
    seen = {}
    ui = manager.create_session()
    try:
        ui.add(Company(name="SYNTHETIC H1", code="SYN-M47-H1"))
        ui.flush()

        def reader():
            with manager.session_scope() as session:            # the manager itself, not worker_database
                seen["count"] = session.execute(
                    text("SELECT COUNT(*) FROM companies WHERE code = 'SYN-M47-H1'")).scalar()

        _join(*_thread(reader))
        ui.commit()
    finally:
        ui.close()
    assert seen["count"] == 0                                   # no dirty read
    assert _rows(path) == ["SYN-M47-H1"] and _integrity_ok(path)


def test_h1_real_hierarchy_worker_during_a_pending_write(env):
    """The real ``HierarchyWorker`` (QThread) while the UI thread has a write
    in flight. M46 already gave this worker its own read-only connection; with
    M47 every session is isolated as well, so this is a regression guard."""
    pytest.importorskip("PySide6.QtCore")
    from main_window import HierarchyWorker

    path, open_manager = env
    manager = open_manager()
    with manager.session_scope() as session:
        session.add(Company(name="SYNTHETIC H1 COMMITTED", code="SYN-M47-H1C"))
    ui = manager.create_session()
    try:
        ui.add(Company(name="SYNTHETIC H1 IN FLIGHT", code="SYN-M47-H1F"))
        ui.flush()
        worker = HierarchyWorker(manager)
        worker.start()
        assert worker.wait(JOIN * 1000), "hierarchy worker did not finish within the bound"
        ui.commit()
    finally:
        ui.close()
    assert worker.error is None
    codes = {company["code"] for company in worker.result}
    assert "SYN-M47-H1C" in codes and "SYN-M47-H1F" not in codes   # committed data only
    assert _rows(path) == ["SYN-M47-H1C", "SYN-M47-H1F"] and _integrity_ok(path)


def test_the_hierarchy_worker_connection_cannot_write(env, monkeypatch):
    """Qt offscreen. With M47 every session has its own connection, so the M46
    H1 test can no longer tell whether the worker reads through
    ``worker_database``. The property that still tells them apart is that the
    worker's connection is ``mode=ro``: a background read can never write.
    The probe tries a real ORM write through the worker's own manager view."""
    pytest.importorskip("PySide6.QtCore")
    from main_window import HierarchyWorker

    path, open_manager = env
    manager = open_manager()
    attempts = []
    real = DatabaseManager.get_full_hierarchy

    def probing(self):
        session = self.create_session()
        try:
            session.add(Company(name="SYNTHETIC READ-ONLY PROBE", code="SYN-M47-RO"))
            session.commit()
            attempts.append("written")
        except OperationalError as error:
            session.rollback()
            attempts.append("readonly" if "readonly" in str(error).lower() else "other")
        finally:
            session.close()
        return real(self)

    monkeypatch.setattr(DatabaseManager, "get_full_hierarchy", probing)
    worker = HierarchyWorker(manager)
    worker.start()
    assert worker.wait(JOIN * 1000), "hierarchy worker did not finish within the bound"
    assert worker.error is None and worker.result is not None
    assert attempts == ["readonly"]
    assert "SYN-M47-RO" not in _rows(path) and _integrity_ok(path)


def test_two_readers_proceed_during_an_active_writer_and_see_its_snapshot(env):
    path, open_manager = env
    manager = open_manager()
    writer = manager.create_session()
    barrier = threading.Barrier(3, timeout=JOIN)
    counts = []

    def reader():
        barrier.wait()                                          # both readers run while the writer holds its lock
        with manager.session_scope() as session:
            counts.append(session.execute(
                text("SELECT COUNT(*) FROM companies WHERE code = 'SYN-M47-W'")).scalar())

    try:
        writer.add(Company(name="SYNTHETIC WRITER", code="SYN-M47-W"))
        writer.flush()                                          # RESERVED lock held, not committed
        threads = [_thread(reader) for _ in range(2)]
        barrier.wait()
        for thread in threads:
            _join(*thread)
        assert counts == [0, 0]
        writer.commit()
    finally:
        writer.close()
    with manager.session_scope() as session:
        assert session.execute(text("SELECT COUNT(*) FROM companies WHERE code = 'SYN-M47-W'")).scalar() == 1


# ---------------------------------------------------------------- concurrent writers

def test_writers_across_managers_serialize_and_fail_explicitly_after_busy_timeout(env, monkeypatch):
    path, open_manager = env
    first = open_manager()
    monkeypatch.setenv(sqlite_connection.BUSY_TIMEOUT_ENV, "200")
    second = open_manager()                                     # a second instance on the same file
    holder = first.create_session()
    try:
        holder.add(Company(name="SYNTHETIC HOLDER", code="SYN-M47-HOLD"))
        holder.flush()                                          # holds SQLite's single write lock
        with pytest.raises(OperationalError) as caught:
            with second.session_scope() as session:
                session.add(Company(name="SYNTHETIC BLOCKED", code="SYN-M47-BLK"))
        assert "locked" in str(caught.value.orig).lower()
        assert _rows(path) == []                                # nothing partial from either side
        holder.commit()
    finally:
        holder.close()
    with second.session_scope() as session:                     # the lock is gone: a later attempt succeeds
        session.add(Company(name="SYNTHETIC LATER", code="SYN-M47-BLK"))
    with pytest.raises(IntegrityError):                         # constraints still apply across managers
        with second.session_scope() as session:
            session.add(Company(name="SYNTHETIC DUPLICATE", code="SYN-M47-HOLD"))
    assert _rows(path) == ["SYN-M47-BLK", "SYN-M47-HOLD"] and _integrity_ok(path)


def test_a_contended_save_reports_failure_and_never_a_false_success(env, monkeypatch):
    path, open_manager = env
    first = open_manager()
    monkeypatch.setenv(sqlite_connection.BUSY_TIMEOUT_ENV, "200")
    second = open_manager()
    with first.session_scope() as session:
        company = Company(name="SYNTHETIC SAVE CO", code="SYN-M47-SAVE")
        session.add(company)
        session.flush()
        project = Project(company_id=company.id, name="SYNTHETIC SAVE PR", code="SYN-M47-SAVE-PR")
        session.add(project)
        session.flush()
        project_id = project.id
    holder = first.create_session()
    try:
        holder.add(Company(name="SYNTHETIC LOCK", code="SYN-M47-LOCK"))
        holder.flush()
        assert second.save_well({"project_id": project_id, "name": "SYNTHETIC W", "code": "SYN-M47-W1"}) is False
        assert _rows(path, "SELECT code FROM wells WHERE code = 'SYN-M47-W1'") == []
        holder.commit()
    finally:
        holder.close()
    assert second.save_well({"project_id": project_id, "name": "SYNTHETIC W", "code": "SYN-M47-W1"}) is True
    assert _rows(path, "SELECT code FROM wells WHERE code = 'SYN-M47-W1'") == ["SYN-M47-W1"]


def test_concurrent_writer_threads_on_two_managers_lose_no_update(env):
    path, open_manager = env
    managers = [open_manager(), open_manager()]
    writers = 8
    barrier = threading.Barrier(writers, timeout=JOIN)

    def write(index):
        barrier.wait()
        with managers[index % 2].session_scope() as session:
            session.add(Company(name=f"SYNTHETIC T{index}", code=f"SYN-M47-T{index}"))

    threads = [_thread(write, i) for i in range(writers)]
    for thread in threads:
        _join(*thread)
    assert _rows(path) == sorted(f"SYN-M47-T{i}" for i in range(writers)) and _integrity_ok(path)


# ---------------------------------------------------------------- maintenance gate

class _SignallingCondition:
    """Wraps the gate's condition: ``closing`` is set once ``close`` waits for the drain."""

    def __init__(self, inner, closing):
        self._inner, self._closing = inner, closing

    def __enter__(self):
        return self._inner.__enter__()

    def __exit__(self, *exc):
        return self._inner.__exit__(*exc)

    def wait_for(self, predicate, timeout=None):
        self._closing.set()
        return self._inner.wait_for(predicate, timeout)

    def notify_all(self):
        self._inner.notify_all()


@pytest.fixture()
def restore_env(env):
    path, open_manager = env
    manager = open_manager()
    with manager.session_scope() as session:
        company = Company(name="SYNTHETIC SNAPSHOT", code="SYN-M47-SNAP")
        session.add(company)
        session.flush()
        project = Project(company_id=company.id, name="SYNTHETIC SNAP PR", code="SYN-M47-SNAP-PR")
        session.add(project)
        session.flush()
        session.add(Well(project_id=project.id, name="SYNTHETIC SNAP W", code="SYN-M47-SNAP-W"))
    backups = dm.BackupService(manager, path.parent / "backups")
    snapshot = backups.create_backup(ADMIN)
    assert snapshot.ok
    with manager.session_scope() as session:
        session.add(Company(name="SYNTHETIC LATER", code="SYN-M47-LATER"))
    restore = dm.RestoreService(manager, backups, drain_timeout=JOIN, lock_timeout=JOIN)
    return path, open_manager, manager, backups, restore, Path(snapshot.path)


def test_a_refused_checkout_never_lowers_the_drain_count(restore_env):
    """Old code: the checkin SQLAlchemy fires for a refused checkout lowered
    the count (1 -> 0) while A still held its connection, and on the shared
    StaticPool connection the refusal closed A's in-flight transaction."""
    path, _open, manager, *_ = restore_env
    gate = manager._maintenance_gate
    a = manager.create_session()
    try:
        a.add(Company(name="SYNTHETIC HELD", code="SYN-M47-HELD"))
        a.flush()
        assert gate.active == 1
        gate.closed = True                                      # what close() sets before it waits
        try:
            for _ in range(3):
                with pytest.raises(dm.MaintenanceActive):
                    with worker_database(manager) as view:
                        view.create_session().execute(text("SELECT 1"))
                refused = manager.create_session()
                with pytest.raises(dm.MaintenanceActive):
                    refused.execute(text("SELECT 1"))
                refused.close()
            assert gate.active == 1 and gate.snapshot()["refused"] == 6
        finally:
            gate.open()
        a.commit()                                              # A's transaction survived the refusals
    finally:
        a.close()
    assert gate.active == 0
    assert "SYN-M47-HELD" in _rows(path)


def test_restore_waits_for_an_active_reader_refuses_new_checkouts_then_completes(restore_env):
    path, _open, manager, _backups, restore, snapshot = restore_env
    gate = manager._maintenance_gate
    closing = threading.Event()
    gate._condition = _SignallingCondition(gate._condition, closing)
    reader = manager.create_session()
    reader.execute(text("SELECT COUNT(*) FROM companies")).scalar()   # holds a checkout
    outcome = {}

    def run_restore():
        outcome["result"] = restore.restore(snapshot, ADMIN, confirmed=True)

    thread, errors = _thread(run_restore)
    try:
        assert closing.wait(JOIN), "restore never started draining"
        late = manager.create_session()
        with pytest.raises(dm.MaintenanceActive):               # refused while draining
            late.execute(text("SELECT 1"))
        late.close()
        with pytest.raises(dm.MaintenanceActive):
            with worker_database(manager) as view:
                view.create_session().execute(text("SELECT 1"))
    finally:
        reader.close()                                          # the drain can now finish
    _join(thread, errors)
    result = outcome["result"]
    assert result.ok, result.error
    assert _rows(path) == ["SYN-M47-SNAP"] and _integrity_ok(path)


def test_restore_drain_timeout_aborts_and_keeps_the_pending_writer_valid(restore_env, monkeypatch):
    """The drain gives up after ``drain_timeout``; nothing is changed and the
    writer commits normally. The best-effort database audit of the failed
    restore needs the write lock this same thread still holds, so it waits
    ``busy_timeout`` (shortened here) and reports ``audit_recorded=False``;
    the sidecar journal keeps the durable record."""
    path, _open, manager, _backups, restore, snapshot = restore_env
    restore.drain_timeout = 0.2
    monkeypatch.setenv(sqlite_connection.BUSY_TIMEOUT_ENV, "200")   # the audit's own connection
    before = _rows(path)
    writer = manager.create_session()
    try:
        writer.add(Company(name="SYNTHETIC DURING", code="SYN-M47-DURING"))
        writer.flush()
        result = restore.restore(snapshot, ADMIN, confirmed=True)
        assert not result.ok and result.stage == "maintenance" and "did not finish" in result.error
        assert result.safety_copy is None and manager._maintenance_gate.closed is False
        assert result.audit_recorded is False
        assert restore.journal.read()[-1]["event"] == "restore_failed"
        writer.commit()                                         # the writer is unaffected
    finally:
        writer.close()
    assert _rows(path) == sorted(before + ["SYN-M47-DURING"]) and _integrity_ok(path)


def test_idle_pooled_connections_are_closed_before_the_file_is_replaced(restore_env):
    path, _open, manager, _backups, restore, snapshot = restore_env
    sessions = [manager.create_session() for _ in range(3)]
    idle = [_raw(s) for s in sessions]
    for session in sessions:
        session.close()
    assert manager.engine.pool.checkedin() >= 3                 # idle connections in the pool
    observed = {}

    def probe(stage):
        if stage == "replace":
            observed["checkedin"] = manager.engine.pool.checkedin()
            observed["checkedout"] = manager.engine.pool.checkedout()

    restore.fault = probe
    result = restore.restore(snapshot, ADMIN, confirmed=True)
    assert result.ok, result.error
    assert observed == {"checkedin": 0, "checkedout": 0}
    for raw in idle:
        with pytest.raises(sqlite3.ProgrammingError):           # closed, not just forgotten
            raw.execute("SELECT 1")


def test_no_new_connection_is_opened_during_maintenance(restore_env, monkeypatch):
    """A new DB-API connection would run the WAL switch on the live file; the
    pool's creator is refused before ``sqlite_connection.connect`` runs."""
    path, _open, manager, *_ = restore_env
    manager.engine.dispose()
    gate = manager._maintenance_gate
    opened = []
    real_connect = sqlite_connection.connect
    monkeypatch.setattr(sqlite_connection, "connect", lambda *a, **k: opened.append(a) or real_connect(*a, **k))
    gate.close(drain_timeout=1)
    try:
        with pytest.raises(dm.MaintenanceBusy):                 # a second maintenance is refused, not stacked
            gate.close(drain_timeout=1)
        assert gate.closed is True
        session = manager.create_session()
        with pytest.raises(dm.MaintenanceActive):
            session.execute(text("SELECT 1"))                   # refused in the pool's creator
        session.close()
        with pytest.raises(dm.MaintenanceActive):
            with worker_database(manager) as view:
                view.create_session().execute(text("SELECT 1"))
        assert opened == []                                     # no connection was opened at all
        assert manager.engine.pool.checkedout() == 0 and gate.snapshot()["connecting"] == 0
    finally:
        gate.open()
    with manager.session_scope() as session:
        assert session.execute(text("SELECT 1")).scalar() == 1


def test_a_held_worker_connection_blocks_the_restore_until_the_drain_times_out(restore_env):
    path, _open, manager, _backups, restore, snapshot = restore_env
    restore.drain_timeout = 0.2
    before = _rows(path)
    with worker_database(manager) as view:
        session = view.create_session()
        try:
            session.execute(text("SELECT COUNT(*) FROM companies")).scalar()
            result = restore.restore(snapshot, ADMIN, confirmed=True)
        finally:
            session.close()
    assert not result.ok and result.stage == "maintenance"
    assert _rows(path) == before


def test_an_untracked_connection_on_the_file_makes_restore_fail_safe(restore_env):
    """Another process or DatabaseManager the gate cannot see: the WAL exit
    needs exclusive access, so restore refuses and changes nothing."""
    path, open_manager, manager, _backups, restore, snapshot = restore_env
    other = open_manager()                                      # second instance on the same file
    with other.session_scope() as session:
        session.execute(text("SELECT 1"))                       # leaves an idle pooled connection open
    before = _rows(path)
    result = restore.restore(snapshot, ADMIN, confirmed=True)
    assert not result.ok and result.stage == "exclusive" and "another process" in result.error
    assert _rows(path) == before and _integrity_ok(path)
    for each in (manager, other):
        with each.session_scope() as session:
            assert session.execute(text("SELECT COUNT(*) FROM companies")).scalar() >= 1


def test_settings_are_reapplied_to_connections_after_a_restore(restore_env):
    path, _open, manager, _backups, restore, snapshot = restore_env
    result = restore.restore(snapshot, ADMIN, confirmed=True)
    assert result.ok, result.error
    sessions = [manager.create_session() for _ in range(2)]
    try:
        for session in sessions:
            settings = sqlite_connection.effective_settings(_raw(session))
            assert settings["foreign_keys"] == 1 and settings["busy_timeout"] == 30_000
            assert str(settings["journal_mode"]).lower() == "wal"
        assert _raw(sessions[0]) is not _raw(sessions[1])
    finally:
        for session in sessions:
            session.close()


def test_a_failed_restore_is_recovered_and_the_pool_is_usable(restore_env):
    path, _open, manager, _backups, restore, snapshot = restore_env
    before = _rows(path)

    def fail(stage):
        if stage == "reopen":
            raise OSError("synthetic reopen failure")

    restore.fault = fail
    result = restore.restore(snapshot, ADMIN, confirmed=True)
    assert not result.ok and result.recovered is True and result.original_intact
    assert _rows(path) == before and _integrity_ok(path)
    with manager.session_scope() as session:
        session.add(Company(name="SYNTHETIC AFTER", code="SYN-M47-AFTER"))
    assert "SYN-M47-AFTER" in _rows(path)


def test_the_gate_is_neither_reset_nor_reopened_by_reinitialize(env):
    path, open_manager = env
    manager = open_manager()
    gate = manager._maintenance_gate
    held = manager.create_session()
    held.execute(text("SELECT 1"))
    old_engine = manager.engine
    try:
        assert manager.initialize(), manager.last_diagnostic        # a new engine, the same gate
        assert manager._maintenance_gate is gate and gate.active == 1
        gate.on_checkin(None, object())                             # an unmatched checkin is ignored
        assert gate.active == 1
    finally:
        held.close()
    assert gate.active == 0
    gate.on_checkin(None, object())
    assert gate.active == 0                                         # never negative
    gate.close(drain_timeout=1)
    try:
        assert manager.initialize() is False                        # refused while closed: not reopened
        assert gate.closed is True
    finally:
        gate.open()
    assert manager.initialize(), manager.last_diagnostic
    old_engine.dispose()


def test_an_in_memory_database_is_never_read_from_a_worker_thread(monkeypatch, tmp_path):
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(tmp_path),
                       "DRILLMASTER_DB_PATH": ":memory:", "DRILLMASTER_AI_IMPORT": "0"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("DRILLMASTER_ENVIRONMENT", raising=False)
    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    try:
        with worker_database(manager) as view:                       # the calling (main) thread: allowed
            assert view is manager
        outcome = {}

        def worker():
            try:
                with worker_database(manager):
                    outcome["entered"] = True
            except RuntimeError as exc:
                outcome["refused"] = str(exc)

        _join(*_thread(worker))
        assert "entered" not in outcome and "worker thread" in outcome["refused"]
    finally:
        manager.close()


def _in_memory_manager(monkeypatch, tmp_path):
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(tmp_path),
                       "DRILLMASTER_DB_PATH": ":memory:", "DRILLMASTER_AI_IMPORT": "0"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("DRILLMASTER_ENVIRONMENT", raising=False)
    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    return manager


def test_the_hierarchy_of_an_in_memory_database_is_read_on_the_calling_thread(monkeypatch, tmp_path):
    """Qt offscreen. The shared in-memory connection must never be read by
    the hierarchy QThread; the read runs on the calling thread instead."""
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    from core.cache_manager import cache
    from main_window import HierarchyWorker, MainWindow

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    manager = _in_memory_manager(monkeypatch, tmp_path)
    monkeypatch.setattr(HierarchyWorker, "start", lambda self: pytest.fail("in-memory read moved to a thread"))
    cache.delete("main_window_hierarchy")
    window = MainWindow.__new__(MainWindow)
    QtWidgets.QMainWindow.__init__(window)
    window.db_manager = manager
    window.tree_widget = QtWidgets.QTreeWidget()
    window._hierarchy_worker = None
    window._hierarchy_generation = 0
    window._hierarchy_refresh_pending = False
    window._hierarchy_shutdown_requested = False
    window._close_confirmed = False
    rendered, threads = [], []
    real_get = manager.get_full_hierarchy
    monkeypatch.setattr(manager, "get_full_hierarchy", lambda: threads.append(threading.get_ident()) or real_get())
    window._build_tree_from_data = rendered.append
    window.show_loading = lambda _message: None
    window.hide_loading = lambda: None
    try:
        window.populate_hierarchy()
        assert threads == [threading.get_ident()]
        for _ in range(5):
            app.processEvents()
        assert len(rendered) == 1 and window._hierarchy_worker is None
    finally:
        cache.delete("main_window_hierarchy")
        window.deleteLater()
        manager.close()


def test_an_in_memory_export_runs_on_the_calling_thread(monkeypatch, tmp_path):
    """Qt offscreen. Export Center with an in-memory manager: no worker thread."""
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    import tabs.w11_Export as module
    from core import export_jobs
    from core.export_jobs import ExportJob

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    manager = _in_memory_manager(monkeypatch, tmp_path)
    monkeypatch.setattr(module.QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(module.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    threads, results, failures = [], [], []
    monkeypatch.setattr(export_jobs, "GENERATORS",
                        {"plan": lambda db, job: threads.append(threading.get_ident()) or True})
    widget = module.ExportWidget(db_manager=manager)
    try:
        job = ExportJob("plan", "Plan", str(tmp_path / "synthetic-plan.html"), 1)
        assert widget._start_export(lambda db: [job], results.append, on_failed=failures.append)
        assert threads == [threading.get_ident()] and failures == []
        assert [o.status for o in results[0].outcomes] == ["ok"] and not widget.export_running()
    finally:
        widget.deleteLater()
        manager.close()
