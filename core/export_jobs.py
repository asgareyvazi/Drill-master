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
  (``mode=ro``) instead of a connection from the application's pool, so a
  background read can never write.
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
from collections import OrderedDict
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


def shares_single_connection(db_manager) -> bool:
    """True when the manager's engine is one shared connection (in-memory tests).

    ``StaticPool`` (the explicit in-memory engine) hands every session the same
    DB-API connection; ``SingletonThreadPool`` (SQLAlchemy's default for a bare
    ``sqlite://`` engine) gives each thread a *different* empty database. A
    worker thread must not query either; callers run such reads on the
    calling thread instead (M47).
    """
    from sqlalchemy.pool import SingletonThreadPool, StaticPool

    pool = getattr(getattr(db_manager, "engine", None), "pool", None)
    return isinstance(pool, (StaticPool, SingletonThreadPool))


def has_isolated_reader(db_manager) -> bool:
    """True when :func:`worker_database` gives a worker its own connection.

    In-memory databases (tests) share one ``StaticPool`` connection; a worker
    thread must not query it, so callers run such reads synchronously.
    File-backed managers use a real pool (M47); the worker view adds the
    ``mode=ro`` guarantee that a background read can never write.
    """
    path = getattr(db_manager, "db_path", None)
    engine = getattr(db_manager, "engine", None)
    database = getattr(getattr(engine, "url", None), "database", None)
    if not path or path == ":memory:" or not database or database == ":memory:":
        return False
    if getattr(db_manager, "Session", None) is None:
        return False
    from pathlib import Path
    # A manager whose engine is not the configured file (e.g. a test manager
    # over an in-memory engine) must not be redirected to a different file.
    return Path(database).expanduser().resolve() == Path(path).expanduser().resolve()


@contextmanager
def worker_database(db_manager):
    """Yield a manager view with its own read-only connection for a worker."""
    path = getattr(db_manager, "db_path", None)
    if not has_isolated_reader(db_manager):
        if shares_single_connection(db_manager) and threading.current_thread() is not threading.main_thread():
            # Fail closed: on a shared in-memory connection this read would run
            # inside (and reset) the UI thread's transaction (M46 H1).
            raise RuntimeError("an in-memory database cannot be read from a worker thread")
        yield db_manager
        return

    from sqlalchemy.orm import sessionmaker

    # Each worker gets its own Engine object (M47 ownership) that shares the
    # per-file engine's dialect and compiled-statement cache; NullPool still
    # gives every checkout a fresh read-only connection.
    engine = _read_only_engine(db_manager, path).execution_options(drillmaster_worker_view=True)
    view = copy.copy(db_manager)
    view.engine = engine
    view.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                                info=dict(db_manager.Session.kw.get("info") or {}))
    yield view


# One read-only engine per database file and maintenance gate (M52).  An engine
# holds SQLAlchemy's compiled-statement cache; a new engine per worker (M47)
# recompiled every query of every background read and left the compilation
# objects as cyclic garbage (about 120k objects per 4 Analysis refreshes at 1k
# synthetic rows), which the GUI-thread collector then had to traverse.  The
# engine keeps NullPool - every checkout opens a fresh ``mode=ro`` connection
# through the gate, nothing is pooled - so sharing it between worker threads is
# safe and a restore still refuses and counts every connection.
_ENGINE_CACHE_SIZE = 8
_read_only_engines = OrderedDict()
_read_only_engines_lock = threading.Lock()


def _read_only_engine(db_manager, path):
    from pathlib import Path

    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    from core import db_maintenance, sqlite_connection

    gate = getattr(db_manager, "_maintenance_gate", None)
    key = (str(Path(path).expanduser().resolve()), id(gate))
    with _read_only_engines_lock:
        entry = _read_only_engines.get(key)
        if entry is not None and entry[0] is gate:
            _read_only_engines.move_to_end(key)
            return entry[1]

        def open_read_only():
            # Restore refuses the connection itself, not only the checkout, and
            # counts it while it is being opened (M47).
            if gate is None:
                return sqlite_connection.connect(path, read_only=True)
            with gate.connecting():
                return sqlite_connection.connect(path, read_only=True)

        engine = create_engine("sqlite://", creator=open_read_only, poolclass=NullPool, hide_parameters=True)
        if gate is not None:
            db_maintenance.watch_engine(gate, engine)
        _read_only_engines[key] = (gate, engine)
        while len(_read_only_engines) > _ENGINE_CACHE_SIZE:
            _old_key, (_old_gate, old_engine) = _read_only_engines.popitem(last=False)
            old_engine.dispose()            # NullPool: nothing pooled; releases dialect state only
        return engine
