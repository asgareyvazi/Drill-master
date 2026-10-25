"""M46: atomicity, authorization and concurrency of document links.

Strengthens the M45 contract tests: a failed change/removal must leave the
WHOLE relevant state (links, audit trail, documents, pages) byte-identical,
including when the failure happens at commit after the audit row was added;
the data-layer policy refuses change and removal to a read-only principal;
two concurrent creates of the same link produce exactly one link and one
audit row.  SYNTHETIC data only.
"""
import sqlite3
import threading
from contextlib import contextmanager

import pytest

from core.document_links import DocumentLinkError, DocumentLinkService
from core.permissions import permissions, session_user
from document_link_fixtures import build_link_world, import_documents, without_session_user, write_documents
from synthetic_operations import make_file_database
from test_document_links import _rows, world  # noqa: F401  (fixture)

STATE_SQL = {
    "links": "SELECT id, document_id, well_id, report_id, page_no, note, linked_by FROM document_links ORDER BY id",
    "audits": "SELECT id, action, entity_type, entity_id, details FROM audit_logs ORDER BY id",
    "documents": "SELECT id, sha256, file_name, page_count FROM documents ORDER BY id",
    "pages": "SELECT id, document_id, page_no, text, review_status FROM document_pages ORDER BY id",
}


def _state(db):
    return {name: _rows(db, sql) for name, sql in STATE_SQL.items()}


def test_failed_change_and_removal_leave_every_row_identical(world, monkeypatch):  # noqa: F811
    db, ids, service = world
    link_id = service.create_link(ids["docs"]["alpha"], ids["alpha"], ids["report_1"], page_no=1)
    before = _state(db)
    assert [a[1] for a in before["audits"] if "link" in a[1]] == ["document_link"]
    monkeypatch.setattr(db, "_add_mandatory_audit",
                        lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("SYNTHETIC")))
    for attempt in (lambda: service.update_link(link_id, ids["alpha"], ids["report_2"], page_no=2),
                    lambda: service.update_link(link_id, ids["twin_1"]),
                    lambda: service.remove_link(link_id)):
        with pytest.raises(DocumentLinkError) as error:
            attempt()
        assert error.value.code == "audit_failed"
        assert _state(db) == before                       # no partial link change, no audit row


def test_a_commit_failure_after_the_audit_was_added_leaves_nothing(world, monkeypatch):  # noqa: F811
    db, ids, service = world
    before = _state(db)
    real_scope = db.session_scope
    seen = {}

    @contextmanager
    def failing_commit_scope():
        with real_scope() as session:
            def boom():
                seen["pending_audits"] = sum(1 for o in session.new if type(o).__name__ == "AuditLog")
                raise sqlite3.OperationalError("SYNTHETIC disk I/O error at commit")
            session.commit = boom
            yield session
    monkeypatch.setattr(db, "session_scope", failing_commit_scope)
    with pytest.raises(DocumentLinkError) as error:
        service.create_link(ids["docs"]["alpha"], ids["alpha"])
    assert error.value.code == "failed"
    monkeypatch.setattr(db, "session_scope", real_scope)
    assert _state(db) == before                           # the flushed link and its audit were rolled back


def test_read_only_principal_cannot_change_or_remove_a_link(tmp_path):
    db = make_file_database(tmp_path / "links_auth_m46.db")
    previous = permissions.user
    try:
        engineer = session_user(db.authenticate_user("engineer", "Synthetic-Eng-1!"))
        viewer = session_user(db.authenticate_user("viewer", "Synthetic-View-1!"))
        permissions.set_user(engineer)
        db.enforce_authorization(permissions)
        ids = build_link_world(db)
        doc = import_documents(db, {"twin": write_documents(tmp_path / "d")["twin"]})["twin"]
        service = DocumentLinkService(db)
        link_id = service.create_link(doc, ids["twin_1"])
        before = _state(db)
        permissions.set_user(viewer)
        for attempt in (lambda: service.update_link(link_id, ids["twin_2"]),
                        lambda: service.remove_link(link_id),
                        lambda: service.create_link(doc, ids["twin_2"])):
            with pytest.raises(DocumentLinkError) as error:
                attempt()
            assert error.value.code == "denied"
        after = _state(db)
        denials = [a for a in after["audits"] if a[1] == "authorization_denied"]
        assert len(denials) == 3 and all(a[2] == "document_links" for a in denials)   # every refusal is audited
        assert after["audits"][:len(before["audits"])] == before["audits"]
        assert len(after["audits"]) == len(before["audits"]) + 3                       # nothing else was written
        assert {k: v for k, v in after.items() if k != "audits"} == \
               {k: v for k, v in before.items() if k != "audits"}
    finally:
        permissions.set_user(previous)
        db.engine.dispose()


def test_a_report_of_another_well_is_refused_on_change_too(world):  # noqa: F811
    db, ids, service = world
    link_id = service.create_link(ids["docs"]["twin"], ids["twin_1"], ids["twin_report"])
    before = _state(db)
    with pytest.raises(DocumentLinkError) as error:
        service.update_link(link_id, ids["twin_2"], ids["twin_report"])     # report id of SYN-T1 under SYN-T2
    assert error.value.code == "report_well_mismatch"
    with pytest.raises(DocumentLinkError) as page:
        service.update_link(link_id, ids["twin_1"], ids["twin_report"], page_no=99)
    assert page.value.code == "page_missing"
    assert _state(db) == before


def test_two_application_instances_racing_on_one_link_store_one_link_and_one_audit(tmp_path):
    """Two DatabaseManager instances (as two running applications: separate
    connections, coordinated only by SQLite locking and the unique
    constraints) create the same link at the same moment.  Threads of ONE
    manager are not a supported writer model (one shared StaticPool
    connection, docs/DATABASE_OPERATIONS.md "Known limitations")."""
    from core.database import DatabaseManager
    path = tmp_path / "links_race_m46.db"
    with without_session_user():
        first = make_file_database(path)
        managers = [first]
        try:
            ids = build_link_world(first)
            doc = import_documents(first, {"alpha": write_documents(tmp_path / "d")["alpha"]})["alpha"]
            for _ in range(3):
                other = DatabaseManager()
                other.db_path = str(path)
                assert other.initialize(), other.last_diagnostic
                managers.append(other)
            barrier = threading.Barrier(len(managers))
            outcomes = []

            def create(manager):
                service = DocumentLinkService(manager)
                barrier.wait()
                try:
                    outcomes.append(service.create_link(doc, ids["alpha"], ids["report_1"]))
                except DocumentLinkError as exc:
                    outcomes.append(exc.code)
            threads = [threading.Thread(target=create, args=(m,)) for m in managers]
            for t in threads:
                t.start()
            for t in threads:
                t.join(60)
            assert sum(isinstance(o, int) for o in outcomes) == 1, outcomes
            assert sorted(o for o in outcomes if not isinstance(o, int)) == ["duplicate"] * 3, outcomes
            assert _rows(first, "SELECT COUNT(*) FROM document_links")[0][0] == 1
            assert _rows(first, "SELECT COUNT(*) FROM audit_logs WHERE action='document_link'")[0][0] == 1
        finally:
            for manager in managers:
                manager.engine.dispose()
