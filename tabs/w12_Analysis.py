"""
Advanced Analysis and Monitoring Tab for Drilling Software
PySide6 Version – Fully refactored with SelectionManager integration
"""
import os
import html as html_lib
import numpy as np
from datetime import datetime
from sqlalchemy import func, desc
from core.text_utils import fmt_num
import logging
logger = logging.getLogger(__name__)
# No process-wide warning filter and no global Matplotlib backend switch here:
# importing a tab must not change how the rest of the application warns or
# renders. Charts use the Figure API directly (no pyplot state) with the canvas
# chosen by core.matplotlib_widgets.select_figure_canvas.

from PySide6.QtCore import QDate, QDateTime, QTime, QTimer, Qt
from PySide6.QtGui import QColor, QTextDocument
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox, QFileDialog,
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QScrollArea, QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from core.common_widgets import safe_replace_chart

from core.managers import ExportManager

import matplotlib
from matplotlib.figure import Figure

from core.matplotlib_widgets import select_figure_canvas
from core import analysis_evidence as ev
from core.cost_semantics import canonical_variance, format_money
from core.engineering.result import EngineeringError

FigureCanvas, MATPLOTLIB_QT_OK = select_figure_canvas()


class _LoadError:
    """A failed read: shown as a read error with Retry, never as "No data"."""

    def __init__(self, exc):
        self.kind = type(exc).__name__
        self.detail = str(exc)

    def text(self):
        return f"Read error ({self.kind}) - use Refresh Now to retry"


_STALE = object()  # a result whose selection changed while it was read


try:
    import pyqtgraph as pg
    # The package does not import its exporters; chart export needs them.
    import pyqtgraph.exporters  # noqa: F401
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    pg = None
    logger.warning(
        "pyqtgraph not installed - charts disabled. "
        "Install with: pip install pyqtgraph"
    )


from core.database import (
    DailyReport, TimeLog24H,
    DrillingParameters, MudReport,
)
from core.base_tab import DrillTabBase
from core.data_quality import DataQualityService
from core.operations_intelligence import OperationsIntelligenceService


def _fmt_rig_day(value):
    """Rig-day cell text: unknown -> "—", a real reported value (incl. 0) kept."""
    return "—" if value is None else str(value)


def _fmt_recent_depth(value):
    """Recent-report depth cell: unknown -> "—", a real 0.0 -> "0.0"."""
    return "—" if value is None else f"{value:.1f}"



_CHART_BACKGROUND, _CHART_FOREGROUND = "#1e1e1e", "#ffffff"


def _analysis_plot_widget():
    """A dark-themed PlotWidget scoped to this tab.

    Earlier versions set pyqtgraph's *global* options at import (dark
    background, white foreground, ``useOpenGL=True``).  Those leak into every
    later PlotWidget in the application (e.g. the trajectory views: white axes
    on a white plot) and force an OpenGL viewport that renders blank where no
    working OpenGL is available (VMs, remote desktops, offscreen).  The theme
    is now applied to each W12 widget and rendering stays raster.
    """
    widget = pg.PlotWidget(background=_CHART_BACKGROUND)
    widget.setAntialiasing(True)
    plot = widget.getPlotItem()
    for name in ("left", "bottom", "right", "top"):
        axis = plot.getAxis(name)
        axis.setPen(pg.mkPen(_CHART_FOREGROUND))
        axis.setTextPen(pg.mkPen(_CHART_FOREGROUND))
    return widget


def _scope_text(widget):
    """Human scope label from a widget's current well/wellbore attributes."""
    bore = getattr(widget, "current_wellbore_id", None)
    if not bore:
        return "Whole well"
    name = getattr(widget, "current_wellbore_name", None)
    return f"Wellbore {name or '#' + str(bore)}"


def _exclusion_text(excluded):
    if not excluded:
        return "Excluded observations: none"
    counts = {}
    for row in excluded:
        label = f"{row.state.replace('_', ' ')}: {row.reason}"
        counts[label] = counts.get(label, 0) + 1
    return "Excluded observations: " + "; ".join(f"{n} x {label}" for label, n in sorted(counts.items()))


def _qss_rgba(hex_rgb, alpha_hex):
    """Qt style sheets read 8-digit hex as #AARRGGBB, not CSS #RRGGBBAA.

    "#3498DB" + "30" would be parsed as alpha 0x34 with colour #98DB30 (a
    green card for a blue KPI). An explicit rgba() is unambiguous.
    """
    h = hex_rgb.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {int(alpha_hex, 16)})"


def _plot_projection(plot, result, actual, colors, names, unit=""):
    """Plot actual / fitted / projection only for an assessed projection."""
    plot.clear()
    if unit:
        plot.setLabel("left", unit)
    if result["status"] != "assessed":
        # The chart itself states the outcome: an empty default axis would read
        # as "no data" or as a broken chart, which is a different state.
        plot.setTitle(f"{names[1]}: NOT ASSESSED - see the reason below the chart")
        return
    plot.setTitle(f"{names[1]} (linear fit; a projection, not a guarantee)")
    plot.setLabel("bottom", "Calendar day (day 1 = first valid date)")
    xs = result["x"]
    plot.plot(xs, actual, pen=pg.mkPen(colors[0], width=3),
              symbol='o', symbolSize=8, symbolBrush=colors[0], name=names[0])
    plot.plot(xs, result["fitted"], pen=pg.mkPen(colors[1], width=2, style=Qt.DashLine), name="Trend line")
    plot.plot([p["day"] for p in result["projection"]], [p["value"] for p in result["projection"]],
              pen=pg.mkPen(colors[2], width=2), symbol='d', symbolSize=9,
              symbolBrush=colors[2], name=names[1])


def _trend_words(result, unit, noun):
    if result["status"] != "assessed":
        return ""
    slope = result["slope"]
    if slope > 0.1:
        direction = "rising"
    elif slope < -0.1:
        direction = "falling"
    else:
        direction = "flat"
    return (f"\n{noun} trend is {direction} ({slope:+.3f} {unit}/day). "
            "This describes the recorded series only; no cause is assessed.")


class AnalysisWidget(DrillTabBase):
    """Advanced Professional Analysis and Monitoring Dashboard – PySide6 Version"""

    def __init__(self, db_manager, parent=None):
        super().__init__("AnalysisWidget", db_manager, parent)
        self.db = db_manager
        self.current_well_id = None
        self.current_well_name = None
        self.current_report_id = None
        # Analytical scope: when a specific wellbore (original hole or sidetrack)
        # is selected, analytics are computed for THAT bore only; None means the
        # whole-well aggregate. Never inferred — mirrors SelectionManager state.
        self.current_wellbore_id = getattr(
            self.sel_manager, "current_wellbore_id", None)
        self.current_wellbore_name = None
        self.quality_service = DataQualityService(self.db)
        self.intelligence_service = OperationsIntelligenceService(self.db)
        self.intelligence_label = QLabel("Operations Intelligence: —")
        self.intelligence_label.setWordWrap(True)
        self.intelligence_label.setStyleSheet("font-weight: bold; padding: 5px; color: #7f8c8d;")
        self.quality_label = QLabel("Data Quality: —")
        self.plan_variance_label = QLabel("Plan vs Actual: —")
        self.plan_variance_label.setStyleSheet("font-weight: bold; padding: 5px; color: #7f8c8d;")
        self.quality_label.setToolTip("Completeness and time-log coverage for the selected report")
        self.quality_label.setStyleSheet("font-weight: bold; padding: 5px; color: #7f8c8d;")

        # Data caches. Keys carry every scope dimension plus the data revision
        # (see _cache_key), so a cached value can only be reused for the same
        # well/bore/section/report and unchanged source data.
        self.data_cache = {}
        self.cache_time = {}
        self.cache_timeout = 30000  # 30 seconds
        self._data_rev = None
        # Selection generation: bumped on every scope change; a result read
        # for an older generation is discarded instead of painted.
        self._generation = 0
        self._last_kpis = None
        self._evidence_rows = []
        self._evidence_meta = None
        self._load_errors = []  # names of reads that failed in the current update
        
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

        # The dark chart theme is applied per widget (_analysis_plot_widget);
        # pyqtgraph's global config is shared by every tab and is left alone.

        # Auto-update timer
        # Parented: the timer dies with the widget and cannot fire into a
        # destroyed page.
        self.update_timer = QTimer(self)
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

        # A wellbore selection must re-scope analytics. DrillTabBase wires
        # well/section/report but not the bore signal, so — exactly like the W3b
        # schematic tab — W12 consumes it directly (smallest, lowest-risk change,
        # no shared-base modification per §7.1).
        try:
            self.sel_manager.wellbore_changed.connect(self.on_wellbore_changed)
        except AttributeError:  # silent-ok: selection managers without a wellbore signal (tests, legacy hosts)
            pass

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
            layout.addWidget(self.plan_variance_label)
            return

        # ---- HEADER SECTION ----
        header_widget = QWidget()
        # Box rules are scoped by object name: a bare "QWidget" rule cascades
        # its padding/margin into every child label and clips the KPI values.
        header_widget.setObjectName("analysisHeader")
        header_widget.setStyleSheet("""
            QWidget#analysisHeader {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2c3e50, stop:1 #34495e);
                border-radius: 12px;
                padding: 15px;
                margin: 5px;
            }
        """)
        header_layout = QGridLayout(header_widget)

        self.status_label = QLabel()
        self._set_status("🔴 No well selected", "error")
        # One cell per widget (status, well, quality, plan, intelligence, scope
        # on rows 0-5; KPI cards right; controls on row 6). Shared cells used to
        # paint the well/controls rows over the quality and plan labels.
        header_layout.addWidget(self.status_label, 0, 0, 1, 2)
        header_layout.addWidget(self.quality_label, 2, 0, 1, 2)
        header_layout.addWidget(self.plan_variance_label, 3, 0, 1, 2)
        header_layout.addWidget(self.intelligence_label, 4, 0, 1, 2)

        self.well_label = QLabel("🌍 Well: Not Selected")
        self.well_label.setStyleSheet("font-size: 14px; color: #bdc3c7;")
        header_layout.addWidget(self.well_label, 1, 0, 1, 2)

        # Explicit analytical scope indicator (Whole-Well vs a specific bore).
        self.scope_label = QLabel("🌐 Scope: Whole Well")
        self.scope_label.setStyleSheet(
            "font-weight: bold; padding: 5px; color: #7f8c8d;")
        header_layout.addWidget(self.scope_label, 5, 0, 1, 2)

        self.kpi_cards_widget = self.create_enhanced_kpi_cards()
        header_layout.addWidget(self.kpi_cards_widget, 0, 2, 4, 3)

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
        refresh_btn.clicked.connect(self.refresh_now)
        control_layout.addWidget(refresh_btn)

        clear_cache_btn = QPushButton("🗑️ Clear Cache")
        clear_cache_btn.setStyleSheet(self.get_button_style("warning"))
        clear_cache_btn.clicked.connect(self.clear_cache)
        control_layout.addWidget(clear_cache_btn)

        header_layout.addWidget(control_widget, 6, 0, 1, 5)
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
                background: rgba(236, 240, 241, 16);
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
        self.evidence_tab = self.create_evidence_tab()

        self.analysis_tabs.addTab(self.time_depth_tab, "📈 Time vs Depth")
        self.analysis_tabs.addTab(self.npt_tab, "⏱️ NPT Analysis")
        self.analysis_tabs.addTab(self.performance_tab, "⚡ Performance")
        self.analysis_tabs.addTab(self.daily_tab, "📅 Daily Monitor")
        self.analysis_tabs.addTab(self.analytics_tab, "📊 Advanced Analytics")
        self.analysis_tabs.addTab(self.evidence_tab, "🔎 Evidence")

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
        # A disabled action (e.g. drill-down on an ambiguous evidence row) must
        # look disabled: without this rule the gradient keeps it looking clickable.
        disabled = """
                QPushButton:disabled {
                    background: #4d5656;
                    color: #95a5a6;
                }
            """
        return styles.get(button_type, styles["default"]) + disabled

    def create_enhanced_kpi_cards(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        # No fabricated starting values: a card shows its state ("—" with no
        # selection) until a real value for the current scope is read.
        kpi_data = [
            ("current_depth", {"icon": "🎯", "title": "Current Depth", "color": "#3498DB"}),
            ("rig_days", {"icon": "📅", "title": "Rig Days", "color": "#2ECC71"}),
            ("avg_rop", {"icon": "⚡", "title": "Avg ROP", "color": "#E74C3C"}),
            ("total_npt", {"icon": "⏱️", "title": "Total NPT", "color": "#F39C12"}),
        ]
        for key, kpi in kpi_data:
            card = self.create_kpi_card_modern(value="—", unit="", trend="No well selected", **kpi)
            card.metric_key = key
            card.metric_value = ev.MetricValue(ev.STATE_NO_SELECTION, unit=ev.KPI_DEFINITIONS[key][1])
            card.setToolTip(ev.kpi_tooltip(key))
            layout.addWidget(card)
            self.kpi_cards.append(card)
        return widget

    _STATUS_COLOURS = {"ok": "#2ecc71", "warn": "#f39c12", "error": "#e74c3c"}

    def _set_status(self, text, level):
        """Status text plus a colour that carries the state (emoji may not render)."""
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            "QLabel { font-size: 16px; font-weight: bold; padding: 8px; color: %s; }"
            % self._STATUS_COLOURS[level])

    def _set_kpi_card(self, card, mv, trend=""):
        """Show one main KPI: number + unit only for a real value, else its state."""
        card.metric_value = mv
        card.value_label.setText(f"<b>{mv.number_text()}</b>")
        card.unit_label.setText(mv.unit if mv.has_value else "")
        if card.trend_label is not None:
            card.trend_label.setText(trend)
        card.value_label.setToolTip(mv.reason)

    def _set_stat_card(self, card, mv):
        """Show one stat card; the unit is the card's own, never parsed back."""
        card.metric_value = mv
        unit = card.unit if mv.has_value else ""
        card.value_label.setText(f"<b>{mv.number_text()}</b> {unit}".rstrip())
        card.value_label.setToolTip(mv.reason)

    def create_kpi_card_modern(self, icon, title, value, unit, color, trend=""):
        card = QFrame()
        # Scoped by object name: QLabel derives from QFrame, so a bare "QFrame"
        # rule would pad and border every label inside the card and clip it.
        card.setObjectName("kpiCard")
        card.setStyleSheet(f"""
            QFrame#kpiCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {_qss_rgba(color, "30")}, stop:1 {_qss_rgba(color, "10")});
                border-radius: 10px;
                border: 2px solid {_qss_rgba(color, "40")};
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
        card.unit_label = unit_label
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
        
        self.time_depth_plot = _analysis_plot_widget()
        self.time_depth_plot.setBackground("#1e1e1e")
        self.time_depth_plot.setLabel("left", "Depth (m)", color="#ffffff", size=14)
        self.time_depth_plot.setLabel("bottom", "Calendar day", color="#ffffff", size=14)
        self.time_depth_plot.showGrid(x=True, y=True, alpha=0.3)
        self.time_depth_plot.setMinimumHeight(300)
        chart_layout.addWidget(self.time_depth_plot)
        
        self.daily_gain_plot = _analysis_plot_widget()
        self.daily_gain_plot.setBackground("#1e1e1e")
        # The full definition does not fit a 150 px axis; keep it as a tooltip.
        self.daily_gain_plot.setLabel("left", "Gain (m)", color="#ffffff", size=12)
        self.daily_gain_plot.setToolTip("Gain (m): depth change since the prior known report")
        self.daily_gain_plot.setLabel("bottom", "Days", color="#ffffff", size=12)
        self.daily_gain_plot.showGrid(x=True, y=True, alpha=0.3)
        self.daily_gain_plot.setMinimumHeight(110)   # room for the axis title
        self.daily_gain_plot.setMaximumHeight(150)
        chart_layout.addWidget(self.daily_gain_plot)
        main_layout.addWidget(chart_container)
        
        # === جدول ===
        table_widget = QWidget()
        # Scoped: an unscoped padding rule cascades into the header sections
        # and clips their text.
        table_widget.setObjectName("timeDepthTableBox")
        table_widget.setStyleSheet(
            "QWidget#timeDepthTableBox { background: #2c3e50; border-radius: 8px; padding: 8px; }")
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
        kpi_widget.setObjectName("perfKpiPanel")   # scoped: see init_ui header
        kpi_widget.setStyleSheet("QWidget#perfKpiPanel { background: #34495e; border-radius: 8px; padding: 12px; }")
        kpi_layout = QGridLayout(kpi_widget)
        
        # "Efficiency" used to be avg ROP / 20 m/hr x 100 — an invented target.
        # The sixth card is now the defined productive-time share instead.
        perf_kpis = [
            ("avg_rop", "⚡", "Avg ROP", "#1abc9c"),
            ("best_rop", "🏆", "Best ROP", "#e67e22"),
            ("avg_wob", "🔧", "Avg WOB", "#3498db"),
            ("avg_rpm", "🌀", "Avg RPM", "#9b59b6"),
            ("avg_torque", "💪", "Avg Torque", "#e74c3c"),
            ("productive_percent", "📈", "Productive Time", "#2ecc71"),
        ]

        self.perf_kpi_cards = []
        for i, (key, icon, title, color) in enumerate(perf_kpis):
            row, col = divmod(i, 3)
            card = self.create_stat_card(icon, title, "—", ev.KPI_DEFINITIONS[key][1], color)
            card.metric_key = key
            card.setToolTip(ev.kpi_tooltip(key))
            self._set_stat_card(card, ev.MetricValue(ev.STATE_NO_SELECTION))
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
        
        self.performance_plot = _analysis_plot_widget()
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

        # ===== d-Exponent Trend (pore-pressure detection from stored bit runs) =====
        de_widget = QWidget()
        de_widget.setStyleSheet("background: #1e1e1e; border-radius: 8px;")
        de_layout = QVBoxLayout(de_widget)

        de_header = QHBoxLayout()
        de_header.addWidget(QLabel("📈 d-Exponent Trend (falling d with depth = abnormal pressure)"))
        de_header.addStretch()
        export_de_btn = QPushButton("📤 Export Chart")
        export_de_btn.setStyleSheet("""
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
        export_de_btn.clicked.connect(lambda: self.export_chart_image("dexponent"))
        de_header.addWidget(export_de_btn)
        de_layout.addLayout(de_header)

        self.dexponent_plot = _analysis_plot_widget()
        self.dexponent_plot.setBackground("#1e1e1e")
        self.dexponent_plot.setLabel("left", "d-exponent (dimensionless)", color="#ffffff", size=14)
        self.dexponent_plot.setLabel("bottom", "Depth (m)", color="#ffffff", size=14)
        self.dexponent_plot.addLegend()
        self.dexponent_plot.setMinimumHeight(260)
        de_layout.addWidget(self.dexponent_plot)

        self.dexponent_table = QTableWidget()
        self.dexponent_table.setColumnCount(8)
        self.dexponent_table.setHorizontalHeaderLabels(
            ["Date", "Bit Run", "Depth Out (m)", "ROP (m/hr)",
             "WOB (klb)", "RPM", "Bit (in)", "d-exponent"])
        self.dexponent_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.dexponent_table.setMaximumHeight(180)
        de_layout.addWidget(self.dexponent_table)
        main_layout.addWidget(de_widget)

        # ===== Bit Run Cost Comparison (cost/ft from stored runs) =====
        cost_widget = QWidget()
        cost_widget.setStyleSheet("background: #2c3e50; border-radius: 8px; padding: 8px;")
        cost_layout = QVBoxLayout(cost_widget)

        cost_header = QHBoxLayout()
        cost_header.addWidget(QLabel("💰 Bit Run Cost Comparison (cost/ft) — SCENARIO"))
        cost_header.addStretch()
        cost_layout.addLayout(cost_header)
        scenario_note = QLabel(
            "Scenario only: rig rate, trip time and bit cost are user-entered assumptions in "
            "one currency of your choice, not recorded cost. Recorded cost is in Advanced "
            "Analytics > Cost Analysis.")
        scenario_note.setWordWrap(True)
        scenario_note.setStyleSheet("color: #f1c40f; font-size: 11px;")
        cost_layout.addWidget(scenario_note)

        cost_inputs = QHBoxLayout()
        self.cost_rig_rate = QDoubleSpinBox()
        self.cost_rig_rate.setRange(0, 1000000)
        self.cost_rig_rate.setValue(40000)
        self.cost_rig_rate.setSuffix(" /day (assumed)")
        self.cost_trip_h = QDoubleSpinBox()
        self.cost_trip_h.setRange(0, 100)
        self.cost_trip_h.setValue(6)
        self.cost_trip_h.setSuffix(" hr")
        self.cost_bit_cost = QDoubleSpinBox()
        self.cost_bit_cost.setRange(0, 100000)
        self.cost_bit_cost.setValue(2000)
        self.cost_bit_cost.setSuffix(" (assumed)")
        cost_inputs.addWidget(QLabel("Rig rate:"))
        cost_inputs.addWidget(self.cost_rig_rate)
        cost_inputs.addWidget(QLabel("Trip:"))
        cost_inputs.addWidget(self.cost_trip_h)
        cost_inputs.addWidget(QLabel("Bit cost:"))
        cost_inputs.addWidget(self.cost_bit_cost)
        cost_inputs.addStretch()
        cost_calc_btn = QPushButton("🔄 Compare Runs")
        cost_calc_btn.setStyleSheet("""
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
        cost_calc_btn.clicked.connect(self._update_cost_comparison)
        cost_inputs.addWidget(cost_calc_btn)
        cost_layout.addLayout(cost_inputs)

        self.cost_table = QTableWidget()
        self.cost_table.setColumnCount(6)
        self.cost_table.setHorizontalHeaderLabels(
            ["Bit Run", "Footage (m)", "Hours", "Scenario Rig+Bit Cost",
             "Scenario Cost/ft", "vs Best"])
        self.cost_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cost_table.setMaximumHeight(200)
        cost_layout.addWidget(self.cost_table)
        main_layout.addWidget(cost_widget)

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
        stats_widget.setObjectName("nptStatsPanel")   # scoped: see init_ui header
        stats_widget.setStyleSheet("QWidget#nptStatsPanel { background: #34495e; border-radius: 8px; padding: 12px; }")
        stats_layout = QGridLayout(stats_widget)
        
        self.npt_total_card = self.create_stat_card("⏱️", "Total NPT", "—", "hours", "#e74c3c")
        self.npt_percent_card = self.create_stat_card("📊", "NPT %", "—", "% of recorded time", "#f39c12")
        self.npt_daily_card = self.create_stat_card("📅", "Daily Avg", "—", "hours/day", "#3498db")
        self.npt_category_card = self.create_stat_card("🔥", "Top Category", "—", "", "#9b59b6")
        self.npt_total_card.setToolTip(ev.kpi_tooltip("total_npt"))
        self.npt_percent_card.setToolTip(ev.kpi_tooltip("npt_percent"))
        self.npt_daily_card.setToolTip(ev.kpi_tooltip("npt_daily_avg"))
        self.npt_category_card.setToolTip(
            "NPT code (TimeLog24H.main_code) with the most NPT hours in the scope. "
            "Rows without a code are shown as '" + ev.UNCLASSIFIED_NPT + "', never remapped.")
        self.npt_coverage_label = QLabel("Time coverage: —")
        self.npt_coverage_label.setWordWrap(True)
        self.npt_coverage_label.setToolTip(
            "A report date is fully covered when its time-log rows all have a valid duration "
            "and an NPT/productive flag and add up to >= 95% of 24 h (no more than 24 h).")
        
        stats_layout.addWidget(self.npt_total_card, 0, 0)
        stats_layout.addWidget(self.npt_percent_card, 0, 1)
        stats_layout.addWidget(self.npt_daily_card, 1, 0)
        stats_layout.addWidget(self.npt_category_card, 1, 1)
        stats_layout.addWidget(self.npt_coverage_label, 2, 0, 1, 2)
        main_layout.addWidget(stats_widget)
        
        # NPT Pie Chart
        chart_container = QWidget()
        chart_container.setStyleSheet("background: #1e1e1e; border-radius: 8px;")
        chart_container.setMinimumHeight(300)
        chart_layout = QVBoxLayout(chart_container)
        
        self.npt_pie_plot = _analysis_plot_widget()
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
        card.setObjectName("statCard")   # scoped: see create_kpi_card_modern
        card.setStyleSheet(
            f"""
            QFrame#statCard {{
                background: {_qss_rgba(color, "20")};
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
        card.unit = unit
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
        today_widget.setMinimumHeight(280)
        today_widget.setObjectName("todaySummary")   # scoped: see init_ui header
        today_widget.setStyleSheet("""
            QWidget#todaySummary {
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
            ("🌡️", "MW In/Out (PCF)", "mw_in_out"),
            ("🧪", "DDR Header MW (PCF)", "mw_header_pcf"),
            ("🧪", "Mud Sample MW (PCF)", "mw_sample_pcf"),
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
        
        self.analytics_plot = _analysis_plot_widget()
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
        self.milestones_scope_label = QLabel("Scope: Whole Well")
        self.milestones_scope_label.setStyleSheet(
            "color: #9aa5b1; font-style: italic; padding: 2px 4px;")
        milestones_layout.addWidget(self.milestones_scope_label)
        self.milestones_widget = QWidget()
        self.milestones_widget.setLayout(QVBoxLayout())
        milestones_layout.addWidget(self.milestones_widget)
        milestones_group.setLayout(milestones_layout)
        main_layout.addWidget(milestones_group)
        
        main_layout.addStretch()
        scroll.setWidget(content)
        return scroll

    # ==================== EVIDENCE (metric -> trend -> source report) ====================
    def create_evidence_tab(self):
        """Evidence-linked workflow inside the Analysis page.

        Scope -> date range -> metric -> dated trend (unit, scope, source) ->
        pick a point -> open its daily report (only through an explicit,
        unambiguous report_id) -> source rows with their data state -> typed
        CSV/XLSX export built from the same dataset as the chart and table.
        """
        content = QWidget()
        layout = QVBoxLayout(content)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Metric:"))
        self.evidence_metric = QComboBox()
        for key, (title, unit, _definition) in ev.EVIDENCE_METRICS.items():
            self.evidence_metric.addItem(f"{title} ({unit})", key)
        controls.addWidget(self.evidence_metric)
        controls.addWidget(QLabel("Scope:"))
        self.evidence_level = QComboBox()
        self.evidence_level.addItem("Selected well / wellbore", ev.SCOPE_WELL)
        self.evidence_level.addItem("Selected section", ev.SCOPE_SECTION)
        self.evidence_level.addItem("Selected daily report", ev.SCOPE_REPORT)
        controls.addWidget(self.evidence_level)
        self.evidence_range_check = QCheckBox("Date range:")
        controls.addWidget(self.evidence_range_check)
        self.evidence_from = QDateEdit()
        self.evidence_to = QDateEdit()
        for edit in (self.evidence_from, self.evidence_to):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
            edit.setDate(QDate.currentDate())
            edit.setEnabled(False)
        controls.addWidget(self.evidence_from)
        controls.addWidget(QLabel("to"))
        controls.addWidget(self.evidence_to)
        self.evidence_range_check.toggled.connect(self.evidence_from.setEnabled)
        self.evidence_range_check.toggled.connect(self.evidence_to.setEnabled)
        controls.addStretch()
        layout.addLayout(controls)

        actions = QHBoxLayout()
        self.evidence_load_btn = QPushButton("🔄 Show Evidence")
        self.evidence_open_btn = QPushButton("📄 Open Source Report")
        self.evidence_open_btn.setEnabled(False)
        self.evidence_csv_btn = QPushButton("📤 Export CSV")
        self.evidence_xlsx_btn = QPushButton("📤 Export XLSX")
        for button in (self.evidence_load_btn, self.evidence_open_btn,
                       self.evidence_csv_btn, self.evidence_xlsx_btn):
            button.setStyleSheet(self.get_button_style("info"))
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.evidence_load_btn.clicked.connect(self.refresh_evidence)
        self.evidence_open_btn.clicked.connect(self.open_evidence_report)
        self.evidence_csv_btn.clicked.connect(lambda: self.export_evidence("csv"))
        self.evidence_xlsx_btn.clicked.connect(lambda: self.export_evidence("xlsx"))
        self.evidence_metric.currentIndexChanged.connect(lambda _i: self.refresh_evidence())
        self.evidence_level.currentIndexChanged.connect(lambda _i: self.refresh_evidence())

        self.evidence_state_label = QLabel("Evidence: select a well")
        self.evidence_state_label.setWordWrap(True)
        self.evidence_state_label.setStyleSheet("font-weight: bold; padding: 4px; color: #ecf0f1;")
        layout.addWidget(self.evidence_state_label)

        self.evidence_plot = pg.PlotWidget(
            background=_CHART_BACKGROUND, axisItems={"bottom": pg.DateAxisItem(orientation="bottom")})
        for name in ("left", "bottom"):
            axis = self.evidence_plot.getPlotItem().getAxis(name)
            axis.setPen(pg.mkPen(_CHART_FOREGROUND))
            axis.setTextPen(pg.mkPen(_CHART_FOREGROUND))
        self.evidence_plot.setMinimumHeight(260)
        self.evidence_plot.setTitle("No well selected", color="#95a5a6")
        layout.addWidget(self.evidence_plot)

        self.evidence_table = QTableWidget()
        self.evidence_table.setColumnCount(8)
        self.evidence_table.setHorizontalHeaderLabels(
            ["Date", "Value", "Unit", "State", "Reason", "Report ID", "Wellbore ID", "Source"])
        self.evidence_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.evidence_table.horizontalHeader().setStretchLastSection(True)
        self.evidence_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.evidence_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.evidence_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.evidence_table.itemSelectionChanged.connect(self._on_evidence_selection)
        layout.addWidget(self.evidence_table)
        return content

    def _evidence_range(self):
        if not self.evidence_range_check.isChecked():
            return None, None
        start = self.evidence_from.date().toPython()
        end = self.evidence_to.date().toPython()
        return (start, end) if start <= end else (end, start)

    def update_evidence(self):
        self.refresh_evidence()

    def refresh_evidence(self):
        """Read and show the evidence rows for metric x scope x date range."""
        self._evidence_rows = []
        self._evidence_meta = None
        self._evidence_highlight = None        # removed by clear() below
        self.evidence_open_btn.setEnabled(False)
        self.evidence_plot.clear()
        self.evidence_table.setRowCount(0)
        if not self.current_well_id:
            self.evidence_state_label.setText("Evidence: select a well")
            self.evidence_plot.setTitle("No well selected", color="#95a5a6")
            return
        metric_key = self.evidence_metric.currentData()
        title, unit, definition = ev.EVIDENCE_METRICS[metric_key]
        scope = self._analysis_scope(self.evidence_level.currentData())
        problem = scope.problem()
        if problem:
            self.evidence_state_label.setText(f"Evidence: NOT ASSESSED - {problem}")
            self.evidence_plot.setTitle(f"NOT ASSESSED - {problem}", color="#95a5a6")
            return
        start, end = self._evidence_range()
        self.evidence_state_label.setText("Evidence: loading…")
        rows = self._fetch_cached(
            f"evidence:{metric_key}:{scope.key()}",
            lambda session: ev.evidence_for_metric(session, scope, metric_key))
        if rows is _STALE:
            return
        if isinstance(rows, _LoadError):
            self.evidence_state_label.setText("Evidence: " + rows.text())
            self.evidence_plot.setTitle(rows.text(), color="#e74c3c")
            return
        rows = ev.filter_range(rows, start, end)
        range_text = f"{start} to {end}" if start else "all dates"
        self._evidence_rows = rows
        self._evidence_meta = ev.export_metadata(
            scope.label(), metric_key, unit, definition, range_text,
            {"well_id": scope.well_id, "wellbore_id": scope.wellbore_id,
             "section_id": scope.section_id if scope.level != ev.SCOPE_WELL else None,
             "report_id": scope.report_id if scope.level == ev.SCOPE_REPORT else None,
             "rows": len(rows),
             "valid_rows": sum(1 for r in rows if r.state == ev.STATE_VALUE)})
        if not rows:
            self.evidence_state_label.setText(
                f"Evidence: No data - {title} has no rows for {scope.label()} ({range_text})")
            self.evidence_plot.setTitle("No data in this scope and range", color="#95a5a6")
            return
        valid_idx = [i for i, r in enumerate(rows) if r.state == ev.STATE_VALUE and r.value is not None]
        valid = [rows[i] for i in valid_idx]
        self.evidence_state_label.setText(
            f"Evidence: {title} [{unit}] | {scope.label()} | {range_text} | "
            f"{len(valid)} valid of {len(rows)} rows | source: {rows[0].source.split('#')[0]}")
        self.evidence_plot.setTitle(f"{title} [{unit}] - {scope.label()}", color="#ffffff")
        self.evidence_plot.setLabel("left", f"{title} ({unit})")
        if valid:
            stamps = [datetime(r.date.year, r.date.month, r.date.day).timestamp() for r in valid]
            self.evidence_plot.plot(stamps, [r.value for r in valid],
                                    pen=pg.mkPen('#3498db', width=2))
            scatter = pg.ScatterPlotItem(
                x=stamps, y=[r.value for r in valid], size=10, brush=pg.mkBrush('#f1c40f'),
                data=valid_idx)
            scatter.sigClicked.connect(self._on_evidence_point_clicked)
            self.evidence_plot.addItem(scatter)
        self.evidence_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            cells = [str(row.date), "—" if row.value is None else f"{row.value:.2f}", row.unit,
                     row.state, row.reason, "" if row.report_id is None else str(row.report_id),
                     "" if row.wellbore_id is None else str(row.wellbore_id), row.source]
            for col, text in enumerate(cells):
                self.evidence_table.setItem(i, col, QTableWidgetItem(text))

    def _on_evidence_point_clicked(self, _item, points, *_args):
        if len(points):
            self.select_evidence_row(points[0].data())

    def select_evidence_row(self, index):
        if 0 <= index < self.evidence_table.rowCount():
            self.evidence_table.selectRow(index)

    def _selected_evidence(self):
        rows = self.evidence_table.selectionModel().selectedRows() if self.evidence_table.selectionModel() else []
        if not rows:
            return None
        index = rows[0].row()
        return self._evidence_rows[index] if index < len(self._evidence_rows) else None

    def _on_evidence_selection(self):
        row = self._selected_evidence()
        self._highlight_evidence_point(row)
        enabled = row is not None and row.drilldown_report_id is not None
        self.evidence_open_btn.setEnabled(enabled)
        if row is not None:
            self.evidence_open_btn.setToolTip(
                f"Open daily report #{row.report_id}" if enabled else row.drilldown_reason())

    def _highlight_evidence_point(self, row):
        """Ring the selected row's point; rows without a value get no marker."""
        old = getattr(self, "_evidence_highlight", None)
        if old is not None:
            self.evidence_plot.removeItem(old)
            self._evidence_highlight = None
        if row is None or row.state != ev.STATE_VALUE or row.value is None or row.date is None:
            return
        stamp = datetime(row.date.year, row.date.month, row.date.day).timestamp()
        self._evidence_highlight = pg.ScatterPlotItem(
            x=[stamp], y=[row.value], size=20, symbol="o",
            pen=pg.mkPen("#e74c3c", width=3), brush=pg.mkBrush(0, 0, 0, 0))
        self.evidence_plot.addItem(self._evidence_highlight)

    def open_evidence_report(self):
        """Open the selected point's daily report — only via its explicit report_id."""
        row = self._selected_evidence()
        if row is None or row.drilldown_report_id is None:
            return False
        session = self.db.create_session()
        try:
            report = session.get(DailyReport, row.drilldown_report_id)
            if report is None or report.well_id != self.current_well_id:
                self.show_error("The source report no longer belongs to this well")
                return False
            ids = (report.well_id, report.wellbore_id, report.section_id, report.id)
        finally:
            session.close()
        well_id, wellbore_id, section_id, report_id = ids
        payload = {"id": report_id, "well_id": well_id, "wellbore_id": wellbore_id,
                   "section_id": section_id}
        self.sel_manager.select_full_context(
            well_id, section_id, report_id, well_data={"name": self.current_well_name},
            report_data=payload, wellbore_id=wellbore_id,
            wellbore_data={"id": wellbore_id, "well_id": well_id} if wellbore_id else None)
        return True

    def export_evidence(self, fmt, filename=None):
        """Typed export of the shown evidence rows (never the table's text)."""
        if not self._evidence_rows or not self._evidence_meta:
            self.show_warning("No evidence rows to export for this scope")
            return None
        if filename is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename, _ = QFileDialog.getSaveFileName(
                self, "Export Evidence", f"evidence_{self._evidence_meta['metric']}_{stamp}.{fmt}",
                "Excel Files (*.xlsx)" if fmt == "xlsx" else "CSV Files (*.csv)")
            if not filename:
                return None
        try:
            writer = ev.export_xlsx if fmt == "xlsx" else ev.export_csv
            count = writer(filename, self._evidence_rows, self._evidence_meta)
        except Exception as exc:
            logger.error("Evidence export failed: %s", type(exc).__name__, exc_info=True)
            self.show_error(f"Export failed: {type(exc).__name__}")
            return None
        self.show_success(f"Exported {count} evidence rows to {os.path.basename(filename)}")
        return filename

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
        """Return a cached value or read it; a failed read is never cached."""
        now = QDateTime.currentMSecsSinceEpoch()
        if key in self.data_cache and (now - self.cache_time[key] < self.cache_timeout):
            return self.data_cache[key]
        data = get_data_func()
        self.data_cache[key] = data
        self.cache_time[key] = now
        return data

    def _cache_key(self, name):
        """Every dimension that changes a result: scope, section, report, data revision."""
        return (f"{name}|{self._scope_key()}|section={getattr(self, 'current_section_id', None)}"
                f"|report={getattr(self, 'current_report_id', None)}|rev={self._data_rev}")

    def _fetch_cached(self, name, reader):
        """Read ``reader(session)`` for the current scope through the cache.

        Returns the value, a ``_LoadError`` (read failed; not cached, shown as
        an error with Retry) or ``_STALE`` when the selection changed while the
        value was being read (the caller must not paint it).
        """
        generation = self._generation

        def fetch():
            session = self.db.create_session()
            try:
                return reader(session)
            finally:
                session.close()

        try:
            value = self.get_cached_data(self._cache_key(name), fetch)
        except Exception as exc:
            logger.error("Analysis read failed (%s): %s", name, type(exc).__name__, exc_info=True)
            value = _LoadError(exc)
        if generation != self._generation:
            return _STALE
        if isinstance(value, _LoadError):
            # Painted per card/chart as "Read error"; also reported in the page
            # status so a handled read failure is never summarised as "Updated".
            self._load_errors.append(name.split(":")[0])
        return value

    def _read_revision(self):
        session = self.db.create_session()
        try:
            return ev.data_revision(session, self.current_well_id)
        finally:
            session.close()

    def _analysis_scope(self, level=ev.SCOPE_WELL):
        return ev.AnalysisScope(
            well_id=self.current_well_id,
            wellbore_id=getattr(self, "current_wellbore_id", None),
            section_id=getattr(self, "current_section_id", None),
            report_id=getattr(self, "current_report_id", None),
            level=level)

    def _report_date_unambiguous(self, session, report):
        """True when (well_id, report_date) maps to exactly ONE DailyReport.

        Used to gate the legacy well+date fallback for child rows that predate
        report_id linkage. When more than one report shares the well and date
        (the multi-bore case), a well+date lookup cannot prove which bore a
        child row belongs to, so the fallback must be refused (UNKNOWN) rather
        than risk pulling another bore's row.
        """
        return session.query(DailyReport.id).filter(
            DailyReport.well_id == report.well_id,
            DailyReport.report_date == report.report_date).count() == 1

    def _unique_legacy_row(self, session, model, well_id, report_date):
        """Return the single legacy child row for (well_id, report_date), or
        None when there are zero OR MORE THAN ONE.

        The legacy well+date fallback only proves ownership when it maps to a
        single row. Two rows sharing the (well, date) make a bare ``.first()``
        nondeterministic and would silently hide one of them, so the ambiguous
        case must resolve to UNKNOWN (None), never a guessed row.
        """
        rows = session.query(model).filter(
            model.well_id == well_id,
            model.report_date == report_date,
            model.report_id.is_(None)).limit(2).all()
        return rows[0] if len(rows) == 1 else None

    def _scope_reports_query(self, session):
        """A DailyReport query filtered to the active scope.

        Bore selected -> DailyReport.wellbore_id == bore (unknown-bore reports
        excluded). Otherwise the whole well. Daily cards add their section/
        report filter in get_today_data; aggregate charts remain bore-wide.
        """
        q = session.query(DailyReport).filter(DailyReport.well_id == self.current_well_id)
        if self.current_wellbore_id:
            q = q.filter(DailyReport.wellbore_id == self.current_wellbore_id)
        return q

    def _scope_params_query(self, session):
        """A DrillingParameters query filtered to the active scope.

        Bore scope is resolved through the report ownership chain
        (DrillingParameters.report_id -> DailyReport.wellbore_id) so a
        parameter row is attributed to exactly the bore its report belongs to.
        """
        from core.operations_intelligence import canonical_params_clause

        q = session.query(DrillingParameters).filter(
            DrillingParameters.well_id == self.current_well_id)
        if not self.current_wellbore_id:
            # Whole well: the same legacy-row rule as the canonical service, so
            # best ROP / midpoints / series can never count a date twice.
            q = q.filter(canonical_params_clause(DrillingParameters))
        if self.current_wellbore_id:
            q = (q.join(DailyReport, DrillingParameters.report_id == DailyReport.id)
                  .filter(DailyReport.wellbore_id == self.current_wellbore_id))
        return q

    def calculate_kpis(self, session):
        """Scope-aware KPIs, with shared metrics from the canonical service.

        The metrics that also exist in ``OperationsIntelligenceService`` —
        current depth, average ROP, NPT hours, NPT%, rig days — are taken from
        that canonical implementation (well- OR bore-scoped) so W12 cannot
        silently disagree with the report engine or the intelligence dashboard.
        When a wellbore is selected the canonical bore rollup
        (``analyze_wellbore``) is used; otherwise the whole-well aggregate
        (``analyze_well``).

        Metrics that are W12-specific scalar reductions and not part of the
        canonical KPI contract (best ROP, mean WOB/RPM/torque midpoints,
        efficiency, daily depth gain) are computed here from the SAME scope,
        preserving the no-fabrication contract: unknown source data yields
        None, never 0.0.
        """
        well_id = self.current_well_id
        if not well_id:
            return dict.fromkeys(['current_depth','total_days','avg_rop','total_npt',
                                  'npt_percentage','best_rop','avg_wob','avg_rpm',
                                  'avg_torque','efficiency','daily_gain','reports'], None)

        # ---- Shared metrics: canonical source of truth (scope-aware) ----
        canonical = self._canonical_scope_kpis()
        if canonical.get("error"):
            # The canonical service caught a read failure and returned empty
            # KPIs; surfacing them would turn an error into "No data".
            raise RuntimeError(f"canonical KPI read failed: {canonical['error']}")
        cur_depth = canonical.get("current_depth")
        total_days = canonical.get("rig_days")
        avg_rop = canonical.get("average_rop")
        total_npt = canonical.get("npt_hours")
        npt_pct = canonical.get("npt_percent")
        # Efficiency is the complement of NPT% and shares its unknown semantics.
        efficiency = (100 - npt_pct) if npt_pct is not None else None

        # ---- W12-specific reductions (not in the canonical KPI contract) ----
        # All scoped to the same bore/well so they can never mix bores.
        # Best ROP shares the canonical validity rule (finite, >= 0): a stored
        # inf or negative rate must not become the "best" run.
        best_rop = ev.summarize_rop(
            v for (v,) in self._scope_params_query(session)
            .with_entities(DrillingParameters.avg_rop).all())["best"]

        def _mean_mid(low_col, high_col):
            mids = ev.midpoint_series(
                self._scope_params_query(session).with_entities(low_col, high_col).all())
            return (sum(mids) / len(mids)) if mids else None

        avg_wob = _mean_mid(DrillingParameters.wob_min, DrillingParameters.wob_max)
        avg_rpm = _mean_mid(DrillingParameters.rpm_min, DrillingParameters.rpm_max)
        avg_torque = _mean_mid(DrillingParameters.torque_min, DrillingParameters.torque_max)

        # Calendar-rate endpoints must be unique and belong to the same bore.
        # A bare first() silently chose among multiple sections/bores on a day.
        daily_gain = None
        reports = self._scope_reports_query(session).order_by(DailyReport.report_date).all()
        if reports:
            first_rows = [r for r in reports if r.report_date == reports[0].report_date]
            last_rows = [r for r in reports if r.report_date == reports[-1].report_date]
            if len(first_rows) == len(last_rows) == 1:
                first, latest = first_rows[0], last_rows[0]
                elapsed = (latest.report_date - first.report_date).days
                if (elapsed > 0 and first.wellbore_id == latest.wellbore_id
                        and first.depth_2400 is not None and latest.depth_2400 is not None):
                    daily_gain = (latest.depth_2400 - first.depth_2400) / elapsed

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
            'daily_gain': daily_gain,
            # Secondary, canonical facts used by the card subtitles (trend
            # lines are shown only when these are valid).
            'daily_progress': canonical.get("daily_progress"),
            'weighted_rop': canonical.get("weighted_rop"),
            # Number of daily reports in the scope: 0 shows "No daily reports
            # in this scope" instead of per-card "No data".
            'reports': len(reports),
        }

    def get_today_data(self, session):
        well_id = self.current_well_id
        if not well_id:
            return None
        query = self._scope_reports_query(session)
        # Daily cards are report-level, unlike the bore-wide KPI/chart rollups.
        section_id = getattr(self, "current_section_id", None)
        if section_id is not None:
            query = query.filter(DailyReport.section_id == section_id)
        selected = getattr(self, "current_report_id", None)
        if selected is not None:
            candidates = query.filter(DailyReport.id == selected).all()
        else:
            latest_date = query.with_entities(func.max(DailyReport.report_date)).scalar()
            candidates = query.filter(DailyReport.report_date == latest_date).limit(2).all()
        report = candidates[0] if len(candidates) == 1 else None
        if not report:
            return None
        from core.operational_time import summarize_time_logs
        time_metrics = summarize_time_logs(session.query(TimeLog24H).filter_by(report_id=report.id).all())
        hours, npt_hours = time_metrics["total_hours"], time_metrics["npt_hours"]
        # Bind parameters/mud to THIS report via report_id (the report is
        # already scope-selected). A well+date fallback is ONLY used when it is
        # provably unambiguous — i.e. this (well, date) maps to a single report
        # (legacy single-bore data whose child rows predate report_id linkage).
        # In a multi-bore day two reports share the date, so the fallback cannot
        # prove ownership and would leak another bore's row: then stay UNKNOWN.
        # The fallback is also refused when MORE THAN ONE legacy child row shares
        # the (well, date): a bare .first() there is nondeterministic and would
        # silently hide the other row(s). Ambiguity -> UNKNOWN, not a guess.
        rows = session.query(DrillingParameters).filter(
            DrillingParameters.report_id == report.id).limit(2).all()
        dr = rows[0] if len(rows) == 1 else None
        if not rows and self._report_date_unambiguous(session, report):
            dr = self._unique_legacy_row(
                session, DrillingParameters, well_id, report.report_date)
        rows = session.query(MudReport).filter(
            MudReport.report_id == report.id).limit(2).all()
        mud = rows[0] if len(rows) == 1 else None
        if not rows and self._report_date_unambiguous(session, report):
            mud = self._unique_legacy_row(
                session, MudReport, well_id, report.report_date)

        def _mid(lo, hi):
            # Midpoint only when BOTH bounds are known; otherwise unknown (None),
            # never a half-fabricated value from a single bound treated as 0.
            if lo is None or hi is None:
                return None
            return (lo + hi) / 2

        # Unknown physical measurements stay None (rendered "—"), never 0. An
        # explicit reported 0 (e.g. depth_2400 == 0) is preserved as a fact.
        return {
            'depth': report.depth_2400,
            'rop': dr.avg_rop if dr else None,
            'hours': hours,
            'rig_day': report.rig_day,
            'npt_hours': npt_hours,
            'mw_in': report.mud_weight_in,
            'mw_out': report.mud_weight_out,
            'mw_header_pcf': report.mw_pcf,
            'mw_sample_pcf': mud.mw if mud else None,
            'mud_weight': mud.mw if mud else None,
            'main_activity': None,  # no authoritative activity classification on this header
            'wob': _mid(dr.wob_min, dr.wob_max) if dr else None,
            'rpm': _mid(dr.rpm_min, dr.rpm_max) if dr else None,
            'torque': _mid(dr.torque_min, dr.torque_max) if dr else None,
            'pressure': _mid(dr.pump_pressure_min, dr.pump_pressure_max) if dr else None
        }

    def get_performance_data(self, session):
        well_id = self.current_well_id
        if not well_id:
            return []
        params = self._scope_params_query(session)\
                        .order_by(DrillingParameters.report_date).all()

        def _mid(lo, hi):
            # Midpoint only when BOTH bounds are valid numbers (finite, >= 0);
            # a single known bound is NOT half a value. Unknown stays None
            # (rendered "—"), never 0. Same rule as calculate_kpis.
            mids = ev.midpoint_series([(lo, hi)])
            return mids[0] if mids else None

        return [{
            'date': p.report_date,
            'bit_run': p.bit_no or f"Bit #{i+1}",
            # avg_rop None = unknown (not measured); a real 0.0 is preserved.
            'rop': p.avg_rop,
            'wob': _mid(p.wob_min, p.wob_max),
            'rpm': _mid(p.rpm_min, p.rpm_max),
            'torque': _mid(p.torque_min, p.torque_max),
            'pressure': _mid(p.pump_pressure_min, p.pump_pressure_max),
            'depth': p.depth_out,
            'depth_in': p.depth_in,
            'hours_on_bottom': p.hours_on_bottom,
            'bit_size': p.bit_size,
        } for i, p in enumerate(params)]

    def get_time_depth_data(self, session):
        well_id = self.current_well_id
        if not well_id:
            return []
        reports = self._scope_reports_query(session)\
                         .order_by(DailyReport.report_date).all()
        data = []
        # ``prev`` is the last KNOWN depth, or None until one is seen. A missing
        # depth must NOT be treated as 0 — doing so fabricates a huge false
        # depth loss on the first gap and a false recovery afterwards. Missing
        # depth => depth None (chart gap) and gain None (unknown), never 0.
        prev = None
        prev_bore = None
        first_date = reports[0].report_date if reports else None
        for r in reports:
            if r.wellbore_id != prev_bore:
                prev = None
            d = r.depth_2400  # trichotomy preserved: None stays unknown
            if d is None:
                gain = None
                status = 'Unknown'
            elif prev is None:
                # First known depth: no prior reference to measure a gain from.
                gain = None
                status = 'Unknown'
            else:
                gain = d - prev
                status = 'Normal' if gain > 0 else 'Depth decreased' if gain < 0 else 'Unchanged'
            data.append({'date': r.report_date, 'day': (r.report_date - first_date).days + 1, 'depth': d,
                         'gain': gain, 'status': status})
            if d is not None:
                prev = d
                prev_bore = r.wellbore_id
        return data

    def get_npt_data(self, session):
        well_id = self.current_well_id
        if not well_id:
            return {'entries': [], 'categories': {}, 'total_npt': None,
                    'npt_percentage': None, 'total_hours': None,
                    'unknown_npt_count': 0, 'report_dates': None,
                    'coverage': ev.npt_coverage_summary([]), 'days': []}
        npt_q = session.query(TimeLog24H, DailyReport).join(DailyReport)\
                          .filter(DailyReport.well_id == well_id, TimeLog24H.is_npt.is_(True))
        if self.current_wellbore_id:
            npt_q = npt_q.filter(DailyReport.wellbore_id == self.current_wellbore_id)
        npt_rows = npt_q.order_by(DailyReport.report_date, TimeLog24H.time_from).all()
        entries = []
        cats = {}
        total_npt = 0.0
        unknown_count = 0  # NPT rows whose duration is NULL (unprovable length)
        for log, rep in npt_rows:
            # A NULL duration is UNKNOWN, not 0.0: it must not silently
            # contribute a fabricated zero to the total, and the entry keeps
            # None so the row can render as "—" rather than "0.00". A stored
            # 0.0 is a real fact and is summed/displayed as 0.0.
            h = log.duration
            cat = (log.main_code or "").strip() or ev.UNCLASSIFIED_NPT
            if h is None:
                unknown_count += 1
            else:
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
        # NPT% is unknown when no time has been recorded for the well; the
        # denominator is genuinely unknown, not 1. With recorded time and no NPT
        # rows, NPT is a real 0.0 and the percentage is a real 0%.
        from core.operational_time import summarize_time_logs
        th_q = session.query(TimeLog24H).join(DailyReport).filter(DailyReport.well_id == well_id)
        if self.current_wellbore_id:
            th_q = th_q.filter(DailyReport.wellbore_id == self.current_wellbore_id)
        metrics = summarize_time_logs(th_q.all())
        scope = ev.AnalysisScope(well_id=well_id,
                                 wellbore_id=getattr(self, "current_wellbore_id", None))
        days = ev.npt_daily_series(*ev.load_npt_inputs(session, scope))
        return {'entries': entries, 'categories': cats, 'total_npt': metrics["npt_hours"],
                'npt_percentage': metrics["npt_percent"], 'total_hours': metrics["total_hours"],
                'known_npt_hours': metrics["known_npt_hours"],
                'unknown_npt_count': unknown_count,
                # Same scope as the NPT rows: distinct report dates (the
                # daily-average denominator) and per-date time coverage.
                'report_dates': len({d.date for d in days}),
                'coverage': ev.npt_coverage_summary(days),
                'days': days}

    # ---- Scope helpers ----
    def _scope_key(self):
        """Cache-key suffix that encodes the active scope.

        Whole-well and each bore get distinct keys so switching scope can never
        surface another scope's cached numbers (§13). Section scope, when a
        section is selected without a bore, is encoded too.
        """
        if self.current_wellbore_id:
            return f"wellbore:{self.current_wellbore_id}"
        if getattr(self, "current_section_id", None):
            return f"section:{self.current_section_id}"
        return f"well:{self.current_well_id}"

    def _canonical_scope_kpis(self):
        """Canonical KPIs for the active scope, from the intelligence service.

        Bore selected  -> analyze_wellbore (bore-only, ownership-chain scoped).
        Section only    -> analyze_section.
        Otherwise       -> analyze_well (whole-well aggregate).
        Formulas are never duplicated here — W12 is a consumer of the canonical
        analytical owner (§9, §37).
        """
        service = getattr(self, "intelligence_service", None)
        if service is None:
            from core.operations_intelligence import OperationsIntelligenceService
            service = OperationsIntelligenceService(self.db)
        if self.current_wellbore_id:
            return service.analyze_wellbore(self.current_wellbore_id).get("kpis", {})
        if getattr(self, "current_section_id", None) and not self.current_well_id:
            return service.analyze_section(self.current_section_id).get("kpis", {})
        return service.analyze_well(self.current_well_id).get("kpis", {})

    # ---- Data update methods ----
    @staticmethod
    def _is_number(value):
        return ev.classify_number(value, allow_negative=True)[0] == ev.STATE_VALUE

    def update_kpi_data(self):
        """Main KPI cards: real value + unit, No data, or Read error — never a 0 placeholder."""
        if not self.current_well_id:
            return
        kpis = self._fetch_cached("kpis", self.calculate_kpis)
        if kpis is _STALE:
            return
        if isinstance(kpis, _LoadError):
            self._last_kpis = None
            for card in self.kpi_cards:
                self._set_kpi_card(card, ev.MetricValue(ev.STATE_ERROR, reason=kpis.detail),
                                   kpis.text())
            return
        self._last_kpis = kpis
        if len(self.kpi_cards) < 4:
            return
        units = [ev.KPI_DEFINITIONS[k][1] for k in ("current_depth", "rig_days", "avg_rop", "total_npt")]
        if kpis.get("reports") == 0:
            none = [ev.MetricValue(ev.STATE_MISSING, unit=u, reason="no daily reports in this scope")
                    for u in units]
            for card, mv in zip(self.kpi_cards, none):
                self._set_kpi_card(card, mv, "No daily reports in this scope")
            return
        npt_missing = ("NPT unknown: no time logs in this scope, or a row lacks a valid "
                       "duration or NPT flag")
        values = [
            ev.metric(kpis["current_depth"], units[0], 1, allow_negative=False,
                      missing_reason="no report with a recorded depth in this scope"),
            ev.metric(kpis["total_days"], units[1], 0, allow_negative=False,
                      missing_reason="no daily reports in this scope"),
            ev.metric(kpis["avg_rop"], units[2], 1, allow_negative=False,
                      missing_reason="no valid DrillingParameters.avg_rop in this scope"),
            ev.metric(kpis["total_npt"], units[3], 1, allow_negative=False,
                      missing_reason=npt_missing),
        ]
        progress, weighted, pct = (kpis.get("daily_progress"), kpis.get("weighted_rop"),
                                   kpis.get("npt_percentage"))
        trends = [
            f"Δ last day: {progress:+.1f} m" if self._is_number(progress) else "Δ last day: not assessed",
            "Distinct report dates" if values[1].has_value else "",
            f"Footage-weighted: {weighted:.1f} m/hr" if self._is_number(weighted)
            else "Footage-weighted: not assessed",
            f"{pct:.1f}% of recorded time" if self._is_number(pct) else "NPT %: not assessed",
        ]
        for card, mv, trend in zip(self.kpi_cards, values, trends):
            self._set_kpi_card(card, mv, trend)

    def update_time_depth_data(self):
        if not self.current_well_id:
            return
        data = self._fetch_cached("td", self.get_time_depth_data)
        if data is _STALE:
            return
        if isinstance(data, _LoadError) or not data:
            failed = isinstance(data, _LoadError)
            self.time_depth_plot.clear()
            self.time_depth_plot.setTitle(
                data.text() if failed else "No daily reports in this scope",
                color="#e74c3c" if failed else "#95a5a6")
            self.daily_gain_plot.clear()
            self.time_depth_table.setRowCount(0)
            self.chart_data['time_depth'] = None
            return
        self.time_depth_plot.setTitle(
            "Depth at 24:00 (m) vs report day", color="#ffffff")

        # Plot only KNOWN depths — a missing depth is a gap in the series, not a
        # data point at 0 m. Fabricating 0 would draw a false plunge to surface.
        depth_days = [d['day'] for d in data if d['depth'] is not None]
        depth_vals = [d['depth'] for d in data if d['depth'] is not None]
        gain_days = [d['day'] for d in data if d['gain'] is not None]
        gain_vals = [d['gain'] for d in data if d['gain'] is not None]

        self.time_depth_plot.clear()
        if depth_vals:
            self.time_depth_plot.plot(
                depth_days, depth_vals,
                pen=pg.mkPen(color="#3498db", width=3),
                symbol='o', symbolSize=8,
                symbolBrush="#2980b9", name="Depth"
            )

        if (len(depth_days) > 1
                and len(set(depth_days)) > 1
                and hasattr(self, 'td_show_trend')
                and self.td_show_trend.isChecked()):
            fit = ev.least_squares(depth_days, depth_vals)
            if fit is not None:
                slope, intercept = fit
                self.time_depth_plot.plot(
                    depth_days, [slope * x + intercept for x in depth_days],
                    pen=pg.mkPen(
                        color="#e74c3c", width=2,
                        style=Qt.DashLine
                    ),
                    name="Trend Line"
                )

        self.daily_gain_plot.clear()
        if gain_vals:
            self.daily_gain_plot.plot(
                gain_days, gain_vals,
                pen=pg.mkPen(color="#2ecc71", width=2),
                fillLevel=0, brush="#27ae6050",
                name="Report depth change"
            )

        self.time_depth_table.setRowCount(len(data))
        for i, row in enumerate(data):
            self.time_depth_table.setItem(
                i, 0, QTableWidgetItem(str(row['date']))
            )
            self.time_depth_table.setItem(
                i, 1, QTableWidgetItem(str(row['day']))
            )
            # Unknown depth/gain render as "—", never a fabricated 0.0.
            self.time_depth_table.setItem(
                i, 2, QTableWidgetItem(
                    "—" if row['depth'] is None else f"{row['depth']:.1f}")
            )
            self.time_depth_table.setItem(
                i, 3, QTableWidgetItem(
                    "—" if row['gain'] is None else f"{row['gain']:.1f}")
            )
            self.time_depth_table.setItem(
                i, 4, QTableWidgetItem(row['status'])
            )

        self.chart_data['time_depth'] = {
            'days': depth_days,
            'depths': depth_vals,
            'gains': gain_vals,
            'data': data
        }

    def update_npt_data(self):
        if not self.current_well_id:
            return
        data = self._fetch_cached("npt", self.get_npt_data)
        if data is _STALE:
            return
        cards = (self.npt_total_card, self.npt_percent_card, self.npt_daily_card)
        if isinstance(data, _LoadError):
            error = ev.MetricValue(ev.STATE_ERROR, reason=data.detail)
            for card in cards:
                self._set_stat_card(card, error)
            self._set_category_card(ev.STATE_TEXT[ev.STATE_ERROR], data.detail)
            self.npt_coverage_label.setText("Time coverage: " + data.text())
            self.npt_table.setRowCount(0)
            self._replace_npt_pie(None, data.text())
            self.chart_data['npt'] = None
            return

        missing = ("NPT unknown: no time logs in this scope, or a row lacks a valid "
                   "duration or NPT flag")
        total = data['total_npt']
        self._set_stat_card(self.npt_total_card, ev.metric(total, "", 1, missing_reason=missing))
        self._set_stat_card(self.npt_percent_card,
                            ev.metric(data['npt_percentage'], "", 1, missing_reason=missing))
        dates = data.get('report_dates')
        daily = total / dates if total is not None and dates else None
        self._set_stat_card(self.npt_daily_card, ev.metric(
            daily, "", 1, missing_reason=missing if total is None else "no report dates in this scope"))

        categories = data['categories']
        if categories:
            self._set_category_card(max(categories, key=categories.get), "")
        elif total == 0.0:
            self._set_category_card("No NPT recorded", "recorded time contains no NPT rows")
        else:
            self._set_category_card(ev.STATE_TEXT[ev.STATE_MISSING], missing)

        cov = data.get('coverage') or ev.npt_coverage_summary([])
        others = ", ".join(f"{state.replace('_', ' ')} {count}"
                           for state, count in sorted(cov["by_state"].items())
                           if state != ev.STATE_VALUE)
        self.npt_coverage_label.setText(
            f"Time coverage: {cov['covered_days']} of {cov['days']} report dates fully covered "
            f"(>= {ev.COVERAGE_SUFFICIENT_PERCENT:.0f}% of 24 h)" + (f"; {others}" if others else ""))

        self.npt_table.setRowCount(len(data['entries']))
        for i, e in enumerate(data['entries']):
            self.npt_table.setItem(i, 0, QTableWidgetItem(str(e['date'])))
            for col, value in ((1, e.get('from')), (2, e.get('to'))):
                text = value.strftime("%H:%M") if value and hasattr(value, 'strftime') else str(value or "")
                self.npt_table.setItem(i, col, QTableWidgetItem(text))
            self.npt_table.setItem(i, 3, QTableWidgetItem(
                "—" if e['hours'] is None else f"{e['hours']:.2f}"))
            self.npt_table.setItem(i, 4, QTableWidgetItem(e['category']))
            self.npt_table.setItem(i, 5, QTableWidgetItem(e['description']))

        self._replace_npt_pie(categories or None)
        self.chart_data['npt'] = data

    def _set_category_card(self, text, tooltip):
        import html
        self.npt_category_card.value_label.setText(f"<b>{html.escape(str(text))}</b>")
        self.npt_category_card.value_label.setToolTip(tooltip)

    def draw_npt_pie_chart(self, categories):
        self._replace_npt_pie(categories or None)

    def _replace_npt_pie(self, categories, placeholder="No NPT categories in this scope"):
        """Swap the NPT pie; with nothing to draw show a placeholder.

        The previous canvas is always removed first, so a well without NPT can
        never keep showing the previous well's pie. The figure is a plain
        ``Figure`` (no pyplot registry), deleted with its canvas.
        """
        old = getattr(self, "_npt_pie_canvas", None)
        container = self.npt_pie_plot.parentWidget()
        layout = container.layout() if container is not None else None
        if old is not None:
            if layout is not None:
                layout.removeWidget(old)
            old.setParent(None)
            old.deleteLater()
            self._npt_pie_canvas = None
        self.npt_pie_plot.clear()
        positive = {k: v for k, v in (categories or {}).items() if v and v > 0}
        if not positive and categories:
            placeholder = "NPT recorded as 0 h in every category"
        canvas = self._npt_pie_canvas_for(positive) if positive and layout is not None else None
        if canvas is None:
            self.npt_pie_plot.setTitle(placeholder, color="#95a5a6")
            self.npt_pie_plot.show()
            return
        self.npt_pie_plot.hide()
        layout.addWidget(canvas)
        self._npt_pie_canvas = canvas

    def _npt_pie_canvas_for(self, categories):
        try:
            fig = Figure(figsize=(5, 4), facecolor='#1e1e1e')
            ax = fig.add_subplot(111)
            ax.set_facecolor('#1e1e1e')
            labels = list(categories.keys())
            colors = matplotlib.colormaps["Set3"](range(len(labels)))
            _wedges, _texts, percents = ax.pie(
                list(categories.values()), labels=labels, autopct='%1.1f%%', colors=colors,
                textprops={'color': 'white', 'fontsize': 8},
                wedgeprops={'edgecolor': 'white', 'linewidth': 0.5})
            for text in percents:          # inside pastel (Set3) wedges: dark text
                text.set_color('#1e1e1e')
            ax.set_title('NPT hours by code (share of NPT)', color='white', fontsize=12)
            fig.tight_layout()
            return FigureCanvas(fig)
        except Exception as exc:
            logger.error("NPT pie chart not drawn: %s", type(exc).__name__, exc_info=True)
            return None

    def _set_productive_card(self):
        if len(self.perf_kpi_cards) < 6:
            return
        kpis = self._last_kpis
        if kpis is None:
            mv = ev.MetricValue(ev.STATE_NOT_ASSESSED, reason="main KPI read unavailable")
        else:
            mv = ev.metric(kpis.get('efficiency'), "", 1,
                           missing_reason="NPT % unknown for this scope")
        self._set_stat_card(self.perf_kpi_cards[5], mv)

    def update_performance_data(self):
        if not self.current_well_id:
            return
        data = self._fetch_cached("perf", self.get_performance_data)
        if data is _STALE:
            return
        if isinstance(data, _LoadError) or not data:
            failed = isinstance(data, _LoadError)
            self.performance_plot.clear()
            self.performance_plot.setTitle(
                data.text() if failed else "No drilling parameters in this scope",
                color="#e74c3c" if failed else "#95a5a6")
            self.performance_table.setRowCount(0)
            state = (ev.MetricValue(ev.STATE_ERROR, reason=data.detail) if failed else
                     ev.MetricValue(ev.STATE_MISSING, reason="no DrillingParameters rows in this scope"))
            for card in self.perf_kpi_cards[:5]:
                self._set_stat_card(card, state)
            self._set_productive_card()
            self.chart_data['performance'] = None
            self.update_dexponent_data([])
            self._update_cost_comparison()
            return

        rop = ev.summarize_rop(d['rop'] for d in data)
        rop_reason = (f"no valid ROP rows ({rop['missing_count']} missing, "
                      f"{rop['invalid_count']} invalid)")

        def _average(key):
            values = [d[key] for d in data if ev.classify_number(d[key])[0] == ev.STATE_VALUE]
            return sum(values) / len(values) if values else None

        reasons = "no row with both bounds recorded"
        cards = [
            ev.metric(rop["average"], "", 1, missing_reason=rop_reason),
            ev.metric(rop["best"], "", 1, missing_reason=rop_reason),
            ev.metric(_average('wob'), "", 1, missing_reason=reasons),
            ev.metric(_average('rpm'), "", 0, missing_reason=reasons),
            ev.metric(_average('torque'), "", 1, missing_reason=reasons),
        ]
        for card, mv in zip(self.perf_kpi_cards, cards):
            self._set_stat_card(card, mv)
        self._set_productive_card()

        self.performance_plot.clear()
        self.performance_plot.setTitle(
            "ROP and WOB, each normalised to its scope maximum (= 100%)", color="#ffffff")
        dated = [d for d in data if d['date'] is not None]
        if len(dated) > 1:
            # x = calendar day since the first record (same-date rows share x);
            # a missing/invalid value is a gap (NaN), never a fabricated 0.
            first = dated[0]['date']
            days = [(d['date'] - first).days + 1 for d in dated]

            def _valid(v):
                return v if ev.classify_number(v)[0] == ev.STATE_VALUE else None

            rops_all = [_valid(d['rop']) for d in dated]
            wob_all = [_valid(d['wob']) for d in dated]
            known_rop = [r for r in rops_all if r is not None]
            known_wob = [w for w in wob_all if w is not None]
            max_rop = max(known_rop) if known_rop and max(known_rop) > 0 else 1
            max_wob = max(known_wob) if known_wob and max(known_wob) > 0 else 1

            def _norm(vals, mx):
                return [(v / mx * 100) if v is not None else float('nan') for v in vals]

            self.performance_plot.plot(
                days, _norm(rops_all, max_rop),
                pen=pg.mkPen('#1abc9c', width=3), name="ROP (% of max)",
                connect="finite",
            )
            self.performance_plot.plot(
                days, _norm(wob_all, max_wob),
                pen=pg.mkPen('#3498db', width=3), name="WOB (% of max)",
                connect="finite",
            )

        def _cell(v, digits):
            # Unknown -> "—"; a real value (including 0.0) -> formatted number.
            return "—" if v is None else f"{v:.{digits}f}"

        self.performance_table.setRowCount(len(data))
        for i, d in enumerate(data):
            self.performance_table.setItem(i, 0, QTableWidgetItem(str(d['date'])))
            self.performance_table.setItem(i, 1, QTableWidgetItem(d['bit_run']))
            self.performance_table.setItem(i, 2, QTableWidgetItem(_cell(d['rop'], 1)))
            self.performance_table.setItem(i, 3, QTableWidgetItem(_cell(d['wob'], 1)))
            self.performance_table.setItem(i, 4, QTableWidgetItem(_cell(d['rpm'], 0)))
            self.performance_table.setItem(i, 5, QTableWidgetItem(_cell(d['torque'], 1)))
            self.performance_table.setItem(i, 6, QTableWidgetItem(_cell(d['pressure'], 0)))

        self.chart_data['performance'] = data
        self.update_dexponent_data(data)
        self._update_cost_comparison()

    def update_dexponent_data(self, data):
        """d-exponent per bit run from stored DrillingParameters.

        ROP stored in m/hr → ft/hr (×3.28084); WOB in klb → lbf (×1000).
        Canonical formula: BitPerformanceEngine.d_exponent (Jorden & Shirley).
        """
        from core.engineering.engines.bit_performance import BitPerformanceEngine
        self.dexponent_plot.clear()
        rows = []
        depths, dvals = [], []
        for d in data:
            # d-exponent needs ALL of ROP, RPM, WOB, bit size known and > 0.
            # A missing input (None) is unknown, not zero — the row simply has
            # no d-exponent rather than a fabricated one.
            rop, wob, rpm, bit = d['rop'], d['wob'], d['rpm'], d['bit_size']
            dval = None
            if None not in (rop, wob, rpm, bit):
                rop_ft = rop * 3.28084
                wob_lbf = wob * 1000.0
                if rop_ft > 0 and rpm > 0 and wob_lbf > 0 and bit > 0:
                    r = BitPerformanceEngine.d_exponent(rop_ft, rpm, wob_lbf, bit)
                    dval = r.value if r.success else None
            rows.append((d, dval))
            if dval is not None and d['depth'] is not None:
                depths.append(d['depth'])
                dvals.append(dval)

        def _dx(v, digits):
            return "--" if v is None else f"{v:.{digits}f}"

        self.dexponent_table.setRowCount(len(rows))
        for i, (d, dval) in enumerate(rows):
            self.dexponent_table.setItem(i, 0, QTableWidgetItem(str(d['date'])))
            self.dexponent_table.setItem(i, 1, QTableWidgetItem(d['bit_run']))
            self.dexponent_table.setItem(i, 2, QTableWidgetItem(_dx(d['depth'], 0)))
            self.dexponent_table.setItem(i, 3, QTableWidgetItem(_dx(d['rop'], 1)))
            self.dexponent_table.setItem(i, 4, QTableWidgetItem(_dx(d['wob'], 1)))
            self.dexponent_table.setItem(i, 5, QTableWidgetItem(_dx(d['rpm'], 0)))
            self.dexponent_table.setItem(i, 6, QTableWidgetItem(
                f"{d['bit_size']:.2f}" if d['bit_size'] else "--"))
            item = QTableWidgetItem("--" if dval is None else f"{dval:.3f}")
            if dval is not None:
                item.setForeground(QColor("#e74c3c" if dval < 1.0 else "#2ecc71"))
            self.dexponent_table.setItem(i, 7, item)

        if len(depths) >= 2:
            self.dexponent_plot.plot(
                depths, dvals, pen=pg.mkPen('#e74c3c', width=3),
                symbol='o', symbolSize=8, symbolBrush='#e74c3c',
                name="d-exponent")
            self.dexponent_plot.setTitle(
                "d-Exponent vs Depth (stored bit runs)", color="#ffffff", size="12pt")
        else:
            self.dexponent_plot.setTitle(
                "Need ≥ 2 bit runs with ROP/WOB/RPM/bit-size to plot the trend",
                color="#95a5a6")

    def _update_cost_comparison(self):
        """SCENARIO cost/ft per stored bit run (Bourgoyne) from user-entered inputs.

        Footage = depth_out − depth_in (m → ft); rotating time = hours_on_bottom.
        The rig rate, trip time and bit cost are assumptions typed by the user
        in one currency of their choice; no currency is invented and nothing
        here is recorded cost.
        """
        from core.engineering.engines.bit_performance import BitPerformanceEngine
        if not self.current_well_id:
            # Drop the previous well's comparison instead of leaving it on screen.
            self.cost_table.setRowCount(1)
            self.cost_table.setItem(0, 0, QTableWidgetItem("NOT ASSESSED: select a well"))
            return
        data = self._fetch_cached("perf", self.get_performance_data)
        if data is _STALE:
            return
        if isinstance(data, _LoadError):
            self.cost_table.setRowCount(1)
            self.cost_table.setItem(0, 0, QTableWidgetItem(data.text()))
            return
        rig_rate = self.cost_rig_rate.value()
        trip_h = self.cost_trip_h.value()
        bit_cost = self.cost_bit_cost.value()

        results = []
        for d in data:
            # Footage/rotating-time need real depths and hours. A missing input
            # (None) means the run cannot be costed — it is skipped, never
            # costed against a fabricated 0.
            if d['depth'] is None or d['depth_in'] is None or d['hours_on_bottom'] is None:
                continue
            footage_ft = (d['depth'] - d['depth_in']) * 3.28084
            if footage_ft <= 0:
                continue
            r = BitPerformanceEngine.cost_per_foot(
                rig_cost_per_day=rig_rate,
                trip_hours=trip_h,
                bit_cost=bit_cost,
                footage=footage_ft,
                rotating_hours=d['hours_on_bottom'],
            )
            if r.success:
                results.append((d['bit_run'], footage_ft, d['hours_on_bottom'],
                                r.values['total_cost'], r.values['cost_per_ft']))

        if not results:
            self.cost_table.setRowCount(1)
            self.cost_table.setItem(0, 0, QTableWidgetItem(
                "NOT ASSESSED: no bit run with depth in/out and on-bottom hours"))
            return
        self.cost_table.setRowCount(len(results))
        best = min((x[4] for x in results), default=None)
        for i, (name, footage, hrs, total, cft) in enumerate(results):
            self.cost_table.setItem(i, 0, QTableWidgetItem(name))
            self.cost_table.setItem(i, 1, QTableWidgetItem(f"{footage / 3.28084:.0f}"))
            self.cost_table.setItem(i, 2, QTableWidgetItem(f"{hrs:.1f}"))
            self.cost_table.setItem(i, 3, QTableWidgetItem(f"{total:,.0f}"))
            ci = QTableWidgetItem(f"{cft:.2f}")
            ci.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if best is not None and abs(cft - best) < 1e-9:
                ci.setForeground(QColor("#2ecc71"))
                ci.setToolTip("Cheapest run under the entered scenario")
            self.cost_table.setItem(i, 4, ci)
            self.cost_table.setItem(i, 5, QTableWidgetItem(
                "✅ best" if best is not None and abs(cft - best) < 1e-9 else ""))

    def _recent_reports(self, session):
        rows = []
        for r in self._scope_reports_query(session).order_by(desc(DailyReport.report_date)).limit(10).all():
            act = session.query(TimeLog24H.main_code).filter_by(report_id=r.id)\
                         .order_by(desc(TimeLog24H.duration)).first()
            rows.append((r.report_date, r.rig_day, r.depth_2400,
                         act[0] if act and act[0] else "—"))
        return rows

    def update_daily_data(self):
        if not self.current_well_id:
            return
        today = self._fetch_cached("today", self.get_today_data)
        if today is _STALE:
            return
        if isinstance(today, _LoadError):
            for indicator in self.today_indicators.values():
                indicator.setText(ev.STATE_TEXT[ev.STATE_ERROR])
                indicator.setToolTip(today.text())
        elif today:
            # Unknown values render as "—" (via fmt_num default=None), never 0.
            self.today_indicators['depth_meter'].setText(fmt_num(today['depth'], 1, default=None))
            self.today_indicators['rop_meter'].setText(fmt_num(today['rop'], 1, default=None))
            self.today_indicators['hours'].setText(fmt_num(today['hours'], 1, default=None))
            self.today_indicators['days'].setText(
                "—" if today['rig_day'] is None else str(today['rig_day']))
            self.today_indicators['npt_hours'].setText(fmt_num(today['npt_hours'], 1, default=None))
            self.today_indicators['mw_in_out'].setText(
                f"{fmt_num(today['mw_in'], 1, default=None)}/"
                f"{fmt_num(today['mw_out'], 1, default=None)}")
            self.today_indicators['mw_header_pcf'].setText(fmt_num(today['mw_header_pcf'], 1, default=None))
            self.today_indicators['mw_sample_pcf'].setText(fmt_num(today['mw_sample_pcf'], 1, default=None))
        else:
            for indicator in self.today_indicators.values():
                indicator.setText("—")
        recent = self._fetch_cached("recent", self._recent_reports)
        if recent is _STALE:
            return
        if isinstance(recent, _LoadError):
            self.recent_reports_table.setRowCount(1)
            self.recent_reports_table.setItem(0, 0, QTableWidgetItem(recent.text()))
            return
        self.recent_reports_table.setRowCount(len(recent))
        for i, (report_date, rig_day, depth, main_act) in enumerate(recent):
            # Presentation truth: an unknown rig-day/depth renders "—", a real
            # reported 0 renders "0"/"0.0". Never collapse None into a fake 0.
            self.recent_reports_table.setItem(i, 0, QTableWidgetItem(str(report_date)))
            self.recent_reports_table.setItem(i, 1, QTableWidgetItem(_fmt_rig_day(rig_day)))
            self.recent_reports_table.setItem(i, 2, QTableWidgetItem(_fmt_recent_depth(depth)))
            self.recent_reports_table.setItem(i, 3, QTableWidgetItem(main_act))

    def _reset_analytics_chart(self):
        """Neutral analytics chart: no items, title, unit labels or custom ticks.

        Used before every analysis and on deselect: plot.clear() removes the
        items only, so a previous analysis' title/labels/ticks would otherwise
        keep describing a chart (or a well) they no longer belong to.
        """
        self.analytics_plot.clear()
        self.analytics_plot.setTitle(None)
        self.analytics_plot.setLabel("left", "Value")
        self.analytics_plot.setLabel("bottom", "Parameter")
        self.analytics_plot.getPlotItem().getAxis("bottom").setTicks(None)

    def run_advanced_analysis(self):
        if not self.current_well_id:
            QMessageBox.warning(self, "No Data", "Please select a well first")
            return
        kind = self.analytics_type.currentText()
        handler = {
            "ROP Prediction": self.analyze_rop_prediction,
            "NPT Forecasting": self.analyze_npt_forecasting,
            "Cost Analysis": self.analyze_cost,
            "Risk Assessment": self.analyze_risk,
        }.get(kind)
        if handler is None:
            return
        self._reset_analytics_chart()
        session = self.db.create_session()
        try:
            handler(session)
        except Exception as exc:
            # An error is reported as an error — never an empty or stale result.
            logger.error("Advanced analysis '%s' failed: %s", kind, type(exc).__name__, exc_info=True)
            self.analytics_plot.clear()
            self.analytics_plot.setTitle(f"{kind}: ERROR - no result (see below)")
            self.results_text.setText(
                f"{kind}: read/processing error ({type(exc).__name__}). No result is shown; "
                "use Refresh Now to retry.")
        finally:
            session.close()

    def _scope_text(self):
        return _scope_text(self)

    def _plot_projection(self, result, actual, colors, names):
        _plot_projection(self.analytics_plot, result, actual, colors, names)

    def analyze_rop_prediction(self, session):
        """Transparent ROP projection: one valid observation per date, or NOT ASSESSED."""
        if not self.current_well_id:
            self.results_text.setText("No well selected")
            return
        params = self._scope_params_query(session)\
            .order_by(DrillingParameters.report_date, DrillingParameters.id).all()
        report_ids = {p.report_id for p in params if p.report_id is not None}
        bores = dict(session.query(DailyReport.id, DailyReport.wellbore_id)
                     .filter(DailyReport.id.in_(report_ids)).all()) if report_ids else {}
        rows = [{"source_id": p.id, "date": p.report_date, "rop": p.avg_rop,
                 "hours": p.hours_on_bottom, "report_id": p.report_id,
                 "wellbore_id": bores.get(p.report_id)} for p in params]
        series, excluded = ev.rop_daily_series(rows)
        source = "DrillingParameters.avg_rop (canonical)"
        if not series:
            # Report-header ROP is used ONLY when no valid parameter ROP exists;
            # each value is owned by its report (no well+date guessing).
            reports = self._scope_reports_query(session).order_by(DailyReport.report_date).all()
            fallback = [{"source_id": r.id, "date": r.report_date, "rop": r.rop_meter,
                         "report_id": r.id, "wellbore_id": r.wellbore_id} for r in reports]
            fb_series, fb_excluded = ev.rop_daily_series(fallback, source_name="DailyReport.rop_meter")
            if fb_series:
                series, excluded = fb_series, excluded + fb_excluded
                source = "DailyReport.rop_meter (fallback: no valid DrillingParameters ROP)"
        result = ev.linear_projection([(o.date, o.value) for o in series], horizon=5)
        _plot_projection(self.analytics_plot, result, [o.value for o in series], ('#3498db', '#e74c3c', '#2ecc71'),
                              ("Actual ROP", "Projection"), unit="ROP (m/hr)")
        if result["status"] != "assessed":
            self.analytics_plot.clear()
        text = ev.describe_projection(result, "m/hr", "⚡ ROP PROJECTION")
        text += f"\nScope: {_scope_text(self)}; source: {source}"
        text += "\n" + _exclusion_text(excluded)
        text += _trend_words(result, "m/hr", "ROP")
        self.results_text.setText(text)

    def analyze_npt_forecasting(self, session):
        """NPT projection over coverage-valid report dates (zero-NPT days included)."""
        well_id = self.current_well_id
        if not well_id:
            self.results_text.setText("No well selected")
            return
        scope = ev.AnalysisScope(well_id=well_id, wellbore_id=getattr(self, "current_wellbore_id", None))
        days = ev.npt_daily_series(*ev.load_npt_inputs(session, scope))
        valid = [d for d in days if d.state == ev.STATE_VALUE]
        result = ev.linear_projection([(d.date, d.npt_hours) for d in valid], horizon=7)
        _plot_projection(self.analytics_plot, result, [d.npt_hours for d in valid], ('#e74c3c', '#f39c12', '#2ecc71'),
                              ("NPT per covered day", "Projection"), unit="NPT (hours per covered day)")
        text = ev.describe_projection(result, "hours", "⏱️ NPT PROJECTION")
        text += (f"\nScope: {_scope_text(self)}; source: TimeLog24H via DailyReport "
                 "(operational_time.summarize_time_logs per report date)")
        zero_days = sum(1 for d in valid if d.npt_hours == 0)
        text += (f"\nCoverage-valid report dates: {len(valid)} of {len(days)} "
                 f"({zero_days} with a valid zero: full coverage and no NPT)")
        text += "\n" + _exclusion_text([d.observation() for d in days if d.state != ev.STATE_VALUE])
        text += _trend_words(result, "hours", "NPT")
        totals = {}
        for d in valid:
            for code, hours in d.categories.items():
                totals[code] = totals.get(code, 0.0) + hours
        total = sum(totals.values())
        if totals and total > 0:
            text += "\n\nTop NPT codes (coverage-valid dates):"
            for code, hours in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:5]:
                text += f"\n  • {code}: {hours:.1f} h ({hours / total * 100:.1f}% of NPT)"
        self.results_text.setText(text)

    def analyze_cost(self, session):
        """Recorded cost (CostRecord) for the whole well via the canonical services."""
        well_id = self.current_well_id
        if not well_id:
            self.results_text.setText("No well selected")
            return
        # AUTHORITATIVE cost comes from persisted CostRecord via the canonical
        # operations-intelligence service — the same numbers the report engine
        # and W16 show. Cost is a WHOLE-WELL fact (CostRecord is well-scoped),
        # so its NPT inputs are whole-well too and nothing is attributed to a
        # selected wellbore. Unknown stays unknown, never a fabricated 0.
        from core.operations_intelligence import OperationsIntelligenceService
        from core.cost_semantics import allocate_npt_cost
        total_days = session.query(DailyReport).filter_by(well_id=well_id).count()
        kpis = OperationsIntelligenceService(self.db).analyze_well(well_id).get("kpis", {})
        if kpis.get("error"):
            raise RuntimeError(f"canonical cost read failed: {kpis['error']}")
        total_npt_hours = kpis.get("npt_hours")
        well_total_hours = kpis.get("total_hours")
        total_cost = kpis.get("total_cost")
        planned = kpis.get("total_planned_cost")
        cpm = kpis.get("cost_per_meter")
        currency = kpis.get("cost_currency")
        status = kpis.get("cost_currency_status")
        npt_note = ""
        try:
            npt_cost = allocate_npt_cost(total_cost, total_npt_hours, well_total_hours or None)
        except EngineeringError as exc:
            npt_cost, npt_note = None, f"NPT cost NOT ASSESSED: {exc}"
        productive_cost = (total_cost - npt_cost
                           if total_cost is not None and npt_cost is not None else None)
        variance = canonical_variance(planned, total_cost)

        not_summed = {"multi-currency": "not summed: several currencies",
                      "unknown-currency": "not summed: currency missing on some lines"}.get(status)

        def money(v):
            # A mixed/unknown-currency total is not "currency unknown": the
            # lines have currencies, they are just never added together.
            if currency is None and not_summed:
                return f"— ({not_summed})"
            return format_money(v, currency)

        # Chart only known values (unknowns are skipped, never plotted as 0).
        self.analytics_plot.clear()
        if total_cost is not None:
            labels = ["Actual"]
            values = [total_cost / 1000]
            for label, value in (("Estimate", planned), ("Productive", productive_cost), ("NPT", npt_cost)):
                if value is not None:
                    labels.append(label)
                    values.append(value / 1000)
            x = list(range(1, len(values) + 1))
            colors = ['#3498db', '#9b59b6', '#2ecc71', '#e74c3c'][:len(values)]
            self.analytics_plot.addItem(pg.BarGraphItem(x=x, height=values, width=0.6, brushes=colors))
            self.analytics_plot.setLabel("bottom", "Cost line")
            self.analytics_plot.getPlotItem().getAxis("bottom").setTicks([list(zip(x, labels))])
            self.analytics_plot.setLabel("left", f"Cost (thousands {currency})")
            self.analytics_plot.setTitle(f"Recorded cost, whole well ({currency})")
        else:
            why = {"multi-currency": "several currencies are never summed (no FX conversion)",
                   "unknown-currency": "currency missing on some lines",
                   "no-records": "no cost recorded for this well"}.get(status, "no total available")
            self.analytics_plot.setTitle(f"Cost: NOT CHARTED - {why}")

        status_text = {
            "single-currency": f"single currency ({currency})",
            "multi-currency": "several currencies - totals NOT aggregated (no FX conversion)",
            "unknown-currency": "currency missing on some lines - totals NOT aggregated",
            "no-records": "no cost recorded for this well",
        }.get(status, str(status))
        bore = getattr(self, "current_wellbore_id", None)
        report = f"💰 COST ANALYSIS (recorded CostRecord lines)\n{'='*40}\n"
        report += "Scope: Whole Well (cost is recorded per well)"
        report += (f"; the selected wellbore #{bore} is NOT attributed a share\n" if bore else "\n")
        report += f"Currency: {status_text}\n"
        report += f"Recorded reports: {total_days}\n"
        report += f"Recorded time (days): {fmt_num(well_total_hours / 24 if well_total_hours is not None else None, 1, default=None)}\n"
        report += (f"NPT time (days): {fmt_num(total_npt_hours / 24 if total_npt_hours is not None else None, 1, default=None)}"
                   f" ({fmt_num(kpis.get('npt_percent'), 1, default=None)}% of recorded time)\n\n")
        report += f"  Actual (recorded) total:  {money(total_cost)}\n"
        report += f"  Estimate (planned) total: {money(planned)}\n"
        report += f"  Variance (planned - actual; + = under estimate): {money(variance)}\n"
        report += f"  NPT cost (actual x NPT share of recorded time): {money(npt_cost)}\n"
        report += f"  Productive cost (actual - NPT cost): {money(productive_cost)}\n"
        report += f"  Cost per metre (actual / current well depth): {money(cpm)}/m\n"
        groups = kpis.get("cost_groups") or []
        if not_summed and groups:
            report += "\n  Per currency (each group in its own currency, never converted or added):\n"
            for g in groups:
                cur = g.get("currency")
                label = f"{cur or 'no currency'} / {g.get('category') or 'uncategorised'}"
                report += (f"    {label}: actual {format_money(g.get('actual'), cur)}; "
                           f"estimate {format_money(g.get('planned'), cur)}\n")
        if npt_note:
            report += f"\n{npt_note}\n"
        if total_cost is None:
            report += ("\nActual total NOT ASSESSED: no records, a missing amount, or mixed/unknown "
                       "currencies (see the cost lines in W16).\n")
        self.results_text.setText(report)

    @staticmethod
    def _risk_scores(npt_pct, days_without_lti, has_safety_report):
        """Rule-based per-category scores (NOT a measurement, NOT a probability).

        Delegates to the canonical rule table in ``core.analysis_evidence``;
        an unknown input yields ``None`` (NOT ASSESSED), never a fabricated score.
        """
        return ev.risk_scores(npt_pct, days_without_lti, has_safety_report)

    def analyze_risk(self, session):
        """Rule-based whole-well risk screening with its evidence and rules."""
        well_id = self.current_well_id
        if not well_id:
            self.results_text.setText("No well selected")
            return
        from core.operations_intelligence import OperationsIntelligenceService
        kpis = OperationsIntelligenceService(self.db).analyze_well(well_id).get("kpis", {})
        if kpis.get("error"):
            raise RuntimeError(f"canonical risk inputs failed: {kpis['error']}")
        npt_pct = kpis.get("npt_percent")
        # Same ambiguity-aware observation as Intelligence, not .first().
        days_no_lti = (kpis.get("safety_kpi") or {}).get("days_without_lti")
        days = ev.npt_daily_series(*ev.load_npt_inputs(session, ev.AnalysisScope(well_id=well_id)))
        coverage = ev.npt_coverage_summary(days)
        assessment = ev.risk_assessment(npt_pct, coverage, days_no_lti)
        first, last = session.query(func.min(DailyReport.report_date),
                                    func.max(DailyReport.report_date))\
            .filter(DailyReport.well_id == well_id).one()

        charted = [c for c in assessment["criteria"] if c["assessed"] and not c["proxy"]]
        self.analytics_plot.clear()
        if charted:
            scores = [c["score"] for c in charted]
            colors = ['#e74c3c' if s >= 7 else '#f39c12' if s >= 4 else '#2ecc71' for s in scores]
            self.analytics_plot.addItem(pg.BarGraphItem(
                x=list(range(len(scores))), height=scores, width=0.6, brushes=colors))
            self.analytics_plot.addItem(pg.InfiniteLine(
                pos=7, angle=0, pen=pg.mkPen('#e74c3c', width=2, style=Qt.DashLine)))
            self.analytics_plot.setLabel("bottom", "Criterion (only assessed, non-proxy criteria are charted)")
            self.analytics_plot.getPlotItem().getAxis("bottom").setTicks(
                [[(i, c["name"]) for i, c in enumerate(charted)]])
            self.analytics_plot.setLabel("left", "Rule score (0-10)")
            self.analytics_plot.setTitle("Rule-based risk screening per criterion (not a probability)")
        else:
            self.analytics_plot.setTitle("Risk: NOT ASSESSED - no criterion could be scored (see below)")

        overall = assessment["overall"]
        report = f"⚠️ RISK SCREENING (rule-based; NOT a probability or a measurement)\n{'='*40}\n"
        report += "Scope: Whole Well (NPT and safety are assessed at well level)"
        bore = getattr(self, "current_wellbore_id", None)
        report += (f"; not narrowed to wellbore #{bore}\n" if bore else "\n")
        report += f"Period: {first or '—'} to {last or '—'}\n"
        if overall["assessed"]:
            report += f"Overall level: {overall['level']} ({overall['reason']})\n"
        else:
            report += f"Overall level: NOT ASSESSED - {overall['reason']}\n"
        report += f"Level rule: {assessment['level_rule']}\n\nCriteria:\n"
        for c in assessment["criteria"]:
            tag = " [proxy, not counted]" if c["proxy"] else (" [required]" if c["required"] else "")
            if c["assessed"]:
                report += f"  {c['name']}{tag}: {c['score']}/10 {c['level']}\n"
            else:
                report += f"  {c['name']}{tag}: NOT ASSESSED - {c['reason']}\n"
            report += f"      rule: {c['rule']}\n"
        report += "\nSources:\n"
        report += (f"  NPT %: TimeLog24H via DailyReport (summarize_time_logs) = "
                   f"{fmt_num(npt_pct, 1, default=None)}%; time coverage "
                   f"{coverage['covered_days']} of {coverage['days']} report dates complete\n")
        report += ("  Safety: SafetyReport (safety_semantics.safety_kpis), days without LTI = "
                   + (f"{days_no_lti}\n" if days_no_lti is not None
                      else "UNKNOWN (missing or ambiguous safety observation)\n"))
        self.results_text.setText(report)

    def update_stat_card_value(self, card, new_val):
        """Set a stat card's text; the unit is the card's own (never parsed back)."""
        unit = getattr(card, "unit", "")
        card.value_label.setText(f"<b>{new_val}</b> {unit}".rstrip())

    def update_perf_kpi_card(self, idx, new_val):
        if idx < len(self.perf_kpi_cards):
            self.update_stat_card_value(self.perf_kpi_cards[idx], new_val)

    def toggle_auto_update(self, state):
        if state in (Qt.Checked, Qt.Checked.value, 2):
            self.update_timer.start(self._auto_update_interval_ms())
            self._set_status("🟢 Monitoring Active", "ok")
            self.update_all_data()
        else:
            self.update_timer.stop()
            self._set_status("🟡 Monitoring Paused", "warn")

    def load_milestones_data(self):
        """Milestones (FACT vs PLAN) per Section — scope-aware, no fabrication.

        FACT = real time logged against each section (TimeLog24H). PLAN = the
        REAL stored plan (Section.planned_days), the same field the section
        editor persists and W10's milestones reader consumes — never a
        display-fabricated duration derived from depth/50 or a flat 5 days.

        Milestones are SECTION facts: a selected wellbore narrows to the
        sections it owns (Section.wellbore_id), unknown-bore sections are
        excluded from a bore view; whole-well shows every section.
        """
        if not self.current_well_id:
            return
        
        session = self.db.create_session()
        try:
            from core.database import Section
            from core.actual_vs_plan import section_actual_days

            self._update_milestones_scope_label()

            # Sections in the active scope. Bore selected -> only that bore's
            # sections (via Section.wellbore_id); otherwise the whole well.
            sec_q = session.query(Section).filter(
                Section.well_id == self.current_well_id)
            if self.current_wellbore_id:
                sec_q = sec_q.filter(Section.wellbore_id == self.current_wellbore_id)
            sections = sec_q.order_by(Section.depth_from).all()
            
            if not sections:
                # No sections in scope: fall back to report-derived milestones
                # (whole-well only — report grouping is not section-scoped).
                if not self.current_wellbore_id:
                    self._load_milestones_from_reports(session)
                else:
                    self._draw_milestones_chart([], [], [])
                return
            
            fact_data = []
            plan_data = []
            section_names = []
            
            for section in sections:
                section_names.append(section.name)
                
                fact_data.append(section_actual_days(session, section.id))
                plan_data.append(section.planned_days)

            # رسم نمودار Milestones
            self._draw_milestones_chart(section_names, fact_data, plan_data)
            
        except Exception as e:
            self._draw_milestones_chart([], [], [])
            if getattr(self, "milestones_scope_label", None) is not None:
                self.milestones_scope_label.setText("FAILED to load milestones")
            logger.error(f"Error loading milestones data: {e}")
        finally:
            session.close()

    def _update_milestones_scope_label(self):
        """Reflect the milestones scope (bore-narrowed vs whole-well)."""
        if not hasattr(self, "milestones_scope_label"):
            return
        if self.current_wellbore_id:
            name = self.current_wellbore_name or f"#{self.current_wellbore_id}"
            self.milestones_scope_label.setText(f"Scope: Wellbore — {name}")
        else:
            self.milestones_scope_label.setText("Scope: Whole Well")

    def _load_milestones_from_reports(self, session):
        """Depth-band elapsed calendar days; never report count or rig-time.

        This fallback has no stored plan. Multiple/unknown bore populations
        cannot establish one depth progression and remain NOT ASSESSED.
        """
        try:
            from core.database import DailyReport
            
            reports = session.query(
                DailyReport.report_date,
                DailyReport.depth_2400,
                DailyReport.wellbore_id
            ).filter(
                DailyReport.well_id == self.current_well_id
            ).order_by(DailyReport.report_date).all()
            
            if not reports or len({r.wellbore_id for r in reports}) != 1:
                self._draw_milestones_chart([], [], [])
                return
            
            # Milestone bands every ~500 m or ~30 days.
            milestones = []
            fact_times = []
            last_depth = None
            band_start = None
            for r in reports:
                depth = r.depth_2400
                if depth is None:
                    continue
                if last_depth is None:
                    last_depth, band_start = depth, r.report_date
                    continue
                elapsed = (r.report_date - band_start).days
                if depth - last_depth >= 500 or elapsed >= 30:
                    milestones.append(f"{last_depth:.0f}-{depth:.0f}m (calendar days)")
                    fact_times.append(elapsed)
                    last_depth, band_start = depth, r.report_date

            # PLAN unknown in this path -> empty plan series (no fabrication).
            self._draw_milestones_chart(milestones, fact_times, [])
                
        except Exception as e:
            self._draw_milestones_chart([], [], [])
            if getattr(self, "milestones_scope_label", None) is not None:
                self.milestones_scope_label.setText("FAILED to load milestones")
            logger.error(f"Error loading milestones from reports: {e}")

    def _draw_milestones_chart(self, sections, fact_days, plan_days):
        if not sections:
            if getattr(self, "milestones_widget", None) is not None:
                safe_replace_chart(self.milestones_widget, QLabel("Milestones: NOT ASSESSED (no sections)"))
            return
        fact_days = [v if v is not None else float("nan") for v in fact_days]
        plan_days = [v if v is not None else float("nan") for v in plan_days]
        
        try:
            fig = Figure(figsize=(10, 5), facecolor='#1e1e1e')
            ax = fig.add_subplot(111)
            ax.set_facecolor('#1e1e1e')
            
            x = np.arange(len(sections))
            # When PLAN is unknown (empty series) draw FACT full-width and omit
            # the PLAN bars entirely rather than plotting a fabricated plan.
            has_plan = bool(plan_days) and len(plan_days) == len(sections)
            width = 0.35 if has_plan else 0.6

            fact_x = (x - width / 2) if has_plan else x
            bars1 = ax.bar(fact_x, fact_days, width, label='FACT', color='#3498db', edgecolor='white', linewidth=0.5)
            bars2 = ax.bar(x + width/2, plan_days, width, label='PLAN', color='#e74c3c', edgecolor='white', linewidth=0.5) if has_plan else []
            
            ax.set_xlabel('Section', color='white', fontsize=11)
            ax.set_ylabel('Days', color='white', fontsize=11)
            ax.set_title('Milestones - FACT vs PLAN (unknown values omitted)', color='white', fontsize=14, fontweight='bold')
            ax.set_xticks(x)
            ax.set_xticklabels(sections, rotation=45, ha='right', color='white')
            ax.tick_params(axis='y', colors='white')
            ax.legend(loc='upper right', facecolor='#2c3e50', edgecolor='white', labelcolor='white')
            ax.grid(True, alpha=0.3, color='white')
            
            # افزودن مقادیر روی میله‌ها
            for bar in bars1:
                height = bar.get_height()
                if not np.isfinite(height):
                    continue
                ax.annotate(f'{height:.1f}',
                           xy=(bar.get_x() + bar.get_width()/2, height),
                           xytext=(0, 3), textcoords="offset points",
                           ha='center', va='bottom', color='white', fontsize=8)
            
            for bar in bars2:
                height = bar.get_height()
                if not np.isfinite(height):
                    continue
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
        except Exception as e:
            logger.error(f"Error drawing milestones chart: {e}")
        
    # ---------- SelectionManager integration ----------
    def on_well_changed(self, well_id, well_data):
        # A new well clears any prior bore scope (a bore belongs to the old
        # well). Re-read the manager in case a bore was set in the same cascade.
        self.current_wellbore_id = getattr(
            self.sel_manager, "current_wellbore_id", None)
        self.current_wellbore_name = None
        self.current_report_id = getattr(self.sel_manager, "current_report_id", None)
        self.set_current_well(well_id, (well_data or {}).get('name', str(well_id)))

    def on_selection_cleared(self):
        """SelectionManager.clear(): nothing of the previous well may stay on screen."""
        self._show_no_selection()

    def on_wellbore_changed(self, wellbore_id, wellbore_data):
        """Re-scope analytics to the selected wellbore (bore) and refresh.

        ``wellbore_id`` None -> whole-well aggregate. All caches are scope-keyed,
        so switching bores can never show another bore's cached numbers.
        Unknown-bore records are excluded from a bore-scoped view (never
        attributed to the selected bore).
        """
        # wellbore_changed is Signal(int, ...): select_wellbore(None) arrives as 0.
        self.current_wellbore_id = wellbore_id or None
        self.current_report_id = getattr(self.sel_manager, "current_report_id", None)
        self.current_section_id = getattr(self.sel_manager, "current_section_id", None)
        self.current_wellbore_name = (
            (wellbore_data or {}).get("name") if wellbore_data else None)
        self._generation += 1
        self.clear_cache()
        self.update_scope_indicator()
        if self.current_well_id:
            self.update_data_quality()
            self.update_plan_variance()
            self.update_intelligence()
            self.update_all_data()

    def update_scope_indicator(self):
        """Make the active analytical scope explicit in the UI.

        The user must always know whether a number describes the whole well
        (an explicit aggregate that may span an original hole and sidetracks) or
        a single bore. Silent scope is a truth defect.
        """
        label = getattr(self, "scope_label", None)
        if label is None:
            return
        if self.current_wellbore_id:
            name = self.current_wellbore_name or f"#{self.current_wellbore_id}"
            label.setText(f"🎯 Scope: Wellbore — {name}")
            label.setToolTip(
                "Analytics are scoped to this wellbore only. "
                "Records with an unknown bore are excluded.")
            label.setStyleSheet(
                "font-weight: bold; padding: 5px; color: #bb8fce;")
        else:
            has_bores = False
            try:
                if self.current_well_id and self.db is not None:
                    has_bores = bool(
                        self.db.get_wellbores_by_well(self.current_well_id))
            except Exception as exc:
                logger.warning("Wellbore lookup failed; treating the well as single-bore: %s", type(exc).__name__)
                has_bores = False
            if has_bores:
                label.setText("🌐 Scope: Whole-Well Aggregate")
                label.setToolTip(
                    "This well has multiple wellbores. Figures aggregate every "
                    "bore (original + sidetracks) plus any unknown-bore records.")
                # Readable on the dark header (#2c3e50 text was invisible there).
                label.setStyleSheet(
                    "font-weight: bold; padding: 5px; color: #f5b041;")
            else:
                label.setText("🌐 Scope: Whole Well")
                label.setToolTip("Analytics for the whole well.")
                label.setStyleSheet(
                    "font-weight: bold; padding: 5px; color: #7f8c8d;")

    def on_section_changed(self, section_id, section_data):
        self.current_section_id = section_id
        self.current_report_id = None
        self._generation += 1
        self.clear_cache()
        self.update_data_quality()
        self.update_daily_data()
        if PYQTGRAPH_AVAILABLE:
            self.refresh_evidence()  # a section-level evidence view must follow

    def on_report_changed(self, report_id, report_data):
        self.current_report_id = report_id
        self._generation += 1
        self.clear_cache()
        self.update_data_quality()
        self.update_plan_variance()
        self.update_intelligence()
        self.update_all_data()

    def update_plan_variance(self):
        if not self.current_well_id:
            self.plan_variance_label.setText("Plan vs Actual: —")
            return
        try:
            metrics = self.db.get_actual_vs_plan(self.current_well_id)
            depth = metrics["depth"]
            hours = metrics["hours"]
            def _metric_text(item, unit):
                if item.get("pct") is None:
                    return "n/a"
                return f"{item['actual']:.1f}/{item['planned']:.1f} {unit} ({item['pct']:+.1f}%)"

            # Plan variance is computed at WELL level (get_actual_vs_plan is
            # keyed by well_id, aggregating every bore), so the label says so
            # explicitly even when a bore is selected — it is NOT narrowed to the
            # selected bore (§13, no hidden mixed scope).
            self.plan_variance_label.setText(
                "Plan vs Actual [Whole-Well] | Depth " + _metric_text(depth, "m") +
                " | Hours " + _metric_text(hours, "h")
            )
            comparable = depth.get("pct") is not None and hours.get("pct") is not None
            color = ("#27ae60" if comparable and abs(depth["pct"]) <= 10 and abs(hours["pct"]) <= 10
                     else "#f39c12" if comparable else "#7f8c8d")
            self.plan_variance_label.setStyleSheet(f"font-weight: bold; padding: 5px; color: {color};")
        except Exception as exc:
            logger.error("Plan variance update failed: %s", exc, exc_info=True)
            self.plan_variance_label.setText("Plan vs Actual: unavailable")

    def update_intelligence(self):
        if not self.current_well_id:
            self.intelligence_label.setText("Operations Intelligence: —")
            return
        try:
            # Operations Intelligence is a WHOLE-WELL analysis (analyze_well
            # aggregates every bore); the label states the scope explicitly so
            # it is never mistaken for the selected bore (§13).
            result = self.intelligence_service.analyze_well(self.current_well_id)
            insights = result.get("insights", [])
            if insights:
                text = " | ".join(f"{item['severity'].upper()}: {item['message']}" for item in insights[:2])
                self.intelligence_label.setText("Operations Intelligence [Whole-Well]: " + text)
                self.intelligence_label.setStyleSheet("font-weight: bold; padding: 5px; color: #e67e22;")
            else:
                self.intelligence_label.setText("Operations Intelligence [Whole-Well]: No critical pattern detected")
                self.intelligence_label.setStyleSheet("font-weight: bold; padding: 5px; color: #27ae60;")
        except Exception as exc:
            logger.error("Operations intelligence failed: %s", exc, exc_info=True)
            self.intelligence_label.setText("Operations Intelligence: unavailable")

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
            self.quality_label.setToolTip("\n".join(f"{m['name']}: {m['value']}% — {m['detail']}" for m in summary["metrics"]))
        except Exception as exc:
            logger.error("Data quality update failed: %s", exc, exc_info=True)
            self.quality_label.setText("Data Quality: unavailable")

    def set_current_well(self, well_id, well_name):
        # SelectionManager.well_changed is Signal(int, object): select_well(None)
        # arrives here as 0. Any falsy id is "no well", never well "0".
        if not well_id:
            self._show_no_selection()
            return
        self._generation += 1
        self.current_well_id = well_id
        self.current_well_name = well_name
        self.clear_cache()
        self._data_rev = None
        self._last_kpis = None
        self._evidence_rows = []
        if not PYQTGRAPH_AVAILABLE:
            return
        self.well_label.setText(f"🌍 Well: {well_name}")
        self._set_status("🟡 Loading…", "warn")
        self.help_label.setVisible(False)
        self.analysis_tabs.setVisible(True)
        self.bottom_widget.setVisible(True)
        # Start monitoring without the checkbox handler running a second,
        # redundant full update of the same well.
        if not self.auto_update_check.isChecked():
            self.auto_update_check.blockSignals(True)
            self.auto_update_check.setChecked(True)
            self.auto_update_check.blockSignals(False)
        self.update_timer.start(self._auto_update_interval_ms())
        self.update_scope_indicator()
        self.update_data_quality()
        self.update_plan_variance()
        self.update_intelligence()
        self.update_all_data()

    def _auto_update_interval_ms(self):
        intervals = {0: 5000, 1: 10000, 2: 30000, 3: 60000, 4: 300000}
        return intervals.get(self.auto_update_interval.currentIndex(), 10000)

    def _show_no_selection(self):
        """Clear every value, chart and table to an explicit no-selection state."""
        self._generation += 1
        self.current_well_id = None
        self.current_well_name = None
        self.current_wellbore_id = None
        self.current_wellbore_name = None
        self.current_section_id = None
        self.current_report_id = None
        self.clear_cache()
        self._data_rev = None
        self._last_kpis = None
        self._evidence_rows = []
        self._evidence_meta = None
        self.update_timer.stop()
        for name, data in list(self.chart_data.items()):
            self.chart_data[name] = None
        self.quality_label.setText("Data Quality: —")
        self.plan_variance_label.setText("Plan vs Actual: —")
        self.intelligence_label.setText("Operations Intelligence: —")
        if not PYQTGRAPH_AVAILABLE:
            return
        self.auto_update_check.blockSignals(True)
        self.auto_update_check.setChecked(False)
        self.auto_update_check.blockSignals(False)
        self.well_label.setText("🌍 Well: Not Selected")
        self._set_status("🔴 No well selected", "error")
        self.scope_label.setText("🌐 Scope: —")
        self.last_update_label.setText("Last update: --:--:--")
        none = ev.MetricValue(ev.STATE_NO_SELECTION)
        for card in self.kpi_cards:
            self._set_kpi_card(card, none, "No well selected")
        for card in (*self.perf_kpi_cards, self.npt_total_card, self.npt_percent_card,
                     self.npt_daily_card):
            self._set_stat_card(card, none)
        self._set_category_card("—", "")
        self.npt_coverage_label.setText("Time coverage: —")
        for plot in (self.time_depth_plot, self.daily_gain_plot, self.performance_plot,
                     self.dexponent_plot, self.analytics_plot, self.evidence_plot):
            plot.clear()
        for plot in (self.time_depth_plot, self.performance_plot, self.evidence_plot):
            plot.setTitle("No well selected", color="#95a5a6")
        self._reset_analytics_chart()
        self._replace_npt_pie(None, "No well selected")
        for table in (self.time_depth_table, self.npt_table, self.performance_table,
                      self.dexponent_table, self.recent_reports_table, self.cost_table,
                      self.evidence_table):
            table.setRowCount(0)
        for indicator in self.today_indicators.values():
            indicator.setText("—")
        self.results_text.setText("No well selected")
        self.evidence_state_label.setText("Evidence: select a well")
        self.evidence_open_btn.setEnabled(False)
        if getattr(self, "milestones_widget", None) is not None:
            safe_replace_chart(self.milestones_widget, QLabel("Milestones: no well selected"))
        self.help_label.setVisible(True)
        self.analysis_tabs.setVisible(False)
        self.bottom_widget.setVisible(False)

    def refresh_now(self):
        """Refresh Now / Retry: re-read everything for the current scope (cache bypassed)."""
        self.clear_cache()
        self._data_rev = None
        self.update_all_data()

    def refresh(self):
        # MainWindow.refresh_all_tabs() calls refresh(); the base load_data()
        # is a no-op, which left this page on pre-change numbers.
        self.refresh_now()

    def load_data(self):
        self.refresh_now()

    def cleanup(self):
        self._generation += 1
        self.update_timer.stop()

    def update_all_data(self):
        if not self.current_well_id or not PYQTGRAPH_AVAILABLE:
            # Without PyQtGraph the page shows its notice and has no charts,
            # cards or tables to paint.
            return
        generation = self._generation
        try:
            revision = self._read_revision()
        except Exception as exc:
            logger.error("Analysis data revision unavailable: %s", type(exc).__name__, exc_info=True)
            revision = None
        if revision is None or revision != self._data_rev:
            # Source data changed (or cannot be fingerprinted): no cached value
            # of the old data may be reused.
            self.clear_cache()
            self._data_rev = revision
        failed = []
        self._load_errors = []
        for step in (self.update_kpi_data, self.update_time_depth_data, self.update_npt_data,
                     self.update_performance_data, self.update_daily_data, self.update_analytics,
                     self.load_milestones_data, self.update_evidence):
            if generation != self._generation:
                return  # the selection changed meanwhile; its own update paints
            try:
                step()
            except Exception as exc:
                failed.append(step.__name__)
                logger.error("Analysis update step %s failed: %s", step.__name__,
                             type(exc).__name__, exc_info=True)
        if generation != self._generation:
            return
        failed += [f"read {name}" for name in dict.fromkeys(self._load_errors)]
        if failed:
            self._set_status("🔴 Error in: " + ", ".join(failed) + " - use Refresh Now to retry", "error")
        else:
            self._set_status("🟢 Updated", "ok")
        self.last_update_label.setText(f"Last update: {QTime.currentTime().toString('HH:mm:ss')}")

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

    def export_all_charts(self, filename=None):
        if not self.current_well_id:
            QMessageBox.warning(self, "No Data", "Please select a well first")
            return
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename, _ = QFileDialog.getSaveFileName(
                self, "Export Charts", f"analysis_charts_{timestamp}.pdf",
                "PDF Files (*.pdf);;PNG Images (*.png)"
            )
            if not filename:
                return
        if filename.lower().endswith('.pdf'):
            # The chosen file name is honoured (previously a second dialog
            # was opened and this name was discarded).
            self.export_dashboard(filename)
        else:
            export_mgr = ExportManager(self)
            base = filename.replace('.png', '')
            
            charts = [self.time_depth_plot, self.daily_gain_plot, self.performance_plot, self.npt_pie_plot]
            saved_files = []
            for i, plot in enumerate(charts):
                png_file = f"{base}_chart_{i+1}.png"
                if export_mgr.export_image(plot, png_file):
                    saved_files.append(os.path.basename(png_file))
            self.show_success(f"Exported {len(saved_files)} chart images successfully")
            QMessageBox.information(self, "Export Complete", "Charts successfully exported:\n" + "\n".join(saved_files))

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
                (self.daily_gain_plot, "Report depth change", 50, 50, width-100, height/2 - 100),
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
                "dexponent": self.dexponent_plot,
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
            
    def export_dashboard(self, filename=None):
        """Export the dashboard report to PDF/HTML (the given filename is honoured)."""
        if not self.current_well_id:
            QMessageBox.warning(self, "No Data", "Please select a well first")
            return
        
        if filename is None:
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
            logger.error("Dashboard export error: %s", type(e).__name__, exc_info=True)
            self.show_error(f"Export failed: {type(e).__name__}")

    def _typed_datasets(self):
        """The datasets behind the charts/tables, typed (numbers, dates, None)."""
        tables = {}
        td = self.chart_data.get('time_depth') or {}
        if td.get('data'):
            tables['time_depth'] = (
                ("date", "day", "depth_2400_m", "depth_change_m", "status"),
                [(r['date'], r['day'], r['depth'], r['gain'], r['status']) for r in td['data']])
        npt = self.chart_data.get('npt') or {}
        if npt.get('entries'):
            tables['npt'] = (
                ("date", "from", "to", "hours", "npt_code", "description"),
                [(e['date'], e.get('from'), e.get('to'), e['hours'], e['category'],
                  e['description']) for e in npt['entries']])
        perf = self.chart_data.get('performance') or []
        if perf:
            tables['performance'] = (
                ("date", "bit_run", "avg_rop_m_hr", "wob_mid_klb", "rpm_mid", "torque_mid_klb_ft",
                 "pump_pressure_mid_psi", "depth_out_m", "depth_in_m", "hours_on_bottom_h",
                 "bit_size_in"),
                [(d['date'], d['bit_run'], d['rop'], d['wob'], d['rpm'], d['torque'], d['pressure'],
                  d['depth'], d['depth_in'], d['hours_on_bottom'], d['bit_size']) for d in perf])
        if self._evidence_rows:
            tables['evidence'] = (
                ev.EXPORT_COLUMNS,
                [tuple(getattr(r, c) for c in ev.EXPORT_COLUMNS) for r in self._evidence_rows])
        return tables

    def export_all_data(self, filename=None):
        """Export the analysis datasets with types, units, IDs and metadata.

        Built from the same typed datasets that feed the charts — never from
        QTableWidget text, so a missing value stays empty and a real 0 stays 0.
        """
        if not self.current_well_id:
            QMessageBox.warning(self, "No Data", "Please select a well first")
            return None
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename, _ = QFileDialog.getSaveFileName(
                self, "Export All Analysis Data",
                f"analysis_data_{timestamp}.xlsx",
                "Excel Files (*.xlsx);;CSV Files (*.csv)"
            )
            if not filename:
                return None
        tables = self._typed_datasets()
        if not tables:
            self.show_warning("No analysis data to export for this scope")
            return None
        scope = self._analysis_scope()
        metadata = ev.export_metadata(
            scope.label(), "analysis datasets", "per column name", "see column names (unit suffix)",
            "all dates in scope",
            {"well_id": scope.well_id, "wellbore_id": scope.wellbore_id,
             "tables": ", ".join(tables)})
        try:
            if filename.lower().endswith('.xlsx'):
                ev.export_tables_xlsx(filename, tables, metadata)
                written = [filename]
            else:
                written = ev.export_tables_csv(filename, tables, metadata)
        except Exception as e:
            logger.error("Data export error: %s", type(e).__name__, exc_info=True)
            self.show_error(f"Export failed: {type(e).__name__}")
            return None
        self.show_success("Data exported: " + ", ".join(os.path.basename(f) for f in written))
        return written

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
        """HTML report from the typed datasets; every inserted text is escaped."""
        esc = html_lib.escape
        scope = self._analysis_scope() if self.current_well_id else None
        parts = [f"""
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
            <p><b>Well:</b> {esc(str(self.current_well_name or 'Unknown'))}</p>
            <p><b>Scope:</b> {esc(scope.label() if scope else 'No well selected')}</p>
            <p><b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
            <p><i>{esc(ev.NULL_POLICY)}</i></p>

            <h2>📈 Key Performance Indicators</h2>
            <div>
        """]
        for card, key in zip(self.kpi_cards, ("current_depth", "rig_days", "avg_rop", "total_npt")):
            title = ev.KPI_DEFINITIONS[key][0]
            metric = getattr(card, "metric_value", None)
            value = metric.text() if metric is not None else "—"
            parts.append(f'<div class="kpi"><b>{esc(title)}:</b><br>'
                         f'<span class="kpi-value">{esc(value)}</span></div>')
        parts.append("""
            </div>
            <h2>📋 Depth History</h2>
            <table>
                <tr><th>Date</th><th>Day</th><th>Depth at 24:00 (m)</th><th>Depth change (m)</th><th>Status</th></tr>
        """)

        def cell(value, digits=1):
            if value is None:
                return "—"
            if isinstance(value, float):
                return f"{value:.{digits}f}"
            return esc(str(value))

        td = self.chart_data.get('time_depth') or {}
        for r in (td.get('data') or [])[:20]:
            parts.append("<tr>" + "".join(f"<td>{cell(v)}</td>" for v in (
                r['date'], r['day'], r['depth'], r['gain'], r['status'])) + "</tr>")
        parts.append("""
            </table>
            <h2>⏱️ NPT by code</h2>
            <table>
                <tr><th>NPT code</th><th>Hours</th></tr>
        """)
        npt = self.chart_data.get('npt') or {}
        for code, hours in sorted((npt.get('categories') or {}).items(),
                                  key=lambda kv: kv[1], reverse=True)[:10]:
            parts.append(f"<tr><td>{esc(str(code))}</td><td>{cell(hours)}</td></tr>")
        parts.append("""
            </table>
            <p><i>Generated by DrillMaster</i></p>
        </body>
        </html>
        """)
        return "".join(parts)
