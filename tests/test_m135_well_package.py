"""M135: end-of-well package — new folder, every part hashed, audited before it gets its final name.

Fixture (synthetic): well SYN-A with its original bore and a sidetrack; DDR r1 (bore, 1 Apr) with a workflow
'approve' action by admin and a mud report (MW 75 pcf, PV 20, YP 10), DDR r2 (sidetrack, 2 Apr) with a mud
report and no approval; an NPT register event N1 08:00-14:00 that matches time-log rows L1+L2 of r1, and one
on r2; an operational procedure with typed names. Hand expectations: whole well → mud 2 samples, approvals 2
reports + 1 procedure = 3 rows; sidetrack only → mud 1, approvals r2 + procedure = 2, NPT 1 group.
"""
from __future__ import annotations

import ast
import csv
import json
import os
import threading
from datetime import date, time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

from core import well_package as wp  # noqa: E402
from core.context_jobs import JobCancelled  # noqa: E402
from core.database import DailyReport, MudReport, NPTReport, OperationalProcedure, TimeLog24H, Wellbore  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402
from tests.test_m123_mse_lineage import _admin, _as_admin, _raw  # noqa: E402

D1, D2 = date(2026, 4, 1), date(2026, 4, 2)


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / "m135.sqlite"
    manager = _open(path, tmp_path, monkeypatch)
    ids = _seed(manager)
    well, bore = ids["A"]
    out = {"manager": manager, "well": well, "bore": bore, "other_bore": ids["B"][1], "path": path,
           "out": tmp_path / "packages"}
    out["out"].mkdir()
    with manager.session_scope() as s:
        st = Wellbore(well_id=well, name="SYN-A ST1", wellbore_type="sidetrack")
        s.add(st)
        s.flush()
        r1 = DailyReport(well_id=well, wellbore_id=bore, report_date=D1, report_number=1, status="Approved")
        r2 = DailyReport(well_id=well, wellbore_id=st.id, report_date=D2, report_number=2)
        s.add_all([r1, r2])
        s.flush()
        out.update(sidetrack=st.id, r1=r1.id, r2=r2.id)
        s.add_all([MudReport(well_id=well, report_id=r1.id, report_date=D1, mud_type="WBM", mw=75.0, pv=20.0, yp=10.0),
                   MudReport(well_id=well, report_id=r2.id, report_date=D2, mud_type="WBM", mw=76.0)])
        for a, b, hours in (((8, 0), (12, 0), 4.0), ((12, 0), (14, 0), 2.0)):
            s.add(TimeLog24H(report_id=r1.id, time_from=time(*a), time_to=time(*b), duration=hours, is_npt=True))
        s.add(TimeLog24H(report_id=r2.id, time_from=time(9, 0), time_to=time(10, 0), duration=1.0, is_npt=True))
        s.add_all([NPTReport(well_id=well, report_id=r1.id, npt_date=D1, start_time=time(8, 0), end_time=time(14, 0),
                             duration_hours=6.0, npt_category="Equipment", npt_code="RIG", npt_description="SYN"),
                   NPTReport(well_id=well, report_id=r2.id, npt_date=D2, start_time=time(9, 0), end_time=time(10, 0),
                             duration_hours=1.0, npt_category="Equipment", npt_code="RIG", npt_description="SYN")])
        s.add(OperationalProcedure(well_id=well, title="SYN casing running", status="Approved",
                                   prepared_by="SYN Writer", approved_by="SYN Approver"))
    admin = _admin(path)
    _raw(path, "INSERT INTO approval_actions(report_id, action, status, user_id, created_at) "
               "VALUES (?, 'approve', 'Approved', ?, '2026-04-02 08:00:00')", out["r1"], admin)
    _as_admin(manager, path)
    yield out
    manager.close()


def _request(env, name="pkg", **kw):
    return wp.PackageRequest(well_id=env["well"], target_dir=str(env["out"] / name), generated_by="admin", **kw)


def _parts(result):
    return {p.key: p for p in result.parts}


def _csv(path):
    with open(path, encoding="utf-8") as handle:
        return list(csv.reader(handle))


def _audits(env):
    return _raw(env["path"], "SELECT details FROM audit_logs WHERE action=?", wp.AUDIT_ACTION)


def test_a_whole_well_package_has_every_part_hashed_and_is_audited_before_it_is_named(env):
    result = wp.build_package(env["manager"], _request(env))
    parts = _parts(result)
    assert [p.key for p in result.parts] == ["eowr_html", "eowr_pdf", "bit_runs", "npt", "mud", "history",
                                            "approvals"]
    assert parts["eowr_html"].status == wp.INCLUDED
    assert (parts["eowr_pdf"].status, parts["eowr_pdf"].note) == (wp.NOT_INCLUDED, "not requested")
    assert (parts["bit_runs"].status, parts["bit_runs"].rows) == (wp.EMPTY, 0)      # no drilling parameters
    assert (parts["mud"].status, parts["mud"].rows) == (wp.INCLUDED, 2)
    assert (parts["approvals"].status, parts["approvals"].rows) == (wp.INCLUDED, 3)
    assert parts["npt"].status == wp.INCLUDED and parts["npt"].rows == 2
    assert result.status == wp.COMPLETE
    # written as .partial; nothing has the final name and nothing is audited yet
    assert os.path.isdir(result.partial_dir) and not os.path.exists(result.final_dir) and _audits(env) == []
    for part in result.parts:
        if part.sha256:
            assert wp.file_sha256(os.path.join(result.partial_dir, part.file)) == part.sha256
    assert wp.file_sha256(os.path.join(result.partial_dir, wp.MANIFEST)) == result.manifest_sha256
    manifest = json.loads(Path(result.partial_dir, wp.MANIFEST).read_text(encoding="utf-8"))
    assert manifest["label"] == "UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED"
    assert "not an approval" in manifest["approval_note"] and manifest["generated_by"] == "admin"
    assert manifest["scope"] == {"well_id": env["well"], "well": "SYN-A", "wellbore_id": None,
                                 "wellbore": "whole well (all wellbores)"}
    html = Path(result.partial_dir, "eowr.html").read_text(encoding="utf-8")
    assert "UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED" in html and "Provenance" in html

    final = wp.finalize_package(env["manager"], result)
    assert final == result.final_dir and os.path.isdir(final) and not os.path.exists(result.partial_dir)
    (details,), = _audits(env)
    assert json.loads(details)["manifest_sha256"] == result.manifest_sha256


def test_an_explicit_wellbore_narrows_every_part_that_can_be_narrowed(env):
    result = wp.build_package(env["manager"], _request(env, wellbore_id=env["sidetrack"]))
    parts = _parts(result)
    assert result.manifest["scope"]["wellbore_id"] == env["sidetrack"]
    assert parts["mud"].rows == 1 and parts["approvals"].rows == 2 and parts["npt"].rows == 1
    assert "does not narrow it" in parts["eowr_html"].scope                 # the EOWR engine is whole-well
    assert parts["history"].scope.startswith("whole well")
    with pytest.raises(wp.PackageError, match="not a wellbore of well"):
        wp.build_package(env["manager"], _request(env, "other", wellbore_id=env["other_bore"]))
    assert not os.path.exists(env["out"] / "other.partial")


def test_typed_names_are_never_shown_as_approvals(env):
    result = wp.build_package(env["manager"], _request(env))
    rows = _csv(os.path.join(result.partial_dir, "approvals.csv"))
    header = rows.index(list(wp.APPROVAL_COLUMNS))
    body = {(r[0].split(" ")[0], r[1]): dict(zip(wp.APPROVAL_COLUMNS, r)) for r in rows[header + 1:]}
    r1, r2 = body[("Daily", str(env["r1"]))], body[("Daily", str(env["r2"]))]
    assert r1["Approval record (workflow action)"].startswith("workflow 'approve' by admin at 2026-04-02T08:00:00")
    assert "not a signature" in r1["Approval record (workflow action)"]
    assert r2["Approval record (workflow action)"] == "No approval recorded in DrillMaster"
    proc = next(v for v in body.values() if v["Record"].startswith("Procedure"))
    assert proc["Typed names (NOT approvals)"] == "Prepared by: SYN Writer; Approved by: SYN Approver"
    assert proc["Approval record (workflow action)"].startswith("none")       # a typed name is not an approval
    assert rows[1] == ["Note", wp.APPROVAL_NOTE]


def test_a_package_never_overwrites_an_existing_folder(env):
    (env["out"] / "taken").mkdir()
    with pytest.raises(wp.PackageError, match="never overwrites"):
        wp.build_package(env["manager"], _request(env, "taken"))
    (env["out"] / "half.partial").mkdir()
    with pytest.raises(wp.PackageError, match="never overwrites"):
        wp.build_package(env["manager"], _request(env, "half"))
    assert os.listdir(env["out"] / "taken") == [] and os.listdir(env["out"] / "half.partial") == []


def test_verification_finds_changed_missing_and_unlisted_files_and_the_audit_record(env):
    manager = env["manager"]
    final = wp.finalize_package(manager, wp.build_package(manager, _request(env)))
    ok = wp.verify_package(final, manager)
    assert ok.ok and ok.checked == 6 and ok.audit.startswith("audit record #")
    assert wp.verify_package(final).audit == "not checked (no database)"
    with open(os.path.join(final, "npt_reconciliation.csv"), "a", encoding="utf-8") as handle:
        handle.write("edited\n")
    Path(final, "extra.txt").write_text("x", encoding="utf-8")
    os.remove(os.path.join(final, "mud_evaluation.csv"))
    bad = wp.verify_package(final, manager)
    assert not bad.ok
    assert "changed: npt_reconciliation.csv (SHA-256 differs from the manifest)" in bad.problems
    assert "missing: mud_evaluation.csv" in bad.problems and "unlisted: extra.txt" in bad.problems
    manifest = Path(final, wp.MANIFEST)
    manifest.write_text(manifest.read_text(encoding="utf-8").replace("SYN-A", "SYN-Z"), encoding="utf-8")
    forged = wp.verify_package(final, manager)
    assert "no matching audit record" in forged.problems and forged.audit.startswith("NO audit record")


def test_finalize_refuses_a_manifest_changed_after_writing_and_records_nothing(env):
    result = wp.build_package(env["manager"], _request(env))
    Path(result.partial_dir, wp.MANIFEST).write_text("{}", encoding="utf-8")
    with pytest.raises(wp.PackageError, match="manifest changed"):
        wp.finalize_package(env["manager"], result)
    assert _audits(env) == [] and not os.path.exists(result.final_dir)
    wp.discard_package(result)
    assert not os.path.exists(result.partial_dir)


def test_a_failing_part_is_recorded_as_failed_and_the_package_is_incomplete(env, monkeypatch):
    from core import calculation_history

    def broken(*_a, **_k):
        raise OSError("SYN disk error with report data")
    monkeypatch.setattr(calculation_history, "load_history", broken)
    result = wp.build_package(env["manager"], _request(env))
    history = _parts(result)["history"]
    assert (history.status, history.note, history.sha256) == (wp.FAILED, "OSError while writing this part", "")
    assert "report data" not in json.dumps(result.manifest)                # the type only, never the message
    assert result.status == wp.INCOMPLETE and _parts(result)["approvals"].status == wp.INCLUDED


def test_a_cancelled_build_leaves_no_folder(env):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(JobCancelled):
        wp.build_package(env["manager"], _request(env), cancel)
    assert os.listdir(env["out"]) == []


def test_the_pdf_is_qt_written_on_request(app, env):
    result = wp.build_package(env["manager"], _request(env, include_pdf=True))
    pdf = _parts(result)["eowr_pdf"]
    assert pdf.status == wp.INCLUDED and "QTextDocument" in pdf.note
    assert Path(result.partial_dir, "eowr.pdf").read_bytes()[:5] == b"%PDF-"


def test_no_pymupdf_in_the_package_path():
    for module in ("core/well_package.py", "tabs/well_package_panel.py"):
        tree = ast.parse(Path(module).read_text(encoding="utf-8"))
        names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not names & {"fitz", "pymupdf"}, module


def test_w11_builds_verifies_and_cleans_up_through_the_real_panel(app, env, monkeypatch):
    from tabs import w11_Export
    from tabs.well_package_panel import WellPackagePanel

    seen = []
    real = wp.build_package

    def recording(db, request, cancel_event=None):
        seen.append(threading.current_thread() is threading.main_thread())
        return real(db, request, cancel_event)
    monkeypatch.setattr(wp, "build_package", recording)
    tab = w11_Export.ExportWidget(db_manager=env["manager"])
    try:
        panel = tab.package_panel
        assert isinstance(panel, WellPackagePanel)
        tab.on_well_changed(env["well"], {"name": "SYN-A"})
        assert panel.wait() and panel.well_id == env["well"] and panel.well_name == "SYN-A"
        assert [panel.bore_combo.itemData(i) for i in range(panel.bore_combo.count())] == \
            [None, env["bore"], env["sidetrack"]]
        assert panel.build_into(str(env["out"]), wellbore_id=env["sidetrack"]) is not None
        assert panel.wait() and seen == [False]                  # written by a worker (read-only reader)
        assert panel.final_dir and os.path.isdir(panel.final_dir) and panel.table.rowCount() == 7
        assert panel.status.text().startswith("COMPLETE: ") and "audit record written" in panel.status.text()
        assert panel.verify(panel.final_dir) is not None and panel.wait()
        assert panel.verification.ok and panel.status.text().startswith("VERIFIED: 6 file(s)")
        assert panel.build_into(str(env["out"]), wellbore_id=env["other_bore"]) is None
        tab.on_selection_cleared()
        assert panel.well_id is None and not panel.build_btn.isEnabled() and panel.table.rowCount() == 0
        calls = []
        monkeypatch.setattr(WellPackagePanel, "shutdown", lambda _p, timeout_ms=5000: calls.append(timeout_ms) or True)
    finally:
        tab.cleanup()
        tab.deleteLater()
    assert calls == [5000]


def test_the_document_direction_comes_from_the_export_center(app, env):
    from tabs import w11_Export
    tab = w11_Export.ExportWidget(db_manager=env["manager"])
    try:
        assert tab.package_panel.document_direction() == "ltr"
        tab.direction_combo.setCurrentIndex(1)
        assert tab.package_panel.document_direction() == "rtl"
    finally:
        tab.cleanup()
        tab.deleteLater()


def test_a_selection_change_during_the_build_does_not_discard_the_package(app, env):
    """The package scope is the explicit request: navigating elsewhere while the worker writes must not turn
    the finished folder into an unaudited orphan (the M103 runner would reject it as STALE)."""
    from core.selection_manager import SelectionManager
    from tabs import w11_Export
    tab = w11_Export.ExportWidget(db_manager=env["manager"])
    try:
        panel = tab.package_panel
        tab.on_well_changed(env["well"], {"name": "SYN-A"})
        assert panel.wait()
        assert panel.build_into(str(env["out"])) is not None
        SelectionManager().select_period(date(2031, 7, 1), date(2031, 7, 31))     # the context token changes
        assert panel.wait() and panel.final_dir and os.path.isdir(panel.final_dir)
        assert len(_audits(env)) == 1 and not any(n.endswith(wp.PARTIAL_SUFFIX) for n in os.listdir(env["out"]))
    finally:
        SelectionManager().select_period(None, None)
        tab.cleanup()
        tab.deleteLater()
