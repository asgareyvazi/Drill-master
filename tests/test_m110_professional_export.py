"""M110: professional export - the real report revision (never "Rev 0"), names as recorded are not an approval,
the approval workflow record is shown as a workflow status, M93 provenance in the workbook and the PDF in both
text directions, Mud Chemicals always present with its source, per-report workbooks in batches.

Synthetic records only; temporary SQLite; offscreen Qt (PDF through QTextDocument; no PyMuPDF).
"""
from __future__ import annotations

import ast
import json
import re
import os
from datetime import date, datetime
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

from core import export_jobs  # noqa: E402
from core import professional_export as pe  # noqa: E402
from core import report_provenance as rp  # noqa: E402
from core.database import ApprovalAction, DailyReport, MudReport, ReportRevision, Well  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402

LABEL = "UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED"


@pytest.fixture
def env(tmp_path, monkeypatch):
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    manager = _open(tmp_path / "m110.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    well, bore = ids["A"]
    with manager.session_scope() as s:
        first = DailyReport(well_id=well, wellbore_id=bore, report_date=date(2026, 1, 2), report_number=7,
                            depth_0000=0, depth_2400=100, summary="SYN <b>bold</b> & co")
        second = DailyReport(well_id=well, report_date=date(2026, 1, 5), report_number=8)
        s.add_all([first, second])
        s.flush()
        s.add(MudReport(well_id=well, report_id=first.id, report_date=date(2026, 1, 2), mw=75.0,
                        chemicals_json=json.dumps([{"name": "SYN barite", "quantity": 12, "unit": "sx"}])))
        ids = {"well": well, "bore": bore, "report": first.id, "bare": second.id}
    yield manager, ids
    manager.close()


def _add_revision_and_approval(manager, report_id):
    with manager.session_scope() as s:
        s.add(ReportRevision(report_id=report_id, revision_no=1, status="Submitted", snapshot={},
                             created_at=datetime(2026, 1, 3, 8, 0)))
        s.add(ReportRevision(report_id=report_id, revision_no=2, status="Approved", snapshot={},
                             created_at=datetime(2026, 1, 3, 9, 30)))
        s.add(ApprovalAction(report_id=report_id, action="approve", status="Approved", user_id=None,
                             created_at=datetime(2026, 1, 3, 9, 30)))


def test_revision_is_the_stored_one_or_none_recorded_never_rev_0(env):
    manager, ids = env
    assert pe.ProfessionalExportMetadata.build(manager, ids["well"], report_id=ids["report"])["Revision"] == \
        "No report revision recorded"
    whole = pe.ProfessionalExportMetadata.build(manager, ids["well"])["Revision"]
    assert whole.startswith("Whole-well export") and pe.PROFESSIONAL_TEMPLATE_VERSION in whole
    _add_revision_and_approval(manager, ids["report"])
    meta = pe.ProfessionalExportMetadata.build(manager, ids["well"], report_id=ids["report"])
    assert meta["Revision"] == "Report revision 2 (Approved, 2026-01-03 09:30)"
    for path in ("core/professional_export.py", "core/managers.py"):
        assert not re.search(r'[:=]\s*["\']Rev 0["\']', Path(path).read_text(encoding="utf-8")), path


def test_names_are_not_an_approval_and_the_workflow_record_is_labelled(env):
    manager, ids = env
    meta = pe.ProfessionalExportMetadata.build(manager, ids["well"], report_id=ids["report"])
    assert meta["Approved By"] == meta["Prepared By"] == pe.NOT_RECORDED_NAME
    assert meta["Approval Record"] == pe.NO_APPROVAL and meta["Signature Status"] == LABEL
    _add_revision_and_approval(manager, ids["report"])
    record = pe.ProfessionalExportMetadata.build(manager, ids["well"], report_id=ids["report"])["Approval Record"]
    assert record == ("Workflow status Approved set by unknown user on 2026-01-03 09:30 "
                      "(workflow status only — not a signature, not a release approval)")
    assert pe.ProfessionalExportMetadata.build(manager, ids["well"], report_id=ids["bare"])["Approval Record"] == \
        pe.NO_APPROVAL                                                      # another report's approval never leaks


@pytest.mark.parametrize("direction", ["ltr", "rtl"])
def test_the_workbook_carries_provenance_revision_and_mud_chemicals(env, tmp_path, direction):
    from openpyxl import load_workbook

    manager, ids = env
    _add_revision_and_approval(manager, ids["report"])
    exporter = pe.ProfessionalExcelExport(manager)
    exporter.direction = direction
    out = tmp_path / f"pro_{direction}.xlsx"
    assert exporter.export(ids["well"], str(out), report_id=ids["report"])
    book = load_workbook(out)
    assert book.sheetnames[0] == "Provenance"
    assert set(pe.ProfessionalExcelExport.SHEETS) <= set(book.sheetnames) and "Mud Chemicals" in book.sheetnames
    prov = {(r[0], r[1]) for r in book["Provenance"].iter_rows(values_only=True)}
    assert ("status", LABEL) in prov and ("direction", direction) in prov
    assert ("revision", "Report revision 2 (Approved, 2026-01-03T09:30:00)") in prov
    assert ("scope.report", f"#7 of 2026-01-02 (id {ids['report']})") in prov
    assert all(bool(ws.sheet_view.rightToLeft) == (direction == "rtl") for ws in book.worksheets)
    summary = {r[0]: r[1] for r in book["Executive Summary"].iter_rows(values_only=True) if r[0]}
    assert summary["Revision"] == "Report revision 2 (Approved, 2026-01-03 09:30)"
    assert summary["Approved By"] == pe.NOT_RECORDED_NAME and summary["Signature Status"] == LABEL
    chem = [r for r in book["Mud Chemicals"].iter_rows(values_only=True)]
    assert chem[0][:3] == ("mud_report_id", "report_id", "mud_report_date") and chem[1][3] == "SYN barite"
    assert chem[1][1] == ids["report"]


def test_a_report_without_mud_states_it_and_whole_well_names_the_latest_mud_report(env, tmp_path):
    from openpyxl import load_workbook

    manager, ids = env
    bare = tmp_path / "bare.xlsx"
    assert pe.ProfessionalExcelExport(manager).export(ids["well"], str(bare), report_id=ids["bare"])
    assert [r for r in load_workbook(bare)["Mud Chemicals"].iter_rows(values_only=True)] == [
        ("No mud report in scope",)]
    whole = tmp_path / "whole.xlsx"
    exporter = pe.ProfessionalExcelExport(manager)
    assert exporter.export(ids["well"], str(whole))
    rows = [r for r in load_workbook(whole)["Mud Chemicals"].iter_rows(values_only=True)]
    assert rows[0][0] == "Latest mud report of the well only (whole-well export)" and not any(rows[0][1:])
    assert exporter.last_provenance["scope"]["report"] == "all daily reports of the well"
    assert exporter.last_provenance["scope"]["title"] == "Professional workbook (whole well)"


@pytest.mark.parametrize("direction", ["ltr", "rtl"])
def test_the_pdf_has_the_banner_provenance_and_escaped_text(env, tmp_path, direction):
    manager, ids = env
    with manager.session_scope() as s:
        s.get(Well, ids["well"]).name = "SYN <i>well</i> & A"
    exporter = pe.ProfessionalPDFExport(manager)
    exporter.direction = direction
    out = tmp_path / f"pro_{direction}.pdf"
    assert exporter.export(ids["well"], str(out), report_id=ids["report"]) and out.stat().st_size > 0
    html = exporter.last_html
    assert f'dir="{direction}"' in html and LABEL in html and "dm-provenance" in html
    assert "Names as recorded — not an approval" in html and "<th>Signature</th>" not in html
    assert "SYN &lt;b&gt;bold&lt;/b&gt; &amp; co" in html and "<b>bold</b>" not in html
    assert "SYN &lt;i&gt;well&lt;/i&gt; &amp; A" in html and "<i>well</i>" not in html
    assert "No report revision recorded" in html and pe.NO_APPROVAL in html


def test_batches_carry_direction_and_can_write_one_workbook_per_report(env, tmp_path):
    manager, ids = env
    reports = [{"id": ids["report"], "report_number": 7, "report_date": "2026-01-02"},
               {"id": ids["bare"], "report_number": 8, "report_date": "2026-01-05"}]
    jobs = export_jobs.plan_batch(well_id=ids["well"], folder=str(tmp_path), fmt="pdf", timestamp="T",
                                  selected=["professional"], ddr_reports=reports, direction="rtl",
                                  professional_per_report=True)
    assert [os.path.basename(j.path) for j in jobs] == [
        "Professional_16Sheets_T.xlsx", "Professional_T.pdf", "Professional_16Sheets_7_2026-01-02_T.xlsx",
        "Professional_16Sheets_8_2026-01-05_T.xlsx"]
    assert [j.report_id for j in jobs] == [None, None, ids["report"], ids["bare"]]
    assert {j.direction for j in jobs} == {"rtl"}
    default = export_jobs.plan_batch(well_id=ids["well"], folder=str(tmp_path), fmt="pdf", timestamp="T",
                                     selected=["professional"], ddr_reports=reports)
    assert len(default) == 2                                              # opt-in only
    from openpyxl import load_workbook
    assert export_jobs.GENERATORS["professional_excel"](manager, jobs[3])
    book = load_workbook(jobs[3].path)
    prov = {(r[0], r[1]) for r in book["Provenance"].iter_rows(values_only=True)}
    assert ("scope.report", f"#8 of 2026-01-05 (id {ids['bare']})") in prov and ("direction", "rtl") in prov
    assert ("revision", "Report revision: none recorded") in prov


def test_the_old_export_coordinator_uses_the_same_metadata(env):
    from core.managers import ExportCoordinator

    manager, ids = env
    meta = ExportCoordinator(manager).get_export_metadata(ids["well"], ids["report"])
    assert meta["revision"] == "No report revision recorded" and meta["approved_by"] == pe.NOT_RECORDED_NAME
    assert meta["data_quality"] != "Validated" and meta["signature_status"] == LABEL


def test_w11_offers_the_per_report_workbook_and_honest_labels(env):
    from tabs.w11_Export import ExportWidget

    manager, _ids = env
    tab = ExportWidget(db_manager=manager)
    try:
        assert tab.batch_professional.text().endswith("(16 core sheets + sections)")
        assert not tab.batch_professional_per_report.isChecked()
    finally:
        tab.deleteLater()


def test_no_pymupdf_in_the_professional_export():
    tree = ast.parse(Path("core/professional_export.py").read_text(encoding="utf-8"))
    names = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
             for alias in node.names} | {node.module.split(".")[0] for node in ast.walk(tree)
                                         if isinstance(node, ast.ImportFrom) and node.module}
    assert not names & {"fitz", "pymupdf"}
    assert rp.KINDS[-2:] == ("workbook", "workbook_report")
