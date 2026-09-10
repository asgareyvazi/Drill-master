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
from core.editor_state import editor_loaded, editor_saved
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
    
    @editor_saved()
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
                except (TypeError, ValueError):
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
        
    @editor_loaded()
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
            data = [""] * self.survey_table.columnCount()
        return self.table_manager.add_row(data)
    
    def delete_row(self):
        if self.survey_table.currentRow() >= 0:
            self.table_manager.delete_row()
    
    def import_data(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Import Survey Data", "", "CSV Files (*.csv);;All Files (*.*)")
        if filename:
            self.table_manager.import_from_csv(filename)
    
    def calculate_trajectory(self):
        from core.survey_records import prepare_surveys, DERIVED_FIELDS
        rows = []
        for index in range(self.survey_table.rowCount()):
            record = {key: self.survey_table.item(index, column).text() if self.survey_table.item(index, column) else None
                      for column, key in enumerate(("md", "inc", "azi"), 1)}
            record["_ui_row"] = index
            rows.append(record)
        try:
            records, issues, rejected = prepare_surveys(rows)
            for index in range(self.survey_table.rowCount()):
                for column in range(4, 10):
                    self.survey_table.setItem(index, column, QTableWidgetItem(""))
            for record in records:
                if record["tvd"] is not None:
                    self.update_row_calculations(record["_ui_row"], *(record[k] for k in DERIVED_FIELDS))
            self.highlight_calculated_cells()
            if issues:
                QMessageBox.warning(self, "Survey review", "\n".join(f"Row {r['row']}: {r['reason']}" for r in issues))
            elif not records:
                QMessageBox.warning(self, "Survey review", "No measured survey stations supplied")
            return records
        except Exception as exc:
            logger.exception("Trajectory calculation failed")
            QMessageBox.critical(self, "Survey SYSTEM_ERROR", str(exc))
            return []

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
                if item and item.text():
                    val = self._optional_float(item.text())
                    if val is not None and val != 0.0:
                        item.setBackground(QColor(220, 255, 220))
                        item.setToolTip("Calculated using Minimum Curvature Method")

    @staticmethod
    def _optional_float(text):
        """Parse a table cell into float, or None for blank/'None'/garbage.

        Survey derived columns (tvd/north/east/vs/hd/dls) are nullable and
        must round-trip NULL from DB -> blank cell -> NULL, instead of the
        literal string "None" crashing float() on save.
        """
        if text is None:
            return None
        s = str(text).strip()
        if s == "" or s.lower() == "none":
            return None
        try:
            return float(s)
        except (TypeError, ValueError):
            return None
    
    @editor_saved()
    def save_data(self):
        if not self.current_well_id:
            QMessageBox.warning(self, "Survey", "Select a well before saving surveys")
            return False
        rows = []
        keys = ("md", "inc", "azi", "tvd", "north", "east", "vs", "hd", "dls", "tool", "remarks")
        for row in range(self.survey_table.rowCount()):
            record = {key: self.survey_table.item(row, col).text() if self.survey_table.item(row, col) else None
                      for col, key in enumerate(keys, 1)}
            if not any(record.values()):
                continue
            record.update(well_id=self.current_well_id, report_id=self.current_report_id,
                          section_id=getattr(self, "current_section_id", None), _source_location={"row": row + 1, "table": "Survey UI"})
            id_item = self.survey_table.item(row, 0)
            if id_item and id_item.text().strip():
                record["id"] = int(id_item.text())
            rows.append(record)
        try:
            result = self.db_manager.save_survey_records(rows, replace_scope=(self.current_well_id, self.current_report_id))
            self.last_save_result = result
            from core.save_outcome import SaveOutcome, SaveIssue
            self.last_save_outcome = SaveOutcome(saved=result["accepted"], issues=[
                SaveIssue("Survey", r["reason"], status=r.get("status", "REVIEW_REQUIRED"), row=r.get("row"), field=r.get("field", ""))
                for r in result["review_items"]])
            if result["review_items"]:
                QMessageBox.warning(self, "Survey review", f"Saved {result['accepted']}; rejected {result['rejected']}; calculated {result['calculated']}.\n" +
                                    "\n".join(f"Row {r['row']}: {r['reason']}" for r in result["review_items"]))
            if not result["rejected"]:
                self.load_data()
                parent = self.parentWidget()
                # The owner also refreshes plots on report selection; an
                # explicit save must refresh the sibling plot tab as well.
                while parent is not None:
                    if hasattr(parent, "plot_tab"):
                        parent.plot_tab.load_for_report(self.current_report_id)
                        break
                    parent = parent.parentWidget()
            return result["rejected"] == 0
        except Exception as exc:
            logger.exception("Survey persistence/calculation failure")
            QMessageBox.critical(self, "Survey system error", str(exc))
            return False

    @editor_loaded()
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
                # NULL derived values display as blank, never as "None"
                self.survey_table.setItem(row, 0, QTableWidgetItem(str(point['id'])))
                self.survey_table.setItem(row, 1, QTableWidgetItem(str(point['md'])))
                self.survey_table.setItem(row, 2, QTableWidgetItem('' if point['inc'] is None else str(point['inc'])))
                self.survey_table.setItem(row, 3, QTableWidgetItem('' if point['azi'] is None else str(point['azi'])))
                self.survey_table.setItem(row, 4, QTableWidgetItem("" if point['tvd'] is None else str(point['tvd'])))
                self.survey_table.setItem(row, 5, QTableWidgetItem("" if point['north'] is None else str(point['north'])))
                self.survey_table.setItem(row, 6, QTableWidgetItem("" if point['east'] is None else str(point['east'])))
                self.survey_table.setItem(row, 7, QTableWidgetItem("" if point['vs'] is None else str(point['vs'])))
                self.survey_table.setItem(row, 8, QTableWidgetItem("" if point['hd'] is None else str(point['hd'])))
                self.survey_table.setItem(row, 9, QTableWidgetItem("" if point['dls'] is None else str(point['dls'])))
                self.survey_table.setItem(row, 10, QTableWidgetItem(point['tool'] or ''))
                self.survey_table.setItem(row, 11, QTableWidgetItem(point['remarks'] or ''))
    
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
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        self.figure_3d = Figure()
        self.canvas_3d = FigureCanvasQTAgg(self.figure_3d)
        self.axes_3d = self.figure_3d.add_subplot(111, projection="3d")
        self.plot_3d_layout.addWidget(self.canvas_3d)
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
        from core.survey_records import plot_series
        if survey_data is None and self.db_manager and self.current_report_id:
            survey_data = self.db_manager.load_survey_points(report_id=self.current_report_id)
        series = plot_series(survey_data or [])
        self.clear_plots()
        if not series["md"]:
            self.plot_3d_label.setText("No complete calculated survey stations. Supply missing MD/inclination/azimuth.")
            return
        east, north, tvd, hd = (series[k] for k in ("east", "north", "tvd", "hd"))
        if self.plot_2d_plan is not None:
            self.plot_2d_plan.plot(east, north, pen=pg.mkPen('b', width=2), symbol='o')
            self.plot_2d_side.plot(hd, tvd, pen=pg.mkPen('r', width=2), symbol='s')
            self.plot_2d_side.invertY(True)
        if hasattr(self, "axes_3d"):
            from core.trajectory_plot import draw_trajectory_3d
            draw_trajectory_3d(self.axes_3d, survey_data or [])
            self.canvas_3d.draw_idle()
        self.plot_3d_label.setText(f"Measured survey stations: {len(tvd)}")
        self.plots = {"2d_plan": {"east": east, "north": north},
                      "2d_side": {"hd": hd, "tvd": tvd}, "3d": series}

    def save_plot(self):
        if not self.current_report_id:
            QMessageBox.warning(self, "Trajectory plot", "Select a daily report before saving a plot")
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
        # Rebuild from persisted surveys; saved presentation snapshots are not
        # an authoritative second trajectory and may be stale after edits.
        self.plot_trajectory()

    def clear_plots(self):
        for plot in (self.plot_2d_plan, self.plot_2d_side):
            if plot is not None:
                plot.clear()
        if hasattr(self, "axes_3d"):
            self.axes_3d.clear()
            self.canvas_3d.draw_idle()
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
        self.configure_save_tracking()
    
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
        from core.save_outcome import save_all
        steps = []
        if self.trip_sheet_tab:
            steps.append(("Trip Sheet", self.trip_sheet_tab.save_data))
        if self.survey_data_tab:
            steps.append(("Survey", self.survey_data_tab.save_data))
        self.last_save_outcome = save_all(steps)
        if self.plot_tab and self.current_report_id:
            self.plot_tab.load_for_report(self.current_report_id)
        (self.show_success if self.last_save_outcome else self.show_error)(self.last_save_outcome.summary())
        return bool(self.last_save_outcome)

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