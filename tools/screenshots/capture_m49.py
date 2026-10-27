"""Capture M49 Knowledge Assistant screenshots of the running application.

Runs the real ``MainWindow`` against a throw-away file database in a
temporary directory (real initialisation, real sign-in with a random admin
password).  The SYNTHETIC corpus of tests/m49_knowledge_fixtures.py is
imported through the real reviewed-import path after the first shot.
Saves ``QWidget.grab()`` images of the Documents tab:

* the assistant with an empty library;
* the Library & Search page with keyword search results;
* a multi-source answer with a value conflict (two documents cited);
* the cited passage opened and highlighted in the library viewer;
* the local-model check with no model server running (real check against
  127.0.0.1:11434 - nothing is installed in the capture environment);
* insufficient evidence for a question the documents do not answer;
* a Persian question with a right-to-left answer;
* a source with instruction-like text flagged, the answer unaffected;
* a well-scoped question.

Environment honesty: run with ``QT_QPA_PLATFORM=offscreen`` (raster
rendering, no window manager, bundled fonts).  Images show the application's
real widgets and data, not a native Windows desktop.  No language model is
used in any image (answers are extractive).

Usage::

    QT_QPA_PLATFORM=offscreen python tools/screenshots/capture_m49.py --out DIR
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _pump(app, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="drillmaster-m49-shots-"))
    os.environ.update({"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_DB_PATH": str(work / "synthetic.db"),
                       "DRILLMASTER_LOG_DIR": str(work / "logs"),
                       "DRILLMASTER_BACKUP_DIR": str(work / "backups"),
                       "DRILLMASTER_AI_IMPORT": "0"})
    for name in ("DRILLMASTER_OLLAMA_URL", "DRILLMASTER_LLM_MODEL", "DRILLMASTER_EMBED_MODEL"):
        os.environ.pop(name, None)
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

    from PySide6.QtCore import QSettings, QUrl
    from PySide6.QtWidgets import QApplication, QMessageBox

    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(work / "settings"))
    app = QApplication.instance() or QApplication(sys.argv)
    for name in ("warning", "information", "critical", "question"):
        setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))

    from core import knowledge_retrieval as kr
    from core.database import DatabaseManager
    from core.permissions import permissions, session_user
    from m49_knowledge_fixtures import build_corpus

    password = secrets.token_urlsafe(18) + "aA1!"
    db = DatabaseManager(bootstrap_passwords={"admin": password})
    db.db_path = str(work / "synthetic.db")
    if not db.initialize():
        raise SystemExit(f"database initialization failed: {db.last_diagnostic}")
    user = session_user(db.authenticate_user("admin", password))
    permissions.set_user(user)
    db.enforce_authorization(permissions)

    from main_window import MainWindow

    window = MainWindow(db_manager=db, user=user, startup_result=None)
    window.resize(1600, 1150)
    window.show()
    _pump(app, 2.0)
    tab = window.documents_tab
    panel = tab.assistant
    window.tab_widget.setCurrentWidget(tab)

    def shot(name: str):
        path = out / f"{name}.png"
        window.grab().save(str(path))
        print("saved", path)

    def assistant():
        tab.sections.setCurrentWidget(panel)
        _pump(app, 0.3)

    def ask(question, scope=kr.SCOPE_ALL, target=None):
        assistant()
        panel.scope_combo.setCurrentIndex(panel.scope_combo.findData(scope))
        if target is not None:
            panel.target_combo.setCurrentIndex(panel.target_combo.findData(target))
        panel.question_edit.setPlainText(question)
        panel.ask()
        end = time.monotonic() + 20
        while (panel.worker is not None or panel.current_state in ("searching", "retrieving", "generating")) \
                and time.monotonic() < end:
            _pump(app, 0.05)
        _pump(app, 0.4)

    ask("What is the planned mud weight for the 12-1/4 in section?")
    shot("m49_assistant_no_documents")

    ids = build_corpus(db)
    tab.refresh()
    _pump(app, 0.5)

    tab.sections.setCurrentIndex(0)
    tab.search_edit.setText("pump liner")
    tab.run_search()
    _pump(app, 0.5)
    shot("m49_library_search_results")

    ask("What is the planned mud weight for the 12-1/4 in section?")
    shot("m49_multi_source_answer")

    panel.answer_view.anchorClicked.emit(QUrl("cite:S3"))   # S3 is cited in the answer (second document)
    _pump(app, 0.6)
    shot("m49_source_opened")

    assistant()
    panel.chat_model_combo.setEditText("qwen2.5:1.5b")
    panel.check_model()                       # real check: nothing listens on 127.0.0.1:11434 here
    end = time.monotonic() + 15
    while panel.model_status is None and time.monotonic() < end:
        _pump(app, 0.05)
    ask("What is the kick tolerance for the 8-1/2 in section?")
    shot("m49_model_unavailable")

    ask("What is the mud motor bend angle for SYN-ZZ-99?")
    shot("m49_insufficient_evidence")

    ask("توصيه براي هرزروي چيست؟")
    shot("m49_persian_answer")

    ask("What is the cement slurry density for the 9-5/8 in casing?")
    shot("m49_injection_flagged")

    ask("pump liner size", kr.SCOPE_WELL, ids["well_c"])
    shot("m49_scope_well")

    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
