"""Cyclic garbage collection only on the GUI thread (M50).

Why: Python's automatic cyclic collector runs in whichever thread happens to
allocate when a generation threshold is crossed.  In this application that
can be a worker thread (Analysis revision, M47 read-only queries and exports,
the knowledge assistant).  When the collected cycles contain PySide wrappers
of GUI objects (replaced charts, labels, menus of a closed page), their C++
destructors then run on the worker thread.  M50 reproduced the consequence
in ``tests/m50_analysis_child.py`` and captured it with native stacks: the
worker held Qt's connection mutex inside ``QObject::~QObject`` and waited for
the GIL, while the GUI thread held the GIL in
``Shiboken::BindingManager::runDeletionInMainThread`` and waited for that
mutex - a permanent deadlock.

Fix (the same policy pyqtgraph ships as ``util.garbage_collector``): disable
automatic collection and collect from a ``QTimer`` on the GUI thread, using
the interpreter's own per-generation thresholds.  Reference counting is not
affected; only reference *cycles* are reclaimed up to one interval later.

Watchdog (M51 §9).  Disabling automatic collection does not stop an explicit
``gc.collect()`` - from our code or a library - on a worker thread, and a
library could re-enable automatic collection.  A ``gc.callbacks`` hook
therefore counts every collection that STARTS off the GUI thread (the hook
only increments counters: no logging, locking or Qt call inside the
collector), and each timer tick re-disables automatic collection if anything
enabled it.  Both are reported from the GUI thread and exposed by
:meth:`MainThreadGarbageCollector.stats` for the soak tests.

Known limits: cycles live up to one interval longer; while the GUI thread is
blocked no collection runs (memory held by cycles grows until it returns);
a worker collection is detected and reported, not prevented.
"""
from __future__ import annotations

import gc
import logging
import threading

from PySide6.QtCore import QObject, QTimer

DEFAULT_INTERVAL_MS = 1000
MAX_THREAD_NAMES = 10

logger = logging.getLogger(__name__)

_collector = None


class MainThreadGarbageCollector(QObject):
    """Runs ``gc.collect(n)`` from a GUI-thread timer when generation ``n`` is due."""

    def __init__(self, parent=None, interval_ms: int = DEFAULT_INTERVAL_MS):
        super().__init__(parent)
        self.threshold = gc.get_threshold()
        self.collections = [0, 0, 0]
        self.worker_collections = 0         # collections that started on any other thread (watchdog)
        self.worker_threads = []            # their thread names, first MAX_THREAD_NAMES
        self.reenabled = 0                  # times automatic collection was found enabled and disabled again
        self._reported = 0
        self._gui_thread = threading.current_thread()
        gc.callbacks.append(self._watch)
        gc.disable()
        self.timer = QTimer(self)
        self.timer.setInterval(int(interval_ms))
        self.timer.timeout.connect(self.check)
        self.timer.start()

    def _watch(self, phase, _info):
        """``gc.callbacks`` hook: runs in the collecting thread, so it only counts."""
        if phase == "start" and threading.current_thread() is not self._gui_thread:
            self.worker_collections += 1
            if len(self.worker_threads) < MAX_THREAD_NAMES:
                self.worker_threads.append(threading.current_thread().name)

    def check(self):
        if gc.isenabled():
            gc.disable()
            self.reenabled += 1
            logger.warning("Automatic garbage collection was re-enabled by other code; disabled again")
        if self.worker_collections != self._reported:
            self._reported = self.worker_collections
            logger.warning("A garbage collection ran off the GUI thread (%d so far)", self.worker_collections)
        count0, count1, count2 = gc.get_count()
        if count0 > self.threshold[0]:
            gc.collect(0)
            self.collections[0] += 1
            if count1 > self.threshold[1]:
                gc.collect(1)
                self.collections[1] += 1
                if count2 > self.threshold[2]:
                    gc.collect(2)
                    self.collections[2] += 1

    def stats(self) -> dict:
        return {"collections": list(self.collections), "worker_collections": self.worker_collections,
                "worker_threads": list(self.worker_threads), "reenabled": self.reenabled,
                "automatic_enabled": gc.isenabled()}

    def stop(self):
        self.timer.stop()
        if self._watch in gc.callbacks:
            gc.callbacks.remove(self._watch)
        gc.enable()


def install(app, interval_ms: int = DEFAULT_INTERVAL_MS) -> MainThreadGarbageCollector:
    """Install once, from the GUI thread, before any worker thread starts."""
    global _collector
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("the garbage-collection policy must be installed from the GUI thread")
    if _collector is None:
        _collector = MainThreadGarbageCollector(app, interval_ms)
    return _collector


def installed() -> bool:
    return _collector is not None and _collector.timer.isActive() and not gc.isenabled()


def uninstall() -> None:
    """Tests only: restore automatic collection."""
    global _collector
    if _collector is not None:
        _collector.stop()
        _collector.deleteLater()
        _collector = None
