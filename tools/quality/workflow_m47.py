#!/usr/bin/env python3
"""M47 end-to-end workflows through the real services, SYNTHETIC data only.

Persistence (H1): a pending UI write while the real ``HierarchyWorker``
(QThread) reads, then commit; an independent ``sqlite3`` connection sees the
row and ``PRAGMA integrity_check`` is ok; a second ``DatabaseManager`` on the
same file is refused explicitly while the first one writes, stores nothing,
and succeeds afterwards.

Documents: import, Persian search, identifier search and its highlight (the
identifier only, never ``SYN`` inside ``SYNTHETIC``, never ``SYN-DEV-012``),
explicit link with a whitespace-only note (stored as NULL), a note-only change
whose mandatory audit fails (nothing changes), then the same change audited.

Maintenance: a restore while a reader holds a connection aborts after the
drain bound and leaves a valid database; after the reader is closed the
restore succeeds, the new connections carry the verified settings and the
snapshot is live.

Real authenticated users on a temporary file database; no fabricated
principal.  Qt runs offscreen (``QT_QPA_PLATFORM=offscreen``); this is NOT a
native Windows desktop run.

Usage::

    QT_QPA_PLATFORM=offscreen python tools/quality/workflow_m47.py [--json OUT]

Exit status 0 only when every step passes.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUSY_MS = 500   # short lock wait so the contention step fails fast (validated range 100..600000)
BOUND_S = 30    # upper bound for waits; never an expected duration
PERSIAN = "\u06af\u0632\u0627\u0631\u0634 \u0644\u0648\u0644\u0647 \u062c\u062f\u0627\u0631\u06cc"


def _codes(path) -> list:
    connection = sqlite3.connect(str(path))
    try:
        return [r[0] for r in connection.execute(
            "SELECT code FROM companies WHERE code LIKE 'SYN-M47-E2E%' ORDER BY code")]
    finally:
        connection.close()


def _raw(path, sql, *params):
    connection = sqlite3.connect(str(path))
    try:
        return connection.execute(sql, params).fetchall()
    finally:
        connection.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    work = Path(tempfile.mkdtemp(prefix="drillmaster-m47-workflow-"))
    db_path = work / "synthetic.db"
    os.environ.update({"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_DB_PATH": str(db_path), "DRILLMASTER_LOG_DIR": str(work / "logs"),
                       "DRILLMASTER_BACKUP_DIR": str(work / "backups"), "DRILLMASTER_AI_IMPORT": "0",
                       "DRILLMASTER_DB_BUSY_TIMEOUT_MS": str(BUSY_MS)})
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
    from PySide6.QtWidgets import QApplication
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    from core import db_maintenance as dm
    from core import search_normalization as sn
    from core import sqlite_connection
    from core.database import Company, DatabaseManager
    from core.document_library import DocumentLibrary, extract_document
    from core.document_links import DocumentLinkError, DocumentLinkService
    from core.permissions import permissions, session_user
    from document_link_fixtures import build_link_world
    from main_window import HierarchyWorker
    from synthetic_operations import make_file_database

    app = QApplication.instance() or QApplication([])
    steps = []

    def step(flow, name, ok, detail=""):
        steps.append({"flow": flow, "step": len([s for s in steps if s["flow"] == flow]) + 1, "name": name,
                      "status": "PASS" if ok else "FAIL", "detail": detail})
        print(f"{flow:11s} {steps[-1]['step']:2d} {'PASS' if ok else 'FAIL'}  {name}  {detail}")

    def integrity_ok():
        return _raw(db_path, "PRAGMA integrity_check") == [("ok",)]

    db = make_file_database(db_path)
    admin = session_user(db.authenticate_user("admin", "Synthetic-Admin-1!"))
    engineer = session_user(db.authenticate_user("engineer", "Synthetic-Eng-1!"))
    permissions.set_user(engineer)
    db.enforce_authorization(permissions)
    started = time.time()

    # ------------------------------------------------------------- persistence (H1)
    with db.session_scope() as session:
        session.add(Company(name="SYNTHETIC E2E COMMITTED", code="SYN-M47-E2E-A"))
    ui = db.create_session()
    try:
        ui.add(Company(name="SYNTHETIC E2E PENDING", code="SYN-M47-E2E-B"))
        ui.flush()
        worker = HierarchyWorker(db)
        worker.start()
        finished = worker.wait(BOUND_S * 1000)
        seen = {c["code"] for c in (worker.result or [])}
        step("persistence", "real HierarchyWorker during a pending UI write: committed rows only (no dirty read)",
             finished and worker.error is None and "SYN-M47-E2E-A" in seen and "SYN-M47-E2E-B" not in seen,
             f"worker finished={finished}")
        ui.commit()
    finally:
        ui.close()
    step("persistence", "after commit: an independent sqlite3 connection sees the row; integrity ok",
         _codes(db_path) == ["SYN-M47-E2E-A", "SYN-M47-E2E-B"] and integrity_ok())

    other = DatabaseManager()
    other.db_path = str(db_path)
    assert other.initialize(), other.last_diagnostic
    holder = db.create_session()
    refused = False
    try:
        holder.add(Company(name="SYNTHETIC E2E HOLDER", code="SYN-M47-E2E-C"))
        holder.flush()
        try:
            with other.session_scope() as session:
                session.add(Company(name="SYNTHETIC E2E SECOND", code="SYN-M47-E2E-D"))
        except OperationalError as error:
            refused = "locked" in str(error)
        absent = "SYN-M47-E2E-D" not in _codes(db_path)
        holder.commit()
    finally:
        holder.close()
    with other.session_scope() as session:
        session.add(Company(name="SYNTHETIC E2E SECOND", code="SYN-M47-E2E-D"))
    step("persistence", "second manager while the first writes: explicit 'locked', nothing stored, later retry stored",
         refused and absent and _codes(db_path)[-2:] == ["SYN-M47-E2E-C", "SYN-M47-E2E-D"] and integrity_ok(),
         f"busy_timeout={BUSY_MS} ms")
    other.close()

    # ------------------------------------------------------------- documents
    ids = build_link_world(db)
    folder = work / "docs"
    folder.mkdir()
    (folder / "syn_m47_fa.txt").write_text(f"SYNTHETIC {PERSIAN} SYN-DEV-01 casing", encoding="utf-8")
    (folder / "syn_m47_other.txt").write_text("SYNTHETIC other well SYN-DEV-012 casing", encoding="utf-8")
    library = DocumentLibrary(db)
    doc_fa = library.import_reviewed(extract_document(folder / "syn_m47_fa.txt"))
    doc_other = library.import_reviewed(extract_document(folder / "syn_m47_other.txt"))
    step("documents", "import: two synthetic text documents",
         doc_fa.status == "imported" and doc_other.status == "imported")
    persian = library.search(PERSIAN)
    step("documents", "Persian search finds the Persian document",
         [h["document_id"] for h in persian["hits"]] == [doc_fa.document_id], persian["method"].split(" (")[0])
    by_id = library.search("SYN-DEV-01")
    original = _raw(db_path, "SELECT text FROM document_pages WHERE document_id=?", doc_fa.document_id)[0][0]
    highlighted = [original[s:e] for s, e in sn.find_spans(original, by_id["groups"])]
    step("documents", "identifier search: SYN-DEV-01 only (not SYN-DEV-012); highlight = the identifier only",
         [h["document_id"] for h in by_id["hits"]] == [doc_fa.document_id] and highlighted == ["SYN-DEV-01"],
         f"highlighted={highlighted}")
    service = DocumentLinkService(db)
    link_id = service.create_link(doc_fa.document_id, ids["alpha"], note=" \t\u3000\r\n ")
    raw_note = _raw(db_path, "SELECT note FROM document_links WHERE id=?", link_id)
    step("documents", "explicit link with a whitespace-only note: stored as NULL", raw_note == [(None,)])

    audits_before = _raw(db_path, "SELECT COUNT(*) FROM audit_logs")
    real_audit = db._add_mandatory_audit

    def failing_audit(*_a, **_k):
        raise sqlite3.OperationalError("SYNTHETIC forced audit failure")

    db._add_mandatory_audit = failing_audit
    try:
        try:
            service.update_link(link_id, ids["alpha"], note="SYNTHETIC note")
            code = None
        except DocumentLinkError as error:
            code = error.code
    finally:
        db._add_mandatory_audit = real_audit
    step("documents", "note-only change with a failing mandatory audit: refused, note and audit unchanged",
         code == "audit_failed" and _raw(db_path, "SELECT note FROM document_links WHERE id=?", link_id) == [(None,)]
         and _raw(db_path, "SELECT COUNT(*) FROM audit_logs") == audits_before, f"code={code}")
    service.update_link(link_id, ids["alpha"], note="  SYNTHETIC note\t")
    change = _raw(db_path, "SELECT details FROM audit_logs WHERE action='document_link_change' "
                           "ORDER BY id DESC LIMIT 1")
    details = json.loads(change[0][0]) if change else {}
    step("documents", "note-only change audited: stored trimmed, audit holds lengths only (no note text)",
         _raw(db_path, "SELECT note FROM document_links WHERE id=?", link_id) == [("SYNTHETIC note",)]
         and details.get("from", {}).get("note_chars") == 0 and details.get("to", {}).get("note_chars") == 14
         and "SYNTHETIC note" not in change[0][0])
    library.close()

    # ------------------------------------------------------------- maintenance
    permissions.set_user(admin)            # as in the app: the service resolves the logged-in principal
    backups = dm.BackupService(db, work / "backups")
    snapshot = backups.create_backup()
    with db.session_scope() as session:
        session.add(Company(name="SYNTHETIC E2E AFTER BACKUP", code="SYN-M47-E2E-Z"))
    reader = db.create_session()
    reader.execute(text("SELECT COUNT(*) FROM companies")).scalar()     # holds a pooled connection
    try:
        blocked = dm.RestoreService(db, backups, drain_timeout=0.5, lock_timeout=BOUND_S).restore(
            Path(snapshot.path), confirmed=True)
    finally:
        reader.close()
    gate = db._maintenance_gate.snapshot()
    step("maintenance", "restore while a reader holds a connection: aborted after the drain bound, DB valid",
         snapshot.ok and not blocked.ok and blocked.original_intact and "SYN-M47-E2E-Z" in _codes(db_path)
         and integrity_ok() and not gate["closed"], f"stage={blocked.stage}")
    restored = dm.RestoreService(db, backups, drain_timeout=BOUND_S, lock_timeout=BOUND_S).restore(
        Path(snapshot.path), confirmed=True)
    with db.engine.connect() as connection:
        settings = sqlite_connection.effective_settings(connection.connection.dbapi_connection)
    step("maintenance", "restore after the reader closed: snapshot live, settings re-applied, integrity ok",
         restored.ok and "SYN-M47-E2E-Z" not in _codes(db_path) and "SYN-M47-E2E-D" in _codes(db_path)
         and settings["foreign_keys"] == 1 and str(settings["journal_mode"]).lower() == "wal"
         and settings["busy_timeout"] == BUSY_MS and integrity_ok(),
         f"journal_mode={settings['journal_mode']}")
    diagnostics = db.connection_diagnostics()
    step("maintenance", "no connection left checked out; gate open and empty",
         diagnostics.get("checkedout") == 0 and diagnostics["gate"]["checked_out"] == 0
         and diagnostics["gate"]["connecting"] == 0 and not diagnostics["gate"]["closed"])

    db.close()
    app.processEvents()
    failed = [s for s in steps if s["status"] != "PASS"]
    print(f"\nsteps={len(steps)} passed={len(steps) - len(failed)} failed={len(failed)} "
          f"seconds={time.time() - started:.1f}")
    if args.json:
        Path(args.json).write_text(json.dumps({"environment": "Qt offscreen, temporary file database",
                                               "steps": steps}, indent=2, ensure_ascii=False), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
