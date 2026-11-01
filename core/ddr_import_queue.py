"""M61: DDR batch import queue (pure Python, no Qt, no database objects).

The queue is the single source of truth for a batch: which files were added,
their current status and pipeline stage, the report profile used, per-file
diagnostics and the final result. The import dialog renders it and drives it;
persistence stays per-file and atomic in ``DDRImportService``.

Statuses are deliberately distinct so a summary can never collapse a user
cancel, a duplicate source and a database failure into one "failed" count.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

QUEUE_VERSION = 2   # M70.6: re-add/twin/changed-file/cancel-running rules

QUEUED = "QUEUED"
RUNNING = "RUNNING"
SAVED = "SAVED"                    # persisted, status ACCEPT
REVIEW_REQUIRED = "REVIEW_REQUIRED"  # persisted with open review items
SKIPPED = "SKIPPED"                # user cancelled the preview for this file
DUPLICATE = "DUPLICATE"            # identical source in this batch or already imported
FAILED = "FAILED"
CANCELLED = "CANCELLED"            # batch cancelled before this file ran

FINAL = {SAVED, REVIEW_REQUIRED, SKIPPED, DUPLICATE, FAILED, CANCELLED}
RETRYABLE = {FAILED, CANCELLED, SKIPPED}
REMOVABLE = {QUEUED, FAILED, CANCELLED, SKIPPED, DUPLICATE}
PERSISTED = {SAVED, REVIEW_REQUIRED}
TWIN_STATUSES = {QUEUED, RUNNING, SAVED, REVIEW_REQUIRED}   # a skipped/failed twin imported nothing
ATOMIC_STAGES = {"persist", "persistence"}   # the dialog names its stage "persistence"
ORDER = (SAVED, REVIEW_REQUIRED, SKIPPED, DUPLICATE, FAILED, CANCELLED, QUEUED, RUNNING)


def file_fingerprint(path: str) -> Optional[str]:
    """SHA-256 of the file bytes, or ``None`` when the file cannot be read."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:  # silent-ok: unreadable file is reported by the pipeline's open stage
        return None
    return digest.hexdigest()


@dataclass
class QueueEntry:
    path: str
    fingerprint: Optional[str] = None
    status: str = QUEUED
    stage: str = ""
    profile: str = ""
    diagnostics: List[str] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    attempts: int = 0

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


def status_from_result(result: Dict[str, Any]) -> str:
    """Map one pipeline result dict to a queue status."""
    if result.get("reimport"):
        return DUPLICATE
    if result.get("skipped") and not result.get("imported"):
        return SKIPPED
    status = str(result.get("status") or "")
    if status == "ACCEPT":
        return SAVED
    if status == "REVIEW_REQUIRED":
        return REVIEW_REQUIRED
    return FAILED


class ImportQueue:
    def __init__(self) -> None:
        self.entries: List[QueueEntry] = []
        self.cancel_requested = False

    # -- building -------------------------------------------------------
    def add(self, paths: Iterable[str]) -> List[QueueEntry]:
        """Add files. Rules (M70.6):

        * a path that is already queued/running is not added twice;
        * an unreadable/missing file is FAILED at once with the reason;
        * re-adding a FAILED/CANCELLED/SKIPPED file re-queues that entry
          (its history is kept);
        * a SAVED/REVIEW_REQUIRED/DUPLICATE entry is never replaced: a new entry
          is appended, DUPLICATE when its bytes equal a queued, running or
          persisted entry, otherwise QUEUED (changed content is new content).
        """
        added: List[QueueEntry] = []
        for path in paths:
            path = str(path)
            if any(e.path == path and e.status not in FINAL for e in self.entries):
                continue  # already pending
            fingerprint = file_fingerprint(path)
            latest = self.find(path)
            if latest is not None and latest.status in RETRYABLE:
                if latest.fingerprint and fingerprint and latest.fingerprint != fingerprint:
                    latest.diagnostics.append("File content changed since it was first queued.")
                latest.fingerprint = fingerprint
                latest.status, latest.stage, latest.result = QUEUED, "", None
                latest.diagnostics.append("Re-added to the batch.")
                if fingerprint is None:
                    self._unreadable(latest)
                else:
                    self._mark_twin(latest)
                added.append(latest)
                continue
            entry = QueueEntry(path=path, fingerprint=fingerprint)
            if fingerprint is None:
                self._unreadable(entry)
            else:
                if latest is not None and latest.status in PERSISTED and latest.fingerprint != fingerprint:
                    entry.diagnostics.append(f"Content changed since {latest.name} was imported in this batch.")
                self._mark_twin(entry)
            self.entries.append(entry)
            added.append(entry)
        return added

    @staticmethod
    def _unreadable(entry: QueueEntry) -> None:
        entry.status, entry.stage = FAILED, "open"
        entry.diagnostics.append("The source file cannot be read (missing, moved or no permission).")

    def _twin(self, entry: QueueEntry) -> Optional[QueueEntry]:
        return next((e for e in self.entries
                     if e is not entry and entry.fingerprint and e.fingerprint == entry.fingerprint
                     and e.status in TWIN_STATUSES), None)

    def _mark_twin(self, entry: QueueEntry) -> bool:
        twin = self._twin(entry)
        if twin is None:
            return False
        entry.status, entry.stage = DUPLICATE, "fingerprint"
        where = "this file" if twin.path == entry.path else twin.name
        entry.diagnostics.append(f"Same content as {where} ({twin.status.lower()}) in this batch; not imported twice.")
        return True

    def find(self, path: str) -> Optional[QueueEntry]:
        """The most recent entry for ``path``."""
        matches = [e for e in self.entries if e.path == str(path)]
        return matches[-1] if matches else None

    def remove(self, index: int) -> bool:
        """Remove a non-running, non-persisted entry; completed results are kept."""
        if not 0 <= index < len(self.entries) or self.entries[index].status not in REMOVABLE:
            return False
        del self.entries[index]
        return True

    def retry(self, index: Optional[int] = None) -> List[QueueEntry]:
        """Re-queue one entry (or every retryable entry when ``index`` is None)."""
        targets = self.entries if index is None else self.entries[index:index + 1]
        out = []
        for entry in targets:
            if entry.status in RETRYABLE:
                entry.status, entry.stage, entry.result = QUEUED, "", None
                entry.diagnostics.append(f"Retry #{entry.attempts + 1} requested.")
                out.append(entry)
        if out:
            self.cancel_requested = False
        return out

    def cancel(self) -> int:
        """Cancel every file that has not started; the running file finishes atomically."""
        self.cancel_requested = True
        count = 0
        for entry in self.entries:
            if entry.status == QUEUED:
                entry.status, entry.stage = CANCELLED, "cancelled before start"
                count += 1
        return count

    # -- running --------------------------------------------------------
    def pending(self) -> List[QueueEntry]:
        return [e for e in self.entries if e.status == QUEUED]

    def start(self, entry: QueueEntry, profile: str = "") -> bool:
        """Begin a file. The bytes are fingerprinted again: a file that vanished
        is FAILED, a file that changed into a copy of an imported one is
        DUPLICATE. Returns whether the file should run."""
        current = file_fingerprint(entry.path)
        if current is None:
            self._unreadable(entry)
            return False
        if entry.fingerprint and current != entry.fingerprint:
            entry.diagnostics.append("File content changed after it was queued; the current content is used.")
        entry.fingerprint = current
        if self._mark_twin(entry):
            return False
        entry.status, entry.stage, entry.profile = RUNNING, "route", profile
        entry.attempts += 1
        return True

    def set_stage(self, entry: QueueEntry, stage: str) -> None:
        if entry.status == RUNNING:
            entry.stage = stage

    def cancel_running(self, entry: QueueEntry) -> bool:
        """Cancel a running file before persistence; during persistence it finishes atomically."""
        if entry.status != RUNNING or entry.stage in ATOMIC_STAGES:
            return False
        entry.status, entry.stage = CANCELLED, f"cancelled during {entry.stage or 'preparation'}"
        entry.diagnostics.append("Cancelled before anything was saved.")
        return True

    def finish(self, entry: QueueEntry, result: Dict[str, Any]) -> str:
        if entry.status == CANCELLED and not result.get("imported"):
            entry.result = result
            return entry.status          # cancelled mid-preparation: keep the cancel, nothing was saved
        entry.result = result
        entry.status = status_from_result(result)
        entry.stage = "done"
        details = result.get("details") or []
        if details:
            entry.diagnostics.append(str(details[-1]))
        return entry.status

    # -- reporting ------------------------------------------------------
    def counts(self) -> Dict[str, int]:
        out = {status: 0 for status in ORDER}
        for entry in self.entries:
            out[entry.status] = out.get(entry.status, 0) + 1
        return out

    def summary_text(self) -> str:
        counts = self.counts()
        head = f"Batch: {len(self.entries)} file(s) — " + ", ".join(
            f"{status.replace('_', ' ').lower()} {counts[status]}" for status in ORDER if counts[status]
        )
        lines = [head]
        for entry in self.entries:
            note = entry.diagnostics[-1] if entry.diagnostics else ""
            lines.append(f"{entry.status:<15} {entry.name}" + (f" — {note}" if note else ""))
        return "\n".join(lines)
