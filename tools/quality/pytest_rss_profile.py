"""Opt-in pytest plugin: per-test memory profile of the long-lived pytest process (M234, D74).

Usage (never loaded by default)::

    DRILLMASTER_RSS_PROFILE=/path/profile.csv PYTHONPATH=tools/quality \\
        python -m pytest -p pytest_rss_profile ...

One CSV row per test, written around the whole runtest protocol (setup + call + teardown, so a module-scoped
fixture's teardown is charged to the module's last test):

* ``rss_anon_kb`` / ``rss_file_kb`` / ``rss_shmem_kb`` from ``/proc/self/status`` - anonymous memory (Python heap,
  Qt / native allocations) is kept apart from file-backed mappings (shared libraries, mmapped files), which the
  kernel can drop under pressure;
* ``widgets`` - ``len(QApplication.allWidgets())`` once Qt is loaded (live widgets, including hidden top-levels);
* ``threads`` - ``threading.active_count()``; ``fds`` - open file descriptors;
* ``gc_objects`` - ``len(gc.get_objects())`` every ``DRILLMASTER_RSS_PROFILE_GC_EVERY`` tests (default 50) and at
  every module boundary, else empty (it is expensive on a large heap).

It only reads; it never collects garbage, deletes widgets or changes the session's GC policy, so the profile
describes the suite as it normally runs. Linux only (``/proc``); elsewhere it does nothing.
"""
from __future__ import annotations

import csv
import gc
import os
import sys
import threading
import time

import pytest

_FIELDS = ("index", "nodeid", "module", "seconds", "rss_anon_kb", "rss_file_kb", "rss_shmem_kb",
           "d_anon_kb", "widgets", "d_widgets", "threads", "fds", "gc_objects")


def _status() -> dict:
    values = {}
    try:
        with open("/proc/self/status", encoding="ascii") as handle:
            for line in handle:
                key, _, rest = line.partition(":")
                if key in ("RssAnon", "RssFile", "RssShmem"):
                    values[key] = int(rest.split()[0])
    except OSError:
        pass
    return values


def _widgets():
    if "PySide6.QtWidgets" not in sys.modules:
        return ""
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is None:
        return ""
    return len(QApplication.allWidgets())


def _fds():
    try:
        return len(os.listdir("/proc/self/fd"))
    except OSError:
        return ""


class _Profile:
    def __init__(self, path: str, gc_every: int):
        self.handle = open(path, "w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.handle)
        self.writer.writerow(_FIELDS)
        self.gc_every = max(1, gc_every)
        self.index = 0
        self.module = None

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        before = _status()
        widgets_before = _widgets()
        start = time.perf_counter()
        yield
        seconds = time.perf_counter() - start
        after = _status()
        widgets_after = _widgets()
        module = item.nodeid.split("::", 1)[0]
        boundary = nextitem is None or nextitem.nodeid.split("::", 1)[0] != module
        self.index += 1
        objects = len(gc.get_objects()) if boundary or self.index % self.gc_every == 0 else ""
        d_widgets = (widgets_after - widgets_before
                     if isinstance(widgets_after, int) and isinstance(widgets_before, int) else "")
        self.writer.writerow([self.index, item.nodeid, module, f"{seconds:.3f}", after.get("RssAnon", ""),
                              after.get("RssFile", ""), after.get("RssShmem", ""),
                              after.get("RssAnon", 0) - before.get("RssAnon", 0), widgets_after, d_widgets,
                              threading.active_count(), _fds(), objects])
        self.handle.flush()

    def pytest_unconfigure(self, config):
        self.handle.close()


def pytest_configure(config):
    path = os.environ.get("DRILLMASTER_RSS_PROFILE")
    if not path or not os.path.isdir("/proc/self"):
        return
    gc_every = int(os.environ.get("DRILLMASTER_RSS_PROFILE_GC_EVERY", "50"))
    config.pluginmanager.register(_Profile(path, gc_every), "drillmaster-rss-profile")
