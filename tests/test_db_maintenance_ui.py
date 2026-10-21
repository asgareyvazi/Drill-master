"""Subprocess-isolated UI test for Tools > Backup Database Now / Restore Database (M43).

The services are covered Qt-free in test_db_backup_service.py and
test_db_restore_service.py. This drives the real dialog and the MainWindow
slots against a synthetic temporary database and proves that:
  * the restore dialog lists verified backups, refuses newer-schema backups and
    only enables Restore after a selection AND the explicit confirmation;
  * the window is frozen and every autosave is paused while the worker runs,
    and the window cannot be closed during the operation;
  * a successful restore is reported only after the service verified it and
    then forces a restart (close without saving stale screens);
  * a failed restore leaves the data unchanged and the window usable again;
  * a viewer is refused by the service even when the slot is invoked.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("PySide6")


_CHILD = textwrap.dedent(
    """
    import os, sys, tempfile, time
    from pathlib import Path
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    data = Path(tempfile.mkdtemp(prefix="dm-ui-"))
    os.environ.update({"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(data),
                       "DRILLMASTER_DB_PATH": str(data / "live.db"),
                       "DRILLMASTER_BACKUP_DIR": str(data / "backups"), "DRILLMASTER_AI_IMPORT": "0"})
    from sqlalchemy import text
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QMessageBox, QWidget

    from core import db_maintenance as dm
    from core.database import Company, DatabaseManager
    from core.managers import AutoSaveManager
    from core.permissions import permissions

    app = QApplication.instance() or QApplication([])
    shown = []
    autosave_when_shown = []  # was the tab's autosave timer running while the message was open?
    for kind in ("information", "warning", "critical"):
        setattr(QMessageBox, kind, staticmethod(
            lambda *a, _k=kind, **k: shown.append((_k, str(a[2])))
            or autosave_when_shown.append("timer" in globals() and timer.isActive()) or QMessageBox.Ok))

    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    permissions.set_user({"id": 1, "username": "synthetic-admin", "role": "admin"})
    manager.enforce_authorization(permissions)
    with manager.session_scope() as s:
        s.add(Company(name="Snapshot Co", code="SNAP"))
    backups = dm.BackupService(manager, data / "backups")
    snapshot = backups.create_backup()
    assert snapshot.ok, snapshot
    with manager.session_scope() as s:
        s.add(Company(name="Later Co", code="LATER"))

    def codes():
        with manager.session_scope() as s:
            return set(s.execute(text("SELECT code FROM companies")).scalars()) & {"SNAP", "LATER"}

    # ---------------------------------------------------------------- dialog
    from dialogs.database_maintenance_dialog import RestoreDatabaseDialog
    candidates = backups.list_backups()
    future = (data / "backups" / "drillmaster_backup_29990101T000000000000Z_deadbeef.db",
              dict(candidates[0][1], schema_version=manager.schema_version + 1, created_utc="2999-01-01T00:00:00+00:00"))
    older = (candidates[0][0], dict(candidates[0][1], schema_version=manager.schema_version - 1))
    dialog = RestoreDatabaseDialog([future] + candidates + [older], manager.schema_version)
    assert dialog.table.rowCount() == len(candidates) + 2
    assert not dialog.restore_button.isEnabled()
    dialog.table.selectRow(0)  # newer schema: not selectable
    assert dialog.selected_candidate() is None and not dialog.restore_button.isEnabled()
    dialog.table.selectRow(1)
    assert dialog.selected_candidate()[0] == candidates[0][0]
    assert not dialog.restore_button.isEnabled(), "confirmation checkbox is required"
    dialog.confirm.setChecked(True)
    assert dialog.restore_button.isEnabled()
    dialog.table.selectRow(dialog.table.rowCount() - 1)
    assert "older database format" in dialog.note.text()
    dialog.deleteLater()

    # ---------------------------------------------------------------- window
    from main_window import MainWindow
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.db_manager = manager
    window.backup_service = backups
    window.auto_save_manager = AutoSaveManager()
    window._maintenance_worker = None
    window._hierarchy_worker = None
    window._hierarchy_shutdown_requested = False
    window._close_confirmed = False
    refreshed, closed = [], []
    window.refresh_all_tabs = lambda: refreshed.append(True)
    window.close = lambda: closed.append(window._close_confirmed) or True

    tab = QWidget(window)  # a widget-level autosave manager must be paused too
    tab.save_data = lambda: True
    tab.autosave_timer = AutoSaveManager()
    timer = tab.autosave_timer.enable_for_widget("SyntheticTab", tab, interval_minutes=5)
    observed = {}

    def run(slot, autosave_resumes=True):
        slot()
        worker = window._maintenance_worker
        assert worker is not None
        observed.update(enabled=window.isEnabled(), timer=timer.isActive())
        ignored = QCloseEvent()
        window.closeEvent(ignored)
        observed["close_refused"] = not ignored.isAccepted()
        deadline = time.monotonic() + 60
        while window._maintenance_worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert window._maintenance_worker is None, "maintenance worker did not finish"
        assert observed == {"enabled": False, "timer": False, "close_refused": True}, observed
        assert window.isEnabled() and timer.isActive() == autosave_resumes
        observed.clear()

    run(window.backup_database_now)
    assert shown[-1][0] == "information" and "Verified backup created" in shown[-1][1], shown
    assert len(backups.list_backups(kinds=(dm.KIND_BACKUP,))) == 2

    import dialogs.database_maintenance_dialog as dialog_module

    class Chosen:
        def __init__(self, *_a, **_k):
            pass
        def exec(self):
            return QDialog.Accepted
        def selected_candidate(self):
            return Path(snapshot.path), {}

    dialog_module.RestoreDatabaseDialog = Chosen

    real_check = dm.RestoreService._require_exclusive_file
    def busy(self):
        raise dm.MaintenanceBusy("the database is open in another process; close it and retry")
    dm.RestoreService._require_exclusive_file = busy
    run(window.restore_database)
    assert shown[-1][0] == "warning" and "was not changed" in shown[-1][1], shown
    assert codes() == {"SNAP", "LATER"} and refreshed and not closed

    dm.RestoreService._require_exclusive_file = real_check
    run(window.restore_database, autosave_resumes=False)
    assert shown[-1][0] == "information" and "restored and verified" in shown[-1][1], shown
    # No screen may autosave stale contents into the restored database, not even
    # while the success message is open (M43: autosave used to resume first).
    assert autosave_when_shown[-1] is False and not timer.isActive()
    assert all(not m._enabled for m in window._autosave_managers())
    assert codes() == {"SNAP"} and closed == [True]

    permissions.set_user({"id": 2, "username": "synthetic-viewer", "role": "viewer"})
    run(window.backup_database_now, autosave_resumes=False)  # still paused for the restart
    assert shown[-1][0] == "warning" and "permission" in shown[-1][1], shown
    manager.close()
    print("DB-MAINTENANCE-UI-OK")
    """
)


def test_backup_and_restore_ui_flow_in_subprocess():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=root)
    completed = subprocess.run([sys.executable, "-c", _CHILD], cwd=root, env=env,
                               capture_output=True, text=True, timeout=240)
    assert completed.returncode == 0 and "DB-MAINTENANCE-UI-OK" in completed.stdout, (
        completed.stdout[-3000:] + completed.stderr[-3000:])
