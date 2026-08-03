"""
Downhole Widget - ابزار مدیریت تجهیزات زیر سطحی (بازنویسی کامل)
"""

import logging
import json
from datetime import datetime, date, timedelta
# Try to import pandas (optional)
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    
import csv

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from core.database import DatabaseManager
from core.managers import StatusBarManager, TableManager, ExportManager, DrillingManager
from core.base_tab import DrillTabBase
from core.selection_manager import SelectionManager

logger = logging.getLogger(__name__)


class DownholeWidget(DrillTabBase):
    """ویجت اصلی مدیریت تجهیزات زیر سطحی"""

    def __init__(self, db_manager=None, parent=None):
        super().__init__("DownholeWidget", db_manager, parent)
        self.current_well = None
        self.current_report_id = None
        self.current_section = None

        # مدیرهای داخلی
        self.bha_manager = None
        self.equipment_manager = None
        self.formation_manager = None

        self.bha_data = {}
        self.saved_formations = {}

        self.init_ui()
        self.setup_managers()
        self.setup_connections()
        logger.info("DownholeWidget initialized")

    # --------------------------------------------------------------
    # رابط کاربری
    # --------------------------------------------------------------
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.tab_widget = QTabWidget()

        # تب 1: BHA
        bha_tab = self.create_bha_tab()
        self.tab_widget.addTab(bha_tab, "🔧 BHA")

        # تب 2: Downhole Equipment
        equipment_tab = self.create_equipment_tab()
        self.tab_widget.addTab(equipment_tab, "⚙️ Downhole Equipment")

        # تب 3: Formation Evaluation
        formation_tab = self.create_formation_tab()
        self.tab_widget.addTab(formation_tab, "🏔️ Formation Evaluation")

        main_layout.addWidget(self.tab_widget)

        # نوار وضعیت
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        self.well_label = QLabel("Well: Not Selected")
        self.well_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        status_layout.addWidget(self.well_label)
        status_layout.addStretch()
        self.save_status_label = QLabel("💾 Auto-save: ON")
        status_layout.addWidget(self.save_status_label)
        save_all_btn = QPushButton("💾 Save All Downhole Data")
        save_all_btn.clicked.connect(self.save_all_data_to_db)
        status_layout.addWidget(save_all_btn)
        main_layout.addWidget(status_widget)

    # ---------- ساخت تب‌ها ----------
    def create_bha_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        header = QHBoxLayout()
        header.addWidget(QLabel("<h3>BHA Configuration</h3>"))
        header.addStretch()

        # انتخاب BHA
        bha_select_layout = QHBoxLayout()
        bha_select_layout.addWidget(QLabel("BHA Name:"))
        self.bha_name_input = QLineEdit()
        self.bha_name_input.setPlaceholderText("Enter BHA name...")
        bha_select_layout.addWidget(self.bha_name_input)
        bha_select_layout.addWidget(QLabel("Saved BHAs:"))
        self.bha_selector = QComboBox()
        self.bha_selector.addItem("-- Select BHA --")
        bha_select_layout.addWidget(self.bha_selector)
        bha_select_layout.addStretch()
        layout.addLayout(bha_select_layout)

        btn_layout = QHBoxLayout()
        self.add_bha_tool_btn = QPushButton("➕ Add Tool")
        self.remove_bha_tool_btn = QPushButton("➖ Remove Tool")
        self.save_bha_btn = QPushButton("💾 Save BHA")
        self.load_bha_btn = QPushButton("📂 Load BHA")
        self.delete_bha_btn = QPushButton("🗑️ Delete BHA")
        self.calculate_bha_btn = QPushButton("🧮 Calculate Totals")
        self.export_bha_btn = QPushButton("📤 Export BHA")
        btn_layout.addWidget(self.add_bha_tool_btn)
        btn_layout.addWidget(self.remove_bha_tool_btn)
        btn_layout.addWidget(self.save_bha_btn)
        btn_layout.addWidget(self.load_bha_btn)
        btn_layout.addWidget(self.delete_bha_btn)
        btn_layout.addWidget(self.calculate_bha_btn)
        btn_layout.addWidget(self.export_bha_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.bha_table = QTableWidget()
        self.bha_table.setAlternatingRowColors(True)
        self.bha_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.bha_table)

        return tab

    def create_equipment_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        header = QHBoxLayout()
        header.addWidget(QLabel("<h3>Downhole Equipment Management</h3>"))
        header.addStretch()
        layout.addLayout(header)

        btn_layout = QHBoxLayout()
        self.add_equipment_btn = QPushButton("➕ Add Equipment")
        self.remove_equipment_btn = QPushButton("➖ Remove Equipment")
        self.calculate_hours_btn = QPushButton("🔄 Calculate Hours")
        self.check_service_btn = QPushButton("🔍 Check Service Due")
        self.save_equipment_btn = QPushButton("💾 Save Equipment")
        self.export_equipment_btn = QPushButton("📤 Export Data")
        self.import_equipment_btn = QPushButton("📂 Import Data")
        btn_layout.addWidget(self.add_equipment_btn)
        btn_layout.addWidget(self.remove_equipment_btn)
        btn_layout.addWidget(self.calculate_hours_btn)
        btn_layout.addWidget(self.check_service_btn)
        btn_layout.addWidget(self.save_equipment_btn)
        btn_layout.addWidget(self.export_equipment_btn)
        btn_layout.addWidget(self.import_equipment_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.equipment_table = QTableWidget()
        self.equipment_table.setAlternatingRowColors(True)
        self.equipment_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.equipment_table)

        return tab

    def create_formation_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        header = QHBoxLayout()
        header.addWidget(QLabel("<h3>Formation Evaluation</h3>"))
        header.addStretch()
        layout.addLayout(header)

        # فرم ورود
        form_group = QGroupBox("Add New Formation")
        form_layout = QGridLayout(form_group)
        form_layout.addWidget(QLabel("Formation Name:"), 0, 0)
        self.formation_name_input = QLineEdit()
        form_layout.addWidget(self.formation_name_input, 0, 1)
        form_layout.addWidget(QLabel("Lithology:"), 0, 2)
        self.lithology_input = QLineEdit()
        form_layout.addWidget(self.lithology_input, 0, 3)

        form_layout.addWidget(QLabel("Top MD (m):"), 1, 0)
        self.top_md_input = QDoubleSpinBox()
        self.top_md_input.setRange(0, 20000)
        self.top_md_input.setDecimals(1)
        form_layout.addWidget(self.top_md_input, 1, 1)
        form_layout.addWidget(QLabel("Base MD (m):"), 1, 2)
        self.base_md_input = QDoubleSpinBox()
        self.base_md_input.setRange(0, 20000)
        self.base_md_input.setDecimals(1)
        form_layout.addWidget(self.base_md_input, 1, 3)

        form_layout.addWidget(QLabel("Color:"), 2, 0)
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(30, 30)
        self.color_btn.setStyleSheet("background-color: #8B4513;")
        self.color_btn.clicked.connect(self.choose_formation_color)
        form_layout.addWidget(self.color_btn, 2, 1)
        form_layout.addWidget(QLabel("Description:"), 2, 2)
        self.description_input = QLineEdit()
        form_layout.addWidget(self.description_input, 2, 3)

        layout.addWidget(form_group)

        btn_layout = QHBoxLayout()
        self.add_formation_btn = QPushButton("➕ Add Formation")
        self.remove_formation_btn = QPushButton("➖ Remove Formation")
        self.save_formations_btn = QPushButton("💾 Save Formations")
        self.load_formations_btn = QPushButton("📂 Load Formations")
        self.export_formations_btn = QPushButton("📤 Export to CSV")
        self.import_las_btn = QPushButton("📊 Import LAS")
        self.export_las_btn = QPushButton("📊 Export LAS")
        btn_layout.addWidget(self.add_formation_btn)
        btn_layout.addWidget(self.remove_formation_btn)
        btn_layout.addWidget(self.save_formations_btn)
        btn_layout.addWidget(self.load_formations_btn)
        btn_layout.addWidget(self.export_formations_btn)
        btn_layout.addWidget(self.import_las_btn)
        btn_layout.addWidget(self.export_las_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.formation_table = QTableWidget()
        self.formation_table.setAlternatingRowColors(True)
        self.formation_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.formation_table)

        return tab

    # --------------------------------------------------------------
    # تنظیم مدیرهای جداول
    # --------------------------------------------------------------
    def setup_managers(self):
        
        self.bha_manager = BHAManager(self.bha_table)
        self.bha_manager.setup_table()
        
        self.equipment_manager = DownholeEquipmentManager(self.equipment_table)
        self.equipment_manager.setup_table()
        
        self.formation_manager = FormationManager(self.formation_table)
        self.formation_manager.setup_table()

    # --------------------------------------------------------------
    # اتصالات
    # --------------------------------------------------------------
    def setup_connections(self):
        # BHA Tab
        self.add_bha_tool_btn.clicked.connect(self.add_bha_tool)
        self.remove_bha_tool_btn.clicked.connect(self.remove_bha_tool)
        self.save_bha_btn.clicked.connect(self.save_bha_config)
        self.load_bha_btn.clicked.connect(self.load_bha_config)
        self.delete_bha_btn.clicked.connect(self.delete_bha_config)
        self.calculate_bha_btn.clicked.connect(self.calculate_bha_totals)
        self.export_bha_btn.clicked.connect(self.export_bha_data)
        self.bha_selector.currentTextChanged.connect(self.on_bha_selected)

        # Equipment Tab
        self.add_equipment_btn.clicked.connect(self.add_equipment)
        self.remove_equipment_btn.clicked.connect(self.remove_equipment)
        self.calculate_hours_btn.clicked.connect(self.calculate_equipment_hours)
        self.check_service_btn.clicked.connect(self.check_service_due)
        self.save_equipment_btn.clicked.connect(self.save_all_data_to_db)
        self.export_equipment_btn.clicked.connect(self.export_equipment_data)
        self.import_equipment_btn.clicked.connect(self.import_equipment_data)

        # Formation Tab
        self.add_formation_btn.clicked.connect(self.add_formation)
        self.remove_formation_btn.clicked.connect(self.remove_formation)
        self.save_formations_btn.clicked.connect(self.save_all_data_to_db)
        self.load_formations_btn.clicked.connect(self.load_formations)
        self.export_formations_btn.clicked.connect(self.export_formations_csv)
        self.import_las_btn.clicked.connect(self.import_las_file)
        self.export_las_btn.clicked.connect(self.export_las_file)

    # --------------------------------------------------------------
    # Override event handlers
    # --------------------------------------------------------------
    def on_well_changed(self, well_id, well_data):
        self.current_well = well_id
        self.well_label.setText(f"Well: {well_data.get('name', 'Unknown')}" if well_data else f"Well ID: {well_id}")
        self.load_all_data_from_db()

    def on_report_changed(self, report_id, report_info):
        self.current_report_id = report_id
        self.load_all_data_from_db()

    # --------------------------------------------------------------
    # بارگذاری / ذخیره‌سازی متمرکز
    # --------------------------------------------------------------

    def load_all_data_from_db(self):
        """بارگذاری تمام داده‌ها - نسخه اصلاح شده (بدون double load)"""
        if not self.current_well or not self.db:
            return

        # ========== BHA (report-level) ==========
        bha_info = self.db.get_bha_report(
            self.current_well,
            report_id=self.current_report_id
        )
        if bha_info:
            bha_data = bha_info.get('bha_configs') or bha_info.get('bha_data_json')
            if isinstance(bha_data, str):
                try:
                    bha_data = json.loads(bha_data)
                except Exception:
                    bha_data = {}
            if isinstance(bha_data, dict):
                self.bha_data = bha_data
                # لود اولین BHA در جدول
                if self.bha_data:
                    first_key = next(iter(self.bha_data))
                    self.bha_manager.load_data(self.bha_data[first_key])
            elif isinstance(bha_data, list):
                self.bha_data = {"default": bha_data}
                self.bha_manager.load_data(bha_data)
            self.update_bha_selector()
        else:
            self.bha_data = {}
            self.bha_table.setRowCount(0)

        # ========== Downhole Equipment (report-level) ==========
        equip_info = self.db.get_downhole_equipment(
            self.current_well,
            report_id=self.current_report_id
        )
        if equip_info:
            eq_data = equip_info.get('equipment_data', {})
            if isinstance(eq_data, str):
                try:
                    eq_data = json.loads(eq_data)
                except Exception:
                    eq_data = {}
            if isinstance(eq_data, (list, dict)):
                self.equipment_manager.load_data(eq_data)
        else:
            self.equipment_table.setRowCount(0)

        # ========== Formation (well-level) ==========
        form_info = self.db.get_formation_report(self.current_well)
        if form_info:
            formations = form_info.get('formations', [])
            if isinstance(formations, str):
                try:
                    formations = json.loads(formations)
                except Exception:
                    formations = []
            self.formation_manager.load_data(formations)
        else:
            self.formation_table.setRowCount(0)

        logger.info(
            f"Downhole data loaded for well {self.current_well}, "
            f"report {self.current_report_id}"
        )
        
    def save_all_data_to_db(self):
        if not self.current_well:
            self.show_error("No well selected. Please select a well first.")
            return False

        success = True

        try:
            # ========== 1. BHA ==========
            if hasattr(self, 'bha_manager'):
                bha_data = self.bha_manager.get_all_data()
                if bha_data:
                    bha_name = self.bha_name_input.text().strip() if hasattr(self, 'bha_name_input') else "Unnamed BHA"
                    bha_report_data = {
                        "well_id": self.current_well,
                        "report_id": self.current_report_id,
                        "bha_name": bha_name,
                        "bha_data_json": bha_data
                    }
                    result = self.db.save_bha_report(self.current_well, bha_report_data)
                    if not result:
                        success = False


            # ========== 2. Downhole Equipment ==========
            if hasattr(self, 'equipment_manager'):
                equipment_data = self.equipment_manager.get_all_data()
                if equipment_data:
                    equip_data = {
                        "well_id": self.current_well,
                        "report_id": self.current_report_id,
                        "equipment_data_json": equipment_data
                    }
                    result = self.db.save_downhole_equipment(self.current_well, equip_data)
                    if not result:
                        success = False


            # ========== 3. Formation Evaluation ==========
            if hasattr(self, 'formation_manager'):
                formation_data = self.formation_manager.get_all_data()
                if formation_data:
                    form_data = {
                        "well_id": self.current_well,
                        "report_id": self.current_report_id,
                        "report_name": f"Formation Report {date.today()}",
                        "formations": formation_data
                    }
                    result = self.db.save_formation_report(self.current_well, form_data)
                    if not result:
                        success = False

            if success:
                self.show_success("All downhole data saved successfully")
            else:
                self.show_error("Some downhole data failed to save")

            return success

        except Exception as e:
            logger.error(f"Save error: {e}")
            import traceback
            traceback.print_exc()
            self.show_error(f"Save error: {str(e)}")
            return False
        
    def save_data(self):
        """For AutoSaveManager"""
        return self.save_all_data_to_db()

    def load_data(self):
        """General load"""
        self.load_all_data_from_db()

    # --------------------------------------------------------------
    # BHA Operations
    # --------------------------------------------------------------
    def add_bha_tool(self):
        """اضافه کردن کامپوننت BHA با دیالوگ"""
        from dialogs.drilling_report_dialogs import AddBHAComponentDialog
        
        dlg = AddBHAComponentDialog(self)
        if dlg.exec():
            data = dlg.get_result()
            if data and hasattr(self, 'bha_manager'):
                row = self.bha_table.rowCount()
                self.bha_table.insertRow(row)
                headers = [self.bha_table.horizontalHeaderItem(c).text()
                          for c in range(self.bha_table.columnCount())]
                for col, header in enumerate(headers):
                    val = data.get(header, "")
                    item = QTableWidgetItem(str(val))
                    self.bha_table.setItem(row, col, item)
                self.show_message(f"{data.get('Tool Type', 'Component')} added to BHA")

    def remove_bha_tool(self):
        self.bha_manager.delete_row()

    def save_bha_config(self):
        name = self.bha_name_input.text().strip()
        if not name:
            self.show_error("Enter BHA name")
            return
        data = self.bha_manager.get_all_data()
        self.bha_data[name] = data
        self.update_bha_selector()
        self.show_success(f"BHA '{name}' saved")

    def load_bha_config(self):
        name = self.bha_selector.currentText()
        if name in self.bha_data:
            self.bha_manager.load_data(self.bha_data[name])
            self.bha_name_input.setText(name)
            self.show_success(f"BHA '{name}' loaded")

    def delete_bha_config(self):
        name = self.bha_selector.currentText()
        if name in self.bha_data:
            del self.bha_data[name]
            self.update_bha_selector()
            self.bha_name_input.clear()
            self.bha_table.setRowCount(0)
            self.show_success(f"BHA '{name}' deleted")

    def calculate_bha_totals(self):
        length, weight = self.bha_manager.calculate_totals()
        QMessageBox.information(self, "Totals", f"Total Length: {length:.2f} m\nTotal Weight: {weight:.0f} kg")

    def export_bha_data(self):
        ExportManager(self).export_table_with_dialog(self.bha_table, "bha_data")

    def update_bha_selector(self):
        self.bha_selector.clear()
        self.bha_selector.addItem("-- Select BHA --")
        self.bha_selector.addItems(list(self.bha_data.keys()))

    def on_bha_selected(self, name):
        if name != "-- Select BHA --":
            self.load_bha_config()

    # --------------------------------------------------------------
    # Equipment Operations
    # --------------------------------------------------------------
    def add_equipment(self):
        if hasattr(self, 'equipment_manager'):
            self.equipment_manager.add_default_row()
            self.show_message("Equipment added")
        else:
            self.show_error("Equipment manager not initialized")

    def remove_equipment(self):
        current_row = self.equipment_table.currentRow()
        if current_row >= 0:
            self.equipment_table.removeRow(current_row)
            self.show_message("Equipment removed")
        else:
            self.show_error("Please select a row to remove")
            
    def calculate_equipment_hours(self):
        totals = self.equipment_manager.calculate_hours()
        QMessageBox.information(self, "Hours", f"Sliding: {totals['sliding']:.1f} h\nRotation: {totals['rotation']:.1f} h\nPumping: {totals['pumping']:.1f} h")

    def check_service_due(self):
        due = self.equipment_manager.check_service_due()
        if due:
            msg = "Equipment due for service:\n" + "\n".join(f"• {d['name']}" for d in due)
        else:
            msg = "All equipment up to date."
        QMessageBox.information(self, "Service Status", msg)

    def export_equipment_data(self):
        ExportManager(self).export_table_with_dialog(self.equipment_table, "equipment")

    def import_equipment_data(self):
        file, _ = QFileDialog.getOpenFileName(self, "Import Equipment", "", "JSON/CSV (*.json *.csv)")
        if file:
            try:
                import pandas as pd
                if file.endswith('.json'):
                    data = json.load(open(file, encoding='utf-8'))
                else:
                    data = pd.read_csv(file).to_dict('records')
                self.equipment_manager.load_data(data)
                self.show_success(f"Imported {len(data)} records")
            except Exception as e:
                self.show_error(f"Import failed: {e}")

    # --------------------------------------------------------------
    # Formation Operations
    # --------------------------------------------------------------
    def choose_formation_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.color_btn.setStyleSheet(f"background-color: {color.name()};")
            self.formation_manager.current_color = color.name()

    def add_formation(self):
        name = self.formation_name_input.text().strip()
        if not name:
            self.show_error("Enter formation name")
            return
        
        top = self.top_md_input.value()
        base = self.base_md_input.value()
        if base <= top:
            self.show_error("Base MD must be > Top MD")
            return
        
        data = {
            "Formation Name": name,
            "Lithology": self.lithology_input.text().strip(),
            "Age": "",
            "Top MD (m)": str(top),
            "Base MD (m)": str(base),
            "Thickness (m)": str(base - top),
            "Top TVD (m)": str(top),
            "Color": getattr(self.formation_manager, 'current_color', '#8B4513'),
            "Description": self.description_input.text().strip(),
            "Properties": ""
        }
        
        if hasattr(self, 'formation_manager'):
            self.formation_manager.add_formation_row(data)
            self.clear_formation_form()
            self.show_success(f"Formation '{name}' added")
        else:
            self.show_error("Formation manager not initialized")

    def clear_formation_form(self):
        self.formation_name_input.clear()
        self.lithology_input.clear()
        self.top_md_input.setValue(0)
        self.base_md_input.setValue(0)
        self.description_input.clear()
    def remove_formation(self):
        self.formation_manager.delete_row()
        self.show_message("Formation removed")

    def load_formations(self):
        if not self.current_well:
            self.show_error("No well selected")
            return
        self.load_all_data_from_db()
        self.show_success("Formations reloaded")

    def export_formations_csv(self):
        ExportManager(self).export_table_with_dialog(self.formation_table, "formations")

    def import_las_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Import LAS", "", "LAS Files (*.las)")
        if file:
            success = self.formation_manager.import_from_las(file)
            if success:
                self.show_success("LAS import successful")
            else:
                self.show_error("LAS import failed")

    def export_las_file(self):
        file, _ = QFileDialog.getSaveFileName(self, "Export LAS", "formations.las", "LAS Files (*.las)")
        if file:
            self.formation_manager.export_to_las(file)
            self.show_success(f"Exported to {file}")

    # --------------------------------------------------------------
    # پاکسازی
    # --------------------------------------------------------------
    def cleanup(self):
        if hasattr(self, 'auto_save_timer') and self.auto_save_timer.isActive():
            self.auto_save_timer.stop()
        logger.info("DownholeWidget cleanup complete")

class BHAManager:
    def __init__(self, table):
        self.table = table
        self.table_manager = TableManager(table)
        self.saved_bhas = {}

    def setup_table(self):
        headers = ["Tool Type", "OD (in)", "ID (in)", "Length (m)", "Serial No",
                   "Weight (kg)", "Connection Type", "Make-up Torque (ft-lb)", "Remarks"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        widths = [150, 80, 80, 100, 120, 100, 120, 120, 200]
        for col, width in enumerate(widths):
            self.table.setColumnWidth(col, width)

    def add_default_row(self, tool_type=""):
        defaults = {
            "Bit": ["PDC Bit", "8.5", "2.5", "0.3", "", "150", "API Reg", "25000", "New bit"],
            "Drill Collar": ["Drill Collar", "8.0", "2.8", "9.0", "", "2500", "API NC", "32000", "Heavy weight"],
            "MWD": ["MWD Tool", "6.75", "2.5", "4.5", "", "120", "API FH", "18000", "Directional"],
            "Stabilizer": ["Stabilizer", "8.25", "3.0", "1.5", "", "350", "API Reg", "22000", "Full gauge"],
            "Shock Sub": ["Shock Sub", "8.0", "3.0", "3.0", "", "450", "API NC", "28000", "Vibration dampener"]
        }
        row = self.table.rowCount()
        self.table.insertRow(row)
        data = defaults.get(tool_type, ["", "0.00", "0.00", "0.00", "", "0", "", "0", ""])
        for col, val in enumerate(data):
            item = QTableWidgetItem(str(val))
            if col in [1, 2, 3, 5, 7]:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, col, item)
        return row

    def calculate_totals(self):
        total_length = total_weight = 0.0
        for row in range(self.table.rowCount()):
            try:
                total_length += float(self.table.item(row, 3).text() or 0)
                total_weight += float(self.table.item(row, 5).text() or 0)
            except: pass
        return total_length, total_weight

    def get_all_data(self):
        return [ { self.table.horizontalHeaderItem(col).text(): (self.table.item(row, col).text() if self.table.item(row, col) else "")
                  for col in range(self.table.columnCount()) } for row in range(self.table.rowCount()) ]

    def load_data(self, data):
        """بارگذاری داده‌ها در جدول - نسخه خوانا"""
        self.table.setRowCount(0)
        if not data:
            return
        for row_data in data:
            row = self.table.rowCount()
            self.table.insertRow(row)
            if isinstance(row_data, dict):
                for col, key in enumerate(row_data.keys()):
                    if col < self.table.columnCount():
                        self.table.setItem(row, col, QTableWidgetItem(str(row_data[key])))
            elif isinstance(row_data, (list, tuple)):
                for col, val in enumerate(row_data):
                    if col < self.table.columnCount():
                        self.table.setItem(row, col, QTableWidgetItem(str(val)))
                        
    def delete_row(self):
        r = self.table.currentRow()
        if r >= 0: self.table.removeRow(r)


class DownholeEquipmentManager:
    def __init__(self, table):
        self.table = table
        self.table_manager = TableManager(table)

    def setup_table(self):
        headers = ["Equipment Name", "Type", "Serial No", "ID", "Manufacturer",
                   "Install Date", "Sliding Hours", "Rotation Hours", "Pumping Hours",
                   "Total Hours", "Cycles", "Last Service", "Next Service", "Status", "Remarks"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        for col, w in enumerate([150, 100, 120, 80, 120, 100, 100, 100, 100, 100, 80, 100, 100, 80, 150]):
            self.table.setColumnWidth(col, w)

    def add_default_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        today = date.today().strftime("%Y-%m-%d")
        default = ["", "", f"SN{row+1:03d}", f"EQ{row+1:03d}", "", today, "0.0", "0.0", "0.0", "0.0", "0", today, (date.today() + timedelta(days=30)).strftime("%Y-%m-%d"), "Active", ""]
        for col, val in enumerate(default):
            item = QTableWidgetItem(val)
            if col in [6,7,8,9,10]: item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, col, item)
        return row

    def calculate_hours(self):
        sums = {"sliding":0.0, "rotation":0.0, "pumping":0.0}
        for row in range(self.table.rowCount()):
            for i, key in enumerate(["sliding","rotation","pumping"]):
                try: sums[key] += float(self.table.item(row, 6+i).text() or 0)
                except: pass
        return {**sums, "total": sum(sums.values())}

    def check_service_due(self):
        due = []
        today = date.today()
        for row in range(self.table.rowCount()):
            try:
                next_date = datetime.strptime(self.table.item(row, 12).text(), "%Y-%m-%d").date()
                if next_date <= today:
                    due.append({"name": self.table.item(row, 0).text(), "row": row})
            except: pass
        return due

    def get_all_data(self):
        return [ { self.table.horizontalHeaderItem(col).text(): (self.table.item(row, col).text() if self.table.item(row, col) else "")
                  for col in range(self.table.columnCount()) } for row in range(self.table.rowCount()) ]

    def load_data(self, data):
        self.table.setRowCount(0)
        for row_data in data:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, header in enumerate([self.table.horizontalHeaderItem(c).text() for c in range(self.table.columnCount())]):
                self.table.setItem(row, col, QTableWidgetItem(str(row_data.get(header, ""))))

    def delete_row(self):
        r = self.table.currentRow()
        if r >= 0: self.table.removeRow(r)


class FormationManager:
    def __init__(self, table):
        self.table = table
        self.table_manager = TableManager(table)
        self.current_color = "#8B4513"

    def setup_table(self):
        headers = ["Formation Name", "Lithology", "Age", "Top MD (m)", "Base MD (m)",
                   "Thickness (m)", "Top TVD (m)", "Color", "Description", "Properties"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        for col, w in enumerate([150, 100, 80, 100, 100, 100, 100, 80, 200, 150]):
            self.table.setColumnWidth(col, w)

    def add_formation_row(self, data=None):
        if not data:
            data = {"Formation Name": f"Formation {self.table.rowCount()+1}", "Lithology": "Shale", "Age": "", "Top MD (m)": "0", "Base MD (m)": "100", "Thickness (m)": "100", "Top TVD (m)": "0", "Color": self.current_color, "Description": "", "Properties": ""}
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, header in enumerate([self.table.horizontalHeaderItem(c).text() for c in range(self.table.columnCount())]):
            item = QTableWidgetItem(str(data.get(header, "")))
            if col in [3,4,5,6]: item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if col == 7 and data.get("Color", "").startswith("#"):
                item.setBackground(QColor(data["Color"]))
            self.table.setItem(row, col, item)

    def get_all_data(self):
        return [ { self.table.horizontalHeaderItem(col).text(): (self.table.item(row, col).text() if self.table.item(row, col) else "")
                  for col in range(self.table.columnCount()) } for row in range(self.table.rowCount()) ]

    def load_data(self, data):
        self.table.setRowCount(0)
        for d in data: self.add_formation_row(d)

    def import_from_las(self, filepath):
        try:
            import lasio
            las = lasio.read(filepath)
            self.table.setRowCount(0)
            if "DEPT" in las.curves:
                depths = las.curves["DEPT"].data
                formations = las.curves.get("FORMATION", [""]*len(depths))
                groups = {}
                for d, f in zip(depths, formations):
                    if f not in groups: groups[f] = []
                    groups[f].append(d)
                for name, dvals in groups.items():
                    self.add_formation_row({"Formation Name": name, "Top MD (m)": str(min(dvals)), "Base MD (m)": str(max(dvals)), "Color": self.current_color})
                return True
        except Exception as e:
            logger.error(f"LAS import error: {e}")
        return False

    def export_to_las(self, filepath):
        try:
            import lasio
            las = lasio.LASFile()
            depths, formations = [], []
            for row in range(self.table.rowCount()):
                try:
                    top = float(self.table.item(row, 3).text())
                    base = float(self.table.item(row, 4).text())
                    name = self.table.item(row, 0).text()
                    depths.append((top+base)/2)
                    formations.append(name)
                except: pass
            if depths:
                las.add_curve("DEPT", depths, unit="m")
                las.add_curve("FORMATION", formations)
                las.write(filepath, version=2.0)
                return True
        except Exception as e:
            logger.error(f"LAS export error: {e}")
        return False

    def delete_row(self):
        r = self.table.currentRow()
        if r >= 0: self.table.removeRow(r)