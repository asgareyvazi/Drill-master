"""Qt workers for expensive Import/AI/PDF operations."""
from PySide6.QtCore import QThread, Signal
import traceback

class FunctionWorker(QThread):
    """Run a callable off the UI thread and report result/error."""
    result_ready = Signal(object)
    failed = Signal(str)
    finished_ok = Signal()

    def __init__(self, function, *args, parent=None, **kwargs):
        super().__init__(parent)
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            self.result_ready.emit(self.function(*self.args, **self.kwargs))
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(f"{exc}\n{traceback.format_exc()}")


class ExportWorker(QThread):
    """Export Center jobs off the UI thread (see ``core.export_jobs``).

    ``build_jobs`` runs in the worker with the worker's own read-only
    database view and returns the jobs; it receives plain identifiers only.
    ``cancel`` takes effect between files. ``failed`` carries the exception
    type name only.
    """
    progress = Signal(int, int, object)   # done, total, ExportOutcome
    completed = Signal(object)            # BatchResult
    failed = Signal(str)

    def __init__(self, db_manager, build_jobs, parent=None):
        super().__init__(parent)
        import threading

        self.db_manager = db_manager
        self.build_jobs = build_jobs
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    def run(self):
        import logging

        from core.export_jobs import run_jobs, worker_database

        try:
            with worker_database(self.db_manager) as db:
                jobs = self.build_jobs(db)
                result = run_jobs(db, jobs, progress=self.progress.emit, cancel_event=self._cancel)
        except Exception as exc:
            logging.getLogger(__name__).warning("Export worker failed: %s", type(exc).__name__)
            self.failed.emit(type(exc).__name__)
            return
        self.completed.emit(result)


class ReadOnlyQueryWorker(QThread):
    """Run ``fn(db)`` off the UI thread with its own read-only connection.

    ``fn`` receives a manager view from ``core.export_jobs.worker_database``
    (separate ``mode=ro`` SQLite connection, restore-gated), so it can never
    write and never touches the application's shared connection.  Only use
    it when ``has_isolated_reader(db_manager)`` is true; otherwise call ``fn``
    synchronously.  ``failed`` carries the exception type name only.
    """
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, db_manager, fn, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.fn = fn

    def run(self):
        import logging

        from core.export_jobs import worker_database

        try:
            with worker_database(self.db_manager) as db:
                result = self.fn(db)
        except Exception as exc:
            logging.getLogger(__name__).warning("Read-only worker failed: %s", type(exc).__name__)
            self.failed.emit(type(exc).__name__)
            return
        self.completed.emit(result)
