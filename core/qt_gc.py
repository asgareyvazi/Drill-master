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
"""
from __future__ import annotations

import gc
import threading

from PySide6.QtCore import QObject, QTimer

DEFAULT_INTERVAL_MS = 1000

_collector = None


class MainThreadGarbageCollector(QObject):
    """Runs ``gc.collect(n)`` from a GUI-thread timer when generation ``n`` is due."""

    def __init__(self, parent=None, interval_ms: int = DEFAULT_INTERVAL_MS):
        super().__init__(parent)
        self.threshold = gc.get_threshold()
        self.collections = [0, 0, 0]
        gc.disable()
        self.timer = QTimer(self)
        self.timer.setInterval(int(interval_ms))
        self.timer.timeout.connect(self.check)
        self.timer.start()

    def check(self):
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

    def stop(self):
        self.timer.stop()
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
