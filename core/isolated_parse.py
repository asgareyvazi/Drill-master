"""M111: DDR file parsing in an isolated ``spawn`` process.

The read-only preparation of one DDR source file (``core.ddr_import_pipeline.prepare_import``: routing,
workbook extraction, the PDF-native fallback, profile rules, validation) runs in a child process started
with the ``spawn`` method.  The boundary rules:

* Only plain data crosses it in both directions (``is_plain``): profiles go in as dictionaries, the
  prepared result comes back as a dictionary.  No session, ORM object, widget, Qt object or callable.
* The child never opens the database.  Preview, the user's decision and persistence stay in the parent
  (``dialogs.excel_import_dialog``), exactly as before.
* Identity: the parent fingerprints the file (SHA-256) before the child starts; the child checks the same
  fingerprint before parsing and again after parsing; the parent checks once more after the result has
  arrived.  Any difference discards the result (``IDENTITY_CHANGED``).
* Cancel: the parent sets a cancel event (honoured by the child between steps), stops waiting at once and
  discards any late result, so a cancelled file can never reach the save path.
* Bounded shutdown: ``join(grace)`` -> ``terminate()`` -> ``join(grace)`` -> ``kill()`` -> ``join(grace)``.
  Every child is also a daemon and is registered for ``shutdown_all`` at interpreter exit: no orphans.
* A parse that does not finish within ``timeout`` seconds is stopped (``TIMEOUT``); a child that dies
  without a result is ``CRASHED``; a non-plain result is ``NOT_PLAIN``.  None of them is ever saved.

Scope (honest): only the production parsers are isolated.  Callables injected into the dialog (tests,
plugins) cannot be sent to another process and keep running in the M71 worker thread; a successful
MinerU result (already produced by the external MinerU process) is normalised in the worker thread too.
No OCR is added (``OCR unavailable`` stays the boundary).  The frozen Windows build needs
``multiprocessing.freeze_support()`` in the entry points (``app.py``, ``run.py``); Windows desktop
acceptance of the spawn path remains an owner gate.
"""
from __future__ import annotations

import atexit
import dataclasses
import multiprocessing
import os
import threading
import time
from datetime import date, datetime, time as dt_time, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

ISOLATION_VERSION = 1
MODE = "spawn process"

OK = "OK"
CANCELLED = "CANCELLED"
TIMEOUT = "TIMEOUT"
CRASHED = "CRASHED"
IDENTITY_CHANGED = "IDENTITY_CHANGED"
NOT_PLAIN = "NOT_PLAIN"

DEFAULT_TIMEOUT = 600.0            # seconds; the same order as the MinerU default
GRACE = 2.0                        # seconds per shutdown step
POLL = 0.05

_LIVE: "set" = set()
_LIVE_LOCK = threading.Lock()

_PLAIN_SCALARS = (type(None), bool, int, float, str, bytes, date, datetime, dt_time, timedelta, Decimal)


class IsolatedParseError(RuntimeError):
    """The isolated parser stopped without a usable result (message says why; nothing was saved)."""


def is_plain(value: Any, _depth: int = 0) -> bool:
    """True when ``value`` is built only from scalars, lists, tuples, sets and dicts (a DTO)."""
    if _depth > 64:
        return False
    if isinstance(value, _PLAIN_SCALARS):
        return True
    if isinstance(value, (list, tuple, set, frozenset)):
        return all(is_plain(item, _depth + 1) for item in value)
    if isinstance(value, dict):
        return all(isinstance(k, (str, int, float, bool, type(None))) and is_plain(v, _depth + 1)
                   for k, v in value.items())
    return False


# ---- DTOs -----------------------------------------------------------------------------------------
def profile_to_dto(profile) -> Optional[Dict[str, Any]]:
    if profile is None:
        return None
    data = dataclasses.asdict(profile)
    data["date_formats"] = list(data.get("date_formats") or ())
    return data


def profile_from_dto(data: Optional[Dict[str, Any]]):
    if data is None:
        return None
    from core.ddr_report_profiles import ReportProfile
    values = dict(data)
    values["date_formats"] = tuple(values.get("date_formats") or ())
    return ReportProfile(**values)


def parse_result_to_dto(parse_result) -> Optional[Dict[str, Any]]:
    """Only an unsuccessful MinerU result is sent (its error text); a successful one is never isolated."""
    if parse_result is None:
        return None
    if getattr(parse_result, "success", False):
        raise ValueError("a successful MinerU result is normalised in the worker thread, not isolated")
    return {"source_file": str(parse_result.source_file), "error": parse_result.error,
            "error_type": parse_result.error_type}


def _parse_result_from_dto(data):
    if data is None:
        return None
    from core.mineru_engine import MinerUParseResult
    return MinerUParseResult(source_file=data["source_file"], success=False, error=data.get("error"),
                             error_type=data.get("error_type"))


def prepared_to_dto(prepared) -> Dict[str, Any]:
    error = prepared.error
    return {
        "source": prepared.source, "stage": prepared.stage, "extracted": prepared.extracted,
        "import_report": prepared.import_report, "pdf_split_info": prepared.pdf_split_info,
        "error_type": type(error).__name__ if error is not None else None,
        "error": str(error) if error is not None else None,
        "error_status": prepared.error_status, "cancelled": bool(prepared.cancelled),
    }


def _error_from_dto(type_name: Optional[str], message: Optional[str]) -> Optional[BaseException]:
    if type_name is None:
        return None
    from core.ddr_import_pipeline import ImportCancelled
    from core.mineru_engine import MinerUError, MinerUNormalizationError
    known = {"ValueError": ValueError, "RuntimeError": RuntimeError, "MinerUError": MinerUError,
             "MinerUNormalizationError": MinerUNormalizationError, "ImportCancelled": ImportCancelled,
             "IsolatedParseError": IsolatedParseError}
    cls = known.get(type_name)
    return cls(message) if cls is not None else IsolatedParseError(f"{type_name}: {message}")


# ---- child ----------------------------------------------------------------------------------------
def _child_main(conn, cancel_event, request: Dict[str, Any]) -> None:
    """Entry point of the spawn child: parse, convert to plain data, send once, exit."""
    try:
        outcome = _prepare_in_child(request, cancel_event.is_set)
    except BaseException as exc:                     # reported to the parent as CRASHED
        outcome = {"status": CRASHED, "error_type": type(exc).__name__, "error": str(exc)[:2000]}
    outcome["child_pid"] = os.getpid()
    try:
        conn.send(outcome)
    finally:
        conn.close()


def _prepare_in_child(request: Dict[str, Any], should_cancel: Callable[[], bool]) -> Dict[str, Any]:
    from core import ddr_import_pipeline as pipe
    from core.ddr_import_queue import file_fingerprint
    from core.ddr_import_service import DDRImportService
    from core.import_router import route_file

    source = request["source"]
    before = file_fingerprint(source)
    if before != request["fingerprint"]:
        return {"status": IDENTITY_CHANGED, "error": "the file changed before the parser read it"}
    extractor = DDRImportService.__new__(DDRImportService)        # no database: extract_file is file-only
    prepared = pipe.prepare_import(
        source,
        parse_result=_parse_result_from_dto(request.get("parse_result")),
        profile=profile_from_dto(request.get("profile")),
        profiles=[profile_from_dto(p) for p in request.get("profiles") or []],
        expected_well=request.get("expected_well"),
        route=route_file,
        template_matcher=DDRImportService._auto_match_template,
        extract_file=extractor.extract_file,
        meaningful=pipe.has_meaningful_canonical_data,
        should_cancel=should_cancel,
    )
    after = file_fingerprint(source)
    if after != before:
        return {"status": IDENTITY_CHANGED, "error": "the file changed while the parser read it"}
    dto = prepared_to_dto(prepared)
    if not is_plain(dto):
        return {"status": NOT_PLAIN, "error": "the parser produced a value that is not plain data"}
    return {"status": OK, "prepared": dto, "fingerprint": after}


# ---- parent ---------------------------------------------------------------------------------------
def _stop(process, grace: float) -> str:
    """Bounded shutdown; returns how the child ended ('exited', 'terminated', 'killed')."""
    process.join(grace)
    if not process.is_alive():
        return "exited"
    process.terminate()
    process.join(grace)
    if not process.is_alive():
        return "terminated"
    process.kill()
    process.join(grace)
    return "killed"


def live_processes() -> List[Any]:
    with _LIVE_LOCK:
        return [p for p in _LIVE if p.is_alive()]


def shutdown_all(grace: float = GRACE) -> int:
    """Stop every child still running (called at interpreter exit); returns how many were stopped."""
    with _LIVE_LOCK:
        processes = list(_LIVE)
        _LIVE.clear()
    stopped = 0
    for process in processes:
        if process.is_alive():
            _stop(process, grace)
            stopped += 1
    return stopped


atexit.register(shutdown_all)


def run_isolated(request: Dict[str, Any], *, should_cancel: Callable[[], bool] = lambda: False,
                 timeout: float = DEFAULT_TIMEOUT, grace: float = GRACE, poll: float = POLL,
                 target: Optional[Callable] = None) -> Dict[str, Any]:
    """Run ``target`` (default: the DDR preparation) in a spawn child; always return a plain outcome."""
    if not is_plain(request):
        raise TypeError("only plain data can be sent to the parser process")
    ctx = multiprocessing.get_context("spawn")
    receiver, sender = ctx.Pipe(duplex=False)
    cancel_event = ctx.Event()
    process = ctx.Process(target=target or _child_main, args=(sender, cancel_event, request),
                          name="drillmaster-ddr-parse", daemon=True)
    started = time.monotonic()
    process.start()
    sender.close()
    with _LIVE_LOCK:
        _LIVE.add(process)
    outcome: Dict[str, Any]
    try:
        while True:
            if receiver.poll(poll):
                try:
                    outcome = receiver.recv()
                except (EOFError, OSError):
                    outcome = {"status": CRASHED, "error": "the parser process closed its channel without a result"}
                except Exception as exc:              # e.g. a result that cannot be unpickled
                    outcome = {"status": NOT_PLAIN, "error": f"unreadable parser result ({type(exc).__name__})"}
                break
            if should_cancel():
                cancel_event.set()
                outcome = {"status": CANCELLED, "error": "cancelled; the parser process was stopped"}
                break
            if not process.is_alive() and not receiver.poll(0):
                outcome = {"status": CRASHED,
                           "error": f"the parser process ended (exit code {process.exitcode}) without a result"}
                break
            if time.monotonic() - started > timeout:
                outcome = {"status": TIMEOUT, "error": f"the parser did not finish within {timeout:g} s"}
                break
        if not isinstance(outcome, dict) or not is_plain(outcome):
            outcome = {"status": NOT_PLAIN, "error": "the parser process sent a value that is not plain data"}
    finally:
        stop = _stop(process, grace)
        receiver.close()
        with _LIVE_LOCK:
            _LIVE.discard(process)
    outcome = dict(outcome)
    outcome.update(pid=process.pid, exitcode=process.exitcode, stop=stop,
                   seconds=round(time.monotonic() - started, 3))
    return outcome


def prepare_isolated(source: str, *, parse_result=None, profile=None, profiles=(), expected_well=None,
                     should_cancel: Callable[[], bool] = lambda: False, timeout: float = DEFAULT_TIMEOUT,
                     grace: float = GRACE):
    """``prepare_import`` in a spawn child; returns the same ``PreparedImport`` DTO as the thread path."""
    from core.ddr_import_pipeline import ImportCancelled, PreparedImport
    from core.ddr_import_queue import file_fingerprint

    source = str(source)
    fingerprint = file_fingerprint(source)
    request = {"source": source, "fingerprint": fingerprint, "parse_result": parse_result_to_dto(parse_result),
               "profile": profile_to_dto(profile), "profiles": [profile_to_dto(p) for p in profiles or ()],
               "expected_well": expected_well, "version": ISOLATION_VERSION}
    outcome = run_isolated(request, should_cancel=should_cancel, timeout=timeout, grace=grace)
    status = outcome["status"]
    if status == OK and file_fingerprint(source) != fingerprint:
        status, outcome["error"] = IDENTITY_CHANGED, "the file changed after the parser read it"
    isolation = {"mode": MODE, "version": ISOLATION_VERSION, "status": status, "pid": outcome.get("pid"),
                 "stop": outcome.get("stop"), "seconds": outcome.get("seconds")}
    label = f"process {outcome.get('pid')}"
    if status == CANCELLED:
        return PreparedImport(source=source, stage="route", cancelled=True, worker_thread=label,
                              error=ImportCancelled(outcome["error"]), import_report={"parser_isolation": isolation})
    if status != OK:
        return PreparedImport(source=source, stage="route", worker_thread=label,
                              error=IsolatedParseError(f"{status}: {outcome.get('error')}; nothing was saved"),
                              import_report={"parser_isolation": isolation})
    dto = outcome["prepared"]
    report = dict(dto["import_report"] or {})
    report["parser_isolation"] = isolation
    return PreparedImport(source=source, stage=dto["stage"], extracted=dto["extracted"], import_report=report,
                          pdf_split_info=dto["pdf_split_info"] or {},
                          error=_error_from_dto(dto["error_type"], dto["error"]),
                          error_status=dto["error_status"], cancelled=dto["cancelled"], worker_thread=label)
