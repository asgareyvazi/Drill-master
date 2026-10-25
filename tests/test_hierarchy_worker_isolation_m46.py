"""M46: the hierarchy worker never shares the UI thread's connection.

All sessions of a ``DatabaseManager`` share one SQLite connection
(``StaticPool``, docs/DATABASE_OPERATIONS.md "Known limitations").  The
``HierarchyWorker`` thread read through it; returning that connection to the
pool rolls it back, so a write the UI thread had in flight was discarded and
its later commit stored nothing - without any error.  The worker now reads
through ``core.export_jobs.worker_database`` (own read-only connection, the
M43 facility already used by the Export Center and Home KPI workers).
SYNTHETIC data only.
"""
import sqlite3
import threading

import pytest
from sqlalchemy import text

pytest.importorskip("PySide6.QtCore")

from core.database import Company  # noqa: E402
from document_link_fixtures import without_session_user  # noqa: E402
from synthetic_operations import make_file_database  # noqa: E402


def _companies(path):
    con = sqlite3.connect(path)
    try:
        return [r[0] for r in con.execute("SELECT code FROM companies ORDER BY id")]
    finally:
        con.close()


def test_a_hierarchy_refresh_during_a_save_does_not_discard_the_save(tmp_path):
    from main_window import HierarchyWorker
    path = tmp_path / "hierarchy_m46.db"
    with without_session_user():
        db = make_file_database(path)
        baseline = _companies(path)                                           # default company of the fixture
        try:
            with db.session_scope() as session:                        # UI thread: save in progress
                session.add(Company(name="SYNTHETIC COMMITTED CO", code="SYN-HC0"))
            with db.session_scope() as session:
                session.add(Company(name="SYNTHETIC IN-FLIGHT CO", code="SYN-HC1"))
                session.flush()
                worker = HierarchyWorker(db)
                reader = threading.Thread(target=worker.run)              # the worker's thread body
                reader.start()
                reader.join(60)
                assert not reader.is_alive()
                codes = [r[0] for r in session.execute(text("SELECT code FROM companies ORDER BY id"))]
                assert codes == baseline + ["SYN-HC0", "SYN-HC1"]               # v1: the in-flight row was rolled back
            assert worker.error is None
            assert [c["code"] for c in worker.result] == baseline + ["SYN-HC0"]   # committed data only (v1: dirty read)
        finally:
            db.engine.dispose()
    assert _companies(path) == baseline + ["SYN-HC0", "SYN-HC1"]            # v1: SYN-HC1 lost, no error raised
