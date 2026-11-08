"""D46 (M140 follow-up): the knowledge index build is cancellable, and a cancelled question keeps its index.

Two product behaviours made the M122 CPU-load cancel cycles far heavier than the lifecycle they test:

* ``KnowledgeIndex(...)`` had no cancellation checkpoint - a worker cancelled during the build finished an
  index nobody waited for, beside the next question's build (two CPU-bound Python threads; with the test's
  GIL burners every GIL re-acquisition of the GUI thread then waited behind them);
* ``cancel()`` disconnects the worker (D40), so the index it built never reached the panel - every cancelled
  question made the next one read the corpus (on the GUI thread for an in-memory database) and build the
  index again, although the corpus had not changed (15 builds and 15 GUI-thread reads in 15 cycles).

Measured on the real load body (4 burners, unchanged bounds and assertions): 15 -> 1 index builds,
15 -> 1 GUI-thread corpus reads, 21-23 s -> 10-11 s, still 15/15 cancels on a live worker.

The ANSWER of a cancelled question is still never accepted (M122/D28); only the corpus index is adopted,
under the rules of ``KnowledgeAssistantPanel._retired_worker_done``.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402

import test_m122_assistant_worker_lifecycle as m122  # noqa: E402
from core import knowledge_retrieval as kr  # noqa: E402
from core import local_llm as ll  # noqa: E402
from m49_fake_ollama import FakeOllama  # noqa: E402
from m49_knowledge_fixtures import corpus_db  # noqa: E402
from tabs import knowledge_assistant as kat  # noqa: E402

app = m122.app
world = m122.world


@pytest.fixture
def snapshot():
    db, _ids = corpus_db()
    try:
        yield kr.read_corpus(db)
    finally:
        db.engine.dispose()


class _CountingCancel:
    """``cancelled()`` answers False ``after`` times, then True; counts every poll."""

    def __init__(self, after):
        self.after, self.calls = after, 0

    def __call__(self):
        self.calls += 1
        return self.calls > self.after


def _track_connections(monkeypatch):
    opened = []
    real_connect = sqlite3.connect

    def connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection
    monkeypatch.setattr(kr.sqlite3, "connect", connect)
    return opened


def _is_closed(connection):
    try:
        connection.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    return False


# ------------------------------------------------------------------ the index build
def test_a_build_cancelled_before_it_starts_raises_and_opens_nothing(snapshot, monkeypatch):
    opened = _track_connections(monkeypatch)
    with pytest.raises(kr.IndexBuildCancelled):
        kr.KnowledgeIndex(snapshot, cancelled=lambda: True)
    assert opened == []


def test_the_build_is_polled_per_page_per_row_and_per_chunk(snapshot):
    probe = _CountingCancel(after=10 ** 9)
    index = kr.KnowledgeIndex(snapshot, cancelled=probe)
    pages, chunks = len(snapshot.pages), len(index.chunks)
    assert chunks > 3 and pages > 1
    # phases (>= 4) + every page + every FTS row + every chunk's trigram vector
    assert probe.calls >= 4 + pages + 2 * chunks, (probe.calls, pages, chunks)


@pytest.mark.parametrize("fraction", [0.0, 0.25, 0.5, 0.75, 0.99])
def test_a_build_cancelled_anywhere_raises_and_leaves_no_open_connection(snapshot, monkeypatch, fraction):
    total = _CountingCancel(after=10 ** 9)
    kr.KnowledgeIndex(snapshot, cancelled=total)
    opened = _track_connections(monkeypatch)
    probe = _CountingCancel(after=int(total.calls * fraction))
    with pytest.raises(kr.IndexBuildCancelled):
        kr.KnowledgeIndex(snapshot, cancelled=probe)
    assert probe.calls == probe.after + 1          # it stopped at the first True, no further work polled
    assert all(_is_closed(c) for c in opened), "a cancelled build left its FTS connection open"


def test_an_uncancelled_build_is_unchanged_and_keeps_no_reference_to_the_token(snapshot):
    plain = kr.KnowledgeIndex(snapshot)
    polled = kr.KnowledgeIndex(snapshot, cancelled=lambda: False)
    assert plain.chunks.keys() == polled.chunks.keys() and plain._df == polled._df
    question = m122.KICK
    assert [h.chunk.chunk_id for h in plain.retrieve(question, kr.SCOPE_ALL, None).hits] == \
        [h.chunk.chunk_id for h in polled.retrieve(question, kr.SCOPE_ALL, None).hits]
    assert polled._checkpoint is kr._no_checkpoint and plain._checkpoint is kr._no_checkpoint
    polled._build_trigrams()                       # a later rebuild of a part never raises
    assert polled._fts is not None and not _is_closed(polled._fts)


# ------------------------------------------------------------------ the workers
class _FlipToken(ll.CancelToken):
    """Not cancelled at the worker's own check; cancelled from the first build checkpoint on."""

    def __init__(self):
        super().__init__()
        self.reads = 0

    @property
    def cancelled(self):
        self.reads += 1
        return self.reads > 1


def test_an_ask_worker_cancelled_inside_the_build_ends_without_emitting(app, snapshot):
    token = _FlipToken()
    worker = kat.AskWorker(1, snapshot, None, m122.KICK, kr.SCOPE_ALL, None, None, False, token)
    seen = []
    worker.done.connect(lambda *a: seen.append(a), Qt.DirectConnection)
    worker.run()                                   # synchronously: the build raises at its first checkpoint
    assert seen == [] and worker.index is None and token.reads >= 2
    worker.deleteLater()


def test_a_semantic_worker_cancelled_inside_the_build_reports_cancelled(app, snapshot, monkeypatch):
    monkeypatch.setattr(kat, "_read_corpus_on_worker", lambda _db: snapshot)

    class Adapter:
        embed_model = "synthetic-embed"
    token = ll.CancelToken()
    token.cancel()
    worker = kat.SemanticBuildWorker(None, Adapter(), None, token, db_manager=object())
    done, indexed = [], []
    worker.done.connect(done.append, Qt.DirectConnection)
    worker.indexed.connect(indexed.append, Qt.DirectConnection)
    worker.run()
    assert done == [{"state": "cancelled", "done": 0, "total": 0}] and indexed == []
    worker.deleteLater()


# ------------------------------------------------------------------ the panel
def _count_builds(monkeypatch):
    builds = []
    real_init = kr.KnowledgeIndex.__init__

    def init(self, *args, **kwargs):
        builds.append(threading.current_thread().name)
        real_init(self, *args, **kwargs)
    monkeypatch.setattr(kr.KnowledgeIndex, "__init__", init)
    return builds


def test_a_cancelled_question_keeps_its_index_but_never_its_answer(app, world, monkeypatch):
    _tab, panel, _ids, _db = world
    builds = _count_builds(monkeypatch)
    with FakeOllama(hold_after_first=20.0) as fake:
        worker = m122._generating(app, panel, fake)
        assert worker is not None and len(builds) == 1
        panel.cancel()
        assert m122._settle(app, lambda: not panel._old_workers, 10)
        assert panel.current_state == "cancelled" and panel.last_answer is None      # the answer: rejected
        assert panel._index is not None and panel._index.signature == panel._snapshot_signature
        m122._generating(app, panel, fake)          # the next question reuses it: no second build
        assert len(builds) == 1, builds
        panel.cancel()
        assert m122._settle(app, lambda: not panel._old_workers, 10)


def _a_built_index(panel):
    return kr.KnowledgeIndex(kr.read_corpus(panel.db_manager))


def test_the_retired_index_is_adopted_only_under_the_rules(app, world):
    _tab, panel, _ids, _db = world
    index = _a_built_index(panel)
    panel._index, panel._snapshot_signature = None, None
    panel._retired_worker_done(0, None, None)                       # nothing delivered
    assert panel._index is None
    panel._retired_worker_done(0, "cancelled", index)               # no known state: adopted
    assert panel._index is index and panel._snapshot_signature == index.signature
    other = _a_built_index(panel)
    panel._retired_worker_done(0, None, other)                      # the panel holds one: never replaced
    assert panel._index is index
    panel._index, panel._snapshot_signature = None, ("another corpus state",)
    panel._retired_worker_done(0, None, other)                      # another corpus state: refused
    assert panel._index is None
    panel._snapshot_signature = other.signature
    panel._closed = True
    try:
        panel._retired_worker_done(0, None, other)                  # after cleanup: refused (D40)
        assert panel._index is None
    finally:
        panel._closed = False


def test_a_cancel_inside_the_build_stops_it_and_adopts_nothing(app, world, monkeypatch):
    _tab, panel, _ids, _db = world
    entered, go = threading.Event(), threading.Event()
    real_chunk_page = kr.chunk_page

    def slow_chunk_page(page):
        entered.set()
        go.wait(10)
        return real_chunk_page(page)
    monkeypatch.setattr(kr, "chunk_page", slow_chunk_page)
    with FakeOllama(hold_after_first=20.0) as fake:
        m122._model_ready(app, panel, fake)
        panel.question_edit.setPlainText(m122.KICK)
        assert panel.ask()
        assert panel.worker is not None
        assert entered.wait(10), "the worker never reached the index build"
        panel.cancel()
        go.set()
        started = time.monotonic()
        assert m122._settle(app, lambda: not panel._old_workers, 10)
        assert time.monotonic() - started < 10
        assert panel.current_state == "cancelled" and panel.last_answer is None
        assert panel._index is None                                  # a cancelled build is never adopted
        monkeypatch.setattr(kr, "chunk_page", real_chunk_page)
        m122._generating(app, panel, fake)                           # the next question builds and generates
        assert panel._index is None or panel._index.signature == panel._snapshot_signature
        panel.cancel()
        assert m122._settle(app, lambda: not panel._old_workers, 10)
