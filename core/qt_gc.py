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

Scheduling (M52 §2.1).  A collection traverses every object of the collected
generations that is still alive.  The Analysis snapshot worker holds hundreds of
thousands of young ORM objects while it reads (64k synthetic time-log rows: a
GUI-thread generation-0 collection traversed 0.6-1.4 million live objects for
60-186 ms and collected 0-910 of them, then promoted them all); a moment later
reference counting frees them without any collection.  A worker that knows it
allocates such a transient heap takes a ``hold()``; while a hold is younger than
``DEFER_MAX_MS`` and the young generation is below ``DEFER_MAX_YOUNG``, young
collections are deferred (counted in ``deferred``); past either bound they run
as usual (counted in ``forced``).  Taking a hold on the GUI thread first
collects whatever is due, so every cycle's garbage is collected while it is
small.  Collection still happens only on the GUI thread and automatic
collection stays disabled.

Known limits: cycles live up to one interval longer (up to ``DEFER_MAX_MS``
during a hold); while the GUI thread is blocked no collection runs (memory held
by cycles grows until it returns); a worker collection is detected and
reported, not prevented.
"""
from __future__ import annotations

import gc
import logging
import threading
import time

from PySide6.QtCore import QObject, QTimer

DEFAULT_INTERVAL_MS = 1000
DEFER_MAX_MS = 10_000               # a hold older than this no longer defers anything
DEFER_MAX_YOUNG = 2_000_000         # nor does it once the young generation is this large
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
        self._holds = {}                    # token -> monotonic start (see module docstring)
        self._holds_lock = threading.Lock()
        self._next_hold = 0
        self.deferred = 0                   # due young collections deferred by a hold
        self.forced = 0                     # due collections run although a hold was active
        self.boundary_checks = 0            # GUI-thread "collect what is due" before a hold
        self.frozen = 0                     # objects moved to the permanent generation at start-up
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
            self.reenabled += 1
            gc.disable()    # automatic collection stays off (module docstring)
            logger.warning("Automatic garbage collection was re-enabled by other code; disabled again")
        if self.worker_collections != self._reported:
            self._reported = self.worker_collections
            logger.warning("A garbage collection ran off the GUI thread (%d so far)", self.worker_collections)
        count0 = gc.get_count()[0]
        if count0 > self.threshold[0] and self._deferring(count0):
            self.deferred += 1
            return
        self._collect_due()

    def _collect_due(self) -> None:
        """The M50 rule: collect each generation whose threshold is exceeded (GUI thread only)."""
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

    # ---- M52 scheduling --------------------------------------------------------------------------
    def hold(self) -> int:
        """A worker starts building a large transient heap: defer young collections (bounded).

        Called on the GUI thread, it first collects what is due - the previous
        cycle's garbage, while it is small and before the new worker's heap
        exists.  Without this, back-to-back holds left no hold-free collector
        tick and the garbage of many cycles was collected in one long pause
        (M52, 1k synthetic rows: 150k objects, 58-99 ms).
        """
        if threading.current_thread() is self._gui_thread:
            self.boundary_checks += 1
            self._collect_due()
        with self._holds_lock:
            self._next_hold += 1
            self._holds[self._next_hold] = time.monotonic()
            return self._next_hold

    def release(self, token) -> None:
        """Thread-safe and idempotent; an unknown token is ignored."""
        with self._holds_lock:
            self._holds.pop(token, None)

    def active_holds(self) -> int:
        with self._holds_lock:
            return len(self._holds)

    def _deferring(self, count0) -> bool:
        with self._holds_lock:
            if not self._holds:
                return False
            oldest = min(self._holds.values())
        if (time.monotonic() - oldest) * 1000.0 < DEFER_MAX_MS and count0 < DEFER_MAX_YOUNG:
            return True
        self.forced += 1
        return False

    def stats(self) -> dict:
        return {"collections": list(self.collections), "worker_collections": self.worker_collections,
                "worker_threads": list(self.worker_threads), "reenabled": self.reenabled,
                "automatic_enabled": gc.isenabled(), "deferred": self.deferred, "forced": self.forced,
                "boundary_checks": self.boundary_checks, "frozen": self.frozen,
                "active_holds": self.active_holds()}

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


def freeze_startup_heap() -> bool:
    """Once, on the GUI thread, after start-up: full collection, then ``gc.freeze()`` (M52).

    The start-up heap (modules, classes, widgets, caches: about 300-400k tracked
    objects) lives as long as the application.  Unfrozen, the first young
    collection promotes it and later generation-1/2 collections traverse it
    again and again (M52: a 98 ms generation-1 collection that freed nothing).
    Frozen objects are skipped by every collection; reference counting still
    frees them.  The full collection right before freezing means no cyclic
    garbage is frozen.  Returns False when not installed, not on the GUI thread
    or already done.
    """
    collector = _collector
    if collector is None or collector.frozen or threading.current_thread() is not collector._gui_thread:
        return False
    gc.collect()
    gc.freeze()
    collector.frozen = gc.get_freeze_count()
    return True


def hold():
    """Token for :meth:`MainThreadGarbageCollector.hold`, or None when the policy is not installed."""
    return _collector.hold() if _collector is not None else None


def release(token) -> None:
    if token is not None and _collector is not None:
        _collector.release(token)


def installed() -> bool:
    return _collector is not None and _collector.timer.isActive() and not gc.isenabled()


def uninstall() -> None:
    """Tests only: restore automatic collection."""
    global _collector
    if _collector is not None:
        if _collector.frozen:
            gc.unfreeze()
        _collector.stop()
        _collector.deleteLater()
        _collector = None
