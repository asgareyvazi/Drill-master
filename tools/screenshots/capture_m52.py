"""Capture M52 screenshots of the real widgets (synthetic data, offscreen Qt).

Each image is produced in its own fresh interpreter (``--shot NAME``; the driver
runs them all): the W13 calculator is fragile when it shares a process with
other widgets.  Every image comes from the application's real widget classes
working on a throw-away temporary file database or a synthetic PDF written to a
temporary directory; ``QWidget.grab()`` saves it.

* trajectory comparison, offset well, CRS confirmed: centre-to-centre
  SCREENING result (tabs/trajectory_compare_panel.py, real worker);
* the same comparison with the CRS not confirmed: NOT ASSESSED and why;
* W13 balanced cement plug: SCREENING result with its source line;
* DDR import preview of a synthetic PDF holding several daily reports: the
  report split table and the blocked Confirm Import;
* W2 time log after a row was moved (time records reorder).

Environment honesty: ``QT_QPA_PLATFORM=offscreen`` (raster, no window
manager, bundled fonts), Linux.  Not a native Windows desktop.  No real well,
company, location or report data; no language model.

Usage::

    QT_QPA_PLATFORM=offscreen python tools/screenshots/capture_m52.py --out DIR
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ("trajectory_offset_screening", "trajectory_not_assessed_crs", "balanced_plug_screening",
         "ddr_pdf_split_preview", "ddr_time_log_reorder")


def _pump(app, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def _synthetic_wells(work: Path):
    from core.database import Company, Project, SurveyPoint, Well
    from synthetic_operations import make_file_database
    db = make_file_database(work / "synthetic-m52-shots.db")
    with db.session_scope() as session:
        company = Company(name="Synthetic Co", code="SYNC")
        session.add(company)
        session.flush()
        project = Project(name="Synthetic Field", code="SYNP", company_id=company.id)
        session.add(project)
        session.flush()
        ids = {}
        # relative synthetic coordinates only (no real location)
        for name, northing, easting, build in (("SYN-REF", 1000.0, 2000.0, 0.0), ("SYN-OFF", 1006.0, 2008.0, 2.0)):
            well = Well(name=name, code=name, project_id=project.id, northing=northing, easting=easting, rte_msl=10.0)
            session.add(well)
            session.flush()
            ids[name] = well.id
            for i, md in enumerate(range(0, 1500, 150)):
                session.add(SurveyPoint(well_id=well.id, md=float(md), inc=min(build * i, 30.0), azi=45.0))
    return db, ids


def shot_trajectory(app, out: Path, work: Path, confirmed: bool) -> Path:
    from tabs.trajectory_compare_panel import TrajectoryComparePanel
    db, ids = _synthetic_wells(work)
    panel = TrajectoryComparePanel(db)
    panel.resize(1100, 720)
    panel.set_well(ids["SYN-REF"])
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("offset"))
    panel.offset_combo.setCurrentIndex(panel.offset_combo.findData(ids["SYN-OFF"]))
    panel.crs_check.setChecked(confirmed)
    panel.show()
    panel.run()
    assert panel.wait_until_idle()
    _pump(app, 0.5)
    name = "trajectory_offset_screening" if confirmed else "trajectory_not_assessed_crs"
    path = out / f"m52_{name}.png"
    panel.grab().save(str(path))
    panel.cleanup()
    return path


def shot_plug(app, out: Path, work: Path) -> Path:
    from PySide6.QtWidgets import QMessageBox, QTabWidget

    from synthetic_operations import make_file_database
    for name in ("information", "warning", "critical"):
        setattr(QMessageBox, name, staticmethod(lambda *a, **k: None))
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
    db = make_file_database(work / "synthetic-m52-plug.db")
    tab = EngineeringCalculatorTab(db)
    tab.resize(1300, 860)
    tab.plug_pipe_id.setValue(2.764)
    tab.plug_yield.setValue(1.06)
    assert tab._plug_calculate().success
    widget, page = tab.plug_result, None
    while widget is not None:                          # bring the plug page to the front of every tab level
        parent = widget.parentWidget()
        if parent is not None and isinstance(parent.parentWidget(), QTabWidget):
            parent.parentWidget().setCurrentWidget(widget)
            page = page or widget
        widget = parent
    tab.show()
    _pump(app, 0.5)
    path = out / "m52_balanced_plug_screening.png"
    tab.grab().save(str(path))
    return path


def shot_pdf_split(app, out: Path, work: Path) -> Path:
    import fitz

    from core import ddr_pdf_split
    from dialogs.excel_import_dialog import ImportPreviewDialog
    texts = []
    for number, day in ((1, "2026-03-01"), (2, "2026-03-02"), (2, "2026-03-02"), (3, "04/03/2026")):
        texts.append(f"DAILY DRILLING REPORT\nWell: SYN-WELL-1\nReport No: {number}\nReport Date: {day}\n"
                     + "Synthetic operations summary line for the screenshot.\n" * 3)
    texts.insert(2, "Time log continued\n" + "Synthetic continuation line.\n" * 3)
    pdf = work / "synthetic-multi-report.pdf"
    with fitz.open() as doc:
        for text in texts:
            doc.new_page().insert_text((50, 60), text, fontsize=9)
        doc.save(str(pdf))
    split = ddr_pdf_split.analyse_pdf(pdf, expected_well="SYN-WELL-1")
    dialog = ImportPreviewDialog(str(pdf), {}, {"review": [], "pdf_split": split.to_json()})
    dialog.resize(1200, 760)
    dialog.show()
    _pump(app, 0.5)
    path = out / "m52_ddr_pdf_split_preview.png"
    dialog.grab().save(str(path))
    return path


def shot_reorder(app, out: Path, work: Path) -> Path:
    from datetime import time as clock
    from types import SimpleNamespace

    from tabs.w2_Daily_Report import DailyReportWidget
    widget = DailyReportWidget(db_manager=None)
    table = widget.time_24_table
    for start, end, text, npt in ((clock(0, 0), clock(6, 0), "Synthetic drilling ahead", False),
                                  (clock(6, 0), clock(9, 0), "Synthetic circulate and condition", False),
                                  (clock(9, 0), clock(11, 0), "Synthetic rig repair (NPT)", True),
                                  (clock(11, 0), clock(14, 0), "Synthetic trip out", False)):
        widget.add_time_log_row(table, SimpleNamespace(
            time_from=start, time_to=end, duration=0, main_phase="DRL", main_code="NPT-B" if npt else "DRL",
            sub_code="", status="Normal", is_npt=npt, activity_description=text, contractor=""))
    table.setCurrentCell(2, 0)
    assert widget.move_time_log_row(table, -1)      # the NPT record moved up one place
    widget.resize(1400, 900)
    # show the page that holds the time log
    from PySide6.QtWidgets import QTabWidget
    node = table
    while node is not None:
        parent = node.parentWidget()
        if parent is not None and isinstance(parent.parentWidget(), QTabWidget):
            parent.parentWidget().setCurrentWidget(node)
        node = parent
    widget.show()
    _pump(app, 0.5)
    path = out / "m52_ddr_time_log_reorder.png"
    widget.grab().save(str(path))
    return path


def run_one(shot: str, out: Path) -> Path:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
    work = Path(tempfile.mkdtemp(prefix="drillmaster-m52-shots-"))
    for key, value in (("DRILLMASTER_ENV", "test"), ("DRILLMASTER_DATA_DIR", str(work)),
                       ("DRILLMASTER_DB_PATH", str(work / "app.db")), ("DRILLMASTER_BACKUP_DIR", str(work / "b")),
                       ("DRILLMASTER_AI_IMPORT", "0")):
        os.environ[key] = value
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    if shot.startswith("trajectory"):
        return shot_trajectory(app, out, work, confirmed=(shot == "trajectory_offset_screening"))
    return {"balanced_plug_screening": shot_plug, "ddr_pdf_split_preview": shot_pdf_split,
            "ddr_time_log_reorder": shot_reorder}[shot](app, out, work)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--shot", choices=SHOTS)
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.shot:
        print(run_one(args.shot, out))
        return 0
    failed = []
    for shot in SHOTS:
        proc = subprocess.run([sys.executable, __file__, "--out", str(out), "--shot", shot], cwd=str(ROOT))
        if proc.returncode:
            failed.append(f"{shot} (exit {proc.returncode})")
    if failed:
        print("failed:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
