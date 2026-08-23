"""
Trajectory Widget - ابزار مدیریت تراژکتوری چاه با قابلیت‌های پیشرفته (بازنویسی کامل)
"""

import os
import csv
import math
import json
import logging
from datetime import datetime, date, time, timedelta
from typing import Dict, List, Any, Optional, Tuple

try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    pg = None
    logging.getLogger(__name__).warning(
        "pyqtgraph not installed. Trajectory plots disabled."
    )


from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtGui import *

from core.database import (
    Well, Section, TripSheetEntry, SurveyPoint, 
    TrajectoryCalculation, TrajectoryPlot, DatabaseManager
)
from core.managers import (
    StatusBarManager, TableManager, ExportManager,
    TableButtonManager, setup_widget_with_managers
)
from core.base_tab import DrillTabBase

logger = logging.getLogger(__name__)

# ==================== Base Widget (replaced by DrillTabBase) ====================
# We use DrillTabBase for main widget; sub-tabs can remain as QWidget.

# ==================== Trip Sheet Tab ====================
class TripSheetTab(QWidget):
    """تب Trip Sheet برای مدیریت سفرهای مته"""
    
    def __init__(self, db_manager: DatabaseManager = None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.current_well_id = None
        self.current_report_id = None
        self.table_manager = None
        self.status_manager = StatusBarManager()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.trip_table = QTableWidget(0, 9)
        self.trip_table.setHorizontalHeaderLabels([
            "ID", "Time", "Activity", "Depth (m)", "Cum. Trip (m)", 
            "Duration (hr)", "Remarks", "Supervisor", "Verified"
        ])
        self.trip_table.hideColumn(0)
        self.table_manager = TableManager(self.trip_table, self)
        self.trip_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.trip_table)
        
        button_layout = QHBoxLayout()
        self.add_btn = QPushButton("➕ Add Row")
        self.add_btn.clicked.connect(self.add_row)
        self.delete_btn = QPushButton("❌ Delete Row")
        self.delete_btn.clicked.connect(self.delete_row)
        self.calculate_btn = QPushButton("🔄 Calculate Cumulative")
        self.calculate_btn.clicked.connect(self.calculate_cumulative)
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.clicked.connect(self.save_data)
        self.load_btn = QPushButton("📂 Load")
        self.load_btn.clicked.connect(self.load_data)
        self.clear_btn = QPushButton("🗑️ Clear")
        self.clear_btn.clicked.connect(self.clear_table)
        
        button_layout.addWidget(self.add_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addWidget(self.calculate_btn)
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.load_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Operational tables start empty; data comes from the selected report.
    
    def set_current_well(self, well_id: int, section_id: int = None):
        self.current_well_id = well_id
        if well_id:
            self.load_data()
    
    def load_for_report(self, report_id: int):
        self.current_report_id = report_id
        self.load_data()
    
    def add_row(self, data=None):
        if isinstance(data, bool):
            data = None
        
        if data is None:
            data = [
                datetime.now().strftime("%H:%M"),
                "New Activity",
                "0.0",
                "0.0",
                "0.0",
                "",
                "",
                False
            ]
        
        row = self.table_manager.add_row(data)
        if row >= 0:
            checkbox = QCheckBox()
            if len(data) > 7:
                # در صورت وجود مقدار verified در داده (index 7)
                if isinstance(data, (list, tuple)) and len(data) > 7:
                    verified_value = data[7]
                    if isinstance(verified_value, bool):
                        checkbox.setChecked(verified_value)
                    elif isinstance(verified_value, str):
                        checkbox.setChecked(verified_value.lower() in ('true', 'yes', '1'))
                    else:
                        checkbox.setChecked(False)
                else:
                    checkbox.setChecked(False)
            else:
                checkbox.setChecked(False)
            
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            self.trip_table.setCellWidget(row, 8, checkbox_widget)
        return row
    
    def delete_row(self):
        if self.trip_table.currentRow() >= 0:
            self.table_manager.delete_row()
    
    def calculate_cumulative(self):
        try:
            cumulative = 0.0
            for row in range(self.trip_table.rowCount()):
                depth_item = self.trip_table.item(row, 3)
                if depth_item and depth_item.text():
                    depth = float(depth_item.text())
                    cumulative += depth
                    cum_item = QTableWidgetItem(f"{cumulative:.2f}")
                    cum_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.trip_table.setItem(row, 4, cum_item)
            QMessageBox.information(self, "Success", f"Cumulative calculation completed\nTotal: {cumulative:.2f} m")
        except ValueError as e:
            QMessageBox.warning(self, "Error", f"Invalid depth values: {str(e)}")
    
    def save_data(self):
        if not self.current_well_id or not self.current_report_id:
            self.status_manager.show_error("TripSheet", "Well or report not selected")
            return False

        
        session = self.db_manager.create_session()
        try:
            # حذف رکوردهای قبلی
            session.query(TripSheetEntry).filter(
                TripSheetEntry.well_id == self.current_well_id,
                TripSheetEntry.report_id == self.current_report_id
            ).delete()
            
            saved_count = 0
            for row in range(self.trip_table.rowCount()):
                # چک کردن وجود item قبل از .text()
                time_item = self.trip_table.item(row, 1)
                activity_item = self.trip_table.item(row, 2)
                depth_item = self.trip_table.item(row, 3)
                cum_item = self.trip_table.item(row, 4)
                duration_item = self.trip_table.item(row, 5)
                remarks_item = self.trip_table.item(row, 6)
                supervisor_item = self.trip_table.item(row, 7)
                
                if not all([time_item, activity_item]):
                    continue  # از ردیف‌های خالی بگذر
                
                time_str = time_item.text().strip()
                activity = activity_item.text().strip()
                depth = float(depth_item.text() or 0) if depth_item else 0.0
                cum_trip = float(cum_item.text() or 0) if cum_item else 0.0
                duration = float(duration_item.text() or 0) if duration_item else 0.0
                remarks = remarks_item.text().strip() if remarks_item else ""
                supervisor = supervisor_item.text().strip() if supervisor_item else ""
                
                # خواندن چک‌باکس
                checkbox_widget = self.trip_table.cellWidget(row, 8)
                verified = False
                if checkbox_widget:
                    checkbox = checkbox_widget.findChild(QCheckBox)
                    if checkbox:
                        verified = checkbox.isChecked()
                
                try:
                    time_obj = datetime.strptime(time_str, "%H:%M").time()
                except:
                    time_obj = datetime.now().time()
                
                entry = TripSheetEntry(
                    well_id=self.current_well_id,
                    report_id=self.current_report_id,
                    time=time_obj,
                    activity=activity,
                    depth=depth,
                    cum_trip=cum_trip,
                    duration=duration,
                    remarks=remarks,
                    supervisor=supervisor,
                    verified=verified
                )
                session.add(entry)
                saved_count += 1
            
            session.commit()
            logger.info(f"Saved {saved_count} trip sheet entries")
            return True
        
        except Exception as e:
            session.rollback()
            logger.error(f"Trip sheet save error: {e}")
            return False
        finally:
            session.close()
        
    def load_data(self):
        if not self.current_well_id:
            return
        self.clear_table()
        if self.db_manager:
            entries = self.db_manager.load_trip_sheet_entries(
                well_id=self.current_well_id,
                report_id=self.current_report_id
            )
            for entry in entries:
                row = self.trip_table.rowCount()
                self.trip_table.insertRow(row)
                self.trip_table.setItem(row, 0, QTableWidgetItem(str(entry['id'])))
                self.trip_table.setItem(row, 1, QTableWidgetItem(entry['time']))
                self.trip_table.setItem(row, 2, QTableWidgetItem(entry['activity']))
                self.trip_table.setItem(row, 3, QTableWidgetItem(str(entry['depth'])))
                self.trip_table.setItem(row, 4, QTableWidgetItem(str(entry['cum_trip'])))
                self.trip_table.setItem(row, 5, QTableWidgetItem(str(entry['duration'])))
                self.trip_table.setItem(row, 6, QTableWidgetItem(entry['remarks']))
                self.trip_table.setItem(row, 7, QTableWidgetItem(entry['supervisor']))
                checkbox = QCheckBox()
                checkbox.setChecked(entry['verified'])
                checkbox_widget = QWidget()
                checkbox_layout = QHBoxLayout(checkbox_widget)
                checkbox_layout.addWidget(checkbox)
                checkbox_layout.setAlignment(Qt.AlignCenter)
                checkbox_layout.setContentsMargins(0, 0, 0, 0)
                self.trip_table.setCellWidget(row, 8, checkbox_widget)
    
    def clear_table(self):
        self.trip_table.setRowCount(0)
    
    def export_data(self):
        export_manager = ExportManager(self)
        export_manager.export_table_with_dialog(self.trip_table, "trip_sheet")


# ==================== Survey Data Tab ====================
class SurveyDataTab(QWidget):
    """تب داده‌های سروی"""
    
    def __init__(self, db_manager: DatabaseManager = None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.current_well_id = None
        self.current_report_id = None
        self.table_manager = None
        self.status_manager = StatusBarManager()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.survey_table = QTableWidget(0, 12)
        self.survey_table.setHorizontalHeaderLabels([
            "ID", "MD (m)", "Inc (°)", "Azi (°)", "TVD (m)", "North (m)", "East (m)", 
            "VS (m)", "HD (m)", "DLS (°/30m)", "Tool", "Remarks"
        ])
        self.survey_table.hideColumn(0)
        self.table_manager = TableManager(self.survey_table, self)
        self.survey_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.survey_table)
        
        button_layout = QHBoxLayout()
        self.add_btn = QPushButton("➕ Add Row")
        self.add_btn.clicked.connect(self.add_row)
        self.delete_btn = QPushButton("❌ Delete Row")
        self.delete_btn.clicked.connect(self.delete_row)
        self.import_btn = QPushButton("📂 Import")
        self.import_btn.clicked.connect(self.import_data)
        self.calculate_btn = QPushButton("🔄 Calculate")
        self.calculate_btn.clicked.connect(self.calculate_trajectory)
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.clicked.connect(self.save_data)
        self.load_btn = QPushButton("📂 Load")
        self.load_btn.clicked.connect(self.load_data)
        self.clear_btn = QPushButton("🗑️ Clear")
        self.clear_btn.clicked.connect(self.clear_table)
        self.export_btn = QPushButton("📤 Export")
        self.export_btn.clicked.connect(self.export_data)
        
        button_layout.addWidget(self.add_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addWidget(self.import_btn)
        button_layout.addWidget(self.calculate_btn)
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.load_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addWidget(self.export_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Operational tables start empty; data comes from the selected report.
    
    def set_current_well(self, well_id: int, section_id: int = None):
        self.current_well_id = well_id
        if well_id:
            self.load_data()
    
    def load_for_report(self, report_id: int):
        self.current_report_id = report_id
        self.load_data()
    
    def add_row(self, data=None):
        if data is None:
            data = ["0.0", "0.0", "0.0", "0.0", "0.0", "0.0", "0.0", "0.0", "0.0", "MWD", ""]
        return self.table_manager.add_row(data)
    
    def delete_row(self):
        if self.survey_table.currentRow() >= 0:
            self.table_manager.delete_row()
    
    def import_data(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Import Survey Data", "", "CSV Files (*.csv);;All Files (*.*)")
        if filename:
            self.table_manager.import_from_csv(filename)
    
    def calculate_trajectory(self):
        if self.survey_table.rowCount() < 2:
            QMessageBox.warning(self, "Error", "At least 2 survey points are required")
            return
        survey_points = []
        for row in range(self.survey_table.rowCount()):
            md_item = self.survey_table.item(row, 1)
            inc_item = self.survey_table.item(row, 2)
            azi_item = self.survey_table.item(row, 3)
            if md_item and inc_item and azi_item:
                try:
                    md = float(md_item.text())
                    inc = float(inc_item.text())
                    azi = float(azi_item.text())
                    survey_points.append({'row': row, 'md': md, 'inc': inc, 'azi': azi})
                except ValueError:
                    QMessageBox.warning(self, "Error", f"Invalid data in row {row+1}")
                    return
        survey_points.sort(key=lambda x: x['md'])
        
        tvd = north = east = vs = hd = dls = 0.0
        if survey_points and survey_points[0]['row'] == 0:
            self.update_row_calculations(0, tvd, north, east, vs, hd, dls)
        
        for i in range(1, len(survey_points)):
            prev = survey_points[i-1]
            curr = survey_points[i]
            md1, inc1, azi1 = prev['md'], prev['inc'], prev['azi']
            md2, inc2, azi2 = curr['md'], curr['inc'], curr['azi']
            inc1_rad = math.radians(inc1)
            inc2_rad = math.radians(inc2)
            azi1_rad = math.radians(azi1)
            azi2_rad = math.radians(azi2)
            delta_md = md2 - md1
            if delta_md <= 0:
                QMessageBox.warning(self, "Error", f"MD must increase (row {curr['row']+1})")
                return
            cos_beta = (math.sin(inc1_rad) * math.sin(inc2_rad) * math.cos(azi2_rad - azi1_rad) + 
                        math.cos(inc1_rad) * math.cos(inc2_rad))
            cos_beta = max(-1.0, min(1.0, cos_beta))
            beta = math.acos(cos_beta)
            rf = 1.0 if abs(beta) < 1e-10 else 2.0 / beta * math.tan(beta / 2.0)
            delta_tvd = 0.5 * delta_md * (math.cos(inc1_rad) + math.cos(inc2_rad)) * rf
            delta_north = 0.5 * delta_md * (math.sin(inc1_rad) * math.cos(azi1_rad) + math.sin(inc2_rad) * math.cos(azi2_rad)) * rf
            delta_east = 0.5 * delta_md * (math.sin(inc1_rad) * math.sin(azi1_rad) + math.sin(inc2_rad) * math.sin(azi2_rad)) * rf
            tvd += delta_tvd
            north += delta_north
            east += delta_east
            hd = math.sqrt(north**2 + east**2)
            vs_ref_rad = 0.0
            vs = north * math.cos(vs_ref_rad) + east * math.sin(vs_ref_rad)
            dls_result = _calc_dls(beta, delta_md)
            dls = dls_result["deg_per_30m"]
            self.update_row_calculations(curr['row'], tvd, north, east, vs, hd, dls)
        
            if dls_result["warning"]:
                item = self.survey_table.item(curr['row'], 9)
                if item:
                    item.setBackground(QColor(255, 200, 200))
                    item.setToolTip(dls_result["warning"])
        
        self.highlight_calculated_cells()
        QMessageBox.information(self, "Success",
            f"Trajectory calculation completed\n\n"
            f"Final Results:\n"
            f"• TVD: {tvd:.2f} m\n"
            f"• North: {north:.2f} m\n"
            f"• East: {east:.2f} m\n"
            f"• HD: {hd:.2f} m")
    
    def update_row_calculations(self, row, tvd, north, east, vs, hd, dls):
        self.survey_table.setItem(row, 4, QTableWidgetItem(f"{tvd:.2f}"))
        self.survey_table.setItem(row, 5, QTableWidgetItem(f"{north:.2f}"))
        self.survey_table.setItem(row, 6, QTableWidgetItem(f"{east:.2f}"))
        self.survey_table.setItem(row, 7, QTableWidgetItem(f"{vs:.2f}"))
        self.survey_table.setItem(row, 8, QTableWidgetItem(f"{hd:.2f}"))
        self.survey_table.setItem(row, 9, QTableWidgetItem(f"{dls:.2f}"))
    
    def highlight_calculated_cells(self):
        for row in range(self.survey_table.rowCount()):
            for col in range(4, 10):
                item = self.survey_table.item(row, col)
                if item and item.text() and float(item.text()) != 0.0:
                    item.setBackground(QColor(220, 255, 220))
                    item.setToolTip("Calculated using Minimum Curvature Method")
    
    def save_data(self):
        if not self.current_well_id:
            QMessageBox.warning(self, "Warning", "Please select a well first")
            return False
        
        session = self.db_manager.create_session()
        try:
            session.query(SurveyPoint).filter(
                SurveyPoint.well_id == self.current_well_id,
                SurveyPoint.report_id == self.current_report_id
            ).delete()
            
            saved_count = 0
            for row in range(self.survey_table.rowCount()):
                md_item = self.survey_table.item(row, 1)
                inc_item = self.survey_table.item(row, 2)
                azi_item = self.survey_table.item(row, 3)
                
                if not all([md_item, inc_item, azi_item]):
                    continue
                
                try:
                    md = float(md_item.text() or 0)
                    inc = float(inc_item.text() or 0)
                    azi = float(azi_item.text() or 0)
                except ValueError:
                    continue
                
                tvd_item = self.survey_table.item(row, 4)
                north_item = self.survey_table.item(row, 5)
                east_item = self.survey_table.item(row, 6)
                vs_item = self.survey_table.item(row, 7)
                hd_item = self.survey_table.item(row, 8)
                dls_item = self.survey_table.item(row, 9)
                tool_item = self.survey_table.item(row, 10)
                remarks_item = self.survey_table.item(row, 11)
                
                tvd = float(tvd_item.text() or 0) if tvd_item else 0.0
                north = float(north_item.text() or 0) if north_item else 0.0
                east = float(east_item.text() or 0) if east_item else 0.0
                vs = float(vs_item.text() or 0) if vs_item else 0.0
                hd = float(hd_item.text() or 0) if hd_item else 0.0
                dls = float(dls_item.text() or 0) if dls_item else 0.0
                tool = tool_item.text().strip() if tool_item else "MWD"
                remarks = remarks_item.text().strip() if remarks_item else ""
                
                point = SurveyPoint(
                    well_id=self.current_well_id,
                    report_id=self.current_report_id,
                    md=md, inc=inc, azi=azi,
                    tvd=tvd, north=north, east=east,
                    vs=vs, hd=hd, dls=dls,
                    tool=tool, remarks=remarks,
                    measured_at=datetime.now()
                )
                session.add(point)
                saved_count += 1
            
            session.commit()
            logger.info(f"Saved {saved_count} survey points")
            return True
        
        except Exception as e:
            session.rollback()
            logger.error(f"Survey save error: {e}")
            return False
        finally:
            session.close()
        
    def load_data(self):
        if not self.current_well_id:
            return
        self.clear_table()
        if self.db_manager:
            points = self.db_manager.load_survey_points(
                well_id=self.current_well_id,
                report_id=self.current_report_id
            )
            for point in points:
                row = self.survey_table.rowCount()
                self.survey_table.insertRow(row)
                self.survey_table.setItem(row, 0, QTableWidgetItem(str(point['id'])))
                self.survey_table.setItem(row, 1, QTableWidgetItem(str(point['md'])))
                self.survey_table.setItem(row, 2, QTableWidgetItem(str(point['inc'])))
                self.survey_table.setItem(row, 3, QTableWidgetItem(str(point['azi'])))
                self.survey_table.setItem(row, 4, QTableWidgetItem(str(point['tvd'])))
                self.survey_table.setItem(row, 5, QTableWidgetItem(str(point['north'])))
                self.survey_table.setItem(row, 6, QTableWidgetItem(str(point['east'])))
                self.survey_table.setItem(row, 7, QTableWidgetItem(str(point['vs'])))
                self.survey_table.setItem(row, 8, QTableWidgetItem(str(point['hd'])))
                self.survey_table.setItem(row, 9, QTableWidgetItem(str(point['dls'])))
                self.survey_table.setItem(row, 10, QTableWidgetItem(point['tool']))
                self.survey_table.setItem(row, 11, QTableWidgetItem(point['remarks']))
    
    def clear_table(self):
        self.survey_table.setRowCount(0)
    
    def export_data(self):
        export_manager = ExportManager(self)
        export_manager.export_table_with_dialog(self.survey_table, "survey_data")


# ==================== Trajectory Plot Tab ====================
class TrajectoryPlotTab(QWidget):
    """تب نمودارهای تراژکتوری"""
    
    def __init__(self, db_manager: DatabaseManager = None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.current_report_id = None
        self.plots = {}
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
 
        if not PYQTGRAPH_AVAILABLE:
            # نمایش پیام جایگزین به جای crash
            placeholder = QLabel(
                "📊 Trajectory plots require pyqtgraph.\n"
                "Install: pip install pyqtgraph"
            )
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet(
                "color: #7f8c8d; font-size: 12px; padding: 20px;"
            )
            layout.addWidget(placeholder)
            
            # ایجاد placeholder برای جلوگیری از AttributeError
            self.plot_2d_plan = None
            self.plot_2d_side = None
            self.plot_3d_container = QWidget()
            self.plot_3d_label = QLabel("pyqtgraph not available")
            
            control_layout = QHBoxLayout()
            self.plot_btn = QPushButton("📊 Plot (unavailable)")
            self.plot_btn.setEnabled(False)
            control_layout.addWidget(self.plot_btn)
            layout.addLayout(control_layout)
            return
            
        self.plot_tabs = QTabWidget()
        self.plot_2d_plan = pg.PlotWidget()
        self.plot_2d_plan.setBackground("w")
        self.plot_2d_plan.setLabel("left", "North (m)")
        self.plot_2d_plan.setLabel("bottom", "East (m)")
        self.plot_2d_plan.setTitle("2D Plan View")
        self.plot_2d_plan.showGrid(x=True, y=True)
        self.plot_tabs.addTab(self.plot_2d_plan, "2D Plan View")
        
        self.plot_2d_side = pg.PlotWidget()
        self.plot_2d_side.setBackground("w")
        self.plot_2d_side.setLabel("left", "TVD (m)")
        self.plot_2d_side.setLabel("bottom", "Horizontal Displacement (m)")
        self.plot_2d_side.setTitle("2D Side View")
        self.plot_2d_side.showGrid(x=True, y=True)
        self.plot_tabs.addTab(self.plot_2d_side, "2D Side View")
        
        self.plot_3d_container = QWidget()
        self.plot_3d_layout = QVBoxLayout(self.plot_3d_container)
        self.plot_3d_label = QLabel("3D Plot (requires additional 3D plotting library)")
        self.plot_3d_label.setAlignment(Qt.AlignCenter)
        self.plot_3d_layout.addWidget(self.plot_3d_label)
        self.plot_tabs.addTab(self.plot_3d_container, "3D View")
        
        layout.addWidget(self.plot_tabs)
        
        control_layout = QHBoxLayout()
        self.plot_btn = QPushButton("📊 Plot Trajectory")
        self.plot_btn.clicked.connect(self.plot_trajectory)
        self.save_plot_btn = QPushButton("💾 Save Plot")
        self.save_plot_btn.clicked.connect(self.save_plot)
        self.load_plot_btn = QPushButton("📂 Load Plot")
        self.load_plot_btn.clicked.connect(self.load_plots)
        self.clear_plot_btn = QPushButton("🗑️ Clear Plot")
        self.clear_plot_btn.clicked.connect(self.clear_plots)
        self.export_plot_btn = QPushButton("📤 Export Data")
        self.export_plot_btn.clicked.connect(self.export_plot_data)
        
        control_layout.addWidget(self.plot_btn)
        control_layout.addWidget(self.save_plot_btn)
        control_layout.addWidget(self.load_plot_btn)
        control_layout.addWidget(self.clear_plot_btn)
        control_layout.addWidget(self.export_plot_btn)
        control_layout.addStretch()
        layout.addLayout(control_layout)
    
    def load_for_report(self, report_id: int):
        self.current_report_id = report_id
        if report_id:
            self.load_plots()
    
    def plot_trajectory(self, survey_data: List[Dict] = None):
        if not survey_data:
            parent = self.parent()
            if parent and hasattr(parent, 'get_survey_data'):
                survey_data = parent.get_survey_data()
        if not survey_data or len(survey_data) < 2:
            QMessageBox.warning(self, "Warning", "No survey data available")
            return
        mds = [point.get('md', 0) for point in survey_data]
        tvd = [point.get('tvd', 0) for point in survey_data]
        north = [point.get('north', 0) for point in survey_data]
        east = [point.get('east', 0) for point in survey_data]
        hd = [point.get('hd', 0) for point in survey_data]
        
        self.clear_plots()
        self.plot_2d_plan.plot(east, north, pen=pg.mkPen('b', width=2), symbol='o', symbolSize=5)
        self.plot_2d_side.plot(hd, tvd, pen=pg.mkPen('r', width=2), symbol='s', symbolSize=5)
        self.plot_3d_label.setText(f"3D Trajectory Plot\nPoints: {len(survey_data)}\nMax TVD: {max(tvd):.1f} m")
        self.plots = {
            '2d_plan': {'east': east, 'north': north},
            '2d_side': {'hd': hd, 'tvd': tvd},
            '3d': {'md': mds, 'north': north, 'east': east, 'tvd': tvd}
        }
    
    def save_plot(self):
        if not self.current_report_id:
            QMessageBox.warning(self, "Warning", "No calculation selected")
            return False
        plot_data = {
            'report_id': self.current_report_id,
            'plot_type': '2d_plan',
            'title': f'Trajectory Plot {datetime.now():%Y-%m-%d %H:%M}',
            'plot_data': json.dumps(self.plots),
            'image_data': None,
            'image_format': 'png'
        }
        if self.db_manager:
            plot_id = self.db_manager.save_trajectory_plot(plot_data)
            if plot_id:
                logger.info(f"Plot saved with ID: {plot_id}")
                return True
        return False
    
    def load_plots(self):
        if not self.current_report_id:
            return
        if self.db_manager:
            plots = self.db_manager.load_trajectory_plots(report_id=self.current_report_id)
            for plot in plots:
                try:
                    plot_data = json.loads(plot.get('plot_data', '{}'))
                    if plot['plot_type'] == '2d_plan':
                        east = plot_data.get('east', [])
                        north = plot_data.get('north', [])
                        if east and north:
                            self.plot_2d_plan.plot(east, north, pen=pg.mkPen('g', width=2, style=Qt.DashLine), name=f"Saved: {plot['title']}")
                    elif plot['plot_type'] == '2d_side':
                        hd = plot_data.get('hd', [])
                        tvd = plot_data.get('tvd', [])
                        if hd and tvd:
                            self.plot_2d_side.plot(hd, tvd, pen=pg.mkPen('orange', width=2, style=Qt.DashLine), name=f"Saved: {plot['title']}")
                except Exception as e:
                    logger.error(f"Error loading plot {plot['id']}: {e}")
    
    def clear_plots(self):
        self.plot_2d_plan.clear()
        self.plot_2d_side.clear()
        self.plot_3d_label.setText("3D Plot (requires additional 3D plotting library)")
        self.plots.clear()
    
    def export_plot_data(self):
        if not self.plots:
            QMessageBox.warning(self, "Warning", "No plot data to export")
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Export Plot Data", "", "CSV Files (*.csv);;JSON Files (*.json)")
        if filename:
            if filename.endswith('.json'):
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(self.plots, f, indent=2)
            else:
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Type', 'Index', 'X', 'Y', 'Z'])
                    if '2d_plan' in self.plots:
                        east = self.plots['2d_plan'].get('east', [])
                        north = self.plots['2d_plan'].get('north', [])
                        for i, (e, n) in enumerate(zip(east, north)):
                            writer.writerow(['2D_Plan', i, e, n, 0])
                    if '2d_side' in self.plots:
                        hd = self.plots['2d_side'].get('hd', [])
                        tvd = self.plots['2d_side'].get('tvd', [])
                        for i, (h, t) in enumerate(zip(hd, tvd)):
                            writer.writerow(['2D_Side', i, h, t, 0])


# ==================== Trajectory Calculation Manager ====================
class TrajectoryCalculationManager:
    def __init__(self, db_manager: DatabaseManager = None):
        self.db_manager = db_manager
        self.calculations = []
    
    def create_calculation(self, well_id: int, report_id: int = None, method: str = "Minimum Curvature", description: str = "") -> int:
        calculation_data = {
            'well_id': well_id,
            'report_id': report_id,
            'method': method,
            'calculation_date': date.today(),
            'parameters': {},
            'results': {},
            'description': description
        }
        if self.db_manager:
            calc_id = self.db_manager.save_trajectory_calculation(calculation_data)
            if calc_id:
                return calc_id
        return None


# ==================== Main Trajectory Widget ====================
class TrajectoryWidget(DrillTabBase):
    """ویجت اصلی تراژکتوری"""
    
    def __init__(self, db_manager: DatabaseManager = None, parent=None):
        super().__init__("TrajectoryWidget", db_manager, parent)
        self.current_well_id = None
        self.current_report_id = None
        self.current_section_id = None
        
        self.trip_sheet_tab = None
        self.survey_data_tab = None
        self.plot_tab = None
        self.calculation_manager = TrajectoryCalculationManager(db_manager)
        
        self.init_ui()
        setup_widget_with_managers(self, "TrajectoryWidget", enable_autosave=True, autosave_interval=5, setup_shortcuts=True)
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        toolbar = QHBoxLayout()
        self.well_combo = QComboBox()
        self.well_combo.currentIndexChanged.connect(self.on_well_combo_changed)
        self.section_combo = QComboBox()
        self.section_combo.currentIndexChanged.connect(self.on_section_combo_changed)
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_data)
        
        toolbar.addWidget(QLabel("Well:"))
        toolbar.addWidget(self.well_combo)
        toolbar.addWidget(QLabel("Section:"))
        toolbar.addWidget(self.section_combo)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch()
        main_layout.addLayout(toolbar)
        
        self.tab_widget = QTabWidget()
        self.trip_sheet_tab = TripSheetTab(self.db)
        self.survey_data_tab = SurveyDataTab(self.db)
        self.plot_tab = TrajectoryPlotTab(self.db)
        self.tab_widget.addTab(self.trip_sheet_tab, "Trip Sheet")
        self.tab_widget.addTab(self.survey_data_tab, "Survey Data")
        self.tab_widget.addTab(self.plot_tab, "Trajectory Plot")
        main_layout.addWidget(self.tab_widget)
        
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignRight)
        main_layout.addWidget(self.status_label)
        
        self.load_wells()
    
    def load_wells(self):
        self.well_combo.clear()
        if self.db:
            hierarchy = self.db.get_hierarchy()
            for company in hierarchy:
                for project in company.get('projects', []):
                    for well in project.get('wells', []):
                        display = f"{well['name']} ({well['code']}) - {project['name']}"
                        self.well_combo.addItem(display, well['id'])
    
    def on_well_combo_changed(self, index):
        if index >= 0:
            well_id = self.well_combo.currentData()
            if well_id != self.current_well_id:
                self.current_well_id = well_id
                self.load_sections(well_id)
                self.update_tabs()
    
    def load_sections(self, well_id):
        self.section_combo.clear()
        self.section_combo.addItem("All Sections", -1)
        if self.db and well_id:
            sections = self.db.get_sections_by_well(well_id)
            for section in sections:
                display = f"{section['name']} ({section['code']})"
                self.section_combo.addItem(display, section['id'])
    
    def on_section_combo_changed(self, index):
        if index >= 0:
            section_id = self.section_combo.currentData()
            self.current_section_id = section_id if section_id != -1 else None
            self.update_tabs()

            
    def on_well_changed(self, well_id, well_data):
        """Override DrillTabBase - sync با combo داخلی"""
        self.current_well_id = well_id
        # Sync internal combo
        self.well_combo.blockSignals(True)
        for i in range(self.well_combo.count()):
            if self.well_combo.itemData(i) == well_id:
                self.well_combo.setCurrentIndex(i)
                break
        self.well_combo.blockSignals(False)
        
        self.load_sections(well_id)
        self.update_tabs()

    def on_section_changed(self, section_id, section_data):
        """Override DrillTabBase"""
        self.current_section_id = section_id
        # Sync internal combo
        self.section_combo.blockSignals(True)
        for i in range(self.section_combo.count()):
            if self.section_combo.itemData(i) == section_id:
                self.section_combo.setCurrentIndex(i)
                break
        self.section_combo.blockSignals(False)
        
        self.update_tabs()

    def on_report_changed(self, report_id, report_info):
        """Override DrillTabBase"""
        self.current_report_id = report_id
        self.update_tabs()
    
    def update_tabs(self):
        """به‌روزرسانی همه زیرتب‌ها با وضعیت جاری"""
        if self.trip_sheet_tab:
            self.trip_sheet_tab.current_well_id = self.current_well_id
            self.trip_sheet_tab.current_report_id = self.current_report_id
            self.trip_sheet_tab.current_section_id = self.current_section_id
            if self.current_well_id:
                self.trip_sheet_tab.load_data()

        if self.survey_data_tab:
            self.survey_data_tab.current_well_id = self.current_well_id
            self.survey_data_tab.current_report_id = self.current_report_id
            self.survey_data_tab.current_section_id = self.current_section_id
            if self.current_well_id:
                self.survey_data_tab.load_data()

        if self.plot_tab:
            self.plot_tab.current_report_id = self.current_report_id
            if self.current_report_id:
                self.plot_tab.load_plots()
    
    def get_survey_data(self):
        data = []
        if self.survey_data_tab:
            for row in range(self.survey_data_tab.survey_table.rowCount()):
                row_data = {}
                for col in range(1, 12):
                    item = self.survey_data_tab.survey_table.item(row, col)
                    if item and item.text():
                        try:
                            value = float(item.text())
                            row_data[self.survey_data_tab.survey_table.horizontalHeaderItem(col).text()] = value
                        except ValueError:
                            row_data[self.survey_data_tab.survey_table.horizontalHeaderItem(col).text()] = item.text()
                data.append(row_data)
        return data
    
    def save_data(self):
        success = True
        if self.trip_sheet_tab:
            if not self.trip_sheet_tab.save_data():
                success = False
        if self.survey_data_tab:
            if not self.survey_data_tab.save_data():
                success = False
        if self.plot_tab:
            if not self.plot_tab.save_plot():
                pass  # optional
        if success:
            self.show_success("Trajectory data saved")
        else:
            self.show_error("Some data could not be saved")
        return success
    
    def refresh_data(self):
        self.load_wells()
        self.update_tabs()
        self.show_message("Data refreshed")
    
    def setup_shortcuts(self):
        shortcuts = {
            "Ctrl+S": self.save_data,
            "F5": self.refresh_data,
        }
        for key, slot in shortcuts.items():
            QShortcut(QKeySequence(key), self).activated.connect(slot)