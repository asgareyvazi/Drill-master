"""M45: user-confirmed document <-> well/report links (service and schema).

SYNTHETIC data only (tests/document_link_fixtures.py).  Every mutation must be
one transaction with referential checks and a mandatory audit record; a
refusal or failure leaves no link and no audit row.
"""
import json
import sqlite3

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from core.database import DocumentLink, OwnershipIntegrityError
from core.document_library import DocumentLibrary
from core.document_links import DocumentLinkError, DocumentLinkService
from core.permissions import permissions, session_user
from document_link_fixtures import build_link_world, import_documents, without_session_user, write_documents
from synthetic_operations import make_file_database
from test_scope_attribution import _mgr


def _rows(db, sql, **params):
    session = db.create_session()
    try:
        return session.execute(text(sql), params).fetchall()
    finally:
        session.close()


def _count_links(db):
    return _rows(db, "SELECT COUNT(*) FROM document_links")[0][0]


def _audits(db, action=None):
    sql = "SELECT action, entity_id, details FROM audit_logs WHERE action LIKE 'document_%link%'"
    if action:
        sql = "SELECT action, entity_id, details FROM audit_logs WHERE action = :action"
    return _rows(db, sql + " ORDER BY id", action=action)


@pytest.fixture
def world(tmp_path):
    with without_session_user():
        db = _mgr()
        ids = build_link_world(db)
        ids["docs"] = import_documents(db, write_documents(tmp_path / "docs"))
        yield db, ids, DocumentLinkService(db)
        db.engine.dispose()


# ------------------------------------------------------------ link + open
def test_link_to_well_is_listed_for_the_well_and_audited(world):
    db, ids, service = world
    link_id = service.create_link(ids["docs"]["alpha"], ids["alpha"], page_no=2)
    (link,) = service.links_for_well(ids["alpha"])
    assert (link["id"], link["document_id"], link["file_name"]) == (link_id, ids["docs"]["alpha"],
                                                                    "syn_alpha_daily.txt")
    assert (link["scope"], link["report_id"], link["page_no"], link["well_name"]) == ("well", None, 2, "SYN-ALPHA-01")
    assert service.links_for_well(ids["twin_1"]) == []
    (audit,) = _audits(db, "document_link")
    details = json.loads(audit[2])
    assert audit[1] == ids["docs"]["alpha"]
    assert (details["link_id"], details["well_id"], details["report_id"], details["page_no"]) == (
        link_id, ids["alpha"], None, 2)


def test_same_document_linked_to_a_report_is_listed_for_that_report(world):
    db, ids, service = world
    service.create_link(ids["docs"]["alpha"], ids["alpha"])
    report_link = service.create_link(ids["docs"]["alpha"], ids["alpha"], report_id=ids["report_1"])
    (link,) = service.links_for_report(ids["report_1"])
    assert (link["id"], link["scope"], link["report_number"]) == (report_link, "report", 1)
    assert service.links_for_report(ids["report_2"]) == []
    assert len(service.links_for_well(ids["alpha"])) == 2
    assert [link["scope"] for link in service.links_for_well(ids["alpha"], include_report_links=False)] == ["well"]
    assert {link["scope"] for link in service.links_for_document(ids["docs"]["alpha"])} == {"well", "report"}


# ------------------------------------------------------- refusals (no row)
@pytest.mark.parametrize("case, code", [
    ("missing_document", "document_missing"), ("missing_well", "well_missing"),
    ("missing_report", "report_missing"), ("report_of_other_well", "report_well_mismatch"),
    ("missing_page", "page_missing"),
])
def test_invalid_targets_are_refused_without_any_row_or_audit(world, case, code):
    db, ids, service = world
    doc, well = ids["docs"]["alpha"], ids["alpha"]
    kwargs = {
        "missing_document": dict(document_id=999_999, well_id=well),
        "missing_well": dict(document_id=doc, well_id=999_999),
        "missing_report": dict(document_id=doc, well_id=well, report_id=999_999),
        "report_of_other_well": dict(document_id=doc, well_id=well, report_id=ids["twin_report"]),
        "missing_page": dict(document_id=doc, well_id=well, page_no=99),
    }[case]
    with pytest.raises(DocumentLinkError) as error:
        service.create_link(**kwargs)
    assert error.value.code == code
    assert _count_links(db) == 0 and _audits(db) == []


def test_duplicate_links_are_refused_by_service_and_schema(world):
    db, ids, service = world
    doc = ids["docs"]["alpha"]
    service.create_link(doc, ids["alpha"])
    service.create_link(doc, ids["alpha"], report_id=ids["report_1"])
    for report_id in (None, ids["report_1"]):
        with pytest.raises(DocumentLinkError) as error:
            service.create_link(doc, ids["alpha"], report_id=report_id)
        assert error.value.code == "duplicate"
    assert _count_links(db) == 2 and len(_audits(db, "document_link")) == 2
    # The schema refuses it too (partial unique index for the NULL report).
    for report_id in (None, ids["report_1"]):
        session = db.create_session()
        try:
            session.add(DocumentLink(document_id=doc, well_id=ids["alpha"], report_id=report_id))
            with pytest.raises(IntegrityError):
                session.commit()
        finally:
            session.rollback()
            session.close()
    assert _count_links(db) == 2


def test_ownership_guard_rejects_a_report_of_another_well_at_the_orm_level(world):
    db, ids, _service = world
    session = db.create_session()
    try:
        session.add(DocumentLink(document_id=ids["docs"]["alpha"], well_id=ids["alpha"],
                                 report_id=ids["twin_report"]))
        with pytest.raises(OwnershipIntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()
    assert _count_links(db) == 0


def test_audit_failure_rolls_the_link_back(world, monkeypatch):
    db, ids, service = world

    def broken_audit(*_args, **_kwargs):
        raise sqlite3.OperationalError("SYNTHETIC audit failure")
    monkeypatch.setattr(db, "_add_mandatory_audit", broken_audit)
    with pytest.raises(DocumentLinkError) as error:
        service.create_link(ids["docs"]["alpha"], ids["alpha"])
    assert error.value.code == "audit_failed"
    assert _count_links(db) == 0 and _audits(db) == []


def test_audit_failure_rolls_a_change_and_a_removal_back(world, monkeypatch):
    db, ids, service = world
    link_id = service.create_link(ids["docs"]["alpha"], ids["alpha"])
    monkeypatch.setattr(db, "_add_mandatory_audit",
                        lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("SYNTHETIC")))
    with pytest.raises(DocumentLinkError) as change:
        service.update_link(link_id, ids["twin_1"])
    with pytest.raises(DocumentLinkError) as removal:
        service.remove_link(link_id)
    assert change.value.code == removal.value.code == "audit_failed"
    assert _rows(db, "SELECT well_id FROM document_links")[0][0] == ids["alpha"]


# ----------------------------------------------------- change and removal
def test_change_link_is_audited_with_before_and_after(world):
    db, ids, service = world
    doc = ids["docs"]["twin"]
    link_id = service.create_link(doc, ids["twin_1"])
    service.update_link(link_id, ids["twin_2"])
    (link,) = service.links_for_document(doc)
    assert (link["id"], link["well_id"]) == (link_id, ids["twin_2"])
    (audit,) = _audits(db, "document_link_change")
    details = json.loads(audit[2])
    assert details["from"]["well_id"] == ids["twin_1"] and details["to"]["well_id"] == ids["twin_2"]
    with pytest.raises(DocumentLinkError) as unchanged:
        service.update_link(link_id, ids["twin_2"])
    assert unchanged.value.code == "unchanged"
    other = service.create_link(doc, ids["twin_1"])
    with pytest.raises(DocumentLinkError) as duplicate:
        service.update_link(other, ids["twin_2"])         # would duplicate the first link
    assert duplicate.value.code == "duplicate"
    with pytest.raises(DocumentLinkError) as mismatch:
        service.update_link(other, ids["twin_1"], report_id=ids["report_1"])
    assert mismatch.value.code == "report_well_mismatch"
    assert {link["well_id"] for link in service.links_for_document(doc)} == {ids["twin_1"], ids["twin_2"]}


def test_remove_link_keeps_the_document_and_is_audited(world):
    db, ids, service = world
    link_id = service.create_link(ids["docs"]["alpha"], ids["alpha"])
    service.remove_link(link_id)
    assert _count_links(db) == 0
    assert DocumentLibrary(db).document(ids["docs"]["alpha"])["file_name"] == "syn_alpha_daily.txt"
    (audit,) = _audits(db, "document_unlink")
    assert json.loads(audit[2])["well_id"] == ids["alpha"]
    with pytest.raises(DocumentLinkError) as error:
        service.remove_link(link_id)
    assert error.value.code == "link_missing"
    with pytest.raises(DocumentLinkError) as error:
        service.update_link(link_id, ids["alpha"])
    assert error.value.code == "link_missing"


# ---------------------------------------------- pickers and unlinked list
def test_picker_disambiguates_same_name_wells(world):
    _db, ids, service = world
    twins = [w for w in service.well_choices() if w["name"] == "SYN-TWIN"]
    assert {w["id"] for w in twins} == {ids["twin_1"], ids["twin_2"]}
    assert all(w["ambiguous_name"] for w in twins)
    assert {(w["code"], w["project"], w["rig"]) for w in twins} == {
        ("SYN-T1", "SYNTHETIC PROJECT EAST", "SYN RIG 2"), ("SYN-T2", "SYNTHETIC PROJECT WEST", "SYN RIG 3")}
    (alpha,) = [w for w in service.well_choices() if w["id"] == ids["alpha"]]
    assert (alpha["ambiguous_name"], alpha["reports"], alpha["company"]) == (False, 2, "SYNTHETIC LINK CO")
    assert [w["id"] for w in service.well_choices("syn-t2")] == [ids["twin_2"]]
    assert [w["id"] for w in service.well_choices("PROJECT WEST twin")] == []      # substring, not a token search
    reports = service.report_choices(ids["alpha"])
    assert [(r["report_number"], r["section"]) for r in reports] == [(2, "SYN 12 1/4 in"), (1, "SYN 12 1/4 in")]


def test_unlinked_documents_are_listed_until_linked(world):
    _db, ids, service = world
    docs = ids["docs"]
    assert service.unlinked_document_ids() == sorted(docs.values())
    service.create_link(docs["alpha"], ids["alpha"])
    assert docs["alpha"] not in service.unlinked_document_ids()
    listed = {d["id"]: d["links"] for d in DocumentLibrary(_db).list_documents()}
    assert listed[docs["alpha"]] == 1 and listed[docs["unrelated"]] == 0


# ---------------------------------------------------------- suggestions
def test_suggestions_come_from_the_text_and_never_link(world):
    db, ids, service = world
    docs = ids["docs"]
    alpha = service.suggest_wells(docs["alpha"])
    assert [(s.well_id, s.matched, s.page_no, s.occurrences) for s in alpha] == [(ids["alpha"], "name", 1, 2)]
    twins = service.suggest_wells(docs["twin"])
    assert {s.well_id for s in twins} == {ids["twin_1"], ids["twin_2"]}          # ambiguous: both offered
    persian = service.suggest_wells(docs["arabic"])                              # "۷" in the name, "7" in text
    assert [s.well_id for s in persian] == [ids["persian"]]
    assert service.suggest_wells(docs["unrelated"]) == []
    assert _count_links(db) == 0 and _audits(db) == []


def test_suggestions_match_whole_tokens_only(world, tmp_path):
    db, ids, service = world
    path = tmp_path / "syn_near_miss.txt"
    path.write_text("SYNTHETIC SYN-ALPHA-012 and SYN-ALPHA are other wells; casing 12 at 7 m", encoding="utf-8")
    doc = import_documents(db, {"near": path})["near"]
    session = db.create_session()
    try:                                     # names that would match by accident are never suggested
        from core.database import Well
        session.add_all([Well(name="12", code="7", project_id=session.get(Well, ids["alpha"]).project_id),
                         Well(name="m", project_id=session.get(Well, ids["alpha"]).project_id)])
        session.commit()
    finally:
        session.close()
    assert service.suggest_wells(doc) == []


# --------------------------------------------------- deletion policy
def test_report_delete_removes_only_its_report_links(world):
    db, ids, service = world
    doc = ids["docs"]["alpha"]
    service.create_link(doc, ids["alpha"])
    service.create_link(doc, ids["alpha"], report_id=ids["report_1"])
    assert db.delete_daily_report(ids["report_1"]) is True
    assert [link["scope"] for link in service.links_for_document(doc)] == ["well"]
    assert DocumentLibrary(db).document(doc) is not None


def test_well_delete_removes_its_links_and_the_document_becomes_unlinked(world):
    db, ids, service = world
    doc = ids["docs"]["alpha"]
    service.create_link(doc, ids["alpha"])
    service.create_link(doc, ids["alpha"], report_id=ids["report_2"])
    service.create_link(ids["docs"]["twin"], ids["twin_1"])
    assert db.delete_hierarchy_entity("well", ids["alpha"]) is True
    assert service.links_for_document(doc) == []
    assert doc in service.unlinked_document_ids()
    assert DocumentLibrary(db).document(doc) is not None
    assert len(service.links_for_well(ids["twin_1"])) == 1                       # other wells untouched


def test_document_delete_removes_its_links_and_counts_them(world):
    db, ids, service = world
    doc = ids["docs"]["alpha"]
    service.create_link(doc, ids["alpha"])
    service.create_link(doc, ids["alpha"], report_id=ids["report_1"])
    assert DocumentLibrary(db).delete_document(doc) is True
    assert _count_links(db) == 0
    (audit,) = _rows(db, "SELECT details FROM audit_logs WHERE action='document_delete'")
    assert json.loads(audit[0])["links_removed"] == 2


# ------------------------------------------------------- permissions
def test_link_permission_is_enforced_at_the_data_layer(tmp_path):
    db = make_file_database(tmp_path / "links_auth.db")
    previous = permissions.user
    try:
        permissions.set_user(session_user(db.authenticate_user("engineer", "Synthetic-Eng-1!")))
        db.enforce_authorization(permissions)
        doc = import_documents(db, {"twin": write_documents(tmp_path / "d")["twin"]})["twin"]
        (well_id,) = _rows(db, "SELECT id FROM wells")[0]
        permissions.set_user(session_user(db.authenticate_user("viewer", "Synthetic-View-1!")))
        with pytest.raises(DocumentLinkError) as error:
            DocumentLinkService(db).create_link(doc, well_id)
        assert error.value.code == "denied" and _count_links(db) == 0
        permissions.set_user(session_user(db.authenticate_user("engineer", "Synthetic-Eng-1!")))
        DocumentLinkService(db).create_link(doc, well_id)
        assert _rows(db, "SELECT linked_by FROM document_links")[0][0] == "engineer"
        assert _rows(db, "SELECT username FROM audit_logs WHERE action='document_link'")[0][0] == "engineer"
    finally:
        permissions.set_user(previous)
        db.engine.dispose()


def test_report_delete_with_links_needs_only_the_report_delete_permission(tmp_path):
    """Links leave with an audited report delete even when the user may delete
    reports but not curate documents (explicit per-user permission)."""
    from datetime import date

    from core.database import DailyReport
    db = make_file_database(tmp_path / "links_delete.db")
    previous = permissions.user
    try:
        permissions.set_user(session_user(db.authenticate_user("engineer", "Synthetic-Eng-1!")))
        db.enforce_authorization(permissions)
        doc = import_documents(db, {"twin": write_documents(tmp_path / "d")["twin"]})["twin"]
        (well_id,) = _rows(db, "SELECT id FROM wells")[0]
        session = db.create_session()
        try:
            report = DailyReport(well_id=well_id, report_date=date(2026, 1, 2), report_number=1)
            session.add(report)
            session.commit()
            report_id = report.id
        finally:
            session.close()
        DocumentLinkService(db).create_link(doc, well_id, report_id=report_id)
        deleter = session_user(db.authenticate_user("viewer", "Synthetic-View-1!"))
        deleter["permissions"] = {"can_delete_reports": True}
        permissions.set_user(deleter)
        assert not permissions.can_import() and permissions.can_delete_reports()
        assert db.delete_daily_report(report_id) is True
        assert _count_links(db) == 0
        assert _rows(db, "SELECT COUNT(*) FROM documents")[0][0] == 1
    finally:
        permissions.set_user(previous)
        db.engine.dispose()


# ------------------------------------------- migration and compatibility
def test_existing_database_gains_the_link_table_without_losing_documents(tmp_path):
    path = tmp_path / "pre_m45.db"
    db = make_file_database(path)
    doc = import_documents(db, {"unrelated": write_documents(tmp_path / "d")["unrelated"]})["unrelated"]
    db.engine.dispose()
    raw = sqlite3.connect(str(path))                    # simulate an M44 database: no link table
    raw.execute("DROP TABLE document_links")
    raw.commit()
    assert raw.execute("SELECT version FROM schema_version").fetchone()[0] == 6
    raw.close()
    upgraded = make_file_database(path)
    try:
        names = {r[0] for r in _rows(upgraded, "SELECT name FROM sqlite_master")}
        assert {"document_links", "uq_document_links_well_level", "ix_document_links_report_id",
                "ix_document_links_well_id"} <= names
        assert _rows(upgraded, "SELECT version FROM schema_version")[0][0] == 6      # older builds still open it
        assert DocumentLibrary(upgraded).document(doc)["file_name"] == "syn_unrelated.txt"
        (well_id,) = _rows(upgraded, "SELECT id FROM wells")[0]
        DocumentLinkService(upgraded).create_link(doc, well_id)
        assert _count_links(upgraded) == 1
    finally:
        upgraded.engine.dispose()
