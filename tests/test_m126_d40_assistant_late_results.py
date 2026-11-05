"""D40 (found by CI on f790f40, Python 3.12): a Knowledge Assistant result queued before ``cleanup()`` was
delivered after it and shown on the closed panel.

``_stop_worker`` cancelled before disconnecting, so the worker could emit ``done("cancelled")`` first; a
queued delivery is not retracted by ``disconnect()``, and ``cleanup()`` - unlike ``cancel()`` - left the answer
generation valid. The fix is an explicit closed state checked by every result slot (worker references are
still released exactly as before). These tests deliver late results deterministically: a real queued signal
emitted before cleanup, and each other slot called after it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402

import test_m49_knowledge_ui as m49  # noqa: E402
from m49_fake_ollama import FakeOllama  # noqa: E402
from test_m122_assistant_worker_lifecycle import _flush, _generating  # noqa: E402

app = m49.app
world = m49.world


class _Emitter(QObject):
    done = Signal(int, object, object)


def test_an_answer_queued_before_cleanup_is_not_shown_after_it(app, world):
    _tab, panel, _ids, _db = world
    with FakeOllama(hold_after_first=20.0) as fake:
        _generating(app, panel, fake)
        late = _Emitter()
        late.done.connect(panel._worker_done, Qt.QueuedConnection)
        late.done.emit(panel._generation, "a late answer for the closed panel", None)   # queued, not delivered
        panel.cleanup()
        state = panel.current_state
        _flush(app)
    assert panel.last_answer is None and panel.last_error is None and panel.current_state == state


def test_every_other_result_slot_ignores_results_after_cleanup(app, world, monkeypatch):
    _tab, panel, _ids, _db = world
    applied = []
    monkeypatch.setattr(panel, "apply_model_status", lambda status: applied.append("status"))
    monkeypatch.setattr(panel, "_apply_choices", lambda *a: applied.append("choices"))
    monkeypatch.setattr(panel, "_apply_library_signature", lambda sig: applied.append("library"))
    panel.cleanup()
    label = panel.semantic_label.text()
    index_before = panel._index
    panel._status_done(getattr(panel, "_generation_status", 0), object())
    panel._choices_read(panel._choices_token["reports"], "reports", [], None)
    panel._corpus_checked(panel._check_token, "SYN signature", None)
    panel._semantic_done({"state": "complete", "total": 3, "done": 3})
    panel._semantic_progress(1, 3)
    panel._semantic_indexed(type("SynIndex", (), {"signature": "SYN"})())
    panel._worker_stage(panel._generation, "generating")
    assert applied == [] and panel.semantic_label.text() == label and panel._index is index_before
    assert panel.current_state != "generating"


def test_the_same_slots_still_apply_results_while_the_panel_is_open(app, world, monkeypatch):
    """The guard is the closed state, not a blanket refusal."""
    _tab, panel, _ids, _db = world
    applied = []
    monkeypatch.setattr(panel, "apply_model_status", lambda status: applied.append("status"))
    monkeypatch.setattr(panel, "_apply_choices", lambda *a: applied.append("choices"))
    monkeypatch.setattr(panel, "_apply_library_signature", lambda sig: applied.append("library"))
    panel._status_done(getattr(panel, "_generation_status", 0), object())
    panel._choices_read(panel._choices_token["reports"], "reports", [], None)
    panel._corpus_checked(panel._check_token, "SYN signature", None)
    panel._semantic_progress(1, 3)
    assert applied == ["status", "choices", "library"] and "1/3" in panel.semantic_label.text()
