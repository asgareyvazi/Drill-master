"""D46 probe: what the M122 CPU-load body does besides the lifecycle it asserts.

Runs the real ``_cpu_load_body`` (4 GIL burners, 15 cancel cycles, unchanged bounds and assertions) with
counters around ``KnowledgeIndex.__init__`` and ``read_corpus``: index builds, the largest number of
builds running at once, corpus reads on the GUI thread and their time, and the body's wall time.

Not collected by the suite (the name does not match ``test_*.py``).  Run it explicitly::

    QT_QPA_PLATFORM=offscreen python -m pytest -p no:cacheprovider -s --rootdir tools/quality \\
        tools/quality/d46_load_body_probe.py

It prints one ``D46 LOAD PROBE {...}`` line.  SYNTHETIC data only (the M49 corpus).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_m122_assistant_worker_lifecycle import _cpu_load_body, app, world  # noqa: E402,F401

from core import knowledge_retrieval as kr  # noqa: E402


def test_d46_load_body_probe(app, world, monkeypatch):  # noqa: F811
    stats = {"index_builds": 0, "build_s": [], "concurrent_builds_max": 0, "gui_thread_corpus_reads": 0,
             "gui_thread_corpus_read_s": 0.0}
    lock, live = threading.Lock(), [0]
    real_init, real_read = kr.KnowledgeIndex.__init__, kr.read_corpus

    def init(self, *args, **kwargs):
        with lock:
            stats["index_builds"] += 1
            live[0] += 1
            stats["concurrent_builds_max"] = max(stats["concurrent_builds_max"], live[0])
        started = time.monotonic()
        try:
            real_init(self, *args, **kwargs)
        finally:
            with lock:
                live[0] -= 1
                stats["build_s"].append(round(time.monotonic() - started, 3))

    def read(*args, **kwargs):
        started = time.monotonic()
        snapshot = real_read(*args, **kwargs)
        if threading.current_thread() is threading.main_thread():
            stats["gui_thread_corpus_reads"] += 1
            stats["gui_thread_corpus_read_s"] += time.monotonic() - started
        return snapshot

    monkeypatch.setattr(kr.KnowledgeIndex, "__init__", init)
    monkeypatch.setattr(kr, "read_corpus", read)
    started = time.monotonic()
    _cpu_load_body(app, world)
    stats["body_s"] = round(time.monotonic() - started, 1)
    stats["gui_thread_corpus_read_s"] = round(stats["gui_thread_corpus_read_s"], 2)
    print("D46 LOAD PROBE " + json.dumps(stats))
    assert stats["index_builds"] >= 1
