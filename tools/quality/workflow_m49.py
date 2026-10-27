#!/usr/bin/env python3
"""M49 Knowledge Assistant workflows through the real Documents tab, SYNTHETIC data.

A temporary FILE database (real initialisation, real authenticated users, no
fabricated principal) receives the M49 synthetic corpus
(tests/m49_knowledge_fixtures.py) through the real reviewed import, as the
``engineer``.  Questions are then asked as the read-only ``viewer`` through the
real ``DocumentsTab`` -> ``KnowledgeAssistantPanel`` and its own buttons.
Every expected value is read from the file with an independent ``sqlite3``
connection and plain SQL, never from the retrieval/answer code under test.

Flows:
  assistant:  empty library -> import -> cited answer whose every passage is
              the stored approved page text at its span -> citations map to
              evidence -> open the cited passage (exact span selected)
  scope:      well scope only cites documents linked to that well (SQL);
              rejected pages are never evidence
  currency:   delete a cited document -> the next answer never cites it
  model:      real loopback check against a closed port -> explicit
              unavailable state, extractive answer and evidence kept
  integrity:  asking wrote nothing (schema + every row count), integrity_check
              ok, no knowledge cache in the repository

Qt runs offscreen (``QT_QPA_PLATFORM=offscreen``); this is NOT a native
Windows desktop run.  No language model is used (none is installed).

Usage::

    QT_QPA_PLATFORM=offscreen python tools/quality/workflow_m49.py [--json OUT]

Exit status 0 only when every step passes.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPROVED = ("extracted", "approved", "edited")


def _raw(path, sql, *params):
    connection = sqlite3.connect(str(path))
    try:
        return connection.execute(sql, params).fetchall()
    finally:
        connection.close()


def _state(path):
    schema = _raw(path, "SELECT type, name, sql FROM sqlite_master ORDER BY type, name")
    tables = [n for t, n, _ in schema if t == "table" and not n.startswith("sqlite_")]
    return schema, {t: _raw(path, f'SELECT COUNT(*) FROM "{t}"')[0][0] for t in tables}


def _closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    work = Path(tempfile.mkdtemp(prefix="drillmaster-m49-workflow-"))
    db_path = work / "synthetic.db"
    os.environ.update({"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_DB_PATH": str(db_path), "DRILLMASTER_LOG_DIR": str(work / "logs"),
                       "DRILLMASTER_BACKUP_DIR": str(work / "backups"), "DRILLMASTER_AI_IMPORT": "0"})
    for name in ("DRILLMASTER_OLLAMA_URL", "DRILLMASTER_LLM_MODEL", "DRILLMASTER_EMBED_MODEL"):
        os.environ.pop(name, None)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance() or QApplication([])
    for name in ("warning", "information", "critical", "question"):
        setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))

    from core import knowledge_retrieval as kr
    from core.permissions import permissions, session_user
    from m49_knowledge_fixtures import build_corpus
    from synthetic_operations import make_file_database
    from tabs.documents_tab import DocumentsTab

    steps = []

    def step(flow, name, ok, detail=""):
        steps.append({"flow": flow, "step": len([s for s in steps if s["flow"] == flow]) + 1, "name": name,
                      "status": "PASS" if ok else "FAIL", "detail": detail})
        print(f"{flow:10s} {steps[-1]['step']:2d} {'PASS' if ok else 'FAIL'}  {name}  {detail}")

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)

    db = make_file_database(db_path)

    def login(user, password):
        principal = session_user(db.authenticate_user(user, password))
        permissions.set_user(principal)
        db.enforce_authorization(permissions)
        return principal

    login("viewer", "Synthetic-View-1!")
    tab = DocumentsTab(db)
    tab.show_dialogs = False
    tab.resize(1400, 1000)
    tab.show()
    panel = tab.assistant
    tab.sections.setCurrentWidget(panel)

    def ask(question, scope=kr.SCOPE_ALL, target=None, use_model=False):
        panel.scope_combo.setCurrentIndex(panel.scope_combo.findData(scope))
        if target is not None:
            panel.target_combo.setCurrentIndex(panel.target_combo.findData(target))
        panel.use_model_check.setChecked(use_model)
        panel.question_edit.setPlainText(question)
        panel.ask_button.click()
        end = time.monotonic() + 30
        while panel.current_state in ("searching", "retrieving", "generating") and time.monotonic() < end:
            pump(0.05)
        return panel.last_answer

    def page_text(document_id, page_no):
        rows = _raw(db_path, "SELECT text, review_status FROM document_pages WHERE document_id=? AND page_no=?",
                    document_id, page_no)
        return rows[0] if rows else (None, None)

    # ------------------------------------------------------------ assistant
    empty = ask("What is the planned mud weight for the 12-1/4 in section?")
    (stored,) = _raw(db_path, "SELECT COUNT(*) FROM documents")[0]
    step("assistant", "Empty library: explicit no-documents state (SQL: 0 documents)",
         stored == 0 and panel.current_state == "no_documents" and empty is not None and not empty.evidence,
         f"state={panel.current_state}")

    login("engineer", "Synthetic-Eng-1!")
    ids = build_corpus(db)
    login("viewer", "Synthetic-View-1!")
    tab.refresh()
    pump(0.3)
    asked = []
    answer = ask("What is the planned mud weight for the 12-1/4 in section?")
    asked.append(answer)
    exact = []
    for item in answer.evidence:
        text, status = page_text(item.document_id, item.page_no)
        exact.append(text is not None and status in APPROVED and text[item.start:item.end] == item.text)
    step("assistant", "Every evidence passage is the stored approved page text at its span (SQL)",
         answer.state == "ready" and answer.evidence and all(exact), f"{sum(exact)}/{len(answer.evidence)} exact")
    labels = {e.label for e in answer.evidence}
    cited = set(__import__("re").findall(r"\[(S\d+)\]", answer.text))
    step("assistant", "Every [S#] in the answer names a retrieved passage",
         bool(cited) and cited <= labels and answer.verified, f"cited={sorted(cited)}")
    values = {v for v in ("1.25", "1.32") if v in answer.text}
    rows = _raw(db_path, "SELECT COUNT(*) FROM document_pages WHERE text LIKE '%12-1/4 in section is 1.25 sg%' "
                         "OR text LIKE '%raised to 1.32 sg%'")[0][0]
    step("assistant", "Both conflicting stored values are shown and the conflict is noted",
         values == {"1.25", "1.32"} and rows == 2 and any("different values" in n for n in answer.notes),
         f"values={sorted(values)} sql_pages={rows}")
    target = next(e for e in answer.evidence if e.label in cited and e.document_id == ids["mud_rev2"])
    panel.answer_view.anchorClicked.emit(__import__("PySide6.QtCore", fromlist=["QUrl"]).QUrl(f"cite:{target.label}"))
    pump(0.4)
    text, _status = page_text(target.document_id, target.page_no)
    selected = tab.viewer.textCursor().selectedText()
    step("assistant", "Opening the citation selects exactly the stored span in the library viewer",
         tab.sections.currentIndex() == 0 and selected == text[target.start:target.end]
         and tab.cited_span == (target.document_id, target.page_no, target.start, target.end),
         f"doc={target.document_id} page={target.page_no}")
    tab.sections.setCurrentWidget(panel)

    # ------------------------------------------------------------ scope
    linked_c = {r[0] for r in _raw(db_path, "SELECT document_id FROM document_links WHERE well_id=?", ids["well_c"])}
    scoped = ask("pump liner size", kr.SCOPE_WELL, ids["well_c"])
    asked.append(scoped)
    docs = {e.document_id for e in scoped.evidence}
    step("scope", "Well scope cites only documents linked to that well (SQL)",
         scoped.state == "ready" and docs and docs <= linked_c, f"evidence docs={sorted(docs)} linked={sorted(linked_c)}")
    # A page rejected at review is not stored at all (reviewed import): the OCR
    # memo has 2 source pages and 1 stored page.  Evidence may only come from
    # stored pages with an approved review status.
    (source_pages,) = _raw(db_path, "SELECT page_count FROM documents WHERE id=?", ids["ocr"])[0]
    stored_ocr = {p for (p,) in _raw(db_path, "SELECT page_no FROM document_pages WHERE document_id=?", ids["ocr"])}
    approved = {(d, p) for d, p in _raw(db_path, "SELECT document_id, page_no FROM document_pages "
                                                 "WHERE review_status IN (?, ?, ?)", *APPROVED)}
    for question in ("How long did the blowout preventer drill take?", "scanned memo page 2"):
        asked.append(ask(question))
    used = {(e.document_id, e.page_no) for a in asked if a for e in a.evidence}
    step("scope", "Rejected page not stored; every evidence page is a stored approved page (SQL)",
         source_pages == 2 and stored_ocr == {1} and used and used <= approved and (ids["ocr"], 2) not in used,
         f"ocr source={source_pages} stored={sorted(stored_ocr)} evidence pages={len(used)}")

    # ------------------------------------------------------------ integrity (read-only asking)
    before = _state(db_path)
    for question in ("What is the kick tolerance for the 8-1/2 in section?", "توصيه براي هرزروي چيست؟",
                     "What is the mud motor bend angle for SYN-ZZ-99?",
                     "What is the planned mud weight for the 17-1/2 in section?"):
        asked.append(ask(question))
    after = _state(db_path)
    step("integrity", "Asking as the read-only viewer wrote nothing (schema and every row count)",
         before == after, f"{len(after[1])} tables compared")
    states = [a.state for a in asked[-4:]]
    step("integrity", "Answer states: ready, ready (Persian), no evidence, no evidence (unknown size)",
         states == ["ready", "ready", "no_evidence", "no_evidence"], f"states={states}")

    # ------------------------------------------------------------ model (real loopback check)
    panel.model_url_edit.setText(f"http://127.0.0.1:{_closed_port()}")
    panel.chat_model_combo.setEditText("syn-chat")
    panel.check_model()
    end = time.monotonic() + 15
    while panel.model_status is None and time.monotonic() < end:
        pump(0.05)
    status = panel.model_status
    option = (panel.use_model_check.isEnabled(), panel.use_model_check.isChecked())   # before ask() sets it
    with_model = ask("What is the kick tolerance for the 8-1/2 in section?", use_model=True)
    # A failed check disables (and unchecks) "write with the local model"; the
    # answer is then quoted from the documents.  (A model failing AFTER a good
    # check gives the model_unavailable answer state - covered by the UI tests
    # with the fake loopback server, which a real-only workflow cannot do.)
    step("model", "No model server: unavailable state with guidance, model option disabled",
         status is not None and not status.chat_ready and status.state == "not_running"
         and option == (False, False)
         and "unavailable" in panel.model_label.text().lower() and "ollama" in panel.model_label.text().lower(),
         f"model={getattr(status, 'state', None)}")
    step("model", "Asked WITH the model option forced on: still extractive (disabled option ignored)",
         with_model is not None and with_model.state == "ready" and with_model.mode == "extractive"
         and "50 bbl" in with_model.text and with_model.evidence and with_model.verified,
         f"state={getattr(with_model, 'state', None)} mode={getattr(with_model, 'mode', None)}")

    # ------------------------------------------------------------ currency (document deleted)
    login("engineer", "Synthetic-Eng-1!")
    tab.library.delete_document(ids["mud_rev2"])
    login("viewer", "Synthetic-View-1!")
    tab.refresh()
    pump(0.3)
    gone = _raw(db_path, "SELECT COUNT(*) FROM documents WHERE id=?", ids["mud_rev2"])[0][0]
    again = ask("What is the planned mud weight for the 12-1/4 in section?")
    step("currency", "After deleting a cited document the next answer never cites it",
         gone == 0 and again.state == "ready" and ids["mud_rev2"] not in {e.document_id for e in again.evidence}
         and "1.32" not in again.text, f"state={again.state}")

    (check,) = _raw(db_path, "PRAGMA integrity_check")[0]
    step("integrity", "PRAGMA integrity_check", check == "ok", check)
    step("integrity", "No knowledge cache or index inside the repository",
         not (ROOT / "knowledge_cache").exists() and not any(ROOT.glob("**/embeddings-v1.sqlite")))

    tab.cleanup()
    failed = [s for s in steps if s["status"] != "PASS"]
    print(f"\nsteps={len(steps)} passed={len(steps) - len(failed)} failed={len(failed)}")
    if args.json:
        Path(args.json).write_text(json.dumps({"steps": steps, "environment": {
            "qt_platform": os.environ.get("QT_QPA_PLATFORM"), "python": sys.version.split()[0],
            "platform": sys.platform}}, indent=2, ensure_ascii=False), encoding="utf-8")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    raise SystemExit(main())
