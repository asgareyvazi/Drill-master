"""
Planning Widget - Comprehensive planning module for drilling operations (بازنویسی کامل)
"""

import sys
import os
from datetime import datetime, date, timedelta, timezone
import random
import json
import logging
import numpy as np

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtCharts import *

from sqlalchemy import func
from core.database import (
    DatabaseManager, TimeLog24H, DailyReport, PlannedActivity, Section, WellPlan,
    DrillingParameters, MudReport
)
from core.managers import (
    StatusBarManager, AutoSaveManager, ShortcutManager,
    TableManager, TableButtonManager, ExportManager
)
from core.base_tab import DrillTabBase
from core.selection_manager import SelectionManager
from dialogs.planning_dialog import WellPlanDialog
from core.common_widgets import safe_replace_chart
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

from ui.helper import make_scrollable
logger = logging.getLogger(__name__)

# Try to import QtCharts for charts
try:
    from PySide6.QtCharts import QChart, QChartView, QLineSeries, QScatterSeries, QValueAxis, QDateTimeAxis
    CHARTS_AVAILABLE = True
except ImportError:
    CHARTS_AVAILABLE = False
    logger.warning("QtCharts not available. Charts will be disabled.")

# ==================== Seven Days Lookahead Tab ====================
class SevenDaysLookaheadTab(QWidget):
    def __init__(self, db_manager=None, parent_widget=None):
        super().__init__()
        self.db = db_manager
        self.parent_widget = parent_widget
        self.current_well_id = None
        self.current_section_id = None
        self.current_report_id = None
        self.status_manager = StatusBarManager()
        self.init_ui()
        self.setup_connections()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        title_label = QLabel("📅 Seven Days Lookahead Planning")
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        header_layout.addWidget(title_label)

        self.report_combo = QComboBox()
        self.report_combo.setMinimumWidth(150)
        header_layout.addWidget(QLabel("Report:"))
        header_layout.addWidget(self.report_combo)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Table
        self.lookahead_table = QTableWidget(7, 6)
        self.lookahead_table.setHorizontalHeaderLabels([
            "Day", "Date", "Activity", "Tools", "Responsible", "Remarks"
        ])
        self.lookahead_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.lookahead_table.setAlternatingRowColors(True)
        for i in range(7):
            day_date = QDate.currentDate().addDays(i)
            self.lookahead_table.setItem(i, 0, QTableWidgetItem(["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][i]))
            self.lookahead_table.setItem(i, 1, QTableWidgetItem(day_date.toString("yyyy-MM-dd")))
            self.lookahead_table.setItem(i, 2, QTableWidgetItem(""))
            self.lookahead_table.setItem(i, 3, QTableWidgetItem(""))
            self.lookahead_table.setItem(i, 4, QTableWidgetItem(""))
            self.lookahead_table.setItem(i, 5, QTableWidgetItem(""))
        main_layout.addWidget(self.lookahead_table)

        # Buttons
        button_layout = QHBoxLayout()
        self.fill_week_btn = QPushButton("📋 Fill Week Plan")
        self.fill_week_btn.clicked.connect(self.fill_week_plan)
        self.copy_prev_btn = QPushButton("📋 Copy Previous Week")
        self.copy_prev_btn.clicked.connect(self.copy_previous_week)
        self.add_row_btn = QPushButton("➕ Add Row")
        self.add_row_btn.clicked.connect(self.add_row)
        self.delete_row_btn = QPushButton("➖ Delete Row")
        self.delete_row_btn.clicked.connect(self.delete_row)
        self.export_csv_btn = QPushButton("📤 Export CSV")
        self.export_csv_btn.clicked.connect(lambda: self.export_plan("csv"))
        self.export_excel_btn = QPushButton("📤 Export Excel")
        self.export_excel_btn.clicked.connect(lambda: self.export_plan("excel"))
        self.export_pdf_btn = QPushButton("📤 Export PDF")
        self.export_pdf_btn.clicked.connect(lambda: self.export_plan("pdf"))
        self.save_btn = QPushButton("💾 Save Plan")
        self.save_btn.clicked.connect(self.save_plan)
        self.save_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        for btn in [self.fill_week_btn, self.copy_prev_btn, self.add_row_btn, self.delete_row_btn,
                    self.export_csv_btn, self.export_excel_btn, self.export_pdf_btn, self.save_btn]:
            button_layout.addWidget(btn)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #666; font-style: italic;")
        main_layout.addWidget(self.status_label)

        self.table_manager = TableManager(self.lookahead_table, self)
        self.table_manager.set_alternating_row_colors(True)

    def setup_connections(self):
        self.report_combo.currentIndexChanged.connect(self.on_report_changed)

    def set_current_well(self, well_id):
        self.current_well_id = well_id
        if self.current_well_id and self.current_section_id:
            self.load_reports(self.current_well_id, self.current_section_id)

    def set_current_section(self, section_id):
        self.current_section_id = section_id
        if self.current_well_id and self.current_section_id:
            self.load_reports(self.current_well_id, self.current_section_id)

    def set_current_report(self, report_id, report_date=None):
        self.current_report_id = report_id
        if report_id:
            self.load_lookahead_plan()

    def load_reports(self, well_id, section_id):
        self.report_combo.blockSignals(True)
        self.report_combo.clear()
        self.report_combo.addItem("-- Select Report --", None)
        if self.db and well_id and section_id:
            reports = self.db.get_daily_reports_by_section(section_id)
            for report in reports:
                date_str = str(report.get('report_date', ''))
                self.report_combo.addItem(
                    f"Report #{report.get('report_number', '?')} - {date_str}", report['id']
                )
        self.report_combo.blockSignals(False)

    def on_report_changed(self, index):
        report_id = self.report_combo.currentData()
        if report_id and report_id != self.current_report_id:
            self.current_report_id = report_id
            self.load_lookahead_plan()

    def load_lookahead_plan(self):
        if not self.db or not self.current_report_id:
            return
        plans = self.db.get_seven_days_lookahead(report_id=self.current_report_id)
        for i in range(self.lookahead_table.rowCount()):
            for j in range(2, 6):
                self.lookahead_table.setItem(i, j, QTableWidgetItem(""))
        for plan in plans:
            day_num = plan.get("day_number", 1) - 1
            if 0 <= day_num < self.lookahead_table.rowCount():
                self.lookahead_table.setItem(day_num, 2, QTableWidgetItem(plan.get("activity", "")))
                self.lookahead_table.setItem(day_num, 3, QTableWidgetItem(plan.get("tools", "")))
                self.lookahead_table.setItem(day_num, 4, QTableWidgetItem(plan.get("responsible", "")))
                self.lookahead_table.setItem(day_num, 5, QTableWidgetItem(plan.get("remarks", "")))
        self.status_label.setText(f"Loaded {len(plans)} plan items")

    def fill_week_plan(self):
        activities = ["Drilling 8-1/2\" section", "Drilling 12-1/4\" section", "Tripping Operations",
                      "Casing Operations", "Cementing Operations", "Wireline Logging", "Well Testing"]
        tools = ["PDC Bit, MWD, Motors", "Tricone Bit, Stabilizers", "Elevators, Tongs",
                 "Casing, Cement", "Cement Pump", "Wireline Tools", "Test Separator"]
        responsible = ["John Smith - Driller", "Mike Johnson - Tool Pusher", "Sarah Williams - Engineer",
                       "David Brown - Supervisor", "Robert Wilson - Company Man", "Wireline Crew", "Test Engineer"]
        remarks = ["Monitor ECD and torque", "Check hole cleaning", "Inspect pipe for wear",
                   "Centralize casing properly", "Monitor cement returns", "Calibrate tools before run",
                   "Monitor flow rates"]
        for i in range(7):
            day_date = QDate.currentDate().addDays(i)
            self.lookahead_table.setItem(i, 1, QTableWidgetItem(day_date.toString("yyyy-MM-dd")))
            self.lookahead_table.setItem(i, 2, QTableWidgetItem(activities[i % len(activities)]))
            self.lookahead_table.setItem(i, 3, QTableWidgetItem(tools[i % len(tools)]))
            self.lookahead_table.setItem(i, 4, QTableWidgetItem(responsible[i % len(responsible)]))
            self.lookahead_table.setItem(i, 5, QTableWidgetItem(remarks[i % len(remarks)]))
        self.status_label.setText("Week plan filled with suggested activities")

    def copy_previous_week(self):
        reply = QMessageBox.question(self, "Copy Previous Week", "Overwrite current plan?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.status_label.setText("Previous week data copied (simulated)")

    def add_row(self):
        self.table_manager.add_row([""] * self.lookahead_table.columnCount())

    def delete_row(self):
        self.table_manager.delete_row()

    def export_plan(self, format_type):
        export_manager = ExportManager(self)
        export_manager.export_table_with_dialog(self.lookahead_table, f"lookahead_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

    def save_plan(self):
        if not self.db or not self.current_report_id:
            self.status_label.setText("No report selected")
            return
        
        if not self.current_well_id:
            self.status_label.setText("No well selected")
            return
        
        plans = []
        today = QDate.currentDate()
        
        for i in range(self.lookahead_table.rowCount()):
            # دریافت آیتم‌ها با بررسی None
            activity_item = self.lookahead_table.item(i, 2)
            tools_item = self.lookahead_table.item(i, 3)
            responsible_item = self.lookahead_table.item(i, 4)
            remarks_item = self.lookahead_table.item(i, 5)
            
            plan_data = {
                "well_id": self.current_well_id,
                "section_id": self.current_section_id,
                "report_id": self.current_report_id,
                "plan_date": today.addDays(i).toPython(),  # تبدیل به Python date
                "day_number": i + 1,
                "activity": activity_item.text() if activity_item else "",
                "tools": tools_item.text() if tools_item else "",
                "responsible": responsible_item.text() if responsible_item else "",
                "remarks": remarks_item.text() if remarks_item else "",
                "status": "Planned",
                "priority": "Normal",
                "progress_percentage": 0,
                "created_by": None
            }
            plans.append(plan_data)
        
        saved = 0
        errors = []
        
        for plan in plans:
            try:
                if self.db.save_seven_days_lookahead(plan):
                    saved += 1
                else:
                    errors.append(f"Day {plan['day_number']}: {plan['activity']}")
            except Exception as e:
                errors.append(f"Day {plan['day_number']}: {str(e)}")
        
        if saved > 0:
            self.status_label.setText(f"Saved {saved} of {len(plans)} items")
            self.status_manager.show_success("SevenDaysLookaheadTab", f"Saved {saved} plan items")
            if errors:
                self.status_manager.show_warning("SevenDaysLookaheadTab", f"Failed to save {len(errors)} items")
        else:
            self.status_label.setText("Failed to save plan items")
            self.status_manager.show_error("SevenDaysLookaheadTab", "No items were saved")
            
@make_scrollable
class NPTReportTab(QWidget):
    def __init__(self, db_manager=None, parent_widget=None):
        super().__init__()
        self.db = db_manager
        self.parent_widget = parent_widget
        self.current_well_id = None
        self.current_report_id = None
        self.current_section_id = None  
        self.init_ui()
        self.setup_connections()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # ========== Header ==========
        header_layout = QHBoxLayout()
        title_label = QLabel("⏱️ Non-Productive Time (NPT) Report")
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        header_layout.addWidget(title_label)

        header_layout.addWidget(QLabel("From:"))
        self.from_date = QDateEdit()
        self.from_date.setDate(QDate.currentDate().addDays(-30))
        self.from_date.setCalendarPopup(True)
        header_layout.addWidget(self.from_date)
        header_layout.addWidget(QLabel("To:"))
        self.to_date = QDateEdit()
        self.to_date.setDate(QDate.currentDate())
        self.to_date.setCalendarPopup(True)
        header_layout.addWidget(self.to_date)
        self.refresh_btn = QPushButton("🔄 Refresh")
        header_layout.addWidget(self.refresh_btn)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # ========== Statistics Cards ==========
        stats_group = QGroupBox("📊 NPT Statistics")
        stats_layout = QGridLayout()
        self.npt_total_card = self.create_stat_card("⏱️", "Total NPT", "0.0", "hours", "#e74c3c")
        self.npt_percent_card = self.create_stat_card("📊", "NPT %", "0.0", "%", "#f39c12")
        self.npt_daily_card = self.create_stat_card("📅", "Daily Avg", "0.0", "hours/day", "#3498db")
        self.npt_category_card = self.create_stat_card("🔥", "Top Category", "-", "category", "#9b59b6")
        stats_layout.addWidget(self.npt_total_card, 0, 0)
        stats_layout.addWidget(self.npt_percent_card, 0, 1)
        stats_layout.addWidget(self.npt_daily_card, 1, 0)
        stats_layout.addWidget(self.npt_category_card, 1, 1)
        stats_group.setLayout(stats_layout)
        main_layout.addWidget(stats_group)

        # ========== Grid of Bar Charts ==========
        charts_group = QGroupBox("📈 NPT Breakdown - Bar Charts")
        charts_layout = QGridLayout()
        charts_layout.setSpacing(15)
        charts_layout.setContentsMargins(10, 10, 10, 10)

        self.chart_keys = [
            "contractor", "type", "category", "failure", "geological", "rig_repair", "waiting"
        ]
        self.chart_titles = {
            "contractor": "NPT By Contractor",
            "type": "NPT By Type (Main Code)",
            "category": "NPT By Category (Phase)",
            "failure": "NPT By Failure (F)",
            "geological": "NPT By Geological Trouble (T)",
            "rig_repair": "NPT By Rig Repair (RR)",
            "waiting": "NPT By Waiting (W)"
        }
        positions = [(0,0), (0,1), (0,2), (1,0), (1,1), (1,2), (2,1)]
        self.chart_widgets = {}
        for key, (row, col) in zip(self.chart_keys, positions):
            container = QWidget()
            container.setMinimumHeight(320)
            container.setMinimumWidth(350)
            container.setStyleSheet("background: #1e1e2e; border-radius: 8px;")
            inner = QVBoxLayout(container)
            label = QLabel(self.chart_titles[key])
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color: white; font-weight: bold; font-size: 12px; padding: 5px;")
            inner.addWidget(label)
            placeholder = QLabel("Loading...")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: gray; font-size: 14px;")
            inner.addWidget(placeholder)
            self.chart_widgets[key] = {"container": container, "label": placeholder, "title": self.chart_titles[key]}
            charts_layout.addWidget(container, row, col)
        charts_group.setLayout(charts_layout)
        main_layout.addWidget(charts_group)

        # ========== Main NPT Table (Details) ==========
        self.npt_table = QTableWidget(0, 8)
        self.npt_table.setHorizontalHeaderLabels([
            "Date", "From", "To", "Duration", "Top Cat", "Full Code", "Sub Code", "Description"
        ])
        self.npt_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.npt_table.setMinimumHeight(400)
        main_layout.addWidget(self.npt_table)

        # Export button
        button_layout = QHBoxLayout()
        self.export_btn = QPushButton("📤 Export NPT Data")
        self.export_btn.clicked.connect(self.export_npt_data)
        button_layout.addWidget(self.export_btn)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        self.table_manager = TableManager(self.npt_table, self)

    # ----- Stat Card Helpers (بدون تغییر) -----
    def create_stat_card(self, icon, title, value, unit, color):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {color}20;
                border-left: 4px solid {color};
                border-radius: 6px;
                padding: 10px;
                margin: 5px;
            }}
        """)
        layout = QVBoxLayout(card)
        title_label = QLabel(f"{icon} {title}")
        title_label.setStyleSheet("font-size: 13px; color: #7f8c8d; font-weight: bold;")
        layout.addWidget(title_label)
        value_label = QLabel(f"<b>{value}</b> {unit}")
        value_label.setStyleSheet(f"font-size: 18px; color: {color};")
        layout.addWidget(value_label)
        card.value_label = value_label
        return card

    def update_stat_card_value(self, card, new_value):
        if hasattr(card, 'value_label'):
            current_text = card.value_label.text()
            if ' ' in current_text:
                unit = current_text.split(' ')[-1]
                card.value_label.setText(f"<b>{new_value}</b> {unit}")
            else:
                card.value_label.setText(f"<b>{new_value}</b>")

    # ----- Connections -----
    def setup_connections(self):
        self.refresh_btn.clicked.connect(self.load_npt_data)
        self.from_date.dateChanged.connect(self.load_npt_data)
        self.to_date.dateChanged.connect(self.load_npt_data)

    def set_current_well(self, well_id):
        """تنظیم چاه جاری و بارگذاری داده‌ها"""
        self.current_well_id = well_id
        if well_id:
            self.update_npt_data()
        else:
            self.npt_table.setRowCount(0)
            self.update_stat_card_value(self.npt_total_card, "0.0")
            self.update_stat_card_value(self.npt_percent_card, "0.0")
            self.update_stat_card_value(self.npt_daily_card, "0.0")
            self.update_stat_card_value(self.npt_category_card, "-")
            
    def set_current_report(self, report_id, report_date=None):
        self.current_report_id = report_id
        if self.current_well_id:
            self.update_npt_data()

    def set_current_section(self, section_id):
        """تنظیم سکشن جاری و به‌روزرسانی داده‌ها"""
        self.current_section_id = section_id
        if self.current_well_id:
            self.update_npt_data()
            
    # ----- Data Fetching (بدون تغییر) -----
    def get_npt_data(self, session, report_id=None, section_id=None):
        well_id = self.current_well_id
        if not well_id:
            return {'entries': [], 'categories': {}, 'total_npt': 0, 'npt_percentage': 0, 'total_hours': 1}
        query = session.query(TimeLog24H, DailyReport).join(
            DailyReport, TimeLog24H.report_id == DailyReport.id
        ).filter(
            DailyReport.well_id == well_id,
            TimeLog24H.is_npt == True
        )

        if section_id:
            query = query.filter(DailyReport.section_id == section_id)
        npt_rows = query.order_by(DailyReport.report_date, TimeLog24H.time_from).all()

        entries = []
        categories = {}
        total_npt = 0.0
        for log, rep in npt_rows:
            h = log.duration or 0
            cat = log.main_code or "Unknown"
            categories[cat] = categories.get(cat, 0) + h
            total_npt += h
            entries.append({
                'date': rep.report_date,
                'from': log.time_from,
                'to': log.time_to,
                'hours': h,
                'category': cat,
                'description': log.activity_description or "",
                'sub_category': log.sub_code or "",
                'contractor': log.contractor or "Unknown",
                'main_phase': log.main_phase or "Unknown"
            })
        total_hours_query = session.query(func.sum(TimeLog24H.duration)).join(
            DailyReport, TimeLog24H.report_id == DailyReport.id
        ).filter(DailyReport.well_id == well_id)
        if report_id:
            total_hours_query = total_hours_query.filter(DailyReport.id == report_id)
        total_hours = total_hours_query.scalar() or 1
        npt_pct = (total_npt / total_hours * 100) if total_hours > 0 else 0
        return {'entries': entries, 'categories': categories, 'total_npt': total_npt,
                'npt_percentage': npt_pct, 'total_hours': total_hours}

    def update_npt_data(self):
        if not self.current_well_id:
            return
        session = self.db.create_session()
        try:
            data = self.get_npt_data(
                session,
                report_id=self.current_report_id,
                section_id=self.current_section_id 
            )
            # بررسی کنیم که ویجت‌ها هنوز وجود دارند
            if not self.isVisible():
                return
            self.display_npt_data(data)
        except Exception as e:
            logger.error(f"Error in update_npt_data: {e}")
        finally:
            session.close()


    # ----- Display -----
    def display_npt_data(self, data):
        """نمایش داده‌های NPT با بررسی None"""
        self.npt_table.setRowCount(len(data['entries']))
        for i, e in enumerate(data['entries']):
            self.npt_table.setItem(i, 0, QTableWidgetItem(str(e['date'] or '')))
            
            # رفع: بررسی None برای time objects
            time_from = e.get('from')
            time_to = e.get('to')
            
            if time_from and hasattr(time_from, 'strftime'):
                self.npt_table.setItem(i, 1, QTableWidgetItem(time_from.strftime("%H:%M")))
            else:
                self.npt_table.setItem(i, 1, QTableWidgetItem(str(time_from or '')))
            
            if time_to and hasattr(time_to, 'strftime'):
                self.npt_table.setItem(i, 2, QTableWidgetItem(time_to.strftime("%H:%M")))
            else:
                self.npt_table.setItem(i, 2, QTableWidgetItem(str(time_to or '')))
            
            self.npt_table.setItem(i, 3, QTableWidgetItem(f"{e.get('hours', 0):.2f}"))
            self.npt_table.setItem(i, 4, QTableWidgetItem(e.get('category', '')))
            self.npt_table.setItem(i, 5, QTableWidgetItem(e.get('category', '')))
            self.npt_table.setItem(i, 6, QTableWidgetItem(e.get('sub_category', '')))
            self.npt_table.setItem(i, 7, QTableWidgetItem(e.get('description', '')))

        # Cards
        self.update_stat_card_value(self.npt_total_card, f"{data['total_npt']:.1f}")
        self.update_stat_card_value(self.npt_percent_card, f"{data['npt_percentage']:.1f}")
        
        unique_dates = len(set(e['date'] for e in data['entries'] if e.get('date')))
        daily_avg = data['total_npt'] / unique_dates if unique_dates > 0 else 0
        self.update_stat_card_value(self.npt_daily_card, f"{daily_avg:.1f}")
        
        top_cat = max(data['categories'], key=data['categories'].get) if data['categories'] else "None"
        self.update_stat_card_value(self.npt_category_card, top_cat)

        self.draw_all_bar_charts(data['entries'])

    def collect_category_data_prefix(self, entries, prefixes, group_by_field='description', fallback_field='sub_category', default_label='General'):
        """
        جمع‌آوری داده برای دسته‌هایی که main_code با یکی از prefixes شروع می‌شود.
        group_by_field اولویت اول، fallback_field دوم.
        """
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        prefixes = [p.upper() for p in prefixes]

        result = {}
        for e in entries:
            main_code = e.get('category', '').upper().strip()
            # بررسی اینکه آیا main_code با یکی از prefixes شروع می‌شود
            matched = any(main_code.startswith(p) for p in prefixes)
            if not matched:
                continue
            # گروه‌بندی: اول description، سپس sub_category، سپس default
            group_key = e.get(group_by_field, '')
            if not group_key or group_key.strip() == "":
                group_key = e.get(fallback_field, default_label)
            if not group_key or group_key.strip() == "":
                group_key = default_label
            group_key = group_key.strip()
            result[group_key] = result.get(group_key, 0) + e['hours']
        return result

    def draw_all_bar_charts(self, entries):
        # 1. Contractor (همه)
        contractor_data = {}
        for e in entries:
            cont = e.get('contractor', 'Unknown')
            contractor_data[cont] = contractor_data.get(cont, 0) + e['hours']
        self.draw_bar_chart(contractor_data, 'contractor')

        # 2. Type (بر اساس main_code کامل)
        type_data = {}
        for e in entries:
            cat = e.get('category', 'Unknown')
            type_data[cat] = type_data.get(cat, 0) + e['hours']
        self.draw_bar_chart(type_data, 'type')

        # 3. Category (بر اساس main_phase)
        phase_data = {}
        for e in entries:
            phase = e.get('main_phase', 'Unknown')
            phase_data[phase] = phase_data.get(phase, 0) + e['hours']
        self.draw_bar_chart(phase_data, 'category')

        # 4. Failure (هر main_code که با 'F' شروع شود)
        failure_data = self.collect_category_data_prefix(entries, 'F', 'description', 'sub_category', 'F-General')
        if not failure_data:
            failure_data = {"No Failure Data": 0}
        self.draw_bar_chart(failure_data, 'failure')

        # 5. Geological (شروع با 'T')
        geo_data = self.collect_category_data_prefix(entries, 'T', 'description', 'sub_category', 'T-General')
        if not geo_data:
            geo_data = {"No Geological Data": 0}
        self.draw_bar_chart(geo_data, 'geological')

        # 6. Rig Repair (شروع با 'RR')
        rr_data = self.collect_category_data_prefix(entries, 'RR', 'description', 'sub_category', 'RR-General')
        if not rr_data:
            rr_data = {"No Rig Repair Data": 0}
        self.draw_bar_chart(rr_data, 'rig_repair')

        # 7. Waiting (شروع با 'W')
        wait_data = self.collect_category_data_prefix(entries, 'W', 'description', 'sub_category', 'W-General')
        if not wait_data:
            wait_data = {"No Waiting Data": 0}
        self.draw_bar_chart(wait_data, 'waiting')
    

    def draw_bar_chart(self, data_dict, chart_key):
        """رسم نمودار میله‌ای افقی با پاک کردن کامل محتوای قبلی و بررسی صحت ویجت"""
        filtered = {k: v for k, v in data_dict.items() if v > 0}
        if not filtered:
            # بررسی کنیم که label هنوز وجود دارد
            if chart_key in self.chart_widgets and self.chart_widgets[chart_key]["label"]:
                self.chart_widgets[chart_key]["label"].setText(f"No data for {self.chart_titles[chart_key]}")
            return


        try:
            sorted_items = sorted(filtered.items(), key=lambda x: x[1], reverse=True)[:10]
            labels = [item[0] for item in sorted_items]
            values = [item[1] for item in sorted_items]

            fig, ax = plt.subplots(figsize=(5, 4), facecolor='#1e1e2e')
            ax.set_facecolor('#1e1e2e')
            y_pos = range(len(labels))
            bars = ax.barh(y_pos, values, color=plt.cm.tab20(range(len(labels))), edgecolor='white', linewidth=0.5)
            ax.set_yticks(y_pos)
            ax.set_yticklabels(labels, color='white', fontsize=8)
            ax.set_xlabel("Hours", color='white', fontsize=10)
            ax.set_title(self.chart_titles[chart_key], color='white', fontsize=11)
            ax.tick_params(axis='x', colors='white')
            for i, (bar, val) in enumerate(zip(bars, values)):
                ax.text(val + 0.5, i, f"{val:.1f}", va='center', color='white', fontsize=8)
            ax.grid(axis='x', alpha=0.3, color='gray')
            fig.tight_layout()

            canvas = FigureCanvas(fig)
            container = self.chart_widgets[chart_key]["container"]
            if not container or container.isHidden():
                return
            # نگه‌داشتن عنوان (اولین ویجت)
            layout = container.layout()
            if layout is None:
                return
            title_widget = layout.itemAt(0).widget() if layout.count() > 0 else None
            while layout.count() > 1:
                item = layout.takeAt(1)
                if item and item.widget():
                    item.widget().setParent(None)
                    item.widget().deleteLater()
            layout.addWidget(canvas)
            plt.close(fig)

        except Exception as e:
            print(f"Error drawing bar chart: {e}")
            if chart_key in self.chart_widgets and self.chart_widgets[chart_key]["label"]:
                self.chart_widgets[chart_key]["label"].setText(f"Chart error: {str(e)[:30]}")
                
    def load_npt_data(self):
        self.update_npt_data()

    def export_npt_data(self):
        export_manager = ExportManager(self)
        export_manager.export_table_with_dialog(self.npt_table, "npt_data")

    def export_charts_to_file(self, filename=None):
        """اکسپورت نمودارها به PDF/PNG"""
        if not filename:
            from PySide6.QtWidgets import QFileDialog
            filename, _ = QFileDialog.getSaveFileName(
                self, "Export Charts",
                f"planning_charts_{datetime.now().strftime('%Y%m%d')}.png",
                "PNG (*.png);;PDF (*.pdf)"
            )
        if not filename:
            return
        
        try:
            # Grab the widget as image
            from PySide6.QtGui import QPixmap
            
            if filename.endswith('.pdf'):
                from PySide6.QtPrintSupport import QPrinter
                from PySide6.QtGui import QPainter
                
                printer = QPrinter(QPrinter.HighResolution)
                printer.setOutputFormat(QPrinter.PdfFormat)
                printer.setOutputFileName(filename)
                
                painter = QPainter(printer)
                self.render(painter)
                painter.end()
            else:
                pixmap = self.grab()
                pixmap.save(filename)
            
            logger.info(f"Charts exported to: {filename}")
        except Exception as e:
            logger.error(f"Chart export error: {e}")
            
@make_scrollable
# ==================== Code Management Tab (Read-only – aggregated from time logs) ====================
class CodeManagementTab(QWidget):
    def __init__(self, db_manager=None, parent_widget=None):
        super().__init__()
        self.db = db_manager
        self.parent_widget = parent_widget
        self.current_well_id = None
        self.current_report_id = None
        self.current_section_id = None         
        self.init_ui()
        self.setup_connections()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        title_label = QLabel("🏷️ Activity Code Usage (from Daily Reports)")
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        header_layout.addWidget(title_label)

        self.refresh_btn = QPushButton("🔄 Refresh")
        header_layout.addWidget(self.refresh_btn)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # ========== Statistics Cards ==========
        stats_group = QGroupBox("📊 Code Statistics")
        stats_layout = QGridLayout()
        stats_layout.addWidget(QLabel("Total Codes Used:"), 0, 0)
        self.total_codes = QLabel("0")
        self.total_codes.setFont(QFont("Arial", 12, QFont.Bold))
        stats_layout.addWidget(self.total_codes, 0, 1)
        stats_layout.addWidget(QLabel("Main Phases:"), 0, 2)
        self.total_phases = QLabel("0")
        self.total_phases.setFont(QFont("Arial", 12, QFont.Bold))
        stats_layout.addWidget(self.total_phases, 0, 3)
        stats_layout.addWidget(QLabel("Most Used Code:"), 1, 0)
        self.most_used_code = QLabel("None")
        stats_layout.addWidget(self.most_used_code, 1, 1)
        stats_layout.addWidget(QLabel("Total Hours:"), 1, 2)
        self.total_hours = QLabel("0.0")
        self.total_hours.setFont(QFont("Arial", 12, QFont.Bold))
        stats_layout.addWidget(self.total_hours, 1, 3)
        stats_group.setLayout(stats_layout)
        main_layout.addWidget(stats_group)

        # ========== Main Code Table ==========
        self.code_table = QTableWidget(0, 6)
        self.code_table.setHorizontalHeaderLabels([
            "Main Phase", "Main Code", "Sub Code", "Code Name", "Productive", "Hours"
        ])
        self.code_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.code_table.setAlternatingRowColors(True)
        self.code_table.setMaximumHeight(350)
        main_layout.addWidget(self.code_table)

        # ========== Charts Section ==========
        charts_group = QGroupBox("📊 Activity Breakdown Charts")
        charts_layout = QGridLayout()
        charts_layout.setSpacing(10)

        # Chart 1: Main Code Hours (Bar)
        self.main_code_chart = QWidget()
        self.main_code_chart.setMinimumHeight(300)
        self.main_code_chart.setStyleSheet("background: #1e1e2e; border-radius: 8px;")
        charts_layout.addWidget(QLabel("📊 Hours by Main Code"), 0, 0)
        charts_layout.addWidget(self.main_code_chart, 1, 0)

        # Chart 2: Sub Code Hours (Bar)
        self.sub_code_chart = QWidget()
        self.sub_code_chart.setMinimumHeight(300)
        self.sub_code_chart.setStyleSheet("background: #1e1e2e; border-radius: 8px;")
        charts_layout.addWidget(QLabel("📊 Hours by Sub Code (Top 15)"), 0, 1)
        charts_layout.addWidget(self.sub_code_chart, 1, 1)

        # Chart 3: Productive vs NPT Pie
        self.productive_pie_chart = QWidget()
        self.productive_pie_chart.setMinimumHeight(300)
        self.productive_pie_chart.setStyleSheet("background: #1e1e2e; border-radius: 8px;")
        charts_layout.addWidget(QLabel("📊 Productive vs NPT"), 2, 0)
        charts_layout.addWidget(self.productive_pie_chart, 3, 0)

        # Chart 4: Status Distribution
        self.status_pie_widget = QWidget()
        self.status_pie_widget.setMinimumHeight(300)
        self.status_pie_widget.setStyleSheet("background: #1e1e2e; border-radius: 8px;")
        charts_layout.addWidget(QLabel("📊 Activity Status Distribution"), 2, 1)
        charts_layout.addWidget(self.status_pie_widget, 3, 1)

        charts_group.setLayout(charts_layout)
        main_layout.addWidget(charts_group)

        # ========== Status Summary Table ==========
        status_group = QGroupBox("📊 Status Summary")
        status_layout = QHBoxLayout()
        self.status_summary_table = QTableWidget(0, 3)
        self.status_summary_table.setHorizontalHeaderLabels(["Status", "Hours", "Percentage"])
        self.status_summary_table.setMaximumHeight(200)
        self.status_summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        status_layout.addWidget(self.status_summary_table)
        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group)

        # ========== Export ==========
        button_layout = QHBoxLayout()
        self.export_btn = QPushButton("📤 Export Codes")
        self.export_btn.clicked.connect(self.export_codes)
        button_layout.addWidget(self.export_btn)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        self.table_manager = TableManager(self.code_table, self)
        
    def setup_connections(self):
        self.refresh_btn.clicked.connect(self.load_codes)

    def set_current_well(self, well_id):
        """تنظیم چاه جاری و بارگذاری داده‌ها"""
        self.current_well_id = well_id
        if well_id:
            self.load_codes()
            self.load_status_distribution()
        else:
            self.code_table.setRowCount(0)
            self.status_summary_table.setRowCount(0)
            self.total_codes.setText("0")
            self.total_phases.setText("0")
            self.total_hours.setText("0.0")
            self.most_used_code.setText("None")
            
    def set_current_report(self, report_id, report_date=None):
        self.current_report_id = report_id
        if report_date:
            pass
        if self.current_well_id:
            self.load_codes()
        
    def set_current_section(self, section_id):
        """تنظیم سکشن جاری و بارگذاری داده‌ها"""
        self.current_section_id = section_id
        if self.current_well_id:
            self.load_codes()
            self.load_status_distribution()
            
    def load_codes(self):
        if not self.db or not self.current_well_id:
            return

        session = self.db.create_session()
        try:
            query = session.query(TimeLog24H).join(
                DailyReport, TimeLog24H.report_id == DailyReport.id
            ).filter(DailyReport.well_id == self.current_well_id)

            if self.current_section_id:
                query = query.filter(DailyReport.section_id == self.current_section_id)

            logs_24h = query.all()

            # ========== تجمیع بر اساس Main Code + Sub Code ==========
            agg = {}
            main_code_hours = {}
            sub_code_hours = {}
            total_productive = 0
            total_npt = 0

            for log in logs_24h:
                main_code = log.main_code or "Unknown"
                sub_code = log.sub_code or ""
                phase = log.main_phase or "General"
                duration = log.duration or 0
                is_npt = log.is_npt

                # کلید ترکیبی
                key = (phase, main_code, sub_code)
                if key not in agg:
                    agg[key] = {'hours': 0, 'productive_hours': 0, 'npt_hours': 0}
                agg[key]['hours'] += duration
                if is_npt:
                    agg[key]['npt_hours'] += duration
                    total_npt += duration
                else:
                    agg[key]['productive_hours'] += duration
                    total_productive += duration

                # تجمیع Main Code
                main_code_hours[main_code] = main_code_hours.get(main_code, 0) + duration

                # تجمیع Sub Code
                sub_key = f"{main_code} → {sub_code}" if sub_code else main_code
                sub_code_hours[sub_key] = sub_code_hours.get(sub_key, 0) + duration

            # ========== پر کردن جدول ==========
            self.code_table.setRowCount(0)
            total_hours = 0
            phases = set()

            sorted_agg = sorted(agg.items(), key=lambda x: x[1]['hours'], reverse=True)

            for (phase, main_code, sub_code), data in sorted_agg:
                row = self.code_table.rowCount()
                self.code_table.insertRow(row)
                self.code_table.setItem(row, 0, QTableWidgetItem(phase))
                self.code_table.setItem(row, 1, QTableWidgetItem(main_code))
                self.code_table.setItem(row, 2, QTableWidgetItem(sub_code))

                name = f"{main_code}" + (f" - {sub_code}" if sub_code else "")
                self.code_table.setItem(row, 3, QTableWidgetItem(name))

                total_code_hours = data['hours']
                productive_hours = data.get('productive_hours', 0)
                npt_hours = data.get('npt_hours', 0)

                if total_code_hours > 0:
                    productive_percent = (productive_hours / total_code_hours) * 100
                    if productive_percent >= 80:
                        productive_text = "✅ Productive"
                        productive_color = "#2ecc71"
                    elif productive_percent >= 50:
                        productive_text = "⚠️ Mixed"
                        productive_color = "#f39c12"
                    else:
                        productive_text = "❌ NPT"
                        productive_color = "#e74c3c"
                else:
                    productive_text = "N/A"
                    productive_color = "#95a5a6"

                productive_item = QTableWidgetItem(productive_text)
                productive_item.setForeground(QColor(productive_color))
                self.code_table.setItem(row, 4, productive_item)

                hours_item = QTableWidgetItem(f"{total_code_hours:.2f}")
                hours_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.code_table.setItem(row, 5, hours_item)

                total_hours += total_code_hours
                if phase:
                    phases.add(phase)

            # ========== آمار ==========
            self.total_codes.setText(str(len(agg)))
            self.total_phases.setText(str(len(phases)))
            self.total_hours.setText(f"{total_hours:.2f} hrs")

            if agg:
                most_used = max(agg.items(), key=lambda x: x[1]['hours'])
                name = f"{most_used[0][1]} ({most_used[0][2]})" if most_used[0][2] else most_used[0][1]
                self.most_used_code.setText(f"{name} ({most_used[1]['hours']:.1f} hrs)")
            else:
                self.most_used_code.setText("None")

            # ========== رسم نمودارها ==========
            self._draw_main_code_chart(main_code_hours)
            self._draw_sub_code_chart(sub_code_hours)
            self._draw_productive_pie(total_productive, total_npt)
            self.load_status_distribution()

        except Exception as e:
            logger.error(f"Error loading activity codes: {e}")
        finally:
            session.close()

    def _draw_main_code_chart(self, main_code_hours):
        """نمودار میله‌ای ساعات بر اساس Main Code"""
        filtered = {k: v for k, v in main_code_hours.items() if v > 0}
        if not filtered:
            return

        try:
            sorted_items = sorted(filtered.items(), key=lambda x: x[1], reverse=True)[:15]
            labels = [item[0][:25] for item in sorted_items]
            values = [item[1] for item in sorted_items]

            fig, ax = plt.subplots(figsize=(6, 4), facecolor='#1e1e2e')
            ax.set_facecolor('#1e1e2e')
            y_pos = range(len(labels))
            colors_list = plt.cm.tab20(range(len(labels)))
            bars = ax.barh(y_pos, values, color=colors_list, edgecolor='white', linewidth=0.5)
            ax.set_yticks(y_pos)
            ax.set_yticklabels(labels, color='white', fontsize=8)
            ax.set_xlabel("Hours", color='white', fontsize=10)
            ax.set_title("Cumulative Hours by Main Code", color='white', fontsize=11, fontweight='bold')
            ax.tick_params(axis='x', colors='white')
            for i, (bar, val) in enumerate(zip(bars, values)):
                ax.text(val + 0.3, i, f"{val:.1f}h", va='center', color='white', fontsize=8)
            ax.grid(axis='x', alpha=0.3, color='gray')
            fig.tight_layout()

            canvas = FigureCanvas(fig)
            safe_replace_chart(self.main_code_chart, canvas)
            plt.close(fig)

        except Exception as e:
            logger.error(f"Error drawing main code chart: {e}")

    def _draw_sub_code_chart(self, sub_code_hours):
        """نمودار میله‌ای ساعات بر اساس Sub Code"""
        filtered = {k: v for k, v in sub_code_hours.items() if v > 0}
        if not filtered:
            return

        try:
            sorted_items = sorted(filtered.items(), key=lambda x: x[1], reverse=True)[:15]
            labels = [item[0][:30] for item in sorted_items]
            values = [item[1] for item in sorted_items]

            fig, ax = plt.subplots(figsize=(6, 4), facecolor='#1e1e2e')
            ax.set_facecolor('#1e1e2e')
            y_pos = range(len(labels))
            colors_list = plt.cm.Set2(range(len(labels)))
            bars = ax.barh(y_pos, values, color=colors_list, edgecolor='white', linewidth=0.5)
            ax.set_yticks(y_pos)
            ax.set_yticklabels(labels, color='white', fontsize=7)
            ax.set_xlabel("Hours", color='white', fontsize=10)
            ax.set_title("Cumulative Hours by Sub Code (Top 15)", color='white', fontsize=11, fontweight='bold')
            ax.tick_params(axis='x', colors='white')
            for i, (bar, val) in enumerate(zip(bars, values)):
                ax.text(val + 0.2, i, f"{val:.1f}h", va='center', color='white', fontsize=7)
            ax.grid(axis='x', alpha=0.3, color='gray')
            fig.tight_layout()

            canvas = FigureCanvas(fig)
            safe_replace_chart(self.sub_code_chart, canvas)
            plt.close(fig)

        except Exception as e:
            logger.error(f"Error drawing sub code chart: {e}")

    def _draw_productive_pie(self, productive_hours, npt_hours):
        """نمودار دایره‌ای Productive vs NPT"""
        if productive_hours == 0 and npt_hours == 0:
            return

        try:
            fig, ax = plt.subplots(figsize=(5, 4), facecolor='#1e1e2e')
            ax.set_facecolor('#1e1e2e')

            labels = ['Productive', 'NPT']
            sizes = [productive_hours, npt_hours]
            colors = ['#2ecc71', '#e74c3c']
            explode = (0, 0.05)

            wedges, texts, autotexts = ax.pie(
                sizes, labels=labels, autopct='%1.1f%%',
                startangle=90, colors=colors, explode=explode,
                textprops={'color': 'white', 'fontsize': 11, 'fontweight': 'bold'},
                wedgeprops={'edgecolor': '#1e1e2e', 'linewidth': 2}
            )
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')

            total = productive_hours + npt_hours
            ax.set_title(
                f"Productive vs NPT\n(Total: {total:.1f} hrs)",
                color='white', fontsize=12, fontweight='bold'
            )
            fig.tight_layout()

            canvas = FigureCanvas(fig)
            safe_replace_chart(self.productive_pie_chart, canvas)
            plt.close(fig)

        except Exception as e:
            logger.error(f"Error drawing productive pie: {e}")
            
    def load_data(self):
        """بارگذاری داده‌ها (برای سازگاری با فراخوانی‌های عمومی)"""
        self.load_codes()
        
    def export_codes(self):
        export_manager = ExportManager(self)
        export_manager.export_table_with_dialog(self.code_table, "activity_codes")

    def load_status_distribution(self):
        """
        بارگذاری توزیع وضعیت‌ها فقط از TimeLog24H با فیلتر well, report, section
        و به‌روزرسانی جدول خلاصه وضعیت‌ها و نمودار دایره‌ای.
        """
        if not self.db or not self.current_well_id:
            return

        session = self.db.create_session()
        try:
            from core.database import TimeLog24H, DailyReport
            from sqlalchemy import func

            # ساخت کوئری پایه
            query = session.query(
                TimeLog24H.status,
                func.sum(TimeLog24H.duration).label('total')
            ).join(
                DailyReport, TimeLog24H.report_id == DailyReport.id
            ).filter(
                DailyReport.well_id == self.current_well_id
            )

            # فیلتر report_id (اگر وجود داشته باشد)
            if self.current_report_id:
                query = query.filter(DailyReport.id == self.current_report_id)

            # فیلتر section_id (اگر وجود داشته باشد)
            if self.current_section_id:
                query = query.filter(DailyReport.section_id == self.current_section_id)

            # گروه‌بندی و اجرا
            status_24h = query.group_by(TimeLog24H.status).all()

            status_stats = {}
            for status, total in status_24h:
                if status:
                    status_stats[status] = status_stats.get(status, 0) + (total or 0)

            # به‌روزرسانی جدول وضعیت‌ها (در صورت وجود متد)
            if hasattr(self, '_update_status_table'):
                self._update_status_table(status_stats)
            else:
                logger.warning("_update_status_table method not found")

            # رسم نمودار دایره‌ای وضعیت‌ها (در صورت وجود متد)
            if hasattr(self, '_draw_status_pie_chart'):
                self._draw_status_pie_chart(status_stats)
            else:
                logger.warning("_draw_status_pie_chart method not found")

        except Exception as e:
            logger.error(f"Error loading status distribution: {e}")
        finally:
            session.close()
            
    def _update_status_table(self, status_stats):
        """به‌روزرسانی جدول خلاصه وضعیت‌ها"""
        if not hasattr(self, 'status_summary_table'):
            return
        
        total_hours = sum(status_stats.values())
        if total_hours == 0:
            total_hours = 1
        
        sorted_status = sorted(status_stats.items(), key=lambda x: x[1], reverse=True)
        self.status_summary_table.setRowCount(len(sorted_status))
        
        color_map = {
            "Normal": "#2ecc71",
            "Delayed": "#f39c12",
            "Completed": "#3498db",
            "In Progress": "#9b59b6",
            "On Hold": "#e74c3c"
        }
        
        for i, (status, hours) in enumerate(sorted_status):
            days = hours / 24
            percentage = (hours / total_hours) * 100
            
            self.status_summary_table.setItem(i, 0, QTableWidgetItem(status))
            self.status_summary_table.setItem(i, 1, QTableWidgetItem(f"{days:.1f} days"))
            self.status_summary_table.setItem(i, 2, QTableWidgetItem(f"{percentage:.1f}%"))
            
            color = color_map.get(status, "#95a5a6")
            for col in range(3):
                item = self.status_summary_table.item(i, col)
                if item:
                    item.setForeground(QColor(color))
                    
    def _draw_status_pie_chart(self, status_stats):
        """نمودار دایره‌ای وضعیت‌ها"""
        filtered = {k: v for k, v in status_stats.items() if v > 0}
        if not filtered:
            self._show_status_chart_error("No status data available")
            return

        try:
            fig, ax = plt.subplots(figsize=(5, 4), facecolor='#1e1e2e')
            ax.set_facecolor('#1e1e2e')

            labels = list(filtered.keys())
            sizes = list(filtered.values())

            color_map = {
                "Normal": "#2ecc71",
                "Delayed": "#f39c12",
                "Completed": "#3498db",
                "In Progress": "#9b59b6",
                "On Hold": "#e74c3c",
                "PLN": "#1abc9c",
            }
            colors = [color_map.get(label, "#95a5a6") for label in labels]

            wedges, texts, autotexts = ax.pie(
                sizes, labels=labels, autopct='%1.1f%%',
                startangle=90, colors=colors,
                textprops={'color': 'white', 'fontsize': 10},
                wedgeprops={'edgecolor': '#1e1e2e', 'linewidth': 1}
            )
            for autotext in autotexts:
                autotext.set_color('white')

            ax.set_title("Activity Status Distribution", color='white', fontsize=12, fontweight='bold')

            canvas = FigureCanvas(fig)
            safe_replace_chart(self.status_pie_widget, canvas)
            plt.close(fig)

        except Exception as e:
            logger.error(f"Error drawing status pie chart: {e}")
            self._show_status_chart_error(f"Chart error: {str(e)[:50]}")
            
    def _show_status_chart_error(self, message):
        """نمایش پیام خطا در ویجت نمودار وضعیت"""
        if self.status_pie_widget.layout() is None:
            self.status_pie_widget.setLayout(QVBoxLayout())
        else:
            # پاک کردن محتویات قبلی
            layout = self.status_pie_widget.layout()
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        # اضافه کردن پیام خطا
        msg_label = QLabel(message)
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setStyleSheet("color: #e74c3c; font-size: 14px; padding: 20px;")
        self.status_pie_widget.layout().addWidget(msg_label)
 
# ==================== Milestones Tab ====================
class MilestonesTab(QWidget):
    """تب نمایش نقاط عطف سکشن‌ها (FACT vs PLAN)"""

    def __init__(self, db_manager=None, parent_widget=None):
        super().__init__()
        self.db = db_manager
        self.parent_widget = parent_widget
        self.current_well_id = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        header = QLabel("📊 Section Milestones - FACT vs PLAN")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #3498db; padding: 10px;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        info_label = QLabel("Actual time spent in each section vs Planned time based on Section creation data")
        info_label.setStyleSheet("color: #95a5a6; font-size: 12px;")
        info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_label)
        
        refresh_btn = QPushButton("🔄 Refresh Milestones")
        refresh_btn.clicked.connect(self.load_data)
        layout.addWidget(refresh_btn)
        
        self.milestones_chart_widget = QWidget()
        self.milestones_chart_widget.setMinimumHeight(350)
        layout.addWidget(self.milestones_chart_widget)
        
        self.milestones_table = QTableWidget(0, 5)
        self.milestones_table.setHorizontalHeaderLabels(["Section", "Depth From", "Depth To", "FACT (days)", "PLAN (days)"])
        self.milestones_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.milestones_table.setMaximumHeight(200)
        layout.addWidget(self.milestones_table)
        
    def set_current_well(self, well_id):
        self.current_well_id = well_id
        self.load_data()

    def set_current_report(self, report_id, report_date=None):
        self.current_report_id = report_id
        if self.current_well_id:
            self.load_data()
            
    def load_data(self):
        if not self.current_well_id or not self.db:
            self._show_no_data()
            return

        session = self.db.create_session()
        try:
            sections = session.query(Section).filter(
                Section.well_id == self.current_well_id
            ).order_by(Section.depth_from).all()

            if not sections:
                self._show_no_data()
                return

            section_names = []
            fact_days = []
            plan_days = []
            depth_from_list = []
            depth_to_list = []

            for section in sections:
                section_names.append(section.name)
                depth_from_list.append(section.depth_from or 0)
                depth_to_list.append(section.depth_to or 0)

                fact_time = session.query(
                    func.sum(TimeLog24H.duration)
                ).join(
                    DailyReport,
                    TimeLog24H.report_id == DailyReport.id
                ).filter(
                    DailyReport.section_id == section.id
                ).scalar() or 0
                fact_days.append(fact_time / 24)
                plan_days.append(section.planned_days or 0)

            # ✅ اگر همه صفر باشند
            if all(f == 0 for f in fact_days) and all(
                p == 0 for p in plan_days
            ):
                self._show_no_data()
                return

            self._draw_chart(
                section_names, fact_days, plan_days
            )
            self._fill_table(
                section_names, depth_from_list,
                depth_to_list, fact_days, plan_days
            )

        except Exception as e:
            logger.error(f"Error loading milestones: {e}")
            self._show_no_data()
        finally:
            session.close()
    
    def _draw_chart(self, sections, fact_days, plan_days):
        try:
            
            fig, ax = plt.subplots(figsize=(10, 5), facecolor='#2c3e50')
            ax.set_facecolor('#2c3e50')
            
            x = np.arange(len(sections))
            width = 0.35
            
            ax.bar(x - width/2, fact_days, width, label='FACT (Actual)', color='#3498db', edgecolor='white')
            ax.bar(x + width/2, plan_days, width, label='PLAN', color='#e74c3c', edgecolor='white')
            
            ax.set_xlabel('Sections', color='white')
            ax.set_ylabel('Days', color='white')
            ax.set_title('Section Milestones - FACT vs PLAN', color='white', fontsize=14)
            ax.set_xticks(x)
            ax.set_xticklabels(sections, rotation=45, ha='right', color='white')
            ax.tick_params(axis='y', colors='white')
            ax.legend(facecolor='#2c3e50', labelcolor='white')
            ax.grid(True, alpha=0.3, color='white')
            
            fig.tight_layout()
            canvas = FigureCanvas(fig)
            
            safe_replace_chart(self.milestones_chart_widget, canvas)
            plt.close(fig)
        except Exception as e:
            logger.error(f"Error drawing chart: {e}")
    
    def _fill_table(self, sections, depth_from, depth_to, fact_days, plan_days):
        self.milestones_table.setRowCount(len(sections))
        for i in range(len(sections)):
            self.milestones_table.setItem(i, 0, QTableWidgetItem(sections[i]))
            self.milestones_table.setItem(i, 1, QTableWidgetItem(f"{depth_from[i]:.1f} m"))
            self.milestones_table.setItem(i, 2, QTableWidgetItem(f"{depth_to[i]:.1f} m"))
            self.milestones_table.setItem(i, 3, QTableWidgetItem(f"{fact_days[i]:.1f}"))
            self.milestones_table.setItem(i, 4, QTableWidgetItem(f"{plan_days[i]:.1f}"))
    
    def _show_no_data(self):
        msg_label = QLabel("No Sections Defined.\nCreate sections in Daily Report tab.")
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setStyleSheet("color: #95a5a6; font-size: 14px; padding: 50px;")
        safe_replace_chart(self.milestones_chart_widget, msg_label)
        
    def refresh(self):
        self.load_data()

# ==================== Well Plan Tab (FACT vs PLAN) ====================
class WellPlanTab(QWidget):
    def __init__(self, db_manager=None, parent_widget=None):
        super().__init__()
        self.db = db_manager
        self.parent_widget = parent_widget
        self.current_well_id = None
        self.current_section_id = None
                
        self.fact_days = []
        self.fact_depths = []
        self.fact_dates = []
        self.plan_activities = []
        self.plan_points = []
        
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # Header
        header = QLabel("📊 Well Plan - FACT vs PLAN")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #9b59b6; padding: 10px;")
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)

        # Toolbar
        toolbar = QHBoxLayout()
        self.refresh_btn = QPushButton("🔄 Refresh FACT Data")
        self.refresh_btn.clicked.connect(self.load_fact_data)
        self.add_plan_btn = QPushButton("➕ Add Plan Activity (Dialog)")
        self.add_plan_btn.clicked.connect(self.open_plan_dialog)
        self.remove_plan_btn = QPushButton("➖ Remove Selected Plan")
        self.remove_plan_btn.clicked.connect(self.remove_plan_activity)
        self.save_plan_btn = QPushButton("💾 Save Plan to DB")
        self.save_plan_btn.clicked.connect(self.save_plan_to_db)

        toolbar.addWidget(self.refresh_btn)
        toolbar.addWidget(self.add_plan_btn)
        toolbar.addWidget(self.remove_plan_btn)
        toolbar.addWidget(self.save_plan_btn)
        toolbar.addStretch()
        main_layout.addLayout(toolbar)

        # Chart area
        self.chart_widget = QWidget()
        self.chart_widget.setMinimumHeight(350)
        self.chart_layout = QVBoxLayout(self.chart_widget)
        main_layout.addWidget(self.chart_widget)

        # جدول FACT (خواندنی)
        fact_group = QGroupBox("📋 FACT Data (from Daily Reports) - Read Only")
        fact_layout = QVBoxLayout()
        self.fact_table = QTableWidget(0, 3)
        self.fact_table.setHorizontalHeaderLabels(["Day (Cumulative)", "Date", "Actual Depth (m)"])
        self.fact_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.fact_table.setEditTriggers(QTableWidget.NoEditTriggers)  # غیرقابل ویرایش
        fact_layout.addWidget(self.fact_table)
        fact_group.setLayout(fact_layout)
        main_layout.addWidget(fact_group)

        # جدول PLAN (فعالیت‌های برنامه)
        plan_group = QGroupBox("📋 Planned Activities (PLAN)")
        plan_layout = QVBoxLayout()
        self.plan_table = QTableWidget(0, 6)
        self.plan_table.setHorizontalHeaderLabels(["Activity", "Start Day", "End Day", "Depth From (m)", "Depth To (m)", "Section"])
        self.plan_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.plan_table.setSelectionBehavior(QTableWidget.SelectRows)
        plan_layout.addWidget(self.plan_table)
        plan_group.setLayout(plan_layout)
        main_layout.addWidget(plan_group)

        # Statistics
        stats_group = QGroupBox("📊 Comparison Stats")
        stats_layout = QGridLayout()
        self.final_depth_label = QLabel("Final FACT Depth:")
        self.final_depth_value = QLabel("0 m")
        self.plan_final_label = QLabel("Planned Final Depth:")
        self.plan_final_value = QLabel("0 m")
        self.diff_label = QLabel("Difference:")
        self.diff_value = QLabel("0 m")
        stats_layout.addWidget(self.final_depth_label, 0, 0)
        stats_layout.addWidget(self.final_depth_value, 0, 1)
        stats_layout.addWidget(self.plan_final_label, 0, 2)
        stats_layout.addWidget(self.plan_final_value, 0, 3)
        stats_layout.addWidget(self.diff_label, 1, 0)
        stats_layout.addWidget(self.diff_value, 1, 1)
        stats_group.setLayout(stats_layout)
        main_layout.addWidget(stats_group)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #666;")
        main_layout.addWidget(self.status_label)

    def set_current_well(self, well_id):
        self.current_well_id = well_id
        if well_id:
            self.load_fact_data()
            self.load_plan_data()

    def set_current_report(self, report_id, report_date=None):
        """برای سازگاری با PlanningWidget - در WellPlanTab نیازی به گزارش جاری نیست"""
        pass

    def load_plans_list(self):
        """برای سازگاری با PlanningWidget - همان load_plan_data را صدا می‌زند"""
        self.load_plan_data()
        
    def set_current_section(self, section_id):
        self.current_section_id = section_id
        if self.current_well_id:
            self.load_fact_data()
            self.load_plan_data()

    def load_fact_data(self):
        """بارگذاری داده‌های واقعی از DailyReport (عمق ۲۴:۰۰) و محاسبه روز تجمعی"""
        if not self.current_well_id:
            return

        session = self.db.create_session()
        try:
            from core.database import DailyReport
            query = session.query(DailyReport).filter(
                DailyReport.well_id == self.current_well_id
            ).order_by(DailyReport.report_date)

            if self.current_section_id:
                query = query.filter(DailyReport.section_id == self.current_section_id)

            reports = query.all()

            if not reports:
                self.status_label.setText("No Daily Reports found for this well.")
                self.fact_table.setRowCount(0)
                self.fact_days = []
                self.fact_depths = []
                self.update_chart()
                self.update_stats()
                return

            self.fact_days = []
            self.fact_depths = []
            self.fact_dates = []

            for i, rep in enumerate(reports, start=1):
                self.fact_days.append(i)
                self.fact_depths.append(rep.depth_2400 or 0)
                self.fact_dates.append(rep.report_date)

            # نمایش در جدول FACT
            self.fact_table.setRowCount(len(self.fact_days))
            for i in range(len(self.fact_days)):
                self.fact_table.setItem(i, 0, QTableWidgetItem(str(self.fact_days[i])))
                self.fact_table.setItem(i, 1, QTableWidgetItem(str(self.fact_dates[i])))
                self.fact_table.setItem(i, 2, QTableWidgetItem(f"{self.fact_depths[i]:.1f}"))

            self.update_chart()
            self.update_stats()

        except Exception as e:
            logger.error(f"Error loading FACT data: {e}")
            self.status_label.setText(f"Error: {str(e)[:100]}")
        finally:
            session.close()

    def load_plan_data(self):
        """بارگذاری فعالیت‌های برنامه از جدول PlannedActivity و تبدیل به نقاط PLAN برای نمودار"""
        if not self.current_well_id:
            return

        session = self.db.create_session()
        try:
            from core.database import PlannedActivity
            from datetime import datetime

            query = session.query(PlannedActivity).filter(
                PlannedActivity.well_id == self.current_well_id
            )
            if self.current_section_id:
                query = query.filter(PlannedActivity.section_id == self.current_section_id)

            activities = query.order_by(PlannedActivity.planned_start).all()
            self.plan_activities = []  # ذخیره لیست کامل برای جدول
            self.plan_points = []      # نقاط (روز, عمق) برای رسم نمودار

            for act in activities:
                # محاسبه روز شروع و پایان بر اساس تاریخ (نسبت به اولین فعالیت)
                start_day = self._date_to_relative_day(act.planned_start)
                end_day = self._date_to_relative_day(act.planned_end)
                depth_from = act.planned_depth_from or 0
                depth_to = act.planned_depth_to or 0

                self.plan_activities.append({
                    'id': act.id,
                    'activity_name': act.activity_name,
                    'start_day': start_day,
                    'end_day': end_day,
                    'depth_from': depth_from,
                    'depth_to': depth_to,
                    'section_name': act.section.name if act.section else ""
                })
                # اضافه کردن نقطه شروع و پایان برای نمودار
                self.plan_points.append({'day': start_day, 'depth': depth_from})
                self.plan_points.append({'day': end_day, 'depth': depth_to})

            # حذف نقاط تکراری و مرتب‌سازی
            unique_points = {}
            for p in self.plan_points:
                unique_points[p['day']] = p['depth']
            self.plan_points = [{'day': d, 'depth': unique_points[d]} for d in sorted(unique_points.keys())]

            self.update_plan_table()
            self.update_chart()
            self.update_stats()

        except Exception as e:
            logger.error(f"Error loading PLAN data: {e}")
        finally:
            session.close()

    def _date_to_relative_day(self, dt):
        """تبدیل datetime به روز نسبی (با احتساب اولین گزارش FACT)"""
        if not self.fact_dates or not dt:
            return 0
        first_date = self.fact_dates[0]
        delta = dt.date() - first_date
        return max(0, delta.days + 1)  # روز اول = 1

    def open_plan_dialog(self):
        """باز کردن دیالوگ WellPlanDialog برای اضافه کردن فعالیت جدید"""
        if not self.current_well_id:
            QMessageBox.warning(self, "No Well", "Please select a well first.")
            return

        dialog = WellPlanDialog(self.db, self.current_well_id, self)
        if dialog.exec():
            self.load_plan_data()  # reload after save
            self.status_label.setText("Plan updated from dialog.")

    def remove_plan_activity(self):
        """حذف فعالیت انتخاب شده از جدول PLAN"""
        current_row = self.plan_table.currentRow()
        if current_row < 0 or current_row >= len(self.plan_activities):
            self.status_label.setText("No activity selected.")
            return

        act_id = self.plan_activities[current_row]['id']
        session = self.db.create_session()
        try:
            from core.database import PlannedActivity
            activity = session.query(PlannedActivity).filter(PlannedActivity.id == act_id).first()
            if activity:
                session.delete(activity)
                session.commit()
                self.load_plan_data()
                self.status_label.setText("Activity removed.")
            else:
                self.status_label.setText("Activity not found.")
        except Exception as e:
            session.rollback()
            logger.error(f"Error removing activity: {e}")
            self.status_label.setText(f"Error: {str(e)[:100]}")
        finally:
            session.close()

    def save_plan_to_db(self):
        """ذخیره داده‌های PLAN (در اینجا نیازی نیست چون دیالوگ قبلاً ذخیره کرده)"""
        self.status_label.setText("Plan already saved via dialog. Use 'Add Plan Activity' to add new.")

    def update_plan_table(self):
        """به‌روزرسانی جدول نمایش فعالیت‌های برنامه"""
        self.plan_table.setRowCount(len(self.plan_activities))
        for i, act in enumerate(self.plan_activities):
            self.plan_table.setItem(i, 0, QTableWidgetItem(act['activity_name']))
            self.plan_table.setItem(i, 1, QTableWidgetItem(str(act['start_day'])))
            self.plan_table.setItem(i, 2, QTableWidgetItem(str(act['end_day'])))
            self.plan_table.setItem(i, 3, QTableWidgetItem(f"{act['depth_from']:.1f}"))
            self.plan_table.setItem(i, 4, QTableWidgetItem(f"{act['depth_to']:.1f}"))
            self.plan_table.setItem(i, 5, QTableWidgetItem(act['section_name']))

    def update_chart(self):
        """رسم نمودار FACT vs PLAN (عمق بر حسب روز)"""
        if not hasattr(self, 'fact_days') or not self.fact_days:
            self.clear_chart()
            return

        fig, ax = plt.subplots(figsize=(10, 5), facecolor='#2c3e50')
        ax.set_facecolor('#1e1e2e')

        # خط FACT
        ax.plot(self.fact_days, self.fact_depths, 'o-', color='#3498db', linewidth=2, markersize=6, label='FACT (Actual)')

        # خط PLAN (نقاط)
        if hasattr(self, 'plan_points') and self.plan_points:
            plan_days = [p['day'] for p in self.plan_points]
            plan_depths = [p['depth'] for p in self.plan_points]
            ax.plot(plan_days, plan_depths, 's--', color='#e74c3c', linewidth=2, markersize=8, label='PLAN (Schedule)')

        ax.set_xlabel("Cumulative Days", color='white', fontsize=11)
        ax.set_ylabel("Depth (m)", color='white', fontsize=11)
        ax.set_title("Well Plan - FACT vs PLAN", color='white', fontsize=12, fontweight='bold')
        ax.invert_yaxis()
        ax.grid(True, alpha=0.3, color='gray')
        ax.tick_params(axis='both', colors='white')
        ax.legend(facecolor='#1e1e2e', labelcolor='white')

        fig.tight_layout()
        canvas = FigureCanvas(fig)
        self.clear_chart()
        self.chart_layout.addWidget(canvas)
        plt.close(fig)

    def update_stats(self):
        """بروزرسانی آمار مقایسه نهایی"""
        if hasattr(self, 'fact_depths') and self.fact_depths:
            final_fact = self.fact_depths[-1]
            self.final_depth_value.setText(f"{final_fact:.1f} m")
        else:
            final_fact = 0
            self.final_depth_value.setText("0 m")

        if hasattr(self, 'plan_activities') and self.plan_activities:
            # پیدا کردن آخرین عمق برنامه‌ریزی شده
            max_depth = max([act['depth_to'] for act in self.plan_activities])
            self.plan_final_value.setText(f"{max_depth:.1f} m")
            diff = final_fact - max_depth
            color = "#2ecc71" if diff >= 0 else "#e74c3c"
            self.diff_value.setText(f"{diff:+.1f} m")
            self.diff_value.setStyleSheet(f"color: {color}; font-weight: bold;")
        else:
            self.plan_final_value.setText("No PLAN")
            self.diff_value.setText("N/A")

    def clear_chart(self):
        while self.chart_layout.count():
            child = self.chart_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def show_error_label(self, message):
        self.clear_chart()
        label = QLabel(message)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #e74c3c; padding: 50px;")
        self.chart_layout.addWidget(label)

    def refresh(self):
        self.load_fact_data()
        self.load_plan_data()
        self.status_label.setText("Data refreshed")

@make_scrollable
# ==================== Drilling Params Tab ====================
class DrillingParamsTab(QWidget):
    def __init__(self, db_manager=None, parent_widget=None):
        super().__init__()
        self.db = db_manager
        self.parent_widget = parent_widget
        self.current_well_id = None
        self.current_report_id = None
        self.bit_records = []
        self.rop_data = []       
        self.bit_params = {}      
        self.init_ui()
        self.setup_connections()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("⚙️ Drilling Parameters Analysis (from Bit Record)")
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        header_layout.addWidget(title_label)

        self.refresh_btn = QPushButton("🔄 Refresh from Bit Record")
        self.refresh_btn.clicked.connect(self.load_data)
        header_layout.addWidget(self.refresh_btn)

        main_layout.addLayout(header_layout)

        # Tab widget
        self.tab_widget = QTabWidget()

        # ----- تب 1: ROP vs Depth (عمودی) -----
        tab_rop = QWidget()
        rop_layout = QVBoxLayout(tab_rop)
        self.rop_chart_widget = QWidget()
        self.rop_chart_widget.setMinimumHeight(400)
        self.rop_chart_layout = QVBoxLayout(self.rop_chart_widget)
        rop_layout.addWidget(self.rop_chart_widget)

        self.rop_table = QTableWidget(0, 2)
        self.rop_table.setHorizontalHeaderLabels(["Depth (m)", "ROP (m/hr)"])
        self.rop_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.rop_table.setMaximumHeight(200)
        rop_layout.addWidget(self.rop_table)

        self.tab_widget.addTab(tab_rop, "📈 ROP vs Depth")

        # ----- تب 2: نمودار خطی پارامترهای مته‌ها -----
        tab_bits = QWidget()
        bits_layout = QVBoxLayout(tab_bits)
        self.bit_chart_widget = QWidget()
        self.bit_chart_widget.setMinimumHeight(450)
        self.bit_chart_layout = QVBoxLayout(self.bit_chart_widget)
        bits_layout.addWidget(self.bit_chart_widget)

        self.bit_info_label = QLabel("Loading bit data...")
        self.bit_info_label.setAlignment(Qt.AlignCenter)
        bits_layout.addWidget(self.bit_info_label)

        self.tab_widget.addTab(tab_bits, "🔧 Bit Performance (Line Chart)")

        main_layout.addWidget(self.tab_widget)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #666;")
        main_layout.addWidget(self.status_label)

    def setup_connections(self):
        self.refresh_btn.clicked.connect(self.load_data)

    def set_current_well(self, well_id):
        self.current_well_id = well_id
        if well_id:
            self.load_data()
    def set_current_report(self, report_id, report_date=None):
        self.current_report_id = report_id
        if self.current_well_id:
            self.load_data()

    def clear_rop_chart(self):
        while self.rop_chart_layout.count():
            child = self.rop_chart_layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
                child.widget().deleteLater()

    def clear_bit_chart(self):
        while self.bit_chart_layout.count():
            child = self.bit_chart_layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
                child.widget().deleteLater()


    def load_data(self):
        if not self.db or not self.current_well_id:
            self.status_label.setText("No well selected")
            return

        session = self.db.create_session()
        try:
            from core.database import BitReport
            import json

            query = session.query(BitReport).filter(BitReport.well_id == self.current_well_id)
            if self.current_report_id:
                query = query.filter(BitReport.report_id == self.current_report_id)
            bit_report = query.order_by(BitReport.report_date.desc()).first()

            if not bit_report or not bit_report.bit_records_json:
                self.status_label.setText("No Bit Record data found.")
                self.clear_rop_chart()
                self.clear_bit_chart()
                return

            records = json.loads(bit_report.bit_records_json)
            self.bit_records = records

            if not records:
                self.status_label.setText("No records in Bit Report.")
                return

            # ========== داده‌های ROP vs Depth ==========
            rop_points = []
            for rec in records:
                try:
                    depth = float(rec.get("Depth Out (m)", 0))
                    rop = float(rec.get("ROP (m/hr)", 0))
                    if depth > 0 and rop > 0:
                        rop_points.append({'depth': depth, 'rop': rop})
                except:
                    continue

            if rop_points:
                rop_points.sort(key=lambda x: x['depth'])
                self.rop_data = rop_points
                self.rop_table.setRowCount(len(rop_points))
                for i, d in enumerate(rop_points):
                    self.rop_table.setItem(i, 0, QTableWidgetItem(f"{d['depth']:.1f}"))
                    self.rop_table.setItem(i, 1, QTableWidgetItem(f"{d['rop']:.2f}"))
                self.plot_rop_chart(rop_points)
            else:
                self.clear_rop_chart()
                self.status_label.setText("No valid ROP/depth data.")

            # ========== داده‌های مته‌ها برای تب دوم ==========
            bit_params = {}
            for idx, rec in enumerate(records):
                # در هر رکورد، Bit No را بگیر (نه فقط اولین بار)
                bit_no = rec.get("Bit No", "").strip()
                if not bit_no:
                    # اگر Bit No وجود نداشت، از شماره ردیف استفاده کن
                    bit_no = f"Bit #{idx+1}"
                
                try:
                    def get_float_value(rec, keys, default=0.0):
                        for k in keys:
                            val = rec.get(k)
                            if val is not None:
                                try:
                                    return float(val)
                                except:
                                    pass
                        return default

                    metres = get_float_value(rec, ["Metres Drilled", "Metres Drilled (m)", "Mètres"], 0)
                    rop = get_float_value(rec, ["ROP (m/hr)", "ROP", "Rate of Penetration"], 0)
                    wob_min = get_float_value(rec, ["WOB Min (klb)", "WOB Min", "WOB (klb) min"], 0)
                    wob_max = get_float_value(rec, ["WOB Max (klb)", "WOB Max", "WOB (klb) max"], 0)
                    wob_avg = (wob_min + wob_max) / 2 if (wob_min or wob_max) else 0

                    rpm_min = get_float_value(rec, ["Rot. Min", "RPM Min", "RPM min"], 0)
                    rpm_max = get_float_value(rec, ["Rot. Max", "RPM Max", "RPM max"], 0)
                    rpm_avg = (rpm_min + rpm_max) / 2 if (rpm_min or rpm_max) else 0

                    gpm_min = get_float_value(rec, ["FR Min", "GPM Min", "Flow Rate min"], 0)
                    gpm_max = get_float_value(rec, ["FR Max", "GPM Max", "Flow Rate max"], 0)
                    gpm_avg = (gpm_min + gpm_max) / 2 if (gpm_min or gpm_max) else 0

                    spp_min = get_float_value(rec, ["SPP Min (psi)", "SPP Min", "Pump Pressure min"], 0)
                    spp_max = get_float_value(rec, ["SPP Max (psi)", "SPP Max", "Pump Pressure max"], 0)
                    spp_avg = (spp_min + spp_max) / 2 if (spp_min or spp_max) else 0

                    torque_min = get_float_value(rec, ["TQ Min (klb.ft)", "Torque Min", "TQ min"], 0)
                    torque_max = get_float_value(rec, ["TQ Max (klb.ft)", "Torque Max", "TQ max"], 0)
                    torque_avg = (torque_min + torque_max) / 2 if (torque_min or torque_max) else 0

                    bit_params[bit_no] = {
                        "Metres Drilled": metres,
                        "ROP (m/hr)": rop,
                        "WOB (klb)": wob_avg,
                        "RPM": rpm_avg,
                        "Flow Rate (gpm)": gpm_avg,
                        "SPP (psi)": spp_avg,
                        "Torque (klb.ft)": torque_avg,
                    }

                except Exception as e:
                    logger.warning(f"Error processing bit record {idx}: {e}")
                    continue

            if bit_params:
                self.bit_params = bit_params
                self.plot_bit_line_chart(bit_params)
                self.bit_info_label.setText(f"Showing {len(bit_params)} bits")
            else:
                self.clear_bit_chart()
                self.bit_info_label.setText("No bit parameter data found.")

            self.status_label.setText(f"Loaded {len(rop_points)} ROP points and {len(bit_params)} bits")

        except Exception as e:
            logger.error(f"Error loading data: {e}")
            import traceback
            traceback.print_exc()
            self.status_label.setText(f"Error: {str(e)}")
        finally:
            session.close()

    def plot_rop_chart(self, rop_points):
        """رسم ROP vs Depth با عمق در محور عمودی (معکوس)"""

        if not rop_points:
            return

        depths = [d['depth'] for d in rop_points]
        rops = [d['rop'] for d in rop_points]

        fig, ax = plt.subplots(figsize=(10, 5), facecolor='#2c3e50')
        ax.set_facecolor('#2c3e50')
        ax.scatter(rops, depths, color='#3498db', s=50, alpha=0.7, label='ROP Data')

        if len(rops) > 1:
            z = np.polyfit(rops, depths, 1)
            trend_rops = np.linspace(min(rops), max(rops), 100)
            trend_depths = np.polyval(z, trend_rops)
            ax.plot(trend_rops, trend_depths, '--', color='#e74c3c', linewidth=2, label='Trend')

        ax.set_xlabel("ROP (m/hr)", color='white')
        ax.set_ylabel("Depth (m)", color='white')
        ax.set_title("ROP vs Depth (All Bits)", color='white')
        ax.invert_yaxis()
        ax.grid(True, alpha=0.3, color='white')
        ax.tick_params(axis='both', colors='white')
        ax.legend(facecolor='#2c3e50', labelcolor='white')
        fig.tight_layout()

        canvas = FigureCanvas(fig)
        self.clear_rop_chart()
        self.rop_chart_layout.addWidget(canvas)
        plt.close(fig)

    def plot_bit_line_chart(self, bit_params):

        if not bit_params:
            self.bit_info_label.setText("No bit parameter data found.")
            return

        try:
            bit_names = list(bit_params.keys())
            bit_names.sort(key=lambda x: int(''.join(filter(str.isdigit, x)) or 0))

            x = np.arange(len(bit_names))

            # تعریف گروه‌ها
            groups = {
                "📊 Group 1 - Depth & Pressure": {
                    "params": ["Metres Drilled", "SPP (psi)"],
                    "colors": ["#3498db", "#e74c3c"],
                    "markers": ["o", "s"],
                    "ylabel": "Metres Drilled (m) / SPP (psi)"
                },
                "⚙️ Group 2 - Rotation & Flow": {
                    "params": ["RPM", "Flow Rate (gpm)"],
                    "colors": ["#2ecc71", "#f39c12"],
                    "markers": ["^", "D"],
                    "ylabel": "RPM / Flow Rate (gpm)"
                },
                "⚡ Group 3 - Performance": {
                    "params": ["ROP (m/hr)", "WOB (klb)", "Torque (klb.ft)"],
                    "colors": ["#9b59b6", "#1abc9c", "#e67e22"],
                    "markers": ["v", "<", ">"],
                    "ylabel": "ROP (m/hr) / WOB (klb) / Torque (klb.ft)"
                }
            }

            # ایجاد شکل با ۳ ردیف (subplot)
            fig, axes = plt.subplots(3, 1, figsize=(10, 10), facecolor='#2c3e50')
            fig.subplots_adjust(hspace=0.4, top=0.95, bottom=0.08)

            for idx, (group_title, group_data) in enumerate(groups.items()):
                ax = axes[idx]
                ax.set_facecolor('#1e1e2e')
                ax.set_title(group_title, color='white', fontsize=12, fontweight='bold')
                ax.set_xlabel("Bit Number", color='white', fontsize=10)
                ax.set_ylabel(group_data["ylabel"], color='white', fontsize=10)
                ax.tick_params(axis='x', labelcolor='white', colors='white')
                ax.tick_params(axis='y', labelcolor='white', colors='white')
                ax.grid(True, alpha=0.3, color='gray')

                for i, param in enumerate(group_data["params"]):
                    values = [bit_params[bit].get(param, 0) for bit in bit_names]
                    if max(values) > 0:
                        ax.plot(x, values, 
                               marker=group_data["markers"][i % len(group_data["markers"])],
                               color=group_data["colors"][i % len(group_data["colors"])],
                               linewidth=2, markersize=8, label=param)

                ax.set_xticks(x)
                ax.set_xticklabels(bit_names, rotation=45, ha='right', color='white')
                ax.legend(loc='upper right', facecolor='#1e1e2e', labelcolor='white')

            fig.tight_layout()

            canvas = FigureCanvas(fig)
            self.clear_bit_chart()
            self.bit_chart_layout.addWidget(canvas)
            self.bit_info_label.setText(f"Showing {len(bit_names)} bits in 3 groups")
            plt.close(fig)

        except Exception as e:
            print(f"Error in plot_bit_line_chart: {e}")
            import traceback
            traceback.print_exc()
            self.bit_info_label.setText(f"Chart error: {str(e)[:50]}")
            
        
    def refresh(self):
        self.load_data()
        
# ==================== Mud Params Tab ====================
class MudParamsTab(QWidget):
    """تب پارامترهای گل vs عمق"""

    def __init__(self, db_manager=None, parent_widget=None):
        super().__init__()
        self.db = db_manager
        self.parent_widget = parent_widget
        self.current_well_id = None
        self.mud_data = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        header = QLabel("🧪 Mud Parameters vs Depth")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #2ecc71;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("Parameter:"))
        self.param_combo = QComboBox()
        self.param_combo.addItems(["MW (pcf)", "PV (cp)", "YP", "Gel 10s", "Gel 10m", "pH", "Temperature"])
        self.param_combo.currentTextChanged.connect(self.update_chart)
        control_layout.addWidget(self.param_combo)
        
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.load_data)
        control_layout.addWidget(self.refresh_btn)
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        self.chart_widget = QWidget()
        self.chart_widget.setMinimumHeight(400)
        layout.addWidget(self.chart_widget)
        
        self.data_table = QTableWidget(0, 7)
        self.data_table.setHorizontalHeaderLabels(["Depth", "MW", "PV", "YP", "Gel10s", "Gel10m", "pH"])
        self.data_table.setMaximumHeight(200)
        layout.addWidget(self.data_table)
    
    def set_current_well(self, well_id):
        self.current_well_id = well_id
        self.load_data()
  
    def set_current_report(self, report_id, report_date=None):
        self.current_report_id = report_id
        if self.current_well_id:
            self.load_data()
        
    def load_data(self):
        if not self.current_well_id or not self.db:
            return
        session = self.db.create_session()
        try:
            from core.database import MudReport, DailyReport, DrillingParameters
            
            results = session.query(
                MudReport, DailyReport.depth_2400
            ).join(
                DailyReport, MudReport.report_id == DailyReport.id
            ).filter(
                DailyReport.well_id == self.current_well_id
            ).order_by(DailyReport.report_date).all()
            
            self.mud_data = []
            self.data_table.setRowCount(0)
            
            for mud, depth in results:
                row = self.data_table.rowCount()
                self.data_table.insertRow(row)
                self.data_table.setItem(row, 0, QTableWidgetItem(f"{depth or 0:.1f}"))
                self.data_table.setItem(row, 1, QTableWidgetItem(f"{mud.mw or 0:.1f}"))
                self.data_table.setItem(row, 2, QTableWidgetItem(f"{mud.pv or 0:.1f}"))
                self.data_table.setItem(row, 3, QTableWidgetItem(f"{mud.yp or 0:.1f}"))
                self.data_table.setItem(row, 4, QTableWidgetItem(f"{mud.gel_10s or 0:.1f}"))
                self.data_table.setItem(row, 5, QTableWidgetItem(f"{mud.gel_10m or 0:.1f}"))
                self.data_table.setItem(row, 6, QTableWidgetItem(f"{mud.ph or 0:.1f}"))
                
                self.mud_data.append({
                    'depth': depth or 0, 'mw': mud.mw or 0, 'pv': mud.pv or 0,
                    'yp': mud.yp or 0, 'gel_10s': mud.gel_10s or 0,
                    'gel_10m': mud.gel_10m or 0, 'ph': mud.ph or 0
                })
            self.update_chart()
        except Exception as e:
            logger.error(f"Error loading mud data: {e}")
        finally:
            session.close()
    
    def update_chart(self):
        if not self.mud_data:
            return
        try:
            
            param_map = {
                "MW (pcf)": ('mw', 'MW (pcf)', '#3498db'),
                "PV (cp)": ('pv', 'PV (cp)', '#e74c3c'),
                "YP": ('yp', 'YP (lb/100ft²)', '#2ecc71'),
                "Gel 10s": ('gel_10s', 'Gel 10s', '#f39c12'),
                "Gel 10m": ('gel_10m', 'Gel 10m', '#9b59b6'),
                "pH": ('ph', 'pH', '#1abc9c'),
                "Temperature": ('temp', 'Temperature (°C)', '#e67e22'),
            }
            key, label, color = param_map.get(self.param_combo.currentText(), ('mw', 'MW', '#3498db'))
            
            values = [d[key] for d in self.mud_data]
            depths = [d['depth'] for d in self.mud_data]
            
            fig, ax = plt.subplots(figsize=(10, 5), facecolor='#2c3e50')
            ax.set_facecolor('#2c3e50')
            ax.plot(values, depths, 'o-', color=color, linewidth=2, markersize=4)
            ax.set_xlabel(label, color='white')
            ax.set_ylabel('Depth (m)', color='white')
            ax.set_title(f'{label} vs Depth', color='white')
            ax.invert_yaxis()
            ax.grid(True, alpha=0.3, color='white')
            ax.tick_params(axis='both', colors='white')
            fig.tight_layout()
            
            canvas = FigureCanvas(fig)
            safe_replace_chart(self.chart_widget, canvas)
            plt.close(fig)
        except Exception as e:
            logger.error(f"Error updating chart: {e}")
    
    def refresh(self):
        self.load_data()
   
# ==================== Material Inventory Tab ====================
class MaterialInventoryTab(QWidget):
    """تب مصرف و موجودی مواد (گل، سیمان، مواد شیمیایی)"""

    def __init__(self, db_manager=None, parent_widget=None):
        super().__init__()
        self.db = db_manager
        self.parent_widget = parent_widget
        self.current_well_id = None
        self.current_report_id = None
        self.current_section_id = None
        self.init_ui()
        self.setup_connections()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        header = QLabel("📦 Material Inventory & Consumption")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #1abc9c; padding: 10px;")
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)

        # نوار ابزار
        toolbar = QHBoxLayout()
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.load_data)
        self.add_material_btn = QPushButton("➕ Add Material")
        self.add_material_btn.clicked.connect(self.add_material_dialog)
        self.remove_material_btn = QPushButton("➖ Remove Material")
        self.remove_material_btn.clicked.connect(self.remove_material)
        self.export_btn = QPushButton("📤 Export")
        self.export_btn.clicked.connect(self.export_data)

        toolbar.addWidget(self.refresh_btn)
        toolbar.addWidget(self.add_material_btn)
        toolbar.addWidget(self.remove_material_btn)
        toolbar.addWidget(self.export_btn)
        toolbar.addStretch()
        main_layout.addLayout(toolbar)

        # جدول مواد
        self.material_table = QTableWidget(0, 8)
        self.material_table.setHorizontalHeaderLabels([
            "Material", "Unit", "Initial Stock", "Received", "Used", "Current Stock", "Last Update", "Remarks"
        ])
        self.material_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.material_table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        self.material_table.setSelectionBehavior(QTableWidget.SelectRows)
        main_layout.addWidget(self.material_table)

        # اتصال تغییرات سلول برای محاسبه خودکار Current Stock
        self.material_table.cellChanged.connect(self.on_cell_changed)

        # نمودار مصرف مواد
        self.chart_widget = QWidget()
        self.chart_widget.setMinimumHeight(300)
        self.chart_layout = QVBoxLayout(self.chart_widget)
        main_layout.addWidget(self.chart_widget)

        # وضعیت
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #666;")
        main_layout.addWidget(self.status_label)

    def setup_connections(self):
        pass

    def set_current_well(self, well_id):
        self.current_well_id = well_id
        self.load_data()

    def set_current_report(self, report_id, report_date=None):
        self.current_report_id = report_id
        self.load_data()

    def set_current_section(self, section_id):
        self.current_section_id = section_id
        self.load_data()

    def load_data(self):
        """بارگذاری داده‌های موجودی از BulkMaterials"""
        if not self.db or not self.current_well_id:
            self.material_table.setRowCount(0)
            self.clear_chart()
            return

        session = self.db.create_session()
        try:
            from core.database import BulkMaterials
            query = session.query(BulkMaterials).filter(
                BulkMaterials.well_id == self.current_well_id
            )
            if self.current_section_id:
                query = query.filter(BulkMaterials.section_id == self.current_section_id)
            if self.current_report_id:
                query = query.filter(BulkMaterials.report_id == self.current_report_id)

            materials = query.all()
            self.material_table.setRowCount(len(materials))
            for i, m in enumerate(materials):
                self.material_table.setItem(i, 0, QTableWidgetItem(m.material_name))
                self.material_table.setItem(i, 1, QTableWidgetItem(m.unit))
                self.material_table.setItem(i, 2, QTableWidgetItem(f"{m.initial_stock:.1f}"))
                self.material_table.setItem(i, 3, QTableWidgetItem(f"{m.received:.1f}"))
                self.material_table.setItem(i, 4, QTableWidgetItem(f"{m.used:.1f}"))
                self.material_table.setItem(i, 5, QTableWidgetItem(f"{m.current_stock:.1f}"))
                self.material_table.setItem(i, 6, QTableWidgetItem(m.updated_at.strftime("%Y-%m-%d") if m.updated_at else ""))
                self.material_table.setItem(i, 7, QTableWidgetItem(""))
            self.update_chart()
            self.status_label.setText(f"Loaded {len(materials)} materials")
        except Exception as e:
            logger.error(f"Error loading inventory: {e}")
            self.status_label.setText(f"Error: {str(e)[:100]}")
        finally:
            session.close()

    def on_cell_changed(self, row, col):
        """هنگام تغییر مقدار دریافت یا مصرف، موجودی را محاسبه کن"""
        if col in [2, 3, 4]:  # Initial, Received, Used
            try:
                initial = float(self.material_table.item(row, 2).text() or 0)
                received = float(self.material_table.item(row, 3).text() or 0)
                used = float(self.material_table.item(row, 4).text() or 0)
                current = initial + received - used
                self.material_table.setItem(row, 5, QTableWidgetItem(f"{current:.1f}"))
                self.save_material_row(row)
            except:
                pass

    def save_material_row(self, row):
        """ذخیره یک ردیف در دیتابیس"""
        if not self.current_well_id:
            return
        session = self.db.create_session()
        try:
            from core.database import BulkMaterials
            material_name = self.material_table.item(row, 0).text()
            unit = self.material_table.item(row, 1).text()
            initial = float(self.material_table.item(row, 2).text() or 0)
            received = float(self.material_table.item(row, 3).text() or 0)
            used = float(self.material_table.item(row, 4).text() or 0)
            current = initial + received - used

            existing = session.query(BulkMaterials).filter(
                BulkMaterials.well_id == self.current_well_id,
                BulkMaterials.material_name == material_name,
                BulkMaterials.report_id == self.current_report_id
            ).first()
            if existing:
                existing.initial_stock = initial
                existing.received = received
                existing.used = used
                existing.current_stock = current
                existing.unit = unit
                existing.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            else:
                new_material = BulkMaterials(
                    well_id=self.current_well_id,
                    section_id=self.current_section_id,
                    report_id=self.current_report_id,
                    material_name=material_name,
                    unit=unit,
                    initial_stock=initial,
                    received=received,
                    used=used,
                    current_stock=current,
                    report_date=date.today()
                )
                session.add(new_material)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving material: {e}")
        finally:
            session.close()

    def add_material_dialog(self):
        """دیالوگ افزودن ماده جدید"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Material")
        layout = QFormLayout()
        name_edit = QLineEdit()
        unit_edit = QComboBox()
        unit_edit.addItems(["kg", "lb", "bbl", "sacks", "m³", "liters"])
        initial_spin = QDoubleSpinBox()
        initial_spin.setRange(0, 100000)
        received_spin = QDoubleSpinBox()
        received_spin.setRange(0, 100000)
        used_spin = QDoubleSpinBox()
        used_spin.setRange(0, 100000)
        layout.addRow("Material Name:", name_edit)
        layout.addRow("Unit:", unit_edit)
        layout.addRow("Initial Stock:", initial_spin)
        layout.addRow("Received:", received_spin)
        layout.addRow("Used:", used_spin)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        dialog.setLayout(layout)
        if dialog.exec():
            row = self.material_table.rowCount()
            self.material_table.insertRow(row)
            self.material_table.setItem(row, 0, QTableWidgetItem(name_edit.text()))
            self.material_table.setItem(row, 1, QTableWidgetItem(unit_edit.currentText()))
            self.material_table.setItem(row, 2, QTableWidgetItem(f"{initial_spin.value():.1f}"))
            self.material_table.setItem(row, 3, QTableWidgetItem(f"{received_spin.value():.1f}"))
            self.material_table.setItem(row, 4, QTableWidgetItem(f"{used_spin.value():.1f}"))
            self.material_table.setItem(row, 5, QTableWidgetItem(f"{initial_spin.value() + received_spin.value() - used_spin.value():.1f}"))
            self.material_table.setItem(row, 6, QTableWidgetItem(date.today().strftime("%Y-%m-%d")))
            self.material_table.setItem(row, 7, QTableWidgetItem(""))
            self.save_material_row(row)
            self.update_chart()

    def remove_material(self):
        current_row = self.material_table.currentRow()
        if current_row < 0:
            return
        material_name = self.material_table.item(current_row, 0).text()
        reply = QMessageBox.question(self, "Delete", f"Delete '{material_name}'?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            session = self.db.create_session()
            try:
                from core.database import BulkMaterials
                session.query(BulkMaterials).filter(
                    BulkMaterials.well_id == self.current_well_id,
                    BulkMaterials.material_name == material_name,
                    BulkMaterials.report_id == self.current_report_id
                ).delete()
                session.commit()
                self.material_table.removeRow(current_row)
                self.update_chart()
            except Exception as e:
                session.rollback()
                logger.error(f"Error deleting material: {e}")
            finally:
                session.close()

    def update_chart(self):
        """نمودار مصرف مواد (میله‌ای) بر اساس مقدار مصرف شده"""
        if self.material_table.rowCount() == 0:
            self.clear_chart()
            return

        materials = []
        used_vals = []
        for row in range(self.material_table.rowCount()):
            name = self.material_table.item(row, 0).text()
            used = float(self.material_table.item(row, 4).text() or 0)
            if used > 0:
                materials.append(name)
                used_vals.append(used)

        if not materials:
            self.clear_chart()
            label = QLabel("No consumption data to display")
            label.setAlignment(Qt.AlignCenter)
            self.chart_layout.addWidget(label)
            return

        fig, ax = plt.subplots(figsize=(8, 4), facecolor='#2c3e50')
        ax.set_facecolor('#1e1e2e')
        colors = plt.cm.viridis(range(len(materials)))
        bars = ax.bar(materials, used_vals, color=colors, edgecolor='white')
        ax.set_xlabel("Material", color='white')
        ax.set_ylabel("Consumed (unit)", color='white')
        ax.set_title("Material Consumption", color='white', fontsize=12)
        ax.tick_params(axis='x', colors='white', rotation=45)
        ax.tick_params(axis='y', colors='white')
        ax.grid(axis='y', alpha=0.3)
        for bar, val in zip(bars, used_vals):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, f"{val:.1f}", ha='center', color='white')

        fig.tight_layout()
        canvas = FigureCanvas(fig)
        self.clear_chart()
        self.chart_layout.addWidget(canvas)
        plt.close(fig)

    def clear_chart(self):
        while self.chart_layout.count():
            child = self.chart_layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
                child.widget().deleteLater()

    def export_data(self):
        export_manager = ExportManager(self)
        export_manager.export_table_with_dialog(self.material_table, "material_inventory")

    def refresh(self):
        self.load_data()

# ==================== Main Planning Widget ====================
class PlanningWidget(DrillTabBase):
    def __init__(self, db_manager=None, parent=None):
        super().__init__("PlanningWidget", db_manager, parent)
        self.db = db_manager
        self.current_well_id = None
        self.current_report_id = None
        self.current_section_id = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # ========== نوار ابزار انتخاب چاه و سکشن ==========
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)

        toolbar_layout.addWidget(QLabel("Well:"))
        self.well_combo = QComboBox()
        self.well_combo.setMinimumWidth(200)
        self.well_combo.currentIndexChanged.connect(self.on_well_combo_changed)
        toolbar_layout.addWidget(self.well_combo)

        toolbar_layout.addWidget(QLabel("Section:"))
        self.section_combo = QComboBox()
        self.section_combo.setMinimumWidth(200)
        self.section_combo.currentIndexChanged.connect(self.on_section_combo_changed)
        toolbar_layout.addWidget(self.section_combo)

        toolbar_layout.addStretch()
        main_layout.addWidget(toolbar_widget)

        # ========== تب‌ها ==========
        self.tab_widget = QTabWidget()
        self.lookahead_tab = SevenDaysLookaheadTab(self.db, self)
        self.npt_tab = NPTReportTab(self.db, self)
        self.code_tab = CodeManagementTab(self.db, self)
        self.milestones_tab = MilestonesTab(self.db, self)
        self.well_plan_tab = WellPlanTab(self.db, self)
        self.drilling_params_tab = DrillingParamsTab(self.db, self)
        self.mud_params_tab = MudParamsTab(self.db, self)
        self.material_inventory_tab = MaterialInventoryTab(self.db, self)


        self.tab_widget.addTab(self.lookahead_tab, "📅 7 Days Lookahead")
        self.tab_widget.addTab(self.npt_tab, "⏱️ NPT Report")
        self.tab_widget.addTab(self.code_tab, "🏷️ Code Management")
        self.tab_widget.addTab(self.milestones_tab, "🏔️ Milestones")
        self.tab_widget.addTab(self.well_plan_tab, "📋 Well Plan")
        self.tab_widget.addTab(self.drilling_params_tab, "⚙️ Drilling Params")
        self.tab_widget.addTab(self.mud_params_tab, "🧪 Mud Params")
        self.tab_widget.addTab(self.material_inventory_tab, "📦 Material Inventory")

        main_layout.addWidget(self.tab_widget)

        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Planning Module Ready")
        main_layout.addWidget(self.status_bar)

        self.tab_widget.currentChanged.connect(self.on_tab_selected)
        self.populate_wells()

    def populate_wells(self):
        """بارگذاری لیست چاه‌ها در کمبوباکس"""
        self.well_combo.blockSignals(True)
        self.well_combo.clear()
        self.well_combo.addItem("-- Select Well --", None)
        if self.db:
            hierarchy = self.db.get_hierarchy()
            for company in hierarchy:
                for project in company.get('projects', []):
                    for well in project.get('wells', []):
                        self.well_combo.addItem(f"{well['name']} ({well['code']})", well['id'])
        self.well_combo.blockSignals(False)
    
    def load_sections(self, well_id):
        """بارگذاری سکشن‌های چاه در کمبوباکس"""
        self.section_combo.blockSignals(True)
        self.section_combo.clear()
        self.section_combo.addItem("All Sections", None)
        if self.db and well_id:
            sections = self.db.get_sections_by_well(well_id)
            for section in sections:
                self.section_combo.addItem(section['name'], section['id'])
        self.section_combo.blockSignals(False)

    def on_well_combo_changed(self, index):
        well_id = self.well_combo.currentData()
        if well_id:
            self.current_well_id = well_id
            self.load_sections(well_id)
            well_data = self.db.get_well_by_id(well_id) if self.db else None
            self.on_well_changed(well_id, well_data or {})
        else:
            self.current_well_id = None
            self.section_combo.clear()
            self.section_combo.addItem("All Sections", None)

    def on_section_combo_changed(self, index):
        section_id = self.section_combo.currentData()
        self.current_section_id = section_id
        self.lookahead_tab.set_current_section(section_id)
        self.npt_tab.set_current_section(section_id)
        self.code_tab.set_current_section(section_id)

    def on_tab_selected(self, index):
        """Refresh the currently selected tab with latest data"""
        if index == 0:   # Seven Days Lookahead
            if self.current_report_id:
                self.lookahead_tab.load_lookahead_plan()
        elif index == 1: # NPT Report
            if self.current_well_id:
                self.npt_tab.load_npt_data()
        elif index == 2: # Code Management
            if self.current_well_id:
                self.code_tab.load_codes()      
        elif index == 3: # Milestones 
            if self.current_well_id:
                self.load_milestones_data()
        elif index == 4: # Well Plan
            if self.current_well_id:
                self.load_plans_list()
        elif index == 5: # Drilling Params
            if self.current_well_id:
                self.load_drilling_data()
        elif index == 6: # Mud Params
            if self.current_well_id:
                self.load_mud_data()

    def on_well_changed(self, well_id, well_data):
        """Override - sync combo + load data"""
        self.current_well_id = well_id
        name = well_data.get("name", str(well_id)) if well_data else str(well_id)
        
        # Sync combo
        self.well_combo.blockSignals(True)
        for i in range(self.well_combo.count()):
            if self.well_combo.itemData(i) == well_id:
                self.well_combo.setCurrentIndex(i)
                break
        self.well_combo.blockSignals(False)
        
        # Load sections
        self.load_sections(well_id)
        
        # Update all sub-tabs
        self.lookahead_tab.set_current_well(well_id)
        self.npt_tab.set_current_well(well_id)
        self.code_tab.set_current_well(well_id)
        self.milestones_tab.set_current_well(well_id)
        self.well_plan_tab.set_current_well(well_id)
        self.drilling_params_tab.set_current_well(well_id)
        self.mud_params_tab.set_current_well(well_id)
        self.material_inventory_tab.set_current_well(well_id)
        
        self.status_bar.showMessage(f"Well: {name}", 3000)
        self.current_report_id = None

    def on_section_changed(self, section_id, section_data):
        """Override - sync combo + update sub-tabs"""
        self.current_section_id = section_id
        
        # Sync combo
        self.section_combo.blockSignals(True)
        for i in range(self.section_combo.count()):
            if self.section_combo.itemData(i) == section_id:
                self.section_combo.setCurrentIndex(i)
                break
        self.section_combo.blockSignals(False)
        
        # Update sub-tabs
        if hasattr(self, 'lookahead_tab'):
            self.lookahead_tab.set_current_section(section_id)
        if hasattr(self, 'npt_tab'):
            self.npt_tab.set_current_section(section_id)
        if hasattr(self, 'code_tab'):
            self.code_tab.set_current_section(section_id)
        if hasattr(self, 'material_inventory_tab'):
            self.material_inventory_tab.set_current_section(section_id)
            
    def on_report_changed(self, report_id, report_info):
        self.current_report_id = report_id
        report_date = report_info.get('report_date') if report_info else None
        self.lookahead_tab.set_current_report(report_id, report_date)
        self.npt_tab.set_current_report(report_id, report_date)
        self.code_tab.set_current_report(report_id, report_date)
        self.milestones_tab.set_current_report(report_id, report_date)
        self.well_plan_tab.set_current_report(report_id, report_date)
        self.drilling_params_tab.set_current_report(report_id, report_date)
        self.mud_params_tab.set_current_report(report_id, report_date)
        if hasattr(self, 'material_inventory_tab'):
            self.material_inventory_tab.set_current_section(self.current_section_id)

    # ==================== متدهای کمکی ====================
    def show_no_data_message(self, target_widget, message):
        """نمایش پیام عدم وجود داده"""
        if hasattr(target_widget, 'setLayout'):
            if target_widget.layout():
                for i in reversed(range(target_widget.layout().count())):
                    widget = target_widget.layout().itemAt(i).widget()
                    if widget:
                        widget.setParent(None)
            else:
                target_widget.setLayout(QVBoxLayout())
            msg_label = QLabel(message)
            msg_label.setAlignment(Qt.AlignCenter)
            msg_label.setStyleSheet("color: #95a5a6; font-size: 14px; padding: 50px;")
            target_widget.layout().addWidget(msg_label)

    def load_milestones_data(self):
        if hasattr(self, 'milestones_tab'):
            self.milestones_tab.load_data()

    def load_plans_list(self):
        if hasattr(self, 'well_plan_tab'):
            self.well_plan_tab.load_plans_list()

    def load_drilling_data(self):
        if hasattr(self, 'drilling_params_tab'):
            self.drilling_params_tab.load_data()

    def load_mud_data(self):
        if hasattr(self, 'mud_params_tab'):
            self.mud_params_tab.load_data()

    def refresh_data(self):
        if self.current_well_id:
            self.load_drilling_data()
            self.load_mud_data()
            self.status_bar.showMessage(f"Data refreshed at {datetime.now().strftime('%H:%M:%S')}", 3000)

    def save_data(self):
        if hasattr(self.lookahead_tab, 'save_plan'):
            self.lookahead_tab.save_plan()
            self.show_success("Lookahead plan saved")
            return True
        return False

    def refresh(self):
        self.show_progress("Refreshing data...")
        self.lookahead_tab.load_lookahead_plan()
        self.npt_tab.load_npt_data()
        self.code_tab.load_codes()
        self.show_success("Data refreshed")