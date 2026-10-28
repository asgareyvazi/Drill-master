"""Capture M50 screenshots of the running application.

Runs the real ``MainWindow`` against a throw-away file database in a
temporary directory (real initialisation, real sign-in with a random admin
password).  The SYNTHETIC M48 wells (tests/m48_synthetic.py) give the Analysis
page data; the SYNTHETIC M50 corpus (tests/m50_knowledge_fixtures.py) is
imported through the real reviewed-import path.  Saves ``QWidget.grab()``
images:

* a lexical (extractive) answer with its diagnostics;
* semantic retrieval unavailable, with the reason (real model check: nothing
  listens on 127.0.0.1:11434 in the capture environment);
* a value conflict, both values cited;
* a refusal (insufficient evidence) and why;
* the local model unavailable (same real check);
* the scope changed while a question was being answered (result dropped);
* the Analysis page updating while its data revision runs off the GUI thread.

NOT captured, and why: "semantic retrieval enabled" (needs a real local
embedding model - none installed; never faked) and a model draft failing the
number/unit checks (only a real model produces a draft; the rendering is
covered by tests/test_m49_knowledge_ui.py and tests/test_m50_citation_navigation.py).

Environment honesty: run with ``QT_QPA_PLATFORM=offscreen`` (raster
rendering, no window manager, bundled fonts).  Images show the application's
real widgets and data, not a native Windows desktop.  No language model is
used in any image.

Usage::

    QT_QPA_PLATFORM=offscreen python tools/screenshots/capture_m50.py --out DIR
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

    work = Path(tempfile.mkdtemp(prefix="drillmaster-m50-shots-"))
    os.environ.update({"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_DB_PATH": str(work / "synthetic.db"),
                       "DRILLMASTER_LOG_DIR": str(work / "logs"),
                       "DRILLMASTER_BACKUP_DIR": str(work / "backups"),
                       "DRILLMASTER_AI_IMPORT": "0"})
    for name in ("DRILLMASTER_OLLAMA_URL", "DRILLMASTER_LLM_MODEL", "DRILLMASTER_EMBED_MODEL"):
        os.environ.pop(name, None)
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QMessageBox

    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(work / "settings"))
    app = QApplication.instance() or QApplication(sys.argv)
    for name in ("warning", "information", "critical", "question"):
        setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))

    from core import knowledge_retrieval as kr
    from core.database import DatabaseManager
    from core.permissions import permissions, session_user
    from core.selection_manager import SelectionManager
    from m48_synthetic import build as build_m48
    from m50_knowledge_fixtures import build_m50_corpus

    password = secrets.token_urlsafe(18) + "aA1!"
    db = DatabaseManager(bootstrap_passwords={"admin": password})
    db.db_path = str(work / "synthetic.db")
    if not db.initialize():
        raise SystemExit(f"database initialization failed: {db.last_diagnostic}")
    _db, m48_ids = build_m48(db)
    user = session_user(db.authenticate_user("admin", password))
    permissions.set_user(user)
    db.enforce_authorization(permissions)
    build_m50_corpus(db)

    from main_window import MainWindow

    window = MainWindow(db_manager=db, user=user, startup_result=None)
    window.resize(1600, 1250)
    window.show()
    _pump(app, 2.0)
    tab = window.documents_tab
    panel = tab.assistant
    window.tab_widget.setCurrentWidget(tab)
    tab.refresh()
    _pump(app, 0.5)

    def shot(name: str):
        path = out / f"{name}.png"
        window.grab().save(str(path))
        print("saved", path)

    def assistant():
        window.tab_widget.setCurrentWidget(tab)
        tab.sections.setCurrentWidget(panel)
        _pump(app, 0.3)

    def wait_answer():
        end = time.monotonic() + 20
        while (panel.worker is not None or panel.current_state in ("searching", "retrieving", "generating")) \
                and time.monotonic() < end:
            _pump(app, 0.05)
        _pump(app, 0.4)

    def ask(question, scope=kr.SCOPE_ALL):
        assistant()
        panel.scope_combo.setCurrentIndex(panel.scope_combo.findData(scope))
        panel.question_edit.setPlainText(question)
        panel.ask()
        wait_answer()

    def check_model(chat, embed):
        assistant()
        panel.chat_model_combo.setEditText(chat)
        panel.embed_model_combo.setEditText(embed)
        panel.model_status = None
        panel.check_model()                   # real check: nothing listens on 127.0.0.1:11434 here
        end = time.monotonic() + 15
        while panel.model_status is None and time.monotonic() < end:
            _pump(app, 0.05)

    ask("What is the planned flow rate for the 12-1/4 in section of SYN-KE-05?")
    shot("m50_lexical_answer_diagnostics")

    check_model("", "bge-m3")
    ask("What is the equivalent circulating density limit for the 12-1/4 in section of SYN-KE-05?")
    shot("m50_semantic_unavailable_reason")

    ask("What is the planned mud weight for the 16 in section of SYN-KE-05?")
    shot("m50_conflict_both_values")

    ask("What is the planned mud weight for the 8-1/2 in section of SYN-KE-05?")
    shot("m50_refusal_insufficient_evidence")

    check_model("qwen2.5:7b-instruct", "")
    ask("What is the kick tolerance for the 8-1/2 in section?")
    shot("m50_model_unavailable")

    assistant()
    panel.scope_combo.setCurrentIndex(panel.scope_combo.findData(kr.SCOPE_ALL))
    panel.question_edit.setPlainText("What is the planned mud weight for the 16 in section of SYN-KE-05?")
    panel.ask()                                       # the worker is running ...
    panel.scope_combo.setCurrentIndex(panel.scope_combo.findData(kr.SCOPE_WELL))   # ... scope changes
    _pump(app, 1.0)                                   # the late result arrives and is dropped
    if panel.worker is not None or panel.answer_view.toPlainText().strip() or panel.last_answer is not None:
        raise SystemExit("scope-change shot invalid: the late result was not dropped")
    shot("m50_scope_changed_mid_request")

    page = window.analysis_widget
    window.tab_widget.setCurrentWidget(page)
    SelectionManager().select_well(m48_ids["C"], {"name": "SYN-C"})
    _pump(app, 1.5)
    page.analysis_tabs.setCurrentIndex(0)
    page.update_all_data()                            # starts the off-thread revision ...
    if page._rev_worker is None or "Updating" not in page.status_label.text():
        raise SystemExit("analysis shot invalid: no revision in flight")
    shot("m50_analysis_updating_responsive")          # ... grabbed while it runs (GUI thread free)
    print("revision worker running at grab:", page._rev_worker is not None and page._rev_worker.isRunning())
    _pump(app, 1.5)

    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
