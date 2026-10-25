"""Capture M46 screenshots of the running application with SYNTHETIC data.

Runs the real ``MainWindow`` against a throw-away database built by
``tests/synthetic_operations.py`` in a temporary directory, signs in through
the real authentication path, imports SYNTHETIC documents through the real
reviewed-import path and saves ``QWidget.grab()`` images of:

* the Home dashboard (fixture KPIs);
* search v2: an identifier query that must not list the SYN-DEV-012 note,
  and a Latin-diacritic query ("cafe") whose hit is highlighted as "café";
* the survey editor of a well with no report selected (fixed defect W1:
  only the well-level rows are listed, not every report's rows);
* the trajectory viewer: a picked station in 3D, the Plan / VS view, and the
  SYN-QA-03 well whose survey cannot be drawn (reason shown, no path).

Environment honesty: run with ``QT_QPA_PLATFORM=offscreen`` (raster
rendering, no window manager, bundled fonts).  Images show the
application's real widgets and data, not a native Windows desktop.

Usage::

    QT_QPA_PLATFORM=offscreen python tools/screenshots/capture_m46.py --out DIR
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


def _write_documents(folder: Path) -> list:
    folder.mkdir()
    (folder / "SYN_dev01_id_note.txt").write_text(
        "SYNTHETIC rig note for SYN-DEV-01\nSYNTHETIC café break after the casing run (label SYN_DEV_01_A)\n",
        encoding="utf-8")
    (folder / "SYN_dev012_id_note.txt").write_text(
        "SYNTHETIC rig note for SYN-DEV-012 (a different identifier)\n", encoding="utf-8")
    (folder / "SYN_generic_procedure.txt").write_text("SYNTHETIC generic procedure without a well name.",
                                                     encoding="utf-8")
    return sorted(folder.iterdir())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="drillmaster-m46-shots-"))
    os.environ.update({"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_DB_PATH": str(work / "synthetic.db"),
                       "DRILLMASTER_LOG_DIR": str(work / "logs"),
                       "DRILLMASTER_BACKUP_DIR": str(work / "backups"),
                       "DRILLMASTER_AI_IMPORT": "0"})
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(work / "settings"))
    from core.database import DatabaseManager
    from core.document_library import DocumentLibrary, extract_document
    from core.permissions import permissions, session_user
    from synthetic_operations import build_synthetic_operations

    app = QApplication.instance() or QApplication(sys.argv)
    password = secrets.token_urlsafe(18) + "aA1!"
    db = DatabaseManager(bootstrap_passwords={"admin": password})
    db.db_path = str(work / "synthetic.db")
    if not db.initialize():
        raise SystemExit(f"database initialization failed: {db.last_diagnostic}")
    ids = build_synthetic_operations(db, end_date=date.today() - timedelta(days=1))
    user = session_user(db.authenticate_user("admin", password))
    permissions.set_user(user)
    db.enforce_authorization(permissions)
    # SYN-DONE-04: one well-level survey row and two rows of its daily report.
    done, done_report = ids["done"], ids["done_report"]
    db.save_survey_records([{"well_id": done, "report_id": None, "md": 0.0, "inc": 0.0, "azi": 0.0, "tool": "GYRO"}],
                           replace_scope=(done, None))
    db.save_survey_records([{"well_id": done, "report_id": done_report, "md": md, "inc": inc, "azi": 90.0,
                             "tool": "MWD"} for md, inc in ((300.0, 1.0), (600.0, 2.0))],
                           replace_scope=(done, done_report))
    library = DocumentLibrary(db)
    for path in _write_documents(work / "documents"):
        library.import_reviewed(extract_document(path))
    library.close()

    from main_window import MainWindow

    window = MainWindow(db_manager=db, user=user, startup_result=None)
    window.resize(1600, 1000)
    window.show()
    _pump(app, 3.0)
    tabs = window.tab_widget

    def shot(name: str, widget=None):
        path = out / f"{name}.png"
        (widget or window).grab().save(str(path))
        print("saved", path)

    # 1. Home dashboard.
    tabs.setCurrentWidget(window.home_tab)
    window.home_tab.refresh()
    _pump(app, 2.0)
    shot("m46_home_dashboard")

    # 2. Search v2.
    documents = window.documents_tab
    documents.show_dialogs = False
    tabs.setCurrentWidget(documents)
    documents.refresh()
    for name, query in (("m46_search_identifier_precision", "SYN-DEV-01"), ("m46_search_latin_diacritics", "cafe")):
        documents.search_edit.setText(query)
        documents.run_search()
        documents.results.setCurrentRow(0)
        _pump(app, 0.8)
        shot(name)

    # 3. Survey editor: well selected, no report (W1).
    trajectory = window.trajectory_widget
    tabs.setCurrentWidget(trajectory)
    trajectory.current_report_id = None
    trajectory.on_well_changed(done, db.get_well_by_id(done) or {})
    trajectory.tab_widget.setCurrentWidget(trajectory.survey_data_tab)
    _pump(app, 1.0)
    shot("m46_survey_editor_well_scope")

    # 4. Trajectory viewer.
    # Through the widget's own well selection (on_well_changed -> update_tabs ->
    # viewer.set_context), so the Well combo and the viewer always agree.
    viewer = trajectory.viewer_tab
    trajectory.tab_widget.setCurrentWidget(viewer)
    trajectory.on_well_changed(ids["dev"], db.get_well_by_id(ids["dev"]) or {})
    viewer.view_tabs.setCurrentWidget(viewer.view3d)
    _pump(app, 1.0)
    x, y = viewer.view3d.projected_points()[45]
    viewer.view3d.pick_at(x, y)                               # the same path as a mouse click
    _pump(app, 0.8)
    shot("m46_trajectory_3d_picked_station")
    viewer.view_tabs.setCurrentIndex(0)
    _pump(app, 0.8)
    shot("m46_trajectory_plan_vs")
    trajectory.on_well_changed(ids["qa"], db.get_well_by_id(ids["qa"]) or {})
    viewer.view_tabs.setCurrentWidget(viewer.view3d)
    _pump(app, 1.0)
    shot("m46_trajectory_invalid_survey")

    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
