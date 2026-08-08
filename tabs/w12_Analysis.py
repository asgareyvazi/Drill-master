"""
Advanced Analysis and Monitoring Tab for Drilling Software
PySide6 Version – Fully refactored with SelectionManager integration
"""
import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta
from sqlalchemy import func, desc
import logging
import json
import tempfile
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtGui import *
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from core.common_widgets import safe_replace_chart

from core.managers import StatusBarManager, TableManager, ExportManager, setup_widget_with_managers

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


try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
    pg.setConfigOption("background", "#1e1e1e")
    pg.setConfigOption("foreground", "#ffffff")
    pg.setConfigOption("antialias", True)
    try:
        pg.setConfigOptions(useOpenGL=True)
    except Exception:
        pass  # OpenGL اختیاری است
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    pg = None
    logger.warning(
        "pyqtgraph not installed - charts disabled. "
        "Install with: pip install pyqtgraph"
    )

import matplotlib.colors as mcolors

from core.database import (
    Company, Project, Well, Section, DailyReport, TimeLog24H,
    TimeLogMorning, User, DrillingParameters, MudReport,
    CementReport, CasingReport, WellboreSchematic,
    TripSheetEntry, SurveyPoint, TrajectoryCalculation, TrajectoryPlot,
    BitReport, BHAReport, DownholeEquipment, FormationReport,
    LogisticsPersonnel, ServiceCompanyPOB, FuelWaterInventory,
    BulkMaterials, TransportLog, TransportNotes,
    SafetyReport, SafetyIncident, BOPComponent, WasteRecord,
    ServiceCompany, ServiceNote, MaterialRequest, EquipmentLog,
    SevenDaysLookahead, NPTReport, ActivityCode, TimeDepthData, ROPAnalysis,
    ExportTemplate, DatabaseManager
)
from core.base_tab import DrillTabBase
from core.selection_manager import SelectionManager
from core.data_quality import DataQualityService

logger = logging.getLogger(__name__)


class AnalysisWidget(DrillTabBase):
    """Advanced Professional Analysis and Monitoring Dashboard – PySide6 Version"""

    def __init__(self, db_manager, parent=None):
        super().__init__("AnalysisWidget", db_manager, parent)
        self.db = db_manager
        self.current_well_id = None
        self.current_well_name = None
        self.current_report_id = None
        self.quality_service = DataQualityService(self.db)
        self.quality_label = QLabel("Data Quality: —")
        self.quality_label.setToolTip("Completeness and time-log coverage for the selected report")
        self.quality_label.setStyleSheet("font-weight: bold; padding: 5px; color: #7f8c8d;")

        # Data caches
        self.data_cache = {}
        self.cache_time = {}
        self.cache_timeout = 30000  # 30 seconds
        
        self.kpi_cards = []
        # Chart data storage
        self.chart_data = {
            'time_depth': None,
            'npt': None,
            'performance': None,
            'daily': None,
            'analytics': None
        }

        # Performance KPI cards
        self.perf_kpi_cards = []

        # Today's indicators
        self.today_indicators = {}

        # PyQtGraph configuration
        if PYQTGRAPH_AVAILABLE:

            pg.setConfigOption("background", "#1e1e1e")
            pg.setConfigOption("foreground", "#ffffff")
            pg.setConfigOption("antialias", True)
            try:
                pg.setConfigOptions(useOpenGL=True)
            except Exception:
                pass

        # Auto-update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.auto_update_data)

        # Export directory
        base_dir = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        self.export_dir = os.path.join(base_dir, "exports", "analysis")
        try:
            os.makedirs(self.export_dir, exist_ok=True)
        except PermissionError:
            # fallback به پوشه temp
            import tempfile
            self.export_dir = os.path.join(
                tempfile.gettempdir(), "drillmaster_exports"
            )
            os.makedirs(self.export_dir, exist_ok=True)
            logger.warning(
                f"Using temp dir for exports: {self.export_dir}"
            )

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        if not PYQTGRAPH_AVAILABLE:
            notice = QLabel(
                "⚠️ pyqtgraph is not installed.\n"
                "Install it with: pip install pyqtgraph\n"
                "Charts are disabled."
            )
            notice.setAlignment(Qt.AlignCenter)
            notice.setStyleSheet(
                "color: #e74c3c; font-size: 14px; padding: 30px;"
            )
            layout.addWidget(notice)
            layout.addWidget(self.quality_label)
            return

        # ---- HEADER SECTION ----
        header_widget = QWidget()
        header_widget.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2c3e50, stop:1 #34495e);
                border-radius: 12px;
                padding: 15px;
                margin: 5px;
            }
        """)
        header_layout = QGridLayout(header_widget)

        self.status_label = QLabel("🔴 No well selected")
        self.status_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #e74c3c;
                padding: 8px;
            }
        """)
        header_layout.addWidget(self.status_label, 0, 0, 1, 2)
        header_layout.addWidget(self.quality_label, 1, 0, 1, 2)

        self.well_label = QLabel("🌍 Well: Not Selected")
        self.well_label.setStyleSheet("font-size: 14px; color: #bdc3c7;")
        header_layout.addWidget(self.well_label, 1, 0, 1, 2)

        self.kpi_cards_widget = self.create_enhanced_kpi_cards()
        header_layout.addWidget(self.kpi_cards_widget, 0, 2, 2, 3)

        # Monitoring controls
        control_widget = QWidget()
        control_layout = QHBoxLayout(control_widget)

        self.last_update_label = QLabel("Last update: --:--:--")
        self.last_update_label.setStyleSheet("color: #95a5a6; font-size: 12px;")
        control_layout.addWidget(self.last_update_label)

        control_layout.addStretch()

        self.auto_update_interval = QComboBox()
        self.auto_update_interval.addItems(["5 seconds", "10 seconds", "30 seconds", "1 minute", "5 minutes"])
        self.auto_update_interval.setCurrentIndex(1)
        self.auto_update_interval.setStyleSheet("""
            QComboBox {
                background: #34495e;
                color: white;
                border: 1px solid #2c3e50;
                border-radius: 4px;
                padding: 5px;
                min-width: 120px;
            }
        """)
        control_layout.addWidget(QLabel("Auto Update:"))
        control_layout.addWidget(self.auto_update_interval)

        self.auto_update_check = QCheckBox("🔄 Auto Update")
        self.auto_update_check.setChecked(False)
        self.auto_update_check.setStyleSheet("""
            QCheckBox {
                font-size: 13px;
                color: #ecf0f1;
                padding: 8px;
            }
        """)
        self.auto_update_check.stateChanged.connect(self.toggle_auto_update)
        control_layout.addWidget(self.auto_update_check)

        refresh_btn = QPushButton("🔄 Refresh Now")
        refresh_btn.setStyleSheet(self.get_button_style("primary", large=True))
        refresh_btn.clicked.connect(self.update_all_data)
        control_layout.addWidget(refresh_btn)

        clear_cache_btn = QPushButton("🗑️ Clear Cache")
        clear_cache_btn.setStyleSheet(self.get_button_style("warning"))
        clear_cache_btn.clicked.connect(self.clear_cache)
        control_layout.addWidget(clear_cache_btn)

        header_layout.addWidget(control_widget, 2, 0, 1, 5)
        layout.addWidget(header_widget)

        # Help message (hidden when a well is selected)
        self.help_label = QLabel(
            "📋 Please select a well from the Well Info tab to start analysis.\n"
            "After opening a well, analysis data will automatically load."
        )
        self.help_label.setAlignment(Qt.AlignCenter)
        self.help_label.setStyleSheet("""
            QLabel {
                color: #7f8c8d;
                font-style: italic;
                padding: 25px;
                background: #ecf0f110;
                border-radius: 8px;
                margin: 10px;
            }
        """)
        layout.addWidget(self.help_label)

        # Analysis tabs
        self.analysis_tabs = QTabWidget()
        self.analysis_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 2px solid #34495e;
                border-radius: 8px;
                background: #2c3e50;
                margin-top: 5px;
            }
            QTabBar::tab {
                background: #34495e;
                color: #ecf0f1;
                padding: 12px 24px;
                margin-right: 3px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3498db, stop:1 #2980b9);
                color: white;
            }
            QTabBar::tab:hover {
                background: #3c5570;
            }
        """)

        self.time_depth_tab = self.create_time_depth_tab()
        self.npt_tab = self.create_npt_tab()
        self.performance_tab = self.create_performance_tab()
        self.daily_tab = self.create_daily_tab()
        self.analytics_tab = self.create_analytics_tab()

        self.analysis_tabs.addTab(self.time_depth_tab, "📈 Time vs Depth")
        self.analysis_tabs.addTab(self.npt_tab, "⏱️ NPT Analysis")
        self.analysis_tabs.addTab(self.performance_tab, "⚡ Performance")
        self.analysis_tabs.addTab(self.daily_tab, "📅 Daily Monitor")
        self.analysis_tabs.addTab(self.analytics_tab, "📊 Advanced Analytics")

        self.analysis_tabs.setVisible(False)
        layout.addWidget(self.analysis_tabs)

        # Bottom action buttons
        bottom_widget = QWidget()
        bottom_widget.setStyleSheet("background: #34495e; border-radius: 8px; padding: 10px;")
        bottom_layout = QHBoxLayout(bottom_widget)

        self.export_dashboard_btn = QPushButton("📊 Export Dashboard")
        self.export_dashboard_btn.setStyleSheet(self.get_button_style("success", large=True))
        self.export_dashboard_btn.clicked.connect(self.export_dashboard)

        self.export_chart_btn = QPushButton("📤 Export Charts")
        self.export_chart_btn.setStyleSheet(self.get_button_style("info", large=True))
        self.export_chart_btn.clicked.connect(self.export_all_charts)

        self.print_report_btn = QPushButton("🖨️ Print Report")
        self.print_report_btn.setStyleSheet(self.get_button_style("warning", large=True))
        self.print_report_btn.clicked.connect(self.print_comprehensive_report)

        self.export_data_btn = QPushButton("📁 Export Data")
        self.export_data_btn.setStyleSheet(self.get_button_style("primary", large=True))
        self.export_data_btn.clicked.connect(self.export_all_data)

        bottom_layout.addWidget(self.export_dashboard_btn)
        bottom_layout.addWidget(self.export_chart_btn)
        bottom_layout.addWidget(self.print_report_btn)
        bottom_layout.addWidget(self.export_data_btn)
        bottom_layout.addStretch()

        layout.addWidget(bottom_widget)
        bottom_widget.setVisible(False)
        self.bottom_widget = bottom_widget

    # ---- UI Helper methods ----
    def get_button_style(self, button_type="default", large=False):
        size = "16px" if large else "14px"
        padding = "14px 28px" if large else "12px 24px"
        styles = {
            "default": f"""
                QPushButton {{
                    background: #34495e;
                    color: white;
                    border: none;
                    padding: {padding};
                    border-radius: 6px;
                    font-size: {size};
                    font-weight: bold;
                }}
                QPushButton:hover {{ background: #3c5570; }}
            """,
            "primary": f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3498db, stop:1 #2980b9);
                    color: white;
                    border: none;
                    padding: {padding};
                    border-radius: 8px;
                    font-size: {size};
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2980b9, stop:1 #2573a7);
                }}
            """,
            "success": f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2ecc71, stop:1 #27ae60);
                    color: white;
                    border: none;
                    padding: {padding};
                    border-radius: 8px;
                    font-size: {size};
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #27ae60, stop:1 #229954);
                }}
            """,
            "info": f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9b59b6, stop:1 #8e44ad);
                    color: white;
                    border: none;
                    padding: {padding};
                    border-radius: 8px;
                    font-size: {size};
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8e44ad, stop:1 #7d3c98);
                }}
            """,
            "warning": f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f39c12, stop:1 #e67e22);
                    color: white;
                    border: none;
                    padding: {padding};
                    border-radius: 8px;
                    font-size: {size};
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e67e22, stop:1 #d35400);
                }}
            """,
        }
        return styles.get(button_type, styles["default"])

    def create_enhanced_kpi_cards(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        kpi_data = [
            {"icon": "🎯", "title": "Current Depth", "value": "0", "unit": "m", "color": "#3498DB", "trend": "↗️ +0.0m"},
            {"icon": "📅", "title": "Rig Days", "value": "0", "unit": "days", "color": "#2ECC71", "trend": "Day 0"},
            {"icon": "⚡", "title": "Avg ROP", "value": "0.0", "unit": "m/hr", "color": "#E74C3C", "trend": "↗️ +0.0"},
            {"icon": "⏱️", "title": "Total NPT", "value": "0.0", "unit": "hrs", "color": "#F39C12", "trend": "↘️ 0%"},
        ]
        for kpi in kpi_data:
            card = self.create_kpi_card_modern(**kpi)
            layout.addWidget(card)
            self.kpi_cards.append(card)
        return widget

    def create_kpi_card_modern(self, icon, title, value, unit, color, trend=""):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {color}30, stop:1 {color}10);
                border-radius: 10px;
                border: 2px solid {color}40;
                padding: 12px;
                margin: 5px;
            }}
        """)
        layout = QVBoxLayout(card)
        header = QHBoxLayout()
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"font-size: 28px; color: {color};")
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #7f8c8d;")
        header.addWidget(icon_label)
        header.addWidget(title_label)
        header.addStretch()
        layout.addLayout(header)

        value_layout = QHBoxLayout()
        value_label = QLabel(value)
        value_label.setStyleSheet(f"font-size: 26px; font-weight: bold; color: {color};")
        unit_label = QLabel(unit)
        unit_label.setStyleSheet("font-size: 14px; color: #95a5a6; margin-top: 8px;")
        value_layout.addWidget(value_label)
        value_layout.addWidget(unit_label)
        value_layout.addStretch()
        layout.addLayout(value_layout)

        if trend:
            trend_label = QLabel(trend)
            trend_label.setStyleSheet("font-size: 11px; color: #95a5a6;")
            layout.addWidget(trend_label)

        card.value_label = value_label
        card.trend_label = trend_label if trend else None
        return card

    def create_time_depth_tab(self):
        # ایجاد scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # محتوای اصلی
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setSpacing(10)
        
        # === کنترل‌ها ===
        control_widget = QWidget()
        control_widget.setStyleSheet("background: #34495e; border-radius: 6px; padding: 8px;")
        control_layout = QHBoxLayout(control_widget)
        control_layout.addWidget(QLabel("📊 Time vs Depth Analysis"))
        
        self.td_show_trend = QCheckBox("📈 Show Trend Line")
        self.td_show_trend.setChecked(True)
        self.td_show_trend.setStyleSheet("color: #ecf0f1;")
        self.td_show_projection = QCheckBox("🔮 Show Projection")
        self.td_show_projection.setChecked(False)
        self.td_show_projection.setStyleSheet("color: #ecf0f1;")
        self.td_export_btn = QPushButton("📤 Export Chart")
        self.td_export_btn.setStyleSheet(self.get_button_style("primary"))
        self.td_export_btn.clicked.connect(lambda: self.export_chart_image("time_depth"))
        
        control_layout.addWidget(self.td_show_trend)
        control_layout.addWidget(self.td_show_projection)
        control_layout.addStretch()
        control_layout.addWidget(self.td_export_btn)
        main_layout.addWidget(control_widget)
        
        # === نمودارها ===
        chart_container = QWidget()
        chart_container.setStyleSheet("background: #1e1e1e; border-radius: 8px;")
        chart_layout = QVBoxLayout(chart_container)
        
        self.time_depth_plot = pg.PlotWidget()
        self.time_depth_plot.setBackground("#1e1e1e")
        self.time_depth_plot.setLabel("left", "Depth (m)", color="#ffffff", size=14)
        self.time_depth_plot.setLabel("bottom", "Time (Days)", color="#ffffff", size=14)
        self.time_depth_plot.showGrid(x=True, y=True, alpha=0.3)
        self.time_depth_plot.setMinimumHeight(300)
        chart_layout.addWidget(self.time_depth_plot)
        
        self.daily_gain_plot = pg.PlotWidget()
        self.daily_gain_plot.setBackground("#1e1e1e")
        self.daily_gain_plot.setLabel("left", "Daily Gain (m)", color="#ffffff", size=12)
        self.daily_gain_plot.setLabel("bottom", "Days", color="#ffffff", size=12)
        self.daily_gain_plot.showGrid(x=True, y=True, alpha=0.3)
        self.daily_gain_plot.setMaximumHeight(150)
        chart_layout.addWidget(self.daily_gain_plot)
        main_layout.addWidget(chart_container)
        
        # === جدول ===
        table_widget = QWidget()
        table_widget.setStyleSheet("background: #2c3e50; border-radius: 8px; padding: 8px;")
        table_layout = QVBoxLayout(table_widget)
        table_layout.addWidget(QLabel("📋 Depth History"))
        
        self.time_depth_table = QTableWidget()
        self.time_depth_table.setColumnCount(5)
        self.time_depth_table.setHorizontalHeaderLabels(
            ["📅 Date", "#️⃣ Days", "📏 Depth (m)", "📈 Daily Gain", "🔧 Status"]
        )
        self.time_depth_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.time_depth_table.setStyleSheet("""
            QTableWidget {
                background: #1e1e1e;
                alternate-background-color: #2c3e50;
                gridline-color: #34495e;
                font-size: 12px;
            }
            QTableWidget::item { padding: 6px; color: #ecf0f1; }
            QHeaderView::section {
                background: #34495e;
                color: #ecf0f1;
                padding: 8px;
                font-weight: bold;
            }
        """)
        self.time_depth_table.setMinimumHeight(200)
        table_layout.addWidget(self.time_depth_table)
        main_layout.addWidget(table_widget)
        
        main_layout.addStretch()
        
        scroll.setWidget(content)
        return scroll
        
    def create_performance_tab(self):
        """Create Performance Dashboard tab with scroll"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setSpacing(10)
        
        # Performance KPI Cards (6 cards in grid)
        kpi_widget = QWidget()
        kpi_widget.setStyleSheet("background: #34495e; border-radius: 8px; padding: 12px;")
        kpi_layout = QGridLayout(kpi_widget)
        
        perf_kpis = [
            ("⚡", "Avg ROP", "0.0", "m/hr", "#1abc9c"),
            ("🏆", "Best ROP", "0.0", "m/hr", "#e67e22"),
            ("🔧", "Avg WOB", "0.0", "klb", "#3498db"),
            ("🌀", "Avg RPM", "0", "rpm", "#9b59b6"),
            ("💪", "Avg Torque", "0.0", "klb.ft", "#e74c3c"),
            ("📈", "Efficiency", "0.0", "%", "#2ecc71"),
        ]
        
        self.perf_kpi_cards = []
        for i, (icon, title, value, unit, color) in enumerate(perf_kpis):
            row, col = divmod(i, 3)
            card = self.create_stat_card(icon, title, value, unit, color)
            kpi_layout.addWidget(card, row, col)
            self.perf_kpi_cards.append(card)
        
        main_layout.addWidget(kpi_widget)
        
        # Performance Chart
        charts_widget = QWidget()
        charts_widget.setStyleSheet("background: #1e1e1e; border-radius: 8px;")
        charts_widget.setMinimumHeight(350)
        charts_layout = QVBoxLayout(charts_widget)
        
        # Chart controls
        chart_control = QHBoxLayout()
        chart_control.addWidget(QLabel("📊 Performance Metrics"))
        chart_control.addStretch()
        
        export_perf_btn = QPushButton("📤 Export Chart")
        export_perf_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background: #2980b9; }
        """)
        export_perf_btn.clicked.connect(lambda: self.export_chart_image("performance"))
        chart_control.addWidget(export_perf_btn)
        charts_layout.addLayout(chart_control)
        
        self.performance_plot = pg.PlotWidget()
        self.performance_plot.setBackground("#1e1e1e")
        self.performance_plot.setLabel("left", "Performance Metrics", color="#ffffff", size=14)
        self.performance_plot.setLabel("bottom", "Bit Run #", color="#ffffff", size=14)
        self.performance_plot.addLegend()
        self.performance_plot.setMinimumHeight(300)
        charts_layout.addWidget(self.performance_plot)
        
        main_layout.addWidget(charts_widget)
        
        # Performance Data Table
        table_widget = QWidget()
        table_widget.setStyleSheet("background: #2c3e50; border-radius: 8px; padding: 8px;")
        table_layout = QVBoxLayout(table_widget)
        
        table_header = QHBoxLayout()
        table_header.addWidget(QLabel("📋 Performance Data"))
        
        export_data_btn = QPushButton("📤 Export Data")
        export_data_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background: #229954; }
        """)
        export_data_btn.clicked.connect(self.export_all_data)
        table_header.addStretch()
        table_header.addWidget(export_data_btn)
        table_layout.addLayout(table_header)
        
        self.performance_table = QTableWidget()
        self.performance_table.setColumnCount(7)
        self.performance_table.setHorizontalHeaderLabels(
            ["📅 Date", "🧱 Bit Run", "⚡ ROP", "🔧 WOB", "🌀 RPM", "💪 Torque", "📊 Pressure"]
        )
        self.performance_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.performance_table.setMinimumHeight(250)
        self.performance_table.setMaximumHeight(400)
        self.performance_table.setStyleSheet("""
            QTableWidget {
                background: #1e1e1e;
                alternate-background-color: #2c3e50;
                gridline-color: #34495e;
                font-size: 12px;
            }
            QTableWidget::item { padding: 6px; color: #ecf0f1; }
            QHeaderView::section {
                background: #34495e;
                color: #ecf0f1;
                padding: 8px;
                font-weight: bold;
            }
        """)
        table_layout.addWidget(self.performance_table)
        main_layout.addWidget(table_widget)
        
        main_layout.addStretch()
        scroll.setWidget(content)
        return scroll
        
    def create_npt_tab(self):
        """Create NPT Analysis tab with scroll"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setSpacing(10)
        
        # NPT Statistics Cards
        stats_widget = QWidget()
        stats_widget.setStyleSheet("background: #34495e; border-radius: 8px; padding: 12px;")
        stats_layout = QGridLayout(stats_widget)
        
        self.npt_total_card = self.create_stat_card("⏱️", "Total NPT", "0.0", "hours", "#e74c3c")
        self.npt_percent_card = self.create_stat_card("📊", "NPT %", "0.0", "%", "#f39c12")
        self.npt_daily_card = self.create_stat_card("📅", "Daily Avg", "0.0", "hours/day", "#3498db")
        self.npt_category_card = self.create_stat_card("🔥", "Top Category", "-", "category", "#9b59b6")
        
        stats_layout.addWidget(self.npt_total_card, 0, 0)
        stats_layout.addWidget(self.npt_percent_card, 0, 1)
        stats_layout.addWidget(self.npt_daily_card, 1, 0)
        stats_layout.addWidget(self.npt_category_card, 1, 1)
        main_layout.addWidget(stats_widget)
        
        # NPT Pie Chart
        chart_container = QWidget()
        chart_container.setStyleSheet("background: #1e1e1e; border-radius: 8px;")
        chart_container.setMinimumHeight(300)
        chart_layout = QVBoxLayout(chart_container)
        
        self.npt_pie_plot = pg.PlotWidget()
        self.npt_pie_plot.setBackground("#1e1e1e")
        self.npt_pie_plot.setTitle("NPT Distribution by Category", color="#ffffff", size="14pt")
        self.npt_pie_plot.setMinimumHeight(280)
        chart_layout.addWidget(self.npt_pie_plot)
        main_layout.addWidget(chart_container)
        
        # NPT Events Table
        table_widget = QWidget()
        table_widget.setStyleSheet("background: #2c3e50; border-radius: 8px; padding: 8px;")
        table_layout = QVBoxLayout(table_widget)
        
        table_header = QHBoxLayout()
        table_header.addWidget(QLabel("📋 NPT Events"))
        
        export_npt_btn = QPushButton("📤 Export NPT")
        export_npt_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background: #2980b9; }
        """)
        export_npt_btn.clicked.connect(lambda: self.export_chart_image("npt"))
        table_header.addStretch()
        table_header.addWidget(export_npt_btn)
        table_layout.addLayout(table_header)
        
        self.npt_table = QTableWidget()
        self.npt_table.setColumnCount(6)
        self.npt_table.setHorizontalHeaderLabels(
            ["📅 Date", "🕐 From", "🕒 To", "⏱️ Hours", "🏷️ Category", "📝 Description"]
        )
        self.npt_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.npt_table.setMinimumHeight(250)
        self.npt_table.setMaximumHeight(400)
        self.npt_table.setStyleSheet("""
            QTableWidget {
                background: #1e1e1e;
                alternate-background-color: #2c3e50;
                gridline-color: #34495e;
                font-size: 12px;
            }
            QTableWidget::item { padding: 6px; color: #ecf0f1; }
            QHeaderView::section {
                background: #34495e;
                color: #ecf0f1;
                padding: 8px;
                font-weight: bold;
            }
        """)
        table_layout.addWidget(self.npt_table)
        main_layout.addWidget(table_widget)
        
        main_layout.addStretch()
        scroll.setWidget(content)
        return scroll
        
    def create_stat_card(self, icon, title, value, unit, color):
        """Create a statistical card widget."""
        card = QFrame()
        card.setStyleSheet(
            f"""
            QFrame {{
                background: {color}20;
                border-left: 4px solid {color};
                border-radius: 6px;
                padding: 10px;
                margin: 5px;
            }}
            """
            )
        layout = QVBoxLayout(card)

        title_label = QLabel(f"{icon} {title}")
        title_label.setStyleSheet("font-size: 13px; color: #7f8c8d; font-weight: bold;")
        layout.addWidget(title_label)

        value_label = QLabel(f"<b>{value}</b> {unit}")
        value_label.setStyleSheet(f"font-size: 18px; color: {color};")
        layout.addWidget(value_label)

        card.value_label = value_label
        return card
    
    def create_daily_tab(self):
        """Create Daily Monitor tab with scroll"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setSpacing(10)
        
        # Today's Summary Panel (gradient background)
        today_widget = QWidget()
        today_widget.setMinimumHeight(200)
        today_widget.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a2980, stop:1 #26d0ce);
                border-radius: 10px;
                padding: 15px;
                margin: 5px;
            }
            QLabel {
                color: white;
            }
        """)
        today_layout = QGridLayout(today_widget)
        today_layout.setSpacing(15)
        
        today_labels = [
            ("🎯", "Current Depth", "depth_meter"),
            ("🚀", "Today's ROP", "rop_meter"),
            ("⏱️", "Hours Today", "hours"),
            ("📅", "Rig Day", "days"),
            ("📉", "Today's NPT", "npt_hours"),
            ("🌡️", "MW In/Out", "mw_pcf"),
        ]
        
        self.today_indicators = {}
        for i, (icon, title, key) in enumerate(today_labels):
            row, col = divmod(i, 3)
            
            # Title
            label_title = QLabel(f"{icon} {title}")
            label_title.setStyleSheet("font-size: 14px; font-weight: bold;")
            today_layout.addWidget(label_title, row * 2, col)
            
            # Value
            label_value = QLabel("--")
            label_value.setStyleSheet("""
                QLabel {
                    font-size: 24px;
                    font-weight: bold;
                    color: white;
                    padding: 8px;
                    background: rgba(255, 255, 255, 0.15);
                    border-radius: 6px;
                    min-width: 120px;
                }
            """)
            label_value.setAlignment(Qt.AlignCenter)
            today_layout.addWidget(label_value, row * 2 + 1, col)
            self.today_indicators[key] = label_value
        
        main_layout.addWidget(today_widget)
        
        # Recent Reports Table
        table_widget = QWidget()
        table_widget.setStyleSheet("background: #2c3e50; border-radius: 8px; padding: 8px;")
        table_layout = QVBoxLayout(table_widget)
        
        table_header = QHBoxLayout()
        table_header.addWidget(QLabel("📋 Recent Reports (Last 10)"))
        table_header.addStretch()
        
        refresh_daily_btn = QPushButton("🔄 Refresh")
        refresh_daily_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background: #2980b9; }
        """)
        refresh_daily_btn.clicked.connect(self.update_daily_data)
        table_header.addWidget(refresh_daily_btn)
        table_layout.addLayout(table_header)
        
        self.recent_reports_table = QTableWidget()
        self.recent_reports_table.setColumnCount(4)
        self.recent_reports_table.setHorizontalHeaderLabels(
            ["📅 Date", "#️⃣ Rig Day", "📏 Depth", "🔧 Main Activity"]
        )
        self.recent_reports_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.recent_reports_table.setMinimumHeight(300)
        self.recent_reports_table.setMaximumHeight(450)
        self.recent_reports_table.setStyleSheet("""
            QTableWidget {
                background: #1e1e1e;
                alternate-background-color: #2c3e50;
                gridline-color: #34495e;
                font-size: 12px;
            }
            QTableWidget::item { padding: 6px; color: #ecf0f1; }
            QHeaderView::section {
                background: #34495e;
                color: #ecf0f1;
                padding: 8px;
                font-weight: bold;
            }
        """)
        table_layout.addWidget(self.recent_reports_table)
        main_layout.addWidget(table_widget)
        
        main_layout.addStretch()
        scroll.setWidget(content)
        return scroll
        
    def create_analytics_tab(self):
        """Create Advanced Analytics tab with scroll"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setSpacing(10)
        
        # Controls
        control_widget = QWidget()
        control_widget.setStyleSheet("background: #34495e; border-radius: 6px; padding: 10px;")
        control_layout = QHBoxLayout(control_widget)
        control_layout.addWidget(QLabel("📊 Advanced Analytics"))
        
        self.analytics_type = QComboBox()
        self.analytics_type.addItems([
            "ROP Prediction", "NPT Forecasting", "Cost Analysis", "Risk Assessment"
        ])
        self.analytics_type.setMinimumWidth(200)
        self.analytics_type.setStyleSheet("""
            QComboBox {
                background: #2c3e50;
                color: white;
                border: 1px solid #34495e;
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background: #2c3e50;
                color: white;
                selection-background-color: #3498db;
            }
        """)
        self.analytics_type.currentTextChanged.connect(self.update_analytics)
        control_layout.addWidget(self.analytics_type)
        
        control_layout.addStretch()
        
        analyze_btn = QPushButton("🔍 Run Analysis")
        analyze_btn.setStyleSheet(self.get_button_style("primary"))
        analyze_btn.clicked.connect(self.run_advanced_analysis)
        control_layout.addWidget(analyze_btn)
        
        export_analytics_btn = QPushButton("📤 Export")
        export_analytics_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover { background: #229954; }
        """)
        export_analytics_btn.clicked.connect(lambda: self.export_chart_image("analytics"))
        control_layout.addWidget(export_analytics_btn)
        
        main_layout.addWidget(control_widget)
        
        # Chart
        chart_widget = QWidget()
        chart_widget.setStyleSheet("background: #1e1e1e; border-radius: 8px;")
        chart_widget.setMinimumHeight(350)
        chart_layout_widget = QVBoxLayout(chart_widget)
        
        self.analytics_plot = pg.PlotWidget()
        self.analytics_plot.setBackground("#1e1e1e")
        self.analytics_plot.setLabel("left", "Value", color="#ffffff", size=14)
        self.analytics_plot.setLabel("bottom", "Parameter", color="#ffffff", size=14)
        self.analytics_plot.showGrid(x=True, y=True, alpha=0.3)
        self.analytics_plot.addLegend()
        self.analytics_plot.setMinimumHeight(320)
        chart_layout_widget.addWidget(self.analytics_plot)
        main_layout.addWidget(chart_widget)
        
        # Results Text
        results_widget = QWidget()
        results_widget.setStyleSheet("background: #2c3e50; border-radius: 8px; padding: 8px;")
        results_layout = QVBoxLayout(results_widget)
        
        results_header = QHBoxLayout()
        results_header.addWidget(QLabel("📋 Analysis Results"))
        results_header.addStretch()
        
        copy_results_btn = QPushButton("📋 Copy")
        copy_results_btn.setStyleSheet("""
            QPushButton {
                background: #7f8c8d;
                color: white;
                border: none;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background: #6c7a89; }
        """)
        copy_results_btn.clicked.connect(self._copy_results_to_clipboard)
        results_header.addWidget(copy_results_btn)
        results_layout.addLayout(results_header)
        
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMinimumHeight(200)
        self.results_text.setMaximumHeight(350)
        self.results_text.setStyleSheet("""
            QTextEdit {
                background: #1e1e1e;
                color: #ecf0f1;
                border: 1px solid #34495e;
                border-radius: 4px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
                padding: 10px;
            }
        """)
        results_layout.addWidget(self.results_text)
        main_layout.addWidget(results_widget)
        
        milestones_group = QGroupBox("🏔️ Milestones (FACT vs PLAN)")
        milestones_layout = QVBoxLayout()
        self.milestones_widget = QWidget()
        self.milestones_widget.setLayout(QVBoxLayout())
        milestones_layout.addWidget(self.milestones_widget)
        milestones_group.setLayout(milestones_layout)
        main_layout.addWidget(milestones_group)
        
        main_layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _copy_results_to_clipboard(self):
        """Copy analysis results to clipboard"""
        text = self.results_text.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.show_message("Results copied to clipboard", 2000)
            
    # ==================== DATA PROCESSING ====================
    def clear_cache(self):
        self.data_cache.clear()
        self.cache_time.clear()

    def get_cached_data(self, key, get_data_func):
        now = QDateTime.currentMSecsSinceEpoch()
        if key in self.data_cache and (now - self.cache_time[key] < self.cache_timeout):
            return self.data_cache[key]
        data = get_data_func()
        self.data_cache[key] = data
        self.cache_time[key] = now
        return data

    def calculate_kpis(self, session):
        well_id = self.current_well_id
        if not well_id:
            return dict.fromkeys(['current_depth','total_days','avg_rop','total_npt',
                                  'npt_percentage','best_rop','avg_wob','avg_rpm',
                                  'avg_torque','efficiency','daily_gain'], 0)

        latest = session.query(DailyReport).filter_by(well_id=well_id)\
                        .order_by(desc(DailyReport.report_date)).first()
        cur_depth = latest.depth_2400 if latest else 0
        total_days = session.query(DailyReport).filter_by(well_id=well_id).count()

        avg_rop = session.query(func.avg(DrillingParameters.avg_rop))\
                         .filter(DrillingParameters.well_id == well_id).scalar() or 0
        best_rop = session.query(func.max(DrillingParameters.avg_rop))\
                          .filter(DrillingParameters.well_id == well_id).scalar() or 0

        wob_vals = session.query(DrillingParameters.wob_min, DrillingParameters.wob_max)\
                          .filter(DrillingParameters.well_id == well_id).all()
        avg_wob = np.mean([(wmin+wmax)/2 for wmin,wmax in wob_vals if wmin is not None and wmax is not None]) if wob_vals else 0

        rpm_vals = session.query(DrillingParameters.rpm_min, DrillingParameters.rpm_max)\
                          .filter(DrillingParameters.well_id == well_id).all()
        avg_rpm = np.mean([(rmin+rmax)/2 for rmin,rmax in rpm_vals if rmin is not None and rmax is not None]) if rpm_vals else 0

        tq_vals = session.query(DrillingParameters.torque_min, DrillingParameters.torque_max)\
                         .filter(DrillingParameters.well_id == well_id).all()
        avg_torque = np.mean([(tmin+tmax)/2 for tmin,tmax in tq_vals if tmin is not None and tmax is not None]) if tq_vals else 0

        total_npt = session.query(func.sum(TimeLog24H.duration)).filter(TimeLog24H.is_npt == True)\
                           .join(DailyReport).filter(DailyReport.well_id == well_id).scalar() or 0
        total_hours = session.query(func.sum(TimeLog24H.duration))\
                             .join(DailyReport).filter(DailyReport.well_id == well_id).scalar() or 1
        npt_pct = (total_npt / total_hours * 100)

        efficiency = 100 - npt_pct

        daily_gain = 0
        if total_days > 0:
            first = session.query(DailyReport).filter_by(well_id=well_id)\
                           .order_by(DailyReport.report_date).first()
            if first and latest:
                daily_gain = (latest.depth_2400 - first.depth_2400) / total_days

        return {
            'current_depth': cur_depth,
            'total_days': total_days,
            'avg_rop': avg_rop,
            'total_npt': total_npt,
            'npt_percentage': npt_pct,
            'best_rop': best_rop,
            'avg_wob': avg_wob,
            'avg_rpm': avg_rpm,
            'avg_torque': avg_torque,
            'efficiency': efficiency,
            'daily_gain': daily_gain
        }

    def get_today_data(self, session):
        well_id = self.current_well_id
        if not well_id:
            return None
        today = date.today()
        report = session.query(DailyReport).filter_by(well_id=well_id, report_date=today).first()
        if not report:
            report = session.query(DailyReport).filter_by(well_id=well_id)\
                            .order_by(desc(DailyReport.report_date)).first()
        if not report:
            return None
        npt_hours = session.query(func.sum(TimeLog24H.duration))\
                           .filter(TimeLog24H.report_id == report.id, TimeLog24H.is_npt == True).scalar() or 0
        hours = session.query(func.sum(TimeLog24H.duration))\
                       .filter(TimeLog24H.report_id == report.id).scalar() or 0
        dr = session.query(DrillingParameters).filter(
            DrillingParameters.well_id == well_id,
            DrillingParameters.report_date == report.report_date).first()
        mud = session.query(MudReport).filter(MudReport.well_id == well_id,
                                               MudReport.report_date == report.report_date).first()
        return {
            'depth': report.depth_2400 or 0,
            'rop': dr.avg_rop if dr and dr.avg_rop else 0,
            'hours': hours,
            'rig_day': report.rig_day or 0,
            'npt_hours': npt_hours,
            'mw_in': mud.mw if mud and mud.mw else 0,
            'mw_out': mud.mw if mud and mud.mw else 0,
            'main_activity': 'Drilling',
            'wob': ((dr.wob_min or 0) + (dr.wob_max or 0))/2 if dr else 0,
            'rpm': ((dr.rpm_min or 0) + (dr.rpm_max or 0))/2 if dr else 0,
            'torque': ((dr.torque_min or 0) + (dr.torque_max or 0))/2 if dr else 0,
            'pressure': ((dr.pump_pressure_min or 0) + (dr.pump_pressure_max or 0))/2 if dr else 0
        }

    def get_performance_data(self, session):
        well_id = self.current_well_id
        if not well_id:
            return []
        params = session.query(DrillingParameters).filter(DrillingParameters.well_id == well_id)\
                        .order_by(DrillingParameters.report_date).all()
        return [{
            'date': p.report_date,
            'bit_run': p.bit_no or f"Bit #{i+1}",
            'rop': p.avg_rop or 0,
            'wob': (p.wob_min + p.wob_max)/2 if p.wob_min and p.wob_max else 0,
            'rpm': (p.rpm_min + p.rpm_max)/2 if p.rpm_min and p.rpm_max else 0,
            'torque': (p.torque_min + p.torque_max)/2 if p.torque_min and p.torque_max else 0,
            'pressure': (p.pump_pressure_min + p.pump_pressure_max)/2 if p.pump_pressure_min else 0,
            'depth': p.depth_out or 0
        } for i, p in enumerate(params)]

    def get_time_depth_data(self, session):
        well_id = self.current_well_id
        if not well_id: return []
        reports = session.query(DailyReport).filter_by(well_id=well_id)\
                         .order_by(DailyReport.report_date).all()
        data = []
        prev = 0
        for i, r in enumerate(reports):
            d = r.depth_2400 or 0
            gain = d - prev if i > 0 else d
            data.append({'date': r.report_date, 'day': i+1, 'depth': d, 'gain': gain,
                         'status': 'Normal' if gain > 0 else 'No Progress'})
            prev = d
        return data

    def get_npt_data(self, session):
        well_id = self.current_well_id
        if not well_id:
            return {'entries': [], 'categories': {}, 'total_npt': 0, 'npt_percentage': 0, 'total_hours': 1}
        npt_rows = session.query(TimeLog24H, DailyReport).join(DailyReport)\
                          .filter(DailyReport.well_id == well_id, TimeLog24H.is_npt == True)\
                          .order_by(DailyReport.report_date, TimeLog24H.time_from).all()
        entries = []
        cats = {}
        total_npt = 0.0
        for log, rep in npt_rows:
            h = log.duration or 0
            cat = log.main_code or "Unknown"
            cats[cat] = cats.get(cat, 0) + h
            total_npt += h
            entries.append({
                'date': rep.report_date,
                'from': log.time_from,
                'to': log.time_to,
                'hours': h,
                'category': cat,
                'description': log.activity_description or "",
                'sub_category': log.sub_code or ""
            })
        total_hours = session.query(func.sum(TimeLog24H.duration))\
                             .join(DailyReport).filter(DailyReport.well_id == well_id).scalar() or 1
        pct = (total_npt / total_hours * 100)
        return {'entries': entries, 'categories': cats, 'total_npt': total_npt,
                'npt_percentage': pct, 'total_hours': total_hours}

    # ---- Data update methods ----
    def update_kpi_data(self):
        if not self.current_well_id: return
        def fetch():
            session = self.db.create_session()
            try: return self.calculate_kpis(session)
            finally: session.close()
        kpis = self.get_cached_data(f'kpis_{self.current_well_id}', fetch)
        cards = self.kpi_cards_widget.findChildren(QFrame)
        
        if len(self.kpi_cards) >= 4:
            self.kpi_cards[0].value_label.setText(f"<b>{kpis['current_depth']:.1f}</b> m")
            self.kpi_cards[1].value_label.setText(f"<b>{kpis['total_days']}</b> days")
            self.kpi_cards[2].value_label.setText(f"<b>{kpis['avg_rop']:.1f}</b> m/hr")
            self.kpi_cards[3].value_label.setText(f"<b>{kpis['total_npt']:.1f}</b> hrs")
            

    def update_time_depth_data(self):
        if not self.current_well_id:
            return

        def fetch():
            session = self.db.create_session()
            try:
                return self.get_time_depth_data(session)
            except Exception as e:
                logger.error(f"Time depth fetch error: {e}")
                return []
            finally:
                session.close()

        data = self.get_cached_data(f'td_{self.current_well_id}', fetch)

        if not data:
            # ✅ نمایش پیام به جای crash
            self.time_depth_plot.clear()
            self.time_depth_plot.setTitle(
                "No daily reports found",
                color="#95a5a6"
            )
            self.daily_gain_plot.clear()
            self.time_depth_table.setRowCount(0)
            return

        days = [d['day'] for d in data]
        depths = [d['depth'] for d in data]
        gains = [d['gain'] for d in data]

        self.time_depth_plot.clear()
        self.time_depth_plot.plot(
            days, depths,
            pen=pg.mkPen(color="#3498db", width=3),
            symbol='o', symbolSize=8,
            symbolBrush="#2980b9", name="Depth"
        )

        if (len(days) > 1
                and hasattr(self, 'td_show_trend')
                and self.td_show_trend.isChecked()):
            try:
                z = np.polyfit(days, depths, 1)
                self.time_depth_plot.plot(
                    days, np.polyval(z, days),
                    pen=pg.mkPen(
                        color="#e74c3c", width=2,
                        style=Qt.DashLine
                    ),
                    name="Trend Line"
                )
            except Exception:
                pass

        self.daily_gain_plot.clear()
        self.daily_gain_plot.plot(
            days, gains,
            pen=pg.mkPen(color="#2ecc71", width=2),
            fillLevel=0, brush="#27ae6050",
            name="Daily Gain"
        )

        self.time_depth_table.setRowCount(len(data))
        for i, row in enumerate(data):
            self.time_depth_table.setItem(
                i, 0, QTableWidgetItem(str(row['date']))
            )
            self.time_depth_table.setItem(
                i, 1, QTableWidgetItem(str(row['day']))
            )
            self.time_depth_table.setItem(
                i, 2, QTableWidgetItem(f"{row['depth']:.1f}")
            )
            self.time_depth_table.setItem(
                i, 3, QTableWidgetItem(f"{row['gain']:.1f}")
            )
            self.time_depth_table.setItem(
                i, 4, QTableWidgetItem(row['status'])
            )

        self.chart_data['time_depth'] = {
            'days': days,
            'depths': depths,
            'gains': gains,
            'data': data
        }


    def update_npt_data(self):
        if not self.current_well_id:
            return

        def fetch():
            session = self.db.create_session()
            try:
                return self.get_npt_data(session)
            except Exception as e:
                logger.error(f"NPT fetch error: {e}")
                return {
                    'entries': [],
                    'categories': {},
                    'total_npt': 0,
                    'npt_percentage': 0,
                    'total_hours': 1
                }
            finally:
                session.close()

        data = self.get_cached_data(
            f'npt_{self.current_well_id}', fetch
        )

        self.update_stat_card_value(
            self.npt_total_card, f"{data['total_npt']:.1f}"
        )
        self.update_stat_card_value(
            self.npt_percent_card, f"{data['npt_percentage']:.1f}"
        )

        session = self.db.create_session()
        total_days = session.query(DailyReport).filter_by(
            well_id=self.current_well_id
        ).count()
        session.close()

        daily_avg = (
            data['total_npt'] / total_days if total_days else 0
        )
        self.update_stat_card_value(
            self.npt_daily_card, f"{daily_avg:.1f}"
        )

        top_cat = (
            max(data['categories'], key=data['categories'].get)
            if data['categories'] else "None"
        )
        self.update_stat_card_value(self.npt_category_card, top_cat)

        # ✅ NPT Table با بررسی None
        self.npt_table.setRowCount(len(data['entries']))
        for i, e in enumerate(data['entries']):
            self.npt_table.setItem(
                i, 0, QTableWidgetItem(str(e['date']))
            )

            # ✅ بررسی None برای time objects
            time_from = e.get('from')
            time_to = e.get('to')

            if time_from and hasattr(time_from, 'strftime'):
                self.npt_table.setItem(
                    i, 1,
                    QTableWidgetItem(time_from.strftime("%H:%M"))
                )
            else:
                self.npt_table.setItem(
                    i, 1,
                    QTableWidgetItem(str(time_from or ""))
                )

            if time_to and hasattr(time_to, 'strftime'):
                self.npt_table.setItem(
                    i, 2,
                    QTableWidgetItem(time_to.strftime("%H:%M"))
                )
            else:
                self.npt_table.setItem(
                    i, 2,
                    QTableWidgetItem(str(time_to or ""))
                )

            self.npt_table.setItem(
                i, 3, QTableWidgetItem(f"{e['hours']:.2f}")
            )
            self.npt_table.setItem(
                i, 4, QTableWidgetItem(e['category'])
            )
            self.npt_table.setItem(
                i, 5, QTableWidgetItem(e['description'])
            )

        # ✅ Pie Chart با محافظت
        self.npt_pie_plot.clear()
        if data['categories']:
            self.draw_npt_pie_chart(data['categories'])

        self.chart_data['npt'] = data

    def draw_npt_pie_chart(self, categories):
        if not categories:
            return

        try:
            fig, ax = plt.subplots(figsize=(5, 4), facecolor='#1e1e1e')
            ax.set_facecolor('#1e1e1e')
            
            labels = list(categories.keys())
            sizes = list(categories.values())
            colors = plt.cm.Set3(range(len(labels)))
            
            wedges, texts, autotexts = ax.pie(
                sizes, labels=labels, autopct='%1.1f%%',
                colors=colors, textprops={'color': 'white', 'fontsize': 8},
                wedgeprops={'edgecolor': 'white', 'linewidth': 0.5}
            )
            ax.set_title('NPT by Category', color='white', fontsize=12)
            fig.tight_layout()
            
            canvas = FigureCanvas(fig)
            
            if hasattr(self, 'npt_pie_plot') and self.npt_pie_plot:
                parent_widget = self.npt_pie_plot.parent()
                parent_layout = parent_widget.layout() if parent_widget else None
                
                if parent_layout:
                    parent_layout.removeWidget(self.npt_pie_plot)
                    self.npt_pie_plot.hide()
                    
                    if hasattr(self, '_npt_pie_canvas') and self._npt_pie_canvas:
                        parent_layout.removeWidget(self._npt_pie_canvas)
                        self._npt_pie_canvas.setParent(None)
                        self._npt_pie_canvas.deleteLater()

                    parent_layout.addWidget(canvas)
                    self._npt_pie_canvas = canvas
            
            plt.close(fig)
            
        except Exception as e:
            logger.error(f"Error drawing NPT pie chart: {e}")


    def update_performance_data(self):
        if not self.current_well_id:
            return

        def fetch():
            session = self.db.create_session()
            try:
                return self.get_performance_data(session)
            except Exception as e:
                logger.error(f"Performance fetch error: {e}")
                return []
            finally:
                session.close()

        data = self.get_cached_data(
            f'perf_{self.current_well_id}', fetch
        )

        if not data:
            # ✅ پاک کردن نمودار و جدول
            self.performance_plot.clear()
            self.performance_plot.setTitle(
                "No drilling parameters found",
                color="#95a5a6"
            )
            self.performance_table.setRowCount(0)
            for i in range(len(self.perf_kpi_cards)):
                self.update_perf_kpi_card(i, "0")
            return

        rops = [d['rop'] for d in data if d['rop']]
        wob = [d['wob'] for d in data if d['wob']]
        rpm = [d['rpm'] for d in data if d['rpm']]
        torque = [d['torque'] for d in data if d['torque']]

        avg_rop = np.mean(rops) if rops else 0
        best_rop = max(rops) if rops else 0
        avg_wob = np.mean(wob) if wob else 0
        avg_rpm = np.mean(rpm) if rpm else 0
        avg_torque = np.mean(torque) if torque else 0
        eff = (avg_rop / 20 * 100) if avg_rop > 0 else 0

        self.update_perf_kpi_card(0, f"{avg_rop:.1f}")
        self.update_perf_kpi_card(1, f"{best_rop:.1f}")
        self.update_perf_kpi_card(2, f"{avg_wob:.1f}")
        self.update_perf_kpi_card(3, f"{avg_rpm:.0f}")
        self.update_perf_kpi_card(4, f"{avg_torque:.1f}")
        self.update_perf_kpi_card(5, f"{eff:.1f}")

        self.performance_plot.clear()
        if len(data) > 1:
            days = list(range(1, len(data) + 1))
            rops_all = [d['rop'] for d in data]
            wob_all = [d['wob'] for d in data]

            max_rop = max(rops_all) if max(rops_all) > 0 else 1
            max_wob = max(wob_all) if max(wob_all) > 0 else 1

            self.performance_plot.plot(
                days,
                [r / max_rop * 100 for r in rops_all],
                pen=pg.mkPen('#1abc9c', width=3),
                name="ROP (norm)"
            )
            self.performance_plot.plot(
                days,
                [w / max_wob * 100 for w in wob_all],
                pen=pg.mkPen('#3498db', width=3),
                name="WOB (norm)"
            )

        self.performance_table.setRowCount(len(data))
        for i, d in enumerate(data):
            self.performance_table.setItem(
                i, 0, QTableWidgetItem(str(d['date']))
            )
            self.performance_table.setItem(
                i, 1, QTableWidgetItem(d['bit_run'])
            )
            self.performance_table.setItem(
                i, 2, QTableWidgetItem(f"{d['rop']:.1f}")
            )
            self.performance_table.setItem(
                i, 3, QTableWidgetItem(f"{d['wob']:.1f}")
            )
            self.performance_table.setItem(
                i, 4, QTableWidgetItem(f"{d['rpm']:.0f}")
            )
            self.performance_table.setItem(
                i, 5, QTableWidgetItem(f"{d['torque']:.1f}")
            )
            self.performance_table.setItem(
                i, 6, QTableWidgetItem(f"{d['pressure']:.0f}")
            )

        self.chart_data['performance'] = data
        
    def update_daily_data(self):
        if not self.current_well_id: return
        def fetch():
            session = self.db.create_session()
            try: return self.get_today_data(session)
            finally: session.close()
        today = self.get_cached_data(f'today_{self.current_well_id}', fetch)
        if today:
            self.today_indicators['depth_meter'].setText(f"{today['depth']:.1f}")
            self.today_indicators['rop_meter'].setText(f"{today['rop']:.1f}")
            self.today_indicators['hours'].setText(f"{today['hours']:.1f}")
            self.today_indicators['days'].setText(str(today['rig_day']))
            self.today_indicators['npt_hours'].setText(f"{today['npt_hours']:.1f}")
            self.today_indicators['mw_pcf'].setText(f"{today['mw_in']:.1f}/{today['mw_out']:.1f}")
        session = self.db.create_session()
        recent = session.query(DailyReport).filter_by(well_id=self.current_well_id)\
                        .order_by(desc(DailyReport.report_date)).limit(10).all()
        self.recent_reports_table.setRowCount(len(recent))
        for i, r in enumerate(recent):
            act = session.query(TimeLog24H.main_code).filter_by(report_id=r.id)\
                         .order_by(desc(TimeLog24H.duration)).first()
            main_act = act[0] if act else "Drilling"
            self.recent_reports_table.setItem(i, 0, QTableWidgetItem(str(r.report_date)))
            self.recent_reports_table.setItem(i, 1, QTableWidgetItem(str(r.rig_day or 0)))
            self.recent_reports_table.setItem(i, 2, QTableWidgetItem(f"{r.depth_2400 or 0:.1f}"))
            self.recent_reports_table.setItem(i, 3, QTableWidgetItem(main_act))
        session.close()

    def run_advanced_analysis(self):
        if not self.current_well_id:
            QMessageBox.warning(self, "No Data", "Please select a well first")
            return
        session = self.db.create_session()
        try:
            t = self.analytics_type.currentText()
            if t == "ROP Prediction": self.analyze_rop_prediction(session)
            elif t == "NPT Forecasting": self.analyze_npt_forecasting(session)
            elif t == "Cost Analysis": self.analyze_cost(session)
            elif t == "Risk Assessment": self.analyze_risk(session)
        finally:
            session.close()

    def analyze_rop_prediction(self, session):
        """Analyze ROP prediction with real data"""
        if not self.current_well_id:
            self.results_text.setText("No well selected")
            return
        
        # گرفتن داده واقعی از DrillingParameters
        params_list = session.query(DrillingParameters).filter(
            DrillingParameters.well_id == self.current_well_id
        ).order_by(DrillingParameters.report_date).all()
        
        if not params_list or len(params_list) < 2:
            # Fallback به Daily Reports
            reports = session.query(DailyReport).filter_by(
                well_id=self.current_well_id
            ).order_by(DailyReport.report_date).all()
            
            if len(reports) < 2:
                self.results_text.setText("Not enough data for ROP prediction (need at least 2 data points)")
                return
            
            days = list(range(1, len(reports) + 1))
            rops = [r.rop_meter or 0 for r in reports]
        else:
            days = list(range(1, len(params_list) + 1))
            rops = [p.avg_rop or 0 for p in params_list]
        
        # Filter valid data
        x = np.array(days)
        y = np.array(rops)
        valid = y > 0
        x, y = x[valid], y[valid]
        
        if len(x) < 2:
            self.results_text.setText("Not enough valid ROP data")
            return
        
        # Linear regression
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        
        # Predict next 5 days
        future_x = list(range(days[-1] + 1, days[-1] + 6))
        future_y = p(future_x)
        
        # Update chart
        self.analytics_plot.clear()
        self.analytics_plot.plot(x.tolist(), y.tolist(), 
                                pen=pg.mkPen('#3498db', width=3), 
                                symbol='o', symbolSize=8, 
                                symbolBrush='#2980b9', name="Actual ROP")
        self.analytics_plot.plot(x.tolist(), p(x).tolist(), 
                                pen=pg.mkPen('#e74c3c', width=2, style=Qt.DashLine), 
                                name="Trend Line")
        self.analytics_plot.plot(future_x, future_y.tolist(), 
                                pen=pg.mkPen('#2ecc71', width=2), 
                                symbol='d', symbolSize=10, 
                                symbolBrush='#27ae60', name="Predicted")
        
        # Results
        avg_rop = np.mean(y)
        std_rop = np.std(y)
        slope = z[0]
        
        report = f"⚡ ROP PREDICTION ANALYSIS\n{'='*40}\n"
        report += f"Data Points: {len(x)}\n"
        report += f"Average ROP: {avg_rop:.2f} m/hr\n"
        report += f"Std Dev: {std_rop:.2f} m/hr\n"
        report += f"Trend Slope: {slope:.3f} m/hr per day\n\n"
        report += "📈 Predictions:\n"
        
        for d, v in zip(future_x, future_y):
            report += f"  Day {d}: {max(0, v):.2f} m/hr\n"
        
        if slope > 0.1:
            report += "\n✅ ROP is improving"
        elif slope < -0.1:
            report += "\n⚠️ ROP is declining - check bit wear"
        else:
            report += "\n➡️ ROP is stable"
        
        self.results_text.setText(report)
        
    def analyze_npt_forecasting(self, session):
        """تحلیل واقعی NPT Forecasting"""
        import numpy as np
        
        well_id = self.current_well_id
        if not well_id:
            self.results_text.setText("No well selected")
            return
        
        # داده واقعی NPT از دیتابیس
        npt_data = self.get_npt_data(session)
        entries = npt_data.get('entries', [])
        
        if len(entries) < 3:
            self.results_text.setText("⏱️ NPT Forecasting\nNot enough data (need at least 3 NPT events)")
            return
        
        # گروه‌بندی NPT بر اساس تاریخ
        daily_npt = {}
        for e in entries:
            d = str(e['date'])
            daily_npt[d] = daily_npt.get(d, 0) + e['hours']
        
        dates = sorted(daily_npt.keys())
        hours = [daily_npt[d] for d in dates]
        days = list(range(1, len(hours) + 1))
        
        # محاسبه trend
        x = np.array(days)
        y = np.array(hours)
        z = np.polyfit(x, y, 1)
        slope = z[0]
        
        # پیش‌بینی 7 روز آینده
        future_days = list(range(len(days) + 1, len(days) + 8))
        future_npt = np.polyval(z, future_days)
        
        # نمودار
        self.analytics_plot.clear()
        self.analytics_plot.plot(days, hours, pen=pg.mkPen('#e74c3c', width=3),
                                 symbol='o', symbolSize=6, symbolBrush='#c0392b',
                                 name="Actual NPT")
        self.analytics_plot.plot(days, np.polyval(z, days).tolist(),
                                 pen=pg.mkPen('#f39c12', width=2, style=Qt.DashLine),
                                 name="Trend")
        self.analytics_plot.plot(future_days, future_npt.tolist(),
                                 pen=pg.mkPen('#2ecc71', width=2),
                                 symbol='d', symbolSize=8, symbolBrush='#27ae60',
                                 name="Forecast")
        
        avg_npt = np.mean(hours)
        total_npt = sum(hours)
        
        report = f"⏱️ NPT FORECASTING ANALYSIS\n{'='*40}\n"
        report += f"Data Points: {len(days)} days with NPT\n"
        report += f"Total NPT: {total_npt:.1f} hours\n"
        report += f"Average Daily NPT: {avg_npt:.2f} hours\n"
        report += f"Trend Slope: {slope:.3f} hours/day\n\n"
        report += "📈 7-Day Forecast:\n"
        for d, v in zip(future_days, future_npt):
            report += f"  Day {d}: {max(0, v):.2f} hours\n"
        
        if slope > 0.1:
            report += "\n⚠️ NPT is INCREASING - investigate root causes"
        elif slope < -0.1:
            report += "\n✅ NPT is DECREASING - good trend"
        else:
            report += "\n➡️ NPT is STABLE"
        
        # Top categories
        cats = npt_data.get('categories', {})
        if cats:
            report += "\n\n🔥 Top NPT Categories:\n"
            sorted_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)
            for cat, hrs in sorted_cats[:5]:
                pct = (hrs / total_npt * 100) if total_npt > 0 else 0
                report += f"  • {cat}: {hrs:.1f} hrs ({pct:.1f}%)\n"
        
        self.results_text.setText(report)

    def analyze_cost(self, session):
        """تحلیل هزینه واقعی"""
        well_id = self.current_well_id
        if not well_id:
            self.results_text.setText("No well selected")
            return
        
        # داده واقعی
        total_days = session.query(DailyReport).filter_by(well_id=well_id).count()
        npt_data = self.get_npt_data(session)
        total_npt_hours = npt_data['total_npt']
        npt_days = total_npt_hours / 24
        
        # نرخ‌های فرضی (قابل تنظیم)
        daily_rate = 45000  # USD per day
        spread_rate = 15000  # USD per day (services, logistics)
        
        total_cost = total_days * (daily_rate + spread_rate)
        npt_cost = npt_days * (daily_rate + spread_rate)
        productive_cost = total_cost - npt_cost
        
        # نمودار
        self.analytics_plot.clear()
        x = [1, 2, 3]
        values = [total_cost/1000, productive_cost/1000, npt_cost/1000]
        colors = ['#3498db', '#2ecc71', '#e74c3c']
        
        bargraph = pg.BarGraphItem(x=x, height=values, width=0.6, 
                                    brushes=colors)
        self.analytics_plot.addItem(bargraph)
        self.analytics_plot.setLabel("bottom", "Category")
        self.analytics_plot.setLabel("left", "Cost (K USD)")
        
        report = f"💰 COST ANALYSIS\n{'='*40}\n"
        report += f"Total Rig Days: {total_days}\n"
        report += f"NPT Days: {npt_days:.1f} ({npt_data['npt_percentage']:.1f}%)\n"
        report += f"Productive Days: {total_days - npt_days:.1f}\n\n"
        report += f"📊 Cost Breakdown:\n"
        report += f"  Daily Rig Rate:    ${daily_rate:,.0f}/day\n"
        report += f"  Spread Rate:       ${spread_rate:,.0f}/day\n"
        report += f"  Total Daily Cost:  ${daily_rate + spread_rate:,.0f}/day\n\n"
        report += f"  Total Cost:        ${total_cost:,.0f}\n"
        report += f"  Productive Cost:   ${productive_cost:,.0f}\n"
        report += f"  NPT Cost:          ${npt_cost:,.0f}\n"
        report += f"  Cost per Meter:    ${total_cost / max(1, session.query(func.max(DailyReport.depth_2400)).filter_by(well_id=well_id).scalar() or 1):,.0f}/m\n"
        
        self.results_text.setText(report)

    def analyze_risk(self, session):
        """تحلیل ریسک واقعی"""
        well_id = self.current_well_id
        if not well_id:
            self.results_text.setText("No well selected")
            return
        
        # جمع‌آوری داده
        npt_data = self.get_npt_data(session)
        total_days = session.query(DailyReport).filter_by(well_id=well_id).count()
        npt_pct = npt_data['npt_percentage']
        
        # Safety data
        safety = session.query(SafetyReport).filter_by(well_id=well_id).order_by(
            SafetyReport.report_date.desc()
        ).first()
        
        # امتیازدهی ریسک
        risk_scores = {}
        
        # 1. NPT Risk
        if npt_pct > 30:
            risk_scores["NPT Risk"] = 9
        elif npt_pct > 20:
            risk_scores["NPT Risk"] = 7
        elif npt_pct > 10:
            risk_scores["NPT Risk"] = 5
        else:
            risk_scores["NPT Risk"] = 3
        
        # 2. Equipment Risk
        risk_scores["Equipment"] = 5  # default
        
        # 3. Weather Risk
        risk_scores["Weather"] = 4  # default
        
        # 4. Well Control Risk
        risk_scores["Well Control"] = 6 if npt_pct > 15 else 3
        
        # 5. Safety Risk
        days_no_lti = safety.days_without_lti if safety else 0
        risk_scores["Safety"] = 2 if days_no_lti > 90 else 5 if days_no_lti > 30 else 8
        
        # نمودار
        self.analytics_plot.clear()
        categories = list(risk_scores.keys())
        scores = list(risk_scores.values())
        x = list(range(len(categories)))
        
        colors = []
        for s in scores:
            if s >= 7:
                colors.append('#e74c3c')
            elif s >= 4:
                colors.append('#f39c12')
            else:
                colors.append('#2ecc71')
        
        bargraph = pg.BarGraphItem(x=x, height=scores, width=0.6, brushes=colors)
        self.analytics_plot.addItem(bargraph)
        
        # خط threshold
        threshold = pg.InfiniteLine(pos=7, angle=0, pen=pg.mkPen('#e74c3c', width=2, style=Qt.DashLine))
        self.analytics_plot.addItem(threshold)
        
        overall = sum(scores) / len(scores)
        
        report = f"⚠️ RISK ASSESSMENT\n{'='*40}\n"
        report += f"Overall Risk Score: {overall:.1f}/10\n"
        report += f"Risk Level: {'HIGH' if overall > 7 else 'MEDIUM' if overall > 4 else 'LOW'}\n\n"
        report += "📊 Risk Breakdown:\n"
        
        for cat, score in risk_scores.items():
            level = "🔴 HIGH" if score >= 7 else "🟡 MEDIUM" if score >= 4 else "🟢 LOW"
            bar = "█" * score + "░" * (10 - score)
            report += f"  {cat:20s}: [{bar}] {score}/10 {level}\n"
        
        report += f"\n📈 Key Metrics:\n"
        report += f"  Total Days: {total_days}\n"
        report += f"  NPT Percentage: {npt_pct:.1f}%\n"
        report += f"  Days without LTI: {days_no_lti}\n"
        
        self.results_text.setText(report)
        
    def update_stat_card_value(self, card, new_val):
        if hasattr(card, 'value_label'):
            parts = card.value_label.text().split()
            unit = parts[-1] if len(parts) >= 3 else ''
            card.value_label.setText(f"<b>{new_val}</b> {unit}")

    def update_perf_kpi_card(self, idx, new_val):
        if idx < len(self.perf_kpi_cards):
            self.update_stat_card_value(self.perf_kpi_cards[idx], new_val)

    def toggle_auto_update(self, state):
        intervals = {0:5000, 1:10000, 2:30000, 3:60000, 4:300000}
        if state == Qt.Checked:
            self.update_timer.start(intervals.get(self.auto_update_interval.currentIndex(), 10000))
            self.status_label.setText("🟢 Monitoring Active")
            self.update_all_data()
        else:
            self.update_timer.stop()
            self.status_label.setText("🟡 Monitoring Paused")

    def load_milestones_data(self):
        """بارگذاری داده‌های Milestones (FACT vs PLAN بر اساس Section)"""
        if not self.current_well_id:
            return
        
        session = self.db.create_session()
        try:
            from core.database import Section, DailyReport, TimeLog24H
            from sqlalchemy import func
            
            # دریافت تمام سکشن‌های چاه
            sections = session.query(Section).filter(
                Section.well_id == self.current_well_id
            ).order_by(Section.depth_from).all()
            
            if not sections:
                # اگر سکشنی وجود نداشت، از داده‌های DailyReport استفاده کن
                self._load_milestones_from_reports(session)
                return
            
            fact_data = []
            plan_data = []
            section_names = []
            
            for section in sections:
                section_names.append(section.name)
                
                # FACT: زمان واقعی صرف شده در این سکشن (از TimeLog24H)
                fact_time = session.query(func.sum(TimeLog24H.duration)).join(
                    DailyReport, TimeLog24H.report_id == DailyReport.id
                ).filter(
                    DailyReport.section_id == section.id
                ).scalar() or 0
                fact_data.append(fact_time / 24)  # تبدیل به روز
                
                # PLAN: زمان برنامه‌ریزی شده (از Section.depth_to - depth_from تقسیم بر نرخ فرضی)
                # یا اگر فیلد planned_days دارید از آن استفاده کنید
                planned_days = (section.depth_to - section.depth_from) / 50 if section.depth_to > 0 else 5
                plan_data.append(planned_days)
            
            # رسم نمودار Milestones
            self._draw_milestones_chart(section_names, fact_data, plan_data)
            
        except Exception as e:
            logger.error(f"Error loading milestones data: {e}")
        finally:
            session.close()

    def _load_milestones_from_reports(self, session):
        """بارگذاری Milestones از DailyReport در صورت نبود Section"""
        try:
            from core.database import DailyReport
            from sqlalchemy import func
            
            # گروه‌بندی بر اساس ماه یا هفته
            reports = session.query(
                DailyReport.report_date,
                DailyReport.depth_2400,
                DailyReport.rig_day
            ).filter(
                DailyReport.well_id == self.current_well_id
            ).order_by(DailyReport.report_date).all()
            
            if not reports:
                return
            
            # ایجاد نقاط عطف (هر 500 متر یا هر 30 روز)
            milestones = []
            fact_times = []
            last_depth = 0
            cumulative_days = 0
            
            for r in reports:
                depth = r.depth_2400 or 0
                if depth - last_depth >= 500 or cumulative_days >= 30:
                    if last_depth > 0:
                        milestones.append(f"{last_depth:.0f}-{depth:.0f}m")
                        fact_times.append(cumulative_days)
                    last_depth = depth
                    cumulative_days = 0
                cumulative_days += 1
            
            if milestones:
                plan_times = [d * 0.8 for d in fact_times]  # تخمین برنامه
                self._draw_milestones_chart(milestones, fact_times, plan_times)
                
        except Exception as e:
            logger.error(f"Error loading milestones from reports: {e}")

    def _draw_milestones_chart(self, sections, fact_days, plan_days):
        if not sections:
            return
        
        try:
            fig, ax = plt.subplots(figsize=(10, 5), facecolor='#1e1e1e')
            ax.set_facecolor('#1e1e1e')
            
            x = np.arange(len(sections))
            width = 0.35
            
            bars1 = ax.bar(x - width/2, fact_days, width, label='FACT', color='#3498db', edgecolor='white', linewidth=0.5)
            bars2 = ax.bar(x + width/2, plan_days, width, label='PLAN', color='#e74c3c', edgecolor='white', linewidth=0.5)
            
            ax.set_xlabel('Section', color='white', fontsize=11)
            ax.set_ylabel('Days', color='white', fontsize=11)
            ax.set_title('Milestones - FACT vs PLAN (Days per Section)', color='white', fontsize=14, fontweight='bold')
            ax.set_xticks(x)
            ax.set_xticklabels(sections, rotation=45, ha='right', color='white')
            ax.tick_params(axis='y', colors='white')
            ax.legend(loc='upper right', facecolor='#2c3e50', edgecolor='white', labelcolor='white')
            ax.grid(True, alpha=0.3, color='white')
            
            # افزودن مقادیر روی میله‌ها
            for bar in bars1:
                height = bar.get_height()
                ax.annotate(f'{height:.1f}',
                           xy=(bar.get_x() + bar.get_width()/2, height),
                           xytext=(0, 3), textcoords="offset points",
                           ha='center', va='bottom', color='white', fontsize=8)
            
            for bar in bars2:
                height = bar.get_height()
                ax.annotate(f'{height:.1f}',
                           xy=(bar.get_x() + bar.get_width()/2, height),
                           xytext=(0, 3), textcoords="offset points",
                           ha='center', va='bottom', color='white', fontsize=8)
            
            fig.tight_layout()
            
            # نمایش در ویجت
            canvas = FigureCanvas(fig)
            if hasattr(self, 'milestones_widget') and self.milestones_widget:
                safe_replace_chart(self.milestones_widget, canvas)
            else:
                logger.warning("milestones_widget not available")
            plt.close(fig)
        except Exception as e:
            logger.error(f"Error drawing milestones chart: {e}")
        
    # ---------- SelectionManager integration ----------
    def on_well_changed(self, well_id, well_data):
        self.set_current_well(well_id, well_data.get('name', str(well_id)))

    def on_report_changed(self, report_id, report_data):
        self.current_report_id = report_id
        self.update_data_quality()
        self.update_all_data()

    def update_data_quality(self):
        if not self.current_report_id:
            self.quality_label.setText("Data Quality: —")
            self.quality_label.setStyleSheet("font-weight: bold; padding: 5px; color: #7f8c8d;")
            return
        try:
            summary = self.quality_service.summary(self.current_report_id)
            color = {"good": "#27ae60", "warning": "#f39c12", "critical": "#e74c3c"}.get(summary["status"], "#7f8c8d")
            self.quality_label.setText(f"Data Quality: {summary['score']:.1f}% ({summary['status']})")
            self.quality_label.setStyleSheet(f"font-weight: bold; padding: 5px; color: {color};")
            self.quality_label.setToolTip("\\n".join(f"{m['name']}: {m['value']}% — {m['detail']}" for m in summary["metrics"]))
        except Exception as exc:
            logger.error("Data quality update failed: %s", exc, exc_info=True)
            self.quality_label.setText("Data Quality: unavailable")

    def set_current_well(self, well_id, well_name):
        self.current_well_id = well_id
        self.current_well_name = well_name
        self.clear_cache()
        self.well_label.setText(f"🌍 Well: {well_name}")
        self.status_label.setText("🟢 Ready for Analysis")
        self.help_label.setVisible(False)
        self.analysis_tabs.setVisible(True)
        self.bottom_widget.setVisible(True)
        self.auto_update_check.setChecked(True)
        self.update_data_quality()
        self.update_all_data()

    def update_all_data(self):
        if not self.current_well_id: return
        try:
            self.update_kpi_data()
            self.update_time_depth_data()
            self.update_npt_data()
            self.update_performance_data()
            self.update_daily_data()
            self.update_analytics()
            self.load_milestones_data() 
            self.last_update_label.setText(f"Last update: {QTime.currentTime().toString('HH:mm:ss')}")
        except Exception as e:
            self.status_label.setText("🔴 Error in data update")
            logger.error(f"Update error: {e}")

    def auto_update_data(self):
        if self.current_well_id and self.auto_update_check.isChecked():
            self.update_all_data()

    def update_analytics(self):
        if self.current_well_id:
            self.run_advanced_analysis()

    # ---- Export & print (simplified but fully functional) ----
    def export_chart(self, chart_type):
        """اکسپورت نمودار انتخابی"""
        return self.export_chart_image(chart_type)

    def export_all_charts(self):
        if not self.current_well_id:
            QMessageBox.warning(self, "No Data", "Please select a well first")
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Charts", f"analysis_charts_{timestamp}.pdf",
            "PDF Files (*.pdf);;PNG Images (*.png)"
        )
        if not filename:
            return
        export_mgr = ExportManager(self)
        if filename.endswith('.pdf'):
            self.export_dashboard()
        else:
            base = filename.replace('.png', '')
            
            charts = [self.time_depth_plot, self.daily_gain_plot, self.performance_plot, self.npt_pie_plot]
            saved_files = []
            for i, plot in enumerate(charts):
                png_file = f"{base}_chart_{i+1}.png"
                if export_mgr.export_image(plot, png_file):
                    saved_files.append(os.path.basename(png_file))
            self.show_success(f"Exported {len(saved_files)} chart images successfully")
            QMessageBox.information(self, "Export Complete", f"Charts successfully exported:\n" + "\n".join(saved_files))

    def _export_charts_to_pdf(self, filename):
        """Export charts to PDF"""
        try:
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.pdfgen import canvas
            from reportlab.lib.utils import ImageReader
            import tempfile
            
            c = canvas.Canvas(filename, pagesize=landscape(A4))
            width, height = landscape(A4)
            
            charts = [
                (self.time_depth_plot, "Time vs Depth", 50, height/2 + 50, width-100, height/2 - 100),
                (self.daily_gain_plot, "Daily Gain", 50, 50, width-100, height/2 - 100),
            ]
            
            for plot, title, x, y, w, h in charts:
                # ذخیره موقت نمودار به PNG
                temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                temp_file.close()
                
                exporter = pg.exporters.ImageExporter(plot.plotItem)
                exporter.export(temp_file.name)
                
                # اضافه کردن به PDF
                c.drawString(x, y + h + 10, title)
                c.drawImage(ImageReader(temp_file.name), x, y, width=w, height=h)
                
                # حذف فایل موقت
                os.unlink(temp_file.name)
                
                c.showPage()
            
            c.save()
            return True
        except ImportError:
            # Fallback: save as PNG
            self._export_charts_to_png(filename.replace('.pdf', '.png'))
            return False

    def _export_charts_to_png(self, filename):
        """Export all charts to PNG files"""
        base_name = filename.replace('.png', '')
        
        charts = [
            (self.time_depth_plot, f"{base_name}_time_depth.png"),
            (self.daily_gain_plot, f"{base_name}_daily_gain.png"),
            (self.performance_plot, f"{base_name}_performance.png"),
            (self.npt_pie_plot, f"{base_name}_npt.png"),
        ]
        
        for plot, fname in charts:
            try:
                exporter = pg.exporters.ImageExporter(plot.plotItem)
                exporter.export(fname)
            except Exception as e:
                logger.error(f"Error exporting {fname}: {e}")

    def export_chart_image(self, chart_type):
        """Export a single chart"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Chart", f"{chart_type}_{timestamp}.png",
            "PNG Images (*.png);;PDF Files (*.pdf)"
        )
        
        if not filename:
            return
        
        try:
            plot_map = {
                "time_depth": self.time_depth_plot,
                "daily_gain": self.daily_gain_plot,
                "performance": self.performance_plot,
                "npt": self.npt_pie_plot,
                "analytics": self.analytics_plot,
            }
            
            plot = plot_map.get(chart_type)
            if plot:
                exporter = pg.exporters.ImageExporter(plot.plotItem)
                exporter.export(filename)
                self.show_success(f"Chart exported to {filename}")
            else:
                self.show_error(f"Unknown chart type: {chart_type}")
        except Exception as e:
            self.show_error(f"Export failed: {str(e)}")
            
    def export_dashboard(self):
        """اکسپورت داشبورد به PDF"""
        if not self.current_well_id:
            QMessageBox.warning(self, "No Data", "Please select a well first")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Dashboard",
            f"dashboard_{self.current_well_name}_{timestamp}.pdf",
            "PDF Files (*.pdf);;HTML Files (*.html)"
        )
        if not filename:
            return
        
        try:
            html = self._generate_report_html()
            
            if filename.endswith('.html'):
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(html)
            else:
                # PDF via QTextDocument
                from PySide6.QtPrintSupport import QPrinter
                from PySide6.QtGui import QTextDocument
                
                printer = QPrinter(QPrinter.HighResolution)
                printer.setOutputFormat(QPrinter.PdfFormat)
                printer.setOutputFileName(filename)
                
                doc = QTextDocument()
                doc.setHtml(html)
                doc.print_(printer)
            
            self.show_success(f"Dashboard exported to: {os.path.basename(filename)}")
            QMessageBox.information(self, "Export", f"Dashboard exported to:\n{filename}")
            
        except Exception as e:
            logger.error(f"Dashboard export error: {e}")
            self.show_error(f"Export failed: {str(e)}")

    def export_all_data(self):
        """اکسپورت همه داده‌ها به Excel"""
        if not self.current_well_id:
            QMessageBox.warning(self, "No Data", "Please select a well first")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export All Analysis Data",
            f"analysis_data_{self.current_well_name}_{timestamp}.xlsx",
            "Excel Files (*.xlsx);;CSV Files (*.csv)"
        )
        if not filename:
            return
        
        try:
            if filename.endswith('.xlsx'):
                try:
                    import pandas as pd
                    
                    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                        # Time Depth Data
                        if self.time_depth_table.rowCount() > 0:
                            td_data = self._table_to_dataframe(self.time_depth_table)
                            td_data.to_excel(writer, sheet_name='Time_Depth', index=False)
                        
                        # NPT Data
                        if self.npt_table.rowCount() > 0:
                            npt_data = self._table_to_dataframe(self.npt_table)
                            npt_data.to_excel(writer, sheet_name='NPT', index=False)
                        
                        # Performance Data
                        if self.performance_table.rowCount() > 0:
                            perf_data = self._table_to_dataframe(self.performance_table)
                            perf_data.to_excel(writer, sheet_name='Performance', index=False)
                        
                        # Recent Reports
                        if self.recent_reports_table.rowCount() > 0:
                            reports_data = self._table_to_dataframe(self.recent_reports_table)
                            reports_data.to_excel(writer, sheet_name='Recent_Reports', index=False)
                    
                    self.show_success(f"Data exported to: {os.path.basename(filename)}")
                    QMessageBox.information(self, "Export", f"All data exported to:\n{filename}")
                    
                except ImportError:
                    self.show_error("Install pandas: pip install pandas openpyxl")
            else:
                # CSV fallback
                import csv
                tables = {
                    'time_depth': self.time_depth_table,
                    'npt': self.npt_table,
                    'performance': self.performance_table,
                }
                base = filename.replace('.csv', '')
                for name, table in tables.items():
                    if table.rowCount() > 0:
                        csv_file = f"{base}_{name}.csv"
                        self._export_table_to_csv(table, csv_file)
                
                self.show_success("Data exported as CSV files")
        
        except Exception as e:
            logger.error(f"Data export error: {e}")
            self.show_error(f"Export failed: {str(e)}")

    def _table_to_dataframe(self, table):
        """تبدیل QTableWidget به pandas DataFrame"""
        import pandas as pd
        
        headers = []
        for col in range(table.columnCount()):
            header = table.horizontalHeaderItem(col)
            h = header.text() if header else f"Col_{col}"
            # حذف emoji از header
            h = ''.join(c for c in h if c.isalnum() or c in (' ', '_', '-', '(', ')', '/', '.'))
            headers.append(h.strip())
        
        data = []
        for row in range(table.rowCount()):
            row_data = []
            for col in range(table.columnCount()):
                item = table.item(row, col)
                row_data.append(item.text() if item else "")
            data.append(row_data)
        
        return pd.DataFrame(data, columns=headers)

    def _export_table_to_csv(self, table, filename):
        """اکسپورت جدول به CSV"""
        import csv
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            headers = []
            for col in range(table.columnCount()):
                header = table.horizontalHeaderItem(col)
                headers.append(header.text() if header else f"Col_{col}")
            writer.writerow(headers)
            for row in range(table.rowCount()):
                row_data = []
                for col in range(table.columnCount()):
                    item = table.item(row, col)
                    row_data.append(item.text() if item else "")
                writer.writerow(row_data)
                
    def print_comprehensive_report(self):
        """Print comprehensive analysis report"""
        if not self.current_well_id:
            QMessageBox.warning(self, "No Data", "Please select a well first")
            return
        
        printer = QPrinter(QPrinter.HighResolution)
        printer.setDocName(f"Analysis_Report_Well_{self.current_well_id}")
        
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.Accepted:
            return
        
        try:
            # ایجاد HTML برای چاپ
            html = self._generate_report_html()
            
            document = QTextDocument()
            document.setHtml(html)
            document.print_(printer)
            
            self.show_success("Report sent to printer")
        except Exception as e:
            logger.error(f"Print error: {e}")
            self.show_error(f"Print failed: {str(e)}")

    def _generate_report_html(self):
        """Generate HTML report"""
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial; margin: 20px; color: #333; }}
                h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
                h2 {{ color: #2980b9; margin-top: 30px; }}
                table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #3498db; color: white; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
                .kpi {{ display: inline-block; background: #ecf0f1; padding: 15px; margin: 10px; border-radius: 8px; }}
                .kpi-value {{ font-size: 24px; font-weight: bold; color: #2c3e50; }}
            </style>
        </head>
        <body>
            <h1>📊 DrillMaster Analysis Report</h1>
            <p><b>Well:</b> {self.current_well_name or 'Unknown'}</p>
            <p><b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
            
            <h2>📈 Key Performance Indicators</h2>
            <div>
        """
        
        # KPI cards
        kpi_labels = ["Current Depth", "Rig Days", "Avg ROP", "Total NPT"]
        for i, label in enumerate(kpi_labels):
            if i < len(self.kpi_cards) and hasattr(self.kpi_cards[i], 'value_label'):
                value = self.kpi_cards[i].value_label.text()
                html += f'<div class="kpi"><b>{label}:</b><br><span class="kpi-value">{value}</span></div>'
        
        html += """
            </div>
            
            <h2>📋 Depth History</h2>
            <table>
                <tr><th>Date</th><th>Days</th><th>Depth (m)</th><th>Daily Gain</th><th>Status</th></tr>
        """
        
        # Table data
        for row in range(min(20, self.time_depth_table.rowCount())):
            html += "<tr>"
            for col in range(self.time_depth_table.columnCount()):
                item = self.time_depth_table.item(row, col)
                html += f"<td>{item.text() if item else ''}</td>"
            html += "</tr>"
        
        html += """
            </table>
            
            <h2>⏱️ NPT Summary</h2>
            <table>
                <tr><th>Category</th><th>Hours</th></tr>
        """
        
        for row in range(min(10, self.npt_table.rowCount())):
            cat = self.npt_table.item(row, 4)
            hours = self.npt_table.item(row, 3)
            if cat and hours:
                html += f"<tr><td>{cat.text()}</td><td>{hours.text()}</td></tr>"
        
        html += """
            </table>
            <p><i>Generated by DrillMaster</i></p>
        </body>
        </html>
        """
        
        return html
        