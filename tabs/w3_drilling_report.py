"""
Drilling Report - کلاس اصلی یکپارچه برای تمام تب‌های گزارش حفاری (بازنویسی کامل)
"""

import logging
import json
from datetime import datetime, date
from typing import Dict, List, Optional, Any

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
import os
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtSvg import QSvgGenerator

from core.database import DatabaseManager
from core.managers import (
    StatusBarManager,
    AutoSaveManager,
    ShortcutManager,
    TableButtonManager,
    ExportManager,
    DrillingManager,
)
from core.base_tab import DrillTabBase
from core.selection_manager import SelectionManager

logger = logging.getLogger(__name__)

import matplotlib
try:
    import matplotlib
    _current_backend = matplotlib.get_backend()
    if _current_backend.lower() in ('agg', ''):
        matplotlib.use('Qt5Agg')
except Exception:
    pass

import matplotlib.pyplot as plt

try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    MATPLOTLIB_QT_OK = True
except ImportError:
    try:
        from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
        MATPLOTLIB_QT_OK = False
    except ImportError:
        FigureCanvas = None
        MATPLOTLIB_QT_OK = False
        

# ==================== DrillingReport (کلاس اصلی) ====================
class DrillingReportWidget(DrillTabBase):
    """کلاس اصلی گزارش حفاری"""

    def __init__(self, db_manager=None, parent=None):
        super().__init__("DrillingReportWidget", db_manager, parent)
        self.current_well = None
        self.current_report_id = None
        self.current_data = {}

        self.status_manager = StatusBarManager()
        self.drilling_manager = DrillingManager()

        self.drilling_tab = DrillingParametersTab(self.db, self)
        self.mud_tab = MudReportTab(self.db, self)

        self.init_ui()
        self.setup_connections()
        self.register_tabs_with_managers()
        logger.info("DrillingReport initialized")

    def init_ui(self):
        layout = QVBoxLayout(self)

        toolbar = QToolBar()
        toolbar.setIconSize(QSize(24, 24))

        save_btn = QAction("💾 Save All", self)
        save_btn.triggered.connect(self.save_all_tabs)
        toolbar.addAction(save_btn)

        load_btn = QAction("📂 Load All", self)
        load_btn.triggered.connect(self.load_all_tabs)
        toolbar.addAction(load_btn)

        toolbar.addSeparator()

        refresh_btn = QAction("🔄 Refresh", self)
        refresh_btn.triggered.connect(self.refresh_all_tabs)
        toolbar.addAction(refresh_btn)

        toolbar.addSeparator()

        self.current_well_label = QLabel("No well selected")
        self.current_well_label.setStyleSheet(
            "padding: 5px; font-weight: bold; color: #0078d4;"
        )
        toolbar.addWidget(self.current_well_label)

        layout.addWidget(toolbar)

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(
            self.drilling_tab, "⚙️ Drilling Parameters"
        )
        self.tab_widget.addTab(self.mud_tab, "🧪 Mud Report")
        layout.addWidget(self.tab_widget)

        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Ready")
        layout.addWidget(self.status_bar)

    def register_tabs_with_managers(self):
        try:
            self.status_manager.register_widget(
                "DrillingReport_Main", self
            )
            self.status_manager.register_widget(
                "DrillingParametersTab", self.drilling_tab
            )
            self.status_manager.register_widget(
                "MudReportTab", self.mud_tab
            )
            logger.info("✅ All tabs registered")
        except Exception as e:
            logger.error(f"Error registering tabs: {e}")
            
    def setup_connections(self):
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

    def on_tab_changed(self, index):
        tab_name = self.tab_widget.tabText(index)
        self.status_bar.showMessage(f"Active tab: {tab_name}")

    def on_well_changed(self, well_id, well_data):
        well_name = (
            well_data.get("name", str(well_id)) if well_data else str(well_id)
        )
        self.set_current_well(well_id, well_name)

    def on_report_changed(self, report_id, report_info):
        self.set_current_report(report_id)

    def set_current_well(self, well_id, well_name=None):
        self.current_well = well_id
        label = (
            f"Well: {well_name} (ID: {well_id})"
            if well_name else f"Well ID: {well_id}"
        )
        self.current_well_label.setText(label)
        for tab in [self.drilling_tab, self.mud_tab]:
            if hasattr(tab, 'current_well'):
                tab.current_well = well_id
                
    def set_current_report(self, report_id):
        self.current_report_id = report_id
        if not report_id:
            return
        for tab, method in [
            (self.drilling_tab, 'load_for_report'),
            (self.mud_tab, 'load_for_report'),
        ]:
            if hasattr(tab, method):
                try:
                    getattr(tab, method)(report_id)
                except Exception as e:
                    logger.error(f"Error: {e}")

    def load_all_tabs(self):
        if not self.current_well:
            return False
        self.drilling_tab.load_data()
        self.mud_tab.load_data()
        return True

    def refresh_all_tabs(self):
        for tab in [self.drilling_tab, self.mud_tab]:
            if hasattr(tab, 'refresh'):
                tab.refresh()

    def clear_all_tabs(self):
        reply = QMessageBox.question(
            self, "Clear All", "Clear all tabs?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for tab in [self.drilling_tab, self.mud_tab]:
                if hasattr(tab, 'clear_form'):
                    tab.clear_form()

    def validate_all_tabs(self):
        errors = []
        if hasattr(self.drilling_tab, 'validate_form'):
            errs = self.drilling_tab.validate_form()
            if errs:
                errors.extend(errs)
        return len(errors) == 0

    def save_data(self):
        return self.save_all_tabs()

    def refresh(self):
        self.refresh_all_tabs()
        
    def save_all_tabs(self):
        if not self.current_report_id:
            self.status_manager.show_error(
                "DrillingReport_Main", "No report selected"
            )
            return False

        try:
            results = {
                "drilling": self.drilling_tab.save_data_for_report(
                    self.current_report_id
                ),
                "mud": self.mud_tab.save_data_for_report(
                    self.current_report_id
                ),
            }
            success_count = sum(1 for r in results.values() if r)
            if success_count > 0:
                self.status_manager.show_success(
                    "DrillingReport_Main",
                    f"Saved {success_count}/{len(results)} tabs"
                )
                return True
            else:
                self.status_manager.show_error(
                    "DrillingReport_Main", "Failed to save tabs"
                )
                return False
        except Exception as e:
            logger.error(f"Save all error: {e}")
            self.status_manager.show_error(
                "DrillingReport_Main", f"Save error: {str(e)}"
            )
            return False

    def export_complete_report(self):
        """اکسپورت کامل گزارش حفاری به PDF یا HTML"""
        if not self.current_report_id:
            QMessageBox.warning(self, "Warning", "Please select a daily report first to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Complete Drilling Report",
            f"Drilling_Report_{self.current_report_id}.pdf",
            "PDF Files (*.pdf);;HTML Files (*.html)"
        )
        if not file_path:
            return

        try:
            success = False
            ext = os.path.splitext(file_path)[1].lower()
            if ext == ".pdf":
                try:
                    from core.ddr_pdf_export import DDRPDFExporter
                    exporter = DDRPDFExporter(self.db_manager)
                    success = exporter.export(self.current_report_id, file_path)
                except Exception as pdf_err:
                    logger.warning(f"DDRPDFExporter failed, falling back to DDRReportEngine: {pdf_err}")
            
            if not success:
                from core.report_engine import DDRReportEngine
                fmt = "html" if ext == ".html" else "pdf"
                engine = DDRReportEngine(self.db_manager)
                success = engine.generate(self.current_report_id, file_path, format=fmt)

            if success:
                self.status_manager.show_success("DrillingReport_Main", f"Report exported successfully: {os.path.basename(file_path)}")
                QMessageBox.information(self, "Export Success", f"Report successfully saved to:\n{file_path}")
            else:
                self.status_manager.show_error("DrillingReport_Main", "Failed to export report.")
                QMessageBox.warning(self, "Export Error", "Could not export report. Check logs for details.")
        except Exception as e:
            logger.error(f"Error exporting drilling report: {e}")
            self.status_manager.show_error("DrillingReport_Main", f"Export error: {str(e)}")

    def show_help(self):
        QMessageBox.information(
            self, "Help",
            "Drilling Report Module\n\n"
            "• ⚙️ Drilling Parameters: Bit info, WOB, RPM, SPP\n"
            "• 🧪 Mud Report: Mud properties and chemicals\n"
            "• 🏗️ Cement Report: Cement job details\n"
            "• 📏 Casing Tally: Joint-by-joint tally\n"
            "• 🔩 Casing Report: Casing design\n\n"
            "Select a Daily Report first, then fill in data."
        )

# ==================== CLASS 1: DrillingParametersTab ====================
class DrillingParametersTab(QWidget):
    """تب پارامترهای حفاری"""

    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.parent = parent
        self.current_well = None
        self.current_data = {}

        if parent and hasattr(parent, "drilling_manager"):
            self.drilling_manager = parent.drilling_manager
        else:
            self.drilling_manager = DrillingManager()

        self.init_ui()
        self.setup_connections()
        logger.info("DrillingParametersTab initialized")

    def init_ui(self):
        layout = QVBoxLayout(self)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)

        # ============ Bit Information ============
        bit_group = QGroupBox("📌 Bit Information")
        bit_layout = QGridLayout()

        bit_layout.addWidget(QLabel("Bit No:"), 0, 0)
        self.bit_no = QLineEdit()
        self.bit_no.setPlaceholderText("Enter bit number")
        bit_layout.addWidget(self.bit_no, 0, 1)

        bit_layout.addWidget(QLabel("Rerun No:"), 0, 2)
        self.bit_rerun = QSpinBox()
        self.bit_rerun.setRange(1, 100)
        self.bit_rerun.setValue(1)
        bit_layout.addWidget(self.bit_rerun, 0, 3)

        bit_layout.addWidget(QLabel("Bit Size (in):"), 1, 0)
        self.bit_size = QDoubleSpinBox()
        self.bit_size.setRange(0, 30)
        self.bit_size.setDecimals(3)
        self.bit_size.setValue(8.5)
        bit_layout.addWidget(self.bit_size, 1, 1)

        bit_layout.addWidget(QLabel("Bit Type:"), 1, 2)
        self.bit_type = QComboBox()
        self.bit_type.addItems(["PDC", "Tricone", "Impregnated", "Diamond"])
        bit_layout.addWidget(self.bit_type, 1, 3)

        bit_layout.addWidget(QLabel("Manufacturer:"), 2, 0)
        self.bit_manufacturer = QLineEdit()
        self.bit_manufacturer.setPlaceholderText("e.g., Schlumberger")
        bit_layout.addWidget(self.bit_manufacturer, 2, 1)

        bit_layout.addWidget(QLabel("IADC Code:"), 2, 2)
        self.iadc_code = QLineEdit()
        self.iadc_code.setPlaceholderText("e.g., M333")
        bit_layout.addWidget(self.iadc_code, 2, 3)

        bit_group.setLayout(bit_layout)
        content_layout.addWidget(bit_group)

        # ============ Nozzle Information ============
        nozzle_group = QGroupBox("🌀 Nozzle Information")
        nozzle_layout = QVBoxLayout()

        # ایجاد ScrollArea برای جدول نازل‌ها
        nozzle_scroll = QScrollArea()
        nozzle_scroll.setWidgetResizable(True)
        nozzle_scroll.setMinimumHeight(150)
        nozzle_scroll.setMaximumHeight(250)

        self.nozzle_table = QTableWidget(0, 3)
        self.nozzle_table.setHorizontalHeaderLabels(["No.", "Size (1/32 in)", "Qty"])
        self.nozzle_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.nozzle_table.setMinimumWidth(350)
        self.nozzle_table.setColumnWidth(0, 40)   # No.
        self.nozzle_table.setColumnWidth(1, 100)  # Size
        self.nozzle_table.setColumnWidth(2, 60)   # Qty

        nozzle_scroll.setWidget(self.nozzle_table)
        nozzle_layout.addWidget(nozzle_scroll)

        nozzle_btn_layout = QHBoxLayout()
        add_nozzle_btn = QPushButton("➕ Add Nozzle")
        add_nozzle_btn.clicked.connect(self.add_nozzle_row)
        remove_nozzle_btn = QPushButton("➖ Remove")
        remove_nozzle_btn.clicked.connect(self.remove_nozzle_row)

        nozzle_btn_layout.addWidget(add_nozzle_btn)
        nozzle_btn_layout.addWidget(remove_nozzle_btn)
        nozzle_btn_layout.addStretch()
        nozzle_layout.addLayout(nozzle_btn_layout)

        tfa_layout = QHBoxLayout()
        tfa_layout.addWidget(QLabel("Total Flow Area (TFA):"))
        self.tfa_value = QDoubleSpinBox()
        self.tfa_value.setReadOnly(True)
        self.tfa_value.setDecimals(3)
        self.tfa_value.setSuffix(" in²")
        tfa_layout.addWidget(self.tfa_value)
        tfa_layout.addStretch()
        nozzle_layout.addLayout(tfa_layout)

        nozzle_group.setLayout(nozzle_layout)
        content_layout.addWidget(nozzle_group)

        # ============ Depth Information ============
        depth_group = QGroupBox("📏 Depth Information")
        depth_layout = QGridLayout()

        depth_layout.addWidget(QLabel("Depth In (m):"), 0, 0)
        self.depth_in = QDoubleSpinBox()
        self.depth_in.setRange(0, 20000)
        self.depth_in.setDecimals(2)
        depth_layout.addWidget(self.depth_in, 0, 1)

        depth_layout.addWidget(QLabel("Depth Out (m):"), 0, 2)
        self.depth_out = QDoubleSpinBox()
        self.depth_out.setRange(0, 20000)
        self.depth_out.setDecimals(2)
        depth_layout.addWidget(self.depth_out, 0, 3)

        depth_layout.addWidget(QLabel("Bit Drilled (m):"), 1, 0)
        self.bit_drilled = QDoubleSpinBox()
        self.bit_drilled.setReadOnly(True)
        self.bit_drilled.setDecimals(2)
        depth_layout.addWidget(self.bit_drilled, 1, 1)

        depth_layout.addWidget(QLabel("Cumulative (m):"), 1, 2)
        self.cum_drilled = QDoubleSpinBox()
        self.cum_drilled.setRange(0, 50000)
        self.cum_drilled.setDecimals(2)
        depth_layout.addWidget(self.cum_drilled, 1, 3)

        depth_layout.addWidget(QLabel("Hours on Bottom:"), 2, 0)
        self.hours_on_bottom = QDoubleSpinBox()
        self.hours_on_bottom.setRange(0, 1000)
        self.hours_on_bottom.setDecimals(1)
        depth_layout.addWidget(self.hours_on_bottom, 2, 1)

        depth_layout.addWidget(QLabel("Cumulative Hours:"), 2, 2)
        self.cum_hours = QDoubleSpinBox()
        self.cum_hours.setRange(0, 10000)
        self.cum_hours.setDecimals(1)
        depth_layout.addWidget(self.cum_hours, 2, 3)

        depth_group.setLayout(depth_layout)
        content_layout.addWidget(depth_group)

        # ============ Drilling Parameters ============
        params_group = QGroupBox("⚙️ Drilling Parameters")
        params_layout = QGridLayout()

        params_layout.addWidget(QLabel("WOB Min (klb):"), 0, 0)
        self.wob_min = QDoubleSpinBox()
        self.wob_min.setRange(0, 100)
        self.wob_min.setDecimals(1)
        params_layout.addWidget(self.wob_min, 0, 1)

        params_layout.addWidget(QLabel("WOB Max (klb):"), 0, 2)
        self.wob_max = QDoubleSpinBox()
        self.wob_max.setRange(0, 100)
        self.wob_max.setDecimals(1)
        params_layout.addWidget(self.wob_max, 0, 3)

        params_layout.addWidget(QLabel("RPM Min:"), 1, 0)
        self.rpm_min = QDoubleSpinBox()
        self.rpm_min.setRange(0, 500)
        self.rpm_min.setDecimals(0)
        params_layout.addWidget(self.rpm_min, 1, 1)

        params_layout.addWidget(QLabel("RPM Max:"), 1, 2)
        self.rpm_max = QDoubleSpinBox()
        self.rpm_max.setRange(0, 500)
        self.rpm_max.setDecimals(0)
        params_layout.addWidget(self.rpm_max, 1, 3)

        params_layout.addWidget(QLabel("Torque Min (klb.ft):"), 2, 0)
        self.torque_min = QDoubleSpinBox()
        self.torque_min.setRange(0, 100)
        self.torque_min.setDecimals(1)
        params_layout.addWidget(self.torque_min, 2, 1)

        params_layout.addWidget(QLabel("Torque Max (klb.ft):"), 2, 2)
        self.torque_max = QDoubleSpinBox()
        self.torque_max.setRange(0, 100)
        self.torque_max.setDecimals(1)
        params_layout.addWidget(self.torque_max, 2, 3)

        params_layout.addWidget(QLabel("SPP Min (psi):"), 3, 0)
        self.pump_pressure_min = QDoubleSpinBox()
        self.pump_pressure_min.setRange(0, 5000)
        self.pump_pressure_min.setDecimals(0)
        params_layout.addWidget(self.pump_pressure_min, 3, 1)

        params_layout.addWidget(QLabel("SPP Max (psi):"), 3, 2)
        self.pump_pressure_max = QDoubleSpinBox()
        self.pump_pressure_max.setRange(0, 5000)
        self.pump_pressure_max.setDecimals(0)
        params_layout.addWidget(self.pump_pressure_max, 3, 3)

        params_group.setLayout(params_layout)
        content_layout.addWidget(params_group)

        # ============ Pump Parameters ============
        pump_group = QGroupBox("💧 Pump Parameters")
        pump_layout = QGridLayout()

        pump_layout.addWidget(QLabel("Flow Rate Min (gpm):"), 0, 0)
        self.pump_output_min = QDoubleSpinBox()
        self.pump_output_min.setRange(0, 5000)
        self.pump_output_min.setDecimals(0)
        pump_layout.addWidget(self.pump_output_min, 0, 1)

        pump_layout.addWidget(QLabel("Flow Rate Max (gpm):"), 0, 2)
        self.pump_output_max = QDoubleSpinBox()
        self.pump_output_max.setRange(0, 5000)
        self.pump_output_max.setDecimals(0)
        pump_layout.addWidget(self.pump_output_max, 0, 3)

        pump_layout.addWidget(QLabel("Pump 1 SPM:"), 1, 0)
        self.pump1_spm = QDoubleSpinBox()
        self.pump1_spm.setRange(0, 200)
        self.pump1_spm.setDecimals(1)
        pump_layout.addWidget(self.pump1_spm, 1, 1)

        pump_layout.addWidget(QLabel("Pump 1 SPP (psi):"), 1, 2)
        self.pump1_spp = QDoubleSpinBox()
        self.pump1_spp.setRange(0, 5000)
        self.pump1_spp.setDecimals(0)
        pump_layout.addWidget(self.pump1_spp, 1, 3)

        pump_layout.addWidget(QLabel("Pump 2 SPM:"), 2, 0)
        self.pump2_spm = QDoubleSpinBox()
        self.pump2_spm.setRange(0, 200)
        self.pump2_spm.setDecimals(1)
        pump_layout.addWidget(self.pump2_spm, 2, 1)

        pump_layout.addWidget(QLabel("Pump 2 SPP (psi):"), 2, 2)
        self.pump2_spp = QDoubleSpinBox()
        self.pump2_spp.setRange(0, 5000)
        self.pump2_spp.setDecimals(0)
        pump_layout.addWidget(self.pump2_spp, 2, 3)
        # Pump 3
        pump_layout.addWidget(QLabel("Pump 3 SPM:"), 3, 0)
        self.pump3_spm = QDoubleSpinBox()
        self.pump3_spm.setRange(0, 200)
        self.pump3_spm.setDecimals(1)
        pump_layout.addWidget(self.pump3_spm, 3, 1)

        pump_layout.addWidget(QLabel("Pump 3 SPP (psi):"), 3, 2)
        self.pump3_spp = QDoubleSpinBox()
        self.pump3_spp.setRange(0, 5000)
        self.pump3_spp.setDecimals(0)
        pump_layout.addWidget(self.pump3_spp, 3, 3)

        pump_group.setLayout(pump_layout)
        content_layout.addWidget(pump_group)

        # ============ Calculations ============
        calc_group = QGroupBox("🧮 Calculations")
        calc_layout = QGridLayout()

        calc_layout.addWidget(QLabel("Avg ROP (m/hr):"), 0, 0)
        self.avg_rop = QDoubleSpinBox()
        self.avg_rop.setReadOnly(True)
        self.avg_rop.setDecimals(2)
        calc_layout.addWidget(self.avg_rop, 0, 1)

        calc_layout.addWidget(QLabel("HSI:"), 0, 2)
        self.hsi = QDoubleSpinBox()
        self.hsi.setReadOnly(True)
        self.hsi.setDecimals(2)
        calc_layout.addWidget(self.hsi, 0, 3)

        calc_layout.addWidget(QLabel("Annular Velocity (ft/min):"), 1, 0)
        self.annular_velocity = QDoubleSpinBox()
        self.annular_velocity.setReadOnly(True)
        self.annular_velocity.setDecimals(1)
        calc_layout.addWidget(self.annular_velocity, 1, 1)

        calc_layout.addWidget(QLabel("Bit Revolution (k.rev):"), 1, 2)
        self.bit_revolution = QDoubleSpinBox()
        self.bit_revolution.setReadOnly(True)
        self.bit_revolution.setDecimals(0)
        calc_layout.addWidget(self.bit_revolution, 1, 3)

        calc_group.setLayout(calc_layout)
        content_layout.addWidget(calc_group)

        # ============ Action Buttons ============
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.clicked.connect(self.save_data)
        self.load_btn = QPushButton("📂 Load")
        self.load_btn.clicked.connect(self.load_data)

        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.load_btn)
        btn_layout.addStretch()

        content_layout.addLayout(btn_layout)
        content_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)

        # اضافه کردن ردیف‌های پیش‌فرض به جدول نازل‌ها
        self.add_nozzle_row(16, 1)
        self.add_nozzle_row(16, 1)
        self.add_nozzle_row(14, 1)

    def setup_connections(self):
        self.depth_in.valueChanged.connect(self.calculate_bit_drilled)
        self.depth_out.valueChanged.connect(self.calculate_bit_drilled)
        self.hours_on_bottom.valueChanged.connect(self.calculate_rop)
        self.pump_pressure_min.valueChanged.connect(self.calculate_hsi)
        self.pump_pressure_max.valueChanged.connect(self.calculate_hsi)
        self.pump_output_min.valueChanged.connect(self.calculate_hsi)
        self.pump_output_max.valueChanged.connect(self.calculate_hsi)
        self.bit_size.valueChanged.connect(self.calculate_hsi)
        self.rpm_min.valueChanged.connect(self.calculate_bit_revolution)
        self.rpm_max.valueChanged.connect(self.calculate_bit_revolution)
        self.nozzle_table.cellChanged.connect(self.calculate_tfa)
        self.pump_output_min.valueChanged.connect(self.calculate_annular_velocity)
        self.pump_output_max.valueChanged.connect(self.calculate_annular_velocity)
        self.bit_size.valueChanged.connect(self.calculate_annular_velocity)
        self.cum_drilled.valueChanged.connect(self.update_cumulative_info)
        self.bit_type.currentTextChanged.connect(self.on_bit_type_changed)
        self.iadc_code.textChanged.connect(self.on_iadc_code_changed)

    # ============ Nozzle Methods ============
    def add_nozzle_row(self, size=16, quantity=1):
        row = self.nozzle_table.rowCount()
        self.nozzle_table.insertRow(row)
        no_item = QTableWidgetItem(str(row + 1))
        no_item.setTextAlignment(Qt.AlignCenter)
        no_item.setFlags(Qt.ItemIsEnabled)
        self.nozzle_table.setItem(row, 0, no_item)
        size_spin = QSpinBox()
        size_spin.setRange(1, 100)
        size_spin.setValue(size)
        size_spin.setSuffix("/32")
        size_spin.valueChanged.connect(self.calculate_tfa)
        self.nozzle_table.setCellWidget(row, 1, size_spin)
        qty_spin = QSpinBox()
        qty_spin.setRange(1, 10)
        qty_spin.setValue(quantity)
        qty_spin.valueChanged.connect(self.calculate_tfa)
        self.nozzle_table.setCellWidget(row, 2, qty_spin)

    def remove_nozzle_row(self):
        current_row = self.nozzle_table.currentRow()
        if current_row >= 0:
            self.nozzle_table.removeRow(current_row)
            self.calculate_tfa()
            for row in range(self.nozzle_table.rowCount()):
                item = QTableWidgetItem(str(row + 1))
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(Qt.ItemIsEnabled)
                self.nozzle_table.setItem(row, 0, item)

    def calculate_tfa(self):
        try:
            nozzles_data = []
            for row in range(self.nozzle_table.rowCount()):
                size_widget = self.nozzle_table.cellWidget(row, 1)
                qty_widget = self.nozzle_table.cellWidget(row, 2)
                if size_widget and qty_widget:
                    nozzles_data.append({
                        'size_32nd': size_widget.value(),
                        'quantity': qty_widget.value()
                    })
            tfa = DrillingManager.calculate_tfa(nozzles_data)
            self.tfa_value.setValue(tfa)
        except Exception as e:
            logger.error(f"Error calculating TFA: {e}")

    # ============ Calculation Methods ============
    def calculate_bit_drilled(self):
        try:
            bit_drilled = self.depth_out.value() - self.depth_in.value()
            if bit_drilled < 0:
                bit_drilled = 0
            self.bit_drilled.setValue(round(bit_drilled, 2))
            self.calculate_rop()
        except Exception as e:
            logger.error(f"Error calculating bit drilled: {e}")

    def calculate_rop(self):
        try:
            depth_in = self.depth_in.value()
            depth_out = self.depth_out.value()
            hours = self.hours_on_bottom.value()
            rop = DrillingManager.calculate_rop(depth_in, depth_out, hours)
            self.avg_rop.setValue(rop)
        except Exception as e:
            logger.error(f"Error calculating ROP: {e}")

    def calculate_hsi(self):
        try:
            pump_pressure = (self.pump_pressure_min.value() + self.pump_pressure_max.value()) / 2
            flow_rate = (self.pump_output_min.value() + self.pump_output_max.value()) / 2
            bit_size = self.bit_size.value()
            hsi_val = DrillingManager.calculate_hsi(pump_pressure, flow_rate, bit_size)
            self.hsi.setValue(hsi_val)
        except Exception as e:
            logger.error(f"Error calculating HSI: {e}")

    def calculate_all(self):
        try:
            self.calculate_tfa()
            self.calculate_bit_drilled()
            self.calculate_rop()
            self.calculate_hsi()
            self.calculate_annular_velocity()
            self.calculate_bit_revolution()
            logger.info("All calculations completed")
        except Exception as e:
            logger.error(f"Error in calculate_all: {e}")

    def calculate_annular_velocity(self):
        try:
            flow_rate = (self.pump_output_min.value() + self.pump_output_max.value()) / 2
            bit_size = self.bit_size.value()

            pipe_od = 5.0
            if self.db_manager and hasattr(self, 'parent') and self.parent and getattr(self.parent, 'current_well_id', None):
                try:
                    session = self.db_manager.create_session()
                    from core.database import DownholeEquipment
                    eq = session.query(DownholeEquipment).filter(DownholeEquipment.well_id == self.parent.current_well_id).first()
                    if eq and eq.equipment_data_json:
                        items = eq.equipment_data_json if isinstance(eq.equipment_data_json, list) else [eq.equipment_data_json]
                        for it in items:
                            if isinstance(it, dict) and "pipe" in str(it.get("type", "")).lower():
                                pipe_od = float(it.get("od_inch", 5.0) or 5.0)
                                break
                    session.close()
                except Exception as db_err:
                    logger.debug(f"Could not load drill pipe OD from db: {db_err}")

            if bit_size > pipe_od > 0:
                result = DrillingManager.calculate_annular_velocity(
                    flow_rate, bit_size, pipe_od
                )
                if isinstance(result, dict):
                    self.annular_velocity.setValue(result.get("ft_min", 0))
                else:
                    self.annular_velocity.setValue(result)
        except Exception as e:
            logger.error(f"Error calculating annular velocity: {e}")

    def calculate_bit_revolution(self):
        try:
            rpm_avg = (self.rpm_min.value() + self.rpm_max.value()) / 2
            hours = self.hours_on_bottom.value()
            rev = DrillingManager.calculate_bit_revolution(rpm_avg, hours)
            self.bit_revolution.setValue(rev)
        except Exception as e:
            logger.error(f"Error calculating bit revolution: {e}")

    def on_bit_type_changed(self, text):
        logger.debug(f"Bit type changed to: {text}")

    def on_iadc_code_changed(self, text):
        logger.debug(f"IADC code changed to: {text}")

    def update_cumulative_info(self):
        cum_drilled = self.cum_drilled.value()
        cum_hours = self.cum_hours.value()
        if cum_hours > 0:
            cum_rop = cum_drilled / cum_hours
            logger.debug(f"Cumulative ROP: {cum_rop:.2f} m/hr, Total Drilled: {cum_drilled} m, Total Hours: {cum_hours} h")
        else:
            logger.debug("Cumulative hours is zero, cannot calculate cumulative ROP.")
            
    # ============ Data Methods ============
    def set_current_well(self, well_id):
        self.current_well = well_id

    def load_for_report(self, report_id):
        if not self.db_manager:
            return
        data = self.db_manager.get_drilling_parameters(report_id=report_id)
        if data:
            self.load_from_dict(data)
        else:
            self.clear_form()

    def save_data_for_report(self, report_id):
        if not self.current_well:
            return False
        drilling_data = self.collect_data()
        drilling_data["report_id"] = report_id
        drilling_data["well_id"] = self.current_well
        drilling_data["report_date"] = date.today()
        result = self.db_manager.save_drilling_parameters(drilling_data)
        return result is not None

    def collect_data(self):
        nozzles_data = []
        for row in range(self.nozzle_table.rowCount()):
            size_widget = self.nozzle_table.cellWidget(row, 1)
            qty_widget = self.nozzle_table.cellWidget(row, 2)
            if size_widget and qty_widget:
                nozzles_data.append({
                    "row": row + 1,
                    "size_32nd": size_widget.value(),
                    "quantity": qty_widget.value(),
                    "diameter_inch": size_widget.value() / 32.0,
                })
        return {
            "bit_no": self.bit_no.text(),
            "bit_rerun": self.bit_rerun.value(),
            "bit_size": self.bit_size.value(),
            "bit_type": self.bit_type.currentText(),
            "manufacturer": self.bit_manufacturer.text(),
            "iadc_code": self.iadc_code.text(),
            "nozzles_json": json.dumps(nozzles_data, indent=2),
            "tfa": self.tfa_value.value(),
            "depth_in": self.depth_in.value(),
            "depth_out": self.depth_out.value(),
            "bit_drilled": self.bit_drilled.value(),
            "cum_drilled": self.cum_drilled.value(),
            "hours_on_bottom": self.hours_on_bottom.value(),
            "cum_hours": self.cum_hours.value(),
            "wob_min": self.wob_min.value(),
            "wob_max": self.wob_max.value(),
            "rpm_min": self.rpm_min.value(),
            "rpm_max": self.rpm_max.value(),
            "torque_min": self.torque_min.value(),
            "torque_max": self.torque_max.value(),
            "pump_pressure_min": self.pump_pressure_min.value(),
            "pump_pressure_max": self.pump_pressure_max.value(),
            "pump_output_min": self.pump_output_min.value(),
            "pump_output_max": self.pump_output_max.value(),
            "pump1_spm": self.pump1_spm.value(),
            "pump1_spp": self.pump1_spp.value(),
            "pump2_spm": self.pump2_spm.value(),
            "pump2_spp": self.pump2_spp.value(),
            "avg_rop": self.avg_rop.value(),
            "hsi": self.hsi.value(),
            "annular_velocity": self.annular_velocity.value(),
            "bit_revolution": self.bit_revolution.value(),
        }

    def save_data(self):
        if self.parent and hasattr(self.parent, 'current_report_id') and self.parent.current_report_id:
            return self.save_data_for_report(self.parent.current_report_id)
        else:
            QMessageBox.warning(self, "Warning", "No report selected. Please select a Daily Report first.")
            return False

    def load_data(self):
        if self.parent and hasattr(self.parent, 'current_report_id') and self.parent.current_report_id:
            self.load_for_report(self.parent.current_report_id)
            return True
        else:
            logger.debug("DrillingParametersTab: no report selected yet")
            return False
        
    def load_from_dict(self, data: dict):
        def safe_val(key, default=0):
            v = data.get(key)
            if v is None:
                return default
            try:
                return float(v)
            except (ValueError, TypeError):
                return default

        def safe_str(key, default=""):
            v = data.get(key)
            return str(v) if v is not None else default

        self.bit_no.setText(safe_str("bit_no"))
        self.bit_rerun.setValue(int(safe_val("bit_rerun", 1)))
        self.bit_size.setValue(safe_val("bit_size", 0))

        bit_type = data.get("bit_type", "")
        if bit_type:
            index = self.bit_type.findText(str(bit_type))
            if index >= 0:
                self.bit_type.setCurrentIndex(index)

        self.bit_manufacturer.setText(safe_str("manufacturer"))
        self.iadc_code.setText(safe_str("iadc_code"))

        nozzles_json = data.get("nozzles_json")
        if nozzles_json:
            self.nozzle_table.setRowCount(0)
            try:
                nozzles_data = json.loads(nozzles_json) if isinstance(nozzles_json, str) else nozzles_json
                for nozzle in nozzles_data:
                    self.add_nozzle_row(
                        nozzle.get("size_32nd", 16),
                        nozzle.get("quantity", 1)
                    )
            except (json.JSONDecodeError, TypeError):
                pass

        self.tfa_value.setValue(safe_val("tfa"))
        self.depth_in.setValue(safe_val("depth_in"))
        self.depth_out.setValue(safe_val("depth_out"))
        self.bit_drilled.setValue(safe_val("bit_drilled"))
        self.cum_drilled.setValue(safe_val("cum_drilled"))
        self.hours_on_bottom.setValue(safe_val("hours_on_bottom"))
        self.cum_hours.setValue(safe_val("cum_hours"))
        self.wob_min.setValue(safe_val("wob_min"))
        self.wob_max.setValue(safe_val("wob_max"))
        self.rpm_min.setValue(safe_val("rpm_min"))
        self.rpm_max.setValue(safe_val("rpm_max"))
        self.torque_min.setValue(safe_val("torque_min"))
        self.torque_max.setValue(safe_val("torque_max"))
        self.pump_pressure_min.setValue(safe_val("pump_pressure_min"))
        self.pump_pressure_max.setValue(safe_val("pump_pressure_max"))
        self.pump_output_min.setValue(safe_val("pump_output_min"))
        self.pump_output_max.setValue(safe_val("pump_output_max"))
        self.pump1_spm.setValue(safe_val("pump1_spm"))
        self.pump1_spp.setValue(safe_val("pump1_spp"))
        self.pump2_spm.setValue(safe_val("pump2_spm"))
        self.pump2_spp.setValue(safe_val("pump2_spp"))
        self.avg_rop.setValue(safe_val("avg_rop"))
        self.hsi.setValue(safe_val("hsi"))
        self.annular_velocity.setValue(safe_val("annular_velocity"))
        self.bit_revolution.setValue(safe_val("bit_revolution"))
        
    def clear_form(self):
        self.bit_no.clear()
        self.bit_rerun.setValue(1)
        self.bit_size.setValue(8.5)
        self.bit_type.setCurrentIndex(0)
        self.bit_manufacturer.clear()
        self.iadc_code.clear()
        self.nozzle_table.setRowCount(0)
        self.add_nozzle_row(16, 1)
        self.add_nozzle_row(16, 1)
        self.add_nozzle_row(14, 1)
        self.tfa_value.setValue(0)
        self.depth_in.setValue(0)
        self.depth_out.setValue(0)
        self.bit_drilled.setValue(0)
        self.cum_drilled.setValue(0)
        self.hours_on_bottom.setValue(0)
        self.cum_hours.setValue(0)
        self.wob_min.setValue(0)
        self.wob_max.setValue(0)
        self.rpm_min.setValue(0)
        self.rpm_max.setValue(0)
        self.torque_min.setValue(0)
        self.torque_max.setValue(0)
        self.pump_pressure_min.setValue(0)
        self.pump_pressure_max.setValue(0)
        self.pump_output_min.setValue(0)
        self.pump_output_max.setValue(0)
        self.pump1_spm.setValue(0)
        self.pump1_spp.setValue(0)
        self.pump2_spm.setValue(0)
        self.pump2_spp.setValue(0)
        self.avg_rop.setValue(0)
        self.hsi.setValue(0)
        self.annular_velocity.setValue(0)
        self.bit_revolution.setValue(0)

    def validate_form(self):
        """اعتبارسنجی فیلدهای ضروری"""
        errors = []
        if not self.bit_no.text().strip():
            errors.append("Bit No is required")
        if self.depth_out.value() <= self.depth_in.value():
            errors.append("Depth Out must be greater than Depth In")
        return errors

    def refresh(self):
        self.load_data()


# ==================== CLASS 2: MudReportTab ====================
class MudReportTab(QWidget):
    """تب گزارش گل حفاری"""

    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.parent = parent
        self.current_well = None
        self.current_data = {}
        self.init_ui()
        self.setup_connections()
        logger.info("MudReportTab initialized")

    def init_ui(self):
        layout = QVBoxLayout(self)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)

        # ============ Mud Properties ============
        properties_group = QGroupBox("🧪 Mud Properties")
        properties_layout = QGridLayout()

        properties_layout.addWidget(QLabel("Mud Type:"), 0, 0)
        self.mud_type = QComboBox()
        self.mud_type.addItems(["WBM", "OBM", "SOBM", "Pseudo Oil", "Synthetic"])
        properties_layout.addWidget(self.mud_type, 0, 1)

        properties_layout.addWidget(QLabel("Sample Time:"), 0, 2)
        self.sample_time = QTimeEdit()
        self.sample_time.setTime(QTime.currentTime())
        properties_layout.addWidget(self.sample_time, 0, 3)

        properties_layout.addWidget(QLabel("MW (pcf):"), 1, 0)
        self.mw = QDoubleSpinBox()
        self.mw.setRange(0, 200)
        self.mw.setDecimals(1)
        self.mw.setValue(65.0)
        properties_layout.addWidget(self.mw, 1, 1)

        properties_layout.addWidget(QLabel("PV (cp):"), 1, 2)
        self.pv = QDoubleSpinBox()
        self.pv.setRange(0, 200)
        self.pv.setDecimals(1)
        properties_layout.addWidget(self.pv, 1, 3)

        properties_layout.addWidget(QLabel("YP (lb/100ft²):"), 2, 0)
        self.yp = QDoubleSpinBox()
        self.yp.setRange(0, 100)
        self.yp.setDecimals(1)
        properties_layout.addWidget(self.yp, 2, 1)

        properties_layout.addWidget(QLabel("Funnel Viscosity (sec/qt):"), 2, 2)
        self.funnel_vis = QDoubleSpinBox()
        self.funnel_vis.setRange(0, 200)
        self.funnel_vis.setDecimals(1)
        properties_layout.addWidget(self.funnel_vis, 2, 3)

        properties_layout.addWidget(QLabel("Gel 10s:"), 3, 0)
        self.gel_10s = QDoubleSpinBox()
        self.gel_10s.setRange(0, 100)
        self.gel_10s.setDecimals(1)
        properties_layout.addWidget(self.gel_10s, 3, 1)

        properties_layout.addWidget(QLabel("Gel 10m:"), 3, 2)
        self.gel_10m = QDoubleSpinBox()
        self.gel_10m.setRange(0, 100)
        self.gel_10m.setDecimals(1)
        properties_layout.addWidget(self.gel_10m, 3, 3)

        properties_layout.addWidget(QLabel("FL (cc/30min):"), 4, 0)
        self.fl = QDoubleSpinBox()
        self.fl.setRange(0, 50)
        self.fl.setDecimals(1)
        properties_layout.addWidget(self.fl, 4, 1)

        properties_layout.addWidget(QLabel("Cake Thickness (mm):"), 4, 2)
        self.cake_thickness = QDoubleSpinBox()
        self.cake_thickness.setRange(0, 20)
        self.cake_thickness.setDecimals(1)
        properties_layout.addWidget(self.cake_thickness, 4, 3)

        properties_layout.addWidget(QLabel("pH:"), 5, 0)
        self.ph = QDoubleSpinBox()
        self.ph.setRange(0, 14)
        self.ph.setDecimals(1)
        self.ph.setValue(9.5)
        properties_layout.addWidget(self.ph, 5, 1)

        properties_layout.addWidget(QLabel("Temperature (°C):"), 5, 2)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0, 200)
        self.temperature.setDecimals(1)
        self.temperature.setValue(25.0)
        properties_layout.addWidget(self.temperature, 5, 3)

        properties_group.setLayout(properties_layout)
        content_layout.addWidget(properties_group)

        # ============ Solids Analysis ============
        solids_group = QGroupBox("🔬 Solids Analysis")
        solids_layout = QGridLayout()

        solids_layout.addWidget(QLabel("Solids (%):"), 0, 0)
        self.solid_percent = QDoubleSpinBox()
        self.solid_percent.setRange(0, 100)
        self.solid_percent.setDecimals(1)
        solids_layout.addWidget(self.solid_percent, 0, 1)

        solids_layout.addWidget(QLabel("Oil (%):"), 0, 2)
        self.oil_percent = QDoubleSpinBox()
        self.oil_percent.setRange(0, 100)
        self.oil_percent.setDecimals(1)
        solids_layout.addWidget(self.oil_percent, 0, 3)

        solids_layout.addWidget(QLabel("Water (%):"), 1, 0)
        self.water_percent = QDoubleSpinBox()
        self.water_percent.setRange(0, 100)
        self.water_percent.setDecimals(1)
        solids_layout.addWidget(self.water_percent, 1, 1)

        solids_layout.addWidget(QLabel("Chloride (ppm):"), 1, 2)
        self.chloride = QDoubleSpinBox()
        self.chloride.setRange(0, 50000)
        self.chloride.setDecimals(0)
        solids_layout.addWidget(self.chloride, 1, 3)

        solids_group.setLayout(solids_layout)
        content_layout.addWidget(solids_group)

        # ============ Volumes ============
        volumes_group = QGroupBox("📊 Volumes")
        volumes_layout = QGridLayout()

        volumes_layout.addWidget(QLabel("Volume in Hole (bbl):"), 0, 0)
        self.volume_hole = QDoubleSpinBox()
        self.volume_hole.setRange(0, 10000)
        self.volume_hole.setDecimals(1)
        volumes_layout.addWidget(self.volume_hole, 0, 1)

        volumes_layout.addWidget(QLabel("Total Circulated (bbl):"), 0, 2)
        self.total_circulated = QDoubleSpinBox()
        self.total_circulated.setRange(0, 20000)
        self.total_circulated.setDecimals(1)
        volumes_layout.addWidget(self.total_circulated, 0, 3)

        volumes_layout.addWidget(QLabel("Downhole Loss (bbl):"), 1, 0)
        self.loss_downhole = QDoubleSpinBox()
        self.loss_downhole.setRange(0, 5000)
        self.loss_downhole.setDecimals(1)
        volumes_layout.addWidget(self.loss_downhole, 1, 1)

        volumes_layout.addWidget(QLabel("Surface Loss (bbl):"), 1, 2)
        self.loss_surface = QDoubleSpinBox()
        self.loss_surface.setRange(0, 5000)
        self.loss_surface.setDecimals(1)
        volumes_layout.addWidget(self.loss_surface, 1, 3)

        volumes_group.setLayout(volumes_layout)
        content_layout.addWidget(volumes_group)

        # ============ Mud Chemicals ============
        chemicals_group = QGroupBox("🧪 Mud Chemicals")
        chemicals_layout = QVBoxLayout()

        chem_scroll = QScrollArea()
        chem_scroll.setWidgetResizable(True)
        chem_scroll.setMinimumHeight(200)
        chem_scroll.setMaximumHeight(350)

        self.chemicals_table = QTableWidget(0, 6)
        self.chemicals_table.setHorizontalHeaderLabels([
            "Product", "Type", "Received", "Used", "Stock", "Unit"
        ])
        self.chemicals_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.chemicals_table.setMinimumHeight(180)

        chem_scroll.setWidget(self.chemicals_table)
        chemicals_layout.addWidget(chem_scroll)

        chem_btn_layout = QHBoxLayout()
        add_chem_btn = QPushButton("➕ Add Chemical")
        add_chem_btn.clicked.connect(self.add_chemical_row)
        remove_chem_btn = QPushButton("➖ Remove")
        remove_chem_btn.clicked.connect(self.remove_chemical_row)

        chem_btn_layout.addWidget(add_chem_btn)
        chem_btn_layout.addWidget(remove_chem_btn)
        chem_btn_layout.addStretch()
        chemicals_layout.addLayout(chem_btn_layout)

        chemicals_group.setLayout(chemicals_layout)
        content_layout.addWidget(chemicals_group)

        # ============ Mud Summary ============
        summary_group = QGroupBox("📝 Mud Summary")
        summary_layout = QVBoxLayout()
        self.mud_summary = QTextEdit()
        self.mud_summary.setMaximumHeight(100)
        self.mud_summary.setPlaceholderText("Enter mud condition summary...")
        summary_layout.addWidget(self.mud_summary)
        summary_group.setLayout(summary_layout)
        content_layout.addWidget(summary_group)

        # ============ Action Buttons ============
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.clicked.connect(self.save_data)
        self.load_btn = QPushButton("📂 Load")
        self.load_btn.clicked.connect(self.load_data)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.load_btn)
        btn_layout.addStretch()
        content_layout.addLayout(btn_layout)
        content_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)

        self.add_chemical_row("Bentonite", "Viscosifier", 100, 50, 50, "kg")
        self.add_chemical_row("Barite", "Weight Material", 200, 100, 100, "kg")
        self.add_chemical_row("Caustic Soda", "Alkalinity", 50, 20, 30, "kg")

    def setup_connections(self):
        self.mud_type.currentTextChanged.connect(self.update_mud_formulation)
        self.sample_time.timeChanged.connect(self.update_sample_time)
        self.solid_percent.valueChanged.connect(self.check_percentages_total)
        self.oil_percent.valueChanged.connect(self.check_percentages_total)
        self.water_percent.valueChanged.connect(self.check_percentages_total)
        self.volume_hole.valueChanged.connect(self.update_mud_volumes)
        self.total_circulated.valueChanged.connect(self.update_mud_volumes)
        self.loss_downhole.valueChanged.connect(self.update_mud_losses)
        self.loss_surface.valueChanged.connect(self.update_mud_losses)
        self.mw.valueChanged.connect(self.update_mud_properties)
        self.pv.valueChanged.connect(self.update_mud_properties)
        self.yp.valueChanged.connect(self.update_mud_properties)
        self.ph.valueChanged.connect(self.update_ph_balance)
        self.temperature.valueChanged.connect(self.update_temperature_effects)

    # ============ Chemicals Table Methods ============

    def add_chemical_row(self, product="", product_type="", received=0,
                          used=0, stock=0, unit="kg"):
        row = self.chemicals_table.rowCount()
        self.chemicals_table.insertRow(row)

        product_edit = QLineEdit(product or f"Chemical_{row+1}")
        self.chemicals_table.setCellWidget(row, 0, product_edit)

        type_combo = QComboBox()
        type_combo.addItems([
            "Viscosifier", "Weight Material", "Alkalinity",
            "Filtration Control", "Lubricant", "Shale Inhibitor"
        ])
        if product_type in [type_combo.itemText(i)
                             for i in range(type_combo.count())]:
            type_combo.setCurrentText(product_type)
        self.chemicals_table.setCellWidget(row, 1, type_combo)

        received_spin = QDoubleSpinBox()
        received_spin.setRange(0, 10000)
        received_spin.setValue(received)
        received_spin.valueChanged.connect(
            lambda val, r=row: self.calculate_stock_for_row(r)
        )
        self.chemicals_table.setCellWidget(row, 2, received_spin)

        used_spin = QDoubleSpinBox()
        used_spin.setRange(0, 10000)
        used_spin.setValue(used)
        used_spin.valueChanged.connect(
            lambda val, r=row: self.calculate_stock_for_row(r)
        )
        self.chemicals_table.setCellWidget(row, 3, used_spin)

        stock_spin = QDoubleSpinBox()
        stock_spin.setRange(-10000, 10000)
        stock_spin.setValue(stock)
        stock_spin.setReadOnly(True)
        self.chemicals_table.setCellWidget(row, 4, stock_spin)

        unit_combo = QComboBox()
        unit_combo.addItems(["kg", "lb", "bbl", "gal", "l", "m³"])
        unit_combo.setCurrentText(unit)
        self.chemicals_table.setCellWidget(row, 5, unit_combo)

    def remove_chemical_row(self):
        current_row = self.chemicals_table.currentRow()
        if current_row >= 0:
            self.chemicals_table.removeRow(current_row)

    def calculate_stock(self):
        for row in range(self.chemicals_table.rowCount()):
            received_widget = self.chemicals_table.cellWidget(row, 2)
            used_widget = self.chemicals_table.cellWidget(row, 3)
            stock_widget = self.chemicals_table.cellWidget(row, 4)
            if received_widget and used_widget and stock_widget:
                stock = received_widget.value() - used_widget.value()
                stock_widget.setValue(stock)
    
    def calculate_stock_for_row(self, row):
        """محاسبه خودکار موجودی برای یک ردیف خاص"""
        received_widget = self.chemicals_table.cellWidget(row, 2)
        used_widget = self.chemicals_table.cellWidget(row, 3)
        stock_widget = self.chemicals_table.cellWidget(row, 4)
        if received_widget and used_widget and stock_widget:
            stock = received_widget.value() - used_widget.value()
            stock_widget.setValue(stock)
    
    # ============ Update helper methods (for live calculations) ============
    def check_percentages_total(self):
        total = self.solid_percent.value() + self.oil_percent.value() + self.water_percent.value()
        if abs(total - 100) > 0.1:
            logger.warning(f"Solids+Oil+Water = {total:.1f}%, expected 100%")

    def update_mud_volumes(self):
        volume_in_hole = self.volume_hole.value()
        total_circulated = self.total_circulated.value()
        # محاسبه اختلاف حجم
        difference = total_circulated - volume_in_hole
        if difference > 0:
            logger.debug(f"Mud volumes: Hole={volume_in_hole:.1f} bbl, Circulated={total_circulated:.1f} bbl, Gain={difference:.1f} bbl")
        elif difference < 0:
            logger.debug(f"Mud volumes: Hole={volume_in_hole:.1f} bbl, Circulated={total_circulated:.1f} bbl, Loss={-difference:.1f} bbl")
        else:
            logger.debug(f"Mud volumes balanced: {volume_in_hole:.1f} bbl")

    def update_mud_losses(self):
        downhole = self.loss_downhole.value()
        surface = self.loss_surface.value()
        total_loss = downhole + surface
        if total_loss > 0:
            logger.debug(f"Mud losses: Downhole={downhole:.1f} bbl, Surface={surface:.1f} bbl, Total={total_loss:.1f} bbl")
        else:
            logger.debug("No mud losses reported.")

    def update_mud_properties(self):
        # محاسبه نسبت YP/PV و غیره
        pv = self.pv.value()
        yp = self.yp.value()
        if pv > 0:
            yp_pv_ratio = yp / pv
            logger.debug(f"YP/PV ratio: {yp_pv_ratio:.2f}")

    def update_ph_balance(self):
        ph = self.ph.value()
        if ph < 8.0 or ph > 11.0:
            logger.warning(f"pH {ph} outside typical range")

    def update_temperature_effects(self):
        temp = self.temperature.value()
        logger.debug(f"Temperature changed to {temp}°C")

    def update_mud_formulation(self, mud_type):
        logger.info(f"Mud type changed to {mud_type}")

    def update_sample_time(self):
        logger.debug("Sample time updated")

    # ============ Core data methods ============
    def set_current_well(self, well_id):
        self.current_well = well_id

    def load_for_report(self, report_id):
        if not self.db_manager:
            return
        data = self.db_manager.get_mud_report(report_id=report_id)
        if data:
            self.load_from_dict(data)
        else:
            self.clear_form()

    def save_data_for_report(self, report_id):
        if not self.current_well:
            return False
        chemicals = self.collect_chemicals()
        mud_data = {
            "well_id": self.current_well,
            "report_id": report_id,
            "report_date": date.today(),
            "mud_type": self.mud_type.currentText(),
            "sample_time": self.sample_time.time().toPython(),
            "mw": self.mw.value(),
            "pv": self.pv.value(),
            "yp": self.yp.value(),
            "funnel_vis": self.funnel_vis.value(),
            "gel_10s": self.gel_10s.value(),
            "gel_10m": self.gel_10m.value(),
            "fl": self.fl.value(),
            "cake_thickness": self.cake_thickness.value(),
            "ph": self.ph.value(),
            "temperature": self.temperature.value(),
            "solid_percent": self.solid_percent.value(),
            "oil_percent": self.oil_percent.value(),
            "water_percent": self.water_percent.value(),
            "chloride": self.chloride.value(),
            "volume_hole": self.volume_hole.value(),
            "total_circulated": self.total_circulated.value(),
            "loss_downhole": self.loss_downhole.value(),
            "loss_surface": self.loss_surface.value(),
            "summary": self.mud_summary.toPlainText(),
            "chemicals_json": json.dumps(chemicals),
        }
        result = self.db_manager.save_mud_report(mud_data)
        return result is not None

    def collect_chemicals(self):
        chemicals = []
        for row in range(self.chemicals_table.rowCount()):
            product_widget = self.chemicals_table.cellWidget(row, 0)
            type_widget = self.chemicals_table.cellWidget(row, 1)
            received_widget = self.chemicals_table.cellWidget(row, 2)
            used_widget = self.chemicals_table.cellWidget(row, 3)
            stock_widget = self.chemicals_table.cellWidget(row, 4)
            unit_widget = self.chemicals_table.cellWidget(row, 5)
            chemicals.append({
                "product": product_widget.text() if product_widget else "",
                "type": type_widget.currentText() if type_widget else "",
                "received": received_widget.value() if received_widget else 0,
                "used": used_widget.value() if used_widget else 0,
                "stock": stock_widget.value() if stock_widget else 0,
                "unit": unit_widget.currentText() if unit_widget else "kg",
            })
        return chemicals

    def save_data(self):
        if self.parent and hasattr(self.parent, 'current_report_id') and self.parent.current_report_id:
            return self.save_data_for_report(self.parent.current_report_id)
        else:
            QMessageBox.warning(self, "Warning", "No report selected. Please select a Daily Report first.")
            return False

    def load_data(self):
        if self.parent and hasattr(self.parent, 'current_report_id') and self.parent.current_report_id:
            self.load_for_report(self.parent.current_report_id)
            return True
        else:
            logger.debug("MudReportTab: no report selected yet")
            return False
        
    def load_from_dict(self, data: dict):
        def safe_val(key, default=0):
            v = data.get(key)
            if v is None:
                return default
            try:
                return float(v)
            except (ValueError, TypeError):
                return default

        self.mud_type.setCurrentText(str(data.get("mud_type", "") or ""))
        self.mw.setValue(safe_val("mw", 65.0))
        self.pv.setValue(safe_val("pv"))
        self.yp.setValue(safe_val("yp"))
        self.funnel_vis.setValue(safe_val("funnel_vis"))
        self.gel_10s.setValue(safe_val("gel_10s"))
        self.gel_10m.setValue(safe_val("gel_10m"))
        self.fl.setValue(safe_val("fl"))
        self.cake_thickness.setValue(safe_val("cake_thickness"))
        self.ph.setValue(safe_val("ph", 9.5))
        self.temperature.setValue(safe_val("temperature", 25.0))
        self.solid_percent.setValue(safe_val("solid_percent"))
        self.oil_percent.setValue(safe_val("oil_percent"))
        self.water_percent.setValue(safe_val("water_percent"))
        self.chloride.setValue(safe_val("chloride"))
        self.volume_hole.setValue(safe_val("volume_hole"))
        self.total_circulated.setValue(safe_val("total_circulated"))
        self.loss_downhole.setValue(safe_val("loss_downhole"))
        self.loss_surface.setValue(safe_val("loss_surface"))
        self.mud_summary.setPlainText(str(data.get("summary", "") or ""))

        chemicals_json = data.get("chemicals_json")
        if chemicals_json:
            self.chemicals_table.setRowCount(0)
            try:
                chemicals = json.loads(chemicals_json) if isinstance(chemicals_json, str) else chemicals_json
                for c in chemicals:
                    self.add_chemical_row(
                        c.get("product", ""),
                        c.get("type", ""),
                        float(c.get("received", 0) or 0),
                        float(c.get("used", 0) or 0),
                        float(c.get("stock", 0) or 0),
                        c.get("unit", "kg"),
                    )
            except (json.JSONDecodeError, TypeError):
                pass
                
    def clear_form(self):
        self.mud_type.setCurrentIndex(0)
        self.mw.setValue(65.0)
        self.pv.setValue(0)
        self.yp.setValue(0)
        self.funnel_vis.setValue(0)
        self.gel_10s.setValue(0)
        self.gel_10m.setValue(0)
        self.fl.setValue(0)
        self.cake_thickness.setValue(0)
        self.ph.setValue(9.5)
        self.temperature.setValue(25.0)
        self.solid_percent.setValue(0)
        self.oil_percent.setValue(0)
        self.water_percent.setValue(0)
        self.chloride.setValue(0)
        self.volume_hole.setValue(0)
        self.total_circulated.setValue(0)
        self.loss_downhole.setValue(0)
        self.loss_surface.setValue(0)
        self.chemicals_table.setRowCount(0)
        self.mud_summary.clear()

    def refresh(self):
        self.load_data()
        

