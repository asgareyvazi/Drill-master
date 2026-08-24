"""
w8_Safety_Widget.py (بازنویسی کامل)
Comprehensive Safety Management Module with Database Integration
"""

import logging
import json
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional

from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtGui import *

from core.managers import (
    TableManager, TableButtonManager, ExportManager,
    setup_widget_with_managers, StatusBarManager
)
from core.database import DatabaseManager, WasteRecord, BOPComponent, SafetyIncident, SafetyReport
from core.base_tab import DrillTabBase
from core.standards import bop_test_interval_days

logger = logging.getLogger(__name__)


# ==================== Safety & BOP Tab ====================
class SafetyBOPTab(QWidget):
    """Safety and BOP Management Tab"""

    def __init__(self, parent_widget):
        super().__init__()
        self.parent = parent_widget
        self.db = parent_widget.db
        self.current_well_id = parent_widget.current_well_id
        self.current_report_id = parent_widget.current_report_id
        self.table_managers = {}
        self.init_ui()
        self.setup_connections()

    def init_ui(self):
        layout = QVBoxLayout()

        # Safety Drills Section
        drills_group = QGroupBox("Safety Drills")
        drills_layout = QGridLayout()

        drills_layout.addWidget(QLabel("Last Fire Drill:"), 0, 0)
        self.last_fire_drill = QDateEdit()
        self.last_fire_drill.setDate(QDate.currentDate().addDays(-7))
        self.last_fire_drill.setCalendarPopup(True)
        drills_layout.addWidget(self.last_fire_drill, 0, 1)

        drills_layout.addWidget(QLabel("Last BOP Drill:"), 0, 2)
        self.last_bop_drill = QDateEdit()
        self.last_bop_drill.setDate(QDate.currentDate().addDays(-14))
        self.last_bop_drill.setCalendarPopup(True)
        drills_layout.addWidget(self.last_bop_drill, 0, 3)

        drills_layout.addWidget(QLabel("Last H2S Drill:"), 1, 0)
        self.last_h2s_drill = QDateEdit()
        self.last_h2s_drill.setDate(QDate.currentDate().addDays(-21))
        self.last_h2s_drill.setCalendarPopup(True)
        drills_layout.addWidget(self.last_h2s_drill, 1, 1)

        drills_layout.addWidget(QLabel("Days without LTI:"), 1, 2)
        self.days_no_lti = QSpinBox()
        self.days_no_lti.setRange(0, 10000)
        self.days_no_lti.setValue(120)
        drills_layout.addWidget(self.days_no_lti, 1, 3)

        update_lti_btn = QPushButton("🔄 Update LTI Days")
        update_lti_btn.clicked.connect(self.update_lti_days)
        drills_layout.addWidget(update_lti_btn, 2, 0, 1, 4)

        drills_group.setLayout(drills_layout)
        layout.addWidget(drills_group)

        # BOP Tests Section
        bop_group = QGroupBox("BOP Tests")
        bop_layout = QGridLayout()

        bop_layout.addWidget(QLabel("Last Rams Test:"), 0, 0)
        self.last_rams_test = QDateEdit()
        self.last_rams_test.setDate(QDate.currentDate().addDays(-10))
        self.last_rams_test.setCalendarPopup(True)
        bop_layout.addWidget(self.last_rams_test, 0, 1)

        bop_layout.addWidget(QLabel("Test Pressure (psi):"), 0, 2)
        self.test_pressure = QDoubleSpinBox()
        self.test_pressure.setRange(0, 20000)
        self.test_pressure.setValue(5000)
        self.test_pressure.setSuffix(" psi")
        bop_layout.addWidget(self.test_pressure, 0, 3)

        bop_layout.addWidget(QLabel("Last Koomey Test:"), 1, 0)
        self.last_koomey_test = QDateEdit()
        self.last_koomey_test.setDate(QDate.currentDate().addDays(-5))
        self.last_koomey_test.setCalendarPopup(True)
        bop_layout.addWidget(self.last_koomey_test, 1, 1)

        bop_layout.addWidget(QLabel("Days Since Last Test:"), 1, 2)
        self.days_since_last_test = QSpinBox()
        self.days_since_last_test.setRange(0, 365)
        self.days_since_last_test.setValue(5)
        bop_layout.addWidget(self.days_since_last_test, 1, 3)

        calculate_days_btn = QPushButton("🔄 Calculate Days Since Test")
        calculate_days_btn.clicked.connect(self.calculate_days_since_test)
        bop_layout.addWidget(calculate_days_btn, 2, 0, 1, 4)

        # BOP Test Report ComboBox
        bop_layout.addWidget(QLabel("BOP Test Report:"), 3, 0)
        self.bop_test_report = QComboBox()
        self.bop_test_report.addItems([
            "Weekly Routine Test", "Monthly Full Test", "Post-Maintenance Test",
            "Pre-Spud Test", "Annular Function Test", "Pipe Rams Function Test",
            "Shear Rams Function Test", "Choke & Kill Line Test",
            "Accumulator (Koomey) Test", "Emergency Disconnect Test",
            "Shallow Water Test", "Deepwater Test", "Other - Custom"
        ])
        self.bop_test_report.setEditable(True)
        self.bop_test_report.setCurrentText("Weekly Routine Test")
        bop_layout.addWidget(self.bop_test_report, 3, 1)

        bop_layout.addWidget(QLabel("Test Status:"), 3, 2)
        self.test_status = QComboBox()
        self.test_status.addItems([
            "Scheduled", "In Progress", "Completed - Pass",
            "Completed - Fail", "Cancelled", "Postponed"
        ])
        self.test_status.setCurrentText("Scheduled")
        bop_layout.addWidget(self.test_status, 3, 3)

        add_test_btn = QPushButton("➕ Add New Test Type")
        add_test_btn.clicked.connect(self.add_new_test_type)
        bop_layout.addWidget(add_test_btn, 4, 0, 1, 4)

        bop_group.setLayout(bop_layout)
        layout.addWidget(bop_group)

        # BOP Stack Table
        bop_stack_group = QGroupBox("BOP Stack & Wellhead")
        bop_stack_layout = QVBoxLayout()

        self.bop_stack_table = QTableWidget(0, 8)
        self.bop_stack_table.setHorizontalHeaderLabels([
            "Name", "Type", "WP (psi)", "Size (in)", "RAMs",
            "Last Test", "Next Due", "Remarks"
        ])
        self.bop_stack_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.bop_stack_table.setEditTriggers(QTableWidget.AllEditTriggers)

        self.bop_table_manager = TableManager(self.bop_stack_table, self)
        self.table_managers['bop'] = self.bop_table_manager

        bop_stack_layout.addWidget(self.bop_stack_table)

        bop_button_layout = QHBoxLayout()
        self.add_bop_btn = QPushButton("➕ Add BOP Component")
        self.remove_bop_btn = QPushButton("➖ Remove BOP Component")
        self.calculate_bop_btn = QPushButton("🔄 Calculate Test Schedule")
        self.export_bop_btn = QPushButton("📤 Export BOP Data")

        bop_button_layout.addWidget(self.add_bop_btn)
        bop_button_layout.addWidget(self.remove_bop_btn)
        bop_button_layout.addWidget(self.calculate_bop_btn)
        bop_button_layout.addWidget(self.export_bop_btn)
        bop_button_layout.addStretch()

        bop_stack_layout.addLayout(bop_button_layout)
        bop_stack_group.setLayout(bop_stack_layout)
        layout.addWidget(bop_stack_group)

        self.setLayout(layout)

    def add_new_test_type(self):
        text, ok = QInputDialog.getText(self, "Add New BOP Test Type", "Enter new BOP test type:", text="Custom Test - ")
        if ok and text:
            if self.bop_test_report.findText(text) == -1:
                self.bop_test_report.addItem(text)
                self.bop_test_report.setCurrentText(text)
                self.parent.show_success(f"New test type added: {text}")
            else:
                self.parent.show_message(f"Test type '{text}' already exists")

    def setup_connections(self):
        self.add_bop_btn.clicked.connect(self.add_bop_row)
        self.remove_bop_btn.clicked.connect(self.remove_bop_row)
        self.calculate_bop_btn.clicked.connect(self.calculate_bop_schedule)
        self.export_bop_btn.clicked.connect(self.export_bop_data)

    def add_bop_row(self):
        if 'bop' in self.table_managers:
            self.table_managers['bop'].add_row()
            row = self.bop_stack_table.rowCount() - 1
            self.setup_bop_row_with_defaults(row)
        else:
            row = self.bop_stack_table.rowCount()
            self.bop_stack_table.insertRow(row)
            self.setup_bop_row_with_defaults(row)

    def setup_bop_row_with_defaults(self, row):
        today = QDate.currentDate()
        defaults = [
            "New Component", "Type", "5000", "13-5/8", "N/A",
            today.toString("yyyy-MM-dd"),
            today.addDays(bop_test_interval_days()).toString("yyyy-MM-dd"),
            "In Service"
        ]
        for col, value in enumerate(defaults):
            item = QTableWidgetItem(value)
            if col in [2]:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.bop_stack_table.setItem(row, col, item)

    def remove_bop_row(self):
        current_row = self.bop_stack_table.currentRow()
        if current_row >= 0:
            self.bop_stack_table.removeRow(current_row)

            if self.db and self.parent.current_well_id:
                self.save_to_database(self.parent.current_well_id, getattr(self.parent, 'current_report_id', None))

    def calculate_bop_schedule(self):
        today = QDate.currentDate()
        overdue_count = 0
        warning_count = 0
        for row in range(self.bop_stack_table.rowCount()):
            last_test_item = self.bop_stack_table.item(row, 5)
            if last_test_item and last_test_item.text():
                try:
                    last_test_date = QDate.fromString(last_test_item.text(), "yyyy-MM-dd")
                    if last_test_date.isValid():
                        next_due = last_test_date.addDays(bop_test_interval_days())
                        if next_due < today:
                            next_due = today.addDays(7)
                            overdue_count += 1
                            self.highlight_bop_row(row, QColor(255, 220, 220))
                        elif next_due <= today.addDays(7):
                            warning_count += 1
                            self.highlight_bop_row(row, QColor(255, 255, 200))
                        else:
                            self.clear_bop_row_highlight(row)
                        next_due_item = QTableWidgetItem(next_due.toString("yyyy-MM-dd"))
                        self.bop_stack_table.setItem(row, 6, next_due_item)
                except:
                    pass
        message = "✅ BOP Test Schedule Updated\n\n"
        if overdue_count > 0:
            message += f"⚠️ {overdue_count} components are OVERDUE for testing\n"
        if warning_count > 0:
            message += f"⚠️ {warning_count} components need testing within 7 days\n"
        if overdue_count == 0 and warning_count == 0:
            message += "✅ All BOP components are up to date"
        QMessageBox.information(self, "BOP Schedule Update", message)

    def highlight_bop_row(self, row, color):
        for col in range(self.bop_stack_table.columnCount()):
            item = self.bop_stack_table.item(row, col)
            if item:
                item.setBackground(color)

    def clear_bop_row_highlight(self, row):
        for col in range(self.bop_stack_table.columnCount()):
            item = self.bop_stack_table.item(row, col)
            if item:
                item.setBackground(QColor(255, 255, 255))

    def export_bop_data(self):
        export_manager = ExportManager(self)
        export_manager.export_table_with_dialog(self.bop_stack_table, "bop_data")

    def calculate_days_since_test(self):
        today = QDate.currentDate()
        days_since_rams = self.last_rams_test.date().daysTo(today)
        days_since_koomey = self.last_koomey_test.date().daysTo(today)
        self.days_since_last_test.setValue(max(days_since_rams, days_since_koomey))
        test_report = self.bop_test_report.currentText()
        test_status = self.test_status.currentText()
        QMessageBox.information(self, "BOP Test Information",
            f"📋 Test Report: {test_report}\n"
            f"📊 Status: {test_status}\n"
            f"⏰ Days since last Rams test: {days_since_rams}\n"
            f"⏰ Days since last Koomey test: {days_since_koomey}\n"
            f"📈 Maximum days: {max(days_since_rams, days_since_koomey)}\n\n"
            f"⚠️ {'TEST OVERDUE!' if max(days_since_rams, days_since_koomey) > bop_test_interval_days() else 'Test within schedule'}"
        )

    def update_lti_days(self):
        current_days = self.days_no_lti.value()
        self.days_no_lti.setValue(current_days + 1)
        QMessageBox.information(self, "LTI Days Updated", f"Days without LTI: {current_days + 1}")

    def save_to_database(self, well_id, report_id=None):
        if not self.db:
            return False
        try:
            bop_stack_data = []
            for row in range(self.bop_stack_table.rowCount()):
                row_data = {}
                for col in range(self.bop_stack_table.columnCount()):
                    header = self.bop_stack_table.horizontalHeaderItem(col).text()
                    item = self.bop_stack_table.item(row, col)
                    row_data[header] = item.text() if item else ""
                bop_stack_data.append(row_data)
            report_data = {
                'well_id': well_id,
                'report_id': report_id,
                'report_date': date.today(),
                'report_type': 'Daily',
                'last_fire_drill': self.last_fire_drill.date().toPython(),
                'last_bop_drill': self.last_bop_drill.date().toPython(),
                'last_h2s_drill': self.last_h2s_drill.date().toPython(),
                'days_without_lti': self.days_no_lti.value(),
                'last_rams_test': self.last_rams_test.date().toPython(),
                'test_pressure': self.test_pressure.value(),
                'last_koomey_test': self.last_koomey_test.date().toPython(),
                'days_since_last_test': self.days_since_last_test.value(),
                'bop_stack_json': bop_stack_data
            }
            record_id = self.db.save_safety_report(report_data)
            if record_id:
                for component_data in bop_stack_data:
                    comp = {
                        'well_id': well_id,
                        'safety_report_id': record_id,
                        'component_name': component_data.get('Name', ''),
                        'component_type': component_data.get('Type', ''),
                        'working_pressure': float(component_data.get('WP (psi)', 0)),
                        'size': component_data.get('Size (in)', ''),
                        'ram_type': component_data.get('RAMs', ''),
                        'last_test_date': QDate.fromString(component_data['Last Test'], "yyyy-MM-dd").toPython() if component_data.get('Last Test') else None,
                        'next_test_due': QDate.fromString(component_data['Next Due'], "yyyy-MM-dd").toPython() if component_data.get('Next Due') else None,
                        'remarks': component_data.get('Remarks', '')
                    }
                    self.db.save_bop_component(comp)
                return True
        except Exception as e:
            logger.error(f"Error saving BOP data: {e}")
        return False

    def load_from_database(self, well_id, report_id=None):
        if not self.db:
            return False
        try:
            report_data = self.db.get_safety_report(well_id, report_id=report_id)
            if report_data:

                def safe_set_date(widget, value, default_days_ago=7):
                    if value is None:
                        widget.setDate(QDate.currentDate().addDays(-default_days_ago))
                    elif isinstance(value, date):
                        widget.setDate(QDate(value.year, value.month, value.day))
                    elif isinstance(value, QDate):
                        widget.setDate(value)
                    else:
                        try:
                            from datetime import datetime
                            dt = datetime.strptime(str(value), "%Y-%m-%d").date()
                            widget.setDate(QDate(dt.year, dt.month, dt.day))
                        except:
                            widget.setDate(QDate.currentDate().addDays(-default_days_ago))
                            
                self.last_fire_drill.setDate(report_data.get('last_fire_drill', QDate.currentDate().addDays(-7)))
                self.last_bop_drill.setDate(report_data.get('last_bop_drill', QDate.currentDate().addDays(-14)))
                self.last_h2s_drill.setDate(report_data.get('last_h2s_drill', QDate.currentDate().addDays(-21)))
                self.days_no_lti.setValue(report_data.get('days_without_lti', 0))
                self.last_rams_test.setDate(report_data.get('last_rams_test', QDate.currentDate().addDays(-10)))
                self.test_pressure.setValue(report_data.get('test_pressure', 0))
                self.last_koomey_test.setDate(report_data.get('last_koomey_test', QDate.currentDate().addDays(-5)))
                self.days_since_last_test.setValue(report_data.get('days_since_last_test', 0))
                if report_data.get('bop_test_report'):
                    idx = self.bop_test_report.findText(report_data['bop_test_report'])
                    if idx >= 0: self.bop_test_report.setCurrentIndex(idx)
                if report_data.get('test_status'):
                    idx = self.test_status.findText(report_data['test_status'])
                    if idx >= 0: self.test_status.setCurrentIndex(idx)

                bop_stack = report_data.get('bop_stack_json', [])
                self.bop_stack_table.setRowCount(0)
                for comp in bop_stack:
                    self.add_bop_row()
                    row = self.bop_stack_table.rowCount() - 1
                    for col, key in enumerate(['Name', 'Type', 'WP (psi)', 'Size (in)', 'RAMs', 'Last Test', 'Next Due', 'Remarks']):
                        self.bop_stack_table.setItem(row, col, QTableWidgetItem(str(comp.get(key, ''))))
                return True
        except Exception as e:
            logger.error(f"Error loading BOP data: {e}")
        return False


# ==================== Waste Management Tab ====================
class WasteManagementTab(QWidget):
    """Waste Management Tab"""

    def __init__(self, parent_widget):
        super().__init__()
        self.parent = parent_widget
        self.db = parent_widget.db
        self.current_well_id = parent_widget.current_well_id
        self.current_report_id = parent_widget.current_report_id
        self.table_managers = {}
        self.init_ui()
        self.setup_connections()

    def init_ui(self):
        layout = QVBoxLayout()

        waste_group = QGroupBox("Waste Management - Current Status")
        waste_form = QGridLayout()

        waste_form.addWidget(QLabel("Recycled (BBL):"), 0, 0)
        self.recycled_volume = QDoubleSpinBox()
        self.recycled_volume.setRange(0, 10000)
        self.recycled_volume.setValue(150.5)
        self.recycled_volume.setSuffix(" BBL")
        waste_form.addWidget(self.recycled_volume, 0, 1)

        waste_form.addWidget(QLabel("pH:"), 0, 2)
        self.waste_ph = QDoubleSpinBox()
        self.waste_ph.setRange(0, 14)
        self.waste_ph.setValue(7.2)
        waste_form.addWidget(self.waste_ph, 0, 3)

        waste_form.addWidget(QLabel("Turbidity/TSS:"), 1, 0)
        self.turbidity = QLineEdit()
        self.turbidity.setText("15 NTU")
        waste_form.addWidget(self.turbidity, 1, 1)

        waste_form.addWidget(QLabel("Hardness/Ca++:"), 1, 2)
        self.hardness = QLineEdit()
        self.hardness.setText("250 mg/L")
        waste_form.addWidget(self.hardness, 1, 3)

        waste_form.addWidget(QLabel("Cutting Trans. (m³):"), 2, 0)
        self.cutting_volume = QDoubleSpinBox()
        self.cutting_volume.setRange(0, 1000)
        self.cutting_volume.setValue(25.3)
        self.cutting_volume.setSuffix(" m³")
        waste_form.addWidget(self.cutting_volume, 2, 1)

        waste_form.addWidget(QLabel("Oil Content (ppm):"), 2, 2)
        self.oil_content = QDoubleSpinBox()
        self.oil_content.setRange(0, 10000)
        self.oil_content.setValue(45.2)
        self.oil_content.setSuffix(" ppm")
        waste_form.addWidget(self.oil_content, 2, 3)

        waste_form.addWidget(QLabel("Waste Type:"), 3, 0)
        self.waste_type = QComboBox()
        self.waste_type.addItems(["Drilling Waste", "Cuttings", "Mud", "Chemicals", "Packaging", "Other"])
        waste_form.addWidget(self.waste_type, 3, 1)

        waste_form.addWidget(QLabel("Waste Disposal Method:"), 3, 2)
        self.disposal_method = QComboBox()
        self.disposal_method.addItems(["Landfill", "Recycle", "Incineration", "Treatment", "Other"])
        waste_form.addWidget(self.disposal_method, 3, 3)

        waste_form.addWidget(QLabel("Remarks:"), 4, 0)
        self.waste_remarks = QTextEdit()
        self.waste_remarks.setMaximumHeight(80)
        self.waste_remarks.setPlaceholderText("Enter waste management remarks...")
        waste_form.addWidget(self.waste_remarks, 4, 1, 1, 3)

        current_buttons = QHBoxLayout()
        save_current_btn = QPushButton("💾 Save Current Data")
        clear_current_btn = QPushButton("🗑️ Clear Form")
        save_current_btn.clicked.connect(self.save_current_waste_data)
        clear_current_btn.clicked.connect(self.clear_waste_form)
        current_buttons.addWidget(save_current_btn)
        current_buttons.addWidget(clear_current_btn)
        current_buttons.addStretch()
        waste_form.addLayout(current_buttons, 5, 0, 1, 4)
        waste_group.setLayout(waste_form)
        layout.addWidget(waste_group)

        # Waste History Table
        waste_table_group = QGroupBox("Waste Management History")
        waste_table_layout = QVBoxLayout()

        self.waste_table = QTableWidget(0, 6)
        self.waste_table.setHorizontalHeaderLabels(["Date", "Type", "Volume (BBL)", "pH", "Disposal Method", "Remarks"])
        self.waste_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.waste_table.setEditTriggers(QTableWidget.AllEditTriggers)

        self.waste_table_manager = TableManager(self.waste_table, self)
        self.table_managers['waste'] = self.waste_table_manager

        waste_table_layout.addWidget(self.waste_table)

        waste_btn_layout = QHBoxLayout()
        self.add_waste_btn = QPushButton("➕ Add Waste Record")
        self.remove_waste_btn = QPushButton("➖ Remove Row")
        self.calculate_waste_btn = QPushButton("🔄 Calculate Totals")
        self.export_waste_btn = QPushButton("📤 Export Waste Data")

        waste_btn_layout.addWidget(self.add_waste_btn)
        waste_btn_layout.addWidget(self.remove_waste_btn)
        waste_btn_layout.addWidget(self.calculate_waste_btn)
        waste_btn_layout.addWidget(self.export_waste_btn)
        waste_btn_layout.addStretch()

        waste_table_layout.addLayout(waste_btn_layout)
        waste_table_group.setLayout(waste_table_layout)
        layout.addWidget(waste_table_group)

        self.setLayout(layout)

    def setup_connections(self):
        self.add_waste_btn.clicked.connect(self.add_waste_row)
        self.remove_waste_btn.clicked.connect(self.remove_waste_row)
        self.calculate_waste_btn.clicked.connect(self.calculate_waste_totals)
        self.export_waste_btn.clicked.connect(self.export_waste_data)

    def add_waste_row(self):
        self.waste_table_manager.add_row()
        row = self.waste_table.rowCount() - 1
        self.setup_waste_row_with_defaults(row)

    def setup_waste_row_with_defaults(self, row):
        today = QDate.currentDate()
        waste_type = self.waste_type.currentText()
        volume = self.cutting_volume.value()
        ph = self.waste_ph.value()
        disposal_method = self.disposal_method.currentText()
        remarks = self.waste_remarks.toPlainText() or "Daily record"
        full_remarks = f"{remarks} | TSS: {self.turbidity.text()} | Hardness: {self.hardness.text()} | Oil: {self.oil_content.value()}ppm"
        values = [
            today.toString("yyyy-MM-dd"),
            waste_type,
            f"{volume:.1f}",
            f"{ph:.1f}",
            disposal_method,
            full_remarks
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col in [2, 3]:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.waste_table.setItem(row, col, item)

    def remove_waste_row(self):
        self.waste_table_manager.delete_row()

    def calculate_waste_totals(self):
        total_volume = 0
        volume_by_type = {}
        volume_by_method = {}
        ph_values = []
        for row in range(self.waste_table.rowCount()):
            type_item = self.waste_table.item(row, 1)
            volume_item = self.waste_table.item(row, 2)
            ph_item = self.waste_table.item(row, 3)
            method_item = self.waste_table.item(row, 4)
            if volume_item:
                try:
                    vol = float(volume_item.text())
                    total_volume += vol
                    wt = type_item.text() if type_item else ""
                    wm = method_item.text() if method_item else ""
                    volume_by_type[wt] = volume_by_type.get(wt,0) + vol
                    volume_by_method[wm] = volume_by_method.get(wm,0) + vol
                    if ph_item:
                        ph_values.append(float(ph_item.text()))
                except: pass
        avg_ph = sum(ph_values)/len(ph_values) if ph_values else 7.0
        report = f"📊 Waste Management Report\n\nTotal Volume: {total_volume:.1f} BBL\nAvg pH: {avg_ph:.1f}\nRecords: {self.waste_table.rowCount()}\n"
        if volume_by_type:
            report += "\nBy Type:\n" + "\n".join(f"  {k}: {v:.1f} BBL" for k,v in volume_by_type.items())
        if volume_by_method:
            report += "\nBy Method:\n" + "\n".join(f"  {k}: {v:.1f} BBL" for k,v in volume_by_method.items())
        QMessageBox.information(self, "Waste Report", report)

    def save_current_waste_data(self):
        self.add_waste_row()
        self.clear_waste_form()
        self.parent.show_success("Current waste data saved to history")

    def clear_waste_form(self):
        self.recycled_volume.setValue(0)
        self.waste_ph.setValue(7.0)
        self.turbidity.clear()
        self.hardness.clear()
        self.cutting_volume.setValue(0)
        self.oil_content.setValue(0)
        self.waste_type.setCurrentIndex(0)
        self.disposal_method.setCurrentIndex(0)
        self.waste_remarks.clear()

    def export_waste_data(self):
        export_manager = ExportManager(self)
        export_manager.export_table_with_dialog(self.waste_table, "waste_data")

    def save_to_database(self, well_id, report_id=None):
        if not self.db:
            return False
        try:
            waste_history = []
            for row in range(self.waste_table.rowCount()):
                row_data = {}
                for col in range(self.waste_table.columnCount()):
                    header = self.waste_table.horizontalHeaderItem(col).text()
                    item = self.waste_table.item(row, col)
                    row_data[header] = item.text() if item else ""
                waste_history.append(row_data)

            report_data = {
                'well_id': well_id,
                'report_id': report_id,
                'report_date': date.today(),
                'report_type': 'Daily',
                'recycled_volume': self.recycled_volume.value(),
                'waste_ph': self.waste_ph.value(),
                'turbidity': self.turbidity.text(),
                'hardness': self.hardness.text(),
                'cutting_volume': self.cutting_volume.value(),
                'oil_content': self.oil_content.value(),
                'waste_type': self.waste_type.currentText(),
                'disposal_method': self.disposal_method.currentText(),
                'waste_history_json': waste_history
            }
            record_id = self.db.save_safety_report(report_data)
            if record_id:
                for waste in waste_history:
                    try:
                        vol = float(waste.get('Volume (BBL)', '0'))
                        ph = float(waste.get('pH', '7.0'))
                    except: vol, ph = 0, 7.0
                    self.db.save_waste_record({
                        'well_id': well_id,
                        'safety_report_id': record_id,
                        'record_date': date.today(),
                        'waste_type': waste.get('Type', ''),
                        'volume': vol,
                        'ph': ph,
                        'disposal_method': waste.get('Disposal Method', ''),
                        'remarks': waste.get('Remarks', '')
                    })
                return True
        except Exception as e:
            logger.error(f"Error saving waste data: {e}")
        return False

    def load_from_database(self, well_id, report_id=None):
        if not self.db:
            return False
        try:
            report_data = self.db.get_safety_report(well_id, report_id=report_id)
            if report_data:
                self.recycled_volume.setValue(report_data.get('recycled_volume', 0))
                self.waste_ph.setValue(report_data.get('waste_ph', 7.0))
                self.turbidity.setText(report_data.get('turbidity', ''))
                self.hardness.setText(report_data.get('hardness', ''))
                self.cutting_volume.setValue(report_data.get('cutting_volume', 0))
                self.oil_content.setValue(report_data.get('oil_content', 0))
                idx = self.waste_type.findText(report_data.get('waste_type', ''))
                if idx >= 0: self.waste_type.setCurrentIndex(idx)
                idx = self.disposal_method.findText(report_data.get('disposal_method', ''))
                if idx >= 0: self.disposal_method.setCurrentIndex(idx)
                waste_history = report_data.get('waste_history_json', [])
                self.waste_table.setRowCount(0)
                for w in waste_history:
                    self.waste_table_manager.add_row()
                    row = self.waste_table.rowCount() - 1
                    # اصلاح این بخش:
                    for col in range(self.waste_table.columnCount()):
                        key = self.waste_table.horizontalHeaderItem(col).text()
                        self.waste_table.setItem(row, col, QTableWidgetItem(str(w.get(key, ''))))
                    # end for
                return True
        except Exception as e:
            logger.error(f"Error loading waste data: {e}")
        return False


# ==================== Safety Widget Main Class ====================
class SafetyWidget(DrillTabBase):
    """Main Safety Widget with Tabs"""

    def __init__(self, db_manager=None, parent=None):
        super().__init__("SafetyWidget", db_manager, parent)
        self.current_well_id = None
        self.current_report_id = None
        self.tabs = {}
        self.init_ui()

        setup_widget_with_managers(
            self, "SafetyWidget",
            enable_autosave=True,
            autosave_interval=5,
            setup_shortcuts=True
        )

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        self.tab_widget = QTabWidget()
        self.safety_bop_tab = SafetyBOPTab(self)
        self.waste_tab = WasteManagementTab(self)

        self.tab_widget.addTab(self.safety_bop_tab, "🛡️ Safety & BOP")
        self.tab_widget.addTab(self.waste_tab, "🗑️ Waste Management")

        self.tabs['safety_bop'] = self.safety_bop_tab
        self.tabs['waste'] = self.waste_tab

        main_layout.addWidget(self.tab_widget)

    def on_well_changed(self, well_id, well_data):
        self.current_well_id = well_id
        self.safety_bop_tab.current_well_id = well_id
        self.waste_tab.current_well_id = well_id
        self.load_data()

    def on_report_changed(self, report_id, report_info):
        self.current_report_id = report_id
        self.safety_bop_tab.current_report_id = report_id
        self.waste_tab.current_report_id = report_id
        self.load_data()

    def load_data(self):
        if not self.current_well_id:
            return
        self.safety_bop_tab.load_from_database(self.current_well_id, self.current_report_id)
        self.waste_tab.load_from_database(self.current_well_id, self.current_report_id)

    def save_data(self):
        if not self.current_well_id:
            self.show_error("No well selected")
            return False
        success_safety = self.safety_bop_tab.save_to_database(self.current_well_id, self.current_report_id)
        success_waste = self.waste_tab.save_to_database(self.current_well_id, self.current_report_id)
        if success_safety or success_waste:
            self.show_success("Safety data saved")
            return True
        self.show_error("Failed to save safety data")
        return False

    def refresh(self):
        self.load_data()