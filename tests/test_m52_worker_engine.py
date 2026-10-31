"""M52: worker read views share one per-file engine (compiled cache) but never a connection.

M47 gave every background read its own engine; M52 found that each new engine
recompiled every query and left the compilation objects as cyclic garbage for
the GUI-thread collector.  The worker view is now an Engine of its own
(``execution_options``) over one cached NullPool read-only engine per file.
These tests pin what must not change: not the GUI's engine, a separate
read-only connection per checkout, and a compiled cache reused across workers.
Synthetic temporary file database.
"""
from __future__ import annotations

import threading

import pytest
from sqlalchemy import text

from core import export_jobs
from synthetic_operations import make_file_database


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    manager = make_file_database(tmp_path_factory.mktemp("m52engine") / "synthetic-m52-engine.db")
    yield manager
    manager.engine.dispose()


def test_each_worker_view_is_its_own_engine_over_one_shared_compiled_cache(db):
    with export_jobs.worker_database(db) as first, export_jobs.worker_database(db) as second:
        assert first.engine is not db.engine and second.engine is not db.engine
        assert first.engine is not second.engine                     # M47 ownership wording still holds
        assert first.engine._compiled_cache is second.engine._compiled_cache
        assert first.engine.dialect is second.engine.dialect


def test_concurrent_views_use_different_read_only_connections(db):
    with export_jobs.worker_database(db) as first, export_jobs.worker_database(db) as second:
        with first.engine.connect() as a, second.engine.connect() as b:
            assert a.connection.dbapi_connection is not b.connection.dbapi_connection
            assert a.execute(text("SELECT 1")).scalar() == 1
            with pytest.raises(Exception, match="readonly|read-only|attempt to write"):
                b.execute(text("CREATE TABLE m52_should_not_exist (x INTEGER)"))


def test_a_second_worker_reuses_compiled_statements(db):
    from core.database import Well
    with export_jobs.worker_database(db) as first:
        session = first.create_session()
        try:
            session.query(Well.id).filter(Well.id > 0).all()
        finally:
            session.close()
        size = len(first.engine._compiled_cache)
    with export_jobs.worker_database(db) as second:
        session = second.create_session()
        try:
            session.query(Well.id).filter(Well.id > 0).all()
        finally:
            session.close()
        assert len(second.engine._compiled_cache) == size           # a cache hit, not a new compilation


def test_views_from_worker_threads_read_concurrently(db):
    results, errors = [], []

    def read():
        try:
            with export_jobs.worker_database(db) as view:
                with view.engine.connect() as connection:
                    results.append(connection.execute(text("SELECT count(*) FROM wells")).scalar())
        except Exception as exc:          # recorded and asserted below
            errors.append(exc)
    threads = [threading.Thread(target=read) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert not errors and len(results) == 6 and len(set(results)) == 1


def test_a_new_maintenance_gate_gets_a_new_base_engine(db):
    with export_jobs.worker_database(db) as before:
        cache_before = before.engine._compiled_cache
    original = getattr(db, "_maintenance_gate", None)
    try:
        from core.db_maintenance import MaintenanceGate
        db._maintenance_gate = MaintenanceGate()
        with export_jobs.worker_database(db) as after:
            assert after.engine._compiled_cache is not cache_before
    finally:
        db._maintenance_gate = original
