"""Capture screenshots of the running application with SYNTHETIC data (M44).

Runs the real ``MainWindow`` against a throw-away database built by
``tests/synthetic_operations.py`` in a temporary directory, signs in through
the real authentication path, and saves ``QWidget.grab()`` images.

Environment honesty: this is normally run with ``QT_QPA_PLATFORM=offscreen``
(raster rendering, no window manager, bundled fonts).  Images show the
application's real widgets and data, not a native Windows desktop.

Usage::

    QT_QPA_PLATFORM=offscreen python tools/screenshots/capture_m44.py --out DIR --stage after
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _pump(app, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def _tab_index(tabs, text: str) -> int:
    for index in range(tabs.count()):
        if text in tabs.tabText(index):
            return index
    raise LookupError(text)


def _capture_documents(app, window, documents, work: Path, shot) -> None:
    """Generate SYNTHETIC files, review them in the real dialog, import, search."""
    import fitz

    from core.document_library import extract_batch
    from tabs.documents_tab import DocumentReviewDialog

    folder = work / "documents"
    folder.mkdir()
    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "SYNTHETIC casing tally: 9 5/8 in shoe set at 1250 m.\n"
                                         "Cement returns observed at surface.", fontsize=12)
    pdf.new_page()                                                     # page without a text layer
    pdf.new_page().insert_text((72, 72), "SYNTHETIC mud weight increased to 1.25 sg after a gas peak.",
                               fontsize=12)
    pdf.save(str(folder / "SYN_end_of_section_report.pdf"))
    (folder / "SYN_rig_notes_fa.txt").write_bytes(
        "يادداشت مصنوعي حفاري\nفشار پمپ 2500 psi\nSYNTHETIC casing shoe test passed".encode("cp1256"))
    (folder / "SYN_broken.pdf").write_bytes(b"%PDF-1.4 truncated synthetic file")

    window.tab_widget.setCurrentWidget(documents)
    _pump(app, 0.5)
    shot("documents_empty")
    extracts = extract_batch(sorted(folder.iterdir()))                   # same call as the worker
    dialog = DocumentReviewDialog(extracts, documents.library, window)
    dialog.show()
    dialog.file_list.setCurrentRow(1)                                  # the partial PDF
    _pump(app, 0.8)
    shot("documents_review_dialog", dialog)
    selected, excluded = dialog.results()
    dialog.close()
    documents.import_reviewed(selected, excluded)
    documents.search_edit.setText("casing shoe")
    documents.run_search()
    documents.results.setCurrentRow(0)
    _pump(app, 0.8)
    shot("documents_search_source")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--stage", choices=("before", "after"), required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="drillmaster-m44-shots-"))
    os.environ.update({"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_DB_PATH": str(work / "synthetic.db"),
                       "DRILLMASTER_LOG_DIR": str(work / "logs"),
                       "DRILLMASTER_BACKUP_DIR": str(work / "backups")})
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

    from PySide6.QtWidgets import QApplication

    from core.database import DatabaseManager
    from core.permissions import permissions
    from synthetic_operations import build_synthetic_operations

    app = QApplication.instance() or QApplication(sys.argv)
    password = secrets.token_urlsafe(18) + "aA1!"
    db = DatabaseManager(bootstrap_passwords={"admin": password})
    db.db_path = str(work / "synthetic.db")
    if not db.initialize():
        raise SystemExit(f"database initialization failed: {db.last_diagnostic}")
    ids = build_synthetic_operations(db, end_date=date.today() - timedelta(days=1))
    account = db.authenticate_user("admin", password)
    from core.permissions import session_user
    user = session_user(account)          # same session shape as every login path
    permissions.set_user(user)
    db.enforce_authorization(permissions)

    from main_window import MainWindow

    window = MainWindow(db_manager=db, user=user, startup_result=None)
    window.resize(1600, 1000)
    window.show()
    _pump(app, 3.0)
    tabs = window.tab_widget

    def shot(name: str, widget=None):
        target = widget or window
        path = out / f"{args.stage}_{name}.png"
        target.grab().save(str(path))
        print("saved", path)

    tabs.setCurrentIndex(_tab_index(tabs, "Home"))
    home = window.home_tab
    if hasattr(home, "wait_for_load"):        # M44 dashboard loads in a worker
        home.wait_for_load()
    _pump(app, 2.5)
    shot("home_dashboard")
    drilled = False
    if hasattr(home, "open_selected_trajectory"):   # M44 drill-down: dashboard row -> viewer
        for row in range(home.wells_table.rowCount()):
            if home.wells_table.item(row, 0).text() == "SYN-QA-03":
                home.wells_table.selectRow(row)
                home.open_trajectory_btn.click()
                drilled = True
                break
        _pump(app, 1.5)
        if drilled:
            shot("home_drilldown_trajectory_qa")

    well = db.get_well_by_id(ids["dev"]) or {}
    window.sel_manager.select_well(ids["dev"], well)
    tabs.setCurrentIndex(_tab_index(tabs, "Trajectory"))
    _pump(app, 1.0)
    trajectory = window.trajectory_widget
    viewer = getattr(trajectory, "viewer_tab", None)
    if viewer is not None:                     # M44 whole-well viewer
        trajectory.tab_widget.setCurrentWidget(viewer)
        viewer.select_well(ids["dev"])
        _pump(app, 1.5)
        shot("trajectory_viewer_plan")
        viewer.view_tabs.setCurrentIndex(1)
        if viewer.stations:
            viewer.select_station(len(viewer.stations) - 1)
        _pump(app, 0.8)
        shot("trajectory_viewer_vertical_section")
        window.sel_manager.select_well(ids["qa"], db.get_well_by_id(ids["qa"]) or {})
        _pump(app, 1.0)
        shot("trajectory_viewer_review_required")
    else:                                      # pre-M44 per-report plot tab
        window.sel_manager.select_report(ids["reports"][6], {"id": ids["reports"][6]})
        _pump(app, 0.5)
        plot_tab = trajectory.plot_tab
        trajectory.tab_widget.setCurrentWidget(plot_tab)
        plot_tab.load_for_report(ids["reports"][6])
        plot_tab.plot_trajectory()
        _pump(app, 1.0)
        shot("trajectory_plot_plan")
        plot_tab.plot_tabs.setCurrentIndex(1)
        _pump(app, 0.5)
        shot("trajectory_plot_side")

    documents = getattr(window, "documents_tab", None)
    if documents is not None:                  # M44 reviewed document import + search
        _capture_documents(app, window, documents, work, shot)

    # Closing the window can open a modal "unsaved changes" prompt, which
    # never returns offscreen; the throw-away database needs no clean close.
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
