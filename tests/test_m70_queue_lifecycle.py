"""M70.6: DDR batch-queue lifecycle edge cases (pure Python, temporary files)."""
from __future__ import annotations

import os

from core import ddr_import_queue as q


def _file(tmp_path, name, data=b"synthetic DDR"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def _saved(queue, entry):
    assert queue.start(entry)
    return queue.finish(entry, {"status": "ACCEPT", "imported": 1})


def test_re_adding_a_saved_path_never_replaces_the_saved_result(tmp_path):
    queue = q.ImportQueue()
    path = _file(tmp_path, "a.pdf")
    (first,) = queue.add([path])
    assert _saved(queue, first) == q.SAVED
    (again,) = queue.add([path])
    assert again is not first and first.status == q.SAVED and first.result == {"status": "ACCEPT", "imported": 1}
    assert again.status == q.DUPLICATE and "Same content as this file (saved)" in again.diagnostics[-1]
    assert queue.counts()[q.SAVED] == 1 and queue.counts()[q.DUPLICATE] == 1 and len(queue.entries) == 2


def test_a_changed_file_re_added_after_save_is_new_content(tmp_path):
    queue = q.ImportQueue()
    path = _file(tmp_path, "a.pdf")
    (first,) = queue.add([path])
    _saved(queue, first)
    _file(tmp_path, "a.pdf", b"different synthetic DDR")
    (again,) = queue.add([path])
    assert again.status == q.QUEUED and "Content changed since a.pdf was imported" in again.diagnostics[-1]
    assert first.status == q.SAVED


def test_a_different_path_with_identical_bytes_is_a_duplicate_of_a_saved_file(tmp_path):
    queue = q.ImportQueue()
    a, b = _file(tmp_path, "a.pdf"), _file(tmp_path, "copy.pdf")
    (first,) = queue.add([a])
    _saved(queue, first)
    (twin,) = queue.add([b])
    assert twin.status == q.DUPLICATE and "a.pdf (saved)" in twin.diagnostics[-1]


def test_a_skipped_or_failed_twin_does_not_block_the_other_copy(tmp_path):
    queue = q.ImportQueue()
    a, b = _file(tmp_path, "a.pdf"), _file(tmp_path, "copy.pdf")
    (first,) = queue.add([a])
    queue.start(first)
    queue.finish(first, {"skipped": 1, "imported": 0})
    assert first.status == q.SKIPPED
    (other,) = queue.add([b])
    assert other.status == q.QUEUED


def test_retry_of_failed_and_cancelled_files_and_repeated_retry(tmp_path):
    queue = q.ImportQueue()
    a, b = _file(tmp_path, "a.pdf", b"1"), _file(tmp_path, "b.pdf", b"2")
    first, second = queue.add([a, b])
    queue.start(first)
    queue.finish(first, {"status": "PERSISTENCE_ERROR", "imported": 0})
    assert queue.cancel() == 1 and second.status == q.CANCELLED and second.stage == "cancelled before start"
    for attempt in (2, 3):
        assert {e.path for e in queue.retry()} == {a, b}
        assert queue.start(first) and queue.start(second)
        queue.finish(first, {"status": "PERSISTENCE_ERROR", "imported": 0})
        queue.finish(second, {"status": "PERSISTENCE_ERROR", "imported": 0})
        assert first.attempts == attempt and second.attempts == attempt - 1
    assert queue.counts()[q.FAILED] == 2
    assert queue.retry(index=0) == [first] and second.status == q.FAILED


def test_re_adding_a_failed_path_requeues_the_same_entry_with_its_history(tmp_path):
    queue = q.ImportQueue()
    path = _file(tmp_path, "a.pdf")
    (entry,) = queue.add([path])
    queue.start(entry)
    queue.finish(entry, {"status": "PERSISTENCE_ERROR", "imported": 0, "details": ["boom"]})
    (again,) = queue.add([path])
    assert again is entry and entry.status == q.QUEUED and "boom" in entry.diagnostics
    assert entry.diagnostics[-1] == "Re-added to the batch." and len(queue.entries) == 1


def test_an_unreadable_or_deleted_source_fails_with_the_reason(tmp_path):
    queue = q.ImportQueue()
    (missing,) = queue.add([str(tmp_path / "missing.pdf")])
    assert missing.status == q.FAILED and "cannot be read" in missing.diagnostics[-1]
    path = _file(tmp_path, "a.pdf")
    (entry,) = queue.add([path])
    os.remove(path)
    assert queue.start(entry) is False and entry.status == q.FAILED and entry.attempts == 0


def test_a_file_changed_after_fingerprinting_is_rechecked_at_start(tmp_path):
    queue = q.ImportQueue()
    a, b = _file(tmp_path, "a.pdf", b"one"), _file(tmp_path, "b.pdf", b"two")
    first, second = queue.add([a, b])
    _saved(queue, first)
    _file(tmp_path, "b.pdf", b"one")                       # now a copy of the imported file
    assert queue.start(second) is False and second.status == q.DUPLICATE
    assert "changed after it was queued" in second.diagnostics[-2]
    third = queue.add([_file(tmp_path, "c.pdf", b"three")])[0]
    _file(tmp_path, "c.pdf", b"three, edited")
    assert queue.start(third) is True and "changed after it was queued" in third.diagnostics[-1]


def test_cancel_during_preparation_but_never_during_persistence(tmp_path):
    queue = q.ImportQueue()
    a, b = _file(tmp_path, "a.pdf", b"1"), _file(tmp_path, "b.pdf", b"2")
    first, second = queue.add([a, b])
    queue.start(first)
    queue.set_stage(first, "mapping")
    assert queue.cancel_running(first) is True
    assert first.status == q.CANCELLED and first.stage == "cancelled during mapping"
    assert queue.finish(first, {"status": "CANCELLED", "imported": 0}) == q.CANCELLED   # late result keeps cancel
    queue.start(second)
    queue.set_stage(second, "persistence")
    assert queue.cancel_running(second) is False and second.status == q.RUNNING
    assert queue.finish(second, {"status": "ACCEPT", "imported": 1}) == q.SAVED
    assert queue.remove(1) is False and queue.counts() == {**{s: 0 for s in q.ORDER}, q.SAVED: 1, q.CANCELLED: 1}


def test_a_pending_path_is_not_added_twice_and_counts_add_up(tmp_path):
    queue = q.ImportQueue()
    a = _file(tmp_path, "a.pdf")
    queue.add([a, a])
    assert len(queue.entries) == 1
    assert sum(queue.counts().values()) == len(queue.entries)
