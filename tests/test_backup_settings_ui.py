"""Settings dialog: automatic-backup controls show and save the resolved settings (M43).

Qt runs offscreen; settings go to a temporary INI file, never the user's store.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QWidget  # noqa: E402

from core import db_maintenance as dm  # noqa: E402


@pytest.fixture()
def dialog_env(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    data = tmp_path / "data"
    monkeypatch.setenv("DRILLMASTER_ENV", "test")
    monkeypatch.setenv("DRILLMASTER_DATA_DIR", str(data))
    monkeypatch.setenv("DRILLMASTER_AI_IMPORT", "0")
    for key in (dm.DIR_ENV, dm.KEEP_ENV, dm.INTERVAL_ENV):
        monkeypatch.delenv(key, raising=False)
    from dialogs import settings_dialog as module

    ini = tmp_path / "settings.ini"
    monkeypatch.setattr(module, "QSettings", lambda *_args: QSettings(str(ini), QSettings.Format.IniFormat))
    messages = []
    for kind in ("warning", "information", "critical"):
        monkeypatch.setattr(module.QMessageBox, kind,
                            lambda *args, _kind=kind: messages.append((_kind, args[2] if len(args) > 2 else "")))
    yield app, module, ini, data, messages


def _store(ini):
    return QSettings(str(ini), QSettings.Format.IniFormat)


def test_the_dialog_shows_the_settings_the_application_really_uses(dialog_env):
    _app, module, _ini, data, _messages = dialog_env
    dialog = module.SettingsDialog()
    assert dialog.backup_enabled.isChecked()  # automatic backups are on by default
    assert dialog.backup_path.text() == str((data / "backups").resolve())
    assert (dialog.backup_interval.value(), dialog.backup_keep.value()) == (
        dm.DEFAULT_INTERVAL_MINUTES, dm.DEFAULT_KEEP)
    assert all(w.isEnabled() for w in (dialog.backup_enabled, dialog.backup_path,
                                       dialog.backup_interval, dialog.backup_keep))
    assert not dialog.backup_now_btn.isEnabled()  # no verified backup service without a main window
    dialog.deleteLater()


def test_legacy_saved_values_do_not_change_what_is_shown(dialog_env):
    _app, module, ini, data, _messages = dialog_env
    store = _store(ini)
    store.setValue("backup/enabled", False)
    store.setValue("backup/path", "/legacy/never/applied")
    store.sync()
    dialog = module.SettingsDialog()
    assert dialog.backup_enabled.isChecked()
    assert dialog.backup_path.text() == str((data / "backups").resolve())
    dialog.deleteLater()


def test_environment_overrides_are_shown_locked_and_are_not_saved(dialog_env, tmp_path, monkeypatch):
    _app, module, ini, _data, _messages = dialog_env
    monkeypatch.setenv(dm.DIR_ENV, str(tmp_path / "admin-backups"))
    monkeypatch.setenv(dm.KEEP_ENV, "6")
    dialog = module.SettingsDialog()
    assert not dialog.backup_path.isEnabled() and dm.DIR_ENV in dialog.backup_path.toolTip()
    assert not dialog.backup_keep.isEnabled() and dialog.backup_keep.value() == 6
    assert dialog.backup_interval.isEnabled()
    dialog.backup_interval.setValue(90)
    dialog.save_settings()
    store = _store(ini)
    assert store.value(dm.SETTINGS_KEYS["interval_minutes"], type=int) == 90
    assert not store.contains(dm.SETTINGS_KEYS["directory"]) and not store.contains(dm.SETTINGS_KEYS["keep"])


def test_an_invalid_folder_blocks_saving_anything(dialog_env):
    _app, module, ini, _data, messages = dialog_env
    dialog = module.SettingsDialog()
    dialog.company_name.setText("Synthetic Drilling Co")
    dialog.backup_path.setText("relative/backups")
    dialog.save_settings()
    assert messages and messages[-1][0] == "warning" and "absolute" in messages[-1][1]
    assert dialog.result() != QDialog.DialogCode.Accepted
    store = _store(ini)
    assert not store.contains(dm.SETTINGS_KEYS["directory"]) and not store.contains("general/company_name")
    dialog.deleteLater()


def test_saved_values_are_what_the_next_start_resolves(dialog_env, tmp_path):
    _app, module, ini, _data, messages = dialog_env
    folder = tmp_path / "second-disk" / "backups"
    dialog = module.SettingsDialog()
    dialog.backup_enabled.setChecked(False)
    dialog.backup_path.setText(str(folder))
    dialog.backup_interval.setValue(120)
    dialog.backup_keep.setValue(3)
    dialog.save_settings()
    assert messages[-1][0] == "information"
    resolved = dm.resolve_backup_settings(dm.persisted_backup_settings(_store(ini)))
    assert (resolved.enabled, resolved.directory, resolved.interval_minutes, resolved.keep) == (
        False, folder.resolve(), 120, 3)
    assert resolved.schedule_seconds == 0 and resolved.warnings == ()
    assert not folder.exists()  # saving a folder creates nothing; the next backup does


def test_backup_now_uses_the_main_windows_verified_backup(dialog_env, monkeypatch):
    _app, module, _ini, _data, _messages = dialog_env
    from core.permissions import permissions

    class Window(QWidget):
        def __init__(self):
            super().__init__()
            self.db_manager = None
            self.backup_service = object()
            self.calls = 0

        def backup_database_now(self):
            self.calls += 1

    monkeypatch.setattr(permissions, "can_maintain_database", lambda: True)
    window = Window()
    dialog = module.SettingsDialog(window)
    assert dialog.backup_now_btn.isEnabled()
    dialog.backup_now_btn.click()
    assert window.calls == 1
    monkeypatch.setattr(permissions, "can_maintain_database", lambda: False)
    denied = module.SettingsDialog(window)
    assert not denied.backup_now_btn.isEnabled()
    for widget in (dialog, denied, window):
        widget.deleteLater()


# ---------------------------------------------------------------- start-up wiring in MainWindow

@pytest.fixture()
def window_env(dialog_env, monkeypatch):
    _app, _module, ini, data, _messages = dialog_env
    monkeypatch.setenv("DRILLMASTER_DB_PATH", str(data / "live.db"))
    from core.database import DatabaseManager
    from main_window import MainWindow
    from PySide6.QtWidgets import QMainWindow

    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    windows = []

    def build():
        window = MainWindow.__new__(MainWindow)
        QMainWindow.__init__(window)
        window.db_manager = manager
        window.settings = _store(ini)
        window._create_backup_services()
        windows.append(window)
        return window

    yield build, ini, data
    for window in windows:
        if window.backup_scheduler is not None:
            assert window.backup_scheduler.stop(timeout=5)
        window.deleteLater()
    manager.close()


def test_main_window_applies_saved_settings_at_start_up(window_env, tmp_path):
    build, ini, _data = window_env
    folder = tmp_path / "chosen-backups"
    store = _store(ini)
    for name, value in {"directory": str(folder), "keep": 4, "interval_minutes": 15}.items():
        store.setValue(dm.SETTINGS_KEYS[name], value)
    store.sync()
    window = build()
    assert window.backup_service.backup_dir == folder.resolve()
    assert window.backup_service.keep == 4
    assert window.backup_scheduler.interval == 15 * 60
    assert window.backup_scheduler._thread is not None  # started


def test_main_window_does_not_schedule_when_backups_are_disabled(window_env):
    build, ini, data = window_env
    store = _store(ini)
    store.setValue(dm.SETTINGS_KEYS["enabled"], False)
    store.sync()
    window = build()
    assert window.backup_scheduler.interval == 0 and window.backup_scheduler._thread is None
    # manual backups still use the resolved folder
    assert window.backup_service.backup_dir == (data / "backups").resolve()


def test_main_window_environment_still_wins_over_saved_settings(window_env, tmp_path, monkeypatch):
    build, ini, _data = window_env
    monkeypatch.setenv(dm.DIR_ENV, str(tmp_path / "admin"))
    store = _store(ini)
    store.setValue(dm.SETTINGS_KEYS["directory"], str(tmp_path / "user"))
    store.sync()
    window = build()
    assert window.backup_service.backup_dir == (tmp_path / "admin").resolve()
    assert window.backup_settings.locked == {"directory": dm.DIR_ENV}
