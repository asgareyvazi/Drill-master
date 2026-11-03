"""M111: the DDR parser runs in an isolated spawn process - plain data only, persistence in the parent,
bounded shutdown, no orphans, identity checks, a cancelled or failed parse never reaches the save path.

Synthetic files only (the SYNTHETIC workbook fixture and the M54 synthetic PDFs); no OCR; offscreen Qt for
the dialog tests, where ``_do_import`` and the preview are replaced so nothing is written to a database.
"""
from __future__ import annotations

import multiprocessing
import os
import shutil
import signal
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402

from core import ddr_import_pipeline as pipe  # noqa: E402
from core import isolated_parse as ip  # noqa: E402
from core.ddr_import_queue import CANCELLED, file_fingerprint  # noqa: E402
from core.ddr_import_service import DDRImportService  # noqa: E402
from core.ddr_report_profiles import profile_from_dict  # noqa: E402
from core.import_router import route_file  # noqa: E402
from core.mineru_engine import MinerUParseResult  # noqa: E402
from tests import m111_child_targets as targets  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
PROFILE = profile_from_dict({"key": "syn-rig", "version": 2, "name": "SYN rig format",
                             "aliases": {"Hrs": "time_logs_24h.duration"}, "date_formats": ["%d.%m.%Y"]})


def _workbook(tmp_path, name="SYN_normal.xlsx"):
    source = tmp_path / name
    shutil.copy(FIXTURES / "normal_ddr.xlsx", source)
    return source


def _gone(outcome):
    try:
        assert outcome["exitcode"] is not None                      # joined: the child has ended
        assert not targets.pid_alive(outcome["pid"])
        assert outcome["pid"] not in [p.pid for p in multiprocessing.active_children()]
        assert not ip.live_processes()
    finally:
        _reap(outcome.get("pid"))


def _reap(pid):
    """Test hygiene only: when an assertion above fails (for example under a mutant that disables
    terminate/kill), do not leave a SIGTERM-ignoring child running after the test session."""
    if pid and targets.pid_alive(pid):
        try:
            os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
        except OSError:  # silent-ok: the child ended between the check and the kill
            pass


def _thread_prepare(source):
    service = DDRImportService()
    return pipe.prepare_import(str(source), route=route_file, template_matcher=service._auto_match_template,
                               extract_file=service.extract_file, meaningful=pipe.has_meaningful_canonical_data)


# ---- the result is the same DTO as the thread path, computed in another process ------------------
def test_a_workbook_is_parsed_in_a_child_process_into_the_same_plain_dto(tmp_path):
    source = _workbook(tmp_path)
    isolated = ip.prepare_isolated(str(source), profile=PROFILE, profiles=[PROFILE], timeout=120)
    reference = _thread_prepare(source)
    assert isolated.ok and isolated.error is None and isolated.stage == reference.stage == "validation"
    assert isolated.extracted == reference.extracted and ip.is_plain(isolated.extracted)
    info = isolated.import_report.pop("parser_isolation")
    assert isolated.import_report == reference.import_report
    assert info["mode"] == "spawn process" and info["status"] == ip.OK and info["stop"] == "exited"
    assert info["pid"] != os.getpid() and isolated.worker_thread == f"process {info['pid']}"
    assert not targets.pid_alive(info["pid"]) and not ip.live_processes()


@pytest.mark.parametrize("fixture", sorted(p.name for p in FIXTURES.glob("*.xlsx")))
def test_every_repository_workbook_crosses_the_boundary_unchanged(tmp_path, fixture):
    """Real parser output (not a hand-made dict): time-log durations arrive as ``timedelta``, which is plain."""
    source = _workbook(tmp_path, fixture)
    shutil.copy(FIXTURES / fixture, source)
    isolated = ip.prepare_isolated(str(source), profile=PROFILE, profiles=[PROFILE], timeout=120)
    reference = _thread_prepare(source)
    assert isolated.stage == reference.stage and isolated.extracted == reference.extracted
    assert (isolated.error is None) == (reference.error is None)
    if reference.error is not None:
        assert type(isolated.error) is type(reference.error) and str(isolated.error) == str(reference.error)
    assert "NOT_PLAIN" not in str(isolated.error or "") and not ip.live_processes()


def test_failures_keep_their_type_and_stage_and_nothing_is_extracted(tmp_path):
    unsupported = tmp_path / "SYN_notes.bin"
    unsupported.write_bytes(bytes(range(64)))
    out = ip.prepare_isolated(str(unsupported), timeout=120)
    assert out.stage == "open" and isinstance(out.error, ValueError) and out.extracted is None and not out.ok
    assert str(out.error) == str(_thread_prepare(unsupported).error)
    failed = MinerUParseResult(source_file=str(unsupported), success=False, error="SYN unavailable",
                               error_type="missing")
    assert ip.parse_result_to_dto(failed) == {"source_file": str(unsupported), "error": "SYN unavailable",
                                              "error_type": "missing"}
    with pytest.raises(ValueError):
        ip.parse_result_to_dto(MinerUParseResult(source_file="x", success=True))


def test_profiles_cross_the_boundary_as_plain_dictionaries():
    dto = ip.profile_to_dto(PROFILE)
    assert ip.is_plain(dto) and dto["date_formats"] == ["%d.%m.%Y"]
    assert ip.profile_from_dto(dto) == PROFILE and ip.profile_from_dto(None) is None
    assert not ip.is_plain({"x": targets.Opaque()}) and not ip.is_plain([threading.Lock()])
    with pytest.raises(TypeError):
        ip.run_isolated({"session": targets.Opaque()})


# ---- identity -------------------------------------------------------------------------------------
def test_a_file_changed_during_parsing_is_rejected(tmp_path):
    source = _workbook(tmp_path)
    original = source.read_bytes()
    changed = []

    def change_once():
        if not changed:
            source.write_bytes(original + b"\0SYN changed")
            changed.append(1)
        return False
    request = {"source": str(source), "fingerprint": file_fingerprint(str(source)), "parse_result": None,
               "profile": None, "profiles": [], "expected_well": None, "version": ip.ISOLATION_VERSION}
    outcome = ip.run_isolated(request, should_cancel=change_once, timeout=120)
    assert outcome["status"] == ip.IDENTITY_CHANGED and "prepared" not in outcome
    _gone(outcome)


def test_the_child_rechecks_identity_after_parsing(tmp_path):
    source = _workbook(tmp_path)
    calls = []

    def change_at_mapping():
        calls.append(1)
        if len(calls) == 3:                                         # route, open pass; change before mapping
            source.write_bytes(source.read_bytes() + b"\0")
        return False
    request = {"source": str(source), "fingerprint": file_fingerprint(str(source))}
    outcome = ip._prepare_in_child(request, change_at_mapping)      # in-process: the child's own logic
    assert outcome == {"status": ip.IDENTITY_CHANGED, "error": "the file changed while the parser read it"}
    assert ip._prepare_in_child({"source": str(source), "fingerprint": "0" * 64}, lambda: False)["status"] == \
        ip.IDENTITY_CHANGED


def test_the_parent_rechecks_identity_after_the_result(tmp_path, monkeypatch):
    source = _workbook(tmp_path)
    real = ip.run_isolated

    def run_then_change(request, **kwargs):
        outcome = real(request, **kwargs)
        source.write_bytes(source.read_bytes() + b"\0")
        return outcome
    monkeypatch.setattr(ip, "run_isolated", run_then_change)
    out = ip.prepare_isolated(str(source), timeout=120)
    assert out.extracted is None and isinstance(out.error, ip.IsolatedParseError)
    assert str(out.error).startswith("IDENTITY_CHANGED") and "nothing was saved" in str(out.error)


# ---- cancel, timeout, crash, non-plain results: bounded and never saved --------------------------
def test_cancel_stops_the_child_and_discards_a_late_result():
    flag = {"at": None}

    def cancel_soon():
        flag["at"] = flag["at"] or time.monotonic()
        return time.monotonic() - flag["at"] > 0.3
    outcome = ip.run_isolated({"sleep": 1.5}, should_cancel=cancel_soon, grace=0.5,
                              target=targets.slow_ok)
    assert outcome["status"] == ip.CANCELLED and "prepared" not in outcome
    assert outcome["stop"] in {"terminated", "exited"}
    _gone(outcome)


def test_the_child_honours_the_cancel_event_between_steps():
    outcome = ip.run_isolated({}, should_cancel=lambda: True, grace=5.0, target=targets.honour_cancel)
    assert outcome["status"] == ip.CANCELLED and "prepared" not in outcome and outcome["stop"] == "exited"
    _gone(outcome)


def test_a_hanging_parser_is_stopped_at_the_timeout():
    started = time.monotonic()
    outcome = ip.run_isolated({}, timeout=0.5, grace=0.5, target=targets.hang)
    assert outcome["status"] == ip.TIMEOUT and outcome["stop"] == "terminated"
    assert time.monotonic() - started < 30
    _gone(outcome)


def test_a_child_that_ignores_terminate_is_killed():
    outcome = ip.run_isolated({}, timeout=0.5, grace=0.5, target=targets.hang_ignoring_terminate)
    assert outcome["status"] == ip.TIMEOUT
    assert outcome["stop"] == ("killed" if os.name == "posix" else "terminated")
    _gone(outcome)


def test_a_crashed_child_and_a_non_plain_result_are_reported_not_used():
    crashed = ip.run_isolated({}, timeout=60, target=targets.crash)
    assert crashed["status"] == ip.CRASHED and crashed["exitcode"] == 3 and "prepared" not in crashed
    _gone(crashed)
    opaque = ip.run_isolated({}, timeout=60, target=targets.send_opaque)
    assert opaque["status"] == ip.NOT_PLAIN and "prepared" not in opaque
    _gone(opaque)


def test_shutdown_all_leaves_no_orphan():
    holder = {}
    worker = threading.Thread(target=lambda: holder.update(
        out=ip.run_isolated({}, timeout=60, grace=0.5, target=targets.hang)))
    worker.start()
    deadline = time.monotonic() + 30
    while not ip.live_processes() and time.monotonic() < deadline:
        time.sleep(0.05)
    pids = [p.pid for p in ip.live_processes()]
    assert len(pids) == 1
    assert ip.shutdown_all(grace=0.5) == 1
    worker.join(30)
    assert not worker.is_alive() and not targets.pid_alive(pids[0])
    assert holder["out"]["status"] in {ip.CRASHED, ip.NOT_PLAIN, ip.TIMEOUT}       # never OK


# ---- the dialog: production parsers isolated, injected ones in the worker thread -----------------
class Preview:
    def __init__(self, *args):
        self.confirmed = True

    def exec(self):
        return QtWidgets.QDialog.Accepted

    def apply_review_changes(self, payload):
        pass


@pytest.fixture
def dialog(monkeypatch, tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import dialogs.excel_import_dialog as module

    dlg = module.ExcelImportDialog(db_manager=SimpleNamespace(), well_id=1)
    persisted, reports = [], []
    monkeypatch.setattr(dlg, "_do_import", lambda extracted, refresh_ui=False: persisted.append(extracted) or {
        "status": "ACCEPT", "details": ["ok"], "imported": 1, "failed": 0})

    class Recorder(Preview):
        def __init__(self, source, extracted, report, parent):
            super().__init__()
            reports.append(report)
    monkeypatch.setattr(module, "ImportPreviewDialog", Recorder)
    monkeypatch.setattr(module.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(dlg, "accept", lambda: None)
    emitted = []
    dlg.import_completed.connect(emitted.append)
    yield dlg, _workbook(tmp_path), persisted, emitted, reports
    dlg._prepare_worker = dlg._mineru_worker = None
    dlg.deleteLater()
    app.processEvents()


def _run(dlg, files):
    dlg._set_import_busy(True)
    dlg._start_import_batch([str(f) for f in files])


def test_the_dialog_parses_in_a_child_and_saves_in_the_parent(dialog):
    dlg, source, persisted, emitted, reports = dialog
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(20)
    _run(dlg, [source])
    timer.stop()
    assert dlg._last_parse_mode == "spawn process" and len(ticks) >= 5          # the GUI loop kept running
    info = reports[0]["parser_isolation"]
    assert info["status"] == ip.OK and info["pid"] != os.getpid() and not targets.pid_alive(info["pid"])
    reference = _thread_prepare(source).extracted
    assert len(persisted) == 1 and persisted[0]["daily_report"] == reference["daily_report"]   # saved by the parent
    assert emitted[0][0]["status"] == "ACCEPT" and not ip.live_processes()


def test_cancel_during_an_isolated_parse_saves_nothing_and_stops_the_child(dialog):
    dlg, source, persisted, emitted, _reports = dialog
    QTimer.singleShot(100, dlg._queue_cancel)
    _run(dlg, [source])
    assert persisted == [] and emitted[0][0]["queue_status"] == CANCELLED
    assert "nothing saved" in emitted[0][0]["details"][0] and not ip.live_processes()


def test_closing_during_an_isolated_parse_is_refused_then_allowed(dialog):
    dlg, source, persisted, _emitted, _reports = dialog
    dlg.show()
    state = {}

    def try_close():
        state["running"] = dlg._workers_running()
        state["children"] = len(ip.live_processes())
        dlg.reject()
        state["visible"] = dlg.isVisible()
    QTimer.singleShot(100, try_close)
    _run(dlg, [source])
    assert state["running"] and state["visible"] and persisted == []
    assert not ip.live_processes() and not dlg._workers_running()
    dlg.reject()
    assert not dlg.isVisible()


def test_a_crash_or_timeout_in_the_dialog_is_a_failure_not_a_save(dialog, monkeypatch):
    dlg, source, persisted, emitted, _reports = dialog
    monkeypatch.setattr(dlg, "parse_timeout", 0.0)                  # the child cannot answer in 0 s
    _run(dlg, [source])
    assert persisted == [] and emitted[0][0]["failed"] == 1 and "TIMEOUT" in emitted[0][0]["error"]
    assert not ip.live_processes()


def test_injected_parsers_keep_the_worker_thread_and_mineru_success_is_not_sent(dialog, monkeypatch):
    dlg, source, persisted, _emitted, _reports = dialog
    kwargs = dict(route=route_file, meaningful=pipe.has_meaningful_canonical_data)
    assert dlg._parsers_can_be_isolated(kwargs, None)
    assert not dlg._parsers_can_be_isolated(kwargs, MinerUParseResult(source_file="x", success=True))
    assert not dlg._parsers_can_be_isolated(dict(kwargs, route=lambda *a, **k: None), None)
    assert not dlg._parsers_can_be_isolated(dict(kwargs, meaningful=lambda e: True), None)
    monkeypatch.setattr(dlg, "isolate_parsing", False)
    assert not dlg._parsers_can_be_isolated(kwargs, None)
    monkeypatch.setattr(dlg, "isolate_parsing", True)
    monkeypatch.setattr(dlg, "extract_file", lambda path: (None, {"daily_report": {"depth_2400": 1}}))
    assert not dlg._parsers_can_be_isolated(kwargs, None)
    _run(dlg, [source])
    assert dlg._last_parse_mode == "worker thread" and persisted == [{"daily_report": {"depth_2400": 1}}]


def test_the_entry_points_support_frozen_spawn_children():
    for name in ("app.py", "run.py"):
        assert "multiprocessing.freeze_support()" in Path(name).read_text(encoding="utf-8")
    import dialogs.excel_import_dialog as module
    assert module.has_meaningful_canonical_data is pipe.has_meaningful_canonical_data
