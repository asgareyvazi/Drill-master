# dialogs/settings_dialog.py
"""
Settings Dialog - تنظیمات نرم‌افزار
"""
import logging
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from core.mineru_engine import MinerUConfig, discover_mineru_executable
from core.runtime_config import write_mineru_settings
from core.db_maintenance import INTERVAL_RANGE as BACKUP_INTERVAL_RANGE
from core.db_maintenance import KEEP_RANGE as BACKUP_KEEP_RANGE
from core.db_maintenance import SETTINGS_KEYS as BACKUP_SETTINGS_KEYS
from core.db_maintenance import persisted_backup_settings, resolve_backup_settings, validate_backup_directory

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Settings dialog for application configuration"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Settings")
        self.setFixedSize(600, 500)
        self.setModal(True)
        self.settings = QSettings("Nikan", "DrillMaster")
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("⚙️ Application Settings")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; padding: 10px;")
        layout.addWidget(title)

        # Tabs
        self.tabs = QTabWidget()

        # General Tab
        self.tabs.addTab(self._create_general_tab(), "🏠 General")
        # Appearance Tab
        self.tabs.addTab(self._create_appearance_tab(), "🎨 Appearance")
        # Auto-Save Tab
        self.tabs.addTab(self._create_autosave_tab(), "💾 Auto-Save")
        # Units Tab
        self.tabs.addTab(self._create_units_tab(), "📏 Units")
        # Database Tab
        self.tabs.addTab(self._create_database_tab(), "🗃️ Database")
        # External document intelligence
        self.tabs.addTab(self._create_mineru_tab(), "📄 MinerU")

        layout.addWidget(self.tabs)

        # Buttons
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("💾 Save Settings")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60; color: white;
                font-weight: bold; padding: 8px 16px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #229954; }
        """)
        self.save_btn.clicked.connect(self.save_settings)

        self.reset_btn = QPushButton("🔄 Reset Defaults")
        self.reset_btn.clicked.connect(self.reset_defaults)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.reset_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def _create_general_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setSpacing(15)

        self.language_combo = QComboBox()
        self.language_combo.addItems(["English", "فارسی"])
        layout.addRow("Language:", self.language_combo)

        self.company_name = QLineEdit()
        self.company_name.setPlaceholderText("Your company name")
        layout.addRow("Company Name:", self.company_name)

        self.user_name = QLineEdit()
        self.user_name.setPlaceholderText("Your full name")
        layout.addRow("User Name:", self.user_name)

        self.show_startup = QCheckBox("Show startup dialog on launch")
        self.show_startup.setChecked(True)
        layout.addRow("Startup:", self.show_startup)

        self.confirm_exit = QCheckBox("Confirm before exit")
        self.confirm_exit.setChecked(True)
        layout.addRow("Exit:", self.confirm_exit)

        return tab

    def _create_appearance_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setSpacing(15)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark", "System"])
        layout.addRow("Theme:", self.theme_combo)

        self.font_size = QSpinBox()
        self.font_size.setRange(8, 20)
        self.font_size.setValue(10)
        self.font_size.setSuffix(" pt")
        layout.addRow("Font Size:", self.font_size)

        self.font_family = QComboBox()
        self.font_family.addItems(["Segoe UI", "Arial", "Tahoma", "Calibri", "Consolas"])
        layout.addRow("Font Family:", self.font_family)

        self.show_toolbar = QCheckBox("Show main toolbar")
        self.show_toolbar.setChecked(True)
        layout.addRow("Toolbar:", self.show_toolbar)

        self.show_statusbar = QCheckBox("Show status bar")
        self.show_statusbar.setChecked(True)
        layout.addRow("Status Bar:", self.show_statusbar)

        return tab

    def _create_autosave_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setSpacing(15)

        self.autosave_enabled = QCheckBox("Enable auto-save")
        self.autosave_enabled.setChecked(True)
        layout.addRow("Auto-Save:", self.autosave_enabled)

        self.autosave_interval = QSpinBox()
        self.autosave_interval.setRange(1, 60)
        self.autosave_interval.setValue(5)
        self.autosave_interval.setSuffix(" minutes")
        layout.addRow("Interval:", self.autosave_interval)

        # Automatic verified database backups (core.db_maintenance).  The values
        # shown are the resolved ones the application actually uses.
        self.backup_enabled = QCheckBox("Automatic verified database backups")
        layout.addRow("Database backup:", self.backup_enabled)

        self.backup_path = QLineEdit()
        self.backup_path.setPlaceholderText("Local backup folder")
        self.backup_browse_btn = QPushButton("Browse...")
        self.backup_browse_btn.clicked.connect(self._browse_backup_path)
        backup_layout = QHBoxLayout()
        backup_layout.addWidget(self.backup_path)
        backup_layout.addWidget(self.backup_browse_btn)
        layout.addRow("Backup folder:", backup_layout)

        self.backup_interval = QSpinBox()
        self.backup_interval.setRange(*BACKUP_INTERVAL_RANGE)
        self.backup_interval.setSuffix(" minutes")
        layout.addRow("Backup every:", self.backup_interval)

        self.backup_keep = QSpinBox()
        self.backup_keep.setRange(*BACKUP_KEEP_RANGE)
        layout.addRow("Backups to keep:", self.backup_keep)

        note = QLabel(
            "Backup settings apply the next time DrillMaster starts. Changing them never moves or "
            "deletes existing backups. After each successful backup, automatic backups in the selected "
            "folder beyond the number to keep are removed; pre-restore safety copies are never removed. "
            "Network and cloud folders are not supported.")
        note.setWordWrap(True)
        layout.addRow("", note)
        self.backup_warning = QLabel("")
        self.backup_warning.setWordWrap(True)
        self.backup_warning.setVisible(False)
        layout.addRow("", self.backup_warning)

        return tab

    # -- automatic backup settings -------------------------------------------

    def _live_db_path(self):
        return getattr(getattr(self.parent(), "db_manager", None), "db_path", None)

    def _backup_widgets(self):
        return {"enabled": (self.backup_enabled,), "directory": (self.backup_path, self.backup_browse_btn),
                "interval_minutes": (self.backup_interval,), "keep": (self.backup_keep,)}

    def _show_backup_settings(self, resolved):
        self._backup_resolved = resolved
        self.backup_enabled.setChecked(resolved.enabled)
        self.backup_path.setText(str(resolved.directory))
        self.backup_interval.setValue(resolved.interval_minutes)
        self.backup_keep.setValue(resolved.keep)
        for name, widgets in self._backup_widgets().items():
            variable = resolved.locked.get(name)
            for widget in widgets:
                widget.setEnabled(variable is None)
                widget.setToolTip(f"Set by the administrator ({variable})." if variable else "")
        self.backup_warning.setText("\n".join(resolved.warnings))
        self.backup_warning.setVisible(bool(resolved.warnings))

    def _backup_values_to_save(self) -> dict:
        """Validated values for the unlocked fields; raises ValueError with a user-facing reason."""
        locked = getattr(self, "_backup_resolved", None)
        locked = locked.locked if locked is not None else {}
        values = {}
        if "directory" not in locked:
            values[BACKUP_SETTINGS_KEYS["directory"]] = str(
                validate_backup_directory(self.backup_path.text(), self._live_db_path()))
        if "enabled" not in locked:
            values[BACKUP_SETTINGS_KEYS["enabled"]] = self.backup_enabled.isChecked()
        if "interval_minutes" not in locked:
            values[BACKUP_SETTINGS_KEYS["interval_minutes"]] = self.backup_interval.value()
        if "keep" not in locked:
            values[BACKUP_SETTINGS_KEYS["keep"]] = self.backup_keep.value()
        return values

    def _create_mineru_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setSpacing(10)

        self.mineru_enabled = QCheckBox("Use MinerU when detected")
        layout.addRow("Enabled:", self.mineru_enabled)

        self.mineru_executable = QLineEdit()
        self.mineru_executable.setPlaceholderText("Auto-discover mineru.exe or configure a path")
        executable_browse = QPushButton("Browse...")
        executable_browse.clicked.connect(self._browse_mineru_executable)
        executable_layout = QHBoxLayout()
        executable_layout.addWidget(self.mineru_executable)
        executable_layout.addWidget(executable_browse)
        layout.addRow("Executable:", executable_layout)

        self.mineru_python = QLineEdit()
        self.mineru_python.setPlaceholderText("Optional Python executable for python -m mineru")
        python_browse = QPushButton("Browse...")
        python_browse.clicked.connect(self._browse_mineru_python)
        python_layout = QHBoxLayout()
        python_layout.addWidget(self.mineru_python)
        python_layout.addWidget(python_browse)
        layout.addRow("Python:", python_layout)

        self.mineru_backend = QComboBox()
        self.mineru_backend.addItems([
            "hybrid-engine",
            "pipeline",
            "vlm-engine",
            "hybrid-http-client",
            "vlm-http-client",
        ])
        layout.addRow("Backend:", self.mineru_backend)

        self.mineru_method = QComboBox()
        self.mineru_method.addItems(["auto", "txt", "ocr"])
        layout.addRow("Method:", self.mineru_method)

        self.mineru_timeout = QSpinBox()
        self.mineru_timeout.setRange(1, 86400)
        self.mineru_timeout.setSuffix(" seconds")
        layout.addRow("Timeout:", self.mineru_timeout)

        self.mineru_output_dir = QLineEdit()
        self.mineru_output_dir.setPlaceholderText("Temporary isolated output by default")
        output_browse = QPushButton("Browse...")
        output_browse.clicked.connect(self._browse_mineru_output_dir)
        output_layout = QHBoxLayout()
        output_layout.addWidget(self.mineru_output_dir)
        output_layout.addWidget(output_browse)
        layout.addRow("Output Directory:", output_layout)

        self.mineru_keep_output = QCheckBox("Keep generated MinerU output")
        layout.addRow("Debug Output:", self.mineru_keep_output)

        note = QLabel(
            "MinerU remains an external installation. DrillMaster never copies "
            "or installs MinerU in its own environment."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #7f8c8d; padding: 8px;")
        layout.addRow("Note:", note)
        return tab

    def _browse_mineru_executable(self):
        path = QFileDialog.getOpenFileName(
            self,
            "Select MinerU executable",
            "",
            "Executables (*.exe);;All files (*)",
        )[0]
        if path:
            self.mineru_executable.setText(path)

    def _browse_mineru_python(self):
        path = QFileDialog.getOpenFileName(
            self,
            "Select MinerU Python executable",
            "",
            "Python executable (python*);;All files (*)",
        )[0]
        if path:
            self.mineru_python.setText(path)

    def _browse_mineru_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select MinerU output directory")
        if path:
            self.mineru_output_dir.setText(path)

    def _create_units_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setSpacing(15)

        self.depth_unit = QComboBox()
        self.depth_unit.addItems(["meters (m)", "feet (ft)"])
        layout.addRow("Depth Unit:", self.depth_unit)

        self.weight_unit = QComboBox()
        self.weight_unit.addItems(["pcf", "ppg", "kg/m³", "sg"])
        layout.addRow("Mud Weight Unit:", self.weight_unit)

        self.pressure_unit = QComboBox()
        self.pressure_unit.addItems(["psi", "bar", "kPa", "MPa"])
        layout.addRow("Pressure Unit:", self.pressure_unit)

        self.temperature_unit = QComboBox()
        self.temperature_unit.addItems(["°C", "°F"])
        layout.addRow("Temperature Unit:", self.temperature_unit)

        self.volume_unit = QComboBox()
        self.volume_unit.addItems(["bbl", "m³", "liters", "gallons"])
        layout.addRow("Volume Unit:", self.volume_unit)

        return tab

    def _create_database_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setSpacing(15)

        self.db_path = QLineEdit()
        manager = getattr(self.parent(), "db_manager", None)
        self.db_path.setText(getattr(manager, "db_path", "Unavailable"))
        self.db_path.setReadOnly(True)
        layout.addRow("Database File:", self.db_path)

        # DB info
        info_label = QLabel("Database information will be shown here")
        info_label.setStyleSheet("color: #7f8c8d; padding: 10px;")
        layout.addRow("Info:", info_label)

        # Actions
        actions_layout = QVBoxLayout()

        # The same verified, permission-checked and audited backup as
        # Tools > Backup Database Now (written to the configured backup folder).
        self.backup_now_btn = QPushButton("📦 Backup Database Now")
        self.backup_now_btn.clicked.connect(self._backup_database)
        try:
            from core.permissions import permissions as _permissions
            allowed = (getattr(self.parent(), "backup_service", None) is not None
                       and _permissions.can_maintain_database())
        except Exception:
            logger.exception("Could not resolve the database maintenance permission")
            allowed = False
        self.backup_now_btn.setEnabled(allowed)
        if not allowed:
            self.backup_now_btn.setToolTip("Requires the database maintenance permission")
        actions_layout.addWidget(self.backup_now_btn)

        reset_btn = QPushButton("🗑️ Reset Database (Caution!)")
        reset_btn.setStyleSheet("color: #e74c3c;")
        reset_btn.clicked.connect(self._reset_database)
        actions_layout.addWidget(reset_btn)

        layout.addRow("Actions:", actions_layout)
        return tab

    def _browse_backup_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Backup Folder")
        if folder:
            self.backup_path.setText(folder)

    def _backup_database(self):
        """Delegate to the main window's verified backup; never copy the file directly.

        ``BackupService.create_backup`` enforces ``can_maintain_database`` at the
        service boundary, writes a manifest and records the outcome in the audit
        log.  (Before M43 this button copied the database to any chosen path
        without a permission check or audit entry.)
        """
        window = self.parent()
        start = getattr(window, "backup_database_now", None)
        if start is None or getattr(window, "backup_service", None) is None:
            QMessageBox.warning(self, "Backup", "Verified backups need a file-backed database.")
            return
        start()

    def _reset_database(self):
        reply = QMessageBox.warning(
            self, "⚠️ Reset Database",
            "This will DELETE ALL DATA!\n\nAre you absolutely sure?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            reply2 = QMessageBox.warning(
                self, "⚠️ Final Warning",
                "This action CANNOT be undone!\nType 'RESET' in the next dialog to confirm.",
                QMessageBox.Ok | QMessageBox.Cancel
            )
            if reply2 == QMessageBox.Ok:
                text, ok = QInputDialog.getText(self, "Confirm Reset", "Type RESET to confirm:")
                if ok and text == "RESET":
                    QMessageBox.information(self, "Offline reset required",
                        "No data has been changed. Close all DrillMaster instances and back up the database.\n"
                        "From the source checkout run: python reset_database.py\n"
                        "Production reset requires a secure DRILLMASTER_ADMIN_PASSWORD in that shell; "
                        "engineer/viewer passwords are optional. Missing or invalid settings refuse reset before deletion.\n"
                        "Reset erases database users and operational data, but keeps external settings/backups. "
                        "Use the same environment and database-path settings when restarting. "
                        "Packaged installations require the administrator's source reset utility.")

    def save_settings(self):
        """Save settings - نسخه اصلاح شده"""
        try:
            backup_values = self._backup_values_to_save()
        except ValueError as exc:  # nothing is saved until every value is valid
            self.tabs.setCurrentWidget(self.backup_path.parentWidget())
            QMessageBox.warning(self, "Backup folder", str(exc))
            return
        self.settings.setValue("general/language", self.language_combo.currentText())
        self.settings.setValue("general/company_name", self.company_name.text())
        self.settings.setValue("general/user_name", self.user_name.text())
        self.settings.setValue("general/show_startup", self.show_startup.isChecked())
        self.settings.setValue("general/confirm_exit", self.confirm_exit.isChecked())

        self.settings.setValue("ui/theme", self.theme_combo.currentText())
        self.settings.setValue("ui/font_size", self.font_size.value())
        self.settings.setValue("ui/font_family", self.font_family.currentText())
        self.settings.setValue("ui/show_toolbar", self.show_toolbar.isChecked())
        self.settings.setValue("ui/show_statusbar", self.show_statusbar.isChecked())

        self.settings.setValue("autosave/enabled", self.autosave_enabled.isChecked())
        self.settings.setValue("autosave/interval", self.autosave_interval.value())
        
        for key, value in backup_values.items():
            self.settings.setValue(key, value)

        mineru_settings = {
            "enabled": self.mineru_enabled.isChecked(),
            "executable": self.mineru_executable.text().strip(),
            "python": self.mineru_python.text().strip(),
            "backend": self.mineru_backend.currentText(),
            "method": self.mineru_method.currentText(),
            "timeout": self.mineru_timeout.value(),
            "output_dir": self.mineru_output_dir.text().strip(),
            "keep_output": self.mineru_keep_output.isChecked(),
        }
        write_mineru_settings(mineru_settings)

        self.settings.setValue("units/depth", self.depth_unit.currentText())
        self.settings.setValue("units/weight", self.weight_unit.currentText())
        self.settings.setValue("units/pressure", self.pressure_unit.currentText())
        self.settings.setValue("units/temperature", self.temperature_unit.currentText())
        self.settings.setValue("units/volume", self.volume_unit.currentText())

        self.settings.sync()
        QMessageBox.information(
            self, "Settings", "Settings saved successfully!"
        )
        self.accept()

    def load_settings(self):
        """Load settings - نسخه اصلاح شده"""
        self.language_combo.setCurrentText(
            self.settings.value("general/language", "English")
        )
        self.company_name.setText(
            self.settings.value("general/company_name", "")
        )
        self.user_name.setText(
            self.settings.value("general/user_name", "")
        )
        self.show_startup.setChecked(
            self.settings.value("general/show_startup", True, type=bool)
        )
        self.confirm_exit.setChecked(
            self.settings.value("general/confirm_exit", True, type=bool)
        )

        self.theme_combo.setCurrentText(
            self.settings.value("ui/theme", "Light")
        )
        self.font_size.setValue(
            self.settings.value("ui/font_size", 10, type=int)
        )
        self.font_family.setCurrentText(
            self.settings.value("ui/font_family", "Segoe UI")
        )

        self.autosave_enabled.setChecked(
            self.settings.value("autosave/enabled", True, type=bool)
        )
        self.autosave_interval.setValue(
            self.settings.value("autosave/interval", 5, type=int)
        )
        
        self._show_backup_settings(resolve_backup_settings(
            persisted_backup_settings(self.settings), live_db_path=self._live_db_path()))

        mineru = MinerUConfig.from_environment()
        self.mineru_enabled.setChecked(mineru.enabled)
        self.mineru_executable.setText(mineru.executable or discover_mineru_executable() or "")
        self.mineru_python.setText(mineru.python_executable or "")
        self.mineru_backend.setCurrentText(mineru.backend)
        self.mineru_method.setCurrentText(mineru.method)
        self.mineru_timeout.setValue(mineru.timeout_seconds)
        self.mineru_output_dir.setText(str(mineru.output_dir) if mineru.output_dir else "")
        self.mineru_keep_output.setChecked(mineru.keep_output)

        self.depth_unit.setCurrentText(
            self.settings.value("units/depth", "meters (m)")
        )
        self.weight_unit.setCurrentText(
            self.settings.value("units/weight", "pcf")
        )
        self.pressure_unit.setCurrentText(
            self.settings.value("units/pressure", "psi")
        )
        self.temperature_unit.setCurrentText(
            self.settings.value("units/temperature", "°C")
        )
        self.volume_unit.setCurrentText(
            self.settings.value("units/volume", "bbl")
        )

    def reset_defaults(self):
        """Reset to default values"""
        reply = QMessageBox.question(
            self, "Reset Settings",
            "Reset all settings to defaults?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.language_combo.setCurrentText("English")
            self.company_name.clear()
            self.theme_combo.setCurrentText("Light")
            self.font_size.setValue(10)
            self.autosave_enabled.setChecked(True)
            self.autosave_interval.setValue(5)
            defaults = resolve_backup_settings({}, live_db_path=self._live_db_path())
            locked = self._backup_resolved.locked if getattr(self, "_backup_resolved", None) else {}
            if "enabled" not in locked:
                self.backup_enabled.setChecked(defaults.enabled)
            if "directory" not in locked:
                self.backup_path.setText(str(defaults.directory))
            if "interval_minutes" not in locked:
                self.backup_interval.setValue(defaults.interval_minutes)
            if "keep" not in locked:
                self.backup_keep.setValue(defaults.keep)
            self.mineru_enabled.setChecked(bool(discover_mineru_executable()))
            self.mineru_executable.setText(discover_mineru_executable() or "")
            self.mineru_python.clear()
            self.mineru_backend.setCurrentText("hybrid-engine")
            self.mineru_method.setCurrentText("auto")
            self.mineru_timeout.setValue(600)
            self.mineru_output_dir.clear()
            self.mineru_keep_output.setChecked(False)
            self.depth_unit.setCurrentText("meters (m)")
            self.weight_unit.setCurrentText("pcf")
            self.pressure_unit.setCurrentText("psi")
            self.temperature_unit.setCurrentText("°C")