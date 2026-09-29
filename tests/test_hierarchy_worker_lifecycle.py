import threading
import time

import pytest


def test_hierarchy_refreshes_coalesce_without_overlapping_database_calls():
    try:
        from PySide6.QtWidgets import QApplication, QMainWindow, QTreeWidget
    except ImportError as exc:  # pragma: no cover - host Qt runtime dependent
        pytest.skip(f"Qt runtime unavailable: {exc}")
    from core.cache_manager import cache
    from main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    cache.delete("main_window_hierarchy")

    class SlowDatabase:
        def __init__(self):
            self.started = threading.Event()
            self.release = threading.Event()
            self.calls = 0
            self.active = 0
            self.max_active = 0
            self.lock = threading.Lock()

        def get_full_hierarchy(self):
            with self.lock:
                self.calls += 1
                call = self.calls
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            if call == 1:
                self.started.set()
                assert self.release.wait(5), "test did not release the first DB call"
            with self.lock:
                self.active -= 1
            return [{"id": call, "name": f"result-{call}", "projects": []}]

    db = SlowDatabase()
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.db_manager = db
    window.tree_widget = QTreeWidget()
    window._hierarchy_worker = None
    window._hierarchy_generation = 0
    window._hierarchy_refresh_pending = False
    window._hierarchy_shutdown_requested = False
    window._close_confirmed = False
    rendered = []
    window._build_tree_from_data = lambda result: rendered.append(result)
    window.show_loading = lambda _message: None
    window.hide_loading = lambda: None

    try:
        window.populate_hierarchy()
        assert db.started.wait(3)
        first_worker = window._hierarchy_worker
        assert first_worker is not None and first_worker.isRunning()

        # More refreshes during one synchronous DB call are coalesced to one
        # subsequent read; none may force-terminate or overlap the first call.
        window.populate_hierarchy()
        window.populate_hierarchy()
        assert window._hierarchy_worker is first_worker
        assert db.calls == 1
        db.release.set()

        deadline = time.monotonic() + 8
        while (window._hierarchy_worker is not None or not rendered) and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()

        assert db.calls == 2
        assert db.max_active == 1
        assert rendered == [[{"id": 2, "name": "result-2", "projects": []}]]
        assert window._hierarchy_worker is None
    finally:
        db.release.set()
        worker = window._hierarchy_worker
        if worker is not None:
            worker.wait(3000)
        cache.delete("main_window_hierarchy")
        window.setParent(None)
        window.deleteLater()
        app.processEvents()
