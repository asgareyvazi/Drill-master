"""Capture M45 screenshots of the running application with SYNTHETIC data.

Runs the real ``MainWindow`` against a throw-away database built by
``tests/synthetic_operations.py`` in a temporary directory, signs in through
the real authentication path, imports SYNTHETIC documents through the real
reviewed-import path, links one through the real link dialog and saves
``QWidget.grab()`` images of:

* the link dialog with an unconfirmed suggestion, and the linked document;
* a Persian-form query matching Arabic-letter text (highlighted original);
* the Well Info and Daily Report pages listing their linked documents;
* the trajectory viewer's 3D tab with a picked station, and a preset view.

Environment honesty: normally run with ``QT_QPA_PLATFORM=offscreen`` (raster
rendering, no window manager, bundled fonts).  Images show the application's
real widgets and data, not a native Windows desktop.  Mouse rotation is not
captured; preset view angles are set through the tab's own controls.

Usage::

    QT_QPA_PLATFORM=offscreen python tools/screenshots/capture_m45.py --out DIR
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
ARABIC_TEXT = ("\u06af\u0632\u0627\u0631\u0634 \u0645\u0635\u0646\u0648\u0639\u064a \u0644\u0648\u0644\u0647 "
               "\u062c\u062f\u0627\u0631\u064a \u0628\u0631\u0627\u064a \u0686\u0627\u0647 SYN-DEV-01\n"
               "\u0643\u0641\u0634\u0643 \u0644\u0648\u0644\u0647 \u062f\u0631 \u0639\u0645\u0642 1250 "
               "\u0645\u062a\u0631 \u0646\u0635\u0628 \u0634\u062f\n"
               "SYNTHETIC casing shoe test passed")                 # Arabic yeh/kaf, cp1256-encodable


def _pump(app, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def _write_documents(folder: Path) -> list:
    import fitz
    folder.mkdir()
    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "SYNTHETIC daily drilling summary.\nWell SYN-DEV-01, section 12 1/4 in.",
                               fontsize=12)
    pdf.new_page().insert_text((72, 72), "SYNTHETIC survey note: station at MD 1800 m, inclination 40 deg.\n"
                                         "Plan check against SYN-DEV-01 directional plan.", fontsize=12)
    pdf.save(str(folder / "SYN_dev01_daily_summary.pdf"))
    (folder / "SYN_dev01_casing_note_fa.txt").write_bytes(ARABIC_TEXT.encode("cp1256"))
    (folder / "SYN_generic_procedure.txt").write_text("SYNTHETIC generic procedure without a well name.",
                                                     encoding="utf-8")
    return sorted(folder.iterdir())


def _scroll_to(app, widget) -> None:
    """Scroll the page's own QScrollArea to ``widget`` (as a user would)."""
    from PySide6.QtWidgets import QScrollArea
    parent = widget.parentWidget()
    while parent is not None and not isinstance(parent, QScrollArea):
        parent = parent.parentWidget()
    if parent is not None:
        parent.ensureWidgetVisible(widget, 0, 40)
    _pump(app, 0.5)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="drillmaster-m45-shots-"))
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
    library = DocumentLibrary(db)
    documents_by_name = {}
    for path in _write_documents(work / "documents"):
        outcome = library.import_reviewed(extract_document(path))
        documents_by_name[path.name] = outcome.document_id
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

    # 1. Link dialog: the well name in the text is only a suggestion.
    documents = window.documents_tab
    documents.show_dialogs = False
    tabs.setCurrentWidget(documents)
    documents.refresh()
    documents.open_document(documents_by_name["SYN_dev01_daily_summary.pdf"], 2)
    _pump(app, 0.5)
    documents.link_selected()
    dialog = documents.pending_link_dialog
    dialog.resize(1100, 640)
    dialog.show()
    _pump(app, 0.8)
    shot("m45_link_dialog_suggestion_unconfirmed", dialog)
    report_id = ids["reports"][6]
    dialog.select_well(ids["dev"])
    dialog.select_report(report_id)
    _pump(app, 0.5)
    shot("m45_link_dialog_confirmed_choice", dialog)
    documents.apply_link_dialog(dialog, True)
    dialog.close()
    _pump(app, 0.5)
    shot("m45_documents_linked_status")

    # 2. Persian-form query against Arabic-letter text.
    documents.search_edit.setText("\u0644\u0648\u0644\u0647 \u062c\u062f\u0627\u0631\u06cc")   # Persian yeh
    documents.run_search()
    documents.results.setCurrentRow(0)
    _pump(app, 0.8)
    shot("m45_documents_persian_search")
    documents.link_selected()                                 # link the casing note to the well only
    note = documents.pending_link_dialog
    note.select_well(ids["dev"])
    documents.apply_link_dialog(note, True)

    # 3. Well and report pages.
    well = db.get_well_by_id(ids["dev"]) or {}
    window.sel_manager.select_well(ids["dev"], well)
    window.well_info_tab.load_well_by_id(ids["dev"])
    tabs.setCurrentWidget(window.well_info_tab)
    _pump(app, 1.0)
    _scroll_to(app, window.well_info_tab.related_documents)
    shot("m45_well_page_related_documents")
    window.daily_report_tab.load_report_by_id(report_id)
    tabs.setCurrentWidget(window.daily_report_tab)
    _pump(app, 1.0)
    _scroll_to(app, window.daily_report_tab.related_documents)
    shot("m45_report_page_related_documents")

    # 4. 3D survey view.
    viewer = window.trajectory_widget.viewer_tab
    tabs.setCurrentWidget(window.trajectory_widget)
    window.trajectory_widget.tab_widget.setCurrentWidget(viewer)
    viewer.select_well(ids["dev"])
    viewer.view_tabs.setCurrentWidget(viewer.view3d)
    _pump(app, 1.0)
    x, y = viewer.view3d.projected_points()[45]
    viewer.view3d.pick_at(x, y)                               # the same path as a mouse click
    _pump(app, 0.8)
    shot("m45_trajectory_3d_picked_station")
    viewer.view3d.preset_combo.setCurrentIndex(1)            # Top (plan, north up)
    _pump(app, 0.8)
    shot("m45_trajectory_3d_top_preset")
    viewer.view_tabs.setCurrentIndex(0)                       # the same station in the 2D plan
    _pump(app, 0.8)
    shot("m45_trajectory_plan_same_station")

    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
