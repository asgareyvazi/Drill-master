"""Export Center worker (M43 closure, phase 6).

Covers the Qt-free job layer (core.export_jobs), the worker's own read-only
database connection, and the W11 widget driving a real QThread: one export
at a time, cancel between files, errors reported by type only, buttons
restored, shutdown waits. Synthetic data and temp paths only.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core import export_jobs
from core.export_jobs import ExportJob, plan_batch, run_jobs, worker_database


# --------------------------------------------------------------------- planning

def test_plan_batch_keeps_the_historical_order_and_file_names(tmp_path):
    folder = str(tmp_path)
    reports = [{"id": 7, "report_number": 41, "report_date": "2026-10-07"},
               {"id": 8, "report_number": 42, "report_date": "2026-10-08"}]
    jobs = plan_batch(well_id=3, folder=folder, fmt="html", timestamp="20261021_101500",
                      selected=export_jobs.BATCH_KINDS, report_id=9, ddr_reports=reports)
    names = [os.path.basename(j.path) for j in jobs]
    assert names == [
        "Professional_16Sheets_20261021_101500.xlsx", "Professional_20261021_101500.pdf",
        "EOWR_20261021_101500.html", "NPT_20261021_101500.html", "Cost_20261021_101500.html",
        "Plan_20261021_101500.html", "DDR_41_2026-10-07.html", "DDR_42_2026-10-08.html",
    ]
    assert all(os.path.dirname(j.path) == folder for j in jobs)
    assert [j.target_id for j in jobs] == [3, 3, 3, 3, 3, 3, 7, 8]
    assert jobs[0].report_id == jobs[1].report_id == 9
    assert {j.fmt for j in jobs[2:]} == {"html"}


def test_plan_batch_never_lets_two_files_share_a_path(tmp_path):
    # Two reports with the same number and date (or a getter without a number)
    # previously produced the same name, and the second file overwrote the first.
    reports = [{"id": 7, "report_date": "2026-10-07"}, {"id": 8, "report_date": "2026-10-07"},
               {"id": 9, "report_number": 5, "report_date": "2026-10-08"}]
    jobs = plan_batch(well_id=1, folder=str(tmp_path), fmt="pdf", timestamp="T",
                      selected=["ddr"], ddr_reports=reports)
    names = [os.path.basename(j.path) for j in jobs]
    assert names == ["DDR__2026-10-07.pdf", "DDR__2026-10-07_id8.pdf", "DDR_5_2026-10-08.pdf"]
    assert len({j.path for j in jobs}) == len(jobs)


def test_daily_report_list_carries_the_report_number(file_db):
    manager, well_id = file_db
    assert [r["report_number"] for r in manager.get_daily_reports_by_well(well_id)] == [41]


def test_plan_batch_selection_and_unknown_kind(tmp_path):
    jobs = plan_batch(well_id=1, folder=str(tmp_path), fmt="pdf", timestamp="T", selected=["npt"])
    assert [(j.kind, os.path.basename(j.path)) for j in jobs] == [("npt", "NPT_T.pdf")]
    assert plan_batch(well_id=1, folder=str(tmp_path), fmt="pdf", timestamp="T", selected=["ddr"]) == []
    with pytest.raises(ValueError):
        plan_batch(well_id=1, folder=str(tmp_path), fmt="pdf", timestamp="T", selected=["bogus"])


# --------------------------------------------------------------------- running

def _job(kind, name="f"):
    return ExportJob(kind, kind.upper(), f"/nowhere/{name}", 1)


def test_run_jobs_records_each_outcome_and_keeps_going(monkeypatch):
    calls = []

    def ok(db, job):
        calls.append(job.kind)
        return True

    def refused(db, job):
        calls.append(job.kind)
        return False

    def broken(db, job):
        calls.append(job.kind)
        raise ValueError("cell value 1234.5 for Private Well")  # must never be surfaced

    monkeypatch.setattr(export_jobs, "GENERATORS", {"a": ok, "b": refused, "c": broken, "d": ok})
    progress = []
    result = run_jobs(object(), [_job("a"), _job("b"), _job("c"), _job("d")],
                      progress=lambda d, t, o: progress.append((d, t, o.status)))
    assert calls == ["a", "b", "c", "d"]
    assert [o.status for o in result.outcomes] == ["ok", "failed", "error", "ok"]
    assert result.outcomes[2].error == "ValueError"
    assert "1234" not in repr(result) and "Private" not in repr(result)
    assert result.ok_count == 2 and len(result.problems) == 2 and not result.cancelled
    assert progress == [(1, 4, "ok"), (2, 4, "failed"), (3, 4, "error"), (4, 4, "ok")]


def test_cancel_finishes_the_current_file_and_skips_the_rest(monkeypatch):
    cancel = threading.Event()
    written = []

    def writes_then_cancel(db, job):
        cancel.set()          # cancel arrives while this file is being written
        written.append(job.path)
        return True

    monkeypatch.setattr(export_jobs, "GENERATORS", {"a": writes_then_cancel})
    result = run_jobs(object(), [_job("a", "1"), _job("a", "2"), _job("a", "3")], cancel_event=cancel)
    assert written == ["/nowhere/1"]
    assert [o.status for o in result.outcomes] == ["ok", "cancelled", "cancelled"]
    assert result.cancelled and result.ok_count == 1


def test_unknown_job_kind_is_a_programming_error(monkeypatch):
    monkeypatch.setattr(export_jobs, "GENERATORS", {})
    with pytest.raises(ValueError):
        run_jobs(object(), [_job("zzz")])


# ------------------------------------------------------- worker's own connection

@pytest.fixture
def file_db(tmp_path, monkeypatch):
    from core.database import Company, DailyReport, DatabaseManager, Project, Section, Well, Wellbore

    data_root = tmp_path / "user-data"
    monkeypatch.setenv("DRILLMASTER_ENV", "test")
    monkeypatch.delenv("DRILLMASTER_ENVIRONMENT", raising=False)
    monkeypatch.setenv("DRILLMASTER_DATA_DIR", str(data_root))
    monkeypatch.setenv("DRILLMASTER_DB_PATH", str(data_root / "drillmaster.db"))
    monkeypatch.setenv("DRILLMASTER_AI_IMPORT", "0")
    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    with manager.session_scope() as session:
        company = Company(name="Synthetic Co", code="SYN-CO")
        session.add(company)
        session.flush()
        project = Project(company_id=company.id, name="Synthetic Project", code="SYN-P")
        session.add(project)
        session.flush()
        well = Well(project_id=project.id, name="Synthetic Well", code="SYN-W")
        session.add(well)
        session.flush()
        bore = Wellbore(well_id=well.id, name="Original", wellbore_type="original")
        session.add(bore)
        session.flush()
        section = Section(well_id=well.id, wellbore_id=bore.id, name="12-1/4 in", depth_from=0, depth_to=1000)
        session.add(section)
        session.flush()
        session.add(DailyReport(well_id=well.id, wellbore_id=bore.id, section_id=section.id,
                                report_date=date(2026, 10, 7), report_number=41, summary="synthetic"))
        well_id = well.id
    yield manager, well_id
    manager.engine.dispose()


def test_worker_view_has_its_own_read_only_connection(file_db):
    manager, well_id = file_db
    with worker_database(manager) as view:
        assert view is not manager
        assert view.engine is not manager.engine
        assert view.get_well_by_id(well_id)["name"] == "Synthetic Well"
        assert [r["report_number"] for r in view.get_daily_reports_by_well(well_id)] == [41]
        # Same authorization state, so the global session hooks apply unchanged.
        assert view.Session.kw["info"]["authorization"] is manager.Session.kw["info"]["authorization"]
        session = view.Session()
        try:
            with pytest.raises(OperationalError) as caught:
                session.execute(text("UPDATE wells SET name = 'x'"))
                session.commit()
            assert isinstance(caught.value.orig, sqlite3.OperationalError)
            assert "readonly" in str(caught.value.orig).lower()
        finally:
            session.close()
    # The manager still works and nothing was changed.
    assert manager.get_well_by_id(well_id)["name"] == "Synthetic Well"


def test_restore_gate_refuses_and_counts_worker_connections(file_db):
    from core.db_maintenance import MaintenanceActive

    manager, well_id = file_db
    gate = manager._maintenance_gate
    with worker_database(manager) as view:
        session = view.Session()
        try:
            session.execute(text("SELECT 1"))
            assert gate.active >= 1  # a live worker connection is visible to the drain
        finally:
            session.close()
        gate.close(drain_timeout=1.0)
        try:
            refused = view.Session()
            try:
                with pytest.raises(MaintenanceActive):
                    refused.execute(text("SELECT 1"))
            finally:
                refused.close()
        finally:
            gate.open()
        assert view.get_well_by_id(well_id)["name"] == "Synthetic Well"


def test_in_memory_database_is_shared_not_reopened():
    manager = SimpleNamespace(db_path=":memory:", Session=object())
    with worker_database(manager) as view:
        assert view is manager


def _masked(path):
    text = open(path, encoding="utf-8").read()
    return re.sub(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?(\.\d+)?|\d{2}:\d{2}(:\d{2})?", "<ts>", text)


@pytest.mark.parametrize("kind", ["eowr", "npt", "cost", "ddr", "plan"])
def test_worker_connection_produces_the_same_report(file_db, tmp_path, kind):
    manager, well_id = file_db
    target = manager.get_daily_reports_by_well(well_id)[0]["id"] if kind == "ddr" else well_id
    direct = ExportJob(kind, kind, str(tmp_path / f"direct_{kind}.html"), target, "html")
    viaworker = ExportJob(kind, kind, str(tmp_path / f"worker_{kind}.html"), target, "html")
    first = run_jobs(manager, [direct])
    with worker_database(manager) as view:
        second = run_jobs(view, [viaworker])
    assert first.outcomes[0].status == second.outcomes[0].status
    if kind == "plan":  # the synthetic well has no plan: both paths refuse alike
        assert first.outcomes[0].status == "failed"
        return
    assert first.outcomes[0].ok, first.outcomes[0]
    assert _masked(direct.path) == _masked(viaworker.path)


# --------------------------------------------------------------------- widget

@pytest.fixture
def widget(monkeypatch):
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import tabs.w11_Export as module

    reports = [{"id": 7, "report_number": 41, "report_date": "2026-10-07"}]
    hierarchy = [{"projects": [{"name": "Synthetic Project",
                                "wells": [{"id": 3, "name": "Synthetic Well"}]}]}]
    fake_db = SimpleNamespace(
        get_hierarchy=lambda *a, **k: hierarchy,
        get_daily_reports_by_well=lambda wid, *a, **k: list(reports),
        db_path=":memory:", Session=object(),
    )
    w = module.ExportWidget(db_manager=fake_db)
    infos = []
    monkeypatch.setattr(module.QMessageBox, "information", staticmethod(lambda *a, **k: infos.append(a[1:])))
    monkeypatch.setattr(module.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(module.ExportWidget, "_open_output", staticmethod(lambda path: None))
    w._infos = infos
    yield module, w, app
    if w._export_worker is not None:
        w._export_worker.cancel()
        w._export_worker.wait(5000)
    w.deleteLater()
    app.processEvents()


def _drain(app, w, timeout_ms=5000):
    worker = w._export_worker
    if worker is not None:
        assert worker.wait(timeout_ms)
    for _ in range(5):
        app.processEvents()


def test_batch_export_runs_in_a_worker_and_restores_the_ui(widget, monkeypatch, tmp_path):
    module, w, app = widget
    ui_thread = threading.get_ident()
    seen_threads = []

    def write(db, job):
        seen_threads.append(threading.get_ident())
        with open(job.path, "w", encoding="utf-8") as fh:
            fh.write(job.kind)
        return True

    monkeypatch.setattr(export_jobs, "GENERATORS", {k: write for k in (
        "ddr", "eowr", "npt", "cost", "plan", "professional_excel", "professional_pdf")})
    monkeypatch.setattr(module.QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(tmp_path)))
    w.batch_well.setCurrentIndex(w.batch_well.findData(3))
    w.batch_fmt.setCurrentText("HTML")
    w._export_batch()
    assert w.export_running()
    assert not any(b.isEnabled() for b in w._export_buttons)
    assert w.batch_cancel_btn.isEnabled()
    _drain(app, w)
    assert not w.export_running()
    assert all(b.isEnabled() for b in w._export_buttons) and not w.batch_cancel_btn.isEnabled()
    produced = sorted(os.listdir(tmp_path))
    assert len(produced) == 7 and any(n.startswith("DDR_41_2026-10-07") for n in produced)
    assert seen_threads and ui_thread not in seen_threads
    log = w.batch_log.toPlainText()
    assert "Done: 7 of 7 files exported" in log and "[7/7]" in log


def test_second_export_is_refused_while_one_runs_and_cancel_skips_the_rest(widget, monkeypatch, tmp_path):
    module, w, app = widget
    release = threading.Event()
    started = threading.Event()
    written = []

    def slow(db, job):
        started.set()
        assert release.wait(5)
        written.append(job.path)
        return True

    monkeypatch.setattr(export_jobs, "GENERATORS", {"plan": slow, "npt": slow})
    jobs = [ExportJob("plan", "Plan", str(tmp_path / "1"), 3), ExportJob("npt", "NPT", str(tmp_path / "2"), 3)]
    results = []
    assert w._start_export(lambda db: jobs, results.append)
    assert started.wait(5)
    assert w._start_export(lambda db: jobs, results.append) is False   # duplicate refused
    assert w._infos and "already running" in w._infos[0][1]
    w._cancel_export()
    release.set()
    _drain(app, w)
    assert written == [str(tmp_path / "1")]
    assert [o.status for o in results[0].outcomes] == ["ok", "cancelled"]
    assert not w.export_running()


def test_single_export_error_shows_the_type_only(widget, monkeypatch, tmp_path):
    module, w, app = widget

    def broken(db, job):
        raise RuntimeError("Synthetic Well 1234 m")

    monkeypatch.setattr(export_jobs, "GENERATORS", {"plan": broken})
    w._start_single_export(ExportJob("plan", "Plan", str(tmp_path / "p.html"), 3, "html"), w.plan_status)
    assert w.plan_status.text().startswith("🔄")
    _drain(app, w)
    assert w.plan_status.text() == "❌ Export failed (RuntimeError)"


def test_worker_level_failure_is_reported_and_releases_the_guard(widget):
    module, w, app = widget
    messages = []

    def build(db):
        raise KeyError("private")

    assert w._start_export(build, lambda r: messages.append("completed"), on_failed=messages.append)
    _drain(app, w)
    assert messages == ["KeyError"]
    assert not w.export_running()


def test_cleanup_cancels_and_waits_for_the_file_in_progress(widget, monkeypatch, tmp_path):
    module, w, app = widget
    started = threading.Event()
    finished = []

    def slow(db, job):
        started.set()
        threading.Event().wait(0.3)
        finished.append(job.path)
        return True

    monkeypatch.setattr(export_jobs, "GENERATORS", {"plan": slow})
    jobs = [ExportJob("plan", "Plan", str(tmp_path / n), 3) for n in ("1", "2", "3")]
    assert w._start_export(lambda db: jobs, lambda r: None)
    assert started.wait(5)
    worker = w._export_worker
    w.cleanup()
    assert worker.isFinished()
    assert finished == [str(tmp_path / "1")]   # current file completed, rest skipped
    for _ in range(5):
        app.processEvents()
