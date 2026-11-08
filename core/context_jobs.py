"""M103: one reusable pattern for background reads bound to the selection context.

    runner = ContextJobRunner(db_manager, "operational analysis")
    runner.result_ready.connect(show)            # (job_id, dto) - only current, non-stale results
    runner.state_changed.connect(show_state)     # (state, message)
    runner.start(compute, params)                # compute(db_view, params, cancel_event) -> plain DTO

Contract
* GUI snapshot: ``params`` is plain data captured on the GUI thread (ids, dates, flags); no
  widget, ORM object or session crosses into the worker.
* Worker session: ``compute`` receives its own database view (``core.export_jobs.worker_database``:
  a separate read-only connection on file databases). In-memory databases share one connection,
  so the job runs synchronously on the calling thread and the state message says so.
* DTOs: ``compute`` returns plain data; ORM rows never leave it.
* Context token: the ``SelectionManager.context_token()`` captured at start. A result whose
  token is no longer current (well/wellbore/section/report changed or cleared) is rejected
  as STALE, never shown.
* Newer job wins: starting a job supersedes the running one; a superseded result is rejected
  even when it finishes first or last.
* States: IDLE, LOADING, DONE, EMPTY, ERROR, CANCELLED, STALE. ``retry()`` re-runs the last
  job with the same snapshot; an error message carries the exception type only.
* Cancel: cooperative (``cancel_event`` is checked by ``compute`` between steps); a cancelled
  result is discarded even when it completes.
* Safe close: ``shutdown(timeout_ms)`` cancels, waits a bounded time and never deletes a running
  thread (``release_when_finished``); it reports whether the worker stopped.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)

IDLE, LOADING, DONE, EMPTY, ERROR, CANCELLED, STALE = (
    "IDLE", "LOADING", "DONE", "EMPTY", "ERROR", "CANCELLED", "STALE")


class JobCancelled(Exception):
    """Raised by ``compute`` (via ``check_cancel``) to stop early."""


def check_cancel(cancel_event) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise JobCancelled()


class _JobThread(QThread):
    finished_job = Signal(int, object, object)        # job id, result, error type name (or None)

    def __init__(self, job_id, db_manager, compute, params, cancel_event):
        super().__init__()
        self.job_id, self.db_manager, self.compute, self.params = job_id, db_manager, compute, params
        self.cancel_event = cancel_event

    def run(self):
        result, error = None, None
        try:
            from core.export_jobs import worker_database
            with worker_database(self.db_manager) as db:
                result = self.compute(db, self.params, self.cancel_event)
        except JobCancelled:  # silent-ok: cancellation is a control signal, shown as the CANCELLED state
            error = "JobCancelled"
        except Exception as exc:      # reported to the GUI as the type name; the runner shows ERROR
            logger.warning("Background job failed: %s", type(exc).__name__)
            error = type(exc).__name__
        self.finished_job.emit(self.job_id, result, error)


class ContextJobRunner(QObject):
    result_ready = Signal(int, object)        # job id, DTO
    state_changed = Signal(str, str)          # state, user-facing message

    def __init__(self, db_manager, name: str, *, selection=None, is_empty: Optional[Callable[[Any], bool]] = None,
                 retry_hint: str = "Press Retry.", refresh_hint: str = "Press Refresh for the new selection.",
                 parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.name = name
        # M138: the action the ERROR / STALE messages name must exist on the panel that shows them
        self.retry_hint, self.refresh_hint = retry_hint, refresh_hint
        self._selection = selection
        self._is_empty = is_empty
        self._next_id = 0
        self.current_id: Optional[int] = None
        self._token = None
        self._cancel: Optional[threading.Event] = None
        self._last = None                     # (compute, params) for retry
        self._threads = {}                    # job id -> running thread
        self._started_at = {}
        self.state = IDLE
        self.message = ""
        self.last_duration_s: Optional[float] = None
        self.rejected = {"superseded": 0, "stale": 0, "cancelled": 0}
        self.synchronous = False

    # -- context ------------------------------------------------------------------------------
    def _sel(self):
        if self._selection is None:
            from core.selection_manager import SelectionManager
            self._selection = SelectionManager()
        return self._selection

    def _set_state(self, state: str, message: str) -> None:
        self.state, self.message = state, message
        self.state_changed.emit(state, message)

    @property
    def busy(self) -> bool:
        return self.state == LOADING

    # -- jobs ---------------------------------------------------------------------------------
    def start(self, compute, params) -> int:
        """Start ``compute(db, params, cancel_event)``; any running job becomes superseded."""
        if self._cancel is not None:
            self._cancel.set()                # the superseded job stops at its next check
        self._next_id += 1
        job_id = self._next_id
        self.current_id = job_id
        self._token = self._sel().context_token()
        self._cancel = threading.Event()
        self._last = (compute, params)
        self._started_at[job_id] = time.perf_counter()
        from core.export_jobs import has_isolated_reader
        self.synchronous = not has_isolated_reader(self.db_manager)
        self._set_state(LOADING, f"Loading {self.name}…"
                        + (" (in-memory database: read on the GUI thread)" if self.synchronous else ""))
        if self.synchronous:
            result, error = None, None
            try:
                result = compute(self.db_manager, params, self._cancel)
            except JobCancelled:  # silent-ok: cancellation is a control signal, shown as the CANCELLED state
                error = "JobCancelled"
            except Exception as exc:  # shown as ERROR with the type name
                logger.warning("Job %s failed: %s", self.name, type(exc).__name__)
                error = type(exc).__name__
            self._finished(job_id, result, error)
            return job_id
        thread = _JobThread(job_id, self.db_manager, compute, params, self._cancel)
        thread.finished_job.connect(self._finished)
        thread.finished.connect(lambda j=job_id: self._threads.pop(j, None))
        self._threads[job_id] = thread
        thread.start()
        from core.async_workers import release_when_finished
        release_when_finished(thread)
        return job_id

    def _finished(self, job_id: int, result, error) -> None:
        started = self._started_at.pop(job_id, None)
        if job_id != self.current_id:
            self.rejected["superseded"] += 1          # a newer job owns the screen
            return
        self.last_duration_s = None if started is None else time.perf_counter() - started
        if error == "JobCancelled" or (self._cancel is not None and self._cancel.is_set()):
            self.rejected["cancelled"] += 1
            self._set_state(CANCELLED, f"{self.name.capitalize()} cancelled; nothing is shown.")
            return
        if not self._sel().is_current(self._token):
            self.rejected["stale"] += 1
            self._set_state(STALE, f"The selection changed while {self.name} was loading; "
                                   f"the result was discarded. {self.refresh_hint}")
            return
        if error is not None:
            self._set_state(ERROR, f"{self.name.capitalize()} failed ({error}); nothing is shown. {self.retry_hint}")
            return
        if self._is_empty is not None and self._is_empty(result):
            self._set_state(EMPTY, f"No data for {self.name} in this scope.")
        else:
            self._set_state(DONE, f"{self.name.capitalize()} loaded in {self.last_duration_s:.2f} s.")
        self.result_ready.emit(job_id, result)

    def cancel(self) -> None:
        """Cancel the current job (its result is discarded whenever it arrives)."""
        if self._cancel is not None and self.state == LOADING:
            self._cancel.set()
            if not self._threads:             # synchronous runs are over already
                return
            self._set_state(CANCELLED, f"Cancelling {self.name}…")

    def invalidate(self) -> None:
        """The view was reset: any running job's result is no longer wanted."""
        if self._cancel is not None:
            self._cancel.set()
        self.current_id = None
        if self.state == LOADING:
            self._set_state(IDLE, "")

    def retry(self) -> Optional[int]:
        if self._last is None:
            return None
        compute, params = self._last
        return self.start(compute, params)

    def wait(self, timeout_ms: int = 30000) -> bool:
        """Pump events until no job runs (tests and shutdown); True when idle."""
        from PySide6.QtCore import QCoreApplication
        end = time.monotonic() + timeout_ms / 1000.0
        while self._threads and time.monotonic() < end:
            QCoreApplication.processEvents()
            for thread in list(self._threads.values()):
                thread.wait(10)
        QCoreApplication.processEvents()
        return not self._threads

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        """Cancel and wait (bounded) for running workers; never deletes a running thread."""
        self.invalidate()
        end = time.monotonic() + timeout_ms / 1000.0
        for thread in list(self._threads.values()):
            thread.wait(max(1, int((end - time.monotonic()) * 1000)))
        stopped = all(not t.isRunning() for t in self._threads.values())
        if not stopped:
            logger.warning("%s: a worker is still running after %d ms; it is left to finish", self.name, timeout_ms)
        return stopped
