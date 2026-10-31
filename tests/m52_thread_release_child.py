"""M52 child process: worker result slots must not destroy a still-running QThread.

Run by ``tests/test_m52_thread_release.py`` (never collected by pytest).  Each
scenario keeps a worker inside ``run()`` for a while AFTER it emitted its result
signal - the window in which a ``deleteLater()`` from the result slot destroys a
running thread and Qt aborts the process ("QThread: Destroyed while thread is
still running").  The child prints ``OK <scenario>`` and exits 0 only if it
survives and the worker object was released after ``finished``.

Synthetic data only; offscreen Qt.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from PySide6.QtCore import QThread, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

LINGER = 0.4


class Lingering(QThread):
    """Emits its result, then stays in run() - like FunctionWorker emitting finished_ok next."""

    done = Signal()

    def run(self):
        self.done.emit()
        time.sleep(LINGER)


def pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


def watch(worker, events):
    worker.finished.connect(lambda: events.append("finished"))
    worker.destroyed.connect(lambda *_: events.append("destroyed"))


def released_after_finished(events):
    return "finished" in events and "destroyed" in events and events.index("finished") < events.index("destroyed")


def scenario_helper(app):
    from core.async_workers import release_when_finished
    events = []
    worker = Lingering()
    watch(worker, events)
    worker.done.connect(lambda: release_when_finished(worker))
    worker.start()
    pump(app, LINGER * 3)
    return released_after_finished(events)


def _panel():
    from tabs.knowledge_assistant import KnowledgeAssistantPanel
    return KnowledgeAssistantPanel(None)


def scenario_status(app):
    panel = _panel()
    events = []
    worker = Lingering(panel)
    watch(worker, events)
    panel.status_worker = worker
    panel._generation_status = 1
    worker.done.connect(lambda: panel._status_done(0, None))       # stale generation: only the release runs
    worker.start()
    pump(app, LINGER * 3)
    return released_after_finished(events) and panel.status_worker is None


def scenario_semantic(app):
    panel = _panel()
    events = []
    worker = Lingering(panel)
    watch(worker, events)
    panel.semantic_worker = worker
    worker.done.connect(lambda: panel._semantic_done({"state": "failed", "message": "synthetic"}))
    worker.start()
    pump(app, LINGER * 3)
    return released_after_finished(events) and "not built" in panel.semantic_label.text()


def scenario_mineru(app):
    from dialogs.excel_import_dialog import ExcelImportDialog
    events = []
    outcomes = []
    for slot, argument in ((ExcelImportDialog._on_mineru_batch_ready, []),
                           (ExcelImportDialog._on_mineru_batch_failed, "synthetic failure")):
        worker = Lingering()
        watch(worker, events)
        host = types.SimpleNamespace(_mineru_worker=worker, _pending_import_files=[], _mineru_results={},
                                     _result_key=lambda source: str(source),
                                     _run_import_pipeline=lambda *a, **k: outcomes.append("pipeline"))
        worker.done.connect(lambda s=slot, h=host, a=argument: s(h, a))
        worker.start()
        pump(app, LINGER * 3)
        outcomes.append(host._mineru_worker is None)
    return events.count("destroyed") == 2 and events.count("finished") == 2 and all(
        o for o in outcomes if o != "pipeline") and outcomes.count("pipeline") == 2


def scenario_choices(app):
    data = Path(tempfile.mkdtemp(prefix="m52-thread-release-"))
    os.environ.update({"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(data),
                       "DRILLMASTER_DB_PATH": str(data / "synthetic-m52-release.db"),
                       "DRILLMASTER_BACKUP_DIR": str(data / "backups"), "DRILLMASTER_AI_IMPORT": "0"})
    from core import knowledge_retrieval as kr
    from core.database import DatabaseManager
    from tabs import knowledge_assistant as ka_tab
    from tabs.documents_tab import DocumentsTab
    real_run = ka_tab.ScopeChoicesWorker.run

    def lingering_run(self):
        real_run(self)
        time.sleep(LINGER)                          # still inside run() after done was emitted
    ka_tab.ScopeChoicesWorker.run = lingering_run
    db = DatabaseManager()
    assert db.initialize(), db.last_diagnostic
    tab = DocumentsTab(db)
    tab.show_dialogs = False
    panel = tab.assistant
    panel.scope_combo.setCurrentIndex(panel.scope_combo.findData(kr.SCOPE_WELL))
    worker = panel.choices_workers["targets"]
    events = []
    watch(worker, events)
    pump(app, LINGER * 3)
    ok = released_after_finished(events) and panel.choices_state["targets"] == "ready"
    tab.cleanup()
    db.close()
    return ok


SCENARIOS = {"helper": scenario_helper, "status": scenario_status, "semantic": scenario_semantic,
             "mineru": scenario_mineru, "choices": scenario_choices}


def main(argv):
    name = argv[1]
    app = QApplication.instance() or QApplication([])
    ok = SCENARIOS[name](app)
    print(f"{'OK' if ok else 'NOT RELEASED'} {name}", flush=True)
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
