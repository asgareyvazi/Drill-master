"""Export Center jobs: Qt-free planning and execution (M43 closure).

The Export Center used to generate every file on the UI thread and kept the
window alive with ``QApplication.processEvents()``, which re-entered the
event loop (a second click started a second export) and froze the UI during
long batch exports. Report generation now runs in a worker thread
(``core.async_workers.ExportWorker``); this module holds the parts that do
not need Qt so they can be tested directly.

Contract
--------
* Jobs carry plain identifiers, paths and arguments only. No ORM object or
  session crosses a thread boundary.
* ``worker_database`` gives the worker its own *read-only* SQLite connection
  (``mode=ro``) instead of the application's shared ``StaticPool``
  connection, which the UI thread may be using inside its own transaction.
  The connection is registered with the restore maintenance gate, so a
  restore drains and refuses it like any other connection, and the
  authorization state is carried over, so the global session hooks apply.
  An in-memory database (tests) cannot be opened twice; the manager itself
  is used then.
* ``run_jobs`` records every job as ``ok`` / ``failed`` (the generator
  returned false) / ``error`` (it raised; only the exception type is kept,
  never its message, which may quote report data) / ``cancelled``.
  Cancellation is checked *between* files: a file that is being written is
  finished, never abandoned half-way.
* File names are the ones the Export Center has always produced.
"""

from __future__ import annotations

import copy
import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

EXTENSIONS: Dict[str, str] = {"pdf": ".pdf", "html": ".html", "excel": ".xlsx"}

# Batch order (unchanged): professional pair, then EOWR, NPT, Cost, Plan, DDRs.
BATCH_KINDS: Tuple[str, ...] = ("professional", "eowr", "npt", "cost", "plan", "ddr")

STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"


def extension_for(fmt: str) -> str:
    return EXTENSIONS.get(fmt, ".pdf")


@dataclass(frozen=True)
class ExportJob:
    kind: str
    label: str
    path: str
    target_id: int
    fmt: str = "pdf"
    args: Tuple[Any, ...] = ()
    report_id: Optional[int] = None
    watermark: Optional[str] = None


@dataclass(frozen=True)
class ExportOutcome:
    job: ExportJob
    status: str
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK


@dataclass(frozen=True)
class BatchResult:
    outcomes: Tuple[ExportOutcome, ...]

    @property
    def ok_count(self) -> int:
        return sum(1 for o in self.outcomes if o.ok)

    @property
    def cancelled(self) -> bool:
        return any(o.status == STATUS_CANCELLED for o in self.outcomes)

    @property
    def problems(self) -> Tuple[ExportOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status in (STATUS_FAILED, STATUS_ERROR))


def _report_engine(class_name: str) -> Callable[[Any, ExportJob], Any]:
    def generate(db, job: ExportJob):
        from core import report_engine

        engine = getattr(report_engine, class_name)(db)
        if job.watermark is not None:
            engine.branding.watermark = job.watermark
        return engine.generate(job.target_id, job.path, job.fmt, *job.args)

    return generate


def _professional(class_name: str) -> Callable[[Any, ExportJob], Any]:
    def generate(db, job: ExportJob):
        from core import professional_export

        exporter = getattr(professional_export, class_name)(db)
        return exporter.export(job.target_id, job.path, report_id=job.report_id)

    return generate


GENERATORS: Dict[str, Callable[[Any, ExportJob], Any]] = {
    "ddr": _report_engine("DDRReportEngine"),
    "eowr": _report_engine("EOWRReportEngine"),
    "npt": _report_engine("NPTReportEngine"),
    "cost": _report_engine("CostReportEngine"),
    "plan": _report_engine("PlanReportEngine"),
    "professional_excel": _professional("ProfessionalExcelExport"),
    "professional_pdf": _professional("ProfessionalPDFExport"),
}


def plan_batch(
    *,
    well_id: int,
    folder: str,
    fmt: str,
    timestamp: str,
    selected: Iterable[str],
    report_id: Optional[int] = None,
    ddr_reports: Sequence[Mapping[str, Any]] = (),
) -> List[ExportJob]:
    """Batch jobs in the historical order with the historical file names."""
    import os

    chosen = set(selected)
    unknown = chosen - set(BATCH_KINDS)
    if unknown:
        raise ValueError(f"unknown batch export kind(s): {sorted(unknown)}")
    ext = extension_for(fmt)
    jobs: List[ExportJob] = []
    if "professional" in chosen:
        jobs.append(ExportJob("professional_excel", "Professional Excel (16 sheets)",
                              os.path.join(folder, f"Professional_16Sheets_{timestamp}.xlsx"),
                              well_id, "excel", report_id=report_id))
        jobs.append(ExportJob("professional_pdf", "Professional PDF",
                              os.path.join(folder, f"Professional_{timestamp}.pdf"),
                              well_id, "pdf", report_id=report_id))
    for kind, label, stem in (("eowr", "EOWR", "EOWR"), ("npt", "NPT", "NPT"),
                              ("cost", "Cost", "Cost"), ("plan", "Plan", "Plan")):
        if kind in chosen:
            jobs.append(ExportJob(kind, label, os.path.join(folder, f"{stem}_{timestamp}{ext}"), well_id, fmt))
    if "ddr" in chosen:
        for report in ddr_reports:
            name = f"DDR_{report.get('report_number', '')}_{report.get('report_date', '')}{ext}"
            jobs.append(ExportJob("ddr", f"DDR #{report.get('report_number', '')}",
                                  os.path.join(folder, name), int(report["id"]), fmt))
    return _without_path_collisions(jobs)


def _without_path_collisions(jobs: List[ExportJob]) -> List[ExportJob]:
    """Never let one batch file overwrite another (e.g. two DDRs, same number and date)."""
    import os
    from dataclasses import replace

    seen: set = set()
    unique: List[ExportJob] = []
    for job in jobs:
        path = job.path
        if os.path.normcase(path) in seen:
            stem, ext = os.path.splitext(job.path)
            path = f"{stem}_id{job.target_id}{ext}"
            suffix = 2
            while os.path.normcase(path) in seen:
                path = f"{stem}_id{job.target_id}_{suffix}{ext}"
                suffix += 1
            job = replace(job, path=path)
        seen.add(os.path.normcase(path))
        unique.append(job)
    return unique


def run_jobs(
    db,
    jobs: Sequence[ExportJob],
    *,
    progress: Optional[Callable[[int, int, ExportOutcome], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> BatchResult:
    """Run jobs in order; one job's failure never stops the others."""
    outcomes: List[ExportOutcome] = []
    total = len(jobs)
    for index, job in enumerate(jobs):
        if cancel_event is not None and cancel_event.is_set():
            outcomes.extend(ExportOutcome(j, STATUS_CANCELLED) for j in jobs[index:])
            break
        generator = GENERATORS.get(job.kind)
        if generator is None:
            raise ValueError(f"unknown export kind: {job.kind!r}")
        try:
            outcome = ExportOutcome(job, STATUS_OK if generator(db, job) else STATUS_FAILED)
        except Exception as exc:
            logger.warning("Export %s failed: %s", job.kind, type(exc).__name__)
            outcome = ExportOutcome(job, STATUS_ERROR, type(exc).__name__)
        outcomes.append(outcome)
        if progress is not None:
            progress(index + 1, total, outcome)
    return BatchResult(tuple(outcomes))


@contextmanager
def worker_database(db_manager):
    """Yield a manager view with its own read-only connection for a worker."""
    path = getattr(db_manager, "db_path", None)
    if not path or path == ":memory:" or getattr(db_manager, "Session", None) is None:
        yield db_manager
        return

    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    from core import sqlite_connection

    engine = create_engine(
        "sqlite://",
        creator=lambda: sqlite_connection.connect(path, read_only=True),
        poolclass=NullPool,
        hide_parameters=True,
    )
    gate = getattr(db_manager, "_maintenance_gate", None)
    if gate is not None:
        event.listen(engine, "checkout", gate.on_checkout)
        event.listen(engine, "checkin", gate.on_checkin)
    view = copy.copy(db_manager)
    view.engine = engine
    view.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                                info=dict(db_manager.Session.kw.get("info") or {}))
    try:
        yield view
    finally:
        engine.dispose()
