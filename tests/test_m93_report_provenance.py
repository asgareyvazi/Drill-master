"""M93: every report carries scope, sources, revisions, methods and the UNSIGNED label in HTML, PDF, Excel
and CSV; LTR/RTL; W11 offers CSV and the text direction.

Synthetic records only. Offscreen Qt (PDF through QTextDocument; no PyMuPDF).
"""
from __future__ import annotations

import csv
import os
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QTextDocument  # noqa: E402

from core import cost_semantics, export_jobs, operational_time  # noqa: E402
from core import report_engine as engines  # noqa: E402
from core import report_provenance as rp  # noqa: E402
from core import survey_revisions as sr  # noqa: E402
from core.database import Base, DailyReport, WellPlan  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402

MAG = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 300.0, "inc": 0.0, "azi": 0.0},
       {"md": 600.0, "inc": 20.0, "azi": 357.0}]
ENGINES = (("ddr", "DDRReportEngine"), ("eowr", "EOWRReportEngine"), ("npt", "NPTReportEngine"),
           ("cost", "CostReportEngine"), ("plan", "PlanReportEngine"))


@pytest.fixture
def env(tmp_path, monkeypatch):
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    manager = _open(tmp_path / "m93.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    well, bore = ids["A"]
    with manager.session_scope() as s:
        report = DailyReport(well_id=well, wellbore_id=bore, report_date=date(2026, 1, 2), report_number=7,
                             depth_0000=0, depth_2400=100)
        s.add(report)
        s.add(DailyReport(well_id=well, report_date=date(2026, 1, 5), report_number=8))
        s.add(WellPlan(well_id=well, plan_name="SYN plan"))
        s.flush()
        rid = report.id
    yield manager, {"well": well, "bore": bore, "report": rid}
    manager.close()


def _target(kind, ids):
    return ids["report"] if kind == "ddr" else ids["well"]


def test_sources_are_real_tables_and_methods_are_catalogued():
    tables = set(Base.metadata.tables)
    for kind in rp.KINDS:
        assert all(t in tables for t in rp.SOURCES[kind] if " " not in t), kind
    from core import method_catalogue as mc
    ids = {e.method_id for e in mc.catalogue()}
    assert all(m in ids for kind in rp.KINDS for m in rp.METHODS[kind])
    with pytest.raises(ValueError):
        rp.build(None, "memo", 1)


def test_ddr_provenance_scope_revisions_and_methods(env):
    manager, ids = env
    prov = rp.build(manager, "ddr", ids["report"])
    assert "SYN-A" in prov["scope"]["well"] and f"(id {ids['bore']})" in prov["scope"]["wellbore"]
    assert prov["scope"]["report"].startswith("#7 of 2026-01-02") and prov["scope"]["period"] == "2026-01-02 – 2026-01-02"
    assert "Report revision: none recorded" in prov["revisions"]
    assert "Survey revision: none recorded" in prov["revisions"]          # never invented
    assert any(operational_time.TIME_SUMMARY_VERSION in m for m in prov["methods"])
    assert "1 daily report(s) in scope" in prov["sources"] and prov["label"] == rp.LABEL
    saved = sr.save_revision(manager, ids["well"], MAG, wellbore_id=ids["bore"], depth_datum="RKB",
                             azimuth_reference="true")
    prov = rp.build(manager, "ddr", ids["report"])
    assert any(r.startswith(f"Survey revision {saved['revision']} (id {saved['id']}") for r in prov["revisions"])
    well = rp.build(manager, "cost", ids["well"])
    assert well["scope"]["wellbore"] == "all wellbores of the well" and "2 daily report(s) in scope" in well["sources"]
    assert any(cost_semantics.COST_SEMANTICS_VERSION in m for m in well["methods"])


@pytest.mark.parametrize("kind,cls", ENGINES)
def test_every_engine_writes_provenance_in_every_format(env, tmp_path, kind, cls):
    manager, ids = env
    engine = getattr(engines, cls)(manager)
    html_path, pdf_path = tmp_path / f"{kind}.html", tmp_path / f"{kind}.pdf"
    assert engine.generate(_target(kind, ids), str(html_path), "html")
    text = html_path.read_text(encoding="utf-8")
    assert text.index(rp.LABEL) < text.index("Provenance")                 # banner first, block last
    assert "scope.well" in text and "revision" in text and rp.PROVENANCE_VERSION in text
    assert engine.generate(_target(kind, ids), str(pdf_path), "pdf")
    assert pdf_path.read_bytes()[:5] == b"%PDF-" and engine.last_provenance["scope"]["kind"] == kind
    xlsx = tmp_path / f"{kind}.xlsx"
    assert engine.generate(_target(kind, ids), str(xlsx), "excel")
    from openpyxl import load_workbook
    book = load_workbook(xlsx)
    assert book.sheetnames[0] == "Provenance" and book["Provenance"]["B1"].value == rp.LABEL
    out = tmp_path / f"{kind}.csv"
    assert engine.generate(_target(kind, ids), str(out), "csv")
    rows = list(csv.reader(open(out, encoding="utf-8-sig")))
    assert rows[0] == ["# status", rp.LABEL] and ["# scope.kind", kind] in rows


def test_rtl_reaches_html_pdf_layout_and_excel(env, tmp_path):
    manager, ids = env
    engine = engines.NPTReportEngine(manager)
    engine.direction = "rtl"
    path = tmp_path / "npt.html"
    assert engine.generate(ids["well"], str(path), "html")
    text = path.read_text(encoding="utf-8")
    assert '<html dir="rtl"' in text.lower() or 'dir="rtl"' in text[:200]
    doc = QTextDocument()
    doc.setHtml(text)                                                      # the same HTML the PDF writer prints
    block, directions = doc.begin(), set()
    while block.isValid():
        if block.text().strip():
            directions.add(block.blockFormat().layoutDirection())
        block = block.next()
    assert directions == {Qt.RightToLeft}
    xlsx = tmp_path / "npt.xlsx"
    assert engine.generate(ids["well"], str(xlsx), "excel")
    from openpyxl import load_workbook
    assert all(ws.sheet_view.rightToLeft for ws in load_workbook(xlsx).worksheets)
    ltr = engines.NPTReportEngine(manager)
    assert ltr.generate(ids["well"], str(tmp_path / "ltr.html"), "html")
    assert 'dir="ltr"' in (tmp_path / "ltr.html").read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        rp.build(manager, "npt", ids["well"], direction="up")


def test_export_jobs_carry_direction_and_csv(env, tmp_path):
    manager, ids = env
    assert export_jobs.extension_for("csv") == ".csv"
    job = export_jobs.ExportJob("cost", "Cost", str(tmp_path / "c.html"), ids["well"], "html", direction="rtl")
    assert export_jobs.GENERATORS["cost"](manager, job)
    assert 'dir="rtl"' in (tmp_path / "c.html").read_text(encoding="utf-8")
    jobs = export_jobs.plan_batch(well_id=ids["well"], folder=str(tmp_path), fmt="csv", timestamp="T",
                                  selected=["eowr", "ddr"], ddr_reports=[{"id": ids["report"], "report_number": 7}],
                                  direction="rtl")
    assert {j.direction for j in jobs} == {"rtl"} and all(j.path.endswith(".csv") for j in jobs)


def test_w11_offers_csv_and_direction(env):
    from tabs.w11_Export import ExportWidget
    manager, _ids = env
    tab = ExportWidget(db_manager=manager)
    try:
        assert [tab.ddr_fmt.itemText(i) for i in range(tab.ddr_fmt.count())] == ["PDF", "HTML", "Excel", "CSV"]
        assert tab.direction() == "ltr"
        tab.direction_combo.setCurrentIndex(1)
        assert tab.direction() == "rtl"
    finally:
        tab.deleteLater()


def test_no_pymupdf_in_the_report_path():
    import ast
    for module in (engines, rp, export_jobs):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not names & {"fitz", "pymupdf"}, module.__name__
