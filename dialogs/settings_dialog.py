# dialogs/settings_dialog.py
"""
Settings Dialog - تنظیمات نرم‌افزار
"""
import logging
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

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

        self.backup_enabled = QCheckBox("Enable automatic backup")
        self.backup_enabled.setChecked(False)
        layout.addRow("Backup:", self.backup_enabled)

        self.backup_path = QLineEdit()
        self.backup_path.setPlaceholderText("Select backup folder...")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_backup_path)
        backup_layout = QHBoxLayout()
        backup_layout.addWidget(self.backup_path)
        backup_layout.addWidget(browse_btn)
        layout.addRow("Backup Path:", backup_layout)

        return tab

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

        backup_btn = QPushButton("📦 Backup Database Now")
        backup_btn.clicked.connect(self._backup_database)
        actions_layout.addWidget(backup_btn)

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
        try:
            manager = getattr(self.parent(), "db_manager", None)
            if not manager or manager.db_path == ":memory:":
                QMessageBox.warning(self, "Backup", "A file-backed database is required.")
                return
            timestamp = QDateTime.currentDateTime().toString("yyyyMMdd_HHmmss")
            dst = QFileDialog.getSaveFileName(
                self,
                "Save Database Backup",
                f"drillmaster_backup_{timestamp}.db",
                "Database Files (*.db)",
            )[0]
            if dst and manager.backup_to(dst):
                QMessageBox.information(self, "Backup", f"Database backed up to:\n{dst}")
            elif dst:
                QMessageBox.warning(self, "Backup", "The database backup could not be created.")
        except Exception:
            logger.exception("Settings database backup failed")
            QMessageBox.critical(self, "Backup Error", "The database backup could not be created.")

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
                    QMessageBox.information(self, "Reset", "Please close the app and run reset_db.py")

    def save_settings(self):
        """Save settings - نسخه اصلاح شده"""
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
        
        # ✅ backup settings که قبلاً ذخیره نمی‌شد
        self.settings.setValue("backup/enabled", self.backup_enabled.isChecked())
        self.settings.setValue("backup/path", self.backup_path.text())

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
        
        # ✅ load backup settings
        self.backup_enabled.setChecked(
            self.settings.value("backup/enabled", False, type=bool)
        )
        self.backup_path.setText(
            self.settings.value("backup/path", "")
        )

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
            self.depth_unit.setCurrentText("meters (m)")
            self.weight_unit.setCurrentText("pcf")
            self.pressure_unit.setCurrentText("psi")
            self.temperature_unit.setCurrentText("°C")